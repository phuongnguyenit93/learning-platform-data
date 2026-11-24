# Context Caching in Spring Batch Test Infrastructure

A Spring Batch integration test typically has to initialize many components: `ApplicationContext`, `Job` and `Step` definitions, `ItemReader`, `ItemProcessor`, `ItemWriter`, `JobRepository`, a transaction manager, and connections to a test database. If every test method rebuilt this entire stack from scratch, the test suite could become noticeably slow even with only a handful of test rows.

**Context caching** in the **Spring TestContext Framework** solves that initialization cost by storing and reusing `ApplicationContext` instances created for identical test configurations. In Spring Batch, understanding this mechanism lets you write faster integration tests while avoiding a subtle class of failures: Test A passes alone, yet Test B fails when both run together due to leftover batch data or bean state.

A crucial distinction right up front:

> **The context cache reuses configuration and beans inside the `ApplicationContext`; it does not automatically clean business data, `JobExecution` history, or state produced by tests.**

This lesson explains how the cache key is computed, when a context is reused, how caching interacts with `@SpringBatchTest`, how to isolate batch data, when `@DirtiesContext` is warranted, and how to read logs to diagnose repeated context startups.

## 1. What Is Context Caching?

When a test uses Spring TestContext—for example via `@SpringBootTest`, `@ContextConfiguration`, or Spring Boot test slices—the framework must load an `ApplicationContext` to run the test. Loading may involve:

- Parsing configurations and instantiating Spring beans.
- Applying `@Profile`, properties, and test bean overrides.
- Initializing `DataSource`, transaction managers, and Spring Batch infrastructure.
- Building `Job`/`Step` definitions and initializing eligible singletons.
- Setting up other application layers per configuration: JPA, security, messaging, web layer, etc.

Once created, Spring TestContext keeps the context in a **static cache** tied to the JVM process running the tests. Subsequent test methods or classes with an equivalent configuration receive the already-initialized context instead of building a new one.

~~~mermaid
flowchart TD
    A["Test needs ApplicationContext"] --> B["Compute context cache key"]
    B --> C{"Cache has valid context\nfor that key?"}
    C -->|Yes| D["Reuse ApplicationContext"]
    C -->|No| E["Load new context"]
    E --> F["Store context in cache"]
    F --> G["Run test"]
    D --> G
    G --> H["Next test"]
    H --> B
~~~

For instance, an `ImportJobIntegrationTest` class with three test methods sharing `@SpringBootTest` usually loads one context for all three methods. If `ExportJobIntegrationTest` has **the same context configuration** in the same JVM, it can reuse that context too. You do not need to write a manual singleton cache.

**Context caching is not test result caching.** Every test still runs its assertions, data processing, and jobs as requested. The cache only avoids repeating Spring context startup when configuration is shareable.

## 2. Which Key Identifies a Cached Context?

Spring does not key solely by test class name. Spring TestContext constructs a **cache key** from `MergedContextConfiguration`, capturing configuration inputs that affect how the context loads.

| Key Component | Example | Why It Affects Caching |
|---|---|---|
| `locations` and `classes` | `@ContextConfiguration(classes = TestBatchConfig.class)` | Different configuration sources can define different beans. |
| `contextInitializerClasses` | Custom `ApplicationContextInitializer` | Initializers can customize the context. |
| `contextLoader` | Standard or custom loader | Different context loading strategies. |
| `activeProfiles` | `@ActiveProfiles("test")`, `@ActiveProfiles("integration")` | Profiles can activate different beans or settings. |
| `propertySourceDescriptors` | `@TestPropertySource(locations = "...")` | Different declared property sources. |
| `propertySourceProperties` | `@TestPropertySource(properties = "...")` | Different inline configuration values. |
| `contextCustomizers` | `@DynamicPropertySource`, mock/override bean declarations | Customizers can alter the context. |
| `parent` | `@ContextHierarchy` | Parent context is part of the configuration. |
| `resourceBasePath` | `@WebAppConfiguration` | Applies to web test environments. |

In Spring Boot, `@SpringBootTest(properties = "...")`, web environment modes, test slices, `@Import`, and mock/override bean declarations can all differentiate keys via configuration or context customizers. **Merely having two classes annotated with `@SpringBootTest` does not guarantee they hit the same cache entry.**

Example:

~~~java
@SpringBootTest(properties = "spring.batch.job.enabled=false")
@ActiveProfiles("test")
class ImportJobTest {
    // ...
}

