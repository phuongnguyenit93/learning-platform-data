# Method testing with `@WithSecurityContext`: custom principals and authority sets

## 1. When do you need `@WithSecurityContext`?

In Spring Security method security testing, `@WithMockUser` helps simulate a simple user with a username, roles, or authorities. However, real-world applications often have a **custom principal** carrying `tenantId`, `organizationId`, account type, or other attributes that `@PreAuthorize` expressions must inspect. In such cases, a test supplying only username/role does not simulate enough security data.

Business example: a user may view a document only when they **simultaneously** hold the `document:read` authority and belong to the document's tenant. An approver must have the `APPROVER` role and also belong to the same tenant.

`@WithSecurityContext` lets you create a **custom test annotation**. This annotation specifies a `WithSecurityContextFactory`, where you construct a `SecurityContext` containing the `Authentication`, principal, and set of `GrantedAuthority` instances tailored for each test.

| Tool | Principal created | When suitable |
| --- | --- | --- |
| `@WithMockUser` | Default Spring Security Test principal, typically `User` | Only simple username, role, or authorities are needed |
| `@WithUserDetails` | Object from `UserDetailsService` | Real principal is needed and the user exists in a data source/bean |
| **`@WithSecurityContext`** | **Determined by your factory** | Custom principal, flexible authority sets, or custom `Authentication` needed |

**Goal:** write a `@WithMockTenantUser` annotation so each test can declare `username`, `tenantId`, `authorities`, and `roles`; and accurately verify access control on a Spring bean.

## 2. How it works and its components

Flow of setting up and using security data:

```text
@Test + @WithMockTenantUser(...)
           |
           v
WithSecurityContextTestExecutionListener
           |
           v
WithMockTenantUserSecurityContextFactory
  1. create TenantPrincipal(username, tenantId)
  2. create GrantedAuthority from authorities + roles
  3. create an authenticated Authentication for the test
  4. put Authentication into a new SecurityContext
           |
           v
SecurityContextHolder (test thread)
           |
           v
Spring-managed DocumentService proxy
           |
           v
@PreAuthorize checks authorities + tenant
           |
           +-- condition met --> execute method
           |
           +-- condition failed --> AccessDeniedException
```

Distinguishing the data types:

- `SecurityContext` stores the current `Authentication`; `SecurityContextHolder` is the context access point according to the storage strategy (bound to the thread by default).
- `Authentication.getPrincipal()` represents the user. It may be a `UserDetails`, a `Principal`, a custom object, or another principal type depending on the authentication mechanism.
- `Authentication.getAuthorities()` returns the collection of `GrantedAuthority`; Spring Security compares authority strings when evaluating `hasAuthority` and `hasRole`.
- `hasAuthority('document:read')` requires the exact `document:read` authority.
- Under default conventions, `hasRole('APPROVER')` requires the `ROLE_APPROVER` authority, not `APPROVER`.
- `@WithSecurityContext` belongs to **Spring Security Test**, used to create test fixtures; it is not an annotation that protects production methods. Access rules reside in `@PreAuthorize` (or another authorization mechanism) on the bean.

The factory **returns a new `SecurityContext`**. The test execution listener places that context into the test execution and cleans it up afterward. You do not need to call `SecurityContextHolder.setContext(...)` directly in each test.

## 3. Complete example: principal with tenant and per-test authorities

This example uses **Java 17, Spring Boot 3.5.7, Spring Security 6.5.x, Maven, JUnit Jupiter**. The application has no HTTP endpoints; tests call the Spring-managed service directly so calls traverse the method security proxy.

Project structure:

```text
custom-security-context-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/securitydemo/
    │   ├── SecurityDemoApplication.java
    │   ├── TenantPrincipal.java
    │   └── DocumentService.java
    └── test/java/com/example/securitydemo/
        ├── WithMockTenantUser.java
        ├── WithMockTenantUserSecurityContextFactory.java
        └── DocumentServiceSecurityTest.java
```

### 3.1. Maven dependencies

File `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>custom-security-context-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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

`spring-security-test` brings in `@WithSecurityContext`, `WithSecurityContextFactory`, `@WithAnonymousUser`, and the test listeners. Adding only the production Spring Security dependency is not enough to use these test annotations.

### 3.2. Enable method security in the application

File `src/main/java/com/example/securitydemo/SecurityDemoApplication.java`:

```java
package com.example.securitydemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class SecurityDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityDemoApplication.class, args);
    }
}
```

`@EnableMethodSecurity` registers the interceptor that handles `@PreAuthorize`. Without this annotation under default configuration, service calls may execute without authorization checks, invalidating the test's purpose.

### 3.3. Define the application principal

File `src/main/java/com/example/securitydemo/TenantPrincipal.java`:

```java
package com.example.securitydemo;

