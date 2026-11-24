# Distinguishing ApplicationContext Creation, BeanDefinition Registration, and Refresh in Spring Boot

## 1. Three Sequential Operations with Distinct Meanings

When a Spring Boot application starts up, three concepts are often lumped together as "Spring creating beans": **creating the ApplicationContext**, **registering bean definitions**, and **refreshing the context**. Understanding the boundaries explains why at certain points Spring "knows" about a bean yet does not have an instance to use, why a BeanFactoryPostProcessor can modify configuration, and why initialization errors often surface only during refresh.

The three operations can be separated briefly as:

1. **Creating the context:** creating the container object (and depending on the context type, creating/preparing the internal BeanFactory). The container **has not completed initialization**.
2. **Registering BeanDefinitions:** placing **metadata/recipes for creating beans** into the registry. Spring now knows what kind of object to create, along with its name, scope, conditions, and dependencies; **this does not mean the constructor has been called or an instance has been created**.
3. **refresh():** completing context initialization: preparing the environment, processing and adding bean definitions, registering post-processors, instantiating non-lazy singletons, setting up lifecycle/event infrastructure, and signaling that the context has refreshed. Once successful, the context is ready to serve bean retrieval/usage within its scope.

This is the explanatory model for **Spring ApplicationContext**. In a typical Spring Boot application, developers usually just call **SpringApplication.run(...)**; Boot coordinates context creation, configuration loading, and calling **refresh()** internally. There is no need to manually call refresh on a Boot context that has already started.

## 2. Lifecycle Diagram

~~~text
              Create ApplicationContext
              (new context / created by Boot)
                         |
                         v
                Context not yet refreshed
                         |
                         v
         Register configuration/definition sources
          registerBean(...), register(...),
             scan(...), XML, auto-config...
                         |
                         v
                BeanDefinition registry
           bean name, class, scope, metadata
                         |
                Not yet a bean instance
                         |
                         v
                    refresh()
                         |
          +--------------+---------------+
          | Prepare context/BeanFactory  |
          | Process config classes, scan |
          | Run factory post-processors  |
          | Register BeanPostProcessors  |
          | Instantiate non-lazy singletons |
          | Finalize lifecycle/events    |
          +--------------+---------------+
                         |
                         v
                 Active context
                         |
            getBean(...), invoke business logic
                         |
                         v
                 close() / shutdown
~~~

Read the diagram **conceptually**, rather than inferring that every bean definition is registered before refresh begins. For example, a **@Configuration** class with **@Bean** methods may already be registered as a configuration source beforehand, but **the BeanDefinitions produced by @Bean** are discovered/registered during the configuration class processing step inside refresh. Component scanning and auto-configuration can also contribute additional bean definitions during this phase.

Another distinction: **context refresh** is not source code hot-reloading or automatically reloading configuration data every time a file changes.

## 3. Phase 1 — Creating the Context Creates the Container

One way to create a context with Spring Framework:

~~~java
AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext();
~~~

This is the **no-argument** constructor, so we explicitly control when to register configuration and when to refresh. **AnnotationConfigApplicationContext** is an implementation usable with Java configuration and annotation-based bean registration.

Before calling refresh:

- The **context** object already exists.
- It has registry / BeanFactory APIs to accept bean definitions. This context type itself may also prepare several annotation infrastructure definitions right in the constructor, so **do not assert that the BeanDefinition count is 0**.
- **context.isActive()** does not yet indicate a fully started context.
- Business beans are not automatically instantiated simply because the no-arg constructor was called.

**A very important difference between constructors:**

~~~java
// Approach A: manually control phases; not refreshed on the first line.
AnnotationConfigApplicationContext ctx =
        new AnnotationConfigApplicationContext();
ctx.register(MyConfiguration.class);
ctx.refresh();

// Approach B: constructor accepts configuration class and refreshes automatically.
AnnotationConfigApplicationContext ready =
        new AnnotationConfigApplicationContext(MyConfiguration.class);
~~~

Both snippets are **API illustrations**; you must define **MyConfiguration** before using them. In approach B, **the constructor taking Class<?>... inputs registers the configuration source and refreshes automatically**, so after the constructor returns, the context is typically ready if startup succeeded. Do not infer from the phrase "new context" that **every constructor of every context type** starts in an unrefreshed state.

In addition, **GenericApplicationContext** holds an internal **DefaultListableBeanFactory** to accept definitions before refresh; several **AbstractRefreshableApplicationContext** implementations manage the BeanFactory differently. Always check the contract of the specific context type.

