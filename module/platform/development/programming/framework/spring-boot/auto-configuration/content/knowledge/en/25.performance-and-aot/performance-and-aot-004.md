# Distinguishing Candidate Reduction from Lazy Bean Initialization

## 1. Two Optimization Approaches Often Confused

When a Spring Boot application starts slowly, two groups of solutions are often considered:

- **Reducing auto-configuration candidates or applied configurations:** eliminating unnecessary configurations before Spring deeply parses them and registers bean definitions.
- **Lazy bean initialization:** keeping bean definitions in the ApplicationContext while creating objects only when requested for use.

These two approaches act on different phases. Reducing candidates can reduce discovery work, metadata reading, configuration parsing, condition evaluation, and bean registration. Lazy initialization primarily defers instance creation and execution of bean initialization.

If you only enable lazy initialization, the application may still have to read and process the same list of auto-configurations. If you exclude an auto-configuration, that configuration's bean definitions are not registered. This is an important distinction when optimizing a custom starter or an application with many dependencies.

This lesson uses **Java 17 and Spring Boot 3.3.13** as its illustrative baseline. When applying to another project, check the documentation for the exact release line.

## 2. Distinguishing Candidate, Condition, Bean Definition, and Bean Instance

Spring processes configuration across multiple steps. Do not call all of these steps "creating a bean."

| Concept | Meaning | Corresponding Question |
| --- | --- | --- |
| Auto-configuration candidate | Class discovered from the imports list and considered for application | Which configuration classes will be examined? |
| Condition evaluation | Evaluating classpath, property, bean, web context, or custom conditions | Does the configuration meet the conditions? |
| Bean definition | Metadata describing a bean registered in BeanFactory | Under what name/type/scope does the container know this bean exists? |
| Bean instance | Actual object created from a bean definition | Has the constructor or factory method run yet? |

A class can be a candidate yet be excluded by a condition. A bean definition can exist without an object instance because it is marked lazy. A singleton bean can be created early if another eager singleton needs to inject it.

Therefore, when saying "reduce the number of beans," specify whether you want to reduce:

- The number of auto-configuration candidates considered.
- The number of configurations passing conditions.
- The number of bean definitions registered.
- The number of instances instantiated during startup.
- Or the number of instances actually used over the application lifecycle.

## 3. Looking Through the Startup Pipeline

Simplified auto-configuration pipeline:

~~~text
AutoConfiguration.imports
          |
          v
Set of auto-configuration candidates
          |
          v
Remove exclusions and early filters
(metadata / AutoConfigurationImportFilter)
          |
          v
Parse remaining configurations
          |
          v
Evaluate @Conditional...
          |
          v
Register bean definitions
          |
          v
Create eager singleton instances
          |
          +---- Lazy bean: wait until first request
~~~

These phases have different performance impacts:

1. **Discovery/filtering:** decides which classes are examined. Filtering candidates early can avoid reading bytecode and parsing unrelated configurations.
2. **Condition/registration:** decides whether a configuration or bean method is applied and registers bean definitions.
3. **Instantiation:** constructors, factory methods, dependency injection, post-processors, and lifecycle callbacks create objects.
4. **First use:** lazy beans are instantiated when the application first requests the bean or invokes via a proxy/provider.

Lazy initialization acts primarily at steps 3 and 4. It does not remove candidates from step 1 on its own.

## 4. Reducing Auto-Configuration Candidates

### 4.1. Understanding the Candidate List in Spring Boot 3.x

In Spring Boot 3.x, a library's auto-configurations are published in the resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Example:

~~~text
com.acme.reports.autoconfigure.ReportsAutoConfiguration
com.acme.reports.autoconfigure.ReportsWebAutoConfiguration
com.acme.reports.autoconfigure.ReportsMetricsAutoConfiguration
~~~

Each line is a published auto-configuration class. Spring Boot reads these resources from dependency JARs to assemble candidates.

Do not put every imaginable configuration into imports. Split configurations by actually required integrations, such as JDBC, web, metrics, or messaging, so an application needing only one feature set does not have to parse unrelated branches.

