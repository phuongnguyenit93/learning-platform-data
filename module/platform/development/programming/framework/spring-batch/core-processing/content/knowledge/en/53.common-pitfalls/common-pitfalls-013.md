# Not Checking ExecutionContext in Spring Batch: Common Checkpoint and Restart Pitfalls

## 1. Why Must ExecutionContext Be Checked?

In Spring Batch, **`ExecutionContext` is where state is stored so a job or step can track progress and resume after stopping or failing**. It is neither an arbitrary global variable nor proof that business work committed successfully.

Suppose `importInvoices` reads a 1-million-line file. After the step successfully writes 400,000 rows, the process loses connectivity and stops. On restart, the reader must know the **last safe position** so it neither re-imports the entire file nor skips uncommitted data. Spring Batch supports this via `ItemStream` and `ExecutionContext`, yet the mechanism is reliable only when the application saves and **validates** state properly.

The "not checking ExecutionContext" pitfall often appears as:

- Reading with `getInt("offset")` without knowing whether the key exists or has the expected type.
- Treating a default of `0` as safe even when the job is restarting and the checkpoint went missing.
- Confusing **JobExecution context** with **StepExecution context**.
- Renaming readers/keys across application versions and resuming old jobs without migration.
- Saving lines read without verifying the file/data source is still the same version.
- Advancing the read position too early or persisting checkpoints manually outside transaction boundaries.
- Storing large or non-serializable objects, causing persistence/restart failures.
- Failing to check checkpoints and target data after a step rollback.

Consequences can be worse than an exception: **dropped records**, **duplicate processing**, **out-of-order writes**, **reading the wrong file**, or **reporting a job `COMPLETED` when output is incomplete**.

**Lesson goal:** understand the `ExecutionContext` lifecycle, distinguish job vs. step scopes, validate checkpoints before using them, implement a simple restartable reader, and test failure/restart scenarios. Examples use Spring Batch **5.2.x**, Spring Boot **3.x**, and Java **17+**; when using other versions, match packages and APIs accordingly.

## 2. ExecutionContext Is Not One Single Scope

Spring Batch has two important `ExecutionContext` scopes:

| Scope | Where obtained? | Primary purpose |
|---|---|---|
| **StepExecution context** | `stepExecution.getExecutionContext()` | State/checkpoint for **one step**: reader offset, next page, cursor, processing progress |
| **JobExecution context** | `jobExecution.getExecutionContext()` | Data shared across **steps in the same job execution**, such as an output file path produced by an earlier step |

Both are key–value maps, yet **they have different lifecycles and persistence timing**.

### 2.1. Runtime Structure

```text
JobInstance: importInvoices + businessDate=2025-05-12
    |
    +-- JobExecution id=501
            |
            +-- Job ExecutionContext
            |     app.source.fileId = "invoices-20250512-v3"
            |     app.validation.approved = true
            |
            +-- StepExecution id=1001: downloadStep
            |      Step ExecutionContext
            |        app.download.lastPart = 8
            |
            +-- StepExecution id=1002: importStep
                   Step ExecutionContext
                     app.invoiceReader.nextIndex = 400000
                     app.invoiceReader.sourceId = "invoices-20250512-v3"
```

On restart, Spring Batch creates a **new `JobExecution`** for the same `JobInstance` and uses persisted metadata from the prior execution to restore appropriate states. Never assume in-memory Java objects or bean map fields survive across a restart.

### 2.2. Both Contexts Persist at Different Times

Under chunk-oriented processing:

- **StepExecution context** is updated/persisted by Spring Batch at checkpoint boundaries, typically **before chunk commit** when `ItemStream`s receive `update(...)`.
- **JobExecution context** is normally persisted at **step boundaries**, making it suitable for passing data between steps—not for updating a cursor after every item in a chunk.
- Data in `ExecutionContext` must pass through `JobRepository` **serialization/deserialization**; plain Java bean fields do not automatically become durable state.

When running parallel or partitioned steps, each `StepExecution` has its own context. Two steps can both set `"offset"` without sharing a single offset counter.

**Scope selection rule:** anything needed to **restart within the same step** usually belongs in step context; anything needed by **a later step from an earlier step** can use job context with an explicit handoff mechanism.

## 3. ItemStream Lifecycle: open, read, update, close

`ItemReader` defines how to read an item. To save and restore state, a reader can implement `ItemStream` or `ItemStreamReader`:

```java
import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.ItemStreamReader;

public class ExampleReader implements ItemStreamReader<String> {

    @Override
    public void open(ExecutionContext executionContext) {
        // Restore checkpoint when starting/restarting the step.
    }

    @Override
    public String read() throws Exception {
        // Return item or null at end of data.
        return null;
    }

    @Override
    public void update(ExecutionContext executionContext) {
        // Store appropriate state when requested by framework.
    }

    @Override
    public void close() {
        // Release resources.
    }
}
```

Typical flow:

```text
Step starts
    |
    v
ItemStream.open(step ExecutionContext)
    |
    v
read -> process -> write (multiple items in chunk)
    |
    v
ItemStream.update(step ExecutionContext)
    |
    v
Persist checkpoint / commit chunk
    |
    v
Repeat next chunk
    |
    v
ItemStream.close()
```

This simplified diagram illustrates the checkpoint concept and does not imply every listener or metadata write follows one rigid order across all failures/transaction managers. Key takeaway: **finishing reading an item does not mean a durable checkpoint already exists for that item**.

### 3.1. Updating a Reader Field Alone Is Not Enough

The following is not restartable:

```java
public class VolatileReader implements ItemReader<String> {

    private int nextIndex;

    @Override
    public String read() {
        if (nextIndex >= items.size()) {
            return null;
        }
        return items.get(nextIndex++);
    }
}
```

`nextIndex` exists only in RAM. A JVM restart instantiates a fresh reader with `nextIndex=0`; if the target already committed 400,000 items, the job can reprocess the entire beginning.

Adding `ItemStream`, persisting checkpoints, and designing an idempotent writer together solve the full problem.

### 3.2. Do Not Manually Persist Durable State on Every Read

Another anti-pattern:

```java
public String read() {
    String item = loadNext();
    saveOffsetToSeparateDatabaseImmediately();
    return item;
}
```

If the position is written to a separate database **before the item is committed by the writer**, and the writer then fails, restart may skip an item that was never written successfully.

Checkpoints should align with appropriate transaction boundaries; if state is stored outside `JobRepository`, synchronize transactions and recovery between state and side effects rather than "saving offsets early just in case".

