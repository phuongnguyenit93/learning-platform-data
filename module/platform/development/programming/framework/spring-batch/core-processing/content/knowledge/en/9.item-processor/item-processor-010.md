# Processors calling external services

In Spring Batch, `ItemProcessor` receives an item from `ItemReader`, validates or transforms the data, and returns a new item for `ItemWriter`. A processor can call another service to fetch additional information or apply business rules, such as looking up a customer profile, checking account status, calculating tax, or calling a partner system's API.

Calling a service from the processor separates item-processing logic from how data is accessed or how external systems are communicated with. However, each call can increase processing time, introduce network errors, and create side effects outside the chunk's transaction. Therefore, you need to design responsibility boundaries, timeouts, retries, idempotency, and load limits clearly before putting the Job into production.

## 1. The role of ItemProcessor

The `ItemProcessor<I, O>` interface takes an item of type `I` and returns an item of type `O`:

```java
public interface ItemProcessor<I, O> {
    O process(I item) throws Exception;
}
```

A processor can:

- Validate input data and throw an exception if the data is invalid.
- Normalize or convert the item into a data type suited to the writer.
- Add information from another service, repository, or API.
- Apply business rules to compute output values.
- Return `null` to filter the item out of the write flow.

For example, the reader reads an `OrderInput` that only has an order ID and a customer ID. The processor calls `CustomerProfileService` to fetch the membership tier, and then creates an `EnrichedOrder` containing the enriched data for the writer.

```text
ItemReader<OrderInput>
        |
        v
ItemProcessor<OrderInput, EnrichedOrder>
        |
        +----> CustomerProfileService
        |             |
        |             v
        |       Customer profile
        |
        v
ItemWriter<EnrichedOrder>
```

The processor does not need to know whether the profile is fetched from a database, a cache, or an HTTP API. It only depends on the service contract. This separation lets you change how the system is accessed without rewriting the item-conversion logic.

## 2. Injecting a service into the processor via dependency injection

In Spring, a processor is usually declared as a bean and receives services via constructor injection. This makes dependencies explicit and is convenient when replacing services in tests.

```java
public interface CustomerProfileService {
    CustomerProfile findByCustomerId(String customerId);
}
```

A processor using this interface:

```java
@Component
public class EnrichOrderProcessor
        implements ItemProcessor<OrderInput, EnrichedOrder> {

    private final CustomerProfileService customerProfileService;

    public EnrichOrderProcessor(
            CustomerProfileService customerProfileService) {
        this.customerProfileService = customerProfileService;
    }

    @Override
    public EnrichedOrder process(OrderInput input) {
        CustomerProfile profile = customerProfileService
                .findByCustomerId(input.customerId());

        return new EnrichedOrder(
                input.orderId(),
                input.customerId(),
                input.amount(),
                profile.membershipLevel());
    }
}
```

The service can be implemented by a repository in the same application or by an HTTP client calling another application. The processor does not need to instantiate a new service with `new`, nor should it manage HTTP or database connections itself when those responsibilities belong to the service.

### A service calling a REST API

If the service needs to call another system, you can use `RestClient` (Spring Framework 6.1 and later) or an HTTP client suited to the application's version:

```java
@Service
public class RemoteCustomerProfileService
        implements CustomerProfileService {

    private final RestClient restClient;

    public RemoteCustomerProfileService(RestClient restClient) {
        this.restClient = restClient;
    }

    @Override
    public CustomerProfile findByCustomerId(String customerId) {
        return restClient.get()
                .uri("/customers/{customerId}", customerId)
                .retrieve()
                .body(CustomerProfile.class);
    }
}
```

`RestClient` should be configured centrally with a base URL, authentication, connection timeout, and appropriate response timeout. Do not create a new HTTP client for every item, because that adds connection-creation overhead and makes resources hard to control.

## 3. Where in the pipeline should the service call be placed?

Where to call a service depends on the purpose of the call.

**In the processor:** appropriate when the service supplies data or a result needed to transform the item. For example, looking up customer information to build an output record, computing fees based on reference data, or checking business conditions.

