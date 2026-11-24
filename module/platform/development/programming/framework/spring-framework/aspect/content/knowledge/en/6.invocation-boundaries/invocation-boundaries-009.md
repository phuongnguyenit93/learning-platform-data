# Nested proxies and tracing the object chain in Spring AOP

## 1. Lesson objectives

In Spring AOP, callers sometimes do not invoke the business object directly, instead going through multiple wrapper layers. An important scenario is when **the target of one Spring AOP proxy is itself another Spring AOP proxy**. In that case you need to know which layer a call passes through, where each interceptor runs, and why advice might be lost or executed twice.

Diagram:

~~~text
Caller
  -> Outer Spring AOP proxy
       -> Outer interceptor/advisor
       -> Inner Spring AOP proxy
            -> Inner interceptor/advisor from @Aspect
            -> TargetService.method()
~~~

This lesson covers only **proxy-based Spring Aspect/Spring AOP**, specifically:

1. Distinguishing **one proxy with multiple advisors** from **multiple nested proxies**.
2. Tracing each layer with Spring AOP APIs: `AopUtils`, `Advised`, `TargetSource`, and `AopProxyUtils`.
3. Understanding invocation order, `proceed`, return values, exceptions, and short-circuiting points.
4. Avoiding dynamic target lookups or unwrapping proxies in business code.
5. Observing behavior through a runnable Maven/Java 17+ application with a real `@Aspect` and `ProxyFactory`.
6. Diagnosing cases where transactions, caching, scoped proxies, or other adapters coexist.

Having multiple `@Aspect` classes or multiple Spring AOP annotations on a bean **does not automatically mean** Spring created multiple nested proxies. Standard Spring auto-proxying can place multiple advisors onto **a single proxy**.

## 2. Three very different structures

### 2.1. One proxy, multiple advisors

~~~text
Client
 -> AOP Proxy [Advisor A, Advisor B, Advisor C]
     -> Target
~~~

The proxy has one `TargetSource` and one advisor list. If a bean has both a custom `@Aspect` and transaction advice applied, in a typical configuration they can both appear on a single Spring AOP proxy. The advisor count may exceed one while the proxy layer count remains one.

### 2.2. Two genuinely nested proxies

~~~text
Client
 -> Outer Proxy [Advisor A]
     -> Inner Proxy [Advisor B]
         -> Target
~~~

Here the target of Outer Proxy is the Inner Proxy object. Each proxy has its own configuration; calling a method on Outer Proxy can traverse both interceptor chains.

If you inspect:

~~~java
Advised outerAdvised = (Advised) outer;
Advisor[] advisors = outerAdvised.getAdvisors();
~~~

that array describes **only outer's direct advisors**, not necessarily displaying advisors on inner.

### 2.3. A Spring AOP proxy inside another wrapper

~~~text
Client
 -> Custom JDK proxy or framework adapter
     -> Spring AOP proxy
         -> Target
~~~

A JDK proxy created manually via `java.lang.reflect.Proxy` is not automatically a Spring AOP proxy. A class whose name contains CGLIB is not necessarily an AOP proxy either: Spring also uses class enhancement for `@Configuration` and other features.

**Rule:** Determine **which actual object the client holds**, rather than jumping to conclusions from class names or log line counts.

## 3. Spring tools worth knowing

| API | Used to observe | Limits to remember |
| --- | --- | --- |
| `AopUtils.isAopProxy(obj)` | Whether the object is a Spring AOP proxy | Does not prove advice from a specific `@Aspect` is present |
| `AopUtils.isJdkDynamicProxy(obj)` | Interface/JDK-based AOP proxy | Do not use this result to count layers |
| `AopUtils.isCglibProxy(obj)` | Class-based AOP proxy | CGLIB-enhanced classes outside AOP are a separate case |
| `obj instanceof Advised` | Whether the object exposes advised configuration | Proxies configured as opaque may not allow casting to `Advised` |
| `Advised.getAdvisors()` | List of advisors at **the current layer** | Does not include inner's advisors |
| `Advised.getTargetSource()` | Abstraction locating the target at **the current layer** | Target may be singleton, scoped, pooled, or lazy |
| `TargetSource.getTargetClass()` | Declared target class | Does not require instantiating or retrieving the actual target |
| `TargetSource.isStatic()` | Whether the same target is returned across calls | Does not guarantee it is a plain object |
| `AopProxyUtils.getSingletonTarget(obj)` | Underlying target immediately below when using `SingletonTargetSource` | Returns null if inapplicable; does not traverse dynamic sources |
| `AopProxyUtils.ultimateTargetClass(obj)` | Deepest target type safely reachable across singleton chain | Not a tool for unwrapping arbitrary wrappers from other libraries |

