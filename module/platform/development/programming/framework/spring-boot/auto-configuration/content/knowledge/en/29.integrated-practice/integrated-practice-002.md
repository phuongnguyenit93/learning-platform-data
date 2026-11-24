# Changing Dependencies and Recording Differences in Beans and the Condition Evaluation Report

When adding or removing a dependency in Spring Boot, the change does not stop at the JAR list. A new dependency can bring additional classes onto the runtime classpath; auto-configurations using **@ConditionalOnClass**, **@ConditionalOnBean**, **@ConditionalOnProperty**, or **@ConditionalOnWebApplication** are re-evaluated. The result can be new beans appearing, default beans backing off, a configuration no longer being applied, or the application failing to start due to a missing required dependency.

An explainable practical exercise needs to capture three layers of evidence:

1. **Dependency graph:** which direct and transitive artifacts were added, removed, changed version, or changed scope?
2. **Bean inventory:** after ApplicationContext refresh, which bean definitions were additionally registered, lost, or changed type/factory method?
3. **Condition Evaluation Report:** which conditions switched from **NO_MATCH** to **MATCH**, or vice versa; what reason does the message give?

Do not infer bean changes from the dependency tree alone. A new dependency might trigger no auto-configuration at all; conversely, a class already present via a transitive dependency might satisfy a condition even though the POM does not declare that class directly.

## 1. Understanding the Impact Chain from Dependency to Bean

Spring Boot auto-configuration relies on the classpath and Environment at startup time. A dependency change can trigger the following chain:

```text
pom.xml changes
      |
      v
Maven resolves dependency graph
      |
      v
Runtime classpath changes
      |
      v
Auto-configuration candidates and class conditions change
      |
      v
Bean conditions / property conditions are evaluated
      |
      v
Bean definitions in ApplicationContext change
      |
      v
Application may behave or fail at startup differently
```

For example, adding **spring-boot-starter-actuator** puts Actuator APIs and auto-configurations onto the classpath. Spring Boot can register additional endpoint infrastructure such as health and the condition report. An application's own configuration using **@ConditionalOnClass** to integrate with **HealthEndpoint** may also begin to match.

Conversely, removing an optional library can cause auto-configurations that depend on that library to no longer be loaded. If application code still directly references the removed class, errors can occur before or during context refresh. Therefore, you must read the dependency diff, condition diff, and bean diff together.

## 2. Distinguishing Direct Dependencies, Transitive Dependencies, and Effective Classpath

In Maven:

- **Direct dependency:** declared directly in the module's dependencies section.
- **Transitive dependency:** pulled in by another dependency.
- **Dependency management:** manages versions and metadata; by itself it does not necessarily add an artifact to the classpath.
- **Scope:** determines whether a dependency is present at compile, test, or runtime.
- **Optional dependency:** is not automatically propagated transitively to consumers like a normal dependency.
- **Exclusion:** removes a transitive dependency from a specific resolution branch.

The command **mvn dependency:tree** displays the dependency tree resolved by Maven for that build. This tree shows what pulled an artifact in, which version was selected, and which branch produced the dependency. When investigating version conflicts, you can add **-Dverbose** to see nodes omitted due to conflict mediation.

Note: a dependency appearing in the tree does not guarantee it will create beans. Spring Boot only registers beans if the corresponding conditions match. A dependency may also provide only an API called directly by code, with no associated auto-configuration.

## 3. Designing a Before/After Experiment Changing Only One Dependency

We use a Java 17 / Spring Boot 3.3.5 application whose base dependency is **spring-boot-starter**. The baseline build does not include Actuator. The second build enables the Maven profile **with-actuator**, which adds only **spring-boot-starter-actuator**.

Keep identical between the two builds:

- Source code and commit.
- Spring Boot parent/version and Java version.
- Default profile, properties, environment variables, and command-line arguments.
- Application configuration and how the JAR is executed.
- The same commands to generate the dependency tree and bean/condition snapshots.

