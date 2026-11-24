# Auto-Configuration Not Discovered Due to Missing Resource or Incorrect Registration Class Name in Spring Boot

## 1. Identifying the Right Error Type

A library may already contain a valid `@AutoConfiguration` class and `@Bean` methods, yet the consuming application still creates no beans from the library. A common cause is that Spring Boot cannot find the auto-configuration class in its list of candidates.

In Spring Boot 3.3, this list is published through the resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

The resource must be on the runtime classpath and list the exact fully qualified name of the configuration class. If the file is missing, placed in the wrong directory, not packaged into the JAR, or has an incorrect class name inside, auto-configuration may not be loaded as intended.

Three scenarios must be separated:

1. **Descriptor not found:** Spring Boot has no candidate list from that JAR, so the class is not discovered through the auto-configuration mechanism.
2. **Descriptor has an entry, but the class name is wrong or the class is missing from the classpath:** Boot read the candidate name but cannot load the corresponding class; startup may fail with an import/class loading error.
3. **Class was discovered, but conditions do not match:** the class is in the candidate list, but annotations such as `@ConditionalOnClass`, `@ConditionalOnProperty`, or `@ConditionalOnResource` prevent the configuration from being applied.

These three scenarios require different checks. Do not modify conditions when the actual problem is that the imports file was not packaged.

## 2. How Auto-Configuration Discovery Works in Spring Boot 3.3

An application enables auto-configuration through `@SpringBootApplication` or `@EnableAutoConfiguration`. This annotation uses Spring Boot's import candidates mechanism to read the list of classes published on the classpath.

For external libraries, Boot looks for the file:

`META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

inside JARs on the classpath. Each line in the file is a fully qualified class name (FQCN), for example:

~~~text
com.acme.widget.autoconfigure.WidgetAutoConfiguration
com.acme.widget.autoconfigure.WidgetWebAutoConfiguration
~~~

Comments starting with `#` can be added:

~~~text
# Core integration
com.acme.widget.autoconfigure.WidgetAutoConfiguration

# Optional web integration
com.acme.widget.autoconfigure.WidgetWebAutoConfiguration
~~~

Boot reads the candidate list from the resource, then proceeds to apply exclusions, import filters, ordering, and conditions. Appearing in the imports file means the class is published as a candidate; it does not yet guarantee that all beans inside it will be created.

### Overall Flow

~~~mermaid
flowchart TD
    A["@SpringBootApplication / @EnableAutoConfiguration"] --> B["Locate AutoConfiguration.imports on classpath"]
    B --> C["Read each FQCN"]
    C --> D["Load auto-configuration class"]
    D --> E["Apply exclusions and import filters"]
    E --> F["Evaluate @Conditional"]
    F --> G{"Condition matches?"}
    G -->|"Yes"| H["Register configuration and bean definitions"]
    G -->|"No"| I["Skip configuration per condition"]
~~~

The Spring Boot 3.3 documentation specifies that auto-configuration should only be loaded by being listed in the imports file; the class should not be the target of component scanning. If supporting configurations need to be loaded, use `@Import` explicitly.

## 3. Creating the Correct AutoConfiguration.imports File

In the module containing the auto-configuration, place the resource at the exact path:

~~~text
acme-widget-autoconfigure/
└── src/
    └── main/
        ├── java/
        │   └── com/acme/widget/autoconfigure/
        │       └── WidgetAutoConfiguration.java
        └── resources/
            └── META-INF/
                └── spring/
                    └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

File content:

~~~text
com.acme.widget.autoconfigure.WidgetAutoConfiguration
~~~

Points that must be right:

- The directory name is `META-INF/spring`, not `META-INF/springs`, `META-INF/springboot`, or a Java package directory.
- The filename must be exactly `org.springframework.boot.autoconfigure.AutoConfiguration.imports`, including the `.imports` extension.
- Each class must be on its own line.
- Write the FQCN, not a short name like `WidgetAutoConfiguration`.
- Do not write Java syntax such as `import com.acme...`, do not add trailing commas, and do not wrap the class name in quotes.
- `#` comments can be used; do not use `//` comments.
- The resource must be packaged in a JAR that is placed on the runtime classpath.

