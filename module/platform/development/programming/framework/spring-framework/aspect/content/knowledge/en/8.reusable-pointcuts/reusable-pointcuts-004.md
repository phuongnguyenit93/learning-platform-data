# Pointcut Method Visibility and Reuse Scope in Spring AOP

## 1. Objective of this lesson

In Spring AOP using the `@AspectJ` syntax, you can name a pointcut expression using a `@Pointcut` method and then reference it from other advice. The pointcut method can be declared `private`, package-private, `protected`, or `public`.

**Two issues that must be strictly distinguished:**

1. **The visibility of the method declaring the named pointcut** determines **where other pointcut expressions are allowed to reference this name**, following Java access rules.
2. **The scope of methods matched by the pointcut** is determined by **the expression inside `@Pointcut("...")`**; `private`/`public` on the method **declaring the pointcut** does not by itself alter which target methods get advised.

Example:

```java
@Aspect
public class TraceAspect {
    @Pointcut("execution(public * com.example.orders..*Service.*(..))")
    private void publicServiceOperations() { }

    @Before("publicServiceOperations()")
    public void beforeService() {
        // Advice applied to public service methods invoked through the proxy.
    }
}
```

The pointcut method `publicServiceOperations()` is **`private`**, yet the expression `execution(public * ...)` can still match **public methods of Spring service beans**. Here, `private` **does not mean "only intercept private methods"**.

Similarly, a `@Pointcut` method declared `public` does not automatically intercept all public target methods. The matched method set still depends on the pointcut expression itself.

**Content scope:** how Spring Framework organizes and reuses named pointcuts, Java visibility, Spring proxy boundaries, and verification using a Spring `ApplicationContext`. This is not a lesson on AspectJ weaving or general Java accessibility.

## 2. How is a named pointcut structured in Spring?

A named pointcut consists of a **method signature** (name, binding parameters, Java visibility, `void` return type) and an **expression in `@Pointcut`**. Spring reads the annotation metadata and resolves references such as `@Before("serviceMethods()")`; the method body is usually left empty and is not a business execution callback.

For example, `@Pointcut("execution(public * com.example..*Service.*(..))") private void serviceMethods() {}` has a *private declaration* while its expression selects *public target methods*. This distinction needs to be verified when sharing names across different access scopes.

## 3. Visibility and reference scope matrix

| Visibility of `@Pointcut` method | Who can reference the named pointcut? | When to use in Spring AOP |
| --- | --- | --- |
| `private` | Advice/pointcut declarations in the **same declaring type** | Encapsulating a predicate meant for a single aspect; preventing other aspects from depending on implementation details. |
| Package-private (no modifier) | Code declarations in the **same Java package** under visibility rules | Grouping several aspects in the same package with internal conventions; less suitable if packages change frequently. |
| `protected` | Declaring type, code in the same package, and hierarchy/subclasses under `protected` rules | Intentionally sharing pointcuts across an aspect/class hierarchy; requires verifying inheritance context and resolution. |
| `public` | Anywhere the **declaring class/method is accessible**, including other packages | Shared named pointcuts across multiple aspects and modules; creating a stable pointcut API. |

**Rule from Spring Framework:** when referencing a pointcut **by name**, standard Java visibility rules apply. Visibility **does not affect pointcut matching**.

A few additional conditions to note:

1. If the class containing the pointcut is package-private, making the method `public` **does not automatically make the declaring class a public API** for other packages.
2. `protected` does not mean "any aspect can use it"; especially outside the package, valid inheritance/access relationships must be checked, not just the `protected` keyword.
3. `private` **does not allow another aspect to reference that name** merely because they share the same Spring context. The Spring container does not bypass Java visibility to turn a private named pointcut into a shared API.
4. An aspect can use **multiple private named pointcuts** to build a complex expression internally, and then expose **a single public named pointcut** if sharing is needed.
5. Visibility is not an authorization/security measure for target methods. It controls **reuse of the definition name**, not a caller's permission to execute a Spring service.

## 4. Private pointcut: reusing within a single aspect

