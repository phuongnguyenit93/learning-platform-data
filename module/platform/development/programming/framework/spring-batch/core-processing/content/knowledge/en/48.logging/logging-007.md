# Attaching Chunk or Item Keys to Logs in Spring Batch

When a batch job runs through millions of records, a log line like `Processing failed` is nowhere near enough to investigate an incident. Operators need to know **which job execution**, **which step**, **which chunk attempt**, and **which item** failed. Yet dumping full objects into logs for extra context can accidentally expose customer data, transaction details, or source file contents.

This lesson under **Spring Batch Core Processing → Logging** focuses on two kinds of keys for correlating events:

- **Chunk key / chunk reference**: identifies one *chunk processing attempt* to group nearby read, process, write, and rollback logs.
- **Item key / item reference**: identifies *one logical record* across retries, chunks, or restarts when the data source provides a stable identifier.

We will use Spring Batch 5.x, Spring Boot 3.x, Java 17, SLF4J/Logback, and JUnit 5 to design keys, attach context via MDC, build a `ChunkListener`, wrap `ItemProcessor`, log retries/skips safely, and test for zero data leaks.

## 1. Why Do We Need Both a Chunk Key and an Item Key?

A chunk-oriented step typically reads multiple items, processes each item, and writes the whole group within a transaction:

```text
JobExecution #850
  └── StepExecution #1260 (importOrdersStep)
       ├── Chunk attempt C1
       │    ├── item A ── process ──┐
       │    ├── item B ── process ──┼── writer ── COMMIT
       │    └── item C ── process ──┘
       │
       ├── Chunk attempt C2
       │    ├── item D ── process ──┐
       │    ├── item E ── process ──┼── writer ── exception
       │    └── item F ── process ──┘              │
       │                                          └── ROLLBACK
       │
       └── Chunk attempt C3 / retry
            ├── item D
            ├── item E
            └── item F ── ...
```

With only `JobExecutionId`, logs from thousands of chunks mix together. With only `chunk_ref`, it is hard to see an item reappear after a retry/rollback. With only `item_ref`, it is hard to tell which attempt rolled back or which batch group the writer received.

Structured log example:

```text
event=chunk_started job=importOrdersJob step=importOrdersStep
job_execution_id=850 step_execution_id=1260 chunk_ref=je850-se1260-c17

event=item_attempt_failed stage=process
chunk_ref=je850-se1260-c17 item_ref=3d9f840e63776c49
error_code=REMOTE_TIMEOUT

event=chunk_rolled_back
chunk_ref=je850-se1260-c17

event=item_skipped stage=process
chunk_ref=je850-se1260-c18 item_ref=3d9f840e63776c49
error_code=INVALID_ORDER
```

These `chunk_ref` and `item_ref` codes are **illustrative examples**. During analysis, you can filter by a chunk to inspect a processing attempt's progress, or filter by an item to view its history across retries. The two keys serve different purposes, so never conflate them.

## 2. Understanding Exactly What Unit Each Key Identifies

| Key / Metadata | Scope | Stable on Retry? | Stable on Restart? | Purpose |
| --- | --- | --- | --- | --- |
| `jobName` | Job definition | Yes | Yes | Group jobs of the same kind |
| `JobInstance` | Job name + identifying `JobParameters` | Yes within same instance | Yes when restarting the same instance | Identify one logical work unit |
| `jobExecutionId` | One job execution | Yes within execution | **No**; restart creates a new execution | Trace a single run |
| `stepExecutionId` | One step execution | Yes within step execution | Usually different when step re-runs | Trace a specific step run |
| Custom `chunk_ref` | One chunk attempt | Yes within that attempt | Not guaranteed | Group logs in one chunk attempt |
| Stable `item_ref` | One logical item | Yes if using same key source | Yes if source identity is unchanged | Join history of one item |
| Trace/span ID | Scope defined by tracing | Depends on instrumentation | Depends on tracing design | Correlate logs and service calls |

**Spring Batch does not provide a durable `chunkId` unique across restarts as a business key.** `StepExecution.getCommitCount()` is only the recorded commit count, not a safe identifier for every chunk attempt. When a transaction rolls back, counts, callbacks, and retry attempts can shift; never treat `commitCount + 1` as an immutable data ID.

