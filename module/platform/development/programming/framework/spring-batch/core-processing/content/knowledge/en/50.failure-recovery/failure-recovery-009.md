# Remote Service Timeouts in Spring Batch: Retry, Recovery, and Data Consistency

## 1. Context and Goal

A Spring Batch job may read data and write to a database reliably yet still fail when calling an external service. For example, an order-import job must call a customer service to enrich membership tier; the service slows down, drops connections, or fails to respond in time. Or a payment job calls a transfer API: the server accepts the request, yet the client times out before receiving the response. Both appear as a "remote service timeout," but **whether it is safe to retry differs completely**.

This is the **Remote service timeout** lesson in the *Failure recovery* group of the *Spring Batch Core Processing* module. The goal is to design a step that handles timeouts with bounds, avoids infinite retry loops, never drops critical data, and avoids accidentally executing external side effects multiple times.

After this lesson, you will be able to:

- Distinguish connect timeout, request/response timeout, business deadlines, and HTTP errors.
- Separate transient errors from non-self-healing errors to choose retry, skip, or fail.
- Configure timeouts on HTTP clients and retry/backoff in fault-tolerant chunk steps.
- Calculate total retry time to choose thresholds aligned with chunks, transactions, and SLAs.
- Understand why timing out on an **HTTP POST** can leave an *indeterminate* outcome despite a client exception.
- Design idempotency keys, status lookups, quarantine, reconciliation, and safe restarts.
- Test using simulated errors, controlled timeouts, and assertions on `JobExecution`/`StepExecution`.
- Monitor timeout counts, service latency, retry durations, and executions requiring manual intervention.

The main code examples use **Java 17+, Spring Boot 3.x, Spring Batch 5.2.x**. Before using with Spring Batch 6.x, adapt APIs and packages per the documentation for your target version.

---

## 2. Where Do Remote Services Sit in the Pipeline?

A batch step can invoke HTTP inside a reader, processor, or writer:

```text
                  Spring Batch Job
                         │
                         ▼
                  Chunk-oriented Step
                         │
        ┌────────────────┼──────────────────┐
        ▼                ▼                  ▼
    ItemReader      ItemProcessor       ItemWriter
   fetches data     enriches/checks    writes results
        │                │                  │
        │                ▼                  ▼
        │         Remote service A     Remote service B
        │         HTTP GET/profile     HTTP POST/payment
        │                │                  │
        └────────────────┴──────────────────┘
                         │
                  JobRepository
             checkpoints and metadata
```

Timeouts at each stage have different impacts:

| Remote Call Location | Example | Risk on Timeout |
|---|---|---|
| `ItemReader` | GET a page of data from an API | Uncertain whether the reader already advanced to a new page; custom readers must guarantee retrying the same data |
| `ItemProcessor` | GET customer info | Safer to retry reads, provided GET has no side effects and inputs match |
| `ItemProcessor` | POST to update another system | Side effect may have occurred before timeout; retries can create duplicate records |
| `ItemWriter` | POST a batch of invoices | Some items may be accepted while others fail; local DB rollback does not roll back the remote service |
| `Tasklet` | Submit a large job request and wait | No chunk-style item-level retry/skip by default; must be controlled at tasklet/orchestrator level |

**In this lesson, "remote service" refers to an HTTP service called by the batch during processing.** Do not confuse it with Spring Batch's **Remote Chunking** feature, where managers and workers exchange chunks over messaging. Remote Chunking has distinct protocols, transactions, and failure mechanics, even though both require timeouts and idempotency.

### Two Questions to Answer Before Implementing

1. **If a request times out, do we know the server has not performed the action?** Pure-read GETs are usually safe to retry; money-transfer POSTs usually are not.
2. **If retries exhaust, must the whole job fail (`FAILED`) or may the item be skipped/quarantined (`SKIPPED`)?** This is a business decision about data completeness, not merely a technical flag.

---

## 3. Distinguishing Timeout Types and Errors

### 3.1. Connect Timeout

The client fails to establish a TCP/TLS connection within the time limit. With Java's `HttpClient`, `HttpClient.Builder.connectTimeout(Duration)` applies when opening a new connection. Reused pooled connections may skip this connect step.

```java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .build();
```

If a connect timeout occurs before sending the request to the target server, there is a stronger basis to retry, though behind proxies/load balancers you must still understand the request path. Never assume every `IOException` is a connect timeout.

### 3.2. Request/Response Timeout

The client managed to send the request but did not receive the response in time. In Java 17:

```java
HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(5))
        .GET()
        .build();
```

`HttpRequest.timeout(...)` caps how long to wait for the request/response via this HTTP client. On expiration, `HttpClient.send(...)` can throw `HttpTimeoutException`; `HttpConnectTimeoutException` is a specialized subtype for connection establishment.

**What you cannot conclude from a response timeout:** that the server definitely did nothing. When the client misses a response, reality could be:

- The server never received the request.
- The server received it but has not started.
- The server is still processing it.
- The server committed the side effect, and the response was lost.
- A proxy returned an error even though the backend succeeded.

For state-mutating HTTP POSTs, the latter cases can cause **duplicate transactions** if the client retries blindly.

### 3.3. Overall Deadline vs. Per-Call Timeout

Distinguish three limits:

- **Connection timeout:** max wait to establish a connection.
- **Per-request timeout:** max wait for one remote call.
- **Overall processing deadline:** max budget for the entire item attempt, including retries and backoffs.

Example with 5s per-request timeout, up to 3 attempts, and backoffs of 0.5s then 1s:

```text
Attempt 1: up to 5.0s
Backoff 1:       0.5s
Attempt 2: up to 5.0s
Backoff 2:       1.0s
Attempt 3: up to 5.0s
------------------------
Nearest total:  16.5s + overhead
```

This is an **illustrative ceiling** if every attempt times out; connection/proxy/DNS behavior and other timeouts also affect wall-clock time. In a 100-item chunk, if each item hits this, the step can hold a transaction open for many minutes. Choose overall deadlines according to both job SLAs and remote service resilience.

### 3.4. HTTP Statuses vs. Transport Timeouts

