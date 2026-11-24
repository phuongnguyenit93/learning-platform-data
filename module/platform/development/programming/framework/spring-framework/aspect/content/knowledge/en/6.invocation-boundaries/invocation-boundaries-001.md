# Cross-bean calls through a proxy and direct calls to the target object

## 1. The real-world problem: the same method sometimes runs advice and sometimes does not

In Spring AOP, having a method written inside a **Spring bean** or matching a **pointcut** expression is not enough to guarantee that advice will run. The deciding factor is also **the reference used to make the call**:

- Is the caller invoking a **Spring AOP proxy** provided by the container, or is it invoking the **original target object**?
- If the caller is **another Spring bean**, is the dependency it receives actually a proxy?
- If the target calls its own method via `this`, does the call go back out through the proxy?
- If code creates an object manually with `new`, has that object ever been processed by the Spring AOP auto-proxy creator?

A typical example:

```text
ClientBean  --------> OrderService proxy  --------> OrderService target
                       |                              |
                       +-- @Before/@Around advice     +-- business code

ClientBean  --------> raw OrderService target
                       (called directly, bypassing the proxy)
```

Both calls can execute **the same business code on the same target instance**, yet only the path through the proxy gives Spring AOP an opportunity to apply advice.

**Key point:** *Spring AOP is proxy-based AOP*. A call that does not go through a proxy normally does not trigger advice even when the method is selected by a pointcut. This lesson focuses on **Spring Aspects and Spring-managed beans**, without expanding into general AOP theory or standalone AspectJ weaving.

## 2. Distinguishing caller, proxy, and raw target

| Component | Meaning in Spring AOP | What to verify |
| --- | --- | --- |
| **Calling bean** | A Spring bean calling a method on an injected dependency. | Is the dependency actually a Spring AOP proxy? |
| **Spring AOP proxy** | An intermediary object Spring hands to the caller when the bean needs advisors. | Does `AopUtils.isAopProxy(bean)` return `true`? |
| **Target (raw object)** | The object containing the actual business method. | Is it being called directly, bypassing the proxy? |
| **Aspect bean** | A Spring bean declaring `@Aspect`, containing advice/pointcuts. | Is it registered and recognized by the auto-proxy infrastructure? |
| **Advisor/interceptor chain** | Logic that the proxy applies to matching methods. | Does advice execute the right number of times and in the right order? |
| **`this` inside target** | Reference inside the target instance itself. | Is it a self-invocation that bypasses the proxy? |

When calling `clientBean.send()`, the client's `send()` method **does not need to be advised itself**. It can call the dependency `orderService.submit()`, and it is that second call that passes through the Spring proxy.

Conversely, annotating a class with `@Service` **does not turn every reference to an instance of that class into a proxy**. Spring can only control instances/references that the container created or returned through its own mechanisms.

### 2.1. Three fundamental call flows

**Flow A — from another bean via a Spring-injected dependency:**

```text
CallerBean
   |
   | this.orderService.submit("A")  // field holds the Spring AOP proxy
   v
OrderService proxy
   |
   +-- @Before / @Around advice if the pointcut matches
   |
   v
Raw target.submit("A")
```

**Flow B — caller already holds a raw target reference:**

```text
Caller / test / code holding the raw object
   |
   | rawTarget.submit("B")
   v
Raw target.submit("B")
   |
   +-- No Spring AOP proxy on the call path
```

**Flow C — self-invocation inside the target:**

```text
Caller -> proxy -> rawTarget.outer()
                         |
                         | this.submit("C")
                         v
                    rawTarget.submit("C")
                    (internal call, bypasses proxy)
```

If the pointcut only selects `submit()`, advice runs for flow A; does not run for B; and **does not run for the internal `submit()` call** in C. If the pointcut also selects `outer()`, the call into `outer()` can be advised, but that **does not mean** the `submit()` call via `this` gets advised a second time.

## 3. Why does another bean usually receive a proxy?

When using standard Spring AOP configuration, such as `@EnableAspectJAutoProxy` or the corresponding Spring Boot AOP auto-configuration:

1. `ApplicationContext` registers the auto-proxy infrastructure, including a `BeanPostProcessor` dedicated to detecting advisors/aspects.
2. Spring instantiates the target bean and runs its lifecycle.
3. If the bean is eligible for advisors, Spring can create a **JDK dynamic proxy** or a **class-based proxy (CGLIB)**.
4. When another bean injects that dependency with a compatible type, the container resolves the bean reference through its management mechanism. The caller usually receives **the created proxy**, not the raw target wrapped by the proxy.
5. Method calls from the caller enter the proxy; matching advisors execute before/after/around the target method.

