# BeanWrapperFieldSetMapper

In Spring Batch, `BeanWrapperFieldSetMapper` is a `FieldSetMapper<T>` implementation used to convert a `FieldSet` into a Java object. It relies on Spring's `BeanWrapper` mechanism to assign each column's value to the corresponding property on the bean.

This mapper is commonly used with `FlatFileItemReader`: the reader reads a line, `LineTokenizer` splits the line into fields to create a `FieldSet`, and `BeanWrapperFieldSetMapper` binds those fields into an object such as `Order`, `Customer`, or `Employee`.

Its main convenience is avoiding repetitive manual calls to `fieldSet.readString(...)`, `readBigDecimal(...)`, and setters for every property. However, field names must match JavaBean properties, data types must be convertible, and binding errors must be handled explicitly.

## 1. Where does FieldSetMapper fit in the file-reading flow?

With `FlatFileItemReader`, turning a text line into an object typically passes through these components:

1. `Resource` provides the input file.
2. `LineMapper` receives each text line.
3. `LineTokenizer` splits the line into fields.
4. The tokenizer creates a `FieldSet` containing values and field names.
5. `FieldSetMapper` converts the `FieldSet` into a business object.
6. The reader returns the object to the Step's processor.

```text
orders.csv
   |
   v
FlatFileItemReader
   |
   v
LineMapper
   |
   v
DelimitedLineTokenizer
   |
   v
FieldSet
   |  orderId = "1001"
   |  customerName = "Lan"
   |  amount = "125.50"
   v
BeanWrapperFieldSetMapper<Order>
   |
   v
Order
   |  orderId = 1001L
   |  customerName = "Lan"
   |  amount = 125.50
```

`BeanWrapperFieldSetMapper` is only responsible for the final step: mapping `FieldSet` into the bean. It does not read files itself, split delimiters, or replace business validation in the processor.

## 2. What is FieldSet?

`FieldSet` is a Spring Batch abstraction representing the values extracted by a tokenizer from a line. A `FieldSet` can read values by position or by name:

```java
String orderId = fieldSet.readString("orderId");
BigDecimal amount = fieldSet.readBigDecimal("amount");
```

Field names are defined by the tokenizer configuration, such as `.names(...)` in the builder. When using `BeanWrapperFieldSetMapper`, these names are used to locate matching properties on the target bean.

Example file:

```csv
order_id,customer_name,amount
1001,Lan,125.50
1002,Minh,89.00
```

The tokenizer can assign names to the columns:

```java
.delimited()
.delimiter(",")
.names("orderId", "customerName", "amount")
```

Then the `FieldSet` for the second line has fields named `orderId`, `customerName`, and `amount`. If the target class has matching properties, the mapper can bind them directly.

Header names inside the file do not automatically determine property names in every configuration. When `.names(...)` is used, those names come from configuration; if you need to read headers to determine columns, configure the reader/tokenizer accordingly.

## 3. What does a JavaBean need for BeanWrapperFieldSetMapper to bind it?

`BeanWrapperFieldSetMapper` uses Spring property access. The target class typically needs:

- A no-arg constructor so the mapper can instantiate it when using `targetType`.
- Properties with public setters or corresponding writable properties.
- Property names matching the field names in `FieldSet`, or discoverable via configured fuzzy matching.
- Data types convertible from text values into the property types.

Example model:

```java
public class Order {

    private Long orderId;
    private String customerName;
    private BigDecimal amount;

    public Order() {
    }

    public Long getOrderId() {
        return orderId;
    }

    public void setOrderId(Long orderId) {
        this.orderId = orderId;
    }

    public String getCustomerName() {
        return customerName;
    }

    public void setCustomerName(String customerName) {
        this.customerName = customerName;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public void setAmount(BigDecimal amount) {
        this.amount = amount;
    }
}
```

If a model only has a parameterized constructor and no setters, standard JavaBean binding will not fit. In that case, use a custom `FieldSetMapper` to invoke the constructor or factory method with the right parameter order and data rules.

