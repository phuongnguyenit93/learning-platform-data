# Distinguishing Importing One Class with @Import from Enabling @EnableAutoConfiguration

## 1. Two Tools Solving Two Different Questions

In Spring Framework, **@Import** allows a configuration class to bring **explicitly specified configurations, components, or import mechanisms** into container processing. In Spring Boot, **@EnableAutoConfiguration** turns on **the mechanism to discover and select a set of candidate auto-configuration classes based on classpath, metadata, exclusion rules, and actual conditions**.

Therefore, the appropriate question when seeing the two annotations is:

- **@Import(FooConfiguration.class)**: "Bring the specifically named FooConfiguration into the active configuration set."
- **@EnableAutoConfiguration**: "Find the auto-configurations published by libraries, drop excluded or ineligible ones, and process the qualifying branches."

An important nuance: **@EnableAutoConfiguration itself uses @Import**, yet it imports an **AutoConfigurationImportSelector**, rather than hardcoding a list of every auto-configuration in the annotation. Thus there is no contradiction in saying @Import is Spring's underlying mechanism while @EnableAutoConfiguration is Spring Boot's higher-level feature.

**Do not think of @Import as "guaranteed to create an object"**: importing a configuration makes Spring process the relevant bean definitions; conditions, scope, lazy initialization, and initialization failures still decide which beans are registered and when instances are created.

## 2. Side-by-Side Comparison Table

| Aspect | @Import(FooConfiguration.class) | @EnableAutoConfiguration |
| --- | --- | --- |
| Unit of control | A class or selector/registrar explicitly named at the import site | A selection system across many candidate auto-configuration classes |
| Who decides configuration names | The code author on the annotation or an explicitly named ImportSelector | Libraries publish candidates and Spring Boot's selector filters them |
| Discovery source | Class literal in the annotation; for a selector, decided by the selector | **AutoConfiguration.imports** files on the Spring Boot 3.x runtime classpath |
| Automatically finds all auto-configurations on classpath? | No, when directly importing a single class | Has a mechanism to read candidate lists and filter |
| Evaluates @Conditional? | Yes, if the imported class or its @Beans carry conditions | Yes, on the auto-configuration class and relevant bean methods |
| Supports "back off"? | Potentially yes, if the imported configuration declares **@ConditionalOnMissingBean** | Commonly uses **@ConditionalOnMissingBean** to yield defaults to the application |
| Processing order | Follows Spring's configuration/import processing; depends on imported object type | Uses **DeferredImportSelector** and auto-configuration before/after rules |
| Spring Boot exclusion mechanism | Not meant to "remove all direct @Imports" | Supports exclude/excludeName and **spring.autoconfigure.exclude** for auto-configuration |
| Relationship to component scan | Does not require component scan to import the named class | Does not require component scan to find candidate auto-configuration classes |
| When to use? | Application wants to explicitly assemble a module or enable a known configuration | Application wants Boot to configure components matching dependencies and environment |

The row in the table for "@Import" describes **@Import targeting a single class**. **@Import** itself also accepts **ImportSelector**, **DeferredImportSelector**, and **ImportBeanDefinitionRegistrar**, so more sophisticated selection strategies can be implemented. This very detail explains why @EnableAutoConfiguration can be built on top of @Import.

## 3. What Does @Import Actually Do?

### 3.1. Importing a Known Configuration Class

A common case:

~~~java
package dev.lesson.manual;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class MailClientConfiguration {

    @Bean
    MailClient mailClient() {
        return new MailClient();
    }
}
~~~

~~~java
package dev.lesson.app;

import dev.lesson.manual.MailClientConfiguration;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Configuration;

@Configuration
@Import(MailClientConfiguration.class)
public class AppConfiguration {
}
~~~

These are **two explanatory code fragments**, not a standalone runnable project: the **MailClient** class is not defined. The goal is to see that Spring knows the exact configuration class to process: **MailClientConfiguration**. It does not have to read every starter's auto-configuration list to find that class.

When Spring processes AppConfiguration, it examines the imported configuration, and can thereby register the **mailClient()** bean definition. If the imported class or method carries **@Conditional**, those conditions still apply. If it is a lazy bean, the instance may not be created yet when the definition appears.

