# EnvironmentPostProcessor and Its Relationship with Environment Preparation in Spring Boot

## 1. What is Environment, and why prepare it early?

In a Spring Boot application, **Environment** is Spring Framework's interface for looking up configuration by key and identifying active profiles. Instead of having every class read configuration files directly, beans can retrieve data via **Environment**, **@Value**, or binding with **@ConfigurationProperties**. Values originate from many **PropertySources**, such as:

- Command-line arguments like **--server.port=9090**.
- Java system properties like **-Ddemo.mode=production**.
- Operating system environment variables.
- **application.properties** or **application.yml**, including profile-specific configuration.
- Default properties of **SpringApplication**.
- Custom sources added by the application or a library.

**ConfigurableEnvironment** allows modifying the **MutablePropertySources** list, as well as changing certain profile settings according to the proper contract. Each **PropertySource** has its own name and can provide values for a set of keys. When multiple sources share the same key, **the precedence order of PropertySources** determines the effective value.

Certain settings must be present **before Spring creates and refreshes the ApplicationContext**: web application type configuration, initial logging, how config data is loaded, profiles involved in bootstrap, and parameters affecting auto-configuration decisions. Therefore, Spring Boot includes a **prepare Environment** phase before creating business beans.

**EnvironmentPostProcessor** is the extension point dedicated to this early phase. It lets you intervene in the **Environment** while Spring Boot is preparing it, when the ApplicationContext **has not been refreshed yet**.

## 2. What is EnvironmentPostProcessor?

In Spring Boot 3.3, the interface has the fully qualified name:

**org.springframework.boot.env.EnvironmentPostProcessor**

And declares the core method:

~~~java
void postProcessEnvironment(
        ConfigurableEnvironment environment,
        SpringApplication application);
~~~

Meaning of the two parameters:

- **environment:** the Environment currently being prepared by Boot; you can add, replace, reorder, or inspect PropertySources using the **getPropertySources()** API.
- **application:** the SpringApplication instance being bootstrapped; used when you need appropriate bootstrap information/configuration, not a refreshed ApplicationContext.

Examples of valid use cases: supplying default properties from a custom source, normalizing a group of custom settings, adding a PropertySource with a chosen precedence, or integrating a library's early configuration mechanism.

**EnvironmentPostProcessor is not a BeanPostProcessor.** This interface processes the **configuration environment** before normal bean creation. Nor is it a bean fetched from ApplicationContext to execute business logic.

## 3. Where does it sit in the startup sequence?

Conceptual diagram for Spring Boot 3.3:

~~~text
main(String[] args)
       |
       v
SpringApplication.run(args)
       |
       v
Create/select and configure ConfigurableEnvironment
       |
       +--> Load initial sources (system/CLI/defaults...)
       |
       v
ApplicationEnvironmentPreparedEvent is handled
       |
       +--> EnvironmentPostProcessorApplicationListener
       |         |
       |         +--> ConfigDataEnvironmentPostProcessor
       |         |       loads application.properties/yml, profile config...
       |         |
       |         +--> Other EnvironmentPostProcessors
       |                 add/adjust PropertySources in order
       |
       v
Environment has been augmented/prepared
       |
       v
Bind relevant SpringApplication options
       |
       v
Create the corresponding ApplicationContext
       |
       v
Apply ApplicationContextInitializers
       |
       v
Load bean definitions, refresh ApplicationContext
       |
       v
Create beans, dependency injection, lifecycle...
       |
       v
ApplicationRunner / CommandLineRunner
       |
       v
ApplicationReadyEvent
~~~

The diagram omits other callbacks and listeners; it does not claim that every EnvironmentPostProcessor executes in a single uniform step or that all other listeners always run after it. The key point to retain is that **EnvironmentPostProcessorApplicationListener triggers post-processors during the Environment-prepared event handling phase, before refresh**.

### What is already available when the post-processor runs?

Typically available:

- A **ConfigurableEnvironment** being prepared and the PropertySources added up to the current stage.
- **SpringApplication**.
- Special bootstrap mechanisms supported by Spring Boot.
- Classpath, system properties, environment variables, and other initial data.