## 4. Phase 2 — Registering BeanDefinition Registers the Blueprint

A **BeanDefinition** stores information used to create and configure a bean, which may include:

| Property / info | Meaning |
| --- | --- |
| Bean name | Name used to look up a bean |
| Bean class or factory method | Object type or how the object is created |
| Scope | singleton, prototype, or an appropriately provided scope |
| Constructor arguments / property values | Data and dependencies to pass in |
| Lazy initialization | Whether to defer creating the bean |
| Initialization / destroy metadata | Lifecycle initialization/release mechanisms |
| Qualifiers, primary, dependency metadata | Helps select beans and resolve dependencies |

The **definition** is the recipe, whereas the **instance** is the product created from that recipe. Having a bean name known to the registry does not guarantee Spring has called its constructor.

Common paths to form a BeanDefinition:

- **context.registerBean("greetingService", GreetingService.class)**: programmatic registration, directly associating a name with a class and metadata.
- **context.register(AppConfig.class)**: registering a configuration class as a source; **@Bean** methods will be processed during the startup phase.
- **@ComponentScan** / **context.scan(...)**: finding component classes and registering corresponding definitions.
- **@Import**, configuration classes, XML, and Boot auto-configuration: adding definitions based on sources and conditions.
- **BeanDefinitionRegistryPostProcessor**: can register/modify definitions while the container is processing configuration.

### Two Non-Equivalent Checks

~~~java
context.containsBeanDefinition("greetingService");
context.getBeanFactory().containsSingleton("greetingService");
~~~

- **containsBeanDefinition** asks whether the registry already has a **BeanDefinition with that name**.
- **containsSingleton** asks whether the singleton registry currently holds a **singleton instance with that name**.

You can observe **true / false** after registering the definition but before refresh; after refresh for a non-lazy singleton bean, it is typically **true / true**.

**Exception to remember:** some singletons are registered directly via **registerSingleton(...)** and do not necessarily have a BeanDefinition; a BeanDefinition may also have prototype scope or be lazy and have no instance immediately after refresh. Therefore, do not use either check as an absolute definition of the other.

## 5. Phase 3 — refresh() Completes Context Initialization

In contexts inheriting from **AbstractApplicationContext**, the **refresh()** method is the milestone that executes the startup pipeline. Depending on the version and context type, typical steps include:

1. **Prepare context state and property sources**.
2. **Prepare the BeanFactory**, attaching the context's infrastructure components.
3. **Run BeanDefinitionRegistryPostProcessors and BeanFactoryPostProcessors**, including parsing configuration classes, component scanning, and adding/modifying definitions. With **@Configuration**, this is when **@Bean** methods are typically processed into bean definitions.
4. **Register BeanPostProcessors**. They can participate in steps before/after bean initialization, supporting dependency injection, processing certain annotations, and creating proxies when appropriate mechanisms exist.
5. **Initialize the message source, event multicaster**, and related infrastructure components.
6. Execute context hooks, such as **onRefresh()**; in a web context, this step can involve creating/starting the web server.
7. **preInstantiateSingletons:** instantiate remaining **non-lazy** singletons, resolve dependencies, and invoke corresponding initialization callbacks.
8. **Finish refresh:** start certain lifecycle beans and publish **ContextRefreshedEvent**.

This is a summary with educational value, **not an immutable API list or an exhaustive order of every internal hook**. Some infrastructure beans or post-processors can be created **before** the application singleton instantiation phase. Thus the statement "refresh creates beans" must be understood as **refresh orchestrates full initialization**, not a guarantee from Spring that zero bean instances exist beforehand.

### How does refresh handle dependencies?

Suppose **OrderService** needs **OrderRepository** via constructor:

~~~java
public OrderService(OrderRepository repository) {
    this.repository = repository;
}
~~~

This is an **illustrative snippet**, not a standalone program. When preparing to create **OrderService**, the BeanFactory must find a matching **OrderRepository** bean; it may have to create the repository before the service. If a dependency is missing and there is no optional mechanism, startup may fail during refresh (for eager singletons), rather than when merely registering a BeanDefinition.

**@PostConstruct**, **InitializingBean.afterPropertiesSet()**, init-method, and BeanPostProcessors participate in the bean creation lifecycle according to each mechanism's contract. They are not synonyms for the entire **ApplicationContext.refresh()** method.

### When is the context considered ready?

