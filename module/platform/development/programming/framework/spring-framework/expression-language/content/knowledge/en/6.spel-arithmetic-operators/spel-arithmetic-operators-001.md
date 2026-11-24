# Addition, Subtraction, Multiplication, and Division in SpEL

## 1. Overview of Arithmetic Operators

Spring Expression Language (SpEL) supports arithmetic operations directly inside expressions. The basic operators include:

| Operator | Name | Example | Result |
|---|---|---|---|
| `+` | Addition | `12 + 8` | `20` |
| `-` | Subtraction | `12 - 8` | `4` |
| `*` | Multiplication | `12 * 8` | `96` |
| `/` | Division | `12.0 / 8.0` | `1.5` |
| `%` | Modulo (remainder) | `17 % 5` | `2` |
| `^` | Exponentiation | `2 ^ 3` | `8` |

SpEL also supports unary plus and unary minus signs to represent positive or negative numbers, such as `+5` and `-5`.

Expressions can be evaluated directly using a parser:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Integer sum = parser.parseExpression("12 + 8").getValue(Integer.class);
Integer difference = parser.parseExpression("12 - 8").getValue(Integer.class);
Integer product = parser.parseExpression("12 * 8").getValue(Integer.class);
Double quotient = parser.parseExpression("12.0 / 8.0").getValue(Double.class);

System.out.println(sum);        // 20
System.out.println(difference); // 4
System.out.println(product);    // 96
System.out.println(quotient);   // 1.5
~~~

Each call to `parseExpression` has the parser create an `Expression`; `getValue` then performs the calculation and returns the result.

## 2. Addition (+)

The `+` operator adds two numeric values:

~~~java
Expression expression = parser.parseExpression("10 + 25");
Integer result = expression.getValue(Integer.class);

System.out.println(result); // 35
~~~

Decimal literals can be added:

~~~java
Double result = parser.parseExpression("10.5 + 2.25")
        .getValue(Double.class);

System.out.println(result); // 12.75
~~~

In SpEL, `+` can also concatenate strings. If one operand is a string, the operator can produce a string result:

~~~java
Expression expression = parser.parseExpression("'Order-' + 42");
String orderLabel = expression.getValue(String.class);

System.out.println(orderLabel); // Order-42
~~~

Therefore, check the data types of the operands before using `+`: in one expression it can mean arithmetic addition, while in another expression it can mean string concatenation.

## 3. Subtraction (-)

The `-` operator subtracts the right operand from the left operand:

~~~java
Integer remaining = parser.parseExpression("100 - 35")
        .getValue(Integer.class);

System.out.println(remaining); // 65
~~~

The unary minus sign negates the sign of a value:

~~~java
Integer negative = parser.parseExpression("-15")
        .getValue(Integer.class);

Integer positive = parser.parseExpression("-(-15)")
        .getValue(Integer.class);

System.out.println(negative); // -15
System.out.println(positive); // 15
~~~

Subtraction can be used to calculate the difference between values taken from the root object or variables in the evaluation context:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("total", 500);
context.setVariable("discount", 75);

Expression expression = parser.parseExpression("#total - #discount");
Integer payable = expression.getValue(context, Integer.class);

System.out.println(payable); // 425
~~~

Passing data through variables helps reuse the same expression with multiple sets of values without having to recreate the expression source string.

## 4. Multiplication (*)

The `*` operator multiplies two operands:

~~~java
Integer area = parser.parseExpression("12 * 8")
        .getValue(Integer.class);

System.out.println(area); // 96
~~~

Example calculating the total amount from quantity and unit price:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("quantity", 4);
context.setVariable("unitPrice", 25);

Expression expression =
        parser.parseExpression("#quantity * #unitPrice");

Integer total = expression.getValue(context, Integer.class);
System.out.println(total); // 100
~~~

An integer can be multiplied by a decimal number:

~~~java
Double extendedPrice = parser.parseExpression("3 * 19.95")
        .getValue(Double.class);

System.out.println(extendedPrice); // 59.849999999999994 (may have binary precision error)
~~~

For monetary data or calculations requiring decimal precision, choose an appropriate numeric type such as `BigDecimal` instead of relying on `double` for completely exact results.

