# End-to-End Example: Intercepting Service Bean Calls in ApplicationContext with Spring AOP

## 1. Objectives and Boundaries

This article builds a **plain Spring Framework** application to observe how Spring AOP intercepts when application code calls methods of a **service bean obtained from ApplicationContext**. After practicing, you will be able to:

- Register a service and a Spring aspect in the same ApplicationContext.
- Enable automatic proxy creation using **@EnableAspectJAutoProxy**.
- Trace the path of a call: client → Spring proxy → advice → target service → client.
- Check whether a returned bean is an AOP proxy.
- Explain why calls from another bean go through the proxy, whereas internal calls using **this** typically bypass advice.
- Identify configuration mistakes that prevent a service method from being intercepted.

The focus is **Spring's mechanism for attaching advice to calls on container-managed beans**. General AOP concepts are mentioned only to the extent needed to read and run the example; this article does not implement AspectJ weaving, bytecode instrumentation, or a Spring-independent AOP system.

## 2. Practical Scenario

Suppose an application has an **OrderService** receiving an order code. We want to print a trace before and after processing without adding log statements into the business method. We create:

1. **OrderService**: the contract used by code calling the service.
2. **OrderServiceImpl**: the bean executing business logic, managed by Spring via **@Service**.
3. **TraceAspect**: the aspect bean discovered by Spring via **@Aspect** and **@Component**; advice applies only to the **place(...)** method.
4. **AppConfig**: configures component scanning and enables Spring AOP.
5. **App**: creates the ApplicationContext, retrieves the service from the container, invokes methods, and checks the results.

Expected call path diagram:

~~~text
App
 │
 ├─ context.getBean(OrderService.class)
 │                 │
 │          Spring AOP proxy
 │                 │
 └─ service.place("A-01")
                   │
            TraceAspect: before
                   │
          OrderServiceImpl.place
                   │
            TraceAspect: after
                   │
             Return value
~~~

One core point: the **service** variable in client code points to the proxy object handed out by Spring. Advice does not automatically inject itself into every Java call everywhere; it runs when the call passes through a matching proxy.

## 3. Project Setup

The example uses **Java 17+**, **Maven 3.9+**, **Spring Framework 6.2.12**, and **AspectJ Weaver 1.9.24**. The project **does not require Spring Boot** or an HTTP server.

Structure:

~~~text
spring-aop-service-demo/
├── pom.xml
└── src/main/java/demo/
    ├── App.java
    ├── AppConfig.java
    ├── OrderService.java
    ├── OrderServiceImpl.java
    └── TraceAspect.java
~~~

**pom.xml**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-service-demo</artifactId>
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

**spring-context** brings in the container components and the Spring AOP module needed in the example; **aspectjweaver** supplies the annotation types, JoinPoint types, and AspectJ-style pointcut expression parser. With this setup, Spring still performs **proxy-based AOP**: no AspectJ compiler is enabled and no Java agent is attached to weave classes.

## 4. Writing the Java Code

### 4.1. Defining the Service Contract

**src/main/java/demo/OrderService.java**

~~~java
package demo;

public interface OrderService {
    String place(String code);

    String placeTwice(String code);
}
~~~

The client will retrieve and use the bean by **OrderService**, the interface that a JDK proxy can implement. The second method is solely used to illustrate the case where a service calls another method on itself.

### 4.2. Implementing the Business Bean

**src/main/java/demo/OrderServiceImpl.java**

~~~java
package demo;

import org.springframework.stereotype.Service;

@Service
public class OrderServiceImpl implements OrderService {

    @Override
    public String place(String code) {
        System.out.println("SERVICE place(" + code + ")");
        return "saved:" + code;
    }

    @Override
    public String placeTwice(String code) {
        String first = this.place(code + "-1");
        String second = this.place(code + "-2");
        return first + "|" + second;
    }
}
~~~

**@Service** makes the class a candidate for component scanning to register into ApplicationContext. **place(...)** holds simple business logic; it needs no awareness of the aspect. Inside **placeTwice(...)**, both **this.place(...)** calls go directly to the target's method. That is intentional in the example: when the client calls **placeTwice(...)** through the proxy, the internal calls do not automatically re-enter the proxy.

