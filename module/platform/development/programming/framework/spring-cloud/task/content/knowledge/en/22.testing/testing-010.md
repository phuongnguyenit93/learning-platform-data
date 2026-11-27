# Integration Testing Batch, Events, and Infrastructure Failures

In the **Testing** chapter of the **SPRING_CLOUD_TASK** module, a finite-lived application rarely stands alone. It is launched by a scheduler or API, runs a **Spring Batch Job**, writes business results to a database, updates `TaskRepository`, and may emit events via **Spring Cloud Stream**. When every component is healthy, writing a passing test is easy. What is harder is proving the system behaves properly when a component **is down**, a reply is lost, or the JVM is killed before recording completion.

The goal of integration testing is not merely checking that a `process()` method returns the right value. You must verify **the actual flow of data and metadata** across Spring Cloud Task, Spring Batch, transactions, JDBC, the event broker, and the orchestrator. At the same time, distinguish carefully: a test that runs inside the same Spring `ApplicationContext` **does not prove** that the JVM exit code and completion events of an independent process are recorded accurately.

This lesson presents a layered strategy, Spring Batch 5.x examples with PostgreSQL Testcontainers, message contract testing with the Spring Cloud Stream Test Binder, and end-to-end scenarios using **a separate Java process** with Kafka/an orchestrator. The examples target Spring Boot 3.x, Spring Batch 5.x, and a compatible Spring Cloud Task version; adjust them when using Spring Batch 6.x or another release train.

## 1. Learning Objectives

After this lesson, you will be able to:

- Select the right testing layer for business logic, `JobExecution`, `TaskExecution`, events, and runtime behavior.
- Use `@SpringBatchTest`, `JobLauncherTestUtils`, and `JobRepositoryTestUtils` from **Spring Batch 5.x** in integration tests.
- Verify `BatchStatus`, `ExitStatus`, `StepExecution`, and **committed data** rather than just a log line.
- Test `spring.cloud.task.batch.fail-on-job-failure=true` so Batch failures surface at the Task/process layer.
- Distinguish `task-events` from `job-execution-events`; test both **message contracts** and a **real broker**.
- Use Testcontainers to verify real PostgreSQL behavior, unique constraints, transactions, and Kafka.
- Design tests for DB/broker connection loss, bootstrap errors, timeouts, SIGKILL, and uncertain commit outcomes.
- Evaluate retry/idempotency, missing completion events, incomplete metadata, and `UNKNOWN` state classification rules.
- Build a test matrix and CI execution criteria with isolated data, bounded timeouts, and complete evidence.

## 2. What an Integration Test Suite Must Prove

In a Spring Cloud Task application integrated with Batch and events, there are at least four distinct outcome layers:

| Layer | Primary Source of Truth | Minimum Verification |
| --- | --- | --- |
| **Business** | Output tables/files/APIs | Data is accurate, complete, non-duplicated, committed or confirmed |
| **Spring Batch** | `JobRepository`, `JobExecution`, `StepExecution` | `BatchStatus`, `ExitStatus`, read/write/skip counts, restarts |
| **Spring Cloud Task** | `TaskRepository`, `TaskExecution` | Single execution, start/end, exit code/message, Batch link when configured |
| **Runtime and events** | Process/pod, broker, consumer, and scheduler | OS exit code, received events, retries/timeouts/duplicates |

For example, a Batch Job can fail while the process still exits `0` if Batch failures are not propagated to the Task properly. Conversely, the process can exit with a failure after the business table already committed. Therefore, **no single assertion can substitute for the others**.

~~~mermaid
flowchart TD
    A["Orchestrator launches Task"] --> B["Spring Boot / Spring Cloud Task"]
    B --> C["Spring Batch Job / Step"]
    C --> D["Business database"]
    C --> E["JobRepository: JobExecution / StepExecution"]
    B --> F["TaskRepository: TaskExecution"]
    B --> G["Spring Cloud Stream: task-events"]
    C --> H["Spring Cloud Stream: job/step events"]
    G --> I["Kafka / Consumer"]
    H --> I
    D --> J["Integration assertion suite"]
    E --> J
    F --> J
    I --> J
    A --> J
~~~

**Do not conflate the repositories**: `TaskRepository` tracks Task application lifecycle; `JobRepository` tracks Batch Jobs/Steps and checkpoints. Both repositories can share one database while still storing distinct metadata models.

## 3. Multi-Layer Integration Testing Matrix

Split tests into groups with clear goals:

| Group | Tools or Environment | What It Must Prove | What It Cannot Prove Alone |
| --- | --- | --- | --- |
| Unit test | JUnit 5, Mockito, or fake services | Validation, mappings, idempotency policy | JDBC commits or broker behavior |
| Batch integration | `@SpringBatchTest` + PostgreSQL | Job/Step status, transactions, business data | Exit code of a **separate JVM** |
| Event contract | Spring Cloud Stream Test Binder | Consumer parses payloads, bindings, and schemas properly | Kafka ACLs, networking, real retries/redelivery |
| Broker integration | Kafka Testcontainers | Producer <-> topic <-> consumer truly interact | Business completion without checking the DB |
| Process end-to-end | `ProcessBuilder`/container Job running real JAR | Bootstrap, auto-config, exit code, `TaskExecution` | Business invariants if checking only exit code |
| Fault injection | Network proxy, process kill, temporary broker/DB outage | No infinite hangs, `UNKNOWN` state, retry/idempotency | Accuracy if relying on arbitrary sleeps |

