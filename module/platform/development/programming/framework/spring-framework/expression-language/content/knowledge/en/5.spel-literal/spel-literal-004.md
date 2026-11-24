# Exponential and Large Value Literals in Spring Expression Language

Spring Expression Language (SpEL) supports integer and real number literals directly in expressions. For numbers with large values or written in scientific notation, it is necessary to understand how SpEL classifies literals, how suffixes determine numeric types, and the precision limits of the underlying Java types. An expression can be parsed successfully yet still yield an unsuitable result if too small a numeric type is chosen or if floating point is used for data requiring absolute decimal precision.

## 1. Numeric Literals in SpEL

A literal is a value written directly in the expression string. Common groups:

| Group | Example | Meaning |
|---|---|---|
| Integer | `42`, `-7` | Integer value; negative sign is applied via the unary operator |
| Long integer | `2147483648L` | Uses `L` or `l` suffix to specify Long |
| Decimal real number | `12.5` | Real number literal; defaults to Double |
| Scientific notation | `1.25e3`, `4.2E-6` | Represents a real number using a significand and an exponent |
| Float real number | `1.25e3F` | Suffix `F` or `f` specifies Float |
| Double real number | `1.25e3D` | Suffix `D` or `d` specifies Double |

SpEL uses numeric syntax based on Java's numeric types. The decimal separator in an expression is a dot, regardless of the locale of the machine running the application. Do not use a comma in place of a decimal point.

## 2. Scientific Notation

Scientific notation represents a number as a significand multiplied by ten raised to an exponent:

`a e n` is equivalent to `a × 10^n`

In SpEL, either `e` or `E` can be used. The exponent can have a `+` or `-` sign.

| Literal | Mathematical Value | Interpretation |
|---|---:|---|
| `1.25e3` | 1,250 | 1.25 × 10³ |
| `4.2E-3` | 0.0042 | 4.2 × 10⁻³ |
| `6.02e23` | 602,000,000,000,000,000,000,000 | 6.02 × 10²³ |
| `7e+8` | 700,000,000 | 7 × 10⁸ |
| `9.5e-7` | 0.00000095 | 9.5 × 10⁻⁷ |

Example:

    ExpressionParser parser = new SpelExpressionParser();

    Object distance = parser.parseExpression("1.25e3").getValue();
    Object ratio = parser.parseExpression("4.2E-3").getValue();

For real literals without a suffix, SpEL defaults to the Double type. Therefore `1.25e3` gives a Double value equivalent to 1250.0, even though the mathematical result is an integer. Scientific notation still represents a real number literal; it does not automatically turn the value into an Integer or Long.

The sign in the exponent only determines the shift of the decimal point. For example, `1e6` is one million, while `1e-6` is one millionth. A negative sign in front of the entire expression, as in `-1.25e3`, is handled by the unary minus operator.

Scientific notation can be combined with numeric type suffixes:

    Object asFloat = parser.parseExpression("1.25e3F").getValue();
    Object asDouble = parser.parseExpression("1.25e3D").getValue();

Use a suffix when you want the data type to be clearly shown in the expression or when you need to pass the value to an API with specific type requirements.

## 3. Suffixes and Numeric Types

Suffixes help specify the numeric type that a literal represents:

| Suffix | Java Type | Used For |
|---|---|---|
| No suffix on integer | Integer according to SpEL integer literal rules | Integers within the appropriate type range |
| `L` or `l` | Long | Integers needing a 64-bit range |
| No suffix on real number | Double | Ordinary real numbers |
| `F` or `f` | Float | When an API or data structure requires Float |
| `D` or `d` | Double | When wanting to explicitly state Double type |

Example with an integer larger than the Integer range:

    Object count = parser.parseExpression("2147483648L").getValue();

The `L` suffix indicates that the literal should be interpreted as Long. For large integers, specify the target type explicitly instead of relying on implicit conversion in operations or when passing parameters.

Do not confuse type suffixes with exponents. In `3.5e8F`, `e8` is the exponent part and `F` is the suffix indicating the Float type.

## 4. Limits When Handling Large Values

Each numeric type has its own representation range and precision. Choosing the right type matters more than merely writing more digits into the literal.

| Type | Characteristics | Notes |
|---|---|---|
| Integer | 32-bit signed integer | Range from -2,147,483,648 to 2,147,483,647 |
| Long | 64-bit signed integer | Range from -9,223,372,036,854,775,808 to 9,223,372,036,854,775,807 |
| Float | 32-bit floating point | Precision of about 6–7 significant decimal digits |
| Double | 64-bit floating point | Precision of about 15–17 significant decimal digits |

### 4.1. Integers Exceeding the Integer Range

If a value exceeds the Integer range, use Long with the `L` suffix:

    2147483648L
    9000000000000L

