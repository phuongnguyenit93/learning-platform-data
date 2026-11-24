# JobRepository Using an External Database

Spring Batch needs to store metadata to know which Jobs have run, what status each execution has, how far a Step has processed, and which state it can restart from. The component responsible for managing this metadata is the **JobRepository**.

In real applications, metadata is usually stored in a relational database external to the application process, such as PostgreSQL, MySQL, Oracle, or SQL Server. This database can be the one that stores business data or a separate database dedicated to batch. Using a durable database lets execution history survive application restarts and allows multiple application instances to work with one metadata store.

## 1. What Data Does JobRepository Store?

JobRepository is where Spring Batch creates, queries, and updates the metadata of JobInstance, JobExecution, StepExecution, and ExecutionContext. Metadata describes the running process, not the business data that the Job is importing or transforming.

In the default JDBC schema, the important tables usually include:

| Table | Role |
| --- | --- |
| **BATCH_JOB_INSTANCE** | Stores the JobInstances, including the Job name and the instance identity |
| **BATCH_JOB_EXECUTION** | Stores each Job execution, its status and execution times |
| **BATCH_JOB_EXECUTION_PARAMS** | Stores the JobParameters of a JobExecution |
| **BATCH_STEP_EXECUTION** | Stores the metadata of each Step execution, such as read count, write count, skip count, and status |
| **BATCH_JOB_EXECUTION_CONTEXT** | Stores the ExecutionContext at the JobExecution level |
| **BATCH_STEP_EXECUTION_CONTEXT** | Stores the ExecutionContext at the StepExecution level |

Depending on the database and Spring Batch version, the schema also has sequences or a corresponding ID-allocation mechanism. The tables are linked by primary keys and foreign keys to keep the relationships among JobInstance, JobExecution, and StepExecution.

For example, an order-import Job may have one JobInstance for the business date 11/15/2026. If the first run fails and is then restarted, JobRepository stores two JobExecutions linked to the same JobInstance. The Step metadata is also stored so Spring Batch knows which Step has completed and which checkpoint state can be restored.

~~~text
Spring Batch metadata database
    |
    +-- BATCH_JOB_INSTANCE
    |       |
    |       +-- BATCH_JOB_EXECUTION
    |               |
    |               +-- BATCH_JOB_EXECUTION_PARAMS
    |               +-- BATCH_JOB_EXECUTION_CONTEXT
    |               |
    |               +-- BATCH_STEP_EXECUTION
    |                       |
    |                       +-- BATCH_STEP_EXECUTION_CONTEXT
    |
    +-- Sequences / ID-allocation support objects
~~~

JobRepository lets Spring Batch manage the lifecycle and restart capability based on durable data. If metadata is stored only in memory, that information can be lost when the process ends; the JDBC repository helps maintain history across application startups.

## 2. The Metadata Database Can Be a Separate Database

There are two common arrangements:

**Shared database:** JobRepository stores metadata in the same database as the business data. This is usually simpler because the application only needs one connection and can share a transaction manager if the operations are on the same DataSource.

**Separate database:** JobRepository stores metadata in a dedicated database, while ItemReader, ItemWriter, or business services access a different database. This helps separate load, access permissions, and the metadata lifecycle from business data.

~~~text
Option A: Shared database

Spring Batch Application
       |
       v
Business Database
       |
       +-- Business data tables
       |
       +-- BATCH_JOB_INSTANCE
       +-- BATCH_JOB_EXECUTION
       +-- BATCH_STEP_EXECUTION


Option B: Separate databases

Spring Batch Application
       |
       +----------------------+
       |                      |
       v                      v
Business Database       Batch Metadata Database
       |                      |
       +-- Orders              +-- BATCH_JOB_INSTANCE
       +-- Customers           +-- BATCH_JOB_EXECUTION
       +-- Import data         +-- BATCH_STEP_EXECUTION
                              +-- ExecutionContext
~~~

In the separate-database option, you need to configure clearly the DataSource for JobRepository and the DataSource used for business data. You should not assume that Spring Batch will automatically figure out which database holds the metadata.

Separating databases does not change the concepts of JobInstance, JobExecution, or StepExecution. It only changes where metadata is stored and how the application manages connections, transactions, access permissions, and operations.

## 3. Connecting JobRepository to an External Database with Spring Boot

