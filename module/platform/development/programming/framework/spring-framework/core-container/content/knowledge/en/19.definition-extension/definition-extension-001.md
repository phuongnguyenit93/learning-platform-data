# Distinguishing BeanDefinition Modification from Bean Instance Processing in Spring Framework

## 1. Objective and Problem to Solve

A Spring application can extend how the container registers, configures, and instantiates beans. Two particularly easy-to-confuse extension points are **`BeanFactoryPostProcessor`** and **`BeanPostProcessor`**. Their names differ by only the word `Factory`, yet they operate on two completely different targets:

- **`BeanFactoryPostProcessor` (BFPP)** reads/modifies **`BeanDefinition`**, which is the metadata that BeanFactory uses to create objects.
- **`BeanPostProcessor` (BPP)** receives a **bean instance** during initialization and can observe, customize, or replace the returned reference, typically with a proxy.
- **`BeanDefinitionRegistryPostProcessor` (BDRPP)** extends BFPP to register additional bean definitions during the early registry phase.

This lesson belongs to **Definition Extension** of Spring Framework Core Container. After studying it, you will accurately distinguish *definition-time* from *instance-time*, know the methods and lifecycle of each SPI, run a Java 17/Spring Framework 6.x example yourself to verify the order, and avoid bugs caused by instantiating beans too early.

## 2. A BeanDefinition Is Not a Bean Object

### 2.1. BeanDefinition Is a Recipe

Spring stores bean creation metadata in `org.springframework.beans.factory.config.BeanDefinition`. Depending on how it is registered (XML, `@Configuration`, `@Component`, `@Bean`, or code), a definition can carry:

- Bean name, class, or factory method.
- Scope such as `singleton`, `prototype`, `request`.
- Constructor arguments, `MutablePropertyValues`, and autowire metadata.
- `lazyInit`, `dependsOn`, `primary`, qualifiers.
- Initialization/destruction method names.
- Attributes serving other framework extensions.

Illustrative metadata example, not a valid configuration file:

~~~text
BeanDefinition name="clientService"
    beanClass="demo.ClientService"
    scope="singleton"
    propertyValues:
       endpoint="https://api.example.invalid"
    initMethod="initialize"
~~~

Modifying `endpoint` in the definition **before instantiation** can cause Spring to use the new value when injecting the bean. However, modifying metadata **after a singleton has already been created** does not mean that object is automatically rebuilt or that the property currently inside the object changes immediately.

### 2.2. A Bean Instance Is an Actual Object

~~~text
BeanDefinition (metadata)
      |
      | constructor/factory method, dependency resolution
      v
Java bean instance (target)
      |
      | BeanPostProcessor + initialization callbacks
      v
Reference Spring provides to consumers
      |
      +-- may be the original instance itself
      +-- or a proxy/wrapper created by a BPP
~~~

A BeanDefinition can be used to create multiple instances according to scope. A BPP can process each instance; a BFPP changes the recipe rather than each object created afterward.

### 2.3. Quick Comparison

| Criterion | `BeanFactoryPostProcessor` | `BeanPostProcessor` |
| --- | --- | --- |
| Primary target | BeanFactory and `BeanDefinition` | Bean instance |
| Timing | After metadata registration, before regular bean instantiation | During each bean's initialization lifecycle |
| Main method(s) | `postProcessBeanFactory(...)` | `postProcessBeforeInitialization(...)` and `postProcessAfterInitialization(...)` |
| Can change property metadata? | Yes | Not its responsibility |
| Can replace returned reference? | Should not touch instances | Yes, e.g., returning a proxy |
| Should it call `getBean()` itself? | **Avoid:** may instantiate too early | Already receives the instance; still must avoid dependency cycles |
| Runs for every prototype instance? | No; processes the factory at bootstrap | Yes, whenever a prototype is created and passes through the processor |
| Framework example | `PropertySourcesPlaceholderConfigurer` | AOP auto-proxying, annotation/lifecycle processing |
| Scope of impact | Corresponding BeanFactory/context | Beans within the corresponding container |

**Rule of thumb:** to change the **bean creation recipe**, use BFPP/BDRPP. To change the **object during initialization**, use BPP.

## 3. Extension Sequence in ApplicationContext.refresh()

A simplified model:

~~~text
ApplicationContext.refresh()
    |
    +-- Prepare BeanFactory
    +-- Load / register BeanDefinitions
    |
    +-- BeanDefinitionRegistryPostProcessor
    |      postProcessBeanDefinitionRegistry(registry)
    |      -> add/modify definitions in the registry phase
    |
    +-- BeanFactoryPostProcessor
    |      postProcessBeanFactory(beanFactory)
    |      -> modify metadata before regular beans are created
    |
    +-- Create and register BeanPostProcessors
    |
    +-- Create eager singleton beans
            |
            +-- Instantiate
            +-- Inject dependencies / populate properties
            +-- BPP before-initialization callbacks
            +-- Initialization callbacks
            +-- BPP after-initialization callbacks
            +-- Bean/proxy is used
    |
    +-- Finish refresh()
~~~

The diagram above only describes the milestones meaningful for this lesson. Spring also handles the environment, factory methods, merged definitions, BeanFactory aware callbacks, and lifecycle infrastructure.

**Important nuance:** `@PostConstruct` is executed by an infrastructure BPP during the before-initialization phase. You cannot claim that `postProcessBeforeInitialization` of **every custom BPP** runs before `@PostConstruct`, because the order among different BPPs is determined by ordering. `InitializingBean.afterPropertiesSet()` and custom `initMethod` are invoked in the initialization logic between the BPP before and after groups.

Beyond the basic BPP interface, there are also `InstantiationAwareBeanPostProcessor` and `SmartInstantiationAwareBeanPostProcessor` with hooks before/after instantiation and property population. Therefore, the statement "a BPP can only intervene after the constructor has completed" is inaccurate when considering **the entire SPI family**. The two core methods presented here do indeed work with an already-created instance.

## 4. BeanFactoryPostProcessor: Processing Configuration Metadata

The `org.springframework.beans.factory.config.BeanFactoryPostProcessor` interface has the method:

~~~java
void postProcessBeanFactory(
    ConfigurableListableBeanFactory beanFactory);
~~~

This is an abbreviated signature, not a standalone Java program.

### 4.1. Modifying a BeanDefinition Properly

~~~java
@Override
public void postProcessBeanFactory(
        ConfigurableListableBeanFactory beanFactory) {

    BeanDefinition definition =
            beanFactory.getBeanDefinition("clientService");

    definition.getPropertyValues()
              .add("endpoint", "https://new.example.invalid");
}
~~~

This is a **BFPP class snippet**: it requires that bean name `clientService` is already registered and that the target bean has a valid `endpoint` setter/property. The code does not access any instance; it only adds a `PropertyValue` to the metadata. Since the bean has not been created yet, the container uses that value during the property population step.

Metadata changes can include constructor args, scope, lazy-init, property values, and other attributes. However, you must respect BeanDefinition semantics and avoid changing the class/factory method to an incompatible type.

### 4.2. Anti-pattern: Creating a Bean Directly Inside a BFPP

~~~java
@Override
public void postProcessBeanFactory(
        ConfigurableListableBeanFactory factory) {

    ClientService service = factory.getBean(ClientService.class);
    service.setEndpoint("https://new.example.invalid");
}
~~~

This is a **counter-example**. `getBean()` can instantiate a singleton when BPPs have not yet been fully registered, leading to:

1. The bean not receiving auto-proxying like other beans.
2. The dependency graph being cascade-initialized too early.
3. Certain injection/initialization callbacks not being processed properly.
4. Circular dependencies or an unready context state.
5. Behavior varying depending on startup order.

The Spring Reference directly advises: a BFPP should work with **bean configuration metadata**, not with bean instances. If the goal is to modify an object after creation, write a BPP.

### 4.3. When and How Often Does a BFPP Run?

During a context's BeanFactory preparation pass, Spring invokes the applicable BFPPs **before creating regular non-processor beans**. A BFPP is not an interceptor running on every bean or every method call. A prototype definition may be used to create dozens of objects, yet the BFPP does not run dozens of times because it does not process individual objects.

With multiple `ApplicationContext` instances (parent/child), processors apply within the scope of the BeanFactory where they are registered. Do not assume a BFPP placed in a parent automatically modifies a child's definitions.

### 4.4. Built-in BFPPs in Spring

