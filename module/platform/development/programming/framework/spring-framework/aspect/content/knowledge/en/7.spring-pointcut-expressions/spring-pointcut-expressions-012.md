# AspectJ Pointcut Designators Not Supported by Spring AOP

## 1. The Problem: Valid AspectJ Syntax Does Not Guarantee Execution in Spring AOP

Spring Framework supports declaring aspects using `@Aspect`, `@Pointcut`, `@Before`, and `@Around` with pointcut expression syntax derived from AspectJ. However, **Spring AOP does not implement the entire AspectJ pointcut language**. Spring's proxy infrastructure provides only **method execution join points on Spring-managed beans**, without observing every kind of event such as method call sites across arbitrary bytecode, field accesses, or constructor initialization.

Therefore, the expression:

~~~java
@Before("execution(* demo.OrderService.submit(..))")
public void beforeSubmit() {
    // Usable by Spring AOP.
}
~~~

can be valid, whereas the expression:

~~~java
@Before("call(* demo.OrderService.submit(..))")
public void beforeCall() {
    // Spring AOP does not support the call(...) designator.
}
~~~

is **invalid for the pointcut parser used by Spring AOP**. When a pointcut expression contains a designator unsupported by Spring AOP and the framework attempts to parse/prepare the pointcut, it throws `IllegalArgumentException`. This is typically a **configuration/application-context startup error**, rather than simply "advice did not match so it was skipped".

The two snippets above illustrate advice methods inside an `@Aspect` class; they are not standalone Java files and should not be placed together in a normally running application. This lesson focuses on valid and invalid designators **in Spring AOP**, alternatives using Spring-managed beans, how to reproduce the error, and how to diagnose it. It does not expand into a full AspectJ weaving guide.

## 2. Why Does Spring AOP Limit Itself to Method Execution?

Spring AOP operates on a **proxy** model. Spring beans are evaluated by an auto-proxy creator after the container creates the bean; if a matching advisor exists, callers receive a JDK dynamic proxy or a class-based proxy. When a caller invokes a method **through the proxy**, the interceptor chain runs advice and then forwards to the target.

~~~text
Caller
   |
   | calls bean provided by Spring
   v
Spring AOP proxy
   |
   | method invocation / advisor matching
   v
@Before / @Around / ... advice
   |
   v
Target bean.method(...)
~~~

Operations that calls going through a proxy *do not directly expose* as join points include:

- Targeting the **call site** of a method inside a specific caller's code, as distinct from the event of the target method executing.
- Reading/writing object **fields** (`get`/`set` in the field join point sense, not methods named `getX`/`setX`).
- Constructor initialization and static initialization.
- Analyzing around a join point across the entire call stack's control flow using `cflow`/`cflowbelow` designators directly.
- Designators requiring bytecode/lexical context details that a Spring AOP proxy does not represent.

Accordingly, `execution(...)` is the primary designator in Spring AOP. Spring still allows constraining by type, annotation, arguments, and bean name **on method executions that can be proxied**.

One distinction to remember: **`call(...)` and `execution(...)` do not have the same meaning**. `call` describes *where code issues the call*, while `execution` describes *the method execution event*. In Spring AOP, an external call to a Spring proxy can trigger advice at the **execution join point**; Spring does not support selecting call sites directly via `call(...)`.

## 3. List of Designators Supported by Spring AOP

According to official Spring Framework 6.2 documentation, Spring AOP accepts the following **nine** AspectJ pointcut designators:

| Designator | Meaning when used in Spring AOP | Example expression |
| --- | --- | --- |
| `execution` | Selects method executions by method signature | `execution(public * demo.OrderService.*(..))` |
| `within` | Narrows scope by method-declaring type | `within(demo..service..*)` |
| `this` | Checks whether the **proxy reference** is an instance of the specified type | `this(demo.OrderOperations)` |
| `target` | Checks whether the **target object** behind the proxy is an instance of that type | `target(demo.OrderService)` |
| `args` | Selects by runtime types of passed arguments | `args(java.lang.String)` |
| `@target` | Checks annotation on the runtime type of the target object | `@target(demo.AuditedType)` |
| `@args` | Checks annotation on the runtime type of argument objects | `@args(demo.ValidatedPayload)` |
| `@within` | Narrows method executions within types bearing an annotation | `@within(demo.AuditedType)` |
| `@annotation` | Selects methods bearing the corresponding annotation | `@annotation(demo.AuditedOperation)` |