**ContextRefreshedEvent** indicates that the context's refresh has completed. In Spring Boot, normal startup also runs **ApplicationRunner** / **CommandLineRunner** and publishes **ApplicationReadyEvent** after refresh succeeds. Therefore:

- **ContextRefreshedEvent**: Spring Framework / context milestone.
- **ApplicationReadyEvent**: Spring Boot milestone after runners.
- **Deployment system readiness**: may depend on health checks, readiness probes, and external services.

Do not conflate these three milestones.

## 6. Java 17+ Example: Observing the Three Phases Clearly

The following example uses **AnnotationConfigApplicationContext** directly to separate the phases. It can be placed in a Spring Boot Maven project generated with Spring Initializr using **Java 17+**, the **Spring Boot Starter** dependency, and the default build plugin; this is a **Spring Framework container API** exercise running inside a project with Spring dependencies, so **main** intentionally does not call **SpringApplication.run**.

File **src/main/java/com/example/demo/ContextPhasesDemo.java**:

~~~java
package com.example.demo;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

@SpringBootApplication
public class ContextPhasesDemo {

    public static class GreetingService {
        public GreetingService() {
            System.out.println("5 | GreetingService constructed");
        }

        public String greet() {
            return "Hello Spring";
        }
    }

    public static void main(String[] args) {
        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext();

        System.out.println("1 | created; active=" + context.isActive());

        // Only register the BeanDefinition; no instance created yet.
        context.registerBean("greetingService", GreetingService.class);

        System.out.println("2 | definition="
                + context.containsBeanDefinition("greetingService"));
        System.out.println("3 | singleton instance="
                + context.getBeanFactory()
                        .containsSingleton("greetingService"));

        // Refresh makes the context process definitions and create non-lazy singletons.
        context.refresh();

        System.out.println("6 | refreshed; active=" + context.isActive());
        System.out.println("7 | singleton instance="
                + context.getBeanFactory()
                        .containsSingleton("greetingService"));
        System.out.println("8 | " + context.getBean(GreetingService.class).greet());

        context.close();
        System.out.println("9 | closed; active=" + context.isActive());
    }
}
~~~

**Role of @SpringBootApplication in this file:** the annotation helps the Spring Boot project recognize the main class under standard build configuration. Because **main** manually creates an **AnnotationConfigApplicationContext** instead of calling **SpringApplication.run**, the annotation on the main class **does not automatically activate Boot auto-configuration** for that manual context. To create a full Boot runtime, you need Spring Boot's bootstrap flow.

### Running the Program

In the Maven project directory generated by Spring Initializr, ensure this is the target main class, then run:

~~~bash
# Linux/macOS
./mvnw spring-boot:run

# Windows PowerShell/cmd:
# .\mvnw.cmd spring-boot:run
~~~

The lines printed by the program itself (excluding build or library logs) in order:

~~~text
1 | created; active=false
2 | definition=true
3 | singleton instance=false
5 | GreetingService constructed
6 | refreshed; active=true
7 | singleton instance=true
8 | Hello Spring
9 | closed; active=false
~~~

The code intentionally uses the number **5** for the constructor log to make it easy to see: the constructor **does not run during the definition registration step**, but runs **during refresh** and before line **6** is printed. There is no line number **4** in the example; this is a way to mark the constructor milestone between two observation steps. The lines above are output printed by the program; dependencies/build tools may print their own logs.

### Analyzing Each Observation Point

| Milestone | Key code | Result | Explanation |
| --- | --- | --- | --- |
| After context constructor | **new AnnotationConfigApplicationContext()** | active=false | Context exists but is not yet refreshed |
| After registerBean | **containsBeanDefinition(...)** | true | Registry holds the blueprint |
| Immediately after registerBean | **containsSingleton(...)** | false | No singleton instance created yet |
| During refresh | **new GreetingService()** called by container | Prints constructor log | Creates non-lazy singleton |
| After refresh | **isActive()** and singleton check | true / true | Context is active, bean is present |
| After getBean | **greet()** | Prints greeting | Invokes method on Spring-managed instance |
| After close | **isActive()** | false | Context is closed |

**Note on runnability:** this is a Java 17+ program **with Spring Boot/Spring Framework dependencies**, so it cannot be compiled purely with **javac ContextPhasesDemo.java** without providing the Spring jars on the classpath. The Maven Wrapper above handles the classpath and runs the main class. If the project has multiple main classes, select the main class via the corresponding plugin configuration.

## 7. The @Configuration and @Bean Case: Definitions Can Appear During Refresh

