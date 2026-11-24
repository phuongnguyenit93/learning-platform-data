# Distinguishing Once-Per-Process Initialization from System-Wide Once-Only Work

## 1. Core Problem: "Run Once" Is an Insufficiently Clear Contract

In Spring Boot, **ApplicationRunner** and **CommandLineRunner** are invoked by SpringApplication after the ApplicationContext has refreshed and before the application becomes ready. They are well suited for initializing caches, checking configuration, or performing startup tasks. However, saying "a runner runs once" **does not mean the task runs strictly once across the entire distributed system**.

An application can have multiple JVM processes, Pods, containers, replicas, servers, or restarts. Every time a SpringApplication with runner beans starts successfully up to the runners phase, those runners execute again. Therefore, if you place sending welcome emails, writing initial data, or periodic billing directly inside a runner without shared control, **every instance can re-execute the task**.

There are two very different kinds of requirements:

- **Local per-startup initialization for each process/instance:** each JVM or ApplicationContext needs to prepare its own resources. Repeating after a restart is desired behavior.
- **Work applied once system-wide:** replicas and restarts all observe the completed state and must never produce duplicate side effects for the same **business key**. This requirement needs a coordination or uniqueness-enforcement mechanism **outside each JVM's memory**.

This lesson focuses on choosing where to place logic, race conditions across multiple instances, transactions, idempotency, and the practical limits of "exactly once" promises.

## 2. What Contract Do Runners Actually Have?

Spring Boot supports two runner types:

~~~java
public interface ApplicationRunner {
    void run(ApplicationArguments args) throws Exception;
}
~~~

~~~java
public interface CommandLineRunner {
    void run(String... args) throws Exception;
}
~~~

These are **abbreviated signatures for learning**, omitting packages and annotations; when coding, use the official interfaces in **org.springframework.boot**. Both bean types are called in the **SpringApplication.run(...)** chain after **ApplicationStartedEvent** and before **ApplicationReadyEvent**. They differ primarily in how they receive arguments: ApplicationRunner receives parsed **ApplicationArguments**; CommandLineRunner receives the raw argument array.

Key points to distinguish:

1. For a single startup reaching the runners phase with a registered runner bean, SpringApplication normally invokes **run(...) once for that bean during that startup**.
2. If the process restarts, that is **a new startup** and the runner gets another chance to run.
3. If **three replicas** are deployed, each replica has its own JVM/context and can run the same runner—typically three independent startups.
4. If multiple SpringApplications or a specialized context hierarchy exist within one JVM, evaluate each context; never treat "once per JVM" as an absolute API guarantee.
5. Multiple runner beans may exist. **@Order/Ordered** only orders runners within **a single SpringApplication**, not across different JVM processes.
6. If a runner throws an exception, startup fails before the successful ready branch. An orchestrator may restart the instance, in which case the runner may **be called again**.

**Accurate terminology:** A runner is a **per-application-startup** hook, not a "run once for the whole cluster" service. If you need to assert a task runs once system-wide, define the scope and enforcement mechanism independently of runners.

## 3. Two Models Side by Side

| Criterion | Once per startup/instance | Once system-wide by key |
| --- | --- | --- |
| Scope | The starting JVM/ApplicationContext | Shared data store or coordinator across instances |
| On restart | Usually must run again | Do not rerun if the same key already completed |
| Scaling from 1 to 3 Pods | Each Pod runs its own initialization step | Only one business outcome accepted for the same key |
| Core mechanism | Runners, bean lifecycle, initialization | Unique constraints, transactions, idempotency, coordination/job orchestration |
| State in Java variables | Can fit local state | Insufficient because each process has separate memory |
| Pod or JVM loss | RAM state vanishes; fresh startup redoes it | Completion state must live in an external durable store |
| Common goals | Node-local cache loading, metrics init, connection setup | Versioned seed data, periodic once-only task dispatch, migrations |
| Critical tests | Restarts, startup failures, runner order | Concurrent replicas, crashes/retries, duplicate requests, atomicity |

Example of **per-process initialization**: Each replica needs a warm cache to serve HTTP requests. Replica A loads cache A; replica B loads cache B. If B did not reload its cache on restart, B would serve requests with incomplete state. Thus **repeating is the right behavior**.

Example of **once system-wide**: The system needs to record "standard data pack v3 applied" in a shared database. If every replica inserts the same dataset on startup, duplicate records or duplicate side effects can occur. You need control via data constraints, transactions, and a key identifying data pack v3.

