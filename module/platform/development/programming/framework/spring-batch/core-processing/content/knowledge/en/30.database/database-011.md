# Multiple DataSources in Batch

A Spring Batch application can work with multiple databases or multiple `DataSource` instances: one for Spring Batch metadata, one for reading business data, one for writing results, or multiple sources across integrated systems. The key is explicitly specifying which `DataSource` each component uses and which `PlatformTransactionManager` manages each Step's transactions.

Spring Batch requires a `JobRepository` to store JobInstance, JobExecution, StepExecution, and ExecutionContext. These metadata tables can live in the same business database or in a separate database. Readers, Writers, and business services can use other datasources. Separating datasources isolates metadata, permissions, and access load, but requires careful design for transactions and restarts.

## 1. Why does a batch application need multiple DataSources?

Common scenarios:

- **Batch metadata database:** stores `BATCH_JOB_INSTANCE`, `BATCH_JOB_EXECUTION`, `BATCH_STEP_EXECUTION`, and ExecutionContext tables.
- **Source database:** reads data from a source system such as ERP or CRM.
- **Target database:** writes transformed data into a target system.
- **Reference database:** reads catalogs, exchange rates, or reference data.
- **Audit database:** stores application-specific business logs or processing status.

For example, a Job transferring orders from a source system to a target system can use three datasources:

```text
                    Spring Batch Job
                           |
             +-------------+-------------+
             |             |             |
             v             v             v
       Batch metadata   Source DB     Target DB
       JobRepository    ItemReader    ItemWriter
       Job/Step state   reads orders  writes imported_orders
```

`JobRepository` manages orchestration state. The source database supplies input data. The target database stores business results. These components can use separate connections and transaction managers.

## 2. Distinguishing metadata DataSource and business DataSources

Do not confuse the datasource Spring Batch uses to persist metadata with the datasources Readers/Writers use to process data.

| Component | Role | Example bean |
|---|---|---|
| Batch metadata `DataSource` | Stores Job/Step history and state | `batchDataSource` |
| Batch metadata transaction manager | Manages JobRepository transactions | `batchTransactionManager` |
| Source `DataSource` | Reads input data | `sourceDataSource` |
| Target `DataSource` | Writes output data | `targetDataSource` |
| Target transaction manager | Manages target-writing chunk transactions | `targetTransactionManager` |

JobRepository needs a durable datasource if you want restarts across application stops or restarts. Using an in-memory repository does not retain metadata persistently like a database repository.

Metadata tables have Spring Batch's own schema. When using a dedicated metadata database, initialize the exact schema matching your database engine and Spring Batch version. Do not create `BATCH_*` tables in the target database simply because the Writer uses the target datasource.

## 3. Naming beans and using @Qualifier

When multiple beans of type `DataSource` or `PlatformTransactionManager` exist, Spring cannot always infer which bean to inject. Name beans explicitly and use `@Qualifier` everywhere a specific selection is needed.

Example declaring transaction managers:

```java
import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class TransactionManagerConfig {

    @Bean("batchTransactionManager")
    public PlatformTransactionManager batchTransactionManager(
            @Qualifier("batchDataSource") DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean("targetTransactionManager")
    public PlatformTransactionManager targetTransactionManager(
            @Qualifier("targetDataSource") DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }
}
```

`DataSourceTransactionManager` manages JDBC transactions for a single datasource. If the application uses JPA, you may need a `JpaTransactionManager` for the corresponding persistence unit. Never use database A's transaction manager assuming it can commit or roll back connections on database B.

You can mark one datasource or transaction manager as `@Primary` if the application has a clear default choice. Even so, in multi-datasource batch configurations, explicit `@Qualifier` annotations are usually easier to read and less error-prone.

## 4. Specifying the datasource for JobRepository

With Spring Batch 5, you can use `@EnableBatchProcessing` and explicitly reference the metadata datasource and transaction manager beans by name:

```java
import org.springframework.batch.core.configuration.annotation.EnableBatchProcessing;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableBatchProcessing(
        dataSourceRef = "batchDataSource",
        transactionManagerRef = "batchTransactionManager")
public class BatchInfrastructureConfig {
}
```

