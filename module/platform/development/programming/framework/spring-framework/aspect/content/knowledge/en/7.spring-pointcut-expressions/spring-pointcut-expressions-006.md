# @within and @target by Type Annotation in Spring AOP

## 1. The Problem: Selecting Spring Beans by Class Annotation

When multiple Spring services perform different tasks, you may want to apply the same advice (auditing, timing, diagnostic logging) to **services marked with a type-level annotation**, rather than annotating every method or hardcoding a list of class names.

Spring AOP supports two closely related pointcut designators:

- `@within(com.example.aop.TracedType)`: selects **method execution join points within types that have the specified annotation**. In Spring Framework's phrasing, for Spring AOP these are method executions **declared within a type that has that annotation**.
- `@target(com.example.aop.TracedType)`: selects method execution join points when the **class of the executing target object** carries the specified annotation.

Both use annotations **on a type**, yet they **do not share the same conceptual meaning**. `@within` concerns the **type declaring the execution**, whereas `@target` concerns the **runtime class of the target object** behind the Spring proxy.

**Lesson scope:** syntax, matching, annotation placement, proxies, and real-world pitfalls in **Spring Framework / Spring AOP @AspectJ**. Do not treat `@within`/`@target` as AspectJ weaving; Spring AOP still supports only **method execution join points on Spring-managed beans through proxies**.

### When the Two Designators Look Identical

If a `PaymentService` class is annotated with `@TracedType` and declares `pay()` itself, then calling `pay()` from another bean through a Spring proxy normally matches both `@within(TracedType)` and `@target(TracedType)` simultaneously.

Therefore, **observing both advices run in a simple example is normal** and does not prove the two expressions are synonymous in all cases. The distinction matters when examining **where a method is declared, inheritance, execution types, interfaces, proxy kinds**, and whether the annotation is actually present on the target class.

## 2. Spring AOP Syntax and Prerequisites

A type-marking annotation:

```java
package com.example.typecut;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface TracedType {
    String value() default "";
}
```

Two pointcuts:

```java
@Aspect
public class TypeSelectionAspect {
    @Before("@within(com.example.typecut.TracedType)")
    public void beforeWithin() {
        // Runs when method execution matches @within.
    }

    @Before("@target(com.example.typecut.TracedType)")
    public void beforeTarget() {
        // Runs when method execution matches @target.
    }
}
```

This is an **illustrative Java snippet**; to run it in Spring, make `TypeSelectionAspect` a bean, enable AOP support, provide dependencies, have a target Spring bean, and have a caller go through the proxy. Import `org.aspectj.lang.annotation.Aspect` and `Before`.

Spring-specific prerequisites:

1. **The annotation has `@Target(ElementType.TYPE)`.** Both designators here select type-level annotations, not `@Target(ElementType.METHOD)`.
2. **Use `@Retention(RetentionPolicy.RUNTIME)` for this example.** It lets Spring/AspectJ pointcuts inspect and bind the annotation at runtime; do not rely on `SOURCE`-only annotations or assume another retention policy is supported identically by Spring AOP.
3. **The `@Aspect` class is a Spring bean.** Use `@Aspect` + `@Component` within scan scope or return the aspect from a `@Bean` method.
4. **Enable Spring AOP `@AspectJ` support.** In Java-config Spring Framework use `@EnableAspectJAutoProxy`; Spring Boot usually auto-configures this when the appropriate AOP starter is present.
5. **The target must also be a Spring bean.** `new PaymentService()` outside the container will not be seen by Spring AOP interceptors.
6. **The call path must go through the proxy** and the method must be proxiable; `this.method()`, constructors, field access, and `final` classes/methods in CGLIB have specific limits.
7. **Have `aspectjweaver` on the classpath** so Spring can parse/match pointcut expressions. No `-javaagent` is needed for normal Spring proxy AOP.

Important: `@target` in a pointcut expression is **not** Java's `@Target` annotation used to declare where an annotation may be placed. One is an **AspectJ pointcut expression**; the other is a **Java meta-annotation**.

## 3. Distinguishing the Meanings of @within and @target

