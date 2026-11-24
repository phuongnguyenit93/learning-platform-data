# Excluding auto-configuration via annotation or spring.autoconfigure.exclude

Spring Boot automatically configures an application based on dependencies present on the classpath, registered beans, properties in the Environment, and the type of application running. This mechanism lets a project start with minimal manual configuration. However, sometimes a particular auto-configuration is unsuitable: the application does not use a database, wants to manage an integration itself, or needs to exclude a conflicting default configuration.

`@ConditionalOnProperty` is an annotation for property-driven configuration; this lesson focuses on **how to exclude an auto-configuration class from being applied**. Spring Boot offers two common ways:

- Declaring exclusions on `@SpringBootApplication` or `@EnableAutoConfiguration`.
- Declaring class names in the `spring.autoconfigure.exclude` property.

Both approaches affect the list of auto-configurations that Spring Boot considers. They do not remove libraries from the dependency graph, nor do they block other ways of registering the same bean. To exclude properly, you first need to understand which auto-configuration class is creating the bean and where that bean comes from.

## 1. How is auto-configuration activated?

The main class of a Spring Boot application typically looks like:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

`@SpringBootApplication` combines three main capabilities:

- Marks the application's root configuration class.
- Enables component scanning from the root package and its subpackages.
- Enables Spring Boot's auto-configuration mechanism.

Auto-configuration classes are provided by Spring Boot and integration modules. Boot discovers candidates from their metadata, then evaluates conditions such as classpath, properties, existing beans, and application context type.

For example, if the application has suitable JDBC libraries and required conditions are met, Boot can apply auto-configurations related to `DataSource`. If a web stack is present, Boot can configure components for serving HTTP.

High-level flow:

```text
SpringApplication.run(...)
          │
          ▼
Create and prepare ApplicationContext
          │
          ▼
@EnableAutoConfiguration
          │
          ▼
Discover list of auto-configuration candidates
          │
          ▼
Apply exclusions
          │
          ▼
Evaluate conditions of remaining candidates
          │
          ▼
Register matching bean definitions
          │
          ▼
Instantiate beans and complete context
```

The diagram describes steps conceptually. Processing configuration classes and conditions involves multiple phases; do not use this diagram to infer the exact initialization order of every bean.

## 2. When do you need to exclude auto-configuration?

Do not exclude auto-configurations merely because you want to understand the application better. Spring Boot already designs many auto-configurations to back off when users provide replacement beans. Before excluding, identify a concrete goal.

Valid scenarios include:

1. **The application does not use an auto-configured technology.** For example, the project does not need default datasource configuration.
2. **The application manages that integration itself.** You want to create beans or configure with another library, and the default auto-configuration does not fit.
3. **An auto-configuration conflicts with the current architecture.** Its conditions still pass, yet the application does not want the corresponding default beans.
4. **A shared module is reused across multiple application types.** One application type needs an auto-configuration, while another needs to exclude it.
5. **Need to restrict a default configuration in a specific environment.** You can choose property exclusion in an appropriate profile or deployment configuration.

For example: an application processes only files and messages, without connecting to a database. If the dependency graph accidentally brings JDBC in, you may see datasource auto-configuration being considered. Excluding it makes explicit that the application does not want Boot to configure a datasource.

However, if the application genuinely needs JPA or JDBC, excluding datasource auto-configuration without providing a replacement datasource can cause context startup to fail. Understand downstream dependencies before excluding.

## 3. First approach: exclude on @SpringBootApplication

This is a direct, readable approach when the exclusion list is a fixed part of the application configuration.

Example excluding `DataSourceAutoConfiguration`:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;

@SpringBootApplication(
    exclude = DataSourceAutoConfiguration.class
)
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

`exclude` accepts class literals of the auto-configurations to omit. Advantages:

- IDE supports imports and navigation to the class.
- The compiler catches nonexistent classes or wrong packages.
- Refactoring/renaming can be supported by the IDE.
- The exclusion intent sits right at the application's entry point.

Multiple classes can be excluded at once:

```java
@SpringBootApplication(
    exclude = {
        DataSourceAutoConfiguration.class,
        SomeOtherAutoConfiguration.class
    }
)
public class DemoApplication {
    // main()
}
```

`SomeOtherAutoConfiguration` here is an illustrative name. Replace it with an actual auto-configuration class present in your project's Spring Boot version and dependencies.

**Note on the `DataSourceAutoConfiguration` example:** the `org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration` import is common in earlier Spring Boot lines. Module structure and packages can change across major versions. Use the actual class provided by your version's IDE/API reference; do not copy packages from another project without checking.

