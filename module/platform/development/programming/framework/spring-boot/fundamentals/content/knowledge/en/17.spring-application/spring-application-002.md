# Preparing the Environment Before Creating the ApplicationContext

Spring Boot needs to know which configuration is in effect before creating and wiring beans. The application must determine which profiles are enabled, which configuration files are loaded, which properties override others, what web type the application runs as, and which values must be available from the very beginning. Spring Boot gathers all of this information into the **Environment** before creating the ApplicationContext.

Preparing the Environment before creating the ApplicationContext ensures startup decisions are made at the right time. For example, Spring Boot needs to know whether the application is servlet web, reactive web, or non-web in order to choose the appropriate ApplicationContext type. It also needs to read settings like `spring.config.import`, `spring.profiles.active`, or logging configuration before bean creation begins.

This lesson explains the role of the Environment, the related startup order, how property sources and profiles are loaded, and the extension points for modifying the Environment early. The focus is on distinguishing **modifying the Environment before context creation** from **changing configuration after the context already exists**, because these two points in time do not have the same effect.

## 1. What is the Environment?

`Environment` is Spring's abstraction for accessing the active configuration and profiles in an application. It provides two key groups of information:

- **Properties:** configuration values such as URLs, timeouts, ports, feature flags, database names, or logging levels.
- **Profiles:** groups of configuration or beans suited to a specific environment or execution mode such as `dev`, `test`, `staging`, or `prod`.

A component can read properties through:

~~~java
String region = environment.getProperty("app.region");
int timeout = environment.getProperty(
        "app.http.timeout",
        Integer.class,
        5
);
~~~

`Environment` is neither a single YAML file nor a single configuration object. It is the unified interface combining multiple configuration sources and providing value resolution rules.

### Environment and ConfigurableEnvironment

`Environment` primarily exposes an API for reading properties and checking profiles. During bootstrap, Spring typically works with `ConfigurableEnvironment`, which allows modifying property sources and profiles.

Common operations:

~~~java
ConfigurableEnvironment environment = ...;

environment.getProperty("app.region");
environment.getActiveProfiles();
environment.getDefaultProfiles();
environment.setActiveProfiles("dev");
environment.addActiveProfile("metrics");
~~~

`ConfigurableEnvironment` also provides access to `MutablePropertySources` to add, replace, or reorder configuration sources.

### How does Environment differ from ApplicationContext?

| Component | Primary Responsibility |
|---|---|
| `Environment` | Provides properties and profiles |
| `PropertySource` | Represents a specific property source |
| `ApplicationContext` | Manages beans, dependency injection, lifecycle, events, and resources |
| `BeanFactory` | Core mechanism for creating and providing beans |
| `ConfigurableApplicationContext` | ApplicationContext configurable before/after refresh |

The Environment becomes part of the ApplicationContext once the context is created, but Spring Boot can prepare the Environment **before creating the context**. That allows bootstrap decisions to use already-available configuration.

## 2. Why Prepare the Environment Before the ApplicationContext?

Consider an application with this configuration:

~~~yaml
spring:
  main:
    web-application-type: servlet
  profiles:
    active: prod

server:
  port: 8082
~~~

Before creating beans, Spring Boot needs to know several things:

- Which profiles are active so configurations annotated with `@Profile("prod")` are considered.
- The application type in order to select the appropriate context.
- Which property sources need to be loaded.
- Which configuration files need to be imported.
- Which bootstrap settings must be present before refreshing the context.

If the context were created before this information is ready, Spring could choose the wrong context type or parse configuration for an unintended environment.

Conceptual flow:

~~~text
SpringApplication.run(args)
          |
          v
Create BootstrapContext and RunListeners
          |
          v
Prepare Environment
  - create/select Environment
  - add initial configuration sources
  - read command-line arguments
  - process Config Data and profiles
  - apply EnvironmentPostProcessors
          |
          v
EnvironmentPrepared
          |
          v
Create appropriate ApplicationContext
          |
          v
Run ApplicationContextInitializers
          |
          v
Load configuration sources
          |
          v
Refresh ApplicationContext
  - parse @Configuration
  - component scan and @Import
  - register bean definitions
  - create beans and inject dependencies
          |
          v
ApplicationStarted / ApplicationReady
~~~

This is a high-level model. Some listeners and EnvironmentPostProcessors are invoked via events during the Environment preparation phase; Config Data has its own processing pipeline and can trigger loading additional configuration/profiles. Still, the core principle remains unchanged: **Spring Boot completes the necessary Environment preparation before creating the ApplicationContext**.

### An obvious example: choosing the ApplicationContext type

Spring Boot can run under different application types:

- `SERVLET`: Servlet-based web application, typically using Spring MVC.
- `REACTIVE`: reactive web application, typically using Spring WebFlux.
- `NONE`: application that does not start a web server.

It can be specified via property:

~~~yaml
spring:
  main:
    web-application-type: reactive
~~~

Or in Java:

~~~java
SpringApplication application =
        new SpringApplication(StoreApplication.class);

application.setWebApplicationType(
        WebApplicationType.REACTIVE
);
~~~

The application type determines which ApplicationContext class Spring Boot creates and which auto-configurations apply. This is a bootstrap decision, so it must be determined before the context is created.

## 3. How Does SpringApplication Prepare the Environment?

In a standard application:

~~~java
@SpringBootApplication
public class StoreApplication {

    public static void main(String[] args) {
        SpringApplication.run(StoreApplication.class, args);
    }
}
~~~

`SpringApplication.run(...)` coordinates the startup process. The Environment-related steps can be summarized as follows:

1. Create or use an Environment suitable for the application type.
2. Configure initial property sources.
3. Add command-line arguments into the Environment if enabled.
4. Prepare profiles and startup properties.
5. Publish the Environment prepared event so listeners and EnvironmentPostProcessors can participate.
6. Load Config Data such as `application.properties`, `application.yml`, profile-specific files, and imports.
7. After the Environment is prepared, create the ApplicationContext.
8. Attach the Environment to the context and proceed with configuration/bean processing.

In Spring Boot's implementation, several of these steps are coordinated through `SpringApplicationRunListeners` and `EnvironmentPostProcessorApplicationListener`. You do not need to invoke each step manually in a typical application; `SpringApplication` executes them as part of its lifecycle.

### Observing startup milestones

Representative application events:

| Event | General Timing | Purpose |
|---|---|---|
| `ApplicationStartingEvent` | Very early, before the Environment is fully prepared | Signals the application has begun starting |
| `ApplicationEnvironmentPreparedEvent` | Environment is being prepared | Allows early configuration processing |
| `ApplicationContextInitializedEvent` | Context has been created and initializers have run | Signals the context has been initialized |
| `ApplicationPreparedEvent` | Context has loaded configuration sources, before refresh | Signals the context is ready to refresh |
| `ApplicationStartedEvent` | After context refresh succeeds | Application has started |
| `ApplicationReadyEvent` | After startup runner steps complete | Application is ready to accept work |
| `ApplicationFailedEvent` | When startup fails | Signals an error during startup |

These event names and ordering reflect the modern Spring Boot lifecycle; details may differ across older Boot generations. An event being published at a milestone does not guarantee all custom listeners have finished if listener ordering is configured differently.

## 4. PropertySource: Environment Combines Multiple Configuration Sources

A `PropertySource` represents a key-value source. Examples:

- Default values declared by the application.
- `application.properties` or `application.yml` files.
- Profile-specific configuration files.
- Operating system environment variables.
- JVM system properties.
- Command-line arguments.
- Custom configuration sources added by the application or libraries.

Example of a map-backed source in Java:

~~~java
Map<String, Object> values = Map.of(
        "app.region", "ap-southeast",
        "app.feature.catalog", true
);

PropertySource<?> source =
        new MapPropertySource("runtimeDefaults", values);
~~~

This source is named `runtimeDefaults` and provides the corresponding properties. Once added to `MutablePropertySources`, the Environment can resolve those values.

### PropertySource has precedence ordering

When multiple sources contain the same key, the source with higher precedence is used first. With `MutablePropertySources`, a source's position in the list matters:

~~~java
environment.getPropertySources().addFirst(source);
~~~

`addFirst` places the source at the front of the list, giving it high priority during property lookup.

~~~java
environment.getPropertySources().addLast(source);
~~~

`addLast` places the source at the end of the list, suitable for low-priority default values.

For example, if multiple sources define `app.region`:

~~~text
commandLineArgs: app.region=eu-west
systemEnvironment: APP_REGION=ap-southeast
application.yml: app.region=ap-southeast
runtimeDefaults: app.region=local
~~~

The final resolved value depends on the actual property source order in the Environment. Do not look at a single YAML file alone to conclude what the effective property value is.

### Precedence order in Spring Boot

Spring Boot follows property source precedence rules. In practical terms:

- Default properties normally have low precedence.
- Config Data from configuration files is loaded into the Environment.
- Environment variables and JVM system properties can override configuration files.
- Command-line arguments typically have higher precedence than standard file configuration sources.
- Test property sources can take high precedence in testing contexts.

The exact order also includes specialized sources such as JSON application properties, JNDI, servlet init parameters, test annotations, and DevTools. When diagnosing precisely, inspect the actual `PropertySource` order rather than memorizing an abbreviated list.

### Default values should not override deployment configuration

If a library adds default properties, it should usually use `addLast` so operators can override them via files, environment variables, or the command line.

Example:

~~~java
Map<String, Object> defaults = Map.of(
        "app.retry.max-attempts", 3,
        "app.retry.backoff", "500ms"
);

environment.getPropertySources().addLast(
        new MapPropertySource("retryDefaults", defaults)
);
~~~

This is how fallback values are provided. Using `addFirst` for defaults could accidentally prevent deployment configuration supplied by the user from taking effect.

## 5. Config Data: Loading application.properties and application.yml

