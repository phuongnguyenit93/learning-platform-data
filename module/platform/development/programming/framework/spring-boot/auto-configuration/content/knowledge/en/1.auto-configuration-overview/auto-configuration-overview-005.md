# From candidate configuration list to the actual set of beans in the application

## 1. The big picture: three distinct sets

When Spring Boot starts, a class appearing in the *auto-configuration* list does not mean every bean declared in that class will show up. Three questions must be separated:

1. **Candidates:** which auto-configuration classes were found on the classpath and placed into the consideration list?
2. **Eligible configurations:** after exclusions, ordering, and evaluating `@Conditional`, which configurations or `@Bean` methods are allowed to contribute bean definitions?
3. **Actual beans:** after registering bean definitions, resolving dependencies, and lifecycle instantiation, which beans exist in `ApplicationContext`, with what types and names?

Conceptual flow:

~~~text
@SpringBootApplication (includes @EnableAutoConfiguration)
    |
    v
Find AutoConfiguration.imports on classpath
    |
    v
Candidate class list -> exclusions -> early filters/conditions -> ordering
    |
    v
Process selected configuration classes and their conditions
    |
    v
Register eligible BeanDefinitions
    |                         ^
    |                         |
    +--- observe user-defined beans already declared
    |
    v
Spring creates required beans, injects dependencies, applies lifecycle
    |
    v
ApplicationContext: queryable set of beans
~~~

This is a learning diagram, not an assertion that each arrow corresponds to a single isolated operation. Some conditions are evaluated at different phases of configuration processing. Bean definitions can exist before bean objects are instantiated.

**Core point:** `candidate != configuration accepted != BeanDefinition registered != bean instance instantiated`. An auto-configuration class can be discovered without being applied; an applied configuration may contribute no beans; a registered bean definition might not have an instance created yet due to `@Lazy` or `prototype` scope.

## 2. How are candidates discovered?

### Activation point

`@SpringBootApplication` combines `@SpringBootConfiguration`, `@EnableAutoConfiguration`, and `@ComponentScan`. The auto-configuration part is activated by `@EnableAutoConfiguration`; `@ComponentScan` is a separate mechanism used to find components declared by the application within the scan scope. Do not conflate the two mechanisms.

In Spring Boot 3.x, auto-configuration candidates are listed in a resource with the exact path:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Each valid line is a fully qualified class name, for example:

~~~text
com.example.feature.autoconfigure.FeatureAutoConfiguration
com.example.feature.autoconfigure.FeatureMetricsAutoConfiguration
~~~

Libraries or starters can package this resource inside a JAR. Spring Boot locates matching resources on the classpath and obtains the class list via the candidate import mechanism. A class annotated with `@AutoConfiguration` (which is itself a Spring configuration) only becomes a **candidate** when properly declared in the imports file; adding a dependency does not guarantee every configuration or bean inside it will be used.

Note for Spring Boot 3.x: `spring.factories` still serves some other SPI roles, but the Boot 3 way of declaring auto-configuration classes is `AutoConfiguration.imports`. Do not use the legacy auto-configuration registration model as the rule for this lesson.

### Candidates are not the same as component scan

A library's auto-configuration class should be placed in its own package, outside the application's `@ComponentScan` scope. If that class is both scanned as an ordinary `@Configuration` and automatically imported, learners will struggle to distinguish processing order and activation mechanisms. Auto-configuration is designed to be imported via the imports file; when supporting configurations are needed, use `@Import` intentionally.

## 3. From candidates to eligible configurations

There are three key decision groups.

**(a) Explicit exclusion.** The application can exclude a specific auto-configuration via `@SpringBootApplication(exclude = ...)`, `@EnableAutoConfiguration(exclude = ...)`, or the `spring.autoconfigure.exclude` property. Excluding a class does not remove the JAR from the classpath and does not delete beans created by other configuration sources.

**(b) Condition checks.** Conditions declared on the configuration class can prevent the entire class from being processed as a matching configuration. Conditions on a `@Bean` method can prevent only that method's bean definition while other methods remain eligible.

