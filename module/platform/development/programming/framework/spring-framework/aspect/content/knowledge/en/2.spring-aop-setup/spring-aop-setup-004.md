# Role of @Configuration, Component Scan, and Bean Registration When Setting Up Spring AOP

## 1. Lesson goal

In Spring Framework, writing a class with **@Aspect** only declares the interception logic. For advice to actually run when the application calls a service method, the **ApplicationContext** must know about both the **service bean** and the **aspect bean**, and must have the **Spring AOP proxy creation infrastructure**. This lesson focuses on three configuration actions that connect those pieces:

1. Use **@Configuration** to supply Java configuration to the container and place **@EnableAspectJAutoProxy**.
2. Use **@ComponentScan** to automatically discover Spring component classes such as **@Service** and **@Component**.
3. Use **@Bean** to explicitly register the service, aspect, and client when you do not want to use component scanning.

Target outcome: explain **why a correctly written aspect still does not run if it has not been registered as a bean**, distinguish **putting a bean into the context** from **whether the bean is wrapped in a proxy**, and know how to inspect the actual bean a client receives from Spring.

**Scope:** Examples use **proxy-based Spring AOP inside an ApplicationContext**; we do not go deep into general AOP theory, AspectJ compile-time/load-time weaving, or other AOP frameworks. The term **@AspectJ** in Spring documentation refers to the annotation-based aspect declaration style; Spring still creates proxies using Spring AOP's mechanism.

## 2. Configuration big picture: three necessary conditions

Imagine an application has **PaymentService** and wants to record a trace before processing payment. Three conditions cannot substitute for one another:

| Component | Role in Spring | If missing |
| --- | --- | --- |
| **ApplicationContext configuration** | Loads the configuration class, activates **@AspectJ** support with **@EnableAspectJAutoProxy** | The aspect may be a bean, but there is no infrastructure to automatically create proxies for its advice |
| **PaymentService registration** | Creates the target bean that clients can retrieve/inject from the container | There is no Spring-managed service for Spring to pass through auto-proxying |
| **AuditAspect registration** | Tells Spring about the bean containing **@Aspect** and advice | The AOP infrastructure cannot find the aspect to build the corresponding advisors |

A registered service is **not automatically always a proxy**. Spring evaluates which advisors apply to the bean and may return a proxy if the bean qualifies. For a call to a matching method, the execution flow is:

~~~text
ApplicationContext
  |
  +-- PaymentServiceImpl (@Service) --------------------+
  |                                                    |
  +-- AuditAspect (@Aspect + @Component) -- advice -----+-- Spring auto-proxy creator
  |                                                            |
  +-- PaymentClient (@Component)                                |
          |                                                     |
          +-- inject PaymentService <--- proxy <----------------+
                                             |
PaymentClient.checkout() --> proxy --> advice --> PaymentServiceImpl.pay()
~~~

The annotations **@Service** and **@Component** handle bean discovery/registration; **@Aspect** handles aspect declaration; **@EnableAspectJAutoProxy** activates the Spring mechanism that reads those declarations and builds proxies. These are distinct responsibilities.

## 3. Plain Spring Framework hands-on project

We use **Java 17+**, **Maven 3.9+**, and **Spring Framework 6.2.12**. No Spring Boot, HTTP server, or database is required. The example is structured so all classes compile together.

~~~text
spring-aop-config-demo/
├── pom.xml
└── src/main/java/example/
    ├── App.java
    ├── AppConfig.java
    ├── PaymentService.java
    ├── PaymentServiceImpl.java
    ├── AuditAspect.java
    └── PaymentClient.java
~~~

**pom.xml**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-aop-config-demo</artifactId>
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
                    <mainClass>example.App</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**spring-context** provides the annotation-configured container and pulls in the needed Spring modules, including **spring-aop**. **aspectjweaver** must be on the classpath for Spring to process **@AspectJ**-style annotations and pointcut expressions. This **does not mean** the example uses AspectJ weaving: calls are still intercepted by Spring AOP through proxies.

### 3.1. Defining the service contract

**src/main/java/example/PaymentService.java**

~~~java
package example;

public interface PaymentService {
    String pay(String orderId);
}
~~~

