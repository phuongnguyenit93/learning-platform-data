# The Role of the Auto-Proxy Creator in ApplicationContext

## 1. What Is an Auto-Proxy Creator and What Problem Does It Solve?

In a Spring application, `OrderService`, `PaymentService`, or `InventoryService` are usually obtained via dependency injection or `ApplicationContext.getBean()`. When developers define an aspect to log, measure timing, or apply a cross-cutting policy, they normally **do not manually create proxies for each service**. Spring does that through an infrastructure component called the **auto-proxy creator**.

An **auto-proxy creator** is a type of **Spring `BeanPostProcessor`** capable of observing beans created by the container, determining whether a bean needs advisors/advice, and providing an **AOP proxy** in place of the original bean object when needed. As a result:

- Target beans do not need to know specifically about `@Aspect`, advisors, interceptors, or how proxies are created.
- One AOP policy can be applied consistently across many Spring-managed beans according to a pointcut.
- Callers receive **the reference returned by the container**; if the bean qualifies, that reference is a proxy carrying the required interceptor chain.
- A bean matching no advisor can be returned normally, without an AOP proxy created by that configuration.

The scope of this lesson is **Spring AOP's auto-proxy creator inside `ApplicationContext`**, especially when using `@Aspect` and `@EnableAspectJAutoProxy` declarations. This is Spring's proxy mechanism, **not AspectJ compile-time or load-time weaving**.

One rule to keep in mind from the start:

> **The auto-proxy creator selects and creates proxies during the bean-management lifecycle; advice runs when a matching method is called through the proxy.** These are two different points in time.

## 2. Where Does It Sit in `ApplicationContext`?

Simplified diagram:

```text
@Configuration / <aop:aspectj-autoproxy/> / Boot AOP configuration
                         |
                         v
           Register auto-proxy creator
           as a BeanPostProcessor
                         |
                         v
ApplicationContext initializes and registers BeanPostProcessors
                         |
                         v
             Create target bean from definition
                         |
                         v
            Inject dependencies, init callbacks
                         |
                         v
Auto-proxy creator inspects bean after initialization
         |                               |
         | Matching advisor found        | No matching advisor
         v                               v
   Create AOP proxy               Keep bean without AOP proxy
         |                               |
         +---------------+---------------+
                         |
                         v
            Expose bean from ApplicationContext
                         |
                         v
Caller calls through proxy -> advice -> target method
```

The diagram depicts the typical path when bean initialization finishes. Spring also has hooks supporting early references for complex bean-creation situations; therefore, **do not treat this as a fixed algorithm applied verbatim to every bean**. The key point to grasp is that the auto-proxy creator is registered early enough with the container to participate in processing beans created afterward.

### 2.1. Distinguishing the Participants

| Object | Managed by whom? | Responsibility |
| --- | --- | --- |
| `ApplicationContext` | Spring runtime | Coordinates bean definitions, post-processors, scopes, lifecycle, and lookups. |
| **Auto-proxy creator** | Registered as a `BeanPostProcessor` bean in the context | Finds candidate advisors/aspects, evaluates applicability, creates proxies when needed. |
| **Aspect bean** | Spring IoC | Contains `@Aspect`, pointcuts/advice for shared behavior. |
| **Advisor** | Spring AOP infrastructure | Combines advice with applicability conditions/pointcut; serves as input for the auto-proxy creator's selection. |
| **Target bean** | Spring IoC | Contains the actual business code. |
| **AOP proxy** | Created by Spring AOP and handed to callers | Routes method calls through the interceptor chain before reaching the target. |

The auto-proxy creator **does not replace** the bean factory. The bean factory still creates/injects/initializes the target according to Spring's contract; the auto-proxy creator participates in the post-processing phase to potentially wrap that bean.

## 3. Why Is the Auto-Proxy Creator a `BeanPostProcessor`?

`BeanPostProcessor` is an extension point that allows Spring to process a **bean object** at the time the container creates it, rather than only modifying bean definitions. The two fundamental callbacks are:

```java
Object postProcessBeforeInitialization(Object bean, String beanName);
Object postProcessAfterInitialization(Object bean, String beanName);
```

