# Enable the Auto-Configuration Report with --debug or debug=true

## 1. What is the Condition Report Used For?

Spring Boot Auto Configuration automatically decides which configurations are suitable for the application based on the classpath, registered beans, properties, web application type, and many other conditions. When a bean or an auto-configuration does not appear as expected, common questions are:

- Was that auto-configuration discovered?
- Did `@ConditionalOnClass` find the required class?
- Did `@ConditionalOnProperty` receive the right configuration value?
- Did `@ConditionalOnBean` see the dependent bean?
- Did `@ConditionalOnMissingBean` detect a bean declared by the application itself?
- Why was a configuration applied or skipped?

Spring Boot provides the **Condition Evaluation Report** to explain many of these decisions. You can instruct Spring Boot to display the report when the application starts in one of two ways:

~~~bash
java -jar target/my-app.jar --debug
~~~

Or declare the property:

~~~properties
debug=true
~~~

In YAML:

~~~yaml
debug: true
~~~

Both approaches enable Spring Boot's debug mode, which includes the auto-configuration condition report. This is a very useful diagnostic tool when developing starters, libraries, or applications that use many auto-configurations.

**Key takeaway:** `--debug` or `debug=true` enables the condition report and debug logging for a core group of loggers selected by Spring Boot. They **do not mean setting the entire application to DEBUG**, do not automatically enable a Java remote debugger, and do not automatically expose an HTTP endpoint.

## 2. Two Ways to Enable the Report

### 2.1. Using the --debug Command-Line Argument

When running a JAR:

~~~bash
java -jar target/my-app.jar --debug
~~~

You can write it explicitly:

~~~bash
java -jar target/my-app.jar --debug=true
~~~

This is an application argument following Spring Boot syntax. Make sure the argument is passed to the application process, not just set as a parameter for Maven/Gradle that the build plugin does not forward.

With the Maven Spring Boot Plugin:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

In Maven, you can pass multiple application arguments in the same string:

~~~bash
mvn spring-boot:run "-Dspring-boot.run.arguments=--debug --acme.reports.enabled=true"
~~~

With Gradle:

~~~bash
./gradlew bootRun --args='--debug'
~~~

On Windows PowerShell, you can use the wrapper and double quotes:

~~~powershell
.\gradlew.bat bootRun --args="--debug"
~~~

If running from an IDE, add `--debug` to **Program arguments** in the Run Configuration. Do not put it in VM options: VM options are for the JVM, whereas `--debug` is a Spring Boot application argument.

### 2.2. Using the debug=true Property

In `application.properties`:

~~~properties
debug=true
~~~

In `application.yml`:

~~~yaml
debug: true
~~~

You can place the property in a profile-specific configuration file, such as `application-dev.yml`, if you want to enable this mode in the development environment. Keep in mind that the property can be overridden by a configuration source with higher precedence.

You can also use:

~~~bash
java -jar target/my-app.jar --debug=false
~~~

to disable the mode enabled by a lower-precedence configuration source, depending on the property source precedence order. Spring Boot command-line arguments generally have higher precedence than application configuration files.

### 2.3. Which Approach Should You Choose?

| Need | Recommended Approach |
| --- | --- |
| Quick one-off diagnosis on a dev machine | Add `--debug` when running |
| Enable by default for the development profile | `debug=true` in `application-dev.yml` |
| Inspect a packaged application in a test environment | Pass `--debug` to the JAR run command |
| Want to toggle per deployment | Use a property or command-line argument per environment |
| Want an entire specific package to have DEBUG logs | Configure `logging.level.<logger>` separately |

Do not leave debug mode enabled indefinitely in production if unnecessary: logs can become longer and expose more information about the application's structure. Manage logs and access permissions just as with other operational logs.

## 3. What Does the Condition Evaluation Report Display?

When debug mode is enabled, Spring Boot outputs the condition report for the auto-configurations that participated in evaluation. Depending on the version and configuration type, the report typically includes these groups:

- **Positive matches:** conditions that matched. For example, a required class is present, a property has the right value, or no replacement bean exists yet.
- **Negative matches:** conditions that did not match. This is usually the first place to look when a default bean does not appear.
- **Exclusions:** auto-configurations that were explicitly excluded.
- **Unconditional classes:** configurations without corresponding conditions.

The report can list results at both the auto-configuration class level and the `@Bean` method level. A class may be loaded while a bean method inside it is filtered out by a condition; therefore, read the exact class/method name rather than just seeing the class name in the log.

### Example of Reading a Result

Suppose a library has a default bean:

~~~java
@Bean
@ConditionalOnProperty(
        prefix = "acme.reports",
        name = "enabled",
        havingValue = "true")
@ConditionalOnMissingBean(ReportClient.class)
ReportClient reportClient() {
    return new ReportClient();
}
~~~

If the configuration is:

~~~yaml
acme:
  reports:
    enabled: false
~~~

The `@ConditionalOnProperty` condition does not match. The report will indicate that the bean method was not registered because the property value did not satisfy the condition. The exact wording/log line varies by version, but the meaning to look for is:

~~~text
Negative matches:
   ReportsAutoConfiguration#reportClient
      - ConditionalOnProperty: acme.reports.enabled
        did not match (property value was not true)
~~~

This is a **simplified illustration to explain the structure**, not a verbatim copy of fixed log output across all Spring Boot versions.

If you change the property to `true` and there is no application-provided ReportClient, the matching conditions will appear under Positive matches:

~~~text
Positive matches:
   ReportsAutoConfiguration#reportClient
      - ConditionalOnProperty: acme.reports.enabled matched
      - ConditionalOnMissingBean: no ReportClient bean found
~~~

If the application has already declared its own ReportClient, the `@ConditionalOnMissingBean` condition no longer matches; the default bean is skipped. The report helps distinguish between **the feature being disabled** and **the application already providing a replacement bean**.

## 4. Workflow for Reading the Report by Problem

When an expected bean does not appear, follow this sequence:

1. **Find the exact auto-configuration or bean method.** Use the fully qualified class name or `@Bean` method name; do not infer from a generic log line.
2. **Read Negative matches first.** Look for the unmatched condition and its reason: missing class, wrong property, missing prerequisite bean, unsuitable web type, or existing replacement bean.
3. **Read Positive matches to confirm which conditions passed.** An auto-configuration can have multiple conditions; one passing condition does not mean every other condition also passed.
4. **Check Exclusions.** An auto-configuration can be excluded via `exclude`, `excludeName`, `spring.autoconfigure.exclude`, or an equivalent exclusion mechanism.
5. **Check the actual configuration.** Cross-check keys, values, active profiles, command-line arguments, and environment variables. The condition report shows the evaluation outcome; it does not always show the full origin of every value.
6. **Check user-declared beans.** A bean of the same type can cause `@ConditionalOnMissingBean` not to match. That may be the intended behavior.
7. **Check errors after the condition phase.** Conditions may match, yet the bean still fails to initialize due to a constructor dependency, an exception in a factory method, or a connection error.

### Reading by Condition Type

| Condition | Question When Reading the Report | Common Remediation |
| --- | --- | --- |
| `@ConditionalOnClass` | Is the required class on the runtime classpath? | Check dependency scope, excluded dependencies, and library version |
| `@ConditionalOnMissingClass` | Which class is present and causing the condition not to match? | Check the classpath and the purpose of the fallback branch |
| `@ConditionalOnProperty` | Does the property exist and have the expected value? | Check prefix, key, profile, and override sources |
| `@ConditionalOnBean` | Was the prerequisite bean registered when the condition was evaluated? | Check ordering between auto-configuration and user beans |
| `@ConditionalOnMissingBean` | Is there already a bean of the same type/name causing the default to back off? | Check custom beans, return type, and search scope |
| `@ConditionalOnWebApplication` | Does the application have the right web application type? | Check web dependencies and application type |
| `@ConditionalOnResource` | Is the required resource on the classpath? | Check resource path and packaging |

**An unmatched condition is not necessarily a bug.** For example, if an auto-configuration provides a default only when a custom bean is missing, a Negative match on `@ConditionalOnMissingBean` can be completely correct. Always compare against the design intent.

## 5. Complete Runnable Example: Enabling and Reading the Condition Report

The example below uses Java 17+ and Spring Boot 3.3.5. We create a conditional auto-configuration so we can observe both Positive and Negative matches.

### 5.1. Project Structure

~~~text
condition-report-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/
    │   │   ├── app/
    │   │   │   └── DemoApplication.java
    │   │   └── library/
    │   │       ├── ReportClient.java
    │   │       └── autoconfigure/
    │   │           └── ReportsAutoConfiguration.java
    │   └── resources/
    │       ├── application.yml
    │       └── META-INF/spring/
    │           └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/com/example/app/
            └── ReportsAutoConfigurationTest.java
~~~

The application package is `com.example.app`; the simulated library package is `com.example.library`. By separating packages, the application's default component scan does not automatically scan the auto-configuration. Spring Boot discovers the library class via the `AutoConfiguration.imports` resource, just as when the library is packaged as a separate JAR.

