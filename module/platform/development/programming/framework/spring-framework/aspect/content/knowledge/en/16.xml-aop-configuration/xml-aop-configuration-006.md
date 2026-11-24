# Parameter Binding, `returning`, and `throwing` in Spring AOP XML

## 1. Objectives

When configuring aspects via XML, Spring AOP allows advice to receive data directly from intercepted methods without manually extracting and casting every value from `JoinPoint.getArgs()`. The three core mechanisms are:

- **Input parameter binding** from a pointcut, e.g., `args(orderId, ..)`, into an advice parameter of the same name.
- **`returning`** on `<aop:after-returning>`: passes the value returned when the method completes normally into the advice.
- **`throwing`** on `<aop:after-throwing>`: passes the exception thrown out of the join point into the advice.

Additionally, **`arg-names`** in XML explicitly declares the parameter name order that Spring uses when connecting a pointcut to an advice method; this is especially helpful when Java bytecode does not retain parameter names at runtime.

This lesson focuses on **XML schema-based Spring AOP** (`<aop:config>`, `<aop:aspect>`, and advice elements). Neither `@Aspect` annotations nor AspectJ weaving are needed to run the examples.

## 2. Distinguishing Commonly Confused Elements

| XML Element | Role | Example |
| --- | --- | --- |
| `<aop:pointcut expression="..."/>` | Selects method executions and can declare binding variables | `args(orderId, ..)` |
| `method` | Java method name on the bean referenced by `<aop:aspect ref="...">` | `method="beforeProcess"` |
| `arg-names` | Ordered list of binding names matching the advice parameters | `arg-names="orderId,receipt"` |
| `returning` | Variable name receiving the return value, for after-returning advice | `returning="receipt"` |
| `throwing` | Variable name receiving the exception, for after-throwing advice | `throwing="failure"` |

Three binding rules to remember:

1. In `args(orderId, ..)`, **`orderId` is a binding name**; the advice method receives a parameter corresponding to this name. It does not have to match the business method's source parameter name, though its type and position must match.
2. `returning="receipt"` requires the advice to have a parameter receiving the return value corresponding to `receipt`. `throwing="failure"` requires a parameter receiving the exception corresponding to `failure`.
3. `arg-names` lists the names of **the parameters to bind** in the order declared on the advice method. If the method has `JoinPoint` as its first parameter, Spring can infer it by type so its name may be omitted from the list; still specify the remaining bindings so the configuration is easy to verify.

**Do not confuse `returning` or `throwing` with Java methods returning values or throwing exceptions.** They are attributes on **XML advice elements** specifying the values Spring passes to the advice after the intercepted method finishes.

## 3. Spring AOP Flow When a Method Is Called

Suppose a caller invokes `invoiceService.process("INV-1", false)` through a Spring proxy:

~~~text
Caller
  |
  v
Spring proxy: pointcut matches process(..), args(invoiceId, ..)
  |
  +-- <aop:before> receives invoiceId = "INV-1"
  |
  v
Target InvoiceService.process(...)
  |
  +-- returns String "paid:INV-1"
  |      |
  |      +-- <aop:after-returning returning="receipt">
  |               invoiceId = "INV-1"
  |               receipt = "paid:INV-1"
  |      |
  |      +-- returns original value to caller
  |
  +-- or throws IllegalStateException
         |
         +-- <aop:after-throwing throwing="failure">
                  invoiceId is bound from input
                  failure is the actual exception
         |
         +-- exception continues propagating to caller
~~~

`<aop:after-returning>` **runs only when the method completes normally**. `<aop:after-throwing>` **runs only when the join point exits by throwing an exception**. If the method catches an exception internally and returns a normal result, that follows the `after-returning` branch, not `after-throwing`.

All of this assumes the call goes through the Spring AOP proxy. Self-invocation like `this.process(...)` inside the target bean itself does not pass through the proxy and will not trigger advice on that internal call.

## 4. Standalone Example: XML + Java 17 + Spring Framework 6

