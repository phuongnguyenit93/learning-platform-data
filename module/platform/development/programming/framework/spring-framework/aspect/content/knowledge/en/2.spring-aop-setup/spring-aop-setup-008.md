# Minimal Spring AOP Application to Confirm an Advice Executes

## 1. Hands-on goal

Build a Java 17+ program using only Spring Framework, requiring no web server or database, to confirm that **Spring AOP invoked a `@Before` advice** before a Spring bean's method.

The output must prove four things:

1. `ApplicationContext` contains both the registered service and aspect.
2. The service object retrieved from Spring is an AOP proxy, checked with `AopUtils.isAopProxy(...)`.
3. When calling the method through the proxy, the `ADVICE` line appears **before** the `SERVICE` line.
4. A counter incremented **directly inside the advice** has value `1`; the program prints `CHECK: PASS` only after verifying both the proxy and the counter.

The `@Aspect` and `@Before` annotations use AspectJ syntax, yet are parsed and implemented by **Spring AOP** using proxies. This lesson tests only Spring Aspects; it does not enable the AspectJ compiler or load-time weaving. Having AspectJ libraries on the classpath does not mean Java classes have been woven.

## 2. Preparing the Maven project

Full structure:

~~~text
spring-aop-check/
├── pom.xml
└── src/main/java/example/
    ├── App.java
    ├── NotificationService.java
    └── TraceAspect.java
~~~

Requires JDK 17 or higher and Maven 3.9+. The library versions below are pinned so the example is reproducible; this is not a claim about the latest release.

Contents of `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-aop-check</artifactId>
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
                    <mainClass>example.App</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` supplies the container and bean configuration annotations; `spring-aop` supplies proxy infrastructure along with `AopUtils`. `aspectjweaver` provides the library for Spring to process `@AspectJ` declaration syntax and pointcuts. **No `-javaagent` flag is needed** to run Spring AOP in this example.

## 3. Service with a method for advice to intercept

Create `src/main/java/example/NotificationService.java`:

~~~java
package example;

public class NotificationService {
    public void deliver(String recipient) {
        System.out.println("SERVICE: Delivered to " + recipient);
    }
}
~~~

Both this class and method are `public` and non-`final`. This suits class-based proxying enabled in the configuration section. `@Component` is omitted because `App` will register the service via `@Bean`, making it clear which objects belong to the Spring container.

## 4. Aspect using `@Before` and a counter

Create `src/main/java/example/TraceAspect.java`:

~~~java
package example;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class TraceAspect {
    private final AtomicInteger adviceInvocations = new AtomicInteger();

    @Before("execution(* example.NotificationService.deliver(..))")
    public void beforeDeliver() {
        adviceInvocations.incrementAndGet();
        System.out.println("ADVICE: before deliver");
    }

    public int getAdviceInvocations() {
        return adviceInvocations.get();
    }
}
~~~

Explanation from a **Spring AOP** perspective:

- `@Aspect` informs Spring that the class contains pointcuts/advice in a syntax Spring understands; **it does not automatically turn the class into a Spring bean**.
- `execution(* example.NotificationService.deliver(..))` selects the method execution of `deliver` on that specific class. `*` matches any return type; `(..)` matches any argument list.
- `@Before` causes Spring to call `beforeDeliver()` when a matching method call **goes through the proxy**. The `ADVICE` line is printed only here, not inside the service.
- `adviceInvocations` is incremented only inside the advice method. After one valid call, a value of `1` proves Spring actually triggered the advice. `AtomicInteger` is a simple counter, safe if multiple threads are involved later, though the current example runs sequentially.
- Method `getAdviceInvocations()` lets main code retrieve evidence directly from the **actual aspect bean** registered in the container.

## 5. Enabling Spring AOP and calling the bean via context

Create `src/main/java/example/App.java`:

~~~java
package example;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class App {
    @Bean
    public NotificationService notificationService() {
        return new NotificationService();
    }

    @Bean
    public TraceAspect traceAspect() {
        return new TraceAspect();
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(App.class)) {
            NotificationService service =
                    context.getBean(NotificationService.class);
            TraceAspect aspect = context.getBean(TraceAspect.class);

            boolean proxy = AopUtils.isAopProxy(service);
            System.out.println("PROXY: " + proxy);

            service.deliver("Spring");

            int count = aspect.getAdviceInvocations();
            System.out.println("ADVICE_COUNT: " + count);

            if (!proxy || count != 1) {
                throw new IllegalStateException(
                        "Spring AOP advice was not executed exactly once");
            }
            System.out.println("CHECK: PASS");
        }
    }
}
~~~

