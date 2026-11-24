# Enrichment processor in Spring Batch

In many batch jobs, data read from a file or database does not yet contain enough information to write to the target system. A customer record may contain only a customer code, whereas the target data requires a standardized name, customer segment, business region, and classification status. An order may contain a product ID but require a product category, tax rate, or shipping unit details before calculations.

An enrichment processor is an `ItemProcessor` that supplements an item with necessary data before passing it to the writer. The processor typically looks up reference data, calls a read-only data service, or combines preloaded data. The result is a richer item, ready for subsequent business validation or mapping to the output model.

Enrichment must be designed with performance, consistency, and restartability in mind. If every item fires its own API call or query, the job can generate N+1 requests and run very slowly. If reference data changes between runs, the same input could be enriched into different results. If the processor creates side effects or writes data itself, chunk retries and rollbacks become hard to control.

## 1. What is an Enrichment processor?

In chunk-oriented processing, `ItemProcessor` receives a read item, executes processing logic, and returns an output item. Enrichment is a form of processing whose focus is supplementing information from another source.

~~~text
Input source
    |
    v
ItemReader<CustomerInput>
    |
    v
EnrichmentProcessor
    |
    +----> Lookup customer profile
    |
    +----> Lookup region reference
    |
    +----> Lookup pricing/rules
    |
    v
EnrichedCustomer
    |
    v
ItemWriter<EnrichedCustomer>
~~~

For example, the input only has:

~~~json
{
  "customerCode": "C-100",
  "regionCode": "SOUTH"
}
~~~

After enrichment, the item may additionally contain customer name, tier, normalized address, and region name:

~~~json
{
  "customerCode": "C-100",
  "customerName": "Example Trading",
  "customerTier": "GOLD",
  "regionCode": "SOUTH",
  "regionName": "Southern Region"
}
~~~

A processor does not have to call multiple sources. Enrichment can simply be one lookup from a reference table, a cache lookup, or combining data from a single service. What matters is that the output carries additional information needed by downstream steps.

## 2. Enrichment vs. validation and transformation

These three types of logic often appear together in a processor, yet they serve distinct purposes:

| Processing type | Purpose | Example |
| --- | --- | --- |
| Validation | Checks whether an item satisfies rules | `customerCode` required, `amount` must be positive |
| Enrichment | Supplements data from other sources | Looking up customer tier by `customerCode` |
| Transformation | Converts data into another shape | Converting `CustomerInput` into `CustomerEntity` |

A single processor can perform all three, though it is better to split logic into clear, testable components. For instance, validating input before calling a service avoids wasting requests on clearly invalid items. Enrichment then adds supplemental data. A final mapper produces the output model for the writer.

If enrichment is just one step in a pipeline, `CompositeItemProcessor` can chain multiple processors in order. The output of each processor becomes the input of the next.

## 3. Creating a basic enrichment processor

Suppose the source provides a customer code and region code. The processor looks up the customer profile and region reference:

~~~java
public class CustomerEnrichmentProcessor
        implements ItemProcessor<CustomerInput, EnrichedCustomer> {

    private final CustomerProfileService customerProfiles;
    private final RegionService regions;

    public CustomerEnrichmentProcessor(
            CustomerProfileService customerProfiles,
            RegionService regions) {
        this.customerProfiles = customerProfiles;
        this.regions = regions;
    }

    @Override
    public EnrichedCustomer process(CustomerInput input) {
        CustomerProfile profile =
            customerProfiles.findByCode(input.customerCode())
                .orElseThrow(() ->
                    new MissingCustomerException(input.customerCode()));

        Region region =
            regions.findByCode(input.regionCode())
                .orElseThrow(() ->
                    new MissingRegionException(input.regionCode()));

        return new EnrichedCustomer(
            input.customerCode(),
            profile.name(),
            profile.tier(),
            input.regionCode(),
            region.name()
        );
    }
}
~~~

The processor only coordinates lookups and builds the output item. Services handle database or API access, while the writer handles persisting results. This separation makes it easy to swap enrichment sources without rewriting the entire step.

