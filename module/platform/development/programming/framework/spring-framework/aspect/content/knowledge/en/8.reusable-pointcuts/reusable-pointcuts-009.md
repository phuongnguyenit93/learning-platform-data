# Keeping Pointcuts Stable When Renaming Packages, Classes, or Methods in Spring AOP

## 1. Why does refactoring easily break Spring Aspects?

In Spring AOP, many pointcuts are written as **expression strings** inside `@Pointcut`, `@Before`, `@Around`, and so on. For example:

```java
@Before("execution(* com.example.orders.OrderService.submit(..))")
public void auditSubmission() {
    // ...
}
```

This expression depends on **package name**, **class name**, and **method name**. When the development team refactors:

- `com.example.orders` moves to `com.example.fulfillment`.
- `OrderService` is renamed to `FulfillmentCoordinator`.
- `submit()` is renamed to `dispatch()`.

The Java source code of beans and callers may be updated by the IDE so it still **compiles cleanly**, yet the pointcut string may **not be updated accordingly**. The most dangerous outcome is that the application keeps running business logic normally while the Spring Aspect silently stops applying auditing, metrics, or shared policies to the new method.

Two situations must be distinguished:

1. **Invalid expression:** Spring may throw an error while parsing the pointcut/creating the advisor, preventing the application context from starting.
2. **Valid expression that no longer matches:** Spring does not necessarily report an error. The bean might not receive a proxy because no advisor applies anymore, or it might have a proxy for another advisor while the advice you care about **never runs**. This is the risk integration tests must catch.

The goal is not to write a single expression that magically understands **every future refactor**. The goal is to design a **clear join-point selection contract with minimal coupling to volatile details**, centralize edits, and make it testable.

**Boundary:** This lesson covers only **Spring Aspects and pointcuts in proxy-based Spring AOP**. Spring AOP supports method executions on Spring-managed beans; plain Java calls outside proxies and AspectJ weaving are not the primary subject.

## 2. Refactoring sensitivity across pointcut selection strategies

| Selection method | Example | On package rename | On class rename | On method rename | Trade-off |
| --- | --- | --- | --- | --- | --- |
| Fixed fully qualified name | `execution(* com.example.orders.OrderService.submit(..))` | Easily loses match | Easily loses match | Easily loses match | Very specific yet brittle. |
| Package convention | `execution(public * com.example..service.*.*(..))` | Depends on package layout | Low coupling to class name | Low coupling to method name | Easy to over-match or miss new packages. |
| Stable interface contract | `target(com.example.api.OrderOperations)` | More resilient if interface stays put | Does not hardcode implementation name | Does not filter individual methods | Needs a stable API and extra method conditions. |
| Annotation on method | `@annotation(com.example.aop.MonitoredOperation)` | Independent of target package | Independent of target class name | Independent of target method name | Must keep annotation on the right methods. |
| Annotation on class | `@target(com.example.aop.MonitoredComponent)` | Independent of target package | Independent of target class name | Selects broad method set unless combined | Contract at the class level. |
| Bean-name convention | `bean(*Service)` | May remain unaffected | Depends on actual bean name | Does not filter individual methods | Spring-specific, tied to bean naming. |
| Named pointcut | `@Pointcut("...") void businessOperation() {}` | Centralizes edits | Centralizes edits | Centralizes edits | By itself **does not** make the expression immutable. |

No single formula is always best. If a policy truly applies only to one specific method, renaming that method may **require** updating the pointcut; that is an intentional change. If a policy applies to a **stable business role**, selecting by annotation, interface, or clear convention is usually more durable than a concrete class name.

**A named pointcut only reduces the number of places to edit.** For example, `@Pointcut("execution(* OldService.save(..))")` still breaks when `OldService` is renamed, even if 10 advice methods share `businessSave()`.

## 3. Foundational strategy: name the intent, not the syntax

Spring Framework recommends composing complex expressions out of small **named pointcuts**. A shared class typically has three layers of meaning:

```text
publicMethod()           -> matching method signature
inBusinessLayer()        -> module/bean type boundary
businessOperation()      -> business role used by aspects

businessOperation() = publicMethod() && inBusinessLayer()
```

Example:

