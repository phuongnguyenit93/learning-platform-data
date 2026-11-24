# Spring AOP XML: `aop:before`, `aop:after-returning`, `aop:after-throwing`, `aop:after`, and `aop:around`

## 1. Purpose and Scope

Spring Framework provides **schema-based Spring AOP** for projects that prefer declaring pointcuts and advice **in XML** rather than placing `@Aspect`, `@Before`, and `@Around` annotations directly on Java classes.

The five key advice elements in the `aop` namespace are:

- `<aop:before>`: runs before the method execution selected by the pointcut.
- `<aop:after-returning>`: runs after the method execution **returns normally**.
- `<aop:after-throwing>`: runs when the method execution **exits by throwing a matching exception**.
- `<aop:after>`: **after finally** semantics, running when the method execution exits either way.
- `<aop:around>`: surrounds the invocation, allowed to call `ProceedingJoinPoint.proceed()`, return a result, or rethrow an error.

All of these are **Spring Aspect mechanisms in Spring AOP**: they intercept method executions on **Spring-managed proxies**, not full AspectJ bytecode weaving.

Unlike the `@Aspect` approach:

```java
@Aspect
public class MyAspect {
    @Before("execution(* com.example.service.*.*(..))")
    public void before() { }
}
```

in XML style, the class holds **ordinary Java methods**, without needing `@Aspect` or `@Before`. Spring reads the XML configuration, references the Java object via the `ref` attribute, and turns the corresponding methods into advice:

```xml
<aop:aspect ref="auditAdvice">
    <aop:before pointcut-ref="businessOperation" method="before"/>
</aop:aspect>
```

The two snippets above are **fragments**, not two configurations meant to be enabled simultaneously. This lesson explores declaring the five advice types, XML/Java binding, return/exception binding, ordering, runtime output, configuration errors, and Spring proxy limitations.

## 2. Architecture of XML AOP Elements

Spring XML schema connects a **target bean**, an **advice POJO bean**, and a **pointcut** through `<aop:config>`:

~~~xml
<bean id="paymentService" class="com.example.xmlaop.PaymentService"/>
<bean id="auditAdvice" class="com.example.xmlaop.AuditAdvice"/>
<aop:config>
    <aop:pointcut id="paymentOperation"
                  expression="execution(* com.example.xmlaop.PaymentService.pay(..))"/>
    <aop:aspect ref="auditAdvice">
        <aop:before method="before" pointcut-ref="paymentOperation"/>
    </aop:aspect>
</aop:config>
~~~

This is a fragment: the backing bean must have a `before` method. XML does not require the Java class containing advice to carry `@Aspect`. Inside `aop:config`, maintain the XSD order **pointcut → advisor → aspect**; inside the **same** `aop:aspect`, the declaration order of advice elements affects precedence (Section 8).

`pointcut-ref` only selects the target method execution; `method` is the Java advice callback name; `ref` on `aop:aspect` is a bean ID. Use inline `pointcut` instead of `pointcut-ref` if the expression is only needed once. These tags do not remove Spring AOP's proxy limitations.

## 3. `<aop:before>` — Running Before the Invocation

Before advice runs prior to the selected method execution. It suits lightweight logging, invocation counting, validating preconditions that may block via an exception, or setting required metadata before entering the target.

XML:

```xml
<aop:before
    pointcut-ref="paymentOperation"
    method="before"/>
```

Java backing method:

```java
public void before() {
    System.out.println("[BEFORE]");
}
```

These are fragments of the Java advice bean and XML aspect. Spring invokes `before()` on a match. If `before()` throws an exception, the target may **not execute** because execution is aborted before proceeding.

**Limitation:** `before()` has no `ProceedingJoinPoint` to control how many times the target runs, and cannot return a replacement method result. If you only need to run logic before the method, `before` is simpler and safer than `around`.

To inspect method name or arguments, Spring XML advice can accept `JoinPoint` as its first parameter:

```java
public void before(org.aspectj.lang.JoinPoint jp) {
    System.out.println("method=" + jp.getSignature().getName());
}
```

This is a fragment. Do not cache a raw `JoinPoint` in a mutable singleton advice bean field shared across requests; each invocation has its own metadata.

## 4. `<aop:after-returning>` — Only on Normal Return

