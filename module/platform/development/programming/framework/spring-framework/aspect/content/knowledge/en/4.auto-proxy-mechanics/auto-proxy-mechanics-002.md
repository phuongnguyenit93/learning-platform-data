# Identifying Advisors Matching Target Classes and Methods in Spring AOP

## 1. The Problem Spring Auto-Proxy Must Solve

In a Spring application, there may be many **advisors** from `@Aspect`s and other AOP components, but not every advisor applies to every bean and every method. Spring needs to answer two different questions:

1. **When preparing a Spring bean:** which advisors *can potentially* affect at least one method of the target class? If there are matching advisors and other exclusion rules do not prevent it, the bean can be wrapped with an AOP proxy.
2. **When a client invokes a method through the proxy:** among the advisors attached to the proxy, which advisors actually match the method being called and — if the pointcut requires it — the **runtime arguments** of that specific call?

For example: an `OrderService` has three methods `checkout()`, `status()`, `cancel()`, while an advisor only applies to `checkout()`. Spring may proxy **the `OrderService` bean**, while only **calls to `checkout()`** go through that advisor's advice. The existence of a proxy does not mean every method runs every advice.

This lesson is about **the advisor matching mechanism in proxy-based Spring AOP**; it focuses on Spring auto-proxying, class/method matching, the proxy-creation decision point, and when advice runs. General aspect knowledge is not repeated.

## 2. Participating Components

| Component in Spring | Role in the matching step |
| --- | --- |
| `Advisor` (`org.springframework.aop.Advisor`) | Represents advice and additional metadata needed to use the advice. |
| `PointcutAdvisor` | A type of advisor that has a `Pointcut` to determine **where to apply advice**. |
| `Pointcut` | Provides two parts: `ClassFilter` to inspect the target class, `MethodMatcher` to inspect methods and sometimes runtime arguments. |
| `ClassFilter` | Answers whether a `Class<?>` falls within the pointcut's scope. |
| `MethodMatcher` | Answers whether a specific method on the target class can match, and whether additional per-call checks are needed. |
| `AopUtils.canApply(...)` | Spring AOP utility to evaluate whether a pointcut/advisor **can apply** to a target class. |
| `AopUtils.findAdvisorsThatCanApply(...)` | Filters a list of candidate advisors to obtain those that can apply to the target class. |
| `AnnotationAwareAspectJAutoProxyCreator` | A Spring auto-proxy creator that recognizes both advisor beans and advice declared in Spring-managed `@Aspect` beans. |
| `AopProxy` | JDK proxy or class-based proxy (CGLIB) that executes the interceptor chain when a call goes through it. |

Key Spring API definitions (illustrating signatures only; real interfaces have additional details):

```java
interface Pointcut {
    ClassFilter getClassFilter();
    MethodMatcher getMethodMatcher();
}

interface ClassFilter {
    boolean matches(Class<?> clazz);
}

interface MethodMatcher {
    boolean matches(Method method, Class<?> targetClass);
    boolean isRuntime();
    boolean matches(Method method, Class<?> targetClass, Object... args);
}
```

Distinguish clearly:

- `ClassFilter.matches(...)` inspects the **target class**; it does not yet confirm a specific method will receive advice.
- `MethodMatcher.matches(method, targetClass)` is a **static check** that can be performed before calls run.
- If `isRuntime()` returns `true`, Spring may also call `matches(method, targetClass, args)` per invocation, because the outcome also depends on the actual arguments.
- `canApply(advisor, targetClass) == true` means the advisor **can potentially apply to part of the class**, not that the current invocation will definitely trigger advice.

Spring can optimize/cache static matching parts. You should not assume Spring always re-scans all advisor beans for every call.

## 3. How Does Spring Select Advisors When Creating a Bean Proxy?

The diagram below is a conceptual flow for a Spring AOP configuration with auto-proxying. Class/method names help orient you when reading Spring source code; this is **not a guarantee that every Spring version always runs every internal step in an immutable order**.

