# BootstrapContextClosedEvent and Bridging to ApplicationContext in Spring Boot

## 1. The problem: an object needs to be created before ApplicationContext is ready

In a Spring Boot application, not all initialization work can wait until regular beans are instantiated. Some mechanisms must operate **very early**, while Boot is preparing `Environment` or loading application configuration: fetching configuration from an external source, building a client to decrypt config values, storing an object created during bootstrap, or sharing preparation results across multiple startup steps.

At that moment, the main `ApplicationContext` does not exist yet or has not been refreshed (`refresh()`). Therefore, you cannot rely on `@Autowired`, `@Bean`, or `applicationContext.getBean(...)`.

Spring Boot provides a temporary staging area dedicated to the early phase:

- `BootstrapRegistry`: where recipes for creating objects are **registered** under a `Class` key.
- `BootstrapContext`: where registered objects are **retrieved** when needed, usually with lazy creation and singleton storage.
- `ConfigurableBootstrapContext`: combines the registration and lookup interfaces.
- `BootstrapRegistryInitializer`: an extension point for registering entries into the bootstrap registry before the application boots further.
- `BootstrapContextClosedEvent`: an event at **the end of the bootstrap scope**, carrying both the bootstrap context and the prepared `ApplicationContext`.

**Core meaning:** once Boot has created and prepared `ApplicationContext` but **before refreshing it**, Boot closes the bootstrap registry lifecycle and notifies registered listeners. Listeners can transfer objects worth keeping from bootstrap into `ApplicationContext`, so regular beans later use those exact objects. This event is **not** a JVM shutdown signal, does not mean the application finished running, and is not synonymous with `ContextClosedEvent`.

Picture a shift handoff:

1. The **bootstrap** team prepares tools before the factory opens.
2. Once the **Spring factory** has built its frame, the bootstrap team hands over the prepared tools.
3. The factory continues assembling and starting up its components (beans).
4. The bootstrap team concludes its role. The handed-off tools can keep living for the application's lifecycle if managed properly.

This article focuses on **Spring Boot 3.3.x / Java 17+** at **the startup extension-point level**. Do not confuse this mechanism with a separate "bootstrap ApplicationContext" in certain **Spring Cloud** setups.

## 2. Distinguishing objects containing the word "context"

| Component | Nature | When present? | What does it hold? |
| --- | --- | --- | --- |
| `BootstrapRegistry` | Configurable registry | Very early, before application context | Suppliers registered under a `Class<T>` key |
| `BootstrapContext` | Object retrieval interface | During the bootstrap process | Objects instantiated on demand from suppliers |
| `ConfigurableBootstrapContext` | Combined registry + context | Provided by Boot to bootstrap machinery | `register`, `get`, and `addCloseListener` capabilities |
| `DefaultBootstrapContext` | Boot's default implementation | From `SpringApplication` start until bootstrap close | Map of suppliers/instances and close listeners |
| `ConfigurableApplicationContext` | Spring bean container about to be refreshed | After Boot selects and creates the context | `Environment`, `BeanFactory`, definitions, listeners, and after refresh, instantiated beans |
| `ApplicationContext` | Container consumption interface | Throughout the application lifecycle | Bean lookup, environment, events, resources... |

**The word "closed" in `BootstrapContextClosedEvent` refers solely to closing the bootstrap phase.** It does not close `ApplicationContext`. Right when a listener receives the event, the application context exists to prepare for handoff, yet application beans are typically **not** instantiated yet.

### 2.1. Do not treat BootstrapContext as BeanFactory

`BootstrapContext.get(Client.class)` looks up by a type registered in the bootstrap registry. This mechanism does **not** perform `@ComponentScan`, does not perform full bean-container dependency injection, and does not automatically turn an object into a Spring bean.

Conversely, `ApplicationContext.getBean(Client.class)` only works for beans registered/managed in BeanFactory once they reach a usable stage. Moving from the registry into the bean container is **an intentional operation** at the handoff point.

### 2.2. BootstrapRegistryInitializer differs from ApplicationContextInitializer

`BootstrapRegistryInitializer.initialize(BootstrapRegistry registry)` works with **the early startup registry**.

`ApplicationContextInitializer.initialize(ConfigurableApplicationContext context)` works with **the already-created application context, before refresh**.

Both initializers run before `refresh()`, yet have **different inputs and goals**. If you need to register a client for a config-preparation step, use the bootstrap registry. If you only want to add listeners/PropertySources once the context exists, `ApplicationContextInitializer` may be the right choice.

## 3. Exact milestone of BootstrapContextClosedEvent

Conceptual order within `SpringApplication.run(...)` in Spring Boot 3.3:

```text
SpringApplication.run(args)
    |
    +-- Create ConfigurableBootstrapContext (usually DefaultBootstrapContext)
    +-- Run BootstrapRegistryInitializers
    +-- Start SpringApplicationRunListener chain
    +-- Prepare Environment / ConfigData
    |       |
    |       +-- Early startup components can use BootstrapContext
    |
    +-- Create appropriate ConfigurableApplicationContext type
    +-- Attach Environment, prepare context
    +-- Run ApplicationContextInitializers
    +-- Notify contextPrepared
    |       |
    |       +-- ApplicationContextInitializedEvent
    |
    +-- bootstrapContext.close(applicationContext)
    |       |
    |       +-- BootstrapContextClosedEvent
    |       +-- Close listeners receive both BootstrapContext and ApplicationContext
    |
    +-- Load primary sources and bean definitions
    +-- Notify contextLoaded
    |       |
    |       +-- ApplicationPreparedEvent
    |
    +-- applicationContext.refresh()
    |       |
    |       +-- BeanFactoryPostProcessor, BeanPostProcessor
    |       +-- Instantiate non-lazy singletons
    |       +-- ContextRefreshedEvent
    |
    +-- ApplicationStartedEvent
    +-- ApplicationRunner / CommandLineRunner
    +-- ApplicationReadyEvent
```

This describes **Boot 3.3's standard startup flow**, not a contract for the exact order of every callback across all custom integrations. Application events and `ConfigData` behavior have their own specifics; do not rely on the diagram to implement extension points beyond API contracts.

### 3.1. Three commonly confused boundaries

**Boundary A — after application context initializers:** `ApplicationContextInitializedEvent` fires after `ApplicationContextInitializer` runs, before primary bean definitions are loaded. `BootstrapContextClosedEvent` sits within this preparation region.

**Boundary B — before refresh:** `ApplicationPreparedEvent` fires after sources/bean definitions are loaded but before `refresh()`. Bootstrap closing has already occurred **before** this milestone in the standard path.

**Boundary C — long before ready:** `ApplicationReadyEvent` only arrives after refresh and runners. Bootstrap close listeners must not expect to call Spring-injected repositories, controllers, or services; those beans have not completed initialization yet.

### 3.2. Why is it called closed while the application context remains alive?

The bootstrap registry has a **short lifespan**. Once the Spring application context has been prepared, Boot can end providing the bootstrap registry as a startup configuration point. It publishes the event so components wanting to migrate still-needed resources into the new management scope get their chance.

At this moment, `ApplicationContext` itself is only at **the start of its lifecycle**. Closing bootstrap does **not** call `ApplicationContext.close()` and does **not** trigger graceful shutdown.

## 4. What does BootstrapContextClosedEvent carry?

Class `org.springframework.boot.BootstrapContextClosedEvent` extends `ApplicationEvent` and provides two key APIs:

```java
BootstrapContext getBootstrapContext();
ConfigurableApplicationContext getApplicationContext();
```

These are **illustrative signatures** of the event's two methods, not a standalone Java file.

- `getBootstrapContext()`: returns the bootstrap context completing its lifecycle, used to retrieve a registered object, e.g., `event.getBootstrapContext().get(MyClient.class)`.
- `getApplicationContext()`: returns the **prepared** `ConfigurableApplicationContext`. You can access BeanFactory or Environment to register objects/metadata for the rest of startup.

The main purpose is **bridging** between the two startup scopes. It does not provide HTTP requests, readiness status, runner results, or a guarantee that all singletons exist.

### 4.1. Listener must be registered via addCloseListener

`BootstrapRegistry` provides the method:

```java
void addCloseListener(
    ApplicationListener<BootstrapContextClosedEvent> listener
);
```

In practice, it is usually written as:

```java
registry.addCloseListener(event -> {
    // Retrieve data from the bootstrap context.
    // Register into the application context when genuinely needed.
});
```

The snippet above illustrates code placed **inside** `BootstrapRegistryInitializer.initialize(...)`.

This is a listener registered **within the bootstrap mechanism itself**. Do not replace it with `@EventListener(BootstrapContextClosedEvent.class)` on a regular application bean: beans are created during refresh, which is **later** than the bootstrap close milestone. Nor should you assume all `ApplicationListener` beans in the application context will receive this event through the same publishing path.

### 4.2. Why does the event belong to Spring Boot rather than ContextClosedEvent?

| Event | Source | When? | Purpose |
| --- | --- | --- | --- |
| `BootstrapContextClosedEvent` | Spring Boot's `BootstrapContext` | Once application context is prepared, before refresh | Hand off objects/config from bootstrap to container |
| `ApplicationContextInitializedEvent` | `SpringApplication` | After application context initializers, before loading bean definitions | Observe/act at context-prepared milestone |
| `ApplicationPreparedEvent` | `SpringApplication` | Before refresh, after loading definitions | Observe milestone where sources are prepared |
| `ContextRefreshedEvent` | `ApplicationContext` | After refresh | Context has been refreshed |
| `ApplicationReadyEvent` | `SpringApplication` | After runners | Boot announces application is ready |
| `ContextClosedEvent` | `ApplicationContext` | When application context actually closes | Stop components, destroy beans, clean up application |

