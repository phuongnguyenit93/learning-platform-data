# New Condition Annotations and How to Verify the First Supported Version

## 1. Why verify versions before using an annotation?

Spring Boot adds condition annotations across release lines. Seeing an annotation in the latest documentation does not mean it exists in every Boot version an application or library supports.

For example, `@ConditionalOnBooleanProperty` was introduced in Spring Boot 3.5.0. A library that still commits to Boot 3.3 compatibility cannot import this annotation and expect a 3.3 project to compile. Conversely, `@ConditionalOnThreading` has existed since Boot 3.2.0 and can therefore be used in 3.2, 3.3, 3.4, and 3.5 projects.

When evaluating a new annotation, answer four questions:

1. **In which version did the annotation appear?** Check the Javadoc for the exact release line and its `Since` entry.
2. **Which version does the application actually resolve?** Inspect the Maven/Gradle dependency graph and BOM.
3. **Is only the API new, or did semantics change as well?** Read release notes and migration notes.
4. **Does the lowest version the library commits to supporting have that API?** Compile and run tests against that exact baseline.

This lesson focuses on Spring Boot 3.x, with a Boot 3.3.13 compatibility example and a test project using Boot 3.5.0, Java 17+. Version milestones are verified against versioned Javadoc and official release notes.

## 2. Version milestone table for selected condition annotations

Not all annotations in the table are new. Older annotations are included as comparison baselines and to demonstrate how to read `Since`.

| Annotation | First version | Meaning | Compatibility notes |
| --- | --- | --- | --- |
| `@ConditionalOnProperty` | 1.1.0 | Checks property values in the Environment | Present in Boot 3.3 |
| `@ConditionalOnWarDeployment` | 2.3.0 | Matches only when running a traditional WAR in a Servlet container | Present in Boot 3.3 |
| `@ConditionalOnThreading` | 3.2.0 | Checks platform/virtual threading mode | Available since Boot 3.2 |
| `Threading` | 3.2.0 | `PLATFORM` and `VIRTUAL` enum used with the threading condition | Available since Boot 3.2 |
| `@ConditionalOnBooleanProperty` | 3.5.0 | Condition dedicated to boolean properties | Absent in Boot 3.3/3.4 |
| `@ConditionalOnBooleanProperties` | 3.5.0 | Container annotation for multiple `@ConditionalOnBooleanProperty` | Available since Boot 3.5 |
| `@ConditionalOnProperties` | 3.5.0 | Container annotation for multiple `@ConditionalOnProperty` | Available since Boot 3.5 |

The versioned Javadoc of `@ConditionalOnBooleanProperty` explicitly states `Since: 3.5.0`. The Javadoc of `@ConditionalOnThreading` and enum `Threading` states `Since: 3.2.0`. These are public API milestones; release notes of each line confirm the context of the change.

Two notable milestones:

- **Boot 3.2.0:** introduced `@ConditionalOnThreading` to configure based on platform threads or virtual threads.
- **Boot 3.5.0:** introduced `@ConditionalOnBooleanProperty`; simultaneously, `@ConditionalOnProperty` and `@ConditionalOnBooleanProperty` became repeatable annotations.

Therefore, if a library has a Boot 3.3 baseline, it can use `@ConditionalOnThreading` but cannot yet use `@ConditionalOnBooleanProperty`.

## 3. @ConditionalOnBooleanProperty — new annotation from Boot 3.5.0

### 3.1. The problem this annotation solves

`@ConditionalOnProperty` has existed for a long time and can check boolean properties by setting `havingValue = "true"`. However, its default has a general meaning: the property must be present and the value must not be the string `false`. Consequently, for a boolean-typed property, the default form can let another string such as `yes` or `enabled` still count as a match.

Example:

```java
@Bean
@ConditionalOnProperty(prefix = "acme.audit", name = "enabled")
AuditClient auditClient() {
    return new AuditClient();
}
```

