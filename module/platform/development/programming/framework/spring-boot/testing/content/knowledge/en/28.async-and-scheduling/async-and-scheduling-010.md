# Testing Spring Batch Jobs, Steps, and Parameters When Used by the Application

## 1. The problem: Spring Batch is not just calling a function and asserting

When a Spring Boot application uses **Spring Batch** to import data, aggregate reports, export files, reconcile records, or run scheduled work, testing differs significantly from a regular service method. A `Job` can contain multiple `Step`s, each step has its own transaction, every run is recorded in `JobRepository`, and reruns depend on **`JobParameters`**.

Real-world bugs a test suite must catch include:

- As soon as the app boots for testing, Spring Boot **automatically runs the job** before the test prepares data.
- A test invokes a single `Step` yet accidentally runs the whole `Job`, causing unwanted side effects.
- `@StepScope` tries to read `jobParameters` when the application context has no `StepExecution`, causing SpEL/scope errors.
- Rerunning a job with the same identifying parameters after it is `COMPLETED` throws `JobInstanceAlreadyCompleteException`.
- Unconditionally adding a timestamp/random parameter prevents the test from verifying restart behavior.
- Checking `BatchStatus.COMPLETED` while ignoring outputs, `StepExecution`, read/write/skip counts, or business data.
- A job fails yet the test only asserts no exception was thrown; `JobLauncher` can return a `JobExecution` with status `FAILED` instead of throwing the step's error directly.
- `@Transactional` on a test method does not automatically roll back transactions committed by batch steps on a different thread/transaction boundary.
- A test reads status `STARTING` when the job launcher is asynchronous and wrongly concludes the job failed.
- Multiple tests reuse the same metadata database, job name, and identifying parameters, creating order-dependent outcomes.

This lesson in the **Async and Scheduling** group focuses specifically on **"Testing Spring Batch jobs, steps, and parameters when used by the application"**. We build a **Java 17+ / Spring Boot 3.3.5 / Spring Batch 5.1.x** project with two steps, identifying parameter `batchId`, non-identifying parameter `attempt`, `@StepScope`, an H2 `JobRepository`, and tests using `@SpringBatchTest`.

**Conditional scope:** apply the techniques below only when the application actually uses Spring Batch. If a project only uses `@Async`, `@Scheduled`, or a thread executor without Batch `Job`/`Step`, do not add `spring-batch-test` just to test schedules.

### Learning outcomes

1. Understand `Job`, `JobInstance`, `JobExecution`, `Step`, `StepExecution`, `JobParameters`, `ExecutionContext`, `BatchStatus`, and `ExitStatus`.
2. Disable auto-launch in tests with `spring.batch.job.enabled=false`, avoiding turning every test run into a batch run.
3. Declare jobs/steps in Spring Batch 5 style using `new JobBuilder(name, jobRepository)` and `new StepBuilder(name, jobRepository)`, along with `PlatformTransactionManager` for tasklets.
4. Use `@SpringBatchTest`, `JobLauncherTestUtils.launchJob(params)`, and `launchStep(name, params)`.
5. Test full flows, individual steps, required/identifying parameters, step-scope late binding, and execution statuses.
6. Distinguish a job returning `FAILED` from a job launcher throwing an exception.
7. Avoid mistaking `launchStep` for a full job, and avoid trusting metadata rollback when steps already committed side effects.
8. Know when to use `JobRepositoryTestUtils`, `StepScopeTestUtils`, or chunk/item reader/writer-level tests.
9. Separate testing job business logic from testing schedulers and real asynchronous launchers.

## 2. Execution model: Job → Instance → Execution → StepExecution

```text
Job: exportReportJob (fixed definition)
   |
   +-- JobInstance A
   |     identifying JobParameters: batchId = "BATCH-A"
   |        |
   |        +-- JobExecution #1 (COMPLETED or FAILED)
   |        |      |
   |        |      +-- StepExecution collectStep
   |        |      +-- StepExecution publishStep
   |        |
   |        +-- JobExecution #2 (only on valid restart)
   |
   +-- JobInstance B
         identifying JobParameters: batchId = "BATCH-B"
            |
            +-- JobExecution #3
                   |
                   +-- StepExecution collectStep
                   +-- StepExecution publishStep
```

- **`Job`** is the flow definition, e.g., `exportReportJob` consisting of `collectStep` followed by `publishStep`.
- **`JobInstance`** is identified by **job name + the set of `JobParameters` with `identifying=true`**. It represents the identity of one logical run, not simply each click of a run button.
- **`JobExecution`** is one execution attempt of an instance; one `JobInstance` can have multiple executions when restarted after `FAILED`/`STOPPED`.
- **`Step`** is the definition of one processing phase.
- **`StepExecution`** stores the outcome of one step within an execution, including status, exit status, counters, execution context, and timestamps.
- **`JobParameters`** is a typed parameter set carrying an `identifying` flag.
- **`ExecutionContext`** is checkpoint/recovery state inside batch metadata; exists at both job level and step level.
- **`BatchStatus`** reflects lifecycle status: `STARTING`, `STARTED`, `COMPLETED`, `FAILED`, `STOPPED`...
- **`ExitStatus`** is a result code driving flow transitions: `COMPLETED`, `FAILED`, custom codes, or descriptions.

### Example of same instance vs different instance

```java
JobParameters first = new JobParametersBuilder()
        .addString("batchId", "BATCH-2026-01", true)
        .addLong("attempt", 1L, false)
        .toJobParameters();

JobParameters retryMetadataChanged = new JobParametersBuilder()
        .addString("batchId", "BATCH-2026-01", true)
        .addLong("attempt", 2L, false)
        .toJobParameters();

JobParameters anotherInstance = new JobParametersBuilder()
        .addString("batchId", "BATCH-2026-02", true)
        .addLong("attempt", 1L, false)
        .toJobParameters();
```

This is a **snippet**, using imports `org.springframework.batch.core.JobParameters` and `JobParametersBuilder`; full project code follows in later sections. The first two objects have **the same identifying set**, so they identify the same `JobInstance` even though `attempt` changed. The third object has a new `batchId`, creating a different `JobInstance`.

**Note:** adding a `run.id`/timestamp parameter with `identifying=true` on every launch **always creates a new instance**; that helps when wanting a fresh run, yet hides restart behavior if a test needs to re-run the same instance.

## 3. Choosing the right test level for each responsibility

| Test level | What runs? | Tools/assertions needed |
| --- | --- | --- |
| Business rule unit test | Service or processor without Spring Batch | JUnit + Mockito, no Batch context needed |
| Individual reader/processor/writer | One component, possibly needing step scope | Spring test + `StepScopeTestUtils`, test fixtures |
| **Single Step** | Only one step with `JobRepository` metadata | `JobLauncherTestUtils.launchStep(...)`; assert `StepExecution` + side effects |
| **Full Job** | Flow across all steps, transitions, job parameters | `launchJob(...)`; assert `JobExecution`/step statuses and business output |
| Restart test | Same `JobInstance` after failure, step skip/retry | `JobRepository` on test DB + controlled failure |
| Full integration | Batch job with DB/file/API/message infrastructure | `@SpringBootTest` + DB/Testcontainers/file fixtures |
| Scheduler integration | Who launches the job and when | Test `@Scheduled`/Quartz/controller separately, mock job launcher when needed |
| Performance/volume | Chunk size, commits, throughput, memory | Large datasets and metrics; does not replace unit tests |

A balanced strategy usually has many cheap unit tests for processors/validation, a few step tests for I/O, and a handful of job-level tests verifying the flow. You do not need `@SpringBootTest` with an H2 database for simple arithmetic inside an `ItemProcessor`.

## 4. Core annotations and APIs

```java
@SpringBootTest
@SpringBatchTest
@ActiveProfiles("test")
class ExportBatchJobTest {
    @Autowired JobLauncherTestUtils jobs;
}
```

This is a **structural snippet**; the full example is in Section 13.

