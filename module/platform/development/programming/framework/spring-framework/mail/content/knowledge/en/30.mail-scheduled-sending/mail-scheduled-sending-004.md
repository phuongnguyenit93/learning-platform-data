# Quartz or External Schedulers for Durable Scheduling

A Spring Framework Mail application often starts simply: when a user confirms an order, a service calls `JavaMailSender.send(...)`. However, many notifications must be sent **at a future point in time**, such as an appointment reminder 24 hours ahead, a contract renewal notice at 08:00 in the customer's timezone, or a weekly report sent on business days. If a timestamp is only kept in a Java variable or `Thread.sleep(...)` is used, application restarts, deployments, crashes, multi-instance scaling, or daylight saving transitions can cause schedules to misfire or vanish completely.

The topic **"Quartz or external schedulers for durable scheduling"** in the **Scheduled Sending** module of **Spring Framework Mail** addresses the question: **How do you persist send intent, recover schedules after a process stops, and handle triggers in a controlled manner?**

We will progress from scheduling requirements and practical guarantees to configuring **Quartz with a JDBC JobStore**, creating `JobDetail`/`Trigger`, handling **misfires**, **clustering**, **timezones/DST**, and designing a **transactional outbox**. The guide also covers external schedulers such as infrastructure cron, Kubernetes CronJob, cloud scheduler services, and workflow engines, comparing trade-offs and presenting idempotency models and testing strategies.

**Core takeaway:** *A durably persisted schedule* does not equal *an email delivered exactly once*. Quartz or an external scheduler can trigger work; the application itself must still manage notifications, SMTP submissions, retries, and uncertain outcomes.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish "running a method on a timer" from "managing a durable schedule".
2. Explain Quartz components: `Scheduler`, `Job`, `JobDetail`, `Trigger`, and `JobStore`.
3. Configure Quartz to use **JDBC JobStore** in Spring Boot instead of the default in-memory store.
4. Register one-shot or cron-based schedules with explicit identities and timezones.
5. Distinguish **Quartz JobDetail durability** from **durability of the entire scheduling system**.
6. Handle cases where the application was down at due time and decide whether to catch up or skip.
7. Safely operate multiple application instances with cluster configuration and shared data.
8. Use schedules to **create notification/outbox entries idempotently** rather than calling SMTP directly inside transactions.
9. Compare embedded Quartz with external schedulers across infrastructure needs, permissions, durability, and operations.
10. Test schedules, restarts, duplicate triggers, timezones, cancel/reschedule flows, SMTP errors, and recovery.

## 2. What Must a "Durable Schedule" Actually Guarantee?

A solid email scheduling system should answer these questions:

- **Where is the schedule definition stored?** Process memory, Quartz's database, or an external service?
- **Do schedules survive an application restart?** Definitions and next-fire times must be restored.
- **Will two running instances fire duplicates?** What distribution/claiming mechanism exists?
- **What happens if due time arrives while workers are down?** Catch up, skip, or raise an alert?
- **Which timezone interprets send time?** Are DST and calendar rules accounted for?
- **What happens if a user cancels or edits a schedule?** Will the old trigger still fire?
- **How does the scheduler handle SMTP errors?** Retry via the same job or via a queue/outbox?
- **What if a crash occurs after SMTP accepted but before DB commit?** Can duplicates happen?
- **Can you tell who modified a schedule and which work actually ran?**

A sample requirement:

> Send an appointment reminder email at 09:00 in the recipient's timezone on the day before the appointment; if the application is down for 30 minutes, there must be an explicit decision to catch up or skip; if cancelled, do not send; if the job fires again, never create two identical notifications.

Relying solely on `@Scheduled` without persisting schedule definitions in a database **will not automatically satisfy** all of these requirements.

## 3. Distinguishing Schedule, Occurrence, Notification, and Attempt

| Concept | Example | Role |
| --- | --- | --- |
| **Schedule** | Renewal reminder on the 5th of every month | Rule governing future runs |
| **Occurrence** | Due run on 2026-12-05 at 09:00 | One logical activation of a schedule |
| **Notification** | Renewal reminder email to Customer A for that occurrence | Business send intent |
| **Submission attempt** | One send try through SMTP provider X | One delivery of the message to the provider |
| **Provider delivery event** | Delivered/bounced/deferred | Asynchronous post-submission evidence |

One recurring schedule produces many occurrences; one occurrence may produce many notifications for a large recipient list; one notification may require multiple attempts. Therefore:

```text
Schedule S-100
     |
     +-- Occurrence O-1 (plannedAt=2026-12-05T02:00Z)
     |      |
     |      +-- Notification N-A -> Attempt 1 -> SMTP
     |      +-- Notification N-B -> Attempt 1 -> SMTP
     |
     +-- Occurrence O-2 (plannedAt=2027-01-05T02:00Z)
            |
            +-- Notification N-A2 -> Attempt 1 -> SMTP
```

**Never use a single boolean `isSent` for an entire recurring schedule.** This month's run may be submitted while next month's still needs to be generated. Conversely, multiple job invocations for the same planned occurrence must never create duplicate notifications.

## 4. Why Is @Scheduled Insufficient for Some Requirements?

Spring supports:

```java
@Scheduled(cron = "0 0 9 * * MON-FRI", zone = "Asia/Ho_Chi_Minh")
public void sendDailySummary() {
    // ...
}
```

This is a useful tool for simple periodic tasks; however, when schedules are user-created/edited/cancelled and must be distributed across multiple instances, relying solely on the annotation has limitations:

- Cron expressions are typically tied to code/config and do not automatically become durable schedule records.
- Each instance may independently execute the method if scheduling is enabled on all.
- Does not durably persist individual occurrences by default.
- Does not automatically create idempotency keys for notifications.
- When the app is down at run time, provides no built-in business catch-up policy.
- Provides no built-in cluster claiming/job persistence equivalent to Quartz JDBC JobStore via `@Scheduled` alone.

This **does not mean `@Scheduled` is always wrong**. With a worker polling the database every few seconds for due notifications, `@Scheduled` can still fit **if the database itself guarantees schedule persistence, claiming, and idempotency**. In that case durability lives in the database and worker logic, not in the annotation.

## 5. Architectural Options

| Option | Where schedules live | Best fit when | What must be added |
| --- | --- | --- | --- |
| Simple `@Scheduled` | Code/config, runtime | Simple periodic jobs, no per-user dynamic schedules | DB claiming, idempotency if multi-instance |
| **Quartz RAMJobStore** | Process memory | Demos, tests, regenerable schedules | State lost on restart |
| **Quartz JDBC JobStore** | Quartz database | Dynamic schedules, cron/one-shot, clustering, misfires | Schema/DB ops, idempotent notifications |
| **DB due-time + polling worker** | Application database | High-volume one-shot, business-oriented schedules | Claim/lease, indexes, backfill |
| **External scheduler** | Cloud/cron/Kubernetes platform | Infrastructure-managed schedules calling HTTP/queues on time | Secure ingress, dedupe, target HA |
| **Workflow engine** | Engine state/event store | Long-running flows with multi-step waits/timeouts | Learning curve, engine ops, activity idempotency |
| **Provider send-at feature** | Mail provider | Email only needs delayed send and feature is supported | Vendor limits, cancel semantics, feedback |

No single solution wins in every case. Second-level precision, schedule volume, edit permissions, deployment topology, quotas, and SLAs dictate where responsibility belongs.

## 6. What Concepts Does Quartz Include?

Quartz centers around these core components:

| Component | Function |
| --- | --- |
| `Scheduler` | Manages registration, pause/resume, and execution |
| `Job` | Class executing the action when a trigger fires |
| `JobDetail` | Describes the job, its identity, and `JobDataMap` |
| `Trigger` | Rule for **when** a job fires |
| `SimpleTrigger` | One-shot or simple fixed-interval schedule |
| `CronTrigger` | Recurring schedule based on a cron expression |
| `JobStore` | Persists job/trigger state |
| `RAMJobStore` | In-process memory |
| `JDBC JobStore` | Persists to a SQL database; supports durability and clustering when properly configured |
| `JobDataMap` | Small configuration payload attached to a job/trigger |
| `JobListener` / `TriggerListener` | Observes job/trigger lifecycle events |

A diagram:

```text
Order reminder schedule
         |
         v
JobDetail: ReminderDispatchJob
         |
         +-- key = "reminder-123"
         +-- data = scheduleId
         |
         v
Trigger: fireAt / cron + time zone
         |
         v
Quartz Scheduler
         |
         v
Quartz JobStore (RAM or JDBC)
         |
         v
ReminderDispatchJob.execute(context)
         |
         v
Business outbox / SMTP worker
```

A `JobDetail` is not the email itself. A `Trigger` does not hold the full sending workflow either. They are mechanisms to **trigger the right work** on schedule.

## 7. "Durable Job" Differs From "Durably Persisted Schedule"

In Quartz, `JobBuilder.storeDurably()` has a narrow meaning: **retain the `JobDetail` even when no triggers remain attached to it**.

```java
JobDetail job = JobBuilder.newJob(ReminderDispatchJob.class)
        .withIdentity("reminder", "mail")
        .storeDurably()
        .build();
```

Do not mistake `storeDurably()` for automatically saving schedules to a database. When `RAMJobStore` is used, a "durable" job still disappears on JVM restart. To **persist job/trigger state across restarts**, you need a persistent JobStore such as **Quartz JDBC JobStore**.

Conversely, once JDBC JobStore is enabled, triggers and jobs are written to the database by design. `storeDurably()` is only needed when you want a `JobDetail` to exist independently of triggers—not as a "durability switch" for every schedule.

## 8. What Quartz Clustering Helps With—and What It Does Not

When multiple application instances share the **same Quartz JDBC JobStore** with clustering configured:

```text
App instance A ---+
                  |
App instance B ---+--> Shared Quartz DB
                  |       |
App instance C ---+       +--> Trigger acquisition/locks
                          |
                          v
                    One job firing claimed by node
```

Quartz coordinates trigger acquisition through the database so all nodes do not independently execute the same scheduled firing.

However:

- A job may still be recovered/re-executed during failover scenarios depending on configuration.
- SMTP is an external side effect outside the Quartz transaction.
- If a job calls SMTP and the node crashes before saving the outcome, the cluster cannot tell whether the message was submitted.
- Misfires can trigger catch-up executions.
- Two distinct logical schedules can still produce the same notification if the business model lacks deduplication.

Therefore, **cluster scheduling does not automatically deliver exactly-once emails**. You still need idempotency at the occurrence/outbox layer and SMTP attempt tracking.

## 9. Recommended Model: Scheduler Triggers, Outbox Owns Sending

A design much easier to control than sending directly inside `Job.execute`:

```text
Quartz or External Scheduler
              |
              v
      Due occurrence event
              |
              v
     Application transaction
       - validate schedule
       - insert occurrence (idempotent)
       - insert notification/outbox
              |
              v
            COMMIT
              |
              v
       Mail outbox worker
              |
              v
       Compose MimeMessage
              |
              v
       JavaMailSender.send()
              |
              v
    Store submission outcome
```

Benefits:

1. The Quartz Job completes fast without holding scheduler threads across slow SMTP I/O.
2. Re-fired triggers are deduplicated by a unique key in the database.
3. The outbox survives restarts with clear retry ownership.
4. The business transaction creating notifications is decoupled from SMTP.
5. Schedules can be cancelled/edited without ambiguously aborting in-flight SMTP calls.
6. Logs and metrics distinguish **schedule triggered**, **notification created**, **SMTP submitted**, and **delivered**.

### What not to do by default

```java
public void execute(JobExecutionContext context) {
    // Avoid sending directly and assuming Quartz will handle
    // all retries, idempotency, and delivery for you.
    mailSender.send(...);
}
```

Direct sending can still fit demos or non-critical jobs, provided you separately handle errors, retries, timeouts, and ambiguous outcomes. For important business emails, an outbox provides critical separation of concerns.

## 10. Spring Boot Dependency Configuration

In a Spring Boot project using Quartz, dependencies typically include:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-quartz'
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

`spring-boot-starter-quartz` integrates Quartz with the application context. `spring-boot-starter-jdbc` and the driver provide the datasource for JDBC JobStore; if the app already has DataSource/JPA, exact dependencies may vary. Use your project's compatible dependency management rather than arbitrarily mixing Quartz/Spring versions by hand.

