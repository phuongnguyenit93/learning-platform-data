# Testing a Matrix of Missing, Valid, Invalid, and Boundary Properties in Spring Boot Auto-configuration

## 1. Goal of a configuration test matrix

A `@ConfigurationProperties` class is a contract between a Spring Boot library and the application using it. This contract can specify:
- Which properties are required.
- Which properties have default values when omitted by the user.
- Data types and conversion rules.
- Valid value ranges, formats, or business constraints.
- How to handle keys that do not belong to the configuration contract.

Testing only a single "valid configuration" case is not enough. A solid matrix must cover at least the four groups named in the topic:

| Group | Question | Expected result |
| --- | --- | --- |
| Missing (undeclared) | When the user omits a property, is the default applied? Is a required property rejected? | Defaults are used for optional properties; required properties fail clearly |
| Valid | Do values of the right type that satisfy constraints bind properly? | Context starts, bean receives the expected values |
| Invalid | Are wrong types, invalid formats, or constraint violations detected? | Context fails with the corresponding binding or validation error |
| Boundary | Are values right at min/max accepted, while values outside are rejected? | Inclusive bounds are accepted; out-of-bounds values are rejected |

This article uses `ApplicationContextRunner` to test both property binding and auto-configuration. Each test creates an independent context, passes properties via `withPropertyValues(...)`, and asserts the beans and startup status. No server startup or database connection is needed.

## 2. Distinguishing an undeclared property from an unsupported key

Two situations are often loosely called a "missing property", yet they have different semantics.

**A property not declared in Environment** is a valid key of the properties class for which the user provided no value. The outcome depends on design:
- Fields with an initializer or constructor default can keep their default value.
- Fields without a default can receive `null` or a primitive default such as `0`.
- Constraints such as `@NotBlank`, `@NotNull`, or `@Min` can cause the context to fail when validation is enabled.

**A key not declared in the properties class** is a key present in `application.yml` for which the class has no corresponding field/getter/constructor property. By default, `@ConfigurationProperties` uses `ignoreUnknownFields = true`, so unknown keys are usually ignored. If you want strict configuration, set `ignoreUnknownFields = false` so binding an unrecognized key becomes an error.

Example:

~~~yaml
acme:
  retry:
    name: primary
    max-attempts: 4
    legacy-mode: true
~~~

If the class defines only `name` and `maxAttempts`, `legacy-mode` is an unknown property. It is not the same as leaving `max-attempts` blank/omitted.

**Design rule:** decide explicitly which properties are optional, which are required, and whether unknown keys should be rejected. Do not rely on the primitive default value `0` to implicitly represent a valid configuration.

## 3. Defining a properties contract with defaults and validation

The Java 17+ example uses JavaBean binding so defaults and setters are easy to observe. This class belongs to the library and is registered via `@EnableConfigurationProperties` in auto-configuration.

File `src/main/java/com/acme/retry/RetryProperties.java`:

~~~java
package com.acme.retry;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "acme.retry")
@Validated
public class RetryProperties {

    /**
     * Retry configuration name; the application must provide a value.
     */
    @NotBlank
    private String name;

    /**
     * Maximum number of attempts, defaulting to 3 and accepting only 1 through 10.
     */
    @Min(1)
    @Max(10)
    private int maxAttempts = 3;

    /**
     * Default endpoint if not declared by the application.
     */
    @NotBlank
    private String endpoint = "https://retry.example";

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public int getMaxAttempts() {
        return maxAttempts;
    }

    public void setMaxAttempts(int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }

    public String getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(String endpoint) {
        this.endpoint = endpoint;
    }
}
~~~

Meaning of each field:

| Property | Java type | Required/default | Constraint |
| --- | --- | --- | --- |
| `acme.retry.name` | `String` | Required; no default | `@NotBlank` |
| `acme.retry.max-attempts` | `int` | Optional; default `3` | `@Min(1)` and `@Max(10)` |
| `acme.retry.endpoint` | `String` | Optional; default URL | `@NotBlank` |

Spring Boot relaxed binding maps the kebab-case key `max-attempts` to the Java property `maxAttempts`. Use kebab-case in configuration files to stay consistent with Spring Boot conventions.