@SpringBootTest(properties = "spring.batch.job.enabled=false")
@ActiveProfiles("test")
class ExportJobTest {
    // ...
}
~~~

These two classes **can** share a context if all other configuration elements also match and they run in the same JVM. Conversely:

~~~java
@SpringBootTest(properties = "app.batch.chunk-size=2")
class SmallChunkTest {
    // ...
}

@SpringBootTest(properties = "app.batch.chunk-size=50")
class LargeChunkTest {
    // ...
}
~~~

Different properties yield different context configurations, so they will not share a cache entry. Tests using Spring Boot's `@MockBean` (in supported versions), or `@MockitoBean` in newer Spring Framework ecosystems, also alter the cache key according to the overridden beans.

**Test method names, CSV input names, and existing database rows do not automatically create a new cache key.** That is the root cause of many order-dependent failures.

## 3. How Does Context Caching Interact with Spring Batch?

In Spring Batch, a reused context typically holds the system's configuration beans:

- `Job` and `Step` defining the processing pipeline.
- `JobLauncher` and `JobRepository` for orchestrating jobs and persisting metadata.
- `PlatformTransactionManager`, `DataSource`, or persistence components.
- Registered readers, processors, writers, and listeners.
- Test utility beans provided by `@SpringBatchTest`.

However, **reusing beans** and **reusing execution state** are completely different things:

| What Is Reused or Persists | How Context Caching Relates | How to Manage in Tests |
|---|---|---|
| `Job`/`Step` definitions and singleton beans | Usually reused along with the context. | Keep beans free of unintended mutable state. |
| `JobRepository` bean | Likely the exact same bean instance. | Manage the metadata records it persists. |
| Business tables updated by writers | Not cleared simply on cache hit/miss. | Reset tables or isolate data per test. |
| `BATCH_JOB_INSTANCE`, `BATCH_JOB_EXECUTION`, `BATCH_STEP_EXECUTION` and related tables | Stored in the repository; can persist across tests. | Clean metadata in the test DB or use a clear `JobParameters` strategy. |
| `ExecutionContext` of a job/step execution | Tied to execution and metadata; not TestContext cache. | Create fresh executions or intentionally test restart on the right execution. |
| `@StepScope` and `@JobScope` | Beans are resolved per execution/scope context. | Configure test scopes properly; do not share processing state casually. |
| H2 in-memory database | May persist across connections depending on DB lifecycle config. | Never assume "in-memory" means empty before every test. |
| External DB, Kafka, filesystem, HTTP mock server | Outside Spring's context cache lifecycle in general. | Clean or isolate per resource type. |

Concrete example: `JobRepository` is reused, and the database still contains a `COMPLETED` `JobInstance` for a given set of `JobParameters`. If another test runs the same job with the same identifying parameters, Spring Batch may throw `JobInstanceAlreadyCompleteException`. This does not mean the cache is broken: the batch infrastructure remembers the prior run in the repository, exactly as designed.

Another example: a singleton writer holds a `List` field to collect test records. If the list is not cleared before each test, the next test sees leftover entries. It is far better to use an intentionally reset collector or scope-isolated execution per run than to rely on Spring recreating the context.

## 4. Distinguishing Context Cache, Transactions, and Checkpoints

These three mechanisms operate at different scopes:

| Mechanism | What It Manages | When It Applies |
|---|---|---|
| **Spring TestContext cache** | Reusing `ApplicationContext` across tests with matching configurations. | Within the test runner's JVM process. |
| **Chunk transaction** | Committing or rolling back transactional changes during step read/process/write. | Within a single step execution. |
| **Spring Batch checkpoint / ExecutionContext** | Persisting progress and state needed for restart. | Per `JobExecution`/`StepExecution` and repository. |

**A context cache hit does not mean a job restart.** To test restart, you must force an execution to fail and then resume the exact same `JobInstance` per Spring Batch rules. **A context cache miss does not wipe job history either.** If the database still retains metadata tables, the new context reads that same history.

In particular, annotating a test method with `@Transactional` does not guarantee all job operations roll back when the test finishes. The job launcher, steps, chunks, and repository can manage transactions with separate boundaries; in some configurations, calling `JobLauncher` inside an existing transaction even triggers an error from `JobRepository`'s transaction check. For full-job integration tests, define transaction boundaries clearly and **clean data via test-appropriate mechanisms**, rather than expecting a test-level annotation to undo every side effect.

