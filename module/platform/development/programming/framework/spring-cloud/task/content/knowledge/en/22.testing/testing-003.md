# Integration Testing the Task Lifecycle with Spring Boot

## 1. Why Test the Full Spring Cloud Task Lifecycle?

**Spring Cloud Task** helps build **finite-lived** Spring Boot applications: starting up, executing work via `ApplicationRunner` or `CommandLineRunner`, persisting execution metadata to **`TaskRepository`**, and terminating. In production, an application may be invoked manually, run on a schedule, launched as a Kubernetes Job, or orchestrated by Spring Cloud Data Flow.

A unit test calling `runner.run(...)` directly only verifies the Java logic inside the runner. It **does not prove** that Spring Boot actually boots properly, that Spring Cloud Task persists metadata, or that the process reports failures accurately. The **Testing** chapter therefore requires **integration tests** that exercise the real Spring Boot lifecycle.

Suppose a `daily-reconciliation` application accepts `--businessDate=2026-11-23`. We want to verify:

1. Spring creates the `ApplicationContext` and required beans.
2. `TaskRepository` creates a `TaskExecution` **before the runner does its work**.
3. The runner receives the arguments and performs the work exactly once per launch.
4. After the runner finishes, the repository has the appropriate `END_TIME` and `EXIT_CODE`.
5. If the runner throws an unhandled exception, the metadata reflects the failure when the framework is able to record it.
6. An early context bootstrap failure **is not confused** with a task that started and then failed.
7. When running under a Kubernetes Job or scheduler, the OS exit code and business outcome are reconciled against the metadata.

**Lesson goal:** build integration tests with **JUnit 5, Spring Boot Test, and H2** for the happy path; write **failure-path** tests by launching `SpringApplication` in a controlled manner; know when to move to **PostgreSQL/Testcontainers** and real process tests.

> The Java examples target **Spring Boot 3.x + Spring Cloud Task 3.x + JUnit Jupiter**, using the common `TaskExplorer` and `TaskExecution` APIs of that generation. Always select a BOM compatible with your project version. This lesson includes self-contained code to illustrate the workflow, which does not substitute for running tests against your actual dependencies.

## 2. Understand the Exact Lifecycle Order Before Writing Assertions

In Spring Cloud Task, metadata is created after context bootstrap succeeds and **before Spring Boot runners execute**. When runners complete normally, the framework updates the execution record; when an `ApplicationFailedEvent` occurs on a supported path, the framework also attempts to record the failure outcome.

~~~mermaid
sequenceDiagram
    participant Test as Integration test
    participant Boot as SpringApplication
    participant Task as Spring Cloud Task
    participant DB as TaskRepository (JDBC)
    participant Runner as ApplicationRunner

    Test->>Boot: @SpringBootTest loads ApplicationContext
    Boot->>Task: Initialize beans and lifecycle
    Task->>DB: INSERT TaskExecution / START_TIME
    Boot->>Runner: run(ApplicationArguments)
    Runner->>DB: Check active execution
    Runner-->>Boot: Complete
    Boot->>Task: ApplicationReadyEvent
    Task->>DB: UPDATE END_TIME / EXIT_CODE
    Boot-->>Test: Context ready, run @Test
    Test->>DB: TaskExplorer reads final result
~~~

| Milestone | Verifiable Signal | Assumption to Avoid |
| --- | --- | --- |
| Context bootstrap complete | `TaskExplorer` and `TaskRepository` beans exist | All business logic has already run |
| Before runner | `START_TIME` set, `END_TIME`/`EXIT_CODE` typically `null` | Process has definitely finished |
| Runner executing | Active record can be queried | `TaskRepository` automatically tracks per-item progress |
| After successful runner | `END_TIME` set and normal exit code is `0` | External systems received every side effect |
| Unhandled runner error | `SpringApplication.run(...)` fails, framework attempts to record error | Every error type guarantees a `TaskExecution` |
| JVM killed or very early bootstrap failure | Final update or any record at all may be missing | `END_TIME IS NULL` always means the process is still alive |

**Two cases must be clearly separated:**

- **Runner fails after `TaskExecution` is created:** you have a basis to assert `ERROR_MESSAGE`, exit code, and end time.
- **Application fails before context bootstrap progresses far enough:** Spring Cloud Task **does not guarantee** a `TaskExecution` will be created. Tests must not expect every startup error to produce a row in `TASK_EXECUTION`.

### Testing Strategy Diagram

~~~mermaid
flowchart TD
    A["Argument conversion / validation logic"] --> B["Runner/service unit tests"]
    C["Spring Boot context + Task lifecycle"] --> D["@SpringBootTest + H2"]
    E["Runner throws exception"] --> F["Separate SpringApplication.run + JDBC readback"]
    G["Real DB DDL / privileges / dialect"] --> H["PostgreSQL/Testcontainers"]
    I["Exit code / SIGTERM / container"] --> J["Run JAR in process or Kubernetes Job"]
    B --> K["Layered test suite"]
    D --> K
    F --> K
    H --> K
    J --> K
