# AutoConfiguration.replacements in Supported Versions and Mapping Legacy Class Names

## 1. The problem when changing an auto-configuration package or name

A Spring Boot library may need to move an auto-configuration class to a new package, rename it to reflect its responsibility accurately, or split a large configuration into smaller modules.

For example, the legacy class:

~~~text
com.acme.reports.autoconfigure.ReportsAutoConfiguration
~~~

is moved to:

~~~text
com.acme.reports.autoconfigure.core.ReportsAutoConfiguration
~~~

If you only change the class name and update AutoConfiguration.imports, consuming applications may still reference the old name in many places:

- @AutoConfigureBefore or @AutoConfigureAfter.
- The beforeName or afterName attributes of @AutoConfiguration.
- @SpringBootApplication(exclude = ...) or excludeName.
- @EnableAutoConfiguration(exclude = ...) or excludeName.

These references can reside in the library itself, in other starters, or in consuming application code. Users would have to find and update every old-name reference when upgrading the library.

Starting in Spring Boot **3.4.0-M3**, Spring Boot supports replacing auto-configuration class names using the AutoConfiguration.replacements file. This feature is available in stable Spring Boot 3.4.0 releases and later. It allows Spring Boot to translate certain legacy auto-configuration references to the new class when processing ordering and exclusions.

This lesson uses **Java 17 and Spring Boot 3.4.13** as an illustrative baseline. This is an example of a Boot line that supports the feature; do not apply this syntax to Boot 3.3.x.

## 2. Which versions support AutoConfiguration.replacements?

This is the compatibility boundary to determine before renaming a class:

| Spring Boot version | Supports replacements | How to handle |
| --- | --- | --- |
| Spring Boot 3.3.x and earlier | Mechanism does not exist | Do not rely on a replacements file; keep the old class name or use a separate compatible artifact |
| Spring Boot 3.4.0-M3 | Feature introduced | Can be tested in milestone builds |
| Spring Boot 3.4.0 and later | Supported | Use the replacements file together with AutoConfiguration.imports |
| Newer release lines | Check reference docs of the supported line | Keep consumer tests to verify behavior after upgrading |

The Spring Boot 3.4.0-M3 release notes state clearly that support for deprecating and replacing auto-configuration classes was introduced in this milestone. The 3.4 reference guide describes the file and how to use it. Therefore, if an application still runs Spring Boot 3.3.x, it cannot be expected to understand a replacements file packaged in a JAR.

**Do not check only the library's compile-time version.** Check the actual Spring Boot version that consuming applications resolve at runtime. A JAR built with Boot 3.4 running inside a Boot 3.3 application still lacks Boot 3.4's remapping mechanism.

### 2.1. If the library supports both Boot 3.3 and Boot 3.4

There are two safe options:

1. Keep the legacy FQCN unchanged until Boot 3.3 support ends. Once dropping the older Boot line, move the class and publish the mapping in the artifact targeting Boot 3.4+.
2. Split the artifact or auto-configuration module by supported Boot line. The Boot 3.3 artifact keeps the legacy compatible mechanism/class name; the Boot 3.4+ artifact uses replacements.

Do not ship a migration that works only on Boot 3.4 and document it as compatible with Boot 3.3. On Boot 3.3, exclusions by the old name will not be remapped to the new class.

## 3. Two files that must work together

When replacing an auto-configuration class, Spring Boot uses two separate files.

### 3.1. AutoConfiguration.imports

This file lists the auto-configuration classes currently published in the JAR:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Example after moving:

~~~text
com.acme.reports.autoconfigure.core.ReportsAutoConfiguration
com.acme.reports.autoconfigure.metrics.ReportsMetricsAutoConfiguration
~~~

Each line is a fully qualified class name. After replacement, the imports file must reference only the new class. Do not keep listing the old class as a second candidate.

### 3.2. AutoConfiguration.replacements

Create the file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements
~~~

Contents use the Java Properties format: the old class name on the left of the equals sign, the replacement class name on the right:

~~~properties
com.acme.reports.autoconfigure.ReportsAutoConfiguration=com.acme.reports.autoconfigure.core.ReportsAutoConfiguration
~~~

Both sides are **fully qualified class names**, including package and class name. Do not write bean names, Maven module names, Java file paths, or simple class names alone.