Key imports:

~~~java
import org.springframework.aop.Advisor;
import org.springframework.aop.TargetSource;
import org.springframework.aop.framework.Advised;
import org.springframework.aop.framework.AopProxyUtils;
import org.springframework.aop.support.AopUtils;
~~~

**Distinction:** Reading a target class does not mean the proxy object is an instance of that class. With JDK proxies, the runtime type is typically an interface-implementing proxy, not a subclass of the implementation.

## 4. How Spring processes calls through nested proxies

Suppose both outer and inner have around-style interceptors:

~~~text
1. Client calls outer.method()
2. Outer interceptor starts and logs before
3. Outer invocation.proceed()
4. Inner proxy receives method call
5. Inner advice runs if pointcut matches
6. Inner delegates to target.method()
7. Target returns result
8. Inner returns result to outer
9. Outer interceptor logs after and returns result to client
~~~

An interceptor logging before and after `proceed` looks like:

~~~java
Object invoke(MethodInvocation invocation) throws Throwable {
    before();
    Object result = invocation.proceed();
    after();
    return result;
}
~~~

This is an **illustrative pattern**: `before`/`after` are pseudocode names, not a complete program. If `proceed` throws an exception, `after` following `proceed` will not run unless cleanup is placed in `finally`. If inner advice short-circuits without calling `proceed` (such as a cache hit), the target may never be invoked.

**`@Order` does not alter physical outer/inner boundaries by itself.** `@Order` primarily participates in sorting advisors when managed by the framework within a single chain. With two proxies configured independently by code, outer stays outer; changing layer order requires changing the wrapping structure.

## 5. Runnable Java 17+ example: `@Aspect` inner + `ProxyFactory` outer

The demonstration program uses:

- Spring Framework **6.2.19**, AspectJ Weaver **1.9.25.1**.
- A Spring bean containing business logic.
- An aspect bean with `@Before`, applied by Spring AOP to the business bean.
- A Spring AOP `ProxyFactory` creating an **outer proxy** that wraps the inner proxy returned by the context.
- Inspection APIs showing there are two distinct layers.

This example **does not use AspectJ bytecode weaving**; all behavior runs through Spring AOP proxies.

### 5.1. Directory

~~~text
spring-nested-aop/
├── pom.xml
└── src/main/java/example/
    ├── GreetingPort.java
    ├── GreetingService.java
    ├── TraceAspect.java
    ├── AppConfig.java
    └── Main.java
~~~

### 5.2. Maven

**`pom.xml`**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-nested-aop</artifactId>
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
            <version>1.9.25.1</version>
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
~~~

In real projects, use the Spring Framework BOM or Spring Boot BOM so `spring-*` modules stay aligned on versions. Versions are listed directly here to keep the example self-contained; do not copy these version numbers into a Spring Boot app managing a different Boot version.

### 5.3. Interface and target

**`GreetingPort.java`**

~~~java
package example;

public interface GreetingPort {
    String greet(String name);
}
~~~

**`GreetingService.java`**

~~~java
package example;

public class GreetingService implements GreetingPort {

    @Override
    public String greet(String name) {
        System.out.println("target: greet " + name);
        return "hello " + name;
    }
}
~~~

### 5.4. Spring aspect

**`TraceAspect.java`**

~~~java
package example;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class TraceAspect {

    @Before("execution(* example.GreetingService.greet(..))")
    public void beforeGreet() {
        System.out.println("inner aspect: before");
    }
}
~~~

The aspect declares advice on the target method. This `@Aspect` class must be registered as a bean for Spring AOP to use it.

### 5.5. Configuration creating the inner proxy

**`AppConfig.java`**

~~~java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class AppConfig {

    @Bean
    public GreetingPort greetingService() {
        return new GreetingService();
    }

    @Bean
    public TraceAspect traceAspect() {
        return new TraceAspect();
    }
}
~~~

