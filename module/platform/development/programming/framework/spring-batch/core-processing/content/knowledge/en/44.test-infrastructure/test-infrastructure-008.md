# Mocking External Services in Spring Batch Testing

## 1. Why Mock External Services?

In Spring Batch, a job might read data from a file or database and then call an HTTP API, gRPC service, payment gateway, customer lookup service, or internal system before deciding what output to write. Those dependencies can be slow, temporarily unreachable, rate-limited, or return data that changes over time.

In batch processing tests, **mocking external services** replaces the integration boundary with an object or server whose behavior is fully controlled. Tests can deterministically produce success responses, business rejections, timeouts, HTTP 429/503 errors, and malformed payloads without depending on the live service.

The goal goes beyond verifying that a method was called. A Spring Batch test with mocked external services should prove:

- Which input data is sent to the service and when.
- That the job transforms or filters items accurately based on the response.
- That retry, skip, and failure occur according to configured policies.
- That Step counters and final persisted output match expectations.
- That service failures do not publish corrupt output or cause duplicate processing on restart.

For example, an order-import job calls **CustomerRiskClient** to obtain a risk score for each customer:

~~~text
orders.csv / staging_order
          |
          v
       ItemReader
          |
          v
      ItemProcessor --------> CustomerRiskClient --------> Real service
          |                       ^
          |                       |
          |                 Mock in test
          v
       ItemWriter
          |
          v
    approved_order
~~~

In the test, the exact same job and processor run, while the **CustomerRiskClient** dependency is replaced with predetermined behavior. This focuses the test on batch logic, error thresholds, and Step transactions.

## 2. Choosing the Right Level of Mocking for the Test Goal

No single mocking approach fits every case. The simulation boundary determines what is verified and what still requires another test.

| Approach | Where It Substitutes | What It Verifies | What It Does Not Verify |
|---|---|---|---|
| **Mockito interface mock** | Client interface injected into processor/writer | Business rules, retry/skip, call arguments, counters, outputs | HTTP serialization, status codes, headers, real timeouts |
| **Stateful fake client** | Same client interface | Multi-call scenarios, request logs, simple idempotency | Real network protocol and configuration |
| **WireMock / MockWebServer** | Local HTTP server | URLs, methods, JSON, headers, status codes, timeouts, adapter error mapping | End-to-end production system behavior |
| **Virtual service in integration env** | Network endpoint simulated by container/service | Network connectivity, test auth config, end-to-end flows | Compatibility with real service if contract tests are missing |
| **Authorized contract/sandbox test** | Real compatible service | Schema, protocol, and API version compatibility | Usually less stable than local mock tests |

A common layered structure:

1. **Processor unit tests**: Mockito for the service interface, verifying per-item decisions.
2. **Spring Batch integration tests**: run real Job/Step with a mock client and test database to verify status, retry counts, skips, and outputs.
3. **HTTP adapter tests**: use a local stub server to verify endpoints, JSON, status codes, timeouts, and error translation.
4. **Scoped contract/integration tests**: verify compatibility against the real service when a suitable environment is available.

Do not bury external client instantiation deep inside processing code. If a processor constructs an HTTP client with **new**, tests cannot swap the dependency easily; route service calls through an interface and dependency injection.

## 3. Business Example for Building Tests

Suppose **importOrdersJob** processes each order containing **orderId**, **customerId**, and **amount**. The processor calls a service to get an integer risk score from 0 to 100.

Business contract for the example:

| Service Result | Expected Behavior |
|---|---|
| Score 0–75 | Approve order, write to `approved_order` table |
| Score 76–100 | Filter order, processor returns `null`; increments `filterCount` |
| Score outside 0–100 | Invalid response payload; throws `InvalidRiskResponseException`; skippable per policy |
| Service temporarily unavailable | Throws `RiskTimeoutException`; retries up to limit |
| Failure persists after exhausting retries | Step becomes `FAILED` if exception is not skippable |
| Input file missing or output DB connection lost | Step becomes `FAILED` per operational policy |