| Signal | Typical Meaning | Starting Action |
|---|---|---|
| `HttpConnectTimeoutException` | Could not connect within limit | Bounded retry if operation is safe |
| `HttpTimeoutException` | Response did not arrive in time | Outcome may be unknown; distinguish GET vs. POST |
| Connection reset / EOF | Connection dropped mid-transfer | Check whether operation has side effects |
| HTTP 408 | Request timeout from HTTP server/proxy | Usually a candidate for bounded retry |
| HTTP 429 | Rate limited | Backoff, honor `Retry-After` if present |
| HTTP 502/503/504 | Transient gateway/service error | Bounded retry or circuit breaker |
| HTTP 500 | Internal server error | May be transient, yet side effects could have happened |
| HTTP 400/422 | Invalid request/schema/business validation | Usually fail/quarantine; do not retry fruitlessly |
| HTTP 401/403 | Authentication/authorization failure | Stop and fix config/credentials; do not retry endlessly |
| HTTP 404 | Resource not found | Follow contract: fail, wait for consistency, or skip if allowed |
| HTTP 409 | Conflict | Check status/idempotency; no single universal retry rule |
| HTTP 202 | Accepted for async processing | Poll status by correlation ID; do not treat as finished immediately |

This table is a starting point. The concrete contract of the remote API dictates which exceptions are retryable and whether retrying is safe.

---

## 4. Choosing a Recovery Policy Before Writing Code

A simple decision tree:

```text
Remote call fails or times out
           │
           ▼
Read-only / idempotent operation?
   ├── Yes ─► Transient error?
   │             ├── Yes ─► Retry + backoff + limit
   │             └── No  ─► Fail or contract-allowed skip
   │
   └── No / uncertain
                 │
                 ▼
       Has idempotency key and
       status lookup API?
                 │
          ├── Yes ─► Reconcile outcome → controlled retry
          └── No  ─► Stop/mark UNKNOWN for
                       investigation or compensation
```

### Outcomes After Exhausting Retries

- **FAILED:** mandatory data could not be processed. Stop step/job and preserve checkpoints to restart once the dependency recovers.
- **SKIPPED:** business permits dropping some failed items and accepting partial output. Requires audit/quarantine to track which items were dropped.
- **QUARANTINED:** isolate failed records into a remediation store with cause/correlation keys and continue if the contract permits.
- **PENDING_CONFIRMATION:** the request may have created a side effect; look up the outcome from the remote API before proceeding.
- **STOPPED:** a controlled stop was requested, distinct from an exception failure.
- **RETRIED_LATER:** requeue to a later queue/job after cooldown, preserving the business key to prevent duplicates.

Never choose `skip` just to make a job show `COMPLETED`. If a 1,000-record payment batch drops 3 timed-out transactions with unknown outcomes, completed status does not mean payment obligations were fulfilled.

---

## 5. End-to-End Example: Customer GET Service from ItemProcessor

### 5.1. Requirements

The job reads payments from input, calls a customer service via **HTTP GET** to retrieve membership tier, and writes enriched data.

Example assumptions:

- GET `/customers/{customerId}` is a read operation with no side effects.
- The service returns JSON such as `{"tier":"GOLD"}`.
- `408`, `429`, and `5xx` statuses are transient errors.
- `401/403/404` and malformed JSON schemas do not self-heal within the call.
- Connection timeout 2 seconds, request timeout 5 seconds.
- Spring Batch retries up to three attempts for transient errors, with backoff.
- On exhausted retries, the step transitions to **FAILED**; do not drop transactions without another business decision.

This example uses Java's `java.net.http.HttpClient` rather than relying on third-party client timeout APIs. With Spring `RestClient`, WebClient, Feign, or Apache HttpClient, timeout/idempotency classification principles stay the same while configuration APIs differ.

### 5.2. Dependencies

Gradle with Spring Boot dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    implementation 'org.springframework.boot:spring-boot-starter-json'

    runtimeOnly 'com.h2database:h2'  // example for local JobRepository

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
}
```

`spring-batch-core` relies on Spring Retry in the 5.x line. If a project manages dependencies without Boot starters, verify Spring Retry is present at a version compatible with Spring Batch.

### 5.3. Intentional Models and Exceptions

Placed in package `com.example.batch.remote`:

```java
package com.example.batch.remote;

import java.math.BigDecimal;

public final class RemoteModels {
    private RemoteModels() {}

    public record Payment(
            long id, long customerId, BigDecimal amount) {}

    public record EnrichedPayment(
            long id, long customerId,
            BigDecimal amount, String customerTier) {}

    public record CustomerResponse(String tier) {}

    public static class TransientRemoteException
            extends RuntimeException {
        public TransientRemoteException(String message) {
            super(message);
        }

        public TransientRemoteException(
                String message, Throwable cause) {
            super(message, cause);
        }
    }

    public static class PermanentRemoteException
            extends RuntimeException {
        public PermanentRemoteException(String message) {
            super(message);
        }

        public PermanentRemoteException(
                String message, Throwable cause) {
            super(message, cause);
        }
    }

    public static class RemoteCallInterruptedException
            extends RuntimeException {
        public RemoteCallInterruptedException(
                String message, Throwable cause) {
            super(message, cause);
        }
    }
}
```

**Why custom exceptions?** Configuring retry on `RuntimeException.class` or `Exception.class` can repeatedly retry authentication failures, JSON bugs, or processor bugs. Classified exceptions keep batch policies aligned with error semantics.

### 5.4. HTTP Client with Timeout

```java
package com.example.batch.remote;

import java.net.http.HttpClient;
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class RemoteHttpConfig {

    @Bean
    HttpClient customerHttpClient() {
        return HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(2))
                .build();
    }
}
```

Sharing a single client allows connection reuse. Java's `HttpClient` is designed to be reused across requests; do not create a new client per item. If mTLS, proxies, auth tokens, or pool tuning are needed, configure them at the client layer.

### 5.5. Processor Translating Remote Errors into Appropriate Exceptions

```java
package com.example.batch.remote;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.batch.item.ItemProcessor;

import com.example.batch.remote.RemoteModels.Payment;
import com.example.batch.remote.RemoteModels.EnrichedPayment;
import com.example.batch.remote.RemoteModels.CustomerResponse;
import com.example.batch.remote.RemoteModels.TransientRemoteException;
import com.example.batch.remote.RemoteModels.PermanentRemoteException;
import com.example.batch.remote.RemoteModels.RemoteCallInterruptedException;

