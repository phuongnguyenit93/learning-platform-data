# Impact of @EnableWebMvc and WebMvcConfigurationSupport in Spring Boot

## Learning Objectives

When building a Spring Boot application using Spring MVC, you typically do not need to enable MVC manually. Spring Boot already configures MVC by default and lets you extend it via **WebMvcConfigurer**. Adding **@EnableWebMvc** or a bean extending **WebMvcConfigurationSupport** can completely change the source of MVC configuration. This is a common reason why an application that previously served static files or an index page suddenly returns HTTP 404 after a configuration class is added.

After this lesson, you will be able to:

- Explain how Spring Boot MVC auto-configuration differs from Spring Framework MVC Java configuration.
- Describe the relationship between **@EnableWebMvc**, **DelegatingWebMvcConfiguration**, and **WebMvcConfigurationSupport**.
- Understand why a `WebMvcConfigurationSupport`-typed bean causes Spring Boot's **WebMvcAutoConfiguration** to back off.
- Distinguish features that are actually affected from core MVC capabilities that continue working.
- Choose **WebMvcConfigurer** to extend MVC while keeping Spring Boot's defaults.
- Recognize situations where intentionally using `@EnableWebMvc` or extending the base MVC configuration is appropriate.
- Diagnose, restore, and prevent configuration issues involving static resources, JSON, formatters, interceptors, CORS, and view resolvers.

## 1. The Spring MVC Configuration Picture in Spring Boot

Spring MVC is Spring Framework's web framework, built on the Servlet API and using **DispatcherServlet** to receive requests, resolve handlers, invoke controllers, and produce responses. Spring Framework comes with its own MVC configuration infrastructure. Spring Boot adds an auto-configuration layer on top so developers do not have to manually register and tune every MVC component.

In a Spring Boot Servlet application with the appropriate MVC starter, when conditions are met, **WebMvcAutoConfiguration** sets up a number of utilities on top of Spring Framework's MVC configuration:

- Registering and integrating appropriate view resolvers.
- Setting up static resource serving, typically from `classpath:/static/`, `classpath:/public/`, and other default locations.
- Supporting the `index.html` welcome page when configuration and resources match.
- Integrating application `Converter`, `Formatter`, and HTTP message converter beans/configuration.
- Adding Spring Boot Web MVC customizations, such as certain data binding mechanisms, resource handling, and related properties.

Details may vary across Spring Boot versions; therefore, you should not treat the utilities listed above as an immutable API guarantee across all major versions.

Typical model:

~~~text
SpringApplication
   |
   +-- Servlet web application
   |
   +-- Spring Framework MVC infrastructure
   |       |
   |       +-- DispatcherServlet
   |       +-- HandlerMapping / HandlerAdapter
   |       +-- HandlerExceptionResolver
   |       +-- message conversion / validation / view resolution
   |
   +-- Spring Boot WebMvcAutoConfiguration
           |
           +-- MVC defaults and integrations
           +-- static resources and welcome page support
           +-- available converters, formatters, view resolvers
           +-- callbacks supplied by WebMvcConfigurer beans
~~~

Keep in mind: **Spring Boot MVC auto-configuration is an enhancement layer**, whereas **Spring MVC infrastructure** is the foundation. Losing the auto-configuration layer does not mean all MVC controllers stop working.

## 2. What Does @EnableWebMvc Do?

**@EnableWebMvc** is a Spring Framework annotation located in the package:

~~~java
org.springframework.web.servlet.config.annotation.EnableWebMvc
~~~

It is used to enable Spring MVC Java configuration. Mechanically, this annotation imports **DelegatingWebMvcConfiguration**, a class that extends **WebMvcConfigurationSupport**:

~~~text
@EnableWebMvc
     |
     v
@Import(DelegatingWebMvcConfiguration.class)
     |
     v
DelegatingWebMvcConfiguration
     |
     +-- extends WebMvcConfigurationSupport
     |
     +-- collects WebMvcConfigurer beans
     |
     +-- registers core Spring MVC infrastructure
~~~

As a result, Spring Framework still registers the infrastructure needed for annotated controllers such as `@Controller`, `@RestController`, `@RequestMapping`, handler adapters, and resolvers. If supporting libraries are on the classpath, Spring Framework's default converters may still be configured.