| Criterion | `@within(TracedType)` | `@target(TracedType)` |
| --- | --- | --- |
| Spring AOP meaning | Method execution within a marked type; Spring docs emphasize the **type declaring the method** | Class of the **target object** executing carries the annotation |
| Factor inspected | Type containing the method execution, and annotation on that type | Runtime type of the target object behind the Spring proxy and its annotation |
| Where is `@TracedType` placed in typical examples? | On the class declaring the method | On the target bean's class |
| Selects methods by an annotation on the method itself? | **No**; that is the role of `@annotation` | **No**; also a type-level annotation |
| Method declared in an annotated class and target is that same class | Usually matches | Usually matches |
| When methods are inherited, overridden, or declared via interfaces | Must check declaring type and how Spring resolves the method | Must check annotation on the actual target class and how Spring resolves type/proxy |
| For an unannotated class | Does not match under ordinary declaring-type rules | Does not match if actual target class also lacks the annotation |
| Changes Spring proxy limitations? | No | No |

The definitions above are based on **Spring Framework Pointcuts** documentation. Do not translate them into " `@within` always matches superclasses/subclasses" or " `@target` always matches every inherited method". With inheritance and interfaces, **exact annotation placement, Java annotation inheritance rules, and Spring's method resolution** determine the runtime outcome.

### Difference from `@annotation`

```java
@TracedType
public class PaymentService {
    public void pay() { }

    @AuditedOperation
    public void refund() { }
}
```

Assuming `@AuditedOperation` is a custom `METHOD` annotation and the class is a Spring bean:

- `@within(TracedType)` and `@target(TracedType)` aim to select executions by the **`PaymentService` type**; they do not require `pay`/`refund` to individually carry `@TracedType`.
- `@annotation(AuditedOperation)` selects by **method annotation**, and does not automatically apply to `pay()` just because the class has `@TracedType`.
- If you need both a class-level annotation and restriction to specific methods, combine `execution(...) && @within(...)` or `execution(...) && @target(...)`; if you need **both annotations at once**, add `@annotation(...)`.

Do not use `@target` to look for annotations on **parameters** or **return types**; those two cases use different mechanisms/expressions and are outside this pointcut's purpose.

## 4. Constraining Types in Pointcuts: Why Avoid Overly Broad Expressions?

A short expression:

```java
@Before("@target(com.example.typecut.TracedType)")
public void trace() {
    // ...
}
```

can force Spring to evaluate **many candidate beans/methods** before determining the target's annotation—especially since `@target` involves runtime target factors. In an application with many infrastructure beans, an overly broad pointcut can cause extra work for the auto-proxy creator or trigger proxy errors on unintended infrastructure beans (e.g., a `final` bean considered for proxying in class-based proxy mode).

Scope type/package/method explicitly:

```java
@Before(
    "execution(public * com.example.typecut..*Service.perform(..))"
    + " && @target(com.example.typecut.TracedType)"
)
public void beforeSpecificServiceMethod() {
    // ...
}
```

- `execution(public * ... )` requires public method execution.
- `com.example.typecut..*Service` limits the package region and class name.
- `perform(..)` limits to methods with that specific name and any parameter count.
- `&& @target(TracedType)` additionally requires the target class to carry the annotation.

If you want the same logic by method-declaring type, replace `@target` with `@within`. The two snippets above are **illustrative code**, not a standalone runnable project.

In real projects, choose scope **by package/bean and contract** rather than matching every class in the application. When excluding a method from interception, write a test to verify it is actually excluded.

## 5. Runnable Java 17+ Demo: Same Class-Level Annotation, Two Counters

The plain Spring Framework example below confirms that **an annotated class** triggers both `@within` and `@target`, whereas an unannotated class does not trigger advice by type annotation in the example. Both advices increment counters without **printing logs**, avoiding reliance on execution order between advisors.

Environment: **Java 17+**, **Spring Framework 6.2.18**, **AspectJ Weaver 1.9.24**, Gradle with the `application` plugin. These dependency versions are available on Maven Central. Spring Boot is omitted in the demo to make `@EnableAspectJAutoProxy` clearly visible.

### 5.1. Directory Tree

```text
spring-type-annotation-pointcuts/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/typecut/
    ├── AppConfig.java
    ├── TracedType.java
    ├── MarkedService.java
    ├── PlainService.java
    ├── TypeSelectionAspect.java
    └── Main.java
```

**`settings.gradle`**

```gradle
rootProject.name = 'spring-type-annotation-pointcuts'
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
    implementation 'org.springframework:spring-context:6.2.18'
    implementation 'org.springframework:spring-aop:6.2.18'
    implementation 'org.aspectj:aspectjweaver:1.9.24'
}

application {
    mainClass = 'com.example.typecut.Main'
}
```

