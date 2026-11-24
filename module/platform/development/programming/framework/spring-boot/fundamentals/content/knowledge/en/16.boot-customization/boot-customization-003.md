# Customizer functions and how to preserve the remaining defaults

Spring Boot provides many default configurations so applications can start up quickly: web servers, JSON converters, HTTP client builders, message converters, MVC infrastructure, and many other components. When you need to change one detail, the safe approach is usually to **customize the object or builder that Spring Boot has prepared**, adjusting only what is needed and letting the rest of the configuration continue working.

This is the purpose of the **customizer** pattern: a callback that receives a configuration object or builder, then changes a few properties before the object is used. In Spring Boot, many extension points are designed as interfaces with a `customize(...)` method. Applications can register a customizer as a bean; Spring Boot collects and applies it at the appropriate configuration stage.

For example, if you only want to enable pretty printing for JSON, you can register a `Jackson2ObjectMapperBuilderCustomizer` to enable that single feature. There is no need to create the entire `ObjectMapper` yourself. If you only want to change the web server port, you can use `WebServerFactoryCustomizer` to modify the port of the factory Boot is configuring, rather than building an entire server factory from scratch.

This lesson focuses on how customizers work, common extension points, the order in which multiple customizers are applied, and how to avoid accidentally replacing useful Spring Boot defaults.

## 1. What is a customizer?

A **customizer** is a component that receives an object already created or prepared by the framework, and then adjusts that object according to the application's needs. It usually represents a small, targeted configuration action.

You can picture it as:

~~~text
Spring Boot prepares builder / factory
                 |
                 v
        Apply customizer
                 |
                 v
        Customized object
                 |
                 v
     Build / initialize / use
~~~

General Java example:

~~~java
public interface Customizer<T> {
    void customize(T target);
}
~~~

This illustrates a generic contract, not a claim that every Spring Boot customizer API uses this exact interface. Many APIs have specialized interfaces, such as `WebServerFactoryCustomizer<T>` or `Jackson2ObjectMapperBuilderCustomizer`.

A customizer typically has these characteristics:

- Receives a target object, such as a builder, factory, or client.
- Only makes changes relevant to its responsibility.
- Does not own the entire object creation process.
- Is invoked at a defined point during configuration.
- Can be registered as a bean so the framework automatically discovers and applies it.

### How does a customizer differ from a factory method?

A factory method creates an object:

~~~java
@Bean
public PaymentClient paymentClient() {
    return new PaymentClient();
}
~~~

A customizer adjusts an object that another mechanism creates or provides:

~~~java
@Bean
public PaymentClientCustomizer paymentClientCustomizer() {
    return client -> client.setConnectTimeout(Duration.ofSeconds(3));
}
~~~

`PaymentClientCustomizer` in the second example is a hypothetical application interface. It illustrates separating the configuration action from object creation.

A factory returns an instance; a customizer typically receives a target and mutates it. The two mechanisms can be combined, but they handle different responsibilities.

## 2. Why customize instead of recreating everything yourself?

Suppose Spring Boot is configuring Jackson to process JSON. The default configuration may include:

- Modules supporting Java data types.
- Module discovery and registration.
- Naming strategy and related settings.
- Integrations with Spring MVC message converters.
- Other customizers provided by the application or libraries.

If the application creates a new `ObjectMapper` itself:

~~~java
@Bean
public ObjectMapper objectMapper() {
    return new ObjectMapper();
}
~~~

the application-provided bean can cause Boot's default auto-configuration to yield. The new mapper may no longer receive all the configuration Boot applied to the default builder, unless the application reconfigures the needed parts itself.

If the goal is just to enable pretty printing, a customizer is usually more appropriate:

~~~java
@Bean
public Jackson2ObjectMapperBuilderCustomizer jsonCustomizer() {
    return builder ->
            builder.featuresToEnable(
                    SerializationFeature.INDENT_OUTPUT
            );
}
~~~

