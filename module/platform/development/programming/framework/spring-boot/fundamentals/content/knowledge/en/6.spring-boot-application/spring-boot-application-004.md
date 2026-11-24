# @EnableAutoConfiguration Selects Configuration Conditionally

A very small Spring Boot application can run an HTTP server, accept JSON, convert requests into Java objects, and use many Spring Framework components even though the developer never wrote initialization code for each of those components. **@EnableAutoConfiguration** is a key part of this experience: it enables Spring Boot to **find available auto-configurations, evaluate conditions, and apply the ones that fit the current application**.

The core word here is **“conditionally”**. Spring Boot does not turn on every feature simply because a library exists. It observes what is already present in the application: dependencies on the classpath, beans you have defined, configured properties, web application type, resources, and other factors. From that, Boot decides which configurations can be added to the Spring ApplicationContext.

Within the **@SpringBootApplication** chapter, this lesson focuses on the role of **@EnableAutoConfiguration**, how it works alongside the remaining annotations, and how to trace the cause when a bean is automatically created, skipped, or missing compared to expectations.

## 1. Where @EnableAutoConfiguration Fits Inside @SpringBootApplication

A typical Boot application has an entry point:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

By role, **@SpringBootApplication** combines three groups of capabilities:

| Component | Responsibility |
|---|---|
| **@SpringBootConfiguration** | Marks the class as the application's Spring Boot configuration; built on Spring Framework's **@Configuration** mechanism. |
| **@EnableAutoConfiguration** | Activates the mechanism that evaluates auto-configurations from Spring Boot and integrated libraries. |
| **@ComponentScan** | Searches for application-registered components via package scanning, such as **@Component**, **@Service**, **@Repository**, and **@Controller**. |

The three components serve **three different goals**, even though they are usually placed under a single annotation.

~~~text
DemoApplication
    @SpringBootApplication
            │
            ├── @SpringBootConfiguration
            │       └── Application configuration class
            │
            ├── @ComponentScan
            │       └── Application-defined beans/components
            │
            └── @EnableAutoConfiguration
                    └── Auto-configurations selected conditionally
                            │
                            ▼
                    Spring ApplicationContext
                        ├── application beans
                        ├── beans from Java configuration
                        └── beans provided by auto-configuration
~~~

**@ComponentScan is not @EnableAutoConfiguration.** When you write a **@Service** class in a subpackage and Spring creates a bean for it, the direct cause is typically component scanning. When Boot automatically prepares web beans or foundational configuration based on present dependencies, that is the responsibility of auto-configuration.

You can use **@EnableAutoConfiguration** by itself in a Spring configuration if the application design requires it, though the common case is using **@SpringBootApplication** for a unified starting point.

## 2. What Problem Does Auto-Configuration Solve?

Spring Framework already provides an IoC container, **@Configuration**, **@Bean**, DI, Spring MVC, transaction management, and many other utilities. Before an application can use them, several infrastructure pieces must be declared and wired together properly.

For example, to handle HTTP requests through Spring MVC, an application needs the appropriate pieces such as:

- A web framework on the classpath.
- An ApplicationContext matching the application type.
- DispatcherServlet and the required MVC components.
- HTTP message conversion or chosen content-handling mechanisms.
- A servlet container or HTTP environment supporting Spring MVC.

These parts can be configured manually. However, if every project had to repeat the exact same configuration boilerplate, creating new applications would become tedious and increase the risk of configuration drift across services.

Spring Boot supplies **auto-configuration classes** to handle these repetitive setups, applying sensible defaults when the corresponding conditions are met.

Example with a web application using **spring-boot-starter-web** in Spring Boot 3.x:

~~~text
starter-web dependency
          │
          ▼
Classpath contains the relevant web components
          │
          ▼
Spring Boot reads candidate auto-configurations
          │
          ▼
Evaluates conditions against environment and existing beans
          │
          ▼
Matching configurations are applied
          │
          ▼
ApplicationContext has the required web infrastructure
          │
          ▼
Your controllers can handle requests
~~~

Spring Boot **does not write your endpoints, business logic, or security policies for you**. It helps assemble the right infrastructure for the parts you actually use.

## 3. Finding Auto-Configuration Candidates Differs from Component Scanning

An important question: **How does Boot know which auto-configuration classes to inspect?**

In Spring Boot 3.x, libraries can publish a list of auto-configurations in the resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

This file contains the fully qualified names of auto-configuration classes exported by the module, typically one class name per line. Illustrative example:

~~~text
com.example.greeting.autoconfigure.GreetingAutoConfiguration
com.example.metrics.autoconfigure.MetricsBridgeAutoConfiguration
~~~

The names above are hypothetical examples, not built-in Spring Boot classes.

**@EnableAutoConfiguration** uses Boot's import and selector mechanism to collect candidates registered through metadata. A central component in this mechanism is **AutoConfigurationImportSelector**, attached to the annotation via **@Import**. The selector also evaluates exclusions and related metadata before configurations enter Spring's configuration processing.

Conceptual model:

~~~text
@SpringBootApplication
    └── @EnableAutoConfiguration
          └── @Import(AutoConfigurationImportSelector)
                 │
                 ▼
       Read candidate auto-configuration list
                 │
                 ├── Filter out excluded configurations
                 ├── Check metadata to drop unsuitable candidates early
                 └── Pass selected classes into configuration processing
                                  │
                                  ▼
                        Evaluate @Conditional...
                                  │
                       ┌──────────┴──────────┐
                       │                     │
                   Satisfied           Not satisfied
                       │                     │
                       ▼                     ▼
                Apply configuration     Skip the configuration/
                and matching beans      or corresponding bean
~~~

Do not interpret the diagram above as a single check applied once for all cases. **Conditions can be placed at the class level or at the @Bean method level**, and are evaluated at appropriate stages as Spring processes configurations and bean definitions. An accepted auto-configuration class does not mean **every bean** inside it will be created.

### 3.1. Why Not Scan Every Class on the Classpath?

The classpath can contain vast numbers of JARs and classes. Inspecting every class and guessing which ones are needed would be both expensive and hard to control. Publishing a list of auto-configurations lets Boot know **which configurations are designed to participate automatically**, independently of application component scanning.

A regular **@Configuration** class inside a dependency does not automatically become an auto-configuration just because its JAR is on the classpath. To become an auto-configuration candidate under Boot 3.x's standard mechanism, it needs to be registered according to Boot's contract.

### 3.2. Differences Between Boot 2.x and Boot 3.x

In older versions of Spring Boot, auto-configurations were commonly declared via the **org.springframework.boot.autoconfigure.EnableAutoConfiguration** key in **META-INF/spring.factories**. Spring Boot 2.7 introduced support for the **AutoConfiguration.imports** format; in Spring Boot 3.x, this is the standard auto-configuration registration mechanism.

When reading an older library or upgrading an internal library, check **which Spring Boot version the library supports**. You cannot simply copy a registration setup from an old guide and assume it works in newer versions.

## 4. At What Levels Are Conditions Checked?

An auto-configuration class commonly declares conditions at the **class level**; **@Bean** methods can declare their own conditions.

~~~java
@AutoConfiguration
@ConditionalOnClass(SomeClient.class)
public class SomeClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(SomeClient.class)
    SomeClient someClient() {
        return new SomeClient();
    }
}
~~~

*SomeClient here is a hypothetical illustrative type.* Meaning:

- If the **SomeClient** class is absent according to the classpath condition, the auto-configuration can be skipped.
- If the class is present, Boot continues evaluating the condition on the bean definition.
- If the application already has a matching bean, the default bean configuration can **back off**.
- If all required conditions are met, the default bean is registered.

This mechanism lets Boot supply defaults while still allowing application code to declare replacements for specific components.

### 4.1. Key Condition Groups

| Annotation | Question checked | Use case |
|---|---|---|
| **@ConditionalOnClass** | Are the specified classes present on the classpath? | Configure a client only when the client library is present. |
| **@ConditionalOnMissingClass** | Is a specific class absent? | Choose a configuration path compatible with environments lacking a library. |
| **@ConditionalOnBean** | Does a matching bean already exist per the condition? | Configure an adapter only when the required dependency already exists. |
| **@ConditionalOnMissingBean** | Is there no matching bean yet? | Provide a default bean, allowing the application to replace it. |
| **@ConditionalOnSingleCandidate** | Can a single matching bean candidate be determined? | Configure an integration only when the dependency is unambiguous. |
| **@ConditionalOnProperty** | Do properties match the declared rule? | Enable/disable features via externalized configuration. |
| **@ConditionalOnWebApplication** | Is this a web application of the requested type? | Configure Servlet web or reactive web. |
| **@ConditionalOnNotWebApplication** | Is this a non-web application? | Appropriate configuration for batch/command-line apps. |
| **@ConditionalOnResource** | Are the required resources on the classpath? | Activate an integration only when matching resources exist. |
| **@ConditionalOnJava** | Does the Java runtime meet the version requirement? | Branch support by Java version. |
| **@ConditionalOnExpression** | Does a SpEL expression evaluate to true? | Special cases; consider evaluation cost and early initialization impact. |

All conditions are evaluated within a **specific context**. For example, **@ConditionalOnBean** does not simply ask "is a class on the classpath?"; it checks for **bean definitions / bean presence** in the Spring context according to the declared criteria.

### 4.2. @ConditionalOnClass: Dependencies as the First Signal

Imagine an application that may or may not include a Redis library. An auto-configuration related to Redis usually only makes sense if the required library types are present. **@ConditionalOnClass** lets Boot skip the configuration when the classpath condition is not met.

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.example.optional.ClientDriver")
public class OptionalClientAutoConfiguration {
    // Configuration evaluated when the classpath condition is satisfied.
}
~~~

Using **name** checks the class by string name, which is useful when the type comes from an optional dependency. When a configuration must directly reference classes that might be absent, isolate them in a conditionally loaded nested/child configuration to avoid class-linking errors before conditions can guard that code.

Having a class on the classpath **does not prove the configuration was enabled**. An auto-configuration can still be excluded, lack a property, mismatch the web application type, or fail a bean condition.

### 4.3. @ConditionalOnMissingBean: Defaults That Can Step Aside

Suppose a library wants to supply a default **GreetingService**, while allowing applications to create their own implementation.

