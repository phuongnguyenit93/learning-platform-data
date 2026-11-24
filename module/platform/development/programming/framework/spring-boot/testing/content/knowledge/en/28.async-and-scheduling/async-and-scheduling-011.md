# Testing Reruns, Duplicate Handling, and Mid-Run Failures

## 1. The problem: one successful run does not prove the system recovers properly

In Spring Boot applications, asynchronous tasks and scheduled jobs can run multiple times due to `@Scheduled` ticks, retries after timeouts, an operator clicking "Run now", consumers redelivering messages, instance restarts, or two replicas starting the job together. A job processing 100 orders might finish 40 and hit an exception on order 41. Next time, the system must resume cleanly: never duplicating side effects for the 40 completed orders, never dropping the failed order, and never double-processing when two workers see the same order simultaneously.

An **insufficient** example:

~~~java
@Test
void batchRuns() {
    runner.runOnce();
    assertThat(receipts.count()).isEqualTo(3);
}
~~~

The test above only observes one run. It does not prove the outcome of a **second** run, does not test two concurrent invocations, does not inject failures between items, and does not distinguish failures before vs after transaction commit. A seemingly minor flaw can issue two invoices, send two emails, or charge twice.

This lesson shows how to design and test three core properties:

- **Rerun/resume**: re-running after success or failure without losing work or duplicating already-confirmed outcomes.
- **Duplicate handling / idempotency**: the same business operation ID submitted/received multiple times or concurrently produces side effects adhering to the defined contract.
- **Partial failure / recovery**: errors at specific points (before writes, after flush, before commit, mid-batch, after commit before publish/ack) are actively tested with clear recovery plans.

The focus sits in **Async and Scheduling** within Spring Boot, so examples use `@Scheduled`, transaction boundaries, Spring Data JPA, failure injection, concurrency tests, retry policies, durable outboxes, and consumer idempotency. The lesson includes a **Java 17 / Spring Boot 3.5.16 / H2 / JUnit 5 / Mockito Maven project** with full code and database-state assertions. Process crashes and external side effects are covered as advanced integration guidance because throwing an exception in one test JVM is not equivalent to a real process crash.

### Learning outcomes

After this lesson, you can:

1. Distinguish **at-most-once**, **at-least-once**, **idempotent effect**, and "exactly once" claims within defined boundaries.
2. Build a failure matrix covering before/after flush, before/after commit, between items, and before/after acknowledgment.
3. Design jobs with stable **idempotency keys** and clear business statuses.
4. Use **per-item transactions** so subsequent runs resume after a mid-batch error.
5. Use `@Lock(PESSIMISTIC_WRITE)` and database unique keys to guard against concurrent processing of the same item.
6. Test `@Scheduled` using **manual triggers** instead of waiting real seconds for timers.
7. Use `@MockitoBean` for fault-injection hooks, without mocking the repository/transaction itself when testing commit/rollback.
8. Inspect database state **outside test-managed transactions**, avoiding false positives from default rollbacks.
9. Know when external side-effect failures require **transactional outbox, idempotent consumers, retry/backoff, and reconciliation**.
10. Recognize H2's limitations and build production-like tests with PostgreSQL/Testcontainers when testing locks/isolation.

**Foundational principle:** A job may be invoked many times; only business side effects must satisfy non-duplication contracts, and interrupted work must be detected and recovered.

## 2. Definitions you cannot skip

### 2.1. "Rerun" takes many forms

- **Rerun after success**: already-`DONE` items must be skipped.
- **Retry after pre-commit exception**: transaction rolls back, item remains eligible; next run processes it again.
- **Restart after mid-batch crash**: some items committed, others did not; new run resumes from durable state.
- **Duplicate trigger**: scheduler/manual/API/queue all trigger processing for the same business ID.
- **Concurrent duplicate**: two instances process the same ID simultaneously.
- **Replay**: consumer re-reads events due to offset/ack state or operator reset.
- **Reconciliation**: re-scanning to catch un-`DONE` work or unconfirmed side effects.

Each form produces a different failure mode. Happy-path testing alone cannot cover them.

### 2.2. At-most-once vs at-least-once

| Delivery/processing model | Good property | Risk |
| --- | --- | --- |
| At-most-once | Tries to avoid repeating | Errors can drop an operation |
| At-least-once | Keeps/retries until handled | Same operation may run multiple times |
| Idempotent effect | Multiple attempts for one operation yield no duplicate business result | Requires keys, transaction boundaries, and proper tests |
| Exactly-once within one DB transaction | Atomic commit + unique constraint can yield one data effect | Does not extend automatically to email/brokers/payments |
| Distributed end-to-end exactly-once | Requires special guarantees across systems and failure boundaries | Cannot be inferred from an annotation or mock test |

To achieve **at-least-once + idempotency**, allow retries while preventing duplicate business side effects. That is usually the pragmatic design for jobs and message handlers.

### 2.3. What does idempotent mean?

For an operation `process(orderId=42)`, calling it once, twice, or ten times produces no extra business outcome beyond the first valid execution. Idempotent **does not necessarily** mean the method only ever enters once or logs only one line. A job may retry multiple times while only one final receipt/order state exists.

Example:

~~~text
process("invoice-42") run 1 -> receipt invoice-42 appears
process("invoice-42") run 2 -> skipped; still only one receipt
process("invoice-42") concurrently from 2 threads -> only one transaction executes to completion
~~~

When an operation carries a different payload for the same ID (e.g., `order-42` with a changed amount), **do not silently treat it as a valid duplicate**. Identity/payload consistency must be an explicit policy: reject conflicts or version the operation.

### 2.4. Rerun-safe does not mean retry-safe for non-DB side effects

~~~text
DB update + unique receipt inside the same transaction
    => Can be atomic inside the database

DB commit
  -> send email / call payment API / publish Kafka
    => No longer inside the same atomic database transaction
~~~

If the process crashes after sending the email but before saving "sent", a retry may send **again**. If it crashes after DB commit before sending the email, you cannot rely on an in-memory callback to ensure the email gets sent. Section 13 presents outbox and idempotency for those cases.

## 3. Failure-point matrix: where should faults be injected?

Suppose a worker processes `item-42` in this sequence:

~~~text
T0: trigger receives itemId
T1: read row, lock item by business ID
T2: check if already DONE?
T3: insert receipt / update item status
T4: flush SQL to DB
T5: COMMIT transaction
T6: emit external event or wake outbox relay
T7: external ACK / consumer commits offset
~~~

| Fault injection | Observable state | On rerun |
| --- | --- | --- |
| Before T1 | No data changed yet | Item remains eligible |
| After T1, before write | Lock released on rollback | Another run can process it |
| After T3/T4, before T5 | SQL flushed yet transaction rolled back | No receipt exists; item not `DONE` |
| After T5, before T6 | DB committed; external event may be lost | Outbox/reconciliation must pick it up |
| After T6, before T7 | Event may be received while caller doesn't know | Retry may duplicate; consumer must be idempotent |
| Between item A and item B | A committed, B did not | Rerun processes B onward |
| Two workers handle same ID | One worker waits/skips or hits controlled conflict | Never two business receipts |
| Side effect fails permanently | Item moves to `RETRY_WAIT`/`FAILED`/DLQ with error info | Never retries infinitely |

**Key point:** `saveAndFlush()` is not `commit`. A test asserting an entity exists **inside the same transaction** after flush does not prove data durability across a worker crash or rollback.

### 3.1. Intentional fault injection

A test-only `FailureGate` can throw a `RuntimeException` after flushing data but before transaction commit. If the error propagates across the transactional proxy, Spring rolls back the transaction by default for unchecked exceptions. This lets tests prove database atomicity.

Do not call a `RuntimeException` an "exact simulation of a JVM kill": a process crash terminates the runtime abruptly, leaving connection/transaction cleanup to the DB and potentially leaving external side effects already executed. Real crash-recovery tests require process/container boundaries.

### 3.2. Goal of a matrix test

A good test should:
1. Create a **distinct item** with clear identity.
2. Trigger at the chosen boundary.
3. Inject deterministic failures independent of timing.
4. Read the database back **after the transaction ends**.
5. Trigger a rerun.
6. Assert final status, receipt count, and observed attempt count.
7. Clean up and ensure the test leaves no data affecting other cases.

Do not simply verify `mockGateway.send()` once and conclude persisted state is correct.

## 4. Two checkpoint layers: per-item transactions and durable state

### 4.1. One transaction for the entire batch

