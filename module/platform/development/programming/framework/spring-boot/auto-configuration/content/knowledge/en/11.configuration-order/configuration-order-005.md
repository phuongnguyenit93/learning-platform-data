# Configuration Processing Order vs. Bean Initialization Order

## 1. Lesson goal

In Spring Boot Auto Configuration, there are two **distinct** questions:

1. **Which configuration is processed first?** Spring reads metadata and processes configuration classes to decide **which bean definitions** are registered, including evaluating `@ConditionalOnBean`, `@ConditionalOnMissingBean`, and other conditions.
2. **Which bean instance is initialized first?** Once definitions exist, the container instantiates objects according to dependencies, scope, eager/lazy initialization, and constraints such as `@DependsOn`.

Core point: **ordering `@AutoConfiguration` with `before`/`after` does not mean beans from the earlier configuration will be initialized first**. Spring Boot 3.3 documentation explicitly notes that auto-configuration application order only affects **bean definition** order; **bean creation** order is governed by dependencies and `@DependsOn` relationships.

This lesson explains the two timelines, how to use the annotations properly, a tested Java 17+ example, common mistakes, and diagnostic methods.

## 2. Distinguishing four concepts

| Concept | Meaning | Question it answers |
| --- | --- | --- |
| **Configuration processing order** | Order in which Spring Boot applies auto-configurations, parses `@Bean` and conditions, and adds definitions to the container | "At condition evaluation time, which beans does Spring already **know about**?" |
| **Bean definition registration** | Name, determinable type, factory method, scope, lazy flag, dependencies, etc., stored in the BeanFactory | "Does a **blueprint to create the bean** exist yet?" |
| **Bean initialization** | The container instantiates the object, injects dependencies, and applies lifecycle/post-processing callbacks | "Has the **actual object** been created yet?" |
| **Post-startup execution order** | Logic running after context refresh, such as `ApplicationRunner`, `CommandLineRunner`, or application-ready events | "When does **business logic** begin running?" |

A bean definition can **exist** while its instance has not yet been created—for example, a `@Lazy` bean. Conversely, the fact that a bean has been initialized **does not by itself prove** its enclosing configuration was processed before another configuration in the way conditions require.

Use accurate terminology:

- "`@ConditionalOnBean(MyType.class)` matches" primarily concerns **processed bean definitions/metadata**, not whether an instance of `MyType` has been initialized.
- "`@DependsOn("cache")` ensures cache initializes before service" is a **bean initialization** constraint; it does not order how auto-configurations are evaluated.
- "`@AutoConfiguration(after = X.class)`" tells Spring Boot an auto-configuration should be **applied after X**; it does not create X's beans or force instances in X to finish creating first.

## 3. Two timelines of a single startup

Conceptual diagram, omitting Spring's internal details:

```text
AXIS A — CONFIGURATION PROCESSING / BEAN DEFINITION
Read @Configuration, auto-configuration list
    -> determine before/after ordering
    -> evaluate conditions using existing metadata
    -> register matching bean definitions
    -> finish related definition processing steps

AXIS B — INSTANCE CREATION / INITIALIZATION
BeanFactory/BeanPostProcessor ready for bean creation phase
    -> create non-lazy singletons based on demand and dependencies
    -> resolve constructor / factory-method parameters
    -> apply @DependsOn and lifecycle
    -> leave lazy or scoped beans to be created when needed

AFTER THE CONTEXT HAS REFRESHED
Run post-startup application mechanisms, e.g., ApplicationRunner
```

This is a **general rule** diagram, not a claim that every bean creation happens at one single moment: certain infrastructure beans or prematurely requested beans can be created while the container is still processing configurations. Therefore, avoid designs that rely on an "accidental" observed initialization order.

For normal singletons, `ApplicationContext` eagerly creates many beans at startup. However:

- A `@Lazy` bean has a definition beforehand, yet may not have an instance once context refresh finishes.
- A `@Lazy` bean **is still created at startup** if an eager singleton requires it via injection or `@DependsOn`.
- Prototype beans are created on demand, rather than eagerly pre-instantiated like ordinary singletons.
- Constructor/factory-method injection forces required dependencies to be ready before finishing creation of the dependent bean.

## 4. Auto-configuration **processing** order: `before`, `after`, and conditions

### 4.1. When is `after` needed?

Suppose `StorageAutoConfiguration` declares a `StorageClient` bean, while `ReportAutoConfiguration` registers `ReportService` only if Spring already has a `StorageClient` bean.

Illustrative snippet, assuming `StorageClient` and `ReportService` are defined in the project:

```java
@AutoConfiguration
class StorageAutoConfiguration {

    @Bean
    StorageClient storageClient() {
        return new StorageClient();
    }
}

@AutoConfiguration(after = StorageAutoConfiguration.class)
class ReportAutoConfiguration {

    @Bean
    @ConditionalOnBean(StorageClient.class)
    ReportService reportService() {
        return new ReportService();
    }
}
```

Here `after = StorageAutoConfiguration.class` solves **definition processing order**: by the time the condition on `reportService` is reached, Spring has had the chance to see the `StorageClient` bean definition registered by the earlier configuration. **There is no guarantee** that the `storageClient` instance was initialized before `ReportAutoConfiguration` was parsed.

An equivalent way to write it in Spring Boot 3.3 is:

```java
@AutoConfigureAfter(StorageAutoConfiguration.class)
@AutoConfiguration
class ReportAutoConfiguration {
    // @Bean methods of this configuration
}
```

Related attributes:

- `@AutoConfiguration(before = OtherAutoConfiguration.class)`: the current configuration should be applied before the other configuration.
- `@AutoConfiguration(after = OtherAutoConfiguration.class)`: the current configuration should be applied after the other configuration.
- `beforeName`, `afterName`: use the configuration's fully qualified name when avoiding direct class references; useful for optional auto-configurations on the classpath.
- `@AutoConfigureBefore`, `@AutoConfigureAfter`: dedicated annotations expressing the same ordering constraints.

These declarations order **auto-configurations**; they are not a general mechanism to control the order of every `@Configuration` or every bean in the program. When multiple before/after rules exist, Spring Boot computes a compatible order; avoid constraint cycles.

### 4.2. What role does `@AutoConfigureOrder` play?

`@AutoConfigureOrder` is an ordering variant dedicated to auto-configurations. It can be used when you want relative priority among configurations that have **no direct dependency relationship**. Fundamentally, smaller order values have earlier application priority. It **does not** replace an explicit `after = ...` constraint when a condition genuinely needs another configuration's metadata.

```java
@AutoConfiguration
@AutoConfigureOrder(100)
class MetricsAutoConfiguration {
    // Declare bean definitions
}
```

Do not infer "every bean inside `MetricsAutoConfiguration` is created at position 100." This order applies to the **auto-configuration**, not when bean constructors run.

### 4.3. Why are `@ConditionalOnBean` and `@ConditionalOnMissingBean` sensitive to order?

Bean conditions are evaluated based on **the bean definitions already processed up to that moment**.

Suppose configuration X provides bean `Client` and configuration Y has:

```java
@Bean
@ConditionalOnBean(Client.class)
ClientMonitor monitor() {
    return new ClientMonitor();
}
```

If Y is evaluated before Spring knows the `Client` definition from X, the condition may **not match**. Adding `@AutoConfiguration(after = X.class)` to Y lets Spring evaluate it with X's definition already present. That is completely different from requiring "the `Client` instance has run its constructor."

With `@ConditionalOnMissingBean(Client.class)`, order is even more critical: if checked too early, Spring may create a default bean even though another auto-configuration intends to declare `Client` later. For this reason, Spring Boot recommends using bean-presence/absence conditions in **auto-configurations** (which are applied after user-defined bean definitions) and establishing proper ordering among dependent auto-configurations.

