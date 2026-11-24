# Tracing Prerequisite Configurations Through before and after Relationships

## 1. Goal: Finding the Exact Configuration That Must Run Before an Auto-Configuration

An auto-configuration often depends on bean definitions provided by another configuration. For example, a JDBC configuration needs to know that a foundational configuration has registered a `DataSource` bean; a repository configuration needs to know that `JdbcTemplate` has been defined; a web adapter configuration must wait for the core MVC configuration.

When you see `@ConditionalOnBean` failing to match or `@ConditionalOnMissingBean` allowing a default bean to be created unexpectedly, trace these questions:

- Which configuration provides the prerequisite bean?
- Is that configuration actually an **auto-configuration candidate** during this startup?
- Which prerequisites does the current configuration declare `before` or `after` against?
- Is there an indirect dependency path through one or more intermediate configurations?
- Do the prerequisite configuration's conditions match, and does the bean definition expose a sufficiently specific type?
- Is the bean missing because of processing order, because the candidate was excluded, or because of another condition?

This article explains how to read the dependency graph from `before`/`after` metadata, trace direct and indirect prerequisites, verify candidates/exclusions, and confirm with `ApplicationContextRunner`. The scope is Spring Boot 3.3.x, Spring Framework 6.1, and Java 17+.

## 2. First Identify Which Configurations Are Actually Considered

Not every class annotated with `@Configuration` automatically becomes an auto-configuration. In Spring Boot 3.x, auto-configurations are discovered via the resource:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Each line contains the fully qualified name of an auto-configuration class; `#` can be used for comments. This resource is packaged inside the library's JAR. Spring Boot reads candidates from this resource on the runtime classpath.

Example file contents from a library:

```text
com.example.storage.autoconfigure.StorageAutoConfiguration
com.example.jdbc.autoconfigure.JdbcAutoConfiguration
com.example.repository.autoconfigure.RepositoryAutoConfiguration
```

These classes should live in a dedicated package and **must not be component-scanned as regular configurations**. Auto-configurations should be loaded via the imports file; when combining other configurations, use explicit `@Import` rather than enabling broad component scanning.

A class annotated with `@AutoConfiguration` that is not discovered through the proper import mechanism will not appear automatically just because the class exists in the JAR. Therefore, before tracing ordering relationships, confirm the candidate has been included in the set being processed.

### 2.1. Conceptual Candidate Pipeline

In the standard `@EnableAutoConfiguration` flow, you can visualize:

```text
Runtime classpath
      |
      v
Read AutoConfiguration.imports from JARs
      |
      v
Deduplicate candidates
      |
      v
Apply exclusions
      |
      v
Apply AutoConfigurationImportFilter
      |
      v
Selected candidate set
      |
      v
AutoConfigurationSorter reads before / after / order
      |
      v
Import auto-configurations in sorted order
      |
      v
Evaluate conditions and register bean definitions
```

These steps explain why an `after` edge cannot bring an excluded class back into the list. Before debating ordering, check whether the source class was discovered and remains in the candidate set after exclusions/filters.

Common candidate-removal mechanisms:

- `@EnableAutoConfiguration(exclude = ...)` excludes classes by type.
- `excludeName` excludes by class name, useful when avoiding a direct reference to an optional dependency.
- The `spring.autoconfigure.exclude` property allows excluding auto-configurations from application config.
- `AutoConfigurationImportFilter` can filter candidates based on metadata, typically to quickly eliminate unsuitable configurations.
- A class-level condition such as `@ConditionalOnClass` or `@ConditionalOnProperty` can prevent a configuration from being processed/registered as expected after the candidate was found.

Distinguish **absent from candidate set** from **candidate present but condition did not match**. These are two different causes and require different evidence.

## 3. Reading the Direction of before and after Correctly

Spring Boot supports two ways to express ordering relationships:

- `@AutoConfiguration(before = Other.class)` or `@AutoConfigureBefore(Other.class)`: the current configuration must be applied **before** `Other`.
- `@AutoConfiguration(after = Other.class)` or `@AutoConfigureAfter(Other.class)`: the current configuration must be applied **after** `Other`.