```java
package com.example.orders.aop;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.aspectj.lang.annotation.Pointcut;

@Aspect
public class OrderAuditAspect {
    @Pointcut("execution(public * com.example.orders..*Service.*(..))")
    private void orderServiceOperations() {}

    @Pointcut("execution(* com.example.orders..*Service.submit(..))")
    private void submitOperations() {}

    @Before("orderServiceOperations() && submitOperations()")
    public void beforeSubmit() {
        System.out.println("audit:submit");
    }
}
```

This is an **illustrative snippet**, requiring corresponding Spring services and Spring AOP infrastructure to run. It shows:

- `orderServiceOperations()` and `submitOperations()` are **two private named pointcuts**.
- `beforeSubmit()` in the **same class** can reference both and combine them with `&&`.
- `private` keeps internal rules from accidentally becoming a public contract for other modules.
- Even though the pointcut is private, `@Before` can still advise a `public submit(..)` on another bean when the method call goes through a Spring proxy.

If a second aspect wants to reuse `orderServiceOperations()`, it **must not** reference `com.example.orders.aop.OrderAuditAspect.orderServiceOperations()` because the declaration is private. When reuse is genuinely needed, **publish an appropriate pointcut** or move the shared predicate into a dedicated pointcut-definition class.

### When is `private` a good default?

- The predicate is meaningful only within a single aspect.
- The pointcut name is tied to local implementation and may change frequently.
- You do not want another module to accidentally couple to expression details.
- Multiple advice methods in the **same aspect** need to reuse the expression or combine with `&&`, `||`, `!`.

Do not make every pointcut public just "in case of future use". Narrow visibility helps maintainers tell what is an implementation detail.

## 5. Public pointcut: sharing across aspects with CommonPointcuts

When multiple aspects target methods in the **service layer**, Spring Framework recommends defining **named pointcut expressions in a shared class**.

```java
package com.example.orders.aop;

import org.aspectj.lang.annotation.Pointcut;

public class CommonPointcuts {
    @Pointcut("execution(public * com.example.orders..*Service.*(..))")
    public void serviceOperations() {}

    @Pointcut("execution(* com.example.orders..*Service.submit(..))")
    public void submitOperations() {}
}
```

This is **a class holding pointcut definitions**, containing no advice. Following the `CommonPointcuts` pattern in Spring Framework documentation, this class **does not need `@Aspect` or its own Spring bean** just for other pointcut expressions to reference `@Pointcut` methods by their fully qualified name.

One aspect can reference it:

```java
@Aspect
public class AuditAspect {
    @Before("com.example.orders.aop.CommonPointcuts.serviceOperations()")
    public void beforeService() {
        // ...
    }
}
```

Another aspect can use that same named pointcut:

```java
@Aspect
public class MetricsAspect {
    @Before("com.example.orders.aop.CommonPointcuts.serviceOperations()")
    public void recordInvocation() {
        // ...
    }
}
```

The snippets above **only illustrate reuse**, not a full runnable project. Both aspect classes **must be Spring beans** (for example `@Aspect` + `@Component` with component scanning, or `@Bean` in configuration) for advice to operate.

**There is no need to copy the literal `execution(...)` string to every aspect.** If the service package changes, update the expression in one place in `CommonPointcuts`; valid references will use the new expression when Spring builds advisors.

### Reference syntax in the same class vs in another class

| Usage location | Syntax | Conditions |
| --- | --- | --- |
| Advice in the same declaring type | `@Before("serviceOperations()")` | The named pointcut may be `private`, package-private, `protected`, or `public`. |
| Another aspect referencing a public pointcut | `@Before("com.example.orders.aop.CommonPointcuts.serviceOperations()")` | Declaring class and method have valid visibility, class is on the classpath, exact name. |
| From another pointcut, combining two public declarations | `@Pointcut("com.example.orders.aop.CommonPointcuts.serviceOperations() && execution(* *.submit(..))")` | Each referenced name resolves, valid syntax; scope should be constrained to avoid overly broad matching. |
| Using a private name of another aspect | `@Before("OtherAspect.privatePointcut()")` | **Invalid** under visibility rules; not made public merely by being in the same Spring context. |