This is resource metadata, not Java source. Placing the file next to the class in `src/main/java` or inside the class's package directory will not produce the correct resource path.

## 4. The Class Name in the File Must Exactly Match the Compiled Class

Suppose the source declares:

~~~java
package com.acme.widget.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;

@AutoConfiguration
public class WidgetAutoConfiguration {
}
~~~

The FQCN must be:

~~~text
com.acme.widget.autoconfigure.WidgetAutoConfiguration
~~~

Some common mistakes:

| Invalid entry | Reason |
| --- | --- |
| `WidgetAutoConfiguration` | Missing package |
| `com.acme.widget.WidgetAutoConfiguration` | Package does not match the source declaration |
| `com.acme.widget.autoconfigure.widgetAutoConfiguration` | Incorrect capitalization in the class name |
| `com.acme.widget.autoconfigure.WidgetAutoConfiguration.java` | Imports requires the class name, not the source filename |
| `com.acme.widget.autoconfigure.WidgetAutoConfiguration.class` | Do not include the bytecode file extension |
| `com.acme.widget.autoconfigure.WidgetAutoConfiguration,` | Comma does not belong in an FQCN |

Package and class names are case-sensitive. This is easily overlooked when developing on a case-insensitive filesystem while building or deploying on Linux.

### Nested Classes Use the $ Sign

Spring Boot allows declaring an auto-configuration class that is not a top-level class. In that case, the name in the imports file uses `$` to separate the outer class from the nested class:

~~~java
package com.acme.widget.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;

public class WidgetConfigurations {

    @AutoConfiguration
    public static class WebAutoConfiguration {
    }
}
~~~

Corresponding entry:

~~~text
com.acme.widget.autoconfigure.WidgetConfigurations$WebAutoConfiguration
~~~

The name uses dots between the package and outer class, followed by `$` for the nested class. In practice, top-level auto-configuration classes are usually easier to read and less error-prone to register.

## 5. Verifying the Class Is Compiled and the Package Has Not Changed

Before inspecting the JAR, cross-check three things:

1. The `package` statement at the top of the Java file.
2. The actual class name in source.
3. The class path after compilation.

For the class `com.acme.widget.autoconfigure.WidgetAutoConfiguration`, the bytecode is normally located at:

~~~text
com/acme/widget/autoconfigure/WidgetAutoConfiguration.class
~~~

Gradle:

~~~bash
./gradlew :acme-widget-autoconfigure:clean :acme-widget-autoconfigure:compileJava
~~~

Maven:

~~~bash
./mvnw -pl acme-widget-autoconfigure -am clean compile
~~~

After compiling, check the class file in the output directory:

~~~text
Gradle: acme-widget-autoconfigure/build/classes/java/main/
Maven:  acme-widget-autoconfigure/target/classes/
~~~

If the class was moved to another package or renamed, update the FQCN in the imports file at the same time. Renaming only the source while keeping the old entry leaves behind a registration name that no longer exists.

## 6. Placing the Resource in the Right Module of a Multi-Module Build

A library structure typically has an auto-configure module and a starter module:

~~~text
acme-widget/
├── acme-widget-autoconfigure/
│   ├── src/main/java/com/acme/widget/autoconfigure/
│   │   └── WidgetAutoConfiguration.java
│   └── src/main/resources/META-INF/spring/
│       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
└── acme-widget-spring-boot-starter/
    └── build.gradle or pom.xml
~~~

The `autoconfigure` module owns the configuration classes and the descriptor. The `starter` module typically pulls in the autoconfigure module along with the runtime dependencies needed by the application.

Gradle Kotlin DSL in the starter:

~~~kotlin
dependencies {
    api(project(":acme-widget-autoconfigure"))
}
~~~

If you do not want dependencies of the autoconfigure module exposed on the starter's compile API, `implementation` can be used depending on module organization. What must be guaranteed is that the autoconfigure JAR is present on the consumer's runtime classpath.

Maven in the starter:

~~~xml
<dependency>
    <groupId>com.acme</groupId>
    <artifactId>acme-widget-autoconfigure</artifactId>
    <version>1.0.0</version>
