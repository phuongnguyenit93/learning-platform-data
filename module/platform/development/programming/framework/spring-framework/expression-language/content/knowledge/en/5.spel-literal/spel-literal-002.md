# Decimal Literals and Inferred Numeric Types

In SpEL, a numeric literal is a numeric value written directly in an expression, such as 12, 12.5, or 1.25M. How the literal is written affects the Java type that the parser creates. This is an important detail when the expression performs calculations, passes results to a method, assigns to a property, or injects into a field with a specific type.

In particular, a decimal number written with a dot does not automatically become a BigDecimal. In SpEL, a real number literal without a suffix is usually inferred as Double. If you need to represent a decimal number with BigDecimal, use the M suffix. Choosing the right type right from the literal helps avoid binary precision errors and reduces unintended type conversions.

## 1. Integer Literals and Real Number Literals

SpEL supports integer and real number literals. How they are written determines the numeric type group chosen by the parser:

| Syntax | Usually Inferred Type | Meaning |
|---|---|---|
| 42 | Integer | Default integer |
| 42L | Long | Integer with L suffix |
| 42.5 | Double | Default real number |
| 42.5D | Double | Explicitly specifies Double type |
| 42.5F | Float | Explicitly specifies Float type |
| 42.5M | BigDecimal | Decimal number in decimal representation |

Letter suffixes can be written in uppercase or lowercase according to SpEL syntax. In code and documentation, it is best to consistently use uppercase L, D, F, and M for easy recognition.

The point to remember is that 42.5 and 42.5M have the same mathematical value in standard notation, but not the same Java type. The first literal is Double; the second literal is BigDecimal.

## 2. Why Do Decimal Literals Default to Double?

When the parser encounters a literal with a fractional part or exponential form without a suffix specifying another type, SpEL creates a Double value by default.

Example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Object value = parser.parseExpression("12.50").getValue();

System.out.println(value);                      // 12.5
System.out.println(value.getClass().getName()); // java.lang.Double
~~~

The dot in the literal indicates a real number, but it does not say that the application wants to use BigDecimal. Double is Java's 64-bit binary floating-point type. Many familiar decimal fractions, such as 0.1, do not have an exact finite binary representation. Therefore, the value stored in a Double may be an approximation.

For scientific, statistical, graphical calculations, or cases where floating-point error is acceptable, Double is usually suitable. For currency, taxes, percentages requiring clear rounding rules, or financial data, BigDecimal is usually the more appropriate choice.

Do not infer the data type solely from how a number is displayed. Two values can both print as 12.5 while one value is Double and the other is BigDecimal.

## 3. Using the M Suffix to Create BigDecimal

SpEL supports the M or m suffix to explicitly indicate a BigDecimal literal. This feature has been available since Spring Framework 5.3.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Object decimal = parser.parseExpression("12.50M").getValue();

System.out.println(decimal);                      // 12.50
System.out.println(decimal.getClass().getName()); // java.math.BigDecimal
~~~

The M suffix is especially useful when writing expressions in annotations, rules, or configuration because it expresses the type intent right at the literal's position:

~~~java
@Value("#{12.50M}")
private BigDecimal unitPrice;
~~~

In this example, the expression returns a BigDecimal. Spring injects the result into the BigDecimal field without relying on converting a Double to BigDecimal.

BigDecimal literals can be used in arithmetic expressions:

~~~text
(19.90M * 3) + 5.00M
~~~

When designing monetary expressions, keep operands in a consistent decimal type and clearly define scale, precision, and rounding rules where appropriate. The M suffix selects the BigDecimal type for the literal; it does not automatically determine the business rounding policy.

## 4. The F, D, and L Suffixes

Besides M, other suffixes help specify other numeric types.

### 4.1. Float with F

~~~java
Object value = parser.parseExpression("3.14F").getValue();

System.out.println(value.getClass().getName()); // java.lang.Float
~~~

Float uses 32 bits and has lower precision than Double. Only use it when the Float type is part of the data contract or there is a specific memory/interop reason. Do not choose Float for currency.

