# Rules for Combining Multiple Requirements in Bean Presence and Absence Conditions

## 1. Purpose and Context

In Spring Boot Auto Configuration, `@ConditionalOnBean` and `@ConditionalOnMissingBean` decide whether a configuration or a `@Bean` method is registered based on **the bean definitions already known to the ApplicationContext/BeanFactory at evaluation time**. This lesson focuses on the case where **one annotation contains multiple requirements**: multiple bean types, multiple bean names, multiple annotations, or a combination of those groups.

After this lesson, you should be able to answer three questions: (1) Under what logic are the requirements combined? (2) Must they all match on **a single bean**? (3) Why is the condition "at least one bean is missing" different from `@ConditionalOnMissingBean` declaring multiple types?

## 2. Core Rule: All Present / All Absent

Let `hasA` = BeanFactory has recognized a matching bean of type `A`; `hasB` similarly for `B`.

- `@ConditionalOnBean({A.class, B.class})` matches when `hasA && hasB`. **Every requirement must be satisfied**.
- `@ConditionalOnMissingBean({A.class, B.class})` matches when `!hasA && !hasB`. **No requirement may be satisfied**: both A and B are absent.
- The requirements do not have to be satisfied by **the same bean**. Two separate beans, one of type A and one of type B, are enough for the first condition.
- The two annotations above **are not complementary branches** when multiple types are declared. There are states where neither matches.

| Bean A present? | Bean B present? | `@ConditionalOnBean({A,B})` | `@ConditionalOnMissingBean({A,B})` |
| --- | --- | --- | --- |
| No | No | Does not match | **Matches** |
| Yes | No | Does not match | Does not match |
| No | Yes | Does not match | Does not match |
| Yes | Yes | **Matches** | Does not match |

Interpreting the case where only A exists: the `OnBean` condition rejects because B is missing; the `OnMissingBean` condition also rejects because A already exists. **"Missing both A and B" is completely different from "missing A or B."** By De Morgan's law, the negation of `hasA && hasB` is `!hasA || !hasB`, not `!hasA && !hasB`.

## 3. How Multiple Requirements Are Combined per Attribute

### 3.1. Multiple Types: `value` or `type`

```java
@ConditionalOnBean({DataSource.class, TransactionManager.class})
// Requires at least one bean of type DataSource
// AND at least one bean of type TransactionManager.

@ConditionalOnMissingBean({DataSource.class, TransactionManager.class})
// Matches only when there is no bean of EITHER of the two types above.
```

`value` takes `Class<?>[]`; `type` takes fully qualified class names (`String[]`), useful when you need to check types by name to avoid referencing optional classes directly. "Having a bean of type T" includes beans recognized as T or a matching subtype/implementation; it does not require the bean name to be `t`. Do not infer that multiple elements in `value` act as an OR operator.

### 3.2. Multiple Names: `name`

```java
@ConditionalOnBean(name = {"primaryStore", "auditStore"})
// Both bean names must exist.

@ConditionalOnMissingBean(name = {"primaryStore", "auditStore"})
// Both bean names must be absent.
```

Here matching is by registered bean name in the BeanFactory; a bean with a different name but the same type does not automatically satisfy a specific name requirement. Choose `name` when the contract depends on bean identity, and choose `value`/`type` when it depends on type.

### 3.3. Multiple Annotations: `annotation`

```java
@ConditionalOnBean(annotation = {Primary.class, Lazy.class})
// Requires a bean carrying @Primary and a bean carrying @Lazy;
// they can be two different beans.

@ConditionalOnMissingBean(annotation = {Primary.class, Lazy.class})
// There must be no bean matching @Primary, and no bean matching @Lazy.
```

This is a condition on annotations associated with registered beans; it **does not** require a single bean to carry both annotations simultaneously. The example only illustrates how requirements are combined and does not recommend using `@Lazy` as a feature criterion in real applications.

### 3.4. Combining `value`, `type`, `name`, `annotation`

```java
@ConditionalOnBean(
    value = {PaymentGateway.class, AuditWriter.class},
    name = {"paymentGateway", "auditWriter"}
)
```

All requirements of each group must be satisfied: type `PaymentGateway` must exist, type `AuditWriter` must exist, and both listed names must exist. **There is no guarantee** that the bean named `paymentGateway` is the bean satisfying the `PaymentGateway` type requirement. Each criterion can be satisfied by a different bean. With `@ConditionalOnMissingBean` and a similar set of groups, the condition matches only when **none of the type/name/annotation requirements** is satisfied.

If you need to assert that **a bean named X has type Y**, check both the name and type of that same bean using a custom `Condition` or an explicit check against the `BeanFactory` (`containsBean("X")` and `isTypeMatch("X", Y.class)`); do not infer a "same bean" relationship from the independent attributes of `@ConditionalOnBean`.

## 4. Hands-On Example: Outcomes of the Four States

An integration feature should only be registered when **both** `PaymentGateway` and `AuditWriter` are already present. An empty-configuration helper component should only appear when **no input component exists**. If the user provides exactly one input, neither conditional bean is created. This is intentional in the example to expose the gap between the two branches.

