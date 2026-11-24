# Spring AOP: self-injecting a proxy reference and emerging dependencies

## 1. Why does the concept of self-injection exist?

Spring AOP is **proxy-based AOP**. Spring creates proxies for Spring-managed beans that need advisors/advice applied. When another bean calls a method **through the proxy**, advice has a chance to run. Yet when the target itself calls one of its own methods via `this`, that call does not pass through the proxy — this is called *self-invocation*.

```java
@Service
public class ReportService {
    public void generate() {
        this.audit(); // Called on target, not through Spring AOP proxy.
    }

    public void audit() {
        System.out.println("audit");
    }
}
```

This snippet is illustrative; it is not a standalone runnable application. Suppose Spring has a `@Before` aspect for `audit()`: if a consumer calls `reportService.audit()` through the Spring-injected proxy reference, advice can run. However, `generate()` calls `this.audit()` directly, so advice for `audit()` does not run. This holds true for both JDK dynamic proxies and CGLIB in Spring AOP.

**Self-injection** is a technique where a bean receives a reference to **its own Spring bean** (hopefully the AOP proxy), and explicitly invokes the method through that reference instead of `this`:

```java
private ReportOperations self;

public void generate() {
    self.audit(); // Advice runs only if self ultimately calls the right AOP proxy.
}
```

This snippet merely illustrates the idea, without an injection mechanism. This workaround can overcome self-invocation for **a specific call**, but it introduces a dependency on the very bean currently being initialized. For that reason, Spring documentation treats self-injection as a fallback; the preferred design solution is to **extract the operation needing advice into another Spring bean** and call it through a Spring-injected dependency.

This lesson focuses solely on Spring AOP, Spring IoC, proxies, bean lifecycle, and resulting dependencies; it does not discuss general AOP or AspectJ weaving outside the scope of Spring AOP proxies.

## 2. Three references easily confused

Consider a Spring bean `ReportService implements ReportOperations` with methods `generate()` and `audit()`:

1. **Target object:** the actual instance holding `ReportService`'s state and code. Inside the target, `this` points to the target.
2. **Spring AOP proxy:** the reference that `ApplicationContext.getBean(ReportOperations.class)` or a consumer's constructor injection can receive when a matching advisor exists.
3. **Lazy-resolution proxy:** an intermediary reference Spring provides to an injection point annotated with `@Lazy`; when the caller uses it, it looks up the real dependency from the container. The ultimate dependency may be a **Spring AOP proxy**.

```text
Consumer
   |
   v
Spring AOP proxy (ReportOperations)
   |
   v
Target ReportService.generate()
   |
   +-- this.audit()
   |       |
   |       v
   |    Target.audit()          -> DOES NOT pass through advice
   |
   +-- self.audit()
           |
           v
       @Lazy proxy if present
           |
           v
       Resolve dependency in Spring
           |
           v
       Spring AOP proxy
           |
           +-- advice for audit(), if pointcut matches
           |
           v
       Target.audit()
```

Key point: **a `@Lazy` injection proxy is not synonymous with an AOP proxy**. Seeing that `self` looks like a proxy is not enough to conclude that advisors are present or that calls run advice. You must verify the actual resolved Spring bean and the result of method invocation.

Neither proxy type automatically replaces `this.audit()` calls either. Only when code **switches to calling `self.audit()` on the right reference** does it get the chance to pass through the Spring AOP proxy.

## 3. Rules of self-injection in Spring DI

### 3.1. `@Autowired` self-references have the lowest priority

Spring Framework allows `@Autowired` to consider the bean currently being configured as a candidate for its own dependency. However, self-injection is a **fallback mechanism**:

- Normal candidate beans/dependencies are considered **before** a self-reference.
- A self-reference has **the lowest priority**, is not treated as a regular autowiring candidate, and is not prioritized with `@Primary`.
- With multiple beans implementing the same interface, `@Autowired ReportOperations self` may not select the current bean if another regular candidate matches.
- Spring can also fall back to resolving by name in appropriate situations; still, a field named `self` should not be assumed to guarantee binding to the current bean.

