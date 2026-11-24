# Comparing Auto-Configuration Conditions When Adding Beans or `@EnableWebMvc`/`@EnableWebFlux`

**A small change like adding a `@Bean`, `@EnableWebMvc`, or `@EnableWebFlux` can alter a Spring Boot app's behavior without touching a single controller.** For example: static resources start returning 404, Jackson/codecs change, CORS disappears, a default service bean is no longer created, or a framework component gets replaced by an application bean. When debugging, pinpoint **which auto-configuration condition matched or failed to match, which bean made the difference, and which HTTP behavior actually changed**. Avoid vague claims like "Spring Boot got turned off."

This article belongs to **Spring Boot - web-runtime → Debugging and Upgrades**, covering **Comparing Auto-Configuration Conditions When Adding Beans or `@EnableWebMvc`/`@EnableWebFlux`**. Content and examples anchor on **Spring Boot 3.3.13, Java 17, and Maven**, using two independent **MVC/Servlet** and **WebFlux/reactive** projects with conditional user beans, condition reports, static resources, CORS, and HTTP integration tests. Properties and scenarios are tied to that version; verify source/Javadoc and actual reports before applying to another Boot version.

## 1. Learning Outcomes

After this article, you will be able to:

1. Explain **`@SpringBootApplication`, `@EnableAutoConfiguration`, `@ComponentScan`** and when Spring Boot registers default beans.
2. Read **`@ConditionalOnClass`, `@ConditionalOnWebApplication`, `@ConditionalOnBean`, `@ConditionalOnMissingBean`, `@ConditionalOnProperty`, `@ConditionalOnSingleCandidate`**.
3. Distinguish auto-configuration **class-level backoff**, **method-level backoff**, and **bean override/name conflicts**.
4. Understand why a `@Bean` returning the right type can replace a default bean via `MissingBean` without needing a matching bean name.
5. Identify whether Boot selected **SERVLET/MVC** or **REACTIVE/WebFlux**, especially when both starters coexist.
6. Explain how **`WebMvcAutoConfiguration`** depends on the absence of **`WebMvcConfigurationSupport`**, and the effect of **`@EnableWebMvc`**.
7. Explain how **`WebFluxAutoConfiguration`** depends on the absence of **`WebFluxConfigurationSupport`**, and the effect of **`@EnableWebFlux`**.
8. Extend Boot using **`WebMvcConfigurer`/`WebFluxConfigurer`** without `@Enable` to preserve Boot defaults whenever possible.
9. Understand the roles of **`WebMvcRegistrations`** and **`WebHttpHandlerBuilderCustomizer`**.
10. Use **`--debug`**, **`ConditionEvaluationReport`**, **`/actuator/conditions`**, **`/actuator/beans`**, and **`/actuator/mappings`**.
11. Write real HTTP tests verifying **default vs. custom beans**, **static files**, **CORS**, and **condition outcomes**.
12. Build a repeatable upgrade/regression workflow traced from **condition → bean/mapping → runtime behavior**.

## 2. Auto-Configuration Is *Conditional* Configuration

### 2.1. Conceptual Execution Flow

`@SpringBootApplication` combines `@SpringBootConfiguration`, `@EnableAutoConfiguration`, and `@ComponentScan`. Spring Boot gathers auto-configuration candidates based on the classpath, environment, and registered bean definitions, activating only those whose conditions pass.

~~~text
Dependencies + spring.* properties + active profiles
                        |
                        v
          ApplicationContext + user configs
                        |
                        v
             Auto-configuration candidates
                |       |        |
                v       v        v
           OnClass   OnBean   OnWebApplication
                |       |        |
                +-------+--------+
                        |
               match or not match
                        |
               create/skip bean defaults
                        |
                        v
     DispatcherServlet / DispatcherHandler / HTTP routes
~~~

Because many auto-configurations use **`@ConditionalOnMissingBean`**, a user-defined bean gets the chance to **replace the default**. Only **the relevant conditions** change; unrelated auto-configurations remain unaffected.

### 2.2. What Does "Back Off" Mean?

Hypothetical example:

~~~java
@AutoConfiguration
class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService defaultGreetingService() {
        return name -> "default:" + name;
    }
}
~~~

When the app has no `GreetingService`, Boot creates `defaultGreetingService`. When a user configuration provides:

~~~java
@Bean
GreetingService greetingService() {
    return name -> "custom:" + name;
}
~~~

the **`@ConditionalOnMissingBean(GreetingService.class)`** condition fails to match and `defaultGreetingService` is skipped. This is **method-level bean backoff**; beans for Tomcat, Jackson, Actuator, or MVC still get created normally. Both snippets are built into a runnable project in section 8.

### 2.3. Common Conditions

| Condition | What is checked | Example |
| --- | --- | --- |
| `@ConditionalOnClass` | Is class on the classpath? | Servlet/`DispatcherServlet` present to consider MVC. |
| `@ConditionalOnMissingClass` | Is class absent? | Skip integration when dependency is absent. |
| `@ConditionalOnWebApplication` | Is context type `SERVLET`/`REACTIVE`? | MVC and WebFlux don't both auto-config in a default app. |
| `@ConditionalOnBean` | Does a bean of matching type/name/annotation exist? | Create adapter only when dependency bean is configured. |
| `@ConditionalOnMissingBean` | Is no matching bean present? | User bean prevents creating the default bean. |
| `@ConditionalOnSingleCandidate` | Is there a single/primary candidate bean? | Default integration for a single `DataSource`. |
| `@ConditionalOnProperty` | Does property match expected value? | Toggle feature via configuration. |
| `@ConditionalOnResource` | Does resource exist? | Enable config when file/classpath resource exists. |
| `@ConditionalOnExpression` | Does SpEL expression evaluate true? | Complex dynamic condition; avoid unless needed. |

Do not assume every condition checks **bean names**. Many conditions match by **type**, and some consider search strategies across parent contexts or bean annotations. To be sure, inspect the condition annotation in your Boot version and the actual report message.

### 2.4. Bean Registration Order and Metadata

`@ConditionalOnMissingBean` evaluates against bean definitions **already processed when the condition runs**, rather than instantiating every runtime object to inspect concrete types. Boot orders auto-configuration after user configuration so user beans can override defaults. Using `MissingBean` casually in ordinary `@Configuration` classes with unclear ordering can yield surprises.

For custom starters, use **`@AutoConfiguration`**, register in **`META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`**, set clear conditions, and use `AutoConfigureBefore`/`After` only when auto-config ordering truly depends on it. **`@DependsOn`** adjusts initialization order; it does not replace auto-configuration condition evaluation.

