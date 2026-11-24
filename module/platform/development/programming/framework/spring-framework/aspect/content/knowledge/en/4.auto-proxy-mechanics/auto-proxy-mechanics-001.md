# The Role of BeanPostProcessor in Wrapping Spring Beans with an AOP Proxy

## 1. Central Question

When declaring an aspect with `@Aspect`, enabling `@EnableAspectJAutoProxy`, and retrieving a service from `ApplicationContext`, why can the returned service be a **proxy** instead of the original object? The mechanism connecting Spring IoC with Spring AOP is **`BeanPostProcessor`**.

In Spring, `BeanPostProcessor` (BPP) is an extension point that allows the container to process a **bean instance** during bean creation. A BPP can return the object it received or return another object — such as a proxy — for the container to use as the bean provided to other callers. Spring AOP's **auto-proxy creator** infrastructure implements that mechanism: it finds matching advisors/advice and replaces the exposed instance with an AOP proxy when needed.

The scope here is how Spring performs auto-proxying and the significance of `BeanPostProcessor` in Spring AOP. The content focuses on Spring beans, advisors, proxies, and processing timing; it does not re-present standalone AspectJ weaving theory.

## 2. When Does BeanPostProcessor Intervene?

Minimal interface:

~~~java
package org.springframework.beans.factory.config;

public interface BeanPostProcessor {
    default Object postProcessBeforeInitialization(Object bean, String beanName)
            throws org.springframework.beans.BeansException {
        return bean;
    }

    default Object postProcessAfterInitialization(Object bean, String beanName)
            throws org.springframework.beans.BeansException {
        return bean;
    }
}
~~~

The snippet above is an **illustration of the two important callbacks**, not a verbatim copy of Spring's source code and not a file to add to a project. Spring provides this interface out of the box. Each callback may return the same instance or a replacement instance; not every BPP creates a proxy.

In a typical bean creation flow, Spring proceeds roughly as follows:

~~~text
BeanDefinition registered in BeanFactory
        |
        v
Create target instance (constructor / factory method)
        |
        v
Populate dependencies / properties
        |
        v
BeanPostProcessor.postProcessBeforeInitialization(...)
        |
        v
Bean initialization: @PostConstruct, InitializingBean, init method
        |
        v
BeanPostProcessor.postProcessAfterInitialization(...)
        |
        |-- no advice needed --> return original bean
        |
        +-- matching advisor found --> return AOP proxy wrapping target
                                      |
                                      v
                     Container stores / provides bean reference
                                      |
                                      v
                        Caller -> proxy -> advice -> target
~~~

This is a **simplified standard model**, not a claim that every bean always goes through every branch in the exact same way. Spring has `InstantiationAwareBeanPostProcessor` and `SmartInstantiationAwareBeanPostProcessor` types that support earlier hooks; `FactoryBean`, lazy beans, and dependency cycles can cause the actual path to differ from the diagram. For the fundamentals, remember that **Spring AOP usually creates the proxy while processing the bean at the end of the initialization phase**, before normal callers receive that reference.

Common points of confusion:

- `BeanPostProcessor` processes **an already-created bean object**. `BeanFactoryPostProcessor`/`BeanDefinitionRegistryPostProcessor` process bean configuration/definitions before the instantiation phase. The auto-proxy system has a step that registers infrastructure definitions, but the operation of **wrapping an instance with a proxy** happens in the BPP.
- The `postProcessBeforeInitialization` callback is usually suitable for pre-init processing. Spring AOP's auto-proxy creator mainly uses `postProcessAfterInitialization` to return a proxy when it determines the bean needs advice.
- When a BPP returns a proxy, the bean in the container is consumed via the **proxy reference**; the target usually remains a separate object that the proxy delegates to. Therefore, `service.getClass()` may be a proxy class, and `service == target` is not a safe assumption.
- Returning `null` from a BPP callback does not mean "skip this bean"; in Spring's BPP processing flow, doing so can stop the processor chain at that stage. In custom BPPs, you normally **return `bean`** if no change is needed.

## 3. Auto-Proxy Creator: Spring AOP's Specialized BeanPostProcessor