### 3.2. Declaring the service with @Service

**src/main/java/example/PaymentServiceImpl.java**

~~~java
package example;

import org.springframework.stereotype.Service;

@Service
public class PaymentServiceImpl implements PaymentService {

    @Override
    public String pay(String orderId) {
        System.out.println("SERVICE pay " + orderId);
        return "ok:" + orderId;
    }
}
~~~

**@Service** is a Spring stereotype annotation and a specialization of **@Component**. When the package containing the class is scanned, the container registers a **bean definition** for **PaymentServiceImpl**. Under default naming rules, the bean is named **paymentServiceImpl**.

Note: the JVM does not automatically create a Spring bean just because a class carries **@Service**. There must be a mechanism registering it into the container: component scan, a **@Bean** method, or registration via context APIs.

### 3.3. Declaring the aspect as a Spring bean

**src/main/java/example/AuditAspect.java**

~~~java
package example;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class AuditAspect {

    @Before("execution(* example.PaymentServiceImpl.pay(..))")
    public void beforePay(JoinPoint joinPoint) {
        Object orderId = joinPoint.getArgs()[0];
        System.out.println("ASPECT before " + orderId);
    }
}
~~~

The two annotations have independent roles:

- **@Aspect**: Spring recognizes the class as defining advice and method-selection expressions; here **@Before** applies to **PaymentServiceImpl.pay(...)**.
- **@Component**: places **AuditAspect** in the candidate list for component scanning, creating the **auditAspect** bean in the context.

If only **@Aspect** remains and **@Component** is removed, a standard component scanner does not treat the class as a component automatically. In that case **@EnableAspectJAutoProxy** may still be enabled, yet this aspect is not registered and does not participate in interception.

An aspect must be **registered as a Spring bean**: you can use **@Component** or a **@Bean** method. There is no need to put **@Service** on an aspect class. Moreover, a bean annotated with **@Aspect** is not itself a target that Spring AOP uses for advising by other aspects.

### 3.4. Creating a client that receives the service from the container

**src/main/java/example/PaymentClient.java**

~~~java
package example;

import org.springframework.stereotype.Component;

@Component
public class PaymentClient {

    private final PaymentService paymentService;

    public PaymentClient(PaymentService paymentService) {
        this.paymentService = paymentService;
    }

    public void checkout(String orderId) {
        String result = paymentService.pay(orderId);
        System.out.println("CLIENT result " + result);
    }
}
~~~

Because the class has a single constructor, Spring can perform constructor injection without writing **@Autowired**. Spring looks up **PaymentService** by type in the context; in this example there is only one matching bean.

From **PaymentClient**'s perspective, the dependency is **PaymentService**. If the bean qualifies for Spring to create an AOP proxy, that proxy itself is injected into the client. Writing **new PaymentServiceImpl()** directly in the client's constructor bypasses Spring's registration and proxying process.

### 3.5. Role of @Configuration, @ComponentScan, and @EnableAspectJAutoProxy

**src/main/java/example/AppConfig.java**

~~~java
package example;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackages = "example")
@EnableAspectJAutoProxy
public class AppConfig {
}
~~~

Reading line by line:

**@Configuration** marks the class as a Java configuration source for Spring. In the example, **AppConfig** is passed directly to **AnnotationConfigApplicationContext**. A configuration class can contain **@Bean** methods, import configurations via **@Import**, or declare scanning and container feature enablement. **@Configuration** alone does not automatically turn every class in the same package into a bean.

**@ComponentScan(basePackages = "example")** tells Spring to search for matching components under the **example** package and its subpackages. Through this, Spring discovers **PaymentServiceImpl** via **@Service**, and **AuditAspect** and **PaymentClient** via **@Component**. If a component lives in a package outside the scan range and is not registered another way, it is not in the context.

**@EnableAspectJAutoProxy** registers the Spring AOP infrastructure that automatically inspects beans and advisors declared via **@AspectJ**, creating proxies when needed. This annotation **does not replace component scan** and **does not automatically create an AuditAspect bean from an unregistered class**.

