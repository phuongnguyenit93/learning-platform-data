# BootstrapRegistry and ConfigurableBootstrapContext Before Beans Exist

## 1. Why does Spring Boot need a bootstrap context?

In a Spring Boot application, some tasks must be performed **before `ApplicationContext` is created and regular beans are instantiated**. For example: loading configuration from an external service, building a client to access a secrets store to read configuration properties, or sharing an expensive object during the `Environment` preparation phase.

At this very early moment, code **cannot rely on `@Autowired`, `@Bean`, `ApplicationContext.getBean()`, or a refreshed `BeanFactory`** to retrieve objects. Spring Boot provides a dedicated mechanism:

- **`BootstrapRegistry`**: where objects or object suppliers are *registered* under a `Class<T>` key.
- **`BootstrapContext`**: where registered objects are *retrieved* when needed, typically instantiated lazily via an `InstanceSupplier<T>`.
- **`ConfigurableBootstrapContext`**: an interface combining both roles (`extends BootstrapRegistry, BootstrapContext`), allowing both reading and registration during the bootstrap phase.
- **`BootstrapRegistryInitializer`**: a callback used to declare registrations very early, before the bootstrap registry is consumed.
- **`DefaultBootstrapContext`**: Spring Boot's default implementation of `ConfigurableBootstrapContext`.

The primary goal is **controlled sharing of startup dependencies before regular Spring beans exist**. This registry does not replace the IoC container, does not perform component scanning, does not manage `@Autowired`, and does not automatically turn an object into a bean when the main context appears.

### Practical scenario

Suppose a system needs to read runtime configuration from a dedicated configuration service. The process requires a `ConfigurationClient` before `ApplicationContext` exists. If multiple bootstrap-phase components need the same client, repeatedly calling `new ConfigurationClient(...)` can open resources multiple times and scatter state. The bootstrap registry lets you register a supplier by type and then share the instance when someone calls `get()`.

Point to remember: **the bootstrap context exists during the application preparation phase, whereas ApplicationContext manages the lifecycle of application beans**. The two mechanisms have different timing and scope.

## 2. Position in the SpringApplication startup sequence

General sequence of `SpringApplication.run(...)` in Spring Boot 3.3:

~~~text
main()
  |
  v
Create SpringApplication and configure bootstrap registry initializers
  |
  v
Create ConfigurableBootstrapContext (typically DefaultBootstrapContext)
  |
  +-- Invoke BootstrapRegistryInitializer.initialize(registry)
  |     +-- register / registerIfAbsent InstanceSuppliers
  |
  +-- Publish early startup events
  +-- Prepare Environment and apply Config Data
  |     +-- Components permitted to access bootstrap context
  |     +-- get(Type.class) may invoke supplier for the first time
  |
  +-- Create ApplicationContext and prepare Environment
  +-- Apply ApplicationContextInitializers
  +-- Close bootstrap context, publish BootstrapContextClosedEvent
  |     +-- Can hand off needed objects to BeanFactory
  |
  +-- Load configuration/bean definitions, refresh ApplicationContext
  |     +-- Process BeanFactoryPostProcessors / BeanPostProcessors
  |     +-- Instantiate regular beans and dependencies
  |
  +-- ApplicationStartedEvent, invoke runners
  +-- ApplicationReadyEvent
  v
Application is ready if startup succeeds
~~~

This is a **simplified logical diagram**; exact ordering among certain event callbacks, `EnvironmentPostProcessor`, `ConfigData`, and definition loading may include additional steps. The most important milestone is that the bootstrap registry is created **before `ApplicationContext` is prepared and refreshed**. The bootstrap context close event occurs once `ApplicationContext` has been prepared, which **does not mean the context has refreshed or the application is ready**.

Per the Spring Boot API, `ApplicationEnvironmentPreparedEvent` gives access to `ConfigurableBootstrapContext` via `getBootstrapContext()` during environment preparation. Built-in config-data components also use this mechanism for startup dependencies.

Do not confuse it with these milestones:

| Milestone | What already exists? | Must not assume |
| --- | --- | --- |
| `BootstrapRegistryInitializer.initialize()` | Registry to register types and suppliers | Business beans exist or an `ApplicationContext` is running |
| `Environment` preparation / `ApplicationEnvironmentPreparedEvent` | `Environment` and bootstrap context | `@Bean` created, `@Autowired` usable |
| `BootstrapContextClosedEvent` | `ApplicationContext` has been *prepared* | `ApplicationContext` refreshed, runners executed |
| `ApplicationStartedEvent` | Context refreshed | Runners completed |
| `ApplicationReadyEvent` | Runners executed successfully per Boot lifecycle | All asynchronous business tasks finished |

Registering BPPs inside `ApplicationContext.refresh()` happens later than the bootstrap registry phase. Therefore, do not mix up **bootstrap registry** with **BeanFactory registry** or `BeanPostProcessor`.

## 3. Relationships among the interfaces

The related interfaces can be pictured as follows:

~~~text
       BootstrapRegistry          BootstrapContext
       -----------------          ----------------
       register(...)              get(...)
       registerIfAbsent(...)      getOrElse(...)
       isRegistered(...)          getOrElseSupply(...)
       addCloseListener(...)      getOrElseThrow(...)
                   \              /
                    \            /
               ConfigurableBootstrapContext
                         ^
                         |
                 DefaultBootstrapContext
~~~

Here:

- `BootstrapRegistry` is the API for **the registering side**.
- `BootstrapContext` is the API for **the consuming side** of what was registered.
- `ConfigurableBootstrapContext` includes both method sets. You do not have to pass the combined interface to every component; choose the narrowest parameter type reflecting the actual responsibility.

### 3.1. Registration by type, not bean name

Example:

~~~java
registry.registerIfAbsent(
    EarlyClient.class,
    context -> new EarlyClient("dev")
);
~~~

This is an **illustrative snippet inside a `BootstrapRegistryInitializer`**, not a standalone program. `EarlyClient` represents a user-written class.

The registry uses **`Class<T>` as the key**. For the same `EarlyClient.class` key, a registry holds **one registration at a time**. Unlike Spring's BeanFactory, it does not provide an IoC-style mechanism to distinguish multiple beans of the same type using bean names and `@Qualifier`.

If you need two clients of the same Java type with different configurations, use two distinct wrapper/marker types or design a holder managing the collection of clients; do not treat the registry as a map keyed by bean name.

### 3.2. register and registerIfAbsent

- `register(type, supplier)`: registers or replaces the supplier if the existing registration still allows replacement. Once a singleton has been accessed/instantiated, replacing the registration is restricted by contract; do not treat `register` as an arbitrary object overwrite.
- `registerIfAbsent(type, supplier)`: registers only if the type does not already have a registration. This is the right choice when a library wants to supply a **default that an application or another integration can override beforehand**.
- `isRegistered(type)`: checks whether the type is registered; **does not prove the supplier was invoked or the instance is non-null**.
- `getRegisteredInstanceSupplier(type)`: inspects the registered supplier, returning null if absent; usually only needed by integrations wanting to customize a registration.

Remember to distinguish registration from instantiation:

~~~text
register(EarlyClient.class, supplier) -> stores creation recipe
get(EarlyClient.class)               -> retrieves (may trigger first creation)
get(EarlyClient.class) again         -> reuses if SINGLETON
~~~

### 3.3. Lazy creation and scope

`BootstrapRegistry.InstanceSupplier<T>` is a functional interface. The method `T get(BootstrapContext context)` receives the bootstrap context, so a supplier can read other bootstrap objects if already registered and free of circular dependencies.

Two scopes are defined:

| Scope | Meaning |
| --- | --- |
| `BootstrapRegistry.Scope.SINGLETON` | Supplier is called at most once for the instance; subsequent `get` calls reuse the same instance |
| `BootstrapRegistry.Scope.PROTOTYPE` | Supplier is called every time a new instance is requested |

The `InstanceSupplier.withScope(...)` API lets you specify scope, for example:

~~~java
registry.register(
    EarlyClient.class,
    (BootstrapRegistry.InstanceSupplier<EarlyClient>)
        context -> new EarlyClient("demo")
);
~~~