</dependency>
~~~

A frequent mistake is having the imports file in the autoconfigure module, yet the starter does not declare this module, or declares it only in test/provided scope. In that case, module tests may see the class, but the real application will not have the JAR containing the descriptor on its runtime classpath.

Check the dependency graph:

~~~bash
# Gradle: application dependencies at runtime
./gradlew :sample-app:dependencies --configuration runtimeClasspath

# Gradle: inspect why the module was selected
./gradlew :sample-app:dependencyInsight --dependency acme-widget-autoconfigure --configuration runtimeClasspath

# Maven: application dependency tree
./mvnw -pl sample-app dependency:tree
~~~

## 7. Verifying the Resource Was Packaged into the JAR

Having the file in the source tree is not enough. You must inspect the built artifact because resource configurations, excludes, or custom source sets can prevent the file from being included in the JAR.

Gradle:

~~~bash
./gradlew :acme-widget-autoconfigure:clean :acme-widget-autoconfigure:jar
jar tf acme-widget-autoconfigure/build/libs/acme-widget-autoconfigure-1.0.0.jar
~~~

Maven:

~~~bash
./mvnw -pl acme-widget-autoconfigure clean package
jar tf acme-widget-autoconfigure/target/acme-widget-autoconfigure-1.0.0.jar
~~~

The entry list must contain exactly:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

On Windows PowerShell, you can filter the output:

~~~powershell
jar tf acme-widget-autoconfigure/build/libs/acme-widget-autoconfigure-1.0.0.jar |
    Select-String "AutoConfiguration.imports"
~~~

On macOS/Linux:

~~~bash
jar tf acme-widget-autoconfigure/target/acme-widget-autoconfigure-1.0.0.jar |
    grep "AutoConfiguration.imports"
~~~

If the entry is missing, investigate resource packaging:
- Is the file under `src/main/resources` of the right module?
- Does the build have custom `sourceSets` or `resources` that replace this directory?
- Does Maven `<resources>` have `<includes>` or `<excludes>` filtering out `.imports` files?
- Is the resource being added to an artifact with the right classifier/module?
- Are you inspecting an old JAR in the build/target directory by mistake?

Do not inspect only the application JAR if auto-configuration lives in a nested dependency JAR. First identify the actual `acme-widget-autoconfigure` JAR being packaged and inspect that JAR directly.

## 8. Reading the Descriptor Content Inside the Artifact

After confirming the entry exists, check the actual content inside the JAR. Make sure the FQCN line matches the source and no old class name remains.

You can extract the resource into a temporary directory:

~~~bash
mkdir inspect-autoconfigure
cd inspect-autoconfigure
jar xf ../acme-widget-autoconfigure-1.0.0.jar META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Then open the file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Expected content:

~~~text
com.acme.widget.autoconfigure.WidgetAutoConfiguration
~~~

If the source file is correct but the artifact contains an old name, check:
- Whether the JAR was rebuilt from the current module.
- Whether another resource with the same name exists in another source set or module.
- Whether the build pipeline is pulling an artifact from a local Maven/Gradle cache or an outdated repository.
- Whether multiple versions of the same module exist on the runtime classpath.

When releasing, inspect the exact JAR version that the application consumes, not just the JAR in the development workspace.

## 9. Distinguishing a Missing Descriptor from an Incorrect Class Name

The two errors have different symptoms:

| Check | Descriptor missing/wrong path | Incorrect FQCN in descriptor |
| --- | --- | --- |
| `jar tf` | File not found at the exact path | File is visible |
| Reading file content | No file to read | Entry exists, but class name is wrong |
| `ImportCandidates` | Does not contain the expected class | Contains the wrong string or lacks the expected class |
| Class loading | No candidate to load | Candidate may cause a class loading/import error |
| Resolution | Fix location/resource packaging | Fix FQCN, package, class name, or dependency |

If the file has multiple lines, inspect every entry. One valid line does not compensate for an invalid line if Boot still has to process the invalid candidate in the same list.

Do not use the fact that the application "starts up" as sole proof. If auto-configuration is skipped and no mandatory bean depends on it, the application can still start normally.