### 5.2. pom.xml

~~~xml
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
    <groupId>com.example</groupId>
    <artifactId>condition-report-demo</artifactId>
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
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

### 5.3. ReportClient.java

**src/main/java/com/example/library/ReportClient.java**

~~~java
package com.example.library;

public record ReportClient(String endpoint) {
    public String describe() {
        return "ReportClient endpoint=" + endpoint;
    }
}
~~~

This is a Java 17 record that simply stores an endpoint to illustrate the created bean. The example does not send real HTTP requests.

### 5.4. ReportsAutoConfiguration.java

**src/main/java/com/example/library/autoconfigure/ReportsAutoConfiguration.java**

~~~java
package com.example.library.autoconfigure;

import com.example.library.ReportClient;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class ReportsAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "acme.reports",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false)
    @ConditionalOnMissingBean(ReportClient.class)
    ReportClient reportClient() {
        return new ReportClient("https://reports.example.invalid");
    }
}
~~~

There are two conditions:

- `@ConditionalOnProperty` only allows registering the default client when `acme.reports.enabled=true`. An absent property is treated as not matching because `matchIfMissing=false`.
- `@ConditionalOnMissingBean` only registers the default if the application has not already provided a `ReportClient`.

### 5.5. Registering the Auto-Configuration

Create the file:

**src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**

~~~text
com.example.library.autoconfigure.ReportsAutoConfiguration
~~~

This is the fully qualified class name for Spring Boot to discover the auto-configuration. Without this resource, the class may not be processed through the auto-configuration mechanism even though the Java code compiles successfully.

### 5.6. application.yml

**src/main/resources/application.yml**

~~~yaml
debug: false

acme:
  reports:
    enabled: false
~~~

To start, the feature is disabled. We will enable the report using the `--debug` command-line argument, then change the feature value to observe the condition outcomes.

### 5.7. DemoApplication.java

**src/main/java/com/example/app/DemoApplication.java**

~~~java
package com.example.app;

import com.example.library.ReportClient;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CommandLineRunner inspect(ObjectProvider<ReportClient> provider) {
        return args -> {
            ReportClient client = provider.getIfAvailable();
            System.out.println(
                    "reportClient=" +
                    (client == null ? "absent" : client.describe()));
        };
    }
}
~~~

Using `ObjectProvider` allows the demo to start in both cases: with or without a ReportClient. If a required `ReportClient` were injected directly, the application would fail at startup when the property is off and the bean does not exist; in that case it would be harder to observe the Negative match result via the runner.

### 5.8. Running When the Feature Is Disabled

From the directory containing pom.xml:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

Because `application.yml` sets `acme.reports.enabled=false`, the Condition Evaluation Report will show that the `reportClient` method did not match the property condition. The runner's output line is:

~~~text
reportClient=absent
~~~

In the log, find the **Negative matches** group and the name `ReportsAutoConfiguration#reportClient`. You will see that the `acme.reports.enabled` condition was not satisfied. Message details may vary depending on the version and how properties are bound.

### 5.9. Running When the Feature Is Enabled

Pass both the debug flag and the property enabling the feature:

~~~bash
mvn spring-boot:run "-Dspring-boot.run.arguments=--debug --acme.reports.enabled=true"
~~~

Runner output:

~~~text
reportClient=ReportClient endpoint=https://reports.example.invalid
~~~

This time `@ConditionalOnProperty` matches and `@ConditionalOnMissingBean` matches because no replacement bean exists yet. Look for the method name `reportClient` in the **Positive matches** group of the Condition Evaluation Report.

You can run the packaged JAR in an equivalent way:

~~~bash
mvn package
java -jar target/condition-report-demo-1.0.0.jar --debug --acme.reports.enabled=true
~~~

The two Maven commands above are **two separate runs**: one to observe the feature disabled and one to observe the feature enabled.

### 5.10. Verifying That a Custom Bean Causes the Default to Back Off

In a real application, you can provide your own ReportClient. When you do, `@ConditionalOnMissingBean` prevents the default bean from being registered, even though the feature is enabled.

Create a custom configuration class (if you want to test with the running application):

~~~java
package com.example.app;

import com.example.library.ReportClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class CustomReportConfiguration {

    @Bean
    ReportClient customReportClient() {
        return new ReportClient("https://custom.example.invalid");
    }
}
~~~

The class is in the `com.example.app` package, so it is discovered by DemoApplication's component scan. Run again with:

~~~bash
mvn spring-boot:run "-Dspring-boot.run.arguments=--debug --acme.reports.enabled=true"
~~~

The runner will print:

~~~text
reportClient=ReportClient endpoint=https://custom.example.invalid
~~~

In the report, `@ConditionalOnProperty` still matches, but `@ConditionalOnMissingBean` does not match because the custom bean was found. **This is not an error:** the library is yielding bean ownership to the application exactly as contracted.

If you added `CustomReportConfiguration`, delete that class or exclude it from component scanning when you want to return to the default bean experiment in section 5.9.

## 6. Testing Conditions Independently with ApplicationContextRunner

The debug report is great for investigating at runtime, but a library should have automated tests for its condition branches. The `spring-boot-starter-test` dependency is already in the POM.

**src/test/java/com/example/app/ReportsAutoConfigurationTest.java**

~~~java
package com.example.app;

import com.example.library.ReportClient;
import com.example.library.autoconfigure.ReportsAutoConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class ReportsAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    ReportsAutoConfiguration.class));

    @Test
    void createsDefaultClientWhenEnabled() {
        runner.withPropertyValues("acme.reports.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportClient.class);
                    assertThat(context.getBean(ReportClient.class).endpoint())
                            .isEqualTo(
                                    "https://reports.example.invalid");
                });
    }

    @Test
    void doesNotCreateClientWhenDisabled() {
        runner.withPropertyValues("acme.reports.enabled=false")
                .run(context ->
                        assertThat(context).doesNotHaveBean(ReportClient.class));
    }

    @Test
    void missingPropertyDoesNotEnableClient() {
        runner.run(context ->
                assertThat(context).doesNotHaveBean(ReportClient.class));
    }

    @Test
    void backsOffWhenApplicationProvidesClient() {
        runner.withPropertyValues("acme.reports.enabled=true")
                .withUserConfiguration(CustomClientConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportClient.class);
                    assertThat(context.getBean(ReportClient.class).endpoint())
                            .isEqualTo("https://custom.example.invalid");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomClientConfiguration {
        @Bean
        ReportClient customReportClient() {
            return new ReportClient("https://custom.example.invalid");
        }
    }
}
~~~

Run:

~~~bash
mvn test
~~~

Expect **four passing tests**. They verify property true, property false, missing property, and custom bean. ApplicationContextRunner lets you test auto-configuration in isolation without running the entire application or enabling debug logging in every test.

## 7. Distinguishing --debug from logging.level and Actuator

Three mechanisms are often confused:

| Tool | Purpose | Automatically Enables Condition Evaluation Report? |
| --- | --- | --- |
| `--debug` or `debug=true` | Enables Spring Boot debug mode and the condition report | **Yes**, via Boot's condition reporting mechanism |
| `logging.level.root=DEBUG` | Sets the log level for the root logger | Not a reliable substitute for the debug flag |
| `logging.level.com.example=DEBUG` | Enables DEBUG logging for a specific package | Does not automatically enable the Condition Evaluation Report |
| Actuator `/actuator/conditions` | Endpoint for observing runtime conditions when Actuator/endpoint is configured | A separate mechanism requiring appropriate dependency and exposure/access |

For example, if you only want DEBUG logs for your application package:

~~~yaml
logging:
  level:
    com.example: DEBUG
~~~

This is not equivalent to:

~~~yaml
debug: true
~~~

Conversely, `debug: true` also **does not mean every logger in the application is set to DEBUG**. Spring Boot selects a core group of loggers to provide additional diagnostic information. If you need detailed logs for a specific package, configure the appropriate `logging.level` alongside the debug flag.

### Actuator Conditions Endpoint

If the application includes Spring Boot Actuator and the `conditions` endpoint is enabled/exposed, you can query:

~~~text
/actuator/conditions
~~~

This endpoint presents condition information over HTTP. It differs from the report written to startup logs when using `--debug`. Do not assume that adding `debug=true` will automatically add Actuator, expose the endpoint, or open access. In production, expose only necessary endpoints and secure access; the condition report can reveal class names, properties, and internal structure.

## 8. What the Report Contains and Does Not Contain

**The report is useful for answering:**

- Which conditions on an evaluated auto-configuration matched or did not match?
- Because of which property or replacement bean was a bean method skipped?
- Is a required class present on the classpath?
- Was a configuration excluded?
- Because of which conditions was an auto-configuration applied?

**The report does not replace:**

- Stack traces when a bean constructor/factory method throws an exception.
- Tracing every method call in the application.
- Debugger breakpoints or remote JVM debugging.
- Full origin analysis of every property and all secret values.
- Verifying that a real database/HTTP connection actually works.
- Testing the business behavior of a bean after initialization.

