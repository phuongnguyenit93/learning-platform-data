# spring.autoconfigure.exclude via configuration files and startup arguments

## 1. Problem: excluding an auto-configuration without modifying source code

**Spring Boot Auto-configuration** automatically registers configurations and beans based on libraries on the classpath, existing beans, and environment conditions. Most of the time this is the desired behavior, but a specific deployment may need to **exclude** an auto-configuration class.

Examples:
- A file-processing project accidentally pulls in a JDBC library; you do not want Spring Boot to auto-configure a datasource.
- A service uses self-managed JSON configuration and wants to disable Spring Boot's default Jackson configuration.
- When diagnosing a startup failure, you want to test excluding an auto-configuration in a controlled way without rebuilding Java code for each environment.

The standard property for this purpose is:

~~~properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

The value is the **fully qualified class name (FQCN)** of the auto-configuration to skip. The example above is for **Spring Boot 3.x**, where `DataSourceAutoConfiguration` resides in the `org.springframework.boot.autoconfigure.jdbc` package. **Spring Boot 4.x reorganized several auto-configuration packages**, so always verify the class name against your project's version.

`spring.autoconfigure.exclude` can be declared in `application.properties`, `application.yml`/`application.yaml`, profile-specific configuration files, **or passed via startup arguments** such as `--spring.autoconfigure.exclude=...`. The exact same exclusion mechanism is used regardless of which configuration source provides the value.

**Expected result:** the auto-configuration named in the exclusion list will not be applied through Spring Boot's auto-configuration mechanism. This **does not mean** deleting every bean of a given type, removing dependencies from the classpath, or disabling all other auto-configurations.

## 2. Mechanism: excluding at the auto-configuration class selection step

At startup, Spring Boot identifies candidate auto-configuration classes, checks conditions and the exclusion list, and imports the selected classes into the `ApplicationContext`. `@EnableAutoConfiguration` (which `@SpringBootApplication` includes) supports a special key:

~~~java
org.springframework.boot.autoconfigure.EnableAutoConfiguration
        .EXCLUDE_PROPERTY
~~~

That constant has the value **`spring.autoconfigure.exclude`**.

Mental model:

~~~text
Candidate auto-configuration classes
                  |
                  v
Read exclusions from annotations and Environment properties
                  |
                  v
Exclude the named auto-configurations
                  |
                  v
Evaluate conditions of remaining configurations
                  |
                  v
Register matching beans into ApplicationContext
~~~

This is an explanatory model, not a verbatim excerpt of Spring Boot's internal code.

Key distinctions:

| Subject | Does `spring.autoconfigure.exclude` affect it? |
| --- | --- |
| An auto-configuration class auto-imported by Spring Boot | **Yes**, if the exact class name is listed |
| A `@Component` discovered by component scanning | **Not directly** |
| A bean manually created via `@Bean` in application configuration | **Not directly** |
| A user-defined bean of the same type as an auto-config bean | **Does not remove** the user bean |
| A dependency in `pom.xml`/`build.gradle` | **Does not** remove the dependency from the classpath |
| All other auto-configurations | **Not** disabled en masse |

Therefore, use this property only when the target to exclude **is genuinely an auto-configuration**. If a bean still exists, check whether it was created by another configuration or defined by the user.

## 3. Declaring in application.properties

With **Spring Boot 3.5.x**, you can place it in `src/main/resources/application.properties`:

~~~properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

When the application starts with this file, Spring Boot will not auto-import `DataSourceAutoConfiguration` via auto-configuration.

### Excluding multiple classes at once

Use a **comma-separated list of class names**:

~~~properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration,org.springframework.boot.autoconfigure.jackson.JacksonAutoConfiguration
~~~

These are two separate class names, not one long class name.

