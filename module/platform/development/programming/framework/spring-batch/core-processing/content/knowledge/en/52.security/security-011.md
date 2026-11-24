# Protecting the Metadata Repository in Spring Batch

## 1. Why is the metadata repository an asset that needs protection?

In Spring Batch Core Processing, **`JobRepository`** is the infrastructure storing metadata so the framework can identify **`JobInstance`**, manage **`JobExecution`**, **`StepExecution`**, statuses, and checkpoints. This metadata determines whether a Job has already run, detects active runs, and recovers data from failed executions.

However, metadata is not merely harmless counters. Depending on application design, it can contain:

- Job and Step names reflecting sensitive business workflows or tasks.
- **`JobParameters`** such as business dates, customer names, account numbers, tenant IDs, file locations, and identifying parameters.
- Job and Step **`ExecutionContext`**, including reader positions, state keys, checkpoint details, and objects placed there by the application.
- **`ExitStatus`**, exit descriptions, exception messages, or error traces that may contain fragments of input data.
- Execution timings, transaction counts, failure counts, and operational details valuable to attackers.

Therefore, securing JobRepository is part of **security, privacy, integrity, and availability** in a batch system. If an unauthorized account gains **read** access, it can view sensitive business info. With **write** access, it can corrupt state and break restartability. With **delete** access, Jobs can lose history and checkpoints or accidentally reprocess completed data.

This lesson presents principles and implementation techniques for securing the metadata repository of **Spring Batch 5.x / Spring Boot 3.x**, illustrated with a JDBC JobRepository and PostgreSQL. The protection mindset applies equally to other database engines, while privilege syntax and connection settings must be adapted to your actual environment.

## 2. What does JobRepository store?

Basic metadata model:

~~~text
                           JobRepository
                                 |
             +-------------------+-------------------+
             |                   |                   |
       JobInstance         JobExecution         StepExecution
       (identity)          (each run)           (each Step run)
             |                   |                   |
       JobParameters       ExecutionContext      ExecutionContext
             |                   |                   |
       identifying        status, exit info     counts, checkpoint
~~~

In a JDBC JobRepository, tables normally carry the **`BATCH_`** prefix:

| Table / object | Typical information stored | Why it needs protection |
| --- | --- | --- |
| **BATCH_JOB_INSTANCE** | Job name, Job key, and JobInstance identity | Tampering can corrupt JobInstance identification |
| **BATCH_JOB_EXECUTION** | Run attempts, status, timestamps, exit code/description | Can reveal schedules; edits corrupt operational state |
| **BATCH_JOB_EXECUTION_PARAMS** | JobParameter names, types, values, and identifying flag | Can hold filenames, IDs, business data, or accidentally passed secrets |
| **BATCH_STEP_EXECUTION** | Read/write/filter/skip/commit/rollback counts, status, exit description | Reveals workload volume and failure causes |
| **BATCH_JOB_EXECUTION_CONTEXT** | Job-level ExecutionContext | Can hold state or sensitive data stored by the app |
| **BATCH_STEP_EXECUTION_CONTEXT** | Step-level ExecutionContext, often checkpoint-related | Directly affects accurate restartability |
| **Sequences / ID tables** | Database/schema metadata ID generators | Unsafe if modified or granted excessive privileges |

Exact table names and layouts depend on the Spring Batch version, database type, and custom table prefixes. When changing framework schemas, use migrations compatible with the running version; never alter metadata structure ad hoc assuming they are mere log tables.

### How do JobParameters differ from ExecutionContext?

**JobParameters** are parameters supplied when launching a Job. Parameters marked **identifying** participate in identifying a JobInstance. Example:

~~~java
JobParameters params = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("batchId", "import-20261115-001", true)
        .addString("requestedBy", "scheduler", false)
        .toJobParameters();
~~~

Even though **requestedBy** is non-identifying, it remains an execution parameter and can be persisted in metadata. The **identifying=false flag is not a security or encryption mechanism**.

**ExecutionContext** is a key-value map storing state that persists across checkpoints/restarts:

~~~java
ExecutionContext context =
        stepExecution.getExecutionContext();

context.putLong("lastProcessedId", 10500L);
context.putString("inputVersion", "v3");
~~~

Metadata serializers represent contents as strings or another serialized format. **Serialized/encoded data is not automatically encrypted data**. Putting tokens, passwords, or personal data into the context can leave them in databases and backups for years.

## 3. Threat model for metadata

Four main risk categories can be examined:

| Risk | Scenario | Impact |
| --- | --- | --- |
| **Disclosure** | An account reading metadata sees JobParameters containing API keys, customer IDs, or internal paths | Exposure of secrets and business data |
| **Tampering** | Someone changes Step status from STARTED to COMPLETED, or alters a checkpoint | Corrupt restarts, missing/duplicate processing |
| **Deletion** | A script deletes `BATCH_*` rows to "clean up" while a Job is running | Lost history, foreign-key errors, broken restarts |
| **Denial of service** | Someone triggers thousands of JobExecutions, holds locks, or fills the database | Batch system slows down, misses schedules |

Risk vectors include direct SQL privileges, admin REST endpoints, a compromised service account, applications sharing a DataSource, ops scripts, or improperly accessed logs and backups.

**Foundational principle:** the metadata repository is **execution control state**, not a statistics table any component can freely mutate. Only the framework and authorized administrative tools should modify metadata via supported contracts.

## 4. Separating access roles via least privilege

A clean permission model typically defines three roles:

1. **Migration owner:** creates and upgrades the Batch schema during controlled deployments.
2. **Batch runtime:** account used by the app to read, insert, and update metadata for Jobs.
3. **Read-only observer:** account for dashboards, reports, or audit tools needing status visibility only.

A fourth role may be **maintenance/retention operator** for purging historical metadata under an approved workflow, without granting those broad rights to every application.

| Role | SELECT | INSERT/UPDATE | DELETE | DDL |
| --- | --- | --- | --- | --- |
| Batch runtime | Needed | Needed for JobRepository operations | Only if workflows truly require it | Generally no |
| Read-only observer | Only needed tables/columns | No | No | No |
| Migration owner | Per migration needs | Per migration needs | Per migration needs | Controlled |
| Maintenance operator | Per archival/purge needs | Per procedure | Needed, tightly scoped | Only with clear justification |

During normal runtime, JobRepository mainly queries, inserts, and updates metadata. Do not grant runtime accounts **DROP TABLE**, **ALTER TABLE**, DBA privileges, or read access across all system schemas simply because the application uses Spring Batch.

However, **do not strip privileges mechanically from the table above**: verify the exact SQL required by your Spring Batch version, database driver, and admin features, especially for batch maintenance or history purges. Too few privileges cause runtime failures; too many create security risk.

## 5. PostgreSQL privilege example for Batch metadata

Suppose the **batch_meta** schema was created by migrations and contains the `BATCH_*` tables. Accounts must receive credentials through a secret management system—never write passwords directly into scripts or Git.

Illustrative SQL example:

~~~sql
-- Run as an appropriately privileged admin/migration account.
CREATE SCHEMA IF NOT EXISTS batch_meta;

-- Runtime and observer accounts must be provisioned through your
-- identity management workflow. ROLE statements below are illustrative.
CREATE ROLE batch_runtime LOGIN;
CREATE ROLE batch_observer LOGIN;

-- Prevent PUBLIC from using this schema by default.
REVOKE ALL ON SCHEMA batch_meta FROM PUBLIC;

GRANT USAGE ON SCHEMA batch_meta
    TO batch_runtime, batch_observer;

-- Batch runtime reads, creates, and updates metadata.
GRANT SELECT, INSERT, UPDATE
    ON ALL TABLES IN SCHEMA batch_meta
    TO batch_runtime;

-- JobRepository may use sequences to generate IDs.
GRANT USAGE, SELECT, UPDATE
    ON ALL SEQUENCES IN SCHEMA batch_meta
    TO batch_runtime;

-- Dashboard has read-only access to metadata.
GRANT SELECT
    ON ALL TABLES IN SCHEMA batch_meta
    TO batch_observer;
~~~

Notes when adapting this script:

- **CREATE ROLE** here is syntactic illustration; production should manage roles/passwords/rotation via DBA tooling, IAM, or a secret manager. Never leave LOGIN accounts without proper authentication policies.
- **GRANT ON ALL TABLES** applies to existing tables. If future migrations add tables/sequences, configure **default privileges** or re-apply grants during migration.
- `SELECT` across all metadata tables may still be too broad for a simple dashboard. Use **column- and row-restricted views** instead of giving observer accounts direct access to every table.
- Runtime privileges vary on other engines; SQL Server, Oracle, and MySQL do not share PostgreSQL's exact syntax.
- **DELETE** is omitted from the runtime example. If your app uses APIs or metadata cleanup jobs requiring `DELETE`, grant it to a dedicated operational account/path and verify against the exact contract.
- Table and sequence names may differ if custom prefixes/schemas are configured.

A stronger isolation pattern creates a **summary-only view** for dashboards:

~~~sql
CREATE VIEW batch_meta.v_step_status AS
SELECT
    se.STEP_EXECUTION_ID,
    se.JOB_EXECUTION_ID,
    se.STEP_NAME,
    se.STATUS,
    se.READ_COUNT,
    se.WRITE_COUNT,
    se.COMMIT_COUNT,
    se.ROLLBACK_COUNT
FROM batch_meta.BATCH_STEP_EXECUTION se;
~~~

Dashboard users need `SELECT` only on the view rather than all JobParameters and ExecutionContexts. In PostgreSQL, design the view and underlying table privileges using appropriate ownership/security-invoker settings. Avoid accidentally granting observers read access to base tables when only the view is intended.

## 6. Isolating schemas and JobRepository connections

Several isolation tiers are commonly used:

### 6.1. Same database, separate schemas

~~~text
application_db
  |
  +-- business_data
  |     +-- orders
  |     +-- customers
  |
  +-- batch_meta
        +-- BATCH_JOB_INSTANCE
        +-- BATCH_JOB_EXECUTION
        +-- BATCH_STEP_EXECUTION
        +-- ...
~~~

Benefits: easier backup and transaction management within one database while allowing per-schema privileges. However, verify runtime connects to the right schema/prefix. If one pod uses **public.BATCH_*** while another uses **batch_meta.BATCH_***, the instances no longer share the same repository.

### 6.2. Dedicated database for metadata

~~~text
batch-metadata-db  -> JobRepository
orders-db          -> ItemReader / ItemWriter
~~~

This strengthens privilege, backup, and resource isolation. Yet understand the **transaction boundary between metadata and business data**: two separate DataSources do not automatically form an atomic distributed transaction. Using one local transaction manager across two databases can let metadata checkpoints and written data diverge if misdesigned.

For critical Jobs, explicitly define transaction managers for JobRepository and Steps, rollback policies, checkpoints, and writer idempotency. Never split databases "to be safer" while neglecting restart consistency.

### 6.3. Multiple instances must share a metadata source

When multiple scheduler/worker instances run a Batch system and coordinate state, they normally must share **the same JobRepository** matched to your concurrency design. If each pod accidentally points to an in-memory H2 database or separate schemas, each pod can create its own JobInstance for the same processing period.

Availability and access control of the repository database are part of distributed architecture. Monitor connection pools, locks, latency, backup/restore, and failover readiness.

## 7. Do not store passwords or tokens in JobParameters

A common mistake is passing secrets as Job parameters:

~~~java
// Unsafe: passwords may be persisted in metadata.
JobParameters params = new JobParametersBuilder()
        .addString("apiToken", realApiToken, false)
        .addString("sftpPassword", sftpPassword, false)
        .toJobParameters();
~~~

Setting **identifying=false** does not remove the parameter from the repository, logs, or query tools.

Instead, store only a non-sensitive **reference** or identifier:

~~~java
JobParameters params = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("sourceId", "partner-feed-A", true)
        .addString("credentialRef", "partner-feed-A/read", false)
        .toJobParameters();
~~~

Here **credentialRef** is a logical name used to fetch secrets from a secret manager or controlled config service. Even references warrant review, since partner names or data sources can sometimes be sensitive themselves.

A component using a secret manager resolves the reference at runtime:

~~~java
public interface CredentialResolver {
    String resolveToken(String credentialRef);
}

@Service
public class PartnerFeedClient {

    private final CredentialResolver resolver;

    public PartnerFeedClient(CredentialResolver resolver) {
        this.resolver = resolver;
    }

    public void fetch(String credentialRef) {
        String token = resolver.resolveToken(credentialRef);

        // Send token in request header over TLS.
        // Never put token into JobParameters, ExecutionContext, or logs.
    }
}
~~~

In real systems, add client configuration, timeouts, token lifecycles, and proper token scrubbing/rotation. Secrets should be issued with least privilege, rotatable, and omitted from exception messages.

### Other sensitive fields to consider

Even when not passwords, metadata can still contain:

- Account numbers, emails, phone numbers, or customer identifiers.
- File paths containing tenant info, usernames, or internal data.
- Bucket names, hostnames, internal endpoints.
- Search criteria containing personal data in JobParameters.
- Financial transaction IDs or partner system names.

For every parameter, ask: **Is storing this value truly needed to identify or restart the Job?** If not, store an intermediate ID and let the application look up details from an access-controlled store.

## 8. ExecutionContext is a checkpoint, not an arbitrary data store

ExecutionContext is persisted by Spring Batch to recover reader/writer state or application-defined execution state. Sensible example:

~~~java
ExecutionContext context =
        stepExecution.getExecutionContext();

context.putLong("lastProcessedOrderId", 100500L);
context.putString("inputSnapshotId", "snapshot-20261115");
~~~