`PropertySourcesPlaceholderConfigurer` commonly participates in resolving placeholders in bean configuration. `CustomScopeConfigurer` registers custom scopes during the BeanFactory post-processing phase. These examples illustrate "extending the container before business beans are created," rather than directly intervening in individual instances after startup.

## 5. BeanPostProcessor: Processing Bean Instances

The `org.springframework.beans.factory.config.BeanPostProcessor` interface provides:

~~~java
Object postProcessBeforeInitialization(
    Object bean, String beanName);

Object postProcessAfterInitialization(
    Object bean, String beanName);
~~~

In modern Spring Framework, both methods have default implementations that return `bean` unchanged. Example code can override one or both.

### 5.1. What Do Before and After Mean?

For a typical bean:

~~~text
Constructor / factory method
       ↓
Dependency injection / property population
       ↓
BeanPostProcessor.beforeInitialization(bean, name)
       ↓
Spring initialization callbacks
       ↓
BeanPostProcessor.afterInitialization(bean, name)
       ↓
Reference returned to client
~~~

`BPP.postProcessBeforeInitialization` can inspect the injected state. `BPP.postProcessAfterInitialization` can inspect the initialized state or return a proxy. Note that `@PostConstruct` is processed by a BPP, so the exact position of the annotation callback relative to a custom BPP depends on processor ordering.

### 5.2. Keeping or Replacing the Reference?

~~~java
@Override
public Object postProcessAfterInitialization(
        Object bean, String beanName) {
    if ("clientService".equals(beanName)) {
        // Inspect, log, or wrap the bean.
    }
    return bean; // Keep the original reference.
}
~~~

If wrapping is needed, a BPP can return a **proxy** that satisfies the injection contract. Do not return an object incompatible with the bean type required by consumers. Spring AOP uses post-processors/autoproxy creators to select and create proxies during bean construction.

### 5.3. Do Not Confuse BPP with Method Interception

BPP callbacks run **when the bean is created**, not every time code invokes a business method. If logging is needed around every `service.execute()`, you need a proxy/interceptor/AOP or equivalent mechanism; a BPP that simply prints a log in after-initialization cannot do that by itself.

For prototype beans, each created object can be processed by BPPs. For singletons, normal initialization happens once per context; not every subsequent `getBean()` call invokes BPPs again.

### 5.4. Bean Type and Name in Callbacks

A BPP receives `Object bean` along with `String beanName`. You should filter:

~~~java
@Override
public Object postProcessAfterInitialization(
        Object bean, String name) {
    if ("clientService".equals(name)
            && bean instanceof ClientService service) {
        service.verifyConfiguration();
    }
    return bean;
}
~~~

This is an illustrative snippet assuming `verifyConfiguration()` is defined. For proxies or framework objects, checking by interface is sometimes more reliable than casting to an implementation class.

## 6. BeanDefinitionRegistryPostProcessor: Adding Definitions Before BFPP

`BeanDefinitionRegistryPostProcessor` (BDRPP) extends `BeanFactoryPostProcessor` and adds:

~~~java
void postProcessBeanDefinitionRegistry(
    BeanDefinitionRegistry registry);
~~~

It is used when you need to register/modify multiple definitions **in the registry phase** rather than only editing metadata of existing definitions.

Example:

~~~java
public class ClientRegistrar
        implements BeanDefinitionRegistryPostProcessor {

    @Override
    public void postProcessBeanDefinitionRegistry(
            BeanDefinitionRegistry registry) {
        if (!registry.containsBeanDefinition("dynamicClient")) {
            registry.registerBeanDefinition(
                    "dynamicClient",
                    new RootBeanDefinition(DynamicClient.class));
        }
    }

    @Override
    public void postProcessBeanFactory(
            ConfigurableListableBeanFactory beanFactory) {
        // No further metadata changes in this example.
    }
}
~~~

This is an **extension snippet**, requiring the `DynamicClient` class and imports for the corresponding Spring interfaces. It is not a standalone runnable file.

### BDRPP vs BFPP

- **BDRPP** receives a registry and can add new definitions before Spring proceeds to process BFPPs.
- **BFPP** mainly modifies metadata already managed by the BeanFactory.
- **BPP** only sees a bean instance when it is created from its definition.

`ConfigurationClassPostProcessor` is Spring's key example of a registry post-processor handling `@Configuration`, `@ComponentScan`, `@Import`, and `@Bean`. If implementing dynamic registration yourself, consider its order relative to this processor.

