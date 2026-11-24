# Conversion Errors and Diagnostic Information

## Objectives

Spring Expression Language (SpEL) can convert values between data types when evaluating expressions. Conversion typically occurs when assigning values to properties, passing arguments to methods or constructors, or requesting an expression result in a specific Java type. If no suitable converter exists, data is invalid, or the conversion cannot be performed, evaluation will raise an error.

Accurate diagnosis requires identifying the **source value**, **target type**, **conversion point**, and **TypeConverter/ConversionService** used by the EvaluationContext. The error message is only the starting point; you need to inspect the message code, expression position, and root exception to find the cause.

After this lesson, you will be able to:

- Recognize SpEL operations that can trigger type conversion.
- Understand the roles of TypeConverter and ConversionService.
- Distinguish parse errors from conversion errors during evaluation.
- Read SpelEvaluationException and related diagnostic information.
- Register a custom Converter when business data types require custom rules.
- Test conversion for properties, method arguments, constructor arguments, and result types.
- Create tests that reproduce errors using the application's exact EvaluationContext.

## 1. When Does SpEL Perform Type Conversion?

SpEL does not merely read and compute values. In many situations, it must convert a value from its current type to the type required by an operation.

### Assigning Values to Properties

Suppose a class has an integer property:

~~~java
public class Account {
    private Integer retryCount;

    public Integer getRetryCount() {
        return retryCount;
    }

    public void setRetryCount(Integer retryCount) {
        this.retryCount = retryCount;
    }
}
~~~

Expression assigning a string to the property:

~~~text
retryCount = '5'
~~~

If the context's TypeConverter supports converting String to Integer, the assigned value can become the integer 5. If the string cannot be converted to Integer, the assignment fails during evaluation.

### Requesting a Result Type

An application can request the result in a specific type:

~~~java
Expression expression = parser.parseExpression("'42'");
Integer value = expression.getValue(context, Integer.class);
~~~

The expression originally produces a String, yet getValue requests an Integer. SpEL uses the context's conversion mechanism to convert the result if a suitable converter exists.

### Method or Constructor Arguments

When invoking a method or constructor, the actual argument type may differ from the parameter type expected by the Java method. SpEL can use TypeConverter while preparing arguments if conversion is supported.

For example, a method accepting an Integer can be called with an expression value of another type if the context can convert that type. With overloads, conversion and method resolution can influence call selection. Check method signatures and actual argument types instead of assuming any value will convert automatically.

## 2. TypeConverter and ConversionService

**TypeConverter** is the abstraction SpEL uses to check and perform conversions. EvaluationContext supplies the TypeConverter for expression evaluation.

In Spring, **StandardTypeConverter** is a common implementation. It integrates with Spring ConversionService to use Spring's conversion rules.

You can picture the processing flow:

1. SpEL identifies the source value and the target type required by the operation.
2. SpEL asks TypeConverter to check conversion capability.
3. TypeConverter uses the configured ConversionService or converters.
4. If a matching conversion exists, the value is converted to the target type.
5. If conversion is not possible, an exception is thrown and the expression does not complete.

ConversionService provides operations to check and perform conversions. It can use Spring's built-in converters or converters registered by the application.

Do not treat conversion as ordinary Java casting. Casting only changes how an object is referenced when types have a compatible relationship; conversion can create a new value from data of a different type, such as String to Integer or String to an enum.

## 3. Configuring ConversionService for SpEL

You can create a StandardTypeConverter from a ConversionService and attach it to a StandardEvaluationContext.

~~~java
DefaultConversionService conversionService =
    new DefaultConversionService();

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setTypeConverter(
    new StandardTypeConverter(conversionService)
);
~~~

Conversions in expressions will then use the configured ConversionService.

Evaluation example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression("'125'");
Integer result = expression.getValue(context, Integer.class);
~~~

If ConversionService has a matching converter, the result is Integer 125.

In a Spring application, you can use the ConversionService provided by the application context instead of creating a separate instance. This ensures SpEL uses the same conversion rules used by the rest of the application.

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext(rootObject);

context.setTypeConverter(
    new StandardTypeConverter(applicationConversionService)
);
~~~

The variable name applicationConversionService in the example represents the ConversionService configured and provided by the application. Use the exact bean or instance managed by your application.

