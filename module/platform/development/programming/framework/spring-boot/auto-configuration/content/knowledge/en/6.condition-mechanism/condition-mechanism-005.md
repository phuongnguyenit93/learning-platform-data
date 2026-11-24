# Combining Multiple Conditions in Spring Boot: The All-Conditions-Must-Match Rule

## 1. Goal and Mental Model

Spring Boot auto-configuration provides default beans **conditionally** rather than registering every bean unconditionally. When a class or a **@Bean** method carries multiple conditional annotations, the key question is not "is one of these conditions true?" but **"have all required conditions been satisfied?"**.

For example, a library wants to provide a **FeatureStatus** bean only when:

1. the required Jackson API is present on the classpath;
2. the feature is enabled by a configuration property;
3. the operating mode is **standard**;
4. the application has not already supplied its own **FeatureStatus** bean.

These four requirements have a logical **AND** relationship. If any one requirement is missing, Spring Boot should not create the default **FeatureStatus**.

Notation:

~~~text
C = required class is present on the classpath
E = enabled property allows the feature
M = mode property matches
B = no bean of the same type from the application yet

Create default bean = C AND E AND M AND B
                    = C ∧ E ∧ M ∧ B
~~~

Learners will master:

- How Spring combines multiple **@Conditional...** annotations on the same class and bean method.
- How class-level and method-level conditions interact.
- Why a single **false** condition is enough to prevent the default bean.
- How to understand **@ConditionalOnProperty** with multiple property names, **havingValue**, and **matchIfMissing**.
- Distinguishing default AND from OR/NOT that must be expressed explicitly.
- How to use **ApplicationContextRunner** to prove each case and avoid misreading results when a user-defined bean is present.
- How to read the **Condition Evaluation Report** to see which condition did not match.

The hands-on lab uses **Java 21**, **Gradle**, and **Spring Boot 3.3.13** as fixed example versions; this does not imply they are the latest versions.

## 2. General Mechanism: Conditions Are Gates for Configuration and Beans

In Spring, **@Conditional** attaches one or more checks to a configuration class or a bean method. Spring Boot builds many convenient annotations on top of this mechanism, for example:

| Annotation | Condition statement |
| --- | --- |
| **@ConditionalOnClass** | The required classes can be found on the classpath. |
| **@ConditionalOnMissingClass** | The specified classes are not present. |
| **@ConditionalOnBean** | The required beans are already registered per the condition's semantics. |
| **@ConditionalOnMissingBean** | No matching bean exists yet, so default configuration can back off. |
| **@ConditionalOnProperty** | A property has a matching value or existence state. |
| **@ConditionalOnWebApplication** | The context matches the required web application type. |
| **@ConditionalOnNotWebApplication** | The context is not a web application. |
| **@ConditionalOnResource** | The specified configuration resource is present. |

A conditional annotation **does not create beans by itself**. It answers whether the framework should process the corresponding class/method. Bean creation still depends on registration steps, dependency injection, lifecycle, and other configurations.

### 2.1. AND When Multiple Annotations Appear Together

Illustrative pattern:

~~~java
@ConditionalOnClass(name = "com.fasterxml.jackson.databind.ObjectMapper")
@ConditionalOnProperty(
    prefix = "demo.feature",
    name = "enabled",
    havingValue = "true"
)
@AutoConfiguration
public class FeatureAutoConfiguration {
    // ...
}
~~~

This is an **illustrative annotation/class snippet**, not a complete Java file. For the configuration class to be applied, both the **classpath condition** and the **property condition** must match. One passing annotation does not "rescue" another failing one.

At the method level:

~~~java
@Bean
@ConditionalOnMissingBean(FeatureStatus.class)
@ConditionalOnProperty(
    prefix = "demo.feature",
    name = "mode",
    havingValue = "standard"
)
FeatureStatus featureStatus() {
    return new FeatureStatus("standard");
}
~~~

Similarly, **both conditions on the method** must pass. When the method is inside a conditional class, the class conditions must also pass before the method has a chance to create a bean.

### 2.2. AND Between Class Level and @Bean Level

Let **C** and **E** be the class conditions, and **M** and **B** be the method conditions:

~~~text
Auto-configuration class applied?
  C AND E
      |
     false --> class is skipped; bean methods are not registered
      |
     true
      v
@Bean method eligible?
  M AND B
      |
     false --> default FeatureStatus is not registered
      |
     true
      v
Register bean definition and create instance per Spring lifecycle
~~~

Do not imagine that the framework **must** run every check and collect all four booleans before deciding. In practice, Spring can **short-circuit/skip a branch early** and avoid evaluating conditions that are no longer needed. The AND model describes the **outcome rule**, not a promise of execution order or condition call counts.

## 3. Truth Table: Default Bean Created Only When All Are True

For **C ∧ E ∧ M ∧ B**:

| C | E | M | B | Create default FeatureStatus? | Explanation |
| --- | --- | --- | --- | --- | --- |
| True | True | True | True | **Yes** | All four conditions satisfied. |
| False | True | True | True | No | Required class is missing. |
| True | False | True | True | No | Feature is disabled. |
| True | True | False | True | No | Mode does not match. |
| True | True | True | False | No | User-supplied bean already exists. |
| False | False | True | True | No | At least one condition is false. |
| True | False | False | True | No | Both properties fail to match. |
| False | False | False | False | No | None of the conditions pass. |

This table lists representative rows. With four booleans there are **16** total combinations; the "Yes" outcome occurs only for **True/True/True/True**.

**Important note:** The column "Create default FeatureStatus?" does not mean "Does the context have a FeatureStatus or not?". When **B = False** because the application **already has a FeatureStatus bean**, the context still contains that bean. Only **the auto-configuration's default bean** yields.

### 3.1. Annotation Declaration Order Does Not Mean AND Order

Swapping the order of two conditional annotations in Java source does not turn AND into OR. Do not use annotation line order to force which check runs first. When bean processing order dependencies exist, handle them through proper auto-configuration design and supported ordering mechanisms, not by reordering lines of code.

### 3.2. A Condition Can Live Inside a Composed Annotation

Spring supports meta-annotations and custom conditions. When writing a composed annotation, understand the conditions it carries; in principle, all conditions applying to the same component must jointly permit that component to be processed, unless you **deliberately build a composite condition with different logic**.

For **@ConditionalOnClass** inside a meta-annotation, the Spring Boot documentation notes you should prefer the **name** attribute over a class literal to avoid metadata-processing issues in certain cases.

## 4. Understanding @ConditionalOnProperty Accurately When Combining Conditions

**@ConditionalOnProperty** is the biggest source of confusion because it distinguishes three things: whether the property exists, what its current value is, and what counts as a match when the property is missing.

### 4.1. havingValue and matchIfMissing

Example:

~~~java
@ConditionalOnProperty(
    prefix = "demo.feature",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
~~~

Meaning:

- If **demo.feature.enabled=true**: matches.
- If **demo.feature.enabled=false**: does not match.
- If **demo.feature.enabled** is not declared: **matches** because **matchIfMissing=true**.
- If the property is present with a value other than **true**: does not match the required value.

**matchIfMissing=true** does not mean Spring converts a missing property into the string **true** or creates a new property. It only determines **the condition outcome when the property is not found**.

If you write:

~~~java
@ConditionalOnProperty(
    prefix = "demo.feature",
    name = "enabled"
)
~~~

then **havingValue** defaults to the empty string, and the condition basically matches when the property **exists** and **is not equal to false** according to **@ConditionalOnProperty** semantics. Do not interpret the default syntax as "must equal boolean true". For explicit on/off switches, you should usually write **havingValue = "true"**.

### 4.2. Multiple Names in One @ConditionalOnProperty Are Also AND

Example:

~~~java
@ConditionalOnProperty(
    prefix = "demo.audit",
    name = {"enabled", "persisted"},
    havingValue = "true"
)
~~~

This is **one annotation** but two keys:

~~~text
demo.audit.enabled
demo.audit.persisted
~~~

**Both must have matching values**. It is not "enabled or persisted". Since **matchIfMissing** is not declared, it defaults to **false** when a key is missing.

| enabled | persisted | Condition matches? |
| --- | --- | --- |
| true | true | Yes |
| true | false | No |
| false | true | No |
| false | false | No |
| true | missing | No |

This example illustrates **AND inside a single annotation**, which differs from AND across separate annotations yet produces the same logical outcome.

If you use **name = {"enabled", "persisted"}** with **matchIfMissing=true**, each missing key may count as matching under the annotation's missing policy; that can enable the configuration when operators have not explicitly confirmed both. For critical features, write the desired semantics explicitly and add tests.

### 4.3. Limits of Property Conditions

**@ConditionalOnProperty** reads keys from **Environment**; it is not a complex configuration validation tool. For **collection**-shaped properties — for example configuring **demo.items[0]** while checking only **demo.items** — the result may not reflect what the author expected. When you need to inspect collection contents or complex combined rules, use an appropriate solution like **@ConfigurationProperties** with validation and a custom condition when truly needed.

### 4.4. Quick Table for a Single Key with havingValue="true"

| Property value | matchIfMissing=false | matchIfMissing=true |
| --- | --- | --- |
| Absent | No | Yes |
| "true" | Yes | Yes |
| "false" | No | No |
| "other" | No | No |

For the lab example, **enabled** and **mode** are placed separately on the class/method. Both permit **missing keys** so the example creates the bean by default, while declaring a non-matching value skips the bean.

## 5. A Complete, Runnable Example with Java 21 and Gradle

Build a workspace containing:

- Module **feature-autoconfigure**: defines **FeatureStatus**, the **@AutoConfiguration** class, and **AutoConfiguration.imports**.
- Module **sample-app**: a Spring Boot application running without a web server, printing the bean count and bean label for verification.
- Tests in the library module using **ApplicationContextRunner**, varying classpath/properties/user beans to prove the AND logic.

To have a verifiable classpath condition, the example picks Jackson's **ObjectMapper** as a **marker class**. The sample configuration does not use ObjectMapper to process JSON; the presence of the class serves as an independent fact in the condition combination. A real production integration would only check for a class if it actually needs that API.

### 5.1. Directory Structure

~~~text
conditional-and-lab/
├── settings.gradle
├── build.gradle
├── feature-autoconfigure/
│   ├── build.gradle
│   ├── src/main/java/com/example/condition/api/
│   │   └── FeatureStatus.java
│   ├── src/main/java/com/example/condition/autoconfigure/
│   │   └── FeatureAutoConfiguration.java
│   ├── src/main/resources/META-INF/spring/
│   │   └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
│   └── src/test/java/com/example/condition/autoconfigure/
│       └── FeatureAutoConfigurationTests.java
└── sample-app/
    ├── build.gradle
    └── src/main/java/com/example/consumer/
        └── SampleApplication.java
~~~

### 5.2. settings.gradle

~~~groovy
rootProject.name = 'conditional-and-lab'
include 'feature-autoconfigure', 'sample-app'
~~~

### 5.3. Root build.gradle

~~~groovy
plugins {
    id 'org.springframework.boot' version '3.3.13' apply false
    id 'io.spring.dependency-management' version '1.1.7' apply false
}

subprojects {
    apply plugin: 'java'
    apply plugin: 'io.spring.dependency-management'

    group = 'com.example'
    version = '1.0.0'

    java {
        toolchain {
            languageVersion = JavaLanguageVersion.of(21)
        }
    }

    repositories {
        mavenCentral()
    }

    dependencyManagement {
        imports {
            mavenBom 'org.springframework.boot:spring-boot-dependencies:3.3.13'
        }
    }

    tasks.withType(Test).configureEach {
        useJUnitPlatform()
    }
}
~~~

The root manages the Java toolchain, dependency versions, and JUnit Platform configuration. **The Spring Boot Gradle plugin is applied only to the application**, not to the library module, to avoid turning the library into an executable bootJar.

### 5.4. feature-autoconfigure/build.gradle

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-autoconfigure'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-json'
}
~~~

