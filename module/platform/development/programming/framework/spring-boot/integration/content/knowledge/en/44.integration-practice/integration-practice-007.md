# Building an IntegrationFlow to Ingest, Validate, Transform, and Route Files

## 1. Practice Context

A **Spring Boot Integration** application needs to ingest CSV files delivered by a partner to a shared directory, validate their contents, normalize them into Java objects, and route them to services handling **orders** or **inventory movements**. This lesson combines HTTP/DB/broker adapters at the business layer with **Enterprise Integration Patterns (EIP)** in Spring Integration: file inbound adapter, polling consumer, transformer, filter, content-based router, service activator, and error channel.

### Problem Statement and Data Contract

To focus on assembling an `IntegrationFlow`, the convention specifies **one record per file** encoded in UTF-8, with exactly two lines: a fixed header and one data line.

~~~csv
type,requestId,sku,quantity
ORDER,req-1001,SKU-42,3
~~~

Example inventory adjustment request:

~~~csv
type,requestId,sku,quantity
STOCK,req-1002,SKU-42,-3
~~~

| Field | Practice Rule | Meaning |
| --- | --- | --- |
| `type` | `ORDER` or `STOCK` | Routing key |
| `requestId` | 1–64 alphanumeric, `_`, or `-` characters | Cross-system idempotency key |
| `sku` | 1–64 characters from the same character set | Product identifier |
| `quantity` | 32-bit integer; `ORDER > 0`; `STOCK != 0` | Order quantity or inventory delta |

The partner writes to a temporary `.writing` file, closes it, and then renames it to `*.ready.csv` once finished. The application **reads only `*.ready.csv`**. This convention lowers the risk of the consumer seeing half-written files.

~~~mermaid
flowchart TD
    A[Partner writes .writing] --> B[Renames to .ready.csv]
    B --> C[File inbound adapter and poller]
    C --> D[Payload: java.io.File]
    D --> E[Parser builds ImportCandidate]
    E --> F{Valid data?}
    F -- No --> Q[rejectedImports]
    Q --> R[Quarantine, save reason]
    F -- Yes --> G[Transformer builds NormalizedImport]
    G --> H{Route by type}
    H -- ORDER --> I[orderImports]
    H -- STOCK --> J[stockImports]
    I --> K[Order handler]
    J --> L[Stock handler]
    K --> M[DB or HTTP + archive]
    L --> M
    E -. Exception .-> X[fileImportErrors]
    G -. Exception .-> X
    K -. Exception .-> X
    L -. Exception .-> X
    X --> Y[Incident and controlled redrive]
~~~

**Classify errors from the start:** missing columns or `quantity=abc` are **data errors** to reject with an explanation; dropped DB connections, file read errors, or HTTP timeouts are **technical errors** to send to the error channel and a retry/redrive workflow. Neither group should silently drop out of the flow.

## 2. Preparing the Application

With Spring Boot 3.x and Java 17+, declare the following Maven dependencies; versions are managed by the Spring Boot BOM:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-file</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Java DSL is built directly into modern Spring Integration modules; the legacy `spring-integration-java-dsl` dependency is unnecessary. If using Spring Boot 4.x, check corresponding dependencies and APIs for that version.

~~~yaml
# application.yml
app:
  import:
    inbox: ./data/inbox
    processed: ./data/processed
    rejected: ./data/rejected
spring:
  application:
    name: file-integration-practice
logging:
  level:
    org.springframework.integration: INFO
~~~

~~~text
data/
├── inbox/       # Only *.ready.csv files are processed
├── processed/   # Successfully processed files
└── rejected/    # Invalid files and rejection reasons
~~~

In containers, mount directories via volumes and environment variables, verify read/write permissions and disk space, and prevent multiple instances from scanning the same directory without a claim mechanism.

## 3. Intermediate Message Models

After ingestion, the message payload is a `File`. The parser converts it into `ImportCandidate`, keeping quantity as text alongside any errors. A filter decides whether to proceed. Only then does the transformer build `NormalizedImport` with typed values.

~~~java
import java.io.File;
import java.util.List;

public record ImportCandidate(
        File file,
        String type,
        String requestId,
        String sku,
        String quantityText,
        List<String> errors) {

    public boolean valid() {
        return errors.isEmpty();
    }
}

public enum ImportType {
    ORDER, STOCK
}

public record NormalizedImport(
        File source,
        ImportType type,
        String requestId,
        String sku,
        int quantity) {
}
~~~

