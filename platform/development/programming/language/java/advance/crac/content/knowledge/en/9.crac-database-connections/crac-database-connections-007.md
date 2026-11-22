# Avoiding Unintended Re-execution of Schema Changes and Data Initialization

When using CRaC (Coordinated Restore at Checkpoint), a Java application can be restored from a checkpoint image without having to start the JVM and application context from scratch. Objects in the heap are restored, execution threads continue from the saved state, and afterRestore callbacks are invoked to recreate necessary resources.

A database has its own lifecycle. The database server and its data usually reside outside the Java process, so a checkpoint image is not a copy of the database. During the time the application is in the checkpointed state, the database can still continue operating, the schema can be migrated, and data can change.

Therefore, it is necessary to clearly distinguish database initialization tasks from connection recovery tasks after restore. Schema migration and data seeding should have their own control mechanisms, be safe to run repeatedly when needed, and not be unintentionally invoked again in recovery callbacks.

## 1. Why does CRaC need to pay attention to migration and initialization?

A Java application typically has database steps at startup:

- Creating or checking the schema.
- Running migrations to upgrade the database version.
- Creating tables, indexes, constraints, sequences, or views.
- Loading reference data such as catalogs, status types, or default configurations.
- Creating an initial administrator account.
- Checking permissions and database connectivity.
- Initializing the connection pool and repositories.

In a normal startup, these steps may be performed by Spring Boot, Flyway, Liquibase, Hibernate, or custom bootstrap code.

With CRaC, if the checkpoint is taken after the application completes startup, the image may already contain the Java state of those components. Upon restore, the process continues from the image. **CRaC restore does not automatically re-run main(), does not automatically recreate the application context, and does not automatically re-run all startup hooks like a fresh JVM startup.**

However, the application can still accidentally re-run initialization if:

- Code after the Core.checkpointRestore() call invokes the bootstrap function again.
- The afterRestore callback calls an overall initialization method that includes both migration and seeding.
- A framework or library is configured to run initialization when the connection pool is recreated.
- A background task is restarted and runs the initialization script on its own.
- A controller restores multiple replicas from the same image, and each replica executes migration logic after restore.
- The deployment process creates a new process instead of restoring an image but shares the same startup script.

It is necessary to clearly identify which code actually runs on restore and which code only runs during a fresh startup. This helps avoid running DDL, seeding, or side effects multiple times.

## 2. Distinguishing migration, validation, seeding, and reconnection

These four tasks have different purposes and lifecycles.

| Task | Purpose | Typically appropriate timing |
|---|---|---|
| Schema migration | Change database structure by version | Controlled startup or a separate migration job before the application receives traffic |
| Schema validation | Confirm the current schema is compatible with the application | Startup or a verification step after reconnecting |
| Data initialization / seed | Load initial data or reference data | Migration or controlled bootstrap, using idempotent operations |
| Connection recovery | Create new connections/sessions to the database | afterRestore or a dedicated lifecycle hook of the connection pool |

Do not bundle all four tasks into a generic function like initializeDatabase() and call that function from afterRestore. Such a function might simultaneously open connections, run migrations, insert default data, and create accounts.

Separate them into components with clear responsibilities:

- Migration runner manages schema versions.
- Seed runner manages reference data and bootstrap data.
- Schema validator checks compatibility.
- Connection manager manages the pool and sessions.
- CRaC Resource manages stopping and recovering process-owned resources.

A typical afterRestore callback only needs to recreate the connection pool, verify connectivity, and update readiness. It should not re-run all migrations or seeding.

## 3. Restore continues from checkpoint, not a fresh startup

This is the most important distinction when designing database initialization logic.

Suppose the application startup has the sequence:

~~~text
JVM start
  -> Load configuration
  -> Create application context
  -> Run database migrations
  -> Seed reference data
  -> Create connection pool
  -> Warm-up services
  -> Application ready
  -> Create CRaC checkpoint
~~~

When restoring the image:

~~~text
Restore JVM process
  -> Restore heap and execution state
  -> Run afterRestore callbacks
  -> Reconnect database resources
  -> Resume execution after checkpoint
~~~

The migration and seeding steps located before the checkpoint have already completed in the saved state. They do not automatically run again just because the process is restored.

This can be visualized with a diagram:

~~~mermaid
flowchart TD
    A["Fresh JVM startup"] --> B["Create application context"]
    B --> C["Run schema migration"]
    C --> D["Initialize seed data"]
    D --> E["Create database pool"]
    E --> F["Warm-up and validate"]
    F --> G["Checkpoint"]
    G --> H["Restore image"]
    H --> I["afterRestore: reconnect pool"]
    I --> J["Resume application"]
    J --> K["Serve requests"]
    style C fill:#dbeafe,stroke:#2563eb,color:#1e3a8a
    style D fill:#dbeafe,stroke:#2563eb,color:#1e3a8a
    style I fill:#dcfce7,stroke:#16a34a,color:#14532d
~~~

This diagram illustrates the ideal case: migration and seeding complete before the checkpoint; the restore callback only recovers connection resources.

If code after the checkpoint calls the migration runner again, or the afterRestore callback calls bootstrap again, those operations will run because the application requests them, not because CRaC automatically restarts the application.

### 3.1 Case of calling Core.checkpointRestore()

When the application calls Core.checkpointRestore(), execution continues after the call in the restored process if the checkpoint and restore succeed. For example:

~~~java
runDatabaseMigrations();
initializeReferenceData();

Core.checkpointRestore();

// This line continues running in the restored process.
startServing();
~~~

The runDatabaseMigrations() and initializeReferenceData() calls are located before the checkpoint, so they are not automatically executed a second time when the call returns after restore.

However, if written as:

~~~java
Core.checkpointRestore();

runDatabaseMigrations();
initializeReferenceData();
startServing();
~~~

then migration and seeding will run after restore because they are located after the call. If multiple instances restore from this image, multiple processes may run that logic concurrently. Therefore, the position of the checkpoint in the startup flow is very important.

When a checkpoint is triggered externally, the application also continues from the saved thread state. There is no new main() call just because a controller sends a restore request.

## 4. Managing schema migrations with versioned migrations

Schema changes should be managed with versioned migrations. Each migration describes a specific change and is recorded after successful execution.

For example:

~~~text
db/migration/
  V001__create_customer_table.sql
  V002__add_customer_status.sql
  V003__create_order_index.sql
  V004__add_reference_country.sql
~~~

A migration tool records applied migrations in the database. When run again, the tool compares the current state with the list of migrations and only executes changes that have not been applied, according to the tool's rules.

This helps distinguish:

- Migrations that have not run yet.
- Migrations that have run successfully.
- Migrations whose checksum or content changed.
- Failed migrations or a database in a state requiring intervention.

Do not infer schema state solely from whether a table already exists. A table may exist but be missing columns, indexes, constraints, or have a structure different from the expected version.

### 4.1 Flyway

Flyway manages migration history in a schema history table, usually **flyway_schema_history**. This table stores the version, description, script, checksum, and migration status.

Usage example:

~~~java
Flyway flyway = Flyway.configure()
        .dataSource(dataSource)
        .locations("classpath:db/migration")
        .load();

flyway.migrate();
~~~

The migrate command applies missing migrations according to Flyway's configuration and history. Calling migrate multiple times does not mean all old scripts are re-run; the tool relies on schema history to determine the remaining work.

Even so, avoid calling migrate unnecessarily in afterRestore. When multiple instances restore simultaneously, they may all try to check or apply migrations at the same time, adding contention and making recovery time unpredictable.

Useful operations:

- migrate(): applies migrations that have not run.
- validate(): validates migration history and checksums against configuration.
- info(): views migration status.
- repair(): fixes history metadata in defined situations; not a general-purpose schema repair tool.

If a migration script has already been applied but the script file is later modified, validation may detect a checksum mismatch. Do not modify old released migrations to change the schema in existing environments; create a new migration instead.

### 4.2 Liquibase

Liquibase records executed changeSets in the **DATABASECHANGELOG** table. It uses the **DATABASECHANGELOGLOCK** table to coordinate having one process execute the changelog at a time.

A changeSet is identified by id, author, and file path. When running update, Liquibase compares the changelog with database history to decide which changeSets need to be executed.

Pay attention to attributes that can cause a changeSet to run again:

- runAlways causes the changeSet to be executed on every update.
- runOnChange allows re-execution when the changeSet's checksum changes.
- preConditions specify conditions before running.
- onFail and onError determine how to handle errors when conditions or operations fail.

