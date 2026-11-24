# Type Casting Failure Scenario When Switching Proxy Mechanisms in Spring AOP

## 1. Symptom: The Bean Still Works, Yet Casting to the Implementation Class Fails

When Spring AOP wraps a Spring bean in a proxy, **the runtime type of the reference received by callers may no longer be the target's concrete type**. In configurations using a **JDK dynamic proxy**, the proxy implements the interfaces exposed by the bean, yet **does not extend the implementation class**. Therefore, code casting from an interface reference to the implementation can throw `ClassCastException`, even though calling methods via the interface still triggers advice normally.

Conceptual example:

~~~java
PaymentOperations payment = context.getBean(PaymentOperations.class);
payment.pay("A-01");                 // Valid for JDK proxy and CGLIB proxy

PaymentService impl = (PaymentService) payment;
// ClassCastException if payment is a JDK dynamic proxy
~~~

The snippet above belongs to a Spring app that already declares `PaymentOperations` and `PaymentService`, not a standalone runnable program. It shows **the error is about the runtime object's type**, not a broken `pay` method or wrong pointcut. Conversely, if Spring creates a **CGLIB class-based proxy**, the proxy is a subclass of `PaymentService` and can be cast to `PaymentService` when the class can be validly subclassed.

In practice, this scenario often appears after changing `proxyTargetClass`, modifying `@EnableAspectJAutoProxy` settings, changing Spring Boot's `spring.aop.proxy-target-class` property, adding transaction AOP config, or upgrading Spring config so a previously used proxy is now created by a different mechanism.

**Lesson scope:** analyzing casting errors caused by **Spring AOP proxies**, reproducing with two ApplicationContexts, how to verify the right proxy type, and fixing dependencies/call sites. `@AspectJ` syntax is used solely to enable advice in Spring; this lesson does not go deep into AspectJ weaving outside Spring.

## 2. Two Proxies Have Different Type Relationships

Suppose we have:

~~~java
public interface PaymentOperations {
    void pay(String orderId);
}

public class PaymentService implements PaymentOperations {
    @Override
    public void pay(String orderId) {
        System.out.println("SERVICE: paid " + orderId);
    }
}
~~~

These are **two abbreviated definitions**; the complete files appear in section 4. Spring AOP has two common wrapper mechanisms:

~~~text
Target class:
PaymentService implements PaymentOperations

JDK dynamic proxy:
         PaymentOperations
                ^
                |
          jdk.proxy...$Proxy...
                |
         [delegates to target PaymentService]

  proxy instanceof PaymentOperations -> true
  proxy instanceof PaymentService    -> false

CGLIB class proxy:
          PaymentService
                ^
                |
       PaymentService$$SpringCGLIB$$...
                |
         [delegates to target PaymentService]

  proxy instanceof PaymentOperations -> true
  proxy instanceof PaymentService    -> true
~~~

The proxy names above are conceptual only: prefixes/numeric suffixes in class names can vary across JDK and Spring versions. Inspect using `instanceof` and `AopUtils` instead of matching class name strings.

| Check on an AOP-proxied bean | JDK dynamic proxy | CGLIB class proxy |
| --- | --- | --- |
| `bean instanceof PaymentOperations` | `true` | `true` |
| `bean instanceof PaymentService` | `false` | `true` |
| `((PaymentService) bean)` | `ClassCastException` | Cast succeeds if proxy matches target class |
| `AopUtils.isJdkDynamicProxy(bean)` | `true` | `false` |
| `AopUtils.isCglibProxy(bean)` | `false` | `true` |
| `AopUtils.isAopProxy(bean)` | `true` | `true` |
| `bean.getClass() == PaymentService.class` | `false` | `false` |

Conditions for this table: **both objects are valid Spring AOP proxies of the same target type**; the CGLIB class proxy can be created and the bean is actually proxied. If no advisor applies or the bean is not container-processed, the object may be the raw target and results will differ.

When using a JDK proxy, the JVM forbids downcasting to `PaymentService` because the proxy has no inheritance relationship with that class. The fact that the target behind the proxy is `PaymentService` **does not make the proxy object itself a `PaymentService`**.

