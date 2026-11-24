# Distinguishing Bean Definition Registration from Bean Instantiation

## 1. Why distinguish them?

In Spring Boot, the framework **knowing that a bean can be created** and **having created a concrete Java object** are two different events. This distinction is especially important when studying **auto-configuration**: a condition can decide whether to register a bean definition, while actual object creation happens afterward according to scope, lazy initialization, and usage demand.

For example, an auto-configuration class has an **@Bean** method to provide a processor. When Spring puts that definition into the **BeanFactory**, the constructor or factory method for the processor has not necessarily executed yet. If the bean is a regular, non-lazy singleton, Spring usually creates it during **ApplicationContext** refresh; if it is lazy, Spring can wait until the bean is requested; if it is a prototype, each request can create a new instance.

Two questions must be kept separate:

1. **Has the bean definition been registered?** Does Spring have the metadata and rules to create a bean with that name?
2. **Does the bean instance already exist?** Has Spring actually invoked the constructor/factory method, performed injection, and passed the object through the required initialization steps?

An existing bean definition **does not guarantee** an instance already exists, and in certain special mechanisms, a singleton object can be registered directly without a normal BeanDefinition.

## 2. Two layers: BeanDefinition and bean instance

### 2.1. BeanDefinition is the "recipe for creation"

**BeanDefinition** is metadata in the container, typically including some or all of the following information:

- **Bean name** used by the container as an identifier; the name can be derived from the class name or **@Bean** method name, or specified explicitly.
- **Source and creation method**: target class, constructor, factory method, bean containing the factory method, or another container-supported creation mechanism.
- **Scope**, such as **singleton** or **prototype**.
- **Lazy-init**, initialization conditions, dependencies, constructor arguments, and property values, if any.
- Lifecycle metadata, such as init/destroy methods, role, and other processing flags.

The exact details depend on how it is defined. With **@Bean**, the BeanDefinition may point to **a factory method on the configuration class** rather than simply holding a constructor for the return type. Therefore, do not think of a BeanDefinition as "a sample Java object" or "a sleeping instance".

Bean definitions can arise via:

- **@ComponentScan** finding **@Component**, **@Service**, **@Repository**, **@Controller** within the scan scope.
- **@Configuration** and **@Bean** methods read by the configuration processor.
- **@Import** and **BeanDefinitionRegistryPostProcessor**s registering additional definitions.
- Programmatic registration via **BeanDefinitionRegistry.registerBeanDefinition(...)**.
- Spring Boot **auto-configuration**: the framework discovers candidate configurations and registers only the branches whose conditions are met.

**Note:** Reading annotations, processing imports, and registering definitions occur across multiple coordinated steps; not all definitions are created at once in a single operation.

### 2.2. Bean instance is the object created and managed

A **bean instance** is the actual object created or received and managed by the container. When creating a regular bean, Spring may perform several steps:

1. Select the instantiation mechanism from the BeanDefinition: constructor, **@Bean** method, or another factory.
2. Resolve dependencies and create/inject the required beans.
3. Perform dependency injection and container-aware callbacks where applicable.
4. Invoke pre/post-initialization **BeanPostProcessor**s, **@PostConstruct**, **InitializingBean.afterPropertiesSet()**, and custom init methods according to their rules.
5. Possibly return a processed **proxy**, not necessarily the original "raw" object from the constructor.
6. For singletons, typically store the instance in the singleton registry for reuse; for other scopes, storage and creation are governed by the scope.

This is a high-level flow; the exact ordering of post-processors, proxies, and callbacks depends on the bean type and extensions in use. **Registering a definition only provides the information needed to create the bean; the steps above do not have to happen at registration time.**

| Criterion | BeanDefinition | Bean instance |
| --- | --- | --- |
| Nature | Metadata/recipe for creating a bean in the container | Java object already created or provided to the container |
| Identifier | Bean name, definition attributes | Actual object reference |
| Exists since when? | After the framework or code registers the definition | When instantiation is triggered according to scope and lifecycle |
| Has constructor/factory method run? | Cannot be inferred | Actual object creation/retrieval has occurred; possibly via factory/proxy |
| For non-lazy singleton | Definition usually exists first | Usually created during the refresh phase |
| For lazy singleton | Definition already exists | May remain uncreated until first needed |
| For prototype | One definition can persist long-term | Multiple instances can be created from the same definition |
| In auto-configuration | Conditions decide which definitions are registered | An instance appears only if the definition is selected and creation succeeds |