### 4.3. Creating a Spring Aspect Intercepting the Right Method

**src/main/java/demo/TraceAspect.java**

~~~java
package demo;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class TraceAspect {

    @Around("execution(* demo.OrderService.place(..))")
    public Object trace(ProceedingJoinPoint joinPoint) throws Throwable {
        System.out.println("AOP before place");
        try {
            Object result = joinPoint.proceed();
            System.out.println("AOP after place");
            return result;
        } catch (Throwable error) {
            System.out.println("AOP error place: "
                    + error.getClass().getSimpleName());
            throw error;
        }
    }
}
~~~

Parts to understand in the Spring context:

- **@Aspect** marks this as a class declaring advice and pointcuts for Spring AOP to process. It **does not by itself make the class a Spring bean**; here **@Component** does that.
- **@Around(...)** instructs Spring to wrap logic around calls matching the expression.
- **execution(* demo.OrderService.place(..))** selects only executions of the **place** method on the **OrderService** contract, with any return type and matching parameter count. Since the bean implements this interface, Spring can apply the advisor to calls through the proxy.
- **joinPoint.proceed()** forwards the call to the next step in the interceptor chain and ultimately to the target. Omitting it means the **place(...)** business logic will not run; calling it multiple times can run the business logic multiple times.
- When the target succeeds, the advice returns the exact value received from **proceed()**. When the target throws an error, the example logs the error type name and **rethrows the original error** to preserve service behavior.
- The current expression **does not** select the **placeTwice(...)** method.

In real applications, log via a logging framework, apply masking policies for sensitive data, and avoid logging excessive payloads in advice. **System.out.println** only gives the example easily verifiable output.

### 4.4. Enabling AOP and Registering Beans

**src/main/java/demo/AppConfig.java**

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

- **@Configuration** declares configuration for the container.
- **@ComponentScan(basePackages = "demo")** discovers **OrderServiceImpl** and **TraceAspect**.
- **@EnableAspectJAutoProxy** registers the auto-proxy infrastructure used to match Spring beans against corresponding advisors. With an interface in this example, plain Spring Framework's default configuration uses a JDK dynamic proxy.
- AOP infrastructure is enabled within the active **ApplicationContext**. Creating another context without corresponding configuration cannot be assumed to produce the same proxies as this context.

### 4.5. Running and Observing from ApplicationContext

**src/main/java/demo/App.java**

~~~java
package demo;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class App {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            OrderService service = context.getBean(OrderService.class);
            System.out.println("IS_PROXY " + AopUtils.isAopProxy(service));

            System.out.println("RESULT " + service.place("A-01"));
            System.out.println(
                    "INTERNAL_RESULT " + service.placeTwice("B-02"));
        }
    }
}
~~~

The key point is **context.getBean(OrderService.class)**. Replacing it with **new OrderServiceImpl()** means the client holds a self-created target not wrapped by Spring in a proxy, so Spring AOP does not intercept those calls.

## 5. Running the Program and Reading Output

In the directory containing **pom.xml**, run:

~~~bash
mvn -q clean compile exec:java
~~~

Expected standard logical output (excluding Maven- or environment-specific messages):

~~~text
IS_PROXY true
AOP before place
SERVICE place(A-01)
AOP after place
RESULT saved:A-01
SERVICE place(B-02-1)
SERVICE place(B-02-2)
INTERNAL_RESULT saved:B-02-1|saved:B-02-2
~~~

Step-by-step explanation:

1. **IS_PROXY true**: Spring returns an AOP proxy object, instead of the client directly holding the plain target.
2. **service.place("A-01")**: this is a client call entering the proxy; advice prints **AOP before place**.
3. **proceed()**: the target executes business logic, prints **SERVICE place(A-01)**, and returns **saved:A-01**.
4. After the target succeeds, advice prints **AOP after place** and returns the result to the client; the client prints **RESULT saved:A-01**.
5. **service.placeTwice("B-02")**: the external call still routes through the proxy to the target, but the pointcut expression does not select **placeTwice(...)** itself.
6. From inside the target, **this.place(...)** is called twice; those calls **do not go through the proxy**, so only two **SERVICE place(...)** lines appear without **AOP before/after** lines.