### 2.5. Three Distinct Failure Modes

~~~text
@ConditionalOnMissingBean sees user bean
    -> default bean is skipped intentionally

Two bean definitions share the same name
    -> may throw BeanDefinitionOverrideException

Two beans share an interface, injection has no qualifier/primary
    -> may throw NoUniqueBeanDefinitionException
~~~

**`@Primary`** picks a preferred candidate for injection; it does not remove the other bean. **`@Qualifier`** selects a specific dependency; it does not disable auto-configuration. Never set **`spring.main.allow-bean-definition-overriding=true`** just to hide an uninvestigated conflict.

## 3. MVC and WebFlux Are Selected by Web Application Type

### 3.1. Spring MVC/Servlet

**`spring-boot-starter-web`** typically supplies Spring MVC, Jakarta Servlet, and embedded Tomcat. Boot chooses **`ServletWebServerApplicationContext`** and auto-configures `DispatcherServlet`/WebMvc when conditions match.

### 3.2. Spring WebFlux/Reactive

**`spring-boot-starter-webflux`** typically includes Spring WebFlux and Reactor Netty, leading to **`ReactiveWebServerApplicationContext`** and `DispatcherHandler` when the app is `REACTIVE`.

### 3.3. What If Both Starters Are Present?

In **Spring Boot 3.3**, when both MVC and WebFlux are on the classpath, **MVC takes precedence by default**. Many MVC projects include `starter-webflux` solely for outbound `WebClient` calls:

~~~text
starter-web                     -> usually SERVLET/MVC
starter-webflux                 -> usually REACTIVE/WebFlux
starter-web + starter-webflux   -> defaults to SERVLET/MVC
~~~

Never conclude an app runs a WebFlux server just because the POM mentions `WebClient`, `Mono`, or `spring-webflux`.

### 3.4. Forcing the Web Application Type

You can configure explicitly:

~~~yaml
spring:
  main:
    web-application-type: reactive
~~~

or in Java:

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setWebApplicationType(WebApplicationType.REACTIVE);
app.run(args);
~~~

This snippet requires `MyApplication` and imports. Forcing `REACTIVE` when both starters are on the classpath requires **re-testing mappings, web server, security, HTTP codecs, and blocking dependencies**. Never use it as a blind fix for `@EnableWebFlux` issues.

### 3.5. Three Completely Separate Things

- Having the **WebFlux dependency**: classes and APIs sit on the classpath.
- Selecting **`WebApplicationType.REACTIVE`**: Boot creates a reactive web context.
- Adding **`@EnableWebFlux`**: imports Spring Framework's WebFlux configuration into the context, causing Boot's `WebFluxAutoConfiguration` to back off.

**`@EnableWebMvc` is not the switch to turn on the MVC server in Spring Boot**; **`@EnableWebFlux` is not the switch to turn Tomcat MVC into Netty WebFlux**.

## 4. `WebMvcAutoConfiguration`: Conditions Affected by `@EnableWebMvc`

### 4.1. Boot 3.3 Javadoc

`WebMvcAutoConfiguration` carries key class-level conditions:

~~~java
@ConditionalOnWebApplication(type = SERVLET)
@ConditionalOnClass({
    jakarta.servlet.Servlet.class,
    org.springframework.web.servlet.DispatcherServlet.class,
    org.springframework.web.servlet.config.annotation.WebMvcConfigurer.class
})
@ConditionalOnMissingBean(
    org.springframework.web.servlet.config.annotation.WebMvcConfigurationSupport.class
)
~~~

This is an **annotation excerpt**, not a standalone Java class. Nested configurations and `@Bean` methods have their own conditions too.

**`@EnableWebMvc`** imports **`DelegatingWebMvcConfiguration`** (a subtype of `WebMvcConfigurationSupport`), so in a Servlet context the **`@ConditionalOnMissingBean(WebMvcConfigurationSupport.class)`** condition on `WebMvcAutoConfiguration` fails to match. A `@Configuration` class that **`extends WebMvcConfigurationSupport`** triggers the same backoff.

**Implementing `WebMvcConfigurer` alone** does not register a `WebMvcConfigurationSupport` replacement bean, so **`WebMvcAutoConfiguration` normally stays active**.

### 4.2. What Can Be Lost When Using `@EnableWebMvc`?

Per Boot 3.3 docs, `WebMvcAutoConfiguration` adds:
- static resource handlers (static files, WebJars);
- static `index.html` welcome page;
- **`ContentNegotiatingViewResolver`**, **`BeanNameViewResolver`**;
- registration of `Converter`/`GenericConverter`/`Formatter` beans;
- `HttpMessageConverters` integration;
- `MessageCodesResolver`, `ConfigurableWebBindingInitializer`;
- other Boot resource/formatting properties and customizations depending on version.

After adding `@EnableWebMvc`, **core MVC infrastructure still gets created**, so a `@RestController` may still return 200 JSON. However, **Boot-specific conveniences are no longer provided automatically**. A clear symptom is **`GET /marker.txt`** from **`src/main/resources/static`** switching from 200 to 404 unless the app configures resource handlers itself.

**Do not conclude `@EnableWebMvc` turns off all of Spring Boot**: embedded server, Actuator, Jackson, and Spring Security still have their own auto-configurations.

### 4.3. Right-Sized Customization

To add interceptors, CORS, formatters, converters, view controllers, or resource handlers, prefer:

~~~java
@Configuration(proxyBeanMethods = false)
public class WebConfig implements WebMvcConfigurer {
    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        // Register application-specific interceptors.
    }
}
~~~

This snippet needs imports. **Do not add `@EnableWebMvc`** if you want to keep Boot defaults. When changing static paths or content negotiation exposed via Boot properties, prefer properties first.

### 4.4. `WebMvcRegistrations`

When you need to customize **`RequestMappingHandlerMapping`, `RequestMappingHandlerAdapter`, or `ExceptionHandlerExceptionResolver`** while preserving Boot's MVC customizations, use **`WebMvcRegistrations`**. This is a deeper extension point than `WebMvcConfigurer`. Custom instances still participate in Spring MVC setup, so test ordering, argument resolvers, interceptors, exception handling, and security.

### 4.5. When Should `@EnableWebMvc` Actually Be Used?

When you **intentionally take over full MVC web configuration** and have tests proving all features previously added by Boot are reconfigured or no longer needed. Never add the annotation thinking it is required to register controllers in Spring Boot.

## 5. `WebFluxAutoConfiguration` and `@EnableWebFlux`

### 5.1. Nature of the Conditions

