# Limitations of excluding regular configuration classes or internal nested classes

## 1. Problem statement: excluding only what Spring Boot auto-imports

In Spring Boot, an application can have multiple sources of configuration registration:

- **Auto-configurations** discovered by Spring Boot via its candidate list and automatically imported.
- **Regular `@Configuration` classes** declared by the project via `@Import`, component scanning, or explicit registration.
- **Nested `@Configuration` classes** residing inside another configuration class, processed by Spring while parsing the outer configuration or imported independently.

When using `@SpringBootApplication(exclude = ...)`, beginners often assume they can pass **any** `@Configuration` class into the exclusion list. This is an important misconception: this feature primarily excludes **auto-configuration candidates** selected by Spring Boot. A regular configuration class or an internal nested class of an auto-configuration is not by default an independently excludable candidate.

Lesson goals:

1. Distinguish the exclusion scope of `@SpringBootApplication(exclude/excludeName)`, `@EnableAutoConfiguration`, and `spring.autoconfigure.exclude` from regular import/scan mechanisms.
2. Explain why excluding a regular `@Configuration` or an internal nested class can cause errors or fail to achieve the goal.
3. Choose the stable **outer auto-configuration class** when disabling an entire feature, or select suitable conditions/import methods when disabling only one part.
4. Demonstrate with Java 17+ and Spring Boot 3.3 examples, along with a scenario table, troubleshooting steps, and key limitations.

## 2. Three distinct configuration loading paths

Look at the high-level model:

```text
                    ApplicationContext
                           |
             +-------------+--------------+
             |             |              |
             v             v              v
   AutoConfiguration     @Import(...)   @ComponentScan
      .imports              |              |
             |             |              |
             v             v              v
   Auto-config candidate  Regular        @Configuration/
             |           @Configuration    @Component
             |             |              |
       Boot's exclude      |              |
       filter applies      |              |
             |             |              |
             v             v              v
        Bean definitions after valid conditions/registrations
```

All three paths can contribute bean definitions to the same context, yet **they do not share the same exclusion filter**.

### 2.1. Auto-configuration auto-discovered by Spring Boot

In Spring Boot 3.3, libraries and starters publish candidate auto-configurations in the resource:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

For example, this file might contain:

```text
com.example.report.ReportAutoConfiguration
com.example.cache.CacheAutoConfiguration
```

During `@EnableAutoConfiguration` execution (bundled inside `@SpringBootApplication`), Boot collects the candidate list, applies conditions/filters, processes excluded classes, and imports what qualifies. **The target of `exclude` is the candidates in the auto-configuration list.**

Annotating a class with `@AutoConfiguration` is part of authoring an auto-config, but for Spring Boot to discover it automatically in a real application, that class must be listed in `AutoConfiguration.imports` of a library on the classpath. Avoid letting auto-configurations be component-scanned or manually imported at the same time.

### 2.2. Regular @Configuration

Example:

```java
@Configuration(proxyBeanMethods = false)
public class BusinessConfiguration {
    @Bean
    BusinessService businessService() {
        return new BusinessService();
    }
}
```

This is **illustrative code**, assuming `BusinessService` is defined and necessary imports are present. If `BusinessConfiguration` is brought into the context via `@Import(BusinessConfiguration.class)` or discovered by component scanning, it is **user configuration**. It does not become an auto-configuration candidate just because it has `@Configuration` and `@Bean`.

Therefore, the following configuration is usually **wrong**:

```java
@SpringBootApplication(exclude = BusinessConfiguration.class)
public class Application {
}
```

If this class is present on the classpath yet **not** in the list of auto-configuration candidates, Spring Boot 3.3 normally halts at startup with an `IllegalStateException`, stating that the class could not be excluded because it is not an auto-configuration class. `exclude` here is **not** a general-purpose way to delete any `@Configuration`.

### 2.3. Internal nested configurations

An auto-configuration may organize its logic into nested static classes:

```java
@AutoConfiguration
public class ReportAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    static class WriterConfiguration {
        @Bean
        ReportWriter reportWriter() {
            return new ReportWriter();
        }
    }
}
```

This snippet is also illustrative, assuming `ReportWriter` exists. `WriterConfiguration` is an **implementation detail** inside `ReportAutoConfiguration`. If only `ReportAutoConfiguration` is listed in `AutoConfiguration.imports`, `WriterConfiguration` does not become **an independent entry** in the candidate list.

