# Opting Out with `@Lazy(false)` When Enabling Lazy Initialization in Spring Boot

## 1. The Problem: Wanting Fast Startup While Ensuring Certain Beans Are Created Immediately

Spring Boot has a **lazy initialization** mode: instead of creating most application singletons right when the context is refreshed, the framework creates them only when actually needed. This feature can **shorten time to the started milestone**, especially for applications with many beans where a single run does not use all of them. However, deferring bean creation comes with trade-offs:

- Missing configuration, connection creation, or internal initialization errors may **only surface on the first request**.
- The first call pays the cost of constructor, dependency injection, `@PostConstruct`, proxies, connection setup, cache loading, or data checks.
- A service that appears "started" may not have actually attempted to initialize its most critical components.
- JVM memory usage after startup can climb when remaining beans are invoked for the first time.

Sometimes you want to **enable lazy initialization for most of the application while selecting a few beans that must initialize immediately**. Spring Boot lets you do this with the annotation:

```java
@Lazy(false)
```

Example:

```properties
# src/main/resources/application.properties
spring.main.lazy-initialization=true
```

```java
@Service
@Lazy(false)
public class CriticalConfigVerifier {
    // This bean is no longer lazy by default under the application-wide setting.
}
```

The code above is an **integration snippet** requiring Spring imports and a real project. `@Lazy(false)` on a **bean definition** tells the container that this bean **is not lazily initialized**. For a **normal singleton** inside an `ApplicationContext` with pre-instantiation, the bean will be initialized during the context startup phase without waiting for the first request.

**Correct meaning:** "Create the designated bean early." **Incorrect meaning:** "The entire application is already ready," "all remaining beans will stay lazy in every situation," or "every scope type is forced to pre-create."

## 2. Enabling Application-Wide Lazy Mode Before Selecting Opt-Outs

### 2.1. Enabling via `application.properties`

```properties
spring.main.lazy-initialization=true
```

This is a **Spring Boot** configuration property, not `spring.lazy=true` or `@Lazy` on the main class. The property can be placed in `application.properties` or a higher-precedence configuration source such as an application argument:

```bash
java -jar myapp.jar --spring.main.lazy-initialization=true
```

### 2.2. Enabling via `application.yaml`

```yaml
spring:
  main:
    lazy-initialization: true
```

The properties and YAML examples are **two alternatives**; you do not need to use both at once in the practice exercise.

### 2.3. Enabling Explicitly from Java Code

```java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setLazyInitialization(true);
app.run(args);
```

This is sample code for integrating into `main`, requiring Spring Boot imports and a real application class. Calling `setLazyInitialization(true)` configures the `SpringApplication` object before `run` begins. If external properties also exist, understand the specific binder/initialization rules; do not simply assume the Java setter and CLI property belong to the same `PropertySource`.

### 2.4. What If Global Lazy Is Not Enabled?

By default, Spring Framework **pre-instantiates non-lazy singletons** when refreshing the context. Therefore, if `spring.main.lazy-initialization=false` or lazy is not enabled and the bean is not otherwise configured as lazy, adding `@Lazy(false)` usually only makes the eager-initialization intent **explicit**, rather than adding a new capability.

`@Lazy` **with no arguments** is equivalent to `@Lazy(true)` — meaning *request lazy initialization*. `@Lazy(false)` has the opposite effect — *disable lazy for the marked bean*. The two annotations differ only by a Boolean value yet behave oppositely, making them easy to misread in code.

## 3. What Does `@Lazy(false)` Change in the Bean Lifecycle?

Consider three groups:

```text
SpringApplication starts
          |
          v
spring.main.lazy-initialization=true
          |
          v
Process bean definitions and create ApplicationContext
          |
          +-----------------------------------------+
          | Bean A: @Service                        |
          | no opt-out                              |
          | -> can be lazy                          |
          +-----------------------------------------+
          |
          +-----------------------------------------+
          | Bean B: @Service @Lazy(false)           |
          | -> not lazy                             |
          +-----------------------------------------+
          |
          +-----------------------------------------+
          | Bean C: @Bean @Lazy(false)              |
          | -> not lazy                             |
          +-----------------------------------------+
          |
          v
refresh(): pre-instantiate non-lazy singletons
          |
          +--> create B (+ required dependencies)
          +--> create C (+ required dependencies)
          |    A still need not be created if unreferenced
          v
ApplicationStartedEvent
          |
Spring Boot invokes ApplicationRunner / CommandLineRunner
          |
ApplicationReadyEvent
          |
First request/lookup of A -> create A if still uncreated
```

**Do not turn this diagram into an exact ordering guarantee between B and C.** Two independent eager beans can be created in an order depending on metadata, the dependency graph, and container internals. `@Lazy(false)` does not define a priority order among multiple beans.

An eagerly initialized singleton still goes through the standard lifecycle:

1. Spring selects the bean definition and constructor/factory method.
2. Creates the instance and resolves dependencies.
3. Invokes relevant `BeanPostProcessor`s.
4. Executes callbacks such as `@PostConstruct`, `InitializingBean`, or init methods when applicable.
5. Completes post-processing, potentially creating a proxy.
6. Exposes the bean reference for consumers to use.

