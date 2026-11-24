# Registering shared configuration without scanning the entire library package

When building a shared library for multiple Spring Boot applications, the library may provide beans such as HTTP clients, data converters, integration services, validators, or security configurations. However, merely adding a JAR as a dependency does not mean Spring will automatically discover every class annotated with `@Component` inside that JAR.

The host application usually places `@SpringBootApplication` in its own package, while the library resides in a different package or module. Default component scanning starts from the main class's package and traverses down into subpackages. Therefore, a library package outside this scope will not be scanned.

A seemingly quick workaround is scanning the entire library package, yet that can register many internal components that are not part of the public API, cause bean name collisions, or activate features the application does not need. Spring provides more explicit mechanisms:

- `@Import` to import one or a group of known configurations/classes.
- `@Enable...`-style annotations so the host application enables a shared module with a single declaration.
- Spring Boot auto-configuration so a starter automatically registers configuration based on classpath and conditions.
- `ImportSelector` or `ImportBeanDefinitionRegistrar` when a library genuinely needs dynamic selection or bean registration.
- Narrowly scoped component scanning when a module has multiple components that need package-based discovery.

The goal is to publish **a stable configuration entry point**, so the application chooses which modules to use and Spring registers only the beans that module intentionally provides.

## 1. Why doesn't a library dependency automatically create beans?

Suppose the application has the structure:

~~~text
com.example.orders
├── OrdersApplication.java
├── controller
├── service
└── repository

com.acme.sharedclient
├── SharedClient.java
├── SharedClientService.java
├── config
│   └── SharedClientConfiguration.java
└── internal
    ├── DefaultTokenProvider.java
    └── RetrySupport.java
~~~

Startup class:

~~~java
package com.example.orders;

@SpringBootApplication
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Default component scanning starts from `com.example.orders` and goes down into subpackages like `com.example.orders.service`. Package `com.acme.sharedclient` is a different package, not underneath the application's root package.

Even when the library JAR is on the runtime classpath, Spring does not automatically scan all classes inside the JAR. The classpath only lets the JVM load classes; component scanning, `@Import`, or another registration mechanism is what puts bean definitions into the Spring container.

These are three separate actions:

| Action | Meaning |
|---|---|
| Adding a dependency | Puts the library and transitive dependencies on the classpath by scope |
| Discovering/registering beans | Adds bean definitions to BeanFactory via scan, import, auto-configuration, or explicit registration |
| Instantiating beans | Creates instances, injects dependencies, and runs lifecycles when the container needs them |

Therefore, a library with `@Component` classes outside the scan scope and not imported may not appear in the context at all.

## 2. Simplest approach: importing a @Configuration class

A library can provide a public configuration class:

~~~java
package com.acme.sharedclient.config;

import com.acme.sharedclient.DefaultSharedClient;
import com.acme.sharedclient.SharedClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class SharedClientConfiguration {

    @Bean
    SharedClient sharedClient() {
        return new DefaultSharedClient();
    }
}
~~~

The host application imports this configuration:

~~~java
package com.example.orders;

import com.acme.sharedclient.config.SharedClientConfiguration;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Import;

@SpringBootApplication
@Import(SharedClientConfiguration.class)
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

When Spring processes `OrdersApplication`, `SharedClientConfiguration` is imported into the same application context. The `SharedClient` bean can be injected into the application's services:

~~~java
@Service
public class OrderSyncService {
    private final SharedClient sharedClient;

    public OrderSyncService(SharedClient sharedClient) {
        this.sharedClient = sharedClient;
    }
}
~~~

There is no need to scan package `com.acme.sharedclient`. Spring already knows exactly which configuration class to process and which beans are declared inside it.

`@Import` can also import multiple classes:

~~~java
@Configuration(proxyBeanMethods = false)
@Import({
    SharedClientConfiguration.class,
    SharedJsonConfiguration.class,
    SharedRetryConfiguration.class
})
public class SharedIntegrationConfiguration {
}
~~~

This fits when the host application knows explicitly which modules to enable. Imported configurations participate in the same context; they do not create a separate container.

## 3. Packaging into an @Enable... annotation

If the library wants to offer a simpler usage experience, it can create a public annotation such as `@EnableSharedClient`. This annotation acts as an **entry point** for the entire module configuration.

### 3.1. Creating a feature-enabling annotation

~~~java
package com.acme.sharedclient;

