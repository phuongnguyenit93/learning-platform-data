# Merging Candidate Lists, Deduplication, and Exclusions

> **Context:** Spring Boot 3.3.x, Spring Framework 6.1, and Java 17+. This lesson belongs to the **Candidate Discovery** topic of the auto-configuration mechanism. The focus is on how the list of *auto-configuration candidate classes* is assembled, deduplicated, filtered by exclusions, and consolidated into a single list for Spring to process further. This is the step of selecting **configuration classes**, not the step of creating all beans.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Explain the origin of the **auto-configuration candidates** list and why multiple JARs contribute to that list.
2. Distinguish **deduplication within a single selection**, **merging across entries**, and **sorting the final result**.
3. Know the three main exclusion mechanisms: `exclude`, `excludeName`, and `spring.autoconfigure.exclude`; understand how they operate on **auto-configuration class names**.
4. Interpret how `AutoConfigurationImportSelector` and `AutoConfigurationGroup` behave when there are multiple candidate sources or multiple deferred import invocations.
5. Recognize that invalid exclusions, outdated class names, non-matching conditions, and default beans backing off are **distinct phenomena**.
6. Run a small Spring Boot application with duplicate candidate declarations, then test exclusions and property conditions; write tests proving context behavior.

**Key point:** The candidate list entering the selector may contain duplicate names and configurations that ultimately are not used. Boot must *normalize the name set → subtract exclusions → apply early-checkable condition filters → sort → import*. After importing, Spring continues evaluating `@Conditional` on configurations and `@Bean` methods.

## 2. What Is a Candidate and Where Does It Come From?

In Spring Boot 3.x, each JAR can provide the file:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

For example, the first JAR:

```text
com.acme.cache.CacheAutoConfiguration
com.acme.metrics.MetricsAutoConfiguration
```

The second JAR:

```text
com.acme.metrics.MetricsAutoConfiguration
com.acme.search.SearchAutoConfiguration
```

If we simply concatenate lines in discovery order, we get:

```text
CacheAutoConfiguration
MetricsAutoConfiguration
MetricsAutoConfiguration
SearchAutoConfiguration
```

`MetricsAutoConfiguration` is duplicated. Boot must not treat two lines with the same name as two independent auto-configurations to be executed twice.

**The unit of identity for deduplication at this stage is the fully qualified class name (FQCN)**, such as `com.acme.metrics.MetricsAutoConfiguration`. Two differently named classes that both create a bean of the same type are **not** a “duplicate candidate” case; bean creation issues require bean conditions, auto-configuration ordering, or a dedicated design solution.

### 2.1. Data Source Differs from Final Outcome

The imports file only declares *candidates*. For a configuration to actually be applied, there are these remaining gates:

```text
Runtime classpath / ClassLoader
  |
  v
Multiple AutoConfiguration.imports resources
  |
  v
Candidate name list (may have duplicates)
  |
  v
Deduplication, exclusions, import filters
  |
  v
AutoConfigurationGroup merges and sorts
  |
  v
Spring processes imported configuration classes
  |
  v
@Conditional on class / @Bean method
  |
  v
Bean definitions, then bean instances
```

Therefore, **seeing a name in imports does not mean the bean appears**; conversely, merely observing that a bean is absent is not enough to conclude the class was never a candidate.

In Spring Boot 3.x, `ImportCandidates` reads imports files by the appropriate annotation name. JARs must actually be on the runtime classpath and the relevant class loader must see the resources. This candidate registration mechanism differs from using `spring.factories` with the `EnableAutoConfiguration` key in older Boot generations; `spring.factories` still serves other roles at certain extension points.

## 3. Two Layers of Duplicate Handling

### 3.1. Layer One: Deduplicating Names Within Each AutoConfigurationEntry

`AutoConfigurationImportSelector` has a `getAutoConfigurationEntry(...)` method, logically structured as:

```text
candidates = getCandidateConfigurations(...)
candidates = removeDuplicates(candidates)

exclusions = getExclusions(...)
checkExcludedClasses(candidates, exclusions)
candidates.removeAll(exclusions)

candidates = applyAutoConfigurationImportFilters(candidates)
notifyImportListeners(candidates, exclusions)

return AutoConfigurationEntry(candidates, exclusions)
```

This is **pseudocode describing the role of the API**, not a verbatim copy of the source code and not meant for compilation. Essential order: *get candidates → deduplicate → collect exclusions → validate exclusions → remove excluded names → filter → return result with exclusions*.