With `havingValue` left empty, the condition matches by default whenever the property is present and different from `false`. This is useful behavior for certain string-valued properties, yet it does not clearly express that the key must be boolean.

`@ConditionalOnBooleanProperty` was added in Boot 3.5.0 to express that intent directly.

### 3.2. Syntax and default values

```java
@Bean
@ConditionalOnBooleanProperty(
        prefix = "acme.audit",
        name = "enabled")
AuditClient auditClient() {
    return new AuditClient();
}
```

Key attributes:

| Attribute | Type | Default | Meaning |
| --- | --- | --- | --- |
| `prefix` | `String` | `""` | Prefix applied to properties |
| `name` / `value` | `String[]` | empty | Property names to check |
| `havingValue` | `boolean` | `true` | Expected boolean value |
| `matchIfMissing` | `boolean` | `false` | Whether to match if the property is not declared |

With the example above:

| Value of `acme.audit.enabled` | Result |
| --- | --- |
| `true` | Match |
| `false` | No-match |
| Undeclared | No-match |
| Invalid non-boolean value | Does not satisfy the boolean condition; validate input values per the application contract |

To enable the bean when the property is false:

```java
@Bean
@ConditionalOnBooleanProperty(
        prefix = "acme.audit",
        name = "enabled",
        havingValue = false)
DisabledAuditMarker disabledAuditMarker() {
    return new DisabledAuditMarker();
}
```

To also treat a missing property as false:

```java
@Bean
@ConditionalOnBooleanProperty(
        prefix = "acme.audit",
        name = "enabled",
        havingValue = false,
        matchIfMissing = true)
DisabledAuditMarker disabledAuditMarker() {
    return new DisabledAuditMarker();
}
```

Read both `havingValue` and `matchIfMissing` carefully. An absent property is a distinct state, not synonymous with a property being present and having the value false.

### 3.3. Comparison with @ConditionalOnProperty

| Usage | Default condition |
| --- | --- |
| `@ConditionalOnProperty(prefix="acme.audit", name="enabled")` | Property is present and not equal to the string `false` |
| `@ConditionalOnProperty(prefix="acme.audit", name="enabled", havingValue="true")` | Property is present and equal to the string `true` |
| `@ConditionalOnBooleanProperty(prefix="acme.audit", name="enabled")` | Property is present and has boolean value `true` |

When Boot 3.3 compatibility is required, the explicit form is:

```java
@Bean
@ConditionalOnProperty(
        prefix = "acme.audit",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false)
AuditClient auditClient() {
    return new AuditClient();
}
```

This form works prior to Boot 3.5 and clearly expresses that only the value `true` enables the bean. There is no need to raise the baseline to 3.5 just to swap one annotation when `@ConditionalOnProperty` already satisfies the contract.

### 3.4. Repeatable from Boot 3.5.0

In Boot 3.5.0, `@ConditionalOnBooleanProperty` can appear multiple times on the same class or method:

```java
@Bean
@ConditionalOnBooleanProperty(
        prefix = "acme",
        name = "audit-enabled")
@ConditionalOnBooleanProperty(
        prefix = "acme",
        name = "metrics-enabled")
CombinedMonitoring combinedMonitoring() {
    return new CombinedMonitoring();
}
```

The conditions are aggregated by `@ConditionalOnBooleanProperties`. In the example, the bean matches only when both properties satisfy their conditions.

With Boot 3.3, `@ConditionalOnProperty` cannot be repeated directly because the annotation was not repeatable in that version. Use a single annotation with multiple names:

```java
@Bean
@ConditionalOnProperty(
        prefix = "acme",
        name = {"audit-enabled", "metrics-enabled"},
        havingValue = "true")
CombinedMonitoring combinedMonitoring() {
    return new CombinedMonitoring();
}
```

When declaring multiple names in the `name` attribute, all properties must match. This approach is well compatible with older versions.

## 4. @ConditionalOnThreading — available since Boot 3.2.0

