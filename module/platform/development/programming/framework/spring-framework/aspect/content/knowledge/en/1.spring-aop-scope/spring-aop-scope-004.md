# Scope of Spring AOP on Spring-Managed Objects

## 1. Scope of the Lesson

In **proxy-based Spring AOP**, Spring-managed objects (Spring beans) are the scope within which automatic proxy creation and advice application operate. Having a Java class with a method matching a pointcut is not enough for every instance of that class to be intercepted.

After this lesson, you need to distinguish:

- **Spring bean**: an instance registered, instantiated, or supplied to the Spring IoC container according to a bean definition; the container manages supplying the bean reference and related processing steps.
- **Target object**: the instance containing the actual business behavior.
- **AOP proxy**: the intermediary object created by Spring for eligible targets, enabling advice to run before/after/around method calls.
- **Self-created object**: an instance instantiated by application code itself, not registered as a bean; automatic Spring AOP does not wrap this instance.

The focus is **Spring AOP inside ApplicationContext**, not general Aspect theory or standalone AspectJ weaving mechanisms.

## 2. Core Rule: Bean + Proxy + Call Passing Through Proxy

A method call has the opportunity to receive Spring AOP advice when all of the following conditions hold simultaneously:

1. **The target object is within Spring-managed scope**: such as beans from `@Component`, `@Service`, `@Repository`, `@Bean`, or equivalent bean declarations.
2. **Spring AOP is configured and has a matching advisor**: the aspect is registered as a bean, `@AspectJ` support is enabled, and the pointcut matches the method/bean. Not every bean produces a proxy.
3. **The call goes through the proxy reference and the method can be intercepted by the proxy**: if calling the target directly or calling internally via `this`, the proxy's advice is not executed for that call.

```text
External call -> Spring bean reference (proxy, if present)
              -> matching advice -> target.method()
              -> result returned to caller

Direct call   -> new Target().method()
              -> target.method()       (bypasses Spring AOP proxy)
```

**Important distinction:** Being a Spring-managed bean is a prerequisite for Spring AOP's auto-proxy mechanism to operate, but **does not guarantee** every bean has a proxy. Whether a proxy exists also depends on AOP configuration, pointcuts, proxyability of the type/method, and bean creation conditions.

### In What Ways Can Spring Manage Objects?

| How the Object Is Obtained | Does Spring Manage That Instance? | Consequence for Spring AOP |
| --- | --- | --- |
| `@Component`/`@Service` discovered by component scan | Yes | Can be proxied if an advisor matches |
| `@Bean` method returning `new OrderService()` | Yes, **for the instance returned and registered as a bean** | Can be proxied; the `new` keyword inside a factory method does not exclude AOP |
| Bean declared via Java configuration, XML, or bean definition registration | Yes | Can be auto-proxied |
| `context.getBean(OrderService.class)` | Retrieves the bean provided by the container | Typically receives the proxy if the bean was AOP-proxied |
| Instance `new OrderService()` outside the container | No | Does not automatically receive Spring AOP advice |
| `new OrderService()` inside a business method, not registered as a bean | No | Does not automatically receive advice |
| `prototype`-scoped bean retrieved through the container | Yes; each lookup can create a new instance | The returned instance can be proxied depending on conditions |
| Object created in another library or by a factory outside the container | Not by default | Requires explicit integration with Spring; merely sharing a bean's type is not enough |

`@Autowired` or constructor injection typically supplies the bean reference from the container; if Spring wrapped the bean in a proxy, the injected dependency is the reference that can pass through advice. Conversely, holding a separate reference to a target you created yourself bypasses the proxy.

## 3. Runnable Example: Same Class, Two Instance Creation Paths

The example uses **Spring Framework 6.2.x and Java 17+**, without needing Spring Boot. `MessageService` is an ordinary class. `AppConfig` registers one instance as a Spring bean; `Main` simultaneously creates another instance itself for comparison.

Maven structure:

```text
spring-aop-scope/
├── pom.xml
└── src/main/java/example/
    ├── AppConfig.java
    ├── MessageService.java
    ├── AuditAspect.java
    └── Main.java
```

**`pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-aop-scope</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.19</spring.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>${spring.version}</version>
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
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

**`MessageService.java`**

```java
package example;

public class MessageService {
    public void send(String message) {
        System.out.println("send: " + message);
    }
}
```

**`AuditAspect.java`**

```java
package example;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class AuditAspect {
    @Before("execution(* example.MessageService.send(..))")
    public void beforeSend() {
        System.out.println("[aspect] before send");
    }
}
```

**`AppConfig.java`**

```java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy
public class AppConfig {
    @Bean
    public MessageService messageService() {
        return new MessageService();
    }

    @Bean
    public AuditAspect auditAspect() {
        return new AuditAspect();
    }
}
```

**`Main.java`**

```java
package example;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            MessageService managed = context.getBean(MessageService.class);
            System.out.println("managed proxy: " + AopUtils.isAopProxy(managed));
            managed.send("bean");

            MessageService manual = new MessageService();
            System.out.println("manual proxy: " + AopUtils.isAopProxy(manual));
            manual.send("new");
        }
    }
}
```

From the directory containing `pom.xml`, run:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.Main
```

Lines printed by the program:

```text
managed proxy: true
[aspect] before send
send: bean
manual proxy: false
send: new
```

**Step-by-step explanation:**

1. `@EnableAspectJAutoProxy` activates the Spring AOP proxy mechanism in the example context; `@Bean auditAspect()` registers the aspect so Spring finds the advice.
2. `@Bean messageService()` registers the **return value** as a bean. Although the method body uses `new`, this instance is placed under container management.
3. The pointcut matches the bean's `MessageService.send(..)` method. `context.getBean(...)` supplies the proxy; the call `managed.send("bean")` goes through advice.
4. `manual` is an instance of the same class created separately in `Main`. Without registration/proxying, `manual.send("new")` only prints the business line.