### 3.1. @SpringBootApplication already includes @EnableAutoConfiguration

There is no need to add a separate `@EnableAutoConfiguration` just to use `exclude`, because `@SpringBootApplication` already includes that capability and exposes the corresponding exclusion attributes.

The following example is usually redundant:

```java
@SpringBootApplication
@EnableAutoConfiguration(exclude = DataSourceAutoConfiguration.class)
public class DemoApplication {
}
```

Choose one clear place to configure. For typical Boot applications, `@SpringBootApplication(exclude = ...)` is the easiest to recognize.

## 4. Second approach: exclude on @EnableAutoConfiguration

If the application does not use `@SpringBootApplication` and you structure the root configuration manually, you can enable auto-configuration directly:

```java
@Configuration
@ComponentScan("com.example.demo")
@EnableAutoConfiguration(
    exclude = DataSourceAutoConfiguration.class
)
public class ApplicationConfiguration {
}
```

This example illustrates traditional Spring configuration: component scanning and auto-configuration declared separately.

In a new Spring Boot application, you usually do not need to rewrite that structure manually. `@SpringBootApplication` already bundles the common annotations into one entry point. Using `@EnableAutoConfiguration` separately is mainly useful when you need fine-grained control over parts of the configuration.

`exclude` on `@EnableAutoConfiguration` has the same meaning: specified classes are removed from the list of applied auto-configurations.

## 5. Using excludeName when specifying classes by name

Besides `exclude`, Spring Boot provides `excludeName`, which accepts fully qualified class names as strings.

For example:

```java
@SpringBootApplication(
    excludeName = {
        "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration"
    }
)
public class DemoApplication {
    // main()
}
```

Differences:

| Attribute | Type | How to specify |
|---|---|---|
| `exclude` | `Class<?>[]` | `DataSourceAutoConfiguration.class` |
| `excludeName` | `String[]` | Fully qualified class name |

`excludeName` is useful when you do not want a direct compile-time reference to the excluded class, for example when the class belongs to an optional integration for which the current module does not declare a direct compile dependency.

However, strings are not checked by the compiler like class literals. Typos, outdated packages, or mismatched class names are only detected when Spring Boot processes the configuration. Therefore, copy class names from the actual API or dependency and test startup.

You can use `excludeName` on `@EnableAutoConfiguration` similarly:

```java
@EnableAutoConfiguration(
    excludeName = "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration"
)
@Configuration
public class ApplicationConfiguration {
}
```

Do not use `excludeName` to specify starter names, artifacts, or bean names. The value must be the **fully qualified class name of an auto-configuration class**.

## 6. Third approach: the spring.autoconfigure.exclude property

If you prefer keeping the exclusion list in a configuration file instead of Java annotations, use the property:

```properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
```

Spring Boot reads this list of class names when preparing auto-configuration. Equivalent YAML example:

```yaml
spring:
  autoconfigure:
    exclude:
      - org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
```

Both formats express a list of auto-configuration classes to exclude. In `application.properties`, multiple classes can be comma-separated:

```properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration,com.example.integration.LegacyClientAutoConfiguration
```

The second name is only a hypothetical example for a library-supplied class. Add only classes that are actually auto-configuration candidates in the application.

### 6.1. Properties can be scoped by profile

If only one environment needs to exclude a configuration, place the property in a profile-specific file.

Example `application-local.yml`:

```yaml
spring:
  autoconfigure:
    exclude:
      - org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
```

When the `local` profile is active, this exclusion property is loaded alongside other property sources. Another profile without this declaration will not receive the exclusion from `application-local.yml`.

You can activate the profile via configuration:

```properties
spring.profiles.active=local
```

or run argument:

```bash
java -jar app.jar --spring.profiles.active=local
```

This is useful when local/test environments do not need a database integration while other environments still use that auto-configuration. Make sure beans depending on the datasource are also configured appropriately in each profile.

### 6.2. Passing exclusions via the command line

The property can be passed when launching the application:

```bash
java -jar app.jar --spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
```

This lets you change the exclusion list for a launch without editing Java annotations or repackaging the application. It remains a startup-time decision; changing command-line options does not update an already-running context.

For multiple classes, pass a list using property list syntax supported by Spring Boot, such as comma-separated values. When using shells or deployment platforms, make sure commas and dots are not mishandled by wrapper tools.

## 7. Comparing exclusion approaches

