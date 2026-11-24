# Auto-Detected and Programmatic Post-Processor Registration in Spring Core Container

## 1. Goal: Extending the Container in the Right Phase with the Right Registration Approach

The Spring IoC Container provides **post-processors** so applications or integration frameworks can participate in definition registration, metadata configuration, and bean initialization. There are two common ways to organize them:

1. **Auto-detection:** declare a post-processor as a Spring bean inside an `ApplicationContext`. The context detects the corresponding type, registers it, and invokes it at the proper phase of `refresh()`.
2. **Programmatic registration:** instantiate the processor and pass it directly to the container API before beans are created, or invoke the callback manually when using a plain `BeanFactory`.

The difference **is not merely syntactic**. It affects **execution order**, **registration timing**, **the scope of beans that can be processed**, and **which processors Spring can discover automatically**.

### Three Key Interfaces

| Extension point | Scope of change | Key callback(s) | Typical timing |
| --- | --- | --- | --- |
| `BeanDefinitionRegistryPostProcessor` | **Registry holding bean definitions**: add/remove/adjust definitions early | `postProcessBeanDefinitionRegistry(BeanDefinitionRegistry)`, inherits `postProcessBeanFactory(...)` | Before regular metadata processing; before creating regular beans |
| `BeanFactoryPostProcessor` (BFPP) | **Metadata/bean definitions**, not yet created objects | `postProcessBeanFactory(ConfigurableListableBeanFactory)` | After bean definitions are prepared, before creating regular bean instances |
| `BeanPostProcessor` (BPP) | **Bean instance** being/just initialized; can inspect or return a proxy | `postProcessBeforeInitialization(Object,String)` and `postProcessAfterInitialization(Object,String)` | Around the init callbacks of each bean created after BPPs are registered |

`BeanDefinitionRegistryPostProcessor` extends `BeanFactoryPostProcessor`, so it also has the regular metadata callback. They are not two unrelated processors.

**An easy rule to remember:** registry processors change *which beans have definitions*; bean-factory processors change *how beans are described/configured*; bean post-processors change/wrap *the instances created from that configuration*.

## 2. Typical Startup Flow of ApplicationContext

~~~text
ApplicationContext.refresh()
  |
  +-- Load/parse bean definitions
  |      └-- e.g., ConfigurationClassPostProcessor reads @Configuration
  |
  +-- Invoke BeanDefinitionRegistryPostProcessors
  |      └-- may register additional bean definitions
  |
  +-- Invoke BeanFactoryPostProcessors
  |      └-- modify metadata/property values, do not create business beans
  |
  +-- Detect + instantiate + register BeanPostProcessors
  |      └-- this group is built early to process subsequent beans
  |
  +-- Pre-instantiate regular non-lazy singleton beans
  |      ├-- constructor/factory method
  |      ├-- dependency/property injection
  |      ├-- BPP.beforeInitialization()
  |      ├-- @PostConstruct, InitializingBean, custom init
  |      └-- BPP.afterInitialization() → may return proxy
  |
  +-- Finish initialization, context lifecycle/events
  |
  +-- ApplicationContext usable
~~~

This is a **conceptual diagram**, not an exhaustive list of every `refresh()` internal step or a claim that every BeanPostProcessor runs exactly once on every object in all situations. `@PostConstruct` is handled by an appropriate BeanPostProcessor, so its relative order against **custom pre-initialization BPPs** depends on processor ordering. Special beans such as `FactoryBean`, scoped proxies, processor bean definitions, and early-reference mechanisms involve additional details.

Do not interpret the diagram as saying every bean with `@Lazy` or `prototype` scope must be created before context refresh completes: they are normally created on demand; at that time, already-registered BPPs continue processing the new instances.

## 3. BeanFactoryPostProcessor: Processing Definitions, Not Instances

`BeanFactoryPostProcessor` has the contract:

~~~java
import org.springframework.beans.BeansException;
import org.springframework.beans.factory.config.BeanFactoryPostProcessor;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;

public final class LabelDefinitionPatch implements BeanFactoryPostProcessor {
    @Override
    public void postProcessBeanFactory(
            ConfigurableListableBeanFactory beanFactory)
            throws BeansException {
        if (beanFactory.containsBeanDefinition("messageBean")) {
            beanFactory.getBeanDefinition("messageBean")
                    .getPropertyValues()
                    .add("label", "configured");
        }
    }
}
~~~

The snippet above is an illustrative Java class; it **modifies a property value on a BeanDefinition**, without calling a setter on any bean instance. If class `MessageBean` has setter `setLabel(String)`, the property value is applied by Spring during subsequent bean creation.

A BFPP can add metadata, replace property values, or inspect definitions without creating beans. Some built-in Spring BFPPs resolve placeholders/configuration metadata through dedicated mechanisms.

