# Adding Transient Error Retries in a Spring Batch Practice Project

## 1. Practice Objectives

In a **Spring Batch Core Processing** project, an order import job rarely just reads a file and writes to a database. It may also call external services for risk scores, exchange rates, customer details, or contract status. If that service occasionally times out or returns HTTP 503 due to brief overload, halting the whole job on the very first error may be unnecessary. Conversely, retrying infinitely or mistakenly retrying permanent errors wastes resources, misses deadlines, and can create duplicate side effects.

In **Practice Projects → Adding Transient Error Retries**, we build a job that reads CSV, calls **`CustomerRiskClient`** in the processor, and writes output via JDBC. Spring Batch will retry when the service throws an exception classified as **transient**, with an explicit **retry limit** and **backoff**. If the service recovers, the job continues; if attempts are exhausted, the job becomes `FAILED` instead of silently dropping the record.

~~~text
orders.csv
    |
    v
FlatFileItemReader
    |
    v
ItemProcessor ---------> CustomerRiskClient
    |                           |
    |                     risk-service HTTP
    |                           |
    |                   timeout / 429 / 503
    |                           |
    |                   RETRY + BACKOFF
    v
ItemWriter (JDBC)
    |
    v
enriched_order
~~~

After practicing, you should understand how to:

- Distinguish **transient** errors from **permanent** errors and data errors.
- Configure **`faultTolerant`**, **`retry`**, **`retryLimit`**, and **`backOffPolicy`**.
- Verify an item fails twice and succeeds on the third attempt.
- Verify sustained errors cause **`FAILED`** without publishing incomplete output.
- Understand how retry differs from **skip**, **filter**, **restart**, and transaction rollback.
- Ensure the writer and external side effects have an **idempotency** policy.
- Write Spring Batch tests, HTTP adapter tests, and collect logs/metrics at the right level.

The examples follow **Spring Batch 5+**, Java 17, JUnit 5, and Spring Boot style. Test annotation details and infrastructure configuration may vary by framework version; version-dependent parts will be noted.

## 2. What Is Retry?

Retry means **re-attempting an operation that failed but has a chance of recovering**, not re-running every exception indiscriminately regardless of cause.

Example:

~~~text
Attempt #1: call /risk/C001 -> timeout
                 |
               backoff
                 |
Attempt #2: call /risk/C001 -> HTTP 503
                 |
               backoff
                 |
Attempt #3: call /risk/C001 -> HTTP 200, score=35
                 |
                 v
          Processor succeeds
                 |
                 v
          Writer + chunk commit
~~~

With **`retryLimit(3)`** in this example, the **maximum number of attempts is three, including the initial attempt**. If the third attempt still throws a retryable error, the operation exhausts retries and the Step handles the error according to remaining policies; without a matching skip policy, the job typically becomes `FAILED`.

### Retry Is Not Skip or Restart

| Mechanism | Meaning | Example |
|---|---|---|
| Retry | Re-attempt a failed operation | HTTP 503 then 200 |
| Skip | Accept skipping an error item per policy | Malformed CSV row routed to rejects |
| Filter | Processor returns null per business rule | `CANCELLED` order does not need output |
| Fail | Cannot continue under current policy | API errors after all attempts |
| Restart | Create a new `JobExecution` for the same `FAILED`/`STOPPED` `JobInstance` when eligible | Resume from saved checkpoint |

Retries occur **within a single Step execution**; restarts occur after a previous `JobExecution` ended unsuccessfully or was stopped. A `JobInstance` can have multiple `JobExecution`s, but each processor retry **does not create a new `JobExecution`**.

## 3. Project Retry Policy

Assume `risk-service` returns an integer score from **0 to 100**. The job must write the validated score to the target table.

| Scenario | Classification | Handling |
|---|---|---|
| HTTP 200, valid score | Success | Write output |
| Transient connect/read timeout | Transient | Retry if replay is safe |
| HTTP 502/503/504 | Transient per API contract | Retry |
| HTTP 429 | Throttling | Retry with backoff and check `Retry-After` |
| HTTP 400/422 | Permanent | Fail or handle via business workflow; never retry blindly |
| HTTP 401/403 | Authentication/authorization | Fail and alert |
| HTTP 404 | Depends on contract | Do not retry by default |
| HTTP 200 missing score | Invalid response | Fail; do not accept a default score |
| Negative score or above 100 | Invalid business response | Fail or route to separate control workflow |
| Amount zero or negative | Input error | Do not retry hoping the amount will fix itself |
| `NullPointerException` | Programming bug | Do not retry broadly |

This lesson's policy:

1. **`TransientRiskServiceException`** is retried up to three times.
2. Use a **200 ms fixed backoff** in the demo.
3. **`PermanentRiskServiceException`** and **`InvalidOrderException`** are not retried.
4. Do not skip transient errors after exhausting retries; the Job ends as `FAILED` so orders are not lost.
5. The scoring API only reads data and produces no side effects on the service side.
6. Output must contain one row per valid order, reconciled by business key.

**200 ms is only a demo value.** Production should consider exponential backoff, jitter, timeouts, deadlines, `Retry-After`, and concurrency limits based on external service capacity.

## 4. Input Data and Target Table

Create **`orders.csv`**:

~~~csv
orderId,customerId,amount
O001,C001,120.00
O002,C002,50.00
O003,C003,80.50
O004,C004,25.00
~~~

