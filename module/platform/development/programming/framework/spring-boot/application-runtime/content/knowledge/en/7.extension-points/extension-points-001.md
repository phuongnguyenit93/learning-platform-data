# Choosing Extension Points by Available Resources at Each Phase

## 1. The problem: the right task at the wrong time still fails

Spring Boot provides many **extension points** to hook into the startup process: listeners, environment post-processors, context initializers, bean lifecycle hooks, runners, and application readiness events. They **cannot be used interchangeably** because each appears at a different phase.

Suppose an application needs to perform four tasks:

- Add a default configuration value **before Spring decides which beans must be created**.
- Add a bean definition to `ApplicationContext` **before beans are instantiated**.
- Prepare internal data **after a service has had its dependencies injected**.
- Validate initial data using a service **after the context starts and before the application is marked ready**.

If all four tasks are placed in `ApplicationReadyEvent`, the first two will be too late: Spring has already evaluated configuration conditions and created the beans. Conversely, if you try to retrieve a service from `ApplicationStartingEvent`, the context does not even exist yet. This is why you choose a hook based on **the resources actually available** rather than just the hook's name.

**Core principle:** first identify whether the task needs `Environment`, bean metadata/definitions, an instantiated bean instance, or an application that has finished running its runners; then choose **the earliest phase where those prerequisites are met** to perform it safely.

## 2. Startup map: resources emerge progressively

General sequence in Spring Boot 3.3:

```text
SpringApplication.run(...)
        |
        v
ApplicationStartingEvent
  - SpringApplication and arguments are available
  - Prepared Environment does not exist yet, ApplicationContext does not exist yet
        |
        v
Prepare and process Environment
  - EnvironmentPostProcessor
  - ApplicationEnvironmentPreparedEvent
  - PropertySources are available; ApplicationContext does not exist yet
        |
        v
Create ApplicationContext + run ApplicationContextInitializer
  - Context and Environment are available
  - Not refreshed yet; cannot rely on application beans yet
        |
        v
ApplicationContextInitializedEvent
  - Initializers have run
  - Main application bean definitions have not been loaded yet
        |
        v
Load configuration and bean definitions
        |
        v
ApplicationPreparedEvent
  - Definitions have been loaded
  - Context is not refreshed yet
        |
        v
refresh() and bean lifecycle
  - BeanDefinitionRegistryPostProcessor
  - BeanFactoryPostProcessor
  - BeanPostProcessor, @PostConstruct, singleton instantiation
  - If a Web server is present: Web server initialization events when applicable
  - ContextRefreshedEvent
        |
        v
ApplicationStartedEvent
  - Context has been refreshed
  - ApplicationRunner / CommandLineRunner have not run yet
        |
        v
LivenessState.CORRECT
        |
        v
ApplicationRunner and CommandLineRunner
        |
        v
ApplicationReadyEvent
        |
        v
ReadinessState.ACCEPTING_TRAFFIC (default flow)

If startup fails: ApplicationFailedEvent
(context may be absent or only partially created)
```

The diagram shows the **order of key milestones**, not a guarantee that every bean and every task runs in a fixed internal order. Callbacks related to refresh may run multiple times in multi-context designs or when a context is refreshed again.

There are two subtle distinctions that are easy to miss:

1. **`ApplicationContextInitializedEvent` differs from `ApplicationPreparedEvent`.** At the first milestone, initializers have run, but the main application bean definitions have not been loaded yet. At the second milestone, definitions have been loaded, but the context has not been refreshed yet.
2. **`ApplicationStartedEvent` differs from `ApplicationReadyEvent`.** Runners still execute after Started. A slow or failing runner can delay or prevent the application from reaching the Ready milestone.

## 3. Hook selection table by available resources