Wrapping a 1,000-item batch in **a single transaction** means an exception on the last item rolls back all database progress. The benefit is all-or-nothing, yet:
- Long transactions hold locks and connections too long.
- Retrying from scratch is expensive.
- Non-DB side effects already performed do not roll back automatically.
- One poison item can block the entire batch.

Use this only when the business contract truly demands batch-wide atomicity and batch sizes allow it.

### 4.2. Separate transaction per item

An alternative:

~~~text
BatchRunner.runOnce()                  no outer transaction
  |
  +-- ItemProcessor.process("a")       Transaction T1 -> COMMIT
  +-- ItemProcessor.process("b")       Transaction T2 -> FAIL/ROLLBACK
  X-- ItemProcessor.process("c")       not run yet
                                        |
Rerun                                   v
  +-- "a": DONE -> not scanned again
  +-- "b": PENDING -> T3 -> COMMIT
  +-- "c": PENDING -> T4 -> COMMIT
~~~

Crucial detail: `BatchRunner` **is not** marked `@Transactional` across the batch, and it calls `ItemProcessor`, which is **a separate Spring bean**. Thus `@Transactional` on the public `process` method runs through the proxy, creating an independent transaction per item.

### 4.3. Beware of self-invocation

Wrong:

~~~java
@Service
class BadJob {
    public void runAll() {
        this.processOne("a");
        this.processOne("b");
    }

    @Transactional
    public void processOne(String id) {
        // ...
    }
}
~~~

With Spring proxy-based transaction AOP, `this.processOne()` bypasses the proxy, so the annotation may not start a new transaction. Extract the processor into a separate bean, or use `TransactionTemplate` when programmatic transaction control is desired.

### 4.4. DONE and receipt must be written atomically

If `WorkItem.status=DONE` without a `CompletionReceipt`, a retry skips it and business output is lost. If the receipt exists while status remains `PENDING`, a retry causes unique conflicts or duplicate side effects.

When both are database state, write them **in the same transaction** so they either commit together or roll back together. Database primary keys/unique constraints guard against two receipts for one business ID.

### 4.5. Transaction duration and batch size

Never load millions of rows into a Java list in memory. Production uses pagination/chunk claiming and bounded work durations. With multiple workers, avoid having every worker query the same huge pending list and contend on locks; use atomic claim/lease or `SKIP LOCKED` where DB/ORM supports it and tests verify it.

The lab intentionally processes a few records to demonstrate semantics. It is not a distributed job scheduler with leasing, heartbeats, and long-running external tasks.

## 5. Duplicate handling under concurrency

### 5.1. Non-atomic check-then-act

Wrong:

~~~java
if (!receiptRepository.existsById(id)) {
    receiptRepository.save(new Receipt(id));
}
~~~

Two threads can simultaneously see `exists=false` and both save. If the database has a unique key, one transaction fails; without one, two receipts get created.

For duplicate-safe processing, use **atomic constraints/locks/claims** and test concurrent requests. A JVM `synchronized` block does not protect across multiple Spring Boot instances on multiple machines.

### 5.2. Pessimistic row lock

In the lab using Spring Data JPA:

~~~java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@Query("select w from WorkItem w where w.id = :id")
Optional<WorkItem> findLockedById(
        @Param("id") String id);
~~~

This method is called **inside** a transaction. It acquires a write lock on the row before checking status and creating the receipt, serializing concurrent attempts for the same ID under database locking semantics. The second worker waits until the first transaction commits, then reads `DONE` and skips.

**Limitation:** Pessimistic locking depends on DB isolation, lock timeouts, and concurrency behavior. H2 exercises basic paths; PostgreSQL/Testcontainers is needed for production-like lock, deadlock, and failover tests.

### 5.3. Primary key/unique constraint is the last line of defense

`CompletionReceipt.workId` uses the business ID itself as primary key. If logic forgets to lock or tries to create a duplicate, the database refuses two receipt rows with the same ID. Do not rely solely on unique constraints to *hide* races: tests must define what callers receive on conflict and have explicit retry/resolution policies.

### 5.4. Row locks do not solve all external duplicates

Holding a DB lock while calling a payment gateway **inside a transaction** does not create an atomic commit across the payment provider. If the gateway charged yet the DB rolls back, the next run charges again. Use provider idempotency keys, outbox/sagas, and reconciliation; avoid holding DB transactions open across long network calls whenever possible.

### 5.5. Duplicate payload policy must be defined

Two messages sharing the same `eventId` may carry:
- Byte-for-byte identical payloads → safe to treat as replay.
- Payload changed due to a new event version → requires versioning rules.
- Different payload with the same idempotency key → typically reject as a conflict and alert.

Store a payload hash or operation parameters alongside the idempotency key for sensitive operations (payments, financial transfers). Checking only `existsById` and skipping everything can mask invalid mutation requests.

## 6. @Scheduled, @Async, and proactive testing

### 6.1. @Scheduled does not guarantee cluster-wide single execution

~~~java
@Scheduled(fixedDelayString =
        "${lab.job.delay-ms:60000}")
public void tick() {
    runner.runOnce();
}
~~~

Spring scheduling invokes the method on **every Spring application instance with scheduling enabled**. With 3 replicas, 3 similar triggers can fire. `fixedDelay` measures from the end of one invocation to the start of the next within one schedule; it is **not a distributed lock**.

A durable approach:
- Use unique keys and DB locks/claims to protect items.
- Or use scheduler leader election, distributed locks, or fencing per architecture.
- Write concurrent processing tests even if production currently runs a single instance.

### 6.2. Manual triggers instead of sleep

To test business jobs effectively:
- Isolate `ScheduledTrigger` purely as an adapter.
- Give the runner a public `runOnce()` method callable directly.
- Enable `@EnableScheduling` via a profile outside tests.
- Invoke `runner.runOnce()`/`trigger.tick()` directly in JUnit.

Do not do:

~~~java
Thread.sleep(65000);
assertThat(...).isEqualTo(...);
~~~

Waiting for real schedule ticks makes tests slow and racy. If cron parsing/next execution times need testing, test `CronExpression`/`Trigger` separately with explicit synthetic instants rather than sleeping until the next minute.

### 6.3. @Async

If a job dispatches tasks to `@Async`/an executor:
- The scheduler thread only enqueues; returning does not mean tasks completed.
- Use `CompletableFuture`, `CountDownLatch`, or bounded Awaitility to wait for side effects.
- Exceptions in `void` async methods may not propagate to the scheduler caller.
- The caller's transaction `ThreadLocal` does not transfer automatically to worker threads.
- You must test failures, cancellations, timeouts, and executor rejections.

The main lab uses synchronous `runOnce()` so transaction and restart semantics stay deterministic; a scheduler can still trigger it on a schedule. Asynchronous variants are covered in the extension sections.

### 6.4. Cron, timezones, DST, and duplicate fires

With `@Scheduled(cron="...")`:
- Specify `zone` explicitly when schedules follow a regional business calendar.
- Test expectations on daylight saving transition days if the timezone observes DST.
- Never infer "once per day" from a cron expression alone; restarts, multiple nodes, and manual reruns create duplicates.
- Use a job execution key such as `businessDate + jobType` for idempotency.
- For backfills, define explicit time windows and cutoffs instead of relying on `LocalDateTime.now()`.

## 7. Runnable Spring Boot project: a safely rerunnable job

### 7.1. Business scenario

The application processes `WorkItem` records with `id`, `payload`, and `status`. On a successful run:
1. Read and lock the row using `PESSIMISTIC_WRITE`.
2. If status is already `DONE`, **return without creating a new receipt**.
3. Insert `CompletionReceipt` whose primary key equals `workId`.
4. Update `WorkItem.status=DONE`.
5. Flush database writes.
6. Allow tests to inject a `RuntimeException` right before commit.
7. Transaction commits if no error occurred.

A `BatchRunner` iterates over `PENDING` items, invoking `ItemProcessor.process(id)` through the Spring proxy. If item B fails, the runner stops; item A already committed, and item C never ran. Next time, querying `PENDING` automatically resumes.

No real network or email calls. The receipt represents **business side effects within the same database**. Section 13 shows how to add an outbox when side effects live outside the DB.

### 7.2. Directory tree

~~~text
job-rerun-recovery-lab/
├── pom.xml
├── src/main/resources/application.properties
├── src/main/java/com/example/jobrecovery/
│   ├── JobRecoveryApplication.java
│   ├── SchedulerConfiguration.java
│   ├── WorkStatus.java
│   ├── WorkItem.java
│   ├── CompletionReceipt.java
│   ├── WorkItemRepository.java
│   ├── CompletionReceiptRepository.java
│   ├── FailureGate.java
│   ├── NoopFailureGate.java
│   ├── ItemProcessor.java
│   ├── BatchRunner.java
│   └── ScheduledTrigger.java
└── src/test/java/com/example/jobrecovery/
    └── JobRecoveryIntegrationTest.java
