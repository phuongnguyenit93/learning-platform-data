# Tracing the Servlet Conditions of WebMvcAutoConfiguration

## 1. Goal: Understand Why Spring Boot Enables or Skips MVC Auto-Configuration

In a Spring Boot application, you may see beans such as `DispatcherServlet`, `RequestMappingHandlerMapping`, `RequestMappingHandlerAdapter`, message converters, and resource handlers appear without declaring each bean individually. Most of the default Spring MVC infrastructure is configured by:

~~~java
org.springframework.boot.autoconfigure.web.servlet.WebMvcAutoConfiguration
~~~

To understand when this class is applied, trace the conditions placed directly on the class. In Spring Boot 3.3.x, there are three main gates:

1. The application must be a **servlet-based web application**.
2. The runtime classpath must contain the required Servlet API and Spring MVC classes.
3. There must not already be a bean of type `WebMvcConfigurationSupport` so that Spring Boot can yield MVC configuration control to the application.

Class-level conditions are combined with **AND** logic: all of them must match for auto-configuration to be applied. If even one condition does not match, the default MVC configuration of this class will not be registered.

This lesson uses **Spring Boot 3.3.13, Java 17+** as the reference version. If your project runs a different version, first verify the actual version and read the source/Javadoc of that exact release; packages, dependencies, and annotations may change between major versions.

## 2. Finding the Right Class in the Right Artifact

For Spring Boot 3.3.x, the class resides in the package:

~~~text
org.springframework.boot.autoconfigure.web.servlet
~~~

The artifact containing the class is:

~~~text
spring-boot-autoconfigure-3.3.13.jar
~~~

You can verify with Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-autoconfigure
~~~

Then find the class in the JAR:

~~~bash
jar tf path/to/spring-boot-autoconfigure-3.3.13.jar | grep WebMvcAutoConfiguration
~~~

The output should contain the corresponding entry:

~~~text
org/springframework/boot/autoconfigure/web/servlet/WebMvcAutoConfiguration.class
~~~

In Spring Boot 3.x, the list of auto-configurations is published via the resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Read the resource inside the JAR:

~~~bash
unzip -p path/to/spring-boot-autoconfigure-3.3.13.jar META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports | grep WebMvcAutoConfiguration
~~~

The corresponding line is the fully qualified name:

~~~text
org.springframework.boot.autoconfigure.web.servlet.WebMvcAutoConfiguration
~~~

This step confirms that the class is declared as an auto-configuration candidate. Afterward, you still need to read the conditions to know whether the candidate is actually applied in the current application.

**Do not use Spring Boot 4 packages to locate Boot 3 classes.** Boot 4 restructured several modules/packages; for Boot 3.3.x, the fully qualified name remains `org.springframework.boot.autoconfigure.web.servlet.WebMvcAutoConfiguration`.

## 3. Reading the Annotations on WebMvcAutoConfiguration

The most important part of the class in Spring Boot 3.3.x looks like this:

~~~java
@AutoConfiguration(after = {
        DispatcherServletAutoConfiguration.class,
        TaskExecutionAutoConfiguration.class,
        ValidationAutoConfiguration.class
})
@ConditionalOnWebApplication(type = Type.SERVLET)
@ConditionalOnClass({
        Servlet.class,
        DispatcherServlet.class,
        WebMvcConfigurer.class
})
@ConditionalOnMissingBean(WebMvcConfigurationSupport.class)
@AutoConfigureOrder(Ordered.HIGHEST_PRECEDENCE + 10)
public class WebMvcAutoConfiguration {
    // Spring MVC beans and nested configurations.
}
~~~

This is the core declaration simplified for studying conditions; the source of your exact patch version may contain additional imports, runtime hints, or other details.

| Annotation | Meaning | Question to Answer |
| --- | --- | --- |
| `@ConditionalOnWebApplication(type = SERVLET)` | Applies only in a servlet web application | Is the current context a servlet web application? |
| `@ConditionalOnClass(...)` | Applies only when the required classes are on the runtime classpath | Are the Servlet API and Spring MVC present? |
| `@ConditionalOnMissingBean(WebMvcConfigurationSupport.class)` | Backs off if the application already provides low-level MVC infrastructure | Is an alternative MVC configuration already registered? |
| `@AutoConfiguration(after = ...)` | Orders processing time relative to other auto-configurations | Which prerequisite configurations need to be processed before this class? |
| `@AutoConfigureOrder(...)` | Sets general priority in the auto-configuration ordering | What is the general priority order of this candidate? |