### 4.1. Purpose

`@ConditionalOnThreading` enables configuring beans based on the active threading mode. It is useful when an integration needs to select a dedicated executor, scheduler, or adapter for platform threads versus virtual threads.

The annotation resides in package:

```java
org.springframework.boot.autoconfigure.condition.ConditionalOnThreading
```

Enum `Threading` resides in package:

```java
org.springframework.boot.autoconfigure.thread.Threading
```

The enum has two values:

- `Threading.PLATFORM`: platform threads; active when virtual threads are inactive.
- `Threading.VIRTUAL`: virtual threads; active when `spring.threads.virtual.enabled=true` and the application runs on Java 21 or later.

### 4.2. Example selecting beans by threading mode

```java
@Bean
@ConditionalOnThreading(Threading.VIRTUAL)
TaskExecutionStrategy virtualTaskExecutionStrategy() {
    return new VirtualTaskExecutionStrategy();
}

@Bean
@ConditionalOnThreading(Threading.PLATFORM)
TaskExecutionStrategy platformTaskExecutionStrategy() {
    return new PlatformTaskExecutionStrategy();
}
```

The example illustrates two implementations both implementing `TaskExecutionStrategy`. Only the bean matching the current threading mode is registered.

To enable virtual threads in a Boot 3.2+ application:

```properties
spring.threads.virtual.enabled=true
```

The virtual condition requires Java 21+. If the application runs Java 17 or the property is not enabled, `Threading.VIRTUAL` is inactive and `Threading.PLATFORM` is the matching choice.

### 4.3. Connection to supported versions

`@ConditionalOnThreading` and enum `Threading` both have Javadoc `Since: 3.2.0`. The Boot 3.2 release notes also state that this new annotation was added to support virtual threads-related concerns.

If a library must support Boot 3.1 and lower, importing `@ConditionalOnThreading` will fail to compile. Use a condition compatible with the older baseline or split implementations by version. You cannot merely change the Java version and expect a Boot 3.2 annotation to appear in Boot 3.1.

## 5. How to verify the first version supporting an annotation

Do not rely on a single latest documentation page or IDE autocomplete results. Use multiple independent pieces of evidence.

### 5.1. Step 1 — open the versioned Javadoc

Look up the annotation in Javadoc with an explicit version, for example:

- Boot 3.3: `https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html`
- Boot 3.5: `https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBooleanProperty.html`
- Boot 3.2: `https://docs.spring.io/spring-boot/docs/3.2.0/api/org/springframework/boot/autoconfigure/condition/ConditionalOnThreading.html`

On the Javadoc page, look for the `Since` entry. Examples:

| Javadoc | Since value |
| --- | --- |
| `ConditionalOnProperty` | 1.1.0 |
| `ConditionalOnThreading` | 3.2.0 |
| `ConditionalOnBooleanProperty` | 3.5.0 |

Do not open `https://docs.spring.io/spring-boot/api` without a version in the URL and assume the annotation exists in the version you are using. That page usually points to the current API.

### 5.2. Step 2 — cross-reference release notes

Javadoc shows the `Since` milestone; release notes explain what problem the annotation was added to solve and what other related changes occurred.

Milestones to read:

- Spring Boot 3.2 Release Notes: introduction of `@ConditionalOnThreading`.
- Spring Boot 3.5 Release Notes: introduction of `@ConditionalOnBooleanProperty`.
- Spring Boot 3.5 Release Notes: `@ConditionalOnProperty` and `@ConditionalOnBooleanProperty` becoming repeatable.
- Spring Boot 3.4 Release Notes: change in one case of evaluating `@ConditionalOnBean`/`@ConditionalOnMissingBean` on `@Bean` methods when using the `annotation` attribute.

Release notes help avoid confusing a “new annotation” with an “old annotation whose behavior changed”.

### 5.3. Step 3 — inspect the actual artifact

