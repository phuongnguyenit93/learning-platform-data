# Property, Method, Constructor, and Conversion Errors

## Objectives

When SpEL evaluates an expression, it must access properties, invoke methods, instantiate objects, or convert data types as required by the operation. An expression can parse successfully yet still fail at runtime if a property cannot be read/written, a method or constructor cannot be resolved, arguments have wrong types, or a converter does not support the required type pair.

Effective diagnostics require identifying the exact failing operation, the runtime object and types at that moment, the `EvaluationContext` configuration, the expression position, and the root exception. You should not rely solely on the final message line or change multiple parts of the expression simultaneously.

After this lesson, you can:

- Distinguish parse errors from evaluation errors.
- Diagnose missing, unreadable, or unwritable properties.
- Handle method resolution and overload errors.
- Identify causes of failed constructor invocations.
- Diagnose `TypeConverter` and `ConversionService` errors.
- Read exception message codes, positions, and cause chains.
- Produce useful logs without exposing sensitive data.
- Write tests reproducing each error type in the exact `EvaluationContext`.

## 1. Identify the Phase Where the Error Occurs

SpEL has two main phases:

1. **Parse:** the parser reads the string and creates an `Expression`.
2. **Evaluate:** the expression is executed with a root object, variables, and an `EvaluationContext`.

Parse errors are usually caused by invalid syntax: missing parentheses/brackets, unclosed string literals, misplaced operators, or incomplete expression blocks.

Evaluation errors appear after a successful parse. Causes may include:

- Property does not exist or cannot be read/written.
- Method is not found or has no matching overload.
- Constructor is not found.
- Arguments are incompatible with parameters.
- `TypeConverter` cannot convert the value to the target type.
- Method, getter, setter, or constructor throws an exception.
- Root object, variable, or collection element is `null` at an unprotected position.

Example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("price * quantity");
~~~

The line above only parses the expression. Errors may only appear when calling `getValue()`:

~~~java
BigDecimal total =
    expression.getValue(context, BigDecimal.class);
~~~

If the root object lacks the `price` or `quantity` properties, or their data types do not support multiplication, the error occurs during the evaluation phase.

Clearly record whether the error occurred in `parseExpression()`, `getValue()`, or `setValue()`. This is the first step in choosing the right investigation path.

## 2. Common Exception Types

Important exceptions in the SpEL flow include:

| Exception | Role |
|---|---|
| **ParseException** | Expression syntax parsing error |
| **SpelParseException** | SpEL-specific parse error information |
| **EvaluationException** | General error during expression evaluation |
| **SpelEvaluationException** | SpEL evaluation error, often with message code and position |
| **AccessException** | Error from a `PropertyAccessor` or custom accessor |
| **ConversionException** | Error during type conversion |
| **ConversionFailedException** | `ConversionService` could not perform the required conversion |
| **ConverterNotFoundException** | No converter exists for the source type and target type |
| **ClassCastException** | A value is used as an incompatible type |
| **NullPointerException** | Code accesses a `null` object, typically inside a method or accessor |

The actual exception depends on the operation, resolver, accessor, converter, and Spring version. Some underlying errors may be wrapped by SpEL in `SpelEvaluationException`, so inspect the cause chain as well.

Do not assume that every property error has the same exception class or that every conversion error directly throws `ConverterNotFoundException`. Record the actual exception and the deepest meaningful cause.

## 3. Property Read Errors

Property expressions can use dot notation or property syntax appropriate for the target:

~~~text
#root.customer.name
#root.address.postalCode
~~~

Property read errors typically occur when:

- The property or field does not exist on the target.
- The property name is misspelled or has wrong casing.
- The getter is missing or inaccessible.
- `PropertyAccessor` does not support the target type.
- The getter throws an exception.
- The target or an intermediate object is `null`.
- `EvaluationContext` restricts property access permissions.

Example:

~~~java
Expression expression =
    parser.parseExpression("customer.displayName");