`@AutoConfiguration` provides `before`, `beforeName`, `after`, and `afterName` attributes as aliases for the corresponding ordering annotations. You can also use the standalone annotations `@AutoConfigureBefore` / `@AutoConfigureAfter` if preferred.

Example:

```java
@AutoConfiguration
class StorageAutoConfiguration {
    // Defines StorageClient or foundational beans.
}

@AutoConfiguration(after = StorageAutoConfiguration.class)
class JdbcAutoConfiguration {
    // Applied after StorageAutoConfiguration.
}
```

Here, `JdbcAutoConfiguration` declares that it must run after `StorageAutoConfiguration`. The arrow direction in the graph is:

```text
StorageAutoConfiguration  --->  JdbcAutoConfiguration
      prerequisite               dependent configuration
```

Do not misread `after = StorageAutoConfiguration.class` as "Storage runs after JDBC". The annotation sits on JDBC and specifies the configuration that JDBC must wait for.

### 3.1. Rule for Converting Annotations into Graph Edges

Adopt one consistent convention: arrows point from the configuration that must be applied earlier to the configuration applied later.

| Annotation on Configuration A | Edge to Draw | Interpretation |
| --- | --- | --- |
| `A @AutoConfiguration(after = B.class)` | `B -> A` | B is a direct prerequisite of A |
| `A @AutoConfiguration(before = B.class)` | `A -> B` | A is a direct prerequisite of B |
| `A @AutoConfigureAfter(B.class)` | `B -> A` | Equivalent to the after relationship above |
| `A @AutoConfigureBefore(B.class)` | `A -> B` | Equivalent to the before relationship above |

Mnemonic: `after` lists classes that must already have been applied; `before` lists classes that must not have been applied yet.

### 3.2. Example Tracing a Prerequisite Chain

Suppose there are three configurations:

```java
@AutoConfiguration
class StorageAutoConfiguration {
}

@AutoConfiguration(after = StorageAutoConfiguration.class)
class JdbcAutoConfiguration {
}

@AutoConfiguration(after = JdbcAutoConfiguration.class)
class RepositoryAutoConfiguration {
}
```

Graph:

```text
StorageAutoConfiguration
          |
          v
JdbcAutoConfiguration
          |
          v
RepositoryAutoConfiguration
```

If investigating `RepositoryAutoConfiguration`, trace backward:

1. `RepositoryAutoConfiguration.after` points to `JdbcAutoConfiguration`.
2. Open `JdbcAutoConfiguration`; `JdbcAutoConfiguration.after` points to `StorageAutoConfiguration`.
3. `StorageAutoConfiguration` declares no other prerequisites in the example.
4. The prerequisite chain is `Storage -> Jdbc -> Repository`.

This is a **transitive** relationship: `Storage` must precede `Repository` via `Jdbc`. You do not need to add `after = StorageAutoConfiguration.class` to Repository if the direct relationship through Jdbc already expresses the contract properly; only add a direct edge when it represents a genuinely independent dependency.

### 3.3. Multiple Prerequisites Do Not Imply Ordering Between Them

If A declares:

```java
@AutoConfiguration(after = {
        StorageAutoConfiguration.class,
        MetricsAutoConfiguration.class
})
class ReportingAutoConfiguration {
}
```

the graph has two edges:

```text
StorageAutoConfiguration  ----\
                               ---> ReportingAutoConfiguration
MetricsAutoConfiguration  ----/
```

Both Storage and Metrics configurations are prerequisites of Reporting, but there is **no conclusion** that Storage must precede Metrics or vice versa. To determine any ordering between them, you must find another edge in the metadata. Do not invent an ordering from the order items are written in the annotation list.

Similarly, if a candidate has no edge connecting it to another candidate, do not rely on accidental line order in the imports file, alphabetical order, or test argument order to infer a domain relationship.

## 4. Tracing Direct and Indirect Prerequisites Backward

Once you have selected the target class, inspect metadata in both directions.

