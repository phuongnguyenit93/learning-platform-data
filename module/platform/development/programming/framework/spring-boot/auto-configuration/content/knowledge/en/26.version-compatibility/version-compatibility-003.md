# Spring Boot 2.7 Transition Milestone and Registration Mechanism Changes in Boot 3

> **Objective:** Understand why Spring Boot 2.7 introduced the `AutoConfiguration.imports` resource, why Boot 3 removed auto-configuration registration via the `EnableAutoConfiguration` key in `spring.factories`, and how to maintain a library that runs across multiple Boot generations. The lesson distinguishes supporting only Boot 2.7+/3.x from also having to support Boot 2.6 and lower.

This lesson belongs to the **Version Compatibility** group, taking Spring Boot 2.7 as the transition milestone and Spring Boot 3.0+ as the milestone that removed the legacy registration path. The focus is on registration, the `@AutoConfiguration` annotation, the imports file, other extension keys in `spring.factories`, custom test slices, JAR packaging, and testing strategies across a version matrix.

## 1. Background of the change

Before Spring Boot 2.7, libraries typically registered auto-configuration in the resource:

~~~text
META-INF/spring.factories
~~~

The file uses the properties format. The `org.springframework.boot.autoconfigure.EnableAutoConfiguration` key points to a list of auto-configuration classes, usually a comma-separated list of FQCNs:

~~~properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.acme.audit.autoconfigure.AuditAutoConfiguration,\
com.acme.audit.autoconfigure.AuditWebAutoConfiguration
~~~

This approach worked in Boot 2.x lines before 2.7. However, `spring.factories` is used for many Spring Boot extension points, not just auto-configuration. Listing classes inside one large properties file made finding, merging, and processing metadata for each extension group less explicit.

Spring Boot 2.7 introduced a dedicated resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Each line contains one fully qualified class name (FQCN). This resource separates the auto-configuration list from other extensions and is the recommended registration mechanism from Boot 2.7 onward.

Boot 2.7 still reads the legacy key in `spring.factories` for backward compatibility. Boot 3.0 specifically removed the auto-configuration registration path via that key. This was a change with a clear transition period, not a deletion of all of `spring.factories`.

## 2. Timeline and compatibility matrix

| Spring Boot line | Reads EnableAutoConfiguration key in spring.factories | Reads AutoConfiguration.imports | Recommendation |
| --- | --- | --- | --- |
| 2.0–2.6 | Yes | No | Use spring.factories |
| 2.7.x | Yes, but deprecated | Yes | Migrate to imports; both may be declared |
| 3.0+ | No | Yes | Use imports; drop legacy auto-configuration key |

Two library scenarios must be distinguished:

- **Libraries supporting only Boot 2.7 and higher:** only `AutoConfiguration.imports` is needed. Both Boot 2.7 and Boot 3 read this file.
- **Libraries supporting both Boot 2.6 and lower as well as Boot 3:** maintain both registration paths in the same artifact: `spring.factories` for older Boot and `AutoConfiguration.imports` for newer Boot. Boot 2.7 reads both and deduplicates if the same class is listed in both.

Therefore, the statement “a library supporting Boot 2.x and Boot 3 must have both files” is only true when the Boot 2.x scope includes versions prior to 2.7. If the lowest version is 2.7, the imports file is sufficient for both lines.

### 2.1. What Boot 3 removes

Boot 3 removes support for registering auto-configuration in `spring.factories` using the key:

~~~text
org.springframework.boot.autoconfigure.EnableAutoConfiguration
~~~

Other keys in `spring.factories` are unaffected by this change. A library may still need that file for another extension point that Boot continues to support. Accordingly:

- Do not delete all of `spring.factories` just because auto-configuration was migrated.
- Remove the `EnableAutoConfiguration` entry only when the library no longer needs to support Boot versions prior to 2.7.
- Keep other entries according to the contract of their respective extension points.
- Do not confuse Boot 3 dropping the auto-configuration key with `SpringFactoriesLoader` being completely removed.