Consequence: declaring a field named `self` does not prove it retrieves this service's own proxy. When correctness depends on it, inspect at runtime, specify bean name/qualifier, and write integration tests. In long-term design, depending on an actual collaborator bean is much clearer.

### 3.2. Why does constructor self-injection usually cause a cycle?

Example that should not be used by default:

```java
@Service
class ReportService implements ReportOperations {
    private final ReportOperations self;

    ReportService(ReportOperations self) {
        this.self = self;
    }
}
```

This is an illustrative fragment missing interface methods. To construct `ReportService`, Spring must resolve the `ReportOperations` constructor parameter; if it points back to the same bean, the bean cannot finish construction yet, creating a **constructor dependency cycle**. Ordinary constructor cycles cannot be resolved via early singleton exposure mechanisms intended for certain field/setter cases.

Putting `@Lazy` **on the constructor parameter** can defer resolution and alter the technical behavior, yet it does not make a self-referential relationship good design. Do not inject the same type via constructor just to fix self-invocation.

### 3.3. Non-`@Lazy` field/setter self-injection is also risky

```java
@Autowired
private ReportOperations self;
```

During field population, the target may still be in the middle of Spring initialization. If the dependency resolves eagerly back to the current bean, Spring may have to handle an **early bean reference**. For singletons and configurations permitting circular dependencies, AOP infrastructure can participate via `SmartInstantiationAwareBeanPostProcessor.getEarlyBeanReference(...)` to create an early proxy.

However:

- Not every circular dependency is accepted by Spring.
- An early reference is not a universal guarantee that all initialization/advice is ready.
- Circular references involving constructors still have their own restrictions.
- Spring Boot 2.6+ disallows circular references by default unless configured otherwise.
- You may encounter `BeanCurrentlyInCreationException`, raw-target references, or mismatches with the final proxy in complex cyclic designs.

Do not enable `spring.main.allow-circular-references=true` as a first resort; eliminate the self-dependency or deliberately defer a dependency only when truly necessary.

## 4. How does `@Autowired @Lazy` at the injection point work?

Placing `@Lazy` at the **injection point**:

```java
@Service
public class ReportService implements ReportOperations {
    @Autowired
    @Lazy
    private ReportOperations self;

    @Override
    public void generate() {
        this.audit(); // Bypasses AOP proxy.
        self.audit(); // Passes through lazy-resolution proxy, then to the Spring-provided bean.
    }

    @Override
    public void audit() {
        System.out.println("audit");
    }
}
```

This is a fragment; the full example is in section 7. With `@Autowired @Lazy`, Spring creates a **lazy-resolution proxy** and does not need to resolve the target dependency immediately during field injection. When `self.audit()` runs for the first time after bean initialization completes, the intermediary proxy resolves `ReportOperations` from Spring. If the container exposes that bean as an AOP proxy and the pointcut selects `audit()`, advice runs.

**Two meanings of `@Lazy` are not identical:**

| Placement | Effect in Spring |
| --- | --- |
| `@Lazy` on a `@Service` class or `@Bean` method | Requests deferring **bean initialization** when possible |
| `@Lazy` on an `@Autowired` field/parameter | Creates a **lazy-resolution proxy** at the injection point; looks up dependency upon actual use |
| `@Lazy` on a business method | Does not automatically enable advice or fix self-invocation |

Notes:

- Do not call `self.audit()` inside a constructor, `@PostConstruct`, or while the container cannot yet supply a complete AOP proxy. Lazy does not mean the bean is initialized.
- For singletons, the lazy proxy typically caches the dependency after first resolution; for other scopes, resolution behavior can differ.
- `@Lazy` can **defer configuration errors**: a missing or unresolvable dependency might fail only when the call actually occurs.
- `@Lazy` does not guarantee that the aspect was scanned, AOP infrastructure is enabled, or the pointcut matches.
- If the actual AOP proxy is a JDK dynamic proxy, inject **an interface implemented by the proxy**; injecting a concrete class can cause type errors or unexpected behavior.
- `@Lazy` does not fix static/private/final method limitations or objects instantiated manually with `new`.
- If multiple `ReportOperations` beans exist, fallback self-injection can select a different bean. Never equate "reference has the right type" with "reference is definitely mine".