Points to note:
1. **Use the FQCN**, such as `org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration`, not just `DataSourceAutoConfiguration`.
2. **Use only auto-configuration classes matching the running version.** Package names can differ between Spring Boot lines.
3. If you only want to disable a feature functionally, sometimes a dedicated property like `spring.*.enabled` or an appropriate bean condition already exists; excluding an entire auto-configuration is a broader option.
4. Usually declare the property **once** with the complete list, rather than repeating the same key on multiple lines and assuming they will automatically append.

**Do not specify by bean name:**

~~~properties
# Wrong: the listed items must be auto-configuration classes.
spring.autoconfigure.exclude=dataSource
~~~

`dataSource` in the example is just a bean name, not the FQCN of an auto-configuration class.

## 4. Declaring in application.yml or application.yaml

Same single-class example, using YAML structure:

~~~yaml
spring:
  autoconfigure:
    exclude:
      - org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

Two-class example:

~~~yaml
spring:
  autoconfigure:
    exclude:
      - org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
      - org.springframework.boot.autoconfigure.jackson.JacksonAutoConfiguration
~~~

YAML supports lists, making this easier to read and less prone to comma mistakes with multiple classes. Both `application.yml` and `application.yaml` are YAML extensions supported by Spring Boot.

A comma-separated scalar form is also valid, though **YAML list** form is usually clearer:

~~~yaml
spring:
  autoconfigure:
    exclude: org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration,org.springframework.boot.autoconfigure.jackson.JacksonAutoConfiguration
~~~

**Watch indentation:** `autoconfigure` is a child of `spring`, and `exclude` is a child of `autoconfigure`. The property is `spring.autoconfigure.exclude`, **not** `spring.auto-configuration.exclude` or `spring.autocofiguration.exclude`.

If the same location contains both `application.properties` and `application.yaml`, Spring Boot applies configuration source precedence rules; the docs recommend sticking to one format consistently to avoid confusion over effective values. When both formats exist in the same location, `.properties` takes precedence.

## 5. Passing arguments directly at application startup

With an executable JAR packaged by Spring Boot:

~~~bash
java -jar target/my-app.jar --spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

Important syntax notes:
- `java -jar target/my-app.jar` launches the application; replace the JAR name with your actual artifact.
- `--spring.autoconfigure.exclude=...` is an **application argument** parsed by `SpringApplication` and added to `Environment`.
- `--` starts the property name; use `=` to assign the value.
- **Do not** place `--spring.autoconfigure.exclude` before `-jar` and expect the Java launcher to treat it as a JVM option.

### Excluding multiple classes via the command line

~~~bash
java -jar target/my-app.jar --spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration,org.springframework.boot.autoconfigure.jackson.JacksonAutoConfiguration
~~~

In some shells or CI environments, wrap the entire argument in quotes to prevent shell interpretation:

~~~bash
java -jar target/my-app.jar "--spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration,org.springframework.boot.autoconfigure.jackson.JacksonAutoConfiguration"
~~~

### Starting with the Maven Spring Boot Plugin

If the project uses Maven with `spring-boot-maven-plugin`:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments="--spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration"
~~~

On Windows PowerShell with the Maven Wrapper in the project:

~~~powershell
.\mvnw.cmd spring-boot:run '-Dspring-boot.run.arguments=--spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration'
~~~

On other operating systems with Maven Wrapper, replace `mvn` with `./mvnw`. `spring-boot.run.arguments` is the **Maven plugin property**, while the string starting with `--spring.autoconfigure.exclude` is the argument forwarded to the application.

### Distinguishing application arguments from JVM system properties

You can also set the property with `-D` before `-jar`:

~~~bash
java -Dspring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration -jar target/my-app.jar
~~~

The form above creates a **JVM system property**; the form after `java -jar ... --spring.autoconfigure.exclude=...` creates a **Spring Boot command-line property**. Both enter `Environment`, but they belong to configuration sources with different precedence. By default, `--...` application arguments take higher precedence than JVM system properties and application files.

## 6. Precedence rules when both file and command line are present

Spring Boot aggregates configuration from multiple sources: `application.properties`/`application.yaml`, profile-specific files, environment variables, JVM system properties, and command-line arguments.

