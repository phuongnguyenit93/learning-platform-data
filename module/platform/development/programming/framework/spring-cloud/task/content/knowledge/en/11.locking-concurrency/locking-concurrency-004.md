# Protection Scope by Task Name and Shared Database

In **Spring Cloud Task**, a finite-lived process performs its work and then exits; each run is tracked by a `TaskExecution` in **TaskRepository**. When two processes of the same task are launched nearly simultaneously, they may ingest the same file, generate duplicate reports, or update the same data rows. The **single-instance** mechanism helps prevent overlapping runs, but you must properly understand **task-name-based locking** and that **processes must coordinate through a shared lock database**.

This lesson in the **Locking and Concurrency** chapter analyzes the protection scope of `spring.cloud.task.single-instance-enabled`, how to configure the repository and JDBC locking mechanism, multi-host/multi-container deployment scenarios, verification steps, and the limitations that must be addressed additionally with business locks and safe rerun design.

## 1. The Problem: Two Processes Handling the Same Job

Suppose a sales system has an `invoice-report-task` that generates an end-of-day invoice report. The scheduler launches it at 02:00, while an operator can also trigger it manually to regenerate a report. Two requests arrive close together:

~~~text
02:00:00  CronJob launches Task A, --report-date=2026-11-23
02:00:03  API launches Task B, --report-date=2026-11-23
02:00:04  Both read invoices and start generating the report
02:01:15  Both processes attempt to write the final report object
~~~

Without coordination, the system may experience:

- Creating two report files for the same period and sending notifications twice.
- Two processes concurrently updating the same `GENERATING` / `READY` states.
- One process overwriting the file created by the other process.
- TaskExecution history recording **two successful runs**, even though business rules expect a single release.

There are three distinct control layers:

| Layer | Protection Scope | Example Tool |
| --- | --- | --- |
| **Orchestrator** | Runs belonging to the same schedule, workflow, or policy | Kubernetes CronJob `concurrencyPolicy: Forbid` |
| **Spring Cloud Task single-instance** | Executions with the **same task name** sharing a locking mechanism | `spring.cloud.task.single-instance-enabled=true` |
| **Business layer** | A logical entity, such as `(tenantId, reportDate)` | Unique constraint, transaction lock, idempotency key |

These three layers complement one another. This lesson focuses on the **second layer**, while clarifying when the first and third layers must be added.

## 2. Single-Instance Protects by Task Name

Core property:

~~~yaml
spring:
  cloud:
    task:
      single-instance-enabled: true
~~~

When this feature is enabled and the **shared locking mechanism is properly configured**, Spring Cloud Task allows only **one execution with the same task name** to hold the right to run at a time. Another process attempting to run with the same name during that window will not continue normal business execution; the exact error reporting and exit timing should be verified for your framework/launcher version.

**The task name is the grouping key.** For example:

~~~text
Task A: taskName = invoice-report-task
        args     = --report-date=2026-11-23

Task B: taskName = invoice-report-task
        args     = --report-date=2026-11-24
~~~

Even though the two processes handle **two different dates**, single-instance still considers them in the same scope because their **taskName is identical**. While A holds the lock, B cannot proceed under single-instance mode, regardless of the differing `report-date`.

Conversely:

~~~text
Task C: taskName = invoice-report-task
Task D: taskName = order-import-task
~~~

C and D have **two different names**, so single-instance does not automatically stop them from running in parallel, even if both access the same business database.

### 2.1. Where Does the Task Name Come From?

In standard configurations, Spring Cloud Task resolves the name via `TaskNameResolver`; setting `spring.application.name` establishes a stable application/task name:

~~~yaml
spring:
  application:
    name: invoice-report-task
~~~

An application can supply a custom `TaskNameResolver` if it needs a custom naming policy. When multiple instances must lock against each other, **all of them must compute the exact same name**; if even one instance resolves a different name, the two instances fall into separate lock groups.

Do not vary the name by Pod number, hostname, run ID, or timestamp if the goal is to block replicas of **the same task type**. Names that always differ render name-based restriction ineffective.

## 3. Why Is a Shared Database Needed?

A Spring Cloud Task application may run across multiple machines or containers that do not share JVM memory. `synchronized`, `ReentrantLock`, or an in-process boolean flag **only coordinates threads within that single process**; they cannot protect two independent Pods.

