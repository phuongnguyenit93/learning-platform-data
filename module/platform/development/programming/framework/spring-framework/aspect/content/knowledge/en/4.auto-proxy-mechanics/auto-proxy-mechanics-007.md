# Early Bean Initialization and Not-Eligible-for-Auto-Proxying in Spring AOP

## 1. Why Does Spring Warn That a Bean Is "not eligible for auto-proxying"?

When an application uses Spring AOP, some Spring beans must be **created after the `BeanPostProcessor` (BPP) system is ready** so the auto-proxy creator can inspect and wrap the bean with a proxy. If a bean is initialized **too early**, while Spring is still finding, instantiating, or registering BPPs, that bean may only pass through part of the BPP chain. As a result, the created bean may **not be wrapped with a Spring AOP proxy**, even though its type or methods appear to match an `@Aspect` advice.

Common warning message:

~~~text
Bean 'someBean' of type [example.SomeBean] is not eligible for getting processed
by all BeanPostProcessors (for example: not eligible for auto-proxying)
~~~

The message above is an **illustrative form**, not a log line guaranteed word-for-word across every Spring version: the bean name, class name, and additional details may vary. It states that the bean was created before all expected post-processors were registered. **It does not automatically mean the bean has a bug, or is guaranteed to lack every kind of proxy**; you must check the actual proxy and initialization sequence. However, with Spring AOP, this is a very noteworthy clue when advice does not run.

The scope of this lesson focuses on **Spring Framework auto-proxying**, `BeanPostProcessor` registration order, dependency relationships causing early bean creation, observable evidence, and how to fix it. There is no need to expand into standalone AspectJ weaving theory.

## 2. Mechanism Causing This Condition

### 2.1. The Auto-Proxy Creator Is Also a BeanPostProcessor

For `@AspectJ`-style Spring AOP, `@EnableAspectJAutoProxy` registers Spring's auto-proxy creator infrastructure (typically `AnnotationAwareAspectJAutoProxyCreator`, extending `AbstractAutoProxyCreator`). This infrastructure is a specialized **`BeanPostProcessor`**: when a Spring bean is created, it looks for matching advisors and can return a proxy instead of the target.

Standard flow, simplified:

~~~text
Register BeanDefinitions
       |
       v
Spring finds and instantiates BeanPostProcessors
       |
       v
Spring fully registers BPPs, including auto-proxy creator
       |
       v
Create regular application beans
       |
       v
postProcessBeforeInitialization(...)
       |
       v
@PostConstruct / InitializingBean / custom init method
       |
       v
postProcessAfterInitialization(...)
       |
       +--> no advisor applies: original bean
       |
       +--> advisor applies: Spring AOP proxy
                                    |
                                    v
                         Bean received by caller
                                    |
                                    v
                        proxy -> advice -> target
~~~

This is the common flow for regular singleton beans. Spring also has extension points supporting early references, such as `SmartInstantiationAwareBeanPostProcessor`, and special dependency situations; the diagram should not be treated as an absolute call order for every kind of bean.

The auto-proxy creator evaluates beans during **bean creation**, and does not re-run on every method invocation. Once a proxy exists, a call going through the proxy enters the advice chain. When a bean was initialized before the auto-proxy creator fully participated, calling methods later **does not make Spring retroactively wrap that instance**.

### 2.2. Special Phase for Creating and Registering BPPs

`ApplicationContext` must prepare BPPs before creating batches of application beans. To do that, Spring proactively finds beans of type `BeanPostProcessor`, instantiates them **early**, and registers them with the container. Those instantiated BPPs, along with beans pulled in as their dependencies, can come into existence **before all other BPPs, including the auto-proxy creator, are fully registered**.

An error-prone sequence:

~~~text
ApplicationContext.refresh()
          |
          v
Begin BeanPostProcessor registration
          |
          v
