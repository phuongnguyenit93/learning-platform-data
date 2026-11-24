# Validation processor

In Spring Batch, `ItemProcessor` is the place typically used to validate input data, normalize values, apply business rules, and transform items into a data type suitable for the writer. A validation processor helps catch invalid records before writing to the target system, while deciding how to handle errors according to the Job's policies.

Validation in batch processing has an important distinction: an invalid item does not always mean the Job must stop. Sometimes data should be intentionally skipped, sometimes it must be written to a reject output for investigation, and sometimes it must fail the Step because data or configuration cannot safely continue.

Three common outcomes:

- **Valid:** the processor returns the validated or transformed item for the writer to process.
- **Intentional filter:** the processor returns `null`; Spring Batch does not pass that item to the writer.
- **Invalid:** the processor throws an exception; the Step applies skip, retry, or fail according to configuration.

Do not use `null` to hide validation errors. `null` means the item was filtered by processing logic, whereas an exception indicates an error that must be handled according to policy. If failed records need to be saved, there must be a reject flow or an appropriate audit mechanism.

## 1. Role of the validation processor

A batch pipeline typically looks like this:

~~~text
Input file / Database / Message
              |
              v
          ItemReader
              |
              v
       ValidationProcessor
              |
              v
       BusinessProcessor
              |
              v
          ItemWriter
              |
              v
        Target database
~~~

The validation processor checks data structure and rules before downstream steps consume the item. For example, with an order:

- `orderId` must be present and greater than 0.
- `customerCode` must not be blank.
- `totalAmount` must be greater than or equal to 0.
- `currency` must be in the supported list.
- `orderDate` must not be in the future if business rules forbid it.
- `quantity` must be greater than 0.

Validation should happen as early as possible after reading and parsing data. When an item is invalid, detecting it before calling external services or writing to the database reduces processing cost and avoids unnecessary side effects.

However, a validation processor does not need to contain every single rule. It helps to divide responsibilities:

| Validation category | Example | Typically appropriate location |
| --- | --- | --- |
| Structure/data type | JSON field is numeric, date parses cleanly | Reader or parser |
| Field-level validation | Customer code is not blank | DTO/Bean Validation |
| Cross-field validation | End date is after start date | Class-level constraint or validator |
| Business validation | Customer is active, credit limit is sufficient | Domain service or processor |
| External validation | Tax ID verified by partner service | Dedicated service with timeout/retry |

Do not push every parse error into the processor if the reader cannot construct the object yet. Likewise, do not put all business rules into annotations when rules require a database, current time, or external systems.

## 2. Designing the input DTO

Example of order data read from CSV or JSON:

~~~java
public record OrderInput(
        Long orderId,
        String customerCode,
        BigDecimal totalAmount,
        String currency,
        LocalDate orderDate,
        Integer quantity) {
}
~~~

The DTO should accurately represent the data received from the source. Use wrapper types like `Long` and `Integer` when you need to distinguish missing fields from zero values. Use `BigDecimal` for money to avoid floating-point rounding errors.

Keep the input DTO separate from the database entity if source and target schemas differ. That way, validation checks the source contract before mapping to the internal model.

Example:

~~~java
public record ValidatedOrder(
        long orderId,
        String customerCode,
        BigDecimal totalAmount,
        Currency currency,
        LocalDate orderDate,
        int quantity) {
}
~~~

`ValidatedOrder` represents data that has passed validation and normalization. Using a distinct type saves downstream processors from repeatedly checking for nulls or re-parsing currencies.

Do not create a DTO named `ValidatedOrder` and still allow every field to be null or keep raw, unnormalized values. The type name should reflect the invariants the application actually guarantees.

## 3. Using Jakarta Bean Validation

Jakarta Bean Validation provides annotations to declare constraints on fields, properties, parameters, or classes. Spring Boot typically integrates Hibernate Validator as the provider.

Commonly used annotations:

| Annotation | Meaning |
| --- | --- |
| `@NotNull` | Value must not be null |
| `@NotBlank` | String must not be null, empty, or whitespace-only |
| `@NotEmpty` | String/collection/map must not be empty |
| `@Positive` | Number must be greater than 0 |
| `@PositiveOrZero` | Number must be greater than or equal to 0 |
| `@Min` / `@Max` | Integer bounds |
| `@DecimalMin` / `@DecimalMax` | Decimal bounds |
| `@Size` | String length or collection size |
| `@Pattern` | String must match regular expression |
| `@Email` | String has a valid email format |
| `@Past` / `@Future` | Date or instant in the past/future |

Example DTO:

~~~java
public class OrderInput {

    @NotNull(message = "orderId is required")
    @Positive(message = "orderId must be positive")
    private Long orderId;

    @NotBlank(message = "customerCode is required")
    @Size(max = 30, message = "customerCode is too long")
    private String customerCode;

    @NotNull(message = "totalAmount is required")
    @DecimalMin(value = "0.00", message = "totalAmount must not be negative")
    private BigDecimal totalAmount;