These are **simplified signatures for learning**, not a standalone Java class. In the typical flow, the auto-proxy creator extends the `AbstractAutoProxyCreator` infrastructure, using the appropriate callbacks to decide whether to return a proxy or keep the current bean.

When an `@Bean` or `@Component` is created:

1. Spring handles instance creation, dependency injection, and lifecycle callbacks.
2. The auto-proxy creator inspects the name/class/metadata and applicable advisors.
3. If corresponding advice exists, it builds an appropriate proxy, attaching the selected advisors/interceptors.
4. Spring publishes the final reference to callers retrieving the bean from the container.

As a result, clients receiving the bean via DI or `context.getBean()` may only see **the proxy**; calling a method through this reference triggers the advisor chain. If a caller manually `new`s the target object or holds a raw target reference from outside, Spring cannot automatically apply the `ApplicationContext`'s proxy to that reference.

**Do not confuse with `BeanFactoryPostProcessor`:** the latter processes **metadata/bean definitions**, whereas `BeanPostProcessor` processes **instances**. The auto-proxy creator belongs to the group processing bean instances, not a step that alters class source code.

## 4. Where Does the Auto-Proxy Creator Get Advice Information?

Depending on configuration, Spring may have **`Advisor` beans** or **`@Aspect` beans**. With `@EnableAspectJAutoProxy` configuration, Spring registers the `@AspectJ`-style support class to recognize aspect beans within the same context, convert advice declarations into advisors, and check which advisors apply to the bean being created.

Example:

```java
@Aspect
public class AuditAspect {
    @Before("execution(public * com.example.shop.*Service.*(..))")
    public void audit() {
        // Record an event before the service method executes.
    }
}
```

This is an **illustrative fragment**, not yet including imports/bean registration. If `AuditAspect` is registered in the Spring context and `@AspectJ` mode is enabled, Spring can discover the `audit()` advice and apply it to methods matching the expression. An `InventoryService.update()` in the example package can be proxied; a `HealthStatus.ping()` not matching the pointcut will not be proxied solely by that aspect.

Several evaluation criteria:

- **Is the bean managed by Spring?** The `@Aspect` annotation alone does not automatically create a bean; typically declare `@Aspect` + `@Component` or `@Bean`.
- **Does the aspect/advisor belong to the relevant context?** The auto-proxy creator operates within a specific container scope.
- **Do the class/methods match the pointcut?** An existing aspect does not mean every bean gets proxied.
- **Does the bean belong to a group to skip?** Advice, advisors, aspect classes, and certain infrastructure beans are not auto-proxied by this Spring AOP mechanism itself.
- **Is the proxy strategy valid?** Interface-based proxies and class-based proxies have different limits; `final` classes/methods cannot be overridden by CGLIB.

In Spring Framework, the class typically used for `@AspectJ` auto-proxying is:

```text
org.springframework.aop.aspectj.annotation.AnnotationAwareAspectJAutoProxyCreator
```

It extends the `AspectJAwareAdvisorAutoProxyCreator` / `AbstractAdvisorAutoProxyCreator` hierarchy, handling both **Spring Advisors** and annotation-declared aspects. This is an **infrastructure class**; learners normally do not need to declare `@Bean` or `new AnnotationAwareAspectJAutoProxyCreator()` manually—simply use the configuration Spring provides.

## 5. Enabling the Auto-Proxy Creator in a Spring Application

### 5.1. Java Configuration — `@EnableAspectJAutoProxy`

```java
@Configuration
@EnableAspectJAutoProxy
public class AopConfig {
}
```

This is a **configuration fragment**. The annotation instructs Spring to enable auto-proxy support based on managed `@Aspect` aspects. In a plain Spring Framework application, you also need `spring-context`/Spring AOP and the `aspectjweaver` library to parse `@AspectJ` syntax (e.g., via Maven/Gradle).

The annotation **does not turn every class annotated with `@Aspect` into a bean**. The aspect must actually be registered, such as `@Aspect` + `@Component` within component scan or an `@Bean` returning the aspect class.

Configurable attributes:

```java
@EnableAspectJAutoProxy(proxyTargetClass = true, exposeProxy = false)
```

