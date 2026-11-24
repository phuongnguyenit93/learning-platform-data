# Mapping processor

In Spring Batch, a Mapping processor is a pattern for using `ItemProcessor` to transform an item from an input data type into an output data type suitable for the next processing step. For example, a reader reads `OrderEntity` from a database, a processor converts the entity into `OrderExportDto`, and a writer writes the DTO to CSV, XML, or a target table.

A mapping processor separates the source data structure from the target data structure. The reader is responsible for fetching data, the processor converts and normalizes data according to business rules, and the writer persists the result. When this boundary is clear, changes to the database schema or integration format have minimal impact on the rest of the Job.

## 1. What is a Mapping processor?

Spring Batch defines `ItemProcessor` with two generic types: an input type `I` and an output type `O`. The `process` method receives an item and returns the processed item.

~~~java
public interface ItemProcessor<I, O> {
    O process(I item) throws Exception;
}
~~~

A mapping processor implements this contract to produce an object of a different type:

~~~text
Reader
  |
  v
OrderEntity
  |
  v
Mapping ItemProcessor
  |
  v
OrderExportDto
  |
  v
Writer
~~~

For example, the reader reads an entity with a relationship to `Customer`, while the receiving system only needs the order ID, customer name, and total amount. The processor can convert the entity into a flat DTO:

~~~java
public record OrderExportDto(
        long orderId,
        String customerName,
        BigDecimal totalAmount,
        String currency) {
}
~~~

~~~java
public class OrderExportProcessor
        implements ItemProcessor<Order, OrderExportDto> {

    @Override
    public OrderExportDto process(Order order) {
        return new OrderExportDto(
                order.getId(),
                order.getCustomer().getName(),
                order.getTotalAmount(),
                order.getCurrency());
    }
}
~~~

The input and output types are declared right in the Step, helping the compiler catch many incompatible component wiring errors.

## 2. Distinguishing mapping in the reader from mapping in the processor

Not every data transformation needs to live in `ItemProcessor`. You should distinguish two mapping layers:

| Location | Responsibility | Example |
|---|---|---|
| `RowMapper` of a JDBC reader | Converts a `ResultSet` row into a Java object | `id`, `amount` columns into `Order` |
| `ItemProcessor` | Transforms or applies business rules on a read item | `Order` into `OrderExportDto` |
| `FieldSetMapper` of a file reader | Converts fields of a file line into a Java object | CSV row into `CustomerInput` |
| Writer/Marshaller | Converts an output object into a storage format | DTO into SQL parameters or XML |

If SQL returns a `customer_name` column and the reader can map directly to an appropriate projection, there is no need to build a complex entity only to convert it again. Conversely, if normalization, calculations, or business rules are needed, the processor is the right place.

A useful rule of thumb is to have the reader return a model representing the source data, the processor produce the model needed for the next step, and the writer focus on output.

## 3. When should you use a Mapping processor?

A mapping processor is useful when input and output have different structures or when data needs to be normalized before writing.

Common scenarios:

- Database entity converted into a DTO for an API or file export.
- CSV input converted into a domain command.
- Legacy data migrated to a new schema.
- Multiple source fields merged into one target field.
- One source field split into multiple output fields.
- Enums or status codes translated into contract values.
- Dates, times, currencies, and decimals standardized.
- Nested data flattened into a record.
- Internal fields stripped from exported data.
- An item converted into an intermediate model for another writer to handle.

There is no need to create a mapping processor solely to rename a local variable or perform a simple conversion already supported by the reader/writer. Use a processor when the transformation is a meaningful step in the pipeline and needs to be tested independently.

## 4. Separating the domain model from the output DTO

The domain model reflects internal application rules and structure. The output DTO reflects the contract required by the receiving system. The two models often have different change lifecycles.

Example entity:

~~~java
public class Order {
    private Long id;
    private Customer customer;
    private BigDecimal totalAmount;
    private OrderStatus status;
    private Instant createdAt;

    // getters
}
~~~

Export file DTO:

~~~java
public record OrderExportDto(
        String orderNumber,
        String customerName,
        String statusCode,
        String createdDate,
        String amount) {
}
~~~

