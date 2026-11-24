# Registering Early-Initialization Objects via BootstrapRegistryInitializer

## Learning objectives

In Spring Boot, some components must be ready **before `ApplicationContext` is created and refreshed**: for example, a client reading configuration from an external source, a configuration-data decryptor, an authenticator used when loading Config Data, or a resource shared across multiple bootstrap steps. At that stage, regular beans created by `@Component`/`@Bean` do not necessarily exist yet.

Spring Boot provides `BootstrapRegistryInitializer` and `BootstrapRegistry` to register objects serving **the early startup phase**. This lesson's goal is to understand the API, execution timing, and how to transfer an object from the bootstrap context into the application context.

After this lesson, you will be able to:

1. Distinguish `BootstrapRegistryInitializer`, `BootstrapRegistry`, `BootstrapContext`, `ApplicationContextInitializer`, and `ApplicationContext`.
2. Register early objects using `register(...)` or `registerIfAbsent(...)` with an `InstanceSupplier`.
3. Explain why **registering a supplier does not mean immediately instantiating the object**; only calling `BootstrapContext.get(...)` triggers creation when needed.
4. Use `addCloseListener(...)` to receive `BootstrapContextClosedEvent`, access `getApplicationContext()`, and bridge an early object into the Spring context in a well-designed way.
5. Register initializers programmatically or via `META-INF/spring.factories`, run a Java 17+ / Spring Boot 3.3 example, and avoid lifecycle misconceptions.

> **Version used in this article:** Spring Boot 3.3.x (demonstrated with 3.3.13), where `BootstrapRegistryInitializer`, `BootstrapRegistry`, and `BootstrapContext` reside in package `org.springframework.boot`. Do not copy imports from Spring Boot 4 documentation without checking package/API differences.

## 1. Why is this extension point needed?

A Spring Boot application typically starts like this:

~~~text
main()
   │
   ▼
SpringApplication.run(...)
   │
   ├─ Bootstrap registry / bootstrap context
   │    ├─ BootstrapRegistryInitializer registers early objects
   │    └─ Early startup steps can fetch objects when needed
   │
   ├─ Prepare Environment, process Config Data
   ├─ Create and prepare ApplicationContext
   │    └─ Close bootstrap context and invoke close listeners
   │
   ├─ Load bean definitions and refresh ApplicationContext
   │    ├─ Create non-lazy singletons, auto-configuration...
   │    └─ Complete refresh
   │
   ├─ ApplicationStartedEvent
   ├─ ApplicationRunner / CommandLineRunner
   └─ ApplicationReadyEvent
~~~

The diagram highlights **key milestones**, not every internal method. In particular, the phrase "bootstrap context closes" means **the application context preparation phase has reached its end**, **not that the application is about to shut down**.

For instance, when loading configuration from a config server, a Config Data processing component may need a custom HTTP client **before** most application beans are created. If you put that client in a regular `@Bean` and try to inject it during config data processing, initialization order does not align: application components are not ready yet.

`BootstrapRegistry` provides a temporary registry accessed by **type (`Class<?>`)**, capable of creating instances lazily on demand. It helps bootstrap steps share an object without waiting for the regular bean factory.

**Boundary:** This is an *early startup extension* mechanism, not a second full-featured DI container and not a replacement for `@Configuration` across the application.

## 2. Distinguishing the concepts

| Component | Purpose | When effective |
| --- | --- | --- |
| `BootstrapRegistryInitializer` | Callback providing `initialize(BootstrapRegistry registry)` to configure early registrations. | While SpringApplication prepares the bootstrap context, before steps needing the registry. |
| `BootstrapRegistry` | Registers suppliers by type, attaches close listeners. | During the bootstrap process. |
| `BootstrapContext` | Retrieves registered instances via `get(Class<T>)` and variants. | During bootstrap steps that have access to this context. |
| `ConfigurableBootstrapContext` | Interface combining registration and lookup permissions. | Concrete bootstrap context implementation. |
| `BootstrapContextClosedEvent` | Signals bootstrap context closure and supplies the prepared application context. | At the transition point to the application context; **before startup finishes**. |
| `ApplicationContextInitializer` | Customizes `ConfigurableApplicationContext` before refresh. | Once the application context is created but not refreshed yet. |
| `ApplicationContext` | Full Spring container managing beans and application lifecycle. | As startup progresses to context creation/refresh and throughout runtime. |