- `proxyTargetClass = true`: prefers **class-based proxies** (CGLIB).
- `proxyTargetClass = false`: uses the default proxy strategy; when the target has suitable interfaces, typically selects a JDK dynamic proxy.
- `exposeProxy = true`: allows accessing the current proxy via `AopContext.currentProxy()` inside an exposed AOP call. This is an advanced option with overhead and coupling, **not the default fix for self-invocation**.

### 5.2. XML Configuration

```xml
<aop:aspectj-autoproxy proxy-target-class="true"/>
```

The line above must be placed inside valid XML declaring the `aop` namespace; this is only a **fragment**, not a complete XML document. It requests auto-proxy support for `@AspectJ` in Spring similarly to the Java annotation.

Another XML configuration with `<aop:config>` or a proxy-based feature such as `<tx:annotation-driven>` can also register/upgrade the auto-proxy infrastructure. Spring unifies standard infrastructure configurations to avoid creating a separate auto-proxy creator per XML line.

### 5.3. Spring Boot

With Spring Boot, the AOP starter and auto-configuration normally take care of enabling the appropriate infrastructure. For example, Boot 3.x uses `spring-boot-starter-aop`; Boot 4.x has `spring-boot-starter-aspectj`. There is no need to add `@EnableAspectJAutoProxy` just to "enable it one more time" if Boot already configures AOP properly.

When changing proxy mode in Boot, check the `spring.aop.proxy-target-class` property and other proxy settings actually loaded. **Boot properties do not replace understanding the auto-proxy creator mechanism in the Spring container**, and one should not infer from the starter that AspectJ weaving is active.

## 6. Complete Example: Seeing the Auto-Proxy Creator in `ApplicationContext`

The example uses **Java 17+, Spring Framework 6.1.14, AspectJ 1.9.22.1, and Maven**, without Spring Boot or a web server. Observable goals:

1. `ApplicationContext` contains the internal auto-proxy creator bean.
2. The `OrderService` bean matching the pointcut is proxied.
3. The `CatalogInfo` bean does not match the pointcut, so it is not required by this aspect to be proxied.
4. Calling `OrderService.place()` through the bean obtained from the context runs the advice exactly once.
5. The `AuditAspect` aspect is managed by Spring but is not itself proxied by Spring AOP.

### 6.1. Project Structure

```text
spring-auto-proxy-demo/
├── pom.xml
└── src/main/java/com/example/apc/
    ├── DemoApp.java
    ├── AppConfig.java
    ├── OrderService.java
    ├── CatalogInfo.java
    └── AuditAspect.java
```

### 6.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-auto-proxy-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.14</version>
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
                <version>3.13.0</version>
                <artifactId>maven-compiler-plugin</artifactId>
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

`spring-context` provides the container and brings in related Spring modules, including `spring-aop`; `aspectjweaver` provides the AspectJ parts needed for `@Aspect` declarations. All code below runs with the example's dependencies; no AspectJ compiler/weaving agent is required.

### 6.3. `src/main/java/com/example/apc/OrderService.java`

```java
package com.example.apc;

public class OrderService {
    public String place(String orderId) {
        System.out.println("[ORDER] " + orderId);
        return "accepted:" + orderId;
    }
}
```

### 6.4. `src/main/java/com/example/apc/CatalogInfo.java`

```java
package com.example.apc;

public class CatalogInfo {
    public String version() {
        return "v1";
    }
}
```

### 6.5. `src/main/java/com/example/apc/AuditAspect.java`

```java
package com.example.apc;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class AuditAspect {
    private final AtomicInteger invoked = new AtomicInteger();

    @Before("execution(public * com.example.apc.OrderService.place(..))")
    public void beforePlace(JoinPoint joinPoint) {
        invoked.incrementAndGet();
        System.out.println("[AUDIT] " + joinPoint.getSignature().getName());
    }

    public int calls() {
        return invoked.get();
    }
}
```

This aspect has only one advice dedicated to `OrderService.place(..)`. `AtomicInteger` makes counting safe under concurrent calls; a singleton aspect is typically shared across many target calls. The illustrative code uses `println` for observation; real applications should use proper logging/metrics.

### 6.6. `src/main/java/com/example/apc/AppConfig.java`

```java
package com.example.apc;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public AuditAspect auditAspect() {
        return new AuditAspect();
    }

    @Bean
    public OrderService orderService() {
        return new OrderService();
    }

    @Bean
    public CatalogInfo catalogInfo() {
        return new CatalogInfo();
    }
}
```