After-returning advice runs when the method execution **does not throw an exception out** and returns normally. It does not run on the corresponding exception path.

XML without binding the return value:

```xml
<aop:after-returning
    pointcut-ref="paymentOperation"
    method="returned"/>
```

Java:

```java
public void returned() {
    System.out.println("[RETURNED]");
}
```

To receive the return value, add the `returning` attribute:

```xml
<aop:after-returning
    pointcut-ref="paymentOperation"
    method="returnedValue"
    returning="result"
    arg-names="result"/>
```

Java:

```java
public void returnedValue(Object result) {
    System.out.println("[RETURNED] result=" + result);
}
```

These fragments should not be used simultaneously with both methods unless you intentionally want **two return advices**. `returning="result"` is a **binding identifier** that must map to a Java advice parameter. `arg-names="result"` declares the name explicitly, avoiding reliance on compiler metadata or parameter name inference. The Java parameter type can **restrict which return values match/bind**; use a type compatible with the target method.

### 4.1. Distinguishing Return Value from Final Outcome

Service example:

```java
public CompletableFuture<String> start() {
    return new CompletableFuture<>();
}
```

`<aop:after-returning>` can run as soon as the method returns a **pending Future**. It **does not prove the async task finished**; a Future may still complete exceptionally later.

Similarly, a method returning `Mono` or `Flux` returns a **Publisher** before subscription. `after-returning` observes the Java method returning the Publisher, not reactive `onComplete`/`onError`.

To observe async completion, use `CompletionStage.whenComplete` or appropriate Reactor operators rather than inferring it from the XML advice lifecycle.

### 4.2. Do Not Replace the Return Result by Reassigning a Local Variable

```java
public void returnedValue(Object result) {
    result = "different";  // Only assigns the local variable.
}
```

This is an anti-pattern fragment: the caller **does not receive** the new string. To alter the result returned to the caller, use `around` and return a contract-compatible replacement, or design the transformation inside the service.

## 5. `<aop:after-throwing>` — Only When Invocation Exits via Exception

After-throwing advice runs when the method execution fails and exits via an exception. To bind the exception, use the `throwing` attribute:

```xml
<aop:after-throwing
    pointcut-ref="paymentOperation"
    method="thrown"
    throwing="error"
    arg-names="error"/>
```

Backing method:

```java
public void thrown(Throwable error) {
    System.out.println("[THROW] "
            + error.getClass().getSimpleName());
}
```

`throwing="error"` maps the observed exception to the Java parameter named `error`. If the Java type is `IllegalArgumentException`, the advice applies only to exceptions compatible with that type per Spring type restrictions; `Throwable` is broader.

**Do not assume `after-throwing` swallows errors or recovers results.** After the advice logs, the exception normally continues to propagate. For retries, fallbacks, or exception translation, use `around` in a controlled manner; do not use after-throwing to silently alter control flow.

### 5.1. Which Errors Are Observed?

| Scenario | Does `after-throwing` observe the method? |
| --- | --- |
| Target method throws `IllegalStateException`, error propagates out | Yes, if pointcut/type matches |
| Target method returns normally | No |
| Method returns a pending `CompletableFuture`, Future fails after return | Does not automatically run on future completion |
| Method returns `Mono.error(ex)` normally, error emitted later on subscribe | Does not automatically run merely on reactive `onError` |
| Method throws while building the Publisher before returning | Yes, if the error escapes the invocation |
| Inner advice catches an error and returns a fallback, outer advice sees normal return | Depends on advisor chain position; error may not cross the observed boundary |

In the demo project below, `PaymentService.pay("fail")` throws `IllegalStateException` **synchronously**, so `<aop:after-throwing>` triggers as expected.

## 6. `<aop:after>` — After Finally, Not Only After Success

`<aop:after>` has **finally semantics**:

```xml
<aop:after
    pointcut-ref="paymentOperation"
    method="afterFinally"/>
```

Java:

```java
public void afterFinally() {
    System.out.println("[FINALLY]");
}
```

It runs when a method invocation exits via **normal return or exception**, making it suitable for releasing resources or clearing state tied to the invocation's lifecycle.

**Do not confuse** `after` with `after-returning`:

| Situation | `after-returning` | `after-throwing` | `after` |
| --- | --- | --- | --- |
| Normal return | Yes | No | Yes |
| Propagated exception | No | Yes if type matches | Yes |
| Method not called due to outer `around` short-circuit | Inner advice/target do not run, so inner advices usually do not fire | Same | Same |
| Future returned normally but fails later | Already ran at method return | Does not run on future late failure | Already ran at method return |

**Exceptions from another advice:** what gets observed also depends on precedence/chain; do not assume every advice always wraps the target directly without other advisors. When cleanup must preserve the original error, design cleanup logic so it does not accidentally throw a new error masking the root cause.

## 7. `<aop:around>` — Controlling `proceed()`, Return, and Throw

Around advice wraps the method execution. It can log before/after the target, return a fallback, short-circuit the call, or retry according to policy. It is the most powerful advice type, so use it only when `before/after` is insufficient.

XML:

```xml
<aop:around
    pointcut-ref="paymentOperation"
    method="around"/>
```

Java:

```java
public Object around(ProceedingJoinPoint pjp) throws Throwable {
    System.out.println("[AROUND] enter");
    try {
        Object result = pjp.proceed();
        System.out.println("[AROUND] return");
        return result;
    } catch (Throwable error) {
        System.out.println("[AROUND] throw");
        throw error;
    }
}
```

This is a method fragment for a backing aspect bean. An around advice method **must** accept `ProceedingJoinPoint` as its **first parameter**, typically return `Object`, and declare `throws Throwable` because `proceed()` can throw `Throwable`.

### 7.1. `proceed()` Is Not Automatic

`pjp.proceed()` forwards the invocation to the rest of the interceptor chain. If you do not call `proceed()`, the target may **not execute** and the caller only receives whatever value the around advice returns (if the return type is valid).

```java
public Object around(ProceedingJoinPoint pjp) throws Throwable {
    if (cacheHit()) {
        return cachedValue();
    }
    return pjp.proceed();
}
```

This is a fragment illustrating a cache short-circuit, requiring two helpers with clear cache contracts. Do not use this short-circuit pattern on methods with side effects unless the cache policy guarantees equivalence.

### 7.2. Calling `proceed()` Multiple Times

In Spring AOP, around advice may call `proceed()` 0, 1, or multiple times. Multiple calls can implement retries, but also **repeat the target and downstream advices, repeating side effects**:

```java
public Object retry(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } catch (TemporaryFailure ex) {
        return pjp.proceed();
    }
}
```

This is a fragment requiring an application-defined `TemporaryFailure`. Retries must have limits, transient error classification, idempotency/transaction boundaries, and observability. Do not call `proceed()` again to "probe" a target that charges money, sends emails, or publishes events if the operation is not safe to repeat.

### 7.3. `proceed(Object[] arguments)`

In proxy-based Spring AOP, the `proceed(Object[])` overload passes replacement arguments forward; the array must match the **number and types of the underlying Java method arguments**:

```java
Object[] args = pjp.getArgs().clone();
args[0] = normalize((String) args[0]);
return pjp.proceed(args);
```

This is a fragment requiring `normalize`. Do not assume merely reassigning a local Java parameter in advice makes the caller/target receive the new argument; you must pass `args` to `proceed(args)`.

### 7.4. Safe Timing in Around Advice

```java
public Object around(ProceedingJoinPoint pjp) throws Throwable {
    long started = System.nanoTime();
    try {
        return pjp.proceed();
    } finally {
        long elapsed = System.nanoTime() - started;
        metrics.record(elapsed);
    }
}
```

This is a fragment. `started` is a **local variable**, avoiding races when the backing advice bean uses singleton scope. If the target returns a Future/Publisher, the duration above only measures **the Java method invocation**, not eventual async/reactive completion.

## 8. Advice Order Within the **Same** XML `<aop:aspect>`

This is the easiest difference to get wrong when switching between XML and `@AspectJ` annotation style.

**Spring XML schema AOP rule: when multiple advice elements inside the same `<aop:aspect>` match the same join point, precedence from highest to lowest is determined by the declaration order of the advice elements in XML.**

Example:

```xml
<aop:aspect ref="auditAdvice">
    <!-- Highest precedence in this XML aspect -->
    <aop:around method="around" pointcut-ref="paymentOperation"/>
    <aop:before method="before" pointcut-ref="paymentOperation"/>
    <aop:after method="afterFinally" pointcut-ref="paymentOperation"/>
    <aop:after-returning method="returnedValue"
        returning="result" arg-names="result"
        pointcut-ref="paymentOperation"/>
    <aop:after-throwing method="thrown"
        throwing="error" arg-names="error"
        pointcut-ref="paymentOperation"/>
</aop:aspect>
```

With the XML sequence above, `around` is the outer advice; `before` runs on the way in; `after` has higher precedence than the return/throw advice placed after it, so following nested `finally` semantics it runs **after** `after-returning` or `after-throwing` on the way out.

Compare on a normal return:

```text
[AROUND] enter
[BEFORE]
[TARGET] execute
[RETURNED] result=...
[FINALLY]
[AROUND] return
```

With an exception:

```text
[AROUND] enter
[BEFORE]
[TARGET] throws exception
[THROW] IllegalStateException
[FINALLY]
[AROUND] throw
```

If you change the order of the XML advice elements, precedence/relative execution can change. **Do not reorder tags arbitrarily just to group them alphabetically**, especially when around/after/throwing are used together.

### 8.1. Do Not Apply the XML Rule to Annotation-Style `@Aspect`

In a Java `@Aspect` class with two matching `@Before` advice methods, Spring **does not guarantee** ordering based on the declaration position of the two Java methods. Java reflection does not provide source declaration order as a contract. Spring annotation style has its own ordering rules by advice type and `@After` finally semantics.

**Specifically for XML `<aop:aspect>`**, Spring docs explicitly specify that the declaration order of **advice elements** determines precedence within the same aspect. This is an intentional exception, not a contradiction.

### 8.2. Between **Multiple Aspects**, Use `order`

```xml
<aop:aspect ref="securityAdvice" order="1">
    <aop:before method="check" pointcut-ref="paymentOperation"/>
</aop:aspect>

<aop:aspect ref="auditAdvice" order="10">
    <aop:around method="around" pointcut-ref="paymentOperation"/>
</aop:aspect>
```

This is a fragment; the `securityAdvice`/`auditAdvice` beans and pointcut must exist. An aspect with a **smaller order value** has **higher precedence**. High-precedence advice runs earlier on entry and later on exit.

You can use `@Order` on the backing bean or implement `Ordered` per Spring conventions, but avoid mixing mechanisms with conflicting values and guessing the final order. `<aop:advisor>` also has an `order` attribute, affecting the chain when combining transaction/caching/security advisors.

**Recommendation:** If an `<aop:aspect>` has too many advice elements on the same join point making order hard to reason about, consider consolidating logic into one clear advice method or splitting into multiple aspects with explicit `order`.

## 9. Parameter Binding in XML: `returning`, `throwing`, and `arg-names`

Several concepts have distinct roles:

| XML attribute | Example | Meaning |
| --- | --- | --- |
| `method` | `method="returnedValue"` | Java method name on the backing advice bean |
| `pointcut` | `pointcut="execution(...)"` | Expression selecting method executions |
| `pointcut-ref` | `pointcut-ref="paymentOperation"` | Uses a declared named pointcut |
| `returning` | `returning="result"` | Binds **normal return value** to parameter |
| `throwing` | `throwing="error"` | Binds **thrown exception** to parameter |
| `arg-names` | `arg-names="result"` | Maps formal parameter names explicitly |
| `ref` on `<aop:aspect>` | `ref="auditAdvice"` | Bean containing Java advice methods |
| `order` on `<aop:aspect>` | `order="10"` | Precedence across aspects |

### 9.1. Binding Java Method Arguments

XML:

```xml
<aop:before
    method="beforeWithArgument"
    pointcut="execution(* com.example.xmlaop.PaymentService.pay(..)) and args(reference)"
    arg-names="reference"/>
```

Java:

```java
public void beforeWithArgument(String reference) {
    System.out.println("reference=" + reference);
}
```

Both fragments use `args(reference)` as a **binding identifier**; it is not a parameter name "auto-read" from the target method. `args` matches the **argument position and type**, then passes the value into the Java advice method.