### 4.1. Read the after Attribute Directly on the Target Class

Example:

```java
@AutoConfiguration(
    after = {
        DataSourceAutoConfiguration.class,
        JdbcTemplateAutoConfiguration.class
    })
class RepositoryAutoConfiguration {
}
```

The two classes in `after` are declared direct prerequisites. For each class:

1. Confirm the exact class name.
2. Locate the class in candidate imports.
3. Open that class and read its `before`/`after` attributes.
4. Repeat until you reach foundational configurations with no declared prerequisites or a candidate absent from the current set.

### 4.2. Find Other Configurations Whose before Points to the Target Class

Not every relationship is written in the target class's `after`. Another configuration may declare:

```java
@AutoConfiguration(before = RepositoryAutoConfiguration.class)
class RepositoryMetricsAutoConfiguration {
}
```

Therefore, when tracing the graph backward, you must also search for other classes whose `before` references the class under investigation. If you only read `after` on the target class, you may miss predecessors declared from the other side.

Practical search rules:

- **Tracing backward:** find all classes A whose `after` is referenced by B, and all classes A whose `before` contains B, following the edge direction A → B (i.e., predecessors of B).
- **Tracing forward:** from B, find classes whose `after` contains B (B → C) and classes referenced by B's `before` (B → C).
- Repeat to collect all direct and transitive paths.

### 4.3. Record a Graph Rather Than Just a List

A trace table makes review verification much easier:

| Configuration | Declared Relationship | Normalized Edge | Role |
| --- | --- | --- | --- |
| `StorageAutoConfiguration` | None | — | Foundational bean source |
| `JdbcAutoConfiguration` | `after = StorageAutoConfiguration` | Storage → JDBC | Direct prerequisite |
| `RepositoryAutoConfiguration` | `after = JdbcAutoConfiguration` | JDBC → Repository | Dependent configuration |
| `RepositoryMetricsAutoConfiguration` | `before = RepositoryAutoConfiguration` | Metrics → Repository | Another prerequisite |

The resulting graph may look like:

```text
StorageAutoConfiguration ---> JdbcAutoConfiguration ---\
                                                        ---> RepositoryAutoConfiguration
RepositoryMetricsAutoConfiguration -------------------/
```

From this diagram, you can only conclude that both Storage and Metrics precede Repository. With no edge between Storage and Metrics, you cannot assert which comes first.

## 5. beforeName and afterName: Relationships Without Class Literals

When the current configuration depends on an auto-configuration from an optional library, using a class literal can create an unwanted compile-time dependency. `@AutoConfiguration` provides `beforeName` and `afterName` to reference fully qualified class names as strings:

```java
@AutoConfiguration(
    afterName = "com.example.storage.autoconfigure.StorageAutoConfiguration")
class JdbcAutoConfiguration {
}
```

Or:

```java
@AutoConfiguration(
    beforeName = "com.example.metrics.autoconfigure.MetricsAutoConfiguration")
class StorageAutoConfiguration {
}
```

The name must match the exact fully qualified class name. For nested classes, use `$` to separate the outer and inner class, for example:

```java
@AutoConfiguration(
    afterName = "com.example.OuterConfiguration$NestedAutoConfiguration")
class DependentAutoConfiguration {
}
```

`afterName` does not itself add the referenced class to the candidate list. It only describes a relationship if a class with that name exists in the auto-configuration set being sorted. If the class is absent, excluded, or not selected, the relationship cannot supply the prerequisite bean.

When investigating name mismatches, check the package, letter case, nested `$`, package refactors, and replacements files. Do not use a runtime bean name in place of an auto-configuration class name.

## 6. Distinguishing Relative Ordering, Priority Ordering, and Instantiation Order

Three mechanisms are frequently confused:

| Mechanism | What It Is For | What It Does Not Do |
| --- | --- | --- |
| `@AutoConfiguration(before/after)` | Expresses relative dependencies between auto-configurations | Does not force constructor or instance creation order |
| `@AutoConfigureOrder` | Gives a general order among auto-configurations with no direct relationship | Does not clearly express a specific bean prerequisite |
| `@DependsOn` / dependency injection | Controls bean instance creation relationships | Does not re-run an already-evaluated condition |

