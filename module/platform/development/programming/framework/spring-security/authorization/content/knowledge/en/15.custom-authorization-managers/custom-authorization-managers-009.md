# Custom Pointcuts and Method Scope Applied in Spring Security

## 1. The Problem: Right Policy, Wrong Methods

Suppose a system has these services:

- `ArchiveService.archive(id)`: document archiving operation, requires authority `DOC_ARCHIVE`.
- `ArchiveService.preview(id)`: only generates a preview, not an archiving operation.
- `OtherService.archive(id)`: method with the same name belonging to a different business domain.

The requirement is to **intercept only `ArchiveService.archive(...)`**. If the pointcut is too broad, such as `execution(* *..*.archive(..))`, it may accidentally block `OtherService.archive(...)`. If the pointcut is too narrow or has the wrong package/signature, `ArchiveService.archive(...)` may **not be intercepted at all**, creating a vulnerability if the application relies solely on this advisor.

In Spring Security, an `AuthorizationManager<MethodInvocation>` is responsible for **deciding whether to grant/deny access**. Meanwhile, the **Spring AOP `Pointcut`** decides **which methods pass through `AuthorizationManagerBeforeMethodInterceptor`**. Both responsibilities must be designed and tested independently.

This lesson helps you:

1. Understand the `Pointcut → Advisor → AuthorizationManager → method` hook.
2. Write pointcuts by package, class, method, parameters, annotation, or bean.
3. Distinguish intended scope from **actual proxied scope**.
4. Use pointcuts tight enough to avoid false matches while never missing protected methods.
5. Register custom method-security advisors properly; understand interactions with `@PreAuthorize`, transactions, and other advisors.
6. Write tests covering **positive coverage, negative coverage**, and AOP-bypass paths.

### Two Symmetric Bugs to Avoid

| Bug | Example | Consequence |
| --- | --- | --- |
| **Under-matching** | Pointcut targets `ArchiveService.approve(..)` while method is `archive(..)` | Protected method can run without passing through the advisor |
| **Over-matching** | Pointcut `execution(* demo..*Service.*(..))` | Methods outside the policy are denied too, including public/read-only ones |

Do not write only a test asserting "unauthorized user is blocked." Add tests proving "methods outside the pointcut **still run normally**" and tests proving **every sensitive method is covered by the pointcut**.

## 2. Architecture: Pointcut Is Scope, Manager Is Decision

Pre-invocation flow in proxy mode:

```text
Caller
  |
  v
Spring-managed proxy
  |
  v
Advisor with Pointcut
  |
  +-- NO MATCH ------------> invoke target method normally
  |
  +-- MATCH
        |
        v
  AuthorizationManagerBeforeMethodInterceptor
        |
        v
  AuthorizationManager<MethodInvocation>
        |
        +-- GRANT ---------> invoke target method
        |
        +-- DENY ----------> AccessDeniedException
```

`Pointcut` selects matching **join points**. In standard Spring AOP, a join point is **the execution of a Spring bean method through a proxy**. `AuthorizationManager` receives `Supplier<Authentication>` and `MethodInvocation` to decide allow or deny; it can inspect authorities, tenant, argument values, and business policy.

Do not equate this with web request matchers:

| Part | What does it select? | Input target |
| --- | --- | --- |
| `requestMatchers("/api/orders/**")` | HTTP requests traversing the filter chain | HTTP path/method |
| Spring AOP `Pointcut` | Method invocations passing through an AOP proxy | Class, method, signature, annotation, bean, etc. |
| `AuthorizationManager<RequestAuthorizationContext>` | Decides access on matched HTTP requests | Request and path variables |
| `AuthorizationManager<MethodInvocation>` | Decides access on matched service calls | Caller identity, target, arguments |

One HTTP endpoint can call multiple services. One service can be called from HTTP, schedulers, or message consumers. A custom method-security pointcut protects **proxied method calls** from all those entry points without being tied to a single URL.

### Key Fact About `@EnableMethodSecurity`

In Spring Security 6.x, the configuration:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}
```

enables the advisors for `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, and `@PostFilter` with default settings. **`spring-boot-starter-security` alone does not enable method-level authorization.** A custom `Advisor` with its own pointcut can be registered alongside default advisors; it is an **additive** extension unless you explicitly disable existing advisors.

## 3. What Elements Can a `Pointcut` Inspect?

Spring AOP provides `Pointcut` with a **ClassFilter** and a **MethodMatcher**. `ClassFilter` filters out out-of-scope types early; `MethodMatcher` evaluates methods/signatures and sometimes runtime information depending on the pointcut.

With AspectJ expressions in Spring AOP, common designators are:

| Syntax | Meaning | Best fit |
| --- | --- | --- |
| `execution(...)` | Matches method execution by name, return type, parameters, visibility | Targeting specific services/methods clearly |
| `within(typePattern)` | Restricts to methods declared in a group of types/packages | Scoping a module |
| `@annotation(MyAnnotation)` | Methods carrying a matching annotation | Explicit per-method policy markers |
| `@within(MyAnnotation)` | Methods within types carrying a matching annotation | Class-level policy markers |
| `target(SomeType)` | Target object has matching type | Based on target type |
| `this(SomeType)` | Proxy has matching type | Requires understanding JDK/CGLIB proxies |
| `args(TypePattern)` | Checks runtime argument types on call | Matching by runtime types |
| `bean(namePattern)` | Matches Spring bean name; Spring AOP extension | Relying on bean naming conventions |