The annotation belongs to the `spring-boot-autoconfigure` artifact. You can inspect the JAR downloaded by Maven.

Linux/macOS:

```bash
jar tf ~/.m2/repository/org/springframework/boot/spring-boot-autoconfigure/3.3.13/spring-boot-autoconfigure-3.3.13.jar | grep ConditionalOnBooleanProperty.class
```

With the Boot 3.3.13 JAR, the command above returns no `ConditionalOnBooleanProperty` class.

Check Boot 3.5.0:

```bash
jar tf ~/.m2/repository/org/springframework/boot/spring-boot-autoconfigure/3.5.0/spring-boot-autoconfigure-3.5.0.jar | grep ConditionalOnBooleanProperty.class
```

The output must contain:

```text
org/springframework/boot/autoconfigure/condition/ConditionalOnBooleanProperty.class
```

You can use `javap` to inspect the class and API signature:

```bash
javap -classpath ~/.m2/repository/org/springframework/boot/spring-boot-autoconfigure/3.5.0/spring-boot-autoconfigure-3.5.0.jar org.springframework.boot.autoconfigure.condition.ConditionalOnBooleanProperty
```

On Windows PowerShell:

```powershell
$jarPath = Join-Path $env:USERPROFILE ".m2\repository\org\springframework\boot\spring-boot-autoconfigure\3.5.0\spring-boot-autoconfigure-3.5.0.jar"
jar tf $jarPath | Select-String "ConditionalOnBooleanProperty.class"
javap -classpath $jarPath org.springframework.boot.autoconfigure.condition.ConditionalOnBooleanProperty
```

If the class is absent from the resolved JAR, code importing the annotation will fail to compile, even if the IDE happens to display Javadoc from a different version.

### 5.4. Step 4 — inspect the resolved dependency version

Maven:

```bash
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-autoconfigure
```

Gradle:

```bash
./gradlew dependencyInsight --dependency spring-boot-autoconfigure --configuration compileClasspath
```

Results to verify:

- The actual version of `spring-boot-autoconfigure`.
- Which dependency pulls that version in.
- Whether there are version overrides or conflicts.
- Whether the version aligns with `spring-boot`, `spring-boot-test`, and the Boot plugin.

Do not infer the library version from the Gradle/Maven plugin version. The build plugin and libraries on the compile/runtime classpath are two separate components.

### 5.5. Step 5 — compile against the lowest version the library supports

Suppose the library declares support for Boot 3.3.13 and later. Create a CI matrix:

| Build | Boot BOM/parent | Permitted source usage |
| --- | --- | --- |
| Compatibility baseline | 3.3.13 | `@ConditionalOnProperty`, `@ConditionalOnThreading` |
| New feature baseline | 3.5.0 | May use `@ConditionalOnBooleanProperty` and repeatable conditions |

If source imports `@ConditionalOnBooleanProperty` while building with Boot 3.3.13, the compiler reports symbol not found. This is a genuine compatibility error, not a runtime condition failure.

For libraries, the supported baseline must be reflected in CI and release documentation. For applications, the version selected by the application's BOM must provide all APIs imported by the source.

## 6. Compatibility strategies when an annotation exists only in a newer version

### 6.1. Keep the old baseline: use the legacy API with matching semantics

If the library needs to support Boot 3.3, use:

```java
@Bean
@ConditionalOnProperty(
        prefix = "acme.audit",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false)
AuditClient auditClient() {
    return new AuditClient();
}
```

Do not import `@ConditionalOnBooleanProperty` into the shared module. This keeps the source compatible with Boot 3.3 while still checking boolean true explicitly.

### 6.2. Raise the minimum supported version

If you want to use the new annotation, update the minimum supported version to Boot 3.5.0:

- Upgrade the BOM/parent in the project.
- Verify the dependency graph does not mix Spring Boot artifacts of different versions.
- Run unit/integration tests.
- Update the library's documentation and release notes.
- Verify consuming applications actually use Boot 3.5+.