**Do not call `beanFactory.getBean("messageBean")` inside a BFPP just to change a bean's value:** this forces bean creation **before BPP/auto-proxying registration completes**, which can result in missing AOP processing, annotation callbacks, or prematurely instantiating dependency beans. To modify an object, use `BeanPostProcessor` or appropriate injection/configuration.

If a new BeanDefinition must be **registered** early, especially so other processors observe it as well, `BeanDefinitionRegistryPostProcessor` is usually more suitable than a plain BFPP.

## 4. BeanDefinitionRegistryPostProcessor: Registering Additional BeanDefinitions

`BeanDefinitionRegistryPostProcessor` adds an extension callback in the registry phase:

~~~java
import org.springframework.beans.BeansException;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.beans.factory.support.BeanDefinitionRegistry;
import org.springframework.beans.factory.support.BeanDefinitionRegistryPostProcessor;
import org.springframework.beans.factory.support.RootBeanDefinition;

public final class ExtraTypeRegistrar
        implements BeanDefinitionRegistryPostProcessor {

    @Override
    public void postProcessBeanDefinitionRegistry(
            BeanDefinitionRegistry registry) throws BeansException {
        if (!registry.containsBeanDefinition("extraService")) {
            registry.registerBeanDefinition(
                    "extraService",
                    new RootBeanDefinition(ExtraService.class));
        }
    }

    @Override
    public void postProcessBeanFactory(
            ConfigurableListableBeanFactory beanFactory)
            throws BeansException {
        // Can adjust metadata after the registry phase if needed.
    }
}
~~~

This is an illustrative example class where `ExtraService` is a Java type to be defined; it is not a standalone application. Advantage: Spring can process newly added bean definitions **before regular bean instantiation**. This is also the extension point Spring uses for configuration processors such as `ConfigurationClassPostProcessor` (a BeanDefinitionRegistryPostProcessor with additional roles).

**Rule:** the registry callback should work on `BeanDefinitionRegistry`, and the factory callback should work on metadata; do not call business beans just to decide whether to register a definition.

## 5. BeanPostProcessor: Processing an Instance Before/After Init

`BeanPostProcessor` is called when Spring creates eligible beans after the processor has been registered. Two fundamental methods:

~~~java
import org.springframework.beans.factory.config.BeanPostProcessor;

public final class TaggingPostProcessor implements BeanPostProcessor {
    @Override
    public Object postProcessBeforeInitialization(
            Object bean, String beanName) {
        return bean;
    }

    @Override
    public Object postProcessAfterInitialization(
            Object bean, String beanName) {
        if ("messageBean".equals(beanName)
                && bean instanceof MessageBean message) {
            message.setTag("POST");
        }
        return bean;
    }
}
~~~

The snippet above is an illustrative class where `MessageBean` must have an appropriate setter. BPP receives a **bean instance and beanName**, not a BeanDefinition. In the `postProcessAfterInitialization` phase, a BPP can **return a different object** (proxy/wrapper) in place of the original target; that is the foundation of many AOP features.

Do not confuse the API names: `postProcessBeanFactory(...)` has no `beanName` and edits metadata; `postProcessAfterInitialization(...)` modifies/wraps an instance.

### BPP and @PostConstruct

Spring processes `@PostConstruct` through a lifecycle-annotation BeanPostProcessor. Therefore, a custom BPP must not automatically assume every `beforeInitialization` runs before `@PostConstruct`. Relative order depends on the BPP list/ordering.

Most business code does not need custom BPPs. This extension point is meant for cross-cutting framework logic across many beans, such as proxying, annotation conventions, infrastructure validation, or adapters.

## 6. Auto-Detection When Using ApplicationContext

In an `ApplicationContext`, you can declare a BFPP/BDRPP/BPP as a bean via `@Component` + component scanning, XML bean definitions, or `@Bean` in Java configuration.

~~~java
@Configuration(proxyBeanMethods = false)
public class ExtensionConfig {
    @Bean
    static BeanFactoryPostProcessor metadataProcessor() {
        return beanFactory -> {
            // Read/modify metadata (do not call getBean on business beans).
        };
    }

    @Bean
    static BeanPostProcessor instanceProcessor() {
        return new TaggingPostProcessor();
    }
}
~~~

This is an illustrative configuration, requiring imports for `@Configuration`, `@Bean`, `BeanFactoryPostProcessor`, `BeanPostProcessor`, and the `TaggingPostProcessor` class. When the config is registered and the context refreshes, Spring detects both processor beans by type and registers them into the appropriate pipeline.

**Requirements that must be met:**

