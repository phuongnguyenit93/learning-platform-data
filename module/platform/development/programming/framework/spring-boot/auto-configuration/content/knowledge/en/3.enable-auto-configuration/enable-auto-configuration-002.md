# How Does @EnableAutoConfiguration Activate Configuration Selection?

## 1. What Gets Activated Is a Selection Mechanism, Not Every Configuration

When **@EnableAutoConfiguration** is added to a Spring configuration class, the application allows Spring Boot to **discover candidate auto-configuration classes, apply exclusion rules, evaluate conditions, and register matching bean definitions**. This annotation does not automatically create every bean in the entire Spring Boot library. The final set of beans also depends on the **classpath**, **Environment and properties**, **application type**, **user-defined beans**, other conditions, and whether instantiation actually succeeds.

In a typical Spring Boot project, developers usually do not write this annotation directly, because **@SpringBootApplication** already includes **@EnableAutoConfiguration**.

Minimal example:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MyApplication {
    public static void main(String[] args) {
        SpringApplication.run(MyApplication.class, args);
    }
}
~~~

This snippet illustrates how to enable it; it is not a standalone file with a package or Maven structure. It is **@SpringBootApplication** that activates auto-configuration; there is no need to add **@EnableAutoConfiguration** a second time on the same application.

It is important to distinguish three events:

1. **Mechanism enabled**: **@EnableAutoConfiguration** is present directly or indirectly.
2. **Configuration branch selected**: a candidate is not excluded and its relevant conditions pass.
3. **Bean instance exists**: the bean definition was selected and the container subsequently created the object according to its lifecycle/scope.

These three events are not equivalent. Auto-configuration may be enabled yet no DataSource exists if the environment does not meet the conditions. A configuration may be selected yet a lazy bean inside it has not been instantiated yet.

## 2. Structure of the Annotation and Related Annotations

In Spring Boot 3.x, **@EnableAutoConfiguration** is built on two key links:

- **@AutoConfigurationPackage**: registers the default package used by certain auto-configured mechanisms such as discovering entities or Spring Data repositories. This package is typically taken from the package containing the class annotated with **@EnableAutoConfiguration**. It is **not** a command to scan every component across all libraries.
- **@Import(AutoConfigurationImportSelector.class)**: brings the auto-configuration selector into Spring's configuration processing. This is the piece directly involved in discovering, filtering, and importing auto-configuration candidates.

Conceptual structure (with target/retention/documentation annotations simplified):

~~~java
@AutoConfigurationPackage
@Import(AutoConfigurationImportSelector.class)
public @interface EnableAutoConfiguration {
    Class<?>[] exclude() default {};
    String[] excludeName() default {};
}
~~~

**This is only an explanatory model**, not the complete annotation source code to copy and redefine. The two attributes **exclude** and **excludeName** allow an application to remove unwanted configurations from the candidate list.

**@SpringBootApplication** combines three main roles:

| Role | Underlying Annotation | Meaning |
| --- | --- | --- |
| Startup configuration class | **@SpringBootConfiguration** | The application class can declare beans and import configurations. |
| Application component scanning | **@ComponentScan** | Finds components in the specified packages or the default root package. |
| Auto-configuration | **@EnableAutoConfiguration** | Imports candidate auto-configurations from metadata, then evaluates conditions. |

"Application components being scanned" is different from "auto-configuration being loaded". A library can carry an auto-configuration outside the application's scan packages and still be discovered by Boot via imports metadata. Conversely, a class annotated with **@AutoConfiguration** that is not registered through the proper discovery mechanism is not automatically loaded just because that annotation is present in the source file.

You can also use the explicit annotations on the main configuration:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.context.annotation.ComponentScan;

@SpringBootConfiguration
@EnableAutoConfiguration
@ComponentScan
public class ExplicitApplication {
    public static void main(String[] args) {
        SpringApplication.run(ExplicitApplication.class, args);
    }
}
~~~

This is an illustrative alternative equivalent in the three core roles. In practice, prefer **@SpringBootApplication** when there are no special configuration requirements. Do not declare both application configuration classes from the two examples as entry points of the same project without clear design intent.

### 2.1. What Is the Significance of the Main Class's Package?