Instantiate customAuditPostProcessor
          |
          +--> constructor / @Bean parameter requires paymentService
                              |
                              v
                     paymentService is created immediately
                              |
                              v
                     Not enough BPPs yet to evaluate auto-proxying
                              |
                              v
                     Bean may remain as raw target
          |
          v
Remaining BPPs (including auto-proxy creator) are registered
          |
          v
ApplicationContext continues creating other beans
          |
          v
paymentService already exists; not recreated automatically
~~~

In some situations, a BPP's dependency can be created early due to type-based lookup, `@Autowired`, `@Resource`, manual calls to `getBean()`, or an `@Bean` method creating a BPP that takes a service parameter. There does not need to be an explicit `new Service()` call in configuration for the issue to appear.

Core point: **Spring AOP also depends on a BeanPostProcessor**. A bean born during the BPP bootstrap phase itself may not get the chance to be processed by the full auto-proxy pipeline.

### 2.3. BeanPostProcessor and Its Dependencies

According to Spring documentation, `BeanPostProcessor` instances themselves and the beans they directly reference are usually **not eligible for auto-proxying like regular application beans created afterward**. A frequently seen example is a business BPP injected with a service that itself needs `@Before`/`@Around` or proxy-based `@Transactional`.

However, read the warning logically rather than over-concluding:

- It primarily detects **post-processing timing and coverage**: a bean was created while the number of registered BPPs was below the expected target.
- It does **not** confirm whether a specific pointcut would match or not; you still need to check aspects and advisors.
- Not every BPP is designed to be an advised target; certain Spring infrastructure beans are intentionally excluded from auto-proxying.
- If the application has other proxy mechanisms or creates proxies directly, the exact status must be confirmed from the actual bean type received and its advisors.
- Do not try to "fix" it by enabling the AspectJ weaver, because the problem lies in **Spring container lifecycle and Spring AOP proxies**.

## 3. Practical Causes in Spring Configuration

| Cause | Why does it trigger early initialization? | Symptom |
| --- | --- | --- |
| Custom BPP constructor takes an application service | Container must build the service to build the BPP | Service is initialized during BPP registration phase |
| Static `@Bean` creating a BPP has a service parameter | `static` avoids instantiating the config class, yet **does not avoid injecting the service dependency early** | Warning for the passed-in service |
| Non-static `@Bean` returning a `BeanPostProcessor` | To invoke the factory method, Spring must instantiate the configuration object early too | Configuration class and related dependencies may miss full post-processing |
| BPP calls `getBean("orderService")` during construction | Pulls business bean out before the auto-proxy creator is ready | BPP startup makes the service appear abnormally early |
| `@Resource`/autowiring inside BPP triggers Spring type-based lookup | Some dependency lookups can pull in unexpected beans | Unrelated bean by name still gets created early |
| Custom `BeanFactoryPostProcessor` calls `getBean(...)` | Forces instance creation in the definition-processing phase, before the normal BPP phase | Bean does not pass through all post-processors |
| BPP registered late at runtime | Already-created beans do not automatically get the new processor applied | Some beans have proxies, others of the same type do not |

An important nuance: **`static @Bean` is recommended for BPPs, but it is not a cure-all for eager dependencies**. When the method still declares a business service parameter, injecting that parameter can pull the service into BPP creation too early.

## 4. Spring Framework Example Reproducing and Contrasting the Issue

The example below intentionally creates **two beans of the same type**: `earlyService` is injected into a `PriorityOrdered BeanPostProcessor` during the bootstrap phase; `normalService` is created later and gets the chance to receive an AOP proxy. One `@Before` aspect matches methods on both. The output makes clear why one bean does not receive advice despite having the same class and pointcut.

Requirements: **Java 17+**, Maven, Spring Framework **6.2.0**. This is a standalone runnable lesson, without Spring Boot and without AspectJ weaving.

Project structure:

~~~text
spring-early-bpp/
├── pom.xml
└── src/main/java/demo/
    ├── App.java
    ├── TrackedService.java
    ├── TraceAspect.java
    └── EarlyReferenceBpp.java
~~~

### 4.1. Maven Dependencies

Create `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-early-bpp</artifactId>
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
                    <mainClass>demo.App</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` handles the container and BPP registration; `spring-aop` supports AOP proxies; `aspectjweaver` provides annotation/pointcut types so Spring understands `@AspectJ`. **Adding this dependency does not activate bytecode weaving**.

### 4.2. Shared Service for Both Beans

Create `src/main/java/demo/TrackedService.java`:

~~~java
package demo;

public class TrackedService {
    private final String name;

    public TrackedService(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }

    public void execute() {
        System.out.println("TARGET: " + name);
    }
}
~~~

Both the `TrackedService` class and the `execute` method are non-`final`, allowing Spring to create a subclass proxy when `proxyTargetClass = true`. The `earlyService` and `normalService` beans differ only by name label, letting us contrast them under the same advisor.

### 4.3. Shared Aspect for Both Services

Create `src/main/java/demo/TraceAspect.java`:

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class TraceAspect {
    private final AtomicInteger calls = new AtomicInteger();

    @Before("execution(* demo.TrackedService.execute(..))")
    public void beforeExecute(JoinPoint joinPoint) {
        TrackedService target = (TrackedService) joinPoint.getTarget();
        calls.incrementAndGet();
        System.out.println("ADVICE: " + target.getName());
    }

    public int count() {
        return calls.get();
    }
}
~~~

The advice only selects `TrackedService.execute()` method execution. If both beans are proxied, every call to `execute()` through a bean reference will match. When only `normalService` is proxied, only calls to that bean trigger the advice and increment `calls`.

### 4.4. BeanPostProcessor Intentionally Pulling a Service Into Bootstrap

Create `src/main/java/demo/EarlyReferenceBpp.java`:

~~~java
package demo;

import org.springframework.beans.factory.config.BeanPostProcessor;
import org.springframework.core.Ordered;
import org.springframework.core.PriorityOrdered;

public class EarlyReferenceBpp implements BeanPostProcessor, PriorityOrdered {
    private final TrackedService capturedService;

    public EarlyReferenceBpp(TrackedService capturedService) {
        this.capturedService = capturedService;
    }

    @Override
    public int getOrder() {
        return Ordered.HIGHEST_PRECEDENCE;
    }
}
~~~

In Spring 6.2, both `BeanPostProcessor` callbacks have default implementations, so the example does not need to override `postProcessBeforeInitialization` or `postProcessAfterInitialization` just to leave the bean untouched. This BPP **does not create proxies, does not invoke aspects, and does not alter business logic**. It intentionally holds a reference to an application service in its constructor to illustrate **a dependency pulled in too early**.

`PriorityOrdered` puts the custom processor in the group Spring prepares ahead of BPPs implementing only `Ordered`. Spring 6.2's auto-proxy creator extends `AbstractAutoProxyCreator`, which implements `Ordered`. In this project, resolving `EarlyReferenceBpp`'s dependency happens while BPPs are still being registered, before the auto-proxy creator processes `earlyService` in the normal flow.

Do not use `PriorityOrdered` to design a business BPP that depends on a service. It is used here **only to reproduce the failure scenario cleanly**.

### 4.5. Configuration and Runner Code

Create `src/main/java/demo/App.java`:

~~~java
package demo;

import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

public class App {
    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy(proxyTargetClass = true)
    static class Config {
        @Bean
        public TrackedService earlyService() {
            return new TrackedService("early");
        }

        @Bean
        public TrackedService normalService() {
            return new TrackedService("normal");
        }

        @Bean
        public TraceAspect traceAspect() {
            return new TraceAspect();
        }