```text
ApplicationContext with Spring AOP auto-proxy creator
        |
        +-- Registered Advisor beans
        |
        +-- Registered @Aspect beans
                  -> convert @AspectJ advice into advisors
        |
        v
List of candidate advisors
        |
        v
Target bean being evaluated: bean name + target class
        |
        +-- Skip objects outside auto-proxy scope
        |
        +-- Filter advisors that can apply to target class:
        |      ClassFilter + MethodMatcher (static check)
        |
        +-- Sort / finalize matching advisors
        |
        +-- If matching advisors exist and bean is proxy-eligible:
        |      create AOP proxy for target bean
        |
        +-- If no matching advisors exist:
               usually return original bean, do not create proxy for that advisor
        |
        v
Client calls method through proxy
        |
        +-- Select interceptor chain for method
        +-- Check runtime conditions if required by pointcut
        +-- Run matching advice then invoke target method
```

In the `AbstractAdvisorAutoProxyCreator` family, useful method names when reading source code or debugging are:

```text
findCandidateAdvisors()
findEligibleAdvisors(beanClass, beanName)
findAdvisorsThatCanApply(candidateAdvisors, beanClass, beanName)
sortAdvisors(...)
```

With `@AspectJ` support, Spring also reads advice on **aspect beans** to include them in the list of candidate advisors. These steps happen during Spring's bean-creation/post-processing lifecycle, before normal callers receive the proxy reference.

### 3.1. Candidate Advisor vs. Eligible Advisor

- **Candidate advisor** is an advisor Spring has discovered from AOP configuration, which may target many different beans.
- **Eligible advisor** is an advisor that can apply to **the bean class being evaluated**, based on the pointcut and related Spring conditions.
- **Advice executed at an invocation** is an even narrower layer: only interceptors/advice matching the method (and runtime conditions) of the invocation run.

An advisor for `OrderService.checkout()` is still a candidate when Spring evaluates `InvoiceService`, but does not become eligible for a class that has no method matching that expression.

### 3.2. Do Not Confuse Class-Level Filtering with Method-Level Filtering

Suppose the pointcut is:

```java
@Before("execution(* example.OrderService.checkout(..))")
```

With `OrderService` containing both `checkout()` and `status()`:

- **At the bean/class level:** at least one method is targeted by the pointcut, so the advisor *can* apply to the bean.
- **At the method level:** `checkout()` matches, `status()` does not match.
- **At the call level:** the call to `checkout()` must go **through the proxy** and satisfy execution conditions to receive advice.

Spring AOP does not automatically insert advice into every method of `OrderService` just because a proxy exists.

## 4. Runnable Java 17+ Example: One Bean Proxied, One Bean Not

Plain Spring Framework example with `@EnableAspectJAutoProxy`. Uses **Spring Framework 6.2.19** and **AspectJ Weaver 1.9.25.1**. This short sample illustrates simultaneously: how Spring determines which class has matching advisors, how methods match, and the result of calling through the proxy.

### 4.1. Project Structure

```text
advisor-matching-demo/
├── pom.xml
└── src/main/java/example/
    ├── AppConfig.java
    ├── AuditAspect.java
    ├── OrderService.java
    ├── InvoiceService.java
    └── Main.java
```

**`pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>advisor-matching-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.19</spring.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.25.1</version>
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

**`OrderService.java`**

```java
package example;

public class OrderService {
    public void checkout() {
        System.out.println("order: checkout");
    }

    public void status() {
        System.out.println("order: status");
    }
}
```

**`InvoiceService.java`**

```java
package example;

public class InvoiceService {
    public void checkout() {
        System.out.println("invoice: checkout");
    }
}
```

**`AuditAspect.java`**

```java
package example;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class AuditAspect {
    @Before("execution(* example.OrderService.checkout(..))")
    public void beforeCheckout() {
        System.out.println("audit: before checkout");
    }
}
```

**`AppConfig.java`**

```java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy
public class AppConfig {
    @Bean
    public OrderService orderService() {
        return new OrderService();
    }

    @Bean
    public InvoiceService invoiceService() {
        return new InvoiceService();
    }

    @Bean
    public AuditAspect auditAspect() {
        return new AuditAspect();
    }
}
```

**`Main.java`**

```java
package example;