## 4. First Question: "Once" by Which Key?

Before choosing a tool, define the exact **unit of work**. "Once" can mean many things:

- **Once per launch:** each instance initializes local state.
- **Once in the entire product lifetime:** e.g., creating an initial catalog when installing a brand-new system.
- **Once per data version:** e.g., applying seed script version v3 strictly once, while v4 is a new unit of work.
- **Once per customer:** each tenant gets onboarding resources created once.
- **Once per period:** sending a notice or closing billing per composite key (tenant, month, report type).
- **Once per business request:** each idempotency key produces one logical effect, even if the client retries.

Without defining a key, a "run once" mechanism might block legitimate future work or allow duplicating old work.

Examples of keys:

~~~text
seed:catalog:v3
tenant:acme:onboarding:v1
billing:tenant-42:2026-11
report:customer-123:month-2026-10
~~~

**Never use startup timestamp, hostname, or Pod UID as the key for system-wide once-only work**, because those values change across restarts/scale-outs. They are only suitable when per-instance behavior is intentional.

## 5. Why Static Variables, AtomicBoolean, and "Does It Exist Yet?" Checks Are Insufficient

### 5.1. In-Memory Variables Only Protect JVM Scope

~~~java
private static final AtomicBoolean initialized = new AtomicBoolean();

public void run(ApplicationArguments args) {
    if (initialized.compareAndSet(false, true)) {
        // Only one thread in this JVM wins.
    }
}
~~~

This is an **illustrative snippet inside a Java class**; it requires importing AtomicBoolean and ApplicationArguments. It can prevent an operation from being re-executed by threads sharing the same variable within **one JVM**, yet:

- Each replica has its own static variable; every replica can observe false.
- Restarting the JVM resets the variable to its initial state.
- If marked true first and the job then fails, subsequent calls in that JVM may never retry.
- It does not guarantee a single effect in a database or external service.

### 5.2. Check-Then-Write Creates a Race Condition

Problematic code:

~~~text
if (database.doesNotContain("seed:v3")) {
    database.insert("seed:v3");
    performBusinessEffect();
}
~~~

This is **pseudocode**, not runnable Java. Consider two replicas A/B:

~~~text
Time      | Replica A                     | Replica B
----------+-------------------------------+----------------------------
T1        | SELECT: seed:v3 absent yet    |
T2        |                               | SELECT: seed:v3 absent yet
T3        | insert seed:v3                |
T4        |                               | insert seed:v3
T5        | execute side effect           | execute side effect
~~~

Both can pass the initial check before the other writes. **SELECT followed by INSERT is not an atomic operation**. Even using a normal transaction without a unique constraint or proper locking does not necessarily eliminate the race.

### 5.3. @Order Is Not a Distributed Lock

~~~java
@Order(1)
@Component
class OnceRunner implements ApplicationRunner {
    // ...
}
~~~

**@Order** orders runners inside the current context. If there are five replicas, all five still have an order-1 runner and can execute concurrently. Ordering inside each JVM does not become cluster-wide ordering.

## 6. Four Frequently Confused Guarantee Levels

| Goal | Meaning | Remaining Risk |
| --- | --- | --- |
| At-most-once attempt | Avoid retrying the same job | If a crash occurs after marking "claimed" yet before the effect, work may be skipped |
| At-least-once attempt | Retry until an acceptable outcome occurs | May run multiple times; requires idempotency |
| Single DB effect per key | Data store rejects or turns duplicate writes into no-ops | Applies only inside the protected DB/transaction; does not cover email, HTTP, or queues automatically |
| Exactly-once end-to-end | Every externally observable side effect occurs once | Very hard when multiple systems do not share a transaction; needs per-target contracts/idempotency/coordination |

**Key point:** Unique keys and transactions can make a **change within the same database** happen at most once per key. That **does not prove `run(...)` was called only once** and does not prove external email/API calls were processed only once.

Example scenario you cannot deduce from logs:

~~~text
Worker sends API request successfully
       |
       +-- Process crashes before saving "DONE"
       |
Restart -> unknown whether API succeeded -> retry
~~~

Without an idempotency key supported by the target system, the retry can create duplicate effects. To achieve near exactly-once at the business level, clearly define who owns state, idempotency keys, outcome verification, and recovery policies when responses are lost.

## 7. Recommended Architecture: Local Runners + Shared Uniqueness Condition

An effective structure:

~~~text
             +-------------------+
Pod A ------>|                   |
Pod B ------>| Shared database   |-- Unique work_key
Pod C ------>|                   |-- Transaction
             +-------------------+
    |                   |
    |                   v
    +-- Local init      Accepted effect for work_key
        (per Pod)       (one business outcome)
~~~

For **changes contained entirely within a single database**:

1. Create a durable business key, such as **seed:catalog:v3**.
2. Enforce a **UNIQUE constraint / PRIMARY KEY** on the key.
3. Perform **the claim and DB effect within the same transaction**, if both steps are needed. If the effect fails, the transaction must roll back the claim too.
4. When another run encounters a duplicate key, verify the outcome is complete; if valid, skip idempotently; if inconsistent, raise an error.
5. When bumping versions or changing job scope, use a new controlled key.
6. Use a **genuinely shared** database across replicas (PostgreSQL, MySQL, or a system with suitable transactions and unique constraints). Avoid separate files inside each container.

**Note on database isolation:** Do not rely solely on "did SELECT find it?". A UNIQUE constraint is the uniqueness gate where data is written. Transactions ensure writes to **the same database** commit or roll back together; verify the exact duplicate error types and retry policy for your specific database.

## 8. Runnable Example: Spring Boot 3.x / Java 17+ with Disk-Backed H2

The example demonstrates both behaviors:

- **LocalInitRunner** always runs on every SpringApplication startup, printing a local initialization notice.
- **GlobalOnceRunner** is also always called, yet thanks to a **unique key + transaction**, the database write side effect is applied only the first time for the same key.

The example uses a **file-backed H2 database** to run sequentially multiple times on one machine and observe data persisting across restarts. **File-backed H2 is not a real cluster coordination solution**; in multi-Pod/multi-machine production, replace it with a shared database offering proper concurrency, backups, and HA.

### 8.1. Project Structure

~~~text
runner-scope-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        demo/
          RunnerScopeDemo.java
      resources/
        application.properties
        schema.sql
~~~

File **settings.gradle**:

~~~groovy
rootProject.name = 'runner-scope-demo'
~~~

File **build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
~~~

Spring Boot 3.3.x and JDK 17+ are the target baseline for the example. The project requires a compatible Gradle installation and repository access or cached dependencies.

### 8.2. Configuring On-Disk H2 Connection

File **src/main/resources/application.properties**:

~~~properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.main.log-startup-info=false

spring.datasource.url=jdbc:h2:file:./once-demo-db
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
~~~

**jdbc:h2:file:./once-demo-db** stores the database relative to the application's working directory, so results persist after the JVM exits. **Do not use jdbc:h2:mem:** for restart tests, because ordinary in-memory databases vanish when the process closes.

In this example, runs execute **sequentially** with the same working directory. File-backed H2 in default embedded mode is not meant for multiple independent Pods accessing it simultaneously; if testing multiple concurrent JVMs, consider H2's client/server or mixed mode and its constraints. System-wide work in production requires a genuine shared data store.

File **src/main/resources/schema.sql**:

~~~sql
CREATE TABLE IF NOT EXISTS run_claim (
    work_key VARCHAR(120) PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS setup_effect (
    work_key VARCHAR(120) PRIMARY KEY,
    detail VARCHAR(200) NOT NULL
);
~~~

Spring Boot runs SQL initialization at startup with **spring.sql.init.mode=always**. **IF NOT EXISTS** prevents later runs from wiping data. For real databases, use a migration tool with history and locking such as Flyway/Liquibase rather than managing schemas long-term via startup scripts.

### 8.3. Complete Java Code

File **src/main/java/demo/RunnerScopeDemo.java**:

~~~java
package demo;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@SpringBootApplication
public class RunnerScopeDemo {
    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(RunnerScopeDemo.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("MAIN_RETURNED");
        }
    }
}

@Component
@Order(10)
class LocalInitRunner implements ApplicationRunner {
    @Override
    public void run(ApplicationArguments args) {
        // Example for per-startup / per-instance init.
        System.out.println("LOCAL_INITIALIZED");
    }
}

@Service
class OnceWorkService {
    static final String WORK_KEY = "seed:catalog:v1";

    private final JdbcTemplate jdbc;

    OnceWorkService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void applyOnce() {
        // Claim and business effect are in the same DB transaction.
        jdbc.update(
                "INSERT INTO run_claim (work_key) VALUES (?)",
                WORK_KEY);

        jdbc.update(
                "INSERT INTO setup_effect (work_key, detail) VALUES (?, ?)",
                WORK_KEY, "initialized catalog v1");
    }