String name = expression.getValue(context, String.class);
~~~

If the root object does not have `customer`, or `customer` does not expose a readable `displayName` property, evaluation fails.

### How to Diagnose

1. Check the runtime type of the root object.
2. Check the property path level by level, starting from the first level.
3. Verify the getter or field is accessible according to the `PropertyAccessor` in use.
4. Check whether any intermediate object is `null`.
5. Check whether `EvaluationContext` has a custom `PropertyAccessor` or read access restrictions.
6. If the getter throws an exception, inspect the cause to find the error inside the getter.

Do not assume a Java property is always readable just because a field exists. SpEL accesses through `PropertyAccessor`; readability depends on the accessor and context configuration.

## 4. Property Write Errors

Property writes typically occur in `setValue()` or assignments inside an expression:

~~~java
Expression expression =
    parser.parseExpression("retryCount");

expression.setValue(context, 5);
~~~

Common causes:

- The property has no setter or no supported write mechanism.
- The setter is inaccessible.
- The property is read-only in `SimpleEvaluationContext`.
- The new value's type cannot be converted to the property type.
- The setter throws an exception due to validation or business rules.
- The target or an intermediate object is `null`.
- A custom `PropertyAccessor` rejects the write operation.

Example of a property with a setter:

~~~java
public class RetrySettings {
    private Integer retryCount;

    public Integer getRetryCount() {
        return retryCount;
    }

    public void setRetryCount(Integer retryCount) {
        this.retryCount = retryCount;
    }
}
~~~

Assignment expression:

~~~text
retryCount = 3
~~~

If the context is configured as read-only, or the property lacks a setter while the accessor does not support direct field writes, the operation will fail.

### Distinguishing Write Errors from Conversion Errors

If a property has a setter accepting `Integer` while the expression provides an invalid `String`, the error may lie in conversion before the setter is called.

If conversion succeeds but the setter rejects the value, the error lies in the setter logic.

To distinguish them, check the source type, property type, converter used, and cause chain. You can test the setter directly with the converted value to determine whether the setter is the source of the error.

## 5. Method Resolution Errors

SpEL invokes methods on an object using the syntax:

~~~text
#root.customer.calculateDiscount(#amount)
~~~

Method resolution can fail when:

- The method name is wrong or does not exist.
- The number of arguments does not match.
- Argument types are incompatible with parameters.
- No matching overload exists.
- Multiple overloads create ambiguity given the data and conversion.
- The method is inaccessible through the configured resolver.
- `EvaluationContext` does not permit the required type of method access.
- The target object is `null`.
- The method is found but throws an exception during execution.

Java example:

~~~java
public class Customer {
    public BigDecimal calculateDiscount(BigDecimal amount) {
        return amount.multiply(new BigDecimal("0.10"));
    }
}
~~~

Expression:

~~~text
#root.calculateDiscount(#amount)
~~~

Ensure the `amount` variable has a type compatible with the `BigDecimal` parameter.

### Checking Overloads

Suppose a class has the following overloads:

~~~java
public String format(Integer value) { ... }

public String format(BigDecimal value) { ... }
~~~

If the expression passes a value of a different type or `null`, overload selection may not behave as expected. Check the runtime types of arguments and avoid relying on ambiguous conversions.

When stability is needed, normalize types before calling the method or provide an intermediate Java method with a single, unambiguous signature.

### Method Is Called but Throws an Exception

Successful method resolution does not mean successful method execution. If the method throws `IllegalArgumentException`, `NullPointerException`, or a business exception, SpEL may report an evaluation error with the corresponding cause.

Read the original exception to distinguish a method not being found from an error originating inside the method.

## 6. Constructor Invocation Errors

Constructor expressions use the syntax:

~~~text
new fully.qualified.ClassName(arguments)
~~~

Example:

~~~text
new java.math.BigDecimal('125.50')
~~~

Constructor invocation can fail because:

- The class name is wrong or the class is not on the runtime classpath.
- `TypeLocator` or the class loader cannot find the class.
- No constructor exists for the number of passed arguments.
- Argument types are incompatible.
- No suitable conversion exists for constructor parameters.
- The constructor is inaccessible.
- The constructor is invoked but throws an exception.
- `EvaluationContext` does not support constructor invocation.

Example of a class requiring two arguments:

~~~java
public class Range {
    public Range(int minimum, int maximum) {
        // Validate and initialize.
    }
}
~~~

Expression:

~~~text
new com.example.Range(10, 20)
~~~

If only one argument is passed or a value is passed that cannot be converted to the parameter type, SpEL cannot invoke the matching constructor.

### How to Diagnose

1. Verify the fully qualified class name.
2. Check that the class is on the runtime classpath and uses the right class loader.
3. Review the public constructors and parameter signatures.
4. Compare the count, types, and actual values of the arguments.
5. Check `TypeConverter` if conversion is needed.
6. Read the cause if the constructor was invoked and threw an exception.

If the object needs dependency injection, proxies, or Spring lifecycle management, let the container create the object. Constructor expressions only create plain Java instances; they do not automatically create Spring-managed beans.

## 7. Conversion Errors

Conversion can occur when:

- Assigning a value to a property.
- Passing arguments to a method.
- Passing arguments to a constructor.
- Requesting a result type in `getValue(context, targetType)`.
- Converting elements in a collection or `Map`.

Example requesting conversion from `String` to `Integer`:

~~~java
Expression expression =
    parser.parseExpression("'not-a-number'");

Integer value =
    expression.getValue(context, Integer.class);
~~~

The expression parses successfully, but conversion can fail when `getValue` requests an `Integer`.

Common causes:

- No converter exists for the source type and target type.
- The data is malformed.
- The value is outside the valid range of the target type.
- A custom converter throws an exception.
- `EvaluationContext` uses a different `ConversionService` than the application expects.
- A generic collection lacks target type information or an element cannot be converted.

### TypeConverter and ConversionService

`EvaluationContext` provides a `TypeConverter` to SpEL. `StandardTypeConverter` typically integrates with Spring's `ConversionService`.

You can attach a specific `ConversionService`:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext(rootObject);

context.setTypeConverter(
    new StandardTypeConverter(applicationConversionService)
);
~~~

If a converter is registered in another `ConversionService`, the expression will not automatically use that converter. Verify that the exact instance is attached to the context performing evaluation.

Do not use conversion to mask invalid data. If input must follow a specific business format, validate before evaluation or write a converter with a clear contract.

## 8. Distinguishing Resolution Errors from Execution Errors

An operation can fail at multiple points:

| Phase | Error Example |
|---|---|
| Parse | Invalid method call syntax, missing parenthesis |
| Resolve property | Property not found or no read permission |
| Resolve method | Method/overload not found |
| Resolve constructor | Class or matching constructor not found |
| Convert argument | Cannot convert value to parameter type |
| Execute getter/method/constructor | Java code inside throws an exception |
| Convert result | Cannot convert result to requested target type |

For example, the expression:

~~~text
#root.customer.calculateDiscount(#amount)
~~~

can fail because `customer` does not exist, `customer` is `null`, the method is missing, `amount` has the wrong type, conversion fails, or `calculateDiscount` itself throws an exception.

Find the first failing step instead of just looking at the method name in the expression and concluding it is a method resolution error.

## 9. Reading SpelEvaluationException

`SpelEvaluationException` is an important source of information when SpEL evaluation fails. Depending on the error type and Spring version, the exception may provide:

- Message code to classify the error.
- Position in the expression.
- Values used to construct the message.
- Cause chain containing the original exception.

Example of catching the error:

~~~java
try {
    return expression.getValue(context, Boolean.class);
}
catch (SpelEvaluationException ex) {
    logger.warn(
        "SpEL evaluation failed: code={}, position={}",
        ex.getMessageCode(),
        ex.getPosition()
    );
    throw ex;
}
~~~

