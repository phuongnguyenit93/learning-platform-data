# Inherited methods, interface default methods, and annotation placement in Spring AOP

## 1. Scope and objectives

When working with Spring AOP, a method call may travel through a **JDK dynamic proxy** or a **CGLIB class-based proxy**. That method might be declared directly on the target class, **inherited from a superclass**, or provided as an **interface default method**. Meanwhile, annotations used to define advice or activate Spring mechanisms may sit on the interface, implementation, superclass, or method.

Four questions must be kept separate:

1. **Is the client calling through a Spring proxy?** Without entering a proxy, Spring AOP does not automatically intercept a call just because the method has an annotation.
2. **Is the method part of the API the proxy can intercept?** With JDK proxies, the call must target a public method exposed on a proxied interface; with CGLIB, the method must be overridable by the proxy subclass.
3. **Does the pointcut match the actual execution?** Check method declaring type, target class, signature, annotations, and Spring AOP expressions.
4. **Where does the framework look up annotations?** Java reflection, Spring merged-annotation utilities, `@annotation` pointcuts, and modules like transactions have metadata lookup rules that are not identical.

This lesson analyzes these scenarios solely within **Spring Framework/Spring AOP proxy-based interception**. General Aspect theory or AspectJ compile-time/load-time weaving are outside the focus.

## 2. Identifying the three method origins

Consider an interface with a default method and an implementation class inheriting a method from a superclass:

```java
public interface CustomerApi {
    String inherited(String id);

    default String fromDefault(String id) {
        return "DEFAULT:" + id;
    }

    String explicit(String id);
}

public class BaseCustomerService {
    public String inherited(String id) {
        return "BASE:" + id;
    }
}

public class CustomerService
        extends BaseCustomerService implements CustomerApi {

    @Override
    public String explicit(String id) {
        return "IMPL:" + id;
    }
}
```

These are **three distinct method categories on the same target object**:

| Method | Where the code lives | Why is it callable from clients? |
| --- | --- | --- |
| `inherited(String)` | `BaseCustomerService` (superclass) | `CustomerService` inherits the public method and satisfies `CustomerApi` |
| `fromDefault(String)` | `CustomerApi` (interface default method) | Interface supplies a default implementation not overridden by the class |
| `explicit(String)` | `CustomerService` | Implementation declares/overrides it directly |

**Where code is declared does not uniquely decide whether advice runs.** Spring AOP needs to intercept calls **passing through the proxy** and resolve matching advisors for the method. Inherited methods or default methods are not automatically excluded from AOP merely because their bodies are not written directly in the leaf class.

With Java reflection, you can inspect the origin:

```java
Method m1 = CustomerService.class.getMethod("inherited", String.class);
System.out.println(m1.getDeclaringClass().getSimpleName());
// BaseCustomerService

Method m2 = CustomerApi.class.getMethod("fromDefault", String.class);
System.out.println(m2.isDefault());
// true
```

These are **illustrative snippets**, requiring `import java.lang.reflect.Method` and the types defined above. `getDeclaringClass()` shows the class/interface declaring the resolved method; it **does not answer** whether Spring created a proxy or whether a pointcut matched.

## 3. How do JDK and CGLIB differ for inherited methods?

### 3.1. JDK dynamic proxy

A JDK proxy does not extend `CustomerService`. It implements the interfaces Spring exposes, such as `CustomerApi`. Because `CustomerApi` declares `inherited(String)`, clients can invoke it through the proxy:

```text
Client (CustomerApi)
        |
        v
JDK proxy.inherited("A")
        |
        v
Spring AOP advice / interceptor
        |
        v
CustomerService target
        |
        v
BaseCustomerService.inherited("A")
```

Here, **the implementation lives in the superclass**, yet external calls can still be intercepted by Spring AOP because the method **is declared on the proxied interface**.

If the superclass has a public method `onlyInBase()` that `CustomerApi` **does not expose**, a client holding the JDK proxy cannot invoke `onlyInBase()` by forcing a cast from the JDK proxy to `CustomerService`. That call is not part of the API exposed by the JDK proxy; attaching advice to the method does not add methods to a proxy interface.

