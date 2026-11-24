# @WithMockUser and the Limits of Simulated Principals in Spring Security Method Testing

> **Scope:** Java 17+, Spring Boot 3.x, Spring Security 6.x, Servlet stack (Spring MVC). The focus is testing `@PreAuthorize`/`@PostAuthorize` and Spring-managed services with method security using `@WithMockUser`. This article explains exactly what is **simulated**, what is **verified**, the limitations of a mock principal, and when `@WithUserDetails`, `@WithSecurityContext`, or real HTTP/login tests are needed. Never use mock-principal test results to claim real-world authentication is secure.

## 1. Problem: Wanting to Test Authorization Without Always Running Real Login

In a Spring MVC application, permissions can be checked at multiple layers:

- Servlet filter chain: `authorizeHttpRequests` decides which requests may enter a URL based on authentication.
- Method security: `@PreAuthorize`, `@PostAuthorize`, `@Secured`, or authorization interceptors decide whether **a method call** is allowed or denied.
- Domain authorization: permissions on **the specific record, tenant, owner**, or concrete business conditions.

When you only want to verify that a method lets users with `DOC_READ` view a document, running login forms, connecting to LDAP/IdP, or minting real JWTs in every test can make tests slow and unfocused. `@WithMockUser` from **spring-security-test** pre-populates a simulated `Authentication` inside the test's Spring Security context.

**However:** a passing `@WithMockUser(roles = "ADMIN")` test **only proves the method's rule accepts an Authentication that already carries ADMIN**. It does not prove the user passed real login, does not prove roles are mapped properly from database/IdP/JWT, does not prove locked accounts are rejected, and does not prove the HTTP API has no bypass path.

### Learning Objectives

After this article, you will be able to:

1. Understand how `@WithMockUser` creates `SecurityContext`, principal, and authorities, and how it is cleaned up between tests.
2. Configure a `@PreAuthorize` service method and write **allow/deny** tests using Spring Boot Test.
3. Distinguish `roles` from `authorities`, username from a real principal object, and `@WithMockUser` from `@WithUserDetails`.
4. Recognize cases where `@WithMockUser` creates **false confidence**, especially custom principals, token/JWT claims, tenant/ownership, database account state, filter chains, and self-invocation.
5. Choose complementary integration tests for HTTP authentication, authority mapping, CSRF, and resource-level permissions.

## 2. How @WithMockUser Works

`@WithMockUser` is in the package:

~~~java
import org.springframework.security.test.context.support.WithMockUser;
~~~

It is backed by **Spring Security Test** via `WithSecurityContextTestExecutionListener` in Spring TestContext. The listener creates a test `SecurityContext`, places the `Authentication` specified by the annotation into the context, and cleans up the context after the test.

A typical annotation:

~~~java
@Test
@WithMockUser(username = "alice", roles = "USER")
void canUseAServiceAsAlice() {
    // Call to a Spring bean with method security.
}
~~~

In this test, `Authentication` has the following representative properties:

| Property | Value / Meaning |
| --- | --- |
| `Authentication.getName()` | `alice`. |
| `Authentication.isAuthenticated()` | `true`: the test token is created in an authenticated state. |
| `Authentication.getPrincipal()` | Usually `org.springframework.security.core.userdetails.User` from Spring Security Test, **not** an `AppUser` entity or IdP principal. |
| `Authentication.getAuthorities()` | Role `USER` becomes `ROLE_USER` by default convention. |
| `Authentication.getCredentials()` | Placeholder information used in the token; no password verification flow runs as in real login. |
| `SecurityContextHolder.getContext()` | Holds the test authentication in the thread/context set up by the test listener. |

**By default**, writing just `@WithMockUser` gives the test user username `user`, default placeholder password `password`, and role `USER` (authority `ROLE_USER`). It does **not** represent an anonymous user.

Watch out for two commonly misunderstood words:

- **Mock** here means *simulating security state*; the principal is usually a concrete `User` object, not an arbitrary Mockito mock.
- **Authenticated** here is a flag on the test `Authentication`. No password encoder, password verification, MFA, JWT signature check, or HTTP login flow runs automatically just from the annotation.

Example inspecting the context in a test with Spring TestContext:

~~~java
@Test
@WithMockUser(username = "alice", roles = {"USER", "EDITOR"})
void showsWhatIsStoredInContext() {
    Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();

    assertEquals("alice", auth.getName());
    assertTrue(auth.isAuthenticated());
    assertTrue(auth.getAuthorities().stream()
            .anyMatch(a -> a.getAuthority().equals("ROLE_EDITOR")));
    assertInstanceOf(
            org.springframework.security.core.userdetails.User.class,
            auth.getPrincipal());
}
~~~

