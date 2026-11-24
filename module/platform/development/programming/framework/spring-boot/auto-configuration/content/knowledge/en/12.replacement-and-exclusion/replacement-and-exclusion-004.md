# `excludeName` when excluding auto-configuration by fully qualified class name

## 1. Problem to solve

Spring Boot automatically selects **auto-configuration** classes from libraries on the classpath based on conditions such as class presence, existing beans, and configuration values. This reduces manual configuration, but sometimes an application **needs to proactively exclude a specific auto-configuration**.

For example, a service does not want Spring Boot to automatically create a `DataSource` even though the project includes JDBC/HikariCP libraries, because database connections are managed by a different infrastructure layer. The common Java-style exclusion is:

```java
@SpringBootApplication(
    exclude = DataSourceAutoConfiguration.class
)
```

This approach requires the program to **reference the `DataSourceAutoConfiguration` type** at compile time, meaning the appropriate import and dependency must be present. When building an application or library with optional modules, you may need to declare an exclusion **without directly referencing the target class**. In that case, use `excludeName`:

```java
@SpringBootApplication(
    excludeName =
        "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration"
)
```

The value in `excludeName` is a **fully qualified class name (FQCN)**, not a bean name, package name, starter name, or JAR file name. It specifies an **auto-configuration candidate** to omit from automatic importing. In Spring Boot 3.3, this attribute is available on both `@SpringBootApplication` and `@EnableAutoConfiguration`.

> Key takeaway: `excludeName` disables the **automatic import path for the named auto-configuration**. It does not remove dependencies, does not block component scanning in general, and does not delete beans declared by the application itself.

## 2. Exact syntax and a minimal Java 17+ application

Create `src/main/java/demo/ExcludeNameApplication.java` in a Spring Boot 3.3.x project:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(
    excludeName =
        "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration"
)
public class ExcludeNameApplication {

    public static void main(String[] args) {
        SpringApplication.run(ExcludeNameApplication.class, args);
    }
}
```

This is a **compilable Java class** when the project has the Spring Boot starter/runtime. No `import DataSourceAutoConfiguration` is needed because the program only uses a **string**. The `DataSourceAutoConfiguration` class belongs to Spring Boot, with the exact FQCN:

```text
org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
```

With `@SpringBootApplication`, Spring Boot already enables auto-configuration by default; there is no need to add `@EnableAutoConfiguration` on the same class.

If multiple classes need to be excluded, pass an array of names:

```java
@SpringBootApplication(excludeName = {
    "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration",
    "org.springframework.boot.autoconfigure.data.redis.RedisAutoConfiguration"
})
public class ExcludeNameApplication {
    public static void main(String[] args) {
        SpringApplication.run(ExcludeNameApplication.class, args);
    }
}
```

This is an **alternative version** of the first class—do not put two classes with the same name in the same source set. The second name is Spring Boot's auto-configuration for Redis in the 3.3 generation, not a user-created `@Component`.

**Good situations for using strings:** shared code that must run across different dependency sets; reusable configuration for applications with or without optional starters; or a meta-annotation wanting to specify an auto-configuration name without holding a `Class<?>` reference to it. Strings avoid compile-time dependencies **for the exclusion attribute itself**, though all other places in the program must still manage class loading separately.

## 3. Comparing `exclude` and `excludeName`

Both attributes share the goal of excluding **auto-configuration**, differing in how the target is identified:

| Criterion | `exclude` | `excludeName` |
|---|---|---|
| Annotation attribute type | `Class<?>[]` | `String[]` |
| Example | `DataSourceAutoConfiguration.class` | `"org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration"` |
| Requires importing target class in Java code? | Usually yes | No |
| Compiler checks the class name? | Yes, via class literal | No, name can be misspelled |
| Useful when optional library/class is absent from compile classpath? | Inconvenient without compile dependency | Well-suited |
| Exclusion target | Auto-configuration | Auto-configuration |
| Affects `@Component` found by application scanning? | Not directly | Not directly |

Equivalent examples of intent when the target class is available:

```java
// Type-based reference, requires corresponding import
@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)

// Name-based reference, no import of target class needed
@SpringBootApplication(excludeName =
    "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration")
