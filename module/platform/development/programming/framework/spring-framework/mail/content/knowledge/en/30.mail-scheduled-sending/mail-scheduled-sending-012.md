# Safely Pausing Scheduled Sending During Maintenance

An application using **Spring Framework Mail** may operate many types of scheduled emails: daily invoices, payment reminders, promotional notifications, periodic reports, or verification emails valid for only a few minutes. When maintenance is needed on the application, database, SMTP relay, or network infrastructure, "pausing sending" might seem as simple as disabling `@Scheduled`. However, if you do that, some workers may still be sending, some messages may have already left the queue, recurring schedules may not be created during the downtime, and overdue jobs may flood the SMTP provider as soon as the system restarts.

**Safely pausing scheduled sending during maintenance** must be a stateful workflow applied across all instances, handling in-flight submissions and defining a post-maintenance resumption policy. Pausing the schedule does not mean canceling emails, does not recall messages already accepted by the SMTP server, and does not guarantee the provider will stop delivering messages already in its queue.

This lesson presents how to design **pause -> drain -> maintenance -> resume** in a Spring Boot/Spring Mail system with schedulers, workers, a transactional outbox, and multiple replicas. The content covers the state model, blocking atomic claims in the database, graceful shutdown, managing in-flight emails, handling `UNKNOWN` outcomes, catch-up policies, testing, and operational runbooks.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish between pausing **schedule creation**, pausing **job claiming**, pausing **SMTP submission**, and canceling a scheduled send.
2. Explain why disabling `@Scheduled` on one pod does not guarantee the whole system stops sending.
3. Design a durable maintenance flag shared across instances.
4. Block atomic claims after a pause command is committed.
5. Define the **drained** criterion: no worker is actively sending or left with an unresolved state.
6. Apply graceful shutdown during deployment or maintenance.
7. Preserve the outbox, retry deadlines, message keys, and attempt history while paused.
8. Classify `PENDING`, `RETRY_WAIT`, `SENDING`, `SMTP_ACCEPTED`, and `UNKNOWN` emails during maintenance.
9. Recover schedules after downtime without creating duplicate recurring occurrences.
10. Handle overdue, expired, or ineligible jobs upon resume.
11. Combine a global pause with per-provider, per-tenant, or per-email-category pauses.
12. Test races between pause commands, claims, SMTP submissions, and database commits.

## 2. Context: Where Can Emails Originate?

A real-world system often has multiple components running concurrently:

```text
                    Business events
                          |
                          v
             Scheduled job / Outbox writer
                          |
                          v
                 Database outbox
                          |
                     Due-job poller
                          |
                          v
                  Dispatcher / claim
                          |
                     Queue / worker
                          |
                          v
                   MIME renderer
                          |
                          v
                   JavaMailSender
                          |
                          v
                    SMTP provider
                          |
                          v
               Recipient mail systems
```

In addition, there may be:

- `@Scheduled` generating daily report emails.
- Quartz or a Spring Integration poller looking for due jobs.
- RabbitMQ/Kafka consumers processing email commands.
- A REST endpoint sending emails immediately upon user action.
- Retry workers handling failed jobs.
- Multiple application pods accessing the same outbox.
- Providers automatically retrying delivery after accepting a submission.

**A "Pause scheduler" button only controls the paths that are actually wired into the pause mechanism.** If the code has any path calling `JavaMailSender.send(...)` directly outside the dispatcher, determine whether that path falls within the maintenance scope.

### 2.1. Define Scope Before Acting

Answer clearly:

- Stop **all emails** or only marketing emails?
- Stop by **SMTP provider**, **tenant**, **region**, or system-wide?
- Allow creating new requests without sending yet, or temporarily reject requests?
- Are in-flight sends allowed to finish?
- Will emails accepted by the provider before the pause timestamp continue to be delivered?
- After resuming, send all missed items or drop expired notifications?

No single pause mode fits every maintenance purpose.

## 3. Four Operations Often Lumped Together as "Stopping the Schedule"

| Operation | Primary effect | What it cannot do alone |
|---|---|---|
| **Pause schedule creation** | Stops creating new recurring jobs | Does not prevent already existing jobs from sending |
| **Pause dispatch/claim** | Prevents workers from claiming more due jobs | Does not stop submissions that have already started |
| **Drain active submissions** | Lets running attempts finish and waits until safe | Does not recall emails already accepted by the relay |
| **Cancel scheduled job** | Cancels a specific unexecuted email/schedule | Does not replace a system-wide pause |

For example, if a schedule has 500 `PENDING` jobs and 10 are already claimed:

- Turning off the cron that creates new schedules: the 500 existing jobs can still be processed by the dispatcher.
- Stopping the poller: the 10 `SENDING` jobs can still call SMTP.
- Pausing dispatch and draining: the 490 jobs are not newly claimed; the 10 jobs get time to finish and have their states handled.
- Canceling: changes the business state of one or more jobs, not a temporary maintenance measure.

**Pause != Cancel != SMTP delivery stop.** Distinguish them from the API, database, and operational UI upward.

## 4. Safety Goals and Guarantees You Can Commit To

A sound maintenance design establishes these invariants:

1. Once the **pause gate** is committed, claim transactions starting **afterward** receive no new jobs within the paused scope.
2. Unclaimed jobs remain durably stored and are not automatically turned into `FAILED` or `CANCELLED`.
3. Already started attempts have explicit states and history.
4. Jobs already `SMTP_ACCEPTED` are not resent simply because of a restart.
5. Attempts with an `UNKNOWN` outcome are not automatically retried if there is a risk the relay already received the email.
6. Resuming does not create two logical emails for the same business event or recurring occurrence.
7. Only jobs still valid with respect to deadline, consent, token, and recipient policy are caught up.
8. Maintenance is audited: who paused/resumed, when, why, and in what scope.

### 4.1. Distinguish `PAUSED` and `DRAINED`

- **PAUSED:** claim control is blocked; **submissions may still be running**.
- **DRAINING:** waiting for already started submissions/attempts to complete or move into a state requiring reconciliation.
- **DRAINED:** no running sends remain within the scope controlled by the application, according to the defined metrics/ownership sources; unresolved states are recorded separately.
- **RESUMED:** claiming new jobs is allowed again.

An HTTP `200 PAUSED` response should not be described as "no emails are currently sending." If guarantees are needed before cutting the SMTP network, include a drain step and check completion criteria.

### 4.2. Uncontrollable Boundary

After the final SMTP `250` corresponding to a successful submission, the email may already be in the provider's queue. Application maintenance **does not stop the provider from delivering emails to destination servers**. If the business needs to recall notifications, rely on provider-specific capabilities (if any) and still avoid promising every email can be recalled.

## 5. Choosing a Pause Strategy for Each Maintenance Type

| Scenario | Recommended strategy | What to check |
|---|---|---|
| Application deployment | Drain worker/pod, rolling update | Claimed jobs, termination grace, idempotency |
| Outbox database maintenance | Pause claims, drain, stop writers/dispatchers on plan | No half-committed writes, backup/migration |
| Rotating SMTP credentials | Pause profile, drain, swap sender/secret, smoke test | Active AUTH sessions, TLS, From permissions |
| SMTP provider outage | Temporarily pause route/provider or circuit breaker | Retry backlog, `UNKNOWN`, rate limits |
| Marketing campaign maintenance | Pause by category/campaign | Consent and expiry before resume |
| Recurring schedule system maintenance | Pause materializer, keep schedule definitions | Missed occurrences, catch-up |
| Suspected wrong-recipient incident | Emergency stop on affected scope, drain/inspect | Direct send paths outside the outbox |
| Receiving mail provider maintenance | Pause affected route; do not assume other providers are safe | Failover and domain verification |

Do not use stopping one pod as a substitute for a global pause. In a multi-replica environment, other pods can continue sending normally.

## 6. Mail Job State Model During Maintenance

An outbox can use:

```text
PENDING ────────────────> SENDING ───────> SMTP_ACCEPTED
   |                          |
   |                          +─────────> RETRY_WAIT
   |                          |
   |                          +─────────> DEAD_LETTER
   |                          |
   |                          +─────────> UNKNOWN
   |
   +── on pause: remain PENDING
   |
   +── if expired: EXPIRED
   |
   +── user cancellation: CANCELLED

RETRY_WAIT ─ on pause: remain RETRY_WAIT
```

**Pause is a dispatcher control state**, not necessarily a per-email state.

Avoid scanning millions of rows and changing every `PENDING` row to `PAUSED` when you only need to block workers. Doing so:
- increases writes and locks;
- makes resuming expensive;
- loses the original state meaning;
- makes it hard to distinguish user-paused schedules from system-wide maintenance pauses.

You can add a `PAUSED_BY_USER` job state in products that let users pause individual schedules, but it does not replace the system control flag used during maintenance.

### 6.1. `SMTP_ACCEPTED` Does Not Change Due to Pause

Do not "roll back" already accepted jobs to `PENDING` after maintenance. Resending can create duplicates.

### 6.2. `RETRY_WAIT` Keeps Its Retry Schedule

If a retry was scheduled for 10:05 but maintenance lasts until 10:30:
- `next_attempt_at` can remain 10:05;
- the job is eligible upon resume;
- the dispatcher must apply rate limiting/backpressure instead of bursting everything at once;
- do not increment `attempt_count` merely because the job became overdue during the pause.

### 6.3. `UNKNOWN` Requires Reconciliation

An attempt that timed out after SMTP `DATA` may have been accepted by the provider. Do not use pause/resume as an excuse to reset it to `PENDING`.

## 7. Why an In-Memory Boolean Is Not Enough?

A common implementation:

```java
private volatile boolean maintenanceMode = false;

@Scheduled(fixedDelay = 1000)
void dispatch() {
    if (maintenanceMode) {
        return;
    }
    sendDueMails();
}
```

Problems:
- The variable only applies to one process.
- A restart resets the variable to its default value.
- In a cluster, pod A is paused while pod B keeps sending.
- A worker that has already passed the `if` check can keep sending.
- A pause occurring between `SELECT` and `UPDATE` can still create a new job claim.
- There is no audit trail, ownership, or maintenance reason metadata.

`volatile` only provides visibility across threads within one JVM; it **does not create a safe pause protocol** across multiple workers and database transactions.

### 7.1. Is an External Feature Flag Enough?

A centralized feature flag can control multiple pods, but if each worker caches the flag for a few seconds:
- the pause command has propagation delay;
- some workers may claim jobs while still holding stale state;
- losing connection to the flag provider can lead to wrong fallbacks.

If strict persistence boundaries are required, combine a feature flag for UX/rollout with **a gate checked inside the same claim transaction**. Clearly specify whether the system fails closed when maintenance state cannot be read.

## 8. Durable Pause Control Table

PostgreSQL example:

```sql
CREATE TABLE mail_dispatch_control (
    scope VARCHAR(128) PRIMARY KEY,
    paused BOOLEAN NOT NULL DEFAULT FALSE,
    generation BIGINT NOT NULL DEFAULT 0,
    paused_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL,
    updated_by VARCHAR(128) NOT NULL,
    reason VARCHAR(256)
);

INSERT INTO mail_dispatch_control (
    scope, paused, generation, paused_at,
    updated_at, updated_by, reason
)
VALUES (
    'GLOBAL', FALSE, 0, NULL,
    CURRENT_TIMESTAMP, 'bootstrap', NULL
);
```

Columns:
- `scope`: `GLOBAL`, or `PROVIDER:transactional`, `TENANT:tenant-123`.
- `paused`: whether the gate is enabled or disabled.
- `generation`: version number to trace and detect control changes.
- `paused_at`: timestamp of the most recent pause start.
- `updated_by` and `reason`: basic audit data.

### 8.1. Do Not Default to "Keep Sending If the Database Is Lost"

If a worker cannot check the control row or the database is unavailable, **never assume `paused=false`** and call SMTP. For a system where maintenance must block sends, the right policy is to fail closed at the claim step.

If a job was already claimed before the DB failed, that is a separate in-flight/`UNKNOWN` scenario; handle it per runbook rather than silently continuing to send everything.

### 8.2. Multiple Scopes

If pausing by provider/tenant is needed, a simple approach gives each scope its own row. When claiming a job, policy must check all applicable scopes. Enforce a consistent lock ordering, for example:
1. `GLOBAL`.
2. `PROVIDER:<providerKey>`.
3. `TENANT:<tenantId>`.

Do not let workers acquire locks in different orders and cause deadlocks.

### 8.3. Locking a Global Row Trades Off Throughput

A gate row locked with `FOR UPDATE` in every claim transaction **serializes claim attempts**, which can become a bottleneck under heavy workload. It is a simple option that is easy to reason about for correctness. For high traffic, you can design a generation/fencing protocol or partition claim gates by scope, but you must still prove that pause and claim form a consistent boundary.

Do not sacrifice atomicity just for a faster boolean read.

## 9. Pause and Claim Must Be Synchronized by Transaction

Suppose:

```text
Worker A                       Operator
   |                              |
   | read paused=false            |
   |                              | pause=true, commit
   | select due job               |
   | update SENDING               |
   |                              |
   v                              v
   SMTP submission continues after pause
```

If reading the flag lacks a protocol synchronized with claiming, new messages can still be claimed after the operator thinks the pause is complete.

### 9.1. A Simple Option: Lock the Gate Row

Each claim transaction executes:

```sql
BEGIN;

SELECT paused, generation
FROM mail_dispatch_control
WHERE scope = 'GLOBAL'
FOR UPDATE;

-- If paused = TRUE:
--   COMMIT without claiming anything.

-- If paused = FALSE, proceed to claim due jobs:
WITH next_jobs AS (
    SELECT message_key
    FROM scheduled_email
    WHERE status IN ('PENDING', 'RETRY_WAIT')
      AND send_at <= CURRENT_TIMESTAMP
      AND next_attempt_at <= CURRENT_TIMESTAMP
    ORDER BY next_attempt_at, send_at, created_at
    FOR UPDATE SKIP LOCKED
    LIMIT :batchSize
)
UPDATE scheduled_email e
SET status = 'SENDING',
    attempt_count = attempt_count + 1,
    lease_token = :leaseToken,
    lease_expires_at = :leaseExpiresAt,
    updated_at = CURRENT_TIMESTAMP
FROM next_jobs n
WHERE e.message_key = n.message_key
RETURNING e.message_key, e.attempt_count,
          e.lease_token;

-- Insert corresponding attempt history in the same transaction.
COMMIT;
```

This is a **skeleton**: the application must inspect `paused` before executing the claim part. Do not run the entire script straight through regardless of the flag value.

### 9.2. The Pause Command Writes the Same Gate Row

```sql
BEGIN;

UPDATE mail_dispatch_control
SET paused = TRUE,
    generation = generation + 1,
    paused_at = CURRENT_TIMESTAMP,
    updated_at = CURRENT_TIMESTAMP,
    updated_by = :operatorId,
    reason = :reason
WHERE scope = 'GLOBAL';

COMMIT;
```

Because the claim transaction holds the lock on the `GLOBAL` row, the pause command waits for the in-progress claim to commit. Conversely, once pause commits, subsequent claims see `paused=true` and acquire no new jobs.

**The guarantee here is "no new claims after the pause commit point,"** not "no SMTP call is currently running."

### 9.3. Why Not Hold the Lock Until SMTP Finishes?

You should not hold a database transaction or row lock across an SMTP call that can take many seconds or time out. The right pattern is:
1. Short claim transaction, commit.
2. SMTP submission outside the transaction.
3. Short transaction to persist the outcome.

That is why **pause + drain** always requires two steps: blocking new claims and managing attempts that have already left the claim transaction.

### 9.4. Paused Does Not Mean Deleting Jobs From the Due Query

Jobs still in `PENDING` or `RETRY_WAIT` remain in the DB with their `send_at`/`next_attempt_at` timestamps. The gate prevents claiming. Upon resume, the dispatcher re-evaluates eligibility and due schedules.

## 10. Implementing the Gate With a Spring Service