If a Spring Boot application has only one DataSource, Spring Batch usually uses that DataSource for the metadata repository. When the DataSource points to an external database, the metadata is also stored in that database.

Example PostgreSQL configuration in the application.properties file:

~~~properties
spring.datasource.url=jdbc:postgresql://db-host:5432/batch_metadata
spring.datasource.username=batch_user
spring.datasource.password=replace-with-secret
spring.datasource.driver-class-name=org.postgresql.Driver

# Initialize the Batch schema when deploying an environment that needs the tables created.
spring.batch.jdbc.initialize-schema=always
~~~

Connection values should be provided through environment variables or a secret manager. You should not commit database passwords into source code or configuration files pushed to a repository.

If you use a different database, you need to add the corresponding JDBC driver and declare the URL, driver, and suitable credentials. For example, a PostgreSQL URL looks like:

~~~text
jdbc:postgresql://db-host:5432/batch_metadata
~~~

When the application starts, Spring Boot creates the DataSource and configures the Spring Batch infrastructure based on that configuration. If the schema already exists and is managed by a migration tool, configure the application not to initialize the schema again.

### Using a Separate Database for Batch in an Application with Multiple DataSources

An application can have a main DataSource for business and a second DataSource for metadata. With Spring Boot, you can mark the DataSource intended for Batch with the **@BatchDataSource** annotation so the auto-configuration mechanism recognizes the right bean.

Example declaring a DataSource for Batch:

~~~java
@Bean
@BatchDataSource
@ConfigurationProperties("app.batch.datasource")
public DataSource batchDataSource() {
    return DataSourceBuilder.create().build();
}
~~~

The corresponding connection properties can be set in application.properties:

~~~properties
app.batch.datasource.url=jdbc:postgresql://db-host:5432/batch_metadata
app.batch.datasource.username=batch_user
app.batch.datasource.password=replace-with-secret
app.batch.datasource.driver-class-name=org.postgresql.Driver
~~~

The application still needs to configure the business DataSource separately in a way that suits its structure. In an application with multiple DataSources, you need to declare clearly which bean is primary and check the transaction managers injected into each component. The configuration above only illustrates how to mark the Batch DataSource; it does not replace designing the transaction managers for the Steps.

If you add **@EnableBatchProcessing** to a Spring Boot application yourself, Boot's Batch auto-configuration backs off. In that case, the application must take responsibility for configuring the Batch infrastructure and initializing the schema in its own way. You should not add this annotation just to specify a DataSource if the current Boot configuration already meets the requirements.

## 4. Configuring JobRepository with Java Configuration

In a Spring Batch configuration that does not rely on Spring Boot auto-configuration, you can specify the DataSource and transaction manager for JobRepository through **@EnableBatchProcessing**.

Example using a separate database for metadata:

~~~java
@Configuration
@EnableBatchProcessing(
        dataSourceRef = "batchDataSource",
        transactionManagerRef = "batchTransactionManager"
)
public class BatchInfrastructureConfiguration {

    @Bean
    public DataSource batchDataSource() {
        return DataSourceBuilder.create()
                .url("jdbc:postgresql://db-host:5432/batch_metadata")
                .username("batch_user")
                .password(System.getenv("BATCH_METADATA_DB_PASSWORD"))
                .driverClassName("org.postgresql.Driver")
                .build();
    }

    @Bean
    public PlatformTransactionManager batchTransactionManager(
            @Qualifier("batchDataSource") DataSource batchDataSource) {
        return new DataSourceTransactionManager(batchDataSource);
    }
}
~~~

In a real application, you should put the URL and username into externalized configuration such as application.properties or environment variables; the code above only illustrates how to connect the two components.

The two attributes of the annotation mean:

- **dataSourceRef** points to the DataSource bean that JobRepository uses to store metadata.
- **transactionManagerRef** points to the transaction manager that manages repository operations on that DataSource.

The bean names must match the reference values. If you omit these attributes, the Batch infrastructure will look for beans by the configuration's default names. For an application with multiple DataSources, you should declare them explicitly to avoid accidentally writing metadata to the business database or an unintended database.

Another way is to extend **DefaultBatchConfiguration** and provide the infrastructure components according to the API of the Spring Batch version in use. You should only choose one suitable infrastructure configuration approach; do not arbitrarily combine multiple Batch configuration mechanisms in the same application.

## 5. Configuring the Transaction Manager for a Step