## 4. Configuring BeanWrapperFieldSetMapper with targetType

The common setup creates the mapper, calls `setTargetType(...)`, and passes the mapper to `FlatFileItemReader`:

```java
@Bean
public FieldSetMapper<Order> orderFieldSetMapper() {
    BeanWrapperFieldSetMapper<Order> mapper = new BeanWrapperFieldSetMapper<>();
    mapper.setTargetType(Order.class);
    return mapper;
}

@Bean
public FlatFileItemReader<Order> orderReader(
        Resource orderResource,
        FieldSetMapper<Order> orderFieldSetMapper) {

    return new FlatFileItemReaderBuilder<Order>()
            .name("orderReader")
            .resource(orderResource)
            .delimited()
            .delimiter(",")
            .names("orderId", "customerName", "amount")
            .fieldSetMapper(orderFieldSetMapper)
            .build();
}
```

`setTargetType(Order.class)` tells the mapper which class to instantiate. The mapper then creates an instance and binds the `FieldSet` values into the matching properties.

Builders and APIs may differ slightly across Spring Batch versions, but the principle stays the same: configure `FieldSetMapper` on the reader and supply the target type to `BeanWrapperFieldSetMapper`.

## 5. Mapping output example

Suppose the tokenizer produces a `FieldSet` from the line:

```text
1001,Lan,125.50
```

With field names:

```java
.names("orderId", "customerName", "amount")
```

The mapper looks up matching properties and converts types:

| FieldSet | Text value | Java property | Property type |
|---|---|---|---|
| `orderId` | `"1001"` | `orderId` | `Long` |
| `customerName` | `"Lan"` | `customerName` | `String` |
| `amount` | `"125.50"` | `amount` | `BigDecimal` |

The result is equivalent to:

```java
Order order = new Order();
order.setOrderId(1001L);
order.setCustomerName("Lan");
order.setAmount(new BigDecimal("125.50"));
```

This is automatic mapping based on property names and Spring's conversion service/property editors. You do not have to write these setters manually in a custom mapper for every line.

## 6. Data type conversion

Values read from files are initially text, while bean properties can be `Long`, `Integer`, `BigDecimal`, `LocalDate`, `Boolean`, or other types. `BeanWrapperFieldSetMapper` relies on Spring's conversion mechanism to bind values into property types.

Common conversions that work when the input format matches:

| File value | Target type | Example |
|---|---|---|
| `"1001"` | `Long` | ID |
| `"25"` | `Integer` | Quantity |
| `"125.50"` | `BigDecimal` | Monetary amount |
| `"true"` | `Boolean` | Status flag |
| `"2026-11-15"` | `LocalDate` | ISO date, if supported by configured conversion |

Do not assume every date or number format will automatically convert according to business rules. For example, `15/11/2026`, `11/15/2026`, and `2026-11-15` can carry different meanings depending on locale. Configure explicit conversion whenever data uses custom formats.

## 7. Configuring ConversionService for custom formats

When a file uses a custom date format, you can supply a `ConversionService` to the mapper. For example, a file containing dates formatted as `dd/MM/yyyy`:

```java
@Bean
public ConversionService orderConversionService() {
    DefaultConversionService conversionService = new DefaultConversionService();
    conversionService.addConverter(String.class, LocalDate.class,
            value -> LocalDate.parse(value, DateTimeFormatter.ofPattern("dd/MM/yyyy")));
    return conversionService;
}

@Bean
public FieldSetMapper<Order> orderFieldSetMapper(
        ConversionService orderConversionService) {

    BeanWrapperFieldSetMapper<Order> mapper = new BeanWrapperFieldSetMapper<>();
    mapper.setTargetType(Order.class);
    mapper.setConversionService(orderConversionService);
    return mapper;
}
```

The model has property:

```java
private LocalDate orderDate;

public LocalDate getOrderDate() {
    return orderDate;
}

public void setOrderDate(LocalDate orderDate) {
    this.orderDate = orderDate;
}
```