Auto-configurations should be loaded through the imports resource and should not be scanned by the application's component scan like regular configurations. Avoid placing the auto-configuration package inside the consuming application's component scan region; avoid broad component scanning from inside auto-configurations. Use explicit @Import for related configurations.

### 4.2. Removing Unneeded Configurations with Exclusions

If the application explicitly knows an auto-configuration is unnecessary, it can exclude it from the applied list.

Using the annotation:

~~~java
@SpringBootApplication(
        exclude = DataSourceAutoConfiguration.class
)
public class ReportsApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReportsApplication.class, args);
    }
}
~~~

If you do not want to reference the class directly, you can use its fully qualified name:

~~~java
@SpringBootApplication(
        excludeName = "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration"
)
public class ReportsApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReportsApplication.class, args);
    }
}
~~~

Or configure the property:

~~~properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

Exclusion is appropriate when the application intentionally does not use an integration. Do not exclude a configuration just because its name sounds unnecessary; verify that no other bean or integration depends on it.

Exclusion removes the configuration from the imported set. It differs from lazy initialization: no default bean definitions from the excluded auto-configuration are registered.

### 4.3. Using Minimal Starters and Purpose-Built Dependencies

A starter often pulls in many dependencies. If a starter always brings JDBC, messaging, web, and metrics onto the classpath even when users only need the core API, Spring Boot will have to process additional related auto-configuration candidates.

When designing a custom starter:

- Include only dependencies needed for the default use case.
- Mark optional integration dependencies as optional in the auto-configure module when appropriate.
- Split starters by integration group if groups can be used independently.
- Do not put heavy dependencies on the classpath just to provide a rarely used feature.
- Inspect the consuming application's runtime dependency tree, not just the library module's POM.

Reducing dependencies can simultaneously lower the number of classes on the classpath, the number of potentially matching auto-configuration candidates, and class loading overhead.

### 4.4. Early Filtering with Auto-Configuration Metadata

Spring Boot has a mechanism to filter out certain auto-configurations very early. Boot's annotation processor collects supported conditions and generates the file:

~~~text
META-INF/spring-autoconfigure-metadata.properties
~~~

When this metadata is present in the JAR, Spring Boot can use it to early-exclude unsuitable auto-configurations. Certain conditions such as classpath checks can be evaluated via metadata before the auto-configuration's bytecode is read.

This is especially useful for libraries with many auto-configurations and many optional dependencies. If a required class is not on the classpath, the corresponding candidate can be excluded early.

To enable the annotation processor in Maven, add it to the auto-configure module:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.12.0</version>
            <configuration>
                <annotationProcessorPaths>
                    <path>
                        <groupId>org.springframework.boot</groupId>
                        <artifactId>spring-boot-autoconfigure-processor</artifactId>
                        <version>3.3.13</version>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

With Gradle:

~~~groovy
dependencies {
    annotationProcessor("org.springframework.boot:spring-boot-autoconfigure-processor")
}
~~~

After building, check the metadata file in the output:

~~~text
target/classes/META-INF/spring-autoconfigure-metadata.properties
~~~

This filename differs from configuration metadata meant for IDEs:

~~~text
META-INF/spring-configuration-metadata.json
~~~

The JSON file describes properties, types, descriptions, and configuration hints. The autoconfigure metadata file supports filtering auto-configurations. Do not confuse the two purposes.

Not every custom condition can be evaluated during the early filtering step. Conditions not described by the processor still need to be processed in the normal configuration parsing phase.

### 4.5. AutoConfigurationImportFilter Is a Low-Level Mechanism

Spring Boot provides the interface:

~~~java
org.springframework.boot.autoconfigure.AutoConfigurationImportFilter
~~~

The filter receives the candidate class list and metadata, then returns a boolean array indicating which candidates are imported. This interface is designed to filter out auto-configurations before their class bytecode is read.

A custom filter can be registered via META-INF/spring.factories, for example:

~~~properties
org.springframework.boot.autoconfigure.AutoConfigurationImportFilter=\
com.acme.reports.autoconfigure.ReportsImportFilter
~~~

