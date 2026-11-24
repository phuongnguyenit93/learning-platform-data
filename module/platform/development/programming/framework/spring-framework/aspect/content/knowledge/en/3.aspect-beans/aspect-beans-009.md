# The singleton, perthis, and pertarget Models Supported by Spring AOP

## 1. What Will You Learn in This Lesson?

In Spring AOP, an aspect is managed by Spring as a bean, yet **the number of aspect instances** can be determined by different models. The three important models to understand are:

- **singleton**: one aspect instance shared across multiple proxies/calls within the scope of the bean and ApplicationContext.
- **perthis**: one aspect instance associated with each matching **Spring AOP proxy** object.
- **pertarget**: one aspect instance associated with each matching **target** object behind the proxy.

These are **aspect instantiation models**—policies for associating and creating aspect instances in Spring AOP. They differ from bean scope concepts such as singleton, prototype, request, or session. Specifically, for perthis/pertarget, the aspect bean must be configured as **prototype** so Spring can create instances per proxy or target.

Practical objectives:

1. Write the right **@Aspect** annotation for each model.
2. Register the aspect bean and enable **@EnableAspectJAutoProxy**.
3. Observe the difference between a single counter and separate counters per advised object.
4. Clearly explain how Spring AOP distinguishes **this = proxy** from **target = the object wrapped by the proxy**.
5. Avoid the mistake of configuring a singleton bean for perthis/pertarget, as well as misconceptions regarding bean counts, call counts, and concurrent data.

**Scope:** Examines only the behavior of **Spring AOP with `@AspectJ` annotation style** inside an **ApplicationContext**. Does not reteach general AspectJ theory or switch to compiler/Java-agent weaving.

## 2. Why Does the Instantiation Model Matter?

Suppose there are two independent service beans:

~~~text
ApplicationContext
  |
  +-- first  --> Spring proxy P1 --> JobImpl target T1
  |
  +-- second --> Spring proxy P2 --> JobImpl target T2
  |
  +-- aspect definition (advice for Job.execute)
~~~

The client invokes in sequence:

~~~text
first.execute()
second.execute()
first.execute()
second.execute()
~~~

If the aspect has a **counter** field, the question is whether the counter is shared or separate?

| Model | Attaches aspect instance to | With P1→T1 and P2→T2 | Counter if every matching call runs advice |
| --- | --- | --- | --- |
| singleton | One shared aspect instance | 1 aspect instance | 1, 2, 3, 4 |
| perthis | Each proxy P1, P2 | 2 aspect instances | P1: 1→2; P2: 1→2 |
| pertarget | Each target T1, T2 | 2 aspect instances | T1: 1→2; T2: 1→2 |

**The table above only illustrates two proxies pointing to two distinct targets.** Therefore perthis and pertarget produce the same result in this situation. What differentiates the two models is the **proxy–target relationship**, especially when multiple proxies share one target.

Do not interpret perthis as “one instance per request”, pertarget as “one instance per call”, or prototype bean as “automatically recreated on every advice execution”. Those are three common misconceptions.

## 3. Default Model: singleton

Declaration:

~~~java
@Aspect
public class SingletonCounter {
    // Fields of this instance are shared
}
~~~

Spring AOP uses the **singleton aspect** model by default. When an aspect is declared as a default Spring bean via **@Component** or **@Bean**, there is normally one aspect instance in the context for that bean definition.

If the same aspect is used to advise multiple services, advice runs on the same aspect instance. This is useful for aspects that hold no per-object state, such as logging, metrics, policy validation, or tracing markers. However, storing per-invocation data in mutable fields of a singleton aspect can create race conditions when multiple threads call concurrently.

Distinguish two ideas:

- **Singleton aspect model**: one aspect instance for join points related to that aspect.
- **Singleton Spring bean scope**: the same bean name in one container normally always returns the same instance.

In typical configurations, the two concepts go together, yet they should not be treated as a single annotation. Spring can support the singleton aspect model even in cases where the bean definition is not declared singleton; in that case the Spring bean lifecycle and aspect lifecycle must be analyzed separately. The easiest setup to control for basic examples remains a singleton aspect bean.

## 4. The perthis Model: One Instance per Proxy

Declaration:

~~~java
@Aspect("perthis(execution(* demo.Job.execute(..)))")
public class PerThisCounter {
    // Each matching proxy has its own aspect state
}
~~~

In Spring AOP, **this** at a join point refers to the **proxy object** that the client invokes. **perthis(...)** associates an aspect instance with the proxy object matching the expression inside the perthis clause.

With the diagram:

~~~text
P1 (proxy) ---> T1 (target)  ---> aspect A1
P2 (proxy) ---> T2 (target)  ---> aspect A2
~~~

A1 and A2 can hold separate state. The associated instance is created when the corresponding object first participates in a join point matching the perthis clause; it does not need to be pre-created just because the ApplicationContext starts up. Before the aspect instance is created, advice belonging to that instance cannot run yet; once created, advice runs at matching join points of the associated object. Do not assume that every method on the same service will match the clause or that every Java call is intercepted by Spring AOP.

**Important Spring requirement:** The bean definition of **PerThisCounter** must be **prototype**, for example:

~~~java
@Bean
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public PerThisCounter perThisCounter() {
    return new PerThisCounter();
}
~~~

Using **@Aspect("perthis(...)")** on a default singleton **@Component** is a misconfiguration. Spring cannot supply a different aspect instance for each proxy if the aspect bean always returns a singleton; an error regarding an aspect instantiation model incompatible with a singleton bean may occur.

## 5. The pertarget Model: One Instance per Target

Declaration:

~~~java
@Aspect("pertarget(execution(* demo.Job.execute(..)))")
public class PerTargetCounter {
    // Each matching target has its own aspect state
}
~~~

Spring AOP wraps the **target** with a proxy. **pertarget(...)** associates an aspect instance with the corresponding target at matching join points. With one proxy per target, the aspect instance count looks the same as perthis. The difference becomes clear when two proxies P1 and P2 wrap the same object T:

~~~text
PERTHIS                         PERTARGET

P1 ------> T                    P1 ------> T
  |                               |        ^
  +---- aspect A1                 |        |
                                 +------ aspect A
P2 ------> T                      |        ^
  |                               |        |
  +---- aspect A2                 P2 ------> T

2 aspect instances                 1 aspect instance
if both P1/P2 match                for the same target T
~~~

This is a **conceptual model** to distinguish identity, not a standalone program manually creating two proxies. When Spring creates proxies, wrapper/advisor configurations can make target organization complex; do not deduce exact proxy/target counts from bean names alone.

Like perthis, a pertarget aspect bean must be **non-singleton**; in practice it should be declared **prototype**:

~~~java
@Bean
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public PerTargetCounter perTargetCounter() {
    return new PerTargetCounter();
}
~~~

**Prototype here is the mechanism supplying new aspect instances as requested by Spring AOP.** It does not mean Spring creates a new aspect on every `execute()` call. For the same already-associated target, subsequent matching calls continue using that target's aspect instance.

## 6. @Scope("prototype") and Per-Clauses Do Not Replace Each Other

This is a particularly important part when working with **Spring beans** and **Spring AOP**.

| Configuration | Meaning | Conclusion |
| --- | --- | --- |
| **@Aspect** with singleton bean | Default aspect model | One shared instance |
| **@Aspect("perthis(...)")** with prototype bean | Aspect instance bound per proxy | Matches the perthis model |
| **@Aspect("pertarget(...)")** with prototype bean | Aspect instance bound per target | Matches the pertarget model |
| **@Aspect("perthis(...)")** but singleton aspect bean | Per-clause needs multiple instances, bean has only one | Misconfiguration; Spring may report an error |
| **@Scope("prototype")** but only **@Aspect** without per-clause | Each prototype bean retrieval can create a new instance, but aspect model remains default singleton | Does not automatically create perthis/pertarget semantics |

Technical note: **@Scope** applies to the Spring bean definition, whereas **perthis/pertarget** resides in metadata describing the **aspect instantiation model**. Spring AOP checks both sides of the configuration to build an appropriate aspect instance factory.

If using **@Component** instead of **@Bean**, place the scope directly on the class:

~~~java
@Aspect("pertarget(execution(* demo.Job.execute(..)))")
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class PerTargetCounter {
    // ...
}
~~~