**Explanation:** The auto-configuration class uses Spring Boot APIs. Tests use Spring Boot test and the JSON starter to ensure **ObjectMapper** is on the test classpath when not deliberately hidden by **FilteredClassLoader**. The library module **does not force consumers to install Jackson** because the condition uses the string **name**.

### 5.5. sample-app/build.gradle

~~~groovy
plugins {
    id 'org.springframework.boot'
}

dependencies {
    implementation project(':feature-autoconfigure')
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-json'
}
~~~

**spring-boot-starter** provides the foundation for a non-web application; **spring-boot-starter-json** puts Jackson on the runtimeClasspath, allowing the classpath condition to match in the standard setup.

### 5.6. Defining the Default Bean Type

File **feature-autoconfigure/src/main/java/com/example/condition/api/FeatureStatus.java**:

~~~java
package com.example.condition.api;

public record FeatureStatus(String label) {
}
~~~

This Java 21 record holds only a label so distinguishing the default bean from a user bean stays easy. The goal is learning **conditions**, not business logic.

### 5.7. Auto-Configuration Class with Two Conditions, Method with Two Conditions

File **feature-autoconfigure/src/main/java/com/example/condition/autoconfigure/FeatureAutoConfiguration.java**:

~~~java
package com.example.condition.autoconfigure;

import com.example.condition.api.FeatureStatus;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(
    name = "com.fasterxml.jackson.databind.ObjectMapper"
)
@ConditionalOnProperty(
    prefix = "demo.feature",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
public class FeatureAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "demo.feature",
        name = "mode",
        havingValue = "standard",
        matchIfMissing = true
    )
    @ConditionalOnMissingBean(FeatureStatus.class)
    public FeatureStatus featureStatus() {
        return new FeatureStatus("standard");
    }
}
~~~

Explaining the order of responsibilities, **not** promising runtime execution order of individual conditions:

1. **@AutoConfiguration** allows the class to be used as an auto-configuration candidate.
2. **@ConditionalOnClass** requires ObjectMapper to exist on the classpath.
3. **@ConditionalOnProperty(enabled)** requires the feature not to be disabled, defaulting to permitted when the key is undeclared.
4. **@ConditionalOnProperty(mode)** requires the **standard** mode, also permitting an absent key.
5. **@ConditionalOnMissingBean(FeatureStatus.class)** creates the default bean only when the application has not already supplied another FeatureStatus bean.

If a class-level condition fails, the **featureStatus()** method is not registered by this auto-configuration. If the class passes yet a method condition fails, only this bean method is skipped; in a larger configuration, other methods with different conditions can still be processed.

### 5.8. Registering the Auto-Configuration Candidate