A high risk score is **filtered** as a business rule, not a technical error. A score of 120 is bad response data from the service, while a timeout is a transient fault. Separating these three cases lets us configure **filter**, **skip**, and **retry** cleanly.

To stay focused on batch logic, assume one input item produces at most one target record and the writer uses the database with the Step's transaction manager.

## 4. Decoupling the External Service Interface from the Processor

First, define the Java contract used by the batch job:

~~~java
public interface CustomerRiskClient {
    int scoreFor(String customerId);
}

public record RawOrder(
        String orderId,
        String customerId,
        java.math.BigDecimal amount) {
}

public record ApprovedOrder(
        String orderId,
        String customerId,
        java.math.BigDecimal amount,
        int riskScore) {
}

public class RiskTimeoutException extends RuntimeException {
    public RiskTimeoutException(String message) {
        super(message);
    }
}

public class InvalidRiskResponseException extends RuntimeException {
    public InvalidRiskResponseException(String message) {
        super(message);
    }
}
~~~

In a real application, an HTTP adapter implements **CustomerRiskClient** and translates service responses into domain values. HTTP 503s, connection timeouts, and invalid JSON responses must be classified cleanly per the contract; throwing a generic **RuntimeException** everywhere makes retry/skip configuration unreliable.

The processor knows nothing about URLs, tokens, or HTTP clients. It only depends on the interface:

~~~java
import org.springframework.batch.item.ItemProcessor;
import org.springframework.context.annotation.Bean;

@Bean
public ItemProcessor<RawOrder, ApprovedOrder> riskProcessor(
        CustomerRiskClient customerRiskClient) {

    return order -> {
        int score = customerRiskClient.scoreFor(order.customerId());

        if (score < 0 || score > 100) {
            throw new InvalidRiskResponseException(
                    "Invalid risk score for orderId=" + order.orderId());
        }

        if (score > 75) {
            return null; // Filter per business rule
        }

        return new ApprovedOrder(
                order.orderId(),
                order.customerId(),
                order.amount(),
                score);
    };
}
~~~

In tests, Mockito can control the return value of **scoreFor** without editing the processor or production code. If the real service provides reason codes, scoring model version, or decision timestamp, include those fields in a response object rather than cramming everything into a single integer.

### Note on Repeatability

A retry can invoke the processor again. If the risk score changes between attempts, the same item could receive a different decision. For sensitive data or jobs that must restart deterministically, specify response versioning, per-batch caching/snapshotting, or request timing rules. Mock tests should exercise both stable responses and deliberate changes.

## 5. Configuring Job/Step to Test with Mocks

The examples below follow Spring Batch 5+ style with injected **JobRepository** and **PlatformTransactionManager**, focusing on wiring the reader, processor, writer, and fault tolerance.

### 5.1. Reader Receiving File Path via Job Parameter

~~~java
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;

@Bean
@StepScope
public FlatFileItemReader<RawOrder> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<RawOrder>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .linesToSkip(1)
            .delimited()
            .names("orderId", "customerId", "amount")
            .fieldSetMapper(fields -> new RawOrder(
                    fields.readString("orderId"),
                    fields.readString("customerId"),
                    fields.readBigDecimal("amount")))
            .build();
}
~~~

**@StepScope** ensures the file is resolved when the Step runs with a specific execution's job parameters. Stateful readers must never be shared across concurrent job executions.

### 5.2. Writer Producing Verifiable Output

Suppose the target table in the test database is:

~~~sql
CREATE TABLE approved_order (
    order_id    VARCHAR(50) PRIMARY KEY,
    customer_id VARCHAR(50) NOT NULL,
    amount      DECIMAL(18, 2) NOT NULL,
    risk_score  INTEGER NOT NULL
);
~~~

Illustrative writer:

~~~java
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@Bean
public ItemWriter<ApprovedOrder> approvedOrderWriter(
        JdbcTemplate jdbcTemplate) {

    return chunk -> {
        for (ApprovedOrder order : chunk) {
            jdbcTemplate.update(
                    """
                    INSERT INTO approved_order
                        (order_id, customer_id, amount, risk_score)
                    VALUES (?, ?, ?, ?)
                    """,
                    order.orderId(),
                    order.customerId(),
                    order.amount(),
                    order.riskScore());
        }
    };
}
~~~

In production, the table should include a **batchId** or appropriate business key along with idempotency rules to prevent duplicates on restart. A JDBC writer participates in chunk rollback when sharing a consistent datasource and transaction manager; HTTP calls do not automatically join a database transaction.

### 5.3. Intentional Retry and Skip Configuration

~~~java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
public Step riskStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        FlatFileItemReader<RawOrder> orderReader,
        ItemProcessor<RawOrder, ApprovedOrder> riskProcessor,
        ItemWriter<ApprovedOrder> approvedOrderWriter) {

    return new StepBuilder("riskStep", jobRepository)
            .<RawOrder, ApprovedOrder>chunk(2, transactionManager)
            .reader(orderReader)
            .processor(riskProcessor)
            .writer(approvedOrderWriter)
            .faultTolerant()
            .retry(RiskTimeoutException.class)
            .retryLimit(3)
            .skip(InvalidRiskResponseException.class)
            .skipLimit(1)
            .build();
}

@Bean
public Job importOrdersJob(JobRepository jobRepository, Step riskStep) {
    return new JobBuilder("importOrdersJob", jobRepository)
            .start(riskStep)
            .build();
}
~~~

In this configuration:

- **RiskTimeoutException** is retried up to three total attempts, including the initial try. If it still fails, this exception is not skippable and the Step becomes FAILED.
- **InvalidRiskResponseException** may be skipped for at most one item in the Step.
- A risk score above 75 is a business filter; **filterCount** increments, not **processSkipCount**.
- **skipLimit** applies to total skips in the Step, not separately per exception type.

Retry and skip policies must reflect the nature of the external service. Never configure **skip(Exception.class)** or retry all exceptions indiscriminately, as that can mask coding bugs, authentication errors, corrupt data, or misconfigurations.

## 6. Designing Test Data and Mock Scenarios

Test data file **orders.csv**:

~~~csv
orderId,customerId,amount
O001,C001,120.00
O002,C002,80.50
O003,C003,60.00
~~~

Define mocked responses:

| Item | Service Call | Mock Response | Expectation |
|---|---|---|---|
| O001 | scoreFor("C001") | 20 | Written to `approved_order` |
| O002 | scoreFor("C002") | 90 | Filtered, not written |
| O003 | scoreFor("C003") | 120 | Process-skipped due to out-of-range score |

With the file above and the Step as defined:

| Metric / Outcome | Expected |
|---|---:|
| readCount | 3 |
| readSkipCount | 0 |
| filterCount | 1 |
| processSkipCount | 1 |
| writeSkipCount | 0 |
| writeCount | 1 |
| Output row count | 1 |
| `order_id` present in target | O001 |
| Job BatchStatus | COMPLETED |

Tests should verify both **counters** and **actual persisted data**. Asserting only that the mock was called three times could miss bugs where the processor accidentally writes O002 or stores the wrong `risk_score`.

## 7. Spring Batch Integration Test with Mockito

Spring Batch Test supports launching Jobs in tests via **JobLauncherTestUtils**. With Spring Framework 6.2+ / compatible Spring Boot, use **@MockitoBean** to replace the client bean with a mock in the application context. Older Spring Boot versions may use **@MockBean** per that version's API.

Prerequisites for the example:

1. A Spring Boot application containing the Job, Step, reader, processor, and writer beans above.
2. The test context has **one matching Job** or `JobLauncherTestUtils` is explicitly pointed to the target Job.
3. The test database already has the Spring Batch metadata schema and the **approved_order** table.
4. Launches are triggered explicitly rather than letting Boot run jobs at context startup.
5. Each test has an isolated output database so parallel tests do not interfere.

For projects using Spring Boot dependency management, declare the corresponding test libraries:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
}
~~~