Spring AOP does not support the full AspectJ weaving pointcut syntax. Designators like `call`, `get`, `set`, `withincode`, or `cflow` are **not** tools for intercepting arbitrary internal method calls or field accesses in Spring AOP proxy mode. Intercepting internal calls or field accesses directly requires AspectJ weaving, which differs from Spring proxies.

### `execution` Syntax

A common pattern:

```text
execution(modifiers-pattern? return-type declaring-type?.method-name(parameters))
```

Examples:

```java
// Match every public method of services in this package and subpackages.
"execution(public * com.acme.billing..*Service.*(..))"

// Match method named archive in a specific class, any overload.
"execution(public * com.acme.docs.ArchiveService.archive(..))"

// Match a signature taking a single primitive long argument.
"execution(public * com.acme.docs.ArchiveService.archive(long))"

// Match methods starting with approve in services of the module.
"execution(public * com.acme.billing..*Service.approve*(..))"

// Only methods carrying an application-defined annotation.
"@annotation(com.acme.security.RequiresApproval)"
```

The lines above are **pointcut expression strings**, not standalone Java class bodies. `*` matches part of a name/type; `..` in parameters `(..)` matches any number and types of arguments; `..` in a type pattern traverses subpackages. `()` matches only no-argument methods, `(long)` matches only primitive `long`. `Long` and `long` **differ** in signatures.

In `execution(public * com.acme.docs.ArchiveService.archive(..))`:

- `public`: matches only public methods.
- First `*`: any return type.
- `com.acme.docs.ArchiveService`: desired declaring type.
- `archive`: exact method name.
- `(..)`: any argument count and types; **can match multiple overloads**.

If the policy reads the first argument as a `long` ID, using `archive(..)` and later **adding an overload taking a DTO** can cause the manager to parse wrongly or deny unexpectedly. Consider narrowing the signature pattern, or thoroughly validating inputs inside the manager and adding regression tests whenever signatures change.

## 4. Writing Pointcuts with the Right Scope

### 4.1. Scoping by Package

```java
"execution(public * com.example.learning.authorization.service..*.*(..))"
```

Intent: apply to public methods inside the chosen service namespace and subpackages. Risk: if read-only queries, health checks, or helpers live in that namespace, the manager may unintentionally deny unprotected methods. If the project moves packages, the pointcut can miss methods.

### 4.2. Scoping by Class/Method

```java
"execution(public * com.example.learning.authorization.ArchiveService.archive(..))"
```

Intent: protect the `archive` operation on a specific type. This is a good fit when scope consists of a few stable services. Risk: renaming the class/method or adding another service with the same responsibility can leave the new target uncovered.

### 4.3. Combining with AND/OR

```java
"within(com.acme.billing..*) && execution(public * *.approve(..))"
```

Applies only when **both** conditions hold. Use `||` when multiple method sets share one policy:

```java
"execution(public * com.acme.billing.InvoiceService.approve(..))"
    + " || "
    + "execution(public * com.acme.billing.PaymentService.release(..))"
```

Before using `!` (negation), evaluate all call paths and future methods. An expression like `!within(..internal..)` without an allowlist boundary can match **far too many** unintended beans. Scope by module/package first, then add exclusions.

### 4.4. Scoping by Annotation

```java
"@annotation(com.acme.security.RequiresArchivePermission)"
```

Fits when you want an explicit marker in code: every method carrying that annotation must pass the policy. Declare runtime retention, proper target, and test methods on both interfaces and implementations. Do not assume meta-annotations, inherited annotations, or proxy modes match identically to Spring Security's built-in `@PreAuthorize` lookup.

### 4.5. Scoping by Bean Name

```java
"bean(document*Service) && execution(public * *.archive(..))"
```

`bean(...)` is a **Spring AOP-specific** designator checking the bean instance name. It is useful when the same class is registered under multiple bean names and only one instance needs a different policy. Test actual bean names in `ApplicationContext` and remember that renaming a bean changes scope. This is not equivalent to AspectJ bytecode weaving.

### 4.6. `@annotation` vs. Hardcoded Class-Name Pointcuts

| Criterion | By class/method signature | By annotation |
| --- | --- | --- |
| Where is the rule placed? | Mainly in configuration | Marker on method and policy in configuration |
| Renaming method/class | Likely requires updating expression | Annotation moves with the method |
| Risk of forgetting a new method | High if pattern is not updated | High if annotation is forgotten |
| Can scope be audited via grep/tests? | Yes | Yes |
| Convention-based policy without annotations | Very suitable | Unnecessary |
| Proxy/interface/meta-annotation effects | Must be tested | Also must be tested |

Neither is universally superior. Pick the option least prone to **dangerous omissions** given your team's code review workflow and architecture.

## 5. Registering a Pointcut with `AuthorizationManagerBeforeMethodInterceptor`

Spring Security provides the constructor:

```java
new AuthorizationManagerBeforeMethodInterceptor(
        Pointcut pointcut,
        AuthorizationManager<MethodInvocation> manager);
```

