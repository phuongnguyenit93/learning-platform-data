# Processing BeanDefinitionRegistryPostProcessor and BeanFactoryPostProcessor in Spring Boot

## 1. Why Does Spring Need These Two Types of Post-Processors?

During Spring Boot startup, the **ApplicationContext** does not immediately instantiate every object from **@Component**, **@Service**, **@Configuration**, and **@Bean**. First, Spring collects and processes **BeanDefinitions**: metadata describing a bean's name, type, scope, lazy initialization, constructor arguments, property values, and how to create the bean. Only afterward does the container instantiate most application singletons.

Spring Framework provides two extension points to intervene **before the normal bean instantiation phase**:

- **BeanDefinitionRegistryPostProcessor (BDRPP):** accesses the registry to register additional BeanDefinitions, remove them, or modify them before regular BeanFactoryPostProcessors are invoked.
- **BeanFactoryPostProcessor (BFPP):** reads and modifies configuration metadata in **ConfigurableListableBeanFactory**, so that those changes are applied when Spring creates the beans.

Both operate primarily at the **bean definition** layer, unlike **BeanPostProcessor** (BPP), which processes bean **instances** during initialization.

~~~text
Configuration sources (@Bean, @Component, @Import...)
                   |
                   v
           BeanDefinitionRegistry
                   |
                   | BDRPP: registry callback
                   | register/modify BeanDefinitions
                   v
        ConfigurableListableBeanFactory
                   |
                   | BDRPP and BFPP: factory callback
                   | read/modify metadata before bean creation
                   v
            Register BeanPostProcessors
                   |
                   v
         Create and initialize singletons
                   |
                   | BPP: before/after initialization
                   v
             Bean instance ready
~~~

For example, if you want to create a bean named **dynamicGreeting** from metadata and then modify its **message** property before its constructor is called, BDRPP and BFPP are the two appropriate extension points. There is no need to instantiate the object and then mutate it manually.

## 2. Interfaces, Callbacks, and Specific Responsibilities

### 2.1. BeanFactoryPostProcessor

The **org.springframework.beans.factory.config.BeanFactoryPostProcessor** interface has one callback:

~~~java
void postProcessBeanFactory(
        ConfigurableListableBeanFactory beanFactory)
        throws BeansException;
~~~

Through **ConfigurableListableBeanFactory**, a processor can read metadata:

~~~java
BeanDefinition definition =
        beanFactory.getBeanDefinition("myService");

definition.setLazyInit(true);
definition.getPropertyValues().add("label", "updated");
~~~

This is an **illustrative snippet**, assuming the **myService** definition already exists, the bean class supports the **label** property, and the code runs during the BFPP phase. **setLazyInit(true)** modifies the bean creation policy; **getPropertyValues().add(...)** modifies the value Spring will assign when creating the bean.

A classic Spring BFPP is **PropertySourcesPlaceholderConfigurer**, which helps resolve configuration placeholders in BeanDefinitions and related value-resolution mechanisms.

**Important:** a BFPP receives the **bean factory**, but you should not call **beanFactory.getBean(...)** to "grab the object and mutate it." Doing so can instantiate the bean prematurely, before all **BeanPostProcessors**, AOP proxies, and related injection mechanisms are fully active.

### 2.2. BeanDefinitionRegistryPostProcessor

The **org.springframework.beans.factory.support.BeanDefinitionRegistryPostProcessor** interface extends **BeanFactoryPostProcessor** and adds the callback:

~~~java
void postProcessBeanDefinitionRegistry(
        BeanDefinitionRegistry registry)
        throws BeansException;
~~~

**BeanDefinitionRegistry** provides operations such as:

- **registerBeanDefinition(name, definition):** registers new metadata.
- **containsBeanDefinition(name):** checks for a bean definition name.
- **getBeanDefinition(name):** retrieves existing metadata.
- **removeBeanDefinition(name):** removes a definition when permitted and justified.

Because **BDRPP extends BFPP**, a BDRPP has **two callbacks to implement**:

~~~java
@Override
public void postProcessBeanDefinitionRegistry(
        BeanDefinitionRegistry registry) {
    // Add/modify/remove BeanDefinitions in the registry phase.
}

@Override
public void postProcessBeanFactory(
        ConfigurableListableBeanFactory beanFactory) {
    // Process metadata in the factory phase.
}
~~~

These are **two methods belonging to a single implementation**, not a standalone Java application. When no additional logic is needed in the second callback, the method can be left empty. Spring still calls it according to the BFPP contract, and **does not invoke the processor again a second time as a separate new BFPP**.

### 2.3. Distinguishing from BeanPostProcessor and FactoryBean

| Concept | What does it process? | Typical callback/API | Timing |
| --- | --- | --- | --- |
| **BeanDefinitionRegistryPostProcessor** | Registry and BeanDefinitions | **postProcessBeanDefinitionRegistry** | Early in refresh |
| **BeanFactoryPostProcessor** | BeanDefinition/BeanFactory metadata | **postProcessBeanFactory** | After the registry phase, before BPP registration |
| **BeanPostProcessor** | Bean object being/already created | **postProcessBeforeInitialization**, **postProcessAfterInitialization** | Each time a bean is initialized by the container |
| **FactoryBean<T>** | Creates a bean object in a custom way | **getObject()** | When the container needs the FactoryBean's product |

**BeanPostProcessor does not extend BeanFactoryPostProcessor.** A BFPP runs in the metadata phase; it is not called again for each bean. **FactoryBean** is also not a type of BFPP: the names look similar, but their responsibilities are completely different.

## 3. Exact Position in ApplicationContext.refresh()

Spring Boot 3.3 uses **SpringApplication** to prepare the Environment, create the ApplicationContext, load configuration sources, and call **refresh()**. Core Spring Framework, especially **AbstractApplicationContext**, orchestrates the processors. The general mechanism applies to non-web, Servlet, and Reactive contexts.

Key sequence during a successful refresh:

~~~text
SpringApplication.run(...)
   |
   +-- Prepare Environment, create context, load sources
   |
   +-- ApplicationContext.refresh()
         |
         +-- prepareRefresh()
         +-- obtainFreshBeanFactory()
         +-- prepareBeanFactory(...)
         +-- context.postProcessBeanFactory(...)   [context hook]
         |
         +-- invokeBeanFactoryPostProcessors(...)
         |      |
         |      +-- BDRPP.postProcessBeanDefinitionRegistry(...)
         |      +-- BDRPP.postProcessBeanFactory(...)
         |      +-- BFPP.postProcessBeanFactory(...)
         |
         +-- registerBeanPostProcessors(...)
         +-- initMessageSource(...)
         +-- initApplicationEventMulticaster(...)
         +-- onRefresh()
         +-- registerListeners()
         +-- finishBeanFactoryInitialization(...)
         |      |
         |      +-- Instantiate remaining non-lazy singletons
         |      +-- Apply BeanPostProcessors
         |
         +-- finishRefresh()
   |
   +-- ApplicationStartedEvent
   +-- ApplicationRunner / CommandLineRunner
   +-- ApplicationReadyEvent
   +-- run(...) returns context
~~~

**Naming note:** **context.postProcessBeanFactory(...)** in **AbstractApplicationContext.refresh()** is a *context extension hook*, distinct from **BeanFactoryPostProcessor.postProcessBeanFactory(...)** on each processor. The context hook runs before the step that invokes processors.

**BFPP runs before most application singletons are created**, though this does not mean the JVM has zero objects yet: to operate, Spring must already create some processors and infrastructure beans at an early stage. A forced **getBean(...)** call inside a BFPP can instantiate additional application beans earlier than intended.

The purpose of this order is to ensure metadata is modified **before it is used** to create singletons, inject dependencies, and invoke initialization callbacks.

## 4. What Algorithm Does Spring Use to Process BDRPP Before BFPP?

Spring does not run processors in source code line order or alphabetical file-name order. Inside **invokeBeanFactoryPostProcessors**, the framework has a dedicated registry-processing mechanism. This matters because one BDRPP can register the **BeanDefinition of another BDRPP**.

