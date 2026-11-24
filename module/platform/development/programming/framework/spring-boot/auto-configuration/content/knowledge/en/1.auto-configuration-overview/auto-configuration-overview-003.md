# Libraries, starters, properties, and user beans together determine the selected configuration

## 1. The problem: why do two applications with the same Spring Boot receive different configurations?

Spring Boot **auto-configuration** automatically proposes beans and settings tailored to an application at startup. That proposal is conditional, not a guarantee that simply adding a library causes Spring Boot to create every related bean. Two applications on the same Spring Boot version can receive different configurations because their **dependencies on the classpath**, **selected starters**, **environment properties**, and **application-declared beans** differ.

For example: an application with JDBC libraries but without appropriate connection settings may fail to create a DataSource; another application with the libraries, connection settings, and no custom DataSource declared may use the auto-configured DataSource; while an application that has declared its own DataSource typically causes the default DataSource creation branch to back off. Do not infer from the presence of a dependency that every bean is guaranteed to exist.

Distinguish four concepts:

- **Dependencies/libraries**: the JARs and classes on the runtime classpath, such as Spring MVC, JDBC drivers, Jackson. They provide the technical capability for a configuration to work.
- **Starter**: a convenient dependency that bundles libraries commonly used together for a feature. Starters affect the classpath indirectly; a starter's name itself is not a command to create beans.
- **Auto-configuration**: configuration classes from Spring Boot or third-party libraries that are discovered and conditionally evaluated to register default beans.
- **Properties and user beans**: signals to enable/disable/tune configuration branches or replace a portion of the defaults with the application's explicit choice.

The goal of this lesson is to explain **how these four information sources combine** during configuration selection, and then prove it with a runnable example.

## 2. Mechanism from classpath to actual beans

In an application using **@SpringBootApplication**, auto-configuration is enabled via **@EnableAutoConfiguration**. Spring Boot looks for candidate auto-configuration classes in **META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports** within relevant JARs (the mechanism applied in Spring Boot 3.x). A candidate can carry conditions at the class level and on individual **@Bean** methods.

The process can be pictured as follows:

~~~text
Dependencies and starters
        |
        v
Runtime classpath: classes/libraries actually present
        |
        v
Discover candidate auto-configurations
        |
        v
Evaluate class / environment / property / bean conditions
        |
        +-- Conditions not met --> Skip corresponding configuration or bean
        |
        +-- Conditions met ------> Register bean definition
                                      |
                                      v
                             Create and wire beans by dependencies
~~~

This is a conceptual diagram, not the absolute execution order of every condition. An auto-configuration class being considered **does not mean** all of its **@Bean** methods are selected. Distinguish **bean definition registration** from **instance creation**: auto-configuration ordering annotations affect configuration processing/registration, not directly determining the instantiation order of every instance.

Common conditions:

| Condition | Question checked | Consequence |
| --- | --- | --- |
| **@ConditionalOnClass** | Is the required class on the classpath? | If the class is missing, the corresponding branch is not selected. |
| **@ConditionalOnMissingClass** | Is the specified class absent? | An alternative configuration can be chosen when the library does not exist. |
| **@ConditionalOnProperty** | Does the property have a matching value? | Allows enabling/disabling a configuration branch via Environment. |
| **@ConditionalOnBean** | Does a bean of the conditioned type or name already exist? | Enables a feature only when it depends on an existing bean. |
| **@ConditionalOnMissingBean** | Is there no matching bean yet? | Creates the default only when the application has not provided its own choice. |
| **@ConditionalOnWebApplication** | Does the application have the required web environment type? | Branches configuration for servlet/reactive when appropriate. |

Conditions on **the same branch** generally must all be satisfied together. For example, a bean factory method is registered only if the required class exists **and** the property enables the feature **and** no bean of the same type exists yet. When a condition is placed on the configuration class, the entire inner group may be excluded; a condition placed on a single **@Bean** method may exclude only that method.

### 2.1. Libraries and starters change the list of viable candidates

