# Validate before transform

In Spring Batch, an ItemProcessor is usually responsible for validating and transforming data between the ItemReader and the ItemWriter. For input data coming from a file, a message, or a database, a safe design is to **validate the source data before transforming it into the target model**.

This order helps detect invalid data right at the input boundary, when the application still has all the original information to explain the error. It also avoids transforming a bad record into a target object only to discover the problem in a later step.

Validation and transformation are two different responsibilities:

- **Validation** determines whether the data meets the required structure and business rules.
- **Transformation** converts valid data from the source model to the target model, normalizing it or computing the required fields.

Spring Batch lets you organize these two responsibilities in a single ItemProcessor, or chain multiple processors in order using CompositeItemProcessor.

## 1. The position of validation in the chunk flow

In a chunk-oriented Step, data passes through ItemReader, ItemProcessor, and ItemWriter:

~~~text
Data source
     |
     v
  ItemReader
     |
     v
  Source data
     |
     v
  Validate
     |
     +---- invalid ----> Exception / Skip / Filter
     |
     v
  Transform
     |
     v
  Target model
     |
     v
  ItemWriter
     |
     v
  Data destination
~~~

The reader is responsible for reading and converting the physical data into application items. For example, FlatFileItemReader can parse a CSV line into an OrderInput. The processor checks conditions that the reader cannot determine, such as a required order ID, a positive amount, or a valid business date. Then the transformer converts OrderInput into Order so the writer can save it to the database.

Validating before transforming is especially useful when:

- The source model and the target model are different.
- The transform can lose the original information or normalize the data.
- Business rules need to be applied to the original values received from the source.
- You want to classify bad records before performing calculations or calling other services.
- You need to record the exact source values and the rejection reason for reconciliation.

Not every check has to be placed in the processor. Syntax errors or parse errors can be detected right in the reader. Database constraints are still necessary to protect the final data. Validation in the processor adds a layer of business checking between those two stages.

## 2. Distinguishing validation from transformation

Suppose the source file contains order data:

~~~text
order_id,customer_code,quantity,unit_price
ORD-1001,CUS-01,2,150000
ORD-1002,,0,-500
~~~

The first line may be valid. The second line is missing customer_code, has a quantity of 0, and a negative unit_price. If the transformer runs first, it may create an Order with missing data or compute totalAmount from invalid values. In that case the error may appear later, for example in the writer or in a reporting system.

You should split the work into two stages:

**Validation on OrderInput**

- orderId must not be empty.
- customerCode must have a value.
- quantity must be greater than 0.
- unitPrice must not be negative.

**Transformation to Order**

- Normalize the order ID.
- Compute totalAmount from quantity and unitPrice.
- Convert the customer code into a customer reference according to the defined rule.
- Assign an initial status to the target entity.

Validation answers the question “is the source data accepted?”. Transformation answers the question “how should the valid data be represented in the target model?”.

## 3. Writing a dedicated validator for source data

One clear approach is to create a validator that accepts the source data type and throws an exception when a record is invalid. Spring Batch provides the Validator contract in the item.validator package:

~~~java
public class OrderInputValidator
        implements org.springframework.batch.item.validator.Validator<OrderInput> {

    @Override
    public void validate(OrderInput input)
            throws org.springframework.batch.item.validator.ValidationException {

        if (input == null) {
            throw new org.springframework.batch.item.validator.ValidationException(
                    "Order input must not be null");
        }

        if (input.getOrderId() == null || input.getOrderId().isBlank()) {
            throw new org.springframework.batch.item.validator.ValidationException(
                    "orderId is required");
        }

        if (input.getCustomerCode() == null
                || input.getCustomerCode().isBlank()) {
            throw new org.springframework.batch.item.validator.ValidationException(
                    "customerCode is required");
        }

        if (input.getQuantity() == null || input.getQuantity() <= 0) {
            throw new org.springframework.batch.item.validator.ValidationException(
                    "quantity must be greater than zero");
        }

        if (input.getUnitPrice() == null
                || input.getUnitPrice().signum() < 0) {
            throw new org.springframework.batch.item.validator.ValidationException(
                    "unitPrice must not be negative");
        }
    }
}
~~~

The validator only checks data and reports errors. It does not modify the input, does not write to the database, and does not perform transformation. Keeping the validator free of side effects makes the check predictable and safe when Spring Batch retries an item.

You can check multiple conditions at once and create a message containing the list of errors instead of stopping at the first error. When doing so, you need to use an exception that fits the application's conventions and ensure the error information is sufficient for operators to identify the source record.

### Using ValidatingItemProcessor

Spring Batch provides ValidatingItemProcessor to turn a Validator into an ItemProcessor. This processor accepts and returns the same data type if validation succeeds:

~~~java
@Bean
public ValidatingItemProcessor<OrderInput> orderValidationProcessor(
        OrderInputValidator validator) {

    ValidatingItemProcessor<OrderInput> processor =
            new ValidatingItemProcessor<>();
    processor.setValidator(validator);
    processor.setFilter(false);
    return processor;
}
~~~

With filter=false, a validation failure is thrown as a ValidationException. The Step can fail or handle the exception according to the retry/skip configuration.

If setFilter(true) is used, an invalid record is filtered by the processor returning null. That item is not passed to the next processor or to the writer. This is a business decision: filter is appropriate when you only need to drop the item, while exception/skip is appropriate when you need to record the rejected record and the reason.

## 4. Combining validation and transformation with CompositeItemProcessor

CompositeItemProcessor lets you chain ItemProcessors together. The output of the previous processor becomes the input of the next processor. This is a way to express clearly the order of validate first, transform after.

Suppose there are two components:

- ValidatingItemProcessor<OrderInput> checks OrderInput and returns the item itself if it is valid.
- OrderTransformer converts OrderInput into Order.

The transformer can be implemented as follows:

~~~java
public class OrderTransformer
        implements ItemProcessor<OrderInput, Order> {

    @Override
    public Order process(OrderInput input) {
        Order order = new Order();
        order.setOrderId(input.getOrderId().trim().toUpperCase());
        order.setCustomerCode(input.getCustomerCode().trim());
        order.setQuantity(input.getQuantity());
        order.setUnitPrice(input.getUnitPrice());
        order.setTotalAmount(
                input.getUnitPrice().multiply(
                        BigDecimal.valueOf(input.getQuantity())));
        order.setStatus(OrderStatus.NEW);
        return order;
    }
}
~~~

Then combine the two processors in the correct order:

~~~java
@Bean
public ItemProcessor<OrderInput, Order> orderProcessor(
        ValidatingItemProcessor<OrderInput> orderValidationProcessor,
        OrderTransformer orderTransformer) throws Exception {

    return new CompositeItemProcessorBuilder<OrderInput, Order>()
            .delegates(orderValidationProcessor, orderTransformer)
            .build();
}
~~~

Execution flow:

~~~text
OrderInput
    |
    v
ValidatingItemProcessor<OrderInput>
    |
    +-- ValidationException if invalid
    |
    v
Validated OrderInput
    |
    v
OrderTransformer
    |
    v
Order
~~~

If validation throws an exception, CompositeItemProcessor stops the chain at that processor. OrderTransformer is not called for the bad item. This ensures the transformation only runs on data that has passed the check.

The generic types of the processors must chain together. The validation processor has OrderInput as both its input and output type; the transformer takes OrderInput and returns Order. If the output of one processor is not compatible with the input of the next processor, the chain cannot be configured correctly.

## 5. Validation with Jakarta Bean Validation

For a DTO with common validation rules, you can declare constraints using Jakarta Bean Validation instead of writing all the conditions yourself.

For example:

~~~java
public class OrderInput {

    @NotBlank
    private String orderId;

    @NotBlank
    private String customerCode;

    @NotNull
    @Positive
    private Integer quantity;

    @NotNull
    @DecimalMin("0.00")
    private BigDecimal unitPrice;

    // constructors, getters and setters
}
~~~

Spring Batch has BeanValidatingItemProcessor to check constraints on an item:

~~~java
@Bean
public BeanValidatingItemProcessor<OrderInput> beanValidatingProcessor()
        throws Exception {

    BeanValidatingItemProcessor<OrderInput> processor =
            new BeanValidatingItemProcessor<>();
    processor.setFilter(false);
    return processor;
}
~~~

When BeanValidatingItemProcessor is placed before OrderTransformer in CompositeItemProcessor, the constraints are checked on OrderInput before conversion.

To use this approach, the application needs a Jakarta Bean Validation implementation dependency that matches the Spring Boot/Spring Framework version in use. With Spring Boot, you can usually add the validation starter. If the project uses Spring Batch 4 or an older version, the validation namespace may be javax.validation instead of jakarta.validation; you need to use the correct namespace for the version.

Bean Validation is suitable for constraints on a single object such as required, length, numeric range, or format. Complex rules that need to query reference data, check related state, or apply depending on the Job context are usually better suited to a dedicated business validator.

## 6. Validate before transform in a single processor

You are not required to use CompositeItemProcessor. For small logic, you can implement both validation and transformation in the same ItemProcessor, but you need to keep the order clear:

~~~java
public class OrderProcessor
        implements ItemProcessor<OrderInput, Order> {

    private final OrderInputValidator validator;
    private final OrderTransformer transformer;

    public OrderProcessor(
            OrderInputValidator validator,
            OrderTransformer transformer) {
        this.validator = validator;
        this.transformer = transformer;
    }

    @Override
    public Order process(OrderInput input) {
        validator.validate(input);
        return transformer.process(input);
    }
}
~~~

The advantage of this approach is fewer configuration components and the order is expressed directly in the process method. The disadvantage is that the processor is responsible for orchestrating two steps, so as validation and transformation grow, separating them will be easier to test and reuse.

You should choose an organization that suits the complexity of the flow. There is no need to create too many processors just to separate simple checks, but you also should not stuff every rule into one long process method.

## 7. Validation failure: fail, skip, or filter?

When validation detects an invalid item, the application must decide how to handle it. The three common behaviors have different meanings:

| Handling | Behavior | When it is appropriate |
| --- | --- | --- |
| Fail Step | An unhandled exception fails the Step | Bad data indicates the source or process is unreliable |
| Skip item | The exception belongs to a group allowed to be skipped; the Step continues and records the skip | The bad record can be ignored but still needs to be tracked |
| Filter item | The processor returns null; the item does not reach the writer | Drop the item based on a business condition without treating it as an error |

You should not use filter just to hide bad data. Filter is generally for items that are structurally valid but need not be included in the result, for example a cancelled order where a business rule requires omitting it from the report. A record missing an order ID or having a negative quantity should usually be treated as a validation failure so it can be tracked.

### Using skip for validation exceptions

If the requirement is to continue the Job but still record the invalid records, you can configure a fault-tolerant Step:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(ValidationException.class)
        .skipLimit(100)
        .build();
~~~

The example allows skipping up to 100 validation failures under the Step's skip policy. The skip limit is counted over the errors skipped in the Step, not as a separate maximum for each exception type.

If the limit is exceeded, or an exception that is not allowed to be skipped appears, the Step can fail. You should not configure skip for every RuntimeException because it can hide programming errors or infrastructure errors.

### Recording skipped records

When you need to store the reason a record was rejected, you can use SkipListener:

~~~java
@Bean
public SkipListener<OrderInput, Order> orderSkipListener(
        RejectedOrderRepository rejectedOrderRepository) {

    return new SkipListener<>() {
        @Override
        public void onSkipInProcess(
                OrderInput item,
                Throwable cause) {

            rejectedOrderRepository.save(
                    RejectedOrder.from(item, cause.getMessage()));
        }
    };
}
~~~

Register the listener with the Step using the corresponding listener method. In practice, you should store the source, line number, or input identifier along with an error code and a message that can be looked up. Avoid storing only a free-form message because the message content can change across versions or languages.

If skipped data needs to be stored in a database different from the Step's transaction, design the transaction and the error-recording capability explicitly. Do not assume the operation that saves the rejected record is always committed together with the business transaction if it uses a different resource or transaction manager.

## 8. Validation in the reader, processor, and database

Validation should be placed in the layer that best understands the kind of error to detect:

| Location | Suitable kind of check | Example |
| --- | --- | --- |
| Reader / parser | Structure and conversion of source data | CSV missing a column, badly formatted date, number that cannot be parsed |
| ItemProcessor before transform | Business rules on the source model | Customer code required, quantity must be positive |
| After transform | Invariants of the target model | Total amount is non-negative, target status is valid |
| Database | Final constraints that protect integrity | NOT NULL, UNIQUE, FOREIGN KEY, CHECK |

You should not push every error into the ItemProcessor. If a CSV line cannot be parsed into an OrderInput, the processor has no object to check yet. That error must be handled in the reader or parser, with an appropriate skip policy if the business allows it.

Similarly, validation in the processor does not replace database constraints. Multiple Jobs or applications may write to the same database; the database constraint is still the last line of defense against inconsistent data.

### Validation after transform may still be necessary

Validating before transform ensures the source data is eligible for conversion. But the transformation can produce new values or combine several fields. Therefore, sometimes you need to additionally check the target model's invariants:

~~~text
OrderInput
   |
   v
Validate source fields
   |
   v
Transform to Order
   |
   v
Validate target invariants
   |
   v
ItemWriter
~~~

For example, quantity and unitPrice may both be valid but the totalAmount calculation may exceed a business limit. In that case you need to check the result after the transform. These two layers of validation have different purposes and can coexist.

## 9. Designing a maintainable validator

A good validator should have these characteristics:

- **Clear scope:** checks one kind of input or one group of related rules.
- **No side effects:** does not write to a database, send messages, or modify external state.
- **Contextual messages:** names the field or the rule code that was violated.
- **Independently testable:** takes an input and returns a result or throws an exception.
- **No duplicated rules:** reuses the validator in other import flows if the semantics are the same.
- **Distinguishes data errors from system errors:** bad data can be skipped according to policy; an unavailable database or service usually needs retry or fail.

If a validator must look up reference data, such as whether customerCode exists, you need to consider the query cost. Calling the database once per item can create N+1 queries and reduce throughput. You can use a bounded cache, a bulk lookup, or preloading of reference data at an appropriate scope. The cache must have a clear expiration policy and consistency.

Avoid using exceptions for every ordinary business condition if the expected number of errors is very large and needs to be handled statistically. However, in Spring Batch, exceptions are still the mechanism that integrates directly with skip/retry. The decision should be based on semantics: whether a bad item must be rejected in a controlled way or merely filtered by a condition.

## 10. Testing validation before transformation

You can test the validator and the transformer separately, and then test the order of the CompositeItemProcessor.

### Testing the validator

~~~java
class OrderInputValidatorTest {

    private final OrderInputValidator validator =
            new OrderInputValidator();

    @Test
    void rejectsInputWithoutOrderId() {
        OrderInput input = new OrderInput(
                " ",
                "CUS-01",
                2,
                new BigDecimal("100.00"));

        assertThrows(
                ValidationException.class,
                () -> validator.validate(input));
    }
}
~~~

### Testing the processing order

You can use Mockito to confirm that the transformer is not called when validation fails:

~~~java
@Test
void doesNotTransformInvalidInput() throws Exception {
    OrderInputValidator validator = new OrderInputValidator();
    OrderTransformer transformer = mock(OrderTransformer.class);
    OrderInput invalidInput = new OrderInput(
            "",
            "CUS-01",
            2,
            new BigDecimal("100.00"));

    OrderProcessor processor =
            new OrderProcessor(validator, transformer);

    assertThrows(
            ValidationException.class,
            () -> processor.process(invalidInput));

    verifyNoInteractions(transformer);
}
~~~

This test confirms the error is detected before transformation takes place. In addition, you should test that a valid item is converted correctly, a filtered item does not reach the writer, a validation exception is skipped within the limit, and the Step fails when the skip limit is exceeded.

## 11. Common mistakes

### Transforming first and validating afterward

If the transformation loses the original value or changes the format, the information needed to explain the error may no longer exist. Check the rules that apply to the input before converting.

### Merging validation and transformation without boundaries

A long process method that validates, normalizes, calls a service, and writes data is hard to test. Separate the validator and transformer when each part has its own responsibility or lifecycle.

### Filtering every invalid record

Returning null makes the item disappear from the writer flow and counts as filtered. If you need to audit or collect statistics on bad records, use an exception together with a skip listener or an appropriate flow that stores rejected records.

### Skipping every exception

Skipping database connection errors or programming errors can cause the Job to continue in an unreliable state. Skip only the exceptions that represent clearly classified data errors.

### A validator with side effects

If the validator writes data or calls an API, a retry can repeat the side effect. Keep validation purely a check; place write or orchestration operations in a component with an appropriate transaction and idempotency.

### Database queries for each item

Business validation that needs reference lookups can generate many queries. Measure the cost and consider a bulk lookup or a bounded cache instead of uncontrolled repeated queries.

### Validating only the input and forgetting the output's invariants

A valid set of inputs can still produce invalid output after calculation or field combination. Add validation after the transform when the target model has its own constraints.

## 12. Workflow for organizing ItemProcessor

When building a data-processing flow, you can follow this sequence:

1. Determine the item type the reader produces and the parse errors that can appear.
2. List the business rules to check on the source data.
3. Choose how to validate: a dedicated validator, ValidatingItemProcessor, or BeanValidatingItemProcessor.
4. Decide whether bad data will fail the Step, be skipped, or be filtered.
5. Write a transformer that accepts only valid data and converts it to the target type.
6. Use CompositeItemProcessor if you need to express a chain of multiple processors.
7. Add a post-transform invariant check when needed.
8. Keep the database constraints to protect final integrity.
9. Test the validation/transformation order, skip/filter, and restart.
10. Monitor the read, filter, skip, and write counts and store rejection reasons when the business needs reconciliation.

## Conclusion

Validating before transforming helps detect bad data on the source model, preserves the original context, and prevents the transformation from running on an invalid item. In Spring Batch, you can use a Validator together with ValidatingItemProcessor, BeanValidatingItemProcessor, or a custom processor, and then combine it with the transformer using CompositeItemProcessor. Distinguish exception/skip from filtering with null, keep validators free of side effects, and add post-transform validation when the target model has its own invariants.