Spring Boot also states explicitly: auto-configuration application order only affects the order in which **bean definitions are registered**. Subsequent bean instantiation is governed by bean dependencies and `@DependsOn`.

Example:

```java
@Bean
ConsumerService consumerService(StorageClient storageClient) {
    return new ConsumerService(storageClient);
}
```

Dependency injection already expresses that `ConsumerService` needs `StorageClient`. The container guarantees the required dependency is provided when creating the consumer. You do not need `@DependsOn` just to make injection work.

Conversely, `@ConditionalOnBean(StorageClient.class)` is evaluated during configuration processing. If the auto-configuration providing StorageClient has not been processed when the condition runs, adding `@DependsOn` will not make the condition see the bean definition. In that case, examine `before`/`after` and type metadata.

Regular `@Order` is likewise not a substitute for `@AutoConfigureBefore`/`@AutoConfigureAfter`. When a relative relationship is needed, declare the explicit edge. `@AutoConfigureOrder` is only appropriate when you need a general precedence among auto-configurations that do not know about each other directly.

## 7. Verify Candidates, Exclusions, and Conditions Before Concluding an Ordering Bug

A graph edge is only useful when both endpoints are active candidates in the current startup.

### 7.1. Confirm the imports Resource

Inside the JAR, verify that the resource exists:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

and contains the needed class name. If the library includes multiple auto-configurations, read the entire file to identify candidates in the same group.

### 7.2. Check Exclusions

Look for:

- `@EnableAutoConfiguration(exclude = ...)`
- `excludeName`
- `spring.autoconfigure.exclude`
- Test configurations with `exclude`/`excludeName`
- Exclusions or import filters added by integrated frameworks/libraries

If the source is excluded, `after` on the consumer cannot force the source to be imported again.

### 7.3. Check Conditions on the Source Itself

Even when the source is a candidate and is applied earlier, the prerequisite bean may still not appear if:

- `@ConditionalOnClass` does not match.
- `@ConditionalOnProperty` is turned off or lacks the required value.
- The source's own `@ConditionalOnBean`/`@ConditionalOnMissingBean` does not match.
- The `@Bean` method is excluded by its own condition.
- The bean definition is registered, yet its return type / `FactoryBean` metadata is too broad for downstream conditions to recognize.
- The bean name/type checked by the consumer does not match the source's actual contract.

Therefore, ordering traces do not stop at class annotations. Open the bean method creating the prerequisite and read all conditions on that class, nested configuration, and method.

### 7.4. Check Class Renames

If an auto-configuration is moved/renamed, Boot 3.x supports the resource:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements
```

This resource maps old classes to replacement classes. Because auto-configuration classes may be referenced in `before`/`after` and `exclude`, when refactoring packages you must update ordering relationships and replacement metadata accordingly. Do not leave old names sitting in `afterName` assuming Boot will guess the new class.

## 8. Practical Workflow for Tracing Prerequisites in a Project

Follow these steps in order so you do not confuse a class sitting in source code with a candidate that is actually loaded.

### Step 1: Locate the Dependency Containing the Auto-Configuration

With Gradle, inspect the runtime dependency graph:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Inspect the specific library:

```bash
./gradlew dependencyInsight --dependency storage-starter --configuration runtimeClasspath
```

Replace `storage-starter` with the actual module/artifact name. The goal is to confirm the library is on the runtime classpath and know which JAR to open.

### Step 2: Locate the imports Resource Inside the JAR

List JAR contents:

```bash
jar tf path/to/storage-starter.jar
```

Filter resource names with an appropriate tool (such as `grep` on Linux/macOS or `Select-String` in PowerShell). Once the path is confirmed, extract just that resource into a temporary directory to read it:

```bash
jar xf path/to/storage-starter.jar META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Read the extracted file. Never modify a dependency JAR directly; this is a read step to trace candidates.

### Step 3: Search for Annotations in Source

