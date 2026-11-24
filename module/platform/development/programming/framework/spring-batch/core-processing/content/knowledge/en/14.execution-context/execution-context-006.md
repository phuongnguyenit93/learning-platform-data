# Non-Serializable State

`ExecutionContext` is the state storage area that Spring Batch uses to resume work after a step or job stops or fails. A reader can save its last read position, a tasklet can save the key of the processed record, and the step can restore those values on restart.

When using `JobRepository` to store durable metadata, state in `ExecutionContext` must be converted into a form that the configured serializer can save and read back. If a non-serializable object is placed in the context, saving the checkpoint may fail. An object that looks simple can still be invalid if inside it holds a stream, connection, thread, or another non-serializable object.

The practical rule is to store only small, stable, and restorable state data; do not store open runtime resources. Store enough information to reopen the resource and continue from the committed point.

## 1. Why Does ExecutionContext Need Serialization?

`ExecutionContext` is a key/value map attached to a `JobExecution` or `StepExecution`. Spring Batch persists the context together with metadata so state can be restored when the application restarts or when a job is restarted.

```text
ItemReader / Tasklet / ItemStream
              |
              v
       ExecutionContext
       { lastId: 4200,
         inputFile: "orders.csv" }
              |
              v
       ExecutionContextSerializer
              |
              v
         JobRepository
              |
              v
      Store durable metadata
```

With JDBC `JobRepository`, the context needs to be serialized before being written to metadata tables. When restoring an execution, Spring Batch reads the saved data and deserializes it into values in the context.

The specific serializer depends on the version and batch infrastructure configuration. Standard JDBC configurations typically use a serializer based on Java serialization; applications can also configure a different serializer, such as a JSON-based serializer. Regardless of which serializer is used, every value must conform to that serializer's serialize/deserialize contract.

## 2. Where Do Non-Serializable Objects Cause Errors?

A common mistake is putting a runtime resource directly into the context:

```java
ExecutionContext context = stepExecution.getExecutionContext();
context.put("inputStream", new FileInputStream("orders.csv"));
```

`FileInputStream` represents an open file in the current process. It holds operating system resource state and is not checkpoint data suitable for serialization. When the repository attempts to save the context, the serializer may fail with a serialization error (for example, a root cause of `NotSerializableException` if using Java serialization).

The error does not necessarily occur right at the `put` line. `ExecutionContext` may accept the object into the map first; the error only appears when Spring Batch serializes the context to update metadata, usually at the step or chunk state-saving boundary. Therefore, logs may show the error occurring at commit or JobRepository update even though the code putting the object into the context appeared earlier.

Do not simply catch the serialization exception and continue the job. If the checkpoint is not saved, the job may fail to restore the correct position after restart.

## 3. Serializable Must Apply to the Entire Object Graph

With Java serialization, marking the outermost class `implements Serializable` is not enough. Every object referenced in the object graph must be serializable, except fields intentionally excluded that can be re-initialized after deserialization.

For example, the following class can still fail:

```java
public class ImportState implements Serializable {
    private String inputFile;
    private InputStream inputStream; // Not serializable
}
```

Even though `ImportState` implements `Serializable`, the `inputStream` field still cannot be serialized via standard Java serialization. A deeply nested field in an object can cause a similar error.

Cases typically unsuitable for direct storage:

- Open `InputStream`, `OutputStream`, `Reader`, `Writer`, or file handles.
- JDBC `Connection`, `Statement`, `ResultSet`, or transaction resources.
- JPA `EntityManager`, sessions, or persistence contexts.
- Active `Thread`, `ExecutorService`, locks, sockets, or HTTP clients.
- Spring beans, proxies, repositories, or service objects.
- Framework objects holding many runtime resources or complex circular references.
- Custom objects with non-serializable fields or overly large data.

Do not store an entire large entity graph just to remember a few attributes. Besides serialization risk, the data may become stale, contain unloaded lazy relationships, or bloat metadata.

