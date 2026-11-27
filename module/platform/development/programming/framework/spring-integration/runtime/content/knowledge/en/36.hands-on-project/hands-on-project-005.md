# Persisting Aggregator State Across Restarts — Spring Integration Runtime Hands-On Project

## 1. Problem Statement and Target Outcome

In the **SPRING_INTEGRATION_RUNTIME** module, we have seen messages flow through channels, consumers, pollers, and handlers. However, an **Aggregator** cannot finish its job from a single message arrival: it must **remember prior messages belonging to the same group**, wait for a release condition, and only then emit output.

This **Hands-On Project → Persisting Aggregator State Across Restarts** exercise builds a Spring Integration application that runs **twice against the same database**:

- **Run 1 (seed):** send two parts belonging to batch `BATCH-101`, while the batch requires three parts. The aggregator does not release yet and must persist the pending state.
- **Stop the JVM/`ApplicationContext` completely:** in-process beans, schedulers, memory, and queues are destroyed.
- **Run 2 (resume):** start a fresh application and send only the third part of the same batch. The aggregator reads the two prior parts back from a **persistent JDBC `MessageGroupStore`**, releases the complete batch, and emits output.

If it only works when all three parts arrive in one run, we have **not proven persistence across restarts**.

### Technical Objectives

After this lesson, you will be able to:

1. Distinguish in-memory state from durable aggregator state.
2. Choose an appropriate `MessageGroupStore` and storage schema.
3. Build a flow with `CorrelationStrategy`, `ReleaseStrategy`, an aggregation handler, and an output channel.
4. Initialize JDBC tables **once** and rerun the application **without** wiping the database.
5. Verify a 2/3 group before restart and a 3/3 completion result after restart.
6. Explain commit points, in-flight messages, transactions, retries, and broker acks.
7. Address remaining gaps: duplicates, late arrivals, group timeout/expiry, lock contention, and schema migrations.
8. Build integration tests, fault injection, metrics, and a recovery runbook.

> **Warning:** "The group survives in the database across restarts" is a specific milestone; it **does not automatically prove exactly-once processing**, guarantee downstream commit of the output, or resolve duplicates when a broker redelivers.

## 2. Choosing the Right Place to Store State

A minimal Aggregator system manages several distinct kinds of data:

| Item | Example | Must Survive Restart? | Where to Store |
| --- | --- | --- | --- |
| Messages waiting in a channel | Part not yet at aggregator | Depends on SLA | `QueueChannel` with `MessageStore` or broker |
| **Aggregator group state** | `BATCH-101` received P1/P2 | **Yes**, in this lesson | Persistent `MessageGroupStore` |
| Released result not yet published | 3-part batch ready, outbound fails | Yes if output loss is unacceptable | Outbox/durable outbound queue |
| Deduplication marker | Part P2 already processed | Yes with at-least-once sources | `MetadataStore`/inbox/business DB |
| Business order state | Order completed | Yes | Business database |
| Connection/retry state | Socket, backoff, worker task | Depends on semantics | Adapter/worker; never replace group store |

`SimpleMessageStore` is an in-memory store for learning how aggregators work. It cannot preserve two parts when the process terminates. In this project we use **`JdbcMessageStore`**, which persists `Message<?>` and `MessageGroup` records over JDBC.

~~~mermaid
flowchart LR
    A["Part producer"] --> C["inputParts / DirectChannel"]
    C --> T["Stateless transformer"]
    T --> G["Aggregator\ncorrelation=batchId"]
    G <--> S[("JDBC MessageGroupStore\nH2 file DB")]
    G -->|All 3 parts| O["completedBatches / QueueChannel"]
    O --> H["ApplicationRunner consumes output"]
    R["Application restart"] -.->|"starts new process"| G
    S -.->|"data remains on disk"| R
~~~

Important detail: the `QueueChannel` used for **demo output** is still an in-memory queue; we consume the output right before the application shuts down. If a batch released right before a crash must also survive without losing output before downstream consumes it, add a **durable output boundary/outbox** in an advanced step.

## 3. Why Is an Aggregator a Stateful Endpoint?

A pure transformer such as `String::trim` processes each message independently. An aggregator must retain **a set of messages per correlation key**.

Example:

~~~text
BATCH-101:
  P1 payload="  red  "
  P2 payload="  blue  "
  P3 payload="  green  "

State after P1: pending count=1
State after P2: pending count=2
State after P3: ready count=3 -> release
~~~

Each `Message` holds payload and headers, while `MessageGroupStore` retains the group's members. Group state includes identity, members, and metadata so the framework can evaluate release and expiry. The framework manages group mutations; never hand-roll a singleton `HashMap<batchId,List<Message>>` expecting it to survive restarts safely.

### Correlation Strategy

A **`CorrelationStrategy`** picks the key used to group messages. In this project, we use the application header `batchId`. All parts of `BATCH-101` must carry the same key.

### Release Strategy

A **`ReleaseStrategy`** decides when a group is ready to emit output. The demo uses:

~~~java
group -> group.size() >= 3
~~~

**Suitable only for demo data with three distinct parts and no redeliveries.** In reality, group size counts message members, **not necessarily distinct `partId`s**; P2 delivered twice could trigger premature release.

### Group Expiry

If only two parts arrive and P3 never comes, you cannot hold groups forever. Production needs `groupTimeout`/expiry/recovery policies. In this first lesson, however, we **deliberately omit auto-expiry timeouts** so we can shut down the process and resume the incomplete group.

## 4. Timeline Model: Stop the Application Without Deleting the Database

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant A1 as Aggregator JVM #1
    participant DB as H2 file database
    participant A2 as Aggregator JVM #2
    participant O as Output channel
    P->>A1: P1 (BATCH-101)
    A1->>DB: Persist P1 / group size 1
    P->>A1: P2 (BATCH-101)
    A1->>DB: Persist P2 / group size 2
    A1--xA1: ApplicationContext close / process exit
    Note over DB: Database file stays intact
    Note over A2: New SpringApplication, same JDBC URL
    P->>A2: P3 (BATCH-101)
    A2->>DB: Read existing group P1 + P2
    A2->>DB: Add P3 / release condition true
    A2->>O: Aggregated result
    O-->>P: Batch output available
~~~

There is no "serialize the entire Spring context"; state must live in **a backend independent of process lifetime**. Nor is there any need to keep JVM #1 alive. Seeing the right result after JVM #1 has exited proves the pending group was recovered.

### Set Pass/Fail Criteria Upfront

| Checkpoint | Expected | If Not Met |
| --- | --- | --- |
| Seed, before stop | `getMessageGroup(batchId).size()==2` | Messages were not stored or correlation is wrong |
| Seed, output check | `receive(0)==null` | Premature release or output from another batch |
| After closing JVM #1 | Database file exists on disk | Using in-memory H2 or accidentally deleting DB |
| Resume, before sending P3 | Store reads group size 2 | Changed JDBC URL/region/schema; data missed |
| Resume, after sending P3 | Receives one aggregated output | Release did not fire or output wiring is broken |
| After completion | State matches completion policy | Inspect cleanup and late duplicates separately |

If you only test **stopping and starting the same endpoint inside one JVM**, an in-memory singleton store still holds the group; that is **not a process-restart test**.

## 5. Stack and Project Structure

