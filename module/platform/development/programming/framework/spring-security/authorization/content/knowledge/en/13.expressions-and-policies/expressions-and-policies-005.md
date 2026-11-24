# DefaultMethodSecurityExpressionHandler and Customization Points in Spring Security

## 1. Why understand this class?

When a service uses `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, or `@PostFilter`, Spring Security needs to understand expressions such as:

```java
@PreAuthorize("hasRole('ADMIN') or @documentAccess.canRead(authentication, #p0)")
public Document findById(long id) { /* ... */ }
```

`DefaultMethodSecurityExpressionHandler` is the **default implementation of `MethodSecurityExpressionHandler`** that parses Spring Expression Language (SpEL) expressions, creates an evaluation environment for **method invocations**, supplies the root containing security checks, and supports filtering inputs/outputs.

You can think of it as the **context bridge from a method invocation to a context that authorization expressions can understand**: who is calling, which method, which arguments, what result, and which beans can be invoked to decide. It **does not authenticate passwords itself**, does not own application permission data, is not an endpoint filter, and does not replace the `AuthorizationManager` that makes the allow/deny decision inside the interceptor.

Goals after this lesson:

1. Trace the path from a method-security annotation to `EvaluationContext` and the authorization outcome.
2. Recognize the root variables and functions of expressions: `authentication`, `principal`, `hasRole`, `hasAuthority`, `hasPermission`, `#p0`, `returnObject`, `filterObject`.
3. Pick the right extension level: **bean called from SpEL → `PermissionEvaluator`/`RoleHierarchy` → configure the handler → custom `AuthorizationManager`**, instead of immediately subclassing the handler.
4. Avoid pitfalls involving proxies, late-initialized beans, expressions checking the wrong parameter, and differences between Spring Security 6 and 7.

This lesson covers **method authorization**, primarily in standard Servlet/Spring Boot applications; configurations for HTTP requests, WebSocket messages, or reactive method security differ.

## 2. Position in the execution architecture

Example of a client call entering a Spring-managed `DocumentService` bean:

```text
Caller
  |
  v
Spring AOP proxy of DocumentService
  |
  v
AuthorizationManagerBeforeMethodInterceptor (@PreAuthorize)
  |
  v
PreAuthorizeAuthorizationManager
  |
  v
MethodSecurityExpressionHandler
  |-- SpEL ExpressionParser: parses "hasRole(...) and ..."
  |-- MethodInvocation: method, target, arguments
  |-- Supplier<Authentication>: retrieves current user when needed
  |-- MethodSecurityEvaluationContext:
  |      root + params #p0/#p1/param names + bean resolver
  v
Evaluate expression into authorization decision
  |                     |
  | allowed             | denied
  v                     v
Method body             AccessDeniedException
```

After the method returns, `@PostAuthorize` advice can evaluate conditions depending on `returnObject`. With `@PreFilter` and `@PostFilter`, the handler supports evaluating expressions per element via `filterObject`. Different advice runs at different points; **never treat post-method filtering as a rollback mechanism for write operations**.

Types and responsibilities:

| Component | Primary responsibility | Example |
| --- | --- | --- |
| `@EnableMethodSecurity` | Enables method-security infrastructure | Placed on `@Configuration` |
| `AuthorizationManagerBeforeMethodInterceptor` | Intercepts calls before execution | Advice for `@PreAuthorize` |
| `PreAuthorizeAuthorizationManager` | Retrieves and evaluates policy before invocation | Uses handler to process SpEL |
| `DefaultMethodSecurityExpressionHandler` | Creates evaluation context and supports evaluation/filtering | Sets role hierarchy, permission evaluator |
| `MethodSecurityEvaluationContext` | Places root and method arguments into context | `#p0`, parameter names |
| `MethodSecurityExpressionOperations` | Interface for method root operations and properties | `hasRole`, `authentication`, `filterObject` |
| `PermissionEvaluator` | Hooks object-level permission rules into `hasPermission(...)` | Can-read by ID and tenant |
| Custom `AuthorizationManager` | Decides permissions in Java when SpEL is unsuitable | Multi-condition rules, reasoned results |

`DefaultMethodSecurityExpressionHandler` resides in package:

```java
org.springframework.security.access.expression.method
    .DefaultMethodSecurityExpressionHandler
```