## 5. Using @SpringBatchTest with SpringBootTest

`@SpringBatchTest` provides Spring Batch testing support, including utilities such as `JobLauncherTestUtils` and `JobRepositoryTestUtils`, plus job/step scope test context support. It handles **controlling and testing batch execution**, while `ApplicationContext` storage and reuse are handled by the Spring TestContext Framework.

In a Spring Boot application, a common setup is:

~~~java
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
@ActiveProfiles("test")
class ImportOrdersJobIntegrationTest {
    // Test code
}
~~~

Explanation:

- `@SpringBootTest` builds the Boot application's integration context.
- `@SpringBatchTest` exposes batch job/step execution and scope utilities to the test.
- `@ActiveProfiles("test")` activates the profile containing test-specific database and batch settings.
- `spring.batch.job.enabled=false` disables **Spring Boot's** automatic `Job` launch on context startup so the test decides when to invoke the job. It does not disable manual job launching.

If the project uses Spring Batch configuration outside Spring Boot's auto-run mechanism, make sure you understand how jobs are triggered in your actual setup. Annotations alone do not guarantee the test database is isolated.

### Example: Running a Job and Cleaning Metadata Between Tests

The code below assumes the application defines an `importOrdersJob` bean, a `processed_order` business table, and a dedicated test database. The example checks output count; in a real application, you should assert individual record values as well:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.JobRepositoryTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
@ActiveProfiles("test")
class ImportOrdersJobIntegrationTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    private JobRepositoryTestUtils jobRepositoryTestUtils;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    @Qualifier("importOrdersJob")
    private Job importOrdersJob;

    @BeforeEach
    void prepare() {
        // Execute only on a database dedicated to testing.
        jobRepositoryTestUtils.removeJobExecutions();
        jdbcTemplate.update("DELETE FROM processed_order");
        jobLauncherTestUtils.setJob(importOrdersJob);
    }

    @Test
    void importsThreeOrders() throws Exception {
        JobExecution execution = jobLauncherTestUtils.launchJob(
            new JobParametersBuilder()
                .addString("scenario", "three-orders")
                .toJobParameters()
        );

        assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
        Integer count = jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM processed_order", Integer.class);
        assertThat(count).isEqualTo(3);
    }
}
~~~

Here, `@BeforeEach` runs before **every test method** even on a context cache hit. It cleans job history and business data in the dedicated database, while the job configuration and beans in the context are reused. Never call `removeJobExecutions()` against a repository shared with a real environment or with parallel tests running on the same database, because it can delete another execution's history.

This example is only valid if the test input is prepared to produce three orders and the writer inserts into `processed_order`. For real test data, keep deterministic CSV files under `src/test/resources` and explicitly point the reader to that resource path.

If the same context contains **multiple `Job` beans**, `JobLauncherTestUtils` must be configured with the target job; here, `setJob(importOrdersJob)` removes ambiguity.

## 6. Reusing Contexts Across Multiple Test Classes

Instead of letting each test class tweak minor properties, unify configuration across test groups:

~~~java
@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
@ActiveProfiles("test")
class ReaderIntegrationTest {
    // ...
}

@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
@ActiveProfiles("test")
class WriterIntegrationTest {
    // ...
}
~~~

If the effective configuration sources, customizers, and context loaders match, both classes can share a cache entry. In both classes, you still must prepare and clean test-specific data state.

Some test groups should use different contexts because they genuinely require different infrastructure:

- Processor unit tests needing only Java objects and simple mocks: **do not need** `@SpringBootTest`.
- Reader tests needing only a tokenizer/mapper: can instantiate the reader directly without booting the entire application.
- `Job` and `Step` integration tests: use the appropriate batch or Boot context.
- Tests running with a different profile, database engine, or bean override: accept a separate context when the configuration difference is meaningful.

The goal is **intentional reuse of matching configurations**, not forcing every test into one giant context. Small unit tests run much faster without initializing Spring.

## 7. When Is `@DirtiesContext` the Right Choice?

`@DirtiesContext` informs Spring TestContext that the active `ApplicationContext` has been modified or should no longer be reused. Depending on placement and mode, the framework evicts and closes the context so the next test loads a fresh one.

Example:

~~~java
import org.springframework.test.annotation.DirtiesContext;

@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
@SpringBatchTest
@SpringBootTest
class ChangesSingletonConfigurationTest {
    // Tests mutate singleton configuration state
    // to a degree that cannot be safely restored in cleanup.
}
~~~

