# Database Credentials in Spring Batch: Secure Credential Management

Spring Batch typically relies on a database in at least one of two roles: **`JobRepository`** stores execution history and state, while **readers/writers** read or write business data. To connect, the application may need a username/password, client certificate, short-lived access token, or a cloud-provided workload identity mechanism. If credentials are leaked or granted overly broad privileges, the risk is not just customer data exposure—it can also corrupt checkpoints, tamper with batch metadata, trigger duplicate runs, or disrupt recovery procedures.

**Database credentials** are the information used by the database to authenticate a connection identity. In **Spring Batch Core Processing → Security**, proper credential management means: **keeping secrets out of source code**, **enforcing least privilege**, **delivering secrets to the application through controlled channels**, **protecting connections**, **never writing secrets into logs or metadata**, and **being able to rotate/revoke credentials without losing batch state**.

This lesson uses Spring Batch 5.x, Spring Boot 3.x, and Java 17+ as illustrative context. Exact property names and behavior should match your application's actual configuration; the security principles apply broadly across other versions and databases.

## 1. Which connections does Spring Batch need credentials for?

A batch application may have **one or multiple `DataSource`s**:

~~~mermaid
flowchart TD
    A["Spring Batch Application"] --> B["JobLauncher / JobRepository"]
    A --> C["ItemReader / ItemWriter"]
    B --> D["Batch metadata database\nBATCH_JOB_INSTANCE, BATCH_JOB_EXECUTION, ..."]
    C --> E["Business database\norders, payments, ledger, ..."]
    F["Secret manager / credential provider"] -->|Supply credentials| A
~~~

Two distinct roles:

| Database role | Responsibility | Typically required runtime privileges |
|---|---|---|
| **Batch metadata repository** | Create/query `JobInstance`, `JobExecution`, `StepExecution`, persist `ExecutionContext`, checkpoints, and restart state. | Read/write access to required metadata tables and sequences; by default does not need schema creation/deletion. |
| **Business reader** | Read source or staging data. | `SELECT` on approved tables/views; may not need write privileges. |
| **Business writer** | `INSERT`/`UPDATE`/`DELETE` target data per business logic. | Only authorized operations and target tables. |
| **Migration/administration** | Create tables, indexes, sequences, run schema migrations. | Dedicated DDL privileges, not granted to the daily job runtime account unless needed. |
| **Monitoring/operations** | View batch status via queries or APIs. | Appropriate read access or via a management service; should not automatically have metadata modification privileges. |

A simple application can share one database and account; however, **separating runtime identities** is a blast-radius reduction strategy. Separating multiple `DataSource`s also requires designing the transaction manager and wiring `JobRepository` vs. business data; merely using different usernames in config files does not automatically make two transactions atomic together.

### Avoid confusing two types of data

- `JobRepository` stores batch metadata, **not** a secret store or input payload store.
- `ExecutionContext` stores restart state and may be serialized into the database; it is **not** an appropriate place to store passwords.
- `JobParameters` have identifying and non-identifying parameters, yet **both types can still be persisted into metadata**. The `identifying=false` flag is not a mechanism to hide or encrypt values.
- Readers/writers normally obtain connections from a `DataSource` and pool; credentials belong to **connection configuration**, not per-item or per-request payloads.

## 2. Core principles

| Principle | Practical meaning |
|---|---|
| **No hardcoding** | Never put real usernames/passwords in Java code, committed `application.yml`, test fixtures, or Dockerfiles. |
| **Least privilege** | Accounts may operate only on required schemas/tables; never use a database admin account for jobs. |
| **Environment separation** | Dev, test, staging, and production have separate credentials/resources; never use production secrets in CI. |
| **Lifecycle management** | Credentials have processes for issuance, rotation, revocation, recovery, and expiration checks. |
| **Never log secrets** | Never print credentials, connection strings with passwords, environment dumps, or full app configurations. |
| **Protect connections** | Use TLS and server verification as supported by database/driver; protect both the network and secret storage. |
| **Keep out of batch metadata** | Never pass passwords via `JobParameters`, `ExecutionContext`, or job/step names. |
| **Fail safely** | If a secret is missing or invalid, never silently fall back to a weaker default account. |
| **Controlled auditing** | Record identity access, secret rotation, and connection outcomes without logging secret values. |

No single secret source fits every organization. An application may use a dedicated secret manager, dynamic credentials, workload identity, or secrets injected by the deployment platform. What matters is knowing **who is authorized to read**, **where the secret resides**, **how it is updated**, and **which systems can observe its value**.

