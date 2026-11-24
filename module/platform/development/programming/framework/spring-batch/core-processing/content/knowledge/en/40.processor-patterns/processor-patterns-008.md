# Processor calling a remote service

In Spring Batch, `ItemProcessor` is typically responsible for transforming, enriching, or validating each item before the item is written to the destination. A common case is when the processor needs to call a remote service to fetch additional data or verify information. For example, when processing orders, the processor may call a Customer API to retrieve the customer segment and then produce an enriched record.

This pattern is useful when the processing result of an item depends on external data. However, every network call introduces latency and can fail independently of the batch job's transaction. Therefore, it is necessary to clearly design responsibility boundaries, error policies, repeatability, and load limits.

## 1. Where does the remote service sit in the processing flow?

In a chunk-oriented step, the basic flow is:

```text
ItemReader
    |
    v
 ItemProcessor -----> Remote service
    |                    |
    |<--- data ----------+
    v
 ItemWriter
    |
    v
 Destination storage
```

`ItemReader` reads the input item. `ItemProcessor<I, O>` receives an item of type `I`, executes business logic, and returns an item of type `O`. `ItemWriter` writes the output items in chunks.

The processor can perform one of the following behaviors:

- Transform the input item into a different output data type.
- Call a service to supplement missing data, then create an enriched item.
- Call a service to check a business condition before letting the item proceed.
- Return `null` to filter the item out of the write stream.
- Throw an exception when the item cannot be processed according to the defined rules.

For example, `Order` only has `customerId`, while the Customer API returns the customer name and segment. The processor combines both data sources to create `EnrichedOrder`.

You should place the remote call in the processor when the returned data directly participates in the transformation or processing decision of the item. If the primary task is reading data from an external source, consider an appropriate reader. If the task is sending a command or creating an external side effect, carefully consider repeatability and consider placing the intent recording in the writer or an outbox.

## 2. Separating batch logic from HTTP details

The processor should depend on an interface describing the business need, such as `CustomerProfileClient`. The adapter implementing that interface is responsible for making the HTTP call, mapping the response, and translating technical errors into exceptions that are meaningful to the application.

This separation makes the processor easy to test, while also allowing you to change the HTTP library or endpoint without modifying the batch processing logic.

```java
public interface CustomerProfileClient {
    CustomerProfile findById(String customerId);
}
```

Illustrative data types:

```java
public record Order(
        String id,
        String customerId,
        BigDecimal total
) {}

public record CustomerProfile(
        String customerId,
        String segment
) {}

public record EnrichedOrder(
        String orderId,
        String customerId,
        String customerSegment,
        BigDecimal total
) {}
```

The processor focuses solely on transformation rules:

```java
import org.springframework.batch.item.ItemProcessor;
import org.springframework.stereotype.Component;

@Component
public class CustomerEnrichmentProcessor
        implements ItemProcessor<Order, EnrichedOrder> {

    private final CustomerProfileClient customerProfileClient;

    public CustomerEnrichmentProcessor(
            CustomerProfileClient customerProfileClient) {
        this.customerProfileClient = customerProfileClient;
    }

    @Override
    public EnrichedOrder process(Order order) {
        CustomerProfile profile = customerProfileClient
                .findById(order.customerId());

        if (profile == null) {
            throw new CustomerNotFoundException(order.customerId());
        }

        return new EnrichedOrder(
                order.id(),
                order.customerId(),
                profile.segment(),
                order.total()
        );
    }
}
```

`CustomerNotFoundException` here is a business exception defined by the application. The application needs to decide whether not finding a customer will fail the job, be skipped according to policy, or be handled by another business branch. Do not silently generate default data if that value could corrupt the results.

## 3. Implementing the HTTP client

With Spring Framework 6.1 and later, `RestClient` can be used for synchronous HTTP calls. The adapter example below calls the customer lookup endpoint:

```java
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class RestCustomerProfileClient implements CustomerProfileClient {

    private final RestClient restClient;

    public RestCustomerProfileClient(RestClient customerRestClient) {
        this.restClient = customerRestClient;
    }

    @Override
    public CustomerProfile findById(String customerId) {
        return restClient.get()
                .uri("/customers/{id}", customerId)
                .retrieve()
                .body(CustomerProfile.class);
    }
}
```

Register a `RestClient` bean with the base URL loaded from environment configuration:

```java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@ConfigurationProperties(prefix = "integration.customer")
record CustomerApiProperties(String baseUrl) {}

@Configuration
@EnableConfigurationProperties(CustomerApiProperties.class)
class CustomerApiConfiguration {

    @Bean
    RestClient customerRestClient(
            RestClient.Builder builder,
            CustomerApiProperties properties) {
        return builder
                .baseUrl(properties.baseUrl())
                .build();
    }
}
```

Example configuration:

```yaml
integration:
  customer:
    base-url: https://customer-api.example.internal
```