`AuthorizationManagerBeforeMethodInterceptor` is a Spring AOP advisor/interceptor. When `Pointcut` matches a call, the interceptor fetches `Authentication` and asks the manager whether execution is allowed. On deny, `AccessDeniedException` is typically thrown and the method body does not run.

Example binding a standard authority to a method without implementing a custom permission algorithm:

```java
@Configuration
@EnableMethodSecurity
class ArchiveSecurityConfig {

    @Bean
    @Role(BeanDefinition.ROLE_INFRASTRUCTURE)
    static Advisor archivePointcutAdvisor() {
        AspectJExpressionPointcut pointcut =
                new AspectJExpressionPointcut();

        pointcut.setExpression(
                "execution(public * demo.ArchiveService.archive(..))");

        return new AuthorizationManagerBeforeMethodInterceptor(
                pointcut,
                AuthorityAuthorizationManager.hasAuthority("DOC_ARCHIVE")
        );
    }
}
```

Imports:

```java
import org.springframework.aop.Advisor;
import org.springframework.aop.aspectj.AspectJExpressionPointcut;
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Role;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.authorization.method.AuthorizationManagerBeforeMethodInterceptor;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
```

This is an **integration snippet** for an application with `demo.ArchiveService`. In the complete runnable example in section 8, all classes and files are provided.

Key points:

- `@Bean` registers the advisor in the context; `@Role(ROLE_INFRASTRUCTURE)` marks its infrastructure role; `static` allows early advisor instantiation during bean creation.
- `AspectJExpressionPointcut` defines the method set; the expression literal must match the **actual package and signature**.
- `AuthorityAuthorizationManager.hasAuthority(...)` takes `MethodInvocation` via constructor generic type inference; no need to loop over authorities manually in Java.
- Registering this advisor **does not disable by default** existing `@PreAuthorize`/`@PostAuthorize` advisors.
- Requires Spring AOP proxy support and, when using AspectJ expressions, the appropriate AspectJ parser/weaver dependency (such as `spring-boot-starter-aop` in the demo).
- Guarded methods must be invoked through the Spring-managed proxy; `@Service` on the class is not enough if a caller insists on invoking a `new` instance.

## 6. How Do Custom Pointcuts Differ from `@PreAuthorize`?

Annotation:

```java
@Service
class ArchiveService {

    @PreAuthorize("hasAuthority('DOC_ARCHIVE')")
    public void archive(long id) {
        // ...
    }
}
```

Here Spring Security has a **built-in pointcut** recognizing `@PreAuthorize`. You do not need a custom advisor to check a simple authority. Custom pointcuts are useful when applying a **shared policy across many methods by convention**, avoiding repeated annotations, or applying a Java manager over a centrally defined pointcut.

Comparison:

| Approach | When to use |
| --- | --- |
| `@PreAuthorize` on method/class | Policy is visible right next to business logic; SpEL condition is short and easy to review |
| Policy bean in `@PreAuthorize("@policy...")` | Complex permission logic while keeping boundaries clear via annotation |
| Custom advisor with `Pointcut` + `AuthorityAuthorizationManager` | Applying one authority policy across many methods by naming/package convention |
| Custom advisor with `Pointcut` + custom `AuthorizationManager<MethodInvocation>` | Shared custom Java policy applied to a well-defined method set |
| Replacing all default interceptors | When infrastructure-level semantics genuinely need changing; must assess app-wide impact |

If a method matches both a custom advisor and `@PreAuthorize`, both checks can **execute together**; never assume a custom advisor replaces the annotation or creates an implicit OR branch. Clearly specify whether stacking policies is intentional (typically all executing advice must grant) and test ordering.

## 7. Pointcut Scope and Proxy Scope Are Two Layers of Conditions

A valid expression alone is not enough for a method to be intercepted. There must be **a call passing through a proxy carrying that advisor**.

```text
Intended scope (business)
       ∩
Actual Pointcut match scope
       ∩
Methods/calls interceptable by AOP
       =
Calls actually checked by the custom manager
```

Call path examples:

```java
ArchiveService bean = context.getBean(ArchiveService.class);
bean.archive(42L);          // Via proxy: custom advisor can intercept.

ArchiveService direct = new ArchiveService();
direct.archive(42L);        // Not via Spring proxy: advisor does not run.
```

This is a reference illustration; the class, `ApplicationContext`, and bean configuration must exist to run. Self-invocation case:

```java
@Service
class ArchiveService {

    public String runInternally(long id) {
        return this.archive(id);   // Internal call on target, bypasses proxy.
    }

    public String archive(long id) {
        return "archived-" + id;
    }
}
```

Even if `runInternally` is called on a Spring proxy, once execution enters the target, `this.archive(id)` **does not route back through the proxy**. The advisor protecting `archive` does not execute on that internal path in proxy mode.

### JDK Proxies, CGLIB, and Visibility

- JDK dynamic proxies primarily expose interface methods; callers should hold interface references.
- Class-based (CGLIB) proxies can intercept eligible methods on classes; however, a `final class` cannot be subclassed, a `final method` cannot be overridden, and `private method`s cannot be intercepted this way.
- Method security and transactions are typically placed at **public service boundaries** for predictable behavior under both proxy modes.
- Placing annotations on interfaces vs. implementations can affect whether a custom `@annotation` pointcut actually matches; test with your concrete types and proxy strategy rather than guessing from source.
- If a class/method becomes `final` (common in Kotlin when classes are closed by default), re-verify the proxy mechanism.