## 7. Standalone Runnable Example: One BeanDefinition Modified, One Instance Processed

This example does not require Spring Boot or a web server. It uses **Java 17, Spring 6.2.9, and GenericApplicationContext**, registering three bean definitions:

1. `DefinitionEditor implements BeanFactoryPostProcessor`.
2. `InstanceTracer implements BeanPostProcessor`.
3. `MessageService implements InitializingBean`.

The first processor modifies the `text` property of `MessageService` **before the instance exists**. The second processor prints instance information before/after initialization. The program prints a sequence sufficient to verify the difference yourself.

### 7.1. Directory Tree

~~~text
bean-extension-demo/
├── pom.xml
└── src/main/java/demo/
    └── DefinitionVsInstanceDemo.java
~~~

### 7.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>bean-extension-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
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
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 7.3. src/main/java/demo/DefinitionVsInstanceDemo.java

~~~java
package demo;

import org.springframework.beans.factory.InitializingBean;
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.beans.factory.config.BeanFactoryPostProcessor;
import org.springframework.beans.factory.config.BeanPostProcessor;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.context.support.GenericApplicationContext;

public class DefinitionVsInstanceDemo {

    public static void main(String[] args) {
        try (GenericApplicationContext context =
                     new GenericApplicationContext()) {

            context.registerBean("messageService", MessageService.class);
            context.registerBean("definitionEditor", DefinitionEditor.class);
            context.registerBean("instanceTracer", InstanceTracer.class);

            context.refresh();

            MessageService service =
                    context.getBean("messageService", MessageService.class);
            System.out.println("result: " + service.getText());
        }
    }

    public static class MessageService implements InitializingBean {
        private String text;

        public MessageService() {
            System.out.println("construct: MessageService");
        }

        public void setText(String text) {
            this.text = text;
            System.out.println("setter: " + text);
        }

        public String getText() {
            return text;
        }

        @Override
        public void afterPropertiesSet() {
            System.out.println("init: " + text);
        }
    }

    public static class DefinitionEditor
            implements BeanFactoryPostProcessor {

        @Override
        public void postProcessBeanFactory(
                ConfigurableListableBeanFactory beanFactory) {

            BeanDefinition definition =
                    beanFactory.getBeanDefinition("messageService");

            definition.getPropertyValues()
                    .add("text", "from-definition");

            System.out.println("BFPP: definition changed");
        }
    }

    public static class InstanceTracer implements BeanPostProcessor {

        @Override
        public Object postProcessBeforeInitialization(
                Object bean, String beanName) {

            if ("messageService".equals(beanName)) {
                MessageService service = (MessageService) bean;
                System.out.println("BPP before: " + service.getText());
            }
            return bean;
        }

        @Override
        public Object postProcessAfterInitialization(
                Object bean, String beanName) {

            if ("messageService".equals(beanName)) {
                MessageService service = (MessageService) bean;
                System.out.println("BPP after: " + service.getText());
            }
            return bean;
        }
    }
}
~~~

All Java classes are nested `public static` inside one properly named file. `GenericApplicationContext.registerBean(...)` registers the bean definitions. When `refresh()` runs, Spring automatically detects both processor beans, creates/runs them during the infrastructure phase, and only then pre-instantiates `MessageService`.

### 7.4. Compile and Run

From the `bean-extension-demo` directory:

~~~bash
java -version
mvn -version
mvn -q compile exec:java -Dexec.mainClass=demo.DefinitionVsInstanceDemo
~~~

**Program stdout** (excluding Maven/SLF4J logs depending on environment):

~~~text
BFPP: definition changed
construct: MessageService
setter: from-definition
BPP before: from-definition
init: from-definition
BPP after: from-definition
result: from-definition
~~~

### 7.5. Why Is This Exact Order Produced?

1. `DefinitionEditor.postProcessBeanFactory(...)` is called when metadata has been registered, before `MessageService`'s constructor. Prints `BFPP: definition changed`.
2. Spring creates the `MessageService` instance, printing `construct: MessageService`.
3. Spring populates the property from the BeanDefinition modified by the BFPP; the setter prints `setter: from-definition`.
4. `InstanceTracer.postProcessBeforeInitialization(...)` sees the object and field already have values, printing `BPP before: from-definition`.
5. Spring calls `InitializingBean.afterPropertiesSet()`, printing `init: from-definition`.
6. `InstanceTracer.postProcessAfterInitialization(...)` receives the object after init, printing `BPP after: from-definition`.
7. `context.getBean(...)` receives the initialized instance, printing `result: from-definition`.