A very common testing mistake: `AopUtils.isAopProxy(self)` returns true because `self` is an **injection-point proxy**, not necessarily because the underlying bean has Spring AOP advice. Check `AopUtils.isAopProxy(context.getBean(ReportOperations.class))` on the actual bean and verify advice lines printed upon invocation.

## 5. Emerging dependencies and design costs

### 5.1. Logic becomes coupled to container lifecycle

A method that seems to run plain business logic now requires Spring to create the bean, wire the self-reference, and publish the AOP proxy. Calling at the wrong lifecycle stage can resolve the reference while the bean is still under construction or before post-processing finishes.

For instance, avoid calling a self method needing advice from `@PostConstruct`: initialization callbacks typically run on the target before the final proxy is published. It is better to let the operation be invoked by a consumer after the context is ready.

### 5.2. Coupling to Spring DI

An `@Autowired @Lazy ReportOperations self` field puts Spring infrastructure directly inside the business class. A simple unit test:

```java
ReportService service = new ReportService();
service.generate();
```

will not receive Spring field injection, so `self` remains null and calling it can throw `NullPointerException`. Testing that path requires a Spring context or manual dependency setup. This is a real cost compared to a design with constructor injection of an independent collaborator bean.

### 5.3. Resolving the wrong dependency when multiple implementations exist

Suppose both `ReportService implements ReportOperations` and `SpecialReportService implements ReportOperations` exist. A self-reference is not prioritized by Spring over ordinary candidates. Therefore, a self-injected field by interface can resolve to the other service; calls and aspects still run, but on the wrong operation or wrong state.

If self-injection is unavoidable, verify bean names/types/qualifiers in the specific application. However, qualifiers and bean names add another layer of coupling; whenever possible, design two services with distinct roles.

### 5.4. Proxy type affects the self-reference type

| AOP configuration | What to watch |
| --- | --- |
| JDK dynamic proxy | Proxy implements interfaces, does not extend the implementation class. Self-reference should use an interface |
| CGLIB class proxy | Can inject by class if the class is subclassable; `final`/`private` methods still cannot be CGLIB-advised |
| Plain Spring Framework | `@EnableAspectJAutoProxy(proxyTargetClass=false)` prefers JDK proxy when target has interfaces |
| Spring Boot with AOP auto-config | Usually defaults to class proxy; set `spring.aop.proxy-target-class=false` if intentionally preferring interface proxies |

Both proxy types experience self-invocation. Switching proxy types does not make `this.audit()` route back into the interceptor chain.

### 5.5. Scopes make "self" unstable

With the default singleton scope, a Spring bean reference is generally stable within a context. With prototype/request scopes or scoped proxies:

- Each time the container resolves the bean, it may create a different target or depend on the current active scope.
- A lazy reference may resolve according to a different scope; the notion of "calling this exact instance" must be verified rather than inferred from the field name.
- When no request scope is active, the call can fail.
- Self-references do not automatically manage thread context or propagate transaction/security state across threads.

Do not generalize a singleton example to every scope.

## 6. Preferred solution: extract the method needing advice to another bean

Instead of `ReportService -> self -> ReportService`, create a collaborator bean with one clear responsibility:

```java
public interface AuditOperations {
    void record(String reportId);
}

@Service
public class AuditService implements AuditOperations {
    @Override
    public void record(String reportId) {
        System.out.println("[audit] " + reportId);
    }
}

@Service
public class ReportService {
    private final AuditOperations audit;

    public ReportService(AuditOperations audit) {
        this.audit = audit;
    }

    public void generate(String reportId) {
        System.out.println("[report] " + reportId);
        audit.record(reportId);
    }
}
```

The snippet above illustrates the design; each public type belongs in its own file, `@Service` classes need `import org.springframework.stereotype.Service`, and Spring AOP/an aspect must be configured to select `AuditService.record()`. Consumers invoke `ReportService.generate(...)`, while `record(...)` needing advice is called **through a Spring-provided dependency**, giving it the chance to traverse an AOP proxy.

Strengths:

1. Avoids a dependency cycle with itself.
2. Uses ordinary **constructor injection**.
3. Clearly separates where policies/aspects apply.
4. Lets you test the service with a fake `AuditOperations` without starting a Spring container.
5. Requires no `@Lazy` on a self field and no `AopContext.currentProxy()`.
6. When switching between JDK and CGLIB, consumers still depend cleanly on an interface contract.