Do not raise the version of `spring-boot-autoconfigure` alone. Upgrade synchronously via the Boot BOM to avoid mixing incompatible components.

### 6.3. Split modules by Boot line when two baselines are needed

If the product must support Boot 3.3 and wants to use new APIs on Boot 3.5, modules can be split:

```text
acme-feature-core/
acme-feature-spring-boot-33/
acme-feature-spring-boot-35/
```

The Boot 3.3 module uses `@ConditionalOnProperty`; the Boot 3.5 module uses `@ConditionalOnBooleanProperty`. The corresponding starter/adapter selects the appropriate module.

This approach fits when there are many genuine API differences. If only one annotation differs and the old API satisfies the exact semantics, keeping one shared module is usually easier to maintain.

### 6.4. Do not use reflection to hide a missing compile-time dependency

An annotation is written into class metadata by the compiler. Reflection is not a simple way to “use the annotation if the version has it, otherwise skip it”. If code must support multiple versions, use a common API available at the baseline or split artifacts by version.

Do not add a newer Boot JAR at runtime just to pick up one annotation while the application runs an older Boot version. That can cause hard-to-diagnose classpath conflicts.

## 7. Semantic changes to check beyond new class presence

### 7.1. Boot 3.5: property annotations become repeatable

Boot 3.5 makes `@ConditionalOnProperty` and `@ConditionalOnBooleanProperty` repeatable. This allows declaring multiple condition annotations on the same element. With Boot 3.3, use the `name` attribute containing multiple properties to require all to match.

### 7.2. Boot 3.5: stricter boolean enabled values

The Boot 3.5 release notes record that supported values for `.enabled`-style properties were tightened; values must be `true` or `false`. Some conditions in previous versions could treat any value other than `false` as enabled.

For custom boolean features, use `havingValue="true"` on `@ConditionalOnProperty` if keeping an older baseline, or use `@ConditionalOnBooleanProperty` once the baseline is Boot 3.5+. Test missing, true, false, and contract-violating values.

### 7.3. Boot 3.4: change in type inference inside bean conditions

Boot 3.4 changed the behavior of `@ConditionalOnBean` and `@ConditionalOnMissingBean` when placed on `@Bean` methods using the `annotation` attribute. When `annotation` is set, the method's return type is no longer automatically used as the default condition type as before; to restore the old behavior, `value` must also be declared with the return type.

For example, when upgrading versions, read the release notes and check conditions that combine multiple attributes. An annotation can remain present across many versions while its semantics change.

## 8. Hands-on project: testing new annotations with Boot 3.5.0

This project verifies three capabilities:

1. `@ConditionalOnBooleanProperty` registers the bean only when the boolean property satisfies the condition.
2. Two repeated boolean annotations can be combined on the same bean.
3. `@ConditionalOnThreading` selects the bean for platform threads when virtual threads are inactive.

### 8.1. Project structure

```text
conditional-annotation-version-lab/
├── pom.xml
├── src/main/java/demo/FeatureAutoConfiguration.java
└── src/test/java/demo/ConditionalAnnotationCompatibilityTest.java
```