- The processor's **bean definition** must enter the context before the corresponding detection phase. This can be via `@ComponentScan` or `register(Config.class)` with Java config.
- A `@Bean` returning a BPP should declare a **recognizable return type of `BeanPostProcessor` or the implementation**, not an overly generic return type like `Object`, because the container needs to detect the type before instantiating it.
- You should write `@Bean static` for BFPP and BPP, especially BFPP, to avoid forcing Spring to instantiate the `@Configuration` instance and the config's dependencies early.
- Do not put `@Lazy` and expect the processor to run only when the user calls `getBean`: processors are handled by the context during the startup phase.
- Post-processors are usually created very early. Avoid injecting heavy business services into the constructor of a BPP/BDRPP/BFPP.

For `BeanDefinitionRegistryPostProcessor`, you can declare a `@Bean static BeanDefinitionRegistryPostProcessor` or corresponding component. Registry processing must happen before most regular beans are created so that new definitions have the chance to participate in the normal lifecycle.

### Why Is static @Bean Important?

Example of a configuration **not to prefer**:

~~~java
@Configuration
public class BadConfig {
    @Autowired
    private DataSource dataSource;

    @Bean
    BeanFactoryPostProcessor metadataProcessor() {
        return factory -> { /* ... */ };
    }
}
~~~

Because BFPP must be created **early**, a non-static method can force Spring to instantiate `BadConfig` before regular annotation processing steps complete. Callbacks/annotations on the configuration class itself, such as `@Autowired` and `@PostConstruct`, risk being skipped; Spring may log an INFO warning about a non-static BFPP `@Bean` method.

Preferred version:

~~~java
@Configuration
public class GoodConfig {
    @Bean
    static BeanFactoryPostProcessor metadataProcessor() {
        return factory -> { /* ... */ };
    }
}
~~~

There is no reason to pass a business `DataSource` into a processor just to read a BeanDefinition. Avoid forcing heavy infrastructure dependencies to be created early.

## 7. Programmatic Registration of BeanFactoryPostProcessor on ApplicationContext

With `ConfigurableApplicationContext` (such as `AnnotationConfigApplicationContext`), you can add a BFPP instance **before `refresh()`**:

~~~java
var context = new AnnotationConfigApplicationContext();
context.register(AppConfig.class);
context.addBeanFactoryPostProcessor(new LabelDefinitionPatch());
context.refresh();
try {
    // Use beans created by the context.
} finally {
    context.close();
}
~~~

This is an illustrative example, requiring valid `AppConfig` and `LabelDefinitionPatch` classes. The context does not auto-refresh when using the no-arg constructor, allowing BFPPs to be added before refresh.

Distinguish the two operations:

- **Declaring a BFPP as a bean:** Spring auto-detects the processor and invokes it during startup.
- **`addBeanFactoryPostProcessor(instance)`:** adds the processor instance directly into the context's list so it is invoked on refresh; no separate bean definition for the processor instance is required.

Do not call `addBeanFactoryPostProcessor` **after `refresh()` has already finished** and expect it to update already-created singletons. Adding to the list does not automatically re-run the entire pipeline, does not destroy/recreate beans, and does not guarantee retroactive application.

### Ordering for Programmatic BFPPs

Per Spring's javadoc, **auto-detected** `BeanFactoryPostProcessor` beans in an ApplicationContext are processed according to `PriorityOrdered` and `Ordered` semantics. However, BFPPs **registered programmatically** with `ConfigurableApplicationContext` apply in **registration order**, not by ordering interfaces. `@Order` on a BFPP class is also **not** used as an automatic BFPP sorting switch.

If you have both programmatic BFPPs and auto-detected BFPPs, understand that they go through separate lists/passes; do not assume a single "unified total order" across the `getOrder()` numbers of both groups without verifying.

## 8. Programmatic Registration of BeanPostProcessor on BeanFactory

When using `DefaultListableBeanFactory` or a plain `ConfigurableBeanFactory`, you can register BPPs directly:

~~~java
DefaultListableBeanFactory factory = new DefaultListableBeanFactory();
factory.registerBeanDefinition(
        "messageBean", new RootBeanDefinition(MessageBean.class));

factory.addBeanPostProcessor(new TaggingPostProcessor());
MessageBean bean = factory.getBean("messageBean", MessageBean.class);
~~~

This is a snippet requiring imports for `DefaultListableBeanFactory`, `RootBeanDefinition`, and the illustrative classes. The key point is to **call `addBeanPostProcessor()` before creating the beans you want processed**.

A `BeanPostProcessor` added programmatically to `ConfigurableBeanFactory` will:

- Run in **direct registration order**; Spring **does not re-sort** them by `PriorityOrdered`/`Ordered`.
- Take precedence before auto-detected context BPPs if both sources exist in the same pipeline.
- Not recreate or retroactively run on beans already instantiated/cached before the BPP was added.

**Order verification example:** if you call `addBeanPostProcessor(A)` then `addBeanPostProcessor(B)`, programmatic BPPs run **A then B**, even if B implements `PriorityOrdered` and declares a very small order. Do not expect `getOrder()` values to reverse that order.