You do not have to split every helper; if advice at the public entry point already covers the whole operation, keep private helpers internal. Split into another bean when a method genuinely needs its own AOP policy/boundary.

## 7. Runnable Java 17 and Spring Framework 6.2 example

The example uses Maven, Java 17, Spring Framework 6.2.x, without Spring Boot. There is a service `ReportService implements ReportOperations` and a `@Before` aspect selecting only `audit()`. We use `@Autowired @Lazy` to obtain a self-reference without resolving eagerly during field injection.

Observation goal: `this.audit()` skips advice; `self.audit()` runs advice after the lazy proxy resolves the Spring AOP bean; calling `audit()` directly on the Spring bean also runs advice.

**Structure:**

```text
spring-aop-self-injection/
├── pom.xml
└── src/main/java/demo/self/
    ├── AppConfig.java
    ├── ReportOperations.java
    ├── ReportService.java
    ├── AuditAspect.java
    └── Main.java
```

### 7.1. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-self-injection</artifactId>
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

### 7.2. `AppConfig.java`

```java
package demo.self;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackageClasses = AppConfig.class)
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class AppConfig {
}
```

Spring scans target beans and aspects in package `demo.self`. Since the target has an interface and `proxyTargetClass=false`, the example uses a JDK dynamic proxy.

### 7.3. `ReportOperations.java`

```java
package demo.self;

public interface ReportOperations {
    void generate();
    void audit();
}
```

Both public methods are in the interface, so the JDK proxy can expose them to callers; only `audit()` is advised by the aspect below.

### 7.4. `ReportService.java`

```java
package demo.self;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Lazy;
import org.springframework.stereotype.Service;

@Service
public class ReportService implements ReportOperations {
    @Autowired
    @Lazy
    private ReportOperations self;

    @Override
    public void generate() {
        System.out.println("[service] generate");
        this.audit(); // Does not go through Spring AOP proxy.
        self.audit(); // Resolves lazy dependency, calls Spring AOP proxy.
    }

    @Override
    public void audit() {
        System.out.println("[service] audit");
    }
}
```

This is **deliberate self-injection for learning**, not a default design recommendation. Because `@Lazy` is on the injection point, `ReportOperations` does not need to be resolved while the field is being injected. When `generate()` is called after the context finishes starting, `self.audit()` resolves the bean published by Spring.

### 7.5. `AuditAspect.java`

```java
package demo.self;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class AuditAspect {
    @Before("execution(* demo.self.ReportService.audit(..))")
    public void beforeAudit() {
        System.out.println("[advice] before audit");
    }
}
```

The aspect has `@Component` so Spring registers it as a bean. The pointcut uses the target class; Spring can match the target method even when callers hold an interface proxy.

### 7.6. `Main.java`

```java
package demo.self;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {
            ReportOperations service = context.getBean(ReportOperations.class);

            System.out.println("isAopProxy=" + AopUtils.isAopProxy(service));
            System.out.println("isJdkProxy=" + AopUtils.isJdkDynamicProxy(service));

            service.generate();

            System.out.println("[main] direct proxy call");
            service.audit();
        }
    }
}
```

