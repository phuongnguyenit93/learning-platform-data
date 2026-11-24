# ApplicationContextInitializer and Pre-Refresh Customization

During Spring startup, the ApplicationContext is created before the container begins refreshing and instantiating beans. In this window, an application may need to add property sources, adjust the Environment, or prepare the context before configuration classes are loaded.

`ApplicationContextInitializer` is the extension point dedicated to that work. Spring Boot invokes initializers after creating the context and attaching the Environment, yet before loading primary configuration sources into the context and before calling `refresh()`. Consequently, initializers are well suited for changes that must take effect before Spring parses bean definitions and creates beans.

## 1. What Is ApplicationContextInitializer?

The `ApplicationContextInitializer` interface belongs to package `org.springframework.context`:

~~~java
public interface ApplicationContextInitializer<C extends ConfigurableApplicationContext> {

    void initialize(C applicationContext);
}
~~~

An initializer receives a `ConfigurableApplicationContext`. From this context, it can access the Environment, adjust context settings, or register processing steps that will execute during refresh.

Common use cases:

- Adding a property source before Spring evaluates configuration conditions.
- Setting certain attributes or metadata on the ApplicationContext.
- Registering a `BeanFactoryPostProcessor` to process bean definitions during refresh.
- Preparing the context to meet a bootstrap requirement of an application or library.

An initializer is not the place to instantiate business services by invoking constructors manually. Bean creation, dependency injection, and lifecycle management still belong to the Spring container.

## 2. Where Does the Initializer Fit in Startup?

When calling `SpringApplication.run()`, Spring Boot runs through a sequence of steps. The relevant flow can be illustrated as follows:

~~~text
SpringApplication.run()
        |
        v
Prepare Environment
        |
        +--> Read arguments, environment variables, and config sources
        +--> Process Config Data, application.yml, and profiles
        |
        v
Create ApplicationContext
        |
        v
Attach Environment to context
        |
        v
postProcessApplicationContext()
        |
        v
Invoke ApplicationContextInitializer.initialize()
        |
        v
Publish ApplicationContextInitializedEvent
        |
        v
Load primary configuration sources
        |
        v
ApplicationContext.refresh()
        |
        +--> Invoke BeanFactoryPostProcessors
        +--> Register BeanPostProcessors
        +--> Instantiate eager singletons
        |
        v
ContextRefreshedEvent
        |
        v
ApplicationRunner / CommandLineRunner
        |
        v
ApplicationReadyEvent
~~~

The crucial point is that initializers run before `refresh()`. Bean definitions from primary configuration sources have not been loaded at the `initialize()` step yet, so you should not call `getBean()` to retrieve application services here.

On the other hand, Spring Boot's Environment has already been prepared before the context is created. Configuration sources such as command-line arguments, environment variables, and Config Data are normally already present. Modifying the Environment in an initializer can influence subsequent bean definition processing, though it cannot turn back time to reload Config Data.

## 3. Writing an ApplicationContextInitializer

For example, suppose an application has an optional feature. If no value is configured yet, an initializer adds default values to the Environment before Spring evaluates conditions:

~~~java
import java.util.Map;

import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;

public class FeatureDefaultsInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(
            ConfigurableApplicationContext applicationContext) {

        ConfigurableEnvironment environment =
                applicationContext.getEnvironment();

        Map<String, Object> defaults = Map.of(
                "app.feature.enabled", "true",
                "app.feature.region", "local"
        );

        environment.getPropertySources().addLast(
                new MapPropertySource(
                        "featureDefaults",
                        defaults
                )
        );
    }
}
~~~

The initializer retrieves the Environment from the context and adds a `MapPropertySource` named `featureDefaults`. In this example, the property source is added with `addLast()`, meaning it has low precedence. Values supplied by users in higher-precedence sources are preserved.

Configuration can then evaluate these properties:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "app.feature",
        name = "enabled",
        havingValue = "true"
)
public class FeatureConfiguration {

    @Bean
    FeatureService featureService() {
        return new FeatureService();
    }
}
~~~

If an operator sets `app.feature.enabled=false` in a higher-precedence configuration source, the condition does not match and `FeatureService` is not registered. The default value in the initializer applies only when no higher-precedence source provides a value.

### How do addFirst and addLast differ?

`MutablePropertySources` allows adding a property source at the beginning or end of the list:

- `addFirst(source)`: puts the source first, giving it higher precedence than trailing sources. It can override values from application config, environment variables, or command-line property sources if they follow behind it.
- `addLast(source)`: puts the source last, usually appropriate for supplying default values that can be overridden.

Choose the position based on the data source's intent. If the initializer provides defaults, `addLast()` is usually more predictable. Use `addFirst()` only when you genuinely want that source to take high precedence.

Property source names should be stable and unique within the Environment. If multiple initializers might add the same source, check `propertySources.contains(name)` before adding to avoid unintended replacement.

## 4. Registering an Initializer with SpringApplication

The direct way is instantiating `SpringApplication`, adding the initializer, and running the application:

~~~java
import org.springframework.boot.SpringApplication;

