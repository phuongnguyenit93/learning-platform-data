# Safe Error Item Logging in Spring Batch

When a batch job processes thousands or millions of records, knowing **which item failed, which step the error occurred in, and whether it was retried or skipped** is essential for incident investigation. However, writing the entire item or raw exception straight to logs can expose customer information, account numbers, tokens, order details, file contents, and other sensitive fields. Logs are often forwarded to centralized platforms, retained longer than source data, and accessible to a broader audience.

This lesson under **Spring Batch Core Processing → Logging** shows how to **safely log failed items** during reading, processing, and writing; design structured events; identify items via protected reference tokens; pick the right listener for retry/skip states; prevent exceptions from leaking payloads; test that forbidden fields never appear in logs; and operate a controlled logging pipeline.

The examples use **Java 17, Spring Boot 3.x, Spring Batch 5.x, SLF4J, and JUnit 5**. Illustrative business class names and data policies must be adapted to your actual application.

## 1. Goals of Safe Error Logging

A good log line should answer:

1. **Where did the error happen?** Job, step, and `read`/`process`/`write` stage.
2. **Which category does the error belong to?** A stable, aggregatable error code such as `INVALID_ORDER` or `REMOTE_TIMEOUT`.
3. **Which execution was affected?** `JobExecutionId`, business date, or an approved correlation ID.
4. **Which item needs investigation?** A controlled reference code or token for lookup in an authorized data store.
5. **What was the processing outcome?** A retry attempt, a skipped item, or a failed step/job.

At the same time, logs must **not** allow reconstructing secret information from what was recorded.

Risky logging examples:

```java
log.error("Failed order: {}", order);
log.error("Cannot process order {}", order, error);
log.warn("Customer email={}, card={}",
        order.customerEmail(), order.cardNumber());
```

For Java `record`s, `toString()` prints every field. For exceptions, `getMessage()`, `toString()`, or stack traces can contain SQL statements, query parameters, HTTP URLs, or sensitive response bodies. Using SLF4J `{}` placeholders **does not automatically make data safe**.

A safer log entry:

```text
event=batch_item_skipped
job=dailyOrdersJob
step=validateOrdersStep
stage=process
business_date=2026-11-16
record_ref=8a62b97f4d21d5a7
error_code=INVALID_ORDER
```

`record_ref` in this example is a protected reference token, **not** the customer ID or raw data content. To investigate details, authorized personnel use this token in a secure lookup tool or locate the item in the original source.

## 2. Classifying Data Before Logging

The single most important rule is **allowlisting**: only allow vetted fields to enter logs. Do not take an object with many fields and try to scrub sensitive ones with a denylist.

| Data | Recommended Handling | Reason |
| --- | --- | --- |
| Fixed job/step names | Safe to log | Helps isolate the failing flow |
| `JobExecutionId`, `StepExecutionId` | Safe to log per internal policy | Points to batch metadata |
| Fixed error codes like `INVALID_ORDER` | Safe to log | Supports search and aggregation |
| Stage `read`, `process`, `write` | Safe to log | Distinguishes error location |
| `businessDate`, `region` | Only when approved and normalized | Some systems treat business parameters as sensitive |
| Record ID, customer ID, order ID | Consider tokenization/HMAC or approved public IDs | IDs can also be personal data or enable user correlation |
| Email, phone number, address, account number | Never log verbatim | Can identify or link individuals |
| Passwords, API keys, access tokens, secrets | Never log | Risk of exposing access credentials |
| CSV/JSON/XML contents, SQL parameters, HTTP bodies | Never log verbatim | Often contain unclassified fields |
| `Throwable.getMessage()`, raw stack traces | Route only to controlled channels after appropriate safeguards | Exceptions often carry input or external system content |

### 2.1. Why Partial String Masking Is Not Always Enough

For example, `email=a***@example.com` can still identify a user when combined with date, region, and other IDs. Similarly, applying `hashCode()`, MD5, or unsalted SHA-256 directly to an email can be reversed via dictionary attacks because the value space of emails, phone numbers, or IDs is predictable.

If you need a stable code to correlate an item across log lines, you can use **HMAC-SHA-256 with a separately managed secret key**, truncating enough of the digest for your data scale and controlling key access. HMAC makes recovering the original value much harder than an unkeyed hash; however, it remains **linkable data** and must obey retention, access, and log TTL rules. If item correlation is not needed, omitting any reference altogether may be the better option.

