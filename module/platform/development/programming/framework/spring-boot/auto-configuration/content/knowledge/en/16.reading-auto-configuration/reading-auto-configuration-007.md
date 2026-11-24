# Building a Matrix of Classpath, Properties, User Beans, and Expected Outcomes

## 1. Why Build a Matrix Before Reading Deep Into Auto-Configuration?

Spring Boot does not enable an auto-configuration merely because a library is present in the project. Spring decides whether to register each configuration and each bean based on multiple conditions at once: whether classes exist on the runtime classpath, whether effective properties match expected values, whether application-declared beans already exist, whether the application is servlet/reactive/non-web, whether required resources exist, and whether the configuration has been excluded.

When a bean does not appear, looking at a single annotation often leads to an incomplete conclusion. For example:

- The dependency is in the build file, yet the class is not on the runtime classpath.
- The property in application.yml is true, yet a profile or environment variable overrides it to false.
- The auto-configuration has @ConditionalOnMissingBean, yet the application already supplied a compatible bean so the default bean actively backed off.
- The class-level condition passed, yet a condition on an @Bean method did not match.
- The configuration was excluded via exclude or spring.autoconfigure.exclude.
- The condition matched and the bean definition was registered, yet the instance could not be created due to a missing dependency or factory method error.

An effective approach is to build an **input → condition → expected outcome matrix** before changing dependencies or properties. A matrix forces you to state clearly which conditions must hold, where actual values come from, and which beans should appear.

This lesson uses **Spring Boot 3.3.x, Java 17+** as its baseline and focuses on common conditions:

- @ConditionalOnClass / @ConditionalOnMissingClass
- @ConditionalOnProperty
- @ConditionalOnBean / @ConditionalOnMissingBean
- @ConditionalOnSingleCandidate
- @ConditionalOnWebApplication / @ConditionalOnNotWebApplication
- @ConditionalOnResource
- @ConditionalOnExpression and custom Conditions

## 2. Mental Model: From Inputs to Final Beans

When reading an auto-configuration, follow this sequence:

1. **Configuration candidate:** did Spring Boot find the auto-configuration class in the imports list? Was it excluded?
2. **Classpath:** can the classes required by conditions be loaded from the runtime classpath?
3. **Properties:** which properties are read, what are their effective values, and what are the defaults and matchIfMissing settings?
4. **User beans:** does a bean of that type or name already exist in the BeanFactory? Is the condition searching only the current context or also ancestor contexts?
5. **Application type/resource:** is the application servlet/reactive/non-web, and do required resources exist?
6. **Condition outcome:** do all conditions on the class and bean methods match?
7. **Resulting bean:** which bean definition is registered, under what name and return type, and is it excluded by another condition?
8. **Runtime:** does the instance initialize successfully, or are any dependencies missing or failing?

Multiple conditions placed on the same class or method normally combine with **AND** logic: all relevant conditions must match. Within each annotation there are also specific rules. For example, all names in @ConditionalOnProperty must match; all types in @ConditionalOnBean must be found.

~~~text
AutoConfiguration.imports
          |
          v
Is it excluded? ---- Yes ----> Do not load configuration
          |
         No
          v
Do classpath conditions match?
          |
      No  +----> Skip configuration
          |
         Yes
          v
Do property / application type / resource match?
          |
      No  +----> Skip configuration
          |
         Yes
          v
Do bean conditions on @Bean method match?
          |
      No  +----> Do not register that bean
          |
         Yes
          v
Register bean definition
          |
          v
Instantiate according to dependencies and lifecycle
~~~

This diagram is a simplified analytical aid. Spring evaluates conditions across multiple phases of configuration registration; class-level and method-level conditions are not necessarily evaluated at the exact same moment. The key rule to preserve is **do not equate configuration loading, bean definition registration, and instance instantiation**.

## 3. Identifying the Exact Auto-Configuration Candidate