When **spring-boot-starter-web** is added to a Spring Boot 3.3 application, Maven/Gradle pulls in libraries related to servlet web and Spring MVC. The newly present classes make many **@ConditionalOnClass** conditions able to pass. If the application is indeed of the servlet web type, other conditions match, and no user configuration prevents it, Spring Boot can configure the corresponding MVC components and web server.

If **spring-boot-starter-jdbc** is added, JDBC and Spring JDBC classes appear; Spring Boot gains a basis to consider database connection configuration. However, a URL/driver or suitable embedded database and remaining conditions are still needed. Having JDBC libraries is not proof that a usable DataSource already exists.

A starter usually bundles dependencies, while auto-configuration code usually lives in Boot's auto-configure modules or the corresponding library. Do not mistake a starter for an unconditional switch. Changing dependencies can change **both the set of classes and the application type inferred from the classpath**. For instance, when both Spring MVC and WebFlux are on the classpath, Spring Boot normally selects the servlet application type by default; you cannot infer that merely adding WebFlux automatically turns the whole application reactive.

### 2.2. Properties control selection and fine-tune values

Environment aggregates property sources such as **application.properties**, **application.yml**, environment variables, command-line arguments, and other sources. An auto-configuration can use properties in two different ways:

1. **Decide whether to create a bean**: for example, **@ConditionalOnProperty(prefix = "demo.greeting", name = "enabled", havingValue = "true", matchIfMissing = true)**.
2. **Only change parameters of an already-selected bean**: for example, **demo.greeting.prefix=Hello** changes the greeting prefix without directly changing the bean-creation condition.

With **@ConditionalOnProperty**, the annotation's default behavior when **havingValue** is omitted is: the condition passes if the property **exists** and does not equal the string **false**. When **havingValue = "true"** is set, only a value matching **true** passes; **matchIfMissing = true** allows passing when the property is completely absent. Do not assume every **enabled**-style property is enabled by default: you must read the actual condition of that feature.

When determining the final property value, **property sources and precedence** must be considered. A command-line argument can override a value read from application.properties. Changing a property also cannot rescue a configuration already excluded because a required class is absent or other conditions failed.

### 2.3. User beans and the back-off mechanism

For default configurations guarded by **@ConditionalOnMissingBean**, when the application supplies a suitable bean itself, Spring Boot **does not register the default bean of that branch**. This is an important customization capability: changing just the needed bean without removing the entire auto-configuration.

Conceptual example:

~~~java
@Bean
DataSource customDataSource() {
    // Return a DataSource managed by the application.
    // This snippet illustrates the mechanism; it is not a standalone runnable program.
    return obtainConfiguredDataSource();
}
~~~

When Spring Boot evaluates a default DataSource bean carrying **@ConditionalOnMissingBean(DataSource.class)**, a suitable user-declared bean can cause the default to back off. However, **not every bean created by auto-configuration has @ConditionalOnMissingBean**, and the condition may check **type**, **name**, or search scope across the ApplicationContext hierarchy. Therefore, check the specific condition before predicting the outcome.

Do not equate the following mechanisms:

- **@ConditionalOnMissingBean**: decides **whether to register the default bean** or not.
- **@Primary**: prioritizes one bean when **multiple beans of the same type already exist** and a single bean needs to be injected; it does not by itself prevent registering another bean.
- **@Qualifier**: selects the exact bean at the injection point; does not replace auto-configuration condition logic.
- **Overriding beans by the same name**: can cause bean definition conflict errors; enabling **spring.main.allow-bean-definition-overriding** solely to mask a conflict is not the preferred default customization approach.

Because bean conditions rely on bean definitions already processed up to the time of evaluation, placing **@ConditionalOnBean** or **@ConditionalOnMissingBean** arbitrarily on an ordinary **@Configuration** class can make results order-dependent. When writing auto-configuration, those conditions are recommended to be placed inside auto-configuration classes, which are processed after application-declared bean definitions.

## 3. Decision table: how do the four factors work together?

Consider a hypothetical **GreetingService** feature that has a default bean when the API class is present, the property is enabled, and there is no user bean:

| Required class | Enabled property | User bean | Result |
| --- | --- | --- | --- |
| Present | Undeclared; condition allows default | Absent | Register default GreetingService bean. |
| Present | true | Absent | Register default bean. |
| Present | false | Absent | Do not register default bean. |
| Present | true | Present | User bean is kept; default backs off. |
| Present | false | Present | Default branch is off; user bean can still exist because that property only constrains the default branch. |
| Absent | true | Absent | Branch requiring the class is skipped. |

This table only describes the conditions of this example, **not a rule for every auto-configuration**. It shows that the four signals do not compete in a linear priority order; they are evaluated together in condition expressions. If a required condition fails, that branch is not selected even if the other conditions pass.

## 4. Runnable example: classpath + property + custom bean

The standalone example below uses **Java 21, Maven, and Spring Boot 3.3.13**. The project is intentionally small: a GreetingService API, an auto-configuration declared via the proper imports mechanism, a runnable application, and a user bean that only appears when the **custom** profile is enabled. The main library **spring-boot-starter** provides Spring Boot core/autoconfigure; the API class resides directly in the project, so **@ConditionalOnClass(GreetingService.class)** always passes in these runs. When developing a real library, class-based conditions become especially meaningful when an API is an optional dependency.

Project structure:

~~~text
auto-config-choice/
├── pom.xml
└── src/main/
    ├── java/dev/example/
    │   ├── api/GreetingService.java
    │   ├── autoconfig/GreetingAutoConfiguration.java
    │   └── app/
    │       ├── DemoApplication.java
    │       └── CustomGreetingConfiguration.java
    └── resources/
        ├── application.properties
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

**File pom.xml**

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
    <groupId>dev.example</groupId>
    <artifactId>auto-config-choice</artifactId>
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

**File src/main/java/dev/example/api/GreetingService.java**

~~~java
package dev.example.api;

@FunctionalInterface
public interface GreetingService {
    String greet(String name);
}
~~~

**File src/main/java/dev/example/autoconfig/GreetingAutoConfiguration.java**

~~~java
package dev.example.autoconfig;

import dev.example.api.GreetingService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

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
    GreetingService greetingService(Environment environment) {
        String prefix = environment.getProperty(
            "demo.greeting.prefix", "Hello"
        );
        return name -> prefix + ", " + name;
    }
}
~~~

The three conditions here play different roles: **@ConditionalOnClass** confirms the API is on the classpath; **@ConditionalOnProperty** chooses whether to create the default bean; **@ConditionalOnMissingBean** defers to an application-declared bean. The **demo.greeting.prefix** property only changes how the default bean behaves.

**File src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**

~~~text
dev.example.autoconfig.GreetingAutoConfiguration
~~~

This is the auto-configuration registration for Spring Boot 3.x. Do not omit this file: merely placing **@AutoConfiguration** on a class is not enough for that class to be discovered automatically. In the example, **dev.example.autoconfig** lies outside the default component scan region of the **dev.example.app** application; the auto-configuration class is imported through the mechanism above, avoiding reliance on component scanning.

**File src/main/java/dev/example/app/DemoApplication.java**

~~~java
package dev.example.app;

import dev.example.api.GreetingService;
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
    ApplicationRunner showGreeting(
            ObjectProvider<GreetingService> services) {
        return args -> {
            GreetingService service = services.getIfAvailable();
            System.out.println(service == null
                ? "service=<none>"
                : "service=" + service.greet("Linh"));
        };
    }
}
~~~

Using **ObjectProvider** allows testing the case where the default bean is intentionally disabled without causing the application to fail due to a missing injected dependency. In the run scenarios below there is at most one GreetingService. With multiple beans of the same type, **getIfAvailable()** may throw an error because a unique bean cannot be resolved; in that case, an appropriate bean selection rule is needed.

**File src/main/java/dev/example/app/CustomGreetingConfiguration.java**

~~~java
package dev.example.app;

import dev.example.api.GreetingService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
@Profile("custom")
public class CustomGreetingConfiguration {

    @Bean
    GreetingService customGreetingService() {
        return name -> "Xin chào, " + name;
    }
}
~~~

Only when the **custom** profile is activated does the application declare its own GreetingService bean. At that point, the default branch in GreetingAutoConfiguration fails **@ConditionalOnMissingBean(GreetingService.class)**.

