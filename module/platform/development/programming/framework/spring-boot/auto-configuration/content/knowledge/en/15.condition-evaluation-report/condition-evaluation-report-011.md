# Comparing the Condition Evaluation Report Before and After Changing Dependencies, Properties, or Beans

## 1. What Questions Does the Condition Evaluation Report Answer?

Spring Boot uses conditions to decide whether a configuration or bean should be applied. Common annotations include:

- `@ConditionalOnClass`: whether required classes are on the classpath.
- `@ConditionalOnProperty`: whether a property exists and has a matching value.
- `@ConditionalOnBean`: whether a matching bean has already been registered.
- `@ConditionalOnMissingBean`: whether a bean already exists to replace the default.
- `@ConditionalOnSingleCandidate`: whether a single candidate can be resolved for injection by type.
- `@ConditionalOnWebApplication` / `@ConditionalOnNotWebApplication`: whether the ApplicationContext is recognized as a web context.

The **Condition Evaluation Report** records the evaluation results of conditions on configurations and auto-configurations, along with reasons for matching or not matching. It helps answer:

1. Why was an auto-configuration applied or skipped?
2. Why was a `@Bean` method registered or not registered?
3. When changing a dependency, property, or bean, which conditions changed state?
4. Did a change cause a dependent bean to disappear or trigger another fallback?

The report is a **startup snapshot** of one ApplicationContext. It is not a change history and does not automatically generate a diff between two runs. To compare before and after, save two separate reports and compare the relevant entries.

## 2. Two Ways to Obtain the Report in Spring Boot

### 2.1. Enabling `--debug` at Startup

For a Spring Boot application, add the `--debug` flag:

```bash
java -jar target/app.jar --debug
```

Spring Boot prints **CONDITIONS EVALUATION REPORT** in the startup logs. The report is typically divided into:

- **Positive matches**: configurations or beans whose conditions matched.
- **Negative matches**: configurations or beans with at least one condition that did not match; details show which conditions did not match and which matched.
- **Exclusions**: excluded auto-configurations.
- **Unconditional classes**: configurations applied without conditions.

`--debug` does not mean enabling remote JVM debugging or opening a debugger; it turns on Spring Boot's debug mode to print extra diagnostics, including the condition report.

This fits quick local diagnostics, CI, or processes without an HTTP server. If the log is long, search for the relevant auto-configuration class or `@Bean` method name instead of reading the entire report.

### 2.2. Using the Actuator Endpoint `/actuator/conditions`

If the application includes Spring Boot Actuator and runs a web server, you can fetch the report in JSON format via the `conditions` endpoint.

Add the dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

Configure endpoint exposure in `application.properties`:

```properties
management.endpoints.web.exposure.include=health,conditions
```

Start the web application, then call:

```bash
curl -s http://localhost:8080/actuator/conditions
```

The endpoint returns the report for the ApplicationContexts. Primary structure:

```json
{
  "contexts": {
    "application": {
      "positiveMatches": {
        "SomeAutoConfiguration#someBean": [
          {
            "condition": "OnPropertyCondition",
            "message": "@ConditionalOnProperty ... matched"
          }
        ]
      },
      "negativeMatches": {
        "AnotherAutoConfiguration#anotherBean": {
          "notMatched": [
            {
              "condition": "OnBeanCondition",
              "message": "@ConditionalOnBean ... did not find any beans"
            }
          ],
          "matched": []
        }
      },
      "unconditionalClasses": []
    }
  }
}
```

This is an **abbreviated illustrative shape**, not verbatim JSON from a specific application. Actual reports have many classes, conditions, and environment-dependent messages.

Notable fields:

| Field | Meaning |
| --- | --- |
| `contexts` | Reported ApplicationContexts, by id |
| `positiveMatches` | Sources whose conditions matched |
| `negativeMatches` | Sources with unmatched conditions |
| `notMatched` | Unsatisfied conditions in that source |
| `matched` | Other conditions still satisfied in the same source |
| `unconditionalClasses` | Configuration classes requiring no conditions |
| `parentId` | Parent context id, if any |

