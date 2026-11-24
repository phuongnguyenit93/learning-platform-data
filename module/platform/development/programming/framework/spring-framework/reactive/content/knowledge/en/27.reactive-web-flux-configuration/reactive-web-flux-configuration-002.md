# Impact of @EnableWebFlux on Spring Boot Auto-Configuration

**Context:** Spring Framework Reactive → **WebFlux Configuration**.

In a Spring Boot application using `spring-boot-starter-webflux`, Spring Boot auto-configures the WebFlux infrastructure so the application can run annotated controllers or functional endpoints without manually declaring all base beans. When you want to add CORS, codecs, formatters, path matching, or resource handlers, you usually only need a `@Configuration implements WebFluxConfigurer` class.

`@EnableWebFlux` has a different meaning: this annotation enables Spring Framework's Java configuration by importing `DelegatingWebFluxConfiguration`. That class extends `WebFluxConfigurationSupport`. That base bean causes the condition on `WebFluxAutoConfiguration` in Spring Boot to no longer be satisfied, so **all of Boot's WebFlux auto-configuration backs off**.

This does not disable Spring WebFlux. Spring Framework's default infrastructure beans are still created by `DelegatingWebFluxConfiguration`. What changes is that Boot no longer contributes its own WebFlux configuration parts such as codec customizers, static resource/WebJars mappings, and the welcome page. If you want to keep those conveniences, configure with `WebFluxConfigurer` without attaching `@EnableWebFlux`.

## 1. Distinguishing the Three Components

Before examining the impact, distinguish the responsibility of each component:

| Component | Role | When It Appears |
|---|---|---|
| `@EnableWebFlux` | Imports Spring Framework's WebFlux Java configuration | When the application explicitly requests full WebFlux configuration control |
| `DelegatingWebFluxConfiguration` | Creates default infrastructure beans and discovers `WebFluxConfigurer` beans to delegate customization | Imported by `@EnableWebFlux`; also used by Boot in its own configuration |
| `WebFluxAutoConfiguration` | Adds Spring Boot-specific WebFlux configuration on top of Spring Framework | When the application is reactive and no `WebFluxConfigurationSupport` bean exists |

`WebFluxConfigurer` is a configuration extension interface. Implementing this interface alone does **not** mean re-enabling full manual configuration, and does not cause Boot auto-configuration to back off.

Example:

```java
@Configuration(proxyBeanMethods = false)
class ApiWebFluxConfiguration implements WebFluxConfigurer {
    // Only add the needed customizations.
}
```

The configuration above still allows Boot to participate. If you add `@EnableWebFlux` to the class, startup behavior changes because Spring Framework imports `DelegatingWebFluxConfiguration`.

## 2. The Exact Condition That Causes Boot to Back Off

In Spring Boot 3.5, `WebFluxAutoConfiguration` has a class-level condition:

```java
@AutoConfiguration(...)
@ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.REACTIVE)
@ConditionalOnClass(WebFluxConfigurer.class)
@ConditionalOnMissingBean(WebFluxConfigurationSupport.class)
public class WebFluxAutoConfiguration {
    // ...
}
```

The key condition is:

```java
@ConditionalOnMissingBean(WebFluxConfigurationSupport.class)
```

Spring Framework defines the inheritance hierarchy:

```text
WebFluxConfigurationSupport
          ^
          |
DelegatingWebFluxConfiguration
          ^
          |
@Import by @EnableWebFlux
```

When a configuration class with `@EnableWebFlux` is processed, `DelegatingWebFluxConfiguration` is imported into the context. Because it is a subclass of `WebFluxConfigurationSupport`, Boot's `@ConditionalOnMissingBean` condition is no longer true.

Result: Spring skips `WebFluxAutoConfiguration`. This is a back off at the entire auto-configuration class level, not just skipping a single bean.

### 2.1. Why Does Implementing WebFluxConfigurer Not Cause Boot to Back Off?