Must not be assumed to exist:

- A refreshed ApplicationContext.
- Application beans such as **@Service**, **@Repository**, DataSource, or WebClient.Builder.
- Standard dependency injection via **@Autowired** inside EnvironmentPostProcessor.
- Results from **@ConfigurationProperties** beans bound after the container is active.

Therefore, code inside an EnvironmentPostProcessor should work independently of business beans and must not rely on bean instantiation to obtain configuration.

## 4. Relationship with ConfigDataEnvironmentPostProcessor

A very important component of Spring Boot is **ConfigDataEnvironmentPostProcessor**. This is also an EnvironmentPostProcessor, responsible for loading and applying **ConfigData**, including configuration in **application.properties**, **application.yml**, profile-specific files, and Boot-supported imported sources.

This means:

- Not all EnvironmentPostProcessors see the exact same set of properties at every moment.
- A processor running **before ConfigDataEnvironmentPostProcessor** may not yet see values from the application.yml file about to be loaded.
- A processor running **after ConfigDataEnvironmentPostProcessor** can read values already configured from ConfigData.
- If you want to influence the selection of **spring.config.location**, **spring.config.name**, or loading config locations by profile, execution order is part of the design; adding a property **after ConfigData has already been processed** will not automatically make Boot reload files under the newly changed name/location.

This is why Spring Boot supports **Ordered** and **@Order** on EnvironmentPostProcessor.

~~~java
public final class DemoProcessor
        implements EnvironmentPostProcessor, Ordered {

    @Override
    public int getOrder() {
        return Ordered.LOWEST_PRECEDENCE;
    }

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application) {
        // Custom Environment logic.
    }
}
~~~

The snippet above is an **illustrative skeleton**, not a standalone runnable file (it needs a package and imports). With **Ordered.LOWEST_PRECEDENCE**, the example is designed to run late, after ConfigDataEnvironmentPostProcessor under default ordering. You should not hardcode Boot's internal order numbers unnecessarily; when relative comparison is needed, refer to **ConfigDataEnvironmentPostProcessor.ORDER** in the version being used.

**Be careful:** processor invocation order and configuration source precedence order are **two different axes**. A processor running last can still add a PropertySource at the front of the list, making its values override other sources. Do not confuse "runs later" with "weaker property".

## 5. Complete Java 17+ example: adding default properties during Environment preparation

Example goals:

1. Register an EnvironmentPostProcessor using Spring Boot's mechanism.
2. Add a PropertySource containing default values.
3. Demonstrate that **application.properties** overrides default properties.
4. Inspect final values using ApplicationRunner once Spring has started.

This example targets **Spring Boot 3.3.x and Java 17+**. Create a Maven project via Spring Initializr, group **com.example**, artifact **demo**, package **com.example.demo**, dependency **Spring Boot Starter**. Spring Web is not needed because this is a non-web application.

### 5.1. EnvironmentPostProcessor file

Create **src/main/java/com/example/demo/bootstrap/LabEnvironmentPostProcessor.java**:

~~~java
package com.example.demo.bootstrap;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.Ordered;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;

public final class LabEnvironmentPostProcessor
        implements EnvironmentPostProcessor, Ordered {

    private static final String SOURCE_NAME = "labBootstrapDefaults";

    @Override
    public int getOrder() {
        // Run late, after ConfigData has normally been loaded.
        return Ordered.LOWEST_PRECEDENCE;
    }

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application) {

        // Avoid adding a duplicate PropertySource with the same name.
        if (environment.getPropertySources().contains(SOURCE_NAME)) {
            return;
        }

        Map<String, Object> defaults = Map.of(
                "demo.message", "hello-from-environment-post-processor",
                "demo.mode", "safe-default");

        // addLast: low priority; config files/CLI can override.
        environment.getPropertySources().addLast(
                new MapPropertySource(SOURCE_NAME, defaults));
    }
}
~~~

**Why choose MapPropertySource and addLast?**

**MapPropertySource** is a PropertySource backed by a map of key/value pairs. **MutablePropertySources.addLast(...)** adds this source **at a lower priority position** than existing sources. This is the right approach when a post-processor only supplies **fallback defaults**: deployers can still configure values in application.properties, environment variables, and CLI arguments.