Keys in `positiveMatches`/`negativeMatches` are usually configuration class names or `ClassName#beanMethod`. This is how you locate the exact bean method to compare.

**Note:** the endpoint must be enabled, exposed, and permitted. Only expose `conditions` in appropriate environments, and protect the endpoint with Spring Security or restrict the management network per operational policy; the report can reveal class names, beans, dependencies, and configuration conditions. If you do not want to expose an HTTP endpoint, use `--debug`.

## 3. Reading the Report by Condition Type

### 3.1. Changing Dependencies: `OnClassCondition`

`@ConditionalOnClass` checks whether one or more classes can be loaded from the classpath. When adding or removing a dependency, related conditions can flip:

- Dependency has the required class: class-level condition can match.
- Dependency removed from runtime classpath: condition does not match, and the configuration guarded by the annotation may not apply.
- Beans inside that configuration may disappear; other conditions depending on those beans can change as well.

In the report, find `OnClassCondition` and messages stating which classes were found or missing. Distinguish **dependencies on the compile classpath** from **dependencies on the runtime classpath**: a running application requires classes to be present on the process's runtime classpath.

Do not look only at `pom.xml`. Inspect the actual dependency graph and dependency scopes:

```bash
mvn dependency:tree
mvn dependency:tree -Dincludes=com.example:optional-library
```

If using Gradle, inspect `runtimeClasspath`, for instance:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

A dependency declared as `test` or `provided` may not be present at runtime as the application needs. Version conflicts or transitive exclusions can also make a class vanish even though another dependency is still declared.

### 3.2. Changing Properties: `OnPropertyCondition`

`@ConditionalOnProperty` checks properties in `Environment`. When changing configuration files, profiles, environment variables, or command-line arguments, conditions can flip between positive and negative.

Example:

```java
@Bean
@ConditionalOnProperty(
        prefix = "demo.feature",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false)
public FeatureService featureService() {
    return new FeatureService("enabled");
}
```

With this configuration:

```properties
demo.feature.enabled=true
```

the condition matches; with `false` or a missing property, the method is not registered. Because `matchIfMissing=false`, a missing property is not treated as enabling the feature.

When comparing, record **the actual value the application received**, not just the contents of one `application.properties` file. Properties can be overridden by profiles, environment variables, command-line arguments, config imports, or higher-precedence configuration sources.

In the report, locate `OnPropertyCondition` and read the property name, expected value, received value, or reason the property was missing. If the message says the property was not found, verify the exact name, prefix, active profiles, and property source order.

### 3.3. Changing Beans: `OnBeanCondition`

`@ConditionalOnBean`, `@ConditionalOnMissingBean`, and `@ConditionalOnSingleCandidate` belong to bean-based conditions. When adding or replacing beans in an application, multiple entries can change:

- `@ConditionalOnBean`: switches from no-match to match when a matching bean is registered.
- `@ConditionalOnMissingBean`: the default can switch from match to no-match when the application provides a custom bean.
- `@ConditionalOnSingleCandidate`: can match with one bean or multiple beans with a single primary; may not match if multiple beans lack a unique primary.

Default example:

```java
@Bean
@ConditionalOnMissingBean(FoundationClient.class)
public FoundationClient foundationClient() {
    return () -> "default";
}
```

If the user adds a custom `FoundationClient`, the default's condition no longer matches. Another consumer with `@ConditionalOnBean(FoundationClient.class)` can still match and use the custom bean.

When comparing reports, do not conclude “the feature disappeared” just because the default provider is no longer registered. Check whether **the custom bean fulfills the right contract** and whether downstream consumers still appear.

Bean conditions are evaluated based on bean definitions processed up to that point. If the provider is another auto-configuration, processing order may require `@AutoConfiguration(after = ...)` metadata. The report helps spot when a consumer fails to see a bean because the provider was not registered yet, was excluded, or failed another condition.