## 4. Using constructor injection and step configuration

Declare the processor as a bean so Spring manages its dependencies:

~~~java
@Bean
ItemProcessor<CustomerInput, EnrichedCustomer> customerEnrichmentProcessor(
        CustomerProfileService customerProfiles,
        RegionService regions) {

    return new CustomerEnrichmentProcessor(customerProfiles, regions);
}
~~~

Register it in the step:

~~~java
@Bean
Step enrichCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<CustomerInput> customerReader,
        ItemProcessor<CustomerInput, EnrichedCustomer> customerEnrichmentProcessor,
        ItemWriter<EnrichedCustomer> customerWriter) {

    return new StepBuilder("enrichCustomersStep", jobRepository)
        .<CustomerInput, EnrichedCustomer>chunk(100, transactionManager)
        .reader(customerReader)
        .processor(customerEnrichmentProcessor)
        .writer(customerWriter)
        .build();
}
~~~

The step defines item types before and after the processor. The reader returns `CustomerInput`, the processor returns `EnrichedCustomer`, and the writer receives `EnrichedCustomer`. Separating input/output types lets the compiler catch pipeline mismatches.

## 5. Keeping input and output separate

A clean design uses immutable DTOs or records for input and output data:

~~~java
public record CustomerInput(
    String customerCode,
    String regionCode
) {}

public record EnrichedCustomer(
    String customerCode,
    String customerName,
    String customerTier,
    String regionCode,
    String regionName
) {}
~~~

The processor constructs a new object instead of mutating the input directly. This helps:

- Preserve the original payload for auditing or comparison.
- Distinguish fields coming from the source from enriched fields.
- Prevent other delegates or listeners from seeing unexpectedly mutated objects.
- Simplify unit testing since inputs and outputs are immutable values.

If you need to retain the full source payload, you can add source reference, source file name, source record number, or source batch ID to the output model. You do not need to copy every field if the writer does not need them.

## 6. Enrichment from a database

A common case is looking up a reference or master data table:

~~~java
@Service
public class CustomerProfileService {

    private final CustomerProfileRepository repository;

    public CustomerProfileService(CustomerProfileRepository repository) {
        this.repository = repository;
    }

    public Optional<CustomerProfile> findByCode(String code) {
        return repository.findByCustomerCode(code);
    }
}
~~~

The processor calls the service by business key. Ensure lookup columns have appropriate indexes; otherwise, millions of lookups can put heavy load on the database.

If each item needs multiple references, avoid running one query per field. You can expose a service returning the required enrichment aggregate in a single lookup, or use a join/projection query in the reader when logic and data sources fit.

## 7. Avoiding N+1 queries in enrichment

Suppose a chunk has 1000 items and the processor calls the repository once per item:

~~~text
1000 input items
  |
  +--> SELECT customer_profile WHERE code = ?
  +--> SELECT customer_profile WHERE code = ?
  +--> SELECT customer_profile WHERE code = ?
  +--> ... 1000 times
~~~

This is an N+1 lookup pattern. Even if each query is fast, total latency, connection usage, and database load can become huge.

Instead, collect the keys to look up and issue a batched query:

~~~sql
select customer_code, customer_name, tier
from customer_profile
where customer_code in (:customerCodes)
~~~

Results are converted into a `Map` keyed by customer code. The processor looks up in the map rather than hitting the database per item.

Because `ItemProcessor` operates one item at a time, collecting keys per chunk must be designed in another component or via caching/bulk preloading. Do not assume the processor receives the entire chunk directly.

## 8. Bulk enrichment strategies

Several approaches reduce lookup counts:

| Strategy | Approach | Best suited when |
| --- | --- | --- |
| Join in reader query | Fetch primary and reference data in the same query | Same database and query is not overly complex |
| Bulk preload | Load reference data before step processing starts | Moderately sized, infrequently changing reference set |
| Batch lookup service | Send a group of keys to a service | Service supports a bulk API |
| Key-based caching | Look up on first hit and reuse | Many items share the same reference |
| Chunk-aware custom component | Group keys per chunk and enrich | Per-chunk batching needed for large datasets |