In the Boot 3.3 branch implementation, the `removeDuplicates` helper leverages `LinkedHashSet` semantics to keep one copy of each name while preserving first-seen order **at that step**.

Example:

| Raw List | After Deduplication |
| --- | --- |
| `A, B, A, C, B` | `A, B, C` |
| `A, A, A` | `A` |
| `B, A, C` | `B, A, C` |

**Do not infer that this order is the final import order**: afterward, `AutoConfigurationGroup` also sorts by order and before/after metadata.

### 3.2. Layer Two: Merging Results Across Multiple Deferred Selector Passes

`AutoConfigurationImportSelector` implements `DeferredImportSelector` and provides a `Group` called `AutoConfigurationGroup`. When Spring processes selectors in the same group, the group receives multiple `AutoConfigurationEntry` instances.

Suppose there are two entries after each entry has deduplicated and removed local exclusions:

```text
Entry 1:
  configurations = [A, B]
  exclusions     = [C]

Entry 2:
  configurations = [C, D]
  exclusions     = [B]
```

The group does not simply concatenate the two arrays and import them; the group:

1. Collects all exclusions: `{C, B}`.
2. Collects all configurations into a deduplicated set: `{A, B, C, D}`.
3. Removes the **shared exclusions set**: leaving only `{A, D}`.
4. Sorts the remaining configurations, then creates corresponding `Group.Entry` items for Spring to import.

The result **A and D** illustrates an important property: **an exclusion from one entry can eliminate a candidate contributed by another entry in the same group**. When reading the source yourself, pay attention to `AutoConfigurationGroup.selectImports()`, rather than only looking at `getAutoConfigurationEntry()`.

In a typical application with one main class enabling auto-configuration, the group path is still used; multiple entries do not always appear. Do not confuse a multi-entry example with a claim that Spring Boot always creates two entries for every application.

### 3.3. Why Does the Group Need to Retain Exclusions?

Each `AutoConfigurationEntry` carries two kinds of information:

- `configurations`: remaining configuration names from that selector pass;
- `exclusions`: the set of names to exclude.

If entry 1 removed C yet entry 2 still contributes C, merging only the `configurations` lists would bring C back. Retaining `exclusions` for the group allows subtracting the full set of exclusions at the combined result level. That is why exclusions cannot be treated as meaningless extra data after local filtering.

### 3.4. Two Non-Equivalent Forms of “Duplicate”

| Duplicate Type | Example | How to Interpret |
| --- | --- | --- |
| Duplicate **auto-configuration FQCN** | `A` appears twice in imports | Selector/group deduplicates the name in the list |
| Two **different auto-configurations** creating a `Client` bean | `AAutoConfiguration` and `BAutoConfiguration` | Requires bean conditions / ordering / design to avoid conflict |
| Same bean registered via scanning and imports | Auto-configuration class accidentally picked up by component scan | Package/registration boundary bug; not solved merely by name dedup in selector |
| Two JARs containing the same binary class `com.acme.A` with different bytecode | Dependency collision | Classpath/classloader issue; imports name dedup **does not guarantee** picking the right implementation |

Identify which layer you are dealing with before fixing.

## 4. Sources of Auto-Configuration Exclusions

Spring Boot lets application builders request **not to apply a specific auto-configuration**.

### 4.1. `exclude`: Excluding by Class Literal

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;