In Spring Boot 3.3, **`WebFluxAutoConfiguration`** targets **`REACTIVE`** web applications and checks **`WebFluxConfigurationSupport`**. **`@EnableWebFlux`** imports **`DelegatingWebFluxConfiguration`**, a subclass of `WebFluxConfigurationSupport`, causing `WebFluxAutoConfiguration`'s `MissingBean` condition to stop matching.

Two **different** reasons can make `WebFluxAutoConfiguration` negative:
- the app is not a reactive web application (e.g., both web and webflux starters present so Boot picked MVC);
- the app is reactive, yet `WebFluxConfigurationSupport` already exists via `@EnableWebFlux`.

**Always inspect `OnWebApplicationCondition` and `OnBeanCondition` to tell which happened**.

### 5.2. Boot WebFlux Defaults That Can Be Lost

Boot adds on top of Spring WebFlux defaults:
- `HttpMessageReader`/`HttpMessageWriter` codec configuration;
- static resources, WebJars, and welcome page integration;
- formatters, `CodecCustomizer`, WebFlux properties;
- error-handling and resource customizations per Boot auto-configuration.

When `@EnableWebFlux` causes `WebFluxAutoConfiguration` to back off, WebFlux core still runs **`DispatcherHandler` and `@RestController`**, yet Boot's resource/codec customizations can vanish. Test JSON, static files, CORS, errors, content types, and security rather than just checking startup.

### 5.3. Using `WebFluxConfigurer`

~~~java
@Configuration(proxyBeanMethods = false)
public class ReactiveWebConfig implements WebFluxConfigurer {
    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://docs.example.test")
                .allowedMethods("GET");
    }
}
~~~

This is a snippet; full files appear in the WebFlux project. **Do not add `@EnableWebFlux`** just to configure CORS or formatters. To customize codecs, check **`configureHttpMessageCodecs`** or **`CodecCustomizer`**; to customize the `HttpHandler` builder, Boot provides **`WebHttpHandlerBuilderCustomizer`**. Never use reactive handlers to hide blocking JDBC on the Netty event loop.

### 5.4. Related Security Stack

MVC Servlet uses **`SecurityFilterChain`** and Servlet `Filter`s, while reactive WebFlux uses **`SecurityWebFilterChain`** and `WebFilter`s. Changing web application type affects authentication, authorization, CSRF, and Actuator. `@EnableWebMvc`/`@EnableWebFlux` do not convert security rules. After every migration, test protected routes and CORS preflights.

## 6. Reading the Conditions Evaluation Report Properly

### 6.1. Printing the Report at Startup

~~~bash
java -jar target/application.jar --debug
~~~

`target/application.jar` is an example path. Spring Boot prints the **CONDITIONS EVALUATION REPORT** on startup, showing **Positive matches**, **Negative matches**, exclusions, and unconditional classes depending on version.

Look for:
- `WebMvcAutoConfiguration` or `WebFluxAutoConfiguration`;
- `DispatcherServletAutoConfiguration`;
- `ServletWebServerFactoryAutoConfiguration` / `ReactiveWebServerFactoryAutoConfiguration`;
- `JacksonAutoConfiguration` / `HttpMessageConvertersAutoConfiguration`;
- `ErrorMvcAutoConfiguration` / `ErrorWebFluxAutoConfiguration`.

**A negative match is not automatically a bug.** In a Servlet app, `WebFluxAutoConfiguration` being negative because it is not a reactive web application is completely normal.

### 6.2. Actuator `/actuator/conditions`

In a local lab with `starter-actuator`:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,conditions,beans,mappings"
~~~

Inspect:

~~~bash
curl -i http://localhost:8080/actuator/conditions
curl -i http://localhost:8080/actuator/beans
curl -i http://localhost:8080/actuator/mappings
~~~

Spring Boot 3.3's `conditions` endpoint returns sections like:

~~~json
{
  "contexts": {
    "application": {
      "positiveMatches": {},
      "negativeMatches": {},
      "unconditionalClasses": []
    }
  }
}
~~~

**The JSON above illustrates only the shape**; real reports key by configuration class/method with condition messages, and may include nested contexts/`parentId`.

**Security:** `conditions`, `beans`, and `mappings` reveal class names, bean names, routes, and internal configuration. Expose them only in labs or authenticated management networks; never expose them publicly in production just to debug.

### 6.3. Interpreting a Negative Match

~~~text
WebMvcAutoConfiguration:
  OnBeanCondition for @ConditionalOnMissingBean
  WebMvcConfigurationSupport was not met
  because DelegatingWebMvcConfiguration is already defined.
~~~

This is an **illustrative message**, not fixed literal output. It tells you user/app config already registered MVC infrastructure, so Boot skipped its MVC auto-configuration. Search for `@EnableWebMvc` or a class extending `WebMvcConfigurationSupport`.

### 6.4. A Positive Match Does Not Guarantee Every Bean Was Created

A class-level positive match does not mean every `@Bean` method inside it matched. Check method-level outcomes, bean inventory, and real HTTP behavior. Mappings can disappear due to `@Profile`, component scan boundaries, type mismatches, security, route conflicts, or resource paths—not just `@Enable*`.

### 6.5. Programmatic Inspection in Tests

Boot's **`ConditionEvaluationReport.get(context.getBeanFactory())`** lets you inspect **`getConditionAndOutcomesBySource()`**. Outcomes expose **`isFullMatch()`** to check whether a source passed all conditions. This turns hypotheses like "Bean A caused condition B to back off" into automated regression tests.

## 7. Change-and-Symptom Matrix

| Action | Typical outcome | Key evidence |
| --- | --- | --- |
| Add `@Bean` matching interface with `MissingBean` | Default `@Bean` method backs off | `OnBeanCondition` and bean count. |
| Add `@Bean` sharing name with non-conditional default | Possible name conflict | `BeanDefinitionOverrideException`. |
| Two beans of same type without qualifier | Injection ambiguity | `NoUniqueBeanDefinitionException`. |
| Add `WebMvcConfigurer` | Boot MVC auto-config stays active | Static resources/mappings/interceptors. |
| Add `@EnableWebMvc` | `WebMvcAutoConfiguration` backs off | `WebMvcConfigurationSupport` bean. |
| Extend `WebMvcConfigurationSupport` | Triggers similar backoff | `OnBeanCondition`. |
| Add `WebFluxConfigurer` | Boot WebFlux auto-config stays active | Codecs/static/CORS. |
| Add `@EnableWebFlux` | `WebFluxAutoConfiguration` backs off in `REACTIVE` app | `WebFluxConfigurationSupport` bean. |
| Add `starter-webflux` to MVC | Boot still defaults to `SERVLET`/MVC | Context type and `DispatcherServlet`. |
| Force `web-application-type=reactive` | Reactive context selected | `DispatcherHandler`/Netty/security stack. |
| Exclude auto-config class | Whole class intentionally skipped | Exclusions/report. |
| Upgrade Boot version | Conditions/APIs/defaults may shift | Diff report, dependency tree, HTTP tests. |