    @NotBlank(message = "currency is required")
    @Pattern(regexp = "VND|USD|EUR", message = "unsupported currency")
    private String currency;

    @NotNull(message = "orderDate is required")
    private LocalDate orderDate;

    @NotNull(message = "quantity is required")
    @Positive(message = "quantity must be positive")
    private Integer quantity;

    // getters and setters
}
~~~

Annotations describe constraints, but they do not run automatically just because an object is constructed. You must call `Validator.validate()` or use framework-triggered validation at the proper boundary.

### @NotNull vs. @NotBlank

For `String`:

- `@NotNull` only forbids null.
- `@NotEmpty` forbids null and empty strings, though whitespace-only strings can still pass.
- `@NotBlank` forbids null, empty strings, and whitespace-only strings.

Choose constraints matching the data contract. For customer codes, `@NotBlank` is usually more appropriate than `@NotNull`.

### Constraints on wrapper types

If a field is an `Integer` and may be null, `@Positive` only checks the value when present; it does not replace `@NotNull`. If the field is mandatory, combine both annotations.

## 4. Creating a Validator and calling it in the processor

You can inject `jakarta.validation.Validator` into the processor:

~~~java
public class OrderValidationProcessor
        implements ItemProcessor<OrderInput, ValidatedOrder> {

    private final Validator validator;

    public OrderValidationProcessor(Validator validator) {
        this.validator = validator;
    }

    @Override
    public ValidatedOrder process(OrderInput input) {
        Set<ConstraintViolation<OrderInput>> violations =
                validator.validate(input);

        if (!violations.isEmpty()) {
            throw new InvalidOrderException(
                    input == null ? null : input.getOrderId(),
                    violations);
        }

        return new ValidatedOrder(
                input.getOrderId(),
                input.getCustomerCode().trim(),
                input.getTotalAmount(),
                Currency.getInstance(input.getCurrency()),
                input.getOrderDate(),
                input.getQuantity());
    }
}
~~~

The example uses a class with getters to illustrate Bean Validation. If the DTO is a record, modern Jakarta Validation providers can support constraints on record components; property access and provider version must match the project.

Registering `Validator` in Spring:

~~~java
@Bean
public LocalValidatorFactoryBean validator() {
    return new LocalValidatorFactoryBean();
}
~~~

Spring Boot can auto-configure `Validator` when the validation dependency is present. In that case, `jakarta.validation.Validator` can be injected directly.

### Do not create a ValidatorFactory per item

Do not call `Validation.buildDefaultValidatorFactory()` on every `process()` invocation. Repeatedly building factories/providers wastes resources and may fail to close factories properly.

Create `Validator` once in the application context and inject it into the processor. `Validator` is designed to be reused once configured.

### Handling null inputs

Bean Validation can validate object graphs, but `validator.validate(null)` is not how to handle a null input object. If a reader or caller might pass null, check upfront:

~~~java
if (input == null) {
    throw new InvalidOrderException(
            null,
            "Input order must not be null");
}
~~~

In Spring Batch, readers normally use `null` to signal EOF and do not invoke the processor for that value. Still, unit tests or custom callers may pass `null` directly.

## 5. Creating structured validation exceptions

Do not merely throw `IllegalArgumentException` with a generic message if you need to classify, log, reject, or aggregate errors.

You can create an exception carrying the business key and error list:

~~~java
public class InvalidOrderException extends RuntimeException {

    private final Long orderId;
    private final List<String> violations;

    public InvalidOrderException(
            Long orderId,
            Collection<? extends ConstraintViolation<?>> violations) {
        super("Order validation failed: " + violations.size()
                + " violation(s)");
        this.orderId = orderId;
        this.violations = violations.stream()
                .map(v -> v.getPropertyPath() + ": " + v.getMessage())
                .sorted()
                .toList();
    }

    public InvalidOrderException(Long orderId, String message) {
        super(message);
        this.orderId = orderId;
        this.violations = List.of(message);
    }

    public Long getOrderId() {
        return orderId;
    }

    public List<String> getViolations() {
        return violations;
    }
}
~~~

The exception can provide:

- Business key or source record ID.
- Field/property path.
- Stable error code.
- Operator-friendly message.
- List of multiple constraint violations.
- Root cause if the error originated from another system.

Do not put full payloads or sensitive data into exception messages. Logs should contain only the fields needed for investigation and comply with data security policies.

## 6. Collecting multiple validation errors in one pass

`Validator.validate()` returns a set of `ConstraintViolation` objects. You can report multiple errors at once instead of stopping at the first invalid field.

Example:

~~~java
Set<ConstraintViolation<OrderInput>> violations =
        validator.validate(input);

if (!violations.isEmpty()) {
    List<String> messages = violations.stream()
            .map(v -> v.getPropertyPath() + ": " + v.getMessage())
            .sorted()
            .toList();

    throw new InvalidOrderException(
            input.getOrderId(),
            messages);
}
~~~

Collecting errors lets users fix multiple fields in a single pass. Use sorting so error ordering is deterministic in logs and tests; do not depend on `Set` iteration order.

