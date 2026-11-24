# Excluding a configuration does not mean removing dependencies from the classpath

## 1. Lesson objective and common misconception

In Spring Boot, a developer might write:

```java
@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)
public class DemoApplication {
}
```

Then they see the application no longer automatically creates a `DataSource` and conclude: "Spring Boot removed the JDBC driver, JDBC library, or related JARs." **This conclusion is false.** The annotation above only tells Spring Boot **not to apply a specific auto-configuration class** through its auto-configuration mechanism; it **does not modify the Maven/Gradle dependency graph, does not remove JARs from the runtime classpath, and does not delete classes from the application package**.

This lesson covers **auto-configuration replacement and exclusion**. You will learn how to identify which layer you are intervening in, choose the right tool for your target, inspect classes/beans/dependencies independently, and avoid confusion when debugging or handling an unwanted library.

After studying this lesson, you should be able to answer four questions:

1. "Is the library still on the **classpath**?" → check the dependency graph and class loading.
2. "Is the **auto-configuration** class applied by Spring Boot?" → check exclusions and the condition report.
3. "Does a **bean** with that name/type exist in `ApplicationContext`?" → check bean definitions/conditions, including application-defined beans.
4. "Is the JAR still inside the **packaged/deployed artifact**?" → inspect the artifact contents and runtime dependencies.

These four questions are related, yet **not identical**. A library can exist on the classpath with no beans created from it; a bean can still exist even when a specific auto-configuration was excluded, because the bean might be defined in another way.

## 2. Three layers to distinguish

### 2.1. Dependency graph and classpath

`Maven` or `Gradle` decides which direct and transitive artifacts and libraries are included during compilation, testing, running, and packaging. For an application using `spring-boot-starter-jdbc`, the dependency graph typically contains:

- `spring-jdbc`, containing APIs such as `org.springframework.jdbc.core.JdbcTemplate`;
- a JDBC connection pool, such as `HikariCP` from the starter;
- the Spring and Boot dependencies required by the application.

The classpath is the set of classes and resources visible to a class loader at runtime. **Disabling an auto-configuration does not alter the build's dependency graph.** If the `spring-jdbc` JAR is still resolved for runtime, the `JdbcTemplate` class can still be loaded.

Note: having a dependency in the build file is not enough to prove it is on the **runtime** classpath; you must check scope/configuration, dependency resolution, packaging, and the deployment environment. Conversely, removing a direct dependency declaration does not guarantee the artifact is gone if it enters via another transitive path.

### 2.2. Auto-configuration classes

A class annotated with `@AutoConfiguration` is typically discovered by Spring Boot as a candidate via:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Merely having an auto-configuration class **listed inside a JAR** does not guarantee it will be applied. Spring Boot also evaluates exclusions, conditions (`@ConditionalOnClass`, `@ConditionalOnBean`, `@ConditionalOnProperty`, etc.), and related factors.

When you exclude `DataSourceAutoConfiguration`, you affect the **list of auto-configurations imported into the context**. The `DataSourceAutoConfiguration` class itself still exists inside `spring-boot-autoconfigure`, and the JDBC libraries can still remain on the classpath.

### 2.3. Bean definitions and instances in ApplicationContext

`@Bean`, `@Component`, `@Import`, and auto-configuration can create bean definitions. When an auto-configuration is excluded, **beans registered solely by that auto-configuration will not be registered through that auto-import path**.

However:

- Beans declared by the user via `@Bean` or component scanning can still exist.
- A **different** non-excluded auto-configuration can still register beans from the same library if its conditions are satisfied.
- If the user manually creates a `DataSource`, another auto-configuration such as `JdbcTemplateAutoConfiguration` can still create a `JdbcTemplate`, even though `DataSourceAutoConfiguration` was excluded.
- Having a class on the classpath does not mean a bean of that type exists; having a bean does not require it to originate from the default auto-configuration.

Therefore, never deduce "exclude `DataSourceAutoConfiguration` ⇒ it is impossible for any `DataSource` or `JdbcTemplate` to exist."

## 3. Comparison table: excluding configuration vs. removing dependencies