Placing the application class in a root package, such as **dev.example.app**, determines the default **@ComponentScan** scope. At the same time, **@AutoConfigurationPackage** identifies the default package used by auto-configured features that search for entities/repositories. The **scanBasePackages** attribute of **@SpringBootApplication** adjusts the component scan scope, but it does not automatically change every package used by entity/repository scanning. When you want to change those specialized scopes, check the dedicated annotations and configuration of that feature.

Do not confuse "the application's **@Service** is not scanned" with "**@EnableAutoConfiguration** is not working"; the two discovery paths are different.

## 3. Processing Chain from Annotation to the Selected Set of Configurations

Spring Framework processes **@Configuration** classes during ApplicationContext refresh. During that process, **@Import(AutoConfigurationImportSelector.class)** lets Spring Boot participate in configuration selection. **AutoConfigurationImportSelector** is a **DeferredImportSelector**: auto-configuration imports are processed in a deferred phase, giving configurations and bean definitions explicitly declared by the application a chance to be processed first. This supports the "back off" mechanism when the application has already provided its own bean.

Conceptual diagram:

~~~text
@SpringBootApplication
        |
        v
@EnableAutoConfiguration
        |
        +--> @AutoConfigurationPackage
        |         |
        |         +--> Register default package for certain features
        |
        +--> @Import(AutoConfigurationImportSelector.class)
                  |
                  v
       Read candidate auto-configuration list from JARs
                  |
                  v
       Deduplicate and apply exclusion configuration
                  |
                  v
       Filter candidates by matching conditions/metadata
                  |
                  v
       Import eligible @AutoConfiguration classes for processing
                  |
                  v
       Evaluate conditions at class level and per @Bean
                  |
                  +--> Not met: skip corresponding class/bean
                  |
                  +--> Met: register bean definition
                                      |
                                      v
                    Spring container creates instance when needed
~~~

The diagram simplifies the condition evaluation and registration passes. It does not mean every condition is evaluated strictly once in a single place; in practice, some conditions may be evaluated during configuration parsing and others during bean registration.

### 3.1. Finding Candidates in JARs

In Spring Boot 3.x, libraries register auto-configurations using a resource with the exact name:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Its content consists of fully qualified class names, one candidate per line, for example:

~~~text
dev.example.autoconfig.GreetingAutoConfiguration
dev.example.autoconfig.OptionalFeatureAutoConfiguration
~~~

The **.imports** file name is part of the candidate discovery contract. The classes can reside in the application JAR or in library JARs. Spring Boot reads this resource from the runtime classpath; the modules/libraries present determine which resource files can be read.

**Version note:** With Spring Boot 3.x, the imports mechanism is the way to register auto-configuration candidates. Documentation for older Spring Boot versions showed registration under the **EnableAutoConfiguration** key in **META-INF/spring.factories**. Do not use that older example as the new auto-configuration registration format for Spring Boot 3.x. The **spring.factories** resource still serves other SPI purposes; the two do not conflict.

Merely listing a class in imports turns it into a **candidate**; it does not guarantee its beans will be created. **@AutoConfiguration** and appropriate conditions are still needed. Spring Boot generally recommends placing auto-configurations in a separate package so the application's component scan does not pick them up as ordinary components.

### 3.2. From Candidate to Processed Configuration Class

Selection can be broken down into the following decision categories:

- **Discoverable:** the imports resource is present on the classpath and lists the exact class name.
- **Not excluded:** the class is not in **exclude**, **excludeName**, or **spring.autoconfigure.exclude**.
- **Meets class/property/web/resource/bean conditions:** conditional annotations on the auto-configuration class or a nested configuration can cause Spring to skip that class.
- **Bean method eligible:** even when the auto-configuration class is processed, a specific **@Bean** can still be skipped due to **@ConditionalOnMissingBean**, **@ConditionalOnProperty**, or another condition.
- **Instantiation succeeds:** after the definition is registered, dependencies, constructors, init callbacks, and real resources must still work.

"Candidate present in imports", "positive match in report", "definition registered", and "instance created" are distinct states.

### 3.3. Role of Metadata and Auto-Configuration Ordering