Multiple mappings can be declared in the same file:

~~~properties
com.acme.reports.autoconfigure.ReportsAutoConfiguration=com.acme.reports.autoconfigure.core.ReportsAutoConfiguration
com.acme.reports.autoconfigure.ReportsWebAutoConfiguration=com.acme.reports.autoconfigure.web.ReportsWebAutoConfiguration
com.acme.reports.autoconfigure.ReportsMetricsAutoConfiguration=com.acme.reports.autoconfigure.observability.ReportsMetricsAutoConfiguration
~~~

Each line is an independent old → new pair. If a class changed packages multiple times across releases, map the old names that users might actually reference directly to the final class published by the current artifact. Do not rely on a multi-step alias chain.

### 3.3. Role of each file

| File | Role |
| --- | --- |
| AutoConfiguration.imports | Declares the new classes that Spring Boot can import |
| AutoConfiguration.replacements | Maps old class names to new class names when Spring Boot processes supported references |

The replacements file does not replace imports. Nor does it register the new class automatically if the new class is missing from imports.

## 4. Where does Spring Boot use the mapping?

Spring Boot documentation describes two important reference groups: ordering and exclusions.

### 4.1. Ordering: before and after

Another auto-configuration may need to run after the Reports configuration:

~~~java
@AutoConfiguration(afterName =
        "com.acme.reports.autoconfigure.ReportsAutoConfiguration")
public class ReportsMetricsAutoConfiguration {
}
~~~

This is a reference using the old name. When Spring Boot 3.4+ reads replacement metadata, the name is mapped to:

~~~text
com.acme.reports.autoconfigure.core.ReportsAutoConfiguration
~~~

Related cases include:

- @AutoConfigureBefore.
- @AutoConfigureAfter.
- @AutoConfiguration(beforeName = ...).
- @AutoConfiguration(afterName = ...).

If using Class<?> in before or after, Java code needs the corresponding class to compile. When the old class has been deleted, use beforeName/afterName attributes with string names or keep an appropriate compatibility type.

Ordering only determines the order of applying auto-configurations and registering bean definitions. It does not guarantee bean instances are created in that order; instance creation still depends on dependencies and @DependsOn.

### 4.2. Exclusion: removing the legacy configuration from an application

An application may already exclude the legacy auto-configuration by name:

~~~java
@SpringBootApplication(
        excludeName =
                "com.acme.reports.autoconfigure.ReportsAutoConfiguration"
)
public class Application {
}
~~~

With Spring Boot 3.4+, the mapping in AutoConfiguration.replacements allows the old name to be translated to the new class name when processing exclusions. Thus, the application still excludes the right auto-configuration after the library changes packages.

Related APIs/annotations:

~~~java
@SpringBootApplication(exclude = SomeAutoConfiguration.class)
@SpringBootApplication(excludeName = "com.example.OldAutoConfiguration")
@EnableAutoConfiguration(exclude = SomeAutoConfiguration.class)
@EnableAutoConfiguration(excludeName = "com.example.OldAutoConfiguration")
~~~

If using exclude = OldAutoConfiguration.class, consuming code needs the old class to exist in order to compile. If the old class was completely deleted, excludeName is a string-based reference that does not require importing the old class.

### 4.3. What replacements do not do

This is a class name mapping for Spring Boot's auto-configuration processing, not a general Java class alias.

It does not automatically:

- Create the old class or make importing OldAutoConfiguration compile.
- Make Class.forName("old.FQCN") return the new class.
- Translate arbitrary class name strings in the application to the new name.
- Replace @Import(OldAutoConfiguration.class) in application code.
- Rename beans, qualifiers, bean names, or properties.
- Move components registered via component scanning.
- Redirect an old Maven/Gradle dependency to a new dependency.

If consumers directly use the old class in source code, update the source or keep a separate compatibility class. Do not rely on the replacements file to substitute for every published Java API.

## 5. Complete class relocation example

Suppose the Acme library has this layout before moving:

~~~text
acme-reports-autoconfigure/
└── src/
    └── main/
        ├── java/com/acme/reports/autoconfigure/
        │   └── ReportsAutoConfiguration.java
        └── resources/META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Legacy class:

~~~java
package com.acme.reports.autoconfigure;