The last two annotations are **ordering metadata**, not on/off conditions. Do not interpret `after = DispatcherServletAutoConfiguration.class` as a condition guaranteeing that DispatcherServlet exists; it only declares a processing relationship between auto-configurations.

## 4. First Gate: @ConditionalOnWebApplication(type = SERVLET)

### 4.1. Meaning of SERVLET

Spring Boot supports multiple application types:

- **SERVLET:** a web application based on the Servlet API, typically using Spring MVC.
- **REACTIVE:** a reactive web application, typically using Spring WebFlux.
- **NONE:** an application that does not start a web application context.

`@ConditionalOnWebApplication(type = Type.SERVLET)` matches only when the context/environment is recognized as a **servlet web application**. It does not merely check whether a Servlet API file exists on the classpath.

Conceptually, a servlet web application is recognized through an appropriate web context/environment, such as a Spring `WebApplicationContext`, session scope, or `ConfigurableWebEnvironment`. A Spring Boot application running embedded Tomcat/Jetty/Undertow typically uses `ServletWebServerApplicationContext`.

### 4.2. Distinguishing Application Type from Classpath

Two scenarios can both contain the Servlet API yet produce different results:

| Scenario | Servlet API on classpath? | Context type | SERVLET condition |
| --- | --- | --- | --- |
| Normal Spring MVC web application | Yes | SERVLET | Matches |
| Application with starter-web forced to run non-web | Yes | NONE | Does not match |
| Pure WebFlux application | Usually no Spring MVC DispatcherServlet | REACTIVE | Does not match |

You can force Spring Boot to run non-web with:

~~~properties
spring.main.web-application-type=none
~~~

Or via the command line:

~~~bash
java -jar target/app.jar --spring.main.web-application-type=none
~~~

Even when the `spring-boot-starter-web` dependency remains on the classpath, the SERVLET condition does not match if the application is configured to run as type NONE.

For pure WebFlux, the application type is REACTIVE; `WebMvcAutoConfiguration` is not the configuration intended for that context. Do not confuse this condition with `@ConditionalOnClass`: one condition inspects **context type**, while the other inspects **class presence**.

### 4.3. Where Does Spring Boot Determine WebApplicationType?

At startup, `SpringApplication` deduces the application type from the classpath unless the user explicitly configures `spring.main.web-application-type`. You can inspect the result in code:

~~~java
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.SpringApplication;

SpringApplication application =
        new SpringApplication(MyApplication.class);

System.out.println(application.getWebApplicationType());
~~~

This is an illustrative snippet that can be placed in `main` before calling `run`; `MyApplication.class` is the project's startup class. For a typical MVC web application, the output is:

~~~text
SERVLET
~~~

If the application sets `spring.main.web-application-type=none`, the corresponding output is:

~~~text
NONE
~~~

Do not deduce the application type solely from the starter name. Check the actual configuration and the condition report at runtime.

## 5. Second Gate: @ConditionalOnClass

Declaration in Spring Boot 3.3.x:

~~~java
@ConditionalOnClass({
        jakarta.servlet.Servlet.class,
        org.springframework.web.servlet.DispatcherServlet.class,
        org.springframework.web.servlet.config.annotation.WebMvcConfigurer.class
})
~~~

The three classes serve different roles:

| Class | Library | Why is it needed? |
| --- | --- | --- |
| `jakarta.servlet.Servlet` | Jakarta Servlet API | Provides the foundational API for a servlet web application |
| `org.springframework.web.servlet.DispatcherServlet` | Spring Web MVC | Provides the front controller that handles Spring MVC requests |
| `org.springframework.web.servlet.config.annotation.WebMvcConfigurer` | Spring Web MVC | Provides the callback API to configure MVC |