| Action | Primary effect | JAR/classes on classpath | Bean impact |
| --- | --- | --- | --- |
| `@SpringBootApplication(exclude = X.class)` | Prevents Spring Boot from auto-importing auto-configuration `X` | **Unchanged** | Beans registered only by `X` are not created via `X`; other beans may still appear |
| `@SpringBootApplication(excludeName = "fully.qualified.X")` | Same as above, using the class name as a string | **Unchanged** | Same as above |
| `spring.autoconfigure.exclude=...` | Specifies auto-configurations not to apply via config | **Unchanged** | Same as above |
| Unmatched `@ConditionalOnProperty` | Prevents a conditional configuration/bean block from registering | **Unchanged** | Only affects the conditional part |
| Removing a declared dependency from `pom.xml`/`build.gradle` | Changes inputs to dependency resolution | **May change** if no other dependency path remains | Auto-configurations relying on removed classes may stop matching; code referencing those classes may fail |
| Maven `<exclusions>` or Gradle dependency `exclude` | Drops a transitive artifact along that declaration path | **May change**; inspect final graph | May affect conditions and runtime capability; does not directly instruct Boot to exclude an auto-configuration |

**Keywords:** *Excluding auto-configuration* is an action at **the time Spring Boot builds the context**; *excluding a dependency* is an action of **the build tool during dependency resolution**. They can be used together, but they serve two different purposes.

## 4. Three ways to exclude auto-configuration in Spring Boot 3.3

Using `org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration` as the target class to exclude. This is the auto-configuration name in Spring Boot 3.3; on a different Boot version, always verify the actual package/class.

### 4.1. Via `@SpringBootApplication(exclude = ...)`

```java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;

@SpringBootApplication(
    exclude = DataSourceAutoConfiguration.class
)
public class DemoApplication {
}
```

This works when the target class can be referenced at compile time. It does not touch `pom.xml` or `build.gradle`.

### 4.2. Via `excludeName`

```java
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(
    excludeName =
        "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration"
)
public class DemoApplication {
}
```

`excludeName` takes the **fully qualified Java class name**, avoiding referencing that class type directly in source code. This is helpful when keeping source code compatible with dependency combinations where the target class may be absent.

**Distinction:** `excludeName` needs the **auto-configuration class name**, not a bean name (`dataSource`), Gradle module, Maven artifact (`spring-boot-starter-jdbc`), or general package name (`org.springframework.jdbc`).

### 4.3. Via application configuration

In `application.properties`:

```properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
```

Or in `application.yml`:

```yaml
spring:
  autoconfigure:
    exclude:
      - org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
```

If the project needs to exclude multiple classes, declare a list in the appropriate configuration format. This option can be adjusted per deployment environment without changing annotations in source code.

In applications using `@EnableAutoConfiguration` directly instead of `@SpringBootApplication`, the `exclude` and `excludeName` attributes also exist on that annotation.

**Scope note:** all three methods only target valid **auto-configuration classes** managed by the auto-configuration import mechanism. Do not use `exclude` to block an arbitrary `@Configuration` that the application explicitly `@Import`s or a `@Component` picked up by component scanning. If you place a non-auto-configuration class that exists on the classpath into the exclusion list, Spring Boot may report an invalid exclusion error. Locate the exact class in the condition report and documentation for your running version.

## 5. Standalone Java 17+ example: class remains, auto-configuration is off

We create a Spring Boot 3.3.13 application using `spring-boot-starter-jdbc` so that `JdbcTemplate` and `HikariDataSource` are definitely on the runtime classpath. At the same time, we exclude `DataSourceAutoConfiguration` while keeping a user-declared bean to demonstrate that exclude **does not remove other beans**.

### 5.1. Directory structure

```text
classpath-vs-autoconfig/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ClasspathVsAutoConfig.java
```

### 5.2. `pom.xml`

```xml
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
    <artifactId>classpath-vs-autoconfig</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <!-- JDBC API + Spring JDBC + HikariCP and required dependencies -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
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

The JDBC starter brings JDBC libraries into dependency resolution. The auto-configuration exclusion below **does not touch** this `<dependencies>` block.

### 5.3. `src/main/java/demo/ClasspathVsAutoConfig.java`

```java
package demo;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.util.ClassUtils;

@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)
public class ClasspathVsAutoConfig {

    // Application-declared bean, independent of whether
    // DataSourceAutoConfiguration is excluded or not.
    @Bean
    String manualMessage() {
        return "still here";
    }

