# BeanFactoryPostProcessor, BeanDefinitionRegistryPostProcessor, and Points to Inspect

Spring provides two important extension points to intervene in the container's configuration before most business beans are created: **BeanFactoryPostProcessor (BFPP)** and **BeanDefinitionRegistryPostProcessor (BDRPP)**. They are related but serve two distinct tasks: BFPP processes the configuration of the BeanFactory after bean definitions have already been registered; BDRPP is called earlier so it can add to or adjust the set of bean definitions itself.

When compiling Spring Boot into a GraalVM Native Image, this difference becomes especially important. Spring AOT needs to analyze the bean structure at build time in order to generate initialization code. A processor that registers beans based on data only available when the application runs can cause the build-time and runtime bean sets to diverge, leaving the generated context no longer reflecting the intended application.

This lesson explains the roles, invocation order, registration methods, practical examples, and points that must be inspected when using BFPP/BDRPP in a Spring Boot AOT/native application.

## 1. Which layer do the two processors intervene in?

First, recall three kinds of objects:

- **BeanDefinition:** metadata describing a bean, such as class, constructor/factory method, scope, lazy flag, dependencies, and configuration values.
- **Bean instance:** the actual Java object created from a definition and managed by the container.
- **BeanFactory:** the component that stores definitions, creates instances, resolves dependencies, and manages the bean lifecycle.

BFPP and BDRPP primarily work with **metadata and factory structure**. They are not general-purpose tools for mutating business state on already-created objects.

### BeanFactoryPostProcessor

BFPP receives a `ConfigurableListableBeanFactory` and can inspect or modify already-registered bean definitions, for example:

- Changing property values or metadata of a definition.
- Adjusting scope, lazy initialization, or certain bean flags.
- Registering dependencies resolvable at the factory level when appropriate.
- Performing container configuration steps before regular singletons are instantiated.

BFPP runs after the bean definition registration phase. It is suitable when you need to **adjust existing metadata** or configure the BeanFactory.

### BeanDefinitionRegistryPostProcessor

BDRPP is a specialized kind of BFPP, extending BFPP and adding the callback:

~~~java
void postProcessBeanDefinitionRegistry(BeanDefinitionRegistry registry);
~~~

This callback is invoked while the registry can still accept additional definitions. A BDRPP can:

- Register a new bean definition.
- Check for an existing definition before adding one.
- Adjust or replace metadata according to explicit rules.
- Detect registered configurations and add related beans.

After the registry callback, BDRPP also has the `postProcessBeanFactory` callback inherited from BFPP. Therefore, BDRPP can participate in both the registry processing phase and the BeanFactory processing phase.

| Criterion | BFPP | BDRPP |
| --- | --- | --- |
| Primary purpose | Adjust the BeanFactory and existing definitions | Adjust the registry, especially registering additional definitions |
| Characteristic callback | `postProcessBeanFactory` | `postProcessBeanDefinitionRegistry`, followed by `postProcessBeanFactory` |
| Timing | After BDRPP registry callbacks | Earlier than regular BFPPs |
| Can add bean definitions in a dedicated callback? | No dedicated registry callback; use BDRPP for this task | Yes |
| Should business beans be created here? | No | No |
| Impact on AOT | Can alter metadata that AOT analyzes | Can alter the set of bean definitions recorded by AOT |

**Quick selection rule:** if you need to add bean definitions, consider BDRPP; if you need to adjust metadata of already-registered definitions, consider BFPP. If you only need to declare regular beans, prefer `@Component`, `@Bean`, auto-configuration, or `@Import` rather than writing a custom post-processor.

## 2. Distinguishing from BeanPostProcessor

The names of these processor types look similar, but they operate at different layers.

| Processor | Target operated on | Primary timing | Example tasks |
| --- | --- | --- | --- |
| BeanDefinitionRegistryPostProcessor | Registry holding bean definitions | Before regular BFPPs | Registering a definition for an implementation |
| BeanFactoryPostProcessor | BeanFactory and definition metadata | Before most regular singletons are created | Setting the lazy flag or modifying property metadata |
| BeanPostProcessor | Bean instance | During the creation and initialization of each bean | Wrapping with proxies, processing annotations, intervening before/after initialization |