Two extension points with similar names but different roles:

~~~java
// Early bootstrap: for BootstrapRegistry.
public interface BootstrapRegistryInitializer {
    void initialize(BootstrapRegistry registry);
}

// Application context preparation: uses ConfigurableApplicationContext.
public interface ApplicationContextInitializer<C extends ConfigurableApplicationContext> {
    void initialize(C applicationContext);
}
~~~

The two declarations above are for **explaining API signatures**, not source files to add to your project. In Spring Boot 3.3, the first interface belongs to `org.springframework.boot`, while the second belongs to `org.springframework.context`.

`@PostConstruct` on a bean comes even later: it runs when that specific bean is instantiated by Spring. If you must intervene in Config Data before application beans exist, registering a bean with `@PostConstruct` is not a valid substitute.

### Bootstrap context vs. Spring Cloud bootstrap context

The names can be confusing. `BootstrapRegistry`/`BootstrapContext` here are **Spring Boot APIs** for sharing startup-phase objects. They are not synonymous with the optional **bootstrap application context** in Spring Cloud's legacy mechanisms. When reading Spring Cloud Config docs, distinguish the two concepts and actual config loading modes.

## 3. BootstrapRegistryInitializer contract

Spring Boot 3.3 defines a functional interface with one primary method:

~~~java
package org.springframework.boot;

// Condensed signature for study, not a self-written source file.
@FunctionalInterface
public interface BootstrapRegistryInitializer {
    void initialize(BootstrapRegistry registry);
}
~~~

You can implement it with a class or a lambda:

~~~java
BootstrapRegistryInitializer initializer = registry -> {
    registry.registerIfAbsent(
            StartupClient.class,
            context -> new StartupClient("local-demo"));
};
~~~

This is a **partial illustrative snippet**; `StartupClient` is a hypothetical type, and the complete example uses `EarlyClient` in section 6.

### Important APIs

| API | Meaning | Note |
| --- | --- | --- |
| `registry.register(Type.class, supplier)` | Associates a supplier with a class key. | Follows rules for replacing existing registrations; understand contention between initializers. |
| `registry.registerIfAbsent(Type.class, supplier)` | Registers only if the type has no supplier yet. | Useful for defaults that an application may supply differently. |
| `registry.isRegistered(Type.class)` | Checks whether the type is registered. | Checks registration, **does not mean the instance has been created**. |
| `registry.getRegisteredInstanceSupplier(Type.class)` | Retrieves the registered supplier, or `null`. | Must not be confused with `BootstrapContext.get(...)` for obtaining an instance. |
| `registry.addCloseListener(listener)` | Registers a listener for `BootstrapContextClosedEvent`. | Used to transfer resources once the application context is prepared. |
| `bootstrapContext.get(Type.class)` | Obtains instance by type; creates via supplier if absent. | Throws `IllegalStateException` when the type is not registered. |
| `bootstrapContext.getOrElse(...)` | Obtains instance or uses fallback. | Does not automatically register the fallback into the registry. |

`BootstrapRegistry.InstanceSupplier<T>` receives a `BootstrapContext`. This allows one supplier to fetch dependencies **already registered in the bootstrap context**:

~~~java
registry.registerIfAbsent(
        Credentials.class,
        context -> new Credentials("local-only"));

registry.registerIfAbsent(
        StartupClient.class,
        context -> new StartupClient(
                context.get(Credentials.class)));
~~~