Imports for `Authentication`, `SecurityContextHolder`, and JUnit 5 static assertions must be added per the project. The snippet above is an **illustrative test method**, not a standalone Java file. It intentionally inspects the simulated principal to remind you that the test **does not read a real user entity**.

## 3. Roles and Authorities: Misconfiguration Leads to Wrong Tests

Spring Security distinguishes **role** (conventionally prefixed) and **authority** (exact name).

~~~java
@WithMockUser(username = "alice", roles = "ADMIN")
// Corresponding GrantedAuthority is typically "ROLE_ADMIN".

@WithMockUser(username = "alice", authorities = "DOC_READ")
// GrantedAuthority has exact name "DOC_READ".
~~~

The two annotations above are **alternative declaration examples** for a method/class; do not place both in sequence expecting two simultaneous users.

| Test Configuration | Primary GrantedAuthority | Fits With |
| --- | --- | --- |
| `@WithMockUser(roles = "ADMIN")` | `ROLE_ADMIN` | `hasRole('ADMIN')` or `hasAuthority('ROLE_ADMIN')`. |
| `@WithMockUser(roles = "USER")` | `ROLE_USER` | `hasRole('USER')`. |
| `@WithMockUser(authorities = "DOC_READ")` | `DOC_READ` | `hasAuthority('DOC_READ')`. |
| `@WithMockUser(authorities = {"DOC_READ", "DOC_WRITE"})` | Two exact authorities. | Rules requiring one or both permissions. |
| `@WithMockUser` | `ROLE_USER` | Testing default user behavior. |

**Do not** declare `roles = "ROLE_ADMIN"` when using the default convention: the `ROLE_` prefix is added by the framework for roles. Use `roles = "ADMIN"`. If the application changes the role prefix or uses a custom authority mapper, tests must reflect the actual policy and not assume every authority starts with `ROLE_`.

Both `roles` and `authorities` exist on the annotation, but when `authorities` is explicitly set, permissions are determined by that authorities list; do not mix both attributes expecting Spring to merge every role automatically. To test multiple permissions, express them explicitly in `authorities`.

### Choosing the Right Condition for the Use Case

- Broad role permission: `@PreAuthorize("hasRole('ADMIN')")`.
- Exact permission: `@PreAuthorize("hasAuthority('DOC_READ')")`.
- Permission combined with resource ownership: `@PreAuthorize("hasAuthority('DOC_READ') and #p0 == authentication.name")`.
- Multi-tenant: requires a server-side policy aware of the principal's tenant and the resource's tenant; role `USER` alone is not enough.

Tests should include both **right role but wrong owner** and **right owner but missing permission** to avoid one-sided positive testing.

## 4. Sample Spring Boot Project: Protecting a Real Method

The following examples combine into a Spring Boot 3.x (Java 17+) project in package `com.example.methodauth`. Tests run in a **Spring ApplicationContext**, not standalone Java SE: use Maven/Gradle with the corresponding dependencies.

### 4.1 Required Dependencies

In `pom.xml` of a Spring Boot project using the Boot parent/BOM, the `dependencies` section needs at least:

~~~xml
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
~~~

If the app also uses MVC endpoints, add `spring-boot-starter-web`. No network/IdP is needed to run tests that only call service methods with `@WithMockUser`.

### 4.2 Enabling Method Security

File `src/main/java/com/example/methodauth/MethodAuthApplication.java`:

~~~java
package com.example.methodauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class MethodAuthApplication {

    public static void main(String[] args) {
        SpringApplication.run(MethodAuthApplication.class, args);
    }
}
~~~

`@EnableMethodSecurity` activates processing of authorization annotations on Spring-managed beans. In Spring Security 6, simply adding `@PreAuthorize` to a Java method does not make it run on an object created with `new`.

With service proxies, **calls must go through the Spring bean/proxy**. A common mistake:

~~~java
// Not a way to prove method security is active:
DocumentService service = new DocumentService();
service.readForOwner("alice");
~~~

If instantiated with `new` as above, the object is not wrapped by the container for method authorization; tests may pass right through the rule without catching errors. The section below uses `@Autowired` to invoke the bean from `ApplicationContext`.

### 4.3 Service Containing Permission and Ownership Policy

File `src/main/java/com/example/methodauth/DocumentService.java`:

~~~java
package com.example.methodauth;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    @PreAuthorize(
        "hasAuthority('DOC_READ') and #p0 == authentication.name")
    public String readForOwner(String ownerUsername) {
        return "document for " + ownerUsername;
    }

    @PreAuthorize("hasRole('ADMIN')")
    public String deleteForAdministration(long documentId) {
        return "deleted " + documentId;
    }
}
~~~

This code is **self-contained in a Spring bean context**: methods simply return strings so both authorization and return value can be tested. It does not query a database or actually delete documents.

