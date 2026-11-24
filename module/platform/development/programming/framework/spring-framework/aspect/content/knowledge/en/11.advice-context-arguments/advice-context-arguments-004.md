# Binding Arguments with `args` and Advice Parameters in Spring AOP

## 1. Goal: passing Spring bean call arguments into strongly typed advice parameters

When writing a Spring `@Aspect`, many advice methods need to know **which values the caller actually passed to the target method**. For example, an audit advice may want `accountId` and `channel` without manually iterating `Object[]`, casting by hand, and guessing element positions.

Spring AOP supports **argument binding** using `args(...)` in AspectJ-style pointcut expressions. When you use a **formal parameter name** rather than a Java type name inside `args`, Spring can **pass the selected argument value into the advice's parameter**.

```java
@Before(
    value = "execution(* com.example.payment.PaymentService.pay(..))"
          + " && args(accountId, amount)",
    argNames = "accountId,amount"
)
public void beforePay(String accountId, java.math.BigDecimal amount) {
    System.out.println("accountId=" + accountId);
    System.out.println("amount=" + amount);
}
```

This is a **method fragment** inside a Spring-managed `@Aspect` class, not a standalone Java program. It assumes `PaymentService.pay(String, BigDecimal)` is called by the consumer **through a Spring AOP proxy**.

Each part has its own responsibility:

- `execution(...PaymentService.pay(..))`: restricts the join point to the desired business method.
- `args(accountId, amount)`: takes **two actual arguments in order** and binds them to the variables named in the pointcut expression.
- `String accountId` and `BigDecimal amount`: the Java types Spring/AspectJ uses for binding and compatibility checks.
- `argNames="accountId,amount"`: maps the exact names appearing in the expression to the advice method's formal parameters.
- Body of `beforePay`: the actual audit logic, **not** part of the expression.

**Scope:** This lesson focuses on Spring Aspects, `@AspectJ` annotation style, and **Spring proxy-based AOP**. AspectJ concepts outside Spring are mentioned only to prevent API confusion, without expanding into compile-time/load-time weaving.

## 2. `args` has two uses: type pattern and binding

The easiest point of confusion is that `args(...)` **does not always mean the same thing**.

### 2.1. Using a Java type to select invocations

```text
args(java.io.Serializable)
```

This is a **type pattern**: it selects calls that have **exactly one argument** whose runtime type matches `Serializable`, within Spring proxy join points.

For example, if the target method declares:

```java
public String send(Object payload) { /* ... */ }
```

If `"hello"` is passed, the runtime argument is a `String` and implements `Serializable`. If `new PlainPayload()` (which does not implement that interface) is passed, the match condition differs even though the `send(Object)` signature is identical.

### 2.2. Using a parameter name to bind the value

```text
args(payload)
```

If `payload` is declared in the signature of a named pointcut or advice method, it is a **binding identifier**. For example:

```java
@Before(
    value = "execution(* com.example.msg.MessageService.send(..))"
          + " && args(payload)",
    argNames = "payload"
)
public void inspect(java.io.Serializable payload) {
    System.out.println(payload.getClass().getSimpleName());
}
```

When the runtime argument matches `Serializable`, `payload` receives **the exact argument being passed**, not a `Serializable` instance created by Spring.

**Comparison summary:**

| Syntax | Meaning | Does it bind the value to an advice parameter? |
| --- | --- | --- |
| `args(java.io.Serializable)` | Runtime type filter | No, because this is a fully qualified type name |
| `args(payload)` with `Serializable payload` | Runtime type filter **and** binding | Yes, captures the corresponding object |
| `args(payload, channel)` | Binds two arguments by position | Yes, if signature/types are compatible |
| `args(payload, ..)` | Binds first argument, allows remaining ones | Yes |
| `args(.., channel)` | Binds last argument, allows preceding ones | Yes |
| `execution(* *.send(java.io.Serializable))` | Filters parameter type **declared in the method signature** | Does not bind arguments automatically |

Spring docs emphasize that `args(java.io.Serializable)` differs from `execution(* *(java.io.Serializable))`: `args` can evaluate the **actual runtime argument**, whereas `execution` inspects the **declared method signature**. Check this before modifying a pointcut that appears "not to run".

## 3. Binding names must match in three places

A complete advice binding has three places that need to agree:

```java
@Before(
    value = "execution(* com.example.order.OrderService.create(..))"
          + " && args(request, source)",
    argNames = "request,source"
)
public void before(OrderRequest request, String source) {
    // ...
}
```

| Location | Notation | Effect |
| --- | --- | --- |
| Pointcut string | `args(request, source)` | References the binding names from the invocation |
| Advice annotation | `argNames="request,source"` | Provides explicit parameter-name mapping |
| Advice Java method | `OrderRequest request, String source` | Types and parameters that actually receive the values |

This is a **fragment**: `OrderRequest` must exist in the project. Naming `request` consistently across all three places prevents readers from having to infer via reflection.

Example of renaming **only** in Java:

```java
@Before(
    value = "execution(* com.example.order.OrderService.create(..))"
          + " && args(request, source)",
    argNames = "request,source"
)
public void before(OrderRequest payload, String channel) {}
```

Java still compiles because the annotation attributes are strings. However, `argNames` declares binding names different from the source parameters; some setups still bind by **explicit list order**, yet this easily causes confusion during refactoring. The safe practice is to **synchronize names across all three places** and run context tests. Especially if you omit `argNames`, how Spring resolves parameter names from build metadata can alter the outcome.

If the **count**, **binding order**, or **type** is wrong, or an identifier cannot be resolved, Spring usually fails when creating the advisor/starting the context, or the advice does not apply as expected. Do not treat annotation expression strings as fully type-checked by the Java compiler.

## 4. `argNames`, `-parameters`, and argument name discovery

`args(payload)` in a pointcut uses the **binding name** `payload`, not the target method's parameter name. Spring must link this name to the correct advice parameter. The most controllable way is declaring `argNames = "payload"`; Java's `-parameters` flag is another metadata source Spring uses to find parameter names when not declared explicitly. When multiple variables or annotation/return bindings exist, leaving Spring to infer names can be ambiguous.

### 4.1. Case with a leading `JoinPoint`

The special first parameter `JoinPoint`, `ProceedingJoinPoint` (for `@Around`), or `JoinPoint.StaticPart` may **have its name omitted from `argNames`**. For example:

```java
@Before(value = "execution(* com.example.payment.PaymentService.pay(..))"
        + " && args(accountId, amount)",
        argNames = "accountId,amount")
public void audit(JoinPoint jp, String accountId, BigDecimal amount) {
    System.out.println(jp.getSignature().getName() + ": " + accountId);
}
```

This is an illustrative snippet inside a Spring-managed `@Aspect`, requiring imports for `JoinPoint`, `BigDecimal`, and `@Before`; `jp` is supplied by Spring, while the other two parameters come from binding. When no other variables are bound, an advice receiving only `JoinPoint` does not need `argNames`. `getArgs()` reads a positional array of values; `args(name)` constrains typed values and participates in match conditions. The **argNames, parameter names, and `-parameters`** lesson in this chapter goes deeper into Maven/Gradle configuration and name discovery order.

## 5. Position-based `args`: one, two, or more parameters

Suppose the target method is:

```java
public Receipt charge(String accountId, BigDecimal amount, String channel);
```

Each expression below has a different meaning:

```text
args(accountId, amount, channel)
args(accountId, ..)
args(.., channel)
args(accountId, *, channel)
args(java.lang.String, java.math.BigDecimal, java.lang.String)
```

- `args(accountId, amount, channel)`: binds all **three positions**; the named pointcut/advice signature must match accordingly.
- `args(accountId, ..)`: binds the **first parameter**; zero or more arguments may follow.
- `args(.., channel)`: binds the **last parameter**; any number of positions may precede it.
- `args(accountId, *, channel)`: binds the first and last positions, with **one** arbitrary argument in between. When using wildcards with complex bindings, run context tests to verify parser/type-matching compatibility.
- `args(String, BigDecimal, String)`: checks types by position only, **without creating named bindings**.

Example caring only about the first `accountId` even if the method has additional parameters:

```java
@Before(
    value = "execution(* com.example.billing.BillingService.charge(..))"
          + " && args(accountId, ..)",
    argNames = "accountId"
)
public void beforeCharge(String accountId) {
    // ...
}
```

This is a conceptually valid method fragment: `accountId` binds to the first argument without requiring the advice to declare the remaining parameters.