~~~

All Java classes sit in package `com.example.jobrecovery`, with tests in the same package using public APIs. The lab contains JPA entities/repositories, a transactional item processor, a runner without an outer transaction, a test-replaceable failure gate, and JUnit integration tests. **Do not** hand-write production migrations from this: H2 and Hibernate `create-drop` are solely for lab/test use.

### 7.3. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>job-rerun-recovery-lab</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
    <dependency>
      <groupId>com.h2database</groupId>
      <artifactId>h2</artifactId>
      <scope>runtime</scope>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

The Spring Boot 3.5 parent/BOM manages Spring Framework 6.2, Spring Data JPA/Hibernate, HikariCP, Mockito, AssertJ, and JUnit Jupiter. Java 17 supports `Stream.toList()` and records if needed.

### 7.4. application.properties

`src/main/resources/application.properties`:

~~~properties
spring.application.name=job-rerun-recovery-lab

# Lab/Test only: H2 database persists while the JVM context is alive.
spring.datasource.url=jdbc:h2:mem:job_recovery;DB_CLOSE_DELAY=-1;LOCK_TIMEOUT=10000
spring.datasource.username=sa
spring.datasource.password=

spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.show-sql=false

# fixedDelay is only activated when the scheduler profile is enabled.
lab.job.delay-ms=60000
~~~

`LOCK_TIMEOUT=10000` gives the concurrent test example room while one transaction holds a row lock. In production, derive lock timeouts from SLAs and DB config; never copy the H2 URL or `ddl-auto=create-drop` into production.

### 7.5. JobRecoveryApplication.java

~~~java
package com.example.jobrecovery;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JobRecoveryApplication {

    public static void main(String[] args) {
        SpringApplication.run(JobRecoveryApplication.class, args);
    }
}
~~~

To keep schedulers isolated from integration tests, the main class **omits** `@EnableScheduling`.

### 7.6. SchedulerConfiguration.java

~~~java
package com.example.jobrecovery;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.scheduling.annotation.EnableScheduling;

@Configuration(proxyBeanMethods = false)
@Profile("scheduler")
@EnableScheduling
public class SchedulerConfiguration {
}
~~~

When the `scheduler` profile is active, Spring detects `@Scheduled` and registers triggers. In JUnit we use the `test` profile so jobs are invoked manually with no background timer racing against test setup/cleanup. This profile is a **lab design choice**, not a built-in Spring Boot default property for disabling schedulers.

### 7.7. WorkStatus.java

~~~java
package com.example.jobrecovery;

public enum WorkStatus {
    PENDING,
    DONE
}
~~~

The lab keeps statuses minimal to focus on rollback/resume. Production extensions expand this to `PENDING/PROCESSING/RETRY_WAIT/DONE/FAILED` with leases/`nextAttemptAt` for long-lived work queues.

### 7.8. WorkItem.java

~~~java
package com.example.jobrecovery;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "work_items")
public class WorkItem {

    @Id
    @Column(name = "work_id", length = 80)
    private String id;

    @Column(nullable = false, length = 150)
    private String payload;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private WorkStatus status;

    protected WorkItem() {
        // Required by JPA.
    }

    public WorkItem(String id, String payload) {
        this.id = id;
        this.payload = payload;
        this.status = WorkStatus.PENDING;
    }

    public String getId() {
        return id;
    }

    public String getPayload() {
        return payload;
    }

    public WorkStatus getStatus() {
        return status;
    }

    public void markDone() {
        this.status = WorkStatus.DONE;
    }
}
~~~

Primary key `id` is the **stable business operation ID** of the work item. Do not generate a fresh random ID per retry if you want to deduplicate the same operation. Test fixtures use synthetic payloads.

### 7.9. CompletionReceipt.java

~~~java
package com.example.jobrecovery;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "completion_receipts")
public class CompletionReceipt {

    @Id
    @Column(name = "work_id", length = 80)
    private String workId;

    @Column(nullable = false, length = 150)
    private String payload;

    protected CompletionReceipt() {
        // Required by JPA.
    }

    public CompletionReceipt(
            String workId, String payload) {
        this.workId = workId;
        this.payload = payload;
    }

    public String getWorkId() {
        return workId;
    }

    public String getPayload() {
        return payload;
    }
}
~~~

`workId` is the primary key, so the database cannot hold two receipt rows with the same ID. It represents a **business outcome within the same database**, not an email opened by a recipient or a payment confirmed by a provider.

### 7.10. WorkItemRepository.java

~~~java
package com.example.jobrecovery;

import java.util.List;
import java.util.Optional;

import jakarta.persistence.LockModeType;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface WorkItemRepository
        extends JpaRepository<WorkItem, String> {

    List<WorkItem> findByStatusOrderByIdAsc(
            WorkStatus status);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select w from WorkItem w where w.id = :id")
    Optional<WorkItem> findLockedById(
            @Param("id") String id);
}
~~~

`findByStatusOrderByIdAsc(PENDING)` returns a candidate snapshot at query time. It may include an ID currently being processed by another instance; that is **acceptable** because the real decision happens inside transactional `findLockedById`, checking status **after acquiring the lock**.

Never query pending items once and assume every row stays pending when its turn comes.

### 7.11. CompletionReceiptRepository.java

~~~java
package com.example.jobrecovery;

import org.springframework.data.jpa.repository.JpaRepository;

public interface CompletionReceiptRepository
        extends JpaRepository<CompletionReceipt, String> {
}
~~~

This repository supports test readbacks and production persistence. Never mock repositories in this lesson's integration tests because real transactions, locks, and unique constraints must be verified.

### 7.12. FailureGate.java

~~~java
package com.example.jobrecovery;

public interface FailureGate {

    void afterDatabaseWrites(String workId);
}
~~~

This hook is **not business logic**; it is a seam to inject an exception right after SQL flushes but before `@Transactional` commits. The production implementation below is a no-op. Tests use `@MockitoBean` to replace the bean by type and configure faults on specific items.

### 7.13. NoopFailureGate.java

~~~java
package com.example.jobrecovery;

import org.springframework.stereotype.Component;

@Component
public class NoopFailureGate implements FailureGate {

    @Override
    public void afterDatabaseWrites(String workId) {
        // No-op in normal execution environments.
    }
}
~~~

Do not rely on a real external system to produce non-deterministic timing failures. In advanced integration tests, hooks can be replaced by failpoints/instrumentation at producer, database, ack, or process boundaries.

### 7.14. ItemProcessor.java

~~~java
package com.example.jobrecovery;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ItemProcessor {

    private final WorkItemRepository items;
    private final CompletionReceiptRepository receipts;
    private final FailureGate failureGate;

    public ItemProcessor(
            WorkItemRepository items,
            CompletionReceiptRepository receipts,
            FailureGate failureGate) {
        this.items = items;
        this.receipts = receipts;
        this.failureGate = failureGate;
    }

    @Transactional
    public void process(String workId) {
        WorkItem item = items.findLockedById(workId)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Unknown work item: " + workId));

        if (item.getStatus() == WorkStatus.DONE) {
            // Operation already completed; do not create a new receipt.
            return;
        }

        // WorkItem row stays locked until the transaction ends.
        receipts.saveAndFlush(new CompletionReceipt(
                item.getId(), item.getPayload()));

        item.markDone();

        // Flush status UPDATE before the failpoint.
        items.flush();

        // Tests can throw RuntimeException here.
        // Both receipt INSERT and WorkItem UPDATE roll back.
        failureGate.afterDatabaseWrites(workId);
    }
}
~~~

### 7.15. Inspecting the transaction boundary closely

- `@Transactional` applies because `process` is called through the Spring proxy, starting one transaction per call.
- `findLockedById` issues a query with `PESSIMISTIC_WRITE`; the lock holds until commit/rollback.
- `saveAndFlush` sends the receipt INSERT to the database **without committing**.
- `item.markDone()` is dirty-checked; `items.flush()` sends the UPDATE.
- `FailureGate` can throw `RuntimeException`; Spring's transaction interceptor rolls back all prior writes.
- If the method returns normally, the transaction commits; a subsequent call locks the row, sees `DONE`, and returns without inserting a receipt.
- For concurrent calls on the same `workId`, the row lock serializes check-and-write, while the receipt primary key prevents leftover duplicates.

