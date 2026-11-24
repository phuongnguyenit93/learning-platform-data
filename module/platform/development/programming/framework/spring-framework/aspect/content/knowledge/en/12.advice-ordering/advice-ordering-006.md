# Limits on Ordering Guarantees Among Same-Type Advice in Spring AOP

## 1. What Problem Does This Lesson Solve?

When multiple Spring AOP advice methods match a method execution of a Spring bean, learners often look at the order methods are written in a class and assume Spring invokes them from top to bottom. **That is not a Spring AOP guarantee.**

Specifically, when **two or more pieces of advice of the same kind**—such as two `@Before`, two `@After`, two `@AfterReturning`, two `@AfterThrowing`, or two `@Around` methods—**are declared in the same `@Aspect` class and apply to the same join point**, **the order between them is undefined** per the Spring Framework documentation. Java reflection does not provide a reliable contract to recover source declaration order for methods compiled by `javac`.

An error-prone example:

~~~java
@Aspect
@Component
public class OrderChecksAspect {

    @Before("execution(* demo.JobApi.run(..))")
    public void validate() {
        System.out.println("VALIDATE");
    }

    @Before("execution(* demo.JobApi.run(..))")
    public void audit() {
        System.out.println("AUDIT");
    }
}
~~~

This is an **illustrative fragment**: it requires appropriate imports, `JobApi`, and a Spring context. **You must not conclude that VALIDATE will always appear before AUDIT** simply because `validate()` is written above `audit()`.

If `audit()` assumes `validate()` has already checked permissions/inputs, results may break when changing compiler versions, Spring versions, or deployment environments.

Objectives of this README:

1. State the exact **ordering guarantees** Spring AOP provides, and what is **not guaranteed**.
2. Distinguish advice **of the same type in one aspect** from advice **in different aspects**.
3. Understand that `@Order` / `Ordered` **controls aspect-level precedence** rather than "numbering source methods" inside the same aspect.
4. Master rules **on the way in** and **on the way out** when advice wraps; avoid misreading `@After`.
5. Refactor into **one advice with sequential steps**, or into **multiple aspects with distinct orders**.
6. Run a **Java 17+ / Spring Framework 6.2.x / Maven** example for two `@Before` methods in **two ordered aspects**, with verifiable stdout.
7. Learn how to write tests: assert guaranteed contracts and **never write tests that depend on accidental behavior**.

**Special Note / Scope:** Focuses strictly on **Spring Framework proxy-based AOP** and the `@AspectJ` style supported by Spring. General AspectJ concepts are mentioned only when needed to explain Spring rules; standalone bytecode weaving is not covered.

## 2. Two Axes to Distinguish: Advice Kind and Declaration Location

There are two separate questions:

- **Are the advice methods of the same kind or different kinds?** For example, two `@Before` methods are **the same kind**; `@Before` and `@AfterReturning` are **different kinds**.
- **Are they in the same `@Aspect` class or in two different `@Aspect` classes?**

Classification table:

| Case | What Does Spring Guarantee? | How to Handle When Order Is a Business Requirement |
| --- | --- | --- |
| Two `@Before` in the same `@Aspect` class, both matching | **Undefined order between the two advice methods** | Merge into one `@Before` calling steps sequentially, or split aspects |
| Two `@AfterReturning` in the same `@Aspect` class, both matching | **Undefined order between the two same-type advice methods** | Merge or split into ordered aspects with `@Order` |
| Two `@Around` in the same `@Aspect` class, both matching | **Undefined order between the two same-type advice methods** | Consolidate logic into one `@Around` or split aspects |
| Two same-type advice methods in **two different aspects**, unordered | **Undefined order**, unless other precedence is configured | Assign explicit precedence |
| Two advice methods in two aspects, `@Order(10)` and `@Order(20)` | Aspect with **smaller value has higher precedence** | Use when clear concern boundaries and controlled order are needed |
| Advice of **different kinds** in the same `@Aspect` | Spring determines precedence by advice kind; execution timing follows before/after semantics | Understand finally-style `@After` and way-in/way-out |

**Do not equate "undefined order" with "Spring picks randomly on every request."** A JVM may produce what looks like a consistent order across thousands of calls, yet that **creates no contract** to rely on across upgrades or refactors.

## 3. What Exactly Does Spring Say About Same-Type Advice?

The Spring Framework documentation under **Declaring Advice → Advice Ordering** states clearly:

- When two pieces of advice of the same kind in **the same `@Aspect` class** both need to run at the same join point, **the order is undefined**.
- Reason: method declaration order in Java source cannot be reliably retrieved via reflection for `javac`-compiled classes.
- Spring recommends **combining related advice into one method** per aspect/join point, or **splitting them into separate `@Aspect` classes** and using `Ordered` or `@Order` at the aspect level.

Pay attention to the condition **"both apply to the same join point."** If two `@Before` methods have **mutually exclusive** pointcuts, they do not compete for order on the same call.