**Do not confuse position with the target method's parameter name.** Callers do not pass an "argument named `accountId`"; the JVM passes an **ordered sequence of values**. The name `accountId` in the pointcut is simply a **binding name** chosen by the advice author. Renaming a parameter `id` in the target Java code does not by itself break `args(accountId,..)` as long as position and type remain valid.

### 5.1. Overloads

Given two overloads:

```java
void submit(Object payload);
void submit(String payload);
```

The Java compiler selects the overload based on the **expression type at the call site**, before Spring AOP applies any pointcut. Then `args(payload)` inspects the **runtime argument** of the chosen method execution.

If the code writes `Object value = "hello"; service.submit(value);`, Java calls the `submit(Object)` overload even though `value` points to a `String`. Advice with `args(payload)` and `String payload` can still bind the runtime `String` when that method execution goes through the appropriate proxy. It does not change the called method into the `submit(String)` overload.

## 6. Binding arguments with a named `@Pointcut`

When multiple advice methods need the same method-selection condition and formal argument types, create a named pointcut:

```java
@Pointcut(
    value = "execution(* com.example.order.OrderService.place(..))"
          + " && args(orderId, channel)",
    argNames = "orderId,channel"
)
public void orderPlaced(String orderId, String channel) {}
```

Then reference it:

```java
@Before(
    value = "orderPlaced(orderId,channel)",
    argNames = "orderId,channel"
)
public void beforeOrder(String orderId, String channel) {
    // ...
}
```

```java
@AfterReturning(
    pointcut = "orderPlaced(orderId,channel)",
    returning = "receipt",
    argNames = "orderId,channel,receipt"
)
public void afterOrder(
        String orderId, String channel, Receipt receipt) {
    // ...
}
```

These are **fragments** of an `@Aspect` class; `Receipt` and `OrderService.place(..)` must actually exist in the project. The named pointcut declares formal parameters, yet **the body of `orderPlaced(...)` is empty**: Spring does not invoke this Java body to obtain arguments. It is a metadata declaration of how values are bound.

Notice that `returning="receipt"` binds the method's **return value**, whereas `args(orderId,channel)` binds **input arguments**. Do not use the same identifier for two objects with different meanings.

### 6.1. Binding names across layers

When a pointcut lives in a shared class:

```java
@Pointcut(
    value = "execution(* com.example.order.OrderService.place(..))"
          + " && args(orderId, channel)",
    argNames = "orderId,channel"
)
public void placed(String orderId, String channel) {}
```

Another aspect can use it:

```java
@Before(
    value = "com.example.aop.CommonPointcuts.placed(orderId,channel)",
    argNames = "orderId,channel"
)
public void audit(String orderId, String channel) {}
```

A **fully-qualified class + method reference** lets Spring locate a named pointcut outside the current class. The method in `CommonPointcuts` needs appropriate Java visibility (usually `public`). `CommonPointcuts` does not need to be instantiated as a bean merely because it holds public named pointcuts referenced by name; however, the `@Aspect` class containing the advice must be a Spring bean.

## 7. Binding across different advice types

`args` is not limited to `@Before`. In Spring, advice methods can receive values from pointcut bindings, provided the matching signature/annotation is used:

| Advice | Uses `args` for input? | Additional binding | Important note |
| --- | --- | --- | --- |
| `@Before` | Yes | Can receive leading `JoinPoint` | Cannot alter the caller's argument simply by reassigning a local parameter. |
| `@After` | Yes | Can receive `JoinPoint` | Runs with after (finally) semantics, not only on success. |
| `@AfterReturning` | Yes | `returning="result"` | `result` is the return value; reassigning an advice parameter does not change what the caller receives. |
| `@AfterThrowing` | Yes | `throwing="error"` | Exception binding; runs only when the call ends with a matching error. |
| `@Around` | Yes | `ProceedingJoinPoint` as first param | Can call `proceed()` or `proceed(Object[])`; advice decides whether and when to forward. |

Example combining `args` with a return result:

```java
@AfterReturning(
    pointcut = "execution(* com.example.order.OrderService.place(..))"
             + " && args(orderId, ..)",
    returning = "result",
    argNames = "orderId,result"
)
public void afterPlace(String orderId, String result) {
    // orderId: input from the call, result: normal return value.
}
```

Example combining `args` with an exception:

```java
@AfterThrowing(
    pointcut = "execution(* com.example.order.OrderService.place(..))"
             + " && args(orderId, ..)",
    throwing = "error",
    argNames = "orderId,error"
)
public void onFailure(String orderId, RuntimeException error) {
    // ...
}
```

