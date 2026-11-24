# Do Not Log Entire Sensitive Data in Spring Batch

When a Spring Batch job processes thousands or millions of records, logging is essential to know whether the job has started, which step failed, how many items were read/written, whether retries or skips occurred, and what category an error belongs to. However, printing the entire item on every read, process, or write can accidentally turn logs into a copy of production data: account numbers, addresses, phone numbers, payment details, tokens, customer profiles, and other internal fields.

**Lesson principle: log enough information for operational investigation, but never log entire sensitive payloads.** The most sustainable approach is to **define an allowlist of fields permitted in logs**, and deliberately construct observability events from those safe fields. Masking a few strings with regex is only a secondary safeguard, because sensitive content can hide in objects, exceptions, stack traces, HTTP client logs, SQL bind parameters, or Spring Batch metadata.

In the context of **Spring Batch Core Processing → Logging**, pay special attention to every data touchpoint: `ItemReader`, `ItemProcessor`, `ItemWriter`, listeners, `JobParameters`, `ExecutionContext`, fault tolerance (skip/retry), `JobRepository`, and asynchronous execution paths. The Java examples below use Spring Batch 5.x+ APIs (writers receive `Chunk`), Java 17+, and logging via SLF4J.

## 1. Why Logging Entire Items Is a Problem

Suppose an input file contains payment records:

~~~csv
payment_id,customer_name,email,account_number,amount
PAY-001,Nguyen An,an@example.test,1234567890123456,250000.00
PAY-002,Tran Binh,binh@example.test,9876543210987654,750000.00
~~~

These two rows use synthetic data for illustration. In a real environment, if a reader or processor runs:

~~~java
log.info("Read item: {}", item);
~~~

and `item.toString()` includes every field, the read step alone pushes customer names, emails, and account numbers into the logging system. If a job restarts after an error or retries multiple times, the same record can appear in logs repeatedly.

Potential consequences:

- People with log-viewing access who **do not have permission to view source data** can still read sensitive details.
- Logs are replicated across stdout, Docker/Kubernetes logging, collectors, search engines, dashboards, alerts, support tickets, and error-tracking tools.
- Log retention may outlive the data processing window; data copied across multiple systems is hard to delete consistently.
- An exception containing an entire input line or a SQL statement with parameters can leak data even without a direct `log.info(item)` call.
- Overly verbose logs bury real errors in millions of lines and drive up storage and processing costs.

Safe logging is therefore both a data-protection requirement and a way to make monitoring more useful. Instead of viewing full payment contents, operators usually only need to know **which job, which execution, which step, what error type, how many items, and at what position**.

## 2. Defining What Data Is Allowed in Logs

A system should classify data by sensitivity level and intended use. The table below is a design example and does not replace your organization's specific data classification policy or legal obligations.

| Information Category | Examples | Recommended Log Handling |
|---|---|---|
| Authentication secrets | Passwords, API keys, bearer tokens, session cookies, signing secrets | **Never log values** in logs or stack traces; use error-category codes and component names instead. |
| Personally identifiable data | Full names, emails, phone numbers, addresses, national IDs | Omit by default; use minimized info or tokens only when genuinely required. |
| Payment/financial data | Account numbers, card numbers, transaction records, balances | Never dump items; counts and policy-compliant totals are usually sufficient. |
| Confidential business data | Contract prices, partner info, fee formulas, internal records | Treat as sensitive per contract and access controls. |
| Unvalidated input content | Full CSV lines, JSON payloads, XML fragments, HTTP bodies | Never log verbatim; may contain sensitive fields or control characters. |
| Batch metadata | `jobName`, `stepName`, `jobExecutionId`, `stepExecutionId`, item/skip/rollback counts | Generally safe to log once verified free of payloads. |
| Observability identifiers | `correlationId`, `requestId`, `triggerType` | Useful when safe tokens; validate format and ensure no PII. |
| Standardized error codes | `FILE_FORMAT`, `VALIDATION_FAILED`, `DB_TIMEOUT` | Well-suited for filtering, statistics, and alerting. |

An **internal transaction code** can still be sensitive if it allows unintended lookup of customer data. Never assume “if it's not an email, it must be safe”. The simplest approach is to define a safe metadata set by contract and keep everything else out of loggers.

### Specific Goal of Batch Logging

An event log can report:

~~~json
{
  "event": "batch.step.completed",
  "jobName": "paymentImportJob",
  "jobExecutionId": 8102,
  "stepName": "importPaymentsStep",
  "stepExecutionId": 9204,
  "status": "COMPLETED",
  "readCount": 1500,
  "writeCount": 1498,
  "readSkipCount": 1,
  "processSkipCount": 1,
  "writeSkipCount": 0
}
~~~

This is an example of an **application-defined log schema**, not JSON emitted automatically by Spring Batch. The counters show processing volume and error locations without names, emails, or account numbers. To tie a failure back to an incoming request, add a safe `correlationId`, then use `jobExecutionId` to inspect `JobRepository`.