The tokenizer must name the field `orderDate`. The conversion service converts the text to `LocalDate` using the specified format.

In real applications, use an immutable `DateTimeFormatter` and an explicit format. If different file types use different formats, use separate mappers/conversion services per source rather than a global converter with ambiguous rules.

## 8. Using a custom PropertyEditor

In addition to `ConversionService`, Spring `BeanWrapper` also supports `PropertyEditor` for value conversion. `BeanWrapperFieldSetMapper` can be configured with custom editors for types needing special handling, depending on the API of your version.

Conceptual example of a date editor:

```java
public class OrderDateEditor extends PropertyEditorSupport {

    private final DateTimeFormatter formatter =
            DateTimeFormatter.ofPattern("dd/MM/yyyy");

    @Override
    public void setAsText(String text) {
        setValue(LocalDate.parse(text, formatter));
    }
}
```

You can register the editor for `LocalDate` through the mapper's `customEditors` property:

```java
Map<Class<?>, PropertyEditor> editors = new HashMap<>();
editors.put(LocalDate.class, new OrderDateEditor());
mapper.setCustomEditors(editors);
```

`PropertyEditor` instances are stateful and not all implementations are thread-safe to share across threads. Check editor lifecycle and how the mapper uses it in your project's Spring Batch version. For new applications, `ConversionService`/`Converter` is usually easier to test and expresses conversion rules more clearly.

## 9. Field names and bean property names

Normally, field names supplied by the tokenizer should exactly match JavaBean property names. For example:

```java
.names("orderId", "customerName", "amount")
```

with a bean having properties `orderId`, `customerName`, and `amount`.

If the file uses headers `ORDER_ID`, `CUSTOMER_NAME`, `TOTAL_AMOUNT`, do not assume the mapper will automatically translate every naming convention into camelCase properties according to business rules. Proactively configure field names or use a custom mapper to map aliases.

Example of a tokenizer assigning names matching bean properties even when file headers differ:

```java
.delimited()
.names("orderId", "customerName", "amount")
```

If input columns have different names and require custom conversion rules, a custom `FieldSetMapper` makes the intent clearer.

## 10. Fuzzy matching and distanceLimit

`BeanWrapperFieldSetMapper` supports finding properties whose names are close to field names within a distance threshold. This can handle minor naming discrepancies, but fuzzy matching should not be treated as a primary business mapping mechanism.

For instance, a field name `customerNmae` might be considered close to property `customerName` due to a character transposition. The mapper can locate the closest property if the configured distance limit permits it.

The distance limit can be configured with `setDistanceLimit(...)`:

```java
BeanWrapperFieldSetMapper<Order> mapper = new BeanWrapperFieldSetMapper<>();
mapper.setTargetType(Order.class);
mapper.setDistanceLimit(2);
```

A smaller distance limit makes near-name matching stricter. Exact values and distance calculation depend on the implementation/version; configure explicitly and verify against your actual field schema instead of relying on defaults.

Fuzzy matching carries the risk of misbinding if a bean has similarly named properties, such as `orderDate` and `orderData`. For financial or critical data, prefer exact names or a custom mapper to avoid silent misbinding.

## 11. Strict mode and fields without matching properties

Strict mode controls how the mapper behaves when no matching property is found for a field. With strict enabled, an unbindable field triggers a mapping error; non-strict mode may ignore unmatched fields depending on implementation behavior.

Example explicit configuration:

```java
BeanWrapperFieldSetMapper<Order> mapper = new BeanWrapperFieldSetMapper<>();
mapper.setTargetType(Order.class);
mapper.setStrict(true);
```

Strict mode is appropriate when a file has a fixed schema and every column must be processed. If an upstream system adds an unused column, strict mode may fail the Job; in that case decide explicitly whether extra columns are permitted.

Do not disable strict mode just to hide typos in field names. If field `amount` is accidentally named `amout`, skipping the mapping could leave the property at its default value and pass bad data downstream. Inspect the input schema and pick a clear policy.

