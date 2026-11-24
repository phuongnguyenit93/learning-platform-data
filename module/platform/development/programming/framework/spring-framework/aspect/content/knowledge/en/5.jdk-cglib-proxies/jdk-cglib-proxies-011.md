# equals, hashCode, toString, and Verifiable Behavior on Spring AOP Proxies

## 1. Why Must These Three Object Methods Be Checked When Using Spring AOP?

A business Spring bean can be handed to callers by `ApplicationContext` as an **AOP proxy**, typically a **JDK dynamic proxy** or a **class-based proxy (CGLIB)**. Therefore, calling `equals(Object)`, `hashCode()`, and `toString()` on an injected variable does not necessarily follow the same path or yield the same result as calling them directly on **the raw target**.

This is an issue of **Spring AOP and Spring-managed beans**, not a general overview of Java's `Object` contract. What you need to know when configuring or debugging aspects is:

- Do two references retrieved from the context point to the same **Spring proxy** or to different proxies?
- Is `equals()` comparing proxy configuration or using Spring-specific rules instead of comparing business data inside the target?
- Is `hashCode()` stable for a proxy; is it safe to use a proxy as a key in a `HashMap`/`HashSet`?
- How is `toString()` dispatched; does logging a proxy trigger advice or access sensitive data?
- Do results change when switching from a JDK proxy to CGLIB, or when the target overrides these three methods?
- Which checks can be used **without drawing false conclusions from proxy class names or a few coincidental outputs**?

Guiding conclusion: **a Spring AOP proxy has its own identity and behavioral layer**. Do not equate `proxy.equals(other)` with `target.equals(other)`, do not equate `proxy.hashCode()` with `target.hashCode()`, and do not treat `proxy.toString()` strings as sufficient proof of proxy structure.

## 2. Revisiting the Boundary Between Proxy and Target

```text
  Bean retrieved from ApplicationContext
             |
             v
       Spring AOP proxy
        /           \
JDK interface      CGLIB subclass
       \             /
        \           /
         v         v
  Spring interceptor/advisor handling
             |
             v
       Target bean method
```

In plain Spring Framework, targets with business interfaces normally lead to JDK proxies; without suitable interfaces, class-based proxies. Setting `proxyTargetClass = true` requests CGLIB; Spring Boot may choose a different default per auto-proxy configuration.

The key point for the three `Object` methods is that **the caller invokes them on the proxy object**, and Spring decides whether to handle them specially or forward them down to the target. The exact path also depends on the Spring version, proxy type, proxied interfaces, `Advisor`, `TargetSource`, method overrides, and infrastructure optimizations.

Do not use formulas like “every call on a proxy goes through the target before returning” or “every method on a proxy triggers advice.” Both ignore Spring AOP's actual dispatch mechanics.

## 3. `equals(Object)` on a Spring AOP Proxy

### 3.1. JDK Dynamic Proxy Case

In Spring's `JdkDynamicAopProxy` implementation, `equals` has a **dedicated handling branch** when no proxied interface declares a matching `equals(Object)` method. In that case, `equals` is handled by the proxy itself rather than defaulting to calling `equals` directly on the target.

Practical implications:

- `proxy.equals(proxy)` must return `true` (reflexivity).
- Two proxies wrapping the same target object **do not automatically guarantee** `proxy1 == proxy2` or `proxy1.equals(proxy2)`.
- Spring may compare proxy configuration characteristics such as **interfaces, advisor chains, and `TargetSource`** when determining whether two AOP proxies are equivalent under Spring's mechanics.
- `proxy.equals(rawTarget)` does not have the same meaning as `rawTarget.equals(rawTarget)`.
- When a proxied interface **redeclares `equals(Object)`**, the JDK proxy's dispatch branch can differ; verify against your specific version and configuration instead of applying one rule to all interfaces by default.

Spring does not always use **Java object identity** rules for `equals` on a proxy. Yet there is also no guarantee it will apply **entity domain equality** per the target's custom logic. That is why you should write tests for actual scenarios rather than guessing.

### 3.2. CGLIB Class Proxy Case

Spring CGLIB AOP has an **EqualsInterceptor** for `equals(Object)` when the method can be overridden and the interceptor is installed appropriately. It can handle comparison by proxy identity and proxy/advisor/target-source configuration, without necessarily invoking `target.equals(...)`.