## 4. Workflow for Comparing Before and After a Change

A reliable comparison requires holding other factors constant. Do not change dependencies, properties, and beans simultaneously and then try to guess which factor caused the result.

### Step 1 — Lock Down the Baseline

Before making changes, record:

- The commit or source version currently running.
- Spring Boot version, JDK version, and active profiles.
- Runtime dependency graph or artifact file.
- Command-line arguments and relevant properties.
- Which custom beans are registered.
- The original condition report.

Name files after the change and time, e.g., `conditions-baseline.json`. If using `--debug`, save full startup logs so you can trace back sources and messages.

### Step 2 — Change Only One Variable

Pick exactly one change category:

- **Dependency:** add/remove/upgrade one library, keeping properties and beans unchanged.
- **Property:** change one property, keeping dependencies and beans unchanged.
- **Bean:** add a custom bean, remove a custom bean, or swap an implementation, keeping dependencies and properties unchanged.

For dependency changes, rebuild the artifact after updating the dependency graph. For property or bean changes, use the same artifact if the source did not change.

### Step 3 — Restart and Capture the Post-Change Report

Conditions are evaluated during context startup. Therefore, you must start **a fresh ApplicationContext** after the change. Save the second report, for instance `conditions-after-property.json`.

Do not treat editing a property in an open file or registering a bean after the context has refreshed as equivalent to a fresh condition evaluation. For an accurate comparison, stop the old process and restart with the new configuration.

### Step 4 — Compare the Right Sources

Focus on the relevant entries:

1. Provider auto-configuration.
2. Bean method creating the foundation bean.
3. Consumer auto-configuration.
4. Dependent feature bean method.
5. Other downstream consumers using the foundation/feature bean.

For each source, compare:

- Is it in positive or negative matches?
- Which conditions matched or did not match?
- How did the message change?
- Does the actual bean exist after startup?
- Did any fallback or consumer disappear along with it?

Do not merely count total positive/negative matches across the entire application. A new dependency can cause many unrelated auto-configurations to change state; most of those changes are irrelevant to the feature under investigation.

### Step 5 — Verify with Bean Registry and Behavior

The report explains **why conditions were evaluated that way**. It does not fully prove business functionality works correctly.

After identifying condition changes, inspect actual beans using `ApplicationContext.getBeansOfType(...)`, `ApplicationContextRunner`, or Actuator `/actuator/beans` if the appropriate endpoint is enabled. Finally, run tests/integration tests for dependent requests, jobs, or business flows.

## 5. Spring Boot 3.3.5 / Java 17+ Example Creating All Three Change Types

This example has three independent axes:

1. **Dependency:** the feature auto-configuration is only active when `org.h2.Driver` is on the runtime classpath.
2. **Property:** the feature bean is only created when `demo.feature.enabled=true`.
3. **Bean:** the application can supply a custom `FoundationClient`; when it does, the default client backs off and the feature uses the custom client.

We use the Actuator endpoint to save JSON reports before and after. The same source structure lets you observe each condition change.

### 5.1. Directory Structure

```text
condition-report-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── api/
    │   │   │   ├── FoundationClient.java
    │   │   │   └── FeatureService.java
    │   │   ├── app/
    │   │   │   └── DemoApplication.java
    │   │   └── autoconfigure/
    │   │       ├── FoundationClientAutoConfiguration.java
    │   │       └── FeatureAutoConfiguration.java
    │   └── resources/
    │       ├── application.properties
    │       └── META-INF/spring/
    │           └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/java/demo/app/
        └── ConditionChangeTests.java
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
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>condition-report-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
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

`spring-boot-starter-web` provides the web server to call Actuator over HTTP. H2 acts solely as a **dependency marker** for the classpath condition example; the program does not connect to a database. When you remove the H2 dependency and rebuild, the feature auto-configuration will fail the classpath condition.

### 5.3. `src/main/resources/application.properties`

```properties
management.endpoints.web.exposure.include=health,conditions
server.port=8080
```

In this local example, the `conditions` endpoint is exposed for easy observation. In real deployments, only open the endpoint to authorized operations teams.

### 5.4. `src/main/java/demo/api/FoundationClient.java`

```java
package demo.api;