| What do you already have at this phase? | Suggested hook | Suitable tasks | What must not be assumed |
|---|---|---|---|
| Only the startup object and very early arguments | Pre-registered `ApplicationStartingEvent` listener | Mark the startup milestone, observe the bootstrap process | Prepared `Environment` or application beans exist |
| `ConfigurableEnvironment`, `PropertySources` | `EnvironmentPostProcessor` | Add/modify property sources, fallback values before context creation | `ApplicationContext` or services exist |
| `Environment` is prepared, context does not exist yet | Early-registered `ApplicationEnvironmentPreparedEvent` listener | Observe configuration, coordinate logic before context creation | Beans can be retrieved via `getBean` |
| Context just created, environment is available, not refreshed yet | `ApplicationContextInitializer` | Configure the context, register appropriate definition components before refresh | Application singletons are instantiated |
| Initializers have run, application definitions not loaded yet | `ApplicationContextInitializedEvent` listener | Observe/propagate early context-phase information | Complete bean definitions exist |
| Definitions loaded, but context not refreshed yet | `ApplicationPreparedEvent` listener | Diagnose configuration before refresh | Beans are ready for business logic |
| Bean registry/factory has metadata before bean creation | `BeanDefinitionRegistryPostProcessor` / `BeanFactoryPostProcessor` | Adjust or add **bean definitions** | Business beans can be freely invoked without affecting the lifecycle |
| A bean has been created, its own dependencies have been injected | `@PostConstruct` / `InitializingBean`, sometimes `BeanPostProcessor` | Initialize **that bean's state**, process around individual bean lifecycles | The entire system is ready or all other beans are finished |
| Context refreshed, runners not run yet | `ApplicationStartedEvent` | Observe state after refresh, record appropriate metrics/telemetry | Startup runners have completed |
| Normal singletons and context initialized to run startup tasks | `ApplicationRunner` / `CommandLineRunner` | Use services to verify data, load initialization info, run tasks that must finish before ready | Running long is harmless, or the Web server is definitely not accepting connections yet |
| All runners have been called and completed successfully | `ApplicationReadyEvent` | Announce/observe the milestone where the application has completed the startup sequence | All external services are guaranteed to stay healthy afterward |
| Startup throws an exception | Early-registered `ApplicationFailedEvent` listener | Log/collect bootstrap errors, clean up independent resources | A particular context/bean always exists |

Choose based on **the work to be completed**: if you need to change bean creation decisions, do it early; if you need to use services, do it after beans are instantiated; if you need to signal readiness, do it after runners. The same task can be split into multiple phases, with each phase receiving the exact inputs it needs.

## 4. Extension points before ApplicationContext exists

### 4.1. ApplicationStartingEvent: no prepared Environment yet

`ApplicationStartingEvent` fires very early, after Spring Boot registers listeners/initializers and before most preparation work. This is the right place to **mark a startup phase** or wire up very early foundational logic.

Example illustrating registration only:

```java
SpringApplication app = new SpringApplication(MyApplication.class);

app.addListeners(
    (ApplicationListener<ApplicationStartingEvent>) event ->
        System.out.println("SpringApplication is starting"));

app.run(args);
```

The snippet above requires the corresponding Spring imports and a real `MyApplication` class; it is **not a standalone Java file**. When the listener handles this event, do not do:

```java
// Wrong mindset at an early phase:
myBusinessService.loadData();
```

Application services have not been created by Spring yet. Putting business logic here can cause null errors, dependency failures, or force you to instantiate services outside Spring, breaking application consistency.

**Register at the right time:** the listener must be attached via `SpringApplication.addListeners(...)`, `SpringApplicationBuilder.listeners(...)`, or appropriate bootstrap registration using `META-INF/spring.factories`. A listener defined as a `@Bean` **does not exist early enough** to receive events before the context creates beans.

### 4.2. EnvironmentPostProcessor: modifying properties before context refresh

`EnvironmentPostProcessor` receives `ConfigurableEnvironment` and `SpringApplication`. This is the dedicated extension point when you need to **add or adjust property sources early**.

Example providing a fallback value `demo.region=local` without overriding configuration set by the operator:

**`src/main/java/com/example/lifecycle/RegionDefaults.java`:**

```java
package com.example.lifecycle;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;

public class RegionDefaults implements EnvironmentPostProcessor {

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application) {

        environment.getPropertySources().addLast(
                new MapPropertySource(
                        "demoRegionDefaults",
                        Map.of("demo.region", "local")));
    }
}
```

Register in **`src/main/resources/META-INF/spring.factories`**:

```properties
org.springframework.boot.env.EnvironmentPostProcessor=com.example.lifecycle.RegionDefaults
```

In Spring Boot 3.3, `EnvironmentPostProcessor` is loaded under the key above in `spring.factories`. `addLast` places this source at the end of the property sources list at the time it is added, so higher-priority sources (such as already-loaded user configuration) can override the fallback value. Relative ordering with other environment post-processors can be controlled using `Ordered`/`@Order`; you should check this when a property must affect very early system decisions.

