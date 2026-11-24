# Converting Strings to Numbers, Booleans, and Enums in SpEL

## 1. Why Type Conversion Is Needed

Spring Expression Language (SpEL) evaluates an expression and produces a runtime value. In many cases, that value needs to be converted to the type expected by the application: string to number, string to Boolean, or string to enum.

SpEL performs conversion via `TypeConverter` in `EvaluationContext`. Under standard configuration, `StandardTypeConverter` integrates with Spring `ConversionService` and uses Spring's default converters.

For example, an expression produces the String `'42'`, while Java code expects an Integer:

```java
ExpressionParser parser = new SpelExpressionParser();
StandardEvaluationContext context =
        new StandardEvaluationContext();

Integer quantity = parser.parseExpression("'42'")
        .getValue(context, Integer.class);

// quantity = 42
```

When calling `getValue(context, Integer.class)`, SpEL knows the target type is Integer and asks TypeConverter to convert the result to that type. If you only call `getValue(context)`, the natural result remains the String `"42"`; SpEL does not guess what type the caller will want later.

## 2. TypeConverter and ConversionService

Two main components:

- `TypeConverter` is the abstraction SpEL uses to convert values between a source type and a target type.
- Spring's `ConversionService` provides a reusable converter system across multiple parts of an application.

In `StandardEvaluationContext`, the default TypeConverter is `StandardTypeConverter`. This converter uses a shared default ConversionService if no dedicated ConversionService is supplied.

You can inspect or replace the TypeConverter:

```java
StandardEvaluationContext context =
        new StandardEvaluationContext();

TypeConverter converter = context.getTypeConverter();
```

Configuring a custom ConversionService:

```java
DefaultConversionService conversionService =
        new DefaultConversionService();

context.setTypeConverter(
        new StandardTypeConverter(conversionService));
```

This allows the application to add converters for business domain types, such as converting string aliases to enums or converting a custom data format into a domain type.

## 3. Converting Strings to Numeric Types

Spring provides converters from String to common numeric types, including:

- `Byte`, `Short`, `Integer`, `Long`.
- `Float`, `Double`.
- `BigInteger`, `BigDecimal`.

SpEL can convert a String result to the target type when calling `getValue()` with the corresponding Class:

```java
Integer count = parser.parseExpression("'42'")
        .getValue(context, Integer.class);

Long population = parser.parseExpression("'1200000'")
        .getValue(context, Long.class);

BigDecimal price = parser.parseExpression("'125.50'")
        .getValue(context, BigDecimal.class);
```

Numeric strings are processed according to the numeric syntax supported by Java/Spring. The default converter trims leading and trailing whitespace before parsing. The decimal separator uses a dot in standard numeric format, rather than automatically relying on the user's display locale.

For example:

```text
' 42 '       -> Integer 42
'125.50'     -> BigDecimal 125.50
'1.25E3'     -> Double 1250.0
```

Strings such as `'12,50'` are not standard decimal format for the default numeric converter. If the application accepts locale-formatted numbers (for example, comma as the decimal separator), register a dedicated converter with explicit locale rules.

### 3.1. Choosing the Right Target Numeric Type

Do not use a single numeric type for every case:

| Target Type | Common Use Cases |
|---|---|
| `Integer` | Small quantities, retry counts, indices. |
| `Long` | Numeric IDs or large-range quantities. |
| `Double` / `Float` | Approximate calculations, measurement data. |
| `BigInteger` | Large integers exceeding primitive type ranges. |
| `BigDecimal` | Currency and decimals requiring exact precision. |

For currency, convert directly from a decimal string to BigDecimal:

```java
BigDecimal amount = parser.parseExpression("'123456.78'")
        .getValue(context, BigDecimal.class);
```

Avoid converting a string to Double first and then constructing BigDecimal, because binary floating-point representation can introduce unwanted rounding inaccuracies.

## 4. Converting Strings to Boolean

Spring's default converter accepts several common Boolean representations, case-insensitively for words:

| Input String | Result |
|---|---|
| `"true"`, `"TRUE"`, `"on"`, `"yes"`, `"1"` | `true` |
| `"false"`, `"FALSE"`, `"off"`, `"no"`, `"0"` | `false` |

For example:

```java
Boolean enabled = parser.parseExpression("'yes'")
        .getValue(context, Boolean.class);

Boolean disabled = parser.parseExpression("'OFF'")
        .getValue(context, Boolean.class);

Boolean flag = parser.parseExpression("'1'")
        .getValue(context, Boolean.class);
```

Empty strings after trimming may be converted to null. A string outside the supported value set, such as `'enabled'` or `'maybe'`, is not automatically treated as true/false; conversion will fail.

If input data comes from a form or configuration file, validate values before evaluating the expression. Do not use truthiness rules from other languages to infer the behavior of Spring ConversionService.