```java
package com.example.aop;

import org.aspectj.lang.annotation.Pointcut;

public class CommonPointcuts {

    @Pointcut("execution(public * *(..))")
    public void publicMethod() {}

    @Pointcut("within(com.example..service..*)")
    public void inServiceLayer() {}

    @Pointcut("publicMethod() && inServiceLayer()")
    public void serviceOperation() {}
}
```

This is a Java class declaring pointcuts; **there is no need to create a `@Bean` for `CommonPointcuts`** solely so other aspects can reference pointcut names.

In another aspect:

```java
@Before("com.example.aop.CommonPointcuts.serviceOperation()")
public void beforeService() {
    // ...
}
```

Benefit: when moving the service package, you edit `inServiceLayer()` in only one place. Advice methods using `serviceOperation()` keep their name and role unchanged.

Limitation: if the new package **no longer** falls under `com.example..service..`, `inServiceLayer()` still misses those methods until you update the expression. **Naming does not grant automatic stability; it creates a centralized management point.**

One note on Java visibility: a `private` pointcut method is sufficient within the same aspect; a pointcut shared across classes should be `public`. Visibility determines **where it can be referenced**, not whether the matched target method is `public`. To match only public target methods, write `execution(public ...)` in the expression.

## 4. Annotation strategy: binding policy to method meaning