Create the exact file:

~~~text
feature-autoconfigure/src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Content:

~~~text
com.example.condition.autoconfigure.FeatureAutoConfiguration
~~~

One line per fully qualified class name, without commas or **.class**. The consuming application does not need to import this class in source; Boot reads the imports resource from the classpath.

## 6. Writing Tests for Each Condition and Each Failing Branch

**ApplicationContextRunner** lets us run lightweight contexts with each combination of properties, classloader, and user-defined beans. Tests in this project have **ObjectMapper** on the classpath thanks to the JSON starter; the negative classpath test uses **FilteredClassLoader** to hide the Jackson package.

File **feature-autoconfigure/src/test/java/com/example/condition/autoconfigure/FeatureAutoConfigurationTests.java**:

~~~java
package com.example.condition.autoconfigure;

import com.example.condition.api.FeatureStatus;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class FeatureAutoConfigurationTests {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(
                    FeatureAutoConfiguration.class
                )
            );

    @Test
    void createsDefaultWhenAllConditionsMatch() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(FeatureStatus.class);
            assertThat(context.getBean(FeatureStatus.class).label())
                .isEqualTo("standard");
        });
    }

    @Test
    void disabledFeaturePreventsDefaultBean() {
        runner.withPropertyValues(
            "demo.feature.enabled=false"
        ).run(context -> {
            assertThat(context).doesNotHaveBean(FeatureStatus.class);
        });
    }

    @Test
    void nonStandardModePreventsDefaultBean() {
        runner.withPropertyValues(
            "demo.feature.mode=legacy"
        ).run(context -> {
            assertThat(context).doesNotHaveBean(FeatureStatus.class);
        });
    }

    @Test
    void twoFailedPropertiesStillPreventDefaultBean() {
        runner.withPropertyValues(
            "demo.feature.enabled=false",
            "demo.feature.mode=legacy"
        ).run(context -> {
            assertThat(context).doesNotHaveBean(FeatureStatus.class);
        });
    }

    @Test
    void missingJacksonPreventsDefaultBean() {
        runner.withClassLoader(
            new FilteredClassLoader("com.fasterxml.jackson.databind")
        ).run(context -> {
            assertThat(context).doesNotHaveBean(FeatureStatus.class);
        });
    }

    @Test
    void userBeanWinsInsteadOfDefaultBean() {
        runner.withUserConfiguration(UserFeatureConfiguration.class)
            .run(context -> {
                assertThat(context).hasSingleBean(FeatureStatus.class);
                assertThat(context.getBean(FeatureStatus.class).label())
                    .isEqualTo("custom");
                assertThat(context.containsBean("featureStatus"))
                    .isFalse();
                assertThat(context.containsBean("customFeatureStatus"))
                    .isTrue();
            });
    }

    @Test
    void explicitMatchingPropertiesCreateDefaultBean() {
        runner.withPropertyValues(
            "demo.feature.enabled=true",
            "demo.feature.mode=standard"
        ).run(context -> {
            assertThat(context).hasSingleBean(FeatureStatus.class);
        });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserFeatureConfiguration {

        @Bean
        FeatureStatus customFeatureStatus() {
            return new FeatureStatus("custom");
        }
    }
}
~~~

### 6.1. Reading Test Results Under AND Logic

| Test | Varied condition | Expected outcome |
| --- | --- | --- |
| **createsDefaultWhenAllConditionsMatch** | None; missing properties count as matching | One default FeatureStatus exists. |
| **disabledFeaturePreventsDefaultBean** | E = false | No default bean. |
| **nonStandardModePreventsDefaultBean** | M = false | No default bean. |
| **twoFailedPropertiesStillPreventDefaultBean** | E = false, M = false | No default bean. |
| **missingJacksonPreventsDefaultBean** | C = false because class is hidden | No default bean. |
| **userBeanWinsInsteadOfDefaultBean** | B = false because user bean exists | Context has only the custom bean, no default created. |
| **explicitMatchingPropertiesCreateDefaultBean** | E = true, M = true | Default bean exists. |

The **userBeanWinsInsteadOfDefaultBean** test is especially important: the right conclusion is **"no default bean"**, not **"the context has no FeatureStatus"**. Therefore, the assertions check **hasSingleBean**, the **custom** value, the bean name **customFeatureStatus**, and that **featureStatus** does not exist.

### 6.2. Running the Tests

From the root directory:

~~~bash
gradle :feature-autoconfigure:test
~~~

If the project has the Gradle Wrapper:

~~~bash
./gradlew :feature-autoconfigure:test
~~~

On Windows PowerShell you can use **.\gradlew.bat :feature-autoconfigure:test**. Gradle displays a passing test task or reports an assertion/context-startup failure; there is no single fixed stdout identical across all environments. Passing tests are evidence for each case in the table, not proof that all dependencies on the production classpath match the test classpath.

### 6.3. What the Tests Cover and Their Limits