Spring Boot can use pre-generated condition metadata, such as **META-INF/spring-autoconfigure-metadata.properties**, to filter out obviously ineligible candidates early, reducing startup overhead. Optimization metadata **does not replace** the **AutoConfiguration.imports** file as the candidate list.

When there are multiple auto-configurations, you can guide processing order using **@AutoConfiguration(after = ...)**, **@AutoConfiguration(before = ...)**, or dedicated auto-configuration ordering annotations. This ordering mainly affects the **order in which configurations are processed / bean definitions are registered**, which is especially important for conditions checking existing beans. It **does not guarantee** the constructor invocation order of every bean instance; dependencies and lifecycle determine the actual instantiation order.

## 4. Conditions That Decide Whether Auto-Configuration Is Applied

Common conditional annotations:

| Condition | Signal Evaluated | Interpretation |
| --- | --- | --- |
| **@ConditionalOnClass** | Class on runtime classpath | Process the branch only when the required library is present. |
| **@ConditionalOnMissingClass** | Class absent from classpath | Select an alternative branch when a library is missing. |
| **@ConditionalOnProperty** | Value of a property in Environment | Enable/disable a branch based on the final property value Spring reads. |
| **@ConditionalOnBean** | Matching bean already exists in the evaluated context | Depends on another configuration or service already being registered. |
| **@ConditionalOnMissingBean** | No matching bean exists yet | Allows auto-configuration to provide a default when the user has not declared one. |
| **@ConditionalOnWebApplication** | Web environment type | Select configuration intended for servlet or reactive contexts as required. |
| **@ConditionalOnResource** | Required resource | Select configuration only when the specified resource is present. |

With the condition **@ConditionalOnProperty(prefix = "demo.greeting", name = "enabled", havingValue = "true", matchIfMissing = true)**:

- **demo.greeting.enabled=true**: condition passes.
- **demo.greeting.enabled=false**: condition fails.
- Property absent: condition passes because **matchIfMissing=true**.
- If a required class for the configuration is absent, a matching property alone is still not enough to activate the branch.

Not every property containing **enabled** has this same default; you must inspect the annotations and documentation of each configuration.

### 4.1. How Do User Beans Cause Defaults to Back Off?

Many auto-configurations use **@ConditionalOnMissingBean**. When the application defines a matching bean itself, the default branch carrying this condition **does not register a duplicate-function bean**. This is how Boot prioritizes user configuration without requiring you to disable all auto-configuration.

Illustrative example, not a standalone program:

~~~java
@AutoConfiguration
@ConditionalOnClass(PaymentClient.class)
class PaymentClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(PaymentClient.class)
    PaymentClient defaultPaymentClient() {
        return new PaymentClient();
    }
}
~~~

**PaymentClient** here is a hypothetical type for explanation. If the class and other conditions match, yet the application has already defined a **PaymentClient** bean, the default bean is not registered. This does not depend on whether the user bean's constructor has already run; the container can inspect the bean definitions already processed.

**Ordering warning:** **@ConditionalOnBean** and **@ConditionalOnMissingBean** conditions rely on definitions already processed at evaluation time. Spring Boot recommends placing them in auto-configuration classes rather than overusing them in ordinary application configuration, because auto-configuration is processed after user-declared definitions.

**Not every @Bean has @ConditionalOnMissingBean.** If a configuration intentionally provides multiple beans or lacks this guard, adding a bean of the same type can lead to multiple beans and injection conflicts; never assume Boot always backs off automatically.

## 5. Complete Example: Observing Enabled Auto-Configuration and Bean Selection

The example uses **Java 21**, **Maven 3.9+**, and **Spring Boot 3.3.13**. We will write a small auto-configuration named **GreetingAutoConfiguration** and register it using an imports file. Then we run the application to compare four states:

1. Conditions met: creates the default **GreetingService**.
2. Property disabled: does not create the default.
3. User bean present: default backs off.
4. Whole auto-configuration class excluded: not applied even though other conditions could match.

The application is designed to print a single output line from the program on each run. Messages from Maven or external tools are not part of the application code's stdout.

### 5.1. Source Structure