JUnit 5 example:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.UUID;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class RiskEnrichmentBatchIT {

    @MockitoBean
    CustomerRiskClient riskClient;

    @Autowired
    JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @TempDir
    Path workDir;

    @BeforeEach
    void clearOutput() {
        // Run only in a dedicated test DB for this class.
        jdbcTemplate.update("DELETE FROM approved_order");
    }

    @Test
    void handlesApprovalFilteringAndInvalidResponse() throws Exception {
        when(riskClient.scoreFor("C001")).thenReturn(20);
        when(riskClient.scoreFor("C002")).thenReturn(90);
        when(riskClient.scoreFor("C003")).thenReturn(120);

        JobExecution execution = launch(
                """
                orderId,customerId,amount
                O001,C001,120.00
                O002,C002,80.50
                O003,C003,60.00
                """);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());

        StepExecution step = execution.getStepExecutions().stream()
                .filter(e -> "riskStep".equals(e.getStepName()))
                .findFirst()
                .orElseThrow();

        assertEquals(3L, step.getReadCount());
        assertEquals(0L, step.getReadSkipCount());
        assertEquals(1L, step.getFilterCount());
        assertEquals(1L, step.getProcessSkipCount());
        assertEquals(0L, step.getWriteSkipCount());
        assertEquals(1L, step.getWriteCount());

        List<String> ids = jdbcTemplate.queryForList(
                "SELECT order_id FROM approved_order ORDER BY order_id",
                String.class);
        assertEquals(List.of("O001"), ids);

        Integer score = jdbcTemplate.queryForObject(
                "SELECT risk_score FROM approved_order WHERE order_id = ?",
                Integer.class, "O001");
        assertEquals(20, score);

        verify(riskClient).scoreFor("C001");
        verify(riskClient).scoreFor("C002");
        verify(riskClient).scoreFor("C003");
    }

    private JobExecution launch(String csvContent) throws Exception {
        Path input = workDir.resolve(UUID.randomUUID() + ".csv");
        Files.writeString(input, csvContent, StandardCharsets.UTF_8);

        JobParameters parameters = new JobParametersBuilder()
                .addString("inputFile", input.toAbsolutePath().toString())
                .addString("testRunId", UUID.randomUUID().toString())
                .toJobParameters();

        return jobLauncherTestUtils.launchJob(parameters);
    }
}
~~~

The following test methods can be added to the same class using the **launch** helper above. When multiple Jobs exist in the context, assign the right Job to **JobLauncherTestUtils** rather than letting it pick arbitrarily. If tests run in parallel, clearing the whole table in **@BeforeEach** causes contention; use separate databases, isolated transactions, or data partitioned by test ID.

**Key distinction:** mocking the **CustomerRiskClient** interface verifies batch logic without making HTTP requests. It does not prove that URLs, JSON payloads, request headers, or HTTP error translation in the adapter are correct.

## 8. Mocking Transient Failures to Test Retry

When a service temporarily times out, retry should re-invoke processing for that item and proceed with writing once the service recovers. With a single item and a side-effect-free processor, Mockito can simulate two failures followed by success.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@Test
void retriesTransientRiskServiceFailureAndThenSucceeds() throws Exception {
    when(riskClient.scoreFor("C001"))
            .thenThrow(new RiskTimeoutException("temporary timeout"))
            .thenThrow(new RiskTimeoutException("temporary timeout"))
            .thenReturn(25);

    JobExecution execution = launch(
            """
            orderId,customerId,amount
            O001,C001,120.00
            """);

    assertEquals(BatchStatus.COMPLETED, execution.getStatus());
    verify(riskClient, times(3)).scoreFor("C001");

    assertEquals(1L, jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM approved_order",
            Long.class));
}
~~~

If the mock always throws a timeout:

~~~java
@Test
void failsWhenRiskServiceRetryIsExhausted() throws Exception {
    when(riskClient.scoreFor("C001"))
            .thenThrow(new RiskTimeoutException("still unavailable"));

    JobExecution execution = launch(
            """
            orderId,customerId,amount
            O001,C001,120.00
            """);

    assertEquals(BatchStatus.FAILED, execution.getStatus());
    verify(riskClient, times(3)).scoreFor("C001");
}
~~~

In the illustrated configuration, **retryLimit(3)** allows at most three attempts (initial try plus retries). The exception class must match the retry configuration; if the HTTP adapter wraps it in another exception type, fix the error classification or update the configuration.

**Do not treat mock invocation count as the sole proof of retry in every job.** If an error occurs in the writer, chunk rollback can re-invoke the processor. With multi-item chunks, stateful retry, caches, and additional processing steps, total call counts can differ from the single-item model above.

## 9. Mocking Non-Skippable Failures and Skip Limits

Simulate two items with invalid responses when the configuration only allows **skipLimit(1)**:

~~~java
@Test
void failsWhenMoreThanOneInvalidResponseIsSkipped() throws Exception {
    when(riskClient.scoreFor("C001")).thenReturn(120);
    when(riskClient.scoreFor("C002")).thenReturn(-1);

    JobExecution execution = launch(
            """
            orderId,customerId,amount
            O001,C001,120.00
            O002,C002,80.50
            """);

    assertEquals(BatchStatus.FAILED, execution.getStatus());
}
~~~

The **FAILED** result is intentional: too many invalid responses indicate the output cannot be trusted. In a real job, add a publish-status flag so downstream consumers do not read partial output by mistake.

Include a dedicated test for an exception that is **neither retried nor skipped**, such as an authentication failure or endpoint misconfiguration. The aim is to prove the policy does not swallow arbitrary exceptions. For HTTP 404, 401, or 429 responses, retry/skip/fail decisions must come from the specific API contract; no single policy fits all services.

## 10. Mocking an HTTP Server to Test the Adapter Itself

Interface mocking with Mockito is fast, but it skips the protocol layer. When you need to verify URLs, query parameters, headers, JSON mapping, HTTP 503, malformed response bodies, and timeouts, spin up a local **HTTP stub server** with WireMock or OkHttp MockWebServer and have the real HTTP adapter call the test-assigned port.

Illustrative REST contract:

~~~http
GET /risk/C001 HTTP/1.1
Accept: application/json
X-Correlation-Id: test-run-123
~~~

Success response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"score":20}
~~~

Transient failure response:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json

{"code":"TEMPORARILY_UNAVAILABLE"}
~~~

JUnit 5 WireMock setup example:

~~~java
import static com.github.tomakehurst.wiremock.client.WireMock.get;
import static com.github.tomakehurst.wiremock.client.WireMock.okJson;
import static com.github.tomakehurst.wiremock.client.WireMock.urlEqualTo;
import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.wireMockConfig;

import com.github.tomakehurst.wiremock.junit5.WireMockExtension;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.RegisterExtension;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

class CustomerRiskHttpAdapterIT {

    @RegisterExtension
    static WireMockExtension riskApi = WireMockExtension.newInstance()
            .options(wireMockConfig().dynamicPort())
            .build();

    @DynamicPropertySource
    static void riskProperties(DynamicPropertyRegistry registry) {
        registry.add("risk.base-url", riskApi::baseUrl);
    }

    @Test
    void mapsSuccessfulHttpResponse() {
        riskApi.stubFor(get(urlEqualTo("/risk/C001"))
                .willReturn(okJson("{\"score\":20}")));

        // Call the real CustomerRiskClient HTTP adapter from the Spring context.
        // Assert scoreFor("C001") == 20 and that the request matched the stub.
    }
}
~~~

This snippet demonstrates the **server stub** part; to run end-to-end, add **@SpringBootTest** or test context configuration, inject the real adapter, and include a compatible WireMock dependency. The property name **risk.base-url** must match the application's HTTP adapter property. This class **must not use @MockitoBean for CustomerRiskClient**, because doing so would replace the real adapter and the stub server would never receive any requests.

An adapter test suite should verify:

| HTTP Stub Scenario | Expected Adapter Outcome |
|---|---|
| 200 + valid JSON schema | Parses into the exact risk score |
| 200 + JSON missing required fields | Explicitly classified invalid response data error |
| 200 + wrong JSON type or out-of-range score | Does not silently fall back to an invalid default |
| 503, 429 per contract | Transient exception suitable for retry and backoff |
| 401/403 from invalid credentials | Authentication error classification; typically fails and alerts |
| 404 | Matches API semantics: valid not-found vs. critical error |
| Closed connection, slow response exceeding timeout | Network error mapped to retryable exception when appropriate |
| Missing header, wrong URL, or wrong body | Stub does not match and test fails with a clear reason |

**Timeouts** should generally be configured short in tests rather than waiting for production timeout durations. **Backoff** can also be kept short in tests, while extracting delay-selection logic into a unit-testable component if timing intervals need verification.

To avoid fragmented coverage, include at least one end-to-end path: the HTTP stub returns 503 then 200, the HTTP adapter maps the error to **RiskTimeoutException**, the Step retries, and finally writes a single record. That validates the integration between the adapter and Spring Batch, which interface-only mocks cannot prove.

## 11. Verifying Call Arguments and Critical Behavior

Mockito lets you verify that the processor passes **customerId** and does not accidentally pass **orderId**:

~~~java
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.never;
import static org.mockito.ArgumentMatchers.anyString;

verify(riskClient).scoreFor("C001");
verify(riskClient, never()).scoreFor("O001");
~~~

If the API accepts a request object carrying batchId, requestId, and an idempotency key, you can use **ArgumentCaptor** to inspect those fields:

~~~java
// General example with another interface:
// ArgumentCaptor<RiskRequest> captor =
//         ArgumentCaptor.forClass(RiskRequest.class);
// verify(riskClient).evaluate(captor.capture());
// assertEquals("BATCH-42", captor.getValue().batchId());
~~~

Only assert parameters that belong to the **business contract**. Avoid forcing the processor to call the service in a rigid order when jobs can run concurrently or rollbacks reprocess items. Assertions coupled too tightly to implementation details break easily even when outputs are right.

For services that perform writes—such as **chargePayment**, **reserveInventory**, or **sendNotification**—merely mocking a success response is not enough. Assert that requests carry a stable idempotency key, and in simulated integration tests verify whether repeating the same request causes a new side effect.

## 12. Simulating Side Effects, Retry, and Idempotency

When a processor only **queries** a service, retries carry far less risk than when a processor **mutates state** on the service. For external write operations, a critical scenario is:

~~~text
Batch sends payment request
       |
       v
External service processes successfully
       |
       v
Response back to Batch times out
       |
       v
Batch retries the same request
~~~

If the second request uses a different key, a duplicate transaction can occur. Tests should simulate "processed successfully but response lost," rather than only simulating "service did nothing and returned 503."

A **stateful fake** can store idempotency keys and their results:

~~~java
import java.util.HashMap;
import java.util.Map;

final class FakeReservationService {
    private final Map<String, String> reservationIdsByKey = new HashMap<>();
    private int newReservations;

    String reserve(String idempotencyKey) {
        return reservationIdsByKey.computeIfAbsent(idempotencyKey, key -> {
            newReservations++;
            return "RES-" + newReservations;
        });
    }

    int newReservations() {
        return newReservations;
    }
}
~~~

This fake is **not thread-safe** and is intended only for sequential tests. If a Step runs with a task executor or partitioning, use thread-safe synchronization or a stub server with a thread-safe request log; avoid introducing race conditions into the test itself.

With two calls using the same `idempotencyKey`, the test should receive the same reservation ID and observe **newReservations() = 1**. With two distinct keys, new reservations equal two. This suite tests duplicate-side-effect prevention; it does not prove the real service implements idempotency correctly, so contract/integration tests are still needed when possible.

## 13. Simulating Failure Recovery and Restart

