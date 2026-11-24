# Limitations of `@AfterReturning` When Attempting to Replace the Returned Object in Spring AOP

## 1. The Problem: You Have the Return Value, but Can You Replace the Object the Caller Receives?

In Spring AOP, `@AfterReturning` is **advice that runs when a selected method execution finishes normally**. It is commonly used to log results, audit, update metrics, or inspect the returned value.

Example:

```java
@AfterReturning(
    pointcut = "execution(* com.example.order.OrderService.find(..))",
    returning = "result",
    argNames = "result"
)
public void afterFind(Object result) {
    // Observe the result from the advised method.
}
```

This is a **method fragment** that must be placed inside a Spring-managed `@Aspect` class. The `returning = "result"` attribute binds the value returned by the method to the advice's `result` parameter.

An easy-to-confuse question: if the advice writes `result = new Result(...)`, does the caller receive the new object?

**No.** The Spring Framework documentation explicitly states that `@AfterReturning` **cannot return a completely different reference** to the caller. The bound parameter only lets the advice **observe the returned value**; reassigning the local Java variable inside the advice does not replace the return value held in the interceptor chain.

However, if the return value is a **mutable object** and the advice mutates the state of that exact object, the caller can still see the altered state because the advice and the caller reference the same object. That is **mutation of the returned object**, not **replacing the returned object**. This distinction is critical when designing Spring Aspects.

If the true requirement is to **replace the result object/reference**, use `@Around` (or redesign the return logic in a service/mapper), because `@Around` can invoke `ProceedingJoinPoint.proceed()` and then **return a different object** to the caller.

This lesson focuses strictly on **Spring `@AspectJ` advice on Spring-managed beans through proxies**, within the Spring Aspect scope. It does not cover standalone AspectJ weaving mechanisms.

## 2. Comparing Three Similar-Looking Operations

Suppose the target method returns:

```java
ResultBox returned = service.load("A");
```

Inside `@AfterReturning`:

| Operation | Example in advice | What does the caller see? |
| --- | --- | --- |
| **Read the result** | `System.out.println(result)` | The object/reference returned by the target, unchanged by reading. |
| **Mutate a mutable object's state** | `result.setStatus("checked")` | May see the new `status` on the **exact same original object**. |
| **Reassign the parameter variable** | `result = new ResultBox("other")` | **Does not receive the new object**; the assignment only updates the advice's local variable. |
| **Try `return result` from `@AfterReturning`** | Change advice from `void` to returning an object hoping to replace the result | Not Spring `@AfterReturning`'s mechanism for replacing return values; should not be used. |
| **`@Around` returns a new object** | `return new ResultBox("other")` | Caller receives the object returned by `@Around`, provided the method contract and chain permit it. |

Separate two concepts:

- **Reference identity**: `a == b` checks whether both refer to the exact same Java object.
- **Object state**: `a.getStatus()` reflects the current data inside the object.

An `@AfterReturning` can affect **state** if the object is mutable; it **has no authority to replace the final reference** by reassigning the advice parameter.

## 3. When Does Spring `@AfterReturning` Run?

Typical flow of a call through a Spring AOP proxy:

```text
Calling bean / ApplicationContext client
                 |
                 v
         Spring AOP proxy
                 |
          advisor chain
                 |
                 v
         target business method
                 |
                 +--> return resultRef (normal completion)
                 |
                 v
        @AfterReturning advice
         |       |       |
         |       |       +-- log/audit/metric
         |       +---------- may mutate resultRef if object is mutable
         +------------------ local assignment does NOT replace returned ref
                 |
                 v
            caller receives resultRef
```

This diagram shows a matching `@AfterReturning` in a simple advice chain. In applications with multiple `@Around`, `@AfterReturning`, or other advisors, **the order and final object can be changed by an outer `@Around`**. That **does not alter** the limitation of `@AfterReturning` itself.

Conditions to remember:

1. **Runs only when the selected method returns normally.** If the target method throws an exception outward, `@AfterReturning` is not the callback for that case. If you need to handle exceptions, see `@AfterThrowing` or `@Around` depending on requirements.
2. **Takes effect only if the call goes through the proper Spring AOP proxy.** `new Service().run()` or self-invocation `this.run()` typically bypasses the advice.
3. **`@AfterReturning` can be declared without binding the return value.** If you need to know the method succeeded without needing the result, use `@AfterReturning("pointcut...") public void afterSuccess()`.
4. **Binding via `returning` imposes a type constraint.** The more specific the advice parameter, the narrower the set of return values/method executions that can match.
5. **Replacing a return value** and **observing a return value** are two distinct responsibilities; choose the minimal advice kind that meets the goal.