~~~text
enable-auto-demo/
├── pom.xml
└── src/main/
    ├── java/dev/academy/
    │   ├── api/GreetingService.java
    │   ├── autoconfig/GreetingAutoConfiguration.java
    │   └── app/
    │       ├── DemoApplication.java
    │       └── UserGreetingConfiguration.java
    └── resources/
        ├── application.properties
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Placing the main class in **dev.academy.app** and the auto-configuration in **dev.academy.autoconfig** illustrates this point: the auto-configuration class **lies outside the app's default component scan**, yet is still imported from Boot metadata. Do not put **@Component** or **@ComponentScan** on the auto-configuration class.

**pom.xml**

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

    <groupId>dev.academy</groupId>
    <artifactId>enable-auto-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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

**src/main/java/dev/academy/api/GreetingService.java**

~~~java
package dev.academy.api;

@FunctionalInterface
public interface GreetingService {
    String greet(String name);
}
~~~

**src/main/java/dev/academy/autoconfig/GreetingAutoConfiguration.java**

~~~java
package dev.academy.autoconfig;

import dev.academy.api.GreetingService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(GreetingService.class)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    @ConditionalOnProperty(
        prefix = "demo.greeting",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
    )
    GreetingService defaultGreetingService() {
        return name -> "Auto: " + name;
    }
}
~~~

How to read it:

- **@AutoConfiguration** marks this as a Spring Boot auto-configuration class.
- **@ConditionalOnClass(GreetingService.class)** requires the API to be on the classpath. In the sample project the API is defined directly, so this condition is always true. In a real library, an optional dependency may determine the class's presence.
- **@ConditionalOnMissingBean(GreetingService.class)** yields if the user has already provided a matching bean.
- **@ConditionalOnProperty** disables the default bean when **demo.greeting.enabled=false**, but allows it when the property is undeclared.
- The **@Bean** method is selected only when the relevant conditions pass; selecting a bean definition does not mean the factory method has already executed right at that moment.

**src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**

~~~text
dev.academy.autoconfig.GreetingAutoConfiguration
~~~

This file is **mandatory** for the example: Boot needs to know which class is an auto-configuration candidate. Having only **@AutoConfiguration** in the source without the imports file would not allow the example to demonstrate the selector loading a class outside component scan.

**src/main/java/dev/academy/app/DemoApplication.java**

~~~java
package dev.academy.app;

import dev.academy.api.GreetingService;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    ApplicationRunner showSelectedGreeting(
            ObjectProvider<GreetingService> greetings) {
        return args -> {
            GreetingService service = greetings.getIfAvailable();
            System.out.println(service == null
                ? "selected=<none>"
                : "selected=" + service.greet("Mai"));
        };
    }
}
~~~

**ObjectProvider** allows the sample to keep running when GreetingService is intentionally absent. Do not inject a required GreetingService directly into the main class's constructor, because the cases where the property is disabled or the whole auto-configuration is excluded would fail startup due to a missing bean.

**src/main/java/dev/academy/app/UserGreetingConfiguration.java**

~~~java
package dev.academy.app;

import dev.academy.api.GreetingService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
@Profile("custom")
public class UserGreetingConfiguration {

    @Bean
    GreetingService userGreetingService() {
        return name -> "User: " + name;
    }
}
~~~

The user bean is registered only when the **custom** profile is active; at that time **@ConditionalOnMissingBean(GreetingService.class)** on the default configuration fails to match.

**src/main/resources/application.properties**

~~~properties
spring.main.banner-mode=off
logging.level.root=OFF
~~~

This logging line keeps the example output clean. To view the condition report in the diagnostics section, you need to re-enable logging using appropriate arguments.

### 5.2. Building and Testing the Four Branches

In the **enable-auto-demo** directory, using JDK 21 and Maven:

~~~bash
mvn -q -DskipTests package
~~~

**Case A: default auto-configuration is selected**

~~~bash
java -jar target/enable-auto-demo-0.0.1-SNAPSHOT.jar
~~~

Line printed by the application:

~~~text
selected=Auto: Mai
~~~

**Why?** **@SpringBootApplication** enables auto-configuration; imports contains **GreetingAutoConfiguration**; the **GreetingService** class is present; there is no user bean in the default profile; the absent enabled property is allowed by **matchIfMissing=true**. Spring registers the definition and creates the default instance when the runner needs it.