Place the three `public` types in three separate Java files within the same package; this lesson combines them for readability. This boundary retains the original file path for archiving/quarantining, shields business handlers from invalid inputs, and lets you swap the CSV parser for JSON/XML without rewriting downstream branches.

## 4. Parser Checking Structure and Basic Rules

The parser below handles the **single-record CSV without embedded commas** case. For production CSVs with quoting/escaping or multiple rows, use Apache Commons CSV or Jackson CSV with streaming; never use `String.split(",")` for general-purpose CSV parsing.

~~~java
import java.io.File;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import org.springframework.stereotype.Component;

@Component
public class CsvImportParser {

    private static final String HEADER = "type,requestId,sku,quantity";
    private static final long MAX_SIZE = 64 * 1024;

    public ImportCandidate parse(File file) {
        List<String> lines;
        try {
            if (java.nio.file.Files.size(file.toPath()) > MAX_SIZE) {
                return invalid(file, "File exceeds 64 KiB");
            }
            lines = java.nio.file.Files.readAllLines(
                    file.toPath(), StandardCharsets.UTF_8);
        } catch (IOException ex) {
            throw new UncheckedIOException("Failed to read " + file.getName(), ex);
        }

        if (lines.size() != 2 || !HEADER.equals(lines.get(0))) {
            return invalid(file, "Requires exact header and one data row");
        }
        String[] fields = lines.get(1).split(",", -1);
        if (fields.length != 4) {
            return invalid(file, "Data row must have exactly 4 fields");
        }

        String type = fields[0].trim().toUpperCase(Locale.ROOT);
        String requestId = fields[1].trim();
        String sku = fields[2].trim();
        String quantityText = fields[3].trim();
        List<String> errors = new ArrayList<>();

        if (!type.equals("ORDER") && !type.equals("STOCK")) {
            errors.add("type must be ORDER or STOCK");
        }
        if (!requestId.matches("[A-Za-z0-9_-]{1,64}")) {
            errors.add("Invalid requestId format");
        }
        if (!sku.matches("[A-Za-z0-9_-]{1,64}")) {
            errors.add("Invalid sku format");
        }

        try {
            int quantity = Integer.parseInt(quantityText);
            if ("ORDER".equals(type) && quantity <= 0) {
                errors.add("ORDER must have quantity > 0");
            }
            if ("STOCK".equals(type) && quantity == 0) {
                errors.add("STOCK must have non-zero quantity");
            }
        } catch (NumberFormatException ex) {
            errors.add("quantity must be a 32-bit integer");
        }

        return new ImportCandidate(
                file, type, requestId, sku, quantityText, List.copyOf(errors));
    }

    private ImportCandidate invalid(File file, String message) {
        return new ImportCandidate(file, "", "", "", "", List.of(message));
    }
}
~~~

Data errors produce an `ImportCandidate` containing `errors` to be explained in `rejectedImports`. File I/O errors throw `UncheckedIOException` so they route to `fileImportErrors`. Checking file size before `readAllLines` suffices for a sandbox whose producer follows the rename protocol, not for untrusted file ingestion or very large files. Production needs streaming read bounds, encoding checks, concurrency guards against writers, and upload size enforcement.

## 5. Normalizing Transformer

Once the filter guarantees the candidate is valid, the transformer converts `type` to an enum and `quantity` to an integer. This marks the data-contract boundary between the partner's format and the internal model.

~~~java
import org.springframework.stereotype.Component;

@Component
public class ImportNormalizer {

    public NormalizedImport normalize(ImportCandidate candidate) {
        if (!candidate.valid()) {
            throw new IllegalArgumentException("Candidate is not valid");
        }
        return new NormalizedImport(
                candidate.file(),
                ImportType.valueOf(candidate.type()),
                candidate.requestId(),
                candidate.sku(),
                Integer.parseInt(candidate.quantityText()));
    }
}
~~~

The parser has already validated the preconditions for `valueOf` and `parseInt` to succeed. If the external contract changes, you can swap the parser/validator while keeping the `NormalizedImport` API intact for business handlers.

## 6. Assembling the IntegrationFlow: Ingest → Validate → Transform → Route

The configuration below is the centerpiece. `Files.inboundAdapter` creates a `FileReadingMessageSource`; the poller checks every 5 seconds and picks up at most 10 matching files per cycle. Downstream stages run synchronously, and the router dispatches messages to channels matching `type`.