The example uses **Java 17**, with Spring AOP supplied by **Spring Boot starter AOP 3.3.0** (whose dependency management brings in compatible Spring Framework 6.1.x), while directly initializing a Spring `ClassPathXmlApplicationContext`. Thus all **aspect declarations live in XML**, with no `@Aspect`, `@EnableAspectJAutoProxy`, or Spring Boot bootstrap via `SpringApplication.run`.

### 4.1. Project Structure

~~~text
pom.xml
src/main/java/com/example/xmlaop/
    InvoiceService.java
    InvoiceAdvice.java
    Demo.java
src/main/resources/
    applicationContext.xml
~~~

### 4.2. Maven

File `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>spring-aop-xml-binding-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Starter AOP includes Spring AOP and AspectJ weaver dependencies for pointcut parsing. Here it simply provides libraries via Maven; **XML itself** creates the auto-proxy.

### 4.3. Target Service

File `src/main/java/com/example/xmlaop/InvoiceService.java`:

~~~java
package com.example.xmlaop;

public class InvoiceService {

    public String process(String invoiceId, boolean reject) {
        System.out.println("service:" + invoiceId);

        if (reject) {
            throw new IllegalStateException("declined:" + invoiceId);
        }

        return "paid:" + invoiceId;
    }
}
~~~

Both branches are intentionally simple:

- `reject = false`: the method **returns a String**.
- `reject = true`: the method **throws IllegalStateException** and returns no String.

Spring AOP receives the same `invoiceId` parameter in before advice, then selects **one of the two** post-execution advices depending on how the method exits.

### 4.4. Plain Java Advice Bean

File `src/main/java/com/example/xmlaop/InvoiceAdvice.java`:

~~~java
package com.example.xmlaop;

public class InvoiceAdvice {

    public void beforeProcess(String invoiceId) {
        System.out.println("before:" + invoiceId);
    }

    public void afterSuccess(String invoiceId, String receipt) {
        System.out.println("returned:" + invoiceId + "->" + receipt);
    }

    public void afterFailure(String invoiceId, IllegalStateException failure) {
        System.out.println(
                "thrown:" + invoiceId + "->" + failure.getMessage());
    }
}
~~~

This is a POJO, requiring no `@Aspect`. The advice methods have clear names and parameter types; mappings are declared in XML.

**Type differences:** `String receipt` means the after-returning advice receives results compatible with `String`; `IllegalStateException failure` means the after-throwing advice only receives exceptions of type `IllegalStateException` or its subclasses. Use `Object receipt` to accept reference results of various types, and `Throwable failure` to observe broader errors (including `Error`). Do not narrow the parameter type below what the targeted method produces.

### 4.5. XML Configuration with Pointcut and Bindings

File `src/main/resources/applicationContext.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:aop="http://www.springframework.org/schema/aop"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/aop
           https://www.springframework.org/schema/aop/spring-aop.xsd">

    <bean id="invoiceService"
          class="com.example.xmlaop.InvoiceService"/>

    <bean id="invoiceAdvice"
          class="com.example.xmlaop.InvoiceAdvice"/>

    <aop:config proxy-target-class="true">
        <aop:aspect id="invoiceAspect" ref="invoiceAdvice">

            <aop:pointcut
                    id="invoiceProcess"
                    expression="execution(public * com.example.xmlaop.InvoiceService.process(..))
                                and args(invoiceId, ..)"/>

            <aop:before
                    pointcut-ref="invoiceProcess"
                    method="beforeProcess"
                    arg-names="invoiceId"/>

            <aop:after-returning
                    pointcut-ref="invoiceProcess"
                    method="afterSuccess"
                    returning="receipt"
                    arg-names="invoiceId,receipt"/>

            <aop:after-throwing
                    pointcut-ref="invoiceProcess"
                    method="afterFailure"
                    throwing="failure"
                    arg-names="invoiceId,failure"/>

        </aop:aspect>
    </aop:config>
</beans>
~~~

Reading in order:

1. `<bean id="invoiceService" .../>` creates the **target bean**. `<bean id="invoiceAdvice" .../>` creates the **advice POJO**.
2. `<aop:config>` enables Spring AOP proxy infrastructure for XML declarations in the ApplicationContext. `proxy-target-class="true"` uses a class-based proxy; `process` is public and non-final so it can be intercepted.
3. `<aop:aspect ref="invoiceAdvice">` connects the XML aspect concept to the `InvoiceAdvice` Java bean.
4. `execution(public * ...InvoiceService.process(..))` narrows the scope strictly to `process`, with any return type and argument count. `args(invoiceId, ..)` requires the first argument to be bindable to the advice's `String invoiceId`.
5. `arg-names="invoiceId"` on the before advice maps the pointcut variable to `beforeProcess(String invoiceId)`.
6. `returning="receipt"` and `arg-names="invoiceId,receipt"` pass **the return value** into the second parameter of `afterSuccess(String invoiceId, String receipt)`.
7. `throwing="failure"` and `arg-names="invoiceId,failure"` pass **the exception** into the second parameter of `afterFailure(String invoiceId, IllegalStateException failure)`.

**Why use `and` in the expression?** XML attributes cannot contain raw `&` characters as in `&&`; Spring AspectJ pointcut expressions support the keywords `and`, `or`, and `not`. If you must write `&&`, escape it as `&amp;&amp;`. This example uses `and` for readable XML.

**Why does `arg-names` include `receipt`/`failure` even though the pointcut does not declare them?** Because those are additional bindings supplied by the **`returning`/`throwing` attributes on the advice**. They need names to match the Java parameters even though they do not appear in `args(...)`.

### 4.6. Main Running Both Cases

File `src/main/java/com/example/xmlaop/Demo.java`:

~~~java
package com.example.xmlaop;

import org.springframework.context.support.ClassPathXmlApplicationContext;

public class Demo {

    public static void main(String[] args) {
        try (ClassPathXmlApplicationContext context =
                     new ClassPathXmlApplicationContext(
                             "applicationContext.xml")) {

            InvoiceService service =
                    context.getBean("invoiceService", InvoiceService.class);

            System.out.println("== success ==");
            String receipt = service.process("INV-1", false);
            System.out.println("caller:" + receipt);

            System.out.println("== failure ==");
            try {
                service.process("INV-2", true);
            } catch (IllegalStateException failure) {
                System.out.println(
                        "caller caught:" + failure.getMessage());
            }
        }
    }
}
~~~

In the directory containing `pom.xml`, run:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=com.example.xmlaop.Demo
~~~

Ignoring environment/Maven logs, the lines printed by the program have a **deterministic order and content**:

~~~text
== success ==
before:INV-1
service:INV-1
returned:INV-1->paid:INV-1
caller:paid:INV-1
== failure ==
before:INV-2
service:INV-2
thrown:INV-2->declined:INV-2
caller caught:declined:INV-2
~~~

Analysis:

- Success branch: `beforeProcess` runs before target; target returns `paid:INV-1`; `afterSuccess` receives both the initial `invoiceId` and the result; the caller still receives **the exact original return value**.
- Failure branch: `beforeProcess` still runs; target throws `IllegalStateException`; `afterFailure` receives the exception; the caller still catches **the original exception**.
- `afterSuccess` is not called on the failure branch; `afterFailure` is not called on the success branch.
- The XML configuration does not use `@Aspect`, and the caller does not instantiate `InvoiceService` with `new`, as doing so would bypass the proxy.

## 5. Deep Dive into `args(...)` and Type Binding

With the expression `args(invoiceId, ..)`:

- `invoiceId` is a **pointcut variable** to bind. Its `String` type is inferred from the advice parameters `beforeProcess(String invoiceId)`, `afterSuccess(String invoiceId, ...)`, etc.
- `..` represents any number of remaining arguments. Hence `process(String, boolean)` matches and captures the first `String` value.
- This is **runtime argument matching**; it does not simply mean "a method with a Java source parameter named `invoiceId`". Target method source parameter names do not dictate binding names in the pointcut.
- To match the signature strictly, add `execution(public String com.example.xmlaop.InvoiceService.process(String,boolean))`, while still using `args(invoiceId, ..)` to capture the specific value.

