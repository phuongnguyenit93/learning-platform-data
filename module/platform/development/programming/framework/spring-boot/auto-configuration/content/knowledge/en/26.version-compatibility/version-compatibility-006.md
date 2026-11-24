# Renaming an Auto-Configuration Class and Its Impact on Exclusions or Ordering Relationships

## Learning objectives

A class annotated with `@AutoConfiguration` typically resides in a shared library and is referenced by many other applications. When changing its package or class name, that change can affect many places outside the library's own source code:

- Spring Boot discovers candidates via the `AutoConfiguration.imports` file.
- Applications can exclude the class via `@SpringBootApplication(exclude = ...)`, `excludeName`, or the `spring.autoconfigure.exclude` property.
- Other auto-configurations can declare relative ordering via `before`, `after`, `beforeName`, `afterName`, `@AutoConfigureBefore`, or `@AutoConfigureAfter`.
- Tests, integration modules, and documentation may store the old fully qualified class name (FQCN).

Therefore, an auto-configuration's FQCN plays a public compatibility role. Spring Boot 3.4 added a replacement metadata mechanism to map old names to new names in exclusions and ordering relationships. This mechanism **does not exist in Spring Boot 3.3**; this is a key version boundary when designing a migration.

After this lesson, you will be able to:

- List the places that reference an auto-configuration's FQCN.
- Predict the impact of package/class renames on imports, exclusions, and ordering.
- Use `AutoConfiguration.replacements` properly on Spring Boot 3.4+.
- Build a compatibility plan if the library still supports Spring Boot 3.3.
- Write tests to verify the new name is discovered, the old name still excludes the configuration, and ordering relationships are preserved.
- Inspect the published JAR rather than checking only the source tree.

## 1. An auto-configuration's FQCN is part of the contract

Suppose the Acme library has the class:

~~~java
package com.acme.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;

@AutoConfiguration
public class AcmeAutoConfiguration {
    // Default beans of the library.
}
~~~

The fully qualified name of the class is:

~~~text
com.acme.autoconfigure.AcmeAutoConfiguration
~~~

Applications usually do not call this class directly. However, Spring Boot and other libraries can store its full name in metadata or annotations.

For example, an application can exclude the auto-configuration by string:

~~~yaml
spring:
  autoconfigure:
    exclude:
      - com.acme.autoconfigure.AcmeAutoConfiguration
~~~

Another library can request to be applied after Acme:

~~~java
@AutoConfiguration(
        afterName = "com.acme.autoconfigure.AcmeAutoConfiguration")
public class AcmeMetricsAutoConfiguration {
}
~~~

If the package is changed to `com.acme.autoconfigure.core`, the new name becomes:

~~~text
com.acme.autoconfigure.core.AcmeAutoConfiguration
~~~

The old name and the new name are two different strings. The compiler cannot find all strings stored in application.yml, resource files, or published artifacts to fix them automatically.

Spring Boot also states explicitly that auto-configuration class names are a public aspect used when applications need to disable configuration. Thus, changing an FQCN should be treated as a compatibility-impacting change, even if the beans inside do not change.

## 2. Places that may contain the old class name

Before renaming, inventory the following references.

| Location | How it is referenced | Consequence if the old name is unhandled |
| --- | --- | --- |
| `AutoConfiguration.imports` | One FQCN per line | Boot cannot find the new candidate if the resource still lists the old name |
| `@SpringBootApplication(exclude = ...)` | Class literal | Source may fail to compile when the old class is deleted |
| `@SpringBootApplication(excludeName = ...)` | FQCN string | Old name no longer points to the new candidate |
| `spring.autoconfigure.exclude` | FQCN string | The new configuration may still be applied |
| `@AutoConfiguration(before/after = ...)` | Class literal | Source referencing the old class may fail to compile |
| `@AutoConfiguration(beforeName/afterName = ...)` | FQCN string | Old ordering edge no longer matches the new name |
| `@AutoConfigureBefore` / `@AutoConfigureAfter` | Class or name | Ordering relationship may be lost |
| `@ImportAutoConfiguration` | Class literal and exclude | Explicit imports/exclusions must be reviewed |
| Tests and integration modules | FQCN in annotations or resources | Tests no longer represent the new behavior |
| Documentation and configuration examples | FQCN as text | Users copy old configuration |