`@Lazy(false)` affects **when instance creation starts**, without skipping initialization, validation, dependency injection, or post-processing steps.

Distinguish between a **registered bean definition** and an **existing singleton instance**. A lazy bean has a definition in the container yet no instance yet. Calling `context.containsBean("myBean")` can return `true` even when the object has not been created. Section 7 checks with `beanFactory.containsSingleton(...)` to avoid this confusion.

## 4. Opt-Out Syntax on `@Component` or `@Service` Classes

Stereotypes such as `@Component`, `@Service`, or `@Repository` are beans registered by Spring via component scanning. For a singleton bean in this category:

```java
package com.example.lazy;

import org.springframework.context.annotation.Lazy;
import org.springframework.stereotype.Service;

@Service
@Lazy(false)
public class CriticalService {

    public CriticalService() {
        System.out.println("CriticalService created");
    }
}
```

When global lazy is enabled, Spring still schedules creating this instance during normal refresh. It does not wait for code to call `getBean(CriticalService.class)`.

An equivalent form when writing the annotation value explicitly:

```java
@Lazy(value = false)
```

**Placement:** put the annotation directly on the **component class**, not merely on a business method thinking the whole class becomes eager. `@Lazy` belongs on bean definitions, `@Bean` methods, or dependency injection points; it is not an annotation controlling **the first call to each method**.

### Which Beans Should Receive `@Lazy(false)`?

Typical candidates include:

- Critical configuration verification beans where invalid values must fail startup.
- Components preparing mandatory infrastructure before accepting traffic.
- Resource-managing beans that must be ready from the start per operational requirements.
- Mandatory data initialization components, **if** the design fits a bean callback (for coordinating multiple services, a runner is usually clearer).

Do not place `@Lazy(false)` on every service simply because they are "important." Doing so forfeits the benefits of global lazy and increases startup cost. Ask: **does this component need to exist during context refresh, or does it only need to finish verification before readiness?** Those two requirements can lead to two different mechanisms.

## 5. Opt-Out Syntax on `@Bean` Methods

Not all beans are discovered by `@ComponentScan`. A bean can be produced from a factory method inside `@Configuration`:

```java
package com.example.lazy;

import java.time.Clock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Lazy;

@Configuration
public class ClockConfiguration {

    @Bean
    @Lazy(false)
    Clock businessClock() {
        return Clock.systemUTC();
    }

    @Bean
    ExpensiveFormatter expensiveFormatter() {
        return new ExpensiveFormatter();
    }
}
```

This is an **integration snippet**, not a self-contained project: it needs a matching `ExpensiveFormatter` class. When global lazy = true, `businessClock` is an eager opt-out; `expensiveFormatter` can stay lazy unless required by another bean.

**You must place `@Lazy(false)` on the `@Bean` method itself that creates the bean you want initialized early.** Putting the annotation on an ordinary Java method that does not register a bean will not make Spring track it.

Example of a conditional factory method:

```java
@Bean
@Lazy(false)
@ConditionalOnProperty(
        prefix = "demo",
        name = "startup-verification-enabled",
        havingValue = "true")
StartupVerifier startupVerifier() {
    return new StartupVerifier();
}
```

This is an integration snippet needing the `StartupVerifier` class and `ConditionalOnProperty` import. **`@Lazy(false)` does not override `@ConditionalOnProperty`**. If the condition does not match, the corresponding bean definition may **not be registered**, leaving no instance to force eager.

### What Effect Does `@Lazy` on a `@Configuration` Class Have?

`@Lazy` placed on a `@Configuration` class can set the lazy policy for the `@Bean` methods declared in that class. Spring Framework allows `@Lazy(false)` on an **individual `@Bean` method** to override the class-level lazy state:

```java
@Configuration
@Lazy
class BatchConfiguration {

    @Bean
    ExpensiveImporter importer() {
        return new ExpensiveImporter(); // lazy by default per configuration class
    }

    @Bean
    @Lazy(false)
    CriticalChecker criticalChecker() {
        return new CriticalChecker(); // non-lazy opt-out
    }
}
```

This is also an illustrative snippet needing the `ExpensiveImporter` and `CriticalChecker` classes; the main point is **overriding at the bean method level**. When selecting only a few opt-outs, placing `@Lazy(false)` on the **specific definition** is easier to read and QA than adding a broad annotation and reasoning backward from it.

## 6. Decision Principle: How Early Is Required?

Distinguish three needs:

| Practical Need | Suitable Mechanism | Guaranteed Timing by Design |
|---|---|---|
| "Create a critical singleton during context refresh" | `@Lazy(false)` on the bean definition | During the pre-instantiation phase of non-lazy singletons |
| "Run checks across multiple services after context refresh, before Ready" | `ApplicationRunner` / `CommandLineRunner` | After `ApplicationStartedEvent`, before `ApplicationReadyEvent` |
| "Run an action once the application finishes startup" | `ApplicationReadyEvent` listener | After runners |
| "Create the bean the first time code uses it" | Leave lazy via global policy or `@Lazy` | First time requested by the container; may be early if required by an eager dependency |
| "Defer resolution of a specific dependency" | `@Lazy` at injection point or `ObjectProvider<T>` | Controls obtaining the dependency reference, not necessarily the bean definition's policy |