## 3. Common anti-patterns

### 3.1. Hardcoding in source code

~~~java
// DO NOT DO THIS: real credentials baked into source code/binary.
var dataSource = new com.zaxxer.hikari.HikariDataSource();
dataSource.setJdbcUrl("jdbc:postgresql://db.internal:5432/payments");
dataSource.setUsername("batch_admin");
dataSource.setPassword("super-secret-password");
~~~

The risk goes beyond the current Git repository. Credentials can linger in commit history, build artifacts, CI caches, pipeline logs, backups, and code reviews. Removing the password line in a new commit **does not make the old secret safe again**; whenever a real secret is exposed, **revoke/rotate** it per procedure.

### 3.2. Putting passwords in JDBC URLs

~~~text
# Unsafe example if the URL is logged or shown in admin tools:
jdbc:postgresql://db.internal:5432/payments?user=batch_user&password=secret
~~~

Some drivers accept credentials in the URL, yet URLs frequently surface in exceptions, config dumps, diagnostics, or monitoring. It is better to keep `jdbcUrl` limited to the endpoint and non-secret connection options, supplying username/password via dedicated `DataSource` properties or a specialized credential provider.

### 3.3. Passing secrets on the command line

~~~bash
# Avoid placing real passwords on the command line:
java -jar app.jar --spring.datasource.password=some-password
~~~

Process arguments can be observed by process inspection tools, ops tooling, or startup logs. Similarly, never echo passwords in scripts, never dump the entire environment during diagnostics, and never let shell debug mode like `set -x` expose commands containing secrets.

### 3.4. Using one high-privilege account for everything

If a runtime account has `DROP TABLE` privileges on metadata, read access to all customer data, and write access to accounting tables, a security breach or writer bug can cause severe damage. Separate privileges by role and workload, and audit what permissions the application actually uses.

### 3.5. Treating `.env` files as completely secure

A `.env` file on a developer machine can be handy locally, **but it is not a secret manager**. It can be copied into images, backups, or accidentally committed. Restrict file permissions, avoid committing it, never share it via chat/support tickets, and prefer infrastructure-managed secret mechanisms in production.

`.gitignore` reduces accidental commits, yet cannot protect secrets already committed earlier, printed to logs, or copied by build tools.

## 4. Configuring Spring Boot DataSource without storing passwords in the repository

For an application with a single `DataSource`, Spring Boot can read datasource properties from external configuration:

~~~yaml
# application.yml: contains only references, no real credentials
spring:
  datasource:
    url: ${DB_JDBC_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 10
  batch:
    jdbc:
      initialize-schema: never
~~~

Spring placeholders `${...}` are resolved from the corresponding environment/configuration source. Real values are injected **at deployment time**, never committed inside config files.

Example variable meanings:

| Variable | Contents | Notes |
|---|---|---|
| `DB_JDBC_URL` | JDBC URL to the authorized database | Do not attach passwords to the query string. |
| `DB_USERNAME` | Runtime principal/role name | Avoid superuser or migration accounts unless required. |
| `DB_PASSWORD` | System-supplied runtime secret | Do not print, do not put in JobParameters. |

`spring.batch.jdbc.initialize-schema=never` is commonly used when the Spring Batch schema has already been initialized by a migration tool or separate deploy account. It **does not automatically create `BATCH_*` tables**. If the schema does not exist yet, the app/job will fail when accessing `JobRepository`; a pre-deployment migration step is required. In local tests, auto-initializing schema can be used deliberately, but do not grant broad DDL privileges to production runtime just for startup convenience.

### Are environment variables secure enough?

Environment variables are convenient and supported by Spring Boot, but they do not make credentials invulnerable:

- Anyone permitted to inspect workload/process configuration can view environment variables on some platforms.
- Crash dumps, diagnostic tools, or scripts can print the entire environment.
- When a secret changes upstream, **a running process does not automatically pick up the new value** if env vars were injected only at startup.
- Secrets can remain in process memory and connection pools.

Therefore, production environments require **workload access controls**, restricted debug/container-exec privileges, safe logging, and an appropriate rotation mechanism.

## 5. Managing secrets with Kubernetes

A common integration pattern injects `DB_USERNAME` and `DB_PASSWORD` from a Kubernetes Secret into the pod:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: settlement-batch
spec:
  replicas: 1
  selector:
    matchLabels:
      app: settlement-batch
  template:
    metadata:
      labels:
        app: settlement-batch
    spec:
      containers:
        - name: app
          image: example/settlement-batch:1.0.0
          env:
            - name: DB_JDBC_URL
              value: jdbc:postgresql://postgres.internal:5432/batchdb
            - name: DB_USERNAME
              valueFrom:
                secretKeyRef:
                  name: batch-db-credentials
                  key: username
            - name: DB_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: batch-db-credentials
                  key: password
~~~

This manifest **illustrates Secret referencing**, not a complete production Kubernetes config. The `batch-db-credentials` Secret must be provisioned through a secure workflow; **never embed real credentials in this YAML or store manifests containing secret values directly in Git**.

Key limitations:

1. Kubernetes Secrets are not end-to-end encrypted secret stores by default simply because values in YAML appear in **Base64**. Base64 is encoding, not encryption.
2. You must govern RBAC, API access, `kubectl exec` permissions, etcd protection, and cluster encryption at rest per requirements.
3. **Container environment variables do not update automatically** when a Kubernetes Secret changes. Typically a pod rollout/restart or an integration with a refresh-capable credential provider is needed.
4. Mounting a Secret as a volume allows Kubernetes to update file contents (with caveats such as `subPath` mounts), **yet `DataSource` does not reload passwords just because a file changed**. The application needs a mechanism to reload and refresh the connection pool.
5. Never grant list/get on all Secrets in a namespace if the pod only needs one specific credential.

If your organization uses an external secret manager or CSI driver, sync/rotation details depend on that integration. Verify **where credentials are actually consumed**—the Spring `DataSource` or driver—not merely that a Secret object updated in the cluster.

## 6. Secret managers and dynamic credentials

A dedicated secret manager can provide versioning, access auditing, rotation, and short-lived credentials. Some platforms also let workloads obtain an identity via a service account or IAM to avoid storing static passwords in app configuration.

~~~mermaid
sequenceDiagram
    participant W as Batch workload
    participant I as Workload identity
    participant S as Secret manager
    participant D as Database
    W->>I: Prove workload identity
    I-->>W: Policy-based access grant
    W->>S: Fetch credential/connection token
    S-->>W: Secret or short-lived token
    W->>D: Connect over TLS and authenticate
    D-->>W: Authenticated connection
~~~

This is a conceptual model. In some environments tokens are issued directly by the provider/driver, while in others a secret manager returns username/password; not every system follows this exact call sequence.

Potential advantages:

- No real secrets inside images or source code.
- Scope can be restricted by application, environment, and database.
- Issuance/reads/revocations are tracked via audit logs.
- Supports rotation/short leases when the database and client support it.

However, dynamic credentials raise questions about **expiration and connection pooling**: when a token/lease expires, existing connections may continue working or be rejected by the database depending on the mechanism; new connections will fail if the pool still uses stale credentials. Design token renewal, new connection creation, and pool replacement safely.

### Do not equate "rotated secret" with "app is using the new secret"

Updating a value in the secret manager **does not prove** every `DataSource` across all pods has adopted the new value. For complete rotation, verify:

1. The new secret is created with appropriate database privileges.
2. The app has a mechanism to receive/refresh the secret in time.
3. The pool can open new connections with the new credential.
4. Running jobs are not disrupted beyond recoverable limits.
5. The old credential is revoked after valid active sessions have transitioned, per security policy.

## 7. Least privilege for JobRepository

Spring Batch metadata lives primarily in `BATCH_`-prefixed tables such as `BATCH_JOB_INSTANCE`, `BATCH_JOB_EXECUTION`, `BATCH_STEP_EXECUTION`, parameter/context tables, and supporting ID sequences/tables.

The `JobRepository` runtime needs read and update permissions on metadata throughout the job lifecycle. `SELECT` alone is insufficient when a job must create a new `JobExecution`, update `BatchStatus`, or save checkpoints.

Conversely, runtime should not automatically be allowed to:

- `DROP TABLE` or alter schemas outside its scope.
- Create users or grant privileges to other users.
- Access business schemas unrelated to JobRepository.
- Modify system data or audit tables it does not require.

### PostgreSQL privilege example

Suppose metadata is placed in a dedicated schema `batch_meta`, already initialized by a migration account:

~~~sql
-- Executed by a privileged granting account (not batch_runtime).
GRANT USAGE ON SCHEMA batch_meta TO batch_runtime;

GRANT SELECT, INSERT, UPDATE, DELETE
ON ALL TABLES IN SCHEMA batch_meta
TO batch_runtime;

GRANT USAGE, SELECT
ON ALL SEQUENCES IN SCHEMA batch_meta
TO batch_runtime;
~~~

This is an **example of minimal privileges at the current metadata schema level**, not a complete script for every organizational model. Some apps do not need `DELETE` on every table at runtime; tailor grants to actual `JobRepository`/`JobOperator`/cleanup usage. Future tables after migrations also involve `ALTER DEFAULT PRIVILEGES` set by the schema/table owner; `GRANT ON ALL TABLES` covers only tables existing at grant time.

If the same role is also used by a business writer, metadata and business privileges are combined—a trade-off worth documenting. For sensitive systems, separate roles/`DataSource`s can shrink the blast radius while requiring transaction orchestration review when metadata and outputs live in separate DBs.

### Separating runtime and migration

| Identity | Responsibility | Privileges |
|---|---|---|
| `batch_migrator` | Run Flyway/Liquibase or schema creation/update scripts | Controlled DDL, used during deployment. |
| `batch_repository_runtime` | Read/write execution metadata | Required DML on `BATCH_*` and related sequences. |
| `payment_reader` | Read source data | `SELECT` on authorized tables/views. |
| `payment_writer` | Write business results | Required DML on specific target tables. |
| `batch_observer` | Query authorized status | Read-only metadata, or via role-protected ops API. |

This separation ensures one compromised credential cannot automatically alter unrelated tables. However, it increases the number of secrets and configs to manage; maintain rotation, inventory, and monitoring procedures for each identity.

## 8. One DataSource or multiple DataSources?

### Single DataSource for both metadata and business data

Pros: simple setup, single pool, and the transaction manager can participate in the same database when all components use the proper connection and transaction.

Cons: the runtime role typically needs privileges on both metadata and business tables. A bug or compromised credential has a wider blast radius. Within a single database, you can still restrict by schema and table, though privileges cannot be fully isolated with only one principal.

### Separating metadata DataSource and business DataSource

~~~text
                  Spring Batch
                      |
          +-----------+-----------+
          |                       |
  batchMetadataDataSource  businessDataSource
  credential: batch_role   credential: writer_role
          |                       |
     BATCH_* tables         payment_output
~~~

Pros: clear per-role privileges, easier independent rotation and auditing. Cons: requires explicit bean routing; transactions across two datasources do not automatically form one shared ACID transaction.

In Spring Boot/Spring Batch, when manually configuring multiple datasources, you must explicitly specify **which datasource/transaction manager `JobRepository` uses** and **which transaction manager `StepBuilder.chunk(..., transactionManager)` uses**. Mechanisms like `@BatchDataSource` or `@EnableBatchProcessing` with datasource/transaction manager references apply depending on your Boot version/config; never assume marking one bean `@Primary` automatically wires everything properly.

Example of deliberate step configuration:

~~~java
@Bean
Step writePaymentsStep(
        JobRepository jobRepository,
        @Qualifier("businessTransactionManager")
        PlatformTransactionManager businessTransactionManager,
        ItemReader<PaymentRow> reader,
        ItemWriter<PaymentRow> writer) {

    return new StepBuilder("writePaymentsStep", jobRepository)
        .<PaymentRow, PaymentRow>chunk(100, businessTransactionManager)
        .reader(reader)
        .writer(writer)
        .build();
}
~~~

This snippet assumes the beans already exist. Ensure the writer uses the `businessDataSource` managed by `businessTransactionManager`. If `JobRepository` is stored in a separate database, metadata/checkpoint commit timing may not be atomic with business data commits; design idempotency, business keys, and reconciliation for clean crash recovery.

**Separating credentials is a security decision; guaranteeing transactions is a data-consistency decision.** Both must be evaluated together in Spring Batch.

## 9. Protecting the database connection channel

Credentials stored safely in a secret manager can still be exposed if the database connection is unprotected or if the app accepts an imposter server.

A PostgreSQL JDBC configuration can enforce TLS verification:

~~~text
jdbc:postgresql://postgres.internal:5432/batchdb?sslmode=verify-full
~~~

With PostgreSQL JDBC, `verify-full` requires verifying both the certificate and hostname against an appropriate trust configuration. You must deploy a trusted CA/root certificate/trust store and ensure DNS names match the certificate. Enabling encryption without server identity checks (such as "encrypt without verification" modes) may not prevent connecting to a spoofed endpoint.

Protection layers to evaluate:

- TLS between workload and database, including proper certificate verification.
- Network policies/firewalls/security groups: allow connections only from required sources.
- DB listens only on required endpoints, not exposed on public management interfaces.
- Client authentication per provider capability: certificates, tokens, or IAM identity.
- Read permissions on private keys and truststore files; avoid baking private keys into public images.
- Certificate/CA renewal procedures and expiration tracking.
- Connection pool limits, timeouts, and failed-login controls to contain incident impact.

TLS and secret storage solve two distinct problems: **where secrets are stored** and **whether the transport to the database is authenticated/encrypted**.

## 10. Credential rotation during multi-hour jobs

A job might start at 23:00 and still be running when a password or token rotates at 00:00. At that moment `HikariCP` or an equivalent pool may hold connections authenticated with the old credential.

~~~text
T0:  Secret V1, connection pool opens connections
T1:  Job reads/writes multiple chunks, reusing some connections
T2:  Secret manager/DB switches to V2
T3:  Pool attempts to open new connections
T4:  Connections using V1 may be rejected depending on DB policy
T5:  Step throws connection / authentication errors
~~~

Some databases allow existing connections to continue until closed even after password changes; others revoke active sessions/tokens. Never assume uniform behavior across all drivers and credential providers.

### System-level safe rotation process

1. **Provision credential V2.** Ensure the new user/role has the exact required privileges before switching the app.
2. **Distribute via a supported mechanism.** Secret manager, workload identity, or config rollout; never paste secrets in logs/chat.
3. **Switch new connections to V2.** The app or pool must actually ingest the new secret; changing an external env var alone is insufficient.
4. **Verify connectivity.** Monitor authentication failures, pool acquisition timeouts, and JobRepository/step status.
5. **Drain old connections.** Recreating the datasource/pool or rolling pods may be necessary depending on the driver and job characteristics.
6. **Revoke V1.** Once all valid workloads have transitioned, revoke the old credential per policy.
7. **Verify batch recovery.** If a step failed mid-transition, use `JobRepository` and checkpoints to restart the exact JobInstance.

Do not just tweak `spring.datasource.hikari.max-lifetime` and consider rotation solved: connection lifetime settings **do not supply fresh credentials** to the pool. If a provider refreshes credentials dynamically, integrate it cleanly into connection creation. If secrets come from pod env vars, a planned rollout/restart is usually required.

### Rotation and Spring Batch restart

Credential rotation **is not a business JobParameter**. Never add passwords or secret versions to identifying `JobParameters` to spawn a new JobInstance per rotation.

If a job `FAILED` due to credential expiration:

- Fix authentication and verify connectivity to metadata/business DBs.
- Keep the identifying parameters of the `JobInstance` to be recovered unchanged.
- Inspect which chunks already committed and what metadata/checkpoints remain.
- Restart when state permits; verify writer idempotency if replay occurs.
- Never truncate `BATCH_*` tables or generate a random `run.id` to bypass repository errors, as that creates a new job instance and risks duplicate writes.

## 11. Authentication errors in reader/writer vs. JobRepository

All of them may look like "database login failed," yet the failure point directly shapes recovery:

| Failure point | Typical symptom | Handling approach |
|---|---|---|
| **Startup / DataSource** | App fails to build pool/beans due to missing secret or DB rejecting credentials. | Verify secret source, URL, role, and TLS; never use unsafe fallbacks. |
| **JobRepository before launch** | Cannot create `JobExecution`; may have no new execution ID. | Fix metadata connection; check existing status before client retries with the same business key. |
| **ItemReader** | Step fails to read source data, potentially failing mid-job. | Check read role, connectivity, and checkpoint state. |
| **ItemWriter** | Chunk rolls back or commit outcome is uncertain. | Check write privileges, connectivity, committed data, and idempotency. |
| **During transaction commit** | Writer may have executed without receiving commit confirmation. | Do not assume rollback succeeded; reconcile against target DB. |
| **After rotation** | Old connections work, new connections report auth failures. | Check pool/provider refresh and old credential revocation timing. |
| **After schema migration** | Runtime role lacks privileges on new tables/sequences. | Update grants systematically in migrations. |

An error that looks credential-related may actually be caused by hostname, DNS, firewall, TLS certificates, pool exhaustion, or an unavailable database. Diagnose the root cause rather than rotating passwords blindly on every connection exception.

### Retrying does not fix a wrong password

~~~java
// Anti-pattern: retrying all connection exceptions indiscriminately.
.faultTolerant()
.retry(Exception.class)
.retryLimit(100)
~~~

Wrong username/password or missing `GRANT` privileges are configuration/authorization errors that will not vanish after 100 retries. Tight retries also add load and can trigger account lockout policies. For transient network errors, bounded retries with backoff can help; for authentication failures, fail fast and fix the configuration/secret.

In some systems, failures from an expired short-lived credential can recover once a new token is issued, yet the retry policy must account for **secret refresh mechanics and pool lifecycle**. Blindly retrying on the same stale credential is not a rotation strategy.

## 12. Logging, tracing, and metadata must never contain secrets

One of the most common ways database credentials leak is "debugging a connection" by printing the whole config:

~~~java
// DO NOT DO THIS:
log.info("DataSource properties: {}", fullDataSourceProperties);
log.debug("Database password: {}", password);
log.info("Environment: {}", System.getenv());
~~~

Replace with a structured event **containing no credentials**:

~~~java
log.warn(
    "batch.database.connection.failed component={} category={} jobExecutionId={}",
    "BUSINESS_WRITER",
    "AUTHENTICATION",
    jobExecutionId
);
~~~

`jobExecutionId` may not exist yet if the failure happens before JobRepository creates the execution. At that stage, use a `correlationId`/launch attempt ID generated by the caller or scheduler, and attach the execution ID once created.

### Do not log raw JDBC URLs arbitrarily

JDBC URLs can contain sensitive query strings or user info. To log an endpoint for diagnostics, use a **configured alias** such as `batch-metadata-primary` or `payments-reader` instead of raw `dataSource.getJdbcUrl()`.

Exceptions can also include hostnames, usernames, SQL, or input data; never assume every `Throwable.getMessage()` is safe for centralized logs. Use standardized error codes and keep stack traces in restricted diagnostic channels after reviewing what they emit.

### Protect surfaces beyond loggers

Leaks can also happen through:

- Actuator/configuration endpoints or custom debug endpoints if misconfigured to expose sensitive values.
- Tracing span attributes, monitoring tags, or error reporting SDKs.
- Startup banners/diagnostics and error messages containing JDBC URLs.
- CI build logs, test reports, or deployment script outputs.
- Heap dumps, core dumps, support bundles, and process snapshots.
- `JobParameters`/`ExecutionContext` serialized into `JobRepository`.
- Command history or process arguments.

A secure setup aligns **source code, runtime platform, observability, and access controls**, rather than relying solely on `@JsonIgnore` or a logger password regex.

## 13. Credentials must not travel per item or in JobParameters

A common flawed design:

~~~java
// Do not do this: the secret may be persisted in BATCH metadata.
JobParameters params = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .addString("dbPassword", password, false)
    .toJobParameters();
~~~

Marking `dbPassword` non-identifying **does not remove it** from job history. When credentials need changing, let the `DataSource`/credential provider handle it instead of recreating JobInstances or passing passwords through the workflow.

Likewise:

~~~java
// Do not put credentials into checkpoints:
stepExecution.getExecutionContext().put("password", password);
~~~

`ExecutionContext` is typically persisted for restart; anyone with metadata or backup access can read this data. If a writer needs to access an external database, inject a secured `DataSource`/service via dependency injection, or call a credential provider using workload identity where needed.

If a job reads data across multiple tenants, **never place all per-tenant credentials in JobParameters**. Use an authenticated `tenantId`/`connectionAlias` mapped server-side to an authorized datasource/provider. Tenant authorization must be enforced; a caller-supplied alias must never self-authorize reading arbitrary databases.

## 14. Relationship between credentials, connection pools, and transactions

In Spring Batch, each chunk normally defines a transaction boundary. A JDBC writer borrows a connection from the pool managed by the configured transaction manager. Consequences:

1. **Successful connection authentication does not mean transactions are wired correctly.** The writer must participate in the right `DataSource`/`PlatformTransactionManager`.
2. **Pools reuse connections.** Credentials may be checked only when opening a connection; rotation does not automatically swap active connections.
3. **Pools are bounded.** When too many partitions/jobs run concurrently, pool exhaustion can be mistaken for a credential failure if you only look at a generic exception.
4. **Database authorization is separate from authentication.** Valid username/password without `INSERT` privilege on the target table still fails.
5. **Connections can change between transactions.** A long-running job may fail mid-run if new connections fail auth after rotation.
6. **Metadata and business logic may use separate pools.** One pool failing does not immediately break the other, yet the job can fail and require state reconciliation.

With HikariCP, settings like `maximumPoolSize`, `connectionTimeout`, `idleTimeout`, and `maxLifetime` govern pool operations; do not treat them as substitutes for secret rotation and least privilege. Some setups support controlled pool refresh/connection eviction; exact usage depends on your HikariCP/credential provider integration.

### Using the wrong transaction manager

Suppose metadata resides in database A and the writer targets database B. If the step is accidentally wired with A's transaction manager, writer updates in B may not participate in the transaction the developer expects.

When a chunk fails, the repository may record metadata rollback in A while writer B already committed partial changes if it opened connections outside the transaction. Upon restart, data may be replayed and duplicated.

**To avoid this:** explicitly align datasources/transaction managers for readers/writers, design unique business keys/idempotency, and include post-failure reconciliation. Strong credential security alone cannot fix transactional mismatches across resources.

## 15. CI/CD and test environments

Never use production credentials in integration tests or CI migrations. Good strategy:

- Unit-test reader/processor logic without a real database whenever unnecessary.
- Integration-test using a dedicated test database or Testcontainers with ephemeral credentials and synthetic data.
- CI fetches needed secrets from the runner's secret store with narrow scope/retention—never committed in the repo.
- Deployment migration accounts run only during deployment; runtime service accounts carry different privileges.
- Test logs must not print passwords, environment dumps, or connection URLs containing credentials.

### Testcontainers example: credentials scoped strictly to the test

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class BatchDatabaseIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("batch_test")
            .withUsername("test_batch_user")
            .withPassword("test_only_password");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Test
    void contextStartsWithTestDatabase() {
        // Application-specific: verify JobRepository/DataSource beans
        // and run a safe query against the initialized test schema.
    }
}
~~~

