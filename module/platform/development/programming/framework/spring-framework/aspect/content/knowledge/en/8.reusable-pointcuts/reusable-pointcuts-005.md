# Spring AOP — Distinguishing Pointcut Declaration Visibility from Matched Methods

## 1. Two kinds of visibility that are often confused

In Spring AOP using the `@AspectJ` annotation style, a **named pointcut** consists of two parts:

1. **The `@Pointcut` method declaration:** a Java method with a name, parameters (if needed), `private`/package-private/`protected`/`public` visibility, and a body normally left empty. This method represents a **name that other pointcuts/advice can reference**; its signature must return `void`.
2. **The `@Pointcut("...")` expression:** the **method execution matching** rule that Spring AOP parses to select where advice can be applied.

These are two independent dimensions. The visibility before the `void` keyword determines **who is allowed to reference the pointcut name** under Java visibility rules; visibility placed **inside the expression** such as `execution(public * *(..))` is what restricts **which methods are matched**.

```java
@Pointcut("execution(public * demo.visibility..*Service.*(..))")
private void servicePublicOperations() {}
```

- `private` on the declaration only states that the named pointcut `servicePublicOperations()` is used within the corresponding declaring scope, typically within the aspect itself.
- `public` inside `execution(public * ...)` is the condition requiring a **public target method**.
- The method `servicePublicOperations()` is not invoked to run business logic; it only names the expression.

Conversely:

```java
@Pointcut("execution(* demo.visibility..*Service.*(..))")
public void serviceOperations() {}
```

- `public void serviceOperations()` allows other aspects/classes to **reference the named pointcut** when using proper access syntax.
- The `*` character in the expression does not restrict method visibility to `public`. It is a wildcard for the return type, and there is no explicit visibility modifier in the method pattern.
- Even when an expression describes a broader set of methods, Spring AOP **can still intercept only calls passing through a Spring proxy** and methods supported by that proxy type. Making the declaration `public` **does not** turn `private`/`static`/`final` methods into interceptable ones.

**Core conclusion:** *the visibility of a pointcut declaration affects **name referencing**; it does not change the **matching** of the expression.* This rule is stated directly by Spring Framework in the "Declaring a Pointcut" documentation.

This lesson focuses solely on Spring AOP proxies and organizing/reusing named pointcuts in Spring; it does not go into general AOP or full AspectJ weaving.

## 2. `@Pointcut` syntax and the role of the declaring method

In `@AspectJ` syntax, the method declaring a named pointcut must return `void`; the method name is the symbol referenced by other pointcuts/advice. For example:

```java
@Pointcut("execution(public * com.example.service..*.*(..))")
private void selectedPublicServiceMethods() {}
```

`private` before `void` belongs to the **Java method declaring the pointcut**. `public` inside `execution(...)` is the **modifier required on the target method**. Calling the body of `selectedPublicServiceMethods()` like a regular Java method does not trigger advice. The lesson on declaring named pointcuts analyzes the full signature and binding.

## 3. Declaration visibility only affects how the named pointcut is reused

Java visibility rules govern **symbol reference rights**: `private` within the declaring type; package-private within the same Java package; `protected` by package/subclass access; `public` from other packages when the declaring class is also accessible. None of those modifiers adds or removes method executions matched by the expression.

Thus, `@Pointcut("execution(public * *(..))") private void p() {}` still selects **public target methods** when referenced by advice in the same class; `@Pointcut("execution(private * *(..))") public void p() {}`, despite exposing its symbol publicly, still cannot intercept private target methods with a Spring proxy. The lesson **"Pointcut Method Visibility and Reuse Scope"** has the access matrix and cross-module sharing examples.

## 4. Target method visibility is described inside the expression

**Target method visibility** must be specified **inside** the Spring AOP expression, for example:

```java
@Pointcut("execution(public * demo.visibility.OrderService.*(..))")
private void onlyPublicServiceMethods() {}
```

Breaking down each part:

- `execution(...)`: selects method **execution join points** supported by Spring AOP.
- `public`: the method modifier required to match.
- first `*`: any return type.
- `demo.visibility.OrderService`: declaring/target type expression.
- `*` before `(..)`: any method name.
- `(..)`: accepts any parameter list.

Another expression:

```java
@Pointcut("execution(* demo.visibility.OrderService.*(..))")
private void anyDeclaredServiceMethod() {}
```

does not constrain `public` in the modifier position. Descriptively, the expression is broader than the public-only case. However, **Spring AOP still has proxy limitations** — do not infer that every `private`/`static` method the expression text can describe will be advised.

### 4.1. `within(...)` does not automatically mean public

```java
@Pointcut("within(demo.visibility..*)")
public void inVisibilityModule() {}
```

`within` restricts the type/package to which the method execution belongs; it **has no condition requiring the method to be public**. If only public methods are required, write:

```java
@Pointcut("within(demo.visibility..*)"
        + " && execution(public * *(..))")
public void publicMethodsInModule() {}
```

A public pointcut declaration combining `within` also does not automatically introduce an `execution(public...)` condition.

### 4.2. Named pointcuts act like named expression macros

Example:

```java
@Pointcut("execution(public * *(..))")
private void publicMethods() {}

@Pointcut("within(demo.visibility..*)")
private void inModule() {}

@Pointcut("publicMethods() && inModule()")
public void publicModuleMethods() {}
```

When Spring parses `publicModuleMethods()`, the effective condition is **public method** AND **in the module**. The `private` modifier of the two helper pointcuts is not "propagated" as part of the matching condition. The `public` modifier on the composite pointcut only allows other modules to reference the pointcut symbol.

## 5. Spring proxy scope matters even more than expression visibility

Spring Framework primarily supports **method executions** that a proxy can receive. This creates a filter **independent** of the Java visibility of the `@Pointcut` method:

### 5.1. JDK dynamic proxy

A JDK proxy implements interfaces. In Spring AOP, it intercepts **public interface method calls** through the proxy reference. If a target has a public method only on the implementation and not exposed on the interface, a caller holding the interface proxy cannot invoke that method as a business API.

Example:

```java
interface WorkPort {
    void execute();
}

class WorkService implements WorkPort {
    @Override
    public void execute() {}

    private void helper() {}
}
```

With a JDK proxy implementing `WorkPort`, calling `port.execute()` through the proxy can be advised if the pointcut matches. `helper()` is not on the interface, so there is no public call on the proxy to intercept.

This has **nothing** to do with whether the advice's named pointcut is declared `public` or `private`.

### 5.2. CGLIB class-based proxy

CGLIB creates a subclass of the target (if the class can be subclassed). Spring AOP can intercept public and protected method calls on the proxy; some package-visible methods can also be intercepted if visibility allows. However:

- `private` methods cannot be overridden and cannot be advised by CGLIB.
- `final` instance methods cannot be overridden and cannot be advised by CGLIB.
- `static` methods are not instance-dispatched on the proxy.
- `final` classes cannot be subclassed by CGLIB.
- A package-private method not visible to a subclass in another package cannot be overridden in the standard way.
- Self-invocation `this.method()` still bypasses the proxy even when that method is public and overridable.

Spring documentation states clearly: if a pointcut is meant **only** for public methods, write the explicit public condition in the expression, even when the app uses CGLIB which can intercept some non-public methods. Do not use the visibility of a named pointcut as a proxy filter.

### 5.3. Two independent axes of control

| Case | Pointcut declaration visibility | Expression match | Does Spring AOP intercept? |
| --- | --- | --- | --- |
| `private void api()` with `execution(public * *(..))` | Private: referenced only in declaring type | Public methods | Possibly, when caller uses proxy and advice matches |
| `public void api()` with `execution(public * *(..))` | Public: shareable | Still public methods | Same as previous row |
| `public void broad()` with `execution(* *(..))` | Public: shareable | No modifier restriction | Only method calls supported by the proxy |
| `private void narrow()` with `execution(private * *(..))` | Private: internal helper | Describes private methods | Cannot intercept private methods with Spring AOP proxy |
| `public void p()` with `within(demo.visibility..*)` | Public: reusable | Type/package scope | Possibly even non-public in CGLIB if interceptable |
| `public void p()` with `execution(public * *(..)) && within(...)` | Public: reusable | Only public in scope | Only appropriate calls through proxy |