The BPP in this example only observes the bean and returns the same reference; replacing the reference with a proxy requires suitable proxy infrastructure (JDK dynamic proxy/CGLIB). That is a separate instance-processing example, not part of BFPP modifying a BeanDefinition.

### 7.6. Try Modifying It Yourself

**Experiment A — remove BFPP:** remove the `definitionEditor` registration. `MessageService` is still created; `text` has no injected value, so the getter result is `null`. The BPP still observes before/after init.

**Experiment B — remove BPP:** remove the `instanceTracer` registration. The BFPP still modifies metadata; constructor/setter/`afterPropertiesSet()` still work, but without the two BPP lines.

**Experiment C — modify metadata:** change `"from-definition"` to `"configured-v2"`. The new value appears in the setter, initialization, BPP, and result without the BFPP needing to call `getBean()`.

**Experiment D — prototype:** register `messageService` with scope `prototype` before refresh. The BFPP still modifies **one definition**, while each `getBean()` call creating a new prototype target is processed by the BPP.

**Experiment E — proxy:** change the after-init BPP to return an object implementing an interface that the client injects. Do not return a JDK proxy implementing only an interface to an injection point expecting a concrete class, because of type mismatch.

## 8. Registering Processors with @Configuration and @Bean

### 8.1. BFPP as a static @Bean

~~~java
@Configuration
class ExtensionConfig {

    @Bean
    static BeanFactoryPostProcessor definitionEditor() {
        return factory -> {
            BeanDefinition def =
                    factory.getBeanDefinition("messageService");
            def.getPropertyValues().add("text", "configured");
        };
    }
}
~~~

This is an **illustrative configuration**, requiring imports for `@Configuration`, `@Bean`, `BeanFactoryPostProcessor`, `BeanDefinition`, and a `messageService` BeanDefinition with a `text` property. `BeanFactoryPostProcessor` is a functional interface, so a lambda is valid.

The Spring Reference recommends declaring `@Bean` methods returning a BFPP as **`static`**. BFPPs must be instantiated very early; if the factory method is an instance method on `@Configuration`, Spring may have to instantiate the configuration class before annotation processing completes, causing `@Autowired`, `@Value`, or `@PostConstruct` fields in that class not to be processed as expected.

### 8.2. BPP as a static @Bean

~~~java
@Configuration
class ExtensionConfig {

    @Bean
    static InstanceTracer instanceTracer() {
        return new InstanceTracer();
    }
}
~~~

This snippet uses `InstanceTracer` from the program in section 7. For BPPs as well, Spring recommends `static @Bean` and a **sufficiently specific return type** (the implementation or at least `BeanPostProcessor`) for early detection by type. Returning `Object` from a factory method makes it harder for the container to recognize before instantiation and can cause the BPP to be registered too late.

**Not every `@Bean` has to be static**. The recommendation above focuses on special infrastructure beans initialized before business beans.

### 8.3. Early-Instantiation and the "not eligible" Warning

A `BeanPostProcessor` or a bean it directly injects often must be created early while Spring registers processors. Business beans pulled in too early may not be eligible to be processed by **all BPPs**, especially AOP auto-proxying.

Typical log:

~~~text
Bean 'someBean' of type [...] is not eligible for getting
processed by all BeanPostProcessors
(for example: not eligible for auto-proxying)
~~~

The solution is not to suppress the log, but to examine **the processor's dependencies**, avoid injecting business beans into a BPP too early, and use a static factory method with no dependencies when feasible.

### 8.4. Programmatic Registration

BFPP before refresh:

~~~java
context.addBeanFactoryPostProcessor(
        beanFactory -> {
            BeanDefinition definition =
                    beanFactory.getBeanDefinition("messageService");
            definition.getPropertyValues()
                      .add("text", "configured");
        });
~~~

This is a snippet inside a method that has a suitable `context`, not a standalone class.

A BPP can also be registered:

~~~java
beanFactory.addBeanPostProcessor(new InstanceTracer());
~~~