The customizer changes one feature on the builder used by Spring Boot. Other modules and default configurations still have the opportunity to be applied.

### Keeping defaults does not mean changing nothing

When using a customizer, the application still changes configuration. What matters is **bounded change**: only modifying the needed properties without replacing the entire object graph or the whole auto-configuration mechanism.

A practical rule:

> If the need is just to adjust a few properties, look for an extension point or builder customizer before declaring a complete replacement bean.

## 3. How does Spring Boot find and apply customizers?

A customizer is usually registered as a bean:

~~~java
@Configuration
public class JsonConfiguration {

    @Bean
    public Jackson2ObjectMapperBuilderCustomizer jsonCustomizer() {
        return builder -> {
            // Adjust the builder here.
        };
    }
}
~~~

Spring Boot can collect beans of the corresponding customizer type and apply them when configuring the builder or factory.

High-level flow:

~~~text
ApplicationContext
       |
       +--> customizer A
       |
       +--> customizer B
       |
       +--> customizer C
                |
                v
      Spring Boot collects customizers
                |
                v
       Apply by contract / order
                |
                v
       Completed builder or factory
                |
                v
       Create runtime component
~~~

Not all customizers in the ecosystem are applied via the exact same mechanism. Each extension point can have its own collection method, ordering, and invocation timing. Therefore, when using a specific interface, you need to understand that interface's contract.

### Customizers are typically applied at startup

Customizers for web server factories, Jackson builders, or HTTP clients are usually applied during the application configuration phase. They are not callbacks invoked on every HTTP request.

If you need to change behavior based on request data, use a controller, interceptor, filter, strategy, or appropriate runtime API. Do not use a startup customizer to store per-user state.

## 4. Customizing the web server while keeping default configuration

Spring Boot can auto-configure an embedded web server based on starters and application configuration. If you only need to change a property on the server factory, you can use `WebServerFactoryCustomizer`.

For example:

~~~java
package com.example.store.config;

import org.springframework.boot.web.server.ConfigurableWebServerFactory;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class WebServerConfiguration {

    @Bean
    public WebServerFactoryCustomizer<ConfigurableWebServerFactory>
            webServerCustomizer() {

        return factory -> factory.setPort(8081);
    }
}
~~~

The customizer above only changes the port. Other settings provided by Spring Boot and the server factory can continue to be applied, such as SSL, compression, error handling, or other server settings if configured in the right place.

In a simple application, if you only need to change the port, property configuration is usually clearer:

~~~yaml
server:
  port: 8081
~~~

Use a customizer when you need to call a factory API to customize a detail that has no suitable property, or when you need to perform configuration in Java.

### Tomcat-specific customization

If the application uses embedded Tomcat and needs to change a connector property, you can use the specific factory type:

~~~java
@Bean
public WebServerFactoryCustomizer<TomcatServletWebServerFactory>
        tomcatCustomizer() {

    return factory -> factory.addConnectorCustomizers(connector -> {
        connector.setMaxParameterCount(1000);
    });
}
~~~

This example depends on Tomcat and its corresponding version API. If the application switches to Jetty or Undertow, the Tomcat-specific customizer is no longer applicable. For configuration usable across multiple servers, prefer the general interface `ConfigurableWebServerFactory`.

### Do not replace WebServerFactory yourself if you only need to tweak one property

A self-created factory bean can cause Boot auto-configuration to yield, depending on bean type and configuration conditions. The application then becomes responsible for many settings that Boot previously provided.

Ask yourself:

- Is there a standard property that solves the need?
- Is there a corresponding `WebServerFactoryCustomizer`?
- Can the exact property be adjusted on the existing factory?
- Is it truly necessary to replace the embedded server or factory?

## 5. Customizing Jackson while keeping Spring Boot's JSON configuration

Spring Boot uses Jackson in many applications for JSON conversion. Instead of declaring a new `ObjectMapper` for a small change, you can use `Jackson2ObjectMapperBuilderCustomizer`.

Example enabling pretty printing:

~~~java
package com.example.store.config;