When refactoring packages or renaming `CommonPointcuts` classes/methods, references by fully qualified name can break when Spring parses advisors. Therefore, treat public named pointcuts as an **AOP configuration API that needs testing**, not merely meaningless string literals.

## 6. Standalone Spring Framework demo: private pointcut and public pointcut applied to a service

This demo clearly verifies both scopes:

- `TraceAspect` holds a **private named pointcut** `processOnly()` used only inside that aspect.
- `PointcutCatalog` exposes a **public named pointcut** `serviceCalls()`; `AuditAspect` in another class uses it by fully qualified name.
- **One Spring service bean** has two public methods. `process(..)` matches both expressions; `inspect()` matches only the shared public pointcut. Results are printed via counters after all calls finish so they do not depend on advice execution order.

Environment: **Java 17+**, **Spring Framework 6.2.19**, **AspectJ Weaver 1.9.25.1**, Gradle with the `application` plugin. This is plain Spring Framework without Boot AOP auto-configuration.

### 6.1. Project structure

```text
named-pointcut-visibility/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/visibility/
    ├── Main.java
    ├── AppConfig.java
    ├── OrderService.java
    ├── PointcutCatalog.java
    ├── AuditAspect.java
    └── TraceAspect.java
```

**`settings.gradle`**

```gradle
rootProject.name = 'named-pointcut-visibility'
```

**`build.gradle`**

```gradle
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
    implementation 'org.springframework:spring-aop:6.2.19'
    implementation 'org.aspectj:aspectjweaver:1.9.25.1'
}

application {
    mainClass = 'com.example.visibility.Main'
}
```

These versions are declared for the standalone demo. When applying to Spring Boot, use the BOM/dependency management of your project's Boot version instead of mixing arbitrary Spring module versions.

### 6.2. Target bean with two methods

**`OrderService.java`**

```java
package com.example.visibility;

public class OrderService {
    public String process(String id) {
        return "processed:" + id;
    }

    public String inspect() {
        return "inspected";
    }
}
```

Both methods are public/non-final. The class name ends with `Service` to match the `*Service` expression of the common pointcut.

### 6.3. Class holding the shared public pointcut

**`PointcutCatalog.java`**

```java
package com.example.visibility;

import org.aspectj.lang.annotation.Pointcut;

public class PointcutCatalog {
    @Pointcut(
        "execution(public * com.example.visibility..*Service.*(..))"
    )
    public void serviceCalls() {}
}
```

This class has **no `@Aspect`, no `@Component`, and no `@Bean`**, strictly serving the role of **defining a public named pointcut**. Spring/AspectJ pointcut expressions can resolve the definition by class/method name. You do not need to call `new PointcutCatalog()` or inject the catalog object into `AuditAspect` to use the pointcut expression syntax.

Do not place executable code in the body of `serviceCalls()`: Spring does not use it as a runtime helper method.

### 6.4. Aspect reusing the public pointcut from another class

**`AuditAspect.java`**

```java
package com.example.visibility;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class AuditAspect {
    private final AtomicInteger calls = new AtomicInteger();

    @Before("com.example.visibility.PointcutCatalog.serviceCalls()")
    public void beforeServiceMethod() {
        calls.incrementAndGet();
    }

    public int count() {
        return calls.get();
    }
}
```

The advice references the **fully qualified public named pointcut** even though it is declared on a different Java class. Both `process(..)` and `inspect()` match because they are public methods of `OrderService`. Nothing is printed inside the advice so that the order of the two aspects does not make stdout non-deterministic.

### 6.5. Aspect using an internal private named pointcut

**`TraceAspect.java`**

```java
package com.example.visibility;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.aspectj.lang.annotation.Pointcut;

@Aspect
public class TraceAspect {
    private final AtomicInteger calls = new AtomicInteger();

    @Pointcut(
        "execution(public * com.example.visibility.OrderService.process(..))"
    )
    private void processOnly() {}

    @Before("processOnly()")
    public void beforeProcess() {
        calls.incrementAndGet();
    }

    public int count() {
        return calls.get();
    }
}
```

The pointcut `processOnly()` is **private**, yet the `beforeProcess()` advice of `TraceAspect` itself can use it. The expression matches only `OrderService.process(..)`; `inspect()` does not match.