## 4. How Does `returning` Bind the Argument and What Are Common Limits?

Spring `@Aspect` example:

```java
@AfterReturning(
    pointcut = "execution(public * com.example.report.ReportService.load(..))",
    returning = "result",
    argNames = "result"
)
public void observe(ResultBox result) {
    System.out.println(result.getValue());
}
```

Meaning:

- `pointcut`: selects the advised method execution.
- `returning`: name of the **parameter in the advice method**, here `result`.
- `argNames`: specifies the binding name explicitly so Spring does not rely solely on compiler parameter metadata.
- `ResultBox`: advice parameter type; Spring uses it to constrain compatible return values.
- `observe(...)`: runs **after normal return**; does not receive `ProceedingJoinPoint` and has no `return` replacement mechanism.

This snippet is only a fragment: it requires imports, the `ResultBox` class, the `ReportService` class, `@Aspect`, and Spring configuration.

### 4.1. Binding with `Object` vs. a Specific Type

```java
@AfterReturning(
    pointcut = "execution(* com.example.report.ReportService.*(..))",
    returning = "value",
    argNames = "value"
)
public void observeAnything(Object value) {
    // Read results of matching returning calls.
}
```

compared with:

```java
@AfterReturning(
    pointcut = "execution(* com.example.report.ReportService.*(..))",
    returning = "box",
    argNames = "box"
)
public void observeBoxes(ResultBox box) {
    // Applies only when the result has a ResultBox-compatible type.
}
```

**These two advice fragments are alternative options, not meant to be registered together.** Binding is not merely casting and hoping it is safe: the advice parameter's type affects matching. With `void`, `null`, primitive boxing, or generic return types, run an integration test on your actual Spring version rather than assuming every return type binds identically.

### 4.2. The `returning` Name Is Not a Variable Name in the Target

Target:

```java
public ResultBox load() {
    ResultBox internal = new ResultBox("value");
    return internal;
}
```

Aspect:

```java
@AfterReturning(
    pointcut = "execution(* com.example.report.ReportService.load(..))",
    returning = "answer",
    argNames = "answer"
)
public void after(ResultBox answer) {}
```

This is completely valid in terms of **naming**: `answer` does not have to match `internal`. The `returning` attribute only needs to match the **advice's** parameter, and the bound value comes from the object returned by the target.

### 4.3. Cannot Fix by Changing the Advice's Return Type

An incorrect attempt:

```java
@AfterReturning(
    pointcut = "execution(* com.example.report.ReportService.load(..))",
    returning = "result"
)
public ResultBox after(ResultBox result) {
    return new ResultBox("replacement");
}
```

**This is an illustrative anti-pattern, not recommended runnable code.** The return value of an `@AfterReturning` advice method is not used as the return value of the target method. Spring may expect specific signatures; even if the Java method returns `ResultBox`, it **does not provide a reference-replacement contract** like `@Around`.

Declare the advice as `void` and place transformation logic at the proper layer.

## 5. Mutating a Mutable Object Is Completely Different from Replacing the Reference

Suppose a service returns a mutable object:

```java
public final class ResultBox {
    private String value;

    public ResultBox(String value) {
        this.value = value;
    }

    public String getValue() {
        return value;
    }

    public void setValue(String value) {
        this.value = value;
    }
}
```

Target:

```java
ResultBox original = new ResultBox("origin");
return original;
```

Advice:

```java
@AfterReturning(
    pointcut = "execution(* com.example.report.ReportService.load(..))",
    returning = "result",
    argNames = "result"
)
public void after(ResultBox result) {
    result.setValue("changed");          // Mutation: caller can see it.
    result = new ResultBox("new-object"); // Rebinding: caller does NOT receive the new ref.
}
```

These are fragments that can be placed into a complete Spring project. The two operations in the same advice have distinct consequences:

- `setValue("changed")` modifies data **inside the existing instance**.
- `result = new ResultBox(...)` only changes the advice's **local** Java parameter.
- The caller receives the **same object reference from before the mutation**, and `getValue()` can return `"changed"`.
- If the caller also holds a reference to that object elsewhere, that code can see the mutation too; this is shared mutable state, not a "modified copy."