### A Plain BeanFactory Does Not Auto-Discover Processor Beans

If you write:

~~~java
factory.registerBeanDefinition(
        "myProcessor", new RootBeanDefinition(TaggingPostProcessor.class));
factory.registerBeanDefinition(
        "messageBean", new RootBeanDefinition(MessageBean.class));
~~~

then with a plain `DefaultListableBeanFactory`, the mere existence of bean definition `myProcessor` is **not enough** for it to join the BPP pipeline automatically. You must instantiate/register the processor programmatically via `addBeanPostProcessor(...)`, or bootstrap the container via an ApplicationContext that supports auto-detection.

Similarly, merely registering a `BeanFactoryPostProcessor` as a bean definition in a plain BeanFactory **does not cause it to run automatically**; you must call `postProcessBeanFactory(...)` during the appropriate preparation step when using BeanFactory directly, or switch to `ApplicationContext`.

## 9. BeanFactoryPostProcessor with a Plain BeanFactory Must Be Invoked Explicitly

A minimal example for metadata transformation:

~~~java
DefaultListableBeanFactory factory = new DefaultListableBeanFactory();
factory.registerBeanDefinition(
        "messageBean", new RootBeanDefinition(MessageBean.class));

// Plain factory does not auto-detect BeanFactoryPostProcessor.
new LabelDefinitionPatch().postProcessBeanFactory(factory);

// BPP instance pipeline must be registered separately before getBean().
factory.addBeanPostProcessor(new TaggingPostProcessor());

MessageBean bean = factory.getBean("messageBean", MessageBean.class);
~~~

This is a snippet assuming `LabelDefinitionPatch` and `TaggingPostProcessor` match the classes from earlier sections.

With a plain `BeanDefinitionRegistryPostProcessor`, you must also perform a call to `postProcessBeanDefinitionRegistry(factory)` when `factory` implements `BeanDefinitionRegistry`, before the `postProcessBeanFactory(factory)` callback. If there are **multiple registry processors** or complex `@Configuration` setups, manually sorting every processor is error-prone; using `ApplicationContext` so Spring orchestrates the full pipeline is usually safer.

### Calling Directly on a Processor That Is Already a Spring Bean?

When using `ApplicationContext`, do not both declare a processor as a bean for Spring auto-detection **and manually invoke callbacks or add the same instance again**, because you can cause double processing, alter ordering, apply property values twice, or wrap beans multiple times. Decide processor ownership clearly.

## 10. PriorityOrdered, Ordered, and @Order

Spring provides different ordering contracts. Within the standard **auto-detected** processor group:

1. `PriorityOrdered` implementations take priority over regular `Ordered`.
2. Smaller `Ordered.getOrder()` **numbers** represent higher priority within the applicable group.
3. Processors implementing no ordering run after the ordered groups, following container rules that may vary across processor sets.

Notable rule: order must not be relied upon from class names, `@Bean` names, file read order, package scan order, or method declaration position in source code.

| Registration | `PriorityOrdered` / `Ordered` | `@Order` annotation on class |
| --- | --- | --- |
| Auto-detected BFPP in `ApplicationContext` | Effective per contract | Not used to order BFPPs |
| Programmatic BFPP via `addBeanFactoryPostProcessor` | **Ignored**, processed in registration order | Not a way to control order |
| Auto-detected BPP in `ApplicationContext` | Effective per contract | Not used to order BPPs |
| Programmatic BPP via `addBeanPostProcessor` | **Ignored**, processed in registration order | Not a way to control order |
| BDRPP | Has special registry phases and pipeline ordering rules | Does not uniformly equate to regular BFPP group |

Note: `@Order` works in **other Spring scenarios** such as ordered injection collections, event listeners, or contextual AOP advice. That does not mean it replaces the `Ordered` interface in the specific contract for BFPP/BPP.

### Example of Interface Ordering

~~~java
public final class FirstMetadataProcessor
        implements BeanFactoryPostProcessor, PriorityOrdered {

    @Override
    public int getOrder() {
        return 0;
    }

    @Override
    public void postProcessBeanFactory(
            ConfigurableListableBeanFactory factory) {
        // Adjust metadata.
    }
}
~~~

This is a snippet requiring imports for `BeanFactoryPostProcessor`, `PriorityOrdered`, and `ConfigurableListableBeanFactory`. For **auto-detected** BFPPs, the order value matters; for **programmatically registered** BFPPs, registration order takes precedence.

## 11. Runnable Java 17 Example: Auto-Detection and Programmatic Registration

Comparison example in **a single program**:

- `AnnotationConfigApplicationContext` auto-detects `BeanFactoryPostProcessor` and `BeanPostProcessor` declared via static `@Bean`.
- A plain `DefaultListableBeanFactory` registers the bean definition and then **explicitly invokes** BFPP and **explicitly adds** BPP to the pipeline.
- Both approaches can achieve the same metadata configuration and instance intervention logic, yet ownership and activation timing differ.