With `@EnableAspectJAutoProxy`, Spring registers the auto-proxy creator infrastructure. A key implementation is `org.springframework.aop.aspectj.annotation.AnnotationAwareAspectJAutoProxyCreator`, which extends the `AbstractAutoProxyCreator` hierarchy and implements the `SmartInstantiationAwareBeanPostProcessor` interface (an extension of `BeanPostProcessor`).

In Spring AOP using the `@AspectJ` declaration style, the auto-proxy creator performs the following tasks:

1. **Identify aspects/advisors:** retrieves Spring `Advisor` beans and converts advice declared with `@Aspect`, `@Before`, `@Around`, etc. from aspect beans into advisors that Spring AOP can use.
2. **Determine which beans need proxying:** inspects each eligible bean, matching candidate advisors/pointcuts against the bean type and the method join points supported by Spring AOP. A bean with no applicable advisor is usually left as-is.
3. **Skip infrastructure classes:** avoids proxying internal AOP components, unsuitable advisors/advice/aspects, or beans excluded by processing rules. Having `@EnableAspectJAutoProxy` does **not** mean **every** bean gets wrapped.
4. **Create a proxy with appropriate advisors:** uses Spring's proxy mechanism (JDK dynamic proxy or CGLIB class proxy, depending on configuration and target type). The proxy holds how advice is dispatched for method calls.
5. **Return the proxy instead of the target** through the `BeanPostProcessor` path (usually `postProcessAfterInitialization`). The Spring container and dependency injection will supply the processed reference to other beans.

### Useful Class Hierarchy When Reading Spring Source Code

~~~text
BeanPostProcessor
        ^
SmartInstantiationAwareBeanPostProcessor
        ^
AbstractAutoProxyCreator
        ^
AbstractAdvisorAutoProxyCreator
        ^
AspectJAwareAdvisorAutoProxyCreator
        ^
AnnotationAwareAspectJAutoProxyCreator
~~~

The arrows show extension/implementation relationships for architectural explanation; `AnnotationAwareAspectJAutoProxyCreator` is the Spring class that supports `@AspectJ`-style aspects. From an internal method perspective, pay attention to:

- `AbstractAutoProxyCreator.postProcessAfterInitialization(...)`: the post-initialization processing point that may wrap a bean with a proxy.
- `wrapIfNecessary(...)`: checks whether a bean needs a proxy created.
- `getAdvicesAndAdvisorsForBean(...)` and the advisor-lookup methods in the `AbstractAdvisorAutoProxyCreator` hierarchy: select applicable advice/advisors.
- `createProxy(...)`: creates the AOP proxy with the selected configuration and advisors.
- `getEarlyBeanReference(...)`: early reference processing path for certain circular-dependency situations; see the notes below.

These method names are for **reading/debugging the framework**, not APIs that a normal application needs to call or override. You should not subclass `AbstractAutoProxyCreator` yourself just to enable a simple `@Before` advice.

## 4. From @EnableAspectJAutoProxy to Runtime Invocation

Configuration registration:

~~~java
@Configuration
@EnableAspectJAutoProxy
class AopConfig {
}
~~~

In Java configuration, `@EnableAspectJAutoProxy` uses Spring's import/registrar mechanism to register the auto-proxy creator. When the container prepares BeanPostProcessors, the auto-proxy creator is managed as a specialized processor. The aspect must also exist in the `ApplicationContext` as a bean, for example via `@Component` (with component scanning) or `@Bean`. **Simply adding `@Aspect` to a class does not automatically register a bean.**

Then:

~~~text
@EnableAspectJAutoProxy
   |
   +--> registers auto-proxy creator in Spring context
                      |
       checkoutService bean is initialized
                      |
                      v
          BeanPostProcessor chain
                      |
                      v
          Evaluate matching Advisors
                      |
                  +---+---+
                  |       |
                Yes      No
                  |       |
               Proxy     Original target
                  |
               Container hands proxy to caller
                  |
             caller.checkout()
                  |
              interceptor chain
                  |
              @Before advice
                  |
              target.checkout()