Spring Cloud Task's single-instance mechanism uses **Spring Integration** components for inter-process locking over JDBC. When multiple processes see **a single persistent lock store**, they contend on the same lock representing the task name. Only one process properly holds the lock; others are prevented from running concurrently with it.

~~~mermaid
flowchart TB
    LA["Cron / API"] --> PA["Pod A<br/>taskName=invoice-report-task"]
    LB["Manual trigger"] --> PB["Pod B<br/>taskName=invoice-report-task"]
    PA --> KA["Request lock: invoice-report-task"]
    PB --> KB["Request lock: invoice-report-task"]
    KA --> DB[("Shared JDBC lock DB<br/>e.g., INT_LOCK table")]
    KB --> DB
    DB --> R{"Only one side holds lock?"}
    R -->|Yes| S["One Pod executes business logic"]
    R -->|Other side| F["Other run is rejected / does not enter protected section"]
    S --> T[("TaskRepository<br/>TaskExecution metadata")]
~~~

**"Sharing a database" must be understood at the actual lock-store level.** Two containers given the same JDBC URL but configured with different schemas, different lock tables, or independent registries will not see each other's locks. Only processes using the same lock table/namespace through an appropriately configured registry can coordinate.

### 3.1. TaskRepository and the Lock Store Are Two Responsibilities

| Component | Primary Data | Purpose |
| --- | --- | --- |
| **TaskRepository** | `TASK_EXECUTION`, `TASK_EXECUTION_PARAMS`, completion metadata | Tracks history of each run, status, and exit code |
| **Spring Integration JDBC lock store** | Lock records, e.g., `INT_LOCK` table | Arbitrates which instance holds the lock for the same task name |
| **Business database** | Orders, reports, import states, unique keys | Ensures consistency and idempotency for actual business data |

The TaskExecution tables **do not automatically become a distributed lock** merely because multiple processes share the same TaskRepository. The single-instance feature requires the supporting dependencies and lock infrastructure to be configured properly.

Spring Integration JDBC has its own lock schema, typically with a table named `INT_LOCK`. Table names, columns, schemas, prefixes, regions, and setup details can vary by version or `LockRepository` customization. Use the **DDL compatible with the deployed Spring Integration JDBC version**. Do not assume changing `spring.cloud.task.table-prefix` automatically renames the Spring Integration lock table; the two schemas have separate configuration lifecycles.

### 3.2. Same TaskRepository but Different Lock Stores

Suppose Pod A and Pod B record `TASK_EXECUTION` into a shared schema, yet:

- A uses the JDBC lock store at `db1.schema_x.INT_LOCK`.
- B uses the JDBC lock store at `db1.schema_y.INT_LOCK`.

Without unified configuration, each Pod sees the lock as **free** in its own table. Both may execute, even though both TaskExecution histories end up in the same repository.

Therefore, checking only that "both see the TaskExecution table" is **insufficient** to prove single-instance is protecting the intended scope.

## 4. Conditions for the Restriction to Take Effect

All of the following factors must be verified simultaneously.

### 4.1. All Instances Enable the Feature

The configuration enabling the feature must be effective on **every process that could contend**. If only A enables single-instance while B runs independently without requesting the lock, B can enter the processing section even while A holds the lock.

~~~properties
spring.cloud.task.single-instance-enabled=true
~~~

Never treat a YAML file in the repository as proof that every Pod loaded that setting: profiles, environment variables, Config Server, or command-line arguments can override it. Verify the effective configuration inside the actual deployed image/environment.

### 4.2. Compatible Spring Integration Dependencies

The single-instance feature uses locking infrastructure from Spring Integration. Depending on the Spring Cloud Task release line, the required modules typically include **`spring-integration-core`** and **`spring-integration-jdbc`**. Example Maven dependency declaration:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-task</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-core</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Do not pin individual dependency versions when using a BOM; Spring Boot, Spring Cloud Task, and Spring Integration must stay **compatible with the system's release train**.

### 4.3. Lock Store Created and Used Properly

Before deploying:

1. Install the Spring Integration JDBC lock schema matching your DBMS.
2. Confirm all Pods share the **same** DataSource/LockRepository and lock namespace (if customized).
3. Ensure SQL read/write/delete/update privileges on the lock table as required by the library.
4. Verify DB resources and stable connectivity throughout the lock holding period.
5. Test with **two processes** in practice rather than checking only that a single instance succeeds.