Spring Framework 6.x requires Java 17+. In a real Spring Boot project, rely on Boot's dependency management/BOM rather than mixing standalone Spring Framework versions without verifying compatibility.

### 5.2. Type-Level Annotation

**`TracedType.java`**

```java
package com.example.typecut;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface TracedType {
    String value() default "";
}
```

The annotation retains `value` so it can be extended to binding, though the two advices in the initial demo only check the **presence of the type annotation** without reading the value.

### 5.3. One Annotated Service, One Plain Service

**`MarkedService.java`**

```java
package com.example.typecut;

@TracedType("checkout")
public class MarkedService {
    public String perform(String id) {
        return "marked:" + id;
    }
}
```

**`PlainService.java`**

```java
package com.example.typecut;

public class PlainService {
    public String perform(String id) {
        return "plain:" + id;
    }
}
```

Both classes are non-final, both methods are public/non-final, and there are no self-calls. Thus the crucial difference between the two services is the **type-level annotation**, not method visibility or proxy eligibility.

### 5.4. One Aspect with Two Independent Advices

**`TypeSelectionAspect.java`**

```java
package com.example.typecut;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class TypeSelectionAspect {
    private final AtomicInteger withinCalls = new AtomicInteger();
    private final AtomicInteger targetCalls = new AtomicInteger();

    @Before(
        "execution(public * com.example.typecut..*Service.perform(..))"
        + " && @within(com.example.typecut.TracedType)"
    )
    public void beforeWithin() {
        withinCalls.incrementAndGet();
    }

    @Before(
        "execution(public * com.example.typecut..*Service.perform(..))"
        + " && @target(com.example.typecut.TracedType)"
    )
    public void beforeTarget() {
        targetCalls.incrementAndGet();
    }

    public int withinCount() {
        return withinCalls.get();
    }

    public int targetCount() {
        return targetCalls.get();
    }
}
```

**Why not print advice order?** Both advices are `@Before` on the same join point; execution order is not pinned without explicit ordering configuration. Using counters and printing after method completion gives **deterministic** verification output without claiming `@within` always runs before `@target` or vice versa.

`AtomicInteger` ensures safe increments/reads under concurrent calls. However, counters in a singleton aspect are only a demo for observing interception, not a production metrics system or cluster-wide counter.

### 5.5. Registering Beans and Enabling @AspectJ Support

**`AppConfig.java`**

```java
package com.example.typecut;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {
    @Bean
    TypeSelectionAspect typeSelectionAspect() {
        return new TypeSelectionAspect();
    }

    @Bean
    MarkedService markedService() {
        return new MarkedService();
    }

    @Bean
    PlainService plainService() {
        return new PlainService();
    }
}
```

`TypeSelectionAspect` is a **Spring bean via `@Bean`**, without needing `@Component`. Both services are also Spring beans via `@Bean`, without needing `@Service` or `@ComponentScan`.

`@EnableAspectJAutoProxy` allows Spring to pick up advices from `@Aspect` beans to evaluate against target beans. `proxyTargetClass=true` makes proxies accessible by class type in the example; this **does not change the meaning** of annotations placed on the **target class**.

### 5.6. Main Verifying Behavior Without Relying on Advice Order

**`Main.java`**

```java
package com.example.typecut;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            MarkedService marked = context.getBean(MarkedService.class);
            PlainService plain = context.getBean(PlainService.class);
            TypeSelectionAspect aspect =
                    context.getBean(TypeSelectionAspect.class);

            System.out.println("markedProxy=" + AopUtils.isAopProxy(marked));
            System.out.println("marked=" + marked.perform("A"));
            System.out.println("plain=" + plain.perform("B"));
            System.out.println("withinCalls=" + aspect.withinCount());
            System.out.println("targetCalls=" + aspect.targetCount());
        }
    }
}
```

Run from the project root with an installed Gradle:

```bash
gradle run --quiet
```

If using the Gradle Wrapper: `./gradlew run --quiet` on Linux/macOS or `gradlew.bat run --quiet` on Windows.

**Expected application stdout in order** (excluding environment/Gradle logs):

```text
markedProxy=true
marked=marked:A
plain=plain:B
withinCalls=1
targetCalls=1
```