## 4. Reading ExecutionContext Without Checking: A Very Common Mistake

Example:

```java
// Fragile pattern:
int nextIndex = stepExecution
        .getExecutionContext()
        .getInt("nextIndex");
```

Hidden assumptions inside:

1. Key `nextIndex` already exists.
2. Value was stored with type `int`.
3. Value is non-negative.
4. Value does not exceed the source element count.
5. Key belongs to the right reader/step.
6. Value was written from the same input version.
7. If the key is absent, starting from the beginning is safe.

Any broken assumption can cause errors or data loss. **Never treat a bare `getInt(...)` call as checkpoint validation.**

### 4.1. Checking Existence and Data Type

`ExecutionContext` supports `containsKey(...)` and typed methods like `putInt/getInt`, `putLong/getLong`, and `putString/getString`.

```java
ExecutionContext context = stepExecution.getExecutionContext();

if (!context.containsKey("app.reader.nextIndex")) {
    // Must distinguish a fresh run from a missing checkpoint.
}

Object raw = context.get("app.reader.nextIndex");

if (!(raw instanceof Integer nextIndex)) {
    throw new IllegalStateException(
            "Checkpoint type is invalid");
}

if (nextIndex < 0) {
    throw new IllegalStateException(
            "Checkpoint index cannot be negative");
}
```

Checking the raw type with `get(...)` before calling typed getters gives clear errors instead of assuming the serializer always produces the expected type. If an old version wrote `Long` while new code expects `Integer`, apply explicit migration rules or reject restart rather than silently casting.

### 4.2. Distinguishing a Fresh Run from a Restart

An empty context is normal on the **first run**. Yet during a **restart** when a checkpoint should exist, defaulting `nextIndex=0` can cause the job to re-read everything.

Do not blindly write:

```java
// Dangerous if checkpoint is lost on restart:
int nextIndex = context.containsKey(KEY)
        ? context.getInt(KEY)
        : 0;
```

everywhere without knowing what missing state means. Distinguish:

- **Fresh run**: context has no checkpoint yet; starting at 0 is valid.
- **Restart where the step never checkpointed**: starting from 0 can be valid if the writer is idempotent and transaction boundaries are clear.
- **Restart where the step already committed many chunks**: a missing checkpoint is an anomaly; do not silently re-read or jump to an arbitrary position.

A practical approach is saving state version, source ID, and cursor together after the first checkpoint; if **some keys exist without the full set**, fail fast. For strict guarantees, combine `JobExplorer`/prior execution history to distinguish a state-less restart. The next section shows consistent validation code.

## 5. Clear Key Naming and State Versioning

`ExecutionContext` is a shared map within its step/job scope. Generic names like `"count"`, `"page"`, or `"offset"` easily collide when multiple `ItemStream`s or listeners share the context.

Prefer namespaced keys:

```text
app.invoiceReader.stateVersion
app.invoiceReader.sourceId
app.invoiceReader.nextIndex

app.paymentReader.stateVersion
app.paymentReader.lastTransactionId

app.report.outputFileId
```

You do not need to stuff `jobExecutionId` into every key: each execution already has its own context. However, namespace by **component** so two readers never accidentally share a key.

### 5.1. Versioning the Checkpoint Schema

A checkpoint might have been written by an earlier code version:

```text
Version 1:
  app.invoiceReader.nextIndex = 400000

Version 2:
  app.invoiceReader.lastOrderId = "INV-400000"
  app.invoiceReader.sourceVersion = "etag-123"
```

If v2 code simply calls `getString("lastOrderId")` without checking version, it can start at the wrong position or throw vague errors.

Persist a `stateVersion` and pick one policy:

- Accept only the current version.
- Convert older versions to the new version via a tested migration function.
- Reject restart and require a safe reprocess workflow.

**Never treat renaming a key as a harmless refactor**: it can break restartability for jobs paused before deployment.

## 6. Example: Checkpoint Reader with Full Validation

Let us build a reader for an immutable list where elements are accessed by index. Persisted state includes:

- `stateVersion=1` to interpret data structure.
- `sourceId` to verify input is **the exact same source/version**.
- `nextIndex` as the next item position.

`sourceId` must bind to an identifier **stable across restarts**, such as an object-storage version or file checksum. Never compute `sourceId` from `LocalDate.now()` or a filename that can be reused with different content.

### 6.1. Checkpoint Management Class

```java
import org.springframework.batch.item.ExecutionContext;

public final class InvoiceCheckpoint {

    public static final String VERSION =
            "app.invoiceReader.stateVersion";

    public static final String SOURCE_ID =
            "app.invoiceReader.sourceId";

    public static final String NEXT_INDEX =
            "app.invoiceReader.nextIndex";

    private static final int CURRENT_VERSION = 1;

    private InvoiceCheckpoint() {
    }

    public static int restore(
            ExecutionContext context,
            String expectedSourceId,
            int inputSize) {

        if (expectedSourceId == null || expectedSourceId.isBlank()) {
            throw new IllegalArgumentException(
                    "Expected source identity is required");
        }

        if (inputSize < 0) {
            throw new IllegalArgumentException(
                    "inputSize must not be negative");
        }

        boolean hasVersion = context.containsKey(VERSION);
        boolean hasSource = context.containsKey(SOURCE_ID);
        boolean hasIndex = context.containsKey(NEXT_INDEX);

        if (!hasVersion && !hasSource && !hasIndex) {
            // Safe only when this is genuinely initial state.
            return 0;
        }

        if (!hasVersion || !hasSource || !hasIndex) {
            throw new IllegalStateException(
                    "Checkpoint is incomplete");
        }

        Object versionValue = context.get(VERSION);

        if (!(versionValue instanceof Integer version)
                || version != CURRENT_VERSION) {
            throw new IllegalStateException(
                    "Unsupported checkpoint version");
        }

        Object sourceValue = context.get(SOURCE_ID);

        if (!(sourceValue instanceof String storedSourceId)
                || !expectedSourceId.equals(storedSourceId)) {
            throw new IllegalStateException(
                    "Input source differs from checkpoint");
        }

        Object indexValue = context.get(NEXT_INDEX);

        if (!(indexValue instanceof Integer nextIndex)
                || nextIndex < 0
                || nextIndex > inputSize) {
            throw new IllegalStateException(
                    "Invalid checkpoint nextIndex");
        }

        return nextIndex;
    }

    public static void save(
            ExecutionContext context,
            String sourceId,
            int nextIndex) {

        context.putInt(VERSION, CURRENT_VERSION);
        context.putString(SOURCE_ID, sourceId);
        context.putInt(NEXT_INDEX, nextIndex);
    }
}
```