Specific method names and accessor details must be checked against the Spring version in use. You can inspect the cause via `getCause()` or traverse the cause chain.

Message codes are more useful than comparing the full message sentence. Wording can change between versions, whereas classification codes are generally more suitable for diagnostics and tests.

Do not catch every `RuntimeException` and return `null` or `false`. Doing so can turn configuration, data, or programming errors into seemingly valid business results.

## 10. Designing Logging and Diagnostics

A good log must help reproduce the error without exposing sensitive data.

Recommended fields to record:

- Rule/expression ID or name.
- Expression version if content can change.
- Error phase: parse, property, method, constructor, or conversion.
- Message code and error position if available.
- Runtime type of the root object.
- Source and target types when conversion fails.
- Related operation/property/method name if available.
- Original exception class and cause chain.
- Correlation ID or request ID.
- `EvaluationContext` type and relevant converter/accessor configuration.

Avoid logging:

- The entire object graph.
- Passwords, tokens, secrets, or credentials.
- Unnecessary personal data.
- Full variable values if they may contain sensitive data.
- User-entered expressions if the expression might contain private data.

You can log data types, reference IDs, variable names, or sanitized parts instead of raw values.

## 11. Handling by Error Type

| Error Type | Check First | How to Handle |
|---|---|---|
| Property unreadable | Target type, property path, getter, accessor | Fix name/path or configure an appropriate PropertyAccessor |
| Property unwritable | Setter, read-only context, target type | Provide setter/writable accessor or use a context with proper permissions |
| Method not found | Name, argument count, and argument types | Fix the call or create a wrapper method with a clear signature |
| Ambiguous method overload | Runtime types of arguments | Normalize types and reduce overload ambiguity |
| Method throws exception | Cause inside the method | Fix data or method logic; preserve business errors |
| Constructor not found | Class, class loader, constructor signature | Fix class name and arguments |
| Constructor throws exception | Cause from constructor | Check invariants and initialization data |
| Conversion fails | Source/target types, ConversionService | Validate data or register the right converter |
| Null in property path | Intermediate object | Use safe navigation when null is valid or validate input |
| Fails only in production | Context/configuration differs from tests | Share a common context factory and conversion configuration |

Do not fix an expression by adding safe navigation if the actual error is a non-existent property or missing method. Safe navigation only protects against a `null` target at the applied position; it does not replace a missing property, method, or converter.

## 12. Testing Property, Method, Constructor, and Conversion

Each operation type needs separate tests to pinpoint the exact failure point.

### Property Read and Write

~~~java
@Test
void readsAndWritesProperty() {
    ExpressionParser parser = new SpelExpressionParser();
    StandardEvaluationContext context =
        new StandardEvaluationContext(new RetrySettings());

    Expression expression = parser.parseExpression("retryCount");
    expression.setValue(context, 3);

    assertEquals(
        Integer.valueOf(3),
        expression.getValue(context, Integer.class)
    );
}
~~~

Add tests for missing properties, read-only contexts, setters throwing exceptions, and unconvertible values.

### Method Invocation

~~~java
@Test
void invokesMethodWithCompatibleArgument() {
    ExpressionParser parser = new SpelExpressionParser();
    StandardEvaluationContext context =
        new StandardEvaluationContext(new Customer());

    context.setVariable("amount", new BigDecimal("100"));

    Expression expression =
        parser.parseExpression("calculateDiscount(#amount)");

    assertNotNull(expression.getValue(context));
}
~~~

Add tests for missing methods, overloads, `null` arguments, and exceptions inside methods.

### Constructor Invocation