Actual URLs, authentication credentials, and timeout configurations should be managed per deployment environment. Do not hardcode tokens or passwords in source code. Both connection timeout and response timeout must be configured using an appropriate request factory; the exact configuration API names depend on the Spring version and HTTP client being used.

`RestClient` is suitable for Spring Framework 6.1+ (commonly included in Spring Boot 3.2+). For applications using older versions, `RestTemplate` or another project-standardized client can be used. Regardless of which library is used, the business interface of the client can remain unchanged.

## 4. Handling errors based on the nature of the response

Not all remote service errors should be handled the same way. Before configuring retry or skip, classify errors by their recoverability and business meaning.

| Situation | Typically appropriate handling |
|---|---|
| Connection error, transient timeout | Can be retried with a limit and backoff |
| HTTP 5xx | Usually a transient error; retry with a limit if the operation is safe to repeat |
| HTTP 429 | Respect `Retry-After` if present, reduce call rate, and apply backoff |
| HTTP 408 | Can be retried if the request can be safely re-executed |
| HTTP 400 or 422 due to invalid data | Usually do not retry; fix the data or handle according to business policy |
| HTTP 401 or 403 | Check authentication and permission configuration; continuous retries usually do not help |
| HTTP 404 | Determine whether this is valid non-existent data, a skippable case, or an error that must stop the job |

HTTP status codes are only classification hints. The final decision must be based on the remote API's contract. For instance, one API might use 404 to indicate a normal business state, while another treats it as a critical data error.

The adapter should translate HTTP errors into meaningful exceptions such as `TemporaryRemoteServiceException`, `RemoteAuthenticationException`, or `CustomerNotFoundException`. As a result, the step's fault-tolerance configuration does not depend on HTTP library details.

Avoid retrying every `Exception`. Retrying data errors, authentication errors, or programming errors only slows down the job and can put extra load on the service.

## 5. Configuring retry and skip in a step

Spring Batch supports fault-tolerant steps to specify which exceptions are retried and which are skipped. The following example illustrates configuration using the Spring Batch 5 API:

```java
@Bean
Step enrichOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, EnrichedOrder> processor,
        ItemWriter<EnrichedOrder> writer) {

    return new StepBuilder("enrichOrders", jobRepository)
            .<Order, EnrichedOrder>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .retry(TemporaryRemoteServiceException.class)
            .retryLimit(3)
            .skip(CustomerNotFoundException.class)
            .skipLimit(100)
            .build();
}
```

In this example:

- Transient remote service errors are retried within the configured limit.
- Missing customer cases are skipped, though the number of skipped items remains bounded.
- If the skip limit is exceeded or an exception without an appropriate handling policy is encountered, the step may fail.

Only skip when dropping an item is an acceptable business decision. If dropping an order could cause financial discrepancies or lose critical data, you should stop the job or route the item into a separate error-handling workflow.

Retries should be accompanied by backoff, typically exponential backoff with jitter and a maximum time cap. For HTTP 429, respect the wait time requested by the server whenever possible. Limit retry attempts so a failing service does not cause the batch job to send requests continuously.

## 6. Transactions, retries, and repeatability

This is the most critical point when a processor calls a remote service. A chunk transaction typically manages changes in resources supported by the transaction manager, such as the target database. A regular HTTP call does not automatically participate in that transaction.

Suppose the processor calls the API successfully, and then the writer writes to the database but encounters an error. The database transaction can roll back, while the remote service retains the effect of the operation already performed. When the chunk is retried or the job is restarted, the processor may call the API again. Therefore, you cannot assume that an item will only produce a single remote call.

For read-only calls like looking up a customer profile, calling again is usually acceptable, even though it still consumes time and load. For calls that create orders, deduct funds, send notifications, or mutate external state, repeated calls can cause duplicate side effects.

To handle this case:

1. Prefer having the processor perform lookups or transformations without side effects.
2. If a command must be sent, generate a stable idempotency key from the item's business identifier and send that key in the request.
3. The remote service needs to support storing and recognizing processed keys so repeated requests do not create a second side effect.
4. If database writes need to be coordinated with sending external commands, consider a transactional outbox: write both the business data and the outbox record in the same transaction, then have a separate process dispatch the messages with controlled retries.

Do not treat adding `@Transactional` around a processor as a way to create a distributed transaction between a database and an HTTP service. This annotation does not make a regular REST API capable of rolling back alongside the database.

Network calls also extend chunk processing time. While a chunk transaction is open, a slow remote service can cause the transaction to hold resources longer and increase the risk of timeouts or lock contention. Set finite timeouts, monitor processing times, and choose chunk sizes based on both API call latency and database capacity.

## 7. Performance, load limits, and thread safety

If the processor calls the API once per item, the number of requests grows with the number of items. For a job with hundreds of thousands of records, even small per-request latency can add up to a large total runtime. Before increasing the thread count, determine how many concurrent requests the remote service can handle.