The word "Closed" is shared, yet **the scopes being closed are completely different**.

## 5. Registering and retrieving objects from the bootstrap registry

### 5.1. Using Class as the key

`BootstrapRegistry` registers suppliers by type, for example:

```java
registry.registerIfAbsent(StartupClient.class,
        bootstrapContext -> new StartupClient("early-config"));
```

Assuming a hypothetical `StartupClient` class with a `String` constructor, this is a **snippet inside `initialize(BootstrapRegistry registry)`**, not a standalone program.

- `register`: registers a supplier for the type; if a supplier is already registered and that type's instance **has not yet been retrieved and stored as a singleton**, it can replace the registration.
- `registerIfAbsent`: does not replace an existing supplier for the type.
- `isRegistered`: checks whether the type has been registered.
- `getRegisteredInstanceSupplier`: retrieves the registered supplier if present.

Because the key is `Class`, a `BootstrapRegistry` is not a bag of named beans: you cannot register five different objects of the same class under five names like Spring BeanFactory's `@Qualifier` without designing appropriate wrapper/key types.

### 5.2. Lazy creation and holding one instance

`BootstrapContext` offers `get(Class<T>)`, `getOrElse(...)`, `getOrElseSupply(...)`, and `getOrElseThrow(...)`. Typically the instance is created **when the first `get(...)` occurs**, using the registered `InstanceSupplier<T>`; the default scope is normally singleton per bootstrap context. Thus **registering** a supplier does not mean the client's constructor has already run.

Example:

```java
registry.registerIfAbsent(StartupClient.class, bootstrap -> {
    System.out.println("Creating StartupClient");
    return new StartupClient("early-config");
});

// In another startup step that has BootstrapContext:
StartupClient client = bootstrapContext.get(StartupClient.class);
```

These two snippets sit in two different places. The log line appears **when the instance is actually accessed**, not necessarily when the registry is created. `get(...)` for an unregistered type throws `IllegalStateException`; use `getOrElseSupply(...)` if you need a custom fallback.

### 5.3. Notes on initialization cost

Registering lightweight suppliers and creating lazily helps when a client is expensive. However, if a close listener tries to fetch every type eagerly, lazy creation happens at **bootstrap close time**. That increases startup time and can trigger errors before refresh. Only hand off objects that are genuinely still needed.

A bootstrap object might already have been used in an `EnvironmentPostProcessor` or a config-processing component. Retrieving it again via `get(MyType.class)` inside the close listener lets you **transfer that exact instance** when it is a singleton, avoiding creating a second client for the application.

## 6. How to hand off into ApplicationContext?

Two common needs must be distinguished.

### 6.1. Transferring a configuration value

If what needs to be kept is merely an early-prepared value/metadata, the listener can add a `PropertySource` to the application context's `Environment`:

```java
registry.addCloseListener(event -> {
    String resolvedMode = "safe"; // Example: result prepared during bootstrap.
    event.getApplicationContext().getEnvironment()
            .getPropertySources()
            .addLast(new MapPropertySource(
                    "bootstrapDefaults",
                    Map.of("demo.mode", resolvedMode)));
});
```

Illustrative Java snippet; requires importing `java.util.Map` and `org.springframework.core.env.MapPropertySource`. `addLast(...)` places this source at low priority, allowing existing configuration a chance to override. For other policy data, choose source ordering per your application's contract.

Do not use this mechanism to alter **decisions already made before the context existed**, such as trying to change `WebApplicationType` after Boot created the context. Also never expose secret keys in logs or exceptions.

### 6.2. Promoting an instance to a bean for injection

`ConfigurableApplicationContext.getBeanFactory()` provides the BeanFactory ready for pre-refresh registrations. A concise way:

```java
registry.addCloseListener(event -> {
    StartupClient client =
            event.getBootstrapContext().get(StartupClient.class);
    event.getApplicationContext().getBeanFactory()
            .registerSingleton("startupClient", client);
});
```

This is a **snippet placed inside the registry initializer**, assuming `StartupClient` was already registered in `BootstrapRegistry`.

Later, when application `@Bean`/`@Component` instances are created, BeanFactory already knows the singleton named `startupClient` and can inject it as a dependency if type/naming do not conflict.

**Technical detail to know:** `registerSingleton(...)` supplies an **already-existing instance**. It is not equivalent to Spring building a bean through the full pipeline of bean definition, injection, BeanPostProcessors, and init/destroy callbacks. Specifically, do not automatically expect `@PostConstruct`, `@PreDestroy`, or a destroy method to be fully managed just from calling `registerSingleton`. If a resource needs Spring to own its full lifecycle, use bean definition registration with an appropriate supplier or a managed adapter bean handling resource disposal.

### 6.3. Choosing BeanDefinition when Spring's lifecycle is needed

In a Boot app using `DefaultListableBeanFactory`, you can register a bean definition with a supplier returning the same bootstrap instance:

```java
registry.addCloseListener(event -> {
    StartupClient client =
            event.getBootstrapContext().get(StartupClient.class);

    ConfigurableListableBeanFactory beanFactory =
            event.getApplicationContext().getBeanFactory();

    if (!(beanFactory instanceof BeanDefinitionRegistry definitions)) {
        throw new IllegalStateException(
                "BeanFactory does not support BeanDefinitionRegistry");
    }

    RootBeanDefinition beanDefinition =
            new RootBeanDefinition(StartupClient.class);
    beanDefinition.setInstanceSupplier(() -> client);
    definitions.registerBeanDefinition("startupClient", beanDefinition);
});
```

This is an **advanced snippet**, requiring imports for `ConfigurableListableBeanFactory`, `BeanDefinitionRegistry`, and `RootBeanDefinition`; `StartupClient` is your own type. A bean definition with an instance supplier lets Spring manage the bean when instantiated by BeanFactory, supporting post-processing and callbacks per contract. Carefully verify singleton policy, bean naming, circular dependencies, and resource ownership.

The `registerSingleton` and `registerBeanDefinition` snippets are **two alternative approaches**; do not use both simultaneously for the same bean name. For a simple immutable object like the main example below, `registerSingleton` is clear enough.

## 7. Complete Java 17+ example: transferring the same instance from bootstrap to BeanFactory

This example consists of **a single complete Java file**, needing no HTTP server or database. We will create a `BootstrapValue` object via the early registry, hand that instance over to the application BeanFactory on the close event, and inject it into an `ApplicationRunner` to prove the end-to-end flow.

**Prerequisites:** Spring Boot 3.3.x, Java 17+, a Gradle project with the Spring Boot plugin and `spring-boot-starter`.

**File:** `src/main/java/com/example/bootstrap/BootstrapTransferApplication.java`

```java
package com.example.bootstrap;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class BootstrapTransferApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(BootstrapTransferApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        app.addBootstrapRegistryInitializer(registry -> {
            registry.registerIfAbsent(BootstrapValue.class, bootstrap -> {
                System.out.println("02 SUPPLIER: creating bootstrap value");
                return new BootstrapValue("from-early-bootstrap");
            });
            System.out.println("01 REGISTRY: supplier registered");

            registry.addCloseListener(event -> {
                BootstrapValue value = event.getBootstrapContext()
                        .get(BootstrapValue.class);

                event.getApplicationContext().getBeanFactory()
                        .registerSingleton("bootstrapValue", value);

                System.out.println("03 HANDOFF: applicationContext active="
                        + event.getApplicationContext().isActive());
            });
        });

        try (ConfigurableApplicationContext context = app.run(args)) {
            BootstrapValue transferred =
                    context.getBean(BootstrapValue.class);
            System.out.println("05 AFTER_RUN: same bean="
                    + (transferred == context.getBean("bootstrapValue")));
        }
    }

    @Bean
    ApplicationRunner showTransferredValue(BootstrapValue value) {
        return args -> System.out.println(
                "04 RUNNER: value=" + value.value());
    }

    public record BootstrapValue(String value) {
    }
}
```

**Meaning of each point:**

1. `addBootstrapRegistryInitializer(...)` registers an early startup callback. Inside it, `registerIfAbsent` only registers the supplier without instantiating `BootstrapValue` yet.
2. `addCloseListener(...)` attaches a dedicated listener to the bootstrap registry.
3. When Boot closes the bootstrap context, the listener calls `event.getBootstrapContext().get(BootstrapValue.class)`; the supplier constructs the instance if it has not been retrieved elsewhere.
4. The listener registers **that exact instance** in the application context's BeanFactory under the name `bootstrapValue`, at a moment when BeanFactory has not yet processed all application beans.
5. After `refresh()`, Spring instantiates the `ApplicationRunner` bean; the `BootstrapValue` dependency is resolved from the newly handed-off singleton.
6. `SpringApplication.run(...)` returns `ConfigurableApplicationContext` after startup; the `try` block verifies identity, then calls `close()` per `AutoCloseable`.

### 7.1. Gradle dependencies

In a Spring Boot 3.3.x project with appropriate plugin/build setup:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

Spring Web or Spring WebFlux is not required because the example intentionally uses `NONE`.

### 7.2. Run command

From the project directory with Gradle Wrapper:

```bash
./gradlew bootRun
```

Windows CMD uses `gradlew.bat bootRun`; PowerShell uses `.\gradlew.bat bootRun`. If Boot does not automatically detect the main class in your project, configure `springBoot { mainClass = 'com.example.bootstrap.BootstrapTransferApplication' }` in the Gradle build. A project containing multiple main classes may require specifying the main class explicitly.

### 7.3. Output lines printed by the example

Ignoring banners and framework logs, on a successful startup with no custom initializer altering logic, the example lines print in this order:

```text
01 REGISTRY: supplier registered
02 SUPPLIER: creating bootstrap value
03 HANDOFF: applicationContext active=false
04 RUNNER: value=from-early-bootstrap
05 AFTER_RUN: same bean=true
```

**Why is `active=false` on the handoff line?** `BootstrapContextClosedEvent` occurs before `refresh()`; the active flag on standard `AbstractApplicationContext` is only turned on during refresh. That is expected behavior, not a startup error.

**Why is `same bean=true`?** We registered **the exact instance** into BeanFactory rather than creating a copy. Both `ApplicationRunner` and `getBean(...)` reference that instance. The example record holds no connections or threads so it needs no special cleanup. Do not generalize this contract to I/O resources with complex lifecycle needs if you use raw `registerSingleton`.

**Caution when modifying the example:** do not add another `@Component` or `@Bean` with the same `BootstrapValue` type/name without handling conflicts explicitly. This example intentionally keeps the record as a plain data type; the sole bean registration lives in the close listener.

## 8. Ways to register BootstrapRegistryInitializer

### 8.1. Directly on SpringApplication

```java
SpringApplication app = new SpringApplication(MyApplication.class);
app.addBootstrapRegistryInitializer(new MyBootstrapInitializer());
app.run(args);
```

This snippet goes inside `main`, assuming `MyBootstrapInitializer` implements `BootstrapRegistryInitializer`. This approach is clear when you control the main class and want to declare the extension point directly.

### 8.2. Implementing a dedicated class in a library

```java
package com.example.bootstrap;

import org.springframework.boot.BootstrapRegistry;
import org.springframework.boot.BootstrapRegistryInitializer;

public final class MyBootstrapInitializer
        implements BootstrapRegistryInitializer {

    @Override
    public void initialize(BootstrapRegistry registry) {
        registry.registerIfAbsent(BootstrapValue.class,
                bootstrap -> new BootstrapValue("library-default"));

        registry.addCloseListener(event -> {
            BootstrapValue value = event.getBootstrapContext()
                    .get(BootstrapValue.class);
            event.getApplicationContext().getBeanFactory()
                    .registerSingleton("bootstrapValue", value);
        });
    }
}
```

This is a **complete implementation class** requiring `BootstrapValue` to be defined in the same package or imported. If using it alongside section 7's example, avoid registering a bean with the same name twice. This class should be used as an **alternative** to the lambda placed in `main`.

### 8.3. Auto-discovery via META-INF/spring.factories

When distributing a starter/library shared by multiple applications, Spring Boot can locate `BootstrapRegistryInitializer` via `SpringFactoriesLoader`. Add the file:

**`src/main/resources/META-INF/spring.factories`**

```properties
org.springframework.boot.BootstrapRegistryInitializer=\
com.example.bootstrap.MyBootstrapInitializer
```

For this to work, the class must be on the application's runtime classpath and instantiable via Spring Boot's factory loading mechanism. Do not confuse this line with the legacy key for registering **auto-configuration classes**: Spring Boot 3.x has its own `AutoConfiguration.imports` mechanism for auto-configuration, while `spring.factories` retains its role for certain factories such as bootstrap initializers.

If auto-discovery is used, do not register the same initializer again in `main` unless there is a clear reason and idempotency is guaranteed. Registering two listeners transferring the same bean name can cause conflicts.

## 9. Bootstrap client and EnvironmentPostProcessor: real-world case

An infrastructure scenario: an application fetches configuration from an external source before Spring creates beans. The config-fetching code resides in an `EnvironmentPostProcessor` or corresponding ConfigData component; it cannot `@Autowired`-inject a client from BeanFactory because the container is not ready yet.

Appropriate design flow:

```text
BootstrapRegistryInitializer
    |
    +-- registerIfAbsent(ConfigClient.class, supplier)
    +-- addCloseListener(listener)
    |
EnvironmentPostProcessor / ConfigData component
    |
    +-- receives BootstrapContext via Boot-supported mechanism
    +-- ConfigClient client = bootstrapContext.get(ConfigClient.class)
    +-- uses client to load/configure PropertySource
    |
BootstrapContextClosedEvent
    |
    +-- Retrieves ConfigClient of the same type/instance
    +-- Registers as a Spring bean if still needed at runtime
    |
ApplicationContext.refresh()
    |
    +-- Runtime beans can inject ConfigClient
```

**Important detail:** a typical `EnvironmentPostProcessor` implements `postProcessEnvironment(ConfigurableEnvironment, SpringApplication)`; if it needs the bootstrap context, it must use **an integration path supported by your Boot version**, such as constructor injection via the loader mechanism for that component or a resolver/loader context API. Do not invent an unbacked `bootstrapContext` variable, or assume every class implementing `EnvironmentPostProcessor` gets injected like a normal bean.

### 9.1. Only reuse the client when needed

If the client is only used once to load configuration, there is no need to transfer it into the application context; you can keep startup lean and let the resource be closed according to library policy. If runtime still needs the client for administrative operations or config updates, the close listener is the intentional handoff point.