Beyond the places above, search for the class name in:
- Source code of other modules in the same repository.
- Files under `META-INF/spring`.
- Test fixtures and sample applications.
- Build scripts, plugins, or code using `Class.forName`.
- Release notes, migration guides, and API documentation.

Not every string is automatically mapped by Spring Boot. Replacement metadata is designed for auto-configuration names used in **exclusions and before/after ordering**. APIs referencing the class directly, custom reflection, or custom resources still need to be checked against their own contracts.

## 3. Impact on AutoConfiguration.imports

Spring Boot looks for candidates in the file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Each line contains one FQCN. Example before renaming:

~~~text
com.acme.autoconfigure.AcmeAutoConfiguration
com.acme.autoconfigure.AcmeMetricsAutoConfiguration
~~~

After changing AcmeAutoConfiguration's package:

~~~text
com.acme.autoconfigure.core.AcmeAutoConfiguration
com.acme.autoconfigure.AcmeMetricsAutoConfiguration
~~~

The imports file must list the exact current class being published. With Boot 3.4+'s replacement mechanism, this file lists only the **replacement class**; do not keep both the old name and the new name as two independent candidates.

If the source code was renamed while the JAR still contains the old imports file, applications can fail to load the configuration class. If the file lists both names and both classes register beans, duplicate configuration or double condition evaluation can occur.

Auto-configuration is discovered via the imports file, not component scanning. Therefore, changing packages does not mean merely updating the application's scan packages; the artifact's candidate resource must be updated.

## 4. Exclude: why an old name can break the application or fail to exclude configuration

Spring Boot supports multiple ways to disable an auto-configuration.

### 4.1. Excluding by class literal

~~~java
import com.acme.autoconfigure.AcmeAutoConfiguration;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(exclude = AcmeAutoConfiguration.class)
public class BillingApplication {
}
~~~

This is a Java type reference. When changing packages, users must update the import and class literal when recompiling source.

### 4.2. Excluding by class name

~~~java
@SpringBootApplication(
        excludeName = "com.acme.autoconfigure.AcmeAutoConfiguration")
public class BillingApplication {
}
~~~

This is useful when you want to declare the name without importing the class. However, the string is still an FQCN. If the library renames it without providing a compatible mapping, the old string does not automatically turn into the new name.

### 4.3. Excluding by property

~~~yaml
spring:
  autoconfigure:
    exclude:
      - com.acme.autoconfigure.AcmeAutoConfiguration
~~~

The `spring.autoconfigure.exclude` property also stores class names. Different environments may set properties in YAML, properties files, environment variables, or the command line; deployment configurations and charts/deployment templates must be reviewed.

### 4.4. Specific behavior on Spring Boot 3.3

In Spring Boot 3.3, `AutoConfigurationImportSelector` checks the exclude list against the candidates read from `AutoConfiguration.imports`.

If the old name is still a loadable class that is no longer in the candidate list, the old exclusion may be reported as a class that is not an auto-configuration. If the old class was deleted, the old name no longer excludes the new candidate; the application can continue applying the new configuration.

Therefore, when supporting Boot 3.3, you cannot simply add a replacement file and expect the framework to understand the mapping. Boot 3.3 does not yet have that mechanism.

## 5. Ordering: before, after, beforeName, and afterName

An auto-configuration can declare relative order:

~~~java
@AutoConfiguration(after = DataSourceAutoConfiguration.class)
public class AcmeJdbcAutoConfiguration {
}
~~~

Or using names:

~~~java
@AutoConfiguration(
        afterName = "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration")
public class AcmeJdbcAutoConfiguration {
}
~~~

The attributes:

- `before`: apply the current auto-configuration before the specified class.
- `beforeName`: same, referenced by FQCN string.
- `after`: apply the current auto-configuration after the specified class.
- `afterName`: same, referenced by FQCN string.

The separate `@AutoConfigureBefore` and `@AutoConfigureAfter` annotations provide the same kind of ordering relationship. When two auto-configurations do not need direct knowledge of each other's types, the `name` attributes reduce coupling.

