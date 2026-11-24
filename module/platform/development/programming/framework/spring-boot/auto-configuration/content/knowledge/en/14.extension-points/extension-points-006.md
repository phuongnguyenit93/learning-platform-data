# Designing Strategy interfaces and replaceable beans for Spring Boot library users

## 1. The library extensibility problem

Suppose an HTTP client library has a default retry policy: retry on HTTP 429 or 5xx server errors, up to a fixed maximum number of attempts. An application using the library may need different rules—for example, retrying only certain internal error codes, limiting by tenant, or reading policies from custom configuration.

If the library hardcodes the algorithm inside `AcmeClient`, users must modify the source, fork the library, or build a completely separate client. A good extension point lets applications swap the **algorithm** while keeping how the client invokes that algorithm unchanged.

The **Strategy** pattern solves the design side:
- Publish a stable interface describing the replaceable behavior.
- Provide a sensible default implementation.
- Have the client depend only on the interface.
- Allow the application to supply another implementation as a Spring bean.

Spring Boot adds a **bean back-off** mechanism so auto-configuration automatically uses the default implementation when the application has not declared its own strategy. The central annotation is `@ConditionalOnMissingBean`.

## 2. Designing the strategy interface as a public contract

An extension interface is part of the **library's API**. It needs to accurately express the decision the library delegates to the application without exposing internal details.

Example `RetryPolicy`:

~~~java
package com.acme.client;

public interface RetryPolicy {

    /**
     * @param failedAttempt number of failed request attempts, starting at 1
     * @param statusCode HTTP status of the failed attempt
     * @return true if the client is allowed to make the next attempt
     */
    boolean shouldRetry(int failedAttempt, int statusCode);
}
~~~

The contract must clarify the following points:

1. **Parameter semantics:** does `failedAttempt` start at 1 or 0? Does it count the initial call? Can `statusCode` be a synthetic code when no HTTP response was received?
2. **Return semantics:** does `true` mean retry immediately, or merely that the policy permits retrying while the client still enforces deadlines/cancellation?
3. **Responsibility boundaries:** the Strategy decides whether to retry; the client executes requests, enforces total duration limits, closes responses, and records telemetry.
4. **Errors and invalid inputs:** specify how invalid arguments and exceptions thrown by the strategy are handled. Do not leave this behavior to vary arbitrarily across implementations.
5. **Thread safety:** a Spring bean is often shared across many requests. The contract should require implementations to be safe under concurrent calls or hold only immutable state.
6. **Stability:** avoid putting internal classes, specific Spring beans, private structures, or hard-to-evolve types into the public interface.

The interface should live in an API package that library users can import, such as `com.acme.client`. The default implementation can reside in a separate implementation package. Users need to know the interface and implementation rules, without depending on the default class.

**Do not create an overly broad interface** like `LibraryStrategy` with dozens of unrelated methods. Each point of variation should have a small contract, a business-expressive name, and clear semantics.

## 3. The library's default implementation

The library provides `DefaultRetryPolicy`:

~~~java
package com.acme.client;

public final class DefaultRetryPolicy implements RetryPolicy {

    private final int maxAttempts;

    public DefaultRetryPolicy() {
        this(3);
    }

    public DefaultRetryPolicy(int maxAttempts) {
        if (maxAttempts < 1) {
            throw new IllegalArgumentException(
                    "maxAttempts must be at least 1");
        }
        this.maxAttempts = maxAttempts;
    }

    @Override
    public boolean shouldRetry(int failedAttempt, int statusCode) {
        if (failedAttempt < 1) {
            throw new IllegalArgumentException(
                    "failedAttempt must start at 1");
        }

        boolean transientFailure =
                statusCode == 429 || (statusCode >= 500 && statusCode <= 599);

        return failedAttempt < maxAttempts && transientFailure;
    }
}
~~~

With `maxAttempts=3`:
- Failed attempt 1: can retry if status is 429 or 5xx.
- Failed attempt 2: can retry if status still falls in those groups.
- Failed attempt 3: no further retry because the total attempt limit has been reached.
- Status 400, 401, 404, or 503? 503 is in 5xx so it can be retried; the 4xx codes in this example are not retried.