This applies both when a service is declared with `@Component`/`@Service` and when it comes from `@Bean`, provided the instance is Spring-managed and eligible for post-processing.

Example:

```java
@Service
public class CheckoutService {
    private final OrderOperations orders;

    public CheckoutService(OrderOperations orders) {
        this.orders = orders; // Spring injects the bean reference (which may be an AOP proxy).
    }

    public void checkout(String id) {
        orders.submit(id); // Goes through the proxy if the dependency is a Spring AOP proxy.
    }
}
```

This is an **illustrative code snippet**, assuming an `OrderOperations` interface and a bean implementing it are declared. Whether advice actually runs also depends on the aspect being registered, the pointcut matching `submit()`, proxy type, scope, and whether the dependency actually points to a proxy.

**Calling from another Spring bean does not automatically guarantee advice runs.** If code inside another bean manually calls `new OrderService()`, intentionally grabs the raw target, or injects a bean from a context without corresponding auto-proxy support, that call can still bypass AOP.

## 4. What does "calling directly on the target object" mean?

A direct call is a call on a **reference to the target itself**, not a reference to the Spring AOP proxy. For example:

```java
OrderService raw = new OrderService();
raw.submit("X");
```

This is a fragment, not a standalone project. `raw` in this example is created with `new`, so the Spring container does not manage it and cannot automatically apply Spring AOP advisors to it.

A more important variant for debugging is **the same raw target that Spring has already proxied**, while code still holds a direct reference to the raw instance. In that case:

```text
proxy.submit("X")  -> advice -> target.submit("X")
raw.submit("Y")    ------------> target.submit("Y")
```

Same target, same method, different path. Therefore, if you see business logic executing while audit/logging/transaction advice does not appear, check **the caller's reference** before suspecting the pointcut.

In production, **do not intentionally expose the raw target of a singleton bean** to evade AOP: doing so breaks consistent enforcement of cross-cutting policies. The runnable example in the next section intentionally keeps a raw reference solely to demonstrate Spring AOP mechanics.

## 5. Runnable Java 17+ example: one target, five call paths

The example is designed to distinguish precisely:

1. Bean `CheckoutFacade` calls `OrderService` **through the Spring-injected proxy**.
2. Code calls `proxy.submit()` directly.
3. Code calls `proxy.submitViaThis()`, and then the target method calls `this.submit()`.
4. Code calls `rawTarget.submit()` on **the exact same target instance that is being proxied**.
5. Code calls the method on an instance created **outside the Spring container** with `new`.

The aspect only advises `OrderService.submit(..)`; only the first two paths run the advice.

### 5.1. Directory structure

```text
spring-aop-call-boundary/
├── pom.xml
└── src/main/java/com/example/boundary/
    ├── AppConfig.java
    ├── OrderService.java
    ├── CheckoutFacade.java
    ├── RawTargetHolder.java
    ├── AuditAspect.java
    └── DemoApp.java
```

### 5.2. `pom.xml`

The example uses **Spring Framework 6.1.14**, `aspectjweaver 1.9.22.1`, JDK 17+, and Maven. This is a **fixed version set for learning**, not a claim about the latest versions.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-aop-call-boundary</artifactId>
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

`spring-context` provides the container and pulls in Spring AOP in the sample's dependency graph; `aspectjweaver` is needed for `@AspectJ`-style declarations. AspectJ compile-time or load-time weaving is not required to run this example.

### 5.3. `src/main/java/com/example/boundary/OrderService.java`

```java
package com.example.boundary;

public class OrderService {

    public void submit(String id) {
        System.out.println("[TARGET] submit " + id);
    }

    public void submitViaThis(String id) {
        this.submit(id);
    }
}
```

`submitViaThis()` calls `submit()` on `this` of the **raw target**. When invoked through the proxy, the call into `submitViaThis()` reaches the target, but the subsequent `this.submit()` call does not go back out to the proxy.

### 5.4. `src/main/java/com/example/boundary/CheckoutFacade.java`

```java
package com.example.boundary;

public class CheckoutFacade {
    private final OrderService orders;

    public CheckoutFacade(OrderService orders) {
        this.orders = orders;
    }

    public void checkout(String id) {
        orders.submit(id);
    }

    public OrderService injectedReference() {
        return orders;
    }
}
```

