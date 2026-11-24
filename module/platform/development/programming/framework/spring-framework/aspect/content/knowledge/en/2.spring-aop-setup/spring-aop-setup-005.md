# Spring AOP: Configuring `proxyTargetClass` and `exposeProxy`

## 1. Two attributes solving two different problems

In Spring Framework, when enabling AOP with `@EnableAspectJAutoProxy`, two attributes appear frequently:

```java
@Configuration
@EnableAspectJAutoProxy(
    proxyTargetClass = false,
    exposeProxy = false
)
class AopConfig {
}
```

This is an **illustrative configuration snippet**, not a standalone runnable application. Both attributes default to `false` on **Spring Framework's `@EnableAspectJAutoProxy` annotation**. However, Spring Boot usually auto-configures **class-based proxies** by default; distinguish the annotation's defaults from Spring Boot's defaults.

| Attribute | Question it answers | `false` | `true` |
| --- | --- | --- | --- |
| `proxyTargetClass` | Which kind of AOP proxy does Spring create? | Prefer a JDK dynamic proxy if the target has an interface; otherwise use a class-based proxy | Force Spring to use a class-based (CGLIB) proxy for proxyable target classes |
| `exposeProxy` | Can code executing inside an AOP call access the **current proxy** via `AopContext.currentProxy()`? | Do not expose current proxy; attempting to retrieve it normally throws `IllegalStateException` | Expose current proxy for the scope of the current proxied call; `AopContext.currentProxy()` can be used |

The two flags are **semantically independent**. Setting `proxyTargetClass=true` does not make `AopContext.currentProxy()` work. Setting `exposeProxy=true` does not automatically switch a JDK proxy to CGLIB. Neither flag **causes every bean to be proxied**: Spring AOP only creates a proxy when advice/advisor infrastructure needs to apply to that bean.

## 2. Understanding `proxyTargetClass` in Spring AOP

Spring AOP uses proxies for **method calls on Spring-managed beans**. When a target implements at least one interface, the two proxy creation approaches differ significantly:

### `proxyTargetClass=false`: prefer interface-based proxy

Example target:

```java
public interface PaymentService {
    void pay();
}

public class PaymentServiceImpl implements PaymentService {
    @Override
    public void pay() {
        System.out.println("pay");
    }
}
```

If this bean is matched by an advisor and `proxyTargetClass=false`, Spring normally creates a **JDK dynamic proxy**:

- The proxy implements `PaymentService`, so injecting or looking up the bean by **interface** is natural.
- The proxy is not a subclass of `PaymentServiceImpl`. Casting to `PaymentServiceImpl` or injecting directly by the implementation class can fail with a bean type error.
- Through an interface proxy, callers can only directly invoke methods declared on the interface(s) the proxy implements. A public method existing only on the implementation and not on the proxy interface will not be exposed via that type.
- If the target **has no suitable interface**, Spring still needs to use a class-based proxy; `false` does not mean always JDK proxy.

### `proxyTargetClass=true`: force class-based proxy

Spring creates a CGLIB subclass of the target (when possible). Even when the target has an interface, the AOP proxy targets the class:

- Injection points can be declared with the concrete target class because the proxy is a subclass of that class.
- A method can be advised without being on an interface, provided the call **goes through the proxy**, an advisor matches, and the method can be intercepted.
- A `final` target class cannot be subclass-proxied. `final` and `private` methods cannot be overridden for CGLIB advising; methods lacking sufficient visibility may also be restricted.
- A CGLIB proxy does not turn self-invocation `this.method()` into a proxied call; the internal call issue still remains.

**Note:** `proxyTargetClass=true` only selects the **proxy type** for beans needing proxies. It does not instruct Spring to convert all beans into CGLIB proxies and has nothing to do with AspectJ weaving.

### Quick selection table

