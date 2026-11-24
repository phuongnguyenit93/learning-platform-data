# Ternary Operator and True or False Branches in SpEL

## 1. Syntax of the Conditional Operator

Spring Expression Language (SpEL) supports the ternary conditional operator, which has the form:

~~~text
condition ? expressionIfTrue : expressionIfFalse
~~~

The conditional expression is evaluated first. If the condition is `true`, SpEL evaluates and returns the expression in the branch to the left of the colon. If the condition is `false`, SpEL evaluates and returns the expression in the branch to the right of the colon.

Example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("10 > 5 ? 'Greater' : 'Not greater'");

String result = expression.getValue(String.class);
System.out.println(result); // Greater
~~~

In this example:

- `10 > 5` is the Boolean condition.
- `'Greater'` is the branch selected when the condition is true.
- `'Not greater'` is the branch selected when the condition is false.
- The `?` sign starts the selection; the `:` sign separates the two branches.

The ternary operator produces a value. Therefore, it can be used wherever another SpEL expression is accepted, such as in a string concatenation, a configuration expression, or a `getValue` call.

## 2. The Condition Must Evaluate to a Boolean

The part before `?` must evaluate to a Boolean value. The condition is usually a comparison:

~~~java
Expression expression =
        parser.parseExpression("#age >= 18 ? 'Adult' : 'Minor'");

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("age", 20);

String category = expression.getValue(context, String.class);
System.out.println(category); // Adult
~~~

Comparison expressions such as `>`, `>=`, `<`, `<=`, `==`, and `!=` are commonly used to form conditions. They can be combined with logical operators:

~~~java
Expression expression = parser.parseExpression(
        "(#age >= 18 and #verified) ? 'Approved' : 'Review'");

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("age", 21);
context.setVariable("verified", true);

String result = expression.getValue(context, String.class);
System.out.println(result); // Approved
~~~

Parentheses around the condition help readers clearly see which part is evaluated before selecting a branch. If a non-Boolean value is placed directly in the condition position, the expression may raise an error during evaluation; do not assume SpEL automatically treats non-zero numbers or non-empty strings as `true`.

## 3. True Branch and False Branch

The true branch is the expression between `?` and `:`. The false branch is the expression after `:`. Each branch can be a literal, variable, property access, method call, or another SpEL expression.

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("available", true);

Expression expression =
        parser.parseExpression("#available ? 'In stock' : 'Out of stock'");

String message = expression.getValue(context, String.class);
System.out.println(message); // In stock
~~~

When changing the variable:

~~~java
context.setVariable("available", false);

String message = expression.getValue(context, String.class);
System.out.println(message); // Out of stock
~~~

The same `Expression` can be re-evaluated with an updated context. The result depends on the condition value at the time `getValue` is called.

Only the selected branch needs to be evaluated to produce the result. This allows placing separate calculations or data accesses in each branch, as long as the selected branch can evaluate validly with the current context.

## 4. Using Boolean Literals true and false

SpEL has Boolean literals `true` and `false`. They can be used as result branches:

~~~java
Expression expression =
        parser.parseExpression("#score >= 50 ? true : false");

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("score", 75);

Boolean passed = expression.getValue(context, Boolean.class);
System.out.println(passed); // true
~~~

In cases where you only return the condition itself or its negation, there is no need to use the ternary operator:

~~~java
Expression expression = parser.parseExpression("#score >= 50");
Boolean passed = expression.getValue(context, Boolean.class);
~~~

The expression `#score >= 50 ? true : false` is equivalent to `#score >= 50`. Use ternary when the two branches need to produce two different results, such as a status, label, fee level, or fallback value.

## 5. Both Branches Can Return Strings, Numbers, or Other Values

The ternary operator does not restrict the result to Boolean. Both branches can return whatever data types the application needs:

~~~java
Expression labelExpression =
        parser.parseExpression("#total >= 1000 ? 'VIP' : 'STANDARD'");

Expression feeExpression =
        parser.parseExpression("#express ? 0 : 25000");

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("total", 1500);
context.setVariable("express", false);

String label = labelExpression.getValue(context, String.class);
Integer fee = feeExpression.getValue(context, Integer.class);