In Spring Boot 3.x, a library's auto-configurations are published through:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Each line is normally the fully qualified name of an @AutoConfiguration class. When reading starter source code, locate the imports file inside the JAR to verify whether Boot discovers the class. Finding the Java class inside a dependency alone is not proof that it is included in the auto-configuration list.

Check exclusion mechanisms:

~~~java
@SpringBootApplication(
    exclude = {MetricsAutoConfiguration.class}
)
public class Application {
}
~~~

Or property configuration:

~~~yaml
spring:
  autoconfigure:
    exclude:
      - com.example.metrics.MetricsAutoConfiguration
~~~

You can exclude with excludeName when you want to use a class name string instead of a direct reference. If the auto-configuration is not in imports, or has been excluded, none of its inner conditions can produce beans.

| Question | Where to Check | Result to Record in Matrix |
|---|---|---|
| Is the class in AutoConfiguration.imports? | Starter JAR, dependency source | Yes/No |
| Does the application exclude the class? | @SpringBootApplication, @EnableAutoConfiguration, properties | Yes/No |
| Is the class imported via another path? | @Import, component scan, test configuration | Note exact loading path |
| Is the auto-configuration ordering-constrained? | before, after, @AutoConfigureOrder | Record configuration dependencies |
| Which dependency version is running? | Maven/Gradle dependency report | Record actual version |

In Boot 3, auto-configuration candidates are published through the dedicated imports file. Do not look for spring.factories as the legacy mechanism for registering new auto-configurations. That file may still appear for other extension points.

## 4. Classpath Column: Is the Library Present or Absent?

### 4.1. @ConditionalOnClass

Used when an auto-configuration only makes sense if a library or API is on the classpath:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.sdk.ReportClient")
class ReportClientAutoConfiguration {
    // Beans integrating with ReportClient
}
~~~

The name attribute is the fully qualified class name. This approach is helpful when the class is an optional dependency, avoiding a direct reference to a type that may not exist. @ConditionalOnClass(ReportClient.class) can also be used when the class can always be safely referenced in configuration metadata.

**Important point:** class-level conditions can be read from annotation metadata without loading the optional class. If you place the condition on an @Bean method whose return type or signature references an optional class, the JVM may have to load that class before the method condition gets a chance to guard it. For genuinely optional dependencies, isolate a nested/static configuration guarded by @ConditionalOnClass so methods using that type live inside the separated configuration.

~~~java
@AutoConfiguration
class ReportAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.sdk.ReportClient")
    static class VendorClientConfiguration {

        @Bean
        @ConditionalOnMissingBean
        ReportGateway reportGateway() {
            return new VendorReportGateway();
        }
    }
}
~~~

This is a structural example; ReportGateway and VendorReportGateway are application/starter types. The child configuration is processed only when the optional class is present. Keep vendor-dependent code inside the guarded configuration branch.

### 4.2. @ConditionalOnMissingClass

Used when a configuration should activate only if a class is absent:

~~~java
@AutoConfiguration
@ConditionalOnMissingClass("com.vendor.legacy.LegacyClient")
class FallbackClientAutoConfiguration {
}
~~~

This condition fits fallback behavior when an older library is not installed. You must inspect the actual classpath, because transitive dependencies can cause a class to be present even when the application team did not declare it directly.

### 4.3. Distinguishing Dependency Declarations from the Runtime Classpath

A dependency line in a build file is not final proof. Inspect the runtime configuration:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Or with Maven:

~~~bash
./mvnw dependency:tree
~~~

Check resolved versions, excluded dependencies, scopes, version conflicts, and whether the class is inside runtime JARs. In containers, verify that the built/deployed artifact carries the same dependency set as the dev environment.

In tests, Spring Boot Test provides FilteredClassLoader to simulate an invisible class:

~~~java
runner.withClassLoader(new FilteredClassLoader(OptionalTransport.class));
~~~

This tests classpath conditions without creating two separate build projects. The class name used in @ConditionalOnClass(name=...) must match the filtered class.

## 5. Property Column: Record the Effective Value, Not Just the YAML Value

