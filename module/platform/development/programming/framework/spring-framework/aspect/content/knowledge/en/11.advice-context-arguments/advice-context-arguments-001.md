# Spring AOP: Using `JoinPoint` to Read Arguments, Signatures, and Invocation Context

## 1. What problem does `JoinPoint` solve in a Spring Aspect?

When writing advice in Spring AOP, sometimes knowing that a call matches a pointcut is not enough: you also want to know **which method is executing**, **what arguments were passed**, **which Spring proxy received the call**, and **which target bean performs the business logic**.

Spring provides the `org.aspectj.lang.JoinPoint` object to the advice being invoked. This is a **context snapshot of the current method execution** observed by the Spring AOP proxy, not an object representing the entire stack trace or every Java operation in the JVM.

Short example:

```java
@Aspect
@Component
public class OrderAuditAspect {
    @Before("execution(* demo.joinpoint.OrderService.place(..))")
    public void beforePlace(JoinPoint joinPoint) {
        System.out.println("method=" + joinPoint.getSignature().getName());
        System.out.println("args=" + Arrays.toString(joinPoint.getArgs()));
    }
}
```

This is a **fragment** for understanding the API: it needs imports, a target Spring bean, Spring AOP infrastructure, and a consumer calling the target through the proxy. With the call `place("ORD-7", 2)`, `getSignature().getName()` returns `"place"`, and `getArgs()` describes the arguments `["ORD-7", 2]` in parameter order.

**Focus:** this covers how to use `JoinPoint` in a **Spring Aspect**, not general AOP theory or full AspectJ bytecode weaving. Spring AOP's `JoinPoint` only appears in advice when a **method execution on a Spring-managed bean** has been intercepted by a proxy and matched by a pointcut.

## 2. Diagram: where is the context created?

```text
A consumer
      |
      | orderOperations.place("ORD-7", 2)
      v
Spring AOP proxy
      |
      | check advisor / pointcut
      v
@Before advice receives JoinPoint
      |
      +-- getArgs()       -> ["ORD-7", 2]
      +-- getSignature()  -> method info for place(...)
      +-- getThis()       -> Spring AOP proxy object
      +-- getTarget()     -> OrderService target object
      |
      v
Target OrderService.place("ORD-7", 2)
      |
      v
Caller receives result
```

Milestones to distinguish:

- The arguments of the method call expression have already been **evaluated by Java before** the call reaches the proxy. `getArgs()` does not tell you which expression produced an argument in the source code.
- Spring AOP creates the advice context within the flow of an **intercepted method execution**. It does not create a new `JoinPoint` for internal `this.someMethod()` calls that bypass the proxy.
- `JoinPoint` provides **invocation information at the proxy boundary**. It does not directly provide the controller name, source file, or Java line number where the caller wrote the invocation.
- If no aspect/advice applies, the target can still execute, but there is no advice to receive a `JoinPoint`.

For example, a call like `new OrderService().place(...)` creates a Java object outside the Spring container; it has no automatic Spring AOP proxy, so the advice above does not run.

## 3. Four core APIs

| `JoinPoint` API | Information obtained | Notes in Spring |
| --- | --- | --- |
| `getArgs()` | Positional array of invocation arguments | May contain `null`, primitive wrappers, DTOs, or sensitive objects; not source variable names |
| `getSignature()` | Description of the advised method | Cast to `MethodSignature` when you need return type, parameter types, or `Method` |
| `getThis()` | **Spring AOP proxy** representing the call | With a JDK proxy, it usually implements the interface but is not an instance of the target concrete class |
| `getTarget()` | **Target object** behind the proxy | The business object; can be `null` in some special target-source cases; do not invoke the target directly if you want advice |
| `getKind()` | Join point kind, typically `method-execution` in Spring AOP | Not the operation name or caller name |
| `toShortString()`, `toLongString()` | String description of the join point | Useful for debugging; do not treat output as a stable log schema |
| `getStaticPart()` | Static part of the join point | Rarely needed in business advice; not the caller's Java stack frame |
| `getSourceLocation()` | AspectJ `JoinPoint` source-location interface | **Do not use as a reliable caller identifier**; Spring proxies do not provide call-site source tracking equivalent to weaving |