## 3. Why Can Changing Configuration Break Existing Code?

### 3.1. `proxyTargetClass` Selects the Proxy Mechanism

In plain Spring Framework:

~~~java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = false)
class InterfaceProxyConfig {
}
~~~

For a target implementing an interface with a matching advisor, Spring **usually** selects a JDK dynamic proxy. `false` means do not force class-based proxies; when a target lacks suitable interfaces, Spring can still use CGLIB.

Another configuration:

~~~java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
class ClassProxyConfig {
}
~~~

`true` forces the auto-proxy infrastructure to choose **class-based proxies** when beans need AOP. If two configurations activate the same auto-proxy creator in **the same ApplicationContext**, the stronger setting (`true`) can be merged and affect **multiple beans**, not just beans “belonging to” that configuration class.

A commonly encountered transition flow:

~~~text
Before:
bean implements interface
  |
@EnableAspectJAutoProxy(proxyTargetClass = true)
  |
Spring returns CGLIB subclass proxy
  |
(PaymentService) bean -> OK

After:
remove forced class proxy / set false
  |
Spring chooses JDK proxy for interface-backed bean
  |
(PaymentService) bean -> ClassCastException
~~~

The reverse direction can also affect applications: code that assumed `bean.getClass()` was a JDK proxy type, extracted methods/fields via reflection, or compared exact proxy class names may no longer fit when switching to CGLIB. Most applications should depend on **interfaces/capabilities**, not on the runtime implementation of proxies.

### 3.2. Spring Boot Has Its Own Default

Spring Boot with AOP auto-configuration usually prefers class-based proxies. You can configure:

~~~properties
spring.aop.proxy-target-class=true
~~~

or:

~~~properties
spring.aop.proxy-target-class=false
~~~

In the corresponding setup, `false` allows interface-based proxies when suitable interfaces exist. However, other annotations or XML AOP/transaction configs can push the merged setting to class proxies in the same context. Therefore **do not infer the final proxy type from a single properties line**; inspect the actual bean.

### 3.3. When Source Code Casts Directly from `getBean(...)`

Two bean retrieval patterns must be distinguished:

~~~java
Object bean = context.getBean("paymentService");
PaymentService impl = (PaymentService) bean; // Possible ClassCastException
~~~

and:

~~~java
PaymentService impl = context.getBean(PaymentService.class);
// Can fail when the actual bean is a JDK proxy.
~~~

The first retrieves a reference by name and then performs a **Java cast**, so `ClassCastException` is the direct result if the JDK proxy is not assignable to `PaymentService`. The second is a **type-based lookup in BeanFactory**: depending on the bean definition, type prediction, and proxy creation timing, Spring may throw `NoSuchBeanDefinitionException`, `BeanNotOfRequiredTypeException`, or another relevant error. Do not assume every “type mismatch” error in Spring is a `ClassCastException`.

With injection:

~~~java
public PaymentJob(PaymentService paymentService) {
    this.paymentService = paymentService;
}
~~~

If only a JDK-proxied bean exposing `PaymentOperations` exists, a dependency typed as the implementation class is no longer type-compatible and can prevent the context from starting with a related autowiring/creation failure. This is an **illustrative constructor snippet** inside a class with a corresponding field, not a standalone Java file.

## 4. Java 17+ Application Reproducing Both the Error and Working Behavior

The example runs with **Java 17+, Maven 3.9+, Spring Framework 6.2.0**. Two ApplicationContexts use **the exact same service and aspect definitions** but different proxy configurations. We intentionally catch `ClassCastException` in JDK mode so the program continues and records the result; in CGLIB mode, the cast succeeds.

Project structure:

~~~text
spring-aop-proxy-cast/
├── pom.xml
└── src/main/java/example/
    ├── Demo.java
    ├── PaymentOperations.java
    ├── PaymentService.java
    └── AuditAspect.java
~~~