An in-JVM-memory lock store or an embedded DB created separately per container provides no cross-process coordination. When sharing PostgreSQL, verify that the JDBC URL, database, schema, and initial objects are genuinely identical.

### 4.4. The Task Lifecycle Must Encompass the Protected Work

The lock only protects the window during which the Task mechanism holds it. If the runner spawns a background thread or triggers an async system and **returns immediately**, the framework may treat the Task as complete and release the lock **before the actual work finishes**.

Risky example:

~~~java
@Bean
ApplicationRunner unsafeRunner(ExecutorService executor) {
    return args -> {
        executor.submit(() -> importData()); // Returns immediately.
    };
}
~~~

In a finite task, wait for the async result, check for exceptions, and allow the runner to return only once the work is truly complete.

~~~java
@Bean
ApplicationRunner safeRunner(ExecutorService executor) {
    return args -> {
        Future<?> job = executor.submit(() -> importData());
        job.get(); // Wait for completion; exceptions propagate to the runner.
    };
}
~~~

This example only illustrates completion timing; in a real application, provide an `ExecutorService` bean, ensure resource cleanup, and handle interrupts properly.

## 5. Protection Scope Matrix

Assume both processes implement the feature properly and the lock store is configured as described. "Blocked" means **not permitted to execute business logic concurrently under the single-instance mechanism**; metadata recording and exit codes depend on the version.

| Processes A and B | Task Name | JDBC Lock Store | Expected Outcome |
| --- | --- | --- | --- |
| Same task type on two Pods | **Identical** | **Same table, same namespace** | One side holds the lock; the other does not run concurrently |
| Two reporting periods of the same application | **Identical** | **Same** | Restricted even though `--report-date` differs |
| Same import source, deployed as two differently named apps | **Different** | **Same** | Not cross-locked by name via single-instance |
| Same task name in two environments using different DBs | **Identical** | **Different** | Both sides can run in parallel |
| Same JDBC server, different lock table/schema | **Identical** | **Different lock namespace** | No mutual exclusion guarantee |
| Same name and lock store, but one side disables single-instance | **Identical** | **Same** | The side not requesting the lock can run in parallel |
| Two different names touching the same business table | **Different** | **Same** | Does not automatically prevent business data collisions |
| Same task name, rerun after the previous run ended | **Identical** | **Same** | Allowed to run again; does not prevent repeated processing by itself |

### Reading the Matrix Correctly

**Same name and same lock store** is required for the restriction to operate across processes. Same name alone is **not enough** when each instance uses its own database. Same database alone is **not enough** when locks have different names or reside in different tables/namespaces.

Parameters such as `--tenant`, `--date`, or `--source-id` **do not participate in single-instance locking by default**. If you want reports for day A and day B to run in parallel while blocking two runs for the same day, lock **by business key**; do not expect single-instance to inspect parameters automatically.

## 6. Two-Pod Configuration Example Using PostgreSQL

The `invoice-report-task` application runs finitely, records TaskExecutions to PostgreSQL, and enables name-based restriction. Example configuration:

~~~yaml
spring:
  application:
    name: invoice-report-task
  main:
    web-application-type: none
  datasource:
    url: ${TASK_DB_URL}
    username: ${TASK_DB_USER}
    password: ${TASK_DB_PASSWORD}
  cloud:
    task:
      single-instance-enabled: true
      initialize-enabled: false
~~~

**Scope explanation:**

- `spring.application.name`: provides a consistent Task name across Pods.
- `spring.datasource.*`: supplies the DB connection to JDBC components configured to use it. If you define multiple DataSources manually, verify the exact DataSource used by TaskRepository and LockRepository.
- `spring.cloud.task.single-instance-enabled`: requests single-run restriction by task name.
- `spring.cloud.task.initialize-enabled=false`: disables automatic Task schema initialization; Task tables and Spring Integration lock tables must be created beforehand via dedicated migrations.

Environment variables must be provided to both Pods, for example:

~~~text
Pod A:
  TASK_DB_URL=jdbc:postgresql://postgres.internal:5432/task_metadata
  TASK_DB_USER=task_runtime

Pod B:
  TASK_DB_URL=jdbc:postgresql://postgres.internal:5432/task_metadata
  TASK_DB_USER=task_runtime
~~~

The URL and username values are illustrative only. Passwords must come from a secret management system; **never print them to logs or pass them as application arguments** because arguments can be stored in `TASK_EXECUTION_PARAMS`.

