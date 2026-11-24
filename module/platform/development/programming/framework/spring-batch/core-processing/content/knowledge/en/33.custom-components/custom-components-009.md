# Exception Contracts

In Spring Batch, custom readers, processors, writers, tasklets, and supporting components all need clear error conventions. A component may encounter bad data, transient connection errors, configuration errors, resource failures, or programming bugs. If all errors are converted into a single generic exception, the framework cannot easily tell which cases should retry, which should skip, and which must stop the job immediately.

An **exception contract** is the agreement about what error types a component can raise, what each error means, what contextual details are preserved, and how errors propagate to Spring Batch. A good contract lets retry/skip policies classify accurately, ensures transactions roll back at the right time, makes logs investigable, and allows tests to verify behavior.

In Spring Batch, core interfaces allow components to throw exceptions. For instance, `ItemReader`, `ItemProcessor`, `ItemWriter`, and `Tasklet` all declare methods with `throws Exception`. A custom component should leverage that contract, preserve root causes, and avoid hiding errors. Throwing an exception, marking an item filtered, ending a step with an `ExitStatus`, and triggering a retry are distinct behaviors that must be used for their intended purposes.

## 1. What Is an Exception Contract?

An exception contract describes what callers can expect when a component cannot complete its work. The contract should answer:

- What error categories can the component raise?
- Which errors represent invalid business data?
- Which errors are transient and safe to retry?
- Which errors are configuration or unrecoverable errors?
- Did the error occur during read, process, write, or lifecycle?
- Does the component preserve the cause when translating exceptions?
- Should the transaction roll back when the error occurs?
- Should the error be skipped, retried, or fail the step/job?
- Do logs and metadata contain enough details to locate the related item/resource?

For example, a custom API reader might define:

| Exception | Meaning | Typical handling |
|---|---|---|
| `InvalidResponseException` | Partner payload has malformed structure or violates contract | Stop or skip per data rules |
| `PartnerUnavailableException` | API timed out or returned a transient error | Bounded retry with backoff |
| `AuthenticationConfigurationException` | Invalid credentials/configuration | Fail fast, do not retry repeatedly |
| `SourceSnapshotChangedException` | Source shifted relative to checkpoint | Stop to avoid reading inconsistent data |
| `ItemNotFoundException` | No data matches the key | Depends on business rules: skip, filter, or fail |

Exception names should express the meaning callers need to know, rather than merely repeating technical library error names.

## 2. Exception Contracts in Spring Batch Interfaces

Core interfaces allow custom components to report errors via exceptions:

| Interface | Method | Key contract |
|---|---|---|
| `ItemReader<T>` | `read()` | Return next item, `null` when data exhausted, throw exception if unable to read |
| `ItemProcessor<I,O>` | `process(I)` | Return output, `null` to filter item, throw exception if processing fails |
| `ItemWriter<T>` | `write(Chunk<? extends T>)` | Write chunk, throw exception if unable to fulfill contract |
| `Tasklet` | `execute(...)` | Return `RepeatStatus` when finished/continuing, throw exception if execution fails |
| `ItemStream` | `open`/`update`/`close` | Manage resource/state lifecycle; use `ItemStreamException` for lifecycle errors |

Methods of reader, processor, writer, and tasklet declare `throws Exception`. Therefore, custom implementations are not forced to wrap every checked exception into `RuntimeException`. Choose meaningful exceptions, preserve causes, and let the framework receive the failure.

Never use `null` or an empty object to represent a read error. For `ItemReader`, `null` specifically means end of data. For `ItemProcessor`, `null` means the item is filtered from output. Neither `null` value replaces throwing an exception on failure.

## 3. Distinguishing Exceptions, EOF, Filtering, and Business Status

Several component outcomes look similar superficially yet carry very different semantics:

| Outcome | Meaning | Framework handling |
|---|---|---|
| `ItemReader` returns `null` | No more items | Ends the reading phase |
| `ItemProcessor` returns `null` | Item intentionally filtered | Item not passed to writer |
| Component throws exception | Operation failed | Applies rollback/retry/skip/fail policy |
| `Tasklet` returns `RepeatStatus.FINISHED` | Tasklet completed | Step proceeds with completion lifecycle |
| Step returns `ExitStatus` | Step result/status label | Job flow can branch on it |
| Job/Step `BatchStatus` | Execution state in metadata | Reflects `COMPLETED`, `FAILED`, `STOPPED`, etc. |

Do not throw an exception just to signal that no data exists. Do not return `null` from a processor just to hide data errors. Do not use exceptions for normal business outcomes that can be expressed with clean outputs or statuses.

If you need to distinguish "not found" as a valid outcome from "not found" as an error, define the contract by business intent. For instance, a processor may return `null` to filter an item that needs no export, whereas a reader missing a mandatory source must throw `SourceNotFoundException`.