Common modes:

| Annotation Usage | Meaning |
|---|---|
| `@DirtiesContext(methodMode = AFTER_METHOD)` on a method | Marks the context dirty after that method finishes. |
| `@DirtiesContext(methodMode = BEFORE_METHOD)` | Ensures a stale context is not reused for the current method. |
| `@DirtiesContext(classMode = AFTER_CLASS)` on a class | Marks the context dirty after the entire class finishes. |
| `@DirtiesContext(classMode = BEFORE_CLASS)` | Requests a fresh context before any test in the class runs. |
| `@DirtiesContext(classMode = AFTER_EACH_TEST_METHOD)` | Marks dirty after every method, triggering more frequent reloads. |

When a test mutates bean configuration, context environment, or a singleton without a clean way to reset it, marking the context dirty makes sense. However, `@DirtiesContext` is **not a tool for wiping all data outside the Spring context**:

- If a writer committed rows to test PostgreSQL, closing the context does not delete those rows.
- If a batch job published a Kafka message or wrote a file, closing the context does not undo that effect.
- If an in-memory database survives beyond connection/context lifetime due to custom settings, closing the context may not clear state as expected.

Therefore, when only `processed_order` rows or `BATCH_*` metadata remain, the fix is usually **resetting test data**, not sprinkling `@DirtiesContext` onto every test. Overusing it increases cache misses and runtime without necessarily fixing the source of state pollution.

## 8. Situations Where Contexts Are Not Reused

### 8.1. Differences in Properties or Profiles

~~~java
@SpringBootTest(properties = "app.import.strict=true")
class StrictImportTest { }

@SpringBootTest(properties = "app.import.strict=false")
class LenientImportTest { }
~~~

These are two contexts with distinct behaviors. If you want to test multiple logic variants without changing how beans are constructed, consider passing data or processing parameters directly; vary context properties only when context wiring itself is under test.

### 8.2. Different Mock Declarations Across Classes

One class overrides `PaymentClient`, while another overrides `NotificationClient`; two distinct sets of customizers produce two cache keys. Having different mocks create distinct contexts is normal.

If a group of tests all need the same set of fake dependencies, you can intentionally share a test configuration or mock configuration. Do not add unnecessary mocks merely trying to optimize caching.

### 8.3. `@DynamicPropertySource` and Dynamic Resources

`@DynamicPropertySource` is commonly used to inject Testcontainers ports, URLs, or credentials into the Spring Environment:

~~~java
@DynamicPropertySource
static void databaseProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
~~~

