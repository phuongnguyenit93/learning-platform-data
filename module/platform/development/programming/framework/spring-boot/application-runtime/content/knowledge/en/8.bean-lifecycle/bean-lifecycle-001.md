# From Bean Definition to a Ready-to-Use Object

When you see `@Component`, `@Service`, `@Repository`, or `@Bean` in a Spring Boot project, we often say “Spring manages this object”. However, between **Spring knowing a bean exists** and **an object having been created, received all its dependencies, completed initialization, and become ready for use** lies a distinct sequence of steps.

This lesson explains the journey **`BeanDefinition` → instance creation → dependency resolution → initialization → post-processing → providing the bean to consumers** in Spring Framework 6.1/Spring Boot 3.3 (Java 17+). It helps you read startup logs, diagnose `BeanCreationException`, choose when to perform initialization work, and avoid confusing “a bean is ready” with “the entire application is ready to receive traffic”.

## 1. Three concepts to distinguish

Imagine an e-commerce application with `OrderService` depending on `OrderRepository`.

- **`BeanDefinition`** is the description the container uses to know **how to manage a bean**. It can contain the name, class or factory method, scope, lazy-init flag, dependency metadata, configuration properties, and lifecycle callbacks.
- **Bean instance** is the **actual Java object** created by a constructor or factory method. Right when the constructor returns, Spring may not yet have performed all post-creation processing on it.
- **Fully initialized bean** is an object that has gone through the appropriate creation, property injection, and initialization callbacks, along with any applicable `BeanPostProcessor`s; the object that a consumer receives **may be a proxy** rather than the original instance itself.

| Question | `BeanDefinition` | Bean instance |
| --- | --- | --- |
| “What kind of bean is this, and how is it created?” | Describes the answer | Is the product created from the description |
| “Is it an existing Java object?” | No | Yes |
| “Can configuration attributes like scope or lazy be read?” | Yes, in the metadata | Can be inferred from how the bean was created, but does not replace metadata |
| “Can business methods be called?” | No | Yes, once the object is in an appropriate state |
| “Have `@Autowired`/`@PostConstruct` already happened?” | Cannot conclude from the definition alone | Depends on the creation and initialization phase |

For example, a bean can be described by:

~~~java
@Service
public class OrderService {
    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }
}
~~~

The snippet above is an **example of a class in a Spring project that already has `OrderRepository`**, not a standalone program. During component scanning, Spring can register a definition for `OrderService`. To create an instance, the container must select the constructor and resolve the corresponding `OrderRepository`. If no instance has been created yet, the presence of the definition **does not prove the constructor has run**.

A simple way to visualize this:

~~~text
Source code / configuration
   |
   | @ComponentScan, @Bean, @Import, auto-configuration ...
   v
BeanDefinition (metadata to create and manage the bean)
   |
   | BeanFactory decides when the bean is needed
   v
Instance creation (constructor or factory method)
   |
   v
Inject dependencies, supply Aware information
   |
   v
Initialization: callbacks + BeanPostProcessor
   |
   v
Bean ready to be provided to other components
   |
   v
Bean consumer receives reference (possibly a proxy)
~~~

The diagram shows the **normal flow**, not a guarantee that every bean goes through the exact same set of callbacks or the exact same internal order in special cases such as factories, early proxies, and circular dependencies.

## 2. Where do bean definitions come from?

In Spring Boot, common sources of bean definitions include:

| Source | How it is declared | Meaning |
| --- | --- | --- |
| Component scanning | `@Component` and variants `@Service`, `@Repository`, `@Controller` | Spring detects classes within the appropriate scan scope and registers a bean definition |
| Java configuration | `@Configuration` with `@Bean` methods | The container knows how to invoke the factory method to obtain the bean |
| Import/configuration | `@Import`, imported configuration classes | Registers additional bean definitions provided by configuration |
| Spring Boot auto-configuration | Auto-configurations whose conditions match | Adds bean definitions matching the classpath, properties, and existing beans |
| Programmatic registration | `BeanDefinition`/`BeanDefinitionRegistry` registration APIs | Dynamic configuration when genuinely needed |