## 5. Division (/)

The `/` operator divides the left operand by the right operand:

~~~java
Double result = parser.parseExpression("15.0 / 4.0")
        .getValue(Double.class);

System.out.println(result); // 3.75
~~~

When a fractional part is needed, use operands with an appropriate decimal type. The literal type and the type of the input data affect both the result type and the precision of the calculation.

SpEL supports `BigDecimal` literals with the `M` suffix. They can be used in division or monetary calculations:

~~~java
BigDecimal amount = parser.parseExpression("15.00M / 4.00M")
        .getValue(BigDecimal.class);
~~~

Division by zero has no valid result and will throw an error during evaluation. If the denominator comes from dynamic data, check that value beforehand or handle the exception at an appropriate boundary.

## 6. Remainder Division (%)

The `%` operator returns the remainder of a division:

~~~java
Integer remainder = parser.parseExpression("17 % 5")
        .getValue(Integer.class);

System.out.println(remainder); // 2
~~~

Example checking whether a number is divisible by 2:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("number", 24);

Expression expression = parser.parseExpression("#number % 2 == 0");
Boolean isEven = expression.getValue(context, Boolean.class);

System.out.println(isEven); // true
~~~

The modulo operation is often useful when grouping, determining loop positions, checking parity (even/odd), or computing cycles. The denominator must be non-zero.

## 7. Exponentiation (^)

SpEL uses the `^` operator to compute exponentiation:

~~~java
Integer result = parser.parseExpression("2 ^ 3")
        .getValue(Integer.class);

System.out.println(result); // 8
~~~

Example computing squares or cubes:

~~~java
Double square = parser.parseExpression("5.0 ^ 2")
        .getValue(Double.class);

Double cube = parser.parseExpression("2.0 ^ 3")
        .getValue(Double.class);

System.out.println(square); // 25.0
System.out.println(cube);   // 8.0
~~~

Note: `^` in SpEL is the exponentiation operator. It does not mean XOR as the `^` operator is used in Java. When converting an expression from Java to SpEL, pay attention to this difference.

## 8. Order of Operations and Parentheses

SpEL follows arithmetic operator precedence: exponentiation is processed before multiplication/division/modulo; multiplication, division, and modulo are processed before addition/subtraction. Operations at the same precedence level are processed in the order of the expression. Use parentheses to clarify intent and change the order when needed.

~~~java
Integer first = parser.parseExpression("2 + 3 * 4")
        .getValue(Integer.class);

Integer second = parser.parseExpression("(2 + 3) * 4")
        .getValue(Integer.class);

System.out.println(first);  // 14
System.out.println(second); // 20
~~~

Example with multiple operations:

~~~java
Double total = parser.parseExpression("(100.0 - 10.0) / 3.0 + 2.0")
        .getValue(Double.class);
~~~

Even when operator precedence is already known, parentheses still make expressions easier to read and reduce misunderstandings when formulas are maintained.

## 9. Numeric Types and Numeric Literals

SpEL supports several numeric literal types. Some common suffixes:

| Suffix | Literal Type | Example |
|---|---|---|
| No suffix for integers | Integer or suitable integer type | `42` |
| `L` | Long | `42L` |
| `F` | Float | `3.14F` |
| `D` | Double | `3.14D` |
| `M` | BigDecimal | `3.14M` |

Example using BigDecimal literals:

~~~java
BigDecimal total = parser.parseExpression("10.50M + 2.25M")
        .getValue(BigDecimal.class);

System.out.println(total); // 12.75
~~~

When using `BigDecimal`, both the literals and the expected result type should be stated explicitly. For monetary calculations, choose scale and rounding rules appropriate for the business logic; do not assume every division automatically produces the number of decimal places the application desires.

With `float` and `double`, some decimal values cannot be represented exactly in binary. Therefore, results may exhibit small rounding errors. Use `BigDecimal` if business requirements need exact decimal representation.

## 10. Combining Operations with Root Object and Variables

Arithmetic expressions do not need to hardcode fixed numbers. Properties can be read from the root object or variables in `EvaluationContext`.

