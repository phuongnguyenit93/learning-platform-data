# Oversized Context and Metadata Cost

In Spring Batch, `ExecutionContext` stores state values needed so a job or step can continue after stopping or failing. For example, a reader can store the last line position read, the next page, the key of the last processed record, or the identifier of the input file. This is data serving checkpoints and restarts.

`ExecutionContext` is persisted alongside batch metadata through `JobRepository`. With a JDBC repository, the context is serialized and written into metadata tables such as `BATCH_STEP_EXECUTION_CONTEXT` and `BATCH_JOB_EXECUTION_CONTEXT`. Therefore, every value added to the context incurs storage, serialization/deserialization, and database write costs at the points where the repository persists the context.

If large lists, full payloads, entity graphs, or business data are put into the context, metadata can bloat. The consequences are increased CPU and memory during serialization, increased database size, slower repository operations, longer backup/restore times, and restarts becoming dependent on objects that are hard to keep compatible across application versions.

The important design principle is: **store only small checkpoints and necessary references to continue work; large data should reside in storage appropriate for the business domain.**

## What Is ExecutionContext Used to Store?

`ExecutionContext` is a key-value area attached to a `JobExecution` or `StepExecution`. Components such as readers, writers, and tasklets can store state that needs to be restored in the context.

Examples of suitable values:

- `currentLine`: the line number or next read position in a file.
- `lastProcessedId`: the last key processed in a stably ordered query.
- `nextPage`: the page number to read on the next call.
- `sourceFile`: path or name of the input resource.
- `inputVersion`: version or checksum of the data source to identify the snapshot.
- `stagingBatchId`: identifier of a staging dataset prepared in another system.

These values are small, have clear meaning, and help the processing component determine where to resume. The context is not designed to replace a business database, file storage, object storage, or application cache.

### Job ExecutionContext and Step ExecutionContext

Spring Batch has two context scopes:

| Scope | Bound to | Common usage |
| --- | --- | --- |
| Job `ExecutionContext` | `JobExecution` | Stores a few small values needed to pass between steps in the same job execution |
| Step `ExecutionContext` | `StepExecution` | Stores step-specific checkpoints, such as reader position or page processing state |

The step context is usually updated at step commit points, especially on each chunk in chunk-oriented processing. The job context is usually saved at job/step update boundaries, such as when a step completes. Specific save frequency depends on step type and repository lifecycle.

Because the step context can be saved many times in a long job, placing large data there often causes repeated overhead. The job context is also not an appropriate place to store large payloads just because it is updated less frequently.

## Where Is Metadata Stored?

With a JDBC `JobRepository`, Spring Batch stores contexts in metadata tables:

| Table | Content |
| --- | --- |
| `BATCH_STEP_EXECUTION_CONTEXT` | Context of each `StepExecution` |
| `BATCH_JOB_EXECUTION_CONTEXT` | Context of each `JobExecution` |

The standard JDBC schema typically has columns such as `SHORT_CONTEXT` and `SERIALIZED_CONTEXT`; column types and schema details depend on the database management system and Spring Batch version. The context is converted to a storage form by the configured serializer, and the repository then writes it to the database.

When the context is updated at a checkpoint, the repository needs to prepare the serialized representation and write metadata. If the context is large, this operation can consume CPU, allocate intermediate objects in memory, transfer a lot of data over JDBC, and write larger amounts of data to the database.

`ExecutionContext.put...()` does not mean an immediate SQL statement is executed on every call. Values are held in the context during processing and saved by the repository at metadata update points per the step/job lifecycle. However, if the context is large at each save point, serialization and write costs still increase with context size.

## Why Does a Large Context Increase Costs?

### Serialization and deserialization cost

Before saving the context, Spring Batch uses the configured `ExecutionContextSerializer` to convert the data into a storable form. When reading metadata to restart, the context is deserialized back.

The larger the context, the more it typically requires:

- More CPU to serialize and deserialize.
- More intermediate objects and memory allocations.
- More memory in the heap while the context is held during execution.
- More data transferred over JDBC.
- More time to save or restore checkpoints.

If a step has thousands of chunks and the context holds a large list, the cost can repeat across many updates. Even if the list does not change after each chunk, keeping it in the context still increases the size of saved metadata.

### Database size and metadata growth

Large contexts make metadata tables grow rapidly. This affects:

- Database size and growth rate per number of executions.
- Backup, replication, restore, and data synchronization across environments.
- Read/write time for context records.
- Metadata retention and cleanup policies.
- Traceability of old jobs when metadata tables contain large payloads.

Batch metadata is often retained for auditing and investigation. If each execution stores megabytes of context, storage will grow significantly as run counts increase, even if actual business data is stored elsewhere.

### Schema and serializer limits