## 12. Mapping nested properties

Spring's `BeanWrapper` supports property paths, allowing fields to map to nested properties when the object graph and getters/setters support it.

Example model:

```java
public class CustomerOrder {
    private Long orderId;
    private Address address;

    public CustomerOrder() {
    }

    public Long getOrderId() {
        return orderId;
    }

    public void setOrderId(Long orderId) {
        this.orderId = orderId;
    }

    public Address getAddress() {
        return address;
    }

    public void setAddress(Address address) {
        this.address = address;
    }
}

public class Address {
    private String city;

    public Address() {
    }

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }
}
```

The tokenizer can supply field name `address.city` when property paths and the object graph are supported by the mapper:

```java
.names("orderId", "address.city")
```

`BeanWrapper` can auto-grow nested paths in certain configurations, but complex object graphs, collections, or non-instantiable properties can fail. Test nested mapping with the actual model. If constructing child objects involves business rules, a custom mapper is usually clearer.

## 13. Using prototypeBeanName instead of targetType

`setTargetType(...)` works well when the mapper can instantiate the bean via a no-arg constructor. If Spring needs to construct the target from a prototype bean configured with dependencies or a factory method, use `prototypeBeanName` and `BeanFactory`.

Example prototype bean configuration:

```java
@Bean
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public Order orderPrototype(OrderDefaults defaults) {
    Order order = new Order();
    order.setCurrency(defaults.currency());
    return order;
}

@Bean
public FieldSetMapper<Order> orderFieldSetMapper(
        BeanFactory beanFactory) {

    BeanWrapperFieldSetMapper<Order> mapper = new BeanWrapperFieldSetMapper<>();
    mapper.setBeanFactory(beanFactory);
    mapper.setPrototypeBeanName("orderPrototype");
    return mapper;
}
```

In this case, the mapper retrieves a fresh prototype bean for each `FieldSet` mapped. Do not configure both `targetType` and `prototypeBeanName` in conflicting ways; choose the object creation mechanism that fits your model.

Prototype beans are useful when objects require Spring-managed dependencies or initial defaults. If the model is simple and has a default constructor, `targetType` is usually more concise.

## 14. Full integration with FlatFileItemReader

Example configuration reading a CSV with a header:

```java
@Bean
public FieldSetMapper<Order> orderFieldSetMapper(
        ConversionService orderConversionService) {

    BeanWrapperFieldSetMapper<Order> mapper = new BeanWrapperFieldSetMapper<>();
    mapper.setTargetType(Order.class);
    mapper.setConversionService(orderConversionService);
    mapper.setStrict(true);
    return mapper;
}

@Bean
public FlatFileItemReader<Order> orderReader(
        Resource orderFile,
        FieldSetMapper<Order> orderFieldSetMapper) {

    return new FlatFileItemReaderBuilder<Order>()
            .name("orderReader")
            .resource(orderFile)
            .linesToSkip(1)
            .delimited()
            .delimiter(",")
            .names("orderId", "customerName", "amount", "orderDate")
            .fieldSetMapper(orderFieldSetMapper)
            .saveState(true)
            .build();
}
```

Here:

- `linesToSkip(1)` skips the header line.
- `.names(...)` supplies field names for the columns in exact order.
- `BeanWrapperFieldSetMapper` creates `Order` and binds its properties.
- `ConversionService` handles data types requiring conversion.
- `saveState(true)` saves reader state to support restart.

The names and order in `.names(...)` must match the file schema. If column order changes, the reader can bind the wrong data even if property names are valid.

## 15. When should you use a custom FieldSetMapper?

`BeanWrapperFieldSetMapper` fits well when the file structure closely mirrors the JavaBean structure and mapping is primarily property assignment. A custom mapper is a better fit when:

- Column names and property names differ significantly.
- One source field needs to populate multiple target properties.
- Multiple fields must be combined into a single value object.
- Per-column custom parsing rules are required.
- Values need normalization or computation during mapping.
- The target is an immutable object/record or lacks a no-arg constructor.
- Null/blank values need complex business-rule handling.