Avoid the simplistic assumption that "each BeanDefinition always corresponds to exactly one object". Prototypes have multiple instances; scoped proxies and **FactoryBean**s have their own structure; and **registerSingleton(...)** allows registering an object directly into the singleton registry in certain situations.

## 3. Milestones during Spring Boot startup

A typical application runs **SpringApplication.run(...)** to create and refresh the ApplicationContext. It can be broken down by purpose:

~~~text
SpringApplication.run(...)
       |
       v
Prepare Environment and ApplicationContext
       |
       v
Load configuration sources, register initial definitions
       |
       v
Process @Configuration, @ComponentScan, @Import,
auto-configuration candidates and related conditions
       |
       v
BeanDefinitionRegistryPostProcessor /
BeanFactoryPostProcessor can inspect, add, modify definitions
       |
       v
Register BeanPostProcessors, finalize BeanFactory
       |
       v
Pre-instantiate regular non-lazy singletons
       |
       v
Context refresh completes; remaining startup mechanisms run
       |
       v
Subsequent getBean/injection calls can still create lazy/prototype beans
~~~

**The diagram above is a conceptual model**; it does not guarantee that throughout the entire refresh Spring strictly "registers every definition first, and only then creates any object". Some infrastructure beans, especially post-processors, must be created early so they themselves can process metadata; additional registrations can also occur during refresh. The purpose of the diagram is to separate **when the container decides a bean exists** from **when a business bean instance is created**.

### 3.1. BeanDefinitionRegistryPostProcessor and BeanFactoryPostProcessor

- **BeanDefinitionRegistryPostProcessor** can intervene in the **bean definition registry**, notably adding definitions before regular singleton creation.
- **BeanFactoryPostProcessor** can read/modify metadata of already-registered definitions without instantiating the corresponding business beans. This mechanism works on **definitions**, whereas **BeanPostProcessor** works on **bean objects** during initialization.
- Spring's **@Configuration** processor is a key component that turns **@Bean** methods and related configurations into BeanDefinitions.

Do not call **getBean(...)** arbitrarily inside a BeanFactoryPostProcessor just to check whether a bean exists: that call can force premature instantiation, violating assumptions about lifecycle and BeanPostProcessor application.

### 3.2. Auto-configuration decides registration, not immediate instantiation

In Spring Boot 3.x, **@SpringBootApplication** includes **@EnableAutoConfiguration**. Candidate auto-configurations are discovered via **META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**; conditions can be placed at the class level or on **@Bean** methods.

Illustrative logic example (this is a snippet of an auto-configuration class, not a standalone runnable program):

~~~java
@AutoConfiguration
@ConditionalOnClass(Client.class)
class ClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(Client.class)
    Client client() {
        return new Client();
    }
}
~~~

If **Client** is on the classpath and no matching bean exists yet, the condition can allow registering a definition for the bean created by **client()**. This **does not prove** the method executed the moment the condition was evaluated. For a non-lazy singleton, it is normally invoked later during refresh; if lazy initialization is enabled, it may happen even later.

A common misconception: **@ConditionalOnMissingBean** does not ask "has an object already invoked its constructor?". It checks information about existing beans in the container by declared type/name/criteria, based on definitions already processed at evaluation time. Therefore, **a bean that already has a definition but no instance yet** can still cause the default branch to back off. These conditions are affected by definition processing order; they should be used properly in auto-configuration rather than placed arbitrarily on regular configuration.

Similarly, **@ConditionalOnClass** inspects the classpath; **@ConditionalOnProperty** inspects the Environment. Conditions decide the **registration** branch; exceptions thrown from constructors, missing dependencies during creation, or failed resource connections are **instantiation**-phase issues, not reasons to conclude the condition failed to match.

## 4. Runnable Spring Boot example: definition exists, instance not yet created

This example uses **Java 21 + Spring Boot 3.3.13 + Maven 3.9+**. It demonstrates three ways instances are created from registered BeanDefinitions:

- **eagerTask**: default singleton, created during refresh.
- **lazyTask**: singleton with **@Lazy**, only created when requested in the example.
- **prototypeTask**: prototype, created anew each time the container is asked.

At the same time, a **BeanFactoryPostProcessor** only checks metadata via **containsBeanDefinition(...)** and the singleton registry via **containsSingleton(...)**. It does not call **getBean(...)** during this early inspection phase.

Project structure:

~~~text
bean-stages/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── dev/example/
        │       └── StageApplication.java
        └── resources/
            └── application.properties
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>dev.example</groupId>
    <artifactId>bean-stages</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/dev/example/StageApplication.java**