### 8.2. Maven POM

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>conditional-annotation-version-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
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
```

Boot 3.5.0 is chosen deliberately because the project uses `@ConditionalOnBooleanProperty`. Java 17 is a valid baseline for Boot 3.5; the threading test below pins virtual threads to off so it does not require Java 21.

### 8.3. Auto-configuration

File `src/main/java/demo/FeatureAutoConfiguration.java`:

```java
package demo;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBooleanProperty;
import org.springframework.boot.autoconfigure.condition.ConditionalOnThreading;
import org.springframework.boot.autoconfigure.thread.Threading;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class FeatureAutoConfiguration {

    public record AuditMarker(String source) {
    }

    public record CombinedMarker(String source) {
    }

    public record PlatformMarker(String source) {
    }

    @Bean
    @ConditionalOnBooleanProperty(
            prefix = "acme.audit",
            name = "enabled")
    public AuditMarker auditMarker() {
        return new AuditMarker("boolean-property");
    }

    @Bean
    @ConditionalOnBooleanProperty(
            prefix = "acme",
            name = "audit-enabled")
    @ConditionalOnBooleanProperty(
            prefix = "acme",
            name = "metrics-enabled")
    public CombinedMarker combinedMarker() {
        return new CombinedMarker("both-flags");
    }

    @Bean
    @ConditionalOnThreading(Threading.PLATFORM)
    public PlatformMarker platformMarker() {
        return new PlatformMarker("platform-threads");
    }
}
```

The two boolean conditions on `combinedMarker` illustrate repeatable annotations. The bean matches only when both `acme.audit-enabled` and `acme.metrics-enabled` are true.

### 8.4. JUnit 5 tests

File `src/test/java/demo/ConditionalAnnotationCompatibilityTest.java`:

```java
package demo;

import demo.FeatureAutoConfiguration.AuditMarker;
import demo.FeatureAutoConfiguration.CombinedMarker;
import demo.FeatureAutoConfiguration.PlatformMarker;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class ConditionalAnnotationCompatibilityTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    FeatureAutoConfiguration.class))
                    .withPropertyValues(
                            "spring.threads.virtual.enabled=false");

    @Test
    void missingBooleanPropertyDoesNotRegisterAuditBean() {
        runner.run(context -> {
            assertThat(context).doesNotHaveBean(AuditMarker.class);
            assertThat(context).hasSingleBean(PlatformMarker.class);
        });
    }

    @Test
    void trueBooleanPropertyRegistersAuditBean() {
        runner.withPropertyValues("acme.audit.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(AuditMarker.class);
                    assertThat(context.getBean(AuditMarker.class).source())
                            .isEqualTo("boolean-property");
                });
    }

    @Test
    void falseBooleanPropertyDoesNotRegisterAuditBean() {
        runner.withPropertyValues("acme.audit.enabled=false")
                .run(context -> {
                    assertThat(context).doesNotHaveBean(AuditMarker.class);
                });
    }

    @Test
    void bothRepeatableBooleanConditionsMustMatch() {
        runner.withPropertyValues(
                "acme.audit-enabled=true",
                "acme.metrics-enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(CombinedMarker.class);
                });
    }

    @Test
    void oneMissingRepeatableBooleanConditionPreventsRegistration() {
        runner.withPropertyValues("acme.audit-enabled=true")
                .run(context -> {
                    assertThat(context).doesNotHaveBean(CombinedMarker.class);
                });
    }
}
```

`ApplicationContextRunner` creates a lightweight context to test conditions. `AutoConfigurations.of(...)` feeds the class directly into the context; this project tests semantics and compile-time APIs, not auto-configuration discovery via `AutoConfiguration.imports`.

### 8.5. Running tests

From the project directory:

```bash
mvn clean test
```

Expected output:

```text
Tests run: 5, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Surefire may vary how it formats the summary by version, yet all five tests must pass.

### 8.6. Trying a compatibility check with Boot 3.3

Change the parent version in the POM from `3.5.0` to `3.3.13` and run:

```bash
mvn clean test
```

The build will fail to compile because Boot 3.3.13 does not provide `ConditionalOnBooleanProperty` and its container annotation. This is the expected result: the project is using an API introduced after the baseline.

To retain Boot 3.3, replace the boolean condition with:

```java
@ConditionalOnProperty(
        prefix = "acme.audit",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false)
```

For two properties, use one annotation with multiple names:

```java
@ConditionalOnProperty(
        prefix = "acme",
        name = {"audit-enabled", "metrics-enabled"},
        havingValue = "true")
```

After changing the code, re-run `mvn clean test` with parent 3.3.13. `@ConditionalOnThreading` still works because it was introduced in Boot 3.2.0.