    public boolean isComplete() {
        Integer claims = jdbc.queryForObject(
                "SELECT COUNT(*) FROM run_claim WHERE work_key = ?",
                Integer.class, WORK_KEY);

        Integer effects = jdbc.queryForObject(
                "SELECT COUNT(*) FROM setup_effect WHERE work_key = ?",
                Integer.class, WORK_KEY);

        return claims != null && claims == 1
                && effects != null && effects == 1;
    }
}

@Component
@Order(20)
class GlobalOnceRunner implements ApplicationRunner {
    private final OnceWorkService onceWorkService;

    GlobalOnceRunner(OnceWorkService onceWorkService) {
        this.onceWorkService = onceWorkService;
    }

    @Override
    public void run(ApplicationArguments args) {
        try {
            onceWorkService.applyOnce();
            System.out.println("GLOBAL_EFFECT_APPLIED");
        } catch (DuplicateKeyException duplicate) {
            // Ignore only if the earlier process completed properly.
            if (!onceWorkService.isComplete()) {
                throw duplicate;
            }
            System.out.println("GLOBAL_ALREADY_COMPLETED");
        }
    }
}

@Component
class ReadyObserver {
    @EventListener(ApplicationReadyEvent.class)
    public void onReady() {
        System.out.println("APPLICATION_READY");
    }
}
~~~

Part-by-part explanation:

1. **LocalInitRunner** prints **LOCAL_INITIALIZED** on **every startup** reaching runners. This is the right behavior for per-instance local initialization.
2. **GlobalOnceRunner** is also called on every startup; it is **not** a special cluster-wide run-once runner.
3. **OnceWorkService.applyOnce()** is a **@Transactional** method on a separate Spring service. The runner calls the method through the injected bean, allowing Spring's transaction proxy to apply. Never call **this.applyOnce()** from inside the same service expecting a transaction automatically.
4. The INSERT into **run_claim** requires WORK_KEY not to exist yet; PRIMARY KEY prevents two transactions from committing duplicate keys.
5. The INSERT into **setup_effect** is a **simulated business side effect in the same DB**. If this step fails, the RuntimeException rolls back the transaction under default transaction settings, so the claim is not committed on its own.
6. When the key already exists, JDBC throws **DuplicateKeyException**. The runner catches the exception **outside the @Transactional method**, after the failed transaction has ended, and calls **isComplete()** to verify both claim and effect.
7. If the claim exists yet the effect is missing (manual data tampering or an abnormal failure), the program **does not silently treat it as complete**, instead rethrowing the error.
8. **@Order(10)** and **@Order(20)** ensure that within the same context, LocalInitRunner runs before GlobalOnceRunner. **@Order does not synchronize across different instances**.
9. **ApplicationReadyEvent** appears after runners complete on the success branch. Main closes the context after SpringApplication.run(...) returns, because the demo is a one-shot job rather than a long-lived web service.

### 8.4. Running Twice and Observing

If the project has a Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

If there is no wrapper yet, use an installed compatible Gradle version:

~~~bash
gradle bootRun
~~~

**First run** with a fresh database, lines printed by the program in order:

~~~text
LOCAL_INITIALIZED
GLOBAL_EFFECT_APPLIED
APPLICATION_READY
MAIN_RETURNED
~~~

**Second run**, rerunning the project from the same working directory while keeping the H2 files, lines printed by the program:

~~~text
LOCAL_INITIALIZED
GLOBAL_ALREADY_COMPLETED
APPLICATION_READY
MAIN_RETURNED
~~~

Spring Boot, HikariCP, and Gradle may print additional log lines; listed here are only the lines printed by the example. The H2 database is stored on disk. If you change working directory or delete the DB files, you have created a new data store, so the next run is treated as the first run again.

**Experiment conclusion:** both runners execute on every startup. Only **the keyed DB write side effect** is protected against duplicate creation on rerun.

### 8.5. Failure Scenario and Transaction Check

If you replace the second INSERT in **applyOnce()** with a SQL statement causing a RuntimeException, under a proper transaction the earlier claim insert rolls back. The next startup can retry because the claim was not falsely marked complete. This is the **atomic claim + effect** principle.