Both are **fragments**. In a real application, the return type, exception type, and `place` signature must be compatible. `@AfterThrowing` is not meant to "swallow errors"; if a fallback result for the caller is needed, consider `@Around` with an explicit contract.

### 7.1. `@Around` and `ProceedingJoinPoint` together with binding

```java
@Around(
    value = "execution(* com.example.order.OrderService.place(..))"
          + " && args(orderId, channel)",
    argNames = "orderId,channel"
)
public Object around(
        org.aspectj.lang.ProceedingJoinPoint pjp,
        String orderId,
        String channel) throws Throwable {

    System.out.println("channel=" + channel);
    return pjp.proceed();
}
```

`ProceedingJoinPoint` comes first and **does not need to be listed in `argNames`**. The remaining two Java parameters are bound from the arguments being passed through the proxy.

If you want to **actually change the arguments forwarded to the target**, use `proceed(newArgs)` with an array matching the count and types of the underlying method. Example in Spring AOP:

```java
Object[] newArgs = pjp.getArgs().clone();
newArgs[1] = "normalized-channel";
Object outcome = pjp.proceed(newArgs);
return outcome;
```

Use this only when the underlying method **actually has a second parameter compatible with `String`**. Assigning `channel = "..."` inside advice only modifies a **local variable**; unlike `proceed(newArgs)`, it does not change the argument of the proceeded invocation.

Spring docs note that `proceed(Object[])` in Spring proxy AOP takes an array matching the **underlying method's arguments**, a distinction to separate from pure AspectJ weaving. Do not use it to silently alter sensitive inputs without a clear policy.

## 8. Complete Java 17+ example: binding inputs, receiving `JoinPoint`, and binding the return value

The example focuses on three goals:

1. The target has `send(Object payload, String channel)`. Its method signature fixes `Object`, while the runtime payload can vary in type.
2. A named pointcut `serializableMessages(...)` binds a `Serializable payload` and a `String channel`.
3. `@Before` receives leading `JoinPoint` + input bindings; `@AfterReturning` receives input bindings + `String result`.
4. Call the same method three times with a `String`, a record that does not implement `Serializable`, and an `Integer`.
5. Only the two calls with a `Serializable` payload trigger both advice methods. All three calls execute the target and the caller receives every result.

The project uses **Java 17+, Spring Framework 6.1.14, AspectJ weaver 1.9.22.1, and Maven**, without AspectJ weaving enabled. Versions are pinned for illustration rather than claiming to be the latest.

### 8.1. Directory structure

```text
spring-aop-args-binding/
├── pom.xml
└── src/main/java/com/example/binding/
    ├── MessageService.java
    ├── BindingAspect.java
    ├── AppConfig.java
    └── DemoApp.java
```

### 8.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-aop-args-binding</artifactId>
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
                <configuration>
                    <parameters>true</parameters>
                </configuration>
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

`spring-context` provides `ApplicationContext` and the appropriate Spring AOP transitive dependencies; `aspectjweaver` allows Spring to parse/match `@AspectJ` expressions. `parameters=true` retains parameter-name metadata when needed; the example also specifies `argNames` explicitly so it does not rely solely on automatic inference.

### 8.3. `src/main/java/com/example/binding/MessageService.java`

```java
package com.example.binding;

public class MessageService {

    public String send(Object payload, String channel) {
        String typeName = payload.getClass().getSimpleName();
        System.out.println("[TARGET] channel=" + channel
                + ", type=" + typeName);

        return "sent:" + channel + ":" + typeName;
    }
}
```

The method intentionally declares its first parameter as `Object`, yet is called with `String`, `Integer`, and a record that does not implement `Serializable`. In the demo project, `payload` is always non-null so output is deterministic; if a production API allows null, guard before calling `getClass()`.

### 8.4. `src/main/java/com/example/binding/BindingAspect.java`

