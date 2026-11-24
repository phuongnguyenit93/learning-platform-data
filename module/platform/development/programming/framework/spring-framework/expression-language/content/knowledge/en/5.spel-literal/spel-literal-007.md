# Literals Do Not Change with Input Data

In Spring Expression Language (SpEL), a **literal** is a value written directly in the expression string, such as a number, a character string, a Boolean value, or **null**. A literal represents a fixed value right in the expression. When the application evaluates the expression against different root objects or input data, the literal itself retains the declared value.

This characteristic enables expressions to use constants for comparisons, calculations, creating labels, or choosing results. However, distinguish the literal's value from the result of the entire expression: a literal does not change, yet the result of an expression containing a literal can still vary according to input data.

## What Is a Literal?

A literal is one of the fundamental components of SpEL syntax. It does not need to fetch data from a root object, variable, or bean. The parser reads the value written directly in the string and makes it part of the expression.

For example, the following expressions contain literals:

| SpEL Expression | Value |
|---|---|
| **42** | Integer 42 |
| **3.14** | Real number 3.14 |
| **'Spring'** | Character string Spring |
| **true** | Boolean value true |
| **false** | Boolean value false |
| **null** | The null value |

If the expression **'Spring'** is parsed, the result of the expression is the string Spring. The root object does not need to contain a property named Spring and does not change the content of this literal.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression("'Spring'");

String value = expression.getValue(String.class);
~~~

In the example above, the parser receives an expression string containing a string literal. When calling **getValue(String.class)**, SpEL returns the literal's value. No external input data is used to produce the string Spring.

## Common Literal Groups

### String Literal

A string literal is enclosed in single quotes:

~~~java
Expression expression =
        parser.parseExpression("'Hello Spring'");

String message = expression.getValue(String.class);
~~~

The result is the string **Hello Spring**. The string content is determined right in the expression and does not automatically change when the root object changes.

If the content needs to contain a single quote, the inner single quote can be represented by repeating it:

~~~java
Expression expression =
        parser.parseExpression("'It''s Spring'");
~~~

This string literal represents the content **It's Spring**. The outer single quotes define the boundary of the SpEL string literal; the escape rule helps the parser distinguish quotes inside the content from the closing quote of the string.

### Numeric Literal

SpEL supports integer and real number literals. Example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Integer count = parser.parseExpression("25")
        .getValue(Integer.class);

Double rate = parser.parseExpression("0.85")
        .getValue(Double.class);
~~~

The values 25 and 0.85 are written directly in the expression. They do not depend on properties of the object being evaluated.

Numeric literals can be used as operands in calculations:

~~~java
Integer result =
        parser.parseExpression("10 * 5 + 2")
                .getValue(Integer.class);
~~~

The result is 52. The numbers 10, 5, and 2 remain fixed values; the operations combine them to produce another value.

SpEL also supports hexadecimal numbers and scientific notation for real numbers. When needing to represent a specific numeric type, numeric suffixes supported by SpEL can be used, such as suffixes for Long or BigDecimal. The actual result type must comply with numeric parsing rules and the context's type conversion.

### Boolean Literal

The two Boolean literals are **true** and **false**:

~~~java
Boolean enabled =
        parser.parseExpression("true").getValue(Boolean.class);

Boolean disabled =
        parser.parseExpression("false").getValue(Boolean.class);
~~~

They are useful when an expression needs a fixed flag or a conditional branch that is always true/false according to the expression's configuration. Boolean literals do not automatically read an enabled/disabled state from an object.

### Null Literal

**null** represents an empty value:

~~~java
Object value =
        parser.parseExpression("null").getValue();
~~~

This literal can be used in comparison or conditional expressions:

~~~java
Boolean missing =
        parser.parseExpression("null == null")
                .getValue(Boolean.class);
~~~

The result of the comparison above is true. When using null in an expression with properties or methods, note that further accessing a null value may cause an evaluation error depending on the operation and parser configuration.

## Literals Do Not Depend on the Root Object

The root object is the object SpEL uses when the expression needs to read properties or invoke behavior on that data. An expression containing only literals does not need a root object to determine its value.

For example, the same Expression can be evaluated with two different objects:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("'ACTIVE'");

String first = expression.getValue(userOne, String.class);
String second = expression.getValue(userTwo, String.class);
~~~

Both evaluations return the string **ACTIVE**. The root objects do not participate in the expression so they do not affect the literal's value.

This is also true for expressions containing only operations on literals:

~~~java
Expression expression =
        parser.parseExpression("100 + 50");

Integer first = expression.getValue(orderOne, Integer.class);
Integer second = expression.getValue(orderTwo, Integer.class);
~~~

Both results equal 150 because the expression does not reference data from order. Passing a root object does not turn the numbers 100 and 50 into dynamic values.

## Literals in Expressions Combined with Input Data

In real applications, literals often appear together with properties, variables, or method calls. In that case, the literal remains fixed while the entire expression can depend on input data.

Example:

~~~java
Expression expression =
        parser.parseExpression("price >= 100");