| Scenario | `proxyTargetClass=false` | `proxyTargetClass=true` |
| --- | --- | --- |
| Target has an interface and is AOP-advised | Usually JDK proxy | CGLIB proxy |
| Target has no interface | Class-based proxy | Class-based proxy |
| Consumer injects by interface | Works well | Works well |
| Consumer must inject concrete implementation class | May fail if JDK proxy is used | Usually valid if class can be subclassed |
| Want to advise a public method declared only on implementation | JDK proxy does not expose that method on the interface | Possible via class proxy when called from outside |
| Target class is `final` | JDK proxy can still proxy matching interfaces | Cannot subclass a final class |
| Target makes internal `this.work()` call | Bypasses advice | Still bypasses advice |

## 3. What is `exposeProxy`?

By default Spring AOP does not provide an API for business code to fetch the current proxy. If enabled:

```java
@Configuration
@EnableAspectJAutoProxy(exposeProxy = true)
class AopConfig {
}
```

Spring can temporarily store the **proxy executing the call** in a `ThreadLocal` for the duration of the AOP proxy invocation. From inside the target during that call, code can retrieve the proxy with:

```java
Object proxy = AopContext.currentProxy();
```

In the example, the proxy-lookup line is **illustrative code** and is only valid when actually executing inside a proxied call with expose enabled. If executed from `main`, a constructor, `@PostConstruct`, an object created with `new`, or another thread without invocation context, `AopContext.currentProxy()` will find no current proxy and throw `IllegalStateException`.

### Why do people use `exposeProxy=true`?

Spring AOP does not intercept normal self-invocation:

```java
public void outer() {
    this.inner(); // Direct call on target, bypassing proxy.
}
```

If you are forced to route the `inner()` call **back through the proxy**, you can do:

```java
public void outer() {
    ((MyService) AopContext.currentProxy()).inner();
}
```

Here `MyService` is the interface implemented by the JDK proxy (or a type compatible with the CGLIB proxy). External callers must invoke `outer()` through the Spring AOP proxy first; the running `outer()` method must have the current proxy exposed. This is an **intentional** workaround for a narrow situation.

Setting `exposeProxy=true` **does not automatically fix** `this.inner()`. Only a call through the proxy reference such as `((MyService) AopContext.currentProxy()).inner()` has a chance to hit advice. It also does not force an advisor to apply to `inner()` if the pointcut does not match.

### Costs and limitations

- `AopContext.currentProxy()` relies on a `ThreadLocal`, meaningful only within the execution scope of the ongoing AOP call; Spring restores the previous state upon exiting the invocation.
- Spring must set up/restore proxy information on each relevant call, adding slight overhead. Enable it only when genuinely needed.
- If execution switches to another thread, such as an async call or thread pool, do not assume the current proxy propagates automatically.
- Business code becomes directly coupled to Spring AOP, harder to pure-unit-test, and prone to error if called outside Spring.
- Retrieving the proxy and casting to the wrong type can cause `ClassCastException`, especially with JDK proxies that do not implement the concrete class.

**Preferred design direction:** extract the method needing advice into another bean and constructor-inject that bean; consumers call through the Spring-supplied dependency. This keeps business logic less coupled to AOP infrastructure. Only use `exposeProxy` when you understand the constraints and need deliberate control over self-invocation.

## 4. Configuring with annotations, XML, and Spring Boot

### Plain Spring Framework

```java
@Configuration
@EnableAspectJAutoProxy(
    proxyTargetClass = true,
    exposeProxy = true
)
class AppConfig {
    // @Bean registrations or @ComponentScan
}
```

This is a **standalone configuration** example. `@EnableAspectJAutoProxy` only affects the application context in which the annotation is registered. With hierarchical application contexts, inspect each actual context rather than assuming an annotation in a parent context enables AOP in all child contexts.

An aspect for Spring to detect must be registered as a bean via `@Component` + `@Aspect` or via a `@Bean` returning an `@Aspect` object. With `@EnableAspectJAutoProxy`, the `aspectjweaver` library is needed to use `@AspectJ` syntax; bytecode weaving is not needed to run Spring proxy AOP.

In equivalent XML:

```xml
<aop:aspectj-autoproxy
    proxy-target-class="true"
    expose-proxy="true"/>
```

The AOP namespace and corresponding bean definitions are required; the XML fragment above is not a complete XML configuration file.

### Spring Boot

Spring Boot has AOP auto-configuration when the required dependencies are present. When using `spring-boot-starter-aop`, typical application configuration **does not need to add** `@EnableAspectJAutoProxy` manually.

In `application.properties`:

```properties
# Spring Boot prefers CGLIB by default.
spring.aop.proxy-target-class=true

# Switch to JDK dynamic proxy if target has a suitable interface:
# spring.aop.proxy-target-class=false
```

In Spring Boot, `spring.aop.proxy-target-class` defaults to `true`. Plain Spring Framework with `@EnableAspectJAutoProxy` without arguments defaults to `proxyTargetClass=false`. This is a common reason for differences between two applications when injecting by concrete class.

Spring Boot also has `spring.aop.auto=true` to allow AOP auto-configuration; `false` disables that **auto-configuration**, yet does not prevent another explicitly declared AOP activation mechanism. Do not confuse it with `proxy-target-class`.

To use `exposeProxy=true` in annotation-based configuration, declare it explicitly:

```java
@Configuration
@EnableAspectJAutoProxy(exposeProxy = true)
class ExplicitAopConfig {
}
```

When combining with Spring Boot, remember Spring can **merge configurations of auto-proxy creators**, so the actual proxy type is also influenced by other configurations in the same context. If Boot is forcing `proxyTargetClass=true`, merely adding `@EnableAspectJAutoProxy(proxyTargetClass=false)` will not guarantee JDK proxies; check `spring.aop.proxy-target-class` and all other auto-proxy declarations.

### Configurations that can interact with one another

Spring merges several AOP proxy creation mechanisms. For instance, `@EnableAspectJAutoProxy(proxyTargetClass=true)` and `@EnableTransactionManagement(proxyTargetClass=true)` can cause all beans handled by those related proxy infrastructures to be created with class-based proxies according to the strongest setting. Thus, never conclude proxy type solely from the annotation closest to a bean. Verify with `AopUtils` after context initialization.

## 5. Runnable Java 17+ project: observing both attributes

The example below uses **Spring Framework 6.2.x**, Maven, and Java 17. There is a `TaskService` that gets auto-proxied because `TraceAspect` applies advice to `work()`. Method `run()` calls `work()` the first time via `this` and the second time via `AopContext.currentProxy()`. Initially it uses a **JDK proxy** with `proxyTargetClass=false` and `exposeProxy=true`.

File structure:

```text
spring-aop-flags/
├── pom.xml
└── src/main/java/demo/aop/
    ├── App.java
    ├── AppConfig.java
    ├── TaskService.java
    ├── TaskServiceImpl.java
    └── TraceAspect.java
```

**`pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-flags</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.18</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.18</version>
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

**`src/main/java/demo/aop/TaskService.java`**

```java
package demo.aop;

public interface TaskService {
    void run();
    void work();
}
```

**`src/main/java/demo/aop/TaskServiceImpl.java`**

```java
package demo.aop;

import org.springframework.aop.framework.AopContext;

public class TaskServiceImpl implements TaskService {
    @Override
    public void run() {
        System.out.println("run()");
        this.work(); // Bypasses proxy: advice will not run.

        // Calling through the proxy with exposeProxy=true:
        ((TaskService) AopContext.currentProxy()).work();
    }

    @Override
    public void work() {
        System.out.println("work()");
    }
}
```

**`src/main/java/demo/aop/TraceAspect.java`**

```java
package demo.aop;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class TraceAspect {
    @Before("execution(* demo.aop.TaskServiceImpl.work(..))")
    public void beforeWork() {
        System.out.println("[advice] before work()");
    }
}
```

**`src/main/java/demo/aop/AppConfig.java`**

```java
package demo.aop;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = false, exposeProxy = true)
public class AppConfig {
    @Bean
    TaskService taskService() {
        return new TaskServiceImpl();
    }