**Why is each part necessary?**

1. `@Configuration` declares the Java configuration class; `proxyBeanMethods = false` only controls proxying of `@Bean` methods on the configuration class and **does not disable AOP on services**.
2. `@EnableAspectJAutoProxy(proxyTargetClass = true)` registers the Spring AOP mechanism, allowing class-based (CGLIB) proxies. Class proxying is chosen so the bean can be retrieved by `NotificationService.class` without adding an extra interface. Using `proxyTargetClass = true` **does not** mean AspectJ weaving is enabled.
3. `@Bean notificationService()` and `@Bean traceAspect()` register both the target object and the aspect. `@Aspect` alone is not enough.
4. `AnnotationConfigApplicationContext(App.class)` initializes the Spring container. `getBean(NotificationService.class)` returns the bean Spring provides, which can be a proxy if an advisor matches.
5. `AopUtils.isAopProxy(service)` tells whether Spring created a proxy, yet is not enough by itself to confirm this advice ran; therefore the program also counts advice invocations.
6. `service.deliver("Spring")` is a call **from code outside the target object into the Spring bean**. The call through the proxy is matched against the pointcut before entering the service method.
7. Checking `!proxy || count != 1` causes the program to fail if either piece of evidence is missing. Only when all conditions are met does it print `CHECK: PASS`.

All three classes share `package example;` and sit at their corresponding paths, so they compile together with Maven.

### Running the program

In the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java
~~~

Lines produced by the example code, in exact order:

~~~text
PROXY: true
ADVICE: before deliver
SERVICE: Delivered to Spring
ADVICE_COUNT: 1
CHECK: PASS
~~~

Maven or the environment may emit extra messages of their own; the five lines above are the program output to verify.

- `PROXY: true` proves the service bean was proxied.
- `ADVICE: before deliver` **appearing before** `SERVICE: Delivered to Spring` proves the `@Before` advice executed before the target method.
- `ADVICE_COUNT: 1` proves the `TraceAspect` instance in Spring recorded exactly one advice execution.
- `CHECK: PASS` indicates the program verified both `proxy` and `count`. If either is wrong, `IllegalStateException` is thrown instead of the success line.

Runtime flow:

~~~text
main()
  |
  +--> AnnotationConfigApplicationContext(App.class)
  |       +--> NotificationService bean proxied by Spring
  |       +--> TraceAspect bean has @Before advisor
  |
  +--> service.deliver("Spring")
           |
           v
       Spring proxy -- pointcut matches execution(...deliver(..))
           |
           v
       TraceAspect.beforeDeliver()    -> increment count, print ADVICE
           |
           v
       NotificationService.deliver()   -> print SERVICE
           |
           v
       main() -> read count, check, print CHECK: PASS
~~~

In the flow above, Spring AOP intercepts method execution on the bean using a **proxy**; it does not recompile or weave bytecode of `NotificationService`.

## 6. Control experiments to confirm the cause

Change **one thing at a time** and restore it before the next test:

| Change | Expected result | Conclusion |
| --- | --- | --- |
| Keep sample code intact | `PROXY: true`, `ADVICE_COUNT: 1`, `CHECK: PASS` | Proxy was created, advice ran exactly once |
| Remove `@EnableAspectJAutoProxy` in this Maven app | No AOP proxy created by the example; count = 0, program throws exception | Having beans and `@Aspect` still requires auto-proxy infrastructure |
| Remove `@Bean traceAspect()` | `context.getBean(TraceAspect.class)` fails | `@Aspect` does not mean the bean automatically appears in the context |
| Change pointcut to `execution(* example.NotificationService.notThere(..))` | Advice does not match `deliver`; count = 0, fails CHECK | Pointcut must match the actual method called |
| Directly call `new NotificationService().deliver("Direct")` outside context | Prints SERVICE without ADVICE, does not increment Spring aspect count | Objects instantiated outside the container do not go through the proxy |

Predictions about removing auto-proxy apply to this **minimal project having only this configuration**. A Spring Boot application with the AOP starter or other configuration may already enable auto-proxying automatically, so verify the context before drawing conclusions.

If you want to verify with a debugger, set a breakpoint in `TraceAspect.beforeDeliver()` and run through `service.deliver("Spring")`. Hitting the breakpoint inside the advice is direct proof, while the stdout marker combined with the counter is already sufficient for this lesson's goal.