**Key difference:** BPPs added via `addBeanPostProcessor(...)` follow **registration order**, not automatic reordering by `Ordered`; programmatically registered BPPs run before auto-detected BPPs. Therefore, if exact ordering is required, you must know the registration path, not just add an `@Order` annotation.

## 9. Ordering: PriorityOrdered, Ordered, and Processor Interactions

### 9.1. BFPP/BDRPP

Spring uses `PriorityOrdered`, `Ordered`, and special phase ordering to sort processors discovered from definitions. `BeanDefinitionRegistryPostProcessor` registry callbacks are processed early, followed by BFPP callbacks. Spring can continue discovering new BDRPPs registered by other BDRPPs.

If two processors both write to the `text` property, the result depends on order. Production code should avoid accidental conflicts, or establish explicit precedence.

### 9.2. BPP

For auto-detected `BeanPostProcessor` beans, `Ordered`/`PriorityOrdered` can be used to participate in sorting. Later BPPs in the chain receive the reference returned by earlier BPPs; if an earlier one produced a JDK proxy, casting to the implementation class in a later BPP may be invalid.

Do not assume your before-init BPP will always run before `@PostConstruct`: `@PostConstruct` lives in the callback system of an infrastructure BPP. Exact ordering can depend on version and processor priorities.

### 9.3. The Registration Path Affects Ordering

When auto-detecting BPP beans, Spring performs a sorting step. When calling `ConfigurableBeanFactory.addBeanPostProcessor` directly, invocation order governs and those BPPs take precedence before auto-detected BPPs. The "just add `@Order(1)`" fix may not work as expected with programmatic registration.

## 10. When BeanDefinitionRegistryPostProcessor Adds Definitions

A plugin framework might need to scan multiple implementation classes and then register definitions based on configuration. In that case:

~~~text
BDRPP → registerBeanDefinition("connectorA")
      ↓
BFPP → edit property/metadata of "connectorA"
      ↓
BeanFactory → create "connectorA" instance
      ↓
BPP → inspect/wrap instance
      ↓
Client uses bean
~~~

The three extension points **complement** one another. A sound design puts registration/configuration into BDRPP/BFPP and runtime observation/wrapping into BPP.

If you only need to declare a simple service, use `@Bean`/`@Component` instead of building a custom BDRPP. Extending the registry should be reserved for genuine **dynamic registration infrastructure or framework integration**.

## 11. Relationship with BeanFactory, FactoryBean, and AOP

Similar names, different roles:

| Interface | Role |
| --- | --- |
| `BeanFactory` | Container retrieving/managing beans |
| `FactoryBean<T>` | Special bean providing a **product object** via `getObject()` |
| `BeanFactoryPostProcessor` | Intervenes in BeanFactory's BeanDefinition metadata |
| `BeanDefinitionRegistryPostProcessor` | Adds/edits bean definitions early in the registry |
| `BeanPostProcessor` | Intervenes on bean instances during their lifecycle |
| Spring AOP auto-proxy creator | Infrastructure typically in the BPP family, deciding and returning proxies |

**Do not confuse `FactoryBean` with BFPP:** a FactoryBean creates a product; a BFPP modifies configuration. A FactoryBean also has a BeanDefinition and its product has a lifecycle, but sharing the word "Factory" does not make the two SPIs equivalent.

An AOP proxy may be created after an instance is initialized; metadata such as annotations and pointcuts help decide which objects should be proxied. This is a good illustration of cooperation between **definition/metadata** and **instance processing**.

## 12. Which Extension Should You Choose for Each Scenario?

### Scenario A: changing endpoints for many beans at startup

Choose **BFPP** if the data to change resides in the BeanDefinition and must be modified before instantiation. Avoid calling `getBean()` inside a BFPP to invoke setters on instances.

If the requirement is simply standard property binding, `@ConfigurationProperties`, `@Value`, or direct `@Bean` configuration may be simpler and easier to maintain than a custom BFPP.

### Scenario B: creating bean definitions from plugin descriptors

Choose **BDRPP**, because bean counts/names/types are unknown when writing the original configuration and must be registered into the registry.

### Scenario C: inspecting or decorating a bean after initialization

Choose **BPP**. For example, checking a marker interface after injection, adding a custom proxy, logging, or lifecycle instrumentation.