## 4. Store Only Reconstructible Checkpoints

Instead of storing an open resource, store enough information to reopen the resource after restart. For example, for a file reader, store the path, line number or byte offset, along with a file checksum/identifier if needed to ensure the exact source.

```java
ExecutionContext context = stepExecution.getExecutionContext();
context.putString("inputFile", inputPath.toString());
context.putLong("lastProcessedLine", lastProcessedLine);
```

Values such as `String`, `long`, `int`, and `boolean` are suitable for simple checkpoints. If the serializer supports other data types, still prefer compact and stable representations.

When reopening the reader, use the saved path and position to create a new stream:

```java
public class ResumableFileReader implements ItemStreamReader<OrderRow> {

    private static final String LINE_KEY = "orders.lastProcessedLine";

    private final Path inputPath;
    private BufferedReader reader;
    private long lineNumber;

    public ResumableFileReader(Path inputPath) {
        this.inputPath = inputPath;
    }

    @Override
    public void open(ExecutionContext context) throws ItemStreamException {
        try {
            lineNumber = context.getLong(LINE_KEY, 0L);
            reader = Files.newBufferedReader(inputPath, StandardCharsets.UTF_8);

            for (long i = 0; i < lineNumber; i++) {
                if (reader.readLine() == null) {
                    throw new ItemStreamException("Checkpoint exceeds file length");
                }
            }
        } catch (IOException ex) {
            throw new ItemStreamException("Cannot open input file", ex);
        }
    }

    @Override
    public OrderRow read() throws Exception {
        String line = reader.readLine();
        if (line == null) {
            return null;
        }
        lineNumber++;
        return parse(line);
    }

    @Override
    public void update(ExecutionContext context) {
        context.putLong(LINE_KEY, lineNumber);
    }

    @Override
    public void close() throws ItemStreamException {
        try {
            if (reader != null) {
                reader.close();
            }
        } catch (IOException ex) {
            throw new ItemStreamException("Cannot close input file", ex);
        }
    }
}
```

The example illustrates the idea of `ItemStream`: `open` restores the position and opens a new resource, `update` saves the checkpoint, and `close` releases the resource. The `parse` method is the application's logic to convert a line into an `OrderRow`. For large files, you can use byte offsets or a built-in stateful reader instead of reading and skipping line by line on restart.

## 5. A Serializable Object Can Still Be a Bad Choice

An object implementing `Serializable` does not automatically become a good checkpoint. For example, a large DTO can serialize into a very large payload; an entity can carry unnecessary relationships; a class can change structure between two deployments.

Checkpoints should contain the minimal state needed to continue:

| Should not store | Should store |
|---|---|
| Open `BufferedReader` | File path and read position |
| JDBC `Connection` | Datasource/config name and last committed record key |
| A list of hundreds of thousands of entities | Next ID or pagination key |
| Spring service or repository bean | Input data needed to call the bean again after restart |
| Active HTTP response/client | Request ID or cursor issued by the service |
| An object containing both cache and runtime resources | Small checkpoint DTO containing only values to restore |

Values in the context should have bounded size. Context is stored in metadata; storing large data can increase table size, serialize/deserialize time, and backup costs.

## 6. Using a Small Checkpoint DTO When Grouping Multiple Values

When there are multiple related attributes, you can create a small checkpoint DTO. With Java serialization, the class and all fields need to be compatible with the serializer.

```java
public final class ImportCheckpoint implements Serializable {

    private static final long serialVersionUID = 1L;

    private final String sourceFile;
    private final long lastProcessedId;
    private final String sourceChecksum;

    public ImportCheckpoint(
            String sourceFile,
            long lastProcessedId,
            String sourceChecksum) {
        this.sourceFile = sourceFile;
        this.lastProcessedId = lastProcessedId;
        this.sourceChecksum = sourceChecksum;
    }

    public String sourceFile() { return sourceFile; }
    public long lastProcessedId() { return lastProcessedId; }
    public String sourceChecksum() { return sourceChecksum; }
}
```