import com.fasterxml.jackson.databind.SerializationFeature;
import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class JsonConfiguration {

    @Bean
    public Jackson2ObjectMapperBuilderCustomizer jsonCustomizer() {
        return builder -> builder
                .featuresToEnable(
                        SerializationFeature.INDENT_OUTPUT
                );
    }
}
~~~

This customizer asks the builder to enable the `SerializationFeature.INDENT_OUTPUT` feature. Other configurations Spring Boot prepared for Jackson still have the opportunity to be applied while the builder is configured, unless another customizer or configuration alters them.

You can adjust an additional feature:

~~~java
@Bean
public Jackson2ObjectMapperBuilderCustomizer jacksonCustomizer() {
    return builder -> builder
            .featuresToEnable(
                    SerializationFeature.INDENT_OUTPUT
            )
            .featuresToDisable(
                    DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES
            );
}
~~~

To use this snippet, you need to import `DeserializationFeature`. The example only illustrates the API; choosing to ignore unknown JSON fields affects API contract validation and the ability to detect clients sending invalid data. Do not toggle features just to make requests "pass more easily"; base it on API requirements.

### Customizers can add modules

The Jackson builder also supports registering modules or configuring naming/serialization per the corresponding API. When a custom module is needed, you can pass the module to the builder or register a `Module` bean via the mechanism Boot supports.

The key point is to leverage the Boot-managed builder. If you create a new mapper yourself, verify that modules, naming strategies, date/time handling, and message converter integrations are all reconfigured completely.

### When should you create a separate ObjectMapper?

There are cases requiring a specialized mapper, such as:

- An internal file format that differs from API JSON.
- A third-party protocol with its own serialization rules.
- An export task requiring a different naming strategy.
- A mapper used only within one module without replacing the application-wide HTTP mapper.

In those cases, you can create a bean with a qualifier or use a separate builder with a clear name. Do not accidentally replace the application-wide default mapper when the need is limited to one use case.

## 6. Customizing MVC while keeping Spring Boot MVC defaults

Spring MVC has the `WebMvcConfigurer` interface for applications to add MVC settings. Although its name does not include "Customizer", it provides similar configuration callbacks.

Example adding an interceptor:

~~~java
package com.example.store.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class MvcConfiguration implements WebMvcConfigurer {

    private final RequestAuditInterceptor auditInterceptor;

    public MvcConfiguration(RequestAuditInterceptor auditInterceptor) {
        this.auditInterceptor = auditInterceptor;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(auditInterceptor)
                .addPathPatterns("/api/**");
    }
}
~~~

In Spring Boot MVC, providing a `WebMvcConfigurer` typically lets you add callbacks while keeping MVC auto-configuration active. This is the right approach when you only want to add interceptors, formatters, CORS mappings, or a few other MVC customizations.

### Why can @EnableWebMvc lose defaults?

Adding `@EnableWebMvc` switches the application to actively configuring Spring MVC and can cause Spring Boot's `WebMvcAutoConfiguration` to back off because its conditions are no longer met. The application may then have to manually configure parts Boot previously supplied.

If you only need to add an interceptor or converter, `@EnableWebMvc` is usually unnecessary. Using `WebMvcConfigurer` to supplement configuration generally preserves more defaults.

This does not mean `@EnableWebMvc` is always wrong. It is appropriate when the application genuinely wants full control over MVC configuration. But that is a decision to change the scope of configuration responsibility, not a simple way to add a callback.

### Only add converters when genuinely needed

`WebMvcConfigurer` has callbacks like `extendMessageConverters` and `configureMessageConverters`. The two methods have different meanings:

- `extendMessageConverters` allows modifying or adding converters after the default list has been established.
- `configureMessageConverters` can participate in configuring the converter list in a way that affects defaults.

If the goal is to **keep the default converters and add one converter**, you should usually consider `extendMessageConverters`. Check the contract of the Spring Framework version in use and converter ordering, because an earlier converter may handle processing before another converter.