Compile and run command from the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.self.Main
```

**Stdout from `System.out` statements in the example** (excluding build logs if emitted by the environment):

```text
isAopProxy=true
isJdkProxy=true
[service] generate
[service] audit
[advice] before audit
[service] audit
[main] direct proxy call
[advice] before audit
[service] audit
```

Explanation:

- The first two lines verify that the official bean fetched from Spring is an AOP proxy and a JDK dynamic proxy in this configuration.
- `service.generate()` passes through the proxy, yet `generate()` does not match the pointcut; the target prints `[service] generate`.
- `this.audit()` prints `[service] audit` with **no advice** before the first occurrence.
- `self.audit()` goes through the lazy-resolution proxy to the Spring bean wrapped in an AOP proxy, printing `[advice] before audit` and then `[service] audit` a second time.
- Calling `service.audit()` in `Main` also passes through the AOP proxy, so advice runs.
- `exposeProxy=true` is not needed in this example; self-injection and `AopContext.currentProxy()` are two separate techniques.

## 8. Experiments and scenarios to watch out for

### 8.1. Removing `@Lazy`

If you change the field to:

```java
@Autowired
private ReportOperations self;
```

Spring may have to resolve the self-reference while the target is under construction, leading to a circular dependency or an early reference. Spring Boot applications with circular references disallowed can fail at startup. There is no guarantee that removing `@Lazy` will still work across all configurations. The right fix is usually refactoring the bean.

### 8.2. Switching `self.audit()` back to `this.audit()`

Both calls from `generate()` will bypass the proxy, even though `service.audit()` in `Main` still runs advice. This distinguishes **self-invocation** from a pointcut error or missing aspect registration.

### 8.3. Adding a second implementation

If another bean also implements `ReportOperations`, Spring has no default rule saying "a field named `self` always injects myself". Self-injection is only a fallback; regular candidates can be chosen first. When you strictly need the right proxy, identify the bean by name/qualifier or consider refactoring. Integration tests must prove the method runs on **the intended bean**.

### 8.4. Removing the aspect

If you remove `@Component` from `AuditAspect` without replacing it with `@Bean`, or change the pointcut so it no longer matches, `self.audit()` can still call the Spring bean yet **without advice**. That is not a `@Lazy` bug, simply the absence of an applicable advisor.

### 8.5. Switching to a class-based proxy

In `AppConfig`, change to:

```java
@EnableAspectJAutoProxy(proxyTargetClass = true)
```

For a non-`final` class, Spring creates a CGLIB proxy. `isJdkProxy` in stdout becomes `false`, while `this.audit()` bypassing and `self.audit()` calling through the proxy remain true. Enabling CGLIB does not eliminate the proxy boundary.

### 8.6. Calling inside lifecycle callbacks

Do not use `self.audit()` inside a constructor or `@PostConstruct` to "turn on" transactions or auditing. At that stage the target may not have passed through final auto-proxying; lazy resolution can hit `BeanCurrentlyInCreationException` or resolve a different reference than expected. Invoke the operation from a Spring-managed consumer after the context is ready.

### 8.7. Using `ObjectProvider` instead of `@Lazy`

An on-demand resolution alternative:

```java
@Service
public class ReportService implements ReportOperations {
    private final ObjectProvider<ReportOperations> provider;

    public ReportService(ObjectProvider<ReportOperations> provider) {
        this.provider = provider;
    }

    @Override
    public void generate() {
        provider.getObject().audit();
    }