| Approach | Example | Advantages | Considerations |
|---|---|---|---|
| `@SpringBootApplication(exclude = ...)` | Class literal on main class | Type-safe, easy to locate in code | List is tied to source code and compile dependencies. |
| `@EnableAutoConfiguration(exclude = ...)` | Class literal on root configuration | Fits when auto-configuration is declared separately | Rarely needed in typical Boot apps. |
| `excludeName` | Fully qualified class name as String | No compile-time reference to the class needed | Compiler does not verify class name. |
| `spring.autoconfigure.exclude` | Property in properties/YAML | Externalized from code, can vary by profile/command line | Need to inspect effective value in the Environment. |

No single option is always best. If the exclusion is a fixed architectural rule of the application, annotations are usually easier to read. If it must vary by profile or deployment environment, properties usually fit better. If an optional class is absent from the compile classpath, `excludeName` or properties avoid a direct import.

## 8. Excluding auto-configuration is not removing a dependency

Suppose the build file declares:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
}
```

The starter and transitive libraries are still resolved onto the classpath by Gradle/Maven. If you exclude `DataSourceAutoConfiguration`, Spring Boot will not apply that auto-configuration class.

This **does not mean**:

- JDBC dependencies are removed from the classpath.
- JDBC classes cannot be used by the application.
- Every database-related auto-configuration is automatically excluded.
- A user-declared `DataSource` bean is deleted.
- A database configuration directly `@Import`ed disappears automatically.

Exclusion operates on **Spring Boot's auto-configuration list**, not on dependency management or component scanning.

If you want to remove an unnecessary library, edit the dependency in Gradle/Maven. If you want to keep the library while preventing Boot from auto-configuring part of it, exclusion is the right mechanism.

## 9. Excluding auto-configuration does not block component scan or @Import

Suppose you exclude `DataSourceAutoConfiguration`:

```java
@SpringBootApplication(
    exclude = DataSourceAutoConfiguration.class
)
public class DemoApplication {
}
```

Yet the application still has its own configuration:

```java
@Configuration(proxyBeanMethods = false)
public class ManualDatabaseConfiguration {

    @Bean
    public DataSource applicationDataSource() {
        return createDataSource();
    }

    private DataSource createDataSource() {
        // Configuration details omitted.
        throw new UnsupportedOperationException("Example only");
    }
}
```

If `ManualDatabaseConfiguration` is component-scanned or imported, Spring still processes it. Exclusion does not apply to bean methods written by the application itself.

Similarly, a library configuration might be imported directly via `@Import(SomeConfiguration.class)`. If that configuration registers beans itself, excluding another auto-configuration class does not block that import path.

This is vital when a bean still exists after an exclusion. Trace the **bean registration source**: auto-configuration, component scan, `@Bean`, `@Import`, or programmatic registration.

## 10. Excluding one auto-configuration can affect multiple beans

An auto-configuration class can declare multiple related beans and configurations. Excluding that class can remove several default beans simultaneously.

For instance, datasource auto-configuration can affect the default datasource bean and components that depend on the datasource. If the application still has other auto-configurations needing `DataSource`, their conditions may no longer match or they may report missing dependencies depending on configuration.

Therefore, before excluding a class:

1. Identify which beans that class provides.
2. Identify other auto-configurations that depend on those beans.
3. Determine whether the application supplies replacement beans itself.
4. Run the application and inspect the condition report after the change.
5. Test business flows that depend on that integration.

Do not judge from a class name alone that an exclusion is harmless. Read the Boot version's API/reference and observe the result in the actual application context.

## 11. When should you override a bean instead of excluding the entire auto-configuration?

Many Spring Boot auto-configurations are designed to **back off** when users supply matching beans, typically via `@ConditionalOnMissingBean`.

If you only want to replace one default bean, you can declare your own bean. Illustrative example:

```java
@Configuration(proxyBeanMethods = false)
public class CustomClockConfiguration {