### 9.2. Property processing order

For a new property to influence config parsing/loading, it typically must exist **during Environment preparation**, before Boot finishes processing ConfigData. Adding a `PropertySource` **at bootstrap close** is still helpful for not-yet-instantiated beans, though it may be too late to change decisions ConfigData already made.

Therefore, do not use a close listener to modify options Boot already applied earlier, such as selecting `WebApplicationType` or initial config-loading policies. Place configuration at a sufficiently early extension point.

## 10. Ownership handoff and resource management

An object created during bootstrap might be an immutable value object (very simple), or it might hold sockets, connection pools, threads, file handles, or decryptors.

If you transfer such a resource into the application context, answer clearly:

1. **Who owns the instance after handoff?** Are bootstrap registry and BeanFactory holding references to the same object or separate objects?
2. **Who is responsible for calling `close()` / `dispose()`?** If Boot only sees it via raw `registerSingleton`, do not assume a destroy callback is wired up.
3. **Who handles cleanup if startup fails before or after handoff?** Are there created resources that were never handed off?
4. **Who guarantees single disposal?** Two sides closing one client can cause errors if the client is not idempotent.
5. **Across multiple ApplicationContexts or multiple SpringApplication runs**, are created instances shared or independent? Do not accidentally keep a static JVM-wide singleton when you only want one per startup.
6. **Are thread-safety and usage scope appropriate for the resource?** A client created very early may have different settings than once runtime is complete.

### 10.1. Avoid confusing raw singletons with Spring-managed lifecycles

`beanFactory.registerSingleton("name", instance)` registers a pre-existing instance. It skips the steps where Spring **constructs** a bean from a definition. For genuine `AutoCloseable` objects, consider a `BeanDefinition` with a supplier and properly configured destroy method, or wrap it in a managed adapter bean:

```java
@Bean(destroyMethod = "close")
RuntimeClientOwner clientOwner(ConfigClientClient client) {
    return new RuntimeClientOwner(client);
}
```

This snippet is purely **illustrative**, assuming `RuntimeClientOwner` has a `close()` method and `ConfigClientClient` is already a bean. It will not compile standalone without defining those two classes. The goal is to distinguish a bootstrap instance from Spring's cleanup management mechanism.

A non-idempotent resource needs an explicit contract to avoid double-closing. Closing the bootstrap context **does not automatically guarantee** that resources registered in it have been transferred to BeanFactory or safely destroyed.

### 10.2. Do not keep the registry as a runtime service

In normal designs, the bootstrap registry exists solely for the pre-application-context phase. Do not inject the registry itself into every service and keep calling `registry.register(...)` arbitrarily during runtime requests. If business logic needs a dynamic registry, write a runtime bean/service with its own lifecycle and concurrency control.

## 11. Error handling during the handoff phase

### 11.1. Unregistered type

`event.getBootstrapContext().get(MyClient.class)` throws an error if the type has not been registered. Before retrieving, you can check:

```java
if (event.getBootstrapContext().isRegistered(MyClient.class)) {
    MyClient client =
            event.getBootstrapContext().get(MyClient.class);
    // Register in application context when genuinely needed.
}
```

This snippet lives inside a close listener, with `MyClient` defined by the application. If it is a required dependency, it is usually better to **fail fast** with a clear error rather than silently skipping.

### 11.2. Duplicate bean name or type

If handoff uses the name `startupClient` while another module also declares a bean with the same name, startup can conflict or behave unpredictably. `registerIfAbsent` only checks **the bootstrap registry**; it does not guarantee Spring's BeanFactory has no bean of the same name/type from other config sources loaded later.

How to reduce risk: use distinct, descriptive bean names, control load order, avoid duplicate configuration classes, and write integration tests running with real starters/auto-configurations.

### 11.3. Listener throwing exceptions

Close listeners run on the standard startup path, **before refresh**. Exceptions in a supplier or listener can cause `SpringApplication.run` to fail and prevent the app from reaching ready. Therefore:

- Report errors describing the type, phase, and root cause without printing secrets.
- Configure I/O timeouts if a supplier opens external connections.
- Never swallow mandatory errors and leave runtime beans running without required resources.
- Clean up opened resources when needed and aligned with ownership.
- Avoid infinite retries inside a listener; a blocked startup can keep health probes from ever reporting ready.

### 11.4. Should you call bootstrapContext.close(...) manually?

Normally **no**. `SpringApplication` coordinates close timing so the application context is in the right phase, passing the prepared context to listeners. Calling close manually can fire the event too early, multiple times, or with the wrong context. `DefaultBootstrapContext.close(ConfigurableApplicationContext)` is an implementation API for the bootstrap pipeline, not a "shutdown button" for business services.

## 12. Comparing BootstrapContextClosedEvent with other extension points