A practical approach is generating a `chunk_ref` at **each chunk start** using `jobExecutionId + stepExecutionId + incrementing sequence`. This reference is great for log diagnostics within a single execution; never use it as an item primary key, idempotency key, or checkpoint.

Conversely, `item_ref` must rely on a stable identifier: the record's `orderId`, source message ID, or `sourceVersion + rowNumber` when the file is **immutable**. Sequential `readCount` and item position within a chunk are usually unstable across rollbacks, partitioning, input changes, or restarts.

## 3. Designing an Item Key Matching the Data Source

Suppose an order-processing job has this model:

```java
package com.example.batch;

import java.math.BigDecimal;

public record OrderRow(
        String orderId,
        String customerEmail,
        BigDecimal amount) {}
```

Here `orderId` is a candidate for building an item key, yet that **does not mean you are allowed to log the raw ID verbatim**. An ID may be indirect personal data, linkable to a customer via another system, or deemed sensitive under internal policy.

Options to consider:

| Item Source | Internal Identifier to Consider | Notes |
| --- | --- | --- |
| Database | Primary key or normalized business key | May change across import runs; avoid printing sensitive keys directly |
| Kafka/message queue | Topic + partition + offset, or event ID | Offset identifies a message in a specific stream, not necessarily the same business entity |
| CSV/immutable file | File version/checksum + record number | Do not use line number alone if file contents can change |
| API with stable ID | Provider + external ID | External ID may reveal identity; apply tokenization policy |
| Unparseable record | May lack an ID yet | Log stage, approved source, and technical position; use `item_ref=unavailable` if needed |

When an entity spans multiple sources, apply a *namespace*: e.g. combine `sourceSystem`, `tenantId`, or `sourceVersion` in the **input before generating the token**. Identical ID strings across two tenants must never be treated as the same item. If an item key is used for business reconciliation or deduplication, manage that business key at the data layer; the log token is strictly a diagnostic reference.

### 3.1. Why Avoid Plain Hashes?

For example, unkeyed `SHA-256(email)` or `SHA-256(orderId)` can still be reversed via dictionary attacks when inputs are predictable. `String.hashCode()` is even worse—neither secure nor collision-resistant.

If you need a **stable token for log correlation** without writing the raw ID, one solution is `HMAC-SHA-256` with a sufficiently strong secret key. HMAC does not make data harmless: the token still allows linking logs and requires access control, retention, and rotation management. If operations do not need item-level correlation, omitting item keys from logs is simpler and safer.

## 4. Generating Item References with HMAC

The class below generates tokens from a namespace and stable ID without exposing the raw ID in output. Each call creates a fresh `Mac` instance because `Mac` is not thread-safe.

```java
package com.example.batch.logging;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.HexFormat;
import java.util.Objects;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class ItemRefFactory {

    private final SecretKeySpec key;

    public ItemRefFactory(byte[] secret) {
        if (secret == null || secret.length < 32) {
            throw new IllegalArgumentException(
                    "HMAC secret must have at least 32 bytes");
        }
        this.key = new SecretKeySpec(
                secret.clone(), "HmacSHA256");
    }

    public String fromOrderId(String orderId) {
        Objects.requireNonNull(orderId, "orderId");
        if (orderId.isBlank()) {
            return "unavailable";
        }

        // Fixed namespace to avoid colliding with IDs from other domains.
        String canonical = "orders:v1:" + orderId;

        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(key);
            byte[] digest = mac.doFinal(
                    canonical.getBytes(StandardCharsets.UTF_8));

            // First 12 bytes (96 bits), represented as 24 hex characters.
            return HexFormat.of().formatHex(digest, 0, 12);
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException(
                    "Cannot calculate safe item reference");
        }
    }
}
```

In a real system, the HMAC key must come from a secret manager or protected configuration—**never hardcoded in source code, logs, or deployment scripts**. Keys must be randomly generated with sufficient strength; checking for 32 bytes in this example is a configuration guard, not proof of high entropy.

Consider two operational aspects:

- **Rotation:** changing keys changes the token for the same item. If you need to search logs across key versions, log a non-sensitive `key_version` and provide an authorized lookup tool.
- **Linkability bounds:** the same key and ID produce the same token. If you do not want correlation across tenants, jobs, or environments, use separate namespaces/keys. Never let users inject unchecked strings into log field names.

HMAC tokens cannot be decrypted back into `orderId`. Looking up an item from its token requires an authorized tool matching against source IDs or a protected mapping store. Never treat the token as an authorization token.

## 5. Attaching Chunk Keys with `ChunkListener` and MDC

SLF4J provides **Mapped Diagnostic Context (MDC)**: a key–value map bound to the execution thread that loggers/encoders read when emitting logs. When a chunk starts, generate a reference and place it in MDC; log lines on that thread automatically carry the key.

Example `ChunkTraceListener.java`:

```java
package com.example.batch.logging;

import java.util.concurrent.atomic.AtomicLong;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.batch.core.ChunkListener;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.scope.context.ChunkContext;

public class ChunkTraceListener implements ChunkListener {

    private static final Logger log =
            LoggerFactory.getLogger(ChunkTraceListener.class);

    private static final String CHUNK_REF = "batch_chunk_ref";
    private static final String STEP_EXECUTION_ID =
            "batch_step_execution_id";

    private final AtomicLong sequence = new AtomicLong();

    @Override
    public void beforeChunk(ChunkContext context) {
        StepExecution step =
                context.getStepContext().getStepExecution();

        long attempt = sequence.incrementAndGet();
        String reference = "je" + step.getJobExecutionId()
                + "-se" + step.getId()
                + "-c" + attempt;

        MDC.put(CHUNK_REF, reference);
        MDC.put(STEP_EXECUTION_ID,
                String.valueOf(step.getId()));

        log.debug(
                "event=batch_chunk_started chunk_ref={} step_execution_id={}",
                reference, step.getId());
    }

    @Override
    public void afterChunk(ChunkContext context) {
        try {
            log.debug("event=batch_chunk_committed chunk_ref={}",
                    MDC.get(CHUNK_REF));
        } finally {
            cleanup();
        }
    }

    @Override
    public void afterChunkError(ChunkContext context) {
        try {
            log.warn(
                    "event=batch_chunk_failed chunk_ref={} error_code={}",
                    MDC.get(CHUNK_REF), "CHUNK_ROLLBACK");
        } finally {
            cleanup();
        }
    }

    private void cleanup() {
        // Remove only the keys owned by this listener.
        MDC.remove(CHUNK_REF);
        MDC.remove(STEP_EXECUTION_ID);
    }
}
```

Key takeaways:

1. `StepExecution.getJobExecutionId()` and `getId()` link the chunk attempt to job/step metadata. The `AtomicLong` sequence merely distinguishes **callback attempts** within the same listener instance.
2. `chunk_ref` in this example is **not a durable ID persisted by Spring Batch**; after a job restart, `jobExecutionId`/`stepExecutionId` and the counter will differ.
3. `afterChunk` and `afterChunkError` clean up attached keys even if logging code fails. Never call `MDC.clear()` indiscriminately, as that can wipe trace context set by other components.
4. Never pass `Throwable` or the entire `Chunk` contents as logger arguments. The rollback event here logs only an approved status code.
5. The example assumes callbacks for a single chunk attempt run on the same thread. If async processing or a custom executor switches threads between stages, MDC must be propagated and cleaned up per task; a listener alone cannot guarantee cross-thread propagation.

### 5.1. Why Use a Step-Scoped Bean?

If a singleton listener is shared across multiple step executions, `sequence` increments across concurrent jobs. Even with execution IDs, that blurs state ownership and scope. For a chunk trace listener holding a counter, create **one instance per step execution**:

```java
@Bean
@StepScope
public ChunkTraceListener chunkTraceListener() {
    return new ChunkTraceListener();
}
```

`@StepScope` creates a scoped proxy so the bean is instantiated only when the step runs. In Java config, import `org.springframework.context.annotation.Bean` and `org.springframework.batch.core.configuration.annotation.StepScope`.