Saving the DTO to the context:

```java
context.put("importCheckpoint", checkpoint);
```

The DTO above contains only strings and integers, so the object graph is simple. If using Java serialization, `serialVersionUID` helps control class identity compatibility across versions, though it does not guarantee all structural changes are compatible. When changing the class, test deserializing metadata created by the previous version.

For simple checkpoints, storing individual values with `putString`, `putLong`, or corresponding typed methods is usually easier to inspect and has less class coupling than storing custom objects.

## 7. Using transient Is Not a Way to Save Checkpoints

Java allows marking a field as `transient` to exclude that field from the serialization process:

```java
public class ImportState implements Serializable {
    private static final long serialVersionUID = 1L;

    private String inputFile;
    private transient InputStream inputStream;
}
```

This approach can avoid serialization errors for the `inputStream` field, but the stream will not be restored on deserialization. After restart, that field will be `null` and must be reopened from `inputFile` or another configuration.

Therefore, `transient` is only suitable for reconstructible resources with clear re-initialization logic. It does not help save internal stream state, read position, or buffers. States that need restoration must be stored separately as checkpoint values.

## 8. Distinguishing Job ExecutionContext and Step ExecutionContext

Spring Batch has contexts at two scopes:

| Context | Scope | Examples of suitable data |
|---|---|---|
| Job `ExecutionContext` | Shared at JobExecution level between steps in the same execution | Processing date, batch code, summary result needed for a later step |
| Step `ExecutionContext` | Specific to one StepExecution | Reader position, current page, step checkpoint |

Readers and `ItemStream` typically store their private state in the step context. A tasklet can also obtain the step context from `StepContribution` to store checkpoints:

```java
ExecutionContext context =
    contribution.getStepExecution().getExecutionContext();
context.putLong("lastProcessedId", lastProcessedId);
```

Do not put a reader's internal state into the job context just because you want other steps to see it. Choose the smallest scope necessary. Whether job context or step context, durably stored values must still meet serialization requirements.

## 9. Context Update Timing and Transactions

`ItemStream` provides the `open`, `update`, and `close` callbacks. Spring Batch calls `update` so the component writes its current state into `ExecutionContext` before step metadata is persisted at the checkpoint.

```text
Read and process chunk
       |
       v
ItemStream.update(context)
       |
       v
JobRepository saves ExecutionContext
       |
       v
Transaction commit
```

When business data and the repository use appropriate transaction resources, the checkpoint can be synchronized with the chunk commit. If they reside in different transaction managers or databases, consider the possibility that the two sides might not commit together.

Do not update the checkpoint to a new position before the corresponding portion of data is written successfully. If the checkpoint gets ahead of business data, restart may skip items that were not actually saved. If the checkpoint lags behind while data has committed, items may be reprocessed; therefore, writers should be idempotent or have unique business keys.

## 10. When Using a Custom Serializer

Spring Batch allows configuring an `ExecutionContextSerializer` for JobRepository. Another serializer can be chosen when an easily inspectable format, support for specific DTOs, or compatibility with system data conventions is needed.

When using a custom serializer, ensure:

- Symmetric serialization and deserialization for every data type actually stored.
- A compatibility strategy when upgrading classes or changing checkpoint structure.
- Allowing only data types controlled by the application; avoid deserializing untrusted data.
- Small payloads with a clear schema and no credentials or unnecessary sensitive data.
- Tests for reading old metadata with the new code version before deployment.

A JSON serializer can suit DTOs with a stable schema, though not every arbitrary Java object can be automatically converted to JSON and back. Clear type mapping, date/number formatting, and compatibility policies need to be configured.

Do not change the serializer between versions without a migration plan. Old metadata written by the previous serializer may not be readable by the new serializer, making old jobs unable to restart.

## 11. Class Evolution and New Version Deployments