Each element in the returned array must correspond to an input candidate; do not mutate the input list. The filter must be lightweight, deterministic, and side-effect-free.

In most libraries, prefer Spring Boot's built-in conditions and annotation processor. Write an AutoConfigurationImportFilter only when candidate-level filtering rules cannot be expressed by standard mechanisms. A buggy custom filter can accidentally drop a required configuration and cause hard-to-diagnose missing bean errors.

### 4.6. Conditions Are Not Lazy Initialization

Annotations such as:

~~~java
@ConditionalOnClass(ReportSdk.class)
@ConditionalOnProperty(
        prefix = "acme.reports",
        name = "enabled",
        havingValue = "true"
)
@ConditionalOnMissingBean(ReportClient.class)
~~~

decide whether a configuration or bean method is applied.

If a condition does not match, the corresponding bean is not registered. That is reducing configurations/bean definitions.

If the condition matches yet the bean is marked @Lazy, the bean definition is still registered and the object is created on demand. That is deferring instance creation.

A class-level condition can skip an entire configuration class; a method-level condition can prevent only a specific bean from being registered. Place conditions at the narrowest scope fitting the logic to avoid excluding too much configuration.

### 4.7. Ordering Does Not Reduce Candidates

Annotations:

~~~java
@AutoConfigureBefore(...)
@AutoConfigureAfter(...)
@AutoConfigureOrder(...)
~~~

only sort the order in which auto-configurations are applied. They do not exclude candidates and do not make beans lazy.

Do not use ordering annotations as a configuration-count optimization. Use them only when two configurations genuinely have an ordering relationship regarding bean definitions or conditions.

## 5. Deferring Bean Instantiation with Lazy Initialization

### 5.1. Lazy Beans Still Exist in the Container

When a bean is marked lazy:

~~~java
@Bean
@Lazy
ReportClient reportClient() {
    return new ReportClient();
}
~~~

Spring still registers the bean definition. When ApplicationContext refreshes, the container does not create that singleton instance immediately. The instance is created on the first request.

You can visualize it as:

| Moment | Bean Definition | Singleton Instance |
| --- | --- | --- |
| After context refresh | Yes | Not yet |
| After first getBean | Yes | Yes |
| Subsequent getBean calls | Yes | Returns the same singleton instance |

Lazy initialization does not remove the bean's name, type, scope, or metadata from the container.

### 5.2. Per-Bean Lazy

You can annotate a @Bean method:

~~~java
@Configuration(proxyBeanMethods = false)
public class ReportsConfiguration {

    @Bean
    @Lazy
    ReportClient reportClient() {
        return new ReportClient();
    }
}
~~~

Or annotate a configuration class:

~~~java
@Configuration(proxyBeanMethods = false)
@Lazy
public class OptionalReportsConfiguration {

    @Bean
    ReportClient reportClient() {
        return new ReportClient();
    }

    @Bean
    ReportHistoryClient historyClient() {
        return new ReportHistoryClient();
    }
}
~~~

Beans defined in this configuration will be lazy by default unless configured otherwise. Use this approach when an entire group of beans represents an optional feature that may go unused on some runs.

### 5.3. Enabling Application-Wide Lazy Initialization

Spring Boot allows enabling lazy initialization globally:

~~~yaml
spring:
  main:
    lazy-initialization: true
~~~

Or:

~~~properties
spring.main.lazy-initialization=true
~~~

When enabled, many application beans are instantiated on demand rather than at startup. You can opt a bean out of lazy mode with:

~~~java
@Bean
@Lazy(false)
CriticalStartupVerifier criticalStartupVerifier() {
    return new CriticalStartupVerifier();
}
~~~

Global lazy initialization is a broad behavioral change. Before enabling it in production, verify beans needed for readiness, startup validation, security, migrations, scheduled tasks, and indirectly initialized dependencies.

### 5.4. Eager Dependencies Can Pull Lazy Beans Into Startup

A common misconception: marking a bean lazy does not guarantee it is always deferred.

Example:

~~~java
@Bean
@Lazy
ReportClient reportClient() {
    return new ReportClient();
}

