# Annotations on Classes, Methods, Interfaces, and Inheritance Rules

> **Module:** Spring Security – authorization  
> **Group:** Method security  
> **Contents:** How Spring Security applies `@PreAuthorize`, `@PostAuthorize`, and other method-security annotations when placed on classes, methods, interfaces, or parent types; annotation precedence and conflicts; Spring AOP proxy limitations; a Java 17 example and a test suite proving actual policy enforcement.

## 1. The Problem: Where Can a Method "See" an Annotation From?

A document management application has the following classes:

~~~java
@PreAuthorize("hasRole('USER')")
@Service
public class DocumentService {

    public String list() {
        return "Document list";
    }

    @PreAuthorize("hasRole('ADMIN')")
    public String delete(long id) {
        return "Deleted " + id;
    }
}
~~~

Key questions:

1. Does `list()` require `ROLE_USER` even without declaring an annotation of its own?
2. Does `delete()` require **only** `ROLE_ADMIN`, or both `ROLE_ADMIN` **and** `ROLE_USER`?
3. If `@PreAuthorize` is placed on an **interface**, and the implementation does not repeat the annotation, is it still protected?
4. If a class implements **two interfaces** with two different `@PreAuthorize` annotations on the same method, which annotation does Spring choose?
5. If an annotated method is **self-invoked within the same bean**, does the security check run?
6. What kind of test is sufficient to conclude the annotation is actually applied?

**Upfront conclusion:** With proxy-based method security, a `@PreAuthorize` annotation on a class applies by default to protected methods of that class; a `@PreAuthorize` on a specific method **overrides the same-type annotation on the class**. Interfaces can carry annotations discovered by Spring Security through the type hierarchy, but conflicting annotations inherited from multiple interfaces must be resolved explicitly; there is no rule that "the first declared interface wins".

You must distinguish **precedence within the same annotation type** from **multiple different annotation types** handled by separate interceptors. They do not share the same "override" algorithm.

## 2. Enable Method Security Before Discussing Inheritance

In Spring Boot 3.x / Spring Security 6.x, having the Spring Security dependency or HTTP rules **does not automatically enable** `@PreAuthorize`. Configuration is required:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