Risky example:

~~~java
// Do not store full sensitive data in checkpoints.
context.putString("accessToken", accessToken);
context.put("rawCustomerRecord", customerWithPersonalData);
context.putString("sqlWithPassword", connectionStringWithSecret);
~~~

Because context is persisted in the database, a crash/restart can preserve sensitive data far longer than intended. Context stored as encoded bytes or a serialized string **can still be read** by anyone with sufficient privileges and knowledge of the serializer.

Design principles:

1. Store only the **minimal state needed for restart**, such as offsets, last IDs, or input versions.
2. Avoid storing whole objects containing personal data or credentials.
3. Never use context as a cache for thousands of items; it both increases data exposure and adds serialization/checkpoint overhead.
4. If a sensitive identifier is strictly required, consider tokenization, application-level encryption with key management, or redesigning storage.
5. Audit default data written by readers/writers into ExecutionContext, especially resource names, paths, keys, or source metadata.

**Never manually edit ExecutionContext in the database to "skip over" a failing record.** Altering checkpoints without understanding transaction boundaries can cause lost or duplicated data.

## 9. Controlling exceptions and ExitStatus to prevent data leaks

When an ItemReader, ItemProcessor, or ItemWriter throws an error, Spring Batch may persist error info into JobExecution/StepExecution metadata depending on configuration. An uncontrolled exception message can contain input data or secrets:

~~~java
// Unsafe: raw data may be persisted/logged.
throw new IllegalStateException(
        "Invalid customer record: " + rawCustomerJson);
~~~

A better error message:

~~~java
throw new InvalidOrderException(
        "Invalid order amount, batchId=" + batchId
        + ", lineNumber=" + lineNumber);
~~~

In the second example, `batchId`/`lineNumber` must be safe identifiers per your organization's data policy. You can emit a correlation ID to a separately secured log for tracing without placing sensitive payloads in broadly persisted messages.

When using custom **ExitStatus**, avoid embedding tokens, raw SQL with credentials, input JSON, or personal data:

~~~java
// Meaningful status code without sensitive payload.
return new ExitStatus("VALIDATION_FAILED", "invalid_input");
~~~

Beyond metadata, inspect logs from Spring Batch, JDBC frameworks, HTTP clients, tracing, and alerting. Securing the repository while letting stack traces carrying tokens appear in public logs remains a vulnerability.

### When error details must be kept for investigation

Store error details in a **tightly secured audit store** with dedicated retention, authorization, and encryption. In Batch metadata, store only an error code and correlation ID for lookup. That way progress observers do not automatically gain access to failing record contents.

## 10. Securing JobExplorer query interfaces and admin APIs

Spring Batch provides **JobExplorer** for reading metadata and operational APIs like **JobOperator** for controlling Job lifecycles. When building REST endpoints, CLIs, or internal dashboards, enforce access control at the **application layer**, not just via database privileges.

Example distinguishable application permissions:

| Application permission | Allowed business capability |
| --- | --- |
| **BATCH_METADATA_READ** | View Job/Step lists and non-sensitive counts |
| **BATCH_JOB_START** | Request launching an authorized Job |
| **BATCH_JOB_RESTART** | Restart an eligible JobInstance |
| **BATCH_JOB_STOP** | Stop a JobExecution per procedure |
| **BATCH_AUDIT_READ** | View permitted detailed audit data |
| **BATCH_ADMIN** | Perform controlled advanced admin operations |

**Permission to read metadata does not imply permission to restart or stop a Job.** Endpoints letting users pick arbitrary Job names, parameters, or execution IDs must be protected against unauthorized access and overload/duplicate-run abuse.

### Example returning minimized data only

With Spring Security method security enabled:

~~~java
@Configuration
@EnableMethodSecurity
public class BatchMethodSecurityConfig {
}
~~~

Service returning a DTO without JobParameters or ExecutionContext:

~~~java
import java.util.List;

import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class SafeBatchMetadataService {

    private final JobExplorer explorer;

    public SafeBatchMetadataService(JobExplorer explorer) {
        this.explorer = explorer;
    }

    @PreAuthorize("hasAuthority('BATCH_METADATA_READ')")
    public List<StepStatusView> stepStatuses(long jobExecutionId) {
        JobExecution execution = explorer.getJobExecution(jobExecutionId);

        if (execution == null) {
            throw new IllegalArgumentException(
                    "Unknown jobExecutionId=" + jobExecutionId);
        }

        return execution.getStepExecutions().stream()
                .map(step -> new StepStatusView(
                        step.getStepName(),
                        step.getStatus().name(),
                        step.getReadCount(),
                        step.getWriteCount(),
                        step.getCommitCount()))
                .toList();
    }

    public record StepStatusView(
            String stepName,
            String status,
            long readCount,
            long writeCount,
            int commitCount) {}
}
~~~