## 3. New file structure in Boot 2.7+

Create the resource with the exact name and path:

**`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`**

Contents:

~~~text
com.acme.audit.autoconfigure.AuditAutoConfiguration
com.acme.audit.autoconfigure.AuditWebAutoConfiguration
~~~

Formatting rules:

1. Each line is an auto-configuration FQCN.
2. Do not write short class names or bean names.
3. Do not separate classes with commas.
4. Comments starting with `#` may be added.
5. The path and filename must match every character, including letter case.
6. The file must be placed in main resources and packaged in the JAR used by consuming applications.

Example with comments:

~~~text
# Core audit integration
com.acme.audit.autoconfigure.AuditAutoConfiguration

# Optional servlet integration
com.acme.audit.autoconfigure.AuditWebAutoConfiguration
~~~

Do not place the file directly under `META-INF/` or inside a Java package. The path must include the `META-INF/spring/` directory.

## 4. The @AutoConfiguration annotation introduced in Boot 2.7

Spring Boot 2.7 introduced `@AutoConfiguration` to mark top-level classes that provide auto-configuration:

~~~java
package com.acme.audit.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class AuditAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    public AuditService auditService() {
        return new AuditService();
    }
}
~~~

`@AutoConfiguration` is a dedicated annotation for auto-configuration. It is a specialization of `@Configuration` with `proxyBeanMethods = false`, and is used on top-level classes listed in the imports file.

Nested configurations or configurations imported by an auto-configuration continue using `@Configuration` as usual:

~~~java
@AutoConfiguration
public class AuditAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    static class ServletConfiguration {
        // Servlet-only @Beans.
    }
}
~~~

There is no need to change every `@Configuration` class in a library into `@AutoConfiguration`. The new annotation is intended for classes acting as auto-configuration entry points. Nested configurations and helper configurations continue using `@Configuration`.

### 4.1. Auto-configuration ordering

`@AutoConfiguration` supports declaring order via the `before`, `beforeName`, `after`, and `afterName` attributes. Example:

~~~java
@AutoConfiguration(after = CoreAutoConfiguration.class)
public class AuditAutoConfiguration {
}
~~~

If you do not want a compile-time dependency on a class from another module, you can reference the class name:

~~~java
@AutoConfiguration(
        afterName = "com.acme.core.autoconfigure.CoreAutoConfiguration")
public class AuditAutoConfiguration {
}
~~~

The legacy `@AutoConfigureBefore` and `@AutoConfigureAfter` annotations remain valid choices, especially when a library must share source with older Boot lines. Auto-configuration ordering only affects the order in which bean definitions are registered; bean instance creation order is still determined by the dependency graph and `@DependsOn`.

### 4.2. When can @AutoConfiguration not be used yet?

`@AutoConfiguration` only exists from Boot 2.7 onward. If a library still has to run with Boot 2.6 or earlier, an annotation present only in Boot 2.7 should not be introduced into shared bytecode that an older runtime must load.

There are two approaches:

- Keep classes using `@Configuration(proxyBeanMethods = false)` and ordering annotations that already existed in older Boot lines; register the class via the appropriate file for each version.
- Split artifacts or build variants by baseline if the library wants to use `@AutoConfiguration` and new APIs in builds dedicated to Boot 2.7+/3.x.

For libraries with a minimum baseline of Boot 2.7, using `@AutoConfiguration` is clear and aligned with current conventions.

## 5. Registration patterns by support strategy

Suppose a library has the class:

~~~java
package com.acme.audit.autoconfigure;

import com.acme.audit.AuditService;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class AuditAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    public AuditService auditService() {
        return new AuditService();
    }
}
~~~

This is the variant using `@Configuration` to preserve loadability on older baselines. With a Boot 2.7+ baseline, the annotation on the class can be replaced with `@AutoConfiguration`.

### 5.1. Supporting only Boot 2.6 and lower

Register only in `spring.factories`:

~~~properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.acme.audit.autoconfigure.AuditAutoConfiguration
~~~

There is no imports resource in this strategy because older Boot lines do not read the new resource.

### 5.2. Supporting Boot 2.7 and Boot 3

Only the imports resource is needed:

~~~text
com.acme.audit.autoconfigure.AuditAutoConfiguration
~~~

Boot 2.7 already understands this resource; Boot 3 continues using it. There is no need to keep the legacy entry solely to support Boot 2.7.

### 5.3. Supporting both Boot 2.6 and lower and Boot 3

Maintain both files:

**`META-INF/spring.factories`**

~~~properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.acme.audit.autoconfigure.AuditAutoConfiguration
~~~

**`META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`**

~~~text
com.acme.audit.autoconfigure.AuditAutoConfiguration
~~~

Behavior by version:

- Boot 2.6: reads only the entry in `spring.factories`.
- Boot 2.7: reads both; if a class appears twice, Boot deduplicates it.
- Boot 3: reads imports; the `EnableAutoConfiguration` entry in `spring.factories` is no longer used.

Do not create two different configuration classes just to serve two registration files if the same implementation can run safely on both lines. If APIs/annotations genuinely differ across baselines, use separate build variants or artifacts instead of hiding differences behind duplicate registration.

## 6. Why did Boot 2.7 retain both registration paths?

Boot 2.7 is a transition release. It supports both the old and new mechanisms so libraries can publish a single artifact usable during the upgrade period.

For example, a library lists `AuditAutoConfiguration` in both files. When running on Boot 2.7, both sources are aggregated and duplicate entries are deduplicated. This lets one artifact remain compatible with pre-2.7 Boot and Boot 3 without applying the auto-configuration twice simply because it is registered in two places.

This deduplication is documented Boot 2.7 behavior for identical entries between the two locations. Do not rely on it as a way to handle arbitrary duplicate beans created by two different classes or two different configuration paths.

## 7. Do not accidentally delete other extensions in spring.factories

`spring.factories` can still contain other extension points. Illustrative structure:

~~~properties
# Legacy auto-configuration registration for Boot <= 2.6
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.acme.audit.autoconfigure.AuditAutoConfiguration

# Other Spring Boot extension points may still use spring.factories
com.acme.audit.SomeOtherExtension=\
com.acme.audit.internal.SomeOtherExtensionImpl
~~~

When the library drops pre-2.7 Boot support, the `EnableAutoConfiguration` section can be removed on its own. Keep other keys if they still belong to mechanisms supported in the targeted Boot line.

Do not replace all contents of `spring.factories` with an imports file. The imports file is strictly for listing auto-configurations; it is not a general registration file for every Spring Boot extension.

## 8. Custom test slices also changed registration

Boot 2.7 changed how custom test slices are registered. If a library defines a custom test annotation, the old registration in `spring.factories` must be moved to the resource:

~~~text
META-INF/spring/<fully-qualified-name-of-test-slice-annotation>.imports
~~~

Example annotation:

~~~java
package com.acme.audit.test;

public @interface AcmeDataTest {
}
~~~

Corresponding resource:

**`src/main/resources/META-INF/spring/com.acme.audit.test.AcmeDataTest.imports`**

~~~text
com.acme.audit.autoconfigure.AuditTestAutoConfiguration
com.acme.audit.test.AcmeDataTestImportSelector
~~~

The list above is only a structural example; listed classes must match the test slice contract implemented by the library. The filename is formed from the FQCN of the slice annotation, not the generic `AutoConfiguration.imports` name.

When upgrading a test slice, check separately:

- Legacy entry in `spring.factories`.
- Full annotation name used in the `.imports` filename.
- List of imported test configurations.
- That the test slice actually starts in the target Boot version.

Do not confuse test-slice imports files with the auto-configuration imports file; they share the same line-based format but have different resource names.

## 9. ManagementContextConfiguration has its own resource

Boot 2.7 also moved registration of management context configuration to its own resource:

~~~text
META-INF/spring/org.springframework.boot.actuate.autoconfigure.web.ManagementContextConfiguration.imports
~~~

If a library provides management context configuration for Actuator, inspect this resource separately. Do not list those classes in `AutoConfiguration.imports` just because they also relate to auto-configuration.

For libraries providing only standard auto-configuration, focus solely on `org.springframework.boot.autoconfigure.AutoConfiguration.imports`.

## 10. JAR packaging and resource collision issues

A common mistake appears when a library or application is built as an uber-JAR or shaded JAR. Multiple dependencies can contain a resource named:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

If the packaging tool keeps only one file with the same name instead of appending contents, auto-configuration lists from some dependencies can vanish. The JAR still builds successfully, yet part of the configuration is not discovered.

### 10.1. Maven Shade Plugin

When using `maven-shade-plugin` and imports resources come from multiple dependencies, configure `AppendingTransformer` for the exact resource:

~~~xml
<transformer implementation="org.apache.maven.plugins.shade.resource.AppendingTransformer">
    <resource>META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports</resource>
</transformer>
~~~

If the artifact also contains management context imports, configure a corresponding transformer for that resource:

~~~xml
<transformer implementation="org.apache.maven.plugins.shade.resource.AppendingTransformer">
    <resource>META-INF/spring/org.springframework.boot.actuate.autoconfigure.web.ManagementContextConfiguration.imports</resource>
</transformer>
~~~

### 10.2. Gradle Shadow Plugin

With the Gradle Shadow Plugin, append the contents of the imports files:

~~~groovy
tasks.withType(ShadowJar).configureEach {
    append("META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports")
    append("META-INF/spring/org.springframework.boot.actuate.autoconfigure.web.ManagementContextConfiguration.imports")
}
~~~

This configuration applies when using Shadow to merge dependencies into one JAR. If publishing a normal library JAR without merging dependencies, you do not need to configure append just for a single imports file.

### 10.3. Inspecting the artifact after packaging

List the JAR contents:

~~~bash
jar tf target/acme-audit-autoconfigure-1.0.0.jar
~~~

Check the resources:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
META-INF/spring.factories
~~~

Read the imports file inside the JAR using an appropriate unzip tool:

~~~bash
unzip -p target/acme-audit-autoconfigure-1.0.0.jar META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

For JARs produced by Shade/Shadow, inspect the actual contents of the resource after merging. Merely seeing the filename present does not prove all FQCN lines were retained.

## 11. Testing discovery across a version matrix

Direct tests using `AutoConfigurations.of(AuditAutoConfiguration.class)` only check the behavior of the directly loaded class. They do not prove that the registration file was packaged or that discovery works.

To test registration, use a context with `@EnableAutoConfiguration` and let Boot locate candidates on the classpath itself:

~~~java
package com.acme.audit.autoconfigure;

import com.acme.audit.AuditService;
import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class AuditRegistrationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(DiscoveryApplication.class);

    @Test
    void auditAutoConfigurationIsDiscoveredFromJarResources() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(AuditService.class);
        });
    }

    @SpringBootConfiguration(proxyBeanMethods = false)
    @EnableAutoConfiguration
    static class DiscoveryApplication {
    }
}
~~~

The test above must run in a test module/artifact with the real registration resource on the classpath. It must not load the auto-configuration using `AutoConfigurations.of(...)`, because the goal is to verify discovery.

### 11.1. Matrix to run

| Test runtime | Resources required in artifact | What to verify |
| --- | --- | --- |
| Boot 2.6.x | spring.factories | Discovery via the legacy key |
| Boot 2.7.x | Imports, and spring.factories if still supporting older Boot | Discovery via imports; if both exist, no duplicate registration |
| Boot 3.x | AutoConfiguration.imports | Discovery does not rely on the legacy key |
| Boot 2.7+/3.x custom test slice | Slice-specific .imports | Test slice is found and configured properly |
| Shaded/uber-JAR | Merged imports resource | No entries lost from dependencies |