**By default, `--spring.autoconfigure.exclude=...` overrides the value declared in application.properties/application.yaml.** This is how you use the same JAR while changing behavior per deployment environment.

Example in `application.properties`:

~~~properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jackson.JacksonAutoConfiguration
~~~

When starting **without passing** `spring.autoconfigure.exclude` on the command line, the effective value is the list containing `JacksonAutoConfiguration`.

If you run:

~~~bash
java -jar target/my-app.jar --spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

the command line supplies a higher-precedence property value. **Do not assume Spring Boot will merge the two lists into `JacksonAutoConfiguration,DataSourceAutoConfiguration`**. When a list property is redefined in a higher-precedence source, list binding uses the value from the winning source and does not merge entries from lower-precedence sources by default.

To keep both exclusions, declare **both names completely in the highest-precedence source**:

~~~bash
java -jar target/my-app.jar --spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jackson.JacksonAutoConfiguration,org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

**Important exception:** exclusions declared via `@SpringBootApplication(exclude=...)` or `@EnableAutoConfiguration(exclude=...)` belong to annotation metadata; property exclusions are combined with annotation exclusions during auto-configuration selection. Thus, overriding the **property value** on the command line does not erase exclusions hard-coded in annotations.

Spring Boot allows disabling automatic addition of application arguments into `Environment` via `SpringApplication.setAddCommandLineProperties(false)`. In such customized setups, you cannot assume `--spring.autoconfigure.exclude` will be processed normally.

## 7. Profile-specific files and deployment configuration

You can scope exclusions to individual profiles. For example, only disabling JDBC auto-configuration initialization when running the `local` profile.

In `src/main/resources/application-local.properties`:

~~~properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

Activate the profile:

~~~bash
java -jar target/my-app.jar --spring.profiles.active=local
~~~

When `local` is active, Spring Boot evaluates configuration from `application-local.properties` alongside other sources; this property can override the same key's list in `application.properties`.

Profile YAML example in `application-local.yaml`:

~~~yaml
spring:
  autoconfigure:
    exclude:
      - org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

You can use `application-prod.properties` or externalized sources outside the JAR for other environments. When deploying one artifact across multiple environments, **command line, external configuration, and profiles** let you change the list without modifying Java source.

**List trap:** if `application.properties` excludes A and `application-local.properties` excludes B, the profile normally picks list B instead of merging A + B. If you want both in the local profile, list both A and B in the local configuration.

## 8. Hands-on example with Java 17 and Spring Boot 3.5

To directly observe the difference, use **JacksonAutoConfiguration**. Spring Boot 3.5 creates a default `com.fasterxml.jackson.databind.ObjectMapper` when Jackson is present and no application-provided `ObjectMapper` bean exists. Thus, excluding this auto-configuration class can be verified by the presence or absence of that bean.

### 8.1 Create a small Maven project