## 4. Designing Exceptions by Root-Cause Category

A custom component typically needs at least these categories:

1. **Data errors:** malformed records, missing required fields, out-of-range values.
2. **Transient errors:** timeouts, throttling, deadlocks, brief connection drops.
3. **Configuration errors:** invalid endpoints, credentials, schemas, table names, or job parameters.
4. **Resource errors:** missing files, permission errors, disk full, closed resources.
5. **Programming errors:** violated invariants, invalid internal state, unexpected nulls.

Not every category requires its own class. However, any exception types that retry/skip policies must tell apart need distinct types. Avoid a single catch-all like `BatchProcessingException` for every case if callers cannot tell how to handle it.

A simple hierarchy:

~~~java
public abstract class OrderImportException extends Exception {

    protected OrderImportException(String message) {
        super(message);
    }

    protected OrderImportException(String message, Throwable cause) {
        super(message, cause);
    }
}

public class InvalidOrderException extends OrderImportException {

    public InvalidOrderException(String message) {
        super(message);
    }
}

public class TemporarySourceException extends OrderImportException {

    public TemporarySourceException(String message, Throwable cause) {
        super(message, cause);
    }
}

public class SourceConfigurationException extends OrderImportException {

    public SourceConfigurationException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

The example above uses checked exceptions to express contract failures. Applications may also use `RuntimeException` for unexpected errors or other abstractions. What matters is that exception types are meaningful and classification policies are consistent.

## 5. Preserving the Original Cause When Translating Exceptions

Custom components often invoke external libraries such as HTTP clients, JDBC drivers, parsers, or filesystem APIs. Translating technical exceptions into domain exceptions keeps step policies decoupled from library specifics.

Example:

~~~java
try {
    return partnerClient.fetchNextPage(pageToken);
} catch (SocketTimeoutException ex) {
    throw new TemporarySourceException(
            "Timed out while fetching the next order page", ex);
} catch (AuthenticationException ex) {
    throw new SourceConfigurationException(
            "Partner authentication failed", ex);
}
~~~

The original cause is passed to the constructor to retain stack traces and technical details. Creating a new exception with only a message discards timeout, HTTP response, or driver error details.

Do not catch `Exception` and rethrow a generic exception without a cause. Also do not catch, log, and proceed as if the call succeeded. If the component cannot handle the error, let it propagate or translate it purposefully.

## 6. Do Not Use One Generic Exception for Transient and Permanent Errors

Retry policies usually classify by exception type. If all API failures are wrapped into `PartnerException`, the framework cannot easily tell apart:

- HTTP 429 or throttling, which may succeed after waiting.
- HTTP 503, which may be temporary.
- HTTP 400 from bad payloads, which will not heal on retry.
- HTTP 401/403, which requires fixing credentials/permissions.
- HTTP 404, which may be a business outcome or a misconfigured endpoint.

Classify according to the partner system's semantics, not mechanically by HTTP status code alone. Example:

~~~java
if (response.statusCode() == 429 || response.statusCode() == 503) {
    throw new TemporarySourceException(
            "Partner service is temporarily unavailable", null);
}

if (response.statusCode() == 401 || response.statusCode() == 403) {
    throw new SourceConfigurationException(
            "Partner credentials or permissions are invalid", null);
}

if (response.statusCode() >= 400) {
    throw new InvalidOrderException(
            "Partner rejected the requested order data");
}
~~~

This is illustrative; preserve useful response/cause details and align with the concrete contract. Never retry authentication failures or malformed payloads endlessly.

## 7. Exception Contract of ItemReader

`ItemReader` has a simple yet critical contract:

- Return an item when read succeeds.
- Return `null` when data is exhausted.
- Throw an exception if reading cannot continue per contract.

Example custom reader:

~~~java
public class ApiOrderReader implements ItemStreamReader<OrderInput> {

    @Override
    public OrderInput read() throws Exception {
        try {
            return fetchNextOrder();
        } catch (SocketTimeoutException ex) {
            throw new TemporarySourceException(
                    "Order source timed out", ex);
        }
    }