**Being able to mutate does not mean you should mutate.** A shared aspect silently modifying a DTO, entity, or collection can break invariants, corrupt cached data, cause race conditions, and make business logic hard to understand. If policy genuinely requires altering the response, prefer an explicit transformation using `@Around` or a dedicated service/mapper.

### 5.1. Immutable Objects: Reassignment Has Even Less Effect

With `String`, immutable records, or immutable DTOs:

```java
@AfterReturning(
    pointcut = "execution(* com.example.report.ReportService.message(..))",
    returning = "text",
    argNames = "text"
)
public void afterMessage(String text) {
    text = "rewritten:" + text;
}
```

`String` is immutable, so there is no `setValue()` to alter the old object's contents. Reassigning `text` merely creates or points to another `String` within the advice's local scope. **The caller still receives the `String` that the target (or another eligible advisor) chose to return**.

With mutable collections, `list.add(...)` inside `@AfterReturning` can cause the caller to see extra elements; however, `list = new ArrayList<>(...)` does not replace the returned reference. If the collection is unmodifiable/immutable, attempting mutation can even throw an exception. Do not write `@AfterReturning` code mutating data like this under the assumption that every return type is mutable.

## 6. To Replace the Returned Object, Use `@Around`

Per Spring Framework, `@Around` receives **`ProceedingJoinPoint`** and wraps the method call. It can:

1. Execute logic before the method.
2. Call `proceed()` to let the target (or the inner portion of the chain) execute.
3. Observe the returned object.
4. Return **that same object**, a wrapped object, a transformed object, or a replacement object to the caller.

Fragment example:

```java
@Around("execution(* com.example.report.ReportService.load(..))")
public Object replaceResult(org.aspectj.lang.ProceedingJoinPoint pjp)
        throws Throwable {

    ResultBox original = (ResultBox) pjp.proceed();
    ResultBox replacement =
            new ResultBox("wrapped:" + original.getValue());

    return replacement; // Return value seen by the caller.
}
```

Unlike `@AfterReturning`, **the return value of `@Around` is the value the Spring proxy returns to the caller**, provided it satisfies the method contract and outer advisors.

Spring also allows `@Around` to skip calling `proceed()` in intentional cases like a cache hit; however, when the goal is to **transform the method's result**, you normally **must call `proceed()` the right number of times** and handle returns/exceptions explicitly.

### 6.1. Important Constraints of `@Around`

- **Match the return type:** if the method declares return type `ResultBox`, do not return an arbitrary `String` expecting Java callers to work normally. Spring/JVM can throw a type error when the proxy returns an incompatible result.
- **`null` and primitives:** when a method returns a primitive, returning `null` is normally invalid; watch out for boxing/unboxing.
- **Preserve the business contract:** wrapping/transforming responses can change identity, equality, and serialization, altering behavior for caches or API consumers.
- **Exceptions:** `proceed()` can throw `Throwable`. Only alter/swallow exceptions if policy requires it and it has been tested.
- **Go through the Spring proxy:** `@Around` also does not apply automatically to objects created with `new` or self-invocation `this.method()`.
- **`@Around` is not always needed:** if you only log/record metrics after success, keeping `@AfterReturning` is more appropriate and easier to maintain.

## 7. Runnable Java 17+ Example: Proving Identity and Replacement

This example uses Spring Framework **6.1.14**, `aspectjweaver` **1.9.22.1**, Maven, and JDK 17+. These are fixed sample versions; the code uses **Spring proxy-based AOP**, without enabling AspectJ weaving.

It exercises three cases on the **same Spring service proxy**:

1. `loadPlain("A")`: target returns a mutable `ResultBox`; `@AfterReturning` **mutates the object** and then reassigns the local variable. The caller still receives the original reference with altered state.
2. `loadWrapped("B")`: `@Around` calls the target and then **returns a different object**. The caller sees the new reference.
3. `message("C")`: `@AfterReturning` observes a `String` and reassigns the local variable. The caller still receives the original `String`.

### 7.1. Project Structure

