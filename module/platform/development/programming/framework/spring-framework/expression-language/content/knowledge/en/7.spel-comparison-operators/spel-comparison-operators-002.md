# Greater Than, Less Than, and Inclusive Variants

In Spring Expression Language (SpEL), the **greater than**, **less than**, **greater than or equal to**, and **less than or equal to** operators are used to compare two values and return a Boolean result. They commonly appear in business conditions, bean configurations, cache expressions, or integration points such as Spring Security.

The four corresponding operators are **>**, **<**, **>=**, and **<=**. A key point to note is that the data types of both operands must support comparison. A syntactically valid expression can still fail during evaluation if the actual data cannot be compared according to SpEL's rules.

## The Four Relational Operators

| Operator | Meaning | Example | Result |
|---|---|---|---|
| **>** | Greater than | **10 > 5** | true |
| **<** | Less than | **3 < 8** | true |
| **>=** | Greater than or equal to | **10 >= 10** | true |
| **<=** | Less than or equal to | **5 <= 4** | false |

The **>** and **<** operators are strict comparisons: when two values are equal, the result is false. The **>=** and **<=** operators include the equality case.

Direct evaluation examples:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Boolean greater = parser.parseExpression("10 > 5")
        .getValue(Boolean.class);

Boolean less = parser.parseExpression("3 < 8")
        .getValue(Boolean.class);

Boolean greaterOrEqual = parser.parseExpression("10 >= 10")
        .getValue(Boolean.class);

Boolean lessOrEqual = parser.parseExpression("5 <= 4")
        .getValue(Boolean.class);
~~~

Each expression returns a Boolean. This result can be used to decide execution branches in Java or for Spring to evaluate conditions at an integration point that supports SpEL.

## Comparing Integers and Floating-Point Numbers

When both operands are numbers, SpEL performs comparison by numeric value. Numeric types can come from literals, properties of the root object, or variables in the EvaluationContext.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Boolean result1 =
        parser.parseExpression("100 > 80")
                .getValue(Boolean.class);

Boolean result2 =
        parser.parseExpression("19.5 <= 20.0")
                .getValue(Boolean.class);

Boolean result3 =
        parser.parseExpression("10 >= 10.0")
                .getValue(Boolean.class);
~~~

The third example illustrates comparing an integer literal with a decimal literal. SpEL supports comparing numeric values of different types through its numeric comparison mechanism.

For data retrieved from objects, let the property type reflect the true meaning of the data. A numeric value stored as a String should not be treated as a number merely because its content looks like a number. Convert and validate data at the input boundary before evaluating expressions.

## Using Comparison Operators with a Root Object

In applications, comparison thresholds are often applied to a property of an object. For example, checking whether a student's score reaches the minimum level:

~~~java
public class ExamResult {
    private final String studentName;
    private final int score;

    public ExamResult(String studentName, int score) {
        this.studentName = studentName;
        this.score = score;
    }

    public String getStudentName() {
        return studentName;
    }

    public int getScore() {
        return score;
    }
}
~~~

~~~java
ExamResult result = new ExamResult("An", 85);

ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("score >= 80");

Boolean passed =
        expression.getValue(result, Boolean.class);
~~~

Here, **result** is the root object. SpEL reads the **score** property, compares it with the literal 80, and returns true. If the score were 79, the same expression would return false.

An expression can be parsed once and then evaluated against multiple objects:

~~~java
Expression passedExpression =
        parser.parseExpression("score >= 80");

for (ExamResult item : results) {
    Boolean passed =
            passedExpression.getValue(item, Boolean.class);
    // Process the result
}
~~~

The literal 80 keeps the same value across all evaluations, while the score property changes with the root object. Therefore, the Boolean result can differ across students.

## Using Variables as Comparison Thresholds

If a threshold varies by configuration or per request, it should not be hardcoded in the expression string. The threshold can be passed into the EvaluationContext as a variable:

~~~java
ExamResult result = new ExamResult("An", 85);

StandardEvaluationContext context =
        new StandardEvaluationContext(result);

context.setVariable("passingScore", 80);

ExpressionParser parser = new SpelExpressionParser();
Expression expression =
        parser.parseExpression("score >= #passingScore");

Boolean passed =
        expression.getValue(context, Boolean.class);
~~~

The **#** sign is used to reference a variable in the evaluation context. The **score** property is read from the root object, while **#passingScore** comes from the variable provided by the application.

This approach separates the comparison rule from the threshold value. The same Expression can be reused with contexts having different thresholds, provided the data and variable types are appropriate.

## Comparing Strings

String in Java implements Comparable, so SpEL can perform relational comparisons on two compatible strings. Comparison according to String's natural ordering is lexicographic comparison by character values, not semantic comparison such as version order or dates.

~~~java
Boolean result =
        parser.parseExpression("'apple' < 'banana'")
                .getValue(Boolean.class);
~~~

The result is true according to string comparison order. However, uppercase and lowercase letters have different values in this comparison. For example, direct String comparison should not be used to determine which user name is "greater" in natural language.

If case-insensitive comparison is needed, normalize the data first or use an application-controlled comparison method. When comparing versions, dates, or business codes with custom rules, convert data to a type with appropriate semantics instead of relying on character ordering.

## Combining Multiple Conditions

Relational operators are often combined with logical operators to create conditions with multiple thresholds:

~~~java
Expression expression = parser.parseExpression(
        "score >= 80 and score <= 100");
~~~

The expression above checks that score lies within the range from 80 to 100, inclusive of both endpoints.

Classification conditions can also be written:

~~~java
Expression expression = parser.parseExpression(
        "age >= 18 and age < 65");