    // open, update, close, and fetchNextOrder are implemented separately.
}
~~~

Never return `null` when an API times out. Spring Batch treats `null` as end of data and can complete the step even though the source was not fully read.

Never return an empty item when a payload fails to parse. That feeds bogus data into the processor/writer and masks source errors.

The reader should clarify whether errors occur before or after the source consumes an item. If a non-transactional source already consumed a record and the reader throws before returning it, the framework has no item to buffer. Design appropriate replay, acknowledgment, or staging.

## 8. Exception Contract of ItemProcessor

A processor takes an item and returns an output or `null` to filter. If it cannot process the item, it can throw an exception:

~~~java
public class OrderProcessor
        implements ItemProcessor<OrderInput, OrderOutput> {

    @Override
    public OrderOutput process(OrderInput input) throws InvalidOrderException {
        if (input.getOrderId() == null) {
            throw new InvalidOrderException("orderId is required");
        }

        if (input.getAmount() == null || input.getAmount().signum() < 0) {
            throw new InvalidOrderException("amount must be non-negative");
        }

        return new OrderOutput(input.getOrderId(), input.getAmount());
    }
}
~~~

Here, invalid data is reported via an exception so the step can apply skip/fail policies. If an item is valid yet does not need writing, the processor can return `null` per filter rules.

Never use `null` to mean "the processor hit an error but wants the job to keep going." That drops the item from the pipeline without incrementing skip counts or invoking skip listeners.

## 9. Exception Contract of ItemWriter

`ItemWriter` receives a chunk and is responsible for writing items per contract. If unable to write, the writer throws an exception:

~~~java
public class OrderAuditWriter implements ItemWriter<OrderOutput> {

    @Override
    public void write(Chunk<? extends OrderOutput> chunk) throws Exception {
        for (OrderOutput item : chunk) {
            writeOne(item);
        }
    }
}
~~~

For writers writing to a database under the step's transaction manager/datasource, an exception normally rolls back the chunk. For writers writing files or calling APIs, understand the specific resource's transaction semantics; side effects already committed outside the transaction do not automatically roll back.

A writer must not swallow exceptions and return normally when only part of a chunk was written. If callers think the chunk succeeded, checkpoints advance and data is lost. If a writer permits partial success, its contract must explicitly indicate which items succeeded, which failed, and how restarts/reconciliation behave.

With standard Spring Batch writers, an exception from `write` causes the chunk to fail; the framework may retry or skip per configuration. Custom writers must ensure behavior aligns with transaction and retry semantics.

## 10. Exception Contract of Tasklet

A `Tasklet` performs a unit of work and returns `RepeatStatus` to indicate completion or continuation. Exceptions indicate that the execution attempt failed:

~~~java
public class ValidateInputTasklet implements Tasklet {

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) throws Exception {

        if (!inputIsValid()) {
            throw new InvalidInputException("Input validation failed");
        }

        return RepeatStatus.FINISHED;
    }
}
~~~

Do not return `RepeatStatus.FINISHED` when validation fails. Also do not return `CONTINUABLE` to retry an error with no termination condition. When polling external state, define explicit timeouts, iteration limits, and wait intervals.

A tasklet can run inside a transaction depending on step configuration. Exceptions from `execute` normally fail the current attempt and roll back the transaction per transaction manager semantics.

## 11. Exceptions in the ItemStream Lifecycle

Stateful or resource-holding readers/writers typically implement `ItemStream`. Lifecycle methods have their own contract:

- `open(ExecutionContext)`: open resources and restore state.
- `update(ExecutionContext)`: update state so the framework saves checkpoints.
- `close()`: close and release resources.

These methods use `ItemStreamException` to report lifecycle failures. Example:

~~~java
@Override
public void open(ExecutionContext context) throws ItemStreamException {
    try {
        openInput();
        restorePosition(context);
    } catch (IOException ex) {
        throw new ItemStreamException("Cannot open input resource", ex);
    }
}
~~~

`open` failures normally occur before chunk processing starts. `update` failures can affect checkpoint persistence. `close` failures can prevent the step from completing cleanly even after item processing finished.

Do not ignore `close` errors if resources remain unreleased or data remains unflushed. For file outputs, `close` may finalize document structure; if `close` fails, never publish that artifact as valid output.

## 12. Listener Callbacks Also Have Error Contracts

Listeners provide hooks to observe or act around read/process/write/chunk/step/job events. Some callbacks do not declare checked exceptions in their signatures. Throwing unchecked exceptions from them can still abort execution.

Examples:

- `ItemReadListener.onReadError(Exception ex)`.
- `ItemProcessListener.onProcessError(item, Exception ex)`.
- `ItemWriteListener.onWriteError(Exception ex)`.
- `SkipListener` recording skipped items.
- `StepExecutionListener.afterStep(...)` returning an `ExitStatus`.

Listeners should focus on observation, auditing, or appropriate metadata updates. Avoid using listeners to replace readers/writers or perform non-idempotent side effects. If auditing must persist durably, define clear transaction and failure policies.

In particular, listeners must not catch and hide original exceptions. If an audit callback fails, decide explicitly whether audit failure should fail the job or merely log/route to a secondary channel. That decision is part of the operational contract.

## 13. Exception Classification: Retry, Skip, or Fail

Spring Batch cannot automatically know how every exception should be handled. Steps need appropriate policies:

| Classification | Meaning | Examples |
|---|---|---|
| Retryable | Likely to succeed if retried | Timeout, deadlock, throttling |
| Skippable | Bad item can be excluded while preserving business correctness | Independent record with invalid data |
| Fatal/non-retryable | Retrying will not help or continuing corrupts data | Misconfiguration, incompatible schema, bad credentials |
| Unknown | Not yet classified | Usually fail safely until explicit rules exist |