Examples target **Java 17+, Spring Boot 3.x, and Spring Integration 6.x** under a compatible BOM. The project uses:

- Spring Integration core + Java DSL;
- `spring-integration-jdbc` for `JdbcMessageStore`;
- Spring JDBC for `DataSource`;
- H2 in **file** mode, not `jdbc:h2:mem`;
- JUnit 5/Spring Test for extended tests;
- Micrometer/Spring Boot Actuator optionally for production observability.

Illustrative project layout:

~~~text
aggregator-restart-lab/
├── build.gradle.kts
├── src/main/java/demo/integration/
│   └── AggregatorRestartLabApplication.java
└── src/main/resources/
    └── application.yml

agg-restart-db.mv.db      # generated in working directory after first run
~~~

The exact database filename depends on the JDBC URL and H2 version. **Never commit this local data file to Git**, and do not delete it between the two runs of the same lab.

### Gradle Kotlin DSL Dependencies

Insert into a Spring Boot project already configured with plugins, Java toolchain, and dependency management:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-integration")
    implementation("org.springframework.boot:spring-boot-starter-jdbc")
    implementation("org.springframework.integration:spring-integration-jdbc")
    runtimeOnly("com.h2database:h2")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

Versions are managed by the project's **Spring Boot BOM**; do not manually mix Spring Integration 6.x with a mismatched Spring Framework/Micrometer major version. This is only the dependency block, not a full `build.gradle.kts`.

## 6. File-Based H2 JDBC: Configuring Persistence Across Restarts

Create `src/main/resources/application.yml`:

~~~yaml
spring:
  main:
    web-application-type: none
  datasource:
    driver-class-name: org.h2.Driver
    url: jdbc:h2:file:./agg-restart-db;DB_CLOSE_ON_EXIT=FALSE
    username: sa
    password:
  sql:
    init:
      mode: never
      schema-locations: classpath:org/springframework/integration/jdbc/schema-h2.sql

logging:
  level:
    org.springframework.integration: INFO
~~~

**Why does this matter?**

1. `jdbc:h2:file:./agg-restart-db` creates a disk-backed database file in the **current working directory**.
2. Use the exact same working directory and JDBC URL for both seed and resume. Changing directories opens a **different database**.
3. `spring.sql.init.mode=never` is the lab default so we **do not accidentally re-run `CREATE TABLE` scripts** against an existing database.
4. On the **first run**, we override with `--spring.sql.init.mode=always` to bootstrap the JDBC schema once.
5. `schema-h2.sql` comes from the `spring-integration-jdbc` artifact of your **chosen version**; verify the script/version in your BOM when building.
6. `DB_CLOSE_ON_EXIT=FALSE` does not discard state: data lives in the file; `DataSource`/connection pool must still close cleanly to release file locks.

**Do not use** `jdbc:h2:mem:lab`: an in-memory database vanishes when the JVM exits, rendering restart tests meaningless.

### Two-Run Schema Initialization

| Run | Initialization Flag | Result |
| --- | --- | --- |
| First run, tables do not exist yet | `--spring.sql.init.mode=always` | Executes official schema SQL from dependency |
| Subsequent runs, tables already exist | `--spring.sql.init.mode=never` | Skips table creation; preserves persisted messages |
| Production, existing database | Flyway/Liquibase or managed migration tool | Versioned migrations with rollback/backup; never re-run "create" blindly |

Accidentally running the init script a second time on an initialized DB can fail with "table already exists". **Never enable `continue-on-error=true` to ignore SQL errors in production.** Separate fresh DB setup from existing schemas with an explicit migration policy.

## 7. Complete Java Application: Seed and Resume Modes

Create `src/main/java/demo/integration/AggregatorRestartLabApplication.java`.

The application contains:

- `inputParts` (`DirectChannel`) receiving part messages.
- A stateless transformer normalizing payloads.
- An aggregator correlating on header `batchId`, releasing at 3 members, and **persisting groups via `JdbcMessageStore`**.
- `completedBatches` (`QueueChannel`) collecting outputs.
- An `ApplicationRunner` executing either mode, verifying group state before/after, and printing results.
- `main` closing `ApplicationContext` after `ApplicationRunner` finishes to enforce a true process boundary.

~~~java
package demo.integration;

import java.util.List;
import java.util.Locale;

import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jdbc.store.JdbcMessageStore;
import org.springframework.integration.store.MessageGroupStore;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootApplication
@EnableIntegration
public class AggregatorRestartLabApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(AggregatorRestartLabApplication.class, args);

        // ApplicationRunner already ran inside SpringApplication.run().
        // Close the context so the next run is a genuinely fresh process.
        context.close();
    }

    @Bean("inputParts")
    MessageChannel inputParts() {
        return new DirectChannel();
    }

    @Bean("completedBatches")
    PollableChannel completedBatches() {
        return new QueueChannel();
    }

    @Bean
    MessageGroupStore batchGroupStore(DataSource dataSource) {
        JdbcMessageStore store = new JdbcMessageStore(dataSource);

        // Logical namespace; must stay unchanged across both runs.
        store.setRegion("LAB_BATCH_AGGREGATOR");
        return store;
    }

    @Bean
    IntegrationFlow batchFlow(MessageGroupStore batchGroupStore) {
        return IntegrationFlow.from("inputParts")
                .transform(String.class,
                        value -> value.strip().toUpperCase(Locale.ROOT))
                .aggregate(spec -> spec
                        .correlationStrategy(message ->
                                message.getHeaders().get("batchId"))
                        .releaseStrategy(group -> group.size() >= 3)
                        .messageStore(batchGroupStore)
                        .expireGroupsUponCompletion(true))
                .channel("completedBatches")
                .get();
    }

    @Bean
    ApplicationRunner demo(
            Environment env,
            @Qualifier("inputParts") MessageChannel input,
            @Qualifier("completedBatches") PollableChannel output,
            MessageGroupStore groups) {

        return args -> {
            String mode = env.getProperty("lab.mode", "seed");
            String batchId = env.getProperty("lab.batch-id", "BATCH-101");

            if ("seed".equalsIgnoreCase(mode)) {
                int before = groups.getMessageGroup(batchId).size();

                // For deterministic demo: a fresh batch must have no prior state.
                if (before != 0) {
                    throw new IllegalStateException(
                            "Batch already exists. Choose a new lab.batch-id.");
                }

                sendPart(input, batchId, "P1", "  red  ");
                sendPart(input, batchId, "P2", " blue ");

                int stored = groups.getMessageGroup(batchId).size();
                Message<?> premature = output.receive(0);

                if (stored != 2 || premature != null) {
                    throw new IllegalStateException(
                            "Expected pending group of 2 parts, got "
                                    + stored);
                }

                System.out.println("SEED_OK batch=" + batchId
                        + " durablePending=" + stored);
                System.out.println("STOP the process; run resume next.");
            }
            else if ("resume".equalsIgnoreCase(mode)) {
                int recovered = groups.getMessageGroup(batchId).size();

                if (recovered != 2) {
                    throw new IllegalStateException(
                            "Expected two persisted parts, found "
                                    + recovered + ". Check DB URL and region.");
                }

                System.out.println("RECOVERED batch=" + batchId
                        + " pending=" + recovered);

                // Send only the missing part in the new process.
                sendPart(input, batchId, "P3", " green ");

                Message<?> combined = output.receive(5_000);
                if (combined == null) {
                    throw new IllegalStateException(
                            "No released result after third part");
                }

                System.out.println("RESUME_OK batch=" + batchId
                        + " result=" + combined.getPayload());
            }
            else {
                throw new IllegalArgumentException(
                        "Unknown lab.mode=" + mode);
            }
        };
    }

    private static void sendPart(
            MessageChannel channel, String batchId,
            String partId, String payload) {

        Message<String> message = MessageBuilder
                .withPayload(payload)
                .setHeader("batchId", batchId)
                .setHeader("partId", partId)
                .setHeader("eventId", batchId + ":" + partId)
                .build();

        boolean accepted = channel.send(message);
        if (!accepted) {
            throw new IllegalStateException(
                    "Channel rejected partId=" + partId);
        }
    }
}
~~~

