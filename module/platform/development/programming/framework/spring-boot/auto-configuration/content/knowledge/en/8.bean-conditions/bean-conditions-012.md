# Two Default Configurations Both Satisfy `@ConditionalOnMissingBean`: What Does Ordering Decide?

In Spring Boot Auto Configuration, two libraries or two modules may both want to provide a default bean for the **same service type**. Both declare `@ConditionalOnMissingBean` to back off in favor of an application-defined bean. When no bean exists yet, at first glance both appear "eligible." So who ultimately provides the bean?

**Key idea:** The condition is evaluated when Spring **processes and registers bean definitions**, based on the definitions processed **up to that point**. If configuration A is applied first, A can register its bean first; by the time B is reached, B's "missing bean" condition is no longer satisfied. Therefore, **the order between auto-configurations can decide which default configuration wins**. This is not a simultaneous check over an immutable snapshot of all configurations.

## 1. Distinguishing the Concepts

- **Bean definition:** the metadata Spring registers about a bean (name, type, how to create it…), which can exist before the actual bean object is instantiated.
- **`@ConditionalOnMissingBean`:** matches only when no bean *satisfying the search criteria* exists yet among the bean definitions the context has processed. It can search by `value`/`type`, `name`, annotation, and context scope; on a `@Bean` method, if no type is specified, it defaults to inferring from the **declared return type** of the method.
- **Auto-configuration:** a default configuration class collected and ordered by Spring Boot via the auto-configuration mechanism. Application bean definitions are typically registered before auto-configurations, allowing default configurations to *back off* when the user has already provided a bean.
- **Configuration application order** differs from **bean instantiation order**. `@AutoConfiguration(before = …)`/`after = …` govern definition registration order; when instances are created also depends on dependencies, `@DependsOn`, lazy initialization, and context lifecycle.

A "missing" condition is always tied to **specific criteria**. For example, `@ConditionalOnMissingBean(PaymentGateway.class)` checks whether a `PaymentGateway`-typed bean exists yet, rather than asking "is there any bean at all anywhere in the system?".

## 2. What Happens with Two Competing Defaults?

Suppose two auto-configurations both have a method:

```java
@Bean
@ConditionalOnMissingBean(PaymentGateway.class)
PaymentGateway gateway() {
    // Returns each library's implementation.
    return ...; // Illustrative code, not a standalone compilable method.
}
```

Suppose initially there is **no** user-provided `PaymentGateway`, and A is processed before B:

| Moment | `PaymentGateway` Bean Definition Present? | Action |
| --- | --- | --- |
| Before processing A | No | A's condition matches. |
| Processing A | No, at condition evaluation time | A registers the `gatewayA` definition. |
| Processing B | Yes, `gatewayA` from A | B's condition does not match; `gatewayB` is not registered. |
| After configuration processing | One default from A | When needed, Spring later instantiates the corresponding bean. |

If B comes before A, then **B can win symmetrically**. The statement "both satisfy the condition" is only true if you look at the *initial state abstractly*; in practice, each condition is evaluated when its turn comes and can see the result of earlier registrations.

If the application **declares its own** `PaymentGateway`, both A and B (when they are auto-configurations processed after user beans) will typically *back off*: neither registers its default bean.

**Note:** If A checks for missing `GatewayA` while B checks for missing `GatewayB`, both conditions can **still match** even if both `GatewayA` and `GatewayB` implement `PaymentGateway`. To compete for the same default slot, check **the same contract type** such as `PaymentGateway.class`. Checking by **name** vs. by **type** can also yield different outcomes.

## 3. Runnable Verification Example: Java 17 and Spring Boot 3.x

The example below does not need a web application: `ApplicationContextRunner` creates a small context and lets you verify exactly which auto-configuration registers the bean. Both configurations declare the same condition; A is explicitly ordered **before** B. The class order passed to `AutoConfigurations.of(…)` is intentionally B then A to emphasize that Boot sorts using auto-configuration metadata.

Create the structure:

```text
bean-order-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── demo/
                └── CompetingDefaultsTest.java
```

