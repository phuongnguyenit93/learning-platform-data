# Greater-Than, Less-Than, and Or-Equal Comparisons

In Spring Expression Language (SpEL), relational operators are used to determine whether a value is greater than, less than, or on one side of a comparison threshold. The four basic operators are **>**, **<**, **>=**, and **<=**. Each comparison returns a Boolean value, so they are commonly used in configuration conditions, authorization expressions, caching, or Spring integration points that support SpEL.

When using these operators, you need to pay attention to the types of the two operands, equality cases, null values, and the meaning of the data being compared. An expression can be syntactically valid yet still fail to evaluate if the two values are incompatible.

## Meaning of the Four Operators

| Operator | Meaning | Condition to return true |
|---|---|---|
| **>** | Greater than | The left-hand side has a value greater than the right-hand side |
| **<** | Less than | The left-hand side has a value less than the right-hand side |
| **>=** | Greater than or equal to | The left-hand side is greater than or equal to the right-hand side |
| **<=** | Less than or equal to | The left-hand side is less than or equal to the right-hand side |

The two operators **>** and **<** are strict comparisons. If the two values are equal, both expressions return false. The two operators **>=** and **<=** include the case where the two values are equal.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Boolean greater = parser.parseExpression("10 > 5")
        .getValue(Boolean.class);       // true

Boolean less = parser.parseExpression("3 < 8")
        .getValue(Boolean.class);       // true

Boolean greaterOrEqual = parser.parseExpression("10 >= 10")
        .getValue(Boolean.class);       // true

Boolean lessOrEqual = parser.parseExpression("5 <= 4")
        .getValue(Boolean.class);       // false
~~~

The expressions above only use literals, so they do not need a root object. When an expression references a property or variable, SpEL retrieves those values from the corresponding evaluation context.

## Comparing Numeric Values

Relational operators are commonly used to compare integers, floating-point numbers, or other numeric types. Operands can be literals in the expression, properties of the root object, or variables placed in the EvaluationContext.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Boolean enoughStock =
        parser.parseExpression("stock > 0")
                .getValue(product, Boolean.class);

Boolean withinBudget =
        parser.parseExpression("price <= 100")
                .getValue(product, Boolean.class);
~~~

In this example, **stock** and **price** are properties read from the product object; 0 and 100 are literals. If stock is greater than 0, the first expression returns true. If price is less than or equal to 100, the second expression returns true.

SpEL supports comparing numeric values according to its arithmetic rules. When using multiple numeric types, clearly define the input data type and the desired result type. Do not rely on a string such as **"100"** automatically being interpreted as the number 100 in every context. If data comes from a form, JSON, or database as a string, validate and convert it to a numeric type before evaluation.

## Comparing Integers with Floating-Point Numbers

You can compare an integer literal with a decimal literal:

~~~java
Boolean result =
        parser.parseExpression("10 >= 10.0")
                .getValue(Boolean.class);
~~~

The expression returns true because the two operands have the same numeric value. Literal types can differ, and SpEL has a mechanism to handle the corresponding numeric comparison.

With Float and Double, note floating-point representation precision errors. A computed value might be very close to the threshold without being exactly equal to the decimal value the reader expects. If a rule depends on an exact boundary, such as monetary amounts, consider BigDecimal or normalizing values according to business policy before comparing.

Example with BigDecimal provided via variables:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("price", new BigDecimal("100.00"));
context.setVariable("limit", new BigDecimal("100.0"));

Expression expression =
        parser.parseExpression("#price <= #limit");

Boolean withinLimit =
        expression.getValue(context, Boolean.class);
~~~

The comparison evaluates the arithmetic value. Different scales of two BigDecimal values do not change whether they have the same arithmetic value. If rules for scale or rounding are needed, perform and control them explicitly in Java.

## Comparing Properties of the Root Object

In an application, conditions often depend on the state of an object. For example, checking whether an order exceeds the free shipping threshold:

~~~java
public class Order {
    private final BigDecimal total;

    public Order(BigDecimal total) {
        this.total = total;
    }

    public BigDecimal getTotal() {
        return total;
    }
}
~~~

~~~java
Order order = new Order(new BigDecimal("250.00"));

ExpressionParser parser = new SpelExpressionParser();
Expression expression =
        parser.parseExpression("total >= 200");

Boolean freeShipping =
        expression.getValue(order, Boolean.class);
~~~

The order object is used as the root object. SpEL reads the total property through the appropriate property access mechanism, compares it with the literal 200, and returns a Boolean. The same Expression can be reused with different orders; the result will depend on each object's total value.

## Using Variables as Thresholds

If the threshold changes by configuration or per request, you can place it in the EvaluationContext instead of writing it directly into the expression:

~~~java
Order order = new Order(new BigDecimal("250.00"));

StandardEvaluationContext context =
        new StandardEvaluationContext(order);

context.setVariable(
        "freeShippingThreshold",
        new BigDecimal("200.00"));

ExpressionParser parser = new SpelExpressionParser();
Expression expression =
        parser.parseExpression("total >= #freeShippingThreshold");

Boolean freeShipping =
        expression.getValue(context, Boolean.class);
~~~

The **#** symbol is used to reference a variable in the context. The total property comes from the root object, while freeShippingThreshold is supplied into the context by the application.

This approach separates comparison rules from configuration data. One Expression can be reused with contexts that have different thresholds, as long as the data types and access permissions are appropriate.

## Comparing Strings and Ordered Types

Relational operators are not limited to numbers. String and Java types that implement Comparable can be compared according to the natural ordering rules of that type, provided the two operands are compatible.

Example:

~~~java
Boolean lexicalOrder =
        parser.parseExpression("'apple' < 'banana'")
                .getValue(Boolean.class);
~~~

The result is true according to the lexicographical order of String. This comparison is case-sensitive and does not apply natural language rules or locale-specific collation. Therefore, it should not be used to sort person names, accented titles, or multilingual text in the way users expect.

For dates, you can compare objects of the same type such as LocalDate:

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

The deliveryDate property and the deadline variable must be compatible date values. Do not convert dates into arbitrary strings and use character order to replace temporal comparison.

For custom data types, a consistent comparison rule is required, usually via Comparable. If the type does not support an appropriate comparison, convert the data or invoke a controlled business method.

## Comparing with null

Null is not the number 0 or an empty value that can be arbitrarily compared like ordinary numbers. In SpEL, null is considered less than any non-null value in relational comparisons. However, in business conditions, you should check for null explicitly so readers understand the policy for handling missing data.

~~~java
Expression expression = parser.parseExpression(
        "score != null and score >= 80");
~~~

The expression checks that score is not null before comparing it with the threshold 80. When a property can be null, writing it this way makes it clear that only values with data are evaluated against the threshold.

If null has a specific business meaning, such as not yet graded, no price yet, or delivery date not yet determined, you should represent that state explicitly rather than letting null comparison ordering decide the result. With data that can be missing, also verify whether the logical operators and context meet the desired policy.

## Combining Relational Operators with Logical Operators

Comparisons are often combined with **and**, **or**, and **not** to build multi-part conditions:

~~~java
Expression expression = parser.parseExpression(
        "score >= 80 and score <= 100");
~~~

The expression above checks whether score lies in the range from 80 to 100, inclusive of both endpoints.

An age condition can be written:

~~~java
Expression expression = parser.parseExpression(
        "age >= 18 and age < 65");
~~~

The condition is true only when age is at least 18 and less than 65. Choosing **<** or **<=** at the boundary 65 directly expresses the policy of whether that age is included.

For multi-branch expressions, parentheses help show how conditions are grouped:

~~~java
"active == true and (score >= 80 or bonus >= 10)"
~~~

Here active must be true, and either score meets the threshold or bonus meets the threshold. Using parentheses clarifies intent and avoids confusion when reading long expressions.