import com.acme.reports.ReportClient;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class ReportsAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    ReportClient reportClient() {
        return new ReportClient("https://reports.example.test");
    }
}
~~~

After moving the core auto-configuration to the new package:

~~~text
acme-reports-autoconfigure/
└── src/
    └── main/
        ├── java/com/acme/reports/
        │   ├── ReportClient.java
        │   └── autoconfigure/
        │       ├── core/ReportsAutoConfiguration.java
        │       └── metrics/ReportsMetricsAutoConfiguration.java
        └── resources/META-INF/spring/
            ├── org.springframework.boot.autoconfigure.AutoConfiguration.imports
            └── org.springframework.boot.autoconfigure.AutoConfiguration.replacements
~~~

### 5.1. New class

**src/main/java/com/acme/reports/autoconfigure/core/ReportsAutoConfiguration.java**

~~~java
package com.acme.reports.autoconfigure.core;

import com.acme.reports.ReportClient;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class ReportsAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    ReportClient reportClient() {
        return new ReportClient("https://reports.example.test");
    }
}
~~~

### 5.2. Metrics configuration referencing the old name

**src/main/java/com/acme/reports/autoconfigure/metrics/ReportsMetricsAutoConfiguration.java**

~~~java
package com.acme.reports.autoconfigure.metrics;

import com.acme.reports.ReportClient;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(afterName =
        "com.acme.reports.autoconfigure.ReportsAutoConfiguration")
public class ReportsMetricsAutoConfiguration {

    @Bean
    @ConditionalOnBean(ReportClient.class)
    ReportsMetrics reportsMetrics(ReportClient client) {
        return new ReportsMetrics(client.endpoint());
    }

    public record ReportsMetrics(String endpoint) {
    }
}
~~~

The example keeps the old afterName to demonstrate how the mapping supports existing ordering references. In new code controlled by the library itself, you can also update directly to the new class name for readability.

### 5.3. AutoConfiguration.imports after migration

**src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**

~~~text
com.acme.reports.autoconfigure.core.ReportsAutoConfiguration
com.acme.reports.autoconfigure.metrics.ReportsMetricsAutoConfiguration
~~~

Only the new classes are present. Do not add a line for com.acme.reports.autoconfigure.ReportsAutoConfiguration.

### 5.4. AutoConfiguration.replacements

**src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements**

~~~properties
com.acme.reports.autoconfigure.ReportsAutoConfiguration=com.acme.reports.autoconfigure.core.ReportsAutoConfiguration
~~~

When an application excludes the old name or another auto-configuration declares ordering using the old name, Spring Boot 3.4+ can map it to the new class.

## 6. Preserving compatibility for Java code referencing the old class

The replacements file helps Spring Boot handle class name references in ordering and exclusions. If a library wants to preserve compilation for consumer Java code using OldAutoConfiguration.class, it can consider keeping a public compatibility type in the old package.

Minimal shim example:

~~~java
package com.acme.reports.autoconfigure;

@Deprecated(since = "3.4.0", forRemoval = true)
public final class ReportsAutoConfiguration {

    private ReportsAutoConfiguration() {
    }
}
~~~

This shim only preserves the type name so legacy code can compile during the transition period. It is **not** annotated with @AutoConfiguration, contains no bean methods, and is not listed in AutoConfiguration.imports. The new class is the sole configuration imported by Spring Boot.

Decide separately whether to keep a shim:

- If compatibility is only needed for excludeName or afterName, the mapping works without the old class existing.
- If consumers use OldAutoConfiguration.class, the old class must remain on the compile classpath or consumers must switch to name-based references.
- If consumers use @Import(OldAutoConfiguration.class) or call APIs of the old class directly, replacements cannot substitute for that behavior. Code migration or a compatibility facade with proper implementation is required.
- Do not keep a shim with bean methods or import it as a second auto-configuration, as it can register duplicate beans or create two configuration branches.

Keep a shim only when there is a real source compatibility need and a clear removal plan.

## 7. Sample Maven project to test replacements

The following example tests two key behaviors:

1. Without exclusion: the new class is discovered from AutoConfiguration.imports and registers ReportClient.
2. Application still excludes by old FQCN: Spring Boot 3.4+ maps the exclusion to the new class and does not register ReportClient.