This is an **API illustration**, requiring `Credentials` and `StartupClient` to be defined for real use. Its purpose is to clarify the `context` parameter inside the lambda: it is the bootstrap context, not a bean factory. Avoid circular dependencies and do not assume any Spring bean is available inside the bootstrap context.

### Does "early registration" mean "early instantiation"?

**Not quite.** Calling:

~~~java
registry.registerIfAbsent(
        EarlyClient.class,
        context -> new EarlyClient("from-bootstrap"));
~~~

only places the **supplier** into the registry. `EarlyClient`'s constructor has not necessarily run yet. When a bootstrap step (or close listener) calls:

~~~java
EarlyClient client = bootstrapContext.get(EarlyClient.class);
~~~

the instance is created if not yet present; the bootstrap context supports lazy access to a singleton. If you need the object to actually exist in the early phase, a valid component must **request it before that phase ends**.

Do not instantiate the object outside the supplier and pass it into the lambda if you want to optimize creation timing; for example, `EarlyClient value = new EarlyClient(...); registry.register(..., context -> value);` already constructed the object before calling `register`.

### Keyed by Class, not bean name

The bootstrap registry uses `Class` as the key, so at any given moment there is at most one registration per type in that registry. It has no `@Qualifier("primary")` or bean name rules like `BeanFactory`. When you need two clients of the same kind with different configurations, create two specialized wrapper types or design a holder containing the clients, then register that holder by type.

## 4. When is the bootstrap close listener invoked?

`registry.addCloseListener(...)` accepts a listener for `BootstrapContextClosedEvent`. This event provides:

- `getBootstrapContext()`: reference to the closing bootstrap context, allowing retrieval of registered objects.
- `getApplicationContext()`: the `ConfigurableApplicationContext` prepared by Spring Boot.

**This is not the application's `ContextClosedEvent` on JVM shutdown.** The bootstrap close listener fires during startup, right after the application context is prepared but **before refresh/runners/ready complete**.

Useful scenarios:

1. A Config Data loader already created an early client, and you need to **reuse that exact instance** when the Spring context starts.
2. A bootstrap object needs to be transferred to the container for proper lifecycle management.
3. You want to forward startup information once the bootstrap context is no longer serving the initial steps.

Note: **Closing the bootstrap context does not automatically register every object as a Spring bean**. You must write explicit handoff logic. Additionally, calling `getApplicationContext()` does not mean application beans are created yet or controllers are serving HTTP.

## 5. Two ways to register BootstrapRegistryInitializer

### Approach A: programmatic registration via SpringApplication

~~~java
SpringApplication application = new SpringApplication(DemoApplication.class);
application.addBootstrapRegistryInitializer(
        new DemoBootstrapRegistryInitializer());
application.run(args);
~~~

This is an **illustrative snippet**, assuming the two classes and imports exist. Spring Boot 3.3's `addBootstrapRegistryInitializer(...)` takes an initializer; call it **before `run`**. This approach is clear and convenient when you own `main`.

You can write a lambda if the logic is short:

~~~java
application.addBootstrapRegistryInitializer(registry ->
        registry.registerIfAbsent(
                EarlyClient.class,
                ignored -> new EarlyClient("example")));
~~~

If the initializer requires multiple steps (suppliers and close listeners), a separate class is usually easier to test and explain.

### Approach B: auto-discovery via META-INF/spring.factories

A library or application can declare the initializer class in the resource:

~~~text
src/main/resources/META-INF/spring.factories
~~~

Contents (exact key for Spring Boot 3.3):

~~~properties
org.springframework.boot.BootstrapRegistryInitializer=com.example.early.DemoBootstrapRegistryInitializer
~~~

The specified class must have the exact package name and be an implementation instantiable via Spring's factories mechanism; this example uses a no-argument constructor. When choosing **Approach B**, remove the `addBootstrapRegistryInitializer(new DemoBootstrapRegistryInitializer())` call in `main` so you do not intentionally register the same initializer twice.