If the Java advice has a leading `JoinPoint`, Spring has a special rule allowing you to omit the leading join point's name from `arg-names`. For around advice, a leading `ProceedingJoinPoint` is handled similarly. Avoid overloading Java advice methods with the same name, which makes matching/binding unpredictable.

### 9.2. Return Type / Exception Type as a Binding Filter

`returnedValue(String result)` matches only return values that Spring can bind to `String`. `thrown(IllegalStateException error)` observes that exception type; `thrown(Throwable error)` is broader. Avoid overly restrictive types that accidentally drop exceptions/results needing logging.

`returning` and `throwing` are **not** ways to replace results/exceptions by reassigning advice parameters. If transformation is genuinely needed, use around advice with a clear behavior contract.

### 9.3. Parameter Names and Compiler

`arg-names` in XML corresponds in intent to `argNames` in annotation style, avoiding dependence on Java `-parameters` and parameter name discovery. Even so, Java parameter **order, count, and types** must still match. When adding/removing parameters, update both the XML declaration and the Java method signature, then test context startup.

## 10. Runnable Example: Maven + Java 17 + Spring Framework XML AOP

This project demonstrates **all five advice types inside the same `<aop:aspect>`**, with XML order intentionally chosen to produce deterministic stdout.

Pinned versions: Java 17+, Spring Framework 6.1.14, AspectJ Weaver 1.9.22.1, Maven. These are illustrative versions, **not claiming to be the latest**. Spring Boot and AspectJ weaving are omitted to keep focus on schema-based Spring AOP.

### 10.1. Directory Structure

```text
spring-xml-five-advices/
├── pom.xml
└── src/main/
    ├── java/com/example/xmlaop/
    │   ├── PaymentService.java
    │   ├── AuditAdvice.java
    │   └── DemoApp.java
    └── resources/
        └── applicationContext.xml
```

### 10.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-xml-five-advices</artifactId>
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

Spring `spring-context` pulls in `spring-aop` and related dependencies via the dependency tree for the example; `aspectjweaver` supports the pointcut expression parser. There is no need to add `@Aspect` to the Java advice POJO.

### 10.3. `src/main/java/com/example/xmlaop/PaymentService.java`

```java
package com.example.xmlaop;

public class PaymentService {
    public String pay(String mode) {
        System.out.println("[TARGET] pay " + mode);

        if ("fail".equals(mode)) {
            throw new IllegalStateException("simulated");
        }
        return "paid:" + mode;
    }

    public String health() {
        System.out.println("[TARGET] health");
        return "UP";
    }
}
```

`pay("ok")` returns normally; `pay("fail")` throws synchronously; `health()` proves **the pointcut targets only pay()**, not every method on the bean.

### 10.4. `src/main/java/com/example/xmlaop/AuditAdvice.java`

```java
package com.example.xmlaop;

import org.aspectj.lang.ProceedingJoinPoint;

public class AuditAdvice {

    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("[AROUND] enter");
        try {
            Object result = pjp.proceed();
            System.out.println("[AROUND] normal exit");
            return result;
        } catch (Throwable ex) {
            System.out.println("[AROUND] exceptional exit");
            throw ex;
        }
    }

    public void before() {
        System.out.println("[BEFORE]");
    }

    public void afterFinally() {
        System.out.println("[FINALLY]");
    }

    public void returnedValue(Object result) {
        System.out.println("[RETURNED] result=" + result);
    }

    public void thrown(Throwable error) {
        System.out.println("[THROW] "
                + error.getClass().getSimpleName());
    }
}
```

This is a **plain Java POJO**. No `@Aspect` or `@Around` annotations. Spring XML selects each method via the `method` attribute.

`around(ProceedingJoinPoint)` uses a local variable to hold the result/exception; `afterFinally()` takes no parameters. `returnedValue(Object result)` and `thrown(Throwable error)` receive bindings through XML `returning`/`throwing`. Both success and exception paths are handled without **swallowing exceptions**.