System.out.println(label); // VIP
System.out.println(fee);   // 25000
~~~

The result type depends on the selected branch and the value type of that expression. When the application needs a specific result type, use the `getValue(..., TargetType.class)` overload and ensure the selected value can be converted to the target type. To keep the expression easy to understand, the two branches should usually return values of compatible types.

Example returning a default value when data does not meet the condition:

~~~java
Expression expression =
        parser.parseExpression("#nickname != null ? #nickname : 'Guest'");

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("nickname", null);

String displayName = expression.getValue(context, String.class);
System.out.println(displayName); // Guest
~~~

This style helps avoid returning null when the application needs a fallback label. However, if the selected branch may access a property through a null object, check the condition before accessing that property.

## 6. Accessing Properties in Both Branches

Each branch can reference properties of the root object or variables in the evaluation context. For example, an order can use different labels depending on its payment status:

~~~java
public class Order {
    private String code;
    private boolean paid;

    public Order(String code, boolean paid) {
        this.code = code;
        this.paid = paid;
    }

    public String getCode() {
        return code;
    }

    public boolean isPaid() {
        return paid;
    }
}

Order order = new Order("ORD-1001", true);

Expression expression = parser.parseExpression(
        "paid ? 'Order ' + code + ' is paid' : 'Order ' + code + ' is pending'");

String status = expression.getValue(order, String.class);
System.out.println(status); // Order ORD-1001 is paid
~~~

In this expression, `paid` and `code` are resolved from the root object `order`. If the payment status is false, SpEL selects the second branch and produces the pending payment message.

It is also possible to access nested properties inside a branch:

~~~text
#customer != null ? #customer.name : 'Unknown customer'
~~~

The condition checks the `#customer` variable before the true branch accesses `name`. When `#customer` is null, the false branch is selected and the `name` property does not need to be accessed.

## 7. Using the Ternary Operator in @Value

In Spring configuration integration points, SpEL is commonly placed inside `#{...}`. The ternary operator can be used to choose the value to inject:

~~~java
@Component
public class RetryConfiguration {
    @Value("#{T(java.lang.Math).max(3, 5) > 3 ? 'HIGH' : 'LOW'}")
    private String retryLevel;

    public String getRetryLevel() {
        return retryLevel;
    }
}
~~~

Spring evaluates the SpEL expression when processing bean configuration. If the condition is true, the field receives the value of the true branch; if false, the field receives the value of the false branch.

Another example selecting a timeout by profile or a configuration value available in the application context can be written with the same structure. Keep each branch short and readable. If the value selection rule has multiple steps, move the logic to a Java method or a dedicated bean.

## 8. Combining the Ternary Operator with Arithmetic Operations

The true and false branches can contain arithmetic calculations:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("quantity", 12);
context.setVariable("unitPrice", 50);
context.setVariable("discountEligible", true);

Expression expression = parser.parseExpression(
        "#discountEligible ? #quantity * #unitPrice * 0.9 : #quantity * #unitPrice");

Double payable = expression.getValue(context, Double.class);
System.out.println(payable); // 540.0
~~~

If the customer is eligible, the true branch applies a 10% discount; otherwise, the false branch calculates the total at the original price. The condition and both formulas are in a single expression, while the data is passed via variables.

It can be combined with other comparison operations:

~~~java
Expression expression = parser.parseExpression(
        "#quantity >= 10 ? #unitPrice * 0.95 : #unitPrice");
~~~

The expression selects a 5% discounted unit price when the quantity is at least 10. For real-world monetary formulas, use an appropriate numeric type and rounding rule, such as `BigDecimal`, instead of relying on `double` when decimal precision is needed.

## 9. Nested Ternary Operators

A branch can contain another ternary operator. This approach allows selecting among multiple cases:

~~~java
Expression expression = parser.parseExpression(
        "#score >= 85 ? 'Excellent' : (#score >= 50 ? 'Pass' : 'Fail')");

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("score", 72);

String grade = expression.getValue(context, String.class);
System.out.println(grade); // Pass
~~~

How to read the expression:

1. If `#score >= 85`, return `Excellent`.
2. If the first condition is false, evaluate the ternary operator inside the parentheses.
3. If `#score >= 50`, return `Pass`; otherwise, return `Fail`.