Boot's condition checks for a bean of type `WebFluxConfigurationSupport`, not a bean of type `WebFluxConfigurer`.

```java
@Configuration(proxyBeanMethods = false)
class CustomWebFluxConfiguration implements WebFluxConfigurer {
    // Without @EnableWebFlux.
}
```

The class above is simply a configurer discovered by Boot's `DelegatingWebFluxConfiguration`. It does not create a new `WebFluxConfigurationSupport` bean, so Boot continues configuring.

This is the most important difference:

| Configuration Approach | User-Added WebFluxConfigurationSupport Bean? | Boot WebFlux Auto-Config |
|---|---:|---|
| Using starter-webflux only | No | Active |
| `@Configuration implements WebFluxConfigurer` | No | Active |
| `@Configuration @EnableWebFlux` | Yes, via DelegatingWebFluxConfiguration | Backs off |
| Extending `WebFluxConfigurationSupport` | Yes | Backs off |
| Extending `DelegatingWebFluxConfiguration` | Yes | Backs off |

Do not assume that having any WebFlux configuration class makes Boot stop working. The specific bean condition decides.

## 3. What Does @EnableWebFlux Actually Do?

In Spring Framework, `@EnableWebFlux` is meta-annotated with `@Import(DelegatingWebFluxConfiguration.class)`. The imported configuration provides the infrastructure for both annotated controllers and functional endpoints.

The base components include:

- Handler mapping for `@RequestMapping` and controller annotations.
- Adapters to invoke handlers/controllers.
- Handlers for `RouterFunction` and functional endpoints.
- `ServerCodecConfigurer` along with default readers/writers.
- Content negotiation and path matching.
- CORS mappings, formatters/converters, validators, and view resolvers as configured.
- Resource handlers if registered by the application via the corresponding API.
- WebSocket handler adapter and related WebFlux infrastructure.

Spring Framework still detects dependencies on the classpath to choose appropriate codecs, such as Jackson for JSON when the corresponding dependency is present. Therefore, adding `@EnableWebFlux` does not make JSON or controllers disappear. The issue is that Boot's own customizations are no longer automatically applied through `WebFluxAutoConfiguration`.

`@EnableWebFlux` also does not replace declaring controllers, routers, services, or component scanning. It only enables WebFlux infrastructure configuration.

## 4. What Boot WebFlux Auto-Configuration Adds

Spring Boot describes WebFlux auto-configuration as an additional layer on top of Spring Framework's default configuration. In Boot 3.5, notable parts include:

| Group | Boot Adds | Meaning When WebFluxAutoConfiguration Backs Off |
|---|---|---|
| HTTP codecs | Applies `CodecCustomizer` and Boot's codec configuration | Must re-verify reader/writer, Jackson, and buffer limit configuration |
| Static resources | Registers resource handlers for standard static directories | Must register resource handlers manually if the app needs to serve files |
| WebJars | WebJars resource mapping | Must configure mapping manually if the app uses WebJars |
| Welcome page | Auto-detects static/template index page | Must handle or verify the home route manually |
| Formatters | Applies formatters/converters and Boot's formatting properties | Must register formatters manually if custom rules are needed |
| Handler configuration | Boot provides the configurer and related beans | Must review beans that the application replaces itself |

Boot 3.5 implements most of these WebFlux contributions through the nested class `WebFluxAutoConfiguration.WebFluxConfig`, a bean implementing `WebFluxConfigurer`. That class applies codec customizers, formatters, resource handlers, argument resolvers, and view resolvers.

When `@EnableWebFlux` causes the outer auto-configuration to back off, Boot's `WebFluxConfig` is not registered either.

## 5. Impact on HTTP Codecs and JSON

Spring WebFlux uses `HttpMessageReader` and `HttpMessageWriter` to read request bodies and write response bodies. Default codecs still come from Spring Framework, but Boot's additional configuration is applied via Boot's configurer.

For example, Boot can apply:

- `CodecCustomizer` beans declared by the application.
- Buffer limits from codec properties.
- Jackson customizations linked to codecs.
- Reader/writer configurations based on classpath dependencies.

When `@EnableWebFlux` causes Boot's WebFlux configurer to disappear, do not assume `CodecCustomizer` beans or Boot properties will still be applied as before. If you need to control codecs, configure them directly via `WebFluxConfigurer`:

```java
@Configuration(proxyBeanMethods = false)
class ApiWebFluxConfiguration implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {

        configurer.defaultCodecs()
                .maxInMemorySize(2 * 1024 * 1024);
    }
}
```

The code increases the default buffer limit to 2 MiB for the configured codecs. It does not grow memory unboundedly and does not replace streaming for large payloads.

If using full manual mode, explicitly determine:

1. Which codecs are registered by default.
2. Whether custom Jackson encoders/decoders are needed.
3. Whether CBOR, XML, Protobuf, or custom codecs are needed.
4. What the memory limit is for request/response aggregation.
5. Whether request detail logging is needed and what data is permitted to be logged.

Do not use `registerDefaults(false)` unless intentionally replacing all default codecs. Calling that method can remove default readers/writers that controllers rely on.

## 6. Impact on Static Resources, WebJars, and Welcome Page

Spring Boot auto-configures serving static content from common classpath locations such as:

```text
classpath:/static/
classpath:/public/
classpath:/resources/
classpath:/META-INF/resources/
```

Boot also supports WebJars mappings and welcome page detection such as `index.html` or an `index` template. Common properties in Boot 3.5:

```properties
spring.webflux.static-path-pattern=/assets/**
spring.webflux.webjars-path-pattern=/webjars/**
spring.web.resources.static-locations=classpath:/public/
```

When using `@EnableWebFlux`, Boot WebFlux auto-configuration backs off. Do not assume the static/WebJars/welcome page mappings registered by `WebFluxAutoConfiguration` still exist.

If you need to serve static resources in manual mode, register them explicitly:

```java
@Configuration(proxyBeanMethods = false)
@EnableWebFlux
class ManualWebFluxConfiguration implements WebFluxConfigurer {

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/assets/**")
                .addResourceLocations("classpath:/static/");
    }
}
```

This is a minimal configuration. If cache control, versioned resources, compressed resources, or WebJars are needed, you must additionally configure the corresponding resolvers/transformers and mappings.

Do not register an overly broad resource handler if API routes use the same path pattern. Define mapping order and scope clearly so static files do not shadow application endpoints.

## 7. Formatters, Converters, and Validators

Boot can add formatters/converters based on beans and configuration properties. WebFlux formatting properties can include:

```properties
spring.webflux.format.date=yyyy-MM-dd
spring.webflux.format.time=HH:mm:ss
spring.webflux.format.date-time=yyyy-MM-dd'T'HH:mm:ss
```

Example values must match the API's formatting and locale requirements. If Boot's configurer is no longer active, do not assume these properties are still wired into WebFlux's ConversionService.

You can register formatters via `WebFluxConfigurer`:

```java
@Configuration(proxyBeanMethods = false)
class DateFormatConfiguration implements WebFluxConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        DateTimeFormatterRegistrar registrar =
                new DateTimeFormatterRegistrar();

        registrar.setUseIsoFormat(true);
        registrar.registerFormatters(registry);
    }
}
```

With Bean Validation, Spring Framework has a mechanism to register a default validator when the corresponding provider is on the classpath. However, if relying on a validator or conversion service customized by Boot, check the actual beans in the context after adding `@EnableWebFlux`.

You can provide a `Validator` via `WebFluxConfigurer#getValidator()` if a custom global validator is needed. Local validators can still be registered using `@InitBinder` inside controllers.

## 8. What Still Works When @EnableWebFlux Is Added?

The back off of `WebFluxAutoConfiguration` does not mean disabling all of Spring Boot auto-configuration.