`test_only_password` is a **dummy credential solely for an isolated test container**, not a pattern for placing production passwords in source code. For Testcontainers tests, ensure the batch schema is properly initialized (via migrations or test setup). `spring.batch.jdbc.initialize-schema` can also control this; do not assume the schema exists simply because the container started.

When multiple tests share the Spring TestContext cache while a container has a shorter lifecycle than the context, the datasource may point to a stopped container. Align Testcontainers lifecycle and context caching consistently so tests never accidentally reuse stale/expired secrets or databases.

### Assertions worth having

| Scenario | Expected test result |
|---|---|
| Missing `DB_PASSWORD` when auth is required | Startup/connection fails clearly; no fallback to hardcoded credentials. |
| Valid secret, minimal privileges | JobRepository creates execution and writer inserts into authorized table. |
| Reader with `SELECT` only | Cannot write or modify source tables out of scope. |
| Runtime without DDL | Job runs on pre-migrated schema; cannot arbitrarily `DROP/ALTER` tables. |
| Rotation to new credential | New connections use V2; no identifying JobParameters changes needed. |
| Old credential revoked | New connections with V1 are rejected per policy, errors classified safely. |
| Password placed in dummy test config | Never appears in logs, traces, JobParameters, or ExecutionContext. |
| Writer loses connection mid-chunk | Verify rollback, restart, and zero duplicate output data. |
| JobRepository unreachable | Does not spawn another run with a random key to bypass the error. |