### 7.1. Structure

~~~text
autoconfiguration-replacement-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/acme/reports/
    │   │   ├── ReportClient.java
    │   │   └── autoconfigure/core/
    │   │       └── ReportsAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       ├── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.replacements
    └── test/
        └── java/com/acme/reports/
            └── AutoConfigurationReplacementTests.java
~~~

### 7.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.13</version>
        <relativePath/>
    </parent>

    <groupId>com.acme</groupId>
    <artifactId>autoconfiguration-replacement-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

### 7.3. ReportClient.java

**src/main/java/com/acme/reports/ReportClient.java**

~~~java
package com.acme.reports;

public record ReportClient(String endpoint) {
}
~~~

### 7.4. ReportsAutoConfiguration.java

**src/main/java/com/acme/reports/autoconfigure/core/ReportsAutoConfiguration.java**

~~~java
package com.acme.reports.autoconfigure.core;

import com.acme.reports.ReportClient;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class ReportsAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    ReportClient reportClient() {
        return new ReportClient("https://reports.example.test");
    }
}
~~~

### 7.5. AutoConfiguration.imports

**src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**

~~~text
com.acme.reports.autoconfigure.core.ReportsAutoConfiguration
~~~

### 7.6. AutoConfiguration.replacements

**src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements**

~~~properties
com.acme.reports.autoconfigure.ReportsAutoConfiguration=com.acme.reports.autoconfigure.core.ReportsAutoConfiguration
~~~

### 7.7. AutoConfigurationReplacementTests.java

**src/test/java/com/acme/reports/AutoConfigurationReplacementTests.java**

