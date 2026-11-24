# Choosing the customization level: property, customizer, bean, or replacing configuration

Spring Boot provides multiple extension points for applications to adjust default behavior. When you need to change a value, add a processing step, or completely replace how a component is created, you can choose between a configuration property, a customizer, an application-provided bean, or replacing the entire configuration.

These approaches differ in scope of impact. You should start with the smallest extension point that satisfies the requirement. A property is usually enough for changing a value; a customizer fits when you need to add behavior to an object Boot is building; a custom bean fits when you need to replace an implementation; and replacing configuration should only be used when you need to control most of the bean registration and wiring process.

## 1. Look at the scope of change before choosing a customization approach

Suppose an application has a client that calls the Catalog service. The following requirements might arise:

- Change the endpoint or timeout per environment.
- Add a default header or interceptor for requests.
- Use a different client implementation.
- Change how the client is created, register multiple dependent components, and control the entire default configuration.

Each requirement should be solved at the appropriate level:

| Customization level | Use when | Example |
|---|---|---|
| Property | Only changing a value that is already supported | Endpoint, timeout, enabling/disabling a feature |
| Customizer | Keeping the default object and creation mechanism, only adding or adjusting part of the behavior | Adding headers, converters, interceptors, MVC mappings |
| Bean | Needing to replace a component or provide a custom implementation | Replacing the default client with a custom client |
| Replace configuration | Needing to control most or all of how related beans are registered | Excluding auto-configuration and declaring configuration manually |

You can picture the increasing level of impact:

~~~text
Property
   |
   v
Customizer
   |
   v
Custom bean
   |
   v
Replace / exclude configuration
~~~

This is not a mandatory Spring order. It is a way of thinking to avoid replacing too many components when the requirement only needs a small adjustment.

## 2. Level 1: use a property for value changes

Configuration properties are the first choice when the application already supports adjusting a value without changing how beans are created.

For example, the endpoint and timeout of the Catalog client vary by environment. They can be declared in `application.yml`:

~~~yaml
app:
  catalog:
    base-url: https://catalog.example.test
    connect-timeout: 2s
    enabled: true
~~~

Create a class to receive the properties:

~~~java
import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.catalog")
public class CatalogProperties {

    private URI baseUrl = URI.create("https://catalog.example.test");
    private Duration connectTimeout = Duration.ofSeconds(2);
    private boolean enabled = true;

