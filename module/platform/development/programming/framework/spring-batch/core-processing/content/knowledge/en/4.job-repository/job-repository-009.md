# Choosing the Database and DataSource for Metadata

`JobRepository` is where Spring Batch stores metadata to track jobs and steps: JobInstance, JobExecution, StepExecution, and ExecutionContext. Metadata lets the framework distinguish runs, prevent duplicate launches, track status, and resume work after an execution fails or stops.

Therefore, the database used for metadata is part of the batch operations design. You need to choose a suitable database management system, configure the correct `DataSource` and transaction manager, prepare the schema per the Spring Batch version, and decide whether metadata shares a database with business data or is placed separately.

## 1. What Does JobRepository Store?

`JobRepository` stores Spring Batch's control state; it is not by default the place that stores all the business data the job is processing. With a JDBC JobRepository, metadata is stored in tables such as:

| Table Group | Main Contents |
|---|---|
| `BATCH_JOB_INSTANCE` | The identities of JobInstances by job name and identifying parameters |
| `BATCH_JOB_EXECUTION` | The executions of a JobInstance, their status and run times |
| `BATCH_JOB_EXECUTION_PARAMS` | The JobParameters of each JobExecution |
| `BATCH_STEP_EXECUTION` | The execution history of each step, the number of records read/written, and status |
| The `*_CONTEXT` tables | The ExecutionContext of jobs and steps, used to store recovery state |
| The corresponding sequences or key-generation structures | Allocate IDs for the metadata records |

Table names and schema details depend on the Spring Batch version and the database management system. The schema scripts that ship with Spring Batch provide the suitable structure for each supported database type.

For example, an order-import job may write order data to the business table `ORDERS`, while `JobRepository` writes the run state into the `BATCH_*` tables. When the job fails, the metadata helps Spring Batch know which step has completed and where the most recent checkpoint is.

## 2. Criteria for Choosing a Metadata Database

For development and test environments, an embedded database can be convenient because it is easy to initialize and clean up. For production, you should use a relational database with durable storage and transactions suited to the application.

Criteria to consider:

1. **Supported by Spring Batch.** Choose a management system that has a corresponding schema script in the Spring Batch version in use. Check the documentation and the script that ships with the exact dependency instead of taking the schema from a different version.
2. **Reliable transactions and locking.** The repository creates and updates metadata in transactions. The database must support the isolation levels and locking mechanisms needed for the way the system runs batch.
3. **Durable storage.** Metadata must remain after the application restarts or a node fails. The database needs backup, recovery, and a suitable retention policy.
4. **Shareable across application instances.** If a job can be launched from multiple nodes, the nodes must access one consistent repository to recognize JobInstances and executions.
5. **Meets write and query load.** Metadata is usually smaller than business data, but a job with many steps, many chunks, or many partitions can generate a significant volume of updates.
6. **Has existing operational tooling.** The team needs to monitor connections, capacity, locks, backup, access permissions, and the database maintenance schedule.

Common relational databases can be used when the Spring Batch version provides the corresponding schema and a suitable driver configuration. Do not choose a database just because the business application uses it; confirm that the transactions, schema, locking, and operations all meet the requirements.

### Why Shouldn't You Use an In-Memory Database in Production?

An in-memory embedded database such as H2 is very useful for demos and tests. However, when the JVM ends, the data of an in-memory database is usually lost. If metadata disappears, Spring Batch no longer has the JobInstance, JobExecution, and ExecutionContext history to recognize an old run or recover a checkpoint.

A file-based embedded database can keep data across process restarts, but you still need to consider concurrent access, durability, backup, HA, and operational support. For production systems or multiple nodes, a managed shared database is usually the more suitable choice.

## 3. Choosing One or Multiple DataSources?

Spring Batch needs one `DataSource` for the JDBC JobRepository. The application may also have one or more datasources to read/write business data. There are two common models.

### Sharing a DataSource for Metadata and Business Data

In the simple model, metadata and business data live in one database and share one `DataSource` and transaction manager.

```text
Spring Batch application
        |
        v
   DataSource
        |
        v
   One relational database
        |
        +-- BATCH_* metadata tables
        +-- ORDERS, CUSTOMERS, ... business tables
```