Example contract:

```java
package com.example.mail.maintenance;

public record DispatchGate(
    boolean paused,
    long generation
) {}

public interface DispatchControlRepository {

    // SELECT ... FOR UPDATE, participating in the current transaction.
    DispatchGate lockGlobal();

    // UPDATE gate row inside the transaction.
    void updateGlobal(
        boolean paused,
        String operatorId,
        String reason
    );
}
```

Coordinator:

```java
package com.example.mail.maintenance;

import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class MailClaimCoordinator {

    private final DispatchControlRepository controls;
    private final ScheduledMailRepository mailRepository;

    public MailClaimCoordinator(
            DispatchControlRepository controls,
            ScheduledMailRepository mailRepository) {
        this.controls = controls;
        this.mailRepository = mailRepository;
    }

    @Transactional
    public List<ClaimedMail> claimDue(int maxJobs) {
        DispatchGate gate = controls.lockGlobal();

        if (gate.paused()) {
            return List.of();
        }

        // The repository uses atomic SELECT ... FOR UPDATE SKIP LOCKED
        // and records mail attempts in the same transaction.
        return mailRepository.claimDueBatch(maxJobs);
    }
}
```

`ScheduledMailRepository` and `ClaimedMail` are application-defined interfaces/models, not built-in APIs in Spring Mail. The repository must have an implementation backed by a real database.

### 10.1. Pause Service With the Same Transaction Discipline

```java
package com.example.mail.maintenance;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class MailMaintenanceService {

    private final DispatchControlRepository controls;

    public MailMaintenanceService(
            DispatchControlRepository controls) {
        this.controls = controls;
    }

    @Transactional
    public void pauseGlobal(
            String operatorId,
            String reason) {

        controls.updateGlobal(true, operatorId, reason);
    }

    @Transactional
    public void resumeGlobal(
            String operatorId,
            String reason) {

        controls.updateGlobal(false, operatorId, reason);
    }
}
```

Requirements:
- Both methods must pass through an actual Spring transaction proxy.
- Do not use self-invocation expecting `@Transactional` to apply automatically.
- The repository must use the same data source and transaction manager as the outbox claim.
- Only authorized operators/services may call pause/resume.
- Maintain an audit trail independent of the current-state row if history across multiple maintenance events is required.

### 10.2. "Pause Succeeded" Must Have Concrete Meaning

An API `POST /ops/mail/pause` can return:
- `PAUSED`: the gate is committed, no new claims occur.
- `DRAINING`: active attempts are still in progress.
- `DRAINED`: the scope's quiescence criteria are satisfied.

Do not call all three states "mail stopped" because their guarantees differ.

## 11. DRAIN: Waiting for In-Flight Sends

Once pause commits, there are still jobs already claimed and currently:

```text
SENDING:
   |
   +--> render MIME
   +--> connect SMTP
   +--> TLS handshake / AUTH
   +--> MAIL FROM / RCPT TO / DATA
   +--> wait for server reply
   +--> persist outcome
```

Killing the process right in the middle of `DATA` may leave the server having accepted the message while the client never saw the result. Stopping abruptly can create many `UNKNOWN` attempts and raise duplicate risk during recovery.

### 11.1. Typical Drain Workflow

1. Commit the pause gate.
2. Pause new dispatchers/consumers (or let them run while claim returns empty).
3. Wait a bounded time for workers that already claimed jobs to finish.
4. Monitor `active_submissions`, `SENDING`, and live leases.
5. If slow attempts remain, investigate and decide whether to extend drain or move them into a reconciliation-needed state.
6. Only then cut SMTP networking, rotate credentials, or terminate workers.
7. Record evidence and the final state of the maintenance window.

### 11.2. Define What Counts as Drained

Useful criteria for a scope:
- no submission tasks are actually running on managed worker instances;
- completed outcomes are persisted;
- unresolved attempts are listed and handled as `UNKNOWN`;
- no old worker holds sending ownership outside operator control.

Simply querying:

```sql
SELECT COUNT(*)
FROM scheduled_email
WHERE status = 'SENDING';
```

is a useful signal, **not necessarily sufficient**: rows may be stuck after a process crash, or the system may have send tasks outside the outbox. Cross-check lease ownership, health/worker heartbeats, and in-flight counters.

### 11.3. Drain Timeout

If an SMTP call hangs, do not wait forever. You must have:
- SMTP connect/read/write timeouts;
- an appropriate overall deadline per attempt;
- lease renewal or a sufficiently large lease duration;
- a drain deadline;
- an escalation policy if draining does not finish.

Do not mark an outcome as definitely `FAILED` merely because an operator forced an in-flight process to stop; the outcome may be unknown.

## 12. Tightening the "No New Sends" Boundary While Draining

A gate check right before `send(...)` helps:

```java
if (maintenanceGuard.isPausedFor(job)) {
    // Do not call SMTP; return the job to an appropriate waiting state,
    // while preserving attempt history and lease discipline.
    return;
}

mailSender.send(mime);
```

However, this is **not an absolute proof** that no SMTP occurs after pause:

```text
Worker: read paused=false
Operator: pause commit
Worker: call mailSender.send(...)
```

There is still a race between reading the flag and the non-rollbackable side effect. Mitigation:
- atomic gate at the claim step;
- define jobs claimed before pause as in-flight;
- drain all workers before performing actual maintenance;
- if extremely strict guarantees are required, implement a coordinated permit/handshake or fencing for sending rather than just an `if` check;
- clearly bound the guarantee scope in the runbook.

**Do not promise "no email will be sent after the pause API returns" if in-flight jobs are still allowed to complete.** Use accurate wording such as "new claims blocked; draining."

## 13. Do Not Use `@ConditionalOnProperty` as a Runtime Pause Switch

Example:

```java
@ConditionalOnProperty(
    name = "app.mail.dispatch.enabled",
    havingValue = "true"
)
@Component
public class DueMailScheduler {
    // ...
}
```

`@ConditionalOnProperty` is typically evaluated when the Spring context is created. Changing a config file or environment variable **does not automatically stop an already running bean**.

It is a good choice for:
- disabling workers when deploying an API-only instance type;
- static environment-specific configuration;
- separating application roles.

However, it is **not a runtime pause/resume switch with a consistent boundary** across a cluster.

### 13.1. `@Scheduled` Is Only a Technical Trigger

```java
@Scheduled(fixedDelayString = "${app.mail.dispatch.delay-ms:1000}")
public void dispatch() {
    coordinator.claimAndDispatch();
}
```

A cron/fixedDelay trigger can keep firing during maintenance and receive an empty list from the gate. That is acceptable if it consumes minimal resources. You can stop the trigger to reduce load after pausing, but correctness must rely on the durable gate, not just the trigger schedule.

### 13.2. Stopping a Scheduled Task With `SchedulingConfigurer`?

Spring supports various ways to configure schedulers or manage lifecycle, but canceling a `ScheduledFuture`/endpoint on one instance:
- has no effect on other instances;
- may not wait for a running callback to finish;
- stores no durable state so a restart knows to stay stopped;
- does not handle in-flight SMTP.

Use task lifecycle management as part of shutdown, not as a replacement for global pause control.

## 14. Graceful Shutdown in Spring Boot

When deploying or stopping the application:

1. Signal that the workload is no longer ready for **new work** using the appropriate mechanism.
2. Block new job claims within the scope to be stopped.
3. Let in-flight operations finish within a timeout.
4. Persist outcomes.
5. Close queue consumers, executors, and resources.
6. Exit the process cleanly.

### 14.1. HTTP Graceful Shutdown Does Not Automatically Stop Email Workers

Spring Boot provides graceful shutdown configuration for the web server:

```yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
```

These settings help the lifecycle manage framework-supported shutdown, but **do not guarantee that every custom `@Scheduled` task or application background email worker will drain properly**.

If you create custom `ExecutorService`, `Thread`, queue consumer, or scheduler components:
- participate properly in the Spring lifecycle;
- stop accepting new jobs;
- await in-flight completion with a timeout;
- handle interruption;
- persist durable state.

### 14.2. `SmartLifecycle` and Controlled Stop

