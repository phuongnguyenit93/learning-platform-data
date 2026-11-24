# Integers, Floating-Point Numbers, and Calculation Results

In Spring Expression Language (SpEL), arithmetic operations are performed on numeric values that an expression receives from literals, the root object, or variables in EvaluationContext. The result depends on the types of the operands and the operation being used. Therefore, two formulas that look the same can yield different results if one expression uses integers while another uses floating-point numbers or BigDecimal.

When writing arithmetic expressions, clearly determine the input data types, the expected result type, and how precision is handled. This is especially important for division, monetary calculations, and values that may exceed the limits of ordinary integer types.

## Types of Numeric Values in SpEL

SpEL supports integer and floating-point literals. Some common forms:

| Literal | Meaning |
|---|---|
| **25** | Integer |
| **25L** | Long integer |
| **3.5** | Floating-point number, usually inferred as Double |
| **3.5F** | Float floating-point number |
| **3.5D** | Double floating-point number |

Example parsing literals directly:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Integer count = parser.parseExpression("25")
        .getValue(Integer.class);

Long largeCount = parser.parseExpression("25L")
        .getValue(Long.class);

Double rate = parser.parseExpression("3.5")
        .getValue(Double.class);

Float factor = parser.parseExpression("3.5F")
        .getValue(Float.class);
~~~

A literal is a value written directly inside the expression string. The literal's type participates in the operation and can affect the result type. Do not look solely at the target type in **getValue(Integer.class)** or **getValue(Double.class)** and assume that was the type the calculation used from the start.

## Arithmetic Operators

SpEL provides common arithmetic operators:

| Operator | Meaning | Example |
|---|---|---|
| **+** | Addition | **10 + 5** |
| **-** | Subtraction | **10 - 5** |
| ***** | Multiplication | **10 * 5** |
| **/** | Division | **10 / 5** |
| **%** | Remainder division | **10 % 3** |
| **^** | Exponentiation | **2 ^ 3** |

The **+** operator can also be used to concatenate strings when an operand is a string. Therefore, pay attention to the actual data types of both sides before interpreting an expression as arithmetic addition.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Integer sum = parser.parseExpression("10 + 5")
        .getValue(Integer.class);

Integer difference = parser.parseExpression("10 - 5")
        .getValue(Integer.class);

Integer product = parser.parseExpression("10 * 5")
        .getValue(Integer.class);

Integer quotient = parser.parseExpression("10 / 5")
        .getValue(Integer.class);

Integer remainder = parser.parseExpression("10 % 3")
        .getValue(Integer.class);

Integer power = parser.parseExpression("2 ^ 3")
        .getValue(Integer.class);
~~~

The results are 15, 5, 50, 2, 1, and 8 respectively. In SpEL, **^** is the exponentiation operator. Do not confuse it with the XOR operator in some other programming languages.

## Order of Operations

Arithmetic expressions can contain multiple operators. SpEL applies operator precedence; multiplication, division, and remainder division are executed before addition and subtraction. Parentheses can be used to clearly express which group of operations should execute first.

~~~java
Integer first = parser.parseExpression("10 + 5 * 2")
        .getValue(Integer.class);

Integer second = parser.parseExpression("(10 + 5) * 2")
        .getValue(Integer.class);
~~~

The first result is 20 because multiplication is performed first. The second result is 30 because parentheses require adding first and then multiplying.

In business expressions, parentheses should be used when a formula has multiple steps or when the order of operations could cause confusion. This helps readers recognize the intent without having to memorize all precedence rules themselves.

## Integers and Division with a Fractional Part

One point to note is that operand types affect division. When both operands are integers, integer division produces an integer result and the fractional part is discarded:

~~~java
Integer integerResult =
        parser.parseExpression("7 / 2")
                .getValue(Integer.class);
~~~

The result is 3. If a fractional part is needed, at least one operand must be a floating-point number or an appropriate decimal type:

~~~java
Double decimalResult =
        parser.parseExpression("7.0 / 2")
                .getValue(Double.class);
~~~

The result is 3.5.

Requesting **getValue(Double.class)** specifies the type the application wants to receive. It does not change the integer division that occurred beforehand. If **7 / 2** is evaluated as integer division and the result is then converted to Double, the result is still 3.0, not 3.5.

Therefore, choose operand types right in the expression or from the data passed into the context. This avoids common bugs when calculating ratios, percentages, unit prices, or averages.

## Result Types and Type Conversion

The result type of an operation depends on operand types and the arithmetic rules SpEL applies. For common numeric types, this can be summarized generally as:

- Two integer operands normally produce a result according to integer arithmetic.
- When Long is present, integer operations can be promoted to Long.
- When Float or Double is present, the operation uses the corresponding floating-point type according to SpEL's rules.
- When BigInteger or BigDecimal is used, SpEL has dedicated handling branches for these numeric types.

This is why data types should be kept intentional rather than mixing multiple numeric types arbitrarily. When an expression combines different types, check the actual result type and conversion rules in the Spring version being used.

A result type can be requested when calling Expression:

~~~java
Expression expression = parser.parseExpression("10 + 5");

Integer integerValue = expression.getValue(Integer.class);
Number numberValue = expression.getValue(Number.class);
Object objectValue = expression.getValue();
~~~

These overloads allow the application to receive the result in the desired type. SpEL can use the evaluation context's type conversion mechanism when appropriate. However, type conversion occurring when retrieving the result is not the same as changing operand types before the operation is performed.

If the result type is incompatible and no suitable conversion exists, evaluation may throw an error.

## Large Integers: Long and BigInteger

The Integer type has value limits. If a calculation may exceed those limits, choose a wider type such as Long or use BigInteger when magnitude goes far beyond primitive types.

Example with Long literals:

~~~java
Long result = parser.parseExpression("9000000000L + 100L")
        .getValue(Long.class);
~~~

The **L** suffix helps the expression clearly indicate a Long literal. If data comes from objects or variables, ensure input values also have appropriate types.

With **BigInteger**, a BigInteger value can be passed through the root object or a variable in the evaluation context and operations performed on it. This approach is suitable for integers of arbitrary magnitude, without a fractional part.

Do not assume every calculation automatically becomes BigInteger just because the result might be large. Choose the data type from the inputs and verify the return type.

## Floating-Point Numbers and Representation Errors

Float and Double represent real numbers using binary floating point. Many decimal numbers cannot be represented exactly in finite binary form. Thus, a seemingly simple calculation can produce an approximate result rather than a strictly exact one.

For example, adding 0.1 and 0.2 using Double can display a result near 0.30000000000000004 instead of exact 0.3:

~~~java
Double result =
        parser.parseExpression("0.1 + 0.2")
                .getValue(Double.class);
~~~

This is a characteristic of floating-point representation, not a SpEL-specific bug. For scientific calculations, graphics, or data where small errors are acceptable, Float/Double are usually suitable. For currency or decimals requiring exact control, use **BigDecimal**.

## Using BigDecimal for Decimals Requiring Precision

BigDecimal represents decimal numbers with precision depending on value and usage. BigDecimal values can be placed into the root object or evaluation context and used with SpEL operators.

Example, an order having a BigDecimal unit price:

~~~java
public class Order {
    private final BigDecimal unitPrice;
    private final BigDecimal quantity;

    public Order(BigDecimal unitPrice, BigDecimal quantity) {
        this.unitPrice = unitPrice;
        this.quantity = quantity;
    }

    public BigDecimal getUnitPrice() {
        return unitPrice;
    }

    public BigDecimal getQuantity() {
        return quantity;
    }
}
~~~

~~~java
Order order = new Order(
        new BigDecimal("19.90"),
        new BigDecimal("3"));

Expression expression =
        parser.parseExpression("unitPrice * quantity");

BigDecimal total =
        expression.getValue(order, BigDecimal.class);
~~~

The result is a BigDecimal corresponding to 59.70. Constructing BigDecimal from a string such as **new BigDecimal("19.90")** avoids introducing Double errors from the start.

If BigDecimal division is needed, explicitly define rounding rules suitable for business logic. Some divisions produce repeating non-terminating decimals; the system must specify scale and rounding mode at the right business-logic location instead of leaving rounding as an unstated assumption.

## Using BigDecimal Variables in Calculations

A BigDecimal factor can be passed into EvaluationContext so an expression uses it as an operand:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(order);

context.setVariable(
        "taxRate",
        new BigDecimal("0.08"));

Expression expression =
        parser.parseExpression(
                "unitPrice * quantity * (1 + #taxRate)");

BigDecimal totalWithTax =
        expression.getValue(context, BigDecimal.class);
~~~

Here, **#taxRate** is an application-supplied variable, while the number **1** is an integer literal. For financial expressions, keep numeric types consistent across operands and check the result type in the SpEL version in use. If full control over scale and rounding mode is desired, perform the corresponding calculation step in Java using the BigDecimal API.

## Division, Remainder, and Division by Zero

The **/** operator performs division; **%** takes the remainder. Both require operands suited to the operation. When the denominator is 0, division or remainder division can throw an evaluation error.