- `hasAuthority('DOC_READ')` checks the document-read permission.
- `#p0` is the first method parameter (by index), so it does not depend on whether the compiler preserves parameter names. Comparing it with `authentication.name` illustrates an ownership check.
- `hasRole('ADMIN')` requires authority `ROLE_ADMIN`.
- A real policy should read owner/tenant from a **trusted database/ACL** based on the resource ID, rather than **trusting an `ownerUsername` supplied by the client**. Using an owner parameter here is solely to demonstrate the SpEL mechanism; section 8 clarifies the limitation.
- Method authorization runs **before entering the method body** for `@PreAuthorize`. If the rule denies access, the `return` statement does not execute.

## 5. Testing Both Allowed and Denied Paths

File `src/test/java/com/example/methodauth/DocumentServiceSecurityTest.java`:

~~~java
package com.example.methodauth;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

@SpringBootTest
class DocumentServiceSecurityTest {

    @Autowired
    DocumentService documents;

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void permitsOwnerWithReadPermission() {
        assertEquals(
                "document for alice",
                documents.readForOwner("alice"));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void deniesUserReadingDifferentOwner() {
        assertThrows(
                AccessDeniedException.class,
                () -> documents.readForOwner("bob"));
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void deniesOwnerWithoutReadPermission() {
        assertThrows(
                AccessDeniedException.class,
                () -> documents.readForOwner("alice"));
    }

    @Test
    @WithMockUser(username = "manager", roles = "ADMIN")
    void permitsAdministrator() {
        assertEquals(
                "deleted 99",
                documents.deleteForAdministration(99L));
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void deniesNormalUserAdministration() {
        assertThrows(
                AccessDeniedException.class,
                () -> documents.deleteForAdministration(99L));
    }
}
~~~

This test suite runs against a **Spring-managed service** with method authorization. Expectations:

| Test | Simulated Authentication | Method Call | Expected Outcome |
| --- | --- | --- | --- |
| `permitsOwnerWithReadPermission` | alice, `DOC_READ` | `readForOwner("alice")` | Allowed, returns `document for alice`. |
| `deniesUserReadingDifferentOwner` | alice, `DOC_READ` | `readForOwner("bob")` | `AccessDeniedException`. |
| `deniesOwnerWithoutReadPermission` | alice, `ROLE_USER` | `readForOwner("alice")` | `AccessDeniedException` due to missing `DOC_READ`. |
| `permitsAdministrator` | manager, `ROLE_ADMIN` | `deleteForAdministration(99)` | Allowed, returns `deleted 99`. |
| `deniesNormalUserAdministration` | alice, `ROLE_USER` | `deleteForAdministration(99)` | `AccessDeniedException`. |

Run in a Spring Boot Maven project containing the classes/dependencies above:

~~~bash
mvn test
~~~

Do not assume fixed Maven stdout: printed output depends on plugin versions and other tests in the project. In this example, the five tests are expected to pass if the Spring context initializes properly and `@EnableMethodSecurity` is in effect. If **all deny tests fail to block**, check: is the object a Spring bean? Is method security enabled? Does the call go through the proxy? Is the annotation enforced?

### Why Must Denied Outcomes Be Tested?

Testing only that an `ADMIN` user passes the rule does not prove a `USER` is blocked. A misconfigured `permitAll` can still let positive tests pass. Negative tests force verification of the **denial path**, catching missing interceptors, wrong annotations, missing authorities, or broken ownership logic.

Conversely, if you only assert HTTP status 403 over HTTP, a test might **pass for the wrong reason** (such as a missing CSRF token) without method security ever being invoked. With service-level unit/integration tests as above, `assertThrows(AccessDeniedException.class, ...)` isolates the method policy. With HTTP tests, CSRF and authentication/authorization must be clearly separated.

## 6. @WithMockUser Defaults and Options

### 6.1 Default Values

~~~java
@Test
@WithMockUser
void testAsDefaultUser() {
    // Authentication.name = "user"
    // Granted authority typically = ROLE_USER
}
~~~

A test without `@WithMockUser` does not automatically run as an anonymous user; in many method tests without a `SecurityContext`, `Authentication` can be `null` and trigger `AuthenticationCredentialsNotFoundException` when a rule requires authentication. To intentionally test anonymous state, use `@WithAnonymousUser` (with a suitable Spring TestContext setup) or an HTTP flow carrying no credentials.

### 6.2 username, password, roles, authorities

~~~java
@WithMockUser(
    username = "report-reader",
    authorities = {"DOC_READ", "REPORT_VIEW"}
)
~~~

`username` sets the test principal's name. `password`, if specified, is merely a placeholder string attached to the test user; Spring Security Test **does not call `PasswordEncoder.matches(...)`** or check the password against a user store. `roles` specifies roles without the `ROLE_` prefix in the annotation. `authorities` specifies exact authority names.

Therefore, a test using:

~~~java
@WithMockUser(
    username = "account-does-not-exist",
    password = "wrong-password",
    roles = "ADMIN"
)
~~~

**can still pass** `@PreAuthorize("hasRole('ADMIN')")`. That is the intended behavior of the annotation: it **deliberately skips real login** to test authorization with the specified permissions. Never use such a result to claim the account exists or the password is protected.

### 6.3 Class-Level vs. Method-Level Annotations

`@WithMockUser` can be placed on a class so tests share a default principal. A method with its own annotation can define a principal for that specific test. However, each test should have **explicit, targeted identity/permissions**; overusing class-level annotations can obscure the security condition a test is supposed to verify.

### 6.4 Timing of SecurityContext Setup

`@WithMockUser` has the option:

~~~java
@WithMockUser(
    username = "alice",
    roles = "USER",
    setupBefore = TestExecutionEvent.TEST_EXECUTION
)
~~~

Import `org.springframework.security.test.context.support.TestExecutionEvent`. By default `setupBefore = TEST_METHOD`: the context is created before the JUnit/Spring `@BeforeEach` callback phase. With `TEST_EXECUTION`, the context is set up later, after `@BeforeEach` and right before the test body. This option is useful when setup deliberately avoids having a mock `Authentication` until the test itself starts.

The test listener manages context cleanup, preventing permission leaks between tests in a standard environment. However, if you spawn custom threads, run `@Async`, use executors, or store `Authentication` in static/shared mutable state, the context may **not automatically propagate to other threads**; test context propagation separately instead of relying solely on `@WithMockUser`.

## 7. Biggest Limitation: The Principal Is Simulated, Not a System User

`@WithMockUser` creates a Spring Security Test `User` with a username and authorities, not a domain entity. It does not invoke:

- `UserDetailsService.loadUserByUsername(...)`;
- user repository/database queries;
- password hash verification or locked/disabled/expired status checks;
- IdP/OIDC/SAML or JWT signature/issuer/audience/expiry validation;
- mapping groups/claims from a provider to application authorities;
- account linking, tenant membership, or system profile enrichment;
- HTTP filter chain, session, CSRF, CORS, or custom authentication converters simply because a method annotation is present.

This can leave tests green while the real system is broken: for example, JWT claim `roles=["admin"]` is not mapped by the converter to `ROLE_ADMIN`, or the IdP returns a differently named group. A `@WithMockUser(roles="ADMIN")` test **bypasses that converter**, so it still passes.

### 7.1 Risk of Wrong Principal Cast

Suppose production code expects:

~~~java
AppPrincipal principal =
        (AppPrincipal) authentication.getPrincipal();
String tenantId = principal.tenantId();
~~~

This illustrative snippet requires the application's `AppPrincipal` class and a valid `authentication` variable; it **will not work** with the default `User` principal from `@WithMockUser` because it is not of type `AppPrincipal`. You may hit `ClassCastException` or a SpEL rule missing the property when accessing `principal.tenantId`.

This separates **two kinds of testing problems**:

1. Only testing rules based on username + standard authorities: `@WithMockUser` is usually sufficient for creating a simple context.
2. Testing rules/code paths requiring claims, `tenantId`, `userId`, domain principal types, or custom authorities: you must build the right principal shape via `@WithSecurityContext` or an appropriate test annotation, and still write real integration tests for converters/IdP.

### 7.2 A Mock Principal Does Not Guarantee Data-Level Permissions

Even the `#p0 == authentication.name` rule in the `DocumentService` example only compares a method parameter with the username. If a controller passes a client-supplied `ownerUsername`, a user can supply their own username to make the rule pass while the actual document ID belongs to someone else.

For production, accept `documentId`, look up ownership/tenant from trusted data, and check together with `Authentication`:

~~~java
@PreAuthorize("@documentPolicy.canRead(authentication, #p0)")
public Document readById(long documentId) {
    return documentRepository.findById(documentId).orElseThrow();
}
~~~

This snippet is an **architectural pattern** and does not run standalone because `Document`, `documentPolicy`, and `documentRepository` are application-specific components. In production, constrain queries by owner/tenant and handle race/TOCTOU conditions properly. `@WithMockUser` tests remain useful for roles/authorities, but verifying real DB owners, tenant isolation, and resource scoping requires tests with data fixtures or corresponding integration tests.

## 8. When to Use @WithUserDetails Instead of @WithMockUser

Spring Security Test provides `@WithUserDetails`:

~~~java
@Test
@WithUserDetails(
    value = "alice",
    userDetailsServiceBeanName = "userDetailsService"
)
void usesARealUserDetailsObjectFromService() {
    // Principal loaded from the configured UserDetailsService.
}
~~~

The example above is a **test method** that only runs when the Spring context has a `UserDetailsService` bean named `userDetailsService` and actually finds user `alice`.

Differences:

| Characteristic | `@WithMockUser` | `@WithUserDetails` |
| --- | --- | --- |
| Username source | From the annotation. | Calls `UserDetailsService` in the test context. |
| Principal | Test-created Spring Security `User`. | `UserDetails` returned by the service; can be a custom principal. |
| Requires account in user store? | **No**. | **Yes** (per service/test fixture). |
| Actually runs login/password check? | No. | **No**: it loads `UserDetails`, without verifying passwords via an authentication provider. |
| Checks account/tenant state? | No. | Can read real data from the user service, yet **does not prove** the authentication provider rejects locked/disabled accounts. |
| Speed and scope | Lightweight, rule-focused. | More coupled to user service, DB fixtures, or bean wiring. |

Use `@WithUserDetails` when code needs a custom `UserDetails` and you want to test with data supplied by the service; still distinguish "the service found the user" from "the user logged in successfully". If you want to verify a locked account is blocked by real login, attempt login through the filter/provider rather than pre-assigning authentication.

## 9. Building @WithSecurityContext for a Custom Principal

When the production principal carries a specific `tenantId` or `userId`, you can write a dedicated annotation with `@WithSecurityContext`. The example below builds a **controlled `AppPrincipal` in tests**. It still simulates authentication (does not prove login), yet **the principal type matches the business code's contract**.

### 9.1 Domain Principal in Tests

File `src/test/java/com/example/methodauth/AppPrincipal.java`:

~~~java
package com.example.methodauth;

import java.security.Principal;

public record AppPrincipal(String username, String tenantId)
        implements Principal {

    @Override
    public String getName() {
        return username;
    }
}
~~~

This is a Java record (Java 17+), with record accessors `username()` and `tenantId()`. Implementing `Principal` lets `Authentication.getName()` return the proper username when using this object. In production, use the real domain principal type rather than a test-only record.

### 9.2 Custom Test Annotation

File `src/test/java/com/example/methodauth/WithTenantUser.java`:

~~~java
package com.example.methodauth;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.security.test.context.support.WithSecurityContext;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.METHOD, ElementType.TYPE})
@WithSecurityContext(factory = WithTenantUserFactory.class)
public @interface WithTenantUser {

