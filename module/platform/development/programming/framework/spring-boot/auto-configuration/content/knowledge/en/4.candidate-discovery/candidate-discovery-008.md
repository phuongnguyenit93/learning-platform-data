# Coordinating Candidates via DeferredImportSelector Groups and Configuration Ordering

## 1. Problem: When Multiple Auto-Configurations Are Discovered, Which One Is Processed First?

In a Spring Boot application, multiple libraries can publish dozens or hundreds of **auto-configuration** classes. When the application enables **@EnableAutoConfiguration**, Spring Boot must do more than read a list of class names: it must **collect candidates**, apply **exclusions and pre-filtering**, **sort configurations with ordering constraints**, and only then feed them into Spring's configuration processing pipeline.

The key lies in Spring Framework providing **DeferredImportSelector** and the **DeferredImportSelector.Group** mechanism. Spring Boot uses **AutoConfigurationImportSelector** and the **AutoConfigurationImportSelector.AutoConfigurationGroup** group to coordinate multiple candidates during the deferred import phase. Once a valid set of candidates is obtained, Boot applies ordering rules such as **@AutoConfiguration(before = ...)**, **@AutoConfiguration(after = ...)**, **beforeName**, **afterName**, and corresponding ordering declarations.

Three questions must be distinguished:

1. **How are candidates discovered?** From **AutoConfiguration.imports** resources on the runtime classpath.
2. **How are candidates coordinated and ordered?** Through the DeferredImportSelector's group, merging/exclusion steps, and Boot's auto-configuration sorter.
3. **Which beans are actually registered and instantiated?** After selection/ordering, **@Conditional** on classes/**@Bean** methods, application beans, scope, dependencies, and initialization steps must still be evaluated.

One class being ordered before another **does not guarantee** the constructor of a bean in that class runs first. **Auto-configuration processing order** primarily affects the order of parsing/registering bean definitions and therefore can affect conditions that depend on already-registered beans.

## 2. From @EnableAutoConfiguration to DeferredImportSelector

**@SpringBootApplication** includes **@EnableAutoConfiguration**. The latter uses **@Import(AutoConfigurationImportSelector.class)** alongside the auto-configuration package registration mechanism. In Spring Boot 3.x:

~~~text
@SpringBootApplication
         |
         v
@EnableAutoConfiguration
         |
         v
@Import(AutoConfigurationImportSelector.class)
         |
         v
AutoConfigurationImportSelector
     implements DeferredImportSelector
         |
         v
getImportGroup() -> AutoConfigurationGroup
         |
         v
Collect / filter / exclude / sort candidates
         |
         v
Return import list for Spring to process
         |
         v
Evaluate conditions and register bean definitions
         |
         v
Instantiate according to scope/lifecycle/dependencies
~~~

This is an explanatory model, not a statement-by-statement internal execution order. Spring Framework processes configurations across multiple passes, and some conditions are evaluated in different phases.

### 2.1. Regular ImportSelector vs. DeferredImportSelector

A regular **ImportSelector** returns the names of classes to import via **selectImports(AnnotationMetadata)**. Spring uses this list when processing the configuration class carrying the corresponding **@Import**.

**DeferredImportSelector** is a form of ImportSelector whose processing is **deferred until regular configuration classes have been parsed in the corresponding phase**. This is especially useful for auto-configuration: explicitly declared application configurations and their bean definitions get the chance to be processed before default configurations proposed by Boot.

“Deferred” **does not mean** Spring has finished instantiating all application bean instances before the selector runs. It refers to **the configuration class import selection and processing phase**, not the completion milestone of constructing every object.

Brief comparison:

| Mechanism | Input | Output | Key Characteristic |
| --- | --- | --- | --- |
| **@Import(SomeConfiguration.class)** | Specified class | Brings that class into configuration processing | Explicit import |
| **ImportSelector** | Annotation metadata and selector logic | List of class names to import | Dynamic selection |
| **DeferredImportSelector** | Metadata and selector logic | Import list processed in the deferred phase | Can yield so application configs are processed first |
| **DeferredImportSelector.Group** | Multiple selectors/metadata in one group | Coordinated import entries returned by the group | Can merge, filter, deduplicate, and sort per strategy |
| **AutoConfigurationImportSelector** | Runtime classpath, properties, exclusions, metadata | Auto-configuration candidates selected by Boot | DeferredImportSelector provided by Boot |
| **AutoConfigurationGroup** | Auto-configuration entries from matching selectors | Imports after merging, exclusions, and sorting | Spring Boot's coordination strategy |

**DeferredImportSelector** does not automatically come with “deduplicate, exclude, sort” algorithms. Those are the responsibility of a specific implementation and/or **Group**. Spring Boot implements the strategy needed for auto-configuration through its own group.

## 3. How Does DeferredImportSelector.Group Coordinate Selections?

In Spring Framework, the group interface of DeferredImportSelector has two crucial operations:

- **process(AnnotationMetadata metadata, DeferredImportSelector selector)**: feeds a selector's output along with related metadata into the group for processing/accumulation.
- **selectImports()**: returns **Entry** items, containing metadata and imported class names, after the group finishes coordinating.

Abbreviated API structure (for understanding the signatures, not standalone source code):

~~~java
interface Group {
    void process(
        AnnotationMetadata metadata,
        DeferredImportSelector selector
    );

    Iterable<Entry> selectImports();
}
~~~

A group can gather results from **selectors assigned to the same group**, combine/adjust ordering, and return a final list. Selectors with different group mechanisms **are not merged into a single global group by default**. Which group is selected depends on the DeferredImportSelector's **getImportGroup()**.

Conceptual example: two configurations both trigger selectors sharing the same Group. Instead of each selector emitting imports independently without knowing what the other decided, the group can inspect related selections, deduplicate, evaluate constraints, and return a unified list. **This is a capability of Group, not a promise that every implementation behaves identically.**

### 3.1. What Components Boot Uses in the Auto-Configuration Group

In Spring Boot 3.x, **AutoConfigurationImportSelector** returns the **AutoConfigurationImportSelector.AutoConfigurationGroup** group. Conceptually, the processing chain consists of:

1. **Reading the list of candidate auto-configurations** from resources on the classpath.
2. **Removing duplicate names** when multiple sources declare the same candidate.
3. **Collecting exclusions** from annotations and properties; removing excluded auto-configurations.
4. **Using filters/metadata** to screen out obviously inapplicable candidates when enough information exists, such as classpath conditions.
5. **Merging the results** collected by the group; ensuring exclusions take effect across the combined list.
6. **Sorting remaining auto-configurations** according to before/after/order information via Boot's internal sorter.
7. **Returning the import list** for Spring to continue parsing configuration classes and evaluating conditions.

Steps may be organized differently across Boot versions; do not treat the list above as one-to-one pseudocode copied from the implementation. The durable takeaway of this lesson is that **the group coordinates candidates before returning the import list**, while **conditions on classes and `@Bean` methods still determine the final bean definitions**.

### 3.2. Why Is Sorting Needed After Merging?

Suppose a library has:

- **EngineAutoConfiguration**: registers a default Engine bean.
- **ReportAutoConfiguration**: registers Report only when **@ConditionalOnBean(Engine.class)** sees an Engine bean already exists.

If ReportAutoConfiguration is processed before the Engine definition appears, the Engine-dependent condition may fail. Therefore the library can publish:

~~~java
@AutoConfiguration(after = EngineAutoConfiguration.class)
class ReportAutoConfiguration {
    // ...
}
~~~

Declaring **after** tells Boot that when both auto-configurations participate, **EngineAutoConfiguration needs to be processed before ReportAutoConfiguration**. Thanks to this, ReportAutoConfiguration has a chance to observe bean definitions registered by EngineAutoConfiguration.

This is a **configuration processing order** constraint, not a requirement that Engine's bean creation method must run immediately before Report's creation method. When Report is instantiated, dependency injection still determines how to create or locate the Engine instance.

### 3.3. Is Order in AutoConfiguration.imports Treated as Execution Order?

**No.** The **META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports** file is a candidate list; line position **is not an ordering contract** between configurations. Boot's sorter uses metadata/annotations along with rules applicable in the corresponding Boot version.

For example, a file could intentionally list Report before Engine:

~~~text
dev.study.autoconfig.ReportAutoConfiguration
dev.study.autoconfig.EngineAutoConfiguration
~~~

If ReportAutoConfiguration declares **@AutoConfiguration(after = EngineAutoConfiguration.class)**, Boot has the information to sort Engine before Report even though the file listed them in reverse. This behavior will be verified in the runnable example below.

Do not edit line order in imports to work around a bean-dependent condition when the author has not published proper ordering relationships. Class names and related annotations are where stable ordering contracts belong.

## 4. Ways to Declare Auto-Configuration Ordering

### 4.1. @AutoConfiguration(before = ...) and after = ...

Spring Boot 3.x provides attributes on **@AutoConfiguration**:

~~~java
@AutoConfiguration(after = EngineAutoConfiguration.class)
public class ReportAutoConfiguration {
}
~~~

And the reverse direction:

~~~java
@AutoConfiguration(before = ReportAutoConfiguration.class)
public class EngineAutoConfiguration {
}
~~~

The two snippets above only illustrate annotations; they are not two standalone runnable files. Place them in the appropriate files/packages containing the corresponding classes. Usually declaring **one clear directional relationship** is enough, avoiding cyclic or conflicting constraints.

**after = X.class** means *if both configurations are considered*, try processing X before the current configuration. It does **not** import X on its own and does **not** force X to match. If X is absent, excluded, or X's conditions fail, configuration Y must still have conditions guarding its own assumptions.

**before = X.class** works in the reverse direction and likewise does not cause X to appear on its own.

### 4.2. beforeName and afterName

When an auto-configuration has an ordering relationship with a class in an **optional dependency**, we do not always want to reference a **Class literal** at compile time:

~~~java
@AutoConfiguration(
    afterName = "dev.optional.autoconfig.OptionalEngineAutoConfiguration"
)
public class OptionalReportAutoConfiguration {
}
~~~

This is an illustrative annotation example. **afterName** and **beforeName** declare relationships via **fully qualified class names**, useful when the current module has no compile-time dependency on the other class. The string name must be exact; a wrong name will not establish the desired constraint.

Do not use afterName as a way to “create a dependency”: it only describes order **if the related candidate actually participates**.

### 4.3. @AutoConfigureBefore, @AutoConfigureAfter, and @AutoConfigureOrder

Besides **@AutoConfiguration** attributes, Spring Boot has documented annotations such as **@AutoConfigureBefore**, **@AutoConfigureAfter**, and **@AutoConfigureOrder** to express ordering. For new Boot 3.x code, **@AutoConfiguration(before/after)** is usually more readable and sufficient.

- **@AutoConfigureBefore(X.class)** and **@AutoConfigureAfter(X.class)** state relative relationships to class X.
- **@AutoConfigureOrder** provides priority ordering information for auto-configurations under the order model. It is not a singleton instantiation directive or a guarantee replacing all before/after relationships.
- Regular **@Order** is used in many other Spring contexts; do not assume placing **@Order** on a `@Bean` changes auto-configuration import order.

Prefer expressing **real dependency relationships** via before/after. Use numeric order only when genuinely needed and its effect is well understood; avoid designs relying on a “lucky” number from another library.

### 4.4. Ordering Is a Relationship Problem, Not a Constructor Queue

A valid chain:

~~~text
DatabaseAutoConfiguration
          |
          | before
          v
RepositoryAutoConfiguration
          |
          | before
          v
ServiceAutoConfiguration
~~~

Read this as **database configuration is processed before repository configuration, then service configuration**, if all three are selected candidates. It does not promise every connection pool is ready before every constructor, does not force dependent classes to exist, and does not replace dependency injection.

Relations like **A after B, B after A** contradict themselves and must be fixed. If there is an ordering cycle among multiple auto-configurations, the sorter cannot produce a valid order satisfying all constraints; do not “fix” it by changing imports line order.

## 5. Three Different Decision Layers: Candidate, Condition, Instance

To analyze a Spring Boot log accurately, divide it into three layers:

| Layer | What Does It Ask? | Example |
| --- | --- | --- |
| **Candidate discovery/group ordering** | Was the auto-config class discovered, not excluded, and placed into which processing order? | Report sorted after Engine |
| **Condition/bean definition registration** | When processing the class or `@Bean`, do conditions pass to register a definition? | `@ConditionalOnBean(Engine.class)` on the report method |
| **Instance lifecycle** | Which bean is actually created, when, and what errors occur during init/injection? | Report needs Engine in its constructor/factory method |

**@ConditionalOnBean** and **@ConditionalOnMissingBean** are especially order-sensitive because they rely on **bean definitions already processed up to the point of evaluation**. These conditions should be used in auto-configurations, where the framework provides post-user-configuration processing and ordering across auto-configurations.

Conversely, **@ConditionalOnClass** focuses on the classpath and **@ConditionalOnProperty** reads the Environment; they do not become true simply because we use before/after.

Do not confuse:

- **Bean definition exists**: the container knows a bean can be created.
- **Bean instance exists**: the container has created/obtained an object per the corresponding scope.
- **Default bean backs off**: the **@ConditionalOnMissingBean** branch does not register a default because a matching bean already exists; the user's bean object does not necessarily have to be instantiated yet.

## 6. Complete Spring Boot Example: Ordering Against the Imports File Sequence

The example uses **JDK 21, Maven 3.9+, Spring Boot 3.3.13**. An **EngineAutoConfiguration** provides a default Engine, and a **ReportAutoConfiguration** creates Report **only when the container already knows an Engine bean**. Report is listed **before** Engine in the imports file, yet declares **@AutoConfiguration(after = EngineAutoConfiguration.class)** so Boot can process them in the right order.

We also demonstrate that a condition can disable the default bean, and a user bean can make the default back off.

### 6.1. Directory Structure

~~~text
deferred-order-demo/
├── pom.xml
└── src/main/
    ├── java/dev/study/
    │   ├── api/
    │   │   ├── Engine.java
    │   │   └── Report.java
    │   ├── autoconfig/
    │   │   ├── EngineAutoConfiguration.java
    │   │   └── ReportAutoConfiguration.java
    │   └── app/
    │       └── DemoApplication.java
    └── resources/
        ├── application.properties
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Place the application package in **dev.study.app**, and auto-configurations in **dev.study.autoconfig**. `@SpringBootApplication`'s default component scan only searches inside `dev.study.app` and subpackages. Thus the two auto-configuration classes in this project enter the application **via AutoConfiguration.imports**, not by accidental `@ComponentScan` discovery.

### 6.2. Dependencies and Build

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
    <groupId>dev.study</groupId>
    <artifactId>deferred-order-demo</artifactId>
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

The base starter provides the required Spring Boot/auto-config/Spring Context components. The project needs no servlet container, database, or network API.

### 6.3. Two Data Types for Observation

**src/main/java/dev/study/api/Engine.java**

~~~java
package dev.study.api;

@FunctionalInterface
public interface Engine {
    String label();
}
~~~

**src/main/java/dev/study/api/Report.java**

~~~java
package dev.study.api;

public record Report(String summary) {
}
~~~

### 6.4. Auto-Configuration Creating Engine First

**src/main/java/dev/study/autoconfig/EngineAutoConfiguration.java**

~~~java
package dev.study.autoconfig;

import dev.study.api.Engine;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(Engine.class)
public class EngineAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(Engine.class)
    @ConditionalOnProperty(
        prefix = "demo.engine",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
    )
    Engine defaultEngine() {
        return () -> "default";
    }
}
~~~

Here:

- **@ConditionalOnClass** requires the Engine class on the classpath. In the sample project it is always present; real libraries may reference an optional API.
- **@ConditionalOnMissingBean(Engine.class)** lets the default Engine yield to a user-declared Engine bean.
- **@ConditionalOnProperty** allows disabling **defaultEngine** when **demo.engine.enabled=false**.
- If the method is selected, Spring registers a bean definition; selection itself does not mean the instance was created at that moment.

### 6.5. Auto-Configuration Depending on the Engine Bean

**src/main/java/dev/study/autoconfig/ReportAutoConfiguration.java**

~~~java
package dev.study.autoconfig;

import dev.study.api.Engine;
import dev.study.api.Report;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(after = EngineAutoConfiguration.class)
@ConditionalOnClass({Engine.class, Report.class})
public class ReportAutoConfiguration {

    @Bean
    @ConditionalOnBean(Engine.class)
    @ConditionalOnMissingBean(Report.class)
    Report report(Engine engine) {
        return new Report("engine=" + engine.label());
    }
}
~~~

**after** governs **auto-configuration processing order**. **@ConditionalOnBean(Engine.class)** is the real condition deciding whether Report is registered. If EngineAutoConfiguration is excluded or does not register a default, Report can still be created **when a user configuration has provided an Engine bean**. Therefore, do not infer that “after” means “absolute dependency on the EngineAutoConfiguration class itself”.

**@ConditionalOnMissingBean(Report.class)** lets the application provide its own Report if desired. In the runs below there is no user-defined Report.

### 6.6. Candidate Registration File Intentionally Listed in Reverse

**src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**

~~~text
dev.study.autoconfig.ReportAutoConfiguration
dev.study.autoconfig.EngineAutoConfiguration
~~~

This is the lesson's deliberate setup: **Report precedes Engine in the resource**, yet **@AutoConfiguration(after = EngineAutoConfiguration.class)** still establishes the right processing order at the configuration level. Do not add **@ComponentScan** to locate classes in the autoconfig package.

### 6.7. Application with Optional User Bean

**src/main/java/dev/study/app/DemoApplication.java**

~~~java
package dev.study.app;

import dev.study.api.Engine;
import dev.study.api.Report;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Profile;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    @Profile("custom")
    Engine customEngine() {
        return () -> "custom";
    }

    @Bean
    ApplicationRunner showSelectedBeans(
            ObjectProvider<Engine> engines,
            ObjectProvider<Report> reports) {
        return args -> {
            Engine engine = engines.getIfAvailable();
            Report report = reports.getIfAvailable();

            System.out.println("engine=" +
                (engine == null ? "<none>" : engine.label()));
            System.out.println("report=" +
                (report == null ? "<none>" : report.summary()));
        };
    }
}
~~~

**@SpringBootApplication** activates auto-configuration via `@EnableAutoConfiguration`. The **custom** profile enables only a user Engine bean; it is processed with application configurations before Boot's auto-configurations. **ObjectProvider** lets the application run even when either Engine or Report bean is absent.

**src/main/resources/application.properties**

~~~properties
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=OFF
~~~

Logging configuration makes the two stdout lines printed by the example easy to see. If you want to view the condition evaluation report, override logging using the options in the debugging section.

### 6.8. Running and Reading Each Output

Requirements: JDK 21, Maven 3.9+, ability to download dependencies. From the project directory:

~~~bash
mvn -q -DskipTests package
~~~

**A. Without passing properties or enabling a profile**

~~~bash
java -jar target/deferred-order-demo-0.0.1-SNAPSHOT.jar
~~~

Two stdout lines printed by the code:

~~~text
engine=default
report=engine=default
~~~

Interpretation: EngineAutoConfiguration is processed early enough for the Engine-creating method to have a definition; ReportAutoConfiguration is sorted after Engine and **@ConditionalOnBean(Engine.class)** matches. The Report bean is created with the corresponding Engine.

**B. Disabling the default Engine via property**

~~~bash
java -jar target/deferred-order-demo-0.0.1-SNAPSHOT.jar --demo.engine.enabled=false
~~~

Stdout:

~~~text
engine=<none>
report=<none>
~~~

Reason: **@ConditionalOnProperty** on the Engine-creating method does not match. ReportAutoConfiguration being sorted after Engine **does not create** an Engine bean by itself; because the container has no Engine bean, Report's **@ConditionalOnBean** also fails.

**C. Enabling the user's Engine bean**

~~~bash
java -jar target/deferred-order-demo-0.0.1-SNAPSHOT.jar --spring.profiles.active=custom
~~~

Stdout:

~~~text
engine=custom
report=engine=custom
~~~

Reason: customEngine is declared by the application configuration, so defaultEngine steps back due to **@ConditionalOnMissingBean(Engine.class)**. ReportAutoConfiguration is still processed and creates Report using the user's Engine bean.

**D. Disabling default via property while enabling custom bean**

~~~bash
java -jar target/deferred-order-demo-0.0.1-SNAPSHOT.jar --spring.profiles.active=custom --demo.engine.enabled=false
~~~

Stdout:

~~~text
engine=custom
report=engine=custom
~~~

The **demo.engine.enabled=false** property only disables the defaultEngine branch in the example. It does not remove the application-defined bean, so Report is still created.

**E. Excluding EngineAutoConfiguration outright**

~~~bash
java -jar target/deferred-order-demo-0.0.1-SNAPSHOT.jar --spring.autoconfigure.exclude=dev.study.autoconfig.EngineAutoConfiguration
~~~

Stdout without the custom profile enabled:

~~~text
engine=<none>
report=<none>
~~~

Here **EngineAutoConfiguration does not participate in auto-configuration**, so defaultEngine is not created. ReportAutoConfiguration can still be a candidate, yet lacks Engine to satisfy its condition. **after** does not force an excluded class back in.

**F. Excluding only ReportAutoConfiguration**

~~~bash
java -jar target/deferred-order-demo-0.0.1-SNAPSHOT.jar --spring.autoconfigure.exclude=dev.study.autoconfig.ReportAutoConfiguration
~~~

Stdout:

~~~text
engine=default
report=<none>
~~~

This is proof that **the `after` rule only sorts order if the configuration participates**; removing Report does not make the default Engine vanish.

### 6.9. Comparing the Scenarios

| Scenario | Which Engine Definition Is Kept? | Can Report Condition Match? | Outcome |
| --- | --- | --- | --- |
| Default | defaultEngine | Yes | default + report |
| demo.engine.enabled=false | None | No | Neither present |
| custom profile | customEngine | Yes | custom + report |
| custom + enabled=false | customEngine | Yes | custom + report |
| exclude EngineAutoConfiguration | None unless custom is present | No | Neither present |
| exclude ReportAutoConfiguration | defaultEngine | Report method of excluded class not evaluated | Default Engine only |

The table describes only the example project. In other systems, additional Engine/Report beans may be registered by other sources. In those cases, inspect the real conditions and do not apply results mechanically.

## 7. Looking Deeply at the Group Algorithm with a Conceptual Example

Suppose there are three deferred selectors with the same Group type:

~~~text
Selector A -> candidates: [CacheAutoConfig, EngineAutoConfig]
Selector B -> candidates: [ReportAutoConfig, EngineAutoConfig]
Selector C -> exclude: [CacheAutoConfig]
~~~

A **Group designed to aggregate** could process as follows:

~~~text
Input set: Cache, Engine, Report, Engine
Deduplicated: Cache, Engine, Report
Excluded: Engine, Report
Constraint: Report after Engine
Final import set: Engine, Report
~~~

This is a **simulated conceptual example of the group mechanism**, not an exact callback-by-callback description of **AutoConfigurationGroup** with those three selectors: Spring Boot has its own rules for obtaining candidates and exclusions from auto-configuration metadata. The example's purpose is to show why a coordination point is needed **after multiple selectors have contributed data but before emitting the import list**.

In practice, Boot uses **AutoConfigurationImportSelector.AutoConfigurationGroup**, coordinating entries, exclusions, and sorting information from auto-configurations. **AutoConfigurationSorter** is the internal implementation component that establishes ordering. Typical library developers **do not need to write a custom Group or call AutoConfigurationSorter**: publish classes via imports and describe relationships using supported annotations.

### 7.1. When to Implement DeferredImportSelector.Group Yourself?

Create your own Group only if designing a **custom `@Enable...` mechanism** where multiple selectors must reach a unified decision—such as resolving module conflicts or sorting imports according to a specialized contract.

Illustrative API skeleton:

~~~java
// Illustrates API signatures, not a standalone runnable project.
final class FeatureImportSelector
        implements DeferredImportSelector {

    @Override
    public String[] selectImports(AnnotationMetadata metadata) {
        return new String[] {"dev.study.features.FeatureConfiguration"};
    }

    @Override
    public Class<? extends Group> getImportGroup() {
        return FeatureGroup.class;
    }
}
~~~

In this snippet, **FeatureGroup** is simply a class name that would need to be implemented per the Group interface; the snippet only illustrates where a selector hooks into a group, **not complete code**. In real code, Group must handle **process(...)** and return **Iterable<Entry>** from **selectImports()**. Avoid building a custom mechanism merely to replicate auto-configuration functionality that Spring Boot already provides.

## 8. Analyzing the Interaction Between Sorting and @ConditionalOnBean

### 8.1. Why Are Bean Existence Conditions Order-Sensitive?

When Spring evaluates **@ConditionalOnBean(Engine.class)** on an auto-configuration, it works against bean definitions **already processed up to that point** within the condition's search scope. If an auto-configuration providing Engine is processed too late, the dependent branch may fail to see Engine even though the engine definition appears later.

This is why **@AutoConfiguration(after = EngineAutoConfiguration.class)** has practical value in the example. Ordering rules do not “wake up” every bean; they help conditions get evaluated at a point with the right registration information.

**Cases to distinguish:**

- **Engine already declared by application:** the condition can match even if EngineAutoConfiguration is excluded.
- **EngineAutoConfiguration is a candidate yet no Engine bean due to false property:** the condition fails.
- **Engine bean registered with lazy scope:** the condition can still match because the definition exists, even though the instance has not been created yet.
- **Engine must be instantiated before the Report instance initializes:** dependency injection via the **report(Engine engine)** method parameter resolves/creates the needed instance per the container; this is a lifecycle relationship **distinct** from definition sorting.
- **Engine bean belongs to a parent context or is registered via a special mechanism:** inspect the condition's search strategy and bean detection rules; do not assume every bean in every context is automatically visible.

### 8.2. Why Is Import Order Not Enough to Guarantee Every Condition?

An auto-configuration branch should only make assumptions backed by **verifiable conditions**. If Report depends on Engine, use a condition like **@ConditionalOnBean(Engine.class)** and inject Engine. If Report requires an optional class, add an appropriate **@ConditionalOnClass** to guard processing. If a feature needs a property enabled, add **@ConditionalOnProperty** per contract.

**@AutoConfiguration(after = ...)** only solves *when evaluating bean-dependent conditions, which configuration should be processed first*; it does not prove the source bean is guaranteed to exist.

### 8.3. Avoiding Ordering Cycles and Circular Dependencies

Do not design both **EngineAutoConfiguration(after = ReportAutoConfiguration.class)** and **ReportAutoConfiguration(after = EngineAutoConfiguration.class)**. Two opposing constraints leave no valid order. Design a clear dependency direction.

Also do not confuse **configuration sorting cycles** with **circular dependencies between bean instances**. The first is a before/after relationship during registration; the second involves constructor/injection cycles between beans. They can occur independently and must be resolved at the right layer.

## 9. Things Ordering Does Not Promise

| Misconception | Correction |
| --- | --- |
| “The first line in AutoConfiguration.imports always runs first.” | That list only publishes candidates; Boot sorts using metadata and before/after relationships. |
| “`after = X` will automatically import X.” | Ordering constraints only matter when X actually participates; they do not force missing/excluded candidates back in. |
| “`after = X` makes bean instance X get created first.” | It controls configuration processing/definition registration order, not replacing dependencies/lifecycle. |
| “`@ConditionalOnBean` finds every bean that will appear in the future.” | The condition relies on beans already processed at evaluation time; that is why order matters. |
| “Deferred means application singletons are already instantiated.” | Deferred here means deferred import during configuration metadata processing. |
| “Group always deduplicates and sorts automatically.” | The Group interface only provides hooks; algorithms depend on the implementation. |
| “`@AutoConfiguration` joins the group via component scan.” | Boot 3.x candidates are published via AutoConfiguration.imports; do not component-scan auto-configs like ordinary components. |
| “`@AutoConfigureOrder` equals `@Bean` init order.” | Auto-configuration order is not constructor order. |
| “A positive match means bean creation succeeded.” | Condition match differs from BeanDefinition and instance creation succeeding. |
| “Once ordered properly, you can omit `@ConditionalOnBean`.” | Sorting only orders; conditions are still needed to verify dependent bean presence. |
| “Just reordering lines in imports fixes a condition.” | Declare before/after relationships on auto-configurations; avoid relying on file order. |

## 10. Debugging and Verifying Order with Built-in Tools

### 10.1. Viewing the Condition Evaluation Report

With the sample project having **logging.level.root=OFF**, use:

~~~bash
java -jar target/deferred-order-demo-0.0.1-SNAPSHOT.jar --debug --logging.level.root=INFO
~~~

Look at the **CONDITIONS EVALUATION REPORT** for **EngineAutoConfiguration** and **ReportAutoConfiguration**. The report explains why conditions matched/did not match and lists corresponding exclusions. When default Engine is off, Report can be a negative match due to missing Engine. When the custom profile is enabled, defaultEngine's condition fails because a user bean already exists, while report can match.

**Limitation:** the condition report is not a guaranteed full listing of the exact processing order of every configuration class; to prove a specific internal ordering in a specific version, use diagnostic/test code at the exact processing phase or read that version's implementation. The report only helps confirm **condition outcomes**.

### 10.2. When the Report Bean Is Missing

Check in this order:

1. **Classpath/resource:** does the JAR contain the **AutoConfiguration.imports** resource and the exact class name? `mvn dependency:tree` helps inspect dependencies if external libraries are involved.
2. **Exclusions:** are **spring.autoconfigure.exclude**, annotation excludes, or other configuration-disabling settings used?
3. **Ordering metadata:** does ReportAutoConfiguration declare **after = EngineAutoConfiguration.class**? If using **afterName**, is the fully qualified name exact?
4. **Bean definition:** was Engine registered at the time Report's condition was evaluated?
5. **Property/condition:** what is **demo.engine.enabled** after considering all property sources and profiles? Are Engine and Report classes on the classpath?
6. **Instantiation:** was there a **BeanCreationException**, factory method error, or dependency resolution failure?
7. **Bean name/type:** did the application provide another Engine/Report bean causing the default to back off?

Use the right kind of evidence: **condition report** for configuration selection, **BeanFactory metadata** for definition registration, and stack traces/lifecycle logs for instance creation.

### 10.3. Role of Optimization Metadata

Spring Boot can use **spring-autoconfigure-metadata.properties** generated during library build to optimize candidate filtering and read related information. For auto-configurations you develop, you can use **spring-boot-autoconfigure-processor** where appropriate per the version's documentation.

This optimization resource **does not replace** **AutoConfiguration.imports** in Spring Boot 3.x. When optimization metadata is absent, do not infer that all before/after directives are disabled; configuration annotations remain the source of truth processed by the framework.

## 11. Practice Questions with Answers

**Question 1.** ReportAutoConfiguration is written on the first line of imports, EngineAutoConfiguration on the second line. Why does Report still work in the default scenario?

**Answer:** Report declares **@AutoConfiguration(after = EngineAutoConfiguration.class)**, letting Boot process Engine before Report per the published relationship. Report's **@ConditionalOnBean(Engine.class)** condition can thereby see the registered Engine bean.

**Question 2.** EngineAutoConfiguration is excluded, yet the custom profile is enabled. Can Report appear?

**Answer:** Yes. Report requires an **Engine bean**, not that the instance be provided specifically by EngineAutoConfiguration. The custom bean satisfies the condition. The `after` constraint does not re-import an excluded class.

**Question 3.** Why shouldn't you use only **@AutoConfiguration(after = EngineAutoConfiguration.class)** and omit **@ConditionalOnBean(Engine.class)**?

**Answer:** `after` only guarantees processing order when both candidates are present; it does not guarantee EngineAutoConfiguration matches, does not guarantee the defaultEngine method is selected, and does not guarantee an Engine bean exists.

**Question 4.** Why does a Group differ from a single DeferredImportSelector?

**Answer:** A selector chooses imports from its metadata; **Group** provides hooks to gather and coordinate results from selectors in the same group and return the final import list. How the group deduplicates/sorts depends on the Group implementation.

**Question 5.** An Engine singleton has a definition marked lazy, with no instance yet. Can Report match **@ConditionalOnBean(Engine.class)**?

**Answer:** It can, because the condition inspects registered bean information without needing an Engine instance already created. However, when Report actually initializes and injects Engine, it may trigger Engine creation at that time.

**Question 6.** Is swapping two lines in AutoConfiguration.imports without changing before/after annotations a standard way to fix ordering?

**Answer:** No. The imports file is a candidate list, not an ordering API. Declare relationships on the auto-configuration annotations and verify the result.

**Question 7.** Can you create an entirely custom DeferredImportSelector.Group outside Spring Boot?

**Answer:** Yes. It is a Spring Framework extension point. However, when writing a Spring Boot library that simply provides defaults based on classpath/conditions, the standard approach is **@AutoConfiguration** plus **AutoConfiguration.imports** and before/after ordering; there is no need to reimplement the group mechanism.

**Question 8.** Why can't the object instantiation order of Report and Engine be inferred directly from the `after` annotation?

**Answer:** The `after` relationship concerns configuration/definition processing. When the Report instance is created, the **report(Engine engine)** method expresses a runtime dependency, causing the container to resolve Engine when needed. Lazy beans, proxies, or different scopes also have their own lifecycle behaviors.

## 12. Reminders When Building Libraries

To coordinate multiple auto-configurations predictably:

1. Publish **each auto-configuration class** in the proper Spring Boot 3.x format inside **META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**.
2. Declare **@AutoConfiguration(after/before/afterName/beforeName)** according to real dependency relationships between configurations; do not rely on imports line order.
3. Place appropriate conditions—especially **@ConditionalOnClass**, **@ConditionalOnBean**, **@ConditionalOnMissingBean**, and **@ConditionalOnProperty**—so each branch guards its own assumptions.
4. Yield default beans to user beans when customization is desired; avoid creating duplicate beans merely because an auto-configuration was imported.
5. Distinguish **candidate discovery → Group coordination → ordering → condition/registration → instance lifecycle** when debugging.
6. Use the **Condition Evaluation Report** to read selection/skip reasons; if a bean creation error occurs, inspect `BeanCreationException` and the dependency chain separately.

**DeferredImportSelector.Group** is the extension point enabling multiple deferred import selections to be processed collectively. **AutoConfigurationGroup and Spring Boot's sorting mechanism** use this point to produce a valid, ordered list of auto-configurations capable of respecting user configuration. **before/after** helps bean-definition-based conditions get evaluated in intentional order; by itself it does not create beans, force conditions to match, or replace dependency injection.

### References

- Spring Framework, **DeferredImportSelector** and **DeferredImportSelector.Group**: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/DeferredImportSelector.html
- Spring Boot, **AutoConfigurationImportSelector**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurationImportSelector.html
- Spring Boot, **@AutoConfiguration**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html
- Spring Boot, *Creating Your Own Auto-configuration*: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- Spring Boot, *Auto-configuration*: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
