# Importing Supporting Components via @Import Instead of Broad Component Scanning

## 1. Problem and Goal

When writing a library that provides **auto-configuration** for Spring Boot, you often need one or a few supporting configurations to supply default beans, adapters, or converters. A good design is for the auto-configuration class to **import the exact supporting configuration needed** via **@Import**, rather than widening **@ComponentScan** across the library's entire package.

Distinguish:

- **@Import(SupportConfiguration.class)** specifies the configuration class Spring should process. That class can declare multiple **@Bean** methods, conditions, and further imports.
- **@ComponentScan(basePackages = "...")** discovers multiple components in matching packages. Whenever the library adds a class annotated with **@Component** or **@Configuration**, the scanned bean set can change.
- Spring Boot's **@EnableAutoConfiguration** is not equivalent to scanning all packages. In Spring Boot 3.x, it uses **AutoConfiguration.imports** metadata to select auto-configuration candidates, then applies conditions and exclusions.

**Core idea:** an auto-configuration should contribute only the components required for an activated feature. Do not perform a broad package scan to "find everything with an annotation", because that can introduce unintended components into the ApplicationContext.

### 1.1. Why Is This Worth Learning?

Suppose an audit library has three kinds of classes:

- **AuditAutoConfiguration**: decides when audit is enabled.
- **AuditSupportConfiguration**: creates a default `AuditSink` bean.
- **UnrelatedComponent**: another component used by internal tooling, not part of audit runtime.

If the audit configuration uses **@ComponentScan("dev.lesson.support")**, that third component can be loaded alongside the support configuration. If it uses **@Import(AuditSupportConfiguration.class)**, Spring processes only the explicitly named configuration path and whatever that configuration itself declares. Another **@Component** sitting in the same package is not automatically registered just because the class exists.

This provides better control over startup, dependencies, bean conflicts, and the library's contract.

## 2. Three Ways to Bring Configuration into the Container

### 2.1. Component Scanning by Package

**@SpringBootApplication** includes component scanning. When the main class is in package **dev.lesson.app**, component scan by default targets that package and its subpackages.

~~~java
package dev.lesson.app;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

This is a basic example; it needs Spring Boot dependencies to run. Classes belonging to **dev.lesson.support** or **dev.lesson.autoconfig** are not in the **dev.lesson.app** package tree, so default component scan does not find them automatically.

If replaced with:

~~~java
@SpringBootApplication(scanBasePackages = "dev.lesson")
public class Application {
    // Other application methods.
}
~~~

the scan scope widens and can cover support/autoconfig. The snippet above only illustrates the annotation, not a standalone runnable file. With wide scanning, newly added components in library packages can appear in the container without the application intending to request them.

### 2.2. Directly @Import-ing a Supporting Configuration

~~~java
@AutoConfiguration
@Import(AuditSupportConfiguration.class)
class AuditAutoConfiguration {
}
~~~

**The snippet above is an abbreviated illustration**, omitting import statements and class definitions. When `AuditAutoConfiguration` is selected, Spring processes `AuditSupportConfiguration` along the **@Import** path. It does not perform component scanning across the package containing `AuditSupportConfiguration`.

**@Import** can accept configuration classes, component classes, `ImportSelector`s, or `ImportBeanDefinitionRegistrar`s. Therefore, an imported class can still declare further imports. Put differently: the benefit is **choosing an explicit configuration path**, not guaranteeing only one `BeanDefinition` is created.

### 2.3. Boot Selects Auto-Configurations Using Metadata

In Spring Boot 3.x, libraries publish candidates in the resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Example:

~~~text
dev.lesson.autoconfig.AuditAutoConfiguration
~~~

When an application has **@SpringBootApplication**, **@EnableAutoConfiguration** is enabled. **AutoConfigurationImportSelector** reads the candidate list and handles exclusions and matching conditions; only selected auto-configuration classes get to pull supporting configurations into processing via **@Import**.

There are two layers:

~~~text
@SpringBootApplication
          |
          v
@EnableAutoConfiguration
          |
          v
AutoConfiguration.imports
          |
          v
AuditAutoConfiguration  (candidate)
          |
       Conditions met?
          |
          v
@Import(AuditSupportConfiguration.class)
          |
          v
@Bean methods inside AuditSupportConfiguration
          |
       Bean conditions met?
          |
          v