Example definition via `@Bean`:

~~~java
@Configuration
public class ServiceConfiguration {
    @Bean
    OrderService orderService(OrderRepository repository) {
        return new OrderService(repository);
    }
}
~~~

The code above is **an alternative** to placing `@Service` directly on `OrderService`. When the container needs to create the `orderService` bean, it resolves the `OrderRepository` parameter and calls the `orderService(...)` method to obtain the instance.

**Do not confuse processing bean definitions with running constructors.** Scanning, configuration parsing, and metadata registration occur before the container decides to create regular singletons. `BeanDefinitionRegistryPostProcessor` and `BeanFactoryPostProcessor` can intervene in metadata during container construction. They are not the same as `BeanPostProcessor`, which processes **bean instances**.

A definition can exist while its instance **has not yet been created**, such as a `@Lazy` singleton bean that has not been requested yet or a `prototype` bean that has never been retrieved.

## 3. When is a bean created?

### Default singleton

By default, a Spring-managed bean has **`singleton`** scope. In a standard `ApplicationContext`, **non-lazy** singletons are created and initialized during `refresh()` (the `BeanFactory` completion phase), before the application proceeds through Spring Boot's final readiness steps.

“Singleton” here means **one shared bean instance per definition in the container**, not that only one Java object of that class may exist across the entire JVM. Two `ApplicationContext`s or two different definitions can produce separate instances.

~~~java
@Service
class PricingService {
}
~~~

Without scope/lazy customization and when the class is within scan scope, this bean is typically created early during refresh.

### Lazy singleton

~~~java
@Bean
@Lazy
HeavyClient heavyClient() {
    return new HeavyClient();
}
~~~

The definition can be registered when building the context, while the `HeavyClient` instance is only created when the bean is requested. However, if a **non-lazy** singleton needs to inject `HeavyClient` directly during startup, Spring may still create `HeavyClient` early to satisfy the dependency. `@Lazy` on a definition does not always mean “guaranteed not to initialize during startup”.

### Prototype and other scopes

~~~java
@Bean
@Scope("prototype")
DraftDocument draftDocument() {
    return new DraftDocument();
}
~~~

With `prototype`, each time the container processes a request for the bean, a new instance is produced according to scope semantics. Therefore, you cannot assume all beans have been created by the end of `refresh()`. Request/session scopes only make sense in their corresponding contexts, and those beans are initialized when the scope is active and they are needed.

**A note when injecting a prototype into a singleton:** direct injection is typically resolved when the singleton is created; subsequent method calls on the singleton **do not automatically create a new prototype**. If you need a fresh instance per task, consider `ObjectProvider<T>`, `Provider<T>`, or an appropriate lookup mechanism.

## 4. Initialization sequence of a typical bean

For a normal non-lazy singleton, the path can be read as follows:

~~~text
BeanDefinition already exists
      |
      v
[1] Container decides the bean is needed
      |
      v
[2] Select constructor / factory method
    Resolve required dependencies
      |
      v
[3] Create Java instance
      |
      v
[4] Populate properties / inject fields, setters, @Value ... if any
      |
      v
[5] Applicable Aware callbacks
      |
      v
[6] Pre-init BeanPostProcessors
    Includes @PostConstruct processing
      |
      v
[7] InitializingBean.afterPropertiesSet() if present
      |
      v
[8] Configured initMethod if present
      |
      v
[9] Post-init BeanPostProcessors
    May return a proxy/wrapper
      |
      v
Instance/reference managed and provided by container
~~~

This is a **learning map** and should be read with the following exceptions:

- Not every bean has field injection, `Aware`, `@PostConstruct`, `InitializingBean`, or `initMethod`.
- `BeanPostProcessor` is **a chain of multiple processors**. `@PostConstruct` is handled by a post-processor mechanism before initialization. Therefore, you cannot claim that **every** custom `postProcessBeforeInitialization` runs **before** `@PostConstruct`. Processor ordering also depends on Spring's ordering mechanism.
- Mechanisms such as `InstantiationAwareBeanPostProcessor`, `SmartInstantiationAwareBeanPostProcessor`, or special factories/proxies can act at an earlier stage. The diagram does not depict all of these technical branches.
- Constructor injection is resolved **before the target bean's constructor runs**. Field/setter injection occurs **after the instance exists**, before initialization callbacks.
- The container can manage a bean created from a `@Bean` method, a `FactoryBean`, or another factory, so you should not always look for a “bean class” constructor by tracing back to a direct `new` statement.

Distinguishing **definition → creation → injection → initialization → post-processing** is precisely what helps pinpoint errors accurately instead of lumping every startup error into “Spring failed to create the bean”.

## 5. From dependencies to an object: constructor injection

Consider two components:

~~~java
public final class MailClient {
    public String send() {
        return "sent";
    }
}

public final class RegistrationService {
    private final MailClient mailClient;

    public RegistrationService(MailClient mailClient) {
        this.mailClient = mailClient;
    }

    public String register() {
        return mailClient.send();
    }
}
~~~

These are **two compilable Java classes**, though to become Spring beans they still need to be declared via `@Component` or `@Bean`. When the container manages both:

1. Spring needs a `RegistrationService`.
2. It looks up the constructor of `RegistrationService` and sees it needs `MailClient`.
3. It resolves the `MailClient` bean; if needed, the dependency bean also goes through its creation and initialization cycle.
4. It invokes `new RegistrationService(mailClient)` or the corresponding creation mechanism.
5. It continues processing the lifecycle of the `RegistrationService` instance.

It follows that in **constructor injection**, the dependency object is already provided when the target bean's constructor executes. With **field injection** or **setter injection**, when the target bean's constructor begins running, fields injected later by Spring may not yet have a value.

### Why shouldn't you use injected fields in a constructor?

~~~java
@Component
class IncorrectService {
    @Autowired
    private MailClient mailClient;

    IncorrectService() {
        // mailClient may be null at constructor time.
        // DO NOT call mailClient.send() here.
    }
}
~~~

The snippet above is **structural illustrative code** and omits the `MailClient` bean definition. If the constructor accesses `mailClient.send()` under this field-injection approach, there is a risk of `NullPointerException` because field population occurs after object instantiation.

Constructor injection makes required dependencies clearer:

~~~java
@Component
class BetterService {
    private final MailClient mailClient;

    BetterService(MailClient mailClient) {
        this.mailClient = mailClient;
        // Required dependency has already been provided.
    }
}
~~~

With a single constructor in modern Spring Framework, you do not need to add `@Autowired` to the constructor for it to be chosen automatically in the normal case.

## 6. `Aware` callbacks: a bean receives information from the container

A bean sometimes needs to know its registered name or interact with the container. Spring provides callback interfaces such as:

| Interface | Purpose |
| --- | --- |
| `BeanNameAware` | Receives the name the container uses to register the bean |
| `BeanFactoryAware` | Receives the `BeanFactory` managing the bean |
| `ApplicationContextAware` | Receives the corresponding `ApplicationContext` |

Example:

~~~java
public final class NamedService implements BeanNameAware {
    private String beanName;

    @Override
    public void setBeanName(String name) {
        this.beanName = name;
    }
}
~~~

This snippet requires importing `org.springframework.beans.factory.BeanNameAware` in a Spring project; it is not a standalone JDK program. `setBeanName(...)` is called during bean initialization, before the bean is provided as a completed object.

**Do not assume every Aware callback is executed by the exact same internal step.** Some Aware interfaces are handled directly by `AbstractAutowireCapableBeanFactory`, while others are handled via a context `BeanPostProcessor`. For business code, prefer injecting specific dependencies and use Aware only when you genuinely need container interaction.

## 7. Three common initialization mechanisms: `@PostConstruct`, `InitializingBean`, `initMethod`

Spring supports initialization callbacks after required dependencies have been set:

### `@PostConstruct`

~~~java
@PostConstruct
public void prepare() {
    // Validate configuration or prepare local state of the bean.
}
~~~