Checking **contains(SOURCE_NAME)** in the example avoids adding a source with the same name if the code is invoked repeatedly in test/integration scenarios. The logic still modifies no business beans.

### 5.2. Registering via spring.factories

Create **src/main/resources/META-INF/spring.factories**:

~~~properties
org.springframework.boot.env.EnvironmentPostProcessor=com.example.demo.bootstrap.LabEnvironmentPostProcessor
~~~

This step is **mandatory** for the example on Spring Boot 3.3. Boot uses the factories mechanism to locate EnvironmentPostProcessors on the dependency/application classpath. Simply adding **@Component** to the class or leaving the class in a component-scanned package **is not enough** for the callback to run in the Environment phase.

The path and class name must match exactly:

- **META-INF** is a subdirectory inside **src/main/resources**.
- The file must be named **spring.factories**.
- The key is the fully qualified name of **EnvironmentPostProcessor** in Spring Boot 3.3.
- The value is the fully qualified name of the implementation class, including package.

In a normal JAR build, this resource must be present on the classpath. If a library has multiple processors, factories can list multiple implementations using properties syntax; execution order should not depend on listing order and should instead be defined using Ordered or @Order.

### 5.3. Application reading the values after startup

Create **src/main/java/com/example/demo/EnvironmentDemoApplication.java**:

~~~java
package com.example.demo;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class EnvironmentDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(EnvironmentDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner printEnvironment(Environment environment) {
        return args -> {
            System.out.println("demo.message="
                    + environment.getProperty("demo.message"));
            System.out.println("demo.mode="
                    + environment.getProperty("demo.mode"));
        };
    }
}
~~~

**ApplicationRunner** executes after the context has refreshed, making it a convenient place to **observe** effective configuration. Meanwhile, **LabEnvironmentPostProcessor** was called much earlier, while Spring Boot prepared the Environment.

### 5.4. Application configuration file

Create **src/main/resources/application.properties**:

~~~properties
demo.mode=from-application-properties
~~~

Do not declare **demo.message** in this file. Thus:

- **demo.message** appears only in the processor's default PropertySource, so its fallback value is read.
- **demo.mode** exists in both the processor's PropertySource and application.properties; the configuration file has higher priority than an addLast source, so the effective value comes from the file.

### 5.5. Running the program and results

From the root directory of the Initializr-generated Maven project:

~~~bash
# Linux/macOS
./mvnw spring-boot:run

# Windows PowerShell/cmd:
# .\mvnw.cmd spring-boot:run
~~~

Lines printed by ApplicationRunner:

~~~text
demo.message=hello-from-environment-post-processor
demo.mode=from-application-properties
~~~

These are **the two expected output lines of the program**, not the entire stdout. Spring Boot and Maven may print other logs/banners. The output assumes no other environment variables, JVM system properties, or CLI arguments override these two keys.

If the application reports that **demo.message** has no value, check first that **META-INF/spring.factories** was packaged properly, the package/class name in the value is exact, and the processor class is on the runtime classpath.

### 5.6. Testing overrides via command-line arguments

If Initializr used artifact **demo**, version **0.0.1-SNAPSHOT**, build the JAR:

~~~bash
./mvnw package
~~~

And run:

~~~bash
java -jar target/demo-0.0.1-SNAPSHOT.jar --demo.message=from-command-line
~~~

If the artifact/version differs, substitute the actual JAR filename in the target directory. Under Spring Boot's default precedence order, command-line properties beat default values added with **addLast**. The lines printed by the program:

~~~text
demo.message=from-command-line
demo.mode=from-application-properties
~~~

Three interactions with **demo.message** across different phases illustrate the exact responsibilities: EnvironmentPostProcessor supplies the source early; Environment resolves the final value based on source precedence; beans reading **Environment** after refresh observe the effective result.

## 6. addFirst, addLast, and PropertySource precedence

The same processor can produce very different behavior solely by choosing insertion position:

~~~java
// Default, normally allowing other sources to override:
environment.getPropertySources().addLast(
        new MapPropertySource("lowPriorityDefaults", defaults));

// Strong override (think carefully before using):
environment.getPropertySources().addFirst(
        new MapPropertySource("highPriorityOverrides", overrides));
~~~

This is an **illustrative snippet**: it assumes **defaults** and **overrides** are already valid maps.

- **addLast:** the added source goes at the back, having lower priority than preceding sources.
- **addFirst:** the added source goes at the front, having highest priority at the time of insertion; it can override config files, system properties, or CLI arguments already in the list.
- **addBefore(name, source)** and **addAfter(name, source)**: insert relative to a specific source; requires knowing the exact name of an existing source.
- **replace(name, source):** completely replaces a source with a known name; you must understand the impact on the keys it provides.

**Do not choose addFirst reflexively** just to be sure your code "takes effect". Doing so can prevent operators from adjusting settings via environment variables or CLI, or accidentally replace configuration that ought to remain controllable.

### When multiple keys collide

Suppose we have:

~~~text
application.properties       demo.mode=prod
systemEnvironment            DEMO_MODE=staging
labBootstrapDefaults         demo.mode=safe-default
~~~

The effective value depends on PropertySource position and the key-handling mechanism of each source. Under typical ordering and without higher-priority sources, **systemEnvironment** can override the config file, while **labBootstrapDefaults** at the end serves only as a fallback. This example illustrates precedence principles; do not treat the abbreviated list above as the complete PropertySource order for every application.

### Processor execution order vs. property precedence

Two independent questions:

1. Which processor **runs first**? Decided via **Ordered/@Order**.
2. After all processors finish, which PropertySource **wins for the same key**? Decided by **position** in MutablePropertySources, together with relevant lookup/relaxed-binding rules.

A processor running after ConfigData that calls **addFirst** can override even values from ConfigData. A processor running before ConfigData that adds a fallback source can be overridden by ConfigData afterward. Design both axes explicitly.

## 7. Why run before refresh instead of using @Bean?

Different extension points have very different timing and purposes:

| Mechanism | Execution milestone | Primary target modified |
| --- | --- | --- |
| **EnvironmentPostProcessor** | Environment preparation phase, before refresh | PropertySources, profiles, and early configuration data |
| **ApplicationContextInitializer** | After context is created, before refresh | Unrefreshed ApplicationContext, environment, and initial setup |
| **BeanDefinitionRegistryPostProcessor** | During refresh phase, before application bean instantiation | Registry/BeanDefinitions |
| **BeanFactoryPostProcessor** | During refresh, before singleton application initialization | BeanFactory and bean metadata |
| **BeanPostProcessor** | As each bean is instantiated | Bean instances, wrappers/proxies, and lifecycle |
| **@Bean / @Component** | Definitions processed during context startup; instantiated per scope/lazy | Application components |
| **ApplicationRunner** | After context refresh succeeds | Post-startup tasks; observation/business initialization as needed |

For example: if **logging.\*** or **spring.main.\*** settings must be read by Spring Boot before context refresh, adding a PropertySource via **@PropertySource** on **@Configuration** may be too late. The Spring Boot Reference notes that PropertySources from @PropertySource are only added during the refresh phase, after some early properties have already been read.

EnvironmentPostProcessor exists to intervene in Environment at an earlier milestone. Even so, do not assume it can alter **every setting from millisecond zero**; values already consumed by Boot or another listener before the processor callback cannot be automatically "rolled back".

**ApplicationContextInitializer** differs from EnvironmentPostProcessor in that an initializer already holds a reference to the context to configure it, though still before refresh. If the requirement is modifying context structure rather than only PropertySources, an initializer may fit better.

## 8. Processor registration and instantiation mechanism

In Spring Boot 3.3, **EnvironmentPostProcessorApplicationListener** is the listener responsible for triggering EnvironmentPostProcessors registered via **spring.factories**. This explains why the interface is named "PostProcessor" yet its activation mechanism **differs** from bean discovery after component scanning.

### Do not use standard bean-style constructor injection