**Do not place the initializer class in `AutoConfiguration.imports`:** `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` is for auto-configuration, not a replacement for the `BootstrapRegistryInitializer` key in `spring.factories`. Nor should you expect `@Component` scanning to suffice, because bean scanning happens later than when the initializer is needed.

When multiple JARs contribute `spring.factories`, Spring Boot may load multiple initializers. Do not build logic relying on arbitrary order; use `registerIfAbsent` when providing defaults and define clear policies when multiple libraries target the same type.

## 6. Runnable example: bridging an object from bootstrap to Spring context

Let us build a **console** application using Java 17+ and Spring Boot 3.3.13. The example makes no network calls or DB connections, allowing clear lifecycle observation.

Key points:

- `DemoBootstrapRegistryInitializer` registers the supplier for `EarlyClient`.
- A listener requests `EarlyClient` from the bootstrap context once the main context is prepared.
- The listener registers a **bean definition whose supplier returns the same instance** into the example's standard `GenericApplicationContext`.
- `ApplicationRunner` receives `EarlyClient` via dependency injection like a regular bean.
- `EarlyClient`'s `@PreDestroy` runs when the main context closes normally.

### 6.1. Project structure

~~~text
bootstrap-registry-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/early/
    ├── BootstrapRegistryDemoApplication.java
    ├── DemoBootstrapRegistryInitializer.java
    └── EarlyClient.java
~~~

**`settings.gradle`:**

~~~groovy
rootProject.name = 'bootstrap-registry-demo'
~~~

**`build.gradle`:**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )
    implementation 'org.springframework.boot:spring-boot-starter'
}

springBoot {
    mainClass = 'com.example.early.BootstrapRegistryDemoApplication'
}
~~~

Only `spring-boot-starter` is used, because this example needs no HTTP server. All files live in the same `com.example.early` package.

### 6.2. Object to share: EarlyClient

**`src/main/java/com/example/early/EarlyClient.java`:**

~~~java
package com.example.early;

import jakarta.annotation.PreDestroy;

public final class EarlyClient {

    private final String identity;

    public EarlyClient(String identity) {
        this.identity = identity;
        System.out.println("EARLY_CLIENT: constructed");
    }

    public String greet() {
        return "hello:" + identity;
    }

    @PreDestroy
    public void destroy() {
        System.out.println("EARLY_CLIENT: destroyed");
    }
}
~~~

`EarlyClient` is a POJO without `@Component`. The bootstrap registry will register its supplier; a listener then registers a bean definition in the main context. This lets us explain why the instance does not automatically become a bean solely through `registry.registerIfAbsent`.

The example uses a non-sensitive `identity` string. With real clients holding secrets or tokens, avoid printing confidential data to logs.

### 6.3. Initializer and close listener

**`src/main/java/com/example/early/DemoBootstrapRegistryInitializer.java`:**

~~~java
package com.example.early;

import org.springframework.boot.BootstrapRegistry;
import org.springframework.boot.BootstrapRegistryInitializer;
import org.springframework.context.support.GenericApplicationContext;

public final class DemoBootstrapRegistryInitializer
        implements BootstrapRegistryInitializer {

    @Override
    public void initialize(BootstrapRegistry registry) {

        System.out.println("BOOTSTRAP: initializer registered");

        // Register supplier. EarlyClient is not instantiated on this line yet.
        registry.registerIfAbsent(
                EarlyClient.class,
                ignored -> new EarlyClient("config-client-demo"));

        // Bridge a bootstrap instance into a Spring bean definition.
        registry.addCloseListener(event -> {
            EarlyClient client =
                    event.getBootstrapContext().get(EarlyClient.class);

            if (!(event.getApplicationContext()
                    instanceof GenericApplicationContext context)) {
                throw new IllegalStateException(
                        "Expected GenericApplicationContext in this demo");
            }

            context.registerBean(
                    "earlyClient",
                    EarlyClient.class,
                    () -> client);

            System.out.println("BOOTSTRAP: bean definition registered");
        });
    }
}
~~~