This registration illustrates the generic lambda; **no cast is needed when the compiler infers the type from `register`'s parameter**. In normal code, you can write `context -> new EarlyClient("demo")` directly. When you genuinely need to change scope, use an appropriately typed supplier and call `.withScope(BootstrapRegistry.Scope.PROTOTYPE)`.

Do not pick `PROTOTYPE` merely to "avoid managing lifecycle": each creation can allocate new resources, and closing them remains the responsibility of the corresponding code.

## 4. Reading data from the bootstrap context

A consumer can call:

~~~java
BootstrapContext bootstrap = event.getBootstrapContext();
EarlyClient client = bootstrap.get(EarlyClient.class);
~~~

The example above is an **illustrative snippet inside an `ApplicationEnvironmentPreparedEvent` listener**, not a standalone Java file. In Spring Boot 3.3, `getBootstrapContext()` returns `ConfigurableBootstrapContext`, which is a subtype of `BootstrapContext`.

Common methods:

| Method | When to use |
| --- | --- |
| `get(Foo.class)` | Type must be registered; may trigger instance creation |
| `getOrElse(Foo.class, fallback)` | If the type is not registered, return an existing fallback value |
| `getOrElseSupply(Foo.class, supplier)` | If not registered, invoke the fallback supplier |
| `getOrElseThrow(Foo.class, exceptionSupplier)` | If not registered, throw an exception per application policy |
| `isRegistered(Foo.class)` | Check whether a registration exists before accessing |

Per the Javadoc, `get` can throw `IllegalStateException` if the type is not registered. **A valid registration can still supply null**, so do not assume `isRegistered` means "a non-null, connected, ready object exists".

`getOrElse(...)` does not turn the fallback value into an official registration unless you actively register it; distinguish lookup from registry configuration.

## 5. Complete Java 17+ example (Spring Boot 3.3.x)

This example directly demonstrates four mechanisms:

1. `BootstrapRegistryInitializer` registers a supplier before Spring creates beans.
2. `ApplicationEnvironmentPreparedEvent` accesses `ConfigurableBootstrapContext` and triggers the supplier for the first time.
3. `BootstrapContextClosedEvent` provides the hook to hand off the instance to the prepared BeanFactory.
4. `ApplicationRunner` receives the handed-off instance via constructor/method dependency injection after context refresh.

To keep milestones easy to observe, the example uses `WebApplicationType.NONE`, starts no HTTP server, and needs no database.

### 5.1. Project structure

Use Maven and Java 17+. Create these exact two files:

~~~text
bootstrap-registry-demo/
├─ pom.xml
└─ src/
   └─ main/
      └─ java/
         └─ com/example/bootstrapdemo/
            └─ BootstrapDemoApplication.java
~~~

**File `pom.xml`:**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>bootstrap-registry-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
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

The example pins Spring Boot **3.3.13** so imports stay consistent; Maven and JDK 17+ must be configured properly. If using a different patch version in the same release line, verify corresponding dependencies before changing the version number.

### 5.2. Complete Java program

**File `src/main/java/com/example/bootstrapdemo/BootstrapDemoApplication.java`:**

~~~java
package com.example.bootstrapdemo;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class BootstrapDemoApplication {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(
                BootstrapDemoApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        // (1) Register before ApplicationContext/beans are initialized.
        app.addBootstrapRegistryInitializer(registry -> {
            System.out.println("01_REGISTER_SUPPLIER");

            registry.registerIfAbsent(
                    EarlyToken.class,
                    bootstrapContext -> {
                        System.out.println("03_CREATE_EARLY_TOKEN");
                        return new EarlyToken("demo-key");
                    }
            );

            // (3) When the bootstrap context closes, the main context has
            // been prepared; hand off the instance to BeanFactory.
            registry.addCloseListener(event -> {
                EarlyToken token = event.getBootstrapContext()
                        .get(EarlyToken.class);

                event.getApplicationContext()
                        .getBeanFactory()
                        .registerSingleton("earlyToken", token);

                System.out.println("05_BRIDGED_TO_BEAN_FACTORY");
            });
        });

        // (2) Listener declared before run, because this event
        // occurs before regular beans exist.
        app.addListeners(
                (ApplicationListener<ApplicationEnvironmentPreparedEvent>)
                        event -> {
                            System.out.println("02_ENVIRONMENT_READY");

                            EarlyToken token = event
                                    .getBootstrapContext()
                                    .get(EarlyToken.class);

                            System.out.println(
                                    "04_BOOTSTRAP_READ=" + token.value());
                        }
        );

        app.run(args);
    }

    // (4) Only during the normal context/runner phase does
    // Spring inject the instance registered into BeanFactory.
    @Bean
    ApplicationRunner printResult(EarlyToken token) {
        return args -> System.out.println(
                "06_RUNNER_BEAN=" + token.value());
    }

    public record EarlyToken(String value) {
    }
}
~~~