```

The two snippets above are **separate illustrative annotation lines** and must be placed individually on the respective class.

Choose `exclude` when the code already depends on the target class and you want IDE support for navigation/renaming. Choose `excludeName` when you need to specify exclusions **via FQCN strings**, especially when the class may be absent in some dependency variants.

**A subtle point about meta-annotations:** Spring Boot Javadoc warns that when creating a composed annotation wrapping `@EnableAutoConfiguration` or `@SpringBootApplication`, `excludeName` should be preferred to avoid issues reading class literals from meta-annotation metadata. Do not generalize that every `Class<?>` on a direct annotation will always fail if the class is missing at runtime; Spring has mechanisms for reading metadata, and the Javadoc distinguishes direct annotations from composed annotations.

## 4. Actual scope of the exclusion operation

Spring Boot 3.3's auto-configuration process can be understood at a high level:

1. Spring Boot discovers the list of **auto-configuration candidates** from `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` resources in JARs.
2. The framework gathers exclusions declared via `exclude`, `excludeName`, and the `spring.autoconfigure.exclude` environment property.
3. Excluded auto-configuration names are removed from the automatic import list.
4. Remaining candidates proceed to evaluation against their own conditions, such as `@ConditionalOnClass` or `@ConditionalOnMissingBean`.
5. The application context is built from user configuration and the permitted auto-configurations.

Consequently, after excluding `DataSourceAutoConfiguration`:

- JDBC/HikariCP starters **may still be present on the classpath**; `excludeName` does not alter the Gradle or Maven dependency graph.
- A user-declared `DataSource` via `@Bean` **can still exist**.
- Another directly imported configuration or another auto-configuration **can still create related beans** if its conditions allow.
- The bean registration path of the **excluded auto-configuration** will not run as an auto-imported candidate; other side effects executed by user code are not turned off.
- When another auto-configuration depends on beans from the excluded configuration, its conditions may fail to match or it may fail at runtime if poorly written; the whole context must be tested after exclusion.

Do not confuse `excludeName` with "disable the entire feature" in all cases. Inspect the **resulting beans** rather than merely seeing the auto-configuration name in the exclusions list.

### Why must it be an auto-configuration class?

Correct:

```java
@SpringBootApplication(excludeName =
    "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration")
```

Wrong target:

```java
// Do not use bean implementation names or regular @Service classes
@SpringBootApplication(excludeName = "demo.service.PaymentService")
```

A regular `@Service` class is not imported by Spring Boot as an auto-configuration candidate, so `excludeName` is not the tool to disable it. For a class that **exists on the classpath** but is not in the valid auto-configuration list, Spring Boot may throw an error like "classes could not be excluded because they are not auto-configuration classes". If the class **does not exist**, the string does not force the JVM to reference that class; however, excluding a name that has no matching candidate **produces no meaningful change**.

To exclude a component discovered by `@ComponentScan`, use scan filters or adjust the component registration design appropriately. To prevent a self-created bean, use the bean's own condition/definition or change application configuration. Do not swap these mechanisms with auto-configuration exclusion.

## 5. `@EnableAutoConfiguration(excludeName=...)` and configuring with properties

`@SpringBootApplication` combines `@SpringBootConfiguration`, `@EnableAutoConfiguration`, and `@ComponentScan`. Therefore, `@SpringBootApplication(excludeName=...)` is an alias for the exclusion attribute on `@EnableAutoConfiguration`.

If you write configuration without `@SpringBootApplication`, you can still declare:

```java
package demo;

import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableAutoConfiguration(
    excludeName =
        "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration"
)
public class ExcludeJdbcAutoConfiguration {
}
```

This is a **separately compilable Java class** in a Spring Boot project with the appropriate dependencies, though it only declares configuration and is not a standalone runnable program with a `main` method.

Besides annotations, Spring Boot also supports the property:

```properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
```

In `application.yml`, you can declare:

```yaml
spring:
  autoconfigure:
    exclude:
      - org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