### Why Not Read from H2 and Reconstruct Groups Manually?

`JdbcMessageStore` implements the store contract; the Aggregator is configured with `.messageStore(batchGroupStore)` and queries the store whenever needed. When the restarted application processes P3, the framework uses **the same correlation key** and backend to load P1 and P2.

We do not manually write `SELECT * ...`, deserialize payloads, and feed a fresh Aggregator; doing so bypasses Spring Integration's group lifecycle, metadata, locking, and release contracts.

### Why Can the Output `QueueChannel` Receive Immediately in the Demo?

`inputParts` is a `DirectChannel`: the path transformer → aggregator and release runs synchronously on the sender thread in this example. Once P3 arrives, the output is enqueued onto `completedBatches` before `sendPart()` returns. `receive(5_000)` uses a finite timeout so the demo never hangs indefinitely.

If you replace the input with an `ExecutorChannel` or a `QueueChannel` with a poller, processing becomes asynchronous; you will need a queue/latch or Awaitility. At that point, `send()` returning true **does not mean the group was persisted yet**.

### Safe Assumptions of This Example

- Only **one instance runs at a time** against the H2 file database.
- No duplicate parts or late arrivals on the happy path.
- Identical `lab.batch-id` and `JdbcMessageStore.region` across both runs.
- H2 file remains intact; no schema or serializer version changes between runs.
- Inputs are not retried after messages are already stored.
- The consumer reads output immediately; no durable outbox yet.
- Both payload and headers are `String`, compatible with the chosen serializer.

This example proves **pending group durability**, not complete end-to-end workflow durability across all fault modes.

## 8. Executing the Two Runs

Run from the same project and **the same working directory** holding the database file.

### Run 1 — Create Schema and Seed Two Parts

Using Gradle Boot Run in the configured project:

~~~shell
./gradlew bootRun --args="--lab.mode=seed --lab.batch-id=BATCH-101 --spring.sql.init.mode=always"
~~~

If running a built executable JAR, equivalently:

~~~shell
java -jar build/libs/aggregator-restart-lab.jar --lab.mode=seed --lab.batch-id=BATCH-101 --spring.sql.init.mode=always
~~~

The JAR name is **illustrative**; use your project's actual JAR name. `--spring.sql.init.mode=always` **is used only when the database has no tables yet**. Never re-run this command against the same database after seeding succeeds.

Expected output:

~~~text
SEED_OK batch=BATCH-101 durablePending=2
STOP the process; run resume next.
~~~

After the app exits, verify in the working directory that an H2 file such as `agg-restart-db.mv.db` exists. That is **evidence the backend file exists**, though by itself it does not prove the group is valid; the `getMessageGroup(batchId).size()==2` assertion verified that during Run 1.

### Run 2 — Resume with the Same DB and Send P3

~~~shell
./gradlew bootRun --args="--lab.mode=resume --lab.batch-id=BATCH-101 --spring.sql.init.mode=never"
~~~

Or:

~~~shell
java -jar build/libs/aggregator-restart-lab.jar --lab.mode=resume --lab.batch-id=BATCH-101 --spring.sql.init.mode=never
~~~

Expected output:

~~~text
RECOVERED batch=BATCH-101 pending=2
RESUME_OK batch=BATCH-101 result=...
~~~

The default output payload depends on the Spring Integration version's aggregation processor. For this demo, it normally represents the three normalized payloads, e.g., `[RED, BLUE, GREEN]`. **Do not hardcode output ordering in concurrency tests** unless you configured explicit ordering or resequencing.

### Rerunning the Exercise

- To practice again on the same DB, pick a **new** `batch-id`.
- To initialize a fresh DB, change the JDBC URL to a new filename and run schema bootstrap once.
- Never delete database files to "fix" production issues; only reset **isolated demo** data when you are sure no state needs to be kept.
- Never reuse a completed batch key without a closed-group/deduplication policy: `expireGroupsUponCompletion(true)` can delete the group and let a late message open a brand-new group.

## 9. Verifying Where State Is Actually Stored

The Spring Integration JDBC schema includes tables for message stores and message groups. In the official schema script for your project version, you will typically find tables such as `INT_MESSAGE` and `INT_MESSAGE_GROUP`.

Read-only SQL queries for **observation only** (do not mutate data):

~~~sql
SELECT COUNT(*) AS message_rows FROM INT_MESSAGE;
SELECT COUNT(*) AS group_rows FROM INT_MESSAGE_GROUP;
~~~

Depending on schema/version/region/group metadata, those two counts do not necessarily equal the group size reported by `MessageGroupStore`. To inspect a **specific batch**, use the API:

~~~java
int pending = batchGroupStore
        .getMessageGroup("BATCH-101")
        .size();

System.out.println("Pending parts=" + pending);
~~~

If querying SQL tables directly, inspect the **actual DDL of your running dependency version** before relying on column or index names; never run a hardcoded query from another version and mistakenly conclude data is missing.

### What Must Stay Constant Across Runs?

| Component | Must Match? | Why |
| --- | --- | --- |
| JDBC URL | **Yes** | Points to the same database file |
| Schema/table names | **Yes**, or compatible migration | Store reads the right records |
| `JdbcMessageStore.region` | **Yes** | Logical store namespace |
| `batchId` | **Yes** | Correlation group key |
| Serializer/header format | Backwards-readable | Old messages must deserialize |
| Java/SI major version | Keep pinned for the lab | Avoids representation drift between seed and resume |
| `ReleaseStrategy` | Compatible with prior state | Prevents incorrect releases |
| `MessageHeaders.ID` | Need not match across processes | Not the logical group ID |
| H2 process lifetime | **Different** | This is what the restart test verifies |

**An H2 file database is not a shared multi-node production option.** It suits a single process or lab. Across multiple pods, migrate to PostgreSQL/MySQL and verify distributed locks, transaction isolation, schema migrations, and connection pooling.

## 10. Process Restart vs. Endpoint Restart

| Experiment | Proves Persistence? | Reason |
| --- | --- | --- |
| `aggregatorEndpoint.stop(); start()` in the same JVM | **Insufficient** | In-memory store stays alive in the process |
| Restarting a new Spring `ApplicationContext` keeping an old static map | No | Test still relies on process memory |
| `SpringApplication.run(...)` → close context → `run(...)` with DB file | Likely | Provided store/JDBC file is recreated cleanly |
| Running **two independent JVMs** sharing one JDBC file | **Strongest for the lab** | Zero shared heap or singletons across runs |
| `kill -9` after seed before DB commit | Not guaranteed | Data may not have committed yet |
| Starting a new pod with a local file on the old pod | Usually no | Local disk volumes are neither shared nor durable |
| Infrastructure with persistent broker and JDBC store | Possible | Must verify acks, transactions, and serializers |

