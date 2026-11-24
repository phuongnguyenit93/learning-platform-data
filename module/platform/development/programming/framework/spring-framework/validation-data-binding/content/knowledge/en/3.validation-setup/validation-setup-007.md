# Distinguishing Spring Framework Configuration and Spring Boot Auto-Configuration

## 1. Two Concepts Solving Two Different Problems

**Spring Framework configuration** describes the beans, dependencies, component scans, and infrastructure components an application wants to use. The Spring IoC container instantiates, wires, and manages the lifecycle of those beans. Spring Framework provides APIs such as `@Configuration`, `@Bean`, `@Component`, `@Import`, `@Profile`, `Environment`, `ApplicationContext`, and extension mechanisms.

**Spring Boot auto-configuration** uses conditions and information from the classpath, environment, configuration properties, and existing beans to automatically register infrastructure beans commonly needed by an application. Boot builds on the exact same Spring container: auto-configuration ultimately produces ordinary bean definitions and beans. It does not replace `ApplicationContext`, IoC, dependency injection, or Spring configuration.

For example, in plain Spring Framework, developers may need to explicitly register web infrastructure, configure servlets, data binding, validators, converters, and specific beans. In a Spring Boot MVC application, the appropriate dependency and Boot's defaults typically supply MVC infrastructure out of the box so you can focus on controllers, services, and application configuration.

| Aspect | Spring Framework | Spring Boot auto-configuration |
| --- | --- | --- |
| Nature | IoC infrastructure and APIs for application authors to configure beans | Conditional configurations running on top of Spring's infrastructure |
| Where beans are defined | `@Bean`, `@ComponentScan`, XML, bean registration APIs | Auto-configuration classes and configurations imported by Boot |
| Activation conditions | Per definitions and configurations supplied by the application | Classpath, existing/missing beans, properties, web application type, and other conditions |
| Customization | Define your own beans and extension points | Boot properties, custom beans, extension points, or excluding specific auto-configurations |
| When dependencies are missing | Configuration may fail to compile or fail to start | Auto-configuration may not be applied because conditions are not satisfied |
| Target usage | All Spring applications, including those without Boot | Applications using Spring Boot's auto-configuration mechanism |

Merely adding a Spring library to the classpath does not mean Spring Framework will automatically register every bean the application needs. Conversely, Boot does not auto-configure every arbitrary library either: a corresponding auto-configuration must exist and its conditions must match.

## 2. How Does Spring Framework Configuration Work?

### 2.1. Declaring Beans via Java Configuration

```java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class ManualSpringConfigDemo {
    interface ClockLabel { String text(); }

    static class FixedClockLabel implements ClockLabel {
        @Override public String text() { return "10:30"; }
    }

    static class GreetingService {
        private final ClockLabel clock;
        GreetingService(ClockLabel clock) { this.clock = clock; }
        String greet() { return "Hello at " + clock.text(); }
    }

    @Configuration(proxyBeanMethods = false)
    static class AppConfig {
        @Bean ClockLabel clockLabel() { return new FixedClockLabel(); }
        @Bean GreetingService greetingService(ClockLabel clockLabel) {
            return new GreetingService(clockLabel);
        }
    }

    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {
            System.out.println(context.getBean(GreetingService.class).greet());
        }
    }
}
```

Output with Spring Context and its dependencies on the classpath:

```text
Hello at 10:30
```

`AppConfig` is application-authored configuration; the container processes `@Bean` and injects `ClockLabel` into `GreetingService`. There is no Spring Boot and no HTTP server needed. This is a Java 17+ program with `main`, though plain `javac ManualSpringConfigDemo.java` requires Spring on the classpath. In a Gradle/Maven project, use the project's build and runtime classpath mechanisms.

### 2.2. Component Scan and Environment-Based Configuration

`@Component`, `@Service`, `@Repository`, and `@Controller` mark classes discoverable via component scanning. Marking a class **does not guarantee the bean exists**: scan scope, context configuration, conditions, and initialization errors determine the outcome. `@Profile("dev")` can restrict a bean by active profile; `@Conditional` or other configuration mechanisms can control bean registration.

`Environment` and property sources exist in Spring Framework itself; Boot extends convenient loading, binding, and organization via `application.properties`/`application.yml`, profiles, and `@ConfigurationProperties`. Do not confuse Spring's property-reading mechanism with property-specific rules of individual Boot auto-configurations.

## 3. How Does Spring Boot Enable Auto-Configuration?

In a typical Boot application:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

`@SpringBootApplication` combines the core roles of `@SpringBootConfiguration`, `@EnableAutoConfiguration`, and `@ComponentScan`. `SpringApplication.run` prepares the environment and creates/refreshes the application context. Boot imports auto-configurations available in the dependencies of the Boot version in use.