## 8. MVC Project: Conditional User Bean and `@EnableWebMvc`

Project A demonstrates two **independent** backoffs:
1. **`GreetingService`** user bean causes the default bean in custom `GreetingAutoConfiguration` to back off.
2. **`@EnableWebMvc`** causes `WebMvcAutoConfiguration` to back off, dropping Boot's default static resource mapping. **`WebMvcConfigurer` without `@Enable`** preserves Boot defaults.

### 8.1. Project Tree

~~~text
mvc-conditions-lab/
  pom.xml
  src/main/java/com/example/mvcconditions/
    MvcConditionsApplication.java
    GreetingService.java
    GreetingController.java
    CustomGreetingConfiguration.java
    MvcExtensionConfiguration.java
    ManualMvcConfiguration.java
  src/main/java/com/example/mvcconditions/autoconfig/
    GreetingAutoConfiguration.java
  src/main/resources/
    application.yml
    static/marker.txt
    META-INF/spring/
      org.springframework.boot.autoconfigure.AutoConfiguration.imports
  src/test/java/com/example/mvcconditions/
    MvcDefaultHttpTest.java
    MvcCustomHttpTest.java
    MvcManualHttpTest.java
~~~

### 8.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>mvc-conditions-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
            <artifactId>spring-boot-starter-actuator</artifactId>
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
~~~

### 8.3. `MvcConditionsApplication.java`

~~~java
package com.example.mvcconditions;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcConditionsApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcConditionsApplication.class, args);
    }
}
~~~

### 8.4. `GreetingService.java`

~~~java
package com.example.mvcconditions;

@FunctionalInterface
public interface GreetingService {
    String greet(String name);
}
~~~

### 8.5. `GreetingAutoConfiguration.java`

~~~java
package com.example.mvcconditions.autoconfig;

import com.example.mvcconditions.GreetingService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    public GreetingService defaultGreetingService() {
        return name -> "default:" + name;
    }
}
~~~

**Important:** register the auto-configuration in the exact file:

**`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`**

~~~text
com.example.mvcconditions.autoconfig.GreetingAutoConfiguration
~~~

If this file is missing or wrong, the user app receives no default `GreetingService` and injection can fail. The fully qualified class name must match. In Boot 3.3, do not use the legacy `spring.factories` registration for this auto-configuration.

### 8.6. `CustomGreetingConfiguration.java`

~~~java
package com.example.mvcconditions;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
@Profile("custom")
public class CustomGreetingConfiguration {

    @Bean
    public GreetingService greetingService() {
        return name -> "custom:" + name;
    }
}
~~~

The user bean returns `GreetingService` with a different bean name from the default. When profile `custom` is active, `defaultGreetingService` is skipped because of `@ConditionalOnMissingBean`. MVC auto-configuration is unaffected by this type.

### 8.7. `GreetingController.java`

~~~java
package com.example.mvcconditions;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    private final GreetingService service;

    public GreetingController(GreetingService service) {
        this.service = service;
    }

    @GetMapping("/api/greet")
    public Map<String, String> greet(
            @RequestParam(defaultValue = "Lan") String name) {
        return Map.of("value", service.greet(name));
    }
}
~~~

### 8.8. `MvcExtensionConfiguration.java`

~~~java
package com.example.mvcconditions;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
@Profile("mvc-configurer")
public class MvcExtensionConfiguration implements WebMvcConfigurer {

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new HandlerInterceptor() {
            @Override
            public boolean preHandle(
                    HttpServletRequest request,
                    HttpServletResponse response,
                    Object handler) {
                response.addHeader("X-Demo-Configurer", "active");
                return true;
            }
        }).addPathPatterns("/api/**");
    }
}
~~~

This is an **extension**, with no `@EnableWebMvc`. It adds an interceptor header for API routes while Boot static resources keep working automatically.

### 8.9. `ManualMvcConfiguration.java`

~~~java
package com.example.mvcconditions;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
@Profile("mvc-manual")
@EnableWebMvc
public class ManualMvcConfiguration implements WebMvcConfigurer {
    // Intentionally omit static resource handler registration in this mode.
}
~~~

When profile `mvc-manual` is active, `@EnableWebMvc` imports `DelegatingWebMvcConfiguration`; Boot's `WebMvcAutoConfiguration` no longer matches `MissingBean(WebMvcConfigurationSupport)`. Controllers still respond, yet `/marker.txt` returns 404 because Boot's static resource mapping is not registered in this demo mode.

### 8.10. `application.yml`

~~~yaml
spring:
  application:
    name: mvc-conditions-lab

server:
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: "health,conditions,beans,mappings"
~~~

### 8.11. `static/marker.txt`

**`src/main/resources/static/marker.txt`**:

~~~text
mvc-static-ok
~~~

### 8.12. Running the Three Profiles

~~~bash
mvn clean package

# Default mode.
java -jar target/mvc-conditions-lab-0.0.1-SNAPSHOT.jar

# Stop the previous process first, then run extension + custom service.
java -jar target/mvc-conditions-lab-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=custom,mvc-configurer

# Stop the previous process first, then run full MVC manual mode.
java -jar target/mvc-conditions-lab-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=mvc-manual --debug
~~~

Do not run all three JARs simultaneously on port 8080. Call:

~~~bash
curl -i "http://localhost:8080/api/greet?name=Lan"
curl -i http://localhost:8080/marker.txt
curl -i http://localhost:8080/actuator/conditions
~~~

| Mode | `/api/greet` | `/marker.txt` | Condition |
| --- | --- | --- | --- |
| default | `{"value":"default:Lan"}`, HTTP 200 | 200, `mvc-static-ok` | `WebMvcAutoConfiguration` positive |
| `custom,mvc-configurer` | `{"value":"custom:Lan"}`, header `X-Demo-Configurer: active` | 200 | Default `GreetingService` bean backs off; MVC positive |
| `mvc-manual` | Controller HTTP 200 | 404 | `WebMvcAutoConfiguration` negative due to `WebMvcConfigurationSupport` |

These are **expectations** for the learner to run and verify, not stdout captured on a live machine.