Some database schemas have a short context column and a full serialized column. Even if the database supports CLOB/TEXT or an equivalent large type, large sizes still carry costs and may hit limits from the driver, serializer, configuration, or custom schema.

Do not rely on the database's ability to store a very large string to turn `ExecutionContext` into a general-purpose data store. Technical storability does not mean it is a suitable design for checkpoints.

### Impact on restart

On restart, Spring Batch must read and restore the context. A large context increases recovery time, while also increasing serializer and class compatibility risks between old and new application versions.

If the context contains many domain objects, package changes, class structure changes, or serializer changes can prevent old jobs from deserializing after deploying a new version. Incomplete jobs may become stuck even though business data remains intact.

## Example of an Unsuitable Design

Suppose a reader reads one million orders and a tasklet stores the entire list in the context for the next step to use:

```java
ExecutionContext context = stepExecution.getExecutionContext();
context.put("allOrders", orders); // Should not store large lists
```

If each `Order` contains many fields, addresses, line item details, and nested objects, the context can become a very large payload. Spring Batch must serialize it when saving metadata and deserialize it again on restart. If the step has multiple checkpoints, the same list may be serialized repeatedly.

Common variations of this anti-pattern:

- Storing an entire `List` or `Map` containing thousands/millions of items.
- Storing `byte[]` of input or output files.
- Storing large API response bodies.
- Storing entire JPA entities along with lazy/eager relationships.
- Storing caches, lookup tables, or large reference datasets.
- Storing the entire list of errors or processing results to write out at the end of the job.

Such data should be stored in a business database, staging table, file, or object storage. The context only needs to hold a stable identifier to look up the data again.

## Store References Instead of Payloads

Instead of storing whole objects, store a key or reference to where the data resides. For example, load data into a staging table and store `stagingBatchId` in the context:

```java
ExecutionContext context = stepExecution.getExecutionContext();
context.putString("stagingBatchId", stagingBatchId);
context.putLong("lastProcessedId", lastProcessedId);
```

The next step uses `stagingBatchId` to query data from the staging table. The context contains only a few scalar values, while large data sits in a database designed for storing and querying business data.

Another example is storing a reference to a file in object storage:

```java
context.putString("sourceObjectKey", "imports/2026/11/orders-15.csv");
context.putString("sourceVersion", sourceVersion);
context.putString("sourceChecksum", checksum);
```

On restart, the reader fetches the object by key and checks version/checksum to ensure it is reading the exact same source used in the initial run.

A good reference should:

- Be stable throughout the job lifecycle and restarts.
- Point to data that still exists when the job needs to resume.
- Have a version or checksum if source content might change.
- Be protected with appropriate access permissions.
- Have a retention policy aligned with metadata retention time and restart capability.

Do not store short-lived temporary URLs or paths that exist only on a single node's filesystem if the job can restart on another node.

## Designing Small and Meaningful Checkpoints

A good checkpoint typically describes **position or progress**, without containing the data to be processed.

Example with a reader reading a database by ascending key:

```java
public class OrderReader implements ItemStreamReader<OrderInput> {

    private long lastProcessedId;

    @Override
    public void open(ExecutionContext context) {
        lastProcessedId = context.getLong("lastProcessedId", 0L);
    }

    @Override
    public OrderInput read() {
        // Read the next record with id > lastProcessedId.
        // After identifying the item, update lastProcessedId in the reader's state.
        return readNextOrder();
    }

    @Override
    public void update(ExecutionContext context) {
        context.putLong("lastProcessedId", lastProcessedId);
    }

    @Override
    public void close() {
        // Release resources if any.
    }
}
```

`readNextOrder()` is the query part implemented by the application. The example focuses on how to save the checkpoint: store only the last key, not all the `OrderInput` items read.

With a custom reader, `ItemStream` provides the `open`, `update`, and `close` lifecycle. Spring Batch calls `update` at the step's state-saving points. Built-in readers such as file readers or paging readers typically already have their own state mechanisms; prefer configuring built-in state instead of manually saving the same data list additionally.

Checkpoints must accurately reflect committed data. If the reader updates the key in memory while reading but the chunk rolls back, the framework needs to restore state from the saved checkpoint to re-read the uncommitted portion. Do not manually write checkpoints to a separate database before business data completes.

## Choosing Stable Data Types for the Context

`ExecutionContext` can store values that the configured serializer can handle. To reduce risk, prefer simple, small, and stable types such as:

- `String` for codes, paths, resource names, versions, or statuses.
- `Long` or `Integer` for IDs, offsets, line numbers, and page numbers.
- `Boolean` for progress flags.
- `Double` or an appropriate numeric type when a numeric value is truly needed.
- Date/time or other types if the application's serializer supports them stably and formats are agreed upon.

Avoid storing directly:

- JPA entities or Hibernate proxies.
- `InputStream`, `Reader`, `Connection`, `EntityManager`, or open resources.
- Objects with large relationship graphs or complex circular references.
- Caches, large collections, or objects dependent on a single thread's state.
- Temporary classes, anonymous classes, or objects whose structure changes easily across builds.

Values must be supported by the serializer and restorable after the application restarts. For custom data types, control the serialization contract and compatibility across versions.

## Serializer Compatibility and Application Versions

The context is saved to be reused after the process finishes, so serialized data can outlive the code version that created it.

Some risks when storing custom objects:

- Class package or name changes.
- Field type or meaning changes.
- Class no longer exists in the new version.
- `serialVersionUID` or serialized structure changes.
- Serializer is replaced or configured differently across nodes.
- An old node writes context that a new node cannot read, or vice versa.

To reduce risk:

1. Prefer scalar values and stable formats instead of domain objects.
2. Use keys with clear names and meanings, maintaining compatibility on restart.
3. If custom objects are needed, design a clear schema/version and test reading old context data.
4. Ensure all nodes in the same system use compatible serializers.
5. When changing the serializer or context structure, plan for running jobs or jobs waiting to restart.

Do not change the serializer abruptly while old executions still need to restart. If old contexts cannot be read, you may have to finish executions before upgrading, provide a conversion mechanism, or handle them under a controlled recovery procedure.

## Do Not Use ExecutionContext as a Cache

`ExecutionContext` is durable metadata for restarts, not a cache for data used repeatedly per item.

Unsuitable example:

```java
context.put("customerLookupCache", allCustomers);
context.put("processedOrders", processedOrderObjects);
```

If the goal is to reduce repeated queries, consider a bounded in-memory cache, reference tables, batch lookups, or a dedicated caching service. An in-memory cache can be rebuilt after restart; if job correctness depends on that data, a durable data source and clear version are needed.

Some alternatives:

| Need | Suitable storage approach |
| --- | --- |
| Looking up thousands of reference codes | Batch query or bounded in-memory cache |
| Holding intermediate data across multiple steps | Staging table or intermediate file, context stores ID/URI |
| Storing large file payloads | File system or object storage, context stores key/version |
| Storing per-item results | Business table or dedicated result table |
| Tracking processing position | Small ID, offset, page, or cursor in context |

## Job Context and Sharing Data Between Steps

Job `ExecutionContext` is often used to share a few small values between steps. For example, an earlier step generates a report file and saves the path, and a later step sends the file to another system.

```java
ExecutionContext jobContext =
        stepExecution.getJobExecution().getExecutionContext();

jobContext.putString("reportObjectKey", reportObjectKey);
jobContext.putString("reportVersion", reportVersion);
```

If you need to move certain keys from step context to job context, you can use `ExecutionContextPromotionListener` with the list of keys to promote. Promote only small values that are truly needed by the next step.

Do not copy an entire large collection from step context to job context. Duplicating payloads increases metadata and couples multiple steps to the same object structure. Store the data in a staging store and pass only the ID or URI.

## Cost Grows with Chunk Count and Execution Count

Suppose a step has 100,000 chunks and the context holds 200 KB of data. If the context is updated on every chunk, the repository may have to serialize and write a large amount of data repeatedly. The cost is not just 200 KB stored once; it also includes CPU, memory allocation, JDBC transfer, and database writes at checkpoint points.

Impact grows along multiple dimensions:

- **Context size:** each save must process more data.
- **Checkpoint count:** the more chunks a step has, the more often the context may be saved.
- **Execution count:** each run creates additional metadata and corresponding context.
- **Retention period:** the longer metadata lives, the larger the total accumulated size.
- **Node count:** many concurrent executions increase metadata write load on the repository.

A small context of a few keys may be negligible. However, a large context saved thousands of times can become a bottleneck for the repository and database, especially when many jobs run concurrently.

## Measuring Context Cost

When suspecting metadata is a bottleneck, measure instead of relying solely on file size or item count.

Metrics to monitor:

- Average and maximum serialized context size.
- Repository execution context update time.
- Chunk commit time and total chunk duration.
- CPU and allocation in serialization/deserialization.
- Size and growth rate of the two context tables.
- Restart and context restoration time.
- Number of running, failed, and restart-pending executions.

Table sizes can be observed using database administration tools or DBMS statistics. Do not query and display entire context payloads in logs because doing so creates extra load and risks exposing sensitive data.

If an execution needs investigation, use `JobExplorer` or the appropriate metadata API to identify the relevant execution and step. Avoid editing serialized contexts directly in the database with manual SQL.

## Managing Metadata Retention and Cleanup

Contexts are stored along with execution history. If the application retains metadata indefinitely, the `BATCH_*` tables will keep growing with run counts. A retention policy should distinguish:

- Jobs that are `COMPLETED` and no longer need restart.
- `FAILED` or `STOPPED` jobs still within the allowed restart window.
- Jobs currently running or under investigation.
- Metadata required to be kept by audit or business requirements.

Only clean up metadata once you have confirmed executions no longer need restart, are no longer depended upon for investigation, and comply with retention policy. Deleting metadata can lose checkpoints and batch history; do not delete context rows separately while keeping the associated executions.

Use administration/cleanup mechanisms designed for the application's Spring Batch version and schema, or a controlled cleanup process that respects foreign key relationships. Back up before cleaning up and check retention alongside business data if the context contains references to files or staging records.

If the context only stores `stagingBatchId`, staging data retention must be at least as long as the window in which the job can still restart. If staging data is deleted before the execution is restarted, the reference in the context will no longer be useful.

## Security and Sensitive Data

Execution context is stored in the batch metadata database and may appear in backups, replication, or admin tools. Therefore, do not store:

- Passwords, access tokens, refresh tokens, or private keys.
- Database or broker credentials.
- Personal/sensitive payloads unnecessary for restart.
- Full business data merely to avoid re-querying.

If a job needs to access a protected resource, store an identifier or secret reference and fetch the secret from a secret manager at runtime. Grant metadata database permissions on a least-privilege basis and apply encryption at rest if required by system policy.

## Example: Moving from a Large Context to a Small Context

### Unsuitable storage approach

```java
ExecutionContext context = stepExecution.getExecutionContext();
context.put("orders", allOrders);
context.put("customerMap", allCustomers);
context.put("rawFileBytes", fileBytes);
```

The values above may contain thousands of objects or large payloads. They make the context hard to serialize, increase metadata size, and force restart to restore data that could have been read from the primary source.

### More suitable design

```java
ExecutionContext context = stepExecution.getExecutionContext();
context.putString("stagingBatchId", stagingBatchId);
context.putString("sourceObjectKey", sourceObjectKey);
context.putString("sourceVersion", sourceVersion);
context.putLong("lastProcessedId", lastProcessedId);
```

The step uses `stagingBatchId` to query staging data, `sourceObjectKey` and `sourceVersion` to access the exact source file, and `lastProcessedId` to continue from the checkpoint. The context is small, easy to store, and easy to restore.

If a large list of IDs needs to be passed between steps, write that list to a staging table with a batch key. The job context only needs to hold the batch key for the next step to query. Staging data can be cleaned up after the job finishes and the recovery window expires.

## Common Mistakes

### Storing all data in the context

This turns metadata into a data store, increasing serialization, database IO, and restart time. Store only checkpoints or small references.

### Storing JPA entities or object graphs

Entities can contain proxies, lazy relations, circular references, and dependencies on class versions. Store IDs or business keys and re-query when needed.

### Storing byte arrays or file contents

Large files belong in a filesystem or object storage. The context stores path/key, version, and checksum.

### Using the context as a lookup cache

Large caches bloat the context and get serialized repeatedly. Use batch queries, bounded caches, or reference data stores.

### Changing the serializer while old jobs await restart

Saved contexts may not be readable by the new serializer. Maintain compatibility, test old data, or have a migration plan before deploying.

### Deleting metadata too early

Deleting contexts or executions that still need restart can make the job unable to continue. Apply controlled retention and respect metadata relationships.

### Storing secrets in the context

Metadata can be backed up and read by operational tools. Store secret references instead of credentials or tokens.

## ExecutionContext Design Principles

When deciding whether to store a value in the context, ask yourself:

1. Is this value truly needed to continue after restart?
2. Can an ID, offset, version, or URI be stored instead of the whole object?
3. Is the value small and of a data type supported by the serializer?
4. Will it be saved repeatedly across many checkpoints?
5. Are the structure and data type compatible across deployments?
6. Does the value contain secrets or sensitive data?
7. Will the referenced resource live long enough for all allowed restarts?
8. Is there a retention policy to clean up metadata and staging data at the right time?

In most production jobs, the context should consist of a few small keys describing processing position, data scope, source version, and intermediate resource identifiers. Large business data should reside in a separately managed database, staging table, or object storage.

## Key Takeaways

`ExecutionContext` is where small checkpoints are stored so Spring Batch can restore jobs and steps. Contexts are serialized and saved to metadata tables at points where the repository updates state; in chunk steps, the step context is usually saved at commit points. Large contexts increase CPU, memory allocation, JDBC traffic, database size, and restart time; custom objects also create serializer/class compatibility risks when deploying new versions. Store offsets, IDs, pages, versions, or stable URIs instead of item lists, entity graphs, byte arrays, or large payloads. Put large data in business databases, staging tables, or object storage; manage retention for both metadata and referenced resources, and do not store secrets in the context.
