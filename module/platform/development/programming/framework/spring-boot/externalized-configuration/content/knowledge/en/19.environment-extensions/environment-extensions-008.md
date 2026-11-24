# Distinguishing `EnvironmentPostProcessor` from `ApplicationContextInitializer` in Spring Boot

## 1. Problem and Objectives

Spring Boot allows retrieving configuration from multiple sources instead of hard-coding values in Java: `application.yml`, `application.properties`, OS environment variables, JVM system properties, command-line arguments, config trees, and additional sources provided by applications or libraries.

Sometimes standard sources are not enough. For example, an application may need to:

- Provide a default value for `app.region` when the deployment has not declared one.
- Load a group of properties through a controlled mechanism before Spring creates beans.
- Change **a characteristic of the application context itself** before it begins refreshing.
- Attach a listener or a `BeanFactoryPostProcessor` to the context during the initialization phase.
- Identify an appropriate extension point to process configuration very early without mixing infrastructure logic into `@PostConstruct` or business services.

Two mechanisms are commonly mentioned:

1. **`EnvironmentPostProcessor`** — a **Spring Boot** extension point for `Environment`.
2. **`ApplicationContextInitializer`** — a **Spring Framework** extension point for `ConfigurableApplicationContext`.

Their names sound similar because both run before the application is ready, but **their target objects, lifecycles, registration mechanisms, and scopes of impact differ**.

> Short conclusion: use `EnvironmentPostProcessor` when the primary goal is to **prepare/adjust the Environment at an early stage**; use `ApplicationContextInitializer` when you need to **initialize or customize an ApplicationContext that has been created but not yet refreshed**.

The main Java examples in this article target **Spring Boot 3.3–3.5, Java 17+**. In Spring Boot 4.x, some related packages/APIs have shifted; the final section explains how to check your version to avoid copying incorrect imports.

## 2. Understanding the Two Objects: `Environment` and `ApplicationContext`

### 2.1. `Environment` Manages Effective Configuration Values

`org.springframework.core.env.Environment` provides a way to access configuration:

~~~java
String region = environment.getProperty("app.region");
boolean enabled = environment.getProperty(
        "app.audit.enabled", Boolean.class, false);
~~~

`ConfigurableEnvironment` allows manipulating `PropertySource`s and profiles:

~~~java
MutablePropertySources sources = environment.getPropertySources();
sources.addLast(new MapPropertySource("fallbacks", values));
~~~

`Environment` is not synonymous with a single YAML file. It aggregates multiple sources in **precedence order**. Typically, a property with the same name in a higher-precedence source overrides the value in a lower-precedence source.

### 2.2. `ApplicationContext` Is the Container Managing Beans

`org.springframework.context.ApplicationContext` is Spring's runtime context, holding bean definitions, dependency injection, event publishing, and various other infrastructure components.

`ConfigurableApplicationContext` allows customizing the lifecycle before refresh:

~~~java
context.setId("catalog-local");
context.addApplicationListener(listener);
context.addBeanFactoryPostProcessor(postProcessor);
~~~

The context has its own `Environment`:

~~~java
ConfigurableEnvironment env = context.getEnvironment();
~~~

Therefore, **`ApplicationContextInitializer` can also access and modify `Environment`**. However, the timing of when it is invoked differs from `EnvironmentPostProcessor`, so you cannot assume the two mechanisms are equivalent in all situations.

## 3. Spring Boot Startup Timeline

A simplified diagram for a typical application:

~~~text
main(String[] args)
       |
       v
SpringApplication.run(args)
       |
       v
Prepare Environment
       |
       +--> process EnvironmentPostProcessors
       |    (including processing Config Data in the appropriate order)
       |
       +--> Environment ready for context creation
       |
       v
Create ConfigurableApplicationContext
       |
       v
Attach Environment to context, prepare context
       |
       +--> ApplicationContextInitializer.initialize(context)
       |    (context exists, not yet refreshed)
       |
       v
Load bean definitions
       |
       v
Refresh ApplicationContext
       |
       +--> BeanFactoryPostProcessor
       +--> create/initialize singleton beans
       +--> Dependency injection, @ConfigurationProperties
       +--> lifecycle and infrastructure by context type
       |
       v
ApplicationStartedEvent, runners, ApplicationReadyEvent...
~~~

The diagram is a **conceptual model**, not an exhaustive list of every internal callback. Spring Boot has many application events and listeners; the triggering of post-processors and loading of Config Data have their own specific ordering. However, the important relative order is:

- **Environment exists before ApplicationContext.**
- **EnvironmentPostProcessor** operates during Environment preparation.
- **ApplicationContextInitializer** receives a created context and runs before the refresh step.
- `@Bean`, `@Component`, and regular business services are not things you can freely retrieve at either of the two stages above.

Following Spring Boot's sequence of application events, `ApplicationEnvironmentPreparedEvent` occurs when the Environment is known but the context has not yet been created; `ApplicationContextInitializedEvent` occurs after initializers have run and before bean definitions are loaded. This helps determine the appropriate stage for placing startup logic.

## 4. Overview Comparison Table