Custom mapper example:

```java
public class OrderFieldSetMapper implements FieldSetMapper<Order> {

    @Override
    public Order mapFieldSet(FieldSet fieldSet) {
        Order order = new Order();
        order.setOrderId(fieldSet.readLong("order_id"));
        order.setCustomerName(fieldSet.readString("customer_name").trim());
        order.setAmount(fieldSet.readBigDecimal("total_amount"));
        return order;
    }
}
```

Here, the custom mapper explicitly maps `order_id` to `orderId`, `customer_name` to `customerName`, and `total_amount` to `amount`. The logic is visible and easy to control when the file schema differs from the model.

## 16. Distinguishing mapping from business validation

Mapping answers: which property does a `FieldSet` value go into, and what Java type should it become? Validation answers: is the resulting object valid according to business rules?

For instance, `amount="-100.00"` can parse into `BigDecimal` successfully. The mapper does not inherently know whether negative orders are permitted. That rule belongs in a processor or a dedicated validator.

```java
@Bean
public ItemProcessor<Order, Order> validateOrderProcessor() {
    return order -> {
        if (order.getAmount().signum() < 0) {
            throw new InvalidOrderException("Order amount must not be negative");
        }
        return order;
    };
}
```

Separating mapping from validation clarifies error classification:

- Binding/conversion errors: the file cannot be converted into an object of the right type.
- Business errors: the object was created but violates business rules.
- System errors: database, filesystem, or dependent service failures.

Spring Batch can apply skip/retry policies for the corresponding exceptions. However, do not skip all binding errors or broad generic exceptions if doing so could silently drop critical data.

## 17. Common binding errors

When mapping fails, identify the root cause instead of just logging “cannot map row”.

| Cause | Example | Mitigation |
|---|---|---|
| Missing setter/property | `FieldSet` has `customerName`, bean lacks this writable property | Fix field/model name or use a custom mapper |
| Cannot instantiate target | Class lacks an appropriate constructor when using `targetType` | Add a no-arg constructor or use a prototype bean/custom mapper |
| Invalid data type | `amount="abc"` while property is `BigDecimal` | Check data and conversion rules |
| Wrong date format | `15/11/2026` does not match the formatter | Configure an explicit converter/formatter |
| Misspelled field name | `custmerName` instead of `customerName` | Fix `.names(...)`; avoid relying on fuzzy matching |
| Extra field | File has a column with no property | Review strict mode or exclude the column from mapping |
| Nested property cannot be instantiated | `address.city` but `address` cannot be created | Initialize the object graph or use a custom mapper |

Conversion errors are typically wrapped in a Spring binding exception, such as `BindException` or a property-access exception. The exact exception type depends on the binding path and version. When configuring skip, target the exact exception or root cause observed in logs/tests.

## 18. Strict mode, skip, and data errors

If `BeanWrapperFieldSetMapper` cannot bind a line, `FlatFileItemReader` can throw an exception and the Step applies fault tolerance if configured.

Example allowing a few lines with parse/binding errors to be skipped:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(validateOrderProcessor())
        .writer(orderWriter)
        .faultTolerant()
        .skip(FlatFileParseException.class)
        .skipLimit(20)
        .build();