## 3. Common Data Leak Points in the Pipeline

Spring Batch processes items along a standard pipeline:

~~~mermaid
flowchart LR
    A["Data Source"] --> B["ItemReader"]
    B --> C["ItemProcessor"]
    C --> D["ItemWriter"]
    D --> E["Database / file / API"]
    B -. parse error .-> F["Listeners / logger"]
    C -. validation error .-> F
    D -. write error .-> F
    F --> G["Stdout / log collector / dashboard"]
~~~

Points to audit:

| Log Source | Risky Statement or Behavior | Problem |
|---|---|---|
| `ItemReader` | `log.debug("item={}", item)` | Invokes `item.toString()`, potentially printing the entire row. |
| `ItemProcessor` | `log.warn("Invalid customer: {}", item)` | Validation error exposes unrelated fields as well. |
| `ItemWriter` | `log.error("Failed chunk: {}", chunk)` | A single chunk can hold hundreds of sensitive items. |
| `ItemReadListener.onReadError` | `log.error("Read failed", exception)` | File parse exceptions may include the raw input line. |
| `ItemProcessListener.onProcessError` | `log.error("Bad item {}", item, exception)` | Exposes both the item and whatever the exception carries. |
| `ItemWriteListener.onWriteError` | `log.error("Write failed {}", items, exception)` | Prints the whole `Chunk` and stack trace with payloads. |
| `SkipListener` / retry listener | Logging every skipped or retried item | Sensitive data may be repeated multiple times. |
| `JobParameters` / `ExecutionContext` | Dumping the full state map | Exposes input parameters, paths, metadata, or developer-saved state. |
| JDBC/JPA infrastructure | Debug SQL, bind parameters, constraint errors | Can expose column values or connection details. |
| HTTP/message clients | Debugging request/response bodies, headers | Can expose tokens, processed payloads, or external system data. |
| Monitoring/tracing | Attaching entire items as span attributes | Sends sensitive data to the tracing backend. |

**The danger does not come solely from code you write.** Libraries with DEBUG/TRACE enabled, API client interceptors, error-reporting SDKs, JSON formatters, and log collection pipelines can all emit payloads.

## 4. Common Anti-Patterns in Spring Batch

### 4.1. Logging Items Directly

~~~java
// Not recommended when item contains sensitive information:
log.info("Processing payment: {}", payment);
~~~

With Java records or Lombok `@Data`, `toString()` typically includes all fields. When the model gains a new field such as `accessToken`, an old log statement can suddenly leak new data without anyone touching logging code.

Replace with behavior-describing info:

~~~java
log.debug("Processing payment record");
~~~

In high-volume pipelines, one log line per record can still cause overload. When item-level investigation is unnecessary, log counts per chunk/step. When linking an individual item is required, consider an **opaque record reference** issued by the system and vetted for safety.

### 4.2. Printing an Entire Chunk on Write Failure

~~~java
// Can expose dozens or hundreds of records:
log.error("Chunk write failed: {}", chunk);
~~~

Replace with:

~~~java
log.warn("batch.write.failed category={} chunkItemCount={}",
    "DATA_CONSTRAINT",
    chunk.size());
~~~

`chunk.size()` is operational metadata. Never print `chunk.getItems()` or serialize the chunk to JSON just to find out where an error happened.

### 4.3. Printing Exceptions Without Controlling Content

~~~java
// Exception may contain raw input, SQL parameters, or HTTP body:
log.error("Cannot parse input", exception);
~~~

In Java logging, a trailing `Throwable` argument tells the logger to print the stack trace and messages across the entire cause chain. That helps when diagnosing technical bugs, but **cannot be assumed safe** when the exception was constructed by a parser or SDK from sensitive input.

Replace in the standard log stream with:

~~~java
log.warn("batch.read.failed category={} lineNumber={}",
    "FILE_FORMAT",
    17);
~~~

For incidents that genuinely require a stack trace, classify the exception source first and route it to a **diagnostic channel with controlled access, retention, and content filtering**; never ship raw exceptions containing customer data straight to general centralized logs.

### 4.4. Using All of JobParameters for Tracing

~~~java
// Not recommended by default:
log.info("Job parameters: {}", jobExecution.getJobParameters());
~~~

`JobParameters` may hold file paths, partner names, customer identifiers, or other values supplied by the caller. Likewise, `ExecutionContext` can store state saved by readers/writers or application code for restart.

Replace with pre-selected fields:

~~~java
log.info("Job started jobName={} jobExecutionId={}",
    jobExecution.getJobInstance().getJobName(),
    jobExecution.getId());
~~~

Include a business key only after confirming it contains no PII or secret values.

## 5. Allowlisting: Log Only Approved Fields

There are two main strategies:

**Denylist/redaction:** Allow logging objects, then search for and mask fields that look like emails, tokens, or account numbers.

**Allowlist:** Construct log records strictly from fields known to be safe, such as `jobExecutionId`, `stepName`, `errorCode`, and counters.

Allowlisting is the right **primary line of defense** because when a model gains a new sensitive field, it does not automatically appear in logs. Redaction remains useful as a secondary mitigation in loggers/collectors, but regex cannot fully understand data semantics.

Example:

~~~java
record PaymentInput(
    String paymentId,
    String customerName,
    String email,
    String accountNumber,
    java.math.BigDecimal amount
) {}

// Do not build logs using payment.toString().
// Selected fields are processing metadata.
log.info("batch.item.rejected category={} stepName={}",
    "BUSINESS_VALIDATION",
    "validatePaymentsStep");
~~~

If you need to know which record failed, one pattern is storing details in an **access-controlled business data store** and logging a safe reference token. That token must neither reveal the customer ID directly nor be sequentially guessable to access data.

## 6. Safe Step Start/Finish Listener Example

For high-level monitoring, `StepExecution` already holds plenty of useful data without touching individual items: read, write, skip, rollback, and commit counts plus final status.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;
import org.springframework.stereotype.Component;

@Component
public class SafeStepLoggingListener implements StepExecutionListener {

    private static final Logger log =
        LoggerFactory.getLogger(SafeStepLoggingListener.class);

    @Override
    public void beforeStep(StepExecution stepExecution) {
        log.info(
            "batch.step.started jobExecutionId={} stepExecutionId={} stepName={}",
            stepExecution.getJobExecution().getId(),
            stepExecution.getId(),
            stepExecution.getStepName()
        );
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        log.info(
            "batch.step.finished jobExecutionId={} stepExecutionId={} " +
            "stepName={} status={} exitCode={} read={} written={} " +
            "filtered={} readSkipped={} processSkipped={} writeSkipped={} " +
            "commits={} rollbacks={}",
            stepExecution.getJobExecution().getId(),
            stepExecution.getId(),
            stepExecution.getStepName(),
            stepExecution.getStatus(),
            stepExecution.getExitStatus().getExitCode(),
            stepExecution.getReadCount(),
            stepExecution.getWriteCount(),
            stepExecution.getFilterCount(),
            stepExecution.getReadSkipCount(),
            stepExecution.getProcessSkipCount(),
            stepExecution.getWriteSkipCount(),
            stepExecution.getCommitCount(),
            stepExecution.getRollbackCount()
        );
        return null; // Preserve the current ExitStatus.
    }
}
~~~

Points to note:

- Logged fields are **execution metadata**, not `StepExecution.toString()` or item lists.
- `ExitStatus.getExitCode()` is summary information. **Do not log `getExitDescription()` by default**, because an exit description may contain a stack trace or exception message holding input data.
- Spring Batch counters reflect processing stages. `readCount` does not necessarily equal physical line count when headers, read errors, or skips exist; interpret each metric accurately.
- If step names or metadata come from untrusted input, sanitize them before logging.
- The listener must be attached to the target step, e.g. via `.listener(safeStepLoggingListener)` in `StepBuilder`.

Configuration example:

~~~java
@Bean
Step paymentImportStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<PaymentInput> reader,
        ItemProcessor<PaymentInput, PaymentOutput> processor,
        ItemWriter<PaymentOutput> writer,
        SafeStepLoggingListener safeStepLoggingListener) {

    return new StepBuilder("paymentImportStep", jobRepository)
        .<PaymentInput, PaymentOutput>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .listener(safeStepLoggingListener)
        .build();
}
~~~

This example assumes `PaymentInput`, `PaymentOutput`, and the corresponding reader/processor/writer beans exist. It focuses strictly on attaching the listener to log metadata; real job business configuration may be more complex.

## 7. Safe Logging in ItemReadListener

When reading CSV, parser exceptions can include the entire raw line. For instance, `FlatFileParseException` exposes `getInput()` for the offending input text and `getLineNumber()` for the line number. Logging `exception` or `exception.getInput()` directly can leak data the system was supposed to process only in memory.

A metadata-only listener:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.item.ItemReadListener;
import org.springframework.batch.item.file.FlatFileParseException;

public class SafeReadErrorListener
        implements ItemReadListener<PaymentInput> {

    private static final Logger log =
        LoggerFactory.getLogger(SafeReadErrorListener.class);

    @Override
    public void onReadError(Exception error) {
        if (error instanceof FlatFileParseException parseError) {
            log.warn(
                "batch.read.failed category={} lineNumber={}",
                "FILE_FORMAT",
                parseError.getLineNumber()
            );
        } else {
            log.warn("batch.read.failed category={}", "READER_ERROR");
        }
    }
}
~~~

Thus, an error on line 17 produces:

~~~text
batch.read.failed category=FILE_FORMAT lineNumber=17
~~~