In modern Spring Boot 3.x apps, Spring Mail uses `jakarta.mail`. Quartz `Job`/`Trigger` code is independent of the mail namespace, while MIME composers must match your Spring Framework version.

## 11. RAMJobStore: When Is It Useful?

For rapid development or tests that do not need persistence:

```yaml
spring:
  quartz:
    job-store-type: memory
```

The scheduler holds jobs and triggers in memory. When the process stops, this state vanishes unless you re-register schedules from an application-owned durable source.

RAMJobStore fits well for:

- Demonstrating the Quartz API.
- Unit/integration tests verifying trigger logic.
- Running transient tasks that can be lost or recreated.

It is **not** the default answer for user-created schedules expected to survive deployments or restarts.

## 12. JDBC JobStore: The Foundation of Persisted Schedules

Example with PostgreSQL:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/mail_app
    username: ${DB_USER}
    password: ${DB_PASSWORD}
  quartz:
    job-store-type: jdbc
    jdbc:
      initialize-schema: never
    overwrite-existing-jobs: false
    properties:
      org.quartz.scheduler.instanceName: MailScheduleCluster
      org.quartz.scheduler.instanceId: AUTO
      org.quartz.jobStore.isClustered: true
      org.quartz.jobStore.clusterCheckinInterval: 20000
      org.quartz.jobStore.misfireThreshold: 60000
      org.quartz.jobStore.tablePrefix: QRTZ_
      org.quartz.threadPool.threadCount: 5
```

The configuration above is an **example for an environment where Quartz tables already exist and clustering is desired**. Declare the proper datasource, ensure Quartz tables match the exact version, and ensure **all instances share the same database, `tablePrefix`, and `instanceName` with unique instance IDs**. Apps with multiple datasources may need to designate Quartz's datasource explicitly (e.g., via Spring Boot's `@QuartzDataSource`).

### Why `initialize-schema: never` in production?

Quartz requires a set of tables usually prefixed with `QRTZ_`. In Spring Boot, automatic schema initialization runs table-creation scripts; some standard scripts may **drop and recreate tables**, risking loss of persisted jobs. Never run automatic drop/recreate scripts on every production startup.

Instead:

1. Pick the Quartz schema script matching your **exact database and Quartz version**.
2. Include the schema in a reviewed migration (Flyway/Liquibase or DBA workflow).
3. Apply migrations in a controlled manner before starting the scheduler.
4. Let Spring Boot use the pre-existing tables.
5. Enforce backups and environment-scoped database permissions.

Never assume setting `job-store-type: jdbc` alone is enough if the Quartz schema has not been created or is incompatible.

## 13. Key Considerations for Quartz JDBC in a Cluster

| Setting or condition | Why does it matter? |
| --- | --- |
| Shared database | Nodes must see the same job/trigger state |
| Same `instanceName` | Nodes join the same logical scheduler |
| `instanceId=AUTO` or unique ID | Prevents two nodes from sharing the same scheduler instance ID |
| `jobStore.isClustered=true` | Enables JDBC JobStore's cluster coordination |
| Properly schema'd Quartz tables | Needed for persistence, locks, and triggers |
| Synchronized server clocks | Large clock skew breaks fire times and failure detection |
| Sufficient DB connection pool | Scheduler needs connections to read/write triggers |
| Proper database permissions | JobStore must update states and locks |
| Backup/migration plan | Avoids wiping registered schedules during upgrades |
| Idempotent jobs | Recovery and error handling never produce duplicate side effects |

**Never run two different Quartz clusters targeting the same set of tables independently**, nor mix non-clustered instances against tables used by clustered instances. Inconsistent configuration causes trigger-acquisition errors and unpredictable behavior.

When sharing one database across multiple applications, isolate via distinct `instanceName`, table prefixes, or separate datasources—never rely on colliding `JobKey` names to partition data without proper design.

## 14. Writing a Quartz Job That Only Creates Occurrences/Outbox Entries

A `Job` should take a schedule ID and **delegate to a service** that handles idempotency. Never store raw SMTP credentials, attachment bytes, or whole `MimeMessage` objects in `JobDataMap`.

```java
import org.quartz.DisallowConcurrentExecution;
import org.quartz.Job;
import org.quartz.JobExecutionContext;
import org.quartz.JobExecutionException;
import java.time.Instant;
import java.util.Date;
import java.util.UUID;

@DisallowConcurrentExecution
public class MailOccurrenceJob implements Job {

    private ScheduleDispatchService dispatchService;

    // For Quartz JobFactory dependency injection.
    public void setDispatchService(
            ScheduleDispatchService dispatchService
    ) {
        this.dispatchService = dispatchService;
    }

    @Override
    public void execute(JobExecutionContext context)
            throws JobExecutionException {

        try {
            String id = context.getMergedJobDataMap()
                    .getString("scheduleId");
            UUID scheduleId = UUID.fromString(id);

            Date plannedFireTime = context.getScheduledFireTime();
            if (plannedFireTime == null) {
                throw new IllegalStateException(
                        "No scheduled fire time"
                );
            }

            Instant plannedAt = plannedFireTime.toInstant();

            dispatchService.materializeOccurrence(
                    scheduleId,
                    plannedAt
            );
        } catch (RuntimeException failure) {
            throw new JobExecutionException(
                    "Failed to materialize mail occurrence",
                    failure
            );
        }
    }
}
```

`ScheduleDispatchService` is an **application-defined service**. The job reads `scheduleId` and `scheduledFireTime` from Quartz and invokes the service; the service verifies the schedule is still valid and creates the occurrence and outbox rows in the database.

### Dependency injection in Quartz Jobs

Quartz instantiates `Job` instances via `JobFactory`. To inject `ScheduleDispatchService`, configure a `JobFactory` integrated with the Spring container or use the integration provided by your Spring Boot version.

The setter above shows one injection option; **it does not run automatically unless your job factory invokes setters**. Constructor or field injection is more common when using an autowiring-capable `JobFactory` in your Spring Boot version. Verify injection via an integration test against the application context.

In standalone setups without DI, a job can retrieve a preconfigured service bridge from `SchedulerContext`; still, avoid abusing global lookups or storing Spring beans in a persistent `JobDataMap`.

## 15. JobDataMap Should Hold Small, Serializable Identifiers

Good example:

```java
.usingJobData("scheduleId", scheduleId.toString())
```

What to avoid:

```java
// Avoid storing full business objects or large payloads in the job store.
JobDataMap data = new JobDataMap();
data.put("customerEntity", customerEntity);
data.put("mimeMessage", mimeMessage);
data.put("pdfBytes", hugePdfByteArray);
```

Reasons:

- JobStore persistence may serialize `JobDataMap` values.
- Java classes can change across deployments.
- JPA entities carry lazy references and lack the durable lifecycle of a job record.
- Attachment bytes bloat database/heap size and backup costs.
- Recipient/token/PII data could leak into Quartz tables.
- If job data is treated as an immutable snapshot when it is actually stale, wrong emails get sent.

Prefer an opaque `scheduleId` and `tenantId` or a few small strings/scalars. Fetch business data from a controlled store at materialization time.

### Should the full email content be stored in the schedule?

It depends on requirements. For an issued invoice, content may need snapshotting/versioning so it cannot change later. However, that snapshot belongs in a notification/content management store or immutable storage—**not necessarily inside Quartz `JobDataMap`**.

## 16. Registering a One-Time Schedule with SimpleTrigger

Suppose the application has a `scheduleId` and a valid future `Instant` named `plannedAt`:

```java
import org.quartz.JobBuilder;
import org.quartz.JobDetail;
import org.quartz.JobKey;
import org.quartz.Scheduler;
import org.quartz.SimpleScheduleBuilder;
import org.quartz.Trigger;
import org.quartz.TriggerBuilder;

import java.time.Instant;
import java.util.Date;
import java.util.UUID;

public final class OneTimeMailScheduler {

    private final Scheduler quartz;

    public OneTimeMailScheduler(Scheduler quartz) {
        this.quartz = quartz;
    }

    public void schedule(
            UUID scheduleId,
            Instant plannedAt
    ) throws Exception {

        JobKey jobKey = JobKey.jobKey(
                "mail-" + scheduleId,
                "mail-once"
        );

        JobDetail detail = JobBuilder
                .newJob(MailOccurrenceJob.class)
                .withIdentity(jobKey)
                .usingJobData(
                        "scheduleId",
                        scheduleId.toString()
                )
                .build();

        Trigger trigger = TriggerBuilder.newTrigger()
                .withIdentity(
                        "fire-" + scheduleId,
                        "mail-once"
                )
                .forJob(detail)
                .startAt(Date.from(plannedAt))
                .withSchedule(
                        SimpleScheduleBuilder.simpleSchedule()
                                .withMisfireHandlingInstructionFireNow()
                )
                .build();

        quartz.scheduleJob(detail, trigger);
    }
}
```

`SimpleScheduleBuilder` with `FireNow` misfire handling is a **deliberate policy choice for this example**. Not every overdue reminder should fire immediately. For time-sensitive notifications, the business service may choose to skip stale occurrences even if Quartz fires.

### Avoid re-registering the same JobKey

`quartz.scheduleJob(detail, trigger)` can fail if a job/trigger identity already exists. Do not automatically "delete and recreate if exists", because that can lose pending triggers or silently alter schedules.

A schedule-creation API should:

1. Persist the business schedule and version first.
2. Use stable `JobKey`/`TriggerKey` identities.
3. Distinguish **create**, **update**, and **cancel**.
4. Use optimistic locking or an appropriate concurrency-control mechanism.
5. When an entry exists, determine whether it is an idempotent retry of the same request or a real conflict.
6. Never let concurrent requests overwrite schedules without versioning.

Quartz offers `checkExists`, `rescheduleJob`, `unscheduleJob`, and `deleteJob`. However, **check-then-create is not atomic** under concurrent callers; handle `ObjectAlreadyExistsException` or designate a single owner for schedule registration.

## 17. Recurring Schedules with CronTrigger

Example: run at **09:00 AM Monday through Friday**, Vietnam time.

```java
import org.quartz.CronScheduleBuilder;
import org.quartz.JobBuilder;
import org.quartz.JobDetail;
import org.quartz.Trigger;
import org.quartz.TriggerBuilder;

import java.time.ZoneId;
import java.util.TimeZone;

ZoneId zoneId = ZoneId.of("Asia/Ho_Chi_Minh");

JobDetail job = JobBuilder.newJob(MailOccurrenceJob.class)
        .withIdentity("daily-report-" + scheduleId, "mail-cron")
        .usingJobData("scheduleId", scheduleId.toString())
        .build();

Trigger trigger = TriggerBuilder.newTrigger()
        .withIdentity("daily-fire-" + scheduleId, "mail-cron")
        .forJob(job)
        .startNow()
        .withSchedule(
                CronScheduleBuilder
                        .cronSchedule("0 0 9 ? * MON-FRI")
                        .inTimeZone(TimeZone.getTimeZone(zoneId))
                        .withMisfireHandlingInstructionDoNothing()
        )
        .build();

quartz.scheduleJob(job, trigger);
```

Quartz cron typically has six required fields:

```text
seconds minutes hours day-of-month month day-of-week [year]

   0      0     9        ?          *      MON-FRI