**Case B: property eliminates the default bean**

~~~bash
java -jar target/enable-auto-demo-0.0.1-SNAPSHOT.jar --demo.greeting.enabled=false
~~~

Stdout:

~~~text
selected=<none>
~~~

**Why?** The GreetingAutoConfiguration class is still a candidate and can be processed, but the property condition on the **@Bean** method fails. There is no default GreetingService. This **differs** from excluding the entire auto-configuration class.

**Case C: user bean takes precedence**

~~~bash
java -jar target/enable-auto-demo-0.0.1-SNAPSHOT.jar --spring.profiles.active=custom
~~~

Stdout:

~~~text
selected=User: Mai
~~~

**Why?** The custom profile registers **userGreetingService**; the **@ConditionalOnMissingBean** condition on the default method fails. It is not that Spring Boot uses **@Primary** to choose between two coexisting beans: in this case the default bean is not registered at all.

**Case D: excluding the auto-configuration class**

~~~bash
java -jar target/enable-auto-demo-0.0.1-SNAPSHOT.jar --spring.autoconfigure.exclude=dev.academy.autoconfig.GreetingAutoConfiguration
~~~

Stdout:

~~~text
selected=<none>
~~~

**Why?** The selector removes **GreetingAutoConfiguration** from the applied set of auto-configurations. Under the default profile there is no user bean. Excluding an auto-configuration branch **does not delete** a bean actively defined by the application; if you both exclude it and activate the custom profile, you still get **selected=User: Mai**.

### 5.3. A Summary Table of Conditions in This Example

| Scenario | Auto-config class allowed to process? | Property match? | User bean present? | Selected GreetingService |
| --- | --- | --- | --- | --- |
| A: default | Yes | Yes, due to matchIfMissing | No | Default bean |
| B: enabled=false | Yes | No | No | None |
| C: custom profile | Yes | Yes | Yes | User bean; default backs off |
| D: exclude | No | No need to evaluate excluded branch | No | None |

This table applies specifically to the conditions of **GreetingAutoConfiguration** in this lesson. For other configurations, conditions may sit at the class level, bean method level, or nested configuration level and yield different results.

## 6. How to Exclude Auto-Configuration: Choosing the Right Level

In Spring Boot, there are three common ways to exclude an **auto-configuration class**:

**Method 1: exclude by class literal on @SpringBootApplication**

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(
    exclude = dev.academy.autoconfig.GreetingAutoConfiguration.class
)
public class DemoApplication {
}
~~~

This snippet illustrates the annotation attribute; to run the full sample project you must keep the **main** method and other components. The excluded class name is part of the public API supported by Spring Boot for exclusions.

**Method 2: exclude by class name when you do not want a class literal reference**

~~~java
@SpringBootApplication(
    excludeName = "dev.academy.autoconfig.GreetingAutoConfiguration"
)
public class DemoApplication {
}
~~~

A similar illustrative snippet, without imports or a main method and not a standalone file. **excludeName** is useful when compiling code does not have a direct reference to the class.

**Method 3: using a property**

~~~properties
spring.autoconfigure.exclude=dev.academy.autoconfig.GreetingAutoConfiguration
~~~

The property can be placed in a configuration file or passed via command line as in case D. Multiple auto-configuration classes can be excluded using a comma-separated list in the proper property format.

If you are using **@EnableAutoConfiguration** directly instead of **@SpringBootApplication**, the **exclude** and **excludeName** attributes are also available there.

**Distinguishing the operations:**

- **Exclude an auto-configuration class**: removes the entire corresponding import branch.
- **Disable a feature property**: affects only branches whose conditions read that property.
- **Define your own bean**: can cause the default to back off **if** the default branch uses an appropriate **@ConditionalOnMissingBean**.
- **@Primary** and **@Qualifier**: help resolve injection when multiple beans exist; they do not directly remove an auto-configuration from the candidate list.

Only exclude when you know clearly which configuration you want to remove; many Boot auto-configurations collaborate with one another. Removing one class can cause dependent features to lose their required conditions.

## 7. Verifying with the Condition Evaluation Report