The sole variable of the experiment is the Maven profile adding Actuator. Because both artifacts use the same source, differences in the bean inventory and report can be directly attributed to the added dependency.

### 3.1. Project structure

```text
dependency-audit-lab/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── DependencyAuditApplication.java
```

Content of **pom.xml**:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>dependency-audit-lab</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <profiles>
        <profile>
            <id>with-actuator</id>
            <dependencies>
                <dependency>
                    <groupId>org.springframework.boot</groupId>
                    <artifactId>spring-boot-starter-actuator</artifactId>
                </dependency>
            </dependencies>
        </profile>
    </profiles>

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

The **with-actuator** profile adds the dependency without modifying source code. No separate version needs to be declared for the Actuator starter because the Spring Boot parent manages versions consistently with 3.3.5.

## 4. Recording the Bean Inventory and Condition Evaluation Report from the Same Application

For a fair comparison, we export both snapshots via code running inside both artifacts. This approach does not require an Actuator endpoint, so the baseline can also generate a condition report.

The program will:

- Retrieve bean definition names from **ConfigurableListableBeanFactory**.
- Record type metadata, factory bean, and factory method without calling **getBean()** for every bean.
- Read **ConditionEvaluationReport** recorded by Spring Boot during auto-configuration processing.
- Print each condition source, **MATCH/NO_MATCH** outcome, condition type, and message.

Create **src/main/java/demo/DependencyAuditApplication.java**:

```java
package demo;

import java.util.Arrays;
import java.util.Map;

import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.condition.ConditionOutcome;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;

@SpringBootApplication
@Import(DependencyAuditApplication.OptionalActuatorConfiguration.class)
public class DependencyAuditApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(DependencyAuditApplication.class, args)) {
            printBeanInventory(context);
            printConditionReport(context);
        }
    }

    private static void printBeanInventory(
            ConfigurableApplicationContext context) {

        ConfigurableListableBeanFactory beanFactory = context.getBeanFactory();

        System.out.println("=== BEAN INVENTORY ===");

        Arrays.stream(beanFactory.getBeanDefinitionNames())
                .sorted()
                .forEach(beanName -> {
                    BeanDefinition definition =
                            beanFactory.getBeanDefinition(beanName);

                    System.out.printf(
                            "BEAN|%s|%s|%s|%s%n",
                            beanName,
                            definition.getResolvableType(),
                            valueOrDash(definition.getFactoryBeanName()),
                            valueOrDash(definition.getFactoryMethodName())
                    );
                });
    }

    private static void printConditionReport(
            ConfigurableApplicationContext context) {

        ConfigurableListableBeanFactory beanFactory = context.getBeanFactory();
        ConditionEvaluationReport report =
                ConditionEvaluationReport.get(beanFactory);

        System.out.println("=== CONDITION REPORT ===");

        report.getConditionAndOutcomesBySource()
                .entrySet()
                .stream()
                .sorted(Map.Entry.comparingByKey())
                .forEach(entry -> {
                    for (ConditionEvaluationReport.ConditionAndOutcome item
                            : entry.getValue()) {

                        ConditionOutcome outcome = item.getOutcome();
                        String message = String.valueOf(outcome.getMessage())
                                .replace('\r', ' ')
                                .replace('\n', ' ');

                        System.out.printf(
                                "CONDITION|%s|%s|%s|%s%n",
                                entry.getKey(),
                                outcome.isMatch() ? "MATCH" : "NO_MATCH",
                                item.getCondition().getClass().getSimpleName(),
                                message
                        );
                    }
                });

        report.getExclusions().stream()
                .sorted()
                .forEach(name -> System.out.println("EXCLUSION|" + name));
    }

    private static String valueOrDash(String value) {
        return value == null ? "-" : value;
    }

    public record ActuatorIntegrationMarker(String source) {
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(
            name = "org.springframework.boot.actuate.health.HealthEndpoint"
    )
    static class OptionalActuatorConfiguration {

        @Bean
        ActuatorIntegrationMarker actuatorIntegrationMarker() {
            return new ActuatorIntegrationMarker("actuator-on-classpath");
        }
    }
}
```