    String username() default "alice";

    String tenantId() default "team-a";
}
~~~

### 9.3 Factory Setting a Typed Simulated Authentication

File `src/test/java/com/example/methodauth/WithTenantUserFactory.java`:

~~~java
package com.example.methodauth;

import java.util.List;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithSecurityContextFactory;

public class WithTenantUserFactory
        implements WithSecurityContextFactory<WithTenantUser> {

    @Override
    public SecurityContext createSecurityContext(WithTenantUser annotation) {

        AppPrincipal principal = new AppPrincipal(
                annotation.username(), annotation.tenantId());

        Authentication authentication =
                UsernamePasswordAuthenticationToken.authenticated(
                    principal,
                    "not-a-real-credential",
                    List.of(new SimpleGrantedAuthority("DOC_READ")));

        SecurityContext context =
                SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authentication);
        return context;
    }
}
~~~

The factory has an implicit public no-arg constructor and creates an **authenticated test `Authentication`** with an `AppPrincipal` principal. `"not-a-real-credential"` is not checked against any user store; do not treat it as a valid password. The factory exists only in `src/test/java`, not as a production login system.

### 9.4 Policy Accepting Authentication and Checking Tenant

File `src/main/java/com/example/methodauth/TenantPolicy.java` (the demo uses `AppPrincipal` equivalent to the production type; in a real project, place the domain principal in `src/main/java`):