No external side effects occur in this method. That choice is **intentional** to demonstrate pure database atomic semantics. Adding `emailGateway.send` at the end of the method while still claiming "rollback undoes the email" would be an architectural bug.

### 7.16. BatchRunner.java

~~~java
package com.example.jobrecovery;

import java.util.List;

import org.springframework.stereotype.Service;

@Service
public class BatchRunner {

    private final WorkItemRepository items;
    private final ItemProcessor processor;

    public BatchRunner(
            WorkItemRepository items,
            ItemProcessor processor) {
        this.items = items;
        this.processor = processor;
    }

    // Intentionally NOT @Transactional across the whole batch.
    public void runOnce() {
        List<String> ids = items
                .findByStatusOrderByIdAsc(WorkStatus.PENDING)
                .stream()
                .map(WorkItem::getId)
                .toList();

        for (String id : ids) {
            processor.process(id);
        }
    }
}
~~~

If `process("b")` throws an exception, the loop stops, yet `process("a")` already returned after its own transaction committed. The next `runOnce()` queries **fresh `PENDING` items**, skipping A. This is a valid recovery contract for small sequential jobs.

For large production batches, replace full-table `findByStatus...` with paged/claimed batches. If the job must continue processing remaining items after item B fails rather than halting, catch the exception **outside the item transaction**, record failure/retry state, and proceed per policy; tests must assert that exact expectation rather than silently swallowing errors.

### 7.17. ScheduledTrigger.java

~~~java
package com.example.jobrecovery;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class ScheduledTrigger {

    private final BatchRunner runner;

    public ScheduledTrigger(BatchRunner runner) {
        this.runner = runner;
    }

    @Scheduled(fixedDelayString =
            "${lab.job.delay-ms:60000}")
    public void tick() {
        runner.runOnce();
    }
}
~~~

The trigger is razor-thin, purely delegating. Use `@EnableScheduling` via the `scheduler` profile to start real scheduled runs. Under the `test` profile, the adapter bean still exists so JUnit can call `tick()` directly without waiting for real time or letting an active scheduler race over fixtures.

### 7.18. JobRecoveryIntegrationTest.java

`src/test/java/com/example/jobrecovery/JobRecoveryIntegrationTest.java`:

~~~java
package com.example.jobrecovery;

import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.doNothing;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.reset;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;

@SpringBootTest
@ActiveProfiles("test")
class JobRecoveryIntegrationTest {

    @Autowired
    WorkItemRepository items;

    @Autowired
    CompletionReceiptRepository receipts;

    @Autowired
    BatchRunner runner;

    @Autowired
    ItemProcessor processor;

    @Autowired
    ScheduledTrigger trigger;

    @MockitoBean
    FailureGate failureGate;

    @BeforeEach
    void cleanBeforeEachTest() {
        // No outer test-managed @Transactional:
        // clean up via real repository transactions.
        receipts.deleteAll();
        items.deleteAll();
        reset(failureGate);
    }

    @Test
    void runningSameBatchAgainDoesNotDuplicateReceipts() {
        items.save(new WorkItem("a", "payload-a"));

        runner.runOnce();
        runner.runOnce();

        assertThat(items.findById("a").orElseThrow()
                .getStatus()).isEqualTo(WorkStatus.DONE);
        assertThat(receipts.findById("a")).isPresent();
        assertThat(receipts.count()).isEqualTo(1);

        verify(failureGate, times(1))
                .afterDatabaseWrites("a");
    }

    @Test
    void directDuplicateInvocationSkipsAlreadyDoneItem() {
        items.save(new WorkItem("same", "payload"));

        processor.process("same");
        processor.process("same");

        assertThat(receipts.count()).isEqualTo(1);
        assertThat(receipts.findById("same")
                .orElseThrow().getPayload())
                .isEqualTo("payload");

        verify(failureGate, times(1))
                .afterDatabaseWrites("same");
    }

    @Test
    void exceptionAfterFlushRollsBackBothWritesThenRetrySucceeds() {
        items.save(new WorkItem("retry", "payload-r"));

        doThrow(new IllegalStateException(
                "injected after database flush"))
                .doNothing()
                .when(failureGate)
                .afterDatabaseWrites("retry");

        assertThatThrownBy(runner::runOnce)
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("injected");

        // Read AFTER transaction exception/rollback.
        assertThat(items.findById("retry").orElseThrow()
                .getStatus()).isEqualTo(WorkStatus.PENDING);
        assertThat(receipts.findById("retry")).isEmpty();

        runner.runOnce();

        assertThat(items.findById("retry").orElseThrow()
                .getStatus()).isEqualTo(WorkStatus.DONE);
        assertThat(receipts.findById("retry")).isPresent();
        assertThat(receipts.count()).isEqualTo(1);

        verify(failureGate, times(2))
                .afterDatabaseWrites("retry");
    }

    @Test
    void failureInMiddleKeepsEarlierCommitAndResumesRemaining() {
        items.saveAll(List.of(
                new WorkItem("a", "payload-a"),
                new WorkItem("b", "payload-b"),
                new WorkItem("c", "payload-c")));

        doThrow(new IllegalStateException(
                "injected failure on b"))
                .doNothing()
                .when(failureGate)
                .afterDatabaseWrites("b");

        assertThatThrownBy(runner::runOnce)
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("on b");

        // a completed in its own transaction.
        assertThat(items.findById("a").orElseThrow()
                .getStatus()).isEqualTo(WorkStatus.DONE);
        assertThat(receipts.findById("a")).isPresent();

        // b rolled back its whole transaction.
        assertThat(items.findById("b").orElseThrow()
                .getStatus()).isEqualTo(WorkStatus.PENDING);
        assertThat(receipts.findById("b")).isEmpty();

        // c was never called because runner stopped at b.
        assertThat(items.findById("c").orElseThrow()
                .getStatus()).isEqualTo(WorkStatus.PENDING);
        assertThat(receipts.findById("c")).isEmpty();
        assertThat(receipts.count()).isEqualTo(1);

        // Rerun reads fresh PENDING: only b and c.
        runner.runOnce();

        assertThat(receipts.count()).isEqualTo(3);
        assertThat(items.findById("a").orElseThrow()
                .getStatus()).isEqualTo(WorkStatus.DONE);
        assertThat(items.findById("b").orElseThrow()
                .getStatus()).isEqualTo(WorkStatus.DONE);
        assertThat(items.findById("c").orElseThrow()
                .getStatus()).isEqualTo(WorkStatus.DONE);

        verify(failureGate, times(1))
                .afterDatabaseWrites("a");
        verify(failureGate, times(2))
                .afterDatabaseWrites("b");
        verify(failureGate, times(1))
                .afterDatabaseWrites("c");
    }

    @Test
    void rerunOnlyProcessesNewlyArrivedPendingItems() {
        items.save(new WorkItem("old", "payload-old"));
        runner.runOnce();

        items.save(new WorkItem("new", "payload-new"));
        runner.runOnce();

        assertThat(receipts.count()).isEqualTo(2);
        assertThat(items.findById("old").orElseThrow()
                .getStatus()).isEqualTo(WorkStatus.DONE);
        assertThat(items.findById("new").orElseThrow()
                .getStatus()).isEqualTo(WorkStatus.DONE);

        verify(failureGate, times(1))
                .afterDatabaseWrites("old");
        verify(failureGate, times(1))
                .afterDatabaseWrites("new");
    }

    @Test
    void manualTriggerExecutesWithoutWaitingForRealSchedule() {
        items.save(new WorkItem("timer", "payload-t"));

        trigger.tick();

        assertThat(receipts.findById("timer")).isPresent();
        assertThat(items.findById("timer").orElseThrow()
                .getStatus()).isEqualTo(WorkStatus.DONE);

        verify(failureGate, times(1))
                .afterDatabaseWrites("timer");
    }

    @Test
    void twoConcurrentAttemptsForOneItemYieldOneReceipt()
            throws Exception {
        items.save(new WorkItem("parallel", "payload-p"));

        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);