    @Bean
    public Clock applicationClock() {
        return Clock.systemUTC();
    }
}
```

This example illustrates supplying an application-managed bean, without claiming every auto-configuration creates a `Clock` bean.

Decision guide:

- If you only want to replace **one default bean**, check whether the auto-configuration backs off when a bean of the same type/name is provided.
- If you want to disable the **entire default configuration** of an integration, exclusion may be appropriate.
- If you only want to disable **one small feature** inside an integration, look for a dedicated property supported by the auto-configuration before excluding the whole class.

If an auto-configuration has a dedicated property to turn off a feature, using that property usually preserves other useful beans. Broad class exclusion can remove more configuration than intended.

## 12. Distinguishing auto-configuration class names from starter names

A common mistake is putting a starter name into `spring.autoconfigure.exclude`.

Incorrect:

```properties
spring.autoconfigure.exclude=spring-boot-starter-jdbc
```

That is an artifact/starter name, not an auto-configuration class name.

Correct in format:

```properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
```

The value must be a fully qualified class name. The exact class name must exist in the project's dependency version and must be an auto-configuration candidate.

One starter can bring multiple auto-configuration classes onto the classpath. If you want to exclude only part of it, identify the exact class to exclude rather than guessing from the starter name.

## 13. Identifying which auto-configuration class to exclude

Do not guess class names from dependency names. There are several ways to identify them:

### 13.1. Using an IDE

- Search for classes named `...AutoConfiguration`.
- Check the package and module containing the class.
- Read the `@AutoConfiguration` annotation or the version's corresponding auto-configuration structure.
- Inspect the conditions and `@Bean` methods the class provides.
- Verify that the class belongs to an actual dependency of the project.

With `exclude = SomeAutoConfiguration.class`, the IDE helps import the right class and the compiler validates the type.

### 13.2. Inspecting metadata inside dependency JARs

Modern Spring Boot lines provide the list of auto-configurations through metadata inside JARs, usually at:

```text
META-INF/spring/
└── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Older lines have different metadata mechanisms, such as `spring.factories` for auto-configurations prior to the transition phase. Use documentation matching the Boot version.

The metadata file tells you which classes are published as auto-configuration candidates. It does not by itself prove that the class matched conditions in the application.

### 13.3. Using the condition evaluation report

Run the application with `--debug` to see which auto-configurations were applied or not applied. The report helps identify which class to examine and why a condition matched or failed.

This is usually an effective way when you know which integration produced a bean yet do not know which auto-configuration class was responsible.

## 14. Debugging after excluding

After adding an exclusion, do not just verify whether the application starts. Confirm the right auto-configuration was excluded and that other parts still work.

### Enabling the report via command line

```bash
java -jar app.jar --debug
```

Or configure:

```properties
debug=true
```

Spring Boot can print the **conditions evaluation report**. Locate the section for excluded or unmatched auto-configurations and the corresponding reason.

If using Actuator with appropriate exposure configured, the `/actuator/conditions` endpoint can supply condition information. The `/actuator/beans` endpoint can help verify which beans exist. Only expose management endpoints within secured boundaries.

### Checking actual beans

You can query the context:

```java
@Component
public class StartupInspector implements ApplicationRunner {

    private final ApplicationContext context;

    public StartupInspector(ApplicationContext context) {
        this.context = context;
    }

    @Override
    public void run(ApplicationArguments args) {
        String[] dataSources =
                context.getBeanNamesForType(DataSource.class);

        System.out.println(
                "DataSource bean count: " + dataSources.length
        );
    }
}
```

This example needs to import `javax.sql.DataSource` from the JDK and assumes the application has datasource types on the compile classpath. It only observes beans by type; if an application-declared datasource exists, the count can still be greater than zero even when auto-configuration was excluded.

**Do not use bean counts as the sole proof of exclusion.** Combine the report, bean definition sources, and actual configuration.

## 15. Testing exclusions with @SpringBootTest

You can pass the exclusion property to a test context:

```java
@SpringBootTest(properties = {
    "spring.autoconfigure.exclude="
        + "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration"
})
class AutoConfigurationExclusionTests {

    @Autowired
    ApplicationContext context;

    @Test
    void datasourceAutoConfigurationDoesNotProvideDataSource() {
        assertThat(context.getBeansOfType(DataSource.class))
                .isEmpty();
    }
}
```

The example assumes:

- The test uses a real Spring Boot application context.
- No other configuration manually declares a `DataSource`.
- The excluded class name matches the Spring Boot version in use.
- The project has the required test dependencies.

If the application has a manual `DataSource`, the assertion above will fail even though the auto-configuration was excluded. In that case, the test should check the specific bean or condition supplied by the auto-configuration, rather than asserting no datasource exists at all.

The goal is to test that **the auto-configuration class was not applied**, not to forbid the entire application from having beans of the same type.

## 16. Common mistakes