~~~java
@Bean
@ConditionalOnMissingBean(GreetingService.class)
GreetingService greetingService() {
    return new GreetingService("Hello");
}
~~~

If the application context already contains a matching **GreetingService** bean when the condition is evaluated, this default bean will not be registered.

This is the **back off** principle: "Boot provides a default value when the application has not supplied its own choice."

Key point to remember: **@ConditionalOnMissingBean is not a mechanism for overriding a bean after it has already been created**. The condition operates while processing bean definition registrations, and depends on the bean definitions known at evaluation time. That is why Boot documentation generally recommends using this type of condition in auto-configurations, where Boot can arrange for application-declared beans to be evaluated first.

### 4.4. @ConditionalOnProperty: Selecting Configuration by Property

An illustrative annotation:

~~~java
@ConditionalOnProperty(
    prefix = "demo.greeting",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false
)
~~~

Intended meaning:

- **demo.greeting.enabled=true**: condition satisfied.
- **demo.greeting.enabled=false**: not satisfied.
- Property not declared: not satisfied because **matchIfMissing=false**.

If **matchIfMissing=true** is set, the condition can be satisfied even when the property is absent.

With **@ConditionalOnProperty** when **havingValue** is omitted, the general rule is that the property must exist and its value must not equal the string **false** according to the condition's evaluation rules. So do not treat it as a general-purpose boolean parser for arbitrary values; when precision is needed, specify **havingValue** explicitly.

In particular, this condition is not suited for directly inferring the presence or elements of a **collection** property using a simple prefix name; choose another condition mechanism for complex cases.

### 4.5. @ConditionalOnBean and Processing Order Risks

When an auto-configuration should only apply if a bean from another configuration exists:

~~~java
@ConditionalOnBean(SomeClient.class)
~~~

the condition inspects bean definitions that have already been processed up to that point. If a bean is registered in a configuration processed later, the condition might not see it yet. Therefore, auto-configurations typically declare **ordering** when they depend on another auto-configuration.

Do not treat the order of classes in the imports file as a reliable contract for all conditional relationships. Boot has dedicated auto-configuration ordering tools, described in a later section.

## 5. A Complete Example of Combined Conditions

Suppose an application has a greeting module and wants to:

1. Allow toggling default service creation via configuration.
2. Have a default prefix while allowing reconfiguration.
3. Allow the application to declare its own **GreetingService** to replace the default bean.

This is an intentionally simple example for understanding auto-configuration. First, a plain Java business class:

~~~java
package com.example.greeting;

public class GreetingService {
    private final String prefix;

    public GreetingService(String prefix) {
        this.prefix = prefix;
    }

    public String greet(String name) {
        return prefix + ", " + name + "!";
    }
}
~~~

A properties configuration class:

~~~java
package com.example.greeting.autoconfigure;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo.greeting")
public class GreetingProperties {
    private String prefix = "Hello";

    public String getPrefix() {
        return prefix;
    }

    public void setPrefix(String prefix) {
        this.prefix = prefix;
    }
}
~~~

Auto-configuration:

~~~java
package com.example.greeting.autoconfigure;

import com.example.greeting.GreetingService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@EnableConfigurationProperties(GreetingProperties.class)
@ConditionalOnProperty(
    prefix = "demo.greeting",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService greetingService(GreetingProperties properties) {
        return new GreetingService(properties.getPrefix());
    }
}
~~~

Here:

- **@AutoConfiguration** marks the auto-configuration class per Spring Boot's mechanism.
- **@EnableConfigurationProperties** registers binding **demo.greeting.prefix** to **GreetingProperties**.
- **@ConditionalOnProperty** determines whether to apply the auto-configuration based on the **enabled** property.
- **@Bean** describes how to create **GreetingService**.
- **@ConditionalOnMissingBean** creates the default service only if no matching bean of the same type exists yet.

For this library module to be recognized as an auto-configuration candidate in Spring Boot 3.x, the following file must be packaged in the JAR:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Content:

~~~text
com.example.greeting.autoconfigure.GreetingAutoConfiguration
~~~

The class name must match the actual compiled class available on the classpath. **Simply attaching @AutoConfiguration without registering or importing the configuration via the proper mechanism is not enough for Boot to auto-discover the library.**

### 5.1. Enabled by Default Case

With:

~~~yaml
demo:
  greeting:
    prefix: "Hi"
~~~

Because **matchIfMissing=true**, omitting **demo.greeting.enabled** still lets the configuration participate.

If no other **GreetingService** bean exists, Boot registers the bean created via the factory method. Calling:

~~~java
greetingService.greet("Lan");
~~~

produces:

~~~text
Hi, Lan!
~~~

### 5.2. Disabled via Property Case

~~~yaml
demo:
  greeting:
    enabled: false
~~~

The class-level condition on **GreetingAutoConfiguration** fails, so this configuration does not register the bean it defines. If the application still has a GreetingService bean from another source, that bean is **not automatically removed** by disabling the auto-configuration.

### 5.3. User-Defined Bean Case

The application can declare:

~~~java
package com.example.demo;

import com.example.greeting.GreetingService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MyGreetingConfiguration {
    @Bean
    GreetingService customGreetingService() {
        return new GreetingService("Hello");
    }
}
~~~