`@EnableMethodSecurity` activates the method authorization infrastructure for Spring-managed beans. `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, and `@PostFilter` are supported by default in standard configuration.

Other annotation styles require optional flags:

~~~java
@EnableMethodSecurity(
        securedEnabled = true,
        jsr250Enabled = true
)
~~~

- `securedEnabled=true` enables `@Secured`.
- `jsr250Enabled=true` enables Jakarta annotations such as `@RolesAllowed`, `@PermitAll`, and `@DenyAll` under matching configuration.
- With Spring Boot 3+, use the `jakarta.annotation.security` namespace for JSR-250; old blog examples using `javax.annotation.security` may be incompatible.

**Important:** method security applies when **the call passes through a Spring AOP advisor/proxy** or configured weaving mechanism. Putting an annotation on an object created via `new`, a `private` method, or an internal call bypassing the proxy does not guarantee the interceptor will execute.

HTTP authorization via `authorizeHttpRequests` and method authorization can apply together:

~~~text
HTTP request
   |
   v
Spring Security FilterChain
   +-- HTTP rule (path/method)
   |
   v
Controller
   |
   v
Spring-managed service proxy
   +-- method-security interceptor
   |
   v
Business method / repository
~~~

A service can also be called from a scheduler, listener, or batch job outside HTTP. Method-level policies hold independent value, though non-HTTP callers must handle `AccessDeniedException` appropriately.

## 3. Annotation Resolution Mechanism: Searching the Object Hierarchy

Method security uses Spring AOP pointcuts and metadata-lookup mechanisms across **the method and type hierarchy** of the Spring-managed object. For each enabled annotation type, Spring Security uses its corresponding interceptor/authorization manager.

Visualize a call `documentService.delete(42)`:

~~~text
Caller -> Spring proxy -> AOP advisor
                          |
                          v
              Find matching @PreAuthorize
              - specific method?
              - class containing method?
              - corresponding declaration on parent/interface?
                          |
                          v
              PreAuthorizeAuthorizationManager
                          |
                   evaluate SpEL
                          |
                   allow / deny
                          |
                          v
                    method body
~~~

The lookup relies on **Spring Security infrastructure**, not just plain Java reflection. An implementation method might carry no annotation directly in bytecode, while Spring Security still locates and applies the annotation declared on the interface method.

### 3.1. Declaration Scopes

| Location | Example | Primary Effect |
|---|---|---|
| Method implementation | `@PreAuthorize` directly on `delete()` | Specific policy for that method |
| Class implementation | `@PreAuthorize` directly on `DocumentService` | Default policy for interceptor-protected methods in the class |
| Interface method | `@PreAuthorize` on `DocumentApi.read()` | Security contract implementers can inherit in Spring method security |
| Interface type | `@PreAuthorize` on `DocumentApi` | Default interface policy for contract-protected methods |
| Superclass method/type | Annotation on parent declaration | Can be discovered by Spring's method-security metadata resolver through the hierarchy |
| Meta-annotation | `@CanReadDocument` annotated with `@PreAuthorize` | Business-meaningful name replacing repeated SpEL |

**Do not assume** every location in the table always works on every Java method: proxy type, overridability, visibility, same annotation type, interface conflicts, and whether the annotation group is enabled all matter.

## 4. Class-Level Annotations: Default Policy for Methods

Example:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
@PreAuthorize("hasRole('USER')")
public class CatalogService {

    public String list() {
        return "catalog";
    }

    public String detail(long id) {
        return "item-" + id;
    }
}
~~~

A call **from outside through the Spring proxy** to `list()` or `detail(...)` undergoes the `hasRole('USER')` check if method security is enabled and the bean is proxied appropriately.

This provides a baseline policy without repeating the annotation on every method. It also carries a risk: when adding a new method to the class, that method inherits the baseline without the author noticing; if the baseline is an overly broad `permitAll`, a new method could be exposed accidentally.

### 4.1. Class-Level Policy Does Not Copy Annotations into Each Method's Source/Bytecode

Do not write a test like:

~~~java
boolean found = CatalogService.class
        .getMethod("list")
        .isAnnotationPresent(PreAuthorize.class);
~~~

and conclude `false` means the method is unprotected. `list()` does not need `@PreAuthorize` directly in Java reflection when the class is annotated. Spring Security uses its own resolver and advisor.

To prove enforcement, invoke the **Spring bean** through the proxy under different `Authentication`s and verify allow/deny.

### 4.2. Should Annotations Be Placed on Controllers?

Spring Security allows method security on controllers or services. However, for sensitive operations, the **service/use-case boundary** is usually the right place for permissions, because the same service may be called from REST, GraphQL, batch jobs, message consumers, or internal code.

~~~java
@Controller
@PreAuthorize("hasRole('USER')")
class MyController {
    // Can protect methods intercepted by Spring AOP.
}
~~~

Never treat a controller annotation as a reason to skip object-level checks in services/repositories; cross-tenant document access must still be checked.

## 5. Method-Level Annotations: Overriding Same-Type Class-Level Rules

Consider the class:

~~~java
@Service
@PreAuthorize("hasRole('USER')")
public class CatalogService {

    public String list() {
        return "list";
    }

    @PreAuthorize("hasRole('ADMIN')")
    public String delete(long id) {
        return "delete-" + id;
    }
}
~~~

With `@PreAuthorize`:

- `list()` has no specific annotation → uses `hasRole('USER')` from the class.
- `delete(...)` has `@PreAuthorize` directly on the method → **overrides the class-level `@PreAuthorize` condition** with `hasRole('ADMIN')`.
- Do not assume `delete()` requires **both** `ROLE_USER` **and** `ROLE_ADMIN`. If both are required, write the policy explicitly.

Example requiring both:

~~~java
@PreAuthorize("hasRole('USER') and hasRole('ADMIN')")
public String delete(long id) {
    return "delete-" + id;
}
~~~

Even so, requiring both roles is not always meaningful: many systems have a role hierarchy where ADMIN implies USER, while others have two independent roles. Choose conditions according to real business semantics.

### 5.1. Avoid Mechanically Assuming "Method-Level Is Always Stricter"

A method-level annotation can **relax** a class-level policy:

~~~java
@PreAuthorize("hasRole('ADMIN')")
public class AdminService {

    @PreAuthorize("permitAll()")
    public String health() {
        return "ok";
    }
}
~~~

In this example using `@PreAuthorize`, `health()` is designed to be public at the method authorization layer, even though the class baseline requires ADMIN. It can still be blocked by HTTP rules or other filters.

Thus, overriding is not an operator that automatically picks the strictest condition. When reviewing a diff that adds an annotation to a method, check whether **the new policy weakens the class-level requirement**.

### 5.2. Overloaded Methods and Method Names

Two methods with the same name but different parameters:

~~~java
@PreAuthorize("hasAuthority('report:read')")
public String report(long id) { return "r-" + id; }

@PreAuthorize("hasAuthority('report:export')")
public byte[] report(long id, String format) {
    return new byte[0];
}
~~~

These are two distinct signatures and can have different policies. Tests must call **the exact overload**; never assume an annotation is "inherited by method name" from one overload to another.

## 6. Annotations on Interface Methods: Security Contracts

An API using an interface:

~~~java
public interface DocumentReader {

    @PreAuthorize("hasAuthority('document:read')")
    String read(long documentId);
}
~~~

Implementation:

~~~java
@Service
public class DefaultDocumentReader implements DocumentReader {

    @Override
    public String read(long documentId) {
        return "document-" + documentId;
    }
}
~~~

In Spring Security's **standard proxy-based** method security configuration, annotations on interface methods are discovered by the framework and applied to the implementation method. There is no need to copy `@PreAuthorize` onto the implementation just for the Java compiler to see it.

This is advantageous when the interface represents a **security contract**: all Spring-managed implementations accessed through compatible interceptors can share one policy.

**However:** an interface contract alone does not protect an object manually instantiated with `new DefaultDocumentReader()`; calls outside the Spring proxy are not processed by the interceptor.

### 6.1. Annotations on Interface Types

A default policy can be placed on the entire interface:

~~~java
@PreAuthorize("hasAuthority('document:read')")
public interface ReadOnlyDocumentApi {
    String list();
    String read(long id);
}
~~~

Methods governed through this contract by Spring method security can inherit the interface type policy. Still:

- An implementation may add new methods **not belonging to the contract**; do not rely on the interface annotation to protect custom methods added solely to the implementation.
- If a class implements multiple interfaces, precedence/conflict rules must be tested.
- If you want uniform service constraints, a class-level annotation on the implementation can be easier to audit.
- If the interface is reused in another module, changing an annotation on the interface can impact **multiple beans**.

**Recommendation:** when placing annotations on an interface, treat them as part of API compatibility and the security contract; review changes just like permission changes.

### 6.2. Java `@Inherited` Is Not Equivalent to Spring Method-Security Inheritance

Java has `@Inherited` for annotations, yet it does not "copy annotations onto every method implementing an interface". Under standard reflection, `@Inherited` applies specifically to **class annotations** along the superclass chain; it does not make an interface annotation a direct annotation of the implementing class, nor does it cause overridden methods to inherit annotations automatically.

In Spring Security, the method-security resolver is designed to search annotations across the bean's hierarchy. Hence:

~~~text
Java reflection:
  ImplementationMethod.getDeclaredAnnotation(...)
    -> may be null

Spring Security method interceptor:
  searches method/type/interface hierarchy
    -> can find the interface rule
~~~

This is why **unit tests using plain reflection cannot replace Spring AOP integration tests**.

## 7. Inheritance Rules Between Implementation and Interface

Conceptually, a rule declared directly on the **concrete method** has the highest explicitness. Class/interface policies provide defaults for methods lacking a more specific rule of **the same annotation type**.

Example:

~~~java
public interface PaymentApi {
    @PreAuthorize("hasAuthority('payment:read')")
    String payment(long id);
}
~~~

Implementation needing a more specific policy:

~~~java
@Service
public class PaymentService implements PaymentApi {

    @Override
    @PreAuthorize("hasAuthority('payment:read') and " +
                  "@paymentPolicy.canSee(authentication, #id)")
    public String payment(long id) {
        return "payment-" + id;
    }
}
~~~

Here the implementation method writes a new policy containing **both the general permission and the resource check** intentionally. Do not annotate the method with only `hasAuthority('payment:special')` assuming the interface's `payment:read` expression will automatically be ANDed in, because same-type `@PreAuthorize` follows override rules rather than unconditional accumulation.

The snippet requires a `paymentPolicy` bean, properly discovered `#id` parameter name, `@EnableMethodSecurity`, and Spring-managed invocation. Not standalone Java.