    @Bean
    TraceAspect traceAspect() {
        return new TraceAspect();
    }
}
```

The aspect is explicitly registered via `@Bean`, so `@ComponentScan` is unnecessary. `@EnableAspectJAutoProxy` detects `@Aspect` on `TraceAspect` and creates an AOP proxy for `TaskService`.

**`src/main/java/demo/aop/App.java`**

```java
package demo.aop;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class App {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            TaskService service = context.getBean(TaskService.class);

            System.out.println("isAopProxy=" + AopUtils.isAopProxy(service));
            System.out.println("isJdkDynamicProxy=" + AopUtils.isJdkDynamicProxy(service));
            System.out.println("isCglibProxy=" + AopUtils.isCglibProxy(service));

            service.run();
        }
    }
}
```

Compile and run from the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.aop.App
```

**Stdout lines printed by the example** (ignoring any build tool output/logs):

```text
isAopProxy=true
isJdkDynamicProxy=true
isCglibProxy=false
run()
work()
[advice] before work()
work()
```

Explanation:

1. `TaskServiceImpl` has an interface, and `proxyTargetClass=false`, so Spring chooses a JDK dynamic proxy for the bean needing advice.
2. `service.run()` is an external call passing through the proxy. Since `exposeProxy=true`, the current proxy is available inside `run()`.
3. `this.work()` is a direct call on the target. The first `work()` line has no `[advice]` before it.
4. `((TaskService) AopContext.currentProxy()).work()` sends the call back through the proxy; the `work(..)` pointcut matches so advice runs before the second `work()`.

### Experiment A: change to `proxyTargetClass=true`

In `AppConfig.java` change to:

```java
@EnableAspectJAutoProxy(proxyTargetClass = true, exposeProxy = true)
```

Recompile/re-run with the same command. With a subclassable target like this example, the first three check lines become:

```text
isAopProxy=true
isJdkDynamicProxy=false
isCglibProxy=true
```

The `run()`, `work()`, and advice lines follow the same rules. Changing the proxy type **does not** route `this.work()` through advice. With a CGLIB proxy, callers can use the concrete class if needed; with a JDK proxy, it is best to obtain the bean via `TaskService`.

### Experiment B: change to `exposeProxy=false`

Keep `proxyTargetClass=false` but change to:

```java
@EnableAspectJAutoProxy(proxyTargetClass = false, exposeProxy = false)
```

In `service.run()`, the first `this.work()` still runs; upon reaching `AopContext.currentProxy()`, the application **throws `IllegalStateException`** because Spring does not expose the current proxy. Disabling expose does not mean the advice disappeared: if `App.main()` calls `service.work()` directly through the proxy, advice still works normally. To run cleanly with `expose=false`, remove the `AopContext.currentProxy()` call or redesign calls between beans.

### Experiment C: comparing injection types

When `proxyTargetClass=false`, retrieving the bean via:

```java
TaskService service = context.getBean(TaskService.class);
```

is the right choice, while looking it up via `TaskServiceImpl.class` can fail because a JDK proxy is not an instance of the implementation. When `proxyTargetClass=true` and the class is not final, the context can provide a proxy compatible with `TaskServiceImpl`. Declare dependencies by interface when designing for business contracts; use CGLIB when there is a clear reason for class-based proxying.

## 6. Real-world scenarios and common errors