Boolean first = expression.getValue(
        new StandardEvaluationContext(productA), Boolean.class);

Boolean second = expression.getValue(
        new StandardEvaluationContext(productB), Boolean.class);
~~~

In this expression, **100** is a fixed numeric literal. The **price** property is read from the root object. If productA has a price of 120 and productB has a price of 80, the results are true and false, respectively.

Therefore, the statement "literals do not change with input data" refers to the value of the literal component, and does not mean every expression containing a literal returns an invariant result.

Another example is a conditional expression:

~~~java
Expression expression = parser.parseExpression(
        "status == 'PAID' ? 'Ready' : 'Waiting'");
~~~

The strings **'PAID'**, **'Ready'**, and **'Waiting'** are literals. The **status** property is retrieved from the object. The result can be Ready or Waiting depending on the object's status, while the content of the three literals does not change.

## Distinguishing Literals from Properties and Variables

When reading a SpEL expression, recognize which values are written as fixed and which values are retrieved from the evaluation environment:

| Component | Example | Value Source |
|---|---|---|
| Literal | **100**, **'PAID'**, **true** | Written directly in the expression |
| Root object property | **price**, **status** | Property of the root object |
| Variable | **#minimumPrice** | Variable set in EvaluationContext |
| Bean reference | **@pricingService** | Bean resolved with context support |

For example, the expression **price >= #minimumPrice** has two parts retrieving values from the environment: the **price** property comes from the root object and the **#minimumPrice** variable comes from the evaluation context. If replaced with **price >= 100**, the threshold 100 is a fixed literal.

This distinction is useful when needing to understand why an expression produces changing results. If you want the comparison threshold to vary by configuration or per request, use a property, variable, or an appropriate configuration mechanism rather than hardcoding a literal in the string.

## Using Literals as Default Values and Fallback Branches

Literals are often used in conditional operators to provide a fallback result:

~~~java
Expression expression = parser.parseExpression(
        "displayName != null ? displayName : 'Unknown'");
~~~

The string **'Unknown'** is a literal. If the displayName property has a value, the expression returns that property; otherwise, the expression returns the literal Unknown.

Literals can be used in similar comparisons, logical expressions, and calculations:

~~~java
"quantity > 0"
"status == 'ACTIVE'"
"enabled == true"
"price * 1.1"
~~~

In the examples above, the numbers, string, and Boolean are written directly. The property parts are still retrieved from the root object during evaluation.

## Literals and Application Configuration

A literal is a value inside the expression content. If you want the value to change by deployment environment, operator, or runtime configuration, use a configuration source instead of treating a literal as a placeholder.

For example, a fixed threshold:

~~~java
@Value("#{10}")
private int retryLimit;
~~~

The value 10 is a literal in the SpEL expression. If you want to retrieve the threshold from a configuration file, a property placeholder is usually more suitable:

~~~java
@Value("${app.retry-limit:10}")
private int retryLimit;
~~~

In the second example, Spring retrieves the value from the **app.retry-limit** property, using 10 as the default value if the property has not been declared. The number 10 in the placeholder syntax is the default value of the configuration mechanism, not a dynamic variable that automatically changes inside a SpEL literal.

Configuration sources can be combined with SpEL if calculations on the injected value are needed. The key is choosing the right mechanism according to intent: literals for constants written directly, properties for configuration values, variables for data passed into the evaluation context, and property access for root object data.

## Do Literals Change After Parsing?

A literal is represented in the Expression structure created from the parsed string. When re-evaluating the same expression, the literal still represents the same value. Changing the root object or variables does not modify the literal content in the expression.

If the application wants to change the value, it can create or parse another expression, or pass the changing value into a property, variable, or a dynamic component of the context. Do not expect modifying a field of the root object to automatically update a literal written directly in the string.

This also means that when expressions are cached by string, each different expression string represents different configuration content. If configuration changes, the application needs to manage reloading or replacing the Expression according to its configuration lifecycle.

## Notes When Receiving Literals from External Input

A literal written in trusted source code or configuration is usually easy to understand and stable. However, if the application takes the entire expression string from users, do not assume the expression only contains a literal just because the UI only asks to enter one value.

The input string may contain property access, method calls, operators, or other syntax. The parser will interpret it according to the full SpEL language. If you only want users to enter a text value or a number, validate and convert the data according to the corresponding type instead of evaluating an arbitrary expression string.

When a use case truly needs to allow expressions, restrict the evaluation context and root object, expose only necessary data, and handle parse and evaluation errors. Limiting string length is also useful to avoid overly large or unnecessary expressions.

## Conclusion

Literals are values written directly in a SpEL expression, including strings, numbers, Booleans, and null. A literal's value does not depend on the root object or variables in the evaluation context. When a literal is combined with properties or variables, the result of the entire expression can still vary with input data.

Use literals for intentional fixed values such as thresholds, labels, or default values. If a value needs to vary by environment or per request, place it in a configuration source, root object, or evaluation context. This distinction makes expressions easier to read, more predictable, and easier to maintain.
