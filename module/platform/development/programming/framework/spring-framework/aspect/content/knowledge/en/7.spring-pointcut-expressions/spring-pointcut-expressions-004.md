# `args` by Actual Argument Type in Spring AOP

## 1. Purpose of `args(...)` When Writing a Spring Aspect

In Spring AOP, the `args(...)` pointcut selects **method executions on a Spring bean through a proxy** based on the **actual arguments passed at call time**. Unlike `execution(...)`, which restricts by declared method signature, `args` is a condition that can depend on runtime data of each invocation.

For example, a bean has the method:

```java
public void send(Object payload) {
    // ...
}
```

The same `send(Object)` method can be called with `"hello"` (a `String`), `Integer.valueOf(7)`, or a custom object that does not implement `Serializable`. An `args(java.io.Serializable)` pointcut can select calls carrying an **actual argument of type `Serializable`**, even though the method declared its parameter as `Object`.

The core difference:

```text
Declared method: send(Object value)

send("hello")            -> runtime value is String, implements Serializable
send(Integer.valueOf(7)) -> runtime value is Integer, implements Serializable
send(new PlainPayload()) -> runtime value is PlainPayload, not Serializable

execution(* *.send(java.io.Serializable)) -> checks declared parameter
args(java.io.Serializable)                -> checks actual argument at call time
```

**Scope:** This lesson only explains `args` in **Spring @AspectJ-style AOP, applied to Spring-managed beans called through an AOP proxy**. It is not a standalone AspectJ weaving lesson and does not discuss pointcuts generally outside Spring's scope.

## 2. Accurately Distinguishing `args` and `execution`

Two expressions that look similar are not equivalent:

```java
// Applies only to methods with exactly one parameter declared as type Serializable:
execution(* *.send(java.io.Serializable))

// Checks an argument passed at runtime whose type is compatible with Serializable:
args(java.io.Serializable)
```

Suppose a `MessageGateway` declares:

```java
void send(Object payload);
```

When a caller passes a `String`, the Java signature **remains** `send(Object)`; the JVM does not change the method signature to `send(String)`. Therefore:

- `execution(* *.send(java.io.Serializable))` **does not match** the `send(Object)` signature simply because the caller passed a `String`.
- `args(java.io.Serializable)` can **match the execution** when the runtime value implements `Serializable`.
- A subsequent call passing an object that does not implement `Serializable` may **not match**, even though the method and proxy are the same objects.

Official Spring documentation presents this exact distinction via `args(java.io.Serializable)` and `execution(* *(java.io.Serializable))`: the former evaluates the runtime argument, while the latter evaluates the signature declaration.

| Criterion | `execution(...)` | `args(...)` |
| --- | --- | --- |
| Primary focus | Method execution, method name, return type, **declared** parameter types | Types of **actual arguments** passed |
| One method receiving different object types | Signature condition stays the same | Match result can differ between two calls |
| When Spring evaluates | Many parts can be determined before invocation | Parts requiring runtime args must be checked on each invocation |
| Restricting package/class/method | Very suitable | Cannot replace scoping by class/method |
| Retrieving argument value in advice | Does not bind values directly from signature alone | Uses `args(name)` paired with an advice parameter to bind |
| Objects outside Spring container | Not auto-proxied by Spring AOP | Also not auto-proxied by Spring AOP |

**Do not use `args` to replace all of `execution`.** Good practice in Spring is to combine a narrow static condition with a runtime condition:

```java
@Before(
  "execution(public * com.example.app.MessageGateway.send(..))" +
  " && args(java.io.Serializable)"
)
public void beforeSerializable() {
    // ...
}
```

This is an **illustrative fragment** that must be placed in a registered Spring `@Aspect`. The outer expression restricts to the service's `send` method, while `args` only filters the runtime type. Avoid standing `args(java.io.Serializable)` alone across the entire application without a clear reason: it may select many unintended methods.

## 3. Syntax of `args` in Spring Pointcut Expressions

### 3.1. A Single Argument of a Given Type

```text
args(java.io.Serializable)
args(com.example.domain.OrderRequest)
```

