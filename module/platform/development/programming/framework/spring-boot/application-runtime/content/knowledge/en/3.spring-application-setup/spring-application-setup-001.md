# Configuring SpringApplication Before run and Modification Limits After Startup

## 1. The Problem to Understand

`SpringApplication` is the object that orchestrates the Spring Boot startup process. An application typically creates this object, sets bootstrap options, and then calls `run(args)`:

~~~java
SpringApplication application = new SpringApplication(MyApplication.class);
application.setWebApplicationType(WebApplicationType.NONE);
application.setDefaultProperties(Map.<String, Object>of("demo.mode", "training"));
application.run(args);
~~~

**Key point:** The `set...` methods on `SpringApplication` primarily describe **how an `ApplicationContext` will be created and started**. Once `run` completes, the context, many singleton beans, and initialized resources already have their own state. Changing a configuration field on the `SpringApplication` instance at this point **does not automatically reconfigure the active context**.

Three kinds of work must be separated:

1. **Bootstrap configuration before `run`:** Choosing the application type, banner, bean creation policy, default properties, profiles, listeners, and initializers.
2. **Configuration loaded by Spring Boot during startup:** `application.properties`/`application.yml`, environment variables, command-line arguments, `spring.main.*`, etc. They participate in the configuration precedence mechanism; some settings must be present very early.
3. **Runtime state after `run`:** Beans, connections, HTTP servers, and tasks can continue operating. A few values can be changed through dedicated runtime APIs, but changing many bootstrap choices requires **creating a new context or restarting**.

Do not confuse "the `SpringApplication` object still exists" with "that object still controls everything about the context it just launched".

## 2. Timeline: Why Configure Before run?

A typical startup process has these conceptual phases:

~~~text
main(String[] args)
    |
    v
new SpringApplication(Main.class)
    |
    +-- setBannerMode(...)
    +-- setWebApplicationType(...)
    +-- setDefaultProperties(...)
    +-- setAdditionalProfiles(...)
    +-- addInitializers(...) / addListeners(...)
    |
    v
application.run(args)
    |
    +-- Prepare Environment and external configuration
    +-- Create appropriate ApplicationContext
    +-- Apply ApplicationContextInitializer
    +-- Register configuration, scan beans, auto-configuration
    +-- Refresh context; initialize required singletons
    +-- Run ApplicationRunner / CommandLineRunner
    +-- Publish application ready signal
    |
    v
run(...) returns ConfigurableApplicationContext
    |
    v
Application continues serving requests / processing work
~~~

This is a **learning model**, not an exhaustive list of every internal callback. Some events such as `ApplicationStartingEvent` and `ApplicationEnvironmentPreparedEvent` occur very early, before a normal context can process them. `ApplicationStartedEvent` occurs after the context is refreshed but before runners; `ApplicationReadyEvent` occurs after runners.

An option used during a startup step may no longer have an "application point" afterward:

- **Application type:** `setWebApplicationType(WebApplicationType.NONE)` helps select a non-web context type before the context is created. Changing `webApplicationType` on `SpringApplication` after `run` does not turn the current context into a different web/non-web context.
- **Bean initialization:** `setLazyInitialization(true)` affects how Spring handles beans when creating the context. Changing the option after singletons have already been created cannot undo those initializations.
- **Banner and startup log:** The banner is printed during startup; `setBannerMode(Banner.Mode.OFF)` after `run` cannot retract an already-printed banner. `setLogStartupInfo(false)` only pertains to startup information logged by SpringApplication, and does not disable all loggers.
- **Profiles:** `setAdditionalProfiles("demo")` is evaluated when preparing the environment and loading configuration. Adding a profile to `SpringApplication` after the context has refreshed does not automatically create additional `@Profile("demo")` beans or reload conditional configuration.
- **Listeners/initializers:** If you need to observe early startup events, register the listener **before** `run`. `ApplicationContextInitializer` is only invoked during context preparation, not as a "re-initialize" command to call at any time.

## 3. Common Pre-run Settings