Thus, a method being in a class annotated with **@Service** does not mean every call to that method is automatically intercepted. The deciding conditions in the example are: **the call goes through a Spring AOP proxy** and **the method matches an advisor/pointcut**.

## 6. Analyzing the Proxy Lifecycle in Spring

### 6.1. When Building ApplicationContext

When executing **new AnnotationConfigApplicationContext(AppConfig.class)**, Spring reads configuration, scans components, creates the relevant beans, and applies the auto-proxy infrastructure. **TraceAspect** is a Spring bean carrying the **@Aspect** declaration; Spring reads the advice declarations and determines which beans/methods may match. **OrderServiceImpl** qualifies, so the bean is exposed to clients via a proxy.

Simplified illustration:

~~~text
AppConfig
  ├─ @ComponentScan ──> OrderServiceImpl (@Service)
  ├─ @ComponentScan ──> TraceAspect (@Aspect, @Component)
  └─ @EnableAspectJAutoProxy
           │
           └─ Auto-proxy infrastructure
                      │
             OrderService bean exposed as proxy
~~~

The target object still holds the **place(...)** business logic. The proxy is responsible for forwarding calls through the interceptor chain built by Spring. For this example, the chain contains the **trace(...)** advice.

### 6.2. When the Client Calls a Method

The conditions for applying advice can be viewed via three questions:

| Question | In the Example | Consequence |
| --- | --- | --- |
| Does the object come from an AOP-enabled ApplicationContext? | Yes, via **context.getBean(...)** | Can receive a proxy |
| Is there an advisor matching the called method? | Yes, for **place(...)** | Advice is selected |
| Does the call pass through the proxy? | Yes for calls from **App**; no for **this.place(...)** | Only external calls to **place(...)** are intercepted |

Here Spring AOP uses a pointcut targeting **bean method execution calls**. Do not generalize that proxies automatically intercept constructors, field accesses, or all Java code inside methods.

### 6.3. JDK Proxy and CGLIB in This Example

**OrderServiceImpl** implements **OrderService**, so with the plain Spring Framework configuration above, Spring can create a **JDK dynamic proxy** implementing that interface. Therefore, retrieve the bean by **OrderService.class**. Do not default to retrieving by **OrderServiceImpl.class** in JDK proxy mode: the proxy type is not an instance of the implementation class.

If a service does not implement an interface, Spring AOP can create a class-based proxy using **CGLIB**. You can also request a class-based proxy with **@EnableAspectJAutoProxy(proxyTargetClass = true)**. In that case, inheritance constraints must be noted: **final** classes cannot be subclassed and **final/private** methods cannot be advised via typical subclass proxying. With Spring Boot applications, the default proxy type may be influenced by Boot configuration, so do not mechanically apply the default assumption of the plain Framework example.

## 7. Three Experiments for Self-Verification

### Experiment A: Calling a Self-Created Object

In **App.java**, right after calling the bean from context, add:

~~~java
OrderService direct = new OrderServiceImpl();
System.out.println("DIRECT_RESULT " + direct.place("C-03"));
~~~

Isolated output for this call:

~~~text
SERVICE place(C-03)
DIRECT_RESULT saved:C-03
~~~

There is no **AOP before/after** because **direct** does not go through a Spring proxy. Having **@Service** on **OrderServiceImpl** does not turn every instance created with **new** into a Spring bean.

### Experiment B: Letting the Proxy Intercept placeTwice as Well

In **TraceAspect.java**, change only the pointcut expression:

~~~java
@Around("execution(* demo.OrderService.*(..))")
~~~

When calling **service.placeTwice("B-02")**, the advice now runs **once for the external call into placeTwice(...)**. The two **this.place(...)** calls inside the target still have no separate advice wrap. The log strings in the example intentionally say **place**, so if running this experiment, change the log message to the dynamic method name (for example **joinPoint.getSignature().getName()**) to avoid confusion.

### Experiment C: Disabling Spring AOP in the Context

Remove **@EnableAspectJAutoProxy** from **AppConfig** in this plain Spring Framework application. Re-run: **AopUtils.isAopProxy(service)** becomes **false** and there are no **TraceAspect** logs. Keeping the **@Aspect** annotation on the class is not enough: aspect-processing infrastructure and aspect bean registration in the context are required.