In the project source or sources JAR, search:

```bash
rg -n "@AutoConfiguration|@AutoConfigureBefore|@AutoConfigureAfter|@AutoConfigureOrder|beforeName|afterName" .
```

Collect all classes related to the target class. If a class exists only in a binary dependency, open the sources JAR/IDE decompiler or inspect annotation metadata with an appropriate tool.

### Step 4: Normalize into a Graph

Convert every relation into an earlier-to-later arrow:

- `A after B` → `B -> A`.
- `A before B` → `A -> B`.

Mark which candidates are in imports, which are excluded, which are filtered, and which have non-matching conditions. Then trace backward from the target configuration to find all direct and indirect predecessors.

### Step 5: Cross-Check Bean Conditions

Find `@Bean` methods using `@ConditionalOnBean` or `@ConditionalOnMissingBean`. Compare the type/name required by the condition against the return type/metadata of the source bean. Even a correct graph does not guarantee a condition match if the source fails to register the bean or its type cannot be recognized.

### Step 6: Prove It with Tests

Use `ApplicationContextRunner` and `AutoConfigurations.of(...)` to build a small context. Keep classpath/properties identical while changing only `before`/`after` relationships or presence/absence of the source. Assert both the final bean and whether conditions permit/disallow dependent beans.

### Step 7: Debug the Sorter When Necessary

When metadata is complex, set a breakpoint in `AutoConfigurationSorter.getInPriorityOrder(...)` or the `AutoConfigurationImportSelector` flow to inspect the candidate set and sorted order in the exact running Spring Boot version. This is an internal class for debugging; do not depend directly on this implementation class in production code.

`--debug` and the Conditions Evaluation Report are helpful for finding which conditions matched/did not match, but the report is not an official substitute for tracing ordering metadata. Use the debugger or tests that reverse input order to confirm relationships.

## 9. Complete Prerequisite Graph Example

Suppose a library has these candidates:

- `StorageAutoConfiguration`: provides `StorageMarker`.
- `JdbcAutoConfiguration`: needs Storage, declares `after = StorageAutoConfiguration`.
- `RepositoryAutoConfiguration`: needs JDBC, declares `after = JdbcAutoConfiguration`.
- `MetricsAutoConfiguration`: needs repository, declares `after = RepositoryAutoConfiguration`.
- `RepositoryMetricsAutoConfiguration`: declares `before = RepositoryAutoConfiguration`.

Graph:

```text
StorageAutoConfiguration
          |
          v
JdbcAutoConfiguration
          |
          v
RepositoryAutoConfiguration <--- RepositoryMetricsAutoConfiguration
          |
          v
MetricsAutoConfiguration
```

If investigating `MetricsAutoConfiguration`, tracing backward yields:
`RepositoryAutoConfiguration`, then `JdbcAutoConfiguration`, then `StorageAutoConfiguration`; at the same time, search for other classes declaring `before = MetricsAutoConfiguration` or `before = RepositoryAutoConfiguration` to catch predecessors from the reverse direction.

Do not conclude `RepositoryMetricsAutoConfiguration` must precede Storage or JDBC because the graph contains no such edges. It only needs to precede Repository.

If `JdbcAutoConfiguration` is excluded, the chain breaks. If `StorageAutoConfiguration` is present yet the Storage bean's condition does not match, `JdbcAutoConfiguration` can still run after it, yet `@ConditionalOnBean(StorageMarker.class)` may fail to match. If the Storage bean definition declares an overly broad type, the condition may likewise fail to recognize it. Each case has a different fix.

## 10. Runnable Practice: Verifying Direct, Indirect, and before Relationships

The following test suite nests auto-configurations inside a test class for isolation. `AutoConfigurations.of(...)` uses Boot's auto-configuration sorting mechanism; the argument order passed to the helper is not the ordering contract.

### 10.1. Project Structure

```text
auto-configuration-prerequisite-trace/
├── settings.gradle
├── build.gradle
└── src/test/java/demo/AutoConfigurationPrerequisiteTraceTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'auto-configuration-prerequisite-trace'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test:3.3.13'
}

test {
    useJUnitPlatform()
}
```

