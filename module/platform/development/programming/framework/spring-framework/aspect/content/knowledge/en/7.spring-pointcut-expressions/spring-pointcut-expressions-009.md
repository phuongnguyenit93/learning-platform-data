# Spring AOP Pointcuts: Combining Conditions with `&&`, `||`, and `!`

## 1. Goal and Scope

When configuring an aspect in **Spring AOP**, a pointcut expression often needs to describe multiple conditions simultaneously: advise only a service in a specific package, select two groups of methods, and exclude internal methods. Spring supports combining pointcut expressions using three logical operators:

- `&&` — **AND (intersection)**: all conditions must match.
- `||` — **OR (union)**: at least one condition matches.
- `!` — **NOT (negation)**: excludes join points where the trailing condition matches.

Example expressing the requirement "advise public methods belonging to the service whose names start with `create` or `cancel`, while excluding methods ending with `Internal`":

```java
@Before(
    "within(demo.pointcuts.OrderService)"
  + " && execution(public * *(..))"
  + " && (execution(* create*(..)) || execution(* cancel*(..)))"
  + " && !execution(* *Internal(..))"
)
public void beforeOperation(JoinPoint joinPoint) {
    System.out.println("[advice] " + joinPoint.getSignature().getName());
}
```

This is a fragment inside an `@Aspect` class. The strings are concatenated in Java with `+` before Spring parses them into a single pointcut expression. The condition above is:

```text
Inside OrderService
         AND
Is a public method
         AND
 (name starts with create OR name starts with cancel)
         AND
Name does not end with Internal
```

**Lesson scope:** this is pointcut syntax interpreted by Spring AOP using the AspectJ expression language. Spring AOP is **proxy-based** and supports only *method-execution join points* on Spring-managed beans; adding logical operators does not turn it into bytecode weaving or intercept every Java call.

## 2. Understanding AND, OR, NOT When Spring Selects Calls

Let A, B, and C be valid pointcut conditions on **a method execution observable by Spring AOP**:

| A | B | `A && B` | `A \|\| B` | `!A` |
| --- | --- | --- | --- | --- |
| false | false | false | false | true |
| false | true | false | true | true |
| true | false | false | true | false |
| true | true | true | true | false |

In the table, `A \|\| B` is escaped in the Markdown cell so it is not mistaken for a column separator; the actual pointcut expression is written `A || B`.

### 2.1. `&&`: Multiple Conditions Must All Hold

```java
@Pointcut("within(demo.pointcuts.OrderService)"
        + " && execution(public * *(..))")
private void publicOrderServiceMethods() {}
```

This matches only method executions determined to be inside `OrderService` **and** public. A public method in another service does not match; a private helper does not become a Spring AOP advised method merely by being declared in the same class.

Practical uses:

- Intersect `execution(...)` with `within(package..*)` to scope by service layer.
- Intersect a method pattern with `@annotation(...)` to advise only annotated methods.
- Intersect `bean(*Service)` with a method pattern when filtering by Spring bean name.

### 2.2. `||`: Combining Two Groups of Calls

```java
@Pointcut("execution(* create*(..)) || execution(* cancel*(..))")
private void mutatingOperations() {}
```

Methods whose names start with `create` **or** `cancel` can match, provided they are executions that a Spring proxy can intercept. Both conditions do not have to be true at the same time.

**Note:** `||` is logical OR, not "run the advice twice". If both sides match, **a single advice declared once** on the union expression still applies as one advice per invocation; having multiple independent advices is a different situation.

### 2.3. `!`: Excluding a Group

```java
@Pointcut("execution(* demo.pointcuts.OrderService.*(..))"
        + " && !execution(* *Internal(..))")
private void publicApiExceptInternal() {}
```

In this fragment, the negated term excludes methods whose names end with `Internal`. The name `publicApiExceptInternal` is only an example `@Pointcut` method name; the initial `execution(* ...*)` **does not restrict to public automatically**. To ensure public only, add `&& execution(public * *(..))`.

This is an important principle: **negation does not mean a security filter or an "absolute deny list"**. `!B` is simply a logical condition over method executions within Spring AOP's scope, and can broaden the match set if not paired with positive narrowing conditions.