`@Bean auditAspect()` puts `AuditAspect` into the context. `@EnableAspectJAutoProxy` activates the auto-proxy creator; `proxyTargetClass=true` forces a class-based proxy for `OrderService`, which implements no interface. `CatalogInfo` is also a Spring bean, but no advisor matches it in this configuration.

### 6.7. `src/main/java/com/example/apc/DemoApp.java`

```java
package com.example.apc;

import org.springframework.aop.config.AopConfigUtils;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.config.BeanPostProcessor;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApp {
    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            Object creator =
                    context.getBean(AopConfigUtils.AUTO_PROXY_CREATOR_BEAN_NAME);
            OrderService orderService = context.getBean(OrderService.class);
            CatalogInfo catalogInfo = context.getBean(CatalogInfo.class);
            AuditAspect aspect = context.getBean(AuditAspect.class);

            System.out.println("creatorIsBPP="
                    + (creator instanceof BeanPostProcessor));
            System.out.println("orderIsAopProxy=" + AopUtils.isAopProxy(orderService));
            System.out.println("catalogIsAopProxy=" + AopUtils.isAopProxy(catalogInfo));
            System.out.println("aspectIsAopProxy=" + AopUtils.isAopProxy(aspect));

            String result = orderService.place("O-42");
            System.out.println("result=" + result);
            System.out.println("catalog=" + catalogInfo.version());
            System.out.println("adviceCalls=" + aspect.calls());
        }
    }
}
```

In this Spring Framework example, `AopConfigUtils.AUTO_PROXY_CREATOR_BEAN_NAME` is an internal infrastructure name Spring uses for the auto-proxy creator. **This is a diagnostic API/detail belonging to this specific configuration**, not an application service name for external systems to rely on. In a Spring Boot application or with other AOP configurations, do not hardcode a single implementation class as a system operating requirement.

### 6.8. Running and Reading the Output

Requirements: JDK 17+, Maven, connectivity to download dependencies. In the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.apc.DemoApp
```

Lines printed by the program itself (excluding separate Maven/SLF4J messages if any):

```text
creatorIsBPP=true
orderIsAopProxy=true
catalogIsAopProxy=false
aspectIsAopProxy=false
[AUDIT] place
[ORDER] O-42
result=accepted:O-42
catalog=v1
adviceCalls=1
```

**Why does the program produce that output?**

- `creatorIsBPP=true`: Spring registered an auto-proxy creator infrastructure bean implementing `BeanPostProcessor`.
- `orderIsAopProxy=true`: the advice matches `OrderService.place(..)`; Spring creates a proxy and returns it for `context.getBean(OrderService.class)`.
- `catalogIsAopProxy=false`: `CatalogInfo.version()` is not selected by this advisor; there is no reason to create an AOP proxy for `CatalogInfo` in the example.
- `aspectIsAopProxy=false`: the `@Aspect` class is used to supply advice, not as a target auto-proxied by Spring AOP's own `@AspectJ` infrastructure.
- `[AUDIT]` appears **before** `[ORDER]`: the caller invokes through the proxy, `@Before` runs, and then the target method executes. `adviceCalls=1` confirms the advice execution count.

What is demonstrated here is **the presence and outcome of the auto-proxy creator in a specific Spring context**. Do not infer that every bean in Spring is proxied or that the `isAopProxy` values above always hold when other advisors/proxies are added to an application.

## 7. How the Auto-Proxy Creator Chooses Which Beans to Proxy

In the `@AspectJ`-supporting model, the decision flow can be pictured as:

```text
Newly created bean
    |
    v
Is it an infrastructure/aspect/advisor bean to exclude?
    | Yes
    +--> Skip this kind of auto-proxying
    |
    | No
    v
Find advisors applicable to the bean's class/methods
    |
    +--> No matching advisor
    |        |
    |        +--> Keep original bean
    |
    +--> Matching advisor found
             |
             v
     Determine proxy strategy
     (interface or class-based)
             |
             v
     Attach advisors/interceptors to proxy
             |
             v
     Return proxy reference to caller