### Scenario D: changing a property of an already-serving singleton

**Do not** expect a runtime BFPP to automatically refresh the instance. Once a singleton exists, the BeanDefinition was only the initial bean-creation metadata. Design a synchronized reconfigure API, a refresh scope with an explicit contract, or an appropriate replaceable delegate.

### Scenario E: every business method call must have logging

**Do not** rely only on BPP logging callbacks at startup. Use a Spring AOP proxy/interceptor or appropriate business code. A BPP may play the role of **creating the proxy**, but its own callback does not run on every method invocation.

### Scenario F: a @Bean returning a BPP is declared as Object

Spring may fail to detect the BPP early by type from the factory method. Return the exact BPP/implementation type and consider `static @Bean`.

## 13. Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| BFPP modified metadata, but singleton did not change | Bean was already created/cached | Perform mutation before instance creation |
| AOP annotations have no effect | Calling `getBean()` too early in BFPP, or BPP dependency pulled bean in at startup | Avoid eager instantiation, check processor ordering |
| Log "not eligible for getting processed by all BeanPostProcessors" | Bean was instantiated while registering BPPs | Reduce BPP dependencies; prefer static @Bean |
| Non-static `@Bean` returning BFPP causes lifecycle conflict | Configuration class was created too early | Use a static factory method |
| BeanPostProcessor does not run | BPP was not registered/detected by Spring via return type | Register bean properly with clear return type |
| BPP ran, but no proxy appears | Implementation returns target without creating proxy; or bean was created early | Check after-init return value and auto-proxy infra |
| `@PostConstruct` runs before custom BPP | Ordering among BPPs, since `@PostConstruct` is handled by a BPP | Do not assume a single ordering for all BPPs |
| BFPP looks up BeanDefinition and reports missing | Wrong bean name/context or definition not yet registered | Use `containsBeanDefinition` and proper registry phase |
| BDRPP creates duplicate names | Not checking registry or attempting override | Check `containsBeanDefinition` and naming strategy |
| Two BFPPs modify the same property with confusing result | Unintended processor order | Use explicit ordering and avoid conflicts |
| BPP returns wrapper with incompatible injection type | Proxy does not implement API required by consumer | Use compatible interface/class proxy |
| `@Order` does not change manual BPP order | `addBeanPostProcessor` uses registration order | Fix the registration sequence |
| Processor in parent does not process child beans | Extension points are per-container | Register in the appropriate child context |
| Invalid property name passed to BeanDefinition | No matching setter/writable property | Check property metadata, constructor args, and type conversion |
| Expecting BPP to re-run on every `getBean()` | Singleton bean is already cached | Distinguish per-instance initialization from per-method interception |

### Systematic Diagnosis

1. Does the intended change affect **metadata** or **instance**?
2. For metadata: was the BeanDefinition registered in the right context under the right name?
3. Do we need to add new definitions (BDRPP) or only modify existing definitions (BFPP)?
4. Was any bean created earlier than when BPPs were registered?
5. If a BPP returns a proxy, are the reference and type received by consumers still compatible?
6. Are there multiple processors with different orderings?
7. Does a parent/child context or prototype scope affect callback counts?

## 14. Standard Testing for Both SPIs

### 14.1. Metadata Unit Test

Use `DefaultListableBeanFactory` and a `RootBeanDefinition`:

~~~java
DefaultListableBeanFactory factory =
        new DefaultListableBeanFactory();

factory.registerBeanDefinition(
        "messageService",
        new RootBeanDefinition(MessageService.class));

new DefinitionEditor().postProcessBeanFactory(factory);

Object text = factory.getBeanDefinition("messageService")
        .getPropertyValues()
        .getPropertyValue("text")
        .getValue();

if (!"from-definition".equals(text)) {
    throw new AssertionError("Definition was not updated");
}
~~~

This is a **unit test snippet**, requiring imports and the nested types from section 7, not a standalone runnable file. It proves that the BFPP updates the BeanDefinition, though it does not yet prove that the BPP is called by Spring.

### 14.2. Instance Callback Unit Test

Create `MessageService`, set state, then invoke `InstanceTracer.postProcessBeforeInitialization`/`postProcessAfterInitialization` manually and verify the returned reference. Processor logic is tested, though this test does not prove Spring auto-registers the BPP.

### 14.3. Integration Test