This handler extends `AbstractSecurityExpressionHandler<MethodInvocation>` and implements `MethodSecurityExpressionHandler`. Do not confuse it with `DefaultWebSecurityExpressionHandler` for the legacy web expression model or `DefaultMessageSecurityExpressionHandler` for messaging.

### What does the handler know during evaluation?

Example expression:

```java
@PreAuthorize("hasAuthority('DOC_READ') and "
            + "@documentAccess.canRead(authentication, #p0)")
public Document read(long id) { /* ... */ }
```

In a call to `read(42L)`, the expression context contains:

- `authentication`: the `Authentication` object tied to the invocation; `authentication.name` is typically the principal name.
- `principal`: the principal inside `Authentication`; its concrete type may be `UserDetails`, `Jwt`, a String, or a custom type.
- `#p0`/`#a0`: the first parameter (here `42L`); `#p1`/`#a1`: the second parameter.
- `#id`: usable if parameter names are resolved by Spring, e.g., via `-parameters` or `@P("id")`. Do not assume every build compiles with parameter names preserved.
- `@documentAccess`: a bean named `documentAccess` in the Spring application context, callable from the expression.
- Security root: operations such as `hasAuthority`, `hasRole`, `isAuthenticated`, `permitAll`, `denyAll`, `hasPermission`, etc.

Keep policies readable: `hasAuthority('DOC_READ') and @documentAccess.canRead(authentication, #p0)`. As business rules grow more complex, move logic into a Java class instead of stuffing dozens of conditions into an annotation string.

## 3. Defaults to master

### 3.1. Roles, authorities, and prefixes

- `hasAuthority('DOC_READ')` requires an authority with that exact name, without prepending `ROLE_`.
- `hasRole('ADMIN')` typically checks authority `ROLE_ADMIN` due to the default `ROLE_` prefix.
- `RoleHierarchy` can make higher roles imply lower ones: e.g., `ROLE_ADMIN > ROLE_READER`.
- Merely changing an expression to `hasRole('ADMIN')` does not make Spring grant `ROLE_ADMIN` to anyone; actual authorities must still exist in `Authentication` or be implied by a configured hierarchy.

### 3.2. Object permissions with `hasPermission`

Two common forms:

```java
@PreAuthorize("hasPermission(#p0, 'read')")
public Document view(Document document) { /* ... */ }

@PreAuthorize("hasPermission(#p0, 'Document', 'read')")
public Document viewById(long id) { /* ... */ }
```

The first form passes a domain object to `PermissionEvaluator.hasPermission(Authentication, Object, Object)`. The second passes the ID, object type name, and action to the overload `hasPermission(Authentication, Serializable, String, Object)`. The types, order, and semantics of these arguments form **the application contract** of your evaluator; Spring does not automatically know what "Document/read" means.

If the application does not supply an appropriate evaluator, `hasPermission` will not automatically check databases/ACLs as expected. Do not assume declaring the annotation alone implements ownership-based authorization.

### 3.3. Post-invocation and element variables

```java
@PostAuthorize("returnObject == null or returnObject.owner == authentication.name")
public Document fetch(long id) { /* ... */ }

@PostFilter("filterObject.publicVisible or filterObject.owner == authentication.name")
public List<Document> list() { /* ... */ }
```

- `returnObject` is the method's return value inside `@PostAuthorize`.
- `filterObject` is each element being evaluated in `@PreFilter`/`@PostFilter`.
- `@PostAuthorize` may deny after the method body has already executed. Never use a post-invocation check to guard write operations with side effects.
- Using `@PostFilter` on very large datasets can waste substantial memory and work; consider filtering in the database query by tenant/permissions.

### 3.4. `Supplier<Authentication>` and lazy lookup

Modern method security uses `Supplier<Authentication>` when constructing the context so fetching authentication can be deferred. An expression like `permitAll` may never need to read `Authentication`. Writing a custom handler that calls `authentication.get()` prematurely can lose this benefit or alter check timing.

This is also why several older subclassing approaches no longer work as expected, as explained in Section 9.

## 4. At what level should you customize?

