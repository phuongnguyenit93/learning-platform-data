# Precision Limits and Overflow Risk

## Objectives

After this lesson, you can recognize arithmetic risks when using Spring Expression Language (SpEL): floating-point representation errors, overflow of bounded integers, the difference between BigDecimal precision and scale, as well as how division requires explicit rounding rules. You will know how to pass BigInteger and BigDecimal into expressions, choose appropriate operations, and test boundary values before putting expressions into an application.

## 1. Why Can Arithmetic Expressions Produce Unexpected Results?

SpEL provides arithmetic operators such as addition, subtraction, multiplication, division, remainder, and exponentiation. However, SpEL performs operations based on the numeric types of operands and Java's numeric handling mechanisms. Therefore, a short expression does not automatically have infinite precision.

Three common problem areas:

- **Representation errors:** a decimal number cannot be represented exactly using binary floating-point types such as ¤float¤ or ¤double¤.
- **Overflow:** a result exceeds the range of a bounded integer type such as ¤int¤ or ¤long¤.
- **Rounding and scale:** division or monetary calculations may require a specific number of decimal places and a defined rounding policy.

What matters is identifying the data type of each operand before evaluating an expression. Two expressions with the same form but using different numeric types can have different precision, range, and results.

## 2. Bounded Integers and Overflow

Primitive types and their wrapper classes in Java have finite ranges. For example:

- ¤byte¤: from -128 to 127.
- ¤short¤: from -32,768 to 32,767.
- ¤int¤: from -2,147,483,648 to 2,147,483,647.
- ¤long¤: from -9,223,372,036,854,775,808 to 9,223,372,036,854,775,807.

If a calculation result exceeds the bounds of an integer type, Java may retain the low-order bits according to signed integer representation. This leads to overflow instead of automatically widening to a larger type.

For example, passing Integer variables into SpEL:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("#max + #one");

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("max", Integer.MAX_VALUE);
context.setVariable("one", 1);

Integer result = expression.getValue(context, Integer.class);
~~~

With two ¤Integer¤ operands, the addition can overflow and yield ¤-2147483648¤. Requesting the result via ¤getValue(context, Integer.class)¤ does not turn the inner addition into arbitrary-precision integer addition.

A similar situation can happen with ¤long¤ when the result exceeds ¤Long.MAX_VALUE¤ or falls below ¤Long.MIN_VALUE¤.

### 2.1. How to Avoid Integer Overflow

If the value domain can exceed the ¤long¤ range, use ¤BigInteger¤ or a numeric type with a suitable range before performing the calculation.

Example:

~~~java
context.setVariable("max", BigInteger.valueOf(Long.MAX_VALUE));
context.setVariable("one", BigInteger.ONE);

Expression expression =
    parser.parseExpression("#max.add(#one)");

BigInteger result =
    expression.getValue(context, BigInteger.class);
~~~

¤BigInteger¤ stores integers with length limited only by available memory, so it does not encounter overflow at fixed 32- or 64-bit limits. However, it still has memory and CPU cost; it should not be used unchecked for input values of arbitrary size.

If you want to keep ¤int¤ or ¤long¤, check bounds before adding or multiplying. Java has methods such as ¤Math.addExact(...)¤ and ¤Math.multiplyExact(...)¤ to detect overflow via exceptions. This check can be placed in a controlled Java method and only the validated result passed into SpEL's context.

## 3. Errors in float and double

¤float¤ and ¤double¤ use binary floating-point representation. Many common decimal fractions have no finite binary representation. Thus, the stored value is often an approximation.

Example:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("0.1 + 0.2");

Double result = expression.getValue(Double.class);
System.out.println(result);
~~~

The result may display near ¤0.30000000000000004¤ instead of exact ¤0.3¤. This is a property of binary floating-point numbers, not a SpEL-specific bug.

Small errors can accumulate across many calculations. If ¤double¤ is used to sum monetary amounts, compute interest, calculate ratios, or compare against an exact threshold, the result may deviate from business rules.

¤double¤ remains suitable for many scientific, statistical, or graphics calculations where small approximation errors are acceptable. What to avoid is using it for quantities requiring exact decimal representation without an error-handling policy.

## 4. Using BigInteger for Large Integers

¤BigInteger¤ represents arbitrary-length integers, useful when values can exceed the range of ¤long¤, such as large counters, cryptographic arithmetic, or combinatorial calculations.

¤BigInteger¤ variables can be passed into SpEL and arithmetic methods invoked:

~~~java
BigInteger left = new BigInteger("9223372036854775808");
BigInteger right = new BigInteger("10000000000000000000");

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("left", left);
context.setVariable("right", right);

Expression expression =
    parser.parseExpression("#left.multiply(#right)");