import java.lang.reflect.Method;
import org.springframework.aop.aspectj.AspectJExpressionPointcut;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) throws Exception {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            var order = context.getBean(OrderService.class);
            var invoice = context.getBean(InvoiceService.class);

            System.out.println("order proxy: " + AopUtils.isAopProxy(order));
            System.out.println("invoice proxy: " + AopUtils.isAopProxy(invoice));

            var pointcut = new AspectJExpressionPointcut();
            pointcut.setExpression(
                "execution(* example.OrderService.checkout(..))"
            );

            System.out.println("order class eligible: "
                + AopUtils.canApply(pointcut, OrderService.class));
            System.out.println("invoice class eligible: "
                + AopUtils.canApply(pointcut, InvoiceService.class));

            Method checkout = OrderService.class.getMethod("checkout");
            Method status = OrderService.class.getMethod("status");
            System.out.println("checkout matches: "
                + pointcut.getMethodMatcher().matches(checkout, OrderService.class));
            System.out.println("status matches: "
                + pointcut.getMethodMatcher().matches(status, OrderService.class));

            order.checkout();
            order.status();
            invoice.checkout();
        }
    }
}
```

In the directory with `pom.xml`, run:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.Main
```

Lines printed by the program in order:

```text
order proxy: true
invoice proxy: false
order class eligible: true
invoice class eligible: false
checkout matches: true
status matches: false
audit: before checkout
order: checkout
order: status
invoice: checkout
```

### 4.2. Analyzing the Output Layer by Layer

1. `AuditAspect` is registered as a Spring bean via `@Bean`; `@EnableAspectJAutoProxy` enables Spring AOP. `@Aspect` alone cannot replace the bean registration step.
2. Spring finds an advisor from `@Before` whose pointcut matches `OrderService.checkout()`. `OrderService` has a matching advisor, so Spring creates a proxy for that bean.
3. `InvoiceService` also has a method named `checkout()`, but **it is not the `example.OrderService` class**, so the pointcut in the example does not match; `invoice proxy: false` is the result when no other advisor applies to it.
4. `AopUtils.canApply(pointcut, OrderService.class)` shows that at the class level there exists at least one method that can potentially match. A `true` result **does not mean** all methods on the class match.
5. `getMethodMatcher().matches(checkout, OrderService.class)` is `true`, whereas for `status()` it is `false`.
6. Calling `order.checkout()` through the proxied bean runs the advice, then the business method. Calling `order.status()` still goes through the same proxy, but **has no corresponding advice**. `invoice.checkout()` calls the unproxied `InvoiceService` bean in this configuration, so there is also no audit line.

In the diagnostic step, `AspectJExpressionPointcut` is created separately to illustrate the static check using **the same expression** as `@Before`; this is an independent check object, not the advisor object sitting inside the proxy. Do not equate the result of `AopUtils.canApply` with retrieving the list of advisors installed on a specific proxy.

## 5. Static and Dynamic Filtering Rules in `MethodMatcher`

### 5.1. Static Matching

A method matcher that does not need per-call data can decide based on the method signature and target class. With the pointcut:

```text
execution(* example.OrderService.checkout(..))
```

Spring has enough information to recognize the suitability of the `checkout()` method from the class/method. Evaluating types and methods before building the proxy avoids doing unnecessary checks on every invocation.

In the Spring AOP API, `MethodMatcher.matches(Method, Class)` is used to test whether a method **can** match; `isRuntime() == false` means there is no `matches(Method, Class, Object... args)` step on each call.

### 5.2. Dynamic Matching: Conditions Depending on Actual Arguments

Some pointcuts depend on runtime data, such as an `args(...)` constraint. The following example is just a **supplementary illustrative snippet**, not part of the standalone program in section 4:

```java
// In a target bean with a method:
public void handle(Object value) {
    System.out.println("handling: " + value);
}
```

Corresponding aspect:

```java
// Inside an @Aspect class registered as a Spring bean:
@Before("execution(* example.OrderService.handle(..)) && args(java.lang.String)")
public void beforeStringValue() {
    System.out.println("argument is String");
}
```

For a method whose declared parameter is `Object`, `handle("A")` has a runtime argument of `String`, while `handle(42)` has a runtime argument of `Integer`. If both calls go through the Spring proxy, the `args(java.lang.String)` condition can select only the first call. **A method chosen as a candidate when creating the proxy does not guarantee every call to it satisfies the pointcut.**

Distinguish clearly:

- `execution(...)` usually describes the method signature and method join point type.
- `args(...)` concerns the **actual** argument type at call time and may require a runtime test.
- `@args(...)` concerns annotations on the runtime type of arguments, distinct from `@annotation(...)` on the **method** being executed.
- If a pointcut uses `&&`, all constraint parts must hold; with `||`, one matching branch may suffice.

Do not assume every pointcut containing `args` necessarily incurs exactly one dynamic match check under all internal optimizations; use `MethodMatcher.isRuntime()` when you actually need to inspect a matcher instance.