import com.acme.sharedclient.config.SharedClientConfiguration;
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.context.annotation.Import;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Import(SharedClientConfiguration.class)
public @interface EnableSharedClient {
}
~~~

The host application only needs:

~~~java
@SpringBootApplication
@EnableSharedClient
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

The `@EnableSharedClient` annotation does not create beans itself. It imports the configuration published by the library. That configuration can in turn import sub-configurations or declare related beans.

### 3.2. When should you use @Enable...?

This pattern fits when:

- The library has an optional feature that applications want to turn on only when explicitly declared.
- The module needs a stable public configuration API.
- Users want clear visibility into which integrations the application enables.
- The configuration should not automatically appear merely because the dependency is present.

For example, a library might provide:

~~~java
@EnableSharedClient
@EnablePartnerMessaging
@EnableTenantSupport
~~~

Each annotation enables a separate configuration group. This clarifies intent at the application layer and avoids a single dependency pulling in unwanted features.

### 3.3. Annotations can accept attributes

A module-enabling annotation sometimes needs parameters:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Import(SharedClientConfiguration.class)
public @interface EnableSharedClient {
    String baseUrl() default "";
}
~~~

Annotation attributes can be read from metadata by the imported configuration or an `ImportSelector`. However, if configuration involves many properties, profiles, and complex binding, `@ConfigurationProperties` is usually a more scalable option. Avoid turning an annotation into a duplicate of the entire application configuration file.

## 4. Import only needed components, do not scan the whole library

`@Import` can directly import concrete component classes, not necessarily a configuration class containing `@Bean`:

~~~java
package com.acme.sharedclient;

import org.springframework.stereotype.Component;

@Component
public class SharedTokenProvider {
    public String currentToken() {
        return "token";
    }
}
~~~

The application or module configuration can register this class with:

~~~java
@Configuration(proxyBeanMethods = false)
@Import(SharedTokenProvider.class)
public class SharedClientConfiguration {
}
~~~

Spring registers the imported class as a bean candidate. This is useful when only a few public components need to be brought into the context.

If a component needs multiple dependencies, it can still inject them via constructor as usual. Those dependencies must also be registered via appropriate configuration/imports/auto-configuration.

### 4.1. Use @Bean when you want to control object creation

Instead of importing an implementation class, the library can declare beans via factory methods:

~~~java
@Configuration(proxyBeanMethods = false)
public class SharedClientConfiguration {

    @Bean
    SharedClient sharedClient(
            SharedTokenProvider tokenProvider,
            SharedClientProperties properties) {
        return new DefaultSharedClient(
                properties.getBaseUrl(),
                tokenProvider
        );
    }
}
~~~

`@Bean` methods let you:

- Choose a concrete implementation while exposing only the interface.
- Pass bound properties and other dependencies into the constructor.
- Set bean name, scope, conditions, or lifecycle callbacks.
- Keep internal implementations free of public stereotypes.

When using `@Configuration(proxyBeanMethods = false)`, inject dependencies via `@Bean` method parameters as shown. Do not call another factory method directly expecting Spring to always return the registered singleton; in lite mode, that call is an ordinary Java method invocation.

## 5. When a library has many components: narrow component scan

Sometimes a module has many components belonging to one feature package. Instead of importing each class individually, you can place `@ComponentScan` in the module configuration while restricting it to a specific package.

~~~java
package com.acme.sharedclient.config;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ComponentScan(basePackages = "com.acme.sharedclient.client")
public class SharedClientConfiguration {
}
~~~

Here only package `com.acme.sharedclient.client` and its subpackages are scanned. Internal components in `com.acme.sharedclient.internal` are not automatically discovered because they sit outside that package tree.

### 5.1. Use a marker class instead of a package string

To avoid invalid package names during refactoring, you can use `basePackageClasses`:

~~~java
package com.acme.sharedclient.client;

public interface SharedClientComponentMarker {
}
~~~

~~~java
@Configuration(proxyBeanMethods = false)
@ComponentScan(basePackageClasses = SharedClientComponentMarker.class)
public class SharedClientConfiguration {
}
~~~

Spring uses the package containing the marker as the base package. This is safer than string literals when packages are renamed.

The marker does not need to be a bean and needs no logic. Place the marker in the exact root package of the component group to scan, not in the root package of the entire library if the goal is to limit scope.

### 5.2. When is a narrow scan still not enough?