Never use this experiment as proof of "exactly once for Kafka/email/HTTP." It merely creates two rows within **the same H2 database transaction**. In real products, use shared PostgreSQL/MySQL and test concurrency, deadlocks, isolation, timeouts, unique constraints, and the real transaction manager.

## 9. When Multiple Replicas Start Concurrently

Suppose Pods A, B, and C start together and each has GlobalOnceRunner. What should happen:

~~~text
Pod A ---> INSERT work_key=seed:catalog:v1 ---+
Pod B ---> INSERT work_key=seed:catalog:v1 ---+--> Shared DB PRIMARY KEY
Pod C ---> INSERT work_key=seed:catalog:v1 ---+
                                               |
                                      One transaction commits
                                      The other two see duplicate
                                               |
                                      Only one valid DB outcome
~~~

This is a simplified view. Real contention may cause a transaction to **wait on locks**, encounter **unique violations**, time out, or hit other transaction errors depending on the database and isolation level. You need a retry policy for **retryable** errors (such as deadlocks/serialization failures) rather than lumping every SQL error into the "already completed" branch.

With PostgreSQL, you can use this syntax:

~~~sql
INSERT INTO run_claim(work_key)
VALUES ('seed:catalog:v1')
ON CONFLICT (work_key) DO NOTHING
RETURNING work_key;
~~~

**Only the process receiving the RETURNING row executes the subsequent business SQL statements**, and those statements must reside in **the same transaction** as the claim if they must commit/roll back together. If no RETURNING row is received, verify completion state. The SQL above is a **PostgreSQL illustrative snippet**, not a portable command across all databases.

A separate claim table is not strictly necessary if **the business effect record** already has a PRIMARY KEY/UNIQUE constraint on the exact key; in that case, direct idempotent insert/upsert can be simpler. Choose the design with the fewest moving states that still satisfies the contract.

## 10. Choosing Tools by Type of System-Wide Work

### 10.1. Database Migrations: Flyway or Liquibase

For versioned schema changes and versioned seeds, use **Flyway** or **Liquibase**. They track migration history and use appropriate coordination/locking to avoid applying the same migration concurrently on a shared database. When multiple instances start, they may **concurrently check migration state**, yet a version already applied successfully will not be rerun as a new migration.

Notes:

- Migrations cover only **the database and the version scope managed by the tool**.
- Analyze how failed migrations or non-transactional DDL are handled per database.
- Do not conclude "each app runs migrations once"; individual instances may still run migration-check logic.
- Avoid putting complex schema-change logic directly inside an ApplicationRunner when a standard migration tool fits the requirement.

### 10.2. Separate Infrastructure-Orchestrated Jobs

If the task is a large data import, index build, or periodic campaign run, extract it into a **Job** instead of running it on every web service replica. In Kubernetes, a **Job** is configured with completions/parallelism/backoff as needed; in CI/CD, there may be a dedicated migration or provisioning step.

Yet a **Kubernetes Job does not automatically provide exactly-once for all side effects**: Pods can be replaced, and tasks can rerun due to errors or retries. Job logic should still be idempotent or keyed, especially when interacting with external services.

The strength of a separate Job is decoupling **shared job lifecycle** from **per-Pod startup lifecycle**. Web services can simply read prepared data instead of running a copy of a heavy job on every scale-out.

### 10.3. Distributed Locks, Leader Election, and Leases

If only one instance is allowed to **execute concurrently** a piece of code, you can use a lock in a database, Redis, or an orchestrator supporting leader election.

However, **"one instance at a time" differs from "only one side effect ever exists"**:

- If the leader crashes, its lease expires and another instance can take over.
- The old leader may briefly lose connectivity and continue performing side effects after its lease was superseded.
- To block stale owners, sensitive systems need **fencing tokens** or compare-and-set/transactions where the effect is written.
- If DONE status is written before the side effect, crashing in between can lose the task.
- If the side effect runs before DONE, crashing in between can duplicate the side effect on retry.

Locks solve only part of the coordination problem; you still need **idempotency** or **atomic commits** at the point where side effects occur.

### 10.4. Spring Batch and JobRepository State

For multi-step batch jobs with checkpoints, restarts, and chunk processing, **Spring Batch** provides JobRepository, JobParameters, JobInstance, and JobExecution to track and coordinate job lifecycles. Choosing JobParameters carefully matters because they affect the identity of a JobInstance.

Spring Batch does not automatically deliver "exactly once across every remote service." Job restarts/retries and external side effects still require idempotency, transaction boundaries, and appropriate recovery.