public final class CustomerEnrichmentProcessor
        implements ItemProcessor<Payment, EnrichedPayment> {

    private final HttpClient http;
    private final ObjectMapper json;
    private final URI baseUri;

    public CustomerEnrichmentProcessor(
            HttpClient http, ObjectMapper json, URI baseUri) {
        this.http = http;
        this.json = json;
        this.baseUri = baseUri;

        // URI must end with "/" so resolve(customerId)
        // attaches cleanly to the /api/customers/ path.
        if (!baseUri.toString().endsWith("/")) {
            throw new IllegalArgumentException(
                    "customer base URI must end with /");
        }
    }

    @Override
    public EnrichedPayment process(Payment payment) {
        URI uri = baseUri.resolve(
                Long.toString(payment.customerId()));

        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(5))
                .header("Accept", "application/json")
                .GET()
                .build();

        try {
            HttpResponse<String> response = http.send(
                    request,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));

            int status = response.statusCode();

            if (status == 200) {
                CustomerResponse customer;
                try {
                    customer = json.readValue(
                            response.body(), CustomerResponse.class);
                } catch (JsonProcessingException invalidBody) {
                    throw new PermanentRemoteException(
                            "Invalid customer JSON: id="
                                    + payment.customerId(),
                            invalidBody);
                }

                if (customer.tier() == null
                        || customer.tier().isBlank()) {
                    throw new PermanentRemoteException(
                            "Missing tier: customerId="
                                    + payment.customerId());
                }

                return new EnrichedPayment(
                        payment.id(),
                        payment.customerId(),
                        payment.amount(),
                        customer.tier());
            }

            if (status == 408 || status == 429
                    || (status >= 500 && status <= 599)) {
                throw new TransientRemoteException(
                        "Temporary customer-service HTTP " + status);
            }

            throw new PermanentRemoteException(
                    "Non-retryable customer-service HTTP " + status);

        } catch (HttpTimeoutException timeout) {
            throw new TransientRemoteException(
                    "Customer-service timeout: customerId="
                            + payment.customerId(), timeout);

        } catch (IOException transportError) {
            throw new TransientRemoteException(
                    "Customer-service I/O failure: customerId="
                            + payment.customerId(), transportError);

        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new RemoteCallInterruptedException(
                    "Customer-service call interrupted", interrupted);
        }
    }
}
```

Key design choices:

1. `HttpTimeoutException` is caught before `IOException` because timeout is a subclass of `IOException`.
2. `InterruptedException` restores the interrupt flag via `Thread.currentThread().interrupt()` and is **not** classified as retryable under this example's default policy. This lets processing honor stop/cancellation signals.
3. Malformed JSON or missing business fields map to `PermanentRemoteException`, avoiding pointless retries.
4. `408/429/5xx` are treated as transient **in this GET example**. For other APIs, verify the contract and adjust the classifier.
5. For readability, this snippet groups all non-timeout `IOException`s as transient. Production code should separate SSL certificate/config failures, permanent DNS errors, or TLS auth errors (non-retryable) from transient network I/O errors.
6. Do not log full response bodies or tokens on error; metadata like `customerId`, HTTP status, and correlation ID suffices for diagnostics while limiting data exposure.
7. URIs are constructed from numeric IDs, never arbitrary paths read from input files targeting arbitrary hosts. In real APIs, protect service base URLs and credentials.

**Remember:** this example performs a read-only GET. For money-moving POSTs, never copy this retry setup verbatim without idempotency and outcome verification.

### 5.6. Processor Bean and Fault-Tolerant Step

```java
package com.example.batch.remote;

import java.net.URI;
import java.net.http.HttpClient;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.retry.backoff.ExponentialBackOffPolicy;
import org.springframework.transaction.PlatformTransactionManager;

import com.example.batch.remote.RemoteModels.Payment;
import com.example.batch.remote.RemoteModels.EnrichedPayment;
import com.example.batch.remote.RemoteModels.TransientRemoteException;

@Configuration(proxyBeanMethods = false)
public class EnrichmentStepConfig {

    @Bean
    CustomerEnrichmentProcessor customerEnrichmentProcessor(
            HttpClient customerHttpClient,
            ObjectMapper mapper,
            @Value("${remote.customer.base-url}") String baseUrl) {
        return new CustomerEnrichmentProcessor(
                customerHttpClient, mapper, URI.create(baseUrl));
    }

    @Bean
    ExponentialBackOffPolicy remoteBackOffPolicy() {
        ExponentialBackOffPolicy policy =
                new ExponentialBackOffPolicy();
        policy.setInitialInterval(500L);
        policy.setMultiplier(2.0);
        policy.setMaxInterval(2_000L);
        return policy;
    }

    @Bean
    Step enrichmentStep(
            JobRepository repository,
            PlatformTransactionManager transactionManager,
            ItemReader<Payment> paymentReader,
            CustomerEnrichmentProcessor customerEnrichmentProcessor,
            ItemWriter<EnrichedPayment> paymentWriter,
            ExponentialBackOffPolicy remoteBackOffPolicy) {

        return new StepBuilder("enrichmentStep", repository)
                .<Payment, EnrichedPayment>chunk(50, transactionManager)
                .reader(paymentReader)
                .processor(customerEnrichmentProcessor)
                .writer(paymentWriter)
                .faultTolerant()
                .retry(TransientRemoteException.class)
                .retryLimit(3)
                .backOffPolicy(remoteBackOffPolicy)
                .build();
    }
}
```

Configuration in `application.yml`:

```yaml
remote:
  customer:
    base-url: "https://customers.internal.example/api/customers/"

spring:
  batch:
    job:
      enabled: false
```

The hostname is illustrative. Your project supplies `paymentReader`, `paymentWriter`, and a `Job` containing `enrichmentStep`; the example focuses on the HTTP client, processor, and retry policy.

**Policy semantics:**

- `.faultTolerant()` enables exception-based retry/skip in the chunk step.
- `.retry(TransientRemoteException.class)` permits retrying only errors classified as transient.
- `.retryLimit(3)` in Spring Batch 5.2 caps **total attempts at three including the initial call** per item: at most two additional retries.
- `.backOffPolicy(...)` avoids immediate hammering, increasing delay between attempts up to a cap.
- Without `.skip(...)`, exhausting retries fails the step per standard fault-tolerance rules.
- `RemoteCallInterruptedException` and `PermanentRemoteException` are excluded from retry, preventing endless re-attempts.

In practice, coordinate with transaction timeouts and SLAs. For example, with chunk size 50 where each item could spend 16.5 seconds during an outage, total chunk time grows huge, holding transactions/DB resources and delaying checkpoints.

### 5.7. Why Not Put Retries at All Three Layers?

A common design mistake:

```text
HTTP client auto retry:      3 attempts
Spring RetryTemplate:        3 attempts
Spring Batch faultTolerant:  3 attempts
------------------------------------------------
A single item can trigger up to 27 remote calls
```

Total calls represent a worst-case if all retry layers nest completely, illustrating **retry amplification**. Within a single flow, assign primary retry responsibility in one place and explicitly bound total request counts, elapsed budgets, circuit breakers, and concurrency.

If your organization's HTTP client already auto-retries 503s, factor those retries into Spring Batch's overall budget. Never let independent retry policies multiply unchecked.

---

## 6. Calculating Retry and Backoff Time Before Choosing Chunk Size

### 6.1. How Long Can Each Item Hold a Transaction?

Suppose `chunkSize=50`, 5s request timeout, max 3 attempts, and backoffs of 0.5s and 1s:

```text
Per item ≈ 5 + 0.5 + 5 + 1 + 5 = 16.5 seconds

