# Locking Across Multiple Scheduler Instances in Spring Batch

## 1. Context: One Schedule, Multiple Applications Triggering Together

When a Spring Boot application is deployed across multiple instances, each instance typically has its own **ApplicationContext** and scheduler. If all three instances contain a method annotated with **@Scheduled**, all three can trigger the same Spring Batch Job when the scheduled time arrives:

~~~text
                    01:10 UTC daily
                           |
               +-----------+-----------+
               |           |           |
          Instance A   Instance B   Instance C
           @Scheduled   @Scheduled   @Scheduled
               |           |           |
               +-----------+-----------+
                           |
                     launch Job
                           |
                 May run duplicates
~~~

Suppose the Job aggregates the previous day's revenue. If run concurrently, it could write multiple identical report records, send duplicate emails, process the same transactions, or contend on database locks. Whether running three pods in Kubernetes or three standalone servers, **@Scheduled schedules locally within each JVM** and does not automatically elect a single instance to execute.

A **distributed lock** is a mechanism for instances to agree that, for a given period, only one instance has the right to start or perform a defined task. In the context of Spring Batch Core Processing, understand two control layers:

1. **Scheduler lock:** coordinates multiple scheduler instances triggering a scheduled task.
2. **JobRepository and JobInstance:** manages identity, history, status, and restart of a Batch Job.

The two layers complement each other. Neither should be viewed as a complete replacement for the other.

## 2. Distinguishing Scheduler Locks from JobRepository Protection

Spring Batch identifies a **JobInstance** by Job name and its set of **identifying JobParameters**. Normally, two requests to run the same Job name with the same identifying parameters are treated as requests for the same JobInstance. `JobRepository` coordinates creating **JobExecution**s; if the JobInstance is already running, a duplicate launch can be rejected with **JobExecutionAlreadyRunningException**. If the JobInstance is already completed, a rerun request can encounter **JobInstanceAlreadyCompleteException**.

Example:

~~~text
Job: dailySettlementJob

Instance A:
  businessDate = 2026-11-15
  -> dailySettlementJob(businessDate=2026-11-15)

Instance B:
  businessDate = 2026-11-15
  -> same JobInstance, Spring Batch checks status

Instance C:
  businessDate = 2026-11-15
  run.id = 872345
  -> may become a different JobInstance if run.id is identifying
~~~

If each scheduler uses **System.currentTimeMillis()**, a UUID, or **RunIdIncrementer** to generate new identifying parameters on every trigger, three instances can create **three different JobInstances** and concurrently run business logic for the same day. `JobRepository` does not automatically know that all three process the same transaction set.

Conversely, if all three use fixed identifying parameters per day, `JobRepository` provides an important guard; however, redundant instances may still call launch repeatedly, receive exceptions, and generate noisy logs. A scheduler lock lets you decide **which instance gets to perform the scheduled call** right from the start.

| Concern | Shared scheduler lock | Spring Batch JobRepository |
| --- | --- | --- |
| Multiple JVMs hitting cron simultaneously | One JVM acquires the lock; others skip or fail to acquire | Does not coordinate **@Scheduled** method invocations |
| Two launches of the same running JobInstance | Can restrict if both go through the same lock | Controls running state of the JobInstance |
| Two different JobInstances processing the same dataset | Can block if sharing the same lock name and lock is active | Can allow concurrent execution |
| Restarting a failed Job | Does not store checkpoints itself | Manages **JobExecution**, **StepExecution**, **ExecutionContext** |
| Preventing duplicate writes to APIs or external systems | Does not strictly guarantee | Does not replace writer idempotency |
| Instance crashes mid-run | May require waiting for lease expiration | Can persist FAILED/STARTED status for Job-level recovery |

The key takeaway: **locks coordinate execution rights over a time window**, while Spring Batch manages a Job execution and its processing state. Critical systems should also add business-level locks, transactions, and idempotent handling where results are written.

## 3. Requirements for Locking in a Multi-Instance Environment

A distributed scheduler lock must satisfy basic requirements:

- **Shared source of truth:** all instances access the same database lock table, same Redis instance, or same coordinator. In-memory locks, **synchronized**, **ReentrantLock**, or per-JVM **AtomicBoolean** cannot coordinate multiple instances.
- **Atomic lock acquisition:** at any moment, at most one instance holds valid ownership of the lock. You cannot write naive “SELECT to check if locked then INSERT” code unless both operations are bound atomically.
- **Recovery mechanism:** if the lock-holding instance is killed or loses connectivity, the system still has a way for another instance to run after a defined timeout or condition.
- **Consistent lock names:** instances running the same schedule must use the **same lock name**, same namespace, and same backend.
- **Proper lock scope:** the lock must cover the protected action, at least the launch decision; when two Jobs must not be active together, lock ownership must span the **entire Job execution duration**.
- **Business data safety on retries:** locks reduce duplication, but crashes, network drops, or lease expirations can still lead to reprocessing.

Two common mental models:

~~~text
A. Lock per JVM (insufficient)

Instance A -- local lock A -- launch
Instance B -- local lock B -- launch
Instance C -- local lock C -- launch

B. Shared distributed lock

Instance A --+
Instance B --+--> Shared lock store --> single owner only
Instance C --+           |
                            +--> launch
~~~

In Spring Boot, a pragmatic choice is **ShedLock** with JDBC. Other options include Quartz clustering, leader election, and direct database locks; the choice depends on schedule needs, Job duration, and deployment architecture.

## 4. Lease Lock Mechanics: Acquire, Release, and Expiration

Some libraries, including ShedLock, use **time-bounded locks (leases)**. The database records the lock name, acquisition timestamp, and expiration timestamp. A simple flow:

~~~text
01:10:00  Instance A acquires lock "dailySettlement"
01:10:00  Instance B fails to acquire -> skips this turn
01:10:01  Instance C fails to acquire -> skips this turn
01:10:02  A starts running dailySettlementJob
01:15:00  A finishes, releases lock
Next day  An instance can acquire lock for the next period
~~~

If A is killed at 01:12:00, it cannot release the lock normally. Once **lockAtMostFor** elapses, the lock is treated as expired; another instance can claim it on a later trigger.

However, distinguish two cases:

- **Instance actually died:** the lease lets the system self-recover after a wait period.
- **Instance is still running past the lease limit:** another instance can acquire the lock and run the same Job while the first is still active. This is dangerous, especially if the two runs use different JobParameters or have external side effects outside the database.

Therefore, a lease lock is not an absolute guarantee that a business action occurs only once. If job duration is unpredictable or spans many hours, design lease renewal, duration monitoring, and output-layer safeguards.

## 5. Using ShedLock with Spring Boot and JDBC

### 5.1. When It Fits

**ShedLock** fits well when:

- The application already uses **@Scheduled**.
- Multiple instances share a reliable database.
- Instances failing to acquire the lock should **skip the invocation** rather than queue up sequentially.
- You only need simple schedule coordination, without misfire management, complex triggers, or persistent schedules of a dedicated scheduler engine.

The example below targets **Spring Boot 3.x, Spring Batch 5.x, Java 17**. Pick a ShedLock version compatible with your project's actual Spring and Java versions. ShedLock requires two parts: Spring annotation support and a **LockProvider** matching the storage backend.

**Example Gradle dependencies (Groovy DSL):**

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    // Replace VERSION with the ShedLock version compatible with your project.
    implementation 'net.javacrumbs.shedlock:shedlock-spring:VERSION'
    implementation 'net.javacrumbs.shedlock:shedlock-provider-jdbc-template:VERSION'
}
~~~

If the app already includes the Batch/JDBC starters, do not duplicate them. Do not mix mismatched versions of **shedlock-spring** and **shedlock-provider-jdbc-template**.

### 5.2. Creating the Shared Lock Table

Example DDL for a database with compatible **TIMESTAMP** types:

~~~sql
CREATE TABLE shedlock (
    name       VARCHAR(64)  NOT NULL,
    lock_until TIMESTAMP(3) NOT NULL,
    locked_at  TIMESTAMP(3) NOT NULL,
    locked_by  VARCHAR(255) NOT NULL,
    PRIMARY KEY (name)
);
~~~

Table name and timestamp precision can be adjusted per database; if using a custom schema or table name, configure **LockProvider** accordingly. Create the table via **Flyway/Liquibase** or centralized project migrations. Do not have every scheduler instance run a drop-and-recreate lock table script on startup.

Column meanings:

| Column | Meaning |
| --- | --- |
| **name** | Unique identifier of the locked task; all instances protecting the same task must use the same name. |
| **lock_until** | Timestamp after which the lock can be re-acquired if not extended. |
| **locked_at** | Timestamp when lock acquisition started, useful for diagnostics. |
| **locked_by** | Identifier of the lock-holding instance for observability and investigation. |

The database is the **shared coordination point**. If instance A uses database X while B uses database Y, both can acquire a lock with the same name and run duplicates. Connecting to the right backend matters as much as adding annotations.

### 5.3. Enabling Scheduling and ShedLock

~~~java
import javax.sql.DataSource;

import net.javacrumbs.shedlock.core.LockProvider;
import net.javacrumbs.shedlock.provider.jdbctemplate.JdbcTemplateLockProvider;
import net.javacrumbs.shedlock.spring.annotation.EnableSchedulerLock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.EnableScheduling;

@Configuration
@EnableScheduling
@EnableSchedulerLock(defaultLockAtMostFor = "PT2H")
public class BatchSchedulerConfiguration {

    @Bean
    public LockProvider lockProvider(DataSource dataSource) {
        return new JdbcTemplateLockProvider(
                JdbcTemplateLockProvider.Configuration.builder()
                        .withJdbcTemplate(new JdbcTemplate(dataSource))
                        .usingDbTime()
                        .build()
        );
    }
}
~~~

**@EnableScheduling** activates Spring's scheduled method execution; **@EnableSchedulerLock** activates locking for ShedLock-annotated methods. **LockProvider** performs the lock operations against the database.

**usingDbTime()** uses database time to determine lock expiration, reducing the impact of clock skew across scheduler hosts. Across multiple nodes, never assume OS clocks are perfectly synchronized.

The example uses the configured database and JDBC setup; with multiple DataSources, explicitly inject the DataSource **shared by all scheduler instances**. The lock table does not have to live in the business database, but every instance must share that backend.

### 5.4. Locking the `@Scheduled` Method

~~~java
import java.time.Clock;
import java.time.LocalDate;
import java.util.Objects;

import net.javacrumbs.shedlock.spring.annotation.SchedulerLock;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class DailySettlementScheduler {

    private final JobLauncher jobLauncher;
    private final Job dailySettlementJob;
    private final Clock clock;

    public DailySettlementScheduler(
            JobLauncher jobLauncher,
            @Qualifier("dailySettlementJob") Job dailySettlementJob,
            Clock clock) {

        this.jobLauncher = Objects.requireNonNull(jobLauncher);
        this.dailySettlementJob = Objects.requireNonNull(dailySettlementJob);
        this.clock = Objects.requireNonNull(clock);
    }

    @Scheduled(cron = "0 10 1 * * *", zone = "UTC")
    @SchedulerLock(
            name = "batch.dailySettlement.schedule",
            lockAtMostFor = "PT2H",
            lockAtLeastFor = "PT30S")
    public void runDailySettlement() throws Exception {
        LocalDate businessDate = LocalDate.now(clock).minusDays(1);

        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", businessDate.toString(), true)
                .toJobParameters();

        JobExecution execution =
                jobLauncher.run(dailySettlementJob, parameters);

        if (execution.getStatus() != BatchStatus.COMPLETED) {
            throw new IllegalStateException(
                    "dailySettlementJob did not complete: "
                    + execution.getStatus());
        }
    }
}
~~~

Register a UTC **Clock**:

~~~java
@Bean
Clock clock() {
    return Clock.systemUTC();
}
~~~

