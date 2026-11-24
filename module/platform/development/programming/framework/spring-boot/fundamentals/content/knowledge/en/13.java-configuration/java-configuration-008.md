# BeanFactoryPostProcessor and Modifying Metadata Before Bean Creation

In Spring, the container does not create a bean the instant it reads a Java class. Before instantiating ordinary singletons, Spring gathers metadata describing how to create the bean, its dependencies, scope, properties, and other options. That information is stored in a **BeanDefinition**. Because of this, the framework can adjust how a bean will be created before the actual object ever exists.

**BeanFactoryPostProcessor (BFPP)** is an extension point that lets an application or framework read and modify bean metadata during this phase. For example, a post-processor can switch a bean to lazy-init, add property values to a bean definition, or customize certain BeanFactory settings.

The key distinction of this lesson is separating:

- **BeanDefinition:** the blueprint/description of a bean, not the bean object itself.
- **BeanFactoryPostProcessor:** processes metadata inside the BeanFactory before ordinary beans are instantiated.
- **BeanPostProcessor:** intercepts the bean object during initialization, before or after initialization callbacks.

Understanding these three concepts helps you know when to alter how Spring creates a bean and when to process the object itself after it has been created.

## 1. From Java Class to Bean Instance

Suppose there is a service:

~~~java
@Service
public class ReportService {

    public void generate() {
        // Generate report.
    }
}
~~~

Spring does not merely see this class and immediately invoke its constructor. During configuration reading, component scanning, and annotation parsing, the container creates a **BeanDefinition** describing how to register the corresponding bean.

A BeanDefinition can contain information such as:

- Bean name and class used to instantiate the bean (if known directly).
- Factory bean or factory method if the object is created via a **@Bean** method.
- Scope: singleton, prototype, request, or custom scope.
- Lazy initialization.
- Constructor arguments and property values.
- Dependencies or **depends-on** relationships.
- **primary**, **autowire candidate** flags, and other metadata.
- Attributes related to role, description, and definition source.

High-level flow:

~~~text
Java class / @Bean / XML / auto-configuration
                    │
                    ▼
             BeanDefinition
               (metadata)
                    │
                    ▼
        BeanFactoryPostProcessor
         can modify metadata
                    │
                    ▼
          BeanFactory creates object
                    │
                    ▼
              Bean instance
                    │
                    ▼
       Dependency injection and lifecycle
~~~

**BeanDefinition is the blueprint; bean instance is the actual object in memory.** A BFPP primarily operates on the blueprint to change how the object will be created or configured.

## 2. What Is BeanFactoryPostProcessor?

**BeanFactoryPostProcessor** is a Spring interface with a single method:

~~~java
void postProcessBeanFactory(
        ConfigurableListableBeanFactory beanFactory);
~~~

The method receives **ConfigurableListableBeanFactory**, allowing the post-processor to access already-registered bean definitions and customize metadata before ordinary beans are initialized.

A minimal implementation:

~~~java
import org.springframework.beans.factory.config.BeanFactoryPostProcessor;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;

public class ApplicationMetadataProcessor
        implements BeanFactoryPostProcessor {

    @Override
    public void postProcessBeanFactory(
            ConfigurableListableBeanFactory beanFactory) {
        // Read or modify bean definitions here.
    }
}
~~~

Spring detects BFPP beans and invokes this method during ApplicationContext refresh. The goal is to process BeanFactory configuration **before ordinary application beans are created**.

One detail to remember: post-processors themselves must be instantiated early enough to do their work. Therefore, BFPPs are a special group of infrastructure beans during startup. Do not treat them like ordinary services that can freely depend on any other bean.

### What Can a BFPP Do?

- Look up bean definitions by name and inspect metadata.
- Change scope, lazy-init, primary, or other applicable attributes.
- Add or modify property values that will be applied when the bean is created.
- Adjust certain BeanFactory settings.
- Support placeholder and metadata processing mechanisms required by the framework.

### BFPP Is Not a Tool for Mutating Already-Created Objects

If a singleton has already been instantiated, modifying its **BeanDefinition** afterward does not automatically update fields on the existing object. BFPP is designed to run early, before most ordinary beans are created.