Examples containing `demo.OrderOperations`, `demo.AuditedType`, and `demo.ValidatedPayload` are syntax illustrations only and require corresponding types/annotations in a real project. Check interface/proxy types with `this` and target implementations with `target`; the two **differ in Spring AOP** because a proxy sits between caller and target.

Spring AOP also adds a **Spring-specific** designator:

~~~text
bean(orderService)
bean(*Service)
~~~

`bean(namePattern)` restricts by **Spring bean name** and supports the `*` wildcard. Example:

~~~java
@Before("execution(* demo.OrderService.submit(..)) && bean(orderService)")
public void beforeOrderService() {
    // Applies when both bean name and method execution match.
}
~~~

This is an illustrative advice method inside an `@Aspect`. `bean()` is a **Spring AOP** extension, not a standard designator usable in native AspectJ weaving. It makes sense because the Spring container manages **bean names** and creates proxies for **specific instances**.

Logical operators can be combined:

- `&&`: both conditions must match;
- `||`: at least one condition matches;
- `!`: negation;
- parentheses when grouping conditions is needed.

Using operators alone does not make an **unsupported** PCD valid. For example, `execution(...) && call(...)` still contains `call` and is rejected by the Spring AOP parser.

## 4. List of 14 Designators Not Supported by Spring AOP

Spring Framework documentation lists **14** designators belonging to the full AspectJ language that are **not supported by Spring AOP** at the pointcut expression layer:

| Designator | Purpose in the full AspectJ language | Verdict in Spring AOP |
| --- | --- | --- |
| `call` | Selects the **call site** of a method/constructor | Not accepted |
| `get` | Selects **field read** join points | Not accepted |
| `set` | Selects **field write** join points | Not accepted |
| `preinitialization` | Selects the phase before constructor initialization | Not accepted |
| `staticinitialization` | Selects static initialization of a type | Not accepted |
| `initialization` | Selects constructor initialization | Not accepted |
| `handler` | Selects exception handler execution points | Not accepted |
| `adviceexecution` | Selects when an advice is executing | Not accepted |
| `withincode` | Selects join points lexically inside the code of a method/constructor | Not accepted |
| `cflow` | Selects join points within the control flow of another join point | Not accepted |
| `cflowbelow` | Selects join points *below* a source join point in control flow | Not accepted |
| `if` | Special dynamic condition inside an AspectJ expression | Not accepted |
| `@this` | Selects by annotation on `this` in AspectJ semantics | Not accepted |
| `@withincode` | Selects by annotation on code containing the join point | Not accepted |

**Exact comparison:** `this` is supported, whereas `@this` is not; `within` is supported, whereas `withincode` is not; `@within` is supported, whereas `@withincode` is not. These pairs are easy to mix up when porting code from native AspectJ to Spring AOP.

When an unsupported PCD is placed into a Spring AOP expression, Spring throws `IllegalArgumentException` while parsing or initializing the pointcut. **No actual bean or method needs to match** to prove that PCD invalid; the error comes from the designator parser. When the error surfaces can vary depending on how pointcuts and the application context are initialized.

This list is based on **Spring Framework 6.2**; when upgrading versions, always consult the documentation for the version in use rather than assuming the set of designators is permanently fixed.

## 5. Especially Common Confusions

### 5.1. `call` Differs from `execution`

Two pointcuts:

~~~text
call(* demo.OrderService.submit(..))
execution(* demo.OrderService.submit(..))
~~~

cannot be substituted arbitrarily in **semantics**. The latter selects method executions on a Spring bean, whereas `call` is in the unsupported group. If the goal is simply logging before a Spring service method runs, the natural Spring AOP solution is `execution(...)` (optionally combined with `within`, `@annotation`, or `bean()`).

If the genuine goal is "advise only when the method is called **from a specific call site**", `execution` will **not guarantee the same scope**. Spring AOP proxies do not observe lexical call sites at the `call` level. Redesign service/adapter boundaries or evaluate a separate weaving mechanism if the requirement truly demands call-site join points.

### 5.2. `get`/`set` Are Not Equivalent to Java Getters/Setters

Given a Java class:

~~~java
public class AccountService {
    private int balance;

    public int getBalance() {
        return balance;
    }

    public void setBalance(int amount) {
        this.balance = amount;
    }
}
~~~