For example, two Spring proxies sharing the same runtime class or the same target type **is not enough** to conclude they are `equals` to each other. Bean identity, scope, target source, and advisor configuration are all relevant.

A **technical warning**: a class-based proxy cannot override `final` methods (including `final equals`), and cannot subclass `final` classes. If a bean has those constraints, do not design tests assuming all `Object` method calls will be intercepted normally by Spring CGLIB.

### 3.3. Do Not Treat Target Domain Equality as the Proxy Contract

Suppose the target holds `id = "INV-10"` and overrides `equals` to compare by id. This **does not prove** two references to AOP proxies will compare equal simply because the two raw targets share the same id.

```java
// Illustrative fragment; variables come from an actual Spring setup:
boolean sameReference = proxyA == proxyB;
boolean sameByProxyEquals = proxyA.equals(proxyB);
boolean sameBusinessId = idA.equals(idB);
```

These three expressions test **three different relationships**:

1. `==`: the exact same Java object reference.
2. `equals` on an AOP proxy: actual Spring proxy semantics in the specific configuration.
3. Comparing **business keys**: domain identity deliberately chosen by business logic.

If the program needs to group transactions by business id, extract **the immutable id** as the key, or use a dedicated value object; do not use AOP proxy equality as the default business criterion.

## 4. `hashCode()` on a Spring AOP Proxy

`hashCode()` is directly tied to `equals()`: if two objects are considered equal, their hash codes must be equal. An AOP proxy must also honor this contract within the scope of semantics Spring applies.

### 4.1. JDK Proxy

In Spring's `JdkDynamicAopProxy`, if no proxied interface declares `hashCode()`, Spring has a **dedicated proxy `hashCode` handling branch**. Spring's implementation may compute the value based on the handler/characteristics of `TargetSource`, rather than taking the target's `hashCode()` directly.

**Do not assert a fixed integer hash.** Hash codes depend on the object, identity/configuration/implementation and can vary across JVM runs. A reasonable check is stability while the proxy and related metadata remain unchanged.

### 4.2. CGLIB Proxy

In standard Spring CGLIB mechanics, `HashCodeInterceptor` is dedicated to handling `hashCode()` on the proxy. This pairs with the special handling in `EqualsInterceptor`.

When the target implements `hashCode` based on a business id, `proxy.hashCode()` **must not be assumed** to be the hash value computed by the target. Do not assert `proxy.hashCode() == rawTarget.hashCode()` unless that is an explicit contract verified on your deployment platform and genuinely needed.

### 4.3. Using Proxies as Keys in `HashMap` or `HashSet`

A stably created and used proxy can serve as a key under its semantics, but keep these caveats in mind:

- **Scope:** singleton beans usually return the same Spring reference within one context; prototype beans produce distinct instances; scoped proxies can present a stable reference while the underlying target changes per request.
- **Changes in proxy configuration:** two proxies differing in advisors, interfaces, or target sources may not share equality equivalence.
- **Mutability:** avoid mutating state/configuration involved in `equals`/`hashCode` while the object resides in a hash collection.
- **Key purpose:** if the business key is `orderId`, store `orderId`, not the `OrderService` proxy while trying to infer business identity from it.
- **Cross-context:** singleton per Spring context does not imply the same reference or the same proxy equality in another context.

Appropriate pattern for a business cache:

```java
Map<String, String> resultsByOrderId = new HashMap<>();
resultsByOrderId.put("ORD-7", "processed");
```

This is a fragment requiring `java.util.Map` and `java.util.HashMap` imports. The `"ORD-7"` key carries far clearer business meaning than an `OrderService` proxy.

## 5. `toString()` on a Spring AOP Proxy

Unlike Spring AOP having dedicated branches for `equals`/`hashCode`, **`toString()` is normally handled through the proxy's method dispatch path**. When the target overrides `toString()`, the Spring proxy can forward the call to the target or pass through the interceptor chain depending on configuration.

Do not lump all three methods into one rule like “Spring always overrides all `Object` methods the exact same way.”

Important points:

- `proxy.toString()` may return the string declared by the target, yet **it is not an API guaranteed to return the proxy's runtime class type**.
- A default or overridden `toString()` can display different values depending on target class, proxy style, and active advice.
- If a pointcut/advisor is designed **such that it can match `toString()`**, the call may be intercepted; a pointcut selecting **only** `OrderService.process(..)` does not turn `toString()` calls into `process` advice.
- `toString()` is not a lifecycle management mechanism and is not a standard tool for listing advisor chains.
- Printing a proxy with `logger.info("bean={}", bean)` or string concatenation can trigger a `toString()` call; if the target's `toString()` touches lazy data, remote services, or sensitive information, logging can be costly and leak data.

Prefer logging **explicitly chosen metadata** (bean name, target class from Spring diagnostic APIs, controlled request id) rather than logging the full `toString()` of a stateful bean.

### 5.1. `getClass().getName()` Differs from `toString()`

```java
String runtimeClass = proxy.getClass().getName();
String printable = proxy.toString();
```

- `runtimeClass`: the actual class name of the held object; may be a `jdk.proxy...` class or a Spring CGLIB generated class.
- `printable`: the string determined by `toString()` dispatch; may come from the target or advice depending on config.

These two values need not match. Generated proxy class names can change across JDK/Spring versions, so do not assert exact full class names. Use `AopUtils.isJdkDynamicProxy`, `AopUtils.isCglibProxy`, and `AopUtils.getTargetClass` for proper checks.

## 6. Comparison Table When Verifying Object Method Behavior

| Check | JDK Spring AOP proxy | CGLIB Spring AOP proxy | Safe verification method |
| --- | --- | --- | --- |
| `proxy == proxy` | `true` | `true` | Java identity check. |
| `proxy.equals(proxy)` | Expect `true` | Expect `true` | Assert reflexivity on the real bean from context. |
| `proxy.hashCode()` called twice | Expect stable while state/config unchanged | Expect stable while state/config unchanged | Compare two values within the same test; do not hardcode numbers. |
| `proxy.equals(rawTarget)` | Not `true` by default | Not `true` by default | Measure in the specific context; avoid relying on raw-target identity. |
| `proxy1.equals(proxy2)` | Depends on semantics/config | Depends on semantics/config | Explicitly test the proxies/target sources, do not guess. |
| `proxy.toString()` | May dispatch to target | May dispatch to target | Define clear `toString` purpose; check output and advice. |
| `proxy.getClass()` | JDK generated proxy class | CGLIB generated subclass | Use `AopUtils` instead of relying on generated class names. |
| `proxy instanceof ConcreteService` | Usually `false` if using interface-based proxy | Usually `true` if class proxy is valid | Test injection/casting against interface or class contract. |

The table describes **typical proxy-based Spring AOP**. Every assertion about business outcomes should run against your project's **Spring version, bean scope, advice chain, and proxy settings**. Do not treat a value observed in a demo project as a permanent compatibility contract of Spring internals.

## 7. Runnable Java 17+ Example: Measuring the Three Methods on JDK and CGLIB

The example builds **two independent `ApplicationContext` instances** over the same business interface and aspect:

- `JDK` context uses `@EnableAspectJAutoProxy(proxyTargetClass=false)`.
- `CGLIB` context uses `@EnableAspectJAutoProxy(proxyTargetClass=true)`.
- `ReportOperations` is the business interface; `ReportService` implements that interface.
- The aspect advises only `runReport()`, **not selecting `equals`, `hashCode`, or `toString`**.
- `ReportService.toString()` returns a fixed string to observe dispatch without relying on hash values or generated class names.

To avoid asserting unpromised equality internals, the program only prints stable/explainable properties: proxy type, `equals` reflexivity, hash stability across two calls, `toString`, and advice invocation counts.

### 7.1. Project Structure

```text
spring-proxy-object-methods/
├── pom.xml
└── src/main/java/com/example/proxycheck/
    ├── ReportOperations.java
    ├── ReportService.java
    ├── TraceAspect.java
    └── DemoApp.java
```

### 7.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-proxy-object-methods</artifactId>
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

`spring-context` manages beans and pulls in Spring AOP in the sample's dependency graph, while `aspectjweaver` provides the library needed for Spring to understand `@Aspect`/pointcut declarations. This code uses **Spring proxy AOP**, without configuring an AspectJ weaving agent.