An exception can be retryable without being skippable. For example, a database deadlock should retry the transaction; if retries exhaust, you typically should not skip the chunk as if it were a bad record.

An exception can be skippable without being retryable. For example, `InvalidOrderException` can be written to an error report and skipped per business policy.

Do not configure retry and skip broadly on `Exception.class` without understanding the underlying failure types. Overly broad policies cause configuration bugs to retry repeatedly or critical data to be silently skipped.

## 14. Configuring Retry for Custom Exceptions

Example configuring retry for transient source errors:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, OrderOutput>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .retry(TemporarySourceException.class)
        .retryLimit(3)
        .build();
~~~

`retryLimit(3)` bounds retry attempts per your builder/version semantics; check exactly how your project's framework version counts the initial attempt versus retries. For rate-limited/backoff scenarios, configure an appropriate backoff policy to avoid hammering external systems.

Retry is safe only when the operation can be repeated safely. If an API already created a side effect and only the response timed out, retries can duplicate effects. Use idempotency keys or status queries before retrying.

## 15. Configuring Skip for Custom Exceptions

Example skipping items with invalid business data:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, OrderOutput>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skipLimit(50)
        .build();
~~~

`skipLimit` caps how many bad items the step's policy permits skipping. Exceeding the limit fails the step.

Skip only when an item can be omitted without breaking business invariants. For example, an independent order with a negative amount can go to an error report; by contrast, a record defining an exchange rate or opening balance affects all subsequent records and should not be skipped.

When auditing skipped items, use `SkipListener` to log business keys, error types, and reasons. Avoid logging full sensitive payloads.

## 16. Retry and Skip Are Separate Decisions

Some errors should retry first; if still failing, the step may fail. Some data errors should skip immediately. Do not treat skip as a final fallback for every error.

Examples:

| Exception | Retry | Skip | Reason |
|---|---|---|---|
| `TemporarySourceException` | Yes, bounded | Usually no | Source may recover temporarily |
| `InvalidOrderException` | Usually no | Yes if business allows | Record data does not change on retry |
| `SourceConfigurationException` | No | No | Configuration/credentials must be fixed |
| `DeadlockLoserDataAccessException` | Yes | Usually no | Retrying the transaction can succeed |
| `DuplicateBusinessKeyException` | Depends on semantics | Depends on policy | May be a valid replay or a data error |

If an exception is configured for both retry and skip, understand policy precedence and classification behavior in your framework version. Prefer avoiding unnecessary overlap and write tests for each exception type.

## 17. noRollback Is Not the Same as Skip

A fault-tolerant step can specify exceptions that do not roll back transactions via `noRollback(...)`. This is a separate axis from retry/skip:

- Retry decides whether to re-attempt the operation.
- Skip decides whether to discard the bad item and continue.
- `noRollback` decides whether the exception rolls back the current transaction.

Conceptual example:

~~~java
.faultTolerant()
.noRollback(NonCriticalValidationException.class)
~~~

Use `noRollback` only when the exception genuinely does not require undoing changes in the transaction. If a writer already wrote partial data and then threw an exception, keeping the transaction committed can leave inconsistent state.

`noRollback` does not turn an exception into success, does not skip items automatically, and does not guarantee the step continues. Verify how exceptions propagate across reader/processor/writer and write tests for exact transaction behavior.

## 18. Rollback and Custom Writers with Side Effects

A custom writer might execute multiple actions per chunk:

1. Write several items to a database.
2. Call an external API.
3. Write an audit file.
4. Throw an exception when a later step fails.

If all actions do not share one transaction, a database rollback cannot undo API calls or written files. When the framework retries the chunk, side effects can run again.

Safer designs:

- Prefer writing database changes inside the chunk transaction.
- Use a transactional outbox to emit events post-commit.
- Use idempotency keys for APIs.
- Write files to staging and publish once the job/step completes.
- Use unique business keys to prevent duplicates.
- Provide reconciliation for ambiguous states after timeouts/crashes.

The exception contract must state clearly what side effects the writer may have triggered before throwing. If atomicity cannot be guaranteed, callers need to know how to handle retries and reconciliation.

## 19. Do Not Swallow Exceptions in Custom Components

A common mistake:

~~~java
try {
    return client.fetch();
} catch (Exception ex) {
    log.error("Fetch failed", ex);
    return null;
}
~~~

In a reader, `null` means end of data. The job can finish with missing output and no sign of failure.

Another mistake:

~~~java
try {
    repository.save(item);
} catch (Exception ex) {
    log.error("Save failed", ex);
}
~~~

The writer returns normally even though the item was not persisted. The framework may commit the checkpoint and never retry that item.

Let errors propagate:

~~~java
try {
    repository.save(item);
} catch (DataAccessException ex) {
    throw new OrderWriteException(
            "Cannot persist order " + item.getOrderId(), ex);
}
~~~

Catch exceptions only when the component can handle them completely or needs to translate them into an explicit contract type. If lower and upper layers both log stack traces, duplicate logs accumulate; designate one layer to log full stack traces.

## 20. Do Not Use Catch-All to Turn Errors into Skips

The following code is dangerous:

~~~java
try {
    return transform(item);
} catch (Exception ex) {
    return null;
}
~~~

It turns every error into a filter, including programming bugs, misconfigurations, and data errors. There is no skip count, no `SkipListener`, and no visibility for operators.

If only a specific set of data errors is skippable, throw dedicated exceptions and configure the skip policy for those exact types. When an item is legitimately excluded by business rules, return `null` intentionally without catching exceptions.

## 21. Exceptions in open, update, and close

Custom `ItemStream`s need clear contracts for non-read/write phases:

- `open`: if resources fail to open or checkpoints cannot restore, throw `ItemStreamException`.
- `update`: if required state cannot be saved, throw an error so the framework does not treat the checkpoint as updated.
- `close`: if flushing/closing fails, throw an error; do not publish incomplete outputs.

Example:

~~~java
@Override
public void update(ExecutionContext context) throws ItemStreamException {
    try {
        context.putLong("lastOrderId", lastOrderId);
    } catch (RuntimeException ex) {
        throw new ItemStreamException("Cannot update reader checkpoint", ex);
    }
}
~~~

`ExecutionContext` is a key/value object persisted by the framework through `JobRepository`. You do not need to catch every `RuntimeException` from `put` methods if nothing useful can be done; the snippet simply illustrates translating errors per the lifecycle contract.

If `update` fails, never assume the step can restart accurately. An older checkpoint may cause the reader to re-read items; outputs must be idempotent to handle that case.

## 22. Listeners and Audit Failures

`SkipListener` is commonly used to record skipped items. Example:

~~~java
public class OrderSkipListener
        implements SkipListener<OrderInput, OrderOutput> {

    @Override
    public void onSkipInRead(Throwable t) {
        log.warn("Order input could not be read: {}", t.toString());
    }

    @Override
    public void onSkipInProcess(OrderInput item, Throwable t) {
        log.warn("Skipping order {}: {}",
                item.getOrderId(), t.toString());
    }

    @Override
    public void onSkipInWrite(OrderOutput item, Throwable t) {
        log.warn("Skipping order {} during write: {}",
                item.getOrderId(), t.toString());
    }
}
~~~

Callbacks indicate the phase where the failure happened. Read skips have no successfully read item, so the callback receives only the `Throwable`; process/write skips receive the corresponding item.

If a listener writes to an error table, define the audit write's transaction semantics so audit records are not lost when chunks roll back. Listeners should not send emails or invoke non-idempotent APIs on every callback if callbacks can rerun under retry scenarios.

## 23. Do Not Confuse Exceptions with ExitStatus

Exceptions signal failed operations and participate in rollback/retry/skip handling. `ExitStatus` represents the outcome of a step and can drive job flow decisions.

For example, a verification step may complete technically yet return a custom exit code `NO_DATA` so the job takes another branch. That need not be an exception:

~~~java
@Override
public ExitStatus afterStep(StepExecution stepExecution) {
    if (stepExecution.getReadCount() == 0) {
        return new ExitStatus("NO_DATA");
    }
    return stepExecution.getExitStatus();
}
~~~

The job flow can then use `.on("NO_DATA")` to pick the right transition. Never throw an exception merely to represent a valid business outcome like "no data for this period."

Conversely, if the source cannot be read because the database is unavailable, that is an execution failure requiring an exception so the framework applies failure policies. `ExitStatus` does not replace exception classification.

## 24. Do Not Confuse BatchStatus with Exception Types

`BatchStatus` reflects execution state such as `STARTING`, `STARTED`, `COMPLETED`, `FAILED`, or `STOPPED`. It is not an exception class and does not explain the detailed cause.

A job can become `FAILED` because:

- Reader threw an exception.
- Processor threw a non-skippable exception.
- Writer threw an exception.
- A listener or resource lifecycle failed.
- A step was stopped under an operational condition.

To find the root cause, inspect `StepExecution`/`JobExecution` failure exceptions and related logs. Never inspect only `BatchStatus` and guess the cause.

## 25. Classifying Read, Process, and Write Failures

Where an error occurs affects how the framework recovers:

| Phase | Examples | Key considerations |
|---|---|---|
| Reader | JSON parse error, API timeout, file permissions | Was the item returned yet? Did the source consume it? |
| Processor | Validation failure, invalid mapping rule | Can the read item be buffered/retained for retry/skip? |
| Writer | Unique constraint, DB timeout, file I/O | Were partial side effects produced? Can the transaction roll back? |
| Stream open | Missing file, cursor open failure | Step has not begun processing items |
| Stream update | Unable to save checkpoint | Restart may be inaccurate |
| Stream close | Flush/close failure | Output may be incomplete |