Spring AOP discovers `TraceAspect` and the advisor matching `GreetingService.greet`. Given the `GreetingPort` interface and no forced class proxying, Spring uses a **JDK dynamic proxy** for the `greetingService` bean. Do not confuse `@Aspect` with a bean-registration annotation: the `@Bean` method is what registers `TraceAspect`.

### 5.6. Creating the outer proxy and inspecting the object chain

**`Main.java`**

~~~java
package example;

import org.aopalliance.intercept.MethodInterceptor;
import org.springframework.aop.framework.Advised;
import org.springframework.aop.framework.AopProxyUtils;
import org.springframework.aop.framework.ProxyFactory;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            GreetingPort inner =
                context.getBean("greetingService", GreetingPort.class);

            ProxyFactory factory = new ProxyFactory();
            factory.setInterfaces(GreetingPort.class);
            factory.setTarget(inner);
            factory.addAdvice((MethodInterceptor) invocation -> {
                System.out.println("outer: before");
                Object result = invocation.proceed();
                System.out.println("outer: after");
                return result;
            });

            GreetingPort outer = (GreetingPort) factory.getProxy();

            System.out.println("inner is AOP proxy: "
                + AopUtils.isAopProxy(inner));
            System.out.println("outer is AOP proxy: "
                + AopUtils.isAopProxy(outer));
            System.out.println("both JDK proxies: "
                + (AopUtils.isJdkDynamicProxy(inner)
                   && AopUtils.isJdkDynamicProxy(outer)));

            Object immediate = AopProxyUtils.getSingletonTarget(outer);
            Object deepest = AopProxyUtils.getSingletonTarget(inner);

            System.out.println("outer wraps inner: "
                + (immediate == inner));
            System.out.println("inner wraps plain target: "
                + (deepest instanceof GreetingService
                   && !AopUtils.isAopProxy(deepest)));
            System.out.println("ultimate target type: "
                + AopProxyUtils.ultimateTargetClass(outer).getSimpleName());

            if (outer instanceof Advised advised) {
                System.out.println("outer advisors: "
                    + advised.getAdvisors().length);
            }

            System.out.println("result: " + outer.greet("Lan"));
        }
    }
}
~~~

Intentional structure: `inner` comes from the Spring container so it already has the `@Aspect` advice. `ProxyFactory` is invoked **after** the context finishes, and the outer proxy is not re-registered as a Spring bean. Thus the example does not depend on whether the container auto-proxies an extra outer proxy layer.

### 5.7. Running the program

In the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.Main
~~~

**Lines printed by the program, in exact order:**

~~~text
inner is AOP proxy: true
outer is AOP proxy: true
both JDK proxies: true
outer wraps inner: true
inner wraps plain target: true
ultimate target type: GreetingService
outer advisors: 1
outer: before
inner aspect: before
target: greet Lan
outer: after
result: hello Lan
~~~

Logs emitted by Maven/frameworks (if any) are not part of the fixed stdout from these `System.out.println` statements.

### 5.8. Why is the output like this?

1. **Inner proxy:** Spring creates an advisor from `TraceAspect` and wraps `GreetingService`; `AopUtils` returns true.
2. **Outer proxy:** `ProxyFactory` creates an additional AOP proxy containing the single `MethodInterceptor` registered by the example.
3. **Two interface-based proxies:** Both inner and outer use JDK dynamic proxies, though the JDK/CGLIB strategy does not determine layer count.
4. **Outer wraps inner:** Outer's `TargetSource` is a `SingletonTargetSource` holding the `inner` instance itself.
5. **Inner wraps plain target:** Inner's `TargetSource` is a `SingletonTargetSource` holding the original `GreetingService`.
6. **Ultimate target:** `AopProxyUtils` traverses the singleton layers and identifies the target class `GreetingService`.
7. **Outer advisors: 1:** Counts only advisors attached at the outer layer. The inner layer still holds its advisor from `@Aspect`.
8. **Call path:** Outer receives `greet` first and prints `"outer: before"`; `proceed` invokes inner, `@Before` on inner prints `"inner aspect: before"`; target prints its output; inner returns, outer prints `"outer: after"`; finally `Main` prints `"result"`.

