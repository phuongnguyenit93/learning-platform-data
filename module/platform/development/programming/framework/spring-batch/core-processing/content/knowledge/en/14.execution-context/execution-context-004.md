# Serialize Context into Repository

Spring Batch uses ExecutionContext to store the state needed to resume a Job or Step after being stopped or failing. When this state is saved through JobRepository, the framework must convert the key/value pairs in the context into a data format that can be written to the metadata repository. That conversion process is called serialization.

Serialization is part of the metadata storage mechanism, not an operation that the application needs to perform manually every time put() is called. The application updates ExecutionContext; Spring Batch manages when to persist it and uses an ExecutionContextSerializer to convert the context content into a storage format. When restoration is needed, the repository reads the saved data and the serializer converts it back into the values in the context.

Understanding this mechanism helps you choose suitable data types, configure the right version of the serializer, avoid errors on restart, and control the size as well as sensitivity of metadata.

## 1. Where Is ExecutionContext Stored?

Spring Batch has two ExecutionContext scopes:

- **Step ExecutionContext** belongs to a StepExecution. It typically stores internal state of the reader, writer, or logic within the Step, such as the next read position or the last processed key.
- **Job ExecutionContext** belongs to a JobExecution. It is used to share a small amount of metadata between Steps within the same Job execution.

With JDBC JobRepository, Spring Batch stores contexts in separate metadata tables:

| Scope | Common JDBC repository table |
|---|---|
| Job ExecutionContext | BATCH_JOB_EXECUTION_CONTEXT |
| Step ExecutionContext | BATCH_STEP_EXECUTION_CONTEXT |

Table names and schema can vary depending on prefix configuration or version. Each table stores information linking to the corresponding execution along with the serialized representation of the context.

ExecutionContext in memory is a key/value structure. For example:

~~~java
ExecutionContext context = stepExecution.getExecutionContext();

context.putLong("customerReader.lastId", 8500L);
context.putString("input.fileVersion", "orders-v4");
context.putInt("page.number", 12);
~~~

The values above are updated in the Step's context. When Spring Batch persists the context through JobRepository, the serializer converts them to a storage format. On restart, the framework loads the corresponding context, and the reader or writer can use those values to restore state.

You should not treat ExecutionContext as an arbitrary cache or a store for all business data. It serves the metadata and checkpoints required for the Batch lifecycle.

## 2. When Does Serialization Occur?

Calling put() only updates the context held in memory. It does not mean the data has been immediately written to the database at that line of code.

Spring Batch manages context persistence during the execution lifecycle. For a chunk-oriented Step, the framework coordinates updating stream state and saving checkpoints at chunk boundaries along with the transaction management process. The Job context is also saved via JobRepository during JobExecution updates according to the Job and Step lifecycle.

General flow:

~~~text
Reader / Writer / Step logic
          |
          | put(key, value)
          v
ExecutionContext in memory
          |
          | framework updates execution
          v
JobRepository
          |
          | ExecutionContextSerializer
          v
Serialized data format
          |
          v
Metadata database
~~~

When reading back:

~~~text
Metadata database
          |
          | serialized data
          v
ExecutionContextSerializer
          |
          v
Restored ExecutionContext
          |
          v
Reader / Writer continues from checkpoint
~~~

Normal applications do not need to call the serializer directly or write to BATCH_* tables manually. Update the context via the ExecutionContext API and let Spring Batch manage saving and restoration.

If the application calls put() and immediately queries the database in the same code block, do not assume the value has already been persisted. The save timing depends on the JobRepository lifecycle and the current transaction.

## 3. What Is ExecutionContextSerializer?

ExecutionContextSerializer is the abstraction responsible for converting context data into a writable format and restoring it from the repository.

Conceptually, a serializer works in two directions:

- **Serialize:** takes the key/value pairs in the context and writes out a representation, usually a string or byte stream.
- **Deserialize:** reads that representation and recreates the key/value pairs to restore the context.

Spring Batch provides a default serializer and allows configuring a different serializer. The specific implementation and default serializer may vary depending on the Spring Batch version as well as how the application creates the JobRepository.