Spring Batch uses `batchDataSource` for JobRepository and `batchTransactionManager` for metadata operations. Both the datasource and transaction manager beans must be declared in the application context with those exact names.

When using manual Java configuration, ensure the metadata schema is created in `batchDataSource`. How the schema is initialized depends on the database, environment, and application migration mechanism. In production, schema should generally be managed via controlled migrations rather than letting each application startup recreate it automatically.

If you fail to specify the datasource explicitly when multiple beans exist, infrastructure may inject the wrong default datasource or fail due to no unique bean match. Explicitly declare the metadata database right at Batch infrastructure configuration.

## 5. Configuring source and target datasources for Reader/Writer

Suppose the application defines three beans:

- `batchDataSource`: metadata database.
- `sourceDataSource`: database containing source orders.
- `targetDataSource`: database storing imported orders.

The Reader must receive the source datasource; the Writer must receive the target datasource. Example using `JdbcPagingItemReader` for paginated reads:

```java
import javax.sql.DataSource;

import org.springframework.batch.item.database.JdbcPagingItemReader;
import org.springframework.batch.item.database.Order;
import org.springframework.batch.item.database.builder.JdbcPagingItemReaderBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.BeanPropertyRowMapper;

@Bean
public JdbcPagingItemReader<SourceOrder> sourceOrderReader(
        @Qualifier("sourceDataSource") DataSource sourceDataSource) {

    return new JdbcPagingItemReaderBuilder<SourceOrder>()
            .name("sourceOrderReader")
            .dataSource(sourceDataSource)
            .selectClause("select id, customer_id, amount")
            .fromClause("from source_order")
            .sortKeys(Map.of("id", Order.ASCENDING))
            .rowMapper(new BeanPropertyRowMapper<>(SourceOrder.class))
            .pageSize(500)
            .saveState(true)
            .build();
}
```

The example above assumes `SourceOrder` is a JavaBean with matching properties. The sort key must be stable and unique so paging does not skip or duplicate records across pages. If the query needs filtering by JobParameters, use `@StepScope` and bind parameters into the query.

Writer using target datasource:

```java
import javax.sql.DataSource;

import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;

@Bean
public JdbcBatchItemWriter<TargetOrder> targetOrderWriter(
        @Qualifier("targetDataSource") DataSource targetDataSource) {

    return new JdbcBatchItemWriterBuilder<TargetOrder>()
            .dataSource(targetDataSource)
            .sql("""
                    insert into imported_order
                        (source_order_id, customer_id, amount)
                    values (:sourceOrderId, :customerId, :amount)
                    """)
            .beanMapped()
            .build();
}
```

`TargetOrder` must have JavaBean properties matching the named parameters in SQL. For records or other data types, provide a custom `ItemSqlParameterSourceProvider`.

One thing to verify is that the Writer actually receives the target datasource. If it accidentally receives the source datasource, the Job might run successfully while writing data to the wrong database.

## 6. Choosing the transaction manager for a chunk Step

Each chunk-oriented Step receives a `PlatformTransactionManager` in the `chunk(...)` call. This transaction manager manages the chunk's transaction. When a Step reads from a source database and writes to a target database, decide which resource belongs inside the chunk transaction.