An effective CI setup usually runs **unit and Batch integration tests** on every commit; Kafka/process/fault-injection tests can run in a dedicated pipeline if runtime and infrastructure cost more. Critical failure paths must still run regularly before releases.

## 4. Demo Problem and Invariants

Suppose a Spring Cloud Task processes reports for `businessKey=shop-01|2026-11-24`. Spring Batch runs a single Step writing results to a `daily_import` table. The Task may be re-run by scheduler/Job retries, but it must never create duplicate rows for the same business key.

### 4.1. Business Invariants

- **One business key produces at most one result**, even when two processes run concurrently.
- Same key + same input -> subsequent attempts return the existing result without new side effects.
- Same key + different input -> report a conflict per policy rather than silently overwriting.
- Batch Job fails before commit -> no result row exists for that attempt.
- When commit acknowledgment is lost -> caller state is **unknown**; read the DB before blindly retrying.
- Batch/Task metadata and broker events are used to reconcile execution progress, not as substitutes for verifying business results.

### 4.2. Table Used in This Lesson

PostgreSQL example:

~~~sql
CREATE TABLE daily_import (
    business_key VARCHAR(160) PRIMARY KEY,
    result       VARCHAR(32) NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

The `business_key` primary key enforces deduplication **in the database**, rather than relying solely on `SELECT` before `INSERT`. This DDL belongs to the **business schema**, separate from framework-managed `TASK_EXECUTION` and `BATCH_JOB_EXECUTION` tables.

### 4.3. Transaction Boundaries

In this example, a tasklet-based Step writes one row to PostgreSQL. Written data and Job/Step statuses are verified through separate sources. Never assume `TaskExecution` creation and the Step transaction form **a single atomic transaction**, even when all tables reside in the same database.

## 5. Dependencies and Versions

The tests below use **Spring Batch 5.x** as a baseline. With Spring Boot 3.x, the project needs a **compatible** Spring Boot parent/BOM and Spring Cloud BOM; never mix arbitrary Boot, Task, Stream, and Batch versions.

Core Maven dependencies:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-batch</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-task</artifactId>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
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
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>postgresql</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

To **test Spring Cloud Stream events** in later sections, add compatible dependencies:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-binder-kafka</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-test-binder</artifactId>
    <scope>test</scope>
</dependency>
~~~

Additional Spring Cloud Task/Stream modules for event emission may be required depending on the release train; verify **the actual dependency tree and auto-configuration**. Keep the Test Binder in `test` scope so it never accidentally replaces the Kafka binder in production.

Use `spring-boot-maven-plugin` to build an executable JAR for end-to-end process tests. Do not pin standalone version strings in these snippets; manage versions consistently via your project's BOM.

**Testcontainers versions:** the `org.testcontainers:junit-jupiter` and `org.testcontainers:postgresql` coordinates with `org.testcontainers.containers.PostgreSQLContainer` in these examples reflect **Testcontainers 1.x** (e.g., the 1.21.x line). Starting in **Testcontainers 2.x**, coordinates changed to `testcontainers-junit-jupiter` and `testcontainers-postgresql`, and some packages/classes changed. If your project BOM manages Testcontainers 2.x, follow the 2.x docs for dependencies and imports; do not mix 1.x artifacts with 2.x versions.

> **Important difference:** In Spring Batch **5.x**, `@SpringBatchTest` provides `JobLauncherTestUtils`. Starting in Spring Batch **6.x**, documentation switches to `JobOperatorTestUtils` and APIs change. Do not copy 5.x class/builder names directly into a 6.x project without checking the docs.

## 6. Sample Application: A Job and Step That Can Fail

Create `src/main/java/com/example/task/DailyImportTaskApplication.java`:

~~~java
package com.example.task;

import java.util.Map;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;

@SpringBootApplication
public class DailyImportTaskApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(DailyImportTaskApplication.class, args);
        int exitCode = SpringApplication.exit(context);
        System.exit(exitCode);
    }

    @Bean
    Job dailyImportJob(JobRepository jobRepository, Step importStep) {
        return new JobBuilder("dailyImportJob", jobRepository)
                .start(importStep)
                .build();
    }

    @Bean
    Step importStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            JdbcTemplate jdbc) {

        return new StepBuilder("importStep", jobRepository)
                .tasklet((contribution, chunkContext) -> {
                    Map<String, Object> params =
                            chunkContext.getStepContext().getJobParameters();

                    Object keyValue = params.get("businessKey");
                    if (!(keyValue instanceof String businessKey)
                            || businessKey.isBlank()) {
                        throw new IllegalArgumentException(
                                "businessKey must be a non-empty string");
                    }

                    boolean failDemo = Boolean.parseBoolean(
                            String.valueOf(params.get("failDemo")));

                    if (failDemo) {
                        throw new IllegalStateException(
                                "DEMO_UPSTREAM_FAILURE");
                    }

                    // PostgreSQL: idempotent write using a unique key.
                    jdbc.update("""
                        INSERT INTO daily_import (business_key, result)
                        VALUES (?, 'DONE')
                        ON CONFLICT (business_key) DO NOTHING
                        """, businessKey);

                    return RepeatStatus.FINISHED;
                }, transactionManager)
                .build();
    }
}
~~~

### Explanation