When using type-based bean conditions, declare `@Bean` return types specifically enough for Spring to identify the type **before instantiating the bean**. Avoid hiding the target type behind `Object` or a factory method that obscures a useful return type.

## 5. Bean **initialization** order: dependencies, `@DependsOn`, `@Lazy`

### 5.1. Dependency injection creates a real relationship

If `ReportService`'s constructor/factory method needs `StorageClient`:

```java
@Bean
ReportService reportService(StorageClient storageClient) {
    return new ReportService(storageClient);
}
```

Spring must resolve `StorageClient` before finishing creation of `ReportService`. This is a **dependency relationship**, working regardless of the textual order in which the two `@Bean` methods are declared. `ReportService(StorageClient)` is an assumed constructor of an application class; the snippet must reside in a configuration class with appropriate imports.

### 5.2. `@DependsOn` sets explicit initialization order

Sometimes a bean needs another infrastructure bean initialized without injecting it directly—for example, driver/registry initialization infrastructure. In that case, you can use:

```java
@Bean
@DependsOn("auditInfrastructure")
AuditService auditService() {
    return new AuditService();
}
```

Meaning: before creating `auditService`, the container must initialize the bean named `auditInfrastructure`. If the specified dependency name does not exist, initialization may fail. For singletons, this relationship also affects destruction order in reverse, ensuring dependents are destroyed before their dependencies.

`@DependsOn` **does not mean** "process the configuration containing `auditInfrastructure` before evaluating bean conditions." If `@ConditionalOnBean` already evaluated negatively because the definition did not exist yet, adding `@DependsOn` to a downstream bean **cannot fix** the earlier condition.

### 5.3. `@Lazy` clearly separates definition from instance

```java
@Bean
@Lazy
LargeCache largeCache() {
    return new LargeCache();
}
```

Spring already has the `largeCache` definition, yet this singleton does not have to be created immediately during context refresh. Only when code calls `getBean(LargeCache.class)` or an eager singleton actually needs it is the instance created.

This is a very clear way to see that **bean registration does not mean bean initialization**. Yet `@Lazy` does not cause `@ConditionalOnBean(LargeCache.class)` to reject it either: if the bean type is registered and identifiable, the condition can still match even though no instance exists yet.

### 5.4. `@Order` is not a pre-initialization command

`@Order`/`Ordered` generally serves to sort components that Spring **orders for consumption**, such as a list of beans injected into `List<Strategy>` or extension points supporting ordering. It **is not a guarantee** that singleton #1 initializes before singleton #2.

Therefore:

- To have **definitions/configurations** ready when conditions are evaluated: choose `@AutoConfiguration(after/before)`.
- To have **bean A created before B**: express the dependency directly via constructor/factory parameters; use `@DependsOn` if there is no natural injection reference.
- To **defer** an instance: consider `@Lazy`, remembering that an eager dependency can still trigger it.
- To **order strategy invocation**: use `@Order` or the ordering protocol of the relevant extension point.

## 6. Java 17+ and Spring Boot 3.3 practice: two distinguishing tests

The following example uses `ApplicationContextRunner` to create isolated contexts, with two complementary tests:

1. **Auto-configuration ordering:** the provider's bean definition is present so `@ConditionalOnBean` matches, even though the `@Lazy` provider **has not been initialized yet**.
2. **Instance creation ordering:** `@DependsOn` forces a `@Lazy` infrastructure bean to initialize **before** an eager service.

Create `src/test/java/example/order/ConfigurationOrderTests.java` in a Java 17+ project with Spring Boot 3.3.x, `spring-boot-starter-test`, JUnit Jupiter, and AssertJ:

```java
package example.order;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.DependsOn;
import org.springframework.context.annotation.Lazy;

import static org.assertj.core.api.Assertions.assertThat;

class ConfigurationOrderTests {

    static final class SharedClient {}
    static final class FeatureMarker {}

    @AutoConfiguration
    static class ProviderAutoConfiguration {
        @Bean
        @Lazy
        SharedClient sharedClient() {
            return new SharedClient();
        }
    }

    @AutoConfiguration(after = ProviderAutoConfiguration.class)
    static class FeatureAutoConfiguration {
        @Bean
        @ConditionalOnBean(SharedClient.class)
        FeatureMarker featureMarker() {
            return new FeatureMarker();
        }
    }

    @Test
    void beanConditionSeesDefinitionBeforeInstanceExists() {
        new ApplicationContextRunner()
                // Intentionally list consumer before provider:
                .withConfiguration(AutoConfigurations.of(
                        FeatureAutoConfiguration.class,
                        ProviderAutoConfiguration.class
                ))
                .run(context -> {
                    assertThat(context).hasSingleBean(FeatureMarker.class);

                    // Definition of the lazy bean already exists.
                    assertThat(context.containsBeanDefinition("sharedClient"))
                            .isTrue();

                    // Yet the instance has not been created.
                    assertThat(context.getBeanFactory()
                            .containsSingleton("sharedClient")).isFalse();

                    // Only when retrieving the bean is the instance created.
                    context.getBean(SharedClient.class);
                    assertThat(context.getBeanFactory()
                            .containsSingleton("sharedClient")).isTrue();
                });
    }

    static final class Trace {
        final List<String> events = new ArrayList<>();
    }

    static final class Infrastructure {}
    static final class BusinessService {}

    @Configuration(proxyBeanMethods = false)
    static class InitializationConfiguration {
        @Bean
        Trace trace() {
            return new Trace();
        }

        @Bean
        @DependsOn("infrastructure")
        BusinessService businessService(Trace trace) {
            trace.events.add("businessService");
            return new BusinessService();
        }

        @Bean
        @Lazy
        Infrastructure infrastructure(Trace trace) {
            trace.events.add("infrastructure");
            return new Infrastructure();
        }
    }

    @Test
    void dependsOnInitializesLazyDependencyBeforeService() {
        new ApplicationContextRunner()
                .withUserConfiguration(InitializationConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(BusinessService.class);
                    assertThat(context).hasSingleBean(Infrastructure.class);
                    assertThat(context.getBean(Trace.class).events)
                            .containsExactly(
                                    "infrastructure",
                                    "businessService"
                            );
                });
    }
}
```

**Explanation of test 1:** `AutoConfigurations.of(...)` is the test mechanism for feeding auto-configurations into the runner. Even though `FeatureAutoConfiguration` is passed first, `after = ProviderAutoConfiguration.class` instructs Boot to reorder them so the condition can see the `SharedClient` definition. The `sharedClient` bean remains `@Lazy`, so `containsSingleton("sharedClient")` is initially `false`. Only when `context.getBean(SharedClient.class)` is called does it become `true`. This is direct proof that **definition-based conditions do not require a bean instance to exist**.

**Explanation of test 2:** `BusinessService` is an eager singleton, while `Infrastructure` is marked `@Lazy`. Because `businessService` has `@DependsOn("infrastructure")`, the container must create the infrastructure bean before creating the service. `Trace.events` records `infrastructure` followed by `businessService`. Removing `@DependsOn` would mean the lazy infrastructure bean is not necessarily created alongside the service; hence this meaningfully tests lifecycle constraints rather than relying on method declaration order.

**Run command** in a project directory with a Gradle wrapper and `test` using JUnit Platform:

```bash
./gradlew test --tests example.order.ConfigurationOrderTests
```

If using Maven with JUnit 5-capable Surefire:

```bash
./mvnw -Dtest=ConfigurationOrderTests test
```

**Expected result:** **both tests PASS**. No fixed stdout string is quoted because Gradle/Maven output depends on versions and logging setup. The test uses nested classes to keep the example self-contained; in production libraries, auto-configurations are typically top-level classes declared in `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`. Using `ApplicationContextRunner` avoids needing an imports file for this test example itself.

## 7. Examples of picking the wrong mechanism and how to fix them