The imports above belong to Spring Boot 3.3: `SpringApplication`, `WebApplicationType`, and `ApplicationRunner` in `org.springframework.boot`; events in `org.springframework.boot.context.event`; listeners and `@Bean` in Spring Framework.

**Key highlights of the program:**

- `registerIfAbsent(EarlyToken.class, ...)` only stores the supplier, so it does not print `03_CREATE_EARLY_TOKEN` right at registration.
- `ApplicationEnvironmentPreparedEvent` arrives while `Environment` exists and `ApplicationContext` is not created yet. The listener retrieves `ConfigurableBootstrapContext`, and then `get(EarlyToken.class)` triggers the supplier.
- When the close listener calls `get(EarlyToken.class)` again, the already-created singleton instance is reused. There is no second `03_CREATE_EARLY_TOKEN` line.
- `registerSingleton("earlyToken", token)` places the instance into the main BeanFactory's singleton registry. After refresh, `@Bean printResult(EarlyToken token)` can receive that instance via dependency injection.
- Because `WebApplicationType.NONE` is set, the program exits after the runner finishes, with no HTTP server keeping the process alive.

### 5.3. Running the program

From the directory containing `pom.xml`:

~~~bash
# Requires Maven installed and Java 17+ on PATH
mvn spring-boot:run
~~~

Or package as a JAR and run:

~~~bash
mvn package
java -jar target/bootstrap-registry-demo-0.0.1-SNAPSHOT.jar
~~~

In the output, **the six lines printed by the example code** appear in this order (Spring Boot/Maven logs may interleave depending on environment):

~~~text
01_REGISTER_SUPPLIER
02_ENVIRONMENT_READY
03_CREATE_EARLY_TOKEN
04_BOOTSTRAP_READ=demo-key
05_BRIDGED_TO_BEAN_FACTORY
06_RUNNER_BEAN=demo-key
~~~

If using a tool that created the project via Spring Initializr, Maven Wrapper may be provided; in that case run `./mvnw spring-boot:run` (Linux/macOS) or `.\mvnw.cmd spring-boot:run` (PowerShell).

### 5.4. Why does the output prove the bootstrap boundary?

`01_REGISTER_SUPPLIER` and `02_ENVIRONMENT_READY` happen before the `printResult` bean is created. The supplier only constructs the instance at `03_CREATE_EARLY_TOKEN`, and the listener reads the instance at `04_BOOTSTRAP_READ`. When the bootstrap context closes, the `05_BRIDGED_TO_BEAN_FACTORY` callback runs once the application context is prepared. Finally, `06_RUNNER_BEAN` shows **a regular bean/runner can now consume the exact same instance**.

This example demonstrates **explicit handoff**. There is no "auto-convert all registrations into beans" behavior: if you delete `registerSingleton(...)` while still asking to inject `EarlyToken`, the context will fail to create the runner due to a missing matching bean.

### 5.5. Notes on registerSingleton and lifecycle

`registerSingleton(...)` registers **an already-created instance** without going through the full standard bean creation pipeline like registering a `BeanDefinition` and letting Spring build the object. Therefore **do not assume an instance handed over this way will automatically receive full constructor injection, `@PostConstruct`, bean post-processing, or destroy callbacks like a factory-created bean**.