50 items × 16.5 seconds ≈ 825 seconds ≈ 13.75 minutes
```

That is a modeled worst case before accounting for database work, the writer, overhead, and retry logic variations. In a chunk-oriented step, remote calls run **inside the chunk transaction**; a chunk holding a transaction open for many minutes threatens locks, pools, timeouts, and rollbacks.

### 6.2. Ways to Reduce Impact

- Choose tight connect/request timeouts matching the service's actual latency SLO.
- Limit retries to recoverable failures; never retry 400/401/422.
- Use bounded backoff, optionally adding jitter so workers do not retry in lockstep.
- Consider lowering chunk size for steps calling slow remote services.
- Cap concurrent requests targeting the same service.
- Apply circuit breakers/bulkheads when a service fails persistently.
- When workflow permits, decouple remote interactions into a separate step or outbox/async reconciliation architecture.
- If the worst-case retry budget exceeds job SLA, prefer failing early so a scheduler can rerun later.

### 6.3. `Retry-After` with HTTP 429 and 503

A service may return a `Retry-After` header indicating how long to wait before calling again. At the HTTP layer:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 30
```

`ExponentialBackOffPolicy` above does not automatically read `Retry-After`. To honor it, the HTTP adapter must extract/propagate retry metadata and a custom policy or orchestrator must handle it. Still cap total wait time so transactions are never held indefinitely.

If `Retry-After` is very long (minutes or hours), it is usually better to **stop/requeue the batch for later** rather than keeping a transaction, DB connection, and worker thread asleep that entire time.

---

## 7. Remote Writes and Uncertain Outcomes: The Biggest Risk

Money-transfer scenario:

1. Batch sends `POST /transfers` to create transaction `T-123`.
2. The remote service commits it in its own database.
3. The response drops or lags, and the HTTP client times out.
4. Spring Batch sees `HttpTimeoutException`.
5. If the client blindly retries POST without idempotency, the remote service may create `T-123` a second time.

```text
Spring Batch                     Payment API
     │                                │
     │ POST transfer T-123            │
     ├───────────────────────────────►│
     │                                ├── Commit T-123
     │       lost response            │
     │◄ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─│
     │                                │
     ├─ Timeout                       │
     ├─ Retry POST                    │
     ├───────────────────────────────►│
     │                                └── May commit T-123 again
```

**A client timeout is not proof the server rolled back.** Spring Batch's chunk transaction does not enroll a remote service's database, HTTP system, broker, or object store into one distributed transaction.

### 7.1. Idempotency Keys

A standard solution is sending an idempotency key built from a **stable business identifier**, such as `transferId`:

```http
POST /transfers HTTP/1.1
Content-Type: application/json
Idempotency-Key: transfer:T-123

{"transferId":"T-123","amount":"125.00","currency":"USD"}
```

Under the contract, the server must guarantee:

1. On first receipt of the key, execute the transaction and store the outcome alongside the key atomically.
2. On subsequent calls with the same key and identical content, return the saved result or current status; **never create a second transaction**.
3. Same key with a different payload must be rejected (e.g., 409) rather than silently executing new content.
4. Retention window is long enough for batch retries, restarts, and backfills.
5. Outcomes can be queried by key or business transaction ID if a response was lost.

**Sending an `Idempotency-Key` header on the client alone is not enough.** The remote API must genuinely implement and uphold those semantics.

### 7.2. Never Generate a Random Key Per Attempt

Wrong:

```java
String key = UUID.randomUUID().toString();
// Every retry creates a new key → server treats it as a new request.
```

Better:

```java
String key = "transfer:" + transfer.businessId();
// Same transaction keeps the same key across retries/restarts.
```

If using `jobExecutionId` to build the key, remember restarting the same `JobInstance` normally creates a **new JobExecution**, producing a different key. Idempotency keys for side effects must derive from business IDs or period/item identifiers guaranteed stable by the domain.

### 7.3. Reconciling Before Retrying

On a POST timeout, recommended flow:

```text
Send POST with stable idempotency key
                   │
                   ▼
      Received clear response?
          ├── 2xx success → record result
          ├── 4xx permanent → fail/quarantine
          └── timeout/unknown
                   │
                   ▼
     GET status by transaction ID/key
          │
          ├── CONFIRMED → record success,
          │                do not POST again
          │
          ├── REJECTED  → handle business failure
          │
          ├── NOT_FOUND → retry POST only if
          │                server guarantees safety
          │
          └── UNKNOWN   → keep pending,
                           retry inquiry later,
                           or require manual handling
```

If the status endpoint is eventually consistent, `NOT_FOUND` immediately after POST does not prove the request was never processed. Follow the server's consistency SLA and inter-system integration contract.

### 7.4. Outbox and Asynchronous Execution

For critical side effects, instead of calling HTTP inside the chunk transaction, one architectural pattern is:

1. Spring Batch writes business state and an outbox row in **the same database transaction**.
2. A worker dispatches outbox messages/requests to the remote service.
3. The worker passes an idempotency key and persists ACKs/correlation IDs.
4. Reconciliation resolves `UNKNOWN` or un-ACKed requests.
5. A job/step finalizes once all mandatory items reach terminal states.

Outbox does not magically create exactly-once delivery; it coordinates reliable dispatch and pairs with receiver idempotency to control duplicate processing.

### 7.5. If the Remote API Lacks Idempotency Support

Never enable unconditional retries for payment, booking, or shipping calls. You may need:

- A status-query flow via business reference.
- A `PENDING_CONFIRMATION`/`UNKNOWN_OUTCOME` state table.
- Operator verification before resending.
- A *compensating action* API if permitted by contract.
- Redesigning the integration contract to add idempotency or correlation IDs.

When outcomes cannot be determined, **failing or pausing processing** is safer than a "COMPLETED" job that duplicated transactions.

---

## 8. Retry, Skip, and Fail in Spring Batch

### 8.1. Retry Transient, Fail Permanent

For mandatory-data jobs, the configuration in Section 5 is a solid starting point:

```java
.faultTolerant()
.retry(TransientRemoteException.class)
.retryLimit(3)
.backOffPolicy(backOffPolicy)
```

When transient exceptions persist beyond the attempt budget, the step fails unless a skip/recovery policy handles them. The final `JobExecution` normally becomes `FAILED`, storing exceptions and metadata status.

### 8.2. Skip Only When the Contract Permits

Suppose a job sends optional recommendation emails and may bypass records missing a customer profile. You might add:

```java
.faultTolerant()
.retry(TransientRemoteException.class)
.retryLimit(3)
.backOffPolicy(backOffPolicy)
.skip(PermanentRemoteException.class)
.skipLimit(10)
```

**Meaning:** items hitting permanent errors can be skipped, up to 10 items across the step under default policy; exceeding the threshold fails the step. This fits optional data—**not appropriate by default for money, taxes, or mandatory reconciliation**.

Never skip `Exception.class` wholesale, as that hides code bugs, drops data, or masks misconfiguration.

### 8.3. Quarantining Failed Records

If an item is allowed to skip, still persist:

- Business item ID and source-linking key.
- Job/step execution IDs and step name.
- Error type, HTTP status, and attempt count.
- Detection timestamp and downstream remediation state.
- Remote request reference/correlation ID.
- Masked payload or access-controlled pointer to original data.

`SkipListener` can record skipped items:

```java
public class RemoteSkipListener
        implements SkipListener<Payment, EnrichedPayment> {

    private final QuarantineService quarantine;

    public RemoteSkipListener(QuarantineService quarantine) {
        this.quarantine = quarantine;
    }

    @Override
    public void onSkipInProcess(Payment item, Throwable error) {
        quarantine.record(
                item.id(),
                "REMOTE_ENRICHMENT",
                error.getClass().getSimpleName());
    }
}
```

This sketch assumes `Payment`/`EnrichedPayment` and `QuarantineService` from your project. Quarantine writes must address transactions and idempotency: callbacks can participate in retry/rollback paths or re-fire on restart. Use a unique constraint so one failed record is not logged multiple times.

### 8.4. Do Not Confuse Retry Count with Skip Count

Getters like `StepExecution.getReadSkipCount()`, `getProcessSkipCount()`, and `getWriteSkipCount()` count **skipped items** per phase, not total HTTP retries. If you need "timeout count," add dedicated counters/metrics in the remote adapter or retry listener using bounded-cardinality labels.

A step finishing with `writeCount=990` and `processSkipCount=10` may still read `COMPLETED` per configuration. Business reporting must know where those 10 items went and whether they require reprocessing.

---

## 9. Remote Timeouts in Reader, Processor, and Writer

### 9.1. Reader Calling a Paginated API

Custom readers easily make this mistake:

```java
@Override
public RemoteItem read() {
    currentPage++;              // Increments page before request succeeds
    return fetchPage(currentPage); // Timeout → skips previous page
}
```

If `fetchPage` times out and Spring Batch retries `read()`, the already-incremented state causes the next call to jump to the following page, **dropping data**.

Safer pattern:

```java
@Override
public RemoteItem read() {
    RemoteItem item = fetchNextItem(lastConfirmedPosition);
    if (item == null) {
        return null;
    }
    lastConfirmedPosition = item.position();
    return item;
}
```

This illustrates the concept; multi-item page readers must manage page buffers, intra-page indices, checkpoints, and deterministic ordering completely. The rule is **never lose a logical item when a fetch fails**. With cursor-token APIs, persist the new token only after the page has been processed/committed per contract.

### 9.2. Processor Calling GET

Section 5's processor works because each item can be re-looked up by customer ID. Still check data consistency: if a customer's profile changes between retries, output can shift. When business requires a fixed snapshot, the remote API must support versions/as-of timestamps or you must use controlled caching.

### 9.3. Writer Sending POSTs Per Chunk

A writer receiving a 100-item chunk may send 60 requests successfully and time out on the 61st. When the writer throws and the local transaction rolls back, Spring Batch can re-invoke `write` during retry/restart. **The first 60 remote side effects do not roll back automatically.**

Therefore require one of these policies:

- Remote API enforces per-item idempotency.
- Bulk endpoint enforces batch idempotency and reports per-item outcomes.
- Outbox/async delivery decouples local commits from remote calls.
- Reconciliation by item ID and remote state precedes retries.

A writer lacking these safeguards cannot be made safe with `.retryLimit(3)` alone.

### 9.4. Tasklet Making a Long Request

`Tasklet` does not use chunk-step item-level retries by default. You can implement retry policies inside the Tasklet/service layer, yet cap total duration and track `PENDING/UNKNOWN` state if side effects were dispatched. Avoid sleeping for minutes inside a database transaction when long tasks can be modeled asynchronously.

---

## 10. Restarting After Remote Timeouts

### 10.1. Spring Batch Restarts Rely on Metadata

JobRepository stores `JobInstance`, `JobExecution`, `StepExecution`, and `ExecutionContext`. When a job fails, relaunching with **the same identifying JobParameters** creates a new `JobExecution` under the same `JobInstance`, provided the job/step is configured for restart.

For example, `businessDate=2026-11-15` identifies that day's import job. If it fails from a remote timeout, never change `businessDate=2026-11-16` just because recovery happens the next day. That creates a separate instance and can miss the old day's data.

### 10.2. Checkpoints Do Not Prove Remote Side Effects Rolled Back

Suppose a chunk reads 100 payments, calls the remote API cleanly for 50, and fails on payment 51. While the chunk remains uncommitted:

- `ExecutionContext` may not have persisted a new checkpoint.
- The local DB transaction can roll back.
- The remote API may still have processed the first 50 payments.
- On restart, Spring Batch can resend those 50 payments.

Only when remote writes support proper idempotency/reconciliation can the chunk replay without duplicating side effects. **Spring Batch's commit and a remote API's commit are two separate boundaries.**