Instead of:

~~~text
Could not parse line 17: PAY-019,Nguyen An,an@example.test,1234567890123456,...
~~~

**A line number is not the line's content.** It is usually enough for a team authorized to view the data source to locate the offending record in a dedicated inspection tool. For other structured sources (databases, queues, APIs), pick position metadata that does not expose payloads.

If a reader consumes multiple resources, a configured `resourceAlias` is safer than the full file path. Absolute paths can reveal usernames, infrastructure layout, or customer names embedded in filenames.

## 8. Logging in Processor, Writer, and Skip/Retry

### Processor

`ItemProcessListener.onProcessError(item, exception)` receives the failing item itself—convenient for debugging, but dangerous if concatenated into log messages. Log the **error category** and step context instead:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.item.ItemProcessListener;

public class SafeProcessErrorListener
        implements ItemProcessListener<PaymentInput, PaymentOutput> {

    private static final Logger log =
        LoggerFactory.getLogger(SafeProcessErrorListener.class);

    @Override
    public void onProcessError(PaymentInput item, Exception error) {
        // Do not log item, exception message, or exception.toString().
        log.warn("batch.process.failed category={}", "VALIDATION_OR_TRANSFORM");
    }
}
~~~

When processor errors span multiple causes, you do not need to print raw messages to tell them apart. Map exceptions to an allowlisted **standardized error code**, such as `INVALID_AMOUNT`, `MISSING_REQUIRED_FIELD`, or `UNSUPPORTED_CURRENCY`. Such codes are defined by the application and contain no actual user-supplied values.

### Writer

Starting in Spring Batch 5.x, `ItemWriteListener` receives `Chunk<? extends T>`. Never pass that chunk to a logger:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ItemWriteListener;

public class SafeWriteErrorListener
        implements ItemWriteListener<PaymentOutput> {

    private static final Logger log =
        LoggerFactory.getLogger(SafeWriteErrorListener.class);

    @Override
    public void onWriteError(
            Exception error,
            Chunk<? extends PaymentOutput> items) {
        log.warn(
            "batch.write.failed category={} attemptedItemCount={}",
            "WRITE_ERROR",
            items.size()
        );
    }
}
~~~

`attemptedItemCount` here describes the chunk size passed into the error callback, **not the number of committed items**. If the writer shares the step transaction and the error triggers a rollback, committed counts must be determined from transaction status and `StepExecution`, not inferred from this log line.

### Skip and Retry

When a step uses `.faultTolerant()`, Spring Batch may retry or skip failing items per policy. Callbacks can fire multiple times, especially when a writer rolls back and replays a chunk item-by-item to isolate the bad record.

Example `SkipListener` logging by error category:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.SkipListener;

public class SafePaymentSkipListener
        implements SkipListener<PaymentInput, PaymentOutput> {

    private static final Logger log =
        LoggerFactory.getLogger(SafePaymentSkipListener.class);

    @Override
    public void onSkipInRead(Throwable error) {
        log.warn("batch.item.skipped stage=READ category=FILE_FORMAT");
    }

    @Override
    public void onSkipInProcess(PaymentInput item, Throwable error) {
        log.warn("batch.item.skipped stage=PROCESS category=VALIDATION");
    }

    @Override
    public void onSkipInWrite(PaymentOutput item, Throwable error) {
        log.warn("batch.item.skipped stage=WRITE category=WRITE_ERROR");
    }
}
~~~

This demonstrates **not printing items**; in a real application, error classification must reflect the actual exception and skip policy. Do not label every read error `FILE_FORMAT` if the reader can also encounter connection or I/O errors.

Avoid emitting an `ERROR` log for every transient retry and then emitting another `ERROR` when the step eventually fails. Under heavy load, that creates noise and makes a single root error appear to happen repeatedly. Track retry counts via appropriate metrics/counters and emit **a single summary event** at step end while keeping enough standardized error logs for investigation.

## 9. Standardizing Error Codes Instead of Printing Exception Messages

`Throwable.getMessage()` and `Throwable.toString()` often contain uncontrolled content. Even custom application exceptions can accidentally interpolate sensitive fields:

~~~java
// Not recommended:
throw new IllegalArgumentException(
    "Invalid account number " + payment.accountNumber()
);
~~~

If the framework logs that failure, the message already leaks the account number even though no logger printed `payment` directly.

Replace with an exception/error code whose message is decoupled from sensitive data:

~~~java
throw new PaymentValidationException("INVALID_ACCOUNT_FORMAT");
~~~

An exception classifier function for logging:

~~~java
import org.springframework.batch.item.file.FlatFileParseException;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.dao.TransientDataAccessException;

