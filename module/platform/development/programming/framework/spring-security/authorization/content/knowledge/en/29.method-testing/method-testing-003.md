# @WithAnonymousUser for unauthenticated user scenarios

> **Scope:** testing Spring Security **method security** in a Java application using Spring Framework/Spring Boot. This lesson focuses on calling methods on Spring beans annotated with `@PreAuthorize`, how **anonymous** users are represented in tests, and how to assert access granted or denied. Examples use Java 17+, JUnit 5, and Spring Security 6.x.

## 1. Learning objectives

After this lesson, you will be able to:

1. Explain why **anonymous is not synonymous with a completely empty `SecurityContext`**.
2. Use `@WithAnonymousUser` to run a single test method as an unauthenticated user, even when the entire test class is annotated with `@WithMockUser`.
3. Test `isAnonymous()`, `isAuthenticated()`, `permitAll()`, and `hasRole(...)` expressions on methods protected by Spring Security.
4. Recognize the right exception when calling a service directly, avoiding confusing method security exceptions with HTTP 401/403 status codes.
5. Avoid "false-passing" tests caused by forgetting `@EnableMethodSecurity`, calling an object created with `new` directly, or bypassing the Spring AOP proxy.

## 2. What is Anonymous in Spring Security?

A request without a logged-in user may still need security rules applied: allowing public content to be viewed while blocking access to personal profiles or data modification. To handle this consistently, Spring Security provides **anonymous authentication**.

On the Servlet stack, when there is no `Authentication` from earlier authentication mechanisms, `AnonymousAuthenticationFilter` normally places an `AnonymousAuthenticationToken` into the `SecurityContext`. The default configuration typically represents the principal as `anonymousUser` with the authority `ROLE_ANONYMOUS`. This is **not a verified logged-in account**.

`@WithAnonymousUser` in the `spring-security-test` module puts an `AnonymousAuthenticationToken` into the test's `SecurityContextHolder` via `WithSecurityContextTestExecutionListener`. As a result:

- `SecurityContextHolder.getContext().getAuthentication()` **can be non-`null`** in an anonymous test.
- `authentication.getPrincipal()` defaults to `anonymousUser`; the default anonymous authority is `ROLE_ANONYMOUS`.
- `AnonymousAuthenticationToken.isAuthenticated()` may return `true` in terms of **the token's internal state**. This **does not mean the user is logged in**. Spring Security uses `AuthenticationTrustResolver` to determine that it is still anonymous; the authorization expression `isAuthenticated()` **does not treat anonymous as a logged-in user**.
- `@WithAnonymousUser` only prepares the security context for the test; the annotation **does not perform HTTP login/logout**, does not invoke `AnonymousAuthenticationFilter` over HTTP, and does not prove that production session/token mechanisms executed.

**Do not** check login status using `authentication != null` or solely `authentication.isAuthenticated()` when the application uses anonymous tokens. For authorization, prefer `isAnonymous()`/`isAuthenticated()` expressions; when classifying in Java code, you can use `AuthenticationTrustResolver`.

### Anonymous differs from an unpopulated context

| State | `SecurityContext` | Meaning in test |
| --- | --- | --- |
| `@WithAnonymousUser` | Contains `AnonymousAuthenticationToken` | Simulates an anonymous principal meaningful to `isAnonymous()` |
| `@WithMockUser` | Contains a mock user's `UsernamePasswordAuthenticationToken` | Assumes an authenticated user with the authorities/roles supplied by the test |
| Test without annotation and without auth set otherwise | May have no `Authentication` | Not guaranteed equivalent to anonymous; depending on expression/config may throw `AuthenticationCredentialsNotFoundException` |
| Real Servlet request through filter chain | `AnonymousAuthenticationFilter` may populate a token if no auth exists | Testing the web path requires separate web/HTTP tests |

Therefore, `@WithAnonymousUser` tests are useful when the goal is to **test method-layer authorization in an anonymous context explicitly and reliably**.

## 3. How @WithAnonymousUser is applied in tests

The annotation is placed on a **test method** or a **test class**:

~~~java
@Test
@WithAnonymousUser
void guestCannotReadPrivateData() {
    // Call a service bean protected by method security.
}
~~~

It relies on Spring TestContext, such as JUnit 5 `SpringExtension` or `@SpringBootTest`. Spring Security Test uses `WithSecurityContextTestExecutionListener` to populate `SecurityContextHolder` before each test and clean up the context afterward. You do not have to manually assign a principal to a ThreadLocal or call `SecurityContextHolder.clearContext()` in regular tests.

The most common use case is a **class that runs as a logged-in user by default** while needing to test a few unauthenticated edge cases:

~~~java
@WithMockUser(username = "member", roles = "USER")
class ExampleTests {

    @Test
    void memberCanReadOwnProfile() {
        // Receives Authentication for "member".
    }

    @Test
    @WithAnonymousUser
    void guestCannotReadOwnProfile() {
        // Method-level annotation overrides the class-level @WithMockUser context.
    }
}
~~~

If you do not place `@WithAnonymousUser` on the second method, it will still run with the `member` user from the class-level annotation and fail to test the anonymous scenario.

By default, the context is set up at the `TestExecutionEvent.TEST_METHOD` phase, meaning before JUnit's `@BeforeEach` callback. If you need setup to happen **after** `@BeforeEach` but before the `@Test` body, use:

~~~java
@WithAnonymousUser(setupBefore = TestExecutionEvent.TEST_EXECUTION)
~~~

Change this timing only when the test setup genuinely depends on security context initialization order. For ordinary tests, keep the default.

## 4. Complete example: testing method authorization with anonymous

We build a Spring bean `ResourceService` with four behaviors:

- `help()`: accessible to everyone, including anonymous and logged-in users.
- `guestWelcome()`: callable only by anonymous users; logged-in users will not satisfy `isAnonymous()`.
- `dashboard()`: requires an authenticated user.
- `adminPanel()`: requires authority `ROLE_ADMIN`.

The goal of the test is to prove **authorization decisions when invoking Spring bean methods**, without starting an HTTP server.

### 4.1. Dependencies