    public URI getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(URI baseUrl) {
        this.baseUrl = baseUrl;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
~~~

Register the properties class using `@EnableConfigurationProperties`:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(CatalogProperties.class)
public class CatalogConfiguration {
}
~~~

Beans can receive `CatalogProperties` via dependency injection:

~~~java
@Bean
CatalogClient catalogClient(CatalogProperties properties) {
    return new CatalogClient(
            properties.getBaseUrl(),
            properties.getConnectTimeout()
    );
}
~~~

At deployment time, the same artifact can use different values per environment. Values can come from `application.yml`, a separate configuration file, environment variables, or command-line arguments. Spring Boot merges configuration sources according to Environment precedence rules.

For example, the environment variable corresponding to `app.catalog.connect-timeout` is:

~~~bash
APP_CATALOG_CONNECTTIMEOUT=5s
~~~

Spring Boot's environment variable naming rules convert dotted property names to uppercase with underscores; hyphens in property names are removed. You should keep variable names aligned with relaxed binding rules.

### When is a property enough?

Use a property when:

- The behavior to adjust is already supported by the existing component.
- The difference only lies in values, such as a URL, timeout, retry count, or limit.
- There is no need to change the bean type or dependency structure.
- Operators need to change values per environment without modifying code.

You should not create a new customizer or bean just to change a value for which Spring Boot already provides a corresponding property.

If a custom-written library has multiple related properties, grouping them with `@ConfigurationProperties` keeps the configuration structure clear, validatable, and easy to test. Avoid scattering many `@Value` strings across services if they belong to the same configuration group.

## 3. Level 2: use a customizer to adjust an object Boot creates

A customizer fits when you want to keep Spring Boot's default object creation mechanism but need to add some behavior. Instead of recreating the entire bean yourself, the application provides a callback to adjust the object during configuration.

Some common extension points:

- `WebMvcConfigurer`: adds configuration for Spring MVC.
- `Jackson2ObjectMapperBuilderCustomizer`: adjusts the Jackson builder that Boot uses.
- `RestTemplateCustomizer`: customizes `RestTemplate` instances created via Boot's builder.
- `WebClientCustomizer`: customizes `WebClient.Builder` configured by Boot.

These interfaces have their own contracts. Check which component invokes the customizer and at what time before assuming every instance receives the change.

### Example: customizing Jackson while keeping default configuration

If you want Jackson to omit null-valued properties when serializing, you can provide a `Jackson2ObjectMapperBuilderCustomizer`:

~~~java
import com.fasterxml.jackson.annotation.JsonInclude;
import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class JacksonCustomization {

    @Bean
    Jackson2ObjectMapperBuilderCustomizer omitNullProperties() {
        return builder -> builder.serializationInclusion(
                JsonInclude.Include.NON_NULL
        );
    }
}
~~~

Spring Boot applies the customizer to the builder used to construct the auto-configured `ObjectMapper`. Other default Boot settings are preserved and combined with this change.

This is the right approach when you only need to adjust part of the Jackson configuration. If you declare a new `ObjectMapper` yourself, the default auto-configuration may back off and the application becomes responsible for all required settings.

### Example: adding MVC configuration with WebMvcConfigurer

If you need to add a CORS mapping for a group of APIs, you can implement `WebMvcConfigurer`:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class ApiMvcCustomization implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedMethods("GET", "POST")
                .allowedOrigins("https://portal.example.test");
    }
}
~~~

Spring Boot detects the additional MVC configuration and combines `WebMvcConfigurer` callbacks with MVC auto-configuration. This keeps Boot's default MVC configuration while adding the needed mapping.

If you only want to extend MVC, do not add `@EnableWebMvc` casually. That annotation switches the application into manual MVC configuration control mode and causes Boot's MVC auto-configuration to back off. Only use it when you truly want to take responsibility for configuring MVC on a broader scale.

### Customizers can be applied multiple times

Some extension points can be implemented by multiple customizer beans at once. In that case, the order and combination behavior depend on the specific API. Some customizers support `Ordered` or `@Order`; do not assume every interface follows the same rule.

If a customizer is applied to a shared builder or multiple instances created from that builder, the change can affect multiple objects. Clearly identify the scope of objects receiving the callback before adding stateful behavior.

## 4. Level 3: provide a custom bean to replace an implementation

If properties and customizers are not enough because you need to replace the implementation itself, the application can provide its own bean.

Spring Boot auto-configuration commonly uses `@ConditionalOnMissingBean` to register a default bean only when no matching bean exists yet. For example:

~~~java
@AutoConfiguration
public class CatalogAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(CatalogClient.class)
    CatalogClient catalogClient(CatalogProperties properties) {
        return new DefaultCatalogClient(
                properties.getBaseUrl(),
                properties.getConnectTimeout()
        );
    }
}
~~~

The application can provide its own implementation:

~~~java
@Configuration(proxyBeanMethods = false)
public class CustomCatalogConfiguration {

    @Bean
    CatalogClient catalogClient(CatalogProperties properties) {
        return new ResilientCatalogClient(
                properties.getBaseUrl(),
                properties.getConnectTimeout()
        );
    }
}
~~~

When the custom bean is registered, the auto-configuration's `@ConditionalOnMissingBean(CatalogClient.class)` condition no longer matches. The default bean is skipped and components depending on `CatalogClient` receive the implementation provided by the application.

This approach fits when the application needs to replace one component while other parts of the auto-configuration remain useful.