- `Job` named `dailyImportJob` has one `Step` named `importStep`.
- `JobParameters.businessKey` is the stable business key.
- `failDemo` triggers an error **before writing data**, purely to test the failure path.
- `ON CONFLICT DO NOTHING` is PostgreSQL-specific syntax, **not generic SQL for every DB**.
- `StepBuilder.tasklet(..., transactionManager)` reflects Spring Batch **5.x** API style. In a multi-datasource system, the Step's transaction manager must target the business write datasource.
- `SpringApplication.exit(context)` lets Boot/Task exit-code mechanisms apply; you must run a **separate process** to verify the OS exit code.
- The example does not add an `ApplicationRunner` manually calling `JobLauncher` because Spring Boot/Task can auto-run the `Job` when configured; adding both can run the Job twice.

Set `spring.cloud.task.batch.fail-on-job-failure=true` when Batch failures must map to a non-zero Task exit code as supported by your version.

### Production-Like Configuration

~~~yaml
spring:
  application:
    name: daily-import-task
  main:
    web-application-type: none

  datasource:
    url: ${TASK_DB_URL}
    username: ${TASK_DB_USER}
    password: ${TASK_DB_PASSWORD}
    driver-class-name: org.postgresql.Driver

  batch:
    job:
      enabled: true
    jdbc:
      initialize-schema: never

  cloud:
    task:
      name: daily-import-task
      initialize-enabled: false
      batch:
        fail-on-job-failure: true
~~~

This configuration assumes the database already has **version-matched Batch + Task schemas** and the `daily_import` table has been migrated. In production, avoid having every process auto-create schema tables.

## 7. Batch Integration Testing with PostgreSQL Testcontainers

A unit test mocking `JdbcTemplate` can check method calls, yet **does not prove** PostgreSQL committed or that unique constraints worked. For integration tests, use PostgreSQL Testcontainers for a real database without relying on a database shared across developers.

### 7.1. Test Configuration

The following example applies to **Spring Batch 5.x**. Create `src/test/java/com/example/task/DailyImportBatchIT.java`:

~~~java
package com.example.task;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.JobRepositoryTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBatchTest
@Testcontainers
@SpringBootTest(
        classes = DailyImportTaskApplication.class,
        properties = {
            "spring.batch.job.enabled=false",
            "spring.batch.jdbc.initialize-schema=always",
            "spring.cloud.task.initialize-enabled=true",
            "spring.cloud.task.events.enabled=false",
            "spring.cloud.task.batch.events.enabled=false"
        })
class DailyImportBatchIT {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void datasource(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    JobLauncherTestUtils launcher;

    @Autowired
    JobRepositoryTestUtils batchCleaner;

    @Autowired
    Job dailyImportJob;

    @Autowired
    JdbcTemplate jdbc;

    @BeforeEach
    void setUp() {
        launcher.setJob(dailyImportJob);

        jdbc.execute("""
            CREATE TABLE IF NOT EXISTS daily_import (
                business_key VARCHAR(160) PRIMARY KEY,
                result VARCHAR(32) NOT NULL
            )
            """);

        batchCleaner.removeJobExecutions();
        jdbc.update("DELETE FROM daily_import");
    }

    @Test
    void jobHoanTatVaGhiDuLieu() throws Exception {
        JobExecution job = launcher.launchJob(
                params("shop-01|2026-11-24", "attempt-1", false));

        assertEquals(BatchStatus.COMPLETED, job.getStatus());
        assertEquals("COMPLETED", job.getExitStatus().getExitCode());
        assertEquals(1, count("shop-01|2026-11-24"));
    }

    @Test
    void jobThatBaiKhongGhiDuLieu() throws Exception {
        JobExecution job = launcher.launchJob(
                params("shop-02|2026-11-24", "attempt-fail", true));

        assertEquals(BatchStatus.FAILED, job.getStatus());
        assertEquals(0, count("shop-02|2026-11-24"));
    }

    @Test
    void retryVoiCungBusinessKeyKhongTaoTrung() throws Exception {
        JobExecution first = launcher.launchJob(
                params("shop-03|2026-11-24", "attempt-1", false));

        JobExecution second = launcher.launchJob(
                params("shop-03|2026-11-24", "attempt-2", false));

        assertEquals(BatchStatus.COMPLETED, first.getStatus());
        assertEquals(BatchStatus.COMPLETED, second.getStatus());
        assertEquals(1, count("shop-03|2026-11-24"));
    }

    private int count(String businessKey) {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM daily_import WHERE business_key=?",
                Integer.class, businessKey);
    }

    private static JobParameters params(
            String key, String attemptId, boolean failDemo) {
        return new JobParametersBuilder()
                .addString("businessKey", key, true)
                .addString("attemptId", attemptId, true)
                .addString("failDemo",
                        Boolean.toString(failDemo), false)
                .toJobParameters();
    }
}
~~~

### 7.2. What the Test Above Verified

- Spring built the `Job`, `Step`, transaction manager, Batch repository, and real JDBC datasource.
- `JobLauncherTestUtils.launchJob(...)` executed the Job inside the **Spring test context** and returned a `JobExecution`.
- The success case produced `BatchStatus.COMPLETED`, `ExitStatus.COMPLETED`, and **one committed row**.
- The simulated failure case returned `BatchStatus.FAILED` and wrote no rows.
- Two launches with the same `businessKey` but different `attemptId` values created **two independent `JobInstance`/attempts per identifying parameters**; the unique key retained exactly one result.