Never fix missing coverage by writing an overly broad `execution(* *(..))` pointcut. Fix the root cause: proper bean registration, calls through proxies, accurate pointcut matching, and protected business boundaries.

## 8. Complete Runnable Java 17 / Spring Boot Example

This demo uses **Spring Boot 3.5.16** (Spring Security 6.x) and Java 17; version 3.5.16 is on Maven Central, though the 3.5.x line has reached end of OSS support. In real products, choose a still-supported Boot/Security branch and verify the corresponding APIs.

Demo goals:

1. Do not place `@PreAuthorize` on `ArchiveService.archive`.
2. Use a **custom pointcut** matching exact `demo.ArchiveService.archive(..)`.
3. Block callers lacking `DOC_ARCHIVE` through the proxy.
4. Allow callers holding `DOC_ARCHIVE`.
5. Prove `preview` and `OtherService.archive` lie outside the pointcut scope.
6. Prove calls via `new` instances and self-invocation bypass the advisor.

### 8.1. Directory Structure

```text
pointcut-scope-demo/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── PointcutScopeApplication.java
    │   ├── ArchiveService.java
    │   └── OtherService.java
    └── test/java/demo/
        └── PointcutScopeTest.java
```

### 8.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
          https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>

  <groupId>demo</groupId>
  <artifactId>pointcut-scope-demo</artifactId>
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
      <artifactId>spring-boot-starter-aop</artifactId>
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

`spring-boot-starter-aop` supplies the AOP/AspectJ weaving library needed for `AspectJExpressionPointcut` expressions. The demo runs via `CommandLineRunner` without starting a web server.

### 8.3. `ArchiveService.java`

```java
package demo;

import org.springframework.stereotype.Service;

@Service
public class ArchiveService {

    public String archive(long id) {
        return "archived-" + id;
    }

    public String preview(long id) {
        return "preview-" + id;
    }

    public String internalArchive(long id) {
        return this.archive(id);
    }
}
```

There is no method security annotation on `archive`. The `Pointcut` alone determines whether that method is intercepted.

### 8.4. `OtherService.java`

```java
package demo;

import org.springframework.stereotype.Service;

@Service
public class OtherService {

    public String archive(long id) {
        return "other-" + id;
    }
}
```

This service has a method with the same name `archive` to test **out-of-scope behavior**. If an unauthorized user calling `OtherService.archive` is also denied, the demo's pointcut was written too broadly.

### 8.5. `PointcutScopeApplication.java`

```java
package demo;

import java.util.List;
import java.util.Map;

import org.springframework.aop.Advisor;
import org.springframework.aop.aspectj.AspectJExpressionPointcut;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Role;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.authorization.method.AuthorizationManagerBeforeMethodInterceptor;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

@SpringBootApplication
@EnableMethodSecurity
public class PointcutScopeApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(PointcutScopeApplication.class);
        app.setDefaultProperties(Map.of(
                "spring.main.web-application-type", "none",
                "spring.main.banner-mode", "off",
                "logging.level.root", "OFF"));

        try (ConfigurableApplicationContext ignored = app.run(args)) {
            // CommandLineRunner runs before SpringApplication.run returns.
        }
    }

    @Bean
    @Role(BeanDefinition.ROLE_INFRASTRUCTURE)
    static Advisor archiveAdvisor() {
        AspectJExpressionPointcut pointcut =
                new AspectJExpressionPointcut();
        pointcut.setExpression(
                "execution(public * demo.ArchiveService.archive(..))");

        return new AuthorizationManagerBeforeMethodInterceptor(
                pointcut,
                AuthorityAuthorizationManager.hasAuthority("DOC_ARCHIVE"));
    }

    @Bean
    CommandLineRunner runDemo(
            ArchiveService managedArchive,
            OtherService otherService) {

        return args -> {
            try {
                System.out.println("archive proxied: "
                        + AopUtils.isAopProxy(managedArchive));

                authenticate("reader", "DOC_READ");

                try {
                    System.out.println("reader archive: "
                            + managedArchive.archive(42L));
                } catch (AccessDeniedException denied) {
                    System.out.println("reader archive: DENIED");
                }

                System.out.println("reader preview: "
                        + managedArchive.preview(42L));
                System.out.println("reader other: "
                        + otherService.archive(42L));
                System.out.println("reader new: "
                        + new ArchiveService().archive(42L));
                System.out.println("reader self: "
                        + managedArchive.internalArchive(42L));

                authenticate("archiver", "DOC_ARCHIVE");
                System.out.println("archiver archive: "
                        + managedArchive.archive(42L));
            } finally {
                SecurityContextHolder.clearContext();
            }
        };
    }

    private static void authenticate(String name, String authority) {
        SecurityContext context =
                SecurityContextHolder.createEmptyContext();
        context.setAuthentication(
                UsernamePasswordAuthenticationToken.authenticated(
                        name,
                        "not-a-real-credential",
                        List.of(new SimpleGrantedAuthority(authority))));
        SecurityContextHolder.setContext(context);
    }
}
```