In the example, `EarlyToken` is just an immutable record without lifecycle hooks, so this simple handoff fits. For real resources like HTTP clients, connection pools, or closeable objects, design ownership and cleanup lifecycle explicitly. If the object needs the full Spring bean processing chain, consider registering a bean definition/factory via the proper ApplicationContext extension point instead of inserting a pre-built singleton arbitrarily.

## 6. Ways to register BootstrapRegistryInitializer

### 6.1. Registering via SpringApplication

This is the clearest approach for an application that controls `main()`:

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.addBootstrapRegistryInitializer(registry -> {
    registry.registerIfAbsent(
            MyEarlyDependency.class,
            context -> new MyEarlyDependency()
    );
});
app.run(args);
~~~

The snippet above **only illustrates the idea** and is not standalone: `MyApplication` and `MyEarlyDependency` are hypothetical classes, and `SpringApplication` must be imported. `SpringApplicationBuilder` also offers `addBootstrapRegistryInitializer(...)` to do the same with builder syntax.

### 6.2. Library-packaged integration

An early-support library can provide an implementation class:

~~~java
public final class MyBootstrapInitializer
        implements BootstrapRegistryInitializer {

    @Override
    public void initialize(BootstrapRegistry registry) {
        registry.registerIfAbsent(
                MyEarlyDependency.class,
                context -> new MyEarlyDependency()
        );
    }
}
~~~

This is **incomplete illustrative code**, missing imports and the `MyEarlyDependency` definition. In Spring Boot 3.3, `BootstrapRegistryInitializer` and `BootstrapRegistry` belong to `org.springframework.boot`.

To be discovered via `SpringFactoriesLoader`, a library can declare the implementation class in `META-INF/spring.factories` under the matching Spring Boot 3 key:

~~~properties
org.springframework.boot.BootstrapRegistryInitializer=com.example.bootstrap.MyBootstrapInitializer
~~~

The path and class name must match the actual package; the class needs an appropriate constructor to be loaded. In an application that already added the initializer directly via `SpringApplication`, do not add a duplicate registration in `spring.factories`. In environments with multiple auto-configurations, avoid relying on an implicit ordering among initializers that is not explicitly defined.

**Do not confuse** `spring.factories` for a specialized SPI with the `AutoConfiguration.imports` list used by standard auto-configuration: they participate in **different phases** of startup.

## 7. When is ConfigurableBootstrapContext useful?

Because `ConfigurableBootstrapContext` is both a registry and a context, it fits when bootstrap-phase code must decide on additional registrations based on the environment.

For example, an `ApplicationEnvironmentPreparedEvent` listener can inspect properties:

~~~java
app.addListeners(
    (ApplicationListener<ApplicationEnvironmentPreparedEvent>) event -> {
        ConfigurableBootstrapContext bootstrap =
                event.getBootstrapContext();

        if (!bootstrap.isRegistered(MyEarlyDependency.class)) {
            bootstrap.register(
                    MyEarlyDependency.class,
                    context -> new MyEarlyDependency());
        }

        MyEarlyDependency value = bootstrap.get(
                MyEarlyDependency.class);
        // Use value for Environment preparation work
    }
);
~~~

This is an **illustrative snippet**, not a standalone program; `MyEarlyDependency`, `app`, and imports are assumed to exist. In Spring Boot 3.3, `ConfigurableBootstrapContext` lives in `org.springframework.boot`.

In most cases, **pre-registering via `BootstrapRegistryInitializer` is still clearer** because it establishes dependency suppliers before starting `Environment` processing. Only add registrations inside a listener when you truly need a decision based on information available at that phase.

### Reading or modifying Environment

`ConfigurableBootstrapContext` itself **is not a container for `PropertySources`**. To read or modify properties, use the event's `ConfigurableEnvironment` or an appropriate `EnvironmentPostProcessor` API. The bootstrap context only holds helper objects needed for that process.

For example: the bootstrap registry holds a `SecretsClient`, while the query results are used to build a `PropertySource` added to `Environment`. You should not stuff every configuration property into type-keyed registrations, because the registry has no property precedence contract like `PropertySources`.

## 8. How to hand off objects to ApplicationContext?