`CheckoutFacade` acts as the caller bean instantiated by the container. `OrderService` is constructor-injected; in a configuration with an aspect and proxy, the `orders` reference is the Spring AOP proxy.

### 5.5. `src/main/java/com/example/boundary/RawTargetHolder.java`

```java
package com.example.boundary;

public class RawTargetHolder {
    private OrderService raw;

    public void remember(OrderService target) {
        this.raw = target;
    }

    public OrderService raw() {
        return raw;
    }
}
```

This class intentionally retains the **raw target reference** before Spring completes providing the AOP proxy. This is an **experimental technique** and should not be used in business architecture because it makes it easy to bypass auditing, transactions, or other policies.

### 5.6. `src/main/java/com/example/boundary/AuditAspect.java`

```java
package com.example.boundary;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class AuditAspect {
    private final AtomicInteger calls = new AtomicInteger();

    @Before("execution(public void com.example.boundary.OrderService.submit(..))")
    public void beforeSubmit(JoinPoint joinPoint) {
        calls.incrementAndGet();
        Object id = joinPoint.getArgs()[0];
        System.out.println("[AOP] before submit " + id);
    }

    public int calls() {
        return calls.get();
    }
}
```

The pointcut intentionally selects **a single method**: `OrderService.submit(..)`. It does not select `submitViaThis()` or `CheckoutFacade.checkout()`. This makes it clear whether advice runs or not **due to the call path**, rather than multiple methods accidentally matching.

`AtomicInteger` is used to count how many times the advice is actually invoked; verification does not rely on log parsing.

### 5.7. `src/main/java/com/example/boundary/AppConfig.java`

```java
package com.example.boundary;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public RawTargetHolder rawTargetHolder() {
        return new RawTargetHolder();
    }

    @Bean
    public OrderService orderService(RawTargetHolder holder) {
        OrderService target = new OrderService();
        holder.remember(target); // Only to compare the raw target against the proxy.
        return target;
    }

    @Bean
    public AuditAspect auditAspect() {
        return new AuditAspect();
    }

    @Bean
    public CheckoutFacade checkoutFacade(OrderService orderService) {
        return new CheckoutFacade(orderService);
    }
}
```

`@EnableAspectJAutoProxy(proxyTargetClass = true)` uses a **class-based proxy** so `CheckoutFacade` can inject `OrderService` by concrete type conveniently for the demo. In an interface-based application, Spring may use a JDK proxy; the principle that **the caller goes through the proxy** remains unchanged.

When `orderService()` creates the target and stores it in `RawTargetHolder`, Spring still has to perform post-processing steps to wrap it in a proxy before another consumer injects the `orderService` bean. Therefore, the same original `target` object can be accessed via two paths: the raw reference and the Spring proxy reference.

### 5.8. `src/main/java/com/example/boundary/DemoApp.java`

```java
package com.example.boundary;

import org.springframework.aop.framework.Advised;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApp {
    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {

            OrderService proxy = context.getBean(OrderService.class);
            RawTargetHolder holder = context.getBean(RawTargetHolder.class);
            OrderService raw = holder.raw();
            CheckoutFacade facade = context.getBean(CheckoutFacade.class);
            AuditAspect aspect = context.getBean(AuditAspect.class);

            System.out.println("proxyIsAop=" + AopUtils.isAopProxy(proxy));
            System.out.println("rawIsAop=" + AopUtils.isAopProxy(raw));
            System.out.println("facadeHasProxy="
                    + (facade.injectedReference() == proxy));
            System.out.println("sameReference=" + (proxy == raw));
            System.out.println("sameTarget="
                    + (((Advised) proxy).getTargetSource().getTarget() == raw));

            System.out.println("-- from another bean --");
            facade.checkout("A");

            System.out.println("-- external through proxy --");
            proxy.submit("B");

            System.out.println("-- self-invocation via target.this --");
            proxy.submitViaThis("C");

            System.out.println("-- direct raw target --");
            raw.submit("D");

            System.out.println("-- outside Spring container --");
            new OrderService().submit("E");

            System.out.println("adviceCalls=" + aspect.calls());
        }
    }
}
```

`Advised.getTargetSource().getTarget()` is an **experimental check** to verify that the singleton bean's proxy points to the exact raw target held in `RawTargetHolder`. Do not do this in business code to bypass AOP policies. With a custom `TargetSource` or scoped target, unwrapping or obtaining a single stable target may not be valid.