Even when a class implements `Serializable`, modifying the class between runs can cause deserialization to fail or produce an object with a different meaning than the old version.

Common risks:

- Renaming the package or class stored in the context.
- Changing `serialVersionUID` or incompatible field structures.
- Changing the data type of a checkpoint field.
- Deleting a field that old restart logic still needs.
- Changing the meaning of a key in the context while keeping the key name.
- Deploying a new build that no longer contains the old class referenced by metadata.

For jobs that may run across multiple deployments, keep the checkpoint schema stable or explicitly versioned. A key such as `checkpoint.version` can be used to choose how to read/migrate state, while ensuring new code understands old executions that still need to restart.

Example saving checkpoint version:

```java
context.putInt("checkpoint.version", 2);
context.putLong("orders.lastProcessedId", lastProcessedId);
```

When changing structure, recovery code can check the version and convert from the old format if supported. For incompatible changes, let old JobInstances complete on the old version or build a controlled migration process.

## 12. How to Find the Cause of Serialization Failure

When a JobExecution or StepExecution fails while saving context, inspect the root exception and identify which key/value was just added or updated.

Investigation process:

1. Identify when the error occurs: during `put`, during `ItemStream.update`, or when `JobRepository` updates metadata.
2. Read the root exception and stack trace to identify the non-serializable class.
3. Check newly added values in both the job context and step context.
4. For custom DTOs, inspect all fields and nested referenced objects.
5. Confirm the actual serializer configured for JobRepository.
6. Replace runtime resources with scalar checkpoints or small restorable DTOs.
7. Test saving and reading context via the repository, then test restarting a representative execution.

You can log key names and class types before saving context in a debug environment, but do not log the full payload if it contains personal data, secrets, or sensitive business information.

## 13. Common Errors

| Error | Consequence | Resolution |
|---|---|---|
| Storing `InputStream` or `BufferedReader` | Serializer cannot save an open resource | Store path and read position; reopen resource in `open` |
| Storing JDBC connection or entity manager | Cannot serialize container-managed resources | Store ID/query key; acquire connection via datasource during execution |
| Marking only the outer class `Serializable` | Nested fields can still cause failures | Inspect the entire object graph |
| Marking a resource `transient` without re-initializing | Field becomes null after restart | Reconstruct the resource from checkpoint in lifecycle callback |
| Storing a large entity list | Metadata bloats, serialization slows, and data easily goes stale | Store only necessary keys or cursors |
| Incompatible checkpoint class change | Cannot deserialize old metadata | Maintain compatibility or version/migrate checkpoints |
| Changing serializer without migrating metadata | Old jobs may fail to restart | Have a conversion plan and test reading old metadata |
| Putting secrets into the context | Secrets may persist in metadata/backups/logs | Store secret reference, fetch credentials from secret manager |

## 14. Checklist for Designing Restorable State

When defining state for a reader, tasklet, or step, determine:

1. Which state truly needs to survive after the process terminates?
2. Can the state be represented by strings, numbers, booleans, IDs, or stable cursors?
3. If using a DTO, are all fields and nested objects compatible with the serializer?
4. Can runtime resources be reopened from checkpoint information?
5. Is the checkpoint updated at the appropriate commit boundary?
6. Can the new code version read the context of old executions?
7. Does the context contain large payloads, secrets, or unnecessary data?
8. Are there integration tests for saving, reading, and restarting through a real JobRepository?

## Conclusion

State in `ExecutionContext` must be compatible with the serializer used by `JobRepository`. An outermost object implementing `Serializable` can still fail if the object graph contains streams, connections, threads, or non-serializable fields. Errors often appear only when Spring Batch saves the context at a checkpoint, rather than right when adding the value to the map.

Store small and stable checkpoint data such as IDs, offsets, file names, or versions; reopen resources in the reader/tasklet lifecycle instead of storing active resources. If using custom DTOs or custom serializers, manage compatibility across deployments and test deserializing old metadata before relying on restart in production.