static String safeErrorCode(Throwable error) {
    if (error instanceof FlatFileParseException) {
        return "FILE_FORMAT";
    }
    if (error instanceof DataIntegrityViolationException) {
        return "DATA_CONSTRAINT";
    }
    if (error instanceof TransientDataAccessException) {
        return "DATABASE_TRANSIENT";
    }
    if (error instanceof PaymentValidationException) {
        return "BUSINESS_VALIDATION";
    }
    return "UNCLASSIFIED_FAILURE";
}
~~~

`PaymentValidationException` is an illustrative application-defined exception type. With multi-layered wrapped exceptions, a real classifier can walk the cause chain **to pick an error code** without writing the message or full exception to general logs.

Error codes should belong to a clearly defined catalog; never construct code names by concatenating user-supplied values such as `"INVALID_ACCOUNT_" + accountNumber`.

### When Stack Traces Are Needed

This does not mean all stack traces are forbidden. For programming bugs like `NullPointerException` in code paths free of sensitive data, stack traces are valuable diagnostic data. Still, do not apply a blanket policy of logging every exception verbatim at every layer.

Options include:

1. Always log safe events using `errorCode`, job/step IDs, timestamp, and safe line/position metadata.
2. Keep stack traces in a diagnostic channel with strict access control and retention **after confirming the exception source does not put raw inputs or secrets into messages/causes**.
3. When inspecting the actual offending record is necessary, let authorized operators use an internal tool against the source via a reference rather than copying that row into the logging pipeline.

## 10. Redaction and Masking: Useful, Yet Not Enough

**Masking** typically obscures part of a value, such as showing only the last few characters of an identifier. **Redaction** replaces the entire value with `[REDACTED]`. Neither technique is identical to excluding the field from logs altogether.

| Approach | Sample Log Output | Limitations |
|---|---|---|
| Omit the field | `category=INVALID_ACCOUNT` | Lowest risk because the value never enters the log pipeline. |
| Full redaction | `account=[REDACTED]` | Useful when legacy formats require the field, but every log path must be covered. |
| Partial masking | `account=************3456` | Remaining characters can still re-identify when combined with other data. |
| Post-write regex filtering | Replaces email/card-like patterns | Misses unusual formats, encoded values, or new fields; raw data already passed upstream components. |
| Unkeyed hash | `sha256(email)` | Emails/phones have predictable domains; attackers can run dictionary attacks. |
| Keyed HMAC | Stable token based on an internal secret | Requires secret management/rotation and still permits record linkage; use only when correlation is truly needed. |

If business operations need to find events for the same customer without logging real emails, you can use an **internal reference token** or keyed HMAC with secrets managed by appropriate infrastructure. Even then, tokens can remain sensitive in context if they allow tracking an individual over time.

Never use `email.hashCode()` or plain SHA-256 to claim an email is “completely anonymized”. Predictable inputs are easily reversed via dictionaries or cross-referenced with external data.

### Prefer Preventing Sensitive Data at the Source

If code calls `log.info("{}", payment)` and counts on a collector regex to scrub everything, raw data has already traversed the logger, buffers, or stdout before redaction runs. A more reliable flow is:

~~~text
Domain object containing sensitive data
    |
    v
Select safe fields / standardized error code
    |
    v
Structured log event
    |
    v
Logger -> Collector -> Dashboard
~~~

For legacy systems with extensive existing logs, infrastructure-level redaction filters can serve as a temporary risk-reduction layer while refactoring applications—but they do not replace eliminating raw payload logs at the source.

## 11. JobParameters, ExecutionContext, and JobRepository

In Spring Batch, operational and restart data is stored across several layers:

- `JobParameters`: job launch arguments, which may hold input file paths, source IDs, processing dates, or caller-supplied values.
- `ExecutionContext`: serializable job/step state used for checkpoints or restarts.
- `JobExecution` and `StepExecution`: statuses, timestamps, counters, exit statuses, and related info.
- `JobRepository`: durable metadata storage, typically in `BATCH_*` tables.

**Do not turn JobParameters or ExecutionContext into secret stores.** Data persisted for execution/restart can live a long time and be read by operational tools, not just loggers.

Pattern to avoid:

~~~java
new JobParametersBuilder()
    .addString("accessToken", token, false)
    .toJobParameters();
~~~

The `false` flag only means non-identifying; it **does not encrypt, hide, or prevent the parameter from being stored in the repository**.

Instead, pass a safe reference if needed and retrieve the secret from a controlled secret management system at execution time. Never stuff secrets into `JobParameters` merely to wire `@StepScope` beans more conveniently.

Also avoid:

~~~java
log.debug("Execution context: {}", stepExecution.getExecutionContext());
log.error("Job failure details: {}",
    jobExecution.getAllFailureExceptions());
~~~

These objects can contain or reference data from processing layers and exceptions. Pick the specific counters and statuses to log rather than serializing whole objects.

## 12. SQL, HTTP, Files, and Third-Party Libraries

Even if application code never logs items, verbose logging in underlying layers can still leak data.

### JDBC/JPA