### 10.3. Avoid Creating New JobInstances Just to Bypass Errors

A flawed workaround:

```java
new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addLong("runId", System.currentTimeMillis(), true)
        .toJobParameters();
```

Every new `runId` spawns a new instance, preventing the framework from using the prior instance's checkpoints/restarts and obscuring audit history for a data period.

For controlled retries, keep the same identifying keys, monitor the new execution, and query outcomes for ambiguous remote requests. Reprocess from scratch only under an explicit business policy with guaranteed idempotency and clear knowledge of already-processed scope.

### 10.4. Should You Auto-Restart Once Remote Recovers?

Yes, provided you verify:

- The job is marked restartable.
- The timeout was transient and the dependency now shows healthy signals.
- No unreconciled unknown side effects remain.
- Restart counts for the period remain within operational thresholds.
- The next scheduled run does not collide.
- Operators can distinguish item retries, step restarts, and period backfills.

Never manually update `BATCH_JOB_EXECUTION.STATUS` to "unlock" retries. Manual metadata edits can corrupt recovery logic; follow supported APIs and runbooks.

---

## 11. Circuit Breakers, Rate Limiting, and Bulkheads

### 11.1. Circuit Breakers

When a remote service times out continuously, firing thousands of retries overloads it further. A circuit breaker **fails fast** for a cooldown period so the target system can recover:

```text
CLOSED: normal calls, collects errors
      │ errors exceed threshold
      ▼
OPEN: rejects new requests during cooldown
      │ enough time elapsed
      ▼
HALF_OPEN: allows a few probe requests
      │
      ├─ succeed → CLOSED
      └─ still failing → OPEN
```

You can use Resilience4j or an equivalent library, coordinated with Spring Batch retry:

- `CallNotPermittedException` while the circuit is open should not trigger rapid dozens of retries.
- If the circuit stays open long, prefer failing/requeuing the batch over holding chunk transactions idle.
- Monitor error rates, open duration, and remote recovery.
- Never nest two circuit breakers/retries without knowing the combined request budget.

### 11.2. Rate Limiters

`429 Too Many Requests` usually calls for throttling. If a batch runs eight workers and each retries three times, workers can create a *retry storm*. Cap requests per second, apply backoff + jitter, and respect quotas/`Retry-After` per contract.

### 11.3. Bulkheads and Concurrency

Bounding in-flight requests protects pools, threads, and remote services. Even with chunk size 100, running 20 concurrent partitions calling HTTP can exceed a remote API's capacity. Tune concurrency against remote rate limits, timeouts, and connection limits.

### 11.4. Overall SLA

A service must not only be retryable—the batch must finish before its deadline. Balance:

- Per-request timeout.
- Backoff/cooldown.
- Retry attempts.
- Item counts and chunk sizes.
- Remote service throughput.
- Windows between scheduled periods.
- Recovery and backfill time if a batch ends `FAILED`.

If worst-case math exceeds the SLA, adopt async architectures, queues, and traffic shaping rather than simply raising timeouts.

---

## 12. Observability: Pinpointing Where Timeouts Occur

### 12.1. Spring Batch Metadata

With `JobExplorer`, inspect running or failed executions:

```java
JobExecution execution =
        jobExplorer.getJobExecution(jobExecutionId);

if (execution != null) {
    System.out.println(execution.getStatus());
    System.out.println(execution.getExitStatus());

    for (StepExecution step : execution.getStepExecutions()) {
        System.out.printf(
                "%s read=%d write=%d skip=%d rollback=%d%n",
                step.getStepName(),
                step.getReadCount(),
                step.getWriteCount(),
                step.getSkipCount(),
                step.getRollbackCount());
    }
}
```

Counters show step outcomes, yet **do not count individual HTTP timeouts or retries**. Add dedicated metrics in your remote adapter or retry listener.

### 12.2. Suggested Metrics

| Metric | Type | Usage |
|---|---|---|
| `remote_client_requests_total` | Counter | Total requests by service, operation, and outcome |
| `remote_client_timeouts_total` | Counter | Timeouts split by connect vs. response |
| `remote_client_retries_total` | Counter | Retries by service and error category |
| `remote_client_request_duration_seconds` | Histogram/Timer | p95/p99 latency of remote APIs |
| `remote_client_circuit_state` | Gauge | OPEN/HALF_OPEN/CLOSED per service |
| `batch_remote_pending_confirmation` | Gauge | Requests awaiting outcome reconciliation |
| `batch_remote_quarantine_total` | Counter | Items routed to quarantine |
| `spring.batch.job/step...` | Built-in meter family | Spring Batch job/step/item/chunk timings |

`remote_client_*` names in this table are **suggested custom metrics**, not built-in names emitted automatically. With Micrometer/Prometheus, meter names may be normalized on export, so verify actual exported series.

Avoid tagging every request with `customerId`, `paymentId`, URLs containing IDs, full error messages, or `jobExecutionId`; those cause high cardinality or leak data. Use bounded tags like service, method, operation, status family, and environment.

### 12.3. Essential Logs

Example diagnostic event:

```json
{
  "event": "REMOTE_TIMEOUT",
  "jobName": "dailyImportJob",
  "jobExecutionId": 7012,
  "stepName": "enrichmentStep",
  "businessDate": "2026-11-15",
  "service": "customer-service",
  "operation": "GET /customers/{id}",
  "attempt": 2,
  "maxAttempts": 3,
  "timeoutMs": 5000,
  "elapsedMs": 5032,
  "retryable": true,
  "outcome": "UNKNOWN",
  "correlationId": "req-55c7"
}
```

This is a sample log structure, not output from a specific platform. `outcome=UNKNOWN` fits when server progress is unknown; on pure-read GETs it does not risk duplicate side effects like POST, though source mutations can still cause data drift.

Never log credentials, sensitive request bodies, or responses carrying PII.

### 12.4. Actionable Alerts

Separate alert conditions:

- Timeout rate > threshold over 5 minutes.
- Multiple jobs failing simultaneously on one dependency.
- A job stalling from prolonged retries/backoff.
- Circuit breaker stuck open too long.
- Rising `PENDING_CONFIRMATION` or quarantine backlogs.
- Jobs failing near deadlines or missing periods after an outage.

Once the service recovers, still reconcile missed periods. Error rates returning to zero do not prove missed data was backfilled.

---