BigInteger product =
    expression.getValue(context, BigInteger.class);
~~~

Methods such as ¤add¤, ¤subtract¤, ¤multiply¤, ¤divide¤, and ¤remainder¤ allow working with large integers without overflowing fixed primitive limits.

¤BigInteger¤ division is still integer division: the fractional part is discarded. If business logic needs a fractional part, use ¤BigDecimal¤ or another suitable data model.

## 5. Using BigDecimal for Decimals Requiring Precision

¤BigDecimal¤ represents a decimal number using an unscaled integer value together with a scale. It is suitable for currency, unit prices, taxes, rates, and calculations where decimal digits carry business meaning.

¤BigDecimal¤ should be constructed from a decimal string:

~~~java
BigDecimal price = new BigDecimal("19.99");
BigDecimal rate = new BigDecimal("0.08");
~~~

Do not construct directly from a ¤double¤ value if the exact original decimal representation must be preserved:

~~~java
BigDecimal risky = new BigDecimal(0.1);
BigDecimal preferred = new BigDecimal("0.1");
~~~

¤risky¤ receives the binary approximation that ¤double¤ stores, and then represents that exact approximation as a decimal. ¤preferred¤ starts from the string "0.1" so it represents the exact intended decimal value.

¤BigDecimal¤ can be used in SpEL expressions by passing variables from Java:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression =
    parser.parseExpression("#price.multiply(#quantity)");

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("price", new BigDecimal("19.99"));
context.setVariable("quantity", new BigDecimal("3"));

BigDecimal subtotal =
    expression.getValue(context, BigDecimal.class);
~~~

When operands are ¤BigDecimal¤, the corresponding operation can preserve decimal representation. However, scale and rounding policy must be clearly specified at business steps that require them.

## 6. Distinguishing Precision and Scale of BigDecimal

These two concepts are often confused:

- **Precision:** the total number of significant digits in the value.
- **Scale:** the number of digits to the right of the decimal point.

Example:

| Value | Precision | Scale |
|---|---:|---:|
| ¤12.34¤ | 4 | 2 |
| ¤0.0012¤ | 2 | 4 |
| ¤1200¤ | 4 | 0 |
| ¤1.2300¤ | 5 | 4 |

The two values ¤1.23¤ and ¤1.2300¤ have the same numeric value when compared using ¤compareTo¤, but have different scales. Scale can affect formatting, division, and how results are represented.

Some useful methods:

~~~java
value.precision();
value.scale();
value.setScale(2, RoundingMode.HALF_UP);
~~~

¤setScale(2, ...)¤ produces a value with two digits after the decimal point according to the chosen rounding rule. This is how to express a business requirement such as "store monetary amounts to two decimal places".

Do not equate precision with the number of digits after the decimal point. If business logic limits the total number of significant digits, use precision or ¤MathContext¤; if business logic requires a fixed number of digits after the decimal point, use scale.

## 7. Division and Rounding Rules

Division is where precision and scale often become critical. Some decimal results have finite representations, such as ¤1 / 4 = 0.25¤. Some results have non-terminating repeating decimal representations, such as ¤1 / 3¤.

With ¤BigDecimal¤, exact division without limiting scale may not be possible if the result is a non-terminating repeating decimal. Java may throw ¤ArithmeticException¤ when an appropriate rounding rule is not provided.

Specify scale and ¤RoundingMode¤ explicitly when a result needs a fixed number of decimal places:

~~~java
BigDecimal amount = new BigDecimal("10");
BigDecimal divisor = new BigDecimal("3");

BigDecimal result =
    amount.divide(divisor, 2, RoundingMode.HALF_UP);
// 3.33
~~~

This method can be called from SpEL:

~~~java
Expression expression =
    parser.parseExpression(
        "#amount.divide(#divisor, #scale, #rounding)"
    );

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("amount", new BigDecimal("10"));
context.setVariable("divisor", new BigDecimal("3"));
context.setVariable("scale", 2);
context.setVariable("rounding", RoundingMode.HALF_UP);

BigDecimal result =
    expression.getValue(context, BigDecimal.class);
~~~

¤RoundingMode.HALF_UP¤ is a common choice, but it is not always the right rule. Business logic may require ¤HALF_EVEN¤, ¤DOWN¤, ¤CEILING¤, or another policy. Align the rounding rule with financial requirements and apply it at the right step of the process.

If you need to limit the number of significant digits rather than digits after the decimal point, ¤MathContext¤ can be used:

~~~java
MathContext mathContext =
    new MathContext(8, RoundingMode.HALF_EVEN);

BigDecimal result = amount.divide(divisor, mathContext);
~~~

Precision in ¤MathContext¤ is the number of significant digits, not scale. Choosing ¤MathContext¤ or ¤setScale¤ depends on the kind of limit imposed by business logic.

