# @AutoConfiguration and candidate configurations

Spring Boot auto-configuration enables libraries to automatically register beans tailored to the classpath, environment configuration, and beans already provided by the application. Instead of requiring each application to manually import every configuration class, libraries publish auto-configuration classes as **candidates**. Spring Boot discovers those candidates, sorts them, and evaluates conditions to decide which configurations are applied.

In Spring Boot 3, the `@AutoConfiguration` annotation marks a configuration class intended for this mechanism. The candidate list is published in the file `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.

## 1. What problem does auto-configuration solve?

Suppose a library provides a client to connect to an external service. An application using the library typically needs a client bean and a service wrapping that client. If every application had to manually declare all of those beans, users would have to repeat the same configuration.

Auto-configuration lets a library supply default configuration. Spring Boot applies the configuration only when appropriate conditions match, for example:

- The client library is present on the classpath.
- A property enabling the feature is configured.
- The application has not already provided a replacement bean.
- The application type or environment meets the integration's requirements.

The application can still override default beans or exclude a specific auto-configuration. That way, the library offers a convenient startup experience while keeping control in the application's hands.

## 2. What is @AutoConfiguration?

`@AutoConfiguration` belongs to the `org.springframework.boot.autoconfigure` package. It is the dedicated annotation for marking a Spring Boot auto-configuration class.

~~~java
import org.springframework.boot.autoconfigure.AutoConfiguration;

@AutoConfiguration
public class AcmeClientAutoConfiguration {
}
~~~

At its core, `@AutoConfiguration` is a form of `@Configuration` with `proxyBeanMethods = false`. This fits how auto-configurations are structured: `@Bean` methods should receive dependencies through parameters rather than calling each other directly and relying on a CGLIB proxy.

For example:

~~~java
@AutoConfiguration
public class AcmeClientAutoConfiguration {

    @Bean
    AcmeClientService acmeClientService(AcmeClient client) {
        return new AcmeClientService(client);
    }
}
~~~

Spring resolves the `AcmeClient` parameter as a bean dependency. You should not call `acmeClient()` directly from another `@Bean` method in the same class expecting the container to intercept it as with a full configuration proxy.

Conditional annotations can be used on the auto-configuration class or on individual `@Bean` methods. Commonly used annotations include:

- `@ConditionalOnClass`: applies when a class is present on the classpath.
- `@ConditionalOnMissingBean`: applies when no matching bean exists yet.
- `@ConditionalOnBean`: applies when a matching bean already exists.
- `@ConditionalOnProperty`: applies when a configuration property matches.
- `@ConditionalOnWebApplication` and `@ConditionalOnNotWebApplication`: apply based on the web application type.

## 3. Publishing candidate configurations in Spring Boot 3

In Spring Boot 3, a library publishes auto-configuration classes in the resource:

~~~text
src/main/resources/
└── META-INF/
    └── spring/
        └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

The `AutoConfiguration.imports` file contains the fully qualified name of each auto-configuration class, one class per line. For example:

~~~text
com.example.acme.autoconfigure.AcmeClientAutoConfiguration
com.example.acme.autoconfigure.AcmeMetricsAutoConfiguration
~~~

When the library is packaged as a JAR, this resource file resides in the JAR and can be read by Spring Boot when an application uses the library.

A few points to remember:

- The path and file name must be exact.
- Each line must be a fully qualified class name, including its package.
- Listed classes must be on the classpath when candidates are processed.
- Do not list a regular configuration class just because you want component scan to find it; this list is specifically for auto-configuration.
- Published classes must be loadable and parseable under their corresponding classpath conditions.

### How are candidates discovered?

`@SpringBootApplication` includes `@EnableAutoConfiguration`. This annotation brings `AutoConfigurationImportSelector` into configuration parsing. The selector uses the published candidate list to gather auto-configurations, then applies filters, exclusion lists, and configuration ordering.

You can picture the overall flow:

~~~text
@SpringBootApplication
        |
        v
@EnableAutoConfiguration
        |
        v
AutoConfigurationImportSelector
        |
        v
Read AutoConfiguration.imports
        |
        v
Set of candidate auto-configurations
        |
        +--> Apply exclusions and filters
        |
        +--> Sort by before / after relationships
        |
        v
Parse configurations and evaluate conditions
        |
        v
Register matching bean definitions
~~~

Having a class name in the imports file only means that class is a candidate. It does not guarantee that every bean in the class will be created. Conditions on the class and bean methods still decide which configurations are actually applied.

## 4. Example of building an auto-configuration

Suppose the Acme library provides `AcmeClient` and applications want to receive a default `AcmeClientService` bean. The types `AcmeClient`, `AcmeClientProperties`, and `AcmeClientService` below represent the library's API.

~~~java
package com.example.acme.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(AcmeClient.class)
@ConditionalOnProperty(
        prefix = "acme.client",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
@EnableConfigurationProperties(AcmeClientProperties.class)
public class AcmeClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    AcmeClient acmeClient(AcmeClientProperties properties) {
        return AcmeClient.connect(properties.getEndpoint());
    }

    @Bean
    @ConditionalOnMissingBean
    AcmeClientService acmeClientService(AcmeClient client) {
        return new AcmeClientService(client);
    }
}
~~~

The configuration has three groups of conditions and behaviors:

1. `@ConditionalOnClass(AcmeClient.class)` requires the Acme client library to be on the classpath.
2. `@ConditionalOnProperty` lets users disable the integration via `acme.client.enabled=false`. If the property is missing, `matchIfMissing = true` allows the default configuration to apply.
3. `@ConditionalOnMissingBean` registers default beans only when the application has not already provided a suitable replacement.

Properties can be set in `application.yml`:

~~~yaml
acme:
  client:
    enabled: true
    endpoint: https://api.example.test
~~~

The application only needs to declare the Acme library dependency. Once the auto-configuration is discovered and conditions match, Spring Boot registers the default beans.

In a real library, make sure `AcmeClientProperties` is defined with `@ConfigurationProperties("acme.client")` and has getters or record accessors matching how it is accessed. Initializing the client should also handle timeouts, authentication, and resource cleanup according to the library's API.

### Allowing the application to override default beans

If the application needs to configure the client in its own way, it can declare the bean itself:

~~~java
@Configuration
public class CustomAcmeConfiguration {

    @Bean
    AcmeClient acmeClient() {
        return AcmeClient.connect("https://internal.example.test");
    }
}
~~~

Because the auto-configuration uses `@ConditionalOnMissingBean`, the application-provided bean causes the corresponding default bean not to be registered. This is one of Spring Boot's key conventions: auto-configuration provides replaceable defaults.

`@ConditionalOnMissingBean` should generally be placed on methods providing default beans so the application can replace individual components. Placing the condition at the class level could cause the entire configuration class to be skipped when one matching bean exists, including other beans the application still needs.

## 5. Ordering of candidate auto-configurations

Some auto-configurations depend on beans or configurations provided by another auto-configuration. `@AutoConfiguration` supports declaring ordering relationships via attributes:

- `before` and `beforeName`: this configuration is processed before the specified configurations.
- `after` and `afterName`: this configuration is processed after the specified configurations.

For example, an integration configuration that needs to be processed after the DataSource configuration:

~~~java
@AutoConfiguration(
        afterName = "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration"
)
public class AcmeJdbcAutoConfiguration {
}
~~~

You can use the `after` attribute with a class literal if there is a direct dependency on that auto-configuration class:

~~~java
@AutoConfiguration(after = DataSourceAutoConfiguration.class)
public class AcmeJdbcAutoConfiguration {
}
~~~

String class names are useful when you do not want a compile-time link to an optional auto-configuration. Make sure the fully qualified name is exact when using `afterName` or `beforeName`.

This ordering controls the processing order of auto-configuration classes during configuration registration. It is not a mechanism to guarantee instantiation order of every bean instance. If a bean needs another dependency, declare it through `@Bean` method parameters or a constructor so Spring manages the relationship properly.

Do not use `@DependsOn` or auto-configuration ordering merely to hide an undeclared dependency. Express bean relationships with dependency injection first; use before/after only when the order between auto-configuration classes genuinely affects condition evaluation or bean definition registration.

## 6. Excluding an auto-configuration

Applications can exclude unwanted auto-configurations. With `@SpringBootApplication` or `@EnableAutoConfiguration`, you can use `exclude`:

~~~java
@SpringBootApplication(
        exclude = AcmeClientAutoConfiguration.class
)
public class Application {
}
~~~

If you do not want to reference the class directly, you can use `excludeName` with the fully qualified name:

~~~java
@SpringBootApplication(
        excludeName = "com.example.acme.autoconfigure.AcmeClientAutoConfiguration"
)
public class Application {
}
~~~

You can also configure this via properties:

~~~yaml
spring:
  autoconfigure:
    exclude:
      - com.example.acme.autoconfigure.AcmeClientAutoConfiguration
~~~

Excluding a candidate means Spring Boot does not apply that auto-configuration when building the context. If the application still needs beans provided by that configuration, it must declare a replacement configuration itself or choose another library providing equivalent functionality.

Excluding an auto-configuration does not remove the dependency from the classpath. The JAR can still exist in the application; only the configuration selected through the auto-configuration mechanism is omitted from application.

## 7. How does auto-configuration differ from component scanning?

Component scanning discovers stereotypes such as `@Component`, `@Service`, `@Repository`, `@Controller`, and configuration classes within the scanned package scope.

Auto-configuration is discovered from the candidate list published by a library in `AutoConfiguration.imports`, and then brought in through Spring Boot's import mechanism.

This difference matters when packaging a starter:

- Component scanning depends on the application's root package and scan scope.
- Auto-configuration can live in a separate library package, outside the application's scanned packages.
- Auto-configuration conditions ensure beans appear only when the classpath, properties, or existing beans satisfy requirements.

Because `@AutoConfiguration` is a form of `@Configuration`, you should not place auto-configuration classes in subpackages scanned by the application as regular components. Let them be discovered via the imports list. This keeps a clean boundary between a library's automatic configuration and configuration explicitly declared by the application.

## 8. Organizing starters and resources

A starter typically has two parts:

- A starter artifact that aggregates dependencies so applications can easily add a feature.
- An auto-configuration module containing the auto-configuration classes and candidate registration file.

Example structure of an auto-configuration module:

~~~text
acme-spring-boot-autoconfigure/
├── src/main/java/
│   └── com/example/acme/autoconfigure/
│       ├── AcmeClientAutoConfiguration.java
│       └── AcmeClientProperties.java
└── src/main/resources/
    └── META-INF/spring/
        └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Imports file content:

~~~text
com.example.acme.autoconfigure.AcmeClientAutoConfiguration
~~~

When building the JAR, verify that the resource is packaged at the exact path. You can open the JAR or list its contents to confirm the file exists:

~~~bash
jar tf acme-spring-boot-autoconfigure.jar
~~~

The output should include the path `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` alongside the compiled auto-configuration classes.

If the file is missing from the JAR, applications consuming the library will not find the candidate even though the configuration class exists in bytecode. If the class name in the file has the wrong package or a typo, importing can fail when the candidate is processed.

## 9. Testing auto-configuration

Auto-configuration should be tested independently of a full application. Spring Boot provides `ApplicationContextRunner` to create a small context, load a set of auto-configurations, and inspect registered beans.

For example:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class AcmeClientAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    AcmeClientAutoConfiguration.class
                            )
                    );

    @Test
    void createsDefaultBeansWhenEnabled() {
        contextRunner
                .withPropertyValues("acme.client.enabled=true")
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(AcmeClient.class);
                    assertThat(context)
                            .hasSingleBean(AcmeClientService.class);
                });
    }

    @Test
    void backsOffWhenDisabled() {
        contextRunner
                .withPropertyValues("acme.client.enabled=false")
                .run(context -> {
                    assertThat(context)
                            .doesNotHaveBean(AcmeClient.class);
                    assertThat(context)
                            .doesNotHaveBean(AcmeClientService.class);
                });
    }
}
~~~

Beyond enabled and disabled cases, you should also test:

- When the application provides its own `AcmeClient`, whether the default bean is skipped.
- When the client class is absent from the classpath, whether the auto-configuration is skipped.
- When the property is missing, whether `matchIfMissing` produces the expected behavior.
- When multiple related auto-configurations exist, whether ordering and conditions produce the right result.
- When excluding an auto-configuration, whether the beans it provides disappear as expected.

To test classpath conditions, you can use `FilteredClassLoader` in Spring Boot Test to simulate a missing optional library. For auto-configurations requiring a servlet or reactive web stack, use the appropriate context runner to verify conditions by context type.

Spring Boot Actuator can also provide the `conditions` endpoint to diagnose why an auto-configuration matched or did not match. This is a useful tool when analyzing a running application; enabling and securing the endpoint must follow the application's operational policy.

## 10. Common mistakes when declaring candidates

### Creating the @AutoConfiguration class but forgetting the imports file

The annotation marks the role of the class, but it does not automatically make the class a candidate. Without an entry in `AutoConfiguration.imports`, the auto-configuration mechanism has no class name to discover.

### Adding the class to the imports file with the wrong package or class name

Spring Boot reads class names from the resource. A wrong name can break importing. Use fully qualified class names and check the JAR contents after building.

### Placing the auto-configuration class in a component-scanned package

The class can be scanned as a normal configuration, defeating the purpose of discovery through the candidate list and potentially causing conditions or processing order to differ from expectations. Place auto-configurations in a separate package outside the application's scan scope.

### Not using @ConditionalOnMissingBean for default beans

If auto-configuration always registers default beans, the application may be unable to replace them or encounter multiple candidates of the same type. Use appropriate conditions so auto-configuration backs off when users provide custom beans.

### Confusing auto-configuration order with bean creation order

`before` and `after` order the processing of configuration classes. They do not replace constructor injection, `@Bean` method parameters, or actual dependency relationships.

### Using the legacy registration mechanism for auto-configuration lists in Boot 3

In Spring Boot 3, the auto-configuration list is published using `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`. Do not continue adding auto-configuration classes to the `EnableAutoConfiguration` key in `spring.factories` as in older guides. `spring.factories` can still be used for some other extension points; what must change is the mechanism for publishing auto-configuration candidates.

## 11. Workflow for building auto-configuration

When creating an auto-configuration for a library, you can follow this sequence:

1. Identify the default functionality the library wants to provide.
2. Create a configuration class annotated with `@AutoConfiguration`.
3. Add appropriate classpath, property, web application, or bean conditions.
4. Use `@ConditionalOnMissingBean` for default beans that the application should be able to replace.
5. Declare candidate classes in `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.
6. Specify `before` or `after` when auto-configuration processing order is genuinely needed.
7. Test match, non-match, custom bean, and optional dependency cases.
8. Verify that the JAR packages the resource at the exact path and that consuming applications can discover the configuration.

`@AutoConfiguration` marks an auto-configuration class; the `AutoConfiguration.imports` file publishes those classes as candidates. Spring Boot discovers, sorts, and evaluates conditions before registering bean definitions. Once you understand both parts, you can build starters that provide convenient defaults while still allowing applications to override and control the integrations they actually need.