public class ApplicationLauncher {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(Application.class);

        application.addInitializers(
                new FeatureDefaultsInitializer()
        );

        application.run(args);
    }
}
~~~

The initializer is added to the `SpringApplication` instance and applied when it creates the ApplicationContext.

If using `SpringApplicationBuilder`, you can register the initializer on the builder:

~~~java
new SpringApplicationBuilder(Application.class)
        .initializers(new FeatureDefaultsInitializer())
        .run(args);
~~~

Explicit registration suits situations where the application owns the launcher and wants clear visibility into which initializers are active.

### Registering initializers via Spring factories

A library can advertise an initializer via `META-INF/spring.factories`:

~~~properties
org.springframework.context.ApplicationContextInitializer=\
com.example.bootstrap.FeatureDefaultsInitializer
~~~

Spring Boot uses `SpringFactoriesLoader` to discover implementations declared under the corresponding key. When packaging a library, ensure the resource file lands in the JAR at the exact path with the exact fully qualified class name.

Do not confuse this mechanism with the auto-configuration list in Spring Boot 3. Auto-configuration candidates are declared via `AutoConfiguration.imports`; `ApplicationContextInitializer` remains an extension point registered via Spring factories or the `SpringApplication` API.

When there are multiple initializers, establish an intentional execution order. Initializers discovered via Spring factories can use `Ordered` or `@Order` under Spring's ordering mechanism. For initializers added directly to `SpringApplication`, verify the actual registration list order rather than relying on untested assumptions.

## 5. Customizing the Environment Before Refresh

One of the best fits for an initializer is adjusting the Environment before Spring processes application configuration.

Beyond adding a property source, an initializer can:

- Read existing properties to decide how to prepare the context.
- Set context attributes such as an ID when explicitly required.
- Set active profiles in cases suited to the bootstrap point in time.
- Register a `BeanFactoryPostProcessor` to process bean definitions during refresh.

Distinguish when Environment modifications occur relative to when Spring Boot loads Config Data. Boot prepares the Environment before creating the ApplicationContext and invoking initializers. Therefore, if your goal is deciding which `application-{profile}.yml` file gets loaded, configure profiles upfront via `spring.profiles.active`, environment variables, or command-line arguments.

For example, setting an active profile inside an initializer does not cause the already-completed Config Data phase to automatically reload profile-specific files for the new profile. If you must intervene in the Environment before or during Config Data loading, look into `EnvironmentPostProcessor` and its execution order.

### Registering a BeanFactoryPostProcessor from an initializer

If you need to process bean definitions during refresh, an initializer can register a `BeanFactoryPostProcessor` on the context:

~~~java
import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;

public class BeanFactoryPreparationInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(
            ConfigurableApplicationContext applicationContext) {

        applicationContext.addBeanFactoryPostProcessor(
                beanFactory -> {
                    // Process BeanDefinitions during the refresh phase.
                }
        );
    }
}
~~~

The initializer simply registers the callback. Spring invokes the `BeanFactoryPostProcessor` during refresh, after bean definitions are loaded and before standard singletons are instantiated.

If you only need to register business beans, use `@Configuration`, `@Bean`, component scanning, or imports. Do not put ordinary bean registration logic inside an initializer without a specific bootstrap reason.

## 6. How Does ApplicationContextInitializer Differ from EnvironmentPostProcessor?

Both extension points can interact with the Environment, yet they run at different points:

| Mechanism | Timing | Appropriate Scope |
|---|---|---|
| `EnvironmentPostProcessor` | While Spring Boot is preparing the Environment, before creating the ApplicationContext | Adding or adjusting property sources early, intervening in Environment/Config Data preparation |
| `ApplicationContextInitializer` | After the context is created and Environment attached, before loading primary config sources and refresh | Customizing the context or Environment in the pre-refresh phase |
| `BeanFactoryPostProcessor` | During refresh, after bean definitions are loaded and before creating standard beans | Modifying or inspecting bean definitions |
| `BeanPostProcessor` | During the initialization of individual beans | Intercepting instances before/after initialization |
| `@PostConstruct` | During initialization of the current bean | Preparing the bean's own internal state |
| `ApplicationRunner` | After context refresh, during Spring Boot startup | Running application tasks once beans are created |

### Choose EnvironmentPostProcessor when early impact is required

For example, a library may need to add a property source before Spring Boot processes Config Data or resolves profiles. In that case, `EnvironmentPostProcessor` fits better than an initializer because it participates in Environment preparation before the ApplicationContext exists.

`EnvironmentPostProcessor` is typically declared in `META-INF/spring.factories` under the key:

~~~properties
org.springframework.boot.env.EnvironmentPostProcessor=\
com.example.bootstrap.CustomEnvironmentPostProcessor
~~~

Processor ordering can determine which property source is processed first. If you need to interact with Config Data, define the order relative to related processors; do not assume a processor runs before or after Config Data without configuring and verifying it.

### Choose ApplicationContextInitializer when the context must already exist

If you need access to `ConfigurableApplicationContext`, want to change the ID, add a property source for bean definition processing, or register a post-processor on the context, an initializer is the right fit.