When this bean is registered before **@ConditionalOnMissingBean(GreetingService.class)** is evaluated, the auto-configuration **backs off**. The expected result when injecting GreetingService in the application is the application-declared bean.

This is the intended behavior of auto-configurations designed with back-off conditions. Not every built-in Spring Boot bean allows replacement in the exact same way; check the conditions on the specific configuration.

### 5.4. Outcome Table by Scenario

| Property enabled | App-declared GreetingService bean | Outcome from example auto-configuration |
|---|---|---|
| Absent | No | Default bean registered because **matchIfMissing=true**. |
| **true** | No | Default bean registered. |
| **false** | No | No bean registered from this configuration. |
| **true** | Yes | **@ConditionalOnMissingBean** causes default bean to back off. |
| **false** | Yes | Auto-configuration skipped; app-declared bean remains the app's own bean. |

This table applies only when the library is registered, the classpath is complete, and no other special configuration interferes.

## 6. Classpath and Starters: Input Signals, Not the Entire Decision

When adding a starter:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Gradle resolves direct and transitive dependencies to assemble the classpath. This classpath is an important signal for conditions such as **@ConditionalOnClass**. However, decisions at the Spring ApplicationContext level also involve properties, existing beans, and application type.

Example:

~~~text
Starter/dependency present
           │
           ▼
Required classes appear
           │
           ▼
Classpath condition satisfied?
           │
           ▼
Web app condition matches?
           │
           ▼
Properties allow configuration?
           │
           ▼
Application already has replacement bean?
           │
           ▼
Decision to register default bean
~~~

This is an illustrative decision tree. A specific auto-configuration can use a completely different set of conditions; Boot does not require every configuration to include all five steps.

### 6.1. Spring MVC Example

With Spring Boot 3.x and the Servlet-based web starter, Boot can supply foundational configurations such as Spring MVC setup and matching embedded server integration when conditions are satisfied.

If certain required web libraries are missing, or the application is designed as a non-web application, those conditions may not trigger. If the application defines its own MVC bean supported for override via a missing-bean condition, Boot can yield to that bean.

This explains why merely adding **@RestController** is not enough to serve an API in just any Java program: the controller needs to sit inside a context with appropriate web infrastructure.

### 6.2. DataSource Example

With JDBC libraries and matching configuration conditions, Spring Boot can automatically prepare a **DataSource**. However:

- Appropriate driver and connection URL must be determinable from the classpath/configuration or options supported by Boot.
- Supported embedded databases behave differently from external databases.
- An application-provided DataSource bean can cause the default DataSource configuration to back off, depending on specific conditions.
- Missing URL/driver/credentials for an external database cannot be guessed by Boot from the starter name.

If startup fails with a DataSource-related error, read the **cause** and inspect the configuration; you cannot conclude "adding the JDBC starter means Boot must connect successfully on its own."

## 7. Differences Between Auto-Configuration and Regular Configuration

A regular configuration class:

~~~java
@Configuration
public class BusinessConfiguration {
    @Bean
    OrderPolicy orderPolicy() {
        return new OrderPolicy();
    }
}
~~~

If discovered by component scan or imported, this class contributes beans to the application according to your explicit choices.

An auto-configuration class:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.example.optional.ExternalClient")
public class ExternalClientAutoConfiguration {
    // Optional beans and conditions.
}
~~~

is designed so Boot can **consider it as a candidate**, applying it only when matching conditions hold. It typically lives in a library or integration module, using conditions so it does not break applications that do not use that feature.

| Criterion | Application configuration | Auto-configuration |
|---|---|---|
| Who explicitly declares it? | Project owner, via scan or import. | Library/Boot registers candidates via the auto-configuration mechanism. |
| Primary purpose | Express specific application decisions. | Provide defaults and conditional integrations. |
| Can use @Conditional? | Yes. | Yes, and typically uses multiple conditions. |
| Required to use @ConditionalOnMissingBean? | No. | Not mandatory, though commonly present to back off for custom configs. |
| Automatically becomes a bean just by being in a JAR? | No. | No; must be registered via the proper mechanism and satisfy conditions. |

Several **@Conditional** mechanisms belong to Spring Framework, while **@ConditionalOn...** annotations are provided by Spring Boot as convenient conditions tailored to auto-configuration needs.

## 8. "Bean Present" Condition Differs from "Class Present" Condition

Two of the most frequently confused conditions are **@ConditionalOnClass** and **@ConditionalOnBean**.

Suppose a library provides an **EmailSender** type:

~~~text
Dependency contains EmailSender.class
                 │
                 ▼
    @ConditionalOnClass(EmailSender.class)
                 │
             Satisfied
~~~

That only indicates **the class can be found by the classpath and class loader used for checking**. Nothing guarantees an EmailSender instance has been registered as a Spring bean.

Conversely:

~~~text
ApplicationContext has EmailSender bean
                 │
                 ▼
    @ConditionalOnBean(EmailSender.class)
                 │
             Satisfied
~~~

Here Spring checks for a matching bean. A bean can be declared with **@Bean** or discovered via component scanning, whereas simply having the class on the classpath does not create a bean.