~~~java
package dev.example;

import java.util.List;

import org.springframework.beans.factory.config.BeanFactoryPostProcessor;
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Lazy;
import org.springframework.context.annotation.Scope;

@SpringBootApplication(proxyBeanMethods = false)
public class StageApplication {

    public static void main(String[] args) {
        try (var context = SpringApplication.run(StageApplication.class, args)) {
            var factory = context.getBeanFactory();

            for (String name : List.of(
                    "eagerTask", "lazyTask", "prototypeTask")) {
                System.out.printf(
                    "AFTER_REFRESH %s singleton=%s%n",
                    name, factory.containsSingleton(name));
            }

            Task lazy1 = context.getBean("lazyTask", Task.class);
            Task lazy2 = context.getBean("lazyTask", Task.class);
            System.out.println("SAME lazyTask=" + (lazy1 == lazy2));

            Task prototype1 = context.getBean("prototypeTask", Task.class);
            Task prototype2 = context.getBean("prototypeTask", Task.class);
            System.out.println(
                "SAME prototypeTask=" + (prototype1 == prototype2));
        }
    }

    @Bean
    static BeanFactoryPostProcessor inspectDefinitions() {
        return factory -> {
            for (String name : List.of(
                    "eagerTask", "lazyTask", "prototypeTask")) {
                System.out.printf(
                    "REGISTERED %s definition=%s singleton=%s%n",
                    name,
                    factory.containsBeanDefinition(name),
                    factory.containsSingleton(name));
            }
        };
    }

    @Bean
    Task eagerTask() {
        System.out.println("CREATE eagerTask");
        return new Task();
    }

    @Bean
    @Lazy
    Task lazyTask() {
        System.out.println("CREATE lazyTask");
        return new Task();
    }

    @Bean
    @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
    Task prototypeTask() {
        System.out.println("CREATE prototypeTask");
        return new Task();
    }

    static final class Task {
    }
}
~~~

Key detail to notice: the **inspectDefinitions()** method is **static @Bean** so that the BeanFactoryPostProcessor is created early without forcing premature instantiation of the **StageApplication** configuration class due to a non-static factory method. This is the recommended practice when declaring a BeanFactoryPostProcessor via **@Bean**.

**src/main/resources/application.properties**

~~~properties
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=OFF
~~~

This configuration merely keeps output concise. No web server is required; the starter here provides Spring Boot and Spring Context. In environments with custom logging or agents, extra environment log lines may still appear: focus on the lines printed by the program itself below.

### 4.1. Build and run

From the **bean-stages** directory, using JDK 21:

~~~bash
mvn -q -DskipTests package
java -jar target/bean-stages-0.0.1-SNAPSHOT.jar
~~~

The lines printed by the example itself, in order:

~~~text
REGISTERED eagerTask definition=true singleton=false
REGISTERED lazyTask definition=true singleton=false
REGISTERED prototypeTask definition=true singleton=false
CREATE eagerTask
AFTER_REFRESH eagerTask singleton=true
AFTER_REFRESH lazyTask singleton=false
AFTER_REFRESH prototypeTask singleton=false
CREATE lazyTask
SAME lazyTask=true
CREATE prototypeTask
CREATE prototypeTask
SAME prototypeTask=false
~~~

**Explanation by milestone:**

1. **REGISTERED ... definition=true**: When the BeanFactoryPostProcessor is invoked, all three business beans already have definitions in the BeanFactory. At the moment of inspection, they **do not yet appear in the singleton registry**.
2. **CREATE eagerTask**: During refresh, Spring creates the non-lazy singleton via the **@Bean eagerTask()** method. This is instance creation; this line appears **after** the definition check lines.
3. **AFTER_REFRESH eagerTask singleton=true**: After **SpringApplication.run(...)** returns, the eager singleton has been created and retained in the container.
4. **AFTER_REFRESH lazyTask singleton=false**: The definition of lazyTask is registered, but there is no singleton instance yet because nothing has requested it in the example.
5. **CREATE lazyTask** appears only once even though **getBean(...)** is called twice; the singleton returns the same reference, so **SAME lazyTask=true**.
6. **CREATE prototypeTask** appears twice. Two calls to **getBean(...)** create two distinct objects; they are not retained as a singleton, so **SAME prototypeTask=false**.

This output proves that **a registered BeanDefinition does not determine the number of instances or the creation time**; those two factors also depend on scope and when the dependency is requested.

### 4.2. Changes that alter the output