### 5.9. Running and expected output

Requires JDK 17+, Maven, and network access to download dependencies. In the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.boundary.DemoApp
```

Lines printed by `DemoApp` and the aspect, in order (excluding Maven/Spring logs if any):

```text
proxyIsAop=true
rawIsAop=false
facadeHasProxy=true
sameReference=false
sameTarget=true
-- from another bean --
[AOP] before submit A
[TARGET] submit A
-- external through proxy --
[AOP] before submit B
[TARGET] submit B
-- self-invocation via target.this --
[TARGET] submit C
-- direct raw target --
[TARGET] submit D
-- outside Spring container --
[TARGET] submit E
adviceCalls=2
```

**Explanation of each output group:**

1. `proxyIsAop=true` while `rawIsAop=false`: for the same business logic there is **one Spring AOP proxy reference** and **one different raw target reference**.
2. `facadeHasProxy=true`: Spring injected the exact proxy reference into the caller `CheckoutFacade`.
3. `sameTarget=true`: in this singleton demo, the proxy genuinely wraps the target object held in `RawTargetHolder`. This proves the difference in advice execution **does not come from swapping service instances**.
4. Both the call from `CheckoutFacade` and the direct call on the `proxy` variable go through the proxy and match the `submit(..)` pointcut, producing two `[AOP]` lines.
5. `proxy.submitViaThis("C")` enters `submitViaThis`, and then `this.submit("C")` calls directly on the target; the pointcut selects `submit`, but the internal call does not return to the proxy, so there is no `[AOP]` line.
6. Calls on `raw` and on the instance from `new` do not go through a proxy; they only print `[TARGET]`. The final counter is `2`, not `5`.

The experiment demonstrates that **the interception point lies on the reference/call path**, not as an inherent property of the `submit` method in source code.

## 6. Behavior matrix: matching the pointcut is not enough

Assuming only `@Before` for `OrderService.submit(..)`:

| Call pattern | Reference at call time | Does `@Before` run for `submit`? | Reason |
| --- | --- | --- | --- |
| `facade.checkout("A")` calls `orders.submit("A")` | `orders` is the Spring-injected proxy | **Yes** | Cross-bean call enters the Spring proxy. |
| `context.getBean(OrderService.class).submit("B")` | Bean reference is the proxy | **Yes** | Caller uses the Spring proxy directly. |
| `proxy.submitViaThis("C")` → `this.submit("C")` | Internal reference is the raw target `this` | **No** for the internal `submit` call | Self-invocation bypasses the proxy. |
| `raw.submit("D")` | Raw target reference | **No** | No proxy on the call path. |
| `new OrderService().submit("E")` | Self-created object outside container | **No** | Spring neither manages nor auto-proxies the object. |
| `@PostConstruct` inside target calls `this.submit(...)` | Raw target during init callback | **No** via normal AOP proxy | Init callback happens before the normal proxy is ready; also an internal call. |
| Another bean injects the service interface and calls the method via JDK proxy | Interface proxy | **Yes** if pointcut matches and method is callable via interface | Different proxy style, same interception boundary. |

In real systems, a single call can have **multiple advisors** and another method may also be advised. The table counts only the `@Before` advice on `submit` per the assumption, avoiding confusion between "no advice on `submit`" and "no advisors running at all".

## 7. Distinguishing "calling from another bean" from "true cross-bean via proxy"

### 7.1. A Spring caller bean manually calls `new` on the target

```java
public class CheckoutFacade {
    public void checkout() {
        OrderService service = new OrderService();
        service.submit("X");
    }
}
```

Even though `CheckoutFacade` is registered as a Spring bean, the `service` variable in this method is a **manually created** object. There is no bean lookup, injection, or Spring AOP proxy. The aspect targeting `OrderService.submit` does not run on that call.

**Proper approach:** inject the Spring-managed service via constructor or access the container through a controlled design; avoid calling `new` manually on a service that needs transaction, audit, caching, or authorization advice.

### 7.2. The caller holds an old reference to the raw target

This can happen when code creates an object manually and registers that object into `BeanFactory`, or when a factory/registry leaks the raw reference out before Spring creates the proxy. Then, even though the target is also managed by Spring, the earlier caller still invokes methods on **the retained reference**, which does not automatically transform into a proxy after the auto-proxy creator runs.

```text
rawRef = target;              // Holds the original object.
springBean = getBean(...);    // Spring may return a proxy wrapping the target.
rawRef.submit();              // Bypasses.
springBean.submit();          // Goes through proxy if advisor matches.
```

This is a diagnostic model, **not a recommendation to store raw targets**. Always try to unify a single path for obtaining dependencies from the Spring container so shared policies do not run inconsistently.

### 7.3. The caller retrieves a bean from a different context

An application can have **parent and child `ApplicationContext`s**, or multiple independent contexts. Auto-proxy configuration is local to each respective context, so a bean outside a context that has `@EnableAspectJAutoProxy` enabled may not be auto-proxied like beans inside that context.

Calling from another bean does not prove "same context" or "same AOP infrastructure". When debugging, identify which context owns the target and aspect, where `@Bean`/`@ComponentScan` are registered, and how dependencies are resolved.

## 8. Self-invocation: calls that do not go back through the proxy

In the demo in section 5, `proxy.submitViaThis("C")` enters the target, but the `this.submit("C")` call inside the target does not go back out to the Spring proxy. Consequently, advice targeting only `submit(..)` does not run on the internal call, even though `submit` is public and the pointcut matches. If an advisor also targets `submitViaThis`, the outer method can be advised, but that does not cause `submit` to be intercepted an additional time.

Switching from JDK proxy to CGLIB does not fix self-invocation. When a policy truly needs to apply to an internally called method, consider **placing the boundary at the outer method** if the policy belongs to the whole operation, or **extracting the responsibility into a Spring collaborator bean** and calling it through an injected dependency. Self-injection can involve circular dependencies, lifecycle, and proxy-type concerns; `AopContext.currentProxy()` requires `exposeProxy=true` and an active AOP invocation, so it is only suitable for exceptions. Subsequent lessons analyze and verify each option individually.

## 9. Initialization boundary: the bean has not yet handed a complete proxy to callers

Constructors, `@PostConstruct`, `InitializingBean.afterPropertiesSet()`, and custom init methods on the target itself usually run **before the bean is published through a complete AOP proxy**. If a callback calls `this.submit("INIT")`, that is also self-invocation; the call to `submit` is not advised via a Spring AOP proxy. Therefore, merely seeing an annotation on a method is not enough to conclude that a transaction, audit, or cache interceptor ran.

A callback on **another bean** may call through the proxy of an already initialized dependency; do not lump every callback into a blanket "always bypasses" conclusion. For startup work that needs interception, use a separate coordinator calling the service via a Spring-managed dependency at the right lifecycle phase, such as `ApplicationRunner` in Spring Boot. A dedicated lesson on lifecycle explains the exact milestones and exceptions.

## 10. Impact of JDK proxy and CGLIB on cross-bean invocation

The rule that calls **must go through the proxy** applies to both mechanisms, though the reference types that another bean can inject/call differ.

| Aspect | JDK dynamic proxy | Class-based (CGLIB) proxy |
| --- | --- | --- |
| Proxy type | Implements the relevant interfaces | Subclass of the target class |
| Typically suitable injection type | By **business interface** | By interface or concrete class when proxy is valid |
| Methods callable through proxy | Methods belonging to proxied interfaces | Methods that the proxy subclass can expose/override within Spring's limits |
| `this.method()` call from target | Bypasses proxy | Bypasses proxy |
| Caller uses `new Target()` | No Spring AOP proxy | No Spring AOP proxy |
| Raw target reference retained outside proxy | Bypasses | Bypasses |
| `final`/private methods | Interface proxy intercepts at interface method boundaries when applicable; internal private methods are not part of interface contracts | Cannot override final/private methods |
| Runtime inspection | `AopUtils.isJdkDynamicProxy(bean)` | `AopUtils.isCglibProxy(bean)` |

For example, a service implements `OrderOperations` while a caller injects the concrete `OrderService` when Spring uses a JDK proxy. This can fail dependency resolution by concrete class because a JDK proxy **is not an instance of the implementation class**. In that case, inject by business interface, or intentionally choose a class-based proxy if needed and the target can be subclassed.

**Do not change proxy types to mask bugs caused by calling a raw target directly.** Whether JDK or CGLIB, if the reference does not go through a proxy, advice still has no chance to intercept method execution.

## 11. Interception boundaries in Spring Boot or plain Spring Framework

### Plain Spring Framework

Usually requires Spring Context, Spring AOP, and AspectJ libraries supporting `@AspectJ`, along with declaring:

```java
@Configuration
@EnableAspectJAutoProxy
public class AopConfig {
}
```

Together with an `@Aspect` bean registered via `@Bean` or `@Aspect` + `@Component` within component scanning. `@Aspect` **does not automatically turn a class into a component** if suitable bean registration is missing.

### Spring Boot

Boot provides AOP auto-configuration depending on the version/starter and configuration. For instance, Boot 3.x uses `spring-boot-starter-aop`; Boot 4.x has `spring-boot-starter-aspectj`. Auto-configuration makes enabling auto-proxying more convenient, but **does not inherently alter the call boundaries of Spring proxy AOP**.

Even when `@Transactional`, `@Cacheable`, or `@Async` are configured via Spring proxies, internal calls or direct calls to a raw target must still be evaluated according to each subsystem's specific mechanism and proxy. Simply having an annotation present on a method is not enough to guarantee an interceptor will run.

## 12. How to verify the call path in a running application

### 12.1. Step 1: check the caller's bean reference

When you have access to `ApplicationContext` in a test or during diagnostics:

```java
Object service = context.getBean("orderService");
System.out.println(org.springframework.aop.support.AopUtils.isAopProxy(service));
```

This is a fragment requiring a `context` variable. If `true`, the returned bean is a Spring AOP proxy. If `false`, you cannot immediately conclude a framework bug: the pointcut may not match, the bean may not be a target needing advice, the aspect may not be registered, or you may be fetching the bean from a different context.

In a test, you can compare with `==` between the dependency held by the caller and the reference Spring returns for the same singleton bean. That helps detect if the caller holds a raw/old reference. **Do not compare with `equals` to conclude identical Java references**, because Spring proxies handle equality specially.

### 12.2. Step 2: check advisors on the proxy, not just proxy presence

```java
Object bean = context.getBean("orderService");