### 3.2. CGLIB class-based proxy

With `@EnableAspectJAutoProxy(proxyTargetClass = true)`, Spring can create a proxy by subclassing `CustomerService`. The subclass proxy can intercept overridable methods, including public methods **inherited from a superclass**, provided method modifiers/visibility and pointcuts match.

```text
Client (CustomerService)
        |
        v
CGLIB proxy extends CustomerService
        |
        v
Spring AOP advice / interceptor
        |
        v
Target CustomerService
        |
        v
BaseCustomerService.inherited("A")
```

An inherited method marked `final` **cannot be overridden** by CGLIB to insert an interceptor, regardless of annotations or matching pointcuts. Likewise, `private` methods are not inherited/overridable, and a `final class` cannot serve as a superclass for a CGLIB proxy.

**Takeaway for inherited methods:** check **proxy API and overridability**, then check **the pointcut**. Never use "the method wasn't overridden in the implementation so Spring AOP skips it" as a general rule.

## 4. Interface default methods from Spring AOP's perspective

A Java interface can declare:

```java
public interface CustomerApi {
    default String fromDefault(String id) {
        return "DEFAULT:" + id;
    }
}
```

A default method is a method **whose implementation is supplied by the interface**. It differs from an abstract interface method, yet remains a public method in the interface's contract.

In Spring AOP:

- **JDK proxy:** a default method belongs to the proxied interface. A client call through the proxy can enter the invocation handler/AOP chain; Spring then proceeds to execute the default implementation on the target unless short-circuited by advice.
- **CGLIB proxy:** the proxy is a subclass of the target. Interface default methods appear as methods inherited from the interface; actual interceptability depends on proxy conditions, target, signature, and Spring version. When exact behavior matters, verify it in a test context with your chosen proxy strategy.
- **Being `default` does not automatically add advice:** if no pointcut matches, the call executes normally without business advice.
- **Default methods can call other methods:** calls made **once execution has entered the target** must not be assumed to count as new calls through the Spring proxy. If a second call needs its own interceptor, extract it to another Spring bean so clients/collaborators call through a proxy.

Notably, **Spring AOP does not apply advice to interface declarations themselves**. It operates on *method executions* whose calls pass through a Spring proxy. Placing an implementation inside an interface does not turn `@AspectJ` pointcuts into bytecode weaving on the interface.

### What if the default method is overridden?

```java
interface CustomerApi {
    default String fromDefault(String id) {
        return "DEFAULT:" + id;
    }
}

class CustomerService implements CustomerApi {
    @Override
    public String fromDefault(String id) {
        return "OVERRIDE:" + id;
    }
}
```

In this illustrative snippet, the executing implementation is `CustomerService.fromDefault(...)`. Do not assume annotations or logic on the interface default method carry identical effect across every Spring feature; annotation lookup depends on the specific matcher/metadata source. Verify the actual implementation, proxy method, and annotation lookup of the feature in use.

## 5. Runnable Java 17+ example: inheritance, default methods, and annotations

The experiment uses **Spring Framework 6.2.19, Java 17+, Maven**. It creates a **JDK dynamic proxy** to keep interface-based routing explicit and avoid relying on generated proxy class names.

Three methods are called from the client:

1. `inherited()`: implementation lives in the superclass, while the interface exposes the signature.
2. `fromDefault()`: default implementation lives in the interface.
3. `marked()`: implementation class overrides it directly and carries custom annotation `@TraceCall`.

The aspect uses a pointcut by **method execution name** to make it easy to see all three calls traverse the proxy; a subsequent check inspects **annotation placement via Java reflection**. Separating these avoids confusing name-based pointcuts with `@annotation` metadata matching algorithms.

### 5.1. Project structure

```text
spring-aop-method-boundaries/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── MethodBoundaryDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-method-boundaries</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.19</version>
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
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.MethodBoundaryDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/MethodBoundaryDemo.java`:

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

public class MethodBoundaryDemo {

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    public @interface TraceCall {
    }

    public interface CustomerApi {
        String inherited(String id);

