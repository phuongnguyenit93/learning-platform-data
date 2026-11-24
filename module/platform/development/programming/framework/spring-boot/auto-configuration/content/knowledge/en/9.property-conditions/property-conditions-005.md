# Multiple Property Names in One @ConditionalOnProperty: All Must Match

## 1. Problem to Solve

In **Spring Boot Auto-configuration**, a bean or an entire configuration class may only be registered if **multiple configuration conditions** are all enabled. For example, the application should only initialize a report-sending service with audit logging when simultaneously:

- \`app.reports.enabled=true\`: the reporting feature is enabled;
- \`app.reports.audit-enabled=true\`: audit logging capability is enabled.

The **\`@ConditionalOnProperty\`** annotation supports checking multiple keys by declaring an array in the **\`name\`** attribute (or its alias **\`value\`**).

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;

// Illustrative annotation snippet; classes and methods are defined
// in the runnable example in the testing section.
@ConditionalOnProperty(
    prefix = "app.reports",
    name = {"enabled", "audit-enabled"},
    havingValue = "true"
)
~~~

**The most important rule: multiple names in the same \`@ConditionalOnProperty\` have an AND relationship.** Each property is evaluated individually under the same rule set, and the entire condition only **matches** when **all** properties match. If even one key fails, the overall condition fails.

The example above is semantically equivalent to the check:

~~~text
match(app.reports.enabled, havingValue="true")
AND
match(app.reports.audit-enabled, havingValue="true")
~~~

Properties are looked up in the **Spring Environment** when Spring processes bean registration conditions; they can come from \`application.yml\`, \`application.properties\`, environment variables, command-line arguments, and other PropertySources.

## 2. Syntax and How Spring Boot Joins Property Names

~~~java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

// This is an illustrative snippet: ReportPublisher is a type defined by the application/library.
@AutoConfiguration
class ReportAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "app.reports",
        name = {"enabled", "audit-enabled"},
        havingValue = "true",
        matchIfMissing = false
    )
    ReportPublisher reportPublisher() {
        return new ReportPublisher();
    }
}
~~~

Meaning of each part:

| Annotation attribute | Effect |
| --- | --- |
| \`prefix = "app.reports"\` | Common prefix for all names; a dot is added automatically when needed |
| \`name = {"enabled", "audit-enabled"}\` | Two independent names to check, not a single joined string |
| \`havingValue = "true"\` | **Each** name must hold the string value \`"true"\` |
| \`matchIfMissing = false\` | If **any** required name is absent, that name fails; this is the default |
| \`value\` | Alias for \`name\`, also accepts \`String[]\` |

With the declaration above, the two full keys are \`app.reports.enabled\` and \`app.reports.audit-enabled\`.

**Writing names correctly:** Spring Boot documentation recommends property names in **dashed notation**, lowercase with hyphens between words, e.g., \`audit-enabled\`. The \`prefix\` part should be a configuration path like \`app.reports\`; no trailing dot is needed. Avoid writing \`name = {"app.reports.enabled", "app.reports.audit-enabled"}\` together with \`prefix = "app.reports"\`, because that duplicates the prefix.

Alternative syntax with the same meaning:

~~~java
// value is an alias for name, not an OR operator.
// Illustrative snippet, placed on an appropriate class or method.
@ConditionalOnProperty(
    prefix = "app.reports",
    value = {"enabled", "audit-enabled"},
    havingValue = "true"
)
~~~

## 3. Truth Table: Having Both Keys and Meeting Requirements Together

Given the condition:

~~~java
@ConditionalOnProperty(
    prefix = "app.reports",
    name = {"enabled", "audit-enabled"},
    havingValue = "true"
)
~~~

Suppose Environment has the following values:

| \`app.reports.enabled\` | \`app.reports.audit-enabled\` | Whole condition | Explanation |
| --- | --- | --- | --- |
| \`true\` | \`true\` | **MATCH** | Both equal the expected value |
| \`true\` | \`false\` | **NO MATCH** | Second key fails |
| \`false\` | \`true\` | **NO MATCH** | First key fails |
| \`false\` | \`false\` | **NO MATCH** | Both fail |
| \`true\` | Absent | **NO MATCH** | Missing second key; \`matchIfMissing=false\` |
| Absent | \`true\` | **NO MATCH** | Missing first key |
| Absent | Absent | **NO MATCH** | Both keys are missing |
| \`yes\` | \`true\` | **NO MATCH** | \`havingValue="true"\` requires value \`true\`, not \`yes\` |
| \`true\` | \`true\`; plus another key = \`false\` | **MATCH** | Keys outside the \`name\` list are unrelated |

In the table, "absent" means Environment **does not contain** the checked property; value \`false\` means the property **exists but fails** the \`havingValue="true"\` condition.

### Example in application.yml

~~~yaml
app:
  reports:
    enabled: true
    audit-enabled: true
~~~

Both properties match, so the conditional \`@Bean\` method in section 2 can be considered for registration.

Change just one line:

~~~yaml
app:
  reports:
    enabled: true
    audit-enabled: false
~~~

The result is **no match**, even though \`app.reports.enabled\` is still \`true\`.

Equivalent configuration with \`application.properties\`:

~~~properties
app.reports.enabled=true
app.reports.audit-enabled=true
~~~

Do not write \`name = "enabled,audit-enabled"\` if you want two keys: that syntax is a single string element and does not form two names in an array. Use **\`name = {"enabled", "audit-enabled"}\`**.

## 4. \`havingValue\` Applies Uniformly to Every Name

One annotation **does not have an array of separate expected values per property**. \`havingValue\` is a single \`String\` and is applied to **all** names in \`name\`.

Example:

~~~java
@ConditionalOnProperty(
    prefix = "app.reports",
    name = {"enabled", "audit-enabled"},
    havingValue = "true"
)
~~~

Here both properties must equal \`true\`.

If \`havingValue\` is omitted, the default is the empty string \`""\`. In default mode, each key must be **present** and its value must **differ from the string \`false\`**. Omitting \`havingValue\` is **not synonymous** with "only accept exact \`true\`".

| Value of a present key | \`havingValue=""\` (default) | \`havingValue="true"\` | \`havingValue="false"\` | \`havingValue="ready"\` |
| --- | --- | --- | --- | --- |
| \`true\` | Match | Match | No | No |
| \`false\` | No | No | Match | No |
| \`ready\` | Match | No | No | Match |
| \`yes\` | Match | No | No | No |

The following example **can match** even though \`mode\` is not boolean:

~~~java
@ConditionalOnProperty(
    prefix = "app",
    name = {"feature-flag", "mode"}
)
~~~

~~~properties
app.feature-flag=true
app.mode=preview
~~~

Both \`true\` and \`preview\` are present values differing from \`false\`. Therefore, if you need to express **two boolean switches must genuinely be on**, use \`havingValue="true"\` explicitly. Spring Boot versions that have \`@ConditionalOnBooleanProperty\` also provide a dedicated boolean option; check your project's version.

### What if two properties need two different expected values?

For instance, needing \`app.reports.enabled=true\` **and** \`app.reports.mode=async\`. You cannot set \`havingValue\` to an array like \`{"true", "async"}\` in the same \`@ConditionalOnProperty\`: the type of \`havingValue\` is \`String\`.

In Spring Boot versions that support repeatable annotations (such as the 3.5 and 4.x lines), you can write:

~~~java
// Both conditions on the same element must match together (AND).
@ConditionalOnProperty(
    prefix = "app.reports",
    name = "enabled",
    havingValue = "true"
)
@ConditionalOnProperty(
    prefix = "app.reports",
    name = "mode",
    havingValue = "async"
)
~~~

The snippet above is an annotation example; place it on a \`@Bean\` method or a configuration class. For older versions that do not support \`@Repeatable\` on this annotation, consider combining via an appropriate condition structure or writing a custom \`Condition\`. Always check the Javadoc of the **Spring Boot version in use** before copying repeatable annotation syntax.

## 5. \`matchIfMissing\` When Checking Multiple Names

The \`matchIfMissing\` attribute controls the outcome **for each missing name**. It does **not** change the AND operator between names.

Example:

~~~java
@ConditionalOnProperty(
    prefix = "app.reports",
    name = {"enabled", "audit-enabled"},
    havingValue = "true",
    matchIfMissing = true
)
~~~

Each key is evaluated as follows:

- If **present**, the key must satisfy \`havingValue="true"\`.
- If **absent**, the key is treated as passing because \`matchIfMissing=true\`.
- The overall result is still the **AND** of both outcomes.

| \`enabled\` | \`audit-enabled\` | Result with \`havingValue="true", matchIfMissing=true\` |
| --- | --- | --- |
| \`true\` | \`true\` | Match |
| \`true\` | Absent | Match |
| Absent | \`true\` | Match |
| Absent | Absent | Match |
| \`false\` | Absent | **No match** |
| Absent | \`false\` | **No match** |
| \`true\` | \`false\` | **No match** |

Common pitfall: **\`matchIfMissing=true\` does not ignore wrong values on a present key.** It only changes **absence** handling. When both keys do not exist, the condition can match, because each missing name is treated as passing. If the business requirement is *must explicitly declare and enable both*, keep \`matchIfMissing=false\` (default).

## 6. Practical Test Program with ApplicationContextRunner

The example below is for a **Java 17+ / Spring Boot 3.5.x** project with \`spring-boot-starter\` and \`spring-boot-starter-test\` dependencies, using JUnit Jupiter and AssertJ. Each auto-configuration class in the test creates a marker type so learners can check the presence/absence of beans in the context.

Create file **\`src/test/java/example/MultiplePropertyConditionTests.java\`**:

~~~java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;

import static org.assertj.core.api.Assertions.assertThat;

class MultiplePropertyConditionTests {

    static final class StrictMarker {
    }

    static final class DefaultMarker {
    }

    static final class MissingAllowedMarker {
    }

    @AutoConfiguration
    static class StrictAutoConfiguration {
        @Bean
        @ConditionalOnProperty(
                prefix = "app.reports",
                name = {"enabled", "audit-enabled"},
                havingValue = "true")
        StrictMarker strictMarker() {
            return new StrictMarker();
        }
    }

    @AutoConfiguration
    static class DefaultAutoConfiguration {
        @Bean
        @ConditionalOnProperty(
                prefix = "app.reports",
                name = {"enabled", "audit-enabled"})
        DefaultMarker defaultMarker() {
            return new DefaultMarker();
        }
    }

    @AutoConfiguration
    static class MissingAllowedAutoConfiguration {
        @Bean
        @ConditionalOnProperty(
                prefix = "app.reports",
                name = {"enabled", "audit-enabled"},
                havingValue = "true",
                matchIfMissing = true)
        MissingAllowedMarker missingAllowedMarker() {
            return new MissingAllowedMarker();
        }
    }

    private final ApplicationContextRunner strictRunner =
            new ApplicationContextRunner().withConfiguration(
                    AutoConfigurations.of(StrictAutoConfiguration.class));

    private final ApplicationContextRunner defaultRunner =
            new ApplicationContextRunner().withConfiguration(
                    AutoConfigurations.of(DefaultAutoConfiguration.class));

    private final ApplicationContextRunner missingAllowedRunner =
            new ApplicationContextRunner().withConfiguration(
                    AutoConfigurations.of(MissingAllowedAutoConfiguration.class));

    @Test
    void bothTrueMatch() {
        strictRunner.withPropertyValues(
                "app.reports.enabled=true",
                "app.reports.audit-enabled=true"
        ).run(context ->
                assertThat(context).hasSingleBean(StrictMarker.class));
    }

    @Test
    void secondFalsePreventsMatch() {
        strictRunner.withPropertyValues(
                "app.reports.enabled=true",
                "app.reports.audit-enabled=false"
        ).run(context ->
                assertThat(context).doesNotHaveBean(StrictMarker.class));
    }

    @Test
    void firstFalsePreventsMatch() {
        strictRunner.withPropertyValues(
                "app.reports.enabled=false",
                "app.reports.audit-enabled=true"
        ).run(context ->
                assertThat(context).doesNotHaveBean(StrictMarker.class));
    }

    @Test
    void missingSecondPropertyPreventsMatch() {
        strictRunner.withPropertyValues(
                "app.reports.enabled=true"
        ).run(context ->
                assertThat(context).doesNotHaveBean(StrictMarker.class));
    }

    @Test
    void bothMissingPreventMatch() {
        strictRunner.run(context ->
                assertThat(context).doesNotHaveBean(StrictMarker.class));
    }

    @Test
    void havingValueTrueRejectsOtherStrings() {
        strictRunner.withPropertyValues(
                "app.reports.enabled=yes",
                "app.reports.audit-enabled=true"
        ).run(context ->
                assertThat(context).doesNotHaveBean(StrictMarker.class));
    }

    @Test
    void defaultModeAcceptsValuesOtherThanFalse() {
        defaultRunner.withPropertyValues(
                "app.reports.enabled=yes",
                "app.reports.audit-enabled=preview"
        ).run(context ->
                assertThat(context).hasSingleBean(DefaultMarker.class));
    }

    @Test
    void defaultModeRejectsAnExplicitFalse() {
        defaultRunner.withPropertyValues(
                "app.reports.enabled=yes",
                "app.reports.audit-enabled=false"
        ).run(context ->
                assertThat(context).doesNotHaveBean(DefaultMarker.class));
    }

    @Test
    void matchIfMissingTrueAllowsOneMissingKey() {
        missingAllowedRunner.withPropertyValues(
                "app.reports.enabled=true"
        ).run(context ->
                assertThat(context).hasSingleBean(MissingAllowedMarker.class));
    }

    @Test
    void matchIfMissingTrueAllowsBothMissingKeys() {
        missingAllowedRunner.run(context ->
                assertThat(context).hasSingleBean(MissingAllowedMarker.class));
    }

    @Test
    void matchIfMissingTrueStillRejectsExplicitFalse() {
        missingAllowedRunner.withPropertyValues(
                "app.reports.enabled=false"
        ).run(context ->
                assertThat(context)
                        .doesNotHaveBean(MissingAllowedMarker.class));
    }
}
~~~

With Maven Wrapper at the project root:

~~~bash
./mvnw test -Dtest=MultiplePropertyConditionTests
~~~

On Windows PowerShell:

~~~powershell
.\mvnw.cmd test -Dtest=MultiplePropertyConditionTests
~~~

**Expected result:** **All 11 tests PASS**. It does not depend on a fixed stdout string because Maven/Surefire logs vary by version. The verification point is that the marker beans exist only in the cases permitted by the decision table.

**Why use \`ApplicationContextRunner\`?** It creates a lightweight ApplicationContext for each property combination, applies the selected auto-configuration, and lets you directly verify whether beans are registered. This avoids starting an entire web application and is especially suitable when testing Spring Boot conditional annotations.

**Project application note:** for an \`@AutoConfiguration\` class in a real library/starter, register the class in \`META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports\`; in the test above, \`AutoConfigurations.of(...)\` directly loads the class under test. It is not required to create an imports file just to run this test.

## 7. Condition Evaluation Flow and Limitations

Conceptually, Spring Boot can be understood as performing:

~~~text
Full name = prefix + "." + each name

For each name:
  If Environment does not contain the property:
    name result = matchIfMissing
  If Environment contains the property:
    If havingValue is empty string (default):
      name result = value differs from "false"
    If havingValue is specified:
      name result = value matches havingValue

Final result = name 1 result AND name 2 result AND ... AND name N result
~~~

This is an **explanatory model**, not verbatim Spring Boot source code. With \`name={"enabled","audit-enabled"}\`, the condition evaluates the two full names **independently** before producing the overall result.

### Where to place the annotation?

- On **\`@Bean\`**: if the condition does not match, only the bean defined by that method is skipped; other beans in the same configuration class can still be considered.
- On an **\`@AutoConfiguration\`** class or **\`@Configuration\`** class: if the condition does not match, the beans belonging to that configuration will not be registered through that class.
- Evaluation occurs when Spring processes configuration conditions, so **changing a property in a file after the application has started generally does not automatically create or remove beans**. A restart or a dedicated configuration-refresh mechanism is needed if the project actually supports it.

### Cases where it should not be applied mechanically

**Multiple names are not OR.** When the business rule is "enable if A **or** B", \`name={"A","B"}\` is logically wrong. Design a separate OR condition, such as a custom \`Condition\` or condition-combining utility compatible with your Boot version.

**Checking collections/maps:** The Javadoc warns that \`@ConditionalOnProperty\` is not reliable for inferring collection existence solely from indexed elements. For example, an existing \`app.targets[0]\` key does not necessarily make \`name="targets"\` match. For requirements involving collection/map data, use binding and an appropriate dedicated condition.

**Properties set in multiple sources:** Spring Environment resolves values according to PropertySource precedence order. A key might be set in \`application.yml\` yet overridden by a command-line argument or environment variable. The condition checks the **effective value returned by Environment**, not just the contents of a single file.

**Key notation:** use dashed notation as recommended by Spring Boot. In environments using environment variables, name-mapping rules depending on PropertySource/Boot can affect the resolved value; it is best to verify the exact value in Environment when debugging.

## 8. Common Errors and How to Fix Them

| Symptom | Common cause | How to handle |
| --- | --- | --- |
| Only \`enabled=true\` is set yet bean is still absent | Missing \`audit-enabled\` and \`matchIfMissing=false\` | Declare both, or reconsider the business requirement |
| \`enabled=true\`, \`audit-enabled=false\` yet expecting the bean | Mistaking multiple \`name\` entries for OR | Understand AND; if OR is needed, create a different condition |
| \`enabled=yes\` yet \`havingValue="true"\` does not match | Using exact value comparison, \`yes\` differs from \`true\` | Set the value \`true\` as required |
| Setting \`name="enabled,audit-enabled"\` | A single string instead of an array of two strings | Use \`name={"enabled", "audit-enabled"}\` |
| Two properties need two different values | One \`havingValue\` applies to all | Split into conditions with different \`havingValue\` if supported by the version |
| \`matchIfMissing=true\` causes bean to appear when unconfigured | Both missing keys are treated as passing | Keep default \`false\` if explicit declaration is required |
| Placing annotation on the whole class makes many beans disappear | Condition scope covers the entire configuration | Move the condition down to the specific \`@Bean\` to check |
| Does not match even though YAML file looks right | Effective value overridden or property name differs | Inspect Environment and the conditions evaluation report |

### Diagnosing with Spring Boot

When an expected bean is not seen, you can enable **debug** when running the Spring Boot application:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

Or run the packaged JAR with \`--debug\`. The **Conditions Evaluation Report** shows which auto-configurations matched/did not match and why. If the project uses Actuator and allows access to the corresponding endpoint, the **\`/actuator/conditions\`** endpoint also provides condition data. Do not expose internal diagnostic endpoints publicly if the deployment environment does not require it.

In tests, prefer **\`ApplicationContextRunner\`** with cases for **both keys present, each key missing, false values, and both missing**. These cases quickly catch misunderstandings between AND and OR.

## 9. Self-Check Questions

**Question 1.** \`@ConditionalOnProperty(prefix="app", name={"a","b"}, havingValue="true")\` with configuration \`app.a=true\`, \`app.b=false\`. Is the bean created?

**Answer:** No. The two sub-conditions have an **AND** relationship and \`b\` does not satisfy the expected value.

**Question 2.** Same annotation as above, but only \`app.a=true\`, while \`app.b\` is completely absent. Does it match?

**Answer:** No. \`matchIfMissing\` defaults to \`false\`, so missing \`b\` causes the overall condition not to match.

**Question 3.** If \`matchIfMissing=true\` is set, does having both keys absent match?

**Answer:** Yes, because each missing key is treated as passing. However, a key present with value \`false\` still causes the condition not to match if \`havingValue="true"\`.

**Question 4.** If \`havingValue\` is omitted, do \`app.a=preview\` and \`app.b=true\` match?

**Answer:** Yes, because by default each key must be present and its value must not equal \`false\`.

**Question 5.** Need \`app.a=true\` and \`app.b=async\`. Can you set \`havingValue={"true","async"}\`?

**Answer:** No. \`havingValue\` has type \`String\`, not \`String[]\`. Split conditions per expected value (when the version supports repeatable annotations) or build a suitable composite condition.

## 10. Official References

- Spring Boot 3.5 Javadoc — \`@ConditionalOnProperty\`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html
- Spring Boot 4.0 Javadoc — \`@ConditionalOnProperty\`: https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html
- Spring Boot Reference — Creating Your Own Auto-configuration, Property Conditions section: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