For example, a `BeanPostProcessor` can wrap a bean in a proxy after the object is instantiated to apply additional behavior. BFPP is not the place to do that: when BFPP runs, business instances typically have not been created yet. Conversely, if you need to add a definition so Spring knows a bean exists, `BeanPostProcessor` is already too late.

## 3. Processing order during ApplicationContext initialization

In a typical Spring `ApplicationContext`, the high-level sequence is as follows:

~~~mermaid
flowchart TD
    A["Read configuration and register bean definitions"] --> B["Discover BeanDefinitionRegistryPostProcessors"]
    B --> C["Invoke postProcessBeanDefinitionRegistry"]
    C --> D["Invoke postProcessBeanFactory on BDRPPs"]
    D --> E["Invoke regular BeanFactoryPostProcessors"]
    E --> F["Register BeanPostProcessors"]
    F --> G["Instantiate regular eager singletons"]
    G --> H["Dependency injection and initialization callbacks"]
    H --> I["Context ready"]
~~~

This is a high-level diagram of the refresh process. Infrastructure processors may be instantiated early to serve preceding steps; do not assume every object in the application waits until step G to be created.

### Ordering via PriorityOrdered and Ordered

Spring supports ordering processors via these interfaces:

1. Processors implementing `PriorityOrdered` are processed before the `Ordered` group.
2. Within each ordered group, a smaller `getOrder()` value generally has higher priority.
3. Processors implementing neither ordering interface are processed after the ordered groups.

For BDRPP, Spring processes registry callbacks before regular BFPPs. Spring can also discover newly registered BDRPPs during processing and continue running registry callbacks before moving on to regular BFPPs.

Do not rely on an internal framework order number unless the application has an explicit requirement. If two processors depend on each other, make that relationship explicit, avoiding accidental ordering from bean declaration order or class names.

### A BDRPP has two callbacks

BDRPP has both a registry callback and a BeanFactory callback. Conceptually:

~~~java
public final class ExampleRegistryProcessor
        implements BeanDefinitionRegistryPostProcessor {

    @Override
    public void postProcessBeanDefinitionRegistry(
            BeanDefinitionRegistry registry) {
        // Add or adjust bean definitions.
    }

    @Override
    public void postProcessBeanFactory(
            ConfigurableListableBeanFactory beanFactory) {
        // Process the BeanFactory after the registry phase.
    }
}
~~~

The registry callback is for operating on definitions. The BeanFactory callback is where BFPP-equivalent work happens. If there is nothing to do in the second callback, you can leave the method body empty.

## 4. BDRPP example: registering a bean definition by a fixed rule

Suppose an application has an optional billing feature service. When application configuration requires adding this service to the context, we want to register its definition using BDRPP. The example below uses a fixed rule in code to focus on registry operations; in a real project, choose an appropriate configuration mechanism and ensure conditions can be determined in the AOT phase.

**FeatureService.java**

~~~java
package com.example.nativeimage;

public final class FeatureService {
    public String status() {
        return "feature-enabled";
    }
}
~~~

**FeatureServiceRegistry.java**

~~~java
package com.example.nativeimage;

import org.springframework.beans.BeansException;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.beans.factory.support.BeanDefinitionRegistry;
import org.springframework.beans.factory.support.BeanDefinitionRegistryPostProcessor;
import org.springframework.beans.factory.support.RootBeanDefinition;

public final class FeatureServiceRegistry
        implements BeanDefinitionRegistryPostProcessor {

    @Override
    public void postProcessBeanDefinitionRegistry(
            BeanDefinitionRegistry registry) throws BeansException {

        String beanName = "featureService";

        if (!registry.containsBeanDefinition(beanName)) {
            RootBeanDefinition definition =
                    new RootBeanDefinition(FeatureService.class);
            registry.registerBeanDefinition(beanName, definition);
        }
    }

    @Override
    public void postProcessBeanFactory(
            ConfigurableListableBeanFactory beanFactory) throws BeansException {
        // No BeanFactory adjustments needed in this example.
    }
}
~~~

**FeatureRegistryConfiguration.java**

~~~java
package com.example.nativeimage;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class FeatureRegistryConfiguration {

    @Bean
    public static FeatureServiceRegistry featureServiceRegistry() {
        return new FeatureServiceRegistry();
    }
}
~~~

Here:

- `FeatureServiceRegistry` registers a definition named `featureService` if the registry does not already have a definition with the same name.
- `RootBeanDefinition` describes the class the container will instantiate when an instance is needed.
- The `@Bean` method declaring the processor is `static` to avoid needing to instantiate the configuration class early just to obtain the BFPP/BDRPP.
- Registering a definition does not mean the `FeatureService` instance was created immediately inside the callback.

In a real application, ensure `FeatureService` is on the classpath when building native, and that any reflection/resources/proxies the service requires have appropriate hints declared by Spring or the library.

### Why check the bean name before registering?

Calling `registerBeanDefinition` with an existing name can cause an override or an error depending on registry/container policy. Checking `containsBeanDefinition` makes the registration rule clearer. However, if the name already exists and points to an incompatible definition, silently skipping it can mask configuration bugs. In a production application, decide explicitly whether to keep the old definition, intentionally replace it, or fail with an error.

## 5. BFPP example: adjusting metadata of an existing definition

Suppose `ReportService` is registered via a `@Bean` method. We want to set lazy initialization on this definition using a BFPP:

~~~java
package com.example.nativeimage;

import org.springframework.beans.BeansException;
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.beans.factory.config.BeanFactoryPostProcessor;

public final class ReportLazyPostProcessor
        implements BeanFactoryPostProcessor {

    @Override
    public void postProcessBeanFactory(
            ConfigurableListableBeanFactory beanFactory)
            throws BeansException {

        String beanName = "reportService";

        if (beanFactory.containsBeanDefinition(beanName)) {
            BeanDefinition definition =
                    beanFactory.getBeanDefinition(beanName);
            definition.setLazyInit(true);
        }
    }
}
~~~

Register the processor using a `static` method:

~~~java
@Configuration(proxyBeanMethods = false)
class ReportConfiguration {

    @Bean
    static ReportLazyPostProcessor reportLazyPostProcessor() {
        return new ReportLazyPostProcessor();
    }

    @Bean
    ReportService reportService() {
        return new ReportService();
    }
}
~~~

The expected result is that the `reportService` definition is marked lazy before Spring creates regular eager singletons. When another eager bean depends on `ReportService`, that dependency can still cause the service to be created early. The lazy flag is not a guarantee that the object will only be created upon the first HTTP request in every situation.

This example also shows that BFPP works with **`BeanDefinition`**, without needing to call `getBean("reportService")` to retrieve the instance and mutate the object.

## 6. Registering processors properly and avoiding premature instantiation

BFPP/BDRPP are special infrastructure components. Spring must discover and invoke them **before creating most regular beans**. How they are declared affects whether the framework recognizes the processor at the right time.

### Recommend using static `@Bean`

When registering a processor in `@Configuration`, declare the factory method as `static`:

~~~java
@Configuration(proxyBeanMethods = false)
class InfrastructureConfiguration {

    @Bean
    static FeatureServiceRegistry featureServiceRegistry() {
        return new FeatureServiceRegistry();
    }
}
~~~

Reason: to invoke a non-static factory method, Spring may have to instantiate the configuration class containing that method early. This can cause the configuration class and its related dependencies to be created before all `BeanPostProcessor`s are registered. Spring often logs warnings when a bean is created too early and is not eligible for processing by all post-processors.

### Declare a specific return type

Declare the return type as the concrete processor class or a processor interface that Spring can recognize:

~~~java
@Bean
static BeanFactoryPostProcessor timeoutPostProcessor() {
    return new TimeoutPostProcessor();
}
~~~

Avoid declaring an overly general type like `Object` if Spring cannot predict the processor type without instantiating the bean. A clear return type helps the container detect the processor during the early discovery phase.

### Keep processors lightweight with minimal dependencies

Do not inject a large business bean graph into a BFPP/BDRPP constructor. Processors are created early; injecting other dependencies can pull them up ahead of their intended timing and cause some beans to miss full `BeanPostProcessor` processing.

Prefer:

- Using simple, stable configuration parameters.
- Working directly with registry/BeanFactory metadata.
- Avoiding calling `beanFactory.getBean(...)` to retrieve business beans.
- Avoiding accessing databases, HTTP APIs, message brokers, or external systems.
- Not using processors to run business logic, write data, or produce production side effects.

If configuration must be read, use an appropriate configuration source and clearly distinguish whether that value belongs to build time or runtime. Especially with AOT, do not assume the build machine's environment variables match the production container environment.