There is no rule that "every bootstrap object becomes a Spring bean". Integrations must explicitly choose a handoff strategy based on need:

1. **Used only during bootstrap:** do not register in BeanFactory; the object supports configuration loading and undergoes appropriate lifecycle cleanup before/after bootstrap finishes.
2. **Reused as a bean:** `BootstrapContextClosedEvent` provides access to the prepared main context; you can register a created singleton as shown with `registerSingleton`, if compatible with the object's lifecycle.
3. **Recreated at runtime:** if the bootstrap client holds sensitive credentials or temporary logic, runtime can build its own bean from loaded configuration instead of reusing the bootstrap instance.
4. **Actually needs Spring init/destroy hooks:** design bean definition or factory registration in the appropriate phase, ensuring names, scopes, and lifecycle are handled as expected.

**Common risk:** keeping an instance with unclear ownership so that both bootstrap and ApplicationContext try to close it, or both assume the other will close it. Pick one owner responsible for closing; avoid closing an object while another bean still uses it.

### BootstrapContextClosedEvent is not ApplicationReadyEvent

`BootstrapContextClosedEvent` signals that the bootstrap context phase ended once the main context was prepared. It is **not a sign that the application started successfully**, nor is it equivalent to Spring's `ContextClosedEvent` on application shutdown. If you need to know when runtime has refreshed or is ready for requests, use `ApplicationStartedEvent`/`ApplicationReadyEvent` for their intended purpose.

## 9. Distinguishing bootstrap registry from easily confused concepts

| Concept | When does it exist? | What does it hold? | What is it for? |
| --- | --- | --- | --- |
| `BootstrapRegistry` | Very early, before main context | Type → supplier | Declaring startup dependencies |
| `BootstrapContext` | Very early, during Environment preparation | Lazy instances by type | Reading registered dependencies |
| `ConfigurableBootstrapContext` | Bootstrap phase | Both registration and lookup | Integrations needing both reading and configuring |
| `ApplicationContext` | Once created by Spring and later refreshed | Bean definitions, instances, dependency graph | Managing all application beans |
| `BeanFactoryPostProcessor` | During refresh, before most beans | Bean definition metadata | Modifying bean metadata/factory |
| `BeanPostProcessor` | During bean creation | Bean instances before/after init | Processing beans/proxies/lifecycle |
| `ApplicationContextInitializer` | Context created, not refreshed yet | ConfigurableApplicationContext | Customizing context before refresh |
| Spring Cloud bootstrap context | Depends on Spring Cloud module and integration | May be a separate ApplicationContext | Spring Cloud's configuration bootstrap mechanism |

Specifically, **Spring Boot's `BootstrapRegistry` is not synonymous with Spring Cloud's bootstrap ApplicationContext**. Spring Cloud has its own configuration mechanisms and history; sharing the word "bootstrap" does not mean sharing the same types, lifecycle, or purpose.

`BootstrapRegistry` is also **not a JNDI registry, service registry (Eureka/Consul), or global bean registry**. It is solely an internal mechanism for the application startup phase.

## 10. Common mistakes and how to handle them

| Symptom / mistake | Common cause | Resolution |
| --- | --- | --- |
| `get(Foo.class)` throws `IllegalStateException` | Type not registered | Register early enough in an initializer, or use `getOrElse...` per contract |
| `get` returns null even though `isRegistered` is true | Supplier may provide null | Check supplier and data conditions; do not use `isRegistered` as a health check |
| Creating the client immediately in the initializer | Confusing registration with eager creation | Put creation logic inside `InstanceSupplier` for lazy initialization |
| Injecting `@Autowired Foo` in bootstrap initializer | Spring has not created regular IoC beans yet | Use registry/context parameters and non-bean dependencies |
| Registering multiple instances of the same type | Registry uses `Class<T>` as key | Separate wrapper types or design a holder managing variants |
| Calling `register()` again after singleton was created | Replacement is restricted, state is already shared | Finalize registrations before consumption; use `registerIfAbsent` for defaults |
| Code expects to use object as a bean but injection fails | Missing handoff step to ApplicationContext | Explicitly register a bean before refresh or create a separate runtime bean |
| Object added with `registerSingleton` lacks init callbacks | Instance was created outside Spring's full lifecycle | Pick a bean definition/factory mechanism if full init/destroy is required |
| Closing bootstrap client too early | Client is still used by runtime | Define ownership and resource release timing |
| Using Boot 4 APIs with Boot 3 imports | Bootstrap API package changed | Check actual version, update imports per compatibility table |
| Calling bean lookup in `ApplicationEnvironmentPreparedEvent` | Context has not been created yet | Use `event.getBootstrapContext()`; do not rely on `getBean()` yet |
| Equating `BootstrapContextClosedEvent` with app shutdown | The two events carry different meanings | Track the proper event for each respective phase |