### 5.1. When the referenced name is changed

Suppose an external integration has:

~~~java
@AutoConfiguration(
        afterName = "com.acme.autoconfigure.AcmeAutoConfiguration")
public class PartnerMetricsAutoConfiguration {
}
~~~

After Acme moves the class to package `com.acme.autoconfigure.core`, the old name no longer matches the new candidate FQCN. Without a compatible mapping, this ordering relationship may no longer take effect.

If using a class literal:

~~~java
@AutoConfiguration(after = AcmeAutoConfiguration.class)
~~~

the integration's source code must be recompiled against the new type if the old class is no longer provided.

### 5.2. Ordering only sorts bean definitions

Auto-configuration ordering determines the order in which configurations are processed and bean definitions are registered. It **does not determine the instantiation order of every bean instance**.

Bean instances are created according to the dependency graph, constructor/method injection, and relationships like `@DependsOn`. If one bean truly needs another bean, declare the dependency via constructor or `@Bean` method parameters. Do not use `@AutoConfigureAfter` in place of dependency injection.

### 5.3. @AutoConfigureOrder does not replace relative relationships

`@AutoConfigureOrder` sets a general priority order for an auto-configuration. It is useful when adjusting order without creating a direct link between two classes.

However, if the contract requires “after AcmeAutoConfiguration”, an absolute order number does not clearly express that relationship. When renaming, update or map the before/after relationship rather than merely adding an arbitrary order number.

## 6. Spring Boot 3.4+: using AutoConfiguration.replacements

Spring Boot 3.4 added a mechanism to declare replacement auto-configuration classes. This mechanism supports renaming a package or class while preserving handling of old references in exclusions and before/after ordering.

Create the resource:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements
~~~

Contents:

~~~properties
com.acme.autoconfigure.AcmeAutoConfiguration=com.acme.autoconfigure.core.AcmeAutoConfiguration
~~~

Meaning:

- The left side is the old FQCN.
- The right side is the new FQCN.
- Spring Boot uses the mapping to resolve legacy auto-configuration references in the supported cases.

At the same time, update `AutoConfiguration.imports`:

~~~text
com.acme.autoconfigure.core.AcmeAutoConfiguration
com.acme.autoconfigure.AcmeMetricsAutoConfiguration
~~~

Imports lists only the replacement class. The replacements file is name-mapping metadata; it is not a candidate registration file.

### 6.1. Resource structure after renaming

~~~text
src/main/resources/
  META-INF/
    spring/
      org.springframework.boot.autoconfigure.AutoConfiguration.imports
      org.springframework.boot.autoconfigure.AutoConfiguration.replacements
~~~

Contents of both files:

~~~text
# AutoConfiguration.imports
com.acme.autoconfigure.core.AcmeAutoConfiguration
com.acme.autoconfigure.AcmeMetricsAutoConfiguration
~~~

~~~properties
# AutoConfiguration.replacements
com.acme.autoconfigure.AcmeAutoConfiguration=com.acme.autoconfigure.core.AcmeAutoConfiguration
~~~

If multiple classes are renamed, each class has its own mapping:

~~~properties
com.acme.autoconfigure.AcmeAutoConfiguration=com.acme.autoconfigure.core.AcmeAutoConfiguration
com.acme.autoconfigure.AcmeWebAutoConfiguration=com.acme.autoconfigure.web.AcmeWebAutoConfiguration
com.acme.autoconfigure.AcmeMetricsAutoConfiguration=com.acme.autoconfigure.observation.AcmeMetricsAutoConfiguration
~~~

Add only the mappings that are genuinely needed. Do not create mappings for a non-auto-configuration class or for a brand-new class without a predecessor.

### 6.2. What does replacement metadata support?

According to the Spring Boot 3.4 documentation, replacements are used to handle legacy references in:
- `before` / `after` ordering relationships.
- Auto-configuration exclusions.

This allows applications or integration libraries that have not yet updated the name to continue being processed using the replacement name in those cases.

Do not treat this file as a general Java renaming tool. It does not fix source code, import statements, custom reflection strings, bean names, property names, URLs, package scans, or arbitrary strings in the application.