The example in section 6 registers **greetingService** via **registerBean**, so the BeanDefinition exists immediately after the call. With a **@Configuration** class containing **@Bean**, the registration sequence differs slightly:

~~~java
@Configuration
public class AppConfig {

    @Bean
    GreetingService greetingService() {
        return new GreetingService();
    }
}
~~~

This is a **configuration illustration**, requiring imports **org.springframework.context.annotation.Configuration** and **org.springframework.context.annotation.Bean**, along with the corresponding **GreetingService** class.

If you do:

~~~java
AnnotationConfigApplicationContext ctx =
        new AnnotationConfigApplicationContext();

ctx.register(AppConfig.class);
// At this point AppConfig is registered as a configuration source.
ctx.refresh();
// During refresh, @Bean methods are parsed to produce definitions.
GreetingService service = ctx.getBean(GreetingService.class);
ctx.close();
~~~

When **register(AppConfig.class)** returns, **AppConfig** has been recorded, but you must not assume the **greetingService** BeanDefinition from every **@Bean** method has already been parsed at that exact moment. Spring uses **ConfigurationClassPostProcessor** during refresh to parse configuration classes, process import/scan directives, and register the derived bean definitions.

Therefore, the question **"Does a bean definition exist before refresh?"** depends on **how it is registered**:

- Using **registerBean(...)** directly: that bean's definition exists before refresh.
- Using **register(AppConfig.class)** containing **@Bean**: the configuration source exists before refresh; definitions produced by @Bean can be added **during refresh**.
- Using **component scanning**: definitions may be scanned/registered before refresh or during configuration class processing, depending on initialization style.
- Using **Spring Boot auto-configuration**: definitions are added based on classpath, conditions, and properties during bootstrap/refresh.

Do not infer that all definitions are "frozen" right before refresh.

## 8. Distinguishing BeanDefinition, BeanFactory, Bean Instance, and ApplicationContext

| Component | Question it answers |
| --- | --- |
| **BeanDefinition** | How should the bean be created/configured? |
| **BeanDefinitionRegistry** | Which bean descriptions has the system registered? |
| **BeanFactory** | How to look up, create, and manage beans by metadata and scope? |
| **ApplicationContext** | How to provide a BeanFactory along with configuration, lifecycle, resources, events, and other infrastructure? |
| **Bean instance** | What actual Java object is the application using? |

A **singleton bean** is managed per **single container** by default, not as an absolute JVM-wide singleton if multiple ApplicationContexts exist. A **prototype bean** is typically created when requested, rather than pre-created on refresh. A **@Lazy** bean may remain uncreated until actually needed, even after the context has refreshed; a lazy bean can still be created early if another eager singleton depends on it.

Avoid saying **"refresh creates all beans."** A more accurate phrasing is: refresh prepares the entire container, processes definitions, and **instantiates non-lazy singletons** along with necessary infrastructure beans; scope/lazy/conditional behaviors can cause many instances to appear only later.

## 9. In Spring Boot, Where Are the Three Phases?

In Spring Boot, the common entry point:

~~~java
@SpringBootApplication
public class ProductionApplication {
    public static void main(String[] args) {
        SpringApplication.run(ProductionApplication.class, args);
    }
}
~~~

This is an **illustrative snippet**, requiring appropriate imports and placement inside a Boot project. When calling **SpringApplication.run(...)**, Boot automatically:

1. Prepares startup information, **Environment**, sources, and application type (SERVLET, REACTIVE, or NONE).
2. Creates the appropriate **ApplicationContext** type (for example, a servlet web context for Spring MVC).
3. Prepares the context and loads configuration sources, auto-configuration, and mechanisms to create/register definitions.
4. Calls **refresh()**, letting the Framework complete definition processing, bean initialization, and infrastructure setup.
5. Executes additional post-refresh Boot milestones, such as runners and the ready event.
6. Returns **ConfigurableApplicationContext** if startup completes.

Because Boot has already performed refresh, application code **must not call refresh() a second time** on the returned context. For **GenericApplicationContext** used by Spring Boot in many configurations, repeated refresh is not supported; calling it again can throw **IllegalStateException**. When you need to recreate the runtime with new code/config, use a restart or a configuration refresh mechanism explicitly supported for that system.

### Where do BeanFactoryPostProcessor and BeanPostProcessor fit?

Two extension points that are easy to confuse:

- **BeanFactoryPostProcessor:** works on the bean factory / definitions **before the application singleton instantiation phase**. Suitable for adjusting metadata or inspecting definitions per contract, not for running logic across all bean instances.
- **BeanPostProcessor:** registered to intervene in the **lifecycle of each bean instance** as it is initialized; it can help inject metadata or create wrappers/proxies depending on the processor.

**BeanDefinitionRegistryPostProcessor** extends BeanFactoryPostProcessor and can contribute additional definitions to the registry before application singletons are created.

Some post-processors are themselves beans and are created early by Spring to perform their work. Therefore, always distinguish **"instantiating application singletons at the end of refresh"** from **"no instances are created before that point."**

## 10. Common Errors and How to Handle Them

| Symptom | Cause / understanding | Resolution |
| --- | --- | --- |
| Calling getBean right after creating the context fails | Context has not completed refresh and processors have not run | Register sources then call refresh exactly once |
| containsBeanDefinition=true, containsSingleton=false | Metadata exists, no singleton instance yet | This is normal state before refresh |
| Registered @Configuration but @Bean definition not visible yet | @Bean needs the config parser to process it | Check after refresh |
| Constructor only invoked during refresh | Eager singleton created during startup | Normal; registerBean does not create the instance |
| Still do not see a prototype bean after refresh | Prototypes are created on demand | Call getBean when needed and manage lifecycle accordingly |
| Do not see a @Lazy bean after refresh | Lazy initialization is deferred | Check @Lazy and eager dependencies |
| Missing Bean / UnsatisfiedDependencyException at startup | BeanFactory cannot resolve a dependency, typically surfacing during refresh | Check bean definitions, conditions, scopes, constructors |
| BeanCurrentlyInCreationException | Dependency cycle or lifecycle issue | Redesign dependency relationships and find the cycle |
| Calling refresh() again on GenericApplicationContext | This context type does not support multiple refreshes | Create a new context / use an appropriate restart |
| ContextRefreshedEvent published but runners not finished | Spring Boot runs runners after refresh | Use ApplicationReadyEvent/readiness when appropriate |
| Assuming refresh continuously reloads application.yml | refresh() is a container startup step, not a file watcher | Use dynamic configuration or restart by design |
| Calling new Service() manually and expecting Spring to inject all dependencies | Manually created object is outside container-managed bean lifecycle | Register/instantiate through Spring when DI is needed |

### Check-Your-Understanding Questions

**Question 1.** After **new AnnotationConfigApplicationContext()** (no-arg constructor), can you claim all business beans are initialized? Why?

**Question 2.** Why can **registerBean("x", X.class)** make **containsBeanDefinition("x")** return true while **containsSingleton("x")** returns false?

**Question 3.** With **@Configuration** and **@Bean**, why might you have to wait for refresh to see the BeanDefinition generated from the method?

**Question 4.** Must a **@Lazy** singleton be created during refresh? What if another eager singleton depends on it?

**Question 5.** Spring Boot has called **SpringApplication.run(...)** successfully. Should you call **refresh()** directly on the returned context again?

**Hints:** (1) No, because the container has not been refreshed yet; (2) metadata and instance are two different states; (3) the framework parses configuration classes during refresh; (4) not required, but a dependency can force early creation; (5) no, Boot already refreshed during startup, and calling it again may not be supported.

## 11. Takeaways

- **Creating ApplicationContext:** creates the container and its foundational structures.
- **Registering BeanDefinition:** provides the recipe/metadata for beans; @Bean, scanning, and auto-configuration in particular can add definitions during refresh.
- **refresh():** coordinates configuration processing and post-processors, instantiates non-lazy singletons, finalizes lifecycle/events, and brings the context into an active state.
- **SpringApplication.run(...):** in a typical Spring Boot application, executes all of the above in the proper order; business code does not need to wire them manually.

Official documentation to verify behavior by version:

1. Spring Framework — AnnotationConfigApplicationContext, creating a context with the no-arg constructor then register/refresh: https://docs.spring.io/spring-framework/reference/core/beans/java/instantiating-container.html
2. Spring Framework API — GenericApplicationContext, registerBean, and refresh limitations: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/support/GenericApplicationContext.html
3. Spring Framework API — AbstractApplicationContext.refresh: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html
4. Spring Boot — SpringApplication, startup, and application events: https://docs.spring.io/spring-boot/reference/features/spring-application.html

Examples are written for **Java 17+**, Spring Framework 6.x / Spring Boot 3.x APIs. Cross-check the documentation for your actual version because bootstrap options may change across major versions.