Advantages:

- Simple configuration, fewer connection pools, and fewer components to operate.
- You can use the same transaction manager for metadata and business data when the operations share a transaction resource.
- It is easy to inspect batch state together with the processed data in one database.

The point to consider is that the batch load and business data share database resources. Jobs that write many chunks can increase contention, log volume, or connection pressure. Access permissions also need to be limited so business code cannot arbitrarily modify the metadata tables.

### Separating the DataSource for Metadata and Business Data

An application can use a separate database or schema for metadata, and another datasource for business data:

```text
Spring Batch application
        |
        +--> batchDataSource ------> Batch metadata database
        |                             BATCH_* tables
        |
        +--> businessDataSource --> Business database
                                      ORDERS, CUSTOMERS, ...
```

This model is useful when you need to separate access permissions, backup, data lifecycle, resources, or query load. It also lets you administer metadata under its own policy.

In return, the application must manage multiple connection pools, datasources, transaction managers, and schema-initialization configuration. If metadata and business data are in two different databases, a local JDBC transaction usually cannot atomically commit both places. A situation can occur where business data has committed but the metadata checkpoint has not been written, or the metadata has been updated but the business operation in the other database has not completed.

Therefore, when separating databases, you need to design idempotent write operations, a unique business key, a reconciliation mechanism, or a suitable compensation process. You should not assume that two separate datasources automatically form a unified transaction.

## 4. The Transaction Manager Must Match the DataSource

`JobRepository` uses a `DataSource` to store metadata and a `PlatformTransactionManager` to manage transactions for repository operations. Steps also need a transaction manager suited to the business resources they read or write.

When metadata and business data use the same database and the same transaction resource, you can share the datasource and transaction manager. This helps coordinate chunk data updates and batch state within a transaction according to the step and repository configuration.

When using a separate datasource, configure the transaction manager for JobRepository to point to the batch datasource. A step that writes business data must use the business datasource's transaction manager. If you need atomicity across two databases, you need a distributed transaction solution that is clearly designed and supported; otherwise, design so you can recover when one side has committed and the other has not.

Do not inadvertently attach `batchTransactionManager` to a step that writes data to `businessDataSource`, or vice versa. A transaction manager manages the resource it was created to manage; using the wrong manager can make an operation fall outside the intended transaction.

## 5. Configuring a Shared DataSource

With a Spring Boot application that has only one datasource, Boot can usually use that datasource for Spring Batch and auto-configure JobRepository. Example PostgreSQL connection configuration:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders
    username: batch_app
    password: ${ORDERS_DB_PASSWORD}
    driver-class-name: org.postgresql.Driver

  batch:
    jdbc:
      initialize-schema: never
```

In this example, `initialize-schema: never` assumes the metadata schema has been created and is managed through the environment's migration process. In a test environment, you can configure Spring Boot to initialize the schema automatically instead of using a separate migration.

With manual Java configuration in Spring Batch 5, `@EnableBatchProcessing` can specify the datasource and transaction manager used for the batch infrastructure:

```java
@Configuration
@EnableBatchProcessing(
    dataSourceRef = "dataSource",
    transactionManagerRef = "transactionManager"
)
public class BatchConfiguration {
    // Declare Job and Step beans here.
}
```

When Spring Boot has already auto-configured the batch infrastructure, do not add `@EnableBatchProcessing` just to redeclare the default configuration. Enabling this annotation switches the application to explicit batch infrastructure configuration and may cause some Spring Boot auto-configuration to no longer apply. Only use it when you deliberately manage the infrastructure configuration.

## 6. Configuring a Separate Datasource for Metadata

When an application has multiple datasources, specify clearly which datasource is used for batch metadata. With explicit Spring Batch 5 configuration, you can declare bean names in `@EnableBatchProcessing`.

Example of a condensed configuration:

```java
@Configuration
@EnableBatchProcessing(
    dataSourceRef = "batchDataSource",
    transactionManagerRef = "batchTransactionManager"
)
public class BatchInfrastructureConfiguration {