| Criterion | `EnvironmentPostProcessor` | `ApplicationContextInitializer` |
| --- | --- | --- |
| Belongs to which framework | Spring Boot | Spring Framework |
| Input objects | `ConfigurableEnvironment` and `SpringApplication` | `ConfigurableApplicationContext` |
| Main method | `postProcessEnvironment(...)` | `initialize(...)` |
| When it runs | During the Environment preparation phase | After the context is created, before refresh |
| Has `ApplicationContext` to manipulate? | No context argument | Yes |
| Can add a `PropertySource`? | Yes, its primary purpose | Yes, via `context.getEnvironment()` |
| Can add a listener to the context? | Not directly via context | Yes |
| Can set the context ID? | Not directly | Yes |
| Discovered via component scan like `@Component`? | Should not rely on component scan | Should not rely on component scan |
| Automatic registration in Boot 3.x | `META-INF/spring.factories` with key `org.springframework.boot.env.EnvironmentPostProcessor` | `META-INF/spring.factories` with key `org.springframework.context.ApplicationContextInitializer` |
| Explicit registration in Java | Usually via SPI; custom listener/lifecycle mechanisms can be added | `SpringApplication.addInitializers(...)` |
| Can control already-loaded Config Data? | Depends on order relative to Config Data processor | Usually **too late** to ask Config Data to reload |
| Should depend on business beans? | No | No, because the context has not refreshed |
| Typical goals | Custom config sources, fallback values, Environment preparation | Context ID, listeners, BeanFactoryPostProcessors, and context-level setup |

Neither mechanism is inherently "stronger" in every case. **Choose based on when the value is needed and what you want to change.**

## 5. The `EnvironmentPostProcessor` API in Spring Boot 3.x

Common imports in Spring Boot 3.3–3.5:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.env.ConfigurableEnvironment;
~~~

Interface:

~~~java
public interface EnvironmentPostProcessor {
    void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application);
}
~~~

The callback receives:

- `environment`: allows adding, removing, or reorganizing `PropertySource`s within API boundaries.
- `application`: the `SpringApplication` instance being started.

Minimal example:

~~~java
package com.example.boot;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;

public final class DemoEnvironmentPostProcessor
        implements EnvironmentPostProcessor {

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application) {

        Map<String, Object> properties =
                Map.of("app.region", "vn");

        environment.getPropertySources().addLast(
                new MapPropertySource("demoFallback", properties));
    }
}
~~~

This is an example of a **fallback property source**, not updating configuration declared in a higher-precedence source.

`MapPropertySource` uses a map as its data source. `addLast(...)` places the new source at the end of the priority chain: it is used when no preceding source provides the same property name.

### 5.1. Why `addLast`?

If a deployment sets:

~~~bash
APP_REGION=apac java -jar app.jar
~~~

then `app.region` can be resolved from the OS environment instead of `vn` in the fallback. This is usually the desired behavior: code provides a fallback value, yet operators can still override it.

If you intentionally use:

~~~java
environment.getPropertySources().addFirst(
        new MapPropertySource("forcedRegion", properties));
~~~

then the new source gets very high precedence and can override values provided by CLI, OS environment, or config files. This can be surprising and strip the deployment environment of control.

**Determine source precedence according to the configuration contract.** Do not default to `addFirst` simply because you want to be sure a property "takes effect."

## 6. Full Example: `EnvironmentPostProcessor` Adding a Fallback

### 6.1. Implementation Class

~~~java
package com.example.boot;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.Ordered;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;

public final class RegionDefaultsEnvironmentPostProcessor
        implements EnvironmentPostProcessor, Ordered {

    private static final String SOURCE_NAME = "exampleRegionDefaults";

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application) {

        if (environment.getPropertySources().contains(SOURCE_NAME)) {
            return;
        }

        Map<String, Object> defaults = new LinkedHashMap<>();
        defaults.put("app.region", "vn");
        defaults.put("app.audit.enabled", "false");

        environment.getPropertySources().addLast(
                new MapPropertySource(SOURCE_NAME, defaults));
    }

    @Override
    public int getOrder() {
        return Ordered.LOWEST_PRECEDENCE;
    }
}
~~~

Purpose of the example:

1. Has an explicit `PropertySource` name to aid diagnostics.
2. Avoids registering a duplicate source named `exampleRegionDefaults` in the same `Environment`.
3. Uses `addLast` to supply values only when higher-precedence sources have not set them.
4. Uses `Ordered.LOWEST_PRECEDENCE` so the lesson does not depend on running before the Config Data processor. This fits a **simple fallback**, not cases where the goal is to alter the Config Data loading mechanism before it runs.

### 6.2. Registering via `META-INF/spring.factories`

Create the file at the exact path:

~~~text
src/main/resources/META-INF/spring.factories
~~~

Content:

~~~properties
org.springframework.boot.env.EnvironmentPostProcessor=\
com.example.boot.RegionDefaultsEnvironmentPostProcessor
~~~