- `@SpringBootTest` loads the Boot application context containing the job, steps, repository, and dependencies.
- `@SpringBatchTest` from `spring-batch-test` registers `JobLauncherTestUtils`, `JobRepositoryTestUtils`, and listeners supporting step/job scope.
- `JobLauncherTestUtils.launchJob(parameters)` runs the entire job.
- `JobLauncherTestUtils.launchStep(stepName, parameters)` runs **only a single step** inside a surrogate single-step job created by the test utility.
- `JobRepositoryTestUtils.removeJobExecutions()` cleans **Spring Batch metadata executions/instances** in the test DB when needed; it does not clean business tables or file/message side effects.
- `StepScopeTestUtils.doInStepScope(...)` activates step context when unit-testing a component needing late binding.

Spring Batch 5.1 docs state that if there is **one** `Job` in the context, `JobLauncherTestUtils` picks it up automatically; if multiple jobs exist, you must explicitly select the job under test rather than risking bean ambiguity.

## 5. Spring Boot auto-configuration and common test pitfalls

With `spring-boot-starter-batch`, Spring Boot auto-configures a JDBC-backed `JobRepository`, `JobLauncher`, batch scopes, and required beans.

**By default, if a `Job` bean exists, Boot normally launches it automatically at startup.** That makes sense for a command-line batch app, but is wrong for integration tests that must prepare fixtures and job parameters first.

In the test profile, configure:

```yaml
spring:
  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: always
```

- `spring.batch.job.enabled=false` turns off **Boot's startup job runner**; it does not stop tests from explicitly calling `launchJob` or schedulers/services from calling `JobLauncher`.
- `spring.batch.jdbc.initialize-schema=always` tells Boot to initialize **BATCH_JOB_INSTANCE**, **BATCH_JOB_EXECUTION**, **BATCH_STEP_EXECUTION**, etc. from Spring Batch scripts on the H2 test database.
- Metadata schema is distinct from business schema; having batch metadata does not mean application data tables were created.
- H2 is a test DB; production running PostgreSQL/MySQL/... typically uses migrations to manage official schemas and vendor-compatible batch metadata.

### Should you add `@EnableBatchProcessing`?

**Do not add `@EnableBatchProcessing` to the example project.** In Spring Boot 3.3, explicitly adding `@EnableBatchProcessing` or extending `DefaultBatchConfiguration` causes Boot's Batch auto-configuration to **back off**, changing how `JobRepository` and JDBC schema initialization are configured. Only use it when you truly intend to own the entire Batch infrastructure and know which beans to supply.

Also avoid following very old tutorials using `JobBuilderFactory` or `StepBuilderFactory` without checking Spring Batch 5.1. The examples below use modern constructors accepting `JobRepository` and `PlatformTransactionManager`.

## 6. Runnable sample project with Java 17+

To stay focused on Job/Step/Parameters, we use **two `TaskletStep`s** rather than a complex CSV/DB job. A thread-safe `JobProbe` records step order **solely for observation in tests/demos**; Spring Batch metadata is genuinely persisted in H2. Writing to `JobProbe` is **non-transactional**, so it is not a production transactional business writer.

Project structure:

```text
batch-job-testing-lab/
├── settings.gradle
├── build.gradle
├── src/main/java/com/example/batch/
│   ├── BatchLabApplication.java
│   ├── JobProbe.java
│   ├── CollectTasklet.java
│   ├── PublishTasklet.java
│   └── ExportJobConfiguration.java
└── src/test/
    ├── java/com/example/batch/
    │   └── ExportBatchJobTest.java
    └── resources/
        └── application-test.yml
```

The project uses `spring-boot-starter-batch`, `spring-batch-test`, and H2; no REST controllers, Docker, external brokers, or input files. Package and file names are consistent throughout.

### 6.1. settings.gradle

```groovy
rootProject.name = 'batch-job-testing-lab'
```

### 6.2. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
```

**Explanation:**

- `spring-boot-starter-batch`: Spring Batch runtime, Boot autoconfiguration, JDBC infrastructure.
- `com.h2database:h2`: in-memory JDBC database holding Spring Batch metadata; `runtimeOnly` suffices for Boot tests/runtime.
- `spring-boot-starter-test`: JUnit Jupiter and Spring TestContext.
- `spring-batch-test`: `@SpringBatchTest`, `JobLauncherTestUtils`, `JobRepositoryTestUtils`, `StepScopeTestUtils`.
- `junit-platform-launcher`: supports Gradle running JUnit Platform.

**If the project has no Gradle Wrapper yet**, `./gradlew` will not exist. Use a compatible installed `gradle test` or generate the wrapper per team workflow before running the sample commands.

## 7. Boot application root

`src/main/java/com/example/batch/BatchLabApplication.java`:

```java
package com.example.batch;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BatchLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(BatchLabApplication.class, args);
    }
}
```

`@SpringBootApplication` sits in the parent package so component scanning finds `JobProbe`, both Tasklet classes, and `ExportJobConfiguration`. There is no `@EnableBatchProcessing`: Boot 3.3 auto-configures Batch infrastructure.

When running the application outside tests, supply an appropriate `DataSource`, batch schema, and job parameters. This example **only backs the H2 test profile scenario**; do not claim an unconfigured `bootRun` is a valid production batch deployment.

## 8. JobProbe: recording which steps ran

`src/main/java/com/example/batch/JobProbe.java`:

```java
package com.example.batch;

import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.stereotype.Component;

@Component
public class JobProbe {

    private final Map<String, List<String>> stages =
            new ConcurrentHashMap<>();

    public void record(String batchId, String stage) {
        stages.computeIfAbsent(
                batchId,
                key -> new CopyOnWriteArrayList<>()
        ).add(stage);
    }

    public List<String> stagesFor(String batchId) {
        List<String> stored = stages.get(batchId);
        return stored == null ? List.of() : List.copyOf(stored);
    }

    public void clear() {
        stages.clear();
    }
}
```

This is a simple **in-memory observation probe**, not a transactional database resource, production file writer, or message publisher. It helps tests prove:

- Running the **full Job** → observes both stages in order: `collect` then `publish`.
- Running **`collectStep`** alone → only stage `collect`.
- Running **`publishStep`** alone → only stage `publish`.
- With distinct `batchId`s, results are isolated by key.

`ConcurrentHashMap` and `CopyOnWriteArrayList` prevent simple data races when components execute on different threads. However, `probe.clear()` in the test still assumes test methods do not run in parallel on the same context; if enabling JUnit parallelism, isolate by test/job ID or separate application contexts.

**Important warning:** A Tasklet could record into `JobProbe` and then fail; Spring Batch's transaction rollback does not undo `CopyOnWriteArrayList.add`. Never treat the probe as proof of database rollback or exactly-once behavior. In production, verify real side effects (JDBC, S3, Kafka...) in dedicated tests.

## 9. CollectTasklet: @StepScope reading JobParameters at step execution

`src/main/java/com/example/batch/CollectTasklet.java`:

```java
package com.example.batch;

import org.springframework.batch.core.StepContribution;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.scope.context.ChunkContext;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
@StepScope
public class CollectTasklet implements Tasklet {

    private final String batchId;
    private final JobProbe probe;

    public CollectTasklet(
            @Value("#{jobParameters['batchId']}") String batchId,
            JobProbe probe) {
        this.batchId = batchId;
        this.probe = probe;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        if (batchId == null || batchId.isBlank()) {
            throw new IllegalArgumentException(
                    "batchId is required");
        }

        probe.record(batchId, "collect");

        contribution.getStepExecution()
                .getExecutionContext()
                .putString("observedBatchId", batchId);

        return RepeatStatus.FINISHED;
    }
}
```

### Deep explanation

`@StepScope` binds bean creation to the **`StepExecution`** lifecycle instead of application context startup. That allows Spring Expression Language to resolve `jobParameters['batchId']` when the job actually runs.

If you omit `@StepScope` while injecting `@Value("#{jobParameters['batchId']}")` into a singleton, Spring has no active `StepContext` at bean initialization and normally fails with a scope/expression error. **The `Step` itself does not need and should not be marked `@StepScope`** in this example; only components needing parameters need that scope.

`RepeatStatus.FINISHED` tells `TaskletStep` the Tasklet is done and should not be called again. Returning `CONTINUABLE` without a termination condition would loop the step repeatedly.

`StepExecution.getExecutionContext().putString(...)` stores the observed parameter value in the **step execution context**. Tests verify not only the probe stage, but also that the **late-bound parameter** reached the right step. When persisted, this context becomes Spring Batch metadata; real jobs should store serializable values with a valid checkpoint strategy.

### Distinguishing jobParameters from application.properties

`batchId` is a **per-run job parameter** (`JobParameters`), not an environment property like `app.batch.batch-id` from Spring `Environment`. Real systems configure datasources and feature flags in application config, while run-specific inputs pass through `JobParameters` governed by identifying/nonidentifying policies.

## 10. PublishTasklet: reading parameters from StepExecution

`src/main/java/com/example/batch/PublishTasklet.java`:

```java
package com.example.batch;