JobRepository needs a transaction manager to manage metadata operations. A TaskletStep or chunk-oriented Step also needs a transaction manager for the work the Step performs. These two roles can share one transaction manager or use different transaction managers depending on the database arrangement.

If metadata and business data are on one DataSource, you can usually share the transaction manager:

~~~java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .writer(writer)
            .build();
}
~~~

If metadata and business data are in two different databases, you need to specify the Step's transaction manager explicitly. For example, a Step that writes order data to the business database:

~~~java
@Bean
public PlatformTransactionManager businessTransactionManager(
        @Qualifier("businessDataSource") DataSource businessDataSource) {
    return new DataSourceTransactionManager(businessDataSource);
}

@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        @Qualifier("businessTransactionManager")
        PlatformTransactionManager businessTransactionManager,
        ItemReader<Order> reader,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, businessTransactionManager)
            .reader(reader)
            .writer(writer)
            .build();
}
~~~

In this configuration, the transaction manager passed into the chunk controls the business work's transaction. JobRepository is configured with batchTransactionManager to manage metadata. You need to understand that two independent transaction managers do not automatically form a distributed transaction.

If the business transaction commits successfully but the metadata update fails, or the metadata is updated while the business transaction rolls back, the state between the two databases may not be synchronized as expected. Using two DataSources does not by itself guarantee atomicity across both systems.

If it is mandatory that both business data and metadata commit or roll back together, you need to consider a suitable distributed transaction solution such as JTA/XA with resources that support it. This is a decision with higher operational cost and complexity. For many batch systems, idempotent design, clear checkpoints, and a reconciliation process are often an important part of the recovery strategy.

## 6. Initializing the Schema for an External Database

The JDBC JobRepository needs the metadata tables and corresponding supporting objects. Spring Batch provides schema scripts for the supported database management systems. You need to use the script suited to the database and the Spring Batch version that is running.

With Spring Boot, the property:

~~~properties
spring.batch.jdbc.initialize-schema=always
~~~

lets the schema initialization mechanism run when the application starts. This is a convenient choice in development or test environments that need to stand up a database quickly.

In a production environment, the schema is usually created and upgraded through a migration tool such as Flyway or Liquibase. When migrations are responsible for managing the schema, the application can set:

~~~properties
spring.batch.jdbc.initialize-schema=never
~~~

The deployment process then includes:

1. Choose the schema script that ships with the Spring Batch version in use.
2. Create the corresponding migration for the target database.
3. Run the migration with a deployment account that has DDL permissions.
4. Grant the runtime account the permissions needed to read, write, and update metadata.
5. Start the application with automatic schema initialization turned off.

You should not take the script of an arbitrary Spring Batch version and use it long-term for every version. Table structure, data types, sequences, and how parameters are stored can change when upgrading the framework. The migration must be checked against the version being deployed.

If you use **@EnableBatchProcessing** in a plain Spring Batch configuration, do not assume by default that this annotation will automatically create tables in the database. You need to actively choose how to run the schema script or migration. In a Spring Boot application, adding this annotation also changes the behavior of Boot's auto-configuration and schema initializer.

## 7. Access Permissions and Database Configuration

The database account used for JobRepository needs enough permissions for Spring Batch to perform metadata operations. During schema deployment, the migration account may need permissions to create tables, indexes, sequences, and constraints. The account that runs the application usually only needs DML permissions and the permission to use the necessary sequences.

You should separate schema-deployment permissions from runtime permissions if the security policy requires it. It is not necessary to grant permission to create or drop tables to the batch process that runs daily.

The information that needs to be configured and checked includes:

| Component | What to Confirm |
| --- | --- |
| JDBC driver | The driver is compatible with the database and the Java version |
| JDBC URL | The exact host, port, and database or service name |
| Credentials | The runtime account and secret are granted correctly |
| Network | The application can reach the database host and port |
| Connection pool | The pool size suits the number of Jobs/Steps and the concurrent load |
| Schema | The tables, indexes, sequences, and constraints were created in the correct version |
| Permissions | The runtime user has permission to read, write, and update metadata |
| Timeouts | The connection timeout, socket timeout, and transaction timeout are appropriate |

JobRepository is a component that is accessed while launching a Job, updating a Step, and storing checkpoints. If the metadata database is unavailable, the application may not launch or may be unable to update execution state properly. Therefore, you need to monitor this database's connections and capacity as an important component of the batch system.