## 9. HTTP Integration Tests for MVC

### 9.1. `MvcDefaultHttpTest.java`

~~~java
package com.example.mvcconditions;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.web.servlet.WebMvcAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.context.ConfigurableApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class MvcDefaultHttpTest {

    @Autowired
    TestRestTemplate http;

    @Autowired
    ConfigurableApplicationContext context;

    @Test
    void defaultBeanAndStaticFileWork() {
        var api = http.getForEntity(
                "/api/greet?name=Lan", String.class);
        var file = http.getForEntity(
                "/marker.txt", String.class);

        assertThat(api.getStatusCode().value()).isEqualTo(200);
        assertThat(api.getBody()).contains("default:Lan");
        assertThat(file.getStatusCode().value()).isEqualTo(200);
        assertThat(file.getBody()).contains("mvc-static-ok");
    }

    @Test
    void bootMvcAutoConfigMatches() {
        var report = ConditionEvaluationReport.get(
                context.getBeanFactory());
        var outcomes = report.getConditionAndOutcomesBySource()
                .get(WebMvcAutoConfiguration.class.getName());

        assertThat(outcomes).isNotNull();
        assertThat(outcomes.isFullMatch()).isTrue();
    }
}
~~~

### 9.2. `MvcCustomHttpTest.java`

~~~java
package com.example.mvcconditions;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.test.context.ActiveProfiles;

import com.example.mvcconditions.autoconfig.GreetingAutoConfiguration;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles({"custom", "mvc-configurer"})
class MvcCustomHttpTest {

    @Autowired
    TestRestTemplate http;

    @Autowired
    ConfigurableApplicationContext context;

    @Test
    void userBeanBacksOffButBootStaticResourcesRemain() {
        var api = http.getForEntity(
                "/api/greet?name=Lan", String.class);
        var file = http.getForEntity(
                "/marker.txt", String.class);

        assertThat(api.getStatusCode().value()).isEqualTo(200);
        assertThat(api.getBody()).contains("custom:Lan");
        assertThat(api.getHeaders()
                .getFirst("X-Demo-Configurer"))
                .isEqualTo("active");
        assertThat(file.getStatusCode().value()).isEqualTo(200);
    }

    @Test
    void customAutoConfigBeanMethodDoesNotMatch() {
        String source = GreetingAutoConfiguration.class.getName()
                + "#defaultGreetingService";
        var outcomes = ConditionEvaluationReport.get(
                context.getBeanFactory())
            .getConditionAndOutcomesBySource().get(source);

        assertThat(outcomes).isNotNull();
        assertThat(outcomes.isFullMatch()).isFalse();
    }
}
~~~

Depending on the Boot version, method key formatting in the report may vary; in Boot 3.3, the source name is normally `ClassName#methodName`. This test separates **bean-level backoff** from disabling all web auto-config.

### 9.3. `MvcManualHttpTest.java`

~~~java
package com.example.mvcconditions;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.web.servlet.WebMvcAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("mvc-manual")
class MvcManualHttpTest {

    @Autowired
    TestRestTemplate http;

    @Autowired
    ConfigurableApplicationContext context;

    @Test
    void frameworkMvcWorksButBootStaticMappingIsAbsent() {
        var api = http.getForEntity(
                "/api/greet?name=Lan", String.class);
        var file = http.getForEntity(
                "/marker.txt", String.class);

        assertThat(api.getStatusCode().value()).isEqualTo(200);
        assertThat(file.getStatusCode().value()).isEqualTo(404);
    }

    @Test
    void webMvcAutoConfigBacksOff() {
        var outcomes = ConditionEvaluationReport.get(
                context.getBeanFactory())
            .getConditionAndOutcomesBySource()
            .get(WebMvcAutoConfiguration.class.getName());

        assertThat(outcomes).isNotNull();
        assertThat(outcomes.isFullMatch()).isFalse();
    }
}
~~~

`RANDOM_PORT` runs Tomcat over real HTTP rather than `MockMvc`. Different profiles create distinct contexts; never alter active profiles after startup. Run:

~~~bash
mvn test
~~~

## 10. Separate WebFlux Project to Verify `@EnableWebFlux`

### 10.1. Why Separate the Projects?

If `starter-web` is accidentally included in a WebFlux project, Boot defaults to MVC and the "not a reactive web application" condition masks `@EnableWebFlux` behavior. Project B has **only `starter-webflux`** and a reactive controller. Three modes:
- default: Boot WebFlux auto-config serves `/marker.txt`.
- `flux-configurer`: CORS extension without `@EnableWebFlux`; static resources still work.
- `flux-manual`: `@EnableWebFlux`, Boot `WebFluxAutoConfiguration` backs off, controller still works yet `/marker.txt` returns 404 without manual resource handler registration.

### 10.2. Project Tree

~~~text
webflux-conditions-lab/
  pom.xml
  src/main/java/com/example/fluxconditions/
    FluxConditionsApplication.java
    FluxGreetingController.java
    FluxExtensionConfiguration.java
    ManualFluxConfiguration.java
  src/main/resources/
    application.yml
    static/marker.txt
  src/test/java/com/example/fluxconditions/
    FluxDefaultHttpTest.java
    FluxConfigurerHttpTest.java
    FluxManualHttpTest.java
~~~

### 10.3. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>webflux-conditions-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
            <artifactId>spring-boot-starter-actuator</artifactId>
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
~~~

### 10.4. `FluxConditionsApplication.java`

~~~java
package com.example.fluxconditions;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FluxConditionsApplication {
    public static void main(String[] args) {
        SpringApplication.run(FluxConditionsApplication.class, args);
    }
}
~~~

### 10.5. `FluxGreetingController.java`

~~~java
package com.example.fluxconditions;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class FluxGreetingController {

    @GetMapping("/api/greet")
    public Mono<Map<String, String>> greet(
            @RequestParam(defaultValue = "Lan") String name) {
        return Mono.just(
                Map.of("value", "reactive:" + name));
    }
}
~~~

`Mono.just` illustrates the reactive stack only, not a WebFlux or non-blocking DB I/O benchmark.

### 10.6. `FluxExtensionConfiguration.java`

~~~java
package com.example.fluxconditions;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.web.reactive.config.CorsRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration(proxyBeanMethods = false)
@Profile("flux-configurer")
public class FluxExtensionConfiguration implements WebFluxConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://docs.example.test")
                .allowedMethods("GET");
    }
}
~~~

### 10.7. `ManualFluxConfiguration.java`