    public static void main(String[] args) {
        SpringApplication app =
            new SpringApplication(ClasspathVsAutoConfig.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = app.run(args)) {
            ClassLoader loader = ClasspathVsAutoConfig.class.getClassLoader();

            boolean jdbcClass = ClassUtils.isPresent(
                "org.springframework.jdbc.core.JdbcTemplate", loader
            );
            boolean poolClass = ClassUtils.isPresent(
                "com.zaxxer.hikari.HikariDataSource", loader
            );
            boolean autoConfigurationClass = ClassUtils.isPresent(
                "org.springframework.boot.autoconfigure.jdbc"
                    + ".DataSourceAutoConfiguration",
                loader
            );

            System.out.println("jdbcTemplateClass=" + jdbcClass);
            System.out.println("hikariClass=" + poolClass);
            System.out.println(
                "dataSourceAutoConfigurationClass=" + autoConfigurationClass
            );
            System.out.println(
                "dataSourceBean=" + context.containsBean("dataSource")
            );
            System.out.println(
                "jdbcTemplateBean=" + context.containsBean("jdbcTemplate")
            );
            System.out.println(
                "manualMessageBean=" + context.containsBean("manualMessage")
            );
        }
    }
}
```

**Requirements:** JDK 17+, Maven, and permission to download dependencies. From the `classpath-vs-autoconfig` directory, run:

```bash
mvn -q spring-boot:run
```

**Six lines printed by the program** in a scenario matching the POM dependencies above (environment log lines, if any, are excluded from this output):

```text
jdbcTemplateClass=true
hikariClass=true
dataSourceAutoConfigurationClass=true
dataSourceBean=false
jdbcTemplateBean=false
manualMessageBean=true
```

Explanation of each result:

1. `jdbcTemplateClass=true`: `spring-jdbc` is still in runtime dependencies, so the `JdbcTemplate` class can still be loaded.
2. `hikariClass=true`: `HikariCP` is still on the classpath, even though no `DataSource` is auto-created.
3. `dataSourceAutoConfigurationClass=true`: the auto-configuration class itself still exists inside `spring-boot-autoconfigure`. **Being excluded does not mean the class is deleted.**
4. `dataSourceBean=false`: in this minimal program, no user-declared `DataSource` bean exists and `DataSourceAutoConfiguration` is excluded, so there is no `dataSource` bean.
5. `jdbcTemplateBean=false`: `JdbcTemplateAutoConfiguration` requires an eligible `DataSource` to auto-create its bean, so there is no `jdbcTemplate` bean in this case.
6. `manualMessageBean=true`: the manual bean does not depend on `DataSourceAutoConfiguration` and is still registered normally.

**Do not overgeneralize:** if another application declares a `DataSource` itself or has another configuration providing that bean, `JdbcTemplateAutoConfiguration` can keep working even while `DataSourceAutoConfiguration` is excluded. The example intentionally omits declaring a datasource to create an easy-to-verify scenario.

### 5.4. Proving for yourself that removing dependencies differs from excluding auto-configuration

Keep the Java class and `@SpringBootApplication(exclude = ...)` annotation above unchanged. Replace the `spring-boot-starter-jdbc` dependency in `pom.xml` with the basic starter:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
</dependencies>
```

This is **an alternative POM state** for the example, not something to add alongside the JDBC starter. `spring-boot-starter` still supplies Spring Boot core, while the JDBC and HikariCP libraries are not requested by this minimal POM.

Run again:

```bash
mvn -q clean spring-boot:run
```

Expected lines printed by the application:

```text
jdbcTemplateClass=false
hikariClass=false
dataSourceAutoConfigurationClass=true
dataSourceBean=false
jdbcTemplateBean=false
manualMessageBean=true
```

Only after **changing the dependency graph** do we see the two specific JDBC classes disappear from this minimal application's classpath. `DataSourceAutoConfiguration` remains present because Spring Boot core still brings the `spring-boot-autoconfigure` module; nevertheless, it remains excluded. The second change came from the POM, not from the annotation.

Summary of the two runs:

| Observation | With JDBC starter, DataSource auto-config excluded | Basic starter only, still excluded |
| --- | :---: | :---: |
| `JdbcTemplate` class on classpath | Yes | No |
| `HikariDataSource` class on classpath | Yes | No |
| `DataSourceAutoConfiguration` class on classpath | Yes | Yes |
| `dataSource` bean in example | No | No |
| `manualMessage` bean | Yes | Yes |