This example demonstrates **data minimization** and authorization via **@PreAuthorize**. Production also needs authentication, a SecurityFilterChain, TLS, auditing, rate limiting, per-Job visibility controls, and safe outbound error handling.

**@PreAuthorize** works when the bean is managed by Spring Security and calls go through Spring's interception proxy; calling a method directly via self-invocation can bypass checks depending on proxy mode. Security tests must invoke through the actual interface layer such as HTTP or a proxied service bean.

### ID-based access trap in multi-tenant systems

A user holding **BATCH_METADATA_READ** is not necessarily allowed to view **every** JobExecution. When Jobs from multiple tenants share one repository, endpoints accepting sequential numeric IDs risk **IDOR (Insecure Direct Object Reference)**.

Verify **scope** by tenant/business unit before returning results. JobExplorer does not enforce tenant authorization rules for your application automatically. Design a dedicated permission-mapping table or a repository/service filtered by trusted tenant context; never trust a client-supplied `tenantId` alone.

## 11. Distinguishing JobExplorer and JobOperator

Principles when building operational tooling:

**JobExplorer** is suited for reading history and status. Return only fields needed for the user's task; never serialize raw **JobExecution** objects to JSON if they expose JobParameters or exception details.

**JobOperator** can start, restart, stop, or manipulate lifecycles per the current API. This is **execution control privilege**, requiring higher authorization than read-only monitoring.

**JobRepository** is framework infrastructure for creating/updating metadata. Never build a SQL endpoint letting users directly edit **STATUS**, **VERSION**, **JOB_KEY**, or **SHORT_CONTEXT** fields to steer a Job; doing so breaks invariants and can bypass Spring Batch lifecycle rules.

In internal applications, administrative actions should have:

- Per-action authentication and authorization.
- Validation of allowed Jobs alongside controlled parameters.
- Guards against overlapping business periods or exceeding concurrent Job caps.
- Rate limits, audit trails, and correlation IDs.
- Error responses free of stack traces/secrets.
- Approval workflows when actions affect financial or customer data.

## 12. Securing repository connections, secrets, and backups

Application-layer protections are insufficient if database traffic or backups are exposed.

### 12.1. Transmitting data over secure connections

Use TLS between the application and database per environment standards. For PostgreSQL, configure the JDBC URL to enforce server certificate verification:

~~~properties
spring.datasource.url=jdbc:postgresql://db.internal.example:5432/batchdb?sslmode=verify-full
spring.datasource.username=batch_runtime
# Password retrieved from secret manager or secure runtime configuration,
# never commit real values to source control.
~~~

When using **verify-full**, the client must trust the right CA and the hostname must match the certificate. **Never switch to disabling certificate validation just to "fix" TLS errors.**

If the app has multiple DataSources, the snippet above illustrates only one connection; apply TLS to the exact DataSource used by Spring Batch JobRepository.

### 12.2. Encryption at rest and backups

Metadata should be protected with encryption at rest per database/storage policy, along with encrypted backups, snapshots, and data exports.

However, **encryption at rest does not replace SELECT permissions**: runtime accounts authorized to read metadata still receive decrypted values from the database. Secrets mistakenly written to JobParameters can still leak through APIs or logs even when disks are encrypted.

### 12.3. Account and credential management

- Use a secret manager, workload identity, or organization-approved mechanism.
- Never hardcode passwords in source code, shared test fixtures, or startup logs.
- Enforce rotation and scope access per application/environment.
- Separate production, staging, and test accounts to prevent cross-environment mistakes.
- Never use DBA/admin accounts for Batch runtime.
- Monitor failed connections and anomalous login behavior.

For database backups and replicas, also control who can read metadata on copies; sensitive data does not stop being sensitive simply because it sits in a backup.

## 13. Auditing and observing repository activity

Events worth recording:

| Event | Why observe |
| --- | --- |
| New JobExecution created | Detect anomalous schedules or manual launches |
| JobInstance restarted | Identify who/why a rerun was triggered |
| Job stopped or abandoned | Trace operational interventions |
| Sensitive metadata accessed | Support unauthorized-access investigations |
| DB login/role changes | Detect anomalous privilege modifications |
| Batch schema DDL/migrations | Track when the repository was upgraded |
| Metadata deleted or archived | Protect restartability and retention compliance |
| Spike in JobExecutions | Detect scheduler bugs or abuse |