The snippet above is the **component scan approach**, not to be used simultaneously with registering the same aspect via **@Bean**. **@ComponentScan** covering the class's package and **@EnableAspectJAutoProxy** must be present in the relevant context.

## 7. Java 17+ Project to Observe All Three Models

The example uses **Spring Framework 6.2.12**, **Java 17+**, and **Maven 3.9+**. We create three **independent** ApplicationContexts, each registering **one kind of aspect** so logs are not mixed with advice from other models.

Structure:

~~~text
spring-aop-instantiation/
├── pom.xml
└── src/main/java/demo/
    ├── Job.java
    ├── JobImpl.java
    ├── SingletonCounter.java
    ├── PerThisCounter.java
    ├── PerTargetCounter.java
    └── App.java
~~~

### 7.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-instantiation</artifactId>
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

**spring-context** provides the Java-based ApplicationContext and pulls in Spring AOP. **aspectjweaver** provides the annotation/pointcut types that Spring uses to process the **@AspectJ** style. The example still uses **proxy-based Spring AOP**, not a weaving agent.

### 7.2. Service Interface and Target

**src/main/java/demo/Job.java**

~~~java
package demo;

public interface Job {
    void execute();
}
~~~

**src/main/java/demo/JobImpl.java**

~~~java
package demo;

public class JobImpl implements Job {

    private final String label;

    public JobImpl(String label) {
        this.label = label;
    }

    public String label() {
        return label;
    }

    @Override
    public void execute() {
        System.out.println("SERVICE " + label);
    }
}
~~~

Create two distinct instances **JobImpl("A")** and **JobImpl("B")** using two **@Bean** methods. The client only retrieves type **Job**, because with an interface and default configuration, plain Spring Framework can create a **JDK dynamic proxy**.

### 7.3. Singleton Aspect

**src/main/java/demo/SingletonCounter.java**

~~~java
package demo;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class SingletonCounter {

    private int calls;

    @Before("execution(* demo.Job.execute(..))")
    public void before(JoinPoint joinPoint) {
        calls++;
        String label = ((JobImpl) joinPoint.getTarget()).label();
        System.out.println("ASPECT singleton count=" + calls
                + " target=" + label);
    }
}
~~~

One instance is registered in the context. Every advice invocation **in that context** increments the same **calls** field. The `int` counter is intentionally simple because the program runs sequentially; it is not safe when multiple threads update it concurrently.

### 7.4. Perthis Aspect

**src/main/java/demo/PerThisCounter.java**

~~~java
package demo;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect("perthis(execution(* demo.Job.execute(..)))")
public class PerThisCounter {

    private int calls;

    @Before("execution(* demo.Job.execute(..))")
    public void before(JoinPoint joinPoint) {
        calls++;
        String label = ((JobImpl) joinPoint.getTarget()).label();
        System.out.println("ASPECT perthis count=" + calls
                + " target=" + label);
    }
}
~~~

The **perthis(...)** clause decides **when and with which proxy** an instance is associated. The **@Before(...)** advice is the logic that runs at matching join points after the instance is available to use. In the example, both refer to **Job.execute()** for easy verification.

Only use this class when the **PerThisCounter** bean definition is configured as prototype as in Section 7.6.

### 7.5. Pertarget Aspect

**src/main/java/demo/PerTargetCounter.java**

~~~java
package demo;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect("pertarget(execution(* demo.Job.execute(..)))")
public class PerTargetCounter {

    private int calls;

    @Before("execution(* demo.Job.execute(..))")
    public void before(JoinPoint joinPoint) {
        calls++;
        String label = ((JobImpl) joinPoint.getTarget()).label();
        System.out.println("ASPECT pertarget count=" + calls
                + " target=" + label);
    }
}
~~~

The line **joinPoint.getTarget()** retrieves the **target object** at invocation time. This is not the API deciding pertarget; the metadata of **@Aspect("pertarget(...)")** itself specifies the model. When a target instance continues to be called through a matching proxy, the state in the aspect associated with it is reused.

### 7.6. Three Separate Spring Configurations

**src/main/java/demo/App.java**

~~~java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Scope;
import org.springframework.beans.factory.config.ConfigurableBeanFactory;

public class App {

    @Configuration(proxyBeanMethods = false)
    static class ServiceBeans {