### Why are @Validated and a validation provider required?

`@Min`, `@Max`, and `@NotBlank` belong to Jakarta Bean Validation. For them to actually be enforced when binding `@ConfigurationProperties`, you need:
1. To annotate the properties class with `@Validated`.
2. A Bean Validation implementation on the classpath, typically via the `spring-boot-starter-validation` dependency.
3. Constraints appropriate for the data types.

Without a validation provider, you cannot expect constraints to run automatically just because annotations appear in source code. Type-conversion binding may still work, but Bean Validation constraints will not be enforced as intended.

## 4. Registering properties via auto-configuration

File `src/main/java/com/acme/retry/autoconfigure/RetryAutoConfiguration.java`:

~~~java
package com.acme.retry.autoconfigure;

import com.acme.retry.RetryProperties;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;

@AutoConfiguration
@EnableConfigurationProperties(RetryProperties.class)
public class RetryAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    RetryExecutor retryExecutor(RetryProperties properties) {
        return new RetryExecutor(
                properties.getName(),
                properties.getMaxAttempts(),
                properties.getEndpoint());
    }
}
~~~

The bean uses the bound values:

~~~java
package com.acme.retry.autoconfigure;

public final class RetryExecutor {

    private final String name;
    private final int maxAttempts;
    private final String endpoint;

    public RetryExecutor(String name, int maxAttempts, String endpoint) {
        this.name = name;
        this.maxAttempts = maxAttempts;
        this.endpoint = endpoint;
    }

    public String getName() {
        return name;
    }

    public int getMaxAttempts() {
        return maxAttempts;
    }

    public String getEndpoint() {
        return endpoint;
    }
}
~~~

In the library JAR, register `RetryAutoConfiguration` using the file:

`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

Content:

~~~text
com.acme.retry.autoconfigure.RetryAutoConfiguration
~~~

In `ApplicationContextRunner` below, the auto-configuration class is supplied directly via `AutoConfigurations.of(...)`, so the test does not need to verify the discovery descriptor. The descriptor is still required for auto-configuration to be discovered automatically when an application consumes the JAR.

## 5. Classifying failures: binding, conversion, and validation

Not every invalid configuration fails at the same step.

**Binding succeeds:** Binder finds the property, converts the data type, and assigns the value to the properties object.

**Conversion/binding failure:** the value cannot be converted to the Java type. For example, `max-attempts=abc` cannot be converted to `int`. This error happens before `@Min`/`@Max` can even be evaluated for that value.

**Validation failure:** the value bound successfully, but violates a constraint. For example, `max-attempts=0` is a valid integer but lower than `@Min(1)`; `name=""` binds as an empty string but violates `@NotBlank`.

**Missing required property:** if a field has no default, after binding it may be `null`; `@NotBlank` or `@NotNull` detects the missing data. With primitives, be careful because Java's default value is 0; use a wrapper or suitable constraint if you need to distinguish "undeclared" from the numeric value 0.

Diagnostic table:

| Input | Phase | Result |
| --- | --- | --- |
| Missing `acme.retry.name` | Validation | `@NotBlank` rejects `null` |
| Missing `acme.retry.max-attempts` | Default/binding | Keeps `3` from initializer |
| `max-attempts=abc` | Conversion/binding | Cannot convert to `int` |
| `max-attempts=0` | Validation | Violates `@Min(1)` |
| `max-attempts=11` | Validation | Violates `@Max(10)` |
| `max-attempts=1` or `10` | Validation | Valid at inclusive bounds |
| `legacy-mode=true` | Unknown field handling | Ignored by default unless `ignoreUnknownFields` is disabled |

Distinguishing these phases helps tests verify the right cause. A conversion error does not prove validation works; a validation error likewise does not prove property conversion works for every data type.

## 6. Setting up test dependencies and runner

The example project uses Java 17+, Spring Boot 3.3, JUnit 5, AssertJ, and Jakarta Validation. With Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

With Maven, the equivalent dependencies:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

If using the Spring Boot BOM or starter parent, versions are managed centrally. Otherwise, import the BOM or declare compatible versions.

Base runner:

~~~java
private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(RetryAutoConfiguration.class));
~~~

`AutoConfigurations.of(...)` brings the auto-configuration into the context following Boot's standard test mechanism. Each `run(...)` call creates a fresh context, so tests can vary property values without leaking state between cases.

## 7. Complete test for missing, valid, invalid, and boundary cases

File `src/test/java/com/acme/retry/RetryPropertiesMatrixTests.java`. To keep the example self-contained, the properties and auto-configuration classes are declared statically inside the test; in a real library, use the production classes from earlier sections.

~~~java
package com.acme.retry;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.validation.annotation.Validated;

import static org.assertj.core.api.Assertions.assertThat;

class RetryPropertiesMatrixTests {

    @ConfigurationProperties(prefix = "acme.retry")
    @Validated
    static class RetryProperties {

        @NotBlank
        private String name;

        @Min(1)
        @Max(10)
        private int maxAttempts = 3;

        @NotBlank
        private String endpoint = "https://retry.example";

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public int getMaxAttempts() {
            return maxAttempts;
        }

        public void setMaxAttempts(int maxAttempts) {
            this.maxAttempts = maxAttempts;
        }

        public String getEndpoint() {
            return endpoint;
        }

        public void setEndpoint(String endpoint) {
            this.endpoint = endpoint;
        }
    }

    static final class RetryExecutor {
        private final RetryProperties properties;

        RetryExecutor(RetryProperties properties) {
            this.properties = properties;
        }

        int maxAttempts() {
            return properties.getMaxAttempts();
        }
    }

    @AutoConfiguration
    @EnableConfigurationProperties(RetryProperties.class)
    static class RetryAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean
        RetryExecutor retryExecutor(RetryProperties properties) {
            return new RetryExecutor(properties);
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(RetryAutoConfiguration.class));

    @Test
    void omittedOptionalPropertiesUseTheirDefaults() {
        runner.withPropertyValues("acme.retry.name=primary")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    RetryProperties properties =
                            context.getBean(RetryProperties.class);

                    assertThat(properties.getName()).isEqualTo("primary");
                    assertThat(properties.getMaxAttempts()).isEqualTo(3);
                    assertThat(properties.getEndpoint())
                            .isEqualTo("https://retry.example");
                    assertThat(context.getBean(RetryExecutor.class)
                            .maxAttempts()).isEqualTo(3);
                });
    }

    @Test
    void missingRequiredPropertyFailsValidation() {
        runner.run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure())
                    .hasStackTraceContaining("name")
                    .hasStackTraceContaining("must not be blank");
        });
    }

    @Test
    void validPropertiesAndUnknownKeyBindAsExpected() {
        runner.withPropertyValues(
                "acme.retry.name=primary",
                "acme.retry.max-attempts=4",
                "acme.retry.endpoint=https://api.example.test",
                "acme.retry.legacy-mode=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    RetryProperties properties =
                            context.getBean(RetryProperties.class);

                    assertThat(properties.getMaxAttempts()).isEqualTo(4);
                    assertThat(properties.getEndpoint())
                            .isEqualTo("https://api.example.test");
                });
    }

    @Test
    void acceptsBothInclusiveBoundaryValues() {
        for (String value : new String[] {"1", "10"}) {
            runner.withPropertyValues(
                    "acme.retry.name=primary",
                    "acme.retry.max-attempts=" + value)
                    .run(context -> {
                        assertThat(context).hasNotFailed();
                        assertThat(context.getBean(RetryProperties.class)
                                .getMaxAttempts()).isEqualTo(Integer.parseInt(value));
                    });
        }
    }

    @Test
    void rejectsNumbersOutsideTheAllowedRange() {
        for (String value : new String[] {"0", "11"}) {
            runner.withPropertyValues(
                    "acme.retry.name=primary",
                    "acme.retry.max-attempts=" + value)
                    .run(context -> {
                        assertThat(context).hasFailed();
                        assertThat(context.getStartupFailure())
                                .hasStackTraceContaining("maxAttempts");
                    });
        }
    }

    @Test
    void rejectsBlankRequiredName() {
        runner.withPropertyValues("acme.retry.name=   ")
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure())
                            .hasStackTraceContaining("must not be blank");
                });
    }

    @Test
    void malformedIntegerFailsDuringBinding() {
        runner.withPropertyValues(
                "acme.retry.name=primary",
                "acme.retry.max-attempts=abc")
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure())
                            .hasStackTraceContaining("acme.retry.max-attempts");
                });
    }
}
~~~

The test class uses the same properties contract and auto-configuration as the production example. When moving into a real project, remove the duplicate nested classes and import the classes from the autoconfigure module.

Run with Gradle:

~~~bash
./gradlew test --tests "com.acme.retry.RetryPropertiesMatrixTests"
~~~

On Windows:

~~~powershell
.\gradlew.bat test --tests "com.acme.retry.RetryPropertiesMatrixTests"
~~~

Maven:

~~~bash
mvn -Dtest=RetryPropertiesMatrixTests test
~~~

**Expected result:** 7 tests PASS. The two loops in the boundary/range tests check two values each, so the total number of scenarios tested is higher than the number of test methods.

## 8. Reading test results by group

| Scenario | Key input | Key assertion | Meaning |
| --- | --- | --- | --- |
| Optional missing | Only `name` declared | `maxAttempts=3`, endpoint keeps default | Property defaults are preserved when keys are absent |
| Required missing | `name` not declared | Context failed, `must not be blank` error | Required contract is protected |
| Valid + unknown | `max-attempts=4` and unknown key | Context succeeds, value 4 is bound | Unsupported keys are ignored by default |
| Min boundary | `max-attempts=1` | Context succeeds | Lower bound is inclusive |
| Max boundary | `max-attempts=10` | Context succeeds | Upper bound is inclusive |
| Below min | `max-attempts=0` | Context failed | Validation rejects values below 1 |
| Above max | `max-attempts=11` | Context failed | Validation rejects values above 10 |
| Blank required | `name` is whitespace string | Context failed | `@NotBlank` rejects empty/whitespace-only strings |
| Invalid conversion | `max-attempts=abc` | Context failed during bind | String cannot be converted to `int` |

Note: the assertions above check outcomes and stable error indicators at a practical level; avoid locking tests to entire messages or property ordering in exceptions because they can vary across validator/compiler versions.

## 9. Boundary values: inclusive, exclusive, and data types

`@Min(1)` and `@Max(10)` are **inclusive** constraints:
- 1 is valid.
- 10 is valid.
- 0 and 11 are invalid.

If business rules require an open interval, such as a value strictly greater than 1 and less than 10, use corresponding constraints like `@DecimalMin(value = "1", inclusive = false)` and `@DecimalMax(value = "10", inclusive = false)` on an appropriate numeric type.

With `int`, integer bounds are usually straightforward to check. With `BigDecimal`, pay attention to scale and numeric comparison; do not compare by string representation. With `Duration`, `DataSize`, or enums, use appropriate converters/constraints instead of forcing everything into integers.

### Do not forget null values

Under Bean Validation, `@Min` and `@Max` generally treat `null` as valid; they only check when a value is present. If a property is required, combine `@NotNull` with the numeric constraint. For example:

~~~java
@NotNull
@Min(1)
@Max(10)
private Integer maxAttempts;
~~~

The difference:
- `int` always has a primitive value, though when the property is absent it may keep its initializer or become 0 if there is no initializer.
- `Integer` can be `null` when the property is absent.
- `@NotNull` makes the requirement for a value explicit.
- `@Min`/`@Max` define the valid numeric range.

Choose the data type based on whether the application needs to distinguish "undeclared" from "explicitly declared as 0".

## 10. Checking unknown fields according to library policy

By default, `ignoreUnknownFields=true` allows Binder to skip keys not described by the properties class. This is useful when there are multiple profiles or configuration versions, but it can also hide typos:

~~~yaml
acme:
  retry:
    max-attemtps: 5 # typo: missing p in attempts
~~~

If `ignoreUnknownFields=true`, the misspelled key may be skipped and the default `maxAttempts=3` is still used. This is why "unknown key" tests should be considered alongside typo tests.

If you want strict binding, declare:

~~~java
@ConfigurationProperties(
        prefix = "acme.retry",
        ignoreUnknownFields = false
)
public class RetryProperties {
    // Declared properties
}
~~~

Then an unbound key can trigger `UnboundConfigurationPropertiesException` during binding. Strict mode is useful for small, tightly controlled configurations; for a public library needing compatibility across versions, weigh the impact of rejecting future properties an application might use.

Do not confuse `ignoreUnknownFields` with `ignoreInvalidFields`:
- `ignoreUnknownFields` controls keys that have no matching property.
- `ignoreInvalidFields` controls ignoring bind/conversion errors for known fields; the default is `false` and should usually stay that way so bad configuration is caught.

## 11. Condition-dependent properties and combinational testing

Besides binding/validation, a property can enable/disable a bean via `@ConditionalOnProperty`. This is a different decision layer:

~~~java
@Bean
@ConditionalOnProperty(
        prefix = "acme.retry.metrics",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
RetryMetrics retryMetrics() {
    return new RetryMetrics();
}
~~~

Matrix for the condition:

| Property | Metrics bean |
| --- | --- |
| Undeclared, `matchIfMissing=false` | Not created |
| `enabled=true` | Created |
| `enabled=false` | Not created |
| Value other than `true` | Does not match `havingValue="true"` |

`@ConditionalOnProperty` does not replace Bean Validation. It decides whether the bean is registered; `@Min`, `@Max`, and `@NotBlank` verify whether the bound data is valid.

When writing tests, separate assertions for the two layers:
1. Does the properties bean bind and validate correctly?
2. Does the optional bean appear according to the condition?

This helps show whether a failure lies in configuration data or in the auto-configuration decision.

## 12. Extended test matrix worth having

For a real properties class, you can lay out a table before writing tests:

| Group | Sample input | Verification |
| --- | --- | --- |
| Missing optional | No key, field has default | Correct default |
| Missing required | No key, field has `@NotNull`/`@NotBlank` | Context fails |
| Explicit empty | String `""` or whitespace | Constraint behaves properly |
| Valid typical | Value in the middle of the range | Binding and bean are correct |
| Min boundary | Exact min | Succeeds |
| Max boundary | Exact max | Succeeds |
| Below min | min minus one unit | Validation fails |
| Above max | max plus one unit | Validation fails |
| Wrong type | `abc` for integer | Binding/conversion fails |
| Unknown key | Key not present in class | Follows ignore/strict policy |
| Typo key | Off by one character | Does not silently fall back to an unintended default |
| Conditional bean | Property on/off | Bean present/absent as expected |
| Multiple properties | Multiple keys changed together | Does not miss interactions between fields |
| Profile/override | Values from a different profile or environment | Correct precedence source |

Not every project needs every combination. Prioritize cases that protect the public contract and regressions that have occurred before; avoid creating a large Cartesian product that adds no extra value.

## 13. Diagnosing errors from ApplicationContextRunner

When the context fails, inspect `context.getStartupFailure()` rather than only asserting `hasFailed()`. You can add a Condition Evaluation Report listener when investigating conditions:

~~~java
new ApplicationContextRunner()
        .withConfiguration(
                AutoConfigurations.of(RetryAutoConfiguration.class))
        .withInitializer(
                ConditionEvaluationReportLoggingListener.forLogLevel(
                        LogLevel.INFO))
        .run(context -> {
            if (context.getStartupFailure() != null) {
                context.getStartupFailure().printStackTrace();
            }
        });
~~~

Imports:

~~~java
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;
~~~

Read errors by symptoms:
- `Failed to bind properties under ...`: check the prefix, key, and target type.
- `Failed to convert ...`: check the input string and converter.
- `must not be blank` or `must be greater than or equal to ...`: Bean Validation ran and rejected the value.
- `NoSuchBeanDefinitionException`: check whether the properties class is registered via `@EnableConfigurationProperties` or scanning.
- Optional bean absent: check `@ConditionalOnProperty` and `matchIfMissing`.
- Unknown property: check `ignoreUnknownFields` and the actual key name.

In tests, avoid asserting the full verbatim stack trace. Assert only the failure state and the message/field fragment needed to distinguish the error type.

## 14. Common issues and how to handle them

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Property omitted yet context still gets `0` | Primitive field has no initializer | Set an explicit default or use a wrapper + `@NotNull` |
| `@Min`/`@Max` do not run | Missing `@Validated` or validation provider | Add `@Validated` and `spring-boot-starter-validation` |
| Wrong-type value is not caught | Configuration ignores invalid fields or custom converter swallows errors | Keep `ignoreInvalidFields=false` and test conversion |
| Value 1 is rejected despite `@Min(1)` | Wrong constraint/data type or wrong annotation import | Use the right Jakarta Validation version; check inclusive boundary |
| Unknown key is ignored | `ignoreUnknownFields=true` by default | Consider strict mode or typo tests |
| Wrong property key yet default is still used | Binder does not find the right key; unknown key is ignored | Write tests for typo keys and check metadata/relaxed binding |
| Properties bean does not appear | Properties class is not registered | Use `@EnableConfigurationProperties` or an appropriate scanning mechanism |
| Tests pass even though validation is not enabled | Tests provide no invalid input or provider is missing | Add explicit invalid tests and verify context failure |
| Test is affected by an earlier case | Shared mutable fixture/context | Use `ApplicationContextRunner`; each `run` creates an isolated context |
| Test locks onto an overly specific exception message | Message depends on validator/version | Assert only the field, error type, or stable message fragment needed |

## 15. Principles for building a sustainable matrix

- Define optional/required properties before writing the class.
- Declare defaults in the right place and test when keys are absent.
- Use wrapper types when you need to distinguish null from primitive default values.
- Enable Bean Validation explicitly with `@Validated` and the matching provider.
- Test conversion failure and validation failure separately.
- For numeric ranges, test min, max, below min, and above max.
- Test empty/whitespace strings for required properties.
- Decide the unknown fields policy; add typo tests if defaults can mask mistakes.
- Use `ApplicationContextRunner` to verify that properties beans and auto-configured beans are registered with the right data.
- Assert both bound values and context state; checking only that the context starts is not enough.
- Avoid locking tests to complete stack traces; keep assertions specific enough for diagnosis.
- Update the matrix whenever the public configuration contract changes.

## 16. Knowledge self-check

1. What value can an undeclared optional property receive? **The default value from its initializer/constructor if designed; otherwise, according to the Java type's rules.**
2. Which constraint should a required String property use? **`@NotBlank` or `@NotNull` depending on the contract.**
3. Does `@Min(1)` accept 1? **Yes, the bound is inclusive.**
4. Does `@Max(10)` accept 10? **Yes.**
5. Is `max-attempts=abc` a validation error or a conversion error? **Conversion/binding failure.**
6. What kind of error is `max-attempts=0`? **Validation failure due to `@Min(1)`.**
7. Which annotation enables validation for a properties class? **`@Validated`, along with a validation provider on the classpath.**
8. Do processor/annotation metadata replace Bean Validation? **No; metadata serves tooling, while validation checks runtime data during binding.**
9. Are unknown keys ignored by default? **Yes, because `ignoreUnknownFields=true` by default.**
10. How do you catch unknown keys? **Set `ignoreUnknownFields=false` and verify the binding error.**
11. Why use `ApplicationContextRunner`? **To create isolated contexts and test binding/conditions for each property set.**
12. What should boundary tests include? **Min, max, one value below min, and one value above max.**

## Official References

- [Spring Boot 3.3 — Validating @ConfigurationProperties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.validation): `@Validated`, Jakarta Bean Validation, and validation provider.
- [Spring Boot 3.3 — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): binding, relaxed binding, default values, and constructor/JavaBean binding.
- [Spring Boot 3.3 — @ConfigurationProperties JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html): `ignoreUnknownFields` and `ignoreInvalidFields`.
- [Spring Boot 3.3 — Testing Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): `ApplicationContextRunner` and testing context behavior across property values.
- [Jakarta Bean Validation 3.0 — Built-in constraints](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html): semantics of `@NotBlank`, `@Min`, and `@Max`.