### 10.5. `src/main/resources/applicationContext.xml`

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

    <!-- Spring-managed target -->
    <bean id="paymentService"
          class="com.example.xmlaop.PaymentService"/>

    <!-- Backing advice POJO: no @Aspect needed -->
    <bean id="auditAdvice"
          class="com.example.xmlaop.AuditAdvice"/>

    <aop:config proxy-target-class="true">
        <!-- Narrow pointcut, selecting only pay(String) -->
        <aop:pointcut
            id="paymentOperation"
            expression="execution(public * com.example.xmlaop.PaymentService.pay(..))"/>

        <aop:aspect id="paymentAudit" ref="auditAdvice">
            <!-- Highest to lowest precedence, XML declaration order -->
            <aop:around
                method="around"
                pointcut-ref="paymentOperation"/>
            <aop:before
                method="before"
                pointcut-ref="paymentOperation"/>
            <aop:after
                method="afterFinally"
                pointcut-ref="paymentOperation"/>
            <aop:after-returning
                method="returnedValue"
                returning="result"
                arg-names="result"
                pointcut-ref="paymentOperation"/>
            <aop:after-throwing
                method="thrown"
                throwing="error"
                arg-names="error"
                pointcut-ref="paymentOperation"/>
        </aop:aspect>
    </aop:config>
</beans>
```

**Why this XML order was chosen:** `aop:around` is outermost; `aop:before` runs before the target; `aop:after` has higher precedence than the after-returning/after-throwing elements declared after it, so cleanup/finally during unwind occurs after them. Child XML tag positions are **not a simple chronological order**, because there is both an entry path and an exit path.

`proxy-target-class="true"` chooses a class-based CGLIB proxy, allowing `PaymentService` (which implements no interface) to still be retrieved as a concrete class from the context. Regardless of proxy style, the Java advice bean remains a POJO.

### 10.6. `src/main/java/com/example/xmlaop/DemoApp.java`

```java
package com.example.xmlaop;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.support.ClassPathXmlApplicationContext;

public class DemoApp {
    public static void main(String[] args) {
        try (ClassPathXmlApplicationContext context =
                 new ClassPathXmlApplicationContext("applicationContext.xml")) {

            PaymentService service =
                    context.getBean("paymentService", PaymentService.class);

            System.out.println("isAopProxy="
                    + AopUtils.isAopProxy(service));

            System.out.println("[CALLER] success");
            String success = service.pay("ok");
            System.out.println("[CALLER] result=" + success);

            System.out.println("[CALLER] failure");
            try {
                service.pay("fail");
            } catch (IllegalStateException ex) {
                System.out.println("[CALLER] caught="
                        + ex.getMessage());
            }

            System.out.println("[CALLER] health");
            System.out.println("[CALLER] result=" + service.health());
        }
    }
}
```

The caller retrieves the Spring bean from the XML context so calls to `pay` pass **through the Spring proxy**, unlike `new PaymentService().pay(...)` outside the container.

### 10.7. Running Maven

From the root directory containing `pom.xml` with JDK 17+:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.xmlaop.DemoApp
```

Lines printed by the program itself, according to the demo source and XML declarations, **excluding additional Maven/Spring logs depending on environment**:

```text
isAopProxy=true
[CALLER] success
[AROUND] enter
[BEFORE]
[TARGET] pay ok
[RETURNED] result=paid:ok
[FINALLY]
[AROUND] normal exit
[CALLER] result=paid:ok
[CALLER] failure
[AROUND] enter
[BEFORE]
[TARGET] pay fail
[THROW] IllegalStateException
[FINALLY]
[AROUND] exceptional exit
[CALLER] caught=simulated
[CALLER] health
[TARGET] health
[CALLER] result=UP
```

### 10.8. Why This Execution Order?

**Success path:**

1. Spring AOP proxy matches `paymentOperation` for `pay("ok")`.
2. XML around element has highest precedence so it prints `[AROUND] enter`.
3. `pjp.proceed()` forwards to the before element, printing `[BEFORE]`.
4. Target runs, prints `[TARGET] pay ok`, and returns the string.
5. Return advice receives `result="paid:ok"` and prints `[RETURNED]`.
6. Finally advice prints `[FINALLY]`.
7. Around receives the result from `proceed()`, prints `normal exit`, and returns the exact string to the caller.

**Failure path:**

1. Around prints `enter`; before prints `[BEFORE]`; target prints `[TARGET] pay fail`.
2. Target throws `IllegalStateException`; there is no normal return so `after-returning` does not run.
3. After-throwing binds `Throwable error` and prints the exception type name.
4. After-finally still runs.
5. The error propagates to the outer around's catch block, is logged, and is rethrown to the caller.
6. Caller catches it and prints the message `simulated`.