```

`?` means no specific value for that date field when the expression targets the other date field. Never copy a five-field Unix cron expression assuming Quartz interprets it identically. Spring `@Scheduled` cron and Quartz cron also differ in syntax and features across versions.

### Why validate with `ZoneId.of(...)` first?

`ZoneId.of("Asia/Ho_Chi_Minh")` validates the timezone ID against Java's zone rules. When accepting timezones from users, never pass arbitrary strings directly into `TimeZone.getTimeZone(String)` because it silently falls back for invalid IDs.

### When missed business-day schedules must be caught up

Choosing `withMisfireHandlingInstructionDoNothing()` means you accept **skipping missed firings** under CronTrigger misfire rules. If every business day's report is mandatory, implement **backfill/reconciliation keyed by business date** and occurrence key rather than assuming Quartz will replay every missed day.

## 18. Differences Between SimpleTrigger and CronTrigger

| Requirement | Appropriate trigger | Notes |
| --- | --- | --- |
| Send one email at 14:00 on day X | `SimpleTrigger` with `startAt` | Fits one-shot schedules |
| Send every 15 minutes | Simple repeat or cron | Decide fixed interval vs. wall-clock |
| Send at 09:00 every Monday | `CronTrigger` | Timezone-aware |
| Send on the 1st of every month | `CronTrigger` | Control timezone/misfire |
| Send per holiday calendar | Cron + calendar or business planner | Cron does not know holidays automatically |
| Send reminder 24 hours before appointment | Compute `Instant` then one-shot | Must update/cancel if appointment changes |
| Sequence "after event A, wait 3 days" | Dynamic schedule or workflow engine | May require a state machine |

Before picking a trigger, ask whether the business wants **real elapsed duration** (e.g., 24 hours after an event) or **local wall-clock time** (e.g., 09:00 every day). Those two diverge across DST transitions.

## 19. @DisallowConcurrentExecution Is Not Idempotency

The annotation:

```java
@DisallowConcurrentExecution
public class MailOccurrenceJob implements Job {
    // ...
}
```

prevents Quartz from concurrently running multiple instances of the **same `JobDetail`/`JobKey`** according to Quartz rules.

However:

- Two different JobKeys can still create notifications for the same recipient.
- A job can fire again after the previous run finishes.
- A retried/recovered trigger can repeat side effects.
- External schedulers know nothing about this annotation.
- Crashing after SMTP accepted cannot be rolled back.

Relying solely on the annotation cannot stop an occurrence from being inserted twice. **A unique constraint on the occurrence business key remains essential.**

## 20. What Is a Misfire?

A **misfire** occurs when Quartz detects that a trigger missed its scheduled fire time beyond its configured threshold—for example due to process downtime, busy thread pools, database unavailability, or a paused scheduler.

```text
09:00  Trigger should fire
08:58  App stopped
09:00  No worker available
09:30  App restarted
        |
        v
Quartz detects missed fire
        |
        v
Apply misfire instruction
```

Common misfire policies for `CronTrigger`:

| Policy | General meaning | Best fit |
| --- | --- | --- |
| Smart policy (default) | Quartz picks a strategy based on trigger type | Only when you understand that type's behavior |
| `withMisfireHandlingInstructionFireAndProceed()` | Run once immediately, then continue schedule | Reminders that should catch up once |
| `withMisfireHandlingInstructionDoNothing()` | Discard missed firings, wait for next future time | Digests/reminders no longer useful once late |
| Ignore misfire policy | Bypass standard misfire handling | Must understand backlog and burst risks |

For `SimpleTrigger`, misfire instructions differ from `CronTrigger` and depend on repeat configuration. Never apply `CronTrigger` instruction names to `SimpleTrigger`.

### "Fire once now" does not automatically replay every occurrence

If a 5-minute cron job was down for two hours, a "fire once now" policy **does not automatically generate 24 emails for the 24 missed slots**. It may trigger **one catch-up execution**, while backfilling 24 periods belongs to a domain planner if required.

### Do not let misfires cause a mail storm

Suppose 50,000 tenants have schedules at the top of the hour. After downtime, immediately catching up all of them can:

- Exceed SMTP quotas.
- Saturate all Quartz worker threads.
- Spike queue backlogs, CPU, and memory.
- Trigger spam/rate-limit alerts.
- Send obsolete notifications.

Enforce policies on occurrence max age, batch sizes, rate limiting, and recovery pacing. Misfire instructions only decide **when Quartz fires**, not total throughput or catch-up business rules.

## 21. Business Policies for Overdue Schedules

A late firing should not always be handled the same way:

| Email category | Example | When 3 hours late | Policy suggestion |
| --- | --- | --- | --- |
| OTP or verification code | Code expires in 5 minutes | No longer useful | Skip, issue a fresh code on request |
| Appointment reminder | Remind 1 day ahead | May still be useful | Check that the appointment is still in the future |
| Periodic report | Business-day summary | May require backfill | Key by business period ID |
| Invoice | Issued per billing cycle | Should not be lost | Create occurrence/outbox idempotently |
| Marketing campaign | Send within allowed hours | May no longer be valid | Check send window, consent, suppression |
| Security alert | Anomaly detected | Likely needs delivery ASAP | Verify data, priority, and deadline |

A general policy flow:

```text
Quartz fires occurrence
      |
      v
Does schedule exist and active?
      |
      +-- No -> skip/audit
      |
      v
Is planned time still eligible?
      |
      +-- Too old -> SKIPPED_STALE
      |
      v
Has this logical occurrence been materialized?
      |
      +-- Yes -> no-op (idempotent)
      |
      v
Create outbox notification(s)
```

Quartz may decide to "fire now", but the **business service must decide whether to send the email** based on live event status, content validity, and recipient eligibility.

## 22. Timezones: Storing Instant and Interpreting Local Time

Two common scheduling intents:

**A. Send at an absolute point in time.**

> Send right at 2026-12-05T02:00:00Z.

Store an `Instant` or equivalent UTC timestamp.

**B. Send in the recipient's local time.**

> Send at 09:00 on business days, in Europe/Berlin.

Store at least:

- The cron rule or local date-time.
- The IANA `ZoneId`, such as `Europe/Berlin`.
- The DST policy when local times do not exist or repeat.
- The business rule version/meaning.

Example converting local date-time to an instant:

```java
import java.time.*;