        @Bean("first")
        Job first() {
            return new JobImpl("A");
        }

        @Bean("second")
        Job second() {
            return new JobImpl("B");
        }
    }

    @Configuration(proxyBeanMethods = false)
    @Import(ServiceBeans.class)
    @EnableAspectJAutoProxy
    static class SingletonConfig {

        @Bean
        SingletonCounter singletonCounter() {
            return new SingletonCounter();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @Import(ServiceBeans.class)
    @EnableAspectJAutoProxy
    static class PerThisConfig {

        @Bean
        @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
        PerThisCounter perThisCounter() {
            return new PerThisCounter();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @Import(ServiceBeans.class)
    @EnableAspectJAutoProxy
    static class PerTargetConfig {

        @Bean
        @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
        PerTargetCounter perTargetCounter() {
            return new PerTargetCounter();
        }
    }

    private static void run(String mode, Class<?> config) {
        try (var context =
                     new AnnotationConfigApplicationContext(config)) {
            Job first = context.getBean("first", Job.class);
            Job second = context.getBean("second", Job.class);

            System.out.println("=== " + mode + " ===");
            first.execute();
            second.execute();
            first.execute();
            second.execute();
        }
    }

    public static void main(String[] args) {
        run("singleton", SingletonConfig.class);
        run("perthis", PerThisConfig.class);
        run("pertarget", PerTargetConfig.class);
    }
}
~~~

**Read the configuration carefully:**

1. **ServiceBeans** creates two beans named **first** and **second**. It is not one bean with two alias names: each method creates a **different JobImpl target**.
2. Each context uses **@Import(ServiceBeans.class)** and **@EnableAspectJAutoProxy**.
3. Each context has only **one** aspect bean definition; no component scan is needed and all three aspects are not accidentally registered together.
4. **SingletonConfig** creates a singleton aspect bean by default; no per-clause.
5. **PerThisConfig** creates a prototype aspect bean, with perthis in class metadata.
6. **PerTargetConfig** also creates a prototype aspect bean, with pertarget in class metadata.
7. Three contexts are created and closed sequentially. **Do not combine instance counts across the three contexts**; instance counts belong to each ApplicationContext.
8. The **@Bean** methods use package-private visibility in this same-package example. Configuration classes are declared as **static nested classes** so Spring can load them without needing an instance of the outer App.

**@Bean** calling **new** does not lose Spring AOP: the returned object is managed by the container. Conversely, if the client manually creates **new JobImpl("A")** and calls it directly, no Spring proxy sits on the call path so advice does not run.

### 7.7. Running the Program

From the **spring-aop-instantiation** directory, run:

~~~bash
mvn -q clean compile exec:java
~~~

**Logical lines following the program's call order:**

For **singleton**, every call uses the same aspect instance, so the output for this part is:

~~~text
=== singleton ===
ASPECT singleton count=1 target=A
SERVICE A
ASPECT singleton count=2 target=B
SERVICE B
ASPECT singleton count=3 target=A
SERVICE A
ASPECT singleton count=4 target=B
SERVICE B
~~~

In the **perthis** and **pertarget** sections, because **first** and **second** have two independent proxies and two independent targets, advice state is managed per corresponding object. We verify that the **ASPECT perthis/pertarget** log line appears before the **SERVICE** line for advised calls, and see the counters for A and B increment **independently** (advice calls on A: 1, 2; advice calls on B: 1, 2).

**Note on the first call:** The per-clause uses the first join point to trigger instance creation; Spring documentation notes that before the instance is created, advice for that instance has not run yet. Therefore, do not rely on a single log line from the first call to measure how many times an aspect is instantiated. When doing deep lifecycle testing, check the full invocation sequence and observe state after the instance is bound to the proxy/target.

To observe more precisely when debugging, set breakpoints in the constructors of **PerThisCounter** and **PerTargetCounter**, record the identity of the aspect instance, and then set a breakpoint in **before(...)**. You can distinguish **instantiation time** from **the time an advice invocation begins**.

> The instance count comparisons in this lesson are **model-level expected behavior** according to configuration. The illustrative code snippets rely only on stdout explicitly identified as logical observation; when the program runs in an IDE/Maven, framework-specific messages are outside the expected output.

## 8. Precisely Distinguishing Proxy (this) and Target

In Spring AOP, the object held by the client is usually a proxy. At a join point:

- **this**: refers to the **Spring AOP proxy**.
- **target**: refers to the **application object** behind the proxy.

Imagine two proxy objects both pointing to target T:

| Identity | perthis | pertarget |
| --- | --- | --- |
| P1 → T | Aspect instance A1 | Aspect instance A |
| P2 → T | Aspect instance A2 | Still aspect instance A |
| Call P1 → T again | Uses A1 | Uses A |
| Call P2 → T again | Uses A2 | Uses A |

If P1 and P2 are two **bean name aliases returning the same proxy**, there are not two different proxy identities; perthis does not create an extra instance just for changing alias names. Conversely, two different targets generally lead to two pertarget associations even if they share the same implementation class.

**Whether the proxy is JDK or class-based** only determines how Spring creates the intermediary object and which methods can be intercepted. The rules distinguishing proxy identity/target identity must still be applied when analyzing perthis/pertarget.

### Distinguishing the Java `this` Variable from `this` in a Pointcut

Inside the **JobImpl** class, Java's **this** is the target object while the method is executing. In the Spring AOP **this(...)** expression, object selection/matching semantics refer to the Spring AOP **proxy**. Do not infer backward solely from the shared keyword.

**joinPoint.getThis()** returns the proxy; **joinPoint.getTarget()** returns the target. Illustrative check snippet inside advice:

~~~java
Object proxy = joinPoint.getThis();
Object target = joinPoint.getTarget();
System.out.println("SAME_OBJECT " + (proxy == target));
~~~

This snippet is a **fragment to add inside advice**, not a standalone Java file. With a real proxy wrapping a separate target, the value is typically **false**. This result alone does not prove whether perthis or pertarget is in use; it must be combined with the declared aspect model and object identities.

## 9. Relationship Between the Per-Clause and Advice Pointcut

Example:

~~~java
@Aspect("perthis(execution(* demo.Job.execute(..)))")
public class DemoAspect {

    @Before("execution(* demo.Job.execute(..))")
    public void beforeExecution() {
        // ...
    }
}
~~~

There are **two expressions**:

1. **Inside perthis(...)**: describes the join points that trigger/associate an aspect instance with a proxy.
2. **Inside @Before(...)**: describes the join points that the advice logic wants to handle.

The two expressions can differ. However, if you choose a per-clause narrower than the advice, the advice might not have an instance bound to the proxy/target for the desired call. If too broad, many services may get unnecessary instances bound.

In Spring AOP, only **method-execution join points on Spring beans** are supported by proxies. Using **call(...)**, field access, constructor execution, or designators unsupported by Spring AOP does not become valid merely because of perthis or pertarget. With JDK proxies, public method calls on the proxy's interface are the standard path.

**Self-invocation** remains a limitation: if a method on the target calls **this.execute()** internally, that direct Java call does not go back through the Spring proxy; there is no new advisor invocation merely because the aspect uses perthis or pertarget.

## 10. When Are Aspect Instances Created and Destroyed?

### 10.1. Singleton

The Spring container normally creates a singleton aspect when initializing required singletons in the context (unless lazy initialization or special configuration applies). That single instance lives with the Spring bean lifecycle, and Spring manages appropriate callbacks when closing the context.

When an aspect is singleton, **it is not recreated per proxy or per method call** just because two different services are advised.

### 10.2. Perthis and pertarget

Spring AOP uses an aspect instance factory capable of supplying multiple instances when needed. Each matching proxy or target gets its own instance bound once the per-clause matches. That instance is tied to the corresponding object; it is not a request/session lifecycle or thread unit.

With **Spring prototype scope**, the container creates and injects bean instances, yet by default **does not guarantee calling destroy callbacks for all prototype instances**. Therefore, do not put resources needing complex cleanup directly inside each perthis/pertarget aspect expecting context close to destroy every instance like a singleton. If the aspect needs connections, pools, caches, or long-lived resources, inject a separate lifecycle-managed Spring bean rather than letting each aspect instance own hard-to-reclaim resources.

Creating multiple instances also does not mean the aspect holds **per-HTTP-request** state. Multiple requests can call the same proxy and the same target; in that case they still access the corresponding aspect instance and require a thread-safe design.

## 11. Why Not Use @Scope("request") or @Scope("prototype") Instead of perthis?

Several Spring bean scopes are often confused with AOP instantiation models:

| Mechanism | Decided by | Appropriate question |
| --- | --- | --- |
| Bean **singleton** | Bean name in Spring container | Which object is returned each time the same bean is retrieved? |
| Bean **prototype** | Each time container is asked to create/retrieve bean | Can a new bean instance be created? |
| Bean **request** | Active web request scope | Which object does each request use? |
| Aspect **perthis** | Proxy identity at matching join point | Which aspect instance is a proxy associated with? |
| Aspect **pertarget** | Target identity at matching join point | Which aspect instance is a target associated with? |

**`@Scope("prototype")` on a perthis/pertarget aspect is a condition for Spring to supply instances per the aspect model**, not an equivalence of the two terms. If the real requirement is counting transactions per HTTP request, perthis/pertarget may be unsuitable: the same singleton service proxy serving multiple requests will still share an aspect instance. In that case, handle per-request data using an appropriate dependency/scope rather than assigning request semantics to perthis.

## 12. Configuration Errors and How to Diagnose Them

### 12.1. Declaring perthis or pertarget on a Singleton Aspect Bean

Incorrect example:

~~~java
@Aspect("perthis(execution(* demo.Job.execute(..)))")
@Component
public class BrokenAspect {
    // ...
}
~~~

Under default component scan, **BrokenAspect** is registered as singleton. The perthis model requires multiple aspect instances and is therefore incompatible. Fix:

~~~java
@Aspect("perthis(execution(* demo.Job.execute(..)))")
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class FixedAspect {
    // ...
}
~~~

These two snippets **only illustrate the configuration difference**; they are not files in the runnable project in Section 7. When copying, import **Aspect**, **Component**, **Scope**, and **ConfigurableBeanFactory** properly and include the required advice method. Errors can appear while Spring builds advisors or proxies, with a message indicating that the bean is singleton while the aspect instantiation model is not singleton.

### 12.2. Having @Aspect and @Scope Without a Bean

**@Aspect** does not automatically register a Spring bean. Without **@Component** and without **@Bean**, the aspect may not be found. In the Section 7 example, aspects are registered via **@Bean**, so the aspect classes do not need **@Component**.

### 12.3. Having an Aspect Bean Without Enabling Spring AOP

In plain Spring Framework, **@EnableAspectJAutoProxy** or equivalent infrastructure configuration is needed. Simply instantiating an aspect instance does not mean advice will run automatically.

### 12.4. Confusing Bean Aliases with Multiple Targets/Proxies

Two bean names can alias to the same object, or two distinct beans can share the same implementation class. To deduce perthis/pertarget instance counts, observe **actual identity**, not just names or classes. Suggested tools: **AopUtils.isAopProxy(...)**, **System.identityHashCode(...)** when debugging, and **==** comparisons for two references retrieved from the Spring context.

### 12.5. Having Mutable State Shared Across Multiple Threads

Even perthis/pertarget is **not thread-local**. If multiple threads use the same proxy or target, they can concurrently update the **calls** field of the same aspect instance.

When accurate counting in a concurrent environment is needed, replace `int calls` with **AtomicInteger**:

~~~java
private final java.util.concurrent.atomic.AtomicInteger calls =
        new java.util.concurrent.atomic.AtomicInteger();

int count = calls.incrementAndGet();
~~~

This is a **replacement fragment for the field and increment inside the aspect**, not a standalone program. AtomicInteger only solves single atomic increments; logic coordinating multiple other states must still be designed for concurrency.

### 12.6. Advice Does Not Run on Certain Calls

Check each condition: whether the service is truly a Spring-managed bean, has an appropriate proxy, whether the advice expression matches, whether the per-clause matches the object, and whether the call goes through the proxy. Do not blame every missing log on the wrong instantiation model.

## 13. Selection Table for Practical Problems

| Purpose | Initial approach | Reason |
| --- | --- | --- |
| Logging, timing, system-wide call count tracking | **singleton** + thread-safe collaborator | Simple and few instances |
| Holding state related to a **specific proxy** | **perthis** | Identity is the Spring proxy |
| Holding state related to a **specific target** | **pertarget** | Identity is the object behind the proxy |
| Keeping data isolated per HTTP request | Request-scoped bean/appropriate context | Do not equate requests with proxies/targets |
| Wanting isolated data per method invocation | Local variables in advice | Avoid holding unnecessary state in the aspect |
| Wanting a new dependency bean created on each use | ObjectProvider, lookup, or appropriate factory | Different from aspect instantiation models |

In most Spring applications using aspects for logging, auxiliary validation, or tracing, a **stateless singleton aspect** is the most maintainable choice. Only switch to perthis/pertarget when there is a genuine need to **store state bound to proxy/target identity**, and the relationships among objects in the container are well understood.

## 14. Self-Assessment Questions

**1. Why must @Aspect("perthis(...)") usually be paired with @Scope("prototype")?**

Because Spring needs the ability to create multiple aspect instances to associate with different proxies. A default singleton bean has only one instance and does not satisfy the perthis model.

**2. If an ApplicationContext has three service beans, is pertarget guaranteed to create three aspect instances immediately at startup?**

No. The instance count depends on the number of **matching targets triggered via matching join points**, not merely the number of bean definitions. Instances can be created on demand when the corresponding join point first occurs.

**3. Suppose two proxies P1 and P2 both wrap target T. How do perthis and pertarget differ?**

If both proxies trigger the per-clause: perthis can associate **two** aspect instances with P1 and P2; pertarget associates **one** aspect instance with target T.

**4. Why can two different singleton service beans create two pertarget aspect instances?**

Because each service bean can be an independent target object. The singleton scope of **each service bean** does not mean all services share one object.

**5. Does perthis mean one aspect instance per thread?**

No. It binds to proxy identity. Multiple threads calling the same proxy can touch the same aspect instance.

**6. Is simply adding @Scope("prototype") to a regular @Aspect already equivalent to pertarget?**

Not yet. Prototype controls how the container supplies beans; pertarget is specific metadata in **@Aspect("pertarget(...)")**.

**7. Why might two calls from the same client not run advice even though the bean was created?**

Because only method executions matching the pointcut and passing through the Spring proxy are advised. Self-invocation on the target or non-matching methods do not automatically run new advice.

**8. Should an instance field of a singleton aspect be used to store the current request ID?**

No. A singleton aspect can be used concurrently by multiple requests and threads. Invocation data should reside in local variables or an explicitly designed context mechanism.

## 15. Spring AOP Configuration Checklist

- Identify the **ApplicationContext** containing the target bean and aspect bean.
- Enable **@EnableAspectJAutoProxy** in plain Spring Framework, or verify the corresponding AOP configuration exists.
- Register the aspect with **@Component/@Bean**, not just **@Aspect**.
- Choose default **@Aspect** for singleton, **@Aspect("perthis(...)")** or **@Aspect("pertarget(...)")** when wanting instances bound to objects.
- With perthis/pertarget, configure the aspect bean as **prototype**, avoiding the default singleton bean.
- Keep the per-clause and advice pointcut clear; test the exact invocations to intercept.
- Inspect **proxy identity**, **target identity**, and the possibility of multiple bean names pointing to the same object.
- Design mutable state safely when multiple threads can use the same aspect instance.
- Do not assume advice runs just because Spring has an aspect bean or service bean; verify actual behavior.

## 16. Official Documentation for Cross-Checking

- **Spring Framework — Aspect Instantiation Models**: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/instantiation-models.html
- **Spring Framework — Declaring a Pointcut** (difference between this and target in Spring AOP): https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html
- **Spring Framework — @AspectJ Support**: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html
- **Spring Framework — Proxying Mechanisms**: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- **Spring Framework — Bean Scopes** (container singleton/prototype): https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html

**Key takeaway:** Spring AOP supports the singleton, perthis, and pertarget aspect instantiation models. Singleton shares one instance; perthis binds aspect state to the Spring AOP proxy; pertarget binds it to the target object. Configuring **@Scope("prototype")** is an important requirement for perthis/pertarget to work with Spring-managed aspects, yet bean prototype scope and aspect instantiation model are not the same concept.
