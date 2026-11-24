# Null, Boolean, Integer, and Real Literals in Spring Expression Language (SpEL)

A literal is a value written directly in a SpEL expression. When the parser parses the expression, literals are recognized and created as corresponding values to be used in comparisons, calculations, conditions, or passed into method calls.

This lesson focuses on four literal groups: null, Boolean (true, false), integers, and real numbers. Understanding the syntax and data types of each group helps avoid confusion between literal values, character strings, and object properties.

## 1. What is a Literal?

A literal is a fixed value represented directly in the expression code. For example:

~~~text
null
true
false
42
0x2A
3.14
1.25e3
~~~

The values above can be used independently or combined with other SpEL components:

~~~text
age >= 18
enabled == true
discount == null
price * 1.08
~~~

The parser parses literals together with the entire expression. When getValue() is called, SpEL evaluates the expression and returns a result of the appropriate type.

Literals differ from root object properties and variables in EvaluationContext:

- **18** is an integer written directly in the expression.
- **age** is usually a property resolved from the root object.
- **#minimumAge** is a variable registered in the EvaluationContext.
- **'18'** is a character string, not an integer.

Correctly distinguishing these forms is the basis for writing accurate conditions and calculations.

## 2. The null Literal

SpEL uses the keyword null to represent a value with no object reference. This keyword is written in lowercase and is not enclosed in quotes.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Object value = parser.parseExpression("null").getValue();

// value == null
~~~

You can request a result type when evaluating the null literal. The result is still null if the requested type is compatible with the null value:

~~~java
String name = parser.parseExpression("null").getValue(String.class);

// name == null
~~~

### 2.1. Comparing with null

The null literal is often used to check whether a property or result is missing a value:

~~~text
email == null
email != null
discount == null or discount == 0
~~~

Example using a root object:

~~~java
public class Customer {
    private final String email;

    public Customer(String email) {
        this.email = email;
    }

    public String getEmail() {
        return email;
    }
}

Customer customer = new Customer(null);

Expression expression = parser.parseExpression("email == null");

Boolean missingEmail =
        expression.getValue(customer, Boolean.class);

// missingEmail == true
~~~

The expression email == null reads the email property from the root object and compares the result with the null literal. If email has a string value, the condition will be false.

### 2.2. Common Points of Confusion

- null is the null literal; 'null' is a four-character string.
- The keyword is written in lowercase. NULL is not SpEL's way of writing the null literal and may be interpreted as a property name or identifier.
- Avoid calling methods or accessing further properties on a null result if the expression does not have proper null handling. Dereferencing null can cause an error during evaluation.
- Comparing with null only checks for the presence of a value. It does not automatically check for an empty string '' or a whitespace-only string.

If you need to distinguish between null, an empty string, and a non-empty string, write a separate condition for each case.

## 3. Boolean Literals: true and false

SpEL represents the two logical values with lowercase keywords:

~~~text
true
false
~~~

They correspond to java.lang.Boolean.TRUE and java.lang.Boolean.FALSE.

~~~java
Boolean active = parser.parseExpression("true")
        .getValue(Boolean.class);

Boolean disabled = parser.parseExpression("false")
        .getValue(Boolean.class);
~~~

Boolean literals can be used in comparisons or as operands of logical expressions:

~~~text
enabled == true
enabled == false
enabled and retryCount < 3
enabled or administrator
not enabled
~~~

SpEL supports keyword-based logical operators such as and, or, not and corresponding symbol-based ones such as &&, ||, !.

Example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression rule = parser.parseExpression("true and (false or true)");

Boolean result = rule.getValue(Boolean.class);

// result == true
~~~

In the example, the parser builds a logical expression from Boolean literals and operators. getValue(Boolean.class) returns a Boolean.

### 3.1. Boolean Literals and Strings

Quotes change the meaning of a value:

| Expression | Meaning |
|---|---|
| true | Boolean value true |
| false | Boolean value false |
| 'true' | Character string "true" |
| 'false' | Character string "false" |

Similar to null, True or FALSE is not the standard SpEL way to write a Boolean keyword. Use exact lowercase.

Do not compare a Boolean property with the string 'true'. Use a Boolean literal without quotes or convert input data at an appropriate boundary before evaluating the expression.

## 4. Integer Literals

Integers are written using decimal digits. SpEL also supports writing hexadecimal integers with the 0x prefix.

~~~text
0
7
42
2026
0x2A
~~~

0x2A represents the same numeric value as 42 in decimal.

Example:

~~~java
Integer decimal = parser.parseExpression("42")
        .getValue(Integer.class);