```java
package com.example.binding;

import java.io.Serializable;
import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.AfterReturning;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.aspectj.lang.annotation.Pointcut;

@Aspect
public class BindingAspect {

    private final AtomicInteger beforeCount = new AtomicInteger();
    private final AtomicInteger afterCount = new AtomicInteger();

    @Pointcut(
        value = "execution(public java.lang.String "
              + "com.example.binding.MessageService.send(..))"
              + " && args(payload,channel)",
        argNames = "payload,channel"
    )
    public void serializableMessages(
            Serializable payload, String channel) {}

    @Before(
        value = "serializableMessages(payload,channel)",
        argNames = "payload,channel"
    )
    public void before(
            JoinPoint jp,
            Serializable payload,
            String channel) {

        beforeCount.incrementAndGet();
        System.out.println("[BEFORE] method="
                + jp.getSignature().getName()
                + ", channel=" + channel
                + ", type=" + payload.getClass().getSimpleName());
    }

    @AfterReturning(
        pointcut = "serializableMessages(payload,channel)",
        returning = "result",
        argNames = "payload,channel,result"
    )
    public void after(
            Serializable payload,
            String channel,
            String result) {

        afterCount.incrementAndGet();
        System.out.println("[AFTER] type="
                + payload.getClass().getSimpleName()
                + ", result=" + result);
    }

    public int beforeCount() {
        return beforeCount.get();
    }

    public int afterCount() {
        return afterCount.get();
    }
}
```

Detailed analysis:

- The named pointcut takes **two formal parameters**: `Serializable payload`, `String channel`.
- `args(payload,channel)` matches exactly **two arguments** in `send(Object,String)` and binds them by position.
- `Serializable payload` makes the **dynamic runtime type** of `payload` matter: `String` and `Integer` qualify; `PlainPayload` in `main` does not.
- `@Before` has a leading `JoinPoint`. `argNames` **lists only** `payload,channel`, using Spring's special rule.
- `@AfterReturning` references the same named pointcut while also binding `result` via `returning="result"`.
- `String result` is the return value produced by the target when the method finishes normally; additionally receiving input arguments does not alter the return value.
- Two counters distinguish actual advice execution from Spring merely holding a singleton aspect bean.

The example avoids `payload.toString()` to prevent logging actual message data; it prints only the **payload type**, channel, and intentionally constructed string result. In production applications, also check whether `channel` or `result` contains sensitive data.

### 8.5. `src/main/java/com/example/binding/AppConfig.java`

```java
package com.example.binding;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public MessageService messageService() {
        return new MessageService();
    }

    @Bean
    public BindingAspect bindingAspect() {
        return new BindingAspect();
    }
}
```

`@EnableAspectJAutoProxy` activates Spring's auto-proxy infrastructure. `proxyTargetClass=true` selects a CGLIB class proxy because `MessageService` does not implement a business interface. `BindingAspect` must be registered as a bean — `@Aspect` alone is **not** `@Component`.

### 8.6. `src/main/java/com/example/binding/DemoApp.java`

```java
package com.example.binding;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApp {

    public record PlainPayload(String label) {
        // Java records do not implement Serializable automatically.
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {

            MessageService service = context.getBean(MessageService.class);
            BindingAspect aspect = context.getBean(BindingAspect.class);

            System.out.println("isAopProxy="
                    + AopUtils.isAopProxy(service));

            System.out.println("result1="
                    + service.send("hello", "web"));

            System.out.println("result2="
                    + service.send(new PlainPayload("plain"), "queue"));

            System.out.println("result3="
                    + service.send(Integer.valueOf(7), "batch"));

            System.out.println("beforeCount=" + aspect.beforeCount());
            System.out.println("afterCount=" + aspect.afterCount());
        }
    }
}
```

`PlainPayload` is a `record` in `DemoApp` that does **not** implement `Serializable`. `String` and `Integer` implement `Serializable` on JDK 17+; hence the first/last calls vs. the middle call produce different match outcomes on **the same method and the same Spring proxy**.

### 8.7. Running and expected stdout