Checking **completeness**, **types**, **version**, **source identity**, and **cursor bounds** together catches metadata that cannot be restored safely early.

**Limitation to understand:** if all three keys are absent, the method returns `0` to support the initial run. The method **cannot tell by itself** whether this is a restart of a step that previously committed. For strict guarantees, callers must add an execution-history check before accepting empty state, or leverage standard Spring Batch readers with proven checkpointing.

### 6.2. Reader Using the Validated Checkpoint

```java
import java.util.List;

import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.ItemStreamReader;

public final class RestartableInvoiceReader
        implements ItemStreamReader<String> {

    private final List<String> invoices;
    private final String sourceId;

    private int nextIndex;

    public RestartableInvoiceReader(
            List<String> invoices,
            String sourceId) {

        this.invoices = List.copyOf(invoices);
        this.sourceId = sourceId;
    }

    @Override
    public void open(ExecutionContext executionContext) {
        nextIndex = InvoiceCheckpoint.restore(
                executionContext,
                sourceId,
                invoices.size()
        );
    }

    @Override
    public String read() {
        if (nextIndex >= invoices.size()) {
            return null;
        }

        return invoices.get(nextIndex++);
    }

    @Override
    public void update(ExecutionContext executionContext) {
        InvoiceCheckpoint.save(
                executionContext,
                sourceId,
                nextIndex
        );
    }

    @Override
    public void close() {
        // No file descriptors or connections held in this example.
    }
}
```

This reader is an **illustrative state/checkpoint sample** only. It assumes:

1. The input list and element ordering **never change**.
2. `sourceId` genuinely binds to input content/version.
3. Only one execution uses a reader instance at a time.
4. `ItemStream.update(...)` is invoked by the framework under the step's checkpointing.
5. Step writer and transactions are properly configured.

Do not use this reader directly over continuously mutating sources, or share one instance in a multi-threaded step, without adding synchronization and snapshotting.

### 6.3. Declaring a Separate Bean Per StepExecution

```java
import java.util.List;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.ItemStreamReader;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;

@Bean
@StepScope
ItemStreamReader<String> invoiceReader(
        @Value("#{jobParameters['sourceId']}") String sourceId) {

    List<String> input = List.of(
            "INV-001",
            "INV-002",
            "INV-003",
            "INV-004"
    );

    return new RestartableInvoiceReader(input, sourceId);
}
```

In production, `List.of(...)` is replaced by a source pinned to `sourceId`: an immutable file, staging snapshot, or object-storage version. `@StepScope` ties the reader instance to its step execution rather than sharing cursor state on a singleton bean.

To participate in lifecycle and checkpointing, Spring Batch must recognize the reader as an `ItemStream`. When passed **directly** to `StepBuilder.reader(...)` with a bean type exposing `ItemStreamReader`, the framework registers its lifecycle. If hidden behind a delegate/composite reader/writer and unregistered, add `.stream(delegate)` appropriately.

## 7. Unregistered ItemStream Delegate Pitfall

A subtle bug: a custom reader sits inside a wrapper implementing `ItemReader`, while the wrapper does not implement `ItemStream` and fails to call `open/update/close` on the delegate.

Example:

```java
public final class MaskingReader
        implements ItemReader<String> {

    private final ItemStreamReader<String> delegate;

    public MaskingReader(ItemStreamReader<String> delegate) {
        this.delegate = delegate;
    }

    @Override
    public String read() throws Exception {
        String value = delegate.read();
        return value == null ? null : mask(value);
    }

    private String mask(String value) {
        return value.replaceAll("\\d", "*");
    }
}
```

If `MaskingReader` is the step's direct reader, the framework only sees an `ItemReader`. The delegate may never receive `open(...)` or `update(...)`, leaving state unpersisted.

Configuration showing how to register the delegate:

```java
@Bean
Step maskedStep(
        JobRepository repository,
        PlatformTransactionManager tx,
        MaskingReader maskingReader,
        ItemStreamReader<String> checkpointReader,
        ItemWriter<String> writer) {

    return new StepBuilder("maskedStep", repository)
            .<String, String>chunk(100, tx)
            .reader(maskingReader)
            .writer(writer)
            .stream(checkpointReader)
            .build();
}
```

`checkpointReader` must be **the exact delegate instance** invoked by `maskingReader`; creating two separate instances causes the framework to save state on an object not actually reading data.

Another option is having the wrapper implement `ItemStreamReader` and forward all `open/update/close` calls. Avoid both forwarding manually and registering the same delegate twice if that triggers duplicate lifecycle calls.

## 8. Reading from Job Context While Writing to Step Context — or Vice Versa

The two contexts can share identical key names yet remain completely separate:

```java
ExecutionContext stepContext =
        stepExecution.getExecutionContext();

ExecutionContext jobContext =
        stepExecution.getJobExecution().getExecutionContext();

stepContext.putString("app.report.outputPath", "/data/report.csv");

// Logic bug: reading from jobContext where the key does not exist.
String output = jobContext.getString("app.report.outputPath");
```

In some API versions, reading a missing key throws an exception; in other code, using a default masks the bug. **Determine each key's scope** rather than blindly "checking the other context" when data is missing.

### 8.1. Passing Values Between Steps via JobExecutionContext

Suppose `generateReport` produces a file and `sendReport` needs its path:

```text
generateReport (StepExecutionContext)
    |
    | promote key per rule
    v
JobExecutionContext
    |
    v
sendReport (reads promoted key)
```

Spring Batch provides `ExecutionContextPromotionListener`:

```java
import org.springframework.batch.core.listener.ExecutionContextPromotionListener;
import org.springframework.context.annotation.Bean;

@Bean
ExecutionContextPromotionListener reportPathPromotion() {
    ExecutionContextPromotionListener listener =
            new ExecutionContextPromotionListener();

    listener.setKeys(new String[] {
            "app.report.outputPath"
    });

    listener.setStatuses(new String[] {
            "COMPLETED"
    });

    listener.setStrict(true);

    return listener;
}
```

Register the listener on the **data-producing step**:

```java
@Bean
Step generateReportStep(
        JobRepository repository,
        PlatformTransactionManager tx,
        Tasklet generateReportTasklet,
        ExecutionContextPromotionListener reportPathPromotion) {

    return new StepBuilder("generateReportStep", repository)
            .tasklet(generateReportTasklet, tx)
            .listener(reportPathPromotion)
            .build();
}
```

