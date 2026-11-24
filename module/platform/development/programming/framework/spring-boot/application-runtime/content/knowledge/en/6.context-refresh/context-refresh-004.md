# Registering BeanPostProcessors Before Regular Beans in Spring Boot

## 1. Purpose and Significance

When Spring Boot starts up, the `ApplicationContext` cannot arbitrarily instantiate all beans as soon as it reads their definitions. Before instantiating most regular singleton beans, the container must register **`BeanPostProcessor` (BPP)** instances: components that intervene in the bean creation and initialization lifecycle. If a regular bean is created too early, it may miss processing by certain post-processors, such as proxy-creation mechanisms associated with Spring AOP.

**`BeanPostProcessor`** is a Spring IoC extension interface with two classic hooks:

- `postProcessBeforeInitialization(Object bean, String beanName)`: processes the bean after creation and assignment of required dependencies/properties, before standard initialization callbacks.
- `postProcessAfterInitialization(Object bean, String beanName)`: processes the bean after initialization callbacks; it may return the bean itself or a replacement wrapper/proxy object.

Some Spring infrastructure BPPs provide additional specialized processing through extended interfaces, so these two hooks are the basic entry points rather than the totality of extension steps that may exist.

**Why must they be registered early?** The container can only apply post-processors that have already been registered at the time a bean is created. Therefore, the standard order is: prepare bean metadata and configuration, discover/instantiate/register BPPs, and only then mass-instantiate regular singletons.

This is a **relative ordering within the `ApplicationContext` lifecycle**. It does not mean "zero beans are created before BPPs are registered": the post-processors themselves, their essential dependencies, and certain infrastructure beans may need to be instantiated early.

## 2. Placing BPP Registration Inside ApplicationContext.refresh()

Core Spring Framework executes `AbstractApplicationContext.refresh()`. At a high level, the key sequence is:

~~~text
SpringApplication.run(...)
  |
  v
ApplicationContext.refresh()
  |
  +-- prepareRefresh()
  +-- obtainFreshBeanFactory()
  +-- prepareBeanFactory(beanFactory)
  +-- postProcessBeanFactory(beanFactory)
  |
  +-- invokeBeanFactoryPostProcessors(beanFactory)
  |     -> process bean definitions / metadata
  |     -> may add or modify bean definitions
  |
  +-- registerBeanPostProcessors(beanFactory)      [KEY FOCUS]
  |     -> find BeanPostProcessors by type
  |     -> instantiate required BPPs
  |     -> sort and register into BeanFactory
  |
  +-- initMessageSource()
  +-- initApplicationEventMulticaster()
  +-- onRefresh()
  +-- registerListeners()
  |
  +-- finishBeanFactoryInitialization(beanFactory)
  |     -> preInstantiateSingletons()
  |     -> instantiate most regular, non-lazy singletons
  |     -> invoke the BPP chain as these beans initialize
  |
  +-- finishRefresh()
  |
  v
Context refresh complete
~~~

Method names reflect actual steps in Spring Framework; the diagram omits certain internal activities and does not represent every detail of every version or every web context type.

Two points to remember:

1. **`invokeBeanFactoryPostProcessors(...)` precedes `registerBeanPostProcessors(...)`.** Factory post-processors need to adjust or add definitions before Spring detects BPPs based on the final definitions.
2. **`registerBeanPostProcessors(...)` precedes `finishBeanFactoryInitialization(...)`.** That way, regular singletons created during `preInstantiateSingletons()` pass through the BPPs already present in the BeanFactory.

In Spring Boot, the `@SpringBootApplication` class and auto-configuration contribute many bean definitions, but **the BPP registration mechanism belongs to core Spring Framework**. It is not limited to web applications or one specific Spring Boot version.

### Registering BPPs Is Not the Same as Creating Regular Beans

You can visualize two separate paths:

~~~text
Bean definitions exist in the registry
       |
       +--> Discover and construct BPPs
       |    then add to BeanFactory
       |
       +--> Initialize regular beans
            +--> constructor/factory method
            +--> dependency injection
            +--> postProcessBeforeInitialization(...)
            +--> init callbacks
            +--> postProcessAfterInitialization(...)
            +--> bean enters use (possibly as a proxy)
~~~

**`BeanDefinition` is metadata**, not an instance. Spring can know a bean's name, type, scope, and factory method ahead of time without constructing business objects yet. The BPP registration step relies on looking up these special definitions by type, then instantiating the BPPs and adding them to the factory's processor list.

## 3. How Does a BeanPostProcessor Work When Initializing a Bean?

Suppose an `invoiceService` bean is created after BPPs have been registered. The typical flow:

~~~text
BeanFactory needs bean "invoiceService"
  |
  +-- Resolve BeanDefinition
  +-- Create instance via constructor or @Bean method
  +-- Assign dependencies and required properties
  |
  +-- BeanPostProcessors called in the before-init phase
  |     postProcessBeforeInitialization(bean, "invoiceService")
  |
  +-- Invoke appropriate init callbacks
  |     e.g., InitializingBean.afterPropertiesSet()
  |     and initMethod on @Bean
  |
  +-- BeanPostProcessors called in the after-init phase
  |     postProcessAfterInitialization(bean, "invoiceService")
  |
  +-- Publish the final object to consumers
        (may be a proxy/wrapper)
~~~

This is the general flow for a Spring-managed bean; the actual lifecycle includes additional steps such as `BeanNameAware`, `BeanFactoryAware`, constructor resolution mechanisms, infrastructure BPPs, and other callbacks. `@PostConstruct` is also handled by a Spring post-processor, so do not deduce the ordering of **all** BPPs from this diagram alone. With a simple `@Bean(initMethod = "...")`, you can clearly observe the three checkpoints: before → init method → after.

**Both hooks return `Object`.** A BPP can return the bean as-is or a replacement object. A classic example is an AOP BPP returning a proxy so callers invoke through the proxy rather than calling the target object directly. When writing a custom BPP, be careful about types, lifecycle, compatibility, and proxy awareness. If you only log for observation, simply `return bean;`.

**BPPs only process instances created/managed by Spring within the corresponding lifecycle.** If an application manually calls `new InvoiceService()` outside the container, do not expect that object to receive the same processing chain. A BPP is scoped to **a single BeanFactory/ApplicationContext**, and does not automatically propagate across all other contexts in a system.

## 4. Mechanism for Discovering and Registering BeanPostProcessors

### 4.1. ApplicationContext Auto-Detects BPPs

In a standard `ApplicationContext`, Spring locates bean definitions recognized as `BeanPostProcessor`, instantiates the required BPPs, and registers them. Developers can provide BPPs in two common ways:

**Approach A — using @Component:**

~~~java
@Component
public class SampleProcessor implements BeanPostProcessor {
    @Override
    public Object postProcessAfterInitialization(Object bean, String beanName) {
        return bean;
    }
}
~~~

This is an **illustrative snippet, not a standalone Java file**; you need to import `org.springframework.stereotype.Component` and `org.springframework.beans.factory.config.BeanPostProcessor`, and the class must lie within an appropriate scan scope. Spring detects the BPP type from the component definition.

**Approach B — using @Bean with an explicit return type:**

~~~java
@Configuration
public class ProcessorConfig {

    @Bean
    public static SampleProcessor sampleProcessor() {
        return new SampleProcessor();
    }
}
~~~

This is an **illustrative configuration snippet**, requiring imports for `@Configuration`, `@Bean`, and the declared `SampleProcessor` class. The method can return the concrete implementation class or at least the `BeanPostProcessor` type.

For BPPs declared via `@Bean`, Spring recommends making the method **`static` and ideally free of dependencies on other beans**. Because BPPs must be created early, `static` lets Spring invoke the factory method without forcing early instantiation of the `@Configuration` class itself. If the method is non-static, the config class itself and its dependencies risk being constructed before the post-processing system is complete.