### 10.2. Complete Java 17 Test File

`src/test/java/demo/AutoConfigurationPrerequisiteTraceTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;

import static org.assertj.core.api.Assertions.assertThat;

class AutoConfigurationPrerequisiteTraceTest {

    record StorageMarker(String origin) {}

    record JdbcMarker(String source) {}

    record RepositoryMarker(String source) {}

    record EarlyMarker(String source) {}

    record NameBasedMarker(String source) {}

    record FallbackMarker(String origin) {}

    @AutoConfiguration
    static class StorageAutoConfiguration {

        @Bean
        StorageMarker storageMarker() {
            return new StorageMarker("storage");
        }
    }

    @AutoConfiguration(after = StorageAutoConfiguration.class)
    static class JdbcAutoConfiguration {

        @Bean
        @ConditionalOnBean(StorageMarker.class)
        JdbcMarker jdbcMarker(StorageMarker storage) {
            return new JdbcMarker(storage.origin());
        }
    }

    @AutoConfiguration(after = JdbcAutoConfiguration.class)
    static class RepositoryAutoConfiguration {

        @Bean
        @ConditionalOnBean(JdbcMarker.class)
        RepositoryMarker repositoryMarker(JdbcMarker jdbc) {
            return new RepositoryMarker(jdbc.source());
        }
    }

    @AutoConfiguration(before = StorageAutoConfiguration.class)
    static class EarlyObserverAutoConfiguration {

        @Bean
        @ConditionalOnBean(StorageMarker.class)
        EarlyMarker earlyMarker() {
            return new EarlyMarker("storage was already visible");
        }
    }

    @AutoConfiguration(
            afterName =
                    "demo.AutoConfigurationPrerequisiteTraceTest$StorageAutoConfiguration")
    static class NameBasedJdbcAutoConfiguration {

        @Bean
        @ConditionalOnBean(StorageMarker.class)
        NameBasedMarker nameBasedMarker() {
            return new NameBasedMarker("name-based prerequisite");
        }
    }

    @AutoConfiguration(after = StorageAutoConfiguration.class)
    static class FallbackAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(StorageMarker.class)
        FallbackMarker fallbackMarker() {
            return new FallbackMarker("fallback");
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner();

    @Test
    void afterRelationMakesPrerequisiteVisible() {
        // Consumer is passed first; after metadata still sorts Storage ahead.
        runner.withConfiguration(AutoConfigurations.of(
                JdbcAutoConfiguration.class,
                StorageAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).hasSingleBean(StorageMarker.class);
                    assertThat(context).hasSingleBean(JdbcMarker.class);
                    assertThat(context).hasBean("storageMarker");
                    assertThat(context).hasBean("jdbcMarker");
                    assertThat(context.getBean(JdbcMarker.class).source())
                            .isEqualTo("storage");
                });
    }

    @Test
    void beforeRelationCanMakeConsumerRunTooEarly() {
        // Storage is passed first, yet EarlyObserver declares before Storage.
        runner.withConfiguration(AutoConfigurations.of(
                StorageAutoConfiguration.class,
                EarlyObserverAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).hasBean("storageMarker");
                    assertThat(context).doesNotHaveBean("earlyMarker");
                    assertThat(context).hasSingleBean(StorageMarker.class);
                });
    }

    @Test
    void afterNameResolvesTheExactPrerequisiteClassName() {
        runner.withConfiguration(AutoConfigurations.of(
                NameBasedJdbcAutoConfiguration.class,
                StorageAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).hasBean("storageMarker");
                    assertThat(context).hasSingleBean(NameBasedMarker.class);
                });
    }

    @Test
    void transitiveAfterRelationsExposeTheFullPrerequisiteChain() {
        runner.withConfiguration(AutoConfigurations.of(
                RepositoryAutoConfiguration.class,
                JdbcAutoConfiguration.class,
                StorageAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).hasSingleBean(StorageMarker.class);
                    assertThat(context).hasSingleBean(JdbcMarker.class);
                    assertThat(context).hasSingleBean(RepositoryMarker.class);
                    assertThat(context.getBean(RepositoryMarker.class).source())
                            .isEqualTo("storage");
                });
    }

    @Test
    void missingPrerequisiteLeavesConditionalFeatureAbsent() {
        runner.withConfiguration(AutoConfigurations.of(
                JdbcAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).doesNotHaveBean(StorageMarker.class);
                    assertThat(context).doesNotHaveBean(JdbcMarker.class);
                });
    }

    @Test
    void fallbackAfterSourceBacksOffWhenSourceExists() {
        runner.withConfiguration(AutoConfigurations.of(
                FallbackAutoConfiguration.class,
                StorageAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).hasSingleBean(StorageMarker.class);
                    assertThat(context).hasBean("storageMarker");
                    assertThat(context).doesNotHaveBean("fallbackMarker");
                });
    }
}
```