The following parts have their own auto-configurations and conditions, so do not conclude they automatically disappear just because `@EnableWebFlux` is present:

- Reactive web server factory and server port/SSL configuration.
- Boot error handling via `ErrorWebFluxAutoConfiguration`.
- Reactive Spring Security and filter chain.
- Actuator and integrations with their own conditions.
- Data access, messaging, scheduling, serialization, or auto-configurations outside WebFluxAutoConfiguration.
- Beans declared directly by the application.

However, an independent auto-configuration may depend on infrastructure beans provided by WebFlux. When replacing configuration yourself, verify that required dependencies still exist and remain compatible.

`@EnableWebFlux` also does not automatically convert a servlet application to reactive. If both `spring-boot-starter-web` and `spring-boot-starter-webflux` are present, Spring Boot normally chooses Spring MVC. Choosing the application type is a separate decision; if reactive mode is truly needed with both starters on the classpath, consider `spring.main.web-application-type=reactive`.

## 9. Recommended Approach: WebFluxConfigurer Without @EnableWebFlux

If you only need to customize a few parts, keep Boot auto-configuration and add a configurer:

```java
@Configuration(proxyBeanMethods = false)
class ApiWebFluxConfiguration implements WebFluxConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://frontend.example")
                .allowedMethods("GET", "POST");
    }

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {

        configurer.defaultCodecs()
                .maxInMemorySize(2 * 1024 * 1024);
    }
}
```

There is no `@EnableWebFlux`. At startup:

1. Boot sees a reactive web application and WebFlux classes on the classpath.
2. There is no user-declared `WebFluxConfigurationSupport` bean.
3. `WebFluxAutoConfiguration` is applied.
4. `WebFluxAutoConfiguration.WebFluxConfig` is registered.
5. `DelegatingWebFluxConfiguration` combines Boot's configurer and the application's configurer.
6. The CORS and codec limits requested by the application are added to the WebFlux configuration.

This is the right approach for most Boot applications. You only declare what differs; Boot still manages the rest.

## 10. When Should You Use @EnableWebFlux?

Only use `@EnableWebFlux` when the application intentionally takes responsibility for WebFlux infrastructure configuration, for example:

- Plain Spring Framework applications not using Spring Boot auto-configuration.
- Wanting full manual control over codecs, resource handlers, view resolvers, validators, and conversion services.
- Special requirements that cannot be satisfied by the `WebFluxConfigurer` API.
- Building an internal framework configuration with team-managed infrastructure beans.
- Needing direct control over the beans declared by `WebFluxConfigurationSupport`.

If you only need to add CORS or change a codec limit, enabling full manual mode usually increases the amount of configuration you must maintain yourself.

Before using it, list the features Boot currently provides to the application and how to replace them. In particular, check static resources, WebJars, welcome page, codec customizers, formatters, validators, and view configuration.

## 11. Do Not Arbitrarily Add @EnableWebFlux to Shared Libraries

A starter or internal library is often imported into many different Boot applications. If the library contains a configuration class with `@EnableWebFlux`, it can cause the host application's `WebFluxAutoConfiguration` to back off.

Consequences may surface in a different application from the one where the library was originally developed:

- Static resources or welcome page no longer map as expected.
- Boot's codec customizers are not applied via Boot's WebFlux configurer.
- Boot-specific properties do not behave as before.
- Users have to manually declare infrastructure that was previously available out of the box.

For libraries that need to add WebFlux customizations, prefer providing a `WebFluxConfigurer` bean or a small conditional auto-configuration with appropriate conditions, without forcing `@EnableWebFlux` onto the host application.

Example:

```java
@Configuration(proxyBeanMethods = false)
class LibraryWebFluxConfigurer implements WebFluxConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/library-api/**")
                .allowedMethods("GET");
    }
}
```