In Kubernetes, each Pod may receive variables from the same ConfigMap/Secret, yet identical secret names do not prove Pods actually connect to the same database. Verify the infrastructure connection path, actual schema, and lock test results.

### 6.1. Simulation Run to Observe Locking

A runner that intentionally holds the process briefly:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.task.configuration.EnableTask;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableTask
public class LockScopeTaskApplication {
    public static void main(String[] args) {
        SpringApplication.run(LockScopeTaskApplication.class, args);
    }

    @Bean
    ApplicationRunner holdRunner() {
        return args -> {
            System.out.println("Entered protected task work");
            Thread.sleep(60_000); // For testing purposes only.
            System.out.println("Finished task work");
        };
    }
}
~~~

Run this sample only in a test environment. It requires the dependencies listed earlier, the Task schema, and the JDBC lock schema; never run it against a production DB.

In two terminals/containers running the same application and configuration:

~~~bash
# Terminal A:
java -jar lock-scope-task.jar

# Terminal B: launch while A is still inside Thread.sleep(...)
java -jar lock-scope-task.jar
~~~

**Outcome to verify:** Terminal A enters the runner, while B **must not concurrently print `Entered protected task work`** while A holds the lock. B's error and exit code can vary depending on the single-instance implementation version and lock-wait/check policy. After A finishes and releases the lock, re-running B must enter the runner normally.

If B enters the runner immediately as well, check the Task name, whether locking is enabled on both sides, the classpath, lock table, DataSource, and namespace before suspecting the framework.

## 7. Does Single-Instance Guarantee "Exactly Once"?

**No.** Single-instance addresses **two concurrent runs with the same name**. It does not prevent a new run from starting **after** the previous one has finished:

~~~text
02:00  Task A imports source-id=feed-23, succeeds, releases lock
02:05  Task B imports source-id=feed-23 again, acquires lock successfully
~~~

Both run **sequentially**, which is completely permitted by single-instance. If B creates duplicate orders, the flaw lies in business design.

For data ingestion, establish unique keys by `source_id` or `external_order_id`, verify checksums, and use upserts/appropriate transactions. For reports, place a unique constraint on `(tenant_id, report_date, report_version)`. For maintenance tasks, use fixed cutoff conditions and idempotent batch processing.

~~~sql
CREATE TABLE report_publication (
    tenant_id     varchar(100) NOT NULL,
    report_date   date NOT NULL,
    version       integer NOT NULL,
    status        varchar(30) NOT NULL,
    artifact_uri  text,
    PRIMARY KEY (tenant_id, report_date, version)
);
~~~

A unique constraint prevents unconditionally inserting the same logical report twice, **even if the orchestrator accidentally runs two differently named Tasks**. However, a unique constraint alone is not enough to prevent sending an email or calling an external API twice; those side effects need dedicated idempotency mechanisms such as an outbox or target-side idempotency keys.

**TaskExecution ID** is a **technical run identifier**, not a business key. Do not use TaskExecution ID to deduplicate an input file across retries.

## 8. When You Need Locking by Tenant, Date, or Source Entity

Multi-tenant problems often require:

- Two runs generating the **same** `(tenantId, reportDate)` must not overlap.
- Two **different** tenants or dates should be allowed to process in parallel.

Single-instance on `invoice-report-task` is too coarse: every period and every tenant compete for one lock. Choose one of two approaches:

1. **Keep name-based single-instance** if the job touches a global resource where running two periods concurrently is unsafe.
2. **Use a business lock** based on `(tenantId, reportDate)` if you want multiple periods in parallel, backed by a unique constraint/transaction in the database to establish processing ownership.

Example table declaring claim ownership for a period:

~~~sql
CREATE TABLE report_claim (
    tenant_id       varchar(100) NOT NULL,
    report_date     date NOT NULL,
    state           varchar(30) NOT NULL,
    owner_id        varchar(100),
    claimed_at      timestamptz,
    PRIMARY KEY (tenant_id, report_date)
);
~~~

The application can use a transaction to insert/claim ownership via the unique key, inspect prior state, and change owners under controlled rules. **Do not** simply run `SELECT ... WHERE state='NEW'` followed by `UPDATE` in two unsynchronized transactions, because both may read the same stale state and both proceed to work.

If using time-bounded leases to recover from crashes, add a **fencing token** or conditional update accepting only the current owner. Because a lease can expire while the old process is still alive, a new process may take ownership and both may try to write results. A TTL-based lock alone does not invalidate stale side effects from an old process.