## 10. Checking the Candidate List Directly with ImportCandidates

Spring Boot provides `ImportCandidates` to read the list of import candidates using the exact classpath mechanism. This is a better way to verify the descriptor than manually concatenating resource paths as strings.

Example JUnit 5 and AssertJ test:

~~~java
package com.acme.widget.autoconfigure;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.context.annotation.ImportCandidates;

import static org.assertj.core.api.Assertions.assertThat;

class AutoConfigurationImportsTests {

    @Test
    void descriptorContainsTheExpectedAutoConfiguration() {
        var candidates = ImportCandidates.load(
                AutoConfiguration.class,
                getClass().getClassLoader());

        assertThat(candidates.getCandidates())
                .contains(WidgetAutoConfiguration.class.getName());
    }

    @Test
    void descriptorResourceIsVisibleOnTheTestRuntimeClasspath() {
        String resource =
                "META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports";

        assertThat(getClass().getClassLoader().getResource(resource))
                .isNotNull();
    }
}
~~~

The first test confirms that Boot reads the candidate with the exact name. The second test confirms that the resource path can be found on the test runtime classpath.

In a multi-module build, place the test in the module containing the auto-configuration or in a consumer test module that actually pulls in the starter. If the test only runs inside the autoconfigure module, it does not prove that the starter delivers that dependency to the final application.

Run with Gradle:

~~~bash
./gradlew :acme-widget-autoconfigure:test --tests "*AutoConfigurationImportsTests"
~~~

Run with Maven:

~~~bash
./mvnw -pl acme-widget-autoconfigure -Dtest=AutoConfigurationImportsTests test
~~~

This is a metadata discovery test. It does not replace dedicated tests for bean registration and auto-configuration conditions.

## 11. Distinguishing Discovery Tests from Bean Behavior Tests

A test using:

~~~java
new ApplicationContextRunner()
        .withConfiguration(
                AutoConfigurations.of(WidgetAutoConfiguration.class));
~~~

passes the class directly into the runner. This test is useful for verifying beans, but **does not verify** whether the `AutoConfiguration.imports` file is read. If the descriptor is missing, the test can still pass because the class was passed directly.

To test end-to-end discovery, you need a consumer context that enables `@EnableAutoConfiguration` and depends on the starter/JAR like a real application.

Example test application configuration:

~~~java
@SpringBootConfiguration
@EnableAutoConfiguration
static class ConsumerApplication {
}
~~~

Integration test:

~~~java
@SpringBootTest(classes = ConsumerApplication.class)
class StarterDiscoveryIntegrationTests {

    @Autowired
    ApplicationContext context;

    @Test
    void discoversLibraryAutoConfigurationFromTheStarter() {
        assertThat(context).hasSingleBean(WidgetClient.class);
    }
}
~~~

This test is meaningful when the test runtime classpath contains only the dependencies the consumer actually declares. Do not add `WidgetAutoConfiguration.class` via `@Import` or `AutoConfigurations.of(...)` in this test, as doing so bypasses the discovery path you need to verify.

## 12. Do Not Confuse AutoConfiguration.imports with spring.factories

In older Spring Boot versions, auto-configuration was registered via the `EnableAutoConfiguration` key in `META-INF/spring.factories`. Spring Boot 2.7 introduced the dedicated imports file; Spring Boot 3.x uses `AutoConfiguration.imports` to discover auto-configuration candidates.

For Boot 3.3, the standard file is:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Do not expect a legacy `EnableAutoConfiguration` entry in `spring.factories` to replace this file.

However, this does not mean the entire `spring.factories` file must be deleted. Spring Boot still uses that file for several other extension points, such as `AutoConfigurationImportFilter` and `AutoConfigurationImportListener`. Move only the auto-configuration registration mechanism to the imports file; keep other entries if they are still used by the framework.

## 13. Verifying the Application Enables Auto-Configuration and Does Not Exclude the Class

Even when both the descriptor and FQCN are correct, auto-configuration will not be applied if the application does not enable the auto-configuration mechanism.

Typically an application uses:

~~~java
@SpringBootApplication
public class SampleApplication {

