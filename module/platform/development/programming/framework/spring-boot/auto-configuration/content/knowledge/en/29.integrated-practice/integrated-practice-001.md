# Building an Experiment to Compare Applications With and Without Auto-Configuration Enabled

## 1. Goal of the Experiment

Spring Boot auto-configuration automatically registers beans based on the classpath, properties, beans the application has already declared, and the ApplicationContext type. Because of this, an application can use a library simply by adding a starter and declaring the required configuration values.

When you need to understand where a bean comes from, or why a dependency makes the application start up differently, build an experiment with two branches:

- **Auto-configuration enabled:** Spring Boot loads auto-configuration candidates, evaluates conditions, and registers the matching beans.
- **Auto-configuration not loaded:** the context only contains the configurations the user registered; default beans from the target auto-configuration do not appear.

Then add sub-branches to distinguish three situations that are often conflated:

1. The auto-configuration is not included in the context.
2. The auto-configuration is loaded, but its condition does not match.
3. The auto-configuration is loaded, its condition matches, but the default bean backs off in favor of a user-provided bean.

These three situations can produce the same result in a simple assertion like "no ReportClient", yet their causes and fixes are different.

This guide uses **Java 17 and Spring Boot 3.3.13** as the baseline. The main experiment uses **ApplicationContextRunner**, the tool recommended by Spring Boot for creating small, isolated contexts and testing auto-configuration. No database, HTTP server, or external service is needed.

## 2. How Does Auto-Configuration Work?

### 2.1. From dependency to bean

A starter typically brings the required libraries onto the classpath. Spring Boot discovers auto-configuration classes published in the resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Each line in the file is the fully qualified name of an auto-configuration class. Spring Boot inspects those classes, applies exclusions, ordering, and conditions, and then registers the appropriate bean definitions.

For example:

~~~text
com.acme.reports.autoconfigure.ReportsAutoConfiguration
~~~

If the classpath contains the required libraries, the property enables the feature, and the application has not provided a replacement bean, auto-configuration can register a default bean.

### 2.2. Conditions decide whether a configuration applies

Common conditions:

| Condition | Question |
| --- | --- |
| @ConditionalOnClass | Is the required class/dependency on the classpath? |
| @ConditionalOnMissingClass | Is a specific class absent? |
| @ConditionalOnProperty | Does the property exist and have the expected value? |
| @ConditionalOnBean | Has a prerequisite bean already been registered? |
| @ConditionalOnMissingBean | Has the application not yet provided a matching bean? |
| @ConditionalOnWebApplication | Is the context servlet, reactive, or non-web? |

A non-matching condition means the guarded configuration or bean method is not applied. It does not necessarily cause application startup to fail.

### 2.3. Auto-configuration being enabled does not mean every bean is created

It is necessary to distinguish:

- Candidate: a class considered by Spring Boot.
- Applied configuration: a class that passes class-level conditions.
- Bean definition: bean metadata registered in the context.
- Bean instance: the actual object created.

An auto-configuration can be loaded while one bean method inside it is excluded by a condition. A bean definition can exist while its instance is initialized lazily. Therefore, an experiment should check the exact bean/type you care about, rather than just counting total beans.

## 3. Three Ways of "Disabling" Have Different Meanings

### 3.1. Not loading the auto-configuration in the experiment

If you create an ApplicationContextRunner without adding AutoConfigurations.of(...), the runner does not load the target auto-configuration:

~~~java
new ApplicationContextRunner()
        .run(context -> {
            assertThat(context).doesNotHaveBean(ReportClient.class);
        });
~~~

This is the control branch to compare against a runner where the configuration is added explicitly. It is useful for an isolated experiment, but it is not the way to disable auto-configuration across a real Spring Boot application.

### 3.2. Loading the auto-configuration when the condition does not match

For example, a feature is enabled only when a property is true:

~~~java
@ConditionalOnProperty(
        prefix = "acme.reports",
        name = "enabled",
        havingValue = "true")
~~~

When running with:

~~~properties
acme.reports.enabled=false
~~~

the auto-configuration remains in the candidate set being evaluated, but the condition does not match and the corresponding bean is not registered.

This is the intentional way to turn off a feature via configuration. It should not be confused with removing the class from the candidate list.

### 3.3. Excluding a specific auto-configuration

In a real Spring Boot application, you can exclude a specific auto-configuration:

~~~java
@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)
public class Application {
}
~~~

Or using the class name:

~~~java
@SpringBootApplication(
        excludeName =
                "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration")
public class Application {
}
~~~

Or via configuration:

~~~properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

These approaches remove the specified classes from the auto-configuration process. They do not automatically disable all other auto-configurations.

### 3.4. Not enabling auto-configuration for a context

@SpringBootApplication includes @EnableAutoConfiguration, @ComponentScan, and @SpringBootConfiguration.

If you need to build a context without auto-configuration enabled for an experiment, you can use @SpringBootConfiguration together with @ComponentScan without adding @EnableAutoConfiguration:

~~~java
@SpringBootConfiguration
@ComponentScan(basePackages = "com.example.app.components")
public class ApplicationWithoutAutoConfiguration {
}
~~~

That configuration only scans the application's component package. It does not automatically load Boot auto-configuration candidates.

This context must declare by itself the infrastructure beans that Spring Boot previously configured automatically. This is a way to compare whole configuration modes in a separate test. In real applications, you should generally exclude a specific integration or control a feature via properties rather than removing all auto-configuration.

## 4. Designing a Controlled Experiment

We build a small auto-configuration for the Acme Reports library:

- If acme.reports.enabled=true, create a default ReportClient.
- If the property is false or missing, do not create the bean.
- If the application provides its own ReportClient, the auto-configuration must back off.

Variants to compare:

| Code | Auto-configuration | Property | Application-provided bean | Expected result |
| --- | --- | --- | --- | --- |
| A | Not loaded | true | No | No default ReportClient |
| B | Loaded | true | No | Default ReportClient present |
| C | Loaded | false | No | No ReportClient |
| D | Loaded | true | Custom bean present | Only custom ReportClient |
| E | Loaded via @EnableAutoConfiguration | true | No | Imports resource discovered and default created |
| F | Loaded via @EnableAutoConfiguration, class name excluded | true | No | Target auto-configuration excluded |

Keep the JDK, dependencies, properties, and user configuration identical between corresponding branches. Change only one factor in each comparison.

## 5. Creating the Maven Project

### 5.1. Directory structure

~~~text
autoconfiguration-experiment/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/acme/reports/
    │   │   ├── ReportClient.java
    │   │   └── autoconfigure/
    │   │       └── ReportsAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/com/acme/reports/autoconfigure/
            └── AutoConfigurationExperimentTests.java
~~~

### 5.2. pom.xml

~~~xml
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

    <groupId>com.acme</groupId>
    <artifactId>autoconfiguration-experiment</artifactId>
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

The parent manages dependency versions aligned with Spring Boot 3.3.13. spring-boot-autoconfigure provides annotations and conditions; spring-boot-starter-test provides JUnit, AssertJ, and Spring Boot test utilities.

## 6. Writing the Bean and Auto-Configuration

### 6.1. ReportClient.java

Create src/main/java/com/acme/reports/ReportClient.java:

~~~java
package com.acme.reports;

public record ReportClient(String endpoint) {
}
~~~

The record holds an endpoint so the experiment can inspect the bean value. It makes no network connections.

### 6.2. ReportsAutoConfiguration.java

Create src/main/java/com/acme/reports/autoconfigure/ReportsAutoConfiguration.java:

~~~java
package com.acme.reports.autoconfigure;

import com.acme.reports.ReportClient;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.reports",
        name = "enabled",
        havingValue = "true")