public interface FoundationClient {
    String id();
}
```

### 5.5. `src/main/java/demo/api/FeatureService.java`

```java
package demo.api;

public record FeatureService(String description) {
}
```

### 5.6. Provider: `FoundationClientAutoConfiguration`

File `src/main/java/demo/autoconfigure/FoundationClientAutoConfiguration.java`:

```java
package demo.autoconfigure;

import demo.api.FoundationClient;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class FoundationClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(FoundationClient.class)
    public FoundationClient foundationClient() {
        return () -> "default";
    }
}
```

The report will show whether the default bean was registered because no `FoundationClient` was found, or skipped because the application already supplied a custom bean.

### 5.7. Consumer: `FeatureAutoConfiguration`

File `src/main/java/demo/autoconfigure/FeatureAutoConfiguration.java`:

```java
package demo.autoconfigure;

import demo.api.FeatureService;
import demo.api.FoundationClient;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(after = FoundationClientAutoConfiguration.class)
@ConditionalOnClass(name = "org.h2.Driver")
public class FeatureAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "demo.feature",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false)
    @ConditionalOnBean(FoundationClient.class)
    public FeatureService featureService(FoundationClient client) {
        return new FeatureService("enabled:" + client.id());
    }
}
```

There are three decision layers:

- `@ConditionalOnClass` at the class level: only process the feature configuration if H2 is present.
- `@ConditionalOnProperty` at the bean level: only register the feature when the property is enabled.
- `@ConditionalOnBean` at the bean level: requires a matching foundation client.

`after` ensures the provider auto-configuration is processed before the consumer so bean conditions see the bean definition created by the provider. It cannot recreate the provider if the provider was excluded or did not match.

### 5.8. Main Application: `DemoApplication`

File `src/main/java/demo/app/DemoApplication.java`:

```java
package demo.app;

import demo.api.FeatureService;
import demo.api.FoundationClient;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    @Bean
    @ConditionalOnProperty(
            prefix = "demo",
            name = "client",
            havingValue = "custom")
    public FoundationClient customFoundationClient() {
        return () -> "custom";
    }

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(DemoApplication.class, args)) {

            FoundationClient client =
                    context.getBeanProvider(FoundationClient.class)
                            .getIfAvailable();

            FeatureService feature =
                    context.getBeanProvider(FeatureService.class)
                            .getIfAvailable();

            System.out.println("client=" +
                    (client == null ? "none" : client.id()));

            System.out.println("feature=" +
                    (feature == null ? "disabled" : feature.description()));
        }
    }
}
```

The custom bean only appears when `demo.client=custom`. When it does, the provider's `@ConditionalOnMissingBean` yields to the application-provided bean.

### 5.9. Registering Auto-Configurations

File `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`:

```text
demo.autoconfigure.FeatureAutoConfiguration
demo.autoconfigure.FoundationClientAutoConfiguration
```

Put the consumer before the provider in the file to demonstrate `after` metadata controlling auto-configuration application order. In real projects, class names must match exactly.

## 6. Capturing Reports and Comparing Four States

Build:

```bash
mvn -q test
mvn -q -DskipTests package
```

Start the application in one terminal; use another terminal to call the endpoint and save the JSON. After each capture, stop the process with Ctrl+C and restart with a new set of arguments.

### State A — Baseline: Dependency Present, Property Enabled, Using Default Bean

Start:

```bash
java -jar target/condition-report-demo-0.0.1-SNAPSHOT.jar --demo.feature.enabled=true
```

Save report:

```bash
curl -s http://localhost:8080/actuator/conditions -o conditions-baseline.json
```

Two lines printed by the program:

```text
client=default
feature=enabled:default
```

Outcomes to look for in the report:

- `FeatureAutoConfiguration` has a positive match for `OnClassCondition` because `org.h2.Driver` is on the runtime classpath.
- `FeatureAutoConfiguration#featureService` has a positive match for `OnPropertyCondition` because the property is enabled.
- `FeatureAutoConfiguration#featureService` has a positive match for `OnBeanCondition` because `FoundationClient` was registered.
- `FoundationClientAutoConfiguration#foundationClient` has a positive match for `OnBeanCondition` of `@ConditionalOnMissingBean` because no custom client exists yet.

