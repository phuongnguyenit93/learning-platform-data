# ParameterizedTest for Data Matrices

In JUnit Jupiter, `@ParameterizedTest` lets you run the same test method multiple times with different input data sets. Instead of writing several nearly identical `@Test` methods, you describe test data as rows. Each row produces an independent invocation of the method.

This is a suitable way to verify a rule across many cases: valid and invalid values, lower and upper boundaries, enum states, combinations of delivery mode and item quantity, or multiple inputs paired with expected outcomes.

## 1. Structure of a Parameterized Test

A parameterized test has three parts:

1. **Test method** annotated with `@ParameterizedTest` and declaring the parameters to receive.
2. **Data source** providing one or more sets of arguments via annotations such as `@ValueSource`, `@CsvSource`, or `@MethodSource`.
3. **Verification body** executing assertions on each set of arguments.

```java
@ParameterizedTest
@ValueSource(ints = {1, 2, 3, 5})
void acceptsPositiveQuantity(int quantity) {
    assertThat(quantity).isPositive();
}
```

JUnit creates four invocations for the method above. Each invocation receives its own `quantity` value. If the case `quantity = 3` fails, the result is tied to that corresponding invocation, helping pinpoint the failing input data.

Unlike `@Test`, `@ParameterizedTest` is a test template. JUnit requires at least one argument source to generate invocations. Each invocation still goes through the JUnit test lifecycle: callbacks and `@BeforeEach`/`@AfterEach` execute per run, while `@BeforeAll`/`@AfterAll` apply at the test container lifecycle level.

## 2. Required Dependencies

Parameterized test annotations and machinery belong to the `junit-jupiter-params` module. If the project uses the aggregate JUnit Jupiter artifact or Spring Boot's `spring-boot-starter-test`, this dependency is typically already included. For projects declaring JUnit artifacts individually, add it to the test classpath.

Gradle example:

```groovy
dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter")
}

tasks.test {
    useJUnitPlatform()
}
```

If a project manages individual JUnit modules separately, it can declare `junit-jupiter-api`, `junit-jupiter-params`, and the corresponding engine. Use the same release line for all JUnit modules; in Spring Boot projects, let Boot's dependency management control versions.

## 3. Built-in Data Sources

JUnit Jupiter provides multiple source annotations. Choosing a source matching the shape of the data keeps tests readable and reduces data setup boilerplate.

### 3.1. `@ValueSource`: A Single Simple Parameter

`@ValueSource` fits when each invocation needs only a single value of a supported type, such as `int`, `long`, `double`, `boolean`, `char`, `String`, or `Class`.

```java
@ParameterizedTest(name = "[{index}] accepts quantity {0}")
@ValueSource(ints = {1, 2, 10, 100})
void acceptsPositiveQuantity(int quantity) {
    assertThat(quantity).isGreaterThan(0);
}
```

Here each element in `ints` is a single-element argument set. `@ValueSource` is not suitable when a case requires multiple columns simultaneously—such as input, expected output, and error message; in that case, use `@CsvSource` or `@MethodSource`.

### 3.2. `@NullSource`, `@EmptySource`, and `@NullAndEmptySource`

These three annotations are helpful when testing absent or empty inputs:

- `@NullSource` passes `null` to a reference-type parameter.
- `@EmptySource` passes an empty value for supported types such as `String`, collections, maps, and arrays.
- `@NullAndEmptySource` combines both `null` and empty cases.

You can combine them with `@ValueSource` to test whitespace strings as well:

```java
@ParameterizedTest
@NullAndEmptySource
@ValueSource(strings = {" ", "\t", "\n"})
void rejectsMissingOrBlankCustomerCode(String customerCode) {
    assertThat(customerCode == null || customerCode.isBlank()).isTrue();
}
```

Do not pass `null` into primitive parameters like `int` or `boolean`; those types cannot represent `null`. If a test needs to verify `null`, use the corresponding wrapper reference type.

### 3.3. `@EnumSource`: Testing Enum Values

`@EnumSource` creates invocations from enum constants. By default, all constants of the enum are used. You can select specific names or exclude certain values.

```java
enum DeliveryMode {
    STANDARD,
    EXPRESS,
    PICKUP
}

@ParameterizedTest
@EnumSource(value = DeliveryMode.class, names = {"STANDARD", "EXPRESS"})
void deliveryModesRequireShippingAddress(DeliveryMode mode) {
    assertThat(mode).isIn(DeliveryMode.STANDARD, DeliveryMode.EXPRESS);
}
```

Commonly used modes:

| Mode | Meaning |
|---|---|
| `INCLUDE` | Runs only the constants listed in `names`. |
| `EXCLUDE` | Runs all constants except those listed. |
| `MATCH_ALL` | Selects names matching all provided regular expressions. |
| `MATCH_ANY` | Selects names matching at least one provided regular expression. |

Example excluding `PICKUP`:

```java
@ParameterizedTest
@EnumSource(value = DeliveryMode.class,
        mode = EnumSource.Mode.EXCLUDE,
        names = "PICKUP")
void shippedModesHaveShippingCost(DeliveryMode mode) {
    assertThat(mode).isIn(DeliveryMode.STANDARD, DeliveryMode.EXPRESS);
}
```

### 3.4. `@CsvSource`: Multiple Data Columns Inline in the Test

`@CsvSource` works well for small, readable matrices. Each CSV line is one invocation; columns map sequentially to method parameters.

```java
@ParameterizedTest(name = "quantity={0}, expectedValid={1}")
@CsvSource({
        "1, true",
        "2, true",
        "100, true",
        "0, false",
        "-1, false"
})
void validatesQuantity(int quantity, boolean expectedValid) {
    assertThat(QuantityRules.isValid(quantity)).isEqualTo(expectedValid);
}
```

In this example, the two columns are converted to `int` and `boolean` respectively. The assertion uses the second column as the expected outcome so each row describes both input and expected result.

Several `@CsvSource` options help keep data clear:

- `delimiter` changes the column delimiter character; `delimiterString` uses a delimiter string.
- `nullValues` declares which token in the data represents `null`.
- `emptyValue` specifies how a quoted empty string value is represented.
- `ignoreLeadingAndTrailingWhitespace` controls stripping whitespace around values.
- `useHeadersInDisplayName` can use column names in display names in JUnit versions supporting this option.

Example using a token to represent `null`:

```java
@ParameterizedTest
@CsvSource(value = {
        "customer-1, ACTIVE",
        "NIL, UNKNOWN"
}, nullValues = "NIL")
void handlesOptionalCustomerCode(String customerCode, String expectedStatus) {
    // Verify rule based on customerCode and expectedStatus.
}
```

If a field contains commas or delimiter characters, use CSV quoting syntax to keep that field as a single value. For complex data, many columns, or reusable datasets, `@MethodSource` is usually easier to maintain than long CSV strings.

### 3.5. `@CsvFileSource`: Data from a CSV File

When a matrix has many rows, you can separate the data from test code. `@CsvFileSource` reads files on the classpath or from file paths according to the annotation configuration.

Example file `src/test/resources/quantity-cases.csv`:

```csv
quantity,expectedValid
1,true
2,true
100,true
0,false
-1,false
```

Corresponding test:

```java
@ParameterizedTest(name = "quantity={0}, valid={1}")
@CsvFileSource(resources = "/quantity-cases.csv", numLinesToSkip = 1)
void validatesQuantityFromCsv(int quantity, boolean expectedValid) {
    assertThat(QuantityRules.isValid(quantity)).isEqualTo(expectedValid);
}
```

`numLinesToSkip = 1` skips the header row. Data files should be managed alongside tests, use clear column names, and avoid cryptic values. When tests depend on files, place them properly under `src/test/resources` so the build includes them on the test classpath.

### 3.6. `@MethodSource`: Java-Based Data Sources

`@MethodSource` fits when data must be constructed in code, requires diverse parameter types, computes expected values, or names individual cases. Factory methods typically return `Stream<Arguments>`.

```java
class QuantityRulesTest {

    @ParameterizedTest(name = "[{index}] {0}")
    @MethodSource("quantityCases")
    void validatesQuantity(String caseName, int quantity, boolean expectedValid) {
        assertThat(QuantityRules.isValid(quantity)).isEqualTo(expectedValid);
    }

    static Stream<Arguments> quantityCases() {
        return Stream.of(
                Arguments.of("minimum accepted", 1, true),
                Arguments.of("ordinary quantity", 5, true),
                Arguments.of("zero", 0, false),
                Arguments.of("negative", -1, false)
        );
    }
}
```

The method name passed to `@MethodSource` must match the factory. Under the default test instance lifecycle, factory methods in the same class must be `static`. If using `@TestInstance(TestInstance.Lifecycle.PER_CLASS)`, an instance factory method can be used. Factories can also live in another class using the class-and-method reference syntax per JUnit conventions.

Factories can return source types such as `Stream`, `Collection`, `Iterable`, `Iterator`, or arrays, depending on JUnit's contract. For each multi-parameter case, use `Arguments.of(...)` to create an argument tuple whose order matches the test method signature.