### 5.7. Reading the Results Correctly

1. `markedProxy=true`: `MarkedService` is returned by Spring as a Spring AOP proxy because applicable advisors exist.
2. `marked=marked:A`: method `MarkedService.perform("A")` executes, while both advices increment their counters at the proxy.
3. `plain=plain:B`: the same-named method on `PlainService` runs, yet **lacks `@TracedType` on its type**, so it does not increment either counter in the demo.
4. `withinCalls=1`: the method belongs to a marked type, so `@within` selects the execution.
5. `targetCalls=1`: the runtime target class `MarkedService` has the annotation, so `@target` selects the execution.

**Do not print/assert `plainProxy=false` in the example.** Depending on how Spring evaluates dynamic pointcuts, other advisors, and configuration versions, an unannotated bean may still be considered when creating proxies. What should be asserted is that **advice does not record events for `PlainService.perform`**, not forcing the entire application to share one `AopUtils.isAopProxy(plain)` result.

Also note: this demo **does not differentiate by output** between the two designators on a simple class/method. It confirms how to enable AOP, annotation types, and that the pointcuts work in Spring. To distinguish them in a real codebase, build a matrix with inheritance/annotation placement rather than guessing.

## 6. Class Inheritance, Method Overriding: Why Distinguish Declared Type from Runtime Target?

Consider three scenarios. They are **analytical models**, not deterministic stdout outputs of the main demo.

### 6.1. Class Declares the Method and Carries the Annotation

```java
@TracedType
public class TracedBillingService {
    public void bill() { }
}
```

- `bill()` is declared in `TracedBillingService`.
- The target bean's runtime class is also `TracedBillingService`.
- When called through a Spring proxy, both `@within(TracedType)` and `@target(TracedType)` have clear conditions to match.

This is the best starting scenario for learning and testing both.

### 6.2. Method Declared in an Unannotated Superclass

```java
public class BaseBillingService {
    public void bill() { }
}

@TracedType
public class SpecialBillingService extends BaseBillingService {
    // bill() is inherited, not redeclared here
}
```

Conceptual analysis:

- The **declaring type of the method** is `BaseBillingService`, which lacks `@TracedType`.
- The **actual target object** can be `SpecialBillingService`, which has `@TracedType`.
- Per the pointcut designator distinction, this is a case where you must test `@within` by declaring type and `@target` by runtime target type, rather than treating them as identical.

**Limits of the claim:** Spring AOP delegates part of matching to the AspectJ pointcut parser and contains logic to locate corresponding methods on target classes/interfaces/bridge methods. With inheritance and specific proxy types, Spring's method resolution can make results hard to deduce from source snippets alone. **Test on your exact Spring version and active runtime proxy**; do not impose a single unverified output table.

Another variation: `SpecialBillingService` **overrides `bill()` and declares the method directly in the annotated class**. Then the declaring type has changed, so results may differ from an inherited method. When testing, explicitly note whether the method is **inherited** or **overridden**.

### 6.3. Annotation on Superclass, Target Is Subclass

```java
@TracedType
public class ParentBillingService {
    public void bill() { }
}

public class ChildBillingService extends ParentBillingService {
    // Does not carry @TracedType directly
}
```

Java's `@Inherited` annotation partly governs whether a subclass **inherits a class-level annotation** when looked up via reflection. If `TracedType` is **not** meta-annotated with `@Inherited`, `ChildBillingService.class.isAnnotationPresent(TracedType.class)` does not become true automatically just because the parent has the annotation. If you want class-hierarchy annotation inheritance in Java, consider:

```java
import java.lang.annotation.Inherited;

@Inherited
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface TracedType {
    String value() default "";
}
```

This is an **illustrative annotation variant**; to compile as a standalone file, add Java imports and package; do not modify the demo's `TracedType.java` directly without checking tests.

`@Inherited` **does not cause an annotation on an implemented interface to become an inherited annotation on the implementing class**. Spring's annotation lookup utilities may use merge/meta-annotation rules different from standard Java reflection, so do not confuse those lookup semantics with specific runtime pointcut conditions.

**Takeaway:** when a policy must apply to subclasses as well, test both reflection/annotation lookup and **actual advice invocation** on a real subclass. Do not place a security policy in an annotation and assume it automatically propagates to every target class.

## 7. Annotations Placed on Interfaces: A Common Trap in Spring AOP