Spring Batch persists checkpoints and metadata for **JobInstance / JobExecution / StepExecution**. A FAILED job can be restarted under the matching restart policy. When testing restart, external service mocks must cover both executions, while distinguishing:

- **Rerunning the same JobInstance**: keep the identifying job parameters and restart after a FAILED or STOPPED execution.
- **Running a new JobInstance**: change identifying parameters to test independent imports.
- **Resetting mocks between runs**: reset only intentionally; if service state is part of the restart scenario, preserve it in a suitable fake or stub server.

Example scenario:

1. On the first run, O001 gets score 20 and its chunk commits; O002 hits API timeouts past the retry limit, and the job becomes FAILED.
2. The service recovers; the job restarts with the same input and JobInstance per Batch rules.
3. The test checks that the final output contains each `order_id` exactly once with the right score and no duplicate rows.
4. Only after the job and reconciliation complete does the system mark the batch READY.

Having the mock return success on the second run is not enough to prove outputs are duplicate-free. Tests need **real database state** or a side-effect-tracking fake combined with unique constraints and upsert/skip rules.

When a reader checkpoints file positions, **do not alter file contents between restarts**. If input must be corrected, issue a new batch/version per the designed workflow. That keeps the test faithful to real recovery behavior.

## 14. Concurrent Steps, Partitioning, and Rate Limits

With multi-threaded Steps, partitioning, or remote chunking, service calls can happen concurrently in non-deterministic order.

Testing principles:

- Do not rely on **call order** unless the contract guarantees ordering.
- Do not share unsynchronized iterators, queues, or mutable counters across threads.
- Mocks should return responses keyed by **request key** (such as `customerId`) rather than positional sequences like **thenReturn(A, B, C)**.
- With partitioning, separate data and outputs by partition or batchId for clean verification.
- Test rate limits with HTTP 429 responses and deterministic retry/backoff policies; if the API returns **Retry-After**, the adapter must parse and honor it as designed.
- Remember total requests after retries can exceed `readCount`, especially on chunk rollbacks.

For instance, a rate-limit test can have the stub server record request timestamps to check backoff, without using overly tight timing thresholds that flake on slow CI runners. When the **backoff rule** itself is under test, extract the policy or sleeper/clock for isolated unit testing, and keep a focused integration test verifying the client reacts properly to 429/503.

## 15. Managing Test Data, Mocks, and Context State

Environment-dependent test flakiness usually comes from test infrastructure rather than batch logic:

| Issue | Proper Organization |
|---|---|
| Job auto-runs when Spring Boot test starts | Set `spring.batch.job.enabled=false` |
| Multiple Job beans exist; utility does not know which to pick | Assign the specific Job to `JobLauncherTestUtils` |
| Singleton reader retains state after an execution | Use `@StepScope` to instantiate readers per execution |
| `JobInstance` already COMPLETED so same parameters fail to rerun | Generate fresh identifying parameters for independent runs |
| Previous test leaves rows in output table | Isolate test database/schema or clean up by test/batchId |
| Mock retains stubbing or interactions from earlier test | Follow framework lifecycle/resets; reset fake state manually |
| HTTP mock bound to a fixed port | Use a dynamic port and pass base URL into the adapter |
| Test hits a live external endpoint | Inject mock client or local server base URL; isolate outbound network |
| Concurrent tests show non-deterministic results | Stub by request key; eliminate unsynchronized shared mutable state |
| Retries make tests wait too long | Configure short timeouts/backoffs in the test profile |

Test mocks should **fail loudly when stubbing is missing**. For example, a Mockito method returning **int** returns **0** by default; if 0 is a valid risk score, an unstubbed call can silently pass approval. Configure mocks with strict default answers, have the interface return a nullable wrapper object, or explicitly verify all expected requests/results. Never treat a default return value as a valid service response.

For sensitive data, never log raw access tokens, `Authorization` headers, PII, or payment payloads when recording mock server interactions. Use synthetic data and log only correlation IDs, error types, test keys, and required diagnostics.

## 16. Recommended Test Matrix for External Services in Batch