To verify logs, you can inject a *canary* value such as `DO_NOT_LOG_TEST_SECRET` into the test environment and capture output from the relevant logger/sink. Tests must never use real credentials and should not claim full security solely by scanning a single log file, since secrets can travel through other observability channels.

## 16. Credential incident response procedure

When a job fails due to authentication/authorization, operations should follow real signals rather than printing full secrets to diagnose:

1. **Locate the failure point.** Startup, JobRepository, reader, writer, commit, or connection pool? Do `jobExecutionId`/`stepExecutionId` exist yet?
2. **Classify the issue.** Authentication (wrong principal/secret), authorization (missing GRANT), TLS/certificate, network/DNS, database outage, or pool exhaustion.
3. **Verify the secret source.** Is the workload bound to the right Secret/role/identity and expected secret version? Inspect only version metadata and status, never display values.
4. **Check database privileges.** Does the runtime role have needed rights on tables/schemas/sequences? Did a recent migration create ungranted objects?
5. **Assess rotation.** Did the secret store update while the process/pool still holds V1? Are any existing connections still working while new pool connections fail?
6. **Remediate safely.** Fix config/permissions, roll out, or refresh credentials through supported mechanisms. Avoid escalating to superuser as a quick fix.
7. **Recover the batch.** Preserve metadata, verify committed chunks and external side effects; restart the same JobInstance if allowed and verify idempotency.
8. **Reconcile and close.** Verify record counts, business keys, and writer output; audit secret issuance/revocation per policy.