```text
spring-after-returning-limit/
├── pom.xml
└── src/main/java/com/example/returnadvice/
    ├── ResultBox.java
    ├── ReportService.java
    ├── ResultAspect.java
    ├── AppConfig.java
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
    <artifactId>spring-after-returning-limit</artifactId>
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

`spring-context` manages the `ApplicationContext` and brings in the compatible Spring AOP dependency for the chosen Spring release; `aspectjweaver` supports parsing/matching `@Aspect` pointcut expressions. No `-javaagent` or AspectJ compiler configuration is needed.

### 7.3. `src/main/java/com/example/returnadvice/ResultBox.java`

```java
package com.example.returnadvice;

public final class ResultBox {
    private String value;

    public ResultBox(String value) {
        this.value = value;
    }

    public String getValue() {
        return value;
    }

    public void setValue(String value) {
        this.value = value;
    }
}
```

`ResultBox` is designed to be **mutable**. This `final` class is a **return value**, not a Spring target bean requiring CGLIB subclassing; making `ResultBox` `final` does not prevent proxying around `ReportService`.

### 7.4. `src/main/java/com/example/returnadvice/ReportService.java`

```java
package com.example.returnadvice;

public class ReportService {
    private ResultBox lastPlain;
    private ResultBox lastWrapped;

    public ResultBox loadPlain(String id) {
        lastPlain = new ResultBox("plain:" + id);
        System.out.println("[TARGET plain] " + lastPlain.getValue());
        return lastPlain;
    }

    public ResultBox loadWrapped(String id) {
        lastWrapped = new ResultBox("source:" + id);
        System.out.println("[TARGET wrapped] " + lastWrapped.getValue());
        return lastWrapped;
    }

    public String message(String id) {
        return "text:" + id;
    }

    public ResultBox rawPlainReference() {
        return lastPlain;
    }

    public ResultBox rawWrappedReference() {
        return lastWrapped;
    }
}
```

The two methods `rawPlainReference()` and `rawWrappedReference()` exist solely for **the experiment comparing references** created by the target; they do not expose the raw target of `ReportService` itself. Real applications should not hold mutable response state in a singleton service if multiple threads/requests can call it concurrently. The example runs sequentially to compare the two references accurately.

### 7.5. `src/main/java/com/example/returnadvice/ResultAspect.java`

```java
package com.example.returnadvice;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.AfterReturning;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;

@Aspect
public class ResultAspect {
    private final AtomicInteger afterBoxCalls = new AtomicInteger();
    private final AtomicInteger afterTextCalls = new AtomicInteger();
    private final AtomicInteger aroundCalls = new AtomicInteger();

    @AfterReturning(
        pointcut = "execution(public com.example.returnadvice.ResultBox "
                 + "com.example.returnadvice.ReportService.loadPlain(..))",
        returning = "result",
        argNames = "result"
    )
    public void afterPlain(ResultBox result) {
        afterBoxCalls.incrementAndGet();

        // Mutate the exact object returned by the target:
        result.setValue("observed:" + result.getValue());

        // Only changes the local variable inside the advice:
        result = new ResultBox("local-only");
        System.out.println("[AFTER box] local=" + result.getValue());
    }

    @AfterReturning(
        pointcut = "execution(public java.lang.String "
                 + "com.example.returnadvice.ReportService.message(..))",
        returning = "text",
        argNames = "text"
    )
    public void afterMessage(String text) {
        afterTextCalls.incrementAndGet();
        text = "rewritten:" + text;
        System.out.println("[AFTER text] local=" + text);
    }

    @Around(
        "execution(public com.example.returnadvice.ResultBox "
        + "com.example.returnadvice.ReportService.loadWrapped(..))"
    )
    public Object aroundWrapped(ProceedingJoinPoint pjp) throws Throwable {
        aroundCalls.incrementAndGet();

        ResultBox source = (ResultBox) pjp.proceed();
        ResultBox replacement = new ResultBox("replaced:" + source.getValue());
        System.out.println("[AROUND] new-reference");
        return replacement;
    }

    public int afterBoxCalls() {
        return afterBoxCalls.get();
    }

    public int afterTextCalls() {
        return afterTextCalls.get();
    }