In multi-threaded or partitioned steps, the atomic counter keeps sequences unique within the instance, but `c1`, `c2` order does not promise source-file order or commit order. For partition analysis, add a vetted fixed `partition_ref` to logs; item keys must still come from item identity, never thread order.

## 6. Scoping Item Keys Properly with `ItemProcessor`

MDC is thread-bound. Never set `batch_item_ref` in `ItemReader` and leave it until chunk end: a chunk contains many items, so by the time the writer runs, MDC would hold only the last item's ID, misleading investigators into thinking the writer processed only that item.

The clean approach is using **one MDC scope per item processing call**, removing it in `finally`. SLF4J 2 supports `MDC.putCloseable(...)`, making this seamless with `try-with-resources`.

Example `ItemTraceProcessor.java`:

```java
package com.example.batch.logging;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.batch.item.ItemProcessor;

import com.example.batch.OrderRow;

public class ItemTraceProcessor
        implements ItemProcessor<OrderRow, OrderRow> {

    private static final Logger log =
            LoggerFactory.getLogger(ItemTraceProcessor.class);

    private final ItemProcessor<OrderRow, OrderRow> delegate;
    private final ItemRefFactory refs;

    public ItemTraceProcessor(
            ItemProcessor<OrderRow, OrderRow> delegate,
            ItemRefFactory refs) {
        this.delegate = delegate;
        this.refs = refs;
    }

    @Override
    public OrderRow process(OrderRow item) throws Exception {
        String reference = refs.fromOrderId(item.orderId());

        try (MDC.MDCCloseable scope =
                MDC.putCloseable("batch_item_ref", reference)) {

            try {
                // Loggers inside delegate can read item_ref from MDC.
                return delegate.process(item);
            } catch (Exception ex) {
                log.warn(
                        "event=batch_item_attempt_failed "
                        + "stage=process chunk_ref={} item_ref={} "
                        + "error_code={}",
                        MDC.get("batch_chunk_ref"),
                        reference,
                        safeErrorCode(ex));
                throw ex;
            }
        }
    }

    private String safeErrorCode(Exception ex) {
        if (ex instanceof IllegalArgumentException) {
            return "INVALID_INPUT";
        }
        if (ex instanceof java.net.SocketTimeoutException) {
            return "REMOTE_TIMEOUT";
        }
        return "PROCESSING_FAILED";
    }
}
```

`delegate` is the actual business processor. It may transform data, return `null` to filter an item, or throw an exception. The wrapper preserves both results and exceptions while adding log references. For the code above to compile, the `OrderRow` record declared in Section 3 must reside in `com.example.batch`.

In logs, pass only error codes from an allowlist. **Never pass `ex.getMessage()`, `ex`, `item`, `item.toString()`, or HTTP/SQL payloads to general loggers**: they can contain sensitive data. When stack traces are required for diagnostics, route them to a dedicated restricted channel with proper data handling.

With `MDC.putCloseable`, `batch_item_ref` is removed when exiting scope, even on exception. This snippet assumes no outer component already set `batch_item_ref`. If nested scopes share the same key, save the previous value and restore it in `finally` rather than deleting the caller's context.

**A `batch_item_attempt_failed` log does not mean the item was skipped or the job is `FAILED`.** An exception may be retried and succeed, or be skipped when reaching policy limits. To determine the final outcome, rely on the appropriate listeners and Spring Batch metadata.

## 7. Writer and SkipListener: Avoiding Misattributed Items

### 7.1. A Writer Can Process Multiple Items

In a chunk-oriented step, `ItemWriter.write(Chunk<? extends T>)` receives a **chunk**, not necessarily a single item:

```java
@Override
public void write(Chunk<? extends OrderRow> chunk) throws Exception {
    log.debug(
            "event=batch_write_requested chunk_ref={} item_count={}",
            MDC.get("batch_chunk_ref"),
            chunk.size());

    // Write data according to the writer's transaction rules.
    delegate.write(chunk);
}
```