Libraries should avoid overriding the host application's configuration without a clear reason. If providing a replaceable bean, use conditions such as `@ConditionalOnMissingBean` following starter design best practices.

## 12. Multiple WebFluxConfigurers and Application Order

Spring allows multiple `WebFluxConfigurer` beans to coexist. `DelegatingWebFluxConfiguration` discovers the configurers and invokes their corresponding callbacks to compose the configuration.

For example, an application may have:

- Boot configurer: configures codecs, static resources, formatters, and views.
- CORS configuration: declares allowed origins/methods.
- API configuration: adds path prefix or content type resolver.
- Custom codec configuration: adds decoders or changes memory limits.

When callback order matters, configurers can be ordered using `@Order` or `Ordered`. Do not rely on component scan order or Java file order.

Avoid multiple configurers modifying the same setting with conflicting values. Choose one clear owner per policy and write integration tests to verify the merged result.

## 13. WebHttpHandlerBuilderCustomizer Is Another Extension Point

Not every customization needs `WebFluxConfigurer`. Spring Boot allows declaring a `WebHttpHandlerBuilderCustomizer` bean to modify the auto-configured `WebHttpHandlerBuilder`.

Use this extension point when HTTP handler-level customization is needed, such as adding components to the processing chain below controller configuration.

```java
@Bean
WebHttpHandlerBuilderCustomizer httpHandlerCustomizer() {
    return builder -> {
        // Add a custom WebExceptionHandler or WebFilter
        // only when the application requires that behavior.
    };
}
```

This is an illustrative snippet; you need to import `org.springframework.boot.web.reactive.server.WebHttpHandlerBuilderCustomizer` and provide an actual implementation.

Choose the right layer:

| Need | Appropriate Extension Point |
|---|---|
| CORS, formatters, codecs, path matching | `WebFluxConfigurer` |
| Static resource mapping | `WebFluxConfigurer#addResourceHandlers` |
| Request/response-level WebFilter | `WebFilter` bean |
| HTTP handler builder customization | `WebHttpHandlerBuilderCustomizer` |
| Full WebFlux infrastructure configuration | `@EnableWebFlux` / advanced configuration |

Do not use a low-level customizer to replace an existing WebFlux callback.

## 14. Advanced Configuration Mode

If `WebFluxConfigurer` does not provide a needed callback, Spring Framework has an advanced mode. Framework documentation describes extending `DelegatingWebFluxConfiguration` to override bean declarations while still discovering other configurers.

Skeleton example:

```java
@Configuration(proxyBeanMethods = false)
class AdvancedWebFluxConfiguration
        extends DelegatingWebFluxConfiguration {

    // Override only the infrastructure bean or hook
    // that the application truly needs to replace.
}
```

In Spring Boot, this is also a deliberate choice to take over configuration ownership. Because `DelegatingWebFluxConfiguration` extends `WebFluxConfigurationSupport`, the condition on `WebFluxAutoConfiguration` will no longer be satisfied. Be prepared to supply replacements for what Boot previously provided.

Do not arbitrarily combine `@EnableWebFlux` with extending another configuration support class. There should be only one source responsible for importing/creating WebFlux infrastructure to avoid duplicate beans or inconsistent configuration.

## 15. Comparison Before and After Adding @EnableWebFlux

Assume the application initially only uses `spring-boot-starter-webflux`:

| Behavior | Without @EnableWebFlux | With @EnableWebFlux |
|---|---|---|
| Spring WebFlux infrastructure | Present | Present |
| Boot WebFluxAutoConfiguration | Present | Backs off |
| Boot WebFluxConfig | Present | Absent |
| Spring default codecs | Present | Present |
| Boot CodecCustomizer applied via WebFluxConfig | Present | Not automatic via Boot's configurer |
| Boot static/WebJars mappings | Present | Must configure manually if desired |
| Boot welcome page configuration | Present | Not provided by WebFluxAutoConfiguration |
| Application WebFluxConfigurer | Discovered | Discovered by Delegating config |
| Separate reactive server auto-config | Subject to its own condition | Not disabled by annotation alone |
| Separate Security/Error/Actuator auto-config | Subject to its own condition | Not blanket-disabled |