The trailing `\` on the first line is Java Properties line continuation. Or write it on a single line to avoid syntax mistakes:

~~~properties
org.springframework.boot.env.EnvironmentPostProcessor=com.example.boot.RegionDefaultsEnvironmentPostProcessor
~~~

**This is the fully qualified name of the interface in Spring Boot 3.x.** Spring Boot discovers implementers under this key in `spring.factories` when creating `SpringApplication`. Placing `@Component` on the class is not a reliable alternative, because environment processing happens **before** scanning and creating component beans.

If packaged into a shared library JAR, the `META-INF/spring.factories` file must exist inside the published JAR itself. Do not put it only in `src/test/resources` if you want the behavior active in production.

### 6.3. Demo Application

~~~java
package com.example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

`src/main/resources/application.yml`:

~~~yaml
app:
  audit:
    enabled: true
~~~

When starting up without `APP_REGION` or another source for `app.region`, the typical result is:

~~~text
app.region = vn
app.audit.enabled = true
~~~

`app.region` comes from `exampleRegionDefaults`. Meanwhile, `app.audit.enabled=true` in YAML takes precedence over `false` from the fallback.

If you add:

~~~bash
APP_REGION=apac java -jar demo.jar
~~~

then `app.region=apac` can win over the fallback.

### 6.4. Reading Values After Startup

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
public class DemoDiagnostics {

    @Bean
    ApplicationRunner printEffectiveProperties(Environment environment) {
        return args -> {
            System.out.println("region="
                    + environment.getProperty("app.region"));
            System.out.println("audit="
                    + environment.getProperty("app.audit.enabled"));
        };
    }
}
~~~

This is an example of observing non-sensitive properties. For real secrets, **do not log the entire Environment or configuration objects**, as they may contain passwords, tokens, or internal infrastructure details.

## 7. The `ApplicationContextInitializer` API

Main imports:

~~~java
import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;
~~~

Interface:

~~~java
public interface ApplicationContextInitializer<
        C extends ConfigurableApplicationContext> {

    void initialize(C applicationContext);
}
~~~

You receive a `ConfigurableApplicationContext` that **already exists** but has not yet refreshed. You can:

- Read `context.getEnvironment()`.
- Change the context ID via `context.setId(...)`.
- Add application listeners.
- Add a `BeanFactoryPostProcessor` to run during refresh.
- Prepare other context-level settings that the implementation actually supports.

You should not assume this is a point where services, repositories, and beans created by `@ComponentScan` are complete and retrievable via `getBean(...)`. Loading bean definitions and instantiating beans happens **after** the initializer callback in the normal Boot flow.

## 8. Full Example: `ApplicationContextInitializer` Setting the Context ID

Suppose the operations team needs each application context to have a distinct ID per running instance. The value is read from config data after the Environment has been prepared.

Class:

~~~java
package com.example.boot;

import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;

public final class InstanceIdContextInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        String instance = context.getEnvironment()
                .getProperty("app.instance-id", "local");

        context.setId("catalog-" + instance);
    }
}
~~~

`application.yml`:

~~~yaml
app:
  instance-id: zone-a-01
~~~

When the initializer runs, the context already has an `Environment`. It reads `app.instance-id` and sets:

~~~text
context.getId() = catalog-zone-a-01
~~~

This is a **context customization**, not merely adding a property value. It illustrates why to use `ApplicationContextInitializer` instead of `EnvironmentPostProcessor`.

### 8.1. Registering via `SpringApplication.addInitializers`

~~~java
package com.example;

import com.example.boot.InstanceIdContextInitializer;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(DemoApplication.class);

        application.addInitializers(new InstanceIdContextInitializer());
        application.run(args);
    }
}
~~~

`addInitializers(...)` is useful when you directly control the entrypoint and want to specify initializers in Java without editing `spring.factories`.

Be careful to call it before `run(args)`. Registering an initializer on another `SpringApplication` instance after the application has already started will not change the current run.

### 8.2. Registering via `spring.factories`

When packaging a library or wanting automatic initializer discovery on the classpath, Spring Boot also supports the key:

~~~properties
org.springframework.context.ApplicationContextInitializer=com.example.boot.InstanceIdContextInitializer
~~~

Placed in:

~~~text
src/main/resources/META-INF/spring.factories
~~~

This key belongs to a **Spring Framework interface**; it is **different** from the `EnvironmentPostProcessor` key. Do not list both classes under a single key and expect the framework to distinguish the methods automatically.

If an application registers the same initializer both explicitly via `addInitializers(...)` and via `spring.factories`, you must guard against duplicate execution or the same behavior being applied multiple times. It is best to use **one clear registration mechanism** per initializer.

## 9. Using an Initializer to Add a Listener

`ApplicationContextInitializer` can also be used to register an application listener on a context about to be refreshed.

Example:

~~~java
package com.example.boot;

import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.ApplicationListener;
import org.springframework.context.event.ContextRefreshedEvent;

public final class StartupListenerInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        context.addApplicationListener(
                (ApplicationListener<ContextRefreshedEvent>) event -> {
                    // Use only non-sensitive metadata in this example.
                    String id = event.getApplicationContext().getId();
                    System.out.println("Context refreshed: " + id);
                });
    }
}
~~~

The initializer **registers** the listener before refresh; the listener actually receives `ContextRefreshedEvent` **when that event is published**, not at the moment `initialize(...)` executes.

If the goal is solely to listen for an application event, registering a listener directly can be simpler than writing an initializer. However, the example above demonstrates that an initializer has the ability to **customize the context itself**.

You can also call:

~~~java
context.addBeanFactoryPostProcessor(postProcessor);
~~~

to add a processor to serve the refresh step. That processor must be implemented in accordance with Spring's lifecycle and should not be used to invoke business beans that have not yet been created.

## 10. Can `ApplicationContextInitializer` Modify the `Environment`?

**Yes.** Example:

~~~java
package com.example.boot;

import java.util.Map;

import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.MapPropertySource;

public final class ContextFlagInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        context.getEnvironment().getPropertySources().addLast(
                new MapPropertySource(
                        "contextFlags",
                        Map.of("app.diagnostics.label", "initialized")));
    }
}
~~~

A bean created **afterward** can access:

~~~java
String label = environment.getProperty("app.diagnostics.label");
~~~

And `@ConfigurationProperties` bound after the callback can see the corresponding value.

However, the crucial question is **who needs to read the property and at what time**.

- If the property is only used by beans, `@Value`, or `@ConfigurationProperties` during context refresh, adding it in an initializer **may be early enough**.
- If the property controls file discovery like `spring.config.location`, or affects a process that **already ran before the initializer**, adding it in an initializer is **too late**.
- If logging has already been configured based on the Environment beforehand, changing `logging.level.root` in an initializer may not cause the logging system to reinitialize with the new value.

Therefore, `ApplicationContextInitializer` does not replace `EnvironmentPostProcessor` for every early-configuration need, even though both can call `getPropertySources().addLast(...)`.

## 11. Side-by-Side Example: Same Problem, Which Extension Point to Choose?

Suppose there are two independent requirements:

**Requirement A:** provide a fallback `app.region=vn` so mechanisms using the Environment early can read it.

**Requirement B:** change the context ID to `catalog-zone-a-01` based on the already-loaded `app.instance-id`.

How to choose:

~~~text
app.region fallback
       |
       v
RegionDefaultsEnvironmentPostProcessor
       |
       v
Environment has the added PropertySource


app.instance-id from Environment
       |
       v
InstanceIdContextInitializer
       |
       v
ApplicationContext.setId(...)
~~~

If both classes are registered as instructed, they do not compete to do the same job. They operate at **two different stages**.

Scenario table:

| Task | Preferred Mechanism | Reason |
| --- | --- | --- |
| Add a property source before the context is created | `EnvironmentPostProcessor` | Invoked during the Environment preparation phase |
| Add a fallback for a business property | `EnvironmentPostProcessor` or default properties | Choose the simplest mechanism; sometimes no SPI is needed |
| Set Context ID based on an existing property | `ApplicationContextInitializer` | Must have the context to call `setId` |
| Register a listener on the context before refresh | `ApplicationContextInitializer` or listener registration | Has the context object |
| Add a `BeanFactoryPostProcessor` to run during refresh | `ApplicationContextInitializer` | Has the API on the context |
| Put a property into Environment for beans to bind later | Either can do it | Depends on when the property is consumed |
| Provide `spring.config.location` from startup code | Needs to be set **before** Config Data processing | Initializer is usually too late; `EnvironmentPostProcessor` must also have the right order |
| Load config from a custom protocol/remote store | Consider Config Data SPI | `ConfigDataLocationResolver`/`ConfigDataLoader` have dedicated contracts |
| Retrieve a service bean to make an HTTP call after startup | Neither is the right choice | Use a post-refresh lifecycle hook or an appropriate readiness/runner |

## 12. `EnvironmentPostProcessor` Order Relative to Config Data Is Critical

A common misconception: because `EnvironmentPostProcessor` runs "early," does every processor run **before** Spring Boot loads `application.yml`?

**No.** Spring Boot 2.4+'s Config Data loading itself is performed by a dedicated processor:

~~~java
org.springframework.boot.context.config.ConfigDataEnvironmentPostProcessor
~~~

This processor also has an execution order. Consequently, other `EnvironmentPostProcessor` implementations may run **before or after** it, depending on `Ordered` or `@Order`.

### 12.1. When You Want to Inspect Loaded Config Data

If your processor needs to read `app.region` from `application.yml` and then add some other values, it needs to run at a stage where that data is already available. A technical example of ordering:

~~~java
import org.springframework.boot.context.config.ConfigDataEnvironmentPostProcessor;
import org.springframework.core.Ordered;

@Override
public int getOrder() {
    return ConfigDataEnvironmentPostProcessor.ORDER + 1;
}
~~~

The goal is to run **after** the Config Data processor in Boot 3.x. `Ordered.LOWEST_PRECEDENCE` is also an option for running late if you are only adding fallbacks without needing very specific relative positioning.

Note that ordering can be affected by other processors; do not guess based on class names or the listing order in `spring.factories`. If you have sensitive lifecycle requirements, use `Ordered` intentionally and test in practice.

### 12.2. When You Want to Influence Finding/Loading Config Data

Properties such as:

~~~properties
spring.config.name
spring.config.location
spring.config.additional-location
spring.profiles.active
~~~

can participate in deciding which files, profiles, and Config Data structures to load. Adding them **after** Config Data has already been processed does not mean Spring Boot will automatically go back and re-read all sources.

If you truly need to customize Config Data's input data, choose a hook that runs before the corresponding step or use the dedicated Config Data API. For standard deployment configurations, supplying these values from **OS environment, JVM system properties, or command-line arguments** at startup is much easier to reason about.

Example:

~~~bash
SPRING_CONFIG_ADDITIONAL_LOCATION=optional:file:/etc/catalog/ \
  java -jar app.jar
~~~

Or:

~~~bash
java -Dspring.config.additional-location=optional:file:/etc/catalog/ -jar app.jar
~~~

Both approaches above supply values from a source earlier than a typical `ApplicationContextInitializer`.

### 12.3. When to Use Config Data SPI Instead of `EnvironmentPostProcessor`?

If the requirement is to support a custom URI form:

~~~properties
spring.config.import=customstore:team/catalog
~~~

then Spring Boot's Config Data model provides extension points such as:

~~~java
ConfigDataLocationResolver
ConfigDataLoader
~~~

They match the contract for resolving locations, loading data, profiles, and imports managed by Spring Boot. An `EnvironmentPostProcessor` that manually reads and adds a config source can accomplish some things, but it does not fully participate in all Config Data import rules.

**Choose the extension point suited to the problem** instead of stuffing all configuration-related logic into a catch-all startup processor.

## 13. `PropertySource` Precedence: A Common Mistake in Both Extension Points

When adding a `MapPropertySource`, two important APIs are:

~~~java
environment.getPropertySources().addFirst(source);
environment.getPropertySources().addLast(source);
~~~

General semantics:

- `addFirst`: the source gets higher precedence than existing sources.
- `addLast`: the source gets lower precedence than existing sources.

Example:

~~~yaml
# application.yml
app:
  mode: development
~~~

The processor adds:

~~~java
MapPropertySource custom = new MapPropertySource(
        "customMode",
        Map.of("app.mode", "production"));
~~~

If `addFirst(custom)` is called after the YAML source is already present, `app.mode` can become `production`. If `addLast(custom)` is called, `development` in YAML is normally preserved.

Do not place a source intended only as a fallback at the front, causing CLI and deployment environment values to be overridden. Similarly, do not place a source meant to have high precedence at the end and then conclude the processor "did not run" simply because its value is shadowed by another source.

You can choose relative placement:

~~~java
sources.addBefore("someSource", custom);
sources.addAfter("someSource", custom);
~~~

but the referenced source name must **actually exist** at the time of the call. Do not assume the names or ordering of all `PropertySource`s across every Spring Boot version.

## 14. Registration: Why `@Component` Is Not Enough?

`@ComponentScan` and `@Bean` operate during the phase of processing the application context and bean definitions. An `EnvironmentPostProcessor` needs to be invoked **before** regular bean creation takes place.

Therefore:

~~~java
@Component
public class MyEnvironmentPostProcessor
        implements EnvironmentPostProcessor {
    // ...
}
~~~

is not the right registration pattern for this SPI. The class may be picked up as a bean later, but **that does not mean** Spring Boot invoked it during the Environment preparation phase.

Similarly, an `ApplicationContextInitializer` registered as a regular `@Component` is not guaranteed to be applied as an initializer in the pre-refresh step; by the time the component is created, that moment has already passed.

Register properly:

- `EnvironmentPostProcessor`: `META-INF/spring.factories` with the Boot key.
- `ApplicationContextInitializer`: `SpringApplication.addInitializers(...)` or `spring.factories` with the Framework key.

When the same `spring.factories` file contains multiple SPI types:

~~~properties
org.springframework.boot.env.EnvironmentPostProcessor=com.example.boot.RegionDefaultsEnvironmentPostProcessor
org.springframework.context.ApplicationContextInitializer=com.example.boot.InstanceIdContextInitializer
~~~

These are two independent entries, not a shared list of classes.

## 15. Ordering Among Initializers

`ApplicationContextInitializer` can be ordered using Spring's `Ordered` or `@Order` when multiple initializers act on the context.

Example:

~~~java
import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.Ordered;

public final class ContextIdInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext>,
                   Ordered {

    @Override
    public int getOrder() {
        return 100;
    }

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        context.setId("catalog-" + context.getEnvironment()
                .getProperty("app.instance-id", "local"));
    }
}
~~~

Another initializer running later can read `context.getId()`. However, if both mutate the context ID, the result depends on ordering and implementation logic. Do not design a system where multiple initializers silently overwrite the same critical state.

**Important:** the order of an `ApplicationContextInitializer` only determines ordering **among initializers** within their own phase. It does not allow an initializer to "jump backward" ahead of Environment preparation merely by using `Ordered.HIGHEST_PRECEDENCE`.

Likewise, `Ordered` on an `EnvironmentPostProcessor` determines the order **of processors within the Environment phase**, not granting it access to a context that does not yet exist.

## 16. Relationship with `@PropertySource` and `@Value`

A developer might ask: "I just need to add a properties file, why not use `@PropertySource`?"

Example:

~~~java
@Configuration
@PropertySource("classpath:extra.properties")
public class ExtraPropertiesConfiguration {
}
~~~

`@PropertySource` is processed alongside configuration classes during the context processing phase. In Spring Boot, that can be **too late** for properties used right from the start, such as certain logging settings or `spring.main.*`.

In contrast, `EnvironmentPostProcessor` creates the property source during Environment preparation. If a custom source needs to be visible very early, this is the practical difference.

For an application bean:

~~~java
@Component
public class RegionReporter {

    public RegionReporter(
            @Value("${app.region:unknown}") String region) {
        System.out.println(region);
    }
}
~~~

the value of `app.region` can come from `@PropertySource`, `application.yml`, environment variables, or a source added by a processor, as long as it is effective by the time placeholders are resolved.

However, `@Value` succeeding **does not prove** the property was present early enough to affect Config Data. Choose your solution based on the **earliest consumer** that needs to read that key.

## 17. Do Not Inject Services into Early Startup Extension Points

### 17.1. In `EnvironmentPostProcessor`

Do not write a processor that relies on a `@Service` such as:

~~~java
public MyProcessor(RemoteConfigService remoteConfigService) {
    this.remoteConfigService = remoteConfigService;
}
~~~

and expect Spring Boot to inject it like a regular bean. Processors instantiated via SPI run at a stage when the application does not yet have a context ready for dependency injection.

In Spring Boot 3.x, if you truly need special startup support capabilities, constructor parameters such as `DeferredLogFactory` or `ConfigurableBootstrapContext` are supported within the scope of the corresponding API. This is **not** permission to arbitrarily inject any service bean.

### 17.2. In `ApplicationContextInitializer`

The initializer has a context reference, but the context **has not refreshed**, so you should also avoid fetching services via:

~~~java
// Do not do this inside initialize(...):
context.getBean(RemoteConfigService.class);
~~~

Bean definitions may not be loaded yet, the bean may not exist yet, or premature instantiation can cause unintended lifecycle behavior.

If you need to invoke a service after the application starts, consider `ApplicationRunner`, `CommandLineRunner`, a later-stage event listener, or an appropriate bean lifecycle hook.

### 17.3. Security and IO

Both extension points run during startup and can prevent the application from starting if an error occurs.

- Avoid network calls without timeouts.
- Avoid reading secrets and printing them to logs.
- Avoid mutating process-wide state such as `System.setProperty(...)` unnecessarily.
- Avoid creating files or mutating shared infrastructure without a control mechanism.
- When a required config source fails, choose an explicit fail-fast policy; when a source is optional, design an intentional fallback.

If integrating with a remote secret store is mandatory, consider a dedicated integration mechanism with Config Data or a framework-supported secret manager, rather than rolling a simple network processor that lacks retry and security contracts.

## 18. Logging in Very Early Stages

A processor might want to log to debug startup ordering:

~~~java
@Override
public void postProcessEnvironment(
        ConfigurableEnvironment environment,
        SpringApplication application) {
    // May run before the logging system is initialized.
}
~~~

However, logging can also be configured **from the Environment**. Using a regular logger too early may result in formats or levels that do not necessarily reflect the final configuration.

Spring Boot 3.x supports mechanisms such as `DeferredLogFactory` for certain environment processors to defer emitting log records until the environment/logger is ready:

~~~java
import org.springframework.boot.logging.DeferredLogFactory;
import org.apache.commons.logging.Log;

public final class LoggingAwareProcessor
        implements EnvironmentPostProcessor {

    private final Log log;

    public LoggingAwareProcessor(DeferredLogFactory factory) {
        this.log = factory.getLog(LoggingAwareProcessor.class);
    }

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application) {
        log.info("Environment extension is active");
    }
}
~~~

This is **special constructor injection provided by Boot for the SPI**, not regular bean DI. APIs/imports may vary by Boot version; consult the exact Javadoc of the version you are using.

In `ApplicationContextInitializer`, logging is usually further along in the startup lifecycle, though you should not assume every `logging.*` change made at this point will be reapplied by the logging system.

## 19. Unit Testing `EnvironmentPostProcessor`

For pure `PropertySource` handling, you can test the class directly without starting the entire application:

~~~java
package com.example.boot;

import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringApplication;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.StandardEnvironment;

import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

class RegionDefaultsEnvironmentPostProcessorTest {

    private final RegionDefaultsEnvironmentPostProcessor processor =
            new RegionDefaultsEnvironmentPostProcessor();

    @Test
    void addsFallbackWhenNoRegionIsProvided() {
        StandardEnvironment environment = new StandardEnvironment();

        processor.postProcessEnvironment(
                environment, new SpringApplication(Object.class));

        assertThat(environment.getProperty("app.region"))
                .isEqualTo("vn");
    }

    @Test
    void preservesHigherPriorityOverride() {
        StandardEnvironment environment = new StandardEnvironment();

        environment.getPropertySources().addFirst(
                new MapPropertySource(
                        "deployment",
                        Map.of("app.region", "apac")));

        processor.postProcessEnvironment(
                environment, new SpringApplication(Object.class));

        assertThat(environment.getProperty("app.region"))
                .isEqualTo("apac");
    }
}
~~~

These tests prove the **class logic** and precedence in an explicitly prepared environment. They **do not prove** that the real application has `spring.factories` at the right path/key or that the processor is invoked in the right order by `SpringApplication`.

To verify SPI registration, add an integration test that actually boots with `SpringApplication` or packages and runs the JAR.

## 20. Unit Testing `ApplicationContextInitializer`

Because the callback receives an unrefreshed context, you can create a context and invoke the initializer in a unit test:

~~~java
package com.example.boot;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.core.env.MapPropertySource;

import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

class InstanceIdContextInitializerTest {

    @Test
    void setsContextIdFromEnvironment() {
        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext();

        try {
            context.getEnvironment().getPropertySources().addFirst(
                new MapPropertySource("test", Map.of(
                        "app.instance-id", "zone-b-02")));

            new InstanceIdContextInitializer().initialize(context);

            assertThat(context.getId())
                    .isEqualTo("catalog-zone-b-02");
        }
        finally {
            context.close();
        }
    }
}
~~~

The test above does not need to instantiate all singleton beans. It shows that the initializer operates on a context object and can use the Environment already attached to the context.

Like the processor test, this unit test **does not by itself verify** that `SpringApplication.addInitializers(...)` or `spring.factories` is wired properly in the real application.

### 20.1. Full-Lifecycle Integration Test

When you need to verify both extension points working together, you can run a minimal `SpringApplication`:

~~~java
SpringApplication application =
        new SpringApplication(DemoApplication.class);

application.setWebApplicationType(WebApplicationType.NONE);
application.addInitializers(new InstanceIdContextInitializer());

try (ConfigurableApplicationContext context = application.run(
        "--app.instance-id=test-01")) {

    String region = context.getEnvironment()
            .getProperty("app.region");

    String id = context.getId();

    // Assert region and ID according to the design.
}
~~~

Imports needed for the example:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.context.ConfigurableApplicationContext;
~~~

If `RegionDefaultsEnvironmentPostProcessor` is properly registered in `spring.factories` on the test runtime classpath, Spring Boot can now trigger the processor during the Environment preparation step. The explicitly registered initializer will run when the context is created.

**Note:** `ApplicationContextRunner` is very useful for testing beans, but by default it does not go through the full `SpringApplication` lifecycle like a real Boot startup. If the test is meant to confirm that `EnvironmentPostProcessor`'s `spring.factories` entry is triggered automatically, using a real `SpringApplication` startup path is more reliable.

## 21. Diagnosing When an Extension Point Does Not Run

Some very common mistakes:

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `EnvironmentPostProcessor` is not called | Missing `META-INF/spring.factories` file or wrong key | Check classpath/JAR resources and the fully qualified interface name |
| Added `@Component` but does not run early | Component scan happens later | Register the processor via `spring.factories` SPI |
| `ClassNotFoundException` at startup | Wrong package/class name in factories | Cross-check compiled class and resource file |
| Processor runs but property does not win | Used `addLast` below a source with a conflicting value | Review precedence and choose source position according to intent |
| Processor runs twice and adds duplicate source | Non-idempotent logic or multiple registration methods | Check source name before adding |
| Values in `application.yml` cannot be read yet | Processor runs before Config Data processor | Specify order or choose an appropriate hook |
| `spring.config.location` set from initializer has no effect | Config Data has already been processed | Supply the property from an earlier source or design a Config Data SPI |
| Initializer does not run | `addInitializers` not called or wrong factories key | Register properly before `run` |
| Initializer calling `getBean` fails | Bean definitions/application not yet refreshed | Move logic to bean creation stage or post-refresh |
| Added listener but events are not seen | Listening to wrong event type or context | Check event type and the context publishing the event |
| Logging configuration does not reflect processor | Logger not yet configured at early stage | Look into `DeferredLogFactory` and timing |
| Works in IDE, fails in JAR | `spring.factories` not packaged into artifact | Inspect resources in build output/JAR |
| Using Boot 3.x imports in Boot 4.x fails | Packages/APIs changed | Check the exact version's Javadoc |
| Unexpected Context ID | Multiple initializers modifying ID or config override | Check initializer ordering and effective config sources |

When debugging, you can inspect non-sensitive `PropertySource` names:

~~~java
for (PropertySource<?> source
        : environment.getPropertySources()) {
    System.out.println(source.getName());
}
~~~

Do not print every `source.getProperty(...)`, as that can leak secrets. If using Actuator, `/actuator/env` or `/actuator/configprops` must be secured and have sensitive-data masking configured.

## 22. `EnvironmentPostProcessor`, `ApplicationListener`, and `ApplicationRunner`

These hooks should not be used interchangeably at random:

| Hook | When Appropriate | What Not to Expect |
| --- | --- | --- |
| `EnvironmentPostProcessor` | Add/customize Environment before context creation | Injecting business beans |
| `ApplicationContextInitializer` | Customize context before refresh | Retrieving initialized services as after refresh |
| `ApplicationListener<ApplicationEnvironmentPreparedEvent>` | Observe/handle Environment prepared event | Automatically having a created context |
| `BeanFactoryPostProcessor` | Adjust bean definitions during refresh | Directly replacing Config Data initialization |
| `ApplicationRunner` | Execute tasks after context refresh | Influencing which config files were loaded |

If you only want to **run a task after beans are ready**, `ApplicationRunner` or a post-refresh listener is simpler. If you want to **change config before beans are created**, choose an early extension point.

`ApplicationListener<ApplicationEnvironmentPreparedEvent>` can access the Environment at an early point, but `EnvironmentPostProcessor` is the dedicated contract for processing the Environment and follows Spring Boot's designed processor ordering.

## 23. Spring Boot 3.x and 4.x Compatibility Notes

The examples in the main sections target **Spring Boot 3.3–3.5** with:

~~~java
org.springframework.boot.env.EnvironmentPostProcessor
~~~

and the `spring.factories` key:

~~~properties
org.springframework.boot.env.EnvironmentPostProcessor=com.example.boot.RegionDefaultsEnvironmentPostProcessor
~~~

In **Spring Boot 4.x**, this API is progressively moved to a different namespace, with the interface `org.springframework.boot.EnvironmentPostProcessor` in newer versions. Some older packages may still exist in deprecated form during the transition period.

Therefore, if your project uses Boot 4.x, check the **Javadoc and migration guide for the exact version you are running** and update your imports and `spring.factories` key accordingly. Do not use a Boot 3.x example verbatim with Boot 4.x simply because the short interface name is the same.

Conversely, `ApplicationContextInitializer` belongs to Spring Framework:

~~~java
org.springframework.context.ApplicationContextInitializer
~~~

It is not the same interface as `EnvironmentPostProcessor`, even in newer Boot versions.

The lifecycle concepts in this article remain useful: one extension point processes the Environment early; one extension point initializes the Context before refresh. However, **class/package names and SPI registration must follow your version**.

## 24. Practice Exercises

### Exercise 1: Choosing an Extension Point

The system needs to add `app.region=vn` as a **fallback**, while allowing deployments to override it with `APP_REGION=apac`.

**Answer:** `EnvironmentPostProcessor` with a `MapPropertySource` added using `addLast`, or another default configuration mechanism if a processor is unnecessary. Do not use `addFirst` for a fallback.

### Exercise 2: Distinguishing Property Source from Context State

The system wants to set the context ID to `catalog-zone-c-03` based on the property `app.instance-id=zone-c-03`.

**Answer:** `ApplicationContextInitializer` receives `ConfigurableApplicationContext`, reads `context.getEnvironment()`, and then calls `context.setId(...)`.

### Exercise 3: Identifying a Stage That Is Too Late

An initializer adds:

~~~java
context.getEnvironment().getPropertySources().addFirst(
        new MapPropertySource("late", Map.of(
                "spring.config.location",
                "file:/etc/catalog/")));
~~~

Should you expect Spring Boot to reload all of `application.yml` from the new location?

**Answer:** No. The initializer runs **after** the normal Environment and Config Data preparation phases. Adding the property afterward does not by default trigger reprocessing of config locations.

### Exercise 4: Checking Ordering

An `EnvironmentPostProcessor` is given a low order value to read `app.name` from YAML, yet runs before the Config Data processor.

**Answer:** Do not rely on an arbitrary order number. Check `ConfigDataEnvironmentPostProcessor.ORDER` and set the order appropriately, or move the requirement to a more suitable extension point. When values from YAML are needed, it must run after YAML has been loaded.

### Exercise 5: SPI Registration

This `spring.factories` snippet:

~~~properties
org.springframework.context.ApplicationContextInitializer=com.example.boot.RegionDefaultsEnvironmentPostProcessor
~~~

Is it correct?

**Answer:** Incorrect, because the key belongs to `ApplicationContextInitializer` while the class implements `EnvironmentPostProcessor`. In Boot 3.x, the correct key is `org.springframework.boot.env.EnvironmentPostProcessor`.

### Exercise 6: Acting on Beans Too Early

Inside `initialize(context)`:

~~~java
PaymentService service = context.getBean(PaymentService.class);
service.warmUp();
~~~

Why is this dangerous?

**Answer:** The context has not refreshed and bean definitions may not be loaded yet. Fetching a bean now can fail or cause abnormal lifecycle behavior. Move the warm-up action to a stage after beans are ready, with clear timeouts and failure policies.

### Exercise 7: Coordinating Two Extension Points

Given the file:

~~~yaml
app:
  instance-id: node-07
  audit:
    enabled: true
~~~

The processor adds fallback:

~~~properties
app.region=vn
app.audit.enabled=false
~~~

The initializer sets:

~~~java
context.setId("catalog-" + context.getEnvironment()
        .getProperty("app.instance-id", "local"));
~~~

Assuming no other higher-precedence sources exist, the expected result is:

~~~text
app.region        = vn
app.audit.enabled = true
context ID        = catalog-node-07
~~~

Reason: the `addLast` fallback source does not override `app.audit.enabled=true` in YAML; the initializer reads `app.instance-id` and updates the context's state.

## 25. Implementation Checklist

Before introducing an extension point into a real application:

1. **Identify the earliest consumer** that needs the property or context state. Does that consumer run before or after Config Data processing?
2. **Choose the right interface:** `EnvironmentPostProcessor` for `Environment`, `ApplicationContextInitializer` for the context.
3. **Register via the proper mechanism:** `spring.factories` for processors; `addInitializers` or `spring.factories` for initializers.
4. **Check your Spring Boot version:** Boot 3.x and Boot 4.x packages can differ.
5. **Set precedence intentionally:** `addLast` for fallbacks; `addFirst` only when a true override is needed.
6. **Design idempotently:** check the `PropertySource` name before adding, and avoid unintentional repeated side effects.
7. **Do not depend on late-created beans:** do not access repositories/services in either early phase.
8. **Do not treat an Initializer as a Config Data resolver:** adding `spring.config.*` late does not reload files.
9. **Do not log secrets:** log only non-sensitive metadata or state.
10. **Test at two layers:** unit tests for logic and integration tests verifying SPI registration/lifecycle.
11. **Keep startup operations fast and deterministic:** avoid long network/blocking calls or uncontrolled shared-state mutations.
12. **Document the contract:** state clearly what source the processor adds, its precedence, default values, and how to override them in deployment.

## 26. Key Takeaways

- **`EnvironmentPostProcessor`** (Spring Boot) modifies `ConfigurableEnvironment` during configuration preparation, before creating the `ApplicationContext`.
- **`ApplicationContextInitializer`** (Spring Framework) modifies a `ConfigurableApplicationContext` that has been created but **not yet refreshed**.
- Both **can add a `PropertySource`**, but they differ in **timing** and **target object**. Properties used for Config Data or early logging should not be added late inside an initializer.
- In **Boot 3.x**, `EnvironmentPostProcessor` is registered via `META-INF/spring.factories` under the key `org.springframework.boot.env.EnvironmentPostProcessor`.
- `ApplicationContextInitializer` can be registered via `SpringApplication.addInitializers(...)` or `spring.factories` under the key `org.springframework.context.ApplicationContextInitializer`.
- Do not use `@Component` as a substitute for early SPI registration.
- Use `Ordered` or `@Order` for ordering **within each phase**; do not confuse ordering with changing the fundamental lifecycle.
- Use `addLast` for fallbacks and clearly understand precedence when adding custom sources.
- Do not retrieve business beans in early startup extension points.
- If loading configuration from a custom location, consider the **Config Data SPI** instead of handling everything through a manual processor.

### References

- Spring Boot 3.5 — Externalized Configuration: https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html
- Spring Boot 3.5 — SpringApplication lifecycle/events: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
- Spring Boot 3.5 API — EnvironmentPostProcessor: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/env/EnvironmentPostProcessor.html
- Spring Boot 3.5 API — ConfigDataEnvironmentPostProcessor: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/config/ConfigDataEnvironmentPostProcessor.html
- Spring Boot 3.5 API — SpringApplication: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/SpringApplication.html
- Spring Framework API — ApplicationContextInitializer: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/ApplicationContextInitializer.html
- Spring Boot 4.x API — EnvironmentPostProcessor: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/EnvironmentPostProcessor.html
