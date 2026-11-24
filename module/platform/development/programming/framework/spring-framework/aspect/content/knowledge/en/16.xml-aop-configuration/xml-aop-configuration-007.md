# Configuring `order` in XML and Declaration-Order Differences vs. `@Aspect` in Spring AOP

## 1. The Problem: Multiple Advices Applying to One Spring Bean

When a Spring bean has multiple XML or annotation advices matching it, the observed outcome depends on **advisor chain precedence**. There are three distinct scopes: (1) `order` between aspects/advisors, (2) **declaration order of advice elements within the same XML `<aop:aspect>`**, and (3) annotation advice rules within the same `@Aspect` class. This lesson focuses on **comparing these three scopes with the exact same invocation**, because code/bean definition placement cannot substitute for an ordering contract.

Consider two nested around advices: the higher-precedence aspect enters first and exits last. Placing audit outside metrics produces the trace `AUDIT enter → METRICS enter → target → METRICS exit → AUDIT exit`.

## 2. `order`: Smaller Numbers Have Higher Precedence

A **smaller** `order` number means **higher** precedence. Example:

~~~xml
<aop:aspect ref="auditBean" order="1">
    <aop:around method="around" pointcut-ref="payment"/>
</aop:aspect>
<aop:aspect ref="metricsBean" order="2">
    <aop:around method="around" pointcut-ref="payment"/>
</aop:aspect>
~~~

This is a fragment requiring two declared beans and a pointcut. If both call `proceed()`, audit wraps metrics, so the log prints:

~~~text
AUDIT enter
METRICS enter
PAY
METRICS exit
AUDIT exit
~~~

A smaller number does not mean logs always appear first on exit: the outer aspect finishes **last** on the unwind path. If two aspects lack explicit precedence, do not rely on XML line order or bean creation order.

## 3. XML: `<aop:aspect order="...">` Controls Precedence Between Aspects

Spring supports the `aop` namespace; a valid configuration requires the namespace/schema and beans holding the advice logic:

```xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:aop="http://www.springframework.org/schema/aop"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/aop
           https://www.springframework.org/schema/aop/spring-aop.xsd">

    <bean id="billingService" class="demo.BillingService"/>
    <bean id="auditBean" class="demo.XmlAuditAspect"/>
    <bean id="metricsBean" class="demo.XmlMetricsAspect"/>

    <aop:config proxy-target-class="true">
        <aop:pointcut id="payment"
                      expression="execution(* demo.BillingService.pay(..))"/>

        <aop:aspect id="audit" ref="auditBean" order="1">
            <aop:around method="around" pointcut-ref="payment"/>
        </aop:aspect>

        <aop:aspect id="metrics" ref="metricsBean" order="2">
            <aop:around method="around" pointcut-ref="payment"/>
        </aop:aspect>
    </aop:config>
</beans>
```

Inside `<aop:config>`, declare **pointcuts first, advisors second, and aspects last** if all three element types coexist. `ref` in `<aop:aspect>` references an ordinary Java bean: the class containing the `around` method **does not need** `@Aspect` because the pointcut/advice are described in XML.

Key distinctions:

- `order` on `<aop:aspect>` controls precedence **between aspects**. It does not reorder methods inside the backing bean class.
- You can use `@Order` or implement `org.springframework.core.Ordered` on the aspect backing bean per Spring rules; if you already chose transparent XML configuration, placing `order` directly on `<aop:aspect>` is usually easier to inspect.
- Setting `proxy-target-class="true"` chooses a subclass-based proxy in the example; it **does not** turn Spring AOP into AspectJ weaving.
- When using a standalone `<aop:advisor>`, the advisor element itself also has its own `order` attribute, e.g., `<aop:advisor advice-ref="guardAdvice" pointcut-ref="payment" order="0"/>`. `guardAdvice` must be an appropriate advice bean, such as one implementing `org.aopalliance.intercept.MethodInterceptor`. This illustrates the attribute, not a standalone runnable advisor.
- When other Spring advisors exist such as transaction/security advisors, you must consider **their** order as well. You cannot deduce total system order from a single `<aop:aspect order="...">`.

## 4. Core Difference: **Advice Declaration Order Within the Same XML Aspect**

According to the Spring AOP schema documentation, when **two advices reside inside the same** `<aop:aspect>` and match the same join point, **the top-to-bottom declaration order of advice elements determines precedence from highest to lowest**.

Illustrative example, assuming the backing bean has matching `around` and `check` methods:

```xml
<aop:aspect id="validationAndAudit" ref="validationAuditBean" order="3">
    <aop:around method="around" pointcut-ref="payment"/>
    <aop:before method="check" pointcut-ref="payment"/>
</aop:aspect>
```

Here `around` is declared **before** `check`, so it has higher precedence and wraps outside when the advice chain runs. Swapping the two lines changes their precedence within this XML aspect group.

Distinguish these two kinds of changes:

| Action | Expected Effect |
|---|---|
| Change `order="1"` to `order="5"` on an `<aop:aspect>` | Changes priority of **that aspect relative to other aspects/advisors** |
| Swap `<aop:around>` and `<aop:before>` **within the same** `<aop:aspect>` | Changes **internal** precedence of XML advices in that aspect |
| Swap positions of two different `<aop:aspect>` elements while keeping `order` 1 and 2 | Does not reverse precedence defined by the two `order` values |
| Swap positions of two `@Before` methods inside a Java `@Aspect` class | Does not establish guaranteed execution order |

**Do not infer** that "XML always runs every element in file order". The declaration-order rule here applies to **advices within a single `<aop:aspect>`**, whereas precedence across aspects requires `order`.

If an XML aspect has multiple advices matching the same pointcut, keep the order clear and avoid writing advices that depend on each other's side effects. When ordering becomes hard to express, split into separate aspects with `order` or consolidate sequential logic into a single `around` advice with an explicit call sequence.

## 5. Compared to `@Aspect`: `@Order` Is Only at the Aspect Level

In annotation configuration, Spring-managed classes use `@Aspect` and `@Order`:

```java
@Aspect
@Order(1)
public class AnnotationAuditAspect {
    @Around("execution(* demo.BillingService.pay(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("AUDIT enter");
        try {
            return pjp.proceed();
        } finally {
            System.out.println("AUDIT exit");
        }
    }
}
```

And a second aspect:

```java
@Aspect
@Order(2)
public class AnnotationMetricsAspect {
    @Around("execution(* demo.BillingService.pay(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("METRICS enter");
        try {
            return pjp.proceed();
        } finally {
            System.out.println("METRICS exit");
        }
    }
}
```

Both snippets show only class bodies (requiring imports for `@Aspect`, `@Order`, `@Around`, and `ProceedingJoinPoint`); **full file** versions appear in the runnable example below.

`@Order(1)` and `@Order(2)` produce a wrapping chain **similar to XML**. However, if one `@Aspect` class has multiple advices:

- Spring applies precedence by **advice type** within the same aspect: `@Around`, `@Before`, `@After`, `@AfterReturning`, `@AfterThrowing` from highest to lowest per Spring's rules. Specifically, `@After` has finally semantics, so in practice it runs after the corresponding `@AfterReturning` or `@AfterThrowing`.
- When multiple advices **of the same type** (for example, two methods both annotated with `@Before`) in the same `@Aspect` class match the same join point, **the order between them is undefined**. Java reflection does not guarantee preserving source declaration order of methods.
- `@Order` on the **aspect class** does not select an order between two `@Before` methods **in the same class**. Reordering the two methods in source code does not fix this either.
- If the order between two same-type advices is a business requirement, merge them into one advice with explicit call order, or split them into two `@Aspect` classes and specify `@Order` on each class.

Example **not to rely on declaration order**:

```java
@Aspect
@Order(1)
public class AmbiguousBeforeAspect {
    @Before("execution(* demo.BillingService.pay(..))")
    public void validate() {
        System.out.println("validate");
    }

    @Before("execution(* demo.BillingService.pay(..))")
    public void audit() {
        System.out.println("audit");
    }
}
```

This snippet only illustrates the ordering pitfall; it is not one of the two aspect files in the runnable example below. **Do not assume** stdout must be `validate` then `audit`. This is a crucial difference from advice element order inside the **same** XML `<aop:aspect>`.

## 6. Runnable Example: Two Configurations, Same Precedence Order

The **Java 17+, Spring Framework 6.2.x, Gradle** example below has two independent run modes:

- `xml`: registers two aspects via `<aop:config>` and `<aop:aspect order>`.
- `annotation`: registers two `@Aspect` classes via `@EnableAspectJAutoProxy` and `@Order`.

They use the **same** `BillingService` but construct **two separate ApplicationContexts** for a fair comparison without registering the same advice twice. Spring AOP executes through proxies in both modes.

Project structure:

```text
spring-aop-order-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/
    │   ├── Main.java
    │   ├── BillingService.java
    │   ├── XmlAuditAspect.java
    │   ├── XmlMetricsAspect.java
    │   ├── AnnotationAuditAspect.java
    │   ├── AnnotationMetricsAspect.java
    │   └── AnnotationConfig.java
    └── resources/aop.xml
```

### 6.1. Gradle and Service

**`settings.gradle`**

```groovy
rootProject.name = 'spring-aop-order-demo'
```

**`build.gradle`**

```groovy
plugins {
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
    implementation 'org.springframework:spring-context:6.2.13'
    implementation 'org.springframework:spring-aop:6.2.13'
    implementation 'org.aspectj:aspectjweaver:1.9.24'
}

application {
    mainClass = 'demo.Main'
}
```

`spring-context` provides the container, `spring-aop` provides AOP proxies, and `aspectjweaver` provides what Spring needs to parse AspectJ pointcuts/annotation aspects. Having `aspectjweaver` on the classpath **does not mean** this example enables load-time weaving: both modes configure **Spring AOP proxies**.

**`src/main/java/demo/BillingService.java`**

```java
package demo;

public class BillingService {
    public void pay() {
        System.out.println("PAY");
    }
}
```

### 6.2. Backing Beans for XML Aspects

**`src/main/java/demo/XmlAuditAspect.java`**

```java
package demo;

import org.aspectj.lang.ProceedingJoinPoint;

public class XmlAuditAspect {
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("AUDIT enter");
        try {
            return pjp.proceed();
        } finally {
            System.out.println("AUDIT exit");
        }
    }
}
```

**`src/main/java/demo/XmlMetricsAspect.java`**

```java
package demo;

import org.aspectj.lang.ProceedingJoinPoint;

public class XmlMetricsAspect {
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("METRICS enter");
        try {
            return pjp.proceed();
        } finally {
            System.out.println("METRICS exit");
        }
    }
}
```

These classes have no `@Aspect`. XML supplies the pointcut, advice method, and order.

**`src/main/resources/aop.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:aop="http://www.springframework.org/schema/aop"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/aop
           https://www.springframework.org/schema/aop/spring-aop.xsd">

    <bean id="billingService" class="demo.BillingService"/>
    <bean id="auditBean" class="demo.XmlAuditAspect"/>
    <bean id="metricsBean" class="demo.XmlMetricsAspect"/>

    <aop:config proxy-target-class="true">
        <aop:pointcut id="payment"
                      expression="execution(* demo.BillingService.pay(..))"/>

        <aop:aspect id="audit" ref="auditBean" order="1">
            <aop:around method="around" pointcut-ref="payment"/>
        </aop:aspect>

        <aop:aspect id="metrics" ref="metricsBean" order="2">
            <aop:around method="around" pointcut-ref="payment"/>
        </aop:aspect>
    </aop:config>
</beans>
```

### 6.3. Two Equivalent Annotation Aspects

**`src/main/java/demo/AnnotationAuditAspect.java`**

```java
package demo;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;

@Aspect
@Order(1)
public class AnnotationAuditAspect {
    @Around("execution(* demo.BillingService.pay(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("AUDIT enter");
        try {
            return pjp.proceed();
        } finally {
            System.out.println("AUDIT exit");
        }
    }
}
```

**`src/main/java/demo/AnnotationMetricsAspect.java`**

```java
package demo;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;

@Aspect
@Order(2)
public class AnnotationMetricsAspect {
    @Around("execution(* demo.BillingService.pay(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("METRICS enter");
        try {
            return pjp.proceed();
        } finally {
            System.out.println("METRICS exit");
        }
    }
}
```

**`src/main/java/demo/AnnotationConfig.java`**

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AnnotationConfig {
    @Bean
    public BillingService billingService() {
        return new BillingService();
    }

    @Bean
    public AnnotationAuditAspect annotationAuditAspect() {
        return new AnnotationAuditAspect();
    }

    @Bean
    public AnnotationMetricsAspect annotationMetricsAspect() {
        return new AnnotationMetricsAspect();
    }
}
```

`@EnableAspectJAutoProxy` enables Spring AOP for this annotation context; `@Bean` makes each aspect a Spring-managed bean. Declaring `@Aspect` on a class alone does not register a bean with the container.

### 6.4. Selecting Run Mode

**`src/main/java/demo/Main.java`**

```java
package demo;

import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.support.ClassPathXmlApplicationContext;