**File src/main/resources/application.properties**

~~~properties
spring.main.banner-mode=off
logging.level.root=OFF
~~~

These two lines keep the exercise's stdout clean; they are not conditions of GreetingService. When you want to inspect diagnostic logs, temporarily remove **logging.level.root=OFF**.

### 4.1. Build and observe four cases

Requirements: **JDK 21**, **Maven 3.9+**, able to download dependencies from Maven Central. Open a terminal in the **auto-config-choice** folder:

~~~bash
mvn -q -DskipTests package
~~~

Default run, with **demo.greeting.enabled** undeclared and the custom profile inactive:

~~~bash
java -jar target/auto-config-choice-0.0.1-SNAPSHOT.jar
~~~

The stdout line printed by the program:

~~~text
service=Hello, Linh
~~~

Reason: the GreetingService class is on the classpath, **matchIfMissing=true** allows the enabled property to be absent, and there is no user bean yet. Auto-configuration registers the default bean.

Change a **configuration value property**, still keeping the default bean:

~~~bash
java -jar target/auto-config-choice-0.0.1-SNAPSHOT.jar --demo.greeting.prefix=Hi
~~~

Stdout line:

~~~text
service=Hi, Linh
~~~

Reason: the command-line argument supplies the new prefix to **Environment**. Bean selection conditions do not change.

**Disable the default bean creation branch**:

~~~bash
java -jar target/auto-config-choice-0.0.1-SNAPSHOT.jar --demo.greeting.enabled=false
~~~

Stdout line:

~~~text
service=<none>
~~~

Reason: the property does not match **havingValue=true**; there is no self-declared bean in the default profile.

**Enable the user bean**:

~~~bash
java -jar target/auto-config-choice-0.0.1-SNAPSHOT.jar --spring.profiles.active=custom
~~~

Stdout line:

~~~text
service=Xin chào, Linh
~~~

Reason: **CustomGreetingConfiguration** is loaded and registers GreetingService; **@ConditionalOnMissingBean** fails so the default bean backs off. If you run **--spring.profiles.active=custom** and **--demo.greeting.enabled=false** simultaneously, you still get the user bean's output: the property only restricts the default branch and does not automatically disable user configuration.

Simulating the absence of the GreetingService class cannot be done simply by removing a dependency in the example project, because the application and auto-configuration sources themselves reference that API at compile time. In a standalone library, **@ConditionalOnClass** takes effect when consuming applications may or may not have an optional dependency.

### 4.2. If you want to observe starters and classpath changes too

The example uses a fixed **spring-boot-starter** to isolate property/bean effects. In a real project, you can compare the dependency tree before and after adding a starter:

~~~bash
mvn dependency:tree
~~~

When changing dependencies, check which classes are pulled onto the runtime classpath and which conditions become viable. **Do not directly infer** that all features of the starter have been initialized; conclusions should rely on the condition report and actual beans.

## 5. Diagnostics: why does Spring Boot select or skip a configuration?

When the application runs but an expected bean does not exist, check in order:

1. **Classpath**: is the dependency on the runtime classpath? Was it excluded, given the wrong scope, hit by a version conflict, or missing a driver? Use the dependency tree to confirm.
2. **Is auto-configuration enabled?** Does the application have **@SpringBootApplication** or **@EnableAutoConfiguration**? Is a custom auto-configuration class listed in the properly named imports file?
3. **Class-level conditions**: missing class, wrong web application type, missing required resource or property?
4. **@Bean method-level conditions**: is there a user bean of the same type/name causing **@ConditionalOnMissingBean** to fail? Is another condition blocking it?
5. **Final Environment value**: what is the actual property value after applying profiles, environment variables, config imports, and command-line arguments?
6. **Registered or failed at initialization?** These are two different cases. Passing conditions does not guarantee every step of resource connection, binding, or initialization succeeds.

In a typical application, start with **--debug** to enable the condition evaluation report in the logs:

~~~bash
java -jar target/auto-config-choice-0.0.1-SNAPSHOT.jar --debug
~~~