        @Bean
        public static EarlyReferenceBpp earlyReferenceBpp(
                @Qualifier("earlyService") TrackedService earlyService) {
            return new EarlyReferenceBpp(earlyService);
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            TrackedService early =
                    (TrackedService) context.getBean("earlyService");
            TrackedService normal =
                    (TrackedService) context.getBean("normalService");
            TraceAspect aspect = context.getBean(TraceAspect.class);

            boolean earlyProxy = AopUtils.isAopProxy(early);
            boolean normalProxy = AopUtils.isAopProxy(normal);

            System.out.println("EARLY_PROXY: " + earlyProxy);
            System.out.println("NORMAL_PROXY: " + normalProxy);

            early.execute();
            normal.execute();

            System.out.println("ADVICE_COUNT: " + aspect.count());

            if (earlyProxy || !normalProxy || aspect.count() != 1) {
                throw new IllegalStateException(
                        "Unexpected Spring AOP auto-proxy behavior");
            }
            System.out.println("CHECK: PASS");
        }
    }
}
~~~

Detailed explanation of the decisions:

- `@EnableAspectJAutoProxy(proxyTargetClass = true)` activates Spring AOP and requests class-based proxies. It does not depend on whether the two services implement an interface.
- `@Bean earlyService()` and `@Bean normalService()` both return `TrackedService`. `@Bean traceAspect()` creates the Spring bean holding the `@Before` advisor.
- `@Bean public static EarlyReferenceBpp earlyReferenceBpp(...)` lets Spring discover/instantiate the BPP without instantiating `Config` solely for the factory method. **However**, the `@Qualifier("earlyService")` parameter forces Spring to create `earlyService` to pass to the BPP constructor, right during the processor registration phase. Declaring `static` cannot block this eager dependency.
- The **concrete** return type `EarlyReferenceBpp` tells Spring that the factory method produces a `PriorityOrdered` BPP right at type-inspection time; returning an overly general type can make detection and processing order inaccurate.
- `normalService` is not a dependency of the BPP, so it is created during normal singleton initialization, after Spring has registered the auto-proxy creator.
- The program retrieves the beans **through the Spring context**, checks them directly with `AopUtils.isAopProxy`, and then calls the same `execute()` method on both beans. The aspect's counter verifies that exactly one advice ran.

### 4.6. Running and Observing the Output

In the `spring-early-bpp` directory:

~~~bash
mvn -q compile exec:java
~~~

Lines **printed by the Java program itself** in the Spring 6.2.0 project configured above:

~~~text
EARLY_PROXY: false
NORMAL_PROXY: true
TARGET: early
ADVICE: normal
TARGET: normal
ADVICE_COUNT: 1
CHECK: PASS
~~~

There may be a WARN from Spring's logger reporting that `earlyService` was not processed by all BPPs. **The warning is not part of the seven lines printed by the program**; logger name, text, and log order depend on logging configuration. The goal here is to observe `AopUtils` and `TraceAspect.count()`.

Reading the output along the two branches:

- **Early branch:** `earlyService` was created in order to instantiate `EarlyReferenceBpp` before the auto-proxy creator had a chance to fully process that bean. When `early.execute()` is called, only `TARGET: early` appears, with no `ADVICE: early`.
- **Normal branch:** `normalService` was created after the BPP registration phase; the auto-proxy creator found the matching `TraceAspect` advisor and created a proxy; `normal.execute()` goes through the proxy, printing `ADVICE: normal` before `TARGET: normal`.
- Both share the same class and use the same pointcut. What differs is **when Spring creates the bean relative to processor registration**.
- If stdout/proxy status differs from expectations, the program throws an exception rather than reporting success. When running with a different Spring version or configuration, inspect bootstrap logs and registered BPPs instead of forcing the data to match the template.

## 5. How to Fix: Do Not Request a Service While Creating a BeanPostProcessor

The best fix is to remove the BPP → business service relationship at initialization time. If the BPP only needs to inspect bean info, write callbacks taking `Object bean, String beanName`; if business logic is needed, move it to a service or advice that runs **after the context finishes initialization**.