~~~

## 3. What to Verify in `TaskExecution`

`TaskExplorer` provides an API for querying execution history; it fits integration tests well because it verifies **both writing and reading** against a real metadata store rather than mocking the repository.

| Property | What It Verifies |
| --- | --- |
| `getExecutionId()` | Assigned ID used for log correlation |
| `getTaskName()` | Task received the configured name |
| `getStartTime()` | Repository recorded start time |
| `getEndTime()` | Completion phase was updated |
| `getExitCode()` | Framework-recorded outcome, usually `0` when the runner succeeds |
| `getErrorMessage()` | Error details when the framework handles `ApplicationFailedEvent` |
| `getArguments()` | Launch arguments persisted according to version and configuration |
| `getExitMessage()` | Additional message from listener mechanisms, if any |

Do not hardcode `executionId=1` in assertions: ID generation sequences depend on the database, prior test runs, and other processes. When an isolated test uses its own database, you can fetch the latest run via `TaskExplorer.getLatestTaskExecutionForTaskName("...")` or capture the actual ID inside the runner.

**Reading back after `SpringApplication` finishes** is the right moment to expect `END_TIME` to be saved. Conversely, calling `TaskExplorer` **inside the runner or inside `onTaskEnd`** may observe metadata before the final update has occurred.

## 4. Dependencies for the Test Environment

Maven example, with Boot/Cloud versions managed by the project's **compatible** BOM:

~~~xml
<dependencies>
    <!-- Finite-lived task application -->
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-task</artifactId>
    </dependency>

    <!-- JDBC metadata and test data -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>

    <!-- Test: JUnit Jupiter, AssertJ, Spring Boot Test -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <!-- Embedded DB for simple integration tests -->
    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

In production, if PostgreSQL is used, include the appropriate PostgreSQL driver at runtime. **H2 makes tests fast, but it does not prove that every SQL statement, transaction, data type, or privilege is compatible with production PostgreSQL.**

### Choosing an Isolated Metadata Store

Each test group should have its own database, for example:

~~~properties
spring.datasource.url=jdbc:h2:mem:task_lifecycle_success;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.cloud.task.initialize-enabled=true
spring.cloud.task.closecontextEnabled=false
spring.cloud.task.name=it-lifecycle-success
spring.main.web-application-type=none
~~~

**Why choose these values?**

- `jdbc:h2:mem:task_lifecycle_success` creates a **named** embedded database, isolated from other tests' databases.
- `DB_CLOSE_DELAY=-1` keeps the H2 database alive within **the same test JVM** even after the last connection closes. Useful for failure tests reading back the repository after context shutdown; do not use it as a durable production store.
- `initialize-enabled=true` lets Spring Cloud Task initialize the `TaskRepository` schema for the lab environment.
- `closecontextEnabled=false` keeps the context open so JUnit and Spring Test can access beans after the runner finishes.
- `task.name` sets a distinct identifier for runs in this test.
- `web-application-type=none` avoids starting an unnecessary web server.

**Note:** if your project has another auto-configured database/migration setup, coordinate so only **one component** manages the schema. Tests must never accidentally run against a production database via inherited environment variables.

## 5. Testing the Happy Path with `@SpringBootTest`

`@SpringBootTest` creates the `ApplicationContext` via `SpringApplication`. Therefore, it triggers `ApplicationRunner`/`CommandLineRunner` beans just like a real launch. Use `webEnvironment=NONE` to indicate a CLI task rather than a web endpoint.

In the example, a **probe bean** records events for the test to verify. This lives in **test JVM memory** purely to observe callback ordering. Durable metadata must still be read from `TaskExplorer`.

### 5.1. Complete JUnit 5 Code

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.task.configuration.EnableTask;
import org.springframework.cloud.task.listener.TaskExecutionListener;
import org.springframework.cloud.task.repository.TaskExecution;
import org.springframework.cloud.task.repository.TaskExplorer;
import org.springframework.context.annotation.Bean;

@SpringBootTest(
    classes = TaskLifecycleSuccessIT.TestTaskApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    args = "--businessDate=2026-11-23",
    properties = {
        "spring.cloud.task.name=it-lifecycle-success",
        "spring.cloud.task.closecontextEnabled=false",
        "spring.cloud.task.initialize-enabled=true",
        "spring.datasource.url=jdbc:h2:mem:task_lifecycle_success;DB_CLOSE_DELAY=-1",
        "spring.datasource.username=sa",
        "spring.datasource.password=",
        "spring.main.web-application-type=none"
    }
)
class TaskLifecycleSuccessIT {

    @Autowired TaskExplorer taskExplorer;
    @Autowired Probe probe;