Example:

~~~java
@Before("execution(* demo.JobApi.run(..))")
public void beforeRun() {
    // Only when run(...) matches.
}

@Before("execution(* demo.JobApi.cancel(..))")
public void beforeCancel() {
    // Only when cancel(...) matches.
}
~~~

If `run` and `cancel` are two distinct methods, a single invocation will not trigger both advice methods in typical cases; there is no ordering conflict to resolve.

Conversely, when two pointcuts overlap:

~~~java
@Before("execution(* demo.JobApi.*(..))")
public void beforeAnyMethod() {
    // Matches every method on JobApi.
}

@Before("execution(* demo.JobApi.run(..))")
public void beforeRunOnly() {
    // Also matches run(...), overlapping with beforeAnyMethod().
}
~~~

Calling `run(...)` can trigger **both `@Before` methods**. If they reside in the same `@Aspect` class, do not rely on the declaration order of those two advice methods.

## 4. @Order Does Not Number Individual Advice Methods Within the Same @Aspect

In Spring, the standard way to establish precedence between **two aspects** is:

~~~java
@Aspect
@Component
@Order(10)
public class FirstAspect {
    @Before("execution(* demo.JobApi.run(..))")
    public void before() {
        System.out.println("FIRST");
    }
}
~~~

and another aspect:

~~~java
@Aspect
@Component
@Order(20)
public class SecondAspect {
    @Before("execution(* demo.JobApi.run(..))")
    public void before() {
        System.out.println("SECOND");
    }
}
~~~

**These are fragments to be placed in two respective files**, not a complete program. With two aspects of different precedence:

- `@Order(10)` has **higher precedence** than `@Order(20)` because the number is smaller.
- Two matching `@Before` advice methods that **do not throw exceptions** will be invoked on the way in according to precedence: **FIRST then SECOND**, followed by the target.
- When running real code, Spring must also instantiate the beans/aspects/advisors and the caller must call through the **Spring AOP proxy**.

**Putting `@Order` on individual advice methods inside one `@Aspect` is not a documented Spring solution to guarantee ordering among same-type advice in that class.** The safe approaches are **ordering at the aspect level** or **merging ordered steps into a single advice**.

Also avoid using:

- Method names like `aFirst`/`zLast` to force order.
- Method position in source code.
- Import order or class file order.
- Log appearance order from a single run.
- Custom annotations not read as precedence by the Spring advisor chain.

If `@Order` values are **equal**, do not treat the order between the two aspects as a stable contract. When specific ordering is required, give them **two distinct precedence levels**.

## 5. Order on the Way In and Way Out

Spring AOP operates as an interceptor chain around a method execution:

~~~text
Client
   |
   v
Aspect order=10 (higher priority)
   |
   v
Aspect order=20 (lower priority)
   |
   v
TARGET METHOD
   |
   v
Aspect order=20 (finishes inside)
   |
   v
Aspect order=10 (finishes outside)
   |
   v
Caller
~~~

Consequences:

- **On the way in:** higher-precedence advice typically runs **first**.
- **On the way out:** higher-precedence advice typically runs **last**, because it wraps the inner portion.
- This is the intuitive rule of **interceptor nesting**; do not infer that every advice runs in both directions. `@Before` only handles pre-execution; `@AfterReturning` only runs on normal return paths, etc.

With two `@Around` methods in two aspects:

~~~text
ORDER 10: around ENTER
  ORDER 20: around ENTER
    TARGET
  ORDER 20: around EXIT
ORDER 10: around EXIT
~~~

If both call `proceed()` once and the target returns normally, this order is explained by nesting. If the outer aspect **does not call `proceed()`**, the inner advisor and target **are not reached**.

**Note:** Do not use `@Order` to "force an `@AfterReturning` to run like `@Before`." `@Order` determines precedence between aspects; **advice kind** determines when code runs.

## 6. Precedence Within the Same @Aspect When Advice Kinds Differ

Spring Framework 6.2 publishes precedence among **different advice types** within one `@Aspect` (highest to lowest):

1. `@Around`.
2. `@Before`.
3. `@After`.
4. `@AfterReturning`.
5. `@AfterThrowing`.

**However, you must understand execution semantics rather than reading that sequence as a linear log order.** Per Spring, `@After` has **finally** semantics and **is actually invoked after `@AfterReturning` or `@AfterThrowing`** in the same aspect.

Illustrative example of an aspect with multiple advice types:

~~~java
@Aspect
@Component
public class TraceAspect {

    @Around("execution(* demo.JobApi.run(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("AROUND enter");
        try {
            return pjp.proceed();
        } finally {
            System.out.println("AROUND exit");
        }
    }

    @Before("execution(* demo.JobApi.run(..))")
    public void before() {
        System.out.println("BEFORE");
    }

    @AfterReturning("execution(* demo.JobApi.run(..))")
    public void afterSuccess() {
        System.out.println("AFTER RETURNING");
    }