Explanation of key lines:

1. `initialize(...)` runs early and receives a `BootstrapRegistry`, **not yet** receiving the main `ApplicationContext`.
2. `registerIfAbsent(EarlyClient.class, ignored -> ...)` only registers a factory for the type; the constructor has not run yet.
3. `addCloseListener(...)` schedules a callback when the bootstrap context closes. When the callback calls `get(EarlyClient.class)`, the supplier constructs the instance if it does not exist yet.
4. `event.getApplicationContext()` provides the prepared context. Because the default non-web demo uses a `GenericApplicationContext`-based context, we can use `registerBean(...)` to register a **bean definition** whose supplier returns the bootstrap instance.
5. During refresh, Spring creates/initializes the bean via that definition. With a managed object and proper lifecycle processing, `@PreDestroy` is handled when the main context closes normally.

**Important limitation:** This handoff snippet relies on `GenericApplicationContext`'s `registerBean(...)` capability. If the application uses another context implementation, use a registration API compatible with that implementation or design the integration accordingly; do not force unchecked casts.

Do not mechanically replace `registerBean(...)` with `getBeanFactory().registerSingleton(...)`. `registerSingleton(...)` inserts an existing object into the singleton registry, but **does not execute the full standard bean definition initialization and destruction steps**. It may be useful at certain extension points, yet if you expect `@PostConstruct`, `@PreDestroy`, or all BeanPostProcessors to run automatically, choose the matching contract.

### 6.4. Application class and ApplicationRunner

**`src/main/java/com/example/early/BootstrapRegistryDemoApplication.java`:**

~~~java
package com.example.early;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class BootstrapRegistryDemoApplication {

    public static void main(String[] args) {

        SpringApplication application =
                new SpringApplication(BootstrapRegistryDemoApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);

        // Initializer must be added before run.
        application.addBootstrapRegistryInitializer(
                new DemoBootstrapRegistryInitializer());

        try (ConfigurableApplicationContext context =
                     application.run(args)) {

            System.out.println("MAIN: run returned");
        }

        System.out.println("MAIN: context closed");
    }

    @Bean
    ApplicationRunner printFromBean(EarlyClient client) {
        return args ->
                System.out.println("RUNNER: " + client.greet());
    }
}
~~~

`ApplicationRunner` is called by Spring Boot **after context refresh succeeds**. Without the listener registering the bean definition, injecting `EarlyClient` into the runner would fail because the class is neither annotated with `@Component` nor declared with another `@Bean`.

`SpringApplication` registers the initializer programmatically. Thus, **no `spring.factories` file is needed** for this section's runnable variant. `WebApplicationType.NONE` keeps the program from running an HTTP server and explicitly closes the context after the runner finishes.

### 6.5. Run command

From the `bootstrap-registry-demo` directory, run with a compatible Gradle installation:

~~~bash
gradle bootRun
~~~

If using a Gradle Wrapper, run `./gradlew bootRun` on Linux/macOS or `.\gradlew.bat bootRun` on Windows. The sample project does not include a wrapper itself; an installed Gradle or self-generated wrapper is needed.

Ignoring log/framework/build lines that may vary, **the lines printed by application code** are expected in this order:

~~~text
BOOTSTRAP: initializer registered
EARLY_CLIENT: constructed
BOOTSTRAP: bean definition registered
RUNNER: hello:config-client-demo
MAIN: run returned
EARLY_CLIENT: destroyed
MAIN: context closed
~~~

Why is this order meaningful?

- `BOOTSTRAP: initializer registered` appears when the registry is configured.
- `EARLY_CLIENT: constructed` appears **after** supplier registration, when the close listener retrieves the client.
- `BOOTSTRAP: bean definition registered` means the main context received a way to construct a bean returning the same instance.
- `RUNNER` only runs after the application context is refreshed.
- `MAIN: run returned` proves `SpringApplication.run` finished running startup runners.
- `EARLY_CLIENT: destroyed` and `MAIN: context closed` belong to **application shutdown**, much later than the bootstrap context close event.