### 4.2. Double with D

~~~java
Object value = parser.parseExpression("3.14D").getValue();

System.out.println(value.getClass().getName()); // java.lang.Double
~~~

D makes the intent to use Double explicit. For real number literals without a suffix, this is also the default type.

### 4.3. Long with L

~~~java
Object value = parser.parseExpression("9000000000L").getValue();

System.out.println(value.getClass().getName()); // java.lang.Long
~~~

The L suffix indicates a Long integer literal. It is useful for integers larger than the Integer range and when the target method or property requires Long.

Suffixes determine the type of the input literal. The result type after an operation also depends on the operands and how the operator handles them.

## 5. Exponents and Writing Decimal Numbers

SpEL accepts writing real numbers in exponential notation. For example:

~~~text
1.5e3
2.75E-2
1.5e3M
~~~

This notation represents 1500, 0.0275, and 1500 as BigDecimal when the M suffix is present, respectively. Exponential form is convenient for very large or very small values, but can be hard to read in business configuration if readers are accustomed to standard decimal notation.

When writing literals in rules or configuration maintained by multiple people, prefer a format that helps readers immediately recognize the unit and magnitude. If a value represents money, clearly state the unit in the variable name or surrounding documentation; SpEL only sees the number and numeric type, not whether it is dong, dollars, or a percentage.

## 6. Checking the Actual Type Created by the Parser

When unsure which type the parser infers, retrieve the value as an Object and inspect its actual class. Do not ask the parser to immediately convert to a target type if the goal is to check the original type of the literal.

~~~java
ExpressionParser parser = new SpelExpressionParser();

String[] literals = {
        "12",
        "12L",
        "12.5",
        "12.5D",
        "12.5F",
        "12.5M"
};

for (String source : literals) {
    Object value = parser.parseExpression(source).getValue();

    System.out.printf(
            "%-8s -> %-20s value=%s%n",
            source,
            value.getClass().getSimpleName(),
            value
    );
}
~~~

Illustrative output:

~~~text
12       -> Integer              value=12
12L      -> Long                 value=12
12.5     -> Double               value=12.5
12.5D    -> Double               value=12.5
12.5F    -> Float                value=12.5
12.5M    -> BigDecimal           value=12.5
~~~

If you call getValue(BigDecimal.class) or a typed result overload, Spring can convert the value to the requested type if a converter supports it. When checking type inference, use getValue() returning Object to distinguish the initial literal type from the post-conversion type.

## 7. Literal Type and Operation Result Type

Do not assume that the result type is always the same as the type of the first literal. An expression can combine multiple numeric types; the operator and conversion mechanism determine how the operation is performed and the result type.

Example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Object a = parser.parseExpression("10 + 2").getValue();
Object b = parser.parseExpression("10.5 + 2.5").getValue();
Object c = parser.parseExpression("10.5M + 2.5M").getValue();

System.out.println(a.getClass().getName());
System.out.println(b.getClass().getName());
System.out.println(c.getClass().getName());
~~~

Pure integer expressions, default real number expressions, and BigDecimal literals go through different numeric processing paths. If the result type is part of an API or passed into an overloaded method, verify it with a small test on the exact Spring version the application is running.

In particular, when mixing BigDecimal with Double or Float, do not rely on the assumption that every operation will automatically convert to BigDecimal as desired. Write literals of the same type, or convert explicitly at the data boundary. This avoids relying on implicit conversion rules and prevents introducing floating-point errors into decimal calculations.

## 8. BigDecimal, Precision, and Scale

BigDecimal represents a decimal number using a non-floating-point integer value and a scale. This fits many problems requiring decimal representation under clear rules.

Example:

~~~java
BigDecimal price = new BigDecimal("19.90");
BigDecimal quantity = new BigDecimal("3");
BigDecimal total = price.multiply(quantity);

System.out.println(total); // 59.70
~~~

In SpEL, you can write the corresponding literals with the M suffix:

~~~text
19.90M * 3M
~~~