~~~java
@Test
void createsValueWithConstructorExpression() {
    ExpressionParser parser = new SpelExpressionParser();
    StandardEvaluationContext context =
        new StandardEvaluationContext();

    Expression expression = parser.parseExpression(
        "new java.math.BigDecimal('10.25')"
    );

    assertEquals(
        new BigDecimal("10.25"),
        expression.getValue(context, BigDecimal.class)
    );
}
~~~

Add tests for missing classes, wrong constructor signatures, and constructors throwing exceptions.

### Conversion

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

Add tests for malformed strings, custom converters, different target types, and contexts using a separate `ConversionService`.

## 13. Systematic Error Investigation Workflow

When an expression fails in a real environment:

1. **Record the expression and error phase.** Determine whether `parseExpression()`, `getValue()`, or `setValue()` threw the exception.
2. **Retrieve the message code and position.** Use the information from `SpelEvaluationException` if available.
3. **Identify the target.** Record the runtime types of the root object and the current object at the failing operation.
4. **Narrow down the expression.** Test each property path or method call independently with representative data.
5. **Check access.** Confirm that `PropertyAccessor`, `MethodResolver`, or `ConstructorResolver` supports the operation.
6. **Check the signature.** Compare the types and count of arguments against the method/constructor.
7. **Check conversion.** Identify the source type, target type, and actual `ConversionService`.
8. **Read the cause chain.** Find the root error from the getter, setter, method, constructor, or converter.
9. **Reproduce with a test.** Use the exact `Expression`, `EvaluationContext`, root object, and converter configuration.
10. **Fix at the right layer.** Fix the data, model, accessor, resolver, converter, or expression according to the root cause.
11. **Add regression tests.** Cover success cases, failure cases, and boundary data.

Do not change the expression, model, and `ConversionService` at the same time before having a reproducing test. Isolating each layer helps determine which change actually resolves the root cause.

## 14. Best Practices

- Distinguish parse errors from evaluation errors before fixing.
- Check the root type and property path level by level.
- Distinguish unreadable properties from unwritable properties.
- Check method signatures and overloads rather than just the method name.
- Verify the class, constructor, and class loader when using `new`.
- Use the application's shared `ConversionService` if conversion rules must stay consistent.
- Validate inputs before evaluation when data follows a business format.
- Read the message code, position, and cause chain.
- Do not rely on the full message text to control logic.
- Do not swallow exceptions and return `null`/`false` if that is not a valid business result.
- Log sufficient diagnostic details without logging secrets or entire object graphs.
- Use the same `EvaluationContext` factory in tests and production.
- Write dedicated tests for properties, methods, constructors, and conversions.
- Move complex logic or logic with side effects to clearly named Java methods.

## 15. Review Checklist

Before putting an expression into use, verify:

- [ ] Expression parses successfully.
- [ ] Operations that can fail at runtime are clearly identified.
- [ ] Root object and runtime types are correct.
- [ ] Property paths exist and are readable/writable per context.
- [ ] Nulls at each level are handled according to contract.
- [ ] Method names, argument counts, and argument types match.
- [ ] Overloads are not unintentionally ambiguous.
- [ ] Constructors and classes are resolved properly.
- [ ] `ConversionService` and `TypeConverter` are properly configured.
- [ ] Custom converters have tests for valid and invalid inputs.
- [ ] Exceptions are categorized by message code/cause, not just message text.
- [ ] Logs do not expose sensitive data.
- [ ] Tests exist for success, failure, and boundary values.
- [ ] Tests use the same `EvaluationContext` configuration as production.

## Conclusion

Property, method, constructor, and conversion errors in SpEL typically appear during the evaluation phase, even when the expression has parsed successfully. Identify the failing operation, the runtime types of the target and arguments, accessor/resolver permissions, `TypeConverter`/`ConversionService`, and the root exception. `SpelEvaluationException` provides helpful message codes and positions; the cause chain reveals deeper errors from getters, setters, methods, constructors, or converters. Verify each layer with reproducing tests, log enough for diagnostics without exposing sensitive data, and fix the actual root cause instead of masking errors with `null` or default values.