### 10.3. Running the Tests

In the project directory:

```bash
gradle test --tests demo.AutoConfigurationPrerequisiteTraceTest
```

If using the Gradle Wrapper on Linux/macOS:

```bash
./gradlew test --tests demo.AutoConfigurationPrerequisiteTraceTest
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests demo.AutoConfigurationPrerequisiteTraceTest
```

The expected result is **6 tests passed**. This is the expected result when dependencies resolve and JDK/Gradle are compatible; Gradle logs have no fixed stdout text.

### 10.4. Why Each Test Matters

| Test | Metadata Tested | What to Observe |
| --- | --- | --- |
| `afterRelationMakesPrerequisiteVisible` | JDBC `after` Storage | Even though the test passes JDBC first, the Storage bean is defined before the JDBC condition evaluates; the JDBC bean appears |
| `beforeRelationCanMakeConsumerRunTooEarly` | EarlyObserver `before` Storage | Condition runs before Storage, so early marker is not created; Storage still exists after refresh |
| `afterNameResolvesTheExactPrerequisiteClassName` | `afterName` | Exact FQCN string enables sorting without a class literal |
| `transitiveAfterRelationsExposeTheFullPrerequisiteChain` | Storage → JDBC → Repository | Two after edges form a transitive prerequisite chain |
| `missingPrerequisiteLeavesConditionalFeatureAbsent` | Missing Storage candidate | Bean condition does not match; no JDBC marker exists |
| `fallbackAfterSourceBacksOffWhenSourceExists` | Fallback `after` Source + MissingBean | Source is present, so fallback does not register |

The `beforeRelationCanMakeConsumerRunTooEarly` test is especially instructive: after context refresh, `storageMarker` exists, yet `earlyMarker` remains absent. That proves the condition does not re-evaluate automatically when the source is processed later.

The `afterName` test uses a nested class name with `$`. If the class is renamed/moved to another package, the string must be updated to match the new class name.

## 11. Common Mistakes When Tracing before/after

| Symptom | Cause | How to Investigate |
| --- | --- | --- |
| Added `after` yet condition still does not match | Source is not a candidate, excluded/filtered, or source's own condition fails | Check imports, exclusions, report, and source conditions |
| Class is in JAR yet absent at startup | Missing from `AutoConfiguration.imports` or resource packaged incorrectly | Check JAR contents and resource path |
| Consumer has `after`, yet source bean is still not found | Source is present but creates no bean; or return type/`FactoryBean` metadata is too broad | Read bean method, conditions, and declared return type |
| `before`/`after` behavior unchanged when reordering imports file | Boot sorts candidates using metadata | Do not rely on line order in imports; verify with tests |
| Used `@DependsOn`, yet condition still fails | Adjusted instance creation order while failure occurs during bean definition processing | Fix the auto-configuration ordering relationship |
| Used `@Order`, yet auto-configs remain misordered | `@Order` does not replace auto-config ordering | Use `@AutoConfiguration(before/after)` or `@AutoConfigureBefore/After` |
| `afterName` has no effect | Wrong FQCN, wrong `$` for nested class, or target not in candidate set | Verify class name against imports/JAR |
| Multiple predecessors exist, yet order between them is unexpected | Only edges pointing to consumer exist; no edge between predecessors | Draw the full graph; do not infer undeclared ordering |
| Source is excluded | Ordering metadata cannot reload an excluded source | Remove exclusion or fix candidate discovery as intended |
| Test passes yet real app behaves differently | Test does not reproduce same candidate set, exclusions, properties, classpath, or context | Compare test inputs with runtime and use report/debugger |