Common ways to improve performance:

- **Bulk API:** If the service supports looking up multiple IDs in a single request, group IDs into batches to reduce round trips. This may require a data preparation step or a processor with a suitable batch lookup mechanism.
- **Caching:** Caching lookup results can reduce duplicate requests. Choose the cache key, TTL, and refresh policy based on the data freshness required by the business. Avoid caching sensitive or rapidly changing data without an appropriate policy.
- **Connection pooling:** Use an HTTP client with a properly configured connection pool to avoid creating a new connection for every item.
- **Timeouts and concurrency limits:** Set connect/read/response timeouts, limit the number of in-flight requests, and consider a rate limiter or circuit breaker.
- **Chunk size:** Larger chunks reduce commit frequency but can prolong transactions and increase the amount of rework on failure. Smaller chunks limit the rollback scope but can increase overhead.
- **Concurrency:** Only increase the thread count after load testing and confirming the remote service can handle it. If the step processes concurrently, the processor and its shared dependencies must be thread-safe; do not store per-item temporary state in mutable fields of a singleton processor.

`ItemProcessor` has a synchronous signature. If you use `WebClient` inside a processor and call `block()`, the call still blocks the thread until the result arrives. Do not spawn unbounded asynchronous tasks per item and let the batch proceed before results complete; doing so breaks the coupling between processing results, chunk commits, and checkpoints. If end-to-end reactive processing is needed, design an appropriate execution model rather than merely switching the HTTP client to reactive.

## 8. Observability and operations

When a remote service becomes part of a batch pipeline, logging job status alone is not enough. Collect metrics that help distinguish batch errors from external dependency errors:

- Request count, successful request count, and failed request count by service or endpoint.
- Response times, especially p95/p99, along with timeout counts.
- Retry counts, 429 response counts, and skipped item counts.
- Error counts broken down by business category and technical category.
- Per-chunk processing duration and total step duration.

Logs should include the job execution ID, step execution ID, and an appropriate business key to trace an item across retries. Do not log access tokens, secrets, or full personal data in requests/responses. When logging errors, retain enough information for investigation while complying with the system's data protection policies.

If using a circuit breaker, clearly define the behavior when the circuit opens: stop the step, retry after a wait period, or route the item to an error-handling flow. Do not return fake data just to keep the job running, unless the business explicitly defines such fallback values.

## 9. Testing the processor and remote client integration

Testing can be split into layers so each layer focuses on a single responsibility.

**Unit tests for the processor:** mock `CustomerProfileClient`, then verify:

- When the client returns a valid profile, the processor produces the expected `EnrichedOrder`.
- When the client reports the customer is not found, the processor throws the expected business exception.
- When the client throws a transient error, the exception propagates so the step applies the retry policy.
- When business logic filters an item, the processor returns `null` and the item is not passed to the writer.

Example with JUnit and Mockito:

```java
@ExtendWith(MockitoExtension.class)
class CustomerEnrichmentProcessorTest {

    @Mock
    CustomerProfileClient customerProfileClient;

    @InjectMocks
    CustomerEnrichmentProcessor processor;

    @Test
    void enrichesOrderWithCustomerSegment() {
        Order order = new Order(
                "order-1", "customer-7", new BigDecimal("125.00"));
        CustomerProfile profile = new CustomerProfile(
                "customer-7", "GOLD");

        when(customerProfileClient.findById("customer-7"))
                .thenReturn(profile);

        EnrichedOrder result = processor.process(order);

        assertEquals("order-1", result.orderId());
        assertEquals("GOLD", result.customerSegment());
        verify(customerProfileClient).findById("customer-7");
    }
}
```

**Integration tests for the HTTP adapter:** use a mock HTTP server to verify the method, path, request headers, response deserialization, and how status codes map to exceptions. There is no need to call the real service in unit tests.

**Step tests:** verify bounded retries, skip limits, the items received by the writer, and behavior on job restart. In particular, if the remote operation has side effects, verify that the idempotency key protects the system from duplicate effects when a request is resent.

## 10. When should you use this pattern?

A processor calling a remote service is appropriate when each item requires data or a decision from another system to complete its transformation. It is a natural choice for lookups, enrichment, and validation with controlled response times.

Before implementing, ensure you can answer the following questions:

- Is the remote call reading data or creating an external side effect?
- Can an item be invoked again during retry or restart, and is the outcome safe when called repeatedly?
- Which errors are transient, which are permanent, and which cases are allowed to be skipped?
- Where are timeouts, backoff, rate limits, and concurrent request limits configured?
- Does the expected request volume match the capacity of the remote service?
- Can a bulk API or caching be used to reduce the number of calls?
- Are metrics and logs sufficient to trace failed items without exposing sensitive data?

Once these conditions are clearly defined, a remote service can become a controlled dependency in a Spring Batch pipeline, rather than an unpredictable bottleneck during job execution.