```

When multiple names are needed in `.properties`, use a comma-separated list:

```properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration,org.springframework.boot.autoconfigure.data.redis.RedisAutoConfiguration
```

**Governance differences:**

- `excludeName` in an annotation places the exclusion decision in source code and ties it to the startup configuration.
- `spring.autoconfigure.exclude` lets you change the list via property sources per environment, profile, or startup arguments; convenient when you do not want to edit Java code.
- Exclusion sources from annotations and properties **can be applied together**. Setting the property does not clear exclusions hard-coded in annotations; nor should you rely on properties to "re-enable" a name excluded directly on the annotation.
- Check the final resolved property value according to **property source precedence**. If a separate configuration file redefines the list, verify the actual effect at startup.

In Spring Boot 3.3, the full property name is `spring.autoconfigure.exclude`; do not confuse it with `spring.main.*` or `spring.boot.*`.

## 6. Verification example with JUnit 5 and `ApplicationContextRunner`

To verify the actual effect, create **one complete test file** at `src/test/java/demo/ExcludeNameTest.java` in a **Spring Boot 3.3.x, Java 17+** project. The test uses H2 and Spring JDBC to create an observable scenario: without exclusion, auto-configuration creates a `DataSource`; with `excludeName` or the exclusion property, no `DataSource` is automatically created.

```java
package demo;