| What do you need to do? | Appropriate extension point | Why? |
| --- | --- | --- |
| Register a client for very early config-loading | `BootstrapRegistryInitializer` | Registry exists before application context. |
| Consume a registered object early | `BootstrapContext` API via compatible integration | Fetches an instance by class key; creates lazily if needed. |
| Retain an early object for runtime injection | `BootstrapRegistry.addCloseListener` + handoff | Has both bootstrap instance and prepared BeanFactory. |
| Add properties for ConfigData loading | `EnvironmentPostProcessor`/ConfigData API | May need to run before application context is created. |
| Modify context before loading bean definitions | `ApplicationContextInitializer` | Receives `ConfigurableApplicationContext` before refresh. |
| Customize bean definitions | `BeanDefinitionRegistryPostProcessor` / `BeanFactoryPostProcessor` | Operates during refresh. |
| Perform business I/O needing services/repositories | `ApplicationRunner` or appropriate lifecycle bean | Beans are already instantiated. |
| Serve endpoints | Spring MVC/WebFlux handler | Only after web runtime is built. |
| Clean up beans on app shutdown | Destroy callbacks, `SmartLifecycle`, `ContextClosedEvent` as needed | That is application context shutdown, distinct from bootstrap close. |

Not every application needs a bootstrap registry. For most services that simply read properties from `application.yml` and inject regular beans, configuration plus the bean container suffice.

## 13. Why not catch this event with @EventListener?

The following example **must not be used as the primary mechanism to receive the bootstrap close event**:

```java
@Component
class IncorrectListener {
    @EventListener
    void onBootstrapClose(BootstrapContextClosedEvent event) {
        // This bean is normally only instantiated during refresh,
        // after the bootstrap context has already closed.
    }
}
```

This example **illustrates wrong timing**, assuming imports for `@Component`, `@EventListener`, and `BootstrapContextClosedEvent`. Reason: Spring has not built beans when bootstrap close listeners need to run, and `BootstrapContextClosedEvent` is dispatched by the bootstrap listener mechanism rather than guaranteed to go through the application context's initialized `ApplicationEventMulticaster`.

The right way is early registration:

```java
registry.addCloseListener(event -> {
    // Handoff at bootstrap close time.
});
```

If a library needs auto-registration, use `BootstrapRegistryInitializer` via `spring.factories` as shown in section 8.

## 14. Distinguishing from Spring Cloud bootstrap context

In some Spring Cloud setups, the term *bootstrap context* also refers to **a separate Spring `ApplicationContext`** running prior to the main application (for example, certain Spring Cloud Config / legacy bootstrap mechanisms).

Core **Spring Boot's** `BootstrapRegistry` mechanism in this article is **a lightweight registry** that does not inherently create a parent context full of Spring beans. Do not infer that:

- Seeing `BootstrapContextClosedEvent` means a "Spring Cloud bootstrap ApplicationContext" closed.
- Fetching a bean from `BootstrapContext` is the same as `@Autowired` from a Spring Cloud parent context.
- All Spring Cloud `bootstrap.yml` mechanisms follow the exact same event ordering regardless of Cloud version/config.

If using Spring Cloud, verify version compatibility with Boot and the specific config-loading path. This article intentionally presents only Spring Boot 3.3 APIs to avoid conflating the two systems.

## 15. How to test and verify handoff behavior

When implementing a real `BootstrapRegistryInitializer`, valuable checks include:

1. **Early registration:** confirm the initializer runs before the config-loading step consumes the client.
2. **Lazy singleton:** the supplier only creates an instance when `get(...)` actually happens, and with singleton scope does not recreate for the same type.
3. **Correct event timing:** handoff runs after the application context is prepared, yet before refresh/runners.
4. **Correct identity:** the application receives the exact same object (or an intentional copy) as bootstrap.
5. **No bean collisions:** registered names/types do not clash with component scan or other starters.
6. **Cleanup:** I/O resources are closed once when the app exits or startup fails.
7. **Failure cases:** unregistered type, supplier throwing exceptions, and listener throwing exceptions produce clear logs/exit behavior.
8. **No leaked secrets:** never print sensitive internal endpoints, tokens, or full configs in startup logs.
9. **Right environment:** test with real profiles and dependencies; test startup can behave differently under custom test configurations.
10. **Independence across runs:** if creating multiple `SpringApplication`/contexts in one test JVM, never let a static registry accidentally hold instances across runs.

With section 7's example, simply run `./gradlew bootRun` and observe lines `01` through `05` in order. It demonstrates lazy creation, handoff, and injection. You do **not** need to start an HTTP server to test this because it is Spring Boot startup lifecycle, not request routing.

## 16. Common misconceptions and fixes