If you want to process object instances after creation, look at **BeanPostProcessor**. If you want to update a configuration value while the application is running, use an appropriate dynamic configuration mechanism; mutating BeanDefinitions is not how runtime state is reloaded.

## 3. When Does BFPP Run During Startup?

In a typical ApplicationContext, the major steps can be visualized as:

~~~text
1. Create ApplicationContext and prepare Environment
                  │
                  ▼
2. Read configurations and register BeanDefinitions
   - @Configuration
   - @ComponentScan
   - @Bean
   - auto-configuration
                  │
                  ▼
3. BeanDefinitionRegistryPostProcessor
   - can register additional BeanDefinitions
   - processes registry before regular BFPPs
                  │
                  ▼
4. BeanFactoryPostProcessor
   - adjusts BeanFactory / BeanDefinition metadata
                  │
                  ▼
5. Register BeanPostProcessors
                  │
                  ▼
6. Instantiate remaining eager singletons
   - constructors
   - dependency injection
   - initialization callbacks
                  │
                  ▼
7. ApplicationContext completes refresh
~~~

This is a high-level diagram to understand where BFPP fits. Certain infrastructure components such as **ConfigurationClassPostProcessor**, post-processors, and startup support beans are instantiated early according to the container's own lifecycle.

**BFPP runs after relevant bean definitions are loaded and before ordinary application singletons are instantiated.** That enables it to modify metadata that the BeanFactory will use later.

### Why Must Processing Happen Before Bean Creation?

Suppose you want to mark **ReportService** as lazy-init. If the service has already been instantiated, flipping the lazy-init flag in metadata will not make the object disappear from memory or cause Spring to defer creating it again. Thus, the change must happen while the BeanFactory is still preparing bean instantiation.

Similarly, if you need to add a property value to a BeanDefinition, that value must be present before the container populates properties on the target object.

## 4. Example 1: Switching a Bean to Lazy-Init

A bean can be marked lazy using an annotation:

~~~java
@Service
@Lazy
public class ReportService {
}
~~~

Or metadata can be configured via a BFPP. Suppose the component is registered under bean name **reportService**:

~~~java
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.beans.factory.config.BeanFactoryPostProcessor;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MetadataConfiguration {

    @Bean
    static BeanFactoryPostProcessor makeReportServiceLazy() {
        return beanFactory -> {
            String beanName = "reportService";

            if (beanFactory.containsBeanDefinition(beanName)) {
                BeanDefinition definition =
                        beanFactory.getBeanDefinition(beanName);
                definition.setLazyInit(true);
            }
        };
    }
}
~~~

In this example:

1. Component scanning registers the BeanDefinition for **ReportService**.
2. Spring invokes the BFPP before creating ordinary eager singletons.
3. The BFPP retrieves metadata with **getBeanDefinition("reportService")**.
4. **setLazyInit(true)** instructs the BeanFactory to defer instantiating that singleton until requested.

**Lazy-init does not mean the bean will never be created.** If another eager singleton requires **ReportService** via its constructor, Spring still has to create that dependency when instantiating the dependent bean. Lazy-init defers bean creation until requested, yet a required dependency of an eager bean can still trigger early creation.

The bean name in the example must match the registered name. For components with default names, Spring normally converts the class name to a lowercase-initial bean name; you can declare an explicit name with **@Service("reportService")** to avoid relying on naming conventions.

## 5. Example 2: Modifying Property Values in a BeanDefinition

A BFPP can also add property values to be applied when the object is constructed.

Application bean:

~~~java
import org.springframework.stereotype.Component;

@Component("batchProcessor")
public class BatchProcessor {

    private int batchSize = 50;

    public void setBatchSize(int batchSize) {
        this.batchSize = batchSize;
    }

    public int getBatchSize() {
        return batchSize;
    }
}
~~~

Post-processor:

~~~java
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.beans.factory.config.BeanFactoryPostProcessor;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class BatchMetadataConfiguration {

    @Bean
    static BeanFactoryPostProcessor configureBatchSize() {
        return beanFactory -> {
            String beanName = "batchProcessor";

            if (beanFactory.containsBeanDefinition(beanName)) {
                BeanDefinition definition =
                        beanFactory.getBeanDefinition(beanName);

                definition.getPropertyValues()
                        .add("batchSize", 200);
            }
        };
    }
}
~~~