A non-lazy bean can have a lightweight constructor and implement `@PostConstruct` to validate internal configuration. But if the requirement is calling repositories, network APIs, and multiple services after the whole context refreshes, a runner with an appropriate timeout usually expresses the intent more clearly.

**Do not use `@Lazy(false)` as a substitute for a readiness probe.** Just because a constructor has run does not prove the database, external endpoints, or the entire HTTP pipeline are ready. With orchestrated services, design proper health/readiness checks for the requirement.

## 7. Spring Boot 3.3.x + Java 17+ Example: Two Eager Opt-Outs and One Lazy Bean

This is a runnable example letting you directly observe:

- A `@Service @Lazy(false)` created before the runner inspects it.
- A `@Bean @Lazy(false)` also created before the runner.
- An unmarked `@Service` that remains **without a singleton instance** when global lazy is enabled.
- Calling `getBean(...)` explicitly triggers creation of the lazy bean and flips `containsSingleton` from `false` to `true`.

The application is **non-web**, requiring no HTTP server or database. It uses `System.out` strictly so execution order is easy to see while learning.

### 7.1. Project Directory

```text
lazy-exception-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/lazydemo/
    │   ├── LazyExceptionApplication.java
    │   ├── CriticalService.java
    │   └── OnDemandService.java
    └── resources/
        └── application.properties
```

**`settings.gradle`:**

```groovy
rootProject.name = 'lazy-exception-demo'
```

**`build.gradle` (Gradle Groovy DSL):**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

**`src/main/resources/application.properties`:**

```properties
spring.application.name=lazy-exception-demo
spring.main.lazy-initialization=true
```

Place the properties file in `src/main/resources` so it is on the runtime classpath. Do not add a conflicting `application.yaml` for the same exercise.

### 7.2. First Opt-Out Bean: `@Service @Lazy(false)`

**`src/main/java/com/example/lazydemo/CriticalService.java`:**

```java
package com.example.lazydemo;

import org.springframework.context.annotation.Lazy;
import org.springframework.stereotype.Service;

@Service
@Lazy(false)
public class CriticalService {

    public CriticalService() {
        System.out.println("CREATE criticalService");
    }

    public String status() {
        return "critical-ok";
    }
}
```

This class is within component-scan scope because it shares the package of the main class. The default bean name of `CriticalService` is `criticalService`. The constructor prints a message to verify when the **instance** is created; no `getBean` call is needed for it to appear.

### 7.3. Normal Lazy Bean: Plain `@Service`

**`src/main/java/com/example/lazydemo/OnDemandService.java`:**

```java
package com.example.lazydemo;

import org.springframework.stereotype.Service;

@Service
public class OnDemandService {

    public OnDemandService() {
        System.out.println("CREATE onDemandService");
    }

    public String ping() {
        return "pong";
    }
}
```

There is no `@Lazy(false)` on this definition. In the exercise, **no eager bean constructor-injects `OnDemandService`**, so with global lazy enabled, the bean can still be uncreated when the runner starts.

### 7.4. Second Opt-Out Bean and `ApplicationRunner` Observing State

**`src/main/java/com/example/lazydemo/LazyExceptionApplication.java`:**

```java
package com.example.lazydemo;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Lazy;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;

@SpringBootApplication
public class LazyExceptionApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(LazyExceptionApplication.class);

        // Demo does not use a web server.
        application.setWebApplicationType(WebApplicationType.NONE);

        try (ConfigurableApplicationContext context =
                application.run(args)) {
            // A non-web program can close the context after the runner.
        }
    }

    @Bean
    @Lazy(false)
    StartupPolicy startupPolicy() {
        System.out.println("CREATE startupPolicy");
        return new StartupPolicy("strict");
    }

    @Bean
    ApplicationRunner inspectLazyBehavior(ApplicationContext context) {
        return args -> {
            ConfigurableListableBeanFactory factory =
                    ((ConfigurableApplicationContext) context)
                            .getBeanFactory();

            System.out.println(
                    "Runner: criticalService singleton = "
                    + factory.containsSingleton("criticalService"));

            System.out.println(
                    "Runner: startupPolicy singleton = "
                    + factory.containsSingleton("startupPolicy"));

            System.out.println(
                    "Runner: onDemandService before = "
                    + factory.containsSingleton("onDemandService"));

            OnDemandService service =
                    context.getBean(OnDemandService.class);

            System.out.println(
                    "Runner: onDemandService ping = " + service.ping());

            System.out.println(
                    "Runner: onDemandService after = "
                    + factory.containsSingleton("onDemandService"));
        };
    }

    public record StartupPolicy(String mode) {
    }
}
```

Exact explanation of the choices in the demo:

1. `@Bean @Lazy(false)` is placed on `startupPolicy()`, making `StartupPolicy` a non-lazy singleton under the bean factory's default configuration.
2. `@Bean ApplicationRunner` can still be discovered and invoked by Spring Boot during the runner phase even when the whole app is in lazy mode; runner beans are part of the startup sequence itself.
3. The runner **does not constructor-inject `OnDemandService`**. It only requests `ApplicationContext`, then inspects the singleton cache before calling `getBean(...)`. This prevents the test from accidentally forcing `OnDemandService` to be created early while constructing the runner.
4. `containsSingleton("...")` checks **singleton instances registered in the singleton cache**, not merely whether the bean definition exists. It is well suited for demonstrating the before/after state of a singleton bean in this lesson.
5. `context.getBean(OnDemandService.class)` is the point where the lazy bean is requested; Spring creates the instance, runs the bean lifecycle, and returns the appropriate final reference.
6. `StartupPolicy` uses a Java `record` (supported in Java 17). It is created by the `startupPolicy()` factory method, not by `@ComponentScan`.
7. `try-with-resources` closes the context after `application.run(args)` returns so the non-web demo exits cleanly. For a web service that must keep serving HTTP requests, **do not close the context right after startup**.

### 7.5. Running the Program

If the project has the **Gradle Wrapper** (for example, generated via Spring Initializr):

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

If you created the files manually, `gradlew`/`gradlew.bat` are not automatically generated just from `build.gradle`. You can use a compatible pre-installed Gradle or generate the Wrapper at the appropriate version.

### 7.6. Expected Output

Ignoring the banner and standard Spring Boot and Gradle logs, the **lines printed by the demo code** follow these relationships:

```text
CREATE criticalService
CREATE startupPolicy
Runner: criticalService singleton = true
Runner: startupPolicy singleton = true
Runner: onDemandService before = false
CREATE onDemandService
Runner: onDemandService ping = pong
Runner: onDemandService after = true
```

**The order of `CREATE criticalService` and `CREATE startupPolicy` may swap**: they are two independent eager beans, and `@Lazy(false)` does not enforce an order between them. The `Runner: ...` lines and the timing of `CREATE onDemandService` are the key evidence:

- Before the runner begins, `criticalService` and `startupPolicy` already have singleton instances.
- At the first check inside the runner, `onDemandService` does not yet have a singleton instance.
- After `context.getBean(OnDemandService.class)`, the constructor prints `CREATE onDemandService` and the singleton cache reflects `true`.
- No fixed millisecond timings are needed: the experiment is about **bean creation timing**, not a benchmark.

If code outside the example automatically references `OnDemandService` before the runner, or if new auto-configurations/custom `BeanPostProcessor`s exist, the result before `getBean` may differ. That is why the example intentionally keeps the dependency graph minimal.

### 7.7. Control Experiment: Disabling Global Lazy

Keep the code unchanged and run:

```bash
./gradlew bootRun --args='--spring.main.lazy-initialization=false'
```

When this property overrides `true` from the file, in a standard setup `OnDemandService` also becomes a **non-lazy singleton** and is created during context startup.

Key lines to observe now:

```text
CREATE onDemandService
Runner: onDemandService before = true
Runner: onDemandService ping = pong
Runner: onDemandService after = true
```

`CREATE onDemandService` occurs **before** `Runner: onDemandService before = true`, instead of right after `before = false` as in the lazy-enabled case. Toggling global lazy does not remove bean definitions or change the `getBean` API; it only affects how the container decides **when to create instances**.

### 7.8. Control Experiment: Removing `@Lazy(false)`

Restore `spring.main.lazy-initialization=true`, then:

- Temporarily remove `@Lazy(false)` from `CriticalService`.
- Temporarily remove `@Lazy(false)` from `startupPolicy()`.
- Keep the runner logic without requesting those two beans via `getBean`.

In the demo configuration, both beans now have the opportunity to defer initialization; `containsSingleton("criticalService")` and `containsSingleton("startupPolicy")` can be `false` before being requested. This experiment shows that **the annotation on the bean definition itself** creates the opt-out.

Restore both annotations after the experiment to avoid altering the lesson's startup conditions.

## 8. A Lazy Bean Can Still Be Created Early Due to an Eager Bean's Dependency

This is the **most important caveat** when choosing `@Lazy(false)`:

> `@Lazy(false)` on a bean ensures that bean **is not deferred by its own lazy policy**. It does not ensure other beans stay uncreated.

Example:

```java
@Service
public class RemoteClient {

    public RemoteClient() {
        System.out.println("RemoteClient created");
    }
}
```

```java
@Service
@Lazy(false)
public class StartupValidator {

    private final RemoteClient remoteClient;

    public StartupValidator(RemoteClient remoteClient) {
        this.remoteClient = remoteClient;
        System.out.println("StartupValidator created");
    }
}
```

These two classes are **integration snippets** requiring `@Service` and `@Lazy` imports, placed in a component-scanned project. When `spring.main.lazy-initialization=true`:

- `StartupValidator` is an eager singleton.
- `StartupValidator`'s constructor requires `RemoteClient`.
- To construct `StartupValidator`, Spring must resolve the dependency. Thus **`RemoteClient` can be created right at startup even though it itself lacks `@Lazy(false)`**.