| Misconception or symptom | Reality | How to handle |
| --- | --- | --- |
| "BootstrapContextClosedEvent means the app is shutting down." | It only closes the very early bootstrap scope. | Distinguish from `ContextClosedEvent`. |
| "The event fires after ApplicationReadyEvent." | Bootstrap closes before refresh and runners. | Check startup event ordering. |
| "Having a @Bean lets bootstrap context fetch it automatically." | The registry is not a BeanFactory. | Use `BootstrapRegistryInitializer.register(...)`. |
| "Just registering a supplier already creates the client." | Usually created lazily on `get`. | Add constructor logging and check first access. |
| "@EventListener on a @Component catches bootstrap close." | That bean/listener typically exists only after refresh. | Use `registry.addCloseListener`. |
| "App beans are ready inside the close listener." | Context is prepared, not refreshed yet. | Do not call `getBean` on business beans; only perform valid registrations. |
| "Closing bootstrap automatically registers every object as a Spring bean." | There is no blanket automatic handoff. | Intentionally hand off required types/instances. |
| "registerSingleton runs full @PostConstruct and @PreDestroy." | Raw singletons skip many lifecycle steps. | Use BeanDefinition or a managed owner when needed. |
| "Once an instance is transferred, keep using the registry at runtime." | Bootstrap registry is temporary startup scaffolding. | Access via the handed-off Spring bean. |
| "registerIfAbsent prevents all Spring bean conflicts." | It only checks keys inside the bootstrap registry. | Also check BeanFactory names/types. |
| "Close listeners are suitable for heavy batch jobs." | They sit on the startup critical path. | Keep work minimal; move post-refresh business logic to runners. |
| "Adding a PropertySource at close alters all prior startup choices." | Several choices have already been applied by Boot. | Place config/processors in an earlier phase. |
| "Spring Cloud bootstrap and Boot BootstrapRegistry are the same context." | They have different designs, lifecycles, and APIs. | Verify module/version and each term's exact meaning. |
| "Just call DefaultBootstrapContext.close() to reset startup." | Boot owns the bootstrap close sequence. | Let `SpringApplication` orchestrate it. |

## 17. Practice exercises

**Exercise A — Observing lazy creation:** in section 7's example, add a log inside the supplier. Run the program and compare that log's position with `REGISTRY` and `HANDOFF`. Explain why registering the supplier did not create the object yet.

**Exercise B — Proving handoff:** remove the `registerSingleton(...)` line while keeping `@Bean ApplicationRunner` requesting `BootstrapValue`. Predict at which stage startup will fail, then restore the registration line and explain the difference between the two containers.

**Exercise C — Comparing events:** trace the path `ApplicationContextInitializedEvent → BootstrapContextClosedEvent → ApplicationPreparedEvent → refresh → ApplicationStartedEvent → ApplicationReadyEvent`. Mark at which milestone BeanFactory can be used for registration and at which milestone business beans are instantiated.

**Exercise D — Ownership:** suppose `BootstrapValue` is a client holding a socket instead of a record. Design who owns it after handoff, when the socket closes, how to avoid double-closing, and how to clean up if startup fails before handoff.

**Exercise E — Distinguishing two bootstrap contexts:** describe why core Boot's registry is not equivalent to a Spring Cloud parent `ApplicationContext`. Point to one API on each side and their characteristic lifecycles.

## 18. Checklist to remember

- `BootstrapRegistryInitializer` is an **ultra-early** registration point, before the main bean container is complete.
- The registry is keyed by `Class<T>`; `get(Class<T>)` retrieves registered instances and may instantiate lazily.
- `BootstrapContextClosedEvent` provides **both `BootstrapContext` and `ConfigurableApplicationContext`**.
- The event fires once the application context is **prepared**, still **before refresh** in a standard `SpringApplication` sequence.
- `BootstrapRegistry.addCloseListener(...)` is the right phase registration for the listener; an `@EventListener` on a runtime bean arrives too late.
- Transfer objects to BeanFactory via `registerSingleton` or a bean definition when genuinely needed, understanding lifecycle differences.
- Closing bootstrap **is not** closing the application context or JVM; nor does it signal readiness.
- Bootstrap registry is for startup; runtime should use handed-off beans/abstractions.
- Objects holding sockets/threads need clear ownership, cleanup, error handling, and timeouts.
- Do not conflate core Spring Boot's `BootstrapRegistry` with Spring Cloud's bootstrap context.

## Official documentation for reference

- [Spring Boot 3.3 — BootstrapRegistry API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/BootstrapRegistry.html)
- [Spring Boot 3.3 — BootstrapContext API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/BootstrapContext.html)
- [Spring Boot 3.3 — ConfigurableBootstrapContext API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ConfigurableBootstrapContext.html)
- [Spring Boot 3.3 — DefaultBootstrapContext API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/DefaultBootstrapContext.html)
- [Spring Boot 3.3 — BootstrapContextClosedEvent API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/BootstrapContextClosedEvent.html)
- [Spring Boot 3.3 — SpringApplication API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html)
- [Spring Boot 3.3 — SpringApplication events](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Framework — Programmatically registering beans](https://docs.spring.io/spring-framework/reference/core/beans/java/programmatic-bean-registration.html)