The condition requires **all three classes** on the runtime classpath. If one class is missing, `WebMvcAutoConfiguration` is not applied.

### 5.1. Starters Typically Provide These Classes

In a typical application, the dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

pulls Spring Web MVC and the matching Servlet API into the dependency graph. The starter also usually provides an embedded servlet container such as Tomcat through its default dependencies.

However, do not draw conclusions solely from the dependency name. Check the runtime dependency tree:

~~~bash
mvn dependency:tree -Dverbose -Dincludes=org.springframework,org.springframework.boot,jakarta.servlet
~~~

If `spring-webmvc` is excluded or has a scope that prevents it from appearing at runtime, `DispatcherServlet` and `WebMvcConfigurer` may be absent from the runtime classpath.

### 5.2. Boot 3 Uses jakarta.servlet, Not javax.servlet

Spring Boot 3 migrated to the Jakarta EE namespace. Therefore, Boot 3's condition references:

~~~java
jakarta.servlet.Servlet.class
~~~

Do not confuse this with the namespace of older Spring Boot 2 applications:

~~~java
javax.servlet.Servlet.class
~~~

An application mixing Spring Boot 2/Spring Framework 5 dependencies with Jakarta Servlet, or Spring Boot 3/Spring Framework 6 with legacy libraries using `javax.servlet`, may encounter compatibility errors. When investigating conditions, verify the major version and the actual packages in the JARs.

### 5.3. Quick Classpath Verification Methods

Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework:spring-webmvc
~~~

Gradle:

~~~bash
./gradlew dependencyInsight --dependency spring-webmvc --configuration runtimeClasspath
~~~

You can inspect the JAR to verify the class:

~~~bash
jar tf path/to/spring-webmvc.jar | grep DispatcherServlet
~~~

For the Servlet API, check the corresponding dependency and the `jakarta/servlet/Servlet.class` class. If a class is missing, fix the dependency/runtime packaging; adding `@EnableWebMvc` cannot compensate for a missing class.

## 6. Third Gate: @ConditionalOnMissingBean(WebMvcConfigurationSupport.class)

This is the condition that implements Spring Boot's **back off** mechanism.

~~~java
@ConditionalOnMissingBean(WebMvcConfigurationSupport.class)
~~~

Meaning: Boot applies the default MVC auto-configuration only if the context does not yet contain a bean of type `WebMvcConfigurationSupport` (or a matching subtype).

### 6.1. Why Does @EnableWebMvc Make Boot Back Off?

Spring Framework provides the annotation:

~~~java
@EnableWebMvc
~~~

This annotation imports Spring Framework's MVC configuration, specifically `DelegatingWebMvcConfiguration`. That class extends `WebMvcConfigurationSupport`.

Therefore, when the application adds `@EnableWebMvc`, a bean of type `WebMvcConfigurationSupport` is registered. The `@ConditionalOnMissingBean(WebMvcConfigurationSupport.class)` condition no longer matches, and `WebMvcAutoConfiguration` backs off.

Result:

- Spring MVC can still work because of the configuration provided by `@EnableWebMvc`.
- Spring Boot's own MVC default customizations may no longer be applied.
- The developer takes responsibility for configuring MVC more completely.

### 6.2. WebMvcConfigurer Does Not Make Boot Back Off

If the goal is only to add an interceptor, formatter, CORS mapping, resource handler, or view controller, you usually only need to declare a `WebMvcConfigurer` bean:

~~~java
@Configuration(proxyBeanMethods = false)
public class MyMvcConfiguration implements WebMvcConfigurer {
    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://frontend.example");
    }
}
~~~

This class has type `WebMvcConfigurer`, not `WebMvcConfigurationSupport`. Therefore, `@ConditionalOnMissingBean(WebMvcConfigurationSupport.class)` still matches; Spring Boot retains its MVC defaults and integrates your callbacks.

**Here is the distinction to remember:**

| User Configuration | Related Bean | Boot MVC auto-configuration |
| --- | --- | --- |
| Only declares `WebMvcConfigurer` | A configurer callback | Still applied |
| Uses `@EnableWebMvc` | `DelegatingWebMvcConfiguration`, subtype of `WebMvcConfigurationSupport` | Backs off |
| Declares a custom `WebMvcConfigurationSupport` subtype | Low-level MVC support bean | Backs off |