When **BatchProcessor** is created, Spring applies the property value **batchSize = 200** via its setter. The default value **50** in the class is replaced by the value from metadata.

Conditions for this example to work:

- The bean definition must exist under the name **batchProcessor** before the BFPP runs.
- The class must have a matching writable property, here **setBatchSize(int)**.
- The value type must be convertible to the property type.
- The BFPP must run before the bean is instantiated.

This example illustrates modifying **metadata**, not calling **setBatchSize(200)** directly on a bean instance. At the moment the BFPP runs, we are modifying the list of property values that the BeanFactory will apply during object creation.

### When Should You Set Property Values in a BFPP?

This is an infrastructure-level technique. In ordinary application code, **@ConfigurationProperties**, **@Value**, constructor injection, or an explicit factory method is much easier to read. BFPP is appropriate when metadata must be transformed systematically—such as an internal framework or integration library adjusting bean definitions across many components.

## 6. What Metadata Does a BeanDefinition Contain?

BeanDefinition is the abstraction describing how the container creates and configures a bean. Common attributes:

| Metadata | Meaning |
|---|---|
| **beanClassName / bean class** | Class used to instantiate the bean if specified directly |
| **scope** | Instance scope, such as singleton or prototype |
| **lazyInit** | Whether bean initialization should be deferred |
| **primary** | Whether the bean is preferred when resolving a single dependency |
| **autowireCandidate** | Whether the bean qualifies as an autowiring candidate |
| **dependsOn** | Beans that must be initialized beforehand |
| **propertyValues** | Values to be assigned to bean properties |
| **constructorArgumentValues** | Values/arguments used when instantiating the bean via constructor |
| **factoryBeanName / factoryMethodName** | Factory bean or factory method producing the object |
| **initMethodName / destroyMethodName** | Custom lifecycle methods |
| **role / description** | Information describing the role and definition source |

Not every BeanDefinition contains all of these fields. For example, a bean created via a factory method may not declare the target object's class directly in the same way as a class-name-defined bean.

### BFPP Can Modify Many Types of Metadata

For instance, changing scope:

~~~java
definition.setScope(BeanDefinition.SCOPE_PROTOTYPE);
~~~

Or marking a bean primary:

~~~java
definition.setPrimary(true);
~~~

Or excluding a bean from being an autowire candidate:

~~~java
definition.setAutowireCandidate(false);
~~~

These lines only demonstrate metadata APIs. Do not arbitrarily change the scope or autowire candidate status of application beans just because it is possible. Scope directly affects instance count, state, and lifecycle; modifying metadata can alter the behavior of the entire system.

## 7. How Does BeanFactoryPostProcessor Differ from BeanPostProcessor?

The two names sound very similar, yet they operate at two different stages.

| Criterion | BeanFactoryPostProcessor | BeanPostProcessor |
|---|---|---|
| Primary target | BeanFactory and BeanDefinition metadata | Bean instances |
| Timing | After bean definitions are loaded, before ordinary application beans are created | During the initialization of each bean |
| Goal | Alter how beans will be created/configured | Process objects before/after initialization |
| Main API | **postProcessBeanFactory(...)** | **postProcessBeforeInitialization(...)**, **postProcessAfterInitialization(...)** |
| Examples | Property placeholder configurer, toggling lazy-init | Annotation processing, proxy creation |

Flow diagram:

~~~text
BeanDefinitions loaded
        │
        ▼
BeanFactoryPostProcessor
        │
        │ modifies metadata
        ▼
BeanFactory starts creating bean
        │
        ▼
Dependency injection
        │
        ▼
BeanPostProcessor before initialization
        │
        ▼
@PostConstruct / afterPropertiesSet / init-method
        │
        ▼
BeanPostProcessor after initialization
        │
        ▼
Bean instance ready
~~~

### Example of BeanPostProcessor

~~~java
import org.springframework.beans.BeansException;
import org.springframework.beans.factory.config.BeanPostProcessor;
import org.springframework.stereotype.Component;

@Component
public class LoggingBeanPostProcessor implements BeanPostProcessor {

    @Override
    public Object postProcessBeforeInitialization(
            Object bean, String beanName) throws BeansException {
        // Can inspect or process the instance before init callbacks.
        return bean;
    }