Component scanning still discovers all matching stereotypes within the package and its subpackages unless exclusion filters are applied. If a package holds many internal implementations or components used only in some applications, even a narrow scan may register too many beans.

In that case, explicit registration via `@Bean` or importing individual classes gives the library API tighter control. Component scanning is a package-based discovery convenience; it does not replace module boundaries.

## 6. Using includeFilters and excludeFilters when scan control is needed

If you need to scan a package yet only want a specific group of components, you can use filters:

~~~java
@Configuration(proxyBeanMethods = false)
@ComponentScan(
        basePackages = "com.acme.sharedclient",
        useDefaultFilters = false,
        includeFilters = @ComponentScan.Filter(
                type = FilterType.ASSIGNABLE_TYPE,
                classes = {
                        SharedTokenProvider.class,
                        SharedClientMetrics.class
                }
        )
)
public class SharedClientConfiguration {
}
~~~

With `useDefaultFilters = false`, the default stereotype filters no longer apply; only declared filters determine which classes are included. This example selects only those two classes by assignable type.

Other filter types such as annotation, regex, aspectJ, or custom filters can be used as needed. However, if there are only a few classes, `@Import` is usually easier to read and requires less configuration.

Do not widen the base package to huge namespaces like `com`, `org`, or a root package shared by many libraries. The wider the scan scope, the higher the risk of discovering unintended components, bean name collisions, and increased startup time.

## 7. Distinguishing @Import from Spring Boot auto-configuration

`@Import` fits when the application **actively chooses** configuration. A Spring Boot starter can offer a different experience: simply add the dependency, and Boot automatically discovers auto-configuration and applies it if conditions match.

The two mechanisms have different goals:

| Criterion | `@Import` / `@Enable...` | Boot auto-configuration |
|---|---|---|
| Activation | Application declares annotation/import | Boot discovers registered classes on the classpath |
| Opt-in level | Explicit opt-in | Typically auto-applied when dependency and conditions match |
| Conditions | Can combine with `@Profile`/`@Conditional...` | Typically uses multiple classpath, property, bean conditions |
| Goal | Assemble module configurations per application intent | Provide convenient default configuration for a starter |
| How to disable | Remove annotation/import or matching condition | Exclude auto-configuration or make conditions not match |

A library can offer both models, but deliberately:

- Core library: provides APIs and required classes.
- Optional configuration module: provides `@EnableSharedClient` annotation and imported configuration class.
- Boot starter: self-registers auto-configuration for applications wanting an automatic experience.

There is no need to create starter auto-configuration if a module is only used internally within one application and enabling via `@Import` is already clear enough.

## 8. Registering auto-configuration in Spring Boot 3.x

For a starter library targeting Spring Boot 3.x, you can create the class:

~~~java
package com.acme.sharedclient.autoconfigure;

import com.acme.sharedclient.DefaultSharedClient;
import com.acme.sharedclient.SharedClient;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(SharedClient.class)
@EnableConfigurationProperties(SharedClientProperties.class)
@ConditionalOnProperty(
        prefix = "acme.shared-client",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
public class SharedClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    SharedClient sharedClient(SharedClientProperties properties) {
        return new DefaultSharedClient(properties.getBaseUrl());
    }
}
~~~

Meaning of the conditions:

- `@ConditionalOnClass` only allows configuration when the required API class is present.
- `@EnableConfigurationProperties` registers the properties class so Spring Boot binds configuration.
- `@ConditionalOnProperty` allows toggling the module via configuration.
- `@ConditionalOnMissingBean` lets applications replace the default implementation with their own bean.

`SharedClientProperties` is a properties class defined by the library. Example:

~~~java
package com.acme.sharedclient.autoconfigure;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.shared-client")
public class SharedClientProperties {
    private String baseUrl;

    public String getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(String baseUrl) {
        this.baseUrl = baseUrl;
    }
}
~~~

Application configuration:

~~~yaml
acme:
  shared-client:
    enabled: true
    base-url: https://api.example.test
~~~

### 8.1. Publishing auto-configuration via AutoConfiguration.imports

In the library JAR, create the file:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Content:

~~~text
com.acme.sharedclient.autoconfigure.SharedClientAutoConfiguration
~~~

Spring Boot reads this list when processing `@EnableAutoConfiguration`. When an application adds the starter to the classpath, the configuration can be discovered without the application component-scanning the library package or writing `@Import` manually.