Do not collect errors by concatenating unstructured strings that downstream systems must parse back. Keep property paths and error codes as separate fields if reporting or analytics is needed.

## 7. Cross-field validation

Some rules cannot be checked on a single field alone:

- `startDate` must precede `endDate`.
- `currency` must match the country.
- `discount` must not exceed `subtotal`.
- `BUSINESS` customer type requires `taxCode`.
- Sum of line quantities must match order `quantity`.

You can write a class-level constraint:

~~~java
@ValidDateRange
public class BookingInput {

    private LocalDate startDate;
    private LocalDate endDate;

    // getters and setters
}
~~~

Annotation:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = DateRangeValidator.class)
public @interface ValidDateRange {
    String message() default "endDate must not be before startDate";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

Validator:

~~~java
public class DateRangeValidator
        implements ConstraintValidator<ValidDateRange, BookingInput> {

    @Override
    public boolean isValid(
            BookingInput value,
            ConstraintValidatorContext context) {

        if (value == null
                || value.getStartDate() == null
                || value.getEndDate() == null) {
            return true;
        }

        return !value.getEndDate().isBefore(value.getStartDate());
    }
}
~~~

The validator returns `true` when involved fields are null because individual `@NotNull` constraints are responsible for reporting missing data. This avoids producing two errors for the same root cause.

If you want property-specific messages, disable the default violation and attach a violation to the `endDate` property path. When doing so, test null cases, same-day cases, reversed dates, and valid ranges.

## 8. Business validation in the processor

Bean Validation fits constraints on objects. Rules needing domain context should reside in business services.

Example checking whether a customer is active and has enough credit limit:

~~~java
public class OrderBusinessValidationProcessor
        implements ItemProcessor<ValidatedOrder, ValidatedOrder> {

    private final CustomerService customerService;
    private final CreditLimitService creditLimitService;

    public OrderBusinessValidationProcessor(
            CustomerService customerService,
            CreditLimitService creditLimitService) {
        this.customerService = customerService;
        this.creditLimitService = creditLimitService;
    }

    @Override
    public ValidatedOrder process(ValidatedOrder order) {
        Customer customer =
                customerService.findByCode(order.customerCode())
                        .orElseThrow(() ->
                                new InvalidOrderException(
                                        order.orderId(),
                                        "Customer does not exist"));

        if (!customer.isActive()) {
            throw new InvalidOrderException(
                    order.orderId(),
                    "Customer is inactive");
        }

        if (!creditLimitService.hasAvailableCredit(
                customer.id(), order.totalAmount())) {
            throw new InvalidOrderException(
                    order.orderId(),
                    "Credit limit exceeded");
        }

        return order;
    }
}
~~~

This is an illustrative example; checking and reserving credit limits may require a dedicated business transaction. A read-only check does not guarantee the credit limit remains available when the writer executes later if concurrent transactions occur.

### Validation and race conditions

Suppose two Jobs check a remaining credit limit of 100 million simultaneously. Each Job has an order of 80 million. Both may read the same state and conclude it is valid, while their combined commitment exceeds the limit.

If a rule must hold at write time, perform check-and-reserve inside a transaction with locking, optimistic versioning, or a conditional update statement. Processor validation can only observe state at check time; it does not replace database constraints or concurrency control.

## 9. Validation and data normalization

Validation and normalization are related yet distinct:

- Validation checks whether data satisfies the contract.
- Normalization converts valid data into a canonical form.

Example:

~~~java
String normalizedCode = input.getCustomerCode().trim().toUpperCase(Locale.ROOT);
~~~

Before normalizing, verify whether the contract permits leading/trailing whitespace or lowercase characters. Do not automatically alter values that may carry business meaning.

A processor can perform:

1. Check the object and required fields.
2. Normalize whitespace/casing per contract.
3. Re-validate invariants after normalization if needed.
4. Convert to an immutable internal DTO.

For instance, a currency code can be trimmed and uppercased, then parsed with `Currency.getInstance()`. If the code is unsupported, throw `InvalidOrderException` with a clear error code.

Do not use normalization to mask invalid data. If the string `"1,234"` can mean different things depending on locale, enforce an explicit formatting rule before parsing.

## 10. Validation processor and filtering

In Spring Batch, a processor returning `null` means the item is filtered and not passed to the writer:

~~~java
public class IgnoreCancelledOrderProcessor
        implements ItemProcessor<OrderInput, OrderInput> {

    @Override
    public OrderInput process(OrderInput input) {
        if (input.status() == OrderStatus.CANCELLED) {
            return null;
        }
        return input;
    }
}
~~~

This is an intentional filter if business rules state `CANCELLED` orders are out of scope.

Do not write:

~~~java
if (input.getOrderId() == null) {
    return null;
}
~~~

if a missing `orderId` is a data error requiring investigation. Doing so drops the item from the pipeline without incrementing skip count or creating a reject record.

### Distinguishing filtering from validation failure

| Situation | Appropriate outcome |
| --- | --- |
| Item excluded by normal business criteria | Return `null` |
| Required field missing or malformed | Throw validation exception |
| Unsupported item that must be retained | Reject/DLQ or skippable exception |
| External system temporarily unresponsive | Transient exception for retry |
| Configuration or schema unsafe to continue | Fail Step/Job |

Filtering is normally not counted as skipping. If filtered item counts are needed, use a filter listener or an appropriately scoped `StepExecution` counter.

## 11. Validation processor with skip policy

If invalid data can be bypassed while continuing to process other records, configure a fault-tolerant Step:

~~~java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, ValidatedOrder> processor,
        ItemWriter<ValidatedOrder> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, ValidatedOrder>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .skip(InvalidOrderException.class)
            .skipLimit(100)
            .build();
}
~~~