Do not read this table as an exhaustive list of every bean in the context. Boot version, dependencies, and application-provided beans all affect the outcome. Use the Condition Evaluation Report or ApplicationContext tests to determine exactly which configurations matched.

## 16. How to Verify Auto-Configuration Backed Off

There are three useful ways:

1. **Condition Evaluation Report:** run the application with debug enabled or inspect the Actuator conditions endpoint if exposed securely.
2. **ApplicationContext test:** check whether Boot's configurer bean is present.
3. **HTTP integration test:** verify behaviors the application relies on such as JSON codecs, static resources, CORS, and the welcome page.

For example, context tests should assert Boot's configurer class rather than only checking that a controller works. A controller can still work after Boot WebFlux auto-config backs off, so an endpoint returning 200 alone does not prove the rest of the configuration is still present.

## 17. Runnable Java 17+ Example: Boot App Preserving Auto-Configuration

Sample project using Spring Boot 3.5.16, Java 17, and WebFlux.

Structure:

```text
webflux-enable-config-demo/
├── pom.xml
├── src/main/java/demo/WebFluxApplication.java
├── src/main/java/demo/ApiWebFluxConfiguration.java
├── src/main/java/demo/HealthController.java
└── src/test/java/demo/EnableWebFluxAutoConfigurationTest.java
```

### 17.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>webflux-enable-config-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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
```

### 17.2. WebFluxApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebFluxApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebFluxApplication.class, args);
    }
}
```

### 17.3. ApiWebFluxConfiguration.java

```java
package demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.reactive.config.CorsRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration(proxyBeanMethods = false)
public class ApiWebFluxConfiguration implements WebFluxConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://frontend.example")
                .allowedMethods("GET", "POST");
    }

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {

        configurer.defaultCodecs()
                .maxInMemorySize(2 * 1024 * 1024);
    }
}
```

Key point: the class does not have `@EnableWebFlux`. Boot still registers `WebFluxAutoConfiguration.WebFluxConfig` and merges this configurer's callbacks with the default configuration.

### 17.4. HealthController.java

```java
package demo;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class HealthController {

    @GetMapping("/health")
    public Mono<Map<String, String>> health() {
        return Mono.just(Map.of("status", "UP"));
    }
}
```

Run the application:

```bash
mvn spring-boot:run
```

Test the endpoint:

```bash
curl -i http://localhost:8080/api/health
```

Expected JSON body:

```json
{"status":"UP"}
```

The response has HTTP status 200 and the corresponding JSON Content-Type. JSON property order is not a contract to rely on; what matters is that the object is serialized properly.

## 18. Testing Both Modes with ReactiveWebApplicationContextRunner

To demonstrate the difference at the context level, you can check for the presence of Boot's configurer:

```java
package demo;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.web.reactive.WebFluxAutoConfiguration;
import org.springframework.boot.test.context.runner.ReactiveWebApplicationContextRunner;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.DelegatingWebFluxConfiguration;
import org.springframework.web.reactive.config.EnableWebFlux;
import org.springframework.web.reactive.config.WebFluxConfigurer;

import static org.assertj.core.api.Assertions.assertThat;

class EnableWebFluxAutoConfigurationTest {

    private final ReactiveWebApplicationContextRunner runner =
            new ReactiveWebApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    WebFluxAutoConfiguration.class));

    @Test
    void plainWebFluxConfigurerKeepsBootConfiguration() {
        runner.withUserConfiguration(PlainConfigurer.class)
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(
                                    WebFluxAutoConfiguration.WebFluxConfig.class);

                    assertThat(context)
                            .hasSingleBean(
                                    WebFluxAutoConfiguration.EnableWebFluxConfiguration.class);
                });
    }

    @Test
    void enableWebFluxMakesBootAutoConfigurationBackOff() {
        runner.withUserConfiguration(ManualEnableWebFlux.class)
                .run(context -> {
                    assertThat(context)
                            .doesNotHaveBean(WebFluxAutoConfiguration.class);

                    assertThat(context)
                            .doesNotHaveBean(
                                    WebFluxAutoConfiguration.WebFluxConfig.class);

                    assertThat(context)
                            .hasSingleBean(
                                    DelegatingWebFluxConfiguration.class);
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class PlainConfigurer implements WebFluxConfigurer {
    }

    @Configuration(proxyBeanMethods = false)
    @EnableWebFlux
    static class ManualEnableWebFlux implements WebFluxConfigurer {
    }
}
```