Key steps:

- Spring Boot creates beans and appropriate auto-proxies. `archiveAdvisor` is a Spring infrastructure bean; `pointcut` inspects the service's signature.
- `AuthorityAuthorizationManager` checks authority `DOC_ARCHIVE`, **without using the `ROLE_` prefix**.
- `CommandLineRunner` receives `ArchiveService` and `OtherService` via constructor/method injection. Calls to `managedArchive.archive` pass through the Spring proxy.
- `new ArchiveService().archive` is a direct Java call and **bypasses AOP advice**.
- `managedArchive.internalArchive` enters the proxy for `internalArchive`, yet that method is **not in the pointcut**. Once inside the target, `this.archive` also bypasses the proxy.
- `SecurityContextHolder` is populated manually only to keep the demo easy to follow. Real applications must use a proper authentication mechanism; never treat this context setup as a production login handler.

### 8.6. Running and Reading the Output

Requires JDK 17+, Maven, and downloading dependencies. In the directory containing `pom.xml`:

```bash
mvn -q -DskipTests clean package
java -jar target/pointcut-scope-demo-1.0.0.jar
```

Lines printed by the application (ignoring JVM/tooling messages that may appear depending on environment):

```text
archive proxied: true
reader archive: DENIED
reader preview: preview-42
reader other: other-42
reader new: archived-42
reader self: archived-42
archiver archive: archived-42
```

Explanation:

| Line | Output | Meaning |
| --- | --- | --- |
| `archive proxied` | `true` | Spring returned a proxy for `ArchiveService` because a matching advisor exists |
| `reader archive` | DENIED | `ArchiveService.archive` is in the pointcut, lacks `DOC_ARCHIVE` |
| `reader preview` | Success | `preview` is in the same class yet **outside the pointcut** |
| `reader other` | Success | `OtherService.archive` shares the method name yet is a different type, **outside the pointcut** |
| `reader new` | Success | `new` instance skips the proxy; a bug if the app treats it as a guarded service |
| `reader self` | Success | `this.archive` bypasses the proxy; a design bug if internal paths must be protected |
| `archiver archive` | Success | Method matches pointcut and manager grants the authority |

**Important:** `preview` and `OtherService.archive` succeeding in the demo only proves the custom advisor's scope. In production, those two methods still need their own appropriate rules if they touch sensitive data. Never infer that "outside this pointcut" means "automatically safe."

## 9. Testing Scope Properly: Both Inside and Outside the Pointcut

A test asserting only "reader is blocked on `archive`" is **not enough**. If the pointcut accidentally matches the entire package, that test still passes while unrelated methods are broken.

Create `src/test/java/demo/PointcutScopeTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class PointcutScopeTest {

    @Autowired ArchiveService archive;
    @Autowired OtherService other;

    @Test
    @WithMockUser(authorities = "DOC_READ")
    void deniesTargetMethodForReader() {
        assertThrows(AccessDeniedException.class,
                () -> archive.archive(42L));
    }

    @Test
    @WithMockUser(authorities = "DOC_ARCHIVE")
    void allowsTargetMethodForArchiver() {
        assertEquals("archived-42", archive.archive(42L));
    }

    @Test
    @WithMockUser(authorities = "DOC_READ")
    void excludesOtherMethodsAndOtherTypes() {
        assertEquals("preview-42", archive.preview(42L));
        assertEquals("other-42", other.archive(42L));
    }

    @Test
    @WithMockUser(authorities = "DOC_READ")
    void showsSelfInvocationBypassInProxyMode() {
        assertEquals("archived-42", archive.internalArchive(42L));
    }
}
```

Test command:

```bash
mvn -q test
```

The fourth test **intentionally demonstrates a bypass path**, not a good security criterion. When a real application has an internal method that must be protected, fix the design by moving the boundary to another Spring bean, and change the test from "bypass" to **"properly denied."**

The test suite proves:

1. The pointcut **matches** the target method and the manager denies properly.
2. The manager grants properly with valid permissions.
3. The pointcut **does not match** the other two methods.
4. Spring proxies have a boundary limitation when a caller invokes `this.archive`.

### Negative Tests for Renaming/Overloads

If a later version adds:

```java
public String archive(String id) {
    return "archived-" + id;
}
```

The expression `archive(..)` will cover **both overloads**. If you only want the `long` method, narrow it to:

```java
"execution(public * demo.ArchiveService.archive(long))"
```

Then test both overloads: `archive(long)` must deny `reader`; whether `archive(String)` is allowed must follow an **explicitly decided policy**, never skipped accidentally just because it is an overload.

Conversely, if a developer renames `archive` to `archiveDocument`, the old pointcut may no longer match; without another advisor, `reader` can call it. To avoid fail-open during refactors, use explicit policy annotations and coverage tests, or tests covering the complete inventory of sensitive methods.

## 10. Choosing the Extension Point: Expression, Annotation, or `Pointcut`?

### Case 1 — Only a Few Methods Need a Business Policy

You may only need:

```java
@PreAuthorize("hasAuthority('DOC_ARCHIVE') and "
            + "@archivePolicy.canArchive(authentication, #p0)")
public void archive(long id) {
    // ...
}
```