### Design limits to understand

**Do not open too many resources during bootstrap.** This lies on the critical startup path; long network timeouts or hanging dependencies can delay startup. Deliberately configure retries, timeouts, fallbacks, and failure policies when integrating external systems.

**Avoid circular dependencies among bootstrap suppliers.** If `Supplier<A>` calls `context.get(B.class)` while `Supplier<B>` calls `context.get(A.class)`, initialization risks infinite recursion or invalid state. Design dependencies unidirectionally and keep structures simple.

**Do not guess thread-safety.** If multiple components access a resource concurrently, the resource itself and its integration must satisfy concurrency requirements. A singleton is not automatically thread-safe.

**Mind information security.** Bootstrap often involves tokens, credentials, or internal endpoints. Never print secret keys in logs, never transfer sensitive data casually into public beans, and avoid letting exceptions leak secrets. The `demo-key` string in the example is purely dummy data.

**Do not confuse caches managed by the bootstrap context with bean singletons.** Singletons in the type-keyed registry and singletons in BeanFactory by bean name/type are two separate systems. They only share an instance when an integration performs an explicit handoff.

**Do not misuse the registry as a service locator for business code.** Once `ApplicationContext` is active, prefer standard dependency injection so the system remains testable, observable, and lifecycle-managed.

## 11. Compatibility across Spring Boot 2.4 → 3.5 → 4.x

Bootstrap registry APIs appeared starting in the Spring Boot 2.4 line; `SpringApplication.addBootstrapRegistryInitializer(...)` arrived in 2.4.5. However, **package paths changed in Spring Boot 4.x**.

| API | Spring Boot 3.3 | Spring Boot 4.x |
| --- | --- | --- |
| `BootstrapRegistry` | `org.springframework.boot.BootstrapRegistry` | `org.springframework.boot.bootstrap.BootstrapRegistry` |
| `BootstrapContext` | `org.springframework.boot.BootstrapContext` | `org.springframework.boot.bootstrap.BootstrapContext` |
| `ConfigurableBootstrapContext` | `org.springframework.boot.ConfigurableBootstrapContext` | `org.springframework.boot.bootstrap.ConfigurableBootstrapContext` |
| `BootstrapRegistryInitializer` | `org.springframework.boot.BootstrapRegistryInitializer` | `org.springframework.boot.bootstrap.BootstrapRegistryInitializer` |
| `BootstrapContextClosedEvent` | `org.springframework.boot.BootstrapContextClosedEvent` | `org.springframework.boot.bootstrap.BootstrapContextClosedEvent` |

`SpringApplication` remains the entry point in `org.springframework.boot` across the versions discussed. When upgrading Boot major versions, update imports and **update SPI key names in `spring.factories` if used**; do not only edit Java classes.

Do not copy a Boot 4 example into a Boot 3 project and conclude "bootstrap registry was removed" merely because the Java compiler cannot find the package. Always check the Javadoc matching your project's dependency version.

## 12. Practice exercises and self-check

**Exercise 1 — Proving lazy supplier.** Run the section 5 example, then temporarily remove the `get(EarlyToken.class)` call from the `ApplicationEnvironmentPreparedEvent` listener while keeping the close listener. Observe how `03_CREATE_EARLY_TOKEN` shifts to the bootstrap-context close phase. Explain why the registry held a registration earlier without having created the instance yet.