### 4.1. Why use @ConditionalOnClass(name = "...")?

**HealthEndpoint** is only on the classpath after adding Actuator. If this class were imported directly in source, the baseline would fail to compile because the dependency is absent.

Using the **name** attribute with a class name string allows the condition to check for the class's presence without creating a compile-time reference. The optional configuration is placed in a separate nested **@Configuration** to isolate references to the optional library.

When the baseline lacks Actuator, **OptionalActuatorConfiguration** evaluates to **NO_MATCH** and the **actuatorIntegrationMarker** bean is not registered. When the **with-actuator** profile is enabled, the class is present on the classpath, the condition switches to **MATCH**, and the marker appears.

This is the experiment's marker bean, making it clear how a classpath change affects a condition. Actual Actuator beans can also appear in the inventory; exact names and counts depend on configuration, version, and application type.

## 5. Building and Saving Both Artifacts and Dependency Trees

Run in PowerShell inside the **dependency-audit-lab** directory. Save the baseline artifact before building the second profile so **mvn clean** does not overwrite the file needed for comparison.

```powershell
New-Item -ItemType Directory -Force artifacts | Out-Null

# Baseline: without enabling the with-actuator profile
mvn clean package
mvn dependency:tree -DoutputFile=artifacts/dependencies-before.txt

Copy-Item target/dependency-audit-lab-1.0.0.jar artifacts/before.jar

java -jar artifacts/before.jar *> artifacts/before-report.txt

# After change: add spring-boot-starter-actuator
mvn -Pwith-actuator clean package
mvn -Pwith-actuator dependency:tree -DoutputFile=artifacts/dependencies-after.txt

Copy-Item target/dependency-audit-lab-1.0.0.jar artifacts/after.jar

java -jar artifacts/after.jar *> artifacts/after-report.txt
```

The sample application has no web starter so it runs in non-web mode; after printing both snapshots, the process exits. If applying this approach to a web application running a server, use an audit profile with **spring.main.web-application-type=none** when appropriate, or capture the snapshot from a separate startup run.

Verify the environment before drawing conclusions:

```powershell
java -version
mvn -version
mvn -Pwith-actuator help:active-profiles
```

If you use any Maven profile other than **with-actuator**, keep that profile identical across both runs. Do not let application profiles or environment variables accidentally enable extra configuration in only one artifact.

## 6. Comparing the Dependency Trees

Use **Compare-Object** to inspect added or removed lines:

```powershell
Compare-Object (Get-Content artifacts/dependencies-before.txt) (Get-Content artifacts/dependencies-after.txt)
```

**<=** indicates lines present only in the baseline; **=>** indicates lines present only in the after version. For the experiment adding Actuator, the after version is expected to add **spring-boot-starter-actuator**, **spring-boot-actuator**, **spring-boot-actuator-autoconfigure**, and related transitive dependencies such as Micrometer.

The actual list depends on dependency management and versions resolved by Maven. Do not copy an expected list into a report as if it were a measured result. Save the full dependency trees from both runs and read the selected versions in the output.

If the dependency tree differs beyond the expected Actuator portion, investigate before proceeding. For example:

- A transitive dependency changed version due to conflict mediation.
- Another profile pulled in extra drivers or adapters.
- An exclusion was added/removed.
- Scope changed, causing a dependency to appear or disappear at runtime.

You can use **-Dverbose** when you need to view nodes omitted by Maven due to version conflicts:

```powershell
mvn -Pwith-actuator dependency:tree -Dverbose -DoutputFile=artifacts/dependencies-after-verbose.txt
```

## 7. Comparing the Bean Inventories

Each **BEAN|...** line in the snapshot represents a bean definition. Filter and compare:

```powershell
$beforeBeans = Get-Content artifacts/before-report.txt |
    Where-Object { $_.StartsWith("BEAN|") }

$afterBeans = Get-Content artifacts/after-report.txt |
    Where-Object { $_.StartsWith("BEAN|") }

Compare-Object $beforeBeans $afterBeans
```

Entries only in the after version typically show **=>**; lines only in the baseline show **<=**. In this experiment, look for:

- **actuatorIntegrationMarker:** appears only when Actuator is present.
- Bean definitions belonging to Actuator packages.
- New infrastructure beans registered by Actuator auto-configuration.
- Beans with the same name whose type/factory method metadata changed, if any.

Do not compare only total bean counts. Two builds can have the same count while one bean disappeared and another bean was added. Line-by-line comparison detects replacement changes, not just count changes.

The program reads metadata from **BeanDefinition** without calling **getBean()** for the entire list. Therefore, the inventory does not proactively initialize lazy beans just to take stock. **getResolvableType()** may not be fully resolved for some definitions; use factory method, bean class, and resource metadata when tracing registration sources.

## 8. Comparing the Condition Evaluation Reports

Filter the condition lines and compare:

```powershell
$beforeConditions = Get-Content artifacts/before-report.txt |
    Where-Object { $_.StartsWith("CONDITION|") }

$afterConditions = Get-Content artifacts/after-report.txt |
    Where-Object { $_.StartsWith("CONDITION|") }

Compare-Object $beforeConditions $afterConditions
```

To inspect the experiment's marker condition specifically:

```powershell
Get-Content artifacts/before-report.txt |
    Where-Object { $_ -like "*OptionalActuatorConfiguration*" }

Get-Content artifacts/after-report.txt |
    Where-Object { $_ -like "*OptionalActuatorConfiguration*" }
```

Illustrative output format:

```text
# Baseline: HealthEndpoint class is not on the classpath
CONDITION|demo.DependencyAuditApplication$OptionalActuatorConfiguration|NO_MATCH|OnClassCondition|...

# With the with-actuator profile
CONDITION|demo.DependencyAuditApplication$OptionalActuatorConfiguration|MATCH|OnClassCondition|...
```

Exact messages are generated by Spring Boot and may vary by version. What matters is reading the source, condition type, match status, and message together. For example:

- **OnClassCondition:** whether required classes are present or absent on the classpath.
- **OnBeanCondition:** whether a bean type/name already existed at the time the condition was evaluated.
- **OnPropertyCondition:** whether a property has a matching value.
- **OnWebApplicationCondition:** whether the context is a servlet/reactive web application.

**MATCH** means that condition passed. It does not by itself guarantee the entire context will start successfully; a bean can still fail during initialization due to other dependencies or configuration. For configurations with multiple conditions, read all outcomes for that source.

### 8.1. The report is not a list of all possible auto-configurations

**ConditionEvaluationReport** records the conditions that were actually evaluated. When a dependency is removed from the classpath, an auto-configuration class may also disappear from the candidate set; in that case the corresponding source will not necessarily appear as **NO_MATCH**. It may be completely absent from the report.

That is why the report must be read alongside the dependency tree. The dependency tree shows which classes/artifacts are present; the report shows which conditions were evaluated and their outcomes. The bean inventory confirms which definitions were ultimately registered.

In the example, **OptionalActuatorConfiguration** is explicitly imported in source in both builds. Thus its classpath condition can show **NO_MATCH** in the baseline and **MATCH** after adding the dependency. This is a controlled illustrative signal; auto-configurations inside libraries may behave differently as candidates.

## 9. Reading Results Across the Three Layers of Evidence

Once you have all three diffs, build a conclusion table:

| Evidence | Baseline build | Build with Actuator | Interpretation |
| --- | --- | --- | --- |
| Dependency tree | No Actuator starter | Starter and transitive dependencies present | Classpath changed as intended by the experiment. |
| Condition marker | **NO_MATCH** due to missing HealthEndpoint | **MATCH** because class is present | Classpath condition transitioned state. |
| Bean marker | No actuatorIntegrationMarker | actuatorIntegrationMarker present | Condition match led to a new bean definition. |
| Actuator infrastructure | No Actuator beans | Additional beans matching auto-configuration | New dependency triggered corresponding conditional configurations. |