*"Possibly" is not a guarantee: the target bean must also be managed, aspect/advisor registered, pointcut matched, and call routed through the proxy.*

## 6. Runnable Maven example: private named pointcut matching a public target

A complete example using **Java 17, Maven, Spring Framework 6.2.x** without Spring Boot. Goals:

- Use a `private @Pointcut` to select a **public method** and observe advice execution.
- Use a `public @Pointcut` to expose a named pointcut whose expression **does not specify a visibility condition**.
- Another aspect uses the `public` named pointcut by its fully qualified name.
- A private helper on the target does not run advice, even though it resides in the class described by the public pointcut.
- A `this.pay()` call from the target does not pass through the AOP proxy, even though the target method is public.

We use two aspects with distinct advice applied to **two different methods** so stdout does not depend on the execution order of multiple advice methods on a single invocation.

### 6.1. Project structure

```text
spring-pointcut-visibility/
├── pom.xml
└── src/main/java/demo/visibility/
    ├── AppConfig.java
    ├── OrderService.java
    ├── LocalAspect.java
    ├── CommonPointcuts.java
    ├── SharedAspect.java
    └── Main.java
```

### 6.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-pointcut-visibility</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.24</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 6.3. `AppConfig.java`

```java
package demo.visibility;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackageClasses = AppConfig.class)
@EnableAspectJAutoProxy
public class AppConfig {
}
```

`@ComponentScan` discovers the target service and `@Component` aspects. `@EnableAspectJAutoProxy` enables AOP proxying. Since the target does not implement an interface, Spring Framework will use a class-based proxy for the target in this example. All externally observed methods are public/non-final.

### 6.4. `OrderService.java` — target with public methods and a private helper

```java
package demo.visibility;

import org.springframework.stereotype.Service;

@Service
public class OrderService {
    public void pay() {
        System.out.println("[target] pay");
    }

    public void notifyCustomer() {
        System.out.println("[target] notify");
        privateHelper();
    }

    public void batch() {
        System.out.println("[target] batch");
        this.pay(); // Self-invocation: does not go through the proxy.
    }

    private void privateHelper() {
        System.out.println("[target] privateHelper");
    }
}
```

`pay()` and `notifyCustomer()` are public methods that the Spring AOP proxy can intercept from an external caller; `privateHelper()` cannot be overridden/intercepted; `batch()` serves to demonstrate self-invocation.

### 6.5. `LocalAspect.java` — private named pointcut selecting public `pay()`

```java
package demo.visibility;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.aspectj.lang.annotation.Pointcut;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class LocalAspect {
    // private is the visibility of the METHOD DECLARING the pointcut.
    // public inside execution is the visibility of the TARGET METHOD.
    @Pointcut("execution(public * demo.visibility.OrderService.pay(..))")
    private void payPublicMethod() {}

    @Before("payPublicMethod()")
    public void beforePay() {
        System.out.println("[local advice] before pay");
    }
}
```

This is the central example: the **private** method `payPublicMethod()` is still a valid named pointcut and matches the **public** `OrderService.pay()`. Spring does not try to invoke `payPublicMethod()` as Java logic to run advice. The method declaration only provides the **name** used by `@Before` within the same aspect.

### 6.6. `CommonPointcuts.java` — public named pointcut shared across aspects

```java
package demo.visibility;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Pointcut;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class CommonPointcuts {
    // PUBLIC pointcut method so other aspects can reference it.
    // The expression has no public/protected/private condition.
    @Pointcut("execution(* demo.visibility.OrderService.*(..))")
    public void anyOrderServiceMethod() {}
}
```

This class serves as a library of named pointcuts. A `public @Pointcut` enables cross-aspect reuse. It does not automatically advise every method, nor does it create advice when no `@Before`/`@After`/`@Around` uses the expression.