`args(java.io.Serializable)` selects join points with **exactly one argument** compatible with `Serializable`. Similarly, `args(com.example.domain.OrderRequest)` uses the `OrderRequest` type declared by the application.

AspectJ type matching evaluates assignability: a `String` object implements `Serializable`; a subclass of `OrderRequest` is also compatible if the type relationship holds. Spring evaluates this condition on Spring bean method calls that a proxy can intercept, not on every Java call in the JVM.

### 3.2. Multiple Arguments and `..`

```text
args(java.io.Serializable, java.lang.String)
args(java.io.Serializable, ..)
args(.., java.lang.String)
args(*, java.lang.String)
args(..)
```

- `args(Serializable, String)`: the method is called with **exactly two** matching arguments in that order.
- `args(Serializable, ..)`: the **first argument** has a type compatible with `Serializable`, followed by **zero or more** other arguments.
- `args(.., String)`: the **last** argument has a type compatible with `String`, preceded by any number of arguments.
- `args(*, String)`: has exactly two arguments; `*` is a pattern for any single argument in the first position.
- `args(..)`: does not constrain the types or number of arguments; standing alone, it is usually not a sufficiently narrow filter.

When a pattern has multiple arguments, **position matters greatly**. For a method `save(String id, Object payload)`, `args(Serializable, ..)` checks `id`, without automatically jumping to `payload` in the second position. Choose a pattern or bind according to the exact position to check.

### 3.3. `args(type)` and `args(variable)` Are Two Different Usage Forms

In an annotation pointcut:

```java
args(java.io.Serializable)
```

is a **type pattern**. Whereas:

```java
args(payload)
```

can be **binding** when `payload` is declared as a parameter in the advice method or named pointcut. The Java type of the bound parameter helps determine the valid argument type.

Do not write `args(payload)` in the annotation and forget to declare `payload` in the advice or fail to provide binding information Spring can resolve. The result is usually an aspect/pointcut initialization error, not an advice silently skipping every invocation.

### 3.4. `args` Differs from `@args`

`args(com.example.domain.OrderRequest)` checks whether the **argument type** is compatible with `OrderRequest`.

`@args(com.example.annotations.Classified)` checks whether an **annotation is present on the runtime type of the argument** per AspectJ semantics—not the `Classified` type itself and not an annotation placed on the parameter in the method signature.

These are **two distinct pointcut designators supported by Spring AOP**. If the goal is an annotation on the called method itself, see `@annotation` rather than confusing it with `@args`.

## 4. Binding Argument Values to Advice Methods

A very useful feature in Spring `@Aspect` is passing runtime arguments into an advice method as strongly typed Java parameters.

Example fragment:

```java
@Aspect
public class AuditAspect {
    @Before(
        value = "execution(public * com.example.app.MessageGateway.send(..))"
              + " && args(payload)",
        argNames = "payload"
    )
    public void before(Serializable payload) {
        System.out.println(payload.getClass().getSimpleName());
    }
}
```

Here:

1. `execution(...send(..))` restricts the method scope.
2. `args(payload)` requires a matching argument and **binds** that argument to the name `payload`.
3. The advice declares `Serializable payload`, so the bound type is checked against that Java type.
4. `argNames = "payload"` clarifies the parameter name used when binding the advice; it is not a field name or bean name in the container.
5. When the advice runs, `payload` is the actual object passed at the call site, not an object Spring created to satisfy the pointcut.

**Spring must be able to resolve the parameter name for binding.** You can use `argNames`, compile with parameter name retention, or rely on name discovery mechanisms supported by your Spring version. Declaring `argNames` explicitly reduces reliance on build flags in examples.

### 4.1. `JoinPoint.getArgs()` and `args(name)`

Two common ways to obtain arguments:

```java
@Before("execution(* com.example.app.MessageGateway.send(..))")
public void observe(org.aspectj.lang.JoinPoint jp) {
    Object[] arguments = jp.getArgs();
    // Manually inspect argument types when needed.
}
```

and:

```java
@Before(
    value = "execution(* com.example.app.MessageGateway.send(..))"
          + " && args(payload)",
    argNames = "payload"
)
public void observe(Serializable payload) {
    // Argument is bound by type.
}
```

These are **two alternative fragments**, not two advices required to run together.

- `JoinPoint.getArgs()` provides the argument array for the matched call, allowing conditional inspection.
- `args(payload)` performs **filtering and binding** directly in the pointcut, reducing manual type checks in the advice.
- If the application needs to filter by **value** (e.g., `amount > 1000`) rather than just type, you still need value checks inside the advice or another predicate design; `args(java.lang.Number)` does not check value ranges by itself.

### 4.2. Two-Argument Example

For a method `reserve(String orderId, Object data)`:

```java
@Before(
    value = "execution(* com.example..ReservationService.reserve(..))"
          + " && args(orderId, data)",
    argNames = "orderId,data"
)
public void beforeReserve(String orderId, Serializable data) {
    // Runtime data must satisfy the Serializable condition.
}
```

This is a fragment requiring appropriate classes/packages. It binds **two positions** in order. If the method signature adds a third parameter, the `args(orderId,data)` expression no longer matches because it describes exactly two arguments. When you want to keep trailing parameters flexible, use `..` appropriately and verify actual positions.

## 5. Runnable Example: `send(Object)` While Advice Selects Runtime Type

The following complete example uses **Java 17+, Spring Framework 6.1.14, AspectJ weaver 1.9.22.1, and Maven**.

Intentional design:

- `MessageGateway.send(Object)` always has an **Object parameter signature**.
- The caller passes sequentially a `String`, a `PlainPayload` that does not implement `Serializable`, and an `Integer`.
- One advice **uses `args(payload)` with a `Serializable` parameter** to select `String`/`Integer` by runtime type.
- A control advice uses `execution(...send(java.io.Serializable))` to demonstrate that a method declared with `Object` does not suddenly turn into a `Serializable` signature.
- Spring AOP uses a **JDK proxy** via the business interface; the target makes no internal self-calls to avoid confusing proxy boundaries.

### 5.1. Project Structure

```text
spring-aop-runtime-args/
├── pom.xml
└── src/main/java/com/example/argsdemo/
    ├── AppConfig.java
    ├── MessageGateway.java
    ├── MessageService.java
    ├── ArgsAuditAspect.java
    └── DemoApp.java
```

### 5.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-aop-runtime-args</artifactId>
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

`spring-context` provides the Spring container and pulls in the foundational Spring AOP modules via the example's dependency tree. `aspectjweaver` allows Spring to process `@Aspect`/pointcut declarations. The goal is **Spring proxy-based AOP**; neither the AspectJ compiler nor a weaving agent is enabled.

### 5.3. `src/main/java/com/example/argsdemo/MessageGateway.java`

```java
package com.example.argsdemo;

public interface MessageGateway {
    void send(Object payload);
}
```

The method has only one parameter **declared as `Object`**, regardless of what class of object callers later pass. The interface lets the example use a JDK dynamic proxy without needing a class-based proxy.

### 5.4. `src/main/java/com/example/argsdemo/MessageService.java`

```java
package com.example.argsdemo;

public class MessageService implements MessageGateway {
    @Override
    public void send(Object payload) {
        String type = payload.getClass().getSimpleName();
        System.out.println("[TARGET] " + type + ": " + payload);
    }
}
```

To print stable output and avoid mixing in `null` rules, the example only passes non-`null` objects. In real applications, if the API allows `null`, the target must check `payload == null` before calling `getClass()`.

### 5.5. `src/main/java/com/example/argsdemo/ArgsAuditAspect.java`

```java
package com.example.argsdemo;

import java.io.Serializable;
import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class ArgsAuditAspect {
    private final AtomicInteger runtimeMatches = new AtomicInteger();
    private final AtomicInteger signatureMatches = new AtomicInteger();

    @Before(
        value = "execution(public * com.example.argsdemo.MessageGateway.send(..))"
              + " && args(payload)",
        argNames = "payload"
    )
    public void runtimeSerializable(Serializable payload) {
        runtimeMatches.incrementAndGet();
        System.out.println("[AOP args] " + payload.getClass().getSimpleName());
    }

    @Before(
        "execution(public * com.example.argsdemo.MessageGateway.send(java.io.Serializable))"
    )
    public void declaredSerializableSignature() {
        signatureMatches.incrementAndGet();
        System.out.println("[AOP execution] Serializable signature");
    }

    public int runtimeMatches() {
        return runtimeMatches.get();
    }

    public int signatureMatches() {
        return signatureMatches.get();
    }
}
```