### 4.2. The Return Type of @Bean Matters Greatly

Example to avoid:

~~~java
@Bean
public static Object processor() {
    return new SampleProcessor();
}
~~~

This is only an illustrative snippet to **identify a mistake**, not a recommended configuration. Declaring the return type as `Object` hides the `BeanPostProcessor` type during early type-detection. Spring cannot reliably invoke factory methods to discover special types without breaking initialization order; as a result, the BPP may not be autodetected in time.

Prefer:

~~~java
@Bean
public static BeanPostProcessor processor() {
    return new SampleProcessor();
}
~~~

Or return the concrete `SampleProcessor`. Place the method in a loaded `@Configuration` class, make it `static`, declare an explicit type, and avoid unnecessary dependencies.

### 4.3. Ordering Multiple BPPs

Spring can register many BPPs: some provided by the framework, others defined by libraries and the application. Auto-detected BPPs in an `ApplicationContext` follow a priority mechanism:

1. BPPs implementing `PriorityOrdered`.
2. Remaining BPPs implementing `Ordered`.
3. BPPs without explicit ordering, following container rules.

A smaller `getOrder()` value indicates higher priority when compared within the same ordering mechanism. **Do not rely on contractually unguaranteed ordering among BPPs of equal rank.** In particular, the `@Order` annotation **is not how BPP ordering is applied** as it is for some other extension types; to control ordering of autodetected BPPs, implement `Ordered`/`PriorityOrdered`.

There is one separate case: **BPPs registered manually via `ConfigurableBeanFactory.addBeanPostProcessor(...)`** run in **manual registration order**, ignoring `Ordered` on the object itself; under Spring's mechanism, manually registered processors are applied before autodetected ones. The manual approach is appropriate when directly bootstrapping a `BeanFactory` or needing special conditional logic, whereas most Spring Boot applications simply let `ApplicationContext` autodetect them.

Note: a standalone `BeanFactory` lacks the full automatic extension-point detection/registration mechanism of `ApplicationContext`. Creating beans directly from an under-bootstrapped factory may omit BPPs you assumed were present.

## 5. Runnable Java 17+ Example: Proving Registration Before Regular Beans

The example uses Spring Boot without opening an HTTP server; thanks to `WebApplicationType.NONE` we focus on bean creation order. A `BeanPostProcessor` is declared with **`static @Bean` and no dependencies**, and observes the lifecycle of a regular service with an init method.

### 5.1. Initializing the Project