| Symptom | Interpretation and resolution |
| --- | --- |
| `AopUtils.isAopProxy(bean)` is `false` | Check whether the bean is actually selected by an advisor, the aspect is registered, and auto-proxy is enabled. The two flags do not create a proxy unless advice applies. |
| `@EnableAspectJAutoProxy(proxyTargetClass=false)` yet runtime still uses CGLIB | Spring Boot may default `spring.aop.proxy-target-class=true`, or another auto-proxy config uses class proxies. Check the merged configuration. |
| Type error when injecting the implementation | Likely using a JDK dynamic proxy. Inject by interface or revisit why class proxying is required. |
| Error creating proxy for `final class` | CGLIB must create a subclass. Change the class/method design or use an interface proxy if appropriate. |
| Advice does not run when target calls `this.method()` | Self-invocation bypasses the proxy even when `proxyTargetClass=true`; route the call through another bean or use exposed proxy deliberately. |
| `AopContext.currentProxy()` throws `IllegalStateException` | Expose is not enabled or execution is outside a proxied invocation; do not call in constructors, `@PostConstruct`, from `new`, or from another thread. |
| Casting `(TaskServiceImpl) AopContext.currentProxy()` throws `ClassCastException` | The actual proxy is an interface JDK proxy; cast to an interface implemented by the proxy or adjust configuration with justification. |
| `exposeProxy=true` set yet `this.method()` still has no advice | Expose only grants permission to **obtain** the proxy; direct self-calls still bypass it. You must actually invoke on the proxy reference. |
| `proxyTargetClass=true` set hoping to intercept private/final methods | CGLIB cannot override private/final methods. Move the advice point to a proxyable method or adjust service boundaries. |
| Inside an async request, `currentProxy()` is suddenly missing | Current context is stored per thread; it does not propagate across threads automatically. Move the AOP operation to a Spring bean and call via an injected dependency. |

### When to use which configuration?

- **Plain Spring Framework, interface-based DI, no need to access current proxy:** usually start with `@EnableAspectJAutoProxy` and its defaults. Keep `exposeProxy=false`.
- **Class-based proxy needed because application contract genuinely relies on the class and the class is proxyable:** consider `proxyTargetClass=true`, check method visibility, `final`, scope, and unified configuration.
- **Internal call needs to go through advice:** prefer refactoring into two Spring beans. If impractical, enable `exposeProxy=true` and call via `AopContext.currentProxy()` inside a valid invocation, accepting the coupling to Spring AOP.
- **Spring Boot projects:** check `spring.aop.proxy-target-class` before concluding JDK vs CGLIB; Boot selects class-based proxies by default. Avoid accidentally having conflicting proxy configurations.
- **Debugging or writing integration tests:** inspect the object Spring actually supplies with `AopUtils.isAopProxy`, `isJdkDynamicProxy`, `isCglibProxy`, and test advice via DI calls.

## 7. Review questions

**1. Does `proxyTargetClass=true` force all Spring beans into CGLIB proxies?** No. It forces the **proxy type** for beans that are actually AOP-proxied; beans with no matching advisor can remain plain objects.

**2. Why does the same code use a JDK proxy in plain Spring Framework but CGLIB in Spring Boot?** Because `@EnableAspectJAutoProxy` defaults to `proxyTargetClass=false`, whereas Spring Boot auto-configuration defaults to `spring.aop.proxy-target-class=true`.

**3. Does `exposeProxy=true` fix self-invocation automatically?** Not automatically. It allows obtaining the proxy executing the invocation; the caller must invoke the method through that proxy.

**4. When can `AopContext.currentProxy()` throw `IllegalStateException`?** When no current proxy is exposed in the current thread and invocation, such as `expose=false` or calling outside a proxy.

**5. How do you determine the actual proxy type?** Use `AopUtils.isJdkDynamicProxy(bean)` / `AopUtils.isCglibProxy(bean)` on the bean retrieved directly from the context or DI, then cross-check the merged configuration.

## Official Spring documentation

- [Spring Framework 6.2 — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
- [Spring Framework — `@EnableAspectJAutoProxy` API](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/context/annotation/EnableAspectJAutoProxy.html)
- [Spring Framework — `AopContext` API](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/aop/framework/AopContext.html)
- [Spring Boot — Aspect-Oriented Programming](https://docs.spring.io/spring-boot/reference/features/aop.html)
- [Spring Boot — Application Properties (spring.aop)](https://docs.spring.io/spring-boot/appendix/application-properties/index.html)