## 9. How to diagnose errors when an annotation is not recognized

| Symptom | Common cause | How to check |
| --- | --- | --- |
| IDE reports annotation not found | API does not exist in compile version | Check Javadoc `Since` and dependency tree |
| Maven reports `cannot find symbol` | Compile classpath resolves a Boot version lower than required | Inspect `spring-boot-autoconfigure` version |
| Code compiles but runtime differs from expected | Condition matches/no-matches per Environment | Read Condition Evaluation Report |
| A bean does not appear | Missing/wrong property value or another condition did not match | Check properties, classpath, beans, and profiles |
| `@ConditionalOnBooleanProperty` unavailable on Boot 3.3 | Annotation exists only from Boot 3.5.0 | Use `@ConditionalOnProperty(havingValue="true")` |
| `@ConditionalOnThreading` unavailable on Boot 3.1 | Annotation exists only from Boot 3.2.0 | Use a condition matching the older baseline or upgrade Boot |
| Local compile passes but CI fails | Local and CI resolve different dependency versions | Compare BOM, effective POM, and dependency tree |
| Annotation exists in JAR yet still fails to compile | JAR containing the class is not on compile classpath or hit a version conflict | Check compileClasspath and `javap` |

When conditions compile yet a bean does not appear, run the application with `--debug` to read the Condition Evaluation Report. Clearly distinguish **missing API at compile time** from **API available yet condition did not match at runtime**.

## 10. Version compatibility review checklist

- [ ] Identified the minimum Spring Boot version the module declares support for.
- [ ] Opened versioned Javadoc rather than looking only at the latest API.
- [ ] Recorded `Since` entries for annotations and accompanying enums/containers.
- [ ] Cross-checked release notes for behavior changes.
- [ ] Verified the actual version of `spring-boot-autoconfigure` in the dependency graph.
- [ ] Did not override a single Boot artifact version out of sync with the BOM.
- [ ] Code uses `@ConditionalOnBooleanProperty` only when the baseline is 3.5.0+.
- [ ] Code uses `@ConditionalOnThreading` only when the baseline is 3.2.0+.
- [ ] For Boot 3.3, used `@ConditionalOnProperty` with `havingValue="true"` when exact boolean true is needed.
- [ ] Verified repeatable behavior according to the exact version.
- [ ] CI compiles on the lowest supported version.
- [ ] CI runs tests for every key baseline.
- [ ] Distinguished compile-time API errors from runtime condition no-match.

**Remember:** The `Since` entry in Javadoc shows where an API first appeared; release notes explain why it was added and which semantics changed; the JAR/dependency tree confirms which version the project actually resolves; finally, compiling/testing with the minimum supported version proves the compatibility contract. In this lesson's examples, `@ConditionalOnThreading` is available from Boot 3.2.0, while `@ConditionalOnBooleanProperty` is only available from Boot 3.5.0. If still supporting Boot 3.3, using `@ConditionalOnProperty` with `havingValue="true"` is the compatible choice.

## Official documentation

- Spring Boot 3.2.0 API — `@ConditionalOnThreading`: https://docs.spring.io/spring-boot/docs/3.2.0/api/org/springframework/boot/autoconfigure/condition/ConditionalOnThreading.html
- Spring Boot 3.2.0 API — `Threading`: https://docs.spring.io/spring-boot/docs/3.2.0/api/org/springframework/boot/autoconfigure/thread/Threading.html
- Spring Boot 3.3 API — `@ConditionalOnProperty`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html
- Spring Boot 3.5 API — `@ConditionalOnBooleanProperty`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBooleanProperty.html
- Spring Boot 3.5 API — `@ConditionalOnBooleanProperties`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBooleanProperties.html
- Spring Boot 3.2 Release Notes: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.2-Release-Notes
- Spring Boot 3.4 Release Notes: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.4-Release-Notes
- Spring Boot 3.5 Release Notes: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.5-Release-Notes