~~~java
import java.io.File;
import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.file.dsl.Files;

@Configuration
public class FileImportFlowConfig {

    @Bean
    IntegrationFlow fileImportFlow(
            @Value("${app.import.inbox}") File inbox,
            CsvImportParser parser,
            ImportNormalizer normalizer) {

        return IntegrationFlow
                .from(Files.inboundAdapter(inbox)
                                .autoCreateDirectory(true)
                                .patternFilter("*.ready.csv")
                                .preventDuplicates(true),
                        endpoint -> endpoint.poller(
                                Pollers.fixedDelay(Duration.ofSeconds(5))
                                        .maxMessagesPerPoll(10)
                                        .errorChannel("fileImportErrors")))
                .transform(File.class, parser::parse)
                .filter(ImportCandidate.class,
                        ImportCandidate::valid,
                        spec -> spec.discardChannel("rejectedImports"))
                .transform(ImportCandidate.class, normalizer::normalize)
                .route(NormalizedImport.class,
                        value -> value.type().name(),
                        spec -> spec
                                .channelMapping("ORDER", "orderImports")
                                .channelMapping("STOCK", "stockImports")
                                .defaultOutputChannel("unsupportedImports"))
                .get();
    }

    @Bean
    IntegrationFlow orderImportFlow(ImportHandlers handlers) {
        return IntegrationFlow.from("orderImports")
                .handle(handlers, "handleOrder")
                .get();
    }

    @Bean
    IntegrationFlow stockImportFlow(ImportHandlers handlers) {
        return IntegrationFlow.from("stockImports")
                .handle(handlers, "handleStock")
                .get();
    }

    @Bean
    IntegrationFlow rejectedImportFlow(RejectedImportHandler handler) {
        return IntegrationFlow.from("rejectedImports")
                .handle(handler, "handle")
                .get();
    }

    @Bean
    IntegrationFlow unsupportedImportFlow(UnsupportedImportHandler handler) {
        return IntegrationFlow.from("unsupportedImports")
                .handle(handler, "handle")
                .get();
    }

    @Bean
    IntegrationFlow fileImportErrorFlow(FileImportErrorHandler handler) {
        return IntegrationFlow.from("fileImportErrors")
                .handle(handler, "handle")
                .get();
    }
}
~~~

### Role and Payload Types of Each Stage

| Stage | Payload In → Out | Role |
| --- | --- | --- |
| `Files.inboundAdapter` | File on disk → `java.io.File` | Discovers files matching pattern |
| `Pollers.fixedDelay(5s)` | Polling schedule | Triggers source, up to 10 messages/poll; does not mean 10 parallel threads |
| `transform(File.class, parser::parse)` | `File → ImportCandidate` | Reads and validates syntax |
| `filter(...valid...)` | `ImportCandidate` or discard | Contract errors route to `rejectedImports` |
| `transform(...normalize...)` | `ImportCandidate → NormalizedImport` | Normalizes data types |
| `route(...type...)` | `NormalizedImport → channel` | Chooses ORDER/STOCK from message content |
| `handle(...)` | Message → side effect | Invokes integration service, archive, or quarantine |
| `errorChannel(...)` | Exception → `ErrorMessage` | Records incident for failures during polling execution |

`filter` does not automatically throw an error when the predicate returns false; `discardChannel` actively preserves rejected files. When configuring a router, add `defaultOutputChannel` so messages with a newly introduced type never drop silently. Notice `unsupportedImports` here receives **`NormalizedImport`**, whereas `rejectedImports` receives **`ImportCandidate`**; each branch must have a handler expecting the right payload type.

By default, these channels connect synchronously (`DirectChannel`). Hence an exception in any handler propagates back to the poller and becomes an `ErrorMessage` on `fileImportErrors`. If you later introduce `ExecutorChannel`, `QueueChannel`, or reactive adapters, redesign error channels, correlation, transactions, and async error reporting: the poller's error channel does not automatically catch exceptions thrown after handoff to another thread.

## 7. Handlers on the Routed Branches

Spring Integration handles **message orchestration**; business execution sits behind interfaces implemented via Spring Data JDBC/JPA, HTTP clients, brokers, or other Spring Integration adapters. Example integration port declarations:

~~~java
public interface ImportApplicationService {
    void applyOrder(String requestId, String sku, int quantity);
    void applyStockDelta(String requestId, String sku, int delta);
}

public interface FileImportArchive {
    void markProcessed(java.io.File source);
    void reject(java.io.File source, java.util.List<String> errors);
}
~~~