If the dependency tree changed while the bean inventory did not, the dependency might only add classes/libraries not yet used by the application or whose conditions do not match. This is still a valid result; do not force bean creation just to prove a dependency has an effect.

If a condition switched to **MATCH** yet the bean does not appear, check conditions on the bean method, **@ConditionalOnMissingBean**, bean names, auto-configuration ordering, and bean creation errors. If a new bean appears without a corresponding condition in the report, the bean might come from configuration not using Spring Boot conditions, or the condition source might appear in another section of the report.

If the context fails before printing snapshots, keep the startup logs and inspect the root cause. A removed dependency can cause **NoClassDefFoundError**, **ClassNotFoundException**, **NoSuchMethodError**, or **BeanCreationException**; that is runtime evidence distinct from a simple non-matching condition.

## 10. Other Ways to Obtain Reports in Real Applications

### 10.1. Using --debug

Spring Boot can print the auto-configuration condition report when launched with **--debug**:

```bash
java -jar target/application.jar --debug
```

This is quick when investigating a single startup. Keep the same log level and debug settings between two builds if using that output for comparison. In the practical example, code calls the API directly to produce stable snapshot lines that are easy to filter with PowerShell.

### 10.2. Using ConditionEvaluationReportLoggingListener

When writing tests with **ApplicationContextRunner**, you can attach a listener to log the report:

```java
ApplicationContextRunner runner = new ApplicationContextRunner()
        .withInitializer(
                ConditionEvaluationReportLoggingListener.forLogLevel(
                        LogLevel.INFO
                )
        );
```

**ConditionEvaluationReportLoggingListener** is an **ApplicationContextInitializer** that logs the report. Do not share the same listener instance across multiple contexts; create a new initializer for each runner/context per the API guidance.

### 10.3. Using Actuator conditions and beans endpoints

When an application has Actuator and is a web application, you can use:

- **/actuator/conditions:** condition evaluation report.
- **/actuator/beans:** list of beans in the ApplicationContext.

By default, only **health** is exposed over HTTP. If you need to view both endpoints in a local environment, you can configure:

```properties
management.endpoints.web.exposure.include=health,conditions,beans
```

Only expose diagnostic endpoints in controlled environments and protect them with appropriate security/network policies. The condition report and bean inventory can reveal classes, configuration, and internal structure of the application. For a baseline without Actuator, the **ConditionEvaluationReport** API in the example still lets you generate the report without adding Actuator solely for observation.

## 11. Notes When Adding or Removing Dependencies

A dependency change can have broader effects than the directly added artifact:

- Adding a starter often pulls in multiple child starters and transitive libraries.
- Removing a direct dependency does not guarantee the class is gone if another dependency still pulls it in.
- An exclusion only removes a dependency from the declared branch; the same artifact can still appear through another branch.
- Dependencies with **test** scope can make tests pass while the packaged application lacks the class at runtime.
- **Optional** dependencies of a library do not automatically become required dependencies for consumers.
- A BOM/parent can change resolved versions even without editing the version on the dependency line.
- Auto-configuration may simultaneously require classpath, beans, properties, and web context; adding only the class might not be enough for the bean to appear.

When removing a dependency, re-check **dependency:tree** to verify the class truly disappeared. If the class is still provided by another dependency, **@ConditionalOnClass** can still match and the bean will still exist.

When adding dependencies to a starter/library, test with a real consumer as well. A test project having a dependency in test scope does not prove applications using the starter will receive that dependency at runtime. If a library requires consumers to add optional integrations themselves, the documentation must clearly state which dependencies to declare.