An instance created during bootstrap and reused at runtime makes sense **only when** that resource is designed for both phases. Do not carelessly turn short-lived objects or objects holding stale bootstrap state into runtime beans.

### 6.6. Testing spring.factories mode

To test **Approach B**, add:

~~~text
src/main/resources/META-INF/spring.factories
~~~

with contents:

~~~properties
org.springframework.boot.BootstrapRegistryInitializer=com.example.early.DemoBootstrapRegistryInitializer
~~~

Then modify `main` to remove the programmatic registration lines:

~~~java
application.addBootstrapRegistryInitializer(
        new DemoBootstrapRegistryInitializer());
~~~

This is **the code snippet to remove when switching to spring.factories**, not a fourth file to execute. Re-run `gradle bootRun` and verify the initializer is still invoked via metadata. Keep **only one registration path** active for the demo so output stays predictable.

## 7. Real-world reading during the Config Data phase

In the demo, the close listener calls `get(EarlyClient.class)` to observe lazy creation. A common real-world use case is a **Config Data loader** requesting a client in the early phase, before the application context is refreshed.

Conceptual flow:

~~~text
BootstrapRegistryInitializer
    └─ registerIfAbsent(HttpClientType.class, supplier)
             │
             ▼
Config Data infrastructure
    └─ BootstrapContext.get(HttpClientType.class)
             └─ Supplier creates client for the first time if needed
             │
             ▼
Environment receives newly loaded configuration
             │
             ▼
BootstrapContextClosedEvent
    └─ Appropriate resources can be handed off to application context
             │
             ▼
ApplicationContext.refresh() → beans → runners → ready
~~~

Spring Cloud Config is one practical example of this idea: customizing an HTTP client to fetch Config Data very early. However, exact class names, integration hooks, and settings depend on the Spring Cloud version; do not bring Spring Cloud classes into a project with only Spring Boot starters unless the matching dependencies are added.

**Do not assume the initializer already has every property from `application.yml`.** Config Data may be loaded after the bootstrap registry has been built. If a supplier needs properties, determine which sources already exist at execution time and what API the caller provides. Avoid accessing a global `Environment` that is not ready yet.

## 8. Managing lifecycle and cleanup

Distinguish three easily confused milestones:

| Event | Meaning | Equivalent to app shutdown? |
| --- | --- | --- |
| `BootstrapContextClosedEvent` | Temporary bootstrap context ends; application context is prepared. | **No** |
| `ContextRefreshedEvent` | Application context finished refreshing. | **No** |
| `ContextClosedEvent` / destroy callbacks | Application context is closing and cleaning up beans. | **Yes**, on normal shutdown path |

If you create an early HTTP client, connection, or resource:

1. Determine **who owns** the client's lifecycle: bootstrap code, or the Spring bean after handoff?
2. If the resource is **used only during bootstrap**, design proper disposal once bootstrap finishes. Do not expect the bootstrap context to act like a Spring BeanFactory running `@PreDestroy` for every object.
3. If the resource is **handed off to runtime**, avoid closing it in the bootstrap close listener while application beans still use it. Ensure the runtime bean's lifecycle/cleanup callback is properly registered.
4. If startup **fails partway through**, do not assume every "success" callback is guaranteed to run. Self-opened resources must have error-path cleanup/idempotency.
5. For real clients, configure timeouts, retry limits, secret protection, and avoid unbounded network operations inside initializers. Early startup is highly sensitive to deadlocks and whole-application latency.

The study example bridges `EarlyClient` into a bean definition so `@PreDestroy` runs when the context closes cleanly. Using a custom-constructed object via a bean definition supplier should be tested for compatibility with real-system BeanPostProcessors, especially when beans need proxies/AOP or complex lifecycles.