This is an illustrative policy, not a recommendation that every HTTP client should retry every 5xx. Production libraries must consider request idempotency, `Retry-After`, exponential backoff, jitter, deadlines, load shedding, and the risk of duplicating write operations.

**The default implementation should be independent of Spring** when Spring APIs are not needed. That way users can unit-test it or use it directly outside a container; Spring only handles bean registration and dependency injection.

## 4. Client depends on the interface

The client receives `RetryPolicy` via its constructor:

~~~java
package com.acme.client;

import java.util.Objects;

public final class AcmeClient {

    private final RetryPolicy retryPolicy;

    public AcmeClient(RetryPolicy retryPolicy) {
        this.retryPolicy = Objects.requireNonNull(retryPolicy);
    }

    public boolean shouldRetry(int failedAttempt, int statusCode) {
        return retryPolicy.shouldRetry(failedAttempt, statusCode);
    }
}
~~~

`AcmeClient` does not need to know whether the active implementation is `DefaultRetryPolicy`, `TenantRetryPolicy`, or a class written by the application. This is **Dependency Inversion**: the client depends on an abstraction; implementations adhere to the same contract.

The flow can be visualized as:

~~~mermaid
flowchart TD
    A["Application starts up"] --> B{"RetryPolicy bean already exists?"}
    B -->|"No"| C["Register DefaultRetryPolicy"]
    B -->|"Yes"| D["Use the application's implementation"]
    C --> E["Inject RetryPolicy into AcmeClient"]
    D --> E
    E --> F["AcmeClient calls shouldRetry()"]
~~~

Each context selects one implementation for a single-strategy extension point. Defining an application bean only changes policy behavior; it does not require modifying the client or replacing the whole library.

## 5. Registering the default bean with @ConditionalOnMissingBean

The library's auto-configuration:

~~~java
package com.acme.client.autoconfigure;

import com.acme.client.AcmeClient;
import com.acme.client.DefaultRetryPolicy;
import com.acme.client.RetryPolicy;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class AcmeClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(RetryPolicy.class)
    DefaultRetryPolicy retryPolicy() {
        return new DefaultRetryPolicy();
    }

    @Bean
    AcmeClient acmeClient(RetryPolicy retryPolicy) {
        return new AcmeClient(retryPolicy);
    }
}
~~~

Reading the condition:

~~~java
@ConditionalOnMissingBean(RetryPolicy.class)
~~~

Meaning: register the default bean from `retryPolicy()` only if the `BeanFactory` does not already contain a bean matching type `RetryPolicy` within the condition's search scope.

There are two branches:

| Bean supplied by the application | Condition | Outcome |
| --- | --- | --- |
| No `RetryPolicy` implementation | Matches | Spring registers `DefaultRetryPolicy` |
| One `RetryPolicy` implementation | Does not match | Default bean is skipped; application bean is used |
| Multiple `RetryPolicy` implementations | Does not match | No extra default is created; a single-value client may become ambiguous unless a candidate is selected |

**Why check the interface?** That is the replacement contract. If the condition only checked `DefaultRetryPolicy.class`, a custom bean implementing `RetryPolicy` would not cause the condition to back off; Spring could register both, and a client injecting by interface would encounter multiple candidates.

**Why does the method return the concrete type?** `DefaultRetryPolicy` gives Spring richer return-type metadata. The condition already specifies `RetryPolicy.class`, while the concrete return type informs the container of the exact type before instantiation. Spring Boot recommends declaring the most specific return type possible on `@Bean` methods, especially when using bean conditions.

`@ConditionalOnMissingBean` should be placed in the library's **auto-configuration**. Conditions only inspect bean definitions already processed at evaluation time; Spring Boot guarantees auto-configurations are applied after user-defined bean definitions. Putting the same condition on a normal early-scanned configuration can make the outcome depend on processing order.

## 6. Users replace the strategy with their own bean