- If you remove **@Lazy** from lazyTask, that bean becomes a regular singleton and is normally created during refresh, before the **getBean(...)** calls in main execute.
- If you add **spring.main.lazy-initialization=true** when running the application, Spring Boot allows deferring many otherwise-eager singletons; in that case, the post-refresh singleton output needs to be re-evaluated. Do not use that property when comparing against the sample stdout.
- If an eager singleton requires **lazyTask** injected as a direct dependency, Spring may have to create lazyTask while constructing the eager singleton even though lazyTask carries **@Lazy** on its definition. **Lazy does not guarantee no one will use the bean before startup finishes.**
- If a singleton directly injects prototypeTask via its constructor, Spring creates one prototype for that injection; the singleton retains the injected reference and calling methods on the singleton multiple times **does not automatically produce new prototypes**. To obtain a fresh prototype per use, inject **ObjectProvider<Task>** with an appropriate qualifier and call **getObject()** when needed.
- If the constructor or factory method of eagerTask throws an exception, the definition was still selected/registered earlier, yet refresh can fail. This differs from a condition preventing the definition from ever being registered.

## 5. Distinguishing singleton, lazy singleton, and prototype

Spring uses **singleton scope** for beans by default. This is a singleton **per bean name within a single Spring IoC container**, not an assertion that only one object of that class exists across the entire JVM. The same class can have multiple bean names and multiple corresponding instances.

| Scope/creation mode | Definition present before getBean? | When can an instance appear? | What does each getBean with the same name return? |
| --- | --- | --- | --- |
| Regular singleton | Yes | Usually during refresh if non-lazy | The same container-managed instance |
| **@Lazy** singleton | Yes | First time truly needed, unless a dependency forces early creation | The same instance once created |
| Prototype | Yes | When requested | Usually a new instance on each request |
| Request/session scope (properly configured web app) | Yes | Within the request/session scope and when requested | According to the scope's lifecycle; a proxy may sit in between |

**@Lazy** governs deferring initialization, while **@Scope** governs the lifecycle/retention scope of instances. The two annotations answer different questions. A BeanDefinition can persist for a long time even though prototype instances are generated repeatedly and are not managed by Spring during destruction by default the way singletons are.

Do not treat **@Lazy on @Component or @Bean** as completely identical to **@Lazy at an injection point**. The former affects how the defined bean is initialized; the latter can cause Spring to inject a proxy that defers dependency resolution. When debugging, check where the annotation is placed and whether any eager dependency pulls instantiation earlier.

## 6. APIs for asking "registered or created?"

Several APIs have similar names yet answer different questions:

| API | Approximate meaning | What NOT to conclude |
| --- | --- | --- |
| **BeanFactory.containsBean(name)** | The BeanFactory recognizes a bean with this name, including via certain parent/alias rules | Does not prove an instance was created |
| **ConfigurableListableBeanFactory.containsBeanDefinition(name)** | The factory currently holds a local BeanDefinition for this name | Does not prove an object was created |
| **BeanFactory.getBean(name)** | Requests the bean; may trigger bean creation and resolve proxy/scope | Not a read-only check |
| **SingletonBeanRegistry.containsSingleton(name)** | The registry holds a registered singleton object for this name | Not a general check for prototypes or every FactoryBean |
| **BeanFactory.isSingleton(name)** | The bean has singleton semantics according to the factory | Does not mean a singleton instance already exists |
| **BeanFactory.isPrototype(name)** | The bean has prototype semantics according to the factory | Does not mean any instance has been created |
| **ConfigurableListableBeanFactory.getBeanDefinition(name)** | Reads metadata of the local bean definition | Does not return a bean instance |

Example of a read-only check against existing metadata:

~~~java
// bf is a ConfigurableListableBeanFactory obtained from ApplicationContext.
// This snippet is illustrative, not a standalone Java program.
String name = "lazyTask";

boolean defined = bf.containsBeanDefinition(name);
boolean singletonObjectPresent = bf.containsSingleton(name);

System.out.println("defined=" + defined);
System.out.println("singletonObjectPresent=" + singletonObjectPresent);
~~~

For **lazyTask** in the runnable example, before the first **getBean("lazyTask")**, the lines above print **defined=true** and **singletonObjectPresent=false**. Note: **containsSingleton** means the singleton registry currently holds that object; it is not a global check of whether constructors of *every* kind of bean across all scopes have ever run.