### 5.1. @ConditionalOnProperty

Example:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
    prefix = "reporting",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false
)
class ReportingAutoConfiguration {
}
~~~

The condition matches only when the effective property reporting.enabled equals true per havingValue. Because matchIfMissing=false, a missing property will not match.

If havingValue is not specified, a present property whose value is anything other than the string false is considered a match. This is a common source of confusion when a property has values like off, no, 0, or an arbitrary string. When boolean semantics are intended, declare havingValue="true" to make the contract explicit.

matchIfMissing=true means an absent property still counts as a match. Use it only when enabled-by-default is an intentional decision.

### 5.2. Multiple Properties in One Annotation

~~~java
@ConditionalOnProperty(
    prefix = "reporting",
    name = {"enabled", "export"},
    havingValue = "true"
)
~~~

Both reporting.enabled and reporting.export must match. The name list is not an OR operator. If OR logic is needed, use nested conditions or a well-tested custom Condition.

@ConditionalOnProperty is not suited for checking whether a collection-style property has at least one element. For keys like reporting.targets[0], use @ConfigurationProperties or an appropriate Condition rather than assuming the annotation detects every collection item.

### 5.3. Where Does the Effective Value Come From?

A property in application.yml is not necessarily the final value. Sources can override one another: command-line arguments, system properties, environment variables, config data, profile-specific files, imported configs, and other PropertySources.

Example YAML:

~~~yaml
reporting:
  enabled: false
~~~

Yet the deployment environment sets:

~~~bash
REPORTING_ENABLED=true
~~~

Because Spring Boot has relaxed binding, the environment variable maps to reporting.enabled; the final value may be true depending on property source precedence. Therefore, record the **effective value** from Environment along with its source in the matrix instead of merely copying YAML.

Document these columns clearly:

- Exact property key.
- Default value in annotation or @ConfigurationProperties.
- Effective value at runtime.
- Source providing the value (profile file, env var, command-line, config server...).
- Matching rules (havingValue, matchIfMissing).
- Expected outcome.

Do not paste secrets or passwords into diagnostic tables. Record only presence/absence, source, profile, or masked values when the raw value is unnecessary.

## 6. User Bean Column: Does a Compatible Bean Already Exist?

### 6.1. @ConditionalOnMissingBean

This is the common pattern allowing auto-configuration to supply a default bean while yielding to the application:

~~~java
@Bean
@ConditionalOnMissingBean(ReportGateway.class)
DefaultReportGateway reportGateway() {
    return new DefaultReportGateway();
}
~~~

If the BeanFactory already knows of a compatible ReportGateway bean before the condition is evaluated, the default bean backs off. This is an **intentional successful outcome**, not an auto-configuration error.

Read the condition by its exact criteria:

- value/type: match by bean type.
- name: match by bean name.
- annotation: match beans carrying the specified annotation.
- ignored/ignoredType: exclude certain types from the missing check.
- search: decide whether ancestor contexts in a context hierarchy are searched.

Do not confuse @ConditionalOnMissingBean with @Primary: the missing condition decides whether to register the default bean; @Primary decides which candidate wins when type-based injection finds multiple matching beans.

### 6.2. @ConditionalOnBean

Used when a bean only makes sense if a dependency is already registered:

~~~java
@Bean
@ConditionalOnBean(ReportGateway.class)
ReportHealthIndicator reportHealthIndicator(ReportGateway gateway) {
    return new ReportHealthIndicator(gateway);
}
~~~

This condition inspects bean definitions/metadata already processed by the container, without requiring the instance to be created beforehand. If multiple types are listed in value, all requirements must be met. Do not use it to check getters or mutable internal bean state.

### 6.3. @ConditionalOnSingleCandidate

Used when a single candidate or an identifiable primary candidate is required:

~~~java
@Bean
@ConditionalOnSingleCandidate(ReportGateway.class)
ReportFacade reportFacade(ReportGateway gateway) {
    return new ReportFacade(gateway);
}
~~~