**In the reader:** can be appropriate if the service itself is the source supplying items. For example, a reader reading records from a paginated API. The reader is responsible for fetching inputs and signaling end of data; the processor should still focus on conversion or applying rules.

**In the writer:** appropriate when the main task is sending processed results to the target system. For example, writing normalized records to a partner API. The writer receives the whole list of items in the chunk, so it can take advantage of endpoints that support batch sending.

Do not place every external call in the processor just because it is an easy place to write code. Determine whether the service is providing input data, supporting per-item processing, or receiving output results so you choose the right component.

## 4. Handling errors when an external service does not respond

An external service can encounter errors such as:

- Timeout or lost network connection.
- HTTP `429 Too Many Requests` due to exceeding request limits.
- HTTP `5xx` when the target service hits a temporary outage.
- HTTP `4xx` due to wrong parameters, invalid permissions, or a nonexistent resource.
- A malformed response or missing required data.
- The service returning a business result rejecting the request.

Do not handle all errors the same way. Transient network errors can be retried; data or authentication errors usually require fixing the input or configuration before running again. If the service returns “customer not found”, the business may treat that as invalid data that needs controlled skipping or that fails the Job.

You should map errors in the service layer into meaningful exceptions so the processor or Step configuration can classify them:

```java
public class RemoteServiceException extends RuntimeException {
    public RemoteServiceException(String message, Throwable cause) {
        super(message, cause);
    }
}

public class CustomerDataException extends RuntimeException {
    public CustomerDataException(String message) {
        super(message);
    }
}
```

The service can convert timeouts or server errors into `RemoteServiceException`, and missing customer data into `CustomerDataException`. Keep the original cause for logging and investigation.

## 5. Retry and skip when the processor calls a service

Spring Batch supports configuring retry and skip for a fault-tolerant Step. For an external service, you should only retry errors that are likely to clear on their own, such as short-lived timeouts, HTTP 429 following a `Retry-After` policy, or transient 5xx errors. Do not retry indefinitely or retry data errors that cannot resolve themselves.

Example of configuring limited retry in Spring Batch 5:

```java
@Bean
Step enrichOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        EnrichOrderProcessor processor,
        ItemWriter<EnrichedOrder> writer) {

    return new StepBuilder("enrichOrdersStep", jobRepository)
            .<OrderInput, EnrichedOrder>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .retry(RemoteServiceException.class)
            .retryLimit(3)
            .build();
}
```

This example allows retrying `RemoteServiceException` up to the configured limit. You need to verify the exact meaning of the retry limit and how retries are counted for the Spring Batch version in use; combine it with backoff to avoid sending retries continuously while the target system is overloaded.

If the input data is invalid and the business allows ignoring it, you can configure skip separately:

```java
.faultTolerant()
.retry(RemoteServiceException.class)
.retryLimit(3)
.skip(CustomerDataException.class)
.skipLimit(100)
```

Do not skip connection errors or service errors en masse arbitrarily. If a dependent system is down, skipping thousands of items can leave the Job `COMPLETED` while the result is missing data. Set a reasonable skip limit, store the list of failed items, and have a backfill process.

## 6. Timeout, backoff, and circuit breaker

Retry does not replace timeout. If an HTTP request has no timeout, a single call can hang for a long time and keep the chunk transaction open for an extended period. You should set:

- **Connection timeout:** limits the time to establish a connection.
- **Response/read timeout:** limits the time waiting for response data.
- **Overall deadline:** limits the total time for one processing unit or one Job if the business requires it.

Backoff spaces out the intervals between retries. For example, instead of sending three retries immediately, you can wait progressively 200 ms, 500 ms, then 1 second, with jitter so multiple workers do not all retry at the exact same instant. For HTTP 429, respect the rate limit or `Retry-After` provided by the target service.

A circuit breaker is a mechanism that temporarily stops calling a service that is failing continuously. When the circuit opens, subsequent calls fail fast for a period of time, helping avoid overloading the dependent system and reducing the number of threads held waiting. Once the period expires, the mechanism allows a few test requests to determine whether the service has recovered.