An auto-configuration may **match** yet the bean still fails to initialize because another dependency cannot be resolved. Conversely, an unmatched condition can be intentional design: for example, the user already provided a replacement bean. Read the report together with startup exceptions, the dependency tree, actual configuration, and tests.

If an auto-configuration does not appear in the report at all, check whether it is on the classpath, whether the `AutoConfiguration.imports` resource is packaged properly, whether the class is excluded, and whether the artifact has the right version. The condition report cannot explain in detail a class that never became a loaded candidate.

## 9. Common Errors and How to Handle Them

| Symptom | Possible Cause | How to Check / Fix |
| --- | --- | --- |
| Running with `--debug` but no report appears | Argument was not forwarded to the application, or looking at the wrong log | Check Run Configuration/Maven/Gradle arguments and startup output |
| Set `debug=true` but command line has `--debug=false` | Command-line source overrides configuration file | Remove the override or pass true |
| Bean does not appear and Negative match says wrong property | Wrong prefix/key, incorrect value, different profile, or override source | Cross-check canonical key, property sources, and active profiles |
| `@ConditionalOnMissingBean` does not match | Application/another starter already registered a matching bean | Check the bean type and determine whether this is intended behavior |
| Auto-configuration missing from report | Not discovered, missing resource/import, or excluded | Check dependencies, JAR resources, and exclusions |
| Condition matches but startup still fails | Error occurs during bean creation or dependency injection | Read the root stack trace and constructor/factory method |
| Log is too long | Debug enabled in an environment with many auto-configurations | Enable only when needed, store logs safely, and disable after diagnosis |
| Expecting all classes to log at DEBUG | Mistaking the debug flag for root logger DEBUG | Configure `logging.level` for the specific package/logger |
| Thinking `--debug` enables a debugger | Confusing debug logging with JVM debugging | Use a separate debugger/JPDA if breakpoints are needed |

## 10. Quick Diagnostic Checklist

When an auto-configured bean does not appear:

1. Re-run with `--debug` or enable `debug=true`.
2. Find the auto-configuration name and bean method under **Negative matches**.
3. Read the first unmatched condition; fix the actual root cause instead of guessing.
4. If a property is wrong, check the canonical key, active profile, command-line args, and environment variables.
5. If a prerequisite bean is missing, check the classpath, auto-configuration ordering, and `@ConditionalOnBean`.
6. If the default bean backed off, check custom beans and `@ConditionalOnMissingBean`.
7. If conditions match but startup fails, read the stack trace and inspect the bean creation step.
8. Write an `ApplicationContextRunner` test for the fixed branch to prevent regressions.
9. Disable debug after diagnosis if the environment does not need those logs regularly.

Do not start by adding `@Primary` or changing dependency order before knowing which condition failed. `@Primary` only selects a candidate at injection time; it does not make a bean-registration condition match.

## 11. Self-Check Questions

**Question 1.** What is the fastest way to see why an auto-configuration matched or did not match?  
**Answer:** Run the application with `--debug` or enable the `debug=true` property, then read the Condition Evaluation Report.

**Question 2.** Does `debug=true` set every logger in the application to DEBUG?  
**Answer:** No. Spring Boot enables debug logging for a selected core group of loggers and the condition report. Individual loggers need `logging.level` if you want more detail.

**Question 3.** Is a Negative match for `@ConditionalOnMissingBean` necessarily an error?  
**Answer:** No. The application may have provided a custom bean so the default auto-configuration intentionally backed off.

**Question 4.** A condition matched, yet the bean failed to initialize. What should you inspect next?  
**Answer:** Startup exception/stack trace, constructor dependencies, and the factory method. The condition report does not replace initialization failure diagnosis.

**Question 5.** Does `--debug` automatically open `/actuator/conditions`?  
**Answer:** No. That endpoint belongs to Actuator and requires the dependency, exposure configuration, and appropriate access permissions.

**Question 6.** If an auto-configuration class does not appear in the report at all, what should you check?  
**Answer:** Dependencies/classpath, the `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` file, class name contents, and exclusion configurations.

**Remember:** `--debug` and `debug=true` are the two ways to enable Spring Boot's condition diagnostic mode. Read **Positive matches**, **Negative matches**, and **Exclusions** to learn why an auto-configuration was applied or skipped; then check properties, the classpath, replacement beans, and startup exceptions. Use the report to find the root cause, then confirm the fix with automated tests.
