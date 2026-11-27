# Completion Messages, Error Messages, and Length Limits

In the **Results and Exit Codes** chapter of the **SPRING_CLOUD_TASK** module, knowing an application finished running is not enough. Operators also need to know **what outcome was produced**, **why the task failed**, and **where to look up details**. Spring Cloud Task supports this by storing per-run metadata in `TaskRepository`, including `exitCode`, `exitMessage`, and `errorMessage`.

This lesson focuses on two fields that are easy to confuse: the **completion message** (`exitMessage`) that the application can explicitly supply, and the **error message** (`errorMessage`) that Spring Cloud Task infrastructure can record when an exception occurs. Both are subject to **length limits** in the standard JDBC schema. For safe operations, write short, consistent messages and rely on logs or business result stores for full details.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish `exitCode`, `exitMessage`, `errorMessage`, and the logs of a run.
- Set `exitMessage` from `TaskExecutionListener` or `@AfterTask`/`@FailedTask`.
- Explain the precedence of messages set in `onTaskStartup`, `onTaskFailed`, and `onTaskEnd`.
- Identify the reference **2,500-character** limit for `EXIT_MESSAGE` and `ERROR_MESSAGE` in the JDBC schema and the default limit in `SimpleTaskRepository`.
- Design concise messages with stable error codes and correlation IDs for log queries.
- Verify metadata via SQL after a successful run and a failed run.
- Avoid pitfalls such as swallowing exceptions, putting long stack traces into exit messages, losing information due to truncation, and confusing Spring Batch outcomes with Spring Cloud Task outcomes.

## 2. Four Information Sources About an Execution Outcome

Suppose an application generates an end-of-day report. The run has ID `1042`, reads 1,500 transactions, and exports one file. Operators may need to check:

| Source | Example | What question does it answer? |
| --- | --- | --- |
| **`EXIT_CODE` / `exitCode`** | `0`, `1`, or a conventional error code | How did the process or Task infrastructure record success/failure? |
| **`EXIT_MESSAGE` / `exitMessage`** | `COMPLETED;rows=1500;reportId=RPT-42` | What summary outcome should be displayed? |
| **`ERROR_MESSAGE` / `errorMessage`** | A portion of the exception stack trace | Was an exception recorded when the Task failed, and what is its trace? |
| **Logs / business outcome store** | Specific error on row 735, correlation ID, report path | What happened in detail and how can it be fixed? |

Think of their relationship like this:

~~~mermaid
flowchart TD
    A["Spring Cloud Task application"] --> B{"How did it terminate?"}
    B -->|"Completed"| C["Success exitCode"]
    B -->|"Unhandled exception"| D["Failure exitCode per active mechanism"]
    C --> E["TaskExecutionListener may set exitMessage"]
    D --> F["Spring Cloud Task may record errorMessage"]
    D --> E
    E --> G["TaskRepository persists summary when JDBC works"]
    F --> G
    A --> H["Logs with run-id / correlation-id"]
    G --> I["Dashboard or SQL lookup"]
    H --> I
~~~

These channels play **complementary roles**:

- `exitCode` fits automated scheduler decisions.
- `exitMessage` fits a readable, structured one-line summary.
- `errorMessage` helps locate exception traces, though it may not hold the entire stack trace.
- Logs and business data provide detailed context with search capabilities and their own retention policies.

**Do not use the mere presence of `exitMessage` or a `"SUCCESS"` string to conclude success when `exitCode` or business criteria indicate otherwise.**

## 3. `exitMessage`: Application-Provided Completion Message

`TaskExecution` has an `exitMessage` property; Spring Cloud Task lets application code update it through `TaskExecutionListener`. For example, a reporting task might write:

~~~text
COMPLETED;reportId=RPT-42;rows=1500
~~~

The message should be a **summary**, not a full report, large JSON payload, or multi-line log dump. Use short, consistently delimited fields, such as:

| Scenario | Recommended `exitMessage` |
| --- | --- |
| Success | `COMPLETED;rows=1500;reportId=RPT-42` |
| No data to process | `COMPLETED;rows=0;reason=NO_DATA` |
| Rejected due to invalid parameter | `FAILED;code=INVALID_DATE;runId=run-1042` |
| Transient error reading data source | `FAILED;code=UPSTREAM_TIMEOUT;runId=run-1043` |
| Work only partially completed | `FAILED;code=PARTIAL_WRITE;runId=run-1044` |

