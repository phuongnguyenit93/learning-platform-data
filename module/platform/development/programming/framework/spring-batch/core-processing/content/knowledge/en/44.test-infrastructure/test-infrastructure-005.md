# Spring TestContext in Spring Batch Testing

The **Spring TestContext Framework** is Spring Framework's testing infrastructure that enables tests to use Spring-managed components: creating an `ApplicationContext`, injecting dependencies, applying test profiles and properties, managing test transactions, preparing data, executing `TestExecutionListener`s, and reusing contexts across tests. In **Spring Batch Core Processing**, TestContext is especially important when testing readers, processors, writers, `@StepScope`/`@JobScope` beans, or running jobs with a real `JobRepository`, `JobLauncher`, and transaction manager.

JUnit discovers and runs tests; Spring TestContext supplies the **Spring environment** those tests require. Both parts integrate via `SpringExtension` in JUnit Jupiter (JUnit 5).

## 1. What Problem Does TestContext Solve?

Consider an `ItemProcessor` that depends on a data-lookup service and configuration:

```java
@Component
public class OrderProcessor implements ItemProcessor<Order, ProcessedOrder> {
    private final PricingService pricingService;

    public OrderProcessor(PricingService pricingService) {
        this.pricingService = pricingService;
    }

    @Override
    public ProcessedOrder process(Order order) {
        return pricingService.calculate(order);
    }
}
```

A unit test can instantiate `OrderProcessor` directly with a fake `PricingService`; that kind of test **does not need** Spring TestContext. However, if the goal is to verify that Spring creates the bean properly, test configuration works, scoped bean proxies resolve `JobParameters` accurately, or the job runs against a real repository, the test needs an `ApplicationContext`. Spring TestContext provides common infrastructure for those scenarios.

| Testing Need | Appropriate Approach | Role of TestContext |
| --- | --- | --- |
| Test pure processor logic | JUnit + mocks/stubs, direct object instantiation | Not required |
| Test wiring, dependency injection, properties, profiles | `@SpringJUnitConfig` with a small context | Creates context, injects beans, applies configuration |
| Test `@StepScope`/`@JobScope` beans | Spring TestContext + Spring Batch test scope utilities/listeners | Injects scoped proxies and opens scopes with `StepExecution`/`JobExecution` |
| Test job/step integration | `@SpringBatchTest` combined with appropriate Spring configuration | Manages context and provides Batch test utilities |
| Test database data handling | Spring TestContext + `@Sql`, `@Transactional`, test database | Seeds data and manages test transactions |

## 2. Core Components

```text
                  JUnit Jupiter
                       |
                       v
                 SpringExtension
                       |
                       v
               TestContextManager
                       |
             +---------+----------+
             |                    |
             v                    v
      TestContext              TestExecutionListener
             |                    |
             v                    +-- DependencyInjection...
      ApplicationContext          +-- Transactional...
             |                    +-- SqlScripts...
             |                    +-- Batch scope listeners
             v
      BeanFactory / Beans
             |
             +-- ItemReader / ItemProcessor / ItemWriter
             +-- Job / Step / JobRepository / JobLauncher
             +-- @JobScope / @StepScope proxies
```

**Roles to distinguish:**

- **`SpringExtension`** integrates Spring TestContext with the JUnit Jupiter lifecycle, such as preparing test instances, handling dependency injection, and invoking callbacks before/after tests.
- **`TestContextManager`** coordinates test execution steps; those steps are delegated to registered `TestExecutionListener`s.
- **`TestContext`** holds information about the test class, method under test, configuration, and active `ApplicationContext`.
- **`ApplicationContext`** holds Spring beans and Batch infrastructure. Beans injected into the test normally come from this context.
- **`TestExecutionListener`** performs test-lifecycle operations: injection, transaction management, running SQL scripts, opening scopes in Spring Batch integration, and more.

Spring TestContext's `TestExecutionListener` **differs** from Spring Batch's `JobExecutionListener`/`StepExecutionListener`. The former follows the **JUnit test** lifecycle; the latter follows the **job or step** lifecycle during batch execution. They serve different purposes and fire at different times.

## 3. Dependency Configuration

Example with Gradle and **Spring Batch 5.x / Spring Framework 6.x / JUnit Jupiter**. Spring Boot projects may already receive these dependencies through starters and dependency management, so declare only what is missing:

```groovy
dependencies {
    implementation 'org.springframework.batch:spring-batch-core'

    testImplementation 'org.springframework:spring-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testImplementation 'org.junit.jupiter:junit-jupiter'
}

test {
    useJUnitPlatform()
}
```

When using Spring Boot, `spring-boot-starter-test` typically provides Spring Test and JUnit Jupiter. `spring-batch-test` provides Batch-specific utilities such as `JobLauncherTestUtils`, `JobRepositoryTestUtils`, `StepScopeTestUtils`, `JobScopeTestUtils`, and the `@SpringBatchTest` annotation.

Do not arbitrarily mix major versions of Spring Framework, Spring Batch, and Spring Boot. The examples use **Spring Batch 5.x** imports; when a project uses Spring Batch 6.x, check the actual APIs and packages for that version.

## 4. Testing a Minimal Spring Context with `@SpringJUnitConfig`

`@SpringJUnitConfig` is a convenience annotation combining `@ExtendWith(SpringExtension.class)` and `@ContextConfiguration`. It fits tests that need a few Spring beans without starting the whole application.

The complete example below tests injecting an order-tagging service configured by a test property. The code can live in `src/test/java/.../OrderTaggerContextTest.java`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringJUnitConfig(OrderTaggerContextTest.Config.class)
@TestPropertySource(properties = "batch.region=APAC")
class OrderTaggerContextTest {

    @Autowired
    private OrderTagger tagger;

    @Test
    void injectsBeanAndResolvesTestProperty() {
        assertEquals("APAC:42", tagger.tag("42"));
    }

    @Configuration
    static class Config {

        @Bean
        OrderTagger orderTagger(@Value("${batch.region}") String region) {
            return new OrderTagger(region);
        }
    }

    static class OrderTagger {
        private final String region;

        OrderTagger(String region) {
            this.region = region;
        }

        String tag(String orderId) {
            return region + ":" + orderId;
        }
    }
}
```

In this example:

1. JUnit Jupiter runs the test; `SpringExtension` loads the context from `Config`.
2. Spring creates the `OrderTagger` bean via the `@Bean` method.
3. `@TestPropertySource` supplies `batch.region=APAC` to the test context.
4. `DependencyInjectionTestExecutionListener` injects the bean into the `@Autowired` field.
5. The assertion verifies that Spring configuration and bean behavior work together properly.

This is a **very small integration test at the Spring context level**. It is faster and easier to isolate than booting the entire Batch application while still verifying real dependency injection.

### When to Use `@SpringBootTest`?

`@SpringBootTest` boots a Spring Boot application context matching the application's configuration. It is appropriate when you need auto-configuration, repositories, transaction managers, datasources, or real batch job definitions. You do not need `@SpringBootTest` to test a processor with just a couple of dependencies.

In Spring Boot applications, `@SpringBootTest` already integrates Spring TestContext and JUnit Jupiter; you normally do not need to add `@ExtendWith(SpringExtension.class)`.

## 5. `ApplicationContext` Caching and Test Lifecycle

Creating a Spring context can be expensive, especially with a `DataSource`, schema migrations, many beans, or repositories. Spring TestContext stores `ApplicationContext` instances in a **shared cache during the test run** and reuses them when tests have compatible configurations.

```text
Test A -- config X --+
                     +--> ApplicationContext X in cache
Test B -- config X --+

Test C -- config Y -----> ApplicationContext Y in cache
```

Attributes such as configuration classes, active profiles, test property sources, context customizers, and context hierarchies affect the cache key. Two test classes that look similar but use different dynamic configuration will still create separate contexts. The context cache lives within the JVM process running the tests; splitting every test class into its own JVM prevents sharing that cache across processes.

`@DirtiesContext` signals to the TestContext Framework that the context has been dirtied, should be evicted from the cache, and recreated when needed. For example, a test mutating configuration or irreversible singleton state might use:

```java
import org.springframework.test.annotation.DirtiesContext;