You can design a `SmartLifecycle` component or shutdown orchestrator to stop the dispatcher and await the worker pool. However, when using multiple phases, define the ordering carefully:
- dispatcher stops first;
- active senders finish;
- persistence and connection pools remain active long enough to write outcomes;
- finally close datasources and network dependencies.

If the database closes before workers persist submission results, attempts can become `UNKNOWN` even though SMTP accepted the messages.

### 14.3. `@PreDestroy` Is Not Enough to Await Asynchronous Work

`@PreDestroy` is useful for cleanup, but it should not just flip a flag and return immediately if worker threads are still running. You need a bounded join/await-termination mechanism that respects the Spring context shutdown order.

Do not extend shutdown indefinitely and force the orchestration platform to kill the process.

## 15. Kubernetes Rolling Maintenance and `preStop`

A Kubernetes deployment may have multiple pods sending emails.

```text
Pod A -> worker/email outbox
Pod B -> worker/email outbox
Pod C -> worker/email outbox
             |
             v
          Database
             |
             v
          SMTP relay
```

When Kubernetes terminates pod A:
- pods B/C can still claim jobs if there is no **global pause**;
- pod A may be in the middle of an SMTP call;
- termination grace period is bounded;
- readiness does not automatically disable background `@Scheduled` tasks;
- a `preStop` hook only runs in the pod's context and does not change global DB control unless designed to.

### 15.1. Distinguish Pod Drain and Global Pause

**Pod drain** is for rolling deployments:
- a specific node/pod stops claiming;
- other pods continue processing;
- lease/worker ownership is managed;
- the pod exits after local workers finish.

**Global pause** is for maintaining all of SMTP/database or a window requiring submissions to halt:
- all pods obey the same gate;
- in-flight work across all pods must be drained;
- resume only after system-wide verification.

### 15.2. Termination Grace Period

The grace period must be long enough for an active attempt or configured timeout, without extending unboundedly. If a pod runs out of grace and is killed mid-SMTP:
- do not assume it was definitely unsent;
- wait for lease recovery and reconciliation;
- do not blindly resend.

### 15.3. Readiness Is Not a Kill Switch for the Scheduler

Failing a readiness probe typically removes the service from the HTTP load balancer, **not guaranteeing that background periodic threads inside the pod stop running**. Control the dispatcher separately.

## 16. Database Maintenance and Transactional Outbox

When preparing for a database migration or backup:

1. Define the maintenance window and type of DB operation.
2. Pause new claims when needed.
3. Wait for in-flight sends to finish and persist outcomes.
4. Optionally stop creating new jobs, or switch the API to reject/safely queue as required.
5. Run breaking schema migrations only after ensuring writers/workers are no longer touching the affected schema.
6. After maintenance, verify schema, constraints, datasources, and outbox consistency.
7. Resume in a controlled manner.

### 16.1. Cannot Write Jobs When the Database Is Unavailable

If the API still accepts requests and returns "scheduled" when it cannot persist the outbox, jobs can be lost. Choose an appropriate pattern:
- reject temporarily with an appropriate status;
- write to another designed durable upstream if available;
- only return success after a durable commit.

Do not substitute an in-memory list and treat it as having database-grade durability.

### 16.2. Migrations Can Break Old Workers

If a rolling migration alters outbox columns/states while old workers are still running, they may:
- fail to understand new statuses;
- claim the wrong jobs;
- write incompatible outcomes.

Use expand/contract schema strategies, versioning, and properly timed draining. A pause only guards gate-based dispatching; it does not automatically resolve every incompatibility between producer and consumer versions.

### 16.3. When a DB Outage Happens After SMTP Accepted

Flow:

```text
Worker                  SMTP relay              Database
   |--- DATA accepted ---->|
   |<------ 250 -----------|
   |                       |---- UPDATE outcome --> X
   |
   +-- cannot persist acceptance
```

If the worker crashes, the outbox row may still be in `SENDING`. Recovery must treat this as **an outcome not durably persisted**, rather than resending simply because the database lacks `SMTP_ACCEPTED`.

## 17. SMTP Provider Maintenance or Credential Rotation

When changing host, TLS certificates, SMTP accounts, or credentials:
- pause jobs routed through **that provider/profile**;
- drain active sends using the old account;
- prepare the new sender/profile;
- verify TLS hostname, CA chain, AUTH, and verified From;
- run a smoke test to an authorized mailbox/sandbox;
- re-enable sending gradually by quota;
- keep the old account during a transition period if needed to handle connections/sends already started.

### 17.1. Do Not Mutate a Singleton `JavaMailSender` While It Is in Use

Do not run:

```java
sharedSender.setHost(newHost);
sharedSender.setUsername(newUser);
sharedSender.setPassword(newPassword);
```

while another worker is sending. Mutable configuration can interleave across requests and accounts. If runtime changes are required, build a new profile/sender and switch ownership in a controlled way after draining or via a versioned registry.

### 17.2. Failover Is Not Pause

Moving jobs from provider A to B is a separate routing and delivery decision. Do it only when:
- B has verified domains and DKIM/SPF/DMARC alignment;
- sending permissions/consent/suppression are preserved;
- B's quota allows it;
- A's attempt is confirmed unaccepted or covered by idempotency/reconciliation;
- no `UNKNOWN` attempts are blindly resent.

Pausing A does not automatically grant permission to send via B.

## 18. Scoped Pauses: Global, Provider, Category, Tenant

A large system may need multiple control layers:

```text
GLOBAL gate
   |
   +--> PROVIDER:transactional
   |
   +--> PROVIDER:marketing
   |
   +--> CATEGORY:MARKETING
   |
   +--> TENANT:enterprise-42
```

A job is eligible only if **all scopes applicable to the job are unpaused**.

### 18.1. Determine the Provider Before Claiming

If pausing by provider, the job must have its provider route decided at or before claim time. If a router changes the provider after the gate check, verify that the new provider's gate is also enforced.

### 18.2. Lock in a Consistent Order

For example, when locking control rows:
1. `GLOBAL`.
2. `PROVIDER` by canonical key.
3. `CATEGORY`.
4. `TENANT`.

Maintain the same order across all worker and admin operations to reduce deadlock risk. Locking multiple rows increases contention, so benchmark it, while never losing the guarantee that operator pauses are respected.

### 18.3. Should Tenants Be Allowed to Self-Pause?

A self-service API can let tenants pause their own campaigns, provided:
- the backend identifies the tenant from authentication;
- tenant A cannot modify global or provider controls;
- rate limits and auditing are enforced;
- an incoming email header never decides the tenant;
- resuming a single tenant cannot override a global pause.

## 19. Retries, Deadlines, and Long Downtime

Suppose:
- Email A was due at 09:00.
- Maintenance ran from 08:55 to 10:30.
- Email B's retry became due at 09:15.
- Email C contains a token expiring at 09:20.

When resuming at 10:30:
- A can be caught up if still useful.
- B can retry per policy with backoff/quota.
- C **should not be sent** if the token has already expired.

### 19.1. Three Timestamps Must Remain Separate

| Field | Meaning |
|---|---|
| `send_at` | Earliest scheduled submission time |
| `next_attempt_at` | Earliest retry time after an error |
| `expires_at` | Time limit until which sending is still allowed |

All of these execution timestamps should be stored as **absolute instants** (for example `TIMESTAMPTZ` in PostgreSQL); the schedule timezone is stored separately if recurrence calculation is needed.

### 19.2. Pausing Does Not Increment `attempt_count`

A job sitting in `RETRY_WAIT` through 2 hours of maintenance does not mean it failed another time. `attempt_count` only increments when an attempt actually starts per contract, not on every poller tick while paused.

### 19.3. Business Retry Deadline Differs From SMTP Socket Timeout

A 10-second SMTP read timeout does not mean an email can retry endlessly every 10 seconds. The retry policy must also cap:
- total attempts;
- maximum elapsed time;
- deadline;
- provider rate limits;
- `UNKNOWN` status.

## 20. On Resume: Do Not Blindly Catch Up Everything