These results apply to **the two independent POMs in the example**; projects with other dependencies might pull in `spring-jdbc`/HikariCP via other paths, so always check the actual dependency graph.

## 6. Properly removing dependencies in Maven and Gradle

### 6.1. Maven: locating dependency sources

Before removing, inspect the dependency tree:

```bash
mvn dependency:tree
```

Filter just the JDBC group of interest:

```bash
mvn dependency:tree -Dincludes=org.springframework:spring-jdbc,com.zaxxer:HikariCP
```

Read the **parent dependency paths** in the tree as well. If `spring-jdbc` is declared directly, remove or change that declaration in `pom.xml`. If pulled in transitively by another starter/library, consider keeping the parent library and excluding the transitive artifact:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jdbc</artifactId>
    <exclusions>
        <exclusion>
            <groupId>com.zaxxer</groupId>
            <artifactId>HikariCP</artifactId>
        </exclusion>
    </exclusions>
</dependency>
```

The XML example above illustrates **Maven exclusion syntax**, not a recommendation to drop HikariCP in an application that needs a connection pool. If features still use `DataSource`/HikariCP, dropping the artifact can break the app or cause auto-configuration to pick another mechanism. Also, if HikariCP enters via another dependency, it can still be present. Always re-run `dependency:tree`.

### 6.2. Gradle (Groovy DSL): locating dependency sources

In a Java/Spring Boot project using Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-jdbc
./gradlew dependencyInsight --configuration runtimeClasspath --dependency HikariCP
```

In a multi-project Gradle build, run the task on the application module, such as `:app:dependencyInsight` when `app` is the project that actually owns `runtimeClasspath`. These commands illustrate the Gradle Wrapper on shells supporting it; on Windows, you can run `gradlew.bat`.

Example syntax to exclude a transitive artifact on a dependency declaration:

```groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-jdbc') {
        exclude group: 'com.zaxxer', module: 'HikariCP'
    }
}
```

To **stop using the JDBC starter**, remove that starter dependency rather than expecting a Java annotation to strip it from the classpath. Still verify that no other dependency pulls in the same artifacts.

### 6.3. Why not simply "exclude everything" for convenience?

Removing a module from the dependency graph can strip APIs or implementations the application still needs:

- Source files importing `JdbcTemplate` will fail to compile if `spring-jdbc` is removed from the compile classpath.
- Already-compiled classes may hit `ClassNotFoundException` or `NoClassDefFoundError` at runtime if the JAR is missing.
- Another library may require a real JDBC pool; dropping the pool without configuring an alternative can cause startup failure.
- A dependency might be required for a feature even if you do not want **auto-configuration** for that feature.

So **choose according to the real need**: to keep the API for manual configuration, keep the dependency and disable unwanted auto-configuration; to prevent an artifact from appearing at runtime, handle it in build/dependency management and re-test the application.

## 7. Classpath conditions can still match when auto-configuration is excluded

Suppose another non-excluded configuration has a condition:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "org.springframework.jdbc.core.JdbcTemplate")
class JdbcClassPresentConfiguration {