In the project above, a minimal fix for self-verification is to replace `EarlyReferenceBpp` with a processor that does not hold `TrackedService`:

~~~java
package demo;

import org.springframework.beans.factory.config.BeanPostProcessor;
import org.springframework.core.Ordered;
import org.springframework.core.PriorityOrdered;

public class EarlyReferenceBpp implements BeanPostProcessor, PriorityOrdered {
    public EarlyReferenceBpp() {
    }

    @Override
    public int getOrder() {
        return Ordered.HIGHEST_PRECEDENCE;
    }
}
~~~

At the same time, replace the BPP factory method in `App.Config` with:

~~~java
@Bean
public static EarlyReferenceBpp earlyReferenceBpp() {
    return new EarlyReferenceBpp();
}
~~~

These two code fences are **replacements for the two corresponding parts in the existing project**, not standalone Java files. Now `earlyService` is no longer created by a BPP dependency. With no other cause of early initialization, both services pass through the auto-proxy creator:

~~~text
EARLY_PROXY: true
NORMAL_PROXY: true
ADVICE: early
TARGET: early
ADVICE: normal
TARGET: normal
ADVICE_COUNT: 2
~~~

Also update the check in `App.main()` for the new scenario:

~~~java
if (!earlyProxy || !normalProxy || aspect.count() != 2) {
    throw new IllegalStateException(
            "Expected both service beans to be proxied");
}
~~~

After replacing all three snippets above, the program continues to print `CHECK: PASS`. If you only replace the BPP while keeping the old condition `earlyProxy || ... count != 1`, the `CHECK` result will fail **according to the old check**, not because Spring AOP broke.

### 5.1. When a BPP Genuinely Needs a Dependency

Distinguish three needs:

1. **Needs simple configuration:** pass literals, plain config, or bean definition metadata into the BPP, avoiding injecting services that carry advice/transactions.
2. **Needs to look up a bean when handling each callback:** consider redesigning so the BPP does not become a business coordinator; if lookup is unavoidable, only look up at safe times and manage dependencies/recursion carefully. Using `ObjectProvider`/`Provider` can **defer** dependency resolution, yet **does not automatically guarantee safety** if `getObject()` is called right inside the constructor or during a bootstrap callback.
3. **Needs normal business processing:** do not use a BPP as a place to invoke services. Use an `@Aspect` advice, another service, or a listener running after context refresh depending on the task. With Spring AOP, that is usually the simplest option.

### 5.2. Declaring `@Bean` for a BPP Properly

A preferred declaration:

~~~java
@Bean
public static CustomBeanPostProcessor customBeanPostProcessor() {
    return new CustomBeanPostProcessor();
}
~~~

`CustomBeanPostProcessor` is an **illustrative** class name, not a class defined in the practice project. Two main points:

- **`static`:** the container can invoke the factory method without prematurely instantiating the configuration instance.
- **No strong dependencies on business services:** avoids initializing services during the BPP registration phase.

Avoid declaring:

~~~java
@Bean
public BeanPostProcessor myProcessor(PaymentService paymentService) {
    return new MyProcessor(paymentService);
}
~~~

This is an **example of configuration to reconsider**, not a standalone compilable snippet. `PaymentService` and `MyProcessor` are illustrative names only. A non-static factory method can trigger the config class early, and the service parameter pulls a business bean dependency into bootstrap.

Furthermore, a factory method creating a BPP needs a return type that clearly reveals the BPP type; if declared with an overly broad return type like `Object`, Spring may fail to accurately detect the BPP early enough while gathering the post-processor list.

## 6. Similar-Looking Situations With Different Causes

### 6.1. Proxy Exists, Yet Advice Still Does Not Run

`AopUtils.isAopProxy(bean) == true` is evidence that a proxy exists, not evidence that a specific advisor will run. If a proxy already exists, check:

- Does the `execution(...)` pointcut actually match the method?
- Is the caller invoking through the Spring bean proxy or calling `this.method()` inside the target?
- Is the method proxyable (JDK interface, CGLIB `final` class/method, visibility)?
- Are there multiple other advisors/proxies covering only certain methods?

Conversely, if the bean does not receive a proxy and a "not eligible for auto-proxying" WARN appears, prioritize investigating **initialization timing and BPP dependencies** before changing the pointcut expression.

### 6.2. @PostConstruct Calling an Advised Method

In proxy-based Spring AOP, a method called directly inside the target's constructor or `@PostConstruct` usually does not go through the final proxy, even if the bean later becomes a proxy. This is **not necessarily** "the bean is not eligible for auto-proxying". Distinguish clearly:

| Situation | Proxy after context initialization? | Advice on the observed call? |
| --- | --- | --- |
| Bean created in right phase, method called through proxy | Yes, if advisor matches | Yes when matched |
| Bean created in right phase, internal method called inside `@PostConstruct` | May exist afterward | Calls during init usually bypass the proxy |
| Bean initialized too early due to BPP dependency | May not exist | Calls to target are not AOP-intercepted |
| Calling an object manually created with `new` outside Spring | Not a Spring proxy | No, barring another independent mechanism |

Moving logic out of `@PostConstruct` or separating services can solve calling methods during init, while the cause of a *not eligible* warning must be examined separately.

### 6.3. Circular Dependencies and Early References

The auto-proxy creator has mechanisms like `getEarlyBeanReference(...)` to support certain circular dependency cases, avoiding handing out a raw target to some beans and a proxy elsewhere later. However, this capability is **not a guarantee that every prematurely initialized bean will be proxied**, especially when all BPPs have not yet been registered. Do not use circular references as a workaround for early initialization warnings. Refactoring dependencies to break the cycle is far more reliable.

### 6.4. Parent/Child Contexts and Proxy Configuration

BeanPostProcessors registered with an `ApplicationContext` are scoped to that container. A BPP in a parent does not automatically process beans instantiated in a child. In multi-context applications, check where the aspect, auto-proxy creator, and service are created; do not blame every missing advice on early initialization.

### 6.5. Spring Boot Auto-Configuration

Spring Boot can enable AOP automatically when the corresponding starter dependency is present, yet Spring's proxy mechanism still relies on container post-processing. If a service is created too early due to a user-declared BPP or its dependencies, merely adding `spring-boot-starter-aop` or `@EnableAspectJAutoProxy` usually **does not fix initialization timing**. Check logs, the bean graph, and processor placement first.

## 7. Practical Diagnostic Workflow

When seeing the warning in logs or when advice suddenly does not run, proceed in order:

1. **Record the exact bean name and type** mentioned in the WARN; do not guess by symptom. If the log only reports "not eligible ...", trace the bootstrap cause of that specific bean.
2. **Confirm proxy status after the context is ready**: call `AopUtils.isAopProxy(context.getBean("beanName"))`. For a proxied Spring bean, consider checking `isCglibProxy`/`isJdkDynamicProxy` next.
3. **Check BPP registration:** inspect classes implementing `BeanPostProcessor`, especially custom BPPs, `BeanPostProcessor`s returned via `@Bean`, and the auto-proxy creator registered by `@EnableAspectJAutoProxy`.
4. **Find dependency relationships:** service constructor parameters, `@Autowired`/`@Resource` inside a BPP, non-static BPP factory methods, early `getBean()` calls, or a `BeanFactoryPostProcessor` instantiating objects.
5. **Read startup order** using your environment's logging framework/debug trace. Compare whether the bean was created before or after the auto-proxy creator was registered and aspect infrastructure was ready.
6. **Decouple eager dependencies from the BPP:** static `@Bean`, reduce dependencies, or defer dependency resolution until an appropriate time, without resolving business beans right inside bootstrap callbacks.
7. **Re-run and verify actual behavior:** is the WARN log gone, does the AOP proxy appear, and does the advice run via an external caller? Measure proxy and advice independently, rather than relying only on the warning disappearing.
8. **Check secondary causes if it still fails:** pointcuts, self-invocation, objects outside the container, `final` methods, multiple contexts, or other advisors.