### State B — Only Disable the Property

Stop the application, restart the same JAR with the same dependencies:

```bash
java -jar target/condition-report-demo-0.0.1-SNAPSHOT.jar --demo.feature.enabled=false
```

Save report:

```bash
curl -s http://localhost:8080/actuator/conditions -o conditions-property-off.json
```

Application output:

```text
client=default
feature=disabled
```

When comparing against baseline:

- Class-level `OnClassCondition` still matches because H2 is unchanged.
- Default provider is still present.
- `FeatureAutoConfiguration#featureService` switches to negative match because `OnPropertyCondition` is not satisfied.
- Consumer is not registered; this is **an intentionally disabled feature**, not a bean initialization error.

### State C — Only Add a Custom Bean

Stop the application, re-enable the feature, and add the property for the custom client:

```bash
java -jar target/condition-report-demo-0.0.1-SNAPSHOT.jar --demo.feature.enabled=true --demo.client=custom
```

Save report:

```bash
curl -s http://localhost:8080/actuator/conditions -o conditions-custom-bean.json
```

Application output:

```text
client=custom
feature=enabled:custom
```

When comparing against baseline:

- `OnClassCondition` still matches.
- `OnPropertyCondition` still matches.
- `FoundationClientAutoConfiguration#foundationClient` no longer creates the default because `@ConditionalOnMissingBean` found the custom bean.
- `FeatureAutoConfiguration#featureService` still matches `@ConditionalOnBean` and uses the custom client.

This is an important example: **the default provider switches from positive to negative match while the consumer remains positive**. Do not treat every negative match as an error; the default backing off is expected behavior.

### State D — Only Remove the H2 Dependency

Return to baseline properties (`demo.feature.enabled=true`, do not declare `demo.client=custom`). Remove the H2 dependency from `pom.xml`:

```xml
<!-- Remove this dependency from pom.xml -->
<dependency>
    <groupId>com.h2database</groupId>
    <artifactId>h2</artifactId>
    <scope>runtime</scope>
</dependency>
```

Rebuild the artifact:

```bash
mvn -q -DskipTests clean package
mvn dependency:tree -Dincludes=com.h2database:h2
```

Verify the dependency is gone from the runtime dependency graph. Restart with the same baseline properties:

```bash
java -jar target/condition-report-demo-0.0.1-SNAPSHOT.jar --demo.feature.enabled=true
```

Save report:

```bash
curl -s http://localhost:8080/actuator/conditions -o conditions-no-h2.json
```

Output:

```text
client=default
feature=disabled
```

When comparing:

- `FeatureAutoConfiguration` switches to negative match because `OnClassCondition` cannot find `org.h2.Driver`.
- Method conditions inside the class are not processed as they are when the class-level condition matches; do not expect a separate negative entry for `featureService`.
- `FoundationClientAutoConfiguration` does not depend on H2, so the default client remains present.
- The consumer feature is not registered because the entire feature auto-configuration was skipped.

Note: H2 in this example is solely a dependency marker, not a connected database. Removing H2 does not make the client provider disappear; it only removes the feature branch guarded by the classpath condition.

### 6.1. Comparison Matrix