For example, suppose a reader consumes a message from a non-transactional source and throws before returning the item. Spring Batch has no item to buffer. By contrast, if a processor throws after the reader returned the item, the framework can use the read item in fault-tolerance recovery.

When designing custom components, pinpoint exactly when side effects occur and when an item is handed off to the framework.

## 26. Custom SkipPolicy

When skip rules are richer than a list of classes, implement `SkipPolicy` to decide whether an exception is skippable based on the exception and current skip count.

Skeleton example:

~~~java
public class OrderSkipPolicy implements SkipPolicy {

    private final long skipLimit;

    public OrderSkipPolicy(long skipLimit) {
        this.skipLimit = skipLimit;
    }

    @Override
    public boolean shouldSkip(Throwable throwable, long skipCount)
            throws SkipLimitExceededException {

        if (throwable instanceof InvalidOrderException
                && skipCount < skipLimit) {
            return true;
        }

        return false;
    }
}
~~~

Policies must traverse cause chains cautiously: errors can be wrapped inside other exceptions. Guard against infinite loops if a malformed exception chain exists. Also do not skip every exception just because its root cause matches a generic class when business context forbids skipping.

Custom `SkipPolicy` implementations should have unit tests covering every branch: skippable error types, non-skippable error types, and exceeding the limit. If class-based rules suffice, the builder's `skip(...)` method is simpler and clearer.

## 27. Custom RetryPolicy and Backoff

When retry counts or conditions depend on state, use a retry policy suited to your Spring Retry/Spring Batch version. For typical cases, builder `retry(...)`, `retryLimit(...)`, and a backoff policy are clear enough.

Retries should include:

- A bounded attempt limit.
- Delays or exponential backoff when sources enforce rate limits.
- Classification of transient errors.
- Overall timeouts so jobs do not hang forever.
- Idempotency for side effects.
- Logs/metrics for retry counts and final exceptions.

Do not retry misconfigurations or immutable bad data. Do not configure overly long backoffs without accounting for SLAs and job run windows.

## 28. Exception Contracts for Duplicate Errors

Duplicates can mean several different things:

- An item was written in an earlier attempt and a retry is re-sending it.
- The source contains two records with the same business key.
- A consumer processed a message and the broker redelivered it.
- A writer re-ran after a crash window.

Do not use a single `DuplicateException` and always skip. If a duplicate is a valid idempotent replay, the writer can use upserts/unique keys and treat the operation as complete. If two source records share a key with conflicting payloads, that may be a data error that must be reported.

The exception contract should distinguish:

- `DuplicateSamePayloadException`: same key and identical content; can be treated as already handled if policy permits.
- `ConflictingDuplicateException`: same key with different content; typically must fail or route to reconciliation.
- `DuplicateDeliveryException`: redelivered message; consumer deduplicates by event ID.

This classification avoids discarding real data conflicts simply because they resemble duplicate retries.

## 29. Exception Messages and Sensitive Data

Exception messages need enough context for investigation without leaking secrets or full payloads:

- Never log passwords, tokens, API keys, or authorization headers.
- Never include full personal data in messages when a business key suffices.
- Avoid logging entire JSON records when order ID and failing field are enough.
- Include correlation IDs, source identifiers, and appropriate item keys.
- Preserve causes so technical stack traces remain intact.

Good message example:

~~~text
Cannot map amount for orderId=1001, source=orders-2026-11-15.json
~~~

Message to avoid:

~~~text
Failed for payload: {full customer record including credentials and personal data}
~~~

Exception contracts should specify what data may be logged, especially when components handle external payloads.

## 30. Exceptions and Retries in Multi-Threaded Steps

In parallel steps, multiple items can raise exceptions simultaneously. Ensure:

- Custom exceptions are immutable or do not share mutable context across threads.
- Readers/processors/writers do not hold the current item in shared singleton fields.
- Logs carry business keys/correlation IDs to identify thread and item.
- Retry policies do not trigger duplicate side effects.
- Skip listeners or audit writers are thread-safe when invoked concurrently.
- Exceptions do not expose item data belonging to another thread.

Never use a global variable to record the "latest exception." When multiple workers fail, values overwrite each other and no longer correspond to the actual item.

## 31. Exception Contracts with Parallel Flows or Partitions

In parallel flows, one flow's error can affect overall job status and sibling flows. Clarify:

- Which flows are mandatory?
- If one partition fails, must the entire step/job fail?
- Can failed partitions be retried individually?
- Are outputs from successful partitions kept in staging?
- On restart, which partitions rerun and which checkpoints restore?