For realistic validation, inspect the **committed state** of the group rather than just what `send()` returned.

## 11. Flow Execution and Transaction Boundaries

With `DirectChannel`, the main steps execute on the same call stack:

~~~text
send(P1)
  -> DirectChannel
  -> stateless transformer
  -> Aggregator
       -> resolve correlationId=BATCH-101
       -> lock group
       -> add P1 to JdbcMessageStore
       -> releaseStrategy(group) == false
  <- return from send(P1)
~~~

Similarly, P2 raises group size to 2. After restart:

~~~text
send(P3)
  -> Aggregator
       -> lock group
       -> load group in JdbcMessageStore
       -> add P3
       -> releaseStrategy(group) == true
       -> create output message
       -> cleanup per completion policy
  -> completedBatches QueueChannel
  <- return from send(P3)
~~~

`JdbcMessageStore` writes to a JDBC database, so persistence depends on JDBC operations committing cleanly. Depending on transaction management and endpoint configuration, **the commit point does not automatically match** `MessageChannel.send()` in asynchronous scenarios.

### Critical Failure Windows

| Crash Window | What Can Happen | What Must Be Designed |
| --- | --- | --- |
| Before store add commits | Part is not yet durable | Source retry/redelivery |
| After store commits, before source ack | Part stored, yet source may redeliver | Deduplicate by logical part ID |
| After 3 parts arrive, before output publishes | Group may already be marked complete | Recoverable release/outbox |
| After output side effect commits, before ack | Downstream may receive twice | Idempotent receiver |
| After group expiry, late part arrives | May open a brand-new group | Closed-group marker/late policy |
| During schema/serializer upgrade | Old bytes still sit in store | Compatibility/migration tests |

This project focuses on the **2/3 pending → restart → P3** window. Understanding the remaining windows prevents overclaiming delivery guarantees.

## 12. Why `group.size() >= 3` Is Not Safe Against Duplicates

Suppose the broker redelivers part P2:

~~~text
P1 -> group size=1
P2 -> group size=2
P2 duplicate -> group size=3 -> PREMATURE release
P3 -> late arrival, old group already completed
~~~

Each delivery can be wrapped by Spring Messaging into a new `Message` with a new `MessageHeaders.ID`. Therefore, **you cannot use the message instance UUID to deduplicate logical events**.

In the demo code, every message carries `partId` and `eventId`, for example:

~~~text
BATCH-101:P1
BATCH-101:P2
BATCH-101:P3
~~~

These IDs can be used to:

- Deduplicate parts before the aggregator accepts them;
- Track whether P1/P2/P3 have already been processed;
- Trace retries and replays;
- Block late parts from spawning a new group;
- Reconcile outputs with the business DB.

**Deduplication must be atomic with store transactions.** If you record "saw P2" in metadata before persisting P2 and the process crashes, a retried P2 would be rejected while the group still lacks it. Production requires an atomic inbox/state machine or coordinated transaction, not a standalone in-memory `Set`.

## 13. What Gap Remains When the Output Queue Is Still In-Memory?

The example uses an in-memory `QueueChannel` so learners can receive outputs easily. When P3 arrives:

~~~mermaid
flowchart LR
    A["Group has 3 parts"] --> B["Aggregator releases"]
    B --> C["Group completion cleanup"]
    B --> D["In-memory QueueChannel"]
    D --> E["ApplicationRunner.receive()"]
    E --> F["Print / downstream"]
~~~

If the process crashes **after group cleanup** yet **before the consumer processes the output**, both the group state and the queued output vanish. That is why "persisting aggregator state across restarts" **does not mean** every final output is preserved.

Production options:

- Persist the output to an **outbox** in the same transaction/resource when release triggers; a separate publisher drains the outbox and retries with a stable ID.
- Or send output to a **durable broker/queue** with proper acks/transactions, verifying crash windows between store and broker.
- When no atomic multi-resource transaction exists, combine idempotency with reconciliation instead of assuming exactly-once.
- Track an outbox pending metric and recovery job so final results are never lost.

This lesson intentionally separates **durable pending groups** (demonstrated) from **durable completion/output** (requires additional design).

## 14. Checklist When Migrating from H2 to PostgreSQL

An H2 file tests **one JVM at a time**. Clustered PostgreSQL/DB servers additionally require:

1. Official PostgreSQL schema or migration DDL compatible with your `spring-integration-jdbc` version.
2. Properly configured connection pool and transaction manager.
3. Appropriate region/namespace keys and indexes.
4. A suitable `LockRegistry` when multiple app instances update the same group.
5. Duplicate/late-message policies and idempotency keys.
6. Timeouts, expiry, retention, and cleanup jobs.
7. SQL lock timeouts and deadlock handling.
8. Message serializer/schema compatibility across rolling deployments.
9. Monitoring store read/write latency, pending group counts/age, and queue lag.
10. Backup/restore and disaster recovery testing.

**Never share a single H2 file DB across multiple pods** as a production HA solution. With a JDBC backend, store state lives on the DB server; locks and transactions are still needed so concurrent updates to the same group do not conflict.

## 15. Real Testing Across Two Independent JVMs

Running seed and resume in **two separate processes** is the clearest proof that state does not live solely in memory. A JUnit integration test can launch the built JAR using a shared temporary working directory, the same relative JDBC URL, and two argument sets.

**Prerequisite:** the Spring Boot JAR must already be built by your project's CI/Gradle workflow before running the test. This document only provides the knowledge and test code, **without running builds**. The test uses `@TempDir` for the H2 database and redirects stdout/stderr to a log file so the child process never blocks on full output pipes.

~~~java
package demo.integration;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class AggregatorRestartProcessTest {

    @TempDir
    Path workDir;

    @Test
    void pendingGroupSurvivesTwoSeparateJvms() throws Exception {
        // Replace with the actual built JAR path of your project.
        Path jar = Path.of("build", "libs", "aggregator-restart-lab.jar")
                .toAbsolutePath();

        assertTrue(Files.isRegularFile(jar),
                "Build the Spring Boot executable JAR before this test");

        String first = runJar(jar, workDir, "seed", "BATCH-101",
                "always");
        assertTrue(first.contains(
                "SEED_OK batch=BATCH-101 durablePending=2"));

        // JVM #1 has exited completely; only the database file remains.
        String second = runJar(jar, workDir, "resume", "BATCH-101",
                "never");

        assertTrue(second.contains(
                "RECOVERED batch=BATCH-101 pending=2"));
        assertTrue(second.contains("RESUME_OK batch=BATCH-101"));
    }

    private static String runJar(
            Path jar, Path directory, String mode,
            String batchId, String sqlInitMode) throws Exception {

        Path java = javaExecutable();
        Path log = Files.createTempFile(directory, "run-", ".log");

        List<String> command = new ArrayList<>();
        command.add(java.toString());
        command.add("-jar");
        command.add(jar.toString());
        command.add("--lab.mode=" + mode);
        command.add("--lab.batch-id=" + batchId);
        command.add("--spring.sql.init.mode=" + sqlInitMode);

        ProcessBuilder builder = new ProcessBuilder(command);
        builder.directory(directory.toFile());
        builder.redirectErrorStream(true);
        builder.redirectOutput(log.toFile());

        Process child = builder.start();
        boolean ended;
        try {
            ended = child.waitFor(
                    Duration.ofSeconds(40).toMillis(),
                    TimeUnit.MILLISECONDS);
        }
        catch (InterruptedException ex) {
            child.destroyForcibly();
            Thread.currentThread().interrupt();
            throw ex;
        }

        if (!ended) {
            child.destroyForcibly();
            throw new AssertionError("Child JVM timed out: " + mode);
        }

        String text = Files.readString(log, StandardCharsets.UTF_8);
        assertEquals(0, child.exitValue(),
                "Child JVM failed in " + mode + ":\n" + text);
        return text;
    }

    private static Path javaExecutable() throws IOException {
        boolean windows = System.getProperty("os.name")
                .toLowerCase(java.util.Locale.ROOT)
                .contains("win");

        Path executable = Path.of(
                System.getProperty("java.home"), "bin",
                windows ? "java.exe" : "java");

        if (!Files.isRegularFile(executable)) {
            throw new IOException("Java binary missing: " + executable);
        }
        return executable;
    }
}
~~~