**(c) Ordering.** `@AutoConfiguration(before = ..., after = ...)`, `@AutoConfigureBefore`, `@AutoConfigureAfter`, and `@AutoConfigureOrder` control auto-configuration processing order to satisfy dependencies between **definitions**. They do not guarantee bean instantiation order at runtime; instantiation depends on the dependency graph and relationships such as `@DependsOn`.

Conditions can be processed early when filtering candidates, or while Spring parses/registers configurations and bean methods. Thus you should not imagine the system running just one single check pass and then instantiating all beans.

### Table of common conditions

| Condition | Practical meaning | Typical scenario |
| --- | --- | --- |
| `@ConditionalOnClass` / `@ConditionalOnMissingClass` | Presence/absence of a type on the classpath | Configure an integration only when the relevant library is included |
| `@ConditionalOnBean` | A bean matching type or name already exists in the search scope | Create an adapter only when required infrastructure already exists |
| `@ConditionalOnMissingBean` | No matching bean is seen at evaluation time | Provide a default bean if the application has not declared one |
| `@ConditionalOnProperty` | Property value in Spring `Environment` satisfies the condition | Enable/disable a configuration with a flag |
| `@ConditionalOnWebApplication` / `@ConditionalOnNotWebApplication` | Matching web environment type or non-web | Add Servlet/WebFlux infrastructure only in the right context |
| `@ConditionalOnResource` | Specified resource exists | Configure only when required files/resources are present |

Do not infer from an annotation's name that a condition always evaluates true/false via a simple lookup: `@ConditionalOnProperty` has `havingValue` and `matchIfMissing` parameters; `@ConditionalOnBean` can search by name/type and context hierarchy; `@ConditionalOnMissingBean` also depends on definitions already processed at the time of checking.

Example:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.example.client.RemoteClient")
@ConditionalOnProperty(
    prefix = "feature.remote",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false
)
public class RemoteFeatureAutoConfiguration {
    // @Bean methods may have their own additional conditions.
}
~~~

This is an **illustrative snippet**, not a standalone program. `name` on `@ConditionalOnClass` lets you specify the class name as a string. When a dependency may be absent, avoid placing the optional type directly in the signature of a `@Bean` method that the JVM loads too early; separating configuration with `@ConditionalOnClass` into a nested/separate `@Configuration` class is a safe approach.

## 4. Why do user-declared beans take precedence?

Spring Boot creates default configurations according to the *back off* principle: if the application has already declared a suitable bean, a default bean carrying `@ConditionalOnMissingBean` will normally **not be registered**. That condition inspects known bean definitions rather than waiting until all instances are instantiated to decide.

For example, suppose an auto-configuration has:

~~~java
@Bean
@ConditionalOnMissingBean(PaymentGateway.class)
PaymentGateway defaultPaymentGateway() {
    return new SandboxPaymentGateway();
}
~~~

If the application already has a `PaymentGateway` bean when the condition is evaluated, the `defaultPaymentGateway` definition is not added. When `@ConditionalOnMissingBean` is used in auto-configuration, Spring Boot arranges to process user-declared configurations first, allowing defaults to back off properly.

**Not every bean with the same name or same type automatically overrides another.** `@ConditionalOnMissingBean(PaymentGateway.class)` checks by **type**, whereas `@ConditionalOnMissingBean(name = "paymentGateway")` checks by **name**. The rules for overriding definitions with the same name are a separate matter; Spring Boot normally disallows accidental bean definition overriding.

A subtle mistake is declaring `@Bean` with an overly generic return type, such as `Object` instead of the actual domain type. Bean lookup conditions rely on type metadata available on the definition, so an explicit signature helps Spring identify it accurately. Only use bean conditions in auto-configuration or where processing order is clearly understood; using them carelessly in application configuration often leads to order-dependent results.

## 5. Complete experiment with Spring Boot 3.3 and Java 17