## 3. Parentheses and Operator Precedence

In AspectJ pointcut syntax supported by Spring, the usual logical operator precedence is:

1. `!` has the highest precedence.
2. `&&` binds tighter than `||`.
3. `||` has the lowest precedence.

Therefore, the following expressions **differ**:

```text
A || B && C
```

is equivalent to:

```text
A || (B && C)
```

but is not equivalent to:

```text
(A || B) && C
```

**Common pitfall:** if you want "(create or cancel) and not Internal", write:

```java
@Pointcut("(execution(* create*(..)) || execution(* cancel*(..)))"
        + " && !execution(* *Internal(..))")
private void allowedMutations() {}
```

Avoid writing:

```java
@Pointcut("execution(* create*(..))"
        + " || execution(* cancel*(..))"
        + " && !execution(* *Internal(..))")
private void riskyMutations() {}
```

The latter is parsed as **create OR (cancel AND NOT Internal)**. Method `createInternal()` still matches because the `create*` branch on the left of `||` matches, even though the method name ends with `Internal`. Parentheses prevent turning a shared condition into one that applies only to the second branch.

### Verification Table for Excluding Internal

Suppose `A = create*`, `B = cancel*`, `C = *Internal`:

| Method | A | B | C | `(A \|\| B) && !C` | `A \|\| (B && !C)` |
| --- | --- | --- | --- | --- | --- |
| `createOrder()` | true | false | false | true | true |
| `cancelOrder()` | false | true | false | true | true |
| `createInternal()` | true | false | true | **false** | **true** |
| `cancelInternal()` | false | true | true | false | false |
| `findOrder()` | false | false | false | false | false |

This table describes **method name conditions**. In a Spring AOP application, calls must also go through a Spring-managed bean proxy and satisfy any other conditions.

**Recommendation:** always add parentheses when mixing `||` with `&&` or `!`, even when you remember precedence. It makes intent unmistakable when reviewing or modifying pointcuts later.

## 4. Combining Spring Pointcut Designators

The three logical operators are placed **between pointcut expressions or named pointcuts**, not inside ordinary Java method signatures. Commonly used Spring AOP pointcut designators include:

| Designator | Condition interpreted in Spring AOP | Example |
| --- | --- | --- |
| `execution(...)` | Method execution signature | `execution(public * demo.shop..*Service.*(..))` |
| `within(...)` | Type within execution scope | `within(demo.shop.service..*)` |
| `this(...)` | Type of the **Spring AOP proxy** | `this(demo.shop.OrderOperations)` |
| `target(...)` | Type of the **target object** | `target(demo.shop.OrderService)` |
| `args(...)` | Runtime type of arguments | `args(java.lang.String)` |
| `@annotation(...)` | Annotation on method execution | `@annotation(demo.shop.Audited)` |
| `@within(...)`, `@target(...)` | Type/target-related annotation | `@within(demo.shop.Secured)` |
| `bean(...)` | Spring bean name (Spring extension) | `bean(*Service)` |

Below are **illustrative** combinations; referenced classes or annotations must actually exist in the application.

**Selecting public service APIs in a package:**

```java
@Pointcut("execution(public * demo.shop.service..*.*(..))"
        + " && !execution(* demo.shop.service..*.healthCheck(..))")
void serviceApiExceptHealthCheck() {}
```

**Selecting annotated methods in a specific type:**

```java
@Pointcut("within(demo.shop.OrderService)"
        + " && @annotation(demo.shop.Audited)")
void auditedOrderMethod() {}
```

**Selecting either of two operation groups, excluding test beans:**

```java
@Pointcut("(execution(* *Service.save*(..))"
        + " || execution(* *Service.delete*(..)))"
        + " && !bean(test*Service)")
void productionWriteOperations() {}
```

`bean(...)` is a Spring-specific pointcut designator that can filter bean names with wildcards. The `test*Service` example is only a naming convention; if no bean matches that name, the negated term excludes nothing. Do not use bean-name logic as a security mechanism; pointcuts are for selecting calls to advise.

### Note on `this` and `target` When Combining

With a JDK dynamic proxy:

- `this(demo.shop.OrderOperations)` can match because the proxy implements the interface.
- `this(demo.shop.OrderService)` may **not** match if the JDK proxy is not a subclass of the implementation.
- `target(demo.shop.OrderService)` can match because the target object is the implementation class.

Hence, `execution(...) && this(...)` and `execution(...) && target(...)` can select different sets of methods. Write pointcuts referencing interfaces/targets deliberately and test on the **actual proxy type**.

## 5. Named Pointcuts: How to Organize Complex Expressions

Spring recommends composing small, clearly named pointcuts. Instead of a long, hard-to-maintain `@Before` string, create `@Pointcut` methods **without Java logic**:

```java
@Aspect
@Component
public class PolicyAspect {
    @Pointcut("within(demo.pointcuts.OrderService)")
    private void orderServiceType() {}

    @Pointcut("execution(public * *(..))")
    private void publicMethod() {}

    @Pointcut("execution(* create*(..))")
    private void createOperation() {}

    @Pointcut("execution(* cancel*(..))")
    private void cancelOperation() {}

    @Pointcut("execution(* *Internal(..))")
    private void internalOperation() {}

    @Pointcut("orderServiceType() && publicMethod()")
    private void servicePublicMethod() {}

    @Before("servicePublicMethod()"
          + " && (createOperation() || cancelOperation())"
          + " && !internalOperation()")
    public void before(JoinPoint jp) {
        System.out.println("[advice] " + jp.getSignature().getName());
    }
}
```

This is a class fragment without imports/package; the full example is in section 7.

How to read it:

- `servicePublicMethod()` is a **named pointcut**, not a Java method that actually runs when the business method is called.
- `createOperation() || cancelOperation()` is the **union of two match sets**.
- `!internalOperation()` **excludes** both `createInternal()` and `cancelInternal()`.
- Advice `before(...)` runs only when the full final condition matches an invocation through a Spring AOP proxy.

When referencing a named pointcut in the **same aspect class**, `servicePublicMethod()` syntax suffices. When sharing from another class, use the appropriate fully qualified name and ensure the pointcut method has **Java visibility** allowing access (e.g., `public`). The visibility of a `@Pointcut` method only controls source-level referencing, without altering the matched method set.

If an expression includes parameter binding such as `args(orderId)` or `@annotation(audited)`, the pointcut method and advice method must declare/bind compatible parameter names; logical operators do not pass Java method arguments into advice on their own. Illustrative example:

```java
@Pointcut("execution(* demo.shop.OrderService.submit(..)) && args(orderId)")
private void submitOrder(String orderId) {}

@Before("submitOrder(orderId)")
public void beforeSubmit(String orderId) {
    System.out.println(orderId);
}
```

This is a fragment requiring `demo.shop.OrderService` and compiler configuration preserving parameter names or explicit binding names when needed. With `||` and parameter binding, both branches must agree on required bindings; do not reference a variable present in only one branch assuming the other branch also supplies it.

## 6. Scopes That Logical Operators Do **Not** Change

### 6.1. Only Method Executions on Spring AOP Proxies

Whether an expression is `A && B`, `A || B`, or `!A`, Spring AOP still sees only method-execution join points interceptable via proxies. Pointcut designators such as `call`, `get`, `set`, `initialization`, and `cflow` are not supported by Spring AOP proxies as in full AspectJ weaving.

A negated expression like `!execution(* privateHelper(..))` does **not** turn private methods into advised methods: Spring proxies could not intercept those calls in the first place. Likewise, static calls do not pass through an instance proxy.

### 6.2. Self-Invocation Still Bypasses Advice

```java
@Service
class OrderService {
    public void runBatch() {
        this.createOrder(); // Direct target call, bypasses Spring AOP proxy.
    }

    public void createOrder() {
        // ...
    }
}
```

This is an illustrative fragment. Even though `createOrder()` matches `execution(* create*(..))`, calling `this.createOrder()` inside the target does not go through the proxy. Expanding `||` or adding `!` does not resolve self-invocation. Place the boundary on another Spring bean and inject the dependency if that operation genuinely needs separate advice.

### 6.3. Writing `@Pointcut` Alone Does Not Create a Proxy

A `@Pointcut` method defines a **condition**. Having a proxy/interceptor also requires:

1. Spring managing the target bean.
2. Registering the aspect as a Spring bean (e.g., `@Aspect @Component`).
3. Enabling Spring AOP infrastructure: `@EnableAspectJAutoProxy` in plain Spring Framework or appropriate auto-configuration.
4. Having an advice actually referencing the pointcut and matching the target.
5. Consumers calling the bean through its **proxy reference**.

If any of those elements is missing, writing a valid logical expression can still produce no observable effect.

## 7. Runnable Java 17 Project: Demonstrating `&&`, `||`, `!` via Logs

The example runs with **Java 17, Maven, and Spring Framework 6.2.x** (no Spring Boot required). It defines a Spring-managed `OrderService` with variously named methods; Spring creates an AOP proxy automatically when advisors match. The aspect uses named pointcuts to combine conditions.

### 7.1. Directory Structure

```text
spring-pointcut-operators/
├── pom.xml
└── src/main/java/demo/pointcuts/
    ├── AppConfig.java
    ├── OrderService.java
    ├── PolicyAspect.java
    └── Main.java
```

### 7.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-pointcut-operators</artifactId>
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

`spring-context` supplies IoC/annotation context, `spring-aop` supports proxies/advisors, and `aspectjweaver` lets Spring parse `@AspectJ` expressions. Neither AspectJ compile-time nor load-time weaving is needed in this example.

### 7.3. `AppConfig.java`

```java
package demo.pointcuts;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackageClasses = AppConfig.class)
@EnableAspectJAutoProxy
public class AppConfig {
}
```

`@EnableAspectJAutoProxy` turns on AOP infrastructure; `@ComponentScan` discovers the service and aspect. The target in the example declares no interface, so Spring selects a class-based proxy for it. Using `&&`/`||`/`!` is independent of choosing JDK proxy vs. CGLIB, though intercepted calls must still pass through a proxy.

### 7.4. `OrderService.java`

```java
package demo.pointcuts;

import org.springframework.stereotype.Service;

@Service
public class OrderService {
    public void createOrder() {
        System.out.println("[service] createOrder");
    }

    public void cancelOrder() {
        System.out.println("[service] cancelOrder");
    }

    public void createInternal() {
        System.out.println("[service] createInternal");
    }

    public void findOrder() {
        System.out.println("[service] findOrder");
    }

    public void batch() {
        System.out.println("[service] batch");
        this.createOrder(); // Self-invocation: does not go through AOP proxy.
    }
}
```

Method groups: `createOrder` and `cancelOrder` are allowed; `createInternal` is negated; `findOrder` does not match `create`/`cancel`; `batch` illustrates self-invocation.

### 7.5. `PolicyAspect.java`

```java
package demo.pointcuts;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.aspectj.lang.annotation.Pointcut;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class PolicyAspect {
    @Pointcut("within(demo.pointcuts.OrderService)")
    private void inOrderService() {}

    @Pointcut("execution(public * *(..))")
    private void publicMethods() {}

    @Pointcut("execution(* create*(..))")
    private void createMethods() {}

    @Pointcut("execution(* cancel*(..))")
    private void cancelMethods() {}

    @Pointcut("execution(* *Internal(..))")
    private void internalMethods() {}

    @Pointcut("inOrderService() && publicMethods()")
    private void orderPublicApi() {}

    @Before("orderPublicApi()"
          + " && (createMethods() || cancelMethods())"
          + " && !internalMethods()")
    public void beforeAllowedOperation(JoinPoint joinPoint) {
        System.out.println("[advice] "
                + joinPoint.getSignature().getName());
    }
}
```

Spring invokes the advice when the method execution **belongs to `OrderService`**, is **public**, has a name **starting with `create` or `cancel`**, and **does not end with `Internal`**.

`@Pointcut` methods are not called like business Java logic. They are named definitions referenced by pointcut expressions. `@Component` registers the aspect bean; `@Aspect` alone without bean registration is not necessarily picked up by Spring component scanning.

### 7.6. `Main.java`

```java
package demo.pointcuts;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {
            OrderService orders = context.getBean(OrderService.class);

            System.out.println("isAopProxy=" + AopUtils.isAopProxy(orders));
            orders.createOrder();
            orders.cancelOrder();
            orders.createInternal();
            orders.findOrder();
            orders.batch();
        }
    }
}
```