Since Spring Boot 2.4, the Config Data mechanism is the standard way to load configuration from files and import configuration sources. Common files include:

- `application.properties`
- `application.yml`
- `application-{profile}.properties`
- `application-{profile}.yml`

Example directory layout:

~~~text
src/main/resources/
├── application.yml
├── application-dev.yml
└── application-prod.yml
~~~

Default file:

~~~yaml
app:
  name: store-service
  feature:
    catalog: true
~~~

Dev file:

~~~yaml
app:
  endpoint:
    payment: http://localhost:8085
~~~

Prod file:

~~~yaml
app:
  endpoint:
    payment: https://payments.example.internal
~~~

When the `dev` profile is active, Spring Boot loads the configuration appropriate for that profile. Property sources are combined by precedence; profile-specific files can override general values according to Config Data rules.

### Specifying configuration files

Important bootstrap properties:

| Property | Purpose |
|---|---|
| `spring.config.name` | Changes the base name of configuration files to search for |
| `spring.config.location` | Specifies configuration locations; can replace default locations |
| `spring.config.additional-location` | Adds locations alongside the default locations |
| `spring.config.import` | Imports additional configuration sources |
| `spring.config.on-not-found` | Controls how missing locations are handled under Config Data |

Example adding an extra location:

~~~bash
java -jar store.jar --spring.config.additional-location=optional:file:./config/
~~~

`additional-location` appends an external configuration directory. The `optional:` prefix allows the application to continue if the optional location does not exist, depending on syntax and location type.

If using `spring.config.location`, remember that it can replace the default list of locations. If your goal is merely to add external configuration while keeping the defaults, `spring.config.additional-location` is usually what you want.

### Importing configuration files

Example in `application.yml`:

~~~yaml
spring:
  config:
    import: optional:file:./config/partner.yml
~~~

Spring Boot imports the additional configuration source via the Config Data mechanism. An imported configuration can be a file, a location, or a supported source type such as a config tree.

### Config tree for deployment-mounted configuration

Some deployment platforms mount secrets or configuration as files. You can use a config tree:

~~~yaml
spring:
  config:
    import: optional:configtree:/run/secrets/
~~~

Each file in the directory can be mapped to a property. This is useful when the deployment environment supplies secrets as files. Make sure directory permissions are protected and avoid printing secrets to logs or management endpoints.

### Config Data is loaded early

Config Data is a crucial part of preparing the Environment. Properties like `spring.config.import` or profile activation must be processed early enough for Spring to know which configuration sources to load before creating the ApplicationContext and analyzing beans.

## 6. Profiles: Selecting Configuration by Environment

A profile is a label used to activate a group of configurations or beans. Example:

~~~java
@Configuration
@Profile("dev")
public class DevelopmentConfiguration {
    // Beans exclusively for the dev environment.
}
~~~

~~~java
@Configuration
@Profile("prod")
public class ProductionConfiguration {
    // Beans exclusively for the production environment.
}
~~~

Spring evaluates `@Profile` during configuration processing based on the prepared Environment.

### Activating profiles via property

In `application.yml`:

~~~yaml
spring:
  profiles:
    active: dev
~~~

Or at runtime:

~~~bash
java -jar store.jar --spring.profiles.active=prod
~~~

Multiple profiles can be enabled:

~~~bash
java -jar store.jar --spring.profiles.active=prod,metrics
~~~

When multiple profiles are active together, their configurations can all apply; if multiple beans of the same type are registered, clear selection rules must be in place.

### Default profile

If no active profile is specified, Spring uses the default profile (usually named `default`). It can be changed:

~~~yaml
spring:
  profiles:
    default: local
~~~

The default profile is used only when no active profile applies. Once a specific profile is activated, the default profile is not necessarily included in the active list.

### Including additional profiles

Additional profiles can be appended to the active list:

~~~yaml
spring:
  profiles:
    include:
      - common
      - observability
~~~

`spring.profiles.include` allows adding profiles beyond the initial active profiles. Rules for processing includes relate to Config Data and declaration placement; you should not place this property arbitrarily inside a document that is itself conditionally activated by another profile.

### Profile groups

Profile groups allow one profile name to represent a group of profiles:

~~~yaml
spring:
  profiles:
    group:
      production:
        - prod-database
        - prod-security
        - observability
~~~

When `production` is activated, its member profiles are included according to group rules. This keeps startup commands shorter and avoids listing many profiles on every deployment.

### Profile activation in Config Data

You can tie a configuration document to a profile:

~~~yaml
spring:
  config:
    activate:
      on-profile: dev

app:
  endpoint:
    payment: http://localhost:8085
~~~

This document is applied only when the matching profile is active. `spring.config.activate.on-profile` is a document activation condition; it differs from declaring `spring.profiles.active` to select profiles.

Certain profile properties such as `spring.profiles.active`, `spring.profiles.default`, `spring.profiles.include`, and `spring.profiles.group` have specific placement rules in Config Data; they cannot be placed arbitrarily inside a document already gated by a profile condition. When configuring complex profiles, keep documents cleanly separated and verify the rules for your Spring Boot version.