### 7.3. `src/main/java/com/example/proxycheck/ReportOperations.java`

```java
package com.example.proxycheck;

public interface ReportOperations {
    String runReport(String reportId);
}
```

The interface **does not itself declare** `equals(Object)` or `hashCode()`: this is the common case for observing Spring JDK proxy's special handling.

### 7.4. `src/main/java/com/example/proxycheck/ReportService.java`

```java
package com.example.proxycheck;

public class ReportService implements ReportOperations {

    @Override
    public String runReport(String reportId) {
        System.out.println("[TARGET] run " + reportId);
        return "report:" + reportId;
    }

    @Override
    public String toString() {
        return "ReportService(target)";
    }
}
```

The target overrides only `toString`. `equals` and `hashCode` keep `Object`'s implementation, letting the demo focus on **proxy handling** differences without mixing in domain equality.

### 7.5. `src/main/java/com/example/proxycheck/TraceAspect.java`

```java
package com.example.proxycheck;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class TraceAspect {
    private final AtomicInteger count = new AtomicInteger();

    @Before("execution(public * com.example.proxycheck.ReportService.runReport(..))")
    public void beforeRun() {
        count.incrementAndGet();
        System.out.println("[ADVICE] before runReport");
    }

    public int count() {
        return count.get();
    }
}
```

The pointcut explicitly selects one business method. Calling `equals`, `hashCode`, and `toString` **is not meant to trigger this advice**. `AtomicInteger` provides an accurate invocation count in the example.

### 7.6. `src/main/java/com/example/proxycheck/DemoApp.java`

```java
package com.example.proxycheck;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.context.annotation.Import;

public class DemoApp {

    @Configuration
    static class SharedBeans {
        @Bean
        ReportOperations reportOperations() {
            return new ReportService();
        }

        @Bean
        TraceAspect traceAspect() {
            return new TraceAspect();
        }
    }

    @Configuration
    @Import(SharedBeans.class)
    @EnableAspectJAutoProxy(proxyTargetClass = false)
    static class JdkConfig {
    }

    @Configuration
    @Import(SharedBeans.class)
    @EnableAspectJAutoProxy(proxyTargetClass = true)
    static class CglibConfig {
    }

    private static void inspect(String label, Class<?> configClass) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(configClass)) {

            ReportOperations proxy = context.getBean(ReportOperations.class);
            TraceAspect aspect = context.getBean(TraceAspect.class);

            System.out.println("[" + label + "] isJdk="
                    + AopUtils.isJdkDynamicProxy(proxy));
            System.out.println("[" + label + "] isCglib="
                    + AopUtils.isCglibProxy(proxy));
            System.out.println("[" + label + "] equalsSelf="
                    + proxy.equals(proxy));

            int firstHash = proxy.hashCode();
            int secondHash = proxy.hashCode();
            System.out.println("[" + label + "] hashStable="
                    + (firstHash == secondHash));

            System.out.println("[" + label + "] toString="
                    + proxy.toString());
            System.out.println("[" + label + "] adviceBeforeBusiness="
                    + aspect.count());

            String result = proxy.runReport(label);
            System.out.println("[" + label + "] result=" + result);
            System.out.println("[" + label + "] adviceAfterBusiness="
                    + aspect.count());
        }
    }

    public static void main(String[] args) {
        inspect("JDK", JdkConfig.class);
        inspect("CGLIB", CglibConfig.class);
    }
}
```

**Why two contexts?** `@EnableAspectJAutoProxy(proxyTargetClass=false)` and `@EnableAspectJAutoProxy(proxyTargetClass=true)` active together in one context can merge to the stronger setting; separating contexts cleanly compares the two proxy choices. Both contexts have their own `TraceAspect` and the same business target definition.

### 7.7. Running and Expected Stdout