@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)
public class ExampleApplication {
    public static void main(String[] args) {
        SpringApplication.run(ExampleApplication.class, args);
    }
}
```

This is a **standalone example**, compiling only when the dependency providing `DataSourceAutoConfiguration` is on the compile classpath. It is not part of the demo project in section 8.

`@SpringBootApplication` forwards the `exclude` attribute to `@EnableAutoConfiguration`. Prefer class literals when the real project has the relevant dependency, as IDEs can refactor them and the compiler can catch typos.

### 4.2. `excludeName`: Excluding by Fully Qualified Class Name

```java
@SpringBootApplication(excludeName = {
    "com.acme.cache.CacheAutoConfiguration",
    "com.acme.search.SearchAutoConfiguration"
})
```

The snippet above is an **annotation excerpt** that must be placed on an application class to become independently compilable code. `excludeName` is useful when you do not want to reference a class literal in source, such as when an auto-configuration lives in an optional dependency.

Use only auto-configuration class names—**not bean method names, interfaces, starter artifacts, or arbitrary annotations**.

### 4.3. `spring.autoconfigure.exclude`: Excluding from the Environment

In `application.properties`:

```properties
spring.autoconfigure.exclude=com.acme.cache.CacheAutoConfiguration,com.acme.search.SearchAutoConfiguration
```

Or at runtime:

```bash
java -jar app.jar --spring.autoconfigure.exclude=com.acme.cache.CacheAutoConfiguration
```

All three forms contribute names to the exclusions set, coming from different configuration sources. The property allows adjustments outside code, useful when dealing with runtime environments or testing.

**Do not confuse** `spring.autoconfigure.exclude` with `spring.boot.enableautoconfiguration=false`: the former excludes **named classes**, whereas the latter disables the default auto-configuration selection mechanism more broadly. Neither removes dependencies from the classpath.

### 4.4. Which Exclusion Takes Precedence When the Same Class Appears Multiple Times?

Exclusions are **combined into a single set**. If you exclude `A` via an annotation and simultaneously via a property, the result is still **A excluded**; there is no “second mention re-enables A”. This is an exclusion selection, not a two-way override configuration.

Example:

```text
Candidates = [A, B, C, A, D, B]

exclude      = [B]
excludeName  = [C]
property     = [B, D]

After deduplication [A, B, C, D]
Combined exclusions {B, C, D}
Remaining           [A]
```

When inspecting configuration, remember properties follow `Environment` precedence rules. The same property key declared across multiple sources may bind to different values according to precedence; the **exclusions set** is the result after the selector reads the effective attributes/properties, not simply concatenating text from every properties file in the application.

## 5. When Is an Exclusion Considered Invalid?

`AutoConfigurationImportSelector` includes a `checkExcludedClasses(...)` step. In Spring Boot 3.3's default mechanism, if an exclusion name refers to **a class present on the classpath that does not belong to the valid auto-configuration candidate list**, Boot can report:

```text
The following classes could not be excluded because they are not auto-configuration classes:
    - com.example.SomeRegularConfiguration