Modifying `TaskNameResolver` to embed `tenantId` directly into the Task name is **not a default solution**: names can suffer from high cardinality, drift across deployment versions, complicate history queries, and still fail to prevent duplicate retries after the lock is released.

## 9. Locks, TTL, and Process Failures

Distributed locking depends on **ownership** and **lock lifecycle**. Systems must handle these scenarios:

| Failure | Risk | How to Prepare |
| --- | --- | --- |
| Pod killed before cleanly releasing the lock | Lock record remains, blocking the next run from acquiring immediately | Understand version-specific TTL/recovery, monitor stuck locks, and test crash behavior |
| Execution exceeds lock validity duration | Another process may acquire the lock while the old process is still running | Choose an appropriate TTL, track runtime, and apply fencing/idempotency in business logic |
| Connection lost to lock store | Ownership cannot be confirmed safely | Follow fail-safe principles: stop or avoid entering critical sections that could duplicate work |
| Task returns before async work finishes | Lock is released prematurely | Await Futures, transactions, and output completion |
| Each Pod uses its own in-memory H2 | No shared lock state | Use a truly shared JDBC store or equivalent distributed locking mechanism |
| Two instances run different versions/configs | Lock key generation or namespace may diverge | Deploy consistently and verify during rolling updates |
| Operator manually deletes a lock record | Old process may still be running and actively holding business work | Maintain a runbook; check process liveness and recovery steps before touching the lock table |

Some Spring Cloud Task versions support options such as `spring.cloud.task.single-instance-lock-ttl` and `spring.cloud.task.single-instance-lock-check-interval`. Always check the **configuration metadata of your exact version** for property names, units, defaults, and algorithms. **Never pick a TTL based solely on average runtime**; account for worst-case runs, interrupt handling, transient network issues, and ownership semantics upon expiration.

Note: Lock TTL and Kubernetes Job or workflow timeouts are **not a single unified setting**. A Job timeout may kill the Pod, while lock release still depends on the failure mode and `LockRepository` behavior. Never delete an active lock just to "retry faster" without checking the old instance.

## 10. Differences from Kubernetes concurrencyPolicy

In a Kubernetes CronJob:

~~~yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: daily-invoice-report
spec:
  schedule: "0 2 * * *"
  timeZone: "Asia/Ho_Chi_Minh"
  concurrencyPolicy: Forbid
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: task
              image: registry.example/invoice-report-task:1.0.0
              args:
                - "--report-date=2026-11-23"
~~~

`Forbid` prevents overlaps among Jobs **created by that specific CronJob**, whereas Spring Cloud Task's single-instance mechanism restricts processes with the **same task name** sharing a lock store. A task invoked separately via an API or another CronJob falls outside the original CronJob's `Forbid` scope, yet can still contend for the same Spring Cloud Task lock if configured identically.

The fixed `--report-date` above is **illustrative only**; never deploy a recurring schedule with a hardcoded date. In production, the orchestrator or application logic must determine the target business date in the agreed time zone. The `timeZone` field requires a Kubernetes version that supports it.

## 11. Observing and Diagnosing Concurrency Incidents

You must be able to correlate **task name**, **TaskExecution ID**, **orchestrator request ID**, **non-sensitive business parameters**, and the **lock-contention outcome**.

Suggested structured logging:

~~~text
event=task_start_requested taskName=invoice-report-task
  businessKey=acme:2026-11-23 runRef=workflow-1042
event=task_lock_acquired taskName=invoice-report-task
  runRef=workflow-1042
event=task_completed taskName=invoice-report-task
  executionId=4102 runRef=workflow-1042 exitCode=0
~~~

Specific events depend on your application and framework instrumentation; **Spring Cloud Task does not emit these exact log lines out of the box**. Never log tokens, passwords, or sensitive personal data.

You can query TaskRepository:

~~~sql
SELECT TASK_EXECUTION_ID,
       TASK_NAME,
       START_TIME,
       END_TIME,
       EXIT_CODE,
       EXIT_MESSAGE
FROM TASK_EXECUTION
WHERE TASK_NAME = 'invoice-report-task'
ORDER BY START_TIME DESC;
~~~

This query shows **TaskExecution history**, not live lock state. `END_TIME IS NULL` does not prove a process is still alive: it may have been killed before updating metadata. Likewise, **do not assume** a run rejected while acquiring a lock will always leave a TaskExecution record with a specific exit code; recording depends on the version and when the framework detected the conflict.