    public int aroundCalls() {
        return aroundCalls.get();
    }
}
```

The pointcuts are scoped to **exactly one method each** to prevent multi-advice ordering from skewing the comparison:

- The first `@AfterReturning` selects only `loadPlain`.
- The second `@AfterReturning` selects only `message`.
- `@Around` selects only `loadWrapped`.

Because they **do not match the same method**, stdout in the demo does not depend on ordering between `@Around` and `@AfterReturning` on a single call. `AtomicInteger` tracks how many times each advice executed; `argNames` helps Spring bind `result`/`text` explicitly.

### 7.6. `src/main/java/com/example/returnadvice/AppConfig.java`

```java
package com.example.returnadvice;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {
    @Bean
    public ReportService reportService() {
        return new ReportService();
    }

    @Bean
    public ResultAspect resultAspect() {
        return new ResultAspect();
    }
}
```

`@EnableAspectJAutoProxy` enables Spring `@AspectJ` proxy support; `proxyTargetClass=true` uses CGLIB for `ReportService`, which does not implement a business interface. `@Aspect` alone does not register a bean; `@Bean resultAspect()` handles that.

### 7.7. `src/main/java/com/example/returnadvice/DemoApp.java`

```java
package com.example.returnadvice;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApp {
    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {

            ReportService service = context.getBean(ReportService.class);
            ResultAspect aspect = context.getBean(ResultAspect.class);

            System.out.println("isAopProxy=" + AopUtils.isAopProxy(service));

            ResultBox plain = service.loadPlain("A");
            System.out.println("plainCaller=" + plain.getValue());
            System.out.println("plainSameReference="
                    + (plain == service.rawPlainReference()));

            ResultBox wrapped = service.loadWrapped("B");
            System.out.println("wrappedCaller=" + wrapped.getValue());
            System.out.println("wrappedSource="
                    + service.rawWrappedReference().getValue());
            System.out.println("wrappedSameReference="
                    + (wrapped == service.rawWrappedReference()));

            String message = service.message("C");
            System.out.println("messageCaller=" + message);

            System.out.println("afterBoxCalls=" + aspect.afterBoxCalls());
            System.out.println("afterTextCalls=" + aspect.afterTextCalls());
            System.out.println("aroundCalls=" + aspect.aroundCalls());
        }
    }
}
```

All calls go through the **Spring bean proxy** obtained from `ApplicationContext`; the demo does not use `new ReportService()` outside Spring. The two getters on the proxy match no advice, so they simply return the data stored on the raw target.

### 7.8. Running Maven and Expected Output

In the directory containing `pom.xml`, with JDK 17+:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.returnadvice.DemoApp
```

Lines printed by the example code, in order (excluding any Maven/SLF4J notices):

```text
isAopProxy=true
[TARGET plain] plain:A
[AFTER box] local=local-only
plainCaller=observed:plain:A
plainSameReference=true
[TARGET wrapped] source:B
[AROUND] new-reference
wrappedCaller=replaced:source:B
wrappedSource=source:B
wrappedSameReference=false
[AFTER text] local=rewritten:text:C
messageCaller=text:C
afterBoxCalls=1
afterTextCalls=1
aroundCalls=1
```

**Reading the results technique by technique:**

1. `isAopProxy=true`: the target service is Spring-managed and wrapped by an AOP proxy.
2. `[TARGET plain]` occurs before `[AFTER box]` because `@AfterReturning` only executes after `loadPlain` returns normally.
3. `[AFTER box] local=local-only` proves the assignment `result = new ResultBox(...)` updated the local variable inside the advice. Yet `plainCaller=observed:plain:A` proves the caller **did not receive the `local-only` object**.
4. `plainSameReference=true`: the caller received the **same reference** returned by the target; the advice only mutated `value` on that object.
5. `wrappedSameReference=false`: `@Around` created and returned a **different reference** from the original `loadWrapped` object. `wrappedSource=source:B` shows the source object retained its old state.
6. `messageCaller=text:C`: reassigning `text` inside `@AfterReturning` did not cause the caller to receive `"rewritten:text:C"`.
7. The counters equal `1` because each advice matched only one of the three defined calls.

The core learning point lies in **comparing identity with `==`**, not just inspecting `getValue()` strings. A mutable object can have its contents changed without changing its reference at all.

*Verification note:* the command and stdout above are designed and reviewed against the stated Spring APIs; when using in a real project, run Maven on your target JDK and Spring version to confirm the environment rather than assuming plugins/logging always emit identical auxiliary messages.

## 8. Cases Where You Should Not Use `@AfterReturning` to "Transform Results"

### 8.1. Replacing a DTO with Another DTO