        Callable<Void> action = () -> {
            ready.countDown();
            if (!start.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "start gate timed out");
            }
            // @Transactional applies through the Spring proxy.
            processor.process("parallel");
            return null;
        };

        ExecutorService pool = Executors.newFixedThreadPool(2);
        Future<Void> first = pool.submit(action);
        Future<Void> second = pool.submit(action);

        try {
            assertThat(ready.await(5, TimeUnit.SECONDS))
                    .isTrue();
            start.countDown();

            first.get(20, TimeUnit.SECONDS);
            second.get(20, TimeUnit.SECONDS);
        }
        finally {
            start.countDown();
            pool.shutdownNow();
        }

        assertThat(items.findById("parallel").orElseThrow()
                .getStatus()).isEqualTo(WorkStatus.DONE);
        assertThat(receipts.count()).isEqualTo(1);
        assertThat(receipts.findById("parallel"))
                .isPresent();

        // Only the worker that wins the lock proceeds through the failpoint.
        verify(failureGate, times(1))
                .afterDatabaseWrites("parallel");
    }

    @Test
    void unknownWorkItemFailsLoudlyAndCreatesNoReceipt() {
        assertThatThrownBy(() ->
                processor.process("does-not-exist"))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("Unknown work item");

        assertThat(receipts.count()).isZero();
    }
}
~~~

### 7.19. Why is each test valuable?

**Test 1 — rerun after DONE:** the same batch runs twice. The second run creates no new receipt, and the in-transaction hook executes only once. Database count assertions matter more than method `verify`, as they prove the side effect was persisted properly.

**Test 2 — direct duplicate call:** simulates two sequential deliveries for the same work ID. `process` re-checks status after acquiring the row lock, so the second call returns early with no new receipt. The test does not rely solely on the runner filtering `PENDING`.

**Test 3 — exception after flush:** the test injects a `RuntimeException` **after INSERT/UPDATE flushed**. The exception crosses the transactional interceptor, rolling back both the receipt and the status update. On retry, it succeeds with exactly one receipt. This proves flush does not equal commit.

**Test 4 — mid-batch failure:** A committed independently; B rolled back; C was not invoked. Rerunning skips A and processes B and C. This is critical behavior when a job is interrupted after partial progress.

**Test 5 — incremental rerun:** after the first run, a new item arrives; the next run processes only the new item without redoing the old one.

**Test 6 — manual scheduler trigger:** tests the business job through public adapter `tick()` without waiting 60 seconds. Profile-based schedule activation can be verified with a separate test configuration if required.

**Test 7 — concurrent attempts:** two worker threads simultaneously call the `ItemProcessor` public bean. Database pessimistic row locking serializes check-and-write; after both requests finish, there is only one receipt and one processing hook execution. This does not test multi-node failover, yet catches basic concurrency races much better than sequential duplicate tests.

**Test 8 — unknown item:** must not silently create a receipt or swallow errors. A domain may define "missing" as skip instead of exception; if so, update both the production contract and assertions intentionally.

### 7.20. Factors making tests deterministic

- The job never auto-runs under the `test` profile.
- No `Thread.sleep` or waiting on real cron ticks.
- Failure injection targets specific item IDs and invocation counts.
- Concurrency uses `CountDownLatch` and `Future.get(timeout)`, never guessing thread scheduling with sleep.
- Data is cleaned in `@BeforeEach` via real repository transactions.
- No `@Transactional` on JUnit test methods, so service transactions actually commit/roll back and readbacks see post-completion state.
- Every fixture uses distinct test IDs with no test-order dependence.
- SQLite/H2 do not substitute for production database semantics; real projects should verify PostgreSQL locking with Testcontainers.
- Mocks replace only `FailureGate`. Repositories, `ItemProcessor` transactions, locks, and the database are all real.

### 7.21. Run commands

In the `job-rerun-recovery-lab` directory, with JDK 17+ and Maven:

~~~bash
mvn -q clean test

mvn -q -Dtest=JobRecoveryIntegrationTest test
~~~

Expected (given matching build and runtime):
- 8 JUnit methods PASS.
- Receipt counts match each test; failed transactions leave no rows.
- Concurrency test finishes within its deadline.
- Maven exit code `0`, reports in `target/surefire-reports`.

**There is no fixed Hibernate/Spring/Maven stdout** across all environments. Inspect actual Surefire reports and stack traces on failure. The lab code was reviewed for APIs/structure, **not executed with Maven/JUnit during authoring**.

### 7.22. Running the real scheduler outside tests

Enable the profile:

~~~bash
mvn spring-boot:run -Dspring-boot.run.profiles=scheduler
~~~

The application loads `SchedulerConfiguration` and fires `ScheduledTrigger.tick()` per `lab.job.delay-ms`. Since the lab has no API seeding work items, booting the app alone finds no pending work; logs only show startup and scheduled scans. Use JUnit to seed items and observe processing.

**Never enable `scheduler` while running integration tests**: the timer could grab items while tests are still setting up fixtures and race against assertions. If production runs multiple replicas with this profile, job-level idempotency/locking must guard concurrency properly.

## 8. Why can Spring tests give false PASSes?

### 8.1. `@SpringBootTest` does not auto-rollback

`@SpringBootTest` loads the application context; **when the test method itself has no `@Transactional`**, service transactions open and commit normally when called through proxies. This lab relies on that behavior.

If you annotate the test class with `@Transactional`, `ItemProcessor.process` (with default `REQUIRED` propagation) joins the long test-managed transaction instead of committing per item. A test failing on B can roll back A along with the test, or readbacks can observe uncommitted state inside the same transaction. That **does not** test real production boundaries.

### 8.2. `@DataJpaTest` rolls back by default

`@DataJpaTest` normally wraps each test in a test-managed transaction and rolls it back at the end. It is great for testing entity/repository mappings, yet does not prove resuming after **real commits**. For per-item transaction tests, pick a full Spring context without a test transaction, or use `TestTransaction`/`@Commit` carefully and clean up committed rows.

### 8.3. Mock verification does not replace state assertions

~~~java
verify(jobHandler).handle("x");
~~~

This assertion only confirms the mock method was called; it does not tell you:
- Whether the DB row committed or rolled back.
- Whether a single transaction wrapped both writes.
- Whether another concurrent worker created a duplicate.
- Whether an external gateway outcome truly completed.

Therefore, use mocks to **inject faults or observe calls**, keep the DB real, and query state after the transaction finishes.

### 8.4. Catching exceptions inside `@Transactional` can cause unintended commits

~~~java
@Transactional
public void process(String id) {
    try {
        saveReceipt(id);
        callSomethingThatFails();
    }
    catch (Exception ex) {
        log.warn("failed", ex);
    }
}
~~~

If an exception is caught and the method returns normally, Spring may commit the transaction even though the workflow failed (unless the transaction was marked rollback-only or a resource failure forced rollback). To test accurately, assert DB state after the call; never assume "logged an error = rolled back".

If failure attempts must be persisted, record attempt state in a separate transaction **after** rollback or use an explicit failure-recording policy instead of catching and accidentally committing partial business writes.

### 8.5. Checked exceptions and rollback rules

By default, Spring `@Transactional` rolls back on unchecked exceptions and `Error`s; checked exceptions may not trigger rollback unless configured via `rollbackFor` or a global rollback policy. When a job can throw checked exceptions, test explicitly:
- Throw the checked exception across the boundary.
- Inspect DB state afterward.
- Decide on `@Transactional(rollbackFor = Exception.class)` or an explicit policy.

The lab intentionally injects `IllegalStateException` (unchecked).

## 9. Testing duplicates across multiple instances and threads

### 9.1. Sequential duplicates do not catch races

A test calling `process("x")` twice sequentially can PASS even with unlocked check-then-insert code. Concurrent calls expose the race.

A concurrency test should:
1. Seed a durable row beforehand.
2. Create two tasks.
3. Use a gate/latch so both start together.
4. Call the **Spring proxy** from each thread.
5. Await futures with finite timeouts.
6. Query the database after both transactions end.
7. Assert one receipt and `DONE`.
8. Clean up even if the test fails.

### 9.2. Database lock semantics differ

`PESSIMISTIC_WRITE` in H2, PostgreSQL, MySQL, and Oracle can vary in waiting, deadlocks, isolation, and `SKIP LOCKED` support. H2 tests verify basic application wiring; production-grade concurrency needs Testcontainers with the exact target DB/version/schema/migrations.

Additional cases to consider:
- Two separate JVM processes processing the same ID.
- Lock wait timeouts.
- Retryable vs non-retryable deadlocks.
- Worker crashing while holding a lock before the DB releases it.
- Transaction cancellation and connection pool recovery.
- `READ COMMITTED` vs `REPEATABLE READ`.
- Unique constraint conflicts if any code path forgets to lock.

### 9.3. Distributed locks do not automatically produce exactly-once