For `@ImportAutoConfiguration` or code referencing the class directly, inspect concrete class references and update them to the API the consumer compiles against. Do not assume replacement metadata replaces all Java references.

### 6.3. Should the old class be kept in AutoConfiguration.imports?

No. With the replacement mechanism, the imports file lists only the new class. If both the old and new classes are registered as two independent candidates, both can participate in processing and create duplicate beans.

If an old Java type must be retained for source compatibility, design that type's role separately. Do not add it back to imports just to preserve the old name for exclusions or ordering; replacement metadata handles the compatibility scope supported by Boot.

## 7. Version boundary: Boot 3.3 and Boot 3.4+

Replacement metadata was introduced in Spring Boot 3.4.0-M3 and is present in Spring Boot 3.4.0 onward.

| Version | Reads AutoConfiguration.replacements? | How old names are handled |
| --- | --- | --- |
| Spring Boot 3.3.x | No | Users must update exclusion/ordering references to the new FQCN; keep FQCN stable if migration cannot be coordinated |
| Spring Boot 3.4+ | Yes | Old → new mapping is used for supported exclusions and before/after ordering |
| Shared artifact for 3.3 and 3.4+ | 3.3 ignores the file, 3.4+ reads it | Mapping protects only consumers on 3.4+; migration docs for 3.3 must still state the change |

### 7.1. If the library still supports Spring Boot 3.3

There are two practical options:

**Option A — Keep the old FQCN in release lines still supporting Boot 3.3.**

If the rename is just an internal package refactor or source reorganization, keep the auto-configuration class in the old package and move implementation details to other classes/helpers. This avoids forcing all 3.3 consumers to update configuration at once.

**Option B — Change the FQCN and publish mandatory migration steps for 3.3 consumers.**

Update:
- `exclude` and `excludeName`.
- `spring.autoconfigure.exclude`.
- `before`, `after`, `beforeName`, `afterName`.
- `@AutoConfigureBefore` and `@AutoConfigureAfter`.
- Tests and modules referencing it directly.

In artifacts supporting Boot 3.4+, add replacement metadata so consumers on 3.4+ remain supported while using the old name in the framework-mapped cases.

Do not advertise that an artifact with a replacements file automatically protects every Boot 3.3 consumer. Boot 3.3 does not read that file.

## 8. Complete migration example

Suppose the library initially has:

~~~text
com.acme.autoconfigure.AcmeAutoConfiguration
~~~

New class:

~~~text
com.acme.autoconfigure.core.AcmeAutoConfiguration
~~~

### 8.1. New class

**File:** `src/main/java/com/acme/autoconfigure/core/AcmeAutoConfiguration.java`

~~~java
package com.acme.autoconfigure.core;

import com.acme.api.AcmeClient;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class AcmeAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(AcmeClient.class)
    AcmeClient acmeClient() {
        return new DefaultAcmeClient();
    }
}
~~~

The example assumes `AcmeClient` and `DefaultAcmeClient` are existing APIs/implementations in the library. Bean content is not the focus of the migration; what needs verification is that the new FQCN is registered and old references are mapped properly.

### 8.2. Imports file