import org.springframework.batch.core.StepContribution;
import org.springframework.batch.core.scope.context.ChunkContext;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.stereotype.Component;

@Component
public class PublishTasklet implements Tasklet {

    private final JobProbe probe;

    public PublishTasklet(JobProbe probe) {
        this.probe = probe;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        String batchId = contribution
                .getStepExecution()
                .getJobExecution()
                .getJobParameters()
                .getString("batchId");

        if (batchId == null || batchId.isBlank()) {
            throw new IllegalArgumentException(
                    "batchId is required");
        }

        probe.record(batchId, "publish");
        return RepeatStatus.FINISHED;
    }
}
```

`PublishTasklet` does not need `@StepScope`: it requires no constructor-time late binding. During step execution, `StepContribution` exposes `StepExecution` and the current execution's job parameters. Both approaches are valid and illustrate when a scoped component is genuinely needed.

Do not slap `@JobScope` on every bean simply because a class has "job" in its name. Use job scope only when you want one instance per job execution and need late binding at that level; be especially careful with multi-threaded or partitioned steps.

## 11. Job and Step definitions in Spring Batch 5 style

`src/main/java/com/example/batch/ExportJobConfiguration.java`:

```java
package com.example.batch;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobParametersInvalidException;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration(proxyBeanMethods = false)
public class ExportJobConfiguration {

    @Bean("collectStep")
    Step collectStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            CollectTasklet tasklet) {

        return new StepBuilder("collectStep", jobRepository)
                .tasklet(tasklet, transactionManager)
                .build();
    }

    @Bean("publishStep")
    Step publishStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            PublishTasklet tasklet) {

        return new StepBuilder("publishStep", jobRepository)
                .tasklet(tasklet, transactionManager)
                .build();
    }

    @Bean("exportReportJob")
    Job exportReportJob(
            JobRepository jobRepository,
            @Qualifier("collectStep") Step collectStep,
            @Qualifier("publishStep") Step publishStep) {

        return new JobBuilder("exportReportJob", jobRepository)
                .validator(parameters -> {
                    String batchId =
                            parameters.getString("batchId");

                    if (batchId == null || batchId.isBlank()) {
                        throw new JobParametersInvalidException(
                                "batchId is required");
                    }
                })
                .start(collectStep)
                .next(publishStep)
                .build();
    }
}
```

### Important syntax and bean wiring notes

- `JobBuilder("exportReportJob", jobRepository)` and `StepBuilder("collectStep", jobRepository)` follow the Spring Batch **5.1** API style.
- `.tasklet(tasklet, transactionManager)` supplies the transaction manager to `TaskletStep`.
- `.start(collectStep).next(publishStep)` defines sequential flow; if `collectStep` fails without special transitions, the job normally skips `publishStep`.
- `.validator(...)` attaches a **Job-level `JobParametersValidator`**: requires non-null/non-blank `batchId` before full job launch.
- `@Qualifier` ensures the job receives the exact `Step` beans rather than relying on autowire ordering when two beans of type `Step` exist.
- `@Configuration(proxyBeanMethods=false)` fits because the config does not invoke its own `@Bean` methods directly.
- Only **one `Job` bean** is declared, allowing `JobLauncherTestUtils` to autowire the job under test automatically.

**Note:** `launchStep(...)` creates a **surrogate test job**, bypassing `exportReportJob`'s Job-level validator. Therefore both Tasklets also validate `batchId` before causing side effects. Never assume a `launchStep` test proved the full job's `JobParametersValidator`.

### Tasklets and transaction boundaries

Spring Batch's `TaskletStep` invokes `Tasklet.execute(...)` inside a step-managed transaction. For JDBC business writes, DB transactions roll back if an error occurs before commit and the DataSource/transaction manager are wired properly. However, `JobProbe`, file I/O, external APIs, and message publishing **are not automatically rolled back** by a JDBC transaction.

If a real app has two DataSources (`JobRepository` metadata vs business database), configure `@BatchDataSource`, `@BatchTransactionManager`, or equivalent wiring explicitly; never assume the repository transaction covers the business DB.

## 12. Test-only H2 configuration

`src/test/resources/application-test.yml`:

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:batch_lab;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: always
```

Add `@ActiveProfiles("test")` on the test class so this file is loaded.

### Why use a named in-memory DB?

`jdbc:h2:mem:batch_lab;DB_CLOSE_DELAY=-1` keeps the H2 database alive in the JVM when connections close and reopen, preserving `JobRepository` metadata across repository calls in the test context. Never share this H2 config with production; production must use an appropriate datasource and migrations.

### Common metadata tables

```text
BATCH_JOB_INSTANCE
BATCH_JOB_EXECUTION
BATCH_JOB_EXECUTION_PARAMS
BATCH_STEP_EXECUTION
BATCH_JOB_EXECUTION_CONTEXT
BATCH_STEP_EXECUTION_CONTEXT
BATCH_JOB_SEQ
BATCH_JOB_EXECUTION_SEQ
BATCH_STEP_EXECUTION_SEQ
```

Exact names/schemas vary by vendor and Spring Batch version; the point here is seeing that **`JobRepository` persists history**. Do not manually edit metadata tables to force a `JobInstance` restart; use `JobRepository`/`JobOperator` APIs and your system's migration policies.

### Why prevent the job from auto-running on context load?

With `spring.batch.job.enabled=false`, Boot does not launch `exportReportJob` via its startup runner; tests explicitly call `launchJob(params)`. Forgetting that flag causes application startup to try running the job **without `batchId`**, getting rejected by `JobParametersValidator` and failing the test context before any test method runs.

**Do not abuse `@EnableBatchProcessing` to "fix" auto-launch**: it changes auto-config behavior; `spring.batch.job.enabled=false` is the proper mechanism here.

## 13. Runnable test class: @SpringBatchTest and JobLauncherTestUtils

`src/test/java/com/example/batch/ExportBatchJobTest.java`:

```java
package com.example.batch;

import java.util.List;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.JobParametersInvalidException;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.repository.JobInstanceAlreadyCompleteException;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@SpringBatchTest
@ActiveProfiles("test")
class ExportBatchJobTest {

    @Autowired
    JobLauncherTestUtils jobs;

    @Autowired
    JobProbe probe;

    @BeforeEach
    void resetProbe() {
        probe.clear();
    }

    private JobParameters params(String batchId, long attempt) {
        return new JobParametersBuilder()
                .addString("batchId", batchId, true)
                .addLong("attempt", attempt, false)
                .toJobParameters();
    }

    private String freshBatchId(String suffix) {
        return suffix + "-" + UUID.randomUUID();
    }

    @Test
    void wholeJobRunsBothStepsInOrder() throws Exception {
        String id = freshBatchId("whole");

        JobExecution execution =
                jobs.launchJob(params(id, 1L));

        assertEquals(BatchStatus.COMPLETED,
                execution.getStatus());
        assertEquals(ExitStatus.COMPLETED.getExitCode(),
                execution.getExitStatus().getExitCode());
        assertEquals("exportReportJob",
                execution.getJobInstance().getJobName());
        assertEquals(id,
                execution.getJobParameters().getString("batchId"));

        Set<String> stepNames = execution.getStepExecutions()
                .stream()
                .map(StepExecution::getStepName)
                .collect(Collectors.toSet());

        assertEquals(
                Set.of("collectStep", "publishStep"),
                stepNames);

        assertTrue(execution.getStepExecutions().stream()
                .allMatch(step ->
                        step.getStatus() == BatchStatus.COMPLETED));

        assertEquals(
                List.of("collect", "publish"),
                probe.stagesFor(id));
    }

    @Test
    void launchCollectStepDoesNotRunPublishStep()
            throws Exception {
        String id = freshBatchId("collect-only");

        JobExecution execution =
                jobs.launchStep("collectStep", params(id, 1L));

        assertEquals(BatchStatus.COMPLETED,
                execution.getStatus());
        assertEquals(1, execution.getStepExecutions().size());
        assertEquals(
                "collectStep",
                execution.getStepExecutions().iterator()
                        .next().getStepName());
        assertEquals(
                List.of("collect"),
                probe.stagesFor(id));
    }

    @Test
    void launchPublishStepDoesNotRunCollectStep()
            throws Exception {
        String id = freshBatchId("publish-only");

        JobExecution execution =
                jobs.launchStep("publishStep", params(id, 1L));

        assertEquals(BatchStatus.COMPLETED,
                execution.getStatus());
        assertEquals(1, execution.getStepExecutions().size());
        assertEquals(
                "publishStep",
                execution.getStepExecutions().iterator()
                        .next().getStepName());
        assertEquals(
                List.of("publish"),
                probe.stagesFor(id));
    }

    @Test
    void stepScopeReadsTheCurrentJobParameter()
            throws Exception {
        String id = freshBatchId("scoped");

        JobExecution execution =
                jobs.launchStep("collectStep", params(id, 1L));

        StepExecution step = execution.getStepExecutions()
                .iterator().next();

        assertEquals(BatchStatus.COMPLETED, step.getStatus());
        assertEquals(
                id,
                step.getExecutionContext()
                        .getString("observedBatchId"));
        assertEquals(
                List.of("collect"),
                probe.stagesFor(id));
    }

    @Test
    void completedInstanceRejectsRerunWithOnlyNoteChanged()
            throws Exception {
        String id = freshBatchId("same-instance");

        JobExecution first = jobs.launchJob(params(id, 1L));
        assertEquals(BatchStatus.COMPLETED, first.getStatus());

        assertThrows(
                JobInstanceAlreadyCompleteException.class,
                () -> jobs.launchJob(params(id, 2L)));

        assertEquals(
                List.of("collect", "publish"),
                probe.stagesFor(id));
    }

    @Test
    void changedIdentifyingBatchIdCreatesNewInstance()
            throws Exception {
        String firstId = freshBatchId("run-A");
        String secondId = freshBatchId("run-B");

        JobExecution first =
                jobs.launchJob(params(firstId, 1L));
        JobExecution second =
                jobs.launchJob(params(secondId, 1L));

        assertEquals(BatchStatus.COMPLETED, first.getStatus());
        assertEquals(BatchStatus.COMPLETED, second.getStatus());
        assertNotEquals(
                first.getJobInstance().getInstanceId(),
                second.getJobInstance().getInstanceId());
        assertEquals(
                List.of("collect", "publish"),
                probe.stagesFor(firstId));
        assertEquals(
                List.of("collect", "publish"),
                probe.stagesFor(secondId));
    }

    @Test
    void jobValidatorRejectsMissingBatchId() {
        JobParameters missing = new JobParametersBuilder()
                .addLong("attempt", 1L, false)
                .toJobParameters();

        assertThrows(
                JobParametersInvalidException.class,
                () -> jobs.launchJob(missing));
    }

    @Test
    void launchStepRejectsUnknownStepName() {
        String id = freshBatchId("unknown-step");

        assertThrows(
                IllegalStateException.class,
                () -> jobs.launchStep(
                        "noSuchStep", params(id, 1L)));
    }

    @Test
    void parametersExposeTheirIdentifyingFlags() {
        JobParameters parameters =
                params("fixed-business-key", 77L);

        assertTrue(
                parameters.getParameters().get("batchId")
                        .isIdentifying());
        assertFalse(
                parameters.getParameters().get("attempt")
                        .isIdentifying());
        assertEquals(
                "fixed-business-key",
                parameters.getString("batchId"));
        assertEquals(
                77L,
                parameters.getLong("attempt"));
    }
}
```

**This class has 9 `@Test` methods.** `@BeforeEach` is setup, not counted as a test. `UUID` suffixes are used **only to keep test `JobInstance`s unique** when sharing H2 metadata, never to randomize expected business outcomes.

To reiterate the boundary: these methods are sample code **designed to run** with matching dependencies/config; no actual Gradle execution report is included in this lesson. When practicing, run the suite and verify reports rather than assuming "9 PASS" just because 9 annotations exist in source.

## 14. Reading job test results properly

The `wholeJobRunsBothStepsInOrder` test asserts **four layers of outcomes**:

1. **Lifecycle status**: `JobExecution.getStatus() == BatchStatus.COMPLETED`.
2. **Exit code**: `getExitStatus().getExitCode()` is `COMPLETED`.
3. **Flow structure**: two `StepExecution`s named `collectStep` and `publishStep`, both completed.
4. **Outcome**: probe observed the exact order `collect` → `publish` for the current `batchId`.

Calling only:

```java
assertEquals(BatchStatus.COMPLETED, execution.getStatus());
```

is necessary but insufficient. A Tasklet could return `FINISHED` without writing any file or DB row; when business behavior requires output, the test must assert that output. The sample uses `JobProbe` to illustrate this, not to replace checking business tables/CSVs/S3 in real projects.

### StepExecution and read/write counts

`StepExecution` provides counters `getReadCount()`, `getWriteCount()`, `getReadSkipCount()`, `getProcessSkipCount()`, `getWriteSkipCount()`, `getCommitCount()`, and `getRollbackCount()`, depending on step type.

**With the demo `TaskletStep` that uses no chunk reader/writer**, do not assert `readCount=10` or `writeCount=10` because there is no item-level processing. For chunk-oriented jobs, counters are very useful, e.g.:

```java
StepExecution step = execution.getStepExecutions()
        .stream()
        .filter(s -> "importCsvStep".equals(s.getStepName()))
        .findFirst()
        .orElseThrow();

assertEquals(10, step.getReadCount());
assertEquals(9, step.getWriteCount());
assertEquals(1, step.getProcessSkipCount());
```

This is a **snippet for another chunk job**, not part of the runnable demo. It only holds if the real job fixture has 10 input rows, 1 skipped item, and 9 written items under a matching skip policy. Never fabricate counters for the Tasklet demo output.

## 15. launchJob and launchStep are not the same

| API | Job being executed | Steps | Job-level validator/flow? |
| --- | --- | --- | --- |
| `jobs.launchJob(params)` | Real `exportReportJob` | Collect then Publish | **Yes** |
| `jobs.launchStep("collectStep", params)` | Single-step **surrogate job** from Spring Batch test utility | Only Collect | **Does not run full job validator/flow** |
| `jobs.launchStep("publishStep", params)` | Single-step surrogate job | Only Publish | Does not run Collect |
| `jobs.launchStep("missing", params)` | Step not found | Does not run | Throws `IllegalStateException` |

In the demo job, `PublishTasklet` does not depend on Collect's output, so `publishStep` can run standalone. In a real app where Publish depends on `jobExecutionContext` populated by Collect, standalone step tests must **set up that context** using `launchStep(stepName, params, jobExecutionContext)` or test the dependency at full-job level. Never run a step standalone and assert preconditions created by a previous step without simulating them.

**Metadata warning:** when using `launchStep`, `execution.getJobInstance().getJobName()` may be a temporary job name generated by `StepRunner`, **not `exportReportJob`**. Runnable tests assert step names and behavior, not the full job name inside step-only tests.

### Picking the right call for each situation

- Flow transitions, validators, ordering across steps → `launchJob`.
- Input/processing/output of one step preparable independently → `launchStep`.
- Custom step-scoped bean/reader without spinning up `JobRepository` → `StepScopeTestUtils` or test fixture scope.
- When a scheduler triggers a job → test scheduler logic separately instead of treating `launchJob` as a timing measurement.

## 16. @StepScope, JobParameters, and late binding