ShedLock, Redis leases, ZooKeeper, or DB advisory locks prevent overlapping runs, yet:
- A lock can expire mid-way through a long task.
- An old worker can resume after a new worker acquired the lock.
- Network partitions can create two logical holders.
- You need **fencing tokens** or DB compare-and-set/unique constraints for critical invariants.
- Locks only address overlap, not recovery after external side effects.

### 9.4. A "global lock" can throttle throughput

Locking an entire job prevents replicas from overlapping—easy to understand, yet often unable to meet throughput demands. Per-item DB locks/claims allow different IDs to run in parallel. Tests should verify both **no duplicates for the same ID** and **independence across distinct IDs**, while monitoring lock contention.

### 9.5. Do not rely on JVM `synchronized`

~~~java
public synchronized void process(String id) {
    // ...
}
~~~

`synchronized` only locks within that single JVM instance/object. Two Spring instances on two pods have separate locks. Database row-level locks, unique constraints, message partition ordering, or durable claims are needed for cross-instance correctness.

## 10. Retries, backoff, and error classification

### 10.1. Do not retry every exception

| Error | Retry? | Handling approach |
| --- | --- | --- |
| Network timeout to provider | Usually yes, if idempotent | Backoff + idempotency key |
| DB deadlock/lock timeout | Possible | Rerun in a new transaction, bounded attempts |
| Broker temporarily unavailable | Usually yes | Outbox pending/retry |
| Permanent input validation error | Usually no | `FAILED`/DLQ, alert |
| Duplicate already `DONE` | No need to redo | Return idempotent result |
| Payload conflict for same key | Do not treat as duplicate | Reject/alert |
| Missing work item | Per business contract | Fail/skip explicitly |
| Invalid token/credentials | Do not retry infinitely | Fix configuration |
| Schema mismatch | Do not retry infinitely | Quarantine poison event |

### 10.2. Meaningful backoff

Never spin-retry inside an open transaction holding locks:

~~~java
for (int i = 0; i < 1000; i++) {
    try {
        gateway.call();
    }
    catch (Exception ex) {
        // dangerous infinite or tight loop
    }
}
~~~

You need:
- Attempt count.
- Bounded backoff, typically exponential with jitter.
- Max attempts / retry deadline.
- Persisted `nextAttemptAt` timestamp.
- Redacted failure reason and stack trace.
- Dead-letter/quarantine for poison items.
- Metrics for waiting/running/retrying/failed.

### 10.3. `@Retryable` has its own AOP boundary

Spring Retry provides `@Retryable`, yet never assume it works just because the annotation is present. You need matching dependencies/configuration (e.g., `spring-retry` and AOP, `@EnableRetry` per setup), calls crossing proxies, and clear retry/transaction boundaries.

A retry wrapping an entire batch can repeat the whole batch rather than just the failing item. If business rules want per-item retry, place the retry boundary at item level; if retrying after external side effects, use idempotency keys.

### 10.4. Deterministic time

Comparing `nextAttemptAt` against `Instant.now()` couples tests to wall-clock time. Inject `Clock`:

~~~java
Clock clock = Clock.fixed(
        Instant.parse("2026-01-15T10:00:00Z"),
        ZoneOffset.UTC);

Instant now = Instant.now(clock);
Instant next = now.plusSeconds(60);
~~~

Illustrative snippet with `java.time` imports, not in the lab project. Tests check:
- At T0: `RETRY_WAIT` not yet eligible.
- At T0+59s: still not eligible.
- At T0+60s: eligible.
- Exceeding `maxAttempts`: `FAILED`.
- No `Thread.sleep(60000)` waiting.

### 10.5. Retries must run in a fresh transaction when needed

After a transaction rolls back, do not keep using a JPA `EntityManager` marked rollback-only for further business writes in the same transaction. Retries should open a fresh transaction, reload entity state, and re-evaluate eligibility and locks.

## 11. At-least-once message processing and scheduled jobs share common ground

### 11.1. Message redelivery

A Kafka consumer can commit DB writes and crash before committing offsets; a RabbitMQ consumer can finish DB writes and crash before `basicAck`. The broker will likely redeliver the same logical event. Consumers should check idempotency records/unique keys inside the business transaction.

~~~text
Kafka: receive event-42
  -> DB business write COMMIT
  -> crash before offset commit
  -> restart re-reads event-42
  -> DB dedupe -> skip side effect
  -> commit offset
~~~

This is **at-least-once plus an idempotent handler**, not exactly-once spanning Kafka and the database.

### 11.2. Acking before business commit is also dangerous

If a consumer commits offsets/acks **before** the database business transaction commits, a crash between the two steps loses the operation. Test failure matrices must verify the sequence:
- Receive.
- Validate.
- Business DB transaction.
- Ack/offset commit.
- Retry/DLT on error.

No single trivial ordering guarantees atomicity across two independent systems.

### 11.3. EventId vs businessId

One business operation can emit multiple event versions:
- `eventId` identifies a specific message for delivery deduplication.
- `businessOperationId` identifies the business effect that must remain unique.
- `aggregateId` identifies the entity.
- `idempotencyKey` may originate from the caller/API.
- `payloadHash` detects identical keys with altered parameters.

Never generate a new `UUID.randomUUID()` on every retry as the business idempotency key, because doing so turns each retry into a brand-new operation.

### 11.4. Scheduled sweeps are also a redelivery mechanism

A scheduled job polling `PENDING` rows is a form of "at-least-once" delivery for remaining work. Backed by durable statuses, locks, and dedupe, it resumes cleanly across process restarts. If pending items live only in RAM, crashes lose them.

## 12. Mid-batch failures: pick an explicit policy

### 12.1. Fail-fast

The runner stops at item B. Pros: does not hide system-wide outages and is easy to debug. Cons: C/D/E must wait for the next run. The lab intentionally uses fail-fast.

### 12.2. Continue-on-error

If items are independent, catch exceptions **outside** `ItemProcessor.process(...)`:

~~~java
for (String id : pendingIds) {
    try {
        processor.process(id);
    }
    catch (RuntimeException ex) {
        // Record failure/attempt in a separate transaction,
        // continue to the next item per policy.
    }
}
~~~

This is a conceptual snippet, not a standalone runnable class. Never catch inside the transactional processor and commit partial writes. When continuing, emit metrics/alerts and record retry state; never swallow errors silently.

### 12.3. Poison item

An item that always throws a validation exception can stall a fail-fast job at the same ID forever. Solutions:
- Max attempts.
- Distinguish permanent vs transient errors.
- Mark `FAILED`/quarantine after recording the reason.
- Allow other items to proceed.
- Provide safe manual redrive after fixing data.
- Test that poison items never loop infinitely.

### 12.4. Batch checkpoints with business meaning

"Finished item A" checkpoints should live in durable DB state, not in-memory counters. If item ordering shifts, storing "processed up to index 42" can skip or repeat items. Use business IDs/statuses/cursors, or a watermark backed by a tested ordering guarantee.

### 12.5. Crash recovery must not rely on JVM memory

Do not rely solely on:

~~~java
private int lastProcessedIndex;
~~~

If the app restarts, the field resets; if the list reorders, the index loses meaning. Use DB statuses/offsets/leases for recovery. Real restart tests using containers/processes prove data persists across JVM boundaries.

## 13. The big exception: external side effects and transactional outbox

### 13.1. Crash windows `@Transactional` alone cannot solve

~~~text
DB COMMIT success
       |
       | JVM crash
       v
AFTER_COMMIT event/email publish never ran
~~~

An `@TransactionalEventListener(AFTER_COMMIT)` callback is not guaranteed to run if the process crashes after database commit and before the callback fires. Conversely:

~~~text
External provider confirms success
       |
       | JVM crash
       v
DB never recorded sent/acknowledged state
       |
       v
Rerun -> sends the same operation again
~~~

When email/payment/event delivery must not be lost, a `CompletionReceipt` in the DB alone does not prove the external system received it.

### 13.2. Transactional outbox

In **the same transaction T1**, persist:
1. Business state.
2. An outbox row with a stable event ID/payload and `PENDING` status.

After commit:
- A relay reads pending outbox rows.
- Sends to the broker/provider using an **idempotency key**.
- Once confirmed, updates outbox delivery state.
- If a crash occurs before publishing, the pending row stays in the DB and gets retried later.
- If a crash occurs after publishing but before marking `SENT`, it may republish; the consumer/provider must deduplicate.

~~~text
T1 (atomic DB transaction):
  UPDATE work_item -> DONE
  INSERT completion_receipt(work_id)
  INSERT outbox_event(event_id, payload, PENDING)
  COMMIT
        |
        v