Examples:

~~~java
@ConditionalOnClass(name = "com.example.mail.EmailSender")
class MailIntegrationConfiguration {
    // Only consider configuration when the corresponding library is present.
}
~~~

~~~java
@ConditionalOnBean(name = "primaryEmailSender")
class MailNotificationConfiguration {
    // Apply only when a bean with the required name already exists.
}
~~~

The two conditions answer two different questions:

| Question | Condition |
|---|---|
| Is the library/feature present on the classpath? | **@ConditionalOnClass** |
| Has a bean been provided by the application or another configuration? | **@ConditionalOnBean** |
| Has the application not provided a bean so I can supply a default? | **@ConditionalOnMissingBean** |

That is also why a dependency can download cleanly yet injection with **@Autowired** or constructor injection still fails with a missing bean error: the classpath and the bean registry are two separate layers of information.

## 9. Auto-Configuration Ordering and Bean-Based Conditions

Bean-based conditions inspect bean definitions that have already been processed while building the context. Therefore, ordering between auto-configurations can matter.

Suppose **AuditAutoConfiguration** only operates when an **EventPublisher** created by **EventsAutoConfiguration** exists:

~~~text
EventsAutoConfiguration
          │ registers EventPublisher
          ▼
AuditAutoConfiguration
          │ checks @ConditionalOnBean(EventPublisher.class)
          ▼
Registers AuditListener if conditions match
~~~

In Spring Boot 3.x, an auto-configuration can declare ordering relationships via the **after** or **before** attributes of **@AutoConfiguration**:

~~~java
@AutoConfiguration(after = EventsAutoConfiguration.class)
@ConditionalOnBean(EventPublisher.class)
public class AuditAutoConfiguration {
    // Audit beans and configuration.
}
~~~

These are hypothetical class names. In real code, ensure the EventPublisher bean is registered appropriately and other conditions are also satisfied.

**@AutoConfiguration(after = ...)** affects the processing order of **auto-configuration classes**. It is not a directive saying "instantiate this bean after that bean at runtime." Bean instantiation order is also governed by dependency injection, **@DependsOn**, and other lifecycle mechanisms.

The **@AutoConfigureBefore** and **@AutoConfigureAfter** annotations may also appear in Boot code or supporting libraries. When writing new code for Spring Boot 3.x, the attributes on **@AutoConfiguration** are the clearest way to express this.

### 9.1. Do Not Rely on Accidental Order in the Imports File

Candidate auto-configurations are read and then processed according to Boot's sorting mechanism. Therefore, you should not treat placing one line above another in **AutoConfiguration.imports** as an ordering contract between beans.

If a configuration with **@ConditionalOnBean** depends on a bean coming from another configuration, describe the dependency and ordering relationships explicitly.

### 9.2. When Should You Use @ConditionalOnMissingBean?

The most common usage is **supplying a default bean if the application has not provided its own choice**. For example, a library supplying a default serializer, HTTP client, converter, or service adapter.

Do not use this condition arbitrarily as a workaround for bean name collisions. If a project has two implementations of the same interface and needs to use both, the issue may belong to injection design with **@Qualifier** or **@Primary**, rather than dropping one bean from the context.

## 10. What Happens When Multiple Conditions Exist?

An auto-configuration can have class-level conditions, method-level conditions, and combined conditions:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.example.storage.StorageClient")
@ConditionalOnProperty(
    prefix = "demo.storage",
    name = "enabled",
    havingValue = "true"
)
public class StorageAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(StorageService.class)
    StorageService storageService() {
        return new StorageService();
    }
}
~~~

Assume **StorageService** is a class available in the example module. The conditions above create three decision gates:

1. **StorageClient class present** per the classpath condition.
2. **Property demo.storage.enabled has value true**.
3. **No matching StorageService bean exists yet** when evaluating the method.

If a class-level condition fails, the configuration is skipped before bean methods can contribute any beans. If class-level conditions pass while a method-level condition fails, the configuration class may still be processed, yet that specific bean is not created.

When multiple conditions are combined, you need to understand how Spring's **@Conditional** aggregates results. In common independent-condition cases like this example, all required conditions at a given level must pass for that configuration piece to apply.

### 10.1. Pitfall to Avoid: Conditions Do Not Re-Evaluate Automatically When Properties Change

Auto-configuration is normally decided during application context creation/refresh. If an operator edits a property in a configuration file on disk after the application has started, Spring Boot **does not automatically re-evaluate every running bean and auto-configuration**.

Dynamic configuration changes require a dedicated mechanism, such as recreating the context, restarting the application, or using a controlled refresh mechanism in a supporting ecosystem. Do not treat **@ConditionalOnProperty** as a switch re-evaluated continuously on every request.

### 10.2. How Do Spring Profiles Interact?

**@Profile** and profile-specific configuration files are Spring/Spring Boot mechanisms for selecting beans or configuration sources by environment. They can indirectly alter:

- Properties loaded into the **Environment**.
- Beans registered by the application.
- Outcomes of **@ConditionalOnProperty**, **@ConditionalOnBean**, and **@ConditionalOnMissingBean**.

Example:

~~~yaml
# application-dev.yml
demo:
  greeting:
    enabled: true
    prefix: "Hello from dev"