In a plain Spring Framework project without Spring Boot, `@EnableWebMvc` is a sensible way to enable MVC Java configuration. In a Spring Boot project, however, it usually signals that the application **wants to manage MVC configuration itself** rather than use Boot's MVC defaults.

Example configuration switching a Boot app to self-managed MVC mode:

~~~java
package com.example.demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;

@Configuration
@EnableWebMvc
public class FullMvcConfiguration {
}
~~~

The class above illustrates a configuration decision and is **not** the recommended choice for a typical Spring Boot application.

## 3. Why Is Spring Boot's WebMvcAutoConfiguration Disabled?

Spring Boot applies conditional auto-configuration. A key condition on MVC configuration is **@ConditionalOnMissingBean(WebMvcConfigurationSupport.class)**. Conceptually, the logic looks like this:

~~~java
// Conceptual illustration of the condition, not the full WebMvcAutoConfiguration source:
@ConditionalOnMissingBean(WebMvcConfigurationSupport.class)
class WebMvcAutoConfiguration {
    // Spring Boot MVC integrations
}
~~~

Normally, when no `WebMvcConfigurationSupport` bean is provided by the application, this condition allows Boot to participate in configuring MVC.

When `@EnableWebMvc` is placed:

1. The annotation imports `DelegatingWebMvcConfiguration`.
2. `DelegatingWebMvcConfiguration` extends `WebMvcConfigurationSupport`.
3. Spring sees a configuration bean of type `WebMvcConfigurationSupport`.
4. The missing-bean condition is no longer satisfied.
5. Spring Boot's `WebMvcAutoConfiguration` backs off, yielding MVC configuration to Spring Framework and the application's classes.

When you declare a class **@Configuration extends WebMvcConfigurationSupport** directly, the condition is also no longer satisfied, even if that class **does not have @EnableWebMvc**.

This is the core cause-and-effect relationship of this lesson:

~~~text
WebMvcConfigurer alone
        |
        +--> does NOT provide WebMvcConfigurationSupport
        |
        +--> Spring Boot MVC auto-configuration can remain active

@EnableWebMvc
        |
        +--> imports DelegatingWebMvcConfiguration
        |      (a WebMvcConfigurationSupport subtype)
        |
        +--> Spring Boot WebMvcAutoConfiguration backs off

@Configuration extends WebMvcConfigurationSupport
        |
        +--> provides WebMvcConfigurationSupport directly
        |
        +--> Spring Boot WebMvcAutoConfiguration backs off
~~~

**Scope distinction:** The condition above applies to **WebMvcAutoConfiguration**. It does not automatically disable all other Spring Boot auto-configurations such as datasource, embedded server, logging, or all of Actuator. Each Boot component has its own conditions.

## 4. What Changes After Adding @EnableWebMvc?

You should not simply conclude that "with `@EnableWebMvc`, Spring MVC is broken." The application can still start, `DispatcherServlet` still receives requests, and `@RestController` still returns results. What changes is that **Boot's automatic utilities and MVC-specific integrations** are no longer created by default.

| Aspect | Default Boot MVC | After `@EnableWebMvc` or Custom `WebMvcConfigurationSupport` |
|---|---|---|
| `DispatcherServlet` and controllers | Auto-configured by Boot and Spring MVC | Core MVC infrastructure can still work via Spring Framework configuration |
| Resource handlers for static files | Boot registers default mappings/resource locations | Do not expect Boot's resource mappings to remain active; usually must be registered manually |
| Welcome `index.html` page | Boot has a dedicated welcome page mechanism | Boot's welcome page mechanism may no longer apply |
| View resolvers | Boot integrates resolvers based on classpath and configuration | Only resolvers actually provided by base MVC config/application remain |
| `Converter` / `Formatter` | Boot contributes beans and defaults | Depends on MVC Java Config, classpath, and manually added configuration |
| JSON via Jackson | Boot integration present when appropriate libraries exist | May still work via Spring Framework converters; do not assume JSON is disabled |
| MVC properties in `application.properties` | Many properties applied by MVC auto-config | Properties tied to MVC auto-config may no longer take effect as expected |
| `WebMvcConfigurer` beans | Contributes to Boot's MVC configuration | May still be used by `DelegatingWebMvcConfiguration`; does not automatically restore Boot-specific defaults |