```

This sample conveys the **meaning of the message**, without guaranteeing identical log whitespace across every patch version.

Why? Exclusion is a mechanism to **exclude auto-configuration**, not a command to delete arbitrary `@Configuration` classes directly declared by the application. If a class is not an auto-configuration candidate, excluding it targets the wrong thing.

Distinguish these cases:

| Scenario | Explanation |
| --- | --- |
| Name is a valid auto-configuration candidate | Can be removed from the candidate set |
| Name points to a regular `@Configuration` **present** on classpath but not a candidate | Selector may report an invalid exclusion |
| Class name **does not exist** at runtime | Exclusion validation may ignore absent names, which does not prove a candidate was excluded |
| Old class name was renamed or removed | Check imports and compatibility metadata for the current Boot/library version; avoid assuming old names still work |

When upgrading Spring Boot or a starter, check whether auto-configuration names changed; do not blindly copy an exclusions list from an older system.

### 5.1. Scopes That Exclusion Does Not Cover

Excluding via `spring.autoconfigure.exclude` or `excludeName` **does not**:
- Remove the JAR or class from the runtime classpath;
- Prevent the application from defining a bean of the same type itself;
- Guarantee that other auto-configurations will not create a similar bean;
- Cancel a `@Configuration` that the application imports directly via `@Import`;
- Replace conditions such as `@ConditionalOnClass`, `@ConditionalOnProperty`, or `@ConditionalOnMissingBean`.

For example, excluding `DataSourceAutoConfiguration` does not make the JDBC driver vanish; application code can still create a `DataSource` itself. Related configurations requiring `DataSource` may also remain and cause startup failure if you have not handled dependencies.

## 6. Import Filters and Ordering After Merging

In addition to user-specified exclusions, Spring Boot can apply `AutoConfigurationImportFilter` implementations to filter out certain candidates early, typically based on classpath/condition metadata.

**Different filtering operations**:

| Operation | Where It Occurs | Meaning |
| --- | --- | --- |
| `removeDuplicates` | Inside selector | Keeps each candidate name only once in an entry's list |
| `getExclusions` | Inside selector | Collects excluded names from annotations/properties |
| `configurations.removeAll(exclusions)` | Inside selector | Subtracts exclusions from the entry's list |
| `AutoConfigurationImportFilter` | While preparing entry | Quickly filters using metadata before deeply processing each configuration |
| Union + `removeAll(allExclusions)` | Inside group | Prevents a candidate from another entry from “reintroducing” an excluded name |
| `AutoConfigurationSorter` | On remaining set | Sorts by order / before-after metadata |
| `@Conditional` on class/bean | During Spring configuration processing | Decides configuration/bean registration against the actual context |

**Order in the imports file is not the final ordering contract.** After the group merges entries, `AutoConfigurationSorter` applies ordering relationships; when precedence is needed, auto-configurations can use `@AutoConfiguration(before=..., after=...)`, `beforeName`, `afterName`, or corresponding metadata. This ordering mainly governs configuration evaluation and bean definitions, **not bean instance creation order**.

### 6.1. Why Shouldn't You Rely on Alphabetical Class Name Order?

Sorting class names alphabetically or trusting JAR order can break `@ConditionalOnMissingBean` assumptions across configurations. Rely on metadata supported by Boot and test cases where the application provides its own bean.

### 6.2. Distinguishing AutoConfigurationImportFilter from @ConditionalOnMissingBean

For example, an auto-configuration creates a default `CacheClient`:

```java
@Bean
@ConditionalOnMissingBean(CacheClient.class)
CacheClient cacheClient() {
    return new CacheClient();
}
```

This is an **illustrative fragment**, not a standalone Java file. Bean-based conditions need to know the bean definitions already processed, so they should not be described as string comparisons on the candidate list. A library may be validly imported yet its bean is not created because the application already declared a matching bean.

## 7. Java 17 Exercise: Simulating Merging and Deduplication Yourself

To separate the idea of **list aggregation** from the framework, create the following `CandidateMergeDemo.java` file:

```java
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public class CandidateMergeDemo {
    public static void main(String[] args) {
        List<String> candidates = List.of(
                "Alpha", "Beta", "Alpha", "Gamma", "Beta");

        Set<String> unique = new LinkedHashSet<>(candidates);
        System.out.println("unique=" + new ArrayList<>(unique));

        Set<String> exclusions = Set.of("Beta", "Gamma");
        unique.removeAll(exclusions);
        System.out.println("remaining=" + new ArrayList<>(unique));

        List<String> entryOne = List.of("Alpha", "Beta");
        List<String> entryTwo = List.of("Gamma", "Delta");
        Set<String> allExcluded = Set.of("Beta", "Gamma");

        Set<String> merged = new LinkedHashSet<>();
        merged.addAll(entryOne);
        merged.addAll(entryTwo);
        merged.removeAll(allExcluded);
        System.out.println("group=" + new ArrayList<>(merged));
    }
}
```

Run with JDK 17+:

```bash
javac CandidateMergeDemo.java
java CandidateMergeDemo
```

Exact stdout:

```text
unique=[Alpha, Beta, Gamma]
remaining=[Alpha]
group=[Alpha, Delta]
```

Why is this right? `LinkedHashSet` preserves insertion order on first appearance and rejects duplicate names. `removeAll` subtracts the exclusion set. This snippet only simulates the **mathematical part of merging**; real Spring Boot also performs many steps such as reading imports, validating exclusions, filtering metadata, and sorting by dependencies/order. Do not infer that Spring Boot only runs these three lines of set operations.

## 8. Spring Boot Demo: Duplicate Candidates, Exclude, and Conditions Are Three Separate Things

The exercise below uses **Java 17 + Spring Boot 3.3.13 + Maven**. In one project, two auto-configurations are published in imports; one name appears **twice intentionally** to observe that a duplicate name does not produce two beans.

**Note:** When publishing a real library, each candidate name should appear **once** and auto-configuration should be packaged in a separate JAR. The duplicate line here is an experimental setup, not an imports authoring convention.

### 8.1. Project Structure

```text
candidate-merge-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/
    │   │   ├── app/DemoApplication.java
    │   │   └── feature/
    │   │       ├── AlphaFeature.java
    │   │       ├── BetaFeature.java
    │   │       └── autoconfigure/
    │   │           ├── AlphaAutoConfiguration.java
    │   │           └── BetaAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/com/example/app/
            └── AutoConfigurationDiscoveryTest.java
```

The app's package is `com.example.app`, while the two library configurations are in `com.example.feature.autoconfigure`. They are on sibling branches so the app's default component scanning **does not accidentally pick up** the two auto-configurations; they are discovered through the imports resource.

### 8.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
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

    <groupId>com.example</groupId>
    <artifactId>candidate-merge-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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
```