When an audit/metrics policy must keep applying even if the team renames packages, classes, or methods, a **meaningful annotation** on the method can serve as a stable contract:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface MonitoredOperation {
}
```

And the Spring aspect:

```java
@Pointcut(
    "execution(public * *(..))"
    + " && @annotation(com.example.aop.MonitoredOperation)"
)
public void monitoredOperation() {}
```

These are **fragments** requiring imports/packages and Spring bean registration; the runnable project in section 8 provides the full version.

Suppose:

```java
@MonitoredOperation
public String submit(String id) { /* ... */ }
```

is refactored to:

```java
@MonitoredOperation
public String dispatch(String id) { /* ... */ }
```

If the annotation remains on the new method and the method is still invoked through a Spring proxy, the `@annotation(MonitoredOperation)` pointcut does not depend on either `submit` or `dispatch`.

### 4.1. Annotations are contracts, not magic

An annotation marker works only if:

1. The annotation has **`@Retention(RetentionPolicy.RUNTIME)`** when matching relies on runtime metadata.
2. The marker is placed on the **proper method/class** and preserved across refactors.
3. The aspect has a valid `@Pointcut`/`@Before` and is registered as a Spring bean in the context managing the target.
4. The target is a Spring bean and invocations pass through the AOP proxy.
5. The method lies within Spring proxy interception limits (JDK interface contract or CGLIB subclassing per configuration).

If a developer **deletes the marker** while renaming a method, Spring cannot guess that the new method still requires auditing. Thus annotations must become part of the **review checklist and integration tests**.

If an annotation is declared on an interface method while the implementation method lacks the marker, whether it matches must be verified against the proxy type, how Spring/AspectJ extracts metadata, and the framework version. **Do not assume method annotations are always inherited from interfaces.** Java's `@Inherited` applies to class annotations and does not make method annotations inherited. For critical policies, adopt a clear marker placement convention and test on real beans/proxies.

### 4.2. Using `@target` or `@within` for class-level scoping

If a policy applies to **all public methods of a class playing a specific role**, you can use a **class-level** annotation:

```java
@Pointcut(
    "execution(public * *(..))"
    + " && @target(com.example.aop.MonitoredComponent)"
)
public void monitoredComponentOperation() {}
```

- `@annotation(...)` selects methods bearing a matching annotation.
- `@target(...)` selects by annotation on the class of the **target object**.
- `@within(...)` selects join points within types carrying a matching annotation; in Spring AOP pay attention to the type/method being inspected.
- `target(SomeInterface)` selects targets compatible with an interface or type, **without relying on annotations**.

All these designators fall within Spring AOP support, yet **they are not interchangeable**. If only a few methods need auditing, method-level `@annotation` is usually more accurate than a broader type-level annotation.

### 4.3. Keeping the annotation package stable

Using `@annotation(com.example.aop.MonitoredOperation)` removes coupling to the **target's** package, yet introduces a new dependency on the **FQCN of the annotation type**. Therefore:

- Place policy annotations in a stable API package/module, such as `com.example.platform.aop`.
- Keep annotation names and semantics clear; avoid renaming annotations with every service refactor.
- When an annotation type/package must change, update the matching expression and rerun integration tests.
- Do not mix technical annotations into domain code if the policy is purely technical and architecture requires domain modules not to depend on infrastructure; in that case consider a stable interface contract or another convention.

**Durability means choosing the least volatile element as the contract**, not eliminating every dependency altogether.

## 5. Interface strategy: anchoring to contracts instead of implementation classes

When an application already has a **stable business interface**:

```java
public interface PaymentOperations {
    Receipt process(PaymentRequest request);
}
```

You can write a pointcut based on the **type contract**:

```java
@Pointcut(
    "execution(public * *(..))"
    + " && target(com.example.api.PaymentOperations)"
)
public void paymentApiOperation() {}
```

This is a fragment inside an aspect; it requires the interface class to exist in the application.

`target(PaymentOperations)` in Spring AOP checks whether the **target object** belongs to that type contract. Thus replacing concrete implementation `LegacyPaymentService` with `NewPaymentCoordinator` can preserve matching if both classes implement the same interface and bean proxying behaves properly.

However, there are two boundaries:

1. **If the interface FQCN itself changes**, the pointcut still needs updating. Place contracts in low-churn API packages.
2. `target(PaymentOperations)` selects matching method executions performed by the target, **not just `process`**. If the policy targets only a subset, add method or marker conditions.

Example:

```java
@Pointcut(
    "target(com.example.api.PaymentOperations)"
    + " && @annotation(com.example.aop.MonitoredOperation)"
)
public void monitoredPaymentOperation() {}
```

When combined, the interface restricts **which objects receive the policy**; the annotation restricts **which methods carry the monitored intent**.

### `this` and `target` in Spring

In Spring AOP:

- `this(MyType)` checks whether the **Spring proxy reference** is type-compatible.
- `target(MyType)` checks the **proxied target object**.

With an interface-based JDK proxy, the proxy is not necessarily an instance of the concrete implementation; hence `this(ConcreteClass)` can differ from `target(ConcreteClass)`. When refactoring classes/interfaces, clarify whether you intend to match by **proxy contract** or **target type**. This is a Spring proxy-based AOP nuance that should be tested against the actual proxy strategy.

## 6. When to use package or Spring bean-name conventions?

### 6.1. Package convention

The expression:

```text
execution(public * com.example..service..*.*(..))
```

is useful if the organization maintains a **durable** package convention, such as placing every service under module `service` packages.

Strength: no need to annotate each method; renaming classes/methods inside the package generally leaves matching intact.

Weaknesses:

- Moving a class outside the matching package pattern → **silently loses match**.
- Placing an unintended class into a matching package → **unexpectedly gets advised**.
- If structure shifts from layer-based to feature-based (e.g., `orders.application`), the old pattern may no longer fit.
- Broad wildcards can match methods outside the policy's true responsibility.

Improvement: use a named pointcut `applicationServiceOperation()` to centralize the expression, document the package convention, and add regression tests when moving modules.

### 6.2. Spring-specific `bean(...)` pointcut

Spring AOP supports `bean(namePattern)` to select by **Spring bean name**, for example:

```java
@Pointcut("bean(*Service) && execution(public * *(..))")
public void namedServiceOperation() {}
```

This is a fragment inside a Spring `@Aspect`. `bean` is a **Spring-specific extension**, matching by **bean instance name** rather than Java class FQCN. It is helpful when bean names follow a controlled convention.

However, **renaming a class can implicitly change its default bean name** under component scanning:

```text
OrderService     -> default bean name: orderService
OrderCoordinator -> default bean name: orderCoordinator
```

If a pointcut uses `bean(*Service)`, renaming `OrderService` to `OrderCoordinator` can drop the match even though the class performs the same business work. For a more durable convention, declare an explicit bean name where genuinely needed, or use a marker/interface contract.

`bean(...)` is strictly for Spring AOP, **not a standard AspectJ weaving pointcut designator**. Do not rely on `bean` if you plan to port the same expression to AspectJ weaving outside Spring.

### 6.3. Comparing refactoring impact points

| Change | Hard-coded `execution` FQCN | `within` package convention | `@annotation` policy marker | `target(StableApi)` | `bean(*Service)` |
| --- | --- | --- | --- | --- | --- |
| Rename method | Easily breaks match | Usually unaffected | Unaffected if marker kept | Unaffected if still called via proxy | Usually unaffected |
| Rename implementation class | Easily breaks match | Usually unaffected | Unaffected if marker kept | Unaffected if interface kept | May alter default bean name |
| Move implementation package | Easily breaks match | Can break if moved out of pattern | Unaffected if marker FQCN stable | Unaffected if interface FQCN stable | Unaffected while bean name stays same |
| Move policy to another method | Must edit expression | Easy to over-match | Intentionally move marker | Need extra method/marker filter | Need extra method/marker filter |
| Change annotation/interface/API itself | Not necessarily | Not necessarily | Must update marker + expression | Must update interface + expression | Not necessarily |

How to read the table: **"unaffected" refers only to the text pattern**; it does not guarantee Spring AOP will run if the bean is no longer Spring-managed or the call bypasses the proxy.

## 7. Do not use overly broad wildcards just to "survive refactors"

Some choices look like easy fixes:

```java
@Before("execution(* *(..))")
public void anyMethod() {}
```

or:

```java
@Before("within(com.example..*)")
public void anyApplicationClassMethod() {}
```

These are illustrative fragments, not recommendations for production use.

Points to watch out for:

- Broad patterns easily attach advisors to beans that never carried the policy before.
- Advice can run on unrelated methods, increasing execution overhead, log volume, and coupling.
- Security or audit policies can accidentally wrap infrastructure methods, causing hard-to-spot consequences.
- When paired with dynamic conditions like `args(...)`, lacking clear scoping can increase matching overhead across many beans.
- A huge wildcard does not prove "resilience": it still depends on **whether the bean goes through a proxy**, context scope, method visibility, and runtime mechanisms.

Spring docs recommend **adequately scoped pointcuts**, preferably composed from meaningful named pointcuts. When using a stable annotation marker across multiple packages, `execution(public * *(..)) && @annotation(Marker)` can be reasonable because the annotation itself is an explicit filter. Even then, verify whether the annotation is misused and whether the app has performance constraints.

**Stability does not mean maximum match breadth.** A safe refactor preserves the **intended set of join points**, not one where advice intercepts everything.

## 8. Runnable Java 17+ example: class and method renamed, policy preserved

The example simulates two services in **different packages** with **different class/method names**:

- Old service: `com.example.orders.LegacyOrderService.submit()`.
- New service: `com.example.fulfillment.RenamedFulfillmentCoordinator.dispatch()`.
- Both have a method marked with `@MonitoredOperation`.
- The Spring `@Aspect` uses a **meaningful named pointcut** based on the annotation, without hardcoding either class or method name.
- An unmarked method serves as a negative control: it must run its business logic **without triggering advice**.

This simulates *before/after refactoring via two coexisting services* for easy comparison, not a requirement to deploy two parallel implementations in production.

Project versions: Java 17+, Spring Framework **6.1.14**, `aspectjweaver` **1.9.22.1**, Maven. These versions are pinned for learning and **not claimed to be the latest**.

### 8.1. Directory structure

```text
spring-stable-pointcuts/
├── pom.xml
└── src/main/java/com/example/
    ├── aop/MonitoredOperation.java
    ├── aop/ObservationAspect.java
    ├── orders/LegacyOrderService.java
    ├── fulfillment/RenamedFulfillmentCoordinator.java
    └── app/AppConfig.java
    └── app/DemoApp.java