These experiments should be run **one experiment at a time**, reverting changes before trying the next scenario.

## 8. Common Errors and How to Check

| Symptom | Possible Cause in Spring | How to Check or Fix |
| --- | --- | --- |
| Advice does not appear to run | **@EnableAspectJAutoProxy** not enabled in current context | Verify **AppConfig** is actually loaded |
| Aspect is not detected | Only **@Aspect** without bean registration | Add **@Component** or register via **@Bean** |
| Service not found | Component scan does not cover package **demo** | Verify **@ComponentScan** and **@Service** |
| Retrieving bean by implementation class fails | Bean exposed via JDK proxy implementing interface | Inject/retrieve by **OrderService** |
| Advice runs on external calls but is missing on internal calls | **this.place(...)** bypasses the proxy | Move the flow needing advice to another Spring bean and call through the injected bean |
| Advice runs unexpectedly or not at all on a method | **execution(...)** expression is too broad or too narrow | Check types, method names, packages, and proxied objects |
| Before log appears but after log is missing | Target threw an exception or **proceed()** did not complete | Preserve the exception; use **finally** if end logging is wanted even on error |
| Startup errors related to AspectJ annotations/pointcuts | Classpath missing AspectJ dependency needed for annotation types/parsing | Check **aspectjweaver** alongside Spring dependencies |

When multiple aspects exist, advice order can change the log sequence. Spring provides **@Order** to specify precedence; do not infer order merely from class locations in the project.

## 9. Applying the Design to Real Services

The logging example here is tiny, but the implementation principles matter more than the code size:

- Place business logic in Spring beans and obtain dependencies via injection from the container. Objects created directly with **new** do not automatically participate in Spring AOP.
- Write sufficiently narrow pointcuts, such as a specific service package or a business annotation, to avoid inadvertently intercepting unintended methods.
- When using **@Around**, call **proceed()** intentionally; preserve the return value and exceptions if you only want to observe. Have advice modify results only when that is genuinely a design requirement.
- Avoid relying on **self-injection** or **AopContext.currentProxy()**. If an internally called operation must be intercepted, the more maintainable solution is to extract that operation into another bean and call it through a Spring-injected dependency.
- In systems using **@Transactional**, **@Async**, or advices from multiple libraries, proxy traversal and self-invocation rules also need checking; each mechanism has additional specific conditions, so verify against the actual configuration.
- Check with both **AopUtils.isAopProxy(...)** and behavioral traces. Having a proxy does not guarantee every method matches the pointcut.

## 10. Self-Assessment Questions

**1. Why does calling the service via context.getBean(...) produce advice logs, while new OrderServiceImpl() does not?**

Because Spring creates and exposes a proxy in an AOP-enabled ApplicationContext. An instance created directly by the application does not go through that process.

**2. Why does placeTwice(...) call this.place(...) without advice logs?**

Because a call from the target itself to one of its own methods is a direct Java call and does not pass through Spring's proxy.

**3. Is @Aspect alone enough for Spring to scan and activate an aspect?**

No. **@Aspect** declares the AOP role; the class must still be registered as a Spring bean (here via **@Component**), and the context must enable @AspectJ processing support.

**4. If we change the pointcut to execution(* demo.OrderService.*(..)), what changes?**

External calls through the proxy to both **place(...)** and **placeTwice(...)** will match. Internal **this.place(...)** calls from inside **placeTwice(...)** still bypass the proxy.

**5. In an interface-based proxy example, why should we retrieve the bean by OrderService.class?**

Because a JDK dynamic proxy implements the **OrderService** interface; it does not necessarily have the runtime type **OrderServiceImpl**.

## 11. Reference Documentation

- Spring Framework Reference — Spring AOP: https://docs.spring.io/spring-framework/reference/core/aop.html
- Spring Framework Reference — @AspectJ support: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html
- Spring Framework Reference — Proxying mechanisms and self-invocation: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html

Key takeaway from the experiment: **Spring AOP intercepts service bean calls through a proxy managed by ApplicationContext, with matching advisors; direct calls on the target or internal calls via this do not automatically run the same advice.**