These attributes are useful in some situations, but if used unintentionally, they can cause scripts to be re-run on every startup or every time an instance restores and calls update.

Only use runAlways or runOnChange when the logic is genuinely designed for repeated execution and its side effects are controlled.

### 4.3 Do not manage migrations solely with CREATE TABLE IF NOT EXISTS statements

A statement like:

~~~sql
CREATE TABLE IF NOT EXISTS customer (
    id BIGINT PRIMARY KEY,
    name VARCHAR(200) NOT NULL
);
~~~

can avoid errors when the table already exists, but does not prove the existing table has the required structure. If the table already exists but is missing columns, has wrong data types, or is missing constraints, the statement above can still complete normally.

Similarly, checking if a table exists and then skipping all migrations will make schema drift hard to detect.

Use migration history to manage versioned changes; use schema validation to check the actual structure.

## 5. Ensuring migrations only run in one place

In a system with multiple replicas, if every instance runs migrations on startup, multiple processes may check or modify the schema at the same time.

Migration tools usually have locking or history-checking mechanisms, but a clear deployment policy is still needed. There are two common approaches.

### 5.1 Dedicated migration job

A job or deployment step runs migrations before rolling out the new application version:

~~~text
Build artifact
  -> Start migration job
  -> Acquire database migration lock
  -> Apply pending migrations
  -> Validate schema
  -> Mark migration job successful
  -> Roll out application instances
  -> Create checkpoint after warm-up
~~~

Advantages:

- Only one component is responsible for changing the schema.
- Application instances do not have to perform DDL concurrently.
- Separate database permissions can be granted to the migration job.
- Easy to control timing, logs, and rollback/forward-fix.
- Restoring multiple replicas from a checkpoint image does not trigger a new migration job.

The application runtime may only need read/write permissions for business data, while the migration job has DDL permissions.

### 5.2 Migration at startup with locking

Some smaller systems choose to let the application run migrations at startup. If using this approach:

- The migration tool must have a locking mechanism suitable for the database.
- Each instance must wait for migrations to complete before readiness is enabled.
- Migrations must be compatible with the running application version.
- The number of instances starting simultaneously should be controlled.
- Do not call the migration runner again in afterRestore.
- Do not allow multiple application versions to compete to change the schema outside the plan.

A migration tool's lock mechanism does not replace rollout planning. A migration can be serialized and still break the old application version if it drops columns or changes semantics too early.

### 5.3 Do not use synchronized in the JVM as a migration lock

A static synchronized method only synchronizes threads within the same classloader/process. It does not protect the database when multiple JVMs, pods, or hosts run migrations concurrently.

Use a database lock, migration tool lock, or appropriate distributed coordination. The lock must be managed across the scope of all instances that can access the database.

## 6. Data initialization: seeds must be safe when run repeatedly

Seed data is data created initially for the application to operate, for example:

- Lists of countries, currencies, or time zones.
- Order status types.
- Default permissions and system roles.
- Default configurations.
- Initial administrator account.

Not all initial data has the same semantics. Reference data that rarely changes can be managed as part of migrations. User data, orders, or business state should not be reset by a startup script.

### 6.1 Uncontrolled INSERT can create duplicate data

For example:

~~~sql
INSERT INTO order_status(code, label)
VALUES ('PENDING', 'Pending');
~~~

If the statement is run on every bootstrap, it can:

- Raise a duplicate key error.
- Create duplicate records if there is no unique constraint.
- Cause the migration to fail.
- Prevent startup or restore from completing.

Identify a unique key with business meaning, such as code, and place a unique constraint in the database. Do not only check beforehand with a SELECT in Java because two instances can both read that it does not exist yet and then both INSERT.

### 6.2 Idempotent seeding with a unique key

With PostgreSQL, you can use INSERT ... ON CONFLICT:

~~~sql
INSERT INTO order_status(code, label)
VALUES
    ('PENDING', 'Pending'),
    ('PAID', 'Paid'),
    ('CANCELLED', 'Cancelled')
ON CONFLICT (code) DO NOTHING;
~~~

The unique constraint on code ensures that repeated runs do not create duplicate records. If the data already exists, the statement skips that record.