For example, a service returns `OrderDto`, and you want to add a field and return a **new immutable DTO**:

```java
@AfterReturning(
    pointcut = "execution(* com.example..OrderService.get(..))",
    returning = "dto"
)
public void after(OrderDto dto) {
    dto = new OrderDto(dto.id(), "audited");
}
```

This is an **anti-pattern fragment**; `OrderDto` would have to be defined in the application. `dto = new ...` only alters the advice's local parameter, not the object the caller receives. If `OrderDto` is an immutable record, the right approach is usually for the **service/mapper to construct the desired DTO**, or for `@Around` to actually `return new OrderDto(...)`.

### 8.2. Masking Sensitive Data

Using `@AfterReturning` to mutate the returned object to mask data can cause side effects if that object is still held in a cache, persistence context, or another reference. A safer path is usually creating a **new response DTO** and returning it from an explicit mapping layer; if transformation must be a cross-cutting concern, `@Around` may fit, provided the pointcut is tightly scoped and security-tested.

Do not treat `@AfterReturning` as an automatic sanitizer for every response: Spring AOP only intercepts methods going through a proxy, not self-invocations or objects instantiated outside the container.

### 8.3. Wrapping Collections or Replacing Immutable Values

- `Collections.unmodifiableList(source)` creates a **different wrapper reference** (do not try `list = wrapper` inside `@AfterReturning`).
- `List.copyOf(source)` creates a collection value matching its contract; do not assume it is always the same reference.
- `String`, `BigDecimal`, immutable Java records: a new value must be created/returned if contents need to change.
- If an object is mutable, mutating it inside `@AfterReturning` can also introduce race conditions, cache bugs, or unintended dirty tracking.

If transforming the return value is the primary goal, `@Around` or an explicit mapper provides a clearer contract.

## 9. Is `@AfterReturning` Suitable for Metrics, Auditing, and Validation?

It is very well suited when you only need to **observe successful events**.

| Purpose | Is `@AfterReturning` suitable? | Notes |
| --- | --- | --- |
| Counting how many times a method returns normally | Yes | Advice runs after normal return, excluding calls where target throws. |
| Recording an audit event about result type/ID | Yes | Watch out for sensitive data and side effects from `toString()`. |
| Recording metrics on returned values | Yes | Use necessary metadata; avoid mutating the object unless required. |
| Checking invariants and logging warnings | Yes | Throwing an exception from advice prevents the caller from receiving normal return; must be a deliberate design choice. |
| Modifying a field on a mutable object in place | Technically possible | This is state mutation, not reference replacement; weigh side effects and concurrency. |
| Replacing `ResultBox` with a new object | No | Use `@Around` or change target logic. |
| Replacing a returned `String` with another string | No | `String` is immutable; local reassignment does not change the return. |
| Returning a cached result without running the target | No | `@Around` can decide not to call `proceed()`. |
| Intervening in target exceptions | Not its primary role | Use `@AfterThrowing` to observe errors, `@Around` if policy requires transforming them. |

A pragmatic Spring rule: **choose the least powerful advice type sufficient for the requirement**. If you only need to inspect the result to log it, `@AfterReturning` is more readable and alters control flow less than `@Around`. Escalate to `@Around` only when you genuinely need to replace output, skip/retry methods, or manage behavior around the invocation.

## 10. Edge Cases That Easily Lead to Wrong Conclusions

### 10.1. Method Throws an Exception

`@AfterReturning` does not run after a target method exits with an exception. If an inner `@Around` catches an exception and returns a fallback value, an `@AfterReturning` advice placed at an appropriate outer position in the interceptor chain may see a **normal return from the inner chain**. Therefore, when multiple advisors are nested, test on the **actual chain**, not just a single method in isolation.

`@AfterThrowing` is for observing exceptions thrown from a join point under Spring's contract, yet it is also **not** a mechanism for directly returning a replacement value. To convert an exception into a fallback value for the caller, `@Around` or explicit handling at the application boundary is usually required.

### 10.2. `void`, Primitives, and `null`