| State | H2 on Classpath | `demo.feature.enabled` | Selected Client | Feature |
| --- | --- | --- | --- | --- |
| A. Baseline | Yes | true | default | enabled:default |
| B. Property off | Yes | false | default | disabled |
| C. Custom bean | Yes | true | custom | enabled:custom |
| D. Dependency off | No | true | default | disabled |

The matrix shows each change affects a different condition. In real applications, a dependency change can also affect multiple other auto-configurations; inspect related sources rather than looking at a single summary line.

## 7. Comparing Two JSON Reports with PowerShell

Actuator reports contain dynamic JSON objects keyed by source name. Use PowerShell to pull the entry for a specific source without reading the entire report:

```powershell
$before = Get-Content .\conditions-baseline.json -Raw | ConvertFrom-Json
$after = Get-Content .\conditions-property-off.json -Raw | ConvertFrom-Json

$source = 'FeatureAutoConfiguration#featureService'

'--- BEFORE: positive ---'
$before.contexts.application.positiveMatches.PSObject.Properties[$source].Value |
    ConvertTo-Json -Depth 20

'--- BEFORE: negative ---'
$before.contexts.application.negativeMatches.PSObject.Properties[$source].Value |
    ConvertTo-Json -Depth 20

'--- AFTER: positive ---'
$after.contexts.application.positiveMatches.PSObject.Properties[$source].Value |
    ConvertTo-Json -Depth 20

'--- AFTER: negative ---'
$after.contexts.application.negativeMatches.PSObject.Properties[$source].Value |
    ConvertTo-Json -Depth 20
```

Change the input filenames and `$source` to compare `conditions-custom-bean.json` or `conditions-no-h2.json`. If a source is missing from both positive and negative sections of a report, the configuration class may not have been processed because its class-level condition did not match; inspect the class-level entry `FeatureAutoConfiguration`.

An effective way to summarize findings is a small table:

| Source | Before | After | Interpretation |
| --- | --- | --- | --- |
| `FeatureAutoConfiguration` | Positive OnClass | Negative OnClass | Dependency marker disappeared |
| `FeatureAutoConfiguration#featureService` | Positive property + bean | Negative property | Feature disabled via property |
| `FoundationClientAutoConfiguration#foundationClient` | Positive missing-bean | Negative missing-bean | Default backed off for custom bean |

These are **per-scenario comparison examples**. Actual entries depend on the exact source, version, and runtime environment. Do not copy messages from another report version and treat them as fixed output.

## 8. Testing Condition Behavior with `ApplicationContextRunner`

The report explains, while tests protect the auto-configuration's contract. Create `src/test/java/demo/app/ConditionChangeTests.java`:

```java
package demo.app;

import demo.api.FeatureService;
import demo.api.FoundationClient;
import demo.autoconfigure.FeatureAutoConfiguration;
import demo.autoconfigure.FoundationClientAutoConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class ConditionChangeTests {

    private ApplicationContextRunner runner(String... properties) {
        return new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        FoundationClientAutoConfiguration.class,
                        FeatureAutoConfiguration.class))
                .withPropertyValues(properties);
    }

    @Test
    void enabledFeatureUsesDefaultClient() {
        runner("demo.feature.enabled=true").run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(FoundationClient.class);
            assertThat(context).hasSingleBean(FeatureService.class);
            assertThat(context.getBean(FeatureService.class).description())
                    .isEqualTo("enabled:default");
        });
    }

    @Test
    void disabledPropertyRemovesOnlyFeature() {
        runner("demo.feature.enabled=false").run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(FoundationClient.class);
            assertThat(context).doesNotHaveBean(FeatureService.class);
        });
    }

    @Test
    void customClientReplacesDefaultAndFeatureStillWorks() {
        runner("demo.feature.enabled=true")
                .withBean(FoundationClient.class, () -> () -> "custom")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(FoundationClient.class);
                    assertThat(context).hasSingleBean(FeatureService.class);
                    assertThat(context.getBean(FeatureService.class)
                            .description())
                            .isEqualTo("enabled:custom");
                });
    }

    @Test
    void missingFoundationPreventsFeatureRegistration() {
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        FeatureAutoConfiguration.class))
                .withPropertyValues("demo.feature.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(FoundationClient.class);
                    assertThat(context).doesNotHaveBean(FeatureService.class);
                });
    }
}
```