There is no mandatory global format for `exitMessage`. Operations teams can pick `key=value`, compact JSON, or a short status code. Whichever format you choose, **define its semantics, length cap, and sensitive-data masking policy**.

### Information That Should Not Go into `exitMessage`

- Access tokens, passwords, API keys, connection strings with secrets.
- Full customer profiles, personal identifiers, or sensitive input data.
- Entire stack traces or per-record failure details.
- Large JSON/XML blobs, lists of thousands of IDs, or output file contents.
- Paths containing secrets or URLs with query strings carrying confidential data.

Instead, record non-sensitive `runId`, `reportId`, or `errorCode` values; use those identifiers to look up logs or result data in the proper store.

## 4. `errorMessage`: Infrastructure-Recorded Error Trace

`TaskExecution.errorMessage` differs from `exitMessage` in **origin** and **intended purpose**. According to the Spring Cloud Task documentation, when an exception terminates the Task and publishes an `ApplicationFailedEvent`, the framework can store the exception's stack trace in `errorMessage`.

Example content might begin like this:

~~~text
java.lang.IllegalArgumentException: invalid businessDate
  at com.example.task.ReportRunner.run(ReportRunner.java:...)
  ...
~~~

This is an **illustrative example**, because how stack traces, class names, line numbers, and retained portions are recorded depends on the version, error, and storage limits. Keep in mind:

1. A non-`0` exit code **does not guarantee** `ERROR_MESSAGE` is populated. For example, a task may emit an exit code via its own policy without an unhandled exception.
2. `errorMessage` can be empty if the application dies before Task infrastructure is active, the JVM is killed, or the `TaskRepository` connection fails.
3. Real stack traces are often longer than the column capacity; **never assume the full trace resides in the database**.
4. Exceptions can carry sensitive information in their messages; control exception construction, database read permissions, and logs.

`errorMessage` should not be used by the application to manually push an entire report. Use `exitMessage` for intentional summaries, `errorMessage` for framework-captured exception traces, and the logging system for diagnostic details.

## 5. Listener Lifecycle and Message Precedence Rules

Spring Cloud Task supports the `TaskExecutionListener` interface with three callbacks:

| Callback | Conceptual timing | Can be used to |
| --- | --- | --- |
| `onTaskStartup(TaskExecution)` | When the Task starts, after infrastructure creates the run record per version behavior | Attach an initial message or context |
| `onTaskFailed(TaskExecution, Throwable)` | When an unhandled exception occurs, before the end callback | Set a concise error code, error source, and correlation ID |
| `onTaskEnd(TaskExecution)` | Before the final status update to the repository | Write a completion summary or finalize the message |

The three equivalent method annotations in a bean are `@BeforeTask`, `@FailedTask`, and `@AfterTask`.

When multiple callbacks call `setExitMessage(...)`, the Spring Cloud Task documentation describes this precedence order:

1. **`onTaskEnd`** has the highest precedence if it sets a message.
2. **`onTaskFailed`** takes precedence over `onTaskStartup` in failure cases.
3. **`onTaskStartup`** acts as the baseline value when no later callback overrides it.

For example: the failure callback sets `FAILED;code=TIMEOUT`, yet the end callback unconditionally sets `COMPLETED`. The final message can become `COMPLETED` even though the job failed. That is a message-design bug **very likely to mislead dashboards**.

### Practical Rules

- Only set `COMPLETED` in `onTaskEnd` if no error message has already been set.
- On failure, set a concise error code in `onTaskFailed`; do not overwrite it in `onTaskEnd`.
- Never alter the meaning of an exit code merely by writing a message that looks like success.
- Listeners should stay lightweight—do not call slow APIs or run business logic that can fail further.
- Do not let an exception inside a listener erase or corrupt the original failure outcome; guard listener code carefully.

## 6. Java Example: Writing Completion and Error Messages

We build a demo task that executes once and records different summaries depending on the outcome. The example works with compatible Spring Boot and Spring Cloud Task versions; it requires `spring-cloud-starter-task`, `spring-boot-starter`, and a JDBC datasource if you want to query metadata after the process exits.

