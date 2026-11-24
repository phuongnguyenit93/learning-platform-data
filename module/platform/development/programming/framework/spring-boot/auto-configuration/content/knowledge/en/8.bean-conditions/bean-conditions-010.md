# @ConditionalOnSingleCandidate: When One Candidate Bean or One @Primary Bean Exists

## 1. Purpose and Meaning

In Spring Boot Auto-configuration, some auxiliary beans should only be created when Spring can select **a single bean by data type** to inject into them. The **@ConditionalOnSingleCandidate** annotation in the **org.springframework.boot.autoconfigure.condition** package addresses this scenario.

The condition matches when **the BeanFactory already knows of at least one eligible candidate bean matching the specified type** and can determine a unique candidate:

- Only **one** eligible candidate bean of that type exists: **matches**.
- **Multiple** eligible candidate beans exist, and **exactly one bean is marked @Primary**: **matches**.
- No candidates exist, or multiple candidates exist without a unique selection: **does not match**.

Key point: "single candidate" refers to **the ability to select one bean for autowiring**, not necessarily that only a single instance of that type exists in the ApplicationContext. Thus, two implementations can coexist and the condition still matches if only one implementation is `@Primary`.

This annotation is essentially a **@Conditional** condition evaluated by **OnBeanCondition**. It is typically placed on a **@Bean** method or an auto-configuration class (**@AutoConfiguration**), and is not a runtime toggle that switches after the application has started.

## 2. Decision Table: Candidate Count and @Primary

Suppose the condition is checking type **PaymentGateway** and the listed beans are all eligible candidates.

| PaymentGateway Beans Present at Evaluation Time | Result | Reason |
| --- | --- | --- |
| No beans at all | Does not match | No candidate exists to inject |
| Only gatewayA | Matches | gatewayA is the sole candidate |
| gatewayA and gatewayB, neither @Primary | Does not match | Cannot pick a single bean by type alone |
| gatewayA (@Primary) and gatewayB | Matches | gatewayA is the sole preferred candidate |
| gatewayA (@Primary) and gatewayB (@Primary) | Does not match | Two beans share priority, still ambiguous |
| Only gatewayA (@Primary) | Matches | Still only one candidate; @Primary is unnecessary |

**@Primary** does not make the other beans disappear: they can still be retrieved by name, used with `@Qualifier`, or injected into a collection. `@Primary` only provides preference when selecting one bean for a matching injection point.

A subtle point: the condition counts **eligible candidates**, not necessarily every physical bean. According to current Spring Boot Javadoc, beans that are not autowire candidates, not default candidates, or are fallback candidates are ignored when determining candidates. On a different Spring Boot version, check the corresponding Javadoc before relying on newer candidate-filtering rules.

## 3. Syntax and Attributes

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnSingleCandidate;
import org.springframework.boot.autoconfigure.condition.SearchStrategy;

// The following snippets illustrate how to write the annotation; not a standalone program.
@ConditionalOnSingleCandidate(PaymentGateway.class)
@ConditionalOnSingleCandidate(value = PaymentGateway.class)
@ConditionalOnSingleCandidate(type = "example.PaymentGateway")
@ConditionalOnSingleCandidate(
    value = PaymentGateway.class,
    search = SearchStrategy.CURRENT
)
~~~

In the syntax examples above, each annotation is an **alternative option**—do not place all four simultaneously on the same Java element.

- **value**: the type to check, e.g. PaymentGateway.class. This is the common choice when the application has that type on the classpath.
- **type**: fully qualified class name as a string. Useful for optional classes; do not use **value** and **type** at the same time.
- **search**: bean lookup scope across a parent–child context hierarchy. Defaults to **SearchStrategy.ALL**; **CURRENT** checks only the current context; **ANCESTORS** checks only parent contexts.

If creating a composite annotation (meta-annotation) for a condition depending on a class that may be absent from the classpath, consider string-based **type** per the Javadoc guidance. To keep the lesson easy to read and test, the following examples specify the type directly in **value**.

### Placing on a Method or Configuration Class?

~~~java
// Assumes PaymentGateway, GatewayClient, and their constructors are already defined.
@AutoConfiguration
class GatewayClientAutoConfiguration {

    @Bean
    @ConditionalOnSingleCandidate(PaymentGateway.class)
    GatewayClient gatewayClient(PaymentGateway gateway) {
        return new GatewayClient(gateway);
    }
}
~~~

At the **@Bean** level, only the gatewayClient bean is governed by the condition; other beans in the same configuration can still be registered. When placed on the **@AutoConfiguration class**, the condition decides whether that entire configuration is applied. Choose the annotation placement according to what genuinely needs to depend on a single candidate.

## 4. Runnable Test Example with Java 17+ and Spring Boot

The following example uses JUnit 5, AssertJ, and **ApplicationContextRunner** (from spring-boot-test) to observe all four basic cases without starting a web server. It can be placed in a Spring Boot Maven project that already has **spring-boot-starter** and **spring-boot-starter-test** dependencies. Create the file **src/test/java/example/SingleCandidateConditionTests.java**:

~~~java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnSingleCandidate;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

import static org.assertj.core.api.Assertions.assertThat;

class SingleCandidateConditionTests {

    interface Gateway {
        String name();
    }

    record Client(Gateway gateway) {
    }

    @AutoConfiguration
    static class ClientAutoConfiguration {

        @Bean
        @ConditionalOnSingleCandidate(Gateway.class)
        Client client(Gateway gateway) {
            return new Client(gateway);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class OneGateway {

        @Bean
        Gateway alphaGateway() {
            return () -> "alpha";
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class TwoGateways {

        @Bean
        Gateway alphaGateway() {
            return () -> "alpha";
        }

        @Bean
        Gateway betaGateway() {
            return () -> "beta";
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class OnePrimaryGateway {

        @Bean
        @Primary
        Gateway alphaGateway() {
            return () -> "alpha";
        }

        @Bean
        Gateway betaGateway() {
            return () -> "beta";
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(ClientAutoConfiguration.class)
                    );

    @Test
    void noGatewayDoesNotCreateClient() {
        runner.run(context ->
                assertThat(context).doesNotHaveBean(Client.class));
    }

    @Test
    void oneGatewayCreatesClient() {
        runner.withUserConfiguration(OneGateway.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(Client.class);
                    assertThat(context.getBean(Client.class)
                            .gateway().name()).isEqualTo("alpha");
                });
    }

    @Test
    void twoGatewaysWithoutPrimaryDoNotCreateClient() {
        runner.withUserConfiguration(TwoGateways.class)
                .run(context ->
                        assertThat(context).doesNotHaveBean(Client.class));
    }

    @Test
    void twoGatewaysWithOnePrimaryCreateClient() {
        runner.withUserConfiguration(OnePrimaryGateway.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(Client.class);
                    assertThat(context.getBean(Client.class)
                            .gateway().name()).isEqualTo("alpha");
                });
    }
}
~~~

Run with the project's Maven Wrapper:

~~~bash
./mvnw test -Dtest=SingleCandidateConditionTests
~~~

On Windows PowerShell, use **.\mvnw.cmd test -Dtest=SingleCandidateConditionTests**. If Maven is installed globally on the project machine, use **mvn test -Dtest=SingleCandidateConditionTests**.

**Expected result:** all four tests succeed; there is no Client bean in the two missing-candidate or ambiguous cases, and there is one Client bean in the two cases where a Gateway can be selected. The final test also confirms the injected Gateway is **alpha**, the bean marked **@Primary**. Detailed console output depends on the Maven version, plugins, and logging configuration; do not treat a fixed log snippet as part of the annotation's definition.

**Explaining the test mechanics:**

1. ApplicationContextRunner registers user configurations before processing auto-configuration in this test case.
2. Spring Boot evaluates the condition on the client(...) method based on the **Gateway** beans registered at that time.
3. If the condition does not match, the Client bean definition is not added to the context.
4. If it matches, Spring creates Client and resolves the Gateway parameter. With two Gateways and one @Primary, the preferred bean is selected.

**Why put @Primary on the @Bean method?** In the example, the Gateways are created by `@Bean` methods. Placing `@Primary` directly on the bean-creating method clearly expresses the priority of that bean definition itself.

## 5. Practical Application in Real Auto-Configuration

Suppose an integration library wants to create a **PaymentAuditService** to record audits when the application can supply an unambiguous **PaymentGateway**. The core idea is:

~~~java
// Illustrative snippet, assuming PaymentGateway and PaymentAuditService types already exist.
@AutoConfiguration
class PaymentAuditAutoConfiguration {

    @Bean
    @ConditionalOnSingleCandidate(PaymentGateway.class)
    PaymentAuditService paymentAuditService(PaymentGateway gateway) {
        return new PaymentAuditService(gateway);
    }
}
~~~

If the application only has StripeGateway, the audit bean is created. If the application has StripeGateway and OfflineGateway without `@Primary`, the audit configuration skips this method to avoid arbitrarily picking a payment gateway. If StripeGateway is marked `@Primary` and OfflineGateway is not, the audit configuration can create the bean and receive StripeGateway.

In a real starter/library, the auto-configuration class is typically declared in **META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**. If the PaymentGateway bean comes from another auto-configuration, order them so the Gateway-providing configuration is processed first, for example using the **after** attribute of `@AutoConfiguration` or **@AutoConfigureAfter** appropriate to your Spring Boot version.

**Distinguishing bean definition order from instance creation time:** the condition is decided while processing **bean definitions**; it does not wait for all beans in the application to finish instantiating before counting them. Therefore, auto-configuration ordering can change the outcome even when looking at the started application makes it seem like enough beans exist.

## 6. Comparison with Similar Conditions

| Annotation | Question the Condition Answers | Scenario with Two Beans of the Same Type, No @Primary |
| --- | --- | --- |
| **@ConditionalOnBean(PaymentGateway.class)** | Has a matching PaymentGateway bean already been registered? | Usually matches because at least one bean exists |
| **@ConditionalOnMissingBean(PaymentGateway.class)** | Does no matching PaymentGateway bean exist yet? | Does not match |
| **@ConditionalOnSingleCandidate(PaymentGateway.class)** | Can a single PaymentGateway candidate be uniquely selected? | Does not match |

Do not replace **@ConditionalOnSingleCandidate** with **@ConditionalOnBean** on a `@Bean` method that requires injecting a single parameter by type when multiple candidates may appear: the "exists" condition can match while the injection point remains ambiguous. Conversely, **@ConditionalOnMissingBean** is typically used for providing default beans that users can replace; its purpose differs from selecting a single dependency.

**@Qualifier** also differs from **@Primary**: an injection point can use `@Qualifier("alphaGateway")` to pick among multiple beans, whereas **@ConditionalOnSingleCandidate(Gateway.class)** checks the uniqueness of candidates by type Gateway. It does not automatically infer the `@Qualifier` value from the `@Bean` method parameter to turn two non-`@Primary` candidates into a single candidate. If you need to pin a bean by name, design the condition and injection parameters explicitly according to your library's contract.

## 7. Important Notes, Common Mistakes, and Troubleshooting

1. **Misinterpreting "single" as counting total instances.** Having two beans with exactly one `@Primary` still matches; see the table in section 2.
2. **Forgetting `@Primary` when multiple implementations exist.** Spring Boot may skip the auto-configuration's auxiliary bean because it cannot select a candidate; consider putting `@Primary` on the main bean or splitting configuration per actual needs.
3. **Putting two `@Primary` annotations.** Two tied priorities do not resolve ambiguity. Pick one clear primary.
4. **Confusing `@Qualifier` with `@Primary`.** A qualifier on an injection point does not alter the annotation's type-only check.
5. **Placing the annotation too broadly.** Putting it on the auto-configuration class can exclude every `@Bean` in the class; put it on the specific method if only one bean needs this condition.
6. **Lacking a sufficiently clear declared type.** For example, a `@Bean` method declared to return `Object` even though it actually returns `Gateway` can cause type inference during bean definition inspection to behave unexpectedly. Declare a return type reflecting the contract, e.g., `Gateway`.
7. **Wrong auto-configuration order.** The condition only recognizes bean definitions already processed. When depending on beans registered by another auto-configuration, declare ordering explicitly.
8. **Overlooking parent–child contexts.** By default `search=ALL` checks the entire hierarchy. If you only want beans in the current context, use `search=SearchStrategy.CURRENT`; when checking only parent contexts, use `ANCESTORS`.
9. **Assuming a match guarantees the whole application starts cleanly.** The condition only checks whether a candidate of the specified type can be selected; constructors, other dependencies, or initialization logic can still fail.
10. **Relying on version-specific behavior without checking.** Concepts like default candidate / fallback candidate have explicit filtering rules in current Spring Boot Javadoc; verify against your project's actual version.

When a bean is unexpectedly missing, enable the condition report with the **--debug** option when running Spring Boot; in applications with Actuator and access enabled for the corresponding endpoint, **/actuator/conditions** also shows which conditions matched or did not match. For unit tests, use **ApplicationContextRunner** to build controlled bean combinations and inspect **ConditionEvaluationReport**.

## 8. Self-Check Questions

**Question 1.** There are two PaymentGateway beans, one of which is `@Primary`. Does `@ConditionalOnSingleCandidate(PaymentGateway.class)` match?

**Answer:** Yes, if the beans are eligible candidates and only one bean is marked `@Primary`; the condition can select a single preferred candidate.

**Question 2.** There are three beans of the same type, none marked `@Primary`; a `@Bean` method carries this condition and takes one parameter of that type. What happens?

**Answer:** The condition does not match, so the bean created by that method is not registered. You should not assume by default that the entire application is guaranteed to fail: other beans may continue operating normally.

**Question 3.** Two beans of the same type have no `@Primary`, but the `@Bean` method's parameter has `@Qualifier`. Does that qualifier alone make `@ConditionalOnSingleCandidate` match?

**Answer:** No. The condition checks whether a candidate of the specified type can be selected, and does not pull the qualifier from the parameter as its selection criterion.

**Question 4.** Why is it necessary to consider the order of auto-configuration classes?

**Answer:** Because the condition is evaluated against the bean definitions already processed at that moment. If the configuration creating the dependency runs later, the condition may not see the dependency you expect.

## 9. Official Reference Documentation

- Spring Boot Javadoc — ConditionalOnSingleCandidate: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnSingleCandidate.html
- Spring Boot Javadoc — SearchStrategy: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/condition/SearchStrategy.html
- Spring Boot Reference — Creating Your Own Auto-configuration (bean conditions and ApplicationContextRunner): https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