| Scenario | Mock Behavior | Key Assertions |
|---|---|---|
| Successful response | Returns valid score | Output values match and Job is COMPLETED |
| Filtering rule | Returns score in rejection range | `filterCount` increments; no output written |
| Invalid response | Returns out-of-range score / bad schema | Correct exception type; skipped or FAILED per policy |
| Timeout then recovery | Two timeouts, third call succeeds | Retried within limit; one record written |
| Prolonged timeout | Always throws retryable exception | Job FAILED; output not published |
| Skip at threshold | One invalid response with `skipLimit=1` | Job continues; `processSkipCount=1` |
| Skip exceeds threshold | Two invalid responses | Job FAILED |
| Non-skippable error | Throws exception outside policy | Job FAILED immediately |
| HTTP 503 / 429 | Stub server returns retryable status | Adapter maps error properly; test retry/backoff |
| HTTP 401 / 403 | Stub server returns auth error | Error not swallowed; alerted / FAILED |
| JSON missing fields | Stub server returns malformed schema | Does not use fallback defaults that corrupt output |
| Timeout after successful side effect | Fake records side effect but drops response | Retry preserves idempotency key; no duplicate side effect |
| Restart after FAILED | First run fails, second run service recovers | `JobInstance` restarts cleanly; no duplicate output |
| Two parallel batches | Different responses per batch/request key | No cross-talk or leaked state |

Prioritize assertions by evidence strength: **Job/Step status → skip/retry/filter counters → DB/file output → contract-level mock interactions**. Depending on the domain, add audit, metric, tracing, and downstream READY-status checks.

## 17. Pitfalls to Avoid

**Mocking the processor directly instead of the external client.** Doing so bypasses the very logic under test: response mapping, filtering, retry/skip, and write decisions. Place mocks at the external service boundary when testing Batch.

**Calling the processor manually and claiming Batch works.** Processor unit tests are necessary, but they do not verify chunk transactions, `StepExecution`, checkpoints, restarts, `skipLimit`, or Job flows. Write integration tests with `JobLauncherTestUtils` for those.

**Mocking all of JDBC and JobRepository.** This strips tests of signals about transactions and committed data. For integration tests, use a test database with real transaction semantics.

**Retrying or skipping every 4xx/5xx.** HTTP status codes are technical signals; retryability depends on API contract, idempotency, and business semantics.

**Returning responses based on call order in parallel Steps.** Non-deterministic order creates flaky tests. Key responses by request argument and use thread-safe counters if needed.

**Skipping verification of actual outputs.** Mockito verification can pass even when the writer drops records, writes the wrong customer, or duplicates rows. Reconcile the target dataset and field values.

**Confusing filter with skip.** Returning `null` from a processor is filtering; throwing a skippable exception is skipping. Outcomes and operational alerts differ substantially.

**Ignoring retries when the service has side effects.** Database transactions do not roll back external payments or processed API calls. Design idempotency keys, reconciliation, and tests for lost responses after success.

**Mocking HTTP while also injecting a mock of the adapter interface.** The stub server never receives requests because the HTTP adapter was replaced. Keep clear which component is real and which is mocked at each test boundary.

**Running tests against live endpoints.** This causes slowness, quota exhaustion, non-repeatable data, and risk of mutating state outside tests. Mock locally for deterministic cases; isolate real contract tests in a dedicated environment.

## 18. Putting It Together in a Reliable Test Infrastructure

For Spring Batch Core Processing, a solid external-service test infrastructure has three parts:

1. **A clean interface or adapter** separating external calls from ItemProcessor/ItemWriter.
2. **Deterministic fixtures and mocks** covering success, filtering, invalid responses, timeouts, retries, skip limits, and non-skippable errors.
3. **Evidence from Spring Batch and outputs** including JobExecution, StepExecution, target data, audit records, and duplicate-free restartability.

This structure tests the decisions that genuinely impact batch outcomes, reproduces external service failures on demand, and verifies that jobs only proceed or complete when outputs still satisfy the defined contract.