Example tasklet writing the value to step context:

```java
@Override
public RepeatStatus execute(
        StepContribution contribution,
        ChunkContext context) {

    String output = generateReportAndReturnPath();

    contribution.getStepExecution()
            .getExecutionContext()
            .putString("app.report.outputPath", output);

    return RepeatStatus.FINISHED;
}
```

Here `generateReportAndReturnPath()` is an illustrative business method. After the step succeeds, the promotion listener copies the selected key to job context for the next step to read:

```java
@Bean
@StepScope
Tasklet sendReportTasklet(
        @Value("#{jobExecutionContext['app.report.outputPath']}")
        String outputPath) {

    return (contribution, context) -> {
        if (outputPath == null || outputPath.isBlank()) {
            throw new IllegalStateException(
                    "Missing report output path in job context");
        }

        sendReport(outputPath);
        return RepeatStatus.FINISHED;
    };
}
```

`sendReport(...)` is an application-defined business method, not a Spring Batch API. This example shows that **the downstream step must still validate the promoted value** instead of falling back to a default path that might send the wrong report.

**Note:** `ExecutionContextPromotionListener` is not a message bus and does not automatically sync state across different jobs. It operates within a single job's lifecycle, provided the listener is registered and the step status matches.

## 9. ExecutionContext Does Not Replace JobParameters

Another design flaw is putting identifying input details into context while omitting them from `JobParameters`.

For example, a file-import job is launched with:

```text
jobName=importInvoices
run.id=123
```

Then inside the step:

```java
stepExecution.getExecutionContext()
        .putString("inputFile", "/data/invoices-20250512.csv");
```

On restart, the job definition or environment may no longer know **which file** is the official input for that job instance. Code might even pick the "latest" file and resume at the old file's offset.

Conversely, a clear design:

```text
JobParameters (identifying):
  businessDate = 2025-05-12
  sourceId     = invoices-20250512-v3

Step ExecutionContext (checkpoint):
  app.invoiceReader.sourceId   = invoices-20250512-v3
  app.invoiceReader.nextIndex  = 400000
  app.invoiceReader.stateVersion = 1
```

`JobParameters` defines the data/intent of a `JobInstance`. `ExecutionContext` records **processing progress** within that intent. Both must be cross-checked and cannot substitute for one another.

### 9.1. Identifying Parameters and Restart

Adding a new identifying `run.id` on every retry makes Spring Batch create a **different JobInstance** instead of restarting the old one; checkpoints from the prior instance do not carry over.

When resuming a `FAILED` or `STOPPED` job, use the restart mechanism with the same job instance's identifying parameters. Also check writer idempotency since prior chunks may have committed before the failure.

## 10. Checking Input Fingerprints or Source Versions

Merely checking `nextIndex <= inputSize` is not enough.

Suppose:

```text
Execution 501:
  file = invoices.csv
  lines 1..500,000 content = version A
  checkpoint = nextIndex 400,000

Before restart:
  invoices.csv is overwritten with version B
  total line count is still 500,000
```

Dataset size validation **fails to detect** the change. Restart could skip 400,000 lines of version B or mix half of A with half of B.

Safeguards:

- **Object-storage version ID**: read the exact locked object version.
- **Whole-file checksum/hash**: compare checksums at launch and restart when cost permits.
- **Immutable staging table**: snapshot data under `importId`; reader queries only that snapshot.
- **Database snapshot/cutoff**: pin business scope and query ordering.
- **Source sequence/version**: if an API provides a stable snapshot ID.

**Do not use file modification timestamps as the sole indicator** in high-assurance systems; timestamps can change or lack resolution. `sourceId` should bind to a real data version.

### 10.1. Do Not Store Large Payloads in ExecutionContext

To avoid re-reading a file, someone might store an entire 100,000-record list in context:

```java
// Do not do this:
context.put("allInvoices", hundredThousandInvoices);
```

This bloats metadata, may break serialization on custom objects, and adds heavy overhead on every checkpoint. Instead:

```text
JobParameters:
  sourceId=invoices-20250512-v3

Step ExecutionContext:
  nextIndex=400000
  cursorVersion=1
```

Raw data belongs in an appropriate durable source; context holds only small state sufficient to relocate the processing position.

## 11. Data Types and Serialization: Do Not Store Arbitrary Objects

`ExecutionContext` can hold key–values, yet not every Java object can be saved and restored safely via `JobRepository`.

Unsuitable examples:

```java
context.put("httpClient", new HttpClient(...));
context.put("jdbcConnection", connection);
context.put("openInputStream", inputStream);
```

An HTTP client, JDBC connection, or open stream is a runtime resource that cannot be validly restored in a new JVM. Serialization can fail, or a restored value becomes meaningless.

Prefer:

- `String` for source IDs, small cursor tokens, and enum codes.
- `int`/`long` for offsets, page indices, and versions.
- `boolean` for a status flag with clear semantics.
- Timestamps as ISO strings or a representation supported by the application's serialization policy.
- Complex objects require compatible serializers and clear migration policies; normally avoid them.

### 11.1. Do Not Confuse getInt and getLong

```java
// Old writer version:
context.putLong("app.reader.offset", 400000L);

// New reader version must not assume Integer type:
Object rawOffset = context.get("app.reader.offset");

if (!(rawOffset instanceof Long offset)) {
    throw new IllegalStateException("Unexpected offset type");
}
```

If converting from `long` to `int`, verify `offset` falls within `Integer.MIN_VALUE..MAX_VALUE` and has valid semantics before casting. Never cast a `Long` directly to `Integer`.

### 11.2. Protecting Sensitive Data

Never store access tokens, passwords, secret keys, or sensitive payloads in `ExecutionContext`. Metadata may be persisted to the database and appear in operational tools, backups, or dumps.

If a step needs to call an API on restart, store a non-sensitive **configuration/secret reference identifier** and fetch fresh credentials from a secure secret manager rather than checkpointing old tokens in context.

### 11.3. Changing Serializers and Library Versions

`ExecutionContext` serialization in `JobRepository` depends on Spring Batch and serializer configuration. Upgrading the framework or swapping serializers can make old checkpoint data unreadable.

Before changing serializers:

1. Check whether any `FAILED`/`STOPPED` jobs are awaiting restart.
2. Test reading context data written by the old version.
3. Prepare a migration or handling strategy for legacy jobs.
4. Test restart against a copy of real metadata.
5. Never manually edit serialized strings directly in the database without a verified tool/procedure.