Create `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>exclusion-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-json</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

The example pins **Spring Boot 3.5.7** so package names and Jackson types are deterministic. In a real project, use your managed and tested Boot version rather than copying a fixed version into a project with a different parent.

Create `src/main/java/example/ExclusionDemoApplication.java`:

~~~java
package example;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication(proxyBeanMethods = false)
public class ExclusionDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ExclusionDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner printJacksonState(ApplicationContext context) {
        return args -> {
            boolean exists =
                    context.getBeanNamesForType(ObjectMapper.class).length > 0;
            System.out.println("OBJECT_MAPPER_PRESENT=" + exists);
        };
    }
}
~~~

**Compilable and runnable code** when using the Maven structure above. `CommandLineRunner` executes after context startup and prints whether a Spring bean of type `ObjectMapper` exists.

### 8.2 Running without exclusion

Leave `src/main/resources/application.properties` empty or without `spring.autoconfigure.exclude`, then run:

~~~bash
mvn spring-boot:run
~~~

Expected diagnostic line in the console:

~~~text
OBJECT_MAPPER_PRESENT=true
~~~

Because the JSON starter puts Jackson on the classpath and Jackson auto-configuration creates a default `ObjectMapper` for the sample application.

### 8.3 Excluding via application.properties

Add to `src/main/resources/application.properties`:

~~~properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jackson.JacksonAutoConfiguration
~~~

Run again:

~~~bash
mvn spring-boot:run
~~~

Expected diagnostic line:

~~~text
OBJECT_MAPPER_PRESENT=false
~~~

This observation holds for the **sample project with no user-defined ObjectMapper and no other configuration creating an ObjectMapper**. If a custom `@Bean ObjectMapper` exists, the setting still excludes Jackson auto-configuration, yet the printed line will be `true` due to the user-defined bean.

### 8.4 Excluding via startup arguments

Remove the exclude line from the file or temporarily leave the file empty, then package:

~~~bash
mvn -DskipTests package
~~~

Launch the JAR and pass the exclusion:

~~~bash
java -jar target/exclusion-demo-0.0.1-SNAPSHOT.jar --spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jackson.JacksonAutoConfiguration
~~~

Expected diagnostic line:

~~~text
OBJECT_MAPPER_PRESENT=false
~~~

Restart **without passing exclude**, while the file remains empty:

~~~bash
java -jar target/exclusion-demo-0.0.1-SNAPSHOT.jar
~~~

Expected diagnostic line:

~~~text
OBJECT_MAPPER_PRESENT=true
~~~

The console also shows Spring Boot/Maven logs; only the two `OBJECT_MAPPER_PRESENT=...` lines above are used as direct verification signals.

### 8.5 Same application, multiple ways to supply values

| Source providing exclude | Where is the value set? | When does behavior change? |
| --- | --- | --- |
| `application.properties` | Configuration file | When restarting the app with the new effective config |
| `application.yml` | YAML file | When restarting with updated content |
| `application-local.properties` | Profile-specific file | When the `local` profile is activated at launch |
| `java -jar ... --spring.autoconfigure.exclude=...` | Application argument | When starting the process with the new argument |
| `java -Dspring.autoconfigure.exclude=... -jar ...` | JVM system property | When launching the JVM with that property |

**No real-time effect:** adding a class name to the file after the context has already started **does not remove already-created beans**. You must restart the application or use an intentional context refresh/recreation mechanism.

## 9. Automated testing with ApplicationContextRunner

To verify the property without starting a web server, Spring Boot provides `ApplicationContextRunner`. The test creates a context with `@EnableAutoConfiguration`, then runs both with and without the exclude property.

Create `src/test/java/example/ExcludeAutoConfigurationTests.java` in the Section 8 project:

~~~java
package example;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class ExcludeAutoConfigurationTests {

    @Configuration(proxyBeanMethods = false)
    @EnableAutoConfiguration
    static class TestConfiguration {
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfiguration.class);

    @Test
    void mapperExistsWithoutExclusion() {
        runner.run(context ->
                assertThat(context).hasSingleBean(ObjectMapper.class));
    }

    @Test
    void propertyExcludesJacksonAutoConfiguration() {
        runner.withPropertyValues(
                "spring.autoconfigure.exclude="
                + "org.springframework.boot.autoconfigure.jackson."
                + "JacksonAutoConfiguration")
            .run(context ->
                assertThat(context).doesNotHaveBean(ObjectMapper.class));
    }
}
~~~

**Note:** for the first test to be meaningful, the sample project must include the Jackson starter and **must not set a default exclude in `application.properties`** or other test environment configuration sources. The test builds two separate contexts and enables the exclusion only in the second case.

Run the tests:

~~~bash
mvn test -Dtest=ExcludeAutoConfigurationTests
~~~

Expected result: **2 tests PASS**. `ApplicationContextRunner` simulates properties in `Environment`; the second test proves `spring.autoconfigure.exclude` itself excludes Jackson auto-configuration. To verify how the shell passes `--...`, you should still run the JAR startup example in Section 8.4, since `withPropertyValues(...)` is not a command-line parser.

## 10. Comparison with exclude on Java annotations

Another option is using `exclude` directly on `@SpringBootApplication`:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;

@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)
public class ExampleApplication {
}
~~~

This is only an **illustrative class declaration**, not a standalone program with `main`. In Spring Boot 3.5, `DataSourceAutoConfiguration` has the FQCN shown above.

If you want to write the class name as a string, such as for an optional dependency:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(
    excludeName = "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration"
)
public class ExampleApplication {
}
~~~

Comparison:

| Exclusion method | When is it appropriate? | Things to watch |
| --- | --- | --- |
| `@SpringBootApplication(exclude = ...)` | Decision permanently tied to application code | Must edit/rebuild code to change |
| `@SpringBootApplication(excludeName = "...")` | Need to specify FQCN as a string | Name must match the version |
| `spring.autoconfigure.exclude` in files | Deployment/profile-specific configuration | Can be overridden by higher-precedence sources |
| `--spring.autoconfigure.exclude=...` | Experimentation and multi-environment deployments using the same JAR | Must pass the complete desired list |

With `@EnableAutoConfiguration` directly, `exclude` and `excludeName` carry the same meaning. Exclusions from annotations and properties can apply together: **excluding via property does not undo an exclusion via annotation**.

## 11. Class names depend on the Spring Boot version

The FQCN is particularly critical because `spring.autoconfigure.exclude` takes **class name strings**, not aliases or short names.

| Auto-configuration | Spring Boot 3.5.x | Spring Boot 4.x |
| --- | --- | --- |
| JDBC DataSource | `org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration` | `org.springframework.boot.jdbc.autoconfigure.DataSourceAutoConfiguration` |
| Jackson | `org.springframework.boot.autoconfigure.jackson.JacksonAutoConfiguration` | `org.springframework.boot.jackson.autoconfigure.JacksonAutoConfiguration` |

**Spring Boot 3.5.x** example:

~~~properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

**Spring Boot 4.x** example:

~~~properties
spring.autoconfigure.exclude=org.springframework.boot.jdbc.autoconfigure.DataSourceAutoConfiguration
~~~

Because of structural and default dependency changes across versions, **do not copy Boot 3 class names verbatim into Boot 4** and do not extrapolate Boot 4 Jackson bean creation results from an example run on Boot 3.5. Check your project's Javadoc/version BOM before using.

Excluding a name that is not a valid auto-configuration or whose package changed can cause the application to fail or fail to achieve the intended effect, depending on whether the class exists and how the framework validates the exclusion list. When errors occur, inspect actual logs; do not assume a missing class means it was successfully disabled.

## 12. When exclude is the right solution and when another approach is needed

**Use it** when you are certain a specific auto-configuration does not fit the runtime environment and want to disable that entire configuration. For example, the server provides a JDBC DataSource via another mechanism and you do not want default auto-configuration competing to create a datasource.

**Consider alternatives** if you only need to:
- Replace a default bean: register a `@Bean` following Spring Boot's contract so auto-configuration automatically `backs off` via `@ConditionalOnMissingBean`.
- Toggle a feature by business rules: prefer a dedicated property (if available) or `@ConditionalOnProperty` on application beans.
- Prevent a dependency from appearing in the artifact: edit dependencies in Maven/Gradle; excluding auto-configuration **does not** reduce JAR size or contents.
- Prevent a `@Component` class from being scanned: adjust scanned packages or use scan filters, because `spring.autoconfigure.exclude` does not target component scanning.

**Side effects:** excluding an auto-configuration can leave beans missing that the rest of the application depends on. If there is a mandatory `@Autowired ObjectMapper` and you exclude `JacksonAutoConfiguration` without defining another mapper, the application may fail to start. Exclusions must be tested alongside consumer dependencies.

## 13. Diagnosing whether the exclusion actually took effect

### Verifying effectiveness with the Conditions Evaluation Report

Run the JAR with `--debug` and the exclude property:

~~~bash
java -jar target/my-app.jar --debug --spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

The **Conditions Evaluation Report** reveals which auto-configurations matched, did not match, or were excluded. It is far more reliable than guessing from whether a bean is present or absent.

If the application uses Spring Boot Actuator and diagnostic endpoints are enabled/exposed, `/actuator/conditions` provides condition status; secure the endpoint according to operational policies.

### Checking the actual resolved property value

When results differ from expectations, check:
1. Is `spring.autoconfigure.exclude` set in `application.properties` or YAML?
2. Is a profile file, external config file outside the JAR, environment variable, or JVM system property overriding it?
3. Was `--spring.autoconfigure.exclude=...` passed to the **right Java process**?
4. Does the class name match the Spring Boot version?
5. Was the remaining bean created by a different auto-configuration or a user `@Bean`?

With Actuator properly configured and access permitted, `/actuator/env` can help investigate value origins; do not publicly expose sensitive operational configuration details.

**Especially:** do not assume two `spring.autoconfigure.exclude` lists from two configuration sources will automatically append to each other. When overridden, place all classes to exclude in the single winning source value.

## 14. Common mistakes

| Mistake | Possible effect | Fix |
| --- | --- | --- |
| Using short name `DataSourceAutoConfiguration` | Fails to find the right auto-configuration class | Use the FQCN |
| Using Boot 3 FQCN in a Boot 4 project | Wrong class package | Check Javadoc for the exact version |
| Writing `spring.auto-configure.exclude` | Incorrect property key | Write `spring.autoconfigure.exclude` accurately |
| Placing `--...` before `-jar` | Java launcher does not treat it as an application argument | Place it after the JAR name |
| Assuming CLI appends to the list in the file | File list may be overridden | Pass all required names on the CLI |
| Excluding a self-defined `@Component` | Bean is still scanned | Adjust component scanning or bean configuration |
| Excluding Jackson while still injecting `ObjectMapper` with no alternative source | App may fail due to missing bean | Provide a replacement bean or remove the exclude |
| Adding a new class name to the file without restarting | Running context does not update automatically | Restart with the new configuration |
| Excluding a class used by another auto-config | Triggers dependency failures | Test startup and related features |

## 15. Practice exercises

1. In the Section 8 example project, start when `application.properties` **does not** contain exclude. Observe `OBJECT_MAPPER_PRESENT=true`.
2. Add `spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jackson.JacksonAutoConfiguration`, restart, and verify `false`.
3. Remove the property from the file, run the JAR with `--spring.autoconfigure.exclude=...`, and verify it is still `false`.
4. Put the Jackson exclude in the file; then start with the command line excluding only `DataSourceAutoConfiguration`. Check whether `ObjectMapper` reappears. Explain using the rule that higher-precedence sources override property lists.
5. Run `mvn test -Dtest=ExcludeAutoConfigurationTests` after clearing default excludes. Explain why the two contexts in the test produce different results.

**Self-check question:** Does `spring.autoconfigure.exclude` remove every bean of a type regardless of creation source?

**Answer:** No. It excludes the named auto-configuration class. Manually configured beans or beans created by other sources can still exist.

**Self-check question:** Given `@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)` and a CLI argument that does not exclude datasource, what happens?

**Answer:** The annotation-declared exclusion remains in effect. The CLI only adjusts property values; it does not undo annotations.

## 16. Official documentation for reference

- Spring Boot Reference — Auto-configuration, Disabling Specific Auto-configuration Classes: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
- Spring Boot Reference — Externalized Configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Boot 3.5 Javadoc — `EnableAutoConfiguration`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/EnableAutoConfiguration.html
- Spring Boot 3.5 Javadoc — `DataSourceAutoConfiguration`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/jdbc/DataSourceAutoConfiguration.html
- Spring Boot 4 Javadoc — `DataSourceAutoConfiguration`: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/jdbc/autoconfigure/DataSourceAutoConfiguration.html