Hence, trying to exclude `ReportAutoConfiguration.WriterConfiguration.class` with `@SpringBootApplication(exclude = ...)` is not a supported approach for this structure; if the nested class is present without being an independent auto-configuration candidate, Boot may report a "not auto-configuration classes" error.

**The public API scope exposed by Spring Boot for exclusion is the auto-configuration class name**, not bean method names or internal nested configurations. Another library version may rename, move, or remove internal classes, breaking configurations tied to internals.

## 3. Valid exclusion forms and each form's limits

### 3.1. Using a class literal when a direct dependency exists

```java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;

@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)
public class Application {
}
```

This is a valid example for excluding the **auto-configuration candidate** `DataSourceAutoConfiguration`. It does not automatically remove any datasource bean the application created by other means.

### 3.2. Using the fully qualified name when avoiding a class reference

```java
@SpringBootApplication(
    excludeName = "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration")
public class Application {
}
```

Or in `application.properties`:

```properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
```

And with `@EnableAutoConfiguration` directly:

```java
@EnableAutoConfiguration(exclude = DataSourceAutoConfiguration.class)
public class Application {
}
```

In all three forms above, Spring Boot is still operating on the **selected auto-configuration set**. `excludeName` uses a fully qualified string name, handy when the class might be absent from the compile classpath; it **does not expand scope** to regular `@Configuration` or internal nested classes.

### 3.3. Do not equate "class with annotation" with "Boot-imported candidate"

| Subject | Primary loading mechanism | Suitable for Spring Boot auto-configuration exclude? |
|---|---|---|
| Boot-published `DataSourceAutoConfiguration` | `AutoConfiguration.imports` | **Yes** |
| Custom auto-config `ReportAutoConfiguration` listed in imports | `AutoConfiguration.imports` | **Yes** |
| Regular `BusinessConfiguration`, directly `@Import`ed | `@Import` | **No** |
| Regular `FeatureConfiguration` found by component scan | `@ComponentScan` | **No** |
| `ReportAutoConfiguration.WriterConfiguration`, nested class only parsed via outer class | Internal configuration member of parent auto-config | **No** as an independent auto-config candidate |
| Nested class **intentionally** published by author as a separate auto-config candidate in imports | `AutoConfiguration.imports` with `$` JVM name | **Mechanically possible**, though rare; rely only on author's stable published API |
| User-declared bean via `@Bean` | `@Configuration` or manual registration | Auto-config exclude does not directly remove that bean |

**Exception worth stating clearly:** Spring Boot permits the uncommon case of a **nested auto-configuration registered as an independent candidate**, using its JVM class name with `$` in the imports file. In that case, it can be treated as a real candidate. This differs from unpublished internal nested classes. You cannot generalize that "no nested class can ever be excluded"; the necessary condition is that it belongs to the candidate list being filtered.

## 4. Why excluding internal nested classes is risky

Spring Boot might structure an auto-configuration's logic as follows:

```text
ReportAutoConfiguration           <-- published candidate
├── FileWriterConfiguration      <-- internal nested @Configuration
│   ├── @Bean fileWriter()
│   └── @Bean fileFormatter()
└── NetworkWriterConfiguration   <-- internal nested @Configuration
    └── @Bean networkWriter()
```

A user sees an error in the `fileWriter` bean and tries to write:

```java
@SpringBootApplication(
    exclude = ReportAutoConfiguration.FileWriterConfiguration.class)
class Application {
}
```

This is a **counter-example**, assuming the nested type is even accessible at compile time. The limitations include:

1. If `FileWriterConfiguration` is not a separate entry in imports, this exclusion is invalid for Boot's filter.
2. Many nested classes in libraries are package-private or private, so they **cannot even be referenced via `.class`** from external code.
3. Even if accessible, nested class names and structures **are not guaranteed public API**, so library updates can break configurations relying on internal details.
4. If the nested class is imported or discovered through **another path**, excluding the outer auto-config does not guarantee removing that separate registration. You must locate and handle the actual loading path.

To disable **the entire auto-configuration**, use the outer class name published by the library:

```java
@SpringBootApplication(exclude = ReportAutoConfiguration.class)
class Application {
}
```

To disable only a **smaller branch** inside it, look for an official configuration property of the library, an appropriate `@ConditionalOnProperty`/`@ConditionalOnClass`, or supply a replacement bean if the auto-config uses `@ConditionalOnMissingBean`. Excluding the entire outer class can remove other related beans; weigh the desired scope before choosing.

## 5. Runnable example: excluding outer auto-config while regular @Configuration remains