Choose a strategy based on data size, reference mutability, latency, and consistency requirements. Preloading an entire table may not work if the table has millions of records.

## 9. Bulk preloading before the step runs

If reference data is moderately sized and requires a consistent snapshot for the whole step, load it before processing starts. For example, use `StepExecutionListener` to initialize a lookup map:

~~~java
public class ReferenceDataListener implements StepExecutionListener {

    private final RegionRepository regionRepository;
    private Map<String, Region> regions;

    public ReferenceDataListener(RegionRepository regionRepository) {
        this.regionRepository = regionRepository;
    }

    @Override
    public void beforeStep(StepExecution stepExecution) {
        this.regions = regionRepository.findAll().stream()
            .collect(Collectors.toUnmodifiableMap(
                Region::code,
                Function.identity()
            ));
    }

    public Region findRegion(String code) {
        return regions.get(code);
    }
}
~~~

The processor can receive this listener/service and query the map. Mind the lifecycle: the listener must be initialized before the processor uses it, and state must be scoped to `StepExecution` if jobs run concurrently.

Do not store a step-specific mutable map in a singleton bean shared across concurrent executions. Use `@StepScope` or an execution-scoped state holder; ensure workers/partitions do not overwrite each other's data.

## 10. Bulk lookup per chunk

If reference data is too large to preload in full, yet the service supports looking up multiple keys, build a batch-aware layer:

~~~text
Chunk input:
  C-1, C-2, C-1, C-3
       |
       v
Collect distinct keys:
  C-1, C-2, C-3
       |
       v
One bulk lookup
       |
       v
Map<customerCode, CustomerProfile>
       |
       v
Enrich each input item
~~~

Because the `ItemProcessor` contract processes one item at a time, preparing a per-chunk lookup map requires an integration point with chunk visibility—such as a custom chunk-oriented component, a cache populated by the reader/listener, or a data preparation step beforehand. Never use static variables to accumulate keys across `process` calls because chunk boundaries, rollbacks, and multi-threading will corrupt state.

A simple alternative when a service only takes single keys but many items share keys is key-based caching. When keys are completely distinct, bulk APIs or joins are usually more efficient.

## 11. Caching in an enrichment processor

Caching helps when many items look up the same reference:

~~~java
public class CachedRegionService {

    private final RegionRepository repository;
    private final ConcurrentMap<String, Region> cache =
        new ConcurrentHashMap<>();

    public CachedRegionService(RegionRepository repository) {
        this.repository = repository;
    }

    public Region findRequired(String code) {
        return cache.computeIfAbsent(code, key ->
            repository.findByCode(key)
                .orElseThrow(() -> new MissingRegionException(key))
        );
    }
}
~~~

Caching reduces repeated queries for the same key. `ConcurrentHashMap` keeps map operations structurally safe under concurrent access, but does not automatically handle invalidation, memory bounds, or reference data consistency.

For long-running jobs, an unbounded cache can grow memory indefinitely. Consider a cache with maximum size, TTL, or single-execution scope. If reference data changes while the job runs, the cache may retain stale values.

## 12. Application-wide or step-scoped cache?

An application-wide cache can be reused across multiple jobs, but needs refresh and synchronization policies. A step-scoped cache makes lifecycle bounds easy and ties cleanly to a single run's snapshot.

| Cache scope | Advantages | Risks |
| --- | --- | --- |
| Application-wide | Reused across jobs, fewer lookups | Stale data, long-lived memory, multi-tenant contention |
| Step-scoped | Isolated per execution, easy to release | Each step may need to reload data |
| Chunk-local | Bounded memory, fits per-chunk lookups | Needs mechanism to collect keys and populate map per chunk |

If keys depend on tenant, locale, or business date, the cache key must include those factors. Caching solely by customer code can return wrong data across tenants or effective periods.

Never share a cache containing tenant-sensitive data across executions without partition keys and clear isolation policies.

## 13. Reference data that changes over time

An enrichment result may depend on a business point in time:

- Tax rates take effect from a specific date.
- Customer tiers change across periods.
- Product prices carry versions or effective dates.
- Region mappings are updated after the job starts.