        default String fromDefault(String id) {
            System.out.println("TARGET default " + id);
            return "DEFAULT:" + id;
        }

        String marked(String id);
    }

    public static class BaseService {
        public String inherited(String id) {
            System.out.println("TARGET inherited " + id);
            return "BASE:" + id;
        }
    }

    public static class CustomerService
            extends BaseService implements CustomerApi {

        @Override
        @TraceCall
        public String marked(String id) {
            System.out.println("TARGET marked " + id);
            return "MARKED:" + id;
        }
    }

    @Aspect
    public static class TraceAspect {
        @Before(
            "execution(* demo..*.inherited(..)) || " +
            "execution(* demo..*.fromDefault(..)) || " +
            "execution(* demo..*.marked(..))"
        )
        public void trace(JoinPoint joinPoint) {
            System.out.println("ADVICE " + joinPoint.getSignature().getName());
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy(proxyTargetClass = false)
    public static class Config {
        @Bean
        public CustomerApi customerApi() {
            return new CustomerService();
        }

        @Bean
        public TraceAspect traceAspect() {
            return new TraceAspect();
        }
    }

    public static void main(String[] args) throws Exception {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            CustomerApi bean = context.getBean(CustomerApi.class);

            System.out.println("JDK_PROXY="
                    + AopUtils.isJdkDynamicProxy(bean));
            System.out.println("INHERITED_DECLARED_IN="
                    + CustomerService.class
                            .getMethod("inherited", String.class)
                            .getDeclaringClass().getSimpleName());
            System.out.println("INTERFACE_DEFAULT="
                    + CustomerApi.class
                            .getMethod("fromDefault", String.class)
                            .isDefault());
            System.out.println("ANNOTATION_ON_INTERFACE="
                    + CustomerApi.class
                            .getMethod("marked", String.class)
                            .isAnnotationPresent(TraceCall.class));
            System.out.println("ANNOTATION_ON_IMPL="
                    + CustomerService.class
                            .getMethod("marked", String.class)
                            .isAnnotationPresent(TraceCall.class));

            System.out.println("RESULT " + bean.inherited("A"));
            System.out.println("RESULT " + bean.fromDefault("B"));
            System.out.println("RESULT " + bean.marked("C"));
        }
    }
}
```

Run in the project directory:

```bash
mvn -q compile exec:java
```

Stdout lines **printed by the program itself** (Maven or logging library messages may appear additionally):

```text
JDK_PROXY=true
INHERITED_DECLARED_IN=BaseService
INTERFACE_DEFAULT=true
ANNOTATION_ON_INTERFACE=false
ANNOTATION_ON_IMPL=true
ADVICE inherited
TARGET inherited A
RESULT BASE:A
ADVICE fromDefault
TARGET default B
RESULT DEFAULT:B
ADVICE marked
TARGET marked C
RESULT MARKED:C
```

Points to match against the output:

- `CustomerService` **does not redeclare** `inherited()`, yet the method is still called through `CustomerApi`; advice prints before the implementation inherited from `BaseService`.
- `fromDefault()` has its body in the interface. The JDK proxy receives the call and Spring has the chance to apply advisors before the default method executes on the target.
- `TraceCall` sits on `CustomerService.marked()`, **not on `CustomerApi.marked()`**. The two annotation inspection lines reflect the difference between method declarations on the interface vs. implementation.
- Advice in the example uses `execution(...)` by **method name**, so `ADVICE marked` **does not yet prove** an `@annotation(TraceCall)` pointcut would behave identically across all proxy types/annotation placements.

### 5.2. Switching to CGLIB to test

In `Config`, change to:

```java
@EnableAspectJAutoProxy(proxyTargetClass = true)
```

Then replace the proxy observation check with:

```java
System.out.println("CGLIB_PROXY="
        + AopUtils.isCglibProxy(bean));
```

These are **two small replacement snippets**, not standalone code. When the target class is eligible for subclassing, Spring can create a CGLIB proxy. Rerun all three calls in the same context and observe the trace rather than assuming interface default method matching is identical across all proxy strategies.

## 6. Annotation placement: what does Java actually see?

### 6.1. Annotation on the implementation method

```java
public interface CustomerApi {
    void submit();
}

public class CustomerService implements CustomerApi {
    @TraceCall
    @Override
    public void submit() {
        // business logic
    }
}
```

This is a clear option if you want metadata declared alongside **the actual implementation**. With JDK proxies, client calls carry the interface's `Method` reflection object, while Spring can locate the **most specific method** on the target class to check for matches.

Still, do not assume every custom annotation resolver automatically walks from interface to implementation. Place annotations where **the Spring feature you are using** officially reads them, and verify with tests.

### 6.2. Annotation placed only on the interface method

```java
public interface CustomerApi {
    @TraceCall
    void submit();
}

public class CustomerService implements CustomerApi {
    @Override
    public void submit() {
        // business logic
    }
}
```

Standard Java reflection distinguishes `CustomerApi.submit()` from `CustomerService.submit()`. **Method annotations are not automatically "inherited" just because a class implements an interface**. Consequently, when a framework inspects annotations on the implementation, it may not see an annotation on the interface unless it actively searches the hierarchy/interfaces.

This matters especially if pointcuts use `@annotation(...)` or if a framework feature reads annotations on its own. Do not equate `@TraceCall` with dedicated Spring annotations backed by specialized metadata resolvers.

### 6.3. Annotation on a superclass method

```java
public class BaseService {
    @TraceCall
    public void submit() {
        // base processing
    }
}

public class CustomerService extends BaseService {
    // Does not override submit()
}
```

When the subclass **does not override**, `CustomerService.class.getMethod("submit")` can return the method declared on the superclass carrying that annotation.

If the subclass **overrides** without re-annotating:

```java
public class CustomerService extends BaseService {
    @Override
    public void submit() {
        // different processing
    }
}
```

then the subclass's `Method` reflection object is **a distinct method**, and `isAnnotationPresent(TraceCall.class)` on that `Method` does not return `true` automatically just because the parent method was annotated. Spring may look up annotations across the hierarchy in certain utilities or features, yet that lookup behavior must be verified.

### 6.4. `@Inherited` does not apply to method annotations

In Java, `java.lang.annotation.Inherited` affects queries for annotations **on classes**, and only across eligible superclass/subclass relationships. It does not cause **method annotations** to be inherited across overrides, nor does it make interface annotations inherited by classes by default.

Therefore, the following does not solve annotations on interface methods:

```java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface ServiceMarker {
}
```

This is an **illustrative annotation on `TYPE`**, not `@TraceCall` for `METHOD`. The `@Inherited` meta-annotation does not replace the method/interface annotation lookup that Spring may need to perform.

## 7. `execution` and `@annotation` in Spring AOP are not the same

Two pointcuts easily confused:

```java
@Before("execution(* demo..*.submit(..))")
public void bySignature() {
    // runs for method execution matching the signature
}

@Before("@annotation(demo.TraceCall)")
public void byAnnotation() {
    // runs for method execution matching the annotation per Spring AOP matcher
}
```

These are **two illustrative advice methods**, not a standalone compilable program. When placed inside an `@Aspect` bean, they use different matching mechanisms:

| Pointcut | Focus | What to check |
| --- | --- | --- |
| `execution(...)` | Method execution signature, modifiers, return type, name/args/declaring type pattern | Types and methods recognized by Spring AOP, and whether calls traverse the proxy |
| `@annotation(...)` | Annotation on the executed method per matcher | Where the annotation sits, target-specific method, and lookup semantics |
| `@within(...)` | Annotated type, restricting executions within that type | Which class/interface has the annotation; whether inherited methods fall in match scope |
| `@target(...)` | Class of the evaluated target object carrying the annotation | Target class and annotation semantics |
| `this(Type)` / `target(Type)` | Type of the proxy / target | JDK proxy is not a subclass of the implementation |

**Do not fix a non-matching `@annotation` by randomly moving annotations between interface and implementation.** First determine which `Method` Spring inspects and which feature is active (AOP pointcut vs. an annotation-specific interceptor).

One diagnostic check is taking the interface method and resolving the implementation method:

```java
Method interfaceMethod =
        CustomerApi.class.getMethod("submit");

Method targetMethod =
        AopUtils.getMostSpecificMethod(
                interfaceMethod, CustomerService.class);
```

This is an **illustrative API snippet** (requiring `java.lang.reflect.Method` and `AopUtils` imports). `getMostSpecificMethod(...)` locates the method on the target class when present. It **does not** mean Spring always uses that exact single `Method` for every annotation type or every scenario.

## 8. Spring Framework annotations must be evaluated by their specific feature

Not every annotation that triggers advice is handled solely by an AspectJ `@annotation` pointcut. For example:

- **`@Transactional`** is resolved by transaction metadata infrastructure via `TransactionAttributeSource`, after which Spring applies transaction interceptors/proxies. Spring recommends placing the annotation on concrete classes/methods when possible to avoid differences across proxy/processing modes. Modern Spring versions may support certain interface placements in proxy mode; that **does not establish a universal rule for custom annotations**.
- **`@Cacheable`** is handled by caching infrastructure with its own metadata lookup, cache-key evaluation, and proxy handling. Whether `@Cacheable` on an interface or implementation behaves as expected must be verified against the feature's configuration/version.
- **`@Async`** likewise has its own annotation processor and proxy/executor wiring. Do not use `@Async`'s behavior for a given annotation placement to conclude an `@Aspect` using `@annotation(...)` resolves metadata identically.

The unifying requirement in **Spring proxy mode** is that client calls must enter a properly configured proxy and the method must be eligible for interception.

### Class-level annotations and inherited methods

Even with Spring `@Transactional`, the documentation notes that a class-level annotation does not automatically apply to every method **declared on an ancestor class** in all situations. You must examine how Spring resolves metadata for inherited methods and subclass overrides. For a clear contract, write tests covering inherited/overridden methods instead of relying solely on seeing an annotation on the subclass.

## 9. Self-invocation: inherited/default methods are no exception

Regardless of whether a method's code lives in a superclass or an interface, a call **inside the target** still does not automatically go back through the Spring proxy.

Example:

```java
public class CustomerService extends BaseService implements CustomerApi {
    public void outer() {
        this.inherited("A");
    }
}
```

If a caller invokes `proxy.outer()` and `outer()` has advice, the outer advice can run. Yet once Spring delegates to the target, `this.inherited("A")` executes directly on the target; advice matching only `inherited()` **does not execute additionally** along that path.

Similarly, if a default method runs on the target and calls another method, never assume that internal call counts as a new client call into the proxy. When an operation needs its own interceptor, extract it into another Spring bean and inject the container-provided bean reference.

Setting `proxyTargetClass=true` **does not fix self-invocation**. It only changes the proxy creation strategy.

## 10. Limits by visibility and code location

| Scenario | JDK proxy | CGLIB proxy | How to interpret |
| --- | --- | --- | --- |
| Public method inherited from superclass and declared on interface | Interceptable | Interceptable if method is overridable | Code living in superclass is no reason for skipping |
| Public method inherited yet not exposed on interface | Not callable via JDK proxy API | Interceptable if eligible | Distinguish target API from proxy API |
| Public interface default method | Can pass through proxy | Possible; verify specific overriding/matching | `default` does not create advice automatically |
| `protected` method | Not in public interface API | Possible depending on Spring version/visibility | Prefer clear public boundaries |
| `private` method | No | No | Cannot be overridden/intercepted by proxy mechanisms |
| `final` method on target | JDK proxy can intercept calls through interface in corresponding cases | Cannot override that method | Consider proxy strategy, do not conflate |
| `final class` | Can use JDK proxy if eligible interface exists | Cannot subclass | Forcing CGLIB configuration can fail |
| Constructors and field accesses | No | No | Outside Spring AOP's method-execution boundary |
| `this.method()` inside target | Does not re-enter proxy | Does not re-enter proxy | Self-invocation bypasses advice |

Read the `final method` row carefully: `final` does not stop an **interface method call** from entering a **JDK proxy**, yet it blocks a **subclass proxy from overriding the target method**. A JDK proxy and a CGLIB proxy can produce different advice outcomes in this case.

## 11. Checklist when advice fails to run

1. **Is the bean Spring-managed?** Created via `@Component`/`@Bean`, or is the application calling a manually `new`-ed object directly?
2. **Does a proxy actually exist?** Check `AopUtils.isAopProxy(bean)`, `isJdkDynamicProxy(bean)`, `isCglibProxy(bean)`.
3. **Which type does the caller use?** Interface or implementation? JDK proxies only expose interfaces implemented by the proxy.
4. **Where is the method actually declared?** Implementation, superclass, interface default, or overridden method?
5. **Can the proxy intercept the method?** Public interface method for JDK; overridable method with compatible visibility for CGLIB.
6. **What does the pointcut match?** `execution` checks signature, `@annotation` checks annotations on the method inspected by the matcher.
7. **Where is the annotation placed?** Method/interface/class/superclass? Did an override drop the annotation? Was `@Inherited` mistaken for method inheritance?
8. **Which Spring module is involved?** `@Transactional`/`@Cacheable`/`@Async` have their own metadata resolvers and settings; do not equate them with custom `@annotation` pointcuts.
9. **Is there self-invocation?** `this.method()` and internal calls on the target do not re-enter the proxy.
10. **Are multiple proxies/advisors present?** `proxy-target-class` settings, advice ordering, and dynamic pointcuts can produce unexpected results.

A solid test uses a **real `ApplicationContext`**, retrieves the actual Spring bean reference, verifies the proxy type, and calls **from a client outside the target**. Include tests for both proxy modes if the application supports both JDK and CGLIB.

## 12. Self-check questions

**Q1.** `CustomerService` inherits public method `run()` from `BaseService` and `CustomerApi` declares `run()`. Can a JDK proxy run Spring AOP advice when clients call `run()` through the interface?  
**Answer:** Yes, if advisors/pointcuts match and the bean actually receives an AOP proxy. Having the implementation in a superclass does not prevent interception.

**Q2.** Same `run()` method, yet the interface does not declare it. Can a client holding a JDK proxy cast the proxy to the implementation to call `run()`?  
**Answer:** You cannot assume so; a JDK proxy is not a subclass of the implementation. If this method is needed via proxy, consider exposing it on the interface or using CGLIB when appropriate.

**Q3.** A default method already has its implementation in the interface. Does that make it impossible for Spring AOP to intercept?  
**Answer:** No. Client calls through the proxy can still be intercepted, subject to advisor matching and proxy method support.

**Q4.** An implementation method carries `@TraceCall` while the interface method lacks the annotation. Will Java reflection on the interface method return true automatically?  
**Answer:** No. Those are two separate `Method` declarations; an annotation placed on the implementation does not appear automatically on the interface method.

**Q5.** A parent method is annotated, and a subclass overrides it without re-declaring the annotation. Does Java method reflection on the subclass inherit the method annotation via `@Inherited`?  
**Answer:** No. `@Inherited` applies to class annotations across superclass relationships, not automatically to method overrides.

**Q6.** Spring `@Transactional` on an interface works in a given proxy configuration. Is that enough to conclude a custom `@annotation(MyMarker)` pointcut always behaves identically?  
**Answer:** No. Spring transaction metadata lookup and AspectJ `@annotation` pointcuts are not identical by default.

**Q7.** `outer()` calls `this.inherited()` and the inherited method has advice. Does that advice run for the internal call?  
**Answer:** No new proxy interception occurs. You must change the call path to go through a proxy if you want advice triggered.

## Spring Framework documentation

- [Spring Framework 6.2 — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): JDK/CGLIB limits, self-invocation, and `final`/`private`.
- [Spring Framework — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html): `execution`, `@annotation`, `@within`, `@target`, and method execution scope.
- [Spring Framework — @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj.html): registering aspect beans and enabling Spring AOP.
- [Spring Framework 6.2 — Using @Transactional](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html): annotation placement, interface/implementation, method visibility, and self-invocation in transaction proxy mode.