**Specifically:** the `JoinPoint.getTarget()` method does not mean returning an "entry point into advice". If you use `joinPoint.getTarget()` to call another method on the target, you can intentionally **bypass the Spring AOP proxy**. If you need bean collaboration to go through Spring AOP, inject the appropriate Spring bean.

## 4. Reading arguments with `getArgs()`

### 4.1. Array positions correspond to method parameters

Consider a business method:

```java
public String place(String orderId, int quantity) {
    return "RCPT-" + orderId + "-" + quantity;
}
```

Inside advice:

```java
Object[] args = joinPoint.getArgs();
String orderId = (String) args[0];
int quantity = (Integer) args[1];
```

This fragment is only valid if the pointcut has restricted matches to a method with exact parameters `(String, int)`. For primitive `int`, the corresponding element in `Object[]` is represented by the `Integer` wrapper. Do not assume the array always has enough elements: a no-arg method returns an empty array, and a broad pointcut can match methods with different signatures.

A debug-only approach:

```java
System.out.println(Arrays.toString(joinPoint.getArgs()));
```

This statement requires importing `java.util.Arrays`; its output depends on each object's `toString()`. It can accidentally print secrets or trigger expensive logic inside `toString()`. The runnable example in section 8 uses non-sensitive test values.

### 4.2. `getArgs()` does not reveal **source parameter names**

From `getArgs()` you know the values `"ORD-7"` and `2`, but you **do not know** whether the caller wrote `place(orderId, quantity)` or `place("ORD-" + i, 1 + 1)`. The parameter names `orderId` and `quantity` are metadata of the method definition; they are not in the argument array.

To inspect parameter types and reflection metadata, use `MethodSignature`. To reliably see **parameter names** via reflection, appropriate compiler flags/metadata are needed (for example `-parameters`); if missing, you may only get generic names or no metadata at all.

### 4.3. With broad pointcuts, avoid blind casting

```java
@Before("execution(* demo.joinpoint..*Service.*(..))")
public void unsafe(JoinPoint jp) {
    String orderId = (String) jp.getArgs()[0]; // Can fail.
}
```

In the code above, a no-arg method causes `ArrayIndexOutOfBoundsException`; a method whose first parameter is `Long` can cause `ClassCastException`. Only cast after the expression or runtime checks actually confirm the signature.

Safer observation example:

```java
Object[] args = jp.getArgs();
System.out.println("argument count=" + args.length);
if (args.length > 0 && args[0] instanceof String first) {
    System.out.println("first argument length=" + first.length());
}
```

This snippet assumes `jp` is a `JoinPoint` argument of the advice. Even when the types are valid, before logging, check whether the data is a token, password, email, account number, address, or other sensitive information.

### 4.4. Should you reassign elements of `getArgs()`?

Do not use:

```java
jp.getArgs()[0] = "FORCED"; // Not a contract to replace target's argument.
```

expecting the target to automatically receive the new argument. In Spring AOP, `getArgs()` is for **observation**; the implementation may return a copy/snapshot. When you truly need to adjust arguments before continuing the invocation, use `@Around` with `ProceedingJoinPoint.proceed(Object[] args)` and respect the exact parameter count and types.

Avoid mutating mutable DTOs directly just for logging; even when the array itself is separate, the object referenced inside can be the business layer's mutable instance.

## 5. Reading the signature with `getSignature()`

`joinPoint.getSignature()` has the general type `org.aspectj.lang.Signature`. For a method-execution join point in Spring AOP, you can cast it to `org.aspectj.lang.reflect.MethodSignature` to access method-specific APIs.

```java
MethodSignature signature = (MethodSignature) jp.getSignature();

String name = signature.getName();
Class<?> returnType = signature.getReturnType();
Class<?>[] parameterTypes = signature.getParameterTypes();
Method method = signature.getMethod();
```

The snippet above is a fragment inside advice and needs these imports:

```java
import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.reflect.MethodSignature;
import java.lang.reflect.Method;
```

The fields/methods:

- `getName()`: method name, for example `place`.
- `getReturnType()`: the **declared** return type, for example `String.class` or `int.class`, not the actual return value.
- `getParameterTypes()`: the declared parameter types in order; distinct from the runtime types in `getArgs()`.
- `getMethod()`: the reflective method of the invocation known to Spring AOP. **Not always synonymous with the method declaration directly on the implementation class** if a JDK interface proxy is used.
- `getDeclaringTypeName()`: declaring type information of the signature, which can be the interface type in the case of a JDK proxy; do not use it to guess the caller class.

### 5.1. Interface method and implementation method can differ

```java
public interface OrderOperations {
    String place(String orderId, int quantity);
}

@Service
public class OrderService implements OrderOperations {
    @Override
    public String place(String orderId, int quantity) {
        return "RCPT-" + orderId + "-" + quantity;
    }
}
```

When a caller holds a **JDK dynamic proxy** under the `OrderOperations` type, the invocation signature can refer to the method declared on the interface, even though the execution logic resides in `OrderService.place(...)`.

If your goal is to find an annotation or the specific implementing method, Spring provides a helper:

```java
MethodSignature sig = (MethodSignature) jp.getSignature();
Method invoked = sig.getMethod();

Object target = jp.getTarget();
if (target != null) {
    Method specific = AopUtils.getMostSpecificMethod(
            invoked, target.getClass());
    System.out.println(specific.getDeclaringClass().getSimpleName());
}
```

This is an illustrative fragment requiring `import org.springframework.aop.support.AopUtils`. With bridge/generic methods and complex annotation mappings, you must also consider the lookup rules of the relevant framework rather than just reading a single annotation from `sig.getMethod()`.

### 5.2. A signature is **not** the caller's source address

The method signature tells you **which method the invocation is executing**. It does **not** tell you:

- which Java class called that method before entering the proxy;
- the source file and call-site line in another controller/service;
- the HTTP endpoint, user identity, request ID, or transaction ID;
- where the argument objects were created.

If needed, these values must come through separate mechanisms: explicit request context, correlation IDs, tracing/observation infrastructure, or business parameters. Do not force `getSignature().getDeclaringTypeName()` into meaning "caller class".

## 6. `getThis()` and `getTarget()`: distinguishing the Spring proxy from the target bean

In Spring AOP, these two methods are **semantically different**:

```java
Object proxy = jp.getThis();
Object target = jp.getTarget();
```

- `proxy` is the **Spring AOP proxy** through which the current call passes.
- `target` is the **Spring AOP target** being advised; in normal cases it is the real service instance.
- `proxy == target` **is not guaranteed to be true**. With an actual AOP proxy, they are typically two different Java objects.
- `getTarget()` can be `null` in special cases with no target object; infrastructure/generic aspect code must tolerate that possibility.
- A JDK proxy implements interfaces and is not a subclass of the concrete class. For example, `proxy instanceof OrderOperations` is true while `proxy instanceof OrderService` is false.
- A CGLIB proxy is typically a subclass assignable to the concrete class if the target class is not final; it is still a **proxy** with an interceptor chain.

**Do not call a business method directly on `getTarget()` to try to trigger advice.** A target invocation not going through the proxy will not create a new interception. If you genuinely need to invoke an advised operation, designing the consumer to receive another bean via constructor injection is the preferred approach; do not abuse calling the proxy back from an aspect.

### 6.1. `getThis()` is not the caller object either

The name `getThis()` easily misleads you into thinking it returns the Java `this` of the class calling the service. In Spring AOP, it returns the **proxy object of the bean currently being intercepted**, not the controller, workflow, or REST endpoint calling this bean.

Example:

```text
CheckoutController -> OrderOperations proxy -> OrderService target
                           |                      |
                   jp.getThis()             jp.getTarget()
```

There is no universal `JoinPoint.getCaller()` API in Spring AOP.

### 6.2. What to do when you need source/caller provenance?

"**Supported call source**" in a Spring proxy practically means you can identify the method, arguments, proxy, and target involved. It does not mean Spring `JoinPoint` automatically collects the call-site location.

If you want to know which request flow led to the service, you should:

- Establish a **trace/span/correlation ID** at the request boundary and propagate it through the appropriate observability infrastructure.
- If you need the caller's business identity, pass explicit caller information in the domain API or a secured context.
- With Spring MVC, extract request route metadata in the appropriate interceptor/filter/web layer instead of guessing from the service's method signature.
- With thread hops/async, account for proper context propagation configuration.
- If you are only debugging, a stack trace can give clues, but it is not a durable API: proxies, inlining, threads, async, or refactoring alter the call stack.

A `SourceLocation` in the AspectJ API **should not be treated as the location where the consumer called the service** in Spring AOP. Understand that Spring AOP primarily observes **execution join points**, not `call(...)` source join points woven at the call site.

## 7. Advice parameter declaration rules

### 7.1. `JoinPoint` goes first in regular advice

Advice types such as `@Before`, `@After`, `@AfterReturning`, and `@AfterThrowing` can accept `org.aspectj.lang.JoinPoint` as their **first parameter**:

```java
@Before("execution(* demo.joinpoint.OrderService.place(..))")
public void audit(JoinPoint jp) {
    System.out.println(jp.getSignature().getName());
}
```

You do not need to declare `JoinPoint` on the business method; Spring supplies it automatically to the advice when an execution matches the pointcut. You cannot inject `JoinPoint` as a singleton bean and use it to infer every ongoing call; it is the invocation context inside advice.

### 7.2. `@Around` must use `ProceedingJoinPoint`

For `@Around`, the first parameter must be `ProceedingJoinPoint`, a subtype of `JoinPoint` that provides `proceed()`:

```java
@Around("execution(* demo.joinpoint.OrderService.place(..))")
public Object around(ProceedingJoinPoint pjp) throws Throwable {
    System.out.println("calling " + pjp.getSignature().getName());
    return pjp.proceed();
}
```

The condition for the real target to run is that the advice calls `proceed()`. If you forget `return pjp.proceed()`, the return value or control flow to the caller can be wrong. Meanwhile, regular `JoinPoint` has no `proceed()`; `@Before` cannot proactively skip the invocation and return an alternative result like `@Around` can.

### 7.3. When should you bind parameters directly instead of using `Object[]`?

If the pointcut selects only a method with a single `String` argument:

```java
@Before(
    value = "execution(* demo.joinpoint.OrderService.cancel(..))"
          + " && args(orderId)",
    argNames = "orderId"
)
public void beforeCancel(JoinPoint jp, String orderId) {
    System.out.println("cancel length=" + orderId.length());
}
```

This is an illustrative fragment requiring `OrderService.cancel(String)` to exist with exactly one argument. `args(orderId)` both checks and binds the argument according to pointcut rules, while `argNames="orderId"` describes the binding name when the compiler does not retain suitable parameter metadata. Spring does not require manually casting `jp.getArgs()[0]` in this case.

**Do not merge this snippet into the project in section 8**, because that project does not define `cancel(..)`; this is a separate API extension example.

With multiple parameters, declare names and order matching the expression, such as `args(orderId, quantity)`; do not assume `argNames` or Java parameter names are always present in bytecode.

### 7.4. Return value and thrown exception are different contexts

`JoinPoint.getArgs()` returns input arguments. It does **not** return the target's result or an as-yet-unthrown exception. Spring supports:

- `@AfterReturning(pointcut=..., returning="result")` to bind the return value when the method completes normally;
- `@AfterThrowing(pointcut=..., throwing="ex")` to bind a matching exception;
- `@Around` to access the outcome of `proceed()` inside try/catch/finally.

`getSignature()` tells you the **declared return type**; it is not equivalent to the **actual returned value**.

## 8. Standalone runnable example: reading signature, args, proxy, and target

The example uses **Java 17 + Maven + Spring Framework 6.2.x**, without Spring Boot. The target has an interface, so with `@EnableAspectJAutoProxy(proxyTargetClass=false)` Spring prefers a **JDK dynamic proxy**. The aspect only advises `place(String,int)`; another method does not match, a `this.place()` call bypasses it, and an object created with `new` does not go through the Spring proxy.

### 8.1. Directory structure

```text
spring-joinpoint-context/
├── pom.xml
└── src/main/java/demo/joinpoint/
    ├── AppConfig.java
    ├── OrderOperations.java
    ├── OrderService.java
    ├── ContextAspect.java
    └── Main.java
```