The logical output can be:

```text
RemoteClient created
StartupValidator created
```

The key point here is not creation speed, but the **dependency path**. Marking a bean with many dependencies as eager can "pull" the whole dependency graph into early creation. If you want to minimize the number of beans created at startup, inspect the **dependency graph of your eager opt-outs**, rather than just counting `@Lazy(false)` annotations.

### Using `ObjectProvider` When a Dependency Is Truly Needed Only Later

If a bean must be eager to check internal configuration, yet only uses a heavy service later, you can avoid resolving that service in the constructor via `ObjectProvider`:

```java
@Service
@Lazy(false)
public class StartupValidator {

    private final ObjectProvider<RemoteClient> remoteClientProvider;

    public StartupValidator(
            ObjectProvider<RemoteClient> remoteClientProvider) {
        this.remoteClientProvider = remoteClientProvider;
    }

    public void validateLater() {
        RemoteClient client = remoteClientProvider.getObject();
        // Use client when actually needed.
    }
}
```

This is an **illustrative integration snippet** requiring the `org.springframework.beans.factory.ObjectProvider` import and existing classes. `ObjectProvider` lets you defer retrieving the reference until `getObject()` is called, though it **does not promise the dependency has not already been created by another consumer**. And if you call `validateLater()` inside the eager bean's `@PostConstruct`, you yourself will still pull the dependency into early creation. Thus **when the object is retrieved** is what must be controlled.

Do not use a provider to hide a mandatory business dependency just to shave a few milliseconds off startup. If the system must verify that the remote client works before Ready, design an appropriate validation step with a timeout.

## 9. `@Lazy(false)` on a Bean Definition vs. `@Lazy` at an Injection Point

Spring also permits `@Lazy` on a **dependency injection point** (`@Autowired` field or constructor parameter). In that context, the annotation has a different meaning from marking a bean definition.

### 9.1. `@Lazy` on a Bean Definition

```java
@Service
@Lazy(false)
public class InventoryService {
}
```

Meaning: the `InventoryService` bean is not lazy in the bean factory (for normal scope); it can be created at startup via pre-instantiation.

### 9.2. `@Lazy` at an Injection Point

```java
@Service
public class OrderService {

    private final InventoryService inventoryService;

    public OrderService(@Lazy InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }
}
```

This is an illustrative snippet requiring `@Service`, `@Lazy`, and related classes. `@Lazy` on a **constructor parameter** tells Spring to inject a **lazy-resolution proxy** for the dependency; the target is resolved upon first use. It **does not mean** `InventoryService` has a lazy bean definition. If another consumer requests the target early, the target may already exist.

Therefore:

| Placement | Example | Meaning |
|---|---|---|
| On component class | `@Service @Lazy(false)` | Disables laziness **for the bean defined by the class** |
| On factory method | `@Bean @Lazy(false)` | Disables laziness **for the bean created by the method** |
| On configuration class | `@Configuration @Lazy` | Sets lazy policy for `@Bean` methods in the class per Spring rules |
| On injection parameter | `OrderService(@Lazy InventoryService inv)` | Can create a lazy proxy for the **dependency reference** |
| On injection parameter with false | `OrderService(@Lazy(false) InventoryService inv)` | Does not request a lazy-resolution proxy at that injection point; **not for switching a bean definition globally to eager** |

If your goal is "an essential bean must appear during startup," place `@Lazy(false)` on the **bean class or factory method**, not solely on another bean's constructor parameter.

**Note on optional dependencies:** a lazy-resolution proxy can be created even when the actual target does not exist; the missing-target error only surfaces when the proxy is used. For optional dependencies, `ObjectProvider<T>` usually expresses "present or absent" more clearly than assuming every proxy has a target.

## 10. Scope, Bean Conditions, and Initialization Ordering

`@Lazy(false)` cannot override every lifecycle management mechanism in Spring.

### 10.1. Singleton and Prototype

Typically:

```java
@Component
@Lazy(false)
public class SingletonHealthValidator {
}
```

With the default singleton scope, the bean is treated as non-lazy and pre-instantiated in a normal context.

However, if you write:

```java
@Component
@Scope("prototype")
@Lazy(false)
public class TransientWorker {
}
```

that does **not** mean Spring must pre-create prototypes. Prototypes are created on demand; singleton pre-instantiation does not apply similarly to prototypes. At any given point, **no prototype instance** may exist yet even though the bean definition carries `@Lazy(false)`.

These are illustrative classes requiring Spring annotations and an appropriate project.

### 10.2. Conditional Beans

`@Profile`, `@ConditionalOnProperty`, and other condition mechanisms determine **whether a bean is registered at all**. `@Lazy(false)` only adjusts initialization once the bean definition exists.

```java
@Component
@Profile("production")
@Lazy(false)
public class ProductionAuditService {
}
```

If the `production` profile is inactive, Spring may not register this bean; `@Lazy(false)` cannot initialize something the container did not define.

### 10.3. `@DependsOn` and the Dependency Graph