For Spring Boot 3.x, import `jakarta.annotation.PostConstruct`. This callback is usually suitable for validating configuration and preparing the bean's own data.

### `InitializingBean.afterPropertiesSet()`

~~~java
public class CacheConfig implements InitializingBean {
    @Override
    public void afterPropertiesSet() {
        // Runs after Spring sets the required properties.
    }
}
~~~

This is a direct Spring API, imported from `org.springframework.beans.factory.InitializingBean`. It couples the class to Spring, so many applications prefer `@PostConstruct` or a plain init method.

### `@Bean(initMethod = "...")`

~~~java
@Bean(initMethod = "initialize")
ReportFormatter reportFormatter() {
    return new ReportFormatter();
}
~~~

Spring calls `initialize()` on the object returned by the factory method according to the initialization configuration. This is appropriate when the class comes from third-party code and cannot be modified to add annotations.

**When all three initialization mechanisms are declared on the same bean with three different methods**, the order per Spring's contract is:

1. `@PostConstruct`.
2. `InitializingBean.afterPropertiesSet()`.
3. The declared init method, e.g. `@Bean(initMethod = "initialize")`.

If the same method is configured redundantly across multiple mechanisms, Spring avoids calling the same method twice per its lifecycle rules. You should not design code that depends on a callback being invoked repeatedly.

Most beans **do not need all three**. They are shown together here to teach the ordering; in real business code, a single clear mechanism is usually easier to maintain.

## 8. Runnable hands-on example with Spring Boot 3.3

The example builds a small console application without a web server. It accurately demonstrates **constructor → BeanNameAware → @PostConstruct → afterPropertiesSet → initMethod → ApplicationRunner → retrieving the bean from context → close**.

### Directory structure

~~~text
bean-journey-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/beanjourney/BeanJourneyApplication.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'bean-journey-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    // Gradle native BOM: provides versions for Spring Boot modules.
    implementation platform(
            org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)

    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'jakarta.annotation:jakarta.annotation-api'
}
~~~

**Why is the BOM needed?** When using the Spring Boot plugin with Gradle native dependency management, applying `org.springframework.boot` **does not automatically supply versions for every dependency declared without a version**. The BOM above provides compatible versions for starters and Jakarta annotations. A project can also use the `io.spring.dependency-management` plugin per the Spring Boot documentation; simply choose one consistent version management mechanism.

File `src/main/java/com/example/beanjourney/BeanJourneyApplication.java`:

~~~java
package com.example.beanjourney;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.springframework.beans.factory.BeanNameAware;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class BeanJourneyApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(BeanJourneyApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context =
                     application.run(args)) {
            GreetingService service =
                    context.getBean(GreetingService.class);
            System.out.println("MAIN ready=" + service.isReady());
        }
        System.out.println("MAIN closed");
    }

    @Bean
    GreetingRepository greetingRepository() {
        return new GreetingRepository();
    }

    @Bean(initMethod = "customInit", destroyMethod = "customDestroy")
    GreetingService greetingService(GreetingRepository repository) {
        return new GreetingService(repository);
    }

    @Bean
    ApplicationRunner verifyService(GreetingService service) {
        return args -> System.out.println(
                "RUNNER message=" + service.greet("Spring"));
    }

    static final class GreetingRepository {
        String prefix() {
            return "Hello";
        }
    }

    static final class GreetingService
            implements BeanNameAware, InitializingBean {

        private final GreetingRepository repository;
        private boolean ready;

        GreetingService(GreetingRepository repository) {
            this.repository = repository;
            System.out.println(
                    "BEAN constructor repository=" + (repository != null));
        }

        @Override
        public void setBeanName(String beanName) {
            System.out.println("BEAN name=" + beanName);
        }

        @PostConstruct
        public void postConstruct() {
            System.out.println("BEAN @PostConstruct");
        }

        @Override
        public void afterPropertiesSet() {
            System.out.println("BEAN afterPropertiesSet");
        }

        public void customInit() {
            ready = true;
            System.out.println("BEAN customInit");
        }

        public boolean isReady() {
            return ready;
        }

        public String greet(String name) {
            return repository.prefix() + " " + name;
        }

        @PreDestroy
        public void preDestroy() {
            System.out.println("BEAN @PreDestroy");
        }

        public void customDestroy() {
            System.out.println("BEAN customDestroy");
        }
    }
}
~~~