- An `@AfterReturning("execution(* ..SomeService.doWork(..))")` advice that does not bind a result can still match a `void` method completing normally.
- When `returning="result"` and parameter `ResultBox result` are present, the binding's runtime type filter applies; `void` methods and incompatible values will not behave like methods returning `ResultBox`.
- With `null`, test behavior on your actual Spring version and never call `result.getValue()` without ensuring `result` is non-null.
- Primitive methods typically involve boxing/unboxing at the interceptor boundary; advices with primitive/wrapper parameters should be verified in integration tests.
- If `@Around` replaces the value, return a type valid for the declared method signature—especially avoid returning `null` for a primitive return type.

Do not use `Object` or `ResultBox` in a catch-all advice and implicitly assume it handles `void`, `null`, primitives, and generics uniformly.

### 10.3. Reactive or Asynchronous Return Types

With `CompletionStage<T>`/`CompletableFuture<T>` or `Mono<T>`/`Flux<T>`, the target method typically **returns a wrapper/handle** before the asynchronous work actually completes or the publisher is subscribed to. Spring proxy AOP's `@AfterReturning` is tied to the **normal return of the Java method**, not automatically becoming a callback for "after HTTP response finishes" or "after future completes."

Therefore:

- `@AfterReturning(returning="future")` may receive **`CompletableFuture`**, not the `T` value computed later.
- `@AfterReturning` does not automatically handle errors occurring during future completion or reactive stream signal emission.
- To transform asynchronous values, use the appropriate API (`thenApply`, Reactor `map`/`onErrorResume`, etc.) at the proper layer; or use `@Around` if the intent is to replace the wrapper/reference returned to the caller.
- Check transaction/security/tracing semantics separately if the application uses Spring subsystems with specialized async/reactive integration.

This is a boundary between **Java method return** and **asynchronous completion**, not a bug specific to the `returning` expression.

### 10.4. `@AfterReturning` and `@Around` Matching the Same Method

An `@Around` can replace the returned reference. If `@AfterReturning` also matches, **the return value it observes depends on the relative positions of the advices in the chain**, which is not guaranteed to always be the original target object or always the replacement object. Use `@Order`/advisor ordering when needed, and integration-test the real order, since multiple advices in the same aspect follow specific rules.

Do not place two transformations with the same responsibility in separate aspects hoping they run in "source order." When the main purpose is return replacement, establish **one owner for the transformation policy** to avoid double-wrapping.

### 10.5. Self-Invocation or Calling the Raw Object

```java
public class ReportService {
    public ResultBox outer() {
        return loadPlain("internal");
    }

    public ResultBox loadPlain(String id) {
        return new ResultBox(id);
    }
}
```

This is an illustrative fragment. If the caller invokes `proxy.outer()`, yet the target calls `this.loadPlain()` internally, the internal call does not go through the proxy and `@AfterReturning` targeting `loadPlain` will not run via standard interception. Switching `@AfterReturning` to `@Around` **does not fix self-invocation**; route the call through a proper Spring proxy or redesign the bean boundary.

## 11. Testing Exactly What Needs to Be Proven

When writing tests for return-value advice in Spring AOP, distinguish:

1. **Is there a Spring proxy?** Verify `AopUtils.isAopProxy(service)` and context/bean registration.
2. **Does the pointcut match the exact method?** A proxy may exist from other advisors while this advice never runs.
3. **When is the advice invoked?** Use counters/events to distinguish normal return from exception exit.
4. **Did the return reference change?** Use `==` on the appropriate two references, not `equals` alone.
5. **Did state change?** Inspect fields/properties of the **exact returned object** after the advice runs.
6. **What does the caller see?** Assert directly on the return value at the call site, not merely by logging `result` inside the advice.
7. **Does `@Around` return the right type/exception?** Test primitives, `null`, and overloaded methods if applicable.
8. **Side-effect impact:** does mutating the object alter a cached/shared instance or managed entity?
9. **Thread safety:** singleton aspects and singleton targets can be invoked concurrently; do not store per-call state in mutable instance fields without proper concurrency control.
10. **Boundary:** test cross-bean invocations through the Spring proxy; do not instantiate targets with `new` expecting the Aspect to run.

Example assertions for the demo:

```java
ResultBox plain = service.loadPlain("A");
assert plain == service.rawPlainReference();
assert "observed:plain:A".equals(plain.getValue());

ResultBox wrapped = service.loadWrapped("B");
assert wrapped != service.rawWrappedReference();
assert "replaced:source:B".equals(wrapped.getValue());

String text = service.message("C");
assert "text:C".equals(text);
```