Integer hexadecimal = parser.parseExpression("0x2A")
        .getValue(Integer.class);

// decimal == 42
// hexadecimal == 42
~~~

Negative integers are created using the unary minus operator before the literal:

~~~text
-1
-42
-0x2A
~~~

The minus sign is an expression operator; it does not change the rules for writing the integer literal part.

### 4.1. Integer Types

SpEL determines the integer type based on the value and the specified type suffix. For typical values, the appropriate integer type is usually Integer. You can use the L or l suffix to denote a Long literal:

~~~java
Integer count = parser.parseExpression("42")
        .getValue(Integer.class);

Long population = parser.parseExpression("9000000000L")
        .getValue(Long.class);
~~~

Use the Long suffix when the value exceeds the Integer range or when you want to explicitly express a long integer type in the expression. If the application needs a stable result type, specify the type via the getValue(Class<T>) overload rather than relying on manual casting after receiving an Object.

Very large integers need to be considered according to the numeric types supported by the expression and the application. Do not assume that a literal can be assigned directly to every Java integer type without appropriate conversion.

### 4.2. Decimal and Hexadecimal Systems

SpEL allows using hexadecimal numbers when you need to represent values commonly encountered in low-level programming, bit masks, or color codes:

~~~text
0x10
0xFF
0x7FFFFFFF
~~~

For example, 0xFF equals 255 in decimal.

~~~java
Integer mask = parser.parseExpression("0xFF")
        .getValue(Integer.class);
~~~

Use the 0x prefix and valid hexadecimal digits from 0 to 9, A to F, or a to f. If the expression contains a value with invalid numeric syntax, the parser will report a parse error.

## 5. Real Number Literals

Real numbers have a fractional part and can use scientific notation. A dot is used as the separator between the integer part and the fractional part:

~~~text
0.5
3.14
10.0
1.25e3
6.02E23
~~~

1.25e3 represents 1.25 times 10 to the power of 3, which is 1250. Scientific notation is useful for very large or very small values.

Example:

~~~java
Double ratio = parser.parseExpression("0.75")
        .getValue(Double.class);

Double distance = parser.parseExpression("1.25e3")
        .getValue(Double.class);
~~~

Real number literals default to being represented as Double. A suffix can be used to specify a particular real number type.

### 5.1. Real Number Type Suffixes

Common suffixes:

| Suffix | Numeric Type | Example |
|---|---|---|
| F or f | Float | 3.14F |
| D or d | Double | 3.14D |
| M or m | BigDecimal | 19.99M |

Example:

~~~java
Float temperature = parser.parseExpression("36.5F")
        .getValue(Float.class);

Double average = parser.parseExpression("3.14159D")
        .getValue(Double.class);

BigDecimal price = parser.parseExpression("19.99M")
        .getValue(BigDecimal.class);
~~~

Suffixes help the expression explicitly indicate the numeric type to use. BigDecimal is especially useful when representing decimal values that require precision control, such as monetary amounts or business rates.

### 5.2. Precision of Real Numbers

Float and Double are binary floating-point types. Some decimal fractions, such as 0.1, do not have an exact finite binary representation. Therefore, calculations can produce small rounding errors.

When you need to preserve a more exact decimal representation for financial business logic or calculations requiring clear rounding rules, consider using a BigDecimal literal with the M suffix:

~~~java
BigDecimal amount = parser.parseExpression("1250.75M")
        .getValue(BigDecimal.class);
~~~

Using BigDecimal does not automatically determine the rounding policy for the entire business logic. The application still needs to choose the scale, rounding mode, and how to handle results as required.

### 5.3. Negative Real Numbers and Exponents

Negative numbers use the unary minus operator:

~~~text
-3.14
-0.5F
-1.25e-4
~~~

The exponent part can carry a positive or negative sign:

~~~text
1.2e3
1.2e+3
1.2e-3
~~~

Check the dot, the letter e or E, the sign of the exponent, and the type suffix when writing literals. A small syntax error can cause the parser to reject the expression.

## 6. Combining Literals in an Expression

Literals are often used together with properties, variables, and operators. For example:

~~~text
age >= 18
price > 0.0
enabled == true and retryCount < 3
discount == null or discount == 0.0
temperature >= 36.0 and temperature <= 37.5
~~~

An example using data from a root object:

~~~java
public class Order {
    private final BigDecimal total;
    private final Boolean approved;
    private final String coupon;

    public Order(BigDecimal total, Boolean approved, String coupon) {
        this.total = total;
        this.approved = approved;
        this.coupon = coupon;
    }

    public BigDecimal getTotal() {
        return total;
    }

    public Boolean getApproved() {
        return approved;
    }