## 8. Sharing JobRepository Across Multiple Application Instances

A major benefit of an external metadata database is that multiple instances of the same application can share one JobRepository. For example, two nodes that both deploy the order-import Job can see the metadata of runs that were initiated from the other node.

~~~text
          Scheduler / Job Operator
                    |
          +---------+---------+
          |                   |
          v                   v
      Batch Node A         Batch Node B
          |                   |
          +---------+---------+
                    |
                    v
          Shared JobRepository
          (External Database)
                    |
                    v
          BATCH_JOB_INSTANCE
          BATCH_JOB_EXECUTION
          BATCH_STEP_EXECUTION
~~~

JobRepository and the constraints in the schema help coordinate JobInstance identity and executions. When multiple nodes simultaneously request to run the same Job with the same identifying parameters, the repository must protect instance creation from duplicate creation. The isolation level property when creating a JobExecution plays a role in handling this contention.

With Spring Boot, you can configure the isolation level used when creating a JobExecution:

~~~properties
spring.batch.jdbc.isolation-level-for-create=SERIALIZABLE
~~~

The default value is usually chosen to protect the execution-creation operation from contention. Only change the isolation level after understanding the database characteristics, the concurrent load, and the behavior when multiple launch requests arrive at once. Lowering the isolation level to reduce locks without checking can increase the risk of race conditions or metadata-creation errors.

The nodes must use the same compatible metadata schema, the same way of naming Jobs, and the same JobParameters conventions. You should not let two incompatible application versions write into one schema if there is no clear upgrade plan and compatibility control.

## 9. Table Prefix and Separating Metadata

The default schema uses the prefix **BATCH_** for the metadata tables. In some environments, the application may need to change the prefix to distinguish the metadata of groups of Jobs or to avoid name collisions with other tables.

With Spring Boot, you can configure:

~~~properties
spring.batch.jdbc.table-prefix=APP_BATCH_
~~~

With plain Spring Batch configuration, you can specify the table prefix through an attribute of **@EnableBatchProcessing** or configure the JobRepository through a mechanism supported by the framework version.

When you change the prefix, the table names in the database must match the repository's configuration. Changing only the property without creating or renaming the corresponding tables will cause the metadata SQL statements to not find the tables.

A table prefix does not replace choosing a database or schema. If you want to separate by database schema, you need to configure the permissions and the default schema of the connecting account, or configure object names in the way the database and framework support.

## 10. Querying Metadata to Check JobRepository

After the application runs, you can query metadata to confirm that the repository is writing to the external database. For example, a query for recent JobExecutions:

~~~sql
SELECT
    JOB_EXECUTION_ID,
    JOB_INSTANCE_ID,
    STATUS,
    START_TIME,
    END_TIME,
    EXIT_CODE
FROM BATCH_JOB_EXECUTION
ORDER BY JOB_EXECUTION_ID DESC;
~~~

To view JobInstances and their related executions:

~~~sql
SELECT
    ji.JOB_INSTANCE_ID,
    ji.JOB_NAME,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.START_TIME,
    je.END_TIME
FROM BATCH_JOB_INSTANCE ji
LEFT JOIN BATCH_JOB_EXECUTION je
    ON je.JOB_INSTANCE_ID = ji.JOB_INSTANCE_ID
ORDER BY ji.JOB_INSTANCE_ID DESC, je.JOB_EXECUTION_ID DESC;
~~~

Table names and some columns can differ if you use a custom table prefix or the schema of a different version. Check against the actual schema before running queries in an operational environment.

In the application, **JobExplorer** provides an API to read metadata instead of forcing business code to query the internal tables itself. You can use JobExplorer to look up JobInstance, JobExecution, and Step status through the Spring Batch API. This approach keeps the code less dependent on the internal SQL structure.

You should not directly update or delete metadata rows to try to fix a Job's state. The tables have foreign-key relationships and the execution state is closely related. Manual changes can break restart capability or cause the repository to misunderstand history. Use the suitable operational API and a controlled metadata administration process.

## 11. Common Errors When Using an External Database

### Metadata Tables Not Found

Errors such as table not found or bad SQL grammar usually occur when the schema has not been created, was created in the wrong schema, the table prefix is wrong, or the application connected to the wrong database.

Check the JDBC URL, the current database, the user's default schema, the table names, the prefix, and the migration result. Do not just check whether the database server is running.