~~~

The condition is true when age is 18 or older and less than 65. The difference between **<** and **<=** determines exactly whether the boundary value is accepted.

When combining multiple operators, parentheses can be used to clarify condition grouping:

~~~java
"active == true and (score >= 80 or bonus >= 10)"
~~~

Parentheses clarify that either score reaching the threshold or bonus reaching the threshold is sufficient, while active must be true.

## Handling null Values

Do not assume that null can be compared as greater than or less than like an ordinary number. If a property can be null, check for null explicitly before performing the comparison:

~~~java
Expression expression = parser.parseExpression(
        "score != null and score >= 80");
~~~

The expression checks that score is not null before applying the threshold. This expresses the business condition clearly and avoids evaluation errors due to missing data.

If a null value has a specific meaning, decide the policy in the application: treat it as failing, skip the record, or return an undetermined state. Do not let implicit null behavior substitute for business rules.

## Incompatible Data Types

Relational operations require two comparable operands. For numeric types, SpEL uses numeric comparison rules. For other object types, comparison generally relies on the type's comparability, such as Comparable, and compatibility between the two operands.

For example, comparing a number with a string containing digits does not mean SpEL always automatically interprets that string as a number:

~~~java
Expression expression =
        parser.parseExpression("score > '80'");
~~~

Do not rely on implicit conversion to handle heterogeneous data. If one side is a String and the other side is an Integer, the expression may fail to evaluate because the two operands are incompatible with the comparison being performed.

Convert the data to the same type before evaluation:

~~~java
Integer score = Integer.valueOf(inputScore);

StandardEvaluationContext context =
        new StandardEvaluationContext();
context.setVariable("score", score);
context.setVariable("threshold", 80);

Expression expression =
        parser.parseExpression("#score > #threshold");

Boolean aboveThreshold =
        expression.getValue(context, Boolean.class);
~~~

Converting and validating input in Java keeps the SpEL expression focused on comparison rules while also making data errors easier to diagnose.

## Comparing BigDecimal and Precision-Sensitive Values

For financial data, BigDecimal can be used as an operand. SpEL supports comparing numeric values according to their numerical value:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("price", new BigDecimal("100.00"));
context.setVariable("limit", new BigDecimal("100.0"));

Expression expression =
        parser.parseExpression("#price >= #limit");

Boolean withinLimit =
        expression.getValue(context, Boolean.class);
~~~

The two BigDecimal values above are numerically equal despite having different scales. This should be distinguished from calling **BigDecimal.equals(...)** directly in Java, which also considers scale. When exact currency rules are needed, clearly define the scale, rounding mode, and business boundary conditions.

For Float and Double, floating-point representation inaccuracy can cause a value very close to a threshold not to equal the expected threshold exactly. If a condition depends on an exact boundary, use BigDecimal or normalize values according to business rules before comparing.

## Comparing Dates and Comparable Types

Data types with natural ordering, such as certain Java date/time classes, can be compared if both operands are compatible with SpEL's comparison mechanism. For example, a LocalDate property can be compared with another LocalDate variable to check a deadline:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(order);

context.setVariable(
        "deadline",
        LocalDate.of(2026, 12, 31));

Expression expression =
        parser.parseExpression("deliveryDate <= #deadline");

Boolean onTime =
        expression.getValue(context, Boolean.class);
~~~

The expression compares deliveryDate with deadline. Both need to be compatible date types. Do not compare dates converted to arbitrary strings because character ordering of string formats does not always match chronological order.

For custom types, if you want to use relational operators, ensure the type has appropriate comparison rules. Do not create a Comparable whose ordering is inconsistent with business semantics and expect the expression to understand those rules automatically.

## Type Checking and Error Handling

A comparison expression can parse successfully yet fail during evaluation if a property does not exist, a value is null in an invalid position, or the two operands are incompatible.

Parse errors and evaluation errors can be handled separately:

~~~java
Expression expression;

try {
    expression = parser.parseExpression("score >= #passingScore");
} catch (ParseException ex) {
    throw new IllegalArgumentException("Invalid SpEL syntax", ex);
}

try {
    Boolean passed =
            expression.getValue(context, Boolean.class);
} catch (EvaluationException ex) {
    throw new IllegalStateException("Cannot compare values", ex);
}
~~~

ParseException indicates that the expression string is syntactically invalid. EvaluationException indicates that the expression cannot be evaluated in the current context or on the current data. When handling errors, log the expression identifier, data types, and necessary context; avoid logging entire objects if they contain sensitive information.

## When Should Relational Operators Be Used in SpEL?

Relational operators are suitable for short, readable conditions with clear input data, such as:

- Checking whether a value exceeds a configured threshold.
- Checking whether a quantity, score, price, or rate falls within a range.
- Checking whether the current point in time is before or after a timestamp.
- Combining multiple conditions to enable/disable a behavior at a Spring integration point that supports SpEL.

If a rule has many branches, multiple data types, complex null policies, or needs to explain rejection reasons, move the decision logic into a clearly named Java method. A SpEL expression should express a concise condition that a reader can understand immediately.

## Conclusion

SpEL provides four relational operators **>**, **<**, **>=**, and **<=** to compare numbers, strings, and data types with compatible comparison rules. The first two operators exclude equality; the latter two include boundary values. Expressions can read data from the root object, variables in the EvaluationContext, or literals.

To keep results predictable, normalize data types before comparing, check for null explicitly, and pay attention to floating-point precision. For conditions with multiple thresholds, parentheses and logical operators make expressions easier to read. When rules become complex, moving logic into Java makes testing and diagnostics easier.