This is **plain Spring Framework**, so AOP is enabled explicitly with the annotation above. In a Spring Boot project with the appropriate starter and auto-configuration, proxy enablement can be provided automatically; check the Boot configuration rather than assuming plain Spring and Boot examples are identical.

### 3.6. Creating the ApplicationContext, checking beans, and calling the service

**src/main/java/example/App.java**

~~~java
package example;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class App {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            System.out.println(
                    "HAS_SERVICE " + context.containsBean("paymentServiceImpl"));
            System.out.println(
                    "HAS_ASPECT " + context.containsBean("auditAspect"));

            PaymentService service = context.getBean(PaymentService.class);
            System.out.println("IS_PROXY " + AopUtils.isAopProxy(service));

            PaymentClient client = context.getBean(PaymentClient.class);
            client.checkout("ORD-7");
        }
    }
}
~~~

Run from the directory containing **pom.xml**:

~~~bash
mvn -q clean compile exec:java
~~~

Expected logical output, ignoring Maven and runtime environment messages:

~~~text
HAS_SERVICE true
HAS_ASPECT true
IS_PROXY true
ASPECT before ORD-7
SERVICE pay ORD-7
CLIENT result ok:ORD-7
~~~

Meaning of the first three lines:

- **HAS_SERVICE true**: component scanning registered the service under its default name.
- **HAS_ASPECT true**: the aspect was also registered as a bean; having **@Aspect** alone would not guarantee this.
- **IS_PROXY true**: the **PaymentService** object returned by the context has been wrapped in a Spring AOP proxy. Having a bean does not equate to having a proxy; the example qualifies because there is advice matching **pay(...)**.

The remaining three lines show the client calling through the proxy, the **@Before** advice running before the target method, and the service returning the result as normal.

## 4. Why don't component scanning and @Configuration automatically enable AOP?

Three cases are very easy to confuse:

| Actual configuration | Is service a bean? | Is aspect a bean? | Does AuditAspect advice run? |
| --- | --- | --- | --- |
| **@ComponentScan** without **@EnableAspectJAutoProxy** | Yes | Yes | No, in this plain Spring Framework example |
| **@EnableAspectJAutoProxy** without scanning or declaring any beans | No | No | No |
| **@Configuration + @ComponentScan + @EnableAspectJAutoProxy** as in the example | Yes | Yes | Yes, for calls matching the pointcut that go through the proxy |
| **@Configuration + @Bean** declaring both service and aspect, plus AOP enabled | Yes | Yes | Yes, if an advisor matches |

**@Configuration** only tells Spring that the class is a source of bean definitions and configuration. **@ComponentScan** only registers components matching the scan range and filters. **@EnableAspectJAutoProxy** is what wires the advice/proxy infrastructure into the Spring container. None of these three annotations can replace the entire job of the other two.

Another detail: **@Configuration** is treated as a component when a scanner scans it, but in the main example we pass **AppConfig.class** directly to the context. Thus loading the main configuration class does not depend on a scanner happening to find it.

## 5. Alternative: registering all beans with @Bean

Component scan is convenient when project-owned classes have stereotype annotations. For classes you cannot modify, when you want explicit bean names, or when beans must be built via constructors/factories, you can use **@Bean**.

**Independent experiment:** replace the **entire contents** of **src/main/java/example/AppConfig.java** with the following version instead of adding a new **@Configuration** class inside the scanned package. That avoids accidentally registering duplicate services and aspects.

~~~java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy
public class AppConfig {

    @Bean
    public PaymentService paymentService() {
        return new PaymentServiceImpl();
    }

    @Bean
    public AuditAspect auditAspect() {
        return new AuditAspect();
    }

    @Bean
    public PaymentClient paymentClient(PaymentService paymentService) {
        return new PaymentClient(paymentService);
    }
}
~~~

There is no **@ComponentScan** anymore. **PaymentServiceImpl**, **AuditAspect**, and **PaymentClient** still keep their old annotations in the Java files, yet they are only registered in the container because of the **@Bean** methods.

Points to notice:

1. **@Bean public PaymentService paymentService()** registers the bean under the default name **paymentService**, not **paymentServiceImpl**. Spring manages the object returned by the factory method and can still wrap it in an AOP proxy.
2. **@Bean public AuditAspect auditAspect()** registers the instance containing **@Aspect** declarations. It is not mandatory for **AuditAspect** to have **@Component** when registering via **@Bean**.
3. **paymentClient(PaymentService paymentService)** lets Spring resolve the parameter via dependency injection. The client receives the **PaymentService** bean processed by the container, without calling the factory method manually.
4. **@EnableAspectJAutoProxy** must still be present in plain Spring Framework configuration. **@Bean** only registers objects; it does not enable AOP automatically.
5. Calling **new PaymentServiceImpl()** inside **paymentService()** is valid because **new** occurs **inside a @Bean factory method** and the returned object is managed by the container. Conversely, calling **new PaymentServiceImpl()** in client code and using it directly will not be proxied by Spring.

To run **App.java** again, change the bean-name check line from:

~~~java
context.containsBean("paymentServiceImpl")
~~~

to:

~~~java
context.containsBean("paymentService")
~~~

Re-run the Maven command from section 3.6; the logical output lines remain the same, including **IS_PROXY true**, **ASPECT before ORD-7**, and **SERVICE pay ORD-7**. If the old name check is left unchanged, **HAS_SERVICE** will be **false** even though the service is genuinely registered under **paymentService**. Therefore, distinguish **checking the exact bean name** from **concluding whether a bean exists by type**.

Restore **AppConfig.java** from section 3.5 when returning to the original component scan version. Avoid keeping both registration paths for the same service/aspect simultaneously unless intentionally managing multiple beans.

## 6. At what stage does Spring create proxies?

In the example, the configuration flow can be broken down into steps for diagnosis:

~~~text
new AnnotationConfigApplicationContext(AppConfig.class)
          |
          v
Read AppConfig and configuration annotations
          |
          +-- @ComponentScan -> bean definitions:
          |      paymentServiceImpl, auditAspect, paymentClient
          |
          +-- @EnableAspectJAutoProxy
          |      -> register auto-proxy creator infrastructure
          |
          v
Create and initialize required beans
          |
          +-- find aspect beans, read @Before and pointcuts
          +-- determine advisors applicable to PaymentServiceImpl
          +-- process bean via AOP BeanPostProcessor
          |
          v
Expose PaymentService via proxy to dependencies/clients
          |
          v
PaymentClient.checkout() -> PaymentService proxy
          -> AuditAspect.beforePay() -> PaymentServiceImpl.pay()
~~~

The diagram illustrates responsibility relationships, not every single callback or a fixed initialization order for all beans. The foundation of auto-proxying consists of Spring's **BeanPostProcessor** components; they can replace the exposed bean object with a proxy after the bean goes through appropriate initialization.

Two practical conclusions follow:

- **Bean definition** means Spring knows how to create/manage the bean. It is not enough to infer that clients receive a proxy.
- **AOP proxy** is the intermediary object Spring can give to clients if a matching advisor exists and AOP infrastructure is active. Advisors determine whether calls to a method go through advice.

In this example, because **PaymentServiceImpl** implements **PaymentService**, the default plain Spring Framework configuration can use an interface-based **JDK dynamic proxy**. Clients should inject by **PaymentService**, as shown above. To force a class-based proxy, you can use **@EnableAspectJAutoProxy(proxyTargetClass = true)**; that changes the proxy type, not bean registration. Other proxy configurations in the same context or Spring Boot settings can also affect the actual proxy type.

## 7. Distinguishing @Configuration enhancement from Spring AOP proxy

One source of confusion is that **@Configuration** also has proxy/subclass-related behavior. In the default full configuration **@Configuration(proxyBeanMethods = true)**, Spring can enhance the configuration class with CGLIB so calls between **@Bean** methods obey container singleton semantics. This is a **bean configuration support mechanism**, distinct from the AOP proxy used to intercept **PaymentService.pay(...)**.

Example of two factory methods:

~~~java
@Configuration
public class ExtraConfig {
    @Bean
    public SharedStore sharedStore() {
        return new SharedStore();
    }

    @Bean
    public ReportService reportService() {
        return new ReportService(sharedStore());
    }
}
~~~