Record correlation ID, Job name, Step, JobExecution ID, actor, timestamp, and action outcome. Avoid dumping full JobParameters/ExecutionContext into general audit logs.

**Metrics** such as active Jobs, failure rates, JobRepository query latency, metadata table sizes, and authorization failures provide early warnings.

Never attach **jobExecutionId**, customerId, or tokens as unbounded Prometheus metric tags. Those belong in logs/traces or controlled audit stores; aggregate metrics should use low-cardinality tags like `jobName`, `status`, or `environment`.

### Detecting anomalous behavior

Suppose an admin endpoint suddenly calls restart 500 times per minute across different executions. The system needs rate limits and audits to catch it, since an attacker or bug could abuse granted rights to overload the database/workers.

If a read-only account starts attempting `INSERT`/`UPDATE` on `BATCH_*` and hitting permission denied, that is also a signal to investigate. Auditing does not block access itself, yet enables detection and forensic evidence afterward.

## 14. Metadata retention, cleanup, and delete privileges

Over time, metadata tables grow large as each JobInstance accumulates runs, StepExecutions, and checkpoints. Retention balances two competing goals:

- Keep enough history for investigations, audits, and restarting incomplete Jobs.
- Avoid keeping sensitive data longer than necessary or overloading the repository.

A practical classification policy:

| Metadata category | Typical policy |
| --- | --- |
| JobExecution currently STARTING/STARTED | Never delete |
| Restartable FAILED JobExecution | Keep until resolved or approved recovery window expires |
| Old COMPLETED JobExecution | May archive/purge per business retention policy |
| JobInstance with active related history | Delete only in safe dependency order per explicit policy |
| Exceptions/ExecutionContext with sensitive data | Evaluate retention limits and masking/encryption |
| Finalized audit reports | Follow separate legal/internal compliance policies |

**Never randomly delete rows in BATCH_JOB_EXECUTION, BATCH_STEP_EXECUTION, or ExecutionContext** with ad-hoc manual DELETE statements. Tables have foreign keys and state relationships; out-of-order deletes can corrupt data or break restartability.

Design principles:

1. Run cleanup only after confirming no Job actively uses the target metadata.
2. Respect dependencies across JobInstance, JobExecution, StepExecution, and ExecutionContext.
3. Use a controlled archive/cleanup procedure tested against backups or staging equivalents.
4. Use a dedicated maintenance account; normal runtime does not need privileges to delete full history.
5. Retain logs/records of deleted row counts, scope, and operator identity.
6. Ensure backups/restores match the Spring Batch schema and version.

**JobRepositoryTestUtils.removeJobExecutions()** is a helpful **testing** utility, not a default choice for production cleanup. Deleting metadata currently used by another test or process can cause flaky failures.

## 15. Never edit metadata directly to fix Job failures

Some shortcuts look simple yet are dangerous:

~~~sql
-- DO NOT run as a routine remediation.
UPDATE BATCH_JOB_EXECUTION
SET STATUS = 'COMPLETED'
WHERE JOB_EXECUTION_ID = 1234;
~~~

This SQL cannot guarantee the Step wrote all outputs or committed its final transaction. It can also trick Spring Batch into treating an unfinished execution as completed.

Likewise, editing **ExecutionContext** to tweak an offset can make a reader skip items or re-read from the wrong position. When a Job stays **STARTED** after its process actually died, investigate metadata, transactions, and recovery mechanics using an organization-approved procedure. Framework admin APIs can help manage lifecycle states, but never assume updating `STATUS` alone fixes business data.

Distinguish:

- **Operational status repair:** controlled lifecycle action.
- **Data recovery:** restart/reprocess/compensate by business key.
- **Corrupted metadata repair:** specialized maintenance requiring backups and impact analysis.

If unauthorized metadata tampering occurred, prioritize isolating credentials, preserving evidence, comparing backups/audits, and re-verifying outputs rather than relaunching Jobs on potentially forged checkpoints.

## 16. Preventing data leaks via logging, APIs, and monitoring

A system may enforce strong DB privileges yet still leak metadata through side channels:

~~~text
PostgreSQL batch_meta
         |
         +--> application log
         +--> REST /internal/batch/executions
         +--> distributed tracing
         +--> error monitoring
         +--> support dashboard
         +--> backup / export file
~~~

Apply **data minimization** at every outlet:

- Expose only statuses, start/end times, and counts needed by viewers.
- Never dump raw ExecutionContext, exception stack traces, or full JobParameters as JSON automatically.
- Mask or replace sensitive values with reference codes.
- Enforce environment- and tenant-scoped dashboard authorization.
- Keep HTTPS/TLS and secure session/token configs on admin APIs.
- Configure appropriate retention on logs, traces, metrics, and exports.
- Test error paths to confirm exceptions never leak credentials in responses.