~~~java
package com.acme.reports;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class AutoConfigurationReplacementTests {

    private static final String OLD_AUTO_CONFIGURATION =
            "com.acme.reports.autoconfigure.ReportsAutoConfiguration";

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner();

    @Test
    void discoversReplacementClassFromImports() {
        runner.withUserConfiguration(ApplicationWithAutoConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportClient.class);
                    assertThat(context.getBean(ReportClient.class).endpoint())
                            .isEqualTo("https://reports.example.test");
                });
    }

    @Test
    void oldExclusionNameExcludesReplacementClass() {
        runner.withUserConfiguration(ApplicationExcludingOldName.class)
                .run(context -> {
                    assertThat(context).doesNotHaveBean(ReportClient.class);
                });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAutoConfiguration
    static class ApplicationWithAutoConfiguration {
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAutoConfiguration(excludeName = OLD_AUTO_CONFIGURATION)
    static class ApplicationExcludingOldName {
    }
}
~~~

The key point in the second test is that OLD_AUTO_CONFIGURATION is merely an FQCN string. The test does not import the old class, and the old class does not need to exist in the project. Spring Boot reads the replacements file, translates the exclusion to the new class, and then excludes that class from the applied auto-configurations.

### 7.8. Running tests and inspecting the JAR

Run:

~~~bash
mvn clean test
~~~

Both tests are expected to pass:

| Test | Result |
| --- | --- |
| No exclusion | Exactly one ReportClient, correct endpoint |
| Exclude by old name | No ReportClient |

After packaging:

~~~bash
mvn clean package
~~~

Inspect the JAR:

~~~bash
jar tf target/autoconfiguration-replacement-demo-1.0.0.jar
~~~

Both resources must be present in the JAR:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements
~~~

Also verify that AutoConfiguration.imports has only the new class and AutoConfiguration.replacements has the exact old → new FQCN pair. Tests in the same module verify resources on the build classpath; also test an independent consumer application with the published/staged JAR if the library is released externally.

## 8. Step-by-step migration roadmap

When an auto-configuration package or name needs to change, follow this sequence:

1. **Determine version support.** Confirm consuming applications use Spring Boot 3.4.0-M3 or stable 3.4.0+.
2. **Choose the new FQCN.** Package and class names should accurately reflect the new responsibility, avoiding unnecessary repeated moves.
3. **Move the implementation.** Move bean methods, conditions, and Java imports to the new class; keep bean behavior unchanged if the migration is only a package change.
4. **Update AutoConfiguration.imports.** Remove the old name, list only the new class.
5. **Add AutoConfiguration.replacements.** Each old class has a direct mapping to the new class.
6. **Review ordering.** Find @AutoConfigureBefore, @AutoConfigureAfter, beforeName, afterName in the library and integration modules.
7. **Review exclusions.** Check examples, documentation, other starters, and consuming code for exclusions using the old name.
8. **Decide on a compatibility shim.** Keep the old type only if source or class literal compatibility is needed.
9. **Write consumer tests.** Verify that old-name exclusions actually exclude the new class in the target Spring Boot version.
10. **Inspect the artifact.** Confirm both resources are packaged with accurate contents in the released JAR.
11. **Update documentation.** Publish the new FQCN, transition timing, minimum version, and how to replace legacy references.
12. **Release according to the compatibility matrix.** Do not include a 3.4+ feature in a release claiming 3.3.x support without a separate compatibility plan.

## 9. Scenarios to watch out for

### 9.1. Changing package while keeping the simple class name

Example:

~~~text
com.acme.old.ReportsAutoConfiguration
    ->
com.acme.new.autoconfigure.ReportsAutoConfiguration
~~~

Even though the simple name did not change, the FQCN changed. The mapping must still specify both the old and new full packages.

### 9.2. Changing both package and class name

~~~text
com.acme.old.ReportsAutoConfiguration
    ->
com.acme.reports.autoconfigure.core.ReportCoreAutoConfiguration
~~~

This is still a single mapping. Legacy references in ordering and exclusions must use the exact old FQCN.

### 9.3. Splitting one auto-configuration into multiple new classes

Suppose the old class contained both core and metrics, and after migration is split into:

~~~text
OldReportsAutoConfiguration
    ->
ReportsCoreAutoConfiguration
ReportsMetricsAutoConfiguration
~~~

A single old → new mapping cannot automatically express splitting one old class into two new classes. AutoConfiguration.replacements maps one old name to one replacement name. Choose a representative class matching the compatibility intent of the old name, while registering additional configurations must be explicitly designed in imports and code.

Do not create multiple lines with the same old key expecting one old exclusion to exclude all new classes automatically. If an old configuration has been split, redesign the exclusion API and guide consumers per feature.

### 9.4. Moving the class to a different JAR module

The replacements file must be present on the runtime classpath that Spring Boot uses to read auto-configurations. If the mapping resides in a module not brought into runtime by the application, Spring Boot cannot read it.

Place the file in the autoconfigure module publishing the new class, package it into the JAR, and verify from a consuming application. Do not leave the file only in a parent module or a build-only module.

### 9.5. Applications still using Spring Boot 3.3.x

Boot 3.3 lacks the replacements mechanism introduced in Boot 3.4. If the new JAR publishes only the new class and a 3.3 consumer still excludes the old name, the old exclusion is not automatically mapped.

In that case:

- Keep the old FQCN in artifacts targeting Boot 3.3.
- Or publish separate artifacts/modules for Boot 3.3 and Boot 3.4+.
- Or postpone the package change until Boot 3.3 support ends.

A shim class can preserve source compatibility, yet it does not make Boot 3.3 understand the replacements file. If runtime behavior is needed on Boot 3.3, ensure the old auto-configuration remains registered using the mechanism supported by that release.

## 10. Common mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Old-name exclusion no longer works | Application runs Boot 3.3 or mapping file is missing from runtime classpath | Check Boot version and the JAR containing replacements |
| New class is not auto-configured | Imports still lists the old class or omits the new class | List only the new class in AutoConfiguration.imports |
| Replacements added but remapping fails | Wrong filename, wrong directory, or wrong FQCN | Use exact path and old FQCN = new FQCN mapping |
| Old exclusion still creates the new bean | Runtime does not read mapping or resolved artifact lacks resource | Inspect the exact JAR resolved by the consumer |
| Java code fails to compile after deleting old class | Consumer references OldClass.class | Keep a compatibility type or switch to excludeName/beforeName |
| @Import(OldClass.class) is not replaced | Outside the remapping scope of replacements | Update imports or write a compatible facade |
| Bean registered twice | Both old and new classes remain listed as two candidates | List only the replacement class |
| Ordering changes unexpectedly | before/after references not audited or mapping is wrong | Check old/new FQCNs and test application order |
| One old class split into multiple new classes | Trying to use one mapping as a one-to-many mechanism | Design new API and per-feature migration guide |
| File sits in a module unused at runtime | Mapping absent from the consumed JAR | Place resource in the published autoconfigure artifact |
| Tests pass in IDE but JAR lacks resource | Resource not packaged or build config excludes file | Run jar tf on the actual artifact |
| Using replacements in an artifact claiming 3.3 support | Feature's version boundary ignored | Keep old class or split artifacts by Boot line |

## 11. Pre-release checklist

### Version and compatibility

- [ ] Confirmed the feature is used only with Spring Boot 3.4.0-M3 or later.
- [ ] Clearly identified the Boot lines the artifact commits to supporting.
- [ ] Plan in place for Boot 3.3.x consumers if this line is still supported.
- [ ] Ensure a release claiming 3.3 support does not depend on remapping introduced in 3.4.

### Metadata and classes

- [ ] File sits at exact path META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements.
- [ ] Mapping uses full FQCNs in the exact order old = new.
- [ ] AutoConfiguration.imports lists only the new class.
- [ ] New class has @AutoConfiguration and necessary conditions.
- [ ] before/after references have been audited.
- [ ] Legacy exclusions have been tested.
- [ ] Compatibility shim (if any) is not imported as a second auto-configuration.

### Testing and release

- [ ] Test without exclusion to confirm the new class is discovered.
- [ ] Test exclusion by old name to confirm the mapping.
- [ ] Test ordering if order between auto-configurations is an important contract.
- [ ] Verify both resources in the final JAR.
- [ ] Test from an independent consumer with the exact target Spring Boot version.
- [ ] Release notes state the new FQCN, minimum version, and consumer guidance.

## 12. Self-check questions

**Question 1.** Starting from which version is AutoConfiguration.replacements supported?  
**Answer:** The feature was introduced in Spring Boot 3.4.0-M3 and is present in stable releases 3.4.0 and later.

**Question 2.** Where does the replacements file live?  
**Answer:** META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements.

**Question 3.** What format does each mapping line have?  
**Answer:** The old fully qualified class name on the left of the equals sign, the replacement class on the right.

**Question 4.** After moving a class, how must AutoConfiguration.imports change?  
**Answer:** List only the replacement class. Do not continue listing the old class as a second candidate.

**Question 5.** Which references does Spring Boot process via replacements?  
**Answer:** Auto-configuration references in before/after ordering and exclusions.

**Question 6.** Does replacements make importing OldAutoConfiguration in Java automatically point to the new class?  
**Answer:** No. This is not a JVM-level or Java-compiler alias. Update source or retain a compatibility type.

**Question 7.** Does a Boot 3.3 application automatically remap old exclusions when a JAR contains a replacements file?  
**Answer:** No. The mechanism was introduced in Boot 3.4.0-M3; Boot 3.3 does not process that mapping.

**Question 8.** Can a single old → new mapping line replace one old class with three new auto-configurations?  
**Answer:** No. A mapping provides one replacement name for one old name. One-to-many requires a separate migration design.

**Question 9.** Should the old class remain in AutoConfiguration.imports after replacement?  
**Answer:** No. Imports lists only the new class; the replacements file handles legacy references within the scope supported by Spring Boot.

**Question 10.** How do you verify the mapping works?  
**Answer:** Use a consumer test with @EnableAutoConfiguration(excludeName = "old-FQCN"), assert the new class's bean does not appear, and then inspect both resources in the released JAR.

## 13. Official references

- [Spring Boot 3.4 — Creating Your Own Auto-configuration, section Deprecating and Replacing Auto-configuration Classes](https://docs.spring.io/spring-boot/3.4/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.4.0-M3 Release Notes — Deprecating and Replacing Auto-configuration Classes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.4.0-M3-Release-Notes)
- [Spring Boot 3.4 Release Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.4-Release-Notes)
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)

**Remember:** AutoConfiguration.replacements is compatibility metadata for Spring Boot, not a Java class alias. From Spring Boot 3.4.0-M3 onward, this file maps old FQCNs to new FQCNs to preserve ordering and exclusion references. When moving a class, update AutoConfiguration.imports to publish only the new class, add the old → new mapping, test exclusion by the old name, and verify the resources are in the JAR. If still supporting Boot 3.3.x, keep a separate compatibility strategy because that line does not process replacements.