| Need | Appropriate extension point | Why |
| --- | --- | --- |
| Check owner, tenant, resource state, custom business rules | `@policyName` bean in SpEL | Easy to unit-test in Java; no root replacement needed |
| Use `hasPermission` API on domain objects/IDs | Set `PermissionEvaluator` on handler | Centralizes object permission semantics |
| Let one role imply another | `RoleHierarchy` via version-appropriate handler/factory | Keeps role expressions simple |
| Change the `hasRole` prefix | `GrantedAuthorityDefaults` or corresponding factory config | Avoids mistyping `ROLE_` across files |
| Change parameter name discovery | `setParameterNameDiscoverer(...)`, `@P`, or `#p0` | Stabilizes parameter access |
| Change SpEL parsing | `setExpressionParser(...)` (very rare) | Affects all expressions using the handler |
| Need a new SpEL root function unsuitable for a bean | Customize evaluation context/root with tests | Deep intervention; easily version-dependent |
| Complex policy or prefer avoiding SpEL | `AuthorizationManager` and appropriate advisor | Pure Java decision, independently testable |

**Pragmatic order:** try a policy bean called via `@bean.method(...)` first. Adjust the handler only when modifying a shared capability of the expression engine itself. One handler is normally shared across expression-based advisors; do not create a separate handler per service or per method.

## 5. Simplest approach: use a policy bean in SpEL

Suppose documents have `tenantId` and `ownerId` stored in a database, and the application only allows users with read permission in the matching tenant to access them. The policy should live in a Java bean that takes the identity and ID and checks server-side data.

```java
@Component("documentAccess")
public class DocumentAccess {

    private final DocumentRepository repository;

    public DocumentAccess(DocumentRepository repository) {
        this.repository = repository;
    }

    public boolean canRead(Authentication auth, long documentId) {
        if (auth == null || !auth.isAuthenticated()) {
            return false;
        }

        return repository.findById(documentId)
                .filter(doc -> tenantMatches(auth, doc.tenantId()))
                .filter(doc -> ownerOrShared(auth, doc))
                .isPresent();
    }

    // tenantMatches, ownerOrShared are project-specific business rules.
}
```

This is an **integration snippet**, not a standalone runnable file: `DocumentRepository`, `tenantMatches`, and `ownerOrShared` are implemented by the application, and anonymous authentication must be handled according to your policy. Avoid trusting a client-supplied `tenantId` without verifying against trusted claims/identity.

Usage in the service:

```java
@Service
public class DocumentService {

    @PreAuthorize("hasAuthority('DOC_READ') and "
                + "@documentAccess.canRead(authentication, #p0)")
    public Document read(long id) {
        // Runs only when both conditions allow it.
        return loadDocument(id);
    }
}
```

`loadDocument` is an application method omitted to focus on the policy. `@documentAccess` is SpEL syntax calling a Spring-managed bean; you do not need to subclass `DefaultMethodSecurityExpressionHandler` just to expose a `canRead` function.

If you want to decouple the expression from user details entirely, the bean can also accept `#root` (type `MethodSecurityExpressionOperations`) and invoke `root.hasAuthority(...)`. This works well when reusing standard checks within the same policy.

**Benefits:** the policy is typed Java code, easy to mock repositories for, and allows testing deny branches; annotations stay concise at the call boundary. **Limits:** policy queries can add round-trips and face race conditions if permissions/state change before a write; for sensitive mutations, verify consistency in the same transaction or use appropriate locking/versioning.

## 6. Configuring a shared `DefaultMethodSecurityExpressionHandler`

When you must set a default role hierarchy or evaluator for expressions, declare a `MethodSecurityExpressionHandler` bean. Ensure the bean exists **before Spring builds the method security configuration**; Spring Security documentation uses `@Bean static` to satisfy that initialization order.

```java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {

    @Bean
    static RoleHierarchy roleHierarchy() {
        return RoleHierarchyImpl.fromHierarchy(
                "ROLE_ADMIN > ROLE_READER");
    }

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            RoleHierarchy roleHierarchy) {
        DefaultMethodSecurityExpressionHandler handler =
                new DefaultMethodSecurityExpressionHandler();
        handler.setRoleHierarchy(roleHierarchy);
        return handler;
    }
}
```