In Spring design, a service often has an interface:

```java
@TracedType
public interface PaymentPort {
    String pay(String id);
}

public class PaymentService implements PaymentPort {
    @Override
    public String pay(String id) {
        return "paid:" + id;
    }
}
```

Illustrative snippets, not part of the runnable `MarkedService` demo above.

Distinguish:

- **`PaymentPort` has the annotation**; **`PaymentService` may not have that annotation** in Java reflection results. `@Inherited` does not transfer annotations from interfaces to implementing classes.
- For `@target(TracedType)`, Spring documentation describes the annotation **on the target object's class**. Do not assume an annotation placed only on an interface is always enough for this pointcut to match the implementation.
- For `@within(TracedType)`, the method declaring type, proxied interface type, and how Spring resolves the implementation method can affect the outcome. Test on both **JDK proxies** and **CGLIB proxies**, especially when method/type annotations appear on interfaces but not on implementations.
- The behavior of a Spring feature supporting **merged annotations** is not proof that `@within`/`@target` apply the same semantics; they are AspectJ pointcut expressions interpreted by Spring AOP.

**Practical, controllable approach:** if a policy must rely on a **class-level annotation of the runtime target**, place the annotation directly on the target implementation class (or use tested, documented inheritance). If the policy belongs to the **interface contract**, consider pointcuts like `execution(* PaymentPort.*(..))` / `this(PaymentPort)` or a suitable marker method annotation, and **test** with the actual proxy type. Do not rely on interface annotation inheritance that Java does not guarantee.

## 8. When to Use @within, and When @target?

The answer is not "one is always better than the other". Choose based on **where the annotation's meaning lives** and what guarantees are needed:

**Use `@within` when:**

- You intentionally select **code belonging to a marked type** and want to express the scope of types declaring methods.
- Methods declared directly in annotated service classes are the primary case.
- You have tested behavior with relevant inherited/overridden/interface methods rather than overgeneralizing.
- You want a clear expression for "method executions inside an annotated type", rather than relying solely on runtime class.

**Use `@target` when:**

- You want to require "the target object to which the Spring proxy delegates has a class bearing this annotation".
- The runtime implementation class is where **the marker type annotation is placed**.
- You need to bind/read annotation metadata on the target inside advice and have tests confirming it.
- You combine it with a specific `execution` so Spring does not evaluate too many bean types and methods.

**Use `@annotation` instead when:**

- Only certain methods on a class need interception.
- The annotation policy is an attribute of the **operation**, not the entire target service.
- You need to distinguish one audited method from another non-audited method in the same class.

If the goal is simply **a named Spring bean** (e.g., `paymentService`), the `bean(paymentService)` pointcut extension may be more precise than a type annotation. `bean` is a **Spring AOP-specific** extension; it is not a general AspectJ weaving pointcut designator.

## 9. Combining @within/@target with execution, bean, and Other Expressions

### 9.1. Intercepting Public Operations in a Business Package

```java
@Pointcut("execution(public * com.example.billing..*Service.*(..))")
public void billingOperations() { }

@Pointcut("@target(com.example.typecut.TracedType)")
public void tracedTarget() { }

@Before("billingOperations() && tracedTarget()")
public void beforeBillingOperation() {
    // ...
}
```

This is an **illustrative snippet inside the same `@Aspect` class**, requiring `Pointcut` and `Before` imports. Breaking pointcuts into small names aids readability and reuse; Spring still needs the aspect bean and Spring-managed targets.

### 9.2. Intercepting by Declaring Type and Method Name

```java
@Before(
    "execution(public * com.example.typecut..*Service.perform(..))"
    + " && @within(com.example.typecut.TracedType)"
)
public void beforePerform() {
    // ...
}
```

This selects both type scope and operation. If the class has multiple methods, only `perform` matching the `execution` expression is evaluated.

### 9.3. Using OR When Either Condition Is Genuinely Acceptable

```java
@Before(
    "execution(public * com.example.typecut..*Service.perform(..))"
    + " && ("
    + "@within(com.example.typecut.TracedType)"
    + " || @target(com.example.typecut.TracedType)"
    + ")"
)
public void beforeAnyMarkedCase() {
    // ...
}
```