## 12. Validate Context Across the Lifecycle, Not Just Per Item

Place checkpoint validation at the right points:

| Timing | What to check? | Response |
|---|---|---|
| **Before job launch** | `JobParameters`, source ID, business date, source read permissions | Reject invalid requests |
| **ItemStream.open** | Key existence/type, state version, source identity, cursor range | Fail fast if checkpoint cannot restore safely |
| **During read** | Whether item matches data contract; how cursor advances | Process/skip/fail per policy |
| **ItemStream.update** | Whether state about to be saved is valid and durable | Write a small, consistent checkpoint |
| **After chunk commit** | Writer result, item count, side-effect control | Reconcile/metrics; avoid assuming state = data commit |
| **Between steps** | Promoted key exists, actual output is ready | Block downstream if missing |
| **Before restart** | Prior execution, source, checkpoints, idempotency | Controlled recovery |

**Do not scatter "if key is missing, just continue" checks everywhere.** Define a clear policy: which keys are optional, which are mandatory, and why.

### 12.1. Fail Fast Beats Silently Reading Wrong Data

If a reader is expected to resume at position 400,000 yet context holds `-1`, silently resetting it to `0` turns a detectable metadata error into a full re-import of all data.

```java
if (checkpointIndex < 0 || checkpointIndex > inputSize) {
    throw new IllegalStateException(
            "Checkpoint is invalid; manual recovery required");
}
```

After failing, operators can inspect the source ID, metadata, and committed output to decide whether to restart or rebuild staging. For critical data, **refusing an unverifiable restart** is usually safer than completing with corrupt data.

## 13. Restart and Transactions: Checkpoints Must Stay Consistent with the Writer

`ExecutionContext` does not guarantee **exactly once** for every side effect. It is a state mechanism working alongside transactions and readers/writers.

Consider two chunks:

```text
Chunk 1:
  read INV-001 ... INV-100
  write 100 invoices
  ItemStream.update(nextIndex=100)
  commit

Chunk 2:
  read INV-101 ... INV-200
  write throws error
  transaction rolls back
  no commit for chunk 2

Restart:
  restore committed checkpoint (nextIndex=100)
  re-read INV-101...
```

If the writer shares the step-managed JDBC transaction, uncommitted changes of chunk 2 roll back with the transaction. However, if the writer sends emails, calls HTTP APIs, or writes files in ways **that do not roll back with the database transaction**, those side effects may already have occurred and will repeat on retry/restart.

### 13.1. Do Not Treat Checkpoints as Proof of Business Commit

Do not write:

```java
if (context.getInt("nextIndex") == 200) {
    // Wrong: concluding 200 invoices committed across all systems.
}
```

Verify target data by business key, transaction logs, or outbox/inbox when high consistency is required. `writeCount` and `readCount` on `StepExecution` are also Batch counters, not a substitute for verifying actually committed database rows.

### 13.2. Idempotent Writers Are an Additional Safeguard

If records are keyed by `invoiceId`, the database table can enforce `UNIQUE(invoice_id)` or conditional versioned upserts to prevent duplicate inserts on retry.

```sql
CREATE TABLE invoices (
    invoice_id VARCHAR(80) PRIMARY KEY,
    amount NUMERIC(18, 2) NOT NULL
);
```

Depending on the domain, a writer may use `INSERT ... ON CONFLICT DO NOTHING`, or check payload conflicts to reject if the same `invoiceId` arrives with a different amount. **Never use `DO NOTHING` to mask every data conflict.**

### 13.3. Never Manually Edit ExecutionContext in the Database

Spring Batch maintains `BATCH_STEP_EXECUTION_CONTEXT` and `BATCH_JOB_EXECUTION_CONTEXT`. Editing serialized `SHORT_CONTEXT`/`SERIALIZED_CONTEXT` columns directly can corrupt data or leave keys inconsistent.

If recovery from corrupted metadata is required, follow a controlled procedure with backups, source/output reconciliation, and migration tooling. Never manually copy context from another execution just because two jobs share the same name.

## 14. Keys in StepExecutionContext Do Not Automatically Appear in JobExecutionContext

This is a common pitfall when one step produces a file and the next step wants to read it.

```text
Step A:
  stepContext["reportPath"] = "/data/report.csv"

Step B:
  jobContext["reportPath"]  -> key absent
```

Reason: the two contexts are **two differently scoped maps**. Spring Batch does not automatically copy every key from step context to job context. You need an explicit strategy such as `ExecutionContextPromotionListener` or writing to job context at a properly designed point.

Even after promotion:

- Keys are copied only when the listener runs and the status policy matches.
- Step B must validate the value.
- File paths or object IDs must be checked for existence/version when read.
- If Step A completed in an earlier execution and Step B is restarted, verify the job context was properly restored.

**Never use a default like `"/tmp/report.csv"` to mask missing promotion.** You could accidentally send a report from a different business date.

## 15. Common Mistakes with Keys, Types, and Scopes

| Mistake | Manifestation | Consequence | Prevention |
|---|---|---|---|
| Omitting `containsKey`/type checks | Exceptions or wrong defaults | Wrong restart offset | Validate in `open` |
| Using `getInt` on a `long` value | Type error | Job fails after upgrade | Stable schema types / migration |
| Renaming keys after deploy | Keys "disappear" | Re-reads data | Version checkpoints and migrate |
| Overly generic keys like `offset` | Another component overwrites | Corrupted checkpoint | Namespaced keys |
| Using Job context instead of Step context | Reader checkpoint not found | Restarts from beginning | Use the right scope |
| Not promoting output between steps | Next step cannot find file | Flow fails or falls back to default | Promotion listener + validation |
| Not registering delegate `ItemStream` | `open/update` never called | No checkpoint | `.stream(delegate)` or forward lifecycle |
| Storing whole Lists/Streams/Connections | Serializer errors, bloated metadata | Cannot restart | Store only IDs and small cursors |
| Storing secrets/tokens | Metadata exposes credentials | Security risk | Secret manager, non-sensitive references |
| Not verifying source version | Offset points into changed file | Lost/mismatched records | Immutable source/version/checksum |
| Writing offset before writer commits | Checkpoint moves ahead of written data | Skipped items | Follow transaction/checkpoint lifecycle |
| Using `readCount` as cursor | Breaks with filters/skips/retries | Wrong source position | Reader persists semantically accurate state |
| Sharing singleton reader across threads | Cursor race conditions | Duplicated/skipped items | `@StepScope` and concurrency design |
| Writing checkpoints to Job context per item | No matching commit boundary | Inconsistent state | Step context + `ItemStream` |
| Not testing restart | State loss discovered in production | Data loss | Test real failure then restart |
| Manually editing DB metadata | Corrupted serialized context | Unrestartable, hard to debug | Controlled recovery procedure |