This is **illustrative code**, assuming corresponding **SharedStore** and **ReportService** classes already exist; it is not a required file for the runnable project above. With default **@Configuration**, Spring ensures bean references across configuration methods remain consistent with managed beans. If switched to **@Configuration(proxyBeanMethods = false)**, directly calling **sharedStore()** from another method can create a new Java instance outside container bean-lookup semantics. In that case, use dependency injection parameters:

~~~java
@Bean
public ReportService reportService(SharedStore sharedStore) {
    return new ReportService(sharedStore);
}
~~~

These two code snippets clarify **@Configuration and @Bean**; they do not change the pointcut or AOP behavior of **PaymentService** in the main example. Do not infer that because **AppConfig** has CGLIB enhancement, the service is guaranteed to get a Spring AOP proxy.

## 8. Diagnosing with small experiments

### 8.1. Aspect has @Aspect but is not registered

In the **component scan** version from section 3.5, remove **@Component** from **AuditAspect** while keeping **@Aspect**. Then create a fresh ApplicationContext by re-running the application. Expected:

~~~text
HAS_SERVICE true
HAS_ASPECT false
IS_PROXY false
SERVICE pay ORD-7
CLIENT result ok:ORD-7
~~~

This result applies to the example with no other advisors. If a real application has other advisors, the bean may still be a proxy even though **AuditAspect** is currently unregistered.

Fix: restore **@Component**, or register the aspect bean via **@Bean** as in section 5; also verify the scan package.

### 8.2. Aspect is scanned but AOP is not enabled

In the component scan version, remove **@EnableAspectJAutoProxy** from **AppConfig**, keeping **@ComponentScan** and **@Component** on the aspect. When re-run:

~~~text
HAS_SERVICE true
HAS_ASPECT true
IS_PROXY false
SERVICE pay ORD-7
CLIENT result ok:ORD-7
~~~

In plain Spring Framework here, lacking AOP infrastructure means advice is not installed onto a proxy; **@Aspect** by itself does not make advice run.

### 8.3. Service lies outside the scan scope

If **PaymentServiceImpl** is moved to another package while keeping **@ComponentScan(basePackages = "example")** and not registering it another way, the **PaymentService** bean is not discovered. When Spring creates **PaymentClient**, the **PaymentService** dependency cannot be resolved; the context usually fails on startup rather than reaching the **HAS_SERVICE** line. Expand the scan range appropriately or declare the service with **@Bean**.

Do not widen the scan indiscriminately across an entire large application just to fix one missing class; inspect actual packages and module structure first.

### 8.4. Instantiating the service outside ApplicationContext

Instead of calling the Spring bean, external code constructs its own instance:

~~~java
PaymentService direct = new PaymentServiceImpl();
System.out.println("DIRECT " + direct.pay("ORD-8"));
~~~

Output of this addition:

~~~text
SERVICE pay ORD-8
DIRECT ok:ORD-8
~~~

There is no **ASPECT before** log because the **direct** instance is not a bean processed by Spring. Contrast this with calling **context.getBean(PaymentService.class)** or injecting into **PaymentClient**.

### 8.5. Client obtains the service properly, yet an internal call bypasses the proxy

If a method inside **PaymentServiceImpl** calls **this.pay(...)** on itself, that internal call does not pass back through Spring's proxy. This is a limitation of proxy-based Spring AOP, not a component scanning error or missing bean registration.

If advice is required for the internal operation, a controllable design is to extract that operation into another Spring bean and inject/call it via a container dependency.

## 9. Common configuration errors