The code above is **a complete Java file in a Gradle project with Spring Boot dependencies**, not a JDK-only example. `GreetingService` is created via a `@Bean` method, so its default bean name is `greetingService`. `GreetingRepository` is resolved by Spring and passed into the factory method before the `GreetingService` constructor runs. The `ready` flag is turned on only in the final init callback of the example for easy observation.

### Run and observe

If the project has a compatible Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

If you have not generated a wrapper yet but have a Gradle version compatible with Spring Boot 3.3 installed, run:

~~~bash
gradle bootRun
~~~

The lines **produced by `System.out.println` in the code above**, in order on the successful startup/shutdown path, are:

~~~text
BEAN constructor repository=true
BEAN name=greetingService
BEAN @PostConstruct
BEAN afterPropertiesSet
BEAN customInit
RUNNER message=Hello Spring
MAIN ready=true
BEAN @PreDestroy
BEAN customDestroy
MAIN closed
~~~

There may be additional messages from Gradle or the logging system; the list above describes only the lines printed by the example itself.

Reading each milestone:

1. **Constructor** is called with the resolved `GreetingRepository`, because this constructor accepts the repository.
2. **`BeanNameAware`** receives the name `greetingService` during the bean completion phase.
3. **`@PostConstruct`** runs before `afterPropertiesSet`.
4. **`afterPropertiesSet`** runs before `@Bean`'s `customInit`.
5. **`ApplicationRunner`** receives the initialized bean; it calls `greet(...)` after the context refreshes.
6. **`SpringApplication.run` returns**; `main` retrieves the bean from the context and sees `ready=true`.
7. **`close()`** begins destroying beans; the bean's `@PreDestroy` and `customDestroy` are invoked before the `MAIN closed` line is printed.

The example intentionally disables the banner, startup log, and web server to reduce noise; it **does not change** bean creation logic. There is no custom `BeanPostProcessor` in the example so that the callback order is easy to predict.

### Initialization failure experiment

In `customInit()`, try replacing the method body with:

~~~java
public void customInit() {
    throw new IllegalStateException("invalid configuration");
}
~~~

This is an **experimental variation**, not the default code of the example. When restarted, Spring cannot complete initialization of `greetingService`. The `application.run(args)` call fails; code after the call does not run as in the success path. The error message typically contains a cause chain including `BeanCreationException` or a related bean creation exception, with root cause `IllegalStateException: invalid configuration`.

After observing, restore the original `customInit()`. Do not leave this intentional error in production configuration.

## 9. `BeanPostProcessor` and why an injected object may be a proxy

`BeanPostProcessor` is an extension point that processes bean **instances** around the initialization phase:

~~~java
public interface BeanPostProcessor {
    Object postProcessBeforeInitialization(
            Object bean, String beanName);

    Object postProcessAfterInitialization(
            Object bean, String beanName);
}
~~~

This is an **illustrative signature of two methods in the Spring API**, not the complete interface source code for a specific version.

A processor can inspect metadata, apply annotation processing, or return a **wrapper object**. AOP mechanisms often use proxies to add behaviors such as transactions, security, or metrics when methods are invoked through a Spring-managed reference.

~~~text
Original bean is created
    |
    +-- Inject + init callbacks
    |
    +-- Post-init BeanPostProcessor
             |
             +-- Return the original bean itself
             |
             +-- Or return a proxy wrapping the original bean
                         |
                         v
            Bean consumer receives the appropriate reference
~~~

Example:

~~~java
@Service
class PaymentService {
    @Transactional
    public void pay() {
        // Actual payment work.
    }
}
~~~