`@DependsOn("otherBean")` requires another bean to be initialized before the current bean, and notably can cause a lazy `otherBean` to be pulled into early creation when a non-lazy bean depends on it:

```java
@Component
@Lazy(false)
@DependsOn("otherBean")
public class CriticalWorkflow {
}
```

Illustrative snippet requiring a bean named `otherBean` and corresponding imports. `@Lazy(false)` **does not impose an ordering** across all eager beans; `@DependsOn` expresses a specific initialization dependency. However, if a real business relationship exists, constructor injection or an explicit API design is usually easier to understand than string-based bean name dependencies.

### 10.4. `@PostConstruct` and Ordering

Beans marked eager go through `@PostConstruct` when initialized. Still, the **order among unrelated beans** can vary. If coordinated work across multiple services is needed **after context refresh**, `ApplicationRunner` is still usually a better place than stuffing a lengthy workflow into an eager bean's `@PostConstruct`.

### 10.5. `@Lazy(false)` Does Not Keep a Bean Alive Forever

For a standard singleton, the bean remains in the context after creation, yet can close upon context shutdown. Other scopes have different lifecycles. `@Lazy(false)` only governs **initialization**, not a guarantee that a service stays reachable, connections stay healthy, or it is never destroyed/recreated by out-of-scope management mechanisms.

## 11. When to Choose an Eager Opt-Out

### 11.1. Detecting Critical Configuration Errors at Startup

A singleton checking immutable configuration:

```java
@Service
@Lazy(false)
public class SigningConfigurationVerifier {

    private final String keyId;

    public SigningConfigurationVerifier(
            @Value("${security.signing-key-id}") String keyId) {
        if (keyId == null || keyId.isBlank()) {
            throw new IllegalArgumentException(
                    "security.signing-key-id must not be blank");
        }
        this.keyId = keyId;
    }
}
```

This is an integration snippet requiring `@Service`, `@Lazy`, `@Value`, and real configuration. When the key is missing, the `@Value` placeholder may fail **before the constructor is even invoked**; both error forms reflect the requirement for configuration at startup.

Never log secrets or private keys; this is only a key ID. In a real project, `@ConfigurationProperties` combined with proper validation can manage large property sets instead of using many `@Value` annotations.

### 11.2. Mandatory Resource-Managing Bean Creation

For example, a `@Component @Lazy(false)` class that initializes a small configuration cache, validates an internal schema, or performs a very compact resource-setup step. It is a good candidate if:

- Early creation catches an **unacceptable** error before serving traffic.
- Startup cost is predictable and monitored.
- Initialization logic has proper timeouts and resource bounds if I/O is used.
- It does not inadvertently pull an entire graph of expensive services into startup.

Not every "important" service has to be eager. A service used only by a rare endpoint without a fail-fast requirement can still benefit from laziness.

### 11.3. Choosing the Right Eager Target in the Dependency Graph

Suppose a request requires:

```text
OrderController -> OrderService -> ShippingClient -> ExternalAPI
```

If `OrderController` is forced into early initialization and uses direct constructor injection, it can pull `OrderService` and `ShippingClient` into early creation. Conversely, merely marking `ShippingClient @Lazy(false)` does not mean an HTTP request to the external API has succeeded; the constructor might only store configuration. Clearly decide whether you need:

- **Eager object construction:** use `@Lazy(false)`.
- **Functional readiness check:** use an appropriate check inside a runner or health/readiness indicator.
- **First-call warmup:** design controlled cache/hot-path warming separately from merely creating an instance.

Optimizing startup properly is not counting lazy beans, but ensuring **required serving conditions are verified at the right milestone**.

## 12. When NOT to Use `@Lazy(false)` as a Fake Fix

### 12.1. Wanting to Guarantee the Whole App Is "Ready"

`@Lazy(false)` on a bean does not emit `ApplicationReadyEvent`, does not run runners by itself, and does not guarantee the readiness probe passes. If you must verify all dependencies before traffic, explicitly design the startup and readiness sequence rather than relying on one annotation.

### 12.2. Trying to Fix Accessing a Bean Too Early

During `ApplicationStartingEvent`, the context usually does not exist yet; adding `@Lazy(false)` to a bean does not make it available during that event. The annotation only affects singleton initialization **after bean definitions are loaded and the context enters refresh**. To work with `Environment` at an early stage, use an appropriate bootstrap API instead of trying to fetch a bean.

### 12.3. Trying to Solve Constructor Circular Dependencies

Two beans A/B constructor-injecting each other can cause a circular dependency. `@Lazy(false)` does not solve this; creating them early even surfaces the error immediately. The right fix is repairing the dependency design or separating responsibilities. Do not enable global circular references just to mask architectural flaws.

### 12.4. Trying to "Fix" a `BeanPostProcessor` or AOP Proxy

`@Lazy(false)` does not replace `BeanPostProcessor`s, proxies, or the conditions under which `@Transactional`/`@Cacheable` apply. Eager beans still go through the exact same Spring lifecycle. Self-invocations like `this.method()` within the same bean still bypass AOP proxies, regardless of eager or lazy.

### 12.5. Trying to Speed Up Startup by Setting `false` Everywhere