For SQL, there is a big difference between a template query with placeholders and actual bind values:

~~~sql
INSERT INTO payment(account_number, amount)
VALUES (?, ?)
~~~

This is structural SQL. However, if a logger/driver/proxy prints full bindings such as `account_number=1234567890123456`, data is still exposed. Review logging levels for JDBC, Hibernate/JPA, SQL proxies, drivers, and database-returned exceptions.

Never turn on TRACE SQL bind parameters in an environment processing real data just to investigate a batch bug. When research is needed, prefer test environments with synthetic data or strictly access-controlled diagnostics.

### HTTP Clients and Messaging

HTTP requests/responses can contain:

- `Authorization` headers, cookies, API keys.
- JSON/XML bodies carrying customer or account data.
- URL query strings containing tokens or identifiers.
- Error responses echoing back the submitted payload.

A “log full request and response” interceptor is very risky when a writer sends items individually to a partner. Configure logging to record only method, normalized endpoint name, status code, duration, and request/correlation ID—excluding sensitive headers and bodies. Apply the same caution to payloads and message headers in Kafka or queues.

### Files

`FlatFileParseException` can expose raw input via `getInput()`; never log that value. File paths can also embed sensitive information in filenames, such as customer names or personal directories. Substitute a logical `resourceId` or configured source alias.

### APM, Tracing, and Error Reporting

Never attach full items as span attributes, event annotations, or tags. Tracing pipelines can forward data to third parties or make it visible across many teams. `traceId` and `jobExecutionId` provide linkage without attaching entire records.

## 13. Correlation: Investigating Without Exposing Payloads

Safe logs still need to show which job an error belongs to. Useful observability identifiers include:

| Field | Purpose |
|---|---|
| `jobName` | Batch workflow definition. |
| `jobInstanceId` | Logical job instance, preserved across restarts of the same instance. |
| `jobExecutionId` | Specific execution attempt. |
| `stepName` / `stepExecutionId` | Pinpoints the failing processing unit. |
| `correlationId` | Links an incoming request or scheduler trigger to the execution. |
| `triggerType` | Distinguishes HTTP, SCHEDULER, MANUAL, MESSAGE. |
| `errorCode` | Standardized error category. |
| `lineNumber` / `resourceAlias` | Error location reproducible in an access-controlled data source. |

A safe log record:

~~~json
{
  "event": "batch.item.skipped",
  "jobName": "paymentImportJob",
  "jobExecutionId": 8102,
  "stepName": "importPaymentsStep",
  "stepExecutionId": 9204,
  "correlationId": "req-301",
  "category": "FILE_FORMAT",
  "resourceAlias": "daily-payments",
  "lineNumber": 17
}
~~~

There are no emails, account numbers, raw CSV lines, or data-laden stack traces. When inspecting the actual record is required, authorized staff use `resourceAlias` and `lineNumber` in the appropriate source system; there is no need to grant the entire team log access to raw customer data.

### MDC and Thread Pools

SLF4J `MDC` lets every log line on the same thread pick up `jobExecutionId` or `correlationId` without passing fields into every call:

~~~java
try {
    MDC.put("jobExecutionId", String.valueOf(jobExecution.getId()));
    MDC.put("correlationId", safeCorrelationId);
    runWork();
} finally {
    MDC.remove("jobExecutionId");
    MDC.remove("correlationId");
}
~~~

`safeCorrelationId` must be a validated/normalized ID free of arbitrary headers or personal data. `MDC` is thread-local; if a step uses a `TaskExecutor`, partitioning, or remote workers, design explicit context propagation to workers and **clear MDC** afterwards so pooled threads never carry another job's IDs.

Specifically, never put domain items or raw payloads into MDC: many libraries attach MDC to every log event, multiplying the same sensitive value thousands of times.

## 14. Structured Logging and Appropriate Log Levels

Structured logging makes searching by `jobExecutionId`, `stepName`, and `errorCode` far easier than parsing long concatenated prose lines. Yet **structured logging does not automatically make data safe**: putting `payment` into a JSON field still leaks it.

A typical log-level policy:

| Level | Example Events | Recommended Content |
|---|---|---|
| `INFO` | Job/step start, completion, read/write totals | IDs, status, counters, duration. |
| `WARN` | Item skipped, retries nearing limit, recoverable data error | Error code, processing stage, safe location, attempt count. |
| `ERROR` | Step/job failed, unrecoverable infrastructure failure | Metadata, error code, controlled diagnostics. |
| `DEBUG` | Test flow details or targeted diagnostics | Extra metadata; **never automatically permitted to log sensitive data**. |
| `TRACE` | Ultra-fine-grained info | Restricted to appropriate environments; watch SQL bind values and request bodies closely. |

**DEBUG is not exempt from data protection rules.** DEBUG can accidentally be turned on in production during an incident, so every debug log statement must be safe from the start. Never rely on the assumption that “this level will never be enabled”.