The cron **0 10 1 * * *** is interpreted by Spring as **01:10 UTC** daily, and the Job receives **businessDate** as the previous UTC day. This example assumes the system's daily cutoff is defined in UTC; if the business uses another timezone, configure timezone consistently for both cron and date calculation. **Clock** also lets tests pin time without altering the system clock.

Only one scheduler instance acquires the lock named **batch.dailySettlement.schedule** at a time. Instances failing to acquire skip the guarded call. The method must be Spring-managed and invoked through ShedLock's proxy/interceptor mechanism; self-invocation via **this.runDailySettlement()** or manual instantiation with **new** can bypass the annotation depending on setup.

**Critical precondition:** the example assumes a **synchronous JobLauncher**, meaning **jobLauncher.run(...)** returns only after the Job finishes. If the application configures an asynchronous JobLauncher, the scheduler method can release the lock immediately after the Job starts while Batch processing continues. In that case, coordinate the lock with the **actual Job lifecycle** or use another design ensuring two Jobs cannot process the data simultaneously.

### 5.5. How Long Is the Lock Held?

ShedLock has two commonly confused parameters:

| Parameter | Purpose | Considerations |
| --- | --- | --- |
| **lockAtMostFor** | Maximum time a lock is held, even if the process fails to release it. | Must exceed expected execution duration plus reasonable buffer; too short risks two owners over time. |
| **lockAtLeastFor** | Holds the lock for at least this duration, even if the method finishes quickly. | Can reduce rapid re-runs from minor clock/schedule skew, but delays valid subsequent turns if set too high. |

Example:

~~~text
01:10:00  A acquires, lockAtMostFor=2h, lockAtLeastFor=30s
01:10:08  Job finishes, scheduler releases
01:10:30  Minimum lock duration elapses before lock is considered released
~~~

If the Job runs 40 minutes, the lock is held until the Job finishes (with a synchronous launcher). If A crashes at minute 20, the lock can remain until the maximum deadline computed at acquisition. If the Job actually runs **longer than 2 hours**, A may keep processing after the lock expires while another instance acquires it.

Do not habitually set **lockAtMostFor** equal to the cron interval. Base it on observed **longest acceptable Job duration**, timeout strategies, lock renewal capabilities, and crash recovery requirements. Longer leases mean longer recovery delays if the owner genuinely dies.

## 6. JobParameters Must Be Consistent per Business Period

A distributed lock does not fix broken JobParameters generation. Two requests processing the same **businessDate** should use the same identifying parameters so Spring Batch recognizes the same JobInstance.

**A pattern that can cause duplicate runs:**

~~~java
JobParameters params = new JobParametersBuilder()
        .addLong("timestamp", System.currentTimeMillis(), true)
        .toJobParameters();
~~~

Every launch creates a new JobInstance. If a lease expires while the first Job is still running, or a manual trigger bypasses the lock, a second Job can double-process the same data.

**Identifying by processing period:**

~~~java
JobParameters params = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .toJobParameters();
~~~

With the same Job name and same **businessDate**, Spring Batch can reject duplicate launches while running or after completion. This provides a second guard layer beneath the scheduler lock.

Not every Job is daily. For a 15-minute schedule, you can use **windowStart** or a period key normalized to an exact boundary, such as **2026-11-16T01:00:00Z**. The key is that all instances compute **the exact same boundary for the same period**, rather than millisecond-precision current timestamps.

For restartable Jobs:

1. The first run ends **FAILED** with that period's identifying parameters.
2. The restart uses the **exact same identifying parameters** so Spring Batch resumes the same JobInstance.
3. Do not invent new identifying parameters just to “force” a rerun. That bypasses checkpoints and increases duplicate-write risk.

Define a separate retry policy for failed periods: the next day's schedule usually advances to a new **businessDate**, so it **does not automatically restart** yesterday's Job. Detecting and handling failed periods can use operational tooling, retry schedules, or `JobOperator` under a clear workflow.