    @Test
    void completesLifecycleAndPersistsMetadata() {
        // When @Test runs, SpringApplication and the runner have already finished.
        assertThat(probe.events)
                .containsExactly("startup", "runner", "end");
        assertThat(probe.businessDate)
                .isEqualTo("2026-11-23");

        TaskExecution execution =
                taskExplorer.getTaskExecution(probe.executionId);

        assertThat(execution).isNotNull();
        assertThat(execution.getTaskName())
                .isEqualTo("it-lifecycle-success");
        assertThat(execution.getStartTime()).isNotNull();
        assertThat(execution.getEndTime()).isNotNull();
        assertThat(execution.getExitCode()).isEqualTo(0);
        assertThat(execution.getArguments())
                .contains("--businessDate=2026-11-23");
    }

    static class Probe {
        final List<String> events =
                new CopyOnWriteArrayList<>();
        volatile long executionId;
        volatile String businessDate;
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableTask
    static class TestTaskApplication {

        @Bean
        Probe probe() {
            return new Probe();
        }

        @Bean
        TaskExecutionListener probeListener(Probe probe) {
            return new TaskExecutionListener() {

                @Override
                public void onTaskStartup(TaskExecution task) {
                    probe.events.add("startup");
                }

                @Override
                public void onTaskEnd(TaskExecution task) {
                    probe.events.add("end");
                }

                @Override
                public void onTaskFailed(
                        TaskExecution task, Throwable error) {
                    probe.events.add("failed");
                }
            };
        }

        @Bean
        ApplicationRunner sampleRunner(
                TaskExplorer explorer, Probe probe) {
            return args -> {
                // TaskExecution already exists BEFORE the runner.
                TaskExecution running =
                        explorer.getLatestTaskExecutionForTaskName(
                                "it-lifecycle-success");

                if (running == null
                        || running.getStartTime() == null
                        || running.getEndTime() != null
                        || running.getExitCode() != null) {
                    throw new IllegalStateException(
                            "Task lifecycle not initialized");
                }

                probe.executionId = running.getExecutionId();
                probe.businessDate =
                        args.getOptionValues("businessDate").get(0);
                probe.events.add("runner");
            };
        }
    }
}
~~~

### 5.2. What Was Actually Tested?

This is more than a "contextLoads" test:

- Spring Boot built the context and enabled Task infrastructure via `@EnableTask`.
- Spring Cloud Task wired `TaskRepository` and `TaskExplorer` against **real H2**.
- `TaskExecution` **was persisted before the runner**: the runner itself read the record and verified `END_TIME` and `EXIT_CODE` were still empty.
- `ApplicationRunner` received `--businessDate=...` from `@SpringBootTest(args=...)`.
- The listener was registered and recorded the `startup -> runner -> end` sequence.
- After the runner, the test read back **the assigned execution ID** to verify the final result was persisted.
- Exit code `0` in the error-free case reflects the framework outcome; **it does not by itself prove that all external side effects outside the database succeeded**.

In an application with multiple runners, ordering across runners must be managed via `@Order`/`Ordered` when dependencies exist; the lab intentionally uses **a single runner** for deterministic ordering. Do not assume an ordering between different runners that the framework does not guarantee.

### 5.3. Why Use a Dedicated `@SpringBootConfiguration` Class?

If a test auto-scans the entire production application, it might:

- Call real APIs or send emails from production runners.
- Start secondary schedulers and workers.
- Read non-test secrets or databases.
- Trigger a Spring Batch Job or listener with unintended side effects.

A small nested configuration inside the test preserves **real lifecycle infrastructure** while replacing business work with a probe. This is a **scoped integration test**, not a full-system smoke test.

**Do not mock `TaskRepository` or `TaskExplorer` in this test**: doing so stops verifying real JDBC schema writes and reads. You may mock **external services** called by the runner while keeping the real repository active.

## 6. Testing the Failure Path: Runner Throws an Exception

When a runner throws an unhandled exception, `SpringApplication.run(...)` throws an error and **`@SpringBootTest` cannot reach a normal `@Test` method** using that same failing configuration. Therefore, failure-path testing is more convenient when **explicitly invoking `SpringApplication.run(...)`** inside a standalone JUnit test.

We use a **uniquely named** H2 database with `DB_CLOSE_DELAY=-1`. Once Spring Boot tears down the context after failure, the test can still connect from outside the context to verify the committed metadata.

### 6.1. JUnit 5 Code Testing Failure After Context Initialization

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

import org.junit.jupiter.api.Test;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.cloud.task.configuration.EnableTask;
import org.springframework.context.annotation.Bean;

class TaskLifecycleFailureIT {