`||` does not make Spring "run the advice twice if both match"; **a single advice method** attached to an OR expression runs **once per matching join point invocation**, unless the application has other advisors/advices or repeated invocations. However, an OR expression widens match scope; for important policies, test inheritance/interface cases to know exactly why a target was selected.

**Distinction note:** if you write **two separate advice methods** for `@within` and `@target` as in the demo, a single method invocation can invoke **both advice methods**, incrementing each counter by one. That is not an OR expression "running twice by itself".

### 9.4. Excluding Unwanted Packages or Beans

```java
@Before(
    "execution(public * com.example.typecut..*Service.perform(..))"
    + " && @target(com.example.typecut.TracedType)"
    + " && !bean(internal*Service)"
)
public void beforePublicFacingTarget() {
    // ...
}
```

`bean(...)` is a **Spring-specific** bean-name PCD. The `internal*Service` pattern is only an example; if actual bean names differ, the exclusion rule will not work. Do not use name-based exclusion expressions in place of solid architecture/security boundaries.

## 10. Binding Annotation Instances to Advice

Spring AOP `@AspectJ` supports binding the annotation of `@target`/`@within` to an advice parameter. Use this when you need to read metadata such as `@TracedType`'s `value` rather than only checking whether the annotation exists.

**Separate illustrative example**—do not add to the main demo because it would change counters and stdout:

```java
@Aspect
public class MetadataAspect {
    @Before(
        value = "execution(public * com.example.typecut..*Service.perform(..))"
              + " && @target(marker)",
        argNames = "marker"
    )
    public void beforeTarget(TracedType marker) {
        System.out.println("typeTag=" + marker.value());
    }
}
```

If the target class has `@TracedType("checkout")` and the method join point matches, Spring can bind the annotation instance to `marker` to print:

```text
typeTag=checkout
```

Requirements for the code to actually run: the aspect class must be a Spring bean, `TracedType` must have `RUNTIME` retention, pointcut bindings must be compatible, and the target method must go through a proxy. `argNames = "marker"` makes the binding parameter explicit, avoiding reliance on Java parameter name info that may be absent when compiling without `-parameters`.

Similarly, you can write `@within(marker)` when binding the annotation of the type associated with `@within`, but verify that the annotation actually resides on the declaring type selected by the pointcut. Binding does not turn a method annotation into a class-level annotation.

**Do not confuse `@target(marker)` with `target(targetObject)`:**

- `@target(marker)` binds the **annotation object**.
- `target(targetObject)` binds the **Spring target instance** matching the parameter type, if the expression and type are valid.

If you only need the annotation to exist without reading metadata, writing `@target(com.example.typecut.TracedType)` is easier to verify and requires no binding.

## 11. A Small but Thorough Test Matrix

When applying type-annotation pointcuts in Spring, prepare integration tests covering **the matching paths** rather than guessing from designator names.

| Case | Where type annotation is placed | Method entry | What to verify |
| --- | --- | --- | --- |
| A | Directly on target class | Public method declared on the same class | Do both `@within` and `@target` produce the expected event counts? |
| B | No annotation on class | Public method with same name | No unintended advice? |
| C | Annotation on subclass, method inherited from base | Unoverridden method | Do declaring type and runtime target behave differently? |
| D | Annotation on subclass, method overridden in subclass | Overridden public method | Does the result differ from case C? |
| E | Annotation on superclass with/without `@Inherited` | Target method belongs to subclass | Do runtime annotation semantics match intent? |
| F | Annotation only on interface | Public implementation method | Do JDK/CGLIB and method resolution differ? |
| G | Annotation directly on implementation | Interface method called via JDK proxy | Does `@target` catch the target class properly? |
| H | Annotation present, but target created via `new` | Called outside container | No Spring AOP advice? |
| I | Annotation present, self-invocation on target | `this.perform()` | Is advice on `perform` bypassed? |
| J | Annotation present, CGLIB `final` method or `final` class | Unoverridable method | Is proxying limited or does startup fail as expected? |

There is no need to turn every case into a new README. Create a **minimal test context** with the right proxy mode and assert only **advice invocation counts**/side effects. In setups with multiple advisors, count per advice rather than concluding that proxy existence means every advice matched.

### Test Example on the Demo Context