### Phase 1 — Processing BeanDefinitionRegistryPostProcessors

Spring prioritizes BDRPPs registered programmatically with the context, then processes processors discovered via bean definitions in groups:

1. **PriorityOrdered** processors.
2. Remaining **Ordered** processors.
3. Processors without a declared order.

During the registry stage, Spring **loops continuously** whenever new BDRPPs are discovered, until no unexecuted BDRPPs remain. This allows definitions introduced during the registry phase to join the appropriate processing round.

The callback invoked is **postProcessBeanDefinitionRegistry(registry)**; inside the callback, the processor can register a new **RootBeanDefinition** or modify existing definitions. Subsequent processors will see the updated registry.

### Phase 2 — Factory Callbacks of the BDRPPs Themselves

After finishing registry processing, Spring invokes **postProcessBeanFactory(beanFactory)** on the BDRPPs that ran. Even though BDRPP extends BFPP, this callback belongs to **that same single processing pass of the processor**, not an independent second processor run.

### Phase 3 — Regular BeanFactoryPostProcessors

The remaining BFPPs are processed sequentially in groups: **PriorityOrdered**, **Ordered**, and then unordered BFPPs. Only after this step finishes does Spring proceed to register BeanPostProcessors and create the remaining application singletons.

~~~text
BDRPP registry callbacks
   -> PriorityOrdered
   -> Ordered
   -> remaining processors (looping if new BDRPPs appear)
           |
           v
BDRPP factory callbacks
           |
           v
BFPP factory callbacks
   -> PriorityOrdered
   -> Ordered
   -> remaining
           |
           v
Register BeanPostProcessors
           |
           v
Instantiate singletons and per-bean callbacks
~~~

**Special case:** processors added directly via **ApplicationContext.addBeanFactoryPostProcessor(...)** follow separate processing rules and cannot be assumed identical in ordering to processors discovered from bean definitions.

### 4.1. PriorityOrdered and Ordered

When an explicit order between custom processors is required, implementations can use **org.springframework.core.PriorityOrdered** or **org.springframework.core.Ordered**. Within the same ordering group, a smaller **getOrder()** value is typically processed earlier:

~~~java
final class MetadataProcessor
        implements BeanFactoryPostProcessor, Ordered {

    @Override
    public int getOrder() {
        return 100;
    }

    @Override
    public void postProcessBeanFactory(
            ConfigurableListableBeanFactory beanFactory) {
        // Selectively modify metadata.
    }
}
~~~

This is a **snippet inside a project with imports declared**, not a standalone program. With multiple processors, do not rely on bean name order, **@Bean** method order, or position in a file. If two processors are tightly interdependent, reorganize the logic or determine ordering based on the framework contract.

## 5. ConfigurationClassPostProcessor Is Spring's Key BDRPP

**ConfigurationClassPostProcessor** is an infrastructure **BeanDefinitionRegistryPostProcessor** with **PriorityOrdered** precedence. It enables Spring to process annotation-based configuration classes:

- Parsing **@Configuration** and configuration sources.
- Processing directives related to **@ComponentScan**, **@Import**, **@Bean**.
- Registering BeanDefinitions for discovered beans and **@Bean** methods.
- Performing finalization steps related to configuration classes.

Example:

~~~java
@Configuration
class FeatureConfiguration {

    @Bean
    GreetingService greetingService() {
        return new GreetingService();
    }
}
~~~

While reading configuration, Spring can register a **BeanDefinition** describing the **greetingService()** method **without needing to instantiate GreetingService immediately**.

That is why **ConfigurationClassPostProcessor must run early**: bean definitions from **@Bean** must appear before remaining BFPPs customize them.

**Ordering warning:** if a custom BDRPP runs after ConfigurationClassPostProcessor and registers an additional **@Configuration** class definition, do not assume Spring will **automatically re-run the entire annotation-scanning pass** that already completed earlier. Register definitions according to the contract or use the configuration/registrar mechanisms Spring supports for that purpose.