### Distinguishing bean replacement from @Primary and @Qualifier

Not every configuration uses `@ConditionalOnMissingBean`. If two beans coexist, Spring may need rules to pick a candidate when injecting:

- `@Primary` marks the preferred bean when injecting by type and multiple matching candidates exist.
- `@Qualifier` explicitly specifies a candidate by qualifier.
- `@ConditionalOnMissingBean` decides whether the default bean is registered at all.

For example, `@Primary` does not make the other bean disappear:

~~~java
@Bean
@Primary
CatalogClient primaryCatalogClient() {
    return new ResilientCatalogClient();
}

@Bean
CatalogClient fallbackCatalogClient() {
    return new DefaultCatalogClient();
}
~~~

Both beans still exist in the context. When a service injects `CatalogClient` without a qualifier, the primary bean is preferred. If the goal is to register only one implementation per configuration, use appropriate conditions or configuration rules instead of treating `@Primary` as a bean replacement mechanism.

### When should you replace a bean?

Provide a custom bean when:

- You need to replace the default implementation.
- You need to control how a specific component is created.
- The remaining beans and settings of the auto-configuration are still appropriate.
- The auto-configuration supports back-off via `@ConditionalOnMissingBean`, or exposes a clear bean extension point.

Before adding a bean, check the auto-configuration's conditions. If the default bean has no back-off condition and is still registered, the application may encounter bean name conflicts or multiple candidates of the same type.

## 5. Level 4: replace or exclude configuration

Sometimes a requirement changes more than a single bean. For example, an application needs to organize multiple related beans itself, use a different library, or replace an integration approach that the default auto-configuration does not support.

In that case, you can exclude the auto-configuration and declare a replacement configuration.

~~~java
@SpringBootApplication(
        exclude = CatalogAutoConfiguration.class
)
public class Application {
}
~~~

Or exclude by class name:

~~~java
@SpringBootApplication(
        excludeName = "com.example.catalog.autoconfigure.CatalogAutoConfiguration"
)
public class Application {
}
~~~

You can also use a configuration property:

~~~yaml
spring:
  autoconfigure:
    exclude:
      - com.example.catalog.autoconfigure.CatalogAutoConfiguration
~~~

After excluding, the application must declare the required beans itself:

~~~java
@Configuration(proxyBeanMethods = false)
public class ApplicationCatalogConfiguration {

    @Bean
    CatalogClient catalogClient(CatalogProperties properties) {
        return new ResilientCatalogClient(
                properties.getBaseUrl(),
                properties.getConnectTimeout()
        );
    }

    @Bean
    CatalogService catalogService(CatalogClient client) {
        return new CatalogService(client);
    }
}
~~~

Excluding an auto-configuration prevents that class from participating in the auto-configuration mechanism. If that class provides multiple beans, the application needs to identify which beans are still needed and redeclare the necessary parts. Do not exclude an entire configuration just to replace one bean if a back-off condition already solves the requirement.

### When you want to control an entire framework

Some frameworks provide an annotation to enable manual configuration. For example, `@EnableWebMvc` lets the application control MVC itself and causes Spring Boot's MVC auto-configuration to back off. This is a large-scope change: the application may have to manually declare components that Boot normally provides, such as resource handling, message converters, and other MVC settings.

Therefore, if you only need to add an interceptor, formatter, or CORS mapping, prefer extension points like `WebMvcConfigurer`. Only enable manual configuration when you truly need to control the entire integration.

## 6. Which level to choose in common scenarios?