~~~java
package com.example.methodauth;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("tenantPolicy")
public class TenantPolicy {

    public boolean canRead(
            Authentication authentication, String tenantId) {
        if (authentication == null ||
                !(authentication.getPrincipal() instanceof AppPrincipal p)) {
            return false;
        }

        boolean canReadDocs = authentication.getAuthorities().stream()
                .anyMatch(a -> "DOC_READ".equals(a.getAuthority()));

        return canReadDocs && p.tenantId().equals(tenantId);
    }
}
~~~

**Important regarding file location:** `TenantPolicy` in `src/main/java` must reference an `AppPrincipal` type that also lives in **`src/main/java`** in a real project. If using this example with a real policy, move `AppPrincipal.java` from section 9.1 into `src/main/java/com/example/methodauth/` (and **do not** keep a duplicate copy in `src/test/java`). The factory and `@WithTenantUser` stay in test sources. This separation prevents production code from referencing classes that only exist during test runs.

File `src/main/java/com/example/methodauth/TenantDocumentService.java`:

~~~java
package com.example.methodauth;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class TenantDocumentService {

    @PreAuthorize("@tenantPolicy.canRead(authentication, #p0)")
    public String readFromTenant(String tenantId) {
        return "tenant " + tenantId;
    }
}
~~~