This file contains fully qualified names of auto-configuration classes, one class per line. Do not put regular components/services here as if it were a component scan list; register auto-configurations, and let those configurations declare beans or import needed components.

### 8.2. Why not put @ComponentScan on auto-configuration?

An auto-configuration should declare the beans it manages via `@Bean`, `@Import`, or a clearly scoped mechanism. Putting `@ComponentScan("com.acme.sharedclient")` on the library's root package can scan internal configurations, helper implementations, or components unrelated to the enabled feature.

If scanning is truly needed, restrict base packages and filters within a specific module. But for public starters, explicit bean declarations usually keep behavior more predictable and reduce risk when the library adds new classes.

## 9. Metadata differences across Spring Boot lines

Auto-configuration registration mechanisms changed across Spring Boot generations:

| Spring Boot line | Commonly used auto-configuration publication |
|---|---|
| Boot 3.x | `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` |
| Boot 2.7 | Supports `AutoConfiguration.imports` mechanism; legacy mechanism may also appear in compatible libraries |
| Boot 2.6 and earlier | Usually declared in `META-INF/spring.factories` under the key `org.springframework.boot.autoconfigure.EnableAutoConfiguration` |

Example legacy metadata for older Boot 2.x:

~~~properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.acme.sharedclient.autoconfigure.SharedClientAutoConfiguration
~~~

Place this content in the library's `META-INF/spring.factories`. When supporting multiple Boot lines, check the compatibility matrix and registration mechanism supported by target versions; do not assume Boot 3's metadata file replaces every legacy mechanism in all Boot 2 releases.

Additionally, Boot 3 uses `@AutoConfiguration` for auto-configuration classes. With Boot 2, `@Configuration` with corresponding ordering/condition annotations was typically used. Compile the library against the exact Spring Boot baseline it declares support for.

## 10. Using ImportSelector when configurations must be selected from metadata

`ImportSelector` lets you choose the list of classes to import during configuration processing:

~~~java
import org.springframework.context.annotation.ImportSelector;
import org.springframework.core.type.AnnotationMetadata;

public class SharedClientImportSelector implements ImportSelector {

    @Override
    public String[] selectImports(AnnotationMetadata metadata) {
        return new String[] {
                "com.acme.sharedclient.config.SharedClientConfiguration",
                "com.acme.sharedclient.config.SharedJsonConfiguration"
        };
    }
}
~~~

Wire the selector into an annotation:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Import(SharedClientImportSelector.class)
public @interface EnableSharedClient {
}
~~~

A selector is useful when the imported list must vary based on annotation metadata or module choices. For example, an annotation has a `mode` attribute to pick an HTTP client or mock client configuration. When reading annotation attributes, use `AnnotationMetadata` and the corresponding Spring APIs to retrieve attribute values.

Do not use `ImportSelector` merely to return a fixed class. In that case, `@Import(SharedClientConfiguration.class)` is shorter and easier to follow.

### DeferredImportSelector

`DeferredImportSelector` is a variant that defers import selection to a later phase of configuration processing. Spring Boot uses this mechanism in its auto-configuration pipeline to coordinate with conditions and ordering.

This is an advanced extension point. Use it only when a library genuinely needs import selection at the deferred stage; there is no need to implement it for an ordinary module configuration.

## 11. ImportBeanDefinitionRegistrar for dynamic bean registration

When you need to create bean definitions based on metadata, interface names, or custom conventions, you can implement `ImportBeanDefinitionRegistrar`:

~~~java
import org.springframework.beans.factory.support.BeanDefinitionRegistry;
import org.springframework.beans.factory.support.RootBeanDefinition;
import org.springframework.context.annotation.ImportBeanDefinitionRegistrar;
import org.springframework.core.type.AnnotationMetadata;

public class SharedClientRegistrar
        implements ImportBeanDefinitionRegistrar {

    @Override
    public void registerBeanDefinitions(
            AnnotationMetadata importingClassMetadata,
            BeanDefinitionRegistry registry) {

        RootBeanDefinition definition =
                new RootBeanDefinition(DefaultSharedClient.class);

        registry.registerBeanDefinition("sharedClient", definition);
    }
}
~~~

Registration:

~~~java
@Configuration(proxyBeanMethods = false)
@Import(SharedClientRegistrar.class)
public class SharedClientModuleConfiguration {
}
~~~

A registrar works at the bean definition registry level, so it can control bean names and metadata. It is useful for libraries creating multiple clients/proxies based on annotations or declarative configuration.