## 6. Runnable Java 17+ Example: Registering a Bean Then Modifying Metadata

The following example uses a **Spring Boot 3.3.x** project, **Java 17+**, the **spring-boot-starter** dependency, and the Spring Boot Gradle plugin. It runs in **non-web** mode to focus on container callbacks.

Create the file:

**src/main/java/com/example/runtime/PostProcessorDemoApplication.java**

~~~java
package com.example.runtime;

import org.springframework.beans.BeansException;
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.beans.factory.config.BeanFactoryPostProcessor;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.beans.factory.support.BeanDefinitionRegistry;
import org.springframework.beans.factory.support.BeanDefinitionRegistryPostProcessor;
import org.springframework.beans.factory.support.RootBeanDefinition;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class PostProcessorDemoApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(PostProcessorDemoApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);

        try (ConfigurableApplicationContext context = app.run(args)) {
            GreetingService service =
                    context.getBean("dynamicGreeting", GreetingService.class);

            System.out.println("5 | main: " + service.getMessage());
        }
    }

    @Bean
    static BeanDefinitionRegistryPostProcessor registryProcessor() {
        return new BeanDefinitionRegistryPostProcessor() {

            @Override
            public void postProcessBeanDefinitionRegistry(
                    BeanDefinitionRegistry registry)
                    throws BeansException {

                RootBeanDefinition definition =
                        new RootBeanDefinition(GreetingService.class);

                definition.getPropertyValues()
                          .add("message", "initial message");

                registry.registerBeanDefinition(
                        "dynamicGreeting", definition);

                System.out.println(
                        "1 | registry: dynamicGreeting registered");
            }

            @Override
            public void postProcessBeanFactory(
                    ConfigurableListableBeanFactory beanFactory)
                    throws BeansException {

                System.out.println("2 | registry: factory callback");
            }
        };
    }

    @Bean
    static BeanFactoryPostProcessor metadataProcessor() {
        return beanFactory -> {
            BeanDefinition definition =
                    beanFactory.getBeanDefinition("dynamicGreeting");

            definition.getPropertyValues()
                      .add("message", "updated before instantiation");

            System.out.println("3 | factory: bean definition updated");
        };
    }

    public static class GreetingService {

        private String message;

        public GreetingService() {
            System.out.println("4 | bean: constructor executed");
        }

        public void setMessage(String message) {
            this.message = message;
        }

        public String getMessage() {
            return message;
        }
    }
}
~~~

Run with the Gradle Wrapper from the Boot project directory:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

**Lines printed by the example itself in expected order:**

~~~text
1 | registry: dynamicGreeting registered
2 | registry: factory callback
3 | factory: bean definition updated
4 | bean: constructor executed
5 | main: updated before instantiation
~~~

Spring Boot may print startup logs interspersed between the lines above. Only the numbered lines printed by the example itself need to match in order and content.

### 6.1. Why Does This Order Occur?

**Step 1:** The BDRPP creates a **RootBeanDefinition** for **GreetingService**, sets the initial value **message = "initial message"**, and registers the bean name **dynamicGreeting**. No GreetingService object is created merely by registering the definition.

**Step 2:** That same registry processor receives the **postProcessBeanFactory** callback, proving that a BDRPP is simultaneously a BFPP.

**Step 3:** The regular BFPP looks up the newly added bean definition and updates **message = "updated before instantiation"**. This modifies the **definition**, not a setter on an instance.

**Step 4:** As Spring completes refresh, the non-lazy singleton **dynamicGreeting** is created. Its constructor prints line 4; afterward, Spring uses the **setMessage(...)** setter to apply the updated property value.

**Step 5:** **SpringApplication.run(...)** returns the context; **main** looks up the existing bean and reads the final value **updated before instantiation**.

If you remove **metadataProcessor()** alone while keeping the registry processor, the final value will normally be **initial message**. The example thus demonstrates both **registration** and **metadata modification before bean instantiation**.

### 6.2. Why Are @Bean Methods Returning Processors `static`?