In this example, the policy compares the principal's tenant with the passed `tenantId`. In a real system, the document's tenant must be fetched from the server-side database by document ID rather than trusting a client-supplied `tenantId`. This policy is purely to demonstrate the principal/type mechanism.

### 9.5 Test Demonstrating the Difference Between Default and Custom Principals

File `src/test/java/com/example/methodauth/TenantDocumentServiceTest.java`:

~~~java
package com.example.methodauth;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

@SpringBootTest
class TenantDocumentServiceTest {

    @Autowired
    TenantDocumentService service;

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void plainMockUserHasWrongPrincipalType() {
        assertThrows(AccessDeniedException.class,
                () -> service.readFromTenant("team-a"));
    }

    @Test
    @WithTenantUser(username = "alice", tenantId = "team-a")
    void correctTenantPrincipalCanRead() {
        assertEquals("tenant team-a", service.readFromTenant("team-a"));
    }

    @Test
    @WithTenantUser(username = "alice", tenantId = "team-a")
    void cannotCrossTenantBoundary() {
        assertThrows(AccessDeniedException.class,
                () -> service.readFromTenant("team-b"));
    }
}
~~~

These tests demonstrate:

- `@WithMockUser` has the right username and `DOC_READ` but **is not an `AppPrincipal`**, so the policy denies access.
- `@WithTenantUser` supplies the expected type and `tenantId`, enabling testing of the domain policy logic.
- A user belonging to `team-a` cannot read `team-b`.

**This still does not test how production constructs `AppPrincipal`** from JWT/OIDC/SSO/database. Integration tests must verify real identity mapping, especially issuer/tenant claims and permissions.

## 10. What Should Be Used for JWT, OAuth2, OIDC, and SAML?

In a system receiving JWT access tokens at a Resource Server, the principal is typically a `Jwt` or `JwtAuthenticationToken`, with claims/authorities processed by a converter. `@WithMockUser` does not check:

- JWT signature, issuer, audience, expiry, or clock skew;
- converter mapping from scope/role claims to `GrantedAuthority`;
- token revocation/introspection when using opaque tokens;
- tenant/userId mapping and the expected principal object.

When testing a method policy that only relies on `hasAuthority("SCOPE_docs.read")`, `@WithMockUser(authorities = "SCOPE_docs.read")` can be used to isolate the policy. However, if code needs `Jwt` claims or issuer/tenant-reading logic, use a properly typed principal, Spring Security Test request post-processors such as `jwt()`/`opaqueToken()` in HTTP tests where appropriate, and separately test the converter/trust chain with real JWT validation in a test environment.

With OAuth2 Login/OIDC, the principal may be an `OAuth2User` or `OidcUser`; with SAML2 Login, it may be a `Saml2AuthenticatedPrincipal`. `@WithMockUser` **does not** carry the attributes/claims of those principals. Spring Security Test provides mock login mechanisms for those protocols depending on version; use the appropriate test support and always separate **policy tests** from **integration tests verifying protocol responses**.

### Why Are Both Mock and Real-Path Tests Needed?

A system can have a flawless rule:

~~~java
@PreAuthorize("hasRole('ADMIN')")
public void executeSensitiveOperation() {
    // ...
}
~~~

Yet if the production SAML groups mapper is wrong and every user receives `ROLE_ADMIN`, the `@WithMockUser` role test suite stays green. You need additional tests for **authority mapping** and the **real authentication path** to prove ordinary users cannot obtain `ADMIN` privileges.

## 11. How Do Method Security Tests Differ from HTTP/MockMvc Tests?

| Test Type | Simulated Subject | Scope It Verifies | Does Not Automatically Verify |
| --- | --- | --- | --- |
| `@SpringBootTest` + `@WithMockUser` calling Spring bean | Test `SecurityContext` | `@PreAuthorize`/`@PostAuthorize`, SpEL, Authentication/args policy, method behavior. | Real login, URL filter chain, CSRF, CORS, converters, HTTP status. |
| `@WebMvcTest` + MockMvc `@WithMockUser` | In-test HTTP request with mock security context | URL matchers, Spring MVC controller wiring, HTTP status, possibly method security if the slice enables/wires it. | Real IdP/DB and full production login. |
| MockMvc `.with(user(...))` | Test request-specific user | Attaches identity to a single request, allowing multiple principals in one test method. | Real authentication via password encoder. |
| MockMvc `.with(jwt())` | Mock JWT/authentication attached to request | Request authorization by test JWT claims/authorities. | Real JWT signature/issuer/audience unless hitting the decoder path. |
| Integration test login / test sandbox IdP | Real credentials/tokens through filter/provider | Authentication pipeline, user/role mapping, session/redirect, and end-to-end API policy. | Behavior in every production environment if configs differ. |