    @After("execution(* demo.JobApi.run(..))")
    public void afterFinally() {
        System.out.println("AFTER FINALLY");
    }
}
~~~

This is an **illustrative class fragment**, requiring imports and a service/app context. When the **target returns normally and no other advice alters flow**, the wrapping logic can be understood as:

~~~text
AROUND enter
BEFORE
TARGET
AFTER RETURNING
AFTER FINALLY
AROUND exit
~~~

If the target throws an exception, `@AfterReturning` does not run, while `@After` with finally semantics still runs once execution reaches its scope. `@Around` can catch/transform exceptions, so you must inspect the advice body as well.

The main focus of this lesson is not memorizing a generic advice-type list, but **distinguishing the Spring-defined ordering among different types from the *undefined* ordering among multiple advice methods of the same type in one class**.

## 7. Runnable Maven Example: Two @Before Methods in Two Explicitly Ordered Aspects

To obtain stdout with **guaranteed order**, the main example uses:

- A Spring service bean implementing `JobApi`.
- `FirstBeforeAspect` as an `@Aspect` with `@Order(10)`.
- `SecondBeforeAspect` as another `@Aspect` with `@Order(20)`.
- Both have **one `@Before`** matching `JobApi.run(..)`.
- Client calls through the proxy from `AnnotationConfigApplicationContext`.

**Environment:** Java 17+, Maven 3.9+, Spring Framework 6.2.12, and AspectJ Weaver 1.9.24.

### 7.1. Project Structure

~~~text
spring-aop-advice-order/
├── pom.xml
└── src/main/java/demo/
    ├── JobApi.java
    ├── JobService.java
    ├── FirstBeforeAspect.java
    ├── SecondBeforeAspect.java
    ├── AppConfig.java
    └── App.java
~~~