To answer "why was class X selected or not?", enable condition diagnostics. Since the sample project sets **logging.level.root=OFF**, override the log level so the report is displayed:

~~~bash
java -jar target/enable-auto-demo-0.0.1-SNAPSHOT.jar --debug --logging.level.root=INFO
~~~

You will see startup logs and a **CONDITIONS EVALUATION REPORT** with sections for positive matches, negative matches, and unconditional classes, depending on the version and logging configuration.

Look for **GreetingAutoConfiguration** and **defaultGreetingService**. In the default state, the class condition passes and the bean method condition passes as well. When adding **--demo.greeting.enabled=false**, the method's condition branch appears under negative matches with the property reason. When enabling the custom profile, **@ConditionalOnMissingBean** reports that a matching bean already exists. When using **spring.autoconfigure.exclude**, the class is removed from the auto-config set and may be listed under exclusions; do not read an absent entry in the report and jump to conclusions without checking exclusions first.

**Be careful:** The condition report tells you **why something matched or did not match**, not proof that the bean was instantiated or that an external service connected successfully. If after matching, a constructor, binding, or connection fails, inspect the **BeanCreationException** stack trace.

In applications with **spring-boot-starter-actuator** and appropriately configured/exposed endpoints, **/actuator/conditions** provides the report as JSON. This endpoint is not public by default; you must configure exposure and secure access appropriately for your environment. **/actuator/beans** is useful to inspect beans currently known to the container, but it does not replace the condition report when tracing why a branch was skipped.

### 7.1. Distinguishing Four Types of Failures

| Symptom | Primary Possibility | What to Check |
| --- | --- | --- |
| Auto-config class does not appear as a candidate | Wrong/missing imports file, missing JAR, exclude | Check runtime classpath, imports content, exclusions |
| Class is a candidate but negative match | Missing class, property mismatch, wrong web environment | Read the reason in the condition report |
| Class matches but bean method is not selected | User bean already exists or condition on method differs | Check conditions on the method itself and bean definitions |
| Definition exists but application cannot use the bean | Instantiation/dependency/binding/resource failure | Check BeanCreationException, lifecycle, scope |

Do not tweak dependencies, properties, or exclusions randomly before knowing which layer of the decision chain the problem lies in.

## 8. Scenarios Involving Starters and Different Configurations

**Scenario 1: Having starter-web.** The starter puts libraries for Spring MVC and an embedded server (depending on the specific dependency tree) onto the classpath. When Boot processes the corresponding candidates, **@ConditionalOnClass** and **@ConditionalOnWebApplication** can match if the context is appropriate; other conditions still determine which beans get created. A starter **does not mean "turn on all auto-configuration regardless of conditions"**.

**Scenario 2: Having starter-jdbc.** JDBC classes give JDBC candidates a chance to match. However, configuring a useful DataSource requires a driver, URL/embedded database, or appropriate settings, and not being replaced by a user bean. Missing conditions or resource errors can still cause startup to fail. Read the condition report before concluding auto-config was disabled.

**Scenario 3: Same source, different environment.** Different command-line arguments, profiles, and property sources can make the same auto-configuration class select different beans. Environment aggregates and resolves property precedence before conditions read the final value.

**Scenario 4: Adding a custom bean.** If the default branch carries **@ConditionalOnMissingBean** for that bean type, Spring Boot usually backs off. This allows selective customization; there is no need to add exclusions for every related auto-configuration.

**Scenario 5: Ordering auto-configurations.** If A needs a bean provided by B, ordering declarations such as **@AutoConfiguration(after = B.class)** help bean-checking conditions run in the right order. This orders configuration processing, not a mechanism to force instance B's startup before instance A if they lack the necessary dependency relationship.

## 9. Common Misconceptions