This is an **illustrative snippet in a project with appropriate transaction management enabled**; compiling requires importing `@Service`, `@Transactional`, and having the necessary Spring dependencies. It does not by itself guarantee transactions work if transaction management has not been configured.

Two important conclusions:

- A bean that has already run `@PostConstruct` **may not yet be wrapped in a post-init proxy**. Do not assume that calling a `@Transactional` method inside `@PostConstruct` itself will go through the desired transaction mechanism.
- **Self-invocation** (one method of a bean calling another method directly on `this`) usually bypasses the Spring AOP proxy, even after the bean is ready. Do not infer from “the bean has been created” that every proxy-related annotation automatically works for every kind of call.

To recognize that an injected bean might not have the exact same runtime class as the target, you can inspect `getClass()` or APIs like `AopUtils.isAopProxy(...)` when Spring AOP is present. However, business logic should depend on interfaces/contracts and avoid assuming the exact runtime class of a proxy.

**Do not write a `BeanPostProcessor` just to log every bean in production** unless truly needed: post-processors run on very many beans, are themselves created and registered early, and accessing other beans at the wrong time can cause premature bean creation or alter initialization order.

## 10. At what level is a “bean ready”?

The phrase “ready to use” usually has **three distinct meanings** that should be separated:

| Milestone | What already exists? | What does not necessarily exist yet? |
| --- | --- | --- |
| Bean just finished initializing | The object has passed through the required callbacks and BPPs; Spring has a reference to provide | Other singletons or system-wide work may not be complete yet |
| `ApplicationContext` finishes refresh | Regular non-lazy singletons have been created, the container refreshed successfully and published the relevant event | `ApplicationRunner`/`CommandLineRunner` may not have run yet |
| Spring Boot publishes `ApplicationReadyEvent` | Synchronous runners have completed; Spring Boot's startup lifecycle reached the ready milestone | External services, databases, or background jobs are not guaranteed healthy unless checked separately |

For singletons that need to coordinate after all regular non-lazy singletons are created, Spring provides the **`SmartInitializingSingleton.afterSingletonsInstantiated()`** extension point. It is invoked at the end of the pre-instantiation phase of regular singletons, after each bean's init callbacks. However, lazy beans created later **do not receive this callback via the initial startup pass**.

In a full context, a `ContextRefreshedEvent` listener is another option for reacting after refresh. When you need to **start/stop** consumers or background components in order, `SmartLifecycle` and `LifecycleProcessor` are better suited than starting long-running asynchronous work directly inside `@PostConstruct`.

The reason: `@PostConstruct` belongs to the **creation phase of a single bean**, typically occurring under singleton creation locks. Performing blocking I/O, waiting for another bean that is not yet ready, or starting complex background work here can cause slow startup, deadlocks, or shutdown management issues.

### Scenario example

`EmailSender` finished creating at 08:00:00 and its `send` method can be called. However, an `ApplicationRunner` is performing a 10-second configuration load, so `ApplicationReadyEvent` has not been published yet. If the system requires data synchronization before accepting HTTP traffic, “`EmailSender` has been initialized” **does not prove** “the application is eligible to receive requests”.

Similarly, a `@Lazy` bean may be created **after** `ApplicationReadyEvent` is published, when the first request asks for the bean. Application “readiness” does not mean all lazy/prototype beans have already been initialized.

## 11. Relationship with scope, proxies, and bean destruction

Bean lifecycle does not end right after initialization. When the container closes, Spring also handles stopping active components and invoking cleanup callbacks for beans within its managed scope.

~~~text
Register definition
    |
    v
Create / inject / initialize
    |
    v
Bean is used while the context exists
    |
    +-- May participate in start/stop via Lifecycle/SmartLifecycle
    |
    v
Context closes normally
    |
    +-- Stop running Lifecycle beans (if any)
    |
    +-- Invoke destroy callbacks for container-managed singletons
    |
    v
Release resources
~~~

For singletons, Spring typically invokes `@PreDestroy`, `DisposableBean.destroy()`, or a declared destroy method according to the corresponding mechanism. For **prototype**, the container supports creation/injection/initialization, but normally **does not track each prototype instance to invoke destroy callbacks**. The consumer must take responsibility for releasing required resources.