```

### 8.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-stable-pointcuts</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.14</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.22.1</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` brings Spring IoC components and the necessary Spring AOP dependency in the dependency tree; `aspectjweaver` enables Spring to parse `@AspectJ` pointcut expressions. The example uses **Spring proxy-based AOP**, with no AspectJ compiler or weaving agent.

### 8.3. `src/main/java/com/example/aop/MonitoredOperation.java`

```java
package com.example.aop;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface MonitoredOperation {
}
```

The marker has runtime retention and applies only to methods. Placed in the stable `com.example.aop` package rather than inside the service package expected to change.

### 8.4. `src/main/java/com/example/orders/LegacyOrderService.java`

```java
package com.example.orders;

import com.example.aop.MonitoredOperation;

public class LegacyOrderService {

    @MonitoredOperation
    public String submit(String id) {
        System.out.println("[ORDER] submit " + id);
        return "submitted:" + id;
    }

    public String preview(String id) {
        System.out.println("[ORDER] preview " + id);
        return "preview:" + id;
    }
}
```

`submit` carries the marker; `preview` does not. Both methods are public and invoked from outside the bean through a Spring AOP proxy in the example.

### 8.5. `src/main/java/com/example/fulfillment/RenamedFulfillmentCoordinator.java`

```java
package com.example.fulfillment;

import com.example.aop.MonitoredOperation;

public class RenamedFulfillmentCoordinator {

    @MonitoredOperation
    public String dispatch(String id) {
        System.out.println("[FULFILLMENT] dispatch " + id);
        return "dispatched:" + id;
    }
}
```