Processors are instantiated by Boot during the bootstrap phase. Because the Spring ApplicationContext is not ready yet, do not write constructors requesting **@Service** or **@Repository**.

Spring Boot 2.4+ supports special constructor parameters for EnvironmentPostProcessor, including:

- **DeferredLogFactory:** creates a logger that defers log output until logging configuration is fully prepared.
- **ConfigurableBootstrapContext** (and certain related bootstrap context types): shares bootstrap objects across startup steps without needing a refreshed ApplicationContext.

Example illustrating a specialized constructor:

~~~java
public SampleProcessor(DeferredLogFactory logFactory) {
    this.log = logFactory.getLog(getClass());
}
~~~

This is an **illustrative code fragment** for a processor with a **log** field and corresponding imports, not a complete class. Using a deferred logger is helpful because the logging system may not have applied all log settings yet when the callback runs. Do not use **System.out** to print secrets or sensitive data merely because you are running in an early phase.

### Wrong spring.factories location

If the file is placed under **src/main/java/META-INF** or only in the test directory, the runtime JAR may not contain it. The proper directory in a standard Maven layout is **src/main/resources/META-INF**. A class implementing the interface without being registered in factories will not be called automatically just because it compiles.

## 9. Relationship with profiles and config loading

Active profiles affect configuration files like **application-dev.properties** and profile-conditional beans. Because ConfigDataEnvironmentPostProcessor processes ConfigData during the Environment phase, distinguish two needs:

**A. Wanting to read already-loaded configuration before adding defaults/normalizing a group of keys.** Running the processor **after ConfigData** usually makes sense; for example, using **Ordered.LOWEST_PRECEDENCE**.

**B. Wanting to change options that decide which config files are loaded or which profiles are evaluated during ConfigData.** You must design the component to intervene **early enough**, properly ordered relative to ConfigData. Simply adding **spring.profiles.active** or **spring.config.location** after ConfigData has already run usually **does not make Boot reload** config files under the new choices. For file/profile selection configuration, prefer sources Boot reads early such as CLI, environment variables, or system properties; if you need a custom config location resolver, consider the proper ConfigData extension point rather than late manipulation in a post-processor.

A processor can read:

~~~java
String[] activeProfiles = environment.getActiveProfiles();
String value = environment.getProperty("demo.mode");
~~~

However, the observed data depends on **when** the processor runs in the chain. Before ConfigData, many profile-specific values have not been loaded yet; after ConfigData, values are typically present, though adding profiles may be too late to affect the completed load pass.

## 10. When should you use EnvironmentPostProcessor?

**Consider using it when:**

- Building a library or starter that must add a configuration source **before application beans are created**.
- Needing to supply a set of fallback properties with well-defined precedence.
- Needing to process or transform early bootstrap values on Environment.
- Integrating a bootstrap-level configuration loading mechanism that standard application.yml files cannot express adequately.

**Usually unnecessary when:**

- Simply declaring **server.port**, datasource URLs, timeouts, or profiles; application.properties/yml or environment variables are simpler.
- Mapping a typed group of properties into a bean; **@ConfigurationProperties** is more appropriate.
- Running logic after startup completes; use **ApplicationRunner**, **CommandLineRunner**, or appropriate lifecycle events.
- Modifying bean definitions or bean instantiation; look at **BeanDefinitionRegistryPostProcessor**, **BeanFactoryPostProcessor**, or **BeanPostProcessor**.
- Automatically reloading config when files change while the app runs; EPP is **not a file watcher** and does not automatically rerun after startup.

Avoid performing slow network calls, uncontrolled blocking, or hard-to-reverse side effects inside a processor: the callback lies on the application's critical startup path. If you must read external sources, enforce timeouts, error policies, and clear security boundaries around configuration data.

## 11. Common errors and troubleshooting