Therefore, when changing framework versions or repository configurations, you need to determine which serializer is actually being used. Do not infer the serializer solely from whether the application uses JDBC or from column names in the database.

### Java serialization

A serializer based on Java Object Serialization can store objects that meet Serializable requirements. When deserializing, the JVM must be able to find the corresponding class and restore the object graph.

The advantage is being able to store certain Java object types directly without manually converting each field to a string. However, this approach creates coupling to the application's classes and object structures. When a class changes between two deployments, old data may fail to deserialize.

### JSON-based serializer

A JSON-based serializer converts the context into a text-based representation. This approach can make the data easier to inspect and supports many common data types, depending on the serializer and mapping configuration.

JSON does not automatically solve all compatibility issues. Complex data types, polymorphism, dates and times, enums, and custom objects still need clear serialize/deserialize rules. Unsafe type metadata configuration can expand the risk surface when deserializing untrusted data.

### Custom serializer

An application can provide its own implementation if it has special requirements for format, compatibility, or integration. When doing so, ensure the serializer can read back every context written in the corresponding format and have a compatibility plan when deploying a new version.

Do not choose a serializer just because the format looks easy to read. What matters is round-trip capability, compatibility across restarts, deserialization safety, and long-term metadata operation.

## 4. Configuring the Serializer for JobRepository

When manually configuring a JDBC repository with JobRepositoryFactoryBean, you can specify the serializer through the repository configuration.

Example illustrating the relevant configuration section:

~~~java
@Bean
ExecutionContextSerializer executionContextSerializer() {
    return new DefaultExecutionContextSerializer();
}

@Bean
JobRepository jobRepository(
        DataSource dataSource,
        PlatformTransactionManager transactionManager,
        ExecutionContextSerializer executionContextSerializer) throws Exception {

    JobRepositoryFactoryBean factory = new JobRepositoryFactoryBean();
    factory.setDataSource(dataSource);
    factory.setTransactionManager(transactionManager);
    factory.setSerializer(executionContextSerializer);

    // Other repository properties configured according to the application.
    factory.afterPropertiesSet();
    return factory.getObject();
}
~~~

This is an example following the JDBC repository configuration style; adjust it according to the Spring Batch version, how the application manages schema, and the repository properties in use. If using Spring Boot or DefaultBatchConfiguration, configure the serializer through the appropriate extension point for that version instead of creating a second JobRepository.

DefaultExecutionContextSerializer is an implementation available in modern Spring Batch versions. If using another serializer, replace the bean with the appropriate implementation and verify that the data format is compatible with existing metadata.

Do not change the serializer in an environment that has executions needing restart without evaluating the context data already saved by the old serializer. The new serializer must be able to read the old data, or you need a controlled migration plan.

## 5. Choosing Data Types to Store in Context

Data types placed in ExecutionContext must be supported by the current serializer. With Java serialization, objects need to satisfy Serializable requirements and the entire related object graph must also be serializable. With a JSON serializer, values need an appropriate mapping and restoration mechanism.

Simple data types are usually easy to manage:

- String for file names, versions, or status codes.
- Long or Integer for IDs, offsets, and page numbers.
- Boolean for status flags.
- Date/time types explicitly supported by the serializer.
- Enums or simple value objects when a stable mapping rule is already in place.

Example:

~~~java
ExecutionContext context = stepExecution.getExecutionContext();

context.putString("input.file", inputFileName);
context.putLong("reader.lastCustomerId", lastCustomerId);
context.putInt("reader.page", currentPage);
context.putBoolean("validation.completed", true);
~~~

Complex object types require careful consideration:

~~~java
// Think carefully before storing a large business object.
context.put("customerAggregate", customerAggregate);
~~~

Business objects may contain large collections, JPA proxies, lazy relationships, connections, resources, or references to classes unsuitable for serialization. Instead of storing the whole object, store the ID or a few small values sufficient for the next Step to query the needed data again.

For example, instead of storing a Customer entity:

~~~java
context.putLong("customerId", customer.getId());
~~~

The next Step can use the ID to load the entity from the database. This approach keeps the context compact and avoids coupling metadata to the entire object structure of the domain model.

## 6. Common Serialization Errors