These tests pass **FeatureAutoConfiguration** directly into the runner via **AutoConfigurations.of**. They verify **the class/method conditions**. They **do not yet prove** that the published JAR contains the right **AutoConfiguration.imports** or that a consumer discovers the configuration simply by adding the dependency. That is why running the application in the next section is necessary.

In addition, **FilteredClassLoader** simulates a class not being found by the test context's classloader. This is well suited for testing **@ConditionalOnClass**, but does not mean all binary version conflicts, missing methods, or packaging issues have been verified.

## 7. Consuming Application: Observing AND Logic in a Real Runtime

File **sample-app/src/main/java/com/example/consumer/SampleApplication.java**:

~~~java
package com.example.consumer;

import com.example.condition.api.FeatureStatus;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class SampleApplication {

    public static void main(String[] args) {
        SpringApplication.run(SampleApplication.class, args);
    }

    @Bean
    ApplicationRunner inspectFeature(ApplicationContext context) {
        return args -> {
            var beans = context.getBeansOfType(FeatureStatus.class);
            System.out.println(
                "FeatureStatus beans: " + beans.size()
            );
            beans.values().forEach(bean ->
                System.out.println(
                    "FeatureStatus label: " + bean.label()
                )
            );
        };
    }
}
~~~

Notice package **com.example.consumer** is outside **com.example.condition.autoconfigure**. Default component scanning from **@SpringBootApplication** does not scan the auto-configuration package. When the bean appears, it comes from the candidate registered in the imports resource, not because the app package accidentally scanned the configuration class.

### 7.1. Default Scenario

Run:

~~~bash
gradle :sample-app:bootRun
~~~

Two lines printed by ApplicationRunner in the sample setup:

~~~text
FeatureStatus beans: 1
FeatureStatus label: standard
~~~

These are **two specific lines printed by our code**, not the entire Gradle/Spring Boot log. Because Jackson is on the classpath, **enabled** and **mode** are missing yet treated as matching, and no user bean exists yet, the default FeatureStatus is eligible to be created.

### 7.2. Disabling the Feature via Property

Run:

~~~bash
gradle :sample-app:bootRun --args='--demo.feature.enabled=false'
~~~

Expected check line:

~~~text
FeatureStatus beans: 0
~~~

The reason is that the class-level condition on **enabled** does not match. The **mode** condition may still be satisfied, but it does not change the overall AND result.

### 7.3. Changing Mode to a Non-Matching Value

Run:

~~~bash
gradle :sample-app:bootRun --args='--demo.feature.mode=legacy'
~~~

Expected line:

~~~text
FeatureStatus beans: 0
~~~

Here the auto-configuration class can still be eligible because ObjectMapper is present and enabled is not turned off, yet **the condition on the @Bean method** does not match.

### 7.4. Intentionally Making Two Conditions False

Run:

~~~bash
gradle :sample-app:bootRun --args='--demo.feature.enabled=false --demo.feature.mode=legacy'
~~~

Still outputs:

~~~text
FeatureStatus beans: 0
~~~

There is no need to distinguish "two falses" from "one false" when computing an AND result; a single unmet condition is enough to prevent the default bean.

### 7.5. Checking the Classpath Condition via Dependency

In a separate practice branch, remove the line:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-json'
~~~

from **sample-app/build.gradle**, then inspect:

~~~bash
gradle :sample-app:dependencies --configuration runtimeClasspath
gradle :sample-app:dependencyInsight --configuration runtimeClasspath --dependency jackson-databind
~~~

If no other dependency brings **com.fasterxml.jackson.databind.ObjectMapper** onto the runtime classpath, the classpath condition will fail to match and the default FeatureStatus will not be created. **Do not assume removing one line guarantees Jackson disappears**: Gradle might still resolve Jackson transitively via another dependency, in which case the outcome must be explained from the actual classpath.

Restore the dependency line after the experiment.

## 8. Nature of AND When Class and Method Conditions Differ

Consider two methods:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
    prefix = "demo",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
class MultiBeanAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "demo",
        name = "alpha",
        havingValue = "true"
    )
    AlphaBean alphaBean() {
        return new AlphaBean();
    }

    @Bean
    @ConditionalOnProperty(
        prefix = "demo",
        name = "beta",
        havingValue = "true"
    )
    BetaBean betaBean() {
        return new BetaBean();
    }
}
~~~

**This is an example snippet of condition structure, not a complete Java file**; the **AlphaBean/BetaBean** classes are not defined.

When **demo.enabled=false**, **both** bean methods are blocked because the class is not applied. When enabled=true, creating **AlphaBean** and **BetaBean** can differ: each method has its own condition.

Table:

| demo.enabled | demo.alpha | demo.beta | Default AlphaBean | Default BetaBean |
| --- | --- | --- | --- | --- |
| false | true | true | No | No |
| true | true | false | Yes | No |
| true | false | true | No | Yes |
| true | true | true | Yes | Yes |