For request/session-scoped beans, lifecycle and destruction timing also depend on the active scope. Thus, you should not describe all beans with the formula “created at startup, destroyed when the JVM exits”.

The typical callback order when a bean has multiple distinct destruction callbacks is:

1. `@PreDestroy`.
2. `DisposableBean.destroy()` if implemented.
3. The configured destroy method for the bean.

The `BeanJourneyApplication` example above uses only `@PreDestroy` and `customDestroy`, so it prints those two corresponding lines.

**Distinction from `LifecycleProcessor`:** `Lifecycle`/`SmartLifecycle` manages **start/stop** of an active component; destroy callbacks manage **bean destruction**. When `ApplicationContext.close()` runs normally, stop can happen before the destroy phase. Do not replace `SmartLifecycle.stop(Runnable)` with an indefinitely long `@PreDestroy` when you need coordinated ordering to stop accepting work.

## 12. Isolating errors by phase

| Symptom | Phase to inspect | Example cause |
| --- | --- | --- |
| No bean available to inject | Definition registration / dependency resolution | Outside component scan scope, auto-config condition not met, missing matching `@Bean` |
| Multiple beans of same type and cannot choose | Dependency resolution | Missing `@Qualifier`/`@Primary` or selection configuration |
| Cannot create instance | Constructor / factory method selection | Constructor throws exception, missing parameter, dependency does not exist |
| `@Autowired` field is `null` in constructor | Instance creation precedes field injection | Reading field too early; switch to constructor injection |
| `@Value`/`@ConfigurationProperties` wrong | Property binding / configuration resolution | Wrong property name, profile, environment variable, or data type |
| Exception in `@PostConstruct` | Initialize phase | Missing configuration, performing I/O, or accessing another bean too early |
| Exception in `afterPropertiesSet`/`initMethod` | Initialization callback | Invalid condition check or invalid resource |
| `@Transactional` has no effect on internal call | Proxy / AOP call path | Calling via `this` or calling before proxy is complete |
| `@Lazy` bean fails only on first request | Lazy on-demand creation | Bug already existed but only surfaces when the bean is initialized |
| Bean logs init yet app still fails | Another container/runner phase | Another bean failed or a runner threw an exception |
| `@PreDestroy` not called on prototype | Scope and destroy management | Container does not automatically track prototype destruction cycle |

When reading a stack trace, look for the **deepest meaningful `Caused by`**, the relevant bean name, and the failing creation phase segment. `BeanCreationException` is often a wrapper describing which bean failed to complete its lifecycle; the root error may lie in a constructor, factory method, or callback.

### Circular dependency case

~~~text
ServiceA constructor needs ServiceB
ServiceB constructor needs ServiceA
~~~

When both use direct constructor injection, the container cannot create A before B while also creating B before A. This typically results in a circular dependency error. Do not treat such an error as `@PostConstruct` “running out of order”; the dependency design needs to be revisited. Some deferral/proxy techniques can handle special cases, but masking circular dependencies is not the default solution.

### Bean ordering vs. list ordering

`@Order` plays a role when Spring sorts a collection of injected beans or processes certain extension points. It is **not a guarantee that every singleton will be created in `@Order` sequence**. To express build-time dependency between beans, use constructor injection or `@DependsOn` when there is a concrete reason; to start/stop active components, use `SmartLifecycle` phases.

## 13. Which action belongs in which phase?