In this example, validation errors are treated as skippable record errors. If total skips exceed the limit, the Step fails. Skip configuration must reflect business requirements; do not skip every `RuntimeException`.

### Skipping in the processor

When the processor throws `InvalidOrderException` and the exception is configured as skippable:

- The failing item is skipped.
- Remaining items in the chunk can proceed per fault-tolerant behavior.
- Skip count is updated.
- `SkipListener` can receive the item and exception to record the rejection.

Errors occurring during read or write have different semantics from processor errors. Classify exceptions by stage to avoid accidentally skipping infrastructure errors or write failures.

### Retry vs. skip

Retries suit self-healing errors such as brief timeouts or deadlocks. Validation errors are usually deterministic data defects; retrying the same input does not make data valid.

Example:

~~~java
.faultTolerant()
.skip(InvalidOrderException.class)
.skipLimit(100)
.retry(TransientDataAccessException.class)
.retryLimit(3)
~~~

Do not include `InvalidOrderException` in the retry policy unless a step fixes the data before the next attempt.

## 12. Reject records and SkipListener

Skipping lets the Step continue, but bypassing an item does not automatically save the raw record or failure reason. If auditing is needed, use a `SkipListener`:

~~~java
public class OrderSkipListener
        implements SkipListener<OrderInput, ValidatedOrder> {

    private final RejectRecordService rejectRecordService;

    public OrderSkipListener(RejectRecordService rejectRecordService) {
        this.rejectRecordService = rejectRecordService;
    }

    @Override
    public void onSkipInProcess(
            OrderInput item,
            Throwable throwable) {

        if (throwable instanceof InvalidOrderException invalid) {
            rejectRecordService.record(
                    item.orderId(),
                    invalid.getViolations());
        }
    }

    @Override
    public void onSkipInRead(Throwable throwable) {
        // No item exists if the error occurred before the reader constructed the object.
    }

    @Override
    public void onSkipInWrite(
            ValidatedOrder item,
            Throwable throwable) {
        // Handle writer errors according to a dedicated policy.
    }
}
~~~

Register the listener:

~~~java
.faultTolerant()
.skip(InvalidOrderException.class)
.skipLimit(100)
.listener(orderSkipListener)
~~~

`SkipListener` provides separate callbacks for read, process, and write. For validation errors inside the processor, the corresponding callback is `onSkipInProcess`.

### Transactional reject recording

If `rejectRecordService` writes to the same database, verify which transaction the callback uses in your Spring Batch version. Skip listeners are designed to report skipped items; callbacks are normally invoked right before chunk commit to avoid writing duplicate rejects during transaction retries.

Nevertheless, never assume an API call or file write inside a listener will roll back with the transaction. If the reject output resides in an external system, use an outbox or idempotent mechanism. If the reject table must commit together with batch metadata, use the same transaction manager and write integration tests.

### Do not lose the raw record

If the reader parses data into a DTO before validation, the raw record representation may already be lost. When precise investigation is required, keep source line, file name, line number, or message ID in DTO metadata.

Do not log full sensitive raw payloads. Reject stores must have appropriate access control, retention, and masking.

## 13. Alternative: representing validation results

In some systems, you want to write both valid and invalid items in the same flow without using skips. You can create a wrapper:

~~~java
public record ValidationResult<T>(
        T original,
        T validValue,
        List<ValidationError> errors) {

    public boolean isValid() {
        return errors.isEmpty();
    }
}
~~~

The processor does not throw exceptions for persistable business errors:

~~~java
public class OrderValidationResultProcessor
        implements ItemProcessor<OrderInput, ValidationResult<ValidatedOrder>> {

    private final Validator validator;

    @Override
    public ValidationResult<ValidatedOrder> process(OrderInput input) {
        Set<ConstraintViolation<OrderInput>> violations =
                validator.validate(input);

        if (!violations.isEmpty()) {
            List<ValidationError> errors = violations.stream()
                    .map(v -> new ValidationError(
                            v.getPropertyPath().toString(),
                            "INVALID_FIELD",
                            v.getMessage()))
                    .toList();

            return new ValidationResult<>(null, null, errors);
        }

        return new ValidationResult<>(
                null,
                toValidatedOrder(input),
                List.of());
    }
}
~~~

