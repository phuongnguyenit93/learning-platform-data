# TestExecutionListener in Spring Batch: Test Lifecycle Control Infrastructure

## 1. What Problem Does TestExecutionListener Solve?

A Spring Batch test usually needs more than a `@Test` method: creating an `ApplicationContext`, injecting beans, preparing `JobExecution`/`StepExecution`, activating scopes for readers/writers, initializing data, and cleaning up resources when the test ends.

In Spring Test, **`TestExecutionListener`** is the contract for components invoked at fixed points in the **test execution lifecycle**. The Spring TestContext Framework orchestrates these listeners so that infrastructure work happens automatically and consistently across tests.

For **Spring Batch Core Processing**, under **Test infrastructure**, two specialized listeners are especially important:

- **`StepScopeTestExecutionListener`**: sets up a `StepExecution` so `@StepScope` beans have context during testing.
- **`JobScopeTestExecutionListener`**: sets up a `JobExecution` so `@JobScope` beans have context during testing.

The **`@SpringBatchTest`** annotation registers these listeners and provides additional batch testing utilities. This lesson explains both the general Spring Test mechanism and practical usage for Spring Batch.

After this lesson, you will be able to identify which callbacks run before/after tests, configure listeners properly, test step/job-scoped beans, write custom listeners when truly needed, and diagnose missing-scope or missing-`JobParameters` errors.

## 2. Distinguishing Similarly Named Concepts

Multiple kinds of listeners can exist in a Spring Batch application; they operate at different lifecycles.

| Component | Package / Source | When Is It Invoked? | Example Responsibilities |
|---|---|---|---|
| `TestExecutionListener` | `org.springframework.test.context.TestExecutionListener` | When Spring Test runs a test class/method | Prepare test context, inject beans, bind scopes, clean test data |
| `StepScopeTestExecutionListener` | `org.springframework.batch.test.StepScopeTestExecutionListener` | During each test's lifecycle | Bind a `StepExecution` to the current thread to resolve `@StepScope` |
| `JobScopeTestExecutionListener` | `org.springframework.batch.test.JobScopeTestExecutionListener` | During each test's lifecycle | Bind a `JobExecution` to resolve `@JobScope` |
| `StepExecutionListener` | Spring Batch runtime | When a **real step** starts/ends | `beforeStep`, `afterStep`, updating `ExitStatus` |
| `JobExecutionListener` | Spring Batch runtime | When a **real job** starts/ends | `beforeJob`, `afterJob`, inspecting job outcomes |
| `BeforeEachCallback` / `AfterEachCallback` | JUnit Jupiter extension API | Before/after tests in the JUnit lifecycle | Custom JUnit extensions |
| `@BeforeEach` / `@AfterEach` | JUnit Jupiter | Setup/teardown inside the test class itself | Create fixture files, reset test-specific state |

A `TestExecutionListener` is **not** a `StepExecutionListener`. For instance, `StepScopeTestExecutionListener` makes a step-scoped bean testable in isolation; it does not trigger a batch step execution, does not run `ItemReader.read()`, and does not call `afterStep()` in place of a real step.

### Layers in the Execution Mechanism

```text
JUnit Jupiter
    │
    ▼
SpringExtension
    │
    ▼
Spring TestContextManager
    │
    ├── DependencyInjectionTestExecutionListener
    ├── TransactionalTestExecutionListener
    ├── StepScopeTestExecutionListener       (spring-batch-test)
    ├── JobScopeTestExecutionListener        (spring-batch-test)
    └── Custom TestExecutionListener
               │
               ▼
         @Test methods
               │
               ├── access @StepScope/@JobScope beans
               └── or call JobLauncherTestUtils to run job/step
```

`SpringExtension` is the bridge between JUnit 5 and Spring TestContext. Listeners are managed by Spring according to the callback mechanism and configured order.

## 3. The TestExecutionListener Lifecycle

The `TestExecutionListener` interface provides default callbacks. An implementation only needs to override the callbacks useful for its requirements.