| Symptom | Possible cause | Resolution |
|---|---|---|
| Application reports it cannot exclude class | Specified name is not an auto-configuration candidate or class name is wrong. | Check metadata, package, and dependency version. |
| `exclude = SomeClass.class` does not compile | Class is not on the compile classpath or package changed. | Check dependency/version; consider `excludeName` if class is an optional integration. |
| Used `spring.autoconfigure.exclude` yet bean still exists | Bean is registered from component scan, `@Bean`, `@Import`, or another auto-configuration. | Trace the bean definition source. |
| Application fails to start after excluding | Another bean depends on the removed bean. | Provide a replacement bean, make consumers conditional, or keep required auto-configuration. |
| Used starter name in property | Confused artifact name with auto-configuration class name. | Use fully qualified class name. |
| Exclusion works only locally | Property placed in a profile file active only locally. | Check active profiles and property sources in other environments. |
| Changed property yet running context did not change | Exclusion is processed at startup. | Restart context/app; use a different dynamic configuration if runtime toggle is needed. |
| Excluded class from another version | Package/class name changed across major versions. | Use class/API reference for the exact Spring Boot version. |
| Thought dependency was removed | Exclusion only omits auto-configuration, not the dependency graph. | Remove the dependency separately if the goal is dropping the library. |

## 17. Workflow for choosing and applying an exclusion

When needing to exclude an auto-configuration, you can follow this sequence:

1. **Identify the unwanted bean or behavior.** Gather logs, the condition report, and bean type/name.
2. **Locate the responsible auto-configuration class.** Check metadata and source/API reference for the exact version.
3. **Check whether a narrower property exists.** If you only need to turn off one feature, use a dedicated property when available.
4. **Check back-off capability.** If you only want to replace one bean, try providing a matching bean instead of excluding the entire configuration.
5. **Choose the exclusion method.** Use annotations for fixed rules; use properties when profile or environment configuration is needed.
6. **Verify downstream dependencies.** Ensure needed beans still have a provider.
7. **Restart and inspect the condition report.** Confirm the class was excluded as intended.
8. **Run tests for related behavior.** Verify both replacement beans and dependent application features.

Do not add multiple exclusions at once before knowing which class caused the issue. Each broad exclusion can alter many bean definitions.

## 18. Practice exercises

### Exercise A — Excluding datasource via annotation

1. Create a Spring Boot project with an appropriate JDBC dependency.
2. Add `DataSourceAutoConfiguration.class` to `@SpringBootApplication(exclude = ...)`, using the exact package for your project's version.
3. Run the application with `--debug`.
4. Inspect the condition report and check datasource beans.
5. Try injecting `DataSource` into a component; observe the behavior if no replacement bean exists.

### Exercise B — Excluding datasource via property

1. Remove the exclusion from the annotation.
2. Add the fully qualified class name to `spring.autoconfigure.exclude` in `application.properties`.
3. Run again and compare the condition report.
4. Move the property to `application-local.yml`, activate the `local` profile, and test with another profile.

The goal is to see that both mechanisms achieve the same exclusion while being declared in different places.

### Exercise C — Trying excludeName

Use `excludeName` with the fully qualified name of the auto-configuration class. Compare with the `exclude` class literal. Note the differences in compile-time checking and refactorability.

### Exercise D — Supplying a replacement bean yourself

1. Remove the exclusion.
2. Create a replacement bean for an integration with `@ConditionalOnMissingBean`.
3. Confirm the auto-configuration backs off if the condition supports it.
4. Compare with excluding the entire auto-configuration class.

Explain why overriding a single bean usually has a smaller blast radius than class-wide exclusion.

### Exercise E — Distinguishing bean sources

After excluding an auto-configuration, create a bean of the same type with `@Bean` in application configuration. Verify it still appears. Explain why exclusion does not block component scanning or user configuration.

## 19. Principles to remember

1. **Exclusion removes an auto-configuration class from Boot's applied list**, without removing dependencies from the classpath.
2. `@SpringBootApplication(exclude = ...)` is the direct choice for fixed rules in code.
3. `@EnableAutoConfiguration(exclude = ...)` fits when you declare auto-configuration separately.
4. `excludeName` takes a fully qualified class name as a String; verify the name since the compiler does not validate it.
5. `spring.autoconfigure.exclude` places the exclusion list in `application.properties`, YAML, profiles, or command-line arguments.
6. Exclusion does not block component scan, `@Bean`, `@Import`, or other independent bean registration sources.
7. Excluding one auto-configuration can affect multiple beans and dependent configurations.
8. If you only want to replace one bean, check `@ConditionalOnMissingBean` and override capability before excluding the whole class.
9. Class names/packages can change across Spring Boot lines; use API references and metadata for the exact version.
10. Verify via the condition report and behavioral tests after making changes.

When excluding an auto-configuration, be able to answer three questions: **which class is being applied, why do you want to exclude it, and which bean will provide the still-needed functionality after exclusion?** Choose annotations when the decision belongs to fixed application configuration; choose `spring.autoconfigure.exclude` when the decision belongs in environment-specific properties.