Visit [Spring Initializr](https://start.spring.io/), choose Maven, Java 17 or a compatible newer JDK, a stable Spring Boot version, group `com.example`, artifact `bpp-demo`, package `com.example.bppdemo`, and the **Spring Boot Starter** dependency (or generate a basic project and add `spring-boot-starter` matching the Boot version generated by Initializr). Initializr's Maven project already includes build configuration and the Maven Wrapper, so you do not need to guess dependency versions.

Create or replace the contents of the file:

~~~text
src/main/java/com/example/bppdemo/BppDemoApplication.java
~~~

### 5.2. Complete Java File

~~~java
package com.example.bppdemo;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.beans.factory.config.BeanPostProcessor;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class BppDemoApplication {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(BppDemoApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.run(args);
    }

    // BeanPostProcessor must be constructed early.
    // static avoids forcing Spring to construct the config instance too early.
    @Bean
    public static TraceProcessor traceProcessor() {
        System.out.println("REGISTER_PROCESSOR");
        return new TraceProcessor();
    }

    // Business bean created during the normal singleton phase.
    @Bean(initMethod = "initialize")
    public GreetingService greetingService() {
        return new GreetingService();
    }

    // Runner uses the bean after the initialization chain completes.
    @Bean
    public ApplicationRunner runner(GreetingService service) {
        return args -> System.out.println("RUNNER_RESULT=" + service.greet());
    }

    public static class GreetingService {
        public GreetingService() {
            System.out.println("SERVICE_CONSTRUCTOR");
        }

        public void initialize() {
            System.out.println("SERVICE_INITIALIZE");
        }

        public String greet() {
            return "Hello BPP";
        }
    }

    public static class TraceProcessor implements BeanPostProcessor {
        @Override
        public Object postProcessBeforeInitialization(
                Object bean, String beanName) {

            if ("greetingService".equals(beanName)) {
                System.out.println("BPP_BEFORE_INIT");
            }
            return bean;
        }

        @Override
        public Object postProcessAfterInitialization(
                Object bean, String beanName) {

            if ("greetingService".equals(beanName)) {
                System.out.println("BPP_AFTER_INIT");
            }
            return bean;
        }
    }
}
~~~

**Why can this example run?** `@SpringBootApplication` is a configuration source; Spring finds the `static @Bean` method with return type `TraceProcessor`, a class implementing `BeanPostProcessor`. This bean is prepared during the BPP registration phase. When `greetingService` is created afterward, the BPP observes both bean callbacks. `@Bean(initMethod = "initialize")` gives us a clear init callback without requiring extra `@PostConstruct` libraries.

The example only observes the bean named `greetingService`, avoiding printing events from numerous Spring infrastructure beans.

### 5.3. Run Command and Output

From the project root directory:

~~~bash
# Linux/macOS
./mvnw spring-boot:run
~~~

~~~powershell
# Windows PowerShell
.\mvnw.cmd spring-boot:run
~~~

Aside from banners/logs depending on version and environment, the lines printed by the example code itself appear in order:

~~~text
REGISTER_PROCESSOR
SERVICE_CONSTRUCTOR
BPP_BEFORE_INIT
SERVICE_INITIALIZE
BPP_AFTER_INIT
RUNNER_RESULT=Hello BPP
~~~

The lines may be interleaved with logs from Spring Boot or other libraries, so they **do not have to appear consecutively** across stdout. The order of the lines printed by the example is what to verify.

Analyzing each milestone:

1. **`REGISTER_PROCESSOR`**: the factory method creating `TraceProcessor` is called early in refresh, before the sample business singleton is constructed.
2. **`SERVICE_CONSTRUCTOR`**: the container creates the `GreetingService` instance from `@Bean`. At this point, the init method has not run yet.
3. **`BPP_BEFORE_INIT`**: the registered BPP receives its callback before the initialization step specified by `initMethod`.
4. **`SERVICE_INITIALIZE`**: Spring invokes the bean's init method per metadata.
5. **`BPP_AFTER_INIT`**: the BPP receives its callback after the init method; in the example it returns the original object unchanged.
6. **`RUNNER_RESULT=Hello BPP`**: after refresh, Spring Boot runs the `ApplicationRunner` using the service created and initialized by the container.

If you remove `static` from `traceProcessor()`, the configuration class can be instantiated early, pulling in unwanted lifecycle effects. **Do not treat a simple run that happens to print all logs as proof that a non-static configuration is always safe**: the larger problem involves other beans/dependencies that may be created early and miss infrastructure post-processors, especially auto-proxying.

If you want to verify that the BPP is applied to another bean, add a Spring-managed service inside the application's package and adjust the `beanName` filter accordingly. Do not use `new GreetingService()` from `main()` to test the BPP, because manually created objects are outside the container lifecycle.

## 6. What Happens If a Bean Is Created Too Early?

While registering BPPs, the BPP objects themselves must be created. If a BPP takes a regular business bean via a constructor or factory-method dependency, Spring may have to instantiate that bean **before all other BPPs finish registering**:

~~~java
@Bean
public static BeanPostProcessor riskyProcessor(
        ImportantBusinessService service) {
    return new MyProcessor(service);
}
~~~

This is a **risk illustration snippet**, not standalone code. `ImportantBusinessService` and `MyProcessor` stand for application-specific bean types. Calling the factory method requires an `ImportantBusinessService` instance before creating the BPP, so that service may appear while post-processors are still incomplete.

Consequences:

- The early-created bean can still be managed by Spring, but **is not eligible to be processed by all BPPs** registered after it was created.
- If a BPP-based AOP proxy has not been registered yet, that bean may fail to receive the expected proxy. This can break proxy-based features like transactions or aspects, depending on configuration.
- Spring often logs a warning like **`Bean '...' is not eligible for getting processed by all BeanPostProcessors (for example: not eligible for auto-proxying)`**. Such warnings must be evaluated by bean type: not every infrastructure bean needs proxying, but business beans requiring AOP deserve careful inspection.
- Already-created beans are not automatically re-initialized from scratch to "catch up" on later BPPs.

### How to Avoid Early Bean Instantiation

1. **Register BPPs using `static @Bean`** with a clear return type (`BeanPostProcessor` or a concrete subclass).
2. **Prefer BPPs without business dependencies**. If configuration is needed, consider passing simple data rather than injecting a complex service.
3. **Avoid calling `getBean()` or `getBeansOfType()` too early** in extension points working with bean definitions, if that operation forces creation of regular beans. Use them only when you truly understand the lifecycle limits.
4. **Do not use BPPs as a place for arbitrary business initialization**. A BPP can be applied to many beans; side effects such as HTTP calls, database queries, or circular dependencies easily cause startup failures.
5. **Focus on warnings for the right beans**; check whether the bean needs `@Transactional`, `@Async`, or another aspect, and which BPP might have been registered late.
6. **Do not try to "fix" it by blindly forcing creation order with `@DependsOn`**. Dependency constraints can force even more beans to be constructed early, making the problem worse.

**Key emphasis:** BPPs themselves and the beans they directly depend on are created during this special phase, so do not expect them to receive full auto-proxying. This is a lifecycle characteristic, not proof that every printed warning is a business bug.

## 7. Distinguishing BeanPostProcessor from BeanFactoryPostProcessor

Their names are similar, but the two processor types work at **two different layers**:

| Criterion | `BeanFactoryPostProcessor` (BFPP) | `BeanPostProcessor` (BPP) |
| --- | --- | --- |
| Primary target | `BeanDefinition`, metadata, and bean factory configuration | Bean instance during initialization |
| Timing in refresh | `invokeBeanFactoryPostProcessors(...)` | `registerBeanPostProcessors(...)`, then invoked when beans are created |
| Purpose | Modify/add metadata before most beans are created | Add pre/post-init processing, optionally wrap in a proxy |
| Typical methods | `postProcessBeanFactory(ConfigurableListableBeanFactory)` | `postProcessBeforeInitialization(...)`, `postProcessAfterInitialization(...)` |
| Misuse risk | Calling `getBean()` too early, breaking definition → instance order | Pulling business dependencies into early registration, missing some BPPs |

`BeanDefinitionRegistryPostProcessor` is a specialized variant for modifying the bean definition registry even earlier. It fits when you need to add definitions before Spring builds the corresponding instances. In this lesson, the core takeaway is that **BFPP acts on metadata beforehand; BPP is registered to act on instances afterward**.

For example, a BFPP should not call `beanFactory.getBean("invoiceService")` just to set a field on the service: that turns a metadata problem into premature instantiation. If you need to intervene in a created object, use an appropriate extension point in the bean-processing phase instead of forcing the container out of sequence.

## 8. How Do BPPs Relate to Auto-Proxying and Spring Annotations?

Several Spring mechanisms rely on post-processing to complete bean behavior. For example, Spring AOP uses BPP/auto-proxy creators in its infrastructure to detect beans needing proxies and return appropriate proxy objects.

When a service has proxy-based transactional logic:

~~~java
@Service
public class PaymentService {

    @Transactional
    public void pay() {
        // Business operation
    }
}
~~~

This is an **illustration, not a standalone program**; it requires appropriate imports, transaction dependencies, and transaction manager configuration. A class with `@Transactional` alone does not guarantee transactions work if the infrastructure is not enabled.

During initialization, auto-proxy infrastructure may decide to return a proxy for `PaymentService`. If the bean was created too early, before the relevant processor was registered, the opportunity to apply the full proxy may be missed. As a result, a bean can exist and behave like a plain Java object, yet external calls through the container lack the expected proxy behavior.

Distinguish two separate things clearly:

- **Registering a bean definition** for a service only tells Spring the service needs to be created; it does not ensure a proxy exists yet.
- **Registering BPPs before creating the service** enables service initialization to pass through the appropriate post-processing mechanism.

Annotations such as `@Autowired`, `@PostConstruct`, `@Transactional`, and `@Async` should not be conflated as all handled by a single BPP or at the exact same moment. Each feature has its own infrastructure and processing mechanism. What matters here is that many Spring extension features depend on preparing infrastructure before instantiating instances.

## 9. When Should You Write or Manually Register a BPP?

**Appropriate cases for writing a custom BPP:**

- Observing the initialization lifecycle of a specific group of beans.
- Checking beans that implement a marker interface to apply a uniform convention.
- Wrapping beans with an adapter/proxy in an extension that genuinely requires per-instance interception.
- Writing internal framework integrations with a clear contract and bean scope.

However, in most business applications, **you do not need to implement a BPP yourself**. Use built-in mechanisms: `@Configuration`, `@Bean`, constructor injection, validation, AOP/transaction integration, lifecycle callbacks, or startup runners as needed. A BPP is a container-level hook, so modifying the wrong bean or breaking order can affect the entire application.

**Manual registration** can be useful in a programmatically created `BeanFactory`:

~~~java
ConfigurableBeanFactory factory = /* prepared factory */;
factory.addBeanPostProcessor(new TraceProcessor());
~~~

This is **API pseudocode**, not a standalone runnable program: you must create/prepare the factory and bean definitions before calling it. The `addBeanPostProcessor` method takes an already-instantiated BPP. Registration must occur **before creating the beans you want the BPP to process**. `Ordered` on a BPP registered this way does not override actual registration order.

In everyday Spring Boot applications, using `@Component` or `static @Bean` so the container detects it automatically is much clearer.

## 10. Common Errors and Diagnostic Guidance

| Symptom | Possible cause | How to check/fix |
| --- | --- | --- |
| BPP does not log for the expected service | BPP was not scanned/registered or the service is not Spring-managed | Check package, `@Bean` definition, bean name, and how the service is created |
| BPP processes only some beans, missing an important bean | Bean was created too early during BPP registration | Check BPP constructor dependencies, factory methods, and `not eligible` warnings |
| `@Bean` returns `Object`, BPP is not detected in time | Return type is too generic, hard for Spring to autodetect early | Change return type to `BeanPostProcessor` or the concrete implementation |
| BPP declared with non-static `@Bean` and config triggers warnings | Config class is constructed early to invoke the factory method | Use `static @Bean` without business bean dependencies |
| Bean has `@Transactional` but proxy behavior is missing | Could be early instantiation, missing transaction infra, or self-invocation bypassing proxy | Separate lifecycle vs transaction config; inspect whether the actual bean is a proxy |
| Log order between BPPs differs from expectations | `@Order` does not control BPP ordering, or manual registration was used | Use `Ordered`/`PriorityOrdered` appropriately; check registration mechanism |
| BPP throws errors on unrelated beans | BPP operates too broadly, assumes wrong bean type, or causes side effects | Restrict conditions, check `instanceof`, pass unrelated beans through unchanged |
| BPP causes a dependency cycle at startup | BPP injects a bean with a reverse dependency or triggers early lookup | Remove unnecessary direct dependencies; redesign extension and bean relationships |
| BPP registered in a child context, parent beans are not processed | BPP applies per BeanFactory/context where it is registered | Register the extension in the context managing the target beans |
| Created object with `new` and expected BPP to run | Instance is outside Spring IoC | Obtain the bean from the context or move instantiation into Spring |

### Analysis Process When Suspecting Early Bean Creation

1. Identify **which specific bean** missed expected processing; check startup warnings and actual proxy class if AOP is involved.
2. Verify the relevant BPP is truly a bean in the same `ApplicationContext` and that its `@Bean` return type is specific enough for early detection.
3. Inspect the BPP's factory method and dependencies: is it pulling a business service during post-processor registration?
4. Check for early instantiation in `BeanFactoryPostProcessor`, `BeanDefinitionRegistryPostProcessor`, `getBean()`, or manual bootstrap code.
5. Fix the structural cause and re-run, verifying the bean is processed by the required BPPs and actual application behavior is correct.

Avoid "patching" it by arbitrarily creating a new instance after context startup: that can produce two instances with diverging state and corrupt the dependency graph.

## 11. Knowledge Check

**Question 1:** Why doesn't Spring instantiate all singletons right after reading bean definitions?

**Answer:** Certain processors must be registered beforehand to participate in instance initialization. If a bean is created too early, it may miss processing by BPPs, such as auto-proxying.

**Question 2:** During refresh, does `invokeBeanFactoryPostProcessors` or `registerBeanPostProcessors` run first?

**Answer:** `invokeBeanFactoryPostProcessors` runs first; BFPPs process metadata/definitions, then BPPs are registered to participate in processing subsequently created beans.

**Question 3:** Are all beans guaranteed to be created only after all BPPs finish registering?

**Answer:** No. BPPs themselves, their direct dependencies, and certain infrastructure beans may be created early. Therefore, avoid letting BPPs pull business beans into this phase.

**Question 4:** Why is `static @Bean` recommended for factory methods returning a BPP?

**Answer:** So the container can create the BPP early without needing to construct an instance of the configuration class containing the factory method, reducing the risk of related beans being constructed too early.

**Question 5:** Does registering a BPP via `addBeanPostProcessor()` automatically respect `Ordered`?

**Answer:** No. With manual registration, the order in which BPPs are added determines application order; `Ordered` applies to BPPs autodetected by the container.

**Hands-on exercise:** Run the example in section 5 and record the order of the six output lines produced by the example code. Then try making `TraceProcessor` require a `GreetingService` in its constructor or factory method, predict at which phase the service will be created, and explain why that change is dangerous for post-processing. During the exercise, check warnings and actual behavior; do not use this risky pattern in real applications.

## 12. References and Key Takeaways

Official references:

- Spring Framework Reference — [Container Extension Points](https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html): distinguishing BPP/BFPP, autodetection, static `@Bean`, early initialization, and AOP.
- Spring Framework Javadoc — [BeanPostProcessor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/config/BeanPostProcessor.html): callback contract and registration/ordering rules.
- Spring Framework Javadoc — [AbstractApplicationContext](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html): API and refresh lifecycle.

**Core takeaways:**

- BPP is an extension point for bean **instances**, invoked at before/after initialization checkpoints.
- Inside `refresh()`, **`invokeBeanFactoryPostProcessors()` → `registerBeanPostProcessors()` → `finishBeanFactoryInitialization()`** is a critical order.
- The container **registers BPPs before instantiating most regular singletons**, though it must create BPPs themselves and some dependencies/infrastructure early so registration can occur.
- When declaring a BPP with `@Bean`, prefer **`static`**, no business dependencies, and a clear BPP or concrete implementation return type.
- Beans created too early can miss auto-proxying or other post-processors; do not dismiss `not eligible for getting processed by all BeanPostProcessors` warnings as meaningless.
- Autodetected BPPs follow `PriorityOrdered`/`Ordered`; manually added BPPs run in registration order.
- Use BPPs for genuine container-extension needs; keep regular business code in beans and appropriate lifecycle callbacks.