**Note on the example above**: remove or temporarily disable **logging.level.root=OFF** to see diagnostic logs. The condition evaluation report groups **positive matches** (satisfied conditions), **negative matches** (unsatisfied conditions), and information about configurations without conditions. Search for **GreetingAutoConfiguration** and the bean factory method to see the specific reason.

If the application uses **spring-boot-starter-actuator** and has HTTP endpoints appropriately configured/exposed, **/actuator/conditions** lets you read the report in JSON format. This endpoint is not automatically exposed publicly just by adding Actuator: exposure and security configuration must be considered. It is a verification tool, not a reason to expose sensitive endpoints arbitrarily in public environments.

### 5.1. Common reasoning mistakes

| Misconception | Correct understanding |
| --- | --- |
| "I added the starter, so bean X is guaranteed to exist." | Starters provide dependencies; beans still depend on conditions and initialization success. |
| "Setting property=true definitely enables everything." | A property only affects the exact conditions and bindings that read it; missing required classes or beans can still block it. |
| "Setting property=false will also remove application-created beans." | Usually a property only disables the auto-configuration branch carrying that condition; self-declared beans have their own lifecycle. |
| "If a bean of the same type exists, Boot always backs off." | It only backs off on branches with an appropriate condition, usually **@ConditionalOnMissingBean**. |
| "Marking @Primary disables the default bean." | @Primary resolves injection precedence, not a mechanism to prevent registration. |
| "The application started, meaning every auto-configuration matched." | Having many excluded branches is normal; the condition report explains each branch. |
| "If auto-configurations are selected, bean creation order must match the imports file order." | Registration order and instantiation order are two separate matters; dependencies between beans affect instantiation order. |
| "@AutoConfiguration classes are automatically scanned in any package." | In Spring Boot 3.x, custom auto-configurations need to be registered in the imports file and avoid normal component scanning. |

## 6. Practical scenarios to test your understanding

**Scenario A.** The required library is present, the property is enabled, and there is no user bean, yet a bean is still absent. Check **@ConditionalOnWebApplication**, **@ConditionalOnBean**, the bean name, and the report as well: the first three signals do not guarantee the final branch passes.

**Scenario B.** The application creates a bean of the same type, and then enables the default configuration's property. If the default method has **@ConditionalOnMissingBean** for that type, the default bean is still not created; enabling the property does not override the remaining condition.

**Scenario C.** After adding a starter, the application changes behavior even though business source code did not change. Compare the **dependency tree**, actual classpath, **positive/negative matches**, final properties, and bean set. That is how to determine whether the change came from pulled-in libraries or another condition.

**Quick self-check:**

1. In the runnable example, change **demo.greeting.prefix=Bonjour** while keeping **demo.greeting.enabled=false**—what is the result? **service=<none>**, because changing the prefix value does not re-create an excluded bean.
2. Enable the **custom** profile while also setting **demo.greeting.prefix=Bonjour**—what is the result? **service=Xin chào, Linh**, because the user bean does not read the default branch's prefix property.
3. Why is **@ConditionalOnMissingBean** not equivalent to **@Primary**? One decides bean registration; the other helps choose among beans that already exist.

## 7. Takeaways for design and operations

For every bean that appears "automatically created by Spring Boot", ask in sequence: **(1) which classes are on the classpath? (2) which candidate auto-configurations can be considered? (3) do existing properties/application type/beans satisfy the conditions? (4) which bean definition is registered? (5) does initialization succeed?** This way of reading explains why adding dependencies, changing starters, editing properties, or declaring beans can all alter the final configuration.

Prefer properties published by the framework to fine-tune behavior; declare your own beans when you need to change how a bean is built; only exclude an entire auto-configuration when you genuinely want to remove the whole branch and understand the related beans. For libraries you write yourself, place class conditions at an appropriate configuration level, place missing-bean conditions to allow user customization, and register auto-configurations using Spring Boot 3.x's imports file.

### Reference documentation

- Spring Boot, *Auto-configuration*: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
- Spring Boot, *Creating Your Own Auto-configuration*: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- Spring Boot 3.3, *Conditions Evaluation Report*: https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html