Spring Batch does not know `batchId` at application context startup. Therefore constructor injection:

```java
@Value("#{jobParameters['batchId']}")
String batchId
```

only makes sense when the bean is `@StepScope` (or appropriate job scope) and a `StepExecution` is active.

### Why should @StepScope not be placed on a Step bean?

A `Step` is part of the flow definition referenced by the `Job` graph at context startup. Late-bound data should go into **Tasklets, `ItemReader`s, `ItemProcessor`s, `ItemWriter`s**, or scoped collaborators, rather than arbitrarily turning the `Step` itself into a scoped proxy.

### Can you test @StepScope without running a job?

Yes. Spring Batch test provides:

- `StepScopeTestExecutionListener`: creates/manages a dummy `StepExecution` per test method.
- `StepScopeTestUtils.doInStepScope(stepExecution, callable)`: runs a block while step scope is bound.
- `MetaDataInstanceFactory.createStepExecution(params)`: builds a test execution with specified `JobParameters`.

Conceptual snippet example (not a file in the project):

```java
JobParameters params = new JobParametersBuilder()
        .addString("batchId", "SCOPE-EXAMPLE", true)
        .toJobParameters();

StepExecution mockStep =
        MetaDataInstanceFactory.createStepExecution(params);

String result = StepScopeTestUtils.doInStepScope(
        mockStep,
        () -> scopedReader.read());
```

This snippet assumes an injected `scopedReader` implementing `ItemReader<String>`. To run standalone, you need a concrete reader bean config, `@SpringBatchTest` or a test context with step-scope infrastructure, and imports: `org.springframework.batch.test.MetaDataInstanceFactory` and `StepScopeTestUtils`. Do not infer `read()` returns `"SCOPE-EXAMPLE"` without defining the reader implementation.

### Job scope in multi-threaded steps

`@JobScope` late-binds job-level parameters/context. However, Spring Batch docs warn about job-scoped beans in multi-threaded or partitioned steps because context does not automatically propagate to worker threads not fully managed by the framework. Clarify thread/partition ownership rather than copying a scoped bean setup from a single-thread demo.

## 17. JobParameters: identifying vs nonidentifying effects on restart

In the project:

```java
new JobParametersBuilder()
        .addString("batchId", "BATCH-001", true)
        .addLong("attempt", 1L, false)
        .toJobParameters();
```

Meaning:

- `batchId` is the business identity of a batch run, **`identifying=true`**.
- `attempt` is auxiliary metadata, **`identifying=false`**.
- Changing `attempt` from 1 to 2 does not change the `JobInstance`.
- Once a `JobInstance` is `COMPLETED`, relaunching with the same identifying params normally throws `JobInstanceAlreadyCompleteException`.
- Changing `batchId` creates a different `JobInstance` (keeping the job name), able to run from scratch.
- A failed instance can be restarted when the job is restartable and metadata/step state permits; this does not mean every failed job resumes seamlessly.

### Pitfall of misunderstanding job completion

If a job already completed and you want to "reprocess yesterday's data", changing only a nonidentifying `attempt` is **not enough** to create a new `JobInstance`. You need an explicit reprocessing policy: an identifying `runId`/revision parameter, a new job name/version, or a domain-specific replay mechanism. Conversely, when wanting to **restart from a checkpoint**, you must keep the **exact same identifying parameters**.

### Verifying with tests

`completedInstanceRejectsRerunWithOnlyNoteChanged` launches once successfully, then changes only nonidentifying `attempt` and expects the exception. `changedIdentifyingBatchIdCreatesNewInstance` changes `batchId` and checks that instance IDs differ.

**Do not call `jobs.getUniqueJobParameters()` in tests trying to verify same-instance restarts**: that utility generates random identifying parameters to avoid collisions, destroying the precondition. For simple fresh runs independent of parameters, it is handy; for job-identity semantics, construct parameters explicitly.

## 18. Job-level parameter validation vs step-level preconditions

`ExportJobConfiguration` attaches `.validator(...)` requiring a valid `batchId`. The test:

```java
JobParameters missing = new JobParametersBuilder()
        .addLong("attempt", 1L, false)
        .toJobParameters();

assertThrows(
        JobParametersInvalidException.class,
        () -> jobs.launchJob(missing));
```

shows that the **full `Job`** validates parameters before starting.

However, `launchStep("collectStep", params)` executes the step inside a surrogate test job without running the full Job-level validator. Hence `CollectTasklet` validates `batchId` itself before writing to the probe, and `PublishTasklet` does the same. Guarding at component boundaries helps even if a job is launched along a different branch.

### When should parameter validation be richer?

Daily processing systems may require:

- `businessDate` in ISO-8601, parseable via `LocalDate.parse`.
- `tenantId` in an allowlist and authorized for the launcher.
- `inputPath` not pointing outside permitted directories/namespaces.
- `dryRun` boolean with an explicit default.
- `maxRows` positive within bounds.
- `outputPath` nonidentifying if it should not determine `JobInstance` identity.
- All `identifying` flags reviewed because changing them alters restart semantics.

Do not use a generic `time` parameter that implicitly grabs `System.currentTimeMillis()` every run without documenting the policy. And never pass raw user input as file paths or SQL queries in a Tasklet without validation.

## 19. Job failures: when it throws an exception vs when it returns FAILED

Two cases:

**A. The launcher refuses to start an execution:** invalid `JobParameters`, already-completed instance, job already running, or severe repository error. A launch API can **throw an exception** such as `JobParametersInvalidException`, `JobInstanceAlreadyCompleteException`, or `JobExecutionAlreadyRunningException`.

**B. The Job/Step started, yet a Tasklet/Reader/Writer throws during processing:** with a normal synchronous launcher, `launchJob(...)` often **returns a `JobExecution` with `BatchStatus.FAILED`**; the root exception is recorded in failure exceptions / exit description. Therefore writing only:

```java
assertDoesNotThrow(() -> jobs.launchJob(params));
```

is **not enough** to prove the job succeeded. Assert `execution.getStatus()`, `getExitStatus()`, `getAllFailureExceptions()` where needed, and output data.

**Do not claim every error in Batch becomes `FAILED`:** validator/repository/start exceptions can be thrown out of `launchJob`. Error type and phase determine how to test.

### Failing step example (supplemental snippet)

A Tasklet intentionally throwing an exception:

```java
@Override
public RepeatStatus execute(
        StepContribution contribution,
        ChunkContext context) {
    throw new IllegalStateException(
            "simulated downstream failure");
}
```

This is a **snippet**, not part of the main runnable project. Placed in a Job/Step test with a real transaction manager and repository, inspect `JobExecution`/`StepExecution` failed status, exit status, failure exceptions, and whether **actual side effects** rolled back. Do not merely assert an exception was thrown by the test runner.

## 20. Restartability, checkpoints, and idempotency

A failed `JobInstance` can be restarted with the same identifying `JobParameters` if the job allows restarts. Yet how accurately it resumes depends on the Step:

- A step already `COMPLETED` in the prior execution is normally **skipped** on restart, unless `allowStartIfComplete(true)` or custom flow rules apply.
- A chunk-oriented reader/writer with `ItemStream` and `ExecutionContext` can restore offsets/counts from checkpoints.
- A Tasklet with non-transactional side effects failing mid-way must be **idempotent** or have compensation/recovery.
- If input files change after failure, a restart can yield different results; pin input revisions/hashes.
- Launching with a new identifying parameter creates a new instance, **not a restart**.

### Good restart tests need two phases

```text
Phase 1:
  Launch JobInstance X
  -> Step A COMPLETED
  -> Step B FAILED in a controlled way
  -> Assert phase 1 metadata and side effects

Phase 2:
  Fix failure condition while keeping X's identifying parameters
  -> Relaunch X (new JobExecution)
  -> Assert Step A is skipped per policy,
     Step B resumes per checkpoint/logic
  -> Assert no duplicate data and JobInstance identity preserved
```

This is a **strategy diagram**, not a test executed in the demo project (since the demo has no configurable failing step). To practice, add a fail-once Tasklet or checkpointed chunk Reader, then assert execution statuses and exact output. Do not write expected results claiming "resumed from record 11" if the reader never persisted position.