### 8.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-joinpoint-context</artifactId>
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

### 8.3. `AppConfig.java`

```java
package demo.joinpoint;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackageClasses = AppConfig.class)
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class AppConfig {
}
```

`@ComponentScan` discovers the Spring service and aspect. `@EnableAspectJAutoProxy` enables the auto-proxy creator. With the `OrderOperations` interface and this configuration in plain Spring Framework, the service bean's proxy is a JDK dynamic proxy.

### 8.4. `OrderOperations.java`

```java
package demo.joinpoint;

public interface OrderOperations {
    String place(String orderId, int quantity);
    String health();
    void batch();
}
```

The consumer contract consists only of public interface methods, compatible with a JDK dynamic proxy.

### 8.5. `OrderService.java`

```java
package demo.joinpoint;

import org.springframework.stereotype.Service;

@Service
public class OrderService implements OrderOperations {
    @Override
    public String place(String orderId, int quantity) {
        System.out.println("[target] place " + orderId + " qty=" + quantity);
        return "RCPT-" + orderId + "-" + quantity;
    }

    @Override
    public String health() {
        System.out.println("[target] health");
        return "UP";
    }

    @Override
    public void batch() {
        System.out.println("[target] batch");
        this.place("INNER", 1); // Target self-invocation: bypasses AOP proxy.
    }
}
```

The pointcut below applies only to `place(..)` when the call **goes through the proxy**. `health()` and `batch()` are not in the pointcut. `this.place("INNER", 1)` still runs as a normal Java method, but without its own before advice.

### 8.6. `ContextAspect.java`

```java
package demo.joinpoint;

import java.util.Arrays;
import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.aspectj.lang.reflect.MethodSignature;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class ContextAspect {
    @Before("execution(* demo.joinpoint.OrderService.place(..))")
    public void observe(JoinPoint jp) {
        MethodSignature signature = (MethodSignature) jp.getSignature();

        System.out.println("[advice] method=" + signature.getName());
        System.out.println("[advice] args=" + Arrays.toString(jp.getArgs()));
        System.out.println("[advice] returnType="
                + signature.getReturnType().getSimpleName());

        System.out.println("[advice] proxyImplementsPort="
                + (jp.getThis() instanceof OrderOperations));

        Object target = jp.getTarget();
        System.out.println("[advice] targetClass="
                + (target == null ? "<none>"
                                  : target.getClass().getSimpleName()));
    }
}
```

Specific observations:

- `getSignature()` describes the `place` method; cast to `MethodSignature` to read the declared return type.
- `getArgs()` holds two values in order, with the number `2` boxed in the array.
- `getThis() instanceof OrderOperations` is true for a JDK proxy implementing the interface.
- `getTarget()` is the `OrderService` instance, so `targetClass=OrderService`.
- The aspect only observes; it does not mutate args or call the target/proxy method again.

### 8.7. `Main.java`

```java
package demo.joinpoint;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            OrderOperations orders = context.getBean(OrderOperations.class);

            System.out.println("[main] jdkProxy="
                    + AopUtils.isJdkDynamicProxy(orders));

            System.out.println("[caller] receipt="
                    + orders.place("ORD-7", 2));

            System.out.println("[caller] health="
                    + orders.health());

            orders.batch();

            OrderOperations unmanaged = new OrderService();
            System.out.println("[caller] rawReceipt="
                    + unmanaged.place("RAW", 1));
        }
    }
}
```