If the application uses SimpleEvaluationContext, configure the conversion service through the builder appropriate for the Spring version running. Do not assume the two EvaluationContext types share the same builders or full feature set.

## 4. Common Conversion Types

Spring ConversionService typically provides many common conversions, depending on source type, target type, and configuration.

| Source Type | Target Type | Example Data |
|---|---|---|
| String | Integer | "42" |
| String | Boolean | "true" |
| String | Enum | "ACTIVE" |
| String | BigDecimal | "125.50" |
| Number | Another Number type | Integer to Long |
| Collection | Collection with a different element type | List<String> to List<Integer>, if conversion supports it |
| String | LocalDate | "2026-11-12", when an appropriate converter/formatter exists |

Do not assume every string is valid. For example:

- Empty strings may behave differently depending on the converter.
- Strings containing non-digit characters cannot be converted to Integer by a typical numeric converter.
- Enum names must match the converter's rules.
- Dates depend on the format and configured converter/formatter.
- Collection conversion also depends on converting each element and target type information.

If data formats come from users or configuration files, validate before passing them into expressions. ConversionService assists with type conversion; it does not replace business validation.

## 5. Reading Conversion Error Messages

When SpEL cannot convert a value, the exception is usually surfaced via **SpelEvaluationException**. The message may include a message code and details about the source type, target type, or operation that could not be performed.

Illustrative example:

~~~text
EL1001E: Type conversion problem, cannot convert from java.lang.String to java.lang.Integer
~~~

Exact wording depends on the Spring version, converter, and actual data. Do not write application logic based on matching the entire message string because wording can change.

When reading an error, identify:

- Source type: what type is the expression or property returning?
- Target type: what type is the operation requesting?
- Actual value: does the data have a valid format and value range?
- Conversion path: which converter is being used or missing?
- Expression position: in which part of the expression did the error occur?
- Root exception: did the converter throw a more detailed error in the cause chain?

Source and target type messages often help narrow down the issue quickly. However, if the error originates from a custom converter, the deeper cause may be a business format or validation rule inside the converter.

## 6. Distinguishing Parse Errors and Conversion Errors

SpEL has distinct phases, so you must identify which phase an error occurred in.

**Parse errors** occur when the parser cannot parse the expression syntax. For example, unbalanced quotes or misplaced operators can prevent the expression from being constructed.

**Evaluation errors** occur after the expression has been parsed, when SpEL accesses properties, invokes methods, assigns values, or performs conversion.

For example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("'not-a-number'");

Integer value = expression.getValue(context, Integer.class);
~~~

The expression is syntactically valid and parses successfully. The error only appears when getValue asks to convert String to Integer.

Separating the two phases avoids investigating the wrong place. If parsing fails, check syntax. If parsing succeeds yet evaluation fails, inspect the root object, variables, properties, methods, converters, and input data.

## 7. Extracting Diagnostic Information from Exceptions

You can catch SpelEvaluationException at the boundary where the application evaluates expressions:

~~~java
try {
    Integer result = expression.getValue(context, Integer.class);
    return result;
}
catch (SpelEvaluationException ex) {
    // Log the error code, position, and expression ID.
    throw ex;
}
~~~

SpelEvaluationException provides details such as message code, values inserted into the message, and the relevant position in the expression. Specific accessors can be checked against the Spring version in use.

Example of logging structured information:

~~~java
catch (SpelEvaluationException ex) {
    logger.warn(
        "SpEL evaluation failed: expressionId={}, messageCode={}, position={}",
        expressionId,
        ex.getMessageCode(),
        ex.getPosition()
    );
    throw ex;
}
~~~

For deeper diagnosis, inspect the cause chain for ConversionException or specific exceptions thrown by the converter. With Spring ConversionService, errors may belong to types such as ConverterNotFoundException or ConversionFailedException.

Not every conversion failure has the same root exception class. Log the actual exception class and cause instead of assuming a single type.

### Information Worth Logging

A useful diagnostic log typically includes:

- Rule/expression ID or name.
- Expression version.
- SpEL message code.
- Error position if available.
- Source and target types when identifiable.
- Root exception class.
- Correlation ID or request ID.
- Relevant EvaluationContext type and conversion configuration.