The new class lies outside `com.example.orders`, is no longer named `OrderService`, and its method is no longer named `submit`. **Only the policy marker is preserved**. A brittle pointcut `execution(* com.example.orders.LegacyOrderService.submit(..))` would fail to match `dispatch()`; the marker-based pointcut still matches.

### 8.6. `src/main/java/com/example/aop/ObservationAspect.java`

```java
package com.example.aop;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.aspectj.lang.annotation.Pointcut;

@Aspect
public class ObservationAspect {
    private final AtomicInteger calls = new AtomicInteger();

    @Pointcut("execution(public * *(..))")
    public void publicMethod() {}

    @Pointcut(
        "publicMethod()"
        + " && @annotation(com.example.aop.MonitoredOperation)"
    )
    public void monitoredOperation() {}

    @Before("monitoredOperation()")
    public void beforeMonitoredCall(JoinPoint jp) {
        calls.incrementAndGet();
        System.out.println("[AOP] " + jp.getSignature().getName());
    }

    public int calls() {
        return calls.get();
    }
}
```

**Where does stability come from?**

- `publicMethod()` describes the kind of method Spring AOP should intercept.
- `monitoredOperation()` names the business/technical policy condition: a method marked with the marker.
- `@Before("monitoredOperation()")` contains neither `LegacyOrderService`, `RenamedFulfillmentCoordinator`, `submit`, nor `dispatch`.
- When renaming classes/packages/methods, simply keep the annotation on the target method and ensure the bean remains properly proxied.
- `JoinPoint.getSignature().getName()` prints the **actual invoked method name**; hence before refactoring it prints `submit`, and after refactoring it prints `dispatch`, without modifying advice logic.

`ObservationAspect` is a singleton Spring bean in the context because it is registered in `AppConfig`; the `AtomicInteger` counter measures advice invocations, not target bean count or how many times the pointcut signature method was called.

### 8.7. `src/main/java/com/example/app/AppConfig.java`

```java
package com.example.app;

import com.example.aop.ObservationAspect;
import com.example.fulfillment.RenamedFulfillmentCoordinator;
import com.example.orders.LegacyOrderService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public LegacyOrderService legacyOrderService() {
        return new LegacyOrderService();
    }

    @Bean
    public RenamedFulfillmentCoordinator fulfillmentCoordinator() {
        return new RenamedFulfillmentCoordinator();
    }

    @Bean
    public ObservationAspect observationAspect() {
        return new ObservationAspect();
    }
}
```

`@EnableAspectJAutoProxy` enables Spring's auto-proxy infrastructure; `proxyTargetClass=true` chooses CGLIB so the demo can inject/look up two concrete service classes without interfaces. **This is not a mandatory requirement for the marker policy**: systems with business interfaces can still use JDK proxies with appropriate adjustments.

When refactoring a bean, `@Bean` registration or component scanning configuration must also be updated, otherwise the new bean might not exist in the context. A durable pointcut **cannot compensate for misconfigured bean registration**.

### 8.8. `src/main/java/com/example/app/DemoApp.java`

```java
package com.example.app;

import com.example.aop.ObservationAspect;
import com.example.fulfillment.RenamedFulfillmentCoordinator;
import com.example.orders.LegacyOrderService;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApp {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {

            LegacyOrderService oldService =
                    context.getBean(LegacyOrderService.class);
            RenamedFulfillmentCoordinator newService =
                    context.getBean(RenamedFulfillmentCoordinator.class);
            ObservationAspect aspect =
                    context.getBean(ObservationAspect.class);

            System.out.println("oldProxy="
                    + AopUtils.isAopProxy(oldService));
            System.out.println("newProxy="
                    + AopUtils.isAopProxy(newService));

            System.out.println("oldResult=" + oldService.submit("O-1"));
            System.out.println("previewResult=" + oldService.preview("O-2"));
            System.out.println("newResult=" + newService.dispatch("F-3"));

            System.out.println("adviceCalls=" + aspect.calls());
        }
    }
}
```