## 16. Why Should You Not Use StepExecution.readCount as a Checkpoint?

A common misconception: the number of items read equals the position in the file, so saving `readCount` suffices instead of a dedicated cursor.

That breaks whenever:

- The reader skips header or comment lines.
- Parse errors occur and `skip in read` fires.
- Items are filtered in the processor.
- Retries/rollbacks cause items to be re-read.
- Paginated APIs or partitions lack a 1:1 item-to-offset mapping.
- The reader builds one item from multiple lines or emits multiple items per line.

For example:

```text
File:
  line 1 = header
  line 2 = INV-001 valid
  line 3 = INVALID (skip in read)
  line 4 = INV-002 valid

readCount=2
readSkipCount=1
actual next file line=5
```

If restart "skips `readCount=2` lines", the reader starts at the wrong line. `FlatFileItemReader` has its own state persistence and line mapping; for custom readers, track cursors in terms of **actual source position** rather than deriving them from a business counter.

## 17. Multithreading, Partitioning, and Context

An `ExecutionContext` is state bound to **a single `StepExecution`**; it does not provide distributed locks or cross-worker merging on its own.

### 17.1. Multi-Threaded Steps

If multiple threads call the same `ItemStreamReader` holding a mutable `nextIndex` field, this can happen:

```text
Thread A reads nextIndex=100
Thread B reads nextIndex=100
A increments to 101
B increments to 101
The same item may be read twice
```

Some readers are not thread-safe; many Spring Batch readers have state/restart options that are not fully compatible with multi-threading without synchronization. Evaluate reader thread safety, input splitting, and consistent checkpointing. Simply adding `@StepScope` does not make a reader thread-safe if the step runs multiple threads against that same instance.

### 17.2. Partitioned Steps

Each partition can carry its own data-range parameters:

```text
manager StepExecution
    |
    +-- worker partition 0
    |     stepContext: minId=1, maxId=100000, nextId=35000
    |
    +-- worker partition 1
    |     stepContext: minId=100001, maxId=200000, nextId=160000
    |
    +-- worker partition 2
          stepContext: minId=200001, maxId=300000, nextId=240000
```

Each worker must validate:

- `minId`, `maxId`, and `nextId` have valid types and bounds.
- Partition ranges do not unintentionally overlap.
- Restart uses the matching key and data range for that partition.
- Source data has not mutated in ways that invalidate `nextId`.

Never funnel every partition's cursor into one `"lastProcessedId"` key in job context expecting workers not to overwrite one another. Result merging/aggregation needs explicit rules matching partition semantics.

### 17.3. Remote Workers

When workers run in separate JVMs, object references in the manager's context are not how state travels. Keys must be serialized and transmitted/read via the appropriate partitioning/remote execution mechanism. Never assume mutating a context map in one JVM instantly updates maps in other JVMs.

## 18. Unit Testing Checkpoints Without Booting Full Batch Infrastructure

`InvoiceCheckpoint` above can be tested with an in-memory `ExecutionContext`.

### 18.1. Testing Fresh State

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.batch.item.ExecutionContext;

class InvoiceCheckpointTest {

    @Test
    void emptyContextStartsAtZero() {
        ExecutionContext context = new ExecutionContext();

        assertEquals(
                0,
                InvoiceCheckpoint.restore(context, "file-v1", 100)
        );
    }
}
```

The rule "empty context ⇒ start at zero" holds only when **the caller ensures this is a fresh run or a restart without prior valid checkpoints**. Unit tests verify the algorithm, not that every execution's metadata meets that assumption.

### 18.2. Testing Saving and Restoring the Cursor

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.batch.item.ExecutionContext;

class InvoiceCheckpointRoundTripTest {

    @Test
    void restoresSavedPosition() {
        ExecutionContext context = new ExecutionContext();

        InvoiceCheckpoint.save(context, "file-v1", 42);

        assertEquals(
                42,
                InvoiceCheckpoint.restore(context, "file-v1", 100)
        );
    }
}
```

### 18.3. Testing a Missing Required Key

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.batch.item.ExecutionContext;

class InvoiceCheckpointMissingKeyTest {

    @Test
    void partialCheckpointMustFail() {
        ExecutionContext context = new ExecutionContext();

        context.putInt(InvoiceCheckpoint.VERSION, 1);
        context.putInt(InvoiceCheckpoint.NEXT_INDEX, 42);
        // Missing SOURCE_ID.

        assertThrows(
                IllegalStateException.class,
                () -> InvoiceCheckpoint.restore(
                        context, "file-v1", 100)
        );
    }
}
```

### 18.4. Testing Source Change, Version, Negative Values, and Out-of-Bounds Cursor

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.batch.item.ExecutionContext;

class InvoiceCheckpointValidationTest {

    @Test
    void rejectsSourceChange() {
        ExecutionContext context = new ExecutionContext();

        InvoiceCheckpoint.save(context, "file-v1", 10);

        assertThrows(
                IllegalStateException.class,
                () -> InvoiceCheckpoint.restore(
                        context, "file-v2", 100)
        );
    }

    @Test
    void rejectsUnsupportedVersion() {
        ExecutionContext context = new ExecutionContext();

        InvoiceCheckpoint.save(context, "file-v1", 10);
        context.putInt(InvoiceCheckpoint.VERSION, 99);

        assertThrows(
                IllegalStateException.class,
                () -> InvoiceCheckpoint.restore(
                        context, "file-v1", 100)
        );
    }

    @Test
    void rejectsNegativeOffset() {
        ExecutionContext context = new ExecutionContext();

        InvoiceCheckpoint.save(context, "file-v1", -1);

        assertThrows(
                IllegalStateException.class,
                () -> InvoiceCheckpoint.restore(
                        context, "file-v1", 100)
        );
    }

    @Test
    void rejectsOffsetPastEnd() {
        ExecutionContext context = new ExecutionContext();

        InvoiceCheckpoint.save(context, "file-v1", 101);

        assertThrows(
                IllegalStateException.class,
                () -> InvoiceCheckpoint.restore(
                        context, "file-v1", 100)
        );
    }

    @Test
    void rejectsUnexpectedValueType() {
        ExecutionContext context = new ExecutionContext();

        InvoiceCheckpoint.save(context, "file-v1", 10);
        context.putString(InvoiceCheckpoint.NEXT_INDEX, "ten");

        assertThrows(
                IllegalStateException.class,
                () -> InvoiceCheckpoint.restore(
                        context, "file-v1", 100)
        );
    }
}
```