Method `runtimeSerializable` binds the `Serializable`-typed value passed via `args(payload)`. Spring must inspect the runtime argument of each call to decide whether the advice should run. Method `declaredSerializableSignature` only matches if the method actually **declares a parameter of type `Serializable`**, which is not true for `MessageGateway.send(Object)`.

The two counters make testing transparent: the number of times `@Before` was invoked for each rule, not the number of aspect objects created.

### 5.6. `src/main/java/com/example/argsdemo/AppConfig.java`

```java
package com.example.argsdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class AppConfig {
    @Bean
    public MessageGateway messageGateway() {
        return new MessageService();
    }

    @Bean
    public ArgsAuditAspect argsAuditAspect() {
        return new ArgsAuditAspect();
    }
}
```

`@EnableAspectJAutoProxy` enables Spring's auto-proxy creator. `MessageGateway` is managed by Spring; `ArgsAuditAspect` has both `@Aspect` and `@Bean` so Spring detects it. The `false` flag allows a JDK proxy when an appropriate interface exists and no other configuration forces CGLIB.

### 5.7. `src/main/java/com/example/argsdemo/DemoApp.java`

```java
package com.example.argsdemo;

import java.io.Serializable;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApp {
    private static final class PlainPayload {
        @Override
        public String toString() {
            return "payload";
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {

            MessageGateway gateway = context.getBean(MessageGateway.class);
            ArgsAuditAspect aspect = context.getBean(ArgsAuditAspect.class);

            System.out.println("isJdkProxy="
                    + AopUtils.isJdkDynamicProxy(gateway));

            gateway.send("hello");
            gateway.send(new PlainPayload());
            gateway.send(Integer.valueOf(7));

            System.out.println("runtimeMatches=" + aspect.runtimeMatches());
            System.out.println("signatureMatches=" + aspect.signatureMatches());
        }
    }
}
```

`PlainPayload` does not declare `implements Serializable`. Both `String` and `Integer` implement `Serializable` on JDK 17+. If you notice the `java.io.Serializable` import in `DemoApp` is unused directly, it can be removed without affecting the result; the Java compiler allows unused imports so the project still compiles.

### 5.8. Running and Expected Output

From the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.argsdemo.DemoApp
```

Lines printed by the program in exact order; any Maven/SLF4J messages are excluded from the illustrative output:

```text
isJdkProxy=true
[AOP args] String
[TARGET] String: hello
[TARGET] PlainPayload: payload
[AOP args] Integer
[TARGET] Integer: 7
runtimeMatches=2
signatureMatches=0
```

**Output explanation:**

1. Spring creates a JDK proxy because the bean implements `MessageGateway` and an advisor can apply to `send(Object)`.
2. `"hello"` is a `String`, which implements `Serializable`, so the call through the proxy runs `runtimeSerializable` before the target prints its content.
3. `PlainPayload` does not implement `Serializable`, so the advice with `args(payload)` and parameter `Serializable` does not run; the target still executes the method.
4. `Integer.valueOf(7)` is an `Integer`, which also implements `Serializable`, so the advice runs a second time.
5. `signatureMatches=0` because the method **declares `Object`**, regardless of runtime arguments. No call alters the method signature in bytecode.
6. The target running all three times while the advice runs only twice shows that `args` evaluates **per invocation**; the result is not a fixed configuration on the target object.

This code demonstrates **type matching**. In production, do not treat `Serializable` as a sign that an argument is safe to log or serialize; it is a Java marker interface, not a representation of payload security or trustworthiness.

## 6. Why Must You Understand Runtime Dependency?

Part of a pointcut can be evaluated by Spring using class/method metadata when building proxies. With `args`, however, **the same method on the same proxy** can produce different results depending on the argument being passed.

In Spring's pointcut API, a `MethodMatcher` has:

```java
boolean matches(Method method, Class<?> targetClass);
boolean isRuntime();
boolean matches(Method method, Class<?> targetClass, Object... args);
```

These are **simplified interface signatures for explanation**, not a standalone compilable class. When `isRuntime()` is true, Spring may need the argument-accepting check method for each method invocation. This reflects the actual cost of dynamic pointcuts, even though Spring optimizes with static matching to quickly rule out target methods that cannot possibly match.

Helpful practices:

- **Bound classes/methods with `execution` or `within`**, then add `args` to filter argument types.
- Avoid declaring just `args(java.io.Serializable)` application-wide when you only want to audit a specific business API.
- If the requirement is a method with a specific signature, consider using `execution` alone—it can be simpler and avoid unnecessary dynamic matching.
- Do not rely on myths that `args` automatically checks values, object contents, or class annotations: those requirements need different conditions.

**The issue is not just performance.** A broad pointcut can cause an advice that depends on runtime data to apply to many unintended modules, increasing coupling or creating audit logs containing inappropriate information.

## 7. Inheritance, Interfaces, and Polymorphism

Suppose:

```java
interface Event {}