public class ReportsAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(ReportClient.class)
    ReportClient reportClient() {
        return new ReportClient("https://default.example.test");
    }
}
~~~

The two conditions have different scopes:

- The class-level condition requires the property to be enabled. If the property is not true, the configuration is not applied.
- The bean-method condition requires that no ReportClient has been provided by the application yet. If a user bean exists, the default method does not register a bean.

@ConditionalOnMissingBean is normally placed on auto-configurations because Spring Boot processes auto-configuration after user-defined bean definitions. This gives the application a chance to supply its own implementation before the default bean is considered.

### 6.3. AutoConfiguration.imports

Create the file:

src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports

Content:

~~~text
com.acme.reports.autoconfigure.ReportsAutoConfiguration
~~~

This file publishes the auto-configuration to consuming applications. When @EnableAutoConfiguration or @SpringBootApplication is used, Spring Boot can discover the class via this resource.

**Distinguishing the two loading approaches in tests:**

- AutoConfigurations.of(ReportsAutoConfiguration.class) adds the class explicitly to the runner, which is suitable for testing an auto-configuration in isolation.
- @EnableAutoConfiguration uses Spring Boot's discovery mechanism and reads AutoConfiguration.imports. This helps verify whether the resource is packaged and discovered.

A test using AutoConfigurations.of does not by itself prove that the imports file was packaged properly.

## 7. Writing the Experiment with ApplicationContextRunner

Create src/test/java/com/acme/reports/autoconfigure/AutoConfigurationExperimentTests.java.

~~~java
package com.acme.reports.autoconfigure;