If `@Before("processOnly()")` is copied directly into `AuditAspect` without redefining or matching visibility, it will not automatically resolve the named pointcut from the other aspect. To share it, expose a separate public named pointcut or use a catalog class.

### 6.6. Spring configuration creating one target bean and two aspect beans

**`AppConfig.java`**

```java
package com.example.visibility;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {
    @Bean
    OrderService orderService() {
        return new OrderService();
    }

    @Bean
    AuditAspect auditAspect() {
        return new AuditAspect();
    }

    @Bean
    TraceAspect traceAspect() {
        return new TraceAspect();
    }
}
```

`@EnableAspectJAutoProxy` enables the Spring AOP `@AspectJ` infrastructure for the context. `AuditAspect`/`TraceAspect` become Spring beans via `@Bean`, without needing `@Component`. `OrderService` is the target Spring bean. `proxyTargetClass=true` makes the example use a CGLIB class-based proxy so `main` can look up `OrderService` by concrete class.

**Do not register `PointcutCatalog`** because that class only defines pointcut signatures and contains no advice or state for Spring to manage.

### 6.7. Main observing the result

**`Main.java`**

```java
package com.example.visibility;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            OrderService service = context.getBean(OrderService.class);
            AuditAspect audit = context.getBean(AuditAspect.class);
            TraceAspect trace = context.getBean(TraceAspect.class);

            System.out.println("proxy=" + AopUtils.isAopProxy(service));
            System.out.println(service.process("A"));
            System.out.println(service.inspect());
            System.out.println("publicPointcutCalls=" + audit.count());
            System.out.println("privatePointcutCalls=" + trace.count());
        }
    }
}
```

From the project directory, with Gradle and JDK 17+ installed:

```bash
gradle run --quiet
```

If Gradle Wrapper is present: `./gradlew run --quiet` (Linux/macOS) or `gradlew.bat run --quiet` (Windows).

**`System.out` lines printed by the program, in exact order** (excluding external messages from JVM/Gradle/logging):

```text
proxy=true
processed:A
inspected
publicPointcutCalls=2
privatePointcutCalls=1
```

Explanation:

1. `proxy=true`: `OrderService` was proxied by Spring because advisors apply to it.
2. `processed:A` and `inspected`: both target methods execute and return values.
3. `publicPointcutCalls=2`: the expression `PointcutCatalog.serviceCalls()` matches **two method invocations** through the proxy; the advice in `AuditAspect` runs twice.
4. `privatePointcutCalls=1`: only the `process("A")` invocation matches `TraceAspect.processOnly()`; `inspect()` does not match.
5. There is no difference caused by a `private` pointcut having "less AOP capability" than a `public` pointcut; **the two selection expressions are different**, while the modifier only governs **referencability** of the named pointcut.

The demo does not rely on advice execution order between `TraceAspect` and `AuditAspect`, because both counters are printed after all calls complete. If specific advice ordering is needed in production, inspect `@Order` and test the full advisor chain.

## 7. Specific reuse scopes in a codebase

### 7.1. Used only inside a single aspect

```java
@Aspect
public class ServiceTraceAspect {
    @Pointcut("execution(public * com.example.billing..*Service.*(..))")
    private void businessMethods() {}

    @Before("businessMethods()")
    public void before() {}

    @AfterReturning("businessMethods()")
    public void afterSuccess() {}
}
```

Two advice methods in the same declaring class share one private named pointcut. No need to duplicate the expression string. This is an **illustrative snippet**, not replacing the `TraceAspect` demo above.

### 7.2. Two aspects in the same Java package

```java
package com.example.billing.aop;

public class InternalPointcuts {
    @Pointcut("execution(public * com.example.billing..*Service.*(..))")
    void businessMethods() {}
}
```

`businessMethods()` here is **package-private** and can be referenced from valid locations in the **same package**. However, if two aspects sit in two different subpackages, remember that Java treats `com.example.billing.aop` and `com.example.billing.aop.audit` as **two different packages**. Package-private does not automatically permit references just because the package path shares a prefix.