~~~

~~~yaml
# application-prod.yml
demo:
  greeting:
    enabled: false
~~~

If the **dev** profile is active, the same auto-configuration can satisfy the condition; if the **prod** profile is active and its corresponding property is used, the condition will not pass. The final outcome still depends on property sources, property precedence, and the application's other beans.

Do not equate **@Profile** with **@ConditionalOnProperty**: profiles are an environment and configuration-selection concept, whereas conditional properties evaluate a property against a specific condition expression.

## 11. When Should You Exclude an Auto-Configuration?

Sometimes an auto-configuration is a candidate and its conditions are satisfied to participate, yet the application wants **not to use** that automatic setup.

For instance, an application deliberately not using a database might need to exclude DataSource auto-configuration in a special case where the classpath and configuration cause it to be evaluated.

With Spring Boot 3.x:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;

@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

This is an **intentional exclusion**. If the application truly needs a database, excluding DataSource auto-configuration merely to silence startup errors may turn the problem into a **missing DataSource bean** or broken data access. In that case, fix the connection, driver, or configuration properly.

### 11.1. Three Common Ways to Exclude

| Approach | Example | When useful |
|---|---|---|
| **exclude** | **@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)** | Can reference the auto-configuration class directly. |
| **excludeName** | **@SpringBootApplication(excludeName = "com.example.SomeAutoConfiguration")** | Want to specify by class name without coupling code directly to that type. |
| **spring.autoconfigure.exclude** | Configuration property listing fully qualified auto-configuration class names to exclude. | Want to control exclusions via environment configuration. |

Property example:

~~~yaml
spring:
  autoconfigure:
    exclude:
      - org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

Exclusions apply to **auto-configuration candidates** managed by Boot. They are not a general mechanism for removing all manually declared beans, all classes in a package, or any dependencies from the runtime classpath.

### 11.2. Excluding Auto-Configuration Does Not Remove Dependencies from the JAR

These are two distinct operations:

~~~text
Gradle exclude dependency
    └── Modifies the dependency graph / classpath

Spring Boot exclude auto-configuration
    └── Modifies the set of auto-configurations evaluated
~~~

You might keep a dependency to use its API directly while defining your own beans, or exclude an auto-configuration for architectural reasons. However, to shrink artifact size and dependency surface, revisit **build dependencies**, not just Spring exclusions.

## 12. Diagnostics: Why Was an Auto-Configuration Applied or Skipped?

When an unexpected bean appears, or an expected bean is missing, ask:

- Which candidate configuration is responsible?
- Is it registered in the auto-configuration list?
- Has it been excluded?
- Are the classpath conditions satisfied?
- Did another bean cause a missing-bean condition to fail?
- What are the actual active properties and profiles?
- Under which context type is the application running?

Spring Boot provides diagnostic output for **condition evaluations** to answer those questions.

### 12.1. Condition Evaluation Report

When running the application with the debug flag:

~~~bash
java -jar demo.jar --debug
~~~

Spring Boot can print a **Condition Evaluation Report** in startup logs, detailing numerous condition check outcomes. Entries can be grouped into:

- **Positive matches**: conditions recorded as satisfied.
- **Negative matches**: conditions recorded as unsatisfied, along with reasons.
- **Exclusions**: excluded auto-configurations.
- **Unconditional classes**: certain auto-configurations without class-level conditions reported in their corresponding section.

Illustrative output excerpt:

~~~text
CONDITIONS EVALUATION REPORT

Positive matches:
-----------------
SomeWebAutoConfiguration matched:
   - @ConditionalOnClass found required class '...'

Negative matches:
-----------------
SomeOptionalAutoConfiguration:
   Did not match:
      - @ConditionalOnClass did not find required class '...'

Exclusions:
-----------
    org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

Configuration names in this example are hypothetical; exact formatting and wording depend on the Boot version and actual conditions.

**A positive match does not guarantee everything related works.** It only records that the specific condition was satisfied. An auto-configuration can still have method-level bean conditions, and bean instantiation code can still throw exceptions.

**A negative match is not necessarily an error either.** For example, if an application does not use MongoDB, having Mongo auto-configuration skipped is completely normal.

### 12.2. Actuator conditions Endpoint

If the application includes **spring-boot-starter-actuator** and configures appropriate endpoint exposure, the **conditions** endpoint can expose condition evaluation details through the management interface.

Example configuration illustrating endpoint exposure:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,conditions
~~~

Then, if the endpoint is deployed and accessed according to an appropriate security policy, data can be viewed at the corresponding management path, typically **/actuator/conditions**.

Diagnostic endpoints can reveal internal structure, configurations, and application components. In real operations, restrict access permissions, network exposure, and exposed scope; do not leave them publicly open just for debugging convenience.

### 12.3. Reading Results as a Causal Chain

Suppose you expect a default **GreetingService** but cannot find it:

~~~text
GreetingService missing
          │
          ├── Is GreetingAutoConfiguration registered?
          │
          ├── Is the auto-configuration excluded?
          │
          ├── Is demo.greeting.enabled false?
          │
          ├── Did another GreetingService bean trigger back-off?
          │
          └── Did the bean method fail during instantiation?