Here `delegate` is the business writer, `log` is the writer class logger, and `Chunk` is `org.springframework.batch.item.Chunk`. If a writer fails at the chunk level without pinpointing the offending record, **never attribute the error to the last item processed by the processor**. Use `chunk_ref` and item counts to narrow down the chunk; only log `item_ref` when the writer or skip mechanism actually isolates the item.

When a writer calls an external service requiring idempotency, use a business key designed specifically for that transaction or event. `chunk_ref` is a transient log key unsuitable as an idempotency key; retries can generate a different chunk reference.

### 7.2. SkipListener Identifies Skipped Items

Spring Batch provides `SkipListener<I, O>` to notify when the framework decides to skip. This example assumes the same `OrderRow` type for input and output:

```java
package com.example.batch.logging;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.batch.core.SkipListener;

import com.example.batch.OrderRow;

public class SafeOrderSkipListener
        implements SkipListener<OrderRow, OrderRow> {

    private static final Logger log =
            LoggerFactory.getLogger(SafeOrderSkipListener.class);

    private final ItemRefFactory refs;

    public SafeOrderSkipListener(ItemRefFactory refs) {
        this.refs = refs;
    }

    @Override
    public void onSkipInRead(Throwable error) {
        log.warn(
                "event=batch_item_skipped stage=read "
                + "chunk_ref={} item_ref={} error_code={}",
                MDC.get("batch_chunk_ref"),
                "unavailable",
                "READ_FAILED");
    }

    @Override
    public void onSkipInProcess(OrderRow item, Throwable error) {
        logSkip("process", item, "INVALID_INPUT");
    }

    @Override
    public void onSkipInWrite(OrderRow item, Throwable error) {
        logSkip("write", item, "WRITE_REJECTED");
    }

    private void logSkip(
            String stage, OrderRow item, String safeCode) {
        log.warn(
                "event=batch_item_skipped stage={} "
                + "chunk_ref={} item_ref={} error_code={}",
                stage,
                MDC.get("batch_chunk_ref"),
                refs.fromOrderId(item.orderId()),
                safeCode);
    }
}
```

In `onSkipInRead`, the callback does not supply a successfully read item, so a safe record ID cannot be derived from an unconstructed `OrderRow`. Never dump the CSV line, buffer, or response body to extract an ID. You can add a vetted `source_ref` if the reader provides a safe source identifier and position.

In this sample code, `READ_FAILED`, `INVALID_INPUT`, and `WRITE_REJECTED` represent illustrative scenarios. A real application should map `Throwable` to **fixed error codes based on exception type**, instead of labeling every process error `INVALID_INPUT`; strictly avoid turning raw exception messages into log fields.

`SkipListener` is right for logging items **actually skipped**, whereas `ItemProcessListener.onProcessError` or the processor wrapper fits **a failed attempt**. With retries, an item may log failed attempts multiple times without ultimately being skipped. Because logs do not participate in data transactions, never treat log line counts as the sole source of truth for exact audit item counts.

## 8. Step Configuration Integrating the Listeners

Assuming the application already has business beans `ItemReader<OrderRow>`, `ItemProcessor<OrderRow, OrderRow>`, and `ItemWriter<OrderRow>`, wire the beans:

```java
package com.example.batch.logging;

import java.util.Base64;

import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

import com.example.batch.OrderRow;

@Configuration
public class ImportOrdersStepConfig {

    @Bean
    ItemRefFactory itemRefFactory(
            @Value("${batch.logging.hmac-key-base64}") String keyBase64) {
        return new ItemRefFactory(
                Base64.getDecoder().decode(keyBase64));
    }

    @Bean
    @StepScope
    ChunkTraceListener chunkTraceListener() {
        return new ChunkTraceListener();
    }

    @Bean
    SafeOrderSkipListener safeOrderSkipListener(ItemRefFactory refs) {
        return new SafeOrderSkipListener(refs);
    }

    @Bean
    ItemTraceProcessor itemTraceProcessor(
            @Qualifier("businessOrderProcessor")
            ItemProcessor<OrderRow, OrderRow> businessProcessor,
            ItemRefFactory refs) {
        return new ItemTraceProcessor(businessProcessor, refs);
    }

    @Bean
    Step importOrdersStep(
            JobRepository repository,
            PlatformTransactionManager transactionManager,
            ItemReader<OrderRow> reader,
            ItemTraceProcessor processor,
            ItemWriter<OrderRow> writer,
            ChunkTraceListener chunkListener,
            SafeOrderSkipListener skipListener) {

        return new StepBuilder("importOrdersStep", repository)
                .<OrderRow, OrderRow>chunk(100, transactionManager)
                .reader(reader)
                .processor(processor)
                .writer(writer)
                .faultTolerant()
                .retry(java.net.SocketTimeoutException.class)
                .retryLimit(3)
                .skip(IllegalArgumentException.class)
                .skipLimit(20)
                .listener(chunkListener)
                .listener(skipListener)
                .build();
    }
}
```