    public static void main(String[] args) {
        SpringApplication.run(SampleApplication.class, args);
    }
}
~~~

`@SpringBootApplication` already includes `@EnableAutoConfiguration`. If this composite annotation is not used, the root configuration must enable `@EnableAutoConfiguration`.

Also check exclusions:

~~~java
@SpringBootApplication(
        exclude = LegacyWidgetAutoConfiguration.class
)
public class SampleApplication {
}
~~~

Or the property:

~~~properties
spring.autoconfigure.exclude=com.acme.widget.autoconfigure.WidgetAutoConfiguration
~~~

If the class is in the exclusion list, the candidate may exist in the descriptor but not be applied. Check:
- `exclude` or `excludeName` on `@SpringBootApplication` / `@EnableAutoConfiguration`.
- The `spring.autoconfigure.exclude` property.
- Custom `AutoConfigurationImportFilter` implementations from the application or dependencies.
- Whether the application is actually running the expected main configuration and runtime profile.

## 14. When the Candidate Is Found but the Bean Still Does Not Appear

If `ImportCandidates` already returns the exact FQCN and the class can be loaded, the next step is to read the condition report. Do not continue editing the imports file once discovery has succeeded.

An auto-configuration may have:

~~~java
@AutoConfiguration
@ConditionalOnClass(WidgetClient.class)
@ConditionalOnProperty(
        prefix = "acme.widget",
        name = "enabled",
        havingValue = "true"
)
public class WidgetAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    WidgetClient widgetClient() {
        return new DefaultWidgetClient();
    }
}
~~~

Conditions that can prevent the configuration from applying:
- The dependency containing `WidgetClient` is not on the runtime classpath.
- The `acme.widget.enabled` property is missing or does not have a value matching the condition.
- The user already provided a bean, causing `@ConditionalOnMissingBean` to back off.
- The configuration was excluded or filtered out by an import filter.
- A resource condition cannot find the required file.

When using `@ConditionalOnResource`, remember to distinguish the condition's resource from descriptor discovery:

~~~java
@AutoConfiguration
@ConditionalOnResource(
        resources = "classpath:widget/widget-defaults.properties"
)
public class WidgetDefaultsAutoConfiguration {
}
~~~

In this example, the imports file may be completely valid and the class is still discovered; however, the condition does not match if `widget/widget-defaults.properties` is not on the classpath. That is a condition resource error, not a missing `AutoConfiguration.imports` error.

## 15. Using the Condition Evaluation Report to Pinpoint the Skipped Step

Run the application with debug enabled:

~~~bash
./gradlew bootRun --args='--debug'
~~~

Or:

~~~bash
java -jar sample-app.jar --debug
~~~

Spring Boot prints the Condition Evaluation Report, showing which auto-configurations matched or did not match and why. For applications running in other environments, appropriate logging can be enabled or the Actuator conditions endpoint can be used if properly configured and secured.

Read the report in sequence:

1. **Auto-configuration name absent from the report:** check the descriptor path, runtime JAR, imports entry, auto-configuration enablement, exclusions, and import filters.
2. **Name present as a negative match:** read the specific condition; check the required classpath, property, bean, or resource.
3. **Configuration matched, but bean method did not create the bean:** check method-level conditions, return type, bean dependencies, and initialization errors.
4. **Bean definition exists, but injection fails:** check qualifiers, `@Primary`, multiple candidates, and the actual exception.

A report lacking the class does not prove the class name is wrong; the resource may not be on the classpath, or the application may be using a different artifact. Combine the report with `jar tf` and `ImportCandidates` to isolate the cause.