If one matching bean exists, or multiple exist yet Spring can determine one primary candidate, the condition can match. If multiple equal candidates exist with no primary candidate, the condition does not match. This differs from @ConditionalOnBean, which only checks whether any matching bean exists.

### 6.4. Bean Definition Order Affects Conditions

Bean conditions only see bean definitions processed up to the moment of evaluation. That is why Spring Boot recommends using @ConditionalOnBean and @ConditionalOnMissingBean on auto-configurations, which are processed after user bean definitions. When auto-configuration A depends on a bean supplied by auto-configuration B, you can use @AutoConfiguration(after = B.class) to order definitions.

after does not mean bean B's instance is initialized first. Instantiation order is governed by the dependency graph and @DependsOn. Record these two facts separately if diagnostics involve both conditions and lifecycle.

## 7. Additional Condition Columns

### 7.1. Application Type: Servlet, Reactive, or Non-Web

A configuration may use:

- @ConditionalOnWebApplication(type = SERVLET) for servlet web applications.
- @ConditionalOnWebApplication(type = REACTIVE) for reactive web applications.
- @ConditionalOnNotWebApplication for non-web applications.

Do not conclude solely from seeing spring-boot-starter-web in the build file; inspect the runtime classpath and the WebApplicationType Spring Boot actually selects. If both MVC and WebFlux are present, application type selection also depends on configuration and how Boot determines the context.

### 7.2. Resource Presence or Absence

@ConditionalOnResource(resources = "classpath:report-defaults.yml") requires the resource to exist via Spring's resource loading mechanism. The resource can come from src/main/resources, a dependency JAR, or another runtime classpath entry. If the resource is on the filesystem, document its exact path and packaging/deployment setup.

### 7.3. SpEL and Custom Conditions

@ConditionalOnExpression allows evaluating SpEL expressions, but you should not reference beans like @settings.enabled: doing so can initialize that bean very early during context refresh and cause it to miss post-processing such as @ConfigurationProperties binding. For complex logic, use a Condition reading Environment/metadata and avoid fetching bean instances while conditions run.

Custom Conditions must return consistent, explainable decisions. If clear match/no-match reasons are needed, extend SpringBootCondition and build ConditionOutcome/ConditionMessage; do not log arbitrarily or call services inside matches().

## 8. Core Matrix: Classpath × Property × User Bean

Suppose a starter has an auto-configuration:

- Active only when example.matrix.AutoConfigurationMatrixTests$OptionalTransport is on the classpath.
- Enabled only when reporting.enabled=true.
- Registers DefaultReportGateway if the application has not provided a ReportGateway bean.

Illustrative code:

~~~java
package example.matrix;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(name = "example.matrix.AutoConfigurationMatrixTests$OptionalTransport")
@ConditionalOnProperty(
        prefix = "reporting",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
public class ReportAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(ReportGateway.class)
    DefaultReportGateway reportGateway() {
        return new DefaultReportGateway();
    }
}
~~~

The ReportGateway, DefaultReportGateway, and OptionalTransport marker types are example types. In a real starter, OptionalTransport normally belongs to an external library and need not be defined in the auto-configuration module. To avoid loading optional classes prematurely, the condition uses name and the configuration is isolated.

### 8.1. Three-Input Truth Table

Notation:

- C: optional class is on the runtime classpath.
- P: effective property reporting.enabled equals true.
- U: user bean of type ReportGateway has already been processed.
- D: default bean DefaultReportGateway is registered.
- X: application's custom bean (when U = Yes).

| C | P | U | D (default) | X (user) | Explanation |
|---|---|---|---|---|---|
| Yes | Yes | No | Yes | No | All conditions match; starter creates default |
| Yes | Yes | Yes | No | Yes | User bean makes @ConditionalOnMissingBean back off |
| Yes | No | No | No | No | Property condition does not match |
| Yes | Missing | No | No | No | matchIfMissing=false |
| No | Yes | No | No | No | Class condition does not match |
| No | Yes | Yes | No | Yes | Auto-config is skipped; user bean still exists |
| Yes | No | Yes | No | Yes | Property disables default; user bean still exists |
| No | No | No | No | No | Neither classpath nor property matches |