**Unmatched method:** `health()` does not match `execution(...pay(..))`, so no advice logs appear when `health()` runs.

Stdout represents **expected output from static code inspection**. When running the project on a real machine, verify with Maven/integration tests matching the exact Spring version and config; do not treat this output as a guarantee for applications with extra advisors or different ordering.

## 11. Notes When XML Advice Coexists with Infrastructure Advisors

In an application with transactions, caching, security, or other XML/`@Aspect` advice, **the advisor's position in the chain** affects what is observed. For example, a logging advisor inside a transaction interceptor may log success before the outermost transaction commits; `after-returning` does not prove commit succeeded.

If an outer `around` catches an error and returns a fallback, an outer after-returning may see a normal return; if `proceed()` repeats multiple times, downstream targets/advices may also run multiple times. Therefore define `order`, transaction boundaries, retry idempotency, and assert event traces on a real context. The lesson **"Combining XML with Java configuration..."** specifically examines the risk of duplicate advisor and bean registration.

## 12. Spring Proxy Boundaries Still Exist Despite Using XML

Even with XML, Spring AOP still handles **method executions on Spring-managed beans through proxies**. `this.method()` inside a target and `new Target()` outside the container do not trigger a fresh proxy interception. With JDK proxies, callers use interfaces; with class proxies, final/private targets cannot be overridden; Future/Publisher completion happens outside the moment the Java method returns.

These limitations affect all five advice types. The lesson **"proxy-target-class and expose-proxy in XML configuration"** gives specific experiments measuring proxy types, self-invocation, and `AopContext.currentProxy()`.

## 13. When Is XML AOP Appropriate?

XML configuration is valuable in projects that:

- Use XML bean definitions and want to attach advice to POJOs **without modifying Java classes**.
- Have legacy aspects that already keep plain methods.
- Want to toggle pointcuts/advice bindings under controlled configuration management.
- Are migrating between schema-based XML AOP and `@AspectJ` annotations.

Advantages include separating configuration from Java source and not requiring advice beans to carry AspectJ annotations. In return, Java method names in XML strings **are not directly type-checked by the Java compiler**; refactoring method/package names requires updating XML and integration tests. The more advice elements share a join point, the harder declaration order is to maintain.

### Comparison with Annotation Style

| Intent | Spring XML AOP | Spring `@AspectJ` style |
| --- | --- | --- |
| Aspect source | Backing Java POJO + `<aop:aspect ref=...>` | Spring-managed Java `@Aspect` class |
| Before | `<aop:before>` | `@Before` |
| After returning | `<aop:after-returning>` | `@AfterReturning` |
| After throwing | `<aop:after-throwing>` | `@AfterThrowing` |
| After finally | `<aop:after>` | `@After` |
| Around | `<aop:around>` | `@Around` |
| Named pointcut | `<aop:pointcut id=...>` | `@Pointcut` |
| Explicit parameter names | XML `arg-names` | Annotation `argNames` |
| Precedence between aspects | XML `order` / Spring ordering | `@Order` / `Ordered` |
| Within same aspect | **XML advice element order** | Precedence by advice type; two same-type advice methods have undefined order |
| Join points | Spring proxy method execution | Spring proxy method execution |

Switching to `@Aspect` **does not** allow Spring AOP to intercept private methods, constructors, or field get/set; proxy boundaries remain unchanged.