    @Override
    public void audit() {
        System.out.println("audit");
    }
}
```

This is a fragment requiring imports for `org.springframework.beans.factory.ObjectProvider`, `@Service`, and the full interface type. Injecting a provider does not necessarily resolve the bean immediately, yet `getObject()` **does not guarantee** picking this exact bean when multiple candidates exist; self-injection still involves candidate selection rules. `ObjectProvider` also increases coupling to the DI container. It is not preferred ahead of refactoring.

## 9. Comparing the options

| Approach | When useful | Limits / risks |
| --- | --- | --- |
| **Extract method to another Spring bean and constructor-inject** | Standard design when an operation needs independent advice | Requires sensible separation of responsibilities |
| `@Autowired @Lazy` self-reference | Stopgap to go through proxy internally when refactoring is not feasible | Fallback autowiring, lazy proxy ≠ AOP proxy, harder to test, lifecycle coupling |
| Non-lazy `@Autowired` self field | May work in some legacy configs supporting early singleton references | Prone to circular dependencies, raw bean vs. proxy issues, startup errors |
| Constructor self-injection | Avoid using directly | Constructor dependency cycle; `@Lazy` only defers rather than fixing design |
| `AopContext.currentProxy()` | Last resort when invocation already passed through proxy and is exposed | Needs `exposeProxy=true`, Spring-specific, thread/invocation-bound |
| `ObjectProvider<T>` or `ApplicationContext.getBean(...)` | When explicitly needing on-demand bean lookup | Service locator coupling, wrong bean selection/ambiguity if type is not unique |

### Does `AopContext.currentProxy()` replace self-injection?

Spring allows:

```java
((ReportOperations) AopContext.currentProxy()).audit();
```

but requires executing inside **an AOP proxy invocation with `exposeProxy=true`**, such as `@EnableAspectJAutoProxy(exposeProxy = true)`. If no matching current proxy exists, `AopContext.currentProxy()` throws `IllegalStateException`. With a JDK proxy, you must cast to a proxy-implemented interface rather than arbitrarily casting to the implementation class.

This couples business code to Spring AOP; Spring documentation advises limiting it and preferring refactoring/bean dependencies. It does not make `private`/`static` methods interceptable, does not fix existing `this.method()` calls, and does not work on objects created outside the container.

## 10. Troubleshooting checklist

| Symptom | Cause / what to check |
| --- | --- |
| `this.inner()` does not run advice | Call path stays on target, bypassing Spring proxy; evaluate splitting into another bean |
| `self.inner()` does not run advice | Check actual lazily resolved bean, aspect/pointcut, and AOP proxy type |
| `AopUtils.isAopProxy(self)` is true yet advice does not run | `self` may only be a lazy-resolution proxy; inspect the primary bean from context |
| `BeanCurrentlyInCreationException` | Eager self-resolution or circular dependency; avoid relying on partial startup beans |
| `NoUniqueBeanDefinitionException` or wrong bean injected | Multiple implementations exist, fallback self-injection; check bean name/qualifier |
| `ClassCastException` or cannot inject concrete class | Actual AOP proxy may be a JDK interface proxy |
| Test with `new ReportService()` throws NPE | `@Autowired @Lazy` is not injected outside the Spring container |
| Fails when run in `@PostConstruct` | Final proxy not yet ready; avoid self calls during init |
| Spring Boot rejects circular reference | Remove the cycle rather than enabling circular references to mask design issues |
| `final`/`private`/`static` method still gets no advice | Proxy method limitation; self-injection cannot bypass overriding constraints |
| AOP proxy exists yet `audit()` does not run advice | Verify pointcut match and that invocation genuinely passes through the proxy |
| Class only has `@Aspect` and is not a bean | Register via `@Component` or `@Bean`, and enable Spring AOP |

Debug order: verify target/aspect are Spring beans → confirm actual Spring AOP proxy (not merely a lazy proxy) → check correct bean selection and interface type → confirm invocation happens after initialization → check `this` vs. `self` → match against pointcut → refactor if an unnecessary self-cycle exists.

## 11. Review questions

**1. Why does `this.audit()` bypass advice?** Because Spring AOP proxies only intercept calls passing through the proxy reference; `this` inside the target calls the target directly.

**2. Is `@Autowired ReportOperations self` guaranteed to pick the bean itself?** No; self-injection is only a fallback mechanism in Spring, and regular candidates are considered first.

**3. Does `@Lazy` on a self field automatically enable Spring AOP?** No. It creates a proxy for lazy dependency resolution, while an AOP proxy requires matching advisors/pointcuts to apply.

**4. Why is constructor-injecting the service into itself prone to failure?** It can create a constructor cycle when a bean attempts to resolve itself before construction finishes.

**5. Why avoid calling `self.audit()` in `@PostConstruct`?** At that moment the target may not have been auto-proxied completely; lazy resolution can encounter a bean still under creation.

**6. Is `exposeProxy=true` required to use `@Autowired @Lazy`?** No. That setting is for `AopContext.currentProxy()`; lazy self-injection works via dependency resolution.

**7. What is the preferred long-term option?** Extract the operation needing advice into an independent bean and call it through a Spring-injected dependency, unless there is a very strong reason to keep a self-reference.

## Official Spring references

- [Spring Framework 6.2 — Proxying Mechanisms and Self-Invocation](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
- [Spring Framework — Using @Autowired: Self Injection](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired.html)
- [Spring Framework 6.2 — @Lazy API: Injection Point](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/annotation/Lazy.html)
- [Spring Framework 6.2 — ContextAnnotationAutowireCandidateResolver API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/annotation/ContextAnnotationAutowireCandidateResolver.html)
- [Spring Framework — Dependency Injection](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-collaborators.html)
- [Spring Framework — @AspectJ support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj.html)