The table considers only the stated conditions and assumes user configuration is processed normally. It does not account for excluded auto-configurations, bean creation failures, missing other dependencies, or contexts closed before completion. Record those cases in separate columns/notes instead of folding them into C, P, or U.

### 8.2. Separating "Not Registered" from "Registered But Failed to Instantiate"

When the table predicts D = Yes yet the context has no bean, pinpoint where it stopped:

1. The auto-configuration was not loaded or was excluded.
2. A class condition did not match.
3. A property condition did not match.
4. A bean condition backed off due to a user bean.
5. The bean definition was registered, yet the instance failed to create due to dependencies, constructors, factory methods, binding, or lifecycle.
6. The bean was created, yet was not found by the lookup method used (scope, parent context, bean name/type, alias).

Do not write vaguely "auto-config did not run" before pinpointing the exact stage. The condition report explains match/no-match; stack traces and bean creation logs explain failures during instantiation.

## 9. Diagnostic Matrix Template for Projects

When reading a real auto-configuration, create a separate table or row per important bean. One row can describe one `@Bean` method; if a class has multiple beans with different conditions, do not merge them into a single generic outcome.

| Field | What to Record | Example |
|---|---|---|
| Auto-config | Fully qualified class name | com.acme.ReportAutoConfiguration |
| Bean method | Method and bean name | reportGateway() / reportGateway |
| Candidate | In imports? Excluded? | Yes / No |
| Classpath condition | Class name and outcome | com.vendor.sdk.ReportClient / Yes |
| Property condition | Key, havingValue, matchIfMissing | reporting.enabled / true / false |
| Effective property | Actual value and source | true / environment variable |
| User bean condition | Type/name, existing beans | ReportGateway / customReportGateway |
| Context condition | Servlet/reactive/non-web or parent context | Servlet |
| Resource condition | Resource and outcome | classpath:report.yml / Yes |
| Order | before/after and dependent conditions | after = TransportAutoConfiguration |
| Expected result | Yes/No, bean name/type | Do not create default |
| Actual result | Observed result from report/context | Default backed off |
| Evidence | Report, test, stack trace, command | ConditionEvaluationReport + test |
| Diagnosis | Cause and next action | User bean exists; expected behavior |

To keep the matrix useful, avoid writing "dependency present" without naming the class, "property right" without recording key/value/source, or "user bean present" without recording type/name. Another engineer should be able to reproduce the conclusion solely from these columns.

### 9.1. Distinguishing Facts from Hypotheses

During an investigation, use explicit statuses:

- **Observed:** verified from runtime classpath, Environment, BeanFactory, or condition report.
- **Expected:** outcome predicted by code/annotations.
- **Unknown:** evidence not yet collected.
- **Mismatch:** actual differs from expected and requires investigation.

For example, do not write reporting.enabled=true if you only saw that value in a YAML file. Write YAML=false, Environment effective=true (source=REPORTING_ENABLED) once verified. If the effective value is not yet known, write Unknown instead of guessing.

## 10. How to Gather Runtime Evidence

### 10.1. Condition Evaluation Report

Run the application with --debug:

~~~bash
./gradlew bootRun --args='--debug'
~~~

Or when running a built executable JAR:

~~~bash
java -jar app.jar --debug
~~~

Spring Boot prints the condition evaluation report, typically with sections:

- **Positive matches:** conditions that matched.
- **Negative matches:** conditions that did not match and why.
- **Exclusions:** excluded auto-configurations.
- **Unconditional classes:** configurations needing no conditions.

Read the report by class name and bean method. For example, ReportAutoConfiguration#reportGateway not matching because @ConditionalOnMissingBean found ReportGateway is evidence that a user bean made the default back off. This differs from ReportAutoConfiguration being skipped due to a classpath condition.