    @Bean
    @ConfigurationProperties("app.datasource.batch")
    DataSource batchDataSource() {
        return DataSourceBuilder.create().build();
    }

    @Bean
    PlatformTransactionManager batchTransactionManager(
            @Qualifier("batchDataSource") DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }
}
```

The necessary imports include `DataSourceBuilder`, `ConfigurationProperties`, `Qualifier`, `DataSource`, `JdbcTransactionManager`, and the corresponding Spring annotations. The properties configuration must provide a suitable URL, username, password, and driver.

With Spring Boot, a datasource marked `@BatchDataSource` can be recognized by auto-configuration as the datasource for Spring Batch. This approach suits wanting to keep Boot's auto-configuration. Choose one consistent configuration method; avoid both enabling the infrastructure yourself with `@EnableBatchProcessing` and expecting Boot to keep creating the same batch beans automatically.

When separating datasources, declare a business datasource and a separate transaction manager for the steps that operate on business data. For example, a chunk step that writes to the orders database must use the transaction manager attached to that business datasource.

## 7. Creating and Managing the Metadata Schema

Spring Batch provides schema scripts by database. The script needs to be taken from the exact library version that is running. Do not copy an old schema file into the project and then upgrade the Spring Batch version without checking the metadata changes.

In Spring Boot, the property `spring.batch.jdbc.initialize-schema` is commonly used to control schema initialization:

| Value | Common Meaning |
|---|---|
| `embedded` | Initializes the schema automatically when an embedded database is detected |
| `always` | Always runs the schema initialization script |
| `never` | Does not run the script automatically; the schema is managed externally |

For production, you should usually manage DDL with a migration tool such as Flyway or Liquibase, after confirming the script suits the Spring Batch version. In that case, set the automatic initialization configuration to `never` to avoid the application running DDL itself during startup.

The schema deployment process should include:

1. Determine the application's exact Spring Batch version.
2. Get the schema script for the database in use from that version's artifact or documentation.
3. Review schema differences when upgrading the library and prepare the corresponding migration.
4. Run the migration with a deployment account that has DDL permissions.
5. Grant the runtime account the minimum permissions needed to read, write, and update metadata.
6. Verify that the application starts, creates a JobInstance and JobExecution, executes a step, and then queries metadata successfully.

Do not let multiple application instances run the table-creation script at the same time in one deployment. Perform the migration in a controlled deployment step before the application instances start using the new schema.

## 8. Schema, Table Prefix, and Access Permissions

The metadata tables can be placed in a separate schema to separate permissions and responsibilities, for example the schema `BATCH_META`. You need to configure the datasource or database connection so JDBC statements access the right schema, and create the tables with a suitably adjusted script.

Spring Batch supports customizing the table prefix in the JobRepository configuration. The default prefix is usually `BATCH_`; changing the prefix changes the table names the repository queries. A prefix does not replace choosing a schema or granting database permissions. If you use a separate schema, make sure the table-creation script and the connection configuration both point to the right place.

You can separate permissions as follows:

- The migration account has permission to create, alter, and update the metadata schema.
- The batch application's runtime account has the permissions needed to read and write the metadata tables.
- The business account may only access the data tables the job needs to process.
- Other user or service accounts must not modify metadata directly without a controlled operational request.

Do not grant DBA privileges to the runtime account just so Spring Batch can write metadata. Minimum privileges help limit the impact when the application or an SQL statement hits an error.

## 9. Database and Configuration When Running Multiple Instances

When multiple instances of the application can launch or coordinate jobs, they must share one durable JobRepository. If each node points to its own metadata database, each node may not see the JobInstances and executions created by the other nodes. This loses the ability to coordinate and can lead to duplicate processing.

```text
Application node A ----+
                       |
Application node B ----+----> Shared JobRepository database
                       |          BATCH_* metadata