### Direct HTTP Test Idea Example

If you want to verify **a GET endpoint** is restricted to admins, use MockMvc and Spring Security Test:

~~~java
mvc.perform(get("/admin/dashboard")
        .with(user("alice").roles("USER")))
   .andExpect(status().isForbidden());

mvc.perform(get("/admin/dashboard")
        .with(user("manager").roles("ADMIN")))
   .andExpect(status().isOk());
~~~

This is an **illustrative snippet** assuming `MockMvc mvc`, static imports, the `/admin/dashboard` endpoint, and a `SecurityFilterChain` protecting the URL already exist. It does not run standalone. For POST, add `csrf()` when CSRF is enabled, to avoid passing due to a 403 from a missing token rather than missing permissions.

`@WithMockUser` in a MockMvc test can supply context to requests through Spring Security test integration, but to test the filter chain properly, ensure MockMvc is configured with Spring Security (for example, `@AutoConfigureMockMvc` in `@SpringBootTest`). Avoid disabling filters or using a standalone MockMvc without the chain attached and concluding server authorization is protected.

## 12. Distinguishing Failure Modes

In method tests, symptoms and root causes can vary:

| Symptom | Possible Cause | What to Check |
| --- | --- | --- |
| `@WithMockUser` test still throws `AccessDeniedException` | Missing authority, wrong SpEL rule, tenant/owner mismatch, or wrong custom principal type. | Print/inspect test authorities and expression; verify policy bean. |
| Method that should deny still executes | `@EnableMethodSecurity` not enabled, service instantiated with `new`, self-invocation, or annotation not intercepted. | Check Spring bean proxy, method visibility/public method, actual call path. |
| No annotation, throws `AuthenticationCredentialsNotFoundException` | No `SecurityContext` where method security requires authentication. | Use `@WithMockUser`/`@WithAnonymousUser` intentionally or configure Spring TestContext. |
| `ClassCastException` on principal | Code expects custom principal, test has Spring Security `User`. | Use `@WithUserDetails` or `@WithSecurityContext` with the right type. |
| `@WithUserDetails` fails to load user | Bean name/user not found, or DB fixture not yet seeded. | Check `UserDetailsService`, test data, transaction lifecycle. |
| `@WithMockUser(roles = "ROLE_ADMIN")` fails | Role declared with duplicate/invalid prefix per convention. | Use `roles = "ADMIN"` or `authorities = "ROLE_ADMIN"`. |
| HTTP deny test returns 403 even before method runs | CSRF blocked first, or URL authorization blocked first. | Add `csrf()` and configure request to isolate each mechanism; test service separately. |
| Method test passes but production JWT/OIDC login fails | Login/validator/converter bypassed in mock principal tests. | Add tests for filters, token verification, mappers, and user provisioning. |
| Role changes in DB not reflected in test | Hard-coded `MockUser` permissions do not query DB. | Use test fixtures for authority mapper/DB; verify role revocation. |
| `@WithMockUser` test affects another test | Shared thread/executor/manually set security context not cleaned up, or custom test harness. | Use Spring TestContext listener, reset state, avoid static security context. |

**Do not treat a "green test" as a blanket conclusion.** State clearly which verification ran: method authorization with a simulated identity; user store lookup; token/SSO integration; HTTP URL security; CSRF; or data-level permissions.

## 13. Best Practices for Testing @PreAuthorize and @PostAuthorize

### Testing Positive, Negative, and Boundary Cases

- **Has permission, right owner/tenant:** allow.
- **Has permission, wrong owner/tenant:** deny.
- **Right owner, missing permission:** deny.
- **Admin and non-admin roles:** test both.
- **Anonymous/unauthenticated:** deny per policy; distinguish method exceptions from HTTP 401/403/redirect.
- **Null/missing claim:** do not grant permissions by default.
- **Non-existent, deleted, or locked resource:** policy must fail-closed without leaking information.
- **Multi-tenant and distinct role mappings:** test against cross-tenant elevation.

### Post-Authorization and Return Values

`@PostAuthorize` checks **after method execution**, usually suited for conditions based on the return value (`returnObject`). It is **unsuitable** for protecting an operation with critical side effects if it only denies after writing/deleting — the side effect may already have occurred before denial. Place `@PreAuthorize` or a pre-check policy before state-changing operations. `@PostAuthorize` tests must verify object-level conditions rather than only positive role cases.

### Avoiding Policy Bypass via Same-Class Calls