In a Java 17+ project where Spring Boot manages dependency versions, include the corresponding dependencies (`build.gradle` snippet):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-security-test` provides `@WithAnonymousUser`/`@WithMockUser`. `spring-boot-starter-test` provides JUnit Jupiter and Spring Test. The `@EnableMethodSecurity` configuration in the example is required for `@PreAuthorize` annotations to actually be enforced.

### 4.2. Complete test file

Place the file at `src/test/java/com/example/authorization/AnonymousMethodSecurityTest.java`:

~~~java
package com.example.authorization;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = AnonymousMethodSecurityTest.TestConfig.class)
@WithMockUser(username = "member", roles = "USER")
class AnonymousMethodSecurityTest {

    @Autowired
    ResourceService service; // Bean obtained from Spring context, already wrapped by AOP proxy.

    @Test
    @WithAnonymousUser
    void anonymousCanReadPublicHelp() {
        assertEquals("public help", service.help());
    }

    @Test
    @WithAnonymousUser
    void anonymousCanCallGuestOnlyMethod() {
        assertEquals("welcome guest", service.guestWelcome());
    }

    @Test
    @WithAnonymousUser
    void anonymousCannotAccessAuthenticatedMethod() {
        assertThrows(AccessDeniedException.class,
                () -> service.dashboard());
    }

    @Test
    @WithAnonymousUser
    void anonymousCannotAccessAdminMethod() {
        assertThrows(AccessDeniedException.class,
                () -> service.adminPanel());
    }

    @Test
    @WithAnonymousUser
    void anonymousContextHasTokenButIsNotLoggedIn() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        assertInstanceOf(AnonymousAuthenticationToken.class, authentication);
        assertEquals("anonymousUser", authentication.getPrincipal());

        AuthenticationTrustResolver trustResolver =
                new AuthenticationTrustResolverImpl();

        assertTrue(trustResolver.isAnonymous(authentication));
        assertTrue(authentication.isAuthenticated());
        // The token's isAuthenticated() does NOT mean an actual login.
    }

    @Test
    void classLevelMockUserMayAccessAuthenticatedMethod() {
        assertEquals("member dashboard", service.dashboard());
    }

    @Test
    void classLevelMockUserIsNotAnonymous() {
        assertThrows(AccessDeniedException.class,
                () -> service.guestWelcome());

        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();
        AuthenticationTrustResolver trustResolver =
                new AuthenticationTrustResolverImpl();

        assertFalse(trustResolver.isAnonymous(authentication));
    }

    @Test
    @WithMockUser(username = "root", roles = "ADMIN")
    void adminMayAccessAdminMethod() {
        assertEquals("admin panel", service.adminPanel());
    }

    @Configuration(proxyBeanMethods = false)
    @EnableMethodSecurity
    static class TestConfig {
        @Bean
        ResourceService resourceService() {
            return new ResourceService();
        }
    }

    public static class ResourceService {

        @PreAuthorize("permitAll()")
        public String help() {
            return "public help";
        }

        @PreAuthorize("isAnonymous()")
        public String guestWelcome() {
            return "welcome guest";
        }

        @PreAuthorize("isAuthenticated()")
        public String dashboard() {
            return "member dashboard";
        }

        @PreAuthorize("hasRole('ADMIN')")
        public String adminPanel() {
            return "admin panel";
        }
    }
}
~~~

Run (on macOS/Linux; Windows uses `gradlew.bat`):

~~~bash
./gradlew test --tests com.example.authorization.AnonymousMethodSecurityTest
~~~

**Expected result:** 8 tests pass with no fixed business stdout. Denied methods throw an exception in the `AccessDeniedException` hierarchy; allowed methods return the exact strings checked by assertions.

| Test context | Call | Expected |
| --- | --- | --- |
| Anonymous | `help()`, `permitAll()` | Allowed, returns `public help` |
| Anonymous | `guestWelcome()`, `isAnonymous()` | Allowed, returns `welcome guest` |
| Anonymous | `dashboard()`, `isAuthenticated()` | `AccessDeniedException` |
| Anonymous | `adminPanel()`, `hasRole('ADMIN')` | `AccessDeniedException` |
| `member / ROLE_USER` | `dashboard()` | Allowed |
| `member / ROLE_USER` | `guestWelcome()` | `AccessDeniedException` |
| `root / ROLE_ADMIN` | `adminPanel()` | Allowed |

**Why this test is meaningful:** `@WithMockUser` at the class level serves as the default for logged-in user cases. Only tests annotated with `@WithAnonymousUser` switch cleanly to anonymous. The same bean governed by `@PreAuthorize` demonstrates the difference between "public to everyone", "guest only", and "requires privileges after login".

**A limitation to remember:** Tests using class-level `@WithMockUser` verify authorization after an identity already exists; they do not check passwords, login, user data sources, or real tokens. `@WithAnonymousUser` also does not require a browser, session, or HTTP headers; its value here lies in method authorization.

## 5. Reading expressions accurately when not logged in

| Expression on method | Anonymous allowed? | Logged-in user allowed? | When to use |
| --- | --- | --- | --- |
| `@PreAuthorize("permitAll()")` | Yes | Yes | Shared resources, no identity needed |
| `@PreAuthorize("isAnonymous()")` | Yes | No | Behavior that should only appear/operate before login |
| `@PreAuthorize("isAuthenticated()")` | No | Yes, when recognized by Spring Security as authenticated | Personal profile, dashboard |
| `@PreAuthorize("hasRole('ADMIN')")` | No under default role config | Only when `ROLE_ADMIN` is present | Administration |
| `@PreAuthorize("denyAll()")` | No | No | Completely block a behavior |

**Distinguishing `permitAll()` and `isAnonymous()`:** `permitAll()` allows both guests and logged-in users; `isAnonymous()` allows guests only. For example, "read FAQ" can be `permitAll()`, whereas "show registration prompt for guests" can be `isAnonymous()` if business logic genuinely intends to block logged-in users.

**Do not confuse role/authority:** `hasRole("ADMIN")` usually checks for an authority named `ROLE_ADMIN`. `@WithMockUser(roles="ADMIN")` creates the corresponding authority. The anonymous token's `ROLE_ANONYMOUS` is **not** `ROLE_USER` or `ROLE_ADMIN`.

**Do not draw conclusions from `Authentication.isAuthenticated()`:** An anonymous token may have that flag set to `true`, but `isAuthenticated()` in authorization expressions uses Spring Security's classification so it does not treat anonymous as a logged-in user.

## 6. Exceptions in method tests vs. HTTP status codes

When a test calls `service.dashboard()` directly through the Spring AOP proxy, `@PreAuthorize` is evaluated before the method body. If anonymous fails the condition, Spring Security normally throws `AccessDeniedException` (or a subclass). Here **there is no HTTP response**, so you cannot assert 401/403 by only calling a Java method.

When the same method is called behind an HTTP endpoint, `ExceptionTranslationFilter` and the configured `AuthenticationEntryPoint`/`AccessDeniedHandler` can translate the outcome into 401, 403, or a redirect to a login page, depending on the anonymous context and authentication type. Checking HTTP statuses requires writing a separate **MockMvc or HTTP integration test**, sending requests without credentials through `SecurityFilterChain`.

A common mistake is claiming "anonymous calling a service always returns 403". When calling a method directly, what is observed is a **Java exception**; an HTTP status only arises when running the full web path with handlers converting exceptions.

### When HTTP also needs testing, add a separate test

Sketch example **not a standalone program** (applicable only when the project already has the corresponding controller/chain/MockMvc):

~~~java
// Testing that an HTTP request without credentials is blocked.
// Expected status depends on the application's entry point / login configuration.
mockMvc.perform(get("/private"))
       .andExpect(status().isUnauthorized());
~~~

The 401 assertion above is appropriate if the endpoint actually uses an authentication entry point that returns 401 (such as many HTTP Basic/API configurations). With form login, a 302 redirect to the login page may be the correct outcome. Do not copy statuses verbatim from method tests to HTTP tests.

## 7. Why might tests "pass" when the method is actually unprotected?

### 7.1. Forgetting to enable method security

Having `@PreAuthorize` on a method alone is not enough without enabling method security support, for example:

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
    // @PreAuthorize annotations on Spring beans are enforced.
}
~~~

Spring Boot starter security **does not enable** method-level authorization by default. Without `@EnableMethodSecurity`, the annotation may not block any calls at all. A good test suite must include a denial case for anonymous and assert `AccessDeniedException`; if protection is off, that test will fail.

### 7.2. Bypassing the AOP proxy

Two different ways of calling:

~~~java
// WRONG for the goal of testing @PreAuthorize:
ResourceService service = new ResourceService();
service.dashboard(); // Direct call, bypassing the Spring AOP proxy.

// RIGHT in a test with @ContextConfiguration/@EnableMethodSecurity:
@Autowired
ResourceService service;
// service.dashboard() goes through the Spring-managed bean.
~~~

Spring method security operates via interceptors/proxies. Self-invocation (one method in the same object calling another via `this.protectedMethod()`) can also bypass the proxy call; the annotation on the target method may then not execute in proxy mode. Do not use that scenario to conclude `@WithAnonymousUser` does not work.

### 7.3. Using @WithMockUser to fake anonymous

This is **not** an anonymous case:

~~~java
@Test
@WithMockUser(username = "anonymousUser")
void notReallyAnonymous() {
    // This is a UsernamePasswordAuthenticationToken of a mock user,
    // not an AnonymousAuthenticationToken.
}
~~~

The name `anonymousUser` alone does not determine the state. A test like this normally receives `ROLE_USER` (the default of `@WithMockUser`), and `isAuthenticated()` will evaluate differently from `@WithAnonymousUser`.

### 7.4. Having no annotation is not always equivalent to @WithAnonymousUser

In a test where `Authentication` is not initialized, `SecurityContext` may be empty. Method security can throw `AuthenticationCredentialsNotFoundException` when an expression needs a principal; whereas `@WithAnonymousUser` pre-populates an anonymous token so expressions like `isAnonymous()` are evaluated under an anonymous state. Use this annotation when you want tests with **stable unauthenticated guest semantics**.

### 7.5. Production anonymous configuration differs from default

An application may customize the anonymous authority or disable anonymous authentication on the filter chain. `@WithAnonymousUser` tests represent the token with test defaults and do not automatically read every production customization. If logic depends on a special authority name, add matching config/mapping tests and at least one real web test when deployment configuration must be verified.

### 7.6. Reading/setting context at the wrong time or leaking between tests

`@WithAnonymousUser` is attached before the test and cleaned up afterward by Spring TestContext. If you manually modify `SecurityContextHolder` in `@BeforeEach`, `@AfterEach`, new threads, or async code, be aware that the context may be overwritten or not propagated to new threads. If you need the annotation to set up after `@BeforeEach`, see `setupBefore = TestExecutionEvent.TEST_EXECUTION`. Do not enable ThreadLocal inheritance just to make one test pass.

## 8. Checklist for designing method-level anonymous tests

For each protected method, determine whether the behavior is **public**, **guest-only**, **authenticated**, or **role-specific**. The minimal test matrix below covers both directions:

| Test group | User context | Assertion |
| --- | --- | --- |
| Guest can use public functionality | `@WithAnonymousUser` | Call succeeds and check result |
| Guest is blocked from private data | `@WithAnonymousUser` | Throws `AccessDeniedException` |
| Logged-in user can use private data | `@WithMockUser` or `@WithUserDetails` | Call succeeds |
| Logged-in user cannot use guest-only functionality | `@WithMockUser` | Throws `AccessDeniedException` if `isAnonymous()` |
| User without required role is blocked | `@WithMockUser(roles="USER")` | Throws `AccessDeniedException` against `hasRole('ADMIN')` |
| Admin is allowed | `@WithMockUser(roles="ADMIN")` | Call succeeds |
| Unauthenticated behavior over HTTP | MockMvc/Web integration, request without credentials | Assert status/redirect according to actual entry point |

Tests should assert **both return values and access control**, avoiding only checking that a method "does not throw" on the happy path. When a method has side effects, verify that the denied branch **does not mutate data**.

## 9. Self-check questions

**Question 1.** In a test with `@WithAnonymousUser`, `SecurityContextHolder.getContext().getAuthentication()` returns a non-`null` object. Can we conclude the user is logged in?

**Answer:** No. That is an `AnonymousAuthenticationToken`; `AuthenticationTrustResolver`/authorization expressions treat it as anonymous.

**Question 2.** The whole class has `@WithMockUser(roles="ADMIN")`. Why does a test checking a guest need `@WithAnonymousUser` on the method?

**Answer:** To override the admin context granted by the class-level annotation. Otherwise, the test still runs as admin and does not test the unauthenticated case.

**Question 3.** A test calling `service.secret()` under `@WithAnonymousUser` sees `AccessDeniedException`. Can we conclude the HTTP endpoint returns 403?

**Answer:** Not yet. The test confirmed that method authorization denies the call. You must test the request through the web chain and entry point/exception translation to know the specific status/redirect.

**Question 4.** Is `@WithMockUser(username="anonymousUser")` equivalent to `@WithAnonymousUser`?

**Answer:** No. The name is the same, but the `Authentication` type and trust semantics differ.

## 10. Takeaways

`@WithAnonymousUser` gives tests a **predictable anonymous principal**, well suited to proving that methods allow guests into public parts and deny access to parts requiring login. Combine **anonymous allowed**, **anonymous blocked**, **valid user allowed**, and **underprivileged user blocked** cases; and always call a **proxied Spring-managed bean** with `@EnableMethodSecurity` enabled. When you need to confirm which HTTP status an unauthenticated request receives, write a separate web test.

### Official documentation

- Spring Security — Testing Method Security: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Security — `@WithAnonymousUser` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/context/support/WithAnonymousUser.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — Anonymous Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/anonymous.html
- Spring Security — `AuthenticationTrustResolver` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationTrustResolver.html