If you call `inner.greet("Lan")` directly, the outer interceptor is not triggered. If you call the raw `GreetingService` directly without going through a proxy, both outer and inner advice are bypassed.

## 6. Inspecting advisors at each layer

In the example, instead of guessing from logs, you can print the separate advisors/target sources of outer and inner:

~~~java
// Snippet to add into Main, not a standalone file.
if (outer instanceof Advised advisedOuter) {
    System.out.println("outer advisor count: "
        + advisedOuter.getAdvisors().length);
    System.out.println("outer source: "
        + advisedOuter.getTargetSource().getClass().getSimpleName());
}

if (inner instanceof Advised advisedInner) {
    System.out.println("inner advisor count: "
        + advisedInner.getAdvisors().length);
    System.out.println("inner source: "
        + advisedInner.getTargetSource().getClass().getSimpleName());
}
~~~

Advisor counts and inner infrastructure class names can vary across Spring releases or added advisors, so do not hard-code them in business tests.

**One proxy with multiple advisors:** `outer.getAdvisors()` can show multiple entries while `getSingletonTarget(outer)` is an ordinary business object.

**Multiple nested proxies:** `getSingletonTarget(outer)` can be another AOP proxy; in that case outer's and inner's `getAdvisors()` must be inspected separately.

`Advised` is the Spring AOP configuration interface, yet not every proxy exposes this interface; opaque proxies can hide it. Always use `instanceof` before casting.

## 7. Tracing a singleton proxy chain safely

Spring provides:

~~~java
Object next = AopProxyUtils.getSingletonTarget(proxy);
Class<?> deepType = AopProxyUtils.ultimateTargetClass(proxy);
~~~

`getSingletonTarget` returns the immediate target only when the proxy holds a `SingletonTargetSource`. Returning null **does not prove the proxy has no target**: the target source may be dynamic, or the object may not be a Spring AOP proxy of this kind.

A safer diagnostic snippet than calling `getTarget()` indiscriminately:

~~~java
// Imports to add to Main.java if using this snippet:
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;
import org.springframework.aop.framework.AopProxyUtils;
import org.springframework.aop.support.AopUtils;

static void traceSingletonChain(Object object) {
    Set<Object> seen =
        Collections.newSetFromMap(new IdentityHashMap<>());
    Object current = object;
    int depth = 0;

    while (current != null && seen.add(current)) {
        System.out.println("depth=" + depth
            + ", aopProxy=" + AopUtils.isAopProxy(current)
            + ", runtimeType=" + current.getClass().getName());

        Object next = AopProxyUtils.getSingletonTarget(current);
        if (next == null) {
            break;
        }
        current = next;
        depth++;
    }
}
~~~

This is a **method snippet** to place inside a class with the noted imports, not a standalone program. It identifies a chain of singleton Spring AOP proxies without triggering a dynamic `TargetSource.getTarget()`.

Use an **identity-based** `Set` instead of a regular `HashSet` to avoid relying on proxy `equals`/`hashCode`. When the trace stops at a non-Spring-AOP wrapper or a dynamic target source, report the boundary instead of concluding "this is definitely the final target".

## 8. `TargetSource` is not always a singleton

A Spring AOP proxy can use different target source types:

| `TargetSource` | Characteristics | Debugging risk |
| --- | --- | --- |
| `SingletonTargetSource` | Holds a single target object | Can inspect a singleton layer via `getSingletonTarget` |
| `PrototypeTargetSource` | Can create/fetch a fresh target | Calling `getTarget()` may instantiate extra unwanted objects |
| Scoped target source | Fetches target per request/session/scope | Current scope may be inactive or return different targets |
| Pooling target source | Borrows objects from a pool | May require `releaseTarget` after use |
| Lazy/hot-swappable target source | Target created lazily or swapped | State may change during execution |

Therefore, **do not** use the following as a default inspection pattern:

~~~java
Object target = ((Advised) proxy).getTargetSource().getTarget();
((GreetingPort) target).greet("Lan");
~~~

It can bypass outer advice, instantiate a new target, require an active scope, or disrupt target lifecycle. Especially with resources/pools, failing to call `releaseTarget` per contract can exhaust resources. Business code should stick to using the bean proxy provided by Spring.

To inspect preliminary metadata without grabbing the target:

~~~java
TargetSource source = ((Advised) proxy).getTargetSource();
Class<?> declaredTargetType = source.getTargetClass();
boolean constantTarget = source.isStatic();
~~~

These two calls retrieve metadata; they do not replace checking actual bean configuration.

## 9. Advice order, exceptions, and early termination

The outer/inner structure determines the **entry** order across layers. With an around-style interceptor:

~~~java
factory.addAdvice((MethodInterceptor) invocation -> {
    System.out.println("outer: begin");
    try {
        return invocation.proceed();
    } finally {
        System.out.println("outer: end");
    }
});
~~~

This is an **alternative version** of the interceptor in `Main.java`; do not use it simultaneously with the earlier version if you want to match the fixed output.

- Outer `"begin"` appears before inner because outer receives the call first.
- If inner returns normally, outer executes `finally` and then returns the result.
- If inner/target throws an exception, outer's `finally` still executes.
- If an outer around advice returns a value **without** calling `proceed`, inner/target may not run at all.
- If inner has a cache advisor returning a result right at that layer, the target may not run, while outer can still execute its before/after or `finally`.

Contrast with `@Order`: ordering advisors inside one proxy and the ordering of **nested proxy layers** are not the same ordering mechanism.

## 10. Call paths that bypass one or more layers

Suppose three references exist:

~~~java
GreetingPort outer = ...; // Outer AOP proxy
GreetingPort inner = ...; // Inner AOP proxy
GreetingPort plain = ...; // Business target (illustrative example)
~~~

Outcomes:

| Caller invokes | Layers traversed | Impact |
| --- | --- | --- |
| `outer.greet(...)` | Outer → Inner → Target | Both outer advice and inner `@Aspect` advice have a chance to run |
| `inner.greet(...)` | Inner → Target | Skips the outer interceptor |
| `plain.greet(...)` | Target directly | Bypasses both proxies |
| Target calls `this.someMethod()` | Direct call inside target | Does not loop back into inner/outer proxy |
| Outer around advice skips `proceed` | Only outer (or earlier outer interceptors) | Inner/target is never invoked |

**Self-invocation** remains a Spring AOP limit regardless of whether outer or inner proxies are JDK or CGLIB. Nested proxies do not create a fresh advice boundary for `this.method()` inside the target.

Never "unwrap" a proxy and cache the plain target in a field as a performance optimization when business behavior relies on transactions, caching, security, or tracing; doing so can strip away essential advice.

## 11. Common causes of multiple wrappers in a Spring application

Several cases worth investigating:

1. A developer creates a `ProxyFactory` wrapping an already-proxied Spring AOP bean.
2. A bean factory returns an object that is already a proxy, and another `BeanPostProcessor` wraps it again.
3. An integration framework like Spring Data supplies a repository proxy alongside extra AOP advisors or a custom proxy.
4. Scoped proxies combined with transaction/cache/custom `@Aspect`s and special target sources.
5. An adapter/client wrapper outside Spring AOP takes a Spring AOP proxy as its target.
6. AOP infrastructure holds multiple advisors, making logs **look** nested while actually being a single proxy.

Cases 2–5 **do not always produce two separate proxy layers**. Spring can merge advisors/configurations or share common infrastructure. Thus, confirm nesting only when you find a proxy object whose target source holds **another proxy**, not by counting annotations or log lines.

## 12. Spring Aspect diagnostic workflow

### Step 1: Start from the object held by the caller

Do not start from the source class and assume it matches the runtime class. Take the reference from dependency injection or the context, and verify `isAopProxy`, `isJdkDynamicProxy`/`isCglibProxy`.

### Step 2: Inspect the outer proxy

If `instanceof Advised`, read `getAdvisors`, `getTargetSource`, `getTargetClass`, and `isStatic`. Do not mutate advisors at runtime in production just to see results.

### Step 3: Walk singleton targets, if applicable

Use `AopProxyUtils.getSingletonTarget` at each layer; stop when it returns null or when the object is not a compatible Spring AOP proxy. You can call `ultimateTargetClass` to get the deepest supported target type.

### Step 4: Diagram the object chain

Write explicitly:

~~~text
caller -> outerProxy/advisor A -> innerProxy/advisor B -> realTarget
~~~

Or:

~~~text
caller -> oneProxy/advisors A,B -> realTarget
~~~