class OrderEvent implements Event {}

class PaymentEvent implements Event {}
```

These are illustrative fragments; place them in appropriate files/packages when implementing.

When a method declares `void handle(Object event)`, the pointcut:

```text
args(com.example.domain.Event)
```

can match runtime arguments that are `OrderEvent` or `PaymentEvent` because they implement `Event`. With:

```text
args(com.example.domain.OrderEvent)
```

the filter is narrower and selects only arguments of type `OrderEvent` or a compatible subtype.

Where a method declares `handle(Event event)` while the caller actually passes `OrderEvent`, `execution(* *.handle(com.example.domain.Event))` checks the **declared type `Event`**, whereas `args(com.example.domain.OrderEvent)` checks the **actual `OrderEvent` object**. Both can be combined if the goal is selecting the method by API and subtype at runtime:

```text
execution(* com.example..EventService.handle(com.example.domain.Event))
&& args(com.example.domain.OrderEvent)
```

This combination is usually easier to reason about than a pointcut relying solely on method name or runtime arguments.

### 7.1. Overload Selection Still Happens Before Spring AOP Evaluates `args`

If a class has:

```java
void process(Object value)
void process(String value)
```

The Java compiler resolves the overload using the **compile-time type of the expression at the call site** (and overload resolution rules); Spring AOP `args` does not decide which method overload is called. After the method is chosen and the invocation passes through the proxy, the pointcut can inspect runtime arguments.

For example, `Object x = "abc"; service.process(x);` selects the `process(Object)` overload at compile time, even though the runtime value is `String`. `args(String)` can still match the runtime value, but `execution(* *.process(String))` will not match the called method signature.

This is especially important when debugging Spring aspects on overloaded service APIs.

## 8. Edge Cases That Must Be Tested

### 8.1. `null` Arguments

`null` has no concrete runtime class on which to call `getClass()`, yet AspectJ and Spring matching/binding mechanisms may still consider the declared signature and compatibility rules. Therefore, **do not infer absolutely** that `args(SomeType)` always matches or never matches when the argument is `null`.

If a method allows `null`, you should:

1. Write an integration test on the **actual Spring version and pointcut**.
2. Confirm whether the advice runs across different signatures.
3. If the advice can receive `null`, do not call `payload.getClass()` without checking first.
4. If logic must distinguish null/non-null, consider using advice with `JoinPoint.getArgs()` or explicit checks in business validation, rather than assuming an `args(Type)` condition equates to `value != null`.

Defensive example:

```java
String typeName = (payload == null)
        ? "<null>"
        : payload.getClass().getSimpleName();