    @Override
    public Object postProcessAfterInitialization(
            Object bean, String beanName) throws BeansException {
        // Can return a different object, such as a proxy.
        return bean;
    }
}
~~~

A BeanPostProcessor receives the **actual object** and can return a wrapped or processed object. For example, AOP mechanisms use post-processing to create proxies for beans.

By contrast, a BFPP does not receive bean instances as parameters. It receives **ConfigurableListableBeanFactory** to manipulate metadata and BeanFactory configuration.

### Do Not Use BFPP in Place of BeanPostProcessor

If the requirement is:

- "Switch to lazy-init before the bean is created" → BFPP.
- "Add a property value to a bean definition" → BFPP.
- "Log when a bean instance finishes initializing" → BeanPostProcessor or appropriate lifecycle callback.
- "Wrap a service in a proxy" → BeanPostProcessor / AOP.
- "Validate object state after injection" → `@PostConstruct` or appropriate post-processor.

Choosing the right extension point avoids premature instantiation or modifying the wrong layer.

## 8. BeanDefinitionRegistryPostProcessor: Registering New Definitions

**BeanDefinitionRegistryPostProcessor (BDRPP)** extends **BeanFactoryPostProcessor** and adds another method:

~~~java
void postProcessBeanDefinitionRegistry(
        BeanDefinitionRegistry registry);
~~~

Key difference:

- **BDRPP** can add, modify, or remove bean definitions in the registry before the ordinary BFPP phase.
- **BFPP** works with the BeanFactory and existing bean definitions; it mainly modifies metadata/configuration.

If you need to **register a new bean definition**, BDRPP is usually the more appropriate extension point.

### Example Registering a Bean Definition

~~~java
import org.springframework.beans.factory.support.BeanDefinitionBuilder;
import org.springframework.beans.factory.support.BeanDefinitionRegistry;
import org.springframework.beans.factory.support.BeanDefinitionRegistryPostProcessor;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class DynamicRegistrationConfiguration {

    @Bean
    static BeanDefinitionRegistryPostProcessor registerAuditService() {
        return new BeanDefinitionRegistryPostProcessor() {

            @Override
            public void postProcessBeanDefinitionRegistry(
                    BeanDefinitionRegistry registry) {
                if (!registry.containsBeanDefinition("auditService")) {
                    registry.registerBeanDefinition(
                            "auditService",
                            BeanDefinitionBuilder
                                    .genericBeanDefinition(AuditService.class)
                                    .getBeanDefinition());
                }
            }

            @Override
            public void postProcessBeanFactory(
                    ConfigurableListableBeanFactory beanFactory) {
                // Additional metadata processing can happen after the registry step.
            }
        };
    }
}
~~~

In this example, **AuditService** is a Java class defined in the application. The BDRPP checks the bean name before registering to avoid duplicates. As startup continues, the BeanFactory uses the new definition to create the object on demand.

### Why Does BDRPP Run Before BFPP?

BDRPP needs an opportunity to add bean definitions so subsequent post-processors can see them. Therefore, Spring executes **BeanDefinitionRegistryPostProcessor**s before ordinary **BeanFactoryPostProcessor**s.

A key part of Spring, **ConfigurationClassPostProcessor**, is itself a BDRPP. It processes configuration classes, component scanning, `@Bean` methods, and various configuration metadata before application beans are created.

If you only need to change lazy-init or a property value on an existing bean, do not use BDRPP simply because its name sounds broader. Choose the simpler BFPP.

## 9. Why Should @Bean Methods Creating a BFPP Be static?

When declaring a BFPP via Java configuration, it is usually best written as:

~~~java
@Configuration
public class MetadataConfiguration {

    @Bean
    public static BeanFactoryPostProcessor metadataProcessor() {
        return beanFactory -> {
            // Adjust metadata.
        };
    }
}
~~~

Reason: Spring must instantiate the BFPP very early to perform metadata processing. If the **@Bean** factory method is an instance method, Spring may have to instantiate its enclosing **@Configuration** object earlier than normal.

Instantiating the configuration class too early can mean dependencies or annotation processing associated with that class are not yet ready as expected. Spring therefore recommends that **@Bean methods returning BeanFactoryPostProcessor/BeanDefinitionRegistryPostProcessor be static** whenever possible.