## 7. Which Part of the Flow Should the Lock Surround?

A Job may be triggered through multiple paths:

~~~text
                     +--> @Scheduled ---> Scheduler lock --+
                     |                                    |
dailySettlementJob <-+--> REST API / manual trigger ------+
                     |
                     +--> event listener / message --------+
~~~

If **@SchedulerLock** is placed only on the **@Scheduled** method, API, event, or admin paths can still launch the Job without hitting the lock. This is not a ShedLock bug; the declared guard only covers the scheduler entry point.

Three common strategies:

**Strategy A — lock guards the scheduler only:** used when the goal is preventing multiple pods from handling the same cron tick. Other paths rely on `JobRepository`, `JobParameters`, and idempotency. Simple when manual launches follow a separate procedure.

**Strategy B — all paths go through a shared coordinator:** place period selection and locking in one unified coordination service. Design the lock API carefully so both REST and scheduler genuinely invoke through the proxied layer; do not annotate a method and self-invoke bypassing the Spring proxy.

**Strategy C — lock by business key in the database:** for example, a **business_period** table with a unique constraint on the settlement period and processing state, plus atomic claim logic. This controls launch requests originating outside the scheduler as well.

In systems risking irreversible side effects, add protection at the **write destination**. Never assume every invocation path passes through the scheduler lock.

## 8. Risks of Async JobLauncher and Long-Running Jobs

Suppose the scheduler acquires a lock, calls an async JobLauncher, and returns in milliseconds:

~~~text
01:10:00  Instance A acquires lock
01:10:01  A launches Job, Job moves to another thread
01:10:01  @Scheduled method returns; lock is released
01:10:02  Instance B can acquire lock
01:10:02  B launches another Job / same period
01:10:03  A and B can process concurrently if other guards do not block
~~~

When using **TaskExecutorJobLauncher** with an asynchronous **TaskExecutor**, the launcher returning does not mean **JobExecution** has ended. Immediately checking **execution.getStatus()** may also show **STARTING** or **STARTED**, leading to wrong conclusions.

Choose one of these design options:

- Use a dedicated synchronous launcher for Jobs where the scheduler must hold the lock until completion, if resource and duration budgets allow.
- Use an orchestrator component that tracks **JobExecution** through terminal state and manages the lease accordingly.
- Use a queue/worker pattern with atomic work claiming instead of treating an async launch call as the entire unit of work.
- For very long Jobs, design monitored lease renewal and hung-owner handling; protect outputs with business keys/idempotency.

Never hold a single database transaction open for hours just to keep a row lock. Appropriate lock mechanisms depend on duration and crash recovery needs; lease locks avoid long transactions, which is precisely why lease expiration while an owner is still alive must be handled.

## 9. Scenarios to Understand Before Production

### 9.1. Two Instances Wake Up Skewed

Two schedulers do not necessarily fire at the exact same millisecond. Instance A may run seconds earlier than B due to CPU load, clock skew, or deployment timing. If A finishes too fast and releases the lock before B wakes up, B can acquire the lock and trigger the same period again.

**lockAtLeastFor** narrows this risk over a small window, but does not eliminate all delayed turns. **JobParameters identifying the business period** and target-data constraints remain necessary to protect results.

### 9.2. Lock-Holding Instance Is Killed

When a process is killed, lock-release code may not execute. With a lease lock, other owners must wait for **lockAtMostFor** to expire. Never manually edit **lock_until** without confirming the previous owner has actually stopped; forcing release while the old owner is still running can cause concurrent execution.

### 9.3. Lock Database Becomes Unavailable

If the lock database is unavailable, schedulers cannot acquire or renew locks normally. Crucially, **do not fall back to running unlocked** on connection failures. Log/alert clearly and pick an appropriate retry policy. Because coordination depends on the shared backend, backend availability is part of scheduler availability.

### 9.4. Inconsistent Lock Names

If A uses **batch.dailySettlement.schedule** and B uses **batch.daily-settlement.schedule**, the two names correspond to two distinct locks. Both instances will be granted execution rights. Keep lock names stable and defined consistently in one deployed artifact; when renaming, account for rolling deployments where old and new versions coexist.