### When credential exposure is suspected

This is a **security incident**, not merely a batch runtime error:

- Restrict/revoke the suspected exposed credential per incident response policy; do not try to "fix" it by deleting log history.
- Issue a new credential with minimal scope, update workloads, and revoke the old credential appropriately.
- Audit access scopes and logs on the database and secret manager, including connections outside normal job schedules.
- If the credential lived in repositories, CI logs, images, or support bundles, assess all copies and retention windows; removing it from one current file is insufficient.
- For running jobs, assess the impact of immediate revocation on transactions, checkpoints, and outputs; follow organization-approved security response procedures.

Never let the convenience of an active job keep a potentially compromised credential alive indefinitely. Revocation timing balances incident response policy with data recovery needs.

## 17. Common mistakes

### "The password is in application.yml, but the repo is private so it's safe"

Private repos still have many authorized readers, commit history, CI copies, and build artifacts. Never treat a repo as a secret store. Once a secret is committed, rotate it and audit history.

### "Using Kubernetes Secrets means encryption and RBAC aren't needed"

Base64-encoded secrets are not encrypted. Cluster access policies, encryption at rest per environment, and strict limits on who/what can read secrets are still mandatory.

### "Changing a Secret value makes HikariCP automatically use the new password"

Not necessarily. Environment variables do not update automatically inside running processes, and datasources/pools do not automatically reload every config source. A refresh mechanism or rollout is required.