Goal: the same `GreetingAutoConfiguration` class is in the candidate list, yet the final set of `GreetingService` beans changes according to application configuration. The example uses Spring Boot 3.3.13, Java 17+, and Maven 3.9+.

File tree:

~~~text
auto-demo/
├── pom.xml
└── src/main/
    ├── java/
    │   └── demo/
    │       ├── api/GreetingService.java
    │       ├── app/DemoApplication.java
    │       └── autoconfig/GreetingAutoConfiguration.java
    └── resources/
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

### 5.1. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <groupId>demo</groupId>
    <artifactId>auto-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
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

`spring-boot-starter` provides context creation and basic logging; the example is not a web application so `spring-boot-starter-web` is unnecessary.

### 5.2. `src/main/java/demo/api/GreetingService.java`

~~~java
package demo.api;

public interface GreetingService {
    String source();
}
~~~

### 5.3. `src/main/java/demo/autoconfig/GreetingAutoConfiguration.java`

~~~java
package demo.autoconfig;

import demo.api.GreetingService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(GreetingService.class)
@ConditionalOnProperty(
    prefix = "demo.auto",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService defaultGreetingService() {
        return () -> "auto";
    }
}
~~~

Reading conditions from outside in: the `GreetingService` interface is on the classpath; `demo.auto.enabled` equals `true` or is undeclared; and finally **no other** `GreetingService` bean exists yet. Only when all relevant conditions are met does the method register the default bean definition.

### 5.4. `src/main/java/demo/app/DemoApplication.java`

~~~java
package demo.app;

import demo.api.GreetingService;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    @ConditionalOnProperty(
        prefix = "demo",
        name = "custom",
        havingValue = "true"
    )
    GreetingService customGreetingService() {
        return () -> "custom";
    }

    @Bean
    ApplicationRunner inspect(ObjectProvider<GreetingService> provider) {
        return args -> {
            GreetingService service = provider.getIfAvailable();
            System.out.println("origin=" +
                (service == null ? "none" : service.source()));
        };
    }
}
~~~

The main class is in `demo.app`, so normal component scan **does not scan** the sibling package `demo.autoconfig`. Auto-configuration only participates thanks to the imports file below. The user bean `customGreetingService` appears when `demo.custom=true`.

### 5.5. `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

~~~text
demo.autoconfig.GreetingAutoConfiguration
~~~

This is the step that turns the class above into an **auto-configuration candidate**. Writing `@AutoConfiguration` on the Java class alone while forgetting this file prevents the experiment from demonstrating candidate discovery.

### 5.6. Run and observe

From the `auto-demo` directory, run the following commands one by one (each starts a separate process):

~~~bash
mvn -q spring-boot:run
mvn -q spring-boot:run -Dspring-boot.run.arguments=--demo.custom=true
mvn -q spring-boot:run -Dspring-boot.run.arguments=--demo.auto.enabled=false
mvn -q spring-boot:run -Dspring-boot.run.arguments="--demo.custom=true --demo.auto.enabled=false"
~~~

The lines **printed by `System.out.println` in the example** are respectively:

~~~text
origin=auto
origin=custom
origin=none
origin=custom
~~~

The application may also print the banner and Spring Boot logs; this is not the entire stdout. Explanation:

| Case | Self-declared bean | Auto-config class condition | Missing-bean condition | Result |
| --- | --- | --- | --- | --- |
| Default | Absent | Passed | Passed | `defaultGreetingService` is selected |
| `demo.custom=true` | Present | Passed | Failed | `customGreetingService` is selected |
| `demo.auto.enabled=false` | Absent | Failed due to property | Method not evaluated | No `GreetingService` |
| Both custom=true and auto=false | Present | Failed | Method not evaluated | User-declared bean still exists |

The value `origin=none` is printed because the program uses `ObjectProvider` for optional lookup. If replaced with mandatory constructor injection for `GreetingService` when no bean exists, the application may fail to start due to a missing dependency. That does **not** mean Spring Boot creates beans automatically just to satisfy every injection.

You can also test the exclusion mechanism:

~~~bash
mvn -q spring-boot:run -Dspring-boot.run.arguments=--spring.autoconfigure.exclude=demo.autoconfig.GreetingAutoConfiguration
~~~

With `demo.custom` off, the observed line is `origin=none`. The candidate class is still in the imports file, but it was explicitly excluded.

## 6. Inspecting actual results: do not look only at the imports file

### Which conditions passed, and which failed?

Start the application with `--debug` so Spring Boot prints the *Condition Evaluation Report* in the logs. For example:

~~~bash
mvn -q spring-boot:run -Dspring-boot.run.arguments="--debug --demo.custom=true"
~~~

In the report, find `GreetingAutoConfiguration` and its related conditions. The report contains matching and non-matching conditions, but **is not** a final list of every instantiated bean.

If the application has `spring-boot-starter-actuator` and configuration allows access to the corresponding endpoints, `/actuator/conditions` provides condition evaluation information; `/actuator/beans` provides information on beans in the context. Endpoints and exposure levels depend on management configuration; do not assume all endpoints are public by default.

### Which beans are actually in the context?

You can use the following snippet inside an `ApplicationRunner` or test code that has an `ApplicationContext`:

~~~java
String[] names = context.getBeanNamesForType(GreetingService.class);
java.util.Arrays.sort(names);
System.out.println(java.util.Arrays.toString(names));
~~~

This is an **illustrative snippet requiring a `context` variable of type `ApplicationContext`**, not a standalone runnable Java file. In the experiment, the expected output is `[defaultGreetingService]`, `[customGreetingService]`, or `[]` depending on the case. If you need to inspect registered definitions rather than just names by type, use the `getBeanDefinitionNames()` and `getBeanFactory()` APIs appropriate to the context type.

Distinguish three kinds of evidence:

- **Classpath/imports:** the class can be considered as a candidate.
- **Condition Evaluation Report:** why a configuration or bean method matched/did not match at evaluation time.
- **ApplicationContext / bean definitions:** the state of beans registered and queryable in that specific process's context.

When you want to determine why a bean is missing, combine all three. Checking only whether a JAR has a class is not enough to conclude the bean appears.

## 7. Factors that change the final bean set

### Dependencies and runtime environment

Adding `spring-boot-starter-jdbc` and a suitable driver can make JDBC-related auto-configurations candidates with a chance to pass classpath conditions; at the same time, connection settings and existing beans must also be considered. Adding a starter, changing the classpath, switching Servlet/WebFlux runtime, or missing resources can all change the outcome without editing auto-configuration classes.

### Externalized configuration

Properties are aggregated into Spring `Environment` from many sources, such as `application.yml`, environment variables, or command-line arguments. A property like `feature.enabled` can cause `@ConditionalOnProperty` to flip its outcome. `@ConfigurationProperties` is the mechanism for binding external configuration to objects; merely declaring a `@ConfigurationProperties` class does not mean auto-configuration necessarily creates that bean. To have the configuration bean, a suitable registration mechanism is required, such as `@EnableConfigurationProperties` or `@ConfigurationPropertiesScan`.

### User beans and dependency relationships

An auto-configuration may create infrastructure bean A only when bean B already exists, or skip default bean A if the application supplies A. The outcome depends on both **user definitions** and previously processed auto-configurations. Registration order matters for bean-existence conditions because conditions see definitions already present at evaluation time.

### Instantiation and lifecycle

From having a `BeanDefinition` to having an instance involves object creation, dependency injection, post-processing, and initialization. Default singletons are normally created during context refresh; lazy singletons can be deferred until needed; prototypes are normally created per request. If bean creation fails or a mandatory dependency is missing, startup may fail. Therefore, saying "the bean has been registered" is more accurate than "the bean is guaranteed to be instantiated and usable".

## 8. Analysis scenario: why is a DataSource present or absent?

An inaccurate answer is "having the JDBC starter guarantees a `DataSource`". How to trace the mechanism:

1. Check JDBC dependencies and drivers on the classpath. Determine whether the required foundational conditions exist.
2. Determine whether relevant auto-configurations, such as `DataSourceAutoConfiguration`, are in the candidate list or excluded.
3. Read class-level conditions and conditions on nested configurations/`@Bean` methods. Those configurations may require matching classes, properties, environment, and related beans.
4. Check whether the application has already defined its own `DataSource` or connection settings. A user bean can cause the default bean to back off.
5. Use the Condition Evaluation Report to inspect match/mismatch reasons. Use `ApplicationContext` or actuator `beans` to confirm the final definitions/beans.
6. If startup fails, read the root exception: wrong connection details and missing beans are two different groups of causes.

In practice, this model applies similarly to Jackson, transaction managers, security filter chains, and many other infrastructure pieces; each auto-configuration still has its own specific conditions, so do not apply one blanket rule to all.

## 9. Common confusions and how to fix them

| Confusion | Fact to verify |
| --- | --- |
| "Listed in `AutoConfiguration.imports` means the bean is guaranteed." | Imports only identify candidates; exclusions, class/method conditions, and then bean registration still follow. |
| "Just adding a starter makes everything work." | Starters add dependencies; beans still depend on classpath, environment, properties, and existing beans. |
| "`@ComponentScan` finds all auto-configurations." | Component scan and the auto-configuration import mechanism are two distinct sources. |
| "`@ConditionalOnMissingBean` checks at bean runtime." | Conditions evaluate from already-processed bean information before deciding whether to register the default bean. |
| "Auto-config order decides bean constructor order." | Order affects definition registration order; dependencies and lifecycle determine instantiation. |
| "A registered bean always has an instance immediately." | `@Lazy`, `prototype`, and bean creation situations separate those two points in time. |
| "If a configuration is excluded, every bean of that type disappears." | Beans created by the user or other configurations can still exist. |
| "The debug report is the final bean list." | The report gives condition reasons; query the context to know existing beans. |
| "If a bean is missing, you must enable definition overriding." | First check conditions, package scan, imports, types, properties, and startup errors. |

### Systematic analysis when a bean does not appear

Start from **the bean you want to find**, trace back to **the `@Bean` method or component creating it**, then to **the owning configuration class**, and finally to **imports and dependencies**. At each step ask: was the bean declared, was the configuration loaded, which condition filtered it out, did a self-declared bean make the default back off, and did initialization fail?

Do not conclude solely from a "No qualifying bean" message, because that message describes an unsatisfied injection point without revealing the root cause.

## 10. Self-verification exercises

1. In the example, delete the class name line from `AutoConfiguration.imports` and run with defaults. Predict and check `origin`. Explain why merely keeping the Java class in the project is not enough.
2. Try `--demo.custom=true` and `--demo.auto.enabled=false` together. Which bean is governed by each property?
3. Replace `@ConditionalOnMissingBean(GreetingService.class)` with a condition checking the name `defaultGreetingService`. Predict what happens when the application has a bean named `customGreetingService` of the same type; explain why two `GreetingService` beans can arise and the impact on single-type lookup.
4. Try adding `@Lazy` to the default bean, then distinguish BeanDefinition existence from instance creation time. Note: the current `ApplicationRunner` requests the bean, which can trigger the lazy bean.
5. Enable `--debug` in each scenario and record evidence from the Condition Evaluation Report, then cross-check against bean names in the context.

**Self-assessment criteria:** able to explain why the same imports file yields different bean sets; pinpoint the exact condition causing the default bean to back off; avoid confusing *candidate discovery*, *definition registration*, and *bean instantiation*.

## 11. Operational checklist

When checking an auto-configuration-related bean, follow the chain: **right classpath → imports → exclusions → configuration ordering and conditions → `@Bean` conditions → user-supplied definitions → BeanDefinition registration → instantiation and lookup in ApplicationContext**. You can skip already-confirmed steps, but never jump from "library present" to "bean guaranteed".

Official reference documentation (Spring Boot 3.3):
- [Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html)
- [Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Maven plugin and starter parent](https://docs.spring.io/spring-boot/3.3/maven-plugin/using.html)