Points to distinguish:

- `get(int demo.AccountService.balance)` and `set(int demo.AccountService.balance)` are AspectJ **field access** designators; they do not work in Spring AOP.
- `execution(* demo.AccountService.getBalance())` or `execution(* demo.AccountService.setBalance(..))` are **method execution** pointcuts, which Spring AOP can apply if the methods are called through a Spring proxy.
- Direct operations `balance = amount` or `int value = balance` inside the target remain field reads/writes. A Spring AOP proxy does not intercept field access merely because other methods on the class are proxied.

The Java snippet illustrates a class that compiles standalone, but becomes a Spring AOP target only if registered as a Spring bean with a matching advisor.

### 5.3. Constructor/Static Initialization Is Not Method Execution

~~~text
preinitialization(demo.OrderService.new(..))
initialization(demo.OrderService.new(..))
staticinitialization(demo.OrderService)
~~~

Three expressions illustrating unsupported designators. Spring instantiates beans via constructors/factories and can post-process them to return proxies **after the object creation phase**; ordinary proxies do not intercept constructor executions or static initializers as advice join points.

If you need behavior when Spring creates a bean, use the appropriate **container lifecycle/extension point** such as `@PostConstruct`, init callbacks, `BeanPostProcessor`, or application events; do not force an `initialization(...)` expression into `@Before` expecting Spring AOP to understand it.

Important detail: `@PostConstruct` is a lifecycle callback, **not** a way to make Spring AOP intercept every object instantiation. When a method is called directly from a target's constructor/init, that call usually **has not passed through the final Spring proxy either**.

### 5.4. `handler` Is Not the Way to Advise Exceptions

`handler(...)` selects exception handler join points in the full AspectJ language; Spring AOP does not support it. If the goal is observing **exceptions thrown from Spring bean method executions**, use `@AfterThrowing` advice:

~~~java
@AfterThrowing(
    pointcut = "execution(* demo.OrderService.submit(..))",
    throwing = "ex"
)
public void whenSubmitFails(IllegalStateException ex) {
    System.out.println("EXCEPTION: " + ex.getMessage());
}
~~~

This is an **illustrative advice method** that must reside in a Spring `@Aspect` bean importing `org.aspectj.lang.annotation.AfterThrowing`. It runs when the advised method execution throws a matching exception and the call passed through the proxy. It is **not** equivalent to entering every `catch` block, nor does it observe exceptions caught and swallowed inside the target itself.

### 5.5. `cflow`/`cflowbelow`: Distinguishing PCDs from the Spring Pointcut API

~~~text
cflow(execution(* demo.Controller.handle(..)))
cflowbelow(execution(* demo.Controller.handle(..)))
~~~

These strings are not valid Spring AOP expressions. Spring AOP does not accept the AspectJ `cflow` or `cflowbelow` PCDs.