One step-end summary event is usually more helpful than thousands of per-item `INFO` lines. For high-frequency errors, apply sampling or aggregation by error code while maintaining accurate counts in appropriate metrics/counters. If sampling, never drop critical failure signals or violate operational policy.

## 15. Testing to Catch Sensitive Log Leaks

In tests, use **synthetic data that resembles sensitive data** to verify loggers never print unexpected fields. Never use real emails, account numbers, or tokens in fixtures.

One technique is capturing logger output in tests and asserting protected strings never appear. With Spring Boot Test, you can use `OutputCaptureExtension`:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.batch.item.file.FlatFileParseException;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;

@ExtendWith(OutputCaptureExtension.class)
class SafeReadErrorListenerTest {

    @Test
    void doesNotLogRawInvalidLine(CapturedOutput output) {
        String marker = "canary-secret@example.test";
        String rawInput =
            "PAY-019," + marker + ",1234567890123456,INVALID";

        FlatFileParseException exception = new FlatFileParseException(
            "Bad record: " + rawInput,
            rawInput,
            17
        );

        new SafeReadErrorListener().onReadError(exception);

        assertThat(output.getAll())
            .contains("category=FILE_FORMAT")
            .contains("lineNumber=17")
            .doesNotContain(marker)
            .doesNotContain("1234567890123456")
            .doesNotContain(rawInput);
    }
}
~~~

This test deliberately puts the same synthetic value in both raw input **and the exception message**. If someone changes the listener to `log.error("...", exception)` or `log.warn("{}", exception.getInput())`, the test catches the leak immediately.

Note: capture behavior depends on logging configuration and the test runner; if a logger writes to an external collector bypassing captured streams, test against that actual appender/sink. The goal is verifying **actual emitted log events**, not merely grepping source code for disallowed calls.

### Scenarios to Include in Logging Tests

| Scenario | Synthetic Data | Log Expectation |
|---|---|---|
| CSV parse error in reader | Line with fake email, account, malformed value | Logs category + line number, no raw input. |
| Validation error in processor | Item containing name, email, amount | Logs error code, no `item.toString()`. |
| JDBC error in writer | Chunk containing multiple fake accounts | Logs chunk size and error type, no item list. |
| HTTP writer gets 4xx/5xx | Request carrying fake Authorization | Logs status code and endpoint alias, no token/body. |
| Retry and skip | Item retried several times | Does not spray payloads per callback; summary counts stay useful. |
| JobParameters with fake secret | `accessToken=TEST_ONLY_SECRET` | Never logs full parameter map; never stores real secrets in metadata. |
| Job restart | New JobExecution ID for same JobInstance | Logs accurate IDs without duplicating raw data. |
| Multi-threaded step | Concurrent tasks in a thread pool | MDC never mixes execution IDs and holds no items. |
| Framework debug loggers | Enable loggers capable of printing binds/bodies in test | Inspect log output and level configuration before deployment. |

For strict environments, use dedicated canary values in integration tests to scan log files, stdout, and tracing sinks. Never feed real sensitive data into test environments or log analysis sandboxes.

## 16. Access Control, Retention, and the Log Pipeline

Minimizing data at the source is the primary control, yet operational policy must still govern the **entire path**:

~~~text
Spring Batch JVM
   |
   +--> stdout / local log file
   |       |
   |       v
   +--> log shipper / sidecar
           |
           v
       log collector
           |
           v
       search index / dashboard / alert / export
~~~

If sensitive data is written at step one, every downstream stage can become a replica store. Therefore:

- **Role-based log access:** never equate permission to view logs with permission to view all customer data.
- **Retention and deletion lifecycle:** set log TTLs aligned with investigation needs and regulations; enforce deletion/redaction for data that should not persist.
- **Protect data in transit and at rest:** apply logging infrastructure security controls per organizational policy.
- **Govern exports and alerts:** alerts sent via chat/email should contain error codes and dashboard links, never raw payloads.
- **Bound user-supplied log values:** headers, paths, and query strings can contain newlines/control characters; sanitize to prevent log injection.
- **Control dumps and snapshots:** heap dumps, crash reports, or test file copies can retain data barred by logging policy.

Even after masking, records can still be linked using external sources. Assess re-identification risk and keep only fields that genuinely serve operations.

## 17. When You Must Investigate an Exact Failing Record

A practical requirement is: “I need to know which item was skipped so I can fix the data, without putting emails or account numbers in logs.” The right solution is **separating the observability channel from the sensitive-data handling channel**.

Example:

1. The reader detects malformed data on line 17.
2. The listener logs: `jobExecutionId=8102`, `stepName=importPaymentsStep`, `resourceAlias=daily-payments`, `lineNumber=17`, `errorCode=FILE_FORMAT`.
3. An access-controlled internal tool lets the data steward open the exact source at that position.
4. The operator fixes the record inside an audited system with proper permissions instead of pasting the failing row into chat or logs.
5. On rerun, monitor by JobInstance/JobExecution and confirm processed/skipped counts after remediation.