Policy sits in a Java bean, easy to unit test. No custom `Advisor` is needed just to handle one rule on one method.

### Case 2 — A Whole Group of Methods Needs a Shared Authority

For example, the billing service module follows the convention "all public methods starting with `approve` require `BILLING_APPROVE`." Custom pointcut:

```java
"execution(public * com.acme.billing..*Service.approve*(..))"
```

This avoids repeating annotations across many classes, though tests must prove the exact set of methods is protected.

### Case 3 — Reusable Policy for a Heterogeneous Set of Methods

Use a project-controlled marker annotation:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface RequiresArchivePermission {
}
```

This is a Java annotation declaration with imports `java.lang.annotation.Retention`, `RetentionPolicy`, `Target`, and `ElementType`; package and annotation name are defined by the project. Marked method:

```java
@RequiresArchivePermission
public void archive(long id) {
    // ...
}
```

Pointcut:

```java
"@annotation(com.acme.security.RequiresArchivePermission)"
```

**Spot the difference:** a custom marker for a custom pointcut does not work like Spring Security's `@PreAuthorize` without an advisor. If an annotation is meant to replace `@PreAuthorize`, ensure your custom manager handles all attributes on the annotation (if parameterized) and test methods on both classes and interfaces.

### Case 4 — Rule Needs to Inspect Parameters in `MethodInvocation`

The pointcut only selects methods; permission based on ID/tenant is computed **inside the manager**:

```java
public final class ArchivePolicyManager
        implements AuthorizationManager<MethodInvocation> {

    private final ArchivePolicy policy;

    public ArchivePolicyManager(ArchivePolicy policy) {
        this.policy = policy;
    }

    @Override
    public AuthorizationResult authorize(
            Supplier<Authentication> authenticationSupplier,
            MethodInvocation invocation) {

        Object[] arguments = invocation.getArguments();
        if (arguments.length != 1
                || !(arguments[0] instanceof Long documentId)
                || documentId <= 0) {
            return new AuthorizationDecision(false);
        }

        Authentication auth = authenticationSupplier.get();
        boolean allowed = auth != null
                && auth.isAuthenticated()
                && policy.canArchive(auth, documentId);
        return new AuthorizationDecision(allowed);
    }
}
```

Minimal imports:

```java
import java.util.function.Supplier;
import org.aopalliance.intercept.MethodInvocation;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.core.Authentication;
```

`ArchivePolicy` is implemented by the application, reading tenant/owner/document state from trusted data. This is a **non-standalone integration snippet**; no `ArchivePolicy` bean/repository exists in the section 8 demo.

Key point: the manager must not assume every overloaded method shares the same signature if `archive(..)` matches multiple types. Return DENY for unsupported parameter shapes, or narrow the pointcut—never silently grant.

## 11. Class/Bean Scope and Structural Project Changes

### 11.1. Moving Packages

Pointcut:

```java
"execution(public * com.acme.orders..*Service.*(..))"
```

When a service moves from `com.acme.orders` to `com.acme.payment`, its methods can fall outside the pointcut. When policies depend on packages, **renames/moves are security-relevant changes** requiring review and regression tests.

### 11.2. Interfaces and Implementations

If a service has a `DocumentOperations` interface and a `DocumentServiceImpl` class, a pointcut targeting the concrete class name may behave differently depending on JDK vs. class proxies and how Spring resolves methods. Scoping by interface signatures can be clearer when JDK proxies are intentionally used. Conversely, class-based proxies allow targeting implementation methods. Never assume every proxy strategy matches an `@annotation`/`execution` identically; test against your actual setup.

### 11.3. Default Methods, Inherited Methods, and Bridge Methods

Java interface default methods, inheritance/generic bridge methods, and overloaded methods can make runtime signatures more complex than source code suggests. Spring AOP and Spring Security have mechanisms to resolve methods/annotations properly, yet **you write the custom pointcut**, so test exact behavior instead of assuming. When possible, place security boundaries on stable public service methods and avoid relying on compiler-generated method names.

### 11.4. Multiple Context Configurations

With parent/child `ApplicationContext`s or multiple security/filter contexts, the advisor must be registered in the context managing **the target bean to protect**. An advisor bean existing somewhere in the application does not guarantee it applies to beans in another context. Verify proxying on the real bean where it is created.

## 12. When Multiple Advisors Match the Same Method

Suppose:

```java
@PreAuthorize("hasAuthority('DOC_READ')")
@Transactional
public void archive(long id) {
    // ...
}
```

and a custom advisor requiring `DOC_ARCHIVE` also matches that method. When both corresponding interceptors run, the caller may need **both authorities**, depending on policy and manager behavior. Never assume a custom advisor "overrides" `@PreAuthorize` or `@Transactional`.

Order in the chain matters:

- `AuthorizationManagerBeforeMethodInterceptor` checks **before entering the target method** when its turn arrives in the chain.
- The transaction interceptor may open a transaction before or after the security interceptor depending on order/configuration.
- `@PostAuthorize` runs after the method; use it to protect returned read data, not to automatically roll back already-written side effects.
- One method can have multiple security advisors, and each can deny at a different point.

`AuthorizationManagerBeforeMethodInterceptor` supports `setOrder(int)`. Spring Security also provides `AuthorizationInterceptorsOrder` to position advisors relative to framework annotation interceptors; for instance, typical values in Spring Security 6.5 place `PRE_FILTER` near 100 and `PRE_AUTHORIZE` near 200. Never rely on arbitrary magic numbers when policy depends on ordering; consult your version's API and **test the actual ordering** of transactions and security.

When you want **only your custom policy instead of default `@PreAuthorize`**, Spring Security provides `@EnableMethodSecurity(prePostEnabled = false)` followed by registering your custom advisor. However, that affects the entire application: `@PreAuthorize`/`@PostAuthorize` will stop being processed under the old setup. Do not use it to fix a single rule without auditing every method.

## 13. Safety Policy: Never Let a Pointcut Fail Open

A wrong pointcut can cause code to **go unchecked** rather than receive DENY. That is an important difference from a manager returning `AuthorizationDecision(false)`: if the interceptor never runs, the manager never gets a chance to deny.

Therefore, fail-closed must be designed **at both layers**:

1. **Pointcut layer:** the list of protected methods must be fully covered, with behavioral tests on proxied calls and tests detecting refactors/renames.
2. **Manager layer:** once matched, missing identity/ID/tenant/permission or an unresponsive policy backend must return deny or an appropriate system error, never grant.

Example condition of a manager checking owner from a request:

```java
// Wrong: client-controlled data can be forged.
String owner = request.getHeader("X-Owner");