`businessOrderProcessor`, reader, and writer are business beans **assumed to exist**; this example focuses on attaching log context. In a real project, adjust retry/skip exception types to match exceptions thrown at step boundaries and your data-handling policy.

Key reference configuration:

```properties
batch.logging.hmac-key-base64=${BATCH_LOG_REF_KEY_B64}
```

`BATCH_LOG_REF_KEY_B64` must be supplied from a secret manager or protected secret store; never store real values in the repository, container images, or logs. Placing `ChunkTraceListener` in `@StepScope` ties its sequence to a single step execution, and requires Spring Batch step scope infrastructure to be active.

With a Logback log pattern, display MDC alongside the message:

```xml
<pattern>
  %d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level
  chunk=%X{batch_chunk_ref:-none}
  item=%X{batch_item_ref:-none}
  %logger{30} - %msg%n
</pattern>
```

This is a **pattern fragment** to place inside an appropriate Logback appender in `logback-spring.xml`; the XML snippet alone is not a complete config file. Never enable dumping all of MDC (`%X`) if other MDC keys hold sensitive data. Also avoid logging **both** pattern values and duplicate fields inside the message text at high log volume; JSON logging systems can emit each field as structured data instead of plain text.

## 9. Impact of Retry, Rollback, Restart, and Concurrency

### 9.1. Retry and Rollback

If item B's processor fails and then succeeds on retry:

```text
chunk_ref=je850-se1260-c17 item_ref=ref-B attempt_failed
chunk_ref=je850-se1260-c17 item_ref=ref-B processed
chunk_ref=je850-se1260-c17 chunk_committed
```

However, if the writer fails and rolls back the chunk, the framework may trigger re-processing passes depending on transaction, buffering, and retry configuration:

```text
chunk_ref=je850-se1260-c17 writer_failed
chunk_ref=je850-se1260-c17 chunk_rolled_back
chunk_ref=je850-se1260-c18 item_ref=ref-B processed_again
```

`chunk_ref` differs while `item_ref` remains identical. That relationship shows where an item was re-executed. Never infer attempt counts solely by counting `chunk_ref`s: one chunk can execute multiple internal retries, and callback/transaction behavior depends on reader, processor, writer, and policies.

### 9.2. Job Restart

When restarting a `FAILED` `JobInstance` with the same identifying `JobParameters`, Spring Batch creates a **new `JobExecution`**. If a step needs to re-run, it normally gets a new `StepExecution`. `chunk_ref` therefore changes, while a stable item reference can correlate logs across both runs:

```text
JobExecution 850:
  chunk_ref=je850-se1260-c17 item_ref=ref-B error

JobExecution 851 (restart same JobInstance):
  chunk_ref=je851-se1302-c01 item_ref=ref-B success
```

Never include `jobExecutionId` or chunk sequence numbers inside an **item key meant to stay stable across restarts**. Conversely, if an item key uses only the business date without an item identifier, many records from the same day collide.

### 9.3. Multi-Threaded Steps and Partitioning

Standard MDC binds to the **current thread**. When using a `TaskExecutor`, partitioning, or async API calls, logs may run on another thread without receiving context automatically. To propagate MDC across tasks, use a wrapper or `TaskDecorator` that copies the context map at dispatch time and **restores/clears it in `finally`** after task completion.