MailClientConfiguration does not need to reside in a package scanned by **@ComponentScan**: the import path already names the class explicitly. This is helpful when wiring an internal library or a group of beans that must be enabled explicitly.

### 3.2. @Import Accepts More Than @Configuration

Under Spring Framework's mechanism, **@Import** can point to:

1. **A configuration or component class** processed by Spring to register its corresponding beans.
2. **ImportSelector**: programmatically computes the list of configuration classes to import.
3. **DeferredImportSelector**: a selector variant scheduled for deferred processing during configuration parsing.
4. **ImportBeanDefinitionRegistrar**: directly registers additional bean definitions via the registry API.

An illustrative selector example, not a standalone program:

~~~java
class FeatureSelector implements org.springframework.context.annotation.ImportSelector {
    @Override
    public String[] selectImports(
            org.springframework.core.type.AnnotationMetadata metadata) {
        return new String[] {"dev.lesson.manual.MailClientConfiguration"};
    }
}
~~~

~~~java
@Import(FeatureSelector.class)
class SelectedFeatureConfiguration {
}
~~~

In this case, the code at the import site does not list MailClientConfiguration; the selector decides the list. Hence claiming "@Import **always** loads strictly the one class written inside parentheses" is false. The real distinction from **@EnableAutoConfiguration** is that the selection strategy **is provided by Spring Boot**, based on the auto-configuration lists in JARs and conditions standardized by Boot.

### 3.3. Importing Does Not Mean Bypassing Conditions

Suppose a directly imported configuration has a condition:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
    prefix = "lesson.manual",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
class ManualFeatureConfiguration {
    // @Bean methods of this configuration.
}
~~~

This snippet illustrates the annotation, not a standalone runnable Java file. If **lesson.manual.enabled=false**, the class can be skipped by the condition even though it was specified via @Import. The difference from auto-configuration lies in **how candidates are discovered and selected**, not in @Import ignoring all conditions.

## 4. How Is @EnableAutoConfiguration Built on @Import?

In Spring Boot 3.x, **@EnableAutoConfiguration** attaches two core mechanisms:

- **@AutoConfigurationPackage**: records the default package serving certain auto-configured features, such as entity/repository discovery mechanisms when applicable.
- **@Import(AutoConfigurationImportSelector.class)**: registers Boot's dedicated auto-configuration selector.

Simplified structural model:

~~~java
@AutoConfigurationPackage
@Import(AutoConfigurationImportSelector.class)
public @interface EnableAutoConfiguration {
    Class<?>[] exclude() default {};
    String[] excludeName() default {};
}
~~~

This is **not** the full annotation source code to copy into a project. The purpose is to see the path from **@EnableAutoConfiguration** to **@Import**.

Normally developers write:

~~~java
@SpringBootApplication
public class Application {
}
~~~

**@SpringBootApplication** carries the core semantics of **@SpringBootConfiguration**, **@EnableAutoConfiguration**, and **@ComponentScan**. Therefore an application with @SpringBootApplication already has auto-configuration enabled and does not need @EnableAutoConfiguration added a second time.

### 4.1. What Is AutoConfigurationImportSelector?

**AutoConfigurationImportSelector** implements **DeferredImportSelector**. It coordinates discovering and selecting auto-configuration classes before they are processed as eligible imports. "Deferred" means processing these imports is postponed within Spring's configuration class parsing; this is part of how configurations explicitly declared by the application are evaluated before Boot's defaults.

However, **do not** infer from "deferred" that all application bean instances have already been created before auto-config runs. **Bean definition** registration and **instance instantiation** are two distinct logical phases. A **@ConditionalOnMissingBean** condition relies on bean metadata already processed in the container at evaluation time, without requiring that bean's object to be constructed yet.

### 4.2. Where Does Boot Discover Candidates?

In Spring Boot 3.x, libraries supply the candidate list in a resource with the exact name:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

A resource may contain:

~~~text
dev.lesson.autoconfig.AutoFeatureAutoConfiguration
dev.lesson.autoconfig.CacheFeatureAutoConfiguration
~~~

Each line is the name of an auto-configuration class eligible **to be considered**, not a guarantee it will be instantiated. JARs present on the runtime classpath provide their corresponding resources. Adding/removing a starter or changing dependencies can alter both the candidate list and whether **@ConditionalOnClass** passes.