`@Lazy(false)` makes beans get created **earlier**, not faster on its own. Applying it broadly can restore nearly the entire cost of default eager initialization and lose the benefits of global lazy.

### 12.6. Trying to Force Prototypes to Pre-Create

Pre-instantiation applies to **non-lazy singletons**; there is no equivalent mechanism to "pre-create unlimited prototypes up front." Do not use `@Lazy(false)` as an instance-pooling annotation for prototype, request, or session scopes.

## 13. Selecting Opt-Outs in a Real Project

An evidence-based decision workflow:

1. **Measure real bottlenecks**: total startup, time to Ready, first-request latency, and which beans take time to create. Never assume lazy is always optimal.
2. **List conditions that must hold before traffic**: required configuration, schemas, certificates, critical components, essential data.
3. **Separate "creating an object" from "functional verification"**: creating a bean only confirms constructor/DI/init succeeded; it does not necessarily validate external systems.
4. **Pick the minimal eager set**: `@Lazy(false)` on bean definitions that truly need creation during refresh.
5. **Inspect the entire dependency graph**: eager beans can pull lazy dependencies into startup. Use providers or decoupled design where appropriate.
6. **Test missing-configuration scenarios**: verify whether fail-fast beans actually fail before Ready.
7. **Re-measure cold start and first request**: laziness can shift cost from startup to the first request; both affect user experience.
8. **Monitor after deploy**: compare created bean counts, first-request latency, late init errors, heap usage, and readiness.
9. **Keep configuration understandable**: comment why a bean has `@Lazy(false)` instead of copying annotations decoratively.

A short decision table:

| Question | If the Answer Is "Yes" | Appropriate Action |
|---|---|---|
| Is the bean a singleton whose **instance itself** must exist at context refresh? | Yes | Consider `@Lazy(false)` on the definition |
| Does the work coordinate multiple services after refresh, before Ready? | Yes | Consider `ApplicationRunner` |
| Is the service only used in low-traffic features? | Yes | Consider keeping lazy and measuring first-call latency |
| Does the bean's constructor depend on a large service? | Yes | Check whether it pulls the dependency into early creation |
| Is the bean excluded by `@Profile`/`@Conditional`? | Yes | Review conditions; `@Lazy(false)` cannot create an excluded bean |
| Does the bean have prototype/request scope? | Yes | Do not extrapolate from singleton pre-instantiation |
| Is cache/warmup needed in a multi-replica cluster? | Yes | Design idempotency and responsibility sharing, not just an annotation |

## 14. Common Mistakes and How to Verify

| Symptom | Possible Cause | Verification Method |
|---|---|---|
| Added `@Lazy(false)` yet bean is not created | Bean outside component scan, condition unmet, or non-singleton scope | Check bean definition, profile, scope, bean name, and constructor logs |
| Placed `@Lazy(false)` on a business method | Method does not define a bean | Place on `@Component` class or `@Bean` method |
| Used `@Lazy(false)`, yet other beans also got created early | Eager bean requires dependencies or something explicitly calls `getBean` | Inspect dependency graph / bean creation stack trace |
| Bean definition exists yet `containsSingleton` = false | Definition exists, singleton instance not yet created | Distinguish `containsBean` from `containsSingleton` |
| Expecting eager beans to run in annotation order | `@Lazy(false)` does not order beans | Use explicit dependencies or `@DependsOn` when appropriate |
| Lazy bean fails on first request | Validation deferred until first init | Add an eager opt-out or design startup validation |
| Placed `@Lazy(false)` on injection point yet target stays lazy | Injection-point annotation does not alter bean definition's lazy flag | Place annotation on the bean definition |
| Marked prototype bean `@Lazy(false)` yet no pre-created instance | Prototypes are created on demand | Check scope and `getBean` timing |
| Disabled global lazy yet bean remains uncreated | Bean has its own `@Lazy`, different scope, or special definition | Inspect actual metadata |
| `@Lazy(false)` slows down startup | Eager bean has heavy constructor/DI/init or pulls a dependency graph | Profile/meter duration and compare against first-call latency |
| Annotated a class not scanned by Spring | Spring is unaware of the bean definition | Register via `@ComponentScan`/`@Import`/`@Bean` appropriately |
| Called `getBean` intending "just to check" a lazy bean | The check accidentally **initializes** the bean | Inspect metadata/cache without requesting an instance |
| Assumed HTTP server is ready because eager beans were created | Bean creation and readiness are separate boundaries | Observe `ApplicationReadyEvent`/readiness probe |

### Debugging a Specific Bean Without Accidentally Creating It

In code with `ConfigurableApplicationContext context`:

```java
var factory = context.getBeanFactory();
System.out.println(factory.containsBeanDefinition("onDemandService"));
System.out.println(factory.containsSingleton("onDemandService"));
```

This is an **integration snippet**. The two methods answer different questions:

- `containsBeanDefinition`: does a **local** bean definition with that name exist?
- `containsSingleton`: is a singleton instance with that name **already registered** in the singleton registry?