To run the application, register beans implementing these two interfaces for your target environment. Keeping DB/API/broker calls behind ports avoids mixing infrastructure code into flow definitions. In production, the service must enforce durable idempotency and manage transactions per downstream contract.

~~~java
import org.springframework.stereotype.Component;

@Component
public class ImportHandlers {
    private final ImportApplicationService service;
    private final FileImportArchive archive;

    public ImportHandlers(
            ImportApplicationService service, FileImportArchive archive) {
        this.service = service;
        this.archive = archive;
    }

    public void handleOrder(NormalizedImport message) {
        service.applyOrder(
                message.requestId(), message.sku(), message.quantity());
        archive.markProcessed(message.source());
    }

    public void handleStock(NormalizedImport message) {
        service.applyStockDelta(
                message.requestId(), message.sku(), message.quantity());
        archive.markProcessed(message.source());
    }
}
~~~

**Ordering matters:** handlers call `markProcessed` only after the service confirms success. If HTTP succeeded yet the app crashed before archiving, a rerun may issue the same request again. `requestId` must serve as an idempotency key at the database or partner layer; filename filtering alone never achieves exactly-once.

### Data Rejection Branch

~~~java
import org.springframework.stereotype.Component;

@Component
public class RejectedImportHandler {
    private final FileImportArchive archive;

    public RejectedImportHandler(FileImportArchive archive) {
        this.archive = archive;
    }

    public void handle(ImportCandidate rejected) {
        archive.reject(rejected.file(), rejected.errors());
    }
}

@Component
public class UnsupportedImportHandler {
    private final FileImportArchive archive;

    public UnsupportedImportHandler(FileImportArchive archive) {
        this.archive = archive;
    }

    public void handle(NormalizedImport unsupported) {
        archive.reject(
                unsupported.source(),
                java.util.List.of("No handler branch for: " + unsupported.type()));
    }
}
~~~

Place the two `public` classes in separate Java files. Under the current contract, the validator rejects any `type` other than `ORDER`/`STOCK`; `unsupportedImports` guards against future enum additions lacking a router mapping.

`FileImportArchive` can create target directories via `java.nio.file.Files.createDirectories`, write a `.reason.txt` sidecar, and move the file with `Files.move`. Never overwrite an existing processed file with the same name; construct target paths safely inside configured directories. Quarantine should keep the raw input, timestamp, schema version, and error list for investigation. If writing reasons or moving the file fails, throw an exception rather than pretending rejection succeeded.

### Technical Error Branch from the Poller

In a synchronous chain, uncaught handler exceptions route to `fileImportErrors`. The handler below only illustrates logging; production needs structured logging, incident persistence, metrics, alerts, and recovery procedures.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.stereotype.Component;

@Component
public class FileImportErrorHandler {
    private static final Logger log =
            LoggerFactory.getLogger(FileImportErrorHandler.class);

    public void handle(ErrorMessage message) {
        Throwable failure = message.getPayload();
        Object failedPayload = null;

        if (failure instanceof MessagingException messagingFailure) {
            Message<?> failedMessage = messagingFailure.getFailedMessage();
            if (failedMessage != null) {
                failedPayload = failedMessage.getPayload();
            }
        }

        String source = "unknown";
        if (failedPayload instanceof java.io.File file) {
            source = file.getAbsolutePath();
        } else if (failedPayload instanceof ImportCandidate candidate) {
            source = candidate.file().getAbsolutePath();
        } else if (failedPayload instanceof NormalizedImport item) {
            source = item.source().getAbsolutePath();
        }

        log.error("fileImport error, source={}", source, failure);
        // TODO: persist incident by correlation/requestId and trigger redrive.
    }
}
~~~

Avoid logging file contents or sensitive identifiers. `ErrorMessage` lets you inspect the exception and failed message, though recovering the failed message depends on where the exception was raised. Best practice is attaching `sourcePath` and a stable correlation ID as headers at the start of the flow or tracking processing state in a repository.

## 8. Reliability: File Filters, Idempotency, and Transactions

### 8.1. Limitations of `preventDuplicates(true)`

`preventDuplicates(true)` uses an in-memory `AcceptOnceFileListFilter`. It reduces re-polling of a file within a single run, yet **is not** an exactly-once guarantee:

- After an app restart, in-RAM accept-once state disappears. Files still sitting in `inbox` will be read again.
- When the adapter marks a file *accepted* and a downstream handler throws, the file is typically **not picked up again in the same run** on later polls. You need a policy to clear the marker, move the file to a retry area, or execute a controlled redrive.
- Two instances with separate RAM filters can pick up the same file from a shared filesystem.
- Ingesting a file once does not guarantee one side effect, because DB commits, HTTP requests, and file moves are not atomic together.

To survive restarts, evaluate `FileSystemPersistentAcceptOnceFileListFilter` backed by a durable `ConcurrentMetadataStore`. Across multiple nodes, use a shared metadata store (e.g., Redis) plus filesystem-compatible claiming/locking, along with downstream idempotency keys. If metadata marks a file accepted before processing finishes, ensure a clear recovery procedure so files are never orphaned.

### 8.2. A Safer Processing Workflow

A production system can be structured as follows:

1. **File handoff:** producer writes `name.writing`, flushes/closes, and renames to `name.ready.csv`. Never guess completion from `mtime`.
2. **Claim:** consumer creates a `RECEIVED/PROCESSING` record keyed by unique file key (or request ID) in durable storage. Across nodes, only one node claims successfully.
3. **Validate and route:** invalid data → `REJECTED` and quarantine; valid data → map to internal model and send to adapter.
4. **Idempotent side effects:** DB writes enforce unique `(sourceSystem, requestId)`; downstream APIs use stable idempotency keys; broker consumers also deduplicate.
5. **Finalize:** record `COMPLETED` after business confirmation, then archive. If archiving fails, subsequent runs see `COMPLETED` and only repeat the archive step.
6. **Recovery:** retryable faults get bounded retries with backoff and `RETRY_PENDING`; data errors get quarantined; unrecoverable faults alert and audit redrives.

### 8.3. Classifying Failure Scenarios

| Situation | Recommended Handling | What to Avoid |
| --- | --- | --- |
| Bad header, missing fields, invalid quantity | `rejectedImports`; save reason and raw file | Silently dropping the message |
| Unreadable file, permission error | `fileImportErrors`; record incident; redrive after fixing permissions | Retrying continuously without limit |
| HTTP timeout, partner may have processed | Retry with same idempotency key and check partner status | Generating a new request ID per retry |
| DB commit succeeded, file move failed | Persist completed state durably; next run only archives | Re-applying business data |
| Persistent filter recorded, consumer crashed | Controlled metadata recovery/reset reconciled with processing state | Equating accepted with completed |
| Two pods read the same file | Shared claim/lock + downstream idempotency | Relying on per-pod `preventDuplicates(true)` |
| File with 10,000 rows | Streaming/batching, consider `split()` and `aggregate()`, explicit partial-success policy | Loading everything into RAM for one giant transaction |

In short, **file locks, file filters, and idempotency solve different problems**. File locks restrict concurrent file opens; accept-once limits re-reading from the source; idempotency protects business side effects whenever messages are replayed for any reason.

## 9. Testing Each Path of the Flow

Before running, provide beans implementing `ImportApplicationService` and `FileImportArchive`. In a sandbox, these adapters can write to a test database or output files named by `requestId`; this lesson does not assume a live partner endpoint. Verify outputs and logs against each scenario below.

**Scenario A — valid ORDER file**

1. Start the app; create `data/inbox/order-001.writing` with the `ORDER` sample from the start of the lesson.
2. Close it and rename to `order-001.ready.csv`.
3. Adapter emits `File`; parser returns `ImportCandidate(valid=true)`; normalizer produces `NormalizedImport(ORDER, req-1001, SKU-42, 3)`.
4. Router sends to `orderImports`; handler calls `applyOrder` and then `markProcessed`.
5. Verify request ID, quantity, file archived, and no further polling.

**Scenario B — valid STOCK file:** create `stock-001.ready.csv` containing `STOCK,req-1002,SKU-42,-3`. Only `applyStockDelta` is called with `-3`; the ORDER handler is not invoked.

**Scenario C — contract error:** create `bad-001.ready.csv` containing `ORDER,req-1003,SKU-42,abc`. Parser builds a candidate with error `quantity must be a 32-bit integer`; filter routes to `rejectedImports` without calling business adapters. Verify raw file and reason exist in quarantine.

**Scenario D — technical error:** make the service throw an exception in `applyOrder`. Verify `fileImportErrors` logs the incident and the file is not marked processed. After fixing the fault, execute your app's redrive; if the downstream request already succeeded, the adapter must detect the duplicate and avoid a second side effect.