```

`AnnotationAwareAspectJAutoProxyCreator` recognizes advisor beans and `@Aspect` beans in the context. It uses pointcut metadata to know which methods can be advised; it does not need to trial-run every method to know whether it matches.

### 7.1. Not Every Bean Is Proxied

An aspect applying only to `execution(* com.example..service.*.*(..))` should not create proxies for all configuration classes, DAOs, or plain DTOs just because those classes are also Spring beans.

**Having beans that are not proxied is the right state.** When reading startup logs, do not conclude the auto-proxy creator failed to run just because not every bean's class changed to a proxy name.

### 7.2. The Auto-Proxy Creator Does Not Decide "Which Method to Call" for the Caller

The Spring auto-proxy creator wraps the bean during management. Afterward, **the caller is still where methods are invoked**, and the interceptor chain executes advice when a call goes through the proxy and matches the pointcut. If another non-matching method is called, the proxy can forward without running that advice.

With a class-based proxy, an object can have many methods; the class being eligible for proxying does not prove every method has advice. Test per method/policy rather than relying only on `AopUtils.isAopProxy()`.

### 7.3. Supporting Advisors Beyond `@Aspect`

In Spring, policies such as transaction interception can use the same advisor and proxy infrastructure. Depending on which infrastructure is enabled, the auto-proxy creator can coordinate these advisors; do not manually create another AOP proxy outside Spring just to add logging without first checking existing advisors.

Also distinguish:

- **`BeanNameAutoProxyCreator`**: auto-proxies based on configured bean names.
- **`DefaultAdvisorAutoProxyCreator`**: selects matching advisors for target beans.
- **`AnnotationAwareAspectJAutoProxyCreator`**: selects advisors and recognizes aspects declared with `@Aspect`.

These are selection mechanisms in Spring AOP. Standard applications should configure via the annotations/XML/starters Spring provides, rather than registering multiple auto-proxy creators manually without a clear architecture.

## 8. One Unified Auto-Proxy Creator Does Not Mean Only One Advice

When using multiple AOP declaration sites (Java config, XML, transaction management), Spring has rules to **unify standard auto-proxy creators within the same context**. For example:

```java
@EnableAspectJAutoProxy(proxyTargetClass = false)
```

and XML:

```xml
<aop:aspectj-autoproxy proxy-target-class="true"/>
```

When both are active in one container, Spring's infrastructure can apply the stronger proxy option, such as **class-based proxying** requested via `true`. You cannot conclude that an annotation statement with `false` will always win if XML or another Spring feature has set `true`.

However, unifying the creator **does not deduplicate functionally identical advice**. For example:

- Two differently named beans both carry an `@Aspect` class with an identical `@Before`.
- A Java `@Aspect` and an XML advisor both record an audit event on the very same method.
- Two different aspects intentionally log at the same join point.

These cases can run multiple advice. **Count the aspect beans/advisors and observe method invocations**; do not count `@EnableAspectJAutoProxy` lines to infer how many times advice runs.

**Spring Framework scope:** unification rules apply to proxy infrastructures participating in the standard mechanism within the same context. If an application has parent/child contexts, third-party `BeanPostProcessor`s, scoped proxies, or manually created proxies, inspect each specific mechanism and call path.

## 9. Boundaries of the Auto-Proxy Creator in the Container

### 9.1. It Only Sees Beans Within Its Processing Scope

Spring registers `BeanPostProcessor`s **per `ApplicationContext`**. A creator in a parent context does not automatically post-process beans instantiated only in a child context, and vice versa. In web applications or multi-context systems, enabling `@EnableAspectJAutoProxy` in one layer does not automatically apply advice to controllers/services in another layer.

Therefore, when advice does not run, check **which context owns the target bean and the aspect bean** before changing the pointcut.

### 9.2. Beans Created Too Early Can Miss Post-Processing

When `ApplicationContext` starts up, it must create and register `BeanPostProcessor`s early so they apply to regular beans. Beans initialized **during a very early phase**, especially `BeanPostProcessor`s themselves and their direct dependencies, may **not be eligible for processing by all post-processors**, including the auto-proxy creator. Spring logs typically indicate that the bean is not eligible for getting processed by all post-processors.

Common causes:

- Writing a custom `BeanPostProcessor` and injecting business services into its constructor, causing those services to be created before full post-processing is ready.
- A factory method declaring a `BeanPostProcessor` in a way that forces an `@Configuration` class to initialize too early.
- Calling `getBean()` proactively during the bean-definition modification phase, disrupting normal lifecycle order.

The fix is to **avoid pulling business beans into the post-processor registration phase**. When writing an `@Bean` returning a `BeanPostProcessor`, Spring recommends a `static` method with minimal dependencies where appropriate; do not apply that trick arbitrarily to every `@Bean`.

### 9.3. Self-Invocation Does Not Go Through the Proxy

```java
public class OrderService {
    public void checkout() {
        validate(); // this.validate(), internal call on target.
    }