@Bean
ReportFacade reportFacade(ReportClient reportClient) {
    return new ReportFacade(reportClient);
}
~~~

ReportFacade is an eager singleton. When Spring creates ReportFacade, it needs ReportClient to inject as the constructor/method parameter. Thus ReportClient must also be created during startup.

To truly defer retrieving the dependency, inject ObjectProvider:

~~~java
@Bean
ReportFacade reportFacade(ObjectProvider<ReportClient> clients) {
    return new ReportFacade(clients);
}
~~~

ReportFacade is created at startup while ReportClient is only retrieved when code calls:

~~~java
ReportClient client = clients.getObject();
~~~

Another option is annotating the injection point with @Lazy so Spring injects a proxy:

~~~java
public ReportFacade(@Lazy ReportClient reportClient) {
    this.reportClient = reportClient;
}
~~~

The proxy defers resolving the target until a method is invoked. You must understand proxies and lifecycles to avoid false expectations, especially with final types or proxy-incompatible calls.

### 5.5. When Should You Use ObjectProvider?

ObjectProvider fits when a bean is only needed in one business branch:

~~~java
@Component
public class ExportService {

    private final ObjectProvider<PdfRenderer> renderers;

    public ExportService(ObjectProvider<PdfRenderer> renderers) {
        this.renderers = renderers;
    }

    public byte[] exportPdf(Report report) {
        PdfRenderer renderer = renderers.getObject();
        return renderer.render(report);
    }
}
~~~

If the application only exports CSV on some runs, PdfRenderer may not need to be created until the PDF branch is invoked.

ObjectProvider also offers operations like getIfAvailable and getIfUnique when a dependency is optional or has multiple candidates. Choose the method matching the contract; do not use getIfAvailable to hide a genuinely required dependency.

## 6. Direct Comparison of the Two Strategies

| Criterion | Reducing Candidates / Unmatched Conditions | Lazy Initialization |
| --- | --- | --- |
| Candidate in imports list | Can be excluded | Still retained |
| Configuration parsed | Can be skipped early | Usually still processed |
| Bean definition | Not registered if configuration/bean excluded | Still registered |
| Bean instance at startup | No instance from excluded beans | May have no instance yet |
| Startup work | Can reduce discovery, parsing, conditions, and registration | Reduces constructor/lifecycle work of lazy beans |
| First-use cost | No bean to use if excluded | May increase due to initialization at first use |
| Configuration errors | Unmatched condition visible in report; bean not created | Constructor/dependency errors may surface only when bean is requested |
| Memory | Can reduce related metadata/definitions/instances | Can reduce temporary instances; if all beans are eventually used, savings may be small |
| Best suited for | Unused integrations, optional dependencies, unrelated auto-configurations | Heavy, rarely used beans, infrequently accessed feature branches |

Examples:

- Application does not use JDBC: remove the dependency or intentionally exclude DataSourceAutoConfiguration. Lazy initialization does not make JDBC configuration disappear from the candidate list.
- Application has PDF export functionality but most requests export CSV: keep the PDF bean in the context and use lazy/ObjectProvider to create it only when needed.
- Library has an optional SDK: use @ConditionalOnClass and optional dependencies so the bean is not registered when the SDK is absent. Do not use @Lazy to replace a classpath condition.

## 7. Complete Maven Example: Condition Excludes Bean and Lazy Defers Instance

The example uses **Java 17 and Spring Boot 3.3.13**. A custom auto-configuration creates ReportClient when a property is enabled. The bean is marked lazy to illustrate that the bean definition still exists even though the instance has not been created.

### 7.1. Project Structure

~~~text
lazy-vs-candidate-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/app/
    │   │   └── ReportsDemoApplication.java
    │   ├── java/com/example/lib/
    │   │   ├── ReportClient.java
    │   │   └── autoconfigure/
    │   │       └── ReportsAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/com/example/lib/autoconfigure/
            └── ReportsAutoConfigurationTests.java
~~~

The library package lies outside the application's component scan package. Spring Boot discovers the auto-configuration through the imports resource.