With Maven and JDK 17+ in the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.proxycheck.DemoApp
```

Lines printed by the program itself in order (ignoring Maven or Spring logs if present in the environment):

```text
[JDK] isJdk=true
[JDK] isCglib=false
[JDK] equalsSelf=true
[JDK] hashStable=true
[JDK] toString=ReportService(target)
[JDK] adviceBeforeBusiness=0
[ADVICE] before runReport
[TARGET] run JDK
[JDK] result=report:JDK
[JDK] adviceAfterBusiness=1
[CGLIB] isJdk=false
[CGLIB] isCglib=true
[CGLIB] equalsSelf=true
[CGLIB] hashStable=true
[CGLIB] toString=ReportService(target)
[CGLIB] adviceBeforeBusiness=0
[ADVICE] before runReport
[TARGET] run CGLIB
[CGLIB] result=report:CGLIB
[CGLIB] adviceAfterBusiness=1
```

Meaning:

1. **Two different proxy types** despite sharing the exact same source class and aspect. `AopUtils` gives more direct evidence than comparing class name prefixes.
2. `equalsSelf=true` verifies reflexivity on the object Spring returned; it **does not prove** `proxy.equals(rawTarget)` or `proxyA.equals(proxyB)`.
3. `hashStable=true` verifies two consecutive calls in the example config yield the same hash; the program **does not print the hash number** because that is not a portable contract.
4. `toString` displays the target's intentional output. It does not return the generated proxy class name, and should not be used to detect proxy type.
5. `adviceBeforeBusiness=0` indicates the `Object` method calls above **did not trigger `@Before`, which only selects `runReport`**.
6. After one business call through the Spring bean proxy, `adviceAfterBusiness=1`, the target method ran once, and the return value is preserved.

The example does not claim `toString()` **cannot** be advised. It only shows **the application's pointcut intentionally selected just the business method**.

## 8. Further Testing Practical Equality Between Two Spring Proxies

An application needing to compare proxies should explicitly test the scenarios it will actually execute:

```java
// Illustrative snippet placed in a test with an ApplicationContext context.
Object first = context.getBean("reportOperations");
Object second = context.getBean("reportOperations");

System.out.println("sameReference=" + (first == second));
System.out.println("equalByEquals=" + first.equals(second));
System.out.println("hashEqualIfEquals="
        + (!first.equals(second) || first.hashCode() == second.hashCode()));
```

With singleton beans like in the example, two lookups of the same bean name in one context normally return the same reference; in that case, the first two lines are usually `true`. However, that is a result of **singleton bean lookup** and **proxy identity**, not proof that two *distinct* proxies share equality semantics.

When evaluating **two different proxies**, set up two separate bean definitions or two Spring contexts; test:

```java
boolean leftEqualsRight = left.equals(right);
boolean rightEqualsLeft = right.equals(left);
boolean hashesAgreeWhenEqual =
        !leftEqualsRight || left.hashCode() == right.hashCode();