## 7. An important built-in Spring processor

A classic example of a BDRPP is `ConfigurationClassPostProcessor`. This is Spring's infrastructure processor responsible for processing Java configurations based on `@Configuration` and related annotations.

It helps discover and process constructs such as:

- `@Bean` to register bean definitions from factory methods.
- `@ComponentScan` to find components.
- `@Import` to import additional configurations or registrars.
- `@ImportResource` to load supported resource configurations.
- Related conditions and configuration metadata.

The process can be visualized as:

~~~mermaid
flowchart TD
    A["Configuration classes and annotations"] --> B["ConfigurationClassPostProcessor"]
    B --> C["Analyze @Bean, @ComponentScan, @Import"]
    C --> D["Register additional BeanDefinitions"]
    D --> E["BFPPs process the BeanFactory"]
    E --> F["Spring creates bean instances per lifecycle"]
~~~

This explains why BDRPPs run before regular BFPPs: Spring needs to finish discovering configurations and registering definitions before other processors modify the BeanFactory based on that set of definitions.

If a requirement is simply adding configuration via `@Import`, `ImportBeanDefinitionRegistrar` may be a better extension point than writing a global BDRPP. If you only need to declare a fixed bean, `@Bean` or component scanning is usually simpler and easier for AOT to analyze.

## 8. How does Spring AOT handle these processors?

Spring AOT analyzes the `ApplicationContext` before native compilation. During this process, Spring builds and processes the container model to learn bean definitions, dependency relationships, and required metadata. BDRPPs/BFPPs can participate in shaping this `BeanFactory`.

AOT output can include:

- Code registering the bean definitions Spring recognized.
- Code supporting application context initialization.
- AOT contributions from frameworks or libraries.
- Runtime hints for required reflection, resource, proxy, or JNI operations.

~~~mermaid
flowchart TD
    S["Source + config + dependencies"] --> A["Spring AOT analyzes ApplicationContext"]
    A --> R["BDRPP registers definitions"]
    R --> F["BFPP processes BeanFactory metadata"]
    F --> G["AOT contributions and generated registrations"]
    G --> H["GraalVM Native Image compilation"]
    H --> N["Native executable"]
    N --> X["Runtime: create bean instances and serve requests"]
~~~

Key points to understand:

1. **Processors may run during the AOT phase:** when Spring analyzes the context to build the model and generated code, relevant post-processors are used to process the registry/factory.
2. **Definitions are shaped at build time:** if a processor registers beans based on fixed conditions and available classes, AOT can record that structure in the generated code.
3. **Bean instances still belong to the runtime lifecycle:** generated code describes how to initialize the context/beans; it does not mean business objects are created at build time and carried into production.
4. **Do not rely on "run exactly once" side effects:** depending on processor type, integration, and registration method, related logic may execute during AOT analysis and/or during context initialization. Use the official AOT contracts of the Spring version in use rather than relying on incidental ordering.

If a processor has custom logic that needs to contribute AOT code, Spring provides dedicated AOT extension SPIs such as `BeanFactoryInitializationAotProcessor` and `BeanRegistrationAotProcessor`. If you need to describe dynamic access capabilities for Native Image, use appropriate runtime hints such as `RuntimeHintsRegistrar`. Do not turn a regular BFPP into a dumping ground for all code generation and reflection registration logic.

## 9. Why can dynamic bean registration cause issues with Native Image?

Native Image relies on the closed-world assumption: required code, types, and dynamic access operations must be determined or declared at build time. Therefore, the set of bean definitions analyzed by Spring AOT must reflect the application structures the binary needs to support.

### Error-prone scenario

Suppose a BDRPP reads a database at runtime and registers a bean for each plugin:

~~~java
// Unsuitable pattern if the plugin list only exists at runtime.
for (PluginRecord plugin : pluginRepository.loadPlugins()) {
    registry.registerBeanDefinition(
            plugin.beanName(),
            createDefinition(plugin.className())
    );
}
~~~

This approach has multiple issues in AOT/native:

- The database may be unavailable or nonexistent at build time.
- The plugin list on the build machine may differ from production.
- A class name coming from runtime data does not prove that class is included in the native binary.
- Reflection constructors/methods and resources needed by the plugin may not be registered.
- The set of definitions recorded in generated code may not match production plugins.