Long still has limits. If a value exceeds the Long range, an ordinary integer literal is not a suitable representation. You can use BigInteger via a variable passed into the context or instantiate an object if the context allows constructor invocation.

### 4.2. Very Large or Very Small Real Numbers

Double represents a wide range of values, but has a finite number of significant digits. When the exponent is too large, the value may exceed the finite range and become infinity according to floating-point rules. When the exponent is too negative, the value may be rounded down to 0 or lose part of its precision due to underflow.

Example:

    1.0e300
    1.0e-300

The expressions above are within Double's finite representation range, but that does not mean every value with many digits is stored accurately. For Float, the representation range and precision are even smaller.

### 4.3. Floating Point Is Not Suitable for All Decimal Calculations

Float and Double store numbers in binary form. Many decimal fractions, such as 0.1, do not have a finite binary representation. Therefore calculations may produce approximate rather than exact results.

For example, do not use Double as a storage type for money if business logic requires addition, subtraction, and comparison exact to every decimal digit. Increasing the number of digits in the literal or switching to scientific notation does not solve this limitation.

For large integers that need to preserve every digit, use `java.math.BigInteger`. For decimal numbers requiring precision, use `java.math.BigDecimal`. Both types can be passed into SpEL via variables in EvaluationContext or created with a constructor when the context allows it.

## 5. Using BigInteger and BigDecimal in Expressions

StandardEvaluationContext allows constructor invocation under the default configuration. You can create a BigInteger from an integer string:

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    ExpressionParser parser = new SpelExpressionParser();

    Object largeInteger = parser.parseExpression(
            "new java.math.BigInteger('123456789012345678901234567890')"
    ).getValue(context);

For decimal numbers needing to stay exact, create a BigDecimal from a decimal string:

    Object preciseDecimal = parser.parseExpression(
            "new java.math.BigDecimal('1234567890.12345678901234567890')"
    ).getValue(context);

Pass the string directly into the BigDecimal constructor. If you create a BigDecimal from a Double value that was already rounded earlier, the original precision is already lost and BigDecimal cannot recover those digits.

Another approach is to create the value in Java and pass it into the context as a variable:

    BigDecimal amount =
            new BigDecimal("1234567890.12345678901234567890");

    context.setVariable("amount", amount);

    BigDecimal value = parser.parseExpression("#amount")
            .getValue(context, BigDecimal.class);

Passing via a variable is useful when data comes from a database, API, or business logic. It also helps limit the expression's permissions: the application decides which values are provided to the context.

Note: SimpleEvaluationContext does not support constructor invocation. If using this restricted context, create BigInteger or BigDecimal in Java and pass them in via variables or the root object.

## 6. Reading and Checking the Result Type

When inspecting literals, observe both the value and the runtime type. Two literals with the same mathematical value can still have different types:

    Object a = parser.parseExpression("1.25e3").getValue();
    Object b = parser.parseExpression("1.25e3F").getValue();
    Object c = parser.parseExpression("1250L").getValue();

    System.out.println(a.getClass()); // Double
    System.out.println(b.getClass()); // Float
    System.out.println(c.getClass()); // Long

When calling `getValue(..., DesiredType.class)`, SpEL can use the context's type conversion mechanism to convert the result to the target type. This is a conversion when retrieving the result; it does not give the original literal higher precision or expand the representation range of the source type.

If the expression is used as an argument to a method, constructor, or property, check the target parameter type and corresponding conversion rules. Do not assume that a Double literal is always passed as a Long or vice versa without conversion.

## 7. Common Mistakes and How to Avoid Them

- **Using a comma as a decimal separator:** SpEL uses a dot in numeric literals. Write `12.5`, not `12,5`.
- **Confusing exponents with suffixes:** `e-4` is the exponent part; `F` or `D` is the real number type suffix.
- **Assuming `1e3` is an integer:** This is a real number literal and defaults to Double.
- **Omitting the Long suffix on large integers:** Use `L` to explicitly show the intent to use Long.
- **Using Double for data needing decimal precision:** Use BigDecimal, initialized from a string or from exact data.
- **Using Float for values needing many significant digits:** Float only has precision of about 6–7 digits; prefer Double or BigDecimal depending on requirements.
- **Assuming BigDecimal fixes already inaccurate Double data:** Create BigDecimal from a string or original decimal data.
- **Forgetting EvaluationContext limits:** SimpleEvaluationContext does not allow creating objects with `new`; prepare the objects in Java and pass them via variables.

## 8. Key Takeaways

Scientific notation uses `e` or `E` to represent exponents and is very useful when writing very large or very small numbers. Real literals without a suffix default to Double; `F` selects Float and `D` selects Double. For integers larger than the Integer range, use the `L` suffix to specify Long. Float and Double have limits on representation range and precision; when arbitrary-size integers or exact decimals are needed, use BigInteger or BigDecimal and pass values into EvaluationContext intentionally.
