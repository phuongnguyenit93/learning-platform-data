# Masking Data in Spring Batch Logs

## 1. Why is log masking a batch security requirement?

In Spring Batch, a job typically reads thousands to millions of records from files, databases, message brokers, or APIs; processes them using \`ItemReader\`, \`ItemProcessor\`, and \`ItemWriter\`; and writes logs to track progress, skips, retries, and errors. Data flowing through the job can include email addresses, phone numbers, customer names, physical addresses, account numbers, identification numbers, payment card numbers, access tokens, and extensive internal information.

If code logs entire objects verbatim, sensitive data can be copied to consoles, log files, monitoring systems, centralized log aggregation platforms, or CI error reports. Logs often have retention periods, access audiences, and replication scopes that **differ** from the original business database.

Example of unsafe logging:

~~~text
INFO  Processing order: Order(id=O17, email=linh@example.test,
      cardNumber=4111111111111111, accessToken=eyJhbGci...)
WARN  Skip invalid row: 2026-11-16,Nguyen Van A,0900000000,4111111111111111
ERROR API call failed: Authorization: Bearer secret-token-value
~~~

Once these lines reach log aggregation, deleting the source record **does not erase the copied logs**. Therefore, the goal of this lesson is not simply replacing a few characters with \`*\`, but controlling **what information is permitted to appear across every logging path**.

A more appropriate log:

~~~text
INFO  event=order.processing jobExecutionId=801 orderRef=r_7af3c8d1
WARN  event=order.skipped jobExecutionId=801
      stepName=importOrdersStep phase=PROCESS
      orderRef=r_7af3c8d1 reasonCode=INVALID_AMOUNT
ERROR event=external.request.failed jobExecutionId=801
      dependency=risk-api failureClass=AUTHENTICATION_FAILURE
      httpStatus=401
~~~

Here, the \`orderRef\` values are **illustrative synthetic identifiers**, not real HMACs computed from the data above. The log retains enough fields for incident tracing without repeating emails, PANs, or tokens.

In the context of **Spring Batch Core Processing → Security**, grasp three principles:

1. **Do not log sensitive data unnecessarily.** Omitting a field is usually safer than partially masking it.
2. **Mask before logs leave the application.** Collector filters are only a secondary defense line, not a substitute for protection at the source.
3. **Preserve controlled operability.** Use execution IDs, Steps, events, reason codes, counters, and reference codes that do not reveal the original information.

## 2. How do masking, redaction, pseudonymization, and encryption differ?

| Approach | Goal | Format example | Considerations |
|---|---|---|---|
| **Omit** | Keep value out of logs | Log only \`hasEmail=true\` if truly needed | Usually the preferred choice |
| **Redact** | Replace entire value with fixed marker | \`email=[REDACTED]\` | Does not support searching by original value |
| **Mask** | Hide part of value, retain permitted portion | \`phone=********42\` | Remaining portion may still identify an individual |
| **Pseudonymize** | Replace with a controllably linkable reference | \`customerRef=r_a7c2...\` | May still count as personal data depending on context |
| **HMAC** | Generate keyed reference tag for correlation | Truncated \`HMAC(key, customerId)\` | Unlike plain hash; key must be protected |
| **Unkeyed hash** | Mathematically one-way digest | \`SHA-256(email)\` | Vulnerable to dictionary guessing for low-entropy values |
| **Encryption** | Preserve decryptability for key holders | Ciphertext | Does not automatically make data safe to log; keys and access control still matter |

**Masking does not automatically make data anonymous.** An email retaining its domain, a phone number retaining a few digits, or a stable hashed customer ID can still identify an individual in some contexts. Absent a clear business requirement, use \`[REDACTED]\` or omit the field entirely from logs.

Example of the same event:

~~~text
Unsafe:
  event=order.failed email=linh@example.test token=secret123

Redacted:
  event=order.failed email=[REDACTED] token=[REDACTED]

Minimized:
  event=order.failed reasonCode=INVALID_AMOUNT
  jobExecutionId=801 stepName=validateOrdersStep

Customer correlation needed and approved:
  event=order.failed customerRef=h_74b9f2ce...
  reasonCode=INVALID_AMOUNT jobExecutionId=801
~~~

The final choice must follow internal policies on data classification, log retention, tracing purpose, and access control. Never assume keeping the last four digits of a card or part of an account number is automatically allowed.

## 3. Classify data before building a logging policy

Define policies **per field category** rather than trying to write one generic regex to guess what is sensitive.

| Data category | Examples | Baseline logging policy |
|---|---|---|
| **Secrets** | Passwords, API keys, access tokens, session cookies, private keys | Never log values; keep no prefix/suffix |
| **Payment data** | Full card numbers, CVV/CVC, transaction auth data | Never log; comply with applicable payment security standards |
| **Direct PII** | Emails, phone numbers, IDs, physical addresses | Omit or redact; partially mask only with justification and policy |
| **Indirect PII** | Customer IDs, order IDs traceable to individuals | Use opaque references or keyed HMAC if correlation is required |
| **Financial data** | Balances, income details, transaction payloads | Never log full details; use aggregates or approved value buckets |
| **Batch metadata** | jobName, jobExecutionId, stepName, stepExecutionId, BatchStatus | Generally useful, though still check names/files/paths |
| **Statistics** | readCount, writeCount, skipCount, duration, reason code | Appropriate if labels do not leak details via overly granular tags |
| **System details** | Hosts, internal URLs, SQL queries, stack traces | Log only to the needed level; may contain secrets and source data |

This is a restrictive baseline policy. Official rules must be aligned with security, legal, and industry requirements if the data is regulated.

### Establish an allowlist instead of a blacklist

An **allowlist** lists the fields permitted in logs. For example, the \`order.skipped\` event is permitted only to contain:

~~~text
event
jobExecutionId
stepExecutionId
stepName
phase
reasonCode
safeRecordRef (if authorized)
~~~

If a business record gains a \`nationalId\` field in a future version, it **does not automatically appear** in logs because it is not on the allowlist. This is the advantage over logging whole objects and trying to strip "familiar" fields with a blacklist.

Never rely solely on field names as proof. Fields named \`id\`, \`message\`, \`path\`, \`details\`, or \`reason\` can still carry tokens, emails, or sensitive data.

## 4. Spring Batch-specific leak paths

A job can emit logs from many places beyond explicit \`log.info\` calls written by the application.

| Location | Risk | Primary control |
|---|---|---|
| \`ItemReader\` | Raw CSV lines, JSON payloads, SQL statements/bind parameters | Never log raw input; configure library loggers and parse errors |
| \`ItemProcessor\` | Object \`toString()\`, sensitive fields in validation messages | Log event + reasonCode + opaque reference |
| \`ItemWriter\` | SQL parameters, API requests/responses, file contents | Log only counts, outcomes, and safe error codes |
| \`SkipListener.onSkipInRead\` | Parse exceptions containing the full input line | Never print \`FlatFileParseException.getInput()\` |
| \`SkipListener.onSkipInProcess\` | Full item object and exception message | Never log the item directly; only safe fields |
| \`SkipListener.onSkipInWrite\` | Entire chunk or failed write payload | Control logged keys and throwables |
| \`JobExecutionListener\` | Dumping entire JobParameters | Use an allowlist; never log raw parameters |
| \`StepExecutionListener\` | ExecutionContext holding custom state | Never serialize/dump the whole context |
| Retry/rollback logging | Throwables from HTTP/DB containing request bodies | Classify errors; never print raw messages uncontrolled |
| MDC | Sensitive values automatically attached to every log on thread | Store only safe technical IDs; clean up/restore |
| JDBC/ORM/HTTP debug | SQL bind values, Authorization headers, bodies | Disable sensitive payload tracing/DEBUG in production |
| APM/traces/metrics | Span attributes, baggage, metric labels containing PII | Apply an allowlist just like logs |
| Exceptions in job metadata | \`ExitStatus.exitDescription\`, failure exceptions | Keep data out of messages; restrict metadata access |

In particular, **Spring Batch JobRepository is a metadata store**, not plain-text logs. If the application throws an exception containing raw input in its message, that content can surface in failure details or execution viewers. Configuring Logback masking alone **does not protect values persisted elsewhere**.

### \`FlatFileParseException\` can contain the full input line

With \`FlatFileItemReader\`, tokenizer or field-mapper errors may be wrapped in \`FlatFileParseException\`. The exception object carries the line number and **input** of the failing line. Example:

~~~csv
orderId,email,amount
O101,linh@example.test,not-a-number
~~~

Do not do this:

~~~java
catch (FlatFileParseException ex) {
    log.error("Could not parse {}", ex.getInput(), ex);
}
~~~

Here both \`ex.getInput()\` and the stack trace can expose source data. Switch to structured logging:

~~~java
catch (FlatFileParseException ex) {
    log.warn(
        "event=input.parse.failed lineNumber={} reasonCode={}",
        ex.getLineNumber(), "INVALID_NUMBER");
    throw ex;
}
~~~

This snippet illustrates safer logging; **rethrowing the exception can still cause the framework or another listener to log the raw exception at another layer**. Audit actual loggers rather than assuming catching and rethrowing makes the entire logging flow safe.

## 5. Structuring a safe log event

Instead of logging the object:

~~~java
log.info("Processing order={}", order);
~~~

Define an event with enough data for investigation without sensitive fields:

~~~java
log.info(
        "event=order.processing jobExecutionId={} stepName={} recordRef={}",
        jobExecutionId,
        "validateOrdersStep",
        safeRecordRef);
~~~

If \`safeRecordRef\` is merely an \`orderId\` that can be traced back to a customer name, it must still be evaluated under policy. Use a dedicated operational opaque ID or an approved HMAC.

Example business record:

~~~java
import java.math.BigDecimal;

public record RawOrder(
        String orderId,
        String customerEmail,
        String phoneNumber,
        String accessToken,
        BigDecimal amount) {
}
~~~

Java records generate a default \`toString()\` containing **component values**. Calling \`log.debug("{}", rawOrder)\` can expose email, phone, and access token directly. Never rely on a class name or the fact that it is a DTO to assume \`toString()\` is safe.

A dedicated logging DTO:

~~~java
public record SafeOrderLogEvent(
        String event,
        long jobExecutionId,
        String stepName,
        String recordRef,
        String reasonCode) {
}
~~~

Construct this object only from **pre-classified safe values**; never map entire business records via reflection. Even with a log DTO, if \`recordRef\` or \`reasonCode\` is taken directly from untrusted input, it can still be abused to inject data or newlines into logs.

### Using fixed reason codes

Instead of:

~~~text
reason=Invalid phone 0900000000 for customer linh@example.test
~~~

Use:

~~~text
reasonCode=INVALID_PHONE_FORMAT
field=phoneNumber
phase=PROCESS
jobExecutionId=801
~~~

Field names, phases, and reasonCodes should come from **controlled enums/constants**, never raw exception messages or user input. When details are needed to fix a record, store them in a properly authorized error-handling store with a separate retention policy rather than using shared logs as a sensitive data store.

## 6. Building a simple redaction class for labeled values

For data where policy permits only logging fully redacted status, an explicit API is better than passing sensitive strings to a logger and hoping an appender rewrites them.

~~~java
public final class SensitiveValues {

    private SensitiveValues() {
    }

    public static String redactedEmail(String email) {
        return email == null ? "[ABSENT]" : "[REDACTED_EMAIL]";
    }

    public static String redactedPhone(String phone) {
        return phone == null ? "[ABSENT]" : "[REDACTED_PHONE]";
    }

    public static String redactedToken(String token) {
        return token == null ? "[ABSENT]" : "[REDACTED_SECRET]";
    }

    public static String redactedPaymentCard(String pan) {
        return pan == null ? "[ABSENT]" : "[REDACTED_PAN]";
    }
}
~~~

Example:

~~~java
log.info("event=order.validation.failed email={} reasonCode={}",
        SensitiveValues.redactedEmail(order.customerEmail()),
        "INVALID_EMAIL_FORMAT");
~~~

This design intentionally **retains no part of the email, token, or PAN**. Even distinguishing \`[ABSENT]\` from \`[REDACTED_EMAIL]\` can sometimes reveal whether a field was populated; if the mere presence of a sensitive field must be protected, use a single fixed marker or omit the field entirely.

### When partial masking is explicitly permitted

For less sensitive fields where policy allows showing the last two characters, implement a dedicated allowlisted helper:

~~~java
public final class ApprovedPartialMask {

    private ApprovedPartialMask() {
    }

    public static String lastTwoOnly(String value) {
        if (value == null) {
            return "[ABSENT]";
        }
        if (value.length() < 3) {
            return "[REDACTED]";
        }
        return "*".repeat(value.length() - 2)
                + value.substring(value.length() - 2);
    }
}
~~~

This example illustrates **partial masking mechanics**, not a recommendation for card numbers, bank accounts, emails, or national IDs. Keeping the last two characters can still constitute PII. The logic counts Java UTF-16 code units; do not use it as-is on Unicode strings with combining characters or free text requiring grapheme handling.

In Spring Batch, the most reliable security choice is usually logging **technical IDs, statuses, and reason codes**, avoiding masked values unless an investigation need proves otherwise.

## 7. HMAC for linkable reference codes across logs

When you need to correlate failures belonging to **the same customer or source key** without logging the raw value, use **HMAC** with a secret key. Compared to unkeyed SHA-256(email), HMAC resists lookup-table attacks as long as the secret is protected.

Java 17+ example:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.Arrays;
import java.util.HexFormat;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class LogReferenceGenerator {

    private final byte[] secretKey;

    public LogReferenceGenerator(byte[] secretKey) {
        if (secretKey == null || secretKey.length < 32) {
            throw new IllegalArgumentException(
                    "HMAC key must be provisioned securely");
        }
        this.secretKey = secretKey.clone();
    }

    public String refForCustomer(String customerId) {
        if (customerId == null || customerId.isBlank()) {
            return "customer_absent";
        }

        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secretKey, "HmacSHA256"));

            byte[] digest = mac.doFinal(
                    ("customer:" + customerId)
                            .getBytes(StandardCharsets.UTF_8));

            // Truncate to 16 bytes (128 bits) as a correlation code.
            byte[] shortened = Arrays.copyOf(digest, 16);
            return "c_" + HexFormat.of().formatHex(shortened);
        } catch (GeneralSecurityException e) {
            throw new IllegalStateException(
                    "Cannot calculate log reference", e);
        }
    }
}
~~~

The example assumes the secret key is **provisioned via a secret manager or equivalent secure mechanism**; never hardcode it in source code, job parameters, logs, or committed config files. In practice, define key versioning/rotation policies, usage permissions, and reference scrubbing aligned with retention windows.

\`Mac\` is instantiated per call to avoid sharing a non-thread-safe instance across parallel chunks. The \`customer:\` prefix separates namespaces when the same HMAC key is used across multiple identifier types.

**HMAC does not automatically make data non-personal.** Anyone authorized to compute HMACs for arbitrary customerIds can still look them up; a stable reference also enables linking events together. Restrict purpose, access rights, and reference retention. If per-customer correlation is unnecessary, omit \`customerRef\` completely.

### Do not use unkeyed hashes for predictable values

Phone numbers, emails, and structured customer IDs often have predictable value spaces. Writing:

~~~java
// Do not treat this as strong anonymization:
sha256(email);
~~~

does not sufficiently defend against attackers able to dictionary-test candidate values. HMAC with a properly managed secret reduces this risk, though data policy evaluation is still required.

## 8. Masking data in ItemProcessor and ItemWriter

Suppose an order-import Step validates amounts and calls a pricing service. The Processor should throw a **safe exception** carrying a reason code rather than embedding the full sensitive record in the message.

~~~java
public enum BatchErrorCode {
    INVALID_AMOUNT,
    INVALID_CURRENCY,
    EXTERNAL_SERVICE_TIMEOUT,
    OUTPUT_WRITE_FAILED,
    UNKNOWN_INPUT_FORMAT
}

public class SafeBatchItemException extends RuntimeException {

    private final BatchErrorCode code;

    public SafeBatchItemException(BatchErrorCode code) {
        super(code.name());
        this.code = code;
    }

    public BatchErrorCode code() {
        return code;
    }
}
~~~

Processor:

~~~java
import java.math.BigDecimal;
import org.springframework.batch.item.ItemProcessor;

public class ValidatingOrderProcessor
        implements ItemProcessor<RawOrder, RawOrder> {

    @Override
    public RawOrder process(RawOrder order) {
        if (order.amount() == null
                || order.amount().compareTo(BigDecimal.ZERO) <= 0) {
            throw new SafeBatchItemException(
                    BatchErrorCode.INVALID_AMOUNT);
        }
        return order;
    }
}
~~~

Do not write:

~~~java
throw new IllegalArgumentException(
        "Invalid order: " + order); // record.toString() contains PII/secrets
~~~

Because exception messages may be logged by the framework, listeners, or surfaced in Batch metadata, placing raw data in the message creates risk even if the app never explicitly calls \`log.error\`.

In the writer, log only aggregate fields:

~~~java
log.info(
        "event=orders.chunk.written jobExecutionId={} itemCount={}",
        executionId,
        chunk.size());
~~~

Never log the entire \`chunk\`, SQL bind values, or request bodies. If the writer handles multiple records and fails, use an **approved item reference** and error category instead of printing the full payload for "easy debugging."

### Raw data still needs handling for remediation

Masking logs does not mean deleting information needed to fix errors from every system. If the batch must retain failing records for operations to reprocess, use a separate **quarantine store** with encryption, RBAC, retention, access auditing, and reference keys. Logs contain only technical IDs or safe references to open records through an authorized UI.

## 9. Writing a SkipListener that never leaks items or raw lines

In a fault-tolerant Step, \`SkipListener<T, S>\` receives failure details for auditing. This is one of the easiest places to accidentally log sensitive data.

Example:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.SkipListener;
import org.springframework.batch.item.file.FlatFileParseException;

public class SecureOrderSkipListener
        implements SkipListener<RawOrder, RawOrder> {

    private static final Logger log =
            LoggerFactory.getLogger(SecureOrderSkipListener.class);

    private final LogReferenceGenerator referenceGenerator;

    public SecureOrderSkipListener(
            LogReferenceGenerator referenceGenerator) {
        this.referenceGenerator = referenceGenerator;
    }

    @Override
    public void onSkipInRead(Throwable error) {
        Integer lineNumber = error instanceof FlatFileParseException ex
                ? ex.getLineNumber()
                : null;

        log.warn(
                "event=batch.item.skipped phase=READ "
                + "reasonCode=UNKNOWN_INPUT_FORMAT lineNumber={}",
                lineNumber);
        // DO NOT log error.getMessage() or FlatFileParseException.getInput().
    }

    @Override
    public void onSkipInProcess(RawOrder item, Throwable error) {
        String reasonCode = error instanceof SafeBatchItemException safe
                ? safe.code().name()
                : "PROCESSING_ERROR";

        log.warn(
                "event=batch.item.skipped phase=PROCESS "
                + "recordRef={} reasonCode={}",
                referenceGenerator.refForCustomer(item.orderId()),
                reasonCode);
    }

    @Override
    public void onSkipInWrite(RawOrder item, Throwable error) {
        log.warn(
                "event=batch.item.skipped phase=WRITE "
                + "recordRef={} reasonCode=OUTPUT_WRITE_FAILED",
                referenceGenerator.refForCustomer(item.orderId()));
    }
}
~~~

In the example, \`refForCustomer\` is called with \`orderId\` solely to reuse reference generation; real projects should define a dedicated **\`refForOrder\`** method and separate HMAC namespace for order IDs. The log retains \`lineNumber\` when available, without raw CSV. Line numbers are metadata, yet when a file has few records or a public mapping to data exists, sensitivity should still be assessed.

Register the listener on a fault-tolerant Step:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<RawOrder, RawOrder>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(FlatFileParseException.class)
        .skip(SafeBatchItemException.class)
        .skipLimit(5)
        .listener(secureOrderSkipListener)
        .build();
~~~

Here \`reader\`, \`processor\`, \`writer\`, \`transactionManager\`, and \`jobRepository\` are existing beans. Actual exception names must match errors thrown by the reader/processor; skip policies should not be broadened to \`Exception.class\` just to get clean logs.

**SkipListener is not the final gate against leaks.** If the reader or JDBC/HTTP client already logged the payload before throwing, a safe listener cannot erase the earlier log entry. Protect from the reader/adapter and exception handling through to third-party loggers.

## 10. Safely attaching JobExecution ID with MDC

SLF4J **Mapped Diagnostic Context (MDC)** lets every log on the current thread include context like \`jobExecutionId\` and \`stepExecutionId\`. Attach only safe metadata; **never put emails, tokens, raw JobParameters, or payloads into MDC**.

Example Step listener:

~~~java
import org.slf4j.MDC;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;

public class SafeMdcStepListener
        implements StepExecutionListener {

    @Override
    public void beforeStep(StepExecution stepExecution) {
        MDC.put("jobExecutionId",
                String.valueOf(stepExecution.getJobExecutionId()));
        MDC.put("stepExecutionId",
                String.valueOf(stepExecution.getId()));
        MDC.put("stepName", stepExecution.getStepName());
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        try {
            // Final Step logs here if needed.
        } finally {
            MDC.remove("stepName");
            MDC.remove("stepExecutionId");
            MDC.remove("jobExecutionId");
        }
        return null;
    }
}
~~~

This snippet illustrates a Step running sequentially on a single thread. With thread pools or partitions, set **MDC at the worker entry point** or copy context via a TaskDecorator and restore the previous context in \`finally\`. Setting MDC only on the Job-controlling thread does not automatically propagate it to worker threads.

MDC can linger when threads are reused, so cleanup is mandatory. Avoid calling \`MDC.clear()\` indiscriminately if a tracing library shares MDC for \`traceId\`/\`spanId\`; remove only keys owned by the listener or restore the prior snapshot.

### Never log raw JobParameters

Spring Batch lets JobParameters contain parameters such as \`inputFile\`, \`batchId\`, \`tenantId\`, or \`accessToken\`. Never do this:

~~~java
log.info("Starting with parameters={}",
        jobExecution.getJobParameters());
~~~

Instead, build an explicit allowlist:

~~~java
log.info(
        "event=batch.started jobExecutionId={} jobName={} "
        + "inputType={} sourceVersion={}",
        jobExecution.getId(),
        jobExecution.getJobInstance().getJobName(),
        "CSV",
        safeSourceVersion);
~~~

If a file path contains usernames, customer codes, or business information, **never log the full path**. Log source type, file extension, or an opaque fileId per contract. Parameters that are secrets should not be passed as regular JobParameters where they may be persisted in JobRepository; use a secret manager/credential provider at the infrastructure layer.

## 11. Configuring Logback without losing safe context

Once code sets approved MDC keys, configure the backend to emit those fields. Example \`logback-spring.xml\` with a text pattern:

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>
                %d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX}
                %-5level
                [jobExecutionId=%X{jobExecutionId:-none}]
                [stepExecutionId=%X{stepExecutionId:-none}]
                [stepName=%X{stepName:-none}]
                %logger{36} - %msg%n
            </pattern>
        </encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

The pattern uses \`jobExecutionId\`, \`stepExecutionId\`, and \`stepName\` MDC keys, which are classified as relatively safe. **\`%msg\` can still contain sensitive data** if code or libraries emit raw messages. Therefore, Logback patterns preserve context rather than automatically redacting all data.

### Structured JSON logs

For log aggregation, structured JSON is cleaner than hand-concatenated strings:

~~~json
{
  "timestamp": "2026-11-16T09:00:00+07:00",
  "level": "WARN",
  "event": "batch.item.skipped",
  "jobExecutionId": "801",
  "stepExecutionId": "3401",
  "stepName": "importOrdersStep",
  "phase": "PROCESS",
  "recordRef": "c_74b9f2ce",
  "reasonCode": "INVALID_AMOUNT"
}
~~~

This is a target format, not the default output of every Spring Boot/Logback version. Projects can use Spring Boot structured logging or a compatible JSON encoder configured with a **field allowlist**. Do not enable "export all MDC" if the application also stores sensitive keys there.

### Regex-based masking in appenders is only an extra defense line

Some systems use filters or custom layouts to replace \`password=...\`, \`Bearer ...\`, or card-like strings with \`[REDACTED]\`. This is useful **defense in depth** for known patterns, but has limits:

- JSON escaping, line breaks, Unicode, alternate encodings, and renamed keys can evade patterns.
- Secrets can appear in exception stack traces, \`toString()\`, structured arguments, or MDC fields unseen by a regex acting only on \`%msg\`.
- Overly broad regexes can corrupt operational data or burn CPU under heavy log volume.
- Overly narrow regexes miss differently formatted tokens.
- Logs may already have been written to another appender/collector before the final filter runs.

Therefore, never treat regex configuration as an absolute guarantee that logs contain no sensitive data. **Preventing at the source** via allowlists and safe exceptions remains primary.

## 12. Exceptions, stack traces, and library error messages

In batch jobs, exceptions can carry sensitive data in several ways:

~~~text
FlatFileParseException: failed to parse line:
  O101,linh@example.test,4111111111111111

HttpClientErrorException:
  401 Unauthorized: {"token":"secret-..."}

SQL exception:
  duplicate key value violates unique constraint ...
  Detail: Key (email)=(linh@example.test) already exists.
~~~

When calling:

~~~java
log.error("Batch operation failed", exception);
~~~

the logger usually prints the exception's message and stack trace; **the exception chain can contain payloads**. Avoid logging raw throwables at untrusted data boundaries unless you know the exception message is safe.

One approach:

~~~java
public enum FailureCategory {
    INPUT_PARSE_ERROR,
    VALIDATION_ERROR,
    EXTERNAL_TIMEOUT,
    OUTPUT_CONSTRAINT_ERROR,
    UNKNOWN_FAILURE
}

public static FailureCategory classify(Throwable error) {
    if (error instanceof org.springframework.batch.item.file
            .FlatFileParseException) {
        return FailureCategory.INPUT_PARSE_ERROR;
    }
    if (error instanceof SafeBatchItemException) {
        return FailureCategory.VALIDATION_ERROR;
    }
    return FailureCategory.UNKNOWN_FAILURE;
}
~~~

Then log:

~~~java
log.error(
        "event=batch.operation.failed failureCategory={} "
        + "jobExecutionId={}",
        classify(error),
        jobExecutionId);
~~~

This is a minimal classification example; production should maintain a reviewed exception mapping across adapters, databases, and external services. **Never use \`error.getMessage()\` or \`error.toString()\` as a safe reason code**.

### What if stack traces are needed for debugging?

Stack traces are helpful yet not always safe. Design a **diagnostic channel** with restricted access, error-source redaction, and shorter retention—or generate an incident ID linking to protected error records in a separate store. When enabling stack traces, test the entire exception chain with synthetic sensitive data to see what the backend actually emits.

Never catch every exception and stay silent: the job must still reflect \`FAILED\`, \`skip\`, or \`retry\` per Spring Batch policy. **Masking data in logs is completely different from hiding operational failures**.

## 13. SQL, HTTP, and third-party libraries

Even when application loggers are safe, libraries can still emit raw values when debug/tracing is turned on.

### JDBC/ORM

Consider:

- Logged SQL statements may contain literals instead of parameter placeholders.
- SQL bind-value logging from JDBC proxies, Hibernate, or drivers may print emails, IDs, and amounts.
- Database error messages may contain values violating constraints.
- Query monitoring or slow query logs on the **database server** are a separate channel unaffected by the application's Logback filters.

Never enable bind-value loggers in production when data is sensitive. When analyzing queries, prefer query templates, execution plans, and timings without bind values; use test environments with synthetic data for deep debugging.

### HTTP and SDKs

Never log full HTTP client requests/responses when \`Authorization\`, cookies, PII, or transaction bodies are present. For request correlation, keep only the endpoint **template** and HTTP status:

~~~text
event=api.failed
dependency=customer-risk
method=POST
route=/risk/evaluate
status=503
durationMs=1260
jobExecutionId=801
~~~

Never log real URLs containing query parameters with emails/tokens. If the HTTP client supports a request/response logging interceptor, configure **header and body redaction** on that interceptor and test redirect/error paths so unusual branches do not slip through.

### Tracing and metrics

Traces can record \`span attributes\`, \`baggage\`, HTTP URLs, SQL statements, and exception messages. Metrics can carry labels like customerId or fileName. Apply the same allowlist principle as logs:

- Keep emails, tokens, and PANs out of span attributes and metric labels.
- Use \`jobName\`, \`stepName\`, \`status\`, and \`failureCategory\` in metrics when cardinality is controlled.
- Put \`jobExecutionId\` in logs/traces or audit queries by ID, not as a default Prometheus label due to **high cardinality**.
- When exporting traces via a collector, configure redaction/scrubbing as an additional defense line.

## 14. Error files, quarantine, and ExecutionContext

Some jobs produce a **reject file** containing unparseable lines or failing records:

~~~text
input.csv
    |
    +--> valid rows --> writer --> output
    |
    +--> invalid rows --> reject file / quarantine store
~~~

A reject file is not a log and may need original data for recovery. If retained:

1. Use separate storage with encryption at rest and narrow access controls.
2. Never embed emails, phone numbers, or secret codes in filenames.
3. Never write raw lines into logs merely to report the reject file path.
4. Attach batchId, source version, reason code, and opaque reference per record.
5. Define retention, deletion procedures, access auditing, and export permissions.
6. Never leave error files in temp directories or broadly accessible volumes.

Spring Batch's **ExecutionContext** stores state for restarts and is typically persisted in JobRepository. Never use ExecutionContext to store access tokens, card numbers, or raw items just "for debugging data"; these fields can outlive business data and bypass Logback masking.

Likewise, \`ExitStatus.exitDescription\`, listener-generated messages, and exceptions retained in \`JobExecution\` can appear in admin UIs. Prevent sensitive data from entering exception messages at the source.

## 15. Protecting thread pools, partitions, and remote workers

When a Step uses a \`TaskExecutor\`, parallel flows, partitioning, or remote chunking, logging context can cross threads or processes.

~~~text
JobExecution 801
   |
   +-- main thread: MDC(jobExecutionId=801)
   |
   +-- worker thread A
   |      MDC must be set for the corresponding execution/partition
   |
   +-- worker thread B
   |      must not retain IDs/fields from the previous task
   |
   +-- remote worker
          receives safe correlation metadata via messages
~~~

A \`TaskDecorator\` can copy MDC from the submitting thread and restore the previous snapshot in \`finally\`; however, **never copy all MDC if the source already holds PII**, as that replicates it across tasks.

For messages to remote workers, use an envelope containing only:

~~~json
{
  "headers": {
    "jobExecutionId": "801",
    "stepExecutionId": "3401",
    "correlationId": "req-27",
    "partitionId": "part-02"
  },
  "payload": {
    "reference": "object-key-authorized-for-worker"
  }
}
~~~

If the payload holds real data, that is a separate business channel with its own protection requirements; the example only illustrates **never placing sensitive data in logging metadata**. When a remote worker receives IDs, verify their association with the assigned job rather than blindly trusting headers from untrusted sources.

Reused thread pools can cause two bugs simultaneously: job A's logs carry \`jobExecutionId\` B, or sensitive MDC from a prior task leaks over. Context cleanup/restoration is therefore a security measure, not just logging convenience.

## 16. Testing masking and leak prevention with synthetic data

Good masking requires testing **where data leaves the application**, not just asserting \`maskEmail()\` returns an expected string. Use synthetic sentinel strings, for example:

~~~text
email:       private.user@example.test
phone:       0901234567
token:       test_secret_DO_NOT_LOG_7f2a
paymentPan:  4111111111111111  (synthetic test data only)
~~~

Tests must never contain production credentials or real customer data. Sentinels can be chosen for exact searching in log output.

### Unit test for redaction and HMAC

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

class SafeLoggingValuesTest {

    @Test
    void redactsEmailWithoutLeakingLocalPartOrDomain() {
        assertEquals("[REDACTED_EMAIL]",
                SensitiveValues.redactedEmail(
                        "private.user@example.test"));
    }

    @Test
    void hmacReferenceIsDeterministicButDoesNotReturnRawId() {
        byte[] testKey =
                "this-is-a-synthetic-test-key-32plus-bytes"
                        .getBytes(StandardCharsets.UTF_8);

        LogReferenceGenerator generator =
                new LogReferenceGenerator(testKey);

        String first = generator.refForCustomer("customer-test-001");
        String second = generator.refForCustomer("customer-test-001");
        String other = generator.refForCustomer("customer-test-002");

        assertEquals(first, second);
        assertNotEquals(first, other);
        assertNotEquals("customer-test-001", first);
    }
}
~~~

This test verifies determinism and that the original value is not returned—**it does not prove HMAC alone satisfies privacy policy**. The secret in the example is a synthetic string for unit testing only; production must use secure key provisioning.

### Capturing logs from Logback

To inspect what logs actually contain, use Logback's \`ListAppender<ILoggingEvent>\` in tests:

~~~java
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import org.slf4j.LoggerFactory;

Logger logger = (Logger) LoggerFactory.getLogger(
        ValidatingOrderProcessor.class);

ListAppender<ILoggingEvent> appender = new ListAppender<>();
appender.start();
logger.addAppender(appender);

try {
    // Run processor/Step with synthetic sentinels.
    // Then inspect all formatted messages and MDC
    // of every captured logging event.
} finally {
    logger.detachAppender(appender);
    appender.stop();
}
~~~

This is a **test skeleton**; add Step execution and project-specific assertions. If the backend uses an async appender or JSON encoder, inspect **encoded bytes or a mock output collector** to catch fields outside \`formattedMessage\` (MDC, structured arguments, throwables, and markers).

A "logs contain no token" test must inspect all of:

- Formatted message.
- Encoded throwable message and stack trace.
- MDC map.
- Structured JSON fields.
- Output of HTTP/JDBC logging adapters if enabled.
- Failure/ExitStatus metadata if admin UIs display them as well.

### Sentinel assertion example

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

String logText = capturedEncodedLog;

assertFalse(logText.contains("private.user@example.test"));
assertFalse(logText.contains("0901234567"));
assertFalse(logText.contains("test_secret_DO_NOT_LOG_7f2a"));
assertFalse(logText.contains("4111111111111111"));

assertTrue(logText.contains("jobExecutionId"));
assertTrue(logText.contains("reasonCode"));
~~~

\`capturedEncodedLog\` is an illustrative variable holding all encoded test output, not a Spring Batch API. Sentinel checks must preserve detection accuracy: if data can be escaped, encoded, or split, test the actual output formats supported by the logger.

## 17. Test matrix across the Spring Batch flow

| Scenario | Synthetic input | What to verify |
|---|---|---|
| Valid item | Email, phone, token in DTO | Progress logs contain no raw fields |
| Validation error | Negative amount, DTO with email | Exception message has only reason code |
| Read skip | CSV numeric error + column with PII | Never log raw line or \`getInput()\` |
| Process skip | \`SafeBatchItemException\` | Log reason code and safe reference |
| Write skip | Unique constraint error containing key | Never emit raw exception detail |
| API retry | HTTP client sees Authorization header | Never log Authorization or body |
| JobParameters | inputFile with username, misconfigured secret | Never dump raw parameters |
| MDC | Two executions run sequentially on same thread | IDs do not bleed into next execution |
| Parallel Step | Two worker threads and partitions | Context matches each execution; carries no sensitive fields |
| Remote worker | Message with correlation metadata | Propagate only allowlisted keys |
| Job FAILED | Listener and backend emit stack traces | No PII in error chain |
| Restart | Same JobInstance, two JobExecutions | Traces match each attempt, no old payload logged |
| JDBC debug | Logging enabled in test env | Never emit sensitive bind values |
| HTTP adapter | 4xx/5xx with response body containing token | Never emit raw response in logs |
| JSON logging | Encoder with MDC and structured args | Emitted fields match allowlist |
| Quarantine | Failing record contains secret | Log has only safe reference; storage separately secured |
| Crash | afterJob/afterStep do not run | Do not rely on completion logs to infer outcome |

In particular, write a **job integration test** with \`spring-batch-test\`: run a small job via \`JobLauncherTestUtils\`, inject sentinels across reader, processor, writer, and skip errors, and capture real logs. Assert that JobExecution/StepExecution still reflect accurate status and read/skip/write counters while logs leak zero data.

Never judge masking solely by clean-looking local console output: production may use different appenders, exporters, or logger libraries.

## 18. Defense in depth across the log pipeline and operations

Even when application code enforces an allowlist, log aggregation infrastructure still needs policies:

~~~text
Spring Batch application
     |
     +-- Safe event + safe exception + safe MDC
     |
     v
Logging backend / appender
     |
     +-- Structured schema, extra filters
     v
Collector / forwarder
     |
     +-- Additional redaction, TLS, access policy
     v
Central log storage
     |
     +-- RBAC, access audit, retention, deletion workflow
     v
Alert / dashboard / incident workflow
~~~

Operational points to design clearly:

**Access control.** Batch operators may need status and reason codes without needing read access to all business data. Permissions for the log store, quarantine store, and JobRepository can differ.

**Retention.** Logs should be kept only as long as required for operations and regulations. Partially masked data is not automatically permitted to be retained indefinitely.

**Incident response.** If secrets/PII are discovered in logs: plug the leak source, identify downstream log receivers and data scope, handle secret rotation/revocation, restrict access, purge/scrub per authorized procedure, and record the incident. Changing source code alone does not delete already-shipped copies.

**Change control.** Whenever adding fields to DTOs, JobParameters, exceptions, HTTP/JDBC adapters, or changing encoders, check whether they could surface in logs/traces/metadata. This is part of ongoing change management, not a one-time deployment check.

**Debug limits.** Never enable \`TRACE\` logging across entire batches or HTTP bodies in production to troubleshoot an isolated error. If deep diagnostics are unavoidable, use a test environment, synthetic data, short timeboxes, and proper approval.

## 19. Common mistakes

**Logging whole objects then masking with regex.** \`toString()\`, JSON fields, throwables, and MDC can slip past filters. Use allowlists and safe events before calling the logger.

**Masking only the last digits and calling it completely safe.** Partial values can still identify individuals or violate policy. Prefer full redaction or omission.

**Using unkeyed SHA-256 on emails/phone numbers.** These values are easy to dictionary-guess. When correlation is needed, use HMAC with a protected secret and still evaluate re-identification risk.

**Logging raw exceptions on read skips.** \`FlatFileParseException\` can carry raw input and exception chains. Log line number, error category, and safe reference instead of payloads.

**Keeping secrets in JobParameters or ExecutionContext.** Values may be persisted in JobRepository, bypassing Logback masking. Use a secret manager instead of passing secrets through metadata.

**Putting emails or tokens in MDC.** MDC attaches to many consecutive logs; if cleanup is missed, it also leaks to subsequent tasks.

**Protecting only your own code.** JDBC, Hibernate, HTTP interceptors, SDKs, database slow query logs, and tracing exporters can have their own logs.

**Logging exception messages and treating them as reasonCodes.** Messages may contain library- or input-generated data. Use controlled enums/constants.

**Calling \`MDC.clear()\` indiscriminately.** This can wipe trace context from observability libraries. Restore snapshots or remove only app-owned keys.

**Assuming JSON logging is always safe.** Encoders may automatically include all MDC and structured arguments. Inspect emitted bytes/fields.

**Putting dynamic PII-bearing IDs into metric labels.** Creates high cardinality and replicates sensitive info. Use logs/traces/audits for detailed correlation.

**Testing only the happy path.** Parse errors, rollbacks, API timeouts, Job FAILED, retries, and restarts are often where the framework logs the most detail.

**Treating log redaction as a substitute for access control.** Logs with reduced sensitivity still require TLS, RBAC, auditing, and retention controls.

**Ignoring already-exposed logs.** Fixing the app only stops future leaks; an incident response workflow is required for logs already stored or forwarded.

## 20. Steps to implement log masking in a Spring Batch project

An implementation plan can be broken into these steps:

1. **Map data flows:** list readers, processors, writers, skip/retry/listeners, dependencies, and log sinks.
2. **Classify fields:** secrets, payment data, PII, business IDs, technical metadata, counters; define what is allowed to be logged.
3. **Define an event schema allowlist:** \`event\`, \`jobExecutionId\`, \`stepExecutionId\`, \`phase\`, \`reasonCode\`, and opaque references only when truly needed.
4. **Make exceptions safe:** translate application errors into payload-free reason codes; audit adapter messages and stack traces.
5. **Harden fault-tolerance hooks:** ensure \`SkipListener\`, retry logging, and item/Chunk listeners never dump raw inputs or objects.
6. **Standardize MDC and JSON encoders:** attach only approved metadata, clean up context afterward, and propagate context cleanly across threads and remote workers.
7. **Disable payload debug logging in production:** JDBC bind parameters, HTTP bodies/headers, and sensitive trace attributes.
8. **Separate quarantine stores from logs:** original data needed for recovery must live in a separately authorized store with its own retention.
9. **Test the full pipeline:** unit-test redaction/HMAC, capture encoded logs, and integration-test Jobs with sentinels on error paths.
10. **Secure log backends:** additional collector redaction, transport encryption, RBAC, auditing, and deletion/incident workflows.
11. **Embed into change lifecycle:** every new field/adapter/logger must be reviewed for leak risk.

The guiding principle is **keeping sensitive data out of logs from the start**, rather than expecting a downstream filter to catch and mask every variant. In Spring Batch, this matters even more because raw items, \`FlatFileParseException\`, JobParameters, ExecutionContext, retry/skip listeners, and library logs provide many opportunities to copy data. Applying allowlists, safe error codes, metadata-only MDC, and testing error paths alongside the log pipeline preserves investigation by job execution ID while minimizing information leakage risk.