## 7. Integrating the check into a real Spring project

When moving from the example to an existing Spring project:

1. Pick a `public` method of a **Spring-managed** service called by another caller through the container. Narrow the pointcut expression to the target package/service to avoid unintended logs.
2. Ensure an AOP enablement mechanism exists: `@EnableAspectJAutoProxy` for Java-configured Spring Framework, or Spring Boot AOP auto-configuration in a Boot application.
3. Register the aspect as a Spring bean (`@Bean` or scanned `@Component`), then place `@Before` with an `execution(...)` expression matching that exact method.
4. Add a verifiable signal inside the advice: a unique log marker or a counter used in test environments.
5. Call from a real bean/caller, confirming proxy, advice, and method behavior. In an integration test you can assert the equivalent of `count == 1` instead of relying on manual log inspection.

In Spring Boot, the `spring-boot-starter-aop` dependency usually provides the necessary libraries and auto-configuration; you still must register the aspect. Plain Spring Framework is used here so learners clearly see the AOP enablement point without relying on Boot's automatic configuration.

For applications with multiple advisors such as transactions, security, or caching, distinguish two questions: "is the bean proxied?" and "did **my specific advice** match this call?". `AopUtils.isAopProxy` answers the first; the counter/log inside `beforeDeliver()` answers the second.

## 8. Common errors and troubleshooting

**ADVICE line is missing:**

- Check whether `TraceAspect` is registered in the same `ApplicationContext` as the service. `@Aspect` alone without `@Bean` or component scanning is not enough.
- Check whether `@EnableAspectJAutoProxy` is on a configuration actually loaded; in Boot, check the starter and active auto-configuration.
- Review the `execution(...)` expression: exact package `example`, class `NotificationService`, and method `deliver`. Spring AOP primarily applies advice to method executions through proxies.
- Confirm you are calling the `service` obtained via `context.getBean(...)`; objects created with `new` are not automatically proxied by Spring.
- If a service method calls `this.otherMethod()` on the target itself, that is self-invocation and may bypass advice on the internal method. This example deliberately calls from `main` to avoid confusion.
- With class proxies, `final` methods, `private` methods, or `final` classes cannot be intercepted via subclass proxying; the sample method is `public` and non-`final`.

**`PROXY: true` appears, yet the counter does not increment:**

The existence of a proxy does not guarantee this `@Before` was triggered. The pointcut might not match; the method called might differ from the intended one; or the bean might be proxied due to another advisor. Check the exact aspect bean whose count is read and the exact call path going through the proxy.

**Errors at compile time or startup:**

- `ClassNotFoundException` / `NoClassDefFoundError` related to AspectJ: check whether Maven downloaded the `aspectjweaver` dependency, its version, and the classpath. This lesson does not require `-javaagent` to fix errors.
- `NoSuchBeanDefinitionException`: check `@Bean`/`@Configuration` and whether the configuration class was loaded into the context.
- `Cannot subclass final class` or method proxy errors: check the CGLIB limitations noted above. Avoid concluding that switching to weaving is mandatory for a minimal example.
- If switching to a JDK dynamic proxy on an interface, the bean is normally retrieved via the interface; do not assume casting the proxy to the implementation works. The original project uses `proxyTargetClass = true` to reduce this variable.

**Counter greater than 1:** verify `deliver` was called only once and not accidentally triggered by multiple threads/tests. If multiple aspects exist, separate markers per advice; multiple log lines do not automatically mean one advice ran multiple times. In the sample code, the counter is incremented inside a single advice method.

## 9. Completion checklist

- [ ] Maven compiles all three Java files in the `example` package.
- [ ] `App` has `@Configuration`, `@EnableAspectJAutoProxy`, and two `@Bean` methods.
- [ ] `TraceAspect` has `@Aspect` and a `@Before` pointcut matching `deliver`.
- [ ] The service is retrieved through `ApplicationContext`; no `new`-created object is called.
- [ ] Output contains `PROXY: true`.
- [ ] `ADVICE` appears before `SERVICE`.
- [ ] `ADVICE_COUNT: 1` and `CHECK: PASS` are printed.
- [ ] Understand that the output proves **Spring AOP proxy ran the advice**, not AspectJ weaving.

## Official reference documentation

- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html).
- [Spring Framework — Declaring Advice](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html).
- [Spring Framework — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html).
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html).