Classic example: `src/main/resources/static/logo.png` is accessible at `/logo.png` in a default MVC app. After adding `@EnableWebMvc`, the default resource handler provided by Spring Boot may disappear and requests return 404 until the application adds an equivalent mapping.

Statements to avoid:

- "Adding `@EnableWebMvc` will always make REST APIs return 404": false; controller mappings can still work.
- "Adding `@EnableWebMvc` will always break JSON completely": false; JSON depends on available converters.
- "Adding `@EnableWebMvc` turns off Spring Boot": false; it only affects configurations matching specific conditions.
- "Just implementing `WebMvcConfigurer` also causes Boot to back off": false; that is the extension mechanism Boot recommends.
- "Removing `@EnableWebMvc` is always enough to fix everything": not necessarily; another `WebMvcConfigurationSupport` bean may also cause Boot to back off.

## 5. Recommended Approach: Use WebMvcConfigurer Without @EnableWebMvc

For most Spring Boot applications, create a **@Configuration implements WebMvcConfigurer** and override only the callbacks you need.

Typical callbacks:

| Callback | Purpose |
|---|---|
| `addInterceptors` | Register `HandlerInterceptor` for Spring MVC requests |
| `addCorsMappings` | Add CORS policies for routes |
| `addFormatters` | Register `Converter` or `Formatter` |
| `addResourceHandlers` | Add static resource serving for custom paths |
| `addViewControllers` | Create simple view controllers or redirects |
| `configurePathMatch` | Customize path matching rules |
| `configureAsyncSupport` | Configure Servlet async processing support |
| `extendMessageConverters` | Refine the converter list after configuration (check API differences by version) |

### Runnable Illustrative Example

Suppose you use a project generated with Spring Initializr, Java 17+, Spring Boot 3.x, and the Spring Web (`spring-boot-starter-web`) dependency. The Java files below live in the same `com.example.mvc` package so they can be discovered by component scanning.

**DemoApplication.java**:

~~~java
package com.example.mvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

**GreetingController.java**:

~~~java
package com.example.mvc;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    @GetMapping("/api/hello")
    public Map<String, String> hello() {
        return Map.of("message", "Hello MVC");
    }
}
~~~

**MvcCustomization.java**:

~~~java
package com.example.mvc;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.ViewControllerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class MvcCustomization implements WebMvcConfigurer {

    @Override
    public void addViewControllers(ViewControllerRegistry registry) {
        registry.addRedirectViewController("/start", "/api/hello");
    }

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://client.example")
                .allowedMethods("GET");
    }

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/docs/**")
                .addResourceLocations("classpath:/docs/");
    }
}
~~~

Do not place `@EnableWebMvc` on this class or any other configuration class. The goal is to extend MVC while letting Spring Boot handle auto-configuration.

Create two optional resource files:

~~~text
src/main/resources/static/readme.txt
src/main/resources/docs/guide.txt
~~~

For example, the content of **readme.txt** is **Boot static**, and **guide.txt** is **Internal documentation**.

Run the application from the project directory:

~~~bash
./mvnw spring-boot:run
~~~

On Windows with the Maven Wrapper:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Test the endpoints:

~~~bash
curl -i http://localhost:8080/api/hello
curl -i http://localhost:8080/start
curl -i http://localhost:8080/readme.txt
curl -i http://localhost:8080/docs/guide.txt
~~~

With the starter and configuration above, expected results:

- `GET /api/hello` returns HTTP 200 with JSON having property `message` equal to **Hello MVC**.
- `GET /start` returns an HTTP redirect to `/api/hello`; you can inspect the `Location` header with **curl -i**.
- `GET /readme.txt` can be served by Boot from the default static directory.
- `GET /docs/guide.txt` is served by the newly declared resource handler.

The example's CORS policy only permits origin `https://client.example` for `/api/**` routes; it does not block `curl` commands without an `Origin` header, nor does it replace CORS configuration when Spring Security participates in the request processing chain.

If your project uses Spring Boot 4.x, use the MVC starter and APIs corresponding to your major version. The principle of using `WebMvcConfigurer` without `@EnableWebMvc` remains the same, though starter names and some converter APIs may change across versions.

## 6. Before-and-After Comparison Using a Practical Scenario

Suppose an application already works with:

~~~text
src/main/resources/static/index.html
src/main/resources/static/assets/app.js
~~~

In default Spring Boot MVC configuration, the system typically has:

~~~text
GET /               -> welcome page index.html
GET /assets/app.js  -> static JavaScript
GET /api/hello      -> GreetingController
~~~

A developer wants to add an interceptor, but writes:

~~~java
@Configuration
@EnableWebMvc
public class ApiWebConfiguration implements WebMvcConfigurer {
    // addInterceptors(...) and custom callbacks
}
~~~

At that point, Spring Boot's MVC configuration backs off. Controller endpoints may still work, but Boot's welcome page mechanism and default resource mappings are at risk of disappearing. Depending on configuration, users will observe 404 at `/` or `/assets/app.js`.

The appropriate fix when you only need to add an interceptor is to **remove @EnableWebMvc** and keep:

~~~java
@Configuration
public class ApiWebConfiguration implements WebMvcConfigurer {
    // addInterceptors(...) and custom callbacks
}
~~~

After restarting, Boot resumes deciding MVC defaults without being blocked by a `WebMvcConfigurationSupport` bean. Actually test the previous URLs, especially if custom resource handlers, a reverse proxy, or Spring Security are also configured.

This fix is simpler than copying all of Boot's resource handlers, welcome page handlers, and converters into application code.

## 7. How Is Extending WebMvcConfigurationSupport Directly Different?

**WebMvcConfigurationSupport** is the base MVC configuration class in package:

~~~java
org.springframework.web.servlet.config.annotation.WebMvcConfigurationSupport
~~~

Example of a class intentionally extending it:

~~~java
package com.example.mvc;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurationSupport;

@Configuration
public class ManualMvcConfiguration extends WebMvcConfigurationSupport {

    @Override
    protected void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/files/**")
                .addResourceLocations("classpath:/files/");
    }
}
~~~

This is an approach that **takes over control of MVC configuration**. As soon as a bean extending `WebMvcConfigurationSupport` appears in the context, Spring Boot's `WebMvcAutoConfiguration` condition can fail to match, regardless of whether the class has `@EnableWebMvc`.

When using a custom subclass, you take responsibility for setting up the MVC features the application needs, including resource handling, converters, path matching, validators, and other settings. If you only want to add `/files/**`, a better approach in a Boot app is usually implementing `WebMvcConfigurer` as in Section 5.

### Difference Between WebMvcConfigurationSupport and DelegatingWebMvcConfiguration

- `WebMvcConfigurationSupport` creates the MVC infrastructure configuration and provides `protected` methods for deep customization.
- `DelegatingWebMvcConfiguration` extends `WebMvcConfigurationSupport` and discovers/delegates callbacks to `WebMvcConfigurer` beans in the context.
- `@EnableWebMvc` imports `DelegatingWebMvcConfiguration`.
- A custom subclass of `WebMvcConfigurationSupport` should not be assumed to automatically process all `WebMvcConfigurer` beans from other modules the way `DelegatingWebMvcConfiguration` does.
- Spring Framework has advanced configuration patterns based on `DelegatingWebMvcConfiguration`; in Boot, that approach also makes you responsible for the MVC defaults Boot previously supplied.

Do not simultaneously declare `@EnableWebMvc` and multiple base MVC configuration classes just to see which wins. Doing so can cause duplicate beans, mapping conflicts, or context startup failures.

## 8. When Are @EnableWebMvc or WebMvcConfigurationSupport Actually Needed?

There are several valid situations:

1. A plain Spring Framework application that does not use Spring Boot's MVC auto-configuration utilities.
2. A system requiring complete control over MVC infrastructure, explicitly registering and managing every related bean.
3. A specialized framework integration that requires replacing base MVC configuration in a way that cannot be satisfied by callbacks or high-level extension points.

However, in a Spring Boot application with common needs such as adding an interceptor, converter, formatter, CORS, or a resource handler, first use **WebMvcConfigurer**. If you need to replace certain low-level beans while keeping Boot integrations, look at **WebMvcRegistrations** in the documentation for your running version.

Other extension points can be used depending on the task, such as **Converter**, **Formatter** beans, or HTTP message converter customization via mechanisms supported by Spring Boot. Do not replace the entire infrastructure just to adjust one detail.

## 9. Converters and JSON: A Common Trap

Spring MVC uses **HttpMessageConverter** implementations to transfer data between HTTP requests/responses and Java objects. For example, `@RequestBody` needs a converter to read JSON into an object, while `@ResponseBody` typically uses a converter to write an object as JSON.

When `@EnableWebMvc` is present:

- Spring Boot's `HttpMessageConverters` MVC integration may not be applied.
- Spring Framework MVC Java Config still has a mechanism to register default converters based on libraries present on the classpath.
- Therefore, JSON **may still work** if Jackson and an appropriate converter are present. You cannot conclude solely from the presence of `@EnableWebMvc` that all JSON endpoints will fail.
- Custom `ObjectMapper` or converter configurations provided by the application/Boot should be checked to verify they still participate in the MVC pipeline properly.

In Spring Framework 6.x, two callbacks are commonly seen:

- **configureMessageConverters(List)**: can alter how the default list is registered. Adding converters carelessly here can prevent default converters from being used.
- **extendMessageConverters(List)**: allows adjusting the list after converters have been configured.

Spring Framework 7.x introduces a new API for configuring converters; read the corresponding documentation rather than copying older converter customization code verbatim.

When an endpoint that previously returned JSON starts returning **406 Not Acceptable** or **415 Unsupported Media Type** after a configuration change, inspect `Accept`, `Content-Type`, the converter list, Jackson dependencies, and request/response handling. These errors can have many causes; do not try to fix them by turning on `@EnableWebMvc`.

## 10. Distinguishing from Unrelated Configurations

### @SpringBootApplication

This annotation enables Spring Boot's general auto-configuration and component scanning. You do not need to add `@EnableWebMvc` for `@RestController` endpoints to work. Adding `@EnableWebMvc` to the application class can cause `WebMvcAutoConfiguration` to back off as analyzed above.

### @EnableWebFlux

`@EnableWebFlux` is for **Spring WebFlux**, not Spring MVC. Do not use it as a substitute for `@EnableWebMvc` in a Servlet MVC application. Boot has separate WebFlux configuration mechanisms and different behavior.

### Spring Security

Spring Security has its own filter chain. Changing `HandlerMapping` or MVC matching can affect matchers and protected URLs, but `@EnableWebMvc` does not automatically disable Security. If endpoint behavior changes after configuring MVC, inspect both the filter chain and MVC mappings.

### Embedded Server

`server.port`, `server.address`, and embedded Tomcat configuration are not automatically lost just because MVC `WebMvcAutoConfiguration` backs off. The embedded server has its own auto-configuration. Thus, an application can still listen on the HTTP port normally while static resources or certain MVC defaults change.

### Spring Boot Actuator

Actuator also has its own configuration and paths. You cannot conclude that all of Actuator disappears when `@EnableWebMvc` is added. If management endpoints fail, check dependencies, management port/base path, security, and active auto-configurations.

## 11. How to Confirm WebMvcAutoConfiguration Is Still Active

When you suspect Boot's MVC configuration has backed off, follow this procedure:

1. Search for **@EnableWebMvc** across application `@Configuration` classes or integrated libraries.
2. Search for beans of type **WebMvcConfigurationSupport**, including direct or indirect subclasses.
3. Check for **DelegatingWebMvcConfiguration** and base MVC configuration classes in the context.
4. Inspect the **WebMvcAutoConfiguration** conditions in the condition evaluation report.
5. Verify observable URLs: API controllers, static resources, welcome page, CORS, and message conversion.
6. If only callbacks are needed, switch the configuration to **WebMvcConfigurer**, restart, and run appropriate HTTP tests.

### Enabling the Condition Evaluation Report

You can use debug mode when starting the application to see which auto-configurations matched and did not match:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

Exact output varies by version and environment. In the report, look for **WebMvcAutoConfiguration** and the reason why the `WebMvcConfigurationSupport`-related condition did not match. Do not rely on exact log line numbers because report formatting can change.

In properly managed environments, Spring Boot Actuator also provides the **conditions** endpoint to inspect auto-configuration condition results, if the endpoint is added and secured appropriately. Avoid exposing diagnostic endpoints to the public internet.

### Useful Regression Checks

After changing MVC configuration, test at minimum:

- Controller `GET /api/hello` returns expected content and HTTP 200.
- Static files in default locations respond at their URLs if the system uses them.
- Welcome page works if the application needs a home page.
- JSON requests with appropriate `Content-Type`/`Accept` can be read and written.
- Routes with custom interceptors, formatters, CORS, or resource handlers still work.
- Spring Security rules have not become broader or narrower than intended.

Compare before and after under the same profile to avoid confusing MVC configuration errors with environment differences.

## 12. Quick Decision Table

| Requirement | Preferred Approach | Keeps Boot MVC Auto-Configuration? |
|---|---|---|
| Add `HandlerInterceptor` | `implements WebMvcConfigurer`, `addInterceptors` | Usually yes |
| Add CORS policy for MVC routes | `implements WebMvcConfigurer`, `addCorsMappings` | Usually yes |
| Add `Formatter` or `Converter` | `WebMvcConfigurer` / Boot-style bean | Usually yes |
| Add custom static URL | `implements WebMvcConfigurer`, `addResourceHandlers` | Usually yes |
| Add redirect or view controller | `implements WebMvcConfigurer`, `addViewControllers` | Usually yes |
| Customize converters | Version-compatible extension API/bean | Can preserve |
| Replace part of advanced MVC infrastructure | Check `WebMvcRegistrations` and extension points | Can preserve, depending on implementation |
| Full control over Spring MVC Java Config | `@EnableWebMvc` or custom base configuration | Boot `WebMvcAutoConfiguration` backs off |
| Extend `WebMvcConfigurationSupport` | Use only with clear architectural reason | Boot `WebMvcAutoConfiguration` backs off |

"Usually yes" in the table assumes no other `WebMvcConfigurationSupport` bean causes Boot to back off. Inspect the entire context when multiple modules and starters are integrated.

## 13. Self-Check Questions and Answers

**Question 1:** Does a class that merely implements `WebMvcConfigurer` automatically cause Boot to lose MVC auto-configuration?

Answer: No. This is the extension approach recommended by Spring Boot, provided no `@EnableWebMvc` or other `WebMvcConfigurationSupport` causes the missing-bean condition to fail.

**Question 2:** Why does `@EnableWebMvc` cause `WebMvcAutoConfiguration` to back off?

Answer: `@EnableWebMvc` imports `DelegatingWebMvcConfiguration`, a subclass of `WebMvcConfigurationSupport`. A bean of this type causes `@ConditionalOnMissingBean(WebMvcConfigurationSupport.class)` not to match.

**Question 3:** Why can extending `WebMvcConfigurationSupport` directly have a similar consequence?

Answer: That configuration class itself supplies a `WebMvcConfigurationSupport` bean, so Spring Boot does not continue auto-configuring its own MVC setup.

**Question 4:** Can `@RestController` and JSON still work after `@EnableWebMvc`?

Answer: Possibly. Spring Framework MVC Java Config still provides controller infrastructure and appropriate converters if the corresponding dependencies are present. Verify concretely rather than assuming everything is disabled.

**Question 5:** A Boot application loses `index.html` and static files right after adding a new MVC configuration. What should be checked first?

Answer: Look for `@EnableWebMvc` or a `WebMvcConfigurationSupport` subclass, and inspect the condition report for `WebMvcAutoConfiguration`. If only an interceptor or CORS is needed, switch to `WebMvcConfigurer` without enabling `@EnableWebMvc`.

**Question 6:** Does `@EnableWebMvc` stop embedded Tomcat from running?

Answer: Not as a direct consequence. Embedded Tomcat is configured by other parts of Spring Boot; the application may continue listening for HTTP while losing certain MVC defaults.

## 14. Official References

- [Spring Boot — Servlet Web Applications](https://docs.spring.io/spring-boot/reference/web/servlet.html): Spring MVC Auto-configuration, static resources, and customizing MVC.
- [Spring Boot — Customize Spring MVC](https://docs.spring.io/spring-boot/how-to/spring-mvc.html): MVC customization mechanisms, `HttpMessageConverters`, and enabling full MVC control.
- [Spring Framework — Enable MVC Configuration](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/enable.html): how `@EnableWebMvc` enables MVC Java Config.
- [Spring Framework — Advanced Java Config](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/advanced-java.html): `DelegatingWebMvcConfiguration` and advanced configuration.
- [Spring Framework — Static Resources](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html): `ResourceHandlerRegistry` and manually registering resource paths.
- [Spring Framework — Message Converters](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/message-converters.html): API choices for adding and customizing converters.