A class-level condition affects **the entire configuration class**, whereas a method-level condition only decides **that bean method**. If both beans must always be present or absent together for one shared feature, put the shared condition at the class level or on an appropriate nested configuration, and keep individual conditions for needed variants.

## 9. Multiple Conditions Do Not Automatically Become OR

**Common mistake:** "Putting two @ConditionalOnProperty annotations with two different criteria means either one being true is enough." The default mechanism for multiple co-located conditions is **AND**, not OR.

If the actual business requirement is "**mode=standard OR mode=legacy**", you must express **OR** explicitly. There are straightforward approaches:

1. **Redesign the property**: check only the enabled flag in the annotation, while mode logic is handled by a **@ConfigurationProperties** class with proper validation inside a bean factory or service; use this when the goal is not actually selecting a configuration class.
2. **Use a composite condition** when you need to select an auto-configuration using OR logic, such as **AnyNestedCondition** in Spring Boot.
3. **Split into separate configurations** with independent conditions if you want distinct beans per mode. Account for cases where multiple modes/conditions match simultaneously and cause duplicate beans.

### 9.1. Example of AnyNestedCondition When You Truly Need OR

The snippet below illustrates a composite condition for the **demo.feature.mode** property. This is a **standalone Java class if placed in the same package with appropriate imports**, but when used in an application you must attach **@Conditional(OnStandardOrLegacy.class)** to the class or method you want to guard:

~~~java
package com.example.condition.autoconfigure;

import org.springframework.boot.autoconfigure.condition.AnyNestedCondition;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.ConfigurationCondition.ConfigurationPhase;

final class OnStandardOrLegacy extends AnyNestedCondition {

    OnStandardOrLegacy() {
        super(ConfigurationPhase.REGISTER_BEAN);
    }

    @ConditionalOnProperty(
        prefix = "demo.feature",
        name = "mode",
        havingValue = "standard"
    )
    static class Standard {
    }

    @ConditionalOnProperty(
        prefix = "demo.feature",
        name = "mode",
        havingValue = "legacy"
    )
    static class Legacy {
    }
}
~~~

**AnyNestedCondition** evaluates to a match if **at least one** nested condition matches. In this code: **mode=standard OR mode=legacy**. This is an **advanced optional** condition, not used in the runnable project in sections 5–7.

**Caution:** Because the two nested annotations above do **not** have **matchIfMissing=true**, a missing mode property will **not** match either one. If the requirement is to enable by default when mode is absent, explicitly design the default branch; do not silently assume OR logic shares the same behavior as the earlier AND example.

**ConfigurationPhase.REGISTER_BEAN** is appropriate here for using the condition at bean-registration level; when a condition applies at configuration level or involves other condition types, revisit the appropriate phase per the API and when required data becomes available.

### 9.2. AllNestedCondition and NoneNestedCondition

Spring Boot also provides composite condition utilities:

- **AllNestedConditions**: matches when **all** nested conditions match — explicit AND.
- **AnyNestedCondition**: matches when **at least one** nested condition matches — OR.
- **NoneNestedConditions**: matches when **none** of the nested conditions match — equivalent to NOT of OR.

You do not need AllNestedConditions just to put standard **@ConditionalOnClass** and **@ConditionalOnProperty** on the same class: combining conditions at the same target already yields AND semantics. Composite conditions are useful when requirements are complex, need reuse, or cannot be expressed readably with standard annotations.

### 9.3. NOT Does Not Mean "Missing Property"

For example, a feature "only when bean X is absent" typically uses **@ConditionalOnMissingBean(X.class)**; however, that negates **the presence of a matching bean**, not every other condition. Similarly, **@ConditionalOnMissingClass** checks class absence, not the negation of arbitrary properties or environments.

Identify the exact target of the NOT operation rather than treating an annotation name as a blanket formula for all cases.

## 10. Bean Processing Order and the Meaning of @ConditionalOnMissingBean

Logically, **@ConditionalOnMissingBean(FeatureStatus.class)** adds one more condition to the AND. Yet it is special: it evaluates **bean definitions the container has already processed up to that moment**.

In an auto-configuration library, this condition is typically used to **yield to application configuration**. Spring Boot designs auto-configuration to be applied after user-declared bean definitions have had a chance to be considered under the normal mechanism. Therefore the custom bean is visible and auto-config does not create a second default.

However, do not conclude that **@ConditionalOnMissingBean** foresees every bean that will be registered at any future time. When multiple auto-configurations depend on one another, the ordering between them can affect the outcome.

### 10.1. Do Not Rely on Imports Line Order to Solve Every Conflict

If libraries A and B both rely on the presence of a bean created by another auto-configuration, consider:

- Placing **@AutoConfiguration(after = OtherAutoConfiguration.class)** or **before** when clear ordering dependencies exist;
- Testing combinations with and without the related library;
- Avoiding overly generic bean types that cause multiple auto-configurations to accidentally back off from each other.