T2 relay reads committed PENDING event
        |
        +-- publish(event_id)
        +-- provider ACK
        +-- mark SENT in a separate transaction
        |
        +-- crash? retry PENDING
                  |
                  +-- same event_id -> idempotent receiver
~~~

Never insert the outbox row **only inside an `AFTER_COMMIT` listener** if it must exist atomically with business state: that leaves the crash gap wide open.

### 13.3. Outbox adaptation pseudocode

~~~java
@Transactional
public void processOne(String id) {
    WorkItem item = items.findLockedById(id)
            .orElseThrow();

    if (item.getStatus() == WorkStatus.DONE) {
        return;
    }

    receipts.save(new CompletionReceipt(
            item.getId(), item.getPayload()));

    outbox.save(new OutboxEvent(
            "processed:" + item.getId(),
            item.getId(),
            item.getPayload(),
            "PENDING"));

    item.markDone();
}
~~~

This is an **architectural snippet**; the runnable project does not define `OutboxEvent`/repository. The key invariant is saving business writes + outbox writes **together in T1** with a unique event ID.

### 13.4. Tests must cover both crash windows

| Fault | Expected DB state | Next run |
| --- | --- | --- |
| Failure before T1 commit | `WorkItem` `PENDING`, no receipt/outbox | Reprocess business logic |
| T1 commits, relay not yet published | `DONE` + receipt + outbox `PENDING` | Relay retries without reprocessing business logic |
| Publish succeeds, relay crashes before marking `SENT` | Outbox stays `PENDING` | Republishes same `eventId`, consumer deduplicates |
| Consumer DB commits, crashes before ack | Consumer dedupe record exists | Redelivery skips effect and ACKs |
| Provider times out yet processed | Outcome unknown | Query/reconcile using stable idempotency key |
| Payload conflict on same key | Never silently overwrite | Reject/alert/reconcile |

### 13.5. Payments and irreversible side effects

Payment capture is a high-risk example: charging twice cannot be "rolled back" by a DB transaction. Tests should use a payment sandbox/fake provider enforcing an **idempotency-key contract**:
- Repeating same key + same parameters → single charge, returns the same result.
- Repeating same key + different parameters → conflict, creates no new charge.
- Timeout after provider accepted → reconcile via provider operation ID.
- Bounded retry/backoff with audit trails.
- Never call live payment providers from CI.

Never claim "exactly-once payment" based solely on a database row lock.

### 13.6. Reconciliation is part of recovery

When outbox/relay/provider states diverge, scheduled reconciliation scans operations stuck in "unknown" past a threshold, cross-checks the external provider or broker, and brings state to completion or flags manual intervention. Tests should simulate:
- Provider succeeded while local status remained pending.
- Provider failed while local state was wrongly marked sent.
- Exhausted retry budgets routed to dead-letter/manual review.
- Duplicate reconciliation runs producing no extra side effects.

## 14. Leases, PROCESSING status, and workers dying mid-long job

### 14.1. Why is a long row lock insufficient?

In the lab, transactions are tiny and DB-only, so pessimistic locking fits well. For 30-minute tasks or slow external API calls, holding DB transactions/connections/locks for the whole duration causes contention and pool exhaustion.

Production can use a state machine:

~~~text
PENDING -> PROCESSING(owner, leaseUntil, attempt)
   |           |
   |           +-- success -> DONE
   |           +-- failure -> RETRY_WAIT
   |           +-- lease expired -> PENDING (recover)
   |
   +-- invalid -> FAILED
~~~

### 14.2. Atomic claim

A worker claims an item with a conditional SQL update (dialect-dependent syntax):

~~~sql
UPDATE work_items
   SET status = 'PROCESSING',
       claimed_by = :worker_id,
       lease_until = :lease_until,
       attempt_count = attempt_count + 1
 WHERE work_id = :id
   AND status = 'PENDING'
~~~

**This is illustrative SQL**, not part of the runnable lab's H2 schema, and cannot be copied directly since the lab table lacks these columns. The core pattern is checking `rowsAffected == 1` to know only one worker won the claim. Databases may also support `SELECT ... FOR UPDATE SKIP LOCKED`, advisory locks, or queue-specific claim APIs.

### 14.3. Lease expiry and fencing

Worker A claims an item then hits a stop-the-world GC pause; the lease expires and Worker B reclaims it. Worker A wakes up and attempts external writes. Without checking ownership/fencing tokens when committing side effects, two workers can write duplicates. You need:
- Lease owner/epoch.
- Monotonically increasing fencing token.
- Compare-and-set when marking `DONE`.
- Downstream systems accepting fencing tokens/idempotency keys where needed.
- Tests proving a late worker cannot overwrite a newer worker's result.

### 14.4. Testing with a fake Clock

Use an injectable `Clock` to jump from `T0` to `T0+leaseExpiry` without sleeping. Test:
- Before lease expiry: cannot reclaim.
- Right at lease expiry: reclaimed per contract.
- Worker A finishes late: fencing rejects it.
- Worker B succeeds: only one business result.
- Lease renewal/heartbeat failure: explicit policy.
- Max attempts/poison items handled.

### 14.5. Do not use only in-memory flags

`AtomicBoolean running` or `ReentrantLock` prevents overlap within one JVM, yet offers zero protection across Kubernetes replicas, crash/restarts, or distinct scheduler nodes.

## 15. Testing asynchronous completion properly

### 15.1. Do not assert immediately after `@Async`

~~~java
service.processAsync("x");
assertThat(receiptRepository.findById("x"))
        .isPresent();
~~~

If `processAsync` returns immediately and the worker runs later, the assertion races. Tests should return a `CompletableFuture` with a completion signal or use a thread-safe probe/await.

### 15.2. CompletableFuture

~~~java
CompletableFuture<Void> task =
        asyncProcessor.processAsync("x");

task.get(5, TimeUnit.SECONDS);

assertThat(receipts.findById("x")).isPresent();
~~~

This is an extension snippet assuming `processAsync` returns `CompletableFuture<Void>`, not part of the runnable lab. `get` with a timeout awaits completion and propagates failures into the test. If an async method returns `void`, add an `AsyncUncaughtExceptionHandler`/probe so failures aren't swallowed.

### 15.3. CountDownLatch

~~~java
CountDownLatch completed = new CountDownLatch(1);

// Fake gateway or callback:
completed.countDown();

// JUnit thread:
assertThat(completed.await(
        5, TimeUnit.SECONDS)).isTrue();
~~~

Illustrative snippet, does not compile standalone outside a test setup. Only count down **after the observable side effect finishes**, not as soon as the executor receives the task.

### 15.4. Bounded polling

For eventual consistency, Awaitility or bounded polling beats `Thread.sleep(1000)` followed by a single assert. However, polling must never hide business races: if requirements demand atomic exact state as soon as a method returns, assert immediately instead of waiting for the system to settle later.

### 15.5. Negative assertions with async

"Saw no message in 20ms" **does not prove no message will ever arrive**. When proving no side effect occurred:
- Disable/control the executor or use a fake producer to observe scheduling attempts.
- Check business state/unique constraints and completion signals.
- Pick a bounded observation window suited to the test architecture.
- For Kafka/Rabbit, inspect offsets/acks/DLQ per protocol rather than racing on local variables.

## 16. Common mistakes and diagnostics

| Symptom | Cause | Fix |
| --- | --- | --- |
| Rerun creates a second receipt | Missing stable idempotency key / unique constraint | PK/unique + `DONE` status |
| Two workers process the same ID | Non-atomic check-then-act | Row lock / atomic claim + concurrent test |
| Sequential test passes, parallel fails | Only tested calling twice in sequence | Latch + thread/process concurrency |
| Test fails after flush yet row still visible | Querying in same transaction / first-level cache | Read after rollback, clear context if needed |
| Item A lost when B fails | Runner has an outer transaction | Per-item transaction via bean proxy |
| Item B marked `DONE` despite throwing | Exception caught inside `@Transactional` | Propagate / mark rollback-only, test state |
| `@Transactional` not applied | Self-invocation / private method | Call through Spring bean proxy |
| Checked exception still commits | Default rollback rules | `rollbackFor` / explicit policy |
| `@SpringBootTest` doesn't reflect real commits | Test-level `@Transactional` attached | Tests without outer transaction |
| `@DataJpaTest` always rolls back | Default transactional slice | Separate real commit-boundary test |
| Duplicate external payment on retry | Non-DB side effect not atomic | Provider idempotency + reconcile/outbox |
| Job drops event after DB commit | In-memory after-commit publish crash gap | Transactional outbox |
| Outbox sends twice | Crash after publish before marking `SENT` | Stable `eventId` + consumer idempotency |
| Poison item blocks batch forever | Fail-fast without terminal state | Max attempts / `FAILED` / DLQ |
| `@Scheduled` runs multiple times across cluster | Each replica runs a scheduler | Distributed lock/claim + DB constraints |
| Job runs during test setup | `@EnableScheduling` active in tests | Scheduler profile off, manual trigger |
| `@Async` assertion flaky | Did not await completion | Bounded Future/latch/Awaitility |
| Retry state doesn't become due on time | Wall clock / timezone | Inject `Clock`, fake-time tests |
| Passes on H2, fails on PostgreSQL locks | Different lock/isolation dialects | Testcontainers PostgreSQL |
| Unknown work silently skipped | Swallowed exception | Define missing-item contract |
| Duplicate key with changed payload | Checked ID only | Payload hash/version conflict policy |
| `@DirtiesContext` assumed to clean DB | Context caching differs from DB state | Explicit cleanup / test DB isolation |
| CI green yet side effects still pending | Asserted too early or only verified mock | Query committed outcome + completion signal |