AOP proxy-based method security normally does not intercept self-invocation (one method on a bean calling an annotated method on the same bean via `this.`). A test calling `service.securedMethod()` directly may pass, while production code calling via `service.someOtherMethod()` on the same object may bypass it. Tests should cover real entry points and place protected methods on clear bean boundaries.

### Thread-Bound Context

The default security context has a thread-bound lifecycle in many scenarios; `@WithMockUser` does not automatically ensure authentication propagates to `@Async`, scheduled tasks, or thread pools. When testing work running on other threads, use Spring Security-supported context propagation mechanisms or an appropriate service identity model and test them separately. Do not create a fake `ADMIN` permission in a worker thread just to "make the test pass".

## 14. Checklist Before Accepting a Security Test Suite

1. `spring-security-test` matches the Spring Security version, and Spring TestContext is active.
2. Method security is enabled (`@EnableMethodSecurity`), and tests call Spring-managed beans through the interceptor/proxy, not objects created with `new`.
3. Tests specify **accurate username, roles, and authorities**, not relying on default `USER` when business logic requires other permissions.
4. Both positive and negative tests exist for the same policy; do not assert only "no exception".
5. Wrong owner/tenant, missing permission, and non-existent resources are tested when relevant.
6. If code uses a custom principal, tests provide the exact type/structure via `@WithUserDetails` or `@WithSecurityContext` rather than casting a mock `User` to a domain principal.
7. `@WithMockUser` is not used to prove password checks, locked-account rejection, JWT validation, OAuth2/SAML handshakes, or group mappers.
8. Separate integration tests exist for the real authentication path (matching the architecture), real authorities from IdP/DB/claims, and session/CSRF at the HTTP layer.
9. For HTTP 403 tests, CSRF, URL authorization, and method authorization are isolated rather than treating any 403 as proof of the intended policy.
10. Differences between test and prod profiles, filter registration, role prefixes, and security configuration have been evaluated.
11. SecurityContext/tokens/test credentials are not shared across tests via static state or uncleaned executors.
12. Results are reported strictly within the **actual test scope executed**, avoiding claims like "entire system security tested" from a few `@WithMockUser` tests.

## 15. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| "`@WithMockUser` logs in a real user from the database." | No; it directly constructs a simulated Spring Security `Authentication` from the annotation. |
| "Adding role `ADMIN` in the annotation proves a user can be granted the right permission." | It only proves the method accepts an `Authentication` carrying that role; real-world authority mappers remain untested. |
| "`@WithMockUser(password = 'wrong')` will be rejected on login." | There is no password verification in the annotation. |
| "The principal is always the project's `AppPrincipal` class." | By default the principal is Spring Security `User`; custom types require separate setup. |
| "Green method tests prove the HTTP endpoint URL is secure." | Method tests do not run the Servlet filter chain or check every URL. |
| "Checking 403 means `@PreAuthorize` denied the request." | 403 can also come from CSRF or URL authorization; mechanisms must be isolated. |
| "`roles` and `authorities` are the same thing." | `roles` uses the `ROLE_` prefix by convention; `authorities` is an exact string. |
| "`@WithUserDetails` verifies passwords and MFA." | It only loads `UserDetails` to build test authentication, without performing real login. |
| "An authenticated user can read any resource." | Object-level owner/tenant/ACL checks are required on the data itself. |
| "If `@WithMockUser` passes, every production code path is properly blocked." | AOP self-invocation, principal mapping, filters, converters, and multiple entry points all require dedicated tests. |

## 16. Summary

**`@WithMockUser` is a strong tool for testing *method authorization* under a `SecurityContext` with intentionally constructed principal and authorities.** It works well for writing fast, clear tests for `@PreAuthorize`, `ADMIN`/`USER` roles, custom permissions, and basic owner/tenant checks — provided tests call a Spring-managed bean and method security is enabled.

However, **`@WithMockUser` is not a real login, and the default principal is not the application's domain/SSO/JWT user**. Everything left unverified — passwords/MFA, IdP/JWT, authority mapping, account status, session/CSRF, HTTP filter chains, real resources, and bypass call paths — requires other tests. When code requires a custom principal, use `@WithUserDetails` or `@WithSecurityContext`; when verifying real-world identity and permission sources, add integration tests following the real production authentication mechanism.

**Quick rule of thumb:** *Use `@WithMockUser` to ask "If a user has identity and permissions X, how does the method behave?", never to conclude "The system verified the user truly has permissions X."*

## References

- Spring Security Reference — Testing Method Security: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Security Reference — Running as a User in Spring Security Test: https://docs.spring.io/spring-security/reference/servlet/test/method.html#test-method-withmockuser
- Spring Security Reference — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security Reference — MockMvc Testing: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
