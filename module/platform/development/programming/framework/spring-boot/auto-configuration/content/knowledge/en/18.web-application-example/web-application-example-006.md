# `@EnableWebMvc` and Its Impact on Spring Boot's Default Configuration Mechanism

In a Spring Boot application using Spring MVC, the `@EnableWebMvc` annotation has a much larger impact than simply "enabling MVC." It instructs Spring Framework to import Spring's own default Java MVC configuration. Because this configuration creates a bean of type `WebMvcConfigurationSupport`, Spring Boot's `WebMvcAutoConfiguration` condition no longer matches. As a result, **Spring Boot hands MVC configuration control back to the application**.

Here is the core point to remember:

- To **keep Boot's default MVC configuration** and only add interceptors, formatters, CORS, resource handlers, or view controllers: register a `WebMvcConfigurer` bean, **do not add `@EnableWebMvc`**.
- To **take full responsibility for configuring Spring MVC** without needing Boot's own MVC customizations: use `@EnableWebMvc` intentionally.
- To replace a few core components such as `RequestMappingHandlerMapping`, `RequestMappingHandlerAdapter`, or `ExceptionHandlerExceptionResolver` while still keeping Boot MVC auto-configuration: look at `WebMvcRegistrations`.

## 1. What Configuration Does `@EnableWebMvc` Actually Import?

The annotation resides in the package:

```java
import org.springframework.web.servlet.config.annotation.EnableWebMvc;
```

When a configuration class has `@EnableWebMvc`, Spring Framework imports `DelegatingWebMvcConfiguration`:

```java
@Configuration(proxyBeanMethods = false)
@EnableWebMvc
public class MyWebConfiguration {
}
```

This is a complete Spring MVC Java configuration. `DelegatingWebMvcConfiguration` extends `WebMvcConfigurationSupport` and detects beans of type `WebMvcConfigurer` to delegate customizations into the MVC configuration.

The inheritance relationship can be visualized as:

```text
@EnableWebMvc
     |
     | @Import
     v
DelegatingWebMvcConfiguration
     |
     | extends
     v
WebMvcConfigurationSupport
     |
     v
Registers Spring MVC infrastructure:
HandlerMapping, HandlerAdapter,
exception resolvers, conversion service,
validator, message converters...
```

Therefore, once `@EnableWebMvc` is processed, the BeanFactory already contains a configuration bean of type `WebMvcConfigurationSupport` (specifically the subclass `DelegatingWebMvcConfiguration`). That type is the signal telling Spring Boot that the application has supplied its own MVC configuration.

Note: `@EnableWebMvc` does not merely create a `WebMvcConfigurer` bean. It imports **a foundational configuration class** of Spring MVC. This is the crucial difference between `@EnableWebMvc` and merely declaring a `WebMvcConfigurer` bean.

## 2. Why Does Spring Boot MVC Auto-Configuration Back Off?

In Spring Boot 3.3, `WebMvcAutoConfiguration` has the key class-level conditions:

```java
@AutoConfiguration(after = {
        DispatcherServletAutoConfiguration.class,
        TaskExecutionAutoConfiguration.class,
        ValidationAutoConfiguration.class
})
@ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.SERVLET)
@ConditionalOnClass({
        Servlet.class,
        DispatcherServlet.class,
        WebMvcConfigurer.class
})
@ConditionalOnMissingBean(WebMvcConfigurationSupport.class)
@AutoConfigureOrder(Ordered.HIGHEST_PRECEDENCE + 10)
public class WebMvcAutoConfiguration {
    // ...
}
```

This is an abridged excerpt based on the Spring Boot 3.3 API. The three main conditions state that:

1. The application must be a **Servlet web application**.
2. The required Servlet and Spring MVC classes must be on the classpath.
3. No bean of type `WebMvcConfigurationSupport` already exists in the condition's search scope.

The third condition explains the impact of `@EnableWebMvc`:

- Without `@EnableWebMvc`: if the web and classpath conditions also match, no `WebMvcConfigurationSupport` exists yet, so `WebMvcAutoConfiguration` is applied.
- With `@EnableWebMvc`: `DelegatingWebMvcConfiguration` has been imported; this class is a subclass of `WebMvcConfigurationSupport`. Hence `@ConditionalOnMissingBean(WebMvcConfigurationSupport.class)` does not match and `WebMvcAutoConfiguration` **backs off**.

This is Spring Boot's conditional backoff mechanism. Boot does not need to delete MVC configurations already registered by Spring Framework, nor does it override them. It simply **does not apply its own default MVC auto-configuration** when it detects the application has already supplied the MVC foundation.

### Diagram of Both Cases

```text
CASE A — Without @EnableWebMvc
  User configuration
       |
       v
  No WebMvcConfigurationSupport yet
       |
       v
  WebMvcAutoConfiguration conditions match
       |
       v
  Boot registers MVC adapter + Boot customizations
       |
       v
  Spring MVC runs with Boot's default configuration

CASE B — With @EnableWebMvc
  User configuration
       |
       v
  @EnableWebMvc imports DelegatingWebMvcConfiguration
       |
       v
  WebMvcConfigurationSupport already exists
       |
       v
  WebMvcAutoConfiguration condition does not match
       |
       v
  Boot MVC auto-configuration backs off
       |
       v
  Application takes responsibility for MVC configuration itself
```

This class-level condition also means that **a custom configuration directly extending `WebMvcConfigurationSupport`** can make Boot MVC auto-configuration back off even without the `@EnableWebMvc` annotation.

## 3. Practical Changes When Adding `@EnableWebMvc`

`@EnableWebMvc` does not make Spring MVC disappear. It transfers MVC setup control from Boot's adapter to the Spring Framework configuration activated by the application.

### 3.1. Boot's Extra MVC Features Are No Longer Applied Automatically

According to Spring Boot documentation, `WebMvcAutoConfiguration` adds many features on top of Spring MVC's defaults:

| Feature provided by Boot MVC auto-configuration | When `@EnableWebMvc` makes auto-config back off |
| --- | --- |
| `ContentNegotiatingViewResolver` and `BeanNameViewResolver` | No longer added by Boot's default MVC adapter; if needed, the application registers and orders view resolvers itself. |
| Static resource handling, WebJars, and static `index.html` welcome page | Do not assume Boot's default mappings and welcome-page behavior remain; configure resource handlers manually when needed. |
| Auto-registration of `Converter`, `GenericConverter`, and `Formatter` beans | Must configure the appropriate formatters/converters in MVC. |
| Integration of `HttpMessageConverters` with MVC | Must define how the application's desired converters are built and registered. |
| Auto-registration of `MessageCodesResolver` per Boot configuration | If custom message code formatting is needed, the application configures it itself. |
| Use of custom `ConfigurableWebBindingInitializer` if a matching bean exists | Must manage the data binding initializer manually in MVC configuration. |
| MVC settings read by Boot's adapter from `WebMvcProperties`/`WebProperties` | Do not assume these properties are still applied to MVC the way auto-configuration does. |

An important distinction: several other Boot auto-configurations may still register beans related to HTTP, validation, errors, or Jackson. The table above refers to **customizations provided by `WebMvcAutoConfiguration` for Spring MVC**. Do not overgeneralize this as "all Spring Boot auto-configurations are turned off."

For example, `@EnableWebMvc` does not automatically disable:

- `@EnableAutoConfiguration` inside `@SpringBootApplication`.
- Embedded Servlet container configuration such as Tomcat/Jetty/Undertow.
- `DispatcherServlet` registration by `DispatcherServletAutoConfiguration`.
- Other independent auto-configurations, as long as their own conditions still match.

`@Controller`/`@RestController` controllers can still be handled by Spring MVC. The application remains a Servlet web application; what changes is how MVC is configured.

### 3.2. Common Errors Observed After Adding the Annotation

- Static URLs like `/css/app.css` or WebJars resources return 404.
- `index.html` is no longer recognized as a welcome page per Boot's rules.
- `spring.mvc.format.*` or `spring.mvc.contentnegotiation.*` no longer produce the previous behavior.
- Custom-declared converters/formatters are not registered via the expected configuration path.
- Boot's default view resolvers do not appear or resolver ordering changes.
- A custom `HttpMessageConverter` alters the converter list unexpectedly.