The first test creates a reactive context with only a plain `WebFluxConfigurer`. Boot's WebFlux configurer still appears.

The second test adds `@EnableWebFlux`. Spring imports `DelegatingWebFluxConfiguration`; the base `WebFluxConfigurationSupport` bean makes Boot's condition fail, so `WebFluxAutoConfiguration` and nested `WebFluxConfig` are not registered.

Run tests:

```bash
mvn test
```

The two tests prove the auto-configuration difference without opening an HTTP socket. The application integration test in the previous section remains useful for verifying codecs, CORS, and resource behavior via real requests.

## 19. If You Truly Want to Use @EnableWebFlux in Boot

If you decide to take full configuration ownership, create an explicit configuration:

```java
@Configuration(proxyBeanMethods = false)
@EnableWebFlux
class ManualWebFluxConfiguration implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {

        configurer.defaultCodecs()
                .maxInMemorySize(2 * 1024 * 1024);
    }

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/assets/**")
                .addResourceLocations("classpath:/static/");
    }
}
```

Then review and add back the parts Boot previously supplied automatically:

- Static resources and WebJars.
- Welcome page.
- Codec customizers, Jackson settings, and buffer limits.
- Formatters/converters and validators.
- View resolvers if the application renders HTML/templates.
- CORS, path matching, and argument resolvers.
- Other customizers/infrastructure the application depends on.

You do not need to rewrite everything mechanically. Only configure the parts actually used and test the application contract. If an independent auto-configuration remains active, verify it still receives its required bean dependencies.

## 20. Common Mistakes

1. **Adding @EnableWebFlux just to add CORS.** Boot auto-config may back off; use WebFluxConfigurer without the annotation.
2. **Thinking @EnableWebFlux disables all of Spring Boot.** It causes WebFluxAutoConfiguration to back off; other auto-configurations have their own conditions.
3. **Thinking WebFluxConfigurer makes Boot back off.** The condition checks for WebFluxConfigurationSupport, not WebFluxConfigurer.
4. **Assuming WebFlux stops working when Boot backs off.** DelegatingWebFluxConfiguration still provides Spring Framework's infrastructure.
5. **Not checking codecs after adding the annotation.** Default codecs still exist, but Boot CodecCustomizers may not be applied via WebFluxConfig.
6. **Losing static resource mappings unexpectedly.** Boot-specific resource handlers may be gone; check /static, WebJars, and welcome page.
7. **Relying on spring.webflux.static-path-pattern in manual mode.** Register ResourceHandlerRegistry manually if Boot's configurer no longer applies.
8. **Relying on codec properties without checking versions.** Boot 3.5 uses spring.http.codecs.*; earlier versions may use spring.codec.*.
9. **Assuming all Boot properties are lost.** Only properties consumed by the auto-configuration that backed off are affected; properties of other subsystems may still work.
10. **Adding multiple @EnableWebFlux annotations.** Only one configuration should import WebFlux infrastructure; use multiple WebFluxConfigurers for customizations.
11. **Registering multiple configurers modifying the same codec.** Can produce unpredictable results; designate one policy owner.
12. **Using @EnableWebFlux in a shared library.** Can cause the host application to lose Boot WebFlux auto-config.
13. **Confusing WebFlux auto-config with reactive server auto-config.** Server factories have their own conditions and are not disabled by the annotation alone.
14. **Assuming Boot's error handler definitely disappears.** ErrorWebFluxAutoConfiguration is a separate auto-configuration; check its conditions.
15. **Using WebFluxConfigurer for low-level HTTP handler customization.** Consider WebHttpHandlerBuilderCustomizer when at that layer.
16. **Extending WebFluxConfigurationSupport while expecting Boot to keep auto-configuring.** Extending this class also fails the missing-bean condition.
17. **Adding @EnableWebFlux to switch MVC to reactive.** Application type is a separate decision; the annotation does not replace choosing the web application type.
18. **Not using the Condition Evaluation Report.** When the context differs from expectations, inspect which conditions matched/backed off rather than guessing from one endpoint.
19. **Only testing that a controller returns 200.** Controllers can run in both modes; test Boot's configurer and the Boot features your app depends on.
20. **Configuring all codecs manually while forgetting defaults.** Only disable default codecs when you truly want to replace them and have registered all required readers/writers.