In Spring Boot 3.x, auto-configurations are typically listed in `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` inside the relevant JAR. This is a list of classes for Boot to evaluate; each class may still be skipped if its conditions are not met. Avoid treating this registration file format as an immutable rule across every Boot generation.

Common conditional annotations:

- `@ConditionalOnClass`: configuration applies only when the required class is on the classpath.
- `@ConditionalOnMissingBean`: registers a default bean when no matching bean exists yet, per the defined condition.
- `@ConditionalOnBean`: applies only when a required bean already exists.
- `@ConditionalOnProperty`: depends on a property and its configured value.
- `@ConditionalOnWebApplication`: restricts by web application type.

There is no guarantee that **every** auto-configuration uses `@ConditionalOnMissingBean`, or that a custom bean will always override every default bean. You must check the exact conditions, bean types, bean names, evaluation scope, and configuration order of the component involved.

### 3.1. A Familiar Example: Web MVC

In Gradle (Groovy DSL) of a version-managed Spring Boot project:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

The web starter typically brings in Spring MVC, required dependencies, and an appropriate embedded web server. When the application is identified as a servlet web application, conditional auto-configurations can set up `DispatcherServlet`, registrations, message converters, and default MVC components.

Controller:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class GreetingController {
    @GetMapping("/greeting")
    String greeting() {
        return "Hello";
    }
}
```

If the controller is within the component scan scope of a running MVC application, `GET /greeting` typically returns the response body `Hello`. This is an example class belonging to a full Boot application; `GreetingController.java` alone does not start a server.

Distinction: `@RestController` and `@GetMapping` belong to Spring Web's programming model; Boot preparing default beans and web application settings is the contribution of auto-configuration.

## 4. Starter, Auto-Configuration, and Property Are Not the Same Thing

Three concepts often appear together yet play distinct roles:

1. **Starter**: a curated dependency bundle for easy capability selection, such as web, validation, or data access; a starter itself is not a container.
2. **Auto-configuration**: Spring configuration classes that run conditionally when Boot detects the application has the required components.
3. **Configuration properties**: input data for configuration, such as `server.port=8081`; they take effect only if a relevant component reads or binds that value.

Example:

```properties
server.port=8081
spring.main.banner-mode=off
```

In a Boot servlet application with a properly configured embedded server, `server.port` changes the listening port. In a plain `AnnotationConfigApplicationContext` application without Boot/web server, setting this property does not conjure an HTTP server on its own.

Do not assume `application.yml` is completely unavailable in every plain Spring Framework app: a Framework application can load YAML/property sources itself using appropriate mechanisms or libraries. Boot provides conventional configuration paths and default integration, reducing setup boilerplate.

## 5. Ways to Customize Boot While Still Using Spring Infrastructure

### 5.1. Defining Application Beans

Suppose an auto-configuration provides a default bean when no `ClockLabel` exists. The application can declare:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class CustomConfig {
    @Bean
    ClockLabel clockLabel() {
        return () -> "11:45";
    }
}
```

This is an **extension point illustration**, with `ClockLabel` being the application interface from section 2's example; the snippet is not a built-in Boot auto-configuration. If the auto-configuration genuinely uses `@ConditionalOnMissingBean(ClockLabel.class)` in the right context, the custom bean causes the default configuration to "back off". Without that condition, adding a bean can cause duplicates or ambiguity instead of replacement.

### 5.2. Using Official Component Properties

Prefer documented properties to alter defaults, such as server configuration or JSON formatting for the running feature and version. Do not invent properties expecting auto-config to read them; there must be a configuration class binding the property or application code explicitly handling it.

### 5.3. Extending via Configuration Interfaces

For Spring MVC, implementing `WebMvcConfigurer` can add formatters, interceptors, resource handlers, or other customizations while retaining the active MVC foundation:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
class MvcConfig implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        // Register application-specific converters or formatters here.
    }
}
```

Note that `@EnableWebMvc` usually switches to application-controlled MVC configuration per Spring Framework and can prevent many of Boot's default MVC customizations from applying. Use it only when you intentionally want to take over MVC configuration.

### 5.4. Excluding Specific Auto-Configurations

```java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;