### 6.1. Application Code

Create `src/main/java/com/example/task/ResultMessageApplication.java`:

~~~java
package com.example.task;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.task.configuration.EnableTask;
import org.springframework.cloud.task.listener.TaskExecutionListener;
import org.springframework.cloud.task.repository.TaskExecution;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableTask
public class ResultMessageApplication {

    public static void main(String[] args) {
        SpringApplication.run(ResultMessageApplication.class, args);
    }

    @Bean
    RunStats runStats() {
        return new RunStats();
    }

    @Bean
    ApplicationRunner reportRunner(RunStats stats) {
        return args -> {
            stats.processedRows.set(2);

            if (args.containsOption("fail")) {
                throw new IllegalStateException(
                        "Simulated failure while processing report");
            }

            stats.processedRows.set(3);
            System.out.println("Report generated: rows=3");
        };
    }

    @Bean
    TaskExecutionListener resultMessageListener(RunStats stats) {
        return new TaskExecutionListener() {

            @Override
            public void onTaskFailed(TaskExecution execution,
                                     Throwable throwable) {
                // Controlled summary; do not put stack traces into exitMessage.
                execution.setExitMessage(
                        "FAILED;code=DEMO_ERROR;rows="
                        + stats.processedRows.get());
            }

            @Override
            public void onTaskEnd(TaskExecution execution) {
                // onTaskEnd runs after onTaskFailed: preserve the error message.
                if (execution.getExitMessage() == null) {
                    execution.setExitMessage(
                            "COMPLETED;rows="
                            + stats.processedRows.get());
                }
            }
        };
    }

    static class RunStats {
        final AtomicInteger processedRows = new AtomicInteger();
    }
}
~~~

**Explanation:**

- `reportRunner` is the short-lived job. With `--fail`, it throws an exception; otherwise it prints the completion output.
- `RunStats` is a bean holding the processed row count to demonstrate how the listener retrieves summary stats.
- `onTaskFailed` writes `FAILED;code=DEMO_ERROR;rows=2` to `exitMessage` and **does not swallow the exception** thrown in the runner.
- `onTaskEnd` populates the completion message only when no prior message exists, avoiding overwriting `FAILED`.
- `errorMessage` is left for Spring Cloud Task's exception-recording mechanism when lifecycle and repository conditions allow.

In this example, every `setExitMessage` call creates a short message. In real applications, collect metrics via a dedicated service and ensure statistics reflect **successfully committed** outcomes, not merely rows read or attempted.

### 6.2. Using Annotations Instead of the Interface

If you prefer methods on a regular Spring bean, you can write:

~~~java
package com.example.task;

import org.springframework.cloud.task.listener.annotation.AfterTask;
import org.springframework.cloud.task.listener.annotation.FailedTask;
import org.springframework.cloud.task.repository.TaskExecution;
import org.springframework.stereotype.Component;

@Component
class MessageHooks {

    @FailedTask
    public void failed(TaskExecution execution, Throwable cause) {
        execution.setExitMessage("FAILED;code=UNEXPECTED");
    }

    @AfterTask
    public void completed(TaskExecution execution) {
        if (execution.getExitMessage() == null) {
            execution.setExitMessage("COMPLETED");
        }
    }
}
~~~

This is an **alternative** to the `TaskExecutionListener` in Section 6.1. Pick **one** mechanism for the same message so multiple listeners do not overwrite one another in hard-to-predict order. Both operate on the same `TaskExecution` object before final data is written to the repository.

## 7. JDBC Configuration to Inspect Across Multiple Runs

To read records after the JVM stops, use PostgreSQL or a persistent JDBC database. For local practice, **file-based** H2 is more convenient than `mem:` H2 because the file preserves metadata across processes (following H2 file access rules).

Minimal Maven dependencies for H2:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-task</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

The project must manage versions using a **compatible Spring Boot BOM/parent and Spring Cloud BOM**. Use `spring-boot-maven-plugin` to package an executable JAR; `pom.xml` determines the artifact name and version.