### 7.2. pom.xml

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

    <groupId>com.example</groupId>
    <artifactId>lazy-vs-candidate-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
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

**src/main/java/com/example/lib/ReportClient.java**

~~~java
package com.example.lib;

public record ReportClient(String endpoint) {
}
~~~

### 7.4. ReportsAutoConfiguration.java

**src/main/java/com/example/lib/autoconfigure/ReportsAutoConfiguration.java**

~~~java
package com.example.lib.autoconfigure;

import com.example.lib.ReportClient;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Lazy;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.reports",
        name = "enabled",
        havingValue = "true")
public class ReportsAutoConfiguration {

    @Bean
    @Lazy
    ReportClient reportClient() {
        return new ReportClient("https://reports.example.test");
    }
}
~~~

When the property is absent or not true, the auto-configuration is not applied and the reportClient bean definition is not registered.

When the property is true, the bean definition is registered. Due to @Lazy, the ReportClient singleton is not created during refresh if no eager bean depends directly on it.

### 7.5. AutoConfiguration.imports

Create the file:

**src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**

~~~text
com.example.lib.autoconfigure.ReportsAutoConfiguration
~~~

This resource publishes the candidate for Spring Boot 3.x. To verify candidate discovery from a packaged JAR, run an independent consumer application adding only the starter or autoconfigure artifact. The tests using AutoConfigurations.of below load the class directly, so they focus on verifying conditions and bean lifecycle.

### 7.6. ReportsDemoApplication.java

**src/main/java/com/example/app/ReportsDemoApplication.java**

~~~java
package com.example.app;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReportsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReportsDemoApplication.class, args);
    }
}
~~~

To enable the feature when running:

~~~properties
acme.reports.enabled=true
~~~

Run the application:

~~~bash
mvn spring-boot:run
~~~

Because no eager bean injects ReportClient in this example, the bean definition can exist while the instance is not created until a consumer requests it.

## 8. Testing Bean Definition vs. Singleton Instance

**src/test/java/com/example/lib/autoconfigure/ReportsAutoConfigurationTests.java**

~~~java
package com.example.lib.autoconfigure;

