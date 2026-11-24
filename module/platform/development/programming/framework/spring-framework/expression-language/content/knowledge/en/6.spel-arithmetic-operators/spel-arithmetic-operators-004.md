# Type Conversion When Two Operands Differ in SpEL

In Spring Expression Language (SpEL), the two operands of an arithmetic operation can have different Java types, such as Integer and Long, Integer and Double, or Integer and BigDecimal. The result depends on the runtime types of the operands and how SpEL handles the corresponding operator. It is important to distinguish **numeric promotion during computation** from **type conversion via TypeConverter** of EvaluationContext: these two mechanisms are related but not synonymous.

## 1. Runtime Types of Operands Affect the Result

Values in an expression can come from literals, the root object, properties, or variables. When an operator is evaluated, SpEL receives the runtime values of the two operands. Example:

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setVariable("count", Integer.valueOf(10));
    context.setVariable("total", Long.valueOf(20));

    ExpressionParser parser = new SpelExpressionParser();
    Object result = parser.parseExpression("#count + #total")
            .getValue(context);

Here `#count` is Integer and `#total` is Long. SpEL processes addition on the two numeric values and the result has a numeric type appropriate for the operation. Because a Long is involved, the result of this addition is Long.

What matters is that SpEL evaluates the actual values passed into the context. A variable declared in Java as Number can still hold an Integer, Long, Double, BigDecimal, or another numeric type; that runtime type affects how the operator behaves.

## 2. Numeric Promotion

When both operands are Number, SpEL's arithmetic operators handle them according to the corresponding arithmetic rules and choose a result type suited to the operand types. Some common cases:

| Left Operand | Right Operand | Typical Result |
|---|---|---|
| Integer | Integer | Integer |
| Integer | Long | Long |
| Integer | Float | Float |
| Integer | Double | Double |
| Integer | BigInteger | BigInteger |
| Integer | BigDecimal | BigDecimal |

Example:

    context.setVariable("integerValue", 10);
    context.setVariable("longValue", 20L);
    context.setVariable("doubleValue", 2.5d);

    Object longResult = parser.parseExpression(
            "#integerValue + #longValue"
    ).getValue(context);

    Object doubleResult = parser.parseExpression(
            "#integerValue + #doubleValue"
    ).getValue(context);

The first addition combines Integer and Long, so the result is Long. The second addition combines Integer and Double, so the result is Double.

Do not infer types just by looking at how literals are written. For example, `10` is an integer literal, `10L` is Long, `10.0` is Double, and `10.0F` is Float. When values come from variables or properties, check the runtime type instead of guessing from variable names.

Type promotion does not make a numeric type infinitely precise. If an operand is Float or Double, the result is still subject to floating-point limitations. If decimal precision must be preserved, use BigDecimal for both operands.

## 3. Division and Result Types

Operand types are especially important for division. When dividing two integers, the fractional part may be discarded under integer division:

    parser.parseExpression("1 / 2").getValue();       // 0
    parser.parseExpression("1.0 / 2").getValue();     // 0.5

In the first expression, both operands are integers, so division gives an integer result. In the second expression, one operand is Double, so the result has a fractional part.

If business logic requires an exact result, do not try to fix the type after division has already happened. Convert or create the operands in the appropriate type before performing the operation.

With BigDecimal, create both numerator and denominator as BigDecimal before dividing. BigDecimal division may not have a finite decimal representation, such as 1 divided by 3; in that case, specify scale and rounding mode in Java logic or call an appropriate method to control the result.

## 4. Distinguishing Numeric Promotion from TypeConverter

EvaluationContext provides a TypeConverter for SpEL to perform type conversions in contexts requiring a target type, for example:

- Assigning a value to a property of a specific type.
- Converting arguments when calling a method or constructor.
- Converting the result to a requested type via the `getValue(..., DesiredType.class)` overload.

Example requesting the result converted to Double:

    Double value = parser.parseExpression("#count + #total")
            .getValue(context, Double.class);

This is a result conversion after the expression has already been evaluated. It does not change the types of the operands during the addition and cannot restore a fractional part that was lost in an integer division.

For example, converting the result of `1 / 2` to Double still yields a value equivalent to 0.0, because the division already produced an integer result of 0 before conversion. To get 0.5, floating-point operands must be used from the start.

Therefore, when two operands have different types, determine the goal first:

1. If both are Number, choose appropriate numeric types and let the operation execute according to SpEL's arithmetic rules.
2. If a specific target type is needed for a property, method, or result, use EvaluationContext's conversion mechanism.
3. If an operand is a string containing digits, convert it explicitly before computing; do not assume an arithmetic operator will automatically parse a string into a Number.