Example transferring data from source to target, where target needs commit/rollback per chunk:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
public Step transferOrdersStep(
        JobRepository jobRepository,
        @Qualifier("targetTransactionManager")
        PlatformTransactionManager targetTransactionManager,
        JdbcPagingItemReader<SourceOrder> sourceOrderReader,
        ItemProcessor<SourceOrder, TargetOrder> orderProcessor,
        JdbcBatchItemWriter<TargetOrder> targetOrderWriter) {

    return new StepBuilder("transferOrdersStep", jobRepository)
            .<SourceOrder, TargetOrder>chunk(500, targetTransactionManager)
            .reader(sourceOrderReader)
            .processor(orderProcessor)
            .writer(targetOrderWriter)
            .build();
}
```

In this example, the chunk transaction manages the target datasource. The reader reads from a separate source datasource; read operations do not automatically join the target transaction. This is a common design for extract-transform-load flows, though you must explicitly define snapshot requirements and source data consistency.

JobRepository is configured with a separate `batchTransactionManager`. Therefore, metadata transactions and target business transactions are not a single local transaction. The consequences are explained in the distributed transactions section below.

## 7. A Step accepts only one transaction manager for chunks

A chunk Step does not accept multiple independent transaction managers to commit multiple datasources simultaneously. Passing `targetTransactionManager` into `chunk(...)` does not make `sourceDataSource` or `batchDataSource` automatically join the same transaction.

If a chunk must update two databases simultaneously and requires both to commit or roll back as an atomic unit, a single `DataSourceTransactionManager` is insufficient. Options include:

1. Using a JTA/XA transaction manager and matching XA resources to coordinate a distributed transaction.
2. Designing for eventual consistency using outbox, inbox, idempotency keys, or compensation workflows.
3. Splitting operations into separate Steps, each with its own transaction manager plus restart/reconciliation mechanisms.
4. When possible, placing changes that must be atomic in the same database under the same transaction manager.

Never manually call `commit()` on a second datasource's connection inside a Writer. Doing so breaks the transaction boundary managed by Spring Batch and can leave partial data behind when a chunk rolls back.

## 8. JobRepository and business transactions can commit out of sync

When the metadata database and business database differ, they typically use two separate local transaction managers. Two transactions are not automatically atomic with each other.

For example, a chunk writes data to the target database and updates checkpoints/metadata in the batch database:

```text
Chunk execution
   |
   +--> Target DB transaction
   |       writes business data
   |
   +--> Batch DB transaction
           saves StepExecution / ExecutionContext
```

If one database commits while the other fails before committing, the two stores can reflect different states. One case is target data committed while the checkpoint was not saved; restart may re-read items and attempt to write them again. Another case is the checkpoint advancing while business changes failed to commit, causing a restart to skip that slice of data.

To handle this:

- Use business keys and unique constraints so the Writer can rerun safely.
- Use upserts or a processed-item table with idempotency keys.
- Keep source data stable via snapshots/watermarks.
- If atomicity across databases is strictly required, use a fully supported XA/JTA transaction coordinator and test on production-equivalent infrastructure.
- If eventual consistency is acceptable, record outbox/audit state and include a reconciliation Step to detect and repair drift.

Separating the metadata database is a valid choice, but do not assume it automatically provides exactly-once processing across systems.

## 9. Configuring multiple DataSources in Spring Boot

With Spring Boot, distinguish two configuration approaches:

- Use Boot's Batch auto-configuration and designate the dedicated metadata datasource with the `@BatchDataSource` qualifier.
- Manually configure Batch infrastructure with `@EnableBatchProcessing` and explicitly reference beans via `dataSourceRef`/`transactionManagerRef`.

Conceptual example using auto-configuration:

```java
@Bean
@BatchDataSource
DataSource batchDataSource() {
    // Create datasource connecting to the metadata database.
}

@Bean
@Primary
DataSource applicationDataSource() {
    // Default datasource for the business application.
}
```

`@BatchDataSource` is Spring Boot's qualifier identifying the datasource dedicated to Batch. The `@Primary` bean can be the business datasource if it serves as the application's default. Readers/Writers should still use explicit `@Qualifier` annotations.

If you add `@EnableBatchProcessing` or extend `DefaultBatchConfiguration`, Spring Boot Batch auto-configuration may back off because the application is supplying infrastructure itself. In that case, you take full responsibility for configuring JobRepository, JobLauncher, and schema initialization accordingly. Never mix both mechanisms without knowing which beans create the Batch infrastructure.

Property details and auto-configuration behavior can vary by Spring Boot version. Check the exact version your application uses, especially for metadata schema initialization and default datasource selection.

## 10. Example configuration with three datasources and two transaction managers

A Java configuration can be structured as follows. The DataSource beans are assumed to be created from separate connection pool configurations:

```java
import javax.sql.DataSource;

import org.springframework.batch.core.configuration.annotation.EnableBatchProcessing;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
@EnableBatchProcessing(
        dataSourceRef = "batchDataSource",
        transactionManagerRef = "batchTransactionManager")
public class MultiDataSourceBatchConfig {

    @Bean("batchTransactionManager")
    PlatformTransactionManager batchTransactionManager(
            @Qualifier("batchDataSource") DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean("targetTransactionManager")
    PlatformTransactionManager targetTransactionManager(
            @Qualifier("targetDataSource") DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }
}
```

Then the Reader/Writer and Step use the matching beans:

```java
@Bean
public Step transferOrdersStep(
        JobRepository jobRepository,
        @Qualifier("targetTransactionManager")
        PlatformTransactionManager targetTransactionManager,
        JdbcPagingItemReader<SourceOrder> sourceOrderReader,
        JdbcBatchItemWriter<TargetOrder> targetOrderWriter) {

    return new StepBuilder("transferOrdersStep", jobRepository)
            .<SourceOrder, TargetOrder>chunk(500, targetTransactionManager)
            .reader(sourceOrderReader)
            .processor(sourceOrderProcessor())
            .writer(targetOrderWriter)
            .build();
}
```

In real setups, `sourceDataSource`, `targetDataSource`, and `batchDataSource` can be declared using `DataSourceProperties` with HikariCP. Use distinct configuration prefixes, such as `app.datasource.source`, `app.datasource.target`, and `app.datasource.batch`, to avoid mixing URLs, usernames, or pool settings.

## 11. Managing connection pools per datasource

Each datasource normally has its own connection pool. When batches run in parallel, total connections can equal the sum of pool sizes across source, target, and metadata databases.

Example:

| Pool | Purpose | Considerations |
|---|---|---|
| Source pool | Reader opens connections to read data | Partition/thread count, cursor lifetime, query latency. |
| Target pool | Writer writes data in chunks | Concurrent worker count, transaction duration, lock contention. |
| Batch pool | JobRepository reads/writes metadata | Concurrent Job/Step executions, polling, and metadata updates. |

Do not set every datasource's pool size identically by guesswork. If 16 workers run while the target pool has only 4 connections, workers will block waiting for connections. If the source database caps concurrent queries, enlarging the pool can overload the source system.

Monitor active/idle/pending connections, connection acquisition timeouts, transaction durations, query latency, and worker counts. Set appropriate connection timeouts and validation so the Job fails clearly if a datasource is unavailable.

## 12. Reading from multiple sources within one Job

A Job can contain multiple Steps, each using a different datasource. Example:

```text
Job: nightlyAggregationJob
   |
   v
readCustomerStep (customerDataSource)
   |
   v
readPaymentStep (paymentDataSource)
   |
   v
aggregateStep (warehouseDataSource)
   |
   v
publishStep (reportDataSource)
```

Each Step can receive the transaction manager matching the database that Step writes to. If a Step only reads, still evaluate source data consistency and isolation. If data across multiple sources must reflect the exact same point in time, you need snapshots, watermarks, or data synchronization mechanisms; reading databases sequentially does not automatically produce a consistent distributed snapshot.

If a Processor needs to query a reference database, inject the datasource/service explicitly and evaluate performance. Querying reference data per item can create N+1 queries. You can cache reference data within an appropriate scope or join data prior to entering the pipeline if volume and consistency requirements permit.

## 13. Restarting when using multiple datasources

Restarting requires metadata from JobRepository alongside source/target data in a state compatible with the checkpoint. When multiple datasources are involved, keep these elements stable:

1. Same identifying JobParameters to restart the exact JobInstance.
2. Source data does not mutate outside the chosen snapshot/watermark.
3. Readers have stable names and save state when checkpointing is needed.
4. Target Writers are idempotent to handle reprocessed items after rollbacks or metadata drift.
5. The batch metadata database is not wiped or reset between runs.
6. Transaction managers continue pointing to the exact right datasources after deploy/restart.

For instance, if a Job reads the source DB by `id <= cutoffId`, store the cutoff ID as an identifying parameter or immutable batch metadata. If the query uses `ORDER BY id`, restart can resume by stable key. If source data mutates and the query lacks a snapshot, new items inserted before the checkpoint may be skipped or already-read items may change content.

If the metadata database becomes temporarily unavailable, JobRepository cannot persist state reliably. Do not continue processing assuming metadata will catch up automatically afterward.

## 14. Testing multi-datasource configurations

Integration tests should use separate test databases for metadata, source, and target to catch miswired qualifiers or transaction managers. Use Testcontainers if the application needs to verify specific database behaviors.

Scenarios to test:

1. **Metadata isolation:** JobInstance/JobExecution appear in the batch database and are not accidentally written to source/target.
2. **Source reader:** data is read from the exact source datasource.
3. **Target writer:** data is written only to the target datasource per configured SQL.
4. **Transaction rollback:** when the Writer throws an exception, target changes in the current chunk roll back under the target transaction manager.
5. **Restart:** after failure, the Job restarts with the same identifying parameters and the Writer creates no duplicate records.
6. **Datasource unavailable:** verify the Job fails clearly when source, target, or metadata database loses connectivity.
7. **Concurrent execution:** verify pool sizing, lock contention, and unique constraints when multiple Jobs/partitions run concurrently.
8. **Cross-database consistency:** if using XA/JTA, test cases where one resource rolls back or disconnects during prepare/commit.

Example checking target after the Job:

```java
Integer targetCount = new JdbcTemplate(targetDataSource).queryForObject(
        "select count(*) from imported_order where batch_id = ?",
        Integer.class,
        batchId);

assertEquals(expectedCount, targetCount);
```

At the same time, use `JobExplorer` or `JobRepository` to confirm JobExecution/StepExecution reside in the metadata database. Do not merely check that the Job is `COMPLETED`; verify actual data in each respective database.

## 15. Common mistakes

| Mistake | Consequence | Resolution |
|---|---|---|
| Not specifying a datasource for JobRepository | Metadata may be created in the default datasource or configuration may fail. | Use `dataSourceRef` or `@BatchDataSource` per your configuration style. |
| Injecting `DataSource` without a qualifier | Spring injects the wrong bean or fails due to multiple candidates. | Use explicit bean names and `@Qualifier`. |
| Using the batch transaction manager for a target writer | Writer does not participate in target transactions as intended. | Select the matching transaction manager in `chunk(...)`. |
| Assuming one Step atomically commits multiple datasources | A local transaction manager manages only its own resource. | Use JTA/XA or design eventual consistency. |
| Reading source and writing target without anti-duplicate keys | Restarts may rewrite items already committed in target. | Unique constraints, upserts, and idempotency keys. |
| Creating BATCH_* schema in the wrong database | JobRepository cannot find or writes metadata to the wrong place. | Initialize schema in the batch metadata database. |
| Pool size too small or too large | Workers block on connections or database is overloaded. | Measure load and tune each pool independently. |
| Mixing `@EnableBatchProcessing` unclearly with Boot auto-config | Infrastructure beans may collide or auto-config may back off. | Choose one consistent Batch infrastructure setup. |
| Restarting after source data mutated | Checkpoints may skip or duplicate data. | Use snapshots, watermarks, and stable query ordering. |
| Assuming two local databases commit atomically | Business data and checkpoints can drift out of sync. | XA/JTA or reconciliation/idempotent processing. |

## Conclusion

A Spring Batch application can use multiple datasources for metadata, source data, target data, and reference systems. Name beans clearly, use `@Qualifier`, assign the datasource/transaction manager for JobRepository, and choose the matching transaction manager for each chunk Step. A Step has only one local transaction manager per chunk; multiple databases do not automatically commit atomically together. When separating batch metadata from business data, account for metadata and business data drifting out of sync, use business keys/unique constraints/upserts for safe restarts, or use JTA/XA when true distributed atomicity is required. Testing each datasource, transaction rollback, restart, and connection pool keeps multi-database setups predictable in operation.