### Scenario A: `@ConditionalOnBean` reports missing even though the bean will be declared

**Symptom:** `MetricsAutoConfiguration` with `@ConditionalOnBean(StorageClient.class)` fails to register metrics, yet the container later contains a `StorageClient` bean.

**Possible cause:** the metrics auto-configuration was evaluated when the other configuration's `StorageClient` definition **had not been processed yet**. When Spring evaluates a condition, it cannot look into the future.

**Fix:** identify which configuration actually declares `StorageClient`; add the constraint:

```java
@AutoConfiguration(after = StorageAutoConfiguration.class)
class MetricsAutoConfiguration {
    // @Bean @ConditionalOnBean(StorageClient.class) ...
}
```

This snippet is not standalone; place the appropriate types/imports in a real project. Add an `ApplicationContextRunner` test with both auto-configurations to verify the condition matches in the expected order. Do not try to fix this with `@DependsOn("storageClient")`, because `@DependsOn` only affects **instance creation after bean definitions are already accepted**.

### Scenario B: A bean needs ready infrastructure, yet only `@AutoConfiguration(after=...)` was added

**Symptom:** a `ReportService` bean requires an initialized registry; the configuration registering the registry is processed first, yet constructor/`@PostConstruct` order still does not meet expectations.

**Cause:** definition order does not enforce instance creation order.

**Fix:** ideally make the registry a real dependency:

```java
@Bean
ReportService reportService(Registry registry) {
    return new ReportService(registry);
}
```

If only lifecycle order is needed without injection, `@DependsOn("registry")` can be used. If the goal is to wait until **the entire application is ready** before executing business tasks, look at `ApplicationRunner`/`CommandLineRunner` or appropriate events instead of putting side effects in constructors. The snippets assume types are defined in the application.

### Scenario C: A `@Lazy` bean passes a condition without being initialized

**Symptom:** `@ConditionalOnBean(ExpensiveClient.class)` matches while no `ExpensiveClient` constructor log appears yet.

**This is usually the right behavior:** the condition inspects metadata of registered beans. A lazy bean has a definition without needing an instance yet. If an eager singleton injects it, it may then be created at startup. Do not "fix" this by forcing eager initialization merely for a condition to see the bean.

## 8. Diagnosing and testing at the right layer

| Issue under investigation | Evidence to inspect | Helpful tools |
| --- | --- | --- |
| Why wasn't an auto-configuration selected? | `ConditionEvaluationReport` outcome, class conditions, property/bean conditions | Run with `--debug`; test with `ApplicationContextRunner` |
| Has the bean been **registered**? | Bean definition by name/type | `containsBeanDefinition(...)`, `getBeanDefinitionNames()`, `getBeanNamesForType(...)` |
| Has the singleton bean been **initialized**? | Instance in singleton cache | `getBeanFactory().containsSingleton(...)` |
| Why did this bean initialize before that bean? | Dependency graph, `@DependsOn`, `@Lazy`, lifecycle | Trace in constructor/factory method/`@PostConstruct` |
| Why did a service run too early or too late? | Context ready timing, runners, lifecycle | `ApplicationRunner`, application events, timestamped logs |

Systematic debugging approach:

1. **Identify what needs ordering:** **bean detection/registration** or **instance initialization**. Many bugs stem from picking the wrong kind of ordering.
2. **Check the bean-declaring configuration and return type:** a `@Bean` returning an overly generic type may prevent type-specific conditions from recognizing the bean in metadata.
3. **Check `after`/`before` between auto-configurations:** add only necessary relationships, avoiding reliance on class names or file positions as an ordering contract.
4. **Check bean-creation dependencies:** constructor parameters, `@DependsOn`, `@Lazy`, and scope; check for circular dependencies or beans pulled into eager creation by another dependency.
5. **Write tests at the right moment:** in a context where `getBean(...)` has not been proactively called yet, check bean definitions and `containsSingleton(...)` separately. Calling `getBean(...)` too early in a test alters the "already initialized or not" result itself.
6. **Inspect the condition report:** `ConditionEvaluationReport` shows why a configuration was included or skipped; it does not prove when constructors ran. Trace lifecycle if instance creation order is suspect.