### 7.1. Keeping Both Baseline and Method Restrictions

Read the baseline policy on the class/interface explicitly, then write the new expression including **all conditions that must be preserved**:

~~~java
@PreAuthorize(
    "hasAuthority('payment:read') " +
    "and @paymentPolicy.canSee(authentication, #id)"
)
~~~

Or move the shared policy into a bean:

~~~java
@PreAuthorize("@paymentPolicy.canRead(authentication, #id)")
~~~

The `paymentPolicy` bean must check authentication, permissions, tenant, and resource completely. Extracting to a bean helps when policies are complex and need unit tests, though it also introduces a dependency to manage in the Spring context.

### 7.2. Inheritance from a Superclass

A subclass can be protected by Spring Security via annotations on its superclass/supermethod because Spring's method-security metadata resolver searches the object's hierarchy.

~~~java
@PreAuthorize("hasRole('USER')")
public abstract class BaseReportService {
    public String list() { return "reports"; }
}

@Service
public class MonthlyReportService extends BaseReportService {
    // Can use class/superclass policy when called through the Spring proxy.
}
~~~

When a subclass overrides a method, adds annotations on new methods, or changes the class hierarchy, **you must run integration tests**. Do not assume Java `@Inherited` rules fully explain Spring AOP and method-security pointcuts.

For sensitive methods, a direct policy on the concrete service method can be easier to follow than tracing multiple superclass/interface layers. Use inheritance to reduce duplication only when the security contract is truly uniform.

## 8. Two Interfaces Declaring Annotations: Conflicts and Startup Failure

Example:

~~~java
public interface SupportApi {
    @PreAuthorize("hasAuthority('support:manage')")
    void operate();
}

public interface AuditApi {
    @PreAuthorize("hasAuthority('audit:manage')")
    void operate();
}

@Service
public class OperationsService implements SupportApi, AuditApi {
    @Override
    public void operate() {
        // Business logic
    }
}
~~~

One concrete method `operate()` inherits `@PreAuthorize` from **two different interfaces**. Spring Security documentation explicitly notes that this case has **no single unique resolution**, so the application can **fail at startup** while resolving method-security metadata.

Do not:

- Rely on the order of `implements SupportApi, AuditApi` to pick one.
- Rely on the order reflection returns interfaces.
- Expect the framework to automatically combine two `@PreAuthorize` annotations with AND.
- Hit a startup error and arbitrarily remove the security annotation from one interface.

### 8.1. Resolving with an Explicit Annotation on the Implementation Method

If both permissions are truly required:

~~~java
@Service
public class OperationsService implements SupportApi, AuditApi {

    @Override
    @PreAuthorize(
        "hasAuthority('support:manage') " +
        "and hasAuthority('audit:manage')"
    )
    public void operate() {
        // Executes only when both conditions are met.
    }
}
~~~

If only one permission fits the implementation's responsibility, the concrete method must declare **the appropriate policy** with an explanation. Adding an annotation on the concrete method resolves **ambiguity**; it does not by itself guarantee the chosen policy is strict enough.

### 8.2. Only One Interface Declares an Annotation

When an implementation has multiple interfaces and only **one** interface carries `@PreAuthorize` for that method, there may be no same-type conflict. Even so, always test the method through the Spring bean because other metadata sources such as superclasses or meta-annotations can interact.

### 8.3. What If Both Interfaces Carry Identical Expressions?

Do not treat duplicating annotations as a safe convention. Documentation warns that inheriting annotations from two interfaces is ambiguous; the configuration should be made explicit on the concrete method, or refactored so only one authoritative security contract exists.

## 9. Multiple Different Annotation Types: Chained Processing, Typically Combined Like AND

Consider:

~~~java
@PreAuthorize("hasAuthority('document:read')")
@PostAuthorize("returnObject.owner == authentication.name")
public Document readDocument(long id) {
    return repository.findById(id).orElseThrow();
}
~~~

Two different annotation types on the same method do not duplicate the same interceptor:

1. `@PreAuthorize` is evaluated **before** the method body, checking the permission.
2. If passed, the method reads the data.
3. `@PostAuthorize` is evaluated **after** the method body, requiring the returned document to belong to the caller.
4. The caller receives the result only if all required checks pass.

Per the documentation, multiple different method-security annotations are processed **sequentially** through their interceptors and can be viewed as requirements that must all be satisfied. However, their execution timing differs; `@PostAuthorize` can deny **after the method has already run**, unlike `@PreAuthorize`.

### 9.1. Do Not Repeat the Same `@PreAuthorize` Type on One Method

Invalid:

~~~java
// NOT ALLOWED:
@PreAuthorize("hasRole('ADMIN')")
@PreAuthorize("hasAuthority('document:delete')")
public void delete(long id) { }
~~~

Spring Security does not support repeating the same method-security annotation on one method this way. Combine the conditions:

~~~java
@PreAuthorize(
    "hasRole('ADMIN') and hasAuthority('document:delete')"
)
public void delete(long id) { }
~~~

Or invoke a policy bean. Do not create two meta-annotations both hiding `@PreAuthorize` expecting them to merge without confirming support; standardize on **one clear policy** to prevent conflicts.

### 9.2. Same-Type Inheritance Differs from Cross-Type Combination

- `@PreAuthorize` on a method can override `@PreAuthorize` on a class.
- `@PreAuthorize` paired with `@PostAuthorize` represents **two evaluation stages**.
- `@Secured`, `@RolesAllowed`, and `@PreAuthorize` belong to separate interceptor systems when enabled.
- Never use JSR-250 `@PermitAll` to "disable" an active `@PreAuthorize`. Verify the entire configuration; annotations of different families do not automatically override one another.
- If multiple annotation types affect one call, test all cases where their intents disagree, e.g., JSR-250 permits while SpEL denies.

### 9.3. `@PostAuthorize` Is Unsuitable for Protecting Side-Effecting Writes

Do not rely on:

~~~java
@PostAuthorize("hasRole('ADMIN')")
public void transferMoney() {
    // Modifies database / sends message here.
}
~~~

to prevent money from being transferred, because the method body may have already executed side effects before post-authorization runs. For write operations, use `@PreAuthorize` and service policies checking **before state changes**. If transaction rollback or post-check policies are needed, explicitly design transaction/advisor ordering rather than assuming a late exception automatically undoes all side effects.

## 10. Meta-Annotations: Defining Security Contracts in Business Language

When multiple methods need the same expression, you can define a composed annotation:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.security.access.prepost.PreAuthorize;

@Target({ElementType.METHOD, ElementType.TYPE})
@Retention(RetentionPolicy.RUNTIME)
@PreAuthorize("hasAuthority('document:read')")
public @interface CanReadDocument {
}
~~~

Usage:

~~~java
@Service
public class DocumentSearchService {

    @CanReadDocument
    public String search(String term) {
        return term;
    }
}
~~~

Benefits: clear business meaning, less SpEL copy-paste. Spring Security supports discovering meta-annotations in method-security pointcuts.

### 10.1. `@Target` and `@Retention` Are Contracts

- `@Target(METHOD)` if allowed only on methods.
- `@Target(TYPE)` if allowed on classes/interfaces.
- Both `METHOD` and `TYPE` can be selected to support both.
- `@Retention(RUNTIME)` is required so runtime infrastructure can find the annotation.
- Meta-annotations need clear authentication/authorization semantics in `@PreAuthorize`; never trust inputs by default.
- When changing a meta-annotation's expression, **every usage site** can change permissions, requiring regression tests.

### 10.2. Multi-Layer Meta-Annotations Still Require Checking Conflicts

Suppose a class has:

~~~java
@CanReadDocument
public class DocumentService { }

~~~

and a method has `@PreAuthorize("hasRole('ADMIN')")`. Since both resolve to `@PreAuthorize`, verify actual precedence and policy with integration tests; do not assume a type-level annotation always adds an extra requirement. Use one consistent model: class-level baseline + explicit method exceptions, or a policy bean.

### 10.3. Parameterized Meta-Annotations

Spring Security also supports expressing parameters in composed annotations depending on version (e.g., `@HasRole("ADMIN")`). When creating parameterized annotations, pay attention to SpEL quoting, Java annotation values, and injection/escaping risks. If dynamic expressions are complex or resource-dependent, a policy bean is easier to test.

## 11. Proxies, Self-Invocation, and Why Annotations "Exist Yet Do Not Run"

A classic vulnerability example:

~~~java
@Service
public class ExportService {

    public void exportFromController() {
        exportSensitiveData();
    }

    @PreAuthorize("hasAuthority('pii:export')")
    public void exportSensitiveData() {
        // Exports sensitive data.
    }
}
~~~

The controller calls `exportFromController()` through the Spring proxy. Since this method has no rule, it enters. Inside, `this.exportSensitiveData()` is **self-invocation** and usually does not go through the proxy, so `@PreAuthorize` on `exportSensitiveData()` may **not execute**.

This is not an annotation inheritance bug; it is a limitation of the interception mechanism.

### 11.1. Intentional Fix

Extract the protected operation into **another Spring-managed bean**:

~~~java
@Service
public class ProtectedExportService {

    @PreAuthorize("hasAuthority('pii:export')")
    public void exportSensitiveData() {
        // Performs PII export.
    }
}

@Service
public class ExportOrchestrator {
    private final ProtectedExportService protectedService;

    public ExportOrchestrator(ProtectedExportService protectedService) {
        this.protectedService = protectedService;
    }