When there are more than two or three choice levels, a nested ternary chain quickly becomes hard to read. You can split the expression, use a clearly named Java method, or use a rule structure suited to the application.

## 10. Combining with Logical Operators

The condition can combine `and`, `or`, and `not` before selecting a branch:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("active", true);
context.setVariable("verified", false);
context.setVariable("balance", 100);

Expression expression = parser.parseExpression(
        "(#active and #verified and #balance > 0) ? 'Can proceed' : 'Blocked'");

String result = expression.getValue(context, String.class);
System.out.println(result); // Blocked
~~~

Even though `active` is true and balance is greater than 0, `verified` is false, so the entire `and` condition is false. SpEL selects the false branch.

You can use `or` to allow multiple different conditions to lead to the same branch:

~~~java
Expression expression = parser.parseExpression(
        "(#isAdmin or #isOwner) ? 'Allowed' : 'Denied'");
~~~

Use parentheses to show condition grouping. This helps avoid confusion when combining multiple logical operators with the ternary operator.

## 11. Distinguishing Ternary from Elvis and Logical Operators

The ternary operator always has three parts: the condition, the true branch, and the false branch:

~~~text
condition ? valueWhenTrue : valueWhenFalse
~~~

SpEL's Elvis operator has the syntax `?:` and is commonly used to choose a fallback value when the left-hand expression is null or empty according to SpEL rules:

~~~java
Expression expression = parser.parseExpression("#nickname ?: 'Guest'");
~~~

The two syntaxes serve different purposes:

- Ternary: selects a branch based on an explicit Boolean condition.
- Elvis: provides a fallback value when the left-hand value does not have a suitable value under Elvis semantics.
- `and`, `or`, `not`: combine or negate Boolean conditions; they do not directly select a result value from two branches.

If you need to check multiple conditions or need a clear business rule, ternary helps express the condition and two results directly.

## 12. Common Mistakes

**Missing a branch**

The expression must include `?`, the true branch, `:`, and the false branch. Missing any part causes the parser to report a syntax error.

**Non-Boolean condition**

The condition part must return a Boolean. Use a comparison or logical expression instead of placing a string or number in the condition position.

**Swapping the order of the two branches**

The value before `:` is the result when the condition is true; the value after `:` is the result when the condition is false. Read expressions following this structure to avoid inverting results.

**Accessing null data in the selected branch**

If a branch accesses a property of a null object, evaluation may fail. Check the object in the condition or use appropriate null-safe access.

**Incompatible types in the two branches**

If the code requests a specific result type, ensure the value of the selected branch can be converted to that type. Avoid having one branch return a number while the other returns an unrelated object if the application expects a consistent type.

**Over-nesting conditions**

A long ternary chain is very hard to read and modify. Move complex rules to a Java method or split them into small, clearly named expressions.

## 13. Comprehensive Example

The following example selects a message and shipping fee based on order status:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("paid", true);
context.setVariable("total", 1200.0);
context.setVariable("express", false);

Expression messageExpression = parser.parseExpression(
        "#paid ? 'Payment received' : 'Awaiting payment'");

Expression shippingExpression = parser.parseExpression(
        "#total >= 1000 ? (#express ? 0 : 15000) : 25000");

String message = messageExpression.getValue(context, String.class);
Double shippingFee = shippingExpression.getValue(context, Double.class);

System.out.println(message);     // Payment received
System.out.println(shippingFee); // 15000.0
~~~

The first expression selects the message based on payment status. The second expression selects the shipping fee based on the order total; if it meets the threshold, a nested ternary further selects the fee based on express delivery service.

## 14. Key Takeaways

- The ternary syntax in SpEL is `condition ? expressionIfTrue : expressionIfFalse`.
- The condition must evaluate to Boolean.
- The true branch is between `?` and `:`; the false branch is after `:`.
- Each branch can return a literal, variable, property, method call, or another expression.
- Ternary can be used with root objects, variables, `@Value`, arithmetic operations, and template expressions.
- Use parentheses when combining logical conditions or nesting ternaries.
- Distinguish ternary from the Elvis operator and logical operators.
- Keep both branches compatible with the result type expected by the application; move multi-level logic to Java when needed.