The project needs no web server or database. The Spring Boot parent manages compatible versions in the 3.3 branch. The demo assumes JDK 17+ and Maven 3.x.

### 8.3. Two Simple Types to Observe Beans

`src/main/java/com/example/feature/AlphaFeature.java`

```java
package com.example.feature;

public record AlphaFeature(String name) {
}
```

`src/main/java/com/example/feature/BetaFeature.java`

```java
package com.example.feature;

public record BetaFeature(String name) {
}
```

`record` is supported in Java 17. Both types have no Spring dependencies and are used solely to observe which default beans were registered.

### 8.4. Two Auto-Configuration Classes

`src/main/java/com/example/feature/autoconfigure/AlphaAutoConfiguration.java`

```java
package com.example.feature.autoconfigure;

import com.example.feature.AlphaFeature;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class AlphaAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(AlphaFeature.class)
    AlphaFeature alphaFeature() {
        return new AlphaFeature("alpha");
    }
}
```

`src/main/java/com/example/feature/autoconfigure/BetaAutoConfiguration.java`

```java
package com.example.feature.autoconfigure;

import com.example.feature.BetaFeature;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(after = AlphaAutoConfiguration.class)
@ConditionalOnProperty(
        prefix = "demo.beta",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
public class BetaAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(BetaFeature.class)
    BetaFeature betaFeature() {
        return new BetaFeature("beta");
    }
}
```

`BetaAutoConfiguration` is ordered **after** `AlphaAutoConfiguration` during auto-configuration processing via `@AutoConfiguration(after=...)`; this does not create a requirement that the Beta bean depend on Alpha. `@ConditionalOnProperty` determines whether Beta configuration applies; `@ConditionalOnMissingBean` lets the app replace default beans.

### 8.5. Imports File with an Intentional Duplicate Name

Create at the exact path:

`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

```text
com.example.feature.autoconfigure.AlphaAutoConfiguration
com.example.feature.autoconfigure.BetaAutoConfiguration
com.example.feature.autoconfigure.AlphaAutoConfiguration
```

Meaning:

- There are **three candidate lines**.
- There are **two unique class names**.
- There are no exclusions in the default state.
- `AlphaAutoConfiguration` is declared twice intentionally to demonstrate candidate name deduplication.
- The final list of auto-configurations still goes through filtering, sorting, and condition processing.

If you replace the third line with a differently named class that also creates `AlphaFeature`, it is **no longer** a duplicate-name problem; you must design appropriate bean conditions and ordering.

### 8.6. Application Displaying the Status of Both Beans

`src/main/java/com/example/app/DemoApplication.java`

```java
package com.example.app;

import com.example.feature.AlphaFeature;
import com.example.feature.BetaFeature;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    ApplicationRunner showFeatures(
            ObjectProvider<AlphaFeature> alpha,
            ObjectProvider<BetaFeature> beta) {
        return args -> {
            AlphaFeature a = alpha.getIfAvailable();
            BetaFeature b = beta.getIfAvailable();

            System.out.println("ALPHA=" +
                    (a == null ? "ABSENT" : a.name()));
            System.out.println("BETA=" +
                    (b == null ? "ABSENT" : b.name()));
        };
    }
}
```

`ObjectProvider` prevents the runner from requiring both beans unconditionally; as a result, the application still runs when Beta is excluded or its condition does not match.

Run from the directory containing `pom.xml`:

```bash
mvn test
mvn spring-boot:run
```

The two lines printed by the runner in the default case:

```text
ALPHA=alpha
BETA=beta
```

Boot and Maven startup logs are also printed; these are the **two lines from `ApplicationRunner`**, not the entire stdout.

### 8.7. Exclusion Actually Removes the Candidate

Re-run from the project:

```bash
mvn spring-boot:run -Dspring-boot.run.arguments=--spring.autoconfigure.exclude=com.example.feature.autoconfigure.BetaAutoConfiguration
```

Two lines from the runner:

```text
ALPHA=alpha
BETA=ABSENT
```

We did not delete `BetaAutoConfiguration.class` or `BetaFeature.class` from the JAR. They remain on the classpath, but the name `BetaAutoConfiguration` is removed from the auto-configuration set for this context.

You can switch from the property control to:

```java
@SpringBootApplication(excludeName =
        "com.example.feature.autoconfigure.BetaAutoConfiguration")