Run tests:

```bash
mvn -q test
```

Four tests verify behavior when the property is enabled/disabled, when a custom bean replaces the default, and when the provider is absent. H2 is on the test runtime classpath due to the dependency in `pom.xml`; if you want to test a negative classpath condition, add a test using Spring Boot Test's `FilteredClassLoader` to hide `org.h2.Driver`. The build/run commands in scenario D further verify removing the dependency from the actual artifact.

## 9. Common Mistakes When Reading and Comparing Reports

1. **Treating the report as an automatic diff.** It is not: each report describes a single startup. You must save before/after snapshots and compare matching sources.
2. **Changing multiple factors at once.** When dependencies, properties, and beans all change together, you cannot tell which condition caused the shift. Change one factor at a time.
3. **Looking at only one condition and ignoring others on the same source.** A bean may require both property and bean conditions; all applicable conditions must pass.
4. **Confusing class-level negative match with method-level negative match.** If a class-level condition fails, the configuration may be skipped before method conditions are evaluated.
5. **Treating a negative match as an error.** `@ConditionalOnMissingBean` not matching because a custom bean exists is usually intentional back-off.
6. **Reading only property files without checking runtime values.** Profiles, environment variables, command-line arguments, and config imports can override values.
7. **Looking at declared dependencies without checking the runtime graph.** Scopes, exclusions, version conflicts, and transitive dependencies can prevent a class from appearing on the runtime classpath.
8. **Assuming bean conditions count objects after initialization.** Conditions are evaluated during configuration processing based on known bean definitions, not after each request.
9. **Checking only the report without checking actual beans.** A condition match does not prove business functionality works; verify the bean registry and execution flow.
10. **Comparing reports from different environments.** Profiles, JDK, Boot version, OS, environment variables, classpath, and command line can flip many conditions. Normalize the environment before drawing conclusions.

## 10. Checklist for Investigating a Change

When reviewing a PR that changes dependencies, properties, or beans, follow in order:

- [ ] Capture the Condition Evaluation Report before the change.
- [ ] Record Boot/JDK version, profile, command line, and runtime dependency graph.
- [ ] Change only one variable per comparison.
- [ ] Start a new context and save the post-change report.
- [ ] Compare provider, consumer, and related downstream bean sources.
- [ ] Note which conditions flipped positive ↔ negative and their explanatory messages.
- [ ] Inspect actual beans by type/name/qualifier and candidate count.
- [ ] Verify whether fallback/back-off behaves as intended.
- [ ] Run auto-configuration tests and integration tests for affected features.
- [ ] Document root cause, expected change, and verification evidence in the PR/review.

**Conclusions should be specific:** “After removing H2 from the runtime classpath, `FeatureAutoConfiguration` switched to a negative match on `OnClassCondition`; provider `FoundationClient` still exists; `FeatureService` is not registered. This matches the design where the feature is supported only when H2 is present.” Such a conclusion pinpoints the cause, scope of impact, and remaining/removed beans.

## Official Documentation

- [Spring Boot 3.3 — Conditions Evaluation Report Actuator API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html): how to fetch the report and the structure of `contexts`, `positiveMatches`, `negativeMatches`, and `unconditionalClasses`.
- [Spring Boot 3.3 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html): enabling, exposing, and controlling endpoint access.
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): class, property, bean conditions, auto-configuration ordering, and testing.
- [Spring Boot 3.3 — Testing Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.testing): `ApplicationContextRunner` and testing condition branches.
