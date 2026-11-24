# Identifying Auto-Configured Components by Classpath and Beans

## 1. Why do applications adding the same Actuator get different results?

Two applications declaring the same `spring-boot-starter-actuator` can receive different beans:

- The first application only needs to record metrics in memory.
- The second application adds a library to export metrics to Prometheus.
- The third application declares its own place to record metrics.
- A web application has components exposing endpoints over HTTP; a non-web application does not have those same components.

Spring Boot does not create a fixed list of beans simply upon seeing the starter name. **Auto-configuration** selects configurations matching the libraries, beans, properties, and application environment.

To read this behavior, distinguish:

| Concept | Question it answers |
| --- | --- |
| `Classpath` | At runtime, which classes/libraries can the application find and load? |
| `Bean` | Which objects or object definitions have been registered for Spring to manage? |
| `ApplicationContext` | In which context is Spring managing the beans and configurations? |
| Configuration condition | Given the available inputs, is this configuration or bean factory method applied? |
| Condition evaluation report | Why was a configuration chosen or skipped? |

The goal of this lesson is to identify **which component is created, which inputs caused it to be created, and which evidence confirms it**. You do not need to memorize every Actuator configuration class.

## 2. The model from library to bean

The process can be visualized as follows:

~~~text
Libraries on runtime classpath
           +
Beans/bean definitions already recognized by Spring
           +
Properties and application type
           ↓
Evaluate auto-configuration conditions
           ↓
Register matching beans
           ↓
Initialize, wire, and use the beans
~~~

This is a model for reading conditional relationships, not a statement that all condition types are always evaluated at the exact same moment.

Spring Boot activates auto-configuration via `@EnableAutoConfiguration` or `@SpringBootApplication`. Auto-configuration candidates are registered by libraries through Boot's mechanism; you do not need to place Boot packages under the application package for component scan to find them. See [Spring Boot 3.3 — Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html).

### 2.1. A class being present differs from a bean being present

For example, a library containing `SimpleMeterRegistry` means application code can use that type. It does not mean Spring already manages an instance of that type.

The following statement only creates a local Java object:

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();
~~~

This is an illustrative snippet inside a method requiring the corresponding import; an object is not registered as a bean merely by being created with `new`.

Conversely, a `@Bean` method in a configuration loaded by Spring can register the returned object into the context:

~~~java
@Bean
public SimpleMeterRegistry manualRegistry() {
    return new SimpleMeterRegistry();
}
~~~

This snippet must be placed in a loaded configuration class with appropriate imports. The experiment section below provides the complete Java file.

### 2.2. Configuration class name, bean name, and bean type

Three identifiers often appear together yet are not equivalent:

~~~text
SimpleMetricsExportAutoConfiguration → auto-configuration class
simpleMeterRegistry                  → name of a bean created by the configuration
SimpleMeterRegistry                  → type of that bean object
~~~

When a condition checks for type `MeterRegistry`, a `SimpleMeterRegistry` bean can satisfy it because it belongs to that type hierarchy. The bean name does not need to match the class name.

In the report, the form `SomeAutoConfiguration#someBean` points to a bean factory method. A configuration matching its conditions does not mean every method inside also matches: a method can have its own conditions.

## 3. Reading the key conditions

### 3.1. ConditionalOnClass: is the required library present?

`@ConditionalOnClass` checks for the presence of the specified classes on the classpath. It does not automatically create beans of those classes.

Example of how to read it:

~~~text
Condition requires ObservationRegistry on the classpath
→ Class present: continue evaluating the configuration
→ Class missing: do not apply that configuration branch
~~~

Inspect the **runtime classpath of the actual application**, not just IDE import lists or test dependencies. A test-only dependency is not guaranteed to exist when running the main application.

A class being present is also insufficient if the configuration still requires other beans, properties, or environments. See [ConditionalOnClass API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html).

### 3.2. ConditionalOnBean: is there already a component to collaborate with?

`@ConditionalOnBean` requires Spring to have already recognized a bean matching the condition's criteria. Criteria can be based on type, name, or annotation, depending on the declaration.