When deep debugging is needed, provide a separate audited access path with strict authorization and access logging rather than exposing details to everyone viewing dashboards.

## 17. Separating dev, test, and production environments

Development environments often use in-memory H2, auto-run schema creation scripts, and metadata cleanup utilities. That suits local tests yet is dangerous if copied verbatim to production.

Example config restricted to test environments:

~~~properties
# Only in ephemeral test/dev databases.
spring.batch.jdbc.initialize-schema=always
spring.batch.job.enabled=false
~~~

In production, run migrations via Flyway/Liquibase or DBA-approved processes; runtime does not need to create/drop schemas itself.

~~~properties
# Production example: schema managed by migrations.
spring.batch.jdbc.initialize-schema=never
~~~

This property controls only initializing the **Batch metadata schema** via Spring Boot; it does not enforce SQL permissions, create roles, encrypt JobParameters, or scan for secrets.

Additional rules:

- Never point test suites at a production JobRepository.
- Never share credentials across environments.
- Never put production DB dumps containing PII onto developer laptops without anonymization and approval.
- Never run test cleanups against a repository serving live Jobs.
- Even with Testcontainers or ephemeral DBs, avoid logging tokens in fixtures.

## 18. Testing metadata repository security

A security design is trustworthy only when tests cover both **success paths and denial paths**. Tests can span several layers:

### 18.1. Testing database privileges

Prepare a test metadata schema and roles mirroring production:

1. Run a simple Job as **batch_runtime**. Confirm JobRepository reads/writes metadata and creates valid StepExecutions.
2. Run `SELECT` on the permitted monitoring view as **batch_observer**.
3. Verify the observer account cannot `INSERT`/`UPDATE`/`DELETE` `BATCH_*` tables.
4. Verify the runtime role cannot `DROP` or `ALTER` the metadata schema.
5. If a retention role exists, verify `DELETE` is granted only within the exact required scope.

Use a database engine matching production when testing privileges, since H2 authorization semantics differ from PostgreSQL/Oracle/MySQL.

### 18.2. Testing JobParameters and ExecutionContext

A useful test launches a Job with allowed parameters and verifies metadata contains no raw secrets:

~~~java
JobParameters params = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("credentialRef", "feed-A/read", false)
        .toJobParameters();

JobExecution execution = jobLauncher.run(importJob, params);

// Using JobExplorer or test metadata tables,
// verify no real token/password values appear in parameters/context.
// Never log tokens on assertion failure.
~~~

Another test can induce an exception containing sensitive test data and verify application sanitization blocks it before reaching logs, audits, and responses. Never use production credentials in fixtures.

### 18.3. Testing endpoint authorization