Do not use `@EnableWebMvc` just because you want to add an interceptor. Use it when you genuinely want full control over MVC configuration and accept managing the parts Boot normally provides yourself.

### 6.3. If You Need to Replace Core Components While Keeping Boot Customizations

Spring Boot provides `WebMvcRegistrations` to supply custom implementations for certain components such as:

- `RequestMappingHandlerMapping`
- `RequestMappingHandlerAdapter`
- `ExceptionHandlerExceptionResolver`

This approach allows Boot and Spring MVC to continue performing subsequent configuration steps on the replaced component. You can then keep using `WebMvcConfigurer` for extension callbacks. Do not subclass `WebMvcConfigurationSupport` yourself if your goal is only to replace a few components.

## 7. Combining the Three Conditions into One Decision

You can read the class logic as follows:

~~~text
WebMvcAutoConfiguration candidate is discovered
              |
              v
Is it a servlet web application?
@ConditionalOnWebApplication(SERVLET)
        | false -> skip
        | true
        v
Are Servlet + DispatcherServlet + WebMvcConfigurer present?
@ConditionalOnClass(...)
        | false -> skip
        | true
        v
Is a WebMvcConfigurationSupport bean already present?
@ConditionalOnMissingBean(...)
        | present -> back off
        | missing
        v
WebMvcAutoConfiguration is applied
              |
              v
Register nested MVC configurations and matching beans
~~~

This is a logical diagram, not a guarantee of the exact internal execution order of every condition. When Spring Boot processes the class, all class-level conditions must match; if any condition fails to match, this configuration is not applied.

**Do not conflate the three conditions into one:** having the Servlet class on the classpath does not prove the context is a servlet web application; a servlet context does not prove all Spring MVC classes are present; and having all classes does not mean Boot will configure defaults if the user has already replaced the MVC infrastructure.

## 8. After the Three Conditions Match, What Does the Class Do?

In Spring Boot 3.3.x, `WebMvcAutoConfiguration` contains nested configurations, notably:

- `WebMvcAutoConfigurationAdapter`: implements `WebMvcConfigurer`, wiring Boot's MVC customizations.
- `EnableWebMvcConfiguration`: foundational configuration based on Spring Framework's `DelegatingWebMvcConfiguration`.

The nested configurations register `WebMvcProperties` and `WebProperties`, then use them to configure various parts of MVC. Depending on individual bean methods and their own conditions, Boot may provide:

- `ContentNegotiatingViewResolver` and `BeanNameViewResolver`.
- Static resource handling and WebJars.
- Integration of `Converter`, `GenericConverter`, and `Formatter`.
- Message converter configuration.
- `MessageCodesResolver`.
- Static welcome page `index.html` support.
- `ConfigurableWebBindingInitializer`.
- Various filters and MVC components according to their own conditions.

Not all of these beans are registered unconditionally. Individual bean methods may have `@ConditionalOnMissingBean`, `@ConditionalOnBean`, `@ConditionalOnProperty`, or other conditions. Therefore, after class-level conditions match, you still need to inspect bean-method conditions if a specific bean does not appear.

### 8.1. Distinguishing from DispatcherServletAutoConfiguration

Two classes are frequently confused:

| Class | Primary Responsibility |
| --- | --- |
| `DispatcherServletAutoConfiguration` | Registers `DispatcherServlet` and the appropriate registration for a servlet application |
| `WebMvcAutoConfiguration` | Configures Spring MVC infrastructure: mappings, adapters, converters, formatters, resources, and other MVC components |

`WebMvcAutoConfiguration` declares `after = DispatcherServletAutoConfiguration.class` to express relative processing order. This does not mean the first class acts as a mandatory condition replacing `@ConditionalOnWebApplication` or `@ConditionalOnClass`.

## 9. Runnable Example: Default MVC and Custom WebMvcConfigurer

The example uses **Java 17+ and Spring Boot 3.3.13**. The goal is to observe that a normal MVC application still receives Boot's default configuration when only adding a `WebMvcConfigurer`.