These are two different diagrams leading to different diagnoses.

### Step 5: Trace `proceed` and returns

Log at interceptor entry/exit points. Identify which advice calls `proceed`, which advice can cache-hit/short-circuit, and whether exceptions are caught or propagated.

### Step 6: Compare against `@Aspect` pointcuts

A proxy existing does not mean every method matches. Verify the Spring-managed aspect bean, advisors matching target/method, proxy type, visibility, and calls passing through the proxy.

### Step 7: Check external and internal boundaries

Does any caller grab `inner` instead of `outer`, hold the plain target, manually `new` an object, or call `this.method()` inside the target? Those call paths produce different traces even for the same business method.

### Step 8: Test with a real context

Integration tests should invoke through the Spring-provided reference held by callers, observing both business outcomes and advice execution, rather than relying solely on target log lines.

## 13. Common mistakes

| Symptom | Hasty conclusion | Proper check |
| --- | --- | --- |
| Two `before` lines printed | Definitely two proxies | Could be one proxy with two advisors |
| Outer has only one advisor | No advice inside | Must inspect `inner` separately |
| `isAopProxy` returns true | Definitely from my `@Aspect` | Proxy might be for transactions/caching/scope |
| `getSingletonTarget` returns null | No target exists | May be a dynamic `TargetSource` or non-matching proxy |
| `ultimateTargetClass` returns `GreetingService` | Proxy can be cast to `GreetingService` | A JDK proxy may still implement only `GreetingPort` |
| `@Order` does not swap outer and inner | Spring ordering bug | Physical proxy layers differ from advisor ordering in one proxy |
| Calling target directly loses tracing | Aspect does not exist | Call path bypassed the proxy |
| Scoped proxy `getTarget` fails | Bean is missing | Scope may currently be inactive |
| One advice logged twice | Definitely caused by nested proxies | Could be duplicate aspect bean registration, multiple advisors, or calling the method twice |
| Target was never called | Broken proxy | An around advice may have returned early or hit a cache |

## 14. Applied questions

**Q1.** An AOP proxy has three advisors. Are there definitely three proxy layers?

**Answer:** No. All three advisors can sit on a single proxy.

**Q2.** Outer has one advisor, and outer's immediate singleton target is another Spring AOP proxy. What can be concluded?

**Answer:** There are at least two AOP proxy layers in this singleton chain. Inspect inner's advisors/target source to understand the rest.

**Q3.** Why does `outer.getAdvisors()` not show advice created by inner's `@Aspect`?

**Answer:** It lists only advisors belonging to outer's configuration; it does not automatically merge inner advisors.

**Q4.** If a caller switches from `outer.greet()` to `inner.greet()`, does outer advice run?

**Answer:** No, because the call bypasses the outer proxy. Inner advice can still run.

**Q5.** Should `getTarget()` be called repeatedly to unwrap scoped proxies in production?

**Answer:** No. Target sources can be dynamic, scope-dependent, and governed by release/lifecycle contracts. Inspect metadata or use singleton helpers only when safe.

**Q6.** An outer around interceptor does not call `proceed`. Must inner and the target still receive the call?

**Answer:** No. The outer interceptor can short-circuit the entire call chain.

## 15. Official primary references

- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK/CGLIB proxies, proxy boundaries, and self-invocation.
- [Spring Framework — Creating AOP Proxies Programmatically](https://docs.spring.io/spring-framework/reference/core/aop-api/prog.html): `ProxyFactory`, `addAdvice`, `addAdvisor`, `getProxy`.
- [Spring Framework — Manipulating Advised Objects](https://docs.spring.io/spring-framework/reference/core/aop-api/advised.html): inspecting advisors and proxy configuration.
- [Spring Framework — TargetSource Implementations](https://docs.spring.io/spring-framework/reference/core/aop-api/targetsource.html): singleton/dynamic target sources.
- [Spring Javadoc — AopProxyUtils](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/aop/framework/AopProxyUtils.html): `getSingletonTarget` and `ultimateTargetClass`.
- [Spring Javadoc — Advised](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/aop/framework/Advised.html): `getAdvisors` and `getTargetSource`.
- [Spring Javadoc — AopUtils](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/aop/support/AopUtils.html): identifying AOP proxies and target classes.