After maintenance, tens of thousands of jobs may be overdue. If `paused=false` and 100 workers wake up together, they can:
- open thousands of connections to the SMTP provider;
- exceed quotas/rate limits;
- trigger more 421/451 responses;
- cause a retry storm;
- send notifications that are no longer valid;
- create duplicate emails if old attempts were not reconciled.

### 20.1. Backlog Policy

Classify before resuming:

| Group | Example | Recommended action |
|---|---|---|
| **Valid catch-up** | Issued invoice, still needed | Keep job, throttle by quota |
| **Expired** | Expired OTP/reset link | `EXPIRED` or generate a valid new flow |
| **No longer consented** | Marketing user opted out during maintenance | Suppress/cancel |
| **Handled externally** | Provider accepted before pause | Do not resubmit |
| **`UNKNOWN`** | Timed out before persisting outcome | Reconcile |
| **Recurring missed runs** | Old daily report | Apply catch-up policy |
| **Partially remaining deadline** | Upcoming event reminder | Send if still meaningful, not past deadline |

### 20.2. Gradual Resume in Waves

You can:
1. Resume only a canary provider/tenant.
2. Cap worker concurrency.
3. Apply rate limiting and jitter.
4. Monitor 4xx/5xx, timeouts, lag, and backlog.
5. Increase throughput once stable.
6. Expand to the remaining scopes.

Prioritize by business criticality; do not assume all old emails are equally important.

### 20.3. Do Not "Bump `send_at` to Now" to Clear Backlog

There is no need to rewrite every `send_at` to `now()`. Overdue jobs are already eligible under `send_at <= now`. Mass-updating `send_at` destroys intent history, breaks schedule-lag calculation, and creates unnecessary database contention.

## 21. Recurring Schedules, Cron, and Maintenance Windows

Another problem: **no outbox rows were created** while the system was down.

Example schedule:
> Send report every day at 09:00 in the user's local time.

If the application stops for 3 days, relying solely on `@Scheduled` can **miss three triggers**.

### 21.1. Separate Schedule Definitions and Occurrences

```text
recurring_schedule:
   scheduleId
   zoneId
   localTime
   recurrenceRule
   status
         |
         v
occurrence materializer
         |
         v
scheduled_email:
   scheduleId
   occurrenceDate
   sendAt
   status
```

Upon resume:
- find unmaterialized occurrences;
- apply the catch-up policy;
- insert with a unique business key;
- send only occurrences that are still valid;
- avoid creating duplicates if the materializer runs again.

### 21.2. Pause the Materializer or the Dispatcher?

Two options:
- **Pause dispatcher only:** cron/materializer keeps inserting jobs into the DB during maintenance as long as the DB is available. Resume drains the backlog.
- **Pause materializer too:** catch-up is required to reconstruct missed occurrences after maintenance.

Choose according to the maintenance type. During DB downtime, the materializer cannot persist anyway, so catch-up computation is required.

### 21.3. Timezones and DST Still Apply

A "09:00 daily in Berlin time" schedule must keep generating the right local occurrence across DST. Do not take the last `Instant` and add a fixed 24 hours if the contract is local wall time. After downtime, compute local date/`ZoneId` and apply the gap/overlap policy.

### 21.4. Unique Occurrence Key

Example:

```text
tenantId | scheduleId | localDate | occurrenceSlot
```

A unique constraint ensures that two materializers running catch-up concurrently do not create two logical emails for the same period. If policy permits two occurrences on a DST overlap day, the key must distinguish the slot/offset.

## 22. Timezones Must Not Change Because of Maintenance

An already resolved schedule:

```text
local: 2026-12-01T09:00
zone: Asia/Ho_Chi_Minh
send_at: 2026-12-01T02:00:00Z
```

When maintenance runs from 01:50Z to 02:30Z:
- `send_at` remains 02:00Z;
- upon resume at 02:30Z, the job is 30 minutes overdue;
- the system can catch it up if still valid;
- audit records actual submission time separately from planned time.

Do not convert it to `09:00 server timezone` upon restart and do not recompute a committed instant simply because the server was deployed in a different region.

### 22.1. When Is Recomputation Needed?

Only when the business schedule is defined in **wall time** and an authorized change occurs, for example:
- the user changes the schedule's timezone;
- the recurrence rule changes;
- timezone rules update and unexecuted future occurrences must reflect the new rules.

Maintenance itself is never a reason to change schedule semantics.

### 22.2. Catch-Up Does Not Mean "Just Fire Cron Once"

If multiple occurrences were missed, a single `@Scheduled` invocation after restart may only create today's job. The materializer must read the schedule definition and the unmaterialized interval rather than relying solely on the current trigger.

## 23. `QueueChannel`, RabbitMQ, and Kafka During Maintenance

Not every system uses an SQL outbox directly. There may be:

```text
Business service -> Broker -> Mail consumer -> SMTP
```

When pausing:
- you can stop consumers;
- reduce prefetch;
- stop acking/claiming more messages;
- let already fetched deliveries finish;
- keep the backlog durable on the broker.

### 23.1. In-Memory `QueueChannel`

A default `QueueChannel` in Spring Integration can live in memory. If the app restarts:
- unprocessed messages can be lost;
- draining only covers messages in the local queue and in-flight in that process;
- there is no durability guarantee just because the name contains "Queue."

For important scheduled sends, use an outbox, a persistent `MessageStore`, or a durable broker with properly designed transactions and recovery.

### 23.2. Pausing Broker Consumers

Stopping or pausing broker listeners prevents receiving new deliveries, however:
- prefetched messages may already sit inside the consumer;
- ack/nack semantics differ;
- Kafka offset commits and RabbitMQ delivery acks are not identical;
- in-flight SMTP cannot be rolled back;
- restarts can redeliver, creating duplicate risk.

Use the broker's contract for draining, acking, and replaying; **do not treat pausing a listener as proof that no sends remain**.

### 23.3. Do Not Route Broker Messages to DLQ Just Because of Maintenance

Maintenance is a system state, usually not a data error. For a temporary pause, keep jobs in the queue/outbox. Dead-letter queues are for cases where policy determines automatic continuation is impossible or the retry budget is exhausted.

## 24. In-Flight State Transitions on Failure or Process Kill

A worker can die at several points:

| Crash point | Likely SMTP accepted? | Recovery action |
|---|---|---|
| Before claim | No | Job remains pending |
| Claim succeeded, before sending | Likely no, if clear evidence exists | Recover per lease/attempt log |
| After connect, before `DATA` | Usually no content accepted, but protocol evidence needed | Retry once classified safe |
| During `DATA` | Uncertain | Keep `UNKNOWN` if unverifiable |
| After end-of-`DATA`, lost response | Possibly accepted | `UNKNOWN`, reconciliation |
| Received `250` success, DB update failed | Yes | Do not blindly resend |
| DB committed `SMTP_ACCEPTED` | Submission evidence exists | Do not create a new attempt |

### 24.1. Lease Expiry Does Not Mean Unsent

If a `SENDING` row has `lease_expires_at < now`:
- the worker may have died before submission;
- or SMTP accepted it without persisting;
- or an old worker is still sending despite the expired lease.

Do not automatically flip all such rows back to `PENDING` and resend on resume. Route them through a recovery classifier and reconciliation, using fencing on database updates.

### 24.2. Storing Attempt History

A record should include:
- message key;
- attempt ID;
- worker/lease token;
- provider/profile;
- `startedAt`;
- stage-by-stage state if observable by the application;
- outcome/safe error code;
- `acceptedAt` or `unknownReason`;
- appropriate correlation metadata.

Do not log passwords, SMTP `AUTH` traffic, full MIME bodies, reset tokens, or attachments for routine investigation.

## 25. Readiness and Health Conditions on Resume

Before unpausing, verify:

- Database schema, connections, and migrations are complete.
- Outbox statuses, indexes, and constraints are queryable.
- Worker deployments are on compatible versions.
- SMTP provider endpoint is reachable per policy.
- TLS certificate and hostname validation pass without errors.
- Credentials have been rotated and still have send permission.
- From identity/domain is verified.
- Queue/broker and related storage can recover cleanly.
- `UNKNOWN` attempts have a handling plan.
- Backlog, deadlines, and rate-limit budgets are estimated.
- Monitoring and on-call are active.