If the serializer cannot convert a value in the context into a representation, the metadata saving process may fail. With Java serialization, a common error is NotSerializableException when an object or a member of the object graph does not implement Serializable.

Common causes:

- Storing a custom object that does not support serialization.
- An object contains a non-serializable field.
- Storing a JPA entity with proxies or unsuitable lazy relationships.
- Storing an open stream, connection, thread, executor, or resource.
- Using a JSON serializer without a mapping for the data type.
- Deserialized data is no longer compatible with the current class.

Examples of what not to do:

~~~java
// Do not store open resources in ExecutionContext.
context.put("jdbcConnection", connection);
context.put("fileReader", bufferedReader);
context.put("executor", executorService);
~~~

These resources have their own lifecycle and cannot be restored merely by serializing an object reference. Store the resource identification info or the position to resume from, then reopen the resource in the ItemStream's open() callback.

When serialization fails, the error may appear at the moment JobRepository persists the context, not necessarily at the put() line that added the object. Therefore, a Step may process many items before encountering an error when the framework saves the checkpoint.

## 7. Compatibility Between Deployments

ExecutionContext can outlive a single application run. A Job that fails today may be restarted after the application has deployed a new version. Therefore, the context format and saved data types need to remain compatible across versions.

With Java serialization, class changes can affect deserialization capability. Certain structural changes or incompatible serialVersionUIDs can make old data unreadable.

With JSON, renaming properties, changing field types, changing enums, or changing polymorphic mapping rules can also prevent old contexts from restoring properly.

Some design principles:

1. Prefer storing simple, stable values instead of domain objects.
2. Use keys namespaced by component, e.g. customerReader.lastId.
3. Keep the meaning of keys stable across versions.
4. When format changes are needed, support reading the old format during a transition period or have a plan to handle old executions.
5. Do not rename classes stored in Java serialization without considering existing data.
6. Test restart using metadata created from the previous application version.

### Versioning Context Keys

If recovery logic changes, you can use versioned keys to identify the state format:

~~~java
private static final String CONTEXT_VERSION =
        "orderWriter.contextVersion";

private static final String LAST_ORDER_ID =
        "orderWriter.lastOrderId";

void saveState(ExecutionContext context, long lastOrderId) {
    context.putInt(CONTEXT_VERSION, 2);
    context.putLong(LAST_ORDER_ID, lastOrderId);
}
~~~

When opening the writer, the code can read the context version and handle the versions that the application still supports. This example illustrates how to organize keys; it does not replace a compatibility plan for the serializer or schema.

You should not remove old keys immediately when deploying a new version if old JobExecutions still need to be restarted. It may be necessary to keep logic that reads both old and new keys for a period of time.

## 8. Changing the Serializer When the Repository Already Has Data

The serializer is part of the storage format. If the application has written contexts using serializer A and then switches to serializer B, serializer B might not understand the old data.

Example:

~~~text
Old executions
    |
    v
Context saved in format A
    |
    | upgrade application / change serializer
    v
New application uses format B
    |
    v
Restart old execution
    |
    +--> B can read format A: can continue
    |
    +--> B cannot read format A: context restoration error
~~~

Before changing the serializer, determine:

- Whether there are failed or stopped JobInstances that need to be restarted.
- Whether there are any StepExecutions that need context restoration.
- Whether the new serializer can read the old data.
- Whether metadata needs to be converted or the old serializer should be kept until old executions finish.
- Whether application nodes running in parallel are using the same format.

Do not directly modify serialized strings in the BATCH_* tables using manual SQL. Doing so easily corrupts the format or metadata relationships. If migration is needed, use a controlled conversion tool, back up data, and test restore/restart on a copy of the repository.

An often easier operational strategy is to keep the compatible serializer while old executions remain, stop creating new executions using the old format, wait for old executions to complete or be handled according to policy, and only then remove support for reading the old format.

## 9. Context Size and Repository Performance

Every time the context is persisted, the data must be serialized and written to the metadata repository. The larger the context, the higher the CPU cost, database storage, backup, and query overhead.

Avoid storing:

- Lists of thousands or millions of items.
- Entire large JSON/XML payloads.
- File content or binary data.
- Entity graphs or large relational collections.
- Data that can be queried again from the business source.