| Requirement | Recommended level | Reason |
|---|---|---|
| Change API URL between local and production | Property | Only changing a value |
| Change timeout already supported by the library | Property | No need to create a new bean |
| Add a default header to an HTTP client builder | Customizer | Keeps Boot's builder and configuration |
| Add a CORS mapping in Spring MVC | Customizer / WebMvcConfigurer | Adds a portion of MVC configuration |
| Adjust Jackson serialization rules | Jackson customizer | Keeps the auto-configured ObjectMapper |
| Use a custom client implementation | Custom bean | Replaces exactly the component that needs changing |
| Need multiple related beans created with custom rules | Replace configuration | Requires controlling registration structure |
| Want to drop an entire default library integration | Exclude auto-configuration | Take full responsibility for replacement configuration |
| Want to manually control all of MVC | Manual MVC configuration | Changes the scope of auto-configuration |

Consider an end-to-end example: the application needs to call the Catalog API.

- If you only change the endpoint and timeout, configure `app.catalog.*`.
- If you need to add a trace header for requests, use the appropriate customizer for the HTTP client being used.
- If you need a client with a custom retry mechanism, provide a `CatalogClient` bean so the default auto-configuration backs off.
- If you need to replace how the client, cache, health indicator, and related beans are organized, consider excluding the auto-configuration and declaring a separate configuration.

## 7. Common mistakes when customizing

### Creating a new bean just to change a property

Creating a bean yourself can cause auto-configuration to back off or lose other default settings. If the library already supports a property, use the property first.

### Recreating an object when only a customizer is needed

A customizer usually lets you adjust a builder or object prepared by Boot. Creating a new object yourself may omit converters, codecs, message sources, metrics, or other default settings.

### Thinking @Primary replaces the default bean

`@Primary` only affects candidate selection during injection. It does not prevent the default bean from being registered. For auto-configuration to back off, an appropriate extension point or back-off condition is required.

### Adding @EnableWebMvc when you only want to supplement MVC

This annotation switches to manual MVC configuration and can lose Boot's automatic settings. Use `WebMvcConfigurer` for additive changes.

### Excluding too much auto-configuration

One auto-configuration can provide many beans. Excluding the entire class to replace one small bean forces the application to redeclare many components itself. Check first which beans can be replaced individually.

### Not checking configuration order and back-off conditions

`@ConditionalOnMissingBean` conditions are evaluated based on bean definitions processed up to that point. Boot's auto-configurations are organized to allow application configurations and higher-priority configurations to be evaluated first. With custom-written auto-configuration, you need to declare the right order and conditions, and test when the application provides a custom bean.

## 8. Verifying results after customizing

After changing a customization level, you need to confirm both the created beans and the final behavior.

You can verify across these cases:

1. No property declared: are default values used properly?
2. Property overridden: does the bean receive the new value?
3. Customizer present: does the Boot-created object receive the adjustment?
4. Application provides its own bean: does the default bean back off?
5. Auto-configuration excluded: are all replacement beans declared completely?
6. Running in a different profile or application type: do conditions create the right set of beans?

For auto-configuration, you can use `ApplicationContextRunner` to test configuration in a small context. Check beans by type, name, and properties; then check bean behavior if the change affects runtime.

If using Actuator, the `conditions` endpoint can help explain why an auto-configuration was applied or skipped. This endpoint must be configured and secured appropriately for the operating environment.

## 9. Decision process for choosing a customization level

When receiving a request to change Spring Boot behavior, you can follow these steps:

1. Identify the exact behavior or value that needs to change.
2. Check whether an existing Spring Boot or library property already meets the requirement.
3. If you need to add behavior to a builder or object Boot creates, look for the corresponding customizer extension point.
4. If you need to replace an implementation, check whether the auto-configuration supports `@ConditionalOnMissingBean` or a bean extension point.
5. Only exclude or replace the entire configuration when smaller levels do not meet the requirement.
6. Check the impact on other beans provided by the auto-configuration.
7. Test the default case, the customized case, and the disabled or replaced configuration case.

Each customization level addresses a different scope. Properties adjust configuration data; customizers add behavior to created objects; beans allow replacing a single component; replacing configuration hands broader control to the application. Choosing the right level helps preserve Spring Boot's useful defaults, reduces the number of components you must manage yourself, and clarifies the responsibility of application configuration.