Main imports for the integration snippet:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.access.hierarchicalroles.RoleHierarchyImpl;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
```

Then, in an appropriate configuration, a user with authority `ROLE_ADMIN` is treated as having role `READER` when evaluating:

```java
@PreAuthorize("hasRole('READER')")
public String readReport(long id) {
    return "report-" + id;
}
```

**Compatibility note:** `setRoleHierarchy(...)` exists and is widely used in Spring Security 6.x. In Spring Security **7.0+**, this setter is marked deprecated in favor of `setAuthorizationManagerFactory(AuthorizationManagerFactory)` or the corresponding factory configuration mechanism; do not copy 6.x configurations while ignoring warnings when upgrading. `setDefaultRolePrefix(...)` and `setTrustResolver(...)` are also deprecated as of 7.0. The hands-on example below pins Spring Boot 3.5.15 (Spring Security 6.x line) for consistent API and behavior.

To change the role prefix application-wide, Spring Security also provides:

```java
@Bean
static GrantedAuthorityDefaults grantedAuthorityDefaults() {
    return new GrantedAuthorityDefaults("APP_");
}
```

With that configuration, `hasRole('READER')` generally checks `APP_READER` instead of `ROLE_READER` across components supporting this setting. Test across web rules, methods, `@Secured`/JSR-250, and your specific hierarchy setup; **do not assume every annotation style uses the same expression handler**. Do not manually prepend the prefix twice.

## 7. Adding `PermissionEvaluator`: connecting to domain permissions

`PermissionEvaluator` has two overloads; implement **both** completely, even if one overload is unsupported, and **deny by default** whenever the object type or action is unrecognized.

Integration illustration:

```java
import java.io.Serializable;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.core.Authentication;

public final class DocumentPermissionEvaluator implements PermissionEvaluator {

    private final DocumentAuthorizationRepository repository;

    public DocumentPermissionEvaluator(
            DocumentAuthorizationRepository repository) {
        this.repository = repository;
    }

    @Override
    public boolean hasPermission(Authentication auth,
                                 Object target,
                                 Object permission) {
        if (!(target instanceof Document document)) {
            return false;
        }
        return canRead(auth, document.id(), permission);
    }

    @Override
    public boolean hasPermission(Authentication auth,
                                 Serializable targetId,
                                 String targetType,
                                 Object permission) {
        if (!"Document".equals(targetType)
                || !(targetId instanceof Long id)) {
            return false;
        }
        return canRead(auth, id, permission);
    }

    private boolean canRead(Authentication auth, long id, Object action) {
        return auth != null
                && "read".equals(action)
                && repository.isReader(auth.getName(), id);
    }
}
```

`Document` and `DocumentAuthorizationRepository` are project-provided types; this is an integration snippet, not a standalone program. `isReader` must check permissions using server/tenant data; the example focuses on the two overloads and default-deny behavior.

Register the evaluator and configure **the same handler**:

```java
@Bean
static PermissionEvaluator documentPermissionEvaluator(
        DocumentAuthorizationRepository repository) {
    return new DocumentPermissionEvaluator(repository);
}

@Bean
static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
        RoleHierarchy hierarchy, PermissionEvaluator evaluator) {
    DefaultMethodSecurityExpressionHandler handler =
            new DefaultMethodSecurityExpressionHandler();
    handler.setRoleHierarchy(hierarchy);
    handler.setPermissionEvaluator(evaluator);
    return handler;
}
```

This **replaces** the `methodSecurityExpressionHandler` bean from Section 6; do not add it as a second bean. Use with:

```java
@PreAuthorize("hasPermission(#p0, 'Document', 'read')")
public Document read(long documentId) { /* ... */ }
```

Key trade-offs:

- `hasPermission` gives a uniform vocabulary across multiple domain objects; a `@documentAccess` bean is often easier to read for straightforward business policies.
- If the evaluator queries a repository, watch query counts: per-element filtering can trigger N+1 queries; consider batched queries or filtering at the DB.
- Never cache authorization decisions indefinitely; tenants, ownership, and revocations can change.
- Never return `true` for an unimplemented overload; never trust permission or tenant attributes sent from the client.

## 8. Runnable Java 17 example: seeing the handler's role clearly

The small example below runs on **Spring Boot 3.5.15** with Java 17. It demonstrates simultaneously:

1. A handler declared via `@Bean static`.
2. `ROLE_ADMIN` implying `ROLE_READER` via the hierarchy.
3. A `@reportGate` policy bean checking an ID-based rule.
4. `@PreAuthorize` actually blocking calls via proxy; the program swaps `SecurityContext` to observe outcomes.

Structure:

```text
method-security-demo/
  pom.xml
  src/main/java/demo/
    MethodSecurityDemo.java
    ReportGate.java
    ReportService.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
          https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.15</version>
    <relativePath/>
  </parent>
  <groupId>demo</groupId>
  <artifactId>method-security-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-security</artifactId>
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