import com.acme.reports.ReportClient;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.assertj.AssertableApplicationContext;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class AutoConfigurationExperimentTests {

    private static final String ENABLED =
            "acme.reports.enabled=true";

    private static final String DISABLED =
            "acme.reports.enabled=false";

    private static final String AUTO_CONFIGURATION_NAME =
            "com.acme.reports.autoconfigure.ReportsAutoConfiguration";

    // Branch A: do not load the target auto-configuration.
    private final ApplicationContextRunner withoutAutoConfiguration =
            new ApplicationContextRunner()
                    .withPropertyValues(ENABLED);

    // Branch B: load the exact auto-configuration to test.
    private final ApplicationContextRunner withAutoConfiguration =
            this.withoutAutoConfiguration
                    .withConfiguration(
                            AutoConfigurations.of(
                                    ReportsAutoConfiguration.class));

    @Test
    void withoutAutoConfigurationDoesNotCreateDefaultBean() {
        this.withoutAutoConfiguration.run(context -> {
            assertThat(context).doesNotHaveBean(ReportClient.class);
            assertThat(reportClientNames(context)).isEmpty();
        });
    }

    @Test
    void withAutoConfigurationAndEnabledPropertyCreatesDefaultBean() {
        this.withAutoConfiguration.run(context -> {
            assertThat(context).hasSingleBean(ReportClient.class);
            assertThat(reportClientNames(context))
                    .containsExactly("reportClient");

            assertThat(context.getBean(ReportClient.class).endpoint())
                    .isEqualTo("https://default.example.test");
        });
    }

    @Test
    void falsePropertyPreventsDefaultBeanRegistration() {
        this.withAutoConfiguration
                .withPropertyValues(DISABLED)
                .run(context -> {
                    assertThat(context).doesNotHaveBean(ReportClient.class);
                    assertThat(reportClientNames(context)).isEmpty();
                });
    }

    @Test
    void userBeanMakesDefaultAutoConfigurationBackOff() {
        this.withAutoConfiguration
                .withUserConfiguration(CustomReportConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportClient.class);
                    assertThat(reportClientNames(context))
                            .containsExactly("customReportClient");

                    assertThat(context.getBean(ReportClient.class).endpoint())
                            .isEqualTo("https://custom.example.test");
                });
    }

    @Test
    void userBeanStillExistsWhenAutoConfigurationIsNotLoaded() {
        this.withoutAutoConfiguration
                .withUserConfiguration(CustomReportConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportClient.class);
                    assertThat(reportClientNames(context))
                            .containsExactly("customReportClient");
                });
    }

    @Test
    void enableAutoConfigurationDiscoversImportsResource() {
        new ApplicationContextRunner()
                .withUserConfiguration(BootAutoConfigurationEnabled.class)
                .withPropertyValues(ENABLED)
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportClient.class);
                    assertThat(context.getBean(ReportClient.class).endpoint())
                            .isEqualTo("https://default.example.test");
                });
    }

    @Test
    void excludeNameRemovesThePublishedAutoConfiguration() {
        new ApplicationContextRunner()
                .withUserConfiguration(BootAutoConfigurationExcluded.class)
                .withPropertyValues(ENABLED)
                .run(context -> {
                    assertThat(context).doesNotHaveBean(ReportClient.class);
                });
    }

    private static String[] reportClientNames(
            AssertableApplicationContext context) {

        return context.getBeanFactory()
                .getBeanNamesForType(ReportClient.class);
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomReportConfiguration {

        @Bean
        ReportClient customReportClient() {
            return new ReportClient("https://custom.example.test");
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAutoConfiguration
    static class BootAutoConfigurationEnabled {
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAutoConfiguration(excludeName = AUTO_CONFIGURATION_NAME)
    static class BootAutoConfigurationExcluded {
    }
}
~~~

### 7.1. Meaning of each test

| Test | Changed condition | What it proves |
| --- | --- | --- |
| withoutAutoConfiguration... | Do not add auto-config to runner | No default bean |
| withAutoConfiguration... | Add auto-config, property true | Default bean exists |
| falseProperty... | Auto-config still loaded, property false | Class is evaluated, but condition excludes configuration |
| userBeanMakes... | Add custom bean before auto-config | Default bean backs off |
| userBeanStillExists... | Do not load auto-config, keep user config | Application bean does not depend on default |
| enableAutoConfiguration... | Use @EnableAutoConfiguration | Boot discovers class from imports resource |
| excludeNameRemoves... | Exclude auto-config FQCN | Boot skips the specified auto-configuration |

The first two tests form the main comparison. The remaining tests help isolate the cause when results differ from expectations.

### 7.2. Running the experiment

In the directory containing pom.xml:

~~~bash
mvn clean test
~~~

Expected result: **seven passing tests**.

The tests use ApplicationContextRunner, so there is no need to start an embedded server. Each call to run creates an isolated context, executes the assertions, and closes the context.

### 7.3. Expected results table

The bean names below are the results for bean type ReportClient, not the total number of beans in the ApplicationContext:

| Branch | ReportClient bean names | Endpoint |
| --- | --- | --- |
| Auto-config not loaded | [] | None |
| Auto-config loaded, enabled=true | [reportClient] | https://default.example.test |
| Auto-config loaded, enabled=false | [] | None |
| Auto-config loaded, user bean present | [customReportClient] | https://custom.example.test |
| Auto-config not loaded, user bean present | [customReportClient] | https://custom.example.test |
| Discovery via imports | [reportClient] | https://default.example.test |
| Exclude class by name | [] | None |

Key takeaways:

- Not having auto-configuration does not prevent user configuration from creating beans.
- A false property disables the feature at the condition level.
- A custom bean takes precedence and causes the default bean to back off.
- @EnableAutoConfiguration tests the actual discovery path via the imports resource.
- Exclusion tests removing a specific candidate.

## 8. Trying with a Real Spring Boot Application

ApplicationContextRunner is ideal for testing each branch. If you need to verify the behavior of an application launched with SpringApplication, create two explicit configurations.

### 8.1. Application with auto-configuration enabled

~~~java
package com.example.app;

import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ApplicationWithAutoConfiguration {
}
~~~

@SpringBootApplication includes @EnableAutoConfiguration, so Boot will search for auto-configurations published in the imports resource.

### 8.2. Application without auto-configuration enabled

~~~java
package com.example.app;

import org.springframework.boot.SpringBootConfiguration;
import org.springframework.context.annotation.ComponentScan;

@SpringBootConfiguration
@ComponentScan(basePackages = "com.example.app.components")
public class ApplicationWithoutAutoConfiguration {
}
~~~

This configuration does not have @EnableAutoConfiguration. It only scans the application's component package; it does not automatically load Boot auto-configuration candidates.

This context must declare by itself the infrastructure beans that Spring Boot previously auto-configured. For example, if the application previously relied on auto-configuration to create a Jackson mapper, task executor, or datasource, those beans might no longer exist.

Keep the auto-configuration library package outside component scan. If component scan covers the library package, the @AutoConfiguration class could be picked up as a regular configuration; the experiment would then no longer isolate the auto-configuration path.

### 8.3. Excluding only one auto-configuration in a real application

Typically, keep @SpringBootApplication and exclude only the unwanted integration:

~~~java
@SpringBootApplication(
        exclude = DataSourceAutoConfiguration.class)
public class Application {
}
~~~

Or configure it in application.properties:

~~~properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

You should not drop all auto-configuration just to remove a single bean or integration.

## 9. Observing Conditions and Bean Sources

### 9.1. Enabling the Condition Evaluation Report

Run the application with:

~~~bash
java -jar target/autoconfiguration-experiment-1.0.0.jar --debug
~~~

Or:

~~~properties
debug=true
~~~

The report shows which auto-configurations matched and did not match, along with the reasons. If ReportsAutoConfiguration did not match because the property was false, the report distinguishes that cause from the class being excluded or not discovered.

In tests, you can attach a listener:

~~~java
new ApplicationContextRunner()
        .withInitializer(
                ConditionEvaluationReportLoggingListener.forLogLevel(
                        LogLevel.INFO))
        .withConfiguration(
                AutoConfigurations.of(ReportsAutoConfiguration.class))
        .run(context -> {
            // Experiment assertions
        });
~~~

Corresponding imports:

~~~java
import org.springframework.boot.logging.LogLevel;
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
~~~

### 9.2. Inspecting beans by type

Do not look only at the total bean count. Use:

~~~java
String[] names = context.getBeanFactory()
        .getBeanNamesForType(ReportClient.class);

System.out.println(Arrays.toString(names));
~~~

And import:

~~~java
import java.util.Arrays;
~~~

This API shows the bean names belonging to the target type. If there are multiple implementations, the list helps detect duplicate candidates.

### 9.3. Distinguishing bean definition and instance

If a bean is marked @Lazy, the definition may exist while the instance has not yet been created. When checking:

~~~java
boolean definitionExists =
        context.getBeanFactory()
                .containsBeanDefinition("reportClient");

boolean singletonCreated =
        context.getBeanFactory()
                .containsSingleton("reportClient");
~~~

These two values have different meanings. Do not use containsSingleton to conclude whether auto-configuration registered the bean definition.

### 9.4. Inspecting the source of a bean definition

When a bean appears unexpectedly, inspect its metadata:

~~~java
BeanDefinition definition =
        context.getBeanFactory()
                .getBeanDefinition("reportClient");

System.out.println(definition.getResourceDescription());
System.out.println(definition.getFactoryBeanName());
System.out.println(definition.getFactoryMethodName());
~~~

For beans created with @Bean, the factory method and configuration class usually help trace where the bean was registered. Resource description may not be present on every kind of definition.

## 10. Measuring Performance With and Without Auto-Configuration

The experiment above verifies **bean registration behavior**. It is not yet a startup benchmark of a production application.

### 10.1. Metrics to measure

| Metric | How to interpret |
| --- | --- |
| Startup time | Time from process start to a consistent readiness marker |
| Bean definitions | Number and types of registered bean definitions |
| Singleton instances | Number of objects created when context refresh finishes |
| First-use latency | Latency on first use of a lazy bean or integration |
| Memory | Heap after startup and after workload stabilization |
| Request latency | Request latency after the application is ready |

Do not use the total bean count alone as a proxy for startup cost. One auto-configuration might register many lightweight beans; another bean might create a connection pool or perform expensive I/O.

### 10.2. Fair comparison

To compare two variants:

1. Use the same JDK and the same build artifact.
2. Keep the dependency graph, profiles, properties, and environment identical.
3. Change only the target auto-configuration.
4. Launch a fresh process for each run if measuring cold startup.
5. Run multiple iterations and compare median and p95; do not pick the fastest run.
6. Measure the same readiness marker.
7. Also measure first-use latency if beans are deferred.
8. Record heap and target bean counts after the application has stabilized.

You can use `time` on Linux/macOS or `Measure-Command` in PowerShell to measure process wall-clock time. For servers that keep the process running continuously, measure the readiness marker or startup event instead of waiting for the process to exit. Do not compare a run from an IDE with a run from a JAR because environment and classpath may differ.

### 10.3. Measuring startup steps

Spring Boot supports ApplicationStartup to record steps during startup. You can enable BufferingApplicationStartup:

~~~java
SpringApplication application =
        new SpringApplication(Application.class);

application.setApplicationStartup(
        new BufferingApplicationStartup(2048));

application.run(args);
~~~

Configure the same instrumentation on both variants. If Actuator is present, you can use the startup endpoint with appropriate exposure configuration to view time-consuming steps.

Profiling with Java Flight Recorder also helps observe class loading, allocation, garbage collection, and JVM activity. Distinguish ApplicationContext creation time from full process time.

### 10.4. Do not conclude before measuring

Disabling an auto-configuration can reduce parsing, condition evaluation, bean definitions, and related instances. However, if that integration does not perform much work during the current run, the startup difference may be very small.

Conversely, disabling a required auto-configuration may force the application to create many beans manually, leading to higher cost and complexity.

Benchmark results must be accompanied by application behavior. A variant that starts faster but lacks a required datasource, health indicator, or serializer is not a valid improvement.

## 11. Common Pitfalls in the Experiment

| Symptom | Cause | Resolution |
| --- | --- | --- |
| No bean in either branch | Property not enabled or another condition fails to match | Check properties and Condition Evaluation Report |
| Non-auto-config test still has bean | User configuration or component scan registers the bean | Check bean source and runner configuration |
| Property is false yet bean still exists | Bean registered through another configuration | Find all bean names and BeanDefinition sources |
| Exclude has no effect | Class imported directly or discovered by component scan | Check class loading path; exclusion only applies to auto-configuration imports |
| Two beans of the same type | User bean and default bean both registered | Check ConditionalOnMissingBean, ordering, and definition sources |
| Custom bean does not make default back off | User configuration not processed in time or condition misplaced | Keep default on the auto-configuration path and check runner |
| Tests pass but real app differs | Test loads class directly without checking real imports or component scan | Add EnableAutoConfiguration test and consumer smoke test |
| Bean count produces unstable results | Counting infrastructure beans and other dependencies | Check bean names by target type |
| Faster startup but slow first request | Initialization cost shifted to first use | Measure both startup and first-use latency |
| Disabling auto-config breaks app | App depends on Boot-provided infrastructure beans | Exclude only intentional integrations and provide replacements if needed |
| Using spring.autoconfigure.exclude yet bean remains | Another registration path still loads the class | Check component scan, @Import, and other configurations |
| Comparing timings from a single run | JIT, class loading, machine, and process state introduce noise | Run multiple fresh processes and compare result distributions |

## 12. Experiment Completion Checklist

### Setup

- [ ] Same JDK, dependencies, and build artifact across branches.
- [ ] Target auto-configuration clearly documented.
- [ ] Properties and user beans clearly documented per branch.
- [ ] Control branch not loading auto-configuration present.
- [ ] Branch loading auto-configuration with property enabled present.
- [ ] Branch where condition does not match present.
- [ ] Branch where user bean makes default back off present.

### Observation

- [ ] Checked bean names by target type.
- [ ] Checked bean endpoint/values when the bean appears.
- [ ] Checked imports discovery via @EnableAutoConfiguration.
- [ ] Checked exclusion by class name.
- [ ] Read Condition Evaluation Report when results differed from expectations.
- [ ] Inspected bean definitions if suspecting registration from another source.

### Performance

- [ ] Changed only one variable between two runs.
- [ ] Used fresh processes for cold startup.
- [ ] Ran enough iterations to get median and p95.
- [ ] Measured the same readiness marker.
- [ ] Measured first-use latency if lazy beans exist.
- [ ] Recorded memory and functional behavior after startup.

## 13. Self-Check Questions

**Question 1.** In the experiment, how do you create a branch that does not load a specific auto-configuration?  
**Answer:** Use ApplicationContextRunner without calling withConfiguration(AutoConfigurations.of(...)) for that class.

**Question 2.** Is an auto-configuration loaded with property false the same as not loading the class?  
**Answer:** No. The class is still evaluated, but the condition does not match so the guarded configuration/bean is not registered.

**Question 3.** What does ConditionalOnMissingBean do in the experiment?  
**Answer:** It lets the default bean back off when user configuration has already provided a bean of the same type.

**Question 4.** Why test both AutoConfigurations.of and @EnableAutoConfiguration?  
**Answer:** The first isolates a class to test its logic; the second verifies Boot discovers the class through AutoConfiguration.imports.

**Question 5.** Does spring.autoconfigure.exclude disable all auto-configuration?  
**Answer:** No. It excludes the listed auto-configuration classes. To make a context not enable auto-configuration, omit @EnableAutoConfiguration/@SpringBootApplication on that configuration.

**Question 6.** Why should you not compare only total bean counts?  
**Answer:** The context also contains infrastructure beans and beans from other dependencies. Inspect the target bean type/names and definition sources.

**Question 7.** How do you confirm an auto-configuration class is discovered from a JAR?  
**Answer:** Use @EnableAutoConfiguration in a consumer test, then inspect the AutoConfiguration.imports resource in the packaged JAR.

**Question 8.** When auto-configuration is enabled, will a custom bean necessarily be replaced by the default?  
**Answer:** No. If the default bean has ConditionalOnMissingBean and the user bean is registered earlier, the default backs off.

**Question 9.** Can you use the duration of a single `mvn test` run as a startup benchmark?  
**Answer:** No. Test time includes Maven, test discovery, JVM overhead, and multiple contexts. To measure application startup, run the same JAR in fresh processes multiple times using the same readiness marker.

**Question 10.** If disabling auto-configuration makes the app start faster but misses required beans, is that a good result?  
**Answer:** No. Performance only matters when the variant still satisfies all functional and operational requirements.

**Key takeaway:** A good experiment separates three causes: auto-configuration not loaded, condition not matching, and default bean backing off for a user bean. Use ApplicationContextRunner to compare small contexts, @EnableAutoConfiguration to verify imports discovery, exclusions to remove specific integrations in a real application, and measure startup and first-use latency under identical conditions.

## 14. Official References

- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.3 — Testing Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 — Using the @SpringBootApplication Annotation](https://docs.spring.io/spring-boot/3.3/reference/using/using-the-springbootapplication-annotation.html)
- [Spring Boot 3.3 — Auto-configuration Classes](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [ApplicationContextRunner — Spring Boot 3.3 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html)