Never share a single mutable `Map<String,String>` across threads and mutate it in place. Each task should receive its own context snapshot. If the listener runs across multiple threads, an `AtomicLong` sequence avoids duplicate `chunk_ref`s within the step execution, yet makes no guarantee about file order, offset order, or commit order.

If your system uses tracing with OpenTelemetry/Micrometer, link `traceId`/`spanId` from tracing into logs. **Trace IDs and item keys have different lifecycles**: one trace can span multiple items, and one item can appear in multiple traces across restarts. Never substitute trace identity for item identity.

## 10. Testing Log Keys and MDC Cleanup

A logging wrapper can work functionally while still leaking context when threads are reused. Tests should verify three invariants: **keys appear when expected**, **raw data never appears**, and **MDC is cleaned up after invocation**.

Example test using JUnit 5, AssertJ, and Logback `ListAppender`. This tests the processor wrapper without running the entire job:

```java
package com.example.batch.logging;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.math.BigDecimal;
import java.util.Arrays;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.batch.item.ItemProcessor;

import com.example.batch.OrderRow;

class ItemTraceProcessorTest {

    @Test
    void addsSafeItemRefAndRestoresThreadContext() {
        byte[] testKey = new byte[32];
        Arrays.fill(testKey, (byte) 7);
        ItemRefFactory refs = new ItemRefFactory(testKey);

        String rawId = "order-private-007";
        String privateEmail = "person@example.test";
        OrderRow item = new OrderRow(
                rawId, privateEmail, new BigDecimal("123.45"));

        ItemProcessor<OrderRow, OrderRow> failingBusinessProcessor =
                row -> {
                    throw new IllegalArgumentException(
                            "Invalid customer: " + row.customerEmail());
                };

        ItemTraceProcessor processor =
                new ItemTraceProcessor(failingBusinessProcessor, refs);

        Logger logger = (Logger) LoggerFactory.getLogger(
                ItemTraceProcessor.class);
        ListAppender<ILoggingEvent> capture = new ListAppender<>();
        capture.start();
        logger.addAppender(capture);

        try {
            assertThatThrownBy(() -> processor.process(item))
                    .isInstanceOf(IllegalArgumentException.class);

            assertThat(capture.list).hasSize(1);
            ILoggingEvent event = capture.list.get(0);
            String message = event.getFormattedMessage();

            assertThat(message)
                    .contains("event=batch_item_attempt_failed")
                    .contains("error_code=INVALID_INPUT")
                    .contains("item_ref=" + refs.fromOrderId(rawId));

            assertThat(event.getMDCPropertyMap())
                    .containsEntry(
                            "batch_item_ref", refs.fromOrderId(rawId));

            assertThat(message)
                    .doesNotContain(rawId)
                    .doesNotContain(privateEmail)
                    .doesNotContain("123.45")
                    .doesNotContain("Invalid customer:");

            assertThat(MDC.get("batch_item_ref")).isNull();
        } finally {
            logger.detachAppender(capture);
            capture.stop();
            MDC.remove("batch_item_ref");
        }
    }
}
```

In this test, we use a known dummy key. Production must use a truly high-entropy key from a secret manager. `ListAppender` captures events emitted by the wrapper; this test **does not prove** other libraries, HTTP clients, SQL loggers, or tracing agents avoid logging sensitive data. For integration tests, pass a synthetic sensitive-data marker through the entire pipeline, capture logs after the encoder, and search for that marker.

### 10.1. Testing the Chunk Listener

For `ChunkTraceListener`, write an integration test running a small step of 2–3 chunks and verify:

1. Each `beforeChunk` creates a `chunk_ref` containing job/step execution IDs and sequence.
2. Processor log lines on the same thread carry the matching `chunk_ref`.
3. After commit, MDC no longer contains `batch_chunk_ref`.
4. When the writer triggers rollback, `batch_chunk_failed` carries the reference and MDC is still cleaned up.
5. When re-running the same item via retry or restart, `item_ref` stays stable while `chunk_ref` can differ.
6. When running across multiple threads, no chunk reference from one task appears in another task's logs.

Testing chunk listeners thoroughly requires real `JobRepository`/transaction configuration and a test step; do not over-mock it and draw conclusions about Spring Batch's rollback cycle.