If you omit `@EnableAspectJAutoProxy` in a plain Spring Framework application like this example, or do not register `AuditAspect` as a bean, do not expect advice to run. In Spring Boot, the AOP starter and auto-configuration may handle enabling AOP support; verify the application's actual configuration.

> **Easy-to-remember rule:** Spring looks at **instances supplied by the container and call paths going through a proxy**, rather than automatically modifying every Java instance of the same class or every location matching a pointcut string.

## 4. Exceptions to Distinguish Regarding Management Scope

Not every object of the same class as a Spring bean is a bean. `@Bean MessageService messageService() { return new MessageService(); }` places the **returned instance** into the container; `new MessageService()` called in another utility does not. For prototype beans, each lookup from the container can receive a new instance, and each instance can still be AOP-proxied if eligible.

A Spring-managed bean is not guaranteed to receive advice either: the aspect may not be registered, the pointcut may not match, the method may not be interceptable by the proxy, or the caller may hold a raw target reference. Calling `this.inner()` from another method on the target does not re-enter the proxy, so advice attached only to `inner()` does not run in that call step. Extract responsibilities into collaborating beans when clear interception is needed.

JDK proxies only expose methods on the proxied interfaces; CGLIB cannot override `final`/`private` methods or subclass a `final class`. Constructors, static methods, and field access are not join points of Spring AOP proxies. Calls during initialization phases such as `@PostConstruct` should also not be designed assuming the proxy is already in effect.

Therefore, two distinct facts must be verified: **the object is registered with Spring** and **the call goes through a proxy with a matching advisor**. This article focuses on the boundary of container-managed instances; self-invocation details and advice ordering belong to proxy mechanics.

## 5. Checking Scope in a Real Application

When advice is expected to run but actually does not, check in order:

1. **Is the bean really in the right context?** Check `@ComponentScan`, `@Bean`, profiles/conditions, and the context containing the bean. `context.containsBean("beanName")` checks a **bean name**, not proof that an arbitrary object is a bean.
2. **Is the reference being called a proxy?** Use `AopUtils.isAopProxy(reference)`, optionally combined with `AopUtils.isJdkDynamicProxy(...)` or `AopUtils.isCglibProxy(...)`. `false` means the inspected reference is not a Spring AOP proxy; do not automatically conclude all AOP configuration is wrong.
3. **Where did the caller get the reference?** Compare `context.getBean(...)` or dependency injection against an instance created with `new`. If using a JDK proxy, inject/call via the appropriate interface type instead of casting to the implementation.
4. **Does the call path loop back via `this`?** If so, advice on the internally called method does not get a pass through the proxy.
5. **Are the pointcut and interceptability right?** Check package, modifiers, proxy type, method signature, annotation, overloads, and actual bean. An expression matching a class name is not enough if the call itself does not go through the proxy.
6. **Are there multiple ApplicationContexts or beans of the same type?** Verify the exact context and bean reference in use; an aspect in one context does not automatically apply to every instance created by another context or another library.

Small diagnostic snippet once you have `context`:

```java
// Assuming an AnnotationConfigApplicationContext context
// and a MessageService bean registered in the context.
Object bean = context.getBean("messageService");
System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.getTargetClass(bean).getName());
```

The first statement observes the **actual proxy reference**; the latter helps inspect the target class behind the proxy. Do not merely check `bean.getClass()` and equate the dynamically generated proxy class with the business class.

## 6. Scenarios to Distinguish

| Scenario | Does Spring AOP Advice Run? | Reason |
| --- | --- | --- |
| Controller/bean A calls a public method on injected service B, and B has a proxy matching the pointcut | Yes | The call goes through proxy B |
| `@Bean` returns `new Service()`, then the caller gets the bean via context and calls a matching method | Yes, if a valid proxy is created | The instance is registered as a bean |
| A utility creates `new Service()` and calls the same method | No | Out-of-container instance, does not go through proxy |
| Service is proxied, but `this.work()` is called inside the Service itself | No for `work()`'s own advice | Self-invocation bypasses the proxy |
| A Spring bean matches no advisor | No | No matching advice |
| Attempting to advise a `private` method | No | The method is not intercepted by the proxy |
| Only adding `@Aspect` on a class without registering it as a bean | Not automatically | Spring does not discover the aspect to configure AOP |

Rows marked "Yes" always assume **working Spring AOP configuration, a correct pointcut, and an interceptable method**. One should not infer that every bean gets intercepted.

## 7. Clear Boundaries of the Topic

Spring AOP is designed for **method execution on Spring beans through proxies**. If a problem strictly requires applying advice to objects not managed by Spring, constructors, field access, or internal calls regardless of proxy, that requirement goes beyond proxy-based Spring AOP. Spring integrates with AspectJ weaving for other scenarios, but that is a **separate mechanism** requiring separate configuration; do not confuse `@EnableAspectJAutoProxy` with enabling bytecode weaving.

**Self-check:** Given a class `PaymentService` with one instance registered via `@Bean` and one instance created with `new`. Both have a `pay()` method matching a pointcut. Call in turn via `context.getBean(...).pay()`, `new PaymentService().pay()`, and `this.pay()` from a method inside the bean. Predict which call path goes through the Spring proxy and explain why. Answer: only the call through the proxy bean reference (if created and matched) runs `pay()`'s advice; the other two bypass the proxy.

**Spring Framework Documentation:**
- [Spring AOP — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html)
- [Spring AOP — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring AOP — Declaring an Aspect](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/at-aspectj.html)