### Do Not Inject Application Services into a BFPP

A BFPP is created at a very early stage. If it depends on a business service:

~~~java
@Bean
BeanFactoryPostProcessor metadataProcessor(
        ReportService reportService) {
    return beanFactory -> {
        // ...
    };
}
~~~

Spring may have to instantiate **ReportService** immediately to supply the factory method parameter, before metadata processing has finished. That bean could be created prematurely, miss ordinary post-processors, or trigger warnings about beans not being eligible for full post-processing.

**Do not retrieve application beans inside a BFPP** via constructor injection, field injection, or calling **beanFactory.getBean(...)**. A BFPP should work with BeanDefinitions and infrastructure configuration, not run business logic or consume application services.

If configuration data is needed, consider an appropriate metadata source such as `Environment` or simple configuration already available, while avoiding forcing the container to instantiate ordinary application beans at this early stage.

## 10. How Are Multiple BeanFactoryPostProcessors Ordered?

An application may have multiple post-processors. Execution order can matter if a second processor depends on metadata modified by the first.

Spring supports ordering BFPPs discovered in the context through two interfaces:

- **PriorityOrdered:** higher-priority group.
- **Ordered:** next group, sorted by order value.
- BFPPs implementing neither interface run after the ordered groups.

Example:

~~~java
import org.springframework.beans.factory.PriorityOrdered;
import org.springframework.beans.factory.config.BeanFactoryPostProcessor;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;

public class EarlyMetadataProcessor
        implements BeanFactoryPostProcessor, PriorityOrdered {

    @Override
    public int getOrder() {
        return 0;
    }

    @Override
    public void postProcessBeanFactory(
            ConfigurableListableBeanFactory beanFactory) {
        // Process metadata in the PriorityOrdered group.
    }
}
~~~

Another processor can implement **Ordered** and return an appropriate order value. Lower order values are generally processed earlier within the same comparison group.

### Note on Programmatic Registration

If a BFPP is added directly via **ConfigurableApplicationContext.addBeanFactoryPostProcessor(...)**, Spring processes programmatically registered processors before those discovered from bean definitions; direct registration order is used, and `PriorityOrdered`/`Ordered` sorting semantics do not apply in the same way as for auto-discovered beans.

Therefore, when intentional ordering is needed, understand how each BFPP is registered. Do not rely on incidental class or configuration file ordering.

### Can @Order Replace Ordered?

For BFPPs, the explicit approach documented by Spring is implementing **PriorityOrdered** or **Ordered**. Do not assume placing **@Order** on any BFPP class will enforce ordering across all registration mechanisms.

## 11. PropertySourcesPlaceholderConfigurer as a Built-In BFPP Example

Applications commonly use placeholders:

~~~java
@Value("\${app.report-timeout:5000}")
private int timeout;
~~~

Or values inside a bean definition:

~~~xml
<property name="timeout" value="\${app.report-timeout}"/>
~~~

Spring provides **PropertySourcesPlaceholderConfigurer**, a BeanFactoryPostProcessor, to resolve placeholders from property sources and replace them with appropriate values.

In Spring Boot, Environment and placeholder configuration are normally auto-configured. You generally do not need to declare this configurer manually in a standard Boot application. Still, it is a helpful example for understanding how BFPP is used within Spring infrastructure.

In a plain Spring Framework application or specialized setup, it can be declared as:

~~~java
@Configuration
public class PlaceholderConfiguration {

    @Bean
    public static PropertySourcesPlaceholderConfigurer propertySourcesPlaceholderConfigurer() {
        return new PropertySourcesPlaceholderConfigurer();
    }
}
~~~

The method is **static** because the bean returns a BFPP. This setup allows the placeholder configurer to participate in BeanFactory processing before ordinary beans are created.

## 12. What a BFPP Should Not Do

### Do Not Call getBean() to Invoke Business Services

~~~java
@Override
public void postProcessBeanFactory(
        ConfigurableListableBeanFactory beanFactory) {
    ReportService service = beanFactory.getBean(ReportService.class);
    service.generate();
}
~~~

This is improper usage. **getBean()** can force Spring to instantiate the bean prematurely before ordinary post-processors are fully registered. Furthermore, calling **generate()** runs business logic during metadata modification, mixing two responsibilities.