~~~java
package com.example.fluxconditions;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.web.reactive.config.EnableWebFlux;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration(proxyBeanMethods = false)
@Profile("flux-manual")
@EnableWebFlux
public class ManualFluxConfiguration implements WebFluxConfigurer {
    // No addResourceHandlers: intentionally drop Boot static defaults.
}
~~~

### 10.8. `application.yml`, `marker.txt`

~~~yaml
spring:
  application:
    name: webflux-conditions-lab
server:
  port: 8080
management:
  endpoints:
    web:
      exposure:
        include: "health,conditions,beans,mappings"
~~~

**`src/main/resources/static/marker.txt`**:

~~~text
flux-static-ok
~~~

### 10.9. Running the Three Modes

~~~bash
mvn clean package

# Default reactive mode.
java -jar target/webflux-conditions-lab-0.0.1-SNAPSHOT.jar

# Stop the previous process first, then run flux-configurer.
java -jar target/webflux-conditions-lab-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=flux-configurer

# Stop the previous process first, then run manual mode.
java -jar target/webflux-conditions-lab-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=flux-manual --debug
~~~

Do not run both MVC and WebFlux JARs on port 8080 simultaneously. Call:

~~~bash
curl -i http://localhost:8080/api/greet
curl -i http://localhost:8080/marker.txt
curl -i -H "Origin: https://docs.example.test" \
  http://localhost:8080/api/greet
curl -i http://localhost:8080/actuator/conditions
~~~

Expected:
- Default: `/api/greet` returns `{"value":"reactive:Lan"}`, `/marker.txt` 200, Boot `WebFluxAutoConfiguration` positive.
- `flux-configurer`: CORS `Access-Control-Allow-Origin` for the allowed `Origin`, static marker remains 200.
- `flux-manual`: `/api/greet` 200, static marker 404; `WebFluxAutoConfiguration` negative due to `WebFluxConfigurationSupport`.

Requests without an `Origin` header do not require CORS response headers. To test CORS, send a valid `Origin` as shown.

## 11. HTTP Integration Tests for WebFlux

Use **JDK 17's `java.net.http.HttpClient`** to avoid relying on test client bean auto-configuration. `@SpringBootTest(RANDOM_PORT)` still starts a real Reactor Netty HTTP server. Conditions are checked via `ConditionEvaluationReport` just like the MVC project.

### 11.1. `FluxDefaultHttpTest.java`

~~~java
package com.example.fluxconditions;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.web.reactive.WebFluxAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.ConfigurableApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class FluxDefaultHttpTest {

    @LocalServerPort
    int port;

    @Autowired
    ConfigurableApplicationContext context;

    private HttpResponse<String> get(String path) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                URI.create("http://localhost:" + port + path))
                .GET().build();
        return HttpClient.newHttpClient().send(
                request, HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void bootReactiveConfigServesJsonAndStatic() throws Exception {
        var api = get("/api/greet");
        var marker = get("/marker.txt");

        assertThat(api.statusCode()).isEqualTo(200);
        assertThat(api.body()).contains("reactive:Lan");
        assertThat(marker.statusCode()).isEqualTo(200);
        assertThat(marker.body()).contains("flux-static-ok");
    }

    @Test
    void webFluxAutoConfigurationMatches() {
        var outcomes = ConditionEvaluationReport.get(
                context.getBeanFactory())
            .getConditionAndOutcomesBySource()
            .get(WebFluxAutoConfiguration.class.getName());

        assertThat(outcomes).isNotNull();
        assertThat(outcomes.isFullMatch()).isTrue();
    }
}
~~~

### 11.2. `FluxConfigurerHttpTest.java`

~~~java
package com.example.fluxconditions;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("flux-configurer")
class FluxConfigurerHttpTest {

    @LocalServerPort
    int port;

    @Test
    void corsExtensionKeepsStaticResources() throws Exception {
        HttpClient client = HttpClient.newHttpClient();

        var originRequest = HttpRequest.newBuilder(
                URI.create("http://localhost:" + port + "/api/greet"))
                .header("Origin", "https://docs.example.test")
                .GET().build();

        var api = client.send(
                originRequest,
                HttpResponse.BodyHandlers.ofString());

        var marker = client.send(
            HttpRequest.newBuilder(
                URI.create("http://localhost:" + port + "/marker.txt"))
                .GET().build(),
            HttpResponse.BodyHandlers.ofString());

        assertThat(api.statusCode()).isEqualTo(200);
        assertThat(api.headers()
                .firstValue("Access-Control-Allow-Origin"))
                .contains("https://docs.example.test");
        assertThat(marker.statusCode()).isEqualTo(200);
    }
}
~~~

### 11.3. `FluxManualHttpTest.java`

~~~java
package com.example.fluxconditions;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.web.reactive.WebFluxAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("flux-manual")
class FluxManualHttpTest {

    @LocalServerPort
    int port;

    @Autowired
    ConfigurableApplicationContext context;

    private int status(String path) throws Exception {
        var request = HttpRequest.newBuilder(
                URI.create("http://localhost:" + port + path))
                .GET().build();
        var response = HttpClient.newHttpClient().send(
                request, HttpResponse.BodyHandlers.discarding());
        return response.statusCode();
    }

    @Test
    void manualModeWorksButBootStaticMappingIsAbsent()
            throws Exception {
        assertThat(status("/api/greet")).isEqualTo(200);
        assertThat(status("/marker.txt")).isEqualTo(404);
    }

    @Test
    void webFluxAutoConfigurationBacksOff() {
        var outcomes = ConditionEvaluationReport.get(
                context.getBeanFactory())
            .getConditionAndOutcomesBySource()
            .get(WebFluxAutoConfiguration.class.getName());

        assertThat(outcomes).isNotNull();
        assertThat(outcomes.isFullMatch()).isFalse();
    }
}
~~~

Run:

~~~bash
mvn test
~~~

**The two Spring Boot projects have independent POMs**, so MVC and WebFlux tests validate two separate web stacks without guessing from a mixed classpath. Assertions reflect Spring Boot 3.3 conditions; when upgrading, inspect the report and run real tests.

## 12. Other Caveats When Adding `@Bean`s

### 12.1. Return Type of `@Bean`

If a condition inspects an interface while a `@Bean` method declares return type **`Object`**, Spring may fail to recognize the concrete type during condition evaluation:

~~~java
@Bean
Object myService() {
    return new MyServiceImpl();
}
~~~

This is a snippet since `MyServiceImpl` is undefined. Declare the return type matching the contract:

~~~java
@Bean
MyService myService() {
    return new MyServiceImpl();
}
~~~

Conditions do not always instantiate every bean eagerly to check runtime classes; metadata and bean definitions matter.