If a job restarts the next day and queries current reference data, the same input might produce a different output from the initial run. This can make results inconsistent.

Ways to control this:

1. Query references by the job's business date/effective date.
2. Store the reference version or snapshot ID in `JobParameters`.
3. Load a reference snapshot into a staging table.
4. Use historical tables with valid-from/valid-to ranges.
5. Persist decided enrichment values if business rules require preserving exact results across restarts.

Do not use `LocalDate.now()` inside a processor for logic that must remain stable on restart. Pass the business date explicitly via `JobParameters` so the same `JobInstance` uses the same point in time.

## 14. Enrichment via REST or external services

A processor may call an external service to add information:

~~~java
public class RiskEnrichmentProcessor
        implements ItemProcessor<PaymentInput, EnrichedPayment> {

    private final RiskClient riskClient;

    public RiskEnrichmentProcessor(RiskClient riskClient) {
        this.riskClient = riskClient;
    }

    @Override
    public EnrichedPayment process(PaymentInput input) {
        RiskProfile profile = riskClient.getProfile(input.customerId());
        return new EnrichedPayment(input, profile.score(), profile.level());
    }
}
~~~

When calling remote services, set explicit timeouts and classify errors:

- 404 or "profile not found" may be a business outcome.
- 429 or 503 may be transient errors, depending on the API contract.
- A timeout does not prove the remote server did not process the request.
- 401/403 are usually credential or permission errors, requiring failure and configuration fixes.
- Schema-mismatched responses may indicate contract drift.

Enrichment should favor read operations. If a remote call creates side effects, reconsider placing it in the processor because retries/rollbacks can trigger duplicate calls. Writes or publishing usually belong in the writer or an outbox.

## 15. Retrying transient lookup errors

If an API or database lookup is temporarily unavailable, configure retries on the step:

~~~java
return new StepBuilder("enrichPaymentsStep", jobRepository)
    .<PaymentInput, EnrichedPayment>chunk(100, transactionManager)
    .reader(paymentReader)
    .processor(riskEnrichmentProcessor)
    .writer(paymentWriter)
    .faultTolerant()
    .retry(TransientEnrichmentException.class)
    .retryLimit(3)
    .build();
~~~

Only wrap exceptions in `TransientEnrichmentException` when the failure is known to be potentially self-healing. Do not retry every `RuntimeException`, as mapping bugs, permanently missing references, or code defects will not fix themselves.

Processor retries can invoke the processor again for the item. The processor must therefore avoid non-idempotent side effects. For remote reads, repeated requests are typically safe, though rate limits and costs must be considered.

If retries are exhausted, the step can fail. Schedulers/operators can restart the `JobInstance` once the service recovers; query parameters and reference versions must remain stable so outputs do not change unexpectedly.

## 16. Missing references: default, skip, quarantine, or fail?

Not every lookup returning no data is an infrastructure error. It may be a business case requiring explicit handling:

| Situation | Handling direction |
| --- | --- |
| Optional reference with a defined default | Use the default and record the default source |
| Mandatory reference missing on a few items | Skip/quarantine if allowed |
| Reference missing across an entire data category | Fail the step/job as it likely indicates source or config errors |
| Lookup service temporarily unresponsive | Bounded retry |
| Reference expired as of the business date | Apply historical rule or reject |

Never silently replace null with a generic default just to make the job finish. A missing customer might not be permitted in a default segment; doing so creates corrupt data that looks valid.

## 17. Representing missing references with dedicated exceptions

Using a dedicated exception helps the skip policy identify business errors accurately:

~~~java
public class MissingCustomerProfileException
        extends RuntimeException {

    public MissingCustomerProfileException(String customerCode) {
        super("No customer profile for code: " + customerCode);
    }
}
~~~

Processor:

~~~java
CustomerProfile profile = customerProfiles.findByCode(code)
    .orElseThrow(() -> new MissingCustomerProfileException(code));
~~~

The step can skip that error type if the business owner allows it:

~~~java
.faultTolerant()
.skip(MissingCustomerProfileException.class)
.skipLimit(100)
~~~

For skipped records, use a `SkipListener` to save the business key, source location, and reason. If records must be reprocessed once the reference is added, the quarantine store must keep enough context to reprocess them.

If missing profiles stem from a global configuration bug—such as pointing to the wrong database or an unloaded reference table—skipping item by item will drop data. Fail the job after a low threshold or verify dependencies before the step runs.

## 18. Validate before or after enrichment?

Ordering depends on which data is needed for validation:

~~~text
Input
  |
  v
Validate structural fields
  |
  v
Enrich reference data
  |
  v
Validate business rules using enriched values
  |
  v
Map output
~~~

For example, a blank `customerCode` can be rejected before lookup. However, the rule "customer tier must support this order type" can only be checked after looking up the tier.

Splitting validation into structural validation and business validation avoids unnecessary queries. It also separates missing source field errors from non-existent reference errors.

## 19. Combining processors with CompositeItemProcessor

To separate each processing step, use `CompositeItemProcessor`:

~~~java
@Bean
CompositeItemProcessor<CustomerInput, EnrichedCustomer> customerProcessor(
        ItemProcessor<CustomerInput, CustomerInput> validator,
        ItemProcessor<CustomerInput, CustomerEnrichedData> enricher,
        ItemProcessor<CustomerEnrichedData, EnrichedCustomer> mapper) {

    return new CompositeItemProcessorBuilder<CustomerInput, EnrichedCustomer>()
        .delegates(validator, enricher, mapper)
        .build();
}
~~~

Data type flow:

~~~text
CustomerInput
    |
    v
Validator
    |
    v
CustomerInput
    |
    v
Enricher
    |
    v
CustomerEnrichedData
    |
    v
Mapper
    |
    v
EnrichedCustomer
~~~

Each delegate's output type must be compatible with the next delegate's input type. If any delegate returns `null`, the pipeline filters the item and subsequent delegates are not called for it.

`CompositeItemProcessor` separates responsibilities but does not create separate transactions per processor. The entire processor chain still executes inside the step's chunk processing.

## 20. Can an enrichment processor filter items?

`ItemProcessor` is permitted to return `null`. Spring Batch treats this as filtering: the item is not forwarded to the writer and counts toward the filter count.

Example:

~~~java
@Override
public EnrichedCustomer process(CustomerInput input) {
    if (input.isTestRecord()) {
        return null;
    }

    return enrich(input);
}
~~~

Only use `null` to filter when excluding the item is an explicit business decision. Never return `null` when a lookup fails or data is missing without a policy, as that silently drops items without raising an exception for the skip listener to handle.

Distinguish:

- Return `null`: intentionally filters the item.
- Throw exception: item could not be processed; step applies retry/skip/fail.
- Return object with rejected status: writer/quarantine receives the record to persist the reason.

## 21. Do not write data inside an enrichment processor

A processor should focus on computation, validation, and data supplementation to build the output. If the processor writes to a database, sends messages, or calls side-effecting APIs directly, those actions happen before the writer and can repeat on chunk retries.

Example to avoid:

~~~java
@Override
public EnrichedOrder process(OrderInput input) {
    EnrichedOrder order = enrich(input);
    auditRepository.save(new AuditRecord(order.id()));
    return order;
}
~~~

If the writer later fails, the transaction may roll back the audit if it shares the same transaction manager, but remote side effects or separate data sources may have already committed. When the processor is re-invoked, the audit may be written again.

Move writes to the writer or an outbox. If read-only lookups are needed, use appropriate services/repositories and understand their transaction semantics.

## 22. Transactions and read consistency

Database enrichment may execute inside the chunk transaction or in a separate transaction/service depending on configuration. Understand what point in time the lookup sees.

For example, the job reads orders in one transaction while a service looks up customer profiles in another transaction. If a profile changes between two calls, two items for the same customer could receive different data.

Options:

- Use the same transaction/appropriate isolation if a consistent snapshot within the chunk is required.
- Use a business effective date to query versioned references.
- Use an immutable reference snapshot per batch.
- Record the reference version in output/audit to explain results later.