A common Spring Boot command to enable the condition report:

```bash
java -jar app.jar --debug
```

This command applies once the application is built into an executable JAR named `app.jar` and launched with an appropriate Java runtime. The report can be very long; focus on the auto-configurations under investigation. Do not infer bean initialization order solely from the line order printed in the condition report.

## 9. Common misconceptions

- **"`after = X` means X's beans run their constructors first."** False. It affects **auto-configuration/definition order**.
- **"`@DependsOn` makes `@ConditionalOnBean` see the bean."** False. `@DependsOn` only affects initializing already-registered definitions; it does not reverse an earlier condition decision.
- **"Declaring `@Bean` at the top of the file ensures the instance is created first."** There is no general contract guaranteeing this. Express dependencies or lifecycle explicitly.
- **"Having a bean definition means a bean instance already exists."** False, especially with `@Lazy`, prototype, or other scopes.
- **"`@Order(1)` forces a bean to be created before `@Order(2)`."** No. `@Order` is a consumption-sorting mechanism in contexts that support it, not a startup instance constraint.
- **"If a bean is created early, conditions will know about it."** Spring Boot bean conditions generally check processed definitions; instantiating a bean early does not fix definition registration order.
- **"`@Lazy` guarantees no creation at startup."** Not if an eager singleton or `@DependsOn` requires the lazy bean.
- **"`@AutoConfigureOrder` can replace dependencies."** It only orders auto-configurations; it does not describe needing a ready instance.
- **"I need to connect to the network in the constructor to ensure readiness."** Constructors run during bean creation; work requiring the application to be ready should use appropriate lifecycle hooks and avoid premature side effects.

## 10. Self-check questions

1. `ConsumerAutoConfiguration` has `@ConditionalOnBean(StorageClient.class)`. It needs to see the definition provided by `StorageAutoConfiguration`. Which annotation should be used? **`@AutoConfiguration(after = StorageAutoConfiguration.class)`** (or `@AutoConfigureAfter`). This is a **configuration processing** order relationship.
2. `StorageClient` has `@Lazy` and its definition is already registered. Can `@ConditionalOnBean(StorageClient.class)` match? **Yes**, if metadata is sufficient to identify it. No initialized instance is needed.
3. `AuditService` must be created after a bean named `registry` without needing to inject `registry`. What should be used? **`@DependsOn("registry")`** on the `AuditService` definition, with a valid bean name.
4. Can you use `@Order(1)` to force `StorageClient`'s constructor to run before `ReportService`'s constructor? **No.** Express a dependency relationship or `@DependsOn`.
5. `StorageClient` needs to be passed into `ReportService`. Is `@DependsOn` also needed? **Normally no**; the constructor/factory-method dependency already enforces resolving the `StorageClient` instance.
6. Does `@AutoConfiguration(after = X.class)` automatically guarantee `X` is activated, or that X's bean definitely exists? **No.** X can still be excluded by other conditions; `after` only determines relative order among evaluated configurations.
7. A test needs to prove a bean has not been initialized yet. Should it call `getBean()` before checking `containsSingleton()`? **No**, because calling `getBean()` itself can trigger bean creation.

## 11. References

- [Spring Boot 3.3 — AutoConfiguration API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html): `before`, `after`, `beforeName`, `afterName` attributes.
- [Spring Boot 3.3 — AutoConfigureBefore API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureBefore.html): official explanation of the difference between bean definition order and bean initialization order.
- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): auto-config ordering and how bean conditions depend on already-processed definitions.
- [Spring Framework — Lazy-initialized Beans](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-lazy-init.html): eager/lazy singletons and cases where lazy beans are still created due to dependencies.
- [Spring Framework — Using depends-on](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-dependson.html): singleton creation and destruction order along dependencies.