The writer can separate valid items and reject records:

~~~java
public class ValidationResultWriter
        implements ItemWriter<ValidationResult<ValidatedOrder>> {

    private final ItemWriter<ValidatedOrder> validWriter;
    private final RejectWriter rejectWriter;

    @Override
    public void write(
            Chunk<? extends ValidationResult<ValidatedOrder>> chunk)
            throws Exception {

        List<ValidatedOrder> valid = new ArrayList<>();
        List<RejectRecord> rejected = new ArrayList<>();

        for (ValidationResult<ValidatedOrder> result : chunk) {
            if (result.isValid()) {
                valid.add(result.validValue());
            } else {
                rejected.add(toRejectRecord(result));
            }
        }

        if (!valid.isEmpty()) {
            validWriter.write(new Chunk<>(valid));
        }

        if (!rejected.isEmpty()) {
            rejectWriter.write(rejected);
        }
    }
}
~~~

This pattern applies when validation errors are business outcomes to be stored rather than exceptions triggering Step skips. The writer must handle both outputs under a clear transaction strategy. If `validWriter` commits independently and `rejectWriter` fails, both outputs can diverge; share a database transaction or use an outbox/staging pattern when needed.

The wrapper should retain the original item or source metadata if reject records need the raw input. The snippet above is simplified to highlight the flow.

## 14. Validation groups

A DTO may be used across multiple stages with different requirements. Jakarta Validation groups allow executing a specific subset of constraints per stage.

Declare groups:

~~~java
public interface ImportChecks {
}

public interface ApprovalChecks {
}
~~~

DTO:

~~~java
public class PaymentInput {

    @NotNull(groups = ImportChecks.class)
    private String paymentId;

    @NotNull(groups = ImportChecks.class)
    @Positive(groups = ImportChecks.class)
    private BigDecimal amount;

    @NotBlank(groups = ApprovalChecks.class)
    private String approver;
}
~~~

The processor invokes the corresponding group:

~~~java
Set<ConstraintViolation<PaymentInput>> violations =
        validator.validate(input, ImportChecks.class);
~~~

In the approval Step:

~~~java
validator.validate(input, ApprovalChecks.class);
~~~

If multiple groups must run in sequence and stop when an earlier group fails, Jakarta Validation supports `GroupSequence`. Configure group sequences carefully because group ordering affects results.

Do not use validation groups to replace separate DTOs when two stages have vastly different contracts. If a single object accumulates confusing stage-specific states and constraints, defining separate types per boundary is usually clearer.

## 15. Custom constraints and validators

When a rule is reused across multiple DTOs, create a custom annotation:

~~~java
@Target({
        ElementType.FIELD,
        ElementType.PARAMETER,
        ElementType.ANNOTATION_TYPE
})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = SupportedCurrencyValidator.class)
public @interface SupportedCurrency {
    String message() default "currency is not supported";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

Validator:

~~~java
public class SupportedCurrencyValidator
        implements ConstraintValidator<SupportedCurrency, String> {

    private static final Set<String> SUPPORTED =
            Set.of("VND", "USD", "EUR");

    @Override
    public boolean isValid(
            String value,
            ConstraintValidatorContext context) {
        return value == null || SUPPORTED.contains(value);
    }
}
~~~

The validator returns `true` for null so `@NotBlank` or `@NotNull` can validate presence separately. This prevents a missing field from emitting an extra "unsupported currency" error.

A `ConstraintValidator` can be reused multiple times by the provider and concurrently in some setups. Do not keep per-item mutable state inside the validator. If a validator requires Spring dependencies, use a properly configured Spring-Bean Validation integration; never look up `ApplicationContext` manually inside `isValid()`.

## 16. Time-dependent validation

Constraints like `@Past` and `@Future` rely on the current clock. Tests can vary by execution date or timezone unless controlled.

For business rules requiring deterministic time, inject a `Clock` into validators/services:

~~~java
public class OrderDatePolicy {

    private final Clock clock;

    public OrderDatePolicy(Clock clock) {
        this.clock = clock;
    }