## 21. Checklist Before Adding @EnableWebFlux

Before committing changes, answer:

- Is the application using plain Spring Framework or Spring Boot?
- Is `spring-boot-starter-webflux` being used?
- Is the goal to add a few callbacks or take full configuration control?
- Can `WebFluxConfigurer` be used without `@EnableWebFlux`?
- Is Boot WebFluxAutoConfiguration providing codecs, static resources, WebJars, or a welcome page that the app needs?
- Are `spring.webflux.*` and codec properties being configured by Boot WebFluxConfig?
- Do formatters, validators, CORS, view resolvers, or path matching need manual configuration?
- Do independent auto-configurations such as server, error handling, Security, and Actuator still run under their own conditions?
- Is there a context test proving Boot's configurer bean appears or backs off as expected?
- Are there integration tests for JSON codecs, static resources, CORS, and main endpoints?
- Does any library in the application accidentally import `@EnableWebFlux`?
- Is there only one place responsible for creating WebFlux infrastructure?

**Key takeaway:** In Spring Boot, `@EnableWebFlux` imports `DelegatingWebFluxConfiguration`, a subclass of `WebFluxConfigurationSupport`. That causes `WebFluxAutoConfiguration`'s `@ConditionalOnMissingBean(WebFluxConfigurationSupport.class)` to no longer be satisfied, so Boot WebFlux auto-configuration backs off. Spring WebFlux still runs using Framework infrastructure. If you only want to customize CORS, codecs, formatters, or path matching, use `WebFluxConfigurer` without `@EnableWebFlux` to keep Boot's configuration. Only enable the annotation when you intentionally replace the Boot-specific parts your application needs.

## References

- Spring Boot 3.5 — [Reactive Web Applications: WebFlux auto-configuration](https://docs.spring.io/spring-boot/reference/web/reactive.html).
- Spring Boot 3.5 — [WebFluxAutoConfiguration Javadoc and its ConditionalOnMissingBean condition](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/reactive/WebFluxAutoConfiguration.html).
- Spring Boot 3.5 — [WebFluxAutoConfiguration.WebFluxConfig Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/reactive/WebFluxAutoConfiguration.WebFluxConfig.html).
- Spring Boot 3.5 — [WebFluxAutoConfiguration.EnableWebFluxConfiguration Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/reactive/WebFluxAutoConfiguration.EnableWebFluxConfiguration.html).
- Spring Framework — [WebFlux Config: @EnableWebFlux and WebFluxConfigurer](https://docs.spring.io/spring-framework/reference/web/webflux/config.html).
- Spring Framework — [DelegatingWebFluxConfiguration Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/config/DelegatingWebFluxConfiguration.html).
- Spring Boot — [Common Application Properties: WebFlux and HTTP codec settings](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html).