A BFPP should use **getBeanDefinition(...)**, not fetch application instances to invoke behavior.

### Do Not Use BFPP to Mutate Object Fields

A BFPP does not receive bean objects. If instance processing is needed, use BeanPostProcessor, `@PostConstruct`, or another properly timed mechanism.

### Do Not Register New Bean Definitions via an Ordinary BFPP

BFPP receives **ConfigurableListableBeanFactory**, not the dedicated registry API for registering definitions. If you need to add bean definitions, use **BeanDefinitionRegistryPostProcessor** or another appropriate registration mechanism.

### Do Not Use BFPP for Every Small Configuration Need

If the goal is merely assigning a timeout, URL, or batch size, prefer **@ConfigurationProperties**, **@Value**, constructor parameters on **@Bean**, or other explicit configuration. BFPP is powerful but complex and runs very early.

### Do Not Depend on Prematurely Created Beans

Fetching an application service or datasource from a BFPP can cause early initialization and interfere with post-processing. Keep BFPPs independent of application beans.

## 13. Comparing Related Extension Points

| Mechanism | Operates on | Purpose |
|---|---|---|
| **BeanDefinitionRegistryPostProcessor** | BeanDefinition registry | Adds or modifies bean definitions during the registry phase |
| **BeanFactoryPostProcessor** | BeanFactory and BeanDefinition metadata | Adjusts metadata/configuration before ordinary beans are created |
| **BeanPostProcessor** | Bean instances | Processes objects before/after initialization |
| **InitializingBean** | A bean instance | Init callback after properties are set |
| **@PostConstruct** | A bean instance | Annotation-based init callback |
| **SmartInitializingSingleton** | Eager singletons after creation | Callback once ordinary eager singletons are initialized |
| **ApplicationRunner** | Application after context refresh | Runs startup tasks at the Spring Boot level |

Decision tree:

~~~text
Need to add a BeanDefinition?
        │
        ├── Yes → BeanDefinitionRegistryPostProcessor
        │
        └── No
             │
             ▼
       Need to modify metadata before bean creation?
             │
             ├── Yes → BeanFactoryPostProcessor
             │
             └── No
                  │
                  ▼
          Need to process a bean instance?
                  │
                  ├── Before/after init → BeanPostProcessor
                  ├── Init callback → @PostConstruct / InitializingBean
                  └── After all eager singletons → SmartInitializingSingleton
~~~

## 14. Example: Verifying Metadata Without Early Bean Instantiation

One way to verify that a BFPP modified metadata is to inspect the **BeanDefinition** in a test context, rather than calling **getBean()** prematurely.

Example checking lazy-init:

~~~java
try (var context =
        new AnnotationConfigApplicationContext(
                MetadataConfiguration.class,
                ReportService.class)) {

    var beanFactory = context.getDefaultListableBeanFactory();
    var definition = beanFactory.getBeanDefinition("reportService");

    assertTrue(definition.isLazyInit());
}
~~~

The snippet above is the illustrative body; a complete test requires importing JUnit assertions and configuring matching components/bean names. It inspects metadata with **getBeanDefinition**, without forcing **ReportService** instantiation.

To verify an added property value:

~~~java
var definition = beanFactory.getBeanDefinition("batchProcessor");
Object configuredValue = definition.getPropertyValues()
        .get("batchSize");

assertEquals(200, configuredValue);
~~~

This verifies **metadata**. To verify the final value on the bean instance, request the bean from the container and read the property:

~~~java
BatchProcessor processor = context.getBean(BatchProcessor.class);
assertEquals(200, processor.getBatchSize());
~~~

These two checks answer two different questions:

- Was the metadata modified properly by the BFPP?
- When the bean was created, did the BeanFactory apply that metadata to the object?

## 15. Common Pitfalls When Implementing BFPPs

**Using a non-static @Bean method to declare a BFPP.** The configuration class may be instantiated prematurely. Prefer static factory methods for BFPP/BDRPP.

**Injecting business services into a BFPP.** Dependencies may be created before post-processing finishes. BFPPs should operate on metadata, not execute business logic.

**Calling getBean() inside postProcessBeanFactory().** This can instantiate objects prematurely and skip full processing by ordinary post-processors.

**Confusing BFPP with BeanPostProcessor.** BFPP edits BeanDefinitions; BeanPostProcessor processes object instances.

**Using BFPP to add new bean definitions.** Use BeanDefinitionRegistryPostProcessor when registering definitions.

**Forgetting that bean names can differ from class names.** Check the registered name or declare explicit names via stereotypes/`@Bean`.

**Changing scope without understanding the impact.** Switching singleton to prototype can alter state, lifecycle, instance count, and dependency injection behavior.

**Setting lazy-init and expecting eager dependents not to create the bean.** A lazy bean can still be created early when an eager bean requires it.

**Relying on unguaranteed ordering.** If multiple post-processors depend on one another, use `PriorityOrdered`/`Ordered` or programmatic registration order properly.

**Running business tasks inside a BFPP.** BFPPs run during early startup; never use them to send emails, import data, or process orders.

## 16. When Should You Use BeanFactoryPostProcessor?

BFPP is best suited when building **infrastructure, internal frameworks, integration libraries, or general-purpose configuration mechanisms** that must adjust bean definitions before instances are created.

Examples worth considering:

- A library marking a group of beans lazy based on metadata.
- An internal platform adding default property values to bean definitions by convention.
- An integration adjusting autowire candidate or primary flags for selected bean definitions.
- A framework modifying metadata of beans registered by component scanning/auto-configuration.
- A configurer resolving placeholders in bean definitions.

For everyday business code, simpler alternatives are usually better:

| Need | Clearer mechanism |
|---|---|
| Supplying required dependencies | Constructor injection |
| Binding configuration into classes | `@ConfigurationProperties` or `@Value` |
| Creating beans with constructor/factory logic | `@Bean` |
| Processing objects after creation | `@PostConstruct` or `BeanPostProcessor` |
| Choosing implementations by environment | `@Profile` / conditional configuration |
| Registering a specific additional bean | `@Bean` or `@Import` |

Do not use BFPP simply because it can alter lots of metadata. Use it when the requirement genuinely belongs in the **BeanDefinition processing phase**.

## 17. Practice: Observing the Order and Effect of a BFPP

Create a small Spring Boot project with **BatchProcessor** and **ReportService** classes. Register a BFPP via a static `@Bean` method. Inside the callback, operate strictly on bean definitions:

1. Read the **batchProcessor** definition.
2. Add property value **batchSize = 200**.
3. Read the **reportService** definition.
4. Set **lazyInit = true**.
5. Do not call **getBean()** inside the callback.

After context refresh:

- Inspect metadata to confirm **batchProcessor** has the new property value.
- Inspect metadata to confirm **reportService** is marked lazy.
- When actually calling **getBean(ReportService.class)**, observe the bean being created only then.
- Try having an eager singleton depend on `ReportService` and observe that the lazy dependency is still created to satisfy the dependency.

Next, create a **BeanPostProcessor** that simply logs before/after initialization to see it operate on instances after the BeanFactory has processed metadata. Then try a **BeanDefinitionRegistryPostProcessor** that registers an additional definition and observe the timing of the registry phase.

The goal is recognizing the three layers:

~~~text
Registry post-processor
    → modifies the list of BeanDefinitions

BeanFactory post-processor
    → modifies BeanDefinition metadata

Bean post-processor
    → processes bean objects during initialization
~~~

## Conclusion

**BeanFactoryPostProcessor** is a Spring extension point for modifying **BeanFactory and BeanDefinition metadata before ordinary application beans are created**. It can adjust lazy-init, scope, property values, primary flags, or other relevant metadata settings.

Keep the distinctions clear:

- **BeanDefinitionRegistryPostProcessor** is used when adding or modifying the bean definition registry at an earlier stage.
- **BeanFactoryPostProcessor** is used when adjusting BeanFactory metadata/configuration.
- **BeanPostProcessor** is used when processing bean instances before or after initialization.

When declaring a BFPP with **@Bean**, prefer a **static** factory method and avoid retrieving application beans in the callback so premature instantiation is not triggered. For ordinary Spring Boot applications, prefer dependency injection, **@ConfigurationProperties**, **@Bean**, and direct configuration annotations; reserve BFPP for cases that genuinely require metadata-layer intervention.