### 7.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-advice-order</artifactId>
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
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.App</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` provides `ApplicationContext` and pulls in the needed Spring AOP modules. `aspectjweaver` allows Spring to read `@AspectJ` annotations and pointcut expressions. No AspectJ compiler or weaving is used in the example.

### 7.3. JobApi.java

~~~java
package demo;

public interface JobApi {
    String run(String jobId);
}
~~~

This is the public contract. Spring can create a JDK dynamic proxy when the implementation has an interface and CGLIB is not forced.

### 7.4. JobService.java

~~~java
package demo;

import org.springframework.stereotype.Service;

@Service
public class JobService implements JobApi {

    @Override
    public String run(String jobId) {
        System.out.println("TARGET run " + jobId);
        return "done:" + jobId;
    }
}
~~~

`@Service` is registered in the Spring context via component scanning. The target code simply prints a line and returns a `String`; no database or network is needed to observe ordering.

### 7.5. FirstBeforeAspect.java

~~~java
package demo;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Aspect
@Component
@Order(10)
public class FirstBeforeAspect {

    @Before("execution(* demo.JobApi.run(..))")
    public void before() {
        System.out.println("BEFORE priority10");
    }
}
~~~

`@Order(10)` is placed on the **aspect class**. This advice has higher precedence than the `@Order(20)` aspect. Do not interpret `10` as "run ten times," "wait ten milliseconds," or "line 10 order."

### 7.6. SecondBeforeAspect.java

~~~java
package demo;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Aspect
@Component
@Order(20)
public class SecondBeforeAspect {

    @Before("execution(* demo.JobApi.run(..))")
    public void before() {
        System.out.println("BEFORE priority20");
    }
}
~~~

Both `@Before` methods match `JobApi.run(..)`, but live in **two different `@Aspect` classes**. Because precedence is explicit, order is predictable.

### 7.7. AppConfig.java

~~~java
package demo;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackages = "demo")
@EnableAspectJAutoProxy
public class AppConfig {
}
~~~

`@ComponentScan` registers the service and both aspects. `@EnableAspectJAutoProxy` creates the appropriate AOP advisors/proxy. Putting `@Aspect` without registering the bean via `@Component` or `@Bean` will not bring the advice into the Spring context automatically.

### 7.8. App.java

~~~java
package demo;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class App {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            JobApi jobs = context.getBean(JobApi.class);

            System.out.println(
                    "IS_PROXY " + AopUtils.isAopProxy(jobs));

            String result = jobs.run("J-17");
            System.out.println("RESULT " + result);
        }
    }
}
~~~

The caller retrieves the Spring-managed bean by the `JobApi` interface, not via `new JobService()`, and does not cast the JDK proxy to the concrete implementation class.

Run in the directory containing `pom.xml`:

~~~bash
mvn -q clean compile exec:java
~~~

### 7.9. Expected Logical Stdout

~~~text
IS_PROXY true
BEFORE priority10
BEFORE priority20
TARGET run J-17
RESULT done:J-17
~~~

The output above is the **expected logical stdout of the example**, omitting Maven/Spring logging. The two `BEFORE` lines are ordered by **aspect-level `@Order`**, not source method order.

Explanation:

1. `IS_PROXY true`: Spring returns an AOP proxy because advisors match the service.
2. `BEFORE priority10` runs first due to higher precedence.
3. `BEFORE priority20` runs next.
4. `TARGET run J-17` appears only after both before advice methods return normally.
5. `RESULT done:J-17` is the value returned by the target and forwarded by the proxy.

If the `priority10` advice **throws an exception**, `priority20` and the target may not be reached along that call path. Precedence defines **sequence when control flow continues**, not a promise that every advice always executes regardless of exceptions.

## 8. Counterexample: Two @Before Methods in the Same Aspect

Suppose you **replace** `FirstBeforeAspect` and `SecondBeforeAspect` with a single aspect:

~~~java
package demo;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class AmbiguousBeforeAspect {

    @Before("execution(* demo.JobApi.run(..))")
    public void alpha() {
        System.out.println("ALPHA");
    }

    @Before("execution(* demo.JobApi.run(..))")
    public void beta() {
        System.out.println("BETA");
    }
}
~~~

This is a **separate file you can use when restructuring the demo**. To test it, **remove the two original aspect beans from the context** or disable their registration before registering `AmbiguousBeforeAspect`. Keeping all three adds extra advice and changes stdout.

You may observe either ordering:

~~~text
ALPHA
BETA
TARGET run J-17
~~~

or:

~~~text
BETA
ALPHA
TARGET run J-17
~~~

**These two blocks are only illustrative possibilities, not a single "expected output."** Spring documentation makes no commitment on which one is chosen. Even if several runs consistently produce `ALPHA` then `BETA`, that is still **not a contract** for production to depend on.

Adding `@Order(1)` to the **`AmbiguousBeforeAspect` class** only affects that aspect's precedence **relative to other aspects**; it does not make `alpha()` and `beta()` deterministically ordered inside the same class.

## 9. Approach 1: Merge into One Advice and Call Helpers Sequentially

If two steps **belong to the same concern** and have a clear dependency ("must validate before auditing"), the simplest solution is one advice:

~~~java
@Aspect
@Component
public class CombinedChecksAspect {

    @Before("execution(* demo.JobApi.run(..))")
    public void validateThenAudit() {
        validate();
        audit();
    }

    private void validate() {
        System.out.println("VALIDATE");
    }

    private void audit() {
        System.out.println("AUDIT");
    }
}
~~~

This is a **class fragment** requiring `@Aspect`, `@Component`, and `@Before` imports. It no longer creates two same-type advice methods; there is **one `@Before`** and two Java helper calls in an order **guaranteed by Java language semantics**:

~~~text
VALIDATE
AUDIT
TARGET run ...
~~~

If `validate()` throws an exception, `audit()` does not run and the target can be blocked—matching a policy of "do not audit a blocked operation," if that is indeed the requirement.

However, if auditing **must record failed validations as well**, design `try/catch/finally` according to business intent; **do not** rely on advice order or type alone to produce the desired behavior magically.

**Advantages of merging:** minimal order configuration, easy-to-read internal logic, easy to unit test with helpers/dependency injection.

**Trade-off:** two responsibilities belonging to two independent modules may become tightly coupled in one aspect; in that case, splitting into separate aspects can make more sense.

## 10. Approach 2: Split Aspects for Clear Concern Ordering

When validation and auditing are two independent concerns:

~~~text
ValidationAspect @Order(10)
           |
           v
AuditAspect @Order(20)
           |
           v
Business service
~~~

This is the exact pattern of the project in section 7. Each aspect has its own purpose, tests, and owner; Spring applies inter-aspect precedence.

Declaration template:

~~~java
@Aspect
@Component
@Order(10)
class ValidationAspect {
    @Before("execution(* demo.JobApi.run(..))")
    public void check() {
        // validation
    }
}

@Aspect
@Component
@Order(20)
class AuditAspect {
    @Before("execution(* demo.JobApi.run(..))")
    public void record() {
        // audit
    }
}
~~~

This is an **illustrative fragment with two package-private classes**, requiring imports and placement in appropriate files. Do not copy it into the section 7 project without removing the original aspects, as it adds extra advisors.

Use **distinct order values** to express boundaries. If security must run before an action with side effects, also check **advisor ordering with Spring Security/transaction/cache aspects**, not just two custom aspects.

**Important caveat:** `@Order` governs precedence among Spring aspects, but does not completely define the ordering of every `BeanPostProcessor`, servlet filter, method security interceptor, or transactional resource lifecycle. Each infrastructure layer has its own integration mechanism; integration tests on a real context are required.

## 11. Approach 3: One @Around Executing Multiple Steps Intentionally

When you need to control both "before" and "after" order, a single `@Around` can hold an explicit sequence:

~~~java
@Around("execution(* demo.JobApi.run(..))")
public Object trace(ProceedingJoinPoint pjp) throws Throwable {
    System.out.println("STEP-1 validate");
    System.out.println("STEP-2 start timer");

    try {
        Object result = pjp.proceed();
        System.out.println("STEP-3 success audit");
        return result;
    } finally {
        System.out.println("STEP-4 finish");
    }
}
~~~

This is a **method fragment inside an `@Aspect`**, requiring imports. When the target returns normally, the logical order is guaranteed by **Java statements**:

~~~text
STEP-1 validate
STEP-2 start timer
TARGET ...
STEP-3 success audit
STEP-4 finish
~~~

If `pjp.proceed()` throws an exception, `STEP-3 success audit` does not run, yet `finally` still executes.

Be careful:

- `@Around` can short-circuit if it omits `proceed()`, skipping the target and inner advisors.
- `proceed()` can be called multiple times, repeating the target and side effects.
- Advice returning `Object` must properly preserve the return contract.
- Do not use `@Around` solely to enforce ordering when a single `@Before` suffices.

Combining multiple steps into one method expresses a **strict sequence**, though it makes AOP logic heavier if it simultaneously logs, caches, retries, and manages transactions.

## 12. @After, @AfterReturning, @AfterThrowing, and Ordering to Understand

If two advice methods **of the same kind** live in the same `@Aspect`, for example:

~~~java
@AfterReturning("execution(* demo.JobApi.run(..))")
public void recordSuccess() {
    System.out.println("SUCCESS");
}

@AfterReturning("execution(* demo.JobApi.run(..))")
public void updateMetric() {
    System.out.println("METRIC");
}
~~~

then **SUCCESS before METRIC** is not guaranteed. If metrics must be recorded after successful auditing, merge into one `@AfterReturning` or split into aspects with `@Order`.

For two `@AfterThrowing` methods matching the same join point, the same principle applies: **the order between them in the same aspect is undefined**. Do not use source method order to assume which handler "processes the exception first."

For two `@After` methods in the same aspect, the order between those two `@After` advice methods is likewise **undefined**.

**Different kinds** have distinct semantics:

- `@AfterReturning`: runs when method execution completes **normally**.
- `@AfterThrowing`: runs when the invocation throws a matching exception; does not necessarily run if an inner `@Around` catches the exception and turns it into a normal value.
- `@After`: finally-style, runs after execution once the invocation has reached the advice, **regardless of normal or exceptional completion**, except on paths short-circuited by outer advice before it participates.
- `@Around`: decides whether to call `proceed()` and whether to handle/transform results or exceptions.

**Do not write a test asserting a single fixed global log list** if the context has multiple unordered aspects of the same kind. Ordering across different kinds has rules, yet concern ordering and exception flow must be evaluated against the actual advisor chain.

## 13. Why Does @After Usually Print After @AfterReturning?

Spring Framework 6.2 documentation distinguishes **precedence assignment** from **callback timing**. `@After` has **after finally semantics**, so within the same aspect it **actually runs after** the corresponding `@AfterReturning` or `@AfterThrowing` of that invocation.

If you read precedence from highest to lowest:

~~~text
@Around > @Before > @After > @AfterReturning > @AfterThrowing
~~~

and draw:

~~~text
TARGET
@After
@AfterReturning
~~~

that is an **incorrect** interpretation of Spring callback timing for the same-aspect case. Precedence governs nested interceptors; `@After` runs in the `finally` branch when the continuation within its scope finishes.

For this lesson's question, remember two separate conclusions:

1. **Different advice kinds:** Spring has defined precedence/semantics rules.
2. **Multiple advice methods of the same kind in the same aspect:** **no ordering guarantee**.

Do not use advice-kind rules to resolve two `@Before` or two `@After` methods of the same kind.

## 14. Case of Two Aspects Without @Order

Example of two aspects neither declaring order:

~~~java
@Aspect
@Component
class LoggingAspect {
    @Before("execution(* demo.JobApi.run(..))")
    public void before() {
        System.out.println("LOGGING");
    }
}

@Aspect
@Component
class TrackingAspect {
    @Before("execution(* demo.JobApi.run(..))")
    public void before() {
        System.out.println("TRACKING");
    }
}
~~~

This is a fragment with **two separate top-level classes**; it needs imports and Spring config. Two different aspects can still have **no guaranteed order** if precedence is not assigned.

Saying "Spring scans `LoggingAspect` first so LOGGING will definitely run first" is insufficient. Component scanning or alphabetical class names **are not an ordering contract between aspects**.

Replace with:

~~~java
@Aspect
@Component
@Order(10)
class LoggingAspect {
    // ...
}

@Aspect
@Component
@Order(20)
class TrackingAspect {
    // ...
}
~~~

This is a **declaration template**; add the advice bodies from the prior snippet if applied. `@Order(10)` takes higher priority than `@Order(20)` on the way in.

## 15. What If Two Aspects Have the Same @Order Value?

A configuration that easily causes confusion:

~~~java
@Aspect
@Component
@Order(100)
class AspectA {
    // ...
}

@Aspect
@Component
@Order(100)
class AspectB {
    // ...
}
~~~

Both aspects are given **the same priority 100**. Do not read that number as a unique sequence ID. When there is a tie, do not rely on an accidental output order to claim a business requirement of "A before B."

To establish a clear contract:

~~~java
@Aspect
@Component
@Order(100)
class AspectA {
    // ...
}

@Aspect
@Component
@Order(200)
class AspectB {
    // ...
}
~~~

`AspectA` has higher precedence than `AspectB`. Numbers can follow module conventions; they do not have to be 1 and 2, as long as the comparison relationship is unambiguous.

In large systems, avoid scattering order numbers across modules without a documented convention. You can define constants such as `SECURITY_ORDER` and `AUDIT_ORDER` for consistency, while understanding that advisors from Spring Framework/starters also have their own orders.

## 16. When Earlier Advice Throws an Exception or Around Short-Circuits

Guaranteed order **does not mean every advice is guaranteed to run**.

### 16.1. High-Priority @Before Throws an Exception

~~~text
@Order(10) @Before: permission check -> throw AccessDenied
@Order(20) @Before: record event
TARGET: business processing
~~~

If higher-priority advice throws an exception, the chain can stop before lower-priority advice and the target. Do not write a test expecting `@Order(20)` to run in an early-rejection exception scenario.

### 16.2. High-Priority @Around Skips proceed

~~~java
@Around("execution(* demo.JobApi.run(..))")
public Object gate(ProceedingJoinPoint pjp) throws Throwable {
    if (maintenanceMode) {
        return "maintenance";
    }
    return pjp.proceed();
}
~~~

This is a **fragment** needing `maintenanceMode` and appropriate imports. If an outer `@Around` returns early without **calling `proceed()`**, inner advice and the target may **not be triggered**.

### 16.3. Two Same-Type @Around Methods in One @Aspect

If the same class has two `@Around` methods matching the same operation and one sometimes returns early, undefined ordering can have drastic effects: whichever method wraps outside decides whether the other gets to run.

In this case it is **especially important** to merge into one around advice or split into ordered aspects with integration tests. Never treat two `@Around` methods as "two independent handlers guaranteed to both be called."

## 17. Difference Between @Order and @Priority/Ordered

In Spring AOP advice ordering:

- `@Order(value)`: the common way to assign order to an **aspect class** as in the demo.
- `Ordered`: an aspect can implement `org.springframework.core.Ordered` and provide `getOrder()`.
- **Smaller numeric value → higher precedence**.
- When advice methods sit in **the same aspect class and have the same type**, the order between them remains **undefined**.
- A bean can participate in multiple kinds of ordering in a Spring context (`BeanPostProcessor`, event listeners, transaction interceptors, etc.). Do not assume they all share one identical contract.

Skeleton example:

~~~java
@Aspect
@Component
public class OrderedAspect implements Ordered {

    @Override
    public int getOrder() {
        return 10;
    }

    @Before("execution(* demo.JobApi.run(..))")
    public void before() {
        System.out.println("ORDERED ASPECT");
    }
}
~~~

This is a **class fragment**, requiring `org.springframework.core.Ordered` and annotation imports. `Ordered` is an alternative to `@Order` on an aspect in the example; do not copy it into the runnable project simultaneously if you want to preserve the expected stdout.

If order must depend on runtime configuration, implementing `Ordered` can be helpful. Yet complex dynamic ordering is hard to debug; explicit constants or `@Order` are usually sufficient.

## 18. XML Schema AOP Has Its Own Rules

This lesson focuses on `@Aspect` annotation style, yet you should avoid confusing it with Spring **schema-based AOP**:

~~~xml
<aop:aspect id="example" ref="exampleBean">
    <aop:before pointcut-ref="serviceOp" method="one"/>
    <aop:before pointcut-ref="serviceOp" method="two"/>
</aop:aspect>
~~~

This is only an **XML fragment**, not a complete valid Spring XML file. Spring documentation notes that **within the same `<aop:aspect>` in schema-based AOP**, precedence is determined by **the declaration order of the advice elements**. That rule **differs** from annotation-style `@Aspect` using Java reflection.

**Do not use XML element order to prove the order of two annotated Java methods.** If using `@Aspect` on Spring beans, apply the rules from earlier sections. If using schema-based AOP, consult the XML configuration documentation.

## 19. Properly Testing Spring AOP Ordering

A reliable test suite should distinguish:

- **Cases with defined order:** test the specific output order.
- **Cases with undefined order:** do not hardcode an accidental order; test that both advice methods **ran** when allowed to run, without asserting relative position between them.
- **Cases without proceed / with exceptions:** test that only advice on the executed control path ran.
- **Cases with multiple advisors:** test against a real application context, not just an isolated aspect unit test.

### 19.1. Testing the Section 7 Project

Assuming variable `jobs` is obtained from `ApplicationContext`:

~~~java
String result = jobs.run("T-1");

if (!"done:T-1".equals(result)) {
    throw new AssertionError("Wrong result");
}
~~~

This is a **result-checking fragment**, not a standalone class. To assert the order of `BEFORE priority10` and `BEFORE priority20`, it is better to inject a `TraceRecorder` into both aspects, store events, and compare order in an integration test rather than relying on console logs that can be affected by other system logging.

### 19.2. TraceRecorder for Integration Tests

A minimal recorder:

~~~java
@Component
public class TraceRecorder {
    private final List<String> events = new CopyOnWriteArrayList<>();

    public void record(String event) {
        events.add(event);
    }

    public List<String> snapshot() {
        return List.copyOf(events);
    }
}
~~~

This is a **class fragment**, requiring `java.util.List`, `java.util.concurrent.CopyOnWriteArrayList`, and `org.springframework.stereotype.Component` imports. It can be constructor-injected into both aspects to record events.

After a valid call, a test can assert:

~~~java
List<String> expected = List.of(
        "priority10",
        "priority20",
        "target"
);

if (!expected.equals(recorder.snapshot())) {
    throw new AssertionError("Incorrect advice order");
}
~~~

Note: for this snippet to make sense, the target must also be updated to record the `target` event. If a real project has other advisors intercepting exceptions or recording additional events, expectations must be adjusted to match the **actual chain**. These fragments illustrate testing techniques and are **not the standalone runnable source** created in section 7.

### 19.3. Never Test Undefined Order Using a Fixed Sequence

If you only have `AmbiguousBeforeAspect` with two same-type advice methods `alpha` and `beta`, a test like the following makes a false assumption:

~~~java
assertEquals(
    List.of("ALPHA", "BETA"),
    recorder.snapshot()
);
~~~

This is a **JUnit fragment**, requiring JUnit and a recorder in the test. It might pass on your current machine yet fail in another environment even while Spring AOP obeys its contract. When there is no defined order, only assert the **presence** of both events (if they execute normally), not their relative order.

## 20. Common Pitfalls

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Two `@Before` methods swap order after another build | Same type in the same `@Aspect` has no guaranteed order | Merge advice or split into aspects with `@Order` |
| `@Order` on class yet two same-type methods still swap | `@Order` does not sort same-type methods internally | Use one advice with sequential helper calls |
| Two aspects run "alphabetically" in dev but differ in CI | No precedence assigned between aspects | Distinct `@Order` values |
| Two aspects both have `@Order(5)` | Tied precedence; order cannot be assumed | Use distinct values |
| `@After` expected to run before `@AfterReturning` | Confused precedence with callback order | Remember `@After` has finally semantics |
| Lower-order aspect finishes after higher-order on the way out | Higher precedence wraps outside so it exits last | Sketch interceptor nesting |
| Lower-priority advice does not run | Outer advice threw an exception or omitted `proceed` | Check exception/continuation path |
| Target does not run even though `@Before` matched | Outer `@Around` short-circuited | Inspect around code and order |
| Private/final method is not advised | Spring proxy limitation | Design methods to be interceptable |
| Advice does not run in `this.method()` | Self-invocation bypasses proxy | Call through a Spring-managed dependency |
| `@Aspect` present yet no advice runs | Aspect not a Spring bean or AOP not enabled | `@Component`/`@Bean` and `@EnableAspectJAutoProxy` |
| One business operation logs multiple times | Multiple advisors share pointcut or method actually called repeatedly | Inspect advisors/pointcuts and call path |
| Ordering unit test passes while integration test fails | Real context has additional advisors and ordering | Test with a production-like Spring context |
| Copied XML ordering assumptions to annotation style | Schema-based AOP has different rules | Apply documentation matching the actual configuration |
| Two `@Around` methods in one aspect cause confusing side effects | Undefined nested order and `proceed` may be skipped/repeated | Merge into one around or split + `@Order` |
| Unsure whether security or transaction runs first | Infrastructure advisors have their own orders | Verify precedence and integration behavior |
| Switched JDK proxy to CGLIB to "fix order" | Proxy type does not create source-declaration order | Fix aspect/advice design, do not switch proxies just for ordering |

## 21. Decision Workflow When Multiple Advice Methods Match

**Step 1 — Identify the join point.** Do the pointcuts genuinely select the **same Spring-managed method execution**? If not, there is no ordering issue on the same invocation.

**Step 2 — Identify advice types.** Two `@Before` or two `@AfterReturning` methods are the same type; `@Before` and `@Around` are different types.

**Step 3 — Identify declaration locations.** Same `@Aspect` class, or different aspect classes?

**Step 4 — Check business requirements.** If order is purely cosmetic logging with no dependency, you may not need to enforce order. If audit/security/validation/retry/cache depend on each other's outcomes, order must be explicit.

**Step 5 — Choose the fix.**

- Two dependent operations within **one concern** → **one advice** with ordered Java steps.
- Two independent concerns → **split aspects** and assign precedence via `@Order` or `Ordered`.
- Multiple advice types → understand Spring precedence and actual callback semantics, especially `@After`.
- Third-party advisors → check their configuration/order; do not only set order on your own aspects while ignoring framework infrastructure.

**Step 6 — Use integration tests.** Assert **guaranteed** ordering, and test exception, retry, and short-circuit branches.

**Step 7 — Document conventions.** Maintain a shared priority order for security, validation, auditing, transactions, and tracing if required by business logic; avoid accidental duplicate values.

## 22. Pre-Production Checklist

1. Are there multiple advice methods of the same type matching the same join point?
2. Do they reside in the same `@Aspect` class?
3. If so, have you avoided relying on Java source/reflection order?
4. If logic requires order, have you merged them into one advice or split aspects?
5. If aspects are split, does each aspect have a distinct `@Order`/`Ordered` without ties?
6. Is it understood that **smaller order value means higher precedence**?
7. Have you checked order on both the way in and way out, rather than only one direction?
8. For `@After` and `@AfterReturning`, have you accounted for finally semantics?
9. If `@Around` skips `proceed` or throws, are inner advice methods skipped cleanly?
10. Is `this.method()` self-invocation bypassing the Spring proxy?
11. Are other Spring Security, transaction, or cache advisors active in the context?
12. Have you tested with a full Spring `ApplicationContext` and the actual proxy type?
13. Have you tested both success and exception paths, not just a single happy path?
14. Have you avoided confusing schema-based XML AOP ordering with annotation-based `@Aspect`?
15. Do README/tests avoid asserting a fixed stdout for **unordered** advice of the same type?

## 23. Self-Assessment Questions

**1. Are two `@Before` methods in the same `@Aspect` class guaranteed to run in declaration order?**

No. If both match the same join point, Spring Framework leaves the order between them undefined.

**2. If an `@Aspect` class has `@Order(1)`, are two `@Before` methods inside it ordered internally?**

No. `@Order` sets aspect-level precedence relative to other aspects; it does not turn the order of two same-type methods into a contract.

**3. What is the simplest approach when you must validate and then audit in strict sequence?**

Merge into a single advice and call `validate()` then `audit()` in Java sequence, if that fits a single cohesive concern.

**4. When should you split aspects and use `@Order`?**

When two concerns are relatively independent yet require explicit precedence between them.

**5. Between `@Order(10)` and `@Order(20)`, which aspect has higher priority?**

`@Order(10)`, because in Spring smaller order values have higher precedence.

**6. On the way out of two nested `@Around` methods, does the higher-priority aspect finish first or last?**

Usually **last** relative to the lower-priority aspect, because it wraps outside—assuming both call `proceed` and do not otherwise alter flow.

**7. Does `@After` in the same aspect run before `@AfterReturning` just because the precedence list puts `@After` first?**

No. `@After` has finally semantics and is actually called after `@AfterReturning`/`@AfterThrowing` when those apply.

**8. If two aspects have no `@Order`, what order does Spring commit to?**

No guaranteed order, unless precedence is configured through another mechanism.

**9. Are two aspects both annotated with `@Order(100)` guaranteed to run by class name?**

No. If order matters, assign distinct precedence values or merge logic appropriately.

**10. If a high-priority around advice does not call `proceed()`, will an inner before advice run?**

No, continuation does not reach it because around short-circuited before invoking the inner chain.

**11. Why is running the program 1,000 times and seeing the same order still insufficient?**

Because behavior can appear accidentally stable without being guaranteed by the Spring API/documentation, so it cannot be treated as a contract across environments.

**12. Does schema-based AOP share the same advice-method ordering rules as annotation style?**

Not entirely. With XML `<aop:aspect>`, the declaration order of advice elements plays a role in precedence; that rule does not apply verbatim to Java `@Aspect`.

## 24. Official Spring Documentation

- **Spring Framework 6.2 — Declaring Advice / Advice Ordering:** https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html
- **Spring Framework — Declaring an Aspect:** https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/at-aspectj.html
- **Spring Framework — @AspectJ-style AOP Support:** https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html
- **Spring Framework — Proxying Mechanisms:** https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- **Spring Framework 6.2 — Schema-based AOP / Advice Ordering:** https://docs.spring.io/spring-framework/reference/6.2/core/aop/schema.html
- **Spring Framework — Order annotation:** https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/annotation/Order.html
- **Spring Framework — Ordered interface:** https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/Ordered.html

**Conclusion:** In Spring `@AspectJ`-style AOP, **multiple advice methods of the same kind in a single `@Aspect` applying to the same method execution have no guaranteed order**. To achieve reliable business sequencing, **merge steps into one advice**, or **split into multiple aspects and specify precedence with `@Order`/`Ordered`**. When multiple advice types participate, evaluate **way-in/way-out flow, finally semantics, and `proceed()`**, rather than treating source code order as a Spring rule.