The application does not need to edit library classes. It implements the interface and declares a bean in application configuration:

~~~java
package com.example.app;

import com.acme.client.RetryPolicy;

public final class BusinessRetryPolicy implements RetryPolicy {

    @Override
    public boolean shouldRetry(int failedAttempt, int statusCode) {
        return failedAttempt <= 5 && statusCode == 503;
    }
}
~~~

Registering the implementation:

~~~java
package com.example.app;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class RetryConfiguration {

    @Bean
    BusinessRetryPolicy businessRetryPolicy() {
        return new BusinessRetryPolicy();
    }
}
~~~

When the application starts:
1. Spring processes application configuration and registers the `BusinessRetryPolicy` bean.
2. Spring Boot processes `AcmeClientAutoConfiguration`.
3. `@ConditionalOnMissingBean(RetryPolicy.class)` detects the user bean implementing the interface, so the default method is skipped.
4. The `AcmeClient` bean receives `BusinessRetryPolicy` via its `RetryPolicy` parameter.

The bean name can be `businessRetryPolicy`; it does not need to match the `retryPolicy` name of the default method. Replacement is based on **bean type**, not overriding a bean definition of the same name.

If users prefer configuration via component scan, the implementation class can be annotated with `@Component` provided it falls within the application's scan scope. For libraries and large applications, explicit `@Bean` configuration is usually easier to read and control.

## 7. Why does the user bean take precedence?

Auto-configuration is a mechanism for conditionally providing defaults. Spring Boot recommends using `@ConditionalOnMissingBean` so users can replace auto-configured beans when they want different behavior.

Processing order is the key factor:

- Bean definitions from application configuration are registered first.
- Library auto-configuration is applied afterwards.
- Conditions observe bean definitions processed up to that point.
- If a matching bean already exists, the library's default bean backs off.

Therefore, publish auto-configuration through the official mechanism and place conditions there. Do not rely on accidental scan order or assume that a class on the classpath automatically becomes a bean.

### Registering auto-configuration in the JAR

Create the file:

`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

Contents:

~~~text
com.acme.client.autoconfigure.AcmeClientAutoConfiguration
~~~

This is the step that lets Spring Boot discover auto-configuration when the starter/library is placed on the classpath. Simply writing a class annotated with `@AutoConfiguration` without registering it in the imports file will not automatically apply the configuration.

### The default bean should not be an unconditionally scanned component

Do not both annotate `DefaultRetryPolicy` with `@Component` so component scanning creates a bean and register it via a `@Bean` method with `@ConditionalOnMissingBean`. If component scanning already created the default bean, the condition sees the interface exists and backs off; yet a customizing application can no longer replace the default as intended because the component bean is always registered. Let auto-configuration own creating the default bean.

## 8. One or multiple strategies? Handling candidates explicitly

The example above designs a **single strategy** per `AcmeClient`. If the application registers two beans implementing `RetryPolicy`:
- `@ConditionalOnMissingBean(RetryPolicy.class)` sees a bean already exists and skips the default.
- The `AcmeClient(RetryPolicy retryPolicy)` constructor requires a single candidate.
- If Spring cannot determine a single unique candidate, context startup can fail with a multiple matching beans error, typically `NoUniqueBeanDefinitionException`.

There are three design directions depending on the contract.

### 8.1. Single strategy: require strictly one implementation

This is the simplest option. The application registers at most one `RetryPolicy` bean. If none is declared, the library uses the default. If one custom bean is declared, the default backs off.

### 8.2. Multiple implementations, selecting one primary bean

The application can mark a custom bean with `@Primary` when multiple candidates exist:

~~~java
@Bean
@Primary
BusinessRetryPolicy businessRetryPolicy() {
    return new BusinessRetryPolicy();
}
~~~

`@Primary` helps Spring prioritize that bean for single-value dependencies when multiple candidates exist and there is strictly one primary bean. It does **not** eliminate other beans, nor does it replace `@ConditionalOnMissingBean`; the condition decides whether to create the default, while `@Primary` decides which candidate is injected when multiple beans coexist.

Alternatively, use `@Qualifier` when a consumer intentionally requests a specifically named/tagged variant. For a library API, qualifiers must be documented so users can supply matching metadata; avoid hardcoding an internal qualifier that is hard to replace.

### 8.3. Multiple strategies participating together

If business requirements genuinely want multiple policies to run, design the consumer to accept a collection:

~~~java
public AcmeClient(List<RetryPolicy> retryPolicies) {
    this.retryPolicies = List.copyOf(retryPolicies);
}
~~~

`@Order`/`Ordered` can be used to sort elements in the collection. This is a **pipeline/chain** model, distinct from a single replaceable strategy. You must specify how results combine (AND, OR, first-match, short-circuit), ordering, exception handling, and empty-collection behavior.

**Do not use `@Order` to resolve single-bean injection**; `@Order` is not a unique-candidate selection mechanism like `@Primary`.

## 9. Distinguishing commonly confused mechanisms

| Mechanism | Role | Effect on extension point |
| --- | --- | --- |
| `Strategy interface` | Defines the replaceable algorithm contract | Decouples the client from implementations |
| `@ConditionalOnMissingBean(Strategy.class)` | Registers default when no matching bean exists | Lets user beans replace the default |
| `@Primary` | Selects preferred candidate for single-value dependency when multiple beans exist | Picks one bean among existing beans |
| `@Qualifier` | Narrows candidates by declared qualifier | Selects a variant with matching metadata |
| `@Order`/`Ordered` | Sorts beans in collection/order-aware contexts | Fits when multiple strategies participate together |
| `@ConditionalOnProperty` | Enables configuration based on a property | Chooses configuration branches by property value; does not swap beans by interface alone |
| Bean name | Bean identifier in the context | Not a type-based replacement contract |

### Do not rely on bean definition overriding

Do not instruct users to create a bean with the same name as the default bean and expect Spring to override it. That approach depends on enabling overriding and easily causes conflicts. Auto-configuration design should use explicit type-based conditions to back off before registering a default.

## 10. Complete test example with ApplicationContextRunner

Auto-configuration tests should create isolated contexts for each case: without a custom bean and with a custom bean. Spring Boot's `ApplicationContextRunner` fits well because it lets you supply auto-configurations and user configurations per test.

Create `src/test/java/com/example/app/RetryPolicyAutoConfigurationTest.java` in a Java 17+ project with `spring-boot-starter-test` (Spring Boot 3.3, JUnit 5, and AssertJ):

~~~java
package com.example.app;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class RetryPolicyAutoConfigurationTest {

    interface RetryPolicy {
        boolean shouldRetry(int failedAttempt, int statusCode);
    }

    static final class DefaultRetryPolicy implements RetryPolicy {
        @Override
        public boolean shouldRetry(int failedAttempt, int statusCode) {
            return failedAttempt < 3
                    && (statusCode == 429
                    || (statusCode >= 500 && statusCode <= 599));
        }
    }

    static final class BusinessRetryPolicy implements RetryPolicy {
        @Override
        public boolean shouldRetry(int failedAttempt, int statusCode) {
            return failedAttempt <= 5 && statusCode == 503;
        }
    }

    static final class AcmeClient {
        private final RetryPolicy retryPolicy;

        AcmeClient(RetryPolicy retryPolicy) {
            this.retryPolicy = retryPolicy;
        }

        boolean shouldRetry(int failedAttempt, int statusCode) {
            return retryPolicy.shouldRetry(failedAttempt, statusCode);
        }
    }

    @AutoConfiguration
    static class LibraryAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(RetryPolicy.class)
        DefaultRetryPolicy retryPolicy() {
            return new DefaultRetryPolicy();
        }

        @Bean
        AcmeClient acmeClient(RetryPolicy retryPolicy) {
            return new AcmeClient(retryPolicy);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserRetryConfiguration {

        @Bean
        BusinessRetryPolicy businessRetryPolicy() {
            return new BusinessRetryPolicy();
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(LibraryAutoConfiguration.class));

    @Test
    void registersDefaultWhenUserHasNoStrategy() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(RetryPolicy.class);
            assertThat(context).hasSingleBean(DefaultRetryPolicy.class);
            assertThat(context).doesNotHaveBean(BusinessRetryPolicy.class);
            assertThat(context).hasSingleBean(AcmeClient.class);

            AcmeClient client = context.getBean(AcmeClient.class);
            assertThat(client.shouldRetry(1, 503)).isTrue();
            assertThat(client.shouldRetry(1, 404)).isFalse();
            assertThat(client.shouldRetry(3, 503)).isFalse();
        });
    }

    @Test
    void userStrategyReplacesDefaultAndIsInjected() {
        runner.withUserConfiguration(UserRetryConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(RetryPolicy.class);
                    assertThat(context).hasSingleBean(BusinessRetryPolicy.class);
                    assertThat(context).doesNotHaveBean(DefaultRetryPolicy.class);
                    assertThat(context).hasSingleBean(AcmeClient.class);

                    AcmeClient client = context.getBean(AcmeClient.class);
                    assertThat(client.shouldRetry(1, 503)).isTrue();
                    assertThat(client.shouldRetry(5, 503)).isTrue();
                    assertThat(client.shouldRetry(1, 500)).isFalse();
                    assertThat(client.shouldRetry(6, 503)).isFalse();
                });
    }
}
~~~

Run from a Gradle project configured with Spring Boot and `spring-boot-starter-test`:

~~~bash
./gradlew test --tests "com.example.app.RetryPolicyAutoConfigurationTest"
~~~

On Windows:

~~~powershell
.\gradlew.bat test --tests "com.example.app.RetryPolicyAutoConfigurationTest"
~~~

**Expected result:** both tests PASS.

- The first test proves the default bean is created and the client uses the default policy.
- The second test registers user configuration alongside auto-configuration; the default bean backs off, `BusinessRetryPolicy` is injected into the client, and behavior changes to match the custom algorithm.
- Assertions check bean types and behavior; they do not depend on Gradle stdout.
- The fixture feeds auto-configuration directly into `ApplicationContextRunner`, so an imports file is not needed in the test. A real starter still needs `AutoConfiguration.imports` as shown in section 7.

These tests are runnable examples when dependencies and packages are set up properly; execute them in your project to verify the specific build environment.

## 11. Design mistakes and diagnostics

| Symptom | Cause | Fix |
| --- | --- | --- |
| Default and custom coexist | Condition checks the default class instead of the strategy interface | Use `@ConditionalOnMissingBean(RetryPolicy.class)` |
| Custom bean does not replace default | Custom class is not registered or does not implement the right interface | Check `@Bean`/component scan and actual type |
| `NoUniqueBeanDefinitionException` | Multiple strategy beans exist while consumer injects one candidate | Register only one bean, or use `@Primary`/`@Qualifier` appropriately |
| Client cannot find strategy | Client auto-configuration ran while default backed off and custom bean was not processed yet | Ensure custom bean is user configuration or order auto-configurations properly |
| Users must scan the library package | Library relies on application component scan to register defaults | Register the default via `@Bean` in auto-configuration |
| Renaming the bean still fails to swap implementation | Condition checks by type, not by bean name | Implement the right interface; do not rely on matching names |
| Condition does not back off even though custom bean is in code | Bean was not registered yet when condition ran, or return type does not expose a specific enough type | Check ordering and `@Bean` method return type |
| Custom policy fails under concurrent requests | Implementation holds unsafe mutable state | Use immutable state or proper synchronization |
| Excessive retries or duplicate requests | Strategy ignores idempotency, deadlines, `Retry-After`, or backoff | Define policy and client responsibilities clearly, cap total time/attempts |
| Unsure which bean is selected | Actual context was not inspected | Use `ApplicationContextRunner`, inspect bean types and the condition report |

### Investigation procedure

1. Confirm the interface is the exact type required by the client constructor.
2. Verify the custom bean is actually registered in the right `ApplicationContext`.
3. Verify the auto-configuration is listed in `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` and not excluded by another condition.
4. Verify `@ConditionalOnMissingBean` specifies the strategy interface.
5. Verify `@Bean` methods providing implementations declare concrete return types.
6. If multiple candidates exist, check `@Primary`/`@Qualifier` or switch to a collection model.
7. Enable `--debug` or `debug=true` to inspect Spring Boot's Condition Evaluation Report. You can use `ApplicationContextRunner` to accurately reproduce the default/custom branches.

## 12. Principles for designing durable extension points

- **Publish a small API:** the interface should only contain the customizable behavior, with JavaDoc covering parameters, return values, errors, and concurrency.
- **Provide useful defaults:** users installing the starter without extra configuration still get sensible behavior.
- **Use types as the contract:** `@ConditionalOnMissingBean(Strategy.class)` accurately expresses the extension point; avoid checking bean names or the default implementation class.
- **Place conditions in auto-configuration:** user-defined bean definitions are processed before default conditions are evaluated.
- **Clients depend on abstractions:** constructors accept the interface, rather than instantiating the default class via `new DefaultStrategy()`.
- **Keep the default implementation separate:** do not let component scanning register the default unconditionally when custom beans are meant to replace it.
- **Choose single vs. multi-strategy upfront:** single strategy uses single-value injection; pipelines use collections and ordering/combination rules.
- **Do not turn `@Primary` into a back-off mechanism:** `@Primary` only selects a candidate when multiple beans exist; `@ConditionalOnMissingBean` decides whether to register the default bean.
- **Test both branches:** without a custom bean and with a custom bean; if multiple strategies are supported, also test ambiguity, qualifier/primary, or collection ordering.
- **Preserve API compatibility:** changing an interface signature breaks the library's contract. When adding behavior, consider default methods, new interfaces, or adapters to minimize impact on existing implementations.

## 13. Knowledge self-check

1. Why does the client take `RetryPolicy` instead of `DefaultRetryPolicy`? **To depend on the contract and allow multiple implementations to replace it.**
2. Is `@ConditionalOnMissingBean(DefaultRetryPolicy.class)` enough for a custom strategy to replace the default? **No**; a custom class has a different type from the default, so the condition could still create the default. Check the `RetryPolicy.class` interface.
3. When the application provides a `BusinessRetryPolicy implements RetryPolicy` bean, what happens? **The condition does not match and the default bean is skipped.**
4. Does the custom bean need the same name as the `retryPolicy()` method? **No**; the condition is declared by type.
5. Why should the condition live in auto-configuration? **Because it only inspects bean definitions already processed, and auto-configuration is applied after user-defined bean definitions.**
6. If two `RetryPolicy` beans exist, is the default created? **No**, because the condition already sees a matching bean; however, a single-value client can become ambiguous.
7. Does `@Primary` prevent the default bean from being registered? **No**; it only prioritizes one candidate when multiple beans coexist.
8. Does `@Order` replace `@Primary` for a constructor injecting a single strategy? **No**; `@Order` is for sorting collections/order-aware components.
9. Why should `@Component` not be put on the default implementation in this design? **Because component scanning can register the default unconditionally, defeating auto-configuration back-off.**
10. What proves the application actually replaced the strategy? **The context has only the custom strategy, not the default, and client behavior reflects the custom implementation.**

## Official references

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): condition annotations, `@ConditionalOnMissingBean`, bean method return types, user-defined bean definitions, and `ApplicationContextRunner`.
- [Spring Boot 3.3.13 — `@ConditionalOnMissingBean` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html): matching when no suitable bean exists and limits based on already processed bean definitions.
- [Spring Boot 3.3 — `@AutoConfiguration` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html): role of auto-configuration and before/after mechanisms.
- [Spring Framework — `@Primary` and `@Fallback`/candidate selection](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-primary.html): selecting a candidate for single-value dependencies when multiple beans exist.
- [Spring Framework — `@Bean` JavaDoc and reference](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html): registering a bean definition from a `@Bean` method and bean type by return type.