## 12. Common Pitfalls When Comparing

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Dependency tree differs more than expected | Profile, BOM, exclusions, or version mediation also changed | Compare POM/effective profiles and explain each transitive branch. |
| Dependency in tree but no new beans | No matching auto-configuration or conditions do not match | Read the condition report and confirm the bean is actually designed to auto-register. |
| New bean appears but no condition source found | Bean comes from regular configuration, import, scan, or another source | Find the bean definition resource/factory method; do not attribute every bean to auto-configuration. |
| Condition MATCH yet bean does not exist | Another condition on the method failed or context refresh failed | Read all outcomes of the source and startup exceptions. |
| Bean lost after removing dependency | Dependency provided classes or infrastructure beans required by the feature | Check direct/transitive dependencies and class/bean conditions. |
| Report does not list removed auto-configuration | Class is no longer a candidate to evaluate | Cross-check dependency tree and AutoConfiguration.imports in the artifact. |
| Two runs differ despite identical POM | Profiles, properties, environment, JDK, or launch method differed | Pin all inputs and save launch commands. |
| Same bean count yet different beans | One bean was replaced by another | Diff the inventory line by line, not just total counts. |
| Actuator endpoint returns 404 | Endpoint not exposed or application is not a web application | Check dependencies, endpoint access/exposure, and management server. |

## 13. Repeatable Practice Workflow

1. Choose one specific dependency to add or remove and write down your hypothesis about the related classes/auto-configurations.
2. Record the source revision, POM, Java/Maven versions, and baseline configuration.
3. Build the baseline, and save the JAR and dependency tree.
4. Run the baseline, and save the bean inventory and condition report.
5. Change only the chosen dependency, and rebuild with the same tools and configuration.
6. Save the second JAR, dependency tree, bean inventory, and condition report.
7. Diff dependencies first, then conditions, and finally the bean inventory.
8. Trace every added/removed bean back to its dependency, condition source, and bean definition.
9. Run relevant functional tests to verify the new beans actually work.
10. Record conclusions, limitations, and the artifacts used to reproduce.

For the Actuator-addition experiment above, the expected evidence is the dependency graph containing Actuator, the classpath condition switching to match, and the marker bean appearing. When applying this to a real starter, replace the marker with the starter's actual beans/auto-configurations and verify the behavior consumers need.

## 14. Checklist Before Finalizing Results

- [ ] Only one dependency/profile was intentionally changed.
- [ ] Same JDK, Maven, Spring Boot parent, and source code.
- [ ] Both dependency trees saved, not just POM screenshots.
- [ ] Checked direct dependencies, transitive dependencies, scopes, and version conflicts.
- [ ] Exported bean inventory from both ApplicationContexts.
- [ ] Exported Condition Evaluation Report from both runs using the same method.
- [ ] Distinguished MATCH, NO_MATCH, and sources no longer in the candidate set.
- [ ] Traced added/removed beans back to their corresponding conditions and dependencies.
- [ ] Checked startup failures and classpath errors if any.
- [ ] Ran functional tests for the affected integration.
- [ ] Saved JARs, logs, snapshots, and build commands to reproduce the results.

**Key takeaway:** the dependency graph explains which classes are brought into runtime; the Condition Evaluation Report explains why configurations were or were not applied; the bean inventory confirms which definitions ultimately exist in the context. Only when all three layers of evidence align can you clearly explain the impact of a dependency change.

### Official References

- Spring Boot 3.3 — Creating Your Own Auto-configuration, class conditions and bean conditions: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 API — ConditionEvaluationReport: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html
- Spring Boot 3.3 API — ConditionEvaluationReportLoggingListener: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/logging/ConditionEvaluationReportLoggingListener.html
- Spring Boot 3.3 Actuator API — Conditions endpoint: https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html
- Spring Boot 3.3 Actuator API — Beans endpoint: https://docs.spring.io/spring-boot/3.3/api/rest/actuator/beans.html
- Apache Maven Dependency Plugin — dependency:tree: https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html
- Spring Framework 6.1 API — BeanDefinition: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/beans/factory/config/BeanDefinition.html