In the directory containing `pom.xml`, with Maven and JDK 17+:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.binding.DemoApp
```

Lines printed by the program and aspect code, in exact order (excluding environment-dependent Maven/SLF4J messages):

```text
isAopProxy=true
[BEFORE] method=send, channel=web, type=String
[TARGET] channel=web, type=String
[AFTER] type=String, result=sent:web:String
result1=sent:web:String
[TARGET] channel=queue, type=PlainPayload
result2=sent:queue:PlainPayload
[BEFORE] method=send, channel=batch, type=Integer
[TARGET] channel=batch, type=Integer
[AFTER] type=Integer, result=sent:batch:Integer
result3=sent:batch:Integer
beforeCount=2
afterCount=2
```

**Why does this happen?**

1. The aspect has pointcut `execution(...MessageService.send(..))`; Spring creates a proxy because the method can be advised.
2. When given a `String`, the runtime payload type is compatible with `Serializable`, so Spring binds `payload="hello"`, `channel="web"`, and runs `@Before`.
3. The target runs and returns `sent:web:String`; `@AfterReturning` binds **both inputs** and the **output** and prints `[AFTER]`.
4. When given `PlainPayload`, the runtime payload is incompatible with `Serializable`, so **neither advice runs**, while the target still runs normally and returns `sent:queue:PlainPayload`.
5. When given `Integer`, the runtime payload is compatible with `Serializable`; both advice methods run a second time.
6. The final counters are `2` for each advice while the target ran `3` times. This proves **binding and type filtering are evaluated per invocation**, not as a static condition based solely on method name.

**Verification note:** Code and output are designed according to the Spring Framework 6.1 API; this is **expected stdout from the source**. Before using in a production project, run Maven/integration tests on your target JDK and Spring version, because actual classpath/proxy configuration and advisor ordering may differ.

## 9. Edge cases to test when binding arguments

### 9.1. `null`

`null` has no concrete runtime class, yet `args` matching also involves the **method's declared type, binder logic, and Spring/AspectJ implementation**. Do not state an absolute rule like "`args(SomeType)` always matches null" or "always skips null" for every signature.

Safe approach:

- If a method permits `null`, write an integration test with the **exact pointcut and Spring version**.
- Do not call `payload.getClass()`, `payload.toString()`, or unbox if `payload` can be null.
- If advice needs to check **null/non-null values**, consider `JoinPoint.getArgs()` and explicit logic after the pointcut reasonably narrows the method.
- Use `args` for **type constraints**; do not assume it is a full validator for all business inputs.

### 9.2. Primitive and wrapper types

A method with `void submit(int count)` declares a primitive, while object arguments in the interception API may involve boxing. For `args(count)` with an `Integer` or `int` advice parameter, verify matching/binding whenever the application has primitive method signatures. If you only need to select a method declaring `int`, `execution(* *.submit(int))` is more appropriate.

When replacing arguments in `@Around` via `proceed(Object[])`, `null` cannot be unboxed into a primitive. Do not rely on implicit conversions to skip validating inputs.

### 9.3. Varargs is an array parameter at the JVM level

Method:

```java
void submit(String... ids);
```

has a JVM parameter corresponding to a `String[]` array. Even if the caller writes `submit("A","B")`, do not assume a pointcut `args(id1,id2)` will see two separate method arguments. Check varargs/array matching in the Spring/AspectJ version in use and design bindings around the JVM signature when needed.

### 9.4. Generic type erasure

Spring docs warn that `args` cannot be used to fully verify the generic element type of a collection, such as binding `Collection<MyType>` and expecting Spring to check every `MyType` element at runtime.

If you need to receive a collection:

```java
@Before(
    value = "execution(* com.example..BatchService.process(..))"
          + " && args(items)",
    argNames = "items"
)
public void beforeBatch(java.util.Collection<?> items) {
    for (Object item : items) {
        // Check element types manually if policy truly requires it.
    }
}
```

This is a **method fragment** requiring a `BatchService` bean/class. `Collection<?>` avoids promising a generic element type that cannot be verified at runtime. Do not read a generic `Collection<Order>` on an advice signature as an automatic Spring AOP filter.

### 9.5. Annotation binding differs from `args`

`args(payload)` binds a method input value. `@args(SomeAnnotation)` is a **different pointcut designator**: it inspects annotations on the runtime types of arguments, rather than serving as a binding equivalent of `args`.

`@annotation(audited)` can bind the **annotation instance attached to the method** to an advice parameter; `target(bean)` can bind the target object; `this(proxy)` can bind the Spring proxy object. When combining these bindings, the `argNames` list must accurately cover **all ordinary formal parameters** that the advice needs to bind.

Example fragment:

```java
@Before(
    value = "execution(* com.example..Service.*(..))"
          + " && args(payload,..)"
          + " && target(bean)",
    argNames = "payload,bean"
)
public void inspect(Object payload, Object bean) {
    // payload: an argument, bean: target instance.
}
```

Do not confuse `bean` in `target(bean)` with the Spring-specific `bean(namePattern)` pointcut: those two notations serve different purposes.

## 10. Spring proxy boundary: a prerequisite even before binding

Even when `args` and `argNames` are written properly, advice **does not run automatically** if the method call does not pass through a Spring AOP proxy:

```text
Spring Bean A -> Spring proxy of Bean B -> advice binding args -> target method
Spring Bean B -> this.method(...)       -> bypasses Spring AOP proxy
new BeanB().method(...)                 -> object outside Spring proxy
```

Verify that:

- **The aspect is registered as a Spring bean** via `@Component` or `@Bean`, not just annotated with `@Aspect`.
- `@EnableAspectJAutoProxy` or the corresponding Spring Boot AOP auto-configuration is active.
- The target bean lives in the same `ApplicationContext` that has the auto-proxy infrastructure.
- Callers use the reference provided by Spring, rather than calling `new` on the service or holding a raw reference.
- With a JDK proxy, the method is exposed via the proxied interface; with CGLIB, `final`/`private` methods are not overridden by the proxy in the normal way.
- The invoked method actually matches the `execution`/scope pointcut **and** the dynamic `args` conditions.

**Having `AopUtils.isAopProxy(bean) == true` does not prove `args(payload)` matches an invocation.** The proxy may exist because of another advisor, while the argument's runtime type varies from call to call.

## 11. Why combine `execution` with `args`?

Spring has both static and dynamic pointcut checks. `execution` lets Spring quickly identify relevant **method/class signatures**; `args` may need to inspect arguments on **each invocation**.

An overly broad expression:

```java
@Before("args(java.io.Serializable)")
public void anySerializable() {}
```

can match many unrelated methods across proxied Spring beans. If the advice performs logging/auditing, this increases overhead and the risk of logging sensitive data.

A narrower expression:

```java
@Before(
    "execution(public * com.example.billing.BillingService.submit(..))"
    + " && args(java.io.Serializable,..)"
)
public void chosenSerializable() {}
```

examines only calls whose method signature and target match the intended scope, then filters by runtime argument type.

**Do not imagine business value logic into `args`.** For example, `args(java.math.BigDecimal)` does not check `amount > 100000`; bind `BigDecimal amount` and check the value inside the advice or appropriate validation/service logic.

Consider performance when there are many dynamic advice pointcuts, but **prioritize correctness and clear scoping** before micro-optimizing. With Spring's `MethodMatcher`, there are both static matching and runtime matching capabilities; do not claim that every `args` expression necessarily forces Spring to check every method of every bean on every call.

## 12. Common errors when binding arguments

| Symptom | Possible cause | How to check / fix |
| --- | --- | --- |
| Spring reports parameter name could not be determined | Missing `argNames`/`-parameters`, or complex expression cannot be inferred | Declare `argNames` completely; compile Java with `-parameters` where appropriate. |
| Named pointcut has 2 parameters but advice references it with no arguments | Mismatched binding count | Use `pointcutName(payload,channel)` and matching signature. |
| Bound `payload` is null and causes NPE | Advice assumes every argument is non-null | Check for null; test APIs with nullable values. |
| `args(Serializable)` runs for `String` even though method declares `Object` | This is runtime type matching, expected behavior | Distinguish `args` from `execution` static signature matching. |
| Same method runs advice once and skips it another time | Actual argument types differ | Inspect inputs on the same Spring proxy; check binding type. |
| Advice receives the wrong argument position | Expression and Java signature have different ordering | Check `args(first,second)`, `argNames`, and parameter order. |
| `argNames` omits the leading `JoinPoint` | This can be permitted by Spring | Distinguish leading `JoinPoint`/`ProceedingJoinPoint` from ordinary parameters. |
| `@AfterReturning` confused with input binding | `returning="result"` is the return value, not a method input | Use `args(input)` separately and declare both input and result in `argNames`. |
| `@AfterThrowing` does not receive the exception | `throwing` name differs from advice parameter, incompatible type, or method threw nothing | Align `throwing` with the advice parameter and test failure paths. |
| Assigning `payload = replacement` in advice leaves target with the old value | Reassigning a local advice parameter does not modify invocation arguments | Use `@Around` + `proceed(newArgs)` if policy requires it and types match. |
| Binding a generic collection fails to filter item types | Erasure and generic-type matching limits | Use `Collection<?>` and inspect elements or design a typed request object. |
| `@Aspect` exists yet advice does not run | Aspect is not a bean, proxying is off, call goes through `this`/`new`, or pointcut doesn't match | Check context, proxy, advisor, method, and call path. |
| `args` matches in many unexpected places | Pointcut relies only on a broad argument type | Constrain with `execution`/package/class and add negative tests. |
| `@args` used mistakenly instead of `args` | `@args` checks annotations on runtime argument types | Use the right designator for your binding needs. |

## 13. Checklist for testing argument binding properly in Spring

A reliable integration test should verify **registration, type matching, value binding, and business behavior**:

1. The Spring `ApplicationContext` contains the target bean and aspect bean as designed.
2. `AopUtils.isAopProxy(target)` is true when advisors can apply, though do not rely on this check alone.
3. The method is invoked by the caller through the Spring proxy, not via self-invocation or a `new`-created instance.
4. For an argument of a matching type, the advice receives the **exact object and position**, not merely the right class name.
5. For an argument of a non-matching type, the target still runs while the advice counter does not increment.
6. When using two arguments, test swapping order/types where the API allows it to catch misbinding.
7. If `JoinPoint` is present, verify `getSignature().getName()`, `getArgs()`, `getThis()`, and `getTarget()` behave as intended.
8. When combining `@AfterReturning`/`@AfterThrowing`, test normal returns and exceptions separately, including input/output binding names.
9. If `@Around` modifies arguments, assert the target receives the actual **newArgs** and the caller receives a valid return value.
10. Test null, primitives, varargs, and generic collections if the business API includes those cases.
11. Protect sensitive data: do not log full payloads, passwords, or tokens simply because `args(payload)` makes access easy.
12. When refactoring advice parameter names, named pointcuts, method signatures, or upgrading Spring versions, re-run tests covering binding annotations and build metadata.

Example matrix for the project in section 8:

```text
send("hello", "web")             -> target +1, BEFORE +1, AFTER +1
send(new PlainPayload(...), ...) -> target +1, BEFORE +0, AFTER +0
send(Integer.valueOf(7), ...)   -> target +1, BEFORE +1, AFTER +1