### 10.2. Actuator Conditions

If the project includes spring-boot-starter-actuator, the conditions endpoint can expose condition outcomes over HTTP when exposed. In Spring Boot 3.3, this endpoint is not exposed over HTTP by default; exposure and security settings must be reviewed. Never expose diagnostic endpoints publicly just to debug.

Internal configuration example:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,conditions"
~~~

Protect the endpoint with Spring Security or appropriate network policies. The report can reveal classpath, configuration, and internal structure, so restrict access to people who need diagnostics.

### 10.3. Inspecting Environment

In tests, ApplicationContextRunner.withPropertyValues(...) creates explicit property variants. At runtime, you can call Environment#getProperty("reporting.enabled") in diagnostic code or a debugger. If using Actuator env, keep sanitization enabled and never share responses containing secrets.

### 10.4. Inspecting Bean Definitions

Distinguish definition from instance:

- containsBeanDefinition("reportGateway"): checks definition by name.
- containsBean("reportGateway"): checks whether a bean is accessible by name, which may trigger bean creation depending on type/scope.
- getBeanNamesForType(ReportGateway.class): finds bean names matching a type.
- getBean(ReportGateway.class): retrieves the instance, may trigger initialization, and may fail if multiple candidates exist.

When you only need to prove registration conditions, inspect definitions and the condition report before calling getBean(), because fetching an instance can alter the state under observation.

## 11. Matrix Testing with ApplicationContextRunner

ApplicationContextRunner is the Spring Boot Test tool for building small, isolated contexts per combination of properties, user configurations, and classloaders. It is ideal for verifying the expected matrix without booting the entire application for each case.

### 11.1. Complete Test Code

Create src/test/java/example/matrix/AutoConfigurationMatrixTests.java in a Spring Boot 3.3.x, Java 17+ project with spring-boot-starter-test.

~~~java
package example.matrix;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class AutoConfigurationMatrixTests {

    interface ReportGateway {
        String source();
    }

    static final class DefaultReportGateway implements ReportGateway {
        @Override
        public String source() {
            return "default";
        }
    }

    static final class CustomReportGateway implements ReportGateway {
        @Override
        public String source() {
            return "user";
        }
    }

    // Marker representing an optional dependency.
    static final class OptionalTransport {}

    @AutoConfiguration
    @ConditionalOnClass(
        name = "example.matrix.AutoConfigurationMatrixTests$OptionalTransport"
    )
    @ConditionalOnProperty(
        prefix = "reporting",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
    )
    static class ReportAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(ReportGateway.class)
        DefaultReportGateway reportGateway() {
            return new DefaultReportGateway();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserGatewayConfiguration {

        @Bean
        CustomReportGateway customReportGateway() {
            return new CustomReportGateway();
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            ReportAutoConfiguration.class));

    @Test
    void allConditionsMatchCreatesDefaultBean() {
        runner.withPropertyValues("reporting.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(DefaultReportGateway.class);
                    assertThat(context).hasSingleBean(ReportGateway.class);
                    assertThat(context.getBean(ReportGateway.class).source())
                            .isEqualTo("default");
                });
    }

    @Test
    void missingPropertyDoesNotCreateDefaultBean() {
        runner.run(context -> {
            assertThat(context).doesNotHaveBean(ReportGateway.class);
            assertThat(context).doesNotHaveBean(DefaultReportGateway.class);
        });
    }

    @Test
    void falsePropertyDoesNotCreateDefaultBean() {
        runner.withPropertyValues("reporting.enabled=false")
                .run(context -> {
                    assertThat(context).doesNotHaveBean(ReportGateway.class);
                    assertThat(context).doesNotHaveBean(DefaultReportGateway.class);
                });
    }

    @Test
    void missingOptionalClassPreventsAutoConfiguration() {
        runner.withClassLoader(new FilteredClassLoader(OptionalTransport.class))
                .withPropertyValues("reporting.enabled=true")
                .run(context -> {
                    assertThat(context).doesNotHaveBean(ReportGateway.class);
                    assertThat(context).doesNotHaveBean(DefaultReportGateway.class);
                });
    }

    @Test
    void userBeanMakesDefaultBackOff() {
        runner.withUserConfiguration(UserGatewayConfiguration.class)
                .withPropertyValues("reporting.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportGateway.class);
                    assertThat(context).hasSingleBean(CustomReportGateway.class);
                    assertThat(context).doesNotHaveBean(DefaultReportGateway.class);
                    assertThat(context.getBean(ReportGateway.class).source())
                            .isEqualTo("user");
                });
    }
}
~~~