Do not use `@Service` and `@PostConstruct` to add a property that is critical for bean selection via `@ConditionalOnProperty`: by the time `@PostConstruct` runs, registration decisions for many bean definitions have already been made.

### 4.3. ApplicationEnvironmentPreparedEvent: observing Environment without beans

`ApplicationEnvironmentPreparedEvent` is fired when Spring Boot already has an `Environment` for the context, **before creating the context**. An early-registered listener can read property values:

```java
app.addListeners(
    (ApplicationListener<ApplicationEnvironmentPreparedEvent>) event -> {
        String runtimeVersion =
                event.getEnvironment().getProperty("java.version");
        System.out.println("Java runtime: " + runtimeVersion);
    });
```

Because ordering among listeners and environment post-processors can affect the `PropertySources` state a listener sees, you should not assume every additional configuration source has already been processed as intended in an arbitrary listener. For tasks that **create property sources affecting bootstrap**, `EnvironmentPostProcessor` with explicit ordering usually expresses the intent more clearly.

There is no `ApplicationContext` at this point; do not call `getBean` or use `@Autowired` on a bean that does not exist yet to run logic inside an early event.

## 5. ApplicationContextInitializer: context exists, beans are not ready yet

`ApplicationContextInitializer<ConfigurableApplicationContext>` is called **after creating the context, before refresh**. You can use it to configure the context or register bean definitions with APIs supported by the context.

Example of an initializer that only observes the context:

```java
SpringApplication app = new SpringApplication(MyApplication.class);

app.addInitializers(
    (ApplicationContextInitializer<ConfigurableApplicationContext>) context -> {
        System.out.println("Context type: "
                + context.getClass().getSimpleName());
        System.out.println("Active profiles: "
                + String.join(",", context.getEnvironment().getActiveProfiles()));
    });

app.run(args);
```

Here **the context exists**, but **has not been refreshed yet**, so `getBean(MyService.class)` cannot be used as a reliable check for an initialized service.

If you truly need to register a bean programmatically before refresh and the context type is `GenericApplicationContext`, you can use its registration API:

```java
if (context instanceof GenericApplicationContext generic) {
    generic.registerBean(
            "clock",
            java.time.Clock.class,
            java.time.Clock::systemUTC);
}
```

This is a snippet **inserted into the initializer callback**, requiring `org.springframework.context.support.GenericApplicationContext` to be imported or written with its fully qualified name. It registers the bean **definition**; it does not mean `Clock` has already been retrieved by Spring and all singletons have been instantiated inside the callback itself.

If you only want to add a fixed Java configuration, `@Import` or an appropriate `@Configuration` class may be simpler and easier to maintain. Initializers are valuable when you need to intervene from a shared startup/framework entry point before the bean lifecycle.

### Subsequent events that are still early

- `ApplicationContextInitializedEvent`: initializers have run, application bean definitions have **not** been loaded yet.
- `ApplicationPreparedEvent`: bean definitions **have** been loaded, the context still **has not been refreshed**.

The difference between these two milestones matters if you plan to observe or inspect the list of **bean definitions**, though neither is enough to safely invoke a business service. If you need to **modify** definitions, using the proper BeanFactory/Registry post-processing mechanism is usually better than manipulating them directly inside a listener.

## 6. BeanDefinitionRegistryPostProcessor and BeanFactoryPostProcessor: working with bean definitions

Once the bean factory and configuration processing are in place, Spring processes bean definitions before instantiating regular beans.

- `BeanDefinitionRegistryPostProcessor` can add or modify bean definitions through the registry, making it suitable for certain bean-definition generation mechanisms.
- `BeanFactoryPostProcessor` can modify metadata/configuration of existing bean definitions before regular beans are instantiated.

**The primary input at this point is bean definition metadata**, such as bean names, classes, scopes, property values, or registration details. You should not call a business service merely because the bean factory already exists.

A self-contained example of **BeanFactoryPostProcessor** (placed as a class inside a Spring Boot project):

```java
package com.example.lifecycle;

import org.springframework.beans.BeansException;
import org.springframework.beans.factory.config.BeanFactoryPostProcessor;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.stereotype.Component;

@Component
public class BeanCountPostProcessor implements BeanFactoryPostProcessor {

    @Override
    public void postProcessBeanFactory(
            ConfigurableListableBeanFactory beanFactory)
            throws BeansException {

        int definitions = beanFactory.getBeanDefinitionCount();
        System.out.println("Current bean definition count: " + definitions);
    }
}
```