## 3. Designing a Structured Error Event

Define a clear log schema instead of free-form sentences containing raw error text:

```json
{
  "event": "batch_item_skipped",
  "job": "dailyOrdersJob",
  "step": "validateOrdersStep",
  "job_execution_id": 78241,
  "stage": "process",
  "business_date": "2026-11-16",
  "record_ref": "8a62b97f4d21d5a7",
  "error_code": "INVALID_ORDER",
  "outcome": "SKIPPED"
}
```

This is an **illustrative data sample**, not default output generated by Spring Batch. It can be implemented with a JSON layout/structured logging or `key=value` messages with fixed fields.

Design properties:

- **Consistent field names:** always use `event`, `stage`, `error_code`, and `record_ref` rather than inventing different names per step.
- **Enum/allowlisted values:** use only safe values like `PROCESS`, `READ`, `WRITE`, `INVALID_ORDER`, `REMOTE_TIMEOUT`, avoiding unvetted free text.
- **Minimal references:** include `record_ref` only when item tracing is required and lookup access controls exist.
- **Execution context:** use `JobRepository` IDs to tie logs to batch history instead of dumping full `JobParameters`.
- **Distinct events:** `batch_item_retry`, `batch_item_skipped`, `batch_step_failed`, and `batch_step_completed` carry distinct semantics.

If logs feed into a metrics system, **never use `record_ref`, `JobExecutionId`, or exception messages as labels/tags**: high value counts spike cardinality, raise storage costs, and can leak data. Metrics should aggregate by `job`, `step`, `stage`, and `error_code`.

## 4. Choosing the Right Moment to Log in the Chunk Lifecycle

In Spring Batch, errors can occur in `ItemReader.read()`, `ItemProcessor.process()`, or `ItemWriter.write(...)`. With `faultTolerant()` and retry/skip policies, an initial exception **does not necessarily fail the job**.

| Callback / Mechanism | When Invoked | What to Log |
| --- | --- | --- |
| `ItemReadListener.onReadError(Exception)` | Read attempt fails | Failed read attempt event, safe error code; item ID is usually unavailable |
| `ItemProcessListener.onProcessError(item, exception)` | A processor invocation fails | Failed attempt event; avoid concluding the item was skipped |
| `ItemWriteListener.onWriteError(exception, chunk)` | A writer invocation fails | Failed write event; note that a chunk can hold multiple items |
| `SkipListener.onSkipInRead(Throwable)` | Framework decides to skip a read error | Read-phase skip event, typically without an item |
| `SkipListener.onSkipInProcess(item, Throwable)` | An item is skipped in the processor | Item skip event with a protected reference token |
| `SkipListener.onSkipInWrite(item, Throwable)` | An item is skipped in the writer | Item skip event with a protected reference token |
| `StepExecutionListener.afterStep(stepExecution)` | Step has finished | Summary of `readCount`, `writeCount`, `skipCount`, `rollbackCount`, status |
| `JobExecutionListener.afterJob(jobExecution)` | Job has finished | Overall result, execution ID, status, and summary error code |

**Do not equate “a failed attempt” with “a skipped item”.** For example, an API call times out on attempt 1, then succeeds on retry attempt 2; if you log in `onProcessError`, an error event appears even though the item ultimately wrote successfully. If your goal is the final list of skipped items, `SkipListener` is far more accurate.

In a fault-tolerant step, Spring Batch invokes `SkipListener` according to its skipped-item mechanism, typically right before the associated transaction commits. However, **logs are not part of the business transaction**: when a transaction rolls back, messages already emitted to the logger do not roll back. Never build accounting reports or exact-count guarantees by counting log lines.

```text
Item → process
          |
          ├── attempt 1: transient error → retry diagnostic (if enabled)
          ├── attempt 2: success         → writer
          |                                └── no skip
          |
          └── unrecoverable error / retry limit exhausted
                                      |
                            is skip configured?
                             |           |
                            Yes          No
                             |           |
                        SkipListener    Step FAILED
```

## 5. Generating Item Reference Tokens with HMAC Instead of Logging Raw IDs