Place the following file in a **Spring Boot 3.3.x, Java 17+** project with `spring-boot-starter-test`, JUnit Jupiter, and AssertJ: `src/test/java/example/conditions/MultipleBeanConditionTests.java`.

```java
package example.conditions;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class MultipleBeanConditionTests {

    interface PaymentGateway {}
    interface AuditWriter {}

    static final class DefaultPaymentGateway implements PaymentGateway {}
    static final class DefaultAuditWriter implements AuditWriter {}
    static final class IntegratedService {}
    static final class NoInputsNotice {}

    @Configuration(proxyBeanMethods = false)
    static class OnlyPayment {
        @Bean
        PaymentGateway paymentGateway() {
            return new DefaultPaymentGateway();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class OnlyAudit {
        @Bean
        AuditWriter auditWriter() {
            return new DefaultAuditWriter();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class BothInputs {
        @Bean
        PaymentGateway paymentGateway() {
            return new DefaultPaymentGateway();
        }

        @Bean
        AuditWriter auditWriter() {
            return new DefaultAuditWriter();
        }
    }

    @AutoConfiguration
    static class FeatureAutoConfiguration {
        @Bean
        @ConditionalOnBean({PaymentGateway.class, AuditWriter.class})
        IntegratedService integratedService(
                PaymentGateway paymentGateway,
                AuditWriter auditWriter) {
            return new IntegratedService();
        }

        @Bean
        @ConditionalOnMissingBean({PaymentGateway.class, AuditWriter.class})
        NoInputsNotice noInputsNotice() {
            return new NoInputsNotice();
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner().withConfiguration(
                    AutoConfigurations.of(FeatureAutoConfiguration.class));

    @Test
    void noInputBeansCreatesOnlyNotice() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(NoInputsNotice.class);
            assertThat(context).doesNotHaveBean(IntegratedService.class);
        });
    }

    @Test
    void paymentOnlyCreatesNeitherConditionalBean() {
        runner.withUserConfiguration(OnlyPayment.class).run(context -> {
            assertThat(context).doesNotHaveBean(NoInputsNotice.class);
            assertThat(context).doesNotHaveBean(IntegratedService.class);
        });
    }

    @Test
    void auditOnlyCreatesNeitherConditionalBean() {
        runner.withUserConfiguration(OnlyAudit.class).run(context -> {
            assertThat(context).doesNotHaveBean(NoInputsNotice.class);
            assertThat(context).doesNotHaveBean(IntegratedService.class);
        });
    }

    @Test
    void bothInputsCreateOnlyIntegratedService() {
        runner.withUserConfiguration(BothInputs.class).run(context -> {
            assertThat(context).hasSingleBean(IntegratedService.class);
            assertThat(context).doesNotHaveBean(NoInputsNotice.class);
        });
    }
}
```

**How to run:** In a Spring Boot project using Gradle, with JUnit Platform enabled and the appropriate test dependencies declared, execute:

```bash
./gradlew test --tests example.conditions.MultipleBeanConditionTests
```

In a Maven project configured with Surefire/JUnit 5, you can run `./mvnw -Dtest=MultipleBeanConditionTests test`. **Expected result:** all four tests PASS; do not assume exact stdout strings because how Gradle/Maven prints reports depends on the build setup. `ApplicationContextRunner` builds isolated ApplicationContexts; `withUserConfiguration` registers user-provided beans and `AutoConfigurations.of(...)` brings the auto-configuration into evaluation.

Note: the ```java``` block above is a complete test file; do not place the four `@Configuration` classes under component scan in a real application, because they are configurations for **separate test scenarios**.

## 5. When You Want "At Least One Condition True" or "At Least One Bean Missing"

Clearly distinguish your intent before choosing an annotation:

| Business Requirement | Logical Expression with `hasA`, `hasB` | How to Express |
| --- | --- | --- |
| Require both A and B | `hasA && hasB` | `@ConditionalOnBean({A.class, B.class})` |
| Require both A and B absent | `!hasA && !hasB` | `@ConditionalOnMissingBean({A.class, B.class})` |
| Have A **or** B | `hasA || hasB` | `AnyNestedCondition` or custom `Condition` |
| Missing A **or** B | `!hasA || !hasB` | `AnyNestedCondition` or custom `Condition` |
| Exactly one of A/B exists | `hasA != hasB` | Custom `Condition`, with four-state tests |

Illustrative example of an `AnyNestedCondition` for the requirement **at least one of A/B is missing** (this snippet uses the `PaymentGateway` and `AuditWriter` types already defined in the project, and is not a standalone Java file):

```java
import org.springframework.boot.autoconfigure.condition.AnyNestedCondition;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.ConfigurationCondition;

final class EitherInputMissing extends AnyNestedCondition {
    EitherInputMissing() {
        super(ConfigurationCondition.ConfigurationPhase.REGISTER_BEAN);
    }

    @ConditionalOnMissingBean(PaymentGateway.class)
    static class PaymentMissing {}

    @ConditionalOnMissingBean(AuditWriter.class)
    static class AuditMissing {}
}
```