For queue or database inputs that lack line numbers, use an **opaque record reference** or source-assigned event ID if policy permits. Never use emails or phone numbers as correlation IDs. Never log `toString()` of a key when that key embeds confidential business data.

If rejected records must be stored for analysis, use a **quarantine/dead-letter store** built for sensitive data, with strict access controls and clear retention. Logs carry only a reference token to the rejected record and a standardized reason. Quarantine writes with separate transactions/retries must be designed so duplicate records are not created unintentionally.

## 18. Common Implementation Misconceptions

**“I only log at DEBUG, so production won't see it.”** DEBUG can be enabled during incident triage; logging code still has to be safe. For library loggers, check which ones turn on TRACE bind values or request bodies.

**“I already masked the email, so logging the whole item is fine.”** Items also contain names, accounts, addresses, newly added secret fields, and other business data. Regex does not understand object structure.

**“I don't log the item, only the exception.”** Parse exceptions, validation messages, or HTTP client exceptions can embed the raw item itself. Sanitize exception messages and cause chains before logging.

**“`@ToString.Exclude` is enough.”** Serializers, custom loggers, nested objects, other records, or lower-layer errors can still print payloads. `@ToString.Exclude` helps as defense-in-depth, not as a substitute for allowlisting.

**“Non-identifying JobParameters aren't stored.”** False. Non-identifying only changes how `JobInstance` identity is computed; parameters can still be persisted in `JobRepository` metadata.

**“Logging the whole ExecutionContext helps debug restarts.”** `ExecutionContext` can hold unvetted application state and is serialized durably. Log safe state keys or normalized progress instead of dumping the map.

**“Hashing emails makes them anonymous.”** Unkeyed hashes of predictable values can be cracked; even stable tokens can link activity across runs. Use tokenization/HMAC only when explicitly required and properly governed.

**“A full stack trace is always required to troubleshoot.”** Many failures can be diagnosed from `errorCode`, location, job IDs, and metrics. When a stack trace is truly needed, control the storage channel and strip payload risks.

**“Without logging sensitive data, you can't find the bad item.”** Line numbers, resource aliases, opaque record references, and separate authorized data tools solve this. Logs **locate** the problem; permissioned stores let you **inspect contents** when needed.

## 19. Workflow for Applying This to a Spring Batch Job

For a new job or when hardening an existing one, follow these steps:

1. **Inventory sensitive data read/processed/written by the job.** Inspect models, files, DB columns, API payloads, headers, and exception contents.
2. **Define safe log fields.** Start with `jobName`, execution IDs, step IDs, status, counters, error code, validated correlation ID, and safe data position.
3. **Replace object/chunk/exception dumps** with allowlist-based structured events. Never log item `toString()`, full `JobParameters`, or `ExecutionContext`.
4. **Add Step/Job listeners for summary logs.** Log read/write/skip/rollback counts and final status to reduce per-item logging needs.
5. **Audit parser, writer, HTTP client, and JDBC errors.** Verify whether messages, stack traces, or debug loggers carry raw inputs or bind values.
6. **Design a separate data-error handling channel.** Use resource aliases, line numbers, or reference tokens alongside an access-controlled quarantine store.
7. **Control MDC/tracing propagation.** Forward safe IDs across async/remote workers and clear thread context afterwards.
8. **Test for leaks using synthetic canary data.** Exercise happy paths, parse failures, skip/retry, writer exceptions, and restarts; inspect the real log sink.
9. **Govern the log pipeline.** Enforce RBAC, retention, alerts, exports, and secondary filters while reviewing third-party libraries.

### Key Takeaway

> **Log processing events, not processing records.** Logging IDs and statuses is enough to pinpoint the execution; sensitive data stays in authorized source and target systems.

A useful log answers **when**, **which job**, **which step**, **what kind of error**, **how many items were affected**, and **how to find the source to fix**. It never needs to copy emails, account numbers, tokens, or entire data rows into a broadly accessible observability system.

## Conclusion

In Spring Batch, the practice of **never logging entire sensitive data** must span `ItemReader`, `ItemProcessor`, `ItemWriter`, listeners, parse/skip/retry failures, `JobParameters`, `ExecutionContext`, JDBC/HTTP libraries, and centralized log infrastructure. The core solution is **allowlisted safe metadata**, standardized error codes, job/step-level summary logs, and correlation IDs for tracing without printing payloads.

Masking, redaction, encryption, and log access control all play supporting roles, but the strongest risk reduction is **preventing sensitive data from entering loggers in the first place**. When observability data is cleanly separated from business payloads, operations teams can still troubleshoot failures, run restarts, and monitor batch health without turning logs into a second customer database.