LocalDate date = LocalDate.of(2026, 12, 5);
LocalTime time = LocalTime.of(9, 0);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime scheduledLocal = ZonedDateTime.of(
        date, time, zone
);
Instant plannedAt = scheduledLocal.toInstant();
```

`Instant` fits **one-shot scheduling**. `CronTrigger` expresses a recurring rule plus a timezone, so it needs `ZoneId` preserved so future runs still occur at 09:00 local time.

## 23. Daylight Saving Time (DST): A Local Hour Can Be Missing or Repeated

In timezones observing DST transitions:

- When clocks **spring forward**, some local times do not exist.
- When clocks **fall back**, some local times occur twice with two UTC offsets.

For instance, a "02:30 daily" schedule in a DST-observing timezone may have no 02:30 firing on the spring-forward day, or hit a repeated hour on the fall-back day.

**Never blindly add 24 hours to an `Instant` and assume it stays 09:00 local time tomorrow.** If the business wants "every day at 09:00 local time", compute the next occurrence using local time + `ZoneId` rules and configure the scheduler with that timezone.

### Rules to decide upfront

For a nonexistent local time:

- Skip the occurrence?
- Run at the next valid time?
- Shift to another hour per policy?

For a repeated hour:

- Run once for the day?
- Run on the earlier offset or the later offset?
- Is there any business case that genuinely needs both?

Quartz/`CronTrigger` has implementation-specific DST behaviors. If your product needs strict semantics, **persist business occurrences by local date + policy** and test across DST transition dates—never guess solely from a cron expression.

## 24. Store the Recipient's Timezone or the Creator's Timezone?

One question can change business behavior completely:

> 09:00 in whose timezone?

Different options:

- Organization's fixed timezone.
- Customer's timezone at schedule creation time.
- Customer's current timezone on each execution.
- Store/branch location's timezone.

Suppose a customer moves from Hanoi to Berlin. If the requirement is "09:00 in the customer's **current** local time", schedules must update or recalculate when their timezone changes. If the requirement is "09:00 branch time", do not use the customer's profile timezone.

Choose a policy, persist it explicitly on the schedule record, and audit changes. Never rely on the JVM or container default timezone.

## 25. Business Database Schema for Schedules and Occurrences

Quartz JDBC tables manage job/trigger state; applications still typically need **business schedule tables** for ownership, consent, templates, and outcomes.

Illustrative PostgreSQL schema:

```sql
CREATE TABLE mail_schedule (
    schedule_id UUID PRIMARY KEY,
    owner_id UUID NOT NULL,
    schedule_kind VARCHAR(20) NOT NULL,
    cron_expression VARCHAR(120),
    zone_id VARCHAR(100) NOT NULL,
    one_shot_at TIMESTAMPTZ,
    state VARCHAR(20) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    template_key VARCHAR(100) NOT NULL,
    template_version VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE mail_schedule_occurrence (
    schedule_id UUID NOT NULL
        REFERENCES mail_schedule(schedule_id),
    planned_fire_at TIMESTAMPTZ NOT NULL,
    materialized_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    result VARCHAR(30) NOT NULL,
    PRIMARY KEY (schedule_id, planned_fire_at)
);

CREATE TABLE mail_outbox (
    notification_id UUID PRIMARY KEY,
    schedule_id UUID NOT NULL,
    planned_fire_at TIMESTAMPTZ NOT NULL,
    recipient_id UUID NOT NULL,
    template_key VARCHAR(100) NOT NULL,
    template_version VARCHAR(40) NOT NULL,
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (schedule_id, planned_fire_at, recipient_id)
);
```

This is an **instructional schema**. In production, add foreign keys/indexes, tenant scoping, data retention, attempt records, `state` check constraints, partitioning strategies, and migration management.

### Why does occurrence have a unique key?

`PRIMARY KEY (schedule_id, planned_fire_at)` ensures a logical schedule occurrence cannot be inserted twice within that key scope.

`UNIQUE(schedule_id, planned_fire_at, recipient_id)` protects each recipient notification within an occurrence. If two workers materialize concurrently during recovery/retry, the transaction must perform an idempotent insert.

### What if a schedule is edited to the same timestamp?

If business rules allow cancelling/editing and recreating a send at the same `planned_fire_at`, decide whether the old occurrence counts as the same event or a new **schedule revision**. You can include `schedule_version` in the business key, though that allows multiple notifications for the same timestamp if the version changes.

Never add revision to the key merely to "resolve conflicts" if the product **forbids resending** when a schedule is edited. That is a business decision, not just an indexing detail.

## 26. Materializing Occurrences via Idempotent Transactions

When a Quartz Job or external scheduler triggers, the service should:

1. Begin a transaction.
2. Lock or read the schedule with appropriate concurrency control.
3. Check `state=ACTIVE`, version, and business eligibility.
4. Verify the timestamp complies with active rules/policies.
5. Insert an occurrence using the unique key.
6. If the occurrence already exists, **do not insert duplicate outbox entries**.
7. Insert one or more recipient notifications, each with a unique business key.
8. Commit the transaction.
9. Let mail workers pick up outbox entries and send separately.

PostgreSQL example:

```sql
INSERT INTO mail_schedule_occurrence (
    schedule_id, planned_fire_at, result
)
VALUES (
    :scheduleId, :plannedAt, 'MATERIALIZED'
)
ON CONFLICT (schedule_id, planned_fire_at)
DO NOTHING
RETURNING schedule_id;
```

If the query returns **no rows**, the occurrence was likely already materialized earlier. If it returns a row, the current transaction owns this creation and can insert the corresponding outbox records.

### Why create the occurrence and outbox in the same transaction?

Suppose:

```text
INSERT occurrence -> COMMIT
process crashes
INSERT outbox never happens
```

If the next run simply sees the occurrence exists and skips, the emails will never be created. Use the **same transaction** or a state machine capable of resuming incomplete materialization—never let a partial commit create a false "already processed" marker.

An illustrative transactional flow:

```text
BEGIN
  SELECT schedule FOR UPDATE
  IF inactive/stale: record skip per policy; COMMIT
  INSERT occurrence ON CONFLICT DO NOTHING RETURNING ...
  IF inserted:
      INSERT outbox for recipients
COMMIT
```

Never send SMTP inside this transaction. SMTP side effects cannot roll back with the database.

## 27. Java Service for Idempotent Occurrences

Example separating responsibilities:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.UUID;

@Service
public class ScheduleDispatchService {

    private final MailScheduleRepository schedules;
    private final MailOccurrenceRepository occurrences;
    private final MailOutboxRepository outbox;

    public ScheduleDispatchService(
            MailScheduleRepository schedules,
            MailOccurrenceRepository occurrences,
            MailOutboxRepository outbox
    ) {
        this.schedules = schedules;
        this.occurrences = occurrences;
        this.outbox = outbox;
    }

    @Transactional
    public void materializeOccurrence(
            UUID scheduleId,
            Instant plannedAt
    ) {
        MailSchedule schedule = schedules.lockById(scheduleId);

        if (!schedule.isActive()
                || !schedule.allowsFireAt(plannedAt)) {
            return;
        }

        boolean inserted = occurrences.insertIfAbsent(
                scheduleId, plannedAt
        );

        if (!inserted) {
            return; // duplicate logical firing
        }

        for (UUID recipientId : schedule.recipientIds()) {
            outbox.insertIfAbsent(
                    UUID.randomUUID(),
                    scheduleId,
                    plannedAt,
                    recipientId,
                    schedule.templateKey(),
                    schedule.templateVersion()
            );
        }
    }
}
```

`MailScheduleRepository`, `MailOccurrenceRepository`, `MailOutboxRepository`, and `MailSchedule` are **application-defined abstractions**, not built-in Spring/Quartz APIs. `insertIfAbsent` should rely on an **actual database unique constraint**, not just querying `exists` followed by `insert`.

### Transaction and exception notes

Depending on your persistence technology, a SQL uniqueness error can mark the transaction rollback-only. Using `ON CONFLICT DO NOTHING` or an equivalent operation with an explicit contract preserves atomicity much more cleanly than catching `DuplicateKeyException` and attempting to reuse the same transaction.

Materialization transactions must stay short. Never render large PDFs, call slow object storage, or send SMTP while holding a lock on the schedule row.

## 28. Is Planned Time Safe to Use as an Idempotency Key?

With Quartz, `context.getScheduledFireTime()` reflects the trigger's planned execution time under Quartz's model.

```java
Instant plannedAt =
        context.getScheduledFireTime().toInstant();
```

This value is useful when each firing maps 1-to-1 to a business occurrence. However, evaluate:

- A `fire-once-now` misfire may represent one catch-up run, **not the full history of missed timestamps**.
- Rescheduling or timezone updates can shift planned fire times.
- Recovery/job refires may have different semantics from regular firings.
- A business period like "October report" is not necessarily best identified by a trigger's UTC timestamp.

For monthly reports, a key like `scheduleId + periodYearMonth` may be more accurate. For one-shot reminders, `scheduleId + appointmentVersion` or an `occurrenceId` generated at registration time may fit better.

**Idempotency keys must represent the business event**, not blindly copy a timestamp without understanding how schedules change.

## 29. Reconciliation: Handling Missed Schedules Even When Quartz Recovers

Quartz manages trigger state and misfires, yet the application should still run a reconciliation job:

```text
Reconciliation worker
       |
       v
Scan eligible schedules / business periods
       |
       v
Compute expected logical occurrences
       |
       v
Compare with mail_schedule_occurrence
       |
       +-- Exists -> no-op
       |
       +-- Missing -> materialize idempotently
       |
       v
Outbox resumes sending
```

Suppose a mandatory report runs every business day, and the cluster is down for three days. Quartz misfire handling may deliver only one callback; reconciliation detects the **three unmaterialized business periods** and generates them within policy limits.

Reconciliation should:

- Bound its lookback window.
- Distinguish cancelled, paused, and stale schedules.
- Apply holiday calendars, DST, and business deadlines.
- Never create millions of occurrences in a single transaction.
- Enforce backpressure and SMTP quotas.
- Audit the backfill reason.

## 30. Cancelling a Schedule: Deleting the Quartz Trigger Is Not Enough

A cancellation API can:

1. Update `mail_schedule.state=CANCELED` in the business database.
2. Audit the actor and timestamp.
3. Call `quartz.unscheduleJob(triggerKey)` or `deleteJob(jobKey)` per contract.
4. Ensure that if a job still fires due to a race, it **checks state before materializing**.
5. Define how previously created outbox notifications are handled.

Simply deleting the trigger:

```text
Trigger already acquired by Quartz node A
User calls unschedule on node B
Node A executes job that was already acquired
```

does not necessarily stop work already in motion. **Business state in the database is the final authority.**

### What about cancelling emails already in the outbox?

Distinguish:

- Schedule cancelled before notifications were materialized.
- Notifications materialized and currently `PENDING`.
- Notifications currently `PROCESSING` or already accepted by the SMTP provider.

In the last state, the application **cannot recall an already-submitted SMTP email** by unscheduling Quartz. A cancellation policy can stop `PENDING` notifications, while `SUBMITTED` ones can only be logged and handled via downstream provider features if supported.

## 31. Safe Rescheduling

Quartz provides `rescheduleJob(TriggerKey, Trigger)` to swap a trigger by identity. Yet changing an email schedule also touches:

- Business schedule version.
- Already-materialized timestamps.
- Pending notifications.
- Business data/template snapshots.
- Races between the old trigger and the update.
- Audit trail of who rescheduled.

One workflow:

```text
User requests new date/time
       |
       v
Check version and authorization
       |
       v
Update business schedule (version++)
       |
       v
Reschedule Quartz trigger
       |
       v
Reconciliation verifies alignment
```

**The business database and Quartz JobStore may not commit in the same transaction**, depending on setup. If updating the business schedule succeeds and rescheduling Quartz fails, retry/reconcile—never leave "UI shows new schedule" while Quartz still fires the old trigger undetected.

An alternative is keeping the business schedule as source of truth and having an idempotent registrar worker sync Quartz. That way a transient Quartz failure never loses a reschedule intent.

## 32. Race Between Cancellation and Job.execute

Scenario:

```text
Worker A: reads schedule ACTIVE
User B: cancels schedule
Worker A: inserts outbox notification
```

If business rules require that **once cancelled commits, no further notifications are created**, use database concurrency control to establish a valid ordering.

For example:

- Materialization locks the schedule row with `SELECT ... FOR UPDATE`.
- The cancel API also updates the row with locking/version checks.
- If cancel commits first, materialization sees `CANCELED` and skips.
- If materialization commits first, notifications were created; the cancel API handles pending notifications per policy.

Never promise "clicking cancel guarantees the email was never sent" if a worker may already have started SMTP I/O.

## 33. Scheduling Emails With Attachments or Mutable Content

An email sending two months later can be affected by:

- Template updates.
- Adjusted prices or orders.
- Recipient address changes.
- Expiring attachment files.
- Expiring URL tokens.
- Changing mail permissions/consent.

Define a clear strategy:

| Data type | Recommended rule |
| --- | --- |
| Issued invoice details | Immutable snapshot/version |
| Upcoming appointment | Check latest state at materialization time |
| Marketing consent | Check eligibility right before submission |
| Reset/OTP token | Generate close to send time with valid TTL |
| Template | Store version or apply explicit latest-version policy |
| Attachment | Immutable storage key/version, verify existence |
| Recipient | Store recipient ID, resolve address per policy |

Never pre-serialize a `MimeMessage` containing a short-lived OTP and store it in Quartz `JobDataMap` for weeks. Separate schedule storage from content rendering so data follows proper lifecycles.

## 34. What Is an External Scheduler?

An **external scheduler** is a service or component running **outside the mail application process**. It stores schedules or fires timers, then invokes an endpoint, publishes a queue message, or launches a worker.

Common categories:

- **OS or job-server cron:** runs scripts/commands periodically.
- **Kubernetes CronJob:** spawns Kubernetes Jobs/Pods on a cluster cron schedule.
- **Cloud-managed scheduler:** cloud platform holds schedules and sends HTTP/queue events to targets.
- **Workflow orchestration engine:** executes durable workflows with timers/wait states.
- **Enterprise job scheduler:** centralized system with auditing, dependencies, RBAC, and operations.

Their common trait is that **schedules do not depend on a single mail app instance staying alive continuously**. Yet an external scheduler only fires according to its own rules; everything downstream remains the application's responsibility:

```text
External Scheduler
     |
     +-- HTTP request / Queue message / Batch job
     |
     v
Application Scheduler Receiver
     |
     v
Validate request + map schedule
     |
     v
Idempotent occurrence/outbox insert
     |
     v
Mail Worker -> JavaMailSender
```

**Never equate durable scheduling with a cron script on a single machine lacking backups and monitoring.** A schedule is only as durable as the scheduler's own storage/recovery and the target's retry handling.

## 35. An External Scheduler Typically Invokes Targets in Three Ways

### A. Calling an HTTP endpoint

```text
Cloud Scheduler
     |
     v
POST /internal/schedules/tick
     |
     v
Application creates due outbox notifications
```

Convenient when the app exposes HTTP APIs, but requires authentication, request integrity, timeouts, retry policies, and idempotency.

### B. Publishing a queue message

```text
Managed Scheduler
     |
     v
Message queue/topic
     |
     v
Worker consumer
     |
     v
Occurrence/outbox service
```

A durable queue decouples the scheduler from business processing time, though you must understand acknowledgments, at-least-once delivery, duplicates, and poison-message handling.

### C. Launching a batch worker

```text
Kubernetes CronJob
     |
     v
Pod runs "claim due schedules" command
     |
     v
Database transaction
     |
     v
Outbox rows
```

Useful when a periodic job only needs to scan the database and exit. Never let each batch pod attempt to send tens of thousands of emails synchronously without quotas/backpressure.

## 36. Do Not Create One Cloud Schedule per Email Without Checking Quotas

Two common patterns:

**Per-notification schedule**:

```text
Email 1 -> Schedule 1
Email 2 -> Schedule 2
...
Email 100000 -> Schedule 100000
```

**Shared tick + due-time database**:

```text
External scheduler calls every minute
             |
             v
      Application scans DB
             |
             v
       Due notifications
```

Per-notification schedules can fit when schedule counts are small, each needs its own lifecycle, and provider limits permit. At scale, check:

- Schedule count quotas per region/account.
- API rate limits on create/update/cancel.
- Storage and per-invocation costs.
- Timing precision/latency guaranteed by the platform.
- Minimum lead time between registration and firing.
- Retention and cancellation semantics.
- Recovery if creating the provider schedule succeeds but the app database commit fails.

The shared-tick model is usually simpler when the system already has a **notification table with `due_at` and an index**. The external scheduler merely ensures periodic scanning while the application database remains the schedule source of truth.

## 37. Using an External Tick to Trigger a Due-Time Scanner

An architecture:

```text
External Scheduler (e.g. every 1 minute)
                  |
                  v
       POST /internal/mail-schedules/tick
                  |
                  v
          Verify caller identity
                  |
                  v
        Dispatch due scanner task
                  |
                  v
     SELECT due schedules in batches
                  |
                  v
       Claim + materialize outbox
                  |
                  v
         Mail outbox workers
```

The endpoint should do minimal work: authenticate, validate the request, record a signal or trigger a short process, and return an acknowledgment. If scanning millions of schedules takes minutes, hand off to a durable worker/queue instead of holding the HTTP connection open.

### Illustrative endpoint in Spring Boot

```java
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/internal/mail-schedules")
public class MailScheduleTickController {

    private final SchedulerCallerVerifier verifier;
    private final DueScheduleDispatcher dispatcher;

    public MailScheduleTickController(
            SchedulerCallerVerifier verifier,
            DueScheduleDispatcher dispatcher
    ) {
        this.verifier = verifier;
        this.dispatcher = dispatcher;
    }

    @PostMapping("/tick")
    public ResponseEntity<Void> tick(
            @RequestHeader HttpHeaders headers,
            @RequestBody byte[] rawBody
    ) {
        // Authn/authz + request integrity per
        // the external scheduler's specific contract.
        verifier.verifyOrThrow(headers, rawBody);

        // Enqueue/persist a tick task or
        // trigger a worker with admission control.
        dispatcher.requestDueScan();

        return ResponseEntity.accepted().build();
    }
}
```

`SchedulerCallerVerifier` and `DueScheduleDispatcher` are **application-designed interfaces**. The code above does not authenticate automatically just because `verifyOrThrow` exists; implement it per the caller platform's docs, configure security filters, and ensure `requestDueScan()` persists/queues work before returning success.

### Choose HTTP status codes carefully

- If a request is rejected as unauthorized: never return `2xx`.
- If a durable work item was persisted: returning `202 Accepted` may fit the contract.
- If the database/queue cannot accept the tick: return an error so the scheduler can retry.
- If a tick is a duplicate: return success idempotently.
- If the provider requires a challenge/handshake: handle it per contract.

**Never return `202` and spawn a fire-and-forget thread without durable state**, as the process could die before the worker runs.

## 38. Securing External Scheduler Endpoints

An internal endpoint can be exposed to untrusted networks if firewall/routing rules are misconfigured. A forged request could trigger floods of notifications.

Mechanisms to consider:

1. Provider-issued identity tokens with verified audience and issuer.
2. mTLS between scheduler and target.
3. Raw-request HMAC/signature verification per contract.
4. Least-privilege service account/IAM allowed only to invoke the target.
5. Private network endpoints or allowlists as defense in depth.
6. Rate limits and request body size limits.
7. Replay protection via timestamps/nonces when supported by the protocol.
8. Auditing of scheduler callers and schedule scopes.
9. Never logging JWTs, OAuth tokens, HMAC secrets, or raw credentials.
10. Proper key rotation and expiration.

Never accept an arbitrary `scheduleId` over HTTP and execute it without verifying the caller is authorized for that schedule. If the endpoint is a shared tick, **do not let callers specify any recipient or schedule ID at all**; workers scan authorized rows directly in the database.

### Verify signatures against the exact raw bytes

When an external scheduler signs the HTTP body, verify the raw bytes using the exact canonical algorithm specified by the platform. Never parse JSON, reorder properties, and re-serialize before checking signatures if the provider signed the raw bytes.

## 39. External Schedulers Can Deliver Duplicates or Late Ticks

A managed scheduler may retry invocations when the target times out or returns errors. It may also introduce infrastructure jitter/delay.

```text
09:00:00  Scheduler sends tick T
09:00:03  Application writes outbox, but response lost
09:01:00  Scheduler retries tick T
09:01:05  Application receives same logical work again
```

If materialization uses a **unique business occurrence key**, repeated ticks become harmless no-ops for already-created notifications. If code instead does "receive tick => send SMTP immediately", retried requests can double-send.

Do not confuse "scheduler has retries" with "application has exactly-once execution". Make receivers/workers **idempotent** and audit logical occurrences.

### Timing precision

Infrastructure cron does not necessarily fire to the exact second; some platforms apply firing windows or jitter. If an SLA demands emails at 09:00:00 ± a few milliseconds, a pipeline involving databases, queues, template rendering, and external SMTP **cannot guarantee that precision** merely because the scheduler fired on time.

Define realistic SLOs: "notifications materialized within X minutes of due time", "p95 SMTP submission within Y minutes", and measure via timestamps.

## 40. Kubernetes CronJob: Useful, Not an Outbox

A Kubernetes CronJob can run every minute to invoke a batch worker:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: mail-schedule-tick
spec:
  schedule: "*/1 * * * *"
  concurrencyPolicy: Forbid
  startingDeadlineSeconds: 120
  successfulJobsHistoryLimit: 2
  failedJobsHistoryLimit: 2
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: tick
              image: example.internal/mail-schedule-worker:stable
              args: ["--mode=scan-due"]
```

This YAML is illustrative; image, RBAC, secrets, resources, `securityContext`, and database connectivity must match your real cluster.

Points to understand:

- `schedule` follows Kubernetes cron semantics.
- `concurrencyPolicy: Forbid` prevents some overlapping Jobs managed by that CronJob controller, **not cluster-wide database locks**.
- A controller may create jobs late or skip missed runs per policy.
- If a process finishes sending but fails to update status, a subsequent run can still reprocess it.
- If multiple distinct CronJobs scan the same table, per-CronJob `concurrencyPolicy` does not coordinate across them.
- Never assume CronJob guarantees at most one SMTP side effect per hour.

Depending on Kubernetes version and enabled features, CronJob may support `timeZone`. When omitted, cron runs in the controller/cluster timezone; avoid relying on defaults for recipient-timezone sends. For per-user schedules across timezones, let the business DB plan individual occurrences.

## 41. CronJob Forbid and Replace Do Not Replace Transactions/Idempotency

`concurrencyPolicy` typically offers `Allow`, `Forbid`, and `Replace`:

| Policy | Meaning at Kubernetes Job level | Email risk |
| --- | --- | --- |
| Allow | Multiple job instances may overlap | Requires DB claiming to prevent duplicate processing |
| Forbid | Prevents overlap within that CronJob | Skipped runs may need backfill |
| Replace | Terminates old job and starts a new one | Stopping mid-SMTP I/O can leave UNKNOWN outcomes |

**Never use `Replace` on critical mail workers without handling ambiguous states.** Killing a pod after the server received DATA but before `SUBMITTED` is saved can cause the next run to resend the same notification.

## 42. Cloud Schedulers and Message Queues

An external scheduler can emit a compact event:

```json
{
  "eventType": "MAIL_DUE_SCAN",
  "triggerId": "scheduler-tick-demo-001",
  "scheduledFor": "2026-12-05T02:00:00Z"
}
```

This is an **application-defined example payload**, not a universal schema of a specific cloud service. Providers have their own event envelopes, IDs, and retry policies.

Consumers should:

1. Authenticate the queue/topic source via IAM.
2. Parse/validate schema version.
3. Persist or apply an appropriate idempotency key.
4. Scan due schedules using transactions/claims.
5. Acknowledge the queue message **only after durable processing at the required boundary**.
6. Apply defined retry/DLQ policies on failure.

If the scanner uses the message solely as a "signal to scan the DB", duplicate ticks are generally safe when DB claims/idempotency are solid. That is a major advantage of shared ticks over stuffing recipients/attachments into scheduler messages.

## 43. Using a Database Scanner Without Quartz

If all schedules are one-shot or already materialized with `due_at` in the application database, Quartz may be unnecessary.

```text
mail_notification:
  id, due_at, status, recipient_id, payload_reference

Worker:
  poll eligible due rows
  claim rows safely
  process each notification
  update outcome
```

A typical PostgreSQL query:

```sql
SELECT notification_id
FROM mail_notification
WHERE status = 'PENDING'
  AND due_at <= now()
ORDER BY due_at, notification_id
FOR UPDATE SKIP LOCKED
LIMIT 100;
```

**This is only the row-selection step inside a transaction**, not a full worker. You must update claim state/leases **before committing** so other workers do not re-select them, then handle SMTP outside the transaction.

If you do:

```text
SELECT ... FOR UPDATE SKIP LOCKED
COMMIT
send SMTP
UPDATE status
```

without persisting a claim before commit, the lock vanishes on commit and another worker can pick the same row. You need a `PENDING -> PROCESSING` state machine, lease tokens, owners, and timeout/reclaim rules.

### Index supporting due scans

```sql
CREATE INDEX ix_mail_notification_due
    ON mail_notification (due_at, notification_id)
    WHERE status = 'PENDING';
```

The index helps workers locate due work as the table grows. Depending on database and workload, you may need partitioning/retention or tenant/priority indexes. Never full-scan a table every second with millions of notifications.

## 44. Database Claim/Lease Mechanisms

A worker picks `notificationId` and updates:

```text
status       = PROCESSING
claimed_by   = worker-17
lease_until  = now + configuredDuration
attempt_id   = UUID
```

After committing, the worker sends via SMTP and persists the outcome in a separate transaction. If the worker crashes, a reconciler finds expired leases.

However, a lease timeout **does not prove SMTP was never submitted**. When a worker disappears after DATA, recovery can encounter an `UNKNOWN` outcome. Therefore:

- Persist `attemptId` before SMTP I/O.
- Record stage/evidence accurately.
- Never auto-resend without an explicit policy for duplicate risk.
- Separate notification state from attempt state.
- If the provider offers query APIs, reconcile using the correlation ID.

Claim/lease solves **concurrent workers**, not **exactly-once SMTP side effects** by itself.

## 45. Quartz vs. Database Scanner: When to Choose Which?

**Quartz JDBC** is worth considering when:

- You have many dynamic cron rules with independent lifecycles.
- You want built-in triggers, calendars, misfire handling, and clustering.
- Your team can administer the Quartz schema and DB contention.
- Schedule counts fit storage and operational capacity.

**A DB due scanner** can be simpler when:

- Every notification already has an explicit `due_at`.
- One-shot record volume is very high.
- Tight alignment between idempotency, state machine, and business logic is needed.
- A shared tick or `@Scheduled` only needs to "wake" workers.
- Individual records do not require complex cron expressions.

Both can be combined: **Quartz manages cron/one-shot triggers while the application database manages occurrences and the outbox**. Avoid keeping two unsynchronized schedule sources without reconciliation.

## 46. When Should You Use a Workflow Engine?

A business sequence:

```text
Payment failed
   |
   v
Wait 1 day
   |
   +-- payment recovered? -> cancel reminder
   |
   v
Send reminder 1
   |
   v
Wait 3 days
   |
   +-- payment recovered? -> stop
   |
   v
Send reminder 2
```

This is not merely a cron job; it is a **stateful workflow with timers and cancellation conditions**. A durable workflow engine may fit better than Quartz when each workflow instance involves multiple steps, signals, timeouts, and recovery logic.

Even when the engine retries activities automatically, **SMTP sending remains an external side effect**. Any activity can re-run after failures; you still need an outbox/idempotency and outcome tracking just as with Quartz.

Do not adopt a heavy workflow engine just to send a 09:00 report if Quartz or a due scanner suffices.

## 47. Email Provider "Send Later" Features

Some email providers offer an API to **schedule sends** or "send at" directly on their platform. In that setup:

```text
Application
    |
    +-- Submit message + desired send time
    |
    v
Provider queue holds future send
    |
    v
Provider submits at scheduled time
    |
    v
Recipient mail server
```

Potential benefits:

- No need to operate Quartz per email.
- Provider infrastructure holds schedules under its own contract.
- APIs may support cancellation or status inspection.

However, verify:

- Maximum scheduling horizon.
- Release timing accuracy.
- Scheduled message quotas.
- Pricing and message size limits.
- How edits/cancellations work after scheduling.
- Ability to retrieve provider IDs or delivery events.
- Policy if a user unsubscribes between scheduling and send time.
- Ability to fail over providers without duplicating schedules.

Do not assume SMTP `JavaMailSender` has a standard `sendAt(...)` method across all providers. Scheduling features are typically **provider-specific APIs** or application-built.

### When should schedules stay inside the application?

If sends depend on changing business state (user cancels appointment, invoice adjusted, consent withdrawn), storing schedules in the application database lets you evaluate final eligibility cleanly. A provider scheduler can still be used, but you must synchronize cancels/updates and handle delivery events per contract.

## 48. Scheduler Firing Differs From SMTP Submission Differs From Delivery

Three states must stay distinct:

```text
SCHEDULED
    |
    v
OCCURRENCE_MATERIALIZED
    |
    v
OUTBOX_PENDING
    |
    v
SMTP_SUBMITTED
    |
    v
REMOTE_DELIVERED / BOUNCED / DEFERRED (if feedback exists)
```

A successful Quartz Job only proves the job **finished its assigned task**. If that task is inserting an outbox row, it does not prove SMTP was called. An HTTP scheduler receiving `202 Accepted` likewise does not prove the email was sent.

### Example state timeline of an occurrence

| Milestone | Data | What is confirmed |
| --- | --- | --- |
| 09:00 | Quartz trigger fired | Scheduler attempted to run job |
| 09:00:02 | Occurrence inserted | Business occurrence materialized |
| 09:00:03 | Outbox committed | Notification request durable |
| 09:01:10 | SMTP transport returns success | Message submitted to provider/relay |
| 09:01:45 | Provider delivers to receiving MTA | Remote delivery evidence, if available |

Never set `email_delivered=true` at 09:00:02 or 09:01:10 if the product defines delivery as reaching the mailbox server.

## 49. Sending Emails From the Outbox Worker

A worker can load a due notification and build the email:

```java
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import jakarta.mail.internet.MimeMessage;

public final class ScheduledMailSubmitter {

    private final JavaMailSender sender;
    private final NotificationRepository repository;
    private final MailContentRenderer renderer;

    public ScheduledMailSubmitter(
            JavaMailSender sender,
            NotificationRepository repository,
            MailContentRenderer renderer
    ) {
        this.sender = sender;
        this.repository = repository;
        this.renderer = renderer;
    }

    public void submit(UUID notificationId) throws Exception {
        NotificationWork work =
                repository.loadClaimedWork(notificationId);

        RenderedMail content = renderer.render(work);

        MimeMessage message = sender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom("notify@example.org");
        helper.setTo(work.recipientEmail());
        helper.setSubject(content.subject());
        helper.setText(
                content.plainText(),
                content.safeHtml()
        );

        // Business policy/recipient eligibility checked
        // before sending and attempt persisted separately.
        sender.send(message);
    }
}
```

`NotificationRepository`, `NotificationWork`, `MailContentRenderer`, and `RenderedMail` are application-defined components. This abbreviated code illustrates only the **compose -> SMTP send** boundary; a real system must persist attempts, classify errors, record outcomes, enforce recipient policies, clean up resources, and apply timeouts.

Never send inside a `@Transactional` method spanning from loading the notification through the SMTP response. Use short transactions for claiming and recording outcomes so database locks are never held across network I/O.

## 50. Should Quartz Automatically Retry SMTP Errors?

Quartz has job-execution failure handling and refire options via `JobExecutionException`, but **you should not use that mechanism to replace a mail retry policy**.

For example, a Quartz job calling SMTP directly and throwing `JobExecutionException` may refire per configuration. Problems:

- Network errors after DATA can leave an `UNKNOWN` outcome.
- Recipients already accepted by the server may get duplicate emails.
- A multi-recipient `MimeMessage` can partially succeed.
- Rapid retries inside the Quartz thread pool can starve workers.
- Data/attachments may expire between tries.

Instead of "refire immediately on any SMTP exception":

1. Materialize the outbox from Quartz.
2. Let mail workers classify submission outcomes.
3. Retry only policy-permitted failures.
4. Persist `attemptId` and next retry time.
5. Enforce rate limiting/backoff outside the main Quartz schedule.

### An illustrative retry policy

| Error | Potentially appropriate policy |
| --- | --- |
| Cannot connect prior to SMTP submission | Bounded retry with backoff |
| Temporary SMTP `450` before DATA | Retry per code/stage |
| Permanent SMTP `550` recipient error | Do not retry blindly; fix data or suppress |
| Invalid authentication/permissions | Alert/reconfigure; do not hammer retries |
| Timeout after end-of-DATA marker | `UNKNOWN`, reconcile before resending if possible |
| Provider status `DEFERRED` | Wait for provider lifecycle per contract |
| Attachment no longer exists | Fail/rebuild from immutable data per policy |
| Schedule cancelled | Do not create new notifications; handle pending ones per policy |

**Never assume every SMTP exception guarantees the message was not sent.**

## 51. Backoff Must Not Block Quartz Scheduler Threads

An anti-pattern:

```java
public void execute(JobExecutionContext context) {
    while (true) {
        try {
            sender.send(message);
            return;
        } catch (Exception ex) {
            Thread.sleep(60000);
        }
    }
}
```

In this example, the job holds a Quartz worker thread across repeated sleeps, lacks max attempts, lacks error classification, persists no durable retry state, and risks duplicate sends.

Better design:

```text
Attempt failed at 09:00
      |
      v
Persist RETRY_WAIT + nextAttemptAt = 09:05
      |
      v
Release worker/thread
      |
      v
Future due scan claims it at 09:05
```

Use `next_attempt_at` in the database and a poller/outbox scheduler instead of sleeping in a Java thread. If a queue provides delayed-message features, you can use them as an implementation mechanism while still keeping durable attempt state and idempotency.

## 52. Cron Jobs and High-Volume Email Campaigns

A cron trigger can mean "start campaign at 09:00". It **does not mean** sending all 200,000 emails immediately inside one `Job.execute`.

```text
09:00 Quartz fire
      |
      v
Create campaign occurrence
      |
      v
Materialize recipients in bounded batches
      |
      v
Durable outbox queue
      |
      +-- Worker 1
      +-- Worker 2
      +-- Worker 3
      |
      v
SMTP/API rate limits and backpressure
```

Limits to define:

- Recipients per batch.
- Average and maximum MIME sizes.
- SMTP account/provider quotas.
- Connection/worker counts.
- Memory/CPU/disk/bandwidth limits.
- Recipient consent/suppression at send time.
- Maximum acceptable lag from schedule to submission.

A scheduler thread should only enqueue/claim in bounded increments, never hold a massive campaign hostage until completion.

## 53. A Durable Queue Does Not Equal Exactly-Once Sending

With an outbox or message broker:

```text
Consumer reads notification
       |
       v
SMTP accepts message
       |
       v
Process crashes before ack
       |
       v
Broker redelivers notification
```

This duplicate window exists even when both the schedule and queue are durable.

You need:

- Single-owner claiming per notification.
- An `attemptId` persisted before SMTP.
- `PROCESSING/SUBMITTED/UNKNOWN` states.
- Controlled leases, reclaims, and reconciliation.
- No automatic resending when the outcome is uncertain.
- Provider-specific idempotency APIs when supported and properly scoped.

Never rely on the `Message-ID` header assuming SMTP relays deduplicate automatically. Standard SMTP provides no universal exactly-once delivery contract.

## 54. Test 1: Are Jobs and Triggers Persisted Across Restarts?

A key integration test must use **JDBC JobStore**, not RAMJobStore:

1. Create test Quartz schema in PostgreSQL or a supported database.
2. Start scheduler instance A with JDBC JobStore.
3. Register a `JobDetail` and trigger scheduled to fire in the future.
4. Shut down instance A before `plannedAt`.
5. Start scheduler instance B pointing to the same database with matching cluster/instance identity.
6. Wait until fire time using a bounded-timeout condition.
7. Verify the occurrence/outbox was created under the business key.
8. No real email sending required.

This proves Quartz persistence/recovery of the **schedule** and application occurrence materialization across restarts within the tested scenario.

### Do not call a RAMJobStore test a restart persistence test

If a test spins up a new scheduler with RAMJobStore and re-registers all triggers from code, events may still fire. That does not prove **Quartz persisted state** across restarts; it only tests application bootstrap logic.

Both test types have distinct goals and should be named accurately.

## 55. Test 2: Two Scheduler Nodes Sharing a Database

A cluster test:

```text
Quartz node A ----+
                  |
                  +---- Shared QRTZ tables
                  |
Quartz node B ----+
                  |
                  v
             One planned firing
                  |
                  v
         Idempotent occurrence insert
```

Goals:

- Both nodes share the same job/trigger state.
- Both nodes have distinct instance IDs in the same logical cluster.
- One logical occurrence creates one occurrence row and one set of outbox notifications.
- If recovery or duplicate invocation happens, database idempotency still blocks duplicate notifications.

Never conclude from one happy-path test that a cluster can never invoke a job twice under any failure mode.

## 56. Test 3: Misfire While Scheduler Is Down

Scenario:

```text
09:00 planned fire
08:55 scheduler stopped
09:20 scheduler started again
```

Test both policies:

**A. `DoNothing`** — for reports with no value once missed:

- Does not create a catch-up notification at 09:20.
- Future scheduled firings still work.
- Emits metrics/audits for missed triggers if required by business rules.

**B. `FireAndProceed`** — for notifications that should catch up once:

- Scheduler restarts and triggers once as expected.
- Business service verifies the schedule is still active and the occurrence is eligible.
- Database creates no duplicates on repeated invocations.
- Does not falsely claim every missed historical firing was replayed.

If every missed day needs backfilling, add tests for business reconciliation creating each missing `businessPeriod`.

## 57. Test 4: Invoking the Same Occurrence ID Twice

Real Quartz is not needed to test idempotency:

```java
UUID scheduleId = fixedScheduleId();
Instant plannedAt =
        Instant.parse("2026-12-05T02:00:00Z");

dispatchService.materializeOccurrence(
        scheduleId, plannedAt);
dispatchService.materializeOccurrence(
        scheduleId, plannedAt);

assertEquals(
        1,
        occurrenceRepository.countByScheduleAndTime(
                scheduleId, plannedAt)
);
assertEquals(
        expectedRecipients,
        outboxRepository.countByScheduleAndTime(
                scheduleId, plannedAt)
);
```

Repositories and helpers are assumed in this test. For concurrency testing, run two parallel transactions against a real database with unique constraints; sequential unit-test calls cannot prove race safety.

## 58. Test 5: Timezones and DST

Cases to cover:

| Scenario | What to verify |
| --- | --- |
| One-shot in Vietnam timezone | UTC instant matches local time |
| Cron 09:00 in Europe/Berlin | Occurrences around DST transitions follow policy |
| Nonexistent local time | Skipped/shifted per policy |
| Repeated local time | Does not send two emails if business wants once/day |
| User changes timezone | Updated schedule or version matches requirements |
| JVM default timezone changes | Job still uses persisted zone |
| Invalid timezone ID | Validation fails instead of silent fallback |
| One-shot in the past | Rejected or handled per misfire/stale policy |

To test `CronTrigger`, use APIs computing `nextFireTime` and compare specific timestamps against expected local dates/zones instead of sleeping until a real DST day.

## 59. Test 6: Cancelling Right Around Fire Time

A concurrency test can run two threads/transactions:

```text
Thread A: claims schedule/starts materialization
Thread B: cancels schedule
Thread A: attempts to insert outbox
```

Requirements:

- A valid commit ordering is enforced.
- If cancellation commits before materialization, no new outbox entries are created.
- If materialization commits before cancellation, cancellation policy handles the pending outbox entries.
- Cannot promise recall of emails already sent via SMTP.
- Audit trail records when cancellation took effect.

In tests, use latches/barriers to control timing instead of arbitrary `Thread.sleep` calls. Assert on database state, not just mock invocation counts.

## 60. Test 7: External Scheduler Sending Duplicate Ticks

An external scheduler sends the same logical tick twice:

```text
POST tick-100 -> 202 Accepted
POST tick-100 -> 202 Accepted
```

Expectations:

- Endpoint authenticates both requests.
- Tick is accepted idempotently.
- Scanner may rerun without creating duplicate occurrences/outbox rows in the database.
- Duplicate ticks never cause duplicate SMTP attempts.
- If a callback fails before durable acknowledgment, the provider can retry per contract.

With shared due scans, a second tick may run concurrently with the first; database claims/unique keys are required for safety, not just request-ID deduplication.

## 61. Test 8: SMTP Failures After Schedule Fires

Scenario:

1. Quartz Job fires and materializes the outbox successfully.
2. Worker sends the message to an SMTP test server.
3. Server returns `450` or drops the connection before receiving DATA.
4. Attempt records `RETRY_WAIT` if policy allows.
5. Still only **one** schedule occurrence exists.
6. Retry submission generates a **new attempt**, not a new occurrence.

Another test simulates SMTP receiving DATA and losing the final reply. Expect `UNKNOWN` recorded with no blind retry; the schedule must not be mislabeled as failed/missing.

This confirms **job scheduling retries** are distinct from **email submission retries**.

## 62. Test 9: Does a Cron Trigger Backfill Completely?

Suppose the business requires sending a report for every business day, and the system is down from Monday to Wednesday.

Using only Quartz cron "fire once now" may give one execution upon recovery, whereas the business expects three separate reports.

Tests must verify:

1. Which days belong in `expectedBusinessPeriods`.
2. Each day has a distinct `occurrenceKey`.
3. Reconciliation creates missing non-expired periods.
4. Two occurrences are never created for the same day even if Quartz also fires late.
5. Concurrent backfill volume is bounded.
6. Audits and notification statuses exist for each day.

Do not name a test `replaysAllMissedCronTriggers()` if the implementation only uses `fire-once-now` misfire handling. Full replay requires an explicit **backfill plan**.

## 63. Test 10: External Scheduler Infrastructure Is Down

With shared ticks + database:

```text
09:00 tick not delivered
09:01 tick not delivered
09:02 tick delivered
       |
       v
Scanner finds every eligible due record <= current time
       |
       v
Materializes missing outbox with idempotency
```

The key is that **the scanner queries `due_at <= now()`**, not `due_at == exactly 09:02`. Thus a missed tick never permanently drops due notifications.

If too much work piles up, workers process in bounded batches with priorities, retries, and backpressure rather than opening one massive transaction. For overdue notifications, still apply stale/eligibility policies.

## 64. SLOs: How Should "On Time" Be Measured?

A scheduled email has at least four timestamps:

| Timestamp | Meaning |
| --- | --- |
| `planned_at` | Target business execution time |
| `materialized_at` | Time occurrence/outbox was created |
| `smtp_submitted_at` | Time SMTP transport returned accepted |
| `remote_delivered_at` | Time provider reported remote delivery, if available |

From these:

```text
Scheduling lateness
  = materialized_at - planned_at

Submission delay
  = smtp_submitted_at - materialized_at

End-to-end submission lateness
  = smtp_submitted_at - planned_at

Remote delivery latency
  = remote_delivered_at - smtp_submitted_at
```

**Never compute remote delivery latency as 0 when provider feedback is absent.** That creates artificially flattering metrics.

Example business SLO:

> 99% of eligible transactional notifications with valid due times are **materialized within 2 minutes** of planned time; 95% are **SMTP submitted within 5 minutes** of planned time.

Both numbers are **illustrative examples**, not universal standards. Choose thresholds based on notification criticality, SMTP capacity, and acceptable retry windows.

## 65. Key Metrics for Quartz

| Suggested metric | Unit | What it reflects |
| --- | --- | --- |
| `mail.schedule.active` | schedules | Number of currently active schedules |
| `mail.schedule.misfires` | count | Trigger misfires observed by source |
| `mail.schedule.job.failures` | count | Errors during occurrence materialization |
| `mail.schedule.fire.lag` | seconds | Lag between planned and actual start |
| `mail.schedule.materialize.duration` | milliseconds | Duration of occurrence/outbox transaction |
| `mail.schedule.occurrence.duplicates` | count | Duplicate invocations blocked by idempotency |
| `mail.outbox.pending` | notifications | Work waiting for submission |
| `mail.outbox.oldest.age` | seconds | Age of the oldest waiting request |
| `mail.smtp.submission.duration` | milliseconds | Time spent in SMTP sender |
| `mail.smtp.submitted` | count | Attempts observed as accepted |
| `mail.smtp.unknown` | count | Attempts with ambiguous outcomes |

These are **application-definable metric names**, not all built-in Quartz/Spring metrics. If using Micrometer/Actuator, verify your versions and each component's observation configuration.

### Protecting metric labels

Allow a bounded set of labels:

- `schedule_type`: once/cron.
- `scheduler_backend`: quartz/external/db-poll.
- `result`: materialized/skipped/duplicate/error.
- `provider_route`: configured allowlist value.
- `message_class`: transactional/bulk.

Never put `recipientEmail`, subjects, attachment filenames, millions of raw user `scheduleId` values, or tokens into metric labels. High cardinality strains monitoring and risks leaking data.

## 66. Logging and Auditing

A clean structured log:

```text
event=scheduled_mail_occurrence
scheduleId=S-416-001
occurrenceId=O-416-20261205
plannedAt=2026-12-05T02:00:00Z
actualStartAt=2026-12-05T02:00:03Z
policy=FIRE_IF_ELIGIBLE
materializationResult=CREATED
outboxCount=3
```

Never log:

- Full To/Cc/Bcc recipients.
- OTPs, reset tokens, magic links.
- Raw `MimeMessage` or attachments.
- SMTP passwords, cloud scheduler tokens.
- Entire `JobDataMap` if it could hold unsafe data.

Audits should answer:

1. Who created/edited/cancelled the schedule?
2. Which rule/zone/version applied at materialization time?
3. Which occurrences were skipped as stale or cancelled?
4. Who or what mechanism requested a backfill?
5. How many notifications were materialized?
6. Which SMTP attempts belong to each notification?

Never use scheduler logs to infer remote delivery without provider feedback.

## 67. Three-Layer Dashboard

### A. Scheduler health

```text
Quartz nodes / external scheduler heartbeat
  - active nodes
  - due triggers
  - misfires and fire lag
  - job execution failures
  - DB latency / lock contention
```

### B. Occurrence/outbox health

```text
Business schedule materialization
  - expected vs created occurrences
  - duplicate prevented
  - canceled/stale skipped
  - outbox pending and age
  - dispatch throughput
```

### C. Mail transport health

```text
SMTP workers
  - submission success/failure/UNKNOWN
  - retries and backoff
  - provider throttling
  - remote delivery events (when available)
```

If a dashboard only displays "Quartz Job SUCCESS", operators can miss that the outbox is backed up or the SMTP provider is rejecting every email.

## 68. Alerts Driven by Real Failures

Examples:

| Condition | What to investigate |
| --- | --- |
| Missing scheduler heartbeat | Scheduler may be down |
| Rising p95 fire lag | DB locks, insufficient workers, cluster issues |
| Spike in misfires | Downtime/overload or threshold settings |
| Rising outbox pending age | Mail workers stalled or SMTP throttling |
| Continuous materialization failures | DB/schema/data/business validation errors |
| Surge in duplicate insert attempts | Trigger retries/recovery/misconfiguration |
| Rising UNKNOWN SMTP attempts | Network interruptions, timeouts |
| Rising recipient suppressions | List quality or provider feedback |

Do not auto-restart the scheduler repeatedly just because one cron job failed on bad recipient data. Separate **scheduling infrastructure**, **business content errors**, and **SMTP errors**.

## 69. Runbook When Schedules Fail to Run

**Step 1 — Verify schedule state.**

- Is the schedule `ACTIVE`?
- Was it cancelled, paused, or expired?
- Are the cron rule and zone valid?
- Does the trigger still exist in Quartz JobStore?

**Step 2 — Inspect planned fire time.**

- Does `nextFireTime` match the expected schedule?
- Was it affected by DST or a default timezone?
- Did a misfire occur with a skip policy?
- Was the schedule recently edited?

**Step 3 — Check scheduler runtime.**

- Is the instance started?
- Are JDBC connections and Quartz tables available?
- Do cluster nodes have unique instance IDs and shared config?
- Is the Quartz thread pool blocked by slow jobs?
- Have database locks/latency spiked?

**Step 4 — Check materialization.**

- Was the occurrence inserted?
- Was it deduplicated by an existing key?
- Was the schedule active/eligible when the job ran?
- Are records present in the outbox?

**Step 5 — Check mail workers.**

- Are outbox records being claimed?
- Are there template, attachment, or recipient-policy errors?
- Was SMTP submitted?
- Are there unknown outcomes or provider throttling?

**Step 6 — Decide on backfill.**

- Is catch-up sending permitted?
- Has the occurrence expired?
- Are duplicates blocked by unique keys?
- What batch size and route should backfills use?
- Are quota and auditing in place?

Avoid "quick fixes" that create a new trigger to send immediately without checking whether occurrences/outbox rows already exist; that can create duplicates.

## 70. Runbook When Duplicate Emails Are Sent

When a customer reports receiving two copies of the same notification:

1. Find the `notificationId`, do not compare Subjects alone.
2. Check whether there are two **business occurrences** or one occurrence with two attempts.
3. If two occurrences: check schedule keys, versions, misfires/backfills, and unique constraints.
4. If one occurrence: check outbox claims, lease timeouts, and broker redeliveries.
5. Inspect SMTP failure stages, especially lost replies after DATA.
6. Check whether provider failover resent an `UNKNOWN` attempt.
7. Check whether retry logic or workers had two concurrent owners.
8. If the provider supplies delivered events, use them as supporting evidence without assuming event counts equal visible emails.
9. Add safeguards against resending in future policies.

Never "fix" duplicates by deleting all retries. Temporary failures need retries; the real goal is **retrying the right entities in the right states**.

## 71. Runbook When Quartz Jobs Disappear After Deployment

Common causes:

- Running `RAMJobStore` instead of JDBC persistence.
- Production startup ran a schema reset.
- Pointed at a different database/schema/`tablePrefix` after deploy.
- Bootstrap code deletes and re-registers jobs from static defaults.
- Cluster configuration/`instanceName` changed.
- Job/trigger identities changed due to bean/class renames or tenant ID changes.
- Migrations were not applied properly.

How to investigate:

1. Verify which `JobStore` the scheduler actually uses.
2. Inspect `QRTZ` tables for expected job/trigger records.
3. Check migration logs and JDBC URL.
4. Verify business schedules still exist in the source of truth.
5. Run an idempotent registrar/reconciliation to resync triggers.

Never wipe all Quartz tables to "start fresh" if they hold user schedules.

## 72. Multi-Tenant and Access Control Considerations

When multiple tenants share one scheduler:

- Every schedule must have an owner/tenant scope.
- Edit/cancel APIs must act only on authorized schedules.
- Idempotency keys must never collide across tenants.
- `JobKey`/group names should follow bounded naming conventions.
- Database queries/worker claims must enforce data isolation.
- Enforce per-tenant quotas on schedule counts and firing frequency.
- Enforce email rate limits per tenant/provider.
- Prevent one tenant from creating a per-second cron that starves others.
- Never embed tenant secrets in `JobDataMap`.

For multi-tenant workers, enforce tenant context **at claim and data-load time**—never trust an unauthenticated caller header.

### Quotas and fairness

One tenant creating 100,000 triggers at 09:00 can occupy scheduler threads and delay other tenants. Bounding schedules and batching by tenant/priority keeps the system fair. Quartz thread pool size is only one lever; outbox pacing and SMTP quotas must also be designed.

## 73. Security of Quartz JobStore

JDBC JobStore stores `JobDataMap` and schedule metadata, which may touch business data.

Recommendations:

- Store only opaque IDs and necessary scalar values in `JobDataMap`.
- Use a least-privilege database user for Quartz tables.
- Avoid unnecessarily sharing production DB credentials.
- Enable encryption at rest and backup protections per policy.
- Do not share Quartz tables across untrusted teams.
- Restrict read access to schedules and correlation identifiers.
- Review all Quartz migrations because they can affect every schedule.
- Never print secrets or raw job data in scheduler error messages.

If multiple applications share cluster tables, define a clear ownership model; any node permitted to update trigger state can affect cluster schedules.

## 74. Operational Cost of Quartz vs. External Schedulers

| Factor | Embedded Quartz JDBC | External scheduler |
| --- | --- | --- |
| Schedule management | App actively manages DB/Quartz | Partially managed by scheduler platform |
| Database infrastructure | Requires Quartz schema, backups, migrations | May skip Quartz DB, still needs business store |
| Clustering/failover | App configures and operates Quartz nodes | Depends on platform SLO/contract |
| Dynamic per-user schedules | Supported, requires scale control | Depends on provider schedule quotas/APIs |
| Simple periodic schedules | Works well | Often convenient |
| Cron/timezone/misfire | Quartz features + business policy | Service-dependent, must verify |
| Trigger delivery | In-process/app cluster | HTTP, queue, or batch invocation |
| Security | DB permissions, app auth | IAM/signatures/network policies |
| Exactly-once SMTP side effect | Not guaranteed automatically | Also not guaranteed automatically |
| Lock-in | Quartz APIs/schema | Cloud/provider platform APIs |
| Observability | App integrates metrics itself | Platform provides logs/metrics; still need app outcomes |

Do not compare only per-invocation pricing. Total cost includes DB storage, operations, monitoring, backups, API quotas, incidents, and reconciliation complexity.

## 75. Decision Guide for Three Scenarios

### Scenario A: one million one-shot notifications with `due_at`

If the database already stores every `notification.due_at`, a due scanner + durable outbox is usually simpler and scales more cleanly than creating one Quartz `JobDetail` per notification, depending on workload. Quartz can still manage a single shared tick/trigger job.

### Scenario B: each organization has its own weekly report cron in its own timezone

Quartz JDBC JobStore with a dedicated `CronTrigger` per schedule fits well, especially when dynamic pause/resume, cron calendars, and clustering are needed. Add timezone/DST validation, idempotent occurrences, and schedule limits.

### Scenario C: multi-step email sequence tied to contract state

A workflow engine or stateful outbox machine with timers often fits better than a standalone cron trigger, since waiting, cancellation, and branching are core parts of the business process.

These are design guidelines, not performance conclusions without knowing schedule volume, frequency, database profile, and SLAs.

## 76. Registering Schedules via API: Validate Before Writing

A schedule-creation API typically receives:

```json
{
  "scheduleType": "CRON",
  "cronExpression": "0 0 9 ? * MON-FRI",
  "zoneId": "Asia/Ho_Chi_Minh",
  "templateKey": "weekly-summary",
  "recipientGroupId": "group-demo-01"
}
```

This payload is a **business contract example**, not a built-in Quartz configuration. Before persisting:

1. Authenticate the user and verify authorization on `recipientGroupId`.
2. Verify `scheduleType` is supported.
3. Parse the cron expression using Quartz syntax—never rely on homegrown regexes alone.
4. Validate `ZoneId.of(...)` and DST policies.
5. Compute several upcoming `nextFireTimes` to catch invalid or overly dense schedules.
6. Check schedule count quotas, frequency limits, and tenant rate limits.
7. Verify the template exists, is permitted, and follows versioning policy.
8. Decide whether past one-shot schedules are rejected.
9. Set optimistic version and create-API idempotency key.
10. Write audit logs and schedule Quartz registration post-commit or via a retryable registrar.

### Syntactically valid cron that violates business rules

A "every second" cron is valid Quartz syntax but breaches SMTP quotas or a "weekly report" intent. Enforce **frequency validation**, not just `CronExpression.isValidExpression(...)`.

Example:

```java
import org.quartz.CronExpression;

String cron = "0 0 9 ? * MON-FRI";
if (!CronExpression.isValidExpression(cron)) {
    throw new IllegalArgumentException(
            "Cron expression is invalid"
    );
}

ZoneId zoneId = ZoneId.of(requestedZoneId);
```

Validating against "overly dense schedules" can compute upcoming fire times over an observation window, cap expected events, and reject per policy. Never try to infer exact frequency by counting `*` characters.

## 77. Never Let Quartz Registration and the Business DB Drift Out of Sync

A scenario:

```text
Application saves mail_schedule ACTIVE
     |
     v
Quartz scheduleJob(...) fails due to DB outage
     |
     v
Business DB says ACTIVE, but no Quartz trigger
```

If both stores do not share a guaranteed single transaction, implement synchronization:

- `mail_schedule.registration_status`: `PENDING/REGISTERED/ERROR`.
- An idempotent registrar worker.
- Comparison of schedule versions and trigger keys.
- Reconciliation of active schedules missing triggers.
- Alerts if registration lag exceeds SLA.
- Never delete a business schedule on a transient Quartz error if the user was already told it was accepted.

Conversely, a trigger may get created while the business commit fails. When a job fires, it must verify the business schedule exists and is active; a separate reconciliation pass can clean up orphan triggers once proven.

**The source of truth must be unambiguous:** if users edit schedules in the app UI, the business DB should normally be primary, with Quartz JobStore acting as a synchronized runtime execution projection.

## 78. Never Turn a Quartz Job Into One Giant Transaction

One job doing everything:

```text
Load 50,000 recipients
Render 50,000 PDFs
Send 50,000 emails
Commit one giant transaction
```

causes severe problems:

- Quartz worker threads stay tied up for tens of minutes or hours.
- Database locks/connections stay open far too long.
- Timeouts or restarts make recovery painful.
- No visibility into which recipients were already submitted.
- A failure on recipient 49,999 can cause retry logic to resend the entire batch.
- Heap/disk/bandwidth may become overwhelmed.

Better:

```text
Quartz fire
   |
   v
Create campaign occurrence
   |
   v
Materialize recipient notifications in bounded chunks
   |
   v
Outbox workers with rate/backpressure
   |
   v
Persist outcomes individually
```

Splitting into batches does not sacrifice aggregation: store `campaignOccurrenceId` to report created/submitted/failed/unknown counts and audit individual recipients.

## 79. Technical Pre-Go-Live Checklist for Quartz JDBC

### A. Scheduler persistence

- [ ] Quartz uses JDBC JobStore in environments requiring durable schedules.
- [ ] Quartz tables are created via version-matched database migrations.
- [ ] Schema is never automatically dropped/recreated on production startup.
- [ ] Cluster nodes share config, DB, and unique instance IDs.
- [ ] DB connection pools, backups, and monitoring are configured.
- [ ] Node clocks are synchronized.
- [ ] `JobDataMap` holds only appropriate identifiers and scalar data.
- [ ] Registrar is idempotent and handles create/update/cancel.

### B. Trigger semantics

- [ ] One-shot and recurring schedules are distinguished.
- [ ] Cron expressions are validated against Quartz syntax.
- [ ] IANA timezones are stored and validated.
- [ ] DST policies exist for nonexistent/repeated local times.
- [ ] Explicit misfire policies exist per notification category.
- [ ] Rules exist for handling stale occurrences.
- [ ] Reconciliation/backfill exists where full business periods are required.
- [ ] "FireNow for everything" is avoided if it would trigger a mail storm.

### C. Business correctness

- [ ] Schedules enforce owner/tenant authorization.
- [ ] Schedule versions and update/cancel audits exist.
- [ ] Occurrence keys accurately represent logical events.
- [ ] Database unique constraints prevent duplicates.
- [ ] Occurrences and outbox entries commit atomically.
- [ ] Jobs always verify state/eligibility before materializing.
- [ ] Data/templates/attachments follow snapshot/versioning policies.
- [ ] SMTP is never sent inside the occurrence-creation transaction.

### D. Mail reliability

- [ ] Notifications and attempts have independent IDs.
- [ ] Outbox workers implement claims/leases and retry/backoff.
- [ ] Timeouts and partial SMTP results are classified.
- [ ] `UNKNOWN` outcomes are never blindly retried.
- [ ] Quotas, rate limits, and backpressure are enforced.
- [ ] SMTP test servers and provider feedback are integrated where needed.
- [ ] "Quartz Job SUCCESS" is never equated with "email delivered".

## 80. Checklist When Using an External Scheduler

### Platform capabilities

- [ ] Verified schedule durability, retries, jitter, and firing windows.
- [ ] Understood schedule count limits and invocation quotas.
- [ ] Verified timezone/DST semantics or an appropriate business planner.
- [ ] Clear contracts for updating/cancelling schedules.
- [ ] Backup or recovery procedures for schedule configuration.

### Endpoint or queue security

- [ ] Trigger source authenticated via IAM/token/mTLS/signature as appropriate.
- [ ] Request size, rate, and allowed schedule scopes bounded.
- [ ] Never trust arbitrary recipients or SMTP configs from external requests.
- [ ] Return success only after durable acceptance.
- [ ] Idempotent handling when the scheduler retries callbacks.
- [ ] Queue consumers configure acknowledgments, retries, and dead-letter policies.

### Workers and data

- [ ] Database due scan uses `due_at <= now()` or a business occurrence planner.
- [ ] Claims/unique constraints stop multiple workers from duplicate processing.
- [ ] Missed ticks and backlogs are handled.
- [ ] Outbox state, retries, and `UNKNOWN` handling are implemented.
- [ ] Metrics separate trigger acceptance from SMTP submission.

## 81. Exercise 1 — Restarts Lose Schedules

An application registers a Monday 09:00 report schedule using Quartz, but after redeploying, the schedule disappears.

**Question:** What is the first check to perform?

**Hint:** Verify which `JobStore` is active. If it is `RAMJobStore`, schedules live only in memory. If JDBC, check URL/schema/`tablePrefix`, migrations, automatic schema initialization, and bootstrap code.

## 82. Exercise 2 — Two Instances Send the Same Email

Two pods share the same `@Scheduled` method, and each calls `JavaMailSender.send(...)`.

**Question:** Why did duplicates happen?

**Hint:** Each instance runs its own independent scheduler; the annotation does not perform cluster claiming. Use Quartz JDBC clustering or a shared DB due scanner, and still enforce unique occurrences/outbox rows.

## 83. Exercise 3 — Job Fires Twice After Failover

Node A begins materializing, restarts mid-way, and Node B re-runs the logic.

**Hint:** `@DisallowConcurrentExecution` is not idempotency. Place a unique constraint on the logical occurrence and write occurrence/outbox rows in one transaction.

## 84. Exercise 4 — Three Days of Reports Missed

A daily cron job was down for three days, and Quartz fires only once upon recovery.

**Question:** How do you generate all three missing reports?

**Hint:** Use reconciliation driven by a business calendar and logical period keys rather than assuming misfire handling replays every historical trigger.

## 85. Exercise 5 — Cancelling Right Before Send Time

A user clicks cancel right as Quartz has already acquired the trigger.

**Hint:** Unscheduling only operates at the trigger layer. Business schedule state and database locking decide whether materialization occurs; notifications already submitted to SMTP cannot be recalled via Quartz.

## 86. Exercise 6 — A Cron in Europe/Berlin Misbehaves on DST

A customer asks for a daily email at 02:30; on one DST transition day, 02:30 does not exist.

**Hint:** Define a policy for nonexistent/repeated times, test specifically on DST transition dates, and never add 24 hours to a UTC timestamp assuming it preserves local wall-clock time.

## 87. Exercise 7 — External Tick Delivered Twice

A cloud scheduler misses an acknowledgment and retries its HTTP callback. The scanner runs twice.

**Hint:** Enforce durable idempotency in database occurrence/outbox tables rather than an in-JVM `boolean processed` flag. If two scans run concurrently, database claims/unique constraints are required.

## 88. Exercise 8 — SMTP Timeout After DATA

The schedule runs on time, and the worker sends MIME bytes but never receives the final `250`.

**Hint:** The scheduler should not blindly refire just because `JavaMailSender` threw an error. The SMTP outcome may be `UNKNOWN`; use an attempt ledger, reconciliation, and duplicate-safe retry policies.

## 89. Exercise 9 — One Tenant Creates Thousands of Schedules per Second

The Quartz DB balloons, jobs fire simultaneously, and mail workers get overwhelmed.

**Hint:** Enforce per-tenant quotas, schedule-creation rate limits, minimum intervals, bounded materialization, notification priorities, worker backpressure, and database/thread-pool monitoring.

## 90. Exercise 10 — Attachment Deleted Before Send Time

A schedule three months out references a temporary file that expires after 24 hours.

**Hint:** Never tie long-term schedules to short-lived temp files. Use immutable storage references/versions, verify access rights, and define policies for missing files.

## 91. Key Principles

1. **Quartz JDBC or external schedulers persist schedules; SMTP sending is an independent side effect.**
2. **Quartz `JobDetail.storeDurably()` does not replace JDBC JobStore.**
3. **Pick triggers matching business semantics:** one-shot `Instant`, local-time/zone cron, or business periods.
4. **Misfire policy is a product decision**, with no single setting fitting every email.
5. **Quartz clustering reduces multi-node trigger collisions**, but does not create exactly-once emails.
6. **Logical occurrence keys + database unique constraints** are essential against duplicate materialization.
7. **Create occurrences and outbox entries atomically**, never committing halfway and treating it as done.
8. **Keep scheduler jobs short**, leaving SMTP work to outbox workers.
9. **Never sleep inside Quartz workers to retry SMTP**; persist retry schedules in the database.
10. **Cancelling or editing schedules requires state/versions and reconciliation**, not just Quartz API calls.
11. **External scheduler calls can also arrive late, duplicate, or drop**, requiring secure ingress and idempotency.
12. **A database due scanner can be simpler than Quartz** when handling large volumes of one-shot notifications with `due_at`.
13. **DST/timezone handling must be part of the contract**, never left to JVM defaults.
14. **SMTP `SUBMITTED` differs from `DELIVERED`**, and timeouts after DATA can leave `UNKNOWN` outcomes.
15. **Observability must separate due time, materialization time, submission time, and remote delivery.**

## 92. References

- **Quartz Scheduler:** https://www.quartz-scheduler.org/documentation/
- **Spring Boot — Quartz Scheduler:** https://docs.spring.io/spring-boot/reference/io/quartz.html
- **Spring Framework — Task Execution and Scheduling:** https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- **Spring Framework — Email Integration:** https://docs.spring.io/spring-framework/reference/integration/email.html

When implementing, cross-check documentation for your project's exact **Quartz/Spring Boot versions**, especially regarding JDBC JobStore integration, `JobFactory`, cluster properties, misfire behavior, and schema migrations. Code examples here use application-defined repositories/services to illustrate architecture; those components do not appear automatically just by adding the Quartz starter.

## 93. Conclusion

For durable email scheduling in Spring Framework Mail, **decouple deciding *when work is due* from *actually submitting the email***. Quartz with JDBC JobStore fits well when the app needs dynamic schedules, `CronTrigger`, `SimpleTrigger`, misfire management, and multi-node execution. External schedulers fit when infrastructure already provides a scheduling service capable of calling HTTP/queues or launching periodic workers. For high volumes of one-shot notifications with `due_at`, a database scanner with claims/leases and unique constraints is often simpler than either.

What determines long-term reliability is not just the scheduler, but the **business data model**: schedules with owners, versions, and timezones; occurrences with logical keys; atomically written outbox entries; and mail workers with attempt state, retry/backoff, backpressure, and ambiguous-SMTP handling. Cancellations, edits, misfires, and downtime recovery all require reconciliation and testing. Never use a single successful job execution to conclude an email reached the Inbox.

When boundaries are organized cleanly as **schedule → occurrence → outbox notification → SMTP attempt → provider delivery feedback**, applications can preserve schedules across restarts, scale safely, detect and recover missed schedules, reduce duplicate risks, and give operators clear evidence across every stage of the email lifecycle.