Use `@Conditional(EitherInputMissing.class)` on the configuration class or bean method needing that condition, importing `org.springframework.context.annotation.Conditional`. The two nested conditions are two OR branches; when **at least one** "missing" branch matches, the whole condition matches. If you only need a default bean of **a single type** for users to override, usually use only `@ConditionalOnMissingBean(MyService.class)` without bundling unrelated types.

## 6. Timing and Lookup Scope Rules

1. **Timing:** conditions are based on bean definitions processed **up to evaluation time**, not a check on singletons instantiated after the application finishes starting. A bean declared later will not necessarily be counted. Place these conditions in **auto-configuration**, where user beans have already been processed beforehand, and adjust ordering between auto-configurations if there are dependencies.
2. **Ordering between auto-configurations:** if configuration B needs a bean declared by configuration A, use `@AutoConfiguration(after = AAutoConfiguration.class)` (or equivalent) so B is evaluated after A. `@DependsOn` only specifies **bean initialization** order, and does not solve bean registration condition evaluation order.
3. **Annotation placement:** placing on a `@Bean` governs that bean method itself; placing on a `@Configuration`/`@AutoConfiguration` class governs the registration of the configuration class and its beans. Choose the narrow scope if only one bean needs the condition.
4. **Leaving attributes empty:** on a `@Bean` method, if `value`, `type`, or `name` is not declared, Spring Boot 3.3 takes **the method's return type** as the default type to check. For example, `@Bean @ConditionalOnMissingBean MyService myService()` creates a default when no `MyService` bean exists yet. For Spring to recognize the type accurately, declare a sufficiently specific return type.
5. **Parent beans:** the `search` attribute defaults to `SearchStrategy.ALL` (including searching parent contexts). `SearchStrategy.CURRENT` searches only the current context; `ANCESTORS` searches parent contexts according to the API contract. In systems with parent/child contexts, the search strategy can alter the condition evaluation outcomes.
6. **Beans inside generic containers:** `parameterizedContainer` allows counting certain generic-parameterized wrappers during type checks. For example, when configured with `value = User.class, parameterizedContainer = Registration.class`, a `Registration<User>` bean can be recognized according to that attribute's contract. This is **not** a mechanism that automatically scans all generic wrappers.
7. **Exclusions when checking absence:** `@ConditionalOnMissingBean` has `ignored` and `ignoredType` to ignore certain bean types while looking for matching beans. `@ConditionalOnBean` does not have these two attributes; do not confuse them with excluding or deleting actual beans.

## 7. Common Mistakes and Diagnosis

- **Mistaking the list for OR.** `@ConditionalOnBean({A,B})` means **A AND B** are required. `@ConditionalOnMissingBean({A,B})` means **A AND B** are missing.
- **Assuming the two annotations cover all cases.** For "only A" or "only B," both reject. Draw a truth table before designing fallbacks.
- **Assuming all criteria must point to the same bean.** Type, name, and annotation can be satisfied by different beans. If a constraint on the same bean is needed, check name + type yourself or use a clear bean/type identifier.
- **Evaluating the condition too early.** A bean registered after the check causes unexpected results. Inspect auto-configuration ordering and available bean definition info; do not rely on constructor call order.
- **Wrong exposed type on `@Bean`.** If the actual bean is `SpecialGateway` but the method declares an overly generic return type, a condition checking `SpecialGateway` may lack the needed type info at evaluation time. Declare a useful, stable return type.
- **Confusing `name` with `@Qualifier`.** `name` checks the bean name in the container; `@Qualifier` is metadata for choosing injection candidates and is not synonymous with an arbitrary bean name.
- **Ignoring parent contexts or generic wrappers.** Check `search`/`parameterizedContainer` when multi-context setups or wrapper beans cause unexpected outcomes.

To inspect actual results: run the application with `--debug` to view the condition evaluation report, or use `ConditionEvaluationReportLoggingListener` with `ApplicationContextRunner` in tests. Focus on the specific reason which condition matched/did not match and which bean definitions were detected. For a critical feature, you should have tests for **neither A/B, only A, only B, and both A/B**; add `name`/`annotation` variants if the problem uses them.

## 8. Self-Check

1. Beans A and B are registered by two different `@Bean` methods. Does `@ConditionalOnBean({A.class, B.class})` match? **Yes**, provided both were processed in time; they do not need to be the same bean.
2. Only A exists, not B. Does `@ConditionalOnMissingBean({A.class, B.class})` match? **No**, because the "missing A" requirement is not met.
3. There is a bean named `primaryStore` but no bean of type `AuditWriter`. Does `@ConditionalOnBean(value=AuditWriter.class, name="primaryStore")` match? **No**; both the type and name requirements must be satisfied.
4. Need to activate when **one of A/B is missing**. Is using `@ConditionalOnMissingBean({A.class,B.class})` right? **No**; you need an OR combination via `AnyNestedCondition` or an equivalent `Condition`.

## Reference Documentation (Spring Boot 3.3.x)

- [`@ConditionalOnBean` — Spring Boot 3.3 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html)
- [`@ConditionalOnMissingBean` — Spring Boot 3.3 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html)
- [Creating Your Own Auto-configuration — bean conditions and testing](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