### 9.5. Different Databases or Schemas

If one instance points to production and another points to a replica or different schema, each has its own **shedlock** table. Identical lock names do not coordinate across different stores. In multi-tenant environments, decide whether locks are per-tenant or Job-wide, and align identifiers accordingly.

### 9.6. Job Fails While the Scheduler Method Returns Normally

Spring Batch can return a **JobExecution** with **BatchStatus.FAILED** without throwing an exception out of **JobLauncher.run(...)**. ShedLock does not automatically decide retries based on business status. Observe **BatchStatus**, log, and alert; in the section 5 example, the method explicitly throws an exception when the Job is not **COMPLETED** to surface failure.

Even if the method throws an exception, the lock is normally released per invocation/lease lifecycle; **do not assume an exception causes the scheduler to retry immediately**. Retries and failed-Job remediation must be explicit decisions.

### 9.7. Rolling Deployments and Cron Changes

During rolling deployments, old and new versions coexist. If both versions share a lock name but perform incompatible processing, preventing overlap alone does not guarantee data correctness. If they use different lock names, both can run together. When changing schedules or `businessDate` logic, plan for the overlap window across versions.

## 10. Locks Do Not Guarantee Exactly-Once

In distributed systems, “only one scheduler acquires the lock” is different from “every side effect occurs exactly once.”

Example of a writer calling a payment transfer API:

~~~text
A acquires lock
A sends command with transactionId=T100
External system succeeds
A crashes before checkpoint is saved
A's lease expires
B restarts Job and resends transactionId=T100
~~~

Even when A and B **do not hold the lock at the same time**, the side effect can still happen twice. Therefore, writers should be designed to be **idempotent**, such as passing an **idempotency key** derived from business identity, using unique constraints, safe upserts, or an outbox combined with consumer deduplication.

If critical scenarios demand that only the latest owner may write, you may need **fencing tokens** or version checks at the destination data store. A simple lease lock can expire and grant ownership while an old owner is still running; checking “did I acquire the lock earlier” does not stop a stale owner from writing.

Example output table with a unique key per period:

~~~sql
CREATE TABLE daily_settlement (
    business_date DATE NOT NULL,
    account_id    BIGINT NOT NULL,
    total_amount  DECIMAL(18, 2) NOT NULL,
    PRIMARY KEY (business_date, account_id)
);
~~~

This table can prevent inserting duplicate **(business_date, account_id)** pairs, though proper update rules and transactions are still needed. Unique constraints are a data safety layer, not a substitute for testing Job correctness.

## 11. Alternatives Beyond ShedLock

### Quartz Clustering

If you need persistent schedules, misfire handling, multiple triggers, schedule pause/resume, dynamic schedules, or cluster node election for triggers, **Quartz with a clustered JDBC JobStore** is an option.

In that model, scheduler nodes share Quartz tables and are configured as members of the same cluster. A trigger is coordinated across nodes. **@DisallowConcurrentExecution** prevents concurrent executions of the same Quartz JobDetail/JobKey; it does not automatically stop distinct JobDetails from touching the same business data. You still need accurate mapping from triggers to Spring Batch Jobs and JobParameters.

Quartz fits better than ShedLock when the core problem is **rich, persistent schedule management**. If you only need a **@Scheduled** method to run once across multiple instances, ShedLock is usually simpler.

### Leader Election

A cluster can elect one instance as leader; only the leader fires schedules. This fits when the platform already provides leader election via Kubernetes, Consul, ZooKeeper, or similar infrastructure. Handle leader handovers and ensure a deposed leader stops producing side effects.

Leader election coordinates **node roles**, whereas scheduler locks coordinate **individual tasks**. They differ in scope and operational overhead.

### Database Advisory Locks or Row Locks

Some databases support advisory locks, **SELECT ... FOR UPDATE**, or atomic claim statements. These fit short transactions, claiming a work row, or tightly controlling data inside the database itself.