The count depends on the project, dependencies, and auto-configuration; **there is no fixed numeric result**. This measurement counts definitions at the moment of the callback, not "all running beans". Trying to call `getBean` to execute business logic inside a post-processor can cause beans to initialize prematurely, bypassing part of the other post-processors.

Post-processors of this kind are **Spring infrastructure** and should be used with a clear purpose. When the need is simply creating services or standard configuration, `@Component`, `@Bean`, `@Import`, and constructor injection are usually more appropriate.

## 7. BeanPostProcessor, @PostConstruct, and InitializingBean: one bean exists, not the whole system

When Spring begins creating a bean, it resolves and injects dependencies, invokes initialization callbacks, and applies the appropriate `BeanPostProcessor` instances. This is the right phase to **prepare a bean's own internal state**.

Example:

```java
package com.example.lifecycle;

import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Service;

@Service
public class WorkerService {

    private String state = "new";

    @PostConstruct
    public void prepare() {
        state = "initialized";
        System.out.println("3. WorkerService @PostConstruct: " + state);
    }

    public String currentState() {
        return state;
    }
}
```

For `WorkerService`, when `@PostConstruct` runs, dependency injection for this bean itself has already occurred according to Spring's mechanism. It is suitable for validating internal data or preparing internal structures that do not require the entire system.

**Do not** treat `@PostConstruct` as a "Spring Boot ready" milestone. Other beans may not have been instantiated yet, the Web server may not have finished all phases, and runners have not executed yet. If a bean needs to communicate with heavy external resources (database, HTTP service), consider doing so in a hook with clear error reporting, timeouts, and startup behavior.

`BeanPostProcessor` specializes in processing individual beans **before/after initialization**, typically used for AOP, proxies, or similar infrastructure. Do not use it as an "application started" event; the callback may be invoked many times for different beans, and doing heavy work here slows down or affects many beans.

`InitializingBean.afterPropertiesSet()` can be used instead of `@PostConstruct` when you need an explicit initialization hook via a Spring interface; both still belong to the **bean lifecycle** and cannot replace `ApplicationReadyEvent`.

## 8. Context refreshed: Started, Runner, and Ready

### ApplicationStartedEvent: runners have not run yet

`ApplicationStartedEvent` fires after `ApplicationContext` is refreshed and before `ApplicationRunner` / `CommandLineRunner` are called. This is a point where you can observe instantiated beans in the context, but **steps inside runners have not completed yet**.

After `ApplicationStartedEvent`, Spring Boot also publishes a liveness state change to `LivenessState.CORRECT` in the default flow. Being "alive" (liveness) **is not equivalent to** being "ready to accept traffic" (readiness).

### ApplicationRunner and CommandLineRunner: beans are available for work before Ready

`ApplicationRunner` receives `ApplicationArguments`; `CommandLineRunner` receives `String... args`. Both are invoked after Started and before Ready. You can use them to:

- Validate data and complete mandatory initialization work before announcing readiness.
- Load caches or prepare application data needed immediately after startup, if designed synchronously.
- Check for the existence of required configuration and let startup fail visibly if the check fails.

Example placed in a `@Configuration` class:

```java
@Bean
ApplicationRunner verifyAtStartup(WorkerService workerService) {
    return args -> {
        System.out.println("4. Runner sees state: "
                + workerService.currentState());
    };
}
```

This is an illustrative bean method snippet; you need to import `org.springframework.context.annotation.Bean` and `org.springframework.boot.ApplicationRunner` when placing it in a class. It uses **a bean already created by Spring and injected into the `@Bean` method**.

**Beware of long blocking:** synchronous runners can delay the Ready milestone. If the Web server has already opened its socket before the runner runs, some requests may still arrive before the system is marked ready; do not rely on the assumption "not Ready yet = no requests can arrive yet". In deployment, configure readiness probes and traffic routing properly.

### ApplicationReadyEvent: runners have finished

`ApplicationReadyEvent` fires after runners complete successfully, indicating the application has nearly finished the bootstrap sequence. In the default sequence, `AvailabilityChangeEvent` with `ReadinessState.ACCEPTING_TRAFFIC` is published **immediately afterward**. `ApplicationReadyEvent` listeners run **before** this readiness notification.

A bean can use:

```java
@EventListener(ApplicationReadyEvent.class)
public void whenReady() {
    System.out.println("5. ApplicationReadyEvent");
}
```