This example uses **Java 17+** and **Spring Boot 3.3.x**. We create:

- An auto-configuration published via `AutoConfiguration.imports`, having two beans: one on the outer class and one in an internal nested configuration.
- A regular `@Configuration` added via `@Import`, also having an outer bean and a nested configuration bean.
- An application excluding the **outer auto-configuration**, then printing the presence of all four beans by name.

### 5.1. Project structure

```text
exclusion-demo/
├── pom.xml
└── src/main/
    ├── java/
    │   └── demo/
    │       ├── app/
    │       │   └── ExclusionDemoApplication.java
    │       ├── regular/
    │       │   └── RegularConfiguration.java
    │       └── autoconfigure/
    │           └── OptionalFeatureAutoConfiguration.java
    └── resources/
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

### 5.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>exclusion-demo</artifactId>
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
```

### 5.3. RegularConfiguration.java

```java
package demo.regular;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class RegularConfiguration {

    @Bean("regularMarker")
    String regularMarker() {
        return "from-regular-configuration";
    }

    @Configuration(proxyBeanMethods = false)
    public static class InternalConfiguration {

        @Bean("regularNestedMarker")
        String regularNestedMarker() {
            return "from-regular-nested-configuration";
        }
    }
}
```

`RegularConfiguration` is not declared as an auto-configuration candidate. Spring Framework automatically processes `static` nested `@Configuration` classes as part of parsing the parent configuration; thus, when the parent is imported, `regularNestedMarker` is created alongside `regularMarker`. This is a way of grouping bean definitions in a **regular configuration**, not a new auto-config.

### 5.4. OptionalFeatureAutoConfiguration.java

```java
package demo.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class OptionalFeatureAutoConfiguration {

    @Bean("autoMarker")
    String autoMarker() {
        return "from-auto-configuration";
    }

    @Configuration(proxyBeanMethods = false)
    public static class InternalConfiguration {

        @Bean("autoNestedMarker")
        String autoNestedMarker() {
            return "from-auto-nested-configuration";
        }
    }
}
```

The outer class `OptionalFeatureAutoConfiguration` is an auto-config. `InternalConfiguration` is a nested `@Configuration` class used to group internal beans. In this lesson, only the outer class is published as a candidate.

### 5.5. Publishing the candidate

File `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`:

```text
demo.autoconfigure.OptionalFeatureAutoConfiguration
```

Do not add `InternalConfiguration` to the imports file. This is the key condition separating **published auto-config classes** from **internal implementation nested classes**.

### 5.6. ExclusionDemoApplication.java

```java
package demo.app;

import demo.autoconfigure.OptionalFeatureAutoConfiguration;
import demo.regular.RegularConfiguration;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Import;

@SpringBootApplication(exclude = OptionalFeatureAutoConfiguration.class)
@Import(RegularConfiguration.class)
public class ExclusionDemoApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(ExclusionDemoApplication.class, args)) {

            System.out.println("regularMarker="
                    + context.containsBean("regularMarker"));
            System.out.println("regularNestedMarker="
                    + context.containsBean("regularNestedMarker"));
            System.out.println("autoMarker="
                    + context.containsBean("autoMarker"));
            System.out.println("autoNestedMarker="
                    + context.containsBean("autoNestedMarker"));
        }
    }
}
```

Note three intentional design details:

1. The application resides in package `demo.app`. `@SpringBootApplication`'s default component scan only scans that package and its subpackages; classes in `demo.regular` or `demo.autoconfigure` **do not enter the context via unintended scanning**.
2. `RegularConfiguration` is added via `@Import`, a loading path independent of auto-configuration exclusion.
3. `OptionalFeatureAutoConfiguration` is published in imports and excluded using its exact **candidate** class. When the outer class is not imported via the auto-config path, nested configurations belonging to parsing that outer class are also not registered through this path.

### 5.7. Running and checking the output

In the `exclusion-demo` directory, with JDK 17+ and Maven installed, run:

```bash
mvn -q spring-boot:run
```

Four lines written by `System.out.println` (Spring Boot may also output banners/other logs):

```text
regularMarker=true
regularNestedMarker=true
autoMarker=false
autoNestedMarker=false
```

Explanation:

| Bean | Source | Why present/absent? |
|---|---|---|
| `regularMarker` | `RegularConfiguration` | Configuration was `@Import`ed, so it is still registered |
| `regularNestedMarker` | `RegularConfiguration.InternalConfiguration` | Nested `@Configuration` processed with the regular configuration |
| `autoMarker` | `OptionalFeatureAutoConfiguration` | Auto-config class excluded from candidate list |
| `autoNestedMarker` | `OptionalFeatureAutoConfiguration.InternalConfiguration` | Nested configuration not parsed because parent import path was excluded |

For comparison, **if you remove the `exclude` parameter** while keeping the other files unchanged and with no condition filtering out the auto-config class, all four beans are expected to be present. This empirically verifies that the absence of the two auto beans comes from the exclusion.

Do not use bean names as a universal metric when real projects have multiple classes creating beans of the same type. The example intentionally uses distinct names to clearly observe loading paths.

## 6. Two common mistakes: regular and nested

### 6.1. Wrong: excluding an `@Import`ed @Configuration class

Change the annotation on the application to:

```java
@SpringBootApplication(exclude = RegularConfiguration.class)
@Import(RegularConfiguration.class)
public class ExclusionDemoApplication {
    // ...
}
```

This is a **counter-example**, not code meant to run successfully. `RegularConfiguration` is a regular `@Configuration` class, **not** in the auto-configuration candidates list. Because the class is on the classpath as in the example, Spring Boot 3.3 validates exclusions and detects that the target is not a candidate: startup fails with a message such as:

```text
The following classes could not be excluded because they are not auto-configuration classes:
    - demo.regular.RegularConfiguration
```

This is the **typical diagnostic message portion**, not the entire stack trace. Do not try fixing it by switching to `excludeName = "demo.regular.RegularConfiguration"` or `spring.autoconfigure.exclude=demo.regular.RegularConfiguration`: those options still go through the **auto-configuration** exclusion mechanism.

How to fix: if you do not want to load `RegularConfiguration`, remove `@Import(RegularConfiguration.class)`, use `@Profile`/`@ConditionalOnProperty` on configurations you own, or adjust component scanning if that was the actual loading source.

### 6.2. Wrong: excluding an internal nested class of an auto-config

Example:

```java
@SpringBootApplication(
    exclude = OptionalFeatureAutoConfiguration.InternalConfiguration.class)
public class ExclusionDemoApplication {
    // ...
}
```

This is also a **counter-example**. Even though the nested class is `public static` so the code compiles, the `AutoConfiguration.imports` file in the example only publishes the **outer** class. The nested class is not an independent candidate, so excluding the inner class cannot disable an internal part and triggers an invalid exclusion check in Spring Boot 3.3.

How to fix when you want to disable **the entire feature**:

```java
@SpringBootApplication(
    exclude = OptionalFeatureAutoConfiguration.class)
public class ExclusionDemoApplication {
    // ...
}
```

If you only want to disable **a bean inside the nested class**, there is no bean-method-level `exclude` in `@SpringBootApplication`. Use an official library option, a replacement bean (when auto-config supports it), or modify the auto-configuration you own to add a condition for that branch.

## 7. Diagnostic table by input scenario

| Requirement / situation | Action | Main result |
|---|---|---|
| Do not need entire auto-config X | `exclude = XAutoConfiguration.class` | Boot does not import candidate X via auto-config path |
| No compile-time dependency on X | `excludeName = "pkg.XAutoConfiguration"` | Excludes candidate by name, not for regular classes |
| Exclude an `@Import`ed `@Configuration` | Use `exclude = RegularConfiguration.class` | **Wrong mechanism**; if class is present yet not a candidate, usually startup error |
| Exclude a scanned `@Configuration` | Use `spring.autoconfigure.exclude=...` | **Wrong mechanism**; must fix scan scope or scan filters |
| Exclude internal nested class not in imports | `exclude = OuterAutoConfiguration.InnerConfiguration.class` | **Wrong mechanism**; not a separate candidate |
| Exclude outer auto-config containing internal nested class | `exclude = OuterAutoConfiguration.class` | Nested class packaged with outer is normally not registered via that path |
| Disable one internal bean while keeping the rest | Find official property, branch condition, or contract bean override | Can selectively disable if library exposes an extension point |
| Class X directly imported while also listed in imports | Only exclude X from auto-config candidates | Separate `@Import(X.class)` path can still register X |
| Bean of type A still appears despite excluding auto-config A | Search for other `@Bean`/`@Component`/imports providing the bean | Auto-config exclude does not delete beans from other sources |
| Nested class **truly** published as a separate candidate | Exclude exact candidate name (typically `$` for nested) | Mechanism can apply; still rely only on library's official API |