Run `GenericApplicationContext` as in the main example:

- BFPP runs before the target constructor is invoked.
- BeanDefinition property is applied by the setter.
- BPP before and after bracket `InitializingBean.afterPropertiesSet()`.
- Only the selected bean name prints logs.
- Switching to prototype ensures each instance is processed.
- Changing BPP to return a proxy keeps the injection type compatible.
- Registering BFPP/BPP in the right context does not trigger early instantiation.
- If using BDRPP, new definitions appear in the BFPP stage and can be instantiated normally.

Use `try-with-resources` to close the test context and release singleton resources.

## 15. Production Project Checklist

- [ ] Modify **BeanDefinition** → `BeanFactoryPostProcessor`.
- [ ] Register **new definitions** → `BeanDefinitionRegistryPostProcessor`.
- [ ] Process **bean instances** → `BeanPostProcessor`.
- [ ] Do not call `getBean()` inside a BFPP to mutate objects.
- [ ] Ensure processor beans are discovered/registered before business beans are instantiated.
- [ ] Use `static @Bean` for BFPP/BPP per Spring guidance when early infrastructure registration is needed.
- [ ] Configure explicit ordering (`PriorityOrdered`/`Ordered`) when multiple processors interact.
- [ ] Do not assume every BPP before-init always runs before `@PostConstruct`.
- [ ] Do not modify metadata late and expect a live singleton to change automatically.
- [ ] Do not overuse BFPP/BDRPP for simple configuration needs.
- [ ] Unit test metadata and instances separately; integration test to verify the full lifecycle.

## 16. Self-Check

**Question 1.** You need to change a default property on 50 beans before they are created. Which SPI do you choose?  
**Answer:** BeanFactoryPostProcessor, because BeanDefinition metadata needs to be changed.

**Question 2.** You need to wrap a bean with a proxy after initialization. Which SPI do you choose?  
**Answer:** BeanPostProcessor (or BPP-based AOP infrastructure).

**Question 3.** Why should a BFPP not call `getBean()`?  
**Answer:** It can instantiate beans when BPPs are not yet fully registered, causing missing proxying/lifecycle handling and triggering dependency cycles.

**Question 4.** How does BeanDefinitionRegistryPostProcessor differ from BFPP?  
**Answer:** It has an early-running registry callback to add/modify bean definitions, while still being a BFPP.

**Question 5.** Does a BPP re-run every time a singleton is retrieved via `getBean()`?  
**Answer:** No. A BPP processes an instance upon creation/initialization. A regular singleton is initialized only once per context.

**Question 6.** Does @PostConstruct always occur after all BPP before-initialization callbacks?  
**Answer:** No. @PostConstruct is processed by an infrastructure BPP, so its relative order against other BPPs depends on ordering.

**Question 7.** Why should a @Bean method returning a BFPP be declared static?  
**Answer:** Because BFPPs are created very early; a static method avoids instantiating the @Configuration instance when annotation processors are not yet ready.

**Question 8.** Does a BPP manually registered via addBeanPostProcessor use @Order the same way as an auto-detected BPP?  
**Answer:** Not in that way; registration order governs programmatic BPPs.

**Question 9.** When changing a BeanDefinition's scope after a singleton has already been created, does the old object turn into a prototype?  
**Answer:** No. Late metadata changes do not automatically replace a cached singleton instance.

**Question 10.** Do BFPP and BPP automatically affect all beans across parent and child ApplicationContexts?  
**Answer:** No. Extension processors operate within the scope of their respective container.

## Official Documentation

- [Spring Framework Reference — Container Extension Points](https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html): BFPP/BPP/ordering/early-instantiation.
- [Spring Framework Reference — Bean Overview](https://docs.spring.io/spring-framework/reference/core/beans/definition.html): BeanDefinition as a recipe.
- [Spring Framework Reference — Customizing the Nature of a Bean](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html).
- [Spring Framework Javadoc — BeanFactoryPostProcessor](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/beans/factory/config/BeanFactoryPostProcessor.html).
- [Spring Framework Javadoc — BeanPostProcessor](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/beans/factory/config/BeanPostProcessor.html).
- [Spring Framework Javadoc — BeanDefinitionRegistryPostProcessor](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/beans/factory/support/BeanDefinitionRegistryPostProcessor.html).