## 13. Testing Timeouts and Recovery

Never wait for a real production service to break before checking behavior. Test across three tiers:

1. **Unit test classifier/HTTP adapter:** timeout maps to a retryable exception, 401 maps to permanent, interrupts are preserved.
2. **Step integration test:** fault tolerance honors retry limits/backoff, step fails or skips as expected, metadata reflects outcomes.
3. **End-to-end/recovery test:** POST with idempotency, dropped response, job restart, and reconciliation produce zero duplicate side effects.

### 13.1. Unit Testing the HTTP Processor with Mockito

Example using Mockito and JUnit Jupiter, mocking Java `HttpClient` to throw a timeout without hitting the network:

```java
package com.example.batch.remote;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import java.math.BigDecimal;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import com.example.batch.remote.RemoteModels.Payment;
import com.example.batch.remote.RemoteModels.TransientRemoteException;

class CustomerEnrichmentProcessorTest {

    @Test
    void convertsHttpTimeoutToRetryableDomainException()
            throws Exception {

        HttpClient client = mock(HttpClient.class);

        when(client.<String>send(
                any(HttpRequest.class),
                org.mockito.ArgumentMatchers
                    .<HttpResponse.BodyHandler<String>>any()))
                .thenThrow(new HttpTimeoutException("simulated"));

        var processor = new CustomerEnrichmentProcessor(
                client,
                new ObjectMapper(),
                URI.create("https://customer.example/api/customers/"));

        var payment = new Payment(
                101L, 42L, new BigDecimal("12.00"));

        assertThrows(TransientRemoteException.class,
                () -> processor.process(payment));
    }
}
```

This test only checks that the processor converts timeouts into the expected exception type. It does **not** prove Spring Batch retried three attempts; verify that in a step integration test.

To test HTTP 429/500, mock `HttpResponse<String>` with the matching `statusCode()`. For 200, return valid JSON; for 401, assert `PermanentRemoteException`.

### 13.2. Step Integration Test for Retry Budget

Build a fixture reader returning one item and a writer recording into a test list. Have a fake remote service behave as:

- Call 1: timeout.
- Call 2: HTTP 503.
- Call 3: HTTP 200 with `{"tier":"GOLD"}`.

Run the real step/job with `@SpringBatchTest` and `JobLauncherTestUtils`, then assert:

- Final `JobExecution` is `COMPLETED`.
- Output item is written **exactly once**.
- The fake remote received calls matching the configured policy.
- `StepExecution.getReadCount()` and `getWriteCount()` are accurate.
- Zero unexpected skips.

A second test where all three attempts time out should assert `FAILED` with the exception reflecting the transient failure after exhausting retries (when skip is disabled).

**Note:** fault-tolerant steps may retry around transactions/rollbacks and vary processor/writer invocation counts depending on failure location, transactions, and caching. Assert expectations tailored to **your specific configuration** rather than generic guesses.

### 13.3. Testing Thread Interruption

Simulate `InterruptedException` from the HTTP client:

- Processor must restore the interrupt flag.
- Exception is excluded from retryables.
- Step stops/exits per policy.
- Interrupt is not swallowed in an infinite HTTP retry loop.

Because the interrupt flag can affect the JUnit worker thread, clear the interrupt state after asserting inside an isolated test harness.

### 13.4. Testing Unknown Outcomes on POST

A fake payment service should:

1. Receive `Idempotency-Key: transfer:T-123`.
2. Persist transaction T-123 successfully.
3. Intentionally withhold the response so the client times out.
4. Accept a status query or retry with the same idempotency key.
5. Return T-123's succeeded state without creating a second transaction.

The key assertion is **remote side-effect count = 1** with the batch recording the right outcome, even across multiple request attempts.

If a fake service omits idempotency, a test can prove why blind POST retries duplicate transactions—never ship that policy to production.

### 13.5. Testing Restarts

Using a dedicated batch repository:

- Run the job with a fixed `businessDate`.
- Make the fake remote time out until the step becomes `FAILED`.
- Switch the fake service back to healthy.
- Relaunch with the same identifying JobParameters or invoke the restart API.
- Assert `JobInstance` keeps its ID while the new `JobExecution` has a new ID.
- Verify final output has no duplicates or missing items.
- For POST side effects, verify idempotency/reconciliation.

### 13.6. Scenario Coverage Matrix

| Scenario | Expected Outcome to Verify |
|---|---|
| Connect timeout then recovery | Retries within budget, job completes |
| Persistent GET response timeout | Exhausts retries → FAILED, no infinite loop |
| HTTP 429 with Retry-After | Waits per policy or requeues, no retry storm |
| HTTP 401 | Fails fast without repeated retries |
| HTTP 404 | Follows contract: fail/skip/await consistency |
| HTTP 200 with invalid JSON schema | Permanent error, no fruitless retries |
| Interrupted during call | Interrupt flag preserved |
| Remote POST commits yet response drops | No duplicate side effects on retry/restart |
| Worker dies before local commit | Restores checkpoint and reconciles remote |
| Single item quarantined | Accurate audit and skip counters |
| 100% of items time out | Workers, connections, and transactions not held indefinitely |
| Multiple partitions retrying concurrently | Rate limits and concurrency stay controlled |
| Circuit breaker open | Fails fast/requeues per policy without HTTP spam |
| Monitor/repository unavailable | Failure signals emitted; never falsely marked success |

---

## 14. Common Design Mistakes

| Mistake | Why It Is Dangerous | Correct Approach |
|---|---|---|
| No HTTP timeout configured | Workers can block indefinitely | Explicit connect/request timeouts |
| Only setting connect timeout | Connected requests can stall waiting on responses | Add request/response timeout and deadlines |
| Retrying all RuntimeExceptions | Schema, auth, and code bugs get retried | Classify transient vs. permanent |
| Assuming POST timeout means server never processed | Response can drop after commit | Idempotency + inquiry/reconciliation |
| Using a new UUID per retry | Each attempt becomes a new transaction | Stable business idempotency keys |
| Only raising retryLimit | Increases duration, remote load, and lock times | Bounded retries + backoff + deadlines |
| Retrying at multiple layers | Attempts multiply unexpectedly | Single budgeted retry strategy |
| Skipping timeouts to force Job COMPLETED | Silently drops records | Skip only per contract, with quarantine |
| Changing runId to restart | Creates new instance, discards old checkpoints | Keep period identifying parameters |
| Treating local rollback as HTTP rollback | Two systems do not share one transaction | Outbox / idempotent remote APIs |
| Retrying reader errors after advancing cursor | Can drop a page or item | Advance only after successful read and proper checkpointing |
| Logging raw payloads/secrets | Sensitive data leaks | Structured logs, masking, correlation IDs |
| Unbounded concurrency | Retry storms worsen remote outages | Rate limiters, bulkheads, circuit breakers |
| Watching only BatchStatus | Blind to retries, latency, pending outcomes | HTTP metrics and reconciliation state |
| Manually editing BATCH_* tables to "recover" | Breaks metadata and restart semantics | Approved APIs and operational runbooks |