Uses Java 17, Maven, Spring Framework 6.2.12. No Spring Boot, web server, or annotation scanning outside Java config is needed.

File structure:

~~~text
post-processor-registration/
├── pom.xml
└── src/main/java/example/PostProcessorRegistrationDemo.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>post-processor-registration</artifactId>
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

`src/main/java/example/PostProcessorRegistrationDemo.java`:

~~~java
package example;

import org.springframework.beans.BeansException;
import org.springframework.beans.factory.config.BeanFactoryPostProcessor;
import org.springframework.beans.factory.config.BeanPostProcessor;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.beans.factory.support.DefaultListableBeanFactory;
import org.springframework.beans.factory.support.RootBeanDefinition;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class PostProcessorRegistrationDemo {

    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(AutoConfig.class)) {
            MessageBean bean = context.getBean("messageBean", MessageBean.class);
            System.out.println("Auto: " + bean.render());
        }

        DefaultListableBeanFactory factory = new DefaultListableBeanFactory();
        factory.registerBeanDefinition(
                "messageBean", new RootBeanDefinition(MessageBean.class));

        // Plain BeanFactory: BFPP must be invoked; BPP must be added.
        new SetLabelDefinitionProcessor("MANUAL")
                .postProcessBeanFactory(factory);
        factory.addBeanPostProcessor(new TaggingBeanPostProcessor());

        MessageBean bean = factory.getBean("messageBean", MessageBean.class);
        System.out.println("Manual: " + bean.render());

        factory.destroySingletons();
    }

    @Configuration(proxyBeanMethods = false)
    public static class AutoConfig {
        @Bean("messageBean")
        public MessageBean messageBean() {
            return new MessageBean();
        }

        // static avoids creating @Configuration instance too early.
        @Bean
        public static BeanFactoryPostProcessor autoMetadataProcessor() {
            return new SetLabelDefinitionProcessor("AUTO");
        }

        @Bean
        public static BeanPostProcessor autoInstanceProcessor() {
            return new TaggingBeanPostProcessor();
        }
    }

    public static final class MessageBean {
        private String label = "DEFAULT";
        private String tag = "NONE";

        public MessageBean() {
        }

        public void setLabel(String label) {
            this.label = label;
        }

        public void setTag(String tag) {
            this.tag = tag;
        }

        public String render() {
            return label + "|" + tag;
        }
    }

    public static final class SetLabelDefinitionProcessor
            implements BeanFactoryPostProcessor {
        private final String label;

        public SetLabelDefinitionProcessor(String label) {
            this.label = label;
        }

        @Override
        public void postProcessBeanFactory(
                ConfigurableListableBeanFactory beanFactory)
                throws BeansException {
            beanFactory.getBeanDefinition("messageBean")
                    .getPropertyValues()
                    .add("label", label);
        }
    }

    public static final class TaggingBeanPostProcessor
            implements BeanPostProcessor {
        @Override
        public Object postProcessAfterInitialization(
                Object bean, String beanName) throws BeansException {
            if ("messageBean".equals(beanName)
                    && bean instanceof MessageBean message) {
                message.setTag("BPP");
            }
            return bean;
        }
    }
}
~~~

Run command from the `post-processor-registration` directory:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.PostProcessorRegistrationDemo
~~~

Stdout of **the `System.out.println` statements themselves** (excluding logging from Maven or SLF4J):

~~~text
Auto: AUTO|BPP
Manual: MANUAL|BPP
~~~

**Why does this result make sense?**

1. `AnnotationConfigApplicationContext(AutoConfig.class)` registers the config and calls `refresh()`. Both `@Bean static` methods declare explicit return types `BeanFactoryPostProcessor` and `BeanPostProcessor`, so the context can detect them in the right phases.
2. The auto BFPP finds BeanDefinition `messageBean` and sets property `label="AUTO"`. When creating the instance from `@Bean messageBean()`, Spring proceeds to process the bean definition's property values, calling `MessageBean.setLabel("AUTO")`.
3. The auto BPP checks name/type in `postProcessAfterInitialization`, calling `setTag("BPP")`. The caller receives `MessageBean`, so `render()` returns `AUTO|BPP`.
4. `DefaultListableBeanFactory` in the manual branch does not auto-discover processor beans. We proactively call `SetLabelDefinitionProcessor("MANUAL").postProcessBeanFactory(factory)` before `getBean`, then call `factory.addBeanPostProcessor(...)`.
5. The plain BeanFactory instantiates `MessageBean`, populates property `label="MANUAL"`, and invokes the registered BPP. Result: `MANUAL|BPP`.
6. `destroySingletons()` releases singletons of the plain BeanFactory per contract if destroy callbacks exist; the demo bean holds no resources or custom destroy method.