### Incompatible Schema Script

A script for a different database or Spring Batch version can create wrong column types, sequences, or constraints. Use the script corresponding to the database and the dependency version that is running, and then manage upgrades with controlled migrations.

### Runtime Account Lacks Permissions

The application may connect but fail on insert, update, or getting an ID from a sequence. Check permissions on each table and sequence, not just the database connection permission.

### Application Writes Metadata to the Wrong DataSource

The problem usually appears when there are multiple DataSources or multiple transaction managers. Confirm the DataSource that JobRepository uses, the bean marked primary, the qualifiers, and the references in the Batch configuration.

### Cannot Connect to the External Database

Check DNS, firewall, network routes, port, TLS, JDBC driver, credentials, and the database's connection limits. An exhausted connection pool can also prevent a Job from initializing or updating metadata.

### Two Nodes Launch the Same Job Concurrently

When there are multiple schedulers or multiple nodes, the same JobInstance may be requested to run concurrently. Share the repository, keep the schema and transaction configuration compatible, and check the isolation level when creating an execution. Do not arbitrarily delete metadata or change identifying parameters to dodge contention errors.

### Metadata and Business Data Out of Sync

If JobRepository and business data use two independent transaction managers, one side can commit while the other fails. Evaluate the transaction boundary, idempotency, checkpoints, and the reconciliation process. If you need atomicity across multiple databases, you need a corresponding distributed transaction solution.

### Restart Does Not Restore the Right Position

JobRepository only stores metadata and the ExecutionContext that components write into it. If a custom reader or Tasklet does not store the necessary state, restart cannot infer the processing position from business data by itself. Implement the ItemStream mechanism or a suitable checkpoint.

## 12. Long-Term Operating Principles

The metadata database is usually smaller than the business database but plays an important role in the ability to control and recover Jobs. You should have a dedicated operations plan for it:

- **Backup and restore:** protect metadata along with the data needed to recover the application. After a restore, check compatibility among the metadata, the schema, and the application version.
- **Migration:** upgrade the schema per Spring Batch version and test migrations before deploying to production.
- **Monitoring:** monitor the connection pool, the number of connections, latency, locks, deadlocks, database capacity, and query errors.
- **Retention:** define how long to keep metadata and a controlled archive or cleanup process. Do not delete individual rows that have foreign-key relationships.
- **Security:** store credentials in a secret manager, encrypt connections where appropriate, and limit the runtime user's permissions.
- **High availability:** evaluate the failover capability of the metadata database because an incident here can affect launching Jobs and updating their state.
- **Compatibility:** nodes sharing the repository must be compatible in schema, Job name, JobParameters, and how the Job is deployed.

JobRepository is part of the batch's operational state. If the metadata database is lost or corrupted, the application may lose the ability to look up history and restart safely, even if the business data remains intact.

## 13. Process for Configuring a JobRepository Using an External Database

When deploying a new application, you can proceed in this order:

1. **Choose where to store metadata:** share the business database or create a separate database for Batch.
2. **Prepare the database:** create the database or schema, users, permissions, and network access.
3. **Declare the DataSource:** configure the JDBC driver, URL, credentials, pool, and secret.
4. **Choose the transaction manager:** determine the transaction manager for JobRepository and for each Step.
5. **Initialize the schema:** use the script for the Spring Batch version or a managed migration.
6. **Configure JobRepository:** use Spring Boot's auto-configuration or specify the DataSource and transaction manager in Java configuration.
7. **Check metadata:** run a test Job, query JobInstance and JobExecution to confirm data is written to the right database.
8. **Check restart:** make a controlled failed run and then restart with the same identifying parameters to confirm metadata is stored durably.
9. **Check operations:** try reconnecting after the application restarts and confirm the nodes sharing the repository see the same execution history.

You should not treat the application connecting successfully as the only proof that JobRepository is configured correctly. You need to confirm the schema, metadata write permissions, transaction behavior, and the ability to read back execution history as well.

## Conclusion

A JobRepository using an external database lets Spring Batch store metadata durably, support restart, and share execution history among multiple application instances. The core configuration consists of the right DataSource, a schema compatible with the Spring Batch version, a suitable transaction manager, and database access permissions. When metadata and business data are in two different databases, you need to design the transaction boundary, checkpoints, and recoverability clearly to avoid an out-of-sync state.