Use build profiles, test modules, or a CI matrix to run the same discovery test suite on each baseline. Do not compile on just one version and conclude the artifact is compatible with every version.

## 12. Migration steps from Boot 2.6 to Boot 2.7

For a library currently using `spring.factories`:

1. Identify which classes are under the `org.springframework.boot.autoconfigure.EnableAutoConfiguration` key.
2. Create `AutoConfiguration.imports` under `src/main/resources/META-INF/spring/`.
3. Move each FQCN onto its own line, without commas.
4. Use `@AutoConfiguration` on top-level auto-configurations if the minimum baseline is 2.7; if still supporting older Boot, keep a compatible annotation choice.
5. Keep the legacy entry in `spring.factories` if the artifact still has to run on Boot 2.6 or earlier.
6. Run tests on Boot 2.7 to confirm imports work and duplicate entries are handled.
7. Check Shade/Shadow if the library bundles dependencies into a single JAR.

Boot 2.7 still reads the legacy key, but marks loading auto-configurations from `spring.factories` as deprecated. Do not treat this compatibility bridge as a reason to postpone migration indefinitely.

## 13. Migration steps from Boot 2.7 to Boot 3

When upgrading a library or application to Boot 3:

1. Ensure auto-configurations are registered in `AutoConfiguration.imports`.
2. If pre-2.7 Boot is no longer supported, remove specifically the `EnableAutoConfiguration` entry from `spring.factories`.
3. Keep other `spring.factories` keys still needed by extension points.
4. Verify auto-configuration classes use APIs compatible with the Boot 3 baseline.
5. Check ordering classes, exclusions, and package names referenced from other configurations.
6. Confirm the imports resource is present in the final JAR.
7. Run discovery tests against an actual Boot 3 runtime.

### 13.1. Do not confuse the registration change with the entire Boot 3 migration

The `spring.factories` change is only part of upgrading. Spring Boot 3.0 also requires Java 17 or later and Spring Framework 6.0. Jakarta EE APIs moved from the `javax.*` namespace to `jakarta.*`; related dependencies and imports must be upgraded accordingly.

You should upgrade the application to the latest 2.7.x release before moving to Boot 3, audit dependencies not managed by Boot, and address removed deprecated APIs. Changing the imports resource alone does not automatically make an application compatible with Java 17, Spring Framework 6, or the Jakarta namespace.

## 14. Common errors and troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| Boot 3 does not find auto-configuration | Entry only remains in spring.factories under EnableAutoConfiguration | Add the FQCN to AutoConfiguration.imports |
| Boot 2.6 cannot find the class after migration | Only the imports resource was published | Keep the legacy entry in spring.factories if Boot 2.6 is still supported |
| Boot 2.7 logs deprecated configuration | Still relying on spring.factories for auto-configuration | Move to imports; keep legacy entry only when a pre-2.7 baseline is needed |
| Some auto-configurations vanish in uber-JAR | Packaging tool overwrites same-named resources | Use AppendingTransformer or Shadow append |
| spring.factories loses other extensions | Deleted entire file when only one key needed removal | Keep other keys and modify only the relevant entry |
| Test slice is not discovered | Custom slice still registered via legacy path | Create resource META-INF/spring/annotation-FQCN.imports |
| Nested configuration does not behave as expected | Annotated every helper class with @AutoConfiguration | Use this annotation only for top-level entry points; nested configs use @Configuration |
| Boot 3 build passes but Boot 2.6 fails | Bytecode references annotations/APIs introduced in Boot 2.7+ | Keep source/APIs compatible or split artifacts by baseline |
| Imports file exists but class fails to load | Wrong FQCN, class excluded from JAR, or missing dependency | Inspect file contents and artifact classpath |
| Tests pass but consuming application misses configuration | Test uses AutoConfigurations.of(...) to load directly | Add a discovery test using @EnableAutoConfiguration |

## 15. Release checklist for libraries supporting multiple Boot lines

