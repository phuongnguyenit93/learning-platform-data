# `JobScopeTestUtils` in Spring Batch: Testing `@JobScope` Beans

In Spring Batch, many data processing components need to receive values when the **job actually starts running**: customer ID from `JobParameters`, execution mode from `JobExecutionContext`, or job name from `JobExecution`. Such beans are typically declared with `@JobScope`. When writing a unit test for an individual component, however, we do not want to launch an entire job just to supply these values.

`JobScopeTestUtils` solves that exact problem: it creates an **active job scope** environment inside a test code block, allowing you to invoke a `@JobScope` bean with a `JobExecution` prepared by the test itself.

## 1. Why Are `@JobScope` Beans Hard to Test Like Normal Beans?

A singleton bean is normally created and usable by Spring right after the application context initializes. In contrast, a `@JobScope` bean is bound to **a single job execution** (`JobExecution`). Spring resolves the actual target bean only when a corresponding job context exists.

For example, a processor needs to know which tenant is being processed:

```java
@Bean
@JobScope
PrefixingProcessor prefixingProcessor(
        @Value("#{jobParameters['tenant']}") String tenant) {
    return new PrefixingProcessor(tenant);
}
```

Here, `tenant` is taken from the parameters of **the current job run**. Spring usually injects a *scoped proxy* for the bean; the proxy can be injected into the test, but calling its methods without an active job scope will fail. Creating `JobParameters` alone or simply injecting the processor is not enough.

Distinguish three concepts:

| Concept | Role | Example |
| --- | --- | --- |
| `JobParameters` | Input parameters for a single job run | `tenant=north`, `date=2026-11-16` |
| `JobExecution` | Object representing a single job execution; holds job parameters and execution context | `processFiles` run with ID `101` |
| `JobExecution.getExecutionContext()` | Job-level state data, which can be updated during execution | `prefix=READY` |

`JobScopeTestUtils` uses `JobExecution` as the context source for resolving job-scoped beans.

## 2. Core API of `JobScopeTestUtils`

This class resides in package `org.springframework.batch.test` of the **`spring-batch-test`** dependency. The method used is:

```java
public static <T> T doInJobScope(
        JobExecution jobExecution,
        Callable<T> callable) throws Exception;
```

- `jobExecution`: simulated or test-prepared job execution; contains the job parameters and job execution context that the bean will read.
- `callable`: code block to execute while job scope is active. One or more methods of the `@JobScope` bean can be called inside the lambda.
- `T`: return type produced by `Callable`; for code that needs no return value, you can `return null`.
- `throws Exception`: errors thrown by `callable` can propagate to the test for JUnit to verify or report.

Conceptually, the execution flow is:

```text
Test creates JobParameters and JobExecution
                |
                v
JobScopeTestUtils.doInJobScope(jobExecution, callable)
                |
                v
Register JobContext for the thread running the test
                |
                v
Execute callable
  -> invoke scoped proxy
  -> create/look up target bean for JobExecution
  -> resolve jobParameters / jobExecutionContext
                |
                v
Finish callable -> clean up registered context
                |
                v
Return result or propagate exception
```

Key point: **the `@JobScope` bean must be invoked inside `callable`**. If called outside, the scope has either not opened yet or already closed.

## 3. Preparing Dependencies and Test Configuration

With Gradle, add Spring Batch test utilities to the test scope (assuming the project already has Spring Batch Core, Spring Test, and JUnit Jupiter managed via dependency management):

```groovy
dependencies {
    implementation 'org.springframework.batch:spring-batch-core'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testImplementation 'org.springframework:spring-test'
    testImplementation 'org.junit.jupiter:junit-jupiter'
}

test {
    useJUnitPlatform()
}
```

Use Spring Batch versions consistent with your project's Spring Framework and BOM/Spring Boot. You do not need a database, `JobRepository`, or `JobLauncher` **just to** test a `@JobScope` bean with `JobScopeTestUtils`.

The test still needs a Spring application context with `JobScope` registered. In a normal Batch application, Batch configuration handles this; in a minimal test-only context, you can register the `JobScope` bean directly as shown in the next example.

## 4. Complete Example: Testing an `ItemProcessor` Using Job Parameters and Job Execution Context

Scenario: a job processes invoices per tenant. The processor receives `tenant` from `jobParameters` and `prefix` from `jobExecutionContext`; processing an item concatenates the values into `prefix/tenant/item`.