**Memorable exceptions:** **DefaultListableBeanFactory.registerSingleton(...)** allows placing an instance directly into the singleton registry; that object does not have to go through a regular BeanDefinition. **FactoryBean** has two layers (the factory object and the product object), so looking up the bean name vs. the name prefixed with **&** has different semantics. For these special cases, do not mechanically apply the "one definition -> one instance" diagram.

## 7. Practical connection to Spring Boot auto-configuration

When reading source code or a condition report, separate three states:

1. **No bean definition for the branch**: class/property/bean conditions were not met, or the auto-configuration was not imported/was excluded. Nothing can be created from that branch.
2. **Definition exists, but no instance yet**: commonly seen with lazy singletons, prototypes before `getBean`, or beans belonging to an inactive scope. The condition may have matched completely.
3. **Definition exists and instantiation was attempted but failed**: for example, a missing dependency to inject, constructor throwing an exception, or invalid connection configuration. Here the error occurs at instantiation time, not when selecting the condition branch.

**@ConditionalOnMissingBean** is commonly used so Spring Boot can "back off" when an application provides a custom bean. Specifically, if an application registers a definition for a **PaymentClient** bean, even if that bean is lazy and has no instance yet, an auto-configuration conditioned on a missing bean of the same type **can still be excluded**. It does not need to wait for the PaymentClient object to finish being created to know that a matching bean has been declared by the application.

Mental flow:

~~~text
Required library / class present?
          |
         Yes
          v
Auto-configuration branch satisfies other conditions?
          |
         Yes
          v
Matching bean definition already exists, failing @ConditionalOnMissingBean?
          |
     Yes -+--> Do not register default BeanDefinition
          |
          No
          v
Register default BeanDefinition
          |
          v
Scope + lazy + dependencies + lifecycle determine instantiation time
~~~

This diagram depicts a default branch **with @ConditionalOnMissingBean**; it does not apply to every auto-configuration. Conditions may live at the class or method level and may involve bean names, annotations, search strategies, or other criteria. Do not conclude that "a bean of the same type exists" always excludes every other configuration.

### 7.1. What does the condition evaluation report answer?

Start a Spring Boot application with the **--debug** argument or enable appropriate diagnostic logging to view the **condition evaluation report**. The report tells you which auto-configurations **matched/did not match** and why. It explains **condition decisions**, but it is **not a constructor-invocation log for each instance**.

Example with a real application that allows logging:

~~~bash
java -jar target/app.jar --debug
~~~

This is a sample command for a JAR named app.jar in another application; for the runnable project in section 4, use the actual JAR name and remove **logging.level.root=OFF** if you want to see logs. A matched condition does not prove instantiation succeeded; nor does the condition report replace a **BeanCreationException** stack trace.

### 7.2. When should you use actuator/beans?

In an application with Actuator and the endpoint configured, **/actuator/beans** shows information about beans in the ApplicationContexts, such as name/type/scope/dependencies according to the exposed data. It is useful for inspecting **bean identity and configuration**, though that list alone should not be treated as an exact count of prototype objects ever created. If you need the reasons why auto-configuration matched or did not match, **/actuator/conditions** is better suited to the task.

Actuator endpoints must be properly configured for exposure and security; having the Actuator starter does not mean every endpoint is publicly exposed.

## 8. Common mistakes and how to fix them

| Mistake | Consequence | Correct way to check |
| --- | --- | --- |
| "Having @Bean means the factory method has already run." | Conflating definition with runtime | Look for instantiation milestones or inspect the singleton registry |
| "If the condition matched, the bean was created successfully." | Missing BeanCreationException errors | Distinguish the condition report from errors during refresh/getBean |
| "@ConditionalOnMissingBean only checks already-created objects." | Wrongly predicting back-off behavior | Check processed bean definitions and the specific condition |
| "@Lazy guarantees a bean is never created during startup." | Overlooking eager dependencies requiring the bean | Inspect the dependency graph and injection points |
| "A prototype injected into a singleton refreshes automatically on every call." | Keeping the same instance inside the singleton | Use ObjectProvider when you need a fresh prototype per access |
| "isSingleton=true means an instance already exists." | Failing to notice lazy singletons | Compare isSingleton with containsSingleton |
| "Calling getBean just to verify a bean exists." | Accidentally instantiating the bean and causing side effects | Use BeanDefinition APIs when you only need metadata |
| "@Primary creates or blocks a default bean." | Confusing injection selection with registration conditions | @Primary resolves injection priority, not registration conditions |
| "Spring has strictly one object per singleton class." | Confusing singleton per bean-name with singleton per class/JVM | Check bean name, container, and scope |
| "Counting definitions tells you the number of instances." | Wrong for lazy, prototype, FactoryBean, and proxies | Observe creation mechanism, scope, and singleton registry |