### 12.2. Limitations of `@Primary`/`@Qualifier`

`@Primary` picks a preferred candidate for injection without removing other beans from the context. `@Qualifier` selects a specific bean. If an auto-config uses `@ConditionalOnSingleCandidate`, `@Primary` can affect the outcome; inspect the condition/report for **that exact class**.

### 12.3. Adding `SecurityFilterChain`

In an MVC Servlet app, adding a custom **`SecurityFilterChain`** can cause the default security chain to back off. That customization carries authorization/CSRF risk if rules are incomplete. For reactive apps, check **`SecurityWebFilterChain`**. Never assume authentication stays intact after adding custom MVC web config; test route and Actuator access.

### 12.4. `MessageConverter`s, Codecs, and Error Handling

Adding an `HttpMessageConverter` or `CodecCustomizer` can alter `Accept`/`Content-Type` behavior, causing **406/415**, different JSON output, or custom error bodies. An `ErrorAttributes` or `ErrorWebExceptionHandler` bean can alter error representations. To debug, read the condition report for the relevant auto-configurations and run HTTP tests instead of blaming `@EnableWebMvc` for everything.

### 12.5. Do Not Replace Auto-Config with Broad Exclusions

~~~java
@SpringBootApplication(
    exclude = SomeAutoConfiguration.class)
~~~

This is an illustrative snippet; **`SomeAutoConfiguration`** is undefined. Exclusions may be warranted in special architectures, yet they drop **the entire class**; identify which beans/features you must replace. Never exclude an auto-config simply because a normal negative match appeared.

## 13. Repeatable Debugging and Upgrade Workflow

### Step 1 — Capture a Baseline

Record Java version, Spring Boot/Framework versions, active profiles, properties, dependency tree, and Servlet vs. Reactive context type. Run the current app and save requests/responses for:
- a JSON endpoint;
- a classpath static file;
- CORS preflight;
- validation and error handling;
- a security-protected endpoint;
- `/actuator/health`.

### Step 2 — Make Exactly One Change

Add only the custom `@Bean`, only `WebMvcConfigurer`, or only `@EnableWebMvc`/`@EnableWebFlux`. Changing dependencies, upgrading Boot, adding beans, and modifying security all at once obscures root cause.

### Step 3 — Diff the Condition Report

Find entries that flipped positive → negative or `@Bean` methods that backed off. Identify the exact reason:
- `OnClassCondition`;
- `OnWebApplicationCondition`;
- `OnBeanCondition`;
- `OnPropertyCondition`;
- explicitly excluded auto-configuration.

If a negative match says "not a reactive web application," do not try to fix it with `@EnableWebFlux`; check web application type and starters first.

### Step 4 — Compare Beans and Mappings

Inspect bean types/names/aliases, handler mappings, resource handlers, Jackson/codecs, filters, and error mappings. **`/actuator/beans` and `/actuator/mappings` must be secured**. A class-level condition match does not guarantee method-level beans were created.

### Step 5 — Run HTTP Regression Tests

Test with `RANDOM_PORT`, `WebTestClient` where appropriate, plus check:
- HTTP 200/400/404/405/406/415;
- static resources and index pages;
- `Accept`/`Content-Type` negotiation;
- CORS `Origin` and `OPTIONS`;
- security/login/CSRF/Actuator;
- formatter/date/time conversions;
- error JSON and validation;
- reactive streaming if the stack is WebFlux.

### Step 6 — Apply the Smallest Fix and Lock In Regressions

Usually remove `@EnableWebMvc`/`@EnableWebFlux` if full takeover isn't needed, use `WebMvcConfigurer`/`WebFluxConfigurer` or properties, fix `@Bean` return types, qualifiers/conditions, or use dedicated extension points. Add tests proving the root cause is resolved. For framework upgrades, read release notes and migration guides for the target version.

## 14. Troubleshooting

| Symptom | Likely cause | Action |
| --- | --- | --- |
| Static `/css/app.css` 404 after `@EnableWebMvc` | Boot MVC static auto-mapping gone | `WebMvcAutoConfiguration` negative; switch to `WebMvcConfigurer`. |
| `/marker.txt` 404 in WebFlux after `@EnableWebFlux` | Boot reactive resource auto-mapping gone | `WebFluxAutoConfiguration` negative; use `WebFluxConfigurer`. |
| MVC still works despite `@EnableWebMvc` | Spring Framework MVC infrastructure still runs | Separate core MVC from Boot additions. |
| Custom bean doesn't replace default | Wrong type/profile or registration order | Check `OnBeanCondition`, method return type, and active profiles. |
| Duplicate bean name causes startup failure | `BeanDefinitionOverrideException` | Rename or make conditional instead of enabling overriding blindly. |
| Two beans of same interface cause ambiguity | `NoUniqueBeanDefinitionException` | Add `@Qualifier`/`@Primary` or fix conditions. |
| `WebFluxAutoConfiguration` not reactive | Boot selected `SERVLET` | Check dependency tree and web application type. |
| Added `starter-webflux` yet still Tomcat | MVC precedence | Use only `WebClient` or split reactive project. |
| `@EnableWebFlux` doesn't switch server | Annotation controls framework web config, not Boot web type | Check context type and stack choice. |
| CORS `OPTIONS` fails | Wrong stack configurer or Security intercept | Check CORS registry, filter chain, preflight. |
| Error JSON or converters changed | Backoff/codec/custom converter | Check conditions, mappings, `Accept`/`Content-Type`. |
| `/actuator/conditions` 404 | Actuator missing or not exposed | Check `starter-actuator` and exposure include. |
| `/actuator/conditions` 401/403 | Endpoint is secured | Use proper credentials; never make public. |
| `--debug` shows many negative matches | Normal when features aren't needed | Read the reason on each entry. |
| `AutoConfiguration.imports` not picked up | Wrong path/name/class | Inspect resources inside JAR. |
| Static works in tests yet fails in JAR | Resource file packaging/location | Inspect JAR contents and classpath. |
| Tests fail order-dependently with profiles | Shared context/mutable state or profile leak | Isolate contexts, disable parallel run if needed. |
| Boot upgrade causes drift | Conditions/properties/defaults changed across versions | Diff report and HTTP contract. |

## 15. Hands-On Exercises

### Exercise 1 — User Bean Backoff
Run the MVC project in default and `custom` profiles. Compare `/actuator/conditions` for `GreetingAutoConfiguration#defaultGreetingService`; explain why the default method is negative while `WebMvcAutoConfiguration` stays positive.