The following example uses **Spring Batch 5.x**, **JUnit Jupiter**, and Spring Test. The entire code can be placed in `src/test/java/.../JobScopeTestUtilsExampleTest.java` (adjusting the package accordingly):

```java
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.configuration.annotation.JobScope;
import org.springframework.batch.core.scope.JobScope;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.test.JobScopeTestUtils;
import org.springframework.batch.test.MetaDataInstanceFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringJUnitConfig(JobScopeTestUtilsExampleTest.Config.class)
class JobScopeTestUtilsExampleTest {

    // Spring injects a scoped proxy; the target is resolved when job scope is active.
    @Autowired
    private PrefixingProcessor processor;

    @Test
    void processorReadsJobParametersAndJobExecutionContext() throws Exception {
        // 1. Prepare parameters for the job run.
        JobParameters parameters = new JobParametersBuilder()
                .addString("tenant", "north")
                .toJobParameters();

        // 2. Create a JobExecution for the test without launching a real job.
        JobExecution execution = MetaDataInstanceFactory.createJobExecution(
                "processFiles", 7L, 101L, parameters);
        execution.getExecutionContext().putString("prefix", "READY");

        // 3. Access the processor only within the job scope of the created execution.
        String result = JobScopeTestUtils.doInJobScope(
                execution,
                () -> processor.process("invoice-42"));

        // 4. Verify that late binding works properly.
        assertEquals("READY/north/invoice-42", result);
    }

    @Configuration
    static class Config {

        // Used for a minimal test context. In an app with full Batch config,
        // re-registering JobScope is usually unnecessary.
        @Bean
        static JobScope jobScope() {
            return new JobScope();
        }

        @Bean
        @JobScope
        PrefixingProcessor prefixingProcessor(
                @Value("#{jobParameters['tenant']}") String tenant,
                @Value("#{jobExecutionContext['prefix']}") String prefix) {
            return new PrefixingProcessor(tenant, prefix);
        }
    }

    public static class PrefixingProcessor implements ItemProcessor<String, String> {

        private final String tenant;
        private final String prefix;

        public PrefixingProcessor(String tenant, String prefix) {
            this.tenant = tenant;
            this.prefix = prefix;
        }

        @Override
        public String process(String item) {
            return prefix + "/" + tenant + "/" + item;
        }
    }
}
```

Analysis of key points:

1. `@SpringJUnitConfig` loads the Spring context for JUnit Jupiter, allowing the test to inject the `PrefixingProcessor` proxy.
2. `MetaDataInstanceFactory.createJobExecution(...)` creates test metadata; it does not persist or launch a job via a repository.
3. `execution.getExecutionContext().putString(...)` explicitly sets state that an earlier step might have written at the job level.
4. `JobScopeTestUtils.doInJobScope(...)` activates the job context for the lambda. Inside the lambda, the proxy resolves `@Value` to `north` and `READY`.
5. `assertEquals(...)` tests processing behavior **along with** late binding pulling from the right data sources.

If `processor.process("invoice-42")` is called before or after `doInJobScope`, the proxy cannot find a matching job context and the test may fail with an inactive-scope error.

## 5. Testing Two Job Runs with Different Parameters

A major benefit of `@JobScope` is that a single scoped proxy injected into a test can point to **two different targets** when using two different `JobExecution` objects. The example below can be added as a test method inside the class in Section 4:

```java
@Test
void eachJobExecutionGetsItsOwnScopedValues() throws Exception {
    JobParameters firstParams = new JobParametersBuilder()
            .addString("tenant", "north")
            .toJobParameters();
    JobExecution first = MetaDataInstanceFactory.createJobExecution(
            "processFiles", 7L, 101L, firstParams);
    first.getExecutionContext().putString("prefix", "FIRST");

    JobParameters secondParams = new JobParametersBuilder()
            .addString("tenant", "south")
            .toJobParameters();
    JobExecution second = MetaDataInstanceFactory.createJobExecution(
            "processFiles", 8L, 102L, secondParams);
    second.getExecutionContext().putString("prefix", "SECOND");

    String firstValue = JobScopeTestUtils.doInJobScope(
            first, () -> processor.process("x"));
    String secondValue = JobScopeTestUtils.doInJobScope(
            second, () -> processor.process("x"));

    assertEquals("FIRST/north/x", firstValue);
    assertEquals("SECOND/south/x", secondValue);
}
```

Across both invocations, the processor code remains unchanged. Input values are resolved according to the `JobExecution` provided by the test. This is useful for exercising multiple tenants, processing dates, feature flags, and different job context scenarios without running the entire pipeline.