**Note on class names in @ConditionalOnClass:** the test uses a nested marker so the full name contains $. In real projects, the marker is typically a class from an external dependency, such as com.vendor.sdk.ReportClient; when using FilteredClassLoader, filter that exact class. The test example does not use OptionalTransport in the auto-configuration's method signatures, so it can isolate the classpath condition by name without forcing method return types to load the optional class.

### 11.2. Run Commands and Expected Results

Gradle:

~~~bash
./gradlew test --tests example.matrix.AutoConfigurationMatrixTests
~~~

Maven:

~~~bash
./mvnw -Dtest=AutoConfigurationMatrixTests test
~~~

Expected result: **5 tests PASS**.

| Test | Classpath | Property | User bean | Outcome |
|---|---|---|---|---|
| allConditionsMatchCreatesDefaultBean | Present | true | Absent | Default appears |
| missingPropertyDoesNotCreateDefaultBean | Present | Missing | Absent | No gateway |
| falsePropertyDoesNotCreateDefaultBean | Present | false | Absent | No gateway |
| missingOptionalClassPreventsAutoConfiguration | Absent | true | Absent | No gateway |
| userBeanMakesDefaultBackOff | Present | true | Present | Custom bean only |

These tests confirm the primary axes of the matrix. They do not cover every possible combination, nor do they test profiles, exclusions, parent contexts, web application types, or gateway instantiation failures. Add dedicated tests when your real auto-configuration uses those conditions.

### 11.3. Expanding Tests to Match a Real Matrix

When there are many properties, do not write one giant test with numerous if branches. Write scenario-named tests or parameterized tests so each matrix row is a case with explicit inputs and expected outputs. For example:

- classpathPresent_propertyEnabled_noUserBean_createsDefault
- classpathMissing_propertyEnabled_noUserBean_skipsConfiguration
- classpathPresent_propertyMissing_noUserBean_skipsConfiguration
- classpathPresent_propertyEnabled_userBeanPresent_backsOff
- configurationExcluded_neverCreatesDefault

Test names should state the key input or cause and the resulting bean, making CI failures immediately readable.

## 12. Workflow for Investigating a Missing Bean

1. **Identify the target bean:** name, type, @Bean method, or component class. Do not search only by interface name since multiple implementations may exist.
2. **Locate the auto-configuration candidate:** JAR imports, @Import, component scan, and exclusions. If the class is not loaded, there is no need to analyze its method conditions deeply.
3. **Build the condition table:** record every class-level and method-level annotation; separate classpath, property, bean, resource, and application type.
4. **Collect runtime values:** runtime dependency tree, effective properties/sources, active profiles, user bean definitions, and context type.
5. **Predict outcomes before reading the report:** mark each condition match/no-match and compute the AND result. This separates logic misunderstandings from runtime surprises.
6. **Check the Condition Evaluation Report:** review positive/negative matches and messages. Identify the first non-matching condition or bean-condition back-off.
7. **Check ordering:** if @ConditionalOnBean/@ConditionalOnMissingBean depends on beans from another auto-configuration, verify before/after and bean method return types.
8. **Separate definition from instance:** if the report shows the bean definition registered yet getting the bean fails, inspect dependencies, constructors, factory methods, binding, and lifecycle.
9. **Write a small reproduction test:** use ApplicationContextRunner with the exact classpath/property/user bean combination, then vary one axis at a time to confirm the hypothesis.
10. **Record actuals and evidence:** update the matrix with observed results rather than keeping predictions. Save commands, profiles, and dependency versions so others can reproduce.