This method must belong to a created bean (for example, a `@Component` or `@Configuration` class) and import `org.springframework.context.event.EventListener` along with `ApplicationReadyEvent`. Use it for lightweight observation/sequencing around the ready milestone; listeners run synchronously by default, so heavy work can also delay marking readiness. If a task **must complete before Ready**, a runner usually expresses that requirement more clearly.

## 9. Complete example: observing five phases in a single run

The following Spring Boot 3.3.x, Java 17+ project does not require a Web server, making the callback order easy to see. It **does not** attempt to call a service before the bean is created.

Structure:

```text
extension-phase-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/lifecycle/
    ├── ExtensionLifecycleApplication.java
    └── WorkerService.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'extension-phase-demo'
```

**`build.gradle`:**

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

**`src/main/java/com/example/lifecycle/ExtensionLifecycleApplication.java`:**

```java
package com.example.lifecycle;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class ExtensionLifecycleApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ExtensionLifecycleApplication.class);

        // No HTTP server needed in this exercise.
        application.setWebApplicationType(WebApplicationType.NONE);

        // Listener registered before run, because no beans exist yet at this point.
        application.addListeners(
                (ApplicationListener<ApplicationStartingEvent>) event ->
                        System.out.println("0. ApplicationStartingEvent"));

        application.addListeners(
                (ApplicationListener<ApplicationEnvironmentPreparedEvent>) event -> {
                    boolean hasJavaVersion =
                            event.getEnvironment().containsProperty("java.version");
                    System.out.println(
                            "1. Environment has java.version: " + hasJavaVersion);
                });

        application.addInitializers(
                (ApplicationContextInitializer<ConfigurableApplicationContext>) context ->
                        System.out.println(
                                "2. Context exists: "
                                + context.getClass().getSimpleName()));

        application.run(args);
    }

    @Bean
    ApplicationRunner printAfterContext(WorkerService workerService) {
        return args -> System.out.println(
                "4. Runner sees WorkerService: "
                + workerService.currentState());
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onReady() {
        System.out.println("5. ApplicationReadyEvent");
    }
}
```

**`src/main/java/com/example/lifecycle/WorkerService.java`:**

```java
package com.example.lifecycle;

import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Service;

@Service
public class WorkerService {

    private String state = "new";

    @PostConstruct
    public void prepare() {
        state = "initialized";
        System.out.println("3. WorkerService @PostConstruct: " + state);
    }

    public String currentState() {
        return state;
    }
}
```

If the project already has a Gradle Wrapper, run in the `extension-phase-demo` directory:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

If there is no Wrapper yet, create the project via Spring Initializr or use an appropriate Gradle installation to generate the Wrapper files. The example does not assume Wrapper files appear automatically just because you wrote `build.gradle`.

The lines **printed by the program itself** will appear in the following meaningful order; Spring Boot/Gradle will also output other logs in between:

```text
0. ApplicationStartingEvent
1. Environment has java.version: true
2. Context exists: AnnotationConfigApplicationContext
3. WorkerService @PostConstruct: initialized
4. Runner sees WorkerService: initialized
5. ApplicationReadyEvent
```

The value `true` reflects a standard Java system property; the context class name reflects the **default context when using `WebApplicationType.NONE`**. If you customize `ApplicationContextFactory` or run in a significantly different environment, the context name may differ. What must be verified is **the phase order**: environment exists before context, beans initialize before runners, and ready comes after runners.

### Why didn't the example retrieve WorkerService in the first listener?

`ApplicationStartingEvent` and `ApplicationEnvironmentPreparedEvent` arrive when Spring has not created application beans yet. Even though you could **manually** instantiate `new WorkerService()`, that object would lie outside Spring's management and would not be a bean with dependencies injected through the normal lifecycle. The right way to experiment is to read properties at the early phase, and only read services in runners/bean callbacks.

### Why does @EventListener receive Ready but not Starting?

`@EventListener` is discovered when Spring creates and processes beans in the context. Therefore, the `onReady` method in `@SpringBootApplication` works at the late phase. Changing it to `@EventListener(ApplicationStartingEvent.class)` on a bean **does not** make it exist earlier; the Starting event has already occurred before the bean is created.

## 10. Registering hooks properly: not just choosing the right phase

**Early-registered listeners** can be added directly:

```java
SpringApplication app = new SpringApplication(MyApplication.class);
app.addListeners(new MyEarlyListener());
app.run(args);
```

Or configured in `META-INF/spring.factories` using the Boot-supported mechanism, for example:

```properties
org.springframework.context.ApplicationListener=com.example.lifecycle.MyEarlyListener
```

In this case, `MyEarlyListener` must be a class that can be instantiated and implements a valid listener, with its dependencies available during the bootstrap phase. This is a **registration skeleton** requiring a real class; it is not complete standalone code.

**Initializers** can be registered via `SpringApplication.addInitializers(...)` before `run`. **EnvironmentPostProcessor** uses its own key `org.springframework.boot.env.EnvironmentPostProcessor` in `spring.factories` as shown in section 4.

**Late listeners** are typically declared using `@EventListener` or `ApplicationListener<T>` beans belonging to the context. A **Runner** is an `ApplicationRunner` or `CommandLineRunner` bean; **bean hooks** live on Spring-managed classes.

If the goal is to decide early **whether or not to create a bean**, remember that registration timing matters just as much as callback timing: attaching an early listener via a late-created bean will miss the event.

## 11. Scenarios for choosing extension points

### Scenario A — setting fallback properties for multiple modules

**Required inputs:** `ConfigurableEnvironment`, `PropertySources`.  
**Should use:** `EnvironmentPostProcessor`, with `Ordered` when needed.  
**Should not use:** `@PostConstruct` on a service to predetermine properties for `@ConditionalOnProperty`.

Reason: once conditional configuration has already been evaluated, modifying properties late does not guarantee Spring will go back and register skipped beans.

### Scenario B — adding bean definitions very early, before refresh