### 9.1. Structure

~~~text
webmvc-condition-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/demo/
    │   │   ├── WebMvcTraceApplication.java
    │   │   ├── HelloController.java
    │   │   └── ApiMvcConfiguration.java
    │   └── resources/
    │       └── application.yml
    └── test/
        └── java/com/example/demo/
            ├── WebMvcTraceTests.java
            └── NonWebContextTests.java
~~~

### 9.2. pom.xml

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
    <artifactId>webmvc-condition-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
~~~

### 9.3. WebMvcTraceApplication.java

**src/main/java/com/example/demo/WebMvcTraceApplication.java**

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebMvcTraceApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebMvcTraceApplication.class, args);
    }
}
~~~

### 9.4. HelloController.java

**src/main/java/com/example/demo/HelloController.java**

~~~java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/api/hello")
    public String hello() {
        return "Hello MVC";
    }
}
~~~

### 9.5. ApiMvcConfiguration.java

**src/main/java/com/example/demo/ApiMvcConfiguration.java**

~~~java
package com.example.demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class ApiMvcConfiguration implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://frontend.example");
    }
}
~~~

The class only implements `WebMvcConfigurer`; there is no `@EnableWebMvc` and it does not extend `WebMvcConfigurationSupport`. Therefore, it adds CORS mappings without causing Boot MVC auto-configuration to back off.

### 9.6. application.yml

**src/main/resources/application.yml**

~~~yaml
spring:
  application:
    name: webmvc-condition-demo
~~~

There is no need to set `spring.main.web-application-type`; with starter-web, Spring Boot recognizes this as a normal servlet application.

### 9.7. Running the Application and Enabling the Condition Report

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

Send a request:

~~~bash
curl http://localhost:8080/api/hello
~~~

Response body:

~~~text
Hello MVC
~~~

In the startup log, look for `WebMvcAutoConfiguration` in the Condition Evaluation Report. With this application, all class-level conditions are expected to match:

- The context is a servlet web application.
- `jakarta.servlet.Servlet`, `DispatcherServlet`, and `WebMvcConfigurer` are on the runtime classpath.
- No user-declared `WebMvcConfigurationSupport` bean exists.

Default MVC beans are configured by Boot; `ApiMvcConfiguration` adds CORS.

### 9.8. Test Verifying MVC Infrastructure Registration

**src/test/java/com/example/demo/WebMvcTraceTests.java**

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurationSupport;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class WebMvcTraceTests {

    @Autowired
    ApplicationContext context;

    @Autowired
    MockMvc mockMvc;

    @Test
    void servletMvcInfrastructureIsPresent() {
        assertThat(context.getBeanNamesForType(
                WebMvcConfigurationSupport.class)).isNotEmpty();
    }

    @Test
    void controllerWorksWithBootMvcDefaultsAndCustomConfigurer()
            throws Exception {
        mockMvc.perform(get("/api/hello"))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello MVC"));
    }
}
~~~

Run:

~~~bash
mvn test
~~~

Expect **both tests to pass**. The first test confirms MVC configuration support is present; the second test confirms the endpoint still works when the application has a custom `WebMvcConfigurer`.

## 10. Experiment: Making the SERVLET Condition Not Match

The project's classpath still contains starter-web and MVC classes, but we force the application to run with type NONE.

You can run:

~~~bash
mvn spring-boot:run "-Dspring-boot.run.arguments=--debug --spring.main.web-application-type=none"
~~~

At this point:

- `@ConditionalOnClass` can still match because the dependencies were not removed from the classpath.
- `@ConditionalOnWebApplication(type = SERVLET)` does not match because the application context is configured as non-web.
- `WebMvcAutoConfiguration` is not applied.

This is a good experiment to prove that **having Servlet classes does not equate to a servlet web application**. Controller classes can still be component-scanned as beans, but there is no MVC web context to dispatch HTTP requests.

### Test for Non-Web Context

**src/test/java/com/example/demo/NonWebContextTests.java**

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurationSupport;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = "spring.main.web-application-type=none")
class NonWebContextTests {