## 9. Register, registerIfAbsent, and handling conflicts

### registerIfAbsent: supplying defaults

~~~java
registry.registerIfAbsent(
        EarlyClient.class,
        ignored -> new EarlyClient("default"));
~~~

If a supplier already exists for `EarlyClient.class`, this call preserves the existing registration. Suitable when a library wants to offer a **fallback** to the application.

### register: explicit registration

~~~java
registry.register(
        EarlyClient.class,
        ignored -> new EarlyClient("explicit"));
~~~

Per the Spring Boot 3.3 Javadoc, an existing registration can be replaced when the corresponding instance **has not yet been retrieved as a singleton**. Do not build designs assuming "overwriting always wins"; once the instance is created, different rules apply, and the sequence of multiple initializers can affect the outcome.

### Checking before get

~~~java
if (bootstrapContext.isRegistered(EarlyClient.class)) {
    EarlyClient client = bootstrapContext.get(EarlyClient.class);
    // Use instance in the current bootstrap step.
}
~~~

This is a **partial illustrative snippet**, assuming you are inside a callback that actually receives `BootstrapContext`. Do not call `get` for an unregistered type as an existence check, because the API throws an error.

When multiple modules or libraries share the registry, define type ownership and instance semantics to prevent two independent components from claiming the same `Class` key while expecting different configurations.

## 10. Common mistakes

**Mistake 1 — Annotating the initializer with @Component and expecting early auto-scan**

~~~java
@Component
public class DemoBootstrapRegistryInitializer
        implements BootstrapRegistryInitializer {
    // ...
}
~~~

The snippet above only depicts a **design mistake**, not a recommended approach. Component scanning happens during application context startup, whereas bootstrap initializers must be known **before that**. Register via `addBootstrapRegistryInitializer` or `META-INF/spring.factories`.

**Mistake 2 — Confusing SpringApplication.addInitializers with addBootstrapRegistryInitializer**

~~~java
application.addInitializers(context -> {
    // context is ConfigurableApplicationContext, not BootstrapRegistry.
});
~~~

`ApplicationContextInitializer` does not receive `BootstrapRegistry` and does not replace `BootstrapRegistryInitializer`. Choose the right API by timing and callback parameter.

**Mistake 3 — Assuming register creates the object immediately**

~~~java
registry.registerIfAbsent(
        EarlyClient.class,
        context -> new EarlyClient("demo"));
~~~

This only adds a supplier; for the instance to exist early, a component must call `BootstrapContext.get(EarlyClient.class)` when appropriate. Wrapping client construction in a supplier avoids cost when nobody needs it.

**Mistake 4 — Retrieving @Autowired beans from the bootstrap registry**

`BootstrapRegistry` is not `ApplicationContext` and does not perform component scanning, bean injection, `@Qualifier`, or bean post-processing like Spring's BeanFactory. If you want to access a type, it must be registered via bootstrap APIs; do not assume application beans exist.

**Mistake 5 — Treating application context as already refreshed inside close listener**

The bootstrap close event provides a **prepared application context**, but does not guarantee application `@Bean`s have been instantiated. In the example, the listener registers a bean definition for the context to process at refresh, rather than invoking controllers/services via `getBean(...)` before the right milestone.

**Mistake 6 — Confusing bootstrap close with shutdown**

Do not close a client needed at runtime inside `BootstrapContextClosedEvent`. Closing at the wrong moment can hand beans an already-disposed resource.

**Mistake 7 — Using registerSingleton and assuming @PreDestroy definitely runs**

`registerSingleton` does not replace creating/initializing beans via definitions with BeanPostProcessors. If normal lifecycle handling is needed, consider `GenericApplicationContext.registerBean` or a supported bean definition registration mechanism. Always verify actual resource disposal.

**Mistake 8 — Uncontrolled overwriting of type keys**