### 4.1. Create `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-aop-proxy-cast</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.0</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.22</version>
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
                <version>3.5.0</version>
                <configuration>
                    <mainClass>example.Demo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` supplies `AnnotationConfigApplicationContext` and bean configuration, `spring-aop` holds the proxy infrastructure along with `AopUtils`; `aspectjweaver` supplies the AspectJ types used when Spring parses `@AspectJ` pointcuts. Having `aspectjweaver` in the project **does not** enable AspectJ bytecode weaving; the code below uses only Spring AOP proxies.

### 4.2. Interface Used by Callers

`src/main/java/example/PaymentOperations.java`:

~~~java
package example;

public interface PaymentOperations {
    void pay(String orderId);
}
~~~

### 4.3. Class Implementing the Interface

`src/main/java/example/PaymentService.java`:

~~~java
package example;

public class PaymentService implements PaymentOperations {
    @Override
    public void pay(String orderId) {
        System.out.println("SERVICE: paid " + orderId);
    }

    public void implementationOnly() {
        System.out.println("IMPLEMENTATION: called");
    }
}
~~~

The `implementationOnly()` method does not belong to the interface. It serves to prove a class proxy can expose implementation-class methods, whereas a JDK proxy does not. This method itself **is not advised by the aspect below** because the pointcut only matches `pay(...)`.

### 4.4. Aspect Ensuring the Service Needs Proxying

`src/main/java/example/AuditAspect.java`:

~~~java
package example;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class AuditAspect {
    @Before("execution(* example.PaymentService.pay(..))")
    public void beforePayment() {
        System.out.println("ADVICE: before pay");
    }
}
~~~

Spring recognizes `AuditAspect` as an aspect when it is registered as a **Spring bean**. The `execution(* example.PaymentService.pay(..))` expression matches `pay` method executions on the target. This advisor causes `PaymentService` to be auto-proxied when Spring AOP is enabled, allowing us to test both proxy types' behavior.

### 4.5. Running Two Contexts with Different Flags

`src/main/java/example/Demo.java`:

~~~java
package example;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

public class Demo {
    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy(proxyTargetClass = false)
    public static class BaseConfig {
        @Bean
        public PaymentService paymentService() {
            return new PaymentService();
        }

        @Bean
        public AuditAspect auditAspect() {
            return new AuditAspect();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy(proxyTargetClass = true)
    public static class ForceClassProxyConfig {
    }

    private static void inspect(
            String label,
            AnnotationConfigApplicationContext context,
            boolean expectClassProxy) {

        PaymentOperations bean = context.getBean(PaymentOperations.class);

        boolean aop = AopUtils.isAopProxy(bean);
        boolean jdk = AopUtils.isJdkDynamicProxy(bean);
        boolean cglib = AopUtils.isCglibProxy(bean);
        boolean implementation = bean instanceof PaymentService;

        if (!aop || cglib != expectClassProxy
                || jdk == expectClassProxy
                || implementation != expectClassProxy) {
            throw new IllegalStateException("Unexpected proxy type: " + label);
        }

        System.out.println(label + "_JDK: " + jdk);
        System.out.println(label + "_CGLIB: " + cglib);
        System.out.println(label + "_IS_IMPLEMENTATION: " + implementation);

        bean.pay("A-01");

        if (expectClassProxy) {
            PaymentService service = (PaymentService) bean;
            System.out.println(label + "_CAST: OK");
            service.implementationOnly();
        } else {
            try {
                PaymentService service = (PaymentService) bean;
                service.implementationOnly();
                throw new IllegalStateException("JDK cast unexpectedly worked");
            } catch (ClassCastException expected) {
                System.out.println(label + "_CAST: ClassCastException");
            }
        }
    }

    public static void main(String[] args) {
        try (var jdk =
                new AnnotationConfigApplicationContext(BaseConfig.class)) {
            inspect("JDK", jdk, false);
        }

        try (var cglib = new AnnotationConfigApplicationContext(
                BaseConfig.class, ForceClassProxyConfig.class)) {
            inspect("CGLIB", cglib, true);
        }

        System.out.println("CHECK: PASS");
    }
}
~~~

**Why do the two contexts produce different results?**

1. `BaseConfig` declares `@EnableAspectJAutoProxy(proxyTargetClass = false)`. `PaymentService` implements `PaymentOperations` and has an applicable `@Before` advisor, so in plain Spring Framework 6.2 this example uses a **JDK dynamic proxy**.
2. `ForceClassProxyConfig` only adds `@EnableAspectJAutoProxy(proxyTargetClass = true)`, defining no extra service or aspect. When loaded into **the same context** as `BaseConfig`, the auto-proxy infrastructure merges with the `true` setting and creates a **CGLIB class proxy**.
3. In both contexts, callers retrieve `PaymentOperations` via the Spring container and `bean.pay("A-01")` passes through the advisor. Therefore, the cast error **does not stem from missing Spring AOP advice**.
4. `AopUtils.isAopProxy`, `isJdkDynamicProxy`, and `isCglibProxy` measure the runtime proxy type. `bean instanceof PaymentService` verifies type assignability before casting.
5. The JDK branch intentionally casts the `PaymentOperations` reference to `PaymentService`. `ClassCastException` is caught to print a stable explanatory line, avoiding dependence on JDK exception message strings.
6. The CGLIB branch casts successfully and invokes `implementationOnly()`, though this method does not match the pointcut so no extra `ADVICE` is printed.
7. The validation condition actively throws `IllegalStateException` if proxy assumptions fail, so `CHECK: PASS` is not printed unconditionally up front.

### 4.6. Running and Verifying Output

Run in the `spring-aop-proxy-cast` directory:

~~~bash
mvn -q compile exec:java
~~~

Lines printed by the application code in exact order:

~~~text
JDK_JDK: true
JDK_CGLIB: false
JDK_IS_IMPLEMENTATION: false
ADVICE: before pay
SERVICE: paid A-01
JDK_CAST: ClassCastException
CGLIB_JDK: false
CGLIB_CGLIB: true
CGLIB_IS_IMPLEMENTATION: true
ADVICE: before pay
SERVICE: paid A-01
CGLIB_CAST: OK
IMPLEMENTATION: called
CHECK: PASS
~~~

Maven, SLF4J, or Spring may emit additional messages depending on the environment. Only the lines above are produced by the example's `System.out.println`.

Notable results:

- **Both modes print `ADVICE: before pay`** before the business logic.
- **Only the JDK proxy fails assignment to the implementation class**; the cast error is intentionally reproduced.
- **The CGLIB proxy is assignable to the implementation class**, yet being able to call an implementation method **does not mean that method will be advised**.
- `CHECK: PASS` confirms the right proxy types in both contexts and that the program ran to completion without unexpected errors.

## 5. Fixing Properly Based on Requirements

### 5.1. Prefer Interfaces for Dependencies Callers Need

If business code only needs the `pay(...)` contract, the most stable solution is injecting/retrieving the bean by interface:

~~~java
package example;

public final class PaymentJob {
    private final PaymentOperations payments;

    public PaymentJob(PaymentOperations payments) {
        this.payments = payments;
    }

    public void execute() {
        payments.pay("A-01");
    }
}
~~~

This is a **complete Java class**, though for Spring to instantiate/inject it, `PaymentJob` must be registered as a bean in the application, e.g., via `@Bean` or `@Component`. The `PaymentOperations` type is compatible with both JDK proxies and CGLIB proxies. If multiple beans share the interface, add `@Qualifier`/`@Primary` to select the right bean; those annotations **do not change the underlying proxy type**.

With existing code:

~~~java
PaymentOperations payments = context.getBean(PaymentOperations.class);
payments.pay("A-01");
~~~

Keeping the interface throughout the call chain avoids downcasting to the implementation just to invoke a method already declared in the contract.

### 5.2. Genuinely Need an Implementation-Only Method?

In the example, `implementationOnly()` belongs only to `PaymentService`. There are three choices:

1. **Add that method to the interface** if it is genuinely public behavior callers need; then the JDK proxy can expose that method. Update the interface contract explicitly and check pointcuts/advice if necessary.
2. **Extract the capability into a separate interface/service** if the implementation-only method does not belong in the current contract. This is usually better than casting based on a concrete class.
3. **Request class proxies with `proxyTargetClass = true`** when there is a compelling reason to work through the implementation class. Evaluate impact on **other AOP beans in the same context**, `final` classes/methods, module/JDK compatibility, and other AOP/transaction settings. Do not treat this as a one-line fix affecting only one bean.

Casting with `(PaymentService)` after an `instanceof` check avoids throwing an exception via conditional logic, yet **does not grant access to implementation-only methods when the runtime proxy is JDK**. What needs fixing is the contract or configuration, not adding guarded casts.

### 5.3. Avoid Looking Up Implementation Classes Unnecessarily

With a JDK proxy, the following patterns can fail at different stages:

~~~java
Object bean = context.getBean("paymentService");
PaymentService cast = (PaymentService) bean;
~~~

This is a direct Java cast that can throw `ClassCastException`.

~~~java
PaymentService byType = context.getBean(PaymentService.class);
~~~

This is a concrete-type lookup that can fail because the proxy is not assignable to `PaymentService`; the exact Spring exception type depends on BeanFactory resolution and type checking. Avoid “catching `ClassCastException`” as the sole handling strategy for `getBean(Class)` or autowiring scenarios.

Interface solution:

~~~java
PaymentOperations byContract = context.getBean(PaymentOperations.class);
~~~

All snippets in this section **go inside a method that already has a `context` variable** and the sample classes defined in section 4; they are not standalone runnable files.

### 5.4. Inspecting Target Metadata Without Casting the Proxy to the Target

When needed for logging/debugging:

~~~java
Object bean = context.getBean("paymentService");

System.out.println(
    org.springframework.aop.support.AopUtils.isAopProxy(bean));
System.out.println(
    org.springframework.aop.support.AopUtils.isJdkDynamicProxy(bean));
System.out.println(
    org.springframework.aop.support.AopUtils.isCglibProxy(bean));
System.out.println(
    org.springframework.aop.support.AopUtils.getTargetClass(bean).getName());
~~~

`AopUtils.getTargetClass(bean)` lets you inspect the target class known to Spring AOP, **without turning the proxy into an instance of that class**. This is a check inserted into an existing application; it does not recommend unwrapping the proxy to call the target directly. Extracting the target object and invoking it directly can bypass advice, transactions, and security.

## 6. “Fixes” That Commonly Introduce New Bugs

| Attempted fix | Why it is wrong or insufficient |
| --- | --- |
| Adding `(PaymentService)` casts in more places | Does not change the JDK proxy's type hierarchy; still throws `ClassCastException` |
| Using `@Qualifier("paymentService")` while the field/constructor type is `PaymentService` | `@Qualifier` selects a bean by name/metadata; it does not turn a JDK proxy into the implementation |
| Setting `proxyTargetClass = true` on one config assuming only that bean is affected | Auto-proxy settings can merge, switching proxy types for many beans in the same context |
| Assuming `@Aspect` or `@Before` creates a CGLIB proxy | Aspects declare advisors; proxy type is decided by infrastructure and configuration |
| Adding `aspectjweaver` or `-javaagent` solely to fix a cast | Switching to weaving is a separate concern; Spring proxy casts must be handled via contract/proxy strategy |
| Casting after calling `AopUtils.getTargetClass` | Target class metadata does not make the reference an object of that class |
| Unwrapping the target object inside the proxy and calling methods directly | Can bypass advice and behaviors built on Spring AOP |
| Making the entire class/methods `final` and forcing CGLIB | CGLIB subclass proxies cannot override `final` methods or subclass `final` classes |
| Checking `bean.getClass() == PaymentService.class` to confirm advice | For both JDK and CGLIB, the proxy runtime class usually differs from the target class |
| Expecting `this.pay()` to be advised after forcing CGLIB | Self-invocation on the target still bypasses the Spring proxy |

Enabling CGLIB due to a cast in one spot can cause side effects for other beans: `final` classes cannot be subclass-proxied, `final`/`private` methods cannot be overridden to intercept, and injection points using interfaces or reflection may behave unexpectedly. Audit all advised beans when changing context-wide configuration.

## 7. Workflow for Finding the Root Cause in a Spring Application

When encountering a `ClassCastException` containing a class name like `jdk.proxy...$Proxy...` or an injection/lookup error by implementation:

1. **Identify the real reference:** did the bean come from `ApplicationContext` or was it created with `new`? If from Spring, record the bean name and lookup/injection method. With proxies, cast errors depend on the runtime type.
2. **Inspect interfaces and implementation:** which interfaces does the target have? Does the call site need a contract method or an implementation-only method?
3. **Measure three states on the reference:** `AopUtils.isAopProxy`, `isJdkDynamicProxy`, `isCglibProxy`, combined with `instanceof Interface` and `instanceof Implementation`.
4. **Find the effective proxy settings:** `@EnableAspectJAutoProxy`, `proxyTargetClass`, Spring Boot AOP properties, XML `<aop:aspectj-autoproxy/>`, transaction auto-proxy config, parent/child contexts, and merged settings.
5. **Check why the bean is proxied:** which advisor/`@Aspect` matches; a bean matching no advisor can be a plain target and fail to reproduce the bug.
6. **Fix the dependency design properly:** prefer interfaces for public behavior, use `@Qualifier` if multiple implementations exist. If an implementation method is mandatory, weigh changing the contract vs. class proxies.
7. **Audit classes and methods when forcing CGLIB:** `final`, `private`, visibility, Java modules, and subclassing eligibility.
8. **Rerun verification:** assert the right proxy type, invoke the method through the bean reference, and confirm advice runs; do not stop merely because casting no longer throws an exception.

### Distinguishing Error Types

- **`ClassCastException` on `(PaymentService) object`**: the runtime reference is not an instance of that class; if it is a JDK proxy, this is the natural consequence.
- **`BeanNotOfRequiredTypeException` / concrete-type lookup failure**: the Spring bean does not match the type requested by the client; inspect BeanFactory traces and injection points.
- **`NoSuchBeanDefinitionException`**: no bean satisfying the requested type/name was found in the queried context; could be wrong context, missing registration, or different exposed type.
- **`NoUniqueBeanDefinitionException`**: multiple beans share the interface, requiring selection via `@Qualifier`/`@Primary` — this is not a JDK/CGLIB cast error.
- **Advice does not run even though the bean casts fine**: a successful cast **does not guarantee a proxy exists** or a pointcut matches. Check `AopUtils.isAopProxy` and calls through the proxy.

## 8. Self-Check Questions

1. **Why is a JDK proxy assignable to `PaymentOperations` but not to `PaymentService`?**  
   Because the proxy implements the interface, and is not a subclass of the implementation class.

2. **When using CGLIB, is every cast down to the concrete class guaranteed safe?**  
   No. It is safe only when the reference is genuinely an instance/subclass of the desired class, the target is eligible for subclassing, and there is no bean ambiguity.

3. **How should a bean whose public methods are only through an interface be fixed so it does not depend on proxy type?**  
   Inject/retrieve and call through the interface, avoiding downcasting to the implementation.

4. **Does `@Qualifier` fix a `ClassCastException` caused by a JDK proxy?**  
   No. It only helps select a bean, without changing the type hierarchy.

5. **Why can `getBean(PaymentService.class)` and `(PaymentService) getBean("paymentService")` produce different exceptions?**  
   The former is Spring-performed lookup/type checking, whereas the latter is a JVM object cast.

6. **Is adding `proxyTargetClass = true` enough to eliminate errors everywhere?**  
   No. The setting is scoped to the context/auto-proxy creator, can affect multiple beans, and has subclassing limits; prioritize reviewing the contract first.

7. **Does CGLIB fix self-invocation?**  
   No. `this.otherMethod()` inside the target can still bypass the Spring proxy.

## Spring Framework Documentation

- [Spring Framework 6.2 — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): JDK dynamic proxies, CGLIB proxies, limits, and self-invocation.
- [Spring Framework 6.2 — AOP Proxies](https://docs.spring.io/spring-framework/reference/6.2/core/aop/introduction-proxies.html): Spring AOP's proxy model.
- [Spring Framework 6.2 — @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj.html): how Spring uses aspect declaration syntax.
- [Spring Framework 6.2 — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html): configuring `@EnableAspectJAutoProxy`.
- [Spring Boot Reference — AOP](https://docs.spring.io/spring-boot/reference/features/aop.html): `spring.aop.proxy-target-class` in Boot.