These mechanisms can be implemented with the HTTP client, Resilience4j, or an appropriate library. Avoid stacking multiple retry layers without calculating the total number of calls. For example, if the HTTP client retries 3 times on its own and Spring Batch also retries 3 times, a single item can generate more requests than expected.

## 7. The chunk transaction does not cover external services

This is an important risk when calling external systems from a processor. Spring Batch normally executes the reader, processor, and writer within the scope of chunk processing, with the transaction committed after the writer finishes. The transaction manager can roll back changes on resources participating in the transaction, such as the managed database connection.

An independent HTTP service does not automatically participate in the chunk's database transaction. If the processor calls an API and the target service performs the action, but the writer later fails and the database transaction rolls back, the action in the external service may still have happened.

For example:

```text
Chunk begins
    |
    v
Processor calls partner API
    |
    v
Partner confirms update succeeded
    |
    v
Writer fails writing to database
    |
    v
Database transaction rolls back

Result: the update at the partner still exists
```

When the chunk is retried or the Job restarts, the processor can call the API again. Therefore, you need to distinguish whether the service call only reads data or creates side effects.

- For read-only calls (GET/enrichment), retry is usually safer, though the response can change over time. If consistency is needed, use a data snapshot or version.
- For write or action-creating calls (payment POST, sending notifications, creating orders), you need an idempotency key or a deduplication mechanism at the target system.
- If you must synchronize database changes and messages/APIs, consider a transactional outbox or an appropriate saga/reconciliation process instead of assuming the two systems share a transaction.

## 8. Designing idempotency for service calls

An operation is idempotent if it can be performed multiple times with the same identifier without creating unintended extra side effects. This is an important requirement because Spring Batch can retry an item or reprocess a chunk after a rollback/restart.

For example, when sending a request to create a partner transaction, you can construct a unique key from the source transaction ID:

```java
public PartnerResult createPartnerTransaction(
        SourceTransaction transaction) {

    String idempotencyKey = "settlement:" + transaction.id();

    return restClient.post()
            .uri("/transactions")
            .header("Idempotency-Key", idempotencyKey)
            .body(new PartnerRequest(
                    transaction.id(), transaction.amount()))
            .retrieve()
            .body(PartnerResult.class);
}
```

This is an illustrative example; the partner system must support and properly enforce the idempotency-key contract for the mechanism to work. The key must remain stable across retries, restarts, and executions of the same business item. Do not generate a new UUID on each call if the goal is to recognize the same action.

If the target service does not support idempotency, you may need to store processing state in your own system, use unique constraints, or build a reconciliation step to detect and handle transactions with unknown outcomes.

## 9. Performance when calling a service for each item

If a Job processes 500,000 items and each item calls an API, the Job can generate 500,000 requests. Even if each request takes 100 ms, the total time can be huge if executed sequentially. When planning, estimate the number of calls, latency, the target service's throughput limit, and network capacity.

Some ways to improve it:

### Caching reference data

If many items look up the same customer ID or rarely changing catalog, a cache can reduce the number of requests. Choose an appropriate TTL, capacity limit, and invalidation policy. Do not cache sensitive data or data with strict consistency requirements without evaluating stale-data risks.

### Batch API

If the target service supports looking up multiple IDs in a single request, you can group keys to call the API in batches. Because `ItemProcessor` receives one item at a time, grouping requests may require a controlled cache/buffer layer or moving data retrieval to an appropriate reader/writer. Do not build your own buffer that alters ordering or causes data loss on restart.

### Limiting parallelism

Adding threads can increase throughput, but it also increases concurrent requests. Limit workers, connection pools, concurrency, and rate according to the target service's quota. If the partner system allows only 50 requests/second, the batch configuration should not exceed that limit.

### Optimizing outbound data

Send only the required fields, reuse the HTTP client, and avoid re-fetching data that can be obtained from the initial source. If the reference data is already available in a database or snapshot, batch reading can be more efficient than calling an API for each item.

## 10. Thread safety when the Step runs in parallel

If the Step uses multi-threading or partitioning, multiple `process()` calls can happen concurrently. Injected processors and services are usually singleton beans, so you should not store item-specific state in shared mutable fields.