## 14. Common Errors When Using the Five XML Advice Tags

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Context load fails because `aop` namespace is unknown | Missing `xmlns:aop`/schemaLocation `spring-aop.xsd` | Declare the proper namespace and XSD |
| XML parsing error on `&&` | Unescaped `&` in attribute | Use `&amp;&amp;` or `and` appropriately |
| `ref="auditAdvice"` fails to resolve | Backing advice bean not registered or wrong ID | Define `<bean id="auditAdvice" .../>` |
| `method="returnedValue"` not found | Wrong Java method name/signature | Align XML with the backing Java bean |
| `pointcut-ref` fails to resolve | Wrong/missing named pointcut ID | Declare matching `<aop:pointcut id=...>` |
| `after-returning` does not run on exception | Applies only to normal return | Use `after-throwing` for exceptions |
| `after-throwing` does not run even though Future fails later | Spring AOP sees normal method return | Observe Future completion separately |
| `after` runs on both success and error | That is `finally` semantics | Use properly for cleanup purposes |
| `around` prevents target from running | Forgot `pjp.proceed()` or short-circuited | Call `proceed()` when forwarding is intended |
| Caller does not receive target result | Around forgot to return the result | `return pjp.proceed()` or valid replacement |
| `returning` does not bind properly | Wrong `arg-names`/type, different method result type | Align identifiers and Java signature |
| `throwing` does not bind | Parameter name/type mismatch | Align XML `throwing`/`arg-names` and Java method |
| Log order differs from naive XML tag reading | Reading precedence as one-way chronological order | Distinguish entry vs. exit path of interceptor chain |
| Two aspects run in unclear order | Missing `order`/Spring precedence | Declare distinct `order` values |
| `health()` gets advised when only `pay()` was intended | Overly broad pointcut | Use narrow `execution` and negative tests |
| XML aspect does not run for manually `new`ed bean | Caller bypassed Spring proxy | Retrieve bean from context |
| Self-invoked method lacks advice | `this.method()` bypasses proxy | Refactor interaction across Spring beans |
| Cannot retrieve concrete class type | JDK dynamic proxy exposes only interfaces | Inject interface or switch proxy strategy |
| CGLIB does not advise `final` method | Cannot override method | Adjust contract/proxy strategy |
| Mixing XML AOP with manually configured auto-proxy creator | Proxy infrastructure conflict | Choose one consistent configuration approach |
| Stale XML references after refactoring | Compiler does not check XML strings | Run context-start/integration tests in CI |

## 15. Review and Test Checklist

Before introducing XML AOP advice into a module, verify:

1. XML `beans`, `aop` namespaces, and schema locations are valid.
2. `<aop:config>` contains valid pointcuts/advisors/aspects in proper XSD declaration order.
3. Target and backing advice Java objects are Spring beans in the proper context.
4. Pointcut expression selects the exact classes/methods, avoiding accidental matching of the entire service layer.
5. `method` points to the exact name/signature on the backing advice bean.
6. `pointcut-ref` points to the named pointcut ID, not confused with a Java method name.
7. `returning`/`throwing`/`arg-names` map accurately to Java formal parameters.
8. `around` takes `ProceedingJoinPoint` first and honors return value/exception contracts.
9. The order of **XML advice declarations inside an `<aop:aspect>`** is intentional.
10. `order` across multiple aspects/advisors is declared where ordering dependencies exist.
11. Integration tests cover normal return, exception, unmatched methods, and targets not advised when bypassing proxies.
12. If transaction/cache/security advisors exist, test chain/commit behavior in a real context.
13. Metrics use local start/actor state; do not hold `JoinPoint` in singleton fields.
14. Do not log user tokens/PII or entire disallowed result objects.
15. Do not use after-returning to infer Future/Publisher completion.
16. After XML/Java refactoring, integration tests **load XML resources from classpath** to catch broken configuration strings.

### Official Sources

- Spring Framework — **Schema-based AOP Support**, full examples of the five `aop` advice tags, parameter binding, and ordering: https://docs.spring.io/spring-framework/reference/core/aop/schema.html
- Spring Framework — **Declaring Advice** and precedence in `@AspectJ` style: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html
- Spring Framework — **Proxying Mechanisms**: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework — **AOP Concepts**: https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html
- Spring Framework — **XML Schema-based Configuration**: https://docs.spring.io/spring-framework/reference/core/appendix/xsd-schemas.html

**Conclusion:** Spring XML AOP uses `<aop:before>`, `<aop:after-returning>`, `<aop:after-throwing>`, `<aop:after>`, and `<aop:around>` to bind **plain Java advice methods** to **Spring proxy method-execution join points**. The five types preserve Spring `@AspectJ` semantics, with one key rule to remember: **within the same `<aop:aspect>`, the declaration order of advice elements determines precedence**. Designing proper `returning`/`throwing` bindings, return/throw contracts, and proxy boundaries keeps XML configuration accurate, safe, and verifiable via integration tests.