| Callback | Typical Timing | Purpose |
|---|---|---|
| `beforeTestClass(TestContext)` | Before tests of a class | Check/prepare infrastructure shared across the class |
| `prepareTestInstance(TestContext)` | After creating the test instance | Dependency injection or instance setup |
| `beforeTestMethod(TestContext)` | Before `@BeforeEach` | Bind scopes, set up method-level infrastructure |
| `beforeTestExecution(TestContext)` | After `@BeforeEach`, before `@Test` | Timing or provisioning resources needed strictly during the test body |
| `afterTestExecution(TestContext)` | After `@Test`, before `@AfterEach` | Capture failure info or measurements |
| `afterTestMethod(TestContext)` | After `@AfterEach` | Unbind method-scoped context, end-of-method cleanup |
| `afterTestClass(TestContext)` | After all tests in the class | Clean up shared class infrastructure |

A typical timeline when running JUnit Jupiter:

```text
beforeTestClass
  └─ create test instance
       └─ prepareTestInstance
            └─ beforeTestMethod
                 └─ @BeforeEach
                      └─ beforeTestExecution
                           └─ @Test
                      ┌─ afterTestExecution
                 ┌─ @AfterEach
            ┌─ afterTestMethod
afterTestClass
```

This is a **conceptual order** for callbacks, excluding other JUnit extensions. A test class may be instantiated multiple times depending on JUnit's lifecycle policy.

### Ordering Multiple Listeners

Spring TestContext invokes listeners in an order determined by `Ordered`/`@Order` or registration order, depending on the discovery mechanism:

- For callbacks **before** the test, higher-precedence listeners typically run first.
- For callbacks **after** the test, the execution order is normally **reversed**, tearing down symmetrically with setup steps.
- Default Spring listeners have built-in ordering to avoid errors such as using transactions before dependency injection completes.

If you create a new listener, use `@Order` or implement `Ordered` when an actual ordering dependency exists. Do not tweak listener order just "to be safe"; accidentally placing cleanup ahead of transaction/scope listeners can cause hard-to-diagnose bugs.

### What Does TestContext Contain?

Through `org.springframework.test.context.TestContext`, a listener can access:

- The current test class and test method.
- The test instance under execution.
- The `ApplicationContext` and beans in it (once loaded).
- Any exception thrown by the test method, if present.
- Attributes used to pass data between listeners during a test run.

This information lets a listener observe or prepare infrastructure; it does not mean the listener should directly drive all business logic.

## 4. Dependencies and Enabling Spring Batch Test Support