## 6. Common Spring AOP Expressions and Their Impact on Matching

The expressions below are **templates to place in advice annotations such as `@Before("...")`**, with classes/packages/annotations that actually exist in the project. They are not standalone Java programs.

| Expression | Factor used to restrict scope |
| --- | --- |
| `execution(* com.acme.order.OrderService.checkout(..))` | Method named `checkout` on `OrderService` with any number of parameters; matches method execution |
| `execution(public * com.acme.order..*Service.*(..))` | `public` methods of types ending with `Service` in matching packages |
| `within(com.acme.order..*)` | Method executions within types belonging to the corresponding package |
| `@annotation(com.acme.audit.Audited)` | Method executions bearing the `@Audited` annotation |
| `@within(com.acme.audit.AuditedType)` | Method executions belonging to types annotated with `@AuditedType` per PCD semantics |
| `target(com.acme.order.OrderService)` | Target object belongs to the specified type |
| `this(com.acme.order.OrderService)` | **Proxy** satisfies the specified type; differs from target when using a JDK proxy |
| `args(java.lang.String)` | Runtime argument type matches |
| `bean(orderService)` | Spring bean **with a matching name**; `bean()` is a Spring-specific PCD |

Several notable consequences:

- `execution(* ...)` targets **method execution** on Spring-managed beans; Spring proxies do not support every AspectJ join point such as constructor/field access.
- `bean(orderService)` can determine scope based on **bean name** when selecting advisors for a specific bean. It is not purely a Java class check.
- With `this(...)`, matching is based on the **proxy** type, whereas `target(...)` is based on the target object; the two results can differ when using a JDK dynamic proxy.
- A pointcut expression matching does not guarantee advice will run if the call **does not go through the proxy** or the method cannot be intercepted by the proxy.

### 6.1. Bean Name Can Determine Applicability

Suppose two Spring beans both return instances of the same `OrderService` class, but are named `importantOrderService` and `backupOrderService`. With the advice:

```java
@Before("bean(importantOrderService) && execution(* *.checkout(..))")
public void beforeImportantCheckout() {
    // ...
}
```

Spring can apply the advisor only to the bean with the matching name, even though the target class is identical. Therefore, during the auto-proxy advisor-selection phase, **the bean name can also be a necessary part of the context**. Do not just call `AopUtils.canApply(..., OrderService.class)` and conclude that every bean of the same class will receive the exact same list of advisors: a utility check on a `Class` alone does not carry the full bean-name context.

## 7. Matching Does Not Guarantee the Proxy Always Intervenes

An advisor may be determined eligible at the class/method level, yet the actual call still fails to run advice if it hits Spring AOP proxy boundaries.

### 7.1. Self-Invocation

```java
// Illustrated inside a target bean, not a standalone program.
public void checkout() {
    this.finalizeOrder();
}

public void finalizeOrder() {
    // ...
}
```

If a caller invokes `proxy.checkout()`, the external call goes through the proxy. But when the body of `checkout()` calls `this.finalizeOrder()`, that is a direct call inside the target, **not going back through the proxy**. Therefore, advice targeting only `finalizeOrder()` will not automatically run for that internal call, even though the pointcut evaluates the `finalizeOrder()` method as matching.

A common way to handle this: extract the responsibility that needs advice into a separate Spring bean, inject that bean, and call it through the reference provided by Spring.

### 7.2. Method Proxyability

With a **JDK dynamic proxy**, callers mainly invoke public methods declared on the proxy's interfaces. With a **class-based proxy/CGLIB**, Spring can proxy eligible methods that can be overridden, however:

- A `final` class cannot be subclassed to create a class-based proxy.
- A `final` method cannot be overridden to be advised under that mechanism.
- A `private` method cannot be advised via the proxy method-override mechanism.
- Constructors, field access, and `static` calls are not method-execution join points of a Spring AOP proxy.

These limitations are **separate** from whether the pointcut expression is syntactically valid or whether the advisor was found.

### 7.3. Spring Beans and Aspect Beans

Spring AOP auto-proxying applies to eligible beans inside the Spring container. An object instantiated manually with `new OrderService()` outside the container does not automatically receive the proxy of a bean of the same class. On the other hand, `@Aspect` classes themselves are not ordinary targets for auto-proxying by other aspects; do not use `AopUtils.isAopProxy(aspectBean)` as the sole test to conclude whether an aspect was registered.