If the seed needs to update system-owned columns, you can use DO UPDATE:

~~~sql
INSERT INTO order_status(code, label)
VALUES ('PENDING', 'Pending')
ON CONFLICT (code)
DO UPDATE SET label = EXCLUDED.label;
~~~

Only update columns that the seed is authorized to manage. If operators or users are allowed to edit label, an upsert that overwrites on every startup can lose valid changes.

Upsert syntax differs across PostgreSQL, MySQL, SQL Server, and Oracle. Use the syntax and semantics of the actual database.

### 6.3 Distinguishing reference data and mutable data

| Data type | Examples | Appropriate management approach |
|---|---|---|
| Application-owned reference data | Status codes, currency types | Versioned migration or idempotent seed |
| Default configuration | Default thresholds, default features | Insert if not present; avoid overwriting values customized by operations |
| Bootstrap identity | First administrator account | Create once in a controlled manner, using unique identity and security procedures |
| User data | User profiles | Do not re-seed or reset during restore |
| Business data | Orders, transactions, history | Managed by business logic and transactions |
| Runtime cache | Rebuildable cache | Recreated according to lifecycle, not treated as database seed |

A seed script should clearly know which data it owns. Do not use a broad UPDATE statement to reset an entire table to default values on every startup.

## 7. Do not re-run DDL or seeding in afterRestore

afterRestore is used to recover process resources. For a database, the tasks are typically:

1. Recreate the DataSource or connection pool if the old pool was closed before checkpoint.
2. Check connectivity.
3. Verify the database user and required permissions.
4. Check that the schema version is compatible with the application.
5. Restore consumers, schedulers, or operations that depend on the database.
6. Enable readiness after essential dependencies are ready.

Example of a Resource that only manages the pool:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class DatabasePoolResource implements Resource {

    private final DatabasePoolFactory poolFactory;
    private DatabasePool pool;

    public DatabasePoolResource(DatabasePoolFactory poolFactory) {
        this.poolFactory = poolFactory;
        Core.getGlobalContext().register(this);
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        if (pool != null) {
            pool.close();
            pool = null;
        }
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        DatabasePool reopened = poolFactory.create();
        reopened.validateConnection();
        pool = reopened;
    }
}
~~~

DatabasePool and DatabasePoolFactory in the example are application abstractions. They can be replaced with HikariDataSource or the pool used by the framework.

The callback does not call flyway.migrate(), liquibase.update(), or seed functions. It only recreates connection resources. If schema validation is a required part of readiness, a read-only check operation can be called with appropriate timeouts and permissions.

If pool creation fails, the callback must propagate the exception so CRaC knows the restore is not complete. Do not set readiness to true before connection and verification succeed.

### 7.1 Avoid calling the entire application bootstrap again

Do not write:

~~~java
@Override
public void afterRestore(Context<? extends Resource> context) {
    applicationBootstrap.initializeEverything();
}
~~~

The name initializeEverything() does not indicate what it does. If inside it there are migrations, seeding, account creation, writing default configurations, or registering side effects, those operations may run again.

Instead, separate specific methods:

~~~java
@Override
public void afterRestore(Context<? extends Resource> context)
        throws Exception {
    databaseConnections.reopen();
    databaseConnections.validate();
    messageClients.reconnect();
    readiness.markReady();
}
~~~

Separating names and responsibilities makes code review easier and reduces the risk of callbacks accidentally performing database changes.

## 8. Spring Boot: controlling SQL initialization and Hibernate DDL

Spring Boot can run several database operations during ApplicationContext initialization. Understanding these configurations helps avoid confusing a fresh startup with a restore.

### 8.1 Hibernate schema generation

The **spring.jpa.hibernate.ddl-auto** property controls how Hibernate handles the schema during SessionFactory/EntityManagerFactory creation.

Common values:

| Value | Behavior |
|---|---|
| none | Do not automatically manage schema |
| validate | Check that schema is compatible with mappings |
| update | Attempt to adjust schema according to entities |
| create | Create schema on initialization |
| create-drop | Create schema on initialization and drop when closing SessionFactory |

In production, manage the schema with Flyway or Liquibase and use validate or none depending on policy. Avoid create or create-drop on databases containing data that must be preserved. update also does not replace a versioned migration and can produce hard-to-control changes.