### Idempotency does not come from Batch metadata alone

`JobRepository` knows step progress, yet cannot roll back an S3 upload that already succeeded or a Kafka message already published when a DB transaction fails. For external side effects, use idempotency keys tied to `JobInstance`/`batchId`/record ID, the outbox pattern, or well-designed checkpoints/compensation.

## 21. Chunk-oriented jobs: what to test beyond Tasklets

Many real batch jobs use:

```text
ItemReader<T> -> ItemProcessor<T,R> -> ItemWriter<R>
            [chunk size N, transaction boundary]
```

A chunk test should guard:

- `readCount` matches input records (including actually read records).
- `filterCount` if the processor returns null to filter items.
- `writeCount` matches written items.
- `readSkipCount`/`processSkipCount`/`writeSkipCount` per policy.
- `commitCount`/`rollbackCount` matching transaction/step semantics.
- Output rows/file records contain accurate values, not just counts.
- Restarts with `ItemStream` restore offsets/checkpoints.
- Skip/retry limits; only intended exception types trigger skip/retry.
- No duplicate writes when a chunk retries.

### Example of testing a pure processor

```java
record RawOrder(String id, int amountCents) {}
record ReportLine(String id, int netCents) {}

ItemProcessor<RawOrder, ReportLine> processor =
        order -> order.amountCents() < 0
                ? null
                : new ReportLine(
                        order.id(), order.amountCents());

assertEquals(
        new ReportLine("A", 100),
        processor.process(new RawOrder("A", 100)));

assertNull(processor.process(
        new RawOrder("INVALID", -1)));
```

This is a **unit test snippet**, requiring imports for `org.springframework.batch.item.ItemProcessor` and JUnit assertions. To make it standalone runnable, place the records and test method inside a test class. It shows logic is easy to test without `JobRepository`. When a processor returns null, Spring Batch treats it as a **filtered item**, not a skip from an exception; do not conflate `filterCount` and `processSkipCount`.

### Chunk size alone does not dictate total commitCount

With chunk size 10, reading 25 records does not necessarily produce `commitCount==3` in every job/reader/setup because of trailing chunks, initialization, retries, or rollbacks. Use real metrics from `StepExecution`/clear fixtures rather than guesswork formulas. Prioritize asserting outputs and counter relationships first, then exact counts once behavior is established.

## 22. JobRepositoryTestUtils and isolation

`@SpringBatchTest` also provides `JobRepositoryTestUtils`, with `removeJobExecutions()` and related helpers. Method-level cleanup example:

```java
@Autowired
JobRepositoryTestUtils repositoryTestUtils;

@BeforeEach
void clearBatchMetadata() {
    repositoryTestUtils.removeJobExecutions();
}
```

This is a **snippet added to a test class**, omitted from the main project because the sample uses distinct batch IDs to test instance identity. `removeJobExecutions()` deletes batch job executions/instances managed by the test repository; running it against a shared/production DB can destroy real job history.

**It does NOT clean up:**

- Business tables inserted/updated by steps.
- Generated CSV/export files.
- S3 objects.
- Kafka messages/HTTP calls.
- In-memory `JobProbe`.
- External counters/caches.

For restart tests or duplicate-key tests, **do not wipe metadata between the two phases of the same test**, because that state is needed to verify restarts. After the test, reset the entire test database/schema/container per ownership.

### Why doesn't this project need deleteAll metadata?

`freshBatchId(...)` generates distinct identifying parameters across test scenarios. Each test creates an independent `JobInstance`, so clearing history before every method is unnecessary. The probe is cleared in `@BeforeEach`; H2 metadata remains without changing any scenario's result.

**This does not mean UUIDs are the only way:** when each test method runs against its own isolated DB, deterministic IDs like `FULL-001` or `STEP-COLLECT-001` work well. Still, whenever a context/database is reused across tests or repeated runs, define clear uniqueness/collision policies.

## 23. @Transactional on a test does not replace batch cleanup

A common mistake:

```java
@SpringBatchTest
@SpringBootTest
@Transactional
class MyBatchTest {
    // ...
}
```

Developers expect all business DB writes in the job to roll back with the test transaction. In reality, Spring Batch manages **Step-level transactions** and may run via separate `JobLauncher`/threads; the test-managed transaction does not automatically wrap step commits.

Another issue: `JobRepository` creates `JobExecution` in a separate transaction while the test holds an uncommitted outer transaction with fixture rows. Steps may fail to see uncommitted inputs or metadata updates may hit locks/conflicts. Therefore:

1. Use a test-specific database/schema.
2. Prepare fixtures with proper transaction visibility for the step.
3. Invoke the job/step launcher.
4. Inspect committed outputs and batch metadata.
5. Clean up/reset per DB ownership.
6. Never rely on `@Rollback` on the test thread as a "guarantee" covering all job side effects.

In the demo project, the `@SpringBootTest` test class is **not** annotated with `@Transactional` to avoid assuming a single transaction wraps the whole job.

## 24. Input test data and SQL fixtures

ETL batch jobs typically read data from DBs or files. Prepare purposeful fixtures:

- Valid rows to test the success path.
- Invalid rows to test filtering/skip policies.
- Duplicate business keys to test idempotency.
- Boundary data (0, max, nullable) per domain rules.
- Explicit ordering/sorting if output requires stable order.
- A bad record mid-chunk to test rollback/retry.
- Empty input to verify whether the job completes with 0 records or fails per contract.

Use `@Sql` before job runs when scripts must insert DB rows; **watch transaction mode** since steps can run on another transaction/thread. For full integration tests, dedicated test databases/schemas and committed test setups are much less surprising than uncommitted fixtures inside a test transaction.

### Do not depend on application seed data

If a production app has global demo seeds, job tests should not rely on them unless they are versioned reference data. Keep fixtures under `src/test/resources`, separate from production scripts. That keeps job tests deterministic and immune to someone adding a demo record.

## 25. Multiple jobs in the same ApplicationContext

`@SpringBatchTest` can auto-select the `Job` when only one exists in the context. If a production app has three `Job` beans:

```text
importUsersJob
monthlyBillingJob
expireSessionsJob
```

select the job under test explicitly instead of relying on accidental injection. For instance, a test configuration or setup calling `JobLauncherTestUtils.setJob(targetJob)` when utilities are configured properly:

```java
@Autowired
JobLauncherTestUtils jobs;

@Autowired
@Qualifier("monthlyBillingJob")
Job targetJob;

@BeforeEach
void selectJob() {
    jobs.setJob(targetJob);
}
```

This is a **snippet**: with multiple `Job` beans, ensure the test utility wires cleanly—for example by importing only the target job config or registering a test-specific `JobLauncherTestUtils` bean rather than letting auto-injection expect a unique `Job`. Do not claim this snippet alone cures a `NoUniqueBeanDefinitionException` occurring **before** `@BeforeEach`.

Better yet, split job configurations into modular classes easy to import and test independently; avoid `@ComponentScan` over an entire enterprise app for a single step test.

## 26. Scheduler and JobLauncher are two separate concerns

An application may use `@Scheduled` or Quartz to decide when to launch a job:

```java
@Scheduled(cron = "0 0 2 * * *")
public void runDaily() throws Exception {
    jobLauncher.run(job, parametersForToday());
}
```

This is an **architectural snippet** omitting class/injection; it is not in the runnable project. `@SpringBatchTest` tests the **Job once launched**; it does not prove the cron schedule, timezone, or cluster-wide single invocation.

Split tests into:

- **Scheduler unit test**: fixed clock, verify service/`JobLauncher` is called with the right parameters, without waiting for 02:00.
- **Batch job integration test**: call `launchJob` and verify steps/output/metadata.
- **Production scheduler integration**: Quartz persistence/distributed locks/misfire/retry if required.

**Do not use `Thread.sleep` waiting for real cron ticks** to test jobs in unit/integration suites. For scheduling, test date calculation, parameter building, and triggers explicitly.

### Preventing duplicate runs across multiple app instances

Two schedulers on two nodes can launch with the same identifying `JobParameters`. `JobRepository` rejects certain concurrent/duplicate job instances, yet does not replace distributed scheduling policies, DB constraints, fencing, or idempotent business writes. Test concurrency/recovery separately if the real system runs clustered.