---

## 15. Runbook When Remote Service Timeouts Halt a Job

When alerted, investigate in an order that minimizes data risk.

### Step 1 — Determine Scope

Record `jobName`, `JobInstance`, `JobExecution`, `StepExecution`, identifying `JobParameters`, failure time, remote service, and operation. Check how many items committed, timed out, or were skipped/quarantined.

### Step 2 — Classify the Failure

Inspect logs/traces to separate connect timeouts, read/response timeouts, HTTP statuses, TLS errors, auth errors, and invalid data. Identify whether the operation is a read GET or a state-changing POST.

### Step 3 — Inspect the Remote Dependency

Check service health, p95/p99 latency, rate limits, circuit breakers, connection pools, proxies, DNS, network policies, and active incidents. If the remote API returned `Retry-After`, verify whether the batch honored it.

### Step 4 — Verify Side Effects

For state-changing POST/PUT/PATCH calls, look up status by business transaction ID or idempotency key. If outcomes remain unclear, hold as `PENDING_CONFIRMATION` and reconcile rather than resending in bulk.

### Step 5 — Choose Recovery Action

- Transient GET error and remote is healthy: restart/retry per policy.
- Auth/configuration error: fix credentials/config before rerunning.
- Data error: fix input, quarantine, or skip per business rules.
- Unknown side effects: reconcile results before retrying.
- Job FAILED with valid checkpoints: restart with the same identifying parameters.
- Job partially published output: check overwrite/append/idempotency rules before rerunning.

### Step 6 — Reconcile and Close the Incident

Verify item counts, outputs, remote transaction statuses, `StepExecution` counters, remaining quarantine backlogs, and affected business periods. Close the incident only once all mandatory items reach terminal status.

---

## 16. Practice Exercises

### Exercise 1 — Configuring Timeouts

Using Java 17 `HttpClient`, set a 1s connect timeout and 3s request timeout. Point it at a test endpoint taking >3s to respond; assert `HttpTimeoutException` (or appropriate subclass) and confirm the batch does not wait forever.

### Exercise 2 — Transient Retries

Create a fake customer service returning 503 twice followed by 200. Configure `retryLimit(3)` and exponential backoff. Verify accurate final output, expected call count, and zero skipped items.

### Exercise 3 — Permanent Errors

Have the service return 401 and HTTP 200 missing `tier`. Prove the processor throws a permanent exception without firing bulk retries.

### Exercise 4 — Calculating Total Retry Budget

A remote call times out after 4s with `retryLimit` 4 and backoffs of 1s, 2s, and 4s. Estimate worst-case duration for one item and for a 50-item chunk. Propose chunk, timeout, or architectural changes if the SLA is only 2 minutes.

### Exercise 5 — Uncertain Side Effects

Make a fake payment API commit transactions while dropping responses. Implement idempotency keys and status lookups, proving retries/restarts never create a second transaction.

### Exercise 6 — Quarantine

Design a `SkipListener` storing permitted 404 skips with business key, error code, and audit timestamp. Verify `processSkipCount` and quarantine record counts while guarding against duplicates on restart.

### Exercise 7 — Paginated Readers

Write a custom API reader that intentionally increments the page token before fetching. Simulate a timeout to observe a skipped page. Fix the reader so state does not advance on failed fetches and test checkpoint restarts.

### Exercise 8 — Circuit Breakers

Simulate a 5-minute customer-service outage; compare total attempts between plain retries and retries paired with a circuit breaker/rate limiter. Evaluate service load and per-chunk execution times.

### Exercise 9 — Real Recovery

Run a job over fixed input and force remote timeouts until the step becomes `FAILED`. Restore the service and restart the same `JobInstance`. Reconcile output for zero duplicates/losses and inspect `JobExecution` history.

---

## 17. References

- [Spring Batch 5.2 — Configuring Retry Logic](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/retry-logic.html): configuring `faultTolerant`, `retryLimit`, and retryable exceptions.
- [Spring Batch 5.2 — Configuring Skip Logic](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/configuring-skip.html): skip policies and skip limits.
- [Spring Batch 5.2 — Controlling Rollback](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/controlling-rollback.html): rollbacks in chunk steps.
- [Spring Batch 5.2 — Retry](https://docs.spring.io/spring-batch/reference/5.2/retry.html): stateful/stateless retries and retry scenarios.
- [Spring Batch 5.2 — ItemStream](https://docs.spring.io/spring-batch/reference/5.2/readers-and-writers/item-stream.html): checkpoints and restart state.
- [Spring Batch 5.2 — JobRepository](https://docs.spring.io/spring-batch/reference/5.2/job/configuring-repository.html): metadata and transactions.
- [FaultTolerantStepBuilder — API 5.2.1](https://docs.spring.io/spring-batch/docs/5.2.1/api/org/springframework/batch/core/step/builder/FaultTolerantStepBuilder.html): `retryLimit`, `retry`, and `backOffPolicy`.
- [Java 17 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): `connectTimeout`.
- [Java 17 — HttpRequest.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): per-request `timeout`.
- [Java 17 — HttpTimeoutException](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpTimeoutException.html): exception when response fails to arrive on time.
- [Spring Retry](https://docs.spring.io/spring-retry/reference/): backoff, retry policies, and retry control mechanisms.
- [Resilience4j](https://resilience4j.readme.io/): circuit breakers, rate limiters, and bulkheads.

A batch job with strong recovery separates **retryable transient errors** from **uncertain outcomes after remote side effects are dispatched**. Timeouts and backoffs protect execution time; `JobRepository` and `ExecutionContext` enable restarts; idempotency, status inquiries, and reconciliation safeguard data correctness across distributed systems. Combining those layers with metrics and runbooks lets jobs recover from remote outages without silently duplicating transactions or dropping required data.