import com.example.lib.ReportClient;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class ReportsAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    ReportsAutoConfiguration.class));

    @Test
    void disabledFeatureDoesNotRegisterBeanDefinition() {
        runner.withPropertyValues("acme.reports.enabled=false")
                .run(context -> {
                    assertThat(context).doesNotHaveBean(ReportClient.class);

                    assertThat(context.getBeanFactory()
                            .containsBeanDefinition("reportClient"))
                            .isFalse();

                    assertThat(context.getBeanFactory()
                            .containsSingleton("reportClient"))
                            .isFalse();
                });
    }

    @Test
    void enabledFeatureRegistersDefinitionButDefersInstance() {
        runner.withPropertyValues("acme.reports.enabled=true")
                .run(context -> {
                    assertThat(context).hasBean("reportClient");

                    assertThat(context.getBeanFactory()
                            .containsBeanDefinition("reportClient"))
                            .isTrue();

                    assertThat(context.getBeanFactory()
                            .containsSingleton("reportClient"))
                            .isFalse();

                    ReportClient client =
                            context.getBean("reportClient", ReportClient.class);

                    assertThat(client.endpoint())
                            .isEqualTo("https://reports.example.test");

                    assertThat(context.getBeanFactory()
                            .containsSingleton("reportClient"))
                            .isTrue();
                });
    }

    @Test
    void eagerConsumerForcesLazyDependencyDuringRefresh() {
        runner.withPropertyValues("acme.reports.enabled=true")
                .withUserConfiguration(EagerConsumerConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(EagerFacade.class);

                    assertThat(context.getBeanFactory()
                            .containsBeanDefinition("reportClient"))
                            .isTrue();

                    assertThat(context.getBeanFactory()
                            .containsSingleton("reportClient"))
                            .isTrue();
                });
    }

    @Test
    void objectProviderDefersDependencyUntilItIsRequested() {
        runner.withPropertyValues("acme.reports.enabled=true")
                .withUserConfiguration(DeferredConsumerConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(DeferredFacade.class);

                    assertThat(context.getBeanFactory()
                            .containsSingleton("reportClient"))
                            .isFalse();

                    DeferredFacade facade =
                            context.getBean(DeferredFacade.class);

                    ReportClient client = facade.getClient();

                    assertThat(client.endpoint())
                            .isEqualTo("https://reports.example.test");

                    assertThat(context.getBeanFactory()
                            .containsSingleton("reportClient"))
                            .isTrue();
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class EagerConsumerConfiguration {

        @Bean
        EagerFacade eagerFacade(ReportClient client) {
            return new EagerFacade(client);
        }
    }

    record EagerFacade(ReportClient client) {
    }

    @Configuration(proxyBeanMethods = false)
    static class DeferredConsumerConfiguration {

        @Bean
        DeferredFacade deferredFacade(
                ObjectProvider<ReportClient> clients) {
            return new DeferredFacade(clients);
        }
    }

    static class DeferredFacade {

        private final ObjectProvider<ReportClient> clients;

        DeferredFacade(ObjectProvider<ReportClient> clients) {
            this.clients = clients;
        }

        ReportClient getClient() {
            return this.clients.getObject();
        }
    }
}
~~~

Run tests:

~~~bash
mvn clean test
~~~

Expected **four passing tests**:

1. Feature disabled: no bean definition and no singleton instance.
2. Feature enabled: bean definition exists yet singleton is not created; first getBean call creates the instance.
3. Eager bean directly injects ReportClient: lazy dependency is still created during refresh to satisfy injection.
4. Eager bean injects ObjectProvider: ReportClient remains uncreated until provider.getObject() is called.

The two key assertions in the example are:

~~~java
context.getBeanFactory().containsBeanDefinition("reportClient")
context.getBeanFactory().containsSingleton("reportClient")
~~~

The first assertion checks the bean definition. The second checks whether the singleton instance has been created yet. They do not answer the same question.

## 9. How Does AOT Relate to Candidate Filtering and Lazy Initialization?

### 9.1. AOT Is a Build-Time Optimization

Spring AOT analyzes the ApplicationContext during the build and generates optimized code/hints for the application. AOT is a required step when building a Spring ApplicationContext into a native image.

With Spring Boot, AOT prepares the BeanFactory at build time. Conditions are also evaluated during this process. That means:

- The classpath used during AOT must represent the runtime classpath.
- Profiles affecting beans must be selected accurately during build.
- Properties affecting whether a bean is registered need appropriate values in the AOT build environment.
- You cannot expect changing a property condition at runtime to create a bean that AOT did not generate.

For example, if you build AOT with:

~~~properties
acme.reports.enabled=false
~~~

then the auto-configuration may not be included in the AOT configuration. Running the resulting binary later with enabled=true cannot add a bean excluded during build-time processing.

### 9.2. AOT Does Not Mean Lazy Initialization

AOT and lazy initialization solve different problems:

| Mechanism | Decision Time | Primary Impact |
| --- | --- | --- |
| Candidate filtering | When importing auto-configurations | Excludes classes not needing examination |
| Condition evaluation | When processing configurations; in AOT, build-time | Decides whether bean definitions are registered |
| Lazy initialization | When ApplicationContext runs | Defers instance creation until requested |
| AOT processing | Build-time | Generates code/hints and prepares context for chosen classpath/Environment |

A bean kept in an AOT-generated context can still be configured lazy if its bean definition and usage support it. AOT does not turn @Lazy into exclusion and does not turn exclusion into lazy.

### 9.3. Running AOT with Maven

You can invoke the process-aot goal of the Spring Boot Maven Plugin:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <id>process-aot</id>
            <goals>
                <goal>process-aot</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

After configuring the plugin, run:

~~~bash
mvn spring-boot:process-aot
~~~

With a project using the Spring Boot parent and native build tools configured, the native profile can assist the workflow:

~~~bash
mvn -Pnative package
~~~

The native command requires an appropriate GraalVM/native build tools environment. Running process-aot alone does not mean a native executable has been built.

Before enabling AOT in CI, pass the exact profiles and properties affecting conditions into the process-aot environment. Verify that profiles/conditions yield the same results between build and deployment environments.

## 10. Measuring Performance Properly

Do not conclude one strategy is faster from a single startup run or by looking only at bean count.

### 10.1. Measuring Startup Steps

Spring Boot supports ApplicationStartup to track steps during startup. You can use BufferingApplicationStartup:

~~~java
@SpringBootApplication
public class ReportsApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ReportsApplication.class);

        application.setApplicationStartup(
                new BufferingApplicationStartup(2048));

        application.run(args);
    }
}
~~~