// Right direction: get subject from Authentication and owner/tenant from trusted DB.
```

This is a policy illustration, not a complete application. In a method manager, `MethodInvocation` typically already holds arguments; you still must verify resource ownership and tenant server-side.

### Handling Concurrently Changing Resources

If the manager reads permissions at T1 and the method writes data at T2, owner/tenant/version can change in between. A custom pointcut does not solve that race condition. For critical writes, use transactions, conditional updates, optimistic locking, or pessimistic locking per your consistency contract. `@Transactional` does not automatically keep owner unchanged without appropriate isolation/concurrency control.

## 14. Common Mistakes

**Mistake 1 — Using overly broad package wildcards.** A pattern guarding "every public method in `..service..`" can block harmless queries, background jobs, and health-related hooks. Narrow by class/method names or marker annotations and test excluded methods.

**Mistake 2 — Forgetting to update the pointcut after renaming a package or method.** If a method escapes the pointcut, there is no `AccessDeniedException`; the method simply runs. Integration tests for every critical boundary are mandatory.

**Mistake 3 — Only unit-testing `AuthorizationManager`.** Unit-testing the manager proves grant/deny logic, yet does not prove the pointcut **actually matches**. Add tests calling Spring beans through proxies.

**Mistake 4 — Testing only methods that must be blocked.** A pointcut accidentally matching out-of-scope methods still passes every deny test. Add **negative scope tests** for sibling methods in the same class, same-named methods in other classes, subpackages, and overloads.

**Mistake 5 — Thinking `@Service` on the class is enough.** If the method is called via `new` or `this.method()`, Spring proxy mode will not intercept it. Route calls through bean proxies and split service boundaries when needed.

**Mistake 6 — Using `call(...)` or `get(...)` in Spring proxy AOP.** Those are AspectJ weaving pointcut designators, not standard Spring AOP runtime ones; the expression may be invalid. Use `execution(...)` for method execution.

**Mistake 7 — Placing a marker annotation only on an interface without testing.** A custom `@annotation` pointcut can see signatures differently across proxies and implementations; test against your actual interface proxy strategy and annotation resolution.

**Mistake 8 — Writing `archive(..)` when the manager only understands `long`.** New overloads can match and be wrongly denied, or get skipped if the pointcut changes. Keep signatures and policies aligned.

**Mistake 9 — Returning allow when tenant/owner cannot be read.** Once the manager is invoked, data errors must deny or throw an explicit system error per API contract, never treat missing data as permission.

**Mistake 10 — Attaching a custom advisor while keeping `@PreAuthorize` without realizing both run.** This can create stricter rules or unintended ordering. Test combinations with and without each authority.

**Mistake 11 — Seeing `AopUtils.isAopProxy(bean) == true` and assuming protection is complete.** The proxy may exist for transactions, caching, or another advisor; test the exact pointcut behavior, not just the proxy flag.

**Mistake 12 — Confusing method pointcuts with HTTP matchers.** A URL match does not protect service calls from a scheduler. A custom method advisor does not automatically protect an HTTP route if a controller takes another path bypassing that method.

## 15. Scope and Permission Testing Matrix

A solid pointcut design has an **expectation map** for every group of methods.

| Call | Matches pointcut? | Caller lacks `DOC_ARCHIVE` | Caller has `DOC_ARCHIVE` |
| --- | --- | --- | --- |
| `beanArchive.archive(42)` | Yes | DENY | ALLOW |
| `beanArchive.preview(42)` | No | Not blocked by **this advisor** | Not blocked by **this advisor** |
| `beanOther.archive(42)` | No | Not blocked by **this advisor** | Not blocked by **this advisor** |
| `new ArchiveService().archive(42)` | Bypasses proxy | Not intercepted by Spring AOP | Not intercepted by Spring AOP |
| `beanArchive.internalArchive(42)` calling `this.archive` | Internal call bypass | Not intercepted by `archive`'s advisor | Not intercepted by `archive`'s advisor |
| `ArchiveService.archive(String)` (if overload added) | Yes with `(..)`; no with `(long)` | Depends on pointcut and manager | Depends on pointcut and manager |
| `ArchiveService` moved to another package | Possibly no | Fail-open risk | Tests must alert |
| `ArchiveService.archive` changed to `final` under CGLIB | May not intercept | Fail-open risk | Tests must alert |
| Method also gets `@PreAuthorize` | May receive extra advisor | Checks must be evaluated together | Does not create OR |

Core tests:

1. **Functional allow/deny**: manager properly enforces authority/tenant/owner when in-scope methods are called.
2. **Coverage test**: every sensitive method is within pointcut scope through Spring proxies.
3. **Exclusion test**: out-of-scope methods are not unexpectedly blocked by the new advisor.
4. **Refactor test**: renames/moves/overloads or new services do not silently drop coverage.
5. **Composition test**: when stacking annotations, transactions, and custom advisors, authorization and rollbacks remain consistent.
6. **Bypass test**: detect `new`/self-invocation on paths that must be protected, and fix the design rather than keeping bypasses as features.

When verifying scope, assert **real business effects** or method-call counters alongside exceptions; checking only interceptor logs or "proxy = true" is insufficient.

## 16. Troubleshooting When a Pointcut Does Not Fire

Investigate in order to minimize debugging time:

1. **Is the target bean created by Spring?** Check component scan, `@Bean`, and the right `ApplicationContext`; eliminate manual `new` outside the container.
2. **Is the custom `Advisor` actually registered?** Check config scanning, successful `@Bean` creation, dependencies, and infrastructure role.
3. **Does the pointcut match the target class/method?** Recheck full package, method name, visibility, signature/overloads, and interface vs. implementation methods.
4. **Does the call go through the proxy?** Check self-invocation, `final`/`private` methods, JDK/CGLIB proxy mode, and bean scope.
5. **Did the manager run yet grant wrongly?** Check `Authentication`, role/authority prefixes, tenant, argument mapping, and fail-closed logic.
6. **Are other advisors interfering?** Check `@PreAuthorize`, transactions, caching, ordering, and other advisor beans.
7. **Test through real entry points**: APIs, scheduled jobs, message handlers, or service beans; test deny and excluded scopes separately.

When debugging, you can use:

```java
boolean proxied = AopUtils.isAopProxy(serviceBean);
boolean jdkProxy = AopUtils.isJdkDynamicProxy(serviceBean);
boolean cglibProxy = AopUtils.isCglibProxy(serviceBean);
```

This is an integration snippet; `serviceBean` must be a reference obtained from Spring. `AopUtils` belongs to `org.springframework.aop.support`. If you need to inspect the advisor chain, you can inspect advisors on `Advised` (when supported by the proxy), yet never treat an advisor's presence as proof a method is intercepted: verify matching and runtime behavior.

Never log access tokens, passwords, or full principals to debug pointcuts; log method signatures, policy names, bounded resource IDs, and permission outcomes per audit policy.

## 17. Production Checklist for Custom Pointcuts

- [ ] Clearly distinguished **intended method set** from **methods actually matched by the pointcut**.
- [ ] Chose the right `MethodInvocation` manager for method security rather than mixing in an HTTP request manager.
- [ ] Pattern has tight package/class/method/annotation boundaries; avoided unjustified broad wildcards.
- [ ] Understood that `execution(public * Type.method(..))` matches every overload.
- [ ] Registered `Advisor` in the right Spring context with an early-initialized bean.
- [ ] `@EnableMethodSecurity` and required Spring AOP/AspectJ dependencies are active.
- [ ] Sensitive methods are invoked via Spring-managed proxies; no `new`/`this.method()` bypass paths exist.
- [ ] Verified JDK/CGLIB behavior, interface/implementation annotations, `final`, and method visibility.
- [ ] Manager denies when identity/permission/resource is missing; never grants on parse/lookup errors.
- [ ] Multiple advisors/transactions have tests for ordering and stacked conditions.
- [ ] Integration tests exist for **allow, deny, in-scope, out-of-scope**, and renames/moves/overloads.
- [ ] For writes, consistency, transactions, and race conditions are handled outside the pointcut.
- [ ] Security review covers every package/class/method refactor; tests catch lost coverage.
- [ ] Debugging/auditing never leaks authentication secrets.

**Key principle:** `Pointcut` answers **"which method calls must be checked?"**; `AuthorizationManager` answers **"is that call allowed to execute?"**. In custom method-security policies, getting either half wrong can create a security flaw or break business functionality. Test **both sides of the boundary** and verify calls actually traverse Spring proxies.

## References

- [Spring Security 6.5 — Method Security: Matching Methods with Custom Pointcuts](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 6.5 — AuthorizationManagerBeforeMethodInterceptor JavaDoc](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/authorization/method/AuthorizationManagerBeforeMethodInterceptor.html)
- [Spring Framework — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html)
- [Spring Framework — Proxying Mechanisms and Self-invocation](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [Spring Boot 3.5.16 Release](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now)