Register BeanDefinition and instantiate per lifecycle

UnrelatedComponent in the same JAR:
    does not appear automatically without appropriate scan/import/registration.
~~~

Do not confuse the **AutoConfiguration.imports** file with the **@Import** annotation: they have similar names yet serve different roles. The resource publishes Boot's list of auto-configurations; the `@Import` annotation sits on a configuration class to specify additional classes or import strategies.

## 3. Comparing @Import and Broad @ComponentScan

| Characteristic | @Import specific support class | Broad package @ComponentScan |
| --- | --- | --- |
| Discovery target | Classes specified in the annotation | Candidates in the package and subpackages |
| Scope control | Usually clear, focused on the feature | Depends on package contents at runtime |
| When adding a new @Component to the package | Does not alter the existing import path | New component may be registered |
| Requires class to be inside scanned package? | No | Yes, or scan package must be widened |
| Does @Conditional still take effect? | Yes | Yes |
| Suitable for auto-config supporting configurations? | Usually yes | Avoid broad scanning of library packages |
| Risk | Transitive imports or a support class scanning itself can still widen scope | Loads extra components, creating unintended beans |
| Boot's candidate selection mechanism | Separate, from `AutoConfiguration.imports` | Not the core role of component scan |

Do not conclude that **@Import is always safe**: if a support class contains a broad `@ComponentScan` or an `ImportSelector` returns too many classes, the effective scope is still broad. Good design keeps imported configurations **bounded and purposeful**.

### 3.1. Auto-Configurations Should Not Be Component-Scanned Like Application Configurations

In Spring Boot 3.x, auto-configurations should live in a separate package and be registered via **AutoConfiguration.imports**. Spring Boot recommends that auto-configurations not become targets of regular component scanning. Supporting **@Configuration** classes can be imported with explicit **@Import**.

If you try to scan the package containing auto-configs, a class can be processed outside `AutoConfigurationImportSelector`, making ordering, conditions, and exclusions harder to reason about compared to the standard contract. It is better to keep the library module in its own package and publish only the intended auto-config candidates.

## 4. Designing Conditions and the Back-off Mechanism

In auto-configuration, conditions belong at the right layer:

- **@ConditionalOnClass** on the auto-configuration class: requires optional APIs to exist on the classpath.
- **@ConditionalOnProperty** on the auto-configuration class: toggles the entire branch via a feature flag.
- **@ConditionalOnMissingBean** on default `@Bean` methods: backs off if the application already declared a matching bean.
- Conditions on the support class or individual methods: restrict supporting beans individually.

Decision diagram:

~~~text
AuditAutoConfiguration is a candidate
             |
             v
Class and property conditions met?
         /              \
       No                Yes
        |                 |
   Skip branch       @Import support
                          |
                          v
                @Bean defaultAuditSink
                          |
                          v
                User AuditSink exists?
                    /           \
                  Yes            No
                   |              |
              Back off       Register default
                                   |
                                   v
                           Create instance when needed
~~~

**Conditions are not a package-scanning operation.** When a `@Conditional` on the auto-configuration class fails, the import path inside that class is not activated. If another application configuration imports the support class directly, that separate path must be evaluated independently; properties on the auto-configuration do not automatically apply to every way the same class is imported.

**@ConditionalOnMissingBean** also does not appear automatically on every `@Bean` method. The library must explicitly add the annotation when supporting back-off-style user overrides.

## 5. Complete Example with Spring Boot 3.3.13 and Java 21

The goal of the project is to prove simultaneously:

1. Support configuration is imported without scanning the support package.
2. Another `@Component` in the support package **is not automatically registered**.
3. Property `false` disables the auto-configuration branch.
4. Excluding the auto-configuration class differs from a property condition.
5. User-declared beans take precedence when the default has `@ConditionalOnMissingBean`.

**Requirements:** JDK 21, Maven 3.9+, network access to download dependencies. No web server or database needed.

### 5.1. Directory Tree

~~~text
selective-import-demo/
├── pom.xml
└── src/main/
    ├── java/dev/lesson/
    │   ├── api/AuditSink.java
    │   ├── support/AuditSupportConfiguration.java
    │   ├── support/extra/UnrelatedComponent.java
    │   ├── autoconfig/AuditAutoConfiguration.java
    │   └── app/DemoApplication.java
    └── resources/
        ├── application.properties
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