### Using AopUtils to Measure Without Inferring from Proxy Class Names

The following illustrative snippet goes **inside code that already has a `context` variable**, not a standalone Java file:

~~~java
Object bean = context.getBean("normalService");

System.out.println("AOP=" + org.springframework.aop.support.AopUtils.isAopProxy(bean));
System.out.println("JDK=" + org.springframework.aop.support.AopUtils.isJdkDynamicProxy(bean));
System.out.println("CGLIB=" + org.springframework.aop.support.AopUtils.isCglibProxy(bean));
~~~

In the original example, `normalService` is a class-based proxy, so the three lines are `AOP=true`, `JDK=false`, `CGLIB=true` respectively. If an application bean has no proxy, go back and check both the lifecycle and advisors/pointcuts; you cannot conclude solely from a class name containing `$$SpringCGLIB$$` or a single WARN.

## 8. Things Not to Do to "Fix" the Warning

- **Do not silence logs or raise the logging level and consider it fixed.** The warning is a signal of an abnormal bean-creation path; you need to understand which bean and which BPP are involved.
- **Do not mechanically use `@DependsOn` to force ordering.** Creating a bean before processors are ready can worsen the problem and does not guarantee a Spring AOP proxy appears.
- **Do not try calling `getBean()` a second time hoping the container will re-create a proxy.** An already-created singleton may be retained; looking it up again usually returns the same instance.
- **Do not manually wrap a second proxy inside a custom BPP if standard advice is all you need.** This easily causes double-proxying, alters advisor order, and conflicts with transactions/caching.
- **Do not confuse `static @Bean` with removing dependencies.** `static` avoids instantiating the configuration object early; factory method parameters are still resolved by Spring when building the processor.
- **Do not assume you must switch to AspectJ weaving.** Fix the bean initialization chain and keep Spring AOP if method scope on managed Spring beans still fits.

## 9. Self-Check Exercises

1. Why can a `BeanPostProcessor` cause a service to miss Spring AOP advice?  
   **Because initializing the BPP pulls the service into the container before all auto-proxy creators/BPPs are ready; the service does not pass through enough post-processing to become a proxy.**

2. Why can declaring `@Bean static EarlyReferenceBpp earlyReferenceBpp(TrackedService earlyService)` still fail?  
   **Because `static` does not prevent Spring from having to initialize the service used as a parameter.**

3. Why do two beans with the same class and same pointcut end up with only one bean proxied?  
   **Because of when each bean is created relative to the BPP registration phase, not because aspect syntax differs.**

4. Does the "not eligible for auto-proxying" message guarantee the bean will never have a proxy?  
   **No. It indicates part of post-processing was missed; you must measure the bean's actual state and configuration.**

5. How do you confirm the issue is resolved?  
   **After removing the dependency causing early initialization, check the bean retrieved from the context with `AopUtils.isAopProxy(...)` and verify the advice actually runs on calls through the proxy.**

## 10. Spring Framework Documentation

- [Container Extension Points — BeanPostProcessor, early initialization](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-extension.html): BPP processing chain, early-initialized beans, WARN, and `static @Bean` recommendations.
- [Spring @Bean Javadoc — BeanPostProcessor-returning methods](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/annotation/Bean.html): concrete return type, `static`, and avoiding dependencies during bootstrap.
- [Spring @AspectJ support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj.html): Spring interpreting `@AspectJ` syntax via proxy infrastructure.
- [Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html): how to enable automatic proxy creation for Spring beans.
- [Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): proxy types and method invocation limitations in Spring AOP.