public class Main {
    public static void main(String[] args) {
        String mode = args.length == 0 ? "xml" : args[0];
        if (!mode.equals("xml") && !mode.equals("annotation")) {
            throw new IllegalArgumentException(
                    "mode must be xml or annotation");
        }

        ConfigurableApplicationContext context =
                mode.equals("xml")
                        ? new ClassPathXmlApplicationContext("aop.xml")
                        : new AnnotationConfigApplicationContext(
                                AnnotationConfig.class);

        try (context) {
            context.getBean(BillingService.class).pay();
        }
    }
}
```

Run using the Gradle Wrapper included in the project:

```bash
./gradlew run --args=xml
./gradlew run --args=annotation
```

On Windows, replace `./gradlew` with `.\gradlew.bat`. If initializing a new directory without a wrapper, generate `gradlew`/`gradlew.bat` using a compatible Gradle version or use `gradle run --args=xml` and `gradle run --args=annotation` when Gradle is installed.

**Both modes print the exact same application lines, in order:**

```text
AUDIT enter
METRICS enter
PAY
METRICS exit
AUDIT exit
```

Gradle may print additional task/build info outside the stdout above. Swapping `order` between XML `audit`/`metrics` from 1/2 to 2/1 (or changing `@Order` accordingly in annotation mode) swaps the outer aspect; expected stdout then becomes:

```text
METRICS enter
AUDIT enter
PAY
AUDIT exit
METRICS exit
```

This is a useful verification: **`order` determines the outer wrapping layer**, while the log order on the return path reverses due to the nature of `around` advice.

## 7. Practical Rules When Combining XML, Annotations, and Advisors

When mixing XML with `@Aspect`, transactions, or framework-created advisors, identify **all applicable advisors** before reasoning about order. Equal order values do not create a stable contract; `@Order` on an aspect does not order two same-type advices inside that same class. Changing bean creation order or the placement of distinct `<aop:aspect>` elements also does not override declared precedence values.

If retry, transaction, and audit have different orders, commit boundaries, target execution counts, and audit events can differ; use integration tests against a real Spring proxy. During migration, keep the expected set of advisors unchanged and verify event traces before and after; the lesson **"Combining XML with Java configuration without creating duplicate behavior"** analyzes sources of duplicate registrations.

## 8. Checklist for Verifying Advice Order in Spring Applications

1. Do the advices being compared actually match the same method execution passing through a Spring proxy?
2. Do they belong to **two different aspects**, the **same XML `<aop:aspect>`**, or the **same `@Aspect` class**?
3. If in different aspects, have **distinct, explicit** `order`/`@Order`/`Ordered` values been set?
4. If in the same XML aspect, have you checked **advice element declaration order** and advice types?
5. If in the same `@Aspect` class, are you accidentally relying on source code order of two same-type advices?
6. If using `@Around`, are you looking at entry logs or exit logs? Do `proceed()` and `finally` reverse the observed order?
7. Are there `<aop:advisor>`, transaction advisors, or security advisors also applying without checking their separate order?
8. Is the aspect registered twice via XML, `@Bean`, or component scanning?
9. Have you tested the order via stdout or integration tests calling **through the proxy** instead of directly on a `new`ed object?

## 9. Key Takeaways and Spring Documentation

| Configuration Level | How Precedence Is Controlled | Can You Rely on Declaration Line Order? |
|---|---|---|
| Two XML `<aop:aspect>` elements | `order` attribute on each aspect (or ordering mechanism on backing bean) | Do not use XML line order instead of `order` |
| Two advices **within the same** `<aop:aspect>` | Top-to-bottom order of advice elements and semantics of each advice type | **Yes**, this is a specific rule of Spring XML schema AOP |
| Two `@Aspect` classes | `@Order` on the aspect or `Ordered` | Do not rely on class or method position in source |
| Multiple advice methods **within the same** `@Aspect` | Advice type rules; same-type order is undefined | **No**; swapping two same-type methods creates no contract |
| `<aop:advisor>` | `order` attribute on the advisor | Do not rely on XML line position without explicit precedence |

Spring Framework references:

- [Schema-based AOP Support – Advice Ordering](https://docs.spring.io/spring-framework/reference/core/aop/schema.html#advice-ordering)
- [Declaring Advice – Advice Ordering for @Aspect](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html#advice-ordering)

**Spring Aspect configuration conclusion:** use `order`/`@Order` to specify precedence **between aspects**. Inside the **same XML `<aop:aspect>`**, advice element order matters; inside the **same Java `@Aspect`**, do not use method declaration order to force two same-type advices to run in a specific sequence.