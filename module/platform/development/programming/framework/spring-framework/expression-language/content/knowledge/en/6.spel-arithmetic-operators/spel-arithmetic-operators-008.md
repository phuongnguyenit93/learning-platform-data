# Using Parentheses to Clarify Arithmetic Expression Intent

In SpEL, parentheses help define groups of operations that need to be performed first. An expression can be syntactically valid yet produce a result different from what the author intended if readers misunderstand operator precedence. Placing parentheses in the right spots clarifies intent, making expressions easier to read, easier to verify, and safer when used in configuration or business rules.

Parentheses are not only useful for changing the order of calculation. They also help readers recognize what is the numerator, denominator, discount part, subtotal, or condition that should be evaluated as a logical unit.

## 1. Basic Order of Operations

In standard arithmetic expressions, multiplication, division, and remainder are performed before addition and subtraction. When operators have the same precedence level, operations are processed from left to right.

Example:

~~~text
2 + 3 * 4
~~~

The result is 14 because multiplication is performed first: 3 * 4 = 12, then 2 + 12 = 14.

If you want to add first and then multiply, put the part to be added in parentheses:

~~~text
(2 + 3) * 4
~~~

The result is 20. Parentheses cause the group 2 + 3 to be calculated first, and then the result 5 is multiplied by 4.

The following table summarizes how common operations are read:

| Operation Group | Operators | Notes |
|---|---|---|
| Expression grouping | ( ... ) | Evaluates the inner expression first |
| Exponentiation | ^ | Used to represent exponentiation in SpEL |
| Multiplication, division, remainder | *, /, % | Higher precedence than addition and subtraction |
| Addition, subtraction | +, - | Performed after multiplication, division, and remainder |

When an expression combines multiple operator groups, parentheses are the clearest way to express the order required by business logic. For expressions with exponentiation or unary minus signs, use parentheses to clarify the base, exponent, and scope of the negative sign instead of forcing readers to deduce them on their own.

## 2. Changing Results by Grouping Operations

The same sequence of numbers and operators can give different results depending on parenthesis placement.

### 2.1. Adding First or Multiplying First

~~~text
10 + 5 * 2
(10 + 5) * 2
10 + (5 * 2)
~~~

The corresponding results are 20, 30, and 20. The first and third expressions produce the same result because multiplication already has higher precedence than addition. The second expression changes the order by grouping the addition first.

### 2.2. Dividing by a Product or Multiplying After Division

~~~text
100 / 5 * 2
100 / (5 * 2)
(100 / 5) * 2
~~~

The results are 40, 10, and 40 respectively. Division and multiplication have the same precedence, so an unparenthesized sequence is processed from left to right. If the intent is to divide by the entire product 5 * 2, the denominator must be placed in parentheses.

This is a very error-prone case when writing ratios, rates, average prices, or allocation formulas.

### 2.3. Scope of Subtraction

~~~text
100 - 20 - 5
100 - (20 - 5)
(100 - 20) - 5
~~~

The corresponding results are 75, 95, and 75. Subtraction is not associative like addition under arbitrary grouping. Parentheses help clearly identify which amount is subtracted first and which part is a group to be kept together.

## 3. Using Parentheses in SpEL with ExpressionParser

When using SpEL directly, content inside parentheses is parsed as part of the expression. No separate API is needed to create operation groups.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression first = parser.parseExpression("10 + 5 * 2");
Expression second = parser.parseExpression("(10 + 5) * 2");

Integer firstResult = first.getValue(Integer.class);
Integer secondResult = second.getValue(Integer.class);

System.out.println(firstResult);  // 20
System.out.println(secondResult); // 30
~~~

The example shows that with the same parser and the same literal types, simply changing parenthesis placement changes the result. Therefore, when reading a configuration expression, do not just look at individual operators; read the grouping structure from inside out.

Nested parentheses can be used:

~~~java
Expression expression = parser.parseExpression(
        "((10 + 5) * 2) - (8 / 4)"
);

Integer result = expression.getValue(Integer.class);
~~~

The expression above computes the two inner groups first, multiplies the first group by 2, computes the division group on the other side, and then subtracts the two results. Nested parentheses are valid, but avoid nesting too deeply if the calculation can be split into clearly named variables or properties.

## 4. Using Parentheses to Clarify Numerator and Denominator

When writing formulas with multiple components, group the numerator and denominator separately according to mathematical meaning.

Example, calculating a weighted average score:

~~~text
(scoreA * weightA + scoreB * weightB) / (weightA + weightB)
~~~