For example, a database check capability needs a Spring-managed `DataSource` to know which data source to check. Simply adding a JDBC driver does not prove the context has a `DataSource`.

Bean conditions are evaluated against bean definitions already processed at that point. Configuration ordering and context search scope can therefore matter. Do not blindly copy this condition into arbitrary classes and treat it as an "after everything has initialized" check. See [ConditionalOnBean API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html).

### 3.3. ConditionalOnMissingBean: use the default when the application has not provided one

`@ConditionalOnMissingBean` commonly lets Boot provide a default bean while still letting the application decide for itself.

How to read a type-based condition:

~~~text
Application has no bean of the target type yet
→ default configuration can be applied if other conditions also pass

Application already has a bean of the target type
→ the default branch with the missing-bean condition is skipped
~~~

This **back-off** mechanism does not delete the bean the application declared. Nor does it mean all auto-configuration is disabled.

When reading an actual condition, check whether it evaluates **type or name** and in which context it searches. A renamed bean can still satisfy a type condition so the default backs off. Conversely, a name-based condition behaves differently. See [ConditionalOnMissingBean API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html).

### 3.4. Properties and application type also participate

Conditions can depend on properties or the environment:

| Condition group | Question to ask |
| --- | --- |
| Classpath | Are the classes this capability needs present? |
| Existing bean | Is there a component to integrate with? |
| Missing bean | Has the application already replaced the default? |
| Property | Is the capability disabled or set to another value? |
| Web | Is this a Servlet, reactive, or non-web application? |

With `@ConditionalOnProperty`, read both the expected value and how a missing property is handled. There is no universal rule that "omitted always means enabled" or "omitted always means disabled"; the `havingValue` and `matchIfMissing` options determine the details. See [ConditionalOnProperty API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html).

Actuator also has specialized conditions for endpoints, health indicators, and metrics export systems. Do not replace all those conditions with a generic true/false assumption.

## 4. Representative Actuator components and their inputs

### 4.1. ObservationRegistry

`ObservationRegistry` coordinates observations in Micrometer Observation. In Spring Boot 3.3.0, `ObservationAutoConfiguration` checks for the presence of this class and creates a default registry bean only when no matching bean exists yet.

Internal branches also depend on Micrometer metrics or tracing. Thus, having a registry does not mean every kind of handler exists or that traces are already being sent to a backend. You can cross-reference [ObservationAutoConfiguration 3.3.0 source](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/observation/ObservationAutoConfiguration.java).