```java
// Illustrative snippet inside a Spring integration test or main
try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
    MarkedService marked = context.getBean(MarkedService.class);
    PlainService plain = context.getBean(PlainService.class);
    TypeSelectionAspect aspect = context.getBean(TypeSelectionAspect.class);

    marked.perform("T1");
    marked.perform("T2");
    plain.perform("T3");

    if (aspect.withinCount() != 2 || aspect.targetCount() != 2) {
        throw new AssertionError("Unexpected type-annotation pointcut count");
    }
}
```

This is a **standalone variant** runnable in the demo package by importing `AnnotationConfigApplicationContext`. Do not run it inside the same `Main` if you want to keep the stdout in section 5.7, as it uses a separate context. The logic asserts that two method calls to the annotated class are counted and one call to the plain class is not.

With `@Before`, counters measure **advice checkpoints before the target runs**, not committed business transactions. If the target method throws an exception after `@Before`, the counter has already incremented; if you want to measure "success", choose the appropriate advice type and business condition.

## 12. Common Pitfalls and How to Handle Them

### 12.1. Putting an Annotation on a Method While Writing @within or @target

```java
public class ExampleService {
    @TracedOperation
    public void execute() { }
}
```

If `@TracedOperation` only has `@Target(ElementType.METHOD)`, `@within(TracedOperation)`/`@target(TracedOperation)` are not the right expressions for that annotation. If the annotation is a **method policy**, choose `@annotation(com.example.TracedOperation)` and ensure the target method is proxied.

### 12.2. Class Has the Annotation but Is Not a Spring Bean

```java
@TracedType
class TracedService {
    public void perform() { }
}
```

A class marked with `@TracedType` is not automatically registered as a bean in Spring. Register it with `@Component`/`@Service` and component scanning, or `@Bean` on `@Configuration`. The aspect side must also be a Spring-managed bean.

### 12.3. Assuming @within and @target Always Behave Identically Across Inheritance

The two expressions may match alike in basic examples, yet **declaring type** and **runtime target type** have different meanings. When inherited/overridden/interface methods exist, test on your project's Spring version and proxy mode. Do not invent an absolute output table and treat it as a contract.

### 12.4. Confusing Java @Inherited with Interface Inheritance

`@Inherited` operates along **class inheritance**, not interface implementation. An interface carrying an annotation does not automatically turn an implementing class into a runtime-annotated target class; framework-specific annotation search mechanisms must also be distinguished clearly.

### 12.5. Overly Broad Pointcuts

Bare `@target(TracedType)` can make AOP infrastructure evaluate too many candidates. Prefer `execution(...) && @target(...)` or a pointcut combined with a package scope. Check whether internal/security/framework beans are accidentally receiving advisors.

### 12.6. Switching Proxy Mode to "Fix" an Annotation Issue Without Testing

JDK interface proxies and CGLIB class proxies differ in method exposure and class/method constraints. If an annotation is on an interface, switching proxy types may change matching, but it does not guarantee Spring copies annotations onto implementations. Verify with tests.

### 12.7. Testing Objects Created with new

`new MarkedService().perform("A")` does not go through a Spring AOP proxy; the class annotation still exists, yet advice does not run. AOP tests must obtain beans from `ApplicationContext`.

### 12.8. Self-Invocation

If `markedService.outer()` calls `this.perform()` on the target, `perform` does not re-enter the proxy; even though the class is annotated, advice specifically for `perform` can still be bypassed. Switching `@within` to `@target` does not fix self-invocation.

### 12.9. Placing Policy Annotations on final Classes or final Methods

With CGLIB proxies, Spring cannot subclass `final` classes and cannot override `final` methods. A valid annotation still cannot turn unoverridable bytecode into Spring proxy interception. If a business interface exists and CGLIB is not forced, a JDK proxy may be suitable; the method must be exposed through the proxied interface.

### 12.10. Inferring from isAopProxy That the Annotation Pointcut Ran

`AopUtils.isAopProxy(bean)` only proves a Spring AOP proxy exists. A bean may have a proxy due to another advisor, a method may not match the pointcut under test, and a self-call may bypass it. Always assert advice events/counters specifically for `@within` or `@target`.

## 13. Workflow for Debugging When @within/@target Does Not Run as Expected