## 7. Command-Line Arguments and SpringApplication

Spring Boot builds `ApplicationArguments` from command-line parameters. For option-style arguments:

~~~bash
java -jar store.jar --app.region=ap-southeast --spring.profiles.active=prod
~~~

option values can be added to the Environment as a command-line property source if that feature is enabled.

Arguments can be read in a runner:

~~~java
@Component
public class StartupReporter implements ApplicationRunner {

    private final Environment environment;

    public StartupReporter(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(
                "Active profiles: "
                        + String.join(",", environment.getActiveProfiles())
        );
    }
}
~~~

`ApplicationRunner` executes after the context has refreshed; this is an example of inspecting the Environment at runtime, not an extension point for altering bootstrap properties before context creation.

### Customizing SpringApplication in Java

You can create a `SpringApplication` instance and configure it before calling `run`:

~~~java
public static void main(String[] args) {
    SpringApplication application =
            new SpringApplication(StoreApplication.class);

    application.setDefaultProperties(Map.of(
            "app.region", "local",
            "app.retry.max-attempts", "3"
    ));

    application.setAdditionalProfiles("metrics");

    application.run(args);
}
~~~

`setDefaultProperties` adds low-precedence default values. `setAdditionalProfiles` appends profiles. Values from files, environment variables, or the command line can still override defaults according to precedence.

Other useful APIs:

~~~java
application.setAddCommandLineProperties(false);
application.setWebApplicationType(WebApplicationType.SERVLET);
application.addInitializers(new StoreContextInitializer());
application.addListeners(new StartupListener());
~~~

- `setAddCommandLineProperties(false)` disables converting option arguments into a property source.
- `setWebApplicationType(...)` specifies the application type.
- `addInitializers(...)` registers an ApplicationContextInitializer.
- `addListeners(...)` registers a listener.

Only disable command-line properties if the application has a clear reason; otherwise, operators lose a helpful configuration mechanism.

### Using SpringApplicationBuilder

For fluent configuration:

~~~java
new SpringApplicationBuilder(StoreApplication.class)
        .profiles("dev")
        .properties(
                "app.region=local",
                "app.feature.catalog=true"
        )
        .run(args);
~~~

`SpringApplicationBuilder` can be useful when an application needs to configure multiple contexts or configure startup programmatically. For a simple application, `SpringApplication.run(...)` remains a concise choice.

## 8. EnvironmentPostProcessor: Modifying the Environment Before Context Creation

`EnvironmentPostProcessor` is a Spring Boot extension point for customizing the Environment during the bootstrap phase. It is called while the Environment is being prepared, before the ApplicationContext is created.

Interface:

~~~java
public interface EnvironmentPostProcessor {
    void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application
    );
}
~~~

An implementation can add property sources, modify active profiles, or compute configuration values based on available information.

### Example: adding a default property source

~~~java
package com.example.store.bootstrap;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.Ordered;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;

public class StoreEnvironmentPostProcessor
        implements EnvironmentPostProcessor, Ordered {

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application
    ) {
        Map<String, Object> defaults = Map.of(
                "app.region", "local",
                "app.retry.max-attempts", 3
        );

        environment.getPropertySources().addLast(
                new MapPropertySource("storeBootstrapDefaults", defaults)
        );
    }

    @Override
    public int getOrder() {
        return Ordered.LOWEST_PRECEDENCE;
    }
}
~~~

The `storeBootstrapDefaults` source is added at the end of the list, acting as a fallback. If an operator supplies `app.region` in application config, an environment variable, or the command line, the higher-precedence source takes effect.

If a customizer needs higher priority, a different position can be chosen, but consider the impact on overriding deployment configuration. Do not use `addFirst` for defaults carelessly.

### Registering EnvironmentPostProcessor

In Spring Boot generations supporting this mechanism, register the implementation via:

`META-INF/spring.factories`:

~~~properties
org.springframework.boot.env.EnvironmentPostProcessor=\
com.example.store.bootstrap.StoreEnvironmentPostProcessor
~~~

This is Boot's extension-point registration mechanism. It differs from annotating a class with `@Component`: an EnvironmentPostProcessor must be discovered during bootstrap, before ApplicationContext component scanning takes place.

### When should you use EnvironmentPostProcessor?

Appropriate when you need to:

- Add a property source before the context is created.
- Prepare properties from a supported bootstrap source.
- Compute early configuration based on the available environment.
- Integrate external configuration into the startup process.
- Provide defaults or metadata for subsequent configuration steps.

You should not use it to create business services, query databases, call external APIs, or perform tasks requiring bean dependencies. EnvironmentPostProcessor runs before the ApplicationContext is ready; it is not a normal Spring service.

### Ordering of EnvironmentPostProcessors

You can implement `Ordered` or use appropriate ordering annotations to specify relative order. This matters when one processor needs to read a property provided by another processor, or needs to run before/after Config Data.