### 6.7. `SharedAspect.java` — referencing a pointcut from another class

```java
package demo.visibility;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class SharedAspect {
    // Reuse the public pointcut from another aspect by FQN.
    // Intersect with a specific method so it does not overlap LocalAspect's advice.
    @Before("demo.visibility.CommonPointcuts.anyOrderServiceMethod()"
          + " && execution(public * demo.visibility.OrderService.notifyCustomer(..))")
    public void beforeNotify() {
        System.out.println("[shared advice] before notify");
    }
}
```

This proves that a **public named pointcut can be referenced from another aspect**. The modifier on `anyOrderServiceMethod()` permits cross-aspect reuse, while the **actual set of selected methods** is the intersection of the broad expression with `execution(public * ...notifyCustomer(..))`.

If you change the method in `CommonPointcuts` to `private` while keeping the FQN reference in `SharedAspect`, the configuration loses permission to reference the named pointcut as written. That is a **declaration visibility** issue, not a matching failure of `notifyCustomer()`.

### 6.8. `Main.java`

```java
package demo.visibility;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var ctx = new AnnotationConfigApplicationContext(AppConfig.class)) {
            OrderService orders = ctx.getBean(OrderService.class);

            System.out.println("isAopProxy=" + AopUtils.isAopProxy(orders));
            orders.pay();
            orders.notifyCustomer();
            orders.batch();
        }
    }
}
```

Run from the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.visibility.Main
```

Stdout lines printed by the program, excluding environment-dependent Maven/Spring logs:

```text
isAopProxy=true
[local advice] before pay
[target] pay
[shared advice] before notify
[target] notify
[target] privateHelper
[target] batch
[target] pay
```

**Why does this output occur?**

1. `OrderService` is a Spring bean; Spring has advisors from both aspects and can create a CGLIB proxy (target has no interface). `isAopProxy=true`.
2. Caller invokes `orders.pay()` through the proxy. The advice referencing the private pointcut `payPublicMethod()` matches the public target method `pay()` and runs.
3. Caller invokes `orders.notifyCustomer()` through the proxy. The advice in `SharedAspect` references the public named pointcut of `CommonPointcuts`; the combined branch selects `notifyCustomer()`.
4. `privateHelper()` is called directly by the target; there is no advice because private methods cannot be overridden by CGLIB.
5. `orders.batch()` matches no advice in this example. Inside target `batch()`, `this.pay()` bypasses the proxy, so `[target] pay` is printed without `[local advice]` before it.
6. No two advice methods hit the same invocation in this example, so no assumptions about execution order across multiple advice methods on one method are needed.

Note that if other advice exists in a real application, stdout will include extra lines depending on pointcuts and advice order. The program above registers only the aspects declared in the example directory.

## 7. Experiments verifying both visibility axes

### Experiment A — Changing the private pointcut to public

In `LocalAspect`, change only:

```java
@Pointcut("execution(public * demo.visibility.OrderService.pay(..))")
public void payPublicMethod() {}
```

Leave the expression and advice unchanged. When rerun, the `[local advice] before pay` lines still appear **exactly as before**. The pointcut's matching set does not depend on whether the declaration is `private` or `public`.

### Experiment B — Changing the public pointcut to private

In `CommonPointcuts`, change:

```java
@Pointcut("execution(* demo.visibility.OrderService.*(..))")
private void anyOrderServiceMethod() {}
```

Keep the FQN reference in `SharedAspect`. The Spring/AspectJ parser does not have permission to reference a **private named pointcut** from another type as a public API. The result may be a **pointcut parsing / ApplicationContext initialization error** rather than a change in the number of matched methods. Do not rely on the exact exception name because messages depend on library versions.

Fix by keeping reusable methods `public`, or placing a separate expression inside the same aspect when only internal use is needed.

### Experiment C — Keeping the public declaration, narrowing the expression to private

Change the pointcut in `CommonPointcuts` to:

```java
@Pointcut("execution(private * demo.visibility.OrderService.*(..))")
public void onlyPrivateOrderMethods() {}
```

At the same time, update the advice to reference the new name, for example:

```java
@Before("demo.visibility.CommonPointcuts.onlyPrivateOrderMethods()")
public void beforePrivate() {
    System.out.println("[shared advice] before private");
}
```

Both fragments must be updated **in sync** across the two files to reference the exact name. On a standard Spring AOP proxy, private `OrderService.privateHelper()` cannot be intercepted by CGLIB, so internal calls to the helper still receive no advice. Declaring the named pointcut `public` **grants no extra ability to intercept private methods**.

### Experiment D — Keeping the private declaration, broadening the expression

In `LocalAspect`, change:

```java
@Pointcut("execution(public * demo.visibility.OrderService.*(..))")
private void payPublicMethod() {}
```

The name `payPublicMethod` may no longer accurately reflect the expression's meaning; this is a **name that should be changed** when genuinely broadening a pointcut. If you keep the name and advice as-is, it can advise `pay()`, `notifyCustomer()`, and `batch()` when called externally through the proxy. This is a change in **matching caused by editing the expression**, not by the pointcut method being private.

Because this is easy to confuse while debugging, name pointcuts to describe the **matching condition**, avoiding names tied to the declaration's modifier. For example, a better name is `publicOrderServiceMethods()`.

## 8. Why can a private pointcut match a public method while a private target method is not advised?

These two situations are completely different:

**Case 1 — private named pointcut:**

```java
@Pointcut("execution(public * demo.visibility.OrderService.pay(..))")
private void chosenPay() {}