If the application context is not recreated during restore, Hibernate startup actions do not automatically re-run. However, if the application actively closes and recreates the context or EntityManagerFactory in a callback, these configurations will be applied again.

### 8.2 Spring SQL initialization

Spring Boot can execute schema.sql and data.sql when the application context starts, depending on configuration and database type.

Related properties include:

- spring.sql.init.mode
- spring.sql.init.schema-locations
- spring.sql.init.data-locations
- spring.sql.init.continue-on-error

If using these scripts for initialization data, determine exactly when they run. In a normal CRaC restore process, the application context is already in the image and is not automatically restarted. However, if the context or datasource initializer is recreated by application code, the scripts may run again.

Do not enable continue-on-error to hide duplicate key errors or schema errors. That can cause the application to transition to a ready state even though initialization only partially completed.

### 8.3 Flyway or Liquibase with Hibernate

A common configuration is to let the migration tool own the schema and have Hibernate only validate:

~~~properties
spring.jpa.hibernate.ddl-auto=validate
spring.flyway.enabled=true
~~~

The exact configuration depends on the Spring Boot version, database, and deployment method. Flyway can be disabled in the application runtime if migrations are run by a separate job:

~~~properties
spring.flyway.enabled=false
spring.jpa.hibernate.ddl-auto=validate
~~~

If using a migration job, the application needs to verify that the schema version is compatible before receiving traffic. Do not disable validation without an alternative check step.

### 8.4 ApplicationReadyEvent is not afterRestore

ApplicationReadyEvent belongs to Spring Boot's startup lifecycle. It is emitted when the application context finishes starting up. CRaC restore does not automatically re-run the entire Spring startup lifecycle like a new process.

If post-restore handling is needed, use a Resource callback or the framework's CRaC integration. Do not put migrations or seeding in a callback invoked after restore just to "re-run startup".

## 9. Liquibase and Flyway: configurations that easily cause scripts to re-run

Migration tools have history mechanisms, but the changelog or script itself can still be designed to run again.

### 9.1 Liquibase runAlways

A changeSet with runAlways=true will be run every time Liquibase update is called, even if the changeSet has been recorded previously.

Do not use runAlways for non-idempotent operations such as:

- INSERTing a new account without a unique key.
- Resetting balances or business state.
- DELETEing an entire table and then INSERTing again.
- Creating test data or sample data in production.
- Incrementing a counter on every startup.

If an operation genuinely needs to run every time, ensure it is safe when repeated and has a clear data scope.

### 9.2 Liquibase runOnChange

runOnChange=true allows a changeSet to re-run when its checksum changes. It is suitable for certain replaceable objects such as views or stored procedures, depending on design.

Do not use it for one-time data-changing migrations if re-running could overwrite user data. For schema changes or historical data migrations, it is usually better to create a new changeSet.

### 9.3 Flyway repeatable migrations

Flyway supports repeatable migrations, usually using the R__ prefix, and re-executes them when the checksum changes. This is a useful mechanism for views, procedures, or objects that can be updated according to a new definition.

If a repeatable migration contains data or side effects, control its repeatability. Modifying a repeatable migration file can cause it to be re-executed on the next migrate.

### 9.4 Released migrations must be immutable

Do not edit versioned migrations that have already run in shared environments to "quick fix" history. Checksum validation may report an error and different databases may have run different contents.

Create a new migration to fix the schema or data. This keeps history auditable and helps environments converge to the same state.

## 10. The database continues changing while the image is kept

A checkpoint image saves the Java process state. It does not freeze the database server and does not save a consistent snapshot of all database data.

Suppose:

1. Application version A connects to database schema version 10.
2. A is warmed up and checkpointed.
3. The database is migrated to version 11.
4. Multiple instances are restored from image A.
5. Instances of A continue running with code built for schema version 10.

If migration version 11 drops a column that code A still needs, restored instances will fail even though the checkpoint succeeded.

This is a version compatibility issue between the application image and the database schema. It must be managed with an expand/contract strategy.

### 10.1 Expand/contract migration

A safe sequence is typically:

**Expand**

- Add new columns or tables.
- Keep old columns so old code continues working.
- If needed, dual-write or backfill data.
- Deploy new code that can read both old and new schemas.

**Migrate application and data**