**Required inputs:** `ConfigurableApplicationContext` / `BeanDefinitionRegistry`.  
**Should use:** `ApplicationContextInitializer` (when the context's API is suitable), `BeanDefinitionRegistryPostProcessor`, or standard configuration mechanisms.  
**Should not use:** `ApplicationReadyEvent` to ask Spring to re-read an entire finalized configuration.

### Scenario C — preparing an internal cache for a single bean

**Required inputs:** the bean's own injected dependencies.  
**Should use:** `@PostConstruct` or `InitializingBean` if the operation is compact and does not create hard-to-control lifecycle dependencies.  
**When coordinating multiple services or when the result is a precondition for Ready:** move the appropriate logic to a runner.

### Scenario D — validating initial data using a service

**Required inputs:** a created bean with dependencies injected.  
**Should use:** `ApplicationRunner` or `CommandLineRunner` when it must finish before Ready.  
**Things to watch out for:** runner failures can cause startup to fail; overly long tasks delay readiness. Proper timeouts, failure handling, and deployment design are required.

### Scenario E — recording that the application completed startup

**Required inputs:** refreshed context and finished runners.  
**Should use:** `ApplicationReadyEvent` for lightweight notifications, startup completion metrics, or actions tied to the Ready milestone.  
**Things to watch out for:** readiness in deployment platforms may involve additional independent probes and checks; `ApplicationReadyEvent` does not mean every external system will always remain operational.

### Scenario F — logging the cause of a startup failure

**Required inputs:** the exception and still-accessible bootstrap information.  
**Should use:** an `ApplicationFailedEvent` listener registered early enough.  
**Must not assume:** `ApplicationContext`, bean-configured logging services, or the database are available; the failure may have occurred before they were created.

## 12. Common mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Putting `@EventListener(ApplicationStartingEvent.class)` on a bean | The listener does not exist when the early event fires | Register via `SpringApplication.addListeners` or `spring.factories`. |
| Using `@Autowired` services in an early environment callback | No context/beans exist yet to inject | Separate property processing in the early phase from business logic in the bean/runner phase. |
| Calling `getBean` inside `ApplicationContextInitializer` | Context has not refreshed yet, beans are not ready | Only configure context/definitions; let Spring create beans according to the lifecycle. |
| Modifying `spring.main.*` after the context has been created | Some bootstrap decisions have already been finalized | Configure via config/Environment before those decisions happen. |
| Using `BeanFactoryPostProcessor` to look up many business beans | Prematurely initializes beans, potentially bypassing other processing | Focus on bean definitions; handle business logic in runners/services. |
| Treating `@PostConstruct` as the application-wide Ready milestone | Other beans, runners, or Web readiness are not finished yet | Use runners or the Ready event for phase-appropriate work. |
| Letting a runner make network calls without timeouts | Can keep the application in an extended startup state | Set timeouts, fail clearly, and control readiness conditions. |
| Doing heavy work inside an `ApplicationReadyEvent` listener | Can delay the readiness notification and event flow | Use a runner for steps that must finish before Ready, or a controlled post-startup mechanism. |
| Assuming HTTP does not accept requests before `ApplicationReadyEvent` | The server may open its socket before Ready | Configure readiness probes and restrict traffic routing. |
| Using one hook everywhere because it "seems to work" | Creates hidden dependencies on initialization order | Choose the hook from available input resources and the milestone that must be completed. |

## 13. How to decide when writing a new feature

Answer four questions in order:

1. **What data does the task actually need?** Only `args`, `Environment`, bean metadata, a bean with injected dependencies, or all started services?
2. **When is that data guaranteed to exist?** Check the phase table; do not try calling an API in too early a phase and rely on luck.
3. **Before which milestone must the result take effect?** Before Spring evaluates configuration, before beans are created, before Ready, or only after Ready?
4. **Can the task fail or take a long time?** Decide where to report errors, set timeouts, and handle startup/readiness impact; do not dump heavy tasks into an arbitrary callback.

You can use a concise rule of thumb:

```text
Need to modify input config?         -> EnvironmentPostProcessor
Need to configure context pre-refresh? -> ApplicationContextInitializer
Need to modify bean definitions?     -> Registry/BeanFactoryPostProcessor
Need to prepare exactly one bean?    -> @PostConstruct / InitializingBean
Need to run service logic before
Ready?                               -> ApplicationRunner / CommandLineRunner
Need to observe the system after
runners?                             -> ApplicationReadyEvent
Need to catch bootstrap errors?      -> ApplicationFailedEvent (early listener)
```

These are guidelines for picking **the right extension point**, not a rule that each task has only one viable API. For simple applications, using `@Configuration`/`@Bean` and constructor injection according to Spring conventions is usually better than adding unnecessary bootstrap hooks.

## 14. Practice exercises

Using the project from section 9, change one factor at a time:

1. Run the application and observe the order `0 -> 1 -> 2 -> 3 -> 4 -> 5`, while also identifying where the `Started ...` line appears between bean initialization and the runner.
2. Try adding `@EventListener(ApplicationStartingEvent.class)` to `WorkerService`, and observe that the new callback on the bean does not receive the overly early event. Keep the `addListeners` listener in `main` to see that it still receives it.
3. Place `System.out.println(workerService.currentState())` in `ApplicationRunner` and confirm it returns `initialized`, then explain why you should not do the same thing inside `ApplicationContextInitializer`.
4. Add a `Thread.sleep(1000)` with proper `InterruptedException` handling inside the runner: the Ready milestone is delayed, while the environment listener and initializer still run before the runner.
5. Add `RegionDefaults` and the `spring.factories` file from section 4 into the proper project package, then read `demo.region` from `Environment` inside the runner. Add a different value from `application.properties` to test fallback behavior and property source precedence.
6. Choose a scenario where the application needs to create a bean based on startup configuration. Explain why changing that property at `ApplicationReadyEvent` cannot automatically ask Spring to re-evaluate all `@ConditionalOnProperty` conditions.

**Self-check questions:** Why doesn't a `@Bean` listener see `ApplicationEnvironmentPreparedEvent`? Why is `@PostConstruct` allowed to use the bean's dependencies while still not guaranteeing that all startup runners have run? Why must `Environment` updates happen early when a property decides whether a bean is created? Being able to answer these questions means you know how to choose extension points by **resources and lifecycle milestones**, rather than guessing at random.

## Official documentation

- Spring Boot 3.3, SpringApplication lifecycle and Application Events ordering: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3, `EnvironmentPostProcessor` Java API and registration: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/env/EnvironmentPostProcessor.html
- Spring Boot 3.3, `ApplicationStartedEvent`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationStartedEvent.html
- Spring Boot 3.3, `ApplicationReadyEvent`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationReadyEvent.html
- Spring Framework, `ApplicationContextInitializer`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/ApplicationContextInitializer.html

When choosing an extension point, evaluate **available resources**, **when the logic must take effect**, and **failure behavior**. A callback that runs is not enough to prove it is at the right time; the right callback is one that receives sufficient data, is early enough to influence the intended decision, and does not create hard-to-control lifecycle dependencies.