Example using variables:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("price", 120.0);
context.setVariable("taxRate", 0.1);
context.setVariable("quantity", 2);

Expression expression =
        parser.parseExpression("#price * #quantity * (1 + #taxRate)");

Double total = expression.getValue(context, Double.class);
System.out.println(total); // 264.0
~~~

Example using a root object:

~~~java
public class Product {
    private double price;
    private int quantity;

    public Product(double price, int quantity) {
        this.price = price;
        this.quantity = quantity;
    }

    public double getPrice() {
        return price;
    }

    public int getQuantity() {
        return quantity;
    }
}

Product product = new Product(25.0, 4);

Expression expression =
        parser.parseExpression("price * quantity");

Double total = expression.getValue(product, Double.class);
System.out.println(total); // 100.0
~~~

In the root object example, `price` and `quantity` resolve to properties of the `product` object. For variables, the `#` prefix tells SpEL to retrieve the value from the evaluation context.

## 11. Combining Multiple Operators in a Formula

An expression can combine multiple operations to describe a concise formula:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("subtotal", 1000.0);
context.setVariable("discountRate", 0.15);
context.setVariable("shippingFee", 25.0);

Expression expression = parser.parseExpression(
        "#subtotal * (1 - #discountRate) + #shippingFee");

Double payable = expression.getValue(context, Double.class);
System.out.println(payable); // 875.0
~~~

The formula consists of three parts: multiplying subtotal by the remaining rate after discount, then adding the shipping fee. Parentheses make it clear that the rate portion is calculated first.

Another example combining modulo and addition:

~~~java
Expression expression = parser.parseExpression("(#number % 10) + 1");
~~~

The expression above extracts the units digit of `#number`, then adds 1. When using long expressions, give variables meaningful names and move complex logic into a Java method if that makes it easier to understand.

## 12. Common Errors and How to Handle Them

**Division by zero**

A denominator of 0 makes division impossible to evaluate. Validate data before calling `getValue`, or catch evaluation errors at an appropriate layer.

**Confusing exponentiation with XOR**

In Java, `^` is bitwise XOR; in SpEL, `^` is exponentiation. When converting formulas between the two languages, translate the mathematical meaning accurately.

**Using the wrong result type**

An expression can return a numeric type different from what the code expects. Use the `getValue(..., TargetType.class)` overload when the output type is known and choose explicit literal types.

**Floating-point precision errors**

`float` and `double` can have representation errors. For currency or strict rounding rules, consider `BigDecimal` and explicitly define scale/rounding.

**Missing parentheses**

An expression with multiple operations may produce a result different from what a reader expects. Add parentheses wherever business calculation grouping needs to be expressed.

**Invalid dynamic data**

If an input value is null or cannot be converted to the required numeric type, the expression may throw an evaluation error. Validate and normalize data at the application boundary instead of relying on expressions to hide bad data.

## 13. When to Use SpEL and When to Write Java?

SpEL is suitable for short formulas used where Spring needs to evaluate an expression, such as in configuration, simple rules, or object-based conditions. It helps describe a calculation directly without creating a separate method for every small expression.

Java is usually more suitable when a formula has multiple steps, multiple branches, requires scale/rounding control, needs detailed logging, or is a critical part of business logic. In those cases, writing a clearly named Java method gives better compiler and IDE support, and is also easier to test.

Do not move an entire business calculation into a long SpEL string just to make an annotation shorter. Keep expressions short, with clear inputs, and easy to verify.

## 14. Key Takeaways

- `+`, `-`, `*`, `/`, `%`, `^` support addition, subtraction, multiplication, division, remainder division, and exponentiation respectively.
- `+` can also concatenate strings; pay attention to the data types of both operands.
- `^` in SpEL is exponentiation, different from Java's XOR.
- Use parentheses to clearly express the order of operations.
- Choose appropriate numeric types; use `BigDecimal` for calculations requiring decimal precision.
- Pass dynamic data into `EvaluationContext` or the root object instead of concatenating data into the expression source string.
- Handle zero denominators, null data, and conversion errors at an appropriate layer.
- Keep SpEL for short expressions; move multi-step logic to Java.