When encountering these symptoms, check whether any configuration class uses `@EnableWebMvc` or extends `WebMvcConfigurationSupport`. If so, investigate the manual MVC configuration path before adding properties or beans to "patch" each individual error.

## 4. Customizing MVC While Keeping Boot's Default Configuration

This is the right choice for most Spring Boot applications. Simply declare a `WebMvcConfigurer` bean:

```java
package demo.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class MvcCustomization {

    @Bean
    WebMvcConfigurer mvcConfigurer() {
        return new WebMvcConfigurer() {

            @Override
            public void addInterceptors(InterceptorRegistry registry) {
                registry.addInterceptor(new RequestAuditInterceptor())
                        .addPathPatterns("/api/**");
            }

            @Override
            public void addCorsMappings(CorsRegistry registry) {
                registry.addMapping("/api/**")
                        .allowedMethods("GET", "POST", "PUT", "DELETE");
            }
        };
    }
}
```

`RequestAuditInterceptor` is an application-defined class implementing `HandlerInterceptor`. The snippet illustrates two extension points; in a real project, configure specific CORS origins according to the application's policy.

There is no `@EnableWebMvc` here. The `WebMvcConfigurer` bean is discovered and delegated to by Boot's MVC configuration. Therefore:

- `WebMvcConfigurationSupport` is still created by Boot's MVC configuration.
- `@ConditionalOnMissingBean(WebMvcConfigurationSupport.class)` still matches.
- `WebMvcAutoConfiguration` continues registering Boot's default features.
- Customization methods such as `addInterceptors`, `addCorsMappings`, `addFormatters`, `addResourceHandlers`, and `addViewControllers` are applied alongside the default configuration.

You can declare multiple `WebMvcConfigurer` beans to split configuration by module. Spring MVC will detect and invoke the configurers. If the order among them matters, you can apply `@Order` or `Ordered` to each configurer and test the result.

### Short Example: Adding a Formatter Without Re-enabling Manual MVC

```java
@Configuration(proxyBeanMethods = false)
public class DateMvcConfiguration {

    @Bean
    WebMvcConfigurer dateFormatterConfigurer() {
        return new WebMvcConfigurer() {
            @Override
            public void addFormatters(FormatterRegistry registry) {
                registry.addFormatter(new LocalDateFormatter());
            }
        };
    }
}
```

`LocalDateFormatter` is an application formatter that must be defined separately. With this approach, Boot keeps the default MVC configuration and also invokes the custom formatter.

## 5. When Core Components Need Replacing: Use `WebMvcRegistrations`

Sometimes an application wants to provide its own implementation of certain Spring MVC components, while still wanting to keep Boot's other customizations. It is not necessary to switch to `@EnableWebMvc`.

Spring Boot provides the `WebMvcRegistrations` extension point for these components:

- `RequestMappingHandlerMapping`
- `RequestMappingHandlerAdapter`
- `ExceptionHandlerExceptionResolver`

Illustrative example:

```java
import org.springframework.boot.autoconfigure.web.servlet.WebMvcRegistrations;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping;

@Configuration(proxyBeanMethods = false)
public class CustomMvcComponents {

    @Bean
    WebMvcRegistrations webMvcRegistrations() {
        return new WebMvcRegistrations() {
            @Override
            public RequestMappingHandlerMapping
                    getRequestMappingHandlerMapping() {
                return new CustomRequestMappingHandlerMapping();
            }
        };
    }
}
```

`CustomRequestMappingHandlerMapping` is a custom class written by the application and must extend/implement appropriately for the Spring Framework API in use. The snippet above only illustrates the extension point; there is no need to replace the mapping class if you only want to add an interceptor or formatter.

Boot still creates MVC auto-configuration and feeds the custom component into the initialization process. This is a good option when you need to replace a core component yet still want Boot's resource, converter, view resolver, and property configurations to continue applying.

## 6. When Should `@EnableWebMvc` Be Used?