    public boolean isAllowed(LocalDate orderDate) {
        LocalDate today = LocalDate.now(clock);
        return !orderDate.isAfter(today);
    }
}
~~~

Test:

~~~java
Clock clock = Clock.fixed(
        Instant.parse("2026-11-15T10:00:00Z"),
        ZoneOffset.UTC);
~~~

When using Jakarta Validator for `@Past`/`@Future`, you can configure a `ClockProvider` so validation uses a deterministic clock. This is useful for tests and batches running by business date.

Always distinguish UTC dates from business timezones. An `orderDate` early in the local day can differ from the UTC date. Explicitly pass a `ZoneId` or business date instead of relying on the JVM's default timezone.

## 17. External validation and transient errors

Some rules require calling external services:

- Verifying customer codes against a CRM system.
- Verifying tax IDs with a partner service.
- Checking whether an account is active.
- Confirming a product is still eligible for sale.

Do not cram all external validation into a Jakarta `ConstraintValidator`. A dedicated service makes timeouts, retries, metrics, and infrastructure errors much easier to manage:

~~~java
public class CustomerValidationProcessor
        implements ItemProcessor<ValidatedOrder, ValidatedOrder> {

    private final CustomerRegistryClient client;

    @Override
    public ValidatedOrder process(ValidatedOrder order) {
        RegistryResult result =
                client.checkCustomer(order.customerCode());

        if (result.isTemporarilyUnavailable()) {
            throw new ExternalValidationUnavailableException(
                    order.orderId());
        }

        if (!result.isValid()) {
            throw new InvalidOrderException(
                    order.orderId(),
                    "Customer registry rejected customer code");
        }

        return order;
    }
}
~~~

Distinguish:

- Registry returns invalid result: deterministic data error, typically skip/reject.
- Registry times out or is unavailable: transient error, potentially retryable with bounds.
- Authentication/configuration error: typically fail fast and alert.

### Avoid excessive external service calls

If many orders share the same `customerCode`, cache results within safe bounds or use bulk lookups. However, caches require clear TTL, invalidation, and concurrency policies.

Do not cache a validation result longer than the underlying data can change if rules demand current state. Also avoid global mutable caches if multiple Jobs/tenants use different data.

### Validation should have no side effects

An operation named `validate` should observe and decide, not reserve resources or mutate business state. If credit limits, inventory, or slots must be reserved, invoke a command/service with explicit transaction semantics and idempotency design.

Processors may be re-invoked during retries. Side effects inside a processor can execute multiple times.

## 18. Placing validation in reader, processor, or writer?

Not all validation belongs in the processor:

| Location | Best suited for | Notes |
| --- | --- | --- |
| Reader/parser | File syntax, unparseable data types, record structure | Errors can happen before an item object exists |
| Processor | Data rules, cross-field checks, normalization, business decisions | Exceptions can be skipped/retried per Step |
| Writer/database | Unique constraints, foreign keys, invariants enforced at write time | Database is the final line of defense |
| Service/domain layer | Rules shared between batch and other applications | Transaction boundaries must be defined |

For example, malformed emails can be checked during DTO validation. Checking whether an email is already registered may require the database. Ensuring a customer code is still active at write time may require locking or constraints.

Never validate solely in the processor and assume data cannot change before commit. Database constraints remain essential for correctness under concurrent transactions.

## 19. Validation and composite processors

You can chain a validation processor with other processors:

~~~text
OrderInput
    |
    v
ValidationProcessor
    |
    v
NormalizationProcessor
    |
    v
EnrichmentProcessor
    |
    v
CalculationProcessor
    |
    v
OrderOutput
~~~

Example:

~~~java
@Bean
public CompositeItemProcessor<OrderInput, OrderOutput> orderProcessor(
        ItemProcessor<OrderInput, ValidatedOrder> validationProcessor,
        ItemProcessor<ValidatedOrder, NormalizedOrder> normalizationProcessor,
        ItemProcessor<NormalizedOrder, EnrichedOrder> enrichmentProcessor,
        ItemProcessor<EnrichedOrder, OrderOutput> calculationProcessor) {

    return new CompositeItemProcessorBuilder<OrderInput, OrderOutput>()
            .delegates(
                    validationProcessor,
                    normalizationProcessor,
                    enrichmentProcessor,
                    calculationProcessor)
            .build();
}
~~~

Each processor has explicit input/output types. If validation throws an exception, downstream processors never receive that item. If a processor returns `null`, the item is filtered and the processor chain stops for that item.

Place validation early in the chain when subsequent steps are expensive or call external systems. However, if normalization must standardize values before validation runs, make that ordering explicit and verify normalization does not silently turn invalid data into seemingly valid data.

## 20. Skip policies and error limits

Skip limits let a Job continue past a few bad records while still failing if errors exceed a threshold.

~~~java
.faultTolerant()
.skip(InvalidOrderException.class)
.skipLimit(50)
~~~

When handling multiple exception types:

~~~java
.skip(InvalidOrderException.class)
.skip(UnsupportedCurrencyException.class)
.noSkip(ExternalValidationUnavailableException.class)
.skipLimit(50)
~~~

Rules must be read alongside the ordering and skip policy semantics of your Spring Batch version. If an exception subclass appears in both `skip` and `noSkip`, verify actual precedence; avoid confusing overlapping configurations.

### Skip limit is a total cap

The skip limit applies to total skips under the Step's policy across supported stages such as read, process, and write. Once exceeded, the Step fails.

Do not rely on `skipLimit` alone to judge batch quality. Track error rates as well:

- Total records read.
- Total valid records.
- Total filtered records.
- Total skipped/rejected records.
- Error rates by category.

You can fail the Job if the error rate exceeds a business threshold even before `skipCount` hits the absolute limit. Implement that logic cleanly using a listener/decider or post-step check, rather than scattering conditions inside the processor.

## 21. Validation errors in the writer

Some errors only surface during writes:

- Unique key already exists.
- Invalid foreign key.
- Optimistic lock conflict.
- Column length exceeded.
- Database check constraint violated.

You cannot guarantee all such errors are caught before the processor because database state can change between validation and write. The writer/database must still handle errors.

Do not blindly skip every `DataIntegrityViolationException`. It may be a single-record data issue, or it could be a schema error or mapping bug. Classify specific exceptions and retain business keys to reject the right item.

On writer exceptions, Spring Batch may roll back the chunk and isolate the failing item via fault-tolerant processing. This can cause multiple writer/processor invocations. Writers must be idempotent and free of unprotected non-transactional side effects.

## 22. Validation and transactions

Processors generally run inside the chunk transaction of a chunk-oriented Step, though whether a processor accesses the database depends on services and the transaction manager.

If validation only inspects in-memory object fields, no separate transaction is needed. If validation reads the database, it can join the chunk transaction or open one per configured propagation.

Avoid:

- Opening `REQUIRES_NEW` transactions for every validation lookup without good reason.
- Calling manual commits inside the processor.
- Writing external reject files and expecting the database to roll them back.
- Reserving inventory during validation without compensation.

If a validation service mutates the database, decide whether those changes must share the writer's transaction. If the processor throws an exception after committing a side effect in `REQUIRES_NEW`, chunk rollback will not undo that side effect.

## 23. Restarts and deterministic validation

When a Job restarts, items from uncommitted chunks may be reprocessed. Validation should yield consistent results if inputs and rules have not changed.

Factors that can change results across runs:

- Current date changes.
- Customer or product status changes.
- External registry returns new results.
- Currency/region lists get updated.
- Validation configuration changes.
- Another database transaction updates reference data.

If the same `JobInstance` must make identical decisions, store business date, rule version, or snapshot key in `JobParameters`/metadata. For external validation, you may need to store results or reference data versions.

Never store managed entities or `Validator` state in `ExecutionContext`. Store only IDs, versions, business dates, or required checkpoints. `Validator` is typically injected from the application context and does not need serialization.

If rules change between restarts, consider failing the old `JobInstance` and starting a new `JobInstance` with the updated rule version instead of resuming from an existing checkpoint with new logic.

## 24. Validation and concurrency

Processors may run concurrently in a multi-threaded Step or partitioned Step. Therefore:

- Do not store mutable per-item state in fields of a singleton processor.
- `Validator` and constraint validators must be used within the provider's thread-safe lifecycle.
- Caches must be thread-safe and appropriately scoped.
- Do not share a mutable error list across items.
- External clients need proper timeouts and connection pools.
- Error counters should use `StepExecution` context, listeners, or thread-safe metrics.

Example to avoid:

~~~java
private final List<String> currentViolations = new ArrayList<>();
~~~

If multiple threads call `process()`, this list can mix errors from different items.

Instead, create local lists per invocation and return/throw errors tied to the current item. When aggregating errors, write individual reject records with a message ID or business key.

## 25. Unit testing a validation processor

Unit tests should verify:

- Valid input produces the expected output.
- Every important constraint is enforced.
- Multiple errors are collected accurately.
- Exceptions carry the business key and property paths.
- Null objects are handled per contract.
- Normalization modifies only permitted fields.
- The processor does not call downstream dependencies when validation fails.

Example:

~~~java
@ExtendWith(MockitoExtension.class)
class OrderValidationProcessorTest {