**Do not confuse with @ComponentScan**: an auto-configuration class usually sits outside the application's scan packages, yet Boot still finds it via the imports file. Conversely, placing **@AutoConfiguration** on a class without registering it through the proper imports mechanism will not make Boot find the class automatically from that annotation name alone.

Legacy documentation used the EnableAutoConfiguration key in **META-INF/spring.factories**. In Spring Boot 3.x, the candidate declaration format is **AutoConfiguration.imports**. The spring.factories file still serves other SPI purposes; do not use memories of the old format to alter the imports path of a Boot 3 library.

### 4.3. Filtering Candidates, Exclusions, and Condition Checks

You can visualize the workflow:

~~~text
Application starts with @EnableAutoConfiguration
                    |
                    v
@Import(AutoConfigurationImportSelector.class)
                    |
                    v
Locate AutoConfiguration.imports files on runtime classpath
                    |
                    v
Initial candidate set, deduplicate and apply exclusions
                    |
                    v
Filter using metadata/applicable conditions
                    |
                    v
Import remaining eligible configurations into processing
                    |
                    v
Evaluate @Conditional on class and @Beans
                    |
       +------------+---------------+
       |                            |
   Not met                      Conditions met
       |                            |
Skip corresponding branch     Register bean definition
                                    |
                                    v
                      Container creates instance per lifecycle
~~~

This diagram is **simplified**; Spring has multiple parsing/registration passes and certain conditions are evaluated at different moments. A class may be a candidate, even get processed, while one @Bean method inside it is still skipped individually.

Common conditions:

| Annotation | Question Spring Boot Uses to Decide |
| --- | --- |
| **@ConditionalOnClass** | Is the required class/library on the classpath? |
| **@ConditionalOnMissingClass** | Is the target class absent? |
| **@ConditionalOnProperty** | Does the final property in Environment have the matching value? |
| **@ConditionalOnBean** | Does a bean of that type/name already exist in the matching search scope? |
| **@ConditionalOnMissingBean** | Is no matching bean present yet so the default can yield? |
| **@ConditionalOnWebApplication** | Is this the web application type required by the branch? |
| **@ConditionalOnResource** | Does the resource needed by the branch exist? |

For example, an auto-config creates a default bean when an API class is present, a property is enabled, and no user bean exists yet. If any one of those conditions fails, **the default bean branch** is skipped. Adding a dependency only gives certain conditions a chance to pass; it does not turn **@EnableAutoConfiguration** into "turn everything on".

### 4.4. Being Excluded Differs from Failing a Condition

Spring Boot supports excluding an **auto-configuration class** via:

- **@EnableAutoConfiguration(exclude = SomeAutoConfiguration.class)**.
- **@EnableAutoConfiguration(excludeName = "package.SomeAutoConfiguration")**.
- **@SpringBootApplication(exclude = ...)** or the corresponding **excludeName**.
- The **spring.autoconfigure.exclude** property listing auto-configuration class names to exclude.

Exclusion acts on the **auto-configuration selection path**. It **does not mean** Spring automatically undoes a configuration class that the application **@Import**ed directly via another path. If you write **@Import(XConfiguration.class)** yourself, control that import through your own configuration or conditions; do not blindly expect **spring.autoconfigure.exclude** to strip manual imports. In particular, **directly importing an internal Boot auto-configuration class** is not a recommended customization approach: those classes are implementation details and may change across versions.

## 5. Runnable Example: Same Application Using Both @Import and @EnableAutoConfiguration

We build a small project with **Java 21, Spring Boot 3.3.13, Maven 3.9+**. The exercise isolates three processing paths:

1. **ManualFeatureConfiguration** imported via explicit **@Import**.
2. **AutoFeatureAutoConfiguration** discovered via **AutoConfiguration.imports** when **@EnableAutoConfiguration** is enabled.
3. A user-declared bean, enabled by the **custom** Spring profile, causing auto-config to back off via **@ConditionalOnMissingBean**.

**@ComponentScan** is not used in the example so that no class can be discovered by package scanning, making the two import paths clearly visible.

Directory structure:

~~~text
import-vs-auto/
├── pom.xml
└── src/main/
    ├── java/dev/lesson/
    │   ├── api/
    │   │   ├── ManualMarker.java
    │   │   └── AutoMarker.java
    │   ├── manual/
    │   │   └── ManualFeatureConfiguration.java
    │   ├── autoconfig/
    │   │   └── AutoFeatureAutoConfiguration.java
    │   └── app/
    │       └── LessonApplication.java
    └── resources/
        ├── application.properties
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

### 5.1. Declaring Dependencies

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
    <groupId>dev.lesson</groupId>
    <artifactId>import-vs-auto</artifactId>
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

The basic starter is sufficient for Spring Boot, Spring Context, and the auto-configuration mechanism. No web server, database, or starter-web is needed for this example.

### 5.2. Two Bean Types to Observe

**src/main/java/dev/lesson/api/ManualMarker.java**

~~~java
package dev.lesson.api;

public record ManualMarker(String source) {
}
~~~

**src/main/java/dev/lesson/api/AutoMarker.java**

~~~java
package dev.lesson.api;

public record AutoMarker(String source) {
}
~~~

Both records are simple types that help observe which bean is present and which source supplied it.

### 5.3. Configuration Directly Imported via @Import

**src/main/java/dev/lesson/manual/ManualFeatureConfiguration.java**

~~~java
package dev.lesson.manual;

import dev.lesson.api.ManualMarker;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
    prefix = "lesson.manual",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
public class ManualFeatureConfiguration {

    @Bean
    ManualMarker manualMarker() {
        return new ManualMarker("imported");
    }
}
~~~

This class is explicitly named by the application via **@Import(ManualFeatureConfiguration.class)**. Here we intentionally add **@ConditionalOnProperty** to prove: even a directly imported configuration can be dropped by a condition. When the property is absent, **matchIfMissing=true** allows the configuration to apply.

### 5.4. Auto-Configuration as a Boot Candidate

**src/main/java/dev/lesson/autoconfig/AutoFeatureAutoConfiguration.java**

~~~java
package dev.lesson.autoconfig;

import dev.lesson.api.AutoMarker;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(AutoMarker.class)
public class AutoFeatureAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(AutoMarker.class)
    @ConditionalOnProperty(
        prefix = "lesson.auto",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
    )
    AutoMarker defaultAutoMarker() {
        return new AutoMarker("default");
    }
}
~~~

In this project **AutoMarker** is always on the classpath. The class condition illustrates how Boot normally guards auto-configurations that depend on optional APIs; when writing a standalone library starter, the API may come from an external dependency and not always be present.

**src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**

~~~text
dev.lesson.autoconfig.AutoFeatureAutoConfiguration
~~~

It is this resource that puts AutoFeatureAutoConfiguration into the candidate set. The main application will not directly @Import this class. The **dev.lesson.autoconfig** package also sits outside the main class's package **dev.lesson.app**; the example does not enable component scan, so there is no accidental path picking up the class from component scanning.

### 5.5. Main Class Declaring Two Different Mechanisms

**src/main/java/dev/lesson/app/LessonApplication.java**

~~~java
package dev.lesson.app;

import dev.lesson.api.AutoMarker;
import dev.lesson.api.ManualMarker;
import dev.lesson.manual.ManualFeatureConfiguration;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Profile;

@SpringBootConfiguration(proxyBeanMethods = false)
@EnableAutoConfiguration
@Import(ManualFeatureConfiguration.class)
public class LessonApplication {

    public static void main(String[] args) {
        SpringApplication.run(LessonApplication.class, args);
    }

    @Bean
    @Profile("custom")
    AutoMarker userAutoMarker() {
        return new AutoMarker("user");
    }

    @Bean
    ApplicationRunner showSources(
            ObjectProvider<ManualMarker> manualProvider,
            ObjectProvider<AutoMarker> autoProvider) {

        return args -> {
            ManualMarker manual = manualProvider.getIfAvailable();
            AutoMarker automatic = autoProvider.getIfAvailable();

            System.out.println("manual=" +
                (manual == null ? "absent" : manual.source()));
            System.out.println("auto=" +
                (automatic == null ? "absent" : automatic.source()));
        };
    }
}
~~~