Application node C ----+
```

JobRepository uses database constraints and transactions to protect metadata creation, instance recognition, and state updates. The isolation level configuration for the execution-creation operation needs to suit the database and the concurrency requirements. In a standard JDBC configuration, the metadata-creation operation usually uses a strict isolation level such as `SERIALIZABLE` to reduce the risk of two concurrent requests creating the same JobInstance. You can adjust `isolationLevelForCreate` when there is a reason and it has been verified on the specific database.

The shared database needs enough connection capacity for all nodes. At the same time, you need to monitor lock waits, deadlocks, timeouts, the connection pool, and metadata write latency. If a job runs for a long time or has many partitions, the load of updating StepExecution and ExecutionContext can increase significantly.

## 10. Backup, Retention, and Recovery

Metadata is part of the application state. Backing up the business database while skipping the metadata database can leave the processed data and batch state out of sync. Conversely, restoring metadata to a different point in time than the business data can make a job restart from a checkpoint that does not match the actual data.

Therefore, include metadata in the backup and disaster recovery plan. If metadata and business data are in two databases, you need to define how to coordinate backup times, restore, and reconciliation after recovery.

The metadata tables grow with the number of JobInstances, JobExecutions, StepExecutions, and the content of ExecutionContext. Define how long to retain history based on auditing, error investigation, and operations needs. Cleanup must follow foreign-key relationships and the rules of the Spring Batch version; do not arbitrarily delete from individual `BATCH_*` tables with manual statements.

When restoring a repository, make sure the schema is compatible with the application version that will run. Do not let a new code version read metadata that was migrated per an incompatible version without a restart test.

## 11. Common Configuration Errors

| Error | Symptom or Risk | How to Handle |
|---|---|---|
| Using an in-memory database in production | Metadata is lost when the process ends or is not shared among nodes | Use a durable database, shared when you need to run multiple nodes |
| JobRepository points to the wrong datasource | Metadata tables are not found or metadata is written to an unintended database | Declare the batch datasource explicitly and check the actual URL/schema |
| Transaction manager does not match the datasource | Operations fall outside the intended transaction or connection errors arise | Attach each transaction manager to the right datasource |
| Creating tables with the schema of a different version | SQL errors, missing columns, or metadata incompatibility | Use the schema script/migration of the exact Spring Batch version |
| Multiple nodes use their own repositories | Nodes do not see the same execution history and may process duplicates | Use one shared repository database |
| Separating metadata and the business DB but assuming atomic commit | One side may commit while the other fails | Design idempotency, reconciliation, or a deliberate distributed transaction |
| Runtime account has overly broad permissions | Increases the risk of schema changes or metadata deletion | Separate the migration and runtime accounts, grant minimum privileges |
| Deleting metadata without following relationships | Broken references or inconsistent loss of history | Use a controlled retention process that suits the schema |

When you hit a startup error, check the database URL, driver, account, current schema, table permissions, migration scripts, and the JobRepository creation log. When you hit a restart error or duplicate run, check whether the nodes use the same repository and look at the JobInstance/JobExecution history in the metadata.

## 12. How to Choose a Configuration by Situation

| Situation | Suitable Choice |
|---|---|
| Learning or simple testing | Embedded database with an automatically initialized schema |
| A single production application, moderate load | A durable relational database; you can share the datasource with business data if the transactions and operations suit it |
| Multiple nodes running batch | One shared JobRepository database that is durably administered |
| Need to separate permissions or the metadata lifecycle | A separate datasource/schema, with the transaction manager and the cross-database recovery strategy configured clearly |
| Production with a DDL management process | Migration with Flyway/Liquibase; turn off the application's automatic schema initialization |

There is no single correct datasource choice for every system. If you need simplicity and the data is in one database, sharing the datasource is usually easier to operate. If you need to isolate resources or permissions, you can separate metadata, but you must handle the transaction boundary and recovery explicitly.

## Conclusion

The JobRepository database stores the control state Spring Batch needs to recognize jobs, track each execution, and restart from the stored metadata. Choose a durable relational database with a schema suited to the Spring Batch version, configure the datasource and transaction manager for the right resources, and manage the schema through a controlled deployment process.

For a simple application, metadata can share the datasource with business data. When separating datasources, you need to account for the non-atomic transaction between the two databases, idempotency, and reconcilability. With multiple nodes, all must share the JobRepository to share execution history and coordinate safely.