Run command from the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.pointcuts.Main
```

**Stdout lines printed by the program** (ignoring any Maven or Spring logs):

```text
isAopProxy=true
[advice] createOrder
[service] createOrder
[advice] cancelOrder
[service] cancelOrder
[service] createInternal
[service] findOrder
[service] batch
[service] createOrder
```

Exact explanation:

1. `isAopProxy=true` shows Spring supplied a proxy when the advisor applies to methods.
2. `createOrder()` matches `createMethods()` and does not match `internalMethods()`; advice runs before the service.
3. `cancelOrder()` matches the `cancelMethods()` branch; advice runs before the service.
4. `createInternal()` matches `createMethods()` **but** also matches `internalMethods()`, so `!internalMethods()` is false; no advice runs.
5. `findOrder()` does not match `create || cancel`; no advice runs.
6. `batch()` does not match `create`/`cancel`; no advice runs for `batch()` itself.
7. Inside `batch()`, the target calls `this.createOrder()` directly; even though the method signature matches, it **does not go through the Spring AOP proxy**, so this `createOrder()` prints no advice line.

### 7.7. Experiment: Omitting Parentheses Causes Incorrect Matching

Keeping the named pointcuts above, replace the advice expression with:

```java
@Before("orderPublicApi() && createMethods()"
      + " || cancelMethods() && !internalMethods()")
```

This is an **annotation-replacement fragment**; in practice, group shared conditions so you do not accidentally widen the scope. `orderPublicApi()` no longer applies to the entire `cancelMethods()` branch. The condition is interpreted as:

```text
(orderPublicApi AND createMethods)
OR
(cancelMethods AND NOT internalMethods)
```

Even `createInternal()` can start receiving advice again via the `create` branch because `!internalMethods()` now guards only the `cancel` branch. If another bean in the context has a `cancel*` method, the second branch also risks matching that bean since it is no longer locked down by `inOrderService()`.

Fix by always wrapping **the entire OR clause in parentheses** before intersecting with shared conditions:

```java
@Before("orderPublicApi()"
      + " && (createMethods() || cancelMethods())"
      + " && !internalMethods()")
```

### 7.8. Experiment: Replacing Negation with the Wrong Positive Condition

Change `!internalMethods()` to `internalMethods()`:

```java
@Before("orderPublicApi()"
      + " && (createMethods() || cancelMethods())"
      + " && internalMethods()")
```

Then only methods named `create`/`cancel` **and** ending with `Internal` match. On the service above, `createInternal()` is advised, while `createOrder()` and `cancelOrder()` are excluded. This verifies the negation meaning of `!`, not a Spring proxy bug.

## 8. Writing Expressions in Annotations, XML, and Other Configs

### 8.1. In Java Annotations

```java
@Before("execution(* demo.pointcuts..*Service.create*(..))"
      + " && !execution(* demo.pointcuts..*Service.createInternal(..))")
public void beforeCreate() {
    // Advice.
}
```

`&&`, `||`, and `!` are placed **inside the Java String** as shown. Do not write `&amp;&amp;` in a Java string; that is XML/HTML escaping, not syntax needed for annotations.

### 8.2. In Spring AOP XML

Example AOP namespace **fragment**:

```xml
<aop:config>
    <aop:pointcut
        id="safeCreate"
        expression="execution(* demo.pointcuts..*Service.create*(..)) and
                    !execution(* demo.pointcuts..*Service.createInternal(..))"/>
</aop:config>
```

In XML, `&` is a special character in **attributes**, so if you use `&&`, write `&amp;&amp;` for the XML parser to read it properly:

```xml
<aop:pointcut
    id="safeCreate"
    expression="execution(* demo.pointcuts..*Service.create*(..))
                &amp;&amp; !execution(* demo.pointcuts..*Service.createInternal(..))"/>