## 7. Customizing RestTemplate via builder and customizer

Spring Boot provides `RestTemplateBuilder` to create `RestTemplate` instances with appropriate configuration. Instead of calling `new RestTemplate()` yourself, inject the builder:

~~~java
@Configuration
public class HttpClientConfiguration {

    @Bean
    public RestTemplate partnerRestTemplate(
            RestTemplateBuilder builder
    ) {
        return builder.build();
    }
}
~~~

The builder provided by Boot may already include message converters, request factories, customizers, and related configuration. Using the builder lets the application inherit those settings.

A customizer can adjust instances created from the builder:

~~~java
@Bean
public RestTemplateCustomizer partnerRestTemplateCustomizer() {
    return restTemplate -> {
        // Add required interceptor or error handler.
    };
}
~~~

`RestTemplateCustomizer` is Spring Boot's extension point for customizing `RestTemplate`. Customizers are applied by Boot to the builder/instance according to the version's corresponding mechanism.

If you create `RestTemplate` with `new RestTemplate()`, the application may bypass the configurations Boot prepared on the builder. When you need a special client, start from the builder and adjust further:

~~~java
@Bean
public RestTemplate partnerRestTemplate(
        RestTemplateBuilder builder
) {
    return builder
            .additionalCustomizers(
                    restTemplate -> {
                        // Customization specific to the partner client.
                    }
            )
            .build();
}
~~~

Builder APIs may vary slightly across Spring Boot versions. Use the methods available in the version your project runs.

### One client or multiple clients?

If an application has multiple partners with different timeouts, authentication, or error handling, you can create multiple `RestTemplate` beans with clear names/qualifiers, each built from `RestTemplateBuilder`. There is no need to replace the global builder just because one partner has unique requirements.

## 8. WebClient and reactive builders

For reactive applications, Spring Boot can provide a pre-configured `WebClient.Builder`. Inject the builder instead of creating a standalone builder if you want to keep shared settings such as codecs, observation, or connectors provided by Boot.

For example:

~~~java
@Configuration
public class ReactiveClientConfiguration {

    @Bean
    public WebClient catalogWebClient(WebClient.Builder builder) {
        return builder
                .baseUrl("https://catalog.example")
                .build();
    }
}
~~~

If multiple beans inject a mutable builder and mutate it themselves, understand whether the builder is shared or cloned according to the Spring Boot version's configuration mechanism. In versions supporting prototype or cloned builders, follow the approach documented for that version to avoid unintended changes to shared configuration.

A dedicated customizer such as `WebClientCustomizer` can be used when adjusting shared configuration for Boot-managed WebClient builders. For configuration specific to one client, customize the builder directly inside that client's factory method.

### Do not create WebClient manually when a pre-configured builder exists

~~~java
WebClient client = WebClient.create();
~~~

This is valid in plain Spring WebFlux, but it may not use the configurations Spring Boot puts into `WebClient.Builder`. If the application needs to keep Boot's defaults, observation, or codecs, use the injected builder.

## 9. Customize via properties first, use code when needed

Spring Boot provides many standard properties for common needs:

~~~yaml
server:
  port: 8081
  compression:
    enabled: true

spring:
  jackson:
    serialization:
      indent-output: true
~~~

If a property already expresses the need accurately, prefer that configuration because:

- It is easy to change between environments without editing code.
- It is clearly visible in configuration files.
- It can be inspected and managed via profiles or config sources.
- It has less coupling to implementation-specific APIs.

A customizer fits when properties are not expressive enough or you need to invoke an API on the target object. For example, a specific Tomcat connector setting may require a Java customizer.

### Choosing the right tool