This is a **test fragment** assuming `service` is a Spring proxy and Java assertions are enabled when running (e.g., `-ea`). When using JUnit, use `assertSame`/`assertNotSame` to check identity and `assertEquals` for state/value.

Important: `equals()` can be overridden; `assertEquals` does not prove the returned reference stayed the same. When the requirement concerns replacing or preserving the **returned object**, an identity check is mandatory.

## 12. Common Errors and How to Fix Them

| Symptom | Cause | How to Fix |
| --- | --- | --- |
| Advice has `result = new Dto(...)`, yet caller still gets the old Dto | Reassigning the local parameter in `@AfterReturning` | Use `@Around` to return a new reference, or build the DTO in a service/mapper. |
| Advice updates a field and appears to have replaced the object | State mutation on a mutable instance | Compare with `==`, check both reference and state; avoid unintended mutation. |
| `@AfterReturning` does not run when target throws | It only runs on normal return | Use `@AfterThrowing` to observe errors, or `@Around` when exception behavior must change. |
| Binding `returning="dto"` fails to resolve | Advice lacks parameter `dto`, or `argNames`/metadata mismatch | Align binding name with advice parameter and verify signature. |
| Advice using `ResultBox` does not run on methods returning other types | Typed return binding restricts matching | Choose the exact type or `Object` if a broad interception point is genuinely needed. |
| `@Around` returns an object incompatible with declared type | Method signature / return contract violated | Return a compatible object; integration-test callers and exceptions. |
| `@Around` forgets `proceed()` and business logic doesn't run | Advice altered control flow | Call `proceed()` when transformation needs the original result; skip only by explicit design. |
| Advice unexpectedly modifies cache/entity/list | Mutable return object is shared | Prefer mapping/immutable returns or defensive copies with `@Around`. |
| Same method runs advice sometimes and skips other times | Callers go through different proxies, or pointcut/binding types differ | Check Spring context, `AopUtils`, pointcuts, and invocation paths. |
| `@AfterReturning` runs when method returns a future, before data arrives | Java method return differs from future completion | Use async/reactive operators at the proper layer; do not wait for `@AfterReturning` to handle completion. |
| Errors after combining `@Around` and `@AfterReturning` | Advice ordering / return type mismatch | Narrow responsibilities, test the chain, and configure explicit ordering. |
| Trying to change a `String` by reassigning the advice parameter | `String` is immutable and binding is local | Use `@Around` or change target logic to return a new `String`. |

## 13. Choosing the Solution Based on Real Requirements

**Only want to know the target finished and what it returned?** Use `@AfterReturning` for metrics/logging/auditing, combined with typed `returning` when needed. Keep the advice free of side effects on the returned object if possible.

**Only need to validate the return value without replacing it?** `@AfterReturning` can read it and log warnings. If policy genuinely requires throwing an error on invariant violation, document clearly that this fails the caller after the method has already run; avoid using it for silent normalization.

**Need to return a different immutable DTO/wrapper?** Prefer explicit mapping at the service/adapter layer. If it is a cross-cutting policy across many beans that must intervene at the proxy boundary, use `@Around` to return a different object of a compatible type.

**Need to edit data directly inside a mutable object?** Technically `@AfterReturning` can do this, but you must evaluate shared state, persistence dirty tracking, cache consistency, concurrency, ownership, and tests. It is not a safe default merely because it takes less code than `@Around`.

**Need to transform the value of a `CompletionStage` or `Mono` when processing completes?** Use operators on the asynchronous/reactive API, or `@Around` returning a transformed wrapper; do not confuse Java method normal return with completion events.

### Spring References

- Spring Framework — Declaring Advice (After Returning, Around): https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html
- Spring Framework — Enabling @AspectJ Support: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html
- Spring Framework — Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework — Advice API and AfterReturningAdvice: https://docs.spring.io/spring-framework/reference/core/aop-api/advice.html
- Spring Framework — AspectJAfterReturningAdvice Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/aop/aspectj/AspectJAfterReturningAdvice.html

**Conclusion:** `@AfterReturning` is designed to **observe a normal return**, not to replace the returned reference. Mutating a mutable object only changes **the state of the existing reference**, whereas assigning `result = new ...` inside advice never reaches the caller. To truly **replace the object the caller receives**, choose `@Around` with `return replacement` and test type, identity, state, and the Spring proxy boundary.