## 6. When to Use `JobScopeTestUtils` vs. Other Approaches?

| Tool / Approach | Scope | Choose When |
| --- | --- | --- |
| `JobScopeTestUtils.doInJobScope(...)` | A specific code block within a test | You need direct control over `JobExecution` and when the scope opens to test `@JobScope` beans |
| `JobScopeTestExecutionListener` | Lifecycle of each test method in Spring TestContext | You want the framework to prepare job scope automatically per test method; can supply `JobExecution` via test factory/field |
| `@SpringBatchTest` | Spring Batch test infrastructure; integrates scope listeners and version-appropriate test utilities | Testing multiple Batch components and wanting convenient annotation-based setup |
| `StepScopeTestUtils.doInStepScope(...)` | `StepExecution` scope | Bean carries `@StepScope`, requiring `stepExecutionContext` or step-level metadata |
| Running job via test launcher/operator utility | An actual job or step execution | Verifying flow, transactions, reader/writer, job/step status, and multi-component integration |

`@JobScope` and `@StepScope` differ in lifecycle and the data they manage. **`JobScopeTestUtils` does not replace `StepScopeTestUtils`**: if a bean needs an active `StepExecution`, use the step-level utility or an appropriate step execution test.

`JobScopeTestExecutionListener` is typically registered when using `@SpringBatchTest`. With `JobScopeTestUtils`, the test explicitly chooses which block needs scope; this can be helpful in a test that only wants to enable scope for a single call.

## 7. Common Errors and How to Handle Them

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `ScopeNotActiveException`, `IllegalStateException`, or no job context message | Calling a method on the scoped proxy outside `doInJobScope` | Move the call that actually accesses the bean inside the lambda |
| `No Scope registered for scope name 'job'` | Spring context has not registered `JobScope` | Enable appropriate Spring Batch configuration or declare `JobScope` for minimal test context |
| `@Value("#{jobParameters['...']}")` resolves to `null` | Missing matching key/parameter on the passed `JobExecution` | Build `JobParameters` first and attach them to the exact `JobExecution` used for testing |
| `jobExecutionContext` value is not as expected | Data placed in `StepExecutionContext` or wrong `JobExecution` | Use `execution.getExecutionContext()` of the job under test |
| `@StepScope` bean still reports no step scope | Opening job scope does not automatically create step scope | Use `StepScopeTestUtils` and an appropriate `StepExecution` |
| Attempting to call bean from another thread inside lambda loses scope | Job context is bound to the executing thread; not propagated to new threads | Run the tested block on the same thread, or set up valid context per worker thread in concurrency tests |

Practices that make tests more meaningful:

- Create a separate `JobExecution` per scenario; set up full job parameters and execution context right inside the test for readability.
- Test only the observable behavior: output data, resolved parameters, or calls to mocked dependencies. `doInJobScope` does not verify that an actual job completes successfully.
- Keep the processor/service under test independent of database infrastructure when the goal is simply verifying late binding or business logic.
- Do not retain a reference to the **target** of a scoped bean to use after job scope ends. You may retain the Spring-injected proxy, but only invoke it when a valid context exists.
- If the lambda throws an exception, let the test verify that exception; the utility manages its scope block rather than having the test manually register context without cleanup.

## 8. Version Coverage and References

The method `JobScopeTestUtils.doInJobScope(JobExecution, Callable<T>)` is present in both Spring Batch 5.x and 6.x API documentation. The full code example above uses **Spring Batch 5.x** imports; when migrating to **Spring Batch 6.x**, cross-check the reorganized packages—for instance, `JobExecution` belongs to `org.springframework.batch.core.job` and job parameter classes belong to `org.springframework.batch.core.job.parameters`. The testing pattern with `doInJobScope` remains the same.

- [API `JobScopeTestUtils` — Spring Batch 5.2.x](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/test/JobScopeTestUtils.html)
- [API `JobScopeTestUtils` — Spring Batch 6.x](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/test/JobScopeTestUtils.html)
- [API `MetaDataInstanceFactory` — creating test metadata](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/test/MetaDataInstanceFactory.html)
- [API `JobScope` — declaring job-scoped beans](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/core/configuration/annotation/JobScope.html)
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html)

When needing to directly test a `@JobScope` reader, processor, writer, or service, prepare a `JobExecution` carrying the required values, invoke the bean inside `JobScopeTestUtils.doInJobScope(...)`, and verify the result. This approach focuses on the behavior of the component under test and reproduces runtime job-level data accurately without running the entire batch execution pipeline.