**Why not use @SpringBootApplication in this runnable lesson?** The purpose is to display the two annotations being compared right on the main class without pulling in **@ComponentScan**. **@SpringBootConfiguration** marks the application configuration class; **@EnableAutoConfiguration** enables Boot's selector; **@Import(ManualFeatureConfiguration.class)** explicitly names the manual configuration.

For normal production applications, **@SpringBootApplication** is the concise and recommended choice; splitting the annotations in this lesson serves to study the mechanism.

The **userAutoMarker()** bean exists only when the **custom** Spring profile is active; it verifies the mechanism of automatically yielding to a user bean. **ObjectProvider** lets the application keep running when a bean is absent. If **AutoMarker** were injected directly as a required dependency, scenarios disabling auto-config would fail startup due to a missing bean.

**src/main/resources/application.properties**

~~~properties
spring.main.banner-mode=off
logging.level.root=OFF
~~~

This setting simply focuses output on the two demo lines; it does not affect the conditions defined in the lesson. When you need to inspect the condition report, override logging as guided in the diagnostics section.

### 5.6. Building and Running

Prepare JDK 21 and Maven 3.9+, positioned in the **import-vs-auto** directory:

~~~bash
mvn -q -DskipTests package
~~~

**Scenario A — No properties passed, both sources present:**

~~~bash
java -jar target/import-vs-auto-0.0.1-SNAPSHOT.jar
~~~

Two lines printed by the program:

~~~text
manual=imported
auto=default
~~~

Explanation: **@Import** brings ManualFeatureConfiguration into processing; the manual property is undeclared so the default condition allows it. **@EnableAutoConfiguration** finds AutoFeatureAutoConfiguration via imports; class and property conditions pass and no user AutoMarker bean exists yet, so default is registered.

**Scenario B — Disabling the bean from auto-configuration via property:**

~~~bash
java -jar target/import-vs-auto-0.0.1-SNAPSHOT.jar --lesson.auto.enabled=false
~~~

Output:

~~~text
manual=imported
auto=absent
~~~

AutoFeatureAutoConfiguration can still be a candidate found by the selector. However, the **defaultAutoMarker** method is not registered because **@ConditionalOnProperty** fails. Disabling the auto branch's property **does not affect** ManualFeatureConfiguration, which is imported independently.

**Scenario C — Excluding the entire auto-configuration class:**

~~~bash
java -jar target/import-vs-auto-0.0.1-SNAPSHOT.jar --spring.autoconfigure.exclude=dev.lesson.autoconfig.AutoFeatureAutoConfiguration
~~~

Output:

~~~text
manual=imported
auto=absent
~~~

The output looks identical to Scenario B yet **the root cause differs**: here the auto-configuration class is removed from selection, rather than merely a bean method failing a property condition. Manual **@Import** of ManualFeatureConfiguration remains active and still creates its bean.

**Scenario D — Disabling the condition inside the directly @Imported configuration:**

~~~bash
java -jar target/import-vs-auto-0.0.1-SNAPSHOT.jar --lesson.manual.enabled=false
~~~

Output:

~~~text
manual=absent
auto=default
~~~

This refutes the misconception that "@Import forces every bean in that class to be created". **@ConditionalOnProperty** on ManualFeatureConfiguration still works normally; meanwhile the auto branch is unaffected.

**Scenario E — User supplies their own AutoMarker:**

~~~bash
java -jar target/import-vs-auto-0.0.1-SNAPSHOT.jar --spring.profiles.active=custom
~~~

Output:

~~~text
manual=imported
auto=user
~~~

When the **custom** profile is active, **userAutoMarker()** registers the application-defined bean. Because the default in AutoFeatureAutoConfiguration carries **@ConditionalOnMissingBean(AutoMarker.class)**, the default branch backs off. This is a conditional rule, **not a spontaneous effect of @Import or a same-name bean overriding mechanism**.

**Scenario F — Property disables default, yet user bean still exists:**

~~~bash
java -jar target/import-vs-auto-0.0.1-SNAPSHOT.jar --spring.profiles.active=custom --lesson.auto.enabled=false
~~~

Output:

~~~text
manual=imported
auto=user
~~~

The default's property controls only the default branch; it does not automatically disable the userAutoMarker bean belonging to application configuration.

### 5.7. Trying Complete Removal of @EnableAutoConfiguration to Compare