### 25.1. Controlled Smoke Test

A test email to an authorized mailbox can verify the submission route. If the system is globally paused:
- use an explicitly **authorized and isolated** smoke-test mechanism, such as an SMTP sandbox or a dedicated test route;
- do not bypass pause haphazardly in production code;
- do not use real customer recipients;
- only resume real traffic after the smoke test passes.

### 25.2. A Successful SMTP Test Does Not Prove Delivery

A relay returning success does not mean the email landed in the Inbox. If switching providers, also verify SPF/DKIM/DMARC, bounce/webhook/suppression handling, and operational quotas.

## 26. Security of Pause/Resume Commands

An operational endpoint capable of halting sending across the entire system is a sensitive action.

Requirements:
- Authenticate operators and apply least-privilege authorization.
- Only authorized staff or automation may pause globally.
- Audit every command and scope.
- Maintenance reasons must not contain secrets.
- Protect against CSRF if cookie/browser sessions are used.
- Restrict the API to appropriate management networks/channels.
- Enforce rate limiting and idempotent command semantics.
- Use two-person approval if required by SLA/policy.
- Prevent tenant A users from pausing tenant B's provider.
- Provide a read-only way to view status without pause/resume permissions.

### 26.1. Suggested API Contract

```text
POST /ops/mail-dispatch/pause
{
  "scope": "GLOBAL",
  "reason": "database-migration",
  "requestId": "maintenance-2026-11-12"
}

Response:
{
  "state": "PAUSED",
  "generation": 42,
  "activeAttempts": 7,
  "drained": false
}
```

This command means the gate has committed; prior attempts may still finish.

```text
GET /ops/mail-dispatch/status?scope=GLOBAL

{
  "state": "DRAINING",
  "generation": 42,
  "activeAttempts": 3,
  "unknownAttempts": 1
}
```

These are **custom application-designed example APIs**, not built-in endpoints of Spring Framework Mail.

### 26.2. Idempotent Pause/Resume

Repeating the same pause request should not produce unintended business changes or flip state. Consider:
- whether to increment `generation` only on actual state transitions or on every newly issued operator command;
- request IDs to avoid duplicate audit events;
- optimistic versioning if multiple operators act concurrently;
- alerting if a resume command occurs outside a maintenance window.

### 26.3. Avoid Automatic Resume on Process Restart

If the pause flag is stored in the DB, restarting the app must not reset it to `false`. Resuming must be an authorized operational action once conditions are ready.

## 27. Observability: Know Exactly Which Step You Are In

Suggested metrics:

| Metric | Purpose |
|---|---|
| `mail_dispatch_paused{scope}` | Whether the gate is on or off |
| `mail_maintenance_generation{scope}` | Control version |
| `mail_active_submissions{provider}` | Running SMTP sends |
| `mail_outbox_pending_count` | Unsent jobs |
| `mail_outbox_retry_wait_count` | Jobs waiting to retry |
| `mail_outbox_unknown_count` | Attempts needing reconciliation |
| `mail_outbox_expired_count` | Expired jobs |
| `mail_outbox_oldest_due_age_seconds` | How long the oldest backlog item has been overdue |
| `mail_dispatch_claims_total` | Jobs claimed |
| `mail_dispatch_claim_blocked_total{scope}` | Claims blocked due to pause |
| `mail_smtp_submit_duration_seconds` | SMTP submission latency |
| `mail_smtp_outcomes_total{outcome}` | Success/failure/unknown |
| `mail_maintenance_drain_seconds` | Drain duration |
| `mail_recovery_stale_leases_total` | Leases needing post-failure handling |
| `mail_schedule_catchup_created_total` | Catch-up occurrences created |

Metric names here are illustrative. Do not use message keys, recipients, or raw tenant identifiers as high-cardinality Prometheus labels.

### 27.1. Structured Logs

```json
{
  "event": "mail.dispatch.paused",
  "scope": "GLOBAL",
  "generation": 42,
  "reasonCode": "DB_MIGRATION",
  "operatorRole": "MAIL_OPERATOR",
  "activeAttemptsAtPause": 7
}
```

And when drained:

```json
{
  "event": "mail.dispatch.drained",
  "scope": "GLOBAL",
  "generation": 42,
  "activeAttempts": 0,
  "unknownAttemptsPendingReview": 1,
  "durationMs": 21820
}
```

**`activeAttempts=0` does not mean `unknownAttempts=0`.** There may be no network calls currently running while some outcomes still need reconciliation before resuming the related jobs.

### 27.2. Critical Alerts

- Gate stayed paused longer than the planned maintenance window.
- Drain did not complete before timeout.
- A new claim occurred after pause commit (coordination bug).
- An active worker still submitted after an operator confirmed `DRAINED`.
- `UNKNOWN` rose during restart.
- Backlog age exceeded SLA.
- Resuming triggered an SMTP 4xx/rate-limit spike.
- An expired job was still submitted.
- Recurring occurrences were missed or duplicated.

## 28. Pre-Maintenance Runbook

A clear runbook limits ad-hoc guesswork.

### Step 1 — Define Scope

Document:
- Purpose and expected duration.
- Affected providers, tenants, and categories.
- Which emails are allowed to continue sending.
- Whether schedule creation is also paused or only dispatch.
- Shortcut senders calling directly outside the outbox.
- Business deadlines, SLAs, and quiet hours.
- Person responsible for pausing and resuming.

### Step 2 — Check Baseline State

Measure:
- due backlog and oldest due age;
- active attempts;
- retries and `UNKNOWN`;
- throughput/quota;
- upcoming recurring schedules;
- DB/schema readiness;
- running pods/consumers.

### Step 3 — Communicate Scope and Expectations

If user-facing APIs accept new schedules during maintenance, the UI/API must state:
- whether requests are still saved or temporarily rejected;
- potential send delays;
- cancellation/rescheduling conditions;
- that overdue notifications may be dropped per policy.

Do not promise that every email will be sent on time while the system intentionally halts dispatch.

### Step 4 — Prepare Rollback

Identify who has authority to:
- extend the pause;
- roll back migrations;
- restore old secrets;
- run a canary resume;
- pause again if provider errors spike.

## 29. Pause and Drain Runbook

### Step 1 — Commit the Pause Gate

Call the admin API or execute the transaction updating the control row. Confirm the version/`generation` and commit timestamp.

### Step 2 — Verify No New Claims

Watch the claim rate and test/query that the dispatcher returns empty in the paused scope. Do not merely check a single JVM flag.

### Step 3 — Let In-Flight Finish

Monitor:
- active SMTP submissions;
- `SENDING` jobs;
- lease ownership;
- timeout/TLS errors;
- number of attempts needing reconciliation.

### Step 4 — Finalize Abnormal Attempt States

If a worker crashed or an outcome is uncertain:
- record `UNKNOWN`/reconciliation tasks per policy;
- do not bulk-reset to `PENDING`;
- record the message keys needing investigation;
- avoid resending before a decision is made.

### Step 5 — Confirm `DRAINED` Per Contract

Record:
- scope;
- generation;
- drained timestamp;
- active count = 0 from observed sources;
- list of unresolved `UNKNOWN` items;
- operator/approval if applicable.

### Step 6 — Perform Maintenance

Only after reaching the required safety level should you:
- cut SMTP routes;
- restart workers;
- migrate the database;
- rotate TLS/credentials;
- update infrastructure.

If the procedure must stop abruptly before draining, explicitly record that an **emergency stop** was used along with the heightened `UNKNOWN`/duplicate risk.

## 30. Resume and Backlog-Handling Runbook

### Step 1 — Verify Infrastructure

- Application is on the right version.
- Database and migrations are complete.
- SMTP connectivity, credentials, and TLS are valid.
- Queues, brokers, and workers are healthy.
- No old pods are still running incompatible logic.

### Step 2 — Classify Backlog