```

This is a **replacement annotation line for the old annotation in `DemoApplication`**, not a standalone file. If you edit the source this way, remember to remove `excludeName` after the experiment to return to the default state.

### 8.8. Non-Matching Condition Has the Same Bean Result but a Different Cause

Run:

```bash
mvn spring-boot:run -Dspring-boot.run.arguments=--demo.beta.enabled=false
```

The runner also prints:

```text
ALPHA=alpha
BETA=ABSENT
```

The difference: **Beta can still be selected as a candidate and imported**, but `@ConditionalOnProperty` causes Spring not to apply this configuration. This is not a list-level exclusion. The way to diagnose is to inspect the **condition report**, rather than assuming the two commands are identical because the app stdout looks identical.

### 8.9. Reading the Condition Report to Distinguish

```bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
```

With the disabling property or exclusion, look for entries related to `BetaAutoConfiguration` in the report:

- **Exclusions** reflect auto-configuration names removed by exclusion.
- **Negative matches** reflect configurations/conditions that did not match.
- **Positive matches** reflect conditions that matched.
- **Unconditional classes** may list configurations without corresponding conditions at the report level.

Output can vary by Boot version and the auto-configurations on the classpath. Do not use an assumed log sample as the sole basis; look at the actual cause from conditions/exclusions.

## 9. Testing Context Behavior: No Duplicate Beans and Handling Exclusions

Create `src/test/java/com/example/app/AutoConfigurationDiscoveryTest.java`:

```java
package com.example.app;

import com.example.feature.AlphaFeature;
import com.example.feature.BetaFeature;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class AutoConfigurationDiscoveryTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(DemoApplication.class);

    @Test
    void duplicateCandidateNameDoesNotCreateDuplicateBean() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(AlphaFeature.class);
            assertThat(context).hasSingleBean(BetaFeature.class);
            assertThat(context.getBean(AlphaFeature.class).name())
                    .isEqualTo("alpha");
        });
    }

    @Test
    void exclusionRemovesAutoConfigurationFromSelection() {
        runner.withPropertyValues(
                "spring.autoconfigure.exclude="
                        + "com.example.feature.autoconfigure.BetaAutoConfiguration")
                .run(context -> {
                    assertThat(context).hasSingleBean(AlphaFeature.class);
                    assertThat(context).doesNotHaveBean(BetaFeature.class);
                });
    }

    @Test
    void propertyConditionCanSkipBetaWithoutExcludingIt() {
        runner.withPropertyValues("demo.beta.enabled=false")
                .run(context -> {
                    assertThat(context).hasSingleBean(AlphaFeature.class);
                    assertThat(context).doesNotHaveBean(BetaFeature.class);
                });
    }
}
```

Run:

```bash
mvn test
```

**What the tests prove:** A context using the real app still creates exactly one `AlphaFeature`, can skip Beta via exclude, and can skip Beta via a property condition. The first test is behavioral output evidence; **having only one bean does not by itself prove which exact line of code in the selector removed the duplicate name**, because `@ConditionalOnMissingBean` also helps guard the bean. To verify the deduplication algorithm, inspect the `removeDuplicates`/`AutoConfigurationGroup.selectImports` source for the version in use.

Unlike a runner configured directly with:

```java
.withConfiguration(AutoConfigurations.of(AlphaAutoConfiguration.class))
```

the runner in this lesson **uses `DemoApplication.class` with `@SpringBootApplication`**, meaning it preserves the `@EnableAutoConfiguration` path and resource discovery mechanism. Passing `AutoConfigurations.of(...)` directly is useful for testing an auto-configuration's conditions, but **bypasses part of candidate discovery from imports**, so it is not the only test to run when studying the selector.

### 9.1. Checking the Imports File When Packaging

```bash
mvn package
jar tf target/candidate-merge-demo-0.0.1-SNAPSHOT.jar
```

In the executable JAR packaged by the Boot Maven plugin, the resource is expected under:

```text
BOOT-INF/classes/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

In a regular library JAR, the resource resides at `META-INF/spring/...`. An artifact missing the file or having a wrong class name can prevent applications from receiving the auto-configuration even though the Java class compiled.

### 9.2. Experiment: Adding an Application-Defined Bean

To separate candidate deduplication from bean back-off, add inside **`DemoApplication`**:

```java
@Bean
AlphaFeature applicationAlphaFeature() {
    return new AlphaFeature("custom");
}
```

This is an addition to the existing class, not a new Java file. When running the app with defaults, the output becomes:

```text
ALPHA=custom
BETA=beta
```

Because `AlphaAutoConfiguration` has `@ConditionalOnMissingBean(AlphaFeature.class)`, it yields to the app's bean. This scenario proves the **back-off when a bean already exists** mechanism, completely different from two imports lines having the same FQCN.

If you add this method before running the first test, the test checking the `alpha` value will need adjusting to match the test goal; run the original tests first, then experiment with customizing the bean.

## 10. Analyzing Multiple Exclusion Sources and Merging Scenarios

Some phenomena become clear only when examining multiple entries, multiple config sources, or multiple library versions.

### 10.1. An Exclusion from One Entry Affects the Whole Group

Suppose:

```text
Import group:
  E1 configurations=[A, B], exclusions=[C]
  E2 configurations=[B, C], exclusions=[B]

Configurations before shared subtraction = [A, B, C]
Shared exclusions set                    = {B, C}
Result before sorting                    = [A]
```

In this case, do not conclude “E2 still has C so C must be imported”: the group removes `C` due to the exclusion from E1. This is an example of the **group's merging and exclusion** mechanism, not a requirement to always create multiple `@EnableAutoConfiguration` declarations in an application.

### 10.2. Duplicate Candidates Do Not Necessarily Mean Two Broken Imports Resources

A class can appear in imports across multiple JARs, or repeat within the same resource. At the selection layer, Boot deduplicates by FQCN. However, **packaging the same class bytecode across multiple JARs can still be a dependency conflict** and must be resolved separately in the dependency graph. Name deduplication in the selector does not solve which class the classloader loads when multiple JARs compete over the same binary name.

### 10.3. Ordering After Merging

Suppose config A declares it runs `after` B; even if raw candidates from imports have order `[A, B]`, the sorter can choose `[B, A]`. Do not use “first appearance” from `LinkedHashSet` as the final configuration ordering contract. Publish `@AutoConfiguration(after=...)` metadata and test bean conditions if that ordering matters.

### 10.4. An Excluded Auto-Configuration Can Leave Behind a Bean from Elsewhere

If you exclude `FooAutoConfiguration` yet the application still has a `Foo` bean, it could be that:
- The application declares `@Bean Foo` itself;
- Another auto-configuration creates a `Foo` bean;
- Component scanning is picking up a `@Component Foo`;
- A test configuration/other `@Import` brought the bean into the context.

Therefore, **exclusion is not equivalent to guaranteeing the absence of a bean by type**. You must trace the actual source of the bean definition.

## 11. Diagnostic Workflow When the Candidate List Causes Confusion

When “excluded yet the bean remains”, “configuration not seen”, or “same library creates beans inconsistently”, follow this order:

1. **Check the exact runtime JARs.** With Maven use `mvn dependency:tree`; with Gradle use `runtimeClasspath`/`dependencyInsight`. Do not look only at the test classpath.
2. **Check imports in the artifact.** Inspect `jar tf` on the actual JAR and the contents of `AutoConfiguration.imports`; names must be fully qualified and the resource at the right path.
3. **Check where auto-configuration is enabled.** Does the application have `@EnableAutoConfiguration` (typically via `@SpringBootApplication`), or was `spring.boot.enableautoconfiguration` turned off?
4. **List exclusions from the right sources.** Check `exclude`, `excludeName`, `spring.autoconfigure.exclude`, and effective properties after precedence.
5. **Classify exclusion errors.** If Boot reports a class is not an auto-configuration, check whether that class is in candidate imports and matches the runtime version.
6. **Check import filters and classpath conditions.** Missing optional classes, missing resources, or incompatible versions can cause a candidate to be filtered or a configuration not to match.
7. **Inspect the condition report.** Use `--debug` to distinguish Exclusions from Negative matches; read the specific reason.
8. **Trace the actual bean.** If a bean still exists after exclusion, find the bean definition from the application, component scan, or another auto-configuration.
9. **Verify ordering.** For two auto-configurations relying on `@ConditionalOnMissingBean`, specify `before/after` and needed conditions rather than relying on incidental imports order.
10. **Test a real consumer.** Test bean creation, no duplicates, exclusion, property disable, custom bean, and also inspect the resource inside the JAR.