| API on SpringApplication | Meaning | Things to Consider |
| --- | --- | --- |
| `setWebApplicationType(WebApplicationType.NONE)` | Selects an application that does not run an embedded web server. | Used for CLI, background tasks, batch; HTTP APIs require the corresponding web type. |
| `setBannerMode(Banner.Mode.OFF)` | Does not print the default banner at startup. | Does not turn off all logs or exceptions. |
| `setLogStartupInfo(false)` | Reduces startup information logged by SpringApplication. | Other loggers can still print logs. |
| `setDefaultProperties(Map...)` | Creates fallback values in `Environment`. | Low precedence; external configuration/arguments can override them. |
| `setAdditionalProfiles("dev")` | Adds profiles to the already-configured profiles. | Can change which configuration files/beans are selected at startup. |
| `setAddCommandLineProperties(false)` | Does not map `--key=value` arguments into properties in `Environment`. | Not the same as removing `args` passed into runners. |
| `setLazyInitialization(true)` | Enables lazy initialization mode for many beans. | Can delay error detection until the first time a bean is used. |
| `setAllowBeanDefinitionOverriding(true)` | Allows bean definitions with the same name to override one another. | Bean conflicts should be resolved explicitly; do not enable this indiscriminately to hide errors. |
| `addInitializers(...)` | Runs logic on the context during the preparation phase. | Not meant for modifying beans already in use at runtime. |
| `addListeners(...)` | Registers an `ApplicationListener` for lifecycle events. | Listeners for early events must be registered early; avoid running heavy tasks in callbacks. |

For typical applications, you can use `SpringApplication.run(Main.class, args)` without creating a customized instance. A configuration class with `@SpringBootApplication` does not inherently require calling multiple setters.

**Do not assume a setter "wins" over all other sources:** Spring Boot also reads properties such as `spring.main.*` from `Environment` and binds them to startup settings. Which setting takes effect depends on **timing** and **value source**. If there are overlapping settings across files, environment variables, or arguments, check the precedence order and actual values rather than assuming a setter call always has highest priority.

### Default Values vs. Mandatory Values

~~~java
application.setDefaultProperties(
        Map.<String, Object>of("demo.mode", "default-value"));
~~~

For example, `demo.mode` can be overridden with:

~~~bash
gradle bootRun --args="--demo.mode=from-cli"
~~~

`setDefaultProperties` is useful when you want the application to have sensible defaults while still allowing the deployment environment to change the values. When you want to enforce a critical business rule, check and validate it separately instead of relying on setting a default property.

## 4. Hands-On: Proving the Boundary Before and After run

The following example uses **Java 17+**, **Spring Boot 3.3.13**, and Gradle. This is a complete console (non-web) application. It demonstrates at the same time:

1. A default property configured **before** `run`.
2. Changing `SpringApplication.setDefaultProperties(...)` **after** `run` does not reconfigure the `Environment` attached to the context.
3. Proactively adding a new `PropertySource` can cause subsequent `Environment` reads at runtime to change.
4. A bean that already stored the old value does not automatically pick up the new value from `Environment`. To change the bean's state, the application must perform an explicit operation.

### Project Structure

~~~text
spring-runtime-boundary/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── boundary/
                        └── BootstrapBoundaryApplication.java
~~~

**File `settings.gradle`:**

~~~groovy
rootProject.name = 'spring-runtime-boundary'
~~~

**File `build.gradle`:**

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
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-starter'
}

springBoot {
    mainClass = 'com.example.boundary.BootstrapBoundaryApplication'
}
~~~

**File `src/main/java/com/example/boundary/BootstrapBoundaryApplication.java`:**

~~~java
package com.example.boundary;

import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;

@SpringBootApplication
public class BootstrapBoundaryApplication {

    public static void main(String[] args) {
        // 1. Configure SpringApplication BEFORE run.
        SpringApplication application =
                new SpringApplication(BootstrapBoundaryApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);
        application.setDefaultProperties(
                Map.<String, Object>of("demo.mode", "bootstrap-default"));
        application.setAdditionalProfiles("training");

        // 2. run creates the context, loads configuration, and initializes beans.
        try (ConfigurableApplicationContext context = application.run(args)) {
            ConfigurableEnvironment environment = context.getEnvironment();
            RuntimeSwitch runtimeSwitch = context.getBean(RuntimeSwitch.class);

            System.out.println("env.start=" +
                    environment.getProperty("demo.mode"));
            System.out.println("bean.start=" + runtimeSwitch.mode());

            // 3. SpringApplication setters do not update the existing context.
            application.setDefaultProperties(
                    Map.<String, Object>of("demo.mode", "late-default"));
            application.setBannerMode(Banner.Mode.CONSOLE);
            System.out.println("env.after-setter=" +
                    environment.getProperty("demo.mode"));

            // 4. This directly mutates the Environment (for EXPERIMENTATION).
            environment.getPropertySources().addFirst(
                    new MapPropertySource(
                            "manualRuntimeOverride",
                            Map.<String, Object>of(
                                    "demo.mode", "runtime-source")));

            System.out.println("env.after-source=" +
                    environment.getProperty("demo.mode"));
            System.out.println("bean.after-source=" + runtimeSwitch.mode());

            // 5. Update bean state through the designed API.
            runtimeSwitch.changeMode("manual-update");
            System.out.println("bean.after-update=" + runtimeSwitch.mode());
        }
    }