Run in the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.joinpoint.Main
```

**Stdout output from the `System.out` calls in the example** (ignoring any extra Maven/Spring logs):

```text
[main] jdkProxy=true
[advice] method=place
[advice] args=[ORD-7, 2]
[advice] returnType=String
[advice] proxyImplementsPort=true
[advice] targetClass=OrderService
[target] place ORD-7 qty=2
[caller] receipt=RCPT-ORD-7-2
[target] health
[caller] health=UP
[target] batch
[target] place INNER qty=1
[target] place RAW qty=1
[caller] rawReceipt=RCPT-RAW-1
```

### 8.8. Log order analysis

1. `getBean(OrderOperations.class)` retrieves the Spring AOP bean reference, using a JDK proxy, so the first line is `jdkProxy=true`.
2. `orders.place("ORD-7",2)` enters the proxy and the pointcut matches; Spring creates a `JoinPoint` for the advice. The advice prints metadata **before** the target.
3. `getArgs()` returns an array containing `String "ORD-7"` and `Integer 2`; `Arrays.toString(...)` displays `[ORD-7, 2]`.
4. `MethodSignature.getReturnType()` returns `String.class`; the target method then returns `"RCPT-ORD-7-2"` to the caller.
5. `orders.health()` does not match the pointcut and only prints the target line.
6. `orders.batch()` does not match the pointcut. Inside the target, `this.place("INNER",1)` bypasses the Spring proxy; there is **no** advice output for INNER.
7. `new OrderService().place("RAW",1)` calls an object outside the container; there is a target line but no advice. The caller still receives the Java method's return value.

The example uses **a single before advice**, so there is no need to reason about ordering across multiple advisors. It does not use `getSourceLocation()` to try printing a "caller file", because Spring proxies do not guarantee reliable call-site metadata.

## 9. When you want the call source: distinguish four kinds of "source"

The word "source" can mean very different things:

| Kind of information | How does Spring `JoinPoint` handle it? | Appropriate approach |
| --- | --- | --- |
| Method **being advised** | Yes: `getSignature()`, `MethodSignature` | Use method name, return/param types; add target type if needed |
| **Proxy object receiving the invocation** | Yes: `getThis()` | Distinguish JDK/CGLIB; do not treat it as the caller object |
| **Target object executing the call** | Yes: `getTarget()` | Can use target class for metadata; do not call directly if advice is needed |
| **Java caller object**, file/line where method was called | No reliable standard Spring `JoinPoint` API for call site | Tracing, explicit context, stack trace for debugging only |
| **HTTP/request origin** | Not built into `JoinPoint` | Spring web filter/interceptor, request context/observation along the flow |
| **User/principal** | Cannot be inferred solely from signature/args | Spring Security context or appropriate explicit application context |
| **Transaction/tracing context** | Not identical to `JoinPoint` | Spring transaction/observability APIs in the proper module |

In Spring AOP, `getThis()` represents the proxy **on the callee side**, not the "this" object at the caller. `getTarget()` represents the bean executing the business logic. If a request starts at `CheckoutController` and reaches `OrderService.place()`, the natural metadata of `JoinPoint` is still `OrderService`'s method execution, not the controller's name.

### 9.1. Why shouldn't you use a stack trace as a business key?

A Java stack trace shows the frames present at a given moment, but:

- Proxy layers and interceptors can add many infrastructure frames.
- Async execution, scheduling, reactive pipelines, and thread pools mean caller logic is no longer on the current stack.
- Method refactoring, compiler optimizations, and generated proxy classes can change frames.
- Stack capture is expensive if performed on every request and can expose implementation details.

Use stack traces when debugging errors; do not assign them as a stable "caller source" for auditing or authorization.

### 9.2. Should you use `getSourceLocation()`?

`JoinPoint` in the AspectJ API has a `getSourceLocation()` method. However, Spring AOP **does not weave call-site bytecode**, so it lacks sufficient information to generally provide the file/line **where a consumer called a bean**. Do not use `getSourceLocation()` as the source of truth for controller, caller ID, or call location.

If business requirements truly need this information, design trace/span ID infrastructure or explicit context parameters. If you want to debug the implementation method, reflection from `MethodSignature` is usually more meaningful than relying on an out-of-scope "source location".

## 10. Binding data into advice: typed binding and caveats

### 10.1. Binding via `args(...)` is more type-safe

For a method:

```java
public String place(String orderId, int quantity) { /* ... */ }
```

a corresponding advice can bind the two values:

```java
@Before(
    value = "execution(* demo.joinpoint.OrderService.place(..))"
          + " && args(orderId, quantity)",
    argNames = "orderId,quantity"
)
public void auditArgs(JoinPoint jp, String orderId, int quantity) {
    System.out.println("orderId length=" + orderId.length());
    System.out.println("quantity=" + quantity);
}
```

This is a fragment that **replaces** the `observe(...)` advice; both should not be registered together if you only want one log output per invocation. `JoinPoint` is the special first parameter; binding `orderId` and `quantity` is handled by Spring `@AspectJ` according to the expression, matching the Java signature.

If the names in `argNames` are wrong or do not match the variables in the pointcut/advice, the context can fail at configuration time. When a pointcut spans multiple method overloads, verify the types/argument positions and test thoroughly.

### 10.2. Annotation binding does not automatically infer caller values

For example, a custom `@Audited` annotation can be used with `@annotation(...)` to select methods. That helps find methods **annotated with it** according to Spring pointcut rules, but it does not provide Java caller source info. The annotation must have runtime retention, be placed appropriately, and be recognized by the aspect. When using a JDK proxy, the method on the interface and the implementation method can differ, so check the actual annotation lookup mechanism.

### 10.3. Do not store `JoinPoint` in a singleton field

An `@Component` aspect is typically created as a singleton Spring bean. If you write:

```java
private JoinPoint lastJoinPoint; // Should not store invocation state long-term.