### Why Is This Test Valuable?

- `@TempDir` isolates a fresh database per test run without polluting existing batches.
- JVM #1 exits completely before JVM #2 starts.
- The second process has zero references to beans, `Map`s, or `SimpleMessageStore` instances from the first JVM.
- Only one intentional shared artifact remains: **the database file path** and `batchId`.
- The test inspects the actual `ApplicationRunner` output to assert pending counts and release results.
- `ProcessBuilder` needs no shell; arguments pass directly without shell-escaping headaches on `;` in the JDBC URL.
- Bounded timeouts and log capture simplify debugging if the context fails to start.

### Limitations of This Test

Running two JVMs sequentially with **graceful close** tests restart persistence. It is not yet a **hard-crash** test: a JVM killed with `kill -9` mid-transaction behaves differently because uncommitted data rolls back, requiring timed fault injection. H2 file locking prevents two JVMs from using the file simultaneously like a production DB server, so this test intentionally **does not run in parallel**.

Spring Boot startup times on CI runners vary; choose timeouts suited to your infrastructure. `@TempDir` cleans up after the test; archive logs as test artifacts on CI failures for diagnosis.

## 16. Designing Hard-Crash Tests: Injecting Faults at Controlled Points

Graceful restart answers "can persisted state be read back?" A hard-crash test asks "if the process dies at an inconvenient instant, is state still consistent?"

An advanced test can add a `seed-and-hold` mode to the application:

1. Send P1 and P2.
2. Wait until the store confirms group size=2 after the JDBC transaction commits.
3. Emit a `SEED_COMMITTED` marker and hold the process open with a latch.
4. The parent test watches for the marker via log/file.
5. Kill the child process and wait for it to **actually exit**.
6. Launch JVM #2 in resume mode.
7. Verify group size=2, and after P3 verify output arrives.
8. Repeat while killing **before commit** to contrast: uncommitted data must not be expected to survive.

### Valid Kill Points

~~~mermaid
sequenceDiagram
    participant SRC as Source
    participant APP as Aggregator JVM
    participant DB as JDBC Store
    participant TEST as Test controller
    SRC->>APP: deliver P2
    APP->>DB: BEGIN + persist P2
    Note over APP,DB: Crash here: commit may not have finished
    DB-->>APP: COMMIT confirmed
    APP-->>TEST: marker SEED_COMMITTED
    TEST-xAPP: hard kill
    TEST->>DB: start new JVM + read group
    DB-->>TEST: P1 and P2 persisted
~~~

**Never use `sleep(200)` to guess commit timing.** Write the marker only after the boundary truly completes; instrumenting inside a method before the transaction interceptor commits can emit the marker prematurely.

Beyond crash tests, test DB network loss, deadlocks, connection pool exhaustion, and read-only DB failover. Use fault injection in store implementations or a test database proxy rather than polluting production code with arbitrary sleeps or waits.

## 17. Verifying Transactions and Source Acknowledgments

In the demo, `ApplicationRunner` sends straight into `DirectChannel`, so there is **no broker source ack**. Production typically consumes from Kafka/JMS/AMQP or an equivalent adapter, where you must define the relationship between **store commit** and **source acknowledgment**.

### Two Critical Moments

~~~text
A. Source receive(P2)
B. JdbcMessageStore commit(P2)
C. Source ack(P2)
~~~

If a crash hits between A and B, the source must be able to redeliver. If a crash hits between B and C, P2 is already stored and the source **may redeliver P2**. Therefore:

- Never ack before state is durably persisted if losing parts is unacceptable.
- Redeliveries after commit must be deduplicated by a stable `partId`.
- `MessageGroupStore` persisting a group **does not automatically ack the source broker**.
- Handler transaction managers must match the active thread and resource. An `ExecutorChannel` or poller can introduce a new transaction boundary.
- When two resources do not share an atomic transaction (DB + broker), design at-least-once delivery + idempotency/outbox rather than assuming exactly-once.

### Layer-by-Layer Design Matrix

| Layer | Required Invariant | Test |
| --- | --- | --- |
| Inbound source | Never ack non-durable parts | Crash before store commit |
| Preprocessing | Never alter logical `eventId`/`batchId` | Header mapping test |
| Group persistence | Valid parts are never lost | Readback/restart |
| Deduplication | Duplicates never increase distinct counts | Resend P2 |
| Release/output | Complete batch yields one logical result | Crash before/after release |
| Downstream | Retries never duplicate business effects | Duplicate output event |
| Cleanup/expiry | Groups do not leak and late parts follow explicit rules | Timeout/late tests |

## 18. Preventing Duplicates in Advanced Practice

To harden the demo for production, handle **two kinds of duplicates**:

- **Duplicate part:** P2 arrives twice; group size must not increment a second time.
- **Duplicate result:** an already released/published batch is retried; downstream must not apply the business side effect twice.

### Deduplicating by Logical `partId`

A complete key looks like:

~~~text
part-key = tenantId + ":" + batchId + ":" + partId
~~~

Using a `ConcurrentMetadataStore` with `putIfAbsent`, we can illustrate claim logic:

~~~java
import org.springframework.integration.metadata.ConcurrentMetadataStore;

final class PartClaim {
    private final ConcurrentMetadataStore store;

    PartClaim(ConcurrentMetadataStore store) {
        this.store = store;
    }

    boolean claim(String batchId, String partId) {
        String key = "part:" + batchId + ":" + partId;
        return store.putIfAbsent(key, "claimed") == null;
    }
}
~~~

**Do not use the snippet above as an exactly-once solution.** If the claim marker is written and the application crashes **before persisting the part into `JdbcMessageStore`**, a retried part gets rejected while the group still lacks it. Use one of these patterns instead:

1. Keep the dedupe key and group mutation inside one atomic transaction/resource.
2. Use an inbox state machine with `CLAIMED`/`COMPLETED`/`FAILED` states, leases, and recovery.
3. Partition inputs by key and enforce unique part IDs at release time.
4. Run a reconciliation job comparing inbox markers against group members after failures.