When Actuator and the startup endpoint are configured, you can collect startup data to pinpoint time-consuming steps. Java Flight Recorder is also useful to observe class loading, allocations, garbage collection, and JVM activity.

### 10.2. Measure First-Use Latency as Well

When lazy initialization is enabled, startup may be faster, yet the first request calling a bean pays the initialization cost. Therefore, measure at least:

- Time from process start to ApplicationReadyEvent.
- Time from readiness until the first request completes.
- Latency of the first request using the lazy bean.
- Steady-state latency after warm-up.
- Heap usage and allocations after startup and after features have been exercised.

Do not measure only startup time and claim lazy always improves performance. For services receiving traffic immediately after readiness, first-use delay can impact user experience or autoscaling.

### 10.3. Designing a Fair Benchmark

When comparing:

1. Use the same JDK, container limits, heap, CPU, dependency graph, and configuration.
2. Run multiple iterations, discarding the first if class-loading/JIT effects skew it, or report cold-start separately.
3. Compare median and p95 rather than picking only the fastest run.
4. Use the same workload and the same readiness definition.
5. Record the number of imported auto-configurations, bean definitions, and singleton instances.
6. Measure both startup and first-use; do not ignore cost shifted to the first request.

An experiment can compare three variants:

| Variant | Candidate/Condition | Lazy |
| --- | --- | --- |
| A | Keep default configuration | Off |
| B | Exclude unused integrations | Off |
| C | Keep optional beans | Enabled for selected beans |

Only from the results should you decide whether to trim dependencies, exclude configurations, or defer instances.

## 11. Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Enabled lazy yet auto-configuration candidate count did not drop | Lazy only defers instance creation | Use minimal dependencies, exclusions, or early filtering where appropriate |
| Bean definition still exists though bean is not created | Inspecting a lazy bean | Distinguish containsBeanDefinition from containsSingleton |
| Marked @Lazy yet bean is still created at startup | An eager singleton directly injects the lazy bean | Use ObjectProvider or @Lazy at injection point if deferral is truly desired |
| Feature disabled yet bean still exists | Condition placed on wrong class/method or property differs from expected | Check Condition Evaluation Report and condition placement |
| Excluding an auto-configuration leaves the application missing many beans | Excluded configuration provides prerequisites for other integrations | Verify inter-configuration dependencies before excluding |
| Adding multiple starters slows startup | Classpath gained extra dependencies and auto-configurations | Split optional integrations and include only needed dependencies in starters |
| Annotation processor does not generate autoconfigure metadata | Processor not configured in the auto-configure module | Add spring-boot-autoconfigure-processor to annotationProcessorPaths/annotationProcessor |
| Confusing configuration metadata with autoconfigure metadata | The two files serve different purposes | Distinguish spring-configuration-metadata.json from spring-autoconfigure-metadata.properties |
| Writing overly complex custom AutoConfigurationImportFilter | Using a low-level SPI for ordinary condition rules | Prefer built-in conditions and processor |
| Using @AutoConfigureBefore hoping to exclude candidates | Ordering only arranges application order | Use exclusions/filters/conditions for the intended purpose |
| Startup is fast yet first request is slow | Lazy shifted cost to first use | Intentional warm-up or keep critical beans eager |
| Configuration error appears only on first request | Lazy bean was not instantiated at startup | Add smoke tests or check critical beans before readiness |
| AOT built with properties different from production | Conditions were evaluated at build-time | Synchronize profiles/properties during process-aot |
| Changing runtime property yet AOT bean does not appear | Condition was decided at build-time | Rebuild with proper environment or design runtime feature toggle inside created bean |