In **LessonApplication.java**, remove only the **@EnableAutoConfiguration** annotation and its corresponding Java import line; **keep @SpringBootConfiguration, @Import(ManualFeatureConfiguration.class), and @Bean ApplicationRunner**. Then rebuild with the same commands:

~~~bash
mvn -q -DskipTests package
java -jar target/import-vs-auto-0.0.1-SNAPSHOT.jar
~~~

Expected output under default configuration without the custom profile:

~~~text
manual=imported
auto=absent
~~~

When @EnableAutoConfiguration is removed, no Boot selector reads AutoConfiguration.imports for this application anymore. ManualFeatureConfiguration still follows the direct **@Import** path and is processed. This is the clearest contrast in functional difference between the two annotations.

Restore **@EnableAutoConfiguration** after this experiment if you want to rerun scenarios A–F. In an application using **@SpringBootApplication** instead of the three separate annotations, auto-configuration is already enabled indirectly; removing a redundant @EnableAutoConfiguration written elsewhere will not turn that mechanism off.

## 6. Why Shouldn't You @Import Every Auto-Configuration Class Directly?

A common thought: "If Boot also uses @Import, why don't I import AutoFeatureAutoConfiguration directly into the app—why bother with @EnableAutoConfiguration?" Doing so causes a class to be processed like an explicit configuration, yet **bypasses the architectural purpose** of the auto-configuration mechanism:

1. **Dynamic configuration set per library:** When starters are added/removed, Boot can evaluate auto-configurations published by the JARs. Manually importing a fixed list forces the application to maintain the list itself.
2. **Standard exclusion mechanism:** Dropping a candidate from the auto-configuration selector does not remove direct @Import paths to that same class.
3. **Ordering and group processing:** Auto-configurations are ordered and processed by Boot's selector mechanism, supporting conditions that inspect existing beans. Importing a class directly can change processing timing from what the library author intended.
4. **API boundaries:** Internal auto-configuration classes are typically treated as implementation details. Spring Boot recommends customizing via properties, user beans, or intentional exclusions rather than depending on internal auto-config source code.
5. **Do not component-scan auto-configs:** If an auto-configuration class is discovered by @ComponentScan like an ordinary component, it can go through a path outside the intended selector and make outcomes unpredictable.

Even so, **@Import is a completely appropriate tool** for assembling a configuration supplied by your application or library such as **ManualFeatureConfiguration**. The point is choosing the right contract: **explicit wiring** uses @Import; **proposing environment-aware defaults** writes an auto-configuration registered via imports and lets @EnableAutoConfiguration process it.

## 7. Subtle Misconceptions to Avoid

### 7.1. "@Import does not evaluate @Conditional"

False. Spring Framework processes conditions on imported configuration classes and bean methods. Case D in the example proves ManualFeatureConfiguration is skipped when **lesson.manual.enabled=false**. The difference lies in how candidates are loaded, not in import granting a right to "bypass" conditions.

### 7.2. "@EnableAutoConfiguration is equivalent to @ComponentScan"

False. Component scan locates components by package and stereotype annotations; auto-configuration finds candidate classes from imports files and applies conditions. Both tools often coexist inside **@SpringBootApplication**, yet they retain distinct roles. If a **@Service** sits outside the scan package, merely enabling auto-configuration does not guarantee that service will be discovered. Likewise, an auto-configuration can sit outside the scan package yet still be processed by Boot via the selector.

### 7.3. "Just putting @AutoConfiguration on a class makes Boot load it automatically"

False in Spring Boot 3.x. A library's auto-configuration class must be declared in **META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports** to participate in candidate discovery. Directly @Importing a configuration via another path is a separate case and does not prove auto-configuration registration is configured properly.

### 7.4. "If a class is in imports, all of its beans have been created"

False. **Imports** only puts the class into the candidate list. Afterward come exclusions and class/method conditions. Even when a BeanDefinition is registered, the instance may be lazy or fail during creation. In the example, setting the property to false prevents the default method from creating a bean even though the auto-config class is present.

### 7.5. "@ConditionalOnMissingBean is an automatic property of every @AutoConfiguration"