Remember: **distinguish what is eliminated at the selection layer from what is blocked at the condition/bean layer.**

## 12. Common Misconceptions and Fixes

| Misconception | Why It Is Wrong | How to Fix |
| --- | --- | --- |
| “Each imports line guarantees one bean” | Imports publishes configuration classes, not beans | Trace selection then conditions |
| “Duplicate names guarantee creating two beans” | Selector and group deduplicate FQCNs; beans also depend on conditions | Check whether name or bean type is duplicated |
| “Deduplication preserves imports order forever” | Group has a metadata sorting step | Use `before/after` when order matters |
| “Every exclusion wins by deleting the bean” | Exclusion only removes the corresponding auto-configuration | Trace other places registering the bean |
| “Excluding regular classes works too” | Selector validates that excluded classes are valid | Only exclude auto-configuration candidates |
| “`@ConditionalOnProperty` is an exclusion” | It is a condition during configuration processing | Check Negative matches, not just Exclusions |
| “`@ConditionalOnMissingBean` runs while merging name strings” | Bean conditions need context bean definitions | Separate the two phases |
| “Each JAR gets its own selector and creates separate beans” | Multiple resources contribute candidates into the selector/group | Observe the combined candidate set |
| “Renaming a configuration does not affect old exclusions” | Exclusions depend on exact class names | Check versions, resources, and migration metadata |
| “`spring.autoconfigure.exclude` removes the dependency too” | The class/JAR remains on the classpath | Use the build tool to change the dependency graph |
| “Same FQCN from two JARs with different bytecode is harmless” | Name dedup does not fix classpath conflicts | Remove duplicate JARs and test at runtime |

## 13. Self-Check

**Question 1.** Candidate list is `[A, B, A, C, B]`, exclude `B`. What is the result before import filters and sorting?

**Answer:** After dedup it is `[A, B, C]`; subtracting `B` leaves `[A, C]`.

**Question 2.** Within the same group, entry 1 contributes A and B; entry 2 contributes B and C but has exclusion A. Does A come back because entry 1 contributed it?

**Answer:** No. The group merges configurations and removes the **shared exclusions set** before sorting/importing. Only B and C remain.

**Question 3.** A JAR declares the same `FooAutoConfiguration` on two lines in imports. Must Boot instantiate two instances of the `Foo` bean?

**Answer:** No. Duplicate candidate names are removed during selection. Moreover, the final bean count is still governed by `@Bean` and `@Conditional`.

**Question 4.** `BarAutoConfiguration` is excluded, yet the application still has `BarClient`. Is that a contradiction?

**Answer:** Not necessarily. The bean may be created by the application, scanning, or another configuration. Exclusion only removes the named auto-configuration.

**Question 5.** Is a non-matching `@ConditionalOnProperty` the same as `spring.autoconfigure.exclude`?

**Answer:** No. A property condition is evaluated while processing the configuration; exclusion acts on the candidate list before import.

**Question 6.** Why must deduplication in the selector be distinguished from deduplication in the group?

**Answer:** The selector normalizes each entry; the group also merges multiple entries, subtracts all shared exclusions, and sorts before importing. Looking at only one entry can miss the effect of an exclusion contributed by another entry.

**Question 7.** Should you rely on imports line order to ensure `@ConditionalOnMissingBean` behaves as intended?

**Answer:** No. The group has a sorter and ordering metadata. Declare explicit ordering with `before/after` when needed, and test cases where the app provides its own bean.

## 14. Key Takeaways

Three main transformations to distinguish:

```text
1. DEDUP       [A, B, A, C]       -> [A, B, C]
2. EXCLUDE     [A, B, C] - {B}    -> [A, C]
3. GROUP       union(entries) - union(exclusions) -> sort -> import
```

The operations above only select **auto-configuration classes**. Afterward, Spring evaluates conditions on classes and `@Bean` methods, registers qualifying bean definitions, and creates beans per lifecycle. This is the right mental model when a starter is on the classpath yet a bean does not appear, or when an exclusion is active yet a bean of the same type still exists.

### References

- Spring Boot 3.3 API — `AutoConfigurationImportSelector`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurationImportSelector.html
- Spring Boot 3.3 — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 — Using Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html
- Spring Framework — `DeferredImportSelector`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/DeferredImportSelector.html
- Java 17 — `LinkedHashSet`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html