### 16.1. Debugging transaction boundaries

Check:
- Does the test method have `@Transactional`?
- Does the runner have an outer transaction?
- Does `ItemProcessor.process` go through the Spring proxy?
- Which thread is it running on?
- Did JPA flush occur?
- Is the exception unchecked or checked?
- Did the real DB transaction commit or roll back?
- Are side effects inside the same DB transaction?

Never adjust expected outcomes "to make it green" before knowing which transaction ran.

### 16.2. Debugging concurrency

Log:
- Work ID / idempotency key.
- Worker/instance ID and transaction correlation.
- Lock acquisition/timeout.
- Status before and after locking.
- Unique constraint outcomes.
- Attempt count / retry reason.
- Normalized timestamps, without leaking PII/secrets.

Never rely solely on producer/worker logs as proof of correct business outcomes.

### 16.3. Debugging retries

Distinguish transient failures (timeouts, deadlocks) from permanent ones (invalid payload, missing schema). Inspect attempt counts, backoff, `nextAttemptAt`, terminal statuses, and DLQ/outbox state. Infinite retries are not a controlled recovery strategy.

## 17. Practice exercises

1. Run `JobRecoveryIntegrationTest`. Explain why there are eight tests instead of just one happy path.
2. Remove the `DONE` check in `ItemProcessor` and observe duplicate calls causing unique-key errors or duplicate side effects; restore the check.
3. Remove `@Lock(PESSIMISTIC_WRITE)` and run the concurrent test repeatedly; explain why races or constraint violations occur.
4. Remove the primary key uniqueness on `CompletionReceipt` in a variant branch and evaluate duplicate risks.
5. Inject an error before `saveAndFlush`; verify the row stays `PENDING` with no receipt.
6. Inject a `RuntimeException` after `saveAndFlush`; verify rollback occurs even though SQL ran.
7. In a 3-item batch, inject a failure on the second item; verify A is `DONE`, B/C are pending, then retry.
8. Add `@Transactional` to `BatchRunner.runOnce()`; explain why transaction semantics change.
9. Turn `ItemProcessor.process` into a self-invoked private helper; observe why the proxy does not apply `@Transactional`.
10. Add a checked exception, observe default rollback policy, and apply `rollbackFor` when appropriate.
11. Enable continue-on-error, record failure attempts in a separate transaction, and process C even when B fails.
12. Add `RETRY_WAIT`/`FAILED`, max attempt count, and a deterministic fake `Clock`.
13. Build a PostgreSQL Testcontainers test for `PESSIMISTIC_WRITE` with two clients/transactions and a lock timeout.
14. Add `payloadHash`; same ID + different payload must reject rather than silently skip.
15. Insert an outbox row in the same `WorkItem`/`Receipt` transaction; verify rollback leaves zero outbox rows.
16. Simulate a relay crash after publish before marking `SENT`; use the same `eventId` and consumer deduplication.
17. Write a provider sandbox test for "timed out yet accepted" and reconcile via operation ID.
18. Add an `@Async` worker using bounded futures/latches instead of `Thread.sleep`.
19. Switch the scheduler from `fixedDelay` to `cron` and test timezone/DST with fake time/`CronExpression`.
20. Simulate 2 replicas firing the scheduler simultaneously; verify per-item claims and unique results.
21. Implement lease/`workerId`/fencing tokens and test that a late worker cannot overwrite a newer worker.
22. Cap batches at 100 items using pagination/claims instead of loading all pending rows.
23. Add metrics: successful items, attempted, duplicates skipped, rolled back, retried, terminal failed.
24. Design a real process-crash test using containers: kill after DB commit, restart, assert resume/outbox.
25. Review an existing test using outer `@Transactional` that falsely claims "committed"; fix the setup to test real service transactions.

## 18. Checklist before merging

- [ ] Are job/business operation IDs stable across retries and restarts?
- [ ] Is there an explicit policy for duplicate IDs carrying different payloads?
- [ ] Is it clear whether idempotency covers DB-only or external effects too?
- [ ] Is there a rerun test after `DONE`?
- [ ] Is there a retry-after-rollback test?
- [ ] Is failure after flush yet before commit tested?
- [ ] Is mid-batch failure tested, verifying earlier commits remain intact?
- [ ] Are concurrent same-ID attempts tested?
- [ ] Are locks/unique constraints/claims suited to the production DB?
- [ ] Does cluster correctness avoid relying on in-JVM `synchronized`?
- [ ] Do the runner and per-item processor have clear transaction boundaries?
- [ ] Does `@Transactional` pass through a Spring proxy?
- [ ] Are exceptions not caught inside transactions in ways that commit partial writes?
- [ ] Do checked exceptions have explicit rollback policies?
- [ ] Do tests avoid outer transactions that distort commit semantics?
- [ ] Are schedulers disabled or deterministic in unit/integration tests?
- [ ] Can manual triggers be invoked without sleeping?
- [ ] Do async tests await completion with deadlines?
- [ ] Are retries/backoff/max attempts explicit?
- [ ] Do poison items have a terminal/quarantine path?
- [ ] Is attempt/lease state persisted for crash recovery?
- [ ] Does DB cleanup avoid interfering with other tests?
- [ ] Do parallel tests have per-test namespace/database isolation?
- [ ] Do external calls use idempotency keys, transactional outboxes, and reconciliation?
- [ ] Are before/after publish/ack crash gaps tested?
- [ ] Do we avoid claiming end-to-end exactly-once across DB + broker/payment from DB locks alone?
- [ ] Are production emails/payments/messages blocked from firing in CI?
- [ ] Do metrics/logs include trace IDs without exposing secrets/PII?
- [ ] Are production-like DB tests present for locking/isolation when critical?
- [ ] Do Maven/JUnit reports confirm all executed tests and failure scenarios?

**Conclusion:** Testing an asynchronous or scheduled job must go far beyond "call once and see a result". Re-run after success, inject faults at the **exact transaction boundary**, check mid-batch progress, and trigger concurrent calls to expose check-then-act races. For DB-only side effects, per-item transactions + row locks + unique business keys ensure one durable result per ID within the tested scope. For external side effects, add outboxes, retries, idempotent receivers, and reconciliation. A test claiming "retry safe" is only trustworthy when it proves both **post-failure state** and **post-rerun state**, not merely that a method was called.

## 19. Official documentation

- Spring Framework 6.2 — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html
- Spring Framework 6.2 — `@Scheduled` Javadoc (`fixedDelay`, `fixedRate`, `cron`): https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/annotation/Scheduled.html
- Spring Framework 6.2 — `@EnableScheduling` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/annotation/EnableScheduling.html
- Spring Framework 6.2 — Using `@Transactional` and self-invocation: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html
- Spring Framework 6.2 — Transaction rollback rules: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/rolling-back.html
- Spring Data JPA 3.5 — Locking with `@Lock`: https://docs.spring.io/spring-data/jpa/reference/3.5/jpa/locking.html
- Spring Data JPA — Transactionality: https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html
- Spring Boot 3.5 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5 — `DataJpaTest` API: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/orm/jpa/DataJpaTest.html
- Spring Boot 3.5 — Testcontainers: https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html
- Spring Framework 6.2 — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Spring Kafka — Listener Container and Offset Commit: https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html
- Spring AMQP — Consumer Acknowledgements: https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-consumer.html
- PostgreSQL — Explicit Locking: https://www.postgresql.org/docs/current/explicit-locking.html