```

This is a Java fragment with no Spring AOP effect of its own unless placed properly inside an advice/bean.

### 8.2. Primitives and Boxing

A method declared as `void count(int n)` uses a primitive in its signature, while Spring advice binding passes values via object argument arrays involving boxing/unboxing. An example like `args(Integer)` on a primitive method may require checking exact matching details for your Spring/AspectJ version, rather than assuming runtime always holds an `Integer` matching what the caller constructed.

**Recommendation:** when a business API uses a primitive signature, use `execution(...int)` to identify the signature if that is what you want to select; introduce `args` only when you genuinely need a runtime condition and have integration tests.

### 8.3. Varargs

A method `void send(String... messages)` compiles to accept **a `String[]` array** at the varargs position; a call can be written `send("a","b")`, yet the JVM signature has one array parameter. Do not assume `args(String, String)` will match as if the method declared two separate parameters. Check varargs/array matching rules on the Spring version in use; many cases require an expression matching the **array argument** rather than the varargs element count.

### 8.4. Generic Type Erasure

Spring docs note limitations when using `args` to constrain generic types of collections like `Collection<MyType>`: runtime does not retain full generic info for Spring/AspectJ to automatically check every element in the collection.

An unworkable pattern you should not write:

```java
@Before(
    "execution(* com.example..Repository.*(..)) && args(list)"
)
public void before(java.util.Collection<MyType> list) {
    // Cannot ask Spring AOP to verify generic element types via args.
}
```

This is an **unsuitable example**, not recommended runnable code. If you need to receive a collection, use `Collection<?>` and **inspect actual elements** as required by business logic, or design the API with a concrete request type carrying an explicit contract.

### 8.5. Runtime Proxies, JDK/CGLIB, and Spring Bean Boundaries

`args` is only evaluated once the call **has entered an eligible Spring AOP proxy**:

- Caller uses `new MessageService().send("x")`: Spring AOP does not intercept because the object is not managed through a proxy.
- Bean calls `this.send("x")` on itself: self-invocation usually bypasses the Spring AOP proxy, so `args` never gets evaluated.
- Same method called via a JDK proxy: the method must be on the proxied interface and the advice/pointcut must match.
- CGLIB class proxy: subject to limits such as `final`/`private` classes or methods that cannot be overridden.
- `@PostConstruct` calling a method on the raw target during initialization: does not automatically create a Spring AOP interception for that internal call.

**Do not diagnose call-path issues by switching `args` to `execution`.** If the caller does not go through the proxy, neither turns a raw target call into a join point Spring AOP can advise.

## 9. Common Mistakes

| Symptom | Possible cause | How to fix / verify |
| --- | --- | --- |
| `args(Serializable)` runs with `String` even though method takes `Object` | This is runtime type matching, working as designed. | Compare with `execution(* *.method(Serializable))` to see the signature is still `Object`. |
| Advice runs on one call but not the next on the same method | Runtime argument types differ. | Safely log type names, inspect arguments and pointcut in an integration test. |
| `args(payload)` reports unable to bind parameter | Advice lacks a matching parameter name/type or name metadata cannot be determined. | Use `argNames`, declare parameter with right type and order, check Spring aspect binding. |
| `args(String,..)` does not match as expected | The `String` argument is not in the first position, or signature does not match. | Check position, `..`, and argument count. |
| Pointcut meant to filter `String` used `execution(...String)` | `execution` filters declared parameter type. | Use `args(String)` if runtime filtering is needed and scope with `execution` method. |
| Declared `@args(Serializable)` instead of `args(Serializable)` | `@args` inspects annotations on the runtime class, not the `Serializable` interface/type. | Distinguish `@`-prefixed designators and problem requirements. |
| `args(Collection<Payment>)` does not filter by element | Java type erasure and generic matching limits. | Bind `Collection<?>`, inspect elements in code if genuinely needed. |
| Pointcut selects many unintended services | `args(...)` does not restrict bean/class/method on its own. | Combine narrow `execution`/`within` by package/service. |
| `@Aspect` exists yet never runs for any argument | Aspect is not a Spring bean, auto-proxy is not enabled, or caller bypasses proxy. | Check bean registration, `@EnableAspectJAutoProxy`, `AopUtils`, and call path. |
| Advice throws `NullPointerException` on `getClass()` | Missing null guard when advice is invoked. | Check for null and test pointcut/binding behavior explicitly. |
| Advice expects `args(Number)` alone to filter `amount > 1000` | `args` is a type condition, not a value condition. | Check `number.doubleValue()` or explicit business logic inside advice. |

## 10. Choosing Between `args`, `execution`, `@args`, and Reading `JoinPoint`

| Actual requirement in Spring | Mechanism to consider |
| --- | --- |
| Select `send` method with declared signature `send(Object)` | `execution(* ..MessageGateway.send(java.lang.Object))`. |
| Run advice only when runtime argument implements `Serializable` | `execution(* ..MessageGateway.send(..)) && args(java.io.Serializable)`. |
| Receive actual argument in advice with a specific type | `args(payload)` and declare advice parameter `Serializable payload`, with `argNames` when needed. |
| Select only arguments whose runtime class carries an annotation | `@args(com.example.MyMarker)`, requiring appropriate runtime annotation setup. |
| Select methods annotated with `@Audit` | `@annotation(com.example.Audit)`, not `@args`. |
| Select methods in a service package before filtering runtime arguments | Use `execution` or `within` as scope + `args`. |
| Need to compare values/amounts/ids | Advice uses `JoinPoint.getArgs()` or binding and then checks values, not `args(Type)` alone. |

Example of declaring a named pointcut for reuse:

```java
@Pointcut(
    value = "execution(public * com.example..MessageGateway.send(..))"
          + " && args(payload)",
    argNames = "payload"
)
public void serializableMessages(Serializable payload) {}