**The application class resides in `dev.lesson.app`**; support and autoconfig are sibling packages of app. Thus, `@SpringBootApplication`'s default `@ComponentScan` does not accidentally pick up classes outside app. This is an essential design condition so the example truly distinguishes the two paths.

### 5.2. pom.xml

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
    <groupId>dev.lesson</groupId>
    <artifactId>selective-import-demo</artifactId>
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

### 5.3. AuditSink Interface

**src/main/java/dev/lesson/api/AuditSink.java**

~~~java
package dev.lesson.api;

@FunctionalInterface
public interface AuditSink {
    String record(String event);
}
~~~

The program cares only about the interface. Auto-configuration can supply a default implementation, while the application retains the right to declare its own implementation.

### 5.4. Explicitly Imported Support Configuration

**src/main/java/dev/lesson/support/AuditSupportConfiguration.java**

~~~java
package dev.lesson.support;

import dev.lesson.api.AuditSink;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class AuditSupportConfiguration {

    @Bean
    @ConditionalOnMissingBean(AuditSink.class)
    AuditSink defaultAuditSink() {
        return event -> "auto:" + event;
    }
}
~~~

This configuration creates a default `AuditSink` **if** no matching bean of the same interface exists yet. `@ComponentScan` is unnecessary for Spring to process the `@Bean` method, because an `@Import` path brings the configuration class into the container.

**proxyBeanMethods=false** fits because the `@Bean` method does not directly invoke other `@Bean` methods. If beans depend on one another, declare dependencies via `@Bean` method parameters rather than calling methods directly and relying on proxy interception.

### 5.5. A Component Present on the Classpath Yet Unrelated to the Feature

**src/main/java/dev/lesson/support/extra/UnrelatedComponent.java**

~~~java
package dev.lesson.support.extra;

import org.springframework.stereotype.Component;

@Component
public class UnrelatedComponent {
}
~~~

In this project, that component is not **@Import**ed and does not fall under component scan of package **dev.lesson.app**. It is still compiled and packaged into the JAR, yet **does not automatically become a bean**.

Do not confuse "class is on the classpath" with "bean exists in ApplicationContext".

### 5.6. Auto-Configuration Enabled by Conditions and Importing Support

**src/main/java/dev/lesson/autoconfig/AuditAutoConfiguration.java**

~~~java
package dev.lesson.autoconfig;

import dev.lesson.api.AuditSink;
import dev.lesson.support.AuditSupportConfiguration;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Import;

@AutoConfiguration
@ConditionalOnClass(AuditSink.class)
@ConditionalOnProperty(
    prefix = "demo.audit",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
@Import(AuditSupportConfiguration.class)
public class AuditAutoConfiguration {
}
~~~

Analysis:

- **@AutoConfiguration** marks the candidate class belonging to Boot's auto-configuration mechanism.
- **@ConditionalOnClass** verifies the `AuditSink` type is present. The demo always includes this class; real libraries may require an optional API.
- **@ConditionalOnProperty** enables the feature when the property is absent or true; when false, the auto-configuration class is not applied.
- **@Import(AuditSupportConfiguration.class)** brings the chosen support configuration into processing. There is no `@ComponentScan` on the support package.
- **@ConditionalOnMissingBean** resides inside the support configuration and decides individually whether to register `defaultAuditSink`.

### 5.7. AutoConfiguration.imports

**src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**

~~~text
dev.lesson.autoconfig.AuditAutoConfiguration
~~~

Note: this file lists **AuditAutoConfiguration**, not **AuditSupportConfiguration** or **UnrelatedComponent**. The support class is orchestrated via `@Import`, while `UnrelatedComponent` is intentionally not loaded.

This is Spring Boot 3.x's mechanism for publishing auto-configuration candidates. Older documentation may describe the `EnableAutoConfiguration` key in `spring.factories`; that is not the new auto-config candidate registration format used in this Boot 3.x project.

### 5.8. Main Application and Optional User Bean

**src/main/java/dev/lesson/app/DemoApplication.java**

~~~java
package dev.lesson.app;

import dev.lesson.api.AuditSink;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Profile;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    @Profile("custom")
    AuditSink customAuditSink() {
        return event -> "user:" + event;
    }

    @Bean
    ApplicationRunner showState(
            ObjectProvider<AuditSink> auditProvider,
            ApplicationContext context) {
        return args -> {
            AuditSink sink = auditProvider.getIfAvailable();
            System.out.println("audit=" +
                (sink == null ? "<none>" : sink.record("Hi")));
            System.out.println("unrelated=" +
                context.containsBean("unrelatedComponent"));
        };
    }
}
~~~