~~~

Two **points in time** must be separated:

- **At bean creation time:** the BPP decides which wrapper to create for Spring to provide to callers.
- **At method invocation time through the proxy:** interceptors/advice inside the wrapper execute at matching join points. The BPP **does not need to run again every time a method is called**. If a singleton service is called 1,000 times, do not assume the BPP also wraps the service 1,000 times.

A proxy from Spring AOP does not transform the service's bytecode into advice code like AspectJ weaving; method invocations go through the proxy object. This explains why `this.otherMethod()` called directly on the target can bypass advice on internal methods.

## 5. Java 17+ Project to Observe BeanPostProcessor and Proxy

Standalone runnable example using **Spring Framework 6.2.0, AspectJ Weaver 1.9.22, Maven, and Java 17+**. The project only initializes an `ApplicationContext`, does not use Spring Boot, and does not enable weaving.

Structure:

~~~text
spring-auto-proxy-bpp/
├── pom.xml
└── src/main/java/example/
    ├── App.java
    ├── CheckoutService.java
    └── AuditAspect.java
~~~

Create `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-auto-proxy-bpp</artifactId>
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

`spring-context` contains the lifecycle/container, `spring-aop` contains the AOP/proxy infrastructure and `AopUtils`. `aspectjweaver` provides the AspectJ types used to parse `@AspectJ` pointcuts in Spring AOP. **This dependency does not automatically activate AspectJ bytecode weaving.**

### 5.1. CheckoutService with a Clear Init Step

Create `src/main/java/example/CheckoutService.java`:

~~~java
package example;

import org.springframework.beans.factory.InitializingBean;

public class CheckoutService implements InitializingBean {
    @Override
    public void afterPropertiesSet() {
        System.out.println("INIT: checkoutService");
    }

    public void checkout() {
        System.out.println("TARGET: checkout");
    }
}
~~~

`afterPropertiesSet()` is a lifecycle callback run after dependencies/properties have been attached to the bean. The `INIT` line lets you see the boundary between the BeanPostProcessor phases. `checkout()` is the business method to be advised, not an init method.

### 5.2. Aspect That Runs When Calling checkout Through the Proxy

Create `src/main/java/example/AuditAspect.java`:

~~~java
package example;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class AuditAspect {
    @Before("execution(* example.CheckoutService.checkout(..))")
    public void beforeCheckout() {
        System.out.println("ADVICE: before checkout");
    }
}
~~~

Spring uses `@Aspect`/`@Before` to create an advisor. `execution(* example.CheckoutService.checkout(..))` matches the **method execution** of `checkout`. The aspect only runs when a call through the Spring AOP proxy matches that advisor; not because the observing BeanPostProcessor invokes the advice itself.

### 5.3. Configuring Two Different Kinds of BeanPostProcessor

Create `src/main/java/example/App.java`:

~~~java
package example;

import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.config.BeanPostProcessor;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class App {
    @Bean
    public CheckoutService checkoutService() {
        return new CheckoutService();
    }

    @Bean
    public AuditAspect auditAspect() {
        return new AuditAspect();
    }

    @Bean
    public static BeanPostProcessor lifecycleObserver() {
        return new BeanPostProcessor() {
            @Override
            public Object postProcessBeforeInitialization(
                    Object bean, String beanName) {
                if ("checkoutService".equals(beanName)) {
                    System.out.println("BPP_BEFORE: checkoutService");
                }
                return bean;
            }

            @Override
            public Object postProcessAfterInitialization(
                    Object bean, String beanName) {
                if ("checkoutService".equals(beanName)) {
                    System.out.println("BPP_AFTER: checkoutService");
                }
                return bean;
            }
        };
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(App.class)) {
            CheckoutService service = context.getBean(CheckoutService.class);
            System.out.println("PROXY: " + AopUtils.isAopProxy(service));
            service.checkout();
        }
    }
}
~~~

In the same `ApplicationContext`, there are two types of processors with **different** roles:

1. `lifecycleObserver()` returns a **BPP we wrote** to print lifecycle milestones. It returns the original `bean` in both callbacks and **does not create a proxy itself**. Because Spring's `ApplicationContext` detects `BeanPostProcessor` beans and invokes them during the creation of eligible beans, the observer sees the initialization process of `checkoutService`.
2. `@EnableAspectJAutoProxy` registers **Spring's internal auto-proxy creator**, which is also a BeanPostProcessor. This processor finds the advisor generated from `AuditAspect` and wraps `CheckoutService` with an AOP proxy when there is a matching method.

Make the custom BPP `@Bean` **`public static`, with no dependencies**, so Spring detects and registers it early without having to instantiate the configuration class prematurely. This is an important practice: BPPs need to be active early enough to process beans created after them. Declaring a BPP with `@Bean` having return type `BeanPostProcessor` (or the implementation class) helps the container recognize it properly.

In the example, `proxyTargetClass = true` selects a **class-based proxy** (CGLIB), so `context.getBean(CheckoutService.class)` returns a type assignable to `CheckoutService`. The `proxyBeanMethods = false` attribute on `@Configuration` only determines how `@Bean` methods on the configuration class are processed; it **does not disable AOP auto-proxying**.

### 5.4. Running and Explaining stdout

In the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java
~~~

The lines produced by the program:

~~~text
BPP_BEFORE: checkoutService
INIT: checkoutService
BPP_AFTER: checkoutService
PROXY: true
ADVICE: before checkout
TARGET: checkout
~~~

Other Maven/logger messages, if any, are not part of the six lines from the example code. The order above reflects the lifecycle of `CheckoutService` in the given project:

- `BPP_BEFORE`: the observer's `postProcessBeforeInitialization` callback runs before `afterPropertiesSet()`.
- `INIT`: Spring executes the service's initialization callback.
- `BPP_AFTER`: the observer's `postProcessAfterInitialization` callback runs after the initialization callback. **This line alone does not prove the bean has already been wrapped**: the observer only prints the bean name and returns the object it received.
- `PROXY: true`: the reference Spring hands to the caller is a Spring AOP proxy, created by the internal auto-proxy creator when an advisor matches.
- `ADVICE` before `TARGET`: the call goes through the proxy, triggers `@Before`, and then forwards to `checkout()` on the service.

Note: **do not infer the type of the object inside each BPP callback solely from log names**. BeanPostProcessors have different processing orders; a custom BPP may observe the target or the wrapper depending on timing and execution order. `AopUtils.isAopProxy(context.getBean(...))` in `main` directly measures the **final reference** Spring supplies to the caller.

## 6. Why Does "Wrapping with a Proxy" Change Caller Behavior?

When the auto-proxy creator finds an applicable advisor, conceptually it returns a wrapper:

~~~text
Before auto-proxying:
caller --> CheckoutService.checkout()

After auto-proxying:
caller --> CheckoutServiceProxy.checkout()
                 |
                 +--> AuditAspect.beforeCheckout()
                 |
                 +--> CheckoutService.checkout()
~~~

There is no need to modify the `CheckoutService` class to insert a call to `AuditAspect.beforeCheckout()`. Other beans in Spring injected with the service normally receive the reference published by the container, which is the proxy if one was created.

Important consequences:

- **Not every bean is a proxy:** if no pointcut matches or no advisor applies, the auto-proxy creator can return the target. `@EnableAspectJAutoProxy` only enables the evaluation/proxying mechanism.
- **Not every call goes through the proxy:** `this.checkout()` inside the target is a self-invocation; internal calls can bypass advice. Separating the responsibility into another bean to call through a Spring reference is a usually easy-to-understand way to handle this.
- **Not every method can be intercepted:** class-based proxies cannot override `final`/`private` methods or `final` classes. With JDK proxies, callers interact through the proxy's interfaces; the choice of proxy type directly affects which methods are exposed.
- **Initialization is not a business invocation through the proxy:** init callbacks usually run on the target during bean creation before the final proxy bean is published; do not treat `@Before` not running for a method called during init as proof that Spring AOP is broken.
- **Not AOP weaving:** Spring creates a proxy object; AspectJ compile/load-time weaving modifies bytecode with its own tooling. The `@Aspect`/`@Before` syntax does not turn Spring auto-proxying into weaving.

## 7. Cases Where BPP Does Not Apply as Expected

### 7.1. BPP Registered Too Late or Creating Early Dependencies

`ApplicationContext` proactively finds and instantiates BPPs during a special phase before many regular beans are created. BPPs themselves, along with beans they pull into premature initialization, **cannot by default benefit from the full BPP chain** and may not be eligible for auto-proxying. Spring logs a warning such as:

~~~text
Bean '...' is not eligible for getting processed by all BeanPostProcessors
(for example: not eligible for auto-proxying)
~~~

If you encounter this warning:

1. Check whether application-declared BPPs are created **early** via a static `@Bean` with a recognizable BPP return type.
2. Avoid injecting heavy business services or creating large dependency graphs in the BPP's constructor/factory method itself; those dependencies may be initialized before the auto-proxy creator is ready.
3. Do not call `getBean()` yourself to initialize batches of services while registering a BPP. Let the container complete the initialization phase properly.

Do not try to advise a `BeanPostProcessor` itself and conclude Spring AOP is broken when it does not receive a proxy like a normal business bean.

### 7.2. Proxy Appearing Early to Support Circular References

`AbstractAutoProxyCreator` is a `SmartInstantiationAwareBeanPostProcessor` and has `getEarlyBeanReference(...)` so Spring can hand out a **wrapped reference** early in certain circular-dependency processing paths. This helps avoid one bean receiving the raw target while another caller later receives a proxy.

However, **do not rely on circular dependencies as a design pattern**. Constructor cycles usually cannot be resolved this way; in Spring Boot many configurations even reject circular references by default. Refactoring the dependency cycle is the sustainable solution. Do not assume a BPP is always called exactly once on every bean or that calling early callbacks will always succeed.

### 7.3. Multiple Contexts and Multiple Auto-Proxy Settings

BPPs are scoped per **container**. A BPP registered in one `ApplicationContext` does not automatically become a post-processor for beans belonging to another context, especially in parent/child models. When advice does not run on a bean created by a child context, check whether the auto-proxy creator and the aspect are registered in the right context containing the bean.

AOP/transaction auto-proxy declarations can be merged by Spring into a single auto-proxy creator and apply the stronger proxy settings when configurations overlap. Do not assume that two annotations guarantee two independent proxy layers. Check the actual proxy via `AopUtils.isAopProxy(...)` and its advisors if needed.

### 7.4. Writing a Custom BPP to Proxy Every Bean

Do not replace `AnnotationAwareAspectJAutoProxyCreator` with a custom BPP just to do logging or ordinary method advice. Creating duplicate proxies yourself easily causes double wrapping, alters advice ordering, disrupts the lifecycle, and breaks transaction/cache behavior. When the goal is Spring AOP, declare an `@Aspect`/advisor and let Spring's infrastructure handle proxy creation.

## 8. Quick Comparison of Related Components

| Component | What does it process? | Role in Spring AOP |
| --- | --- | --- |
| `BeanDefinitionRegistryPostProcessor` | Bean registry/definitions | Can participate in registering additional bean definitions before instantiation |
| `BeanFactoryPostProcessor` | BeanFactory configuration/metadata | Modifies definitions; not the step that wraps individual instances with proxies |
| `BeanPostProcessor` | Bean instances around init callbacks | Extension point allowing a wrapper/proxy to be returned instead of the bean |
| `SmartInstantiationAwareBeanPostProcessor` | Adds early hooks into instantiation | Gives the auto-proxy creator the ability to provide an early proxy reference in some cases |
| `AnnotationAwareAspectJAutoProxyCreator` | Beans matching Advisors/`@AspectJ` | Concrete BPP that finds advisors, selects beans, and creates AOP proxies |
| `Advisor` / `Pointcut` / `Advice` | Join point selection criteria and execution logic | Placed into the proxy's interceptor chain by the auto-proxy creator |
| JDK dynamic proxy / CGLIB | Runtime wrapper | Mechanism for executing method calls through the proxy |
| `@EnableAspectJAutoProxy` | Configuration enabling `@AspectJ`-style AOP support | Registers the auto-proxy infrastructure for the configured context |

## 9. Diagnosing When a Service Does Not Receive an AOP Proxy

A practical checklist order:

1. **Is it actually a Spring bean?** `new CheckoutService()` does not go through the container's `BeanPostProcessor`s. Retrieve the bean from the context that owns the service.
2. **Is the auto-proxy creator enabled?** Verify `@EnableAspectJAutoProxy` is in a loaded configuration or that Boot AOP auto-configuration is active.
3. **Is the aspect a bean?** `@Aspect` is not enough if Spring does not register the aspect class as a bean.
4. **Does the advisor match the method?** The `execution(...)` pointcut must match the actual method's type and signature. Without a match, the service can be left as-is, not necessarily proxied.
5. **Was the BPP initialized too late?** Look for the log "not eligible for auto-proxying", a BPP declared via a non-static `@Bean`, or a BPP injecting too many services early.
6. **Does the call go through the proxy?** The proxy exists, but self-invocation or an object outside the container will not trigger advice like a cross-bean call.
7. **Is the proxy type appropriate?** Check interface/JDK proxy, CGLIB class proxy, `final` class/method, visibility, and the injected bean type.
8. **Are multiple BPPs/proxies/contexts overlapping?** Check where the aspect and advisor are defined and the BPP order. A custom BPP must return the received object or a valid wrapper.

For a quick check in an application that already has a Spring container:

~~~java
Object bean = context.getBean("checkoutService");
System.out.println(org.springframework.aop.support.AopUtils.isAopProxy(bean));
System.out.println(org.springframework.aop.support.AopUtils.isJdkDynamicProxy(bean));
System.out.println(org.springframework.aop.support.AopUtils.isCglibProxy(bean));
~~~

This is a **snippet to insert into a program that already has a `context` variable**, not a standalone Java file; with the example in section 5, it returns `true`, `false`, `true` in that order when class-based proxying is configured as shown. If `isAopProxy` is `false`, check the proxy/advisor conditions as well before blaming the BPP.

## 10. Self-Check Questions

1. **What does BeanPostProcessor change?** — It processes bean instances; it can return a wrapper instead of the original instance after initialization.
2. **Which BPP does Spring AOP rely on to automatically create proxies for `@AspectJ`?** — The auto-proxy creator family, typically `AnnotationAwareAspectJAutoProxyCreator`.
3. **Does `@EnableAspectJAutoProxy` turn every bean into a proxy?** — No. A bean must match an advisor and the proxy mechanism.
4. **Why is `BPP_AFTER` not equivalent to `ADVICE`?** — BPP runs during the bean-creation lifecycle, whereas advice runs when a method call through the proxy matches a pointcut.
5. **Why is `@Bean static BeanPostProcessor` important?** — It helps Spring detect and initialize the BPP early enough while avoiding premature instantiation of configuration/dependencies.
6. **If a proxy exists, why might `this.checkout()` not run advice?** — Internal calls bypass the Spring AOP wrapper.
7. **When should you avoid modifying the core auto-proxy creator?** — When the requirement is just ordinary logging/audit/transaction logic, use standard aspects/advisors and let Spring manage proxying.

## Spring Framework Reference Documentation

- [Container Extension Points — BeanPostProcessor](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-extension.html): BPP lifecycle and auto-proxy eligibility notes.
- [Using the auto-proxy facility](https://docs.spring.io/spring-framework/reference/6.2/core/aop-api/autoproxy.html): auto-proxy creators in Spring AOP.
- [Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html): how to enable auto-proxying for aspects.
- [Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): JDK proxies, CGLIB, and self-invocation limitations.
- [AnnotationAwareAspectJAutoProxyCreator API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/aop/aspectj/annotation/AnnotationAwareAspectJAutoProxyCreator.html) and [AbstractAutoProxyCreator API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/aop/framework/autoproxy/AbstractAutoProxyCreator.html): infrastructure classes/callbacks.