import java.security.Principal;
import java.util.Objects;

public final class TenantPrincipal implements Principal {

    private final String username;
    private final String tenantId;

    public TenantPrincipal(String username, String tenantId) {
        this.username = Objects.requireNonNull(username, "username");
        this.tenantId = Objects.requireNonNull(tenantId, "tenantId");
    }

    @Override
    public String getName() {
        return username;
    }

    public String getUsername() {
        return username;
    }

    public String getTenantId() {
        return tenantId;
    }
}
```

This is an immutable POJO that also implements `java.security.Principal`. Because it has `getName()`, the sample token's `Authentication.getName()` can return the username directly. Because it has `getTenantId()`, Spring Expression Language (SpEL) can access the `principal.tenantId` property in security conditions.

In production, a principal may implement `UserDetails` or be another type. Implementing `UserDetails` is **not mandatory** to use `@WithSecurityContext`: the factory can build an `Authentication` with any suitable principal.

### 3.4. Service protected by authority and tenant

File `src/main/java/com/example/securitydemo/DocumentService.java`:

```java
package com.example.securitydemo;

import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    @PreAuthorize(
        "hasAuthority('document:read') and principal.tenantId == #tenantId"
    )
    public String readDocument(@P("tenantId") String tenantId) {
        return "document:" + tenantId;
    }

    @PreAuthorize(
        "hasRole('APPROVER') and principal.tenantId == #tenantId"
    )
    public String approveDocument(@P("tenantId") String tenantId) {
        return "approved:" + tenantId;
    }
}
```

Both conditions in each `@PreAuthorize` must hold simultaneously:

1. Hold the corresponding authority (`document:read` or `ROLE_APPROVER`).
2. `tenantId` on the principal equals the method's `tenantId` parameter.

`@P("tenantId")` (correct import: `org.springframework.security.access.method.P`) exposes the parameter name to method-security SpEL, even without relying on the compiler's `-parameters` metadata. `#tenantId` references the call argument; `principal.tenantId` references the property on the authenticated principal.

**Important:** the `tenantId` value sent by the caller is only a business argument. Authorization compares it against the trusted tenant in `Authentication` before allowing execution. In a real system, you still need tenant/ownership checks in data queries to prevent data leaks through other access paths.

### 3.5. Create a custom annotation for test fixtures

File `src/test/java/com/example/securitydemo/WithMockTenantUser.java`:

```java
package com.example.securitydemo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.security.test.context.support.WithSecurityContext;

@Target({ElementType.METHOD, ElementType.TYPE})
@Retention(RetentionPolicy.RUNTIME)
@Inherited
@WithSecurityContext(factory = WithMockTenantUserSecurityContextFactory.class)
public @interface WithMockTenantUser {

    String username() default "demo";

    String tenantId() default "tenant-a";

    String[] authorities() default {};

    String[] roles() default {};
}
```

Explanation of each part:

- `@Target({METHOD, TYPE})` allows using the annotation on **a single test method** or **an entire test class**.
- `@Retention(RUNTIME)` preserves metadata so the test listener can read it at runtime.
- `@Inherited` lets a class-level annotation be inherited when subclassing a test class.
- `@WithSecurityContext(factory = ...)` links the annotation to the context-building code.
- `username` and `tenantId` configure the principal; `authorities` and `roles` configure the authority set. Each test can specify the fields it needs; the remaining fields take their default values.

This annotation lives under `src/test/java` because it is only for testing. Declaring a test annotation **does not replace** the authorization annotations on the service.

### 3.6. Factory creating principal, authorities, and SecurityContext

File `src/test/java/com/example/securitydemo/WithMockTenantUserSecurityContextFactory.java`:

```java
package com.example.securitydemo;

import java.util.ArrayList;
import java.util.List;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithSecurityContextFactory;

public final class WithMockTenantUserSecurityContextFactory
        implements WithSecurityContextFactory<WithMockTenantUser> {

    @Override
    public SecurityContext createSecurityContext(WithMockTenantUser user) {
        TenantPrincipal principal =
                new TenantPrincipal(user.username(), user.tenantId());

        List<GrantedAuthority> permissions = new ArrayList<>();

        for (String authority : user.authorities()) {
            permissions.add(new SimpleGrantedAuthority(authority));
        }

        for (String role : user.roles()) {
            permissions.add(new SimpleGrantedAuthority("ROLE_" + role));
        }

        Authentication authentication =
                UsernamePasswordAuthenticationToken.authenticated(
                        principal, "N/A", permissions);

        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authentication);
        return context;
    }
}
```

Purpose of each step:

1. Build `TenantPrincipal` with the annotation data of **the current test**.
2. Convert each `authorities` string into a `SimpleGrantedAuthority`, keeping the exact name.
3. Convert each `roles` element into an authority prefixed with `ROLE_` per default convention. For example, `roles = {"APPROVER"}` produces `ROLE_APPROVER`.
4. Build `UsernamePasswordAuthenticationToken.authenticated(...)` to get an authenticated `Authentication` object for the test; the `"N/A"` credential is just a placeholder and is not used for login.
5. Create a fresh `SecurityContext` and return it to the listener. Never reuse a static context across tests.

If you pass `authorities = {"APPROVER"}`, the factory creates the `APPROVER` authority, so `hasRole('APPROVER')` will **not** match. To match, use `roles = {"APPROVER"}` or `authorities = {"ROLE_APPROVER"}`. Do not pass a string already prefixed with `ROLE_` into `roles`, or it will become `ROLE_ROLE_APPROVER`.

### 3.7. Testing principal, authority sets, allowed and denied conditions

File `src/test/java/com/example/securitydemo/DocumentServiceSecurityTest.java`:

```java
package com.example.securitydemo;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithAnonymousUser;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest(classes = SecurityDemoApplication.class)
@WithMockTenantUser(
    username = "lan",
    tenantId = "tenant-a",
    authorities = {"document:read"}
)
class DocumentServiceSecurityTest {

    @Autowired
    private DocumentService documentService;

    @Test
    void springInjectsProxiedService() {
        assertThat(AopUtils.isAopProxy(documentService)).isTrue();
    }

    @Test
    void customPrincipalAndAuthoritiesArePresent() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        assertThat(authentication.isAuthenticated()).isTrue();
        assertThat(authentication.getName()).isEqualTo("lan");
        assertThat(authentication.getPrincipal())
                .isInstanceOf(TenantPrincipal.class);

        TenantPrincipal principal =
                (TenantPrincipal) authentication.getPrincipal();
        assertThat(principal.getTenantId()).isEqualTo("tenant-a");

        assertThat(authentication.getAuthorities())
                .extracting(GrantedAuthority::getAuthority)
                .containsExactly("document:read");
    }

    @Test
    void readerCanReadDocumentInOwnTenant() {
        assertThat(documentService.readDocument("tenant-a"))
                .isEqualTo("document:tenant-a");
    }

    @Test
    @WithMockTenantUser(
        tenantId = "tenant-a",
        authorities = {"document:write"}
    )
    void userWithoutReadAuthorityIsDenied() {
        assertThatThrownBy(() -> documentService.readDocument("tenant-a"))
                .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    @WithMockTenantUser(
        tenantId = "tenant-b",
        authorities = {"document:read"}
    )
    void readerFromDifferentTenantIsDenied() {
        assertThatThrownBy(() -> documentService.readDocument("tenant-a"))
                .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    @WithMockTenantUser(
        tenantId = "tenant-a",
        roles = {"APPROVER"}
    )
    void approverCanApproveOwnTenantDocument() {
        assertThat(documentService.approveDocument("tenant-a"))
                .isEqualTo("approved:tenant-a");
    }

    @Test
    @WithMockTenantUser(
        tenantId = "tenant-a",
        authorities = {"APPROVER"}
    )
    void authorityWithoutRolePrefixDoesNotMatchHasRole() {
        assertThatThrownBy(() -> documentService.approveDocument("tenant-a"))
                .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    @WithAnonymousUser
    void anonymousCannotReadDocument() {
        assertThatThrownBy(() -> documentService.readDocument("tenant-a"))
                .isInstanceOf(AccessDeniedException.class);
    }
}
```

There are **8 tests**:

1. **Proxy:** verifies that `DocumentService` obtained from Spring is an AOP proxy. This check is useful, though by itself it does not prove authorization works.
2. **Principal + authorities:** verifies that the factory actually places `TenantPrincipal("lan", "tenant-a")` and authority `document:read` into the context; also checks `Authentication.getName()`.
3. **Allow right tenant:** both authority and tenant match, service returns `document:tenant-a`.
4. **Missing authority:** same tenant but only `document:write`, access is denied.
5. **Wrong tenant:** has `document:read` but principal belongs to another tenant, access is denied.
6. **Right role:** `roles = {"APPROVER"}` is converted into `ROLE_APPROVER`, approval succeeds.
7. **Wrong authority format:** authority `APPROVER` does not satisfy `hasRole('APPROVER')`.
8. **Anonymous:** `@WithAnonymousUser` sets the anonymous state instead of the class-level annotation; access is denied.

The annotation on the test class applies by default to tests that do not declare their own authentication. **A method-level annotation replaces** the class-level authentication configuration for that method; attributes not passed on the method annotation use the annotation's own defaults rather than automatically merging authorities with the class configuration.

Denied cases use `assertThatThrownBy(...).isInstanceOf(AccessDeniedException.class)` to verify that the security annotation actually blocks the call. Depending on the version, the concrete exception may be a subclass of `AccessDeniedException`.

### 3.8. Run and compare results

From the directory containing `pom.xml`, using JDK 17+ and Maven:

```bash
java -version
mvn test
```

The test suite is expected to pass with a summary equivalent to:

```text
Tests run: 8, Failures: 0, Errors: 0, Skipped: 0
```

This is the **expected outcome**, not the log of an executed run. Maven may print many Spring context startup lines, but what matters is the total test count and the assertions.

A very useful sensitivity check: temporarily remove `@EnableMethodSecurity` in a local experiment and re-run. The tests `userWithoutReadAuthorityIsDenied`, `readerFromDifferentTenantIsDenied`, `authorityWithoutRolePrefixDoesNotMatchHasRole`, and `anonymousCannotReadDocument` must no longer observe denial; the proxy test may also fail. After the check, restore the configuration. If the suite stays completely green with security disabled, you are likely calling a mock/target object by mistake or missing denial assertions.

## 4. Controlling the security context lifecycle

### 4.1. When does the listener set up the context?

With Spring Test integration, `WithSecurityContextTestExecutionListener` handles `@WithSecurityContext` and its meta-annotations. By default, the context is set up in the `beforeTestMethod` event, i.e., **before JUnit Jupiter's `@BeforeEach`**. You can choose `TestExecutionEvent.TEST_EXECUTION` to set up the context after `@BeforeEach` and before the `@Test` method itself.

**Standalone illustrative** example, not a replacement for the annotation in the full project:

```java
// Place on the custom annotation declaration if you truly need to change setup timing.
@WithSecurityContext(
    factory = WithMockTenantUserSecurityContextFactory.class,
    setupBefore = TestExecutionEvent.TEST_EXECUTION
)
```

With this option, do not expect the custom principal to already be present when `@BeforeEach` runs. The right enum import is `org.springframework.security.test.context.support.TestExecutionEvent`.

Tests need isolation: every factory invocation should return a new context, without using a `static SecurityContext` that could leak principals between tests. When using standard Spring Test listeners, you do not have to write `@AfterEach` just to clear the security context.

### 4.2. The test context does not automatically authenticate HTTP requests

`@WithSecurityContext` configures the context for the **test execution thread**. When running a real HTTP server on another thread (for example `@SpringBootTest(webEnvironment = RANDOM_PORT)` and sending HTTP requests), the server does not automatically inherit the principal from the test thread. For HTTP testing, attach authentication info to the request (MockMvc `with(user(...))`, bearer token, HTTP Basic, etc.) suited to the test goal.

This lesson tests **method security directly** through a Spring-managed service. It does not replace testing token validation, filter chains, or endpoint-level access rules.

## 5. Factory design variations

### 5.1. `UserDetails`-style principal

If the application has `CustomUserDetails`, the factory can construct or retrieve that object and put it into `Authentication`, provided the type and authorities match what the method-security expression reads. When you want to use real data from `UserDetailsService`, `@WithUserDetails` is usually simpler. Choose `@WithSecurityContext` when you need extra fields or authentication semantics that built-in test annotations cannot express.

### 5.2. Need a real JWT/`OAuth2AuthenticationToken` in unit/integration tests?