- Still-valid pending jobs.
- Due retries.
- Expired/Cancelled jobs.
- `UNKNOWN` items needing reconciliation.
- Missed recurring occurrences needing catch-up.
- Jobs suppressed or affected by consent changes.

### Step 3 — Materialize/Catch Up Recurring Schedules

Generate missed occurrences per timezone/recurrence policy. Use unique keys to avoid duplicates.

### Step 4 — Canary Resume

Unpause a controlled scope or cap worker concurrency/rate. Watch accepted/4xx/unknown rates and queue lag.

### Step 5 — Full-Scope Resume

Once metrics stabilize:
- unpause remaining scopes;
- maintain quotas/bounded concurrency;
- do not reset attempts;
- watch the backlog drain down.

### Step 6 — Close Incident/Maintenance Report

Record:
- total paused duration;
- number of caught-up jobs sent;
- number of expired/cancelled jobs;
- `UNKNOWN` attempts;
- errors/retries;
- whether any recurring schedules were missed;
- action items to improve the runbook.

## 31. Failure Modes to Distinguish

| Symptom | Possible cause | Fix |
|---|---|---|
| Paused, yet SMTP still receives some calls | In-flight jobs claimed before pause | Drain, check ownership |
| Pod A stopped, but Pod B keeps sending | Local pause instead of cluster-wide | Shared gate/atomic claim |
| Everything bursts after restart | In-memory pause flag lost, due backlog | Persist gate, controlled resume |
| Schedules lost after maintenance | Only used in-memory scheduler/queue | Durable outbox/recurrence |
| Old OTP emails sent after maintenance | Missing `expires_at` check | Expire before submission |
| Duplicate sends during recovery | Expired lease treated as unsent | `UNKNOWN`/reconciliation |
| Claims stopped, but cron still creates jobs | Pausing dispatch does not pause materializer | May be intentional; make scope explicit |
| Missing jobs for downtime days | Materializer was also stopped | Catch up per recurrence |
| Database migration stuck | Workers still holding transactions/locks | Drain, keep transactions short |
| Claim happened after pause commit | Reading flag was not atomic with claim | DB lock gate/fencing protocol |
| Resumed, yet workers stay stopped | Scheduled task was canceled and never restarted | Synchronize lifecycle with gate |
| `QueueChannel` fills up on resume | Producer faster than consumer | Backpressure/rate limits, durable storage |
| Provider 451 spikes sharply | Backlog burst exceeded quota | Gradual resume, jitter/concurrency |
| Schedule fires at wrong timezone | Recomputed using system default zone | Store `Instant`/`ZoneId`, test DST |
| Marketing sent even though user opted out | Consent not revalidated before sending | Suppression policy at dispatch |
| Operator mistakes `PAUSED` for `DRAINED` | API does not separate the two states | Distinguish responses and dashboards |
| Resume command overwritten | Concurrent operators/automations racing | Versioning/CAS, audit |
| TLS errors right after SMTP maintenance | Credentials/certs/hostname changed | Smoke test with proper TLS policy |
| Logs contain full email bodies | Excessive debug/exception logging | Redaction and log access controls |
| Scope A paused, yet job routed to B | Routing ran after gate check | Check the gate of the actual route |

## 32. Unit Testing the Pause Mechanism

Test the coordinator layer without real SMTP:

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.*;

import java.util.List;
import org.junit.jupiter.api.Test;

class MailClaimCoordinatorTest {

    @Test
    void pausedGateDoesNotClaimJobs() {
        DispatchControlRepository controls =
            mock(DispatchControlRepository.class);

        ScheduledMailRepository repository =
            mock(ScheduledMailRepository.class);

        when(controls.lockGlobal())
            .thenReturn(new DispatchGate(true, 42));

        MailClaimCoordinator coordinator =
            new MailClaimCoordinator(controls, repository);

        List<ClaimedMail> claimed =
            coordinator.claimDue(20);

        assertThat(claimed).isEmpty();
        verifyNoInteractions(repository);
    }

    @Test
    void unpausedGateAllowsClaim() {
        DispatchControlRepository controls =
            mock(DispatchControlRepository.class);

        ScheduledMailRepository repository =
            mock(ScheduledMailRepository.class);

        when(controls.lockGlobal())
            .thenReturn(new DispatchGate(false, 43));

        when(repository.claimDueBatch(5))
            .thenReturn(List.of());

        MailClaimCoordinator coordinator =
            new MailClaimCoordinator(controls, repository);

        coordinator.claimDue(5);

        verify(repository).claimDueBatch(5);
    }
}
```

These tests verify branch logic; they **do not prove row locking or concurrency on a real database**. Integration tests are needed for that.

### 32.1. Test That Producers Do Not Lose Data While Paused

If business services still accept requests during maintenance, test that:
- the outbox job is persisted;
- `status=PENDING`;
- no new attempt is created;
- `JavaMailSender` is not called;
- the API returns "queued/pending" semantics, not "delivered."

### 32.2. Test That Cancellation Does Not Break Pause

If a user cancels a queued job during maintenance, upon resume that job must stay `CANCELLED` and not be claimed. Global pause and per-job cancellation must interact cleanly.

## 33. Integration Testing With PostgreSQL Testcontainers

To verify gate atomicity, run the real repository on a database with production-compatible semantics.

### 33.1. Test Setup

- PostgreSQL in Testcontainers.
- Application migrations/schema.
- Real Spring transaction manager and repository.
- Two coordinator instances/threads using separate database connections.
- SMTP gateway as a test double so no external emails are sent.
- Controllable `Clock` to test due times.
- Explicit test cleanup and isolation.

### 33.2. Scenario: Pause Committed Before Claim

1. Insert a due `PENDING` job.
2. Commit `paused=true`.
3. Call `claimDue(1)`.
4. Assert the result is empty.
5. Assert the job remains `PENDING` with `attempt_count=0`.
6. Assert zero SMTP calls.

### 33.3. Scenario: Concurrent Claim and Pause

Use `CountDownLatch`/transaction barriers:
- Worker A starts claiming and holds the lock on the control row.
- Operator B calls pause in another transaction.
- Confirm B cannot commit before A releases the lock.
- After A commits, B commits the pause.
- Worker C starts claiming after B commits and gets an empty result.
- Jobs claimed by A count as valid in-flight work.

What matters is the **commit order**, not just log statement order. Do not rely on random `Thread.sleep` calls hoping to hit a race.

### 33.4. Scenario: Two Nodes Pausing Simultaneously

Two operators request a pause together, or automation retries a request. Verify:
- the final state is paused;
- there is no unexpected transition back to resumed;
- generation/audit conforms to contract;
- no duplicate email attempts occur as a side effect of pausing.

### 33.5. Scenario: Resume After Restart

1. Pause in the database.
2. Start a new worker / restart the Spring context against the same database.
3. Verify it still does not claim jobs.
4. Resume with an authorized command.
5. Claim eligible jobs.
6. Do not send jobs that are `CANCELLED`/`EXPIRED`/`SMTP_ACCEPTED`.

### 33.6. Scenario: DB Failure After SMTP Accepted

Have the fake gateway simulate acceptance, then force the repository outcome update to fail. Verify that the system does **not** simply flip the job back to pending and resend on the next poll; it must go through recovery/reconciliation.

## 34. Testing Graceful Shutdown and In-Flight Drain

A useful integration test uses a **blocking fake gateway**:

```text
Test starts one email submission
       |
       v
Fake gateway signals "send started"
       |
       +--> blocks on latch
       |
Test calls pause
       |
       v
No new claims allowed
       |
Release gateway latch
       |
       v
Worker persists outcome
       |
       v