@Before("execution(* demo.joinpoint..*Service.*(..))")
public void before(JoinPoint jp) {
    lastJoinPoint = jp;
}
```

there will be a **race condition** risk when multiple threads process invocations concurrently. `JoinPoint` and `getArgs()` belong to a single invocation, not shared state. Use local variables, pass data to concurrency-safe telemetry, or use a context scoped to the lifecycle of a request.

## 11. Spring AOP limitations that directly affect JoinPoint information

- Standard Spring AOP intercepts **method executions** on Spring-managed beans, not every method call in the JVM. `call(...)`, field access, and constructor join points from full AspectJ are not automatically supported by Spring proxies alone.
- With a **JDK proxy**, only public interface methods exposed by the proxy can be called by consumers through the proxy reference. Public methods present only on the concrete implementation do not appear on the JDK interface proxy.
- With a **CGLIB proxy**, methods must be overridable by a subclass; private/final methods have limitations. Final classes cannot be subclassed by CGLIB.
- **Self-invocation** such as `this.place()` bypasses the proxy; advice does not create a separate `JoinPoint` for that call.
- An object created with `new` outside Spring is not automatically AOP-proxied; there is no advice context just because another class with the same name is a bean.
- `@Aspect` alone does not register the aspect as a Spring bean; `@Component` or `@Bean` configuration is needed, along with AOP activation.
- `JoinPoint.getThis()`/`getTarget()` describe the proxy/target **of the matched invocation**, not the dependency graph or the entire Spring container.
- `@Before` sees input arguments but not the target's return value or exception. To get the outcome, use the appropriate advice type or logic in `@Around`.
- Some other AOP features such as introduction interfaces can cause the proxy to expose additional interfaces; do not cast directly to the implementation when using a JDK proxy.
- Multiple application contexts can have different proxies/aspects; inspect the actual reference held by the consumer before concluding which context a `JoinPoint` belongs to.

## 12. Troubleshooting checklist

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| `@Before` does not receive `JoinPoint` | Advice does not match, aspect is not registered as a bean, or call bypasses proxy | Check `@Aspect @Component`, `@EnableAspectJAutoProxy`, `AopUtils`, and call path |
| `getArgs()[0]` throws an error | Method has no parameters or pointcut matches multiple signatures | Check array length, class, and expression |
| `ClassCastException` when casting arg | Runtime argument type differs from assumption | Use `instanceof` or properly typed `args(...)` binding |
| `getSignature().getName()` is right but `getMethod` does not point to implementation | JDK proxy knows the interface method | Use target class + `AopUtils.getMostSpecificMethod(...)` when needed |
| `getThis().getClass()` differs from target class | Spring AOP returns the proxy object | This is normal; use `AopUtils` to determine proxy type |
| `getTarget()` differs from `getThis()` | Target and proxy are two different references | Do not compare identity to decide an error |
| Aspect prints service name, not controller name | Signature describes callee method execution | Use request tracing/correlation IDs; do not treat `JoinPoint` as a caller API |
| `getSourceLocation()` does not give call-site line | Spring AOP does not weave caller sites | Avoid depending on it; trace at the request boundary |
| `getArgs()` prints exposed token/password | Uncontrolled logging of sensitive data | Redact/allowlist metadata; do not log full args |
| Advice modifies args but target receives old values | Assigning into `getArgs()` array is not an invocation-control contract | `@Around` and `proceed(newArgs)` if truly needed |
| `this.method()` has no advice log | Self-invocation bypasses proxy | Extract to another Spring bean / change call boundary |
| `new Service().method()` has no advice | Object outside the container | Inject the Spring-managed bean |
| Method is advised twice | Multiple advisors or call passes through proxy multiple times | Check order/pointcut; avoid duplicate aspect registration |
| `JoinPoint` stored in a field produces wrong data | Singleton aspect shares state across threads | Keep invocation data in local variables |
| Replacing `JoinPoint` with `ProceedingJoinPoint` in `@Before` | Wrong advice-type contract | Only use `ProceedingJoinPoint` as the required first param for `@Around` |

**Quick verification sequence:**

1. Verify **the target and aspect belong to the Spring context** and AOP is enabled.
2. Obtain the **actual bean reference** from DI/context, use `AopUtils.isAopProxy(...)`, and check JDK/CGLIB.
3. Check whether the pointcut matches the **method execution** and whether the caller goes through the proxy.
4. Use `getSignature()` first to identify the method, then handle `getArgs()` based on declared types.
5. If you need the implementation annotation/method, resolve the specific method against the target class, paying attention to interfaces/generics.
6. Use `getThis()`/`getTarget()` properly to mean the proxy and callee target.
7. If caller/request origin is required, use real tracing/context rather than inferring from signature or `getSourceLocation`.
8. Add an integration test proving exactly which methods are advised, what data is logged, and which cases bypass the proxy.

## 13. Review questions

**1. What does `JoinPoint.getArgs()` contain?** The array of runtime invocation values in method parameter order; it does not contain Java variable names at the call site or call-site metadata.

**2. Is `getThis()` the caller object?** No. In Spring AOP, it is the **AOP proxy** of the bean currently being intercepted.

**3. Are `getTarget()` and `getThis()` always the same?** No. Proxy and target are usually two different objects; `getTarget` can sometimes be null in special target cases.

**4. To find a method's `String` return type, which API do you use?** Cast `jp.getSignature()` to `MethodSignature` and call `getReturnType()`. This is the declared type, not the actual returned value.

**5. Can you tell which file and line in a Java controller called the service using `getSignature()`?** No. The signature describes the method execution on the callee side; dedicated tracing or context is appropriate for determining the request/caller source.

**6. Does `getArgs()[0] = anotherValue` change the argument the target receives?** Do not rely on that in the Spring AOP contract. If you really need to change inputs, use around advice and `proceed(Object[])` with the matching signature.

**7. Why does `this.place()` not produce its own advice `JoinPoint`?** The target calls its own method directly, bypassing the Spring AOP proxy; no new method interception occurs.

**8. Does `@Around` take `JoinPoint` just like `@Before`?** It requires `ProceedingJoinPoint` as its first parameter; this subtype provides `proceed()`.

**9. How can you receive typed arguments more safely than array casting?** Bind parameters with `args(name)` in the pointcut and parameters in the advice, along with appropriate metadata/`argNames`.

**10. Should you store `JoinPoint` in a field of a singleton aspect?** No. That is per-invocation state; a shared field creates race conditions and risks data leakage.

## Official documentation references

- [Spring Framework 6.2 — Declaring Advice: Access to the Current JoinPoint](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html)
- [Spring Framework 6.2 — Pointcuts and execution join points](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html)
- [Spring Framework 6.2 — Proxying Mechanisms and self-invocation](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
- [Spring Framework 6.2 API — MethodInvocationProceedingJoinPoint (getThis/getTarget)](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/aop/aspectj/MethodInvocationProceedingJoinPoint.html)
- [Spring Framework 6.2 — @AspectJ annotation support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj.html)
- [Spring Framework 6.2 — Introduction to AOP proxies](https://docs.spring.io/spring-framework/reference/6.2/core/aop/introduction-proxies.html)