The example intentionally **does not print logs from processors**, avoiding reliance on when infrastructure beans are processed. The two stdout lines are verified by printing only after each context/factory has supplied `MessageBean`.

### Difference When Using AnnotationConfigApplicationContext Manually

You can obtain an unrefreshed context, add a BFPP, and then refresh:

~~~java
try (var context = new AnnotationConfigApplicationContext()) {
    context.register(AutoConfig.class);
    context.addBeanFactoryPostProcessor(
            new SetLabelDefinitionProcessor("OVERRIDE"));
    context.refresh();
}
~~~

This is a **separate illustrative snippet**, not added directly to the two-line stdout program above. In this example there is already an automatic BFPP setting `AUTO`, so **two processors modify the same property**. The final result can depend on phase and processing order; to avoid conflicting configurations, choose a single processor as owner of the `label` field or define explicit override precedence and test it. Do not use this pattern to infer that a programmatic BFPP always wins or always loses against an auto-detected BFPP in every context.

## 12. Different Registration Approaches in Practice

### 12.1. @Component and @ComponentScan

~~~java
@Component
public final class ValidationProcessor implements BeanPostProcessor {
    @Override
    public Object postProcessAfterInitialization(
            Object bean, String beanName) {
        return bean;
    }
}
~~~

When the package containing the processor is component-scanned, Spring creates a bean definition and automatically recognizes the BPP type. However, **component scanning does not happen unless configured**; merely putting `@Component` on a class and creating a plain `DefaultListableBeanFactory` does not trigger scanning or the processor.

A small note: processor beans are created early, so avoid constructors accepting complex business services; doing so may prematurely instantiate beans that ought to be auto-proxied.

### 12.2. @Bean static

This is usually the most controlled approach when the processor requires exact configuration. For BFPP, `static` must especially be preferred; for BPP, `static` is also recommended with few or no dependencies, declaring the return type as the BPP class/`BeanPostProcessor` so Spring detects it before instantiation.

### 12.3. XML or Manual Bean Definitions in Context

Bean definitions implementing BFPP/BPP can also be registered via XML or API. When added to an **ApplicationContext before refresh**, Spring auto-detects by type and invokes them along the pipeline. When registering the same definition in a **plain BeanFactory**, there is no guarantee of automatic processor invocation unless you trigger the corresponding mechanism programmatically.

### 12.4. BeanDefinitionRegistryPostProcessor via @Bean

If you need to add new bean definitions, a processor returned from `@Bean static` can implement BDRPP. However, pay attention to interactions with `ConfigurationClassPostProcessor` processing config classes: a BDRPP wanting to add definitions before scanning/config finishes must respect registry processing order and avoid abusing `getBean()`.

### 12.5. Manual BPP on an Already-Refreshed ApplicationContext

`context.getBeanFactory().addBeanPostProcessor(myBpp)` technically registers the BPP for beans created **afterward**; it **does not retroactively process already-created singletons**. If you want to process all eager singletons, it must be added before they are created. For typical applications, declaring a BPP bean for Spring auto-detection is less risky.

## 13. Why Are Early-Registered Processors and Early Dependencies Dangerous?

`BeanPostProcessor` instances must exist **before** regular beans are instantiated so they can run on them. Therefore, Spring creates these processors themselves and their direct dependencies very early. This leads to consequences:

- Beans created early alongside a processor may **not be eligible to receive all BeanPostProcessors**, including auto-proxying.
- WARN messages may appear stating a bean is not eligible for being processed by all BeanPostProcessors.
- If a BPP has constructor injection of a `TransactionalService`, the service may be constructed before the transactional auto-proxy creator is fully active; behavior may differ from expectations.
- If a BFPP uses `getBean` to resolve metadata, it can construct instances before the BPP pipeline.
- Calling the network, running database migrations, or starting threads in processor init/callbacks makes context startup slow and hard to recover from.

**Safe practice:** keep processors **lightweight, low-dependency, without calling business beans in definition phases**, and use registry/metadata APIs instead of instantiation when the concern is configuration.

A BPP that genuinely needs an infrastructure dependency can isolate that infrastructure into a bean specifically designed for early startup (not expecting AOP) or defer certain operations until a guaranteed moment; test the actual bootstrap path, not only regular post-refresh tests.

## 14. Container Hierarchy: Which Scope Does Each Processor Handle?

In principle, post-processors are **per-container**:

~~~text
Parent ApplicationContext
    ├── Parent Bean A
    └── Parent BeanPostProcessor P
            └── processes parent's beans, does not automatically process child beans

Child ApplicationContext
    ├── Child Bean B
    └── Child BeanPostProcessor C
            └── processes child's beans, does not automatically process parent beans
~~~

The fact that a child context can **look up parent beans** does not mean a child BPP is applied to already-created parent instances. Likewise, a BFPP in the parent affects definitions belonging to the factory it manages, without automatically scanning/editing all definitions in the child factory.