## 8. Differences Between "Has Proxy", "Has Advisor", and "Advice Ran"

| Observation | What can be concluded | What **cannot** yet be concluded |
| --- | --- | --- |
| `AopUtils.isAopProxy(bean) == true` | The reference held is a Spring AOP proxy | Every method/every call runs a specific advice |
| `AopUtils.canApply(pointcut, Target.class) == true` | The pointcut **can** apply to at least one method of the target class | The pointcut is installed on the proxy for a specific bean or matches all runtime arguments |
| A method has static match `true` | Can match by signature and class | Calls go through the proxy and all dynamic conditions hold |
| `AopUtils.isAopProxy(bean) == false` | The reference is not a Spring AOP proxy | Why the bean lacks a proxy; could be no advisor, configuration, or an object outside the container |
| Log inside advice appears | Advice executed in the observed call path | Other calls always run the advice too |
| A bean has no matching advisor | Not proxied **by that set of advisors** | Could still be proxied by another advisor/infrastructure mechanism |

Key point to emphasize when debugging: **Spring decides proxying at the bean level**, whereas **an invocation runs advice at the method/invocation level**. The two decisions are related, not identical.

## 9. Inspecting Actual Advisors on a Proxy

After retrieving a bean from `ApplicationContext`, you can check whether the proxy allows inspecting its advice configuration using `org.springframework.aop.framework.Advised`. In a typical Spring AOP proxy configuration, the proxy can implement this interface.

Illustrative snippet using the `order` object from section 4's example:

```java
// Snippet added to Main.java (not standalone):
import org.springframework.aop.Advisor;
import org.springframework.aop.PointcutAdvisor;
import org.springframework.aop.framework.Advised;

if (order instanceof Advised advised) {
    for (Advisor advisor : advised.getAdvisors()) {
        System.out.println(advisor.getClass().getName());

        if (advisor instanceof PointcutAdvisor pcAdvisor) {
            System.out.println(pcAdvisor.getPointcut().getClass().getName());
        }
    }
}
```

The snippet above may print advisor/pointcut class names depending on version and configuration; **you should not hardcode stdout** of Spring's internal infrastructure structure in lessons. This is an observation tool, while the ultimate confirmation of behavior remains calling the method through the proxy and seeing the advice execute.

Some proxies are configured not to expose `Advised` or not to allow modifying advice; therefore use an `instanceof Advised` check rather than casting blindly.

### Checking with Logs and Debugger

If you want to trace the advisor-selection process in Spring Framework, you can use a debugger to set breakpoints at points such as:

```text
AbstractAdvisorAutoProxyCreator.findEligibleAdvisors(...)
AbstractAdvisorAutoProxyCreator.findAdvisorsThatCanApply(...)
AopUtils.findAdvisorsThatCanApply(...)
AopUtils.canApply(...)
```

Note:

- A Spring Boot application may have many kinds of advisors and other infrastructure beans; seeing many advisor candidates is normal.
- Spring versions may change internal method details, caching, or call order. Only use breakpoints to observe the version **actually running**.
- When `@Order` or `Ordered` is present, Spring can sort advisors to determine advice order; **sorting does not turn a non-matching advisor into a matching one**.
- If you only see a proxy created without seeing the advice line, distinguish between **the advisor was not selected for the bean** and **the method/runtime invocation did not match**.

## 10. Diagnosing Non-Matching Advisors

Perform checks in order to locate the exact layer where the issue arises.

### Step 1. Confirm the Aspect/Advisor Is Registered by Spring

- For `@Aspect`, verify the aspect class is a Spring bean (`@Component` within scan scope or `@Bean`).
- For `@EnableAspectJAutoProxy`, verify the annotation is in the right context; on Spring Boot, check the AOP/AspectJ starter and auto-configuration.
- Do not confuse an aspect class existing on the classpath with an advisor discovered by Spring.

### Step 2. Confirm the Target Bean and Type Are Correct

- Does `context.getBean(OrderService.class)` retrieve the expected bean?
- Are there multiple beans with the same interface, different bean names, or multiple `ApplicationContext`s?
- The pointcut `execution(* example.OrderService.checkout(..))` will not automatically extend to a class with the same method name in another package.

### Step 3. Check Class Matching Then Method Matching