## 16. Common Pitfalls and Mistakes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Imports file does not appear in the JAR | Resource placed in wrong directory or excluded by build | Place in `src/main/resources/META-INF/spring` of the module owning the auto-configuration |
| JAR has the file, but candidate is not in the list | Wrong resource name, reading wrong JAR, or different classloader | Verify exact path, runtime dependencies, and `ImportCandidates` |
| Candidate string exists, but class fails to load | FQCN has wrong package/class name or class is missing from runtime classpath | Cross-check source, bytecode path, and dependency graph |
| Class name works in IDE but fails on Linux | Case mismatch | Synchronize exact package and class capitalization |
| Renamed package but forgot to update imports | Descriptor still holds old FQCN | Update the entry in the same refactoring change |
| Nested class not found | Dot used instead of `$` | Use the binary class name with `$`, or make it a top-level class |
| `ApplicationContextRunner` test passes, but starter consumer gets no bean | Test passed class directly via `AutoConfigurations.of(...)` | Add an `ImportCandidates` test and a consumer integration test |
| Tests pass, but packaged application has no bean | Dependency is only in test/compile scope, not runtime | Check `runtimeClasspath`/dependency tree |
| `spring.factories` still has legacy entry | Using Boot 2.x auto-configuration registration | Move FQCN to `AutoConfiguration.imports`; keep other extension points still in use |
| Candidate is in imports, but condition does not match | Dependency/property/bean/resource condition not satisfied | Read Condition Evaluation Report and fix the corresponding input |
| File exists in source, but artifact still contains old content | Build/cache/repository uses an old JAR | Clean build and verify the consumer's actual artifact and version |
| Configuration only works via component scan | Auto-configuration is being loaded through the wrong path | Register via imports; use `@Import` for supporting configurations |

## 17. Ordered Diagnostic Checklist

1. Confirm the application enables `@EnableAutoConfiguration`, typically via `@SpringBootApplication`.
2. Confirm the autoconfigure module has the properly named file under `src/main/resources/META-INF/spring`.
3. Read the file and compare each FQCN against the source package and class name.
4. For nested classes, confirm `$` is used.
5. Clean-compile the autoconfigure module and confirm the `.class` file exists.
6. Build the JAR and use `jar tf` to check the descriptor.
7. Read the descriptor content inside the built JAR.
8. Confirm the starter puts the right autoconfigure JAR on the runtime classpath.
9. Use `ImportCandidates.load(AutoConfiguration.class, classLoader)` to inspect candidates.
10. If the candidate is present, read the Condition Evaluation Report and check exclusions/conditions.
11. Run a consumer integration test that does not import the auto-configuration class directly.
12. Re-check the deployed artifact/version, not only the workspace source.

## 18. Self-Check Questions

1. From which resource does Spring Boot 3.3 read auto-configuration candidates? **`META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.**
2. What does each line in the imports file contain? **The FQCN of an auto-configuration class.**
3. Can a short class name be written? **No; it must include the full package.**
4. Which character starts a comment in the imports file? **`#`.**
5. Which character separates a nested class from its outer class? **`$`.**
6. Where must the imports file reside in a default Maven/Gradle module? **`src/main/resources/META-INF/spring`.**
7. Why is checking the source file alone not enough? **The resource might not be packaged into the JAR, or the JAR might not be on the runtime classpath.**
8. Does a test using `AutoConfigurations.of(MyAutoConfiguration.class)` prove the descriptor is valid? **No; the test passes the class directly.**
9. Which API reads candidates using the exact imports mechanism? **`ImportCandidates.load(AutoConfiguration.class, classLoader)`.**
10. When the candidate is found but the condition does not match, what should you inspect? **The Condition Evaluation Report.**
11. How does `@ConditionalOnResource` differ from descriptor discovery? **It is a condition on an already-discovered class, checking another resource required by the configuration.**
12. Should component scan be used as an alternative to imports? **No; auto-configuration must be published via imports; use `@Import` for supporting configurations.**

## Official References

- [Spring Boot 3.3.13 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): location and content of `AutoConfiguration.imports`, class names, component scanning, conditions, reports, and testing.
- [Spring Boot 3.3.13 — `ImportCandidates` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/annotation/ImportCandidates.html): how candidate lists are loaded from the classpath.
- [Spring Boot 3.3.13 — `@AutoConfiguration` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html): annotation and rules for auto-configuration classes.
- [Spring Boot 3.3.13 — `AutoConfigurationImportSelector` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurationImportSelector.html): selector handling auto-configuration imports.
- [Spring Boot 3.3.13 — `@ConditionalOnResource` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnResource.html): resource condition for auto-configuration.