**File:** `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

~~~text
com.acme.autoconfigure.core.AcmeAutoConfiguration
~~~

### 8.3. Replacements file

**File:** `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements`

~~~properties
com.acme.autoconfigure.AcmeAutoConfiguration=com.acme.autoconfigure.core.AcmeAutoConfiguration
~~~

### 8.4. External integration ordering

A previously compiled integration may still declare the old name:

~~~java
package example.partner;

import org.springframework.boot.autoconfigure.AutoConfiguration;

@AutoConfiguration(
        afterName = "com.acme.autoconfigure.AcmeAutoConfiguration")
public class PartnerMetricsAutoConfiguration {
}
~~~

On Spring Boot 3.4+, replacement metadata lets Boot associate the old name with the new class when processing ordering. When a new version of the integration can be released, it is still advisable to update the source to the new name for readability and to avoid long-term reliance on compatibility mappings.

## 9. Testing the migration with ApplicationContextRunner

At least three contracts must be tested:

1. The new candidate is discovered via the imports file.
2. Exclusion using the old name still excludes the new candidate on Boot 3.4+.
3. Ordering relationships referencing the old name are still resolved on Boot 3.4+.

The following example is for **Spring Boot 3.4+** because it tests replacement metadata.

### 9.1. New auto-configuration providing a marker bean

~~~java
package com.acme.autoconfigure.core;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class AcmeAutoConfiguration {

    @Bean
    public AcmeMarker acmeMarker() {
        return new AcmeMarker();
    }
}
~~~

~~~java
package com.acme.autoconfigure.core;

public class AcmeMarker {
}
~~~

### 9.2. Downstream configuration still referencing the old name

**Test file:** `src/test/java/example/consumer/AardvarkDownstreamAutoConfiguration.java`

~~~java
package example.consumer;

import com.acme.autoconfigure.core.AcmeMarker;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(
        afterName = "com.acme.autoconfigure.AcmeAutoConfiguration")
public class AardvarkDownstreamAutoConfiguration {

    @Bean
    @ConditionalOnBean(AcmeMarker.class)
    public DownstreamFeature downstreamFeature() {
        return new DownstreamFeature();
    }
}
~~~

~~~java
package example.consumer;

public class DownstreamFeature {
}
~~~

Add the downstream test configuration to the test candidate list using the resource:

**File:** `src/test/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

~~~text
example.consumer.AardvarkDownstreamAutoConfiguration
~~~

The name `AardvarkDownstreamAutoConfiguration` is chosen to make the `afterName` ordering edge observable: when the ordering edge is not recognized, it can be sorted before the Acme class alphabetically. When the replacement is recognized, it is applied after Acme.

### 9.3. JUnit 5 verifying exclusion and ordering

**File:** `src/test/java/example/consumer/AutoConfigurationReplacementTests.java`

~~~java
package example.consumer;