~~~

The last point is crucial: **conditions passing yet bean creation failing** is different from **conditions failing so the bean is never defined**. The first case usually produces a **BeanCreationException** stack trace or related cause; the second is usually explained via the condition report and bean registry.

## 13. Common Errors Related to Auto-Configuration

### 13.1. "Dependency Is Present, Yet the Bean Still Does Not Exist"

Possible causes include:

- The dependency is only on the **test** or **compile classpath**, not on the required runtime classpath.
- The module contains the class but does not publish an auto-configuration candidate.
- The auto-configuration was excluded.
- A classpath/property/bean/web-application condition failed.
- The auto-configuration creates the bean only when another dependent bean exists.
- You are injecting the wrong type or wrong bean name.

Check the **resolved classpath**, condition report, and corresponding bean definitions. Adding yet another dependency without understanding the conditions can make things more confusing.

### 13.2. "The Application Suddenly Created a Bean I Didn't Declare"

That may be a bean from auto-configuration. Locate the class defining the bean, inspect the import path and satisfied conditions, and check whether properties exist to adjust it.

If you need to alter behavior, prefer customization mechanisms exposed by the configuration: properties, application-provided beans, customizers, or intentional exclusion. You do not need to rewrite all of Spring's machinery just to change a default value.

### 13.3. "NoSuchBeanDefinitionException Despite Having @Component"

Not every missing bean error stems from auto-configuration. If a component lies outside the scan range, is filtered out by **@Profile**, or is not imported, it still will not be registered.

For instance, **@SpringBootApplication** typically component-scans from the main class's package and its subpackages. Placing a service in a package outside that scan region can cause DI to fail.

Changing **scanBasePackages** on `@SpringBootApplication` primarily affects **component scanning**, not how Boot discovers all auto-configuration candidates. The two scopes use different mechanisms; determine whether your bean is an **application-defined component** or an **auto-configuration-created bean** before applying a fix.

### 13.4. "NoUniqueBeanDefinitionException: Multiple Beans of the Same Type"

This indicates Spring could not resolve a single unique bean for an injection point. The application might have declared multiple implementations itself, or an auto-configuration lacked a suitable back-off condition.

The fix depends on the design:

- Inspect which beans are actually registered.
- Use **@Qualifier** if the caller requires a specific implementation.
- Use **@Primary** if there is a meaningful default implementation.
- Check the conditions of the relevant auto-configuration if an unexpected bean is present.

Do not randomly disable an auto-configuration just to eliminate one bean if the application still needs other components from that configuration.

### 13.5. "Added a Starter and Now the Application Won't Start"

Adding a starter can alter the classpath and cause previously unsatisfied conditions to become satisfied. A new auto-configuration might begin creating beans or require environment settings the application has not prepared yet.

For example, adding data-related libraries can prompt Boot to evaluate DataSource/JPA configurations while URL, driver, or credentials remain incomplete.

Investigation workflow:

1. Read the **cause chain** in the startup error.
2. Identify the relevant auto-configuration.
3. Compare resolved dependencies before and after the change.
4. Identify which condition changed its outcome.
5. Complete the configuration, adjust dependencies, or exclude only what is genuinely unneeded.

### 13.6. "Changed a Property, Yet Behavior Didn't Change"

The property may be loaded from another source with higher precedence, the active profile might differ from what you expect, the property name might have a typo, or the condition annotation might not check that specific name/value.

Also, if you edit a file on disk after startup without a refresh mechanism, auto-configuration generally **does not re-evaluate**. First verify the property value in the **Environment at context startup** and how the application is being launched.

## 14. Principles When Writing Your Own Library Auto-Configuration

When a team wants to build a shared Spring Boot library, auto-configuration can let consumers get started with just a dependency and a few properties. To keep the library predictable:

1. **Register candidates properly** in AutoConfiguration.imports matching the target Boot version.
2. **Activate features only when required dependencies exist**, using classpath conditions and separating configurations when optional types may be absent.
3. **Provide clear properties**, set sensible defaults, and document toggle conditions.
4. **Back off for application-defined beans** at points where the library allows customization.
5. **Declare ordering** if one configuration depends on the outcome of another auto-configuration.
6. **Keep auto-configurations out of consumers' regular component-scan scope** to prevent unintended discovery.
7. **Do not assume the application is Servlet web** if the library might be used in reactive or non-web contexts.
8. **Place side-effectful behavior in appropriate lifecycle hooks**, rather than turning condition evaluation into business execution.

Auto-configuration is a mechanism for **library integration and defaults**. It does not completely replace module design or application-level business decisions.

### 14.1. Distinguishing Class Presence Conditions from Instantiation Readiness

A configuration can pass **@ConditionalOnClass** and still fail during bean creation because:

- A constructor throws an exception.
- A property is present, yet malformed or invalid.
- A lower-level dependency is missing at runtime.
- An external service is unavailable during bean initialization.
- Two libraries have binary-incompatible versions.

Therefore, **auto-configuration selected** differs from **bean successfully instantiated**.

### 14.2. Do Not Use Auto-Configuration to Mask Required Dependencies