Use it only when the application genuinely wants **complete control over Spring MVC configuration**.

Examples:

- An internal framework already has a complete MVC configuration suite.
- The application needs deep changes to how handler mappings, adapters, exception resolvers, and infrastructure beans are registered.
- The application does not want to depend on Boot's MVC defaults and custom property mappings.
- The engineering team wants full ownership over resource handler, converter, formatter, view resolver, content negotiation, and data binding policies.

Manual configuration can start like this:

```java
@Configuration(proxyBeanMethods = false)
@EnableWebMvc
public class FullControlMvcConfiguration implements WebMvcConfigurer {

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/assets/**")
                .addResourceLocations("classpath:/assets/");
    }

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatter(new LocalDateFormatter());
    }
}
```

In this example, the application itself declares the `/assets/**` resource mapping and formatter. If WebJars, welcome page, resolvers, converters, CORS, or other configurations are still needed, register them explicitly per actual requirements.

Spring Framework notes that there should only be **one configuration class** using `@EnableWebMvc` to import MVC configuration. There can be multiple other classes implementing `WebMvcConfigurer` to break down customizations. `DelegatingWebMvcConfiguration` will discover these configurers.

### Distinguishing from WebFlux

`@EnableWebMvc` is for **Spring MVC/Servlet**. For Spring WebFlux applications, the corresponding annotation is `@EnableWebFlux` and the extension point is `WebFluxConfigurer`. The two stacks have separate configuration mechanisms; do not use `@EnableWebMvc` to customize a Reactive web application.

## 7. Minimal Experiment: Verifying Boot's Condition with `WebApplicationContextRunner`

We can prove the annotation's impact without running an embedded server. `WebApplicationContextRunner` creates a Servlet `WebApplicationContext` with a `MockServletContext`. We load `WebMvcAutoConfiguration` directly and compare three cases:

1. No user MVC configuration: Boot auto-configuration matches.
2. User enables `@EnableWebMvc`: Boot auto-configuration does not match.
3. User only registers `WebMvcConfigurer`: Boot auto-configuration still matches.

The experiment reads `ConditionEvaluationReport` to verify the exact class-level conditions, while also checking `WebMvcConfigurationSupport` and `WebMvcProperties` beans.

### 7.1. Project Structure

```text
enable-webmvc-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── demo/
                └── EnableWebMvcAutoConfigurationTest.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>enable-webmvc-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

### 7.2. Complete Test File

Create `src/test/java/demo/EnableWebMvcAutoConfigurationTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.web.servlet.WebMvcAutoConfiguration;
import org.springframework.boot.autoconfigure.web.servlet.WebMvcProperties;
import org.springframework.boot.test.context.assertj.AssertableWebApplicationContext;
import org.springframework.boot.test.context.runner.WebApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurationSupport;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

import static org.assertj.core.api.Assertions.assertThat;

class EnableWebMvcAutoConfigurationTest {