    @Test
    void runnerFailureIsRecordedAfterBootstrap() throws Exception {
        String url =
                "jdbc:h2:mem:task_lifecycle_failure;DB_CLOSE_DELAY=-1";

        // SpringApplication creates TaskExecution, then the runner throws an exception.
        assertThatThrownBy(() -> SpringApplication.run(
                FailingTaskApplication.class,
                "--spring.main.web-application-type=none",
                "--spring.cloud.task.name=it-lifecycle-failure",
                "--spring.cloud.task.initialize-enabled=true",
                "--spring.cloud.task.closecontextEnabled=false",
                "--spring.datasource.url=" + url,
                "--spring.datasource.username=sa",
                "--spring.datasource.password="
        )).hasRootCauseInstanceOf(IllegalStateException.class);

        // The context may already be closed, so use a separate JDBC connection to read.
        try (Connection connection =
                    DriverManager.getConnection(url, "sa", "");
             PreparedStatement query =
                    connection.prepareStatement("""
                        SELECT TASK_EXECUTION_ID, END_TIME,
                               EXIT_CODE, ERROR_MESSAGE
                        FROM TASK_EXECUTION
                        WHERE TASK_NAME = ?
                        ORDER BY TASK_EXECUTION_ID DESC
                        """)) {

            query.setString(1, "it-lifecycle-failure");

            try (ResultSet rows = query.executeQuery()) {
                assertThat(rows.next()).isTrue();
                assertThat(rows.getLong("TASK_EXECUTION_ID"))
                        .isPositive();
                assertThat(rows.getTimestamp("END_TIME"))
                        .isNotNull();
                assertThat(rows.getObject("EXIT_CODE", Integer.class))
                        .isNotNull()
                        .isNotEqualTo(0);
                assertThat(rows.getString("ERROR_MESSAGE"))
                        .contains("Simulated runner failure");
            }
        }
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableTask
    static class FailingTaskApplication {

        @Bean
        ApplicationRunner failingRunner() {
            return args -> {
                throw new IllegalStateException(
                        "Simulated runner failure");
            };
        }
    }
}
~~~

**Limitation of the assertions above:** the test expects **a failure path after `TaskExecution` has been created** and Spring Cloud Task updates metadata via `ApplicationFailedEvent`. How exceptions and exit codes are encoded can depend on `ExitCodeExceptionMapper` and version; we assert **non-zero** rather than hardcoding a custom error code.

If the application dies **before a working context exists**, the database/schema is missing, or the repository itself fails, do not expect `ERROR_MESSAGE` to be present. In those cases, verify the startup exception and infrastructure logs rather than forcing tests to look for a record that was never written.

### 6.2. Why Not Call `System.exit` Inside Tests?

Calling `System.exit(...)` directly inside the JUnit JVM can **terminate the entire test runner**, not just a single test method. To test OS exit codes, launch the task as **a separate process** or use a process-isolation test framework.

`SpringApplication.run(...)` in the test above verifies **lifecycle and metadata**; it **does not verify the actual exit code observed by the shell or Kubernetes**. That is the purpose of smoke tests covered later.

## 7. Testing Callback Ordering and Observable State

Spring Cloud Task provides `TaskExecutionListener` with:

- `onTaskStartup(TaskExecution)`: task startup phase.
- `onTaskFailed(TaskExecution, Throwable)`: when the framework handles an uncaught error.
- `onTaskEnd(TaskExecution)`: task completion phase on the corresponding lifecycle path.

Testing model:

| Scenario | Expected Callback Sequence During Normal Lifecycle Handling |
| --- | --- |
| Runner succeeds | `onTaskStartup -> runner -> onTaskEnd` |
| Runner throws exception | `onTaskStartup -> runner fails -> onTaskFailed -> onTaskEnd` |
| Exception caught and ignored by runner | `onTaskStartup -> runner returns -> onTaskEnd`; `onTaskFailed` **not guaranteed** |
| Context bootstrap fails too early | Possibly **no** `TaskExecution` callbacks at all |
| Process receives SIGKILL/OOM kill | End callbacks and final repository update **not guaranteed** |

**Subtle detail:** `onTaskEnd` often executes **before `TaskRepository` commits final metadata**. Consequently, calling `TaskExplorer` **inside `onTaskEnd`** and asserting `END_TIME` is already populated is a badly timed assertion. Verify callback ordering using probes or logs, and verify final persisted results by querying **after `SpringApplication.run` returns**.

If the application registers multiple listeners, a listener throwing an exception may affect how remaining listeners are invoked. In lifecycle tests, keep listeners simple without network or timing dependencies; test listener error handling in a separate case rather than polluting the basic happy path.

### Swallowed Errors Cause False-Green Tests

~~~java
@Bean
ApplicationRunner badRunner(ExternalService service) {
    return args -> {
        try {
            service.exportReport();
        }
        catch (Exception ex) {
            // Log and stay silent: the runner still finishes normally!
        }
    };
}
~~~

With this code, Spring Cloud Task may record a success exit code even though `exportReport()` failed. Integration tests must include cases where external services fail and verify **the runner reports failure properly**, such as rethrowing the exception or mapping errors to an exit code via supported mechanisms.

## 8. Testing `ApplicationArguments` and Parameter Data

A task commonly accepts parameters such as run date, tenant, or dry-run mode. Tests must verify:

1. The runner reads the right values and applies validation rules.
2. Runtime configuration does not accidentally overwrite parameters.
3. `TaskRepository` persists the argument list in metadata tables per the version's contract.
4. No sensitive data is written to command lines or test reports.

`@SpringBootTest(args={"--businessDate=2026-11-23"})` passes arguments into the test's `SpringApplication`. Inside the runner:

~~~java
@Bean
ApplicationRunner validatingRunner() {
    return arguments -> {
        var dates = arguments.getOptionValues("businessDate");

        if (dates == null || dates.size() != 1) {
            throw new IllegalArgumentException(
                    "Required exactly one businessDate");
        }

        java.time.LocalDate day =
                java.time.LocalDate.parse(dates.get(0));

        // Execute business logic for day.
    };
}
~~~

A SQL metadata verification query:

~~~sql
SELECT e.TASK_EXECUTION_ID, e.TASK_NAME, p.TASK_PARAM
FROM TASK_EXECUTION e
JOIN TASK_EXECUTION_PARAMS p
  ON p.TASK_EXECUTION_ID = e.TASK_EXECUTION_ID
WHERE e.TASK_NAME = 'it-lifecycle-success'
ORDER BY e.TASK_EXECUTION_ID DESC;
~~~

Never pass `--password=...`, tokens, or sensitive connection strings as test arguments: the framework can persist them into `TASK_EXECUTION_PARAMS`. For integration tests against real environments, use properly managed secrets/environment variables.

If the task also launches **Spring Batch**, distinguish Spring Boot arguments from **Batch `JobParameters`** per your launcher/version. `TaskExecution.getArguments()` alone does not prove `JobParameters` were received and used by the Batch job.

## 9. Transactions, `TaskRepository`, and Business Outcomes

Three concerns must never be conflated:

- **Task metadata transaction**: writing `START_TIME`, `END_TIME`, `EXIT_CODE` in `TaskRepository`.
- **Business transaction**: writing orders, report outputs, or summary tables.
- **OS/process lifecycle**: JVM and container exiting with a status code.

A good integration test verifies **both metadata and essential business effects**. For example, a task might finish its runner while the result table remains un-updated because code swallowed an exception. Conversely, business data might commit successfully while the process is killed before updating `TaskRepository`, leaving `END_TIME` blank.

### 9.1. Testing Business Data in the Same DataSource

If the runner writes to a `reconciliation_result` table, create the business schema using a test-specific migration before the task runs, then after the task finishes:

~~~sql
SELECT WORK_KEY, RESULT_COUNT, COMPLETED_AT
FROM reconciliation_result
WHERE WORK_KEY = 'tenant-a:2026-11-23';
~~~

Combined with:

~~~sql
SELECT TASK_EXECUTION_ID, TASK_NAME,
       START_TIME, END_TIME, EXIT_CODE, ERROR_MESSAGE
FROM TASK_EXECUTION
WHERE TASK_NAME = 'daily-reconciliation'
ORDER BY TASK_EXECUTION_ID DESC;
~~~

Verification data must use a **work key** invariant across retries. `TASK_EXECUTION_ID` changes on every launch; never use it as a unique identifier to conclude that a given day's work is already complete.

### 9.2. Avoid `@Transactional` on Tests If You Want to Observe Real Commits

In Spring tests, `@Transactional` on a test method typically creates a transaction rolled back at the end of the test. However, the runner executed **during context creation before `@Test` started**; the runner's business transactions do not necessarily participate in the test method's transaction.

Therefore:

- **Do not assume** `@Transactional` on the test automatically rolls back all effects from the runner.
- Use an isolated database/schema per test or perform controlled cleanup.
- Never run tests against someone else's shared database.
- To verify committed data, query using an appropriate transaction/connection **after the runner finishes**.
- When metadata and business data use two separate `DataSource`s, never assume they share a single atomic transaction.

## 10. H2 vs. PostgreSQL/Testcontainers

H2 is a sensible choice for lab tests verifying basic lifecycle behavior, but it does not fully test production PostgreSQL SQL dialect, isolation, locking, sequences, or permissions.

| Test Type | Database | Primary Verification |
| --- | --- | --- |
| Runner unit test | No DB needed, or mock | Business/validation rules |
| Context integration test | Uniquely named H2 | Bean wiring, lifecycle, `TaskRepository` read/write |
| Real-DB integration test | PostgreSQL via Testcontainers or staging DB | Schema DDL, SQL dialect, transactions, sequences, mappings |
| Process-level smoke test | Persistent PostgreSQL | Process exit code, `closecontextEnabled`, logs and metadata after JVM exit |
| Deployment test | Kubernetes Job/CronJob on test cluster | Env/Secret/ServiceAccount, timeouts, retries, Pod/Job status |

### 10.1. Testcontainers Guidance

With **JUnit Jupiter + Testcontainers PostgreSQL**, a test can start a PostgreSQL container and inject the JDBC URL/username/password into the Spring Boot test via `@DynamicPropertySource`.

Sample datasource configuration snippet:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest(
    classes = TaskLifecycleSuccessIT.TestTaskApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = {
        "spring.cloud.task.name=it-lifecycle-success",
        "spring.cloud.task.closecontextEnabled=false",
        "spring.cloud.task.initialize-enabled=true"
    }
)
class PostgresDataSourceWiringExample {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("task_test")
                    .withUsername("test_user")
                    .withPassword("test_password");