Do not assume a chunk transaction automatically gives a consistent snapshot for the entire job duration. Isolation semantics depend on the database, transaction manager, and how services open transactions.

## 23. @StepScope for JobParameters-driven enrichment

Some enrichment depends on business date, tenant, or reference version:

~~~java
@Bean
@StepScope
ItemProcessor<OrderInput, EnrichedOrder> orderEnrichmentProcessor(
        ProductCatalogService catalog,
        @Value("#{jobParameters['businessDate']}") String businessDate,
        @Value("#{jobParameters['tenantId']}") String tenantId) {

    LocalDate effectiveDate = LocalDate.parse(businessDate);
    return input -> {
        Product product = catalog.findForTenant(
            tenantId,
            input.productCode(),
            effectiveDate
        );
        return EnrichedOrder.from(input, product, effectiveDate);
    };
}
~~~

`JobParameters` ensures the same `JobInstance` uses the same tenant and business date on restart. Do not read the current system date inside `process()` if that date affects business outcomes.

If the processor holds per-execution caches or mutable state, `@StepScope` isolates the target instance. However, the processor can still be called concurrently in certain setups; internal state must be designed thread-safely.

## 24. Enrichment with large reference datasets

If a reference table has millions of rows, preloading everything into a `Map` can cause memory pressure. Alternatives:

- Query by groups of keys from the chunk or sliding window.
- Use a cache with bounded size and TTL.
- Read references via a separate reader and build an appropriate staging/index table.
- Join directly in the source query when in the same database and the query plan is efficient.
- Use database indexes on business keys.
- Partition the job by tenant, region, or batch range.

Choose an approach based on key duplication ratio. If one million inputs use only 1,000 distinct customer codes, caching or preloading 1,000 profiles can be effective. If every input has a distinct key, bulk lookups or joins may perform better.

Measure query counts, cache hit ratio, memory, response times, and database load rather than picking caching purely by intuition.

## 25. Handling API rate limits and back pressure

When enrichment calls a remote service, batch throughput can exceed the API's capacity. Symptoms:

- HTTP 429.
- Rising timeouts.
- Growing request queues.
- Service returning 503 or throttling responses.

Apply:

- Reasonable connection/read timeouts.
- Bounded retries and backoff per service contract.
- Rate limiters or concurrency caps.
- Bulk endpoints if the API supports them.
- Caching for infrequently changing references.
- Circuit breakers or temporary call suspension during prolonged outages.

Do not retry immediately in a tight loop on 429. Respect `Retry-After` if provided by the API and bound total time the step can wait.

If the service cannot meet SLAs, split enrichment into a separate job/step or introduce a staging queue to regulate throughput. Do not let a simple processor turn into a dumping ground for all retry and orchestration logic.

## 26. Logging and metrics for enrichment

Enrichment must be observable because many bugs surface only when source data meets unusual reference states:

- Number of items processed.
- Number of items filtered.
- Number of items missing references.
- Lookup counts per source.
- Cache hit/miss ratio.
- Average and percentile lookup latencies.
- Retry, timeout, and API error counts.
- Number of quarantined items.

Logs should include job execution ID, step execution ID, source batch ID, and business key. Do not log entire customer profiles or sensitive payloads unnecessarily.

For enrichment failures, clearly log which source lacked data and which lookup key failed. Avoid logging secrets, access tokens, or full remote service responses.

## 27. Unit testing an enrichment processor

Processors should be tested independently using mock services/repositories:

~~~java
@Test
void enrichesCustomerWithProfileAndRegion() {
    when(customerProfiles.findByCode("C-100"))
        .thenReturn(Optional.of(
            new CustomerProfile("C-100", "Example Trading", "GOLD")
        ));
    when(regions.findByCode("SOUTH"))
        .thenReturn(Optional.of(
            new Region("SOUTH", "Southern Region")
        ));

    EnrichedCustomer result =
        processor.process(new CustomerInput("C-100", "SOUTH"));

    assertThat(result.customerName()).isEqualTo("Example Trading");
    assertThat(result.customerTier()).isEqualTo("GOLD");
    assertThat(result.regionName()).isEqualTo("Southern Region");
}
~~~