## 13. Common Mistakes When Building a Matrix

- **Recording only build-file dependencies:** you must check the runtime classpath and resolved dependencies.
- **Reading only application.yml:** effective values can be overridden by environment variables, command line, profiles, or config imports.
- **Failing to separate class-level and method-level conditions:** a configuration may load while a specific bean is not registered.
- **Treating @ConditionalOnMissingBean as an error when a user bean exists:** that is normally intentional back-off by design.
- **Thinking @ConditionalOnBean requires an instantiated object:** the condition relies on already-processed bean metadata/definitions.
- **Ignoring auto-configuration ordering:** bean conditions see definitions present prior to evaluation time.
- **Using @ConditionalOnProperty for collections:** the annotation is not suited for detecting collection elements.
- **Placing @ConditionalOnClass on a method whose signature depends on an optional class:** the JVM may load the type before the method condition runs; isolate into a guarded configuration.
- **Reading the condition report as an instantiation result:** the report explains conditions, not whether bean instances were created and run successfully.
- **Calling getBean() before checking definitions:** this can trigger initialization and alter the state being observed.
- **Omitting matchIfMissing:** a missing property may produce a different outcome than guessed.
- **Confusing @Primary with @ConditionalOnMissingBean:** one selects an injection candidate, while the other decides whether the default bean is registered.
- **Failing to distinguish exclusions from condition mismatches:** an excluded auto-configuration never reaches bean logic as expected.
- **Omitting versions:** conditions, auto-configurations, and dependency graphs can change between Boot/starter versions.

## 14. Self-Check Questions

1. The dependency is in pom.xml, yet @ConditionalOnClass does not match. What should you check first? **Runtime classpath**, scope, dependency exclusions, resolved version, and actual classloader.
2. reporting.enabled=true is in YAML, yet the condition does not match. Why? **A higher-precedence property source may have overridden it**, a different profile is active, the key is wrong, or the effective value does not match havingValue.
3. The user declares a ReportGateway bean, and auto-config has @ConditionalOnMissingBean(ReportGateway.class). Will the default appear? **No**, if the user definition was processed before the condition.
4. How many types must be found for @ConditionalOnBean({A.class, B.class})? **Both A and B**.
5. Two ReportGateway beans exist and one is marked @Primary. Can @ConditionalOnSingleCandidate match? **Yes**, if Spring determines a single primary candidate.
6. The auto-configuration does not appear in the Condition Evaluation Report. What should you check? **The imports file, exclusions, and configuration loading path** before analyzing properties.
7. The condition report shows the bean method matched, yet the application still fails to start. What should you inspect? **Bean initialization errors and the dependency graph**; a condition match only confirms registration eligibility.
8. Why record the actual property source in the matrix? **To prove the actual runtime value and trace overrides**, rather than relying on static config files.
9. You want to test a classpath condition without building two artifacts. What do you use? **FilteredClassLoader in ApplicationContextRunner**.
10. Does @AutoConfiguration(after = X.class) guarantee X's bean has been instantiated? **No**; it orders bean definition processing, while instantiation depends on dependencies and @DependsOn.

## 15. Official References (Spring Boot 3.3)

- [Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): imports, ordering, class/bean/property conditions, back-off, and ApplicationContextRunner.
- [Condition Annotations API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/package-summary.html): list of condition annotations and condition types.
- [ConditionEvaluationReport API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html): model for condition match/no-match reports.
- [Spring Boot Actuator — Conditions endpoint](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html): condition diagnostic endpoint and exposure/security requirements.
- [Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html): property sources, profiles, and configuration precedence.
- [ApplicationContextRunner API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html): building small contexts to test auto-configuration.
- [FilteredClassLoader API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/FilteredClassLoader.html): simulating missing classes on the classpath in tests.