Do not infer from `containsSingleton == false` that the application lacks that bean altogether. It may be an uncreated lazy bean, a prototype, or a definition in a parent context. Conversely, `containsBeanDefinition == true` does not guarantee instantiation will succeed.

Avoid calling `getBeansOfType(...)` or `getBean(...)` just to "check whether a bean exists" if your goal is measuring **not yet initialized**, because some lookup paths can trigger instance creation.

## 15. Practice Exercises and Check Questions

Use the Section 7 project. Change only one thing at a time and record three milestones: **before context refresh completes**, **inside the runner**, and **after the first `getBean`**.

**Exercise 1 — Class and factory opt-outs.** With `spring.main.lazy-initialization=true`, run the project. Observe `CREATE criticalService` and `CREATE startupPolicy` before the Runner lines. Explain why the order between those two CREATE lines is not guaranteed to be fixed.

**Exercise 2 — Keeping a bean lazy.** Verify `Runner: onDemandService before = false`. Call `getBean(OnDemandService.class)` and confirm the constructor runs and `containsSingleton` becomes `true`.

**Exercise 3 — Disabling global lazy.** Run `--spring.main.lazy-initialization=false`. Now `OnDemandService` is created before the Runner, while `@Lazy(false)` on the two opt-outs continues to express intent.

**Exercise 4 — Removing each annotation.** Re-enable global lazy, remove `@Lazy(false)` from `CriticalService` and run; then restore it and try removing the annotation from `startupPolicy()`. Observe which beans remain pre-instantiated. Do not use results from one run to assert ordering across all systems.

**Exercise 5 — Pulling a lazy dependency.** Add `RemoteClient` and `StartupValidator` from Section 8, marking the Validator `@Lazy(false)`. Verify `RemoteClient`'s constructor runs even though `RemoteClient` lacks an eager opt-out. Try replacing constructor injection with `ObjectProvider` and only retrieving the object when needed.

**Exercise 6 — Distinguishing scopes.** Create a `@Component @Scope("prototype") @Lazy(false)`. Observe that no prototype instances are generated automatically at refresh; instances are created only when requested via `getBean`.

**Exercise 7 — Configuration error.** Create an eager bean with `@PostConstruct` checking a hypothetical property, and intentionally omit the property in a test environment. Compare against a lazy bean invoked for the first time after startup. Confirm the difference in error-detection timing and evaluate the project's fail-fast requirements.

**Exercise 8 — Choosing the right hook.** Suppose the application must call services after context refresh and before Ready. Explain why `ApplicationRunner` should be used instead of stuffing all logic into a `@Lazy(false)` bean's constructor.

### Self-Assessment Questions

1. When `spring.main.lazy-initialization=true`, what is the specific effect of `@Service @Lazy(false)`?
2. Why do `@Lazy` and `@Lazy(false)` have opposite meanings?
3. If a `@Bean` is excluded from the context by `@ConditionalOnProperty`, will `@Lazy(false)` still create the bean?
4. Why can `@Lazy(false)` on one bean cause multiple other beans to be created early?
5. Is `@Lazy(false)` on a constructor parameter enough to mark the injected bean globally eager?
6. Is a `@Lazy(false)` prototype bean pre-instantiated like a singleton?
7. Why is `containsBean` not a reliable measure of "an instance already exists"?
8. Why can increasing eager beans slow startup while reducing the risk of late initialization errors?
9. Should you use a runner or `@Lazy(false)` if you need to check a set of services **after context refresh**?
10. How do you explain a situation where Spring Boot is already Ready yet a lazy bean has never been created?

## 16. Summary and Reference Sources

**One sentence to remember:** with global lazy enabled, `@Lazy(false)` is the way to **select a non-lazy opt-out for a specific bean definition**. It causes a normal singleton to be created during the context startup phase, without forcing all other beans to stay lazy, eliminating dependency graph effects, overriding scopes/conditions, or replacing readiness.

In short, apply three steps:

1. **Enable lazy only with clear measured justification**: reduce startup while accepting and managing first-use cost.
2. **Choose truly necessary eager beans via `@Lazy(false)`**: place on component classes or `@Bean` methods and inspect the dependency graph.
3. **Verify lifecycle at runtime**: observe constructors/`@PostConstruct` alongside singleton state; use runners/readiness for system readiness instead of equating instance creation with Ready.

Official documentation:

- Spring Boot 3.3 — *SpringApplication / Lazy Initialization* (including guidance on using `@Lazy(false)` to opt out): https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Framework 6.1 — `@Lazy` Javadoc (on components, `@Bean`, `@Configuration`, and injection points): https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Lazy.html
- Spring Framework 6.1 — *Lazy-initialized Beans* (relationship between lazy beans and eager dependencies): https://docs.spring.io/spring-framework/reference/6.1/core/beans/dependencies/factory-lazy-init.html
- Spring Boot 3.3 — *Application Events and Listeners / Runners* (started/ready milestones): https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html

Do not use `@Lazy(false)` as a "universal switch" to fix every lazy initialization bug. Its value lies in **explicitly declaring an architecturally justified opt-out on the right bean at the right stage** and verifying it through real runtime behavior.