@Before(value = "serializableMessages(payload)", argNames = "payload")
public void audit(Serializable payload) {
    // ...
}
```

This is a **fragment inside an `@Aspect` class**, requiring `@Pointcut`, `@Before`, and `Serializable` imports. Multiple advices can reference the named pointcut to share logic, while still keeping binding names consistent in each advice.

## 11. Testing `args` in a Spring Application

A good integration test should use a **real Spring context** and a bean returned as a proxy:

1. Verify the aspect bean and target bean are registered in the right context.
2. Verify `AopUtils.isAopProxy(bean)`; if using a JDK proxy, you can check `isJdkDynamicProxy(bean)`.
3. Run the method once with an argument of **matching runtime type**; expect the advice counter to increment.
4. Run **the same method/same proxy** again with a different argument type; expect the counter not to increment.
5. Contrast with an `execution` pointcut filtering the signature to ensure signature/runtime types are not confused.
6. Test polymorphism: interface/supertype and runtime subtypes.
7. Test method overloads/varargs, primitives, `null`, and generic collections if the API supports them.
8. Verify target return values/exceptions are not unintentionally altered when adding `@Before`/`@Around`.
9. Verify each advice runs the **exact expected number of times** if multiple `@Aspect`s match the same method.
10. Keep pointcuts narrow enough not to apply accidentally to other beans.

General assertion example for the three calls in this lesson:

```text
send("hello")             -> runtime Serializable -> advice +1
send(new PlainPayload())  -> runtime not Serializable -> advice +0
send(Integer.valueOf(7))  -> runtime Serializable -> advice +1

Total: target runs 3 times; args advice runs 2 times.
```

This is the result for the **stated demo configuration**, not a claim that every `args` pointcut in every Spring application has the same advice counts.

### Official Documentation

- Spring Framework — Declaring a Pointcut / Supported Pointcut Designators: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html
- Spring Framework — Declaring Advice / Passing Parameters to Advice: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html
- Spring Framework — Pointcut API / Static and Dynamic MethodMatcher: https://docs.spring.io/spring-framework/reference/core/aop-api/pointcuts.html
- Spring Framework — Enabling @AspectJ Support: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html
- Spring Framework — Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html

**Conclusion:** In a Spring Aspect, `args` filters calls by the **types of actual arguments passed** and can bind that argument to the advice method; `execution` selects methods by **declared signature**. Combining both on **Spring beans called through a proxy** lets you define pointcuts that match business intent while avoiding overly broad advice application.