Processors in the **BeanFactoryPostProcessor** family are created **very early**. If declared via an **@Bean instance method**, Spring may have to instantiate the **@Configuration** object containing the method early. That can prevent **@Autowired**, **@Value**, **@PostConstruct**, or annotation processing on the configuration class from running through their full lifecycle.

Declaring:

~~~java
@Bean
static BeanFactoryPostProcessor metadataProcessor() {
    return beanFactory -> {
        // Process bean definitions.
    };
}
~~~

allows Spring to call the method **without instantiating the configuration class**. You should use **static @Bean** for BDRPP/BFPP when declaring them as methods on a configuration class, keep processor dependencies simple, and avoid pulling other application beans into their constructors.

### 6.3. Why Not Retrieve Bean Instances Inside a Processor?

Correct snippet in a BFPP:

~~~java
BeanDefinition definition =
        beanFactory.getBeanDefinition("dynamicGreeting");
~~~

Snippet risking lifecycle corruption:

~~~java
GreetingService service =
        beanFactory.getBean("dynamicGreeting", GreetingService.class);
~~~

Calling **getBean(...)** can force Spring to create **GreetingService too early**, before all BeanPostProcessors are registered. Consequences may include missing AOP proxies, skipped initialization mechanisms, or dependency errors. **BFPP should modify metadata, while BPP/lifecycle callbacks handle instances.**

## 7. What Can Be Modified in a BeanDefinition?

| Metadata | Illustrative API | Meaning |
| --- | --- | --- |
| Bean class | **new RootBeanDefinition(MyService.class)** | Specifies the class to instantiate |
| Bean name | **registerBeanDefinition("myService", definition)** | Sets the bean lookup name |
| Property values | **getPropertyValues().add("name", value)** | Assigns values via appropriate property binding |
| Constructor arguments | **getConstructorArgumentValues()** | Declares constructor parameters |
| Scope | **setScope("prototype")** | Selects instance lifecycle |
| Lazy flag | **setLazyInit(true)** | Allows deferring singleton creation when no eager dependency requires it |
| Depends-on | **setDependsOn("anotherBean")** | Declares explicit lifecycle ordering dependency |

These APIs operate at the metadata layer. **Modifying a BeanDefinition is not equivalent to modifying every already-created singleton.** Once a bean has been instantiated, changing its definition generally does not cause that object to be automatically recreated.

### 7.1. Avoiding Duplicate-Name Registration

With BeanDefinitionRegistry, check whether duplicate names should be avoided:

~~~java
if (!registry.containsBeanDefinition("dynamicGreeting")) {
    registry.registerBeanDefinition("dynamicGreeting", definition);
}
~~~

This is an illustrative snippet, assuming **definition** has been constructed appropriately. Duplicate registration can be rejected under bean-overriding policies or unintentionally shadow existing configuration if overriding is enabled. Do not overwrite infrastructure beans whose roles you do not clearly understand.

### 7.2. Iterating Definitions Selectively

A BFPP can iterate over metadata:

~~~java
for (String name : beanFactory.getBeanDefinitionNames()) {
    BeanDefinition definition =
            beanFactory.getBeanDefinition(name);

    // Modify only when the bean matches the target name/type/condition.
}
~~~

Do not apply **lazy**, scope, or property values indiscriminately across every application and library definition. Spring infrastructure beans have specific lifecycle requirements; uncontrolled changes can prevent the container from starting.

## 8. Choosing the Right Processor for Each Need

| Requirement | Appropriate mechanism | Explanation |
| --- | --- | --- |
| Register a new BeanDefinition before BFPPs run | **BeanDefinitionRegistryPostProcessor** | Has registry manipulation access |
| Change configuration of existing definitions | **BeanFactoryPostProcessor** | Operates on metadata before bean creation |
| Wrap/proxy a bean instance when created | **BeanPostProcessor** | Receives callbacks before/after initialization |
| Produce a bean object via custom factory logic | **FactoryBean<T>** | Provides a factory method for the bean product |
| Declare a regular application bean | **@Bean**, **@Component** | Easier to read and test than custom processors |
| Configure beans conditionally in Spring Boot | **@Conditional...**, auto-configuration | Leverages built-in framework mechanisms |
| Register beans from a custom annotation during config processing | **ImportBeanDefinitionRegistrar** | Fits the annotation/configuration pipeline |

