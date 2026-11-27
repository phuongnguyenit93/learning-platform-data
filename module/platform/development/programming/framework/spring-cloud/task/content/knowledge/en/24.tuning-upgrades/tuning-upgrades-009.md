# Verifying Batch, Stream, and Deployer Integration Behavior After Upgrades

In the **Tuning and Upgrades** chapter of the **SPRING_CLOUD_TASK** module, updating a library version does not end at a successful compile. A Spring Cloud Task application may start on a new JDK yet **lose its link with Spring Batch**, **stop emitting proper events over Spring Cloud Stream**, or **be accepted by the Deployer without actually spawning a runnable process**. These failures often appear only when testing against production-like databases, brokers, deployment platforms, and historical data.

This lesson establishes a **pre- and post-upgrade verification workflow**, grounded in observable behavior, across three integration paths:

- **Batch:** `TaskExecution` ↔ `JobExecution`/`StepExecution`, identifying parameters, Job status, checkpoints, and JVM exit codes.
- **Stream:** bindings, destinations, payload schemas, start/end events, consumer groups, redelivery, and short-lived task startup behavior.
- **Deployer:** artifacts/versions/images, arguments, environment variables, permissions, resources, execution IDs, pod/process status, and remote partitioning workers if used.

This is a **behavior-verification and migration-strategy** lesson, not a fixed list of properties for every Spring Boot/Spring Cloud release train. When upgrading across major generations—especially between Spring Boot 3/Spring Batch 5 and Spring Boot 4/Spring Batch 6—consult **version-specific migration guides for each component** before applying sample code.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Build a compatibility matrix across **JDK – Spring Boot – Spring Cloud Task – Spring Batch – Spring Cloud Stream – binder – Deployer – database**.
2. Capture a baseline of the old version's behavior to compare against the upgraded build using identical inputs and business criteria.
3. Verify `TaskExecution`-to-`JobExecution` linking via `TaskBatchExecutionListener` and the corresponding metadata tables.
4. Detect changes affecting `JobParameters`, `JobInstance`, restarts, checkpoints, and Batch schemas.
5. Confirm `task-events` and `job-execution-events` bindings, destinations, headers/serializers, and consumers do not drift in contract after upgrades.
6. Prove that a request accepted by the Deployer **actually** spawns a process, finishes, and returns the right exit code.
7. Test remote partitioning, broker/DB disconnects, duplicate runs, and early `ApplicationContext` creation failures.
8. Set performance comparison thresholds, canary strategies, deployment gates, and feasible rollback paths.
9. Design auditable test evidence: artifact digest, profiles, execution IDs, business keys, logs, metrics, SQL, and broker messages.

## 2. Why Is a "Green Build" Not Enough?

A single Task run can traverse multiple components:

~~~mermaid
flowchart LR
    A["Scheduler / SCDF API"] --> B["Spring Cloud Deployer"]
    B --> C["JVM / Pod running Spring Cloud Task"]
    C --> D["Spring Batch Job / Step"]
    D --> E["Business DB"]
    D --> F["JobRepository"]
    C --> G["TaskRepository"]
    C --> H["Stream binding: task-events"]
    D --> I["Stream binding: job-execution-events"]
    H --> J["Kafka / RabbitMQ"]
    I --> J
    J --> K["Monitoring consumer"]
    F --> L["Outcome reconciliation"]
    G --> L
    E --> L
    K --> L
~~~

After an upgrade, any boundary can shift even when business logic stays untouched:

| Boundary | Possible Symptom | Why Compilation Misses It |
| --- | --- | --- |
| Boot ↔ Task | Lifecycle listeners not triggered; missing `TaskExecution` | Auto-configuration conditions changed by classpath/properties |
| Task ↔ Batch | `JobExecution` exists without link to `TaskExecution` | Missing `TaskBatchExecutionListener` bean or dependency module |
| Batch ↔ JDBC | Old Jobs fail to restart; metadata queries error | DDL and `JobParameters` serialization changed |
| Task/Batch ↔ Stream | No events, or consumer fails to parse | Binding names, content types, serializers, binders, and runtime config |
| Deployer ↔ artifact | Launcher returns an ID but pod never starts | Image pull, Java runtime, manifest, security context, resource limits |
| Deployer ↔ worker | Partition worker spawns but cannot find `StepExecution` | Wrong datasource, `JobRepository`, token, or worker arguments |
| Task ↔ scheduler | Process finishes but exit code does not reflect Batch failure | `fail-on-job-failure` mapping policy or context shutdown behavior |
| Runtime ↔ monitoring | Missing end event or `END_TIME` | SIGKILL, OOM, broker/DB failure, task too short for telemetry export |

Rule: **every integration path must have an observable behavior test at the real boundary**, not just unit/mocking tests of a single class.

## 3. Lock Down the Version Matrix Before Changing Dependencies

Do not upgrade individual Spring libraries piecemeal by guesswork. Spring Cloud uses **release train BOMs** engineered for compatibility with a specific Spring Boot line; Spring Batch and Stream normally inherit versions through the ecosystem's dependency management.

Examples of combinations published in Spring Cloud compatibility tables in the 2025–2026 period (re-verify when picking a specific release):

| Spring Cloud Release Train | Spring Boot Generation | Planning Notes |
| --- | --- | --- |
| `2025.0.x` | `3.5.x` | Spring Boot 3 generation; check the exact managed Spring Batch line |
| `2025.1.x` | `4.0.x` and supported `4.1.x` per train release | May involve major transitions Boot 3 → 4 and Batch 5 → 6 |
| `2026.0.x` | `4.2.x` per corresponding train docs | Consult Task/Stream/Batch/Binder docs for the exact release |