**`pom.xml`**:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>bean-order-demo</artifactId>
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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

**`src/test/java/demo/CompetingDefaultsTest.java`**:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class CompetingDefaultsTest {

    interface Gateway {
        String provider();
    }

    // A must be applied before B.
    @AutoConfiguration(before = BetaAutoConfiguration.class)
    static class AlphaAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(Gateway.class)
        Gateway alphaGateway() {
            return () -> "alpha";
        }
    }

    @AutoConfiguration
    static class BetaAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(Gateway.class)
        Gateway betaGateway() {
            return () -> "beta";
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserConfiguration {

        @Bean
        Gateway userGateway() {
            return () -> "user";
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner().withConfiguration(
                    AutoConfigurations.of(
                            BetaAutoConfiguration.class,
                            AlphaAutoConfiguration.class));

    @Test
    void alphaWinsWhenNoUserBeanExists() {
        runner.run(context -> {
            assertThat(context.getBeansOfType(Gateway.class))
                    .containsOnlyKeys("alphaGateway");
            assertThat(context.getBean(Gateway.class).provider())
                    .isEqualTo("alpha");
        });
    }

    @Test
    void userBeanMakesBothDefaultsBackOff() {
        runner.withUserConfiguration(UserConfiguration.class).run(context -> {
            assertThat(context.getBeansOfType(Gateway.class))
                    .containsOnlyKeys("userGateway");
            assertThat(context.getBean(Gateway.class).provider())
                    .isEqualTo("user");
        });
    }
}
```

Run in the `bean-order-demo` directory:

```bash
mvn test
```

**Expected result:** both tests pass; in the first test only `alphaGateway` exists, and in the second test only `userGateway` exists. The test does not print application stdout, so do not assume a fixed console line; Maven logs and summary counts may vary by environment.

Explanation:

1. `AlphaAutoConfiguration` declares `before = BetaAutoConfiguration.class`, so it must be applied before `BetaAutoConfiguration`, regardless of the order of the two classes in the `AutoConfigurations.of` call.
2. Once the `alphaGateway` definition is registered, B's `@ConditionalOnMissingBean(Gateway.class)` sees a matching bean already exists and backs off.
3. When `UserConfiguration` is present, `userGateway` is available before both auto-configurations; hence both A and B back off.
4. If you change A's annotation to `@AutoConfiguration(after = BetaAutoConfiguration.class)` and change the first test's expectation to `betaGateway`/`"beta"`, B becomes the winning default. That is a hands-on modification to the example, not a simultaneous code branch.

This example uses nested auto-configuration classes inside a **test** and loads them directly via `AutoConfigurations.of`. In a **real starter**, place auto-configuration classes in a separate package so component scan does not pick them up, and list their fully qualified class names in `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` (Spring Boot 3.x). Do not use line order in the imports file as a contract determining who wins.

## 4. Choosing and Fixing Order Properly

When two auto-configurations have a specific priority relationship:

```java
// Excerpt from an actual configuration class:
@AutoConfiguration(before = SecondaryGatewayAutoConfiguration.class)
public class PrimaryGatewayAutoConfiguration {
    // @Bean with @ConditionalOnMissingBean(Gateway.class)
}
```

Or declare it on the configuration that needs to run **after**:

```java
@AutoConfiguration(after = PrimaryGatewayAutoConfiguration.class)
public class SecondaryGatewayAutoConfiguration {
    // @Bean with @ConditionalOnMissingBean(Gateway.class)
}
```

Equivalents are `@AutoConfigureBefore` and `@AutoConfigureAfter`. For a direct relationship between two configurations, `before/after` is clearer and more durable than implicitly relying on class names, dependency order, or line order in `AutoConfiguration.imports`. For independent auto-configurations that should not reference each other directly, Spring Boot also has `@AutoConfigureOrder` to set a general priority level; it should not replace an explicit dependency relationship expressible with `before/after`.

Do not confuse:

- `@Order` on beans, `@Primary`, or `@Qualifier` determine priority/selection in other contexts (such as injection); they **do not guarantee the processing order of two auto-configurations** to resolve missing-bean conditions.
- `@DependsOn` governs instantiation relationships; it **does not** cause a bean definition to be evaluated earlier so another configuration's condition can see it.
- Swapping two dependencies in `pom.xml` or two lines in the imports file is not a reliable way to dictate which default wins.
- Using `@ConditionalOnMissingBean` in regular user configuration can produce results dependent on definition registration timing. Spring Boot recommends using this condition in **auto-configuration**, where application-defined beans have usually already been processed.

If two providers actually represent **two different functional choices**, there should be an explicit selection mechanism: for instance, each branch uses `@ConditionalOnProperty` with its own value (and clearly defines the default branch), or only one auto-configuration is activated via appropriate classpath/scope conditions. `before/after` resolves priority **when both are valid**, but does not replace provider selection design.

## 5. Diagnosing Unexpected Results

1. **Identify the target bean.** Do both branches truly check `@ConditionalOnMissingBean(Gateway.class)`, or does each infer a different return type? Does one branch check `name` instead of `type`? Also watch `search` for parent/child contexts.
2. **Check auto-configuration ordering.** Are `@AutoConfiguration(before/after)` or `@AutoConfigureBefore/After` declared on the right two actual auto-configuration classes? Are they loaded through the auto-config mechanism (instead of component scan or ordinary `@Import`)?
3. **Inspect the Condition Evaluation Report.** With a Boot application, start with `--debug` or configure logging to see which conditions matched/did not match; in tests, use `ConditionEvaluationReportLoggingListener`. Messages like "found bean …" show which definition the later condition saw.
4. **Check registered beans, not just instantiated objects.** A bean may be lazy, yet its definition still exists and causes `@ConditionalOnMissingBean` not to match.
5. **Write tests for all three key scenarios:** no user-declared bean, user bean present, and one auto-configuration branch disabled. `ApplicationContextRunner` helps lock in the starter's behavioral contract across upgrades.

### Common Mistakes

| Symptom | Common Cause | Fix |
| --- | --- | --- |
| Default B wins when A was wanted | B applied first or A ineligible for another reason | Declare `before/after` relationship and check the report. |
| Both beans exist; type-based injection is ambiguous | Conditions check two different types/names, or configurations are not processed as auto-config | Have both check the same contract type; check how they are registered. |
| Custom bean exists yet default is still added | Custom bean registered too late, or declared type/condition criteria mismatch | Put custom bean in user configuration and ensure sufficiently specific type. |
| Added `@Primary` yet two beans still exist | `@Primary` does not remove other beans | Fix conditions and registration order; use `@Primary` only when actually resolving injection. |
| Used `@Order`/`@DependsOn` yet outcome unchanged | Confusing injection/instantiation order with registration order | Use metadata specifically designed for auto-configuration. |

## 6. Self-Check Exercise

- If A and B both use `@ConditionalOnMissingBean(Gateway.class)`, there is no user bean, and A is applied first: which bean gets registered? **A**, assuming no other condition blocks A.
- If `@Bean Gateway customGateway()` is added from user configuration: will either A or B still create a default? **No**, when that bean has been registered before the two auto-configurations are evaluated.
- If A checks for missing `AlphaGateway.class` and B checks for missing `BetaGateway.class`: is a single `Gateway` guaranteed? **No**; the two conditions check two different types.
- If `@AutoConfiguration(after = B.class)` is placed on A, what changes? **B has priority to be applied before A**, so B can register its default first and A backs off.
- Want to be sure object instantiation order also matches auto-configuration order? **Cannot be inferred** solely from `before/after`; look at dependencies and bean lifecycle.

**Remember:** `@ConditionalOnMissingBean` is a **back-off mechanism at bean definition evaluation time**. To make two competing default configurations for the same type behave predictably, (1) use the same target bean type criterion, (2) declare explicit auto-configuration order if there is priority, and (3) test both the defaults and user-customized beans.

### Reference Documentation

- Spring Boot Reference — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- Spring Boot API — `@AutoConfiguration`: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html