## 8. Comparing BigDecimal Properly

¤BigDecimal.equals(...)¤ checks both value and scale. Therefore:

~~~java
new BigDecimal("1.0").equals(new BigDecimal("1.00")) // false
~~~

Whereas:

~~~java
new BigDecimal("1.0").compareTo(new BigDecimal("1.00")) == 0 // true
~~~

If you want to compare numeric values regardless of scale, use ¤compareTo¤:

~~~text
#left.compareTo(#right) == 0
#left.compareTo(#limit) >= 0
~~~

This is useful when writing SpEL conditions for monetary amounts or decimal thresholds. If using the ¤==¤ equality operator on ¤BigDecimal¤, clearly understand the comparison rules the expression applies and the difference between object comparison and numeric value comparison.

## 9. Type Conversion Does Not Replace Range Checking

SpEL can convert values through ¤EvaluationContext¤'s ¤TypeConverter¤ mechanism, and ¤getValue(...)¤ can be requested to return a target type.

Example:

~~~java
Integer count = expression.getValue(context, Integer.class);
~~~

Requesting a result type does not guarantee that the prior calculation did not overflow. If the expression already computed using ¤Integer¤ and overflowed, converting the result to another type cannot restore the original correct value.

Similarly, converting a floating-point number to ¤BigDecimal¤ cannot automatically recover fractional digits lost due to binary representation. Choose the numeric type from the start, before performing the operation.

If value domain bounds are needed, validate before or after the calculation in the Java layer:

~~~java
if (quantity < 0 || quantity > MAX_ALLOWED_QUANTITY) {
    throw new IllegalArgumentException("Quantity is out of range");
}
~~~

For primitive addition or multiplication, consider ¤Math.addExact¤ and ¤Math.multiplyExact¤. For ¤BigDecimal¤, check scale, precision, and business bounds using appropriate methods.

## 10. Controlling Errors in Monetary Calculations

For currency, clearly decide:

1. Currency unit and number of decimal places stored.
2. Data type used throughout all calculations.
3. Timing of rounding: after each line item, after the order total, or at ledger posting.
4. Rounding rule applied.
5. How negative numbers, refunds, taxes, and discount rates are handled.
6. Valid value bounds and how out-of-bounds values are handled.

Example calculating a line item total:

~~~java
BigDecimal unitPrice = new BigDecimal("12.345");
BigDecimal quantity = new BigDecimal("3");

BigDecimal lineTotal = unitPrice.multiply(quantity)
    .setScale(2, RoundingMode.HALF_UP);
// 37.04
~~~

If unit price is rounded before multiplying, the result may differ from multiplying exactly and then rounding the line total. Both approaches may be valid in different business contexts; what matters is choosing the right rule and applying it consistently.

SpEL should express short calculations once data has been normalized and numeric types have been selected. Complex financial rules, requiring auditing or multi-step coordination, belong in a Java service for easier testing and control.

## 11. Testing Boundary Values

Do not test only a few typical values. For arithmetic expressions, include data near boundaries and special cases:

| Case | What to Verify |
|---|---|
| Value equal to ¤Integer.MAX_VALUE¤ | Whether addition or multiplication exceeds range |
| Value equal to ¤Long.MAX_VALUE¤ | Whether BigInteger is needed |
| Negative value near bound | Overflow in the negative direction |
| ¤0.1 + 0.2¤ | Floating-point representation error |
| Division by 0 | Arithmetic error and how the application handles it |
| ¤1 / 3¤ with BigDecimal | Whether scale or MathContext is provided |
| ¤1.0¤ and ¤1.00¤ | Value and scale comparison |
| Very large value or very high scale | Precision limits, memory, and computation cost |
| Null or wrong-type value | Conversion errors and evaluation errors |

Separate ¤Expression¤ instances can be created to test the same rule against multiple datasets. For each case, define the expected result or expected error type in advance. This helps detect discrepancies between input numeric types, rounding approaches, and results used by the application.

## 12. Key Takeaways

SpEL provides arithmetic operators, but precision and result range depend on actual numeric types. ¤int¤ and ¤long¤ can overflow; ¤float¤ and ¤double¤ have binary representation errors; ¤BigInteger¤ suits large integers; ¤BigDecimal¤ suits decimals needing controlled precision.

With ¤BigDecimal¤, distinguish precision and scale, construct values from decimal strings, specify scale and ¤RoundingMode¤ when dividing or rounding, and use ¤compareTo¤ when comparing values independently of scale.

Do not rely on type conversion at the end of an expression to fix errors or overflow that happened earlier. Choose numeric types before the calculation, check bounds, define rounding policies, and test boundary values.