### 10.5. Queues and Transactional Outbox

For sending emails, payments, REST integrations, or message brokers, consider the **outbox** pattern:

1. Within the business DB transaction, save **the outcome record + outbox event** with a unique key.
2. An independent worker reads outbox events and dispatches them to the target system.
3. The worker can retry; the target system or consumer needs an **idempotency key/deduplication**.
4. Record delivered/processed status per contract; monitor failed events and dead letters.
5. If the external party processed the request yet the response was lost, retrying with the same idempotency key avoids duplicate effects **if the target supports it**.

This pattern is usually superior to having a runner directly send an email once and then mark DONE in the database, because a DB and an external SMTP/API do not share an ordinary atomic transaction.

## 11. Does "Once Before Ready" Differ from "Once System-Wide"?

**Yes.** Runners execute before ApplicationReadyEvent in Spring Boot's startup flow. That creates a **per-instance readiness barrier**: if a runner must complete, that instance does not enter the successful ready branch yet.

Yet with multiple replicas:

~~~text
Replica A: Started -> Runner A -> Ready A
Replica B: Started -> Runner B -> Ready B
Replica C: Started -> Runner C -> Ready C
~~~

Each replica has its own readiness. If Runner A must acquire a global key while Runners B/C must wait or check status, decide:

- **Must global work finish before any instance becomes ready?** If so, replicas must safely check completion status with timeouts/fail-fast; only one instance performs the effect.
- **Can partial functionality be served before the global job finishes?** You can separate the job and use feature readiness/health or a designed degraded mode, avoiding blocking all startups indefinitely.
- **Is it better to separate the global job from the web deployment?** Usually yes, especially for long migrations, large imports, email campaigns, or tasks with complex retries.

Never use **Thread.sleep()** or unbounded polling inside a runner to "wait for another replica." Establish deadlines, backoff, metrics, and clear job states. If system-wide work takes long, a dedicated job model is easier to operate.

## 12. Why Catching DuplicateKeyException Alone Is Still Not Enough

In the H2 example, on a duplicate key, **isComplete()** verifies both claim and effect. This is an important habit:

- If the system previously committed a **claim** without creating the **effect** due to a buggy deployment or manual intervention, a duplicate does not prove the job succeeded.
- If there are multiple job types, verify **the exact work_key and version/payload**.
- If the DB returns a timeout or network error, **never treat that error as "already completed."** The client may not know whether the transaction committed; query state from a trusted source.
- If executing side effects outside a transaction, store explicit states such as **PENDING**, **IN_PROGRESS**, **DONE**, **FAILED** and design clear recovery/leases. Never simply write DONE upfront and hope the side effect succeeds.

In real concurrent systems, writing claim and effect in one shared transaction ensures readers after commit see consistent state. Checking **isComplete()** after a duplicate does not replace transaction/constraint design, yet helps detect inconsistent data instead of failing silently.

## 13. Testing at the Right Scope

### Test 1 — Single-Instance Restart

Run the H2 example twice from the same working directory. Expectations:

- Both runs print **LOCAL_INITIALIZED**.
- Only the first run prints **GLOBAL_EFFECT_APPLIED**.
- The second run prints **GLOBAL_ALREADY_COMPLETED**.
- The database contains only one row for `work_key` in each table.

This tests **state persistence across restarts** on one machine, not a real cluster test.

### Test 2 — Failure Between Two SQL Statements

In a test environment, trigger a RuntimeException after inserting the claim yet before committing the effect. Verify the transaction rolls back the claim as well. Then rerun with fixed code; the job can still execute.

Do not induce this failure in production to "test your luck," and do not rely on stdout alone. Inspect actual database state.

### Test 3 — Concurrent Competing Instances

Run multiple instances connecting together to **the same PostgreSQL/MySQL test database** with the same key. Verify:

- Only one DB outcome commits for `work_key`.
- Remaining instances produce no duplicate effects.
- Duplicate errors are treated as "already completed" only when state is genuinely complete.
- Deadlock/timeout/serialization errors follow their own retry policy rather than being masked.
- No instance advertises ready while mandatory data is still missing.

### Test 4 — Crash After Commit, Before Success Log

Simulate process termination right after the transaction commits yet before the runner logs **GLOBAL_EFFECT_APPLIED**. On restart, the database must remain the source of truth: an already-committed key must not be written twice, even though the prior log never stated completion.