Assume the service returns:

| Order | Customer | Score |
|---|---|---:|
| O001 | C001 | 35 |
| O002 | C002 | 10 |
| O003 | C003 | 60 |
| O004 | C004 | 20 |

Target table:

~~~sql
CREATE TABLE enriched_order (
    batch_id     VARCHAR(64) NOT NULL,
    order_id     VARCHAR(64) NOT NULL,
    customer_id  VARCHAR(64) NOT NULL,
    amount       DECIMAL(18, 2) NOT NULL,
    risk_score   INTEGER NOT NULL,
    PRIMARY KEY (batch_id, order_id)
);
~~~

**`batchId`** is the business batch identifier, not `JobExecutionId`. When the job restarts the same `JobInstance`, previously committed output must still be considered under the same `batchId`. The primary key helps prevent physical duplicates, but if the writer still uses plain `INSERT`, replaying an existing record can trigger a constraint violation; that alone **is not complete idempotency**.

The Job accepts two important `JobParameters`:

- **`inputFile`**: path to the input snapshot, immutable across a `JobInstance`.
- **`batchId`**: business key for writing and reconciling output.

In independent tests you can add a random **`testRunId`** to create a new `JobInstance`. When restarting, **never change identifying parameters**.

## 5. Dependencies and Infrastructure

For a Spring Boot application with proper dependency management, illustrative Gradle dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'com.h2database:h2'
}
~~~

Spring Batch uses retry infrastructure compatible with the Spring Retry version in the dependency graph. Never arbitrarily add a Spring Retry version that differs from the project's dependency management.

`JobRepository` needs the Spring Batch metadata schema; the business datasource has the **`enriched_order`** table. In the demo, a single datasource can be used with a consistently configured **`PlatformTransactionManager`** so the JDBC writer and chunk checkpoints have the expected transaction semantics. Production needs real database drivers, pooling, credentials, and timeouts.

## 6. Models, Interfaces, and Exceptions

Place each class/record below in a Java file matching the project package.

~~~java
package com.example.batch.orders;

import java.math.BigDecimal;

public record RawOrder(
        String orderId,
        String customerId,
        BigDecimal amount) {
}
~~~

~~~java
package com.example.batch.orders;

import java.math.BigDecimal;

public record EnrichedOrder(
        String orderId,
        String customerId,
        BigDecimal amount,
        int riskScore) {
}
~~~

~~~java
package com.example.batch.risk;

public interface CustomerRiskClient {
    int scoreFor(String customerId);
}
~~~

Retryable exception:

~~~java
package com.example.batch.risk;