| Task to perform | Typically appropriate place | Explanation |
| --- | --- | --- |
| Validate required configuration values of a bean | Constructor or `@PostConstruct` | Early check within the bean's own scope |
| Prepare small local data structures | `@PostConstruct` or init method | Does not prolong startup and needs no other bean to run first |
| Use required dependencies | Constructor injection | Allows declaration and verification right during creation |
| Adjust definitions before creating instances | `BeanFactoryPostProcessor`/`BeanDefinitionRegistryPostProcessor` | Operates on metadata, not instances |
| Wrap beans or create proxies for infrastructure concerns | `BeanPostProcessor`/Spring AOP | Container-level extension mechanism |
| Perform a task after regular singletons are initialized | `SmartInitializingSingleton` or `ContextRefreshedEvent` | Avoids doing system-wide work in the middle of creating a single bean |
| Run a one-time check after context refresh | `ApplicationRunner`/`CommandLineRunner` | Can use beans already prepared by the container |
| Start/stop consumers, schedulers, workers by phase | `SmartLifecycle` | Provides coordinated start/stop contract |
| Clean up sockets, connections, or end-of-life resources | `@PreDestroy` or destroy method | When the container closes the bean normally |

A practical rule: if logic requires **a bean that has completed init**, place it after the bean creation phase. If logic requires **the entire context or application to reach a milestone**, use the appropriate event/runner/availability hook. Never use one bean's `@PostConstruct` as an application-wide ready event.

## 14. Self-check exercises

1. **Is a `BeanDefinition` the running `OrderService` object?** No. It is metadata telling Spring how to create/manage the bean.
2. **Why can a `@Lazy` bean still be created early?** Because a non-lazy singleton may need to inject the lazy bean directly during startup.
3. **How do constructor injection and field injection differ in timing?** Constructor dependencies are supplied before the target constructor runs; field injection happens after the instance is created.
4. **Is a bean that has just exited its constructor already “fully initialized”?** Not necessarily; field/setter injection, Aware callbacks, init, and post-processing may remain.
5. **What is the order of `@PostConstruct`, `afterPropertiesSet()`, and an init method when they are three separate methods?** In the exact order just listed.
6. **Can you guarantee that every custom `BeanPostProcessor.postProcessBeforeInitialization` runs before `@PostConstruct`?** No. `@PostConstruct` is also processed by infrastructure via a post-processor; processor ordering matters.
7. **Does having called `@PostConstruct` mean an AOP proxy is definitely ready?** No; proxies can be formed during the post-processing step.
8. **Why might `@Transactional` not work when one method calls another via `this`?** Because the call may bypass the Spring AOP proxy.
9. **Are prototype beans automatically destroyed by the container when no one uses them anymore?** Usually no; the consumer must manage resources that need cleanup.
10. **Does a singleton finishing init prove the whole application has published `ApplicationReadyEvent`?** No; the context may still be finalizing and runners have not run yet.
11. **If `customInit` throws an exception, does Spring still provide the bean normally?** No; failed initialization usually causes bean creation to fail and can cause startup to fail.
12. **When needing to start and stop a background consumer by phase, choose `@PostConstruct` or `SmartLifecycle`?** `SmartLifecycle` is usually more appropriate because it has a coordinated start/stop and shutdown contract.

When reading Spring source code or diagnosing startup, trace **bean definition registered → container requests bean → create object → inject dependencies → run init callbacks → apply post-processors → provide reference**. Only after that should you evaluate whether the **context/application** has completed its subsequent runtime milestones.

### References

- Spring Framework — Bean Definition (`BeanDefinition` API): https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/beans/factory/config/BeanDefinition.html
- Spring Framework — Customizing the Nature of a Bean (init/destroy callbacks and Aware): https://docs.spring.io/spring-framework/reference/6.1/core/beans/factory-nature.html
- Spring Framework — Container Extension Points (`BeanFactoryPostProcessor`, `BeanPostProcessor`): https://docs.spring.io/spring-framework/reference/6.1/core/beans/factory-extension.html
- Spring Framework — Lazy-initialized Beans: https://docs.spring.io/spring-framework/reference/6.1/core/beans/dependencies/factory-lazy-init.html
- Spring Framework — Bean Scopes: https://docs.spring.io/spring-framework/reference/6.1/core/beans/factory-scopes.html
- Spring Framework 6.1 — `SmartInitializingSingleton`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/beans/factory/SmartInitializingSingleton.html
- Spring Boot 3.3 — SpringApplication Events/Listeners: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot Gradle Plugin 3.3 — Managing Dependencies: https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html