Another short XML example when binding two parameters:

~~~xml
<aop:before
        pointcut="execution(* com.example.xmlaop.InvoiceService.process(..))
                  and args(invoiceId,reject)"
        method="auditInput"
        arg-names="invoiceId,reject"/>
~~~

The corresponding advice method must have a matching signature, for example:

~~~java
public void auditInput(String invoiceId, boolean reject) {
    System.out.println("request=" + invoiceId + ", reject=" + reject);
}
~~~

The two snippets above **only illustrate a variant**; `auditInput` is not present in `InvoiceAdvice` in Section 4's runnable program. If you update the XML and add the method as shown, Spring passes both arguments in order. Do not paste this XML alone into the main example without adding the method.

When you want to inspect all args without configuring explicit bindings, before advice can accept `JoinPoint`:

~~~java
public void inspect(org.aspectj.lang.JoinPoint joinPoint) {
    Object[] arguments = joinPoint.getArgs();
    System.out.println("argumentCount=" + arguments.length);
}
~~~

This is also an **illustrative variant**. `JoinPoint.getArgs()` is more flexible, but you must extract and cast values manually. For a small set of clear variables, binding via `args` and `arg-names` is usually easier to maintain.

## 6. `returning`: Receiving the Result Without Altering the Return Value

`<aop:after-returning>` triggers only when the matched method **completes normally**. When `returning="receipt"` is set, Spring passes the result to the advice parameter with the matching binding name.

For instance, `afterSuccess(String invoiceId, String receipt)` specifies `String`: that acts as a **type constraint**. In a broad pointcut intercepting multiple methods with different return types, an advice accepting `String receipt` applies only to calls whose return value is compatible with `String`. Using `Object receipt` broadens the range of captured reference results. On a method declared to return `void`, there is no result value to bind to `String` as in the example.

After-returning advice **cannot use its own return value to replace the result** received by the caller. For example:

~~~java
// Illustrative variant, not a method in the main example:
public String afterSuccess(String invoiceId, String receipt) {
    return "overridden"; // does not become the return value of InvoiceService.process()
}
~~~

If business requirements call for modifying or replacing the result, use `<aop:around>` with `ProceedingJoinPoint` and explicitly return the intended result to the caller. Altering results in around advice requires respecting the method's contract and type.

**Note on mutable objects:** an advice receiving a reference to a result object can mutate **internal state inside that object** if it is mutable. That differs from replacing the returned reference itself. Avoid silently mutating data in telemetry/audit advice, as it makes outcomes depend on interceptor order.

## 7. `throwing`: Receiving the Thrown Exception Without Handling Recovery

Declaration:

~~~xml
<aop:after-throwing
        pointcut-ref="invoiceProcess"
        method="afterFailure"
        throwing="failure"
        arg-names="invoiceId,failure"/>
~~~

Spring passes the exception thrown out of the matched method to the advice's `failure` parameter. `IllegalStateException failure` matches only that exception type or its subtypes; if the method throws `IOException`, an advice typed as `IllegalStateException` will not run for it.

**After-throwing differs from `catch`**:

- The `afterFailure` advice in the example only records information.
- It does not swallow the exception to turn the execution into a success.
- A `return` inside after-throwing advice (if the method has a return type) does not replace the target's exception.
- The caller can still handle it with `try/catch`.
- If the target catches the error internally and returns normally, no exception escapes the join point for Spring to invoke after-throwing advice.

If you want a fallback when the target throws an exception, use `<aop:around>` and handle the exception around `proceed()` according to a **well-defined business policy**. Do not confuse `after-throwing` with Spring MVC's `@ControllerAdvice`/exception resolvers: they operate at different boundaries.

## 8. `arg-names`: How Spring Matches Variable Names to Advice Signatures

Variable binding in Spring AOP cannot reliably depend on **Java source parameter names** if bytecode does not retain them. Spring has parameter name discovery strategies, yet in XML you can explicitly configure `arg-names` to avoid ambiguity.

Suppose:

~~~java
public void afterSuccess(String order, String result) {
    // ...
}
~~~