### "Granting superuser is the fastest fix for repository errors"

This needlessly expands risk. If a job needs a new table/sequence, grant privileges on that exact object or fix migrations/grants; never make an admin account the runtime default.

### "Sharing the same credential for read and write databases is easier to manage"

It lowers secret count while increasing blast radius. When business requirements allow, separate read/write and metadata privileges; if sharing is unavoidable, scope exact privileges rather than skipping review.

### "Non-identifying JobParameters aren't persisted"

False. Non-identifying affects only JobInstance identity; passwords still enter the parameters table. Never pass credentials via `JobParameters` or `ExecutionContext`.

### "Enabling SSL is enough, no need to verify certificates"

TLS without server identity verification may fail to prevent endpoint spoofing. Configure trust and hostname verification suited to your database/driver.

### "Authentication failures just need more retries"

Wrong passwords or missing privileges do not heal themselves. Unbounded retries add load and mask root causes; fix the secret, role, or refresh mechanism before recovering the job.

### "Rotating a database password requires rerunning with a new run.id"

Credentials are infrastructure authentication, not business job identity. When a job fails, restart the same JobInstance with intact metadata; creating a new instance can duplicate already-committed data.

### "Masking passwords in logs protects the entire secret"

Credentials can also live in process arguments, environment variables, crash dumps, support bundles, URLs, trace attributes, backups, or app-persisted metadata. Protect the whole lifecycle, not just one logger.