Instead, store reference values:

~~~java
context.putString("staging.file", "/data/batch/staging/orders-8421.csv");
context.putLong("staging.batchId", 8421L);
context.putLong("reader.lastId", 95000L);
~~~

Large data should be stored in a business database, file, or object storage. ExecutionContext only holds an ID, path, or watermark sufficient to determine how to proceed.

Large context sizes can increase serialize/deserialize time on every save or restore, bloat metadata tables, and slow down cleanup/backup. Keeping the context small helps JobRepository focus on execution management.

## 10. Security of Serialized Data

Serialization is not encryption. If the context contains a password, API token, private key, or credentials, the serializer may write that value to metadata in a form that can be read or decoded depending on the format.

Do not store secrets in:

- Job ExecutionContext.
- Step ExecutionContext.
- Custom objects placed in the context.
- Exception messages or logs generated during serialization.

Store secrets in a secret manager and put only a non-sensitive reference in the context if a subsequent Step needs to look up the secret. Access to JobRepository should also be restricted since anyone who can read metadata can view persisted context values.

Database or disk encryption at rest is an additional layer of protection, not a replacement for the principle of not storing credentials in metadata. If an organization requires encrypting specific data in the context, configure and test an appropriate serializer or encryption layer, including readability on restart and key management.

## 11. JobParameters and ExecutionContext Are Not the Same

Both JobParameters and ExecutionContext are stored in JobRepository, but they serve different roles.

| Attribute | JobParameters | ExecutionContext |
|---|---|---|
| Purpose | Describes input of a JobInstance/JobExecution | Stores runtime state and checkpoints |
| Who usually creates it | Caller, scheduler, or JobLauncher | Reader, writer, Step, or Job logic |
| Can be updated while running? | Not used to update runtime state | Can be updated via context API |
| Role on restart | Keeps identifying parameters to recognize the same JobInstance | Restores saved position and state |
| Storage method | Parameter metadata by type and value | Serialized key/value via ExecutionContextSerializer |

Do not use JobParameters as a substitute for ExecutionContext for checkpoints. Conversely, do not use ExecutionContext to alter the identity of a JobInstance.

Also remember that non-identifying JobParameters can still be stored in metadata. The identifying flag only determines whether a parameter participates in identifying the JobInstance; it is not a security flag.

## 12. Serialization in Readers and Writers

Readers and writers can implement ItemStream to save state through ExecutionContext.

Example of a reader saving the last read ID:

~~~java
public class CustomerReader implements ItemStreamReader<Customer> {

    private static final String LAST_ID =
            "customerReader.lastId";

    private long lastId;

    @Override
    public void open(ExecutionContext context) {
        lastId = context.containsKey(LAST_ID)
                ? context.getLong(LAST_ID)
                : 0L;
    }

    @Override
    public Customer read() {
        // Read the next record after lastId from the data source.
        // Update lastId once the item is obtained.
        return loadNextCustomer();
    }

    @Override
    public void update(ExecutionContext context) {
        context.putLong(LAST_ID, lastId);
    }

    @Override
    public void close() {
        // Close resources if the reader opened any.
    }
}
~~~

When the Step needs to save a checkpoint, the framework calls update() so the reader puts its state into the Step ExecutionContext. JobRepository serializes the context according to the repository configuration.

A writer can use a similar approach if it needs to save the write position. However, writer state must match the committed target data. Do not just increment a counter in memory and save it; if the chunk rolls back, the counter might have advanced even though the target data was not confirmed.

When wrapping a reader or writer that implements ItemStream inside a delegate/composite, ensure the stream is registered properly so the open, update, and close callbacks are invoked.

## 13. Testing Serialization and Round-Trip

A serializer needs to be tested in both directions. A basic round-trip test can verify that values retain their exact types and contents after being serialized and then deserialized.

Illustrative example:

~~~java
@Test
void executionContextCanBeSerializedAndRestored() throws Exception {
    ExecutionContext original = new ExecutionContext();
    original.putString("source.version", "v4");
    original.putLong("reader.lastId", 8500L);
    original.putBoolean("validation.completed", true);

    ByteArrayOutputStream output = new ByteArrayOutputStream();
    serializer.serialize(original, output);

    ByteArrayInputStream input =
            new ByteArrayInputStream(output.toByteArray());
    Map<String, Object> restoredValues = serializer.deserialize(input);

    assertEquals("v4", restoredValues.get("source.version"));
    assertEquals(8500L, restoredValues.get("reader.lastId"));
    assertEquals(true, restoredValues.get("validation.completed"));
}
~~~

Specific method names and parameter types of ExecutionContextSerializer may vary by version; adjust the test according to the interface in use. The goal is to test round-trip using the exact serializer configured for the repository.

In addition to unit tests, you should have integration tests with JobRepository:

1. Create a JobExecution or StepExecution.
2. Put checkpoint values into ExecutionContext.
3. Persist the execution via the repository.
4. Read the execution/context back using the repository or appropriate query API.
5. Verify that keys, values, and data types are restored.
6. Simulate a restart using the saved context and verify the reader/writer resumes at the exact position.

If the application upgrades versions, keep metadata fixtures created by the previous version to test deserializing old data.

## 14. Checking Serialization Errors in Operations

When a Job fails while updating metadata, you need to determine whether the error comes from business logic, a transaction, or the serializer.

Some indicators:

- NotSerializableException when using Java serialization.
- Mapping errors or unsupported types with a JSON serializer.
- Deserialization errors because a class or schema has changed.
- Errors reading corrupted or truncated serialized data.
- Database write errors due to column size limits or transactions.

Investigation steps:

1. Identify the JobExecution and StepExecution that failed.
2. Check the root exception and the point where the framework is persisting ExecutionContext.
3. Identify the key/value newly added to the context in the chunk or Step.
4. Inspect the data type and object graph of that value.
5. Confirm the serializer configured at runtime.
6. Check the metadata schema and column limits of the repository.
7. Try serializing/deserializing a similar value using the same serializer in a test environment.
8. If the error appeared after a deployment, compare the format and classes between the version that created the context and the version reading it.

Do not log the entire context if it might contain sensitive data. When diagnosing, log key names and non-sensitive value types instead of printing the entire content.

## 15. Common Design Mistakes

**Assuming put() writes immediately to the database.** The context in memory is only persisted when the framework updates the repository according to the lifecycle.

**Storing non-serializable objects.** An object might contain resources or fields that do not support serialization. Store scalars or IDs instead.

**Storing large domain entities.** Entity graphs cause context bloat, class coupling, and may contain unsuitable proxies.

**Changing the serializer without considering old data.** Old executions may fail to restart if the new format cannot read the old representation.

**Modifying already serialized classes.** Java serialization may become incompatible after class or serialVersionUID changes.

**Treating JSON as self-compatible.** JSON still requires clear mapping, data types, and versioning policies.

**Storing secrets in the context.** Serializers are not a security mechanism; metadata can be queried or exported.

**Using the context as a large data store.** Large payloads increase repository cost and cause difficulties during backup/cleanup.

**Directly editing metadata tables.** Altering serialized context via SQL can break the format or ruin restart capability.

## 16. Process for Choosing and Managing a Serializer

When designing JobRepository, determine:

1. The Spring Batch version and the actual default serializer being used.
2. The data types that readers, writers, and Steps will put into the context.
3. Whether custom objects need to be stored or only scalars/references.
4. Whether the serializer can round-trip those values.
5. Whether the format remains compatible when the application upgrades.
6. Whether there are old JobExecutions needing restart after changing the serializer.
7. Whether the context is small enough and free of sensitive data.
8. Whether the database schema and column sizes are suitable.
9. Whether there are integration tests to persist, load, and restart with a real repository.
10. Whether there is a backup and migration plan if the metadata format changes.

Prefer keeping ExecutionContext small, stable, and easy to deserialize. Use an explicitly configured ExecutionContextSerializer, test round-trip, and maintain compatibility with metadata that still needs to be used.

Serialization allows Spring Batch to turn runtime state into durable metadata for JobRepository to save and restore on restart. When you store only necessary values, choose compatible data types, manage serializer changes in a planned manner, and protect the context as metadata, Jobs can recover reliably across runs and application deployments.