The illustrative snippet above needs `import org.aspectj.lang.annotation.Pointcut` if placed in a real file. If an internal package still needs to be consumed by another module via fully qualified name, deliberately choose a **public API pointcut** instead of bypassing visibility.

### 7.3. Using `protected` in a hierarchy

```java
public abstract class BasePointcuts {
    @Pointcut("execution(public * com.example.billing..*Service.*(..))")
    protected void businessMethods() {}
}

// Illustrating an aspect inheriting the declaration, in the same project.
@Aspect
public class ChildAspect extends BasePointcuts {
    @Before("businessMethods()")
    public void beforeBusiness() {}
}
```

This is **illustrative syntax**, not two standalone runnable Java files: appropriate packages/imports and bean registration are required. `protected` can support intentional pointcut reuse across a hierarchy, though inheritance of aspects/`@AspectJ` has its own limitations. Spring applies normal Java visibility when resolving references; do not assume an arbitrary aspect in another package can call this `protected` name without a valid visibility relationship.

If multiple aspects **with no genuine parent–child relationship** need the same reuse, a `CommonPointcuts` class with `public` named declarations is usually simpler than an inheritance hierarchy created just to share expressions.

### 7.4. Sharing across modules

A `platform-aop` module may publish:

```java
package com.example.platform.aop;

import org.aspectj.lang.annotation.Pointcut;

public final class PlatformPointcuts {
    private PlatformPointcuts() {}

    @Pointcut("execution(public * com.example.app..*Service.*(..))")
    public void appServiceCalls() {}
}
```

This is an **illustrative snippet**, not combined with the demo in section 6. When another module references `com.example.platform.aop.PlatformPointcuts.appServiceCalls()`, the class/method must be accessible at runtime, included in the appropriate dependency/classpath, and the expression must target the actual application's packages. There is no need to instantiate a class holding only pointcut signatures for consumers to reference the name.

When published as a shared API, renaming the FQCN/method or changing the expression's semantics can break consuming aspects or select a different set of target methods. Manage changes as a **compatibility contract**.

## 8. Combining named pointcuts: visibility controls reference, not matched set

You can keep catalog building blocks `private` while exposing a `public` composite pointcut with a clear contract:

```java
@Pointcut("within(com.example.billing..*)")
private void billingTypes() {}

@Pointcut("execution(public * save*(..))")
private void publicSave() {}

@Pointcut("billingTypes() && publicSave()")
public void billingSaveOperations() {}
```

The methods above are fragments in the same declaring class. External consumers only reference `billingSaveOperations()` if the declaring class is public, while internal changes to `billingTypes()` do not couple them to helper names. The expression determines matching; visibility only determines where it can be referenced.

## 9. Parameterized named pointcuts: notes on sharing bindings

A named pointcut can carry a **binding parameter**, for example:

```java
@Pointcut(value = "args(orderId,..)", argNames = "orderId")
public void withOrderId(String orderId) {}
```

An aspect outside the class references `SomePointcuts.withOrderId(orderId)` from an advice with matching `argNames`/parameters. When used across packages, the method must have suitable visibility; `public` does not make `args` automatically match an argument of the wrong type. This is a snippet, not a standalone runnable method; test actual parameter types and argument counts.

## 10. Registration, proxy, and lifecycle: prerequisites for reuse to take effect

For a public reference to succeed, the class containing the named pointcut must be on the classpath, the type/method accessible, the fully qualified name exact, and the pointcut expression parseable. Yet advice runs only if **the aspect containing the advice is a Spring bean**, AOP support is enabled, the target is a Spring bean, the method is interceptable, and the caller goes through the proxy.

A catalog class declaring only public `@Pointcut` methods does not need to become a Spring bean. Conversely, declaring `@Aspect` without registering it via `@Component` or `@Bean` will not make advice run automatically.

## 11. Common mistakes

When troubleshooting errors, separate three layers of causes. **Name fails to resolve:** wrong package/class/method or inaccessible named pointcut. **Resolves but fails to match:** `execution`, `within`, `bean`, or annotation does not select the actual method. **Matches properly but advice does not run:** target outside context, self-invocation, or JDK/CGLIB cannot intercept that call.