1. **Verify annotation placement.** Does `TracedType` have `@Target(TYPE)` and `@Retention(RUNTIME)`? Is the annotation on the implementation class, superclass, or interface?
2. **Verify the Spring context.** Is the aspect actually a bean? Is the target a bean? Are you in the right ApplicationContext with AOP auto-configuration active?
3. **Inspect the pointcut carefully.** `@within` checks the method-declaring type, while `@target` checks the runtime target class; add `execution` to prevent out-of-scope matching.
4. **Inspect the proxy.** `AopUtils.isAopProxy(bean)`, `isJdkDynamicProxy`, `isCglibProxy`; is the method entry on the interface or overridable?
5. **Call the method through the proxy.** Obtain the Spring bean from context or inject it into another bean; do not use `new` and do not rely on `this.method()`.
6. **Measure each advice separately.** Create counters/test recorders for `@within` and `@target`; do not only inspect the method's return value.
7. **Check inheritance/bridge methods if needed.** Record whether the method is overridden, whether the annotation has `@Inherited`, and which runtime class acts as target. Do not use `proxy.getClass().isAnnotationPresent(...)` instead of checking the annotation on the target class.
8. **Write integration tests for the real proxy mode.** Test with your actual Spring/Boot version and JDK, especially for interface annotations, generic bridge methods, or Kotlin final classes.
9. **Review impact.** Advice used for auditing/security/transactions needs real business-behavior tests rather than inferring from a single log line that the policy is comprehensively enforced.

### Inspecting Target Class Instead of Generated Proxy Class

```java
Object bean = context.getBean("markedService");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.getTargetClass(bean).getName());
```

This is an **illustrative snippet**, requiring `org.springframework.aop.support.AopUtils` and a bean named `markedService` in the context. In the demo, `getTargetClass` identifies the business class `MarkedService`, avoiding confusion between the generated proxy subclass or JDK runtime proxy class and the class holding the type annotation.

To check whether the annotation is truly present on the target type via Java reflection:

```java
Class<?> targetType = AopUtils.getTargetClass(bean);
boolean directlyOrInherited =
        targetType.isAnnotationPresent(TracedType.class);
```

This snippet is a diagnostic tool for `RUNTIME` annotations under Java reflection (and `@Inherited` if present); it **does not replace** the Spring/AspectJ pointcut matching engine or actual advice verification.

## 14. Practice Checklist

- [ ] Does the type-marking annotation have `@Target(TYPE)` and `@Retention(RUNTIME)`?
- [ ] Do you clearly distinguish `@within`'s **method-declaring type** from `@target`'s **runtime target class**?
- [ ] Are you sure `@within`/`@target` are not confused with `@annotation` on methods or Java's `@Target` meta-annotation?
- [ ] Is the aspect a Spring bean, is the target a Spring bean, and is `@AspectJ` support enabled?
- [ ] Is the pointcut constrained with an appropriate `execution(...)` so it does not accidentally apply to too many beans?
- [ ] Are calls made from another bean/context through a **Spring proxy**, not from `new` or `this.method()`?
- [ ] Have you confirmed the JDK/CGLIB proxy type and ability to intercept public/interface/non-final methods?
- [ ] If the annotation is on a superclass/interface, have you tested inheritance/overriding/Java `@Inherited` directly rather than assuming?
- [ ] If you need the annotation's value, did you use `@target(marker)` or `@within(marker)` binding with the right parameter name?
- [ ] Do integration tests separately verify how many times `@within` and `@target` advices run for marked/unmarked classes?
- [ ] Do you avoid assuming `isAopProxy=true` means "every method is advised"?
- [ ] Do security/transaction policies have tests for actual effects, including bypass call paths?

**Remember:** In Spring AOP, `@within` emphasizes **method executions within an annotated type**; `@target` emphasizes the **annotation on the target object's class**. On simple classes both often match together, but that similarity does not eliminate differences between declaring and runtime types when inheritance, proxies, and annotation placement are involved. Always scope pointcuts and verify with a Spring context and real calls through a proxy.

## References

- [Spring Framework 6.2 — Declaring a Pointcut: @within, @target, @annotation, supported PCDs](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html)
- [Spring Framework 6.2 — Declaring Advice: binding annotations to advice parameters](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html)
- [Spring Framework 6.2 — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html)
- [Spring Framework 6.2 — Proxying Mechanisms and self-invocation](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
- [Maven Central — spring-context 6.2.18](https://central.sonatype.com/artifact/org.springframework/spring-context/6.2.18)
- [Maven Central — aspectjweaver 1.9.24](https://central.sonatype.com/artifact/org.aspectj/aspectjweaver/1.9.24)