@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class MutatingContextIntegrationTest {
    // Tests intentionally mutate context state that cannot be cleanly reset.
}
```

Do not add `@DirtiesContext` to every test by default. It defeats caching and slows down the suite; database state, message queues, or `JobRepository` data are not automatically wiped just because the context closes.

A useful design rule: **reuse the Spring context when configurations match, but isolate the data and state each test modifies**.

## 6. Combining Spring TestContext with `@SpringBatchTest`

`@SpringBatchTest` is an annotation from `spring-batch-test` that enables Spring Batch-specific test support. In Spring Batch 5.x, it registers test utilities such as `JobLauncherTestUtils` and `JobRepositoryTestUtils`, and configures listeners supporting test scopes.

`@SpringBatchTest` **does not replace** specifying the Spring application context. You normally pair it with `@SpringBootTest` or `@SpringJUnitConfig`/`@ContextConfiguration` so the framework knows which beans to load.

Example testing an application-configured job:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBatchTest
@SpringBootTest(classes = BatchApplication.class)
@ActiveProfiles("test")
@TestPropertySource(properties = "spring.batch.job.enabled=false")
class ImportOrdersJobIntegrationTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    private Job importOrdersJob;

    @BeforeEach
    void selectJobUnderTest() {
        jobLauncherTestUtils.setJob(importOrdersJob);
    }

    @Test
    void runsJobWithControlledParameters() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", "2025-01-15")
                .addString("testScenario", "runsJobWithControlledParameters")
                .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
    }
}
```

**Conditions for the example to work:** the project has `BatchApplication` (a `@SpringBootApplication` class), a `Job` bean named `importOrdersJob`, and validly configured `JobRepository`, transaction manager, and test database. `@SpringBootTest` loads that infrastructure, while `@SpringBatchTest` adds testing tools. If the application has multiple `Job` beans, the `@Autowired` field must have a matching bean name or an explicit `@Qualifier`.

`spring.batch.job.enabled=false` prevents Spring Boot from auto-launching jobs on context startup. In the test, we explicitly call `launchJob(parameters)` with deterministic inputs. The `testScenario` parameter distinguishes scenarios against **a shared repository**, though it does not replace isolating repositories across test runs.

If a `JobInstance` with the same job name and identifying parameters is already `COMPLETED` in `JobRepository`, rerunning it can raise `JobInstanceAlreadyCompleteException`. That is a core batch rule. Integration tests need a clear data strategy: a dedicated test repository, controlled schema cleanup, or a fresh test database. For restart tests, retain metadata from the failed run and **do not change** identifying parameters.

## 7. TestContext and `@StepScope`/`@JobScope` Beans

A `@StepScope` or `@JobScope` bean is typically injected by Spring as a proxy. The proxy requires an active `StepExecution` or `JobExecution` to resolve its target and expressions like:

```java
@Value("#{jobParameters['businessDate']}")
@Value("#{jobExecutionContext['source']}")
@Value("#{stepExecutionContext['readCount']}")
```

When running a real job, Spring Batch opens the corresponding scopes during execution. When testing just one bean, Spring TestContext can construct the bean/proxy, yet the scope may not be active yet. That is where `StepScopeTestUtils`, `JobScopeTestUtils`, or the listeners provided by `@SpringBatchTest` come in.

### Example: Spring TestContext + `StepScopeTestUtils`

The following example uses a small context and **does not launch a full job**. The scope is opened only for the needed block of code:

```java
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.scope.StepScope;
import org.springframework.batch.test.MetaDataInstanceFactory;
import org.springframework.batch.test.StepScopeTestUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringJUnitConfig(StepScopedFormatterTest.Config.class)
class StepScopedFormatterTest {

    @Autowired
    private Formatter formatter;

    @Test
    void resolvesParameterInsideStepScope() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("batchTag", "demo")
                .toJobParameters();

        StepExecution stepExecution =
                MetaDataInstanceFactory.createStepExecution(parameters);

        String result = StepScopeTestUtils.doInStepScope(
                stepExecution,
                () -> formatter.format("42"));

        assertEquals("demo-42", result);
    }

    @Configuration
    static class Config {

        @Bean
        static StepScope stepScope() {
            return new StepScope();
        }

        @Bean
        @StepScope
        Formatter formatter(@Value("#{jobParameters['batchTag']}") String tag) {
            return new Formatter(tag);
        }
    }

    static class Formatter {
        private final String tag;

        Formatter(String tag) {
            this.tag = tag;
        }

        String format(String input) {
            return tag + "-" + input;
        }
    }
}
```

In this minimal test context, `@Bean static StepScope stepScope()` registers the scope so Spring knows how to handle `@StepScope`. In a fully configured Spring Batch application, do not register duplicate scopes when the infrastructure already provides them. `MetaDataInstanceFactory` creates test metadata, and `StepScopeTestUtils` binds `StepExecution` for the lambda. Calling `formatter.format(...)` outside this scope will lack a valid step context.