### Deduplicating Output

Produce a stable `batchResultId`, such as `tenant:batchId:version`. Downstream outbox/consumers use this ID to block duplicate side effects. `MessageHeaders.ID` can change on rebuild/retry, so never use it as a logical business key.

## 19. Late Arrivals After Completion

In the example, `expireGroupsUponCompletion(true)` is enabled to clean up released groups. That **does not guarantee** late P2/P3 deliveries will be rejected. If the same `batchId` arrives after completion and the group was already deleted, the framework can create a brand-new group for that key.

~~~text
Run #2: BATCH-101 P3 -> release -> group cleanup
Run #3: P2 duplicate -> new group? -> pending 1/3
~~~

Production applications often need a durable **closed-group marker**:

| Key | Status | Updated |
| --- | --- | --- |
| `BATCH-101` | `COMPLETED` | when output committed |
| `BATCH-102` | `EXPIRED` | when timeout triggered |
| `BATCH-103` | `PROCESSING` | last part accepted |

Incoming parts check this status under an atomic/transactional policy. For an already completed batch, return a duplicate acknowledgment or route to quarantine; never silently open a new group.

**Retention:** retain closed markers at least as long as your redelivery/replay window. A 1-hour marker will not stop a duplicate arriving 7 days later.

## 20. Group Timeout and Expiry: Never Leave 2/3 Parts Forever

The demo intentionally disables expiry on pending groups to demonstrate restart recovery. In production, a `BATCH-999` with two parts where P3 never arrives would stay in the DB forever without cleanup.

Sample operational policy:

- **T0:** first part arrives; record the group's `createdAt`.
- **Deadline:** after 15 minutes with missing parts, expire the group.
- **Recovery:** emit a timeout event containing `batchId` and **the received part IDs**; never emit a partial result as success if the domain forbids it.
- **Cleanup:** once the timeout event is durably persisted, delete or compact the group per policy.
- **Late parts:** route to DLQ/quarantine or an explicit reopen workflow.
- **Monitoring:** gauge pending group counts and oldest group age.

Relevant Spring Integration Aggregator APIs include `groupTimeout`, group expiry, `sendPartialResultOnExpiry`, `expireGroupsUponCompletion`, and version-specific message group processors/expiry callbacks. When applying a specific DSL feature, **verify the exact overloads/APIs of your dependency version**; never turn on an option solely because its name sounds right.

### Comparing Different Timeouts

| Timeout | Scope | Does Not Replace |
| --- | --- | --- |
| `QueueChannel.receive(timeout)` | How long consumer waits for output | Group lifetime |
| Poller `receiveTimeout` | Poller waiting for a message | Group expiry |
| `groupTimeout` | Correlation group waiting for release | Gateway request timeout |
| HTTP/JMS request timeout | Caller/gateway waiting for reply | Guaranteed group cleanup |
| Transaction timeout | Maximum resource transaction length | Business deadline |

Stopping an endpoint does not automatically expire groups. On restart, timeout management must be configured so groups that expired while the JVM was down are processed according to policy.

## 21. Scale-Out and Locking: From Single H2 to Multiple Pods

When two workers can concurrently add parts to `BATCH-101`:

~~~mermaid
sequenceDiagram
    participant A as Pod A
    participant B as Pod B
    participant L as LockRegistry
    participant D as Shared JDBC store
    A->>L: lock(BATCH-101)
    B->>L: lock(BATCH-101) [wait]
    A->>D: add P1 + evaluate release
    A->>L: unlock
    L-->>B: acquired
    B->>D: add P2 + evaluate release
    B->>L: unlock
~~~

With a local `DefaultLockRegistry`, each pod holds **its own** locks with zero cross-node coordination. With a shared multi-node store, evaluate `JdbcLockRegistry`, lock repository/schema/lease settings, and transaction isolation; alternatively, partition messages so each group has a single owner at any point in time.

**A shared `JdbcMessageStore` alone does not prove concurrency correctness.** Add/release/remove operations and business outputs must be tested under race conditions, failover, and lock lease expiry.

### Two Scale-Out Models

| Model | How It Works | Trade-Offs |
| --- | --- | --- |
| **Partition by `batchId`** | All parts of a group route to one owner consumer | Hot groups, rebalancing, pending-state handoff |
| **Shared store + distributed lock** | Multiple pods read/write groups, locking per correlation key | Lock overhead, DB contention, lease/liveness issues |
| **External workflow coordinator** | State lives in a process manager/workflow service | Cleaner long-running sagas; more infrastructure |

Never scale executor threads blindly to solve a hot correlation key: extra threads may just increase lock wait and DB connection pressure.

## 22. Schema Migrations and Old Serialized Messages

`JdbcMessageStore` must deserialize messages written by earlier application versions. If you seed with version A and resume with version B, several things can break:

- Java payload classes are no longer compatible with the serializer.
- Headers were added or changed types.
- The JDBC schema underwent an incompatible upgrade.
- `JdbcMessageStore.region` changed, pointing the app to the wrong logical namespace.
- The release strategy changed, stranding older groups so they never complete.
- The correlation key format changed, routing P3 to a new group.
- Stored `replyChannel`/`errorChannel` references cannot be restored across JVMs as expected.

In the lab we used **`String` payloads** and `String` headers to reduce complexity. For complex domain objects, use versioned DTO schemas and backward-compatible serialization contracts.

### Expand–Migrate–Contract

1. **Expand:** deploy a new reader capable of reading both old and new data formats.
2. **Migrate:** migrate schemas/stores/serialized payloads, or let pending groups drain under the compatible reader.
3. **Contract:** drop legacy support only after zero old messages remain.
4. **Rollback:** also test the case where an older version must read state written by the newer version during a rolling deploy.

With long-lived pending groups, new code may encounter serialized messages written several releases ago. Never "wipe the database" to avoid decode errors without an explicit, controlled data-loss decision.

## 23. Observing and Measuring Recovery

The lab should emit observability signals beyond the two seed/resume log lines.

| Metric / Signal (Suggested) | Meaning | How to Read |
| --- | --- | --- |
| `aggregator.group.pending` | Unfinished group count | Watch for sustained growth |
| `aggregator.group.oldest.age` | Age of oldest pending group | Alert on missing parts |
| `aggregator.part.accepted` | Logical parts persisted | Distinguish send vs. store |
| `aggregator.part.duplicate` | Rejected duplicate parts | Track redeliveries |
| `aggregator.group.released` | Groups reaching release | Does not mean output committed |
| `aggregator.output.confirmed` | Confirmed outbound business outcomes | Track SLO |
| `aggregator.store.read/write.duration` | JDBC latency | DB/serialization bottlenecks |
| `aggregator.store.error` | Persistence failures | Retries/quarantine |
| `aggregator.lock.wait` | Lock contention | Multi-node hot keys |
| `aggregator.group.expired` | Expired groups | Missing/late parts |
| `flow.inflight`, `queue.depth` | Pending work | Backpressure |
| `recovery.time.to.first.batch` | Time from restart to first output | Recovery speed |

**These are suggested instrumentation names**; Spring Integration does not emit all of them out of the box. Use Micrometer `Observation`/`Timer`/`MeterRegistry` appropriately and avoid logging full payloads needlessly.