## 11. Operational Rules for Chunk/Item Keys

| Case | Do | Avoid |
| --- | --- | --- |
| Diagnosing chunk rollbacks | Use `jobExecutionId`, `stepExecutionId`, `chunk_ref` | Treating `commitCount` as a permanent chunk ID |
| Tracking an item across retries/restarts | Use item ref from a stable source identity | Using chunk position or thread ID |
| Items containing PII | Policy-backed HMAC/token, or omit ref | Logging raw email/order ID |
| Reader failure before producing an item | `item_ref=unavailable` and error code | Dumping raw CSV lines/bodies to get an ID |
| Writer handling a whole chunk | Log chunk ref, item count, outcome | Misattributing error to the last item |
| Logging attempts vs skips | Separate `attempt_failed`, `item_skipped`, `chunk_failed` | Calling every error “final item failure” |
| Multi-threaded logging | Scope MDC per task, clean up in `finally` | Letting MDC leak into the next task |
| Metrics | Label by job, step, stage, error code | Putting item key/chunk key as metric labels |
| Idempotency/restart | Use dedicated business keys/checkpoints | Using chunk ref as a transaction key |
| Log aggregation | Mask data at source; restrict access and retention | Assuming safe log text guarantees a safe pipeline |

**Cardinality:** item keys and chunk keys typically have huge value spaces. They belong as **searchable fields in logs** during investigation, never as time-series metric labels (Prometheus/Micrometer), where they explode series counts and storage costs. Aggregate metrics over bounded dimensions like `job_name`, `step_name`, `stage`, and `error_code`.

**Accuracy:** logs are an observability channel, not Spring Batch's transaction log. During rollbacks, retries, network glitches, or collector hiccups, events can duplicate or drop. If auditing requires “each item has exactly one final outcome”, use an audit table or transactional outbox with idempotency keys and proper commit semantics.

**Security:** restrict log-read permissions, retention TTLs, token-mapping access, and HMAC keys. Never dump full `JobParameters` or `ExecutionContext` into logs for context, because both objects can hold data outside your allowlist.

## 12. Hands-on Exercise

Create an `importOrdersJob` with chunk size 3 and an input of at least 7 records, where one item has a validation error and one item triggers a transient service error:

1. Create `OrderRow` with `orderId`, `customerEmail`, and `amount`. Build `ItemRefFactory` using HMAC with a test key; verify identical order IDs produce identical item refs while different IDs produce different refs.
2. Attach `ChunkTraceListener` to the step. Run a successful pass and observe chunk events with `jobExecutionId`, `stepExecutionId`, and sequence.
3. Wrap the real processor with `ItemTraceProcessor`. On validation failure, verify `item_ref` appears while email, raw ID, and amount stay absent from logs.
4. Configure `retry` for transient errors in the processor. Fail twice then succeed; compare attempt events against final item outcomes.
5. Configure `skip` for validation errors. Use `SkipListener` to emit the **item skipped event**, distinct from processor attempt exceptions.
6. Have the writer throw an error before commit and observe `chunk_ref` on rollback and retry. Confirm you do not infer the failing item from `chunk_ref` alone when the writer handles multiple records.
7. Trigger a restart after a `FAILED` job on a durable repository. Verify reprocessed items keep the same `item_ref` while execution/chunk references change.
8. Run a multi-threaded or partitioned step and confirm task MDCs never mix. If using async tasks, add a propagation wrapper and cleanup.
9. Capture all logs with a Logback test appender and verify synthetic sensitive data never appears. Also check JSON encoders, exception layouts, and tracing if enabled.
10. Define a dashboard counting skipped items and chunk rollbacks by error code, job, and step; exclude item/chunk references from metric labels.

When attaching chunk or item keys to Spring Batch logging, pick **the right key scope and lifecycle**. `chunk_ref` groups logs for a single processing pass, `item_ref` tracks the same data across retries/restarts, and `JobExecution`/`StepExecution` link logs to framework metadata. Using keys derived from stable identities, tokenizing sensitive IDs, bounding MDC lifetimes, and distinguishing technical attempts from business outcomes keeps logs valuable without increasing data-exposure risk.