With Spring Security Test and MockMvc, test internal monitoring endpoints per role. Suppose endpoint **GET /internal/batch/executions/42** is implemented and secured:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class BatchMetadataAuthorizationTest {

    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(authorities = "BATCH_METADATA_READ")
    void metadataReaderCanViewSanitizedExecution() throws Exception {
        mvc.perform(get("/internal/batch/executions/42"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.jobParameters").doesNotExist())
                .andExpect(jsonPath("$.executionContext").doesNotExist());
    }

    @Test
    @WithMockUser(authorities = "BATCH_JOB_START")
    void launcherCannotReadMetadataWithoutReadPermission() throws Exception {
        mvc.perform(get("/internal/batch/executions/42"))
                .andExpect(status().isForbidden());
    }
}
~~~

This snippet requires a fixture with matching JobExecution ID or an appropriately mocked endpoint/service; Spring Boot Test, Spring Security Test, and MockMvc imports/dependencies must be configured in the project.

Beyond role checks, especially in multi-tenant apps, create two distinct tenants and verify a tenant A user **cannot view tenant B's execution** even if they know the numeric ID.

### 18.4. Testing restart safety and metadata integrity

In an integration test:

- Run a Job over deterministic data and trigger a controlled mid-run failure.
- Verify JobRepository retains checkpoints and failed status.
- Restart using the exact same identifying JobParameters.
- Verify zero lost/duplicated records, idempotent writes, and accurate final Job outcome.
- Verify an unauthorized account cannot modify StepExecution/ExecutionContext between runs.

This proves **metadata access and integrity directly govern final business data**, not merely monitoring pages.

## 19. Organizing privileges in multi-tenant models

If multiple organizations or customers share one Spring Batch deployment, JobRepository may hold metadata for many tenants. Three isolation levels exist:

| Level | Characteristics | Risks to address |
| --- | --- | --- |
| Single shared repository, app-level auth | Low cost, metadata in shared tables | IDOR, logs, or queries reading wrong tenant |
| Separate schema per tenant | Stronger DB privilege separation | Prefix/schema config, migrations, and connections |
| Separate database per tenant | Strongest isolation | Managing multiple repositories, connections/backups, and monitoring |

In the shared model, **JobParameters containing `tenantId` does not automatically turn JobRepository into Row-Level Security**. JobExplorer and SQL can still read cross-tenant metadata unless an additional authorization layer is enforced.

If using PostgreSQL RLS or tenant-filtering views, verify compatibility with metadata relationships, transactions, connection pooling, and framework queries. Do not enable RLS on Batch tables without testing the entire lifecycle, because JobRepository touches multiple related tables in one transaction.

A straightforward option for batches with strict isolation requirements is physically separating repositories—while accounting for operational, backup, centralized querying, and Job identification costs across repositories.

## 20. Evaluation table of protection controls

| Control | Protects against | Does not fully solve |
| --- | --- | --- |
| **Least-privilege DB role** | Unauthorized metadata read/write/delete | Data exposure if runtime account is compromised |
| **Schema/database separation** | Access beyond granted structural scope | Wrong JobParameters or idempotency bugs |
| **No secrets in params/context** | Credential leaks via metadata | Secrets leaked in logs or other systems |
| **TLS to database** | Eavesdropping in transit | Unauthorized reads after valid login |
| **Encryption at rest/backups** | Exposure from raw disks or backups | Valid `SELECT` queries returning plaintext |
| **API authorization + tenant scope** | Unauthorized Job reads or control via API | Overly broad direct SQL privileges |
| **Auditing + monitoring** | Enables detecting and investigating abuse | Does not block events by itself |
| **Retention + archival** | Reduces data residue and metadata bloat | Does not replace backup/restart strategy |
| **Idempotent writer + restart tests** | Crash-recovery corruption | Does not prevent unauthorized viewing |
| **Controlled migrations** | Ad-hoc schema edits, metadata corruption | Malicious code running under privileged accounts |

No single setting protects the entire JobRepository. Combine access controls, data minimization, encryption, auditing, backups, and testing.

## 21. Production deployment checklist

- [ ] JobRepository targets the right, consistent database/schema across all relevant instances.
- [ ] Runtime account has no unnecessary DBA/DDL privileges.
- [ ] Dashboard observers read only required fields, preferably via restricted views.
- [ ] All Batch schema migrations run through a controlled pipeline/role.
- [ ] Zero passwords, API tokens, or raw secrets in JobParameters.
- [ ] ExecutionContext stores only minimal state needed for restart.
- [ ] ExitStatus/exception messages and logs contain no sensitive raw payloads.
- [ ] Ops REST/APIs enforce authentication, per-action authorization, and tenant scope.
- [ ] Start/restart/stop operations are audited and rate-limited against abuse.
- [ ] Database traffic, backups, and storage are protected per encryption policies.
- [ ] Credentials come from a secret manager/workload identity with rotation.
- [ ] Retention policy exists without deleting metadata for running or restartable Jobs.
- [ ] Never edit STATUS/ExecutionContext via ad-hoc SQL to patch Job failures.
- [ ] Metrics/alerts track admin actions, DB authorization failures, and repository anomalies.
- [ ] Dev/test environments never share repositories or credentials with production.
- [ ] Integration tests cover DB privileges, data leaks, API auth, restarts, and metadata integrity.

## 22. Safe operational workflow for investigating Batch failures

Suppose an import Job reports **FAILED** after committing several chunks. A controlled workflow:

~~~text
Monitoring detects Job FAILED
             |
             v
Authenticated operator
             |
             v
Read metadata via filtered JobExplorer / dashboard
             |
             +--> View status, counts, execution IDs
             +--> View error code/correlation ID
             +--> Do not view sensitive params/context by default
             |
             v
Investigate authorized logs/audits
             |
             v
Assess root cause and committed data
             |
       +-----+------+
       |            |
   Restart      Remediate
   permitted    per business rules
       |            |
       +-----+------+
             |
             v
Reconcile output, verify zero loss/duplicates
             |
             v
Record remediation outcome + audit trail
~~~

This workflow preserves metadata for investigation, avoids granting ad-hoc database edit privileges, and verifies real data after recovery.

**Protecting the metadata repository** does not merely mean hiding a few BATCH_* tables. It means treating JobRepository as **the core control plane of Spring Batch**, carrying potentially sensitive information and state that directly governs restarts. Combining least privilege, data minimization, endpoint access controls, connection security, retention, and auditing protects information while preserving batch integrity and post-failure recoverability.