If the pointcut uses the variable `invoiceId` and `returning="receipt"`, you can still declare:

~~~xml
<aop:after-returning
        pointcut-ref="invoiceProcess"
        method="afterSuccess"
        returning="receipt"
        arg-names="invoiceId,receipt"/>
~~~

Here the **order** in `arg-names` corresponds to the first and second Java parameters; the source names `order`/`result` do not control the mapping when Spring uses an explicit `arg-names` list. Even so, keeping the same names in Java and XML makes documentation and implementation easier to follow.

### If the Advice Accepts `JoinPoint`

Example before advice taking `JoinPoint` first followed by the bound argument:

~~~java
public void beforeProcess(
        org.aspectj.lang.JoinPoint joinPoint,
        String invoiceId) {
    System.out.println(joinPoint.getSignature().getName() + ":" + invoiceId);
}
~~~

The XML declaration can be:

~~~xml
<aop:before
        pointcut-ref="invoiceProcess"
        method="beforeProcess"
        arg-names="invoiceId"/>
~~~

Spring can automatically recognize a leading `JoinPoint` parameter by its type, so `joinPoint` does not need to be listed in `arg-names`. This is an **illustrative variant**: using this signature requires updating the `beforeProcess` method in the main example accordingly.

With `<aop:around>`, the first parameter of the advice method must be `ProceedingJoinPoint` in order to call `proceed()`. Binding for remaining parameters follows the same rules, while the around advice decides whether to run the target.

### Common Naming Configuration Mistakes

- XML writes `returning="retVal"` while `arg-names="invoiceId,result"`: `retVal` has nowhere to bind; this can cause aspect/advisor creation failure or an invalid binding.
- XML writes `throwing="failure"` while the advice method only has parameter `String failure`: incompatible type for the exception object.
- `arg-names="receipt,invoiceId"` while the method declares parameters in order `(String invoiceId, String receipt)`: since both values are Strings, the bug **evades type checking**, silently swapping log or business values.
- Pointcut writes `args(invoiceId, ..)` while the advice also wants to bind `tenantId` missing from the expression: the variable lacks a value source.
- Omitting `arg-names` and expecting Spring to always recover Java parameter names when compiled without appropriate name-retention flags: binding may depend on discovery or fail.

Especially when bindings share identical types like String/String, **tests asserting actual runtime values** are necessary to prove correct mapping; the Java compiler cannot catch semantic parameter swaps.

## 9. Combining Multiple Variables: Inputs + Returning/Throwing

An advice can receive both inputs from `args(...)` and outputs/exceptions. As used in the main example:

| Call | Pointcut `args(invoiceId, ..)` | Extra data from XML | Advice receives |
| --- | --- | --- | --- |
| `process("INV-1", false)` | `invoiceId="INV-1"` | `receipt="paid:INV-1"` | `afterSuccess(String, String)` |
| `process("INV-2", true)` | `invoiceId="INV-2"` | `failure=IllegalStateException("declined:INV-2")` | `afterFailure(String, IllegalStateException)` |

Even though both after-advices share the same `pointcut-ref`, whether the method succeeds or fails determines which advice runs; `returning` and `throwing` **never bind simultaneously for the same completion**.

When interception must distinguish overloads or different argument types, narrow `execution` by signature and use `args` for the specific values you want to capture. Avoid overly broad expressions spanning every bean/method just to audit one operation, since binding types can cause unexpected matching or unnecessary overhead.

## 10. Operating Conditions and Common XML AOP Errors

### 10.1. Advice Not Called Even Though XML Loads Successfully

Check sequentially:

1. Are the `aop` namespace, `spring-aop.xsd`, `<aop:config>`, and `<aop:aspect ref="...">` declared properly?
2. Does the aspect bean referenced by `ref` exist, and does `method` match the exact method name on that bean?
3. Is the target bean **Spring-managed**, and does the caller retrieve the **proxy** from the context?
4. Does the `execution(...)` pointcut match the actual class, method, and parameter types?
5. Is self-invocation `this.process(...)` or a private/final method preventing the proxy from intercepting the call?
6. Are there errors in `arg-names`, `returning`, `throwing`, or the advice's parameter types?