For `@JobScope` beans, the idea is similar, using `JobExecution` and `JobScopeTestUtils.doInJobScope(jobExecution, callable)`. Note that `jobExecutionContext` is **job-level** context while `stepExecutionContext` is **step-level** context; choose the right scope and metadata for the data your bean requires.

### Spring Batch Listeners in TestContext

Two key listeners are:

- **`StepScopeTestExecutionListener`**: creates/activates a step context for the test method and can detect a test-supplied `StepExecution`.
- **`JobScopeTestExecutionListener`**: activates a job context for the test method and can use a test-supplied `JobExecution`.

When using `@SpringBatchTest` in supported versions, the framework registers these listeners so tests can access scoped beans conveniently. When using `StepScopeTestUtils`/`JobScopeTestUtils`, the test explicitly controls which code block needs the scope; this is often clearer for very small unit/integration tests.

## 8. Common Spring TestContext Annotations

| Annotation | Effect | Notes for Batch Testing |
| --- | --- | --- |
| `@SpringJUnitConfig` | Combines JUnit 5 extension and Spring context configuration | Great for testing beans, services, processors, or small configs |
| `@ContextConfiguration` | Selects classes/XML/initializers to load context | Can be paired with `@ExtendWith(SpringExtension.class)` |
| `@SpringBootTest` | Loads the Spring Boot context | Suitable when jobs, repositories, databases, or Boot auto-config are needed |
| `@SpringBatchTest` | Adds Batch test utilities and scope listeners | Requires a context with corresponding infrastructure |
| `@ActiveProfiles("test")` | Activates the `test` Spring profile | Selects test datasources, service stubs, and batch settings |
| `@TestPropertySource` | Adds/overrides properties at test level | Used for fixture paths, batch flags, and repeatable configs |
| `@DynamicPropertySource` | Supplies dynamic properties via a static method | Useful for database containers with runtime-assigned URLs/ports |
| `@Sql` | Runs SQL scripts before/after a test method or class | Seeds/cleans business data in the test database |
| `@Transactional` | Opens a test-managed transaction and usually rolls back after test | Does not automatically roll back transactions managed by job/step on other threads |
| `@DirtiesContext` | Marks the context for eviction from cache | Use only when a test irreversibly mutates context state |
| `@TestExecutionListeners` | Adds to or replaces the listener list | Be careful to preserve required default listeners |

If you need to add a custom listener, use merge mode to preserve listeners already registered by Spring and Batch infrastructure:

```java
import org.springframework.test.context.TestExecutionListeners;

@TestExecutionListeners(
        listeners = MyTestExecutionListener.class,
        mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS)
class BatchWithCustomTestListener {
    // ...
}
```

This example illustrates the declaration syntax; `MyTestExecutionListener` must be implemented if used. Specifying a custom listener list in a way that replaces defaults can accidentally disable dependency injection, transaction support, SQL scripts, or scope listeners that tests depend on.

## 9. Managing Test Data and Transactions

Spring TestContext supports seeding data with `@Sql`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.jdbc.Sql;

@Sql(
        scripts = "/sql/seed-test-orders.sql",
        executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD)
class OrderRepositoryIntegrationTest {