Do not log full expression inputs or variable values if they may contain passwords, tokens, personal data, or sensitive information. You can log data types, lengths, or reference IDs instead of raw values.

## 8. Registering a Custom Converter

When a business type has custom conversion rules, the application can register a Converter with ConversionService.

Example converting a status code string into an enum:

~~~java
public enum OrderStatus {
    NEW, PAID, SHIPPED, CANCELLED
}
~~~

Converter:

~~~java
public class StringToOrderStatusConverter
        implements Converter<String, OrderStatus> {

    @Override
    public OrderStatus convert(String source) {
        if (source == null || source.isBlank()) {
            throw new IllegalArgumentException(
                "Order status must not be blank");
        }

        return OrderStatus.valueOf(
            source.trim().toUpperCase(Locale.ROOT)
        );
    }
}
~~~

Registering the converter:

~~~java
DefaultConversionService conversionService =
    new DefaultConversionService();

conversionService.addConverter(
    new StringToOrderStatusConverter()
);

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setTypeConverter(
    new StandardTypeConverter(conversionService)
);
~~~

Afterward, expressions or assignments needing to convert String to OrderStatus can use the registered converter.

In a Spring application, converters are usually registered in the shared ConversionService per application configuration. Avoid creating a separate ConversionService in every location if other parts of the application need the same conversion rules.

A converter should have deterministic behavior, clear error reporting, and no side effects. Do not use converters to query databases, call remote services, or perform stateful business logic.

## 9. Conversion in Collections and Generic Types

Conversion does not apply only to single scalar values. Spring can convert collections or collection elements when sufficient type information and matching converters exist.

For example, an operation may expect List<Integer> while the source is List<String>. Conversion requires a converter for each element and sufficiently specific target type information.

When working with generic collections, TypeDescriptor helps describe source and target types in greater detail than a simple Class. This matters because List.class alone cannot express whether elements should be Integer or String.

If collection conversion fails, identify which element could not be converted. You can test the converter directly on individual elements to separate data errors from collection structure errors.

Do not assume every collection can be converted between any types. Converters must support the required conversion and the target collection must be instantiable by the mechanism in use.

## 10. Testing Converters Before Evaluating Expressions

If an application needs to diagnose a conversion beforehand, it can query ConversionService directly:

~~~java
boolean supported = conversionService.canConvert(
    String.class,
    Integer.class
);
~~~

If direct conversion testing is needed:

~~~java
Integer value = conversionService.convert("42", Integer.class);
~~~

This check confirms whether ConversionService supports a simple type pair. However, it does not replace full expression testing because SpEL also involves the root object, property accessors, method resolvers, target descriptors, and evaluation context.

For generic types or metadata-dependent conversions, use the appropriate TypeDescriptor APIs rather than checking only by Class.

A useful workflow is:

1. Test the converter independently with input data.
2. Inspect the conversion service used by the EvaluationContext.
3. Evaluate the expression with the same context.
4. Compare the actual result type with the target type requested by the application.

## 11. Common Conversion Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| String fails to convert to Integer | String contains non-numeric characters or is empty | Validate format before evaluating |
| Converter not found | ConversionService lacks a converter for the type pair | Register an appropriate Converter |
| Custom converter is not called | Converter was registered in a different service than the context's | Check the active TypeConverter and ConversionService |
| Enum conversion fails | Wrong enum name or normalization mismatch | Normalize input and define a converter |
| Date conversion fails | Format mismatch or missing converter/formatter | Define format explicitly and test locales |
| Property assignment fails | Source value cannot be converted to the property type | Check setter, target type, and conversion service |
| getValue with target type fails | Expression result cannot be converted to the requested type | Check return type and converters |
| Method invocation fails | Argument incompatible with method parameter | Check signature and argument types |
| Fails only in production | ConversionService or context configuration differs from tests | Share context factory and conversion configuration |
| Unclear error message | Only general message logged, cause chain ignored | Log message code, position, and root exception |

## 12. Testing Conversion and Errors

You should test both successful and failing conversion cases.

Example testing String-to-Integer conversion in SpEL:

~~~java
@Test
void convertsStringResultToInteger() {
    ExpressionParser parser = new SpelExpressionParser();
    StandardEvaluationContext context =
        new StandardEvaluationContext();

    Expression expression = parser.parseExpression("'42'");

    assertEquals(
        Integer.valueOf(42),
        expression.getValue(context, Integer.class)
    );
}
~~~

Example testing failing conversion:

~~~java
@Test
void reportsInvalidIntegerConversion() {
    ExpressionParser parser = new SpelExpressionParser();
    StandardEvaluationContext context =
        new StandardEvaluationContext();

    Expression expression =
        parser.parseExpression("'not-a-number'");

    assertThrows(
        SpelEvaluationException.class,
        () -> expression.getValue(context, Integer.class)
    );
}
~~~

For custom converters, verify:

- Valid inputs convert to the expected type.
- Empty or null inputs behave per contract.
- Malformed inputs produce errors with a clear cause.
- The converter is registered in the right ConversionService.
- StandardTypeConverter in EvaluationContext uses the right service.
- Expressions trigger conversion through the actual operation used.
- Test configuration matches production.

For collections, add a case with one invalid element among valid elements. Clarify whether conversion fails as a whole or the application has a policy to handle elements individually.

## 13. Procedure for Diagnosing Conversion Errors

When an expression raises a conversion error:

1. **Identify the error phase.** Check whether the failure occurred during parsing or when calling getValue/setValue.
2. **Record expression ID and position.** Use information from the exception to pinpoint the failing expression fragment.
3. **Identify source and target types.** Check the value's actual type and the type required by the operation.
4. **Inspect the data.** Verify strings, numbers, enums, or collections have valid formats and value ranges.
5. **Inspect the context.** Confirm which TypeConverter and ConversionService the expression is using.
6. **Inspect converters.** Check whether an appropriate converter is registered and accepts the exact types.
7. **Read the cause chain.** Locate the specific exception thrown by Spring conversion or a custom converter.
8. **Reproduce in a test.** Use the exact root object, expression, context, and failing data.
9. **Fix at the right boundary.** Normalize data, add a converter, or fix the target type per contract.
10. **Regression test.** Cover valid data, malformed data, null, and boundary types.

Do not fix errors by forcing every value to String or returning null when conversion fails. Doing so can hide invalid data and allow business logic to proceed with invalid values.

## 14. Best Practices

- Clearly define source type and target type for every important conversion.
- Use the application's shared ConversionService when consistent conversion rules are needed.
- Attach StandardTypeConverter with the right ConversionService in EvaluationContext.
- Register custom Converters for business types with custom rules.
- Keep converters small, deterministic, and side-effect-free.
- Validate data before evaluating expressions if formats carry business rules.
- Do not rely on exception wording to drive application control flow.
- Log message code, position, data types, and cause chain when diagnosing.
- Do not log sensitive values solely to trace conversion failures.
- Test conversions independently and inside actual expressions.
- Use the same EvaluationContext factory and ConversionService configuration in both tests and production.
- Distinguish parse errors, evaluation errors, and internal converter errors.

## 15. Review Checklist

Before putting expressions involving conversion into production, verify:

- [ ] Operations that can trigger conversion have been identified.
- [ ] Source and target types match the data contract.
- [ ] TypeConverter in the context is configured as expected.
- [ ] Required ConversionServices are registered.
- [ ] Custom Converters handle valid, null, and malformed data.
- [ ] Collection conversions have appropriate generic type information.
- [ ] Parse errors are separated from conversion/evaluation errors.
- [ ] Exception message codes, positions, and cause chains can be logged.
- [ ] Logs do not expose sensitive data.
- [ ] Tests cover success, failure, and boundary data.
- [ ] Tests use conversion configuration matching production.
- [ ] Conversion errors are not masked by unintended defaults or nulls.

## Conclusion

Conversion errors in SpEL occur when an operation requires a data type different from the current value's type and TypeConverter cannot perform the conversion. EvaluationContext supplies the TypeConverter; StandardTypeConverter can integrate with Spring's ConversionService to use default or application-registered converters. When diagnosing, identify source type, target type, expression position, conversion configuration, and root exception. Test converters both independently and inside real expressions, while keeping input types explicit and avoiding masking errors by returning null arbitrarily.