Understand lock lifecycles: some locks bind to transactions, others bind to sessions/connections. With JDBC connection pools, this distinction is critical. Never hold a transaction for hours to guard a long Job, and never acquire a session-scoped advisory lock and return the connection to the pool without a clear release mechanism.

### Kubernetes CronJob

If the workload is inherently a scheduled Job on Kubernetes, consider moving the schedule to a **CronJob** with an appropriate concurrency policy. **concurrencyPolicy: Forbid** limits overlap among Jobs owned by the same CronJob, but does not synchronize across separate CronJob resources or manual triggers. Nor does it guarantee end-to-end exactly-once across controller failures, retries, or non-transactional side effects.

| Mechanism | Best suited when | Key caveats |
| --- | --- | --- |
| **ShedLock + @Scheduled** | Apps have cron in each instance and need to skip duplicate turns | Shared lock store, accurate lease sizing, watch async/long-running Jobs |
| **Quartz clustered JobStore** | Need metadata-backed trigger, misfire, and central scheduler management | Configure JDBC clustering and Quartz lifecycle |
| **Leader election** | Cluster already has leader election and leader orchestrates multiple jobs | Leader failover, fencing, and stale-owner state |
| **DB lock / claim** | Want to claim a record, period, or task in the database | Transaction/connection scope and recovery handling |
| **Kubernetes CronJob** | Batch runs as isolated one-shot Jobs on Kubernetes | Concurrency policy applies only within that CronJob |

## 12. How to Verify Only One Scheduler Actually Runs

A unit test calling a scheduler method directly usually **does not prove the distributed lock works**, because annotations may activate only through Spring proxies and require a shared backend. A reliable integration test should simulate at least **two scheduler instances** or two independent application contexts sharing one lock table.

### Scenario 1: Two Schedulers Triggering the Same Period

Setup:

- Both A and B configure the same **LockProvider**, **shedlock** table, and lock name.
- Both compute **businessDate** from a fixed period.
- The Job runs long enough for both requests to contend for the lock; use **CountDownLatch** to coordinate rather than **Thread.sleep**.
- Target data has a business key and tracks how many times the task actually started.

Execution:

~~~text
T0:  Start schedulers A and B
T1:  Advance both to the point of acquiring the same lock
T2:  A acquires successfully; B fails to acquire
T3:  A executes the Job
T4:  A completes and releases lock
~~~

Expected: **one execution of the guarded method** runs during lock contention, and business output matches the input data. Do not assert A always wins; B may win depending on scheduling order.

### Scenario 2: Instance Crashes Mid-Job

A acquires the lock and terminates before releasing it. Verify B does not immediately overlap while the lease is still valid. Once the lease expires, B can acquire the lock on a subsequent turn, and recovery/restart via `JobRepository` keeps data consistent.

For such tests, set a short lease **only in an isolated test environment** so you do not wait for production durations. Never manually edit lease timestamps in a production database to “simulate” test conditions.

### Scenario 3: Job Runs Longer Than the Lease

Hold A past **lockAtMostFor** and let B attempt to acquire. The goal is to observe the **two owners over time** risk, then verify how `JobRepository`, `JobParameters`, and target-data safeguards handle the situation.

This test is especially valuable for Jobs with unpredictable durations. If relying on lease renewal, also test losing connectivity to the lock backend during renewal.

### Scenario 4: Failure After Side Effect

Have the writer write successfully to the target but fail before checkpointing, then rerun the same period. Verify the writer/target handles it idempotently without adding duplicate records or resending commands. This tests not just the scheduler lock, but overall recovery safety.

## 13. Operations, Logging, and Alerting

To spot missed schedules or overdue locks, record the following for each scheduled period:

| Observation field | Usage |
| --- | --- |
| **Job name** | Name of the Spring Batch Job triggered |
| **Lock name** | Identifies which task is being coordinated |
| **Business period** | Date or data window processed by the Job |
| **JobInstance/JobExecution ID** | Correlates with Spring Batch metadata tables |
| **Instance/pod ID** | Shows which node won ownership and ran the Job |
| **Start/end time, duration** | Tracks actual duration to tune lease limits |
| **BatchStatus, ExitStatus** | Identifies completed, failed, stopped, or custom exit status |
| **Lock skip count** | Distinguishes cron firing without winning the lock |
| **Latest successful run per period** | Detects missed periods or unretried failures |

Rows in **shedlock** reflect lease state, **not complete business execution history**. Never use **lock_until** to infer a Job actually succeeded. Monitor `JobRepository`, target data, and dedicated monitoring systems separately.

Set alerts when:

- No successful `JobExecution` exists past a business deadline.
- Job duration approaches **lockAtMostFor**.
- Leases frequently expire while Jobs are still active.
- Multiple output writes or unexpected multiple JobInstances appear for one period.
- The lock database is unavailable or lock-acquisition errors spike.

**Lock skips** are expected when multiple instances contend for one schedule. However, if all turns are skipped over a prolonged period, a lock may be stuck, an instance hung, or the lease misconfigured.

## 14. Mistakes to Avoid

### Using `synchronized` to Lock Across Multiple Pods

~~~java
@Scheduled(cron = "0 0 * * * *")
public synchronized void runBatch() {
    // ...
}
~~~

**synchronized** only synchronizes threads accessing **the same monitor inside one JVM**. Two pods run two independent JVMs and can still execute in parallel.

### Building Lock Names with Instance IDs

~~~java
// Conceptually wrong example:
String lockName = "dailySettlement-" + podName;
~~~

Each pod using a different name means each pod owns a different lock. Lock names must describe the **shared task**, not the instance; pod identity belongs in **locked_by** or logs.

### Releasing the Lock Right After Async Job Submission

Locking only around the submit call is insufficient if two Jobs must not run concurrently. Define when work is truly finished and guard the full lifecycle.

### Generating Different Identifying Run IDs per Pod

This turns the same business period into multiple JobInstances. Use a normalized **businessDate/windowStart** per period so `JobRepository` can distinguish duplicate runs from restarts.

### Treating a Lease Lock as Exactly-Once

Leases can expire, side effects can succeed before checkpoints, and schedulers can re-trigger. Treat **idempotency** as a business and writer responsibility.

### Sharing One Lock Name Across Unrelated Tasks

If Job A and Job B share a lock name unintentionally, they will block each other. Name locks after the **protected capability** and clearly define their scope.

## 15. Checklist for Multiple Scheduler Instances

- [ ] All scheduled instances use the **same lock backend and same lock name** per task.
- [ ] The lock table is created via migrations, has a primary key, and is centrally managed.
- [ ] Clocks are consistent; for JDBC ShedLock consider **usingDbTime()**.
- [ ] **lockAtMostFor** is sized from real Job duration plus buffer; overruns have a plan.
- [ ] **lockAtLeastFor** fits minor schedule skew and is never used to mask Job identification bugs.
- [ ] Locked methods are Spring-managed and annotations apply through the proper proxy mechanism.
- [ ] If the lock must hold for the full Job run, **JobLauncher is truly synchronous** or an alternative orchestrator manages it.
- [ ] Identifying **JobParameters** are consistent per business period and reused accurately on restarts.
- [ ] Non-cron launch paths have explicit concurrency policies.
- [ ] Writers and target tables enforce deduplication/idempotency across crashes and retries.
- [ ] Integration tests cover at least two instances contending for the lock, owner loss, lease expiry, and recovery.
- [ ] Metrics/logs exist per run period to detect scheduler skips, Job failures, or abnormal slowdowns.

When deploying Spring Batch with multiple scheduler instances, a reliable design typically combines a **distributed lock to pick the active instance**, **`JobRepository` to manage JobInstance and restart**, and **idempotent rules to safeguard business results**. All three layers play a role: locks reduce contention when cron fires across JVMs, `JobRepository` manages Batch Job lifecycles, and destination-data controls protect against crashes, retries, and edge cases a lease cannot eliminate alone.