Do not guess the order value. Check the order of related processors in the Spring Boot version you are using and verify the resulting property sources. If a processor needs to read loaded application config, it must be ordered appropriately after the Config Data step; if it runs before, config files may not have been loaded yet.

A processor that only adds fallback defaults can normally use a low-precedence source and an appropriate order. A processor performing specialized integration should document its intended ordering.

## 9. ApplicationContextInitializer: Modifying the Context After Creation but Before Refresh

`ApplicationContextInitializer<C>` is another extension point:

~~~java
public interface ApplicationContextInitializer<C extends ConfigurableApplicationContext> {
    void initialize(C applicationContext);
}
~~~

Initializers are invoked after the ApplicationContext has been created, but before context refresh and before standard beans are instantiated.

Example:

~~~java
package com.example.store.bootstrap;

import java.util.Map;
import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.MapPropertySource;

public class StoreContextInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(
            ConfigurableApplicationContext context
    ) {
        Map<String, Object> values = Map.of(
                "app.context-label", "store-web"
        );

        context.getEnvironment().getPropertySources().addLast(
                new MapPropertySource("storeContextDefaults", values)
        );
    }
}
~~~

Registering from main:

~~~java
public static void main(String[] args) {
    SpringApplication application =
            new SpringApplication(StoreApplication.class);

    application.addInitializers(new StoreContextInitializer());
    application.run(args);
}
~~~

An initializer can access the context, Environment, and certain configuration metadata. It is suitable when you need to prepare the context prior to refresh—such as adding a property source, registering configurations, or customizing the context.

### How does EnvironmentPostProcessor differ from ApplicationContextInitializer?

| Criterion | EnvironmentPostProcessor | ApplicationContextInitializer |
|---|---|---|
| Timing | During Environment preparation, before ApplicationContext | After context is created, before refresh |
| Does ApplicationContext exist yet? | No | Yes |
| Receives | Environment and SpringApplication | ConfigurableApplicationContext |
| Suited for | Bootstrap properties, Config Data integration, early profiles | Customizing context/Environment before loading beans |
| Common registration | `spring.factories` under EnvironmentPostProcessor key | `SpringApplication.addInitializers` or initializer registration mechanism |
| Can use initialized business beans? | No | Standard beans are not initialized yet |

If a value must influence ApplicationContext type selection or Config Data loading, `EnvironmentPostProcessor` is usually the right phase. If you need to interact with a created-but-unrefreshed context, use an initializer.

### Initializers are not the place to change every bootstrap property

By the time an initializer runs, Spring Boot has already prepared the Environment and selected/created the ApplicationContext. Modifying properties in an initializer can affect beans and configuration processed during refresh, but it cannot turn back time to alter already-completed decisions such as context type or earlier Config Data loading steps.

## 10. ApplicationListener and ApplicationEnvironmentPreparedEvent

You can listen for Spring Boot events. Example:

~~~java
public class EnvironmentPreparedListener
        implements ApplicationListener<ApplicationEnvironmentPreparedEvent> {

    @Override
    public void onApplicationEvent(
            ApplicationEnvironmentPreparedEvent event
    ) {
        ConfigurableEnvironment environment = event.getEnvironment();

        String region = environment.getProperty("app.region");
        // Observe the value during the Environment prepared phase.
    }
}
~~~

Listeners can be added to SpringApplication:

~~~java
SpringApplication application =
        new SpringApplication(StoreApplication.class);

application.addListeners(new EnvironmentPreparedListener());
application.run(args);
~~~

However, event-observing listeners and EnvironmentPostProcessors serve different roles. If the goal is to add a property source via a dedicated extension point, EnvironmentPostProcessor usually expresses that intent more clearly.

### Be careful with listener ordering

Multiple listeners may react to the same event. Their order determines whether one listener sees a property source added by another listener. If you must modify the Environment, use extension points and ordering designed for bootstrap rather than relying on implicit listener order.

Do not create or retrieve beans from the ApplicationContext inside `ApplicationEnvironmentPreparedEvent`, because the context has not been created yet. A listener can observe the Environment and perform appropriate bootstrap tasks, but it should not assume context dependency injection is available.

## 11. @PropertySource: Why Might It Be Too Late for Bootstrap Configuration?

A Spring configuration class can add a property source using:

~~~java
@Configuration
@PropertySource("classpath:custom.properties")
public class CustomPropertiesConfiguration {
}
~~~

This mechanism is processed when Spring parses configuration classes—that is, after the ApplicationContext has been created and refresh has started.

Therefore, `@PropertySource` can supply properties for beans and configurations processed afterward, but it is **not suitable for configuring properties that must be known before the context is created or before Config Data is loaded**.

Examples of bootstrap property groups:

- `spring.config.name`
- `spring.config.location`
- `spring.config.additional-location`
- `spring.config.import`
- Certain `spring.main.*` properties
- Early logging configuration