## 5. When an Operand Is a String

String is not Number. With the addition operator, if a string operand is present, SpEL may perform string concatenation instead of numeric addition:

    parser.parseExpression("'10' + 2").getValue(); // "102"

The result is the string `"102"`, not the number 12. This is an important difference when data comes from forms, configuration files, or external APIs.

If a string represents a number, convert it before using it in calculations. For integers:

    context.setVariable("rawCount", "10");

    Object count = parser.parseExpression(
            "T(java.lang.Integer).parseInt(#rawCount)"
    ).getValue(context);

For decimals requiring precision:

    context.setVariable("rawAmount", "123.4500");

    Object amount = parser.parseExpression(
            "new java.math.BigDecimal(#rawAmount)"
    ).getValue(context);

Then use the converted values as operands. When data comes from the application, a clearer approach is to parse and validate in Java and then pass normalized Numbers into the context.

If two operands are objects not belonging to Number or String, the operation may require a custom OperatorOverloader. OperatorOverloader defines how to perform operators on custom types; it is not a mechanism for automatically converting strings to numbers.

## 6. Combining BigInteger and BigDecimal

BigInteger is suitable for integers exceeding the Long range or needing to retain all digits exactly. BigDecimal is suitable for decimal calculations requiring precision, such as currency or rates.

BigDecimal should be constructed from the original decimal string:

    BigDecimal price = new BigDecimal("19.99");
    BigDecimal tax = new BigDecimal("1.50");

    context.setVariable("price", price);
    context.setVariable("tax", tax);

    BigDecimal total = parser.parseExpression("#price + #tax")
            .getValue(context, BigDecimal.class);

Do not create a BigDecimal from a previously computed Double if absolute precision is needed. In that case, floating-point error may have already occurred before converting to BigDecimal.

With two operands of different types, especially when mixing BigInteger, BigDecimal, and floating point, normalize both to the desired type before computing. This clarifies the application's rounding policy, precision, and result type.

## 7. Checking Result Types When Debugging

When an expression produces an unexpected result, print both the value and the runtime type:

    Object result = parser.parseExpression(
            "#left + #right"
    ).getValue(context);

    System.out.println(result);
    System.out.println(result.getClass().getName());

Each operand can be inspected directly in Java before being placed into the context:

    System.out.println(context.lookupVariable("left").getClass());
    System.out.println(context.lookupVariable("right").getClass());

This helps detect cases where a value that should be Long was created as Integer, or a decimal number was read as a String. For complex expressions, split the calculation into intermediate variables to observe the type after each step.

When using `getValue(context, TargetType.class)`, remember that TypeConverter is converting the final result to the requested type. If you need to determine the actual type produced by the operator, call `getValue(context)` and then check `getClass()`.

## 8. Customizing Type Conversion

If an application needs conversion between custom data types, a TypeConverter can be configured on StandardEvaluationContext. StandardTypeConverter can use Spring's ConversionService to apply registered Converters.

For example, create a converter at the application layer and provide it to the context:

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setTypeConverter(
            new StandardTypeConverter(conversionService)
    );

TypeConverter is useful when SpEL needs to convert a value to a target type during property assignment or method call resolution. However, normalize operands before the operation if you want exact control over arithmetic types. Do not rely on a custom converter to replace all operator arithmetic rules.

If expressions come from users, provide only necessary converters and restrict the types that can be converted. An overly broad converter can turn invalid input data into unexpectedly meaningful values.

## 9. Common Errors

- **String concatenation instead of numeric addition:** check runtime types; parse Strings into Numbers before computing.
- **Losing the fractional part on division:** use Double or BigDecimal for operands before dividing.
- **Integer overflow:** use Long or BigInteger if values exceed the Integer/Long range.
- **Decimal precision errors:** use BigDecimal created from strings or exact data sources.
- **Converting types too late:** converting the result after an operation cannot restore lost precision.
- **Confusing TypeConverter with numeric promotion:** TypeConverter serves conversion to target types; arithmetic operators have their own Number handling rules.
- **Not checking the result type:** use `getValue(context)` and `getClass()` when needing to determine the actual type of the result.

## 10. Key Takeaways

When two operands have different types, first determine whether they are Number. With two numeric operands, SpEL applies arithmetic handling and result typing based on runtime types. With String, especially with the addition operator, string concatenation can occur instead of numeric addition. TypeConverter handles conversions needing a target type such as property assignment, method calls, or retrieving results in a requested type; it does not replace choosing appropriate operand types before the calculation. For very large integers, use BigInteger; for decimals requiring precision, use BigDecimal and normalize both operands before performing the operation.