If a library **strictly requires** a service, silently skipping its bean simply because the service is missing can make incomplete setups hard for consumers to notice. Some cases warrant conditions so a module stays completely inactive; other cases warrant a clear startup error or explicit required constraint.

Proper design depends on the library's contract: an **optional** integration should avoid disrupting applications that do not use it; a feature **explicitly enabled by the user** may need to fail loudly if configuration is incomplete.

## 15. Analyzing Three Scenarios

### Scenario A: Adding the Web Starter

An application starts out as a Java command-line app. You add the web starter, create a controller, and run it again.

**Question:** Why did Boot start launching an HTTP server?

**Explanation:** The classpath now contains the appropriate web components; Boot determines the application type and evaluates the corresponding auto-configurations. Those whose conditions pass can set up an embedded server and Spring MVC. Your controller is registered via component scanning and now has an environment to handle requests.

**Note:** This is the coordination of dependency resolution, environment, auto-configuration, and component scanning—not a single annotation acting alone.

### Scenario B: Application Supplies Its Own Bean

The library defines:

~~~java
@Bean
@ConditionalOnMissingBean(GreetingService.class)
GreetingService greetingService() {
    return new GreetingService("Hello");
}
~~~

The application adds:

~~~java
@Bean
GreetingService greetingServiceForApp() {
    return new GreetingService("Hello from app");
}
~~~

**Question:** Will there be two GreetingService beans?

**Explanation:** Under typical auto-configuration design, if the application bean is already known when the condition is evaluated, **@ConditionalOnMissingBean** will skip registering the default bean. Inspect the condition report and bean registration process to confirm the exact runtime outcome.

### Scenario C: Property Does Not Enable the Feature

The library uses:

~~~java
@ConditionalOnProperty(
    prefix = "demo.greeting",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false
)
~~~

The application does not declare **demo.greeting.enabled**.

**Question:** Why does GreetingService not appear?

**Explanation:** Because the property is absent and **matchIfMissing=false**, the condition is not satisfied. To enable the feature, declare the matching property or change the library's default contract. This is not an IoC container bug.

## 16. Misconceptions to Avoid

**"@EnableAutoConfiguration scans every class and turns all of them into beans."**  
No. It uses a list of auto-configuration candidates and a condition system; component scanning is a separate mechanism.

**"Adding a starter enables every auto-configuration inside that starter."**  
No. The classpath is one signal, while properties, beans, web application type, and other conditions can still cause configurations to be skipped.

**"@ConditionalOnClass means a bean already exists."**  
No. A class can exist without any corresponding bean definition.

**"@ConditionalOnMissingBean overrides an existing bean after startup."**  
No. It evaluates conditions during configuration processing and bean registration; it is not a runtime bean replacement mechanism.

**"A positive match proves every bean in the auto-configuration was created."**  
No. There may still be method-level conditions or errors during bean instantiation.

**"A negative match means the application is misconfigured."**  
No. Skipping unneeded configurations is a normal goal of Spring Boot.

**"Excluding an auto-configuration is equivalent to deleting the library from the classpath."**  
No. Exclusions operate on configurations; the dependency graph belongs to the build tool.

**"Editing application.yml at runtime immediately changes condition decisions."**  
Not by default. Conditions are typically evaluated when building the context.

**"Every Spring-managed bean comes from auto-configuration."**  
No. Beans can be defined via **@Bean**, component scanning, imports, other registration mechanisms, or auto-configuration.

**"Spring Boot will automatically fix every missing configuration."**  
No. Auto-configuration supplies sensible defaults when sufficient signals exist; required dependencies, endpoints, external connections, and custom business logic still must be defined by the application.

## 17. Applying This When Reading a Spring Boot Application

When trying to understand why a bean exists or is missing, trace this chain:

~~~text
1. Which dependency provides the relevant class / module?
                     │
                     ▼
2. Is a candidate auto-configuration registered?
                     │
                     ▼
3. Is it excluded via annotation or property?
                     │
                     ▼
4. Which @Conditional... annotations are declared?
                     │
                     ▼
5. What is the state of classpath, properties, web type, and existing beans?
                     │
                     ▼
6. Was the bean definition registered?
                     │
                     ▼
7. Was the bean instantiated successfully when needed?
                     │
                     ▼
8. How does the application consume that bean?
~~~

This chain connects three crucial layers of knowledge: **dependencies and classpath**, **Spring IoC container**, and **Spring Boot auto-configuration**. For diagnostics, the condition evaluation report helps explain the configuration selection step, while stack traces and startup logs help explain failures during bean creation or execution.

## Key Takeaways

**@EnableAutoConfiguration** activates the mechanism allowing Spring Boot to find and evaluate registered auto-configurations. Conditions such as **@ConditionalOnClass**, **@ConditionalOnProperty**, **@ConditionalOnBean**, **@ConditionalOnMissingBean**, and **@ConditionalOnWebApplication** decide which configurations or beans can participate in the application.

Within **@SpringBootApplication**, auto-configuration collaborates with Spring configuration and component scanning, yet fulfills its own distinct role: **providing infrastructure and defaults tailored to the current context**. By understanding conditional selection, you can explain why a bean appears, why Spring Boot backs off for application beans, and why adding a dependency or changing a property can alter how the system starts up.