    public String getCoupon() {
        return coupon;
    }
}

Order order = new Order(new BigDecimal("125.50"), true, null);

ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
        "approved == true and total >= 100M and coupon == null"
);

Boolean eligible = expression.getValue(order, Boolean.class);

// eligible == true
~~~

In the expression above:

- true is a Boolean literal.
- 100M is a BigDecimal literal.
- null is the null literal.
- approved, total, and coupon are properties resolved from the root object order.

The example shows that literal groups can be combined directly with business domain data without needing to create an intermediate variable for each fixed value.

## 7. Getting Values and Java Types from Literals

parseExpression(...) returns an Expression. Calling getValue() evaluates the literal and returns the result. When a specific type is needed, getValue(Class<T>) can be used:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Object rawBoolean = parser.parseExpression("true").getValue();
Boolean booleanValue = parser.parseExpression("true")
        .getValue(Boolean.class);

Object rawInteger = parser.parseExpression("42").getValue();
Integer integerValue = parser.parseExpression("42")
        .getValue(Integer.class);

Double realValue = parser.parseExpression("3.14")
        .getValue(Double.class);

Object nullValue = parser.parseExpression("null").getValue();
~~~

The result of getValue() has a declared type of Object, but the actual object depends on the literal. When using the typed overload, SpEL uses the EvaluationContext's type conversion mechanism if needed and if a suitable conversion exists.

Do not confuse requesting a result type with changing the literal syntax. For example, the L suffix denotes a Long literal, whereas getValue(Long.class) requests that the result be provided as a Long.

If the result cannot be converted to the requested type, evaluation may throw an EvaluationException. Choose a type that matches the value and the application's data contract.

## 8. Common Mistakes

| Syntax or Situation | Problem | How to Handle |
|---|---|---|
| 'null' | This is a string, not null. | Use null if you need a null value. |
| 'true' | This is a string, not a Boolean. | Use true or false. |
| True, FALSE | Incorrect spelling of standard Boolean keywords. | Use lowercase. |
| '42' | This is a character string, not an integer. | Use 42 if you need a number. |
| '3.14' | This is a character string, not a real number. | Use 3.14 or a literal with a type suffix. |
| Using a Long literal for an Integer variable without checking conversion | It may not match the target type. | Choose a consistent numeric type or request an appropriate result type. |
| Using Double for monetary calculations requiring decimal precision | Floating-point errors may occur. | Consider BigDecimal with the M suffix. |
| Accessing further properties from a null result | An evaluation error may occur. | Check for null before accessing or design an expression with appropriate null handling. |

### 8.1. Distinguishing Syntax Errors and Evaluation Errors

A syntax error occurs when a literal string is not accepted by the parser, such as an invalid suffix or numeric notation. An evaluation error can occur when the expression is valid but the data or result type is incompatible, for example accessing a property on null or being unable to convert the result.

~~~java
try {
    Expression expression = parser.parseExpression("3.14F");
    Float value = expression.getValue(Float.class);
} catch (ParseException ex) {
    // Handle invalid SpEL syntax.
} catch (EvaluationException ex) {
    // Handle errors during evaluation or result conversion.
}
~~~

When investigating an error, determine whether it occurs at parseExpression(...) or getValue(...), then check the literal syntax, data type, context, and requested result type.

## 9. Usage Rules in Applications

1. Write null, true, and false in lowercase, without quotes, when the corresponding value is needed.
2. Use single quotes when you actually want a string. Quotes change the type and meaning of a literal.
3. Use the L suffix for Long integers when you need to express the type explicitly.
4. Use the F or D suffix when you need to specify Float or Double.
5. Consider the M suffix for BigDecimal in decimal calculations requiring precision.
6. Use 0x for hexadecimal integers and use e or E notation for real numbers in scientific notation.
7. Choose an explicit result type via getValue(Class<T>) when Java code needs a specific type.
8. Check for null before using a result as an object with properties or methods.
9. Do not treat input data as a safe literal just because it looks like a number or keyword. Control how expression strings are concatenated and which data sources are allowed to be passed into the parser.

## 10. Key Takeaways

- null represents the null value; true and false represent Boolean.
- Integers can be written in decimal or hexadecimal with the 0x prefix; the L suffix specifies Long.
- Real numbers support fractional parts and scientific notation; the default is usually Double.
- The suffixes F, D, and M denote Float, Double, and BigDecimal, respectively.
- Single quotes turn content into a string; 'true' is not the same as true.
- Literals can be combined with properties, variables, and operators in the same SpEL expression.
- Use an explicit result type when a clear data contract is needed and handle null cases separately.
