# The between Operator and Expressing Value Ranges

## Objectives

After this lesson, you will be able to use the **between** operator in Spring Expression Language (SpEL) to test whether a value lies within a range; understand how the two endpoints of the range are handled; pass lower and upper bounds via variables; and choose the appropriate syntax for closed, open, or half-open intervals. You will also learn how to handle data types, null values, invalid ranges, and boundary cases.

## 1. What Is the between Operator Used For?

**between** is a comparison operator used to check whether a value lies between two bounding values. Basic syntax:

~~~text
value between {lowerBound, upperBound}
~~~

Example:

~~~text
#age between {18, 65}
~~~

The expression returns **true** if **#age** lies in the range from 18 to 65 according to comparison order. If it is less than 18 or greater than 65, the result is **false**.

This operator expresses a range rule more concisely than writing two separate comparisons. It is especially useful when configuration expressions need to check age, score, price level, dates, or a business threshold.

## 2. Syntax and the Two Bounds of the Range

The left side of **between** is the value to be checked. The right side is an inline list consisting of two elements in order:

1. Lower bound.
2. Upper bound.

Example:

~~~text
#score between {0, 100}
~~~

This expression can be understood as equivalent to:

~~~text
#score >= 0 and #score <= 100
~~~

Therefore, **between** uses a **closed interval**: both the lower bound and the upper bound are counted as inside the range.

| Test Value | Expression | Result |
|---:|---|---|
| 0 | 0 between {0, 100} | true |
| 1 | 1 between {0, 100} | true |
| 50 | 50 between {0, 100} | true |
| 100 | 100 between {0, 100} | true |
| -1 | -1 between {0, 100} | false |
| 101 | 101 between {0, 100} | false |

If the business rule requires excluding one or both endpoints, **between** cannot directly express an open interval. Use separate comparisons such as **>**, **<**, **>=**, and **<=**.

## 3. Inline List on the Right Side

The curly braces in **between** syntax represent a SpEL inline list:

~~~text
#temperature between {18, 26}
~~~

This is a list of two bounding values, not syntax for generating a number sequence from 18 to 26. The expression does not iterate over every integer in the range; it compares the value on the left against the two bounds.

The order of the two elements matters. The first element is the lower bound and the second element is the upper bound:

~~~text
#quantity between {#minimumQuantity, #maximumQuantity}
~~~

Do not reverse the two bounds merely to write them in another order. If the lower bound is greater than the upper bound in the same comparison domain, no ordinary value simultaneously satisfies being greater than or equal to the lower bound and less than or equal to the upper bound. Validate bound ordering in the Java layer before evaluation if the two bounds come from dynamic data.

The right side must provide exactly two bounding values. If the expression does not produce an appropriate two-element structure, evaluation may fail. When a dynamic range is needed, use two variables or two properties already supplied in the context.

## 4. Using Variables as Lower and Upper Bounds

Numbers do not need to be hardcoded in the expression. Bounds can be passed into the EvaluationContext as variables:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression =
    parser.parseExpression("#score between {#minimum, #maximum}");

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("score", 82);
context.setVariable("minimum", 60);
context.setVariable("maximum", 100);

Boolean accepted = expression.getValue(context, Boolean.class);
~~~

The result is **true** because 82 lies in the closed interval from 60 to 100.

When bound values vary by configuration or user, simply update the variables in the context without assembling a new expression string. This approach also avoids concatenating input data directly into SpEL code.

Bounds can be read from a root or variable object:

~~~text
#measurement.value between {#measurement.minAllowed, #measurement.maxAllowed}
~~~

Or use the root object without a # prefix if the application passes it directly to getValue:

~~~text
value between {minAllowed, maxAllowed}
~~~

Property names must match the object model and the accessibility configured on the EvaluationContext.

## 5. Expressing Closed, Open, and Half-Open Intervals

Choose operators based on the business meaning of the two endpoints.

| Interval Type | Condition | SpEL Example |
|---|---|---|
| Closed [a, b] | x >= a and x <= b | #x between {#a, #b} |
| Open (a, b) | x > a and x < b | #x > #a and #x < #b |
| Half-open [a, b) | x >= a and x < b | #x >= #a and #x < #b |
| Half-open (a, b] | x > a and x <= b | #x > #a and #x <= #b |

For example, a grading system may consider scores from 0 up to below 5 as failing:

~~~text
#score >= 0 and #score < 5
~~~

If the rule accepts a score of 5 as well:

~~~text
#score between {0, 5}
~~~

For date ranges, half-open intervals are often useful. For example, a range where the start date is included but the end date is excluded:

~~~text
#eventDate >= #startDate and #eventDate < #endDate
~~~

Half-open intervals prevent adjacent ranges from overlapping at boundaries. **between** is suitable when both endpoints are included.

## 6. Combining between with Logical Operators

**between** can be combined with **and**, **or**, and **not** to describe multi-condition rules.

For example, a transaction must have an amount within the allowed range and a confirmed status:

~~~text
#transaction.amount between {#minimumAmount, #maximumAmount}
and #transaction.confirmed
~~~

Another case is checking whether an age belongs to one of two allowed groups:

~~~text
(#age between {18, 25}) or (#age between {30, 40})
~~~

Parentheses help readers clearly see that each **between** is an independent condition. A negation can also be written:

~~~text
not (#score between {0, 100})
~~~

This expression is true when the score falls outside the closed range from 0 to 100. To express the two out-of-range cases explicitly, you can write:

~~~text
#score < 0 or #score > 100
~~~

When there are multiple conditions, use parentheses to avoid confusion about the precedence of **and** and **or**.

## 7. Data Types and Comparison Rules

**between** is not limited to integers. It can be used with values that have appropriate comparison ordering, provided the data types on the left side and both bounds can be compared under a mechanism supported by SpEL.

### 7.1. Integers and Decimals

Example with scores:

~~~text
#score between {0.0, 10.0}
~~~

When working with money or exact decimal values, pass BigDecimal from Java:

~~~java
context.setVariable("amount", new BigDecimal("125.50"));
context.setVariable("minimum", new BigDecimal("100.00"));
context.setVariable("maximum", new BigDecimal("200.00"));

Expression expression =
    parser.parseExpression("#amount between {#minimum, #maximum}");

Boolean inRange = expression.getValue(context, Boolean.class);
~~~

Keep operands in the same type domain or compatibly convertible. Do not rely on implicit conversion to mask wrongly typed data.

### 7.2. Dates and Times

Date and time types with comparison ordering can be used to check whether a timestamp falls within a range. Example:

~~~java
context.setVariable("eventDate", LocalDate.of(2026, 5, 12));
context.setVariable("startDate", LocalDate.of(2026, 1, 1));
context.setVariable("endDate", LocalDate.of(2026, 12, 31));

Expression expression =
    parser.parseExpression("#eventDate between {#startDate, #endDate}");

Boolean withinYear = expression.getValue(context, Boolean.class);
~~~

All three variables use LocalDate, so comparison by date order is clearly defined.

For instants with time zones, normalize to a consistent representation, such as Instant, or unify the time zone before creating bounds. Do not compare local dates from different time zones as if they were on the same absolute timeline.

### 7.3. Strings

Strings can be compared in lexicographic order if the comparison type is supported. Example:

~~~text
#code between {'A100', 'A999'}
~~~

Understand that lexicographic order is not natural numeric order or user-language sorting rules. For example, the strings "A20" and "A100" are compared character by character, without automatically converting the numeric part into an integer.

Do not use **between** on strings to describe complex business ordering, locale-specific ordering, or code ranges with custom rules. For those cases, normalize the data or write a comparator in Java.

## 8. Null Values, Wrong Types, and Invalid Ranges

A **between** expression can only evaluate when the value to check and both bounds supply sufficient comparable data.

Cases that must be handled:

- The left-hand value is null.
- The lower bound or upper bound is null.
- One bound is a string while the checked value is an incompatible numeric type.
- The two bounds belong to types that cannot be compared with each other or with the checked value.
- The lower bound is greater than the upper bound.
- A referenced variable or property does not exist in the context.

These cases can lead to an evaluation error rather than a **false** result. **between** does not substitute 0 for missing data, does not automatically sort the two bounds, and does not validate business rules.

If input data may be missing, check beforehand:

~~~text
#value != null and #minimum != null and #maximum != null
and #minimum <= #maximum
and #value between {#minimum, #maximum}
~~~

This expresses multiple conditions in a single expression. However, the application still needs to validate data and handle errors in the Java layer; a conditional expression should not be treated as a comprehensive validation mechanism for untrusted data.

## 9. Practical Example: Classifying Temperature Levels

Suppose a temperature monitoring application needs to determine whether a value falls within the normal operating zone:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "#temperature between {#minimum, #maximum}"
);

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("temperature", new BigDecimal("22.5"));
context.setVariable("minimum", new BigDecimal("18.0"));
context.setVariable("maximum", new BigDecimal("26.0"));

Boolean normal = expression.getValue(context, Boolean.class);
~~~

The result is **true**. If the temperature is exactly 18.0 or 26.0, the result is still **true** because both bounds are included.

If the rule requires the temperature to be strictly greater than 18.0 and less than 26.0, replace it with:

~~~text
#temperature > #minimum and #temperature < #maximum
~~~

Do not use **between** when both endpoints need to be excluded.

## 10. Practical Example: Checking Order Amount Limits

An order is accepted if its total falls within configured limits and its status is not cancelled:

~~~text
#order != null
and #order.status != 'CANCELLED'
and #order.total between {#minimumTotal, #maximumTotal}
~~~

The **#minimumTotal** and **#maximumTotal** variables can be BigDecimal values passed from Java. If the application supports multiple currencies, ensure the order amount and both bounds share the same currency unit before comparing.

If the rule involves additional conditions such as customer tier, region, payment status, or daily limits, consider moving complex business decisions into a Java service. SpEL is well suited to short, easy-to-understand declarative conditions.

## 11. Testing Boundary Values

Value ranges commonly have bugs right at the two endpoints. When testing a **between** expression, include:

| Case | Expected Result for x between {10, 20} |
|---|---|
| x = 9 | false |
| x = 10 | true |
| x = 11 | true |
| x = 20 | true |
| x = 21 | false |

Besides the two bounds, also test:

- Null value.
- One or both bounds are null.
- Lower bound equals upper bound.
- Lower bound greater than upper bound.
- Decimal values close to the bounds.
- Incompatible data types.
- Date/time values right at the start and end instants.

If using open or half-open intervals, write separate test cases for each endpoint. Do not infer open-interval results from **between** tests because the two interval types have different semantics.

## 12. Key Takeaways

The **between** operator checks whether a value lies within a closed interval. The syntax is:

~~~text
value between {lowerBound, upperBound}
~~~

Both the lower bound and the upper bound are included. The right side is an inline list containing two bounds in exact order; it does not generate a sequence of numbers and does not automatically sort the limits.

Use **between** for closed intervals. Use comparison operators **>**, **<**, **>=**, and **<=** when open or half-open intervals are needed. Bounds can be literals, variables, or properties, as long as the data types can be compared appropriately.

Validate null data, data types, and the order of the two bounds; test both endpoints; and keep complex business logic in Java. When a rule is simply checking a value within a range, **between** keeps SpEL expressions short and readable.