~~~java
Integer quotient =
        parser.parseExpression("17 / 5")
                .getValue(Integer.class);

Integer remainder =
        parser.parseExpression("17 % 5")
                .getValue(Integer.class);
~~~

With integer division, the result is 3 and the remainder is 2. If a ratio of 3.4 is needed, use floating-point operands or an appropriate decimal type.

Input data should be checked beforehand if the denominator can be 0. Do not rely on catching exceptions on every evaluation to replace business data validation rules.

## When Expressions Read Numbers from the Root Object or Variables

Numeric literals are only one source of operands. In applications, calculations often read numbers from object properties or variables:

~~~java
public class Cart {
    private final int quantity;
    private final BigDecimal unitPrice;

    public Cart(int quantity, BigDecimal unitPrice) {
        this.quantity = quantity;
        this.unitPrice = unitPrice;
    }

    public int getQuantity() {
        return quantity;
    }

    public BigDecimal getUnitPrice() {
        return unitPrice;
    }
}
~~~

~~~java
Cart cart = new Cart(4, new BigDecimal("12.50"));

Expression expression =
        parser.parseExpression("quantity * unitPrice");

BigDecimal amount =
        expression.getValue(cart, BigDecimal.class);
~~~

The expression reads two properties from the root object. The type of the **quantity** property is int and **unitPrice** is BigDecimal. SpEL performs the operation according to the operand types and related conversion mechanisms.

If the application receives data from JSON, a database, or a form, define field types right at the data conversion layer. A numeric string not yet converted to Number does not necessarily participate in calculations as a number; depending on operator and type, the plus sign can also be used for string concatenation.

## Distinguishing Numeric Addition from String Concatenation

The **+** operator can add two numeric values or concatenate strings. Example:

~~~java
String message =
        parser.parseExpression("'Order ' + 'A102'")
                .getValue(String.class);

Integer total =
        parser.parseExpression("10 + 20")
                .getValue(Integer.class);
~~~

The first expression produces the string **Order A102**; the second expression performs arithmetic addition and returns 30.

When an operand is a String, examine how SpEL handles string concatenation. If the goal is arithmetic, ensure both operands are appropriate numeric types. This is especially important when data is read from sources with inconsistent types.

## Type Checking and Error Handling

An arithmetic expression can parse successfully yet fail to evaluate on actual data. Common situations include:

- A property does not exist or has a null value where calculation is needed.
- An operand is not a compatible numeric type.
- Dividing by 0 or performing an invalid operation.
- Conversion to the requested result type is not supported.
- A value exceeds the bounds of the numeric type in use.

Parse errors and evaluation errors can be separated:

~~~java
Expression expression;

try {
    expression = parser.parseExpression("unitPrice * quantity");
} catch (ParseException ex) {
    throw new IllegalArgumentException("Invalid expression syntax", ex);
}

try {
    BigDecimal amount =
            expression.getValue(cart, BigDecimal.class);
} catch (EvaluationException ex) {
    throw new IllegalStateException("Cannot evaluate arithmetic expression", ex);
}
~~~

ParseException indicates an expression string has invalid syntax. EvaluationException indicates the expression cannot be evaluated in the current context or on the current data. When logging, record the expression identifier and error type along with necessary business information, avoiding logging the entire object if it contains sensitive data.

## Conclusion

SpEL supports addition, subtraction, multiplication, division, remainder division, and exponentiation on numeric operands. Operand types affect how calculations work and the result type; integer division can discard the fractional part, while Float/Double have inherent representation errors.

Choose appropriate numeric types right from the data source: Integer or Long for integers within bounds, BigInteger for very large integers, Float/Double for floating-point calculations, and BigDecimal for decimals needing precision control. For currency, explicitly define scale and rounding rules. When expressions combine literals, properties, and variables, ensure operands have compatible types so results are predictable and easy to maintain.