if (bean instanceof org.springframework.aop.framework.Advised advised) {
    for (org.springframework.aop.Advisor advisor : advised.getAdvisors()) {
        System.out.println(advisor.getClass().getName());
    }
}
```

This is a diagnostic fragment; output varies by Spring version and advisor set. A proxy can exist because of transactions, a scoped proxy, or another advisor; **having a proxy does not mean your `@Before` matches the method being called**.

### 12.3. Step 3: compare with a direct raw target call in an isolated test

If you genuinely need to prove the mechanism, use a test/demonstration like `RawTargetHolder` in section 5. Do not spread raw references in production code just for debugging. Verify:

- Calls through the Spring-injected dependency run advice.
- Calls on the raw target still perform business logic but without advice.
- Self-invocation calls only trigger advice for **the outer method** if that method also matches the pointcut; the inner method does not go back through the proxy on its own.
- Business results, exceptions, and target state mutations match expectations.

If a call through the proxy does not run advice, check both the pointcut and bean lifecycle instead of immediately blaming self-invocation.

### 12.4. Step 4: measure with a counter or test event

Do not look for just a similar-looking log line: a single API request may call a method twice; logs from transactions/filters may also look alike.

A solid test should have a counter/event collector in both the advice and the target:

```text
One clientBean -> proxy.submit() call:
    advice count +1, target count +1