### Test 5 — External Non-DB Side Effects

Simulate an external API receiving the request while the client times out before receiving the response. Test retries with an idempotency key; if the target does not support one, provide reconciliation or compensation workflows. Never claim "exactly once" merely because the service has a distributed lock.

### Test 6 — Rollout and Scale-Out

In staging, deploy two or more replicas, perform rolling updates, kill a Pod mid-startup, and scale up then down. Verify durable state, uniqueness, readiness durations, retry behavior, error metrics, and absence of deadlocks.

## 14. Practical Decision Matrix

| Task | Correct Goal | Implementation Approach to Consider |
| --- | --- | --- |
| Populate local RAM cache | Per instance / per startup | ApplicationRunner or init service, safe to repeat |
| Validate bean config | Each time bean is created | Constructor / @PostConstruct / initMethod |
| Set up connection pool | Per ApplicationContext | Bean / DataSource lifecycle management |
| Mandatory warm-up before traffic | Per instance / per startup | Runner with timeout, readiness barrier |
| Schema migration version vN | Once per version and database | Flyway/Liquibase + migration history/locking |
| Create seed data vN | Once per version/tenant | Unique key + DB transaction, or idempotent migration |
| Send welcome email to tenant | One logical effect per tenant/event key | Outbox, sender/receiver idempotency, retries/reconciliation |
| Close billing period | Per tenant + period | Unique constraint per period, transactions, job orchestrator |
| Generate large monthly report | One job per month, restartable | Separate batch/job, checkpoints + deduplication |
| Long-lived queue listener | Per replica or consumer-group partition | Consumer container/SmartLifecycle, do not use runner for entire lifecycle |
| Build shared search index | One job per version/alias | Job/leader/lock, checkpoints, and idempotent index writes |
| Task handled by only one leader at a time | Temporary mutual exclusion | Distributed lock/lease + fencing, still needs idempotency |

## 15. Common Design Mistakes

**Mistake 1 — Calling a runner "runs strictly once" without stating scope.** During autoscale, restarts, or rolling updates, runners run on new instances. Use the term **per startup**.

**Mistake 2 — Using a static boolean to lock the entire cluster.** Static variables are shared only within one JVM/classloader, not across Pods, and vanish on restart.

**Mistake 3 — Using @Order to synchronize Pods.** @Order only orders runners within a context; it provides no distributed mutual exclusion.

**Mistake 4 — SELECT first then INSERT without a unique constraint.** Two replicas can both observe "does not exist" and both write.

**Mistake 5 — Writing DONE first then calling the API.** Crashing between the two steps can leave the task dropped permanently.

**Mistake 6 — Calling the API first then writing DONE.** Crashing after the API call and before DONE can cause duplicate side effects on retry.

**Mistake 7 — Treating a distributed lock as exactly-once.** Expired leases, failovers, stale holders, and crashes can still trigger retries/duplicates; fencing or idempotent effects are needed.

**Mistake 8 — Catching all SQLExceptions and printing "already ran."** Network errors, full databases, transaction timeouts, or broken schemas are not duplicate keys. Classify and report errors honestly.

**Mistake 9 — Swallowing exceptions from a mandatory runner.** SpringApplication may continue publishing ApplicationReadyEvent despite incomplete preparation data.

**Mistake 10 — Putting a separate file-backed H2 database inside each container and calling it global uniqueness.** Pods see separate data, so every Pod creates its own "unique" result.

**Mistake 11 — Putting entire schema migrations into a web service runner.** Prone to collisions when versions overlap, hard to roll back, and hard to audit history; prefer migration tooling.

**Mistake 12 — Using request timestamp as an idempotency key.** Every retry gets a new timestamp, defeating deduplication. Keys must bind to the same business intent.

**Mistake 13 — Waiting indefinitely for a lock during startup.** Can hold every instance unready, causing rollout timeouts and cascading failures; define deadlines and operational plans.

**Mistake 14 — Failing to verify transactions apply through proxies.** Self-invocation of @Transactional methods can bypass the AOP proxy; claim and effect accidentally commit separately.

**Mistake 15 — Assuming Job/Kubernetes/Scheduler guarantees exactly once.** These mechanisms involve retries, replacements, and failovers; business logic still needs deduplication or reconciliation.

**Mistake 16 — Confusing "one unique DB effect" with "method executes once."** Methods can be called multiple times; what matters is the side-effect boundary at the source of truth.

## 16. Pre-Deployment Checklist