- Shift traffic to the new code.
- Backfill or migrate data in batches.
- Verify no instances are still using the old structure.

**Contract**

- Only after all old instances and checkpoint images are no longer used, drop the old columns, tables, or indexes.
- Create a separate migration for the removal step.
- Invalidate or mark old images as expired so they are not accidentally restored.

~~~mermaid
flowchart TD
    A["Schema v10 + App A"] --> B["Expand: add compatible structure"]
    B --> C["Compatible schema v10/v11"]
    C --> D["Deploy App B and backfill"]
    D --> E["Verify no App A/old image remains"]
    E --> F["Contract: remove old structure"]
    F --> G["Schema v11"]
~~~

Checkpoint images can outlive a single rollout. Therefore, image lifetime and schema compatibility must be managed together. Do not just check running pods; know which images can still be restored from cache or storage.

### 10.2 Storing schema version in image metadata

You can record the application version and schema compatibility range alongside the checkpoint image:

~~~json
{
  "applicationVersion": "2.4.0",
  "checkpointId": "image-2026-11-13-001",
  "schemaMinVersion": 10,
  "schemaMaxVersion": 11
}
~~~

This is metadata defined by the deployment system, not a mandatory CRaC format. The controller can use it to reject a restore if the current schema is outside the range supported by the application.

Do not just store the schema version in a static field and assume it is always accurate. Reconcile against the actual database state or migration history after reconnecting.

## 11. Transactions and in-flight data

Do not checkpoint while the application still has unhandled database transactions. Connections and transaction state belong to the database server and are not guaranteed to be restored just because JDBC objects remain in the heap.

Before checkpoint:

- Stop accepting new work.
- Wait for in-flight requests and transactions to complete.
- Commit or roll back according to business logic.
- Return connections to the pool or close the pool according to lifecycle.
- Save offsets/message acknowledgments if the application processes messages.
- Do not keep a transaction open across the checkpoint period.

After restore, create new connections and start new transactions. If a business operation was partially executed before checkpoint, use idempotency mechanisms or workflow state to continue safely.

For example, if an order is created in the database but the confirmation message has not been sent yet, the reconnect callback cannot know for sure whether the message was received by the broker. The outbox pattern, idempotent consumers, or clear transaction boundaries help handle this situation.

## 12. Handling seeding and bootstrap with side effects

Some initializations do not only write to the database but also call other services:

- Creating a default user.
- Issuing an API key.
- Registering a webhook.
- Creating a bucket or queue.
- Sending a welcome email.
- Creating a subscription or recurring schedule.

If bootstrap is called again after restore, side effects may repeat even if database inserts are already protected by a unique key.

### 12.1 Using a business key and completion state

For a bootstrap step that must only be performed once, a marker with a unique key can be stored:

~~~sql
CREATE TABLE bootstrap_step (
    step_key VARCHAR(100) PRIMARY KEY,
    completed_at TIMESTAMP NOT NULL
);
~~~

Before performing the side effect, the system needs to coordinate the marker with the business operation safely. A SELECT checking the marker followed by calling an external API still has a race condition if two instances run concurrently.

Database transactions and locks can be used to reserve execution rights, but a single ACID transaction cannot be formed across every external HTTP API. For remote side effects, use an idempotency key supported by the target service or an outbox/retry protocol.

### 12.2 Seeding administrator accounts

Do not recreate an admin account with a default password on every restore. If a bootstrap account is required:

- Only create it if it does not already exist.
- Use a unique username or identity.
- Store the password hash according to security policy.
- Do not reset the password of an account that an administrator has already changed.
- Record that bootstrap has completed.
- Do not print secrets into logs or checkpoint metadata.

If access recovery is needed, use a separate administrative procedure instead of re-running seeding.

### 12.3 Do not reset business data

Statements like:

~~~sql
TRUNCATE TABLE customer;
DELETE FROM orders;
UPDATE account SET balance = 0;
~~~

are not safe initialization operations if the tables contain real data. Do not place them in afterRestore callbacks or startup hooks that run on production databases.

If cache data needs to be recreated, use a separate table or namespace that can be rebuilt without affecting business data.

## 13. Checking the database after restore

After the connection pool is recreated, the application can run read-only checks:

- Connection succeeds.
- Database user has required permissions.
- Schema history exists and is at a supported version.
- Essential tables or columns are present.
- A simple health check query executes successfully.
- Pre-checkpoint transactions have ended.
- Consumers or schedulers are only started after dependencies are ready.

It is not necessary to run migrations to perform these checks. A validator that reads schema metadata or queries migration history can be used.

If the schema version is incompatible, keep readiness false and report a clear error. Do not automatically run a compatibility-breaking migration just to make the instance restore.

## 14. Testing to detect re-running initialization

Test fresh startup, successful checkpoint, successful restore, and failed checkpoint.

| Scenario | What to verify |
|---|---|
| Fresh startup | Migrations and seeding run according to policy |
| Running migration runner a second time | Old migrations do not re-run; checksum/version are validated |
| Checkpoint after startup | No in-flight transactions or migrations |
| Successful restore | Only connection/resource recovery runs; no unintended DDL or seeding |
| Restoring multiple replicas | No multiple processes concurrently running bootstrap side effects |
| Failed checkpoint | Resources are reopened; database is not reset or migrations re-run |
| Database changes schema while image exists | Old image is rejected or remains compatible according to policy |
| Repeated seed execution | No duplicates created and user data is not overwritten |
| Connection pool reconnect failure | Readiness stays false; migrations are not run as a way to fix connectivity |
| Restore from old image | Schema compatibility is verified before serving |

You can record migration version and seed count in logs or metrics to compare before checkpoint and after restore. For tests, use a separate database and disposable data. Do not test destructive scripts on shared databases.

## 15. Recommended implementation workflow

When integrating CRaC with an application that uses a database, the following workflow can be applied:

**Step 1 — Inventory all initialization.** Find Flyway, Liquibase, Hibernate DDL, schema.sql, data.sql, import.sql, custom initializers, and scripts run by containers.

**Step 2 — Categorize operations.** Separate schema migration, reference data seeding, bootstrap identity, validation, and connection recovery into distinct components.

**Step 3 — Manage versioned migrations.** Use schema history and checksums. Do not modify released migrations; create new migrations for subsequent changes.

**Step 4 — Choose where to run migrations.** Prefer a dedicated migration job or a startup path with explicit database locking. Do not place the migration runner in afterRestore.

**Step 5 — Make seeding idempotent.** Use unique constraints, appropriate upserts, and only update system-owned columns. Separate reference data from user data.

**Step 6 — Separate CRaC Resources.** beforeCheckpoint stops work and closes the pool; afterRestore creates a new pool, verifies connectivity, and restores clients. Do not call overall bootstrap.

**Step 7 — Ensure schema compatibility.** Use expand/contract and track checkpoint images that can still be restored. Do not drop structures that code in old images still needs.

**Step 8 — Handle transactions and side effects.** Drain requests, finish transactions, and use idempotency/outbox for repeatable operations.

**Step 9 — Test restore multiple times.** Confirm no unexpected DDL or seeding, the pool reconnects properly, and readiness is only enabled when the schema is compatible.

## References

- [CRaC — What CRaC is](https://crac.org/about/about-crac/): checkpoint/restore model and lifecycle coordination with the application.
- [CRaC — Integrating CRaC in your Application](https://docs.azul.com/crac/usage/integrating-crac): registering Resource and implementing beforeCheckpoint/afterRestore.
- [Spring Boot — Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html): SQL initialization, Hibernate, and migration tools.
- [Spring Boot — Application Events and Listeners](https://docs.spring.io/spring-boot/reference/features/spring-application.html): lifecycle and application events.
- [Flyway — Migrations](https://documentation.red-gate.com/flyway/flyway-concepts/migrations): versioned and repeatable migrations.
- [Flyway — Validate](https://documentation.red-gate.com/flyway/reference/commands/validate): checking migration history and checksums.
- [Liquibase — Changeset attributes](https://docs.liquibase.com/concepts/changelogs/attributes/home.html): runAlways, runOnChange, and changeSet attributes.
- [Liquibase — Database changelog lock](https://docs.liquibase.com/concepts/basic/databasechangeloglock-table.html): how Liquibase coordinates changelog changes.
- [PostgreSQL — INSERT](https://www.postgresql.org/docs/current/sql-insert.html): ON CONFLICT and insert/upsert operations.