When multiple modules/contexts share a need for a processor, you must register the processor in the appropriate contexts; do not assume a BeanPostProcessor propagates down the context tree automatically. Copying a BPP instance programmatically to another context should only be done when the processor is stateless or designed for multi-context use; watch out for references held to an owning context.

## 15. Idempotence, Safety, and Avoiding Double Registration

Post-processors have broad lifecycle impact, so small bugs can affect many beans.

### 15.1. Specify Registration Ownership Clearly

If using auto-detection in ApplicationContext, do not manually invoke the processor an extra time. If using a plain BeanFactory, invoke processors manually in the right sequence; do not both add a BPP and have another system add the same instance again uncontrollably.

### 15.2. Are Metadata Changes Idempotent?

If a BFPP prepends a prefix to a property via string concatenation, running twice can turn `service` into `X-X-service`. When a processor might be invoked again due to configuration or tests, write the callback to set a clear final value, check an already-processed attribute, or define idempotent semantics.

### 15.3. BPP Wrapping Multiple Proxy Layers

A BPP can return a new wrapper/proxy. If the same logic triggers twice, clients may receive nested proxies, unexpected `equals`/`hashCode`, or unexpected reflection behavior. When designing a processor that could be called again, detect whether the object is already wrapped, or ensure the bean is processed once within a valid pipeline.

### 15.4. Scope of Modification

BFPP should only edit known definitions by type/name/attribute in a controlled manner. BPP should check type/name/annotation before intervening on an instance; do not cast every bean to a business class or mutate unrelated singletons.

### 15.5. Failure Policy

If a processor throws an exception during startup, the context may fail to refresh. For severely invalid config this may be the right behavior, yet logs should explain which bean name/definition is invalid. Do not swallow exceptions and continue when metadata is half-modified and state is no longer trustworthy.

## 16. When to Choose Auto-Detection vs. Programmatic Registration?

| Scenario | Typically Appropriate Approach | Why |
| --- | --- | --- |
| Normal Spring application needing BPP/BFPP | `@Bean static` or `@Component` in `ApplicationContext` | Spring automatically applies the pipeline and ordering |
| Infrastructure library with fixed post-processors | Clear bean definition/import configuration | Good auto-detection and maintainability |
| Need to add BFPP conditionally at bootstrap before refresh | `context.addBeanFactoryPostProcessor(...)` | Select processor before metadata is processed |
| Using `DefaultListableBeanFactory` directly | Invoke BFPP manually, `addBeanPostProcessor` before `getBean` | BeanFactory does not auto-discover processor beans |
| Need to add bean definitions before regular beans are created | `BeanDefinitionRegistryPostProcessor` | Appropriate registry-phase extension |
| Just setting regular bean properties via configuration | `@Bean`/`@Value`/constructor DI first | No processor needed if standard wiring solves it |
| Proxying many beans by annotation/custom semantics | BPP / AOP infrastructure | Instance extension has a clear mechanism |
| Wanting to process already-created singletons | Do not expect a late-added BPP to apply automatically | Redesign registration timing or an explicit transformation mechanism |

Do not create a BPP/BFPP just to set a property that `@Configuration`, `@Bean`, or `@ConfigurationProperties` already expresses clearly. Processors are container-level hooks with wide impact, harder to reason about than explicit configuration.

## 17. Common Errors and How to Handle Them

| Symptom | Typical Cause | Inspection / Fix |
| --- | --- | --- |
| Processor is a bean, but does not run | Using plain BeanFactory without registering/invoking processor | `addBeanPostProcessor`/call BFPP manually or use ApplicationContext |
| Processor `@Bean` is not auto-detected | Return type declared too generically, missing scan/import | Declare clear `BeanPostProcessor`/implementation return type |
| Processor breaks `@Autowired`/`@PostConstruct` on `@Configuration` | Non-static BFPP `@Bean` method causes early config instantiation | Change to `static @Bean` |
| Bean is not auto-proxied | BPP or BPP dependency was instantiated too early | Reduce early dependencies, static `@Bean`, check warnings |
| BFPP modifies an already-existing object | Used `getBean` during metadata phase | Edit `BeanDefinition`, do not instantiate business beans |
| Added BPP after `getBean` with no effect | Singleton bean was already created/cached | Register BPP before bean creation |
| Implemented `Ordered` but programmatic processor runs in wrong order | Programmatic registration ignores ordering interfaces | Change **registration order** |
| Used `@Order` to control BFPP/BPP | Processor ordering contract does not use `@Order` | Implement `PriorityOrdered`/`Ordered` for auto-detected ones |
| Multiple processors edit the same property | Conflict, unclear order | Single owner or explicit precedence/tests |
| BPP gets called on unexpected infrastructure beans | BPP processes many matching beans in container | Filter by type/name/annotation |
| Child context does not see parent's BPP | Post-processors are scoped per container | Register in the proper child context |
| Startup hangs | Processor init or BFPP lookup pulls network/deadlock | Thread dump, remove unnecessary I/O/bean lookups |
| BDRPP misses new definitions | Registry processor registered too late | Place processor in bootstrap/registry phase |
| `BeanCreationException` while processor runs | Post-processor instantiates beans itself or config error | Read root cause and metadata processing point |
| `@PostConstruct` order vs. BPP differs from guess | Annotation lifecycle is also handled by a BPP | Check processor ordering; do not assume all before run prior to annotations |