Both beans are looked up from `ApplicationContext` and invoked via the references returned by Spring. There is no direct `new` of targets in the caller and no self-invocation skewing the output.

### 8.9. Run command and expected stdout

Requires JDK 17+, Maven able to download dependencies. In the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.app.DemoApp
```

Lines printed in order by the program and advice (excluding any Maven/Spring logs depending on environment):

```text
oldProxy=true
newProxy=true
[AOP] submit
[ORDER] submit O-1
oldResult=submitted:O-1
[ORDER] preview O-2
previewResult=preview:O-2
[AOP] dispatch
[FULFILLMENT] dispatch F-3
newResult=dispatched:F-3
adviceCalls=2
```

Interpretation:

1. Both Spring beans have marked methods, so the auto-proxy creator built corresponding AOP proxies.
2. `submit` is marked, so advice runs before the target.
3. `preview` is not marked, so **no `[AOP]` line** appears for that call even though `LegacyOrderService` is already a proxy.
4. `dispatch` belongs to a **different class and package** with a different method name, yet the marker preserves the policy so advice still runs.
5. `adviceCalls=2` proves only two methods were selected; calling just any method on a proxied bean does not trigger advice.
6. If `@MonitoredOperation` is deleted from `dispatch` after refactoring, Spring may still start normally, yet tests **must fail** when expecting advice on the new method.

This is an experiment demonstrating **policy semantics surviving a refactor**, not a recommendation to keep two similarly purposed services in a real production app.

## 9. Alternatives when you do not want to annotate individual methods

Not every codebase wants custom annotations scattered across application/service code. There are three other strategies:

### 9.1. Using a stable interface or class annotation in an API module

If multiple implementations conform to `BillingOperations`, use `target(com.example.api.BillingOperations)`. When changing the implementation class, the pointcut can remain valid.

If a policy applies to all public methods of a bean class, a class-level annotation + `@target` can reduce marker count compared to annotating every method.

Things to check: changing the interface/class annotation type, altering bean scopes/proxy interfaces, and changing the number of matched methods can alter the join point set.

### 9.2. Naming conventions backed by tests

In a stably modularized architecture, you can select `execution(public * com.example..application.*.*(..))`. The package organization rule must be documented as a contract and enforced in code reviews, architecture tests, or code checks. When moving a package outside the pattern, tests must detect the missing advice.

Never leave package naming as an implicit assumption known only to the original aspect author.

### 9.3. Explicit bean names for Spring-specific selection

Some applications want to identify a specific bean regardless of implementation class:

```java
@Service("primaryBillingService")
public class BillingAdapter {
    // ...
}
```

You can combine `bean(primaryBillingService)` with `execution(public * *(..))`. If you keep the Spring bean name stable across refactors, renaming the class/package does not necessarily break the rule.

These are **fragments**, not a runnable project. Suitable only when the bean name is genuinely part of a controlled contract. Duplicate bean names or multiple aliases must be accounted for; do not treat `bean(...)` as a universal solution for every aspect.

## 10. Designing tests to catch regressions during refactors

A Spring AOP test must verify **advice behavior**, not merely that the application context loads successfully. Include both **positive** and **negative** cases.

### 10.1. Before/after matrix

| Scenario | Before refactor | After refactor | Expected advice result |
| --- | --- | --- | --- |
| Method with `@MonitoredOperation` | `LegacyOrderService.submit()` | `RenamedFulfillmentCoordinator.dispatch()` | Still runs once per proxy invocation. |
| Method without marker | `preview()` | Equivalent unmarked method | Does not run this policy. |
| Bean moved to new package | `orders` | `fulfillment` | Still runs if annotation/contract is stable and bean is registered. |
| Bean no longer in Spring context | Before: Spring-managed | After: `new` instance | Spring AOP does not run; must fix bean boundary architecture. |
| Method called via `this` | Previously cross-bean call | Self-invocation after refactor | Advice can be bypassed; tests catch it. |
| Concrete method becomes `final` on class proxy | Interceptable method | CGLIB cannot override | Tests must detect missing interception or proxying failure. |

You do not need to test every permutation in the application if too costly. However, **methods carrying critical policies** must be covered by clearly named regression tests.

### 10.2. Testing through Spring proxies rather than instantiating targets with `new`

A test must use:

```java
LegacyOrderService service = context.getBean(LegacyOrderService.class);
service.submit("T-1");
```

instead of substituting:

```java
new LegacyOrderService().submit("T-1");
```

These are **fragments**. The second case tests only plain Java target logic and **proves nothing about the Spring AOP proxy**.

If using JDK proxies, look up/inject by business interface rather than concrete type, or configure class proxying intentionally. Do not flip the proxy type just to turn a test green without considering production injection contracts.

### 10.3. Verifying exact invocation counts and scope

An integration test can use a safe counter/event recorder to assert:

```text
markedOperation()    -> adviceCount +1
unmarkedOperation()  -> adviceCount +0
renamedMarkedMethod()-> adviceCount +1
```

If there are multiple aspects/advisors, count each policy separately. Do not take the total count of Spring proxies or advisors as proof that a particular `@Before` is running properly: a bean may be proxied due to other transaction/security/metric advice.

`AopUtils.isAopProxy(bean)` can serve as a supplementary check, yet only **asserting invocation behavior** verifies the pointcut.

### 10.4. Build-time checks and static review

An AspectJ pointcut string in `@Pointcut` is not a plain Java symbol reference. IDE rename refactoring may or may not update string literals depending on IDE/tooling. A safe workflow:

1. Find all `@Pointcut`, `@Before`, `@After*`, `@Around`, and XML `<aop:...>` elements containing expressions.
2. Search for exact old FQCN/method names inside pointcut expression strings, not just in Java imports/references.
3. Verify marker annotations, stable interfaces, bean names, and module boundaries.
4. Run business unit tests and **Spring AOP integration tests**.
5. Read Spring startup warnings, yet **never rely on successful startup** to conclude pointcuts are still accurate.

Example searches in a repository using `rg`:

```bash
rg -n '@Pointcut|@Before|@Around|@AfterReturning|@AfterThrowing' src/main/java
rg -n 'OldService|oldMethod|com\.example\.oldpackage' src/main/java src/main/resources
rg -n '<aop:|pointcut-ref|pointcut=' src/main/resources
```

These commands are merely source-inspection examples and modify no files. On PowerShell, `rg` must be installed separately; equivalent IDE search can be used instead.

## 11. Step-by-step refactoring when changing package or class names

A reliable Spring AOP refactoring workflow:

1. **Define the policy:** identify precisely which methods *must* run advice and which methods *must not*.
2. **Choose a stable anchor:** marker annotation, stable interface, class annotation, or governed package/bean convention.
3. **Centralize selection logic in a named pointcut:** e.g., `monitoredOperation()` instead of duplicating expressions across advice classes.
4. **Write behavior tests before refactoring:** assert advice events/counters, target return values, exceptions, and unmatched cases.
5. **Perform the rename/move** and update Spring bean registration/component scan/XML imports accordingly.
6. **Verify markers/contracts remain intact:** especially annotations on implementation methods, target classes/interfaces, and bean naming.
7. **Check Spring proxy boundaries:** ensure callers still go through Spring bean references; do not instantiate services with `new` or turn cross-bean calls into self-invocations.
8. **Audit all expressions for stale names:** including XML and strings in Java annotations, plus other proxy-based policies like `@Transactional`/caching.
9. **Rerun integration tests** with the exact Spring version, proxy type, and active profiles.
10. **Measure unintended impact:** when switching from hard-coded class patterns to annotations/markers, ensure no extra beans/methods were misannotated.

A named pointcut **does not prevent unintended policy changes**. It simply provides an anchor for discussion, review, and testing. Especially for auditing/security, changing the join point set changes system behavior and must be treated as a significant functional change.

## 12. Common pitfalls and diagnostics

| Post-refactor symptom | Possible cause | Action |
| --- | --- | --- |
| Spring still starts yet audit advice stops running | Expression contains old class/method name and no longer matches | Search string pointcuts and run positive interception tests. |
| Annotation marker kept yet advice disappeared | Bean not scanned, marker placed elsewhere, proxy/call boundary changed | Check Spring bean registry, annotation metadata on implementation, proxy, and invocation path. |
| Method renamed yet named pointcut keeps old name | Name `businessOperation()` is stable yet inner expression hardcodes old method | Update expression in one place, run tests; named pointcuts do not update meaning automatically. |
| Advice suddenly applies to too many methods | Replaced old exact signature with an overly broad wildcard | Constrain scope by business policy/marker and add negative tests. |
| Used `within(com.example..service..*)` then moved class to `application` | Package convention no longer matches | Update named scope rule or switch to a stable annotation/interface. |
| Used `bean(*Service)` and renamed class to `Coordinator` | Component-scan default bean name changed too, no longer matching pattern | Use explicit stable bean name or pick a policy marker. |
| `target(OldInterface)` pointcut stopped matching | Target no longer implements old interface or interface FQCN changed | Review contract and update anchor intentionally. |
| `@annotation` stopped matching after moving annotation to interface method | Method annotation metadata not preserved as assumed | Standardize markers on concrete implementations and test JDK/CGLIB per config. |
| Method changed to `private` or `final` | Proxy can no longer intercept as before | Review API/proxy contract; redesign public entry point when needed. |
| Advice disappeared after merging two services | Cross-bean call turned into `this.method()` | Split responsibilities across beans or redesign method boundary. |
| Pointcut expression fails to parse | Wrong referenced pointcut/type name, broken `&&`/`@annotation` syntax | Read exception during advisor creation, fix expression. |
| Bean still has `isAopProxy=true` yet audit policy does not run | Proxy carries another advisor while audit pointcut does not match | Check policy counter/event and advisors, not just the proxy boolean. |
| Old tests only asserted response and missed lost auditing | Advice behavior not tested | Add positive/negative interception assertions for the policy. |

## 13. Limitations that cannot be "solved" merely by stable pointcuts

Even with semantic markers and named pointcuts, Spring AOP still has boundaries:

- **Only Spring-managed beans** passing through the proxy infrastructure receive this style of advice.
- **Self-invocation** inside a target, such as `this.someMethod()`, does not go through the Spring proxy.
- **Objects created directly with `new`** outside the container are not auto-proxied under standard configuration.
- **JDK proxies** are interface-based, so methods outside the interface may have no call path through the proxy.
- **CGLIB class proxies** cannot override `final` classes/methods, `private` methods, or methods restricted by Java/module visibility.
- **Spring context boundaries** matter: an auto-proxy creator in one context does not automatically process beans existing only in another context.
- **Annotation markers do not register aspect beans:** `@Aspect` classes must be Spring-managed, e.g., via `@Component` or `@Bean`, with AOP enabled.

If a refactor changes these boundaries themselves, even a very "durable" pointcut may fail to run. You must redesign how the application invokes methods, not just tweak expression strings.

## 14. Pre-merge refactoring design checklist

- [ ] Pointcut expresses the **stable meaning** of the policy rather than coupling to arbitrary class/method names.
- [ ] Expressions are organized into **named pointcuts** with clear names for reuse.
- [ ] Chosen annotation/interface/bean-name convention anchor has a clear owner and documentation.
- [ ] No stale FQCN/method names remain in active pointcut strings or XML.
- [ ] Marker annotations remain where Spring AOP can detect them, with appropriate retention.
- [ ] New beans remain registered with Spring and caller invocations pass through proxies.
- [ ] JDK/CGLIB proxy type, method visibility, `final`, and context/scope were not altered unintentionally.
- [ ] Positive tests prove advice runs on renamed/moved methods.
- [ ] Negative tests prove advice **does not** run on out-of-policy methods.
- [ ] Tests verify exact advice execution counts, business results, and exceptions.
- [ ] No broad wildcards were added that leak policy out of scope.
- [ ] Startup/logs were checked, yet **do not replace** behavior tests.

### Official Spring Framework documentation

- Declaring a Pointcut, Combining Pointcut Expressions, Sharing Named Pointcut Definitions: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html
- Declaring Advice: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html
- Enabling @AspectJ Support: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html
- Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Schema-based AOP Support: https://docs.spring.io/spring-framework/reference/core/aop/schema.html

**Conclusion:** Keeping pointcuts stable during refactoring in Spring AOP means designing a **clear method-selection contract**: reusable pointcut names, low-churn anchors (annotations/interfaces/conventions), and integration tests verifying the exact invocations that must be advised. Do not trade stability for overly broad wildcards; what must be preserved is the **set of business behaviors governed by Spring Aspects**, not merely a pointcut string that still parses without error.