**Key Spring Batch nuance:** if you supply **the exact same identifying `JobParameters`** for an already-completed `JobInstance`, Batch can reject the re-launch with `JobInstanceAlreadyCompleteException`. This example uses `attemptId` as an identifying parameter **solely to simulate two independent runs for the same business key**. When testing **restarting a single `JobInstance`**, keep identifying parameters identical and use the appropriate restart mechanism/`JobRepository` policy rather than creating a new instance and calling it a restart.

`@SpringBatchTest` does not by itself verify `TaskExecution` for an independent JVM. The Spring test context has a different lifecycle from a scheduler-launched process; Task exit code checks belong in end-to-end process tests.

### 7.3. Notes on Test Isolation

- Use a dedicated container or schema; never drop tables in a shared non-test database.
- `JobRepositoryTestUtils.removeJobExecutions()` cleans only **Batch** metadata; it does not clean business tables or `TASK_EXECUTION`.
- Do not blindly put `@Transactional` on the entire test if doing so masks Step commits; query the database **after** the job finishes.
- Avoid running tests sharing the same database/`JobParameters` in parallel without isolation.
- Enabling schema creation via `initialize-schema=always` is for **tests**, never a production policy.
- For Spring Batch **6.x** projects, migrate the example to `JobOperatorTestUtils` and the corresponding APIs.

## 8. Inspecting `StepExecution` Data and Batch-Task Linking

Beyond `BatchStatus`, tests can verify the Step actually ran:

~~~java
assertEquals(1, job.getStepExecutions().size());

var step = job.getStepExecutions().iterator().next();
assertEquals("importStep", step.getStepName());
assertEquals(BatchStatus.COMPLETED, step.getStatus());
~~~

In a Job with only a single tasklet Step, there are not necessarily read/write counts like in a chunk-oriented step. If you switch to `ItemReader`/`ItemWriter`, also assert `readCount`, `writeCount`, `skipCount`, and `ExecutionContext` checkpoints on restart.

Spring Cloud Task can link a `JobExecution` to a `TaskExecution` when Task-Batch integration is configured properly (including the appropriate listeners and dependencies). **Do not assume merely adding `spring-batch-test` establishes this link.**

You can verify via metadata tables in a real JAR launch environment:

~~~sql
SELECT TASK_EXECUTION_ID,
       TASK_NAME,
       START_TIME,
       END_TIME,
       EXIT_CODE
FROM TASK_EXECUTION
ORDER BY TASK_EXECUTION_ID DESC;
~~~

~~~sql
SELECT JOB_EXECUTION_ID,
       JOB_INSTANCE_ID,
       STATUS,
       EXIT_CODE,
       START_TIME,
       END_TIME
FROM BATCH_JOB_EXECUTION
ORDER BY JOB_EXECUTION_ID DESC;
~~~

The Task-Batch link may be persisted in a dedicated mapping table in your version's Spring Cloud Task schema. Use the corresponding official schema/SQL rather than assuming direct join columns on every table. A successful `JobExecution` does not automatically prove the process exited cleanly or that events reached the broker.

## 9. Testing Events: Contract vs. Broker Integration

Per Spring Cloud Task documentation, with Spring Cloud Stream and a compatible binder, listeners can emit `TaskExecution` events at **start** and **end** via the `task-events` logical binding. Batch integration exposes event streams such as `job-execution-events`, `step-execution-events`, and `chunk-events` when configured.

You must distinguish **two types of tests**:

| Test | How It Runs | What It Concludes |
| --- | --- | --- |
| **Consumer contract** | Feeds test payloads into Spring Cloud Stream Test Binder | Consumer parses, validates, and processes the message format properly |
| **Producer/broker/process integration** | Runs real JAR, real Kafka in Testcontainers, consumer reads topics | Task listeners and binder actually publish to the broker and consumers receive them |
| **Reliability/failure** | Broker outage, JVM kill, redelivery | How the application handles missing, delayed, or duplicate events |

A contract test injecting simulated messages **is not sufficient** to claim Spring Cloud Task successfully published both lifecycle events over Kafka.

### 9.1. Destination Configuration

Producer:

~~~yaml
spring:
  cloud:
    task:
      events:
        enabled: true
      batch:
        events:
          enabled: true
    stream:
      bindings:
        task-events:
          destination: it.task.lifecycle
          contentType: application/json
        job-execution-events:
          destination: it.batch.jobs
          contentType: application/json
~~~

`task-events` and `job-execution-events` are **output bindings** for Task/Batch integration in the corresponding configuration. With Kafka, they target topics `it.task.lifecycle` and `it.batch.jobs`. Ensure a binder is on the classpath and the broker is configured. These topic names are for test environments only.

To isolate failures:

~~~properties
spring.cloud.task.events.enabled=false
spring.cloud.task.batch.events.enabled=false
~~~

The first switch disables **Task lifecycle events**, and the second disables **Batch events**; neither disables `TaskRepository` or `JobRepository`.

## 10. Consumer Contract Test Example with Test Binder

Spring Cloud Stream provides the Test Binder to test consumers **without real Kafka**. Below is a minimal test using a `Consumer<Message<byte[]>>` function; the payload is read as JSON text to avoid coupling to producer internal Java classes.

~~~java
package com.example.task;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.function.Consumer;

import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.stream.binder.test.InputDestination;
import org.springframework.cloud.stream.binder.test.EnableTestBinder;
import org.springframework.context.annotation.Bean;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.GenericMessage;
import org.springframework.beans.factory.annotation.Autowired;

@SpringBootTest(
        classes = TaskEventConsumerContractIT.TestApp.class,
        properties = {
            "spring.cloud.function.definition=captureTask",
            "spring.cloud.stream.bindings.captureTask-in-0.destination=it.task.lifecycle",
            "spring.cloud.stream.bindings.captureTask-in-0.contentType=application/octet-stream",
            "spring.cloud.task.autoconfiguration.enabled=false",
            "spring.batch.job.enabled=false"
        })
@EnableTestBinder
class TaskEventConsumerContractIT {

    @Autowired
    InputDestination input;

    @Autowired
    BlockingQueue<String> captured;

    @Test
    void consumerNhanDuocJsonPayload() throws Exception {
        String json = """
            {"executionId":42,"taskName":"daily-import-task",
             "exitCode":0,"endTime":"2026-11-24T01:00:00Z"}
            """;

        input.send(
                new GenericMessage<>(
                        json.getBytes(StandardCharsets.UTF_8)),
                "it.task.lifecycle");

        String received = captured.poll(3, TimeUnit.SECONDS);
        assertNotNull(received);
        assertTrue(received.contains("\"executionId\":42"));
        assertTrue(received.contains("\"taskName\":\"daily-import-task\""));
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApp {

        @Bean
        BlockingQueue<String> captured() {
            return new LinkedBlockingQueue<>();
        }

        @Bean
        Consumer<Message<byte[]>> captureTask(
                BlockingQueue<String> captured) {
            return message -> captured.add(
                    new String(
                            message.getPayload(),
                            StandardCharsets.UTF_8));
        }
    }
}
~~~

This is a **consumer contract test**; it does not trigger `TaskExecutionListener` itself. The JSON payload is supplied directly by the test and illustrates fields commonly needed for dashboards. In real code, replace substring checks with JSON schema/DTO validation matched to the **actual payload** emitted by your Spring Cloud Task version.

If the converter in your Stream version handles non-`byte[]` payloads, use `Message<String>` or configure matching content types and test against the actual version. Do not assume every version's `TaskExecution` serializes identically to this example.

## 11. End-to-End Event Testing with Real Kafka

To prove the **Task producer** publishes events to the broker, run a process-level test:

1. Start Kafka using **Testcontainers** or an isolated Kafka integration environment.
2. Create dedicated topics (e.g., `it.task.lifecycle`, `it.batch.jobs`) per test policy.
3. Create a Kafka consumer with a dedicated group, `auto.offset.reset=earliest`, ready to read before or alongside launch.
4. Run the **Spring Cloud Task JAR in a separate process**, pointing both JDBC and the Kafka binder at the containers.
5. Wait for the process to exit within a finite deadline; capture exit code and stdout/stderr.
6. Poll the topics with a timeout, filter by `executionId`/`runId`, and compare start/end events.
7. Query `TASK_EXECUTION` and `BATCH_JOB_EXECUTION` to reconcile event contents.
8. Verify the consumer handles duplicates, out-of-order delivery, and missing end events.

**Never simply run `@SpringBootTest` and wait for events to appear after the test method starts.** The startup listener may have already published the event while the context was initializing; if the consumer subscribes too late, the test can miss events or depend on offset/retention timing.

Sample input configuration for the JAR test:

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:5432/task_it
spring.datasource.username=task_it
spring.datasource.password=from-test-secret
spring.cloud.stream.bindings.task-events.destination=it.task.lifecycle
spring.cloud.stream.bindings.job-execution-events.destination=it.batch.jobs
spring.cloud.stream.kafka.binder.brokers=localhost:9092
spring.cloud.task.events.enabled=true
spring.cloud.task.batch.events.enabled=true
spring.cloud.task.batch.fail-on-job-failure=true
~~~

These addresses/credentials are **illustrative values**. With Testcontainers, actual host/port mappings are assigned dynamically by the container runtime; the test harness must pass **the actual mapped endpoints** to the child process. Check Kafka's `advertised.listeners` and TLS/SASL settings if required by your environment.

### 11.1. Identifying Start and End Events

When events carry data for the same `TaskExecution`, you can verify:

- Matching `executionId`/task name aligns with the DB record.
- The start event carries run-identification fields; completion metadata may not be populated yet.
- The completion event carries `endTime`/`exitCode` formatted by the chosen version's serializer.
- There may be **two or more messages** for the same execution ID; never deduplicate solely on execution ID and accidentally drop the end event.
- Never assume global ordering across **two different topics** (Task vs. Batch) is guaranteed.

Under normal runs and stable broker conditions, tests can expect both milestones. However, **missing end events must be tested explicitly**, never treated as proof that the application never ran.

### 11.2. Why Use Kafka Testcontainers?

The Test Binder cannot test:

- Producer authentication and topic ACLs.
- Network connections, timeouts, retries, and advertised listeners.
- Real serialization through the Kafka binder.
- Consumer groups, offsets, partitions, and redelivery after restarts.
- Impact when the producer JVM exits too quickly before messages are flushed/acknowledged per configuration.

Therefore, use Test Binder for **fast contracts**, and real Kafka for **actual interoperability**.

## 12. Infrastructure Failures: Scenario Matrix to Test

Not every failure can be reproduced by making a mock throw an exception. Some failures occur only at transaction, network, or process boundaries:

| Scenario | How to Inject Fault in Test Environment | Evidence to Verify |
| --- | --- | --- |
| DB unavailable when JVM starts | Deliberately block JDBC endpoint before bootstrap | Process fails/times out properly, infrastructure logs present; `TaskExecution` may not exist |
| Missing Task/Batch schema | Disable schema init on empty DB | Explicit failure, never reports success |
| DB drops connection during Step | Proxy cuts JDBC connection during write | Transaction and Job status match reality; no corrupted data |
| Reply lost after COMMIT | Fault injection at boundary or simulate caller losing ACK post-commit | Retry with same business key creates no second row |
| Broker unavailable | Block Kafka endpoint or ACLs | Classify publish/consumer error; do not assume all messages were sent |
| Consumer stopped | Stop consumer, then restart while retention still holds data | Resumes from offset/group without duplicate processing |
| JVM receives `SIGKILL` | Kill process mid-work | End event/`END_TIME` may be missing; runtime and business DB reconcile state |
| Task exceeds deadline | Kill/cancel via scheduler with finite timeout | Distinguish `TIMEOUT`/`UNKNOWN`; handle safe retry |
| Two processes share business key | Launch two JARs/Jobs concurrently | Unique constraint prevents duplicate results |
| Upstream returns 429/503 | Stub API, Toxiproxy, or mock environment | Bounded retry/backoff without runaway call amplification |

**Warning:** never inject network failures, kill processes, or drop tables in environments serving real users. Fault-injection tests must use isolated, time-bounded resources, dedicated test credentials, and recovery scripts.

## 13. Uncertain Commit Outcomes and Idempotent Retries

An exception around `COMMIT` can occur **after the database already persisted changes** but before the application received the reply. Therefore:

~~~text
SQLException / connection reset  !=  guaranteed transaction rollback
~~~

Example two-branch test:

- **Branch A:** failure occurs **before commit**, data was not saved -> retrying the same key is allowed to write for the first time.
- **Branch B:** data committed, then the test deliberately makes the caller "lose the reply" -> retrying the same key must read or write idempotently and **create no extra result**.

Branch B can be simulated in a controlled test: perform a real commit, intentionally return a simulated exception to the caller, then re-launch with the same business key. This tests **the retry policy under uncertain outcomes**, and **does not replace** testing real network faults right inside the `COMMIT` protocol.

In PostgreSQL, a unique key combined with `INSERT ... ON CONFLICT DO NOTHING` prevents duplicate rows. However, if the same key carries a different payload, verify a fingerprint and raise a conflict rather than returning a false success. For multi-table writes or external side effects, verify transaction/outbox/idempotency designs at every boundary.

### Decision Flow When Outcome Is Uncertain

~~~mermaid
flowchart TD
    A["Connection loss / JVM crash / task timeout"] --> B["Extract business key from request"]
    B --> C{"Can query primary data source?"}
    C -->|"No"| D["UNKNOWN, backoff and alert"]
    C -->|"Yes"| E["Read committed data by key"]
    E --> F{"Matching result exists?"}
    F -->|"Yes"| G["Already applied: take no new action"]
    F -->|"Exists with different data"| H["CONFLICT: investigate"]
    F -->|"Not found"| I["Execute idempotent operation with same key"]
    I --> J["Re-verify DB / broker / file"]
    J --> G
~~~

`TaskRepository` is a **supplementary observation source**, not the sole authority for deciding whether business data committed.

## 14. Testing Process Exit Codes and Bootstrap Failures

`@SpringBatchTest` only runs the Job inside the test process's Spring `ApplicationContext`. It does not fully simulate spawning a new JVM and returning an exit code to the operating system. Therefore, **process-level integration tests** are required.

A Java harness can use `ProcessBuilder`:

~~~java
ProcessBuilder builder = new ProcessBuilder(
        "java",
        "-jar", "target/daily-import-task.jar",
        "--businessKey=shop-01|2026-11-24",
        "--attemptId=process-it-1",
        "--failDemo=true");

builder.environment().put("TASK_DB_URL", jdbcUrlFromTestContainer);
builder.environment().put("TASK_DB_USER", testDbUsername);
builder.environment().put("TASK_DB_PASSWORD", testDbPassword);
builder.redirectErrorStream(true);

Process child = builder.start();

// A separate reader must drain stdout/stderr to avoid deadlocking
// if pipe buffers fill while waiting for the process.
boolean finished = child.waitFor(90, TimeUnit.SECONDS);
if (!finished) {
    child.destroy();
    if (!child.waitFor(5, TimeUnit.SECONDS)) {
        child.destroyForcibly();
    }
    throw new AssertionError("Task exceeded test timeout");
}
int exitCode = child.exitValue();
~~~

This is an **illustrative skeleton**, not a standalone test class with full imports, log reading, and cleanup. For real processes, you must:

1. Point to the built JAR path; do not assume the JAR exists when Maven runs `unit` tests.
2. Drain stdout/stderr **concurrently** or redirect to a log file in a dedicated test directory.
3. Never log `TASK_DB_PASSWORD` or Kafka secrets.
4. Capture exit code, PID, duration, logs, and DB state after the process exits.
5. Enforce a global timeout and clean up processes/containers on test failure.
6. Distinguish **non-zero exit from Batch failure**, **non-zero exit from bootstrap failure**, **timeout**, and **`SIGKILL`**.

### 14.1. Assertions for Three Scenarios

| Scenario | Process Exit Code | Task Metadata | Business Result |
| --- | --- | --- | --- |
| Job succeeds | Expected `0` per policy | Completed record when JDBC is ready | Expected row exists |
| Batch Job `FAILED` | Expected non-zero if `fail-on-job-failure=true` is supported/configured properly | Error exit code; may carry failure details | No corrupt or half-written data |
| Very early `ApplicationContext` failure | Usually non-zero | **Record may be absent** because Task infrastructure never started | Depends on failure; never guess |

A failure test that only asserts `exitCode != 0` **is insufficient**; it could pass because the JAR lacked a dependency, had a broken classpath, or couldn't connect to the database rather than failing in the intended Batch Job. Inspect **logs/error codes and Job state in the DB** to verify the true cause.

## 15. Reconciling Batch Failure, Task Failure, and Events

Per Spring Cloud Task documentation, when a Spring Batch Job ends with `BatchStatus.FAILED`, Task exit-code behavior depends on integration policy; set:

~~~properties
spring.cloud.task.batch.fail-on-job-failure=true
~~~

so Spring Cloud Task maps Batch failure to a non-zero exit code in supported versions.

Tests must verify **three distinct outcomes**:

1. `BATCH_JOB_EXECUTION.STATUS = FAILED` with matching `EXIT_CODE`.
2. `TASK_EXECUTION.EXIT_CODE` and the OS exit code reflect failure per configuration.
3. `job-execution-events`/`task-events` receive the appropriate status **when publishing succeeds**.

Do not conclude a Batch Job succeeded merely because `task-events` emitted an end event. Task events and Batch events have different scopes, and message ordering across **two topics** is not guaranteed.

### Listener Ordering Note

Spring Cloud Task provides `onTaskStartup`, `onTaskFailed`, and `onTaskEnd` callbacks. They are invoked around metadata writes; a callback firing **does not prove the subsequent metadata-persistence transaction committed**. Full failure monitoring requires correlating logs/runtime, repositories, and the broker.

## 16. Evaluating Missing, Duplicate, Delayed, and Out-of-Order Events

Events are notifications, not an all-or-nothing distributed transaction. In unstable environments:

- A Task emits a **start** event, then the JVM dies before emitting an **end** event.
- The broker accepts an event yet the producer misses the ACK; retries emit **duplicates**.
- A consumer restarts, re-reads an offset, and reprocesses an event.
- An end event reaches the consumer before the start event across multiple topics/partitions or relays without global ordering.
- The Task completes yet serialization fails, destination is misconfigured, or publish permissions are missing.

### Observation Table on the Consumer Side

~~~sql
CREATE TABLE task_event_observation (
    execution_id BIGINT NOT NULL,
    lifecycle_phase VARCHAR(20) NOT NULL,
    payload_hash CHAR(64) NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (execution_id, lifecycle_phase)
);
~~~

This is an **observability system's business table**, not a table created by Spring Cloud Task. `lifecycle_phase` can be `START` or `END` per your verified parser rules; framework payloads may not include an explicit phase field. If the same key/phase arrives with the same hash, the consumer can ignore it. If the same key/phase arrives with a different hash, determine whether it is a valid update event or a conflict.

Never deduplicate solely on `execution_id`, as doing so can discard the end event after receiving the start event. When an end event stays missing past a threshold, cross-check `TaskRepository` and the scheduler before assuming the task is still running.

## 17. Organizing CI and Cleaning Up Test Data

A good integration suite must produce reproducible results, not just pass on the author's laptop.

### 17.1. Pipeline Grouping

| Stage | Target | Recommended Frequency |
| --- | --- | --- |
| Unit/contract | Validation, mappings, message schemas | Every commit |
| Batch + PostgreSQL Testcontainers | SQL, transactions, unique keys, status | Every PR or commit |
| Kafka + process E2E | Start/end events, `TaskRepository`, exit codes, real binder | Integration pipeline |
| Fault injection | Crashes, timeouts, DB/broker outages, uncertain commits | Pre-release or scheduled |
| Staging smoke | Artifacts, secrets, broker ACLs, schemas, real deployer | Every deployment |

### 17.2. Isolation Principles

- Give each test its own **business key**; clean up data or scope it inside ephemeral containers.
- Avoid fixed `Thread.sleep` waits for Kafka/processes; poll with a deadline and message condition.
- Allocate ports/containers dynamically; never assume `localhost:5432` or `9092` is free.
- Never use production tokens or production DBs in tests.
- Retain logs, container output, `TaskExecution`, and `JobExecution` to diagnose failures; redact secrets.
- Failing tests must clean up their own resources without wiping schemas of parallel tests.
- Separate parallelizable tests from tests requiring exclusive resources; avoid random cross-case races.
- Test connectivity from both **the test JVM** and **child JVMs**, because Docker networking/host ports can differ.

### 17.3. Evidence on Test Failure

An integration test report should capture:

~~~text
testCase=postgresCommitReplyLost
requestId=it-20261124-007
attemptId=2
businessKey=shop-01|2026-11-24
processExit=1
batchStatus=FAILED
taskExitCode=1|UNKNOWN
businessRows=1
receivedTaskEvents=1
reconciliation=ALREADY_APPLIED
~~~

This is an **example report format**, not actual execution output. `UNKNOWN` is not an error to hide; it states explicitly that one data source did not provide sufficient evidence while business data may already exist.

## 18. Acceptance Checklist

- [ ] At least one passing Batch test and one failing Batch test against real JDBC.
- [ ] Verify both `JobExecution`/`StepExecution` **and** committed business data.
- [ ] Retries with the same business key create no duplicates; concurrency tested where applicable.
- [ ] `@SpringBatchTest` and matching utilities verified for your version (5.x/6.x).
- [ ] Consumer contract tests exist using Test Binder or equivalent converter tests.
- [ ] Real Kafka tests exist verifying bindings, destinations, groups, payloads, and broker interaction.
- [ ] Start/end events are never treated as sole proof of business success.
- [ ] Process-level tests exist verifying OS exit codes and bootstrap failures.
- [ ] DB/broker disconnect, timeout, or `SIGKILL` scenarios tested in isolation.
- [ ] For uncertain commits, the system reconciles before blindly retrying.
- [ ] Tests use deadlines/backoff rather than fixed sleeps or lucky ordering.
- [ ] No secrets/PII appear in test logs or captured messages.
- [ ] Task/Batch tables use version-matched schemas; no shared production resources.
- [ ] Test results pinpoint exactly which layer failed: Batch, Task, broker, runtime, or business logic.

## 19. Questions and Exercises

**Question 1.** A `@SpringBatchTest` returns `BatchStatus.COMPLETED`. Does that prove `java -jar` will exit with code `0` and Kafka will receive two Task events? Why or why not?

**Question 2.** Why can a test calling `JobLauncherTestUtils` with the exact same identifying parameters as a completed `JobInstance` be rejected? How does that differ from retrying the whole Task?

**Question 3.** When a Kafka consumer receives a start event but no end event, does that prove the Task is still running? Where should you check?

**Question 4.** A connection reset occurs right at database `COMMIT`. Why is simply mocking `JdbcTemplate.update(...)` to throw an exception insufficient to evaluate retry safety?

**Question 5.** Which testing utility does Spring Batch 6.x change compared to the Spring Batch 5.x examples in this lesson?

**Exercise A — Batch and rollback.** Modify `importStep` to insert a row and then throw an exception **within the same transaction**. Prove the transaction rolls back on PostgreSQL and explain what differs when the transaction manager is misconfigured.

**Exercise B — Process-level exit code.** Package the JAR and run both the success case and `--failDemo=true` via `ProcessBuilder`. Capture exit code, `JobExecution`, and `TaskExecution`; do not rely solely on logs.

**Exercise C — Real Kafka.** Using Kafka Testcontainers, run the task with event listeners enabled and consume `task-events` and `job-execution-events`. Write assertions for run identity and consumer payload parsing.

**Exercise D — Broker outage.** Temporarily make the broker unreachable at Task start or end. Observe actual publishing/exit behavior under your configuration; reconcile with business results and design reconciliation for missing events.

**Exercise E — Unknown commit.** Simulate a DB commit where the caller receives an error. Re-run with the same business key and prove only one result row exists even though Task/Job may record multiple executions.

**Exercise F — Standardizing CI.** Define a test matrix covering schema errors, timeouts, `SIGKILL`, broker redelivery, and two competing processes; specify timeouts, cleanup, suite tags, and failure artifacts.

## 20. Key Takeaways

- **Batch, Task, event, and runtime testing are four distinct scopes.** Passing in one scope does not prove the others work.
- In **Spring Batch 5.x**, `@SpringBatchTest` and `JobLauncherTestUtils` run Jobs/Steps in-context; in **6.x**, verify `JobOperatorTestUtils` and updated APIs.
- Tests must verify **`BatchStatus` + `ExitStatus` + committed data**; only process-level tests measure real JVM exit codes and bootstrap errors.
- `task-events` and `job-execution-events` serve different purposes; Test Binder verifies **contracts**, while Kafka Testcontainers verifies **real binder/broker behavior**.
- **Missing completion events or `TaskExecution.END_TIME` does not prove a task is incomplete**; the JVM may have been killed or metadata persistence may have failed.
- **Connection errors around `COMMIT` have uncertain outcomes.** Safe retries require stable business keys, unique constraints, and reconciliation.
- Reliable integration testing must **isolate resources, enforce deadlines, clean up, capture evidence, and never break production infrastructure**.

## References

- [Spring Batch 5.2 — Testing](https://docs.spring.io/spring-batch/reference/5.2/testing.html): `@SpringBatchTest`, `JobLauncherTestUtils`, `JobRepositoryTestUtils`, Job/Step integration tests.
- [Spring Batch 6.x — Testing](https://docs.spring.io/spring-batch/reference/testing.html): `JobOperatorTestUtils` and API changes from 5.x.
- [Spring Cloud Task — Batch](https://docs.spring.io/spring-cloud-task/reference/batch.html): Task-Batch linking and `spring.cloud.task.batch.fail-on-job-failure`.
- [Spring Cloud Task — Spring Cloud Stream Integration](https://docs.spring.io/spring-cloud-task/reference/stream.html): `task-events`, Batch events, and listener enable/disable settings.
- [Spring Cloud Task — Features](https://docs.spring.io/spring-cloud-task/reference/features.html): `TaskRepository`, `TaskExecution`, and persistence limits on startup errors.
- [Spring Cloud Stream — Testing](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html): Test Binder, `InputDestination`, and `OutputDestination`.
- [Testcontainers for Java — PostgreSQL](https://java.testcontainers.org/modules/databases/postgres/): creating isolated JDBC databases for integration tests.
- [Testcontainers for Java — Kafka](https://java.testcontainers.org/modules/kafka/): testing real Kafka brokers in integration tests.

**Lesson limitations:** Java/YAML snippets are instructional examples for the stated version combination and have not been compiled or executed in a learner repository. Before adopting them, verify your Spring Boot, Spring Cloud Task/Stream, Spring Batch, driver, and serializer versions as well as Docker connectivity in CI. A Content QA pass and thorough integration tests will validate details for your project environment.