import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ExcludeNameTest {

    private static final String DATA_SOURCE_AUTO_CONFIGURATION =
            "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration";

    @Configuration(proxyBeanMethods = false)
    @EnableAutoConfiguration
    static class AutoConfigurationEnabled {
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAutoConfiguration(
            excludeName = DATA_SOURCE_AUTO_CONFIGURATION
    )
    static class AutoConfigurationWithExcludeName {
    }

    private ApplicationContextRunner jdbcRunner() {
        return new ApplicationContextRunner().withPropertyValues(
                "spring.datasource.url=jdbc:h2:mem:exclude_name_test",
                "spring.datasource.username=sa",
                "spring.datasource.password="
        );
    }

    @Test
    void baselineCreatesDataSourceAutomatically() {
        jdbcRunner()
                .withUserConfiguration(AutoConfigurationEnabled.class)
                .run(context -> assertEquals(
                        1,
                        context.getBeansOfType(DataSource.class).size()
                ));
    }

    @Test
    void excludeNamePreventsDataSourceAutoConfiguration() {
        jdbcRunner()
                .withUserConfiguration(AutoConfigurationWithExcludeName.class)
                .run(context -> assertTrue(
                        context.getBeansOfType(DataSource.class).isEmpty()
                ));
    }

    @Test
    void propertyAlsoPreventsDataSourceAutoConfiguration() {
        jdbcRunner()
                .withUserConfiguration(AutoConfigurationEnabled.class)
                .withPropertyValues(
                        "spring.autoconfigure.exclude="
                                + DATA_SOURCE_AUTO_CONFIGURATION
                )
                .run(context -> assertTrue(
                        context.getBeansOfType(DataSource.class).isEmpty()
                ));
    }
}
```

Key points when reading the test:

1. `AutoConfigurationEnabled` is the baseline, having `@EnableAutoConfiguration` and no exclusion.
2. `AutoConfigurationWithExcludeName` uses a **compile-time constant string** with `@EnableAutoConfiguration(excludeName = ...)`; no import of the target auto-configuration class is required.
3. `jdbcRunner()` supplies JDBC/H2 configuration without declaring any `@Bean DataSource`. When the HikariCP library and H2 driver are present per the dependencies below, the default branch can create a datasource automatically.
4. The first test confirms exactly **one `DataSource` bean** in the baseline; the following two tests confirm no bean of that type exists because the auto-configuration path creating it was excluded.
5. Each `ApplicationContextRunner` runs an independent application context. The tests **do not query a business database**, require no HTTP server, and need no external database connection.

In a Spring Boot 3.3.x Gradle project **already configured with the Spring Boot plugin and dependency management**, add the following dependencies if not already present:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation 'org.springframework.boot:spring-boot-starter-jdbc'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'com.h2database:h2'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

If dependencies are properly managed by the Spring Boot BOM, no explicit version is needed for H2. `spring-boot-starter-jdbc` supplies the datasource creation path and connection pool for the test, while H2 provides an in-memory database. These dependencies serve the **test scenario**; an application merely using `excludeName` at the annotation level does not need to add JDBC/H2.

Run tests from the Gradle project root:

```bash
./gradlew test --tests demo.ExcludeNameTest
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests demo.ExcludeNameTest
```

**Expected result:** **3 tests pass**. The baseline test has one `DataSource`; the two exclusion tests have no `DataSource`. This expectation is based on Spring Boot 3.3.x and the described dependency set, **not stdout from an actual run**. If the project already has extra configuration manually creating a `DataSource` or another starter interfering, isolate the test runner or adjust assertions to match what you intend to prove.

### When a self-registered bean exists: what happens?

Suppose the application adds:

```java
@Bean
DataSource applicationDataSource() {
    // Return an application-managed DataSource.
}
```

This is an **illustrative snippet, not runnable standalone**. Excluding `DataSourceAutoConfiguration` **does not prevent** the application from registering `applicationDataSource`. That is why checking "whether the context has a `DataSource`" in tests only proves the exclusion's effect when **no other source creates a `DataSource`**.

## 7. Why must the class name be exact?

With `excludeName`, Spring Boot processes a string. The compiler cannot catch typos or package changes in the auto-configuration name.

Examples:

```java
// CORRECT: full name of the auto-configuration
@SpringBootApplication(excludeName =
    "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration")

// WRONG: missing package, not an FQCN
@SpringBootApplication(excludeName = "DataSourceAutoConfiguration")

// WRONG TARGET: application bean/implementation name
@SpringBootApplication(excludeName = "demo.service.PaymentService")
```

These are independent illustrative annotations, not placed simultaneously on one class.

To reliably find the name to exclude:

1. Run the application with `--debug` to read the **Condition Evaluation Report**. Find the auto-configuration associated with the bean/feature you want to disable.
2. Cross-reference the class in the **official Javadoc**, library source code, or the `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` file of the dependency in use.
3. Copy the **exact FQCN**, including package and casing. Do not use `*`, bean names, or package patterns.
4. Write a test confirming the intended auto-configuration was skipped, **not just** checking that the app starts up.
5. When upgrading Spring Boot/starters, review hard-coded names and check whether class names were replaced or moved.

According to Spring Boot documentation, even when auto-configuration classes are public, **the class name for exclusion** is the part considered public API. Do not depend on bean methods, nested configuration classes, or internal auto-configuration structure because those details can change.

## 8. Scenarios where `excludeName` is valuable

### 8.1. Optional module not present in every runtime

An application deploys multiple variants: variant A includes the relevant starter, variant B does not. Shared Java configuration wants to exclude an auto-configuration from module A without declaring a class literal depending on that module.

```java
@SpringBootApplication(excludeName =
    "com.vendor.platform.autoconfigure.OptionalFeatureAutoConfiguration")
```

Here, `com.vendor.platform.autoconfigure.OptionalFeatureAutoConfiguration` is **hypothetical**; before applying it, look up the library's actual auto-configuration name. Using a string lets Java compile even when the vendor's class is absent from the compile classpath. In the variant without the module, there is no matching candidate to exclude; in the variant with the module, the exclusion only matters if it actually participates in the auto-configuration mechanism.

### 8.2. Shared meta-annotation

If a development team builds an annotation bundling configuration policies, it can include `@EnableAutoConfiguration` as a meta-annotation with `excludeName`, for example:

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.context.annotation.Configuration;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Configuration
@EnableAutoConfiguration(excludeName =
    "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration")
public @interface WithoutJdbcAutoConfiguration {
}
```

This is a **compilable Java file** when the Spring Boot dependency exists; to use it, place `@WithoutJdbcAutoConfiguration` on an application configuration class. `excludeName` is especially fitting on a meta-annotation because it avoids declaring class literals on nested annotations, following the Javadoc recommendation.

Do not invent a meta-annotation just to save one line of code if a direct `@SpringBootApplication(excludeName = ...)` is already clear enough.

### 8.3. Environment-specific deployment configuration

If only certain deployments need exclusion, declaring `spring.autoconfigure.exclude` in a property source may be better than hard-coding `excludeName`. Both exclude auto-configurations; the choice mainly concerns **who owns the decision**: shared code or the deployment environment.

## 9. Common mistakes and how to handle them

**Mistake 1 — Passing a bean name to `excludeName`.** `"dataSource"` or `"paymentService"` is a bean name, not an auto-configuration FQCN. Find the actual auto-configuration class or use mechanisms meant for beans/components.

**Mistake 2 — Supplying a package instead of a class.** `"org.springframework.boot.autoconfigure.jdbc"` does not exclude the whole package. The value must be **a class name**; use a `String[]` array for multiple classes.

**Mistake 3 — Assuming dependencies are excluded.** Even when auto-configuration is excluded, the JDBC driver, HikariCP, Redis client, etc. can still reside on the classpath. If the goal is reducing artifact size or dependency vulnerabilities, edit the dependency graph in Gradle/Maven.

**Mistake 4 — Thinking all related beans vanish.** A manually declared `@Bean`, a direct `@Import`, or another auto-configuration can still create beans with the same role. Always verify the bean graph after startup.

**Mistake 5 — Confusing it with `@ComponentScan(excludeFilters=...)`.** Component scan filters primarily affect scanned components; `excludeName` affects the **auto-configuration imports** list. If an application `@Component` is being scanned, handle it via component scanning or bean configuration.

**Mistake 6 — Using a non-auto-configuration class.** Spring Boot may reject exclusions pointing to classes present on the classpath that are not auto-configuration candidates. Do not try to "exclude any `@Configuration`" with `excludeName`.

**Mistake 7 — Misspelling the FQCN and concluding the exclusion worked.** Strings are not checked by the Java compiler. Especially when a name is not on the classpath, the application might still run because nothing matched to exclude. Check both the condition report and actual beans.

**Mistake 8 — Ignoring indirect effects.** Excluding one auto-configuration may prevent another auto-configuration from finding an expected bean, or activate a different fallback bean. Test both startup and dependent beans, not just the primary bean.

**Mistake 9 — Using `excludeName` to replace `@ConditionalOnProperty`.** If you own the auto-configuration and want users to toggle a feature via a flag, put a condition on that feature. `excludeName` fits when an application **proactively disables an entire known auto-configuration**, typically from a library.

**Mistake 10 — Misunderstanding when it takes effect.** Auto-configuration exclusions are processed while building the context. Changing properties or annotations after the application is already running **does not automatically** remove beans from the started context.

## 10. Practical troubleshooting workflow

When an auto-configuration still runs after you declared `excludeName`:

1. Check that the annotation sits on the **actual startup class**, or inspect `spring.autoconfigure.exclude` in the final `Environment`.
2. Verify the **full class name** against the exact dependency version running; do not copy names from another version's documentation without checking.
3. Verify the target is an **auto-configuration candidate** picked by Boot via imports, not a user `@Configuration` or regular bean.
4. Run with `--debug` to view matched/unmatched conditions and the exclusions section; if Actuator is used, check `/actuator/conditions` per the application's access configuration.
5. Inspect beans after startup, such as `context.getBeansOfType(DataSource.class)` or an `ApplicationContextRunner` test; seeing "excluded" in logs alone does not necessarily explain all registered beans.
6. If the bean still exists, trace the **bean definition source**: `@Bean` code, component scan, manual import, or another auto-configuration.
7. Test at least two setups: **without exclusion** and **with exclusion**, using the same dependency/runtime set, to prove a real difference.

Read error messages carefully: a `ClassNotFoundException`/`NoClassDefFoundError` from elsewhere in the code is not necessarily caused by `excludeName`; a string attribute does not shield every optional class reference across the whole application. Conversely, an error saying "not auto-configuration classes" indicates you targeted the wrong kind of class or invalid candidate.

## 11. Takeaways

- `excludeName` takes a **`String[]` of auto-configuration FQCNs**: for example, `org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration`.
- Can be used in **`@SpringBootApplication` or `@EnableAutoConfiguration`**. If a suitable class literal is available, `exclude` provides compile-time type checking.
- `excludeName` is very useful when **optional classes cannot be referenced directly**; pay special attention in composed/meta-annotations.
- Exclusion **only blocks auto-importing the specified auto-configuration**; it does not remove JARs, does not block all component scanning, and does not delete self-registered beans.
- `spring.autoconfigure.exclude` is the mechanically equivalent choice when controlling via environment configuration.
- String names must be exact; verify the Condition Evaluation Report and **test beans after startup**, especially when upgrading dependencies.

### Official documentation for reference

- Spring Boot 3.3 Javadoc — `SpringBootApplication`, `exclude` and `excludeName`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/SpringBootApplication.html
- Spring Boot 3.3 Javadoc — `EnableAutoConfiguration`, exclusions and `spring.autoconfigure.exclude` property: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/EnableAutoConfiguration.html
- Spring Boot Reference — *Auto-configuration*, disabling specific auto-configuration classes: https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html
- Spring Boot 3.3 Reference — *Creating Your Own Auto-configuration*, auto-configuration imports: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