Example input model for an order-processing job:

```java
package com.example.batch;

import java.math.BigDecimal;

record OrderInput(
        String orderId,
        String customerEmail,
        BigDecimal amount) {}

record OrderOutput(
        String orderId,
        BigDecimal approvedAmount) {}
```

**Do not call `log.info("{}", order)` on these two records**: `record.toString()` puts all components into the log. We only use `orderId` inside code to compute the token, while the log output contains no raw value.

`SafeRecordToken.java`:

```java
package com.example.batch;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class SafeRecordToken {

    private final SecretKeySpec secretKey;

    public SafeRecordToken(byte[] keyBytes) {
        if (keyBytes == null || keyBytes.length < 32) {
            throw new IllegalArgumentException(
                    "HMAC key must contain at least 32 bytes");
        }
        this.secretKey = new SecretKeySpec(
                keyBytes.clone(), "HmacSHA256");
    }

    public String fromIdentifier(String identifier) {
        if (identifier == null || identifier.isBlank()) {
            return "unavailable";
        }
        try {
            // Create a new Mac per call: Mac is not thread-safe.
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(secretKey);
            byte[] digest = mac.doFinal(
                    identifier.getBytes(StandardCharsets.UTF_8));

            // First 12 bytes = 96 bits; choose length based on usage scale.
            return HexFormat.of().formatHex(digest, 0, 12);
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException(
                    "Could not calculate record reference");
        }
    }
}
```

Each `orderId` yields the same token under the same key, enabling correlation without printing the original ID. 96 bits is used as an example providing a large space for most log-reconciliation needs; you still need to evaluate collision risk, record volume, and specific security policies.

Operations should:

- Generate a sufficiently strong random key in a secret manager; **never hardcode** keys in source code or production test fixtures.
- Never log the key, configuration value, or HMAC input.
- Restrict key usage scope and token-lookup permissions; separate test and production environments.
- Plan for rotation: changing the key changes the token for the same ID. If you must search logs across rotations, include a **non-sensitive key version** in the log schema and maintain a controlled lookup tool.
- Consider adding namespace identifiers (`tenant`, `job`) to the HMAC input so the same ID is not unintentionally linkable across systems.

HMAC **does not encrypt** the ID and is not a decryptable mechanism. Looking up details from a token requires a tool with access to the source data and the same algorithm/key for matching, or storing a protected mapping in a separate store.

## 6. Classifying Exceptions into Safe Error Codes Only

Exceptions thrown by JDBC, HTTP, or business validation may carry raw payloads inside `getMessage()`. Instead of logging the message, build a classifier that returns only predefined error codes.

```java
package com.example.batch;

final class InvalidOrderException extends RuntimeException {
    InvalidOrderException(String detail) {
        super(detail);
    }
}

final class TemporaryPartnerException extends RuntimeException {
    TemporaryPartnerException(String detail) {
        super(detail);
    }
}

public final class SafeErrorCodes {
    private SafeErrorCodes() {}

    public static String of(Throwable error) {
        Throwable current = error;

        // Inspect a controlled number of wrapper layers.
        for (int depth = 0; depth < 4 && current != null; depth++) {
            if (current instanceof InvalidOrderException) {
                return "INVALID_ORDER";
            }
            if (current instanceof TemporaryPartnerException) {
                return "PARTNER_TEMPORARY_FAILURE";
            }
            current = current.getCause();
        }

        return "UNCLASSIFIED_FAILURE";
    }
}
```

This code deliberately **does not return** `error.getMessage()`, unapproved class names, or SQL/HTTP error text. For real errors, you can extend the mapping by vetted exception types, SQLState, or HTTP status codes if those fields are confirmed safe. Unknown errors fall back to the generic `UNCLASSIFIED_FAILURE` code and are tracked through an appropriate investigation channel.

If stack traces are needed for deep diagnostics, do not simply enable `log.error(..., exception)` on the general logger. Use a restricted channel with short retention, tight access controls, and sensitive-data stripping; even stack traces must be evaluated because some exceptions embed request/response or query details.

## 7. Logging Skipped Items with `SkipListener`

In Spring Batch 5, `SkipListener<I, O>` has three callbacks covering read, process, and write phases. A safe implementation:

```java
package com.example.batch;

import java.time.LocalDate;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.SkipListener;

public final class SafeOrderSkipListener
        implements SkipListener<OrderInput, OrderOutput> {

    private static final Logger log =
            LoggerFactory.getLogger(SafeOrderSkipListener.class);

    private final SafeRecordToken recordToken;
    private final String businessDate;

    public SafeOrderSkipListener(
            SafeRecordToken recordToken, String businessDate) {
        this.recordToken = recordToken;
        // Normalize date to ISO, avoiding arbitrary CLI strings in logs.
        this.businessDate = LocalDate.parse(businessDate).toString();
    }

    @Override
    public void onSkipInRead(Throwable error) {
        // No reliable item is available to extract an ID in this callback.
        logSkip("read", "unavailable", error);
    }

    @Override
    public void onSkipInProcess(OrderInput item, Throwable error) {
        logSkip("process",
                recordToken.fromIdentifier(item.orderId()), error);
    }

    @Override
    public void onSkipInWrite(OrderOutput item, Throwable error) {
        logSkip("write",
                recordToken.fromIdentifier(item.orderId()), error);
    }

    private void logSkip(
            String stage, String reference, Throwable error) {

        // Do not pass the item or Throwable into the logger.
        log.warn(
                "event=batch_item_skipped job=dailyOrdersJob "
                + "step=validateOrdersStep business_date={} "
                + "stage={} record_ref={} error_code={}",
                businessDate,
                stage,
                reference,
                SafeErrorCodes.of(error));
    }
}
```

The `stage`, `job`, and `step` values here are constants. If an application has multiple jobs/steps, supply names through configuration or normalized metadata rather than logging an untrusted user parameter directly. If `jobExecutionId` is needed, read it from `StepExecution` in the step context or pass it via an appropriately scoped listener; **never store mutable `StepExecution` from multiple runs on a singleton shared across parallel jobs**.

`onSkipInRead` differs from `onSkipInProcess` and `onSkipInWrite`: when a read error occurs, the reader has not necessarily produced an item, so the callback receives no ID. Logging the raw data line, file row, or input buffer here can leak data; if the reader supports it, log an approved resource alias and permitted technical position.

### 7.1. Attaching the Listener to a Fault-Tolerant Step

Example bean configuration for use in a job:

```java
package com.example.batch;

import java.util.Base64;

import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class OrdersStepConfig {

    @Bean
    SafeRecordToken safeRecordToken(
            @Value("${batch.logging.hmac-key-base64}") String keyBase64) {
        return new SafeRecordToken(
                Base64.getDecoder().decode(keyBase64));
    }

    @Bean
    @StepScope
    SafeOrderSkipListener safeOrderSkipListener(
            SafeRecordToken token,
            @Value("#{jobParameters['businessDate']}")
            String businessDate) {
        return new SafeOrderSkipListener(token, businessDate);
    }

    @Bean
    Step validateOrdersStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            ItemReader<OrderInput> reader,
            ItemProcessor<OrderInput, OrderOutput> processor,
            ItemWriter<OrderOutput> writer,
            SafeOrderSkipListener skipListener) {

        return new StepBuilder("validateOrdersStep", jobRepository)
                .<OrderInput, OrderOutput>chunk(100, transactionManager)
                .reader(reader)
                .processor(processor)
                .writer(writer)
                .faultTolerant()
                .retry(TemporaryPartnerException.class)
                .retryLimit(3)
                .skip(InvalidOrderException.class)
                .skipLimit(20)
                .listener(skipListener)
                .build();
    }
}
```

`ItemReader`, `ItemProcessor`, and `ItemWriter` here are business beans **assumed to be provided** by the application. The job name `dailyOrdersJob` used in the listener must match the actual job of the example.

The HMAC key configuration property can be declared as:

```properties
# Contains only the referenced environment variable name; do not commit secrets to Git.
batch.logging.hmac-key-base64=${BATCH_LOG_REF_KEY_B64}
```

The environment variable should be injected from a secret manager or infrastructure secret mechanism. With Spring Boot, restrict actuator/configuration endpoints and environment-reading privileges so the key is not exposed. In high-security systems, supply keys through a controlled secret provider and limit how keys are held in memory.

The example configuration defines two distinct policies:

- `TemporaryPartnerException` is **retried** up to three attempts, including the first attempt. If it eventually succeeds, no skip event is emitted for that item.
- `InvalidOrderException` is allowed to **skip** up to 20 items under the policy. When an item is actually skipped, `SafeOrderSkipListener` logs a safe event.

When an error cannot be retried or skipped per policy, the step can end `FAILED`. Avoid catching every exception and returning `null` just to “keep the job running”: doing so hides failure states and blurs discarded items with valid filtered records.

## 8. Logging on Retry, Failure, and Rollback

### 8.1. A Retry Is an Attempt, Not the Final Outcome

Suppose `order-007` calls an external service:

```text
attempt 1: TemporaryPartnerException
attempt 2: TemporaryPartnerException
attempt 3: success
```

On the third attempt, the item is written successfully. If you log `ERROR: item failed` on the first two attempts without marking them as a **retry attempt**, operators easily mistake them for two failed items. For per-attempt logs, use a semantically clear event such as:

```text
event=batch_retry_attempt stage=process
error_code=PARTNER_TEMPORARY_FAILURE attempt=2
record_ref=8a62b97f4d21d5a7
```

`attempt` here illustrates a value taken from a retry context or reliable counter, **not inferred by counting log lines**. Depending on policy, you can log retries at `DEBUG` or `INFO` and emit `WARN` only when hitting a threshold; avoid flooding logs when transient errors occur en masse.

Spring Retry's `RetryListener` can observe retry cycles. Be cautious because the same chunk may roll back or replay part of its work, and the same item can trigger multiple callbacks. Never treat the invocation count of `onProcessError` as the final count of failed items.

### 8.2. Summary Logging After the Step

A `StepExecutionListener` reports the overall outcome without printing individual items:

```java
package com.example.batch;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;

public class SafeStepSummaryLogger implements StepExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(SafeStepSummaryLogger.class);

    @Override
    public ExitStatus afterStep(StepExecution step) {
        log.info(
                "event=batch_step_finished step={} execution_id={} "
                + "status={} read={} write={} skip={} rollback={}",
                step.getStepName(),
                step.getJobExecutionId(),
                step.getStatus(),
                step.getReadCount(),
                step.getWriteCount(),
                step.getSkipCount(),
                step.getRollbackCount());

        return null; // Do not alter the step's ExitStatus.
    }
}
```

`StepExecution` provides technical metrics without exposing item contents. Still, application-constructed fields like step names or exit descriptions should have their origins checked. In a step with retries, `readCount`, `writeCount`, `rollbackCount`, and `skipCount` are **not** literal counts of processor/writer invocations.

### 8.3. Recording Failures That Require Deep Investigation

For a `FAILED` job, log a summary such as:

```text
event=batch_job_failed job=dailyOrdersJob
execution_id=78241 error_code=UNCLASSIFIED_FAILURE
action=REVIEW_RESTRICTED_DIAGNOSTICS
```

Operators can inspect `JobRepository` and internal diagnostic systems using `execution_id`. If raw failed records must be retained for business remediation, write them to an encrypted **quarantine/dead-letter store** with separate access control and retention limits, and log only a safe reference. Never replace quarantine with dumping entire items into general logging.

Logs are not rolled back by the step transaction manager. If you require **exactly one committed audit event per failed item**, design an audit table or transactional outbox with an idempotency key, proper transaction boundaries, and post-commit event publishing. General logs are primarily diagnostic, not the sole source of truth for item state.

## 9. Testing That Logs Do Not Leak Data

A thorough test verifies both that **required fields are present** and that **sensitive data is absent**. Example unit test for the listener using Logback's `ListAppender`, which is typically available with `spring-boot-starter-test` and default Spring Boot logging:

```java
package com.example.batch;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;

class SafeOrderSkipListenerTest {

    @Test
    void logsReferenceAndCodeWithoutRawItemOrExceptionMessage() {
        byte[] testKey = new byte[32];
        Arrays.fill(testKey, (byte) 7);

        var token = new SafeRecordToken(testKey);
        var listener = new SafeOrderSkipListener(
                token, "2026-11-16");

        Logger logger = (Logger) LoggerFactory.getLogger(
                SafeOrderSkipListener.class);

        ListAppender<ILoggingEvent> capture = new ListAppender<>();
        capture.start();
        logger.addAppender(capture);

        try {
            String privateId = "order-007-secret";
            String privateEmail = "sample.user@example.test";

            var item = new OrderInput(
                    privateId,
                    privateEmail,
                    new BigDecimal("123.45"));

            // Simulate an error containing sensitive data in the message.
            var error = new InvalidOrderException(
                    "Invalid data for " + privateEmail);

            listener.onSkipInProcess(item, error);

            assertThat(capture.list).hasSize(1);
            String message = capture.list.get(0)
                    .getFormattedMessage();

            assertThat(message)
                    .contains("event=batch_item_skipped")
                    .contains("stage=process")
                    .contains("error_code=INVALID_ORDER")
                    .contains("record_ref=" + token.fromIdentifier(privateId));

            assertThat(message)
                    .doesNotContain(privateId)
                    .doesNotContain(privateEmail)
                    .doesNotContain("123.45")
                    .doesNotContain("Invalid data for");
        } finally {
            logger.detachAppender(capture);
            capture.stop();
        }
    }
}
```

This test checks **messages produced by the listener**; it does not automatically cover every log from readers/processors/writers, dependencies, JDBC drivers, or system appenders. For integration testing, run synthetic data containing an easily recognizable sensitive marker (such as `SENSITIVE_MARKER_001`) through read, error, retry, skip, and write paths, then search for that marker across **all log output** of the test application.

When using a JSON encoder or centralized log system, inspect data **after the encoder and collection pipeline**, because MDC, exception layouts, tracing baggage, or APM agents can inadvertently attach payloads even when the original message is safe.

### Scenarios to Test

| Scenario | What to Verify |
| --- | --- |
| Valid item | No unnecessary skip events emitted |
| Item validation failure | Only `record_ref` and `INVALID_ORDER` logged; no email, raw ID, or amount |
| Two retries then success | Attempt logs (if enabled) distinguished from skips; no final skip emitted |
| Permanent failure exceeding retries without skip | Step/job ends failed; error event leaks no payload |
| Read error without an item | `record_ref=unavailable`, no CSV/JSON line dumped |
| Whole-chunk write failure | Does not print full item collection; per-item skips tracked via callback |
| Exception message contains sensitive data | Message and stack trace do not appear in general logs |
| Concurrent executions running in parallel | No cross-contamination of MDC/record references between executions |
| Invalid HMAC key | System reports configuration error instead of falling back to raw IDs |
| Centralized log pipeline | JSON encoder/collector adds no sensitive fields |

## 10. Avoiding Leaks via MDC, Tracing, and Monitoring Systems

`MDC` (Mapped Diagnostic Context) attaches `jobExecutionId` or a correlation ID to all log lines within a processing block. However, MDC is normally bound to the **current thread**; pooled threads are reused. If you set MDC manually, always clean it up in `finally`:

```java
import org.slf4j.MDC;

try {
    MDC.put("job_execution_id", Long.toString(executionId));
    MDC.put("stage", "process");

    // Log statements within this scope receive the MDC fields.
    runOperation();
} finally {
    MDC.remove("job_execution_id");
    MDC.remove("stage");
}
```

This is an **illustrative snippet**: `executionId` and `runOperation()` are supplied by the application. With asynchronous execution, `TaskExecutor`, partitioning, or multi-threaded steps, context must be propagated explicitly across thread boundaries; never assume MDC propagates automatically across threads.

Beyond your logger, other places can capture sensitive data unintentionally:

- APM/tracing agents automatically capturing HTTP URLs, query parameters, request bodies, or exception messages.
- JDBC logging at `TRACE` printing SQL statements together with bind values.
- DTO `toString()` methods appearing inside framework logs.
- Reader/writer loggers printing raw items or malformed file lines.
- `JobParameters` or `ExecutionContext` dumped as whole objects during debugging.
- HTTP clients logging response bodies containing customer data.
- Log aggregation enriching metadata or retaining logs longer than allowed.

Your audit scope must cover the **entire log pipeline**, not just code inside `SkipListener`. In production, log access should be role-based, encrypted in transit and at rest, governed by retention policies, and backed by an incident response plan for log leaks.

## 11. Keeping Logs Useful Without Creating Excessive Noise