### 3.7. `@ArgumentsSource`: Custom Providers

When data generation logic is reused across many tests, you can write an `ArgumentsProvider` and reference it with `@ArgumentsSource`.

```java
class QuantityArgumentsProvider implements ArgumentsProvider {

    @Override
    public Stream<? extends Arguments> provideArguments(ExtensionContext context) {
        return Stream.of(
                Arguments.of(1, true),
                Arguments.of(5, true),
                Arguments.of(0, false),
                Arguments.of(-1, false)
        );
    }
}

class QuantityProviderTest {

    @ParameterizedTest
    @ArgumentsSource(QuantityArgumentsProvider.class)
    void validatesQuantity(int quantity, boolean expectedValid) {
        assertThat(QuantityRules.isValid(quantity)).isEqualTo(expectedValid);
    }
}
```

Custom providers are useful when there is shared data-generation logic, but they make tests harder to read if created merely to replace a short `@CsvSource`. Name providers after their purpose and avoid hiding important test values from readers.

## 4. Building Data Matrices and Input Combinations

One row in a data source usually represents **one complete test case**. Example:

| Case | Delivery mode | Quantity | Expected |
|---|---|---:|---|
| A | STANDARD | 1 | Valid |
| B | STANDARD | 3 | Valid |
| C | EXPRESS | 1 | Valid |
| D | EXPRESS | 3 | Valid |

If you want to test all combinations between two delivery modes and two quantities, you can generate a Cartesian product using `@MethodSource`:

```java
static Stream<Arguments> deliveryAndQuantityCases() {
    return Stream.of(DeliveryMode.STANDARD, DeliveryMode.EXPRESS)
            .flatMap(mode -> Stream.of(1, 3)
                    .map(quantity -> Arguments.of(mode, quantity)));
}

@ParameterizedTest(name = "{0} with quantity {1}")
@MethodSource("deliveryAndQuantityCases")
void acceptsSupportedDeliveryAndQuantity(DeliveryMode mode, int quantity) {
    assertThat(ShippingRules.isSupported(mode, quantity)).isTrue();
}
```

With 2 delivery modes and 2 quantities, this source produces 4 invocations. When there are many dimensions, the number of combinations grows as the product of each dimension's values. For instance, 4 sizes, 5 colors, and 3 shipping methods produce 60 combinations. You do not always need to run the full Cartesian product; identify high-risk interactions, critical boundaries, and combinations that must be proven. Select representative rows or design pairwise datasets when dimensionality is large.

Do not confuse a list of single values with a multidimensional matrix. `@ValueSource` generates single-parameter invocations. If the method takes two parameters, the source must provide both arguments for every invocation, such as `@CsvSource`, `@MethodSource`, or a custom provider.

## 5. Argument Conversion and Aggregation

### 5.1. Automatic Type Conversion

JUnit Jupiter can convert several common source types into matching parameter types. For example, values in `@CsvSource` are read as strings and converted into `int`, `long`, `boolean`, enums, or other supported standard types when requested by the test signature. This keeps CSV data concise without manual parsing inside the test body.

When the target type is a complex application type, use `@ConvertWith` with an `ArgumentConverter`, or construct objects directly via `@MethodSource`. Example converter for `BigDecimal`:

```java
class MoneyConverter extends SimpleArgumentConverter {

    @Override
    protected Object convert(Object source, Class<?> targetType)
            throws ArgumentConversionException {
        if (targetType != BigDecimal.class || !(source instanceof String value)) {
            throw new ArgumentConversionException("Expected a decimal string");
        }

        try {
            return new BigDecimal(value);
        } catch (NumberFormatException exception) {
            throw new ArgumentConversionException("Invalid decimal: " + value, exception);
        }
    }
}

@ParameterizedTest
@CsvSource({"10.50", "0.99", "125.00"})
void acceptsMoneyAmount(@ConvertWith(MoneyConverter.class) BigDecimal amount) {
    assertThat(amount).isPositive();
}
```

If the data source already provides `BigDecimal`, `LocalDate`, or explicitly constructed value objects, `@MethodSource` is often easier to read than a converter because there is no extra conversion rule to maintain.

### 5.2. `ArgumentsAccessor`: Accessing Columns by Position

When using CSV data with many columns, sometimes you do not want to declare a separate Java parameter for each column. `ArgumentsAccessor` lets you read arguments by index:

```java
@ParameterizedTest
@CsvSource({
        "SKU-1, 2, true",
        "SKU-2, 0, false"
})
void validatesOrderRow(ArgumentsAccessor row) {
    String sku = row.getString(0);
    int quantity = row.getInteger(1);
    boolean expectedValid = row.getBoolean(2);

    assertThat(OrderRules.isValid(sku, quantity)).isEqualTo(expectedValid);
}
```

`ArgumentsAccessor` is convenient for flexible reading, but indices like `0`, `1`, `2` convey less meaning than parameter names. For stable structures, declare explicit parameters or use `@AggregateWith` to bundle a row into an object with named fields.

### 5.3. Aggregating a Data Row into an Object

`@AggregateWith` lets you use an `ArgumentsAggregator` to transform multiple columns into a domain object. This helps when tests work with a meaningful data structure, such as `OrderInput`.

```java
record OrderInput(String sku, int quantity) {}

class OrderInputAggregator implements ArgumentsAggregator {

    @Override
    public Object aggregateArguments(ArgumentsAccessor row, ParameterContext context)
            throws ArgumentsAggregationException {
        return new OrderInput(row.getString(0), row.getInteger(1));
    }
}

@ParameterizedTest
@CsvSource({"SKU-1, 2", "SKU-2, 5"})
void acceptsOrderInput(@AggregateWith(OrderInputAggregator.class) OrderInput input) {
    assertThat(input.quantity()).isPositive();
}
```

Aggregators help tests focus on meaningful objects instead of manipulating loose columns. However, with only two simple parameters, declaring `String sku, int quantity` directly is usually clearer.

## 6. Naming Each Invocation

When a method runs many times, clear display names help identify which case failed in the IDE and test reports. `@ParameterizedTest` supports templates in its `name` attribute:

| Placeholder | Content |
|---|---|
| `{index}` | Invocation index number. |
| `{arguments}` | List of arguments. |
| `{argumentsWithNames}` | Arguments with parameter names when the data source supplies suitable naming metadata and the version supports it. |
| `{0}`, `{1}`, ... | Positional arguments starting from 0. |

Example:

```java
@ParameterizedTest(name = "[{index}] {0}: quantity={1}, valid={2}")
@MethodSource("quantityCases")
void validatesQuantity(String caseName, int quantity, boolean expectedValid) {
    assertThat(QuantityRules.isValid(quantity)).isEqualTo(expectedValid);
}
```

With `MethodSource`, you can use `Named` to label an argument:

```java
static Stream<Arguments> deliveryCases() {
    return Stream.of(
            Arguments.of(Named.of("economy", DeliveryMode.STANDARD)),
            Arguments.of(Named.of("fast", DeliveryMode.EXPRESS))
    );
}
```

Test names should describe meaningful data or expectations. A name like `case 4` is less helpful than `zero quantity is rejected`, especially when data ordering changes.

## 7. Combining with Spring Test

Parameterized tests belong to JUnit Jupiter. When a test needs a Spring `ApplicationContext`, you can combine `@ParameterizedTest` with `@SpringJUnitConfig` or an appropriate Spring Test configuration. Spring Extension still manages the context and dependency injection; JUnit's parameter source feeds data to each invocation.

Example of a Spring service tested with multiple inputs:

```java
@SpringJUnitConfig(classes = PricePolicyTestConfiguration.class)
class PricePolicyParameterizedTest {

    @Autowired
    private PricePolicy pricePolicy;

    @ParameterizedTest(name = "quantity={0} -> discount={1}")
    @CsvSource({
            "1, 0",
            "4, 0",
            "5, 5",
            "10, 10"
    })
    void calculatesDiscount(int quantity, int expectedDiscount) {
        assertThat(pricePolicy.discountPercent(quantity)).isEqualTo(expectedDiscount);
    }
}
```

Here `@SpringJUnitConfig` integrates JUnit Jupiter with Spring TestContext and builds a context from `PricePolicyTestConfiguration`. Spring injects `PricePolicy` into the test instance. `@CsvSource` generates invocations and passes `quantity` and `expectedDiscount` to each run. The test does not need to manually initialize the context for each row; Spring Test manages lifecycle and context caching per configuration.

If the test only verifies a pure Java function or a rule without Spring dependencies, do not load an `ApplicationContext`. Using a standalone JUnit parameterized test is simpler and faster. Only add a Spring context when the behavior under verification genuinely depends on Spring beans, configuration, or infrastructure.

## 8. Designing Meaningful Test Matrices

A good matrix is not just about having many rows. Each row should prove a specific behavior or boundary. When designing data, identify:

- **Normal values:** typical inputs seen in regular usage flows.
- **Boundary values:** immediately below, exactly at, and immediately above accepted thresholds.
- **Abnormal inputs:** `null`, empty strings, blank strings, negative numbers, unsupported enums, or malformed formats.
- **Expected outcomes:** booleans, exceptions, states, calculated values, or parts of a returned object.
- **Case names:** concise labels so readers understand why each row exists.

Example matrix for a quantity rule from 1 to 100:

| Group | Input | Expected |
|---|---:|---|
| Valid lower boundary | 1 | Valid |
| Inside range | 50 | Valid |
| Valid upper boundary | 100 | Valid |
| Below boundary | 0 | Invalid |
| Above boundary | 101 | Invalid |
| Negative number | -1 | Invalid |

Avoid adding duplicate rows that contribute no extra verification value. If several rows test the exact same outcome and logic branch, consider keeping only the truly necessary representatives. For multi-condition rules, each row should clarify which condition is being triggered and how the remaining conditions are held constant.

## 9. When to Use Which Source

| Situation | Suitable Source |
|---|---|
| Single parameter, short value list | `@ValueSource` |
| Checking `null`, empty strings, or empty collections | `@NullSource`, `@EmptySource`, `@NullAndEmptySource` |
| Iterating over some or all enum values | `@EnumSource` |
| Multiple simple columns, small matrix | `@CsvSource` |
| Many-row matrix managed as external data | `@CsvFileSource` |
| Computed data, complex objects, or multidimensional combinations | `@MethodSource` |
| Data provisioning rules needed for broad reuse | `@ArgumentsSource` |
| Multiple columns needing aggregation into an object | `@AggregateWith` or `@MethodSource` returning suitable objects |

Prefer the data source that expresses the test's structure most clearly. `@CsvSource` is easy to scan for a few short rows; `@MethodSource` is easier to maintain when data involves logic or objects; `@ArgumentsSource` should be reserved for genuinely reusable providers.

## 10. Common Mistakes

### Missing the `junit-jupiter-params` Dependency

If the IDE does not recognize `@ParameterizedTest`, `@ValueSource`, or `@MethodSource`, inspect the test classpath. Projects using the aggregate JUnit Jupiter artifact or `spring-boot-starter-test` normally already include this module; projects declaring dependencies manually must add it.

### Argument Count Not Matching the Test Signature

Each invocation must supply enough arguments for the parameters managed by the data source, in matching order and convertible types. For example, if `@CsvSource` has three columns, the method must accept three corresponding parameters unless using `ArgumentsAccessor` or an aggregator.

### `@MethodSource` Factory Method Not Found

Check the name in `@MethodSource`, visibility, and `static` rules of the factory method. Under the default lifecycle, a method source in the same class must be `static`. If using an instance factory, configure `@TestInstance(PER_CLASS)` intentionally.

### Using `@ValueSource` for Multiple Parameters

`@ValueSource` supplies only one argument per invocation. For input and expected values together, use `@CsvSource` or `@MethodSource` to describe the full row.

### Passing `null` into Primitive Types

`@NullSource` cannot assign `null` to `int`, `long`, or `boolean`. Use reference wrapper types if the test must check `null`, or separate null cases from numeric value cases.

### Overly Large and Slow Matrices

Cartesian products can cause invocation counts to grow rapidly. Generate all combinations only when the test objective truly requires it. With many dimensions, identify critical interactions, test boundaries, and use appropriate combination selection techniques to keep runtimes reasonable.

### Invocation Names That Do Not Help Diagnose Failures

Default names or index-only names make reports hard to read. Set `name` using key data fields, descriptive arguments, or `Named` when needed.

### Putting Too Much Logic in Data Sources

Factory methods should describe cases and how data is constructed. If a factory contains heavy business branching, the test may duplicate logic under test or obscure the matrix's meaning. Keep expected values explicit and never compute expectations using the very function being tested.

## 11. Checklist When Writing a ParameterizedTest

Before finishing the test, verify the following points:

- The method uses `@ParameterizedTest` and has an appropriate data source.
- Each data row represents a meaningful case with clear input and expected value.
- Parameter count, order, and types match the data source.
- Relevant normal, boundary, and abnormal inputs are covered.
- Invocation names are clear enough to pinpoint a failing row.
- The data source is readable and stored appropriately for the matrix size.
- If using Spring, load an `ApplicationContext` only when the behavior under verification genuinely depends on Spring.

`@ParameterizedTest` turns a single test rule into multiple executions backed by transparent data. When every row clearly expresses a scenario and expected outcome, the data matrix serves as living documentation of system behavior while expanding test coverage without duplicating nearly identical `@Test` methods.