Total target = 3; beforeCount = 2; afterCount = 2
```

These numbers depend on the **declared named pointcut**, not because every Spring Aspect using `args` runs exactly twice.

## 14. Summary of the mechanism and official documentation

| Question | Short answer |
| --- | --- |
| What does `args(java.io.Serializable)` do? | Filters by compatible **runtime argument type**, without binding a named value. |
| What does `args(payload)` do? | Binds the argument value to the formal parameter named `payload` with the declared type. |
| What is `argNames` used for? | Provides an explicit parameter-name mapping for Spring Aspect binding. |
| Does `JoinPoint` need to appear in `argNames`? | A **leading `JoinPoint`/`ProceedingJoinPoint`/`StaticPart`** may be omitted according to Spring rules. |
| Can a named `@Pointcut` bind values? | Yes, via formal parameters and `args(...)`, then referencing the pointcut with parameters from advice. |
| Can `@AfterReturning` receive input and output together? | Yes: `args(input)` and `returning="result"`. |
| Can `@Around` change arguments passed to the target? | Yes: use `proceed(Object[])` with matching count/types; reassigning a local parameter is not enough. |
| Does `args` filter by values such as `amount > 100`? | No; check values inside advice or validation logic. |
| Do code outside Spring or self-invocation trigger binding advice? | No, under standard Spring proxy AOP mechanics. |

Spring Framework documentation for cross-reference:

- Declaring Advice — Advice Parameters, Passing Parameters to Advice, Determining Argument Names: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html
- Declaring a Pointcut — Supported Pointcut Designators, `args`: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html
- Enabling @AspectJ Support: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html
- Pointcut API — Static and Dynamic MethodMatcher: https://docs.spring.io/spring-framework/reference/core/aop-api/pointcuts.html
- Proxying Mechanisms — Spring proxy boundary: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html

**Conclusion:** `args` in a Spring Aspect is the bridge between **runtime invocation arguments** and **typed formal advice parameters**. To use it correctly, understand how `args(type)` differs from `args(name)`, enforce **matching positions, types, and names**, coordinate `argNames` or `-parameters` properly, and test against a **real Spring AOP proxy**. When you also need the return value or thrown exception, use `returning`/`throwing` independently of input binding; when you need to alter arguments reaching the target, use `@Around` and `proceed(newArgs)` per the method contract.