The example uses a class-based proxy so `InvoiceService` needs no interface. If switching to a JDK proxy, the target must have a proxied interface and callers should inject/retrieve the bean by **interface type**, not cast the proxy to the concrete class.

### 10.2. XML Rejected by Parser Due to Ampersand

Incorrect:

~~~xml
<!-- Invalid XML syntax: raw & cannot be placed inside an attribute -->
<aop:pointcut
        id="x"
        expression="execution(* com.example..*(..)) && args(name,..)"/>
~~~

Correct (using keyword):

~~~xml
<aop:pointcut
        id="x"
        expression="execution(* com.example..*(..)) and args(name,..)"/>
~~~

Or using XML entities:

~~~xml
<aop:pointcut
        id="x"
        expression="execution(* com.example..*(..)) &amp;&amp; args(name,..)"/>
~~~

These XML snippets only illustrate escaping/pointcut syntax; they do not replace the demo configuration with explicit bindings.

### 10.3. Binding Errors May Not Surface at Compile Time

XML configuration is processed by Spring when initializing the `ApplicationContext`. If an advice references a nonexistent name, mismatched variable count, or unresolvable method, errors appear **at startup** rather than during Java compilation. For critical security/audit/transaction logic, write integration tests that boot the context and invoke methods via bean proxies on both success and failure paths.

### 10.4. `returning` Does Not Always Mean "Business Work Finished"

If a method returns `CompletableFuture`, after-returning advice usually sees **the returned future object**, not necessarily the final processing result. If a method returns `Mono`/`Flux`, the advice sees the returned publisher, without measuring subscription completion. When auditing the final outcome of asynchronous work, observe completion/subscription with an appropriate mechanism instead of inferring from method return time.

### 10.5. Multiple Advice Order and Exception Handling

When combining advice from different aspects/advisors, interceptor order affects what data is seen and when logs are written. If an outermost around advice catches an exception and returns a fallback, an after-throwing advice **outside** that around advice will no longer see the exception. If after-throwing sits **inside** and sees the exception before it is caught, it can still trigger. Define observation boundaries and order around required guarantees; when order matters, configure precedence explicitly and test rather than guessing.

### 10.6. Where to Place Configuration

Schema-based AOP lives in the Spring `ApplicationContext` that actually loads the XML. A standalone XML declaring `<aop:config>` has no effect if the application never imports/loads that file. If a Spring Boot application primarily uses Java config, `@ImportResource("classpath:applicationContext.xml")` on a configuration class can load the XML; this is an **optional integration approach**, not required by the demo using `ClassPathXmlApplicationContext`.

## 11. Verification Checklist

Before considering XML AOP binding correct, confirm:

- Spring starts the `ApplicationContext` with the `aop` schema and all required dependencies.
- The pointcut selects only intended methods and does not accidentally intercept other operations.
- `args` binds the right **input values**, even when Java source names differ from pointcut variables.
- `arg-names` order matches the advice's Java parameter list.
- `returning` binds the right result on success; after-returning does not run on failure.
- `throwing` binds the right exception type on failure; after-throwing does not run on success.
- The caller still receives the original return value or exception, unless an around advice intentionally changes it.
- Tests invoke **through the Spring proxy**, not directly on `new Target()` or via self-invocation.
- When using async/reactive types, it is clear whether method exit or actual task completion is being observed.

## 12. Takeaways

Spring AOP XML separates **what to intercept** (pointcut) from **what data enters the advice** (binding). `args(...)` associates input values with variable names; `arg-names` maps those names to the Java advice signature; `returning` and `throwing` add bindings for normal results or exceptions. Although configured in XML, Spring AOP remains **proxy-based**, carrying the same self-invocation and advisor-ordering rules as other Spring AOP styles.

Official documentation:

- [Spring Framework — Schema-based AOP Support](https://docs.spring.io/spring-framework/reference/core/aop/schema.html)
- [Spring Framework — Declaring Advice](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html)
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)