The first parentheses define the sum of weighted scores. The second parentheses define the total weight. Without these two groups, readers find it hard to tell whether the denominator includes both weights or only part of them.

Example in Java:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression weightedAverage = parser.parseExpression(
        "(#scoreA * #weightA + #scoreB * #weightB) "
        + "/ (#weightA + #weightB)"
);

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("scoreA", 8);
context.setVariable("scoreB", 9);
context.setVariable("weightA", 2);
context.setVariable("weightB", 3);

Object result = weightedAverage.getValue(context);
~~~

With the example data, the formula is (8 * 2 + 9 * 3) / (2 + 3), giving an arithmetic result of 8.6. The actual result type depends on operand types and operator rules; if a specific type is needed, design input types and result conversion appropriately.

Similarly, when calculating percentages or ratios, put parentheses around the entire part to be divided:

~~~text
(part / total) * 100
(part * 100) / total
~~~

The two ways of writing can differ in intermediate types and precision depending on the numeric types used. With integers, integer division can lose the fractional part before multiplying. If a decimal ratio is needed, choose appropriate numeric types and group operations according to the exact business formula.

## 5. Using Parentheses in Price, Tax, and Discount Formulas

Commercial formulas often have multiple steps: quantity multiplied by unit price, minus discount, then plus tax or fees. Group each part according to business sequence.

Suppose:

- Unit price: 19.90
- Quantity: 3
- Discount rate: 10%
- Tax: 8%

A clear way to write it is:

~~~text
((unitPrice * quantity) * (1 - discountRate)) * (1 + taxRate)
~~~

This formula expresses in sequence the total before discount, the post-discount factor, and the post-tax factor.

It can be written in SpEL with variables:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression totalExpression = parser.parseExpression(
        "(#unitPrice * #quantity) "
        + "* (1M - #discountRate) "
        + "* (1M + #taxRate)"
);

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("unitPrice", new BigDecimal("19.90"));
context.setVariable("quantity", new BigDecimal("3"));
context.setVariable("discountRate", new BigDecimal("0.10"));
context.setVariable("taxRate", new BigDecimal("0.08"));

BigDecimal total = totalExpression.getValue(
        context,
        BigDecimal.class
);
~~~

Here the decimal values are passed via BigDecimal variables. Parentheses clearly show each factor and the order of combination. If writing BigDecimal literals directly in the expression, the M suffix can be used, for example:

~~~text
(19.90M * 3M) * (1M - 0.10M) * (1M + 0.08M)
~~~

Parentheses only define operation grouping. They do not automatically apply currency rounding rules, determine how many decimal places to keep, or replace tax policies. Those rules must be explicitly defined in the business layer.

## 6. Using Parentheses with Negative Signs and Exponentiation

A negative sign can apply to a literal or to an entire expression group. Parentheses help determine the scope of the negative sign:

~~~text
-5 * 2
-(5 * 2)
(-5) * 2
~~~

All three ways yield -10 in this example, but the grouping carries different meanings when the expression changes:

~~~text
-(5 + 2)
(-5) + 2
~~~

The results are -7 and -3 respectively. In the first expression, the negative sign applies to the entire sum. In the second expression, only the number 5 carries a negative sign.

SpEL has the exponentiation operator ^. When an expression combines exponentiation with multiplication, negative signs, or multiple exponents, use parentheses to clearly show the base and exponent:

~~~text
(2 ^ 3) * 4
2 ^ (3 * 2)
(-2) ^ 2
-(2 ^ 2)
~~~

The groups above express different mathematical intents. For instance, (-2) ^ 2 squares a negative number, whereas -(2 ^ 2) negates the square of 2. Do not omit parentheses if doing so forces readers to guess whether the negative sign belongs to the base or the whole result.

## 7. Parentheses in Expressions Combining Arithmetic and Conditions

Parentheses are also useful when arithmetic results are used in comparison or logical conditions.

~~~text
(price * quantity) >= minimumTotal
(discount + tax) <= maximumAdjustment
((width * height) / 2) > minimumArea
~~~

For example, checking the total amount of an order:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression eligible = parser.parseExpression(
        "(#order.unitPrice * #order.quantity) "
        + "- #order.discount >= #minimumTotal"
);

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("order", order);
context.setVariable("minimumTotal", new BigDecimal("100.00"));

Boolean accepted = eligible.getValue(context, Boolean.class);
~~~

Parentheses around unit price times quantity help readers recognize the pre-discount total. Then the expression subtracts the discount and compares against the minimum threshold.