Drain eventually reaches 0
```

Assertions:
- The first attempt can finish.
- Another attempt is not claimed after pause.
- Drain does not report complete while the gateway is still blocked.
- When the gateway releases, the state is persisted.
- If the worker dies or times out, drain reports unresolved/`UNKNOWN` per contract.
- No real SMTP provider is needed to verify orchestration.

### 34.1. Bounded Waits Instead of Arbitrary Sleeps

Use:
- `CountDownLatch` for synchronization;
- `Future.get(timeout, unit)` to prevent hanging tests;
- test schedulers/clocks to control timestamps;
- bounded polling assertions when testing async behavior;
- thread/resource cleanup between tests.

Do not rely on `Thread.sleep(10000)` and assume "draining must be done."

### 34.2. Testing Process Termination

A dedicated deployment test suite can:
- send `SIGTERM` to a worker;
- verify it stops claiming;
- await in-flight work within the grace period;
- restart the worker against the same DB;
- verify zero job loss;
- handle stale leases/`UNKNOWN`.

This is an integration/system test, not a single-method unit test.

## 35. Testing Backlogs, Catch-Up, and Deadlines

After a long maintenance window, tests need multiple job types:

```text
Job A: PENDING, due 08:00, expires tomorrow
Job B: PENDING, due 08:30, expired 09:00
Job C: RETRY_WAIT, next attempt due 08:45
Job D: SMTP_ACCEPTED
Job E: UNKNOWN
Job F: CANCELLED
```

When resuming at 10:00:
- A is eligible.
- B is marked expired and not sent.
- C is eligible under retry budget if still valid.
- D is not resubmitted.
- E is not automatically resubmitted.
- F is not sent.

Add a recurring schedule:
- Occurrences exist for three days of downtime.
- Catch-up creates only the periods allowed by policy.
- Each occurrence has a unique key to avoid duplicates even if the materializer runs twice.
- `sendAt` timestamps are computed from local date/time + `ZoneId`, not by merely adding UTC hours.

### 35.1. Testing Gradual Resume

Simulate quota/provider limits:
- cap concurrent sends;
- cap submissions per second;
- assert the backlog decreases at a controlled pace;
- assert the budget is never exceeded;
- when the provider returns rate limits, jobs back off without causing a storm.

### 35.2. Testing Maintenance Spanning DST

A `Europe/Berlin` recurring schedule has a run on the DST transition day:
- apply the stored gap/overlap policy;
- do not create two unintended occurrences;
- do not drop a valid period;
- resuming does not alter the chosen `ZoneId`.

## 36. Practice Exercises

### Exercise 1 — Distinguish Pause and Cancel

Write a contract description for `PAUSED`, `DRAINING`, `DRAINED`, `CANCELLED`, `SMTP_ACCEPTED`, and `UNKNOWN`. Identify which states are global controls and which belong to individual jobs.

### Exercise 2 — In-Memory Gate Is Not Enough

Suppose three pods each have `volatile boolean paused`. Explain why toggling it on pod A does not guarantee B/C stop sending and why a restart can reset the flag.

### Exercise 3 — Control Table

Create `mail_dispatch_control` with scope, paused, generation, and audit fields. Write a migration creating the initial `GLOBAL` row.

### Exercise 4 — Atomic Pause/Claim

Use PostgreSQL `SELECT ... FOR UPDATE` on the control row, then `FOR UPDATE SKIP LOCKED` to claim due jobs. Test that when pause commits before claim, no job is picked up.

### Exercise 5 — Pause and Drain Commands

Write an admin API:
- `pauseGlobal` updates the gate;
- `getDrainStatus` returns active attempts;
- `resumeGlobal` allows only authenticated operators.

Distinguish the `PAUSED` response from `DRAINED`.

### Exercise 6 — Race Between Send and Pause

Use a blocking fake SMTP gateway and a latch. Pause while a send is blocked. Verify that the already claimed job can finish while a new job cannot be claimed.

### Exercise 7 — Graceful Shutdown

Design a shutdown sequence in Spring Boot: stop the dispatcher, await the worker pool, persist outcomes, and only then close the datasource. Explain why simple `@PreDestroy` is insufficient.

### Exercise 8 — Kubernetes

A deployment has three replicas and a 30-second `terminationGracePeriod`. Design a global pause before SMTP maintenance, contrasting it with pod-local draining during a rolling deploy.

### Exercise 9 — Retry Across Maintenance

A job has `next_attempt_at=09:05`, while the system is paused 09:00–10:00. After resume, it must retry according to budget without incrementing `attempt_count` due to poller ticks during maintenance.

### Exercise 10 — Expired Token

A verification email has `expires_at=09:30` and pause lasts until 10:00. Prove the job is not submitted after resume and transitions clearly to `EXPIRED`.

### Exercise 11 — `UNKNOWN`

Simulate SMTP acceptance followed by a failed database update. After restart and resume, test that the worker does not automatically resend while the outcome remains unreconciled.

### Exercise 12 — Multi-Provider Pause

Pause `PROVIDER:A` while letting `PROVIDER:B` continue. Write routing and scope-checking rules so an email cannot be sent through the wrong provider due to rerouting after the gate check.

### Exercise 13 — Recurring Catch-Up

The app missed two daily report triggers. Generate occurrences from the recurrence definition and unique `(scheduleId,localDate,slot)`. Run catch-up twice and assert zero duplicates.

### Exercise 14 — Pause the Materializer Too

Compare two modes: pausing dispatch while continuing to create jobs, versus pausing the schedule materializer too. Analyze recovery after DB downtime.

### Exercise 15 — Backlog After Resume

There are 20,000 due jobs and the provider has a tight quota. Design gradual resume using worker concurrency, rate limiting, jitter, and monitoring metrics.

### Exercise 16 — Cancellation Race

A user cancels an email right as a worker claims it. Design an optimistic lock or conditional update to determine accurately whether cancellation succeeded before the side effect.

### Exercise 17 — Schedules Across DST

Maintenance spans March 29, 2026 in Berlin. A recurring schedule at 02:30 hits a gap; choose a `SKIP` or `SHIFT` policy and prove catch-up does not create an email at an invalid time.

### Exercise 18 — Rotating SMTP Credentials

Pause the profile, drain, swap in a sender instance with new credentials, smoke-test a test mailbox, and resume. Do not mutate an in-use singleton `JavaMailSenderImpl`.

### Exercise 19 — Maintenance Audit

Design an audit table containing operator, scope, generation, reason, pause/resume timestamps, and drain status. Do not record SMTP passwords or email contents.

### Exercise 20 — Reconciliation Report

Given three attempts: `SMTP_ACCEPTED`, `DEAD_LETTER`, and `UNKNOWN`. Produce a maintenance report permitting resends only for jobs classified as safe; explain why `UNKNOWN` cannot be assumed unsent.

## 37. Summary

**Safely pausing scheduled sending during maintenance** in Spring Framework Mail is not just turning off `@Scheduled` or setting a boolean variable. It is a system-wide stateful orchestration process with a cutoff for new jobs, a drain mechanism for in-flight sends, durable data for recovery, and a resume policy for handling backlogs.

Core principles:

1. **Distinguish pause, drain, and cancel.** Pause blocks new claims; drain manages in-flight work; cancel stops a job for business reasons.
2. With multiple workers/pods, you need **a durable, shared gate synchronized with atomic claims**. Local flags are insufficient.
3. **Do not hold a DB transaction across SMTP.** Claiming and persisting outcomes are short transactions separated from network side effects.
4. After pause commits, jobs **already claimed beforehand may still send**. To stop safely, wait until `DRAINED` or record unresolved attempts.
5. **Do not blindly resend when leases expire or SMTP outcomes are `UNKNOWN`.** The relay may have accepted the email before the worker was killed.
6. Use **durable outbox/recurring schedule definitions** to preserve jobs across restarts instead of relying on timers or an in-memory `QueueChannel`.
7. On resume, **check deadlines, consent, cancellations, retry budgets, and backlog**, then reopen gradually per quota rather than dumping everything onto the provider.
8. If pausing affects **recurring materialization**, perform idempotent catch-up by local date/time/`ZoneId`, including DST transition days.
9. **Scheduled send time is not delivery time.** A successful `JavaMailSender.send(...)` call does not guarantee the email reached the Inbox.
10. Operations must include **authorization, auditing, metrics, runbooks, rollback capability, and integration tests for races and persistence**.

When you design clear boundaries — **no new claims -> finish or reconcile in-flight attempts -> maintenance -> controlled resumption** — an application can pause and resume scheduled sending predictably, minimize lost jobs, avoid duplicate sends, and preserve the user's intended timing.