You can construct a different `Authentication` type in the factory instead of `UsernamePasswordAuthenticationToken`, but you must understand the token type production code actually inspects. If a production expression uses `authentication.tokenAttributes` or checks the `JwtAuthenticationToken` type, a factory creating a username-password token is **not equivalent**. Build the matching token and check claims, authorities, and principal as needed; if the test goes through HTTP filters, use dedicated HTTP testing tools or send authenticated requests.

### 5.3. Does the factory need a Spring bean?

`WithSecurityContextFactory` supports Spring Test dependency injection. You can use `@Autowired` to inject a builder or principal-creation service into the factory when complex fixture construction logic is needed. However, prefer small fixtures with clear data; avoid making tests call databases or external systems just to construct a simple principal.

## 6. Common errors and troubleshooting

| Symptom | Common cause | How to check |
| --- | --- | --- |
| Test ignores the custom annotation | Missing `@Retention(RUNTIME)`, missing `@WithSecurityContext`, or missing `spring-security-test` dependency | Check annotation + factory and Spring Test integration |
| `Authentication.getPrincipal()` has wrong type | Factory still creates default `User` or service expects a different type | Assert `instanceof TenantPrincipal` right in the test |
| `principal.tenantId` cannot be read | Principal lacks a matching getter property | Provide `getTenantId()` or access the actual principal structure |
| `#tenantId` fails to resolve | Java parameter names not preserved or alias not declared | Use `@P("tenantId")` with the right import, or compile with `-parameters` |
| `hasRole('APPROVER')` always denies | Granted `APPROVER` instead of `ROLE_APPROVER` | Use `roles = {"APPROVER"}` in the custom annotation |
| Authorities accumulate unexpectedly | Misunderstanding that method annotation inherits all authorities from class annotation | Inspect each fixture; the factory creates authorities from the test's effective annotation |
| Every call succeeds | `@EnableMethodSecurity` not enabled, object called via `new` or mock, or self-invocation bypasses proxy | Inject Spring bean; assert denied and check proxy |
| `@BeforeEach` does not see principal yet | Set `setupBefore = TEST_EXECUTION` | Use default or move assertion into `@Test` |
| HTTP test against real server is always anonymous | Test thread's security context does not transfer to HTTP thread | Supply credentials/token on the request and test filter chain separately |
| Tests flake when run in parallel | Factory shares mutable context or static state | Always create a new `SecurityContext` and avoid shared state |

In particular, **do not use `@MockBean`/`@MockitoBean` to replace `DocumentService` itself** and treat a mock call as proof that the security annotation works. Plain Mockito helps test logic, while authorization tests require method invocations to pass through an object Spring Security can intercept.

With Spring AOP proxies, internal calls like `this.securedMethod()` normally do not traverse the proxy and can skip method-security advice on the target method. Tests through the injected bean must cover the exact call path production uses.

## 7. Criteria for a reliable test suite

A quality `@WithSecurityContext` test suite should ensure:

1. **Right identity:** the principal has the right type, username, and attributes used by the policy.
2. **Right privileges:** `GrantedAuthority` instances in `Authentication` match the exact semantics of `hasAuthority`/`hasRole`; include role prefix tests if relevant.
3. **Right boundary:** run tests with a Spring context containing `@EnableMethodSecurity` and call the bean through its Spring proxy.
4. **Positive + negative tests:** simultaneously test sufficient privileges, missing privileges, mismatched business attributes, and anonymous when applicable.
5. **Order independence:** do not store static `Authentication` or `SecurityContext`; keep each test's fixture data easy to read.
6. **Catches broken authorization:** disabling the policy in a control check must cause at least one negative test to fail.

Advanced exercise example: add `departmentId` to `TenantPrincipal` and the annotation, then add the condition `principal.departmentId == #departmentId` on another method. Write three independent tests: matching tenant/department/authority; wrong department despite matching tenant; sufficient organizational info but missing authority. If all three verify correctly, you have effectively used `@WithSecurityContext` to model a principal and authority set aligned with your application's specific policy.

## References

- [Spring Security — Testing Method Security: `@WithSecurityContext`](https://docs.spring.io/spring-security/reference/servlet/test/method.html): creating custom annotations, `WithSecurityContextFactory`, and test context lifecycle.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@PreAuthorize`, roles/authorities, principal, and method parameters.
- [Spring Framework — AOP Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): proxy limitations and self-invocation.