The deciding question is: must the change take effect before the Environment is prepared, or only before context refresh? Answering that guides you to the right extension point.

## 7. What Should and Should Not Be Done in an Initializer?

Initializers run during bootstrap, when the context exists yet has not refreshed. Keep their work within an appropriate scope.

Do:

- Add property sources with clear provenance and precedence.
- Configure context metadata before refresh.
- Register a `BeanFactoryPostProcessor` when bean definition processing is genuinely needed.
- Validate essential bootstrap values and fail startup early if configuration is invalid.

Do not:

- Call `getBean()` to invoke business services before the context refreshes.
- Manually call constructors and manage service lifecycles outside the container.
- Manually call `refresh()` on a context managed by Spring Boot.
- Perform network calls or slow work that stalls startup without clear timeout policies.
- Set active profiles too late and expect Boot to reload Config Data.
- Insert a property source at the front of the Environment without considering how it could override operator-supplied configuration.

If an initializer throws an exception, startup fails. This is appropriate when a mandatory bootstrap condition is not met, provided the exception clearly describes the configuration source and cause.

## 8. Testing ApplicationContextInitializer

You can test an initializer independently of the full application. Spring Boot Test provides `ApplicationContextRunner`, letting you attach the initializer and assert that Environment values apply before bean conditions are evaluated.

For example, using the initializer above to supply default values:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class FeatureDefaultsInitializerTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withInitializer(new FeatureDefaultsInitializer())
                    .withUserConfiguration(FeatureConfiguration.class);

    @Test
    void usesInitializerDefaultWhenPropertyIsMissing() {
        contextRunner.run(context -> {
            assertThat(context.getEnvironment().getProperty(
                    "app.feature.enabled"
            )).isEqualTo("true");

            assertThat(context).hasSingleBean(FeatureService.class);
        });
    }

    @Test
    void externalPropertyOverridesInitializerDefault() {
        contextRunner
                .withPropertyValues("app.feature.enabled=false")
                .run(context -> {
                    assertThat(context.getEnvironment().getProperty(
                            "app.feature.enabled"
                    )).isEqualTo("false");

                    assertThat(context)
                            .doesNotHaveBean(FeatureService.class);
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class FeatureConfiguration {

        @Bean
        @ConditionalOnProperty(
                prefix = "app.feature",
                name = "enabled",
                havingValue = "true"
        )
        FeatureService featureService() {
            return new FeatureService();
        }
    }
}
~~~

This test suite verifies two things:

1. The property source added by the initializer is present before Spring processes configuration and conditions.
2. Properties supplied by the test have higher precedence than defaults from the initializer.

When testing a real application initializer, also verify that property sources are not duplicated, initializer ordering is clear, and bootstrap errors produce clear messages.

## 9. Common Mistakes

### Using an initializer to change profiles and expecting profile config files to load

Spring Boot prepares the Environment and processes Config Data before calling initializers. Changing active profiles inside an initializer does not rerun Config Data loading. Supply profiles before launch or use `EnvironmentPostProcessor` at the right phase.

### Calling business beans before the context refreshes

Primary configuration sources may not be loaded yet and ordinary singletons are not initialized. Calling `getBean()` here can instantiate beans prematurely or cause bootstrap to fail. Restrict initializers to context preparation work.

### Adding a property source with unsuitable precedence

Using `addFirst()` can overwrite configuration passed by operators. If you only intend to provide defaults, use a low-precedence position like `addLast()` and test the override case with external properties.

### Confusing an initializer with BeanFactoryPostProcessor

Initializers run before Spring loads primary configuration sources into the context. `BeanFactoryPostProcessor` executes during refresh, after bean definitions are loaded. If you need to inspect or alter bean definitions, register a post-processor and let Spring invoke it in the right phase.

### Assuming an initializer automatically re-runs when the context changes

An initializer runs during context preparation. It is not a listener watching the Environment or beans throughout application runtime. If a new context is created, initializers registered for that initialization run again; changing properties in a running context does not re-trigger the initializer.

## 10. Process for Choosing and Using an Initializer

When pre-refresh customization is needed, follow this sequence:

1. Determine whether the change must happen before the Environment is prepared or simply before context refresh.
2. Choose `EnvironmentPostProcessor` if you must intervene in Environment preparation or Config Data; choose `ApplicationContextInitializer` if you need an existing context.
3. Write the initializer for the appropriate context type, keeping changes small and predictable.
4. Pick a registration method: `SpringApplication.addInitializers`, `SpringApplicationBuilder.initializers`, or Spring factories.
5. Define ordering explicitly when multiple initializers exist.
6. Verify property source precedence and ensure operator-supplied values take proper effect.
7. Test outcomes before bean definitions and conditions are evaluated.
8. Keep bean instantiation and business logic inside Spring's bean management lifecycle.

`ApplicationContextInitializer` provides a clear hook after the ApplicationContext is created yet before refresh. Used at the right time, an initializer prepares the Environment and context so configuration parsing proceeds as intended, while keeping bean creation and lifecycle management under Spring's control.