Remember: you cannot look solely at **Java structure** to conclude whether a class is in the auto-configuration list. Determine **by which mechanism** that class is published or loaded.

## 8. Proper ways to drop a regular @Configuration

### 8.1. If directly `@Import`ed

```java
@Configuration(proxyBeanMethods = false)
@Import({SecurityConfiguration.class, ReportingConfiguration.class})
public class ApplicationConfiguration {
}
```

This is an illustrative example with hypothetical classes. If `ReportingConfiguration` is no longer wanted, remove it from the `@Import` list or wrap the import/configuration in a condition within the design you own. `@SpringBootApplication(exclude = ReportingConfiguration.class)` does not solve this requirement.

If the import comes from **a library**, look for the library's official configuration options first; do not disable configuration by relying on unguaranteed internal class names.

### 8.2. If loaded via component scanning

Set an appropriately narrow scan range and, if needed, use scan filters:

```java
@ComponentScan(
    basePackages = "demo.business",
    excludeFilters = @ComponentScan.Filter(
        type = FilterType.ASSIGNABLE_TYPE,
        classes = LegacyFeatureConfiguration.class
    )
)
```

The snippet above requires the corresponding Spring imports and existing application classes; this is a **scan filter illustration**, not a standalone program. This filter only affects classes **found through that specific component scan**. If `LegacyFeatureConfiguration` is also `@Import`ed through another path, the scan filter **does not block** that import path. Conversely, avoid overly broad scanning paired with dozens of exclude filters to compensate for unclear package structure.

### 8.3. If you own the `@Configuration` class

Toggle explicitly with conditions:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
    prefix = "demo.reporting",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false
)
public class ReportingConfiguration {