False. **@ConditionalOnMissingBean** is a conditional annotation that the configuration author must declare wherever a default should back off. Not every @Bean inside an @AutoConfiguration class automatically yields when the application declares a bean of the same type.

### 7.6. "@Import always takes strictly one class and nothing else"

False. **@Import** can import multiple classes, an ImportSelector, a DeferredImportSelector, or an ImportBeanDefinitionRegistrar. **@EnableAutoConfiguration** leverages the import selector form. When reading source code, inspect the type passed to @Import, not just the annotation name.

### 7.7. "Order inside the imports file determines constructor execution order"

False. Spring Boot provides auto-configuration ordering metadata such as **@AutoConfiguration(before = ...)** and **after = ...** to guide configuration processing order. These primarily affect when **bean definitions** are processed. Instances are created based on lifecycle and dependencies; object instantiation order does not automatically match line order in the imports file.

### 7.8. "Using spring.autoconfigure.exclude disables every class with that name everywhere"

Do not assume that. The exclude property is designed to drop **auto-configuration candidates** through Boot's mechanism. If application code still directly @Imports a class or creates the bean itself, inspect that path separately. In particular, avoid directly importing internal auto-configurations while expecting all exclusion/ordering modes to behave identically to selector management.

## 8. Debugging: When You Don't Know Which Path a Bean Came From

When a bean is unexpectedly present or absent, break the question into steps:

1. **Find the registration source**: is the bean in a @Bean method of a directly imported application class, component scan, or an auto-configuration class? Read the declaring class and its annotations.
2. **Check annotations on the main class**: is @SpringBootApplication or @EnableAutoConfiguration present? Are there manual @Imports? Is there an unexpected component scan?
3. **If it is auto-config**: check the JAR containing the class and its AutoConfiguration.imports file, exclusion rules, and class/method conditions.
4. **If it is direct @Import**: check the import annotation, the target configuration class, any @Conditionals, and import order. Do not rely on Boot's condition report as the sole source for ordinary configurations.
5. **Check user beans**: is there a matching bean causing @ConditionalOnMissingBean to fail? Does a profile alter the definition set?
6. **Distinguish registration from startup**: a bean with a definition that fails during constructor/injection/init is an instantiation issue—read the stack trace rather than only the condition report.

For the example in section 5, to view the **Condition Evaluation Report**, run:

~~~bash
java -jar target/import-vs-auto-0.0.1-SNAPSHOT.jar --debug --logging.level.root=INFO
~~~

The report explains which auto-configurations matched/did not match, which candidates were excluded, and the specific condition reasons. When running scenario B, look for the property condition on **defaultAutoMarker**; when enabling the custom profile, inspect the **@ConditionalOnMissingBean** branch. Scenario C excludes the candidate from the selector, which differs from a negative match on a method.

**The condition report does not prove every bean instance was instantiated successfully**. If a constructor or dependency error occurs, inspect the **BeanCreationException** message. For directly imported configurations not in the auto-configuration list, also use BeanFactory APIs, configuration logs, and actual bean checks; do not infer backward that because something is absent from the report, @Import did not run.

When Actuator is added and endpoints are appropriately configured, **/actuator/conditions** exposes condition results as JSON. Endpoints are not public by default; configure exposure and authorization appropriately for your environment. **/actuator/beans** helps inspect beans known to the context, yet also does not replace identifying the registration source.

## 9. Which Approach to Choose in Practice?

| Need | Suitable Tool | Reason |
| --- | --- | --- |
| Application always wants to load a specific team-owned configuration | **@Import(MyConfiguration.class)** | Explicit, tight control over which class is processed |
| Creating a custom annotation to enable a well-defined module group | Meta-annotation using **@Import** or an appropriate ImportSelector | Bundles wiring according to the library's contract |
| Library wants to propose default beans when added to a Boot app | **@AutoConfiguration**, **AutoConfiguration.imports** file, appropriate conditions | Compatible with candidate selection and back-off |
| Ordinary Boot application needs auto-configuration features | **@SpringBootApplication** | Already includes @EnableAutoConfiguration and required startup roles |
| Want to change parameters of an auto-configured bean | Supported properties | No need to import internal classes directly |
| Want to supply your own bean instead of the default | **@Bean** in user configuration, verify @ConditionalOnMissingBean | Boot can yield defaults when designed to back off |
| Want to disable one specific auto-configuration | **exclude/excludeName/spring.autoconfigure.exclude** | Removes the class from the corresponding selector mechanism |
| Want to see why an auto-config was dropped | **Condition Evaluation Report** | Shows positive/negative matches, exclusions, and reasons |