Note that the `@DynamicPropertySource` method contributes to the context customizer. If multiple classes **inherit the same method** while the underlying resource actually changes (for example, the previous class's container stopped and the next class started a new container/port), a cached context could hold a `DataSource` bound to the defunct resource. In that scenario, design the container lifecycle to match context sharing, or mark the context dirty when the dynamic endpoint actually changes.

A single stable container shared across an integration test group cuts startup time, provided tests isolate their data. Never let the context cache implicitly dictate the lifecycle of external resources outside the JVM.

### 8.4. Running Tests Across Multiple JVMs or Processes

The context cache is a **static cache within a single JVM**. It is not shared across:

- Two separate test processes.
- Independent worker JVMs forked by the build tool.
- Two separate test runs in an IDE or CI.

Thus, the same configuration may load a context once in JVM A and once in JVM B; that is not an abnormal cache miss. When configuring builds to fork tests across multiple JVMs, balance parallelism, memory, context startup cost, and database isolation.

### 8.5. Cache Too Small and Eviction Occurs

The Spring TestContext cache has a capacity limit; a common default is **32 contexts** with Least Recently Used (**LRU**) eviction when exceeded. If a suite generates too many distinct configurations, older contexts are closed and reloaded when needed again.

You can adjust the maximum via a JVM system property:

~~~text
-Dspring.test.context.cache.maxSize=64
~~~

Increasing cache size is not always better: keeping many live contexts simultaneously consumes heap, holds connection pools, and retains other resources. Before raising the limit, check why tests produce so many distinct configurations and whether equivalent ones can be consolidated.

## 9. Observing Cache Hits/Misses in Logs

Spring TestContext exposes cache statistics via logging. Set the following logger to `DEBUG` in your test log configuration:

~~~properties
logging.level.org.springframework.test.context.cache=DEBUG
~~~

If the project does not use Spring Boot logging properties, configure the equivalent level in Logback, Log4j, or your chosen logging system. During test execution, look for metrics such as:

- `size`: number of contexts currently in the cache.
- `maxSize`: maximum cache entry limit.
- `hitCount`: lookups that found a matching context.
- `missCount`: lookups with no matching cached context.
- `parentContextCount`: parent context count when using context hierarchies.

A cache miss on the first load of a configuration is normal. What warrants investigation is a miss count that grows steadily in a suite meant to share configurations, or contexts repeatedly evicted due to `@DirtiesContext` and cache eviction.

Note that **`hitCount` is not the number of passing test methods**; the framework may query the cache multiple times during a single test's lifecycle, so do not divide `hitCount` by test count to compute an exact hit ratio. Use these metrics as diagnostic signals paired with comparing context configurations.

### When Context Loading Fails

In newer Spring Framework versions, TestContext includes a **context failure threshold** to avoid repeatedly trying to load a broken context. A default used since Spring Framework 6.1 is a threshold of 1 failure per cache key, adjustable via:

~~~text
-Dspring.test.context.failure.threshold=2
~~~

When you see an error like "`ApplicationContext failure threshold exceeded`", look for **the first context-loading exception** (for example, a missing property, uncreatable bean, or unreachable database) rather than reading only the skipped subsequent failures. Raising the threshold does not fix misconfiguration; it is only useful in specific diagnostic scenarios or transient resource failures.

## 10. Specific Spring Batch Failure Modes with Context Caching

### Scenario A: "JobInstance already complete"

**Symptom:** The first test runs a job to completion; the second test uses the same job name and the same identifying `JobParameters` and receives `JobInstanceAlreadyCompleteException`.

**Cause:** `JobRepository` still holds metadata for an already completed `JobInstance`. Context caching can make it easier for tests to share a repository, though the actual state resides in the database.

**Resolution:** Use an isolated test database; clear metadata between tests when independent runs are the goal; or supply distinct `JobParameters` when testing a new job instance. When testing restart, **do not delete metadata between the two runs of the same instance**, because that metadata is required for restart behavior.

### Scenario B: Writer Test Reports More Records Than Expected

**Symptom:** Running alone yields three rows; running after another test class yields six rows.

**Possible causes:** The business table was not reset, the writer uses a static collector, or both tests share the same data keys.

**Resolution:** Reset dedicated test tables or use isolated schemas/databases; never blindly delete data in shared environments. If a writer holds state in a singleton, refactor the design or reset it intentionally before each test case.

### Scenario C: Closing Contexts Makes the Suite Slow

**Symptom:** Frequent database/bean startup logs; total runtime grows linearly with the number of test classes.

**Possible causes:** `@DirtiesContext` on a base class, each class overriding an inline property, differing mock declarations, or cache eviction.

**Resolution:** Enable `DEBUG` on the cache logger, inspect hit/miss stats, compare annotations across classes, and keep `@DirtiesContext` only where the context genuinely cannot be reused.

### Scenario D: Testcontainers Tests Pass Alone but Fail in the Suite

**Symptom:** `DataSource` tries to connect to a port/container that shut down when the previous class finished.

**Possible causes:** Container lifetime is shorter than the cached context; dynamic configuration from `@DynamicPropertySource` is reused against a stale endpoint.

**Resolution:** Keep the container alive long enough if contexts are shared, or avoid sharing contexts when endpoints change. Also isolate data produced by different tests inside the shared container.

### Scenario E: Testing a Step-Scoped Bean Without a StepExecution

**Symptom:** A `@StepScope` reader accesses job parameters or execution context, yet the test invokes the bean directly without a step context.

**Cause:** The bean relies on runtime scope, not a context-cache data loss bug.

**Resolution:** Use `@SpringBatchTest` scope support, the relevant test execution listeners, or `StepScopeTestUtils` to supply a suitable `StepExecution`. Each test must provide its expected scope and parameters; reusing `ApplicationContext` does not mean reusing the previous test's `StepExecution`.

## 11. Parallel Tests: Cache Still Works, Data Must Be Isolated

When running in parallel, two tests can share a cached `ApplicationContext`. That **does not automatically make the application or test fixtures thread-safe**:

- If two jobs write to the same table with identical IDs, they can collide or interleave results.
- If both tests call `JobRepositoryTestUtils.removeJobExecutions()` against the same database, one test can delete metadata for another test's active job.
- If a mutable singleton holds counters or temporary lists, tests can corrupt each other's state.
- If tests mutate global system properties, changes can leak to tests running on other threads.

Sensible strategies include: separate schemas/databases, per-test data keys, grouping tests that must run sequentially, or redesigning beans to avoid mutable shared state. Pick a strategy matching your real constraints; disabling context caching solely to dodge concurrency bugs is rarely sufficient because external databases remain shared resources anyway.

Especially with `JobRepositoryTestUtils.removeJobExecutions()`, this operation is safest when each suite uses a **dedicated repository with no concurrent jobs**. If multiple jobs run against the same repository, design scoped metadata deletion with explicit lifecycles, or provision separate repositories per test.

## 12. An Approach for Fast and Reliable Test Suites

A practical organization:

1. **Tier by Spring dependency.** Test pure-Java processors with no context; test reader mapping directly; reserve `@SpringBatchTest`/`@SpringBootTest` for job integration.
2. **Keep integration test configs consistent.** Share the same `test` profile, configuration sources, and properties across tests needing the same environment.
3. **Make fixtures and expected outputs explicit.** Small datasets with fixed IDs make post-job verification straightforward.
4. **Separate context lifecycle from data lifecycle.** Let Spring cache contexts; clean job metadata, business tables, and test resources per test case.
5. **Do not randomize `JobParameters` just to mask bugs.** Choose meaningful identifying parameters; vary them for new job instances and reuse the exact instance when testing restart.
6. **Use `@DirtiesContext` only when the context is genuinely unsafe.** Cleaning isolated data does not require dirtying the context.
7. **Measure before optimizing.** Check cache logs, context load counts, memory usage, database connections, and build-tool fork/parallel settings.

Matching test tiers:

| Test Group | Needs Spring Context? | What to Clean? | Expected Caching |
|---|---|---|---|
| Pure Java processor | No | Local test objects. | Not applicable. |
| Standalone flat file parser | Possibly no | Close reader, reset test execution context. | Not required. |
| Batch job integration on test DB | Yes | Business tables, `BATCH_*`, input/output resources. | Reused when configs match. |
| Step-scoped reader integration | Yes | `StepExecution` and test state. | Context reusable; step scope set per test. |
| Irreversible singleton config change | Yes | External resources if any. | Mark dirty at the needed scope. |
| Batch tests with containers having varying endpoints | Yes | Container lifecycle and data. | Cache safe only while endpoint/config matches. |

## 13. Frequently Asked Questions

**Should `@DirtiesContext` be placed on every Spring Batch test class?**

No. Doing so forces classes to repeatedly rebuild contexts while committed database records may still linger. Clean data where it is stored, and use `@DirtiesContext` only when the context is mutated so that reuse is unsafe.

**Do two tests both annotated with `@SpringBootTest` definitely share a context?**

Not necessarily. The key also depends on profiles, properties, configuration classes, initializers, context customizers (including mock/override declarations), and other factors. Furthermore, the cache is only shared within the same JVM.

**Can caching cause `JobRepository` to drop or duplicate metadata?**

Context caching itself does not govern metadata persistence. `JobRepository` records job instances/executions according to Spring Batch rules and persistence config. Duplicate-run errors usually stem from `JobParameters`, leftover repository data, or unisolated test strategies.

**If the context is reloaded, will the test database be empty?**

There is no general guarantee. It depends on schema initialization settings, database type, connection/container lifecycles, and resource provisioning. With PostgreSQL or any external database outside the context, data persists until cleaned or replaced by another database.

**Does enabling caching make tests order-dependent?**

Context reuse can **expose** mutable state or uncleaned data between tests. The solution is controlling input/output state and isolation while keeping singletons safe for reuse.

**Where should I start if tests are slow?**

Set `org.springframework.test.context.cache` to `DEBUG` and inspect hits, misses, and context closures. Then compare class configurations, JVM fork counts, and startup times of resources like databases or containers rather than optimizing by guesswork.

## Conclusion

In Spring Batch test infrastructure, **context caching** is Spring TestContext's mechanism for reusing `ApplicationContext` instances when test configurations match. It delivers speed, yet requires clearly separating **Spring configuration** from **batch execution state**.

Let contexts be cached where appropriate, use `@SpringBatchTest` to drive jobs and steps, proactively clean `JobRepository` metadata and writer data, manage container/fixture lifecycles, and reserve `@DirtiesContext` for contexts that are no longer safe to reuse. When these boundaries are cleanly drawn, integration test suites run fast and remain stable individually, across the full suite, and in CI.