Create `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: result-message-demo
  main:
    web-application-type: none
  datasource:
    url: jdbc:h2:file:./result-message-task-db
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
  cloud:
    task:
      name: result-message-demo
      initialize-enabled: true
      closecontextEnabled: true

logging:
  level:
    org.springframework.cloud.task: INFO
~~~

With `jdbc:h2:file:./result-message-task-db`, H2 stores data on disk in the runtime environment. In production, use a shared database, manage schemas with migrations, and do not rely on auto-creating tables on every task startup. Never commit real passwords in source configuration files.

### 7.1. Successful Run

~~~bash
./mvnw clean package
java -jar target/result-message-demo-0.0.1-SNAPSHOT.jar
~~~

On Windows PowerShell, use `.\mvnw.cmd clean package` and your actual JAR name. Expected business output:

~~~text
Report generated: rows=3
~~~

When Spring Cloud Task writes metadata successfully, the execution's `EXIT_MESSAGE` field can be:

~~~text
COMPLETED;rows=3
~~~

### 7.2. Failed Run

~~~bash
java -jar target/result-message-demo-0.0.1-SNAPSHOT.jar --fail
~~~

The runner throws `IllegalStateException`. Expected outcome at the Task layer, assuming infrastructure initialized and repository writes succeeded:

- `EXIT_MESSAGE` is `FAILED;code=DEMO_ERROR;rows=2`.
- `ERROR_MESSAGE` may contain part of the exception's stack trace.
- `EXIT_CODE` reflects failure per Spring Boot/Spring Cloud Task and runtime environment behavior.

Do not expect logs or `ERROR_MESSAGE` contents to match character-for-character, as stack traces depend on Java version, library versions, and where the error was thrown.

### 7.3. Querying Results

Once processes have stopped, open the file-based H2 database with a SQL tool using the **same file path**. Under the standard schema, you can run:

~~~sql
SELECT TASK_EXECUTION_ID,
       TASK_NAME,
       START_TIME,
       END_TIME,
       EXIT_CODE,
       EXIT_MESSAGE,
       ERROR_MESSAGE
FROM TASK_EXECUTION
ORDER BY TASK_EXECUTION_ID DESC;
~~~

To check stored lengths, use H2's `LENGTH` function (supported by many other DBMSs too):

~~~sql
SELECT TASK_EXECUTION_ID,
       LENGTH(EXIT_MESSAGE)  AS EXIT_MESSAGE_LENGTH,
       LENGTH(ERROR_MESSAGE) AS ERROR_MESSAGE_LENGTH
FROM TASK_EXECUTION
ORDER BY TASK_EXECUTION_ID DESC;
~~~

If the `TASK_EXECUTION` table or records are missing, check the schema, datasource, connection permissions, Task configuration, and errors occurring before context completion. **Do not assume the absence of a record means the program never launched.**

## 8. Length Limits: What Does 2,500 Characters Mean in Practice?

In the currently published Spring Cloud Task JDBC schema documentation, the `TASK_EXECUTION` table specifies:

| Column | Reference type | Reference length limit |
| --- | --- | ---: |
| `TASK_NAME` | `VARCHAR` | 100 |
| `EXIT_MESSAGE` | `VARCHAR` | **2,500** |
| `ERROR_MESSAGE` | `VARCHAR` | **2,500** |

The Javadoc for `SimpleTaskRepository` (API 3.0.4) also declares `MAX_EXIT_MESSAGE_SIZE` and `MAX_ERROR_MESSAGE_SIZE` constants with a default of **2,500**, alongside `MAX_TASK_NAME_SIZE = 100`.

**Interpret these limits within the proper scope:**

- These are values from the **referenced schema and API version**; your project must verify the DDL scripts and implementation for **the exact version in use**.
- Application limits and database column limits are related but not strictly identical. Databases may enforce length by characters, bytes, or engine-specific rules.
- Do not assume every framework version handles oversized data identically. One release may bound/truncate text before writing; the database can still reject oversized values if the schema or configuration mismatches.
- When truncated, the dropped portion may be the exact root-cause detail, correlation ID, or stack frame you needed.
- Arbitrarily widening the column in DDL **does not guarantee** repository code will pass more characters. Conversely, raising the code limit without updating the schema can trigger write errors.

### 8.1. Practical Business Limits to Follow

Do not try to use all 2,500 characters for `exitMessage`. An internal convention might be:

| Data type | Suggested cap in example | Where to store |
| --- | --- | --- |
| Summary `exitMessage` | 200–500 characters | `TaskRepository` |
| Stable error code | 20–80 characters | `exitMessage` and logs |
| Correlation ID | Short identifier, no secrets | `exitMessage` and logs |
| Full stack trace | Do not cram into a short message | Access-controlled logging system |
| Result files, failed record lists | Per business data requirements | Appropriate database or object storage |

The 200–500 figures here are **recommended conventions**, not mandatory Spring Cloud Task properties.

### 8.2. Unicode and String Length

With Vietnamese text or emojis, "2,500 characters" does not always correspond to "2,500 bytes." Java's `String.length()` counts UTF-16 code units; some characters such as emojis use two units. Databases may count differently.

Therefore, to stay safe:

1. Keep messages substantially shorter than the column limit.
2. Avoid storing long free-form user text in the repository.
3. When truncation is necessary, avoid splitting a Unicode surrogate pair.
4. Test data with Vietnamese diacritics and special characters against **the actual production JDBC driver and database**.

Example truncation helper by **Unicode code point**, useful for a short display convention:

~~~java
static String abbreviate(String text, int maxCodePoints) {
    if (text == null) {
        return null;
    }

    int count = text.codePointCount(0, text.length());
    if (count <= maxCodePoints) {
        return text;
    }

    int end = text.offsetByCodePoints(0, maxCodePoints - 1);
    return text.substring(0, end) + "…";
}
~~~

This function demonstrates avoiding mid-surrogate splits; it **does not replace** verifying actual DBMS byte/length limits. When using it, require `maxCodePoints >= 1` and validate arguments at the calling layer.

### 8.3. Should You Increase the Limit to 10,000?

Consider it only with a clear requirement, because you must evaluate **repository code, schema, and reading tools together**:

- Does your framework/version support configuring max sizes via custom APIs? `SimpleTaskRepository` exposes `setMaxExitMessageSize` and `setMaxErrorMessageSize` setters in the referenced API, though you **must not invent unverified YAML property names for your version**.
- DDL requires migrations and testing across all supported databases.
- Can dashboards and APIs handle long messages without leaking sensitive data?
- Are storage and query costs reasonable?

In most systems, **keeping `exitMessage` brief and routing detailed logs to an appropriate store** is far easier to operate.

## 9. Preserving Full Long Errors: Correlation IDs and Logs

A stack trace can be tens of thousands of characters long. If `ERROR_MESSAGE` keeps only part of it, finding the root cause becomes difficult. Design around **one shared correlation ID** across data sources.

Example:

~~~text
runId=report-2026-11-24-001
exitMessage=FAILED;code=UPSTREAM_TIMEOUT;runId=report-2026-11-24-001
logKey=runId:report-2026-11-24-001
~~~

Workflow:

1. The orchestrator generates `runId` and logs the execution request.
2. The application includes `runId` in logs, or links it with `TASK_EXECUTION_ID` once Task infrastructure is created.
3. The listener writes a summary with a stable error code into `EXIT_MESSAGE`.
4. The framework writes `ERROR_MESSAGE` within limits when an exception is observed.
5. Operators use `runId` and `TASK_EXECUTION_ID` to look up detailed logs, inspect the failing resource, and remediate.

Do not depend solely on `TASK_EXECUTION_ID` to join records: if the JVM crashes before the repository writes a row, that ID may not exist. A scheduler-generated ID lets you investigate even cases with **no `TaskExecution`**.

When logging exceptions, ensure messages and input data do not leak sensitive details; apply appropriate redaction, retention, and access controls. Storing errors in a database does not replace log security policies.

## 10. Common Failure Scenarios

### 10.1. Exit Message Says "COMPLETED" Despite a Failure Exit Code

This can happen when `onTaskEnd` unconditionally calls `setExitMessage("COMPLETED")` even after `onTaskFailed`. Fix: set the completion message only when no failure has been recorded, use consistent status conventions, and verify the business outcome.

### 10.2. `ERROR_MESSAGE` Is Empty Despite a Non-Zero Exit Code

Not every failure code comes from an `ApplicationFailedEvent` or an exception observed by the framework. Check `ExitCodeGenerator`/`ExitCodeExceptionMapper` if used, logs, and how the process actually terminated. If the task was killed, error persistence may not have completed.

### 10.3. `ERROR_MESSAGE` Contains Only the Beginning of the Stack Trace

Column limits and persistence logic can cap the content. Look up the full trace by `runId` in the logs instead of treating truncated metadata as the sole diagnostic source.

### 10.4. Saving a Long Message Fails the Repository Update

If the string exceeds column capacity or repository/schema settings mismatch, the final write can fail. Prevent this with concise message conventions, testing on the real DB, controlled migrations, and monitoring JDBC errors.

### 10.5. A Listener Throws an Exception Itself

A listener can introduce a new error and disrupt callback execution or exit code handling. Do not let a message-writing listener perform failure-prone operations such as HTTP calls or large file writes. Keep it to lightweight work over already-available data, and never call `System.exit` inside a listener.

### 10.6. No `TaskExecution` Record Exists

If `ApplicationContext` fails to bootstrap, the task may never create a record. Or JDBC failed, the schema is missing, or the datasource points to the wrong database. Check startup logs and external monitoring before concluding the task never ran.

### 10.7. Exit Message Shows Processed Rows, Yet the Report Is Missing Rows

An in-memory counter may reflect rows read rather than rows **committed**. Define business acceptance criteria, verify transactions, and record metrics only after results are confirmed.

## 11. Coordinating with Spring Batch and Exit Codes

In an application using both **Spring Cloud Task** and **Spring Batch**:

- `TaskExecution` describes **one application run** and fields `exitCode`, `exitMessage`, and `errorMessage`.
- `JobExecution` and `StepExecution` describe **batch** processing state; they belong to Spring Batch's `JobRepository`.
- Batch's `BatchStatus` and `ExitStatus` are **not identical** to Spring Cloud Task's `EXIT_CODE` or `EXIT_MESSAGE`.
- If a Batch job fails but the application handles or maps statuses improperly, **the Task exit code may still be 0**. In supported Spring Cloud Task versions, `spring.cloud.task.batch.fail-on-job-failure=true` propagates Batch failures to the Task exit code according to library policy.

Example policy in an environment requiring a failed job to also fail the Task:

~~~yaml
spring:
  cloud:
    task:
      batch:
        fail-on-job-failure: true
~~~

Verify the property against your exact version and run a **Batch FAILED → Task exit non-zero** test. Do not simply overwrite `EXIT_MESSAGE` with `FAILED` to simulate a Batch failure; the orchestrator needs an exit code that accurately reflects status.

When building the final summary, you may include `jobExecutionId` and `batchStatus` in `exitMessage` if free of sensitive data, staying within length limits. Logs and Batch's `JobRepository` remain the place to inspect per-step causes.

## 12. Testing Critical Scenarios

A meaningful integration test suite should run against a JDBC repository (at minimum file-based H2; ideally a production-equivalent database) and verify:

| Scenario | What to reconcile |
| --- | --- |
| Runner completes | Success `EXIT_CODE`; accurate `EXIT_MESSAGE` summary; `END_TIME` populated |
| Runner throws exception | Failure `EXIT_CODE`; error code in `EXIT_MESSAGE`; `ERROR_MESSAGE` may hold trace |
| Both `@AfterTask` and `@FailedTask` exist | Completion hook does not overwrite failure message with `COMPLETED` |
| Very long `exitMessage` string | Check current version behavior, DB result, errors/truncation; correlation ID preserved |
| Long stack trace | Confirm full trace exists in logs while metadata plays only a supporting role |
| Error before `ApplicationContext` creation | Scheduler/logs still detect failure even if `TaskRepository` lacks a record |
| PostgreSQL schema and repository version mismatch | Catch JDBC failures before deployment rather than relying solely on H2 results |
| Spring Batch job `FAILED` | Task exit code and Batch status match the configured policy |

**For simulated failures**, pass an option like `--fail` in the Java example; you do not need to trigger real production infrastructure failures to test length controls.

## 13. Safe Operations Checklist

- [ ] Align on the meaning of `EXIT_CODE`, `EXIT_MESSAGE`, `ERROR_MESSAGE`, and business status.
- [ ] Keep `exitMessage` short, with a stable error code and correlation ID, and free of secrets or sensitive data.
- [ ] Ensure summary-writing listeners do not overwrite failure messages set in `onTaskFailed`.
- [ ] Verify `EXIT_MESSAGE`/`ERROR_MESSAGE` column limits against the **actual version's** schema.
- [ ] Maintain complete logs with run identifiers, appropriate retention, and access control.
- [ ] Ensure the scheduler/container captures exit codes and statuses even when `TaskRepository` has no record.
- [ ] Ensure error codes or unhandled exceptions are never swallowed to produce false success.
- [ ] When rerunning, protect business data with deduplication keys and an idempotency strategy.
- [ ] When using Spring Batch, verify the mapping from Batch status to Task exit code.

## 14. Questions and Exercises

**Question 1.** If `EXIT_CODE = 1`, `EXIT_MESSAGE = "COMPLETED"`, and `ERROR_MESSAGE` contains an exception, what will you check first? Why should you not trust `exitMessage` alone?

**Question 2.** If the database declares `EXIT_MESSAGE VARCHAR(2500)`, why should business messages still stay around 200–500 characters?

**Question 3.** `@FailedTask` sets `FAILED;code=INPUT_INVALID`. `@AfterTask` runs afterward and sets `COMPLETED`. What might the final message be? Fix the logic to preserve the failure cause.

**Question 4.** Why can `ERROR_MESSAGE` be empty even when the process failed? How does a database connection drop differ from a business logic failure?

**Exercise A — Structured messages:** Extend the Java example to set `exitMessage` in the format `status=...;rows=...;runId=...`. Generate `runId` from the orchestrator and pass it to the application. Keep values within internal length conventions.

**Exercise B — Length limits:** Trigger an error with a long message in a test environment, then inspect the full log and `ERROR_MESSAGE` in the repository. Compare sizes, note your framework/database versions, and avoid assuming all versions truncate identically.

**Exercise C — Batch integration:** Run a failing Batch job; compare `BatchStatus`, `ExitStatus`, `TaskExecution.exitCode`, `exitMessage`, and the process exit code. Apply the `fail-on-job-failure` policy if supported by your version.

## 15. Key Takeaways

- **`exitCode`** is a numeric status signal; **`exitMessage`** is an application-supplied summary; **`errorMessage`** is an infrastructure-captured error trace on exception paths.
- `TaskExecutionListener` supports setting `exitMessage`. Among callbacks, `onTaskEnd` can overwrite messages from `onTaskFailed`, so failure messages must be protected.
- The reference JDBC schema currently documents **2,500** for `EXIT_MESSAGE` and `ERROR_MESSAGE`; `SimpleTaskRepository` in API 3.0.4 also defaults to 2,500. Always verify your actual version and DDL.
- **Metadata is a bounded summary.** Full stack traces, per-record details, and large outputs belong in logs or business stores linked by correlation IDs.
- A failed process can lack `ERROR_MESSAGE` or even lack a `TaskExecution` if startup or metadata persistence fails.
- When integrating Spring Batch, verify the policy mapping Batch status to Task exit code; never treat wording in `exitMessage` as a substitute for status checks.

## References

- [Spring Cloud Task Reference — Features: Task Execution, Exit Messages, and Task Execution Listener](https://docs.spring.io/spring-cloud-task/docs/current/reference/html/features.html).
- [Spring Cloud Task — Task Repository Schema](https://docs.spring.io/spring-cloud-task/docs/current/reference/html/appendix-task-repository-schema.html), describing `TASK_EXECUTION.EXIT_MESSAGE` and `TASK_EXECUTION.ERROR_MESSAGE`.
- [SimpleTaskRepository API (Spring Cloud Task 3.0.4)](https://docs.spring.io/spring-cloud-task/docs/current/apidocs/org/springframework/cloud/task/repository/support/SimpleTaskRepository.html), declaring size limits and related setter APIs.
- [Constant Field Values (Spring Cloud Task 3.0.4)](https://docs.spring.io/spring-cloud-task/docs/current/apidocs/constant-values.html), 2,500 default values.
- [TaskExecutionListener API](https://docs.spring.io/spring-cloud-task/docs/current/apidocs/org/springframework/cloud/task/listener/TaskExecutionListener.html), end/failure callback contract.

When implementing, verify these details against **the actual Spring Cloud Task, Spring Boot, and DDL versions in use**; character counts and handling of oversized strings can vary across releases.