**ObjectProvider** allows checking when `AuditSink` is absent without failing startup due to required injection. Under the **custom** profile, the application declares its own `AuditSink` bean, causing the default bean with `@ConditionalOnMissingBean` to back off.

**src/main/resources/application.properties**

~~~properties
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=OFF
~~~

These settings merely keep output concise. In environments with other logging or agents, extra log lines may appear; below are the lines printed by the demo itself.

### 5.9. Build and Run

In the **selective-import-demo** directory:

~~~bash
mvn -q -DskipTests package
~~~

**Scenario A: using default auto-configuration**

~~~bash
java -jar target/selective-import-demo-0.0.1-SNAPSHOT.jar
~~~

Stdout lines from `ApplicationRunner`:

~~~text
audit=auto:Hi
unrelated=false
~~~

Spring Boot selects `AuditAutoConfiguration` from imports, conditions pass, and `@Import` processes support. `UnrelatedComponent` has no bean because it is neither scanned nor imported.

**Scenario B: disabling the feature via property**

~~~bash
java -jar target/selective-import-demo-0.0.1-SNAPSHOT.jar --demo.audit.enabled=false
~~~

Output:

~~~text
audit=<none>
unrelated=false
~~~

The property causes the condition on `AuditAutoConfiguration` to fail. That auto-config branch's `@Import` path does not process support.

**Scenario C: excluding auto-configuration**

~~~bash
java -jar target/selective-import-demo-0.0.1-SNAPSHOT.jar --spring.autoconfigure.exclude=dev.lesson.autoconfig.AuditAutoConfiguration
~~~

Output:

~~~text
audit=<none>
unrelated=false
~~~

Here Boot removes the auto-configuration from applied candidates; it is not merely a `@Bean` method failing a property match. The observed output matches B, but the reason is different.

**Scenario D: user provides custom implementation**

~~~bash
java -jar target/selective-import-demo-0.0.1-SNAPSHOT.jar --spring.profiles.active=custom
~~~

Output:

~~~text
audit=user:Hi
unrelated=false
~~~

The `customAuditSink` bean was registered by the application, causing **@ConditionalOnMissingBean(AuditSink.class)** on `defaultAuditSink` to fail. The support class may still be imported, yet the default bean is not registered.

**Scenario E: property false while user bean still exists**

~~~bash
java -jar target/selective-import-demo-0.0.1-SNAPSHOT.jar --spring.profiles.active=custom --demo.audit.enabled=false
~~~

Output:

~~~text
audit=user:Hi
unrelated=false
~~~

The property blocks only the library's auto-configuration; it does not disable beans declared independently by the application.

| Scenario | Auto-config applied? | Default AuditSink bean exists? | Custom AuditSink bean exists? | UnrelatedComponent is a bean? |
| --- | --- | --- | --- | --- |
| A | Yes | Yes | No | No |
| B | No, due to condition | No | No | No |
| C | No, due to exclude | No | No | No |
| D | Yes | No, due to back-off | Yes | No |
| E | No, due to condition | No | Yes | No |

### 5.10. Experiment: Widening Component Scan in a Controlled Manner

To prove `UnrelatedComponent` can appear via scanning, you can replace the annotation on the main class with the following snippet **while keeping all other methods/main intact**:

~~~java
@SpringBootApplication(
    scanBasePackages = {
        "dev.lesson.app",
        "dev.lesson.support.extra"
    }
)
public class DemoApplication {
    // Other members as in the full runnable version.
}
~~~

This is only an illustrative annotation snippet, not a standalone file. After widening scan to **dev.lesson.support.extra**, `UnrelatedComponent`'s default bean name is **unrelatedComponent**, so the second line from the runner becomes:

~~~text
unrelated=true
~~~

Do not set `scanBasePackages` to **"dev.lesson"** just to find one support class: that package also contains **dev.lesson.autoconfig** and other library parts. Broad scanning like that can cause configurations not chosen by the intended selector to also be picked up by Spring via component scan.