| Need | Usually appropriate choice |
|---|---|
| Change web server port | `server.port` |
| Enable compression | `server.compression.enabled` |
| Enable JSON pretty print | `spring.jackson.serialization.indent-output` or Jackson customizer |
| Add MVC interceptor | `WebMvcConfigurer` |
| Adjust a web server property with no matching property | `WebServerFactoryCustomizer` |
| Adjust RestTemplates created from Boot builder | `RestTemplateCustomizer` |
| Create a separate RestTemplate per partner | Inject `RestTemplateBuilder`, then build separately |
| Adjust Jackson builder with Java logic | `Jackson2ObjectMapperBuilderCustomizer` |

A standard property is usually the easiest option to operate. A customizer is the next step when controlled API-level customization is needed.

## 10. Multiple customizers applied together: order matters

An application can have multiple customizers acting on the same target. For example:

- Customizer A enables compression.
- Customizer B changes the port.
- Customizer C configures the connector.
- Customizer D adjusts header limits.

If each customizer modifies a distinct property, they can usually coexist. However, if two customizers call setters on the same property, the result depends on application order.

For example:

~~~java
@Bean
@Order(10)
WebServerFactoryCustomizer<ConfigurableWebServerFactory> firstCustomizer() {
    return factory -> factory.setPort(8081);
}

@Bean
@Order(20)
WebServerFactoryCustomizer<ConfigurableWebServerFactory> secondCustomizer() {
    return factory -> factory.setPort(9090);
}
~~~

In extension points supporting ordering, customizers are sorted according to their order. In this illustrative example, the customizer with order 20 runs later and can override the port to 9090.

Do not rely on arbitrary bean discovery order. If multiple customizers can override the same property, you should:

1. Centralize ownership of the property in a single customizer.
2. Use `Ordered` or `@Order` if the extension point supports it.
3. Avoid having multiple environment configurations modify the same value.
4. Check the final result in the context or startup logs.

### Not all customizers share the same ordering rules

Some Boot extension points collect customizers using an ordered stream or comparator; other APIs have their own contracts. You cannot deduce that every interface named *Customizer* automatically honors `@Order`. Check the specific API and how the framework applies that collection.

### @Order differs from dependency order

`@Order` usually sorts elements in a collection or callback chain. It does not create bean dependencies, does not guarantee another bean is initialized first, and does not replace `@DependsOn`.

If a customizer needs another bean, declare the dependency via constructor or factory method. Do not rely on customizer order to ensure a bean instance has been created.

## 11. Additive customization and replacement customization

Not every API applies changes the same way.

**Additive customization**: adds an interceptor, converter, connector customizer, or module to an existing list. The result can include both default and new components.

**Replacement customization**: calls a setter to replace an existing value, such as changing port, timeout, or naming strategy. The new value can overwrite the previous value.

For example:

~~~java
factory.addConnectorCustomizers(connector -> {
    // Add a connector configuration action.
});
~~~

usually means appending a callback to the customizer list.

Whereas:

~~~java
factory.setPort(8081);
~~~

changes a single value. If another customizer calls `setPort(9090)` afterward, the final value can be 9090.

With builders, methods like `additionalInterceptors` usually mean additive; methods like `baseUrl` or `connectTimeout` usually set a value. API names can vary across versions, so read the contract rather than assuming every method is additive.

## 12. How to preserve the remaining defaults

This is the most important part of writing customizers. A small change can accidentally discard large parts of configuration if you create a bean that replaces everything.

### Principle 1: use the injected builder/factory

For example:

~~~java
@Bean
public RestTemplate partnerTemplate(RestTemplateBuilder builder) {
    return builder
            .build();
}
~~~

The Boot-provided builder may already contain shared configurations. Using that builder preserves the settings integrated by the framework.

### Principle 2: only modify the properties you need

~~~java
@Bean
public WebServerFactoryCustomizer<ConfigurableWebServerFactory>
        serverCustomizer() {
    return factory -> factory.setPort(8081);
}
~~~

There is no need to create a new factory if you only want to change the port.

### Principle 3: prefer additive extension points

For MVC, implement `WebMvcConfigurer` and override only the needed callbacks. Avoid enabling `@EnableWebMvc` if the goal is to add an interceptor while still wanting Boot to keep auto-configuration.