@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)
class NoDataSourceApplication {
}
```

This is an example of excluding an auto-configuration when the application **intentionally** does not want Boot to create a `DataSource`. Do not use it as a trick to hide missing JDBC driver, URL, or credential errors if the application actually needs a database. You can also exclude via the `spring.autoconfigure.exclude` property when appropriate.

## 6. Writing Auto-Configuration When Developing a Library

Ordinary applications only need `@Configuration` and `@Bean`. Auto-configuration is valuable when shipping a shared library/starter and wanting Boot to automatically activate features based on defined conditions.

Simple example (placed in the JAR containing the auto-configuration):

```java
package example.autoconfig;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(GreetingFormatter.class)
public class GreetingAutoConfiguration {
    @Bean
    @ConditionalOnMissingBean
    GreetingFormatter greetingFormatter() {
        return new GreetingFormatter();
    }
}
```

And an illustrative library type:

```java
package example.autoconfig;

public class GreetingFormatter {
    public String format(String name) {
        return "Hello, " + name;
    }
}
```

Register the resource path:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

File contents:

```text
example.autoconfig.GreetingAutoConfiguration
```

In Spring Boot 3.x, Boot loads auto-configuration classes from the imports file, evaluates class and bean conditions, and registers beans when conditions pass. `@ConditionalOnMissingBean` is commonly appropriate for defaults that applications may override. Test auto-configuration using `ApplicationContextRunner` from `spring-boot-test` across combinations with/without dependencies and custom beans; having the class in imports does not prove every condition succeeds.

Do not place a library's auto-configuration classes under regular component scanning as a default activation mechanism; the imports mechanism gives Boot clearer control over auto-configuration ordering and conditions.

## 7. Diagnosing Why Auto-Configuration Was or Was Not Applied

When a bean does not appear, check in sequence:

1. **Does the application use Boot auto-configuration?** Verify the entry point, `@EnableAutoConfiguration`/`@SpringBootApplication`, and no unintended exclusions.
2. **Does the classpath have the required dependencies?** Check the dependency tree and modules present at runtime.
3. **Are conditions satisfied?** Another existing bean, profile/property, web application type, class, or resource can alter the outcome.
4. **Component scan scope?** Are application `@Component` and `@Configuration` classes within scanned/imported packages?
5. **Did bean creation fail?** Construction/injection failures, dependency cycles, or invalid configurations differ from an auto-configuration not being selected.
6. **Are there multiple beans of the same type?** `@Primary`, qualifiers, bean names, or default conditions can affect injection.

With Spring Boot, enable the condition evaluation report using `--debug` or appropriate logging levels; `ConditionEvaluationReport` shows which auto-configurations were evaluated and why they matched/did not match. If using Spring Boot Actuator and the corresponding endpoint is enabled/secured, the `conditions` endpoint can also aid analysis. Secure management endpoints appropriately; never assume this endpoint should be public.

Example running a properly packaged Boot application:

```bash
java -jar build/libs/your-application.jar --debug
```

The JAR name is illustrative; use the actual built artifact. Do not confuse Boot's `--debug` flag with JVM debugging tools.

## 8. Common Reasoning Mistakes

- **"Having `spring-context` means Boot auto-configures everything."** False: Spring Context provides the container mechanism; Boot needs auto-configuration enabled along with matching conditions.
- **"Having a starter is enough for a feature to work in all cases."** False: drivers, endpoints, credentials, external service configs, or specific beans may still be required.
- **"`@Bean` always takes absolute precedence over auto-config."** Read the auto-configuration's conditions and bean registration timing; sometimes multiple beans conflict.
- **"Disable auto-configuration to fix any startup error."** Arbitrary exclusion can mask the root cause and remove the feature entirely.
- **"Boot dictates configuration and cannot be changed."** Many defaults can be customized via properties, custom beans, and extension points; flexibility varies by component.
- **"Framework XML/Java config is obsolete and no longer used in Boot."** Boot still runs on the Spring IoC container and can use annotation config, XML/imports, and container APIs when needed.
- **"Spring Framework and Spring Boot are two independent containers."** Boot orchestrates application startup and auto-configuration on top of the Spring Framework container.

## 9. Checklist for Choosing a Configuration Approach

1. If you only need to create beans or declare business dependencies, start with `@Component`/`@Configuration`/`@Bean` and constructor injection.
2. If using Spring Boot, choose the corresponding starter first, and check the official properties and default beans Boot supplies.
3. When overriding default behavior, identify the exact extension point: property, custom bean, configuration interface, or auto-config exclusion.
4. When a bean is missing, read the condition report and dependency tree before writing workaround configurations.
5. When developing a library for multiple Boot applications, consider conditional auto-configuration and test back-off cases; do not apply that pattern to ordinary business beans.

**Conclusion:** Spring Framework provides the tools to define and run application configuration. Spring Boot uses those very tools to apply conditional defaults, reducing repetitive setup. Understanding this boundary enables targeted customization and evidence-based troubleshooting.