**Exercise 2 — Removing bean handoff.** Temporarily remove `registerSingleton("earlyToken", token)` while keeping `@Bean ApplicationRunner printResult(EarlyToken token)`. Predict the injection error and explain why a type in the bootstrap registry does not automatically become a bean. This is an experimental change; restore the code afterward.

**Exercise 3 — Changing registration policy.** Write two initializers both supplying `EarlyToken.class` and using `registerIfAbsent`. Observe which initializer establishes the registration before `get`. Why shouldn't business logic depend on unspecified ordering? Propose a transparent configuration when overrides are needed.

**Exercise 4 — Evaluating lifecycle.** Replace the simple record with an `AutoCloseable` object simulating a connection; determine who owns closing after bootstrap completes, especially when the same instance is handed off as a bean. Do not close twice or leak the resource.

**Question 1:** Why can't every bootstrap dependency be solved with `@Autowired`?

**Answer:** `@Autowired` requires Spring's bean/container mechanism; during `Environment` preparation, the main context has not been created/refreshed yet. The bootstrap registry can supply early objects independently of the normal bean lifecycle.

**Question 2:** How do `BootstrapRegistry` and `ConfigurableBootstrapContext` differ?

**Answer:** `BootstrapRegistry` only defines registration/close-listener operations; `ConfigurableBootstrapContext` extends both `BootstrapRegistry` and `BootstrapContext`, enabling both registering and retrieving objects.

**Question 3:** Does registering a supplier mean immediately constructing the object?

**Answer:** No. The mechanism is designed for lazy lookup; calling `get` triggers the supplier when no corresponding instance exists yet.

**Question 4:** Does `BootstrapContextClosedEvent` mean the application is ready and all beans exist?

**Answer:** No. It fires once the ApplicationContext has been prepared. Refreshing, instantiating beans, and running runners belong to subsequent steps.

**Question 5:** Can you register two clients of the same type with different configs using two string names in this registry?

**Answer:** There are no bean names in registration keys; the registry only uses `Class<T>`. You must organize distinct types or a wrapper class managing the client collection.

**Question 6:** After `registerSingleton` places a bootstrap instance into BeanFactory, can you rely on Spring re-running all init callbacks on it?

**Answer:** No. It is a pre-constructed object, so the integration itself must review lifecycle and cleanup.

## 13. Official documentation and takeaways

Reference sources matching the Spring Boot release line in use:

- [Spring Boot 3.3 — BootstrapRegistry API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/BootstrapRegistry.html).
- [Spring Boot 3.3 — ConfigurableBootstrapContext](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ConfigurableBootstrapContext.html).
- [Spring Boot 3.3 — BootstrapContext and lookup](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/BootstrapContext.html).
- [Spring Boot 3.3 — BootstrapRegistry.InstanceSupplier](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/BootstrapRegistry.InstanceSupplier.html).
- [Spring Boot 3.3 — BootstrapContextClosedEvent](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/BootstrapContextClosedEvent.html).
- [Spring Boot 3.3 — SpringApplication](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html).
- [Spring Boot 4.x — BootstrapRegistry (new package)](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/bootstrap/BootstrapRegistry.html).

**Points you must not confuse:**

1. The bootstrap registry solves **dependencies before beans exist**, rather than replacing Spring IoC.
2. `BootstrapRegistry` registers suppliers; `BootstrapContext` retrieves objects; `ConfigurableBootstrapContext` combines both.
3. Registration is keyed by **`Class<T>`**, not bean name; it can create lazy singletons or prototypes by scope.
4. `BootstrapRegistryInitializer` is called early, before steps needing the bootstrap context.
5. `ApplicationEnvironmentPreparedEvent` exposes the bootstrap context during the early phase.
6. `BootstrapContextClosedEvent` is the context-preparation boundary; if a resource must enter runtime beans, perform an **explicit handoff**.
7. Moving an existing instance via `registerSingleton` does not automatically guarantee all lifecycle hooks like normally created beans.
8. Check the version before copying imports: **Spring Boot 3.3 uses `org.springframework.boot`; Spring Boot 4.x uses `org.springframework.boot.bootstrap`** for bootstrap APIs.