Using BigDecimal does not mean every operation automatically produces a result with the desired business scale. Division can produce a non-terminating decimal expansion; in that case Java BigDecimal needs appropriate scale and RoundingMode rules. Monetary calculations often need rounding specified at a defined business step, for example when calculating taxes, allocating discounts, or totaling line items.

Additionally, scale is part of BigDecimal. 19.90M and 19.9M have the same numeric value but different scales. If the business logic cares about the number of decimal digits displayed or compares using BigDecimal.equals() in Java, handle scale intentionally. When comparing numeric values in Java, compareTo() is usually more appropriate if the scales do not need to be identical.

## 9. Type Conversion When Passing Results into Java or Spring

SpEL results can be requested as a specific Java type:

~~~java
Expression expression = parser.parseExpression("12.50M");

BigDecimal amount = expression.getValue(BigDecimal.class);
~~~

Or injected directly in Spring:

~~~java
@Component
public class PricingDefaults {

    @Value("#{12.50M}")
    private BigDecimal defaultPrice;

    @Value("#{0.15M}")
    private BigDecimal taxRate;

    @Value("#{3.5}")
    private double measurement;
}
~~~

The example above clarifies the intent: price and tax are BigDecimal, while the measurement quantity uses Double. The field type does not change how the parser created the literal; it is the target type that the evaluation/conversion mechanism needs to provide.

Two configuration situations need to be distinguished:

- @Value with a SpEL expression such as #{12.50M} asks Spring to evaluate the expression and the literal already carries the BigDecimal type.
- @Value with a configuration property placeholder retrieves a string from the property source and converts it to the field type via the conversion service. This is not a SpEL decimal literal.

If external configuration contains the string "12.50", injecting into BigDecimal relies on Spring's converter, not on the M suffix in SpEL. Choose the right mechanism according to the data source and goal.

## 10. Using Numeric Literals in Conditions and Rules

Numeric literals are often used in conditions:

~~~text
age >= 18
temperature < 37.5
total >= 100.00M
discountRate <= 0.15M
~~~

In rule expressions, the numeric type should be compatible with the type of the compared property. If the domain object uses BigDecimal for amount, use a BigDecimal literal to express the threshold. If the domain object uses Integer for count, an integer literal is usually clear enough.

Example in Java:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression rule = parser.parseExpression(
        "total >= 100.00M and itemCount >= 2"
);

boolean accepted = Boolean.TRUE.equals(
        rule.getValue(context, Boolean.class)
);
~~~

When expressions are configured by operators, clearly document the unit, data type, and rounding rule of each threshold. 0.15M might be 15% as a rate, but SpEL does not know it is a percentage unless the application specifies it.

## 11. Common Mistakes

| Symptom | Common Cause | How to Handle |
|---|---|---|
| Value 12.50 is Double even though field is BigDecimal | Default literal for real numbers is Double | Use 12.50M if a BigDecimal literal is wanted |
| Calculation result has small error | Using Double/Float for decimal fractions | Use BigDecimal literals and keep operands the same type |
| Method does not receive expected parameter | Literal type differs from the selected overload type | Check runtime type and method signature |
| Conversion to target type fails | No suitable converter or incompatible value | Check return type, TypeConverter, and field type |
| Dividing BigDecimal throws an error | Result has non-terminating decimal expansion without suitable scale/rounding | Specify scale and RoundingMode in business logic |
| Displayed result differs from expected number of digits | Numeric value and display formatting are two separate things | Format at the presentation layer, define scale during calculation |
| Comparing BigDecimal in Java gives unexpected result | equals() considers scale as well | Use compareTo() when numeric value comparison is needed |

## 12. Key Takeaways

Decimal literals without a suffix in SpEL default to Double. The D suffix explicitly specifies Double, F selects Float, L selects Long for integers, and M selects BigDecimal. If exact decimal values are needed, use M directly in the expression instead of relying on converting from Double afterward.

The literal's type is the starting point; the operation result type also depends on the operands, operators, and conversions. Check the runtime type when it affects method overloading or data contracts, keep numeric types consistent within expressions, and handle scale/rounding at the business layer.