    @Autowired
    ApplicationContext context;

    @Test
    void servletMvcAutoConfigurationDoesNotApply() {
        assertThat(context.getBeanNamesForType(
                WebMvcConfigurationSupport.class)).isEmpty();
    }
}
~~~

This test keeps the MVC dependencies unchanged and only alters the application context type. The test is expected to pass because there is no MVC infrastructure bean from auto-configuration.

## 11. Experiment: Making @ConditionalOnMissingBean Not Match

In the project from section 9, modify `ApiMvcConfiguration` to:

~~~java
package com.example.demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
@EnableWebMvc
public class ApiMvcConfiguration implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://frontend.example");
    }
}
~~~

Run again with `--debug`:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

This time:

- The servlet web application condition can still match.
- Servlet/MVC classes are still present.
- `@EnableWebMvc` imports configuration based on `DelegatingWebMvcConfiguration`, a subtype of `WebMvcConfigurationSupport`.
- `@ConditionalOnMissingBean(WebMvcConfigurationSupport.class)` does not match.
- `WebMvcAutoConfiguration` backs off.

In the condition evaluation report, look for `WebMvcAutoConfiguration` under Negative matches. The reason will relate to an existing `WebMvcConfigurationSupport` bean; exact wording depends on the version.

Spring MVC can still function thanks to `@EnableWebMvc`, but Boot MVC customizations are no longer automatically added in the standard way. This is the expected behavior of this annotation, not a startup error.

After the experiment, remove `@EnableWebMvc` to return to the recommended customization approach when you want to keep Boot defaults.

## 12. Reading the Condition Evaluation Report Through the Three Gates

When running with `--debug`, search for:

~~~text
WebMvcAutoConfiguration
~~~

You may encounter results with the following meanings:

| Condition | Positive match when | Negative match when |
| --- | --- | --- |
| `@ConditionalOnWebApplication(SERVLET)` | Context is a servlet web application | Context is NONE or REACTIVE |
| `@ConditionalOnClass` | All three required classes are on the classpath | Missing Servlet API or Spring MVC class |
| `@ConditionalOnMissingBean(WebMvcConfigurationSupport.class)` | No alternative MVC support bean exists | An MVC support bean already exists, usually due to `@EnableWebMvc` |

Illustrative example of the meaning of a negative match:

~~~text
WebMvcAutoConfiguration:
   Did not match:
      - @ConditionalOnMissingBean
        found bean of type WebMvcConfigurationSupport
~~~

This is a **simplified mock log**, not a verbatim output guaranteed across all versions.

To read the report accurately:

1. Locate the exact class name `WebMvcAutoConfiguration`.
2. Distinguish class-level conditions from conditions on individual bean methods.
3. Identify the first condition that did not match and its explanatory message.
4. Cross-reference with context type, runtime classpath, and application-registered beans.
5. If class-level conditions all match but a specific bean is missing, locate the `@Bean` method and its individual condition.
6. If a bean is registered but fails to initialize, read the stack trace; the Condition Evaluation Report does not replace constructor/factory method errors.

You can inspect the `/actuator/conditions` endpoint if the application has added Actuator, exposed the endpoint, and secured access appropriately. `--debug` does not automatically install Actuator or open this endpoint.

## 13. Common Pitfalls

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Has jakarta.servlet.Servlet but WebMvcAutoConfiguration does not run | Context is not a servlet web application | Check `spring.main.web-application-type` and web context |
| Has starter-web but class condition does not match | Runtime dependency excluded, wrong scope, or incompatible version | Inspect runtime dependency tree and classes inside JARs |
| Using Boot 3 but code looks for javax.servlet.Servlet | Confusing Boot 2 namespace with Boot 3 Jakarta | Use `jakarta.servlet.Servlet` and compatible dependencies |
| WebMvcAutoConfiguration backs off after adding @EnableWebMvc | DelegatingWebMvcConfiguration is a subtype of WebMvcConfigurationSupport | Remove @EnableWebMvc if you only need customization |
| Adding WebMvcConfigurer and thinking Boot will back off | Confusing WebMvcConfigurer with WebMvcConfigurationSupport | Keep WebMvcConfigurer to extend Boot defaults |
| DispatcherServlet bean exists but view resolver or resource handling is missing | DispatcherServletAutoConfiguration and WebMvcAutoConfiguration are separate configurations | Read the condition report of each class |
| Class-level conditions match but a bean method does not appear | The bean method's own condition did not match | Read the condition on that method |
| Changed Boot version but IDE source is still stale | Source attachment or runtime dependency not updated | Verify dependency tree and open the source JAR of the matching version |
| Putting @EnableWebMvc in test config produces different results from production | Test changed the back-off condition | Inspect test configuration and the Condition Evaluation Report |