## 18. Designing database credentials for Spring Batch

When building a new batch system, follow these steps:

1. **Inventory all database connection paths.** Identify which datasources are used by `JobRepository`, readers, writers, staging, auditing, and migrations.
2. **Design least-privilege roles.** Grant DML on exact tables/sequences; separate DDL migrations; never give runtime superuser access.
3. **Choose secret sources.** Secret manager, workload identity, or platform secret integration; keep real passwords out of source/images.
4. **Configure externalized properties.** Use `${DB_USERNAME}`/`${DB_PASSWORD}` or an appropriate provider; keep passwords out of JDBC URLs and JobParameters.
5. **Secure network and TLS.** Verify certificates/hostnames; restrict reachable endpoints and allowed client sources.
6. **Align datasources and transaction managers.** Ensure readers/writers participate in transactions as designed; evaluate risks when metadata and business data live in separate DBs.
7. **Design rotation and recovery.** How are secrets updated? When do pools refresh? How do active jobs fail and restart safely?
8. **Prevent observability leaks.** Log error codes, job/step IDs, and connection aliases; never print secrets, full configs, env vars, or raw JDBC URLs.
9. **Test with isolated credentials.** Test privileges, auth failures, rotation, schema migrations, and chunk recovery against test databases/fixtures.
10. **Maintain an incident runbook.** Audit secret access, revoke exposed credentials, and reconcile data after failures.

## Conclusion

In Spring Batch, **database credentials** are far more than `username` and `password` properties. Credentials govern access to **restart metadata** and **business data**, so they must be managed end-to-end from provisioning, `DataSource` loading, connection authentication, and pooling through rotation or revocation.

A secure design keeps secrets **out of source code and batch metadata**, enforces **least privilege**, secures connections with **TLS and server verification**, separates runtime vs. migration roles, implements rotation that truly updates pools, and treats authentication failures as infrastructure events impacting transactions and checkpoints. When these layers operate together, batch systems protect data while preserving consistent post-failure recovery.