### Avoid High-Cardinality Metrics

Never use `batchId`, `partId`, `eventId`, or raw `MessageHistory` as metric labels. Put those in structured logs or traces governed by retention and access policies. Metric tags should use low-cardinality values like endpoint, region, outcome, store type, and exception class.

### Message History and Tracing

`MessageHistory` can show that P3 passed through the transformer and aggregator. It cannot replace `MessageGroupStore` for knowing whether P1/P2 are pending. To trace across restarts, carry stable `batchId`/`eventId` values, trace/log correlations, and application-level recovery events.

## 24. Common Troubleshooting Table

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Seed creates no tables | Forgot `spring.sql.init.mode=always` on first run, or missing JDBC dependency | Verify `schema-locations` and classpath |
| `Table already exists` during seed | Ran bootstrap script a second time on an existing DB | Use `mode=never` once tables exist |
| Resume reports `pending=0` | Wrong working directory, JDBC URL, region, or `batchId` | Compare configs across both runs verbatim |
| Resume reports `pending=1` | Seed/transaction did not persist all parts, or wrong batch | Check logs/DB and source deliveries |
| Resume fails to deserialize | Version mismatch in payload/header serializer | Pin BOM; plan migrations/compatibility |
| Group size=2 before restart, no output after P3 | Wrong release strategy, routing, or output channel | Inspect integration graph and group state |
| Output fires with only 2 parts | Duplicate arrival or flawed release condition | Log distinct part IDs; fix release validation |
| P3 opens a new group | Correlation key case/type mismatch | Normalize `batchId`; inspect headers |
| Switching to `ExecutorChannel` makes test flaky | Async send returns before store persist finishes | Await store condition; avoid fixed sleeps |
| H2 file locked | Old JVM still running or another process holds lock | Ensure strictly one process at a time |
| Completed group re-opens on late part | `expireGroupsUponCompletion(true)` removed group | Add closed markers and late-event policies |
| In-memory `QueueChannel` loses output on crash | Non-durable output | Add durable outbox/broker |
| Multi-node duplicate output | Local locks do not coordinate across pods | Partition ownership or distributed locks + dedupe |
| Pending groups grow endlessly | Missing parts or no expiry | Add timeout policies, alerts, quarantine |
| DB connection pool exhausted | Slow JDBC, long transactions, retries | Monitor pool metrics, timeouts, storage tuning |
| Handler throws yet source still acks | Error swallowed or recovered at wrong boundary | Verify ack and transactional failure paths |

## 25. Fault-Injection Matrix for the Project

| Scenario | Action | Expected Result |
| --- | --- | --- |
| Happy path | Seed 2/3, close JVM, resume 1/3 | Exactly one batch result |
| No persistence | Swap `JdbcMessageStore` for `SimpleMessageStore` | Resume sees 0 parts |
| Wrong DB | Resume with different JDBC URL | Pending group not found |
| Wrong region | Resume with different `setRegion` | Pending group invisible |
| Wrong group key | P3 uses `batchId=BATCH-102` | `BATCH-101` stays 2/3 |
| Duplicate part | Seed P1/P2 then resend P2 | Demo releases early; production must deduplicate |
| Late part | After result, resend P1 | Must not emit a duplicate logical result |
| Crash after commit | Kill after store-committed marker | Restart recovers pending group |
| Crash before commit | Kill before transaction commits | Source must redeliver part |
| Output-lost window | Kill after group cleanup before output persisted | Demonstrates need for outbox/durable queue |
| DB unavailable | Block JDBC writes | Message never silently acked as succeeded |
| Old serialized data | Seed with old code, resume with new code | New reader decodes or migrates cleanly |
| Concurrent writers | Two nodes add to same group | No lost parts or duplicate releases |
| Expired group | Never send P3 past deadline | Failure/expiry event + controlled cleanup |
| Retry storm | DB timeout + continuous handler retries | Backoff and retry budget prevent pool exhaustion |

### Test Verification Checklist

Do not trust a `RESUME_OK` log line alone. Cross-check simultaneously:

1. JDBC group counts and group sizes at each checkpoint;
2. Output message/payload and stable batch result ID;
3. Deduplication/inbox markers if configured;
4. Source acknowledgments or broker redelivery logs;
5. Transaction commits and rollbacks;
6. Error/recovery message stores;
7. Lock wait times and pending group ages;
8. Restart compatibility after deploying a new version.

## 26. Runbook When Applications Restart Without Completing Batches

**Symptom:** after deployment, the application is running and the database is healthy, yet pending batches fail to release.

### Investigation Sequence

1. Identify `batchId`, `region`, JDBC URL/schema, and the running instance's code version.
2. Query pending group sizes and ages in the **real store**, not an in-memory counter.
3. Verify all parts share the exact same correlation header, key, and type.
4. Check for missing source event IDs, duplicates, and DLQ records.
5. Check release strategy and serializer compatibility after the deploy.
6. Inspect JDBC connection pools, lock registries, transactions, deadlocks, and timeouts.
7. Check whether input channels, pollers, and executors are running with active subscribers and throughput.
8. Check whether any released output failed to commit or ack.
9. If replaying a missing part, use its **original stable `eventId`** under the deduplication policy.
10. Delete groups only after a formal business decision and recovery plan; never manually delete JDBC rows impulsively.

### Rolling Restart Procedure

~~~mermaid
flowchart TD
    A["Prepare deploy"] --> B["Inventory pending groups + schema"]
    B --> C["Pause/drain ingress if needed"]
    C --> D["Confirm persistence + transactions"]
    D --> E["Stop one instance"]
    E --> F["Start new version, same store + region"]
    F --> G["Verify pending group readback"]
    G --> H["Send/receive controlled part"]
    H --> I{"Output valid + no duplicates?"}
    I -->|Yes| J["Resume and monitor backlog"]
    I -->|No| K["Quarantine / rollback / reconcile"]
~~~

**Never restart all pods simultaneously** if group state requires migration or distributed locks/connection pools are tight. In the local H2 demo, run processes strictly one after another. In production, test multi-node shared-DB rollouts separately.

## 27. Upgrading the Project: Separating Stateless and Stateful Flows

The example combines transform and aggregate inside one `IntegrationFlow`; you can split them into two beans for independent scaling and observability.

Model:

~~~text
inputParts
  -> normalizationFlow (stateless)
  -> normalizedParts channel
  -> aggregationFlow (stateful, JDBC MessageGroupStore)
  -> completedBatches
~~~

Benefits:

- The stateless transformer is easy to unit test and scale independently.
- The stateful aggregator isolates its correlation strategy, group timeout, and lock registry.
- A durable broker/queue can sit at the boundary to buffer inputs when the stateful backend slows down.
- Metrics distinguish normalization time, queue wait, and store add/release durations.
- Easy to test "input normalized accurately" separately from "groups survive restarts."

### Java DSL Skeleton

~~~java
@Bean
IntegrationFlow normalizationFlow() {
    return IntegrationFlow.from("inputParts")
            .transform(String.class,
                    s -> s.strip().toUpperCase(Locale.ROOT))
            .channel("normalizedParts")
            .get();
}