### 11.1. Do Not Confuse imports Order with Applied Order

The `AutoConfiguration.imports` file is a candidate list, not a document from which readers can infer final order by line position. Spring Boot collects candidates, applies exclusions/filters, and then sorts them according to ordering metadata.

Similarly, in `ApplicationContextRunner`, do not manually order classes passed to `AutoConfigurations.of(...)` to simulate relationships; the `before`/`after` metadata itself is what needs testing.

### 11.2. Do Not Confuse Condition Mismatch with Ordering Errors

If `@ConditionalOnBean` does not match, verify whether the condition ran before the source. If the source was already processed earlier and it still does not match, check:

- Does the requested type match the declared return type?
- Was the source bean excluded by another condition?
- Is `search = SearchStrategy.CURRENT` used while the bean lives in a parent context?
- Is the source produced by a `FactoryBean` whose `getObjectType()` does not publish a specific enough type?
- Is the consumer checking a different bean type or bean name than the source's actual one?

Only change `after` when the graph and timing prove that ordering is the root cause.

### 11.3. Conflicting Graphs

A cyclic constraint chain—for example A `after` B, B `after` C, and C `after` A—cannot have a linear order satisfying every edge. Remove or redesign the relationships so the graph is acyclic. Do not try to patch cycles by adding `@AutoConfigureOrder`; precedence must reflect real dependencies.

## 12. Review Checklist When Adding or Modifying Ordering Relationships

- [ ] Class is annotated with `@AutoConfiguration` and listed in the JAR's `AutoConfiguration.imports`.
- [ ] Prerequisite class is also present in the candidate set for the run under review.
- [ ] Checked `exclude`, `excludeName`, `spring.autoconfigure.exclude`, and import filters.
- [ ] Read `before`, `after`, `beforeName`, and `afterName` on both the target configuration and related configurations.
- [ ] Normalized every relationship into an earlier-to-later edge.
- [ ] Traced transitive predecessors, not just a single direct edge.
- [ ] Did not infer ordering between two configurations without a constraining edge.
- [ ] Checked source conditions and the bean definition type required by the consumer.
- [ ] Did not use `@DependsOn`/`@Order` in place of auto-config ordering.
- [ ] Added tests proving bean presence/absence in the appropriate cases.
- [ ] Tested reversing argument order in `AutoConfigurations.of(...)` to prove metadata is the contract.
- [ ] Tested missing source and user override/fallback if supported by the feature.
- [ ] Verified class name strings in `beforeName`/`afterName`, including `$` if nested.
- [ ] Updated references/replacements when renaming classes.
- [ ] Verified there are no ordering cycles.

**Key takeaway:** To trace prerequisite configurations, start from the actually selected candidates, convert `before`/`after` into directed edges, and trace backward through all direct and indirect predecessors. Then verify that the source is processed and creates a matching bean definition before the consumer's condition runs. The metadata graph explains **definition order**; bean assertions prove **final behavior**.

## Official Documentation

- Spring Boot 3.3 — Creating Your Own Auto-configuration, candidate discovery, imports file, and ordering: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 API — `@AutoConfiguration`, `before`, `beforeName`, `after`, `afterName` attributes: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html
- Spring Boot 3.3 API — `@AutoConfigureBefore`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureBefore.html
- Spring Boot 3.3 API — `@AutoConfigureAfter`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureAfter.html
- Spring Boot 3.3 API — `@AutoConfigureOrder`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureOrder.html
- Spring Boot 3.3 — Testing Auto-configuration with `ApplicationContextRunner`: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