## 18. Pre-Deployment Checklist

1. Determine whether you are using `ApplicationContext` or a plain `DefaultListableBeanFactory`.
2. Choose the **registry**, **metadata**, or **instance** extension point according to the task.
3. Are processor definitions registered before refresh/bean creation?
4. If `@Bean` returns a processor, is the method `static` with a recognizable return type?
5. Does the processor avoid heavy infrastructure dependencies and business beans needing auto-proxying?
6. Does BFPP/BDRPP manipulate only definitions/registry without calling `getBean` on business beans?
7. Does BPP filter by bean name/type/annotation and return a valid bean or wrapper?
8. Are `PriorityOrdered`/`Ordered` used for **auto-detected** processors when ordering is needed?
9. If programmatic, has the **actual registration order** been tested?
10. Have you avoided adding BPPs too late so old singletons are not skipped?
11. Do you distinguish the processor's lifecycle from the lifecycle of the beans it processes?
12. Have you tested idempotence, duplicate registration, fail-fast, and shutdown?
13. Do you understand that processors do not automatically propagate from parent context to child context?
14. If only one specific bean needs adjusting, have you considered `@Bean`/standard DI before extending the container?

## 19. Self-Check Questions

**Question 1.** A `BeanPostProcessor` is declared via `@Bean static` in `AnnotationConfigApplicationContext` with the proper return type. Do you still need to call `addBeanPostProcessor`?

**Answer:** No. ApplicationContext auto-detects the BPP bean, creates/registers it at startup, and applies it to beans created after that phase.

**Question 2.** `DefaultListableBeanFactory` registers the BeanDefinition of `MyPostProcessor implements BeanPostProcessor` and then calls `getBean("service")`. Does the processor run automatically?

**Answer:** Not automatically. A plain BeanFactory does not auto-detect such beans; you need `addBeanPostProcessor` or to bootstrap through a supporting context.

**Question 3.** A `BeanFactoryPostProcessor` wants to change a field of an already-instantiated singleton. Is calling `getBean()` directly inside the BFPP the right extension point?

**Answer:** No. BFPP operates on bean metadata before regular bean instances are created. Calling `getBean` here risks instantiating beans too early and missing BPP/AOP; to act on instances, choose a BPP or appropriate DI/configuration.

**Question 4.** BPP A implements `Ordered` order=100, BPP B implements `PriorityOrdered` order=0. If you call `factory.addBeanPostProcessor(A)` then `factory.addBeanPostProcessor(B)`, which runs first?

**Answer:** In this **programmatic registration**, A runs before B according to insertion order, not interface order.

**Question 5.** An auto-detected BFPP uses `@Order(-100)` for priority; is that guaranteed?

**Answer:** No. The `@Order` annotation is not used to determine BFPP order under the contract. You must implement `PriorityOrdered` or `Ordered` when using auto-detection.

**Question 6.** You need to register additional bean definitions during config processing. Choose BFPP or BDRPP?

**Answer:** `BeanDefinitionRegistryPostProcessor` fits because it has a registry-phase hook before most bean definitions finish processing.

**Question 7.** Why declare `@Bean static BeanFactoryPostProcessor`?

**Answer:** So the container creates the post-processor early without prematurely instantiating the configuration class, avoiding lifecycle conflicts with annotations like `@Autowired` and `@PostConstruct` on the config class.

**Question 8.** Does registering a BPP after singleton `service` has already been created automatically wrap that service?

**Answer:** No. BPP applies during instance creation, not retroactively modifying already-created/cached singletons.

## 20. Official References

- [Spring Framework — Container Extension Points](https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html)
- [Spring Framework — The BeanFactory API](https://docs.spring.io/spring-framework/reference/core/beans/beanfactory.html)
- [Spring Framework — Annotation-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config.html)
- [Spring Framework — Bean Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring Framework 6.2 Javadoc — BeanFactoryPostProcessor](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/config/BeanFactoryPostProcessor.html)
- [Spring Framework 6.2 Javadoc — BeanPostProcessor](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/config/BeanPostProcessor.html)
- [Spring Framework Javadoc — BeanDefinitionRegistryPostProcessor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/support/BeanDefinitionRegistryPostProcessor.html)