## 27. If JobLauncher runs asynchronously

The sample project uses Boot's synchronous launcher under a simple config. Some systems configure `TaskExecutorJobLauncher` with an asynchronous `TaskExecutor`. In that case:

```java
JobExecution execution = jobLauncher.run(job, parameters);

// Status at return time may be STARTING/STARTED.
```

**Do not assert `COMPLETED` immediately after `run`** with an asynchronous launcher. Poll `JobExplorer`/`JobRepository` or a business-visible state until a terminal status (`COMPLETED`, `FAILED`, `STOPPED`) with a timeout.

Pseudo-test:

```text
Launch job
  -> receive executionId
  -> repeat until deadline:
       refresh JobExecution from JobExplorer
       if terminal status: stop waiting
       if past deadline: FAIL
  -> assert JobExecution, StepExecutions, and output
```

You can use Awaitility if the project adds the dependency:

```java
await()
    .atMost(Duration.ofSeconds(20))
    .untilAsserted(() -> {
        JobExecution current =
                jobExplorer.getJobExecution(executionId);
        assertEquals(
                BatchStatus.COMPLETED,
                current.getStatus());
    });
```

This is a **snippet** requiring Awaitility's `await()`, declared `jobExplorer`/`executionId`, and the library dependency; it is not in the runnable project. Never busy-spin without a deadline, and never hard-code `Thread.sleep(5000)` guessing the job finished.

**Note:** Test utilities and job scopes in async/multithreaded jobs require careful control of contexts/transactions/timeouts; never assume writer thread-safety from a single-threaded tasklet test.

## 28. Monitoring and error handling

Production-grade batch tests should also observe:

- `JobInstance` name / identifying params run.
- `JobExecution` ID and terminal status.
- Start/end timestamps and duration.
- `StepExecution` statuses, read/write/skip/rollback counts.
- Error cause/`ExitStatus` description (containing no PII/secrets).
- Business output written to DB/files/outbox.
- Retry and restart policies.
- Handling of partial files, rolled-back chunks, and orphaned artifacts.
- Runtime/resource usage on large datasets.

When a job FAILS, first inspect **failure exceptions and step names**; do not dump arbitrary errors into the batch metadata schema. If `getAllFailureExceptions()` is empty yet the job failed via custom flow/`ExitStatus`, inspect step transitions, listeners, and exit descriptions.

### BatchStatus and ExitStatus can differ

A step can have `BatchStatus.COMPLETED` with a custom `ExitStatus` like `COMPLETED_WITH_WARNINGS` to drive flow routing. Do not assert that status and exit code are the same type or string in every application. In the demo there are no custom transitions, so both are `COMPLETED`.

## 29. Common anti-patterns

| Anti-pattern | Consequence | Better approach |
| --- | --- | --- |
| Not disabling Boot auto-run in tests | Job runs before fixtures/params exist | `spring.batch.job.enabled=false` |
| Adding `@EnableBatchProcessing` casually in Boot 3.3 | Boot auto-config/schema init backs off | Use Boot starter/auto-config, customize only when needed |
| Using `JobBuilderFactory` from old tutorials without checking Batch 5 | Broken or deprecated API | `new JobBuilder(name, jobRepository)` |
| Calling `launchJob()` without required job params | Missing params / validator fails | `launchJob(explicitParams)` |
| Always adding random identifying timestamps | Restart tests lose the same `JobInstance` | Control `identifying` flags |
| Changing nonidentifying param to re-run completed instance | `JobInstanceAlreadyCompleteException` | New identifying identity when a fresh run is wanted |
| Treating `launchStep` as full job | Skips flow/validator/predecessors | Use `launchJob` for flow |
| `@Value("#{jobParameters[...]}"` on singleton | Step scope inactive at startup | `@StepScope` on component needing late binding |
| Putting `@StepScope` on the `Step` bean unnecessarily | Complex wiring/proxies | Scope Tasklet/Reader/Writer |
| Only asserting no exception thrown | Job can return `FAILED` | Assert `JobExecution` and output |
| Only asserting `COMPLETED` | Empty Tasklet still completes | Assert business side effects and step metadata |
| Putting `@Transactional` on test expecting batch writes roll back | Step commits run outside test transaction | Dedicated DB + cleanup/reset |
| Deleting batch metadata between restart test phases | Loses checkpoints/history | Keep metadata until assertions finish |
| Using `JobRepositoryTestUtils` on shared DB | Wipes others' job history | Dedicated test DB/schema |
| Using fixed `Thread.sleep` for async jobs | Flaky/slow tests | Bounded polling on `JobExplorer` |
| Asserting ordering across parallel steps | Concurrency race | Assert DAG/dependencies or controlled ordering |
| Using in-memory probe as proof of JDBC rollback | Probe is non-transactional | Query business DB |
| Counting read/write on Tasklet demo as if chunked | Wrong metric type | Assert counts in chunk tests |
| Using fake credentials/PII from production snapshots | Sensitive data leak | Synthetic fixtures and separate test secrets |

## 30. Debugging sequence

1. Verify whether Spring Batch is actually used; projects with only a scheduler should test the scheduler without Batch.
2. Confirm Spring Boot 3.3.5, Spring Batch 5.1.x, `spring-boot-starter-batch`, `spring-batch-test`, and H2 driver.
3. Confirm the test profile is active with `spring.batch.job.enabled=false`.
4. Confirm `BATCH_*` tables exist and are not managed by two conflicting schema mechanisms.
5. If `JobRepository` bean is missing, check whether `@EnableBatchProcessing`/`DefaultBatchConfiguration` made Boot back off.
6. If `JobLauncherTestUtils` lacks a `Job`, check the count of `Job` beans or bean selection.
7. If `StepScope` is inactive, check `@StepScope` and that it runs inside a real `StepExecution`.
8. If `launchStep` reports step not found, check step names in the `Job` graph and bean wiring.
9. If the job throws `JobInstanceAlreadyCompleteException`, inspect identifying params and `JobRepository` history.
10. If the launcher returns `JobExecution FAILED`, inspect failure exceptions/`ExitStatus` and step logs.
11. If job status is `COMPLETED` with no output, inspect Tasklet/Writer or transaction/commit.
12. If tests pass standalone yet fail in the full suite, check reused `JobRepository`, test IDs, context cache, and parallel runs.
13. If an async test fails, poll `JobExecution` status with a deadline rather than asserting immediately.
14. If production jobs fail to restart cleanly, inspect `ItemStream`/`ExecutionContext` checkpoints and external idempotency.

## 31. Expected results from the sample project

| Test method | What it protects | Expected outcome from source |
| --- | --- | --- |
| `wholeJobRunsBothStepsInOrder` | Full Job, status, exit code, flow, output | `COMPLETED`; `collect` → `publish` |
| `launchCollectStepDoesNotRunPublishStep` | Only Collect step | One `StepExecution`; stage `collect` |
| `launchPublishStepDoesNotRunCollectStep` | Only Publish step | One `StepExecution`; stage `publish` |
| `stepScopeReadsTheCurrentJobParameter` | Late binding from `JobParameters` | Context holds matching `batchId` |
| `completedInstanceRejectsRerunWithOnlyNoteChanged` | Nonidentifying param doesn't change instance | `JobInstanceAlreadyCompleteException` |
| `changedIdentifyingBatchIdCreatesNewInstance` | Identifying param changes instance | Two distinct instance IDs |
| `jobValidatorRejectsMissingBatchId` | Job-level validation | `JobParametersInvalidException` |
| `launchStepRejectsUnknownStepName` | Step lookup failure | `IllegalStateException` |
| `parametersExposeTheirIdentifyingFlags` | Typed params + identifying flags | `batchId=true`, `attempt=false` |

**These are expected assertions from the 9 test methods, not observed console output.** When practicing, run Gradle and inspect the test report before reporting 9 PASS.

### Run commands

If the project already has a Gradle Wrapper:

```bash
./gradlew test --tests 'com.example.batch.ExportBatchJobTest'
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

If there is no Wrapper yet but a compatible Gradle is installed:

```bash
gradle test
```

JUnit/Gradle results after execution typically appear at:

```text
build/reports/tests/test/index.html
build/test-results/test/
```

There is no fixed business stdout: Spring Batch and H2 can log varying details depending on logging settings. Reliable proof of PASS is a successful Gradle test task and a report recording the right passed test count, not a hand-written console line in documentation.

## 32. Practice exercises

1. Run `ExportBatchJobTest` and inspect both step names in `JobExecution.getStepExecutions()`.
2. Remove `spring.batch.job.enabled=false` from the test profile: analyze why the startup runner may attempt to run the Job without `batchId`.
3. Swap `.start(collectStep).next(publishStep)` order and observe how probe stages/order assertions catch the change.
4. Try removing `@StepScope` from `CollectTasklet` and read the late-binding error at context startup.
5. Run `publishStep` standalone and explain why `collectStep` is not invoked.
6. Test a step depending on `JobExecutionContext` set by an earlier step; use `launchStep(step, params, context)` to supply fixture context.
7. Launch the full job twice with the same `batchId` but different `attempt`; verify exceptions are not hidden by catching and returning 200.
8. Change `batchId` on rerun, inspect the distinct `JobInstance` IDs, and verify both executions complete.
9. Add a `JobParametersValidator` validating ISO `businessDate`; write invalid/missing cases.
10. Switch `batchId` from `identifying=true` to `false` to observe the risk of all runs collapsing into one instance.
11. Add a fail-once Tasklet in `publishStep` and write a restart test using the same identifying parameters.
12. Add a chunk-oriented step reading 10 rows and filtering 1; assert read/write/filter counts from real fixture data.
13. Write an `ItemProcessor` unit test without starting a Batch context.
14. Try `JobRepositoryTestUtils.removeJobExecutions()` on H2 tests only; distinguish metadata from business effects.
15. Add a second `Job` to the context and handle `JobLauncherTestUtils` selection explicitly.
16. Switch the launcher to async to practice bounded polling on terminal status.
17. Write a scheduler test building exact `JobParameters` for a fixed business date.
18. Try running two test classes in parallel on a shared H2 DB; isolate `batchId`/database to prevent collisions.
19. Replace H2 with PostgreSQL Testcontainers and run version-matching batch metadata migrations.
20. Add assertions confirming files/outputs are idempotent after restart with zero duplicates.

## 33. QA checklist for code review

- [ ] Does the real application actually use Spring Batch, avoiding unnecessary Batch test frameworks?
- [ ] Do Boot/Batch API imports match Java 17+/Boot 3.3.5/Batch 5.1?
- [ ] Is the job prevented from auto-running on test context startup?
- [ ] Is the batch metadata JDBC schema created via the right initializer/migration?
- [ ] Do `JobRepository` and `PlatformTransactionManager` point to the right `DataSource`?
- [ ] Does `@SpringBatchTest` register `JobLauncherTestUtils`/`JobRepositoryTestUtils` properly?
- [ ] Is the job under test explicitly chosen when multiple `Job`s exist in context?
- [ ] Have `JobParameters` names, types, defaults, and `identifying` flags been reviewed?
- [ ] Are missing/invalid required parameters tested?
- [ ] Is the full job flow tested, not just individual steps?
- [ ] Are single steps tested via `launchStep` without misunderstanding the surrogate job?
- [ ] Are step-scoped components late-bound properly in the runtime context?
- [ ] Is the `Step` bean itself left unscoped unless genuinely needed?
- [ ] Are `BatchStatus`, `ExitStatus`, and `StepExecutions` verified?
- [ ] For chunk jobs, are read/write/filter/skip/rollback counts validly asserted?
- [ ] Is actual output asserted, not merely `COMPLETED`?
- [ ] Do restart tests preserve the same identifying parameters without wiping metadata?
- [ ] Do fresh-run tests use distinct identifying parameters?
- [ ] Does the test avoid assuming `@Transactional` on the test rolls back all step effects?
- [ ] Are DB/fixtures/side effects isolated and cleaned up under test ownership?
- [ ] Are asynchronous launchers distinguished from synchronous launchers?
- [ ] Are unbounded/unconditional `Thread.sleep` calls avoided?
- [ ] Is scheduler timezone/trigger logic tested separately if the app uses schedules?
- [ ] Are production credentials, PII, and real file paths kept out of fixtures?
- [ ] Did Gradle/CI test suites actually run and were reports read instead of inferring PASS from code?
- [ ] Do tests produce consistent results both individually and across the full suite?

## 34. References

- [Spring Batch 5.1 — Unit Testing](https://docs.spring.io/spring-batch/reference/5.1/testing.html): `@SpringBatchTest`, `JobLauncherTestUtils`, `launchJob`, `launchStep`, `StepScopeTestUtils`. If minor version URLs shift, consult "Testing" in [Spring Batch Reference](https://docs.spring.io/spring-batch/reference/testing.html).
- [JobLauncherTestUtils 5.1 Javadoc](https://docs.spring.io/spring-batch/docs/5.1.1-SNAPSHOT/org/springframework/batch/test/JobLauncherTestUtils.html): `launchJob(JobParameters)` and `launchStep(name, params)` signatures, surrogate job.
- [SpringBatchTest 5.1 Javadoc](https://docs.spring.io/spring-batch/docs/5.1.1-SNAPSHOT/org/springframework/batch/test/context/SpringBatchTest.html): test utility registrations, step/job scope listeners.
- [Spring Batch 5.1 — TaskletStep](https://docs.spring.io/spring-batch/reference/5.1/step/tasklet.html): `Tasklet`, `RepeatStatus`, and transactions.
- [Spring Batch 5.1 — Late Binding](https://docs.spring.io/spring-batch/reference/5.1/step/late-binding.html): `@StepScope` and `JobParameters` SpEL.
- [Spring Batch — Configuring a Job](https://docs.spring.io/spring-batch/reference/job/configuring-job.html): `JobInstance`, restartability, and flow.
- [Spring Batch — Configuring a Step](https://docs.spring.io/spring-batch/reference/5.1/step/chunk-oriented-processing/configuring.html): `StepBuilder`, transaction manager, chunk semantics.
- [Spring Boot 3.3 — Batch Applications](https://docs.spring.io/spring-boot/3.3/how-to/batch.html): `spring.batch.job.enabled`, `@EnableBatchProcessing`, Batch `DataSource`.
- [Spring Boot 3.3 — Database Initialization](https://docs.spring.io/spring-boot/3.3/how-to/data-initialization.html): `spring.batch.jdbc.initialize-schema` and SQL initialization.
- [JobRepositoryTestUtils 5.1 Javadoc](https://docs.spring.io/spring-batch/docs/5.1.0/org/springframework/batch/test/JobRepositoryTestUtils.html): metadata cleanup, utility semantics.
- [JUnit Jupiter User Guide](https://junit.org/junit5/docs/current/user-guide/): test lifecycle, assertions, and independent methods.

## 35. Conclusion

Testing Spring Batch does not stop at invoking `JobLauncher` and checking no exception was thrown. A **`Job`** is the flow, a **`Step`** is the processing unit, **`JobParameters`** govern both input data and `JobInstance` identity, and **`JobRepository`** persists execution history to drive restarts.

With Spring Boot 3.3 / Spring Batch 5.1, set `spring.batch.job.enabled=false` in the test profile, let Boot manage JDBC Batch infrastructure properly, use `@SpringBatchTest` with `JobLauncherTestUtils.launchJob(params)` to test the full flow, and `launchStep(name, params)` to test individual steps. Use `@StepScope` for components needing late-bound parameters, and verify `StepExecution`/`BatchStatus`/`ExitStatus` **and output** rather than treating `COMPLETED` as sufficient.

Advanced tests must properly handle `identifying` flags, same instance vs new instance, failed-job restarts, chunk checkpoints, transaction boundaries, asynchronous launchers, and separate scheduler triggers. **Never claim data/side effects rolled back simply because the test method has `@Transactional`**, and never claim Gradle tests PASSED without running them. This structure gives Batch tests clarity, repeatability, and real protection whenever an application relies on batch jobs.