If you want to select configuration files, import a config tree, or determine profiles early, use a bootstrap configuration source supported by Spring Boot such as command-line arguments, environment variables, system properties, Config Data, or `EnvironmentPostProcessor`.

### When is @PropertySource still appropriate?

It can be suitable when an application has an auxiliary properties file whose values only need to be consumed during bean/configuration creation after context refresh begins.

Example:

~~~properties
app.invoice.prefix=INV
app.invoice.max-lines=100
~~~

~~~java
@Configuration
@PropertySource("classpath:invoice.properties")
public class InvoiceConfiguration {

    @Bean
    public InvoiceFormatter invoiceFormatter(
            Environment environment
    ) {
        String prefix = environment.getProperty(
                "app.invoice.prefix",
                "DOC"
        );

        return new InvoiceFormatter(prefix);
    }
}
~~~

If these properties do not need to drive bootstrap decisions, `@PropertySource` can be a valid option. If the project already uses Config Data, you can often place them in `application.yml` or import the configuration file to unify the loading mechanism.

## 12. Properties Needed Early vs. Properties That Can Be Read Later

Not every property needs to be known before the ApplicationContext is created.

| Configuration Group | Example | When Needed |
|---|---|---|
| Application type selection | `spring.main.web-application-type` | Before context creation |
| Config file/location selection | `spring.config.name`, `spring.config.location` | During Config Data bootstrap |
| Profile activation | `spring.profiles.active` | Before processing `@Profile` configurations |
| Logging bootstrap | `logging.config`, certain `logging.*` | Very early in startup |
| Bean configuration | `app.payment.timeout` | Before the corresponding bean is bound/created |
| Server port | `server.port` | When configuring the embedded server, after Environment has the value |
| Business feature flag | `app.feature.catalog-enabled` | Before conditional beans or corresponding logic need to read it |
| Request data | `customerId`, `orderId` | At runtime via parameters, not bootstrap Environment |

Rule of thumb: properties affecting **configuration source selection or context type** must come from an early source. Properties used only when creating a bean can be read later, provided they are present before that bean is initialized or bound.

### ConfigurationProperties and Environment

A typed configuration class:

~~~java
@ConfigurationProperties(prefix = "app.payment")
public class PaymentProperties {
    private Duration timeout = Duration.ofSeconds(3);

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
~~~

It can be registered via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`. Spring binds properties from the Environment into the object when the corresponding bean configuration is processed.

YAML example:

~~~yaml
app:
  payment:
    timeout: 5s
~~~

Typed properties work well for configuration with multiple fields, validation, and metadata. They do not replace the Environment; they are a way to bind a group of properties from the Environment into a typed object.

## 13. Custom Environment and Programmatic Property Source Modification

In certain specialized applications, you can create a custom Environment and pass it to SpringApplication:

~~~java
ConfigurableEnvironment environment =
        new StandardEnvironment();

Map<String, Object> values = Map.of(
        "app.region", "local"
);

environment.getPropertySources().addFirst(
        new MapPropertySource("bootstrapOverrides", values)
);

SpringApplication application =
        new SpringApplication(StoreApplication.class);

application.setEnvironment(environment);
application.run(args);
~~~

This approach gives you control over the Environment before startup. However, you must pick an Environment compatible with the application type and understand how Spring Boot subsequently configures, converts, or adds property sources. Replacing the Environment manually can lose default behavior if the wrong type is chosen.

For web applications, Spring provides dedicated Environments for servlet/reactive contexts. In most cases, you should let Spring Boot create the appropriate Environment and supplement properties via default properties or an `EnvironmentPostProcessor`.

### Where to insert a property source?

Several options:

~~~java
environment.getPropertySources().addFirst(source);
environment.getPropertySources().addLast(source);
environment.getPropertySources().addBefore("systemEnvironment", source);
environment.getPropertySources().addAfter("systemEnvironment", source);
~~~

`addBefore` and `addAfter` require the anchor property source name to exist. If that name is absent, the operation can fail. Inspect the current list before positioning relatively.

### Do not modify the Environment after beans have bound and expect automatic updates

Some beans read properties in their constructor or are bound into `@ConfigurationProperties` during context initialization. If you modify a property source afterward, already-created objects are not automatically re-bound.

The Environment may reflect the new value when queried directly, while a bean holding a value already copied into a field keeps the old value. If runtime configuration refresh is needed, you must use an explicit refresh/rebind mechanism rather than merely adding a property source and assuming every bean updates.

## 14. Property Source Ordering and Practical Override Example

Suppose an application has:

`application.yml`:

~~~yaml
app:
  payment:
    timeout: 3s
    endpoint: https://sandbox-payments.example
~~~

Environment variable:

~~~bash
APP_PAYMENT_TIMEOUT=8s
~~~

Command line:

~~~bash
java -jar store.jar --app.payment.endpoint=https://payments.example
~~~

The effective values can be:

- Timeout: 8 seconds from the environment variable, if that source has higher precedence than the config file.
- Endpoint: the URL from the command line, which typically has higher precedence than the config file.
- Other properties not overridden continue to come from YAML.

This is why a single configuration file does not always represent the complete runtime configuration. In production, properties can come from environment variables, secret stores, command-line arguments, or a config server.

### Setting defaults in code that can be overridden

If an `EnvironmentPostProcessor` adds:

~~~java
environment.getPropertySources().addLast(
        new MapPropertySource(
                "appDefaults",
                Map.of("app.payment.timeout", "2s")
        )
);
~~~

then `2s` acts as a fallback. Config files or environment variables with higher precedence can override it. This pattern fits libraries that want to supply defaults while respecting deployment configuration.

### Do not put secrets in defaults or logs

Never place API keys, passwords, or tokens into default property sources in code. Secrets should come from a secret manager, environment variables, or a controlled config tree. When logging the Environment, avoid printing all property values because credentials could be exposed.

## 15. Distinguishing Bootstrap Extension Points

These extension points are frequently confused:

| Extension Point | Timing | Recommended Use |
|---|---|---|
| `EnvironmentPostProcessor` | While preparing Environment, before ApplicationContext | Adding/reordering property sources, handling bootstrap config |
| `ApplicationEnvironmentPreparedEvent` listener | When Environment prepared event is published | Observing or reacting to the bootstrap event |
| `ApplicationContextInitializer` | After context creation, before refresh | Customizing context/Environment before loading beans |
| `BeanFactoryPostProcessor` | After bean definitions are registered, before standard bean instantiation | Modifying bean definition metadata |
| `BeanDefinitionRegistryPostProcessor` | During registry processing phase | Registering/modifying bean definitions |
| `BeanPostProcessor` | During creation of each bean | Modifying instances/proxies before or after initialization |
| `ApplicationRunner` / `CommandLineRunner` | After context refresh | Executing post-startup tasks |

If your goal is to change a property used to load configuration files, use `EnvironmentPostProcessor` or a bootstrap source. If you want to alter bean definitions, use a registry post-processor or appropriate registrar. If you want to process bean instances, use a `BeanPostProcessor`. If you want to run tasks once the application is ready, use a runner.

Placing logic in the wrong extension point can cause properties to appear too late or beans not to exist yet.

## 16. Common Errors When Preparing the Environment

| Symptom | Possible Cause | How to Investigate |
|---|---|---|
| Profile not activated | Active profile value overridden or declared in the wrong source | Check `spring.profiles.active`, command line, and environment variables |
| External config file not loaded | Incorrect `spring.config.location` or import syntax | Check Config Data locations and startup logs |
| `@Profile` does not match | Profile was not active during configuration parsing | Check Environment before refresh |
| Property in `@PropertySource` does not affect logging | Property loaded too late | Move to Config Data or a bootstrap source |
| Custom Environment breaks web configuration | Wrong Environment type used or Boot behavior replaced | Let Boot create the Environment; add property sources instead |
| EnvironmentPostProcessor does not run | Not properly registered in `spring.factories` or class missing from classpath | Check metadata file and runtime artifact |
| EnvironmentPostProcessor does not see property file | Processor ran before Config Data processor | Check processor ordering |
| Custom property gets overridden | Property source is in a low-precedence position | Inspect `PropertySources` order |
| Bean retains old value after Environment change | Bean bound/copied property at initialization | Use an intentional refresh/rebind mechanism |
| Application picks wrong ApplicationContext | Web application type determined before custom property was loaded | Provide the property from an early bootstrap source |

### Checking active profiles

You can observe:

~~~java
log.info("Active profiles: {}",
        Arrays.toString(environment.getActiveProfiles()));
~~~

Log only profile names; avoid logging the entire configuration if secrets are present.

### Checking property source names

You can iterate over the sources:

~~~java
for (PropertySource<?> source :
        environment.getPropertySources()) {
    log.info("Property source: {}", source.getName());
}
~~~

Source names help trace where properties originate. Avoid printing entire maps, as they may contain sensitive information.

### Using Actuator in a controlled manner

If Spring Boot Actuator is integrated, the `env` endpoint can help inspect property sources and sanitized values. Because this endpoint can reveal sensitive configuration, expose it only on a protected management network, restrict access, and keep proper sanitization enabled.

## 17. Testing Environment and Bootstrap Configuration

Not every test needs to start the entire application. You can test properties or profiles at several levels.

### Testing with Spring Boot properties

~~~java
@SpringBootTest(properties = {
        "app.region=test",
        "app.feature.catalog=false"
})
class StoreConfigurationTest {
    // Test beans/configuration using the properties above.
}
~~~

Test properties are added to the test context's Environment with precedence appropriate for testing.

### Testing profiles

~~~java
@SpringBootTest
@ActiveProfiles("test")
class PaymentConfigurationTest {
    // Verify beans belonging to the test profile.
}
~~~

`@ActiveProfiles` selects profiles for the test context. It lets you test environment-specific configurations without altering the main configuration files.

### Testing property sources

~~~java
@SpringBootTest
@TestPropertySource(properties = {
        "app.payment.timeout=2s"
})
class PaymentPropertiesTest {
    // ...
}
~~~

`@TestPropertySource` adds properties for the test. In modern Spring Boot, consider `@DynamicPropertySource` when values come from dynamic test resources such as container databases.

### Testing EnvironmentPostProcessor

`EnvironmentPostProcessor` is a bootstrap extension point, so tests should verify both that the processor is registered and that the property source appears at the right time. You can spin up a small `SpringApplication` or verify via a context integration test using the actual registration metadata.

If a unit test only calls `postProcessEnvironment` directly, it tests the processor logic but does not verify `spring.factories` registration or ordering relative to Config Data.

### Testing configuration across multiple sources

A useful test places the same key in default properties, a config file, and the command line, then asserts the value has the expected precedence. This prevents deployment bugs caused by wrong assumptions about which source wins.

## 18. End-to-End Example: Selecting Profile and Property Before Context

Suppose a payment application has two configurations:

~~~java
@Configuration
@Profile("dev")
public class DevPaymentConfiguration {

    @Bean
    public PaymentGateway paymentGateway() {
        return new DemoPaymentGateway();
    }
}
~~~

~~~java
@Configuration
@Profile("prod")
public class ProdPaymentConfiguration {

    @Bean
    public PaymentGateway paymentGateway(
            PaymentProperties properties
    ) {
        return new LivePaymentGateway(properties.getEndpoint());
    }
}
~~~

`PaymentProperties`:

~~~java
@ConfigurationProperties(prefix = "app.payment")
public class PaymentProperties {
    private String endpoint;

    public String getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(String endpoint) {
        this.endpoint = endpoint;
    }
}
~~~

`application.yml` file:

~~~yaml
spring:
  profiles:
    active: dev

app:
  payment:
    endpoint: https://sandbox-payments.example
~~~

When running in production, an operator can pass:

~~~bash
java -jar store.jar --spring.profiles.active=prod --app.payment.endpoint=https://payments.example
~~~

Sequence:

1. Spring Boot prepares the Environment.
2. The command-line property source is added as configured.
3. The active profile is determined to be `prod`.
4. Config Data loads the shared and matching profile-specific files.
5. The ApplicationContext is created.
6. Spring parses configuration; `@Profile("prod")` matches and the dev configuration is not applied.
7. `PaymentProperties` is bound from the Environment.
8. The production `PaymentGateway` is created and injected into services.

Services do not need to inspect profiles or look up beans themselves. The Environment determines which configurations are registered; the container wires dependencies afterward.

## 19. Principles for Predictable Bootstrap Design

1. **Provide bootstrap properties from early sources.** Use command line, environment variables, system properties, Config Data, or `EnvironmentPostProcessor` for configuration needed before the context.
2. **Let Spring Boot create the appropriate Environment in standard applications.** Add property sources instead of replacing the entire Environment unless you have a special need.
3. **Understand PropertySource precedence.** Defaults should have low priority; deployment configuration must be able to override them.
4. **Select profiles before refreshing the context.** `@Profile` is evaluated when Spring processes configuration and bean definitions.
5. **Use Config Data for application configuration files.** `spring.config.import`, `additional-location`, and config trees load external sources through the standard mechanism.
6. **Use EnvironmentPostProcessor for bootstrap logic.** Do not use it as a business service or a place to call databases/APIs.
7. **Use ApplicationContextInitializer for a created-but-unrefreshed context.** Do not expect an initializer to undo already-completed bootstrap decisions.
8. **Do not use @PropertySource for properties needed early.** It is processed during configuration class parsing.
9. **Do not expect bound beans to auto-update when the Environment changes.** Runtime refresh requires a dedicated mechanism.
10. **Do not log secrets from the Environment.** Observing property source names and active profiles suffices for many scenarios.
11. **Test both precedence and profiles.** A single YAML file does not represent the entire runtime Environment.
12. **Choose extension points based on the phase you need to hook into.** Environment, context, bean definition, and bean instance are distinct milestones.

## Conclusion

Spring Boot prepares the Environment before creating the ApplicationContext so it can determine property sources, profiles, Config Data, and essential bootstrap decisions. The Environment unifies multiple configuration sources in precedence order; profiles decide which configurations apply; Config Data loads files and imported sources before Spring starts building the object graph.

`EnvironmentPostProcessor` hooks into the Environment preparation phase, while `ApplicationContextInitializer` runs after the context is created but before refresh. `@PropertySource` is processed later during configuration class parsing, making it unsuitable for properties needed early such as Config Data settings or bootstrap logging.

When a property or profile behaves unexpectedly, inspect the actual configuration sources, `PropertySource` ordering, processor execution timing, and the phase in which beans or configurations consume that value. Understanding the boundary between the Environment and the ApplicationContext keeps Spring Boot startup predictable, environment-specific configuration clear, and prevents deployment-only surprises.