- [ ] Clearly determine the lowest baseline: Boot 2.6, 2.7, or 3.x.
- [ ] If the baseline is 2.7 or higher, register via AutoConfiguration.imports.
- [ ] If still supporting prior to 2.7, also maintain the EnableAutoConfiguration entry in spring.factories.
- [ ] Each imports entry is one FQCN per line.
- [ ] @AutoConfiguration is used only when the runtime baseline is Boot 2.7 or higher.
- [ ] Nested/imported configurations continue using @Configuration.
- [ ] Keep other extension keys in spring.factories.
- [ ] Move custom test slices to their own .imports resource.
- [ ] If management context configuration exists, check its separate resource.
- [ ] Configure resource merging for Maven Shade or Gradle Shadow when creating an uber-JAR.
- [ ] Inspect actual imports contents in the released artifact.
- [ ] Run discovery tests on every Boot line the library commits to supporting.
- [ ] For Boot 3, also review Java 17, Spring Framework 6, and the Jakarta namespace.

## 16. Self-check questions

1. Which version introduced `AutoConfiguration.imports`?  
   **Answer:** Spring Boot 2.7.

2. Does Boot 2.7 still read the `EnableAutoConfiguration` key in `spring.factories`?  
   **Answer:** Yes, for backward compatibility; loading via the legacy mechanism is deprecated.

3. Does Boot 3 still use the `EnableAutoConfiguration` key in `spring.factories`?  
   **Answer:** No. Boot 3 uses the imports file for auto-configuration.

4. Does Boot 3 remove all keys from `spring.factories`?  
   **Answer:** No. This change only removes the auto-configuration registration key; other keys are unaffected by that change.

5. Which files does a library supporting Boot 2.6 and Boot 3 need?  
   **Answer:** Both `spring.factories` and `AutoConfiguration.imports`. Boot 2.7 can read both and deduplicates duplicate entries.

6. Does a library supporting only Boot 2.7 and Boot 3 need two files?  
   **Answer:** No. The imports file is supported by both lines.

7. Which version introduced `@AutoConfiguration`?  
   **Answer:** Spring Boot 2.7. This is a specialized annotation for top-level auto-configurations.

8. Should nested configurations be changed to `@AutoConfiguration`?  
   **Answer:** No. Nested/imported configurations continue using `@Configuration`.

9. Why do shaded JARs need to append imports resources?  
   **Answer:** Multiple dependencies can provide files with the same name; appending preserves entries rather than letting one file overwrite another.

10. Does a test using `AutoConfigurations.of(...)` prove the imports file works?  
    **Answer:** No. Discovery must be tested via `@EnableAutoConfiguration` against the artifact on the classpath.

## Official documentation

- [Spring Boot 2.7 Release Notes — Auto-configuration Registration](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-2.7-Release-Notes): new imports file, backward compatibility, deduplication, `@AutoConfiguration`, custom test slices, and Shade/Shadow.
- [Spring Boot 3.0 Migration Guide — Auto-configuration Files](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide): removal of the `EnableAutoConfiguration` key in `spring.factories` and how to support both Boot 2.x/3.x.
- [Spring Boot 2.7 API — AutoConfiguration](https://docs.spring.io/spring-boot/docs/2.7.1/api/org/springframework/boot/autoconfigure/AutoConfiguration.html): new annotation from 2.7 and ordering attributes.
- [Spring Boot 3.3 API — AutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html): annotation semantics and ordering attributes in the 3.3 line.
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): discovery via imports, package layout, and testing.
- [Spring Boot 3.0 Migration Guide — System Requirements and Jakarta EE](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide): Java 17, Spring Framework 6, and Jakarta namespace migration.

**Remember:** Boot 2.7 is the bridge: it understands both `spring.factories` and `AutoConfiguration.imports`, while deduplicating entries. Boot 3 removes specifically the legacy auto-configuration registration path. Choose the number of files based on the library's lowest baseline, preserve other extension keys, merge resources properly, and test discovery on every supported Boot line.