```

This is a fragment requiring `left` and `right` variables in the test. Beyond `equals`/hash, also verify **symmetry** in both directions and **transitivity** with three objects. Do not hardcode that two distinct proxies wrapping the same target type must be equal.

If the target itself overrides `equals`/`hashCode`, rerun the exact same test under JDK proxies and CGLIB; the target overriding them does not mean both proxy styles forward the methods identically.

### 8.1. Testing the Right Scopes and Bean Retrieval Paths

Practical cases worth checking:

| Scenario | What to observe |
| --- | --- |
| Retrieving a singleton bean with the same name twice | `==`, `equals`, `hashCode`; expected stable reference in the same context. |
| Retrieving a prototype bean twice | Two bean/proxy references and equality semantics; do not assume they are equal by default. |
| Two bean names pointing to two target instances | Equality of the two proxies and hash contract if equal. |
| Request/session scoped proxy | Separates long-lived proxy reference from scope-varying target. |
| Two independent ApplicationContexts | Compare only after confirming identical configs and without assuming JVM-wide singletons. |
| Target overrides Object methods | Test symmetry/consistency of proxy, target, and related domain value objects. |

Evaluate the semantics your application actually needs. There is no need to reach into internals if an independent business identifier suffices as a key.

## 9. Common Mistakes When Debugging These Three Methods on a Spring Proxy

### 9.1. “The Target Overrides `equals`, So the Proxy Uses the Exact Same Logic”

**Wrong when treated as a default rule.** Spring AOP can handle `equals` at the proxy infrastructure layer, especially when interfaces do not declare that method, or when using a dedicated CGLIB interceptor. Separate tests for raw targets from tests for proxies retrieved from Spring.

### 9.2. “Two Proxies of the Same Target Class Must Be Equal”

**Insufficient basis.** Target class is only one factor; interface sets, advisors, and `TargetSource` can participate. `proxy1 == proxy2` is a separate identity check.

### 9.3. “Equal Hash Codes Prove Two Spring Beans Are the Same”

**No.** Hash collisions are always possible. Use `==` to test same reference, bean name/type to check config, business keys for business comparison, and `equals` per the actual contract. Hash codes only help data structures distribute buckets; they do not prove identity.

### 9.4. “Printing `toString` Is Enough to Know If a Bean Is Proxied”

**No.** The target may override `toString` and return a fixed string as in the demo. Use:

```java
boolean aop = org.springframework.aop.support.AopUtils.isAopProxy(bean);
boolean jdk = org.springframework.aop.support.AopUtils.isJdkDynamicProxy(bean);
boolean cglib = org.springframework.aop.support.AopUtils.isCglibProxy(bean);
```

This fragment requires a `bean` variable retrieved from the container. Having an AOP proxy still **does not guarantee** a specific method is advised; inspect pointcuts and invocations.

### 9.5. “`toString` Is Harmless, We Can Log Every Spring Bean”

**Not always true.** A target's `toString` might touch a large object graph, secret properties, lazy-loaded associations, or heavy computation. Some advice can even match that method when pointcuts are overly broad. In production, logging curated filtered fields is safer and easier to control.

### 9.6. “CGLIB Always Intercepts Every Object Method”

**No.** Class proxies are bounded by inheritance and overridability; `final` methods, `private` methods, or `final` classes have limits. Specifically, `equals`/`hashCode` also have special implementation branches. Do not switch from JDK to CGLIB just trying to “guarantee” domain equality, as that is not the responsibility of proxy type selection.

### 9.7. “No `@Before` Line Means Object Methods Did Not Go Through the Proxy”

**Flawed reasoning.** Advice may match only business methods. An `Object` method can still be processed by the proxy without matching that advisor. To determine the dispatch flow, inspect advisors/pointcuts and test each method explicitly.

## 10. Checklist When Refactoring AOP or Upgrading Spring Versions

1. **Identify the exact proxy type** from the injected bean using `AopUtils.isJdkDynamicProxy`/`isCglibProxy`.
2. **Identify bean scope and reference semantics:** singleton, prototype, scoped proxy; distinguish proxy vs. target.
3. **Test `equals` reflexivity and symmetry** on the exact object combinations the application intends to compare.
4. **Test `hashCode` stability** and the `equals => same hash` contract; do not assert specific hash integers.
5. **Verify `toString` produces valid output**, triggers no unintended side effects, and exposes no sensitive data.
6. **Measure advice invocation counts** before/after calling `equals`/`hashCode`/`toString`, especially with broad pointcuts or special advisors.
7. **Compare JDK vs. CGLIB** when changing `proxyTargetClass`, modifying interfaces, enabling Spring Boot auto-config, or upgrading framework versions.
8. **Do not use proxy equality as business identity** when the primary requirement is comparing domain objects by id.
9. **Audit usage in collections/caches**: if proxies are used as keys, determine key lifecycle and stability under real configurations.
10. **Capture observations in automated tests** running on a production-like Spring context; separate guarantees of the Java Object contract from internal implementation details of a specific Spring release.

### Reference Documentation

- Spring Framework — Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework — AOP Proxies: https://docs.spring.io/spring-framework/reference/core/aop/introduction-proxies.html
- Spring Framework — Spring AOP APIs: https://docs.spring.io/spring-framework/reference/core/aop-api.html
- Spring Framework — JdkDynamicAopProxy source: https://github.com/spring-projects/spring-framework/blob/main/spring-aop/src/main/java/org/springframework/aop/framework/JdkDynamicAopProxy.java
- Spring Framework — CglibAopProxy source: https://github.com/spring-projects/spring-framework/blob/main/spring-aop/src/main/java/org/springframework/aop/framework/CglibAopProxy.java

**When working with Spring AOP, treat `equals`, `hashCode`, and `toString` as calls whose semantics must be verified directly on the real proxy.** This prevents false assumptions about identity, avoids cache bugs, and clearly separates advice policies from Spring's object dispatch mechanics.