Registry keys are `Class` objects with no qualifiers. `register(...)` differs from `registerIfAbsent(...)`, and collisions can make outcomes depend on registration order. Establish clear contracts when multiple libraries integrate.

**Mistake 9 — Reading secrets and logging them during bootstrap**

Early configuration may contain sensitive data. Never log tokens, passwords, URLs with secret queries, auth configurations, or exceptions containing headers. Use minimal logging/diagnostics and protect data across every startup stage.

**Mistake 10 — Thinking spring.factories was replaced by AutoConfiguration.imports for all extensions**

Auto-configuration migration does not mean Spring Boot 3.3 dropped `spring.factories` for `BootstrapRegistryInitializer`. Use the hook's exact key per version docs instead of swapping the two mechanisms.

## 11. Practice exercises

1. Run the section 6 project and inspect the order of `BOOTSTRAP`, `EARLY_CLIENT`, `RUNNER`, and `MAIN`. Why does the constructor run after the `registerIfAbsent` call?
2. Move `event.getBootstrapContext().get(EarlyClient.class)` out of the listener and keep only supplier registration. Will an `EarlyClient` instance still be created for the Runner to inject? Identify which bridging step is missing.
3. Replace programmatic registration with `spring.factories` as instructed. Verify the initializer runs once and produces equivalent output.
4. Try calling `registry.registerIfAbsent` twice for the same `EarlyClient.class` with two different values; explain which supplier is kept before anyone retrieves the instance.
5. Add a `BootstrapOptions` type and register `EarlyClient`'s supplier using `context.get(BootstrapOptions.class)`. How is this similar to and different from application bean dependency injection?
6. Try removing the `registerBean(...)` logic inside the close listener. Why does `ApplicationRunner` ask for `EarlyClient` yet the context cannot autowire that type?
7. If a bootstrap client must continue to be used after startup, how will you ensure shutdown/cleanup, timeouts, and ownership?
8. Why can calling `application.addBootstrapRegistryInitializer(...)` **after** `run(args)` not retroactively trigger already-passed bootstrap steps?
9. Explain why you cannot use `@PostConstruct` on an application bean to customize Config Data loading before the context exists.
10. Two libraries in a system both want to register an HTTP client under the same class key. How would you handle type ownership or fallbacks to avoid accidental behavior?

## Takeaways

- `BootstrapRegistryInitializer` is an **ultra-early** callback receiving `BootstrapRegistry` before normal application beans are ready.
- `register` and `registerIfAbsent` take **suppliers keyed by Class**; registration does not necessarily instantiate the object immediately, while `BootstrapContext.get` creates/fetches the singleton when needed.
- `BootstrapContextClosedEvent` occurs **during startup**, once the application context has been prepared; it **differs from** `ContextClosedEvent` during application shutdown.
- Bootstrap objects **do not automatically become Spring beans**. An explicit bridge is required, along with proper ownership and lifecycle handling.
- There are two common ways to register initializers in Spring Boot 3.3: `SpringApplication.addBootstrapRegistryInitializer(...)` and `META-INF/spring.factories` with key `org.springframework.boot.BootstrapRegistryInitializer`.
- Only use this extension point when genuinely needed in the early phase. For business logic running after startup, `@Bean`, `ApplicationRunner`, `ApplicationReadyEvent`, or bean lifecycle hooks are usually more appropriate.

### References

- Spring Boot 3.3.13 — BootstrapRegistryInitializer: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/BootstrapRegistryInitializer.html
- Spring Boot 3.3.13 — BootstrapRegistry: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/BootstrapRegistry.html
- Spring Boot 3.3.13 — BootstrapContext: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/BootstrapContext.html
- Spring Boot 3.3.13 — BootstrapContextClosedEvent: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/BootstrapContextClosedEvent.html
- Spring Boot 3.3.13 — SpringApplication: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Cloud Config — Customizing a BootstrapRegistryInitializer for Config Data: https://docs.spring.io/spring-cloud-config/reference/client.html