BDRPP and BFPP are suitable for **infrastructure, starters, integration libraries, or cross-cutting metadata changes across multiple definitions**. If you just need to create a simple service, declaring **@Bean** is usually more maintainable.

## 9. Relationship with Spring Boot Auto-Configuration

Spring Boot builds on Spring Framework's configuration-processing mechanism. **@SpringBootApplication** enables components associated with **@Configuration**, **@ComponentScan**, and **@EnableAutoConfiguration**. **ConfigurationClassPostProcessor** and infrastructure configurations produce bean definitions before other BFPPs process metadata.

Three points to note:

1. Auto-configuration conditions such as **@ConditionalOnMissingBean** are evaluated when configuration is processed. If a bean is registered by a BDRPP **too late**, do not assume the framework will re-evaluate all previously completed conditions.
2. Custom processors can modify metadata created by auto-configuration, but you must know which processors still run afterward and might touch the same definition.
3. A BDRPP/BFPP belongs to **a specific ApplicationContext**. In systems with parent/child contexts, a processor in one context does not automatically process every definition in another context.

In the Boot ecosystem, prefer **@Conditional...**, **@ConfigurationProperties**, **@Bean**, **ImportBeanDefinitionRegistrar**, or official customization mechanisms when sufficient; only touch BeanDefinitions directly when the problem genuinely requires it.

## 10. Common Mistakes and How to Avoid Them

### 10.1. Confusing BFPP with BeanPostProcessor

**Symptom:** trying to mutate an instance field inside a BFPP, or assuming BFPP is called after each bean is created. **Fix:** BFPP processes metadata; BPP and lifecycle callbacks are suited for processing instances.

### 10.2. BFPP Using @Autowired to Pull Application Services Too Early

**Symptom:** a service is created before all BPP/AOP infrastructure, and logs report that the bean is not eligible to receive all post-processors. **Fix:** keep BFPPs dependent almost solely on metadata, Environment, or early-stage infrastructure; avoid calling **getBean** on regular services.

### 10.3. Non-Static @Bean Returning a BFPP

**Symptom:** Spring warns about a non-static **@Bean** method or annotations on the configuration class are not processed completely. **Fix:** declare **static @Bean** whenever possible.

### 10.4. BDRPP Only Implementing the Registry Callback

Because BDRPP extends BFPP, an implementation must still provide **postProcessBeanFactory**. If there is no factory-phase work to do, leave the callback empty; do not call the registry callback again from inside it.

### 10.5. Relying on Unguaranteed Processor Ordering

**Symptom:** in one environment a processor sees a definition, while in another environment it does not. **Fix:** consider **PriorityOrdered/Ordered**, programmatically registered processor groups, CCPP's precedence, and other classpath dependencies. Do not treat method declaration order as a contract.

### 10.6. Registering Definitions After ApplicationReadyEvent and Expecting BFPP to Re-Run

The BFPP callbacks for the **refresh** pass are already finished. Adding/modifying the registry at runtime does not make the framework re-run the pipeline and does not replace already-created instances. For runtime changes, design a dedicated management mechanism.

### 10.7. Mistaking a BeanDefinition for an Active Instance

A **RootBeanDefinition** is only a blueprint for how to create a bean. Before instantiation, the target class constructor has not necessarily run. Looking up **getBeanDefinition** does not allow invoking business methods on the bean.

### 10.8. Modifying Infrastructure Without Checking AOT/Native

Custom registration/post-processing may behave differently under AOT/native builds, especially code relying on reflection or dynamically selected classes. For applications targeting native images, verify directly against the AOT contract of the Spring Boot version in use.

## 11. How to Verify and Debug Startup Failures

When diagnosing, classify errors by phase: **definition registration**, **factory metadata**, **BPP registration**, or **bean instance creation**.