Do not change `private @Pointcut` to `public` as a way to fix an overly narrow expression: Java visibility does not change matching scope. Likewise, do not assume a public catalog gives every Spring bean an AOP proxy.

## 12. Strategy for organizing pointcuts in large projects

A maintainable structure:

```text
com.example.app
├── aop
│   ├── ServicePointcuts.java          # reusable public names
│   ├── AuditAspect.java               # advice, internal private pointcuts
│   └── MetricsAspect.java             # advice, references ServicePointcuts
├── billing
│   └── BillingService.java
└── inventory
    └── InventoryService.java
```

Separate by role:

- **Pointcut catalog:** publishes names conveying business/architectural meaning (`businessServiceOperation()`, `billingWriteOperation()`), keeping only expressions reused across multiple places.
- **Aspect classes:** hold advice and internal pointcuts, declared `private` when sharing is unnecessary.
- **Package-private:** used inside a well-encapsulated AOP package; document team conventions clearly.
- **Protected:** only when there is a genuine reuse need within a valid hierarchy.
- **Public:** treated as an API, with documentation/tests for match semantics; changing the expression changes the contract.
- **Test module:** checks real Spring proxy targets to catch expressions selecting the wrong service or losing advisors due to moves/renames.

With the Java module system (JPMS), beyond the `public` modifier, **module readability / exported packages** also apply at compile/runtime. A public method inside an inaccessible class/module will not naturally become a cross-module API. Run integration tests using production packaging to catch this.

### Should you create a single CommonPointcuts for the entire system?

Not necessarily. An overly large catalog containing every pointcut in the company creates coupling across modules. Instead, use one or more clearly scoped catalogs such as `BillingPointcuts`, `InventoryPointcuts`, or `PlatformServicePointcuts`; make public API only those rules truly meant to be shared.

Choose names based on the **intent of the method set**, not solely on the implementation pattern. For instance, `businessOperations()` is better than `pointcut1()`, while ensuring the expression inside genuinely matches business operations in the active packages/modules.

## 13. Verifying pointcut names and matched method sets

Verify both behaviors **independently**: (1) An external aspect successfully references a public catalog pointcut and advice runs properly; (2) A private pointcut used inside the same aspect can still select public target methods. For each case, add an unmatched control method and check actual counters/events.

If changing `public` to `private` on a consumed catalog, keep misconfiguration experiments in a separate fixture so the main context is not broken. After renaming a class/method or changing visibility, audit FQCN strings and run integration tests on real proxies.

## 14. Quick selection table

| Requirement | Visibility to consider | Declaration style |
| --- | --- | --- |
| Two advice methods in one aspect share internal selection | `private` | `@Pointcut` inside the aspect itself; use `@Before("localName()")`. |
| Multiple aspects in the same package, rule not used outside package | Package-private | Pointcut catalog in the package, test access/refs. |
| Aspect hierarchy genuinely needs predicate from base | `protected` | Named pointcut on base type; ensure valid Java inheritance/visibility and Spring `@AspectJ` parsing. |
| Aspects across packages/modules need a shared selection | `public` | Public `CommonPointcuts`/`PlatformPointcuts` with public methods, referenced by FQCN. |
| Each aspect has a single non-reused rule | Naming not strictly needed | Simple inline `@Before("execution(...)")` is reasonable. |
| Want to change which methods are advised | Do not handle via visibility | Edit `@Pointcut("...")` expression/bean boundaries, then test proxy call paths. |
| Want to intercept `private`/`final` methods on target | Pointcut visibility does not help | Review Spring JDK/CGLIB proxy limits, refactor target entry; AspectJ weaving is a different mechanism. |

## 15. Pre-production checklist

Before sharing, verify the `@Pointcut` method returns `void`, has an empty body, and its name conveys the target method set; declaring type and method are public when consumed from other packages. Internal-only pointcuts should restrict visibility accordingly. Cross-check the expression (especially modifiers in `execution(public ...)`) against target methods and JDK/CGLIB proxy type; verify aspect bean registration, proxy call paths, matched cases, and unmatched cases.

For public catalogs consumed across modules, manage name/FQCN/expression changes as a configuration contract backed by regression tests.