**Easily misunderstood exception:** Spring also provides `org.springframework.aop.support.ControlFlowPointcut` in the **programmatic Pointcut API**. It is a Spring API that can select method executions using call-stack info (less powerful than AspectJ's `cflow` semantics). The existence of **class `ControlFlowPointcut` does not make the `cflow(...)` designator usable inside `@Pointcut`**. These are two different APIs/mechanisms.

If the goal is accessing a request-scoped context or correlation ID when a Spring service method is called, consider passing context explicitly or using an appropriate layer such as filters/interceptors/request context rather than trying to port AspectJ call-flow expressions into Spring AOP.

### 5.6. `withincode` and `within` Are Not the Same

- `within(demo..service..*)` **is supported**: restricts method executions by **type scope**.
- `withincode(* demo.Controller.handle(..))` **is not supported**: requires matching join points lexically located **inside** a method's body.
- `@within(demo.AuditedType)` **is supported**: types carrying the corresponding annotation.
- `@withincode(demo.AuditedAction)` **is not supported**: annotation on the code enclosing the join point.

When you need to scope a pointcut by **service layer**, use `execution(* demo..service..*.*(..))` or `within(...)` combined with `execution(...)`. If you only want advice when a specific caller calls, type/method-execution matching does not provide `withincode`'s call-site model.

### 5.7. `this`/`@this` and `target`/`@target`

With Spring AOP proxies, `this(Type)` inspects the **proxy object**, while `target(Type)` inspects the **target object**. This semantics is especially important when a JDK dynamic proxy only implements interfaces and is not a subclass of the implementation.

~~~text
this(demo.OrderOperations)      // Supported by Spring AOP
target(demo.OrderService)       // Supported by Spring AOP
@target(demo.AuditedType)       // Supported by Spring AOP
@this(demo.AuditedType)         // Not supported by Spring AOP
~~~

The `@` prefix creates a different designator; do not change `@this` to `this` if your original goal was matching by **annotation**. Decide whether you need to check the target's type or annotation, then choose `target` or `@target` accordingly.

## 6. Java 17+ Project Demonstrating Valid Pointcuts and Unsupported Errors

The example uses **Spring Framework 6.2.0**, **AspectJ Weaver 1.9.22**, Maven, and JDK 17+. We create a Spring service bean with a valid advice, then **programmatically check an invalid `call` pointcut using the Spring API** without crashing the application context at startup.

Structure:

~~~text
spring-aop-pcd-check/
├── pom.xml
└── src/main/java/demo/
    ├── Demo.java
    ├── OrderService.java
    └── TraceAspect.java
~~~

### 6.1. Maven Configuration

Create `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-pcd-check</artifactId>
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
                    <mainClass>demo.Demo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` supplies Java configuration and the container, `spring-aop` holds proxy/pointcut APIs, and `aspectjweaver` lets Spring parse `@AspectJ`-style syntax. This dependency **does not automatically enable AspectJ bytecode weaving**.

### 6.2. Business Service

Create `src/main/java/demo/OrderService.java`:

~~~java
package demo;

public class OrderService {
    public void submit(String orderId) {
        System.out.println("SERVICE: submit " + orderId);
    }
}
~~~

The class is non-`final` and `submit` is `public`; Spring can wrap it in a class-based proxy to intercept method execution.

### 6.3. Aspect with Supported Expressions

Create `src/main/java/demo/TraceAspect.java`:

~~~java
package demo;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class TraceAspect {
    @Before("execution(* demo.OrderService.submit(..))"
          + " && within(demo.OrderService)")
    public void beforeSubmit() {
        System.out.println("ADVICE: before submit");
    }
}
~~~

Both `execution` and `within` are in the Spring AOP supported set. The `within(demo.OrderService)` condition also illustrates valid type-scope restriction. Both conditions match the same method in the example; the method is not intercepted twice just because the expression has two designators.

### 6.4. Checking the Proxy Then Catching the Parser Error for `call(...)`

Create `src/main/java/demo/Demo.java`:

~~~java
package demo;

import org.springframework.aop.aspectj.AspectJExpressionPointcut;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class Demo {
    @Bean
    public OrderService orderService() {
        return new OrderService();
    }

    @Bean
    public TraceAspect traceAspect() {
        return new TraceAspect();
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Demo.class)) {
            OrderService service = context.getBean(OrderService.class);
            boolean proxied = AopUtils.isAopProxy(service);

            System.out.println("PROXY: " + proxied);
            service.submit("A-01");

            AspectJExpressionPointcut unsupported =
                    new AspectJExpressionPointcut();
            unsupported.setExpression(
                    "call(* demo.OrderService.submit(..))");

            boolean rejected = false;
            try {
                unsupported.getClassFilter().matches(OrderService.class);
            } catch (IllegalArgumentException ex) {
                rejected = true;
                System.out.println("UNSUPPORTED_CALL: rejected");
            }

            if (!proxied || !rejected) {
                throw new IllegalStateException(
                        "Spring AOP pointcut check failed");
            }
            System.out.println("CHECK: PASS");
        }
    }
}
~~~

Mechanics in this snippet:

1. `@EnableAspectJAutoProxy(proxyTargetClass = true)` allows Spring to build a class proxy for the `OrderService` bean. `@Bean traceAspect()` registers the aspect with a valid advisor. `@Aspect` alone without registering as a bean would not be enough.
2. `service.submit("A-01")` goes through the proxy, so `@Before` runs before the target method.
3. `new AspectJExpressionPointcut()` is a Spring AOP API for interpreting an AspectJ pointcut expression. We **intentionally** set an expression containing unsupported `call(...)`. This pointcut object is **not registered as an advisor in the context**, so it does not fail Spring application startup.
4. `getClassFilter().matches(OrderService.class)` forces the pointcut to perform type-condition parsing/evaluation; the Spring AOP parser rejects `call` and throws `IllegalArgumentException`.
5. `catch` prints only a stable marker, avoiding exception messages that can vary across parser versions. The `rejected` flag forces the app to prove it caught the error before printing `CHECK: PASS`.