public class TransientRiskServiceException
        extends RuntimeException {

    public TransientRiskServiceException(String message) {
        super(message);
    }

    public TransientRiskServiceException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Non-retryable exceptions:

~~~java
package com.example.batch.risk;

public class PermanentRiskServiceException
        extends RuntimeException {

    public PermanentRiskServiceException(String message) {
        super(message);
    }

    public PermanentRiskServiceException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

~~~java
package com.example.batch.orders;

public class InvalidOrderException extends RuntimeException {

    public InvalidOrderException(String reasonCode) {
        super(reasonCode);
    }
}
~~~

Rather than letting the processor parse every HTTP status itself, the **`CustomerRiskClient`** adapter translates technical errors into contractual exceptions. The Step only retries the class meant for retrying.

Do not put access tokens, raw responses, emails, or full request bodies into exception messages. Exceptions may be logged or stored in metadata; prefer a **fixed reason code** and a safe correlation ID.

## 7. Reader: Reading CSV Line by Line

~~~java
package com.example.batch.config;

import com.example.batch.orders.RawOrder;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;

@Configuration
public class OrderReaderConfiguration {

    @Bean
    @StepScope
    public FlatFileItemReader<RawOrder> orderReader(
            @Value("#{jobParameters['inputFile']}") String inputFile) {

        return new FlatFileItemReaderBuilder<RawOrder>()
                .name("retryPracticeOrderReader")
                .resource(new FileSystemResource(inputFile))
                .linesToSkip(1)
                .delimited()
                .names("orderId", "customerId", "amount")
                .fieldSetMapper(fields -> new RawOrder(
                        fields.readString("orderId"),
                        fields.readString("customerId"),
                        fields.readBigDecimal("amount")))
                .saveState(true)
                .build();
    }
}
~~~

**`@StepScope`** resolves the path when the Step runs, avoiding sharing a stateful reader across multiple executions. **`saveState(true)`** allows the reader to persist progress in `ExecutionContext` at appropriate checkpoints.

The reader reads line by line rather than loading the entire file into a `List`. A parse error on one line generally does not self-heal by re-reading the exact same line, so **do not retry every `FlatFileParseException`** in this lesson.

## 8. Processor: Enriching with Risk Scores

~~~java
package com.example.batch.config;

import com.example.batch.orders.EnrichedOrder;
import com.example.batch.orders.InvalidOrderException;
import com.example.batch.orders.RawOrder;
import com.example.batch.risk.CustomerRiskClient;
import com.example.batch.risk.PermanentRiskServiceException;
import java.math.BigDecimal;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderProcessorConfiguration {

    @Bean
    public ItemProcessor<RawOrder, EnrichedOrder> riskProcessor(
            CustomerRiskClient riskClient) {

        return order -> {
            if (order.amount() == null
                    || order.amount().compareTo(BigDecimal.ZERO) <= 0) {
                throw new InvalidOrderException("INVALID_AMOUNT");
            }

            int score = riskClient.scoreFor(order.customerId());

            if (score < 0 || score > 100) {
                throw new PermanentRiskServiceException(
                        "INVALID_RISK_SCORE");
            }

            return new EnrichedOrder(
                    order.orderId(),
                    order.customerId(),
                    order.amount(),
                    score);
        };
    }
}
~~~

The processor knows nothing about HTTP URLs, auth headers, or `RestClient` exceptions; it uses only the interface. **Retry configuration on the Step** decides whether to re-invoke the processor after a classified error.

In the demo, `CustomerRiskClient` is a read operation. If replaced by a **payment-creation or reservation** API, retries need an idempotency key/receipt to avoid creating duplicate side effects if the previous attempt's response was lost.

### Avoid Swallowing Errors to Return a Default Value

Anti-pattern:

~~~java
try {
    return riskClient.scoreFor(customerId);
} catch (Exception ignored) {
    return 0; // Unsafe: turns a network error into a valid score.
}
~~~

If `score=0` is a valid value, the job can write wrong results and still report `COMPLETED`. Transient errors must go through the retry/failure policy instead of being masked by a default value.

## 9. Writer: Writing Output by `batchId`

~~~java
package com.example.batch.config;

import com.example.batch.orders.EnrichedOrder;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.ItemWriter;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;

@Configuration
public class OrderWriterConfiguration {

    @Bean
    @StepScope
    public ItemWriter<EnrichedOrder> orderWriter(
            JdbcTemplate jdbcTemplate,
            @Value("#{jobParameters['batchId']}") String batchId) {

        return chunk -> {
            for (EnrichedOrder order : chunk) {
                jdbcTemplate.update(
                        """
                        INSERT INTO enriched_order
                          (batch_id, order_id, customer_id,
                           amount, risk_score)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        batchId,
                        order.orderId(),
                        order.customerId(),
                        order.amount(),
                        order.riskScore());
            }
        };
    }
}
~~~

The writer participates in the Step's transaction if the datasource and transaction manager are configured accordingly. A successful JDBC update return **does not prove the chunk has committed**: commit happens after the writer.

Given retry/restart risks, plain `INSERT` is insufficient for every scenario. Production systems need stable business keys, merge/upsert/reconciliation, and handling for cases where commit succeeded yet the checkpoint failed to update due to a crash.

## 10. Configuring the Fault-Tolerant Step

Core section: declare **`retry(TransientRiskServiceException.class)`**, attempt limits, and backoff.

~~~java
package com.example.batch.config;

import com.example.batch.orders.EnrichedOrder;
import com.example.batch.orders.RawOrder;
import com.example.batch.risk.TransientRiskServiceException;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.retry.backoff.FixedBackOffPolicy;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class RetryPracticeJobConfiguration {

    @Bean
    public Step enrichOrdersStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            FlatFileItemReader<RawOrder> orderReader,
            ItemProcessor<RawOrder, EnrichedOrder> riskProcessor,
            ItemWriter<EnrichedOrder> orderWriter) {

        FixedBackOffPolicy backOff = new FixedBackOffPolicy();
        backOff.setBackOffPeriod(200L);

        return new StepBuilder("enrichOrdersStep", jobRepository)
                .<RawOrder, EnrichedOrder>chunk(2, transactionManager)
                .reader(orderReader)
                .processor(riskProcessor)
                .writer(orderWriter)
                .faultTolerant()
                .retry(TransientRiskServiceException.class)
                .retryLimit(3)
                .backOffPolicy(backOff)
                .build();
    }

    @Bean
    public Job importOrdersJob(
            JobRepository jobRepository, Step enrichOrdersStep) {

        return new JobBuilder("importOrdersJob", jobRepository)
                .start(enrichOrdersStep)
                .build();
    }
}
~~~

| Component | Meaning |
|---|---|
| **`chunk(2, transactionManager)`** | Two-item commit interval in the demo |
| **`faultTolerant()`** | Enables fault tolerance on the chunk Step |
| **`retry(TransientRiskServiceException.class)`** | Only this class is retryable |
| **`retryLimit(3)`** | Maximum of three attempts, including the initial attempt |
| **`backOffPolicy(backOff)`** | Delays between attempts per policy |
| No skip configured for transient | Exhausting retries marks Step `FAILED` instead of dropping records |

For errors in the processor, Spring Batch can re-attempt item processing per the retry policy. For writer errors, chunk rollbacks, or commit failures, actual invocation counts may differ due to how the Step recovers transactions. Never assume every commit-stage exception is retried with the exact same semantics as the processor.

### Distinguishing Two Retries from Three Attempts

~~~text
Attempt 1 -> transient failure
      | 200 ms
Attempt 2 -> transient failure
      | 200 ms
Attempt 3 -> success or exhausted
~~~

The two illustrated pauses total around 400 ms, excluding request execution time, commits, scheduling, and error handling.

## 11. Writing an Error-Classifying HTTP Adapter

In production, `CustomerRiskClient` can be implemented using Spring Framework 6.1+ **`RestClient`**. The adapter translates HTTP/network errors into business exceptions matching the Step's retry policy.

~~~java
package com.example.batch.risk;

import org.springframework.stereotype.Component;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;

@Component
public class HttpCustomerRiskClient implements CustomerRiskClient {

    private final RestClient restClient;

    public HttpCustomerRiskClient(RestClient restClient) {
        this.restClient = restClient;
    }

    @Override
    public int scoreFor(String customerId) {
        try {
            RiskResponse response = restClient.get()
                    .uri("/risk/{customerId}", customerId)
                    .retrieve()
                    .body(RiskResponse.class);

            if (response == null || response.score() == null) {
                throw new PermanentRiskServiceException(
                        "RISK_RESPONSE_MISSING_SCORE");
            }
            return response.score();

        } catch (RestClientResponseException error) {
            int status = error.getStatusCode().value();

            if (status == 429 || status == 502
                    || status == 503 || status == 504) {
                throw new TransientRiskServiceException(
                        "RISK_TEMPORARY_UNAVAILABLE", error);
            }

            throw new PermanentRiskServiceException(
                    "RISK_HTTP_ERROR_" + status, error);

        } catch (ResourceAccessException error) {
            throw new TransientRiskServiceException(
                    "RISK_NETWORK_FAILURE", error);
        }
    }

    public record RiskResponse(Integer score) {
    }
}
~~~

Successful response per assumed contract:

~~~json
{"score":35}
~~~

Base URL can be configured via `Environment`:

~~~java
package com.example.batch.config;

import java.util.Objects;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.web.client.RestClient;

@Configuration
public class RiskClientConfiguration {

    @Bean
    public RestClient riskRestClient(
            RestClient.Builder builder,
            Environment environment) {

        String baseUrl = Objects.requireNonNull(
                environment.getProperty("risk.base-url"),
                "risk.base-url must be configured");
        return builder.baseUrl(baseUrl).build();
    }
}
~~~

Example `application.yml`:

~~~yaml
risk:
  base-url: https://risk-service.internal.example
~~~

In production, configure **connect timeout, read/response timeout**, credential providers, and connection pooling via an appropriate HTTP client/request factory. Retries only happen after an attempt fails; an indefinitely hanging request is not fixed by `retryLimit`.

### Do Not Classify Solely by a Rigid Status Code Table

The adapter snippet is an **illustrative rule set for the `risk-service` API**. A 429 may carry a **`Retry-After`** header; a fixed 200 ms backoff is not always appropriate. Some APIs treat 404 as permanently not found, while others treat it as an eventual-consistency state. `ResourceAccessException` is sometimes a non-self-healing DNS/certificate error; analyze the cause and contract before retrying.

HTTP 401/403 must fail and alert instead of retrying a bad token thousands of times. Response bodies or exception messages may contain PII/secrets; logs should record **`failureCategory`** and HTTP status instead of raw bodies.

## 12. Backoff and Avoiding Retry Storms

If hundreds of jobs or partitions receive 503 and immediately retry, an already overloaded service can struggle even harder to recover.

**Fixed backoff**:

~~~text
Attempt 1 --200ms--> Attempt 2 --200ms--> Attempt 3
~~~

**Exponential backoff**:

~~~text
Attempt 1 --200ms--> Attempt 2 --400ms--> Attempt 3
~~~

**Jitter** adds bounded random variation so multiple workers do not re-call at the exact same instant.

Example changing the policy in the Step:

~~~java
import org.springframework.retry.backoff.ExponentialBackOffPolicy;

ExponentialBackOffPolicy backOff =
        new ExponentialBackOffPolicy();
backOff.setInitialInterval(200L);
backOff.setMultiplier(2.0);
backOff.setMaxInterval(3000L);

// Then use:
// .backOffPolicy(backOff)
~~~

With `retryLimit=3` there are at most two pauses between three attempts. To meet SLAs, control **total elapsed time** across response timeouts, backoff, and chunk processing.

If the HTTP client retries three attempts itself and Spring Batch also retries three attempts, one item can generate around **nine requests**, not counting gateways/service meshes. The design must specify which layer owns retries and the maximum total requests.

### Do Not Solve Every Problem with a Large `retryLimit`

An overly high `retryLimit` can:

- Prolong transactions or `JobExecution`s.
- Hold database connections and thread resources.
- Increase traffic to an overloaded dependency.
- Repeat side effects if requests are not idempotent.
- Cause batches to miss deadlines without a clear failure signal.

During prolonged service outages, controlled failure, a circuit breaker, or waiting for scheduler restart after upstream recovery may be more suitable.

## 13. Running with Four Orders

Have the mock/client return:

~~~text
C001 -> score 35 immediately
C002 -> timeout, HTTP 503, score 10
C003 -> score 60 immediately
C004 -> score 20 immediately
~~~

Expected flow with chunk size two:

~~~text
Chunk #1:
  O001: risk score 35
  O002: attempt 1 timeout
        attempt 2 HTTP 503
        attempt 3 score 10
  Writer: O001 + O002
  Commit

Chunk #2:
  O003: risk score 60
  O004: risk score 20
  Writer: O003 + O004
  Commit

Job status: COMPLETED
~~~

For the illustrative pipeline without filtering/skipping:

| Metric | Expected |
|---|---:|
| readCount | 4 |
| writeCount | 4 |
| processSkipCount | 0 |
| writeSkipCount | 0 |
| filterCount | 0 |
| Batch rows | 4 |
| Unique business keys | 4 |
| Job status | COMPLETED |

Do not look only at read/write counts or mock invocation counts. Query the output to confirm each order has one record with the right score and amount.

## 14. Integration Testing with JUnit 5 and Mockito

Spring Batch Test lets you run the **real Job** via `JobLauncherTestUtils` inside the Spring context. We replace **`CustomerRiskClient`** with a mock so transient errors occur deterministically without network calls.

Environment prerequisites:

1. Job, Step, reader, processor, and writer beans are registered.
2. A dedicated test database has the `JobRepository` schema.
3. The output table is created before running tests.
4. Spring Boot does not auto-run the Job at context startup.
5. Only one Job is selected or the Job is explicitly configured for `JobLauncherTestUtils`.

With Spring Boot 3.4+/Spring Framework 6.2+, you can use **`@MockitoBean`**; older Boot projects typically use **`@MockBean`** for their version.

~~~java
package com.example.batch;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;

import com.example.batch.risk.CustomerRiskClient;
import com.example.batch.risk.PermanentRiskServiceException;
import com.example.batch.risk.TransientRiskServiceException;
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
@SpringBootTest(properties = {
        "spring.batch.job.enabled=false",
        "spring.batch.jdbc.initialize-schema=always",
        "spring.datasource.url=jdbc:h2:mem:retrytest;DB_CLOSE_DELAY=-1"
})
class RiskRetryBatchIT {

    @MockitoBean
    CustomerRiskClient riskClient;

    @Autowired
    JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @TempDir
    Path tempDir;

    @BeforeEach
    void prepareDatabase() {
        jdbcTemplate.execute(
                """
                CREATE TABLE IF NOT EXISTS enriched_order (
                    batch_id VARCHAR(64) NOT NULL,
                    order_id VARCHAR(64) NOT NULL,
                    customer_id VARCHAR(64) NOT NULL,
                    amount DECIMAL(18, 2) NOT NULL,
                    risk_score INTEGER NOT NULL,
                    PRIMARY KEY (batch_id, order_id)
                )
                """);

        // Use only a dedicated test database.
        jdbcTemplate.update("DELETE FROM enriched_order");
    }

    @Test
    void retriesTwiceAndThenWritesOneRecord()
            throws Exception {

        when(riskClient.scoreFor("C001"))
                .thenThrow(new TransientRiskServiceException(
                        "TEMPORARY_TIMEOUT"))
                .thenThrow(new TransientRiskServiceException(
                        "TEMPORARY_503"))
                .thenReturn(35);

        JobExecution execution =
                launchOne("B-RETRY-SUCCESS", "O001", "C001");

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        verify(riskClient, times(3)).scoreFor("C001");

        StepExecution step = execution.getStepExecutions().stream()
                .filter(e -> "enrichOrdersStep".equals(e.getStepName()))
                .findFirst()
                .orElseThrow();

        assertEquals(1L, step.getReadCount());
        assertEquals(1L, step.getWriteCount());
        assertEquals(0L, step.getProcessSkipCount());

        Long rows = jdbcTemplate.queryForObject(
                """
                SELECT COUNT(*) FROM enriched_order
                WHERE batch_id = ? AND order_id = ?
                """,
                Long.class,
                "B-RETRY-SUCCESS", "O001");
        assertEquals(1L, rows);

        Integer score = jdbcTemplate.queryForObject(
                """
                SELECT risk_score FROM enriched_order
                WHERE batch_id = ? AND order_id = ?
                """,
                Integer.class,
                "B-RETRY-SUCCESS", "O001");
        assertEquals(35, score);
    }

    @Test
    void failsAfterRetryLimitIsExhausted()
            throws Exception {

        when(riskClient.scoreFor("C002"))
                .thenThrow(new TransientRiskServiceException(
                        "STILL_UNAVAILABLE"));

        JobExecution execution =
                launchOne("B-RETRY-FAIL", "O002", "C002");

        assertEquals(BatchStatus.FAILED, execution.getStatus());
        verify(riskClient, times(3)).scoreFor("C002");

        Long rows = jdbcTemplate.queryForObject(
                """
                SELECT COUNT(*) FROM enriched_order
                WHERE batch_id = ?
                """,
                Long.class, "B-RETRY-FAIL");
        assertEquals(0L, rows);
    }

    @Test
    void doesNotRetryPermanentFailure()
            throws Exception {

        when(riskClient.scoreFor("C003"))
                .thenThrow(new PermanentRiskServiceException(
                        "RISK_HTTP_ERROR_400"));

        JobExecution execution =
                launchOne("B-PERMANENT", "O003", "C003");

        assertEquals(BatchStatus.FAILED, execution.getStatus());
        verify(riskClient, times(1)).scoreFor("C003");
    }

    private JobExecution launchOne(
            String batchId, String orderId, String customerId)
            throws Exception {

        Path input = tempDir.resolve(
                UUID.randomUUID() + "-orders.csv");
        Files.writeString(
                input,
                "orderId,customerId,amount\n"
                + orderId + "," + customerId + ",120.00\n",
                StandardCharsets.UTF_8);

        JobParameters params = new JobParametersBuilder()
                .addString("inputFile",
                        input.toAbsolutePath().toString())
                .addString("batchId", batchId)
                .addString("testRunId",
                        UUID.randomUUID().toString())
                .toJobParameters();

        return jobLauncherTestUtils.launchJob(params);
    }
}
~~~

**Proof scope:** The test runs the real Job/Step, mocks at the `RiskClient` interface, and uses a test DB for the writer. The **single-item, synchronous Step** scenario verifies `retryLimit=3` directly via invocation count.

For multi-step Jobs, configure `JobLauncherTestUtils` to target the right Job; with parallel tests, never wipe entire tables in a shared database. If frameworks/contexts reset mocks differently, reset mocks between tests so stubbing and interactions do not leak.

This test does not prove that the HTTP adapter builds URLs/JSON/headers properly; test the adapter separately using an HTTP stub.

### When Mock Invocation Counts Differ from Expectations

Check:

- Are there retries at the HTTP client or gateway layer?
- Did a writer/transaction rollback cause the processor to be re-invoked?
- Are multiple items/chunks being processed concurrently?
- Is the actual exception the exact class configured for retry?
- Is another `JobExecution` sharing the same mock or context?
- Did a wrapper layer convert the exception into another class?

Never increase `retryLimit` just to make a test pass without understanding why the request count changed.

## 15. Testing Two Items in One Chunk

Extend the fixture:

~~~csv
orderId,customerId,amount
O001,C001,120.00
O002,C002,50.00
~~~

Mock:

~~~java
when(riskClient.scoreFor("C001")).thenReturn(35);
when(riskClient.scoreFor("C002"))
        .thenThrow(new TransientRiskServiceException(
                "TEMPORARY_TIMEOUT"))
        .thenReturn(10);
~~~

Expected:

- Job `COMPLETED`.
- Both records **`O001`** and **`O002`** exist exactly once.
- Risk scores are 35 and 10 respectively, with accurate amounts.
- No items skipped.
- No uncommitted output published.

With writer/transaction errors, some items may be reprocessed; therefore, never treat method invocation counts as sole proof of output. **Reconciling final output** is always more important.

## 16. Testing the HTTP Adapter with a Mock Server

Mocking `CustomerRiskClient` isolates Batch logic well, yet does not verify the protocol. To verify the adapter, run **WireMock** or **MockWebServer** locally.

Assumed contract:

~~~http
GET /risk/C001 HTTP/1.1
Accept: application/json
~~~

First response:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json

{"code":"TEMPORARILY_UNAVAILABLE"}
~~~

Subsequent response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"score":35}
~~~

Stub scenarios to cover:

| Response / Scenario | What to Assert |
|---|---|
| HTTP 200, valid score | Parses score accurately |
| HTTP 503 | `TransientRiskServiceException` |
| HTTP 429 | Handles throttling/`Retry-After` per contract |
| HTTP 400 | `PermanentRiskServiceException` |
| HTTP 401/403 | Never retries blindly |
| HTTP 200 missing score | Rejects schema-invalid response |
| HTTP 200 score outside 0..100 | Processor reports permanent data error |
| Connect/read timeout | Bounded timeout and error mapping |
| Wrong URL/header/body | Stub mismatch fails test informatively |

In **HTTP adapter tests**, never also replace `CustomerRiskClient` with `@MockitoBean`, because requests then fail to go through the real HTTP client. Point the base URL to the mock server's **dynamic port**.

An end-to-end test can have the server return 503 then 200, run the real Job, and reconcile the output table for a single exact record. That confirms the link between HTTP adapter, exception mapping, and Step retry.

## 17. Transaction, Rollback, and Checkpoint

A processor retry typically happens before the writer, yet Spring Batch still organizes work around chunk transactions and fault-tolerant Step semantics:

~~~text
Chunk 1:
  O001 -> risk score 35
  O002 -> timeout -> retry -> risk score 10
  Writer INSERT O001, O002
  COMMIT, checkpoint

Chunk 2:
  O003 -> score 60
  Writer INSERT O003
  COMMIT -> connection error, outcome unclear
~~~

Not every exception occurring in transaction manager **`commit()`** is handled as a processor retry. The DB may have committed while the application lost acknowledgment, or metadata checkpoints may not have updated synchronously.

If business data and Batch metadata share **the same real datasource/transaction**, chunk commits help keep them more consistent. However, external APIs, files, Kafka, logs, and other resources do not automatically participate in that transaction.

Therefore:

- Never assume a finished writer call means the transaction committed.
- Never use `retry(Exception.class)` to handle indeterminate commit failures.
- Never treat `writeCount` as proof that all external outputs were persisted.
- On restart, reconcile by business key rather than trusting processed item counts alone.

## 18. Idempotency When Retrying Calls

In this lesson `RiskClient` only **reads** scores. That is a retry-friendly operation, yet even a read-only service can return different data across attempts or restarts.

~~~text
Attempt #1 -> timeout
Attempt #2 -> score 35
Next-day restart -> score 60
~~~

If the business requires batch-consistent results, you need **source snapshots, effective dates, scoring model versions, or controlled caching**. Repeatability is part of the data contract.

### Calls with Side Effects

Suppose `RiskClient` is replaced with `ReserveInventoryClient`:

~~~text
Batch sends POST reserve
       |
       v
Service created reservation R123
       |
       v
Response timed out
       |
       v
Batch retries POST reserve
~~~

If the second call creates a different reservation, retrying broke business correctness. You need a **stable idempotency key** by `batchId`/`orderId`/operation, an API supporting result lookup by key, and an appropriate key retention window.

~~~http
POST /reservations
Idempotency-Key: B42-O001-RESERVE
Content-Type: application/json

{"orderId":"O001","quantity":1}
~~~

Adding a header alone is not enough: the target service must commit to and enforce idempotency semantics. Otherwise, choose another workflow such as outbox, receipt lookup, or controlled compensation.

### Idempotency in the Writer

For JDBC, a typical replay policy is:

- Key absent -> `INSERT`.
- Key present and payload matches -> accept replay.
- Key present yet content differs -> report conflict, do not silently overwrite.

Illustrative PostgreSQL idea:

~~~sql
INSERT INTO enriched_order
    (batch_id, order_id, customer_id, amount, risk_score)
VALUES
    (:batchId, :orderId, :customerId, :amount, :riskScore)
ON CONFLICT (batch_id, order_id)
DO UPDATE SET amount = enriched_order.amount
WHERE enriched_order.customer_id = EXCLUDED.customer_id
  AND enriched_order.amount = EXCLUDED.amount
  AND enriched_order.risk_score = EXCLUDED.risk_score
RETURNING order_id;
~~~

If the key conflicts yet the payload differs, the `WHERE` condition fails and no row is returned; the application can classify the conflict. **No-op `UPDATE`s can fire triggers or create versions** depending on the database, so this illustrates the policy rather than optimal SQL for every engine. Other databases have different syntax.

## 19. Exhausted Retries: Fail or Skip?

In the basic lesson, exhausted retries lead to **`FAILED`**:

~~~text
Attempt #1 -> timeout
Attempt #2 -> timeout
Attempt #3 -> timeout
        |
        v
Retry exhausted
        |
        v
Step FAILED -> Job FAILED
~~~

Reason: the contract requires every valid order to have a risk score. If an item is auto-skipped after three timeouts and the job still finishes `COMPLETED`, output could miss records without downstream knowing.

In a **best-effort** system, skipping after retry can be allowed, provided you have:

1. An intentional skip limit.
2. A separate reject/quarantine store.
3. Auditing of `reasonCode` and `batchId`.
4. A workflow to replay skipped records.
5. Reconciliation of expected output under a partial-success policy.

Extension example to skip **invalid input errors**, independent of transient outages:

~~~java
.faultTolerant()
.retry(TransientRiskServiceException.class)
.retryLimit(3)
.skip(InvalidOrderException.class)
.skipLimit(2)
~~~

**`skipLimit` is not `retryLimit`.** Skips count excluded items, not how many times an item was retried before succeeding. Avoid `skip(Exception.class)` because it can mask DB, auth, or code bugs.

## 20. Restart When a Dependency Recovers

If a service outage lasts longer than `retryLimit`, the `JobExecution` may become `FAILED`. Once the service returns, the Job can restart the same `JobInstance` from checkpoints if conditions are met.

~~~text
JobInstance importOrdersJob(batchId=B42, inputFile=...)
       |
       +-- JobExecution #900: FAILED
        |      Chunk 1 committed
       |      Chunk 2 retry exhausted
       |
       +-- JobExecution #908: restart
               Restores checkpoint
               Resumes processing
              COMPLETED
~~~

Example:

~~~java
long failedExecutionId = 900L;

// jobOperator is injected; restart only when execution is eligible.
Long restartedExecutionId =
        jobOperator.restart(failedExecutionId);
~~~

Key points:

- Never add a random identifying parameter to pass off a new run as a restart.
- Never edit the input file when the reader checkpoints by position.
- Never assume items committed in the previous execution appear in the new execution's `writeCount`.
- Never start a second execution before confirming the old execution finished and no worker is still writing.
- Have an idempotent writer or reconciliation for replays after uncertain-outcome commits.

### Restart Test Scenario

1. Six-item input, chunk size two.
2. First two items succeed and commit.
3. Third item throws transient exception three times; Job becomes `FAILED`.
4. Verify first chunk's output was saved.
5. Change mock behavior so the third item returns a valid score.
6. Use `JobOperator.restart` with the `FAILED` execution ID.
7. Verify the new `JobExecution` is `COMPLETED` and final output has all six business keys.
8. Verify no missing/duplicate rows and accurate written values.

Combining results across multiple `JobExecution`s belonging to the same `JobInstance` is a key part of recovery testing.

## 21. Observing Retries in Logs and Metrics

A Job may ultimately finish `COMPLETED`, yet having to retry thousands of times increases duration and signals an unstable dependency.

Recommended metrics:

| Metric | Purpose |
|---|---|
| Retry attempts | Retry counts per dependency |
| Retry exhausted | Counts of exhausting the retry limit |
| Dependency error rate | Rate of 429/502/503/504/timeouts |
| Dependency latency | Request duration distribution |
| Job/Step duration | Impact on deadlines |
| read/write/skip counts | Data processing health |
| rollbackCount | Rollback counts |
| last successful batch | Tracking published results |

Safe structured log example:

~~~text
event=external.retry
jobExecutionId=900
stepName=enrichOrdersStep
dependency=risk-service
failureCategory=HTTP_503
attempt=2
maxAttempts=3

event=external.retry.exhausted
jobExecutionId=900
dependency=risk-service
failureCategory=TEMPORARY_UNAVAILABLE
~~~

This is an illustrative schema. When exact Step attempts are needed, use instrumentation suited to Spring Batch's retry mechanism (such as `RetryListener`) or the adapter, while distinguishing **HTTP request attempts**, **Step retries**, and **processor re-invocations due to rollback**.

Do not attach `customerId`, `orderId`, or `jobExecutionId` as high-cardinality Prometheus labels; dynamic IDs belong in logs/traces/audits, whereas metrics should use `jobName`, `stepName`, `dependency`, `outcome`, and failure category. Never write raw responses, `Authorization` headers, or PII into retry logs.

### Alerts Worth Tracking

- Sudden spike in exhausted retries.
- Sustained high HTTP 429/503 rates.
- Increasing Job duration despite unchanged input volume.
- Step `STARTED` with no chunk progress.
- No `READY` batch before deadline.

Depending on workload, set thresholds to avoid paging on a single self-recovered timeout.

## 22. Multiple Threads and Partitions Can Create a Retry Storm

A job with four partitions:

~~~text
Partition A -> retry C001
Partition B -> retry C201
Partition C -> retry C401
Partition D -> retry C601
~~~

Each worker has `retryLimit=3`, yet total requests can surge rapidly. With 100 partitions, a brief outage can emit hundreds of simultaneous retries.

Mitigations:

- Backoff with jitter.
- Rate limiting / capping total concurrency to the dependency.
- Overall timeout per item/request.
- Circuit breaker for prolonged outages.
- Bounded queues and worker pools.
- Monitoring total requests, not just per-item retry counts.
- Ensuring reader/writer and retry state are compatible with the execution model.

In multi-threaded tests, stub responses **by `customerId` or request key** rather than relying on global call order. Avoid non-thread-safe static mutable counters.

## 23. Common Mistakes

**Retrying every `RuntimeException`.** Validation errors, code bugs, or auth errors do not self-heal in a few hundred milliseconds.

**Confusing `retryLimit` with extra retry count.** `retryLimit(3)` grants at most three attempts total, including the initial attempt.

**Not setting HTTP timeouts.** An indefinitely hanging attempt prevents retries from ever starting.

**Zero backoff with many workers.** Easily triggers a retry storm.

**Two or three layers all retrying.** Total requests can multiply uncontrollably.

**Returning a default score when the service fails.** Causes the job to write wrong data while reporting success.

**Using retries on side-effecting APIs without idempotency.** Causes duplicate transactions or notifications.

**Assuming DB transactions roll back HTTP/Kafka.** There is no automatic distributed transaction.

**Skipping transient outages after retries exhaust without a contract.** Silently causes missing records.

**Creating a new `JobInstance` when intending to restart.** Can re-read the entire file.

**Editing input between two executions.** Positional checkpoints may become invalid.

**Trusting `writeCount` instead of reconciling the database.** A writer call does not necessarily equal durable external output.

**Retrying commit errors with unknown outcome.** Commit may have succeeded while the ACK was lost; must reconcile.

**Asserting mock call counts across complex transactions.** Rollbacks and concurrency can trigger extra invocations.

**Not monitoring retry rates.** The job still finishes `COMPLETED`, yet the service is near overload.

**Logging raw requests/responses during debugging.** Risks leaking tokens, PII, and business data.

## 24. Extension Exercises

### A. Exponential Backoff

Replace fixed backoff with exponential backoff and a max interval. Test two failures followed by success; avoid asserting exact millisecond timings on CI. For rate limiting, consider jitter.

### B. HTTP 429 and `Retry-After`

Mock the server returning 429 with `Retry-After` followed by 200. The adapter must classify throttling and apply the contractual delay; the Step completes with one output without generating excessive requests.

### C. HTTP 400 Must Not Be Retried

Mock HTTP 400 and verify the adapter throws `PermanentRiskServiceException`; the Step becomes `FAILED` immediately per policy without calling HTTP three times.

### D. Restart After Exhausted Retries

Six-record file, chunk size two, error in the second chunk. First run `FAILED`, second run restarts the right `JobInstance` and `COMPLETED`. Reconcile output for all six keys with no duplicates.

### E. Side-Effecting API

Replace `RiskClient` with `ReserveInventoryClient`. Simulate the service creating a reservation successfully while the response times out. Retrying with the same idempotency key must return the same reservation instead of creating a new one.

### F. Multi-Worker Test

Run partitioning with mocks keyed by request; verify global rate limits and timeouts, ensuring retry state does not bleed across partitions.

## 25. Project Acceptance Criteria

| Item | Required Evidence |
|---|---|
| Exception taxonomy | Separates transient, permanent, and invalid input |
| Retry Step | `faultTolerant`, retries right class, bounded `retryLimit` |
| Backoff | Explicit delay, prevents bursty retries |
| Third-attempt recovery | Job `COMPLETED`, one accurate output record |
| Exhausted retries | Job `FAILED`, no false completion report |
| Permanent errors | Never retried blindly |
| Output | Key/amount/score accurate, no duplicates |
| Tests | Scoped Mockito Job tests and HTTP adapter tests |
| Transactions | Understands commits, checkpoints, and replay |
| Restarts | Same `JobInstance`, stable input snapshot |
| Side effects | Idempotency or appropriate reconciliation mechanism |
| Observability | Distinguishes attempts, exhausted, and status |

Adding a single retry configuration does not automatically make batch processing reliable. Retries are genuinely valuable only when **exceptions are properly classified, attempts and backoffs are bounded, replays are safe, Job status is faithfully reflected, and final output is reconciled**. Applying those principles enables Spring Batch to weather transient external service outages without turning them into missing data, retry storms, or duplicate side effects.