    public void export() {
        protectedService.exportSensitiveData();
    }
}
~~~

The caller passes through `ProtectedExportService`'s proxy, giving the interceptor a chance to run. Real tests are still needed to ensure the bean is right, the method is interceptable, and there is no backdoor calling the implementation directly.

### 11.2. Related Proxy Pitfalls

| Situation | Key Takeaway |
|---|---|
| Caller instantiates object with `new` | No Spring proxy; method security does not run automatically |
| `this.securedMethod()` | Bypasses proxy in standard AOP proxy mode |
| JDK dynamic proxy | Typically proxies interface methods; check interfaces and injection types |
| Class-based/CGLIB proxy | Relies on overridable methods; final/private methods are not proxied like public overridable methods |
| `private` method | Cannot be protected solely by standard proxy-based advice |
| `final` method / `final` class | Has limitations with subclass-based proxies; check proxy strategy |
| Kotlin classes/methods `final` by default | Require `open` configuration or an appropriate proxy strategy |
| Interface `default` method | Never rely on assumptions; test proxy mode/version and call paths |
| Overloaded / generic / bridge methods | Verify metadata resolution and exact signatures |
| Interface annotations in AspectJ mode | Differs from proxy mode; check Java/AspectJ inheritance rules |

**AspectJ warning:** Spring Security documentation emphasizes that Java annotations on interfaces **are not inherited under Java rules**, and AspectJ weaving follows those rules. If using `@EnableMethodSecurity(mode = AdviceMode.ASPECTJ)`, do not assume interface annotations behave identically to Spring proxy mode. Place annotations appropriately on classes/concrete methods and test under real weaving.

### 11.3. AOP Proxies Are Not Object-Level Authorization

Even when the interceptor runs and `hasAuthority('document:read')` passes, the caller might still request a document belonging to another tenant. Use a resource policy:

~~~java
@PreAuthorize(
    "hasAuthority('document:read') " +
    "and @documentPolicy.canRead(authentication, #documentId)"
)
public DocumentDto read(long documentId) {
    return repository.findVisible(documentId);
}
~~~

This snippet depends on the application. `documentPolicy` must check permissions on a trustworthy record, never relying on client-asserted IDs or `tenantId`s.

## 12. Parameter Names in SpEL When Annotations Live on Interfaces

An interface has:

~~~java
public interface DocumentApi {
    @PreAuthorize(
        "hasAuthority('document:read') and " +
        "@documentPolicy.canRead(authentication, #documentId)"
    )
    DocumentDto read(long documentId);
}
~~~

`#documentId` works only if the expression infrastructure can **discover the exact parameter name**. For interfaces, bytecode does not carry local-variable debug information the same way concrete methods do that Spring can always rely on.

Spring Security documentation describes several mechanisms:

1. Spring Security's `@P("documentId")` to declare the name via annotation.
2. `@Param` in compatible setups.
3. Compiling Java with `-parameters` to emit parameter-name metadata.
4. Debug symbols on concrete classes (insufficient for interface methods when relying solely on debug metadata).

Explicit example on an interface:

~~~java
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;

public interface DocumentApi {

    @PreAuthorize(
        "hasAuthority('document:read') and " +
        "@documentPolicy.canRead(authentication, #documentId)"
    )
    DocumentDto read(@P("documentId") long documentId);
}
~~~

The snippet depends on a real `documentPolicy` bean and `DocumentDto` type. In Maven/Gradle builds, enable compiler parameter metadata when using named SpEL parameters. Test with **the actual interface bean** and real parameter data, not just parameterless expressions.

## 13. Do `@Secured`, `@RolesAllowed`, `@PermitAll`, and `@DenyAll` "Inherit" Similarly?

When enabled, Spring Security also supports `@Secured` and JSR-250 annotations on classes/interfaces/methods. However, each group has its own interceptor/semantics:

~~~java
// Effective only when @EnableMethodSecurity(securedEnabled = true).
@Secured("ROLE_ADMIN")
public void manageUsers() { }
~~~

~~~java
// Effective only when @EnableMethodSecurity(jsr250Enabled = true).
@RolesAllowed("ADMIN")
public void manageUsers() { }
~~~

The examples above are two **separate alternatives**, not guidance to put both on the same method. For `@RolesAllowed`, role-prefix interpretation and version/config behavior must be tested. JSR-250 `@PermitAll` and `@DenyAll` **are not** HTTP-layer `requestMatchers(...).permitAll()/denyAll()`.

### 13.1. Do Not Mix Annotation Types to Create Unclear "Exceptions"

For example, class has `@PreAuthorize("hasRole('ADMIN')")` and method has `@PermitAll`:

~~~java
@PreAuthorize("hasRole('ADMIN')")
class AdministrativeService {

    @PermitAll
    public String status() { return "ok"; }
}
~~~

If the relevant interceptors are both enabled, you must not assume `@PermitAll` cancels the `@PreAuthorize` check: they are **two different annotation families**, with no same-type `@PreAuthorize` class-vs-method override rule.

If an exception is genuinely wanted, use an explicit `@PreAuthorize` on the method in the same family as the baseline:

~~~java
@PreAuthorize("permitAll()")
public String status() { return "ok"; }
~~~

and verify other policies still run as designed. Avoid annotation conflicts or splitting permission semantics across three mechanisms.

## 14. Behavior-Based Testing: The Only Way to Verify Effective Inheritance

If code only checks Java reflection:

~~~java
assertNull(
    Implementation.class.getMethod("read")
        .getDeclaredAnnotation(PreAuthorize.class)
);
~~~

that does not tell you whether Spring AOP picks up the annotation from the interface. Conversely, checking that an annotation exists is not enough because the bean might not be proxied.