### 6.5. Run Command and Output

In the `spring-aop-pcd-check` directory:

~~~bash
mvn -q compile exec:java
~~~

Lines intentionally printed by the sample code:

~~~text
PROXY: true
ADVICE: before submit
SERVICE: submit A-01
UNSUPPORTED_CALL: rejected
CHECK: PASS
~~~

Messages from Maven/frameworks may appear besides these five lines. Two results to distinguish:

- `PROXY: true` and `ADVICE: before submit` confirm the `execution && within` expression **is accepted by Spring AOP and advice runs through the proxy**.
- `UNSUPPORTED_CALL: rejected` proves `call(...)` was rejected by the Spring AOP pointcut parser—not because `OrderService` lacked the method or because the advisor failed to match.

This is a controlled reproduction testing the core point of the lesson: **pointcut syntax valid in native AspectJ is not necessarily valid in Spring AOP**.

## 7. What Happens When Writing an Unsupported Designator Directly in `@Aspect`?

If you change `TraceAspect`'s advice to:

~~~java
@Aspect
public class TraceAspect {
    @Before("call(* demo.OrderService.submit(..))")
    public void beforeSubmit() {
        System.out.println("ADVICE: before submit");
    }
}
~~~

this is an **illustrative replacement snippet for the aspect class**, not a normally runnable setup. When Spring prepares the advisor/pointcut for the aspect and detects the unsupported `call` designator, bean/context creation or AOP advisor initialization fails with `IllegalArgumentException` in the cause chain (sometimes wrapped in a Spring bean-creation exception). Spring never silently converts `call` into `execution`.

The same applies to named `@Pointcut`:

~~~java
@Pointcut("cflow(execution(* demo.OrderService.submit(..)))")
public void underSubmitFlow() {
}
~~~

Spring AOP does not support `cflow` in pointcut expressions, even when the inner `execution(...)` expression is supported. `@Pointcut` only names/composes expressions; it does not add new join-point recognition capabilities to Spring proxies. This is an illustrative snippet inside an `@Aspect`, not meant to be added to section 6's working project.

If you want to test other unsupported designators with `AspectJExpressionPointcut`, simply swap `setExpression(...)` in the demo and keep the `IllegalArgumentException` catch. Some expressions also have syntax/parameter-type issues; use documentation examples and inspect the true root cause when debugging. Do not assume every parser error has the exact same message.

## 8. Translating Pointcut Designs to Spring AOP Capabilities

Not every requirement written with AspectJ keywords translates verbatim by swapping designator names. The table below distinguishes **author intent** from **Spring solutions**:

| Initial requirement | Unsupported designator | Approach in Spring AOP |
| --- | --- | --- |
| Log before a service method runs | `call` | Advise `execution(...)` on Spring beans, optionally combined with `bean(name)`/`within(...)` |
| Log calls to setter methods | `set` if referring to field assignment | `execution(* set*(..))` selects **setter methods**, does not intercept direct field assignments |
| Observe getter methods through proxy | `get` if referring to field read | `execution(* get*(..))` selects **getter methods**, does not intercept field reads |
| Run logic right after a Spring bean finishes init | `initialization`, `preinitialization` | Spring lifecycle callbacks or `BeanPostProcessor`, not AspectJ join points |
| Configure when class loads / static init | `staticinitialization` | Place initialization config in appropriate application startup/lifecycle; do not expect AOP proxies to intercept static initializers |
| Record exceptions thrown by a method | `handler` | `@AfterThrowing` on Spring method execution; does not intercept every `catch` handler |
| Select methods by layer | `withincode` | `execution(...)`/`within(...)` or `bean(...)` to scope the target layer; does not match by source call site |
| Depend on caller's call stack | `cflow`, `cflowbelow` | Consider explicit context propagation/adapters; if using Spring's Pointcut API, `ControlFlowPointcut` is a different mechanism with its own limits |
| Select methods by annotation on proxy `this` | `@this` | Consider `@target`, `@within`, `@annotation` per goal; do not treat them as byte-for-byte equivalents |
| Select code blocks carrying an annotation | `@withincode` | Mark advised methods with `@annotation` or classes with `@within`/`@target` and intercept via proxy |
| Custom runtime condition inside pointcut | `if` | Move condition into `@Around`/`@Before` advice code or appropriate Spring method selection; do not assume identical semantics |
| Select execution of another advice | `adviceexecution` | Use appropriate infrastructure instrumentation/observability instead of advising AOP internals |