The design distinction is meaningful: **@Import** expresses an explicit wiring decision by the application; **@EnableAutoConfiguration** activates an engine proposing conditional configurations based on the application's actual capabilities and library-published candidates.

## 10. Self-Assessment Exercises

**Question 1.** An application uses **@Import(CacheConfiguration.class)** without enabling @EnableAutoConfiguration. CacheConfiguration has no conditions and has a normal singleton @Bean. Can Spring register a bean from that configuration?

**Answer:** Yes, because direct @Import is enough to bring the configuration class into processing. No auto-configuration selector is required. Instance creation still depends on lifecycle.

**Question 2.** **XAutoConfiguration** is in **AutoConfiguration.imports** and on the classpath, yet the property enabling one of its @Beans is false. Does that class create the bean?

**Answer:** No, if the bean's condition requires that property to be true. Presence in the candidate list does not mean the bean method matches.

**Question 3.** A project has @SpringBootApplication. Is adding @EnableAutoConfiguration again necessary to turn on auto-configuration?

**Answer:** No. @SpringBootApplication already includes @EnableAutoConfiguration; adding a duplicate annotation is redundant and harms readability.

**Question 4.** In the runnable example, remove @EnableAutoConfiguration while keeping @Import(ManualFeatureConfiguration.class). What are the two output lines under default configuration?

**Answer:**

~~~text
manual=imported
auto=absent
~~~

**Question 5.** Keep @EnableAutoConfiguration enabled, yet run with **--lesson.manual.enabled=false**. Why does the manual bean disappear?

**Answer:** @Import brings the configuration into processing, yet **@ConditionalOnProperty** on ManualFeatureConfiguration fails. Importing does not bypass conditions.

**Question 6.** Why is **@EnableAutoConfiguration** both different from direct @Import and related to @Import?

**Answer:** @EnableAutoConfiguration **uses @Import(AutoConfigurationImportSelector.class)** to activate a selector. The import mechanism is the underlying tool; how the selector discovers candidate lists across JARs, evaluates conditions, and handles exclusions is the behavior specific to Spring Boot.

**Question 7.** An auto-configuration has @ConditionalOnMissingBean(Client.class), and the application imports its own configuration registering a Client bean that is lazy. Can the default still back off before the lazy Client is instantiated?

**Answer:** Yes. The missing-bean condition inspects bean metadata already processed in the container and does not require the lazy object to be instantiated first.

**Question 8.** Why shouldn't you directly @Import internal Spring Boot auto-configuration classes to "save on" using @EnableAutoConfiguration?

**Answer:** Doing so couples the application to implementation details and bypasses standard candidate discovery, filtering, and ordering mechanics. Prefer properties, conditional bean overrides/back-off, or intentional exclusions.

## 11. Key Takeaways

**@Import** is about **configurations brought into processing through an explicitly specified import path**; it can import a concrete class or a selector/registrar. **@EnableAutoConfiguration** is about **activating Spring Boot's workflow to discover and select candidate auto-configurations based on classpath, imports metadata, exclusions, and conditions**. The core distinction is *how configurations are discovered and selected*, not one side having conditions while the other does not.

When debugging any bean, trace its registration source first: **direct @Import, component scan, or auto-configuration candidate**. Only then ask whether conditions passed, whether the definition was registered, and whether the instance instantiated cleanly. Separating these questions lets you accurately predict behavior when adding starters, changing properties, declaring user beans, excluding auto-configurations, or restructuring modules.

### References

- Spring Framework, *Using the @Import Annotation*: https://docs.spring.io/spring-framework/reference/core/beans/java/composing-configuration-classes.html
- Spring Framework, **@Import** API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/Import.html
- Spring Framework, **ImportSelector** API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/ImportSelector.html
- Spring Boot, *Auto-configuration*: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
- Spring Boot, *Creating Your Own Auto-configuration*: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- Spring Boot, **@EnableAutoConfiguration** API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/EnableAutoConfiguration.html