| Symptom | Common cause | How to inspect |
| --- | --- | --- |
| Processor is never called | Missing or incorrect **META-INF/spring.factories** | Check path under resources, key, and fully qualified class name |
| Used **@Component** but callback does not run early | Component scan is not the EPP registration mechanism | Register properly via factories |
| Processor requests **@Autowired MyService** but bean is missing | ApplicationContext has not refreshed yet | Do not depend on business beans in early phase |
| Cannot read properties from application.yml | Processor ran before ConfigData | Check Ordered order and Boot version used |
| Added **spring.config.location** but files did not reload | ConfigData phase already passed | Configure file selection from an early enough source |
| Config file cannot override defaults | Processor called **addFirst** or inserted source too high | Choose **addLast** for fallback defaults |
| Retrieved value differs from expectation | Multiple PropertySources share the key | Check order, CLI/system/env sources, and key binding |
| Processor runs in tests but not production | Class or spring.factories only on test classpath | Inspect JAR structure and resource locations |
| Startup is too slow | Processor performs expensive I/O/network calls | Add timeouts, reduce I/O, or move work out of startup |
| Logs inside processor do not respect configured log level | Logging has not been fully prepared yet | Check DeferredLogFactory and startup order |
| Added property expecting existing beans to pick up new value automatically | Many beans/configs already bound at startup | Design explicit dynamic refresh or restart |

For diagnostics, Spring Boot Actuator (when installed and properly secured) can expose **env** and **configprops** endpoints. They can help identify configuration sources and bound values, while avoiding secret exposure. Do not expose sensitive endpoints publicly just for debugging.

## 12. Comprehension exercises

**Question 1.** A class implementing EnvironmentPostProcessor is annotated with **@Component** but not declared in spring.factories. In Boot 3.3, should you expect it to run automatically during Environment preparation?

**Question 2.** With a processor using **addLast** to supply **demo.mode=safe-default**, while application.properties has **demo.mode=from-file**, what value does Environment return after startup?

**Question 3.** Why is **Ordered.LOWEST_PRECEDENCE** useful when a processor wants to read properties already loaded by ConfigData?

**Question 4.** Suppose a processor runs after ConfigData and then sets **spring.config.location**. Can you assume Boot will reload files from the new location?

**Question 5.** Why might **@PropertySource** on a configuration class be too late if the goal is to affect certain logging or spring.main.* values?

**Question 6.** To add default values while allowing command-line arguments to override them, should you use **addFirst** or **addLast**? Does changing processor execution order automatically change property precedence?

**Suggested answers:** (1) no, it must be registered via the EPP mechanism; (2) from-file because file sources take precedence over fallback sources; (3) ConfigData processor gets a chance to run first; (4) no, the decision must be made before the file-loading phase; (5) because @PropertySource is only added during context refresh, after some early values have already been read; (6) addLast, and execution order vs. PropertySource precedence are two separate mechanisms.

## 13. Takeaways

- **EnvironmentPostProcessor** is Spring Boot's hook for modifying **ConfigurableEnvironment before ApplicationContext.refresh()**.
- **EnvironmentPostProcessorApplicationListener** invokes implementations registered via **META-INF/spring.factories** during Boot 3.3's bootstrap flow.
- **ConfigDataEnvironmentPostProcessor** is itself an EPP. If you want to inspect already-loaded application.properties/yml files, understand execution order; if you want to decide config locations or profiles early, you cannot arbitrarily run after ConfigData.
- **Ordered/@Order** decides **when the processor runs**; **addFirst/addLast** decides **where the property source sits**. These two are independent.
- **EPP is not a normal Spring bean**; do not use it to inject business services, run business logic, or dynamically refresh configuration by itself.
- For simple default values, **addLast** preserves override capability for config files, environment variables, and CLI.

### Official documentation (Spring Boot 3.3)

1. EnvironmentPostProcessor JavaDoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/env/EnvironmentPostProcessor.html
2. EnvironmentPostProcessorApplicationListener JavaDoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/env/EnvironmentPostProcessorApplicationListener.html
3. ConfigDataEnvironmentPostProcessor JavaDoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/config/ConfigDataEnvironmentPostProcessor.html
4. Externalized Configuration, PropertySource order and @PropertySource: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
5. SpringApplication and startup lifecycle: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html

The Java examples in this article are written for **Java 17+ / Spring Boot 3.3.x**. For Spring Boot 4.x and other major versions, check that version's JavaDoc and extension registration mechanism before reusing the source code verbatim.