## 6. When to Use @Import, ImportSelector, or Registrar?

### 6.1. @Import One or Several Fixed Configuration Classes

If a feature always needs two clear support groups:

~~~java
@Import({
    AuditSupportConfiguration.class,
    ConversionSupportConfiguration.class
})
class FeatureAutoConfiguration {
}
~~~

This is an illustration; `ConversionSupportConfiguration` is not defined in the sample project. Every imported class still obeys its own conditions; importing does not turn into immediate object instantiation.

Use this approach when the list of configurations is **stable, bounded, and known at compile time**.

### 6.2. ImportSelector for Dynamic Selection

If the list of classes to import depends on annotation metadata, you can use **ImportSelector**:

~~~java
public class FeatureSelector
        implements org.springframework.context.annotation.ImportSelector {

    @Override
    public String[] selectImports(
            org.springframework.core.type.AnnotationMetadata metadata) {
        return new String[] {
            "dev.lesson.support.AuditSupportConfiguration"
        };
    }
}
~~~

This is a single API example, not a runnable project. You can write **@Import(FeatureSelector.class)** so the selector returns the list of configurations to process.

In typical auto-configurations, **there is no need to build your own selector just to replace Boot's mechanism**; use `@AutoConfiguration`, `AutoConfiguration.imports`, conditions, and `@Import` of specific support classes.

### 6.3. ImportBeanDefinitionRegistrar for Complex Registration

When you must register `BeanDefinition`s with names/types computed by programmatic logic, **ImportBeanDefinitionRegistrar** is an advanced extension point. It can create definitions from `AnnotationMetadata` and the registry. Do not use a registrar if a `@Bean` inside a support configuration already expresses the intent: the simpler approach is easier to read, maintain, and diagnose.

## 7. Risks That Remain Even When Using @Import

Do not merely swap annotation names and ignore design:

1. **SupportConfiguration itself uses broad @ComponentScan**: importing support can still trigger a secondary scan, pulling in many components.
2. **SupportConfiguration transitively imports many modules**: you must trace transitive import paths.
3. **SupportConfiguration is imported in multiple places**: although Spring handles duplicate configurations, registration/condition paths can become hard to reason about; establish one clear orchestration point.
4. **Missing @ConditionalOnMissingBean on defaults**: when an application adds a bean of the same interface, multiple beans and ambiguous injection can occur.
5. **Conditions placed on the wrong tier**: `@ConditionalOnProperty` on auto-config does not automatically block support if support is also imported directly through another branch.
6. **Supporting beans with side effects**: constructors/factory methods that open connections or start background jobs need appropriate conditions so they do not initialize unnecessarily.

The decisive point is **setting feature boundaries**. `@Import` makes boundaries more visible, yet you still need proper conditions, package conventions, bean naming, and lifecycle handling.

## 8. Debugging When an Unintended Bean Appears

Check in order:

1. **Bean name and source class**: was the bean created by a `@Bean`, component scan, or registrar?
2. **Package scan**: which package is `@SpringBootApplication` in? Are `scanBasePackages` or `@ComponentScan` widening it?
3. **Boot imports path**: is the auto-config class in **AutoConfiguration.imports**? Is it excluded or failing a class/property condition?
4. **Supporting @Import**: which classes does auto-config import? Does the support class have `@ComponentScan`, `@Import`, or other `@Bean`s?
5. **User beans and back-off**: is `@ConditionalOnMissingBean` targeting the right type/name?
6. **Instantiation failure**: if the definition exists yet bean creation fails, inspect `BeanCreationException` and the dependency chain.

With the demo project, you can enable condition diagnostics with:

~~~bash
java -jar target/selective-import-demo-0.0.1-SNAPSHOT.jar --debug --logging.level.root=INFO
~~~

The **Condition Evaluation Report** helps find why Boot selected or skipped `AuditAutoConfiguration`. The report is not a tool that proves every bean instance was created; for directly imported beans, you still need to inspect bean metadata and the corresponding configuration path.

If Actuator is added with proper exposure and security configuration, **/actuator/conditions** provides the condition report and **/actuator/beans** provides bean details. Do not expose management endpoints outside trusted environments without access protection.

## 9. Common Mistakes