An unsafe example:

```java
@Component
public class UnsafeProcessor
        implements ItemProcessor<OrderInput, EnrichedOrder> {

    private OrderInput currentItem; // State shared across threads

    @Override
    public EnrichedOrder process(OrderInput item) {
        currentItem = item;
        // Another thread can overwrite currentItem here.
        return convert(currentItem);
    }
}
```

Keep processing data in local variables of the method:

```java
@Component
public class SafeProcessor
        implements ItemProcessor<OrderInput, EnrichedOrder> {

    private final CustomerProfileService profileService;

    public SafeProcessor(CustomerProfileService profileService) {
        this.profileService = profileService;
    }

    @Override
    public EnrichedOrder process(OrderInput item) {
        CustomerProfile profile = profileService
                .findByCustomerId(item.customerId());

        return convert(item, profile);
    }
}
```

The service and HTTP client must also be safe when called concurrently. Check the documentation for the client, cache, and shared libraries; ensure connection pools and concurrency limits are configured appropriately. If the processor is not thread-safe, do not enable a multi-threaded Step just to speed things up.

## 11. Logging and monitoring service calls

When the processor calls an external service, logs should help identify which item hit an error and which service is slow. You should log:

- JobExecution ID and StepExecution ID.
- Item ID or business key, avoiding logging full sensitive data.
- Service/endpoint name at an appropriate level.
- Call duration, result status, and retry count.
- Error code or correlation ID from the target system.

Do not log access tokens, passwords, personal data, or full payloads unless there is a clear need and appropriate access control. Metrics should track p50/p95/p99 latency, error rate, retry count, requests/second, and circuit-breaker openings. These metrics help distinguish whether the Job is slow because of the processor or because of a dependent service.

## 12. Testing a processor with service dependencies

Because the processor depends on a service interface, you can test its logic without calling the real system by using a mock or fake service.

An example with Mockito:

```java
@ExtendWith(MockitoExtension.class)
class EnrichOrderProcessorTest {

    @Mock
    CustomerProfileService profileService;

    @InjectMocks
    EnrichOrderProcessor processor;

    @Test
    void enrichesOrderUsingCustomerProfile() {
        OrderInput input = new OrderInput("O-100", "C-10", new BigDecimal("50.00"));
        CustomerProfile profile = new CustomerProfile("C-10", "GOLD");

        when(profileService.findByCustomerId("C-10"))
                .thenReturn(profile);

        EnrichedOrder result = processor.process(input);

        assertEquals("O-100", result.orderId());
        assertEquals("GOLD", result.membershipLevel());
    }
}
```

Beyond the success case, test the service returning not-found data, throwing transient errors, throwing business errors, and the processor filtering items if applicable. Separate integration tests can verify HTTP timeouts, status-code mapping, authentication, and serialization. Do not let unit tests depend on the network or production endpoints.

## 13. When should you not call a service directly from the processor?

You should not call a service directly in the processor if:

- Each item requires one request, but the API only supports batching and the data volume is very large.
- The service has high latency or low request limits that prevent the Job from finishing within the batch window.
- The call creates side effects without idempotency, while the chunk may retry or restart.
- The lookup data can already be joined or fetched in batches more efficiently from a database.
- The business needs a consistent snapshot, but the service returns data that changes over time.
- The processor needs shared mutable state or depends on parallel execution order.

In these cases, consider loading reference data into a snapshot up front, using a reader that reads from a prepared source, calling a batch API, or moving write operations to a writer with an idempotent mechanism. The goal is to place responsibility in the appropriate component and keep restart reliable.

## Conclusion

`ItemProcessor` can use an injected service to enrich data or apply business rules for each item. Depend on interfaces, manage HTTP clients centrally, and clearly separate transient errors from data errors. When calling an external service, configure timeouts, limited retries, and backoff; understand that the chunk's transaction cannot roll back side effects in an independent system; and use idempotency to protect against retries or restarts. For large Jobs, measure latency, cache or batch calls when appropriate, limit parallelism, and ensure both the processor and the service are safe when multiple threads execute.