    private final WebApplicationContextRunner runner =
            new WebApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            WebMvcAutoConfiguration.class
                    ));

    private static ConditionEvaluationReport.ConditionAndOutcomes
    bootMvcOutcomes(AssertableWebApplicationContext context) {
        return ConditionEvaluationReport.get(context.getBeanFactory())
                .getConditionAndOutcomesBySource()
                .get(WebMvcAutoConfiguration.class.getName());
    }

    @Test
    void bootMvcAutoConfigurationMatchesWithoutEnableWebMvc() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(WebMvcConfigurationSupport.class);
            assertThat(context).hasSingleBean(WebMvcProperties.class);

            assertThat(bootMvcOutcomes(context)).isNotNull();
            assertThat(bootMvcOutcomes(context).isFullMatch()).isTrue();
        });
    }

    @Test
    void enableWebMvcMakesBootMvcAutoConfigurationBackOff() {
        runner.withUserConfiguration(ManualMvcConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .hasSingleBean(WebMvcConfigurationSupport.class);

                    assertThat(context).doesNotHaveBean(WebMvcProperties.class);

                    assertThat(bootMvcOutcomes(context)).isNotNull();
                    assertThat(bootMvcOutcomes(context).isFullMatch()).isFalse();
                });
    }

    @Test
    void webMvcConfigurerAloneKeepsBootMvcAutoConfiguration() {
        runner.withUserConfiguration(MvcCustomizerConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(WebMvcConfigurationSupport.class);
                    assertThat(context).hasSingleBean(WebMvcProperties.class);
                    assertThat(context).hasBean("customMvcConfigurer");

                    assertThat(bootMvcOutcomes(context)).isNotNull();
                    assertThat(bootMvcOutcomes(context).isFullMatch()).isTrue();
                });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableWebMvc
    static class ManualMvcConfiguration {
    }

    @Configuration(proxyBeanMethods = false)
    static class MvcCustomizerConfiguration {

        @Bean
        WebMvcConfigurer customMvcConfigurer() {
            return new WebMvcConfigurer() {
            };
        }
    }
}
```

Run from the `enable-webmvc-demo` directory using JDK 17+ and Maven:

```bash
mvn test
```

**Expected result:** three tests pass.

| Test | Observed bean/configuration | `WebMvcAutoConfiguration` condition outcome |
| --- | --- | --- |
| `bootMvcAutoConfigurationMatchesWithoutEnableWebMvc` | Boot provides `WebMvcConfigurationSupport` and `WebMvcProperties` | Full match: `true` |
| `enableWebMvcMakesBootMvcAutoConfigurationBackOff` | Spring Framework provides `WebMvcConfigurationSupport`; Boot MVC properties adapter is not registered by this auto-config | Full match: `false` |
| `webMvcConfigurerAloneKeepsBootMvcAutoConfiguration` | `customMvcConfigurer` bean exists and Boot still provides MVC configuration/properties | Full match: `true` |

`ConditionEvaluationReport` groups conditions by source. Here, the source is the fully qualified name of `WebMvcAutoConfiguration`. `isFullMatch()` returns `true` when all conditions recorded for that source match. In the second test, the missing-bean condition fails to match because `@EnableWebMvc` imported a subclass of `WebMvcConfigurationSupport`.

The tests use `WebApplicationContextRunner` because Boot's condition requires a Servlet web application. If using a plain `ApplicationContextRunner`, `@ConditionalOnWebApplication(type = SERVLET)` would fail to match and we would not be testing the exact cause under study.

The tests are designed to isolate the **auto-configuration decision**. They do not launch a real HTTP server and do not prove every route/static resource in a production application works; to test actual requests, add an integration test with `@SpringBootTest(webEnvironment = RANDOM_PORT)`.

## 8. Diagnosing When the Application No Longer Receives Boot's MVC Configuration

### 8.1. Locating the Source of `@EnableWebMvc`

Search in the source code for:

- `@EnableWebMvc` on `@Configuration` classes.
- Configuration classes extending `WebMvcConfigurationSupport` or `DelegatingWebMvcConfiguration`.
- Configurations imported from shared modules or internal starters.
- Configurations automatically discovered by component scan.

Do not search only in the main application class. The annotation may reside in a configuration module imported indirectly.

### 8.2. Inspecting the Condition Evaluation Report

Start the application with:

```bash
java -jar app.jar --debug
```

Look for the `WebMvcAutoConfiguration` source. If the `@ConditionalOnMissingBean(WebMvcConfigurationSupport.class)` condition does not match, the message will state what type of bean was found. This is direct evidence that manual MVC configuration is making Boot back off.

You can check via the `/actuator/conditions` endpoint if Actuator is added and the endpoint is safely exposed. Do not expose internal configuration reports to a public network.

### 8.3. Distinguishing MVC Errors from Servlet Container Errors

If `@EnableWebMvc` is added, yet:

- The application still starts and has an embedded server: that is consistent, because Servlet container auto-configuration is independent of `WebMvcAutoConfiguration`.
- Controllers are not mapped: check component scan, request mappings, context, and handler mapping configuration.
- Static files return 404: check `addResourceHandlers`, resource locations, and path patterns.
- JSON converters behave differently than before: inspect the actual `HttpMessageConverter` list in `RequestMappingHandlerAdapter`.
- Date/time formatting differs: check `addFormatters` and `ConversionService` configuration.
- View resolvers cannot find templates: check `ViewResolver` beans, resolver ordering, and template engine.

Do not blame every web error after adding the annotation on DispatcherServlet or the embedded server. First determine which part of MVC auto-configuration backed off.

## 9. Common Misconceptions

| Misconception | Correct Understanding |
| --- | --- |
| "`@EnableWebMvc` turns on extra features that Boot does not have." | It imports Spring Framework's MVC configuration and makes Boot MVC auto-configuration back off. |
| "With `@EnableWebMvc`, all Spring Boot auto-configuration is disabled." | Only `WebMvcAutoConfiguration` is blocked by the missing-bean condition; other auto-configurations evaluate their own conditions. |
| "Without `@EnableWebMvc`, you cannot add interceptors or formatters." | Registering a `WebMvcConfigurer` bean is the standard way to extend Boot's MVC. |
| "`WebMvcConfigurer` also makes Boot back off." | No. This bean is not `WebMvcConfigurationSupport`. |
| "`@EnableWebMvc` disables DispatcherServlet and embedded Tomcat." | No. It changes MVC configuration; the servlet container and DispatcherServlet have separate auto-configurations. |
| "`spring.mvc.*` is always ignored completely." | Properties are not applied through the MVC adapter that backed off; identify which property is read by which component. |
| "To replace HandlerMapping you must enable `@EnableWebMvc`." | You can use `WebMvcRegistrations` to replace certain components while keeping Boot MVC auto-configuration. |
| "`@EnableWebMvc` is a WebFlux annotation." | No. WebFlux uses `@EnableWebFlux` and `WebFluxConfigurer`. |
| "You can put `@EnableWebMvc` on multiple configurations to split modules." | There should only be one configuration class importing MVC via this annotation; there can be multiple `WebMvcConfigurer` instances. |

## 10. Checklist for Choosing the Right Mechanism

Before adding the annotation, ask yourself:

1. Do I only want to add interceptors, formatters, CORS, view controllers, or resource handlers? → Use a `WebMvcConfigurer` bean.
2. Do I need to replace a `RequestMappingHandlerMapping`, `RequestMappingHandlerAdapter`, or exception resolver while keeping Boot configuration? → Look at `WebMvcRegistrations`.
3. Do I want to manage the full MVC infrastructure, converters, resource handlers, view resolvers, binding, and content negotiation myself? → `@EnableWebMvc` may be appropriate.
4. Am I accidentally extending `WebMvcConfigurationSupport` or importing a configuration using `@EnableWebMvc` from another module?
5. After making changes, have I checked the condition report, bean definitions, and HTTP behavior?

**Takeaway:** `@EnableWebMvc` imports `DelegatingWebMvcConfiguration`, a subclass of `WebMvcConfigurationSupport`. Spring Boot 3.3 applies `WebMvcAutoConfiguration` only when **no** bean of type `WebMvcConfigurationSupport` exists yet. Therefore, adding `@EnableWebMvc` makes Boot MVC auto-configuration back off and leaves the application to manage many MVC customizations itself. If you only want to extend behavior, add `WebMvcConfigurer` without `@EnableWebMvc`; if you want to replace certain core components, look at `WebMvcRegistrations`.

### Official References

- Spring Boot 3.3 — Servlet Web Applications / Spring MVC Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- Spring Boot 3.3 API — `WebMvcAutoConfiguration`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/servlet/WebMvcAutoConfiguration.html
- Spring Framework 6.1 — `@EnableWebMvc` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/web/servlet/config/annotation/EnableWebMvc.html
- Spring Framework 6.1 — `DelegatingWebMvcConfiguration` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/web/servlet/config/annotation/DelegatingWebMvcConfiguration.html
- Spring Framework 6.1 — `WebMvcConfigurationSupport` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/web/servlet/config/annotation/WebMvcConfigurationSupport.html
- Spring Boot 3.3 API — `WebApplicationContextRunner`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/WebApplicationContextRunner.html