**Scenario E — incomplete file:** create only `order-002.writing`. Confirm the adapter ignores it across several polls; processing starts only after renaming to `.ready.csv`.

### Automated Tests Should Span Three Layers

| Layer | Example Checks | Scope |
| --- | --- | --- |
| Parser unit tests | Exact two lines; missing header; code > 64 chars; integer overflow; negative ORDER quantity | Syntax + data rules |
| Transformer/handler unit tests | Valid candidate → right enum/int; service called before archive | Mapping + business coordination |
| Integration tests | Write files to `@TempDir`, wait for poll with timeout, assert output/quarantine/error, test restart/redrive | Endpoint wiring and real side effects |

Example standalone parser unit test:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class CsvImportParserTest {
    @TempDir Path tempDir;

    @Test
    void rejectsNonNumericQuantity() throws Exception {
        Path file = tempDir.resolve("bad.ready.csv");
        Files.writeString(file,
                "type,requestId,sku,quantity\n" +
                "ORDER,req-9,SKU-1,abc\n",
                StandardCharsets.UTF_8);

        ImportCandidate result = new CsvImportParser().parse(file.toFile());

        assertFalse(result.valid());
        assertTrue(result.errors().stream()
                .anyMatch(e -> e.contains("32-bit integer")));
    }
}
~~~

With `@SpringBootTest`, use `@DynamicPropertySource` to point `app.import.inbox` at a temporary directory and mock/stub target adapters. Since polling runs asynchronously on a schedule, use bounded condition waiting instead of fixed `Thread.sleep` calls that make tests slow and flaky. Never run file-intake tests against production paths.

### Expected Outcome Matrix

| Input | Outcome |
| --- | --- |
| `ORDER,req-1,SKU-1,2` | Order handler called, archived successfully |
| `STOCK,req-2,SKU-1,-2` | Stock handler called with negative delta |
| `ORDER,req-3,SKU-1,0` | Rejected: invalid ORDER quantity |
| `STOCK,req-4,SKU-1,0` | Rejected: invalid STOCK quantity |
| `REFUND,req-5,SKU-1,1` | Rejected: unsupported type |
| Three-line file or bad header | Rejected: file contract violation |
| `quantity=2147483648` | Rejected: outside 32-bit integer range |
| Only `.writing` file present | No message emitted |
| Handler throws exception | Error channel records incident, not archived |
| Same `requestId` replayed | Business layer incurs no second side effect |

## 10. Observability, Load, and Acceptance Criteria

In integrated systems, logs should include `requestId`, filename, branch identifier, start/end timestamps, and outcome. Metrics can include `files_discovered_total`, `files_rejected_total{reason}`, `files_processed_total{type}`, `file_processing_duration_seconds`, `file_import_errors_total{stage}`, and oldest pending file age. Never put request ID or filename into metric labels because cardinality grows unbounded.

`fixedDelay` and `maxMessagesPerPoll` only govern how messages are pulled from the source. With `DirectChannel`, slow synchronous handlers tie up the poll cycle. If adding executors/queues for throughput, bound queue capacity, timeouts, circuit breakers, claiming, per-SKU ordering, and async error handling. With DBs/brokers, design transaction boundaries and outbox/inbox patterns to avoid lost events across independent commits.

**Practice completion criteria:**

- Completed files are ingested once in normal operation; `.writing` files are ignored.
- Invalid inputs are explained and quarantined without calling business adapters.
- Valid data is normalized and routed to the right ORDER or STOCK handler.
- Downstream failures are recorded with a retry/redrive process; files are never archived before business success.
- Restarts, same-`requestId` replays, and archive failures do not duplicate downstream side effects.
- Tests cover the parser, routing, rejection branch, error branch, and end-to-end file flow.

When extending this lesson to HTTP, JDBC, cache, RabbitMQ/Kafka, or other Spring Integration adapters, the ingest/validate/transform/route flow remains a reusable EIP backbone. What demands the most care is **message contracts, idempotency, transactions, error boundaries, and observability**.

## References

- [Spring Integration Reference — File Reading](https://docs.spring.io/spring-integration/reference/file/reading.html)
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl/java-basics.html)
- [Spring Integration Reference — Pollers](https://docs.spring.io/spring-integration/reference/dsl/java-pollers.html)
- [Spring Integration Reference — Routers](https://docs.spring.io/spring-integration/reference/router/implementations.html)
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