    @Bean
    RuntimeSwitch runtimeSwitch(ConfigurableEnvironment environment) {
        // This bean captures the value at the time it is created.
        return new RuntimeSwitch(
                environment.getProperty("demo.mode", "fallback"));
    }

    public static final class RuntimeSwitch {
        private final AtomicReference<String> currentMode;

        public RuntimeSwitch(String initialMode) {
            this.currentMode = new AtomicReference<>(initialMode);
        }

        public String mode() {
            return currentMode.get();
        }

        public void changeMode(String newMode) {
            currentMode.set(newMode);
        }
    }
}
~~~

**Explanation of why the program behaves this way:**

- `SpringApplication` is created with `BootstrapBoundaryApplication.class` itself, used as the Spring Boot configuration source.
- `WebApplicationType.NONE` is for a console example that does not open an HTTP port. `Banner.Mode.OFF` and `setLogStartupInfo(false)` make the experiment output lines easier to read, but do not guarantee silencing all loggers.
- `@Bean` creates a `RuntimeSwitch` with the `demo.mode` value **at the moment the bean is constructed**. `AtomicReference` is a safe Java mechanism for reading/resetting *a single reference value* across multiple threads; the example does not attempt to solve every complex configuration change scenario.
- After `application.run(args)`, calling `application.setDefaultProperties(...)` only changes the configuration stored on the bootstrap object; the running context's `Environment` still retains the property sources prepared earlier.
- `environment.getPropertySources().addFirst(...)` is an operation **directly on the running `Environment`**. It causes new reads of `demo.mode` to change because the new property source sits at the front of the list. **It does not recreate beans**, so `RuntimeSwitch` keeps the value it received upon initialization.
- `runtimeSwitch.changeMode(...)` changes the bean's own state. Components calling `mode()` afterward will see the new state; this is not equivalent to changing Spring Boot's global configuration.
- `try (ConfigurableApplicationContext context = ...)` closes the context when the experiment ends. Only do this for short-lived programs; web applications must keep the context active while serving requests.

### How to Run and Compare

In the directory containing `build.gradle`, with a compatible Gradle installed:

~~~bash
gradle bootRun
~~~

If the project includes a Gradle Wrapper, you can run `./gradlew bootRun` on Linux/macOS or `.\gradlew.bat bootRun` on Windows.

When **no** other configuration source sets `demo.mode`, the lines printed by the Java code itself have the exact content below (framework log lines may be added around them):

~~~text
env.start=bootstrap-default
bean.start=bootstrap-default
env.after-setter=bootstrap-default
env.after-source=runtime-source
bean.after-source=bootstrap-default
bean.after-update=manual-update
~~~

Comparison:

| Checkpoint | `Environment` | `RuntimeSwitch` | Why? |
| --- | --- | --- | --- |
| After `run` | `bootstrap-default` | `bootstrap-default` | Both receive the value present at startup. |
| After `application.setDefaultProperties` | Still `bootstrap-default` | Still `bootstrap-default` | Late setter does not replace property sources already attached to the context. |
| After `addFirst(new MapPropertySource(...))` | `runtime-source` | Still `bootstrap-default` | New lookups see the higher-priority source; the bean does not automatically rebind. |
| After `runtimeSwitch.changeMode(...)` | `runtime-source` | `manual-update` | Business API updates the bean's own state. |

Try running with a command-line argument:

~~~bash
gradle bootRun --args="--demo.mode=from-cli"
~~~

With other input property sources unchanged, the **first three lines** will be:

~~~text
env.start=from-cli
bean.start=from-cli
env.after-setter=from-cli
~~~