    @Bean
    String jdbcLibraryDetected() {
        return "JDBC class is available";
    }
}
```

This is an **illustrative snippet**, assuming a configuration properly registered by the application. While `spring-jdbc` remains on the classpath, `@ConditionalOnClass` can still match even if `DataSourceAutoConfiguration` is excluded. This condition asks **"does the class exist?"**, not "is there a `JdbcTemplate` bean?" or "which auto-configurations were excluded?".

Conversely, a condition:

```java
@ConditionalOnBean(javax.sql.DataSource.class)
```

checks only whether a bean of type `DataSource` is known at evaluation time. In the Section 5 program, it does not match because no such bean exists; if the application manually registers a `DataSource` bean, the result can change without restoring `DataSourceAutoConfiguration`.

When building a starter, it is common to combine `@ConditionalOnClass` (ensuring the library is present) with `@ConditionalOnMissingBean` (yielding to user-declared beans). However, **the outcome cannot be deduced from a single exclude annotation**: you must inspect the actual conditions of each auto-configuration class and bean state.

## 8. Verifying three things independently: classes, beans, and configuration

A reliable troubleshooting process:

1. **Check the dependency graph:** use `mvn dependency:tree` or Gradle `dependencies`/`dependencyInsight` for the right module and `runtimeClasspath`. This answers "where does the artifact come from?".
2. **Check class loading:** use `ClassUtils.isPresent("fully.qualified.Class", classLoader)` as in the example, or inspect the executable JAR structure. This answers "can the class be loaded in the running runtime?". Do not infer solely from IDE autocomplete.
3. **Check beans:** use `ApplicationContext.containsBean("name")`, `getBeanNamesForType(...)`, or suitable introspection tools to see registered beans. This answers "does Spring have that bean?".
4. **Check the condition report:** run the application with `--debug` to view the condition report and excluded auto-configurations list when version/logging settings allow. With a suitable Actuator setup, `/actuator/conditions` shows condition outcomes. This answers "why was an auto-configuration applied or skipped?".
5. **Check the deployable artifact:** after building an executable JAR, inspect the libraries actually packaged, e.g., `jar tf target/app.jar` (adjust filename to your real artifact). Maven/Gradle may have multiple packaging tasks; do not assume the JAR being executed is the one you inspected if deployment uses another artifact.
6. **Test across scenarios:** test the application with exclude only; after changing POM/Gradle; and with a manual bean. Compare classpath data, condition reports, and actual beans rather than concluding from a single log line.

Example inspecting the contents of a Spring Boot executable JAR:

```bash
mvn -q package
jar tf target/classpath-vs-autoconfig-1.0.0.jar
```

With the POM in Section 5.2, you can find the libraries containing `spring-jdbc` and `HikariCP` under `BOOT-INF/lib/`. With the basic-starter-only POM in Section 5.4, they are no longer included via that direct dependency (unless the build has another dependency source). **An auto-configuration exclude never removes these JAR entries.**

### 8.1. Symptom patterns and where to trace next

| Observation | Likely reality | Next check |
| --- | --- | --- |
| `JdbcTemplate.class` still loads after `exclude` | JDBC JAR is still on runtime classpath | `dependency:tree` / `dependencyInsight` and JAR contents |
| Condition report says `DataSourceAutoConfiguration` is excluded, yet `DataSource` bean exists | Bean may be declared by `@Bean`, `@Import`, or another configuration | Locate the bean definition source; inspect bean name and type |
| No `DataSource` bean, yet `HikariDataSource` class exists | Class presence does not require a bean | Separate classpath checks from `ApplicationContext` |
| `@ConditionalOnClass(JdbcTemplate.class)` still matches | Class is still present despite another auto-config being excluded | Inspect dependency graph; review specific condition |
| Dependency removed, yet IDE or runtime still sees the class | Another transitive path exists; runtime/IDE classpaths differ | Check dependency graph for the right configuration, rebuild, verify running artifact |
| Excluded a regular `@Configuration` name and Spring Boot errors | Target is not a valid auto-configuration per importer | Use manual config disabling methods; identify true auto-config |
| Removing dependency leads to `NoClassDefFoundError` | Code or library still references the missing class | Restore/replace implementation, align code or dependencies |

## 9. Common mental traps and design mistakes

### 9.1. "Auto-config was excluded, so the dependency is no longer an issue"

False. The JAR may still be packaged in the artifact, remain present at runtime, and be used by other components. If the goal is to **eliminate an unwanted library from the binary, shrink footprint, or address dependency alerts**, annotation-level exclude does not achieve that. You must fix the version, scope, or actual dependency graph, then verify the deployed artifact. Presence of a library in a binary does not by itself prove an exploitable vulnerability; security assessment still requires checking version, configuration, and attack paths.

### 9.2. "Excluding one auto-config turns off the whole feature"

Not guaranteed. A feature may have **multiple auto-configurations** with independent conditions, and the application may register similar beans itself. For instance, excluding `DataSourceAutoConfiguration` does not delete user-written `DataSource` `@Bean` methods. If the goal is to disable an entire integration, identify all bean-creation sources, on/off properties, and dependencies of the feature before deciding.

### 9.3. "Removing one JAR turns off every related condition"

Not always true. Some auto-configurations depend on **other** classes still on the classpath, can fall back to another implementation, or are activated by other bean/property conditions. Conversely, application code may fail to start if it directly references the removed class. Always test and read the condition report.

### 9.4. "Excluding auto-config is the same as deleting a @Configuration"

Not the same. `exclude` on `@SpringBootApplication`/`@EnableAutoConfiguration` primarily affects how Boot **imports auto-configuration candidates**. It is not a mechanism for removing every configuration explicitly imported or component-scanned by the user. Official docs also recommend starter auto-configurations **only** be loaded via `AutoConfiguration.imports`, avoiding accidental component scanning.

### 9.5. "Using `excludeName` instead of `exclude` will drop the dependency"

No. The difference between the two attributes is solely **how the target class is specified**: `Class` versus fully qualified `String` class name. Neither attribute edits `pom.xml`, `build.gradle`, or the contents of an executable JAR.

## 10. Self-check

**Question 1.** An application depends on `spring-boot-starter-jdbc` and has `@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)`. You call `ClassUtils.isPresent("org.springframework.jdbc.core.JdbcTemplate", loader)`; predict the result?  
**Answer:** In the typical JDBC starter dependency graph, the result is true, because `spring-jdbc` is still brought into runtime. Exclude only changes the list of applied auto-configurations.

**Question 2.** You exclude `DataSourceAutoConfiguration` but declare `@Bean DataSource customDataSource()` yourself. Can a `JdbcTemplate` bean still be created by another auto-configuration?  
**Answer:** Yes. If there is a single eligible `DataSource` candidate and the remaining conditions are met, `JdbcTemplateAutoConfiguration` can register `JdbcTemplate`. You cannot conclude that all JDBC beans vanish.

**Question 3.** To remove the `HikariCP` JAR from the runtime classpath, should you only write `spring.autoconfigure.exclude=...DataSourceAutoConfiguration`?  
**Answer:** Not enough. You must adjust the Maven/Gradle dependency graph or appropriate scope, verify the artifact is no longer resolved via other paths, and test the application.

**Question 4.** Can `@ConditionalOnClass(JdbcTemplate.class)` match when `DataSourceAutoConfiguration` is excluded?  
**Answer:** Yes. A condition checking a **class** differs from a condition checking a bean or whether a specific auto-configuration was applied.

**Question 5.** Is `@SpringBootApplication(excludeName = "dataSource")` valid?  
**Answer:** No. `excludeName` takes an **auto-configuration's fully qualified class name**, e.g., `org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration`; `dataSource` can only be a bean name.

**Question 6.** You remove the direct `spring-jdbc` dependency, yet `dependencyInsight` still reports this class/module at runtime. Likely reason?  
**Answer:** Another dependency still pulls `spring-jdbc` in transitively. You must trace all paths in the dependency graph and inspect the final artifact.

**Question 7.** You want to keep the JDBC API to define beans manually, while stopping Boot from auto-creating a DataSource when configuration is missing. What is the first appropriate action?  
**Answer:** Keep the required JDBC dependency and consider excluding `DataSourceAutoConfiguration` specifically or adjusting related conditions/properties; then write and test the manual configuration. There is no need to strip `spring-jdbc` from runtime.

## 11. Takeaways and official references

- `exclude`, `excludeName`, and `spring.autoconfigure.exclude` **exclude an auto-configuration from automatic application**; they do not remove JARs from the classpath.
- **Classpath, auto-configuration, and the bean registry are three distinct layers.** A class can remain with no bean; an auto-configuration can be excluded while a bean from elsewhere still exists.
- To **change runtime dependencies**, edit the build file or dependency management in Maven/Gradle and inspect the actual dependency graph.
- To **disable automatic behavior while keeping the API**, keep the required dependencies and use properly scoped configuration exclusions/conditions.
- To prove results, verify the dependency graph, class loadability, beans in context, condition report, and packaged artifact together.

References:

1. Spring Boot 3.3 — [Auto-configuration: Using Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html), especially *Disabling Specific Auto-configuration Classes*.
2. Spring Boot 3.3 — [Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html), *Locating Auto-configuration Candidates* and *Class Conditions*.
3. Spring Boot 3.3 — [`@SpringBootApplication` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/SpringBootApplication.html), attributes `exclude`, `excludeName`.
4. Spring Boot 3.3 — [`@EnableAutoConfiguration` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/EnableAutoConfiguration.html).
5. Gradle — [Viewing Dependencies and `dependencyInsight`](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html).
6. Apache Maven — [Maven Dependency Plugin: dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/usage.html).