An application can add `ObservationPredicate`, `ObservationFilter`, or `ObservationHandler` beans to participate in the observation mechanism once the corresponding infrastructure is configured. This is an example of **collaborating with existing beans**, not just creating a replacement bean. See [Spring Boot 3.3 — Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

### 4.2. Metrics foundation and where measurements are recorded

`MeterRegistry` is the central interface for registering and recording metrics. `SimpleMeterRegistry` is an in-memory implementation.

In Boot 3.3.0, `MetricsAutoConfiguration` provides foundational components, such as a Micrometer clock when no matching clock bean exists yet. This explains why one capability can depend on a bean created by another configuration. See [MetricsAutoConfiguration 3.3.0 source](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/MetricsAutoConfiguration.java).

`SimpleMetricsExportAutoConfiguration` creates a fallback registry when matching conditions hold, including:

- A Micrometer clock bean is present.
- No `MeterRegistry` bean exists yet.
- Simple metrics export is allowed by configuration.

If the application provides its own `MeterRegistry` bean, the fallback registry does not need to be created. This is the case we will verify directly in the experiment section. See [SimpleMetricsExportAutoConfiguration 3.3.0 source](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/export/simple/SimpleMetricsExportAutoConfiguration.java).

### 4.3. Registries for external systems

When adding a supported registry implementation, such as `micrometer-registry-prometheus`, Boot has the basis to configure the corresponding integration. The outcome still depends on enable/disable properties and existing beans; an application can end up with a composite registry when using multiple metric sinks.

Do not guess a fixed list of beans for every application that has Prometheus. Inspect the dependency tree, condition report, and actual beans. See [Spring Boot 3.3 — Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

At the same time, the Prometheus registry and the HTTP endpoint `/actuator/prometheus` are two distinct links: having the metric recording component does not prove the URL is exposed.

### 4.4. DataSource health component

In Boot 3.3.0, JDBC health configuration checks relevant classes, a `DataSource` bean, and enablement of the `db` health indicator. The default contributor factory method also checks that no bean exists with specific alternative names.

This case illustrates two points:

1. Having JDBC on the classpath is not enough to conclude database health is created.
2. Back-off rules can evaluate **by name**, not only by type like the metrics example.

See [DataSourceHealthContributorAutoConfiguration 3.3.0 source](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/jdbc/DataSourceHealthContributorAutoConfiguration.java).

There is no need to add a fake database to an application just to "have enough Actuator components". Operational capabilities should reflect the components the application actually uses.

### 4.5. HTTP endpoints and tracing

For an Actuator endpoint over HTTP, there must also be an appropriate web environment, an available endpoint, HTTP exposure, and a valid access path. Setting `management.endpoints.web.exposure.include` neither downloads a missing library nor automatically creates every needed bean. See [Spring Boot 3.3 — Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

Similarly, the presence of `ObservationRegistry` does not prove complete tracing is configured. Tracing integration requires bridge/tracer libraries and export configuration matching the chosen solution. See [Spring Boot 3.3 — Tracing](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html).

## 5. Experiment: same classpath, replace one bean

The experiment uses **Spring Boot 3.3.0 and JDK 21**, with Java code compatible from Java 17 onward. The application runs without web to focus on bean creation decisions, without needing to open an HTTP port.

Two runs keep the same libraries; only the profile changes to activate the configuration declaring an application bean.

### 5.1. Gradle configuration for the sample project

The project assumes Gradle wrapper 8.5 and JDK 21. In `settings.gradle`:

~~~groovy
rootProject.name = 'actuator-conditions-demo'
~~~

In `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

The BOM manages dependency versions. Only the Actuator starter is added because the experiment does not need a web server. Starter declaration syntax is shown in [Spring Boot 3.3 — Enabling Production-ready Features](https://docs.spring.io/spring-boot/3.3/reference/actuator/enabling.html).

Place the sample project in its own package without other registry configurations; extra beans would alter the experiment's inputs.

### 5.2. Complete Java file

Create `src/main/java/example/actuatorconditions/ActuatorConditionsApplication.java`:

~~~java
package example.actuatorconditions;

import java.util.Arrays;
import java.util.Map;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@SpringBootApplication
public class ActuatorConditionsApplication {
    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ActuatorConditionsApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);
        application.setDefaultProperties(Map.of(
                "spring.jmx.enabled", "false",
                "management.metrics.use-global-registry", "false"));

        try (ConfigurableApplicationContext context = application.run(args)) {
            String[] registryNames = context.getBeanNamesForType(MeterRegistry.class);
            Arrays.sort(registryNames);
            System.out.println("registryBeans=" + Arrays.toString(registryNames));
            System.out.println("observationRegistry="
                    + (context.getBeanNamesForType(ObservationRegistry.class).length == 1));
        }
    }

    @Configuration(proxyBeanMethods = false)
    @Profile("manual")
    public static class ManualRegistryConfiguration {
        @Bean
        public SimpleMeterRegistry manualRegistry() {
            return new SimpleMeterRegistry();
        }
    }
}
~~~

Meaning of the choices in the program:

- `WebApplicationType.NONE` keeps the application in non-web mode.
- `ManualRegistryConfiguration` is loaded only when the `manual` profile is active.
- The `manualRegistry` method explicitly declares return type `SimpleMeterRegistry` so Spring recognizes it.
- Bean names are sorted before printing for easy comparison.
- `try-with-resources` closes the context after reading the results.
- Not using the static global registry keeps the experiment focused on beans in the current context.

The two lines printed by the program are direct evidence of registered beans. Other environment log lines are not treated as fixed output.

### 5.3. Run A: let Boot provide the fallback registry

In the sample project directory:

~~~powershell
.\gradlew.bat bootRun
~~~

With the exact dependency set and configuration above, the two lines printed by the program are:

~~~text
registryBeans=[simpleMeterRegistry]
observationRegistry=true
~~~

There is no registry bean declared by the application. The conditions of the fallback branch match, so Boot creates `simpleMeterRegistry`.

`observationRegistry=true` here only means the program found exactly one bean of type `ObservationRegistry`. It does not verify exporting traces or the state of a monitoring server.

### 5.4. Run B: application provides its own registry

Run again with the profile:

~~~powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=manual"
~~~

Expected two lines:

~~~text
registryBeans=[manualRegistry]
observationRegistry=true
~~~

The classpath did not change; the `SimpleMeterRegistry` class still exists. What changed is that the context has a `manualRegistry` bean definition from the active configuration.

Because this bean is of type `MeterRegistry`, the "no MeterRegistry yet" condition of the fallback branch fails. Boot skips that branch, while the application registry is retained.

This is not two same-named beans overriding each other: `manualRegistry` and `simpleMeterRegistry` are two different names. The decision to skip the default in this example is based on **bean type**.

### 5.5. Why is Primary not needed in the example?

`@Primary` helps select a preferred candidate when multiple matching beans participate in single-dependency injection. It does not mean that bean is the only one existing, nor does it delete other beans.

The example uses the missing-bean mechanism: when the application registry already exists, the fallback registry is not registered. There is no need to add Primary to force that outcome. See [Spring Framework — Autowiring with Primary](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-primary.html).

Nor is there any need to enable `spring.main.allow-bean-definition-overriding` to run this experiment. Allowing same-name definition overriding is a different mechanism from default configuration backing off.

## 6. Using the condition report to explain the results

### 6.1. Enabling the report at startup

For the Gradle example:

~~~powershell
.\gradlew.bat bootRun --args="--debug"
~~~

With the manual profile:

~~~powershell
.\gradlew.bat bootRun --args="--debug --spring.profiles.active=manual"
~~~

If you have an already packaged runnable JAR, the corresponding command form is:

~~~powershell
java -jar .\build\libs\actuator-conditions-demo-0.0.1-SNAPSHOT.jar --debug
~~~

The JAR command assumes that artifact has already been built, for example with `bootJar` on a project configured as above. Do not run `javac` alone on a Spring file and expect libraries to appear automatically: the program needs the full classpath provided by the build tool or runtime environment.

`--debug` makes Boot print the condition evaluation report and enables debug for a few related loggers; it does not mean every logger of every library switches to DEBUG. See [Spring Boot 3.3 — Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html).

### 6.2. Recognizing the sections of the report

| Section | How to read |
| --- | --- |
| Positive matches | Configurations/branches whose evaluated conditions matched |
| Negative matches | Configurations/branches that did not match; inspect the specific reason |
| Exclusions | Configurations excluded by application configuration |
| Unconditional classes | Candidates without conditions listed at that level; do not assume every bean inside always exists |

Configuration names or formatting may vary by version. Always read the report from the specific run under investigation, not a report from another machine with different profiles or dependencies.

**Negative matches are usually normal behavior.** A non-web application skips Servlet and reactive configurations; an application with its own registry skips the fallback registry. Do not try to turn every negative line into a positive one.

### 6.3. Comparing the two runs

Find `SimpleMetricsExportAutoConfiguration`.

In Run A, the reasons to recognize are:

~~~text
micrometerClock bean is present
No bean of type MeterRegistry found
Simple export branch is allowed
~~~

In Run B, the deciding reason is:

~~~text
Missing-bean condition did not match
MeterRegistry bean named manualRegistry already exists
~~~

This is a **paraphrase of the report content**, not a verbatim console copy. The actual report can include condition names, packages, and longer descriptions.

A configuration can pass several conditions yet still not be selected because another condition fails. In Run B, the export configuration still being enabled does not override the fact that the application bean already exists.

### 6.4. If a web application has the conditions endpoint

In an existing sample web application, you can expose the `conditions` endpoint over HTTP within the needed scope:

~~~yaml
server:
  address: 127.0.0.1

management:
  endpoints:
    web:
      exposure:
        include: health,conditions
~~~

Then call the application's exact port/base path, for example with default port 8080:

~~~powershell
curl.exe --silent --show-error http://127.0.0.1:8080/actuator/conditions
~~~

The endpoint returns a report by context, with sections such as `positiveMatches` and `negativeMatches`; a negative match can separate matched and unmatched reasons. See [Spring Boot 3.3 — Conditions REST API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html).

**The Java example above sets NONE so it does not provide this URL.** Merely adding exposure YAML to a non-web experiment will not create an HTTP server. You can use the console report to complete the entire comparison.

In an application with Spring Security, the call is also subject to authentication/authorization policies. The report can reveal technical details so access should be restricted. Do not open all endpoints just to look up one condition.

## 7. A workflow to identify a component in a real application

Suppose an expected registry or health contributor cannot be found:

1. **Name the exact component you are looking for.** Are you looking for a bean type, bean name, endpoint, or exported data? "Actuator isn't working" is too broad a description.
2. **Check the runtime classpath.** Right library, right version, and right running module? Read dependency tree/insight when needed.
3. **Check whether the application configuration was loaded.** Is a custom bean in a valid scan/import scope? Is its profile active?
4. **Read the report from the exact startup run.** Locate the relevant configuration class and method; record the failing condition instead of only noting "negative".
5. **Cross-check actual beans.** Do type, name, and context match the criteria? An object created outside Spring is not evidence of a bean.
6. **If looking for a URL, check the web layer next.** Port, base path, exposure, and security are inputs to examine separately.
7. **Change one input and rerun.** Keep other inputs stable to observe causal relationships.

Avoid simultaneously adding multiple libraries, renaming beans, toggling multiple properties, and clearing caches, then concluding one specific change solved the problem.

When the report says missing-bean found an existing bean, check where that bean came from. It may be provided by the application, another library, or an auto-configuration applied earlier.

### Timing and scope to keep in mind

Conditions generally serve context construction. Changing a configuration variable after the application has started does not automatically make Boot rerun all auto-configuration to swap out the registry.

Bean conditions rely on identifiable information. Declaring an overly generic return type such as `Object` on a `@Bean` method can make configuration-time type inference inaccurate. Declare a type appropriate for the provided bean. For some configurations, you must also consider parent/child context relationships and the order in which definitions are processed. See [Spring Boot 3.3 — Developing Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html).

Do not fix ordering by renaming Java files or moving methods in source; that is not the coordination contract of auto-configuration.

## 8. Conclusions that are easy to get wrong

| Premature conclusion | What to verify |
| --- | --- |
| JAR has class X so context definitely has bean X | Is there a configuration creating the bean and are all conditions met? |
| Called `new` on an object so missing-bean must see it | Is the object registered for Spring to manage? |
| Having one custom bean stops all Actuator auto-configuration | Which specific branch backed off? Other configurations can still run |
| Having a registry means data reached Prometheus/Zipkin | Are the exporter, export path, and destination configured? |
| No URL seen means no bean exists | Distinguish bean, web environment, exposure, and access permissions |
| Negative matches is a list of errors | Read whether that branch fits the application and needs to apply |
| Primary makes other beans disappear | Check the bean set and single-dependency injection selection rules separately |
| Renaming the registry makes type-based missing-bean miss it | Is the condition checking name or type? |
| Last run's report explains the current run | Are classpath, profile, properties, and context still the same? |

### Practice on your own

1. Run both experiments and record the bean name, bean type, and the report's reason for selecting/skipping the fallback branch.
2. In the manual profile, rename the `manualRegistry` method to `teamRegistry`. Predict whether the default registry returns and explain based on the condition type.
3. Keep the JDBC library without a `DataSource` bean: is there enough evidence to claim a database health contributor exists?
4. In a non-web application, enable exposure for `conditions`. Explain why there is still no HTTP URL.
5. Find a normal negative match in the report and state the input that caused it not to match.

**Reference hint:** the fallback registry example checks by `MeterRegistry` type, so renaming the application bean does not make that type disappear. Classpath and bean are two separate conditions. The report explains configuration decisions; reading beans confirms context results; HTTP access requires subsequent conditions.