## 14. Checklist for Tracing Servlet Conditions

When you need to explain why Spring MVC auto-configuration is or is not present in an application:

1. Confirm the running Spring Boot version.
2. Locate the exact artifact containing `WebMvcAutoConfiguration`.
3. Open source/Javadoc for the exact release; do not use a same-named class from another major version.
4. Read `@ConditionalOnWebApplication(type = SERVLET)`.
5. Check the runtime classpath for `jakarta.servlet.Servlet`, `DispatcherServlet`, and `WebMvcConfigurer`.
6. Check whether there is a `WebMvcConfigurationSupport` bean or `@EnableWebMvc` configuration.
7. Enable `--debug` and locate the class in the Condition Evaluation Report.
8. If the class is applied, continue reading the conditions of the bean method under investigation.
9. Verify with an integration test/MockMvc in a servlet context.
10. Try non-web or `@EnableWebMvc` to understand each condition branch.

## 15. Self-Check Questions

**Question 1.** How do `@ConditionalOnWebApplication(type = SERVLET)` and `@ConditionalOnClass(Servlet.class)` differ?  
**Answer:** One condition checks whether the application/context is a servlet web application; the other checks whether the class is on the runtime classpath. Having the Servlet class is not enough to prove the context is a servlet web application.

**Question 2.** Why does MVC auto-configuration not run when an application has `spring-boot-starter-web` but sets `spring.main.web-application-type=none`?  
**Answer:** The classpath condition may match, but the servlet web application condition does not match because the context is forced to be non-web.

**Question 3.** What are the three classes required by `@ConditionalOnClass` in Boot 3.3.x?  
**Answer:** `jakarta.servlet.Servlet`, `org.springframework.web.servlet.DispatcherServlet`, and `org.springframework.web.servlet.config.annotation.WebMvcConfigurer`.

**Question 4.** Why does `@EnableWebMvc` cause `WebMvcAutoConfiguration` to back off?  
**Answer:** It imports `DelegatingWebMvcConfiguration`, a subtype of `WebMvcConfigurationSupport`; the `@ConditionalOnMissingBean` condition no longer matches.

**Question 5.** Does adding a `WebMvcConfigurer` bean make Boot MVC auto-configuration back off?  
**Answer:** No. WebMvcConfigurer is an extension callback, not WebMvcConfigurationSupport. This is the usual way to keep Boot defaults and add customizations.

**Question 6.** Is `after = DispatcherServletAutoConfiguration.class` a condition for MVC auto-configuration to be enabled?  
**Answer:** No. It is metadata ordering auto-configuration processing; the on/off conditions live in `@Conditional...` annotations.

## 16. Official References

- [WebMvcAutoConfiguration — Spring Boot 3.3 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/servlet/WebMvcAutoConfiguration.html)
- [Servlet Web Applications — Spring Boot 3.3 Reference](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html)
- [ConditionalOnWebApplication — Spring Boot 3.3 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnWebApplication.html)
- [WebMvcRegistrations — Spring Boot 3.3 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/servlet/WebMvcRegistrations.html)

**Takeaway:** `WebMvcAutoConfiguration` applies only when **the context is a servlet web application**, **Servlet API and Spring MVC classes are on the runtime classpath**, and **no user-supplied WebMvcConfigurationSupport exists**. `WebMvcConfigurer` extends the default configuration; `@EnableWebMvc` hands MVC configuration control to the application. Reading the three condition gates for the right version is the fastest way to understand why Spring Boot does or does not provide MVC infrastructure.