A useful observation technique is selective logging at three points:

~~~text
REGISTRY: postProcessBeanDefinitionRegistry
FACTORY:  postProcessBeanFactory
BEAN:     constructor / initialization
~~~

Then inspect the specific definition using **containsBeanDefinition**, **getBeanDefinition**, and its metadata. Avoid calling **getBean()** merely to inspect things, because that itself alters instantiation timing and can mask the root cause.

When multiple processors exist, check classes implementing **PriorityOrdered/Ordered**, registration mechanisms, stack traces, and Spring logs. Enable appropriate logging per package rather than printing every bean definition. If the error relates to auto-configuration, Spring Boot's condition evaluation report can clarify why a bean definition was or was not registered.

### Questions to Answer When Debugging

- Has your processor been created and recognized by Spring as a BDRPP/BFPP?
- Were the **registry** callback and **factory** callback invoked, and in what order?
- Did the target BeanDefinition already exist **at the moment** your processor ran?
- Did another processor overwrite/modify the metadata after your callback?
- Did any **getBean(...)** call or dependency cause **eager instantiation** before metadata edits finished?
- Are you debugging the right ApplicationContext when multiple contexts exist?

## 12. Self-Check Questions

**Question 1.** A BDRPP registers the **auditClient** definition. Can a regular BFPP change the lazy flag of that definition during the same refresh?

**Answer:** Yes. The registry phase occurs before the BFPP phase; if registration succeeds and is not removed or replaced, the BFPP sees the new definition.

**Question 2.** Does a BDRPP receive the **postProcessBeanFactory** callback?

**Answer:** Yes. BDRPP extends BFPP, so Spring invokes both the registry callback and the factory callback on the implementation.

**Question 3.** Should you retrieve **PaymentService** via **beanFactory.getBean(...)** inside a BFPP to set a field on the service?

**Answer:** No. Doing so can trigger premature instantiation, bypass some post-processing, and misuse the purpose of BFPP. Modify the BeanDefinition or use an instance-level extension point instead.

**Question 4.** A BFPP depends on a definition registered by a BDRPP. Do you need to call the BFPP manually from the registry callback to guarantee order?

**Answer:** No. The framework already executes the registry phase before the factory phase; calling callbacks manually can cause duplicate processing and unexpected side effects.

**Question 5.** Why should you use **@Bean static BeanFactoryPostProcessor**?

**Answer:** Because Spring needs to create BFPPs very early. A static method does not force Spring to instantiate the configuration class before annotation processors have finished their work.

**Question 6.** If a BDRPP registers a **@Configuration** class late, is ConfigurationClassPostProcessor guaranteed to rescan that class?

**Answer:** No. Understand the processing order and choose an appropriate extension mechanism; do not rely on an already-completed pipeline re-running automatically.

**Question 7.** In the example code, does the **GreetingService** constructor log line appear before or after the BFPP metadata-modification line?

**Answer:** After, because regular singletons are instantiated in a phase after BFPPs finish.

## 13. Takeaways and Official References

**BeanDefinitionRegistryPostProcessor modifies the set of BeanDefinitions**, whereas **BeanFactoryPostProcessor modifies the metadata of those BeanDefinitions**. BDRPP extends BFPP and has two callbacks. Spring executes these phases **before fully registering BeanPostProcessors and instantiating regular singletons**, so timely changes affect how beans are created.

Avoid instantiating services prematurely inside processors, choose **static @Bean** for processors when appropriate, and make ordering explicit if multiple processors depend on one another.

Official references:

- Spring Framework — Container Extension Points: https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html
- Spring Framework 6.1 API — BeanDefinitionRegistryPostProcessor: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/beans/factory/support/BeanDefinitionRegistryPostProcessor.html
- Spring Framework 6.1 API — BeanFactoryPostProcessor: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/beans/factory/config/BeanFactoryPostProcessor.html
- Spring Framework 6.1 API — ConfigurationClassPostProcessor: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/context/annotation/ConfigurationClassPostProcessor.html
- Spring Boot 3.3 API — SpringApplication: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html