    @Test
    void readsPreparedOrders() {
        // Call Spring-injected repository/service.
    }
}
```

`seed-test-orders.sql` is placed under `src/test/resources/sql/`. Tests using `@Sql` must have Spring TestContext and properly configured datasource/transaction infrastructure.

`@Transactional` on a Spring test normally creates a **test-managed transaction** that rolls back after the test. However, batch steps can open their own transactions via `PlatformTransactionManager`, and jobs can execute on separate threads. Therefore, **never assume** `@Transactional` on a JUnit method will roll back all data written by the job.

Distinguish three state regions:

1. **Business data** in tables like `orders`, `invoice`, `payment`.
2. **Batch metadata** in `JobRepository` tables (job instances, executions, step executions, execution contexts).
3. **Bean state / context state** residing in memory inside the Spring application context.

Test rollbacks, database cleanup, and `@DirtiesContext` act on these regions in different ways. For job-running integration tests, use an isolated test database and explicit setup/cleanup routines. `JobRepositoryTestUtils.removeJobExecutions()` can help clean Batch metadata in a test repository, but it does not delete business data and must not be used on a repository shared with other systems.

Notes for parallel tests: two tests running batch jobs against one repository can contend over `JobInstance`s, database locks, or fixture data. Isolate schemas/repositories per test suite or coordinate integration tests that share resources; do not rely on test execution order for correctness.

## 10. Choosing the Right Context Loading Level

Context startup cost significantly impacts CI duration, especially when a Batch project has many jobs or datasources. Tests can be organized in tiers:

| Tier | What It Verifies | Setup |
| --- | --- | --- |
| Unit test | Transformation/validation logic of `ItemProcessor` | JUnit + constructor injection + stubs/mocks, no Spring loaded |
| Small context test | Bean definitions, wiring, properties, profiles, scopes | `@SpringJUnitConfig`, declaring only required beans |
| Batch component integration | Reader/writer database/file access, scopes, transactions | Spring TestContext + datasource/scope configuration and fixtures |
| Batch job integration | Step/job flows, status, restart, metadata | `@SpringBatchTest` + application context + test `JobRepository` |

Use the lowest tier capable of verifying a test's requirements. A processor test checking a simple transformation should not waste time booting the entire application context; a restart test that needs persisted metadata and job execution cannot get by with only a mock `JobRepository`.

**Reuse contexts effectively:** avoid creating unnecessary configuration variations; keep profiles and properties consistent across classes with identical needs. **Isolate data effectively:** keep fixtures deterministic, use dedicated integration-test databases, choose clear identifying `JobParameters`, clean state within the proper scope, and avoid mutating shared singleton beans across tests.

## 11. Diagnosing Common Failures

| Symptom | Likely Causes | Troubleshooting |
| --- | --- | --- |
| `@Autowired` field is `null` | `SpringExtension`/TestContext not used; object instantiated manually with `new` | Add `@SpringJUnitConfig` or `@SpringBootTest`; check bean belongs to context |
| `Failed to load ApplicationContext` | Missing bean, property, datasource, schema, or infrastructure config | Inspect root cause in exception; shrink context or add test configuration |
| `@StepScope` proxy exists but invoking bean throws `ScopeNotActiveException` | Step context not activated | Use scope test utility/listener and pass proper `StepExecution` |
| `No Scope registered for scope name 'job'` | Test context lacks `JobScope` registration | Enable proper Batch config or declare scope in minimal context |
| Job auto-runs before test calls `launchJob` | Spring Boot auto-runs Batch jobs on startup | Set `spring.batch.job.enabled=false` in test config |
| `JobInstanceAlreadyCompleteException` | Repository already has metadata for a completed job with the same identifying parameters | Isolate/clean metadata; distinguish new-instance vs. restart scenarios |
| Data remains in DB despite `@Transactional` on test | Job/step uses a transaction separate from test-managed transaction | Use isolated test DB with explicit setup/cleanup; do not rely on test rollback |
| Test suite slow due to repeated context reloads | Frequent `@DirtiesContext` or fragmented test configurations | Reduce context variations, leverage caching, separate non-Spring tests |
| Adding `@TestExecutionListeners` breaks injection or transactions | Default listener list was replaced | Use `MERGE_WITH_DEFAULTS` when adding listeners |
| Test passes alone but fails when running full suite | Shared database/context state, order dependency | Isolate fixtures/repository, reset data cleanly; avoid shared mutable beans |

## 12. References

- [Spring Framework Reference — Testing, TestContext Framework](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework.html)
- [Spring Framework Reference — Context Configuration with TestContext](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management.html)
- [Spring Framework Reference — Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html)
- [Spring Framework Reference — TestExecutionListener](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tel-config.html)
- [Spring Framework Reference — SpringExtension and JUnit Jupiter](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/support-classes.html)
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html)
- [Spring Batch API — `@SpringBatchTest`](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/test/context/SpringBatchTest.html)
- [Spring Batch API — `StepScopeTestUtils`](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/test/StepScopeTestUtils.html)

Spring TestContext is the foundation connecting JUnit to Spring's bean system and configuration; `spring-batch-test` builds dedicated utilities for jobs, steps, and batch scopes on top of it. To write reliable Batch tests, define clearly what you are verifying, pick the matching context level, prepare reproducible data, and manage `JobRepository` state separately from business data. Done right, tests both reflect real Spring Batch behavior and stay fast and stable enough to run routinely in CI.