However, you must check existing bean names, scopes, dependencies, and conditions before registering. If the goal is just to provide a default bean, `@Bean` with `@ConditionalOnMissingBean` is simpler and easier to maintain.

## 12. Allowing applications to replace default beans

A shared library should avoid forcing every application to use its internal implementation. Publish an interface and allow applications to provide a replacement bean:

~~~java
@AutoConfiguration
@ConditionalOnClass(SharedClient.class)
public class SharedClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(SharedClient.class)
    SharedClient sharedClient(SharedClientProperties properties) {
        return new DefaultSharedClient(properties.getBaseUrl());
    }
}
~~~

The application can declare its own:

~~~java
@Configuration(proxyBeanMethods = false)
class CustomClientConfiguration {

    @Bean
    SharedClient sharedClient() {
        return new CustomSharedClient();
    }
}
~~~

When the custom bean is registered before the auto-configuration's condition is evaluated, `@ConditionalOnMissingBean` lets the default configuration back off. This is an important part of starter design: providing useful defaults while respecting application configuration.

Auto-configuration processing order and user configuration placement can matter for bean-dependent conditions. Boot orders auto-configurations via its mechanism so application configurations generally get processed first. Do not rely on scanning the library package to replace conditions.

## 13. Avoiding bean conflicts when multiple shared modules are used

If multiple libraries scan wide packages or register beans under colliding default names, the context may encounter bean definition conflicts or the application may be unclear which implementation gets injected.

Some principles:

- Use meaningful bean names namespaced by module when a stable bean name is needed.
- Expose interfaces and keep internal implementations package-private or in an internal package where appropriate.
- Use `@ConditionalOnMissingBean` for intentional default beans.
- Use `@Qualifier` or `@Primary` when multiple implementations are valid.
- Avoid component scanning the library's entire root package.
- Do not enable bean definition overriding just to hide duplicate configurations.

Example:

~~~java
@Bean
@ConditionalOnMissingBean(name = "sharedClient")
SharedClient sharedClient(SharedClientProperties properties) {
    return new DefaultSharedClient(properties.getBaseUrl());
}
~~~

Name-based conditions are useful when the configuration contract relies on a specific bean name. If the goal is allowing replacement of any implementation of an interface, a type-based condition like `SharedClient.class` is usually more appropriate.

## 14. Separating core library, configuration module, and starter

For larger libraries, artifacts can be split by role:

~~~text
acme-shared-client-core
  ├── SharedClient interface
  ├── DTOs / exceptions
  └── API independent of Spring Boot

acme-shared-client-spring
  ├── @EnableSharedClient
  ├── SharedClientConfiguration
  └── Spring integration beans

acme-shared-client-spring-boot-starter
  ├── dependencies on core and spring integration
  └── SharedClientAutoConfiguration + metadata
~~~

Applications can choose to:

- Use only the core API without Spring.
- Use the integration module and enable via `@EnableSharedClient`.
- Use the starter so auto-configuration runs conditionally on its own.

This split avoids forcing every library user to accept all dependencies and automatic behaviors. It also makes testing and upgrading parts independently easier.

Not every small project needs three artifacts. Split modules only when dependency boundaries, reusability, or compatibility requirements genuinely justify it.

## 15. Testing imported configuration

For opt-in configurations using `@Import`, you can test a small context:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class SharedClientConfigurationTest {

    @Test
    void registersSharedClient() {
        try (var context = new AnnotationConfigApplicationContext(
                SharedClientConfiguration.class)) {

            assertThat(context.getBean(SharedClient.class)).isNotNull();
        }
    }
}
~~~

If the configuration needs properties or other dependencies, register them in the test context or use an appropriate context runner.

For Boot auto-configurations, `ApplicationContextRunner` lets you test conditions:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class SharedClientAutoConfigurationTest {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    SharedClientAutoConfiguration.class));

    @Test
    void createsDefaultClientWhenEnabled() {
        contextRunner
                .withPropertyValues(
                        "acme.shared-client.enabled=true",
                        "acme.shared-client.base-url=https://example.test")
                .run(context ->
                        assertThat(context).hasSingleBean(SharedClient.class));
    }

    @Test
    void backsOffWhenApplicationProvidesClient() {
        contextRunner
                .withBean(SharedClient.class, CustomSharedClient::new)
                .run(context ->
                        assertThat(context).hasSingleBean(SharedClient.class));
    }
}
~~~