Auto-configuration ordering governs **the processing order of bean definitions registered by auto-configurations**, not directly the instance initialization order of every bean in the container. Startup instantiation dependencies should be designed with dependency injection and appropriate Spring mechanisms.

### 10.2. A False Condition Does Not Mean "The Application Cannot Have That Bean"

For example, if enabled=false yet the application **registers FeatureStatus itself** through another @Configuration, the context still has that custom bean. A condition only governs **the configuration/bean it is attached to**. This is why **@ConditionalOnProperty** should not be interpreted as a global switch that deletes all beans of that type.

When building production feature toggles, clarify: are we disabling **default auto-config**, disabling **all service behavior**, or blocking **an endpoint**? Those can be distinct requirements.

## 11. Diagnosing Condition Combinations with the Condition Evaluation Report

When a bean is not created, randomly adding **@Bean** methods or changing dependencies without evidence easily causes new bugs. Read the reasons why conditions matched or did not match.

### 11.1. Enabling the Report When Running the App

~~~bash
gradle :sample-app:bootRun --args='--debug'
~~~

In an application with the condition evaluation report, look for **FeatureAutoConfiguration** and related entries, such as:

- Is the condition class present?
- Does **demo.feature.enabled** have the right value, or is the key missing with **matchIfMissing=true**?
- Does **demo.feature.mode** match **standard**?
- Has an application-provided **FeatureStatus** bean already been found?

Exact content, Positive/Negative Matches grouping, and log order depend on the Spring Boot version and runtime state. Do not fabricate a sample report and treat it as exact stdout across all environments.

### 11.2. Classifying Causes by Table

| Symptom | Where to check first | Common cause |
| --- | --- | --- |
| Entire auto-config skipped | Class-level conditions / exclusions | Missing ObjectMapper, enabled=false, or excluded. |
| Auto-config matched but bean method not applied | Method-level conditions | mode is not standard, or bean already exists. |
| Context has a custom bean instead of default | @ConditionalOnMissingBean | Back-off mechanism worked as designed. |
| Tests create the bean but production does not | Dependency/property/profile differences | Test classpath has Jackson while runtime lacks it, or profile config differs. |
| Two beans of the same type exist | Registration order / conditions / bean types | Do not patch with global overriding before identifying the source. |
| Condition still matches though property undeclared | matchIfMissing | Annotation permits missing key. |
| Property condition matches when value is not true | Default havingValue | Default only requires value not equal to false, not strict true. |

### 11.3. Using the Right Configuration When Checking the Classpath

With Gradle:

~~~bash
gradle :sample-app:dependencies --configuration runtimeClasspath
gradle :sample-app:dependencyInsight --configuration runtimeClasspath --dependency jackson-databind
~~~

Do not use **testRuntimeClasspath** as proof that the production application has that class. A class present in tests but absent in the deployed artifact is a very real reason why classpath conditions yield different outcomes.

## 12. When Multiple Conditions Do Not All Need to Be Checked

In pure logic, AND can "short-circuit" upon encountering false. Yet Spring executes conditions across multiple phases of metadata, classpath, bean definition, and context processing. Therefore:

- Do not rely on annotation order to predict which log line appears first.
- Do not use side effects inside conditions to drive business logic.
- Custom conditions must behave predictably without arbitrarily mutating the context.
- Classpath conditions can often be evaluated earlier than bean-related conditions, but do not claim every condition is evaluated in a single fixed loop.
- A non-matching condition can block an entire class or just one method; know **at which level** the annotation is placed.

The standard way to verify is to **assert final context state** and **read the condition report**, not infer from a print statement placed at the end of a custom condition.

## 13. Common Design Mistakes

**Mistake 1 — Using two annotations as OR:** Wanting "either property is true" yet placing multiple conditions at the same target. Actual result is AND; express OR explicitly or change the configuration model.

**Mistake 2 — Forgetting matchIfMissing:** Wanting enabled by default yet declaring **@ConditionalOnProperty(havingValue="true")** without **matchIfMissing=true**. When the key is absent, the bean is not created. Write a test for the missing-key case.

**Mistake 3 — Misreading default havingValue:** Using the annotation without **havingValue** and assuming only true matches. Per Boot semantics, any present value other than false may count as a match; if you need strict boolean matching, declare **havingValue="true"**.

**Mistake 4 — Placing a classpath condition in the wrong place:** A **@Bean** method has a return type from an optional dependency yet is guarded only by a condition on the method itself. Spring may need to introspect the signature beforehand. Isolate such methods in a configuration class with **@ConditionalOnClass** at class level.

**Mistake 5 — Checking bean presence without distinguishing default vs. custom:** A context containing a FeatureStatus might hold the user's bean. Verify bean count, name, source, or behavior to know whether auto-config actually created the default.

**Mistake 6 — Testing only the all-true case:** With four conditions, testing only the happy path is insufficient. Write at least one negative test per independent condition plus a test proving back-off.