These tests target the exact pitfall of **not checking context**. They are fast, require no `Thread.sleep(...)`, and depend on no clocks, networks, or random data.

### 18.5. Testing Reader Lifecycle

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.batch.item.ExecutionContext;

class RestartableInvoiceReaderTest {

    @Test
    void readerResumesFromSavedIndex() throws Exception {
        ExecutionContext context = new ExecutionContext();

        RestartableInvoiceReader first =
                new RestartableInvoiceReader(
                        List.of("A", "B", "C", "D"),
                        "file-v1"
                );

        first.open(context);
        assertEquals("A", first.read());
        assertEquals("B", first.read());

        // Simulate framework calling update at committed checkpoint.
        first.update(context);
        first.close();

        RestartableInvoiceReader restarted =
                new RestartableInvoiceReader(
                        List.of("A", "B", "C", "D"),
                        "file-v1"
                );

        restarted.open(context);
        assertEquals("C", restarted.read());
        assertEquals("D", restarted.read());
        assertEquals(null, restarted.read());
        restarted.close();
    }
}
```

This test reuses an in-memory `ExecutionContext` to illustrate state round-tripping. **It does not simulate transaction rollbacks or real `JobRepository` serialization.** Those requirements need an integration test.

## 19. Integration Test: Mid-Chunk Failure and Real Restart

To confirm checkpoints are production-ready, write an integration test with:

1. A real `JobRepository` (e.g., H2 for logic tests; a production-like database for critical transaction verification).
2. A properly registered `ItemStreamReader`.
3. A JDBC writer sharing the step's transaction manager.
4. A controlled failure triggered **after several chunks have committed**.
5. Restarting the same `JobInstance` via `JobOperator.restart(...)` or `JobLauncher` as appropriate.
6. Reconciling the target table after restart: complete data, zero duplicates, zero missing items.

Scenario diagram:

```text
Immutable input: A, B, C, D, E, F
chunk size = 2

Execution 501:
  chunk 1: A, B -> commit
  chunk 2: C, D -> commit
  chunk 3: E, F -> writer intentionally fails -> rollback
  Step FAILED

Execution 509 (restart):
  restores reader at checkpoint after D
  chunk 3: E, F -> commit
  Job COMPLETED

Final output:
  A, B, C, D, E, F (each item exactly once)
```

In the test, use a fake writer throwing once based on a **test-harness flag outside the transaction**, then restart and let the writer succeed normally. Do not use a counter inside the processor assuming it rolls back with the database.

### 19.1. Building Stable Run Parameters

```java
JobParameters params = new JobParametersBuilder()
        .addString("sourceId", "file-v1", true)
        .addString("businessDate", "2025-05-12", true)
        .toJobParameters();
```

On restart, do not add a different identifying `run.id` that creates a new job instance. If running multiple independent tests, create a clean test `JobRepository`/schema or use distinct source IDs **across different tests**, never changing parameters between two executions of the same restart test.

### 19.2. What Should Be Asserted?

```java
// Illustrative assertions after restart completes:
assertEquals(BatchStatus.COMPLETED, restarted.getStatus());

List<String> ids = jdbcTemplate.queryForList(
        "SELECT invoice_id FROM invoices ORDER BY invoice_id",
        String.class
);

assertEquals(List.of("A", "B", "C", "D", "E", "F"), ids);
```

This is an illustrative assertion snippet assuming schema and data are created in the test. Beyond the final outcome, inspect `StepExecution`s of the old/new executions and persisted checkpoints; otherwise, an idempotent writer can mask a bug where the reader restarted from the beginning. To prove the reader truly resumed, capture **item IDs returned by the reader during the restarted execution** in the test fixture.

### 19.3. Testing Missing or Invalid Context

In addition to the happy path, test:

- Context after commit missing a checkpoint key.
- Unsupported `stateVersion`.
- `sourceId` mismatching `JobParameters`.
- `nextIndex` exceeding input length.
- Wrong key type (e.g., string instead of number).
- Unregistered `ItemStream` reader delegate.
- Source file content changed while keeping the same filename.
- Job context missing a promoted key from the previous step.
- Two partitions sharing the same key name and corrupting state mapping.
- Serializer changed and unable to read legacy metadata.

These cases must produce **explainable failures**, rather than silently resetting checkpoints and letting the job finish `COMPLETED` with missing data.

## 20. Inspecting ExecutionContext in Operations

When a job is `FAILED` or `STOPPED` and cannot restart, operators need to inspect:

- `JobInstance`: job name and identifying parameters.
- `JobExecution`: status, start/end times, failure exceptions.
- `StepExecution`: status, read/write/skip/rollback/commit counters.
- **Step ExecutionContext**: key names, state version, source ID, cursor or page token.
- **Job ExecutionContext**: values shared across steps, whether promotion occurred.
- Data source: file/object version, snapshot ID, checksum.
- Data target: committed rows and non-transactional side effects.

Spring Batch provides the `JobExplorer` API to read metadata:

```java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.item.ExecutionContext;

public final class CheckpointInspector {

    private final JobExplorer explorer;

    public CheckpointInspector(JobExplorer explorer) {
        this.explorer = explorer;
    }

    public void inspect(long jobExecutionId) {
        JobExecution job =
                explorer.getJobExecution(jobExecutionId);

        if (job == null) {
            throw new IllegalArgumentException(
                    "Unknown JobExecution " + jobExecutionId);
        }

        for (StepExecution step : job.getStepExecutions()) {
            ExecutionContext state = step.getExecutionContext();

            System.out.println("stepName=" + step.getStepName());
            System.out.println("status=" + step.getStatus());
            System.out.println("stepExecutionId=" + step.getId());

            // Read only a safe allowlisted key; never dump the whole map.
            if (state.containsKey(InvoiceCheckpoint.SOURCE_ID)) {
                System.out.println(
                        "sourceId="
                                + state.getString(
                                        InvoiceCheckpoint.SOURCE_ID));
            }

            if (state.containsKey(InvoiceCheckpoint.NEXT_INDEX)) {
                Object raw = state.get(InvoiceCheckpoint.NEXT_INDEX);
                System.out.println("nextIndex=" + raw);
            }
        }
    }
}
```

**Never log the entire `ExecutionContext` via `toString()`** unless you know everything it holds. Context can contain identifiers, internal paths, tokens mistakenly saved by the application, and values requiring access control. Operations dashboards should display only safe allowlisted keys behind clear query permissions.

### 20.1. Reading Metadata from the Database

The Spring Batch schema typically uses two tables:

```text
BATCH_STEP_EXECUTION_CONTEXT
  STEP_EXECUTION_ID
  SHORT_CONTEXT
  SERIALIZED_CONTEXT