A job processing 10 million items can trigger hundreds of thousands of retries if an external service degrades. If every attempt logs a stack trace, the logging pipeline can overload right when observability matters most.

Recommended practices:

1. **Log item-level events when items are actually skipped**, with approved fields only.
2. **Make retry diagnostics configurable**, using an appropriate log level or sampling; always preserve accurate aggregate metrics and retry counters.
3. **Log a step summary**: `read`, `write`, `skip`, `rollback`, `BatchStatus`, and duration.
4. **Alert on thresholds**: skip ratio, errors by `error_code`, `FAILED` job count, latency, and missed deadlines.
5. **Never use item IDs as metrics labels**; use low-cardinality event/job/step/error codes.

If you cap log volume or apply sampling, state clearly which events may be omitted. Sampled logs cannot give exact counts of every failed item. For exact counts, rely on counters/metadata or an audit store designed for that purpose.

## 12. Common Mistakes and How to Fix Them

| Implementation Mistake | Risk | Fix |
| --- | --- | --- |
| `log.error("item={}", item)` | Calls `toString()` exposing all fields | Log an allowlist and reference token |
| `log.error("failed", throwable)` on a general channel | Stack trace/message carries payload or SQL params | Stable error codes; restricted diagnostics channel |
| Logging email/ID replaced with unkeyed SHA-256 | Reversible via dictionary lookup | Omit or use keyed HMAC/token under policy |
| Logging full `JobParameters` | May contain secrets and business data | Select only approved fields |
| Logging `ERROR` on every retry | Misleads operators into thinking the item permanently failed | Distinguish attempt from final skip/fail |
| Logging every element of a chunk on writer error | Exposes many items and spikes volume | Log technical event; use skip callbacks for item identification |
| Treating `SkipListener` as an absolute audit source | Logging is non-transactional and can be lost/duplicated on failure | Use an audit table or outbox when exactness is required |
| Using `record_ref` as a metrics label | High cardinality and data linkability | Use only `error_code`, `job`, `step`, `stage` |
| Leaving MDC set on thread pools | Other job logs inherit stale context | Clear MDC in `finally`; configure proper propagation |
| Blindly logging unknown exception messages | Sensitive input slips into logs | Fall back to `UNCLASSIFIED_FAILURE` |
| Unrestricted access to quarantine store | Leaks raw data through secondary system | Encrypt, enforce RBAC, retention, and access auditing |

## 13. Hands-on Exercise

Build a chunk step `validateOrdersStep` processing a test list of orders containing valid orders, orders violating business rules, and orders encountering transient partner errors.

1. Create `OrderInput` with `orderId`, `customerEmail`, and `amount`. Keep a default `toString()` but **never** pass it to a logger.
2. Create `SafeRecordToken` using HMAC-SHA-256 and a dedicated test key. Verify identical IDs yield identical tokens and distinct IDs yield distinct tokens.
3. Create `SafeErrorCodes` returning only `INVALID_ORDER`, `PARTNER_TEMPORARY_FAILURE`, and `UNCLASSIFIED_FAILURE`.
4. Register `SafeOrderSkipListener` on a step with `.faultTolerant()`, `.skip(InvalidOrderException.class)`, and `.retry(TemporaryPartnerException.class)`.
5. Cause an invalid item to skip and confirm logs contain only the safe event—no `orderId`, email, amount, or exception message.
6. Cause an item to fail transiently twice and succeed on the third attempt; distinguish retry attempt logs from final skip events.
7. Trigger a read error that produces no item; verify `onSkipInRead` does not attempt to print the raw data line.
8. Add `SafeStepSummaryLogger` and compare `skipCount` with the actual number of discarded items in batch metadata.
9. Run an integration test capturing all logs with a synthetic sensitive data marker, and confirm the marker never appears after the JSON encoder, MDC, or tracing.
10. Design a quarantine store where only authorized users can inspect failed payloads; external logs hold only a reference token for safe lookup.

When logging error items in Spring Batch, the guiding principle is **keep enough information to diagnose causes and processing states without putting sensitive business data into logs**. Classifying errors into fixed codes, logging at purpose-built lifecycle callbacks, using protected references, and testing the entire logging pipeline makes batch jobs both operable and far less prone to data leaks.