### Exercise 2 — Extending MVC While Keeping Boot Defaults
Enable `mvc-configurer`, verify header `X-Demo-Configurer` and `/marker.txt` HTTP 200. Add a formatter or CORS mapping without `@EnableWebMvc`.

### Exercise 3 — MVC Takeover
Enable `mvc-manual`, observe `/api/greet` 200 and `/marker.txt` 404. Locate `WebMvcConfigurationSupport` in the condition message. Remove `@EnableWebMvc` and re-run.

### Exercise 4 — WebFlux CORS
Enable `flux-configurer`; send an `Origin` header and check `Access-Control-Allow-Origin`; static marker remains 200. Compare conditions.

### Exercise 5 — WebFlux Takeover
Enable `flux-manual`; confirm the controller works while static mapping vanishes. If full control is desired, register a resource handler manually and note what else Boot no longer provides automatically.

### Exercise 6 — Two Starters
Add `starter-webflux` to an MVC app solely for `WebClient`; verify it remains `SERVLET`. Explain why `@EnableWebFlux` does not convert the whole service to reactive.

### Exercise 7 — Duplicate Bean
Remove `@ConditionalOnMissingBean` from the demo auto-config in a lab copy and enable profile `custom`. Observe the injection ambiguity error. Then test duplicate bean names and distinguish the two failures.

### Exercise 8 — Upgrade
Upgrade a Spring Boot version in an authorized environment, diff `ConditionEvaluationReport`, bean lists, and HTTP responses. Build a table: `condition → bean/mapping → runtime effect → fix`.

## 16. Pre-Merge Checklist

- [ ] Accurately identified Servlet MVC vs. Reactive WebFlux.
- [ ] Captured dependency tree, Java/Boot/Framework versions, and active profiles.
- [ ] Reviewed `--debug` or `ConditionEvaluationReport`.
- [ ] Identified whether unmatched conditions are class-level or method-level.
- [ ] Audited `@EnableWebMvc`, `@EnableWebFlux`, `WebMvcConfigurationSupport`, and `WebFluxConfigurationSupport`.
- [ ] Audited `@Bean` types, names, `@ConditionalOnMissingBean`, `@Primary`, and `@Qualifier`.
- [ ] Did not enable app-wide bean overriding to mask errors.
- [ ] Preferred `WebMvcConfigurer`/`WebFluxConfigurer` when only extending defaults.
- [ ] Verified static resources, `index.html`, and WebJars if used.
- [ ] Tested HTTP conversions, JSON codecs, CORS, and error handling.
- [ ] Verified Security/Actuator access did not change unintentionally.
- [ ] Included HTTP integration tests via `RANDOM_PORT`.
- [ ] Confirmed `/actuator/conditions`, `beans`, and `mappings` are not public on the Internet.
- [ ] Ran regression tests before and after Boot upgrades.
- [ ] Changed one variable at a time when debugging.
- [ ] Prepared a rollback plan for major web-stack/configuration changes.

## 17. Self-Check Questions

**1. Does `@EnableAutoConfiguration` always create every default?** No, each class and method has its own conditions.

**2. Does a user bean turn off all of Spring Boot?** No, usually only the related `MissingBean` target backs off.

**3. Is `WebMvcConfigurer` the same as `@EnableWebMvc`?** No; one extends defaults, the other takes over MVC framework configuration.

**4. Does `@EnableWebMvc` erase Jackson/Actuator/Security completely?** No, those auto-configurations have separate conditions.

**5. Does `@EnableWebFlux` automatically turn an MVC app into a Netty server?** No, Boot's web type is determined separately.

**6. With both starters in Boot 3.3, which does Boot pick by default?** MVC/Servlet.

**7. Does `@ConditionalOnMissingBean` match by bean name or type?** Depends on annotation attributes; most conditions match by type.

**8. When should `WebMvcRegistrations` be used?** When replacing core MVC components while retaining Boot customizations.

**9. When should `WebHttpHandlerBuilderCustomizer` be used?** When customizing Boot WebFlux's `HttpHandler` builder.

**10. How do you read the condition report?** Startup `--debug`, secured `/actuator/conditions`, or the programmatic API in tests.

**11. Does a positive match guarantee static files will work?** No; verify resource handlers, file locations, security, and real HTTP.

**12. Why do static files return 404 after `@EnableWebMvc`?** Boot's `WebMvcAutoConfiguration` backs off, and core MVC does not automatically replicate Boot's static mappings.

## 18. References

1. [Spring Boot 3.3 — Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html): backoff mechanism and conditions report.
2. [Spring Boot 3.3 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): `WebMvcAutoConfiguration`, `WebMvcConfigurer`, `@EnableWebMvc`, `WebMvcRegistrations`.
3. [Spring Boot 3.3 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html): `WebFluxAutoConfiguration`, `WebFluxConfigurer`, `@EnableWebFlux`, `WebHttpHandlerBuilderCustomizer`, and MVC precedence.
4. [Spring Boot 3.3 — WebMvcAutoConfiguration API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/servlet/WebMvcAutoConfiguration.html): `@ConditionalOnWebApplication`/`@ConditionalOnClass`/`@ConditionalOnMissingBean`.
5. [Spring Boot 3.3 — WebFluxAutoConfiguration API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/reactive/WebFluxAutoConfiguration.html): reactive conditions and `WebFluxConfigurationSupport`.
6. [Spring Boot 3.3 — Conditions Endpoint](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html): `positiveMatches`/`negativeMatches`.
7. [Spring Boot 3.3 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html): exposure and security.
8. [Spring Boot 3.3 — Testing](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): web type, `RANDOM_PORT`.
9. [Spring Framework 6.1 — MVC Config](https://docs.spring.io/spring-framework/reference/6.1/web/webmvc/mvc-config.html): MVC infrastructure and extension points.
10. [Spring Framework 6.1 — WebFlux Config](https://docs.spring.io/spring-framework/reference/6.1/web/webflux/config.html): WebFlux configuration and resource handlers.

**Conclusion:** Whenever adding a user bean or `@EnableWebMvc`/`@EnableWebFlux`, identify the **web application type**, read **`ConditionEvaluationReport`**, pinpoint **which condition stopped matching**, and verify the actual **beans, mappings, and HTTP responses**. A bean of the same type can make a default bean back off, whereas `@EnableWebMvc`/`@EnableWebFlux` takes over web framework configuration and can drop Boot-specific defaults. For typical customization, prefer **`WebMvcConfigurer`/`WebFluxConfigurer` without `@Enable`**, use properties and dedicated extension points, and lock down regressions with HTTP and condition-outcome tests.