File `src/main/java/demo/MethodSecurityDemo.java`:

```java
package demo;

import java.util.List;
import java.util.Map;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.access.hierarchicalroles.RoleHierarchyImpl;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

@SpringBootApplication
@EnableMethodSecurity
public class MethodSecurityDemo {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(MethodSecurityDemo.class);
        app.setDefaultProperties(Map.of(
                "spring.main.web-application-type", "none",
                "spring.main.banner-mode", "off",
                "logging.level.root", "OFF"
        ));
        try (ConfigurableApplicationContext ignored = app.run(args)) {
            // CommandLineRunner already ran before SpringApplication.run returned.
        }
    }

    @Bean
    static RoleHierarchy roleHierarchy() {
        return RoleHierarchyImpl.fromHierarchy(
                "ROLE_ADMIN > ROLE_READER");
    }

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            RoleHierarchy roleHierarchy) {
        DefaultMethodSecurityExpressionHandler handler =
                new DefaultMethodSecurityExpressionHandler();
        handler.setRoleHierarchy(roleHierarchy);
        return handler;
    }

    @Bean
    CommandLineRunner demo(ReportService reportService) {
        return args -> {
            attempt(reportService, "alice", "ROLE_ADMIN", 42L);
            attempt(reportService, "alice", "ROLE_ADMIN", 7L);
            attempt(reportService, "bob", "ROLE_READER", 42L);
        };
    }

    private static void attempt(ReportService service, String username,
                                String role, long reportId) {
        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(
                UsernamePasswordAuthenticationToken.authenticated(
                        username,
                        "ignored",
                        List.of(new SimpleGrantedAuthority(role))));
        SecurityContextHolder.setContext(context);

        try {
            String value = service.readReport(reportId);
            System.out.println(username + "/" + reportId + ": " + value);
        } catch (AccessDeniedException denied) {
            System.out.println(username + "/" + reportId + ": DENIED");
        } finally {
            SecurityContextHolder.clearContext();
        }
    }
}
```

File `src/main/java/demo/ReportGate.java`:

```java
package demo;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("reportGate")
public class ReportGate {

    public boolean canRead(Authentication authentication, long reportId) {
        // Simulated data for this lesson: only alice may view report 42.
        return authentication != null
                && "alice".equals(authentication.getName())
                && reportId == 42L;
    }
}
```

File `src/main/java/demo/ReportService.java`:

```java
package demo;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @PreAuthorize("hasRole('READER') and "
                + "@reportGate.canRead(authentication, #p0)")
    public String readReport(long reportId) {
        return "report-" + reportId;
    }
}
```

Run in the directory containing `pom.xml` (requires JDK 17+ and Maven):

```bash
mvn -q clean package
java -jar target/method-security-demo-1.0.0.jar
```

Three lines of output printed by the app:

```text
alice/42: report-42
alice/7: DENIED
bob/42: DENIED
```

Explanation of each case:

- `alice/42`: `alice` has `ROLE_ADMIN`; the hierarchy makes `hasRole('READER')` pass; `reportGate.canRead` also passes → service executes.
- `alice/7`: role passes, yet the policy bean rejects ID `7` → service does not run.
- `bob/42`: `bob` has `ROLE_READER`, so the role check passes; the policy only allows `alice`, so it is still denied.
- Because `CommandLineRunner` invokes `ReportService` obtained from the Spring container, the method interceptor actually participates. If you instantiate `new ReportService()` manually and call it directly, the annotation will not run.

This is a command-line demo intentionally setting a mock `Authentication` for clarity, **not how users authenticate in production**. Real systems use configured security filters/authentication providers and permission policies backed by trusted data. `ReportGate` is deliberately hardcoded so the lesson yields deterministic output.

### Switching to a permission evaluator