One raw.submit() call:
    advice count +0, target count +1

One this.submit() call inside the raw target:
    advice count +0, target count +1
```

These are the expected counts **with one advice applying only to `submit`**. If there are multiple advisors or an `@Around` advice that skips `proceed()`, adjust expected counts according to the actual policy.

## 13. `@Around` behavior makes the difference between proxy and target even sharper

With `@Before`, bypassing via a raw target mainly omits the pre-method action. With `@Around`, the consequences can be more severe: when going through a proxy, the advice **can decide whether to call the target at all**, alter the return value, or translate exceptions. When the proxy is bypassed, all of that orchestration capability is skipped.

Example method fragment inside an aspect:

```java
@Around("execution(public * com.example.boundary.OrderService.submit(..))")
public Object around(org.aspectj.lang.ProceedingJoinPoint pjp)
        throws Throwable {
    long start = System.nanoTime();
    try {
        return pjp.proceed(); // Through proxy: proceed to execute target.
    } finally {
        System.out.println("durationNanos=" + (System.nanoTime() - start));
    }
}
```

This is an **illustrative method fragment**; it must be placed in a registered `@Aspect` bean class with `Around` imported. Do not add this fragment simultaneously to the section 5 project if you want to preserve the published stdout.

On a raw target call path, there is no Spring AOP `ProceedingJoinPoint` for that call and no timing logic from the aspect. The same applies to audit, retry, security check, or caching advice designed around interception.

**Do not treat proxy bypass as a minor performance glitch.** It can cause a security requirement or transaction policy not to be enforced. If a behavior is mandatory for correctness, combine API/bean boundary design, unit/integration tests, and safeguards outside AOP when needed.

## 14. Common mistakes and remedies

| Symptom | Possible cause | How to resolve |
| --- | --- | --- |
| `@Before` runs when called from controller, does not run when called within the same service | Controller holds a reference to the proxy, while service calls `this.method()` on the raw target | Extract the method needing advice to another Spring bean; call via injected proxy. |
| `@Aspect` exists yet calls from another bean are still not advised | Aspect is not a Spring bean, proxying is not enabled, pointcut does not match, or caller holds raw reference | Check registration → context → AOP creator → proxy → pointcut → call path. |
| Creating service manually with `new` prevents transaction/audit from running | Instance is outside the Spring container | Place service in IoC and inject the Spring-managed bean. |
| `@PostConstruct` calls an aspected method but advice does not run | Initialization runs on raw bean before proxy + self-invocation | Move invocation to a post-context-ready phase via another bean. |
| Forcing `proxyTargetClass=true` yet `this.method()` still bypasses | CGLIB does not change the self-invocation nature of Spring proxy AOP | Do not use proxy type to fix call boundaries; split beans or structure valid call paths. |
| Advice runs sometimes and not others for the same class | Multiple instances/references exist, some proxied, some raw/new, or beans in different contexts | Trace bean origin, `AopUtils`, identity, and where dependencies are resolved. |
| `getBean(ConcreteClass.class)` fails when using JDK proxy | Proxy only implements interfaces so it is not assignable to the concrete class | Inject by business interface, or intentionally choose class proxy if valid. |
| Bean is proxied yet method does not run advice | Proxy has a different advisor or pointcut does not match that method | List advisors, instrument invocations, and inspect the specific pointcut. |
| Trying `AopContext.currentProxy()` and hitting errors | `exposeProxy` not enabled, not inside a proxy invocation, or wrong type cast | Prefer bean refactoring; only use this mechanism when genuinely needed and properly configured. |
| Unit test uses `new Service()` yet expects aspect to run | Test does not initialize a Spring AOP context | Test Spring AOP with a context-backed integration test, or test raw business logic separately without expecting advice. |

## 15. Process for designing resilient Spring AOP boundaries

1. **Identify which methods are intentional interception points**, for example `OrderService.submit()`.
2. **Make the target a Spring bean** and register the aspect as a bean in the right `ApplicationContext`.
3. **Enable Spring auto-proxying properly**, via Java config, XML, or the corresponding Spring Boot auto-configuration.
4. **Design public entry points called from other beans**, avoiding reliance on self-invocation for critical policies.
5. **Inject using a type compatible with the proxy strategy**; with JDK proxies, prefer business interfaces. Never manually `new` a service that needs advice.
6. **Do not retain raw references outside the container**; if needed for debugging, use an isolated test and keep it out of production code.
7. **Verify `AopUtils.isAopProxy` and actual calls** on the caller's dependency, not just the bean type or annotation.
8. **Measure advice count and target count**, especially with `@Around`, errors/exceptions, transactions, and multiple advisors.
9. **Check contexts and scopes**, when services move across modules, web child contexts, or use prototype/scoped proxies.
10. **Include call-boundary tests in the regression suite**, so refactoring does not accidentally switch from a proxy reference to a raw target reference.

### Official Spring documentation

- Spring Framework — Proxying Mechanisms, Understanding AOP Proxies: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework — Enabling @AspectJ Support: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html
- Spring Framework — Declaring an Aspect: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/at-aspectj.html
- Spring Framework — AOP Concepts: https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html
- Spring Framework — Programmatic AOP Proxy Creation: https://docs.spring.io/spring-framework/reference/core/aop-api/prog.html

**In summary, in Spring AOP, the same target method can be called via two paths: through the Spring proxy or directly on the raw target. Only the path through the proxy executes matching advisors/advice.** Designing clear bean boundaries and testing the caller's actual reference are the ways to guarantee Spring Aspects apply consistently.