For Jackson, use a builder customizer instead of replacing the entire `ObjectMapper` if you only need one feature.

### Principle 4: do not unintentionally replace a default bean

Many Spring Boot auto-configurations use conditions like `@ConditionalOnMissingBean`. When an application declares a bean of the same type itself, the default configuration may back off. This is useful when you want to replace an entire implementation, but risky if you only want to tweak a property.

Before creating a replacement bean, check whether Boot has a corresponding customizer, builder, configurer, or property.

### Principle 5: keep specific configuration in the right scope

A global customizer can affect every client or server factory belonging to that extension point. If only one integration needs a custom timeout, build a separate client from the builder instead of changing a global customizer.

### Principle 6: do not unexpectedly override environment configuration

If a customizer always calls `setPort(8081)`, it may override `server.port` from the environment depending on application order. If you want properties to be the primary source of configuration, do not add a fixed setter inside the customizer. If conditional Java logic is needed, read `Environment` or configure typed properties explicitly.

## 13. Example: customizer adding only a default header to RestTemplate

Suppose an application calls partner APIs and wants to add a header identifying the application. You can use `RestTemplateCustomizer`:

~~~java
@Configuration
public class PartnerHttpConfiguration {

    @Bean
    public RestTemplateCustomizer applicationHeaderCustomizer() {
        return restTemplate -> {
            restTemplate.getInterceptors().add(
                    new ApplicationHeaderInterceptor("store-service")
            );
        };
    }

    @Bean
    public RestTemplate partnerRestTemplate(
            RestTemplateBuilder builder
    ) {
        return builder.build();
    }
}
~~~

`ApplicationHeaderInterceptor` is an application-defined class implementing `ClientHttpRequestInterceptor` that adds a header to requests. This example illustrates adding an interceptor without creating an independent RestTemplate manually.

If the header applies only to partner A, do not register a global customizer affecting every RestTemplate. Instead, attach the interceptor to the builder for that specific client:

~~~java
@Bean
public RestTemplate partnerARestTemplate(
        RestTemplateBuilder builder
) {
    return builder
            .additionalCustomizers(
                    new ApplicationHeaderInterceptor("store-service")
            )
            .build();
}
~~~

That way, shared configuration from the Boot builder is still used, while the specific change affects only client A.

## 14. Example: adding an MVC interceptor while keeping defaults

Suppose an application wants to record audits for APIs under `/api/**`. You can create an interceptor and register it via `WebMvcConfigurer`:

~~~java
@Component
public class RequestAuditInterceptor implements HandlerInterceptor {

    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler
    ) {
        // Record appropriate request metadata.
        return true;
    }
}
~~~

~~~java
@Configuration
public class AuditMvcConfiguration implements WebMvcConfigurer {

    private final RequestAuditInterceptor interceptor;

    public AuditMvcConfiguration(RequestAuditInterceptor interceptor) {
        this.interceptor = interceptor;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(interceptor)
                .addPathPatterns("/api/**");
    }
}
~~~

This configuration adds the interceptor to MVC. There is no need to redeclare handler mappings, message converters, exception resolvers, or the entire MVC infrastructure.

In real applications, interceptors should not log entire bodies or sensitive data indiscriminately. If reading/logging the request body is needed, consider buffering, size limits, and appropriate filters.

## 15. Example: customizing Jackson without losing the Java Time module

An application uses Jackson to serialize `LocalDateTime` types. Spring Boot can configure the Java Time module in the default mapper.

If you create it yourself:

~~~java
@Bean
public ObjectMapper objectMapper() {
    return new ObjectMapper();
}
~~~

this mapper may not receive the modules and configuration Boot prepared, leading to unexpected date/time behavior.

Instead, if you only want readable output formatting:

~~~java
@Bean
public Jackson2ObjectMapperBuilderCustomizer jsonCustomizer() {
    return builder -> builder
            .featuresToEnable(
                    SerializationFeature.INDENT_OUTPUT
            );
}
~~~