| Symptom | Common cause | How to verify |
| --- | --- | --- |
| Aspect does not run even though class has **@Aspect** | Aspect bean not created or **@EnableAspectJAutoProxy** missing | Check **containsBean**, context configuration, and AspectJ dependency |
| Cannot inject service | Package not scanned, **@Service** missing, or **@Bean** missing | Check packages, bean names, and bean definitions |
| **NoUniqueBeanDefinitionException** | Multiple beans satisfy the requested injection type | Identify the intended bean, use **@Qualifier** or **@Primary** where appropriate |
| Looking up bean by implementation class fails | JDK proxy only implements the service interface | Inject/look up bean by **PaymentService** |
| Aspect has a bean but method is not intercepted | Pointcut does not match or call bypasses proxy | Match package/class/method names; observe the call path |
| Proxy exists but expected aspect log is absent | Proxy may have been created by a different advisor | Check the exact aspect bean and pointcut, not only **AopUtils.isAopProxy** |
| Code runs from **new** without advice | Instance was not created and exposed through the Spring container | Retrieve/inject the bean from the context |
| Duplicate service or aspect registered | Both scan and **@Bean** declared for the same logic | Choose one registration path or manage multiple beans explicitly |
| Multiple ApplicationContexts used; advice runs in only one | AOP configuration is tied to the context holding the related beans | Determine which context owns the config and the service |
| Error while parsing **@Aspect**/pointcut | Missing **aspectjweaver** or incompatible dependencies | Check Maven dependency tree and running Spring version |

For applications using multiple advices, pay attention to precedence and application order; **@Order** can be used when ordering is a specific requirement. That is advice configuration after bean registration and proxy creation are properly solved.

## 10. Self-check questions

**Q1. With @Configuration and @ComponentScan present, why doesn't @Before run?**

Because these two annotations let Spring load configuration and register components, yet in a plain Spring Framework example **@EnableAspectJAutoProxy** is also needed to process **@Aspect** and create proxies for advisors.

**Q2. If AuditAspect only has @Aspect, will component scan automatically detect it as a bean?**

No. It must also have **@Component** (or a scannable Spring stereotype) or use explicit registration such as **@Bean**.

**Q3. Must every Spring AOP aspect be registered via component scan?**

No. A **@Bean** method returning **AuditAspect** also gives the container an aspect bean for the AOP infrastructure to use.

**Q4. Why is `new PaymentServiceImpl()` allowed inside `@Bean`, while `new` in client code bypasses AOP?**

**@Bean** hands the instance to the container to manage, and the container can pass that instance through the auto-proxy step before exposing the bean to clients. An instance created directly with `new` in client code does not go through that pipeline.

**Q5. What is the difference between a bean and a proxy in the example?**

A bean is an object managed by Spring; a proxy is an intermediary object Spring can expose to clients to apply advice. Being registered as a bean does not guarantee that every method on it is advised.

**Q6. Why is the bean named `paymentService` in the `@Bean` config, whereas in component scan it is `paymentServiceImpl`?**

By default, a bean from **@Bean** takes its name from the factory method; a bean from component scan normally derives its name from the class name according to Spring's naming rules. Different names do not necessarily mean different service types.

**Q7. What evidence is sufficient for a successful setup?**

You should observe at least: the service bean is in the context, the aspect bean is in the context, the service returned by the context is an AOP proxy when applicable, and **@Before** actually runs during a service call through a Spring dependency.

## 11. Checklist for applying to a Spring AOP module

1. Identify which **ApplicationContext** holds the service bean to be intercepted.
2. Choose an appropriate registration path: **@Service + @ComponentScan** or **@Bean**.
3. Ensure the **@Aspect** class is also registered as a bean, not just annotated.
4. Enable auto-proxy support in the corresponding context (**@EnableAspectJAutoProxy** in plain Framework examples).
5. Verify the pointcut expression matches the target method.
6. Inject the service from the container by interface when using JDK proxies.
7. Verify behavior with an actual call; confirm boundaries such as self-invocation.

## 12. Spring reference documentation

- Spring Framework Reference — Java-based Container Configuration: https://docs.spring.io/spring-framework/reference/core/beans/java.html
- Spring Framework Reference — @Bean: https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html
- Spring Framework Reference — @Configuration: https://docs.spring.io/spring-framework/reference/core/beans/java/configuration-annotation.html
- Spring Framework Reference — @AspectJ support and enabling auto-proxy: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html
- Spring Framework Reference — Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html

**Technical conclusion:** in Spring AOP, **@Configuration** loads configuration, **@ComponentScan/@Bean** make the service and aspect Spring-managed beans, and **@EnableAspectJAutoProxy** allows Spring to create proxies and apply advice according to pointcuts. Combining all three responsibilities is what makes the service-call interception example work.