After that, the `addFirst(...)` call in the program still prioritizes the `manualRuntimeOverride` source for `Environment` lookups, while the bean retains the `from-cli` value until `changeMode(...)` is called.

**Scope limitation of the experiment:** Manually inserting a `MapPropertySource` after startup is only meant to illustrate the boundary between property lookup and bean state. It is not a recommendation for updating system-wide configuration in production; beans consuming configuration may have different lifecycles, caches, and synchronization requirements.

## 5. What Can and Cannot Be Changed After Startup

The phrase "application has already started" should be understood as the context having refreshed, dependent beans having been created, and `run` having completed. Afterward:

| Requirement | Appropriate Approach | Does It Happen Automatically When Calling a Late SpringApplication Setter? |
| --- | --- | --- |
| Change the printed banner or past startup log lines | Change the configuration before the next startup. | **No** |
| Switch a non-web context to web and open an embedded server | Start a context with the web type and compatible dependencies. | **No** |
| Change profiles to register new `@Profile` beans | Restart or use an explicitly designed context/bean management mechanism. | **No** |
| Change a default property so already-created beans get the new value | Use an intentional reload/rebind mechanism or restart; depends on the bean type. | **No** |
| Adjust a live business logic value | Call a bean API designed for runtime changes; ensure concurrency control. | **No, requires a business operation** |
| Read a new property inserted into `ConfigurableEnvironment` | Manipulating property sources directly can make subsequent lookups see the new value. | **No, late setters differ from mutating Environment** |
| Stop the application and release resources | Use the proper lifecycle, such as intentionally closing the context or a shutdown procedure. | **Unrelated to bootstrap setters** |

**Distinguish three levels of "new value"**:

1. **`Environment.getProperty(...)`** typically reads `PropertySource` entries at the time it is called. If the source actually changes and has appropriate precedence, a new read can differ from a previous one.
2. **`@Value`, `@ConfigurationProperties`, and constructor injection** usually supply values to a bean when it is created or bound. Changing a property source does not equate to automatically reassigning fields of all running beans.
3. **Already-initialized infrastructure** such as an embedded server, connection pools, executors, and schedulers also have their own resources/lifecycles. Changing a string property does not automatically change listening ports, open connections, or running threads.

Some ecosystems offer dynamic refresh solutions, such as Spring Cloud Context with its corresponding features and conditions. You should not infer that **plain Spring Boot** will automatically reload every bean whenever you edit a YAML file or property source. If the architecture supports refresh, verify exactly which beans are refreshable, what state gets replaced, and how to test consistently.

## 6. Configuration File Locations and Timing Constraints

Not all configuration is read at the same time.

- **Very early configuration:** Keys such as `spring.config.name`, `spring.config.location`, and `spring.config.additional-location` determine where Spring Boot looks for files. They must be available from an appropriate `Environment` source when the config data loading process runs (for example, environment variables, JVM system properties, or command-line arguments).
- **Bootstrap runtime configuration:** `spring.main.*` relates to initializing `SpringApplication`/context. You cannot expect `@PropertySource` on a `@Configuration` class to be present early enough for every option, because this source is only added while the context is refreshing.
- **Bean configuration:** A property assigned to `@ConfigurationProperties` is usually bound when the bean is constructed. Changing file contents on disk afterward does not automatically cause the bean to rebind.
- **Command-line arguments:** With the default `setAddCommandLineProperties(true)`, arguments of the form `--demo.mode=value` are placed into `Environment` by Spring Boot and can override default properties. If `setAddCommandLineProperties(false)` is called before `run`, the arguments still exist in `String[] args` and `ApplicationArguments`, but are not added as the default command-line property source.

In particular, **editing `application.yml` and expecting the configuration to take effect automatically** is a common misconception. In an application without a refresh mechanism, perform a controlled redeploy/restart, or build a dedicated runtime management interface only for parameters that can be safely adjusted.

## 7. Choosing the Right Extension Point

There are three options that are commonly confused:

### 7.1. Setters and Initializers Before run

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setAdditionalProfiles("local");
app.addInitializers(context -> {
    // Interact with the context during the preparation phase.
    // Do not assume beans have been fully created here.
});
app.run(args);
~~~

This is a **partial illustration**, not a standalone runnable program. Initializers are suitable for context preparation, not for operating on beans that are only needed after refresh. For listeners handling very early startup events, they must be registered sufficiently early (`addListeners` or the corresponding registration mechanism).