    @Bean
    ReportWriter reportWriter() {
        return new ReportWriter();
    }
}
```

This is an **illustrative snippet**, requiring imports for the annotations and `ReportWriter`. When the property is not enabled, the class is not registered under this condition; no abuse of auto-config exclude is needed. You can place `@ConditionalOnProperty` on a **specific nested class** if only one sub-branch should be conditional while keeping the outer configuration.

If using `@Profile("reporting")`, the condition depends on active profiles, differing from `spring.autoconfigure.exclude`. Choose the rule matching deployment needs; do not treat profiles and feature flags as identical.

### 8.4. If replacing a bean provided by auto-config

Many auto-configurations use `@ConditionalOnMissingBean`, meaning they **yield** when the application provides a suitable bean. This is controlled **behavior replacement** without excluding the entire outer configuration. However, this only works when the library actually provides the matching back-off condition, and requires checking type, name, and qualifiers. `@Primary` only adjusts bean selection for injection; it **does not remove** the original bean from the context.

## 9. Independent loading paths: two advanced traps

### 9.1. Auto-config was excluded, yet its beans still appear

Suppose you have:

```java
@SpringBootApplication(exclude = ReportAutoConfiguration.class)
@Import(ReportAutoConfiguration.class)
class Application {
}
```

This is a **design counter-example**: the same class can be excluded by Spring Boot from the **auto-configuration path**, yet registered via direct `@Import`. Do not think of `exclude` as a total ban forbidding the class from existing anywhere in the application. The right approach is ensuring auto-configs are never simultaneously imported or scanned outside the Boot-designated mechanism.

This is also why Spring Boot recommends isolating auto-configurations in a dedicated package and **preventing component scanning from discovering them**.

### 9.2. Nested configuration registered independently

A nested class can be `@Import(Outer.Inner.class)`ed or discovered by component scanning **independently** of the outer class. In that case, even if the outer class is excluded from the auto-config path, the nested class can still be parsed via its own loading path.

There is another easily missed Spring Framework detail: if a condition sits on the **outer class**, it does not necessarily apply to a nested class **when the nested class is discovered independently**. For configurations you own, put required conditions directly on the nested class or use an appropriate composed annotation if the nested class might be imported or scanned separately.

Practical takeaway: **excluding the outer class stops nested classes from being pulled in as part of that outer class via the auto-config path**, but it does not promise to block every independent registration path designed by the application.

## 10. Troubleshooting workflow when exclusion fails to achieve the goal

1. **Note the exact class to exclude.** Is it an outer auto-config, a regular `@Configuration`, or an internal nested class? Do not guess from naming patterns.
2. **Identify the class's loading path.** Inspect `AutoConfiguration.imports` in relevant JARs for auto-configs; for regular configurations, trace `@Import`, `@ComponentScan`, direct declarations, or registrars.
3. **Match the exclusion mechanism.** `@SpringBootApplication(exclude)`, `@EnableAutoConfiguration(exclude)`, and `spring.autoconfigure.exclude` only handle auto-config candidates through that mechanism.
4. **If "not auto-configuration classes" appears**, the requested class is on the classpath but not in the candidate list reviewed by the selector. Switch to the proper loading mechanism; do not just swap `exclude` for `excludeName`.
5. **If the bean still exists**, trace the actual source bean definition. The bean may come from user config, an independent import, or another auto-config.
6. **Check the condition report.** In a Spring Boot app, pass `--debug` to view the **Condition Evaluation Report**. With Spring Boot Actuator configured/exposed, `/actuator/conditions` shows which auto-configurations matched or did not match. Do not treat the presence or absence of a single bean as complete proof.
7. **Test each option with a small context** using `ApplicationContextRunner` or integration tests to confirm both kept configurations and disabled configurations. Test cases with auto-config active, excluded, property flag off, and regular config present.

### Checklist before adding an exclusion

- [ ] Target class is a **published auto-configuration candidate**, not just any `@Configuration`.
- [ ] If it is a nested class, is there proof it is an **independent candidate**, or is it merely an implementation detail?
- [ ] Will the exclusion strip other beans from the outer auto-config that the application still needs?
- [ ] Could the targeted bean be supplied by another class?
- [ ] Is there an official property or `@ConditionalOnMissingBean` allowing selective disabling/replacement?
- [ ] Have you verified the app still starts and required beans remain present?

## 11. Self-check questions

**Question 1:** `RegularConfiguration` is only loaded via `@Import(RegularConfiguration.class)`. Can `@SpringBootApplication(exclude = RegularConfiguration.class)` be used to exclude it?

**Answer:** No. It is not an auto-config candidate selected by Boot. When the class is present yet not a candidate, this exclude configuration normally causes a startup failure. Fix `@Import` or the conditions on that configuration itself.

**Question 2:** `OuterAutoConfiguration` is published in `AutoConfiguration.imports` and has a nested `static class InnerConfiguration`, while `InnerConfiguration` is not published separately. To disable the entire feature, which class should be excluded?

**Answer:** Exclude `OuterAutoConfiguration`. Do not try relying on the internal class name `InnerConfiguration` as a stable API.

**Question 3:** If you only want to disable `InnerConfiguration` while keeping the outer class's other beans, what should you use?

**Answer:** Prefer an official property/condition or extension mechanism provided by the author. If you own the auto-config, you can add `@ConditionalOnProperty` on the inner branch. There is no `@SpringBootApplication(excludeBeanMethod = ...)` for this requirement.

**Question 4:** You excluded `XAutoConfiguration`, yet a bean of type `XService` still exists. Does that prove `exclude` failed?

**Answer:** No. The bean may be created by user config, another auto-config, component scan, or an independent import. Locate the source bean definition.

**Question 5:** A nested class uses its JVM name `com.example.Outer$NestedAutoConfiguration` in `AutoConfiguration.imports` as a **separate candidate**. Can it be excluded by that class name?

**Answer:** Mechanically, if it is genuinely an independent candidate in imports, it can participate in the exclude filter. However, this is rare; only rely on names published and committed by the author as public API.

## 12. Takeaways

**Excluding an auto-configuration filters the auto-config candidate list; it does not arbitrarily delete any `@Configuration` class or bean in the ApplicationContext.**

- For **published outer auto-configurations**, use `exclude`/`excludeName`/`spring.autoconfigure.exclude` with its exact class name.
- For **regular @Configuration**, handle the `@Import` source, component scanning, conditions, or application structure.
- For **internal nested configurations**, do not treat unpublished inner classes as independent exclusion points. To disable the entire feature, exclude the outer class; to disable a branch, use an appropriate extension point/condition.
- Excluding the outer class only cuts off **the auto-config import path**. If the class or bean is loaded independently by another path, address that exact loading path.

### Official references

- [Spring Boot 3.3 — Auto-configuration / Disabling Specific Auto-configuration Classes](https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html)
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 API — SpringBootApplication.exclude/excludeName](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/SpringBootApplication.html)
- [Spring Boot 3.3 API — AutoConfigurationImportSelector](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurationImportSelector.html)
- [Spring Framework — Composing Java-based Configurations](https://docs.spring.io/spring-framework/reference/core/beans/java/composing-configuration-classes.html)