The example uses `SharedClientProperties`, `CustomSharedClient`, and corresponding constructors defined by the library/test. In the second test, verify that the returned bean is the custom implementation, not just the bean count.

Scenarios to test:

1. Required dependency/class is present.
2. Property enabled and disabled.
3. Missing property uses the right default.
4. Application provides a replacement bean and auto-configuration backs off.
5. Configuration not enabled means optional beans are genuinely absent.
6. Internal components are not registered unintentionally.

With narrow component scanning, you can inspect bean names/types in the context to confirm only the intended component group was discovered.

## 16. Diagnosing when library beans do not appear

If an application service reports a missing bean from the library, check according to the registration source:

| How the library expects to register | What to check |
|---|---|
| `@Import` | Is the configuration class imported? Is a condition/profile excluding it? |
| `@Enable...` | Did the application put the enable annotation on a Spring-processed configuration class? |
| `@ComponentScan` | Do base packages and filters cover the required classes? |
| Boot auto-configuration | Is imports metadata inside the JAR? Was auto-configuration discovered and did conditions match? |
| `ImportSelector` | Does the selector return the right class names and are classes on the classpath? |
| `ImportBeanDefinitionRegistrar` | Is the registrar imported and does it register the right bean name/type? |

### Inspecting the dependency tree

A class might fail to load because the library JAR is not on the runtime classpath. With Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

With Maven:

~~~bash
mvn dependency:tree
~~~

These commands only confirm the dependency was resolved. Having the dependency present does not yet prove the bean was registered.

### Viewing the Condition Evaluation Report

With Spring Boot, enable `debug=true` or run the application with `--debug` to view auto-configuration conditions. The report shows which configurations matched, did not match, or were excluded.

If a configuration was imported explicitly yet the bean is still missing, check conditions/profiles on the configuration or `@Bean` method, as well as errors creating dependencies.

### Observing actual beans

In development environments, inspect `ApplicationContext` with `getBeanNamesForType(...)` or use the Actuator `beans` endpoint if enabled and properly secured. Do not expose this diagnostic endpoint publicly without access control.

## 17. Practices to avoid

**Scanning an overly broad root package:**

~~~java
@ComponentScan("com.acme")
~~~

This can discover components from many modules or other libraries under the same namespace. Restrict to feature packages or import public configurations.

**Putting @Component on every internal implementation and hoping applications discover them:** that makes the library API depend on each application's scan scope. Create a module configuration to register beans intentionally.

**Using auto-configuration for features applications always want to toggle manually:** if a module requires explicit opt-in, `@Enable...` annotations and `@Import` usually express intent better.

**Using @ImportSelector or a registrar for a fixed list:** advanced extension points add complexity. Use `@Import` directly when the classes to load are known.

**Registering every implementation with default bean names:** multiple libraries may share short class names. Expose interfaces and assign clear names when names are part of a contract.

**Enabling bean overriding to mask conflicts:** find which bean definition is duplicated, why it is registered twice, and which module owns it.

## 18. How to choose the right mechanism

| Scenario | Recommended approach |
|---|---|
| Application wants to enable a specific configuration | `@Import(SharedConfiguration.class)` |
| Want an easy-to-use module-enabling API | `@EnableSharedFeature` annotation combined with `@Import` |
| Library has a few components to register | `@Import` individual classes or declare via `@Bean` |
| Module has multiple components in a narrow package | `@ComponentScan` with specific base package/marker |
| Starter wants to self-configure when dependency is present | Boot auto-configuration and imports metadata |
| Need to pick configuration classes dynamically from metadata | `ImportSelector` or `DeferredImportSelector` |
| Need to register bean definitions dynamically by convention | `ImportBeanDefinitionRegistrar` |
| Need to load legacy XML configuration | `@ImportResource` |

A shared library design usually has a **public configuration** serving as the entry point. That configuration can declare beans via `@Bean`, import necessary components, and bind properties via `@ConfigurationProperties`. The host application simply imports the entry point or applies the `@Enable...` annotation. If the library is packaged as a starter, Boot auto-configuration can automatically discover the configuration and apply conditions.

The key is registering beans along **feature boundaries**: only beans belonging to enabled modules appear in the context. This avoids scanning the entire library package, reduces conflicts, and keeps configuration behavior predictable as applications add more shared modules.