Mapping processor:

~~~java
public class OrderExportProcessor
        implements ItemProcessor<Order, OrderExportDto> {

    private static final DateTimeFormatter DATE_FORMAT =
            DateTimeFormatter.ISO_LOCAL_DATE;

    @Override
    public OrderExportDto process(Order order) {
        return new OrderExportDto(
                order.getId().toString(),
                order.getCustomer().getName(),
                order.getStatus().getCode(),
                DATE_FORMAT.format(
                        order.getCreatedAt()
                                .atZone(ZoneOffset.UTC)
                                .toLocalDate()),
                order.getTotalAmount().toPlainString());
    }
}
~~~

The DTO can evolve with the file/API version without forcing the domain entity to carry annotations or fields dedicated to each consumer. If multiple output formats share the same domain model, each Step can have its own processor and DTO.

Do not pack the entire entity graph into a DTO if the writer only needs a few fields. Smaller output objects reduce memory footprint and clarify the contract.

## 5. Manual mapping

For small mappings, manual mapping is often easy to read and control:

~~~java
public class CustomerProcessor
        implements ItemProcessor<CustomerInput, Customer> {

    @Override
    public Customer process(CustomerInput input) {
        Customer customer = new Customer();
        customer.setExternalId(input.externalId().trim());
        customer.setName(input.name().trim());
        customer.setEmail(normalizeEmail(input.email()));
        customer.setActive(true);
        return customer;
    }

    private String normalizeEmail(String email) {
        return email == null
                ? null
                : email.trim().toLowerCase(Locale.ROOT);
    }
}
~~~

Advantages of manual mapping:
- Directly visible which fields are copied or transformed.
- Easy to apply conditional business rules.
- No extra mapping library required.
- Easy to handle default or computed fields.

When the number of fields grows, manual code can become verbose and easy to miss new fields. Organize mappings into dedicated methods or mappers so the processor does not turn into a class containing all application rules.

## 6. Using MapStruct for many-field mappings

MapStruct is a compile-time code generation library for mapping. Developers declare interfaces and annotations, and the annotation processor generates Java implementations. Mapping does not require runtime reflection for each field.

Example:

~~~java
@Mapper(componentModel = "spring")
public interface OrderMapper {

    @Mapping(target = "orderNumber", source = "id")
    @Mapping(target = "customerName", source = "customer.name")
    @Mapping(target = "statusCode", source = "status.code")
    @Mapping(target = "amount", source = "totalAmount")
    OrderExportDto toExportDto(Order order);
}
~~~

The processor uses the injected mapper:

~~~java
@Component
public class OrderMappingProcessor
        implements ItemProcessor<Order, OrderExportDto> {

    private final OrderMapper mapper;

    public OrderMappingProcessor(OrderMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public OrderExportDto process(Order item) {
        return mapper.toExportDto(item);
    }
}
~~~

You need to configure the MapStruct annotation processor in the build and pick a version compatible with the project's Java/compiler version. With the Spring component model, the generated implementation is registered as a Spring bean for injection.

MapStruct suits mappings with many fields, nested properties, or many DTOs. Complex business rules should still be expressed in the processor or a separate service, rather than stuffing all logic into annotations.

## 7. Controlling unmapped fields

When schemas change, a new field can easily be forgotten in a DTO. With a mapper generator, you can configure the unmapped target/source policy to warn or fail the build when a mapping is missing.

Example:

~~~java
@Mapper(
    componentModel = "spring",
    unmappedTargetPolicy = ReportingPolicy.ERROR)
public interface CustomerMapper {

    CustomerExportDto toExportDto(Customer customer);
}
~~~

The `ERROR` policy is useful when the target DTO has a contract requiring complete mapping. However, some fields are intentionally unmapped, such as metadata populated in a later step. Explicitly declare those fields with ignore or default mapping so the compiler and reviewers understand the intent.

Do not suppress all mapping warnings just to get the build passing. A new field in the output contract could silently remain null or default without anyone noticing.

## 8. Mapping nested objects and flattening data

The source may contain nested objects:

~~~text
Order
  |
  +-- id
  +-- totalAmount
  +-- customer
        |
        +-- name
        +-- address
              |
              +-- city
              +-- country
~~~

The output may be a flat record:

~~~text
orderId, customerName, city, country, totalAmount
~~~

MapStruct can access nested properties via source paths:

~~~java
@Mapper(componentModel = "spring")
public interface OrderFlatMapper {

    @Mapping(target = "orderId", source = "id")
    @Mapping(target = "customerName", source = "customer.name")
    @Mapping(target = "city", source = "customer.address.city")
    @Mapping(target = "country", source = "customer.address.country")
    @Mapping(target = "totalAmount", source = "totalAmount")
    OrderFlatDto toDto(Order order);
}
~~~

Clearly define behavior when `customer` or `address` is null. If data may lack relationships, the mapping must intentionally produce null/default results, or validation must reject the item before accessing nested properties.

Do not assume every nested association is already loaded. When using ORM lazy loading, the processor can trigger additional queries for each item and cause an N+1 problem.

## 9. Mapping and N+1 queries

A mapping processor might access lazy relationships such as `order.getCustomer().getName()`. If the reader returns entities and the persistence context has not pre-fetched the relationship, each item can trigger an extra query.

For example, a chunk of 500 `Order` items can cause:
- One query to read the list of Orders.
- Up to 500 additional queries to fetch Customer.
- Even more queries if the mapper traverses deeper associations.

How to handle it:
- Use query projections/joins to fetch exactly the needed data.
- Configure an appropriate fetch strategy.
- Use DTO projections from the reader when entities are not needed.
- Batch-fetch relationships if the ORM supports it.
- Measure query counts in integration tests or production-like environments.

Do not solve N+1 by having the processor call a repository once per item if the data can be fetched in batches. Mapping should transform already-available data; fetching additional data needs to be designed and measured separately.

## 10. Mapping data types

A mapping processor often needs to convert between different Java types or representations:

| Source | Target | Notes |
|---|---|---|
| Long | String | ID formatting rules |
| BigDecimal | String | Precision, scale, and locale |
| Instant | LocalDate/String | Timezone and format |
| Enum | String/code | Stable contract, independent of internal enum names |
| Boolean | Y/N or 1/0 | Consumer convention |
| Collection | Single field or multiple items | Separator, escaping, and ordering |
| Nested object | Flat DTO | Nulls and lazy loading |
| Nullable value | Optional/default | Distinguish null from default values |

Example of converting `BigDecimal`:

~~~java
String formatAmount(BigDecimal amount) {
    return amount == null
            ? null
            : amount.setScale(2, RoundingMode.HALF_UP)
                    .toPlainString();
}
~~~

Do not use `double` for currency when decimal precision is required. Do not use `NumberFormat` with the server's default locale if the output contract requires a fixed decimal point.

## 11. Dates, times, and timezones

Dates and times are a common source of mapping bugs. `Instant` represents a point on the timeline; `LocalDateTime` carries no timezone; `LocalDate` represents only a date.

Example converting `Instant` to a UTC date:

~~~java
LocalDate toUtcDate(Instant value) {
    return value.atZone(ZoneOffset.UTC).toLocalDate();
}
~~~

If the consumer requires an ISO-8601 timestamp with offset:

~~~java
String toIsoTimestamp(Instant value) {
    return DateTimeFormatter.ISO_INSTANT.format(value);
}
~~~

Lock down the timezone per the contract:
- UTC for timestamps exchanged between systems.
- Business timezone if reports are grouped by local date.
- Explicit offset if the consumer needs to interpret the exact instant.
- Do not rely on the JVM's default timezone.

Test cases near midnight, daylight saving time transitions where applicable, nulls, and values with nanosecond/millisecond precision.

## 12. Mapping enums and business codes

Do not use `enum.name()` as the output contract if internal enum names may change. Example Java enum:

~~~java
public enum OrderStatus {
    NEW,
    IN_PROGRESS,
    COMPLETED,
    CANCELLED
}
~~~

Consumers may require dedicated codes:

~~~java
public enum OrderStatus {
    NEW("N"),
    IN_PROGRESS("P"),
    COMPLETED("C"),
    CANCELLED("X");

    private final String code;

    OrderStatus(String code) {
        this.code = code;
    }

    public String getCode() {
        return code;
    }
}
~~~

The mapper uses the code instead of the enum name:

~~~java
@Mapping(target = "status", source = "status.code")
OrderExportDto toDto(Order order);
~~~

If a code is undefined or a new enum constant is introduced, decide whether to fail, reject, or map to `UNKNOWN`. Do not silently send `null` if the consumer requires a mandatory status.

## 13. Conditional mapping

Some target fields depend on multiple source fields or business rules.

Example determining customer type:

~~~java
CustomerType mapCustomerType(Customer customer) {
    if (customer.isCorporate()) {
        return CustomerType.BUSINESS;
    }

    if (customer.getBirthDate() == null) {
        return CustomerType.UNKNOWN;
    }

    return CustomerType.PERSONAL;
}
~~~

You can call a helper method from the mapper or perform the logic in the processor before invoking the mapper. When rules have many branches, extract them into a clearly named policy/service for isolated testing.

Do not let mapping rely solely on field copying while accidentally dictating business behavior. If a transformation affects business semantics, document the rule, version it, and test boundary cases.

## 14. Mapping multiple inputs into one output

`ItemProcessor` receives one item and returns at most one output item. It is not a natural API for aggregating multiple items into a single record. If you need to aggregate multiple inputs, consider:
- Aggregation inside a processor with explicitly managed state.
- An `ItemReader` that returns groups/aggregates.
- Grouping by key in the database query.
- A custom reader or tasklet for an aggregation unit.
- A writer that handles collections under a specific contract.

Do not accumulate every item of the Job into a list inside a singleton processor. That causes memory to grow with the entire input, complicates restarts, and can mix state across executions.

## 15. Mapping one input into multiple outputs

A standard `ItemProcessor` returns one output object or `null` to filter. If one input needs to generate multiple output records, you can use:
- An output object containing a collection for the writer to unpack.
- A processor creating a wrapper/group item.
- A custom processor/writer adapter with a clear contract.
- Splitting into Steps to flatten the collection into an item stream.

Do not return `List<T>` expecting Spring Batch to automatically flatten the list into multiple items. With the `ItemProcessor<I,O>` signature, `List<T>` is simply a single output item of type `List<T>` if the writer is configured to accept that type.

If fan-out is needed, explicitly design output counts, ordering, transaction, and restart semantics.

## 16. Combining mapping processor with validation

Mapping and validation are two distinct responsibilities. A processor transforms data, while a validator checks inputs or outputs against the contract.

Example:
- Validate input before mapping to catch nulls or invalid codes.
- Map from source to DTO.
- Validate the output DTO to ensure required fields and formats are valid.
- Reject or skip per policy if data is invalid.

Spring Batch provides `ValidatingItemProcessor` and `BeanValidatingItemProcessor` in corresponding versions. `BeanValidatingItemProcessor` can use Bean Validation annotations on objects; configure the validator/provider and verify APIs for your version.

Example DTO:

~~~java
public record CustomerExportDto(
        @NotBlank String externalId,
        @NotBlank String name,
        @Email String email) {
}
~~~

Validation should produce specific errors tied to a business key for easy investigation. Do not turn every mapping error into a filter by returning `null`; only filter when that item type is permitted by business rules to be skipped.

## 17. Null return means filtering the item

Per the `ItemProcessor` contract, if `process` returns `null`, the item is filtered and is not sent to the writer.

Example:

~~~java
@Override
public OrderExportDto process(Order order) {
    if (order.getStatus() == OrderStatus.CANCELLED) {
        return null;
    }

    return mapper.toExportDto(order);
}
~~~

This differs from an exception:
- Return `null`: intentionally excludes the item; not an error.
- Throw an exception: signals a processing error; the Step may fail, retry, or skip depending on configuration.
- Return a DTO with `REJECTED` status: the item still proceeds to the writer and can be saved to a reject output.

Choose a consistent representation. If filtered items need auditing, record them via a listener/metrics or a dedicated flow. Do not use `null` to hide errors in mandatory data.

## 18. Combining multiple processors

`CompositeItemProcessor` allows chaining multiple `ItemProcessor` instances in sequence. The output of an earlier processor becomes the input of the next processor.

Example:

~~~text
OrderInput
    |
    v
NormalizeOrderProcessor
    |
    v
NormalizedOrder
    |
    v
ValidateOrderProcessor
    |
    v
ValidatedOrder
    |
    v
OrderMappingProcessor
    |
    v
OrderExportDto
    |
    v
Writer
~~~

Configuration:

~~~java
@Bean
CompositeItemProcessor<OrderInput, OrderExportDto> orderProcessor(
        ItemProcessor<OrderInput, NormalizedOrder> normalizeProcessor,
        ItemProcessor<NormalizedOrder, ValidatedOrder> validateProcessor,
        ItemProcessor<ValidatedOrder, OrderExportDto> mappingProcessor) {

    return new CompositeItemProcessorBuilder<
            OrderInput, OrderExportDto>()
            .delegates(
                    normalizeProcessor,
                    validateProcessor,
                    mappingProcessor)
            .build();
}
~~~

Generic types must match across the chain: the output of the preceding processor must be compatible with the input of the following processor. Splitting steps gives each processor a single responsibility and allows independent unit testing.

If a delegate returns `null`, the item is filtered and does not continue through subsequent processors. If a delegate throws an exception, the Step's fault-tolerance policy determines whether to retry, skip, or fail.

## 19. Selecting a processor with a classifier

`ClassifierCompositeItemProcessor` is appropriate when a single Step handles multiple input types and needs to select a different processor per item.

Example:
- `ORDER` event type uses `OrderProcessor`.
- `PAYMENT` event type uses `PaymentProcessor`.
- `CUSTOMER` event type uses `CustomerProcessor`.

The selected processors need a common output type compatible with the writer, or a shared supertype/envelope. Generic types cannot be ignored: `ItemProcessor<Order, OrderDto>` cannot arbitrarily substitute for `ItemProcessor<BaseEvent, ExportRecord>`.

The classifier picks the processor; the processor performs the mapping. If every item uses the same mapping, using an `ItemProcessor` directly is simpler.

## 20. Attaching a Mapping processor to a Step

In Spring Batch 5, `StepBuilder` declares input and output types on `chunk`:

~~~java
@Bean
Step exportOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ItemProcessor<Order, OrderExportDto> orderProcessor,
        ItemWriter<OrderExportDto> orderWriter) {

    return new StepBuilder("exportOrdersStep", jobRepository)
            .<Order, OrderExportDto>chunk(200, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
~~~

Key points to note:
- The Step's input generic must match the type returned by the reader.
- The Step's output generic must match the type returned by the processor and accepted by the writer.
- Without a processor, input and output are usually the same type.
- The processor is invoked for each item before the writer receives the processed chunk.
- Filtered items are not sent to the writer.

In older Spring Batch versions, Step creation and `ItemWriter` signatures may differ. Use APIs consistent with your application's dependency version.

## 21. Mapping and chunk transactions

A processor runs within the chunk processing flow but does not create its own transaction. Transaction boundaries are controlled by the Step/transaction manager. If the processor only transforms in-memory objects, the mapping operation typically has no side effects requiring rollback.

If the processor calls a database or external service, note:
- Additional queries may participate in the current transaction depending on how connections are acquired.
- HTTP calls do not automatically roll back with a JDBC transaction.
- External service calls may repeat when a chunk retries.
- Mappings dependent on mutable data can produce different results on restart.

Prefer pure, deterministic processors without side effects. If database enrichment is needed, consider joining in the reader, batch preloading lookups, or versioned caching. If calling external services is necessary, use idempotency and define retry behavior clearly.

## 22. Deterministic mapping across retries and restarts

The same input under the same rule set should produce the same output. If mapping depends on:
- Current wall-clock time.
- Default JVM locale or timezone.
- Configuration that can change while the Job is running.
- An external service returning dynamic results.
- Random numbers or counters.
- Mutable singleton state.

then retries/restarts may produce different output from the initial run.

To preserve stability:
- Use explicitly specified timezones and locales.
- Pin mapping/configuration versions in `JobParameters`.
- Use input snapshots or stable source data.
- Do not use random values or counters for business fields.
- Persist mapping decisions if they cannot be reproduced.
- Keep the same mapping version when restarting an existing `JobInstance`.

If output format changes across versions, create a separate DTO or mapper version. Do not deploy a new mapper and restart a `JobInstance` that needs to resume with old semantics without a migration plan.

## 23. Statelessness and thread safety

Processors are typically declared as singleton Spring beans. If a processor only holds an immutable mapper and stores no per-item state, sharing it is usually safe.

Avoid:
- Storing the current item in a field.
- Using a mutable `List` as an accumulator for the whole Job.
- Using a shared non-thread-safe `SimpleDateFormat`.
- Incrementing a counter to generate business keys.
- Holding an `EntityManager` or `ResultSet` outside its managed lifecycle.
- Saving `JobParameters` from a previous execution in a singleton field.

If Job- or Step-scoped data is needed, use `@StepScope` or `@JobScope` and pass the appropriate parameters. Scope alone does not make a processor safe when multiple threads call it within one Step; you still must avoid mutable shared state or synchronize properly.

## 24. Mapping and performance

Mapping is usually an in-memory CPU operation, but it can become a bottleneck if:
- Creating large object graphs.
- Repeatedly formatting dates/currencies with improperly reused formatters.
- Querying the database on every `process` call.
- Parsing large JSON/XML payloads per item.
- Using reflection or dynamic conversions repeatedly.
- Unnecessarily copying large collections.

Optimization directions:
- Use small DTOs containing only the fields the writer needs.
- Use MapStruct for many-field mappings where appropriate.
- Reuse immutable/thread-safe formatters like `DateTimeFormatter`.
- Avoid N+1 queries.
- Compute only necessary output values.
- Measure CPU, allocations, and throughput on representative data.

Do not optimize solely based on mapper call counts. Profile the entire pipeline because database read times, transaction commits, or output I/O often outweigh mapping overhead.

## 25. Logging and observing mapping errors

When mapping fails, you need to know which item caused the error and which field was invalid. Include the business key in the exception or log context:

~~~java
@Override
public OrderExportDto process(Order order) {
    try {
        return mapper.toExportDto(order);
    } catch (RuntimeException exception) {
        throw new OrderMappingException(
                "Cannot map order id=" + order.getId(),
                exception);
    }
}
~~~

Do not log entire entities or payloads if they contain personal data, tokens, or sensitive information. Log only the business key, `JobExecution` ID, Step name, mapper version, and necessary error details.

If an exception is skippable, record the item and reason via a `SkipListener`. If a mapping error is a configuration bug affecting every item, fail the Job early instead of skipping massive numbers of records.

## 26. Testing a Mapping processor

Unit testing the processor directly verifies mappings without launching a Job.

Example:

~~~java
@Test
void mapsOrderToExportDto() throws Exception {
    Order order = new Order(
            101L,
            customer("Acme"),
            new BigDecimal("125.50"),
            OrderStatus.COMPLETED,
            Instant.parse("2026-01-10T12:00:00Z"));

    OrderExportDto result = processor.process(order);

    assertEquals("101", result.orderNumber());
    assertEquals("Acme", result.customerName());
    assertEquals("C", result.statusCode());
    assertEquals("125.50", result.amount());
}
~~~

What to test:
- Basic field mapping.
- Nested properties.
- Nulls in associations or optional fields.
- Decimal precision/scale.
- Date/time and timezone handling.
- Enum/code mapping.
- Default values.
- Filter conditions returning `null`.
- Invalid input throwing expected exceptions.
- Same input and same rules yielding identical output.
- Newly added or unmapped fields.

With MapStruct, you can test the Spring-injected implementation or instantiate the generated mapper depending on configuration. Beyond unit tests, integration tests are needed when the mapper is a Spring bean and the processor is wired into a Step.

## 27. Testing the processor in a Step

Unit tests do not prove generic wiring between reader, processor, and writer is correct. Integration tests should verify that mapped data is received and written accurately by the writer.

Example:
1. Insert a few Orders into a test database.
2. Launch the Step with the reader, mapping processor, and writer.
3. Verify read and write counts.
4. Query the output table or read the output file.
5. Compare transformed fields.
6. Verify filtered or rejected items per policy.
7. Re-run the test with an error in one chunk to verify retry/restart.

Do not just assert that the Step `COMPLETED`. Inspect output contents, business keys, and record counts. If the processor filters an item, the write count will be lower than the read count; tests must assert the exact expected behavior.

## 28. Testing composition and multi-step mapping

If using `CompositeItemProcessor`, test both delegate ordering and data types between steps.

Example:
- Normalize first.
- Validate after normalization.
- Map to the final DTO.

Tests should verify:
- The first processor receives the right input.
- Subsequent processors receive normalized output.
- Null at any step halts the chain per filter semantics.
- Exceptions propagate up to the Step.
- Delegate order is not inverted.
- Final output matches the contract.

Test each delegate individually and include integration tests for the composite. Do not mock every processor in every test; a test using real implementations catches wiring and mapping bugs.

## 29. Common pitfalls

**Putting all mapping into RowMapper.** The reader becomes tightly coupled to the target format and hard to reuse.

**Using domain entities as the output contract.** Internal changes can break consumers.

**Mapping nested associations causing N+1 queries.** The Job slows down as item counts grow.

**Failing to handle null nested objects.** The processor throws `NullPointerException` on missing data.

**Using default timezone/locale.** Output can vary across environments.

**Using `enum.name()` as integration codes.** Renaming an enum can break downstream contracts.

**Using `double` for currency.** Can introduce decimal rounding errors.

**Mixing mapping and side effects in one processor.** Retries can repeat side effects outside the transaction.

**Processor holding mutable state in a singleton.** Multiple executions or threads can corrupt each other.

**Returning `null` to hide mapping errors.** Items disappear without auditing.

**Expecting one input to automatically fan out into multiple outputs.** `ItemProcessor` only returns a single output item of generic type `O`.

**Not checking Step generic types.** Reader, processor, and writer can be wired with mismatched types.

**Testing the processor solely with mocks.** Fails to catch mapper bugs, nested field issues, or integration wiring errors.

## 30. Mapping processor implementation checklist

When building a mapping processor in Spring Batch, follow this sequence:

1. Identify the input type returned by the reader and the output type expected by the writer.
2. Decide which mappings belong to `RowMapper`/`FieldSetMapper` and which are business transformations.
3. Design an output DTO or model independent of the domain entity when needed.
4. Choose manual mapping for small logic or MapStruct for many-field mappings.
5. Explicitly specify nested mappings, null handling, enums, decimals, and date/time formats.
6. Separate validation and business rules from field copying when they carry distinct meaning.
7. Keep the processor deterministic, stateless, and free of non-idempotent side effects.
8. Use `CompositeItemProcessor` if you need to chain multiple typed transformation steps.
9. Use `ClassifierCompositeItemProcessor` when you need to select a processor per item type and the API version supports it.
10. Declare Step input/output generics matching reader, processor, and writer.
11. Check for N+1 queries, allocations, and throughput with representative data.
12. Unit test the mapper, nulls, boundaries, timezones, decimals, and filter behavior.
13. Integration test the Step, actual outputs, skip/retry, and restart.
14. Version the mapping if old `JobInstance` executions may be restarted after deployment.

A mapping processor is the transformation layer between the data provided by the reader and the data needed by the writer. When DTOs are separated from domain models, nulls and data types are controlled, mappings remain deterministic, and generic types are accurately declared, a Spring Batch pipeline becomes easier to evolve, test, and recover. MapStruct can reduce boilerplate for large mappings, while the processor remains the coordinator for item-level transformation rules.