```

These are fragments, not a complete Spring application context XML file. Writing `and` and `or` as logical keywords is often more readable in XML, yet you must distinguish syntax variants per configuration medium. Unescaped `&` in XML can cause parse errors before Spring AOP even evaluates the pointcut.

### 8.3. Expressions Loaded from Properties/Config Text

If an application reads an expression from custom configuration to pass to Spring AOP APIs, you must know **which parser layer** receives the expression and the escaping rules of the outer format (XML, YAML, Java, properties). Pointcut operators differ from the syntax of the host configuration file. Do not assume a string valid in `@Before(...)` is automatically a valid literal in every file format.

## 9. Common Errors and How to Check

| Symptom | Cause | How to handle |
| --- | --- | --- |
| `createInternal()` is still advised despite `!internalMethods()` | Wrote `A || B && !C` instead of `(A || B) && !C` | Group OR with parentheses |
| Advice runs on beans outside intended scope | `within(...)` placed inside only one OR branch | Move scope condition **outside** the OR group and join with `&&` |
| No advice for any method | Used `&&` between mutually exclusive conditions | Consider `||` when the intent is union |
| Matches too many methods | Wrote only `!execution(...)` | Pair with positive narrowing conditions `execution(...) && within(...)` |
| Valid pointcut expression yet no proxy | Aspect is not registered as a Spring bean or no advisor matches | Check `@Aspect @Component`, auto-proxy, and AOP advisors |
| XML reports parse error on `&` | Wrote literal `&&` inside attribute | Change to `&amp;&amp;` or use keyword operators as appropriate |
| Spring throws unsupported pointcut error | Used `call`, `get`, `set`, `cflow`, or out-of-scope designator | Use Spring AOP-supported designators, typically `execution` |
| `this.createOrder()` receives no advice | Self-invocation bypasses proxy | Extract advised method into another Spring bean |
| Private/static method "matches on paper" | Spring proxies do not intercept those calls | Move policy to a public method on a proxied bean |
| `this(ImplementationClass)` fails to match JDK proxy | `this` checks the proxy, not the target | Use appropriate interface, or `target(ImplementationClass)` deliberately |
| `@annotation(...)` fails to match as expected | Annotation placed elsewhere or method/proxy type affects lookup | Check annotation on executing method and run integration test |
| Renamed named pointcut and advice stops running | Referenced method has wrong name/signature/visibility | Ensure `@Pointcut` exists, is named accurately, and is accessible |

**Review checklist when writing compound pointcuts:**

1. Write the business requirement as a sentence: "only in …; select A or B; exclude C".
2. Structure as `SCOPE && (A || B) && !C`, rather than cramming everything into an ungrouped string.
3. When conditions grow long, define small, clear, reusable `@Pointcut` names.
4. Verify operator precedence with an **included / excluded** table of at least 4–5 methods.
5. Ensure target/aspect are Spring-managed and callers go through the proxy.
6. Check JDK/CGLIB limits, self-invocation, and method visibility.
7. In XML, escape `&` and check file format before debugging AOP logic.
8. Add integration tests confirming target methods get advice and negated methods do not.

## 10. Review Questions

**1. Difference between `A && B` and `A || B`?** Intersection requires both true; union requires at least one true on the evaluated method execution.

**2. Does `!internalMethods()` make Spring intercept private methods?** No. It only negates the filter condition; interceptability depends on Spring proxies and method-execution join point scope.

**3. Is `A || B && !C` the same as `(A || B) && !C`?** No. The first is evaluated as `A || (B && !C)`; branch A escapes the negated C condition.

**4. Why use named pointcuts?** To separate small conditions, enable reuse, avoid string duplication, and clarify intersection/union/negation points.

**5. How is `&&` written in an XML attribute?** It must be escaped as `&amp;&amp;`, or written with the appropriate keyword form; in Java strings use `&&` directly.

**6. Can `@Before("A() || B()")` run the advice twice if both A and B match?** No. A single advice declaration using an OR expression is evaluated as one match condition; if it matches, that advice applies to the invocation.

**7. Why does `this.createOrder()` not trigger advice despite matching all method name conditions?** Because a direct internal call on the target bypasses the Spring AOP proxy.

## Official Spring Documentation

- [Spring Framework — Declaring a Pointcut, Combining Pointcut Expressions](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html)
- [Spring Framework — Declaring Advice](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html)
- [Spring Framework — @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html)
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework — Pointcut API (union/intersection)](https://docs.spring.io/spring-framework/reference/core/aop-api/pointcuts.html)