    private Validator validator;
    private OrderValidationProcessor processor;

    @BeforeEach
    void setUp() {
        ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory();
        validator = factory.getValidator();
        processor = new OrderValidationProcessor(validator);
    }

    @Test
    void returnsValidatedOrderForValidInput() {
        OrderInput input = validOrderInput();

        ValidatedOrder result = processor.process(input);

        assertEquals(input.getOrderId(), result.orderId());
        assertEquals("C001", result.customerCode());
    }

    @Test
    void throwsWhenRequiredCustomerCodeIsMissing() {
        OrderInput input = validOrderInput();
        input.setCustomerCode(" ");

        InvalidOrderException exception = assertThrows(
                InvalidOrderException.class,
                () -> processor.process(input));

        assertEquals(input.getOrderId(), exception.getOrderId());
        assertTrue(exception.getViolations().stream()
                .anyMatch(message -> message.contains("customerCode")));
    }
}
~~~

In large test suites, create `ValidatorFactory` once per class and close it after tests finish, or use a `Validator` bean managed by the test context. Do not open a new factory per test without closing it.

### Testing individual constraints

For DTOs with many constraints, parameterized tests work well:

~~~java
@ParameterizedTest
@MethodSource("invalidOrderCases")
void rejectsInvalidOrders(OrderInput input) {
    assertThrows(
            InvalidOrderException.class,
            () -> processor.process(input));
}
~~~

Give cases clear names in `MethodSource` or use `Arguments` with display names so you know which rule is under test. A single test with multiple missing fields only proves at least one error occurs; to verify every constraint, assert specific property paths.

## 26. Testing cross-field rules and validation groups

Cross-field validators must test:

| startDate | endDate | Outcome |
| --- | --- | --- |
| `null` | `null` | Field-level `@NotNull` reports error if required |
| `2026-01-10` | `2026-01-09` | Invalid |
| `2026-01-10` | `2026-01-10` | Valid if same-day is permitted |
| `2026-01-10` | `2026-01-11` | Valid |

Validation groups must test that:

- Group `ImportChecks` runs only import constraints.
- Group `ApprovalChecks` runs only approval constraints.
- Constraints outside a group are not triggered unexpectedly.
- `GroupSequence` halts in the defined order.

Do not merely check that annotations exist in source code. Invoke `Validator.validate()` with real groups and assert property paths/error codes.

## 27. Integration testing skips and reject outputs

Unit tests do not prove a Step actually skips records. Integration tests should:

1. Build inputs containing valid and invalid records.
2. Run the Step with the validation processor and skip policy.
3. Verify the Step is `COMPLETED` when skip count is within the limit.
4. Verify valid records are written.
5. Verify reject records are stored accurately if a reject listener/writer exists.
6. Verify skip count is accurate.
7. Test exceeding `skipLimit` and verify the Step is `FAILED`.
8. Restart the Job and verify committed records are not reprocessed twice.

If the reject writer writes to a database, test transactions and idempotency. If the reject output is a file or broker, test side effects across chunk rollbacks and retries.

### Testing the skip listener

Verify `onSkipInProcess` receives the right item and `InvalidOrderException`. For listeners writing reject records, test that a failing item does not create duplicate reject records after retries or restarts.

You can use a unique key combining `batchId` and `sourceRecordId` to prevent duplicate rejects.

## 28. Common pitfalls

### Assuming annotations run automatically in the processor

Annotations only declare constraints. You must call `Validator.validate()` or trigger validation at the proper boundary.

### Using @NotNull instead of @NotBlank

Empty or whitespace-only strings can slip through. Pick the constraint matching the type and contract.

### Using null to represent invalid data

Spring Batch treats `null` as a filter. Throw an exception or return a reject result when errors must be recorded.

### Retrying validation errors

Deterministically bad data rarely becomes valid after retries. Use skip/reject or fail per policy.

### Skipping every RuntimeException

This can bypass configuration errors, bugs, or infrastructure failures. Skip only explicitly classified exceptions.

### Dropping source record metadata

After parsing, it becomes hard to pinpoint the offending line/file/message. Keep source ID, line number, or message ID in item metadata.

### Validator querying the database per field

Can cause N+1 lookups and slow down the batch. Batch lookups, cache safely, or extract a business validation service.

### Validation with side effects

Retries can repeat reservations, messages, or API calls. Keep validation read-only; command side effects require idempotency.

### Checking data only before writing

The database can change between validation and write. Use constraints, locking, or conditional updates where guarantees are required.

### Ignoring errors in reject listeners

Records are skipped without a trace. Build durable reject outputs with clear transaction strategies.

### Logging sensitive payloads

Logs can expose personal data or secrets. Store only business keys, field paths, and necessary error codes.

### Failing to test restarts

Rules or external references can change across runs. Persist rule versions/business dates when consistency is required.

## 29. Validation processor design workflow

When implementing, follow these steps:

1. Define the input contract and DTO type received from the reader.
2. Separate structural, field-level, cross-field, business, and external validations.
3. Declare Jakarta constraints for pure object-level rules.
4. Inject and reuse `Validator` in the processor.
5. Create exceptions carrying business keys, property paths, and error codes.
6. Normalize data under clear rules before converting to an internal DTO.
7. Clearly decide whether invalid items fail, skip, reject, or filter.
8. Configure skip/retry policies strictly for appropriate exceptions.
9. Persist reject records durably if data requires investigation or replay.
10. Keep the validation processor free of non-idempotent side effects.
11. Guard external validation with timeouts, retries, caches, or snapshots.
12. Define business dates and rule versions for consistent restarts.
13. Write unit tests for all critical constraints and boundaries.
14. Write integration tests for skip counts, reject outputs, rollbacks, and restarts.
15. Monitor valid, filtered, skipped, and rejected counts plus error rates.

A well-designed validation processor clarifies why an item is accepted or rejected, keeps errors structured, and lets Spring Batch apply consistent policies. Downstream steps receive only data meeting the invariants they rely on.

## Conclusion

A validation processor verifies data before downstream processing and writing steps consume items. Use Jakarta Bean Validation for DTO constraints, custom class-level validators for cross-field rules, and domain services for business validation requiring reference data. Inject a reusable `Validator`, craft exceptions with business keys and structured errors, and clearly distinguish filtering via `null`, skipping/rejecting via exceptions, and failing the Job. Skip policies must specify exact error types; retries belong to transient errors, while deterministic validation errors typically require rejection or skipping. Keep validation free of non-idempotent side effects, enforce final invariants at the database, preserve source metadata for investigation, and test both the rules and Step behavior, reject outputs, and restarts.