import com.acme.autoconfigure.core.AcmeMarker;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class AutoConfigurationReplacementTests {

    private static final String OLD_CLASS =
            "com.acme.autoconfigure.AcmeAutoConfiguration";

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner();

    @Test
    void newCandidateIsDiscoveredAndDownstreamOrderingIsPreserved() {
        this.runner
                .withUserConfiguration(EnabledApplication.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(AcmeMarker.class);
                    assertThat(context).hasSingleBean(DownstreamFeature.class);
                });
    }

    @Test
    void exclusionUsingOldNameExcludesTheReplacement() {
        this.runner
                .withUserConfiguration(ExcludingApplication.class)
                .run(context -> {
                    assertThat(context).doesNotHaveBean(AcmeMarker.class);
                    assertThat(context).doesNotHaveBean(DownstreamFeature.class);
                });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAutoConfiguration
    static class EnabledApplication {
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAutoConfiguration(excludeName = OLD_CLASS)
    static class ExcludingApplication {
    }
}
~~~

This test relies on the resources in the main/test classpath:

- Main `AutoConfiguration.imports` lists the new AcmeAutoConfiguration.
- Main `AutoConfiguration.replacements` maps the old FQCN to the new FQCN.
- Test `AutoConfiguration.imports` adds the downstream candidate.
- The downstream candidate still references the old name via `afterName`.

**Expected results on Boot 3.4+:**
- The first test has both `AcmeMarker` and `DownstreamFeature`; this confirms the new candidate was discovered and the legacy ordering relationship was mapped.
- The second test has no `AcmeMarker`; the old name in `excludeName` excluded the replacement class. Because the downstream bean requires `AcmeMarker`, `DownstreamFeature` does not appear either.

This is an integration test for auto-configuration discovery, exclusion, and ordering. It does not merely call `AutoConfigurations.of(NewClass.class)` directly, because calling it directly skips reading candidate/replacement metadata via `@EnableAutoConfiguration`.

### 9.4. Dependencies and run commands

Requires Java 17+, Spring Boot 3.4+, and JUnit 5. In a Gradle module whose Spring Boot version is managed by the plugin or BOM:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Run:

~~~bash
# Linux/macOS
./gradlew test --tests "example.consumer.AutoConfigurationReplacementTests"

# Windows
gradlew.bat test --tests "example.consumer.AutoConfigurationReplacementTests"
~~~

**Expected result:** both tests PASS. The test example is designed for Boot 3.4+; if run with Boot 3.3, replacement metadata is not processed and the old-name compatibility tests cannot be expected to pass.

## 10. Inspecting the JAR after building

Testing the source is insufficient if resources are missing from the artifact. After building the autoconfigure module:

~~~bash
jar tf build/libs/acme-spring-boot-autoconfigure-1.2.0.jar
~~~

Verify both resources exist:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements
~~~

Inspect the imports file and confirm only the new name is present:

~~~text
com.acme.autoconfigure.core.AcmeAutoConfiguration
~~~

Inspect the replacements file and confirm the mapping:

~~~properties
com.acme.autoconfigure.AcmeAutoConfiguration=com.acme.autoconfigure.core.AcmeAutoConfiguration
~~~

If the module uses `spring-boot-autoconfigure-processor`, rebuild so generated metadata reflects the new class. Do not hand-edit metadata files generated by annotation processors; update source/annotations and rebuild.

A useful CI check is extracting the JAR and comparing the resources against expected values. This catches cases where the source is right yet the released artifact still packages old imports or replacements.

## 11. Safe migration plan

Follow this sequence:

1. **Confirm the reason for renaming.** If you only want to reorganize internal packages, consider keeping the FQCN and moving the implementation to helpers/delegates.
2. **Find all old references.** Search for the FQCN in sources, resources, tests, sample apps, YAML, deployment charts, and documentation.
3. **Choose the supported Spring Boot range.** Determine whether 3.3 must still be supported or only 3.4+.
4. **Create the new class.** Keep behavior, conditions, and bean contracts unchanged during the rename if possible.
5. **Update AutoConfiguration.imports.** List only the new class.
6. **Add AutoConfiguration.replacements if supporting 3.4+.** Map the old FQCN to the new FQCN.
7. **Update internal ordering.** Update `before`, `after`, `beforeName`, `afterName`, and ordering annotations owned by the library itself.
8. **Handle 3.3 consumers.** Update the migration guide so users update exclusion/ordering references, or keep the old FQCN in release branches still supporting 3.3.
9. **Test both directions.** Verify default discovery, exclusion using the old name, ordering using the old name, and configuration after updating to the new name.
10. **Inspect the JAR.** Verify imports, replacements, and generated metadata.
11. **Publish migration notes.** State the old FQCN, new FQCN, versions supporting replacements, and dedicated steps for Boot 3.3.

Avoid combining a class rename with changes to bean behavior, property defaults, or dependency graphs unless necessary. Separating changes helps isolate whether a failure comes from the rename or from new behavior.

## 12. Common mistakes

1. **Renaming only the Java file.** The package/FQCN in source and the imports file may still be old; inspect all resources.
2. **Forgetting AutoConfiguration.imports.** Boot cannot find the new class or tries to load the old class.
3. **Keeping both old and new names in imports when using replacements.** Both candidates may be processed and create duplicate configuration.
4. **Writing the replacement mapping backward.** The left side must be the old FQCN and the right side must be the replacement FQCN.
5. **Misnaming the resource.** The filename must be exact: `org.springframework.boot.autoconfigure.AutoConfiguration.replacements` under `META-INF/spring`.
6. **Assuming Boot 3.3 reads the replacements file.** The feature was introduced in Boot 3.4; Boot 3.3 requires separate migration.
7. **Forgetting the spring.autoconfigure.exclude property.** Exclusions may live in environment configurations rather than appearing in repository source.
8. **Updating only exclude while forgetting ordering.** `afterName` or `beforeName` in another library may still point to the old name.
9. **Using @AutoConfigureOrder to fix all legacy relationships.** Absolute ordering does not fully replace a before/after relationship.
10. **Thinking replacement metadata rewrites every string.** It only supports the auto-configuration references defined by Boot; reflection, direct imports, and custom strings must be updated separately.
11. **Not checking source compatibility.** Consumers recompiling against the old class literal will fail to find the old type.
12. **Testing with AutoConfigurations.of and concluding replacements work.** That approach loads classes directly and does not test selector/imports/replacements like `@EnableAutoConfiguration`.
13. **Testing only on the JVM without testing the artifact.** The JAR can miss resources even when tests pass in the IDE.
14. **Confusing ordering with bean creation.** Auto-configuration order controls bean definition processing; dependency injection expresses bean usage dependencies.
15. **Not documenting version limits.** Boot 3.3 users may assume old mappings are protected while the framework does not read that resource.

## 13. Pre-release checklist

### Naming and registration

- [ ] New FQCN finalized.
- [ ] `AutoConfiguration.imports` lists only the new class.
- [ ] No other resource still registers the old class unintentionally.
- [ ] Generated auto-configuration metadata regenerated.

### Exclusions and ordering

- [ ] Searched for `exclude`, `excludeName`, and `spring.autoconfigure.exclude`.
- [ ] Searched for `before`, `after`, `beforeName`, `afterName`.
- [ ] Checked `@AutoConfigureBefore` and `@AutoConfigureAfter`.
- [ ] Reviewed `@ImportAutoConfiguration` and direct class references.
- [ ] Replacement mapping is in old → new direction if using Boot 3.4+.

### Compatibility and tests

- [ ] Supported Spring Boot range clearly documented.
- [ ] Migration instructions for Boot 3.3 published if this version is still supported.
- [ ] Discovery test for the new class.
- [ ] Exclusion test using the old name on Boot 3.4+.
- [ ] Ordering test referencing the old name on Boot 3.4+.
- [ ] Exclusion/ordering test with the new name.
- [ ] Published JAR contains accurate imports and replacements.
- [ ] Migration notes list consumer configurations that must be updated.

## 14. Self-check questions

**Question 1.** Changing `AcmeAutoConfiguration`'s package can affect which locations?

**Answer:** The imports file, exclusions, before/after ordering, class references in source, tests, resources, sample apps, and documentation.

**Question 2.** Which file maps an old auto-configuration name to a new one on Spring Boot 3.4+?

**Answer:** `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements`, with each line in the form `old.FQCN=new.FQCN`.

**Question 3.** After adding a replacement mapping, should the imports file contain both names?

**Answer:** No. The imports file lists only the replacement class; the replacements file stores the compatibility mapping.

**Question 4.** Does Spring Boot 3.3 use replacement metadata?

**Answer:** No. The feature was introduced in Spring Boot 3.4.0; 3.3 consumers must update legacy references or keep the FQCN stable.

**Question 5.** What does `@AutoConfiguration(afterName = "...")` control?

**Answer:** It requests that the current auto-configuration be applied after the class with the specified FQCN. It affects bean definition processing order, not the instantiation order of every bean instance.

**Question 6.** Which test verifies that replacement metadata is actually used by Spring Boot?

**Answer:** An integration test running via `@EnableAutoConfiguration` that keeps an exclusion/ordering referencing the old name and asserts the new class is excluded or the ordering relationship still applies. Loading directly via `AutoConfigurations.of` is insufficient to test the replacement mechanism.

## 15. Takeaways

An auto-configuration's FQCN is part of the compatibility contract because applications and other libraries can use that name to disable or order auto-configurations. When renaming, update the imports file and audit exclusions and ordering references.

With Spring Boot 3.4+, use `AutoConfiguration.replacements` to map old names to new names for exclusions and before/after ordering; the imports file lists only the new class. With Spring Boot 3.3, replacement metadata is not supported, so consumer references must be updated or the old FQCN retained across compatible release lines.

Finally, test via `@EnableAutoConfiguration` and inspect the released JAR. A rename is complete only when the new class is discovered, compatibility references behave according to the Boot version, and no unintended legacy resources remain.

### Official Spring Boot documentation

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 — AutoConfiguration Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html)
- [Spring Boot 3.3 — AutoConfigurationImportSelector Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurationImportSelector.html)
- [Spring Boot 3.4 — Deprecating and Replacing Auto-configuration Classes](https://docs.spring.io/spring-boot/3.4/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.deprecating)
- [Spring Boot 3.4.0-M3 Release Notes — Auto-configuration replacements](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.4.0-M3-Release-Notes)