    public void validate() {
        // Business validation.
    }
}
```

This is an **illustrative class fragment**. If a caller invokes `proxy.checkout()`, Spring can advise `checkout()`; however, calling `validate()` from inside the target does not go through the proxy, so advice dedicated to `validate()` will not run via the auto-proxy creator.

The creator already did its job of **wrapping the bean**; it does not rewrite every `this.method()` call in bytecode. A common simple approach is to move the advised part into another bean so calls go through a Spring-managed dependency.

### 9.4. Constructors and Initialization Callbacks Are Not "Calls Through the Proxy"

Spring normally runs `@PostConstruct`, `InitializingBean.afterPropertiesSet()`, or init methods on the raw bean during initialization, before the normal proxy reference is returned to callers. An internal call from an init callback does not automatically run Spring AOP advice.

If business logic must run after the context is initialized and proxies exist, choose an entry point suited to the application lifecycle (e.g., another component calling through the Spring bean after the context is ready). Do not use `@Before`/`@After` to replace `@PostConstruct`/`@PreDestroy`.

### 9.5. Manually `new`'d Objects or `final` Methods

`new OrderService()` outside the Spring container **is not processed by the creator**. A class-based proxy cannot intercept `final` methods; a `final` class cannot be subclassed by CGLIB either. With a JDK dynamic proxy, callers go through the interface; class-only methods are not automatically present on the proxy interface. These limitations affect the auto-proxy creator's effectiveness even when the `@Aspect` and pointcut are correct.

## 10. How to Inspect the Auto-Proxy Creator in a Running Project

### 10.1. Checking the Infrastructure Bean in the Context

With standard Spring AOP configuration enabled, you can use:

```java
boolean present = context.containsBean(
    org.springframework.aop.config.AopConfigUtils.AUTO_PROXY_CREATOR_BEAN_NAME
);
System.out.println("auto-proxy creator present = " + present);
```

This is **diagnostic code placed inside a program that already has a `context` variable**, not a standalone Java file. If no bean exists under this infrastructure name, check `@EnableAspectJAutoProxy`, XML, or the auto-configuration of the Spring version used in the app. Do not rely solely on internal bean names for production monitoring.

### 10.2. Checking the Proxy for a Specific Target

```java
Object bean = context.getBean("orderService");
boolean isProxy = org.springframework.aop.support.AopUtils.isAopProxy(bean);
System.out.println("proxied = " + isProxy);
```

Recognizing a proxy is step one. If `true`, determine **which advice sits inside the proxy and whether it matches the method being tested**; a bean might be proxied for transactions or scope without having a specific audit advice.

### 10.3. Observing Advisors When Needed

```java
Object bean = context.getBean("orderService");