```

This is only an example for reader parse errors; specific binding errors may throw different exception types and must be verified with tests. Do not assume every error raised by BeanWrapper is a `FlatFileParseException`.

If a file has schema-wide errors such as wrong column names or missing required columns, skipping line by line makes no sense because every line could be mis-mapped. Validate headers/schema before reading data and fail early when the file structure violates the contract.

## 19. Performance and safety when using the mapper

`BeanWrapperFieldSetMapper` uses reflection/property access and conversion to build objects. For most batch jobs, this overhead is reasonable and reduces boilerplate mapping code. If processing tens of millions of lines, measure actual throughput before replacing the mapper for performance reasons.

Key principles:

- Configure the mapper once before the Step runs; do not mutate target type, editors, or conversion service mid-processing.
- Use immutable, reusable converters.
- Avoid converters that rely on per-item mutable state.
- Keep mapping simple; move complex business logic to the processor.
- If the Step runs multi-threaded, verify thread safety of custom converters/editors and any shared state.
- Do not include sensitive data in exception messages or log entire lines if the file contains personal information.

When complex mapping is needed, a custom mapper can be both clearer and more efficient. Base the choice on schema complexity and maintainability, not just line count.

## 20. Testing BeanWrapperFieldSetMapper

You can test the mapper in isolation without running a full Job. Create a `FieldSet`, call `mapFieldSet()`, and verify properties are populated properly.

Example:

```java
@Test
void mapsFieldSetToOrderBean() throws Exception {
    BeanWrapperFieldSetMapper<Order> mapper = new BeanWrapperFieldSetMapper<>();
    mapper.setTargetType(Order.class);

    FieldSet fieldSet = new DefaultFieldSet(
            new String[] {"1001", "Lan", "125.50"},
            new String[] {"orderId", "customerName", "amount"}
    );

    Order order = mapper.mapFieldSet(fieldSet);

    assertEquals(1001L, order.getOrderId());
    assertEquals("Lan", order.getCustomerName());
    assertEquals(new BigDecimal("125.50"), order.getAmount());
}
```

Beyond the happy path, also test:

1. Invalid numeric values for numeric properties.
2. Dates in valid and invalid formats.
3. Field names with no matching property when strict is enabled.
4. Field names close to property names when distance limit is configured.
5. Unmatched fields when strict is disabled, confirming ignore behavior per implementation.
6. Nested properties with valid and invalid object graphs.
7. Target class lacking a no-arg constructor.
8. Files with real headers, delimiters, quotes, and encoding.
9. Job restart after several chunks have committed.

Integration tests with `FlatFileItemReader` confirm that the tokenizer builds the right `FieldSet` and the mapper receives the right column names and values. Isolated mapper unit tests cannot verify delimiters, quotes, headers, or `Resource` configuration.

## 21. Common misconceptions

**Assuming BeanWrapperFieldSetMapper reads files.** It only maps `FieldSet` into objects; `FlatFileItemReader`, `LineMapper`, and tokenizers handle reading and splitting lines.

**Assuming header names automatically match Java properties.** Field names come from tokenizer configuration or a configured header mechanism. Specify column names explicitly.

**Assuming every data type converts automatically in the right format.** Conversion depends on the conversion service/property editors. Dates, currencies, and locales require explicit configuration.

**Assuming fuzzy matching is always safe.** Two similarly named properties can be misbound. Prefer exact names and test the distance limit.

**Assuming strict=false solves all schema errors.** It may skip unmappable fields, but it does not validate that source data is right. A wrong schema can leave objects missing values.

**Using the mapper to enforce business rules.** The mapper converts structure and data types; the processor or validator should enforce business rules.

**Using BeanWrapperFieldSetMapper for immutable objects without a suitable factory.** If you cannot instantiate and set properties via JavaBean conventions, use a prototype bean or custom mapper.

## 22. Choosing a mapper for flat files

Use `BeanWrapperFieldSetMapper` when column names can be configured to match JavaBean properties, the target can be instantiated, and values convert cleanly via a conversion service or property editors. Configure `targetType`, strict mode, and conversion rules explicitly; only enable fuzzy matching when justified and tested.

If the file schema differs from the model, requires complex aliases, constructs nested objects with custom rules, or targets immutable objects, use a custom `FieldSetMapper`. Keep business validation in the processor or validator so mapping stays decoupled from business decisions.

When integrating with `FlatFileItemReader`, verify the entire chain from `Resource`, tokenizer, `FieldSet` names, and mapper to the model. For production files, test valid data, conversion errors, schema changes, skip policies, and restart. Organizing it this way lets `BeanWrapperFieldSetMapper` cut down boilerplate while keeping file ingestion clear and controllable.