- Use `AopUtils.canApply(pointcut, Target.class)` to determine whether there is a **possibility** of matching any method of the class.
- Use `pointcut.getMethodMatcher().matches(method, Target.class)` to check **a specific method** when using Spring's `Pointcut` API.
- If the pointcut uses `bean(name)`, you must check the **bean name/context** itself, not just the type.
- With `args(...)` or runtime conditions, check the argument type/value at call time rather than only the method signature.

### Step 4. Check the Proxy and Call Path

- `AopUtils.isAopProxy(context.getBean(...))` checks the reference from the container.
- Check whether the code calls `new`, calls `this.method()`, calls `private`/`final` methods, or accesses a method outside the JDK proxy's interface.
- If the expression matches but the call bypasses the proxy, Spring AOP will not run the advice.

### Step 5. When Multiple Advisors Exist

- Another advisor can cause a proxy to be created even when the advisor you care about **does not match**.
- Identify **which advisor** was selected, then inspect that advisor's method matcher.
- If an advisor has dynamic matching, the same method may run advice on one call and not on another.
- `@Order` mainly adjusts **execution order** among matching advisors; it does not fix a wrong pointcut.

### Common Error Table

| Symptom | Possibilities to check |
| --- | --- |
| `@Aspect` has advice, but no bean gets proxied | Aspect is not a bean yet; auto-proxy is not enabled; AOP dependencies are incomplete |
| Bean has a proxy, `checkout()` runs advice, `status()` does not | Completely normal if the advisor only matches `checkout()` |
| Two beans have the same method name, but only one receives advice | Pointcut restricts by package/class, annotation, target type, or bean name |
| Same method, but advice sometimes runs and sometimes does not | Pointcut has conditions on runtime arguments; or different call paths/bean references |
| Pointcut matches the method, but calling via `this` does not run advice | Self-invocation bypasses the proxy |
| Proxy exists, but your advice does not run | Proxy may have been created by another advisor; the advisor in question may not be eligible or the method does not match |
| `ClassFilter` matches, but `MethodMatcher` does not | Class is in the broad scope, specific method does not match signature/scope |
| `ClassCastException` when casting a JDK proxy to the implementation class | Interface-based proxy; inject/call via the interface or check the configured proxy strategy |

## 11. Knowledge-Check Scenarios

**Scenario 1:** A `PaymentService` has methods `pay()`, `refund()`; there is only an advisor `execution(* example.PaymentService.pay(..))`. The bean is proxied; does calling `refund()` run the advice?

**Answer:** It does not run this advice if `refund()` does not match. Spring can proxy the whole bean because at least one method matches, but the advice must specifically match the method actually invoked.

**Scenario 2:** Two beans of the same class `PaymentService`, named `primaryPayment` and `secondaryPayment`. The advice uses `bean(primaryPayment) && execution(* *.pay(..))`. Do the two beans have the same list of advisors?

**Answer:** Not necessarily. The Spring-specific pointcut `bean(...)` checks the bean name; an advisor can be eligible for one bean and not eligible for the other despite having the same class.

**Scenario 3:** Method `handle(Object value)` has pointcut `args(java.lang.String)`. It is called sequentially through the proxy with `"a"` and `Integer.valueOf(5)`. Can there be different results?

**Answer:** Yes. Different runtime argument types can cause the dynamic matcher to allow advice only on the call passing a `String`.

**Scenario 4:** `AopUtils.canApply(pointcut, PaymentService.class)` is `true`, yet `new PaymentService().pay()` does not run advice. Is that a contradiction?

**Answer:** No. `canApply` only checks whether the pointcut can match the class; an instance created manually outside the container does not automatically have a Spring AOP proxy.

## 12. Official Spring Documentation

- [Spring Framework — Pointcut API](https://docs.spring.io/spring-framework/reference/core/aop-api/pointcuts.html): `ClassFilter`, `MethodMatcher`, static/dynamic matching, and caching.
- [Spring Framework — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html): `execution`, `within`, `target`, `this`, `args`, `@annotation`, `bean` expressions supported by Spring.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): proxy mechanisms and method/self-invocation limitations.
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): auto-proxy configuration for `@Aspect`.
- [Spring Javadoc — AopUtils](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/support/AopUtils.html): `canApply`, `findAdvisorsThatCanApply`.
- [Spring Javadoc — AbstractAdvisorAutoProxyCreator](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/framework/autoproxy/AbstractAdvisorAutoProxyCreator.html): mechanism for finding candidate/eligible advisors when creating a proxy.