Before placing work inside a runner, answer clearly:

1. Is this **per-instance state initialization** or **one shared business outcome**?
2. Does "once" mean **once forever, per version, per tenant, or per period**?
3. How many replicas/JVMs/pods can start or restart concurrently?
4. Which store is the **durable source of truth** for completion state? Is it genuinely shared?
5. Is there a **UNIQUE constraint** or atomic compare-and-set where the effect is written?
6. Can the claim and effect reside in **the same transaction**?
7. If effects span multiple systems, are **idempotency keys, outbox, retries, and reconciliation** in place?
8. If leadership/lock is lost midway, can a stale process still write? Is a fencing token needed?
9. May an instance become ready before global work finishes? Are timeouts/fail-fast and readiness configured properly?
10. When rolling out a new version, does the work key change per version as contracted?
11. Have restarts, concurrent startups, crashes after commit, timeouts, and schema conflicts been tested?
12. Do metrics track **attempted**, **applied**, **skipped**, **pending**, **failed**, and **retried** per key?

## 17. Self-Check

**Question 1.** Two Pods with the same ApplicationRunner start simultaneously. How many times is the runner called?  
**Answer:** Normally each Pod invokes its runner once during its startup—two independent invocations.

**Question 2.** After restarting a Pod, does `@Order(1)` on a runner skip work that already ran previously?  
**Answer:** No. `@Order` only specifies order among runners in a single context; it persists no state across restarts.

**Question 3.** Should populating in-memory RAM caches for each replica run once cluster-wide or once per replica?  
**Answer:** Each replica needs its own cache, so initialize per instance/startup.

**Question 4.** To seed catalog v3 in a shared database without duplicate inserts across 10 Pods, what is required?  
**Answer:** A versioned work key, unique constraint, transaction/idempotency; use migration tooling if appropriate.

**Question 5.** Two replicas both SELECT and find no row; why can both write duplicates?  
**Answer:** That is a check-then-act race condition. Enforce uniqueness or atomic coordination at the shared store.

**Question 6.** The claim committed and the process crashed before calling the API; is the task guaranteed to succeed?  
**Answer:** No. Mark-before-effect can drop tasks; use a state machine/retries and guarantees at the effect source.

**Question 7.** External email succeeded yet the client timed out before saving DONE; can the next run send a duplicate?  
**Answer:** Yes. Use idempotency keys at sender/target, outbox patterns, and reconciliation policies.

**Question 8.** Does a PostgreSQL unique constraint cause ApplicationRunner to be invoked only once across the cluster?  
**Answer:** No. Runners are still invoked on each replica; the DB rejects duplicate writes per key.

**Question 9.** Why did the demo place `@Transactional` on a separate service instead of calling a method within the same runner?  
**Answer:** So the call passes through Spring's bean proxy and the transaction genuinely encompasses both claim and effect.

**Question 10.** Does a Kubernetes Job running once guarantee every external API call executes strictly once?  
**Answer:** No. Jobs can retry or Pods can be replaced; idempotency and side-effect verification are still required.

**Question 11.** Can a separate file-backed H2 database per container enforce cluster-wide once-only execution?  
**Answer:** No. State is not shared. The file-backed H2 demo only demonstrates persistence across restarts in the same working directory.

**Question 12.** Must every web replica stay unready until a 20-minute global job completes?  
**Answer:** Depends on the contract. Usually extract the job with its own lifecycle, health, and retries; if strictly mandatory, use explicit barriers, timeouts, and operational policies.

**Final Takeaway:** **Runners execute on each SpringApplication startup and hold no magic power to "run once system-wide."** Use runners for local initialization and per-instance startup tasks. For shared business outcomes, define a **work key**, enforce **unique constraints/transactions** at the data source, or use **migrations/jobs/locks/outbox** as required. Distinguish "how many times code is called" from "how many times side effects are recorded," because system reliability lives at the side-effect boundary.

### References

- [Spring Boot — Using ApplicationRunner or CommandLineRunner](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
- [Spring Boot 3.3 — ApplicationRunner API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationRunner.html)
- [Spring Framework — Transaction rollback semantics](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [H2 Database — Connection modes and persistent databases](https://h2database.com/html/features.html)
- [Spring Batch — JobRepository and job instances](https://docs.spring.io/spring-batch/reference/job.html)
- [Spring Boot — Database Initialization](https://docs.spring.io/spring-boot/reference/howto/data-initialization.html)