A proper test suite needs:

- `@EnableMethodSecurity` active in the Spring context.
- Beans retrieved via `@Autowired`, never instantiated with `new`.
- Methods invoked from tests through the bean/proxy.
- `SecurityContext` populated via `@WithMockUser` or an appropriate authentication strategy.
- **Allowed** and **denied** tests, especially regular user vs admin roles.
- Behavior tests when class-level rules are overridden by method-level rules.
- Interface-level contract tests.
- Two-interface conflict tests via startup/context tests.
- Tests confirming self-invocation is prevented via refactoring where applicable.
- Object-level tenant/owner tests.

### 14.1. JUnit 5 + Spring Security Test Template

Assuming a `CatalogService` bean exists:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class CatalogMethodSecurityTest {

    @Autowired
    CatalogService catalogService;

    @Test
    @WithMockUser(roles = "USER")
    void userMayList() {
        assertEquals("list", catalogService.list());
    }

    @Test
    @WithMockUser(roles = "USER")
    void userMayNotDelete() {
        assertThrows(AccessDeniedException.class,
                () -> catalogService.delete(7));
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminMayDeleteUsingMethodRule() {
        assertEquals("delete-7", catalogService.delete(7));
    }
}
~~~

**Conditions for the test to truly be valid:** `CatalogService` must be a real Spring bean returning the values from the example with `@EnableMethodSecurity` enabled. `@WithMockUser` requires `spring-security-test`. In a default setup **without a role hierarchy** making ADMIN imply USER, ADMIN is still allowed to delete because method-level `@PreAuthorize` overrides class-level, without assuming ADMIN also holds `ROLE_USER`.

This test illustrates a **potentially counterintuitive result**: changing a method's annotation can drop the class's USER baseline role.

### 14.2. Testing Interface Methods

With `DocumentReader` carrying `@PreAuthorize("hasAuthority('document:read')")` and Spring-managed `DefaultDocumentReader`:

~~~java
@SpringBootTest
class DocumentInterfaceSecurityTest {

    @Autowired
    DocumentReader reader;

    @Test
    @WithMockUser(authorities = "document:read")
    void readerMayRead() {
        assertEquals("document-9", reader.read(9));
    }

    @Test
    @WithMockUser(authorities = "document:write")
    void writerWithoutReadIsDenied() {
        assertThrows(AccessDeniedException.class,
                () -> reader.read(9));
    }
}
~~~

This snippet assumes the same test imports as the previous example and a real bean implementation, not a standalone Java file. **Do not grant `document:read` in the deny test**; the test must prove the interface annotation is enforced by Spring.

### 14.3. Testing Interface Conflicts

The case `OperationsService implements SupportApi, AuditApi` without annotating the concrete method should be tested in a **Spring `ApplicationContext` test**. According to Spring Security documentation, inheriting two same-type annotations from two interfaces causes ambiguity and can fail startup. A proper context test asserts startup failure related to method-security metadata. After adding a specific annotation on `OperationsService.operate()`, the context must boot and allow/deny tests must match the new policy.

Do not leave a class **intentionally causing startup failure** in the application's main component scan just for illustration: it can prevent the whole app from booting. Isolate it in a dedicated test fixture/context.

### 14.4. Testing Interface Annotations Under Real Proxy Modes

If switching `proxyTargetClass`, changing from JDK proxies to class proxies, using AspectJ weaving, or upgrading Spring versions, re-run the tests. A test calling an implementation class created via `new` cannot replace tests on a Spring-managed proxy.

## 15. Standalone Java 17: Simulating Lookup, Override, and Conflict

The following program **does not use Spring Security**. It simulates useful learning rules: method annotations take precedence over class annotations, interface method annotations are searched separately, and two interfaces carrying annotations cause ambiguity. Java reflection here deliberately shows that an interface annotation **does not automatically appear as a declared annotation on the implementation method**.

**Warning:** This is only a simplified demo algorithm, not Spring Security's real resolver/pointcut. It does not simulate multi-level superclasses, composed annotations, bridge methods, proxies, AspectJ, or authentication. Real Spring tests from earlier sections are required to confirm behavior.

Create `MethodAnnotationDemo.java`:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;

public class MethodAnnotationDemo {

    @Target({ElementType.TYPE, ElementType.METHOD})
    @Retention(RetentionPolicy.RUNTIME)
    @interface Gate { String value(); }

    @Gate("ROLE_USER")
    static class CatalogService {
        public String list() { return "list"; }
        @Gate("ROLE_ADMIN")
        public String delete() { return "delete"; }
    }

    interface ReaderApi {
        @Gate("document:read")
        String read();
    }

    static class ReaderService implements ReaderApi {
        public String read() { return "read"; }
    }

    interface SupportApi {
        @Gate("support:manage")
        String operate();
    }

    interface AuditApi {
        @Gate("audit:manage")
        String operate();
    }

    static class AmbiguousService implements SupportApi, AuditApi {
        public String operate() { return "operate"; }
    }

    static class ResolvedService implements SupportApi, AuditApi {
        @Gate("ops:approved")
        public String operate() { return "operate"; }
    }

    static String decide(Class<?> impl, String methodName) throws Exception {
        Method method = impl.getMethod(methodName);
        Gate methodRule = method.getDeclaredAnnotation(Gate.class);
        if (methodRule != null) return methodRule.value();

        Gate classRule = impl.getDeclaredAnnotation(Gate.class);
        if (classRule != null) return classRule.value();

        List<String> found = new ArrayList<>();
        for (Class<?> iface : impl.getInterfaces()) {
            try {
                Method interfaceMethod = iface.getMethod(methodName);
                Gate interfaceRule = interfaceMethod.getAnnotation(Gate.class);
                if (interfaceRule != null) found.add(interfaceRule.value());
                else {
                    Gate interfaceTypeRule = iface.getAnnotation(Gate.class);
                    if (interfaceTypeRule != null) found.add(interfaceTypeRule.value());
                }
            } catch (NoSuchMethodException ignored) {
                // This interface does not declare the requested method.
            }
        }
        if (found.size() > 1) {
            return "AMBIGUOUS(" + String.join(",", found) + ")";
        }
        return found.isEmpty() ? "NO_RULE" : found.get(0);
    }

    public static void main(String[] args) throws Exception {
        System.out.println("catalog list: " +
                decide(CatalogService.class, "list"));
        System.out.println("catalog delete: " +
                decide(CatalogService.class, "delete"));
        System.out.println("reader read: " +
                decide(ReaderService.class, "read"));
        System.out.println("ambiguous operate: " +
                decide(AmbiguousService.class, "operate"));
        System.out.println("resolved operate: " +
                decide(ResolvedService.class, "operate"));
        System.out.println("interface reflected on implementation: " +
                (ReaderService.class.getMethod("read")
                    .getDeclaredAnnotation(Gate.class) != null));
    }
}
~~~

Run with **Java 17 or newer**:

~~~bash
javac --release 17 MethodAnnotationDemo.java
java MethodAnnotationDemo
~~~

Exact output:

~~~text
catalog list: ROLE_USER
catalog delete: ROLE_ADMIN
reader read: document:read
ambiguous operate: AMBIGUOUS(support:manage,audit:manage)
resolved operate: ops:approved
interface reflected on implementation: false
~~~

Line-by-line analysis:

- `catalog list`: method has no `@Gate`, so the demo finds the class annotation.
- `catalog delete`: method has `@Gate("ROLE_ADMIN")`, overriding the class value `ROLE_USER`.
- `reader read`: implementation method is unannotated; the demo inspects the interface declaration.
- `ambiguous operate`: two interfaces supply two different values; the demo refuses to pick one.
- `resolved operate`: concrete method annotates an explicit policy.
- `interface reflected on implementation: false`: Java reflection `getDeclaredAnnotation` on the implementation method does not automatically see the interface annotation.

**Do not infer from the demo that Spring prints the same `"AMBIGUOUS"` string**: Spring Security can cause **`ApplicationContext` startup to fail** when detecting metadata conflicts. The demo simply returns a label so it can run and teach the logic.

### 15.1. Extension Exercises

1. Add a `@Gate("PUBLIC")` method to a class with class-level `ROLE_ADMIN`. Observe the method "overriding" the baseline.
2. Add a third interface without `@Gate` and check that the demo still picks the one annotated interface.
3. Add superclass traversal with a `visited` set to avoid duplicate traversal.
4. Replace the "method > class > interface" assumption with a real Spring test configuration; compare similarities and differences.
5. Put `@PreAuthorize("hasAuthority('document:read')")` on an interface in a Spring Boot test, then invoke through `@Autowired DocumentReader` with two users.

## 16. Advisor Ordering, Transactions, and Combining Multiple Annotations

Method security uses AOP interceptors before/after methods, rather than "scanning annotations and running once at startup":

~~~text
proxy invocation
    |
    +--> @PreFilter (if present)
    +--> @PreAuthorize: required before calling method
    +--> @Secured / JSR-250 (if enabled and present)
    |
    v
    method body
    |
    +--> @PostAuthorize: required after method returns
    +--> @PostFilter (if present)
    |
    v
result / AccessDeniedException
~~~

**This diagram is a logical simplification**, not a guarantee of exact ordering for every advisor. Interceptors have order constants and can interact with transactions, caching, metrics, and custom AOP advice. Spring Security allows configuring ordering via `@EnableMethodSecurity` and advisor registrations where appropriate.

Core takeaways for this topic:

- Annotations of **different types** have separate interceptors and are evaluated in stages.
- Annotations of **the same type across hierarchy levels** must resolve consistently, rather than all running automatically.
- `@PostAuthorize` runs after the method and does not guarantee undoing all side effects.
- Interception may not run at all if the caller bypasses the proxy, even if annotations exist on methods, classes, and interfaces.
- Switching to AspectJ mode changes how weaving and inheritance work; test thoroughly.

## 17. Common Mistakes and Fixes

| Mistake | Risk | Fix |
|---|---|---|
| Forgetting `@EnableMethodSecurity` | Annotations are unused | Enable config, test denial |
| Class has `@PreAuthorize("hasRole('USER')")`, method writes `@PreAuthorize("hasRole('ADMIN')")` assuming AND | Misunderstood override | State all required conditions explicitly in the method |
| Class-level method accidentally annotated `permitAll()` | Widens permissions unexpectedly | Security review on every method exception |
| Annotation only on interface, yet object created with `new` | No AOP proxy | Obtain Spring bean via DI |
| Two interfaces both annotate the method | Ambiguous metadata/startup failure | Place one explicit annotation on the concrete method |
| Relying on `implements` order to pick an interface | Rule undefined by intent | Resolve explicitly, test |
| Using Java `@Inherited` to infer interface method authorization | Reflection differs from Spring resolver | Spring integration tests |
| Self-invoking `this.securedMethod()` | Bypasses proxy-based interception | Split service or change architecture |
| Using final/private methods with class-based proxy | Advice cannot intercept | Public overridable methods through proxy, test |
| Switching to AspectJ while keeping interface-only annotations | Java/AspectJ inheritance differs | Annotate concrete methods/classes and test weaving |
| Repeating two `@PreAuthorize` on a method | Not supported | Combine SpEL with AND/OR |
| Mixing `@PermitAll` and `@PreAuthorize` to "override" | Different interceptor families may conflict | Use consistent policies and test |
| `@PostAuthorize` protecting write operations | Side effects happen before check | `@PreAuthorize` for writes |
| Interface SpEL uses `#id` without parameter metadata | Expression fails or cannot evaluate | `@P` or `-parameters`, test |
| Meta-annotation with wrong `@Retention` | Runtime infrastructure misses metadata | Proper `RUNTIME` and `@Target` |
| Checking only `getDeclaredAnnotation` | Misses class/interface/meta annotations | Test through Spring proxy |
| Checking only HTTP authorization | Schedulers/other entrypoints slip through | Policy service + method security |
| Checking only role without resource permission | IDOR/BOLA | Owner/tenant/object policies |
| Testing only admin success | Missed overly permissive rules | Negative tests with normal users, anonymous |

## 18. Checklist When Designing Multi-Level Annotations

- [ ] Is method security enabled in the right Spring context?
- [ ] Did you pick **one authoritative place** for policies: class/interface defaults or concrete methods?
- [ ] Does any same-type method-level annotation weaken a class/interface baseline?
- [ ] Have you inspected all interface contracts the service implements, including library-provided interfaces?
- [ ] Do two interfaces both declare `@PreAuthorize` for one signature? Resolved explicitly?
- [ ] Do composed annotations have proper `@Retention(RUNTIME)`, `@Target`, and no conflicts?
- [ ] Do multiple different annotation types need to run together? Tested AND/denial semantics?
- [ ] Are there no repeated `@PreAuthorize` annotations on the same method?
- [ ] Is the method invoked through a bean proxy without self-invocation, `new`, or private/final bypasses?
- [ ] Does the proxy strategy (JDK/CGLIB/AspectJ) match annotation placement?
- [ ] Are interface SpEL parameter names available via `@P`/`-parameters`?
- [ ] For `@PostAuthorize`, does the method avoid side effects before authorization succeeds?
- [ ] Are there allow + deny tests when a user passes the class rule but fails the method rule?
- [ ] Are there interface-contract tests when the implementation does not repeat the annotation?
- [ ] Are there startup-failure tests when multiple interfaces conflict?
- [ ] Are HTTP, schedulers, and other entry points invoking critical use cases tested?
- [ ] Are owner/tenant/resource policies and auditing present, not just role strings?
- [ ] Are regression tests run when refactoring interfaces, superclasses, overrides, or proxy modes?

**Practical rule:** *State explicitly at which level policies live, use concrete methods to resolve exceptions and ambiguities, and prove it by calling through the Spring proxy.*

## 19. Self-Check Questions

**1. Class has `@PreAuthorize("hasRole('USER')")`, method has `@PreAuthorize("hasRole('ADMIN')")`. Does the method require both roles?**  
Not by default. For same-type annotations, method-level overrides class-level; to require both, write a combined expression.

**2. An implementation has no annotation, while the interface method has `@PreAuthorize`. Can it still be protected?**  
Yes, in compatible Spring proxy-based method security, because the resolver searches annotations across the hierarchy. Method security must be enabled, calls must go through the bean/proxy, and you must test it.

**3. Does Java's `@Inherited` automatically copy annotations from an interface method to the implementation?**  
No. Java reflection inheritance and Spring method-security hierarchy resolution are different.

**4. Two interfaces annotate a method with different `@PreAuthorize` rules; does Spring pick the first declared interface?**  
No. That is ambiguous metadata that can cause startup failure; annotate the concrete method explicitly to resolve it.

**5. Are `@PreAuthorize` and `@PostAuthorize` on the same method a duplicate of the same type?**  
No, they are two distinct annotation types with different before and after interceptors; both conditions must be satisfied.

**6. Can you place two `@PreAuthorize` annotations on one method expecting AND?**  
Not supported; combine conditions in one annotation or a policy bean.

**7. Why is `@PostAuthorize` not the default choice for protecting deletes/updates?**  
Because the method body may have already caused side effects before post-authorization checks.

**8. Why can a `@PreAuthorize` method still be called unlawfully via `this.method()`?**  
In proxy mode, self-invocation does not pass through the proxy, so the interceptor can be bypassed.

**9. Are interface annotations in AspectJ mode inherited the same way as proxy mode?**  
Do not assume so; AspectJ follows Java rules for annotations on interfaces. Place annotations appropriately and test weaving.

**10. If reflection on the implementation method returns null, does that prove Spring does not protect the method?**  
No. Spring can find the annotation on the class/interface/superclass/meta-annotation. Test through the Spring proxy.

**11. If `@PreAuthorize` is on the class and `@PermitAll` is on the method, does `@PermitAll` cancel the class-level check?**  
Do not assume so. They belong to two different annotation families/interceptors; enabled flags and active policies still apply.

**12. Can someone with `document:read` read every document of every tenant?**  
No. Function-level annotations must be paired with object-level authorization on real resources.

## 20. Official Documentation

- Spring Security – **Method Security** (class/interface annotations; method-level overrides; multiple interface conflicts; meta annotations; multiple annotations and repetition): https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security – **Method Security** version 7.0 (check when upgrading versions): https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/method-security.html
- Spring Security – **Authorization Architecture** (`AuthorizationManager` and `GrantedAuthority`): https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Framework – **Proxying Mechanisms** (self-invocation, JDK proxies, and CGLIB): https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Security – **Testing Method Security**: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Java SE 17 – **@Inherited JavaDoc**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Inherited.html