## 5. Converting Strings to Enums

Spring supports converting Strings to enums by constant name. For example:

```java
public enum OrderStatus {
    NEW,
    PAID,
    SHIPPED,
    CANCELLED
}
```

You can request the enum type during evaluation:

```java
OrderStatus status = parser.parseExpression("'PAID'")
        .getValue(context, OrderStatus.class);

// OrderStatus.PAID
```

The default enum converter uses the enum's constant name. Name matching is case-sensitive:

```text
'PAID'  -> OrderStatus.PAID
'paid'  -> does not match default constant name
```

Strings are trimmed before conversion; empty strings may convert to null. A non-existent name such as `'COMPLETED'` causes a conversion error if the enum has no such constant.

When using enums in expressions, you can combine type references to access constants directly:

```text
T(com.example.OrderStatus).PAID
```

This is a way to reference an enum constant via `T(...)`, not converting a String to an enum. The two approaches differ:

- `'PAID'` with target type `OrderStatus.class`: TypeConverter converts String to enum.
- `T(com.example.OrderStatus).PAID`: SpEL resolves the enum type and accesses the static constant.

## 6. Conversion When Assigning to Typed Properties

Type conversion does not occur only when retrieving results via `getValue(context, TargetType.class)`. SpEL also converts values when assigning to properties or elements with a known target type.

Example configuration class:

```java
public class AppSettings {
    private Integer retryCount;
    private Boolean enabled;
    private OrderStatus status;

    public Integer getRetryCount() {
        return retryCount;
    }

    public void setRetryCount(Integer retryCount) {
        this.retryCount = retryCount;
    }

    public Boolean getEnabled() {
        return enabled;
    }

    public void setEnabled(Boolean enabled) {
        this.enabled = enabled;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public void setStatus(OrderStatus status) {
        this.status = status;
    }
}
```

Assigning strings to properties of different types:

```java
AppSettings settings = new AppSettings();

StandardEvaluationContext context =
        new StandardEvaluationContext(settings);

parser.parseExpression("retryCount").setValue(context, "5");
parser.parseExpression("enabled").setValue(context, "yes");
parser.parseExpression("status").setValue(context, "PAID");

// retryCount = 5
// enabled = true
// status = OrderStatus.PAID
```

When processing `setValue()`, SpEL knows the target type from the property metadata and uses TypeConverter to convert the string before assigning. If the converter cannot convert, the assignment fails and the value is not set to the desired target type.

## 7. Generic Metadata When Converting Collection Elements

Spring ConversionService can use the generic metadata of a target property to convert elements inside a collection.

Example `List<Boolean>` property:

```java
public class FeatureSettings {
    private List<Boolean> enabledFlags =
            new ArrayList<>(List.of(true, true));

    public List<Boolean> getEnabledFlags() {
        return enabledFlags;
    }

    public void setEnabledFlags(List<Boolean> enabledFlags) {
        this.enabledFlags = enabledFlags;
    }
}
```

You can assign a string to an element:

```java
FeatureSettings settings = new FeatureSettings();

StandardEvaluationContext context =
        new StandardEvaluationContext(settings);

parser.parseExpression("enabledFlags[0]")
        .setValue(context, "false");

Boolean firstFlag = settings.getEnabledFlags().get(0);
// Boolean.FALSE
```

SpEL and ConversionService can determine the target element type is Boolean from the List's generic metadata. Therefore, the string `"false"` is converted to Boolean instead of remaining a String.

This depends on the property's type metadata. If a collection is declared only as `List<Object>` or generic metadata is absent, the framework may not know the intended element type. When explicit conversion is needed, use a specific target type or convert elements individually in Java.

## 8. Explicit Conversion Using getValue()

If an expression produces a value whose type differs from what the caller needs, use the `getValue()` overload that takes a target Class:

```java
Integer retryCount = parser.parseExpression("'3'")
        .getValue(context, Integer.class);

Boolean active = parser.parseExpression("'on'")
        .getValue(context, Boolean.class);

OrderStatus status = parser.parseExpression("'SHIPPED'")
        .getValue(context, OrderStatus.class);
```

The target type must be compatible with the value or have a matching converter. If no converter exists, SpEL does not coerce types arbitrarily.

For example, do not assume any arbitrary string can be converted to a number:

```java
Integer invalid = parser.parseExpression("'three'")
        .getValue(context, Integer.class);
```

This expression throws a conversion error because `"three"` is not a valid integer representation.

If you need to inspect the result without failing the application flow, catch the exception at the Java boundary and provide an appropriate validation message.

## 9. Registering Custom Converters

Default converters fit common types. For custom business domain rules, you can register custom converters in ConversionService.

Example accepting the alias `COMPLETED` as another representation of the `PAID` enum:

```java
DefaultConversionService conversionService =
        new DefaultConversionService();

conversionService.addConverter(
        String.class,
        OrderStatus.class,
        source -> switch (source.trim().toUpperCase(Locale.ROOT)) {
            case "COMPLETED" -> OrderStatus.PAID;
            case "NEW" -> OrderStatus.NEW;
            case "PAID" -> OrderStatus.PAID;
            case "SHIPPED" -> OrderStatus.SHIPPED;
            case "CANCELLED" -> OrderStatus.CANCELLED;
            default -> throw new IllegalArgumentException(
                    "Unknown order status: " + source);
        });

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setTypeConverter(
        new StandardTypeConverter(conversionService));

OrderStatus status = parser.parseExpression("'completed'")
        .getValue(context, OrderStatus.class);

// OrderStatus.PAID
```

A custom converter should:

- Normalize inputs consistently, such as trimming and using `Locale.ROOT` for case conversion.
- Only accept values permitted by business rules.
- Report clear errors when input is invalid.
- Perform no side effects or external system access during conversion.
- Have unit tests for valid values, aliases, and invalid values.

A single configured ConversionService can be shared across multiple contexts if the converters match the same application rules.

## 10. Using TypeConverter in SimpleEvaluationContext

SimpleEvaluationContext also supports type conversion. This context restricts certain SpEL features such as constructor/type/bean references, yet value conversion can still be configured.

For example:

```java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding()
                .withTypeConverter(
                        new StandardTypeConverter(conversionService))
                .build();
```

If you only need to convert Strings to numbers, Booleans, or enums when reading/writing properties, there is no need to enable constructor invocation or type references. Choose the context according to the capabilities expressions actually need.

## 11. Common Conversion Errors

| Symptom | Common Cause | Resolution |
|---|---|---|
| String fails to convert to Integer | String contains non-numeric characters or exceeds type range. | Validate input and choose the appropriate Integer/Long/BigInteger. |
| Decimal number fails | Input uses locale comma while default converter expects standard numeric syntax. | Normalize format or register a locale-aware converter. |
| Empty string becomes null | Standard converter may treat an empty string after trim as null. | Validate empty strings before converting or use an appropriate wrapper/nullable type. |
| Boolean does not recognize value | String is not in true/on/yes/1 or false/off/no/0. | Normalize and validate the input value set. |
| Enum constant not found | Wrong enum name or case mismatch. | Use exact constant name or register a converter handling aliases/case. |
| setValue() fails to assign | Value cannot be converted to the target property type. | Check setter/property type and active TypeConverter. |
| Collection keeps elements as String | Collection generic metadata does not indicate target element type. | Declare specific generic type or convert elements explicitly. |
| getValue() returns String instead of Number | Target type was not passed to getValue(). | Use `getValue(context, Integer.class)` or the required target type. |
| Custom converter is not invoked | Converter was not registered in the ConversionService attached to context. | Use the right ConversionService when creating StandardTypeConverter and calling setTypeConverter(). |
| Error occurs only with null data | Target type is primitive or does not allow null. | Use wrapper types or handle null before assigning. |

## 12. Checklist for Testing Type Conversion

1. Identify the source type of the expression, typically String.
2. Explicitly identify the target type: Integer, Long, BigDecimal, Boolean, or enum.
3. Test valid values representing realistic formats.
4. Test leading/trailing whitespace, empty strings, and null if they can appear.
5. For Boolean, test accepted tokens and an invalid token.
6. For enums, test constant names, case differences, and aliases if any.
7. For numbers, test integers, decimals, scientific notation, range boundaries, and locale formats.
8. Test both `getValue(context, Target.class)` and `setValue()` if the application uses both.
9. Test generic metadata when assigning to collections or nested properties.
10. Ensure EvaluationContext uses the exact same TypeConverter/ConversionService as the application environment.

## 13. Key Takeaways

- SpEL uses TypeConverter to convert values to target types; StandardTypeConverter integrates Spring ConversionService.
- `getValue(context, Target.class)` requests converting the result to Target; `getValue(context)` keeps the expression's natural type.
- String can be converted to common numeric types such as Integer, Long, Double, BigInteger, and BigDecimal.
- Boolean recognizes true/on/yes/1 and false/off/no/0 by default; other values are not inferred automatically.
- String to enum is based on constant names; the default converter is case-sensitive.
- `setValue()` also converts according to the target property type.
- Generic metadata enables converting collection elements such as List<Boolean>.
- Custom converters can be added to DefaultConversionService and attached to StandardTypeConverter.
- Validate null, empty strings, numeric formats, invalid enums, and locale before passing data into business logic.

## References

- [Spring Framework Reference — Type Conversion](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework Reference — Type Conversion with Generics](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [StandardTypeConverter Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardTypeConverter.html)
- [ConversionService Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/convert/ConversionService.html)
- [DefaultConversionService Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/convert/support/DefaultConversionService.html)