## 12. Custom Starter Optimization Checklist

### Reducing Candidates and Configuration Work

- [ ] AutoConfiguration.imports lists only genuinely supported configurations.
- [ ] Auto-configurations are not inadvertently component-scanned.
- [ ] Optional integrations have separate dependencies and appropriate conditions.
- [ ] Applications exclude unused configurations via intentional exclusions.
- [ ] Auto-configure module uses spring-boot-autoconfigure-processor.
- [ ] Verified spring-autoconfigure-metadata.properties in built artifacts.
- [ ] Ordering annotations are not used as a filtering tool.

### Lazy Initialization

- [ ] Only mark beans lazy if they may genuinely go unused.
- [ ] Checked whether eager dependencies pull lazy beans into startup.
- [ ] Used ObjectProvider or lazy proxies when dependency deferral is needed.
- [ ] Kept required beans eager to validate startup/readiness.
- [ ] Measured first-use latency and memory after bean creation.
- [ ] Added tests catching lazy bean initialization failures before release.

### AOT and Measurement

- [ ] Built AOT with accurate classpath, profiles, and condition-affecting properties.
- [ ] Verified conditions produce expected results in the build-time environment.
- [ ] Do not expect runtime properties to recreate beans excluded during AOT.
- [ ] Measured startup steps with ApplicationStartup or JFR.
- [ ] Compared startup, first-use latency, p95, and memory using the same workload.

## 13. Self-Check Questions

**Question 1.** How does an auto-configuration candidate differ from a bean instance?  
**Answer:** A candidate is a class considered for application; a bean instance is the actual object created later from a bean definition.

**Question 2.** If an auto-configuration is excluded, are its default bean definitions registered?  
**Answer:** No. The configuration is removed from the set of imported configurations.

**Question 3.** If a bean is marked @Lazy, does its bean definition disappear?  
**Answer:** No. The bean definition remains; only the instance is created on demand.

**Question 4.** Why can an eager bean cause a @Lazy dependency to be created at startup?  
**Answer:** Spring needs to resolve dependencies to create the eager bean. When injecting the instance directly, the lazy dependency must be instantiated to satisfy injection.

**Question 5.** How does ObjectProvider help defer a dependency?  
**Answer:** The consumer is injected with the provider first; the target bean is retrieved only when calling getObject or an equivalent method.

**Question 6.** What is spring-autoconfigure-metadata.properties used for?  
**Answer:** It contains condition metadata generated by the annotation processor so Spring Boot can early-filter unsuitable auto-configurations.

**Question 7.** When does AOT evaluate conditions?  
**Answer:** During build-time processing. Classpath, profiles, and properties affecting bean registration must match the build environment.

**Question 8.** When enabling lazy, why should you measure the first request?  
**Answer:** Bean creation cost shifts from startup to first use; faster startup can come with higher first-use latency.

**Question 9.** Does @AutoConfigureAfter reduce the number of candidates?  
**Answer:** No. It only suggests the order in which auto-configurations are applied.

**Question 10.** To verify a lazy bean has a definition yet no instance, what do you check?  
**Answer:** containsBeanDefinition(name) must be true and containsSingleton(name) must be false before the first lookup.

## 14. Official References

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 — SpringApplication and Lazy Initialization](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [AutoConfigurationImportFilter — Spring Boot 3.3.13 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurationImportFilter.html)
- [Ahead-of-Time Processing — Spring Boot 3.3.13](https://docs.spring.io/spring-boot/3.3/maven-plugin/aot.html)
- [Lazy-initialized Beans — Spring Framework](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-lazy-init.html)

**Takeaway:** Reducing candidates gives Spring less configuration to examine and apply; unmatched conditions prevent bean definitions from being registered; lazy initialization keeps definitions while deferring instances. AOT shifts context analysis and condition evaluation to build-time. Choose the right phase to optimize, then measure startup, first-use latency, and memory before deciding on a strategy.