With Spring Boot 3.x, Spring Batch 5.x, and JUnit Jupiter, a typical Gradle declaration is:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'

    // Only needed when integration tests create JobRepository on H2.
    runtimeOnly 'com.h2database:h2'
}
```

Or Maven:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-batch</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.batch</groupId>
        <artifactId>spring-batch-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

When using Spring Boot, let dependency management govern compatible versions instead of pinning mismatched Spring Test and Spring Batch versions manually.

### @SpringBatchTest

The most concise way to enable test infrastructure in a Spring Batch application:

```java
import org.junit.jupiter.api.Test;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.JobRepositoryTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBatchTest
@SpringBootTest(
    classes = BatchApplication.class,
    properties = "spring.batch.job.enabled=false"
)
class PaymentJobTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    private JobRepositoryTestUtils jobRepositoryTestUtils;

    @Test
    void testInfrastructureIsAvailable() {
        // Use jobLauncherTestUtils for launchJob / launchStep,
        // and jobRepositoryTestUtils when cleaning metadata
        // in an isolated repository dedicated to testing.
    }
}
```

`@SpringBatchTest` provides utility beans `JobLauncherTestUtils`/`JobRepositoryTestUtils` and registers `StepScopeTestExecutionListener` and `JobScopeTestExecutionListener`. `@SpringBootTest` loads the application context; disabling Spring Boot's automatic job execution lets the test control when the job launches.

**Note:** the example above assumes the application actually configures batch support, `JobRepository`, `JobLauncher`, and the required beans. If there are multiple `Job`s, specify the job under test on `JobLauncherTestUtils`.

`@SpringBatchTest` does not generate input data, does not guarantee the job will succeed, and does not replace assertions on `JobExecution`, `StepExecution`, and output data.

## 5. StepScopeTestExecutionListener: Testing @StepScope Beans

### 5.1. The Problem

Suppose a reader receives its filename from `StepExecutionContext`:

```java
@Bean
@StepScope
public FlatFileItemReader<Payment> reader(
        @Value("#{stepExecutionContext['inputFile']}") String inputFile) {
    // Create reader with the resource located at inputFile.
    // ...
}
```

Because `@StepScope` is bound to **an active StepExecution**, merely loading the Spring context is not enough. When a test accesses the bean proxy without a step context, an error like this typically appears:

```text
Scope 'step' is not active for the current thread
```

`StepScopeTestExecutionListener` solves this by supplying a `StepExecution` during the test method's lifecycle. Spring Batch can create a default `StepExecution` for the test, or you can provide a factory method returning a `StepExecution` populated with the needed `ExecutionContext`.

### 5.2. Complete Example Using Spring TestContext

This example uses Spring Batch 5.x, JUnit Jupiter, and a simple bean to isolate the scope mechanism from file I/O or metadata databases. No real job launch is required.

```java
package com.example.batchtest;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.scope.StepScope;
import org.springframework.batch.test.MetaDataInstanceFactory;
import org.springframework.batch.test.StepScopeTestExecutionListener;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.TestExecutionListeners;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = StepScopeListenerTest.Config.class)
@TestExecutionListeners(
        listeners = StepScopeTestExecutionListener.class,
        mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
class StepScopeListenerTest {

    @Configuration(proxyBeanMethods = false)
    static class Config {

        // Register StepScope without starting a full JobRepository.
        @Bean
        static StepScope stepScope() {
            return new StepScope();
        }

        @Bean
        @StepScope
        InputDescriptor inputDescriptor(
                @Value("#{stepExecutionContext['inputFile']}") String path) {
            return new InputDescriptor(path);
        }
    }

    // Do not declare final: @StepScope uses a class-based scoped proxy.
    public static class InputDescriptor {
        private final String file;

        public InputDescriptor(String file) {
            this.file = file;
        }

        public String getFile() {
            return file;
        }
    }

    @Autowired
    private InputDescriptor inputDescriptor;

    // StepScopeTestExecutionListener obtains the StepExecution from this factory.
    public StepExecution getStepExecution() {
        StepExecution execution = MetaDataInstanceFactory.createStepExecution();
        execution.getExecutionContext()
                .putString("inputFile", "fixtures/orders.csv");
        return execution;
    }

    @Test
    void resolvesValueFromStepExecutionContext() {
        assertEquals("fixtures/orders.csv", inputDescriptor.getFile());
    }
}
```

Flow explanation:

1. `@SpringJUnitConfig` integrates Spring Test with JUnit 5 and loads the test configuration.
2. The configuration declares `StepScope` and registers the `@StepScope` bean `InputDescriptor`.
3. `@TestExecutionListeners(...MERGE_WITH_DEFAULTS)` adds the specialized listener while keeping Spring's default listeners required for injection and test infrastructure.
4. The listener locates the `StepExecution` returned by `getStepExecution()`, which inserts `inputFile` into `StepExecutionContext`.
5. When `@Test` calls `inputDescriptor.getFile()`, the scoped proxy accesses the bean with the step context activated and reads the string `fixtures/orders.csv`.
6. After the test, the listener removes the step context from the thread.

In practice, in an application already using `@EnableBatchProcessing` or Spring Boot Batch auto-configuration, `StepScope` is usually registered automatically. Do not declare a duplicate `StepScope` bean in such an application context.

### 5.3. Notes on the Factory Method

- Naming the method `getStepExecution()` and returning `StepExecution` lets the listener find the test-supplied context.
- Use `MetaDataInstanceFactory` to create lightweight test metadata without opening a database connection just to evaluate scope expressions.
- If the test does not supply a factory, the listener can create a default `StepExecution`; however, the default context will lack business keys like `inputFile`.
- `ExecutionContext` has distinct levels: `stepExecutionContext` belongs to the step, while `jobExecutionContext` belongs to the job. Do not put a key in one and reference it with the expression for the other.
- Avoid accessing step-scoped beans in test constructors or static initializers. The scope works properly once the listener has bound the context during the test method lifecycle.

### 5.4. When You Only Want to Activate Scope for One Block of Code

Some tests need explicit scope boundaries rather than keeping the scope active across the whole method. `StepScopeTestUtils.doInStepScope` lets you execute a `Callable` with a specific `StepExecution`:

```java
StepExecution stepExecution =
        MetaDataInstanceFactory.createStepExecution();
stepExecution.getExecutionContext()
        .putString("inputFile", "fixtures/manual.csv");

String actual = StepScopeTestUtils.doInStepScope(
        stepExecution,
        () -> inputDescriptor.getFile()
);

assertEquals("fixtures/manual.csv", actual);
```

This snippet assumes `inputDescriptor` is injected from a Spring context with `StepScope` registered, and adds the import:

```java
import org.springframework.batch.test.StepScopeTestUtils;
```

`doInStepScope` is useful when testing multiple `ExecutionContext` sets within one method, or when you do not want to configure a listener for the whole class. You do not need to combine both approaches if one already satisfies the test goal.

### 5.5. What This Level of Testing Actually Proves

A test like the one above **proves late binding** from `StepExecutionContext` into the scoped bean. It does not prove the reader can open the file, the processor transforms items properly, or the writer creates the right output. To verify those, run a real step/job via the test utilities and assert output data.

## 6. JobScopeTestExecutionListener: Testing @JobScope Beans

`@JobScope` has a broader lifecycle than `@StepScope`: a job-scoped bean lives within the context of a `JobExecution`. It is often used for configuration shared across multiple steps, such as tenant name, root directory, business date, or a run configuration object.

`JobScopeTestExecutionListener` provides the `JobExecution` to that bean during test execution. Standalone example:

```java
package com.example.batchtest;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.configuration.annotation.JobScope;
import org.springframework.batch.core.scope.JobScope;
import org.springframework.batch.test.JobScopeTestExecutionListener;
import org.springframework.batch.test.MetaDataInstanceFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.TestExecutionListeners;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = JobScopeListenerTest.Config.class)
@TestExecutionListeners(
        listeners = JobScopeTestExecutionListener.class,
        mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
class JobScopeListenerTest {

    @Configuration(proxyBeanMethods = false)
    static class Config {

        @Bean
        static JobScope jobScope() {
            return new JobScope();
        }

        @Bean
        @JobScope
        RunInfo runInfo(
                @Value("#{jobExecutionContext['runLabel']}") String label) {
            return new RunInfo(label);
        }
    }

    public static class RunInfo {
        private final String label;

        public RunInfo(String label) {
            this.label = label;
        }

        public String getLabel() {
            return label;
        }
    }

    @Autowired
    private RunInfo runInfo;

    public JobExecution getJobExecution() {
        JobExecution execution = MetaDataInstanceFactory.createJobExecution();
        execution.getExecutionContext()
                .putString("runLabel", "daily-settlement");
        return execution;
    }

    @Test
    void resolvesValueFromJobExecutionContext() {
        assertEquals("daily-settlement", runInfo.getLabel());
    }
}
```

In this example, the listener uses the `JobExecution` returned by `getJobExecution()` to activate the job scope. `runInfo` is injected as a proxy, while the actual target object is instantiated under the job context when the test calls `getLabel()`.

If the value comes from **JobParameters**, construct a `JobExecution` containing the corresponding `JobParameters` and use the expression:

```java
@Value("#{jobParameters['inputFile']}") String inputFile
```

Do not conflate `jobParameters` with `jobExecutionContext`: parameters are inputs supplied when launching the job, whereas execution context is mutable state updated during processing.

### When a Test Needs Both Job Scope and Step Scope

A step-scoped bean can reference data at both levels. When a test requires both, `StepExecution` and `JobExecution` must be consistently linked: the step must belong to the job execution whose data is being referenced.

In complex cases, **running a real step with test-supplied `JobParameters`** is often easier to verify than manually wiring multiple contexts together. `@SpringBatchTest` registers the necessary listeners when both scopes are used.

## 7. Writing Your Own Custom TestExecutionListener

Not every test infrastructure requirement has a built-in listener. You can write a listener to track failures, attach a trace ID, collect diagnostics, or manage shared test resources.

A concise way is to extend `AbstractTestExecutionListener` and override only the needed callbacks. For example, logging when a test method throws an exception:

```java
package com.example.batchtest;

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.springframework.test.context.TestContext;
import org.springframework.test.context.support.AbstractTestExecutionListener;

public class BatchFailureDiagnosticsListener
        extends AbstractTestExecutionListener {

    private static final Log log =
            LogFactory.getLog(BatchFailureDiagnosticsListener.class);

    @Override
    public void afterTestExecution(TestContext testContext) {
        Throwable failure = testContext.getTestException();
        if (failure == null) {
            return;
        }

        String testId = testContext.getTestClass().getSimpleName()
                + "#" + testContext.getTestMethod().getName();

        log.error("Batch test failed: " + testId, failure);
    }
}
```

Registering the listener in a test:

```java
import org.springframework.test.context.TestExecutionListeners;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = SomeTestConfig.class)
@TestExecutionListeners(
    listeners = {
        StepScopeTestExecutionListener.class,
        BatchFailureDiagnosticsListener.class
    },
    mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
class ScopedReaderTest {
    // @Autowired reader and corresponding @Test methods
}
```

For the declaration above, add the import:

```java
import org.springframework.batch.test.StepScopeTestExecutionListener;
```

The listener observes failures; it does not replace assertions and must never swallow exceptions to produce fake passing tests. For common tasks like creating per-method fixtures, `@BeforeEach` and `@TempDir` are clearer and more explicit than writing a custom listener.

### Choosing a Callback by Purpose

| Task | Appropriate Mechanism |
|---|---|
| Create distinct input files per test | `@BeforeEach` with `@TempDir` |
| Need Spring bean injection | Default `DependencyInjectionTestExecutionListener` |
| Activate `StepExecution` across multiple tests | `StepScopeTestExecutionListener` |
| Activate `JobExecution` across multiple tests | `JobScopeTestExecutionListener` |
| Measure execution duration of the `@Test` body | `beforeTestExecution` + `afterTestExecution` |
| Collect errors right after the `@Test` body | `afterTestExecution` |
| Tear down resources spanning `@BeforeEach` and `@AfterEach` | `afterTestMethod` |
| Clean job metadata in an isolated test DB | `JobRepositoryTestUtils` / explicit fixture cleanup |

## 8. Registering Listeners: Automatic, Explicit, and Inherited

### Option A — Using @SpringBatchTest

Suitable for most Spring Batch integration tests:

```java
@SpringBatchTest
@SpringBootTest
class JobIntegrationTest {
    // Listeners for step/job scope are already provided by @SpringBatchTest.
}
```

Advantage: minimal configuration, aligned with the official test utilities.

### Option B — Explicit Registration

Suitable when only Spring TestContext and a single scope are needed, such as unit testing a scoped reader:

```java
@SpringJUnitConfig(classes = ReaderConfig.class)
@TestExecutionListeners(
    listeners = StepScopeTestExecutionListener.class,
    mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
class ReaderScopeTest {
}
```

`MERGE_WITH_DEFAULTS` preserves Spring Test's default listeners. If you omit this option and supply a partial list, you can accidentally drop injection or transaction listeners that the test depends on.

### Option C — Adding a Custom Listener Alongside @SpringBatchTest

When adding a custom listener to a setup already annotated with `@SpringBatchTest`, pay attention to **ordering and annotation inheritance/merging**. You can use `@TestExecutionListeners(..., mergeMode = MERGE_WITH_DEFAULTS)` while ensuring the required batch listeners remain present in the effective configuration. If needed, declare both batch listeners and the custom listener explicitly on the test.

Do not register the same listener both manually and via meta-annotations without understanding how Spring merges listener lists. Verify scope behavior in the test to confirm scopes activate at the right time.

### Option D — Custom JUnit Extension

If the problem is purely JUnit-related (requiring no `TestContext`, `ApplicationContext`, or Spring scopes), a `BeforeEachCallback`/`AfterEachCallback` may be a better fit. Reserve `TestExecutionListener` for mechanisms tied to Spring TestContext.

## 9. How Test Listeners Relate to Real Steps and Jobs

Test listeners primarily supply **context**, while the Spring Batch runtime actually drives reading, processing, writing, and committing data.

Example flow for testing a job that takes file paths from `JobParameters`:

```text
JUnit @Test
  │
  ├─ @SpringBatchTest
  │    ├─ Spring TestContext
  │    ├─ StepScopeTestExecutionListener
  │    └─ JobScopeTestExecutionListener
  │
  └─ JobLauncherTestUtils.launchJob(parameters)
         │
         ├─ JobRepository creates JobExecution
         ├─ Step executes inside transaction/chunk
         │    ├─ @StepScope reader obtains inputFile
         │    ├─ ItemProcessor
         │    └─ @StepScope writer obtains outputFile
         │
         └─ Returns JobExecution
                 ├─ assert BatchStatus
                 ├─ assert readCount/writeCount/skipCount
                 └─ assert file output
```

Integration test template:

```java
@SpringBatchTest
@SpringBootTest(
    classes = BatchApplication.class,
    properties = {
        "spring.batch.job.enabled=false",
        "spring.batch.jdbc.initialize-schema=always"
    }
)
class ImportJobTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @TempDir
    Path tempDir;

    @Test
    void readsAnInputResourceAndWritesTheExpectedOutput()
            throws Exception {

        Path input = tempDir.resolve("input.csv");
        Path output = tempDir.resolve("output.csv");

        Files.writeString(input, "id,amount\n1,10.00\n",
                StandardCharsets.UTF_8);

        JobParameters parameters = new JobParametersBuilder()
                .addString("inputFile", input.toString())
                .addString("outputFile", output.toString())
                .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        assertTrue(Files.exists(output));
        // Also assert actual output contents and read/write/skip counts.
    }
}
```

Required imports for the snippet above:

```java
import static org.junit.jupiter.api.Assertions.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
```

`BatchApplication` represents the real application configuring the Job, Step, reader, and writer; the test only illustrates how to use the infrastructure. If the project lacks a metadata schema or valid datasource, the integration test will not run solely by adding `@SpringBatchTest`.

**Distinguish two scenarios:**

- Testing a **`@StepScope` bean directly**: the listener is essential to mock/set up the scope; no job needs to run.
- Testing a **real job/step** via a launcher: Spring Batch sets up scopes itself during step execution; `@SpringBatchTest` provides test utilities and test context integration.

Do not use a passing test of a single scoped bean as proof that the entire job handles resources properly.

## 10. Transactions, Test Data, and Cleanup Order

Spring test infrastructure can combine other listeners such as `TransactionalTestExecutionListener` and `SqlScriptsTestExecutionListener`. In batch testing, this is a common source of bugs when assuming all data rolls back with a single transaction.

### Typical Pitfall

1. A test is annotated with `@Transactional`; Spring Test opens a transaction wrapping the test per `TransactionalTestExecutionListener`.
2. The test calls `JobLauncherTestUtils.launchJob(...)`.
3. The job/step executes with its own transaction manager and commit boundaries.
4. The test expects all batch writes to always roll back with the outer test transaction.

That expectation is **not always true**. The job may run on another thread/transaction; `JobRepository` and business database configuration also affect how transactions behave. Design fixtures and cleanup around the job's actual behavior.

For batch integration tests:

- Use a dedicated test database or isolated schema; do not rely on test rollback to revert changes committed by the job.
- Explicitly initialize required state before the test.
- Use appropriate identifying parameters when running multiple `JobInstance`s; rerunning a `COMPLETED` instance will not produce an identical fresh run.
- If using `JobRepositoryTestUtils.removeJobExecutions()`, apply it only on a repository **dedicated to testing**, as it deletes execution metadata.
- Place file resources under `@TempDir`; do not share hardcoded paths across test methods or threads.

### Scope Lifecycle and Errors in @AfterEach

A step-scoped bean may still need its context when accessed in `@AfterEach`. Because `StepScopeTestExecutionListener` normally tears down the scope in `afterTestMethod`, the listener lifecycle allows cleanup operations in `@AfterEach` to execute while the context is still valid. Even so, avoid retaining references to the underlying step-scoped target object for use after the test finishes or on a thread without a bound context.

In parallel testing, thread-bound scope contexts do not automatically make shared data thread-safe: files, table names, static state, and shared repositories can still collide.

## 11. Common TestExecutionListener Configuration Errors

| Symptom | Common Cause | Resolution |
|---|---|---|
| `Scope 'step' is not active for the current thread` | Accessing a `@StepScope` bean with no bound `StepExecution` | Add `StepScopeTestExecutionListener`, use `@SpringBatchTest`, or `StepScopeTestUtils` |
| `Scope 'job' is not active for the current thread` | Accessing a `@JobScope` bean with no `JobExecution` | Use `JobScopeTestExecutionListener`/`@SpringBatchTest` |
| `No Scope registered for scope name 'step'` | Spring context has not registered `StepScope` | Use batch configuration or declare a `StepScope` bean for minimal test contexts |
| `@Value` in scoped bean resolves to `null` | Key missing from context or wrong context type | Check expressions for `stepExecutionContext`, `jobExecutionContext`, and `jobParameters` |
| `@Autowired` does not inject beans | Default listeners were replaced by manual declaration | Enable `MERGE_WITH_DEFAULTS` and retain Spring Test injection infrastructure |
| Unit test passes, job integration test fails on metadata | Mock scope works, but JobRepository/DB is not configured | Configure database, schema, transaction manager, and batch infrastructure for integration tests |
| Test passes alone, fails in full suite | Shared files, job parameters, test DB, or mutable context | Use `@TempDir`, isolated fixtures, and managed `JobInstance`s |
| Scoped bean access error after test ends | Using target after scope closed or across threads | Access only within scope lifecycle or bind proper context to the thread |
| Error creating scoped proxy for final class | `@StepScope`/`@JobScope` typically use class-based scoped proxies | Use a proxyable bean type or design an interface/proxy accordingly |
| Custom listener hides original failure output | Listener itself throws an exception during cleanup | Ensure safe cleanup; log secondary errors without masking the primary test failure |

### Systematic Diagnosis

When encountering a scope error, follow this path:

```text
Are @SpringJUnitConfig / @SpringBootTest and SpringExtension present?
    │
    ├─ No -> Spring TestContext is not active.
    │
    └─ Yes
        │
        ▼
Does the context register StepScope / JobScope?
    │
    ├─ No -> Configure the scope.
    │
    └─ Yes
        │
        ▼
Is the matching listener / StepScopeTestUtils present?
    │
    ├─ No -> Bind StepExecution / JobExecution.
    │
    └─ Yes
        │
        ▼
Does the context contain the key referenced by @Value?
    │
    ├─ No -> Initialize the proper ExecutionContext / JobParameters.
    │
    └─ Yes -> Check thread, access timing, proxy, and actual context.
```

These steps distinguish test infrastructure issues from business bugs in readers, processors, or writers.

## 12. Practice: Testing Listeners at Each Level

### Exercise 1 — Value from StepExecutionContext

Create a `@StepScope` bean reading `stepExecutionContext['batchSize']`. Write a test using `StepScopeTestExecutionListener` with `getStepExecution()` supplying `batchSize=50` and assert the bean receives the right integer.

Next, remove the factory method and observe what happens when the default context lacks the key. Explain why the listener activates the scope but does not fabricate business data automatically.

### Exercise 2 — Value from JobExecutionContext

Create a `@JobScope` bean with a `tenant` property sourced from `jobExecutionContext['tenant']`. Test two sample values `"shop-A"` and `"shop-B"` using two distinct `JobExecution`s or two independent test methods. Ensure the scoped bean does not reuse stale data across runs.

### Exercise 3 — Manual Scope versus Listener

Using the same `@StepScope` bean, write two tests:

- Test A: register `StepScopeTestExecutionListener`.
- Test B: activate scope for a single callback using `StepScopeTestUtils.doInStepScope`.

Compare the effective scopes and which style is easier to read.

### Exercise 4 — Diagnostic Listener

Write `BatchFailureDiagnosticsListener` to log the method name and exception when a test fails. Run a test with an intentionally failing assertion. Confirm the test still reports **FAILED** and the original error details remain intact.

### Exercise 5 — Full Job Integration

Use `@SpringBatchTest` to test a job that reads CSV, adds a fee, and writes CSV:

1. Create input/output files inside `@TempDir`.
2. Pass file paths via `JobParameters`.
3. Call `JobLauncherTestUtils.launchJob(...)`.
4. Assert `BatchStatus.COMPLETED`, `readCount`, `writeCount`, and the complete output contents.
5. Supply malformed input to observe `BatchStatus.FAILED`; explain how this differs from scope-activation failures in unit tests.

## 13. Version and API Notes

The declarations and imports in this lesson match **Spring Batch 5.x, Spring Framework 6.x, and JUnit Jupiter**. For Spring Batch 6.x, consult the corresponding API documentation to update classes whose packages or test utilities changed. The Spring TestContext `TestExecutionListener` mechanism and the purpose of the two scope listeners remain foundational.

In Spring Batch 5.x, `JobLauncherTestUtils.launchJob()/launchStep()` are commonly used in batch tests. In Spring Batch 6.x, `JobOperatorTestUtils.startJob()/startStep()` replace them when upgrading the test utilities. During migration, align dependencies and imports across the entire project to the same Spring Batch version.

Do not copy imports from a Spring Batch 5.x example into a Spring Batch 6.x project and merely rename the test utility; verify against that release line's API documentation.

## 14. References

- [Spring Framework — TestContext Framework](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework.html): Spring context-based testing architecture, callbacks, and listeners.
- [Spring Framework — TestExecutionListener](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tel-config.html): registration, auto-discovery, ordering, and listener inheritance.
- [Spring Batch — Unit Testing](https://docs.spring.io/spring-batch/reference/testing.html): `@SpringBatchTest`, step/job scoped testing, and test utilities.
- [Spring Batch — Late Binding of Job and Step Attributes](https://docs.spring.io/spring-batch/reference/step/late-binding.html): `@StepScope`, `@JobScope`, and late-bound execution attributes.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): JUnit Jupiter lifecycle and extension model.

`TestExecutionListener` connects the test lifecycle to Spring infrastructure. In Spring Batch, understanding `StepScopeTestExecutionListener`, `JobScopeTestExecutionListener`, and `@SpringBatchTest` helps test batch-context-dependent beans accurately while clearly separating **setting up the test context** from **running a real job/step and verifying data outcomes**.