**Note:** the table gives **redesign suggestions** for Spring AOP, without claiming `execution(get*(..))` equals field `get` or `@AfterThrowing` equals exception `handler`. If a requirement genuinely demands call-site, field-access, constructor, or lexical join points, Spring AOP's proxy limits are insufficient; **evaluate another mechanism with its own cost and characteristics**. This lesson does not implement mechanisms outside Spring AOP.

## 9. Typical Scenarios in Spring Applications

### 9.1. Logging Only Methods with `@Audited`

Instead of hoping `@withincode` checks annotations at call sites, mark the **exact method needing advice**:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface Audited {
}
~~~

and inside an aspect bean:

~~~java
@Before("@annotation(demo.Audited)")
public void beforeAudited() {
    System.out.println("AUDIT");
}
~~~

These are two illustrative snippets; import `java.lang.annotation.Retention`, `RetentionPolicy`, `Target`, `ElementType` for the annotation, and `@Aspect`/`@Before`/bean registration for the advice. They are not a standalone runnable project. `@annotation` selects only **annotated methods** when method execution goes through a Spring proxy.

### 9.2. Scoping by Bean Name

If services are named `orderService` and `paymentService`, use:

~~~java
@Before("execution(public * demo..service..*.*(..)) && bean(*Service)")
public void beforeBusinessCall() {
    // ...
}
~~~

This expression is illustrative only: the package syntax in `execution` must match the project's real package and bean names must match the `Service` suffix. `bean(*Service)` is a Spring-specific extension suitable when Spring-managed bean names follow a convention. It does not apply to objects created outside the container.

### 9.3. Scoping by Proxy Type

With a JDK dynamic proxy, `this(demo.OrderOperations)` can match the proxy by interface; `target(demo.OrderService)` matches the target implementation. With a CGLIB proxy, the proxy can also be a subclass of the target. Avoid confusing `@this` (unsupported) with `this` (supported), and avoid casting a JDK proxy to an implementation class.

### 9.4. Internal Calls Are Not Intercepted

~~~java
public class OrderService {
    public void batch() {
        this.submit("A-02");
    }

    public void submit(String orderId) {
        System.out.println("SERVICE: submit " + orderId);
    }
}
~~~

Even though `execution(* demo.OrderService.submit(..))` is a valid pointcut, calling `this.submit()` inside the target **does not go back through the Spring AOP proxy**. This is not because the `execution` designator is unsupported, but because of how the caller crosses the proxy boundary. The fix belongs in architecture—calling through another Spring-managed collaborator—not adding `call` to the pointcut.

## 10. Distinguishing Parser Errors from Non-Matching Pointcut Errors

When startup or method calls do not behave as expected, there are three distinct failure classes:

### A. Unsupported Designator

Signs:

- Pointcut contains `call`, `set`, `get`, `cflow`, or one of the 14 unsupported PCDs;
- `IllegalArgumentException` occurs while Spring prepares/parses the expression;
- The application may fail to initialize the aspect, auto-proxy creator, or context.

How to handle: find the **root cause**, identify the unsupported designator, and switch to a Spring AOP-compatible design; do not merely widen wildcards or edit method names.

### B. Supported Designator, Yet Invalid Expression or Non-Matching Method

Signs:

- Uses valid `execution(...)`/`@annotation(...)`/`within(...)`, yet package/class/method/annotation does not match, or syntax is malformed;
- Syntax errors can still throw parser exceptions; if syntax is valid but nothing matches, Spring may not create a proxy for that bean;
- No advice output appears because the advisor does not apply.

How to handle: verify full package, interface/implementation, runtime annotation, type/bean name, `(..)` parameter syntax, and where Spring registers the aspect.

### C. Advisor Matches, Yet Calls Do Not Go Through the Proxy

Signs:

- Bean has an advisor/proxy, yet code calls `this.submit()`, calls a raw target, calls a `final`/`private` method, or uses a `new` object outside Spring;
- Method logic runs without advice running, with no parser exception required;
- JDK/CGLIB proxy strategy and Spring bean scope affect which methods can be intercepted.