    @DynamicPropertySource
    static void datasource(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username",
                postgres::getUsername);
        registry.add("spring.datasource.password",
                postgres::getPassword);
    }

    @Test
    void databaseIsAvailable() {
        // Add real TaskExplorer/TaskExecution assertions here.
    }
}
~~~

**This is a wiring illustration, not a complete copy-pasteable test.** You must add the appropriate Testcontainers `junit-jupiter` and `postgresql` dependencies along with the PostgreSQL JDBC driver; `TaskLifecycleSuccessIT.TestTaskApplication` and configuration must be accessible from the new test. Because the example **reuses the runner looking for `it-lifecycle-success`**, the task name property matches the runner. On a fresh PostgreSQL container, `initialize-enabled=true` lets Spring Cloud Task create test tables; if you switch to `initialize-enabled=false`, you must apply **the exact-version Spring Cloud Task schema via Flyway/Liquibase/test migrations** before the Task lifecycle writes metadata. Failing to do so will cause test startup to fail.

With newer Spring Boot releases supporting `@ServiceConnection`, you can use a more concise wiring setup when compatible dependencies are present, but verify versions and pick a single `DataSource` configuration mechanism.

### 10.2. When Is Real PostgreSQL Testing Mandatory?

- Using `TASK_SEQ`/sequences and dialect-specific DDL.
- Multiple concurrent task processes, single-instance locking, or `TASK_LOCK` state.
- `TaskRepository` and business `DataSource` are separate.
- Real PostgreSQL roles/permissions, TLS, or schema/`search_path` are required.
- Testing transaction isolation, deadlocks, retries, and idempotency.
- The project recently upgraded Spring Cloud Task/Boot/Batch versions or changed schemas.

A "green" H2 test is never enough to approve production database migrations without compatibility testing.

## 11. Real Process and Exit Code Smoke Tests

`@SpringBootTest` verifies the lifecycle at the `SpringApplication` level, but it does not prove that the JVM **actually exits** or that the container receives **the right error code**. Issues like non-daemon threads, schedulers, thread pools, and `System.exit` may not surface fully inside an in-JVM test.

### 11.1. Running the JAR in a Separate Process

With a built JAR and a dedicated staging database, operators can run:

~~~bash
java -jar target/daily-reconciliation.jar --businessDate=2026-11-23
echo $?
~~~

The output of `echo $?` is the exit code **observed by the shell** on Linux/macOS. On PowerShell, inspect `$LASTEXITCODE` per shell rules. In a CI pipeline, capture the process exit code programmatically rather than just grepping for an `INFO Completed` line.

When testing that the task closes its own context, configure:

~~~properties
spring.cloud.task.closecontextEnabled=true
~~~

**Unlike `@SpringBootTest`:** this setting is suitable for verifying that a finite process closes its context and releases resources; in in-JVM Spring Test suites, it is typically kept `false` so the test framework can still access the context.

### 11.2. Java `ProcessBuilder` Pattern for CI Integration

Illustrative example launching a packaged JAR, assuming an external test database is available:

~~~java
import java.io.File;
import java.time.Duration;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;

class TaskProcessSmokeExample {

    void runJarAndCheckExitCode() throws Exception {
        ProcessBuilder builder = new ProcessBuilder(
                "java",
                "-jar",
                "target/daily-reconciliation.jar",
                "--businessDate=2026-11-23"
        );

        // Pass only controlled test DB configuration.
        builder.environment().put(
                "SPRING_PROFILES_ACTIVE", "integration");
        builder.redirectErrorStream(true);
        builder.redirectOutput(
                ProcessBuilder.Redirect.to(
                        new File("target/task-smoke.log")));

        Process process = builder.start();
        boolean ended = process.waitFor(
                Duration.ofMinutes(2).toMillis(),
                TimeUnit.MILLISECONDS);

        if (!ended) {
            process.destroy();
            if (!process.waitFor(10, TimeUnit.SECONDS)) {
                process.destroyForcibly();
            }
            throw new AssertionError("Task process timed out");
        }

        assertThat(process.exitValue()).isZero();

        // Next: query the test DB by work key/TaskExecution ID.
    }
}
~~~

This is an **illustrative pattern**, not yet wired as a ready-to-run `@Test`. Ensure the `target` directory and JAR exist, an integration DB profile is available, data cleanup is handled, and logs/CI artifacts are retained appropriately. Failure tests run the JAR or arguments designed to fail in a controlled way and assert a non-zero exit code.

**Never call `System.exit(...)` directly from the JVM running JUnit.** If a running task hits a timeout or `SIGKILL`, `TaskRepository` may not finish writing `END_TIME`; in those cases, tests must cross-check the database, OS exit status, and logs.

## 12. Spring Batch Inside Spring Cloud Task

If a task application launches a Spring Batch Job, tests must distinguish **two lifecycles**:

| Spring Cloud Task | Spring Batch |
| --- | --- |
| `TaskExecution`: one application launch | `JobExecution`: one Job execution |
| `TaskRepository` stores start/end/process exit code | `JobRepository` stores Job and Step state |
| `TaskExplorer` reads task metadata | `JobExplorer` reads `JobExecution`/`StepExecution` |
| Task success does not automatically imply all Steps succeeded | Job/Step status follows its own rules |

Recommended assertions:

- `TaskExecution` is created when the task context starts.
- The corresponding `JobExecution` has `BatchStatus.COMPLETED` or `FAILED` matching the scenario.
- `StepExecution` shows expected `READ_COUNT`, `WRITE_COUNT`, and `SKIP_COUNT`.
- If the task must wait for the Batch Job to finish, the runner **does not return early** while the Job runs asynchronously.
- A failed Batch job maps properly to the task/process exit code per integration settings (for example, `spring.cloud.task.batch.fail-on-job-failure` in supported branches).
- On restart, Batch's `ExecutionContext` and business data remain consistent, not just `TaskExecution.END_TIME` being populated.

To avoid launching the Batch Job twice in integration tests, establish **one clear launcher mechanism**: Spring Boot's auto-run or a controlled `JobLauncher` call by the test/application. Do not unintentionally let Spring Boot auto-run a single Job while an `ApplicationRunner` also calls `JobLauncher.run(...)`.

## 13. Avoiding Flaky Tests and Side Effects

### 13.1. Context Caching and H2 Data

Spring Test caches the `ApplicationContext` across test methods/classes with equivalent configurations. This means:

- Runners typically execute **when the context is created**, not before **every `@Test` method**.
- A new test method **does not automatically create a new `TaskExecution`** when reusing a cached context.
- A named in-memory H2 database with `DB_CLOSE_DELAY=-1` retains data for the lifetime of the test JVM.
- Sharing the same JDBC URL across classes running in parallel can mix test data.

For isolation, use unique database names per scenario or separate Testcontainers/DB schemas; clean up according to a defined strategy. Use `@DirtiesContext` only when context recreation is genuinely required and you understand the startup cost.

### 13.2. Do Not Assume Results Are Ready in `@BeforeEach`

With `@SpringBootTest`, the context and runners may already have run **before `@BeforeEach` executes**. Therefore, seeding source data in `@BeforeEach` can be **too late** for the runner. Load test data via migrations/`@Sql` at the proper time, a pre-runner setup bean, or dedicated test configuration; verify the exact execution order of those mechanisms.

If you need to vary inputs per test method, consider **calling the service directly in unit/service integration tests**, while testing lifecycle through **dedicated `SpringApplication` launches** or separate processes.

### 13.3. Avoid `sleep` and Wall-Clock Time in Assertions

Do not write:

~~~java
Thread.sleep(500);
assertThat(taskExplorer.getTaskExecution(id).getEndTime())
        .isNotNull();
~~~

This causes flaky tests when CI is slow or the database experiences latency. For a synchronous task, wait for **`SpringApplication.run` to return** before asserting metadata; for asynchronous work, use **controlled completion mechanisms** such as `CountDownLatch`/`CompletableFuture` or polling with explicit timeouts and conditions.

If business requirements prohibit exiting before async work finishes, the runner must **await the actual result**; simply making tests wait longer does not fix an application lifecycle bug.

### 13.4. Avoid Real Queues/Brokers or External Services When Unnecessary

An integration test for the **`TaskRepository` lifecycle** does not need to send real emails, call a payment gateway, or create real Kubernetes Pods. Mock/fake non-essential external boundaries while using a **real JDBC repository**. When end-to-end verification is required, build a separate smoke test using staging infrastructure and least-privilege credentials.

## 14. Failure Scenarios to Include in the Test Suite

| Scenario | Setup | What to Verify |
| --- | --- | --- |
| **Happy path** | Runner returns normally | `TaskExecution` exists, start/end set, exit code `0` |
| **Invalid arguments** | Missing `--businessDate` | Runner reports error; repository records failure if lifecycle started |
| **Unhandled exception** | Runner throws `IllegalStateException` | `ApplicationFailedEvent`, error metadata if persisted |
| **Swallowed error** | Intentionally catch exception without rethrowing | Identify design flaw: exit code may falsely report success |
| **Listener failure** | Callback throws in a dedicated test setup | Verify error path and other callbacks without polluting the happy path |
| **DB unreachable** | Wrong JDBC URL / DB stopped | `TaskExecution` may not be created; check bootstrap exception |
| **Schema uninitialized** | `initialize-enabled=false`, empty DB | Context fails due to missing tables; do not force end-time assertions |
| **Insufficient SQL privileges** | Read-only role without write permission | Startup or metadata update fails |
| **Process timeout/SIGTERM** | JAR in separate process, finite deadline | OS exit, logs, and potential incomplete metadata |
| **Task re-run** | Two launches with the same work key | Two execution IDs, no duplicate business outcome |
| **Unfinished async work** | Runner spawns async work and returns | Detect premature `TaskExecution` completion; fix by awaiting completion |
| **Spring Batch Job failure** | Batch Step throws exception | Accurate Job/Step metadata, verified task exit-code mapping |

**Not every failure requires a heavyweight test.** Unit tests handle validation variants, integration tests handle lifecycle/schema, process tests handle JVM behavior, and deployment tests handle the runtime environment.

## 15. CI Workflow and Pre-Release Testing

A testing pipeline can be ordered as follows:

1. **Unit tests:** run fast with no DB or infrastructure dependencies.
2. **Task lifecycle integration tests:** use H2 to verify context, runner, listener, and `TaskRepository`/`TaskExplorer`.
3. **Database compatibility tests:** use PostgreSQL/Testcontainers with real schema migrations, checking DB roles/permissions when relevant.
4. **Process smoke tests:** run the standalone JAR to verify exit codes, timeouts, and `closecontextEnabled`.
5. **Staging deployment tests:** run Kubernetes Job/Scheduler/SCDF in a test environment, cross-checking metadata, logs, and business results.
6. **Release checks:** confirm image/binary version, secret configuration, migrations, and rollback paths.

~~~mermaid
flowchart LR
    U["Unit tests"] --> I["@SpringBootTest + H2"]
    I --> D["PostgreSQL / Testcontainers"]
    D --> P["Process smoke test"]
    P --> K["Kubernetes / Scheduler staging"]
    K --> R{"Ready for release?"}
    R -->|Yes| Y["Monitored release"]
    R -->|No| N["Fix issues + re-run"]
~~~

### Quality Checklist

- [ ] Use JUnit 5 and `@SpringBootTest(webEnvironment=NONE)` for task context tests.
- [ ] Enable `@EnableTask` or Task lifecycle configuration matching the actual version.
- [ ] Use a real JDBC `TaskRepository`; do not mock the repository in lifecycle integration tests.
- [ ] Use an **isolated** database/schema; never touch production databases.
- [ ] Set `closecontextEnabled=false` in tests that must keep `ApplicationContext` open.
- [ ] Verify the runner observes an existing `TaskExecution` before processing.
- [ ] After the runner finishes, verify `END_TIME`, `EXIT_CODE`, and `TASK_NAME`.
- [ ] Include a test where the runner throws an exception and read metadata back via a separate connection.
- [ ] Account for the fact that early bootstrap failures may leave no `TaskExecution`.
- [ ] Assert **business outcomes**, not only metadata.
- [ ] Never use `Thread.sleep` as the primary synchronization mechanism.
- [ ] Ensure context caching and H2 state do not cause tests to interfere with one another.
- [ ] Test PostgreSQL schemas/transactions and permissions when production differs from H2.
- [ ] Include process-level tests for exit codes and thread/context cleanup.
- [ ] If Spring Batch is integrated, verify both `JobRepository`/`JobExplorer` and `TaskRepository`/`TaskExplorer`.
- [ ] Include retry scenarios with work keys/idempotency to prevent duplicate processing.
- [ ] Never leak secrets via arguments, logs, JDBC URLs, or test reports.

## 16. Summary

**Integration testing the Task lifecycle with Spring Boot** requires running through `SpringApplication` and a **real `TaskRepository`**, rather than merely calling a runner method in a unit test. On the happy path, `@SpringBootTest` lets you observe Spring Cloud Task **recording start metadata before the runner**, then updating metadata when the runner completes. On the failure path, you can launch `SpringApplication.run(...)` in a controlled test and read H2 via an independent connection to verify failure state.

Three test scopes must remain distinct: **lifecycle inside `ApplicationContext`**, **committed metadata/business outcomes**, and **actual process exit codes**. H2 keeps tests fast; PostgreSQL/Testcontainers verifies schemas and transactions; process/Kubernetes smoke tests verify shutdown, timeouts, and exit codes. When Spring Batch is present, test `JobExecution`/`StepExecution` separately as well.

A reliable test suite reports success only when **lifecycle metadata is recorded accurately, business outcomes are verified, failures are surfaced clearly, and re-runs produce no duplicate effects**.

### References

- [Spring Cloud Task — Features: Task lifecycle, TaskExecution, and closing context](https://docs.spring.io/spring-cloud-task/reference/features.html)
- [Spring Cloud Task — Getting started and TaskRepository with H2](https://docs.spring.io/spring-cloud-task/reference/getting-started.html)
- [Spring Cloud Task — TaskExplorer API](https://docs.spring.io/spring-cloud-task/docs/current/apidocs/org/springframework/cloud/task/repository/TaskExplorer.html)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Spring Boot — ApplicationRunner / CommandLineRunner](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
- [Spring Batch — JobRepository, JobExplorer, and restarts](https://docs.spring.io/spring-batch/reference/domain.html)