| Mistake | Truth |
| --- | --- |
| "Having `@Configuration` on the classpath makes Boot import it automatically." | There must be an appropriate import, component scan, or registration path. |
| "`@Import` always scans the package of the imported class." | `@Import` specifies classes/selectors/registrars; it does not scan the entire package. |
| "Having `@Component` always yields a bean." | Only when the class is discovered or registered in the container. |
| "Auto-configuration needs `@ComponentScan` to find support." | Normally it should import specific support configurations. |
| "`@Import` bypasses `@Conditional`." | Conditions are still evaluated on the relevant classes/methods. |
| "A property disabling auto-config deletes application beans." | No; user-defined beans have their own lifecycle and registration path. |
| "`@ConditionalOnMissingBean` applies automatically to every `@Bean`." | It must be declared on the branch intended to back off. |
| "`@ComponentScan` and `AutoConfiguration.imports` are the same mechanism." | One is package-based; the other publishes auto-config candidates. |
| "Importing support means the bean instance is already created." | Registering a definition and instantiating an instance are two distinct stages. |
| "Scanning the whole library is always faster." | It can create unintended beans and couple configuration to package layout. |

## 10. Self-Check

**Question 1.** `AuditSupportConfiguration` and `UnrelatedComponent` both reside under the support package. If you only `@Import(AuditSupportConfiguration.class)`, does `UnrelatedComponent` register itself?

**Answer:** No, unless that class is scanned/imported/registered via another path. Being in the same package is not enough.

**Question 2.** The support class is outside component scan, so why do its `@Bean` methods still work?

**Answer:** `@Import` brings the configuration class into configuration processing. Spring can register eligible `@Bean` methods from that class.

**Question 3.** Can `@Import` take an `ImportSelector`?

**Answer:** Yes. Spring Framework supports configuration classes, components, `ImportSelector`, and `ImportBeanDefinitionRegistrar`. For a fixed set of support classes, direct import is usually easier to understand.

**Question 4.** What will the scenario with property false while the custom profile is active print?

**Answer:** `audit=user:Hi` and `unrelated=false`. Auto-configuration properties do not remove application beans.

**Question 5.** What if `AuditAutoConfiguration` is excluded yet the application itself `@Import(AuditSupportConfiguration.class)`?

**Answer:** The support class can still be processed along the application's explicit import path. Boot exclusions do not automatically disable all independent import paths.

**Question 6.** Why shouldn't you `@ComponentScan` an entire library's autoconfig package?

**Answer:** It can cause auto-configuration classes to be processed outside Boot's standard candidate selection, ordering, and exclusion mechanisms.

**Question 7.** If a user `AuditSink` bean exists yet is lazy, can `defaultAuditSink` still back off?

**Answer:** Yes. `@ConditionalOnMissingBean` inspects registered bean information; it does not require the user instance to be already instantiated.

**Question 8.** Should `@ComponentScan` be put on a support class to make it "easy to add beans later"?

**Answer:** Only when you genuinely need multi-component discovery and have designed clear conditions/filters. If a feature needs only a few supporting beans, declaring explicit `@Bean` methods or importing specific configurations is easier to control.

## 11. Takeaways

In regular applications, **@ComponentScan** is very useful for finding the application's own components. Yet in a Spring Boot library, especially inside an **@AutoConfiguration** class, prefer **@Import of purposefully chosen supporting configurations**, rather than broad scanning of library packages. When multiple beans are needed, group them into a `SupportConfiguration` with explicit `@Bean` methods and conditions.

The right mental flow:

~~~text
Auto-config candidate from AutoConfiguration.imports
             |
             v
Conditions and excludes decide the branch
             |
             v
@Import specifies support configuration
             |
             v
@Bean methods have conditions evaluated and definitions registered
             |
             v
Instances are created per scope/dependency/lifecycle
~~~

Another class in the same package, even with `@Component`, still **does not automatically become a bean** without a scan/import/registration path. That is the concrete payoff of selective supporting-component imports: the container reflects enabled features, not every class that happens to sit in a package.

### References

- Spring Boot, *Creating Your Own Auto-configuration*: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- Spring Boot, *Auto-configuration*: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
- Spring Framework, *Using the @Import Annotation*: https://docs.spring.io/spring-framework/reference/core/beans/java/composing-configuration-classes.html
- Spring Framework, *Classpath Scanning and Managed Components*: https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html
- Spring Framework, **@Import** API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/Import.html