if (bean instanceof org.springframework.aop.framework.Advised advised) {
    for (org.springframework.aop.Advisor advisor : advised.getAdvisors()) {
        System.out.println(advisor.getClass().getName());
    }
}
```

The snippet above is an **inspection fragment**, with no fixed stdout because advisor types/order depend on the application and Spring version. The advisor list does not equate to advice execution count: an advisor may have a pointcut that does not match the method being called, and the advisor chain may also contain Spring infrastructure.

### 10.4. Testing Behavior Rather Than Only Structure

A convincing test should prove:

1. The aspect bean is registered exactly once as designed.
2. The target bean is obtained from `ApplicationContext` with the appropriate proxy strategy.
3. A method matching the pointcut runs the expected number of advice.
4. A method/bean not matching the pointcut **does not** run this advice.
5. Business exceptions and return values are preserved properly.
6. Other transaction, security, or async modes still operate per project configuration.

If advice is missing, troubleshoot in the order **bean/context → auto-proxy setup → advisor/pointcut → proxy type → caller going through proxy**. If it runs twice, check whether there are multiple aspect beans/advisors or two method calls; do not immediately blame having two lines enabling AOP.

## 11. Common Configuration Errors

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| `@Aspect` is in source code, yet no advice runs | Aspect is not registered as a Spring bean; auto-proxy is not enabled. | Check `@Component`/`@Bean`, context, and `@EnableAspectJAutoProxy`/Boot starter. |
| Bean is injected, yet `AopUtils.isAopProxy() = false` | No matching advisor, creator not enabled, or bean created too early. | Check bean scope, bean creation site, advisors, and startup warnings. |
| AOP proxy exists, yet `@Before` does not run | Pointcut does not match method, self-invocation, or different context. | Try a direct public call through the proxy and compare against the pointcut. |
| Bean has class name `$$SpringCGLIB$$` | Class-based proxy created; this can be normal behavior. | Verify `proxyTargetClass` and why the bean is proxied; do not rely on class names to measure advice. |
| `ClassCastException` when casting proxy to implementation class | Using an interface-based JDK dynamic proxy. | Inject the interface or adjust the proxy strategy according to actual needs. |
| Aspect invoked twice on a single method | Multiple aspect beans/advisors match, or the caller actually calls the method twice. | Count aspect beans, the advisor chain, and per-invocation correlation IDs. |
| `Bean ... not eligible for auto-proxying` | Bean instantiated too early during `BeanPostProcessor` registration. | Inspect dependencies/factory methods of post-processors. |
| AOP in root context runs, controller child context does not | Creator and target reside in different contexts. | Check parent-child structure and local AOP configuration. |
| Changed Boot property, yet proxy still differs from expectations | Java/XML or another infrastructure component requests a stronger proxy strategy. | Inventory all proxy configurations in the context. |
| `final` method not advised by CGLIB | Subclass proxy cannot override the method. | Redesign method/class or use an interface proxy if appropriate. |

## 12. Practical Implementation and Verification Workflow

In a new Spring application or when introducing Spring AOP into an existing codebase:

1. **Identify the `ApplicationContext` owning the target bean.** Check where contexts are created, package scans, and imported XMLs.
2. **Enable the right kind of auto-proxy support.** Plain Spring with `@AspectJ` typically uses `@EnableAspectJAutoProxy`; Spring Boot prefers the auto-configuration matching its Boot version.
3. **Register aspect beans.** `@Aspect` + `@Component` or `@Bean`; check for duplicate registrations.
4. **Constrain pointcuts.** Only apply advisors to methods of beans needing shared behavior.
5. **Verify the proxy policy.** Decide between JDK dynamic proxy and class-based proxy; do not set `proxyTargetClass=true` mechanically.
6. **Observe actual beans and calls.** Use `AopUtils`, advisor inspection when needed, and a test verifying exact advice counts.
7. **Review lifecycle.** Avoid initializing services too early from custom post-processors, and avoid calling advised methods inside the target's constructor/init callbacks.
8. **Check overlapping configurations.** Spring may unify the creator, but does not automatically merge the logic of two advice with the same responsibility.
9. **Re-test after changing modules/contexts.** If moving a service to a child context, changing how beans are injected, or using scoped proxies, re-run AOP tests.

### Official Spring Documentation

- Spring Framework — Enabling @AspectJ Support: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html
- Spring Framework — Declaring an Aspect: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/at-aspectj.html
- Spring Framework — Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework — Auto-proxy facility: https://docs.spring.io/spring-framework/reference/core/aop-api/autoproxy.html
- Spring Framework — Container Extension Points / BeanPostProcessor: https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html
- Spring Framework — AnnotationAwareAspectJAutoProxyCreator API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/aop/aspectj/annotation/AnnotationAwareAspectJAutoProxyCreator.html
- Spring Framework — AbstractAutoProxyCreator API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/aop/framework/autoproxy/AbstractAutoProxyCreator.html

**The role of the auto-proxy creator in `ApplicationContext` is to turn Spring's aspect/advisor configuration into bean references capable of interception, right during the container's bean creation and publication process.** Spring still manages the target bean and its lifecycle, while calls through the proxy determine when advice actually executes.