### 7.2. Running After Beans Are Ready

~~~java
@Bean
ApplicationRunner initializeBusinessData(MyService service) {
    return arguments -> service.initialize();
}
~~~

This is also an **illustrative snippet**, assuming the project already has `MyService` and imports `ApplicationRunner`/`Bean`. `ApplicationRunner` and `CommandLineRunner` are invoked by Spring Boot as part of `run` after context refresh. They are suitable for verifying data and executing business initialization logic, but **too late** to change the selected `ApplicationContext` type.

### 7.3. Changing While the Application Is Running

If a requirement is like "change alert threshold without restarting", design a bean that holds validated runtime configuration and updates via a dedicated method. You need to consider caller permissions, validation, concurrency, in-flight state, and auditing changes. The `AtomicReference` example in section 4 only models a single value; for multiple related properties, update **an entire immutable configuration object** atomically rather than changing separate fields piecemeal, which leads to a half-old, half-new state.

## 8. Common Mistakes

**Mistake 1 — Calling a setter after run and expecting the context to switch automatically**

~~~java
ConfigurableApplicationContext context = app.run(args);
app.setWebApplicationType(WebApplicationType.NONE); // Does not convert the existing context.
~~~

If you want non-web, set `setWebApplicationType` **before** `run`. Once the context type has been created, there is no in-place type conversion using this setter.

**Mistake 2 — Calling run a second time to "re-apply configuration"**

~~~java
app.run(args);
app.run(args);
~~~

Each call to `run` starts a new context, rather than refreshing the old context. This can lead to beans/runners executing twice, port contention, or conflicts over resources or shared state. If you intentionally manage multiple contexts, design their lifecycles explicitly; do not use two `run` calls as a reload trick.

**Mistake 3 — Assuming every property updates dynamically**

~~~java
// Editing application.properties on disk while the JVM is running
// does not guarantee that already-initialized @Value/@ConfigurationProperties will change.
~~~

This is an explanatory comment, not a command that changes configuration. Know clearly which reload mechanism has been configured before claiming a property updates dynamically.

**Mistake 4 — Using @PropertySource for very early configuration**

~~~java
@PropertySource("classpath:my-startup.properties")
@Configuration
class ExtraConfig {
}
~~~

The snippet above is illustrative only and needs the corresponding imports. `@PropertySource` adds a source when the context refreshes, so it can be too late for settings like `logging.*` and `spring.main.*`. Use startup sources that Spring Boot reads during the environment preparation phase.

**Mistake 5 — Closing the context right after run in a web application**

~~~java
try (ConfigurableApplicationContext context = app.run(args)) {
    // ...
} // Context is closed here.
~~~

This structure fits a CLI/short-lived experiment like section 4; for a long-running REST API/consumer, closing the context causes the application to stop serving.

**Mistake 6 — Mutating a bean directly without checking concurrency**

Changing a field accessed by multiple threads without synchronization can cause different requests to observe inconsistent state. Choose safe update mechanisms, validation, and auditing according to actual needs; do not expect `SpringApplication` setters to solve concurrency for beans.

## 9. Knowledge Self-Check

1. Why does `setBannerMode(OFF)` after `run` have no effect on the banner of the startup that just finished?
2. Can an already-started non-web application become a web server simply by calling `setWebApplicationType(SERVLET)` after `run`? Explain in relation to `ApplicationContext` selection.
3. In the section 4 example, why does `env.after-source` differ from `bean.after-source`?
4. Run the same program with and without `--demo.mode=from-cli`. Identify which property source is winning before the `addFirst` operation.
5. If operators need to adjust the retry threshold of a running service, how would you design the update API and validation? When should a restart be required?
6. If an `ApplicationListener` needs to receive `ApplicationStartingEvent`, at what point must it be registered? Why are beans discovered only after refresh generally unsuitable for very early events?

## Key Takeaway

**Apply configuration that determines context creation on `SpringApplication` before `run(args)`.** Once `run` has created and refreshed the context, changing setters on the bootstrap object does not replay the lifecycle that just occurred. `Environment` can support dynamic property lookups in certain scenarios, but already-bound beans and already-built infrastructure require separate update mechanisms or a restart.

### References

- Spring Boot 3.3 — `SpringApplication` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Boot 3.3 — Externalized Configuration: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 — Application Events and Listeners: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.application-events-and-listeners