Unit tests should cover:

- Successful lookup.
- Missing customer or reference.
- Input missing required keys.
- Default values per contract.
- Correct forwarding of business date/tenant.
- Cache hits avoiding repeated repository calls when cached.
- Transient errors propagating for step retry.
- Processor not mutating input when using immutable output.

Do not check output alone; verify service call counts to catch accidental N+1 lookups in code.

## 28. Testing missing references and skip behavior

If missing profiles are configured to be skipped, integration tests must run the full step:

1. Prepare two customers with profiles and one customer without a profile.
2. Reader returns all three inputs.
3. Enrichment processor throws `MissingCustomerProfileException` for the missing item.
4. Step configures skip for the exception with an appropriate limit.
5. `SkipListener` records the failing item's business key.
6. Writer receives only the successfully enriched items.

Verify:

- Job/step status is accurate.
- Write count equals valid items.
- Skip count equals skipped items.
- Target store contains all valid customers.
- Quarantine/audit stores the reason and source reference.

If a missing reference is a batch-wide failure, test job failure and confirm no partial completion is wrongly marked successful.

## 29. Testing retries for remote enrichment

Use a mock server or stub client to simulate:

~~~text
Request 1 -> HTTP 503
Request 2 -> HTTP 503
Request 3 -> HTTP 200 with profile
~~~

Verify:

- Retry count respects the limit.
- Request timeouts are enforced.
- Eventual success produces the right enriched item.
- Exceeding the retry limit fails or handles the step per policy.
- No duplicate side effects occur if the endpoint is not purely read-only.

If the API returns 404, test separately whether it is a skippable missing reference or a fatal error. Do not lump 404 and 503 under the same exception type if policies differ.

## 30. Testing caching and consistency

For caches, test these cases:

- Same key queried multiple times only calls the repository per cache policy.
- Two tenants with the same customer code but different data do not share cache entries.
- Cache expires or refreshes per policy.
- Multiple threads querying the same key never produce wrong results.
- Cache is released after `StepExecution` if step-scoped.
- Restart uses the right reference version for the business date.

If a cache snapshot is preloaded in `beforeStep`, verify the processor never runs before preload finishes. With partitioning, confirm each partition has the proper lookup scope and does not overwrite another partition's map.

## 31. Restart and enrichment results

Spring Batch may re-read uncommitted items after a restart. If enrichment is recomputed, results can differ if reference data changed.

Example:

~~~text
Initial run:
  Order 100 -> lookup tax rate 8%
  Chunk commits up to Order 90
  Job fails before Order 100 commits

Before restart:
  Tax rate changes to 10%

Restart:
  Order 100 is re-enriched with tax rate 10%
~~~

Results can become inconsistent within the same batch if earlier items used 8% and post-restart items use 10%.

To avoid this:

- Query tax rates by a fixed effective date.
- Pass reference version/snapshot ID in identifying parameters.
- Store enrichment decisions if exact reproduction is required.
- Stage reference data into a snapshot before processing.

If business rules permit using new references on restart, explicitly log the reference version/timestamp for auditing. Never let behavior shift silently.

## 32. Restart and in-memory caches

In-memory caches do not survive process restarts. Never treat a cache as a checkpoint. After restart, the cache can be repopulated, but it must load the exact reference version and data scope of the original `JobInstance`.

If the cache is preloaded from the live database without a version/cutoff, restarts can yield different outputs. Save a snapshot ID or query by effective date.

Do not store an entire cache map inside `ExecutionContext` if the map is large. `ExecutionContext` is for small, serializable checkpoint metadata; staging tables or reference snapshots are better suited for large datasets.

## 33. Enrichment and partitioning

When a step runs in parallel across partitions, the processor can be called across multiple threads or workers. Determine:

- Is the lookup service thread-safe?
- Is the cache shared or per-partition?
- Are remote API rate limits enforced job-wide or per-worker?
- Is the reference snapshot consistent across partitions?
- Can the same customer key be looked up in multiple partitions?