How to handle: measure `AopUtils.isAopProxy(bean)` and call methods **through the reference provided by the Spring container**; avoid concluding from a pointcut that merely looks right.

### Diagnostic Checklist

1. Read the **entire pointcut expression** in `@Pointcut`, `@Before`, XML, or the `AspectJExpressionPointcut` API.
2. Check every designator against Spring AOP's supported set: the nine standard PCDs plus the `bean()` extension.
3. If it is one of the 14 unsupported PCDs, fix the **design**; do not tweak Java imports trying to make the parser accept it.
4. Inspect the exception's **root cause**, especially `IllegalArgumentException` from the pointcut parser.
5. Verify Spring beans, `@EnableAspectJAutoProxy`, and that `@Aspect` is registered as a Spring bean.
6. Check proxy kind (`AopUtils.isAopProxy`, `isJdkDynamicProxy`, `isCglibProxy`); check whether the method is interceptable.
7. Call a method through the proxy and use a marker or counter inside the advice to verify execution.
8. For cases needing call-site/field-access/constructor interception, note Spring AOP's boundaries and choose an appropriate mechanism rather than pretending an equivalent PCD exists.
9. If the app also uses Spring Boot AOP auto-configuration, transactions, caching, or multiple contexts, check the **actual runtime ApplicationContext and configuration**.
10. After fixing, run an integration test performing external caller → Spring proxy → method; do not rely solely on IDE syntax highlighting.

## 11. Self-Check Questions

**1. Does Spring AOP support `call(...)` because it uses `@AspectJ` syntax?**  
No. Spring AOP understands **a subset** of PCDs and intercepts only method executions on Spring beans through proxies.

**2. Can `execution(* set*(..))` replace `set(* ..*)`?**  
They are not equivalent. `execution(set*(..))` matches only **setter method executions**; AspectJ's `set(...)` selects field writes.

**3. If you write `execution(...) && cflow(...)`, does Spring simply ignore `cflow` and run `execution`?**  
No. `cflow` is in the unsupported PCD group; the expression is rejected by the parser rather than silently ignored.

**4. `within(...)` is supported—what about `withincode(...)`?**  
`within` is supported to narrow type scope; `withincode` is rejected by the Spring AOP parser.

**5. Are `this(...)` and `@this(...)` the same?**  
No. In Spring AOP, `this` checks the proxy type; `@this` is an unsupported PCD.

**6. Why does Spring support `bean(name)` while native AspectJ weaving does not?**  
Spring AOP has the concept of **Spring bean names**/instances in a container; `bean` is a Spring extension, not a standard native AspectJ PCD.

**7. Since `ControlFlowPointcut` exists, is `cflow(...)` valid in `@Pointcut`?**  
No. `ControlFlowPointcut` belongs to Spring's programmatic Pointcut API and does not make the AspectJ `cflow` designator valid in Spring AOP's parser.

**8. Does an `IllegalArgumentException` from an unsupported PCD mean Spring AOP cannot run on the project?**  
No. It means that specific expression lies outside the subset of the language Spring AOP supports. Valid expressions like `execution && within` still run normally, as in section 6's project.

**9. When a method has a valid pointcut yet advice does not run, is an unsupported designator the only cause?**  
No. Also check whether the advisor matches, whether the bean is in the Spring context, and whether the call goes through the proxy.

**10. If you need to intercept field reads on every object, is switching from JDK proxy to CGLIB enough?**  
No. Both remain **Spring AOP proxies for method execution**. Switching proxy types does not turn field reads into join points.

## 12. Official Spring Framework Documentation

- [Spring Framework 6.2 — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html): list of 9 supported PCDs, 14 unsupported PCDs, `bean` extension, and Spring AOP method-execution notes.
- [Spring Framework 6.2 — @AspectJ support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj.html): Spring uses AspectJ syntax while runtime AOP remains Spring proxy-based.
- [Spring Framework 6.2 — Declaring Advice](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html): `@Before`/`@AfterThrowing`/`@Around` on valid execution join points.
- [Spring Framework 6.2 — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): JDK/CGLIB proxies, self-invocation, method restrictions.
- [Spring Framework 6.2 — Pointcut API](https://docs.spring.io/spring-framework/reference/6.2/core/aop-api/pointcuts.html): `AspectJExpressionPointcut` and Spring API `ControlFlowPointcut` (distinct from the `cflow` PCD).