Never turn a worker's exception into a success status solely to keep the overall flow moving. If partial completion is a valid business outcome, model it explicitly with statuses/manifests and a consolidation step checking completeness.

## 32. Testing Custom Component Exception Contracts

Every custom component should have tests for both the success path and every error type declared in its contract.

For readers:

- Returns items when source has data.
- Returns `null` at EOF.
- Timeouts translate to `TemporarySourceException` preserving cause.
- Malformed payloads translate to `InvalidResponseException`.
- Never returns `null` on source errors.
- If the source consumes before failing, tests verify replay/acknowledgment mechanics.

For processors:

- Valid items produce expected outputs.
- Filtered items return `null`.
- Invalid data throws the expected exception type.
- Never swallows exceptions or returns `null` on errors.

For writers:

- Valid chunks write completely.
- Database failures propagate with cause intact.
- Never reports success after partial writes.
- Retries produce no duplicate side effects.
- Rollbacks leave output state matching contract.

For `ItemStream`:

- `open` restores checkpoints.
- `open`/`update`/`close` failures wrap in `ItemStreamException` with cause.
- Resources release on failures.

## 33. Unit Testing Exception Types and Causes

Example test verifying a reader translates timeouts:

~~~java
@Test
void wrapsTimeoutAsTemporarySourceException() {
    when(client.fetchNextPage()).thenThrow(
            new SocketTimeoutException("read timed out"));

    TemporarySourceException exception = assertThrows(
            TemporarySourceException.class,
            reader::read);

    assertInstanceOf(
            SocketTimeoutException.class,
            exception.getCause());
}
~~~

The test checks both the public exception type visible to callers and that the technical cause is preserved. Never assert merely that *some* exception was thrown, because the wrong type breaks retry policies.

For processors, verify `InvalidOrderException` is thrown only under defined data conditions. For writers, verify exceptions are not swallowed and safe item keys appear in messages.

## 34. Integration Testing Retry and Skip

Unit testing exceptions does not prove the step builder's policy is configured properly. Integration tests are needed for framework behavior:

1. Create reader/processor/writer test doubles that throw per item or call count.
2. Configure retry for `TemporarySourceException` with a small limit.
3. Configure skip for `InvalidOrderException`.
4. Launch the job.
5. Verify transient failures retry and either succeed or fail once the limit expires.
6. Verify invalid items skip in the exact count and listeners fire.
7. Verify configuration errors are not unintentionally retried/skipped.
8. Inspect final outputs and `StepExecution` metrics.

Example reader test double:

~~~java
public class RetryOnceReader implements ItemReader<String> {

    private int attempts;

    @Override
    public String read() throws Exception {
        attempts++;
        if (attempts == 1) {
            throw new TemporarySourceException(
                    "Temporary failure", new IOException("connection reset"));
        }
        if (attempts == 2) {
            return "order-1";
        }
        return null;
    }
}
~~~

This is a simple test double simulating an error before returning an item. For checkpointed readers or transactional sources, test real source semantics rather than relying solely on in-memory counters.

## 35. Testing Transaction Rollback and Side Effects

An important integration test injects a failure after a writer executes partial operations. Verify:

- Database transactions roll back transactional changes.
- Chunks retry, skip, or fail as configured.
- Writers leave no non-transactional side effects without idempotency.
- Error reports reflect items actually skipped.
- Checkpoints do not advance past successfully processed items.

For external APIs or message brokers, use fake servers/brokers to simulate timeouts after the server accepts a request before the client receives a response. Verify idempotency keys prevent duplicate side effects.

## 36. Testing the ItemStream Lifecycle

For stateful custom readers/writers, test each lifecycle phase individually:

- `open` with a fresh `ExecutionContext`.
- `open` with a saved checkpoint.
- `update` after reading/writing several items.
- Restarting from the saved context.
- `close` releasing resources.
- `open`/`update`/`close` throwing `ItemStreamException` on corresponding failures.

Example:

~~~java
ExecutionContext context = new ExecutionContext();
reader.open(context);

reader.read();
reader.update(context);
reader.close();

CustomReader restarted = new CustomReader(source);
restarted.open(context);
// Verify the next item starts after the checkpoint.
restarted.close();
~~~

This is a test skeleton; tailor assertions to whether the reader checkpoints by offset, item count, page token, or business key. Do not check only that a key exists in context; verify the reader actually resumes with the exact next item.

## 37. Do Not Turn Technical Failures into Success Inside Listeners

Some listeners return `ExitStatus` or execute after step processing. Never overwrite a step's status to `COMPLETED` after failure simply to force the job flow onward without explicit business rules.

If an error is an acceptable business outcome:

- Model a distinct status such as `NO_DATA` or `VALIDATION_WARNING`.
- Record clearly what data was processed and what was not.
- Use explicit transitions in the job flow.
- Ensure downstream consumers do not mistake partial output for complete results.

If the error is technical and leaves data untrustworthy, preserve the failure status so operators can intervene.