If using a shared cache, it must be thread-safe with keys including tenant/version. Using per-partition caches may increase total lookups, though isolation is simpler.

For remote services, limit concurrency job-wide so request volume is not multiplied by partition count. Separate rate limiters per partition can let total traffic exceed API limits.

## 34. Enrichment via query joins instead of processor lookups

If primary data and references live in the same database, enrichment info can be fetched right inside the reader query:

~~~sql
select new com.example.EnrichedCustomer(
    c.customerCode,
    c.name,
    r.regionName,
    t.tierName
)
from Customer c
left join Region r on r.code = c.regionCode
left join CustomerTier t on t.code = c.tierCode
where c.status = :status
order by c.id
~~~

Advantages:

- Eliminates per-item queries.
- Database optimizes joins and indexes.
- Reader returns the ready-made projection.
- Avoids holding large entity graphs in the processor.

Disadvantages:

- Queries can grow complex.
- Joins can produce duplicate rows if relationships are not unique.
- Pagination requires careful verification.
- Enrichment logic becomes tightly coupled to the database query.
- Hard to combine with non-database sources.

If query joins make the reader hard to maintain or remote services must be called, keeping enrichment in the processor/service may fit better.

## 35. Common pitfalls when using an enrichment processor

**Querying once per item:** creates N+1 lookups and increases database load. Use joins, bulk lookups, or appropriate caching.

**Unbounded preloading of entire reference sets:** can cause memory pressure. Measure size and choose bounded caches or grouped lookups.

**Caches missing tenant/version in keys:** can return wrong data across tenants or business dates. Use complete cache keys.

**Using current date inside the processor:** restarting on another day can produce different output. Pass business date via `JobParameters`.

**Conflating missing references with connection errors:** 404 and 503 mean different things. Use separate exceptions/result types.

**Skipping all enrichment errors:** can ignore infrastructure failures and lose data. Skip only record-level errors allowed by business rules.

**Retrying every `RuntimeException`:** mapping bugs or permanent missing references repeat uselessly. Retry only bounded transient errors.

**Returning `null` on lookup failures:** items are silently filtered out. Use exceptions or quarantine per policy.

**Writing data inside the processor:** side effects can repeat on retry/rollback. Move writes to the writer or an outbox.

**Accessing lazy associations after entities detach:** can cause `LazyInitializationException`. Use proper fetch strategies or projections.

**Holding mutable caches in shared singletons:** jobs/partitions can overwrite state. Use proper scopes and concurrency models.

**Failing to test restarts with changing references:** the same item may be enriched differently after restart. Pin reference versions or record decisions.

**Testing the processor solely with mocks:** misses N+1, transaction, rate limit, or restart bugs. Add suitable integration/performance tests.

## 36. Production enrichment processor design workflow

First, identify what data must be supplemented, which source owns it, and which timestamp/version governs lookups. Validate mandatory inputs before lookups; use a clear output model distinguishing source fields from enriched fields. Choose among query joins, bulk lookups, preloading, and caching based on dataset size and key repetition frequency.

Next, implement the processor statelessly or with controlled `StepExecution`-scoped state. Use services/repositories for lookups, set timeouts on remote calls, and classify missing references vs. transient errors with distinct exceptions/result types. Do not perform write side effects inside the processor. Configure retries for recoverable errors, skip/quarantine for permitted record errors, and fail for critical config/infrastructure errors.

Finally, test successful lookups, missing references, caching, tenant isolation, business dates, retries, skips, restarts, and concurrency. Measure query/request counts, latency, cache hit ratios, and memory under large datasets. If enrichment results must stay identical across restarts, pin reference snapshots/versions or persist required decisions in durable storage.

An enrichment processor supplements items so they have complete information for downstream processing and writing. A strong design separates validation, lookup, and mapping; avoids N+1 queries; controls caches and reference versions; and distinguishes missing data from infrastructure errors. When processors avoid side effects, queries and parameters stay stable, writers are idempotent, and integration tests cover restarts, batches can enrich data efficiently while preserving resilience and auditability.