Let Boot continue creating the mapper from the configured builder. If you genuinely need an independent mapper, register it with a separate name/qualifier and actively add the required modules, naming strategy, date/time format, and settings.

Do not assume every mapper in the application shares the same configuration just because a customizer exists. A module might create its own mapper with `new ObjectMapper()` and not use Boot's builder.

## 16. When a customizer is not applied as expected

Some common causes:

| Symptom | Possible cause | What to check |
|---|---|---|
| Customizer does not run | Bean is not registered or package is outside component scan | Check component scan, `@Bean` configuration, and conditions |
| Customizer runs but shows no effect | Customizing a builder/factory not used by the actual bean | Check where the object is created |
| Value gets changed back | Another customizer runs later and overwrites it | Check order, `@Order`, and overlapping setters |
| Boot defaults disappear | Application provided a replacement bean causing auto-configuration to back off | Check `@ConditionalOnMissingBean` and condition report |
| Only one client was meant to be customized but others also changed | Global customizer affects all instances in the extension point | Switch to a per-client builder |
| Property has no effect | Code customizer overwrites property or application order differs from expected | Check final configuration and customizer order |
| MVC defaults disappear | `@EnableWebMvc` was enabled or MVC configuration was replaced entirely | Use `WebMvcConfigurer` if only adding settings |
| Jackson behavior differs between API and file export | Two ObjectMappers created from different sources | Check which bean is injected and which mapper is used |

### Check if the customizer is actually a bean

If using:

~~~java
@Bean
public Jackson2ObjectMapperBuilderCustomizer jsonCustomizer() {
    return builder -> builder.featuresToEnable(
            SerializationFeature.INDENT_OUTPUT
    );
}
~~~

the configuration class containing the `@Bean` method must be processed by Spring. If its package is outside the component scan area and is not imported, the customizer bean is not registered.

### Check if the actual bean uses that builder/factory

The application might have two `ObjectMapper`s or two `RestTemplate`s. A customizer only affects the object creation path managed by its extension point. A client created manually via `new RestTemplate()` does not necessarily receive Boot builder customizers.

### Check order and final values

If multiple customizers modify the same property, check the application order. Do not just verify whether one customizer was called; check the final value after the entire configuration chain.

## 17. Customizers and @ConditionalOnMissingBean

Spring Boot often provides default configuration along the lines of "if the application does not have a matching bean yet, create this bean." Conceptual example:

~~~java
@Bean
@ConditionalOnMissingBean(ReportFormatter.class)
public ReportFormatter reportFormatter() {
    return new DefaultReportFormatter();
}
~~~

If the application declares `ReportFormatter` itself, the default bean may not be registered. This is a full bean override mechanism, not a customizer.

If the need is only to change a property of the formatter, a customizer extension point may be better. If you need to replace the entire algorithm, implementation, or contract, declaring a custom bean is appropriate.

| Need | What to consider |
|---|---|
| Change a few options on a Boot-managed object | Customizer |
| Add an interceptor or callback | Additive extension point |
| Replace the entire implementation | Replacement bean / separate configuration |
| Create a dedicated instance for one use case | Factory method from builder |
| Disable an unnecessary auto-configuration | Exclude configuration or condition |
| Create multiple instances from runtime data | Business factory/registry |

### Customizers can also be registered conditionally

If a customizer is only appropriate for one environment, you can use `@Profile` or `@ConditionalOnProperty`:

~~~java
@Bean
@Profile("dev")
public Jackson2ObjectMapperBuilderCustomizer developmentJsonCustomizer() {
    return builder -> builder.featuresToEnable(
            SerializationFeature.INDENT_OUTPUT
    );
}
~~~

When the `dev` profile is not active, the customizer is not registered. However, ensure that configuration really should apply only in dev; do not use a profile to hide a required production configuration.

## 18. Customizers should be small, focused, and testable

A good customizer usually has one clear responsibility. For example:

- One customizer only configures server compression.
- One customizer only adds a module or feature to Jackson.
- One customizer only adds an interceptor to an HTTP client.
- One customizer only adjusts a specific connector property.

Do not create a giant customizer that alters many unrelated systems. Nor should you split them into so many tiny customizers that multiple ones overwrite the same property and make ordering hard to follow.

### Avoid side effects in customize

Do not perform network calls, database queries, or start business tasks inside a customizer callback. Callbacks usually run during startup or object building; side effects can slow startup and make behavior hard to reproduce.

Customizers should primarily adjust target metadata/options. Opening real connections should be handled by the lifecycle of the client/server or the bean owning the resource.

### Test by observing the configured target

For application customizers, you can test the action directly on a builder/factory or start a small context to verify the customizer bean is applied.

Example testing a hypothetical customizer:

~~~java
@Test
void appliesOnlyRequestedSetting() {
    TestServerFactory factory = new TestServerFactory();

    WebServerFactoryCustomizer<TestServerFactory> customizer =
            target -> target.setPort(8081);

    customizer.customize(factory);

    assertEquals(8081, factory.getPort());
    assertEquals(true, factory.isCompressionEnabled());
}
~~~

`TestServerFactory` here is a hypothetical object for the test, not a Spring Boot class. The goal is to verify that the customizer only changes the port and does not lose the existing compression value. With real extension points, you can use the corresponding factory/builder or a Spring context test to confirm the framework applies the bean.

## 19. How to decide between property, customizer, and replacement bean

You can use the following decision chain:

~~~text
Need only changes a common configuration value?
              |
         Yes  |  No
          |        |
          v        v
     Standard    Is there a suitable extension
     property?   point / builder customizer?
                    |
               Yes  |  No
                |        |
                v        v
           Selective    Do you truly need to replace
           customizer?  the entire bean?
                           |
                      Yes  |  No
                       |       |
                       v       v
                 Intentional  Review existing
                 replacement  API / config
                 bean
~~~

Examples:

- Change port: property.
- Enable pretty print: property or Jackson customizer.
- Add MVC interceptor: `WebMvcConfigurer`.
- Customize Tomcat connector: specialized customizer.
- Replace payment algorithm: custom bean implementation.
- Create a dedicated HTTP client for one partner: Boot-provided builder, then build separately.

## 20. Checklist for preserving defaults when customizing

Before writing configuration, check yourself:

1. **What defaults is Spring Boot providing?** Identify the specific bean/builder/factory.
2. **Which property alone needs changing?** Avoid replacing the entire bean if only one setter is needed.
3. **Is there a standard property?** If yes, prefer properties for routine operational configuration.
4. **Is there a customizer/configurer extension point?** Find the right API for the component in use.
5. **Does the customizer act globally or locally?** If only one client needs changes, do not register a global customizer.
6. **Can multiple customizers overwrite each other?** Define ordering and ownership of each property.
7. **Are you accidentally making auto-configuration back off?** Check `@ConditionalOnMissingBean` and bean type.
8. **Do you need to preserve the Boot-provided builder?** Avoid constructing objects via default constructors when Boot already configures a builder.
9. **Are you replacing all of MVC/WebFlux?** Avoid enabling enable-annotations if you only want to add callbacks.
10. **Can you test the final result?** Inspect the target after all customizers have run.

## Conclusion

Customizers are an approach to extending configuration by **modifying just the necessary parts on a builder or factory prepared by the framework**. Spring Boot offers many extension points such as `WebServerFactoryCustomizer`, `Jackson2ObjectMapperBuilderCustomizer`, `RestTemplateCustomizer`, and MVC configuration callbacks. They let applications add or adjust certain settings while still leveraging most of Boot's defaults.

To preserve remaining defaults, prefer standard properties, inject Boot-provided builders/factories, keep customizers small, and avoid declaring replacement beans unnecessarily. When multiple customizers exist, control their order and which properties are overwritten. Only replace an entire bean or enable manual framework configuration when you genuinely want to take on broader configuration responsibility.