If you prefer `hasPermission`, replace the expression with:

```java
@PreAuthorize("hasPermission(#p0, 'Report', 'read')")
public String readReport(long reportId) { /* ... */ }
```

Then attach an appropriate `PermissionEvaluator` to **the existing handler bean** via `setPermissionEvaluator(...)`. Do not change only the annotation while skipping evaluator registration; the outcome will differ from expectations.

## 9. When do you need to subclass the handler?

Some legacy systems subclass `DefaultMethodSecurityExpressionHandler` to add methods like `isTenantAdmin()` onto a custom root. This intervenes much deeper than a SpEL bean because you must ensure the new root preserves every check/variable of `MethodSecurityExpressionOperations`.

**Important upgrade trap:** with modern `@EnableMethodSecurity`, evaluation uses the overload `createEvaluationContext(Supplier<Authentication>, MethodInvocation)`. Overriding **only** `createSecurityExpressionRoot(Authentication, MethodInvocation)` may no longer be called as before. Spring Security documentation recommends using a policy bean whenever possible.

If you genuinely must build a custom root, the core idea is:

```text
createEvaluationContext(Supplier<Authentication>, MethodInvocation)
    -> call super.createEvaluationContext(...)
    -> get current root from StandardEvaluationContext
    -> create custom root/decorator preserving MethodSecurityExpressionOperations
    -> setRootObject(customRoot)
    -> return context
```

This is a **sketch**, not standalone runnable Java. Generic signatures and nullability vary by Spring Security version; verify the exact version's Javadoc before writing `@Override`. A custom root must preserve all standard behavior such as `hasRole`, `hasPermission`, `authentication`, `returnObject`, and `filterObject`; omitting any piece can break existing annotations when swapping handlers. Never replace the root merely to add a `canRead` helper that fits cleanly in a bean.

On the other hand, when you want policies computed entirely in Java, using an `AuthorizationManager<MethodInvocation>` wired through an appropriate method advisor avoids forcing complex logic into SpEL. The handler is not the only extension point in the authorization architecture.

## 10. How to verify configuration and test

Test through the **Spring bean proxy**, using `@SpringBootTest` and `spring-security-test`/`@WithMockUser` where appropriate. For Section 8's demo, each case maps to a specific check:

| Scenario | Expected | What bug does it catch? |
| --- | --- | --- |
| `alice` with only `ROLE_ADMIN` calls ID 42 | Allow | Handler/hierarchy is applied |
| `alice` calls ID 7 | Deny | Policy bean is invoked; resource permissions aren't bypassed |
| `bob` with `ROLE_READER` calls ID 42 | Deny | Owner/tenant check isn't replaced by a role check |
| No valid authentication | Deny on permission-requiring rules | Anonymous users aren't accidentally permitted |
| `hasPermission` with unrecognized object/ID | Deny | Evaluator enforces default-deny |
| Named parameter `#id` unresolved | Test catches expression error | Needs `-parameters`, `@P`, or `#p0` |
| Proxy call vs. same-bean self-invocation | Difference clearly understood | Self-invocation can bypass advice |
| Adding handler bean early | Configuration takes effect | Avoids a bean existing without infrastructure using it |
| Upgrading Spring Security 6 to 7 | Check deprecations and behavior | Don't rely on old setters indefinitely |

Example denial test using `spring-security-test`:

```java
@SpringBootTest
class ReportServiceSecurityTest {

    @Autowired
    ReportService reportService;

    @Test
    @WithMockUser(username = "alice", roles = "ADMIN")
    void adminCanReadAllowedReportThroughHierarchy() {
        assertEquals("report-42", reportService.readReport(42L));
    }

    @Test
    @WithMockUser(username = "bob", roles = "READER")
    void readerWithoutResourcePermissionIsDenied() {
        assertThrows(AccessDeniedException.class,
                () -> reportService.readReport(42L));
    }
}
```

This test snippet is an example **for a Spring Boot test project** (requiring JUnit 5 imports, `@SpringBootTest`, `@Autowired`, `@WithMockUser`, and `AccessDeniedException` along with `spring-boot-starter-test` and `spring-security-test` dependencies); it is not a standalone source file compiled with `javac`. Because bean/advisor ordering or context setup differences can occur, real integration tests matter more than merely seeing the handler instantiated.