@Bean
IntegrationFlow aggregationFlow(MessageGroupStore batchStore) {
    return IntegrationFlow.from("normalizedParts")
            .aggregate(spec -> spec
                    .correlationStrategy(message ->
                            message.getHeaders().get("batchId"))
                    .releaseStrategy(group -> group.size() >= 3)
                    .messageStore(batchStore))
            .channel("completedBatches")
            .get();
}
~~~

This snippet requires a `normalizedParts` channel bean and must not be declared alongside `batchFlow()` from Section 7. **Choose one topology** for your project rather than registering two competing aggregators on the same input. When switching to async or persistent channels, update wait assertions, transactions, and acks accordingly.

## 28. Mandatory and Advanced Exercises

### Part A — Verifying Persistence

1. **Bootstrap:** run seed on a fresh H2 file, ensuring the schema initializes exactly once.
2. **Readback:** confirm group size = 2 with zero output.
3. **Restart:** shut down the JVM completely and run resume with the same URL and region.
4. **Release:** verify output arrives after P3 and group completion cleans up per policy.
5. **Negative:** intentionally supply the wrong DB URL; explain why resume fails to load the group.
6. **In-memory baseline:** swap `JdbcMessageStore` for `SimpleMessageStore` and test across two JVMs.

### Part B — Correctness

7. **Correlation:** send P3 with a different `batchId`; explain the resulting states of both groups.
8. **Duplicate:** send P1/P2/P2 and observe the failure of releasing on raw group size.
9. **Dedupe:** add a stable `partId` marker/inbox and prove duplicates do not increment the distinct count.
10. **Late part:** send P1 after release and implement a closed-group policy.
11. **Incomplete group:** add timeouts and failure events without publishing partial successes.
12. **Out-of-order:** send P3/P1/P2; determine when a resequencer is required.
13. **Header mapping:** introduce a transformer that rebuilds messages; verify `batchId` and `eventId` survive.
14. **Version migration:** seed with an older serializer schema and resume on a newer version.

### Part C — Reliability and Operations

15. **Hard crash:** kill the process right after store commit, then resume.
16. **Lost-ack:** simulate source redelivery of P2 after store commit.
17. **Output crash:** stop right after group completion before outbound commit; prove why an outbox is needed.
18. **Multi-node:** switch to PostgreSQL and test locks/partition ownership.
19. **Contention:** send concurrent parts for the same `batchId`; measure lock wait and duplicate releases.
20. **Metrics:** build a dashboard tracking pending groups, oldest age, completed, expired, duplicates, and store latency.
21. **Runbook:** write a pause/drain/resume and replay plan without losing state.
22. **Security:** audit DB credentials/TLS, untrusted payload serialization, and access controls.
23. **Cleanup:** implement expiry/quarantine with retention; never manually delete active rows.
24. **Regression:** run the two-JVM test in CI asserting outputs/logs without hardcoded `Thread.sleep()`.

### Self-Check Questions

- Why does `SimpleMessageStore` fail across restarts?
- Why is stopping and restarting an endpoint inside one JVM insufficient to prove durability?
- How does what `MessageGroupStore` stores differ from a `QueueChannel` message store?
- What distinct decisions do `correlationStrategy` and `releaseStrategy` govern?
- Why use H2 `file:` instead of `mem:`?
- Why must JDBC URL, region, and `batchId` remain identical?
- Why should schema initialization run only on the first run?
- Once all 3 parts arrive, what gap remains with an in-memory output `QueueChannel`?
- Does deleting a completed group automatically block late P1/P2 arrivals?
- If the broker redelivers P2, why can raw group size trigger an invalid result?
- Why are an idempotent receiver/outbox still needed even when JDBC group state is durable?
- Does a multi-node shared group store require distributed locking or key ownership?
- When a transaction fails between add and ack, how must the source behave?
- Why does the metric `aggregator.group.released` not prove the business side effect committed?

## 29. Project Completion Checklist

| Item | Pass Condition |
| --- | --- |
| Build dependencies | JDBC + Integration + H2 aligned with BOM |
| Durable DB | Stable `file:` JDBC URL, schema present |
| Seed | Two parts in same batch, group size=2 |
| No premature output | Output channel empty after seed |
| Process restart | First JVM exited completely |
| Resume | New JVM sees group size=2 before P3 |
| Release | Output produced after third part |
| Correlation | P3 with mismatched `batchId` does not trigger wrong release |
| Serialization | Older messages deserialize cleanly |
| Cleanup | Completed group handled per policy |
| Duplicate handling | Design/test blocks duplicate P2 increments |
| Late arrivals | Closed-group/replay policy in place |
| Timeout | Incomplete groups never hang forever |
| Crash/replay | Transaction/ack/outbox boundaries tested |
| Observability | Pending/expired/completed/duplicate metrics |
| Runbook | Clear restart, verification, and rollback procedures |
| Technical scope | STEP 4 authoring only; not yet STEP 6 QA |

## 30. Summary

This lesson started with three messages intentionally **split across two JVM runs**: two parts build an incomplete message group, the database retains state while no process is running, and the third part triggers release in a fresh application.

From that result emerges a core design principle:

> **A stateful runtime requires a state owner independent of worker lifetimes, paired with explicit contracts for correlation, transactions, retries, expiry, and output commits.**

`JdbcMessageStore` solves **persisting the message group**. Production safety additionally requires idempotency for duplicate/late messages, outbox/ack coordination for final outputs, proper transactions and locking, serializer migrations, observability, and fault-injection testing.

## 31. Official References

- [Spring Integration — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html): correlation, release, group timeout, expiry, and aggregator lifecycle.
- [Spring Integration — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html): `MessageStore`, `MessageGroupStore`, persistence contracts.
- [Spring Integration — JDBC Support](https://docs.spring.io/spring-integration/reference/jdbc.html): JDBC configuration, schemas, and database-specific store behavior.
- [Spring Integration — JDBC Message Store](https://docs.spring.io/spring-integration/reference/jdbc/message-store.html): JDBC-backed messages/groups and serializers.
- [Spring Integration Javadoc — JdbcMessageStore](https://docs.spring.io/spring-integration/api/org/springframework/integration/jdbc/store/JdbcMessageStore.html): constructors, group persistence, and region.
- [Spring Integration — Distributed Lock](https://docs.spring.io/spring-integration/reference/distributed-locks.html): `LockRegistry` and shared-state concurrency.
- [Spring Integration — Idempotent Receiver](https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html): deduplication and metadata stores.
- [Spring Integration — Metadata Store](https://docs.spring.io/spring-integration/reference/meta-data-store.html): storing simple idempotency markers.
- [Spring Integration — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): `IntegrationFlow`, aggregator spec, and channel composition.
- [Spring Integration — Message Channels](https://docs.spring.io/spring-integration/reference/channel/implementations.html): `DirectChannel`, `QueueChannel`, `ExecutorChannel`.
- [Spring Integration — Poller/Transaction](https://docs.spring.io/spring-integration/reference/polling-consumer.html): polling, transaction, and retry boundaries.
- [Spring Integration — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): `ErrorMessage`, `errorChannel`, and recovery.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): resource transactions and rollbacks.
- [Spring Boot — SQL Database Initialization](https://docs.spring.io/spring-boot/reference/how-to/data-initialization.html): `spring.sql.init.mode` and schema scripts.
- [H2 Database — Connection Modes](https://h2database.com/html/features.html): embedded file databases, connection URLs, and lifecycle.