@Before("chosenPay()")
public void beforePay() {
    System.out.println("before pay");
}
```

The Java method `chosenPay()` has private visibility, yet it is not the target method being advised. It is merely a way of naming the expression. Spring AOP does not need external callers to invoke `chosenPay()`.

**Case 2 — private target business method:**

```java
public class OrderService {
    private void privateHelper() {
        System.out.println("helper");
    }
}
```

The method `privateHelper()` is an internal business/implementation method inside the target. With Spring AOP proxies, private methods are not on the JDK interface proxy surface and cannot be overridden by a CGLIB subclass. Even if the aspect's named pointcut is `public`, Spring still cannot intercept this private invocation.

**Never say "a private pointcut cannot catch methods."** Always ask: **is it `private` on the pointcut-declaring method or `private` on the target method?**

## 9. Mistakes when organizing named pointcuts in Spring projects

Three categories of mistakes are commonly conflated:

- **Declaration visibility:** another aspect references `OtherAspect.privatePc()` and fails to resolve; either publish a public named pointcut or move the rule to the proper owner.
- **Target visibility:** an expression without `public` can describe a broader set of methods, yet JDK proxies only expose interface methods and CGLIB does not override `private`/`final` target methods. Changing the named pointcut's modifier will not fix this limitation.
- **Invocation boundary:** the target may match the expression while `this.pay()` or `new Service().pay()` does not pass through the Spring proxy; the aspect bean must also be registered in the proper context.

A Spring bean having a proxy does not mean every method is advised. Assert the output/counter of the **specific advice**, comparing a matched public target method against a private/final or out-of-scope method that cannot be intercepted.

## 10. Self-check questions

**Self-check:**

1. Can `@Pointcut("execution(public * *(..))") private void anyPublic() {}` match a public service method? **Yes**, if advice in the same class references it and the target is called through the proper proxy.
2. Does changing `private` to `public` on a named pointcut alter the matched method set? **No**, when the expression/configuration stays unchanged; only the reference scope is broadened.
3. Can `@Pointcut("execution(* *(..))") public void allMethods() {}` advise a private target method? **No**, via a standard Spring AOP proxy.
4. Does `protected @Pointcut` select protected target methods? **Not automatically**; to filter target modifiers, place the condition inside the expression.
5. Why is self-invocation still not advised when the method is public? Because the `this.method()` call bypasses the Spring proxy.

**Documentation:** [Spring — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html), [Spring — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html).