For conditions having both and/or operators, group clauses to make logical intent clear. Parentheses around arithmetic parts and parentheses around condition groups serve two different purposes, yet both make expression structure easier to understand.

## 8. Parentheses Do Not Change Numeric Types or Rounding Rules

Parentheses determine the order and scope of operations. Parentheses themselves do not convert Double to BigDecimal, turn division into exact division, or round results.

For example, if operands are Double then:

~~~text
(0.1 + 0.2) * 10
~~~

still uses Double floating-point arithmetic. Adding parentheses does not eliminate binary representation error.

If decimal precision is needed for currency, use BigDecimal or BigDecimal literals with the M suffix:

~~~text
(0.10M + 0.20M) * 10M
~~~

For BigDecimal division with a non-terminating decimal result, the application still needs to specify appropriate scale and RoundingMode. Handle rounding at an explicit business step, rather than expecting parentheses to solve precision issues.

In addition, grouping can alter the types of intermediate values because operators are applied step by step. When the result type is part of a contract with a target method or property, check the runtime type on the actual Spring version.

## 9. Writing Readable and Maintainable Expressions

A short expression may not need parentheses everywhere because precedence is already clear. However, for business expressions, an extra pair of parentheses is often worthwhile if it represents a concept such as a subtotal, ratio, factor, or threshold.

Some practical guidelines:

1. Put parentheses around numerator and denominator when a formula has multiple operands.
2. Put parentheses around a sum or difference that needs to be multiplied/divided as a single unit.
3. Put parentheses around base, exponent, and the scope of negative signs when an expression has exponentiation.
4. Use consistent spacing around operators for readability.
5. Do not nest parentheses too deeply; consider moving complex calculations into clearly named variables or methods.
6. Keep operands of the same numeric type when deterministic precision is needed.
7. Write verification examples with representative input values, especially at boundaries such as 0, negative numbers, zero denominators, and very large values.

Do not add parentheses mechanically around every operator. The goal is to clarify meaningful structure and help readers quickly identify which group is computed first.

## 10. Verifying Expressions with Comparison Cases

When writing a formula with parentheses, test at least two forms: the intended formula and a form easily miswritten if parentheses are omitted. This helps prove that the parentheses truly matter.

Example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Object withoutGrouping =
        parser.parseExpression("100 / 5 * 2").getValue();

Object withGrouping =
        parser.parseExpression("100 / (5 * 2)").getValue();

System.out.println(withoutGrouping); // 40
System.out.println(withGrouping);    // 10
~~~

When testing expressions on business objects, prepare data with values easy to calculate by hand, then compare SpEL's output with the expected result. If the expression is stored in configuration, inspect the exact string after placeholders are resolved and before evaluation to catch confusion between the two syntax layers.

Cases to consider:

- Zero or negative values.
- Zero or near-zero denominators.
- Operands of different types.
- Large values at risk of exceeding numeric type ranges.
- Decimal values needing scale or rounding.
- Expressions with exponentiation or multiple nested parenthesis groups.

## 11. Common Errors

| Symptom | Cause | How to Fix |
|---|---|---|
| Addition/multiplication result differs from expected | Forgetting that multiplication/division takes precedence over addition/subtraction | Group the part to compute first with parentheses |
| Dividing by a sum gives a result too large/small | Only part of the denominator is inside the division | Put the entire denominator in parentheses |
| Subtraction produces wrong result | Confusing grouping order of subtractions | Explicitly group the subtraction with parentheses |
| Negative sign applies to wrong scope | Unclear whether negative sign belongs to one number or the whole expression | Use parentheses around the base or the group to negate |
| Ratio formula loses fractional part | Using integer types for intermediate division | Choose appropriate decimal types and group operations clearly |
| Monetary result has precision errors | Using Double/Float or lacking a rounding policy | Use BigDecimal and define scale/rounding |
| Expression hard to read even though result is right | Too many operators and deeply nested parentheses | Extract into variables or methods with descriptive names |

## 12. Key Takeaways

Parentheses are the tool for expressing intent in SpEL arithmetic expressions. Multiplication, division, and remainder have higher precedence than addition and subtraction; operations at the same level are processed from left to right. Parentheses allow grouping numerators, denominators, subtotals, discount factors, bases, or an entire part that needs a negative sign.

Parentheses only determine how operations are grouped. Numeric types, precision, and rounding still depend on literals, variables, operators, and business rules. Write expressions in a structure that readers can verify visually, then confirm them with examples that have clear expected results.