**Mistake 7 — Putting @ConditionalOnMissingBean where it depends on registration timing:** In typical setups, bean conditions belong carefully in auto-configuration because they depend on already processed bean definitions. Do not scatter them into app configuration expecting to see beans created later.

**Mistake 8 — Using @ConditionalOnProperty to inspect collections:** A list/indexed property key may not match as expected. Do not turn this annotation into a validation tool for complex configuration objects.

**Mistake 9 — Confusing candidates with beans:** A class listed in **AutoConfiguration.imports** is only a candidate. It can still be excluded, fail a class-level condition, or have only some of its bean methods permitted.

**Mistake 10 — Treating test runner results as discovery tests:** **AutoConfigurations.of** specifies the class directly. To confirm an external app auto-discovers the configuration, add a consumer test/app and inspect JAR imports.

## 14. Verifiable Hands-On Exercises

### Exercise 1 — Predict Combinations Before Running

With the sample configuration, evaluate the default bean outcome for:

| enabled | mode | Has ObjectMapper | Has custom FeatureStatus | Result |
| --- | --- | --- | --- | --- |
| missing | missing | Yes | No | Default present |
| true | standard | Yes | No | Default present |
| false | standard | Yes | No | No default |
| true | legacy | Yes | No | No default |
| true | standard | No | No | No default |
| true | standard | Yes | Yes | Custom bean only |
| false | legacy | No | Yes | No default; custom bean may still exist |

Explain why the last row **cannot** be shortened to "there are no beans in the context".

### Exercise 2 — Add Another Required Property

Add the requirement **demo.feature.approved=true** to the class-level **@ConditionalOnProperty** or create a separate conditional annotation. Decide whether a missing key should match or not. Add at least three tests: approved=true, approved=false, approved missing.

If two properties must both be true and both use **havingValue="true"**, consider **name={"enabled","approved"}**, remembering that **matchIfMissing** then applies under the annotation's shared policy.

### Exercise 3 — Compare Class Level and Method Level

Add a **FeatureAuditMarker** bean without a mode condition while keeping it inside FeatureAutoConfiguration. When mode=legacy, predict whether the marker bean can be created if class-level conditions match. Use tests to distinguish the effect of class-level conditions from method-level conditions.

### Exercise 4 — Design and Test OR Yourself

Allow mode **standard** or **legacy**. Write out the truth table and use **AnyNestedCondition** or an appropriate service design. Test both missing mode and mode=unsupported so you do not accidentally alter default behavior.

### Exercise 5 — Distinguish Default Bean and User Bean

When enabled=true and mode=standard, register a custom FeatureStatus. Assert there is one custom bean and no default bean. Then try enabled=false while keeping the custom bean; explain why auto-config has no authority to delete an application-created bean.

### Exercise 6 — Diagnose with Tooling

Run **--debug** with a non-matching property combination. Read the condition report and record which class-level or method-level condition caused the skip. Inspect runtimeClasspath to confirm whether ObjectMapper is actually present. State conclusions based on real output rather than copying a mock report.

## 15. Checklist Before Completing This Lesson

- [ ] Can state the rule **multiple conditions on one component = all must be satisfied**.
- [ ] Can explain the AND between conditions on the auto-configuration class and on each @Bean method.
- [ ] Can draw the truth table for **C ∧ E ∧ M ∧ B**, creating the default bean only when all are true.
- [ ] Understand the difference between **havingValue** and **matchIfMissing**.
- [ ] Know that **multiple names in one @ConditionalOnProperty must also match simultaneously**.
- [ ] Know that **@ConditionalOnMissingBean** yields to user beans rather than deleting user beans.
- [ ] Know not to use multiple conditional annotations as an undeclared OR.
- [ ] Know when to use **AnyNestedCondition**, **AllNestedConditions**, and **NoneNestedConditions**.
- [ ] Have written and run an auto-configuration example with multiple class/method conditions.
- [ ] Have run negative tests for each of C, E, M, and B.
- [ ] Have observed a consuming app receiving the default bean only when all conditions match.
- [ ] Know how to use the **Condition Evaluation Report** and **dependencyInsight** to investigate unexpected outcomes.
- [ ] Do not confuse "no default created" with "the context has zero beans of that type".

## Conclusion

The easiest rule to remember when reading Spring Boot auto-configuration is: **every condition applied to a class or a bean method must allow that component to be processed**. If a class-level condition is not satisfied, none of that class's bean methods are applied. If the class passes yet a method-level condition is not satisfied, that method does not create a bean.

For the **FeatureStatus** exercise, the formula is **C ∧ E ∧ M ∧ B**: right classpath, feature enabled, matching mode, and no existing bean of the same type. From here, learners can design safe default configurations, write tests for every false branch, understand how application-declared beans take precedence, and deliberately use composite conditions when a problem truly requires OR/NOT instead of mistaking them for AND.

## References

- [Spring Boot 3.3 — Developing Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [ConditionalOnProperty — Spring Boot API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html)
- [AnyNestedCondition — Spring Boot API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/AnyNestedCondition.html)