BATCH_JOB_EXECUTION_CONTEXT
  JOB_EXECUTION_ID
  SHORT_CONTEXT
  SERIALIZED_CONTEXT
```

Table names, columns, and context encoding depend on version/schema/table-prefix configuration. Direct reads can assist investigations, yet **never manually edit serialized context**. Using `JobExplorer` ensures the application respects the framework's serialization layer.

### 20.2. Which Metrics Are Useful?

Beyond step duration, monitor:

| Metric | Purpose |
|---|---|
| Failed job restarts due to invalid checkpoint | Spot unexpected code or source changes |
| `sourceId` mismatch count | Spot mutated files/versions |
| Context serialization errors | Spot incompatible objects or serializer upgrades |
| `FAILED` steps by root-cause category | Separate metadata, input, and writer errors |
| `readCount`, `writeCount`, `rollbackCount` | Reconcile progress against transactions |
| Last checkpoint time and time without progress | Spot hung steps |
| Restarts per `JobInstance` | Assess pipeline stability |

These metrics are **designed by the application/monitoring team**, not all emitted automatically by Spring Batch. Never put individual `jobExecutionId`, `sourceId`, or context values as Prometheus labels due to high cardinality. Use access-controlled logs/audits for detailed lookups.

## 21. Incident Handling: Restart Reports Missing ExecutionContext

A safe operational procedure:

1. **Confirm the right instance is restarting.** Verify job name, identifying parameters, and old execution.
2. **Read execution/step status.** Is it `FAILED`, `STOPPED`, or stuck `STARTED` in metadata? Never assume every state is restartable.
3. **Verify the reader registered `ItemStream`.** Are `open/update/close` invoked under the current configuration?
4. **Check keys and versions.** Were bean names, readers, key namespaces, or serializers changed after deploy?
5. **Verify the source.** Do `sourceId`, checksums, and formats still match?
6. **Reconcile written data.** Which chunks committed? Did the writer trigger non-transactional side effects?
7. **Choose controlled recovery.** Fix config/migrate checkpoints with evidence; if unrecoverable, launch a fresh reprocess workflow with deduplication/reconciliation.
8. **Add regression tests.** Reproduce the broken context state in tests to prevent recurrence.

**Avoid this:**

```java
try {
    return context.getInt("nextIndex");
} catch (Exception ignored) {
    return 0; // Masks every checkpoint error by reading from the beginning.
}
```

This pattern turns schema, type, or source-mutation errors into unexpected outcomes. If the business allows reprocessing from the beginning, make it an **explicit decision** with writer idempotency and auditing—never a silent fallback for every exception.

## 22. Practice Exercises

Build `syncInvoiceSnapshot` reading an immutable list of invoices from a snapshot with `sourceId` and writing to `invoices`. The step uses `chunk(100)`.

Requirements:

1. Define `JobParameters` containing `businessDate` and `sourceId`. Distinguish identifying parameters from cursors stored in `StepExecutionContext`.
2. Write an `ItemStreamReader<Invoice>` with `open/read/update/close`, storing `stateVersion`, `sourceId`, and `nextIndex`.
3. In `open(...)`, reject contexts with partial keys, unknown versions, wrong types, negative indices, or out-of-bounds indices.
4. Design an immutable snapshot source with matching checksum/versioning to block restarts on mutated data.
5. Build a JDBC writer with a unique constraint on `invoiceId`, guaranteeing idempotency across retries/restarts.
6. Run a failure test after 2 committed chunks, then restart; verify zero missing or duplicate invoices.
7. Intentionally delete one checkpoint key in a recovery test and confirm the reader fails fast instead of resetting the cursor.
8. Change `sourceId` from `file-v1` to `file-v2` while keeping item count identical; confirm the mismatch is caught.
9. Wrap the `ItemStreamReader` delegate inside an `ItemReader`; omit `.stream(delegate)` to reproduce the lifecycle bug, then fix and verify.
10. Create two steps: step A puts `reportPath` into step context and step B reads job context. Use `ExecutionContextPromotionListener`, and test missing keys or mismatched statuses.
11. Try changing `nextIndex` from `Integer` to `Long` and write a range-checked migration test.
12. Design an ops view displaying only allowlisted checkpoint keys and essential metadata without dumping secrets or payloads.

**Review question:** A step already wrote 400,000 invoices; on restart, `ExecutionContext` lacks the `nextIndex` key. Should we default to starting from 0 just so the job "can run"?

**Answer:** **Not automatically.** First determine whether this is valid initial state or a lost checkpoint, and verify committed chunks and writer idempotency. Unless you can prove reprocessing from the beginning is safe, fail fast and perform controlled recovery.

## 23. References

- [Spring Batch Reference — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): `open`, `update`, `close`, and persisting state in `ExecutionContext`.
- [Spring Batch Reference — Registering ItemStream with a Step](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/registering-item-streams.html): registering `ItemStream` delegates via `.stream(...)`.
- [Spring Batch Reference — Common Batch Patterns](https://docs.spring.io/spring-batch/reference/common-patterns.html): read/write patterns, restarts, and state handling.
- [Spring Batch Reference — Domain Language](https://docs.spring.io/spring-batch/reference/domain.html): `JobInstance`, `JobExecution`, `StepExecution`, and `ExecutionContext` scopes.
- [Spring Batch Reference — Configuring a Step](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): chunks, transactions, and checkpoints.
- [Spring Batch Reference — Execution Context Promotion](https://docs.spring.io/spring-batch/reference/common-patterns.html): using `ExecutionContextPromotionListener` across steps.
- [Spring Batch 5.2 API — ExecutionContext](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/item/ExecutionContext.html): `containsKey`, `get`, `putInt`, `getInt`, `putString`.
- [Spring Batch 5.2 API — ItemStream](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/item/ItemStream.html): lifecycle contract for stateful readers/writers.
- [Spring Batch Reference — Metadata Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html): tables storing job/step execution contexts.
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html): testing steps/jobs and restart scenarios.