A real-world pitfall: an application declares its own **@Lazy** bean, yet the default auto-configuration does not appear. This is usually expected behavior when the default uses **@ConditionalOnMissingBean**: the user-declared definition is enough for the framework to back off. Conversely, if the default definition is registered yet the bean has not appeared in startup logs, check **lazy/scope** before concluding that auto-configuration is broken.

## 9. Diagnostic workflow for a specific bean

Suppose an application needs an **OrderClient** bean, and it is unclear why it is not working. Pinpoint the problem with these questions:

1. **Is there a candidate config?** Check the library containing the auto-configuration and the Spring Boot 3.x imports file; check exclusions if any.
2. **Do the conditions match?** Check classpath, properties, application type, bean conditions, and the **condition evaluation report**.
3. **Is the BeanDefinition in the factory?** Check the exact bean name using metadata APIs; watch out for aliases/parent contexts and custom-registered definitions.
4. **What scope is the bean, and is it lazy?** Inspect the BeanDefinition, injection points, and eager dependencies.
5. **Has the object been created yet?** For singletons, use appropriate checks against the singleton registry; for prototypes or request-scoped beans, inspect each retrieval within its scope.
6. **If creation failed, where did it fail?** Examine the stack trace for dependency resolution, constructor, factory method, binding, initialization callbacks, or resource connections.
7. **If you get an object whose behavior is unexpected, is there a proxy/decorator?** Check the actual type, the bean selected via **@Qualifier/@Primary**, the bean name, and AOP in the relevant environment.

When instrumenting an application, avoid calling **getBean(...)** in overly early configuration callbacks; logs from constructors, factory methods, BeanPostProcessors, or appropriately phased listeners provide much more accurate evidence for **instantiation timing**.

## 10. Reasoning exercises

**Exercise 1.** A **@Lazy** singleton has a BeanDefinition and has caused a default's **@ConditionalOnMissingBean** condition to fail. Is an instance of that bean guaranteed to have been created yet?

**Answer:** Not yet. The missing-bean condition can see the matching definition; a lazy singleton can remain uncreated until a dependency requests it.

**Exercise 2.** In the application from section 4, two calls to **getBean("prototypeTask")** both print **CREATE prototypeTask**. Did Spring register two separate BeanDefinitions?

**Answer:** No. A single definition with prototype scope can produce multiple instances.

**Exercise 3.** After **SpringApplication.run(...)** returns, **containsBeanDefinition("lazyTask") = true**, **containsSingleton("lazyTask") = false**. Is there a contradiction?

**Answer:** No. Spring knows how to create the bean, but does not yet hold a singleton instance. This is completely consistent if nothing forced lazyTask to be created.

**Exercise 4.** A non-lazy singleton bean has its definition selected, yet the application throws **BeanCreationException** in the constructor. Can you say auto-configuration failed to register the bean?

**Answer:** You cannot conclude that. On the contrary, a constructor error typically indicates Spring attempted to create an instance from a definition; inspect the stack trace and why bean creation failed.

**Exercise 5.** A singleton holds a field for a prototype bean injected once. Does calling a method on that singleton ten times create ten new prototypes?

**Answer:** Not automatically. You must request the prototype again via a provider or an appropriate lookup mechanism if you want a fresh instance per invocation.

## 11. Takeaways

When Spring Boot decides whether an auto-configuration applies, the central question is **which BeanDefinitions qualify to be registered**. When the Spring container runs, the next question is **which instances are created, when, in what scope, and whether creation succeeds**.

Use **BeanDefinition/condition reports** to understand **configuration selection**; use **scope, lazy, the dependency graph, lifecycle callbacks, and BeanCreationException errors** to understand **object creation**. Keeping these two layers clear explains why a bean can be declared yet have no object yet, why a default bean backs off even when the user bean is lazy, and why a prototype can spawn multiple objects from the same definition.

### References

- Spring Framework, *Bean Overview*: https://docs.spring.io/spring-framework/reference/core/beans/definition.html
- Spring Framework, *Bean Scopes*: https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html
- Spring Framework, *Lazy-initialized Beans*: https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-lazy-init.html
- Spring Framework, *Container Extension Points*: https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html
- Spring Boot, *Auto-configuration*: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
- Spring Boot, *Creating Your Own Auto-configuration*: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