## Word-Form Operator Names

In addition to symbols, SpEL provides corresponding keywords for the four relational operators:

| Symbol | SpEL keyword |
|---|---|
| **>** | **gt** |
| **<** | **lt** |
| **>=** | **ge** |
| **<=** | **le** |

Example:

~~~java
Expression expression =
        parser.parseExpression("age ge 18 and age lt 65");
~~~

The expression has the same meaning as **age >= 18 and age < 65**. Word-form keywords are especially useful when expressions are embedded in XML, where the **<** and **>** characters have special meaning in markup syntax and may need escaping.

These keywords are SpEL syntax, not Java method names. When reading an expression, you may encounter both symbolic and word forms depending on where the expression is declared.

## Operator Precedence and Parentheses

Arithmetic operations have higher precedence than comparisons. For example, the expression:

~~~java
"price * quantity >= 500"
~~~

will compute price multiplied by quantity first and then compare the result with 500. Use parentheses if you want to clarify how operations are grouped or combine multiple conditions:

~~~java
"(price * quantity) >= minimumOrderValue"
~~~

In business configuration, prefer readable expressions over relying on readers to remember every precedence level. Especially when arithmetic, comparison, and logic appear together, parentheses help reduce misunderstandings.

## Incompatible Data Types and Evaluation Errors

The parser may accept the expression syntax, yet at evaluation time SpEL can still fail if the two operands cannot be compared. Common cases include:

- A property does not exist on the root object.
- A property has a null value while the expression performs an inappropriate operation.
- One side is a number and the other side is a string or an incompatible type.
- A custom type lacks an appropriate comparison rule.
- Data is malformed or has not been converted before being placed into the context.

For example, do not assume that the string **'80'** will always be converted to a number for comparison with an Integer:

~~~java
Expression expression =
        parser.parseExpression("score > '80'");
~~~

If the intent is numeric comparison, convert the input data to a numeric type in Java and place the validated value into the root object or context. That helps the expression accurately reflect a numeric comparison instead of depending on implicit conversion.

Separate parse errors and evaluation errors when handling exceptions:

~~~java
Expression expression;

try {
    expression = parser.parseExpression("score >= #minimumScore");
} catch (ParseException ex) {
    throw new IllegalArgumentException("Invalid expression syntax", ex);
}

try {
    Boolean passed =
            expression.getValue(context, Boolean.class);
} catch (EvaluationException ex) {
    throw new IllegalStateException("Cannot compare values", ex);
}
~~~

ParseException indicates that the string is syntactically invalid. EvaluationException indicates that the expression cannot be executed against the current data or context. When logging, record the expression identifier and error type while avoiding logging the entire object if it contains sensitive information.

## When Should You Use These Operators?

Comparisons in SpEL are suitable for short conditions with clear data types evaluated at a supported Spring integration point, such as:

- Checking whether a value exceeds a configured threshold.
- Determining whether a quantity, score, price, or rate is within a valid range.
- Comparing deadlines, delivery dates, or timestamps.
- Combining a few conditions to enable or disable behavior.
- Declaring simple conditions in annotations supported by Spring or Spring modules.

If a condition has many branches, complex null policies, requires multiple side operations, or needs to explain why an object was rejected, move the decision into a clearly named Java method. SpEL works best when the expression is short and its meaning can be understood directly from its syntax.

## Conclusion

SpEL provides four relational operators **>**, **<**, **>=**, and **<=** to compare compatible values. The first two exclude equality; the latter two include the boundary value. You can use symbols or the **gt**, **lt**, **ge**, **le** keywords when the syntax where the expression is embedded requires the word form.

For predictable results, normalize data types before comparing, handle null according to business policy, and pay attention to floating-point precision. Root objects and variables in EvaluationContext allow changing comparison data without changing the expression string. When conditions become complex, moving logic into Java makes testing and diagnostics easier.