Even if such a BDRPP runs on the JVM, that does not guarantee such a dynamic architecture is AOT-compatible.

### A more AOT-friendly design

If the list of implementations is finite and known in advance, include the implementations on the classpath/build and register them using an analyzable configuration:

~~~java
@Configuration(proxyBeanMethods = false)
class PluginConfiguration {

    @Bean
    UppercasePlugin uppercasePlugin() {
        return new UppercasePlugin();
    }

    @Bean
    LowercasePlugin lowercasePlugin() {
        return new LowercasePlugin();
    }
}
~~~

At runtime, the application can select an implementation based on configuration or requests through a registered factory/strategy. If completely new Java code must be loaded after the build, consider a separate process/plugin service boundary; a native executable is not an open class loader for arbitrarily adding new JARs.

### Distinguishing build-time conditions from runtime data

| Decision kind | Examples | How to handle |
| --- | --- | --- |
| Deciding whether a bean definition exists in the context | `@ConditionalOnProperty`, profiles, custom registry processor | Determine conditions in the AOT phase; build artifacts for the supported configuration variants |
| Choosing among already-present implementations | Selecting a strategy among registered beans | Can be decided at runtime via factory/strategy |
| Instance configuration values | URL, timeout, token, credentials | Read via appropriate runtime configuration; do not freeze secrets into the binary |
| New plugin class from an external JAR | Loading classes absent from build inputs | Cannot be supported out of the box by a built native executable; requires a different architecture or rebuild |

**Principle:** you can choose at runtime among beans and classes already prepared for the binary; do not expect runtime to arbitrarily expand the set of classes/definitions unknown to AOT.

## 10. Points to check during code review

When reviewing a BFPP/BDRPP in a Spring Boot Native Image project, check the following questions:

| Check point | Good sign | Sign needing review |
| --- | --- | --- |
| Purpose | Only handles appropriate metadata/registry work | Uses processor to run business logic or arbitrarily construct objects |
| Processor registration | `static` `@Bean`, clear return type | Non-static factory method or overly generic return type |
| Dependencies | Lightweight, does not pull in a large bean graph | Constructor injects repositories/services/clients |
| Registry impact | Clear names, existence checks, idempotent rules | Duplicate registrations, unintended overrides |
| Conditions | Based on configuration determinable at AOT | Based on database/network/requests available only at runtime |
| Ordering | Specified only when real dependencies exist and tested | Relies on internal order values or declaration order |
| AOT | Registration results are reproducible, with AOT/native tests | Relies on unstable side effects |
| Reflection/resources | Hints provided when needed, targeting exact members/resources | Assuming all dynamic access is supported merely because the definition exists |
| Version | Uses APIs matching pinned Spring Framework/Boot | Relies on internal APIs or generated code structure of another version |

### Red flags to avoid

- Calling `getBean` inside `postProcessBeanFactory` just to mutate a business bean.
- Opening database connections or making HTTP calls inside a registry callback.
- Reading a plugin list from an external file that may differ between build and runtime.
- Registering definitions under fixed names without checking the registry.
- Using a post-processor to replace auto-configuration or simple configuration classes.
- Assuming generated sources have fixed package/file names across all Spring versions.
- Editing generated code directly inside the build directory instead of fixing the source processor/configuration.

## 11. How to inspect when the application does not behave as expected

Diagnosing layer by layer saves more time than immediately adding reflection hints as soon as a native error appears.

### Step 1: Determine whether the definition exists

Use `BeanFactory` to check the definition:

~~~java
ConfigurableListableBeanFactory beanFactory =
        context.getBeanFactory();

boolean definitionExists =
        beanFactory.containsBeanDefinition("featureService");

System.out.println("definitionExists=" + definitionExists);
~~~

If false, inspect component scanning, `@Import`, profiles/conditions, and whether the BDRPP was registered/executed. If the bean was registered under an alias or another factory, check the exact bean name/type.

### Step 2: Distinguish definitions from singleton instances

~~~java
boolean singletonCreated =
        beanFactory.containsSingleton("featureService");

System.out.println("singletonCreated=" + singletonCreated);
~~~

A definition existing while its singleton has not yet been created is normal if the bean is lazy, prototype, or has not yet been requested. Do not conclude the registry processor failed merely because `containsSingleton` returns false.

### Step 3: Check processor logs and initialization timing

Log at the start of each callback to see whether the processor is invoked. Avoid logging sensitive data or invoking side effects in logs. Observe both build-time AOT logs and runtime logs of the native executable.

### Step 4: Verify AOT generated output

Run AOT processing according to your project's Maven/Gradle configuration. For example, with a Maven project that binds the goal to the `native` profile:

~~~bash
./mvnw -Pnative clean process-classes
~~~

With Gradle Native Build Tools configured:

~~~bash
./gradlew processAot
~~~

Exact task/goal names and output locations depend on plugin versions. Check the logs and generated source directory of your own project. Do not edit generated code; fix the source processor or configuration and rerun AOT.

### Step 5: Test the native build

Build the native executable using your project's toolchain and exercise business paths that use the registered bean. If the definition already exists but errors only appear when calling methods, check dependencies, initialization callbacks, reflection/resources/proxies, and Native Image metadata.

## 12. Common errors and resolutions

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| BDRPP is not invoked | Processor is not registered or return type was not recognized early | Check processor's bean definition, `static` `@Bean`, return type, and logs |
| Bean definition does not appear | Registry callback did not run or registration condition evaluated to false | Check profiles/conditions, processor order, classpath, and bean name |
| Definition exists, but bean cannot be created | Constructor/factory method/dependency error | Check root exception, dependency graph, and instance configuration |
| Configuration class created too early | Processor registered via non-static factory method or pulls dependencies early | Use `static` `@Bean`, reduce processor dependencies |
| Bean created before full proxy/post-processing | Processor or dependency initialized too early | Do not call `getBean` inside BFPP/BDRPP; inspect warnings about beans not eligible for full post-processing |
| Duplicate bean definition | Multiple processors register the same name or fail to check existing names | Establish ownership, define idempotent rules, and handle conflicts explicitly |
| JVM works, but native lacks reflection | Dynamically accessed type/member lacks hints | Register proper reflection metadata or use APIs/frameworks with AOT support |
| Native lacks resources | File not packaged or pattern mismatch | Check resource inputs and resource hints |
| Beans differ between build and runtime | Processor relies on environment data or external systems | Move structural decisions to build time or register a fixed set of implementations |
| Repeated processor runs cause side effects | Assuming callback runs only once or build/runtime are not cleanly separated | Make processor deterministic, avoid side effects, and use AOT SPIs for their intended purpose |

## 13. Practice exercise: testing a BDRPP in Spring AOT

Create a small Spring Boot application with two classes:

- `FeatureService` with a `status()` method returning a fixed string.
- `FeatureServiceRegistry` implementing `BeanDefinitionRegistryPostProcessor` and registering a definition named `featureService` if not already present.

Register the processor using a `static` `@Bean` in a configuration class. Then perform:

1. Run the application on the JVM and check `containsBeanDefinition("featureService")`.
2. Check `containsSingleton("featureService")` before and after calling `getBean` to see the difference between definition and instance.
3. Run Spring AOT processing and observe whether the processor is executed during the analysis phase.
4. Build the native executable and verify the same bean on the native build.
5. Add a property-based registration condition, then change the property between build and runtime to observe which conditions are decided during AOT.
6. Add a reflection call inside `FeatureService` (if you want to extend it) and separately verify the required runtime hints.

### Self-check questions

1. Why are BDRPPs processed before regular BFPPs?
2. How can a BFPP modify the lazy flag of an already-registered definition?
3. Why should a `@Bean` method declaring a BFPP/BDRPP be `static`?
4. Why can calling `getBean` inside a BFPP cause premature bean instantiation?
5. Is a BDRPP that registers beans based on a plugin list fetched from a production database suitable for Spring AOT? Why or why not?
6. Does a definition appearing in generated AOT code guarantee that all reflection inside the bean will work in native?
7. When custom AOT code generation is needed, why should you look at AOT SPIs rather than relying on side effects of a BFPP?

**Success criteria:** accurately distinguish BFPP, BDRPP, and `BeanPostProcessor`; describe the order of registry/factory callbacks; write a safe processor and register it properly; explain the processor's impact on Spring AOT; and separately diagnose missing-definition errors, instance-creation errors, and reachability-metadata errors in GraalVM Native Image.