## 38. Exception Contracts and Observability

Well-designed exception types support operations:

- Class names reflect the root-cause category.
- Messages include appropriate business keys/source identifiers.
- Causes preserve original stack traces.
- Logs include job name, job execution ID, step name, and correlation ID.
- Metrics distinguish retries, skips, and failures.
- Error reports capture item keys and error codes, not necessarily full payloads.
- Alerts fire only for errors needing intervention, avoiding alert storms on transient retries.

If every exception logs only "Batch failed", production debugging drags on. If full payloads are logged, sensitive data leaks. Balance traceability with data minimization.

## 39. Common Design Mistakes

| Scenario | Cause | Fix |
|---|---|---|
| Reader stops early on API error | Catching exception and returning `null` | Return `null` only on EOF; throw on read failure |
| Processor silently drops items | Catching all errors and returning `null` | Use `null` only for intentional filters; throw data errors |
| Writer commits checkpoints despite write failure | Swallowing exceptions and returning normally | Propagate exceptions to the framework |
| Retry never runs | Wrapping into an unrecognized exception type | Preserve causes and classify exception types accurately |
| Permanent errors retry repeatedly | Overly broad retry on `Exception.class` | Retry only transient error types |
| Bad data retries endlessly | Validation failures not classified for skip/fail | Use business exceptions and explicit policies |
| Skipped items lack audit trail | No `SkipListener` registered | Record business keys and skip reasons |
| Duplicate side effects after retry | Writer calls external API outside transaction | Use idempotency keys, outboxes, or reconciliation |
| Rollback fails to undo files/APIs | Non-transactional resources | Staging, publishing, or compensating actions |
| Checkpoint errors hidden | `update` catches and ignores exceptions | Throw `ItemStreamException` with cause |
| Job reports `COMPLETED` despite errors | Listener alters status improperly | Use exceptions for execution failures and `ExitStatus` for business branches |
| Logs leak sensitive data | Putting entire payloads into messages | Log business keys/correlation IDs and sanitize |
| Too many records skipped | Overly permissive skip policy | Bound skips and skip only business-permitted errors |
| Tests assert only that an exception occurred | Ignoring type/cause/policy | Assert exact exception contract and step behavior |

## 40. Exception Contract Design Workflow

1. **List boundaries:** reader, processor, writer, tasklet, stream lifecycle, and listeners.
2. **Categorize causes:** data, transient, configuration, resource, and programming errors.
3. **Define exception types:** create distinct classes only when callers/policies must distinguish them.
4. **Preserve causes:** translate technical exceptions to domain exceptions without losing root causes.
5. **Define return semantics:** `null` only for EOF/filtering per contract; never to mask errors.
6. **Choose retry/skip/fail:** set retry limits, skip limits, and backoff per business rules.
7. **Decide rollbacks:** use `noRollback` only when the transaction needs no undo.
8. **Review side effects:** identify non-transactional actions needing idempotency/outboxes.
9. **Design auditing/logging:** log business keys and correlation IDs; omit unnecessary secrets/payloads.
10. **Test every boundary:** assert exception classes, causes, listeners, rollbacks, retries, skips, and outputs.
11. **Test restarts:** verify checkpoints and resources recover cleanly after failures.
12. **Monitor production:** track retry/skip/failure metrics and alert by root-cause category.

## 41. Principles to Remember

- An exception contract defines error types, meanings, causes, context, and caller handling.
- `ItemReader` returns `null` at EOF; never return `null` to mask timeouts or parse failures.
- `ItemProcessor` returns `null` for intentional filtering; processing failures must throw exceptions.
- `ItemWriter` must throw exceptions when unable to fulfill write contracts; never swallow errors and advance checkpoints.
- `ItemStream` uses `ItemStreamException` for `open`/`update`/`close` failures.
- `Tasklet` throws exceptions when `execute` fails; `RepeatStatus` signals completion or continuation.
- Preserve causes when wrapping technical exceptions into domain exceptions.
- Retry is for recoverable errors; skip is for safely omittable items; configuration errors should normally fail.
- `noRollback`, retry, and skip are independent decisions; `noRollback` does not turn exceptions into success.
- Non-transactional side effects require idempotency, outboxes, staging, or reconciliation.
- Listeners should observe/audit per contract without masking root errors or arbitrarily altering status.
- `ExitStatus` and `BatchStatus` do not replace exception types.
- Exception messages must supply enough context without exposing secrets or sensitive payloads.
- Tests must verify types/causes and retry/skip/rollback/restart behaviors, not merely that an exception happened.

A clear exception contract integrates custom components cleanly with Spring Batch fault tolerance. When every component separates EOF, filtering, and failure; when exceptions preserve root causes; and when retries, skips, rollbacks, and side effects are designed consistently, jobs recover predictably without hiding errors or corrupting data.