## 11. Common pitfalls and fixes

**1. Defined a `MethodSecurityExpressionHandler` bean, yet role hierarchy has no effect.** Check `@EnableMethodSecurity`, whether the bean is registered too late or duplicated, whether `@Bean static` is used, whether calls go through the service proxy, whether you are testing `@Secured`/JSR-250 instead of expression annotations, and which version is in use. Do not assume all authorization managers share a single handler.

**2. Added `@Component("policy")` and subclassed the expression root just to call `canRead(...)`.** Unnecessary. Use `@policy.canRead(authentication, #p0)` directly; the policy receives all needed arguments and is unit-testable in plain Java.

**3. `hasRole('ADMIN')` fails to match the authority.** Check whether the actual authority is named `ROLE_ADMIN` or uses a custom prefix; distinguish `hasRole` from `hasAuthority`. Test with the hierarchy to confirm roles are implied as intended.

**4. `#documentId` is always null or SpEL cannot find the variable.** Check whether the Java compiler preserves parameter names, `@P` annotations, actual method names on the interface/proxy, and use `#p0` as a reliable check.

**5. Passing `returnObject` into `@PreAuthorize`.** The return value does not exist yet during pre-authorization. Use `@PostAuthorize` for post-method checks; for writes, enforce permissions and atomicity before side effects happen.

**6. Policy hits the database once per element.** With `@PostFilter` or `@PreFilter`, the evaluator/bean may run many times. Watch for N+1 queries, cache appropriately scoped to request/tenant, or push filtering into the database.

**7. Using `isAuthenticated()` alone as full authorization.** Being "authenticated" does not mean the user has permission on a specific resource. For flows requiring authentication, distinguish anonymous, remember-me, and fully authenticated users if required by policy; verify authorities and domain permissions in the proper place.

**8. Constructing SpEL expressions from user input.** Annotations should hold application-managed expressions. Never turn client data into parsed/evaluated SpEL code, because SpEL can reference context beans/methods; client values should appear only as validated **parameter data**.

**9. Overriding the old root method and upgrading to new `@EnableMethodSecurity`.** Check the `Supplier<Authentication>` overload and uphold the `MethodSecurityExpressionOperations` contract. For most business rules, migrate logic into a SpEL bean.

**10. Logging passwords, tokens, or the entire principal while debugging.** Log only the policy name, method, appropriate resource ID, and outcome; follow data security rules and never log authentication secrets.

## 12. Checklist when choosing an extension point

- [ ] Application enables `@EnableMethodSecurity` and tests invoke methods through a Spring bean proxy.
- [ ] Permissions by HTTP route, method, role, and object are clearly distinguished.
- [ ] Custom business policies favor clearly named Java beans; annotation expressions remain short and readable.
- [ ] If using `hasPermission`, both `PermissionEvaluator` overloads enforce safe deny behavior.
- [ ] Role hierarchy/prefix and authority sources in `Authentication` align; tests cover both allowed and denied roles.
- [ ] If defining a handler, it is registered early with an appropriate bean without conflicting handlers.
- [ ] Any subclassing checks the exact version's `createEvaluationContext(Supplier<Authentication>, MethodInvocation)` signature and preserves standard root behavior.
- [ ] Tests cover per-object permissions, tenants, state changes, self-invocation, and SpEL errors.
- [ ] Decisions rely on server-side data, fail closed, limit N+1 queries, and avoid leaking sensitive data.
- [ ] When upgrading to Spring Security 7+, deprecation warnings for `setRoleHierarchy`, `setDefaultRolePrefix`, and `setTrustResolver` are addressed, considering `AuthorizationManagerFactory`.

**Remember:** `DefaultMethodSecurityExpressionHandler` addresses **how method security expressions are evaluated in a specific context**. To add a business rule, usually start with a **policy bean**. Configure the handler or dedicated extension components only when changing shared expression machinery. When you want authorization decided purely in Java, consider `AuthorizationManager`.

## Official Documentation

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security — JavaDoc DefaultMethodSecurityExpressionHandler](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/expression/method/DefaultMethodSecurityExpressionHandler.html)
- [Spring Security — JavaDoc AbstractSecurityExpressionHandler](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/expression/AbstractSecurityExpressionHandler.html)
- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