For real investigations, also cross-check:

- Logs from both Pods and the failure reason at the lock-acquisition step.
- Effective `single-instance-enabled` config and task name on each Pod.
- Evidence both connect to the **same lock store**: JDBC URL, database, schema, lock namespace, and migrations.
- Pod/Job status, age, runtime, retries, and timeout behavior.
- Business state tables to spot duplicate results after retries.

You should instrument metrics for lock contention counts, wait times, rejections, abnormally old locks, and duplicate processing attempts by business key, exported through your observability stack.

## 12. Verification Procedure in a Test Environment

Run the following tests **after creating both the JDBC lock schema and the TaskRepository schema**:

| Test | Procedure | Expected Result |
| --- | --- | --- |
| **A. Same name, same DB** | Start A; while runner sleeps, launch B immediately | Only one side enters processing at a time |
| **B. Different args, same name** | Change `--report-date` on B while keeping `taskName` | B is still restricted while A holds the lock |
| **C. Different names, same DB** | Use two different `spring.application.name` values | Both can run simultaneously; confirms lock scopes by name only |
| **D. Same name, different DB** | Point B to an independent lock DB | No coordination guarantee; test demonstrates the risk |
| **E. Lock disabled on one side** | A enables, B disables single-instance | Protection scope is broken |
| **F. Sequential runs** | Wait for A to finish, then launch B with same args | B can run; verify idempotency avoids duplicate output |
| **G. Process killed** | Kill A while holding lock; test B following runbook | Observe lock recovery behavior and timeout/fencing requirements |
| **H. Rolling update** | Run two image/app versions with same name and lock store | Confirm both versions obey the same lock scope |

When documenting tests, capture the command invoked, timestamp, task name, target database/schema, and output logs. **Never** test in production or deliberately break locks while real users depend on them.

### Hands-On Exercise

A multi-tenant platform runs `cleanup-task` to delete expired temporary data. The operations team sets three requirements:

1. Never allow **two Pods to execute any cleanup task simultaneously**.
2. Allow `cleanup-task` and `invoice-report-task` to run concurrently even though they share TaskRepository.
3. If `cleanup-task` retries after an error, it must not delete data past `cutoff` or repeat side effects.

Propose a configuration and design:

- Set a stable Task name; enable single-instance across all cleanup Pods; share the JDBC locking mechanism.
- No cross-lock with `invoice-report-task` is needed since names differ, unless both jobs contend for a shared business resource requiring an additional mechanism.
- Fix the cutoff via an absolute date/time parameter; delete in safe batches/transactions; track results by business key and support safe resumption after errors.
- Test two Pods with the same name, two Pods with different names, lock-DB loss, and process restarts.

**Extension question:** if the requirement changes to "only block cleanups with the same `tenantId`; other tenants must run in parallel," why is single-instance locking on `cleanup-task` too broad? Sketch a claim table with unique key `(tenant_id, cleanup_cutoff)` and transaction/fencing rules to satisfy it.

## 13. Key Takeaways

1. **Single-instance restricts by `taskName`**, without automatically distinguishing date, tenant, or source-id parameters.
2. **Having the same name is not enough**: instances must genuinely coordinate through the **same JDBC lock backend**, schema, and namespace; every competing process must participate in locking.
3. **TaskRepository tracks runs**, whereas Spring Integration's lock store arbitrates concurrent execution rights; business data requires its own consistency safeguards.
4. This mechanism **does not provide exactly-once**: a second sequential run can still duplicate data. Apply idempotency, unique constraints, and transactions keyed by business key.
5. Choose timeouts/TTL carefully, test crashes, never release locks before async work completes, and avoid manual edits to active locks.
6. CronJob restrictions, Spring Cloud Task locks, and business locks are **three distinct scopes**. Design your solution around the exact scope you need to protect.

### References

- [Spring Cloud Task Reference — Features: Restricting Spring Cloud Task Instances](https://docs.spring.io/spring-cloud-task/reference/features.html)
- [Spring Cloud Task Reference — TaskRepository, TaskExecution](https://docs.spring.io/spring-cloud-task/reference/features.html)
- [Spring Integration Reference — JDBC Lock Registry](https://docs.spring.io/spring-integration/reference/jdbc/lock-registry.html)
- [Kubernetes Documentation — CronJob](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/)