| Wrong Assumption | Accurate Explanation |
| --- | --- |
| "@EnableAutoConfiguration automatically instantiates every bean." | It enables discovering and applying eligible auto-configurations; conditions, scope, and lifecycle still apply. |
| "@SpringBootApplication must be accompanied by a separate @EnableAutoConfiguration." | The composite annotation already includes the auto-configuration mechanism. |
| "Auto-configuration is the same as @ComponentScan." | Component scan finds components by package; auto-config uses candidate imports and condition evaluation. |
| "Putting @AutoConfiguration on a class is enough for Boot to find it." | The class must appear in the **AutoConfiguration.imports** resource if provided via this mechanism. |
| "Spring Boot 3 still uses the EnableAutoConfiguration key in spring.factories to load new candidates." | Spring Boot 3 uses **AutoConfiguration.imports** for auto-configuration candidates. |
| "Having a class on the classpath guarantees a bean exists." | Classpath is one condition; properties, beans, environment, and other conditions also apply. |
| "Property enabled=true overrides every condition." | No; all relevant conditions must pass. |
| "Having a user bean deletes all default beans." | Only branches with appropriate conditions back off. |
| "Positive match means the service connected successfully." | The report reflects conditions, not guaranteed instantiation or successful resource connection. |
| "Auto-configuration order is the exact object creation order." | Definition registration order and bean instance creation order are two different things. |
| "Exclude and property=false are equivalent." | Exclude removes the entire auto-configuration class; a property may affect only one branch. |
| "Enabling auto-config is enough to scan beans from any package." | Component scanning and specialized packages have their own scopes. |

## 10. Self-Check Questions

**Question 1.** A library contains an **AutoConfiguration.imports** file listing **XAutoConfiguration**. Is class X guaranteed to create beans?

**Answer:** No. The class is only a candidate; it may be excluded or fail conditions. Even if definitions are registered, instance creation depends on lifecycle and can fail.

**Question 2.** You have **@SpringBootApplication** on the main class without declaring **@EnableAutoConfiguration** separately. Is auto-configuration enabled?

**Answer:** Yes. **@SpringBootApplication** includes **@EnableAutoConfiguration**.

**Question 3.** By default **defaultGreetingService** exists, yet when enabling the **custom** profile only **userGreetingService** exists. Why?

**Answer:** The user bean was declared before auto-config evaluated its condition; **@ConditionalOnMissingBean(GreetingService.class)** failed so the default backed off.

**Question 4.** Running the application with **demo.greeting.enabled=false** and **spring.profiles.active=custom**: is there a GreetingService?

**Answer:** Yes, **userGreetingService** exists, because the property condition is attached only to the method creating the default bean in the example. The user bean is not automatically disabled by that property.

**Question 5.** If **GreetingAutoConfiguration** is excluded and the custom profile is not enabled, can the default GreetingService from this class still exist?

**Answer:** No. The auto-configuration class was removed from processing; no bean is provided by that class. If a bean comes from another source, evaluate that separately.

**Question 6.** Why can the report show a positive match yet the application throws **BeanCreationException**?

**Answer:** Configuration selection conditions and instance creation are two stages. A match only indicates the conditions fit; the constructor/factory method/dependencies can fail when creating the object.

**Question 7.** If you want to turn off one specific auto-configuration, do you need to disable **@EnableAutoConfiguration** across the entire application?

**Answer:** No. Use **exclude**, **excludeName**, or **spring.autoconfigure.exclude** for the specific class; if you only want to adjust one feature, check its dedicated property first.

## 11. Practical Conclusion

Whenever you need to explain why Spring Boot puts a bean into an application, trace the chain: **(1) Is @EnableAutoConfiguration enabled? (2) Is the auto-configuration class in imports / runtime classpath? (3) Is the class excluded? (4) Do class-level and per-@Bean conditions pass? (5) Was the bean definition registered? (6) Did the instance initialize successfully?**

**@EnableAutoConfiguration** is the entry point of the **conditional configuration selection** mechanism. **AutoConfigurationImportSelector** finds and selects candidate auto-configurations; conditions coordinate classpath, properties, environment, and user-defined beans; finally the Spring container creates the required instances. Understanding this full chain lets you customize configuration intentionally and use the condition report to diagnose accurately.

### References

- Spring Boot, *Auto-configuration*: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
- Spring Boot, *Creating Your Own Auto-configuration*: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- Spring Boot 3.3, **@EnableAutoConfiguration** API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/EnableAutoConfiguration.html
- Spring Boot 3.3, **AutoConfigurationImportSelector** API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurationImportSelector.html