**This is not a forever-guaranteed list of supported combinations.** Use [Spring Cloud's official compatibility table](https://spring.io/projects/spring-cloud/) and per-release notes to verify **each patch release**.

Create a version manifest before making changes:

~~~text
service                 daily-import-task
old-artifact            daily-import-task:1.8.3
new-artifact            daily-import-task:2.0.0
old-java                (fill in from baseline)
new-java                (fill in from target)
spring-boot             old -> new
spring-cloud-train      old -> new
spring-cloud-task       old -> new
spring-batch            old -> new
spring-cloud-stream     old -> new
kafka-binder            old -> new
spring-cloud-deployer   old -> new
scdf-server             old -> new, if present
postgresql-driver       old -> new
schema-task             old -> target
schema-batch            old -> target
kafka-cluster           broker + protocol + ACL
runtime                 k8s/CF/local + cluster/version
image-digest            sha256:<new digest>
~~~

Do not guess loaded versions from `pom.xml` numbers alone: inspect **the dependency tree**, BOM precedence, packaging plugins, and the actual artifacts inside the image. Example Maven commands to inspect the dependency tree, run in **a project permitted to build**:

~~~bash
./mvnw dependency:tree
./mvnw help:effective-pom
~~~

Do not use this output in place of running an integration test. It only confirms **dependencies and build configuration**.

### Questions to Answer Before Selecting a Target

- What minimum Java version / image/JDK does the target Spring Boot release require?
- Does the target Spring Cloud Task release support that exact Boot release?
- Is the target Stream binder compatible with the broker, Kafka client, and serialization?
- Does the target Spring Batch release introduce DDL migrations or `JobParameters` changes?
- Does the target Deployer/Spring Cloud Data Flow accept the new artifact and legacy deployment properties?
- Which historical data **must** remain readable or restartable after the upgrade?
- Do multiple worker versions share one `JobRepository`/`TaskRepository`? Is mixed-version support verified?

## 4. Capturing a Baseline with a "Golden Run"

Before upgrading, run the old version in staging with a controlled sample dataset and save full traces. For example, a reconciliation job for `businessKey=shop-01|2026-11-24|v1`.

A **golden run** should capture:

| Baseline Data | Example | Source |
| --- | --- | --- |
| Exact artifact | Version, image digest, or JAR hash | Registry/build manifest |
| Inputs | Business key, Batch parameters, data snapshot, runId | API/scheduler |
| Launch receipt | Request ID, execution ID, external runtime ID | SCDF/Deployer |
| Task metadata | `TASK_EXECUTION_ID`, `START_TIME`, `END_TIME`, `EXIT_CODE` | `TaskRepository` |
| Batch metadata | `JOB_INSTANCE_ID`, `JOB_EXECUTION_ID`, `STATUS`, `EXIT_CODE` | `JobRepository` |
| Task–Batch link | Task ↔ Job mapping | `TASK_TASK_BATCH`, when active |
| Business output | Row counts, checksums, unique business keys | Business DB/files/APIs |
| Events | Message count, destination, schema, correlation ID | Kafka/Rabbit + consumer |
| Runtime | Pod status, exit code, OOM, launch-to-finish duration | Deployer/Kubernetes |
| Performance | JVM startup, batch throughput, DB query time, broker lag | Logs/metrics |

**A valid baseline record is more than a screenshot.** Save the launch command, secret-redacted config, timestamps, arguments, and query tools. Without these, it is hard to separate upgrade regressions from input data drift.

### Do Not Compare by Absolute IDs

The new run will normally receive different `TASK_EXECUTION_ID` and `JOB_EXECUTION_ID` values. Instead of comparing ID equality, compare **relationships and invariants**:

- One intentional launch creates one `TaskExecution` once infrastructure is ready.
- `TaskExecution` links to the right `JobExecution`.
- Jobs/Steps reach expected statuses.
- Output has the same business key, counts, and checksum per contract.
- Start/end events identify the same execution without needing baseline IDs.
- Runtime exits with the policy-defined exit code.

## 5. Testing Against New Schemas and Historical Data

An upgrade may pass against an **empty DB** yet fail when reading an existing `JobRepository`. Database testing should therefore cover **at least three cases**:

1. **Fresh install:** Task and Batch schemas created with exact new-version DDL; run the job for the first time.
2. **Upgrade from old version:** clone/snapshot old schemas and metadata into an isolated environment, apply controlled migrations, then run the new app.
3. **Historical compatibility:** query historical `TaskExecution`/`JobExecution` records and read Jobs/`ExecutionContext`s that the business needs to retain.

### 5.1. Do Not Mutate Metadata Tables Like Arbitrary Business Tables

Spring Cloud Task uses tables like `TASK_EXECUTION`, `TASK_EXECUTION_PARAMS`, and `TASK_TASK_BATCH`. Spring Batch uses `BATCH_JOB_INSTANCE`, `BATCH_JOB_EXECUTION`, `BATCH_STEP_EXECUTION`, and parameter/context tables. Each framework owns its schema and mapping rules.

A sound migration requires:

- Data backup/snapshot before execution.
- Official DDL migrations or reviewed scripts matching **the exact source and target versions**.
- Verifying privileges, sequences, indexes, foreign keys, table prefixes, and database vendor quirks.
- A plan for serialized `ExecutionContext` entries, legacy `JobParameters`, and in-flight work.
- Never letting multiple processes race to run DDL in production.

Example production config managing schemas externally from the app:

~~~yaml
spring:
  batch:
    jdbc:
      initialize-schema: never
  cloud:
    task:
      initialize-enabled: false
~~~

`initialize-enabled: false` only stops automatic Task table creation; it **does not disable `TaskRepository`**. In a fresh staging environment, provision schemas first via migrations and run with this same setting to mirror production.

### 5.2. Special Considerations for Spring Batch 5 → 6

The official Spring Batch 6 migration guide notes changes in how `JobParameters` are represented/stored, the domain model, and several APIs. One major consequence: **failed `JobInstance`s created with Batch 5 cannot be restarted directly with Batch 6 due to different parameter formats**, per the migration guide. Therefore, before cutover you must **restart to completion or abandon** remaining Batch 5 failed `JobInstance`s via an approved procedure.

This does not mean all v5 history must be deleted. Separate clearly:

- **Reading/auditing old metadata:** test with compatible APIs/queries in the migrated environment.
- **Restarting a specific failed `JobInstance`:** may be constrained by version and serialization format.
- **Creating a new `JobInstance` for the same business work:** never use this to bypass restart issues without explicit idempotency and business sign-off.

When upgrading Boot/Batch across **two generations**, schedule a worker quiesce window, settle in-flight Jobs, and verify rollback feasibility **before altering schemas**. Never promise rollback by swapping Docker images alone once incompatible database migrations have been applied.

## 6. Verifying Spring Cloud Task ↔ Spring Batch Integration

Spring Cloud Task links `TaskExecution` with `JobExecution` via `TaskBatchExecutionListener`. Docs describe the listener as auto-configured when a `Job` and `spring-cloud-task-batch` are on the classpath. After an upgrade, verify **classpath, auto-configuration, and actual DB outcomes**, not just bean names.

### 6.1. Behaviors That Must Be Preserved

- The `Job` launches **once as intended**, not twice due to both the Batch auto-runner and a custom runner firing.
- Request `JobParameters` carry the right values, types, and identifying/non-identifying flags.
- `JobExecution` belongs to the right `JobInstance`; retries and restarts follow defined policy.
- `StepExecution` has valid status/counters/checkpoints.
- Task–Batch mapping is persisted when the feature is enabled and the repository is available.
- `BatchStatus.FAILED` propagates accurately to `TaskExecution.exitCode` and the process exit code when policy requires it.
- Committed business results are never duplicated merely because a new execution ID was allocated.

### 6.2. Sample Configuration for Testing Failure Paths

~~~yaml
spring:
  application:
    name: upgrade-smoke-task
  main:
    web-application-type: none
  batch:
    job:
      enabled: true
    jdbc:
      initialize-schema: never
  cloud:
    task:
      name: upgrade-smoke-task
      initialize-enabled: false
      batch:
        fail-on-job-failure: true
~~~

This snippet omits datasource/credentials; provide them via test Secrets or environment variables. `fail-on-job-failure` is the policy requiring Batch failures to surface in the Task exit code; **it does not guarantee every JVM/Deployer failure is recorded in `TaskRepository`**.

In some release lines, changing the order of the Batch integration `ApplicationRunner` can alter behavior. Spring Cloud Task docs provide `spring.cloud.task.batch.applicationRunnerOrder` in supported lines. Check version-specific property metadata, especially if the app has **multiple runners** or data-prep logic running prior to the Job.

### 6.3. SQL Query Reconciling Task and Batch

Per the reference Spring Cloud Task JDBC schema, `TASK_TASK_BATCH` stores the mapping:

~~~sql
SELECT t.TASK_EXECUTION_ID,
       t.TASK_NAME,
       t.START_TIME AS TASK_START_TIME,
       t.END_TIME   AS TASK_END_TIME,
       t.EXIT_CODE  AS TASK_EXIT_CODE,
       j.JOB_EXECUTION_ID,
       j.STATUS     AS BATCH_STATUS,
       j.EXIT_CODE  AS BATCH_EXIT_CODE
FROM TASK_EXECUTION t
JOIN TASK_TASK_BATCH m
  ON m.TASK_EXECUTION_ID = t.TASK_EXECUTION_ID
JOIN BATCH_JOB_EXECUTION j
  ON j.JOB_EXECUTION_ID = m.JOB_EXECUTION_ID
ORDER BY t.TASK_EXECUTION_ID DESC;
~~~

If no rows appear, do not immediately assume the task did not run. Check:

1. Is there a standalone row in `TASK_EXECUTION`?
2. Is there a standalone row in `BATCH_JOB_EXECUTION`?
3. Are `spring-cloud-task-batch` and `TaskBatchExecutionListener` active?
4. Are you querying the exact schema/prefix/datasource the app actually writes to?
5. Did the Job run before the listener attached, or fail during initialization?

A valid mapping row for the new run is far stronger evidence than merely reading `Job completed` in logs.

### 6.4. Distinguishing Batch Outcomes from Task Outcomes

| Observation | Proper Interpretation |
| --- | --- |
| `BatchStatus.COMPLETED` | Job/Step marked complete by Batch; still verify business output |
| `BatchStatus.FAILED` + Task exit code `0` | Mapping policy lost, auto-config changed, or app swallowed the error |
| `BatchStatus.FAILED` + non-zero Task exit code | Exit-code policy worked for the test case; also verify process exit code |
| Non-zero Task exit code, yet output exists | Business work may have committed before metadata/post-processing failed |
| No `TaskExecution`, yet launcher ran | Possible very early failure creating `ApplicationContext` |

Simply asserting "exit code != 0" is also insufficient: the process might have failed due to **a missing dependency** instead of the intended Batch error. Inspect the root exception and `JobExecution` in the database.

## 7. Testing Restarts, Checkpoints, and Business Data

Upgrades must never break critical restart behaviors.

### 7.1. Scenarios That Must Be Tested

| Scenario | What to Verify |
| --- | --- |
| Fresh Job run | Right `JobInstance`, `StepExecution`, written row count, and exit code |
| Job fails mid-chunk | Only committed chunks persist per transaction; checkpoint accurate |
| Restart with same identifying parameters | Behavior matches Batch version and `JobInstance` state |
| Whole-Task retry creating a new `JobInstance` | No duplicate output thanks to business keys and unique constraints |
| `JobRepository` error during update | Do not guess committed results from logs; reconcile output |
| v5 → v6 upgrade with old failed `JobInstance` | Settled/abandoned before cutover; never blindly auto-restarted |
| Two workers processing one partition | Locking/fencing/idempotency at write target, not metadata alone |

### 7.2. Enforcing Business Invariants in the Database

Example output table:

~~~sql
CREATE TABLE daily_report (
    tenant_id       VARCHAR(64) NOT NULL,
    business_date   DATE NOT NULL,
    report_version  VARCHAR(24) NOT NULL,
    payload_hash    CHAR(64) NOT NULL,
    report_body     TEXT NOT NULL,
    PRIMARY KEY (tenant_id, business_date, report_version)
);
~~~

If the same request reruns, the unique key blocks duplicate rows. However, if a row already exists with a different `payload_hash`, the app must **raise a conflict or handle business versioning**, never blindly return `ALREADY_APPLIED`.

A subtle post-upgrade regression: new code injects the current timestamp as an identifying `JobParameter`, creating a new `JobInstance` on every attempt while the real business key did not change. `JobRepository` cannot substitute for unique constraints on business tables.

## 8. Verifying Spring Cloud Stream After Upgrades

When Task–Stream integration is active, Spring Cloud Task can emit events carrying `TaskExecution` at start and end via the `task-events` logical output binding. When Batch events are enabled, bindings like `job-execution-events`, `step-execution-events`, or `chunk-events` can be configured separately.

After an upgrade, test **both producer and consumer**, because "a message landed on the topic" does not prove consumers parse the schema properly.

### 8.1. Illustrative Producer and Consumer Configurations

Task side:

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
          destination: ops.task.lifecycle.v1
          contentType: application/json
        job-execution-events:
          destination: ops.batch.job.v1
          contentType: application/json
      kafka:
        binder:
          brokers: ${KAFKA_BROKERS}
~~~

Consumer side using a `Consumer` function named `observeTask`:

~~~yaml
spring:
  cloud:
    function:
      definition: observeTask
    stream:
      bindings:
        observeTask-in-0:
          destination: ops.task.lifecycle.v1
          group: task-observer
          contentType: application/json
      kafka:
        binder:
          brokers: ${KAFKA_BROKERS}
~~~

**Notes:**

- `task-events` is the **logical output binding**, whereas `ops.task.lifecycle.v1` is the **target Kafka topic**; never rename the binding in producer config and expect the listener to find it.
- Equivalent property forms are `spring.cloud.stream.bindings.task-events.destination=ops.task.lifecycle.v1` on the producer and `spring.cloud.stream.bindings.observeTask-in-0.destination=ops.task.lifecycle.v1` on the consumer.
- Under the functional model, `observeTask-in-0` is the default input binding for function `observeTask`.
- Brokers, topics, ACLs, content types, converters, serializers, and consumer groups must be verified at **runtime**, not just in YAML.
- These are suggested configs for building tests; binder and event module versions must be drawn from a compatible release train, not arbitrary artifact versions.

### 8.2. "Golden Message Contract" Testing

Capture a real event from the old version—**with sensitive data scrubbed**—and test the new consumer against that payload. Also capture an event from the new producer and test the old consumer if a parallel rollout window exists.

Matrix:

| Producer | Consumer | Desired Outcome |
| --- | --- | --- |
| Old | Old | Valid baseline |
| New | New | New operational path works |
| Old | New | Must be supported if rolling upgrades overlap |
| New | Old | Must be supported if old consumers remain while canary emits messages |

For JSON/Avro/Protobuf payloads, test each system's exact contract: field names, `executionId` type, timestamps, nullability, enums, `contentType`, headers, and schema versions. A consumer reading into `Map<String,Object>` is not exempt from runtime type checks—e.g., numbers may deserialize as `Integer` or `Long`.

**Do not compare byte-for-byte** when JSON field order or date formatting differs while staying contract-compatible. Use schemas/DTOs or field-and-semantics assertions.

### 8.3. Start/End Events and Completeness

Tests must answer:

1. Are matching start and end events emitted for a **normally completed** `TaskExecution`?
2. Do they share the same execution ID or appropriate correlation ID?
3. Does the end event carry exit code/end time matching the repository row per the actual schema/payload?
4. When a Batch Job fails, do `job-execution-events` and `task-events` reflect the appropriate status?
5. If the JVM is killed prior to shutdown, does monitoring record `UNKNOWN` rather than falsely staying `RUNNING` forever?
6. If the broker redelivers, is the consumer idempotent by **(executionId, lifecycle phase)** or an equivalent mechanism?

A consumer that deduplicates solely by `executionId` can ingest the start event and **drop the end event**. Derive lifecycle phase from actual messages and protocols rather than assuming every version's payload has a `phase` field.

## 9. Test Binder and Real Brokers Serve Different Goals

The Spring Cloud Stream Test Binder supports testing contracts and functions inside a Spring context **without a real Kafka/RabbitMQ broker**. It is a fast test layer, yet it does not verify broker realities:

- Broker endpoints, TLS/SASL, publish/subscribe ACLs.
- Existing topics and proper destination mappings.
- Real serializers/converters, offsets, consumer groups, partition keys, retries/DLQs.
- Very short tasks exiting the JVM and flushing messages before shutdown.
- Network cuts, lost producer ACKs, or consumer redelivery.

Therefore split them:

- **Contract tests:** Test Binder in an appropriate module/test profile to validate payloads and mappings.
- **Broker integration tests:** real Kafka/RabbitMQ (e.g., via Testcontainers), running task and consumer in separate processes and awaiting messages within a finite deadline.

Spring Cloud Stream docs also warn against mixing Test Binder and a real binder in the same uncontrolled test module, because Test Binder may take precedence over the real broker. Separating profiles or modules prevents real broker tests from "passing falsely" over an in-memory channel.

### Mandatory Evidence on a Real Broker

~~~text
runId=upgrade-20261124-001
taskExecutionId=<ID allocated by repository>
brokerCluster=<test cluster>
taskBinding=task-events
taskTopic=ops.task.lifecycle.v1
batchBinding=job-execution-events
batchTopic=ops.batch.job.v1
consumerGroup=task-observer
receivedStart=true|false
receivedEnd=true|false
receivedBatchEvent=true|false
payloadSchema=verified version
consumerAckStatus=per binder
~~~

Missing data in this checklist defaults to failure; investigate clearly whether **it never launched, never published, never got a broker ACK, or the consumer never read it**.

## 10. Verifying the Deployer: Launch Receipt Is Not Completion

With Spring Cloud Data Flow or apps using Spring Cloud Deployer, the Deployer layer handles deploying artifacts, injecting configs, and creating processes on platforms like Kubernetes, Cloud Foundry, or local.

After upgrading, verify across this chain:

~~~mermaid
flowchart TD
    A["Register new artifact/version"] --> B["Launch request"]
    B --> C{"Deployer accepts?"}
    C -->|"Yes"| D["Receipt / deployment ID"]
    C -->|"No"| X["Launch failure"]
    D --> E["Image pull / Pod or process creation"]
    E --> F["JVM bootstrap + TaskExecution"]
    F --> G["Batch Job / business logic"]
    G --> H["Runtime exits + exit code"]
    H --> I["Reconcile TaskRepository + Batch + output + events"]
    E -. "Pull/secret/quota failure" .-> J["May lack TaskExecution"]
    F -. "ApplicationContext failure" .-> J
~~~

**A successful launch response does not prove the application finished running.** If Kubernetes cannot pull the image, a Secret is missing, a ServiceAccount is denied, or the runtime JDK is incompatible, the Deployer may still have created or requested a Job while the Task never creates a `TaskExecution`.

### 10.1. Fields to Preserve When Sending `TaskLaunchRequest`

In a Spring Cloud Stream launch flow, `TaskLaunchRequest` can carry:

| Field | What Needs Testing |
| --- | --- |
| `uri` | Artifact resolved at the right version/coordinates |
| `applicationName` | Task name used by launcher, logs/metadata |
| `commandLineArguments` | Business keys, `JobParameters`, and Boot options passed intact |
| `environmentProperties` | Required env configs passed accurately; secrets not leaked |
| `deploymentProperties` | Deployer settings like resources/namespace/instance config if supported |

Illustrative example using a `TaskLaunchRequest` constructor from a release line supporting this signature:

~~~java
import java.util.List;
import java.util.Map;
import org.springframework.cloud.task.launcher.TaskLaunchRequest;

TaskLaunchRequest request = new TaskLaunchRequest(
    "maven://com.example:daily-report-task:jar:2.0.0",
    List.of("--businessDate=2026-11-24",
            "--tenant=shop-01",
            "--runId=upgrade-20261124-001"),
    Map.of("SPRING_PROFILES_ACTIVE", "staging"),
    Map.of(),
    "daily-report-task"
);
~~~

This snippet only **constructs the request**; it does not send the message or deploy the task. It requires an appropriate sink/launcher and binder. On Kubernetes, the Deployer may require a **container image** instead of a Maven JAR coordinate depending on setup; `uri` must match an artifact type actually supported by your launcher.

### 10.2. Testing Launches with Unchanged vs. New Artifacts

- **Same artifact, new deployer:** isolates deployment infrastructure regressions.
- **Same deployer, new artifact:** isolates Boot/Task/Batch regressions.
- **Change both:** perform only after each axis is verified, using an end-to-end canary.

In SCDF, check **task application version/default version**, deployer properties, and behavior while an old task is still running. SCDF documentation describes launch scenarios when artifacts/properties are unchanged or when upgrading a deployment; some platforms may **block upgrades while a task is running** to avoid disrupting the active deployment. Never assume that exact rule applies identically across all SCDF/platform/version setups.

## 11. When Using Remote Partitioning: Test Both Manager and Workers

Spring Cloud Task provides **Spring Batch remote partitioning** integration via classes such as `DeployerPartitionHandler` and `DeployerStepExecutionHandler` in supported releases. The manager creates partitions, the Deployer launches workers, and each worker must locate its `StepExecution` in `JobRepository`.

Upgrades can break this path even when a non-partitioned Job runs fine.

### 11.1. Contracts to Verify

- Manager and workers use **compatible library/model combinations** and metadata formats supported by the version.
- Workers launch with the right artifact URI/image, environment variables, Job/StepExecution IDs, and datasource configs.
- Workers find `StepExecution` in **the exact `JobRepository`**, not an empty DB or wrong schema.
- `gridSize`, concurrent workers, poll intervals, timeouts, and thread pools fit within Deployer capacity.
- A dead worker never causes the manager to falsely report Job success; worker retries never duplicate committed data.
- Partitions have non-overlapping keys/ranges; restarts inherit valid checkpoints.
- Short-lived worker tasks close their context/process cleanly after finishing rather than leaving pods dangling indefinitely.

### 11.2. Partition Test Matrix

| Scenario | What Must Be Proven |
| --- | --- |
| Single partition | Worker launches, reads/writes properly, manager receives outcome |
| Multiple partitions | Exact partition count, zero lost or duplicated records |
| One worker crashes | Manager detects failure or times out; Job never reports false success |
| Launcher refuses to spawn worker | Does not hang forever; surfaces clear error details |
| Worker runs wrong image/version | Compatibility/canary checks and alerts catch it |
| Worker hits wrong DB/schema | Fails clearly; never writes records into another repository |
| Partition retried after ambiguous commit | Idempotent outcome with business-key reconciliation |
| Changing max workers | Stays within quotas/connections; acceptable throughput |

Avoid setting **infinite** timeouts and merely checking that the manager is "waiting": when a worker never appears, tests must fail against **a clear deadline**.

## 12. Example Test Harness Running the JAR in a Separate Process

A `@SpringBootTest` can validate Job logic inside a context, yet cannot prove the Deployer, JVM exit, process exit code, or final event publishing. You need a test executing **the real artifact** in an isolated JVM/Pod.

Example JUnit 5 harness using `ProcessBuilder` on a machine/build agent with Java and a built JAR:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.nio.file.Path;
import java.time.Duration;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

class UpgradeProcessSmokeIT {

    @Test
    void taskKetThucTrongGioiHan() throws Exception {
        Path artifact = Path.of(
            "target", "daily-report-task-2.0.0.jar");

        ProcessBuilder builder = new ProcessBuilder(
            "java", "-jar", artifact.toString(),
            "--businessDate=2026-11-24",
            "--tenant=shop-01",
            "--runId=upgrade-20261124-001");

        // Real code must obtain endpoints/secrets from Testcontainers
        // or an isolated integration environment.
        builder.environment().put(
            "SPRING_PROFILES_ACTIVE", "integration");

        // Redirect output to a test file to avoid filling the pipe buffer.
        builder.redirectErrorStream(true);
        builder.redirectOutput(
            Path.of("target", "upgrade-smoke.log").toFile());

        Process child = builder.start();
        try {
            boolean completed =
                child.waitFor(90, TimeUnit.SECONDS);

            if (!completed) {
                child.destroy();
                if (!child.waitFor(5, TimeUnit.SECONDS)) {
                    child.destroyForcibly();
                }
                fail("Task exceeded test timeout");
            }

            assertEquals(0, child.exitValue(),
                "Check logs and repository when exit != 0");
        } finally {
            if (child.isAlive()) {
                child.destroyForcibly();
            }
        }
    }
}
~~~

This is an **illustrative skeleton**, not a substitute for test environment configuration. In a real project you must:

1. Build the JAR before the integration-test phase, or fetch the artifact path from CI.
2. Create log output directories and isolate filenames per test so parallel tests do not overwrite each other.
3. Supply `TASK_DB_URL`, username/password, and broker endpoints/credentials via env vars or test Secrets, **never printing secret values**.
4. Await the process with a timeout; collect exit code and logs before closing the test.
5. Query PostgreSQL and the broker **after** the process exits to verify `TaskExecution`, Batch metadata, events, and output.
6. Never run process-level tests against H2 `mem:` if you need to inspect data after the child JVM exits.
7. Also test *negative paths* like `--failDemo=true` or intentional data errors; non-zero exit must happen for **the exact expected reason**, not missing classes or DB errors.

In Kubernetes environments, replace `ProcessBuilder` with the orchestration API/CLI to **create a test Job** and wait on Job/Pod status. Never treat Job-creation API success as proof of task completion.

## 13. Mandatory Pre/Post-Upgrade Test Matrix

Core test suite for a system with Batch + Stream + Deployer:

| ID | Scenario | Acceptance Evidence |
| --- | --- | --- |
| U01 | App context boots with new artifact | Zero dependency/autoconfiguration errors; right profile/JDK |
| U02 | Launch via Deployer | Receipt returned; pod/process spawned with exact image digest |
| U03 | Task succeeds | `END_TIME`, Task exit code, and process exit code valid; output valid |
| U04 | Batch Job succeeds | `BatchStatus.COMPLETED`, accurate Steps, Task–Batch mapping present |
| U05 | Batch Job fails | `BatchStatus.FAILED`; Task/process non-zero per policy |
| U06 | Task start/end events | Right topic; payload contract; matching execution identity |
| U07 | Batch Job events | Dedicated topic; job status matches `JobRepository` |
| U08 | New consumer reads old payload | Rolling-upgrade compatible or clear cutover plan |
| U09 | Old consumer reads new payload | Compatible during overlap or versioned topics |
| U10 | Restart/`JobParameters` | Exact `JobInstance`, checkpoints, strategy for legacy history |
| U11 | Retry with same business key | Zero duplicate output; conflicts detected |
| U12 | PostgreSQL migration | Historical metadata readable within scope; sequences/indexes valid |
| U13 | Broker down / wrong ACL | Fails/alerts with reason; never claims event received when not |
| U14 | DB down at bootstrap | Runtime logs show error; do not assert `TaskExecution` must exist |
| U15 | JVM killed mid-job | No end event expected; runtime/reconciliation determines state |
| U16 | Remote partitioning if used | Worker launch, `StepExecution` mapping, timeouts, and retries valid |
| U17 | Overlap / 2 executions | Idempotency and unique keys block duplicates |
| U18 | Performance comparison | Meets measured thresholds on an equivalent baseline |
| U19 | Canary using new artifact | No rise in error/lag/timeout rates vs. baseline |
| U20 | Rollback rehearsal | Recovers cleanly under prepared DB/schema/event/worker policy |

Not every application uses remote partitioning or Batch events. Mark **not applicable** items explicitly with a reason rather than leaving them blank as if untested.

## 14. Automating Assertions: Assert Meaningful Outcomes Only

### 14.1. Example SQL Checking Batch–Task Metadata

Count tasks by exit code within a test window using timestamps supplied by the framework/test:

~~~sql
SELECT TASK_NAME,
       EXIT_CODE,
       COUNT(*) AS RUNS
FROM TASK_EXECUTION
WHERE START_TIME >= ?
  AND START_TIME < ?
GROUP BY TASK_NAME, EXIT_CODE
ORDER BY TASK_NAME, EXIT_CODE;
~~~

With JDBC `PreparedStatement`/`JdbcTemplate`, bind both `?` placeholders to the start/end timestamps of each test. Never assert row counts across the whole database if old history or parallel tests exist.

Query checking Task–Batch links within the test window:

~~~sql
SELECT COUNT(*) AS LINKED_JOBS
FROM TASK_TASK_BATCH m
JOIN TASK_EXECUTION t
  ON t.TASK_EXECUTION_ID = m.TASK_EXECUTION_ID
JOIN BATCH_JOB_EXECUTION j
  ON j.JOB_EXECUTION_ID = m.JOB_EXECUTION_ID
WHERE t.TASK_NAME = ?
  AND t.START_TIME >= ?;
~~~

Compare `LINKED_JOBS` against the number of Jobs expected by the golden run. If the `Job` never ran due to a bootstrap error, the missing mapping is a **symptom**, not the root cause.

### 14.2. Example JSON Contract Assertion

For a `task-events` payload:

~~~json
{
  "executionId": 502,
  "taskName": "upgrade-smoke-task",
  "startTime": "2026-11-24T01:00:00Z",
  "endTime": "2026-11-24T01:00:08Z",
  "exitCode": 0
}
~~~

This is an **illustrative payload**, not a mandatory serializer contract across all Spring Cloud Task versions. Base tests on the actual JSON/schema of old and new versions. Assertions should check:

- Valid `executionId` present; identity matches a row in `TaskRepository`.
- `taskName`, `startTime`, `endTime`, and `exitCode` parse with expected types/semantics when present.
- Start and end events are both recognized using actual version fields, rather than dropping an event due to duplicate `executionId`.
- Newly added fields are handled by consumers under backward-compatibility rules.
- Timestamp timezones/precision compare semantically (do not require identical string formatting when both represent the same instant).

## 15. Upgrades Can Alter Performance

An upgrade that increases latency is not necessarily a logic bug, yet it can cause **SLA breaches**, especially for short-lived tasks with large bootstrap overhead.

### 15.1. Measure Stage by Stage

| Metric | Where to Measure | Regressions It Can Catch |
| --- | --- | --- |
| Launch-to-pod-ready | Deployer/cluster | Slow image pull, admission/quotas, resources |
| JVM/context startup | Boot logs/telemetry | Extra auto-configuration, classpath bloat, JDK |
| Task runtime | `TaskExecution` + process | Total duration increase |
| Batch Job/Step duration | `JobRepository`, Step metrics | Chunk size, JDBC, serialization |
| Throughput | Business rows / time | Slower reader/processor/writer |
| DB pool/locks/waits | PostgreSQL metrics | Concurrent jobs/migrations/indexes |
| Event publish latency | Broker/producer metrics | Batching/acks/serializer |
| Consumer lag | Kafka consumer group | Slow converter or processing |
| Remote worker launch latency | Deployer/manager logs | Partition scaling and provisioning |

When comparing v1/v2, hold constant **the data snapshot**, partition count, CPU/memory limits, broker/database, and sensible warm-up timing. Never compare a warm-cache run against a cold-cache run and blame a library regression.

### 15.2. Define Acceptance Thresholds Before Running

Example thresholds agreed upon by operations:

~~~text
task_success_rate >= 99.9% on canary (if sample size is large enough)
p95_launch_to_finish <= baseline_p95 * 1.20
p95_batch_step_duration <= baseline_p95 * 1.15
task_event_missing_end = 0 when runtime shuts down normally and broker is healthy
duplicate_business_output = 0
unexplained_batch_task_exit_mismatch = 0
database_migration_errors = 0
remote_partition_stuck_above_deadline = 0
~~~

Percentage figures are **illustrative policy examples**, not framework SLAs or defaults. When canary sample sizes are small, 99.9% has no statistical meaning; use controlled tests and inspect **every single run** rather than relying on a pretty percentage chart.

## 16. Phased Upgrade Workflow

A practical roadmap:

~~~mermaid
flowchart TD
    A["Lock baseline and dependency manifest"] --> B["Review compatibility/migration guides"]
    B --> C["Backup DB + rehearse schema migration"]
    C --> D["Run contract/unit/Batch tests"]
    D --> E["Test real broker + Deployer sandbox"]
    E --> F{"Golden run and failure tests PASS?"}
    F -->|"No"| G["Fix regressions; hold cutover"]
    F -->|"Yes"| H["Small controlled canary on staging/prod"]
    H --> I{"Metrics, Batch, events, output meet thresholds?"}
    I -->|"No"| J["Halt rollout + reconcile"]
    I -->|"Yes"| K["Expand in waves + monitor"]
    J --> L["Rollback/restore per plan"]
~~~

### Phase A — Preparation

1. Freeze source version, config, artifact URI/image digest, and dependency list.
2. Lock down test dataset/golden run, including one `FAILED` Batch case and one same-business-key retry case.
3. Capture metadata/DB backups; list incomplete `JobInstance`s.
4. Read migration guides for **each hop** from old to new version.
5. Confirm whether old/new images can coexist in the same cluster or require isolated environments.

### Phase B — Testing in Isolated Staging

1. Clone database (with sensitive fields masked/scrubbed) and apply migrations.
2. Launch the new JAR through the Deployer sandbox, not merely `mvn spring-boot:run`.
3. Run Task/Batch/Stream/Deployer checks per matrix U01–U20.
4. Inject broker unavailability, DB disconnect, worker timeout, and killed JVM failures.
5. Archive SQL outputs, sample messages, logs, artifact digest, and sign-off notes.

### Phase C — Cutover

1. Pause new launches or route traffic per plan, avoiding upgrades mid-Job while metadata is actively written.
2. Settle in-flight Jobs, especially across Batch major and serialization changes.
3. Apply DDL via independent monitored migrations.
4. Deploy producer and consumer according to **the compatibility matrix**, avoiding simultaneous blind swaps that obscure root causes.
5. Run a few canary requests with isolated business keys; expand only once gates pass.

### Phase D — Post-Cutover Monitoring

- Verify Batch failures convert to non-zero Task/process exits per policy.
- Monitor start/end event counts and consumer lag by topic.
- Watch Deployer retries, pod OOMs, image pull failures, and deadline-exceeded events.
- Reconcile `TaskRepository`, `JobRepository`, and output tables for every canary.
- Confirm scheduled occurrences are not missed and retries never duplicate results.

## 17. Rollback Must Account for Database, Broker, and Workers

Rollback is not simply **reverting a Docker tag to the old version**.

| Component | Rollback Risk | What to Prepare |
| --- | --- | --- |
| Batch database | Migrated metadata/`JobParameters` unreadable/unrestartable by old app | Verified snapshot/restore or backward-compatible plan |
| Task database | Changed DDL/schema/prefix, new sequences/indexes or rows | Tested forward/reverse migrations, backups, data-loss assessment |
| Stream producer/consumer | New payloads already emitted to topic; old consumer cannot parse | Versioned destinations or dual v1/v2 consumer support |
| Kafka offsets | New consumer committed offsets; reverting to old consumer may skip messages | Replay/dedup/DLQ plan with adequate retention |
| Deployer | New artifact already deployed/cached; old workers still running | Pin digests/versions; decide handling for in-flight Jobs |
| Business output | New build already committed data or called external APIs | Idempotency/reconciliation or compensation; never delete blindly |
| Scheduler | Cron/triggers keep firing launches during rollback | Controlled pause/reroute; track missed occurrence backlog |

For breaking schema changes, many teams use **expand → migrate → contract** to maintain an overlap window where both versions work, if the framework/schema allows it. Do not mechanically apply that to `JobRepository` when the migration guide **does not support concurrent dual-version reads/writes**. In that case, accept a maintenance-window cutover, backups/restores, and a dedicated data recovery plan.

If new business side effects already occurred, restoring the database from a snapshot can **erase outcomes committed after the snapshot**. The rollback plan must specify how to reconcile, replay, or recover them rather than treating restore as risk-free.

## 18. Common Post-Upgrade Failures

| Symptom | Possible Cause | Action |
| --- | --- | --- |
| Job runs yet `TASK_TASK_BATCH` is empty | Batch–Task module/listener missing or bean conditions changed | Check dependencies, auto-config, mapping, and datasource |
| Batch `FAILED` yet Task `EXIT_CODE=0` | `fail-on-job-failure` policy not applied / custom runner | Process-level test, condition report, `ExitCodeGenerator` |
| Cannot restart old Job after major upgrade | `JobParameters` serialization/schema changed | Read migration guide; settle old `JobInstance`s before cutover |
| Task runs yet `task-events` topic is empty | Missing module/binder/listener, wrong destination, ACL error | Check classpath, config, broker, and producer logs |
| Consumer receives event yet fails to parse | Changed JSON fields/types/headers/`contentType` | Contract tests: new producer ↔ old/new consumers |
| Deployer accepts launch yet no `TaskExecution` | Image/pod failed to start, bootstrap error, wrong DB | Check receipt, Job/Pod status, startup logs |
| Partition worker hangs | Worker failed to launch or locate `StepExecution` | Deployer logs, `JobRepository`, timeout/worker configs |
| Two runs write duplicate output | Retry spawned new `JobInstance`; missing unique key | Add business idempotency; inspect conflicts |
| Task slower even though Batch duration unchanged | Pod provisioning / JVM startup / telemetry | Compare launch-to-finish and per-stage timings |
| Missing end events after rollout | JVM exited early, broker error, or publish not flushed | Cross-check runtime, repository, producer ACKs, and consumer |
| Canary passes, production hits errors | Larger history/data or different ACLs/scale than staging | Test on migrated DB clone with equivalent limits and load |

Never "fix" missing `TaskExecution` records by disabling Task auto-configuration if operations still requires metadata. Find the root cause in versions, schemas, connectivity, and listeners.

## 19. Upgrade Acceptance Checklist

- [ ] Exact BOM/Boot/Task/Batch/Stream/Binder/Deployer/Java/DB versions and artifact digests recorded.
- [ ] Compatibility matrix confirmed against **release-exact** official documentation.
- [ ] Pre-upgrade golden run and reproducible test dataset/snapshot captured.
- [ ] DB backed up and migration rehearsed with historical metadata, sequences, and indexes.
- [ ] Incomplete legacy Batch `JobInstance`s settled per migration guide.
- [ ] Jobs/Steps run accurately, `JobParameters` match, and checkpoints/restarts verified.
- [ ] Task–Batch mapping `TASK_TASK_BATCH` present when the feature is required.
- [ ] `BatchStatus.FAILED` reflected in Task and process exit codes per policy.
- [ ] Start/end Task events and Batch events reach target destinations and parse cleanly.
- [ ] Old/new producer ↔ old/new consumer tested if rolling upgrades are needed.
- [ ] Real broker tests executed, not just Test Binder.
- [ ] Deployer tested with real JAR/image: receipt, pod/process, exit code, and logs.
- [ ] If remote partitioning is used, worker launches, metadata, and timeouts verified.
- [ ] Retries/overlaps produce zero duplicate business data; unique keys and reconciliation exist.
- [ ] DB/broker outage, bootstrap failure, `SIGKILL`, and ambiguous commit outcomes tested.
- [ ] Canary performance thresholds agreed upfront with supporting evidence.
- [ ] Procedures ready for halting rollout, rolling back DB/workers/events, and recovering post-snapshot outputs.
- [ ] Secrets, PII payloads, logs, access tokens, and topic/database permissions secured.
- [ ] `PASS/FAIL/BLOCKED/NOT_APPLICABLE` verdict recorded for every test case with evidence.

## 20. Exercises and Self-Check Questions

**Question 1.** Why is a passing `JobExecution.STATUS=COMPLETED` test insufficient to prove Spring Cloud Task and Deployer integration upgraded successfully?

**Question 2.** If both `TASK_EXECUTION` and `BATCH_JOB_EXECUTION` have new rows yet `TASK_TASK_BATCH` is empty, which conditions do you check?

**Question 3.** When a Batch Job is `FAILED` yet the Kubernetes Job reports process exit code `0`, which property should you inspect and why are process-level tests necessary?

**Question 4.** Why can contract tests using Test Binder not verify Kafka topics, ACLs, or consumer groups after a binder upgrade?

**Question 5.** What is the difference between `TaskLaunchRequest.uri`, `deploymentProperties`, and `commandLineArguments`? What else must the Deployer verify?

**Question 6.** Why shouldn't you blindly restart a failed `JobInstance` created on Batch 5 using Batch 6 before handling migration steps?

**Question 7.** If the database schema was already upgraded and 100 new tasks ran, is rolling back solely by reverting the container image safe? Why or why not?

**Exercise A — Golden run.** Create a baseline/target manifest and run one success case and one Batch failure case. Save `TaskExecution`, `JobExecution`, mapping rows, output checksum, and process exit code for each version.

**Exercise B — Stream contract.** Capture real `task-events` JSON from old and new builds; build old/new consumer matrix tests. When payloads change incompatibly, propose schema versioning or a new destination.

**Exercise C — Deployer sandbox.** Launch the same JAR on local and Kubernetes deployers, comparing receipts, env vars, resources, exit codes, and runtime metadata.

**Exercise D — Remote partition.** In a partitioned Job, kill one worker mid-processing. Check manager timeouts, `JobExecution`/`StepExecution`, and business row counts after retry.

**Exercise E — Rollback.** Rehearse migration on an isolated DB containing historical data, then plan how to revert to the old version without losing outputs committed after the backup timestamp.

**Exercise F — Performance regression.** Using the same data snapshot, measure p95 startup, Job duration, and end-to-end latency; define rollout-blocking thresholds and explain warm/cold cache and pod image pull effects.

## 21. Key Takeaways

- **A successful upgrade does not equal a successful build.** Verify behavior across Batch, Stream, Deployer, `TaskRepository`, and business outcomes.
- A **JDK–Boot–Cloud–Batch–Stream–Deployer** version matrix plus artifact manifests make tests reproducible.
- `TaskExecution`–`JobExecution` linking must be verified via `TaskBatchExecutionListener`/mapping rows, not just seeing rows in both tables.
- On major Batch upgrades, read migration guides on `JobParameters`, DDL, and restartability of **old `JobInstance`s**.
- `task-events` is a logical output binding; destination, serializer, broker, and consumer groups must all be verified with real events.
- **Deployer ACK does not mean task completion.** Observe processes/pods, exit codes, Task metadata, and outputs.
- Remote partitioning adds manager–worker–`JobRepository` boundaries, so test timeouts, retries, and worker versions.
- Canary rollouts, failure injection, idempotency, and rollbacks covering **both database and broker** are mandatory in systems requiring safe operations.

## References

- [Spring Cloud — Compatibility with Spring Boot](https://spring.io/projects/spring-cloud/): release train and Boot generation matrix; updated per release.
- [Spring Cloud Task — Batch](https://docs.spring.io/spring-cloud-task/reference/batch.html): `TaskBatchExecutionListener` and `spring.cloud.task.batch.fail-on-job-failure`.
- [Spring Cloud Task — Stream Integration](https://docs.spring.io/spring-cloud-task/reference/stream.html): Task start/end events and Batch event bindings.
- [Spring Cloud Task — Task Repository Schema](https://docs.spring.io/spring-cloud-task/docs/current/reference/html/appendix-task-repository-schema.html): `TASK_EXECUTION` and `TASK_TASK_BATCH` tables.
- [Spring Batch 6 — Migration Guide](https://github.com/spring-projects/spring-batch/wiki/Spring-Batch-6.0-Migration-Guide): `JobParameters` changes, domain model, and v5 historical restart limits.
- [Spring Batch — Metadata Schema](https://docs.spring.io/spring-batch/reference/6.0/schema-appendix.html): Job/Step tables, DDL, and migration scripts.
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html): destination, group, `contentType`, and binder.
- [Spring Cloud Stream — Test Binder](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html): contract tests and limitations vs. testing with a real broker.
- [Spring Cloud Task — DeployerPartitionHandler API](https://docs.spring.io/spring-cloud-task/docs/current/apidocs/org/springframework/cloud/task/batch/partition/DeployerPartitionHandler.html): worker `StepExecution` in remote partitioning.
- [Spring Cloud Task — TaskLaunchRequest API](https://docs.spring.io/spring-cloud-task/docs/current/apidocs/org/springframework/cloud/task/launcher/TaskLaunchRequest.html): artifact URI, args, environment, deployment properties.
- [Spring Cloud Data Flow — Reference Guide](https://docs.spring.io/spring-cloud-dataflow/docs/current/reference/htmlsingle/): task application versions, launch lifecycle, and platform upgrades.

**Scope:** code snippets and SQL are samples for learning and building test harnesses; they were not compiled/executed in a real project. Verify dependencies, migration scripts, binder/Deployer configurations, and version-exact API compatibility before applying. A thorough Content QA pass will evaluate alignment with the project structure after this authoring step.
