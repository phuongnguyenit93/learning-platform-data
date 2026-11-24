# Passing Arguments to Functions

## Objectives

After this lesson, you will be able to register a Java function to call from Spring Expression Language (SpEL); pass literals, variables, root object properties, and expression results as arguments; understand how parameter types are matched with the method signature; and handle null values, function invocation errors, or invalid data. You will also learn how to use functions in conditions, selection, and projection, distinguish functions from method invocations and bean references, and restrict which functions are allowed to be called.

## 1. What is a Function in SpEL?

A function is a Java method registered in an EvaluationContext so that a SpEL expression can invoke it by name. The function call syntax has a hash sign before the name and passes arguments inside parentheses:

~~~text
#functionName(argument1, argument2)
~~~

Example:

~~~text
#normalize('  Spring  ')
~~~

The expression calls the function named normalize and passes a string as an argument. The return value of the method becomes the result of that part of the expression.

Functions are suitable when you need to reuse a Java operation across multiple expressions, such as normalizing strings, checking codes, calculating thresholds, or converting a value. SpEL does not automatically discover every Java method by function name. The application must register a Method object to bind the function name to the permitted method.

## 2. How Does a Function Differ from Method Invocation?

SpEL can call a method on an object without registering a function:

~~~text
#customer.getDisplayName()
~~~

This is a method invocation on the object stored in the customer variable.

A function has its own syntax:

~~~text
#formatName(#customer)
~~~

Here formatName is the function name registered in the EvaluationContext. The argument #customer is passed into the corresponding Java method.

Three forms can be distinguished:

| Syntax | Meaning |
|---|---|
| #normalize(#value) | Calls a function registered in the context |
| #customer.normalize() | Calls a method on the customer object |
| @customerService.normalize(#value) | Retrieves a bean via BeanResolver and calls a method on the bean |

A function is neither a bean nor a property. The # symbol tells SpEL to look up the function in the EvaluationContext's variable namespace; the @ symbol is used to reference a bean via BeanResolver.

## 3. Registering a Function Using Method

A function is registered using a java.lang.reflect.Method object. A method used as a function must normally be static, because SpEL invokes the Method directly without requiring an instance receiver.

Utility class example:

~~~java
public final class TextFunctions {

    private TextFunctions() {
    }

    public static String normalize(String value) {
        if (value == null) {
            return null;
        }
        return value.trim().toLowerCase(Locale.ROOT);
    }
}
~~~

Registering the function in StandardEvaluationContext:

~~~java
Method normalizeMethod =
    TextFunctions.class.getMethod("normalize", String.class);

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.registerFunction("normalize", normalizeMethod);
~~~

After registration, an expression can call:

~~~text
#normalize('  SPRING  ')
~~~

The result is a string with leading and trailing whitespace removed and converted to lowercase.

Use getMethod(...) to retrieve a public method by exact name and parameter types. If using getDeclaredMethod(...), pay attention to the method's accessibility; prefer public static methods so behavior is predictable and you avoid needing to open reflection access unnecessarily.

## 4. Complete Java Example

The following example registers the normalize function, passes a variable into the expression, and receives the result:

~~~java
import java.lang.reflect.Method;
import java.util.Locale;

import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

public final class TextFunctions {

    private TextFunctions() {
    }

    public static String normalize(String value) {
        if (value == null) {
            return null;
        }
        return value.trim().toLowerCase(Locale.ROOT);
    }
}

public class FunctionExample {

    public static void main(String[] args) throws Exception {
        Method method =
            TextFunctions.class.getMethod("normalize", String.class);

        StandardEvaluationContext context =
            new StandardEvaluationContext();

        context.registerFunction("normalize", method);
        context.setVariable("input", "  SPRING  ");

        ExpressionParser parser = new SpelExpressionParser();
        Expression expression =
            parser.parseExpression("#normalize(#input)");

        String result =
            expression.getValue(context, String.class);

        System.out.println(result); // spring
    }
}
~~~

Main steps:

1. Obtain the Method object representing the Java method.
2. Register the Method under the function name normalize.
3. Put input data into the context using setVariable.
4. Parse the expression calling the function.
5. Evaluate the expression and retrieve the return value.

The Expression can be parsed once and evaluated many times with different variable values. On each evaluation, the function is invoked with the data currently present in the context.

## 5. Passing Literals as Arguments

Arguments can be literals written directly in the expression:

~~~text
#normalize('  Hello World  ')
#isAllowed(18, 65)
#formatCode('vn', 42)
~~~

SpEL string literals are normally enclosed in single quotes. Numeric and boolean literals can be written directly using the language's syntax.

Example of a Java function taking two integers:

~~~java
public static boolean isWithinRange(
        int value, int minimum, int maximum) {
    return value >= minimum && value <= maximum;
}
~~~

After registering the corresponding Method, you can call:

~~~text
#isWithinRange(25, 18, 65)
~~~

The result is true. The order of arguments in the expression must match the order of parameters of the Java method. If minimum and maximum are swapped, the function can still run, but the result will no longer reflect the intended rule.

## 6. Passing Variables in EvaluationContext

Function arguments are often taken from variables so that data can change without rebuilding the expression string:

~~~text
#calculateDiscount(#subtotal, #discountRate)
~~~

Java registers the data:

~~~java
context.setVariable("subtotal", new BigDecimal("250.00"));
context.setVariable("discountRate", new BigDecimal("0.10"));
~~~

Suppose the function has the signature:

~~~java
public static BigDecimal calculateDiscount(
        BigDecimal subtotal, BigDecimal rate) {
    return subtotal.multiply(rate);
}
~~~

During evaluation, SpEL retrieves both variables, evaluates each argument, and passes the values to the registered method.

This approach keeps the expression separated from input data. Update variables from Java before evaluating; do not concatenate user data directly into the expression string.

## 7. Passing Properties of the Root Object or an Object in a Variable

Arguments can also be properties of the root object:

~~~text
#formatCustomerName(name, email)
~~~

If the root object has name and email properties, SpEL reads them and passes them into the function.

You can reference an object registered in a variable:

~~~text
#calculateTotal(#order.items, #order.taxRate)
~~~

Or pass a specific property:

~~~text
#normalize(#customer.profile.displayName)
~~~

All arguments are evaluated before calling the function. Therefore, if an intermediate property path is null, retrieving the argument can fail before the Java method is called.

If nested data can be null, use safe navigation at every link that may be null:

~~~text
#normalize(#customer?.profile?.displayName)
~~~

The function must have a null-handling contract matching the values it can receive. Safe navigation protects property access; it does not automatically handle every error inside the function.

## 8. Passing Expression Results as Arguments

Arguments are not limited to literals or simple variables. You can pass the result of another expression:

~~~text
#calculateTax(#order.total * #taxRate)
~~~

~~~text
#formatName(#firstName + ' ' + #lastName)
~~~

~~~text
#isEligible(#customer.age, #customer.orders.size())
~~~

SpEL evaluates the argument expressions, then calls the function with the computed values. Functions can be nested if the return type of the inner function is compatible with the parameter of the outer function:

~~~text
#formatCode(#normalize(#rawCode))
~~~

In this example, normalize runs first; its result is passed into formatCode.

Nested expressions help reuse processing, but should not be nested so deeply that data types or call order become hard to determine. If there are multiple transformation steps, compute intermediate results in Java or create a business method with a clearly descriptive name.

## 9. Multiple Parameters and Data Types

The number and order of arguments must match the registered Method signature.

Example:

~~~java
public static String formatAmount(
        BigDecimal amount, String currency, int scale) {
    return amount.setScale(scale, RoundingMode.HALF_UP)
        + " " + currency;
}
~~~

Expression:

~~~text
#formatAmount(#amount, #currency, #scale)
~~~

Values are passed in the order amount, currency, and scale.

Some points to note:

- The number of arguments must match the method.
- Data types must be compatible with the parameter types.
- Primitive types such as int cannot accept null.
- Reference types such as String or BigDecimal can accept null if the method allows it.
- The return value has the type determined by the Java method.

SpEL has a TypeConverter mechanism in EvaluationContext to convert certain argument values when needed. Do not rely on implicit conversion to mask malformed input data. For monetary amounts or data requiring precision, pass the exact type such as BigDecimal from the start.

## 10. Choosing the Right Method When Overloads Exist

Java allows multiple methods with the same name but different parameter lists:

~~~java
public static String format(int value) { ... }

public static String format(BigDecimal value) { ... }
~~~

When registering a function, the application registers a specific Method object:

~~~java
Method method =
    FormatFunctions.class.getMethod("format", BigDecimal.class);

context.registerFunction("formatAmount", method);
~~~

The function name in SpEL is formatAmount, and the explicitly chosen Method is the overload taking BigDecimal.

SpEL does not automatically register all overloads of a Java method name. Method selection happens when the application retrieves the Method to register. If multiple input forms are needed, register functions with distinct names or write a wrapper method accepting a unified data type and branching in Java.

Explicit registration avoids having an expression call the wrong overload or change behavior when another method with the same name is added to the Java class.

## 11. Registering Functions with setVariable and registerFunction

Functions are stored in the variable namespace of EvaluationContext. In older Spring versions, a Method can be registered using setVariable:

~~~java
context.setVariable("normalize", normalizeMethod);
~~~

Then invoked using:

~~~text
#normalize(' Spring ')
~~~

Since Spring Framework 6.1, StandardEvaluationContext provides registerFunction(name, method) to clearly express the intent of registering a function:

~~~java
context.registerFunction("normalize", normalizeMethod);
~~~

Prefer registerFunction when the Spring version in use supports this method. For older projects, check the API of the exact version; using setVariable with a Method value is the traditional way to register functions.

Functions and variables share a namespace. If you register the normalize function and then call setVariable("normalize", "text"), the variable value can replace the registered Method. Then the expression #normalize(...) will no longer find the Method to call.

Avoid using the same name for a function and a variable. Choose meaningful names by role, such as normalizeText for a function and inputText for a variable.

## 12. Functions Returning Values and Using Results

A function can return a string, number, boolean, object, or collection. The return value can be used as part of a larger expression.

Example of a function returning boolean:

~~~text
#isBusinessDay(#eventDate) and #order.total > 0
~~~

Example of a function returning a string:

~~~text
#normalize(#customer.name).toUpperCase()
~~~

Example of a function returning BigDecimal:

~~~text
#calculateNetAmount(#grossAmount, #taxAmount) >= #minimumAmount
~~~

If a function returns null, the part of the expression receiving that result can also be null. Continuing to access properties or call methods on a null result can raise an error. Clarify whether the function can return null and use safe navigation or appropriate conditions.

Functions used in expressions should usually return a meaningful value. A void method provides no useful result for subsequent operations; if an action needs to be executed, consider invoking a service through a controlled mechanism at the application layer rather than using a computation function.

## 13. Using Functions in Selection and Projection

Functions can be invoked inside selection conditions or projection expressions.

Example filtering valid codes:

~~~text
#codes.?[#isValidCode(#this)]
~~~

The isValidCode function is invoked for each element of the collection.

Example normalizing names in projection:

~~~text
#customers.![#normalize(#this.name)]
~~~

Each customer is transformed into a normalized name string.

Both can be combined:

~~~text
#orders.?[#isEligibleOrder(#this, #minimumTotal)].![#toSummary(#this)]
~~~

Selection calls isEligibleOrder on each order; projection calls toSummary on each selected order.

Remember that a function can be called multiple times during a single collection evaluation. With N elements, a function in selection may run up to N times; a function in projection runs for each element passing through the projection. Avoid placing network queries, file writes, or heavy operations inside functions called repeatedly per element.

## 14. Function Side Effects and Performance Considerations

A function is real Java code. When called, the method can mutate state, read/write data, or communicate with external systems.

For functions used in conditional expressions or collection operations, prefer pure functions:

- Same inputs produce the same result.
- Do not mutate shared state.
- Do not write files or send messages.
- Do not open connections or hold resources.
- Do not depend on call order beyond the defined contract.

A function with side effects can be called multiple times when an expression is re-evaluated or when placed in selection/projection. This can cause an expression that looks like a simple filter to generate multiple transactions or unintended actions.

If you need to call a service, query data, or perform an operation that can fail, place that work in a Java service and pass the prepared result into the context. Measure actual cost if a function performs CPU-intensive calculations.

## 15. Handling Nulls and Argument Passing Errors

Errors can occur before or during a function call:

- An input variable has not been registered.
- The root object or an intermediate property is null.
- The number of arguments does not match the Method.
- An argument type cannot be converted to the parameter type.
- A null argument is passed to a primitive parameter.
- The function throws an exception while processing data.
- The method is inaccessible under current reflection permissions.

Example of a function accepting String:

~~~java
public static String normalize(String value) {
    if (value == null) {
        return null;
    }
    return value.trim();
}
~~~

This method proactively handles null. If a function does not accept null, check before calling it:

~~~text
#input != null and #isValidCode(#input)
~~~

For evaluation errors, the application should catch EvaluationException at the expression invocation boundary and log the root cause. Do not catch all errors and return true or an arbitrary default value, as that can turn invalid data into a valid business outcome.

## 16. Distinguishing Functions from Beans and Method Resolvers

A function is a Method registered directly in the context. A bean reference retrieves an object from the Spring container, while a method resolver determines how methods are called on objects.

| Mechanism | Registration or configuration | Invocation syntax |
|---|---|---|
| Function | Method registered in the context | #functionName(args) |
| Bean reference | BeanResolver connected to BeanFactory | @beanName.method(args) |
| Method invocation | Object accessible in the expression | #object.method(args) or rootProperty.method(args) |

Functions are typically suited for short, static operations with clear inputs and outputs. Beans are suited for collaborators with Spring-managed dependencies, lifecycle, or state. Method invocation is suited when the operation belongs to the data object itself being evaluated.

Do not register a service instance as a function by passing an instance method's Method. Function references are designed to call a Method registered under the function mechanism; use a static method or a bean reference if you need to call a method on a Spring-managed instance.

## 17. Restricting Function Invocation Privileges

Registering a function means allowing expressions to execute the corresponding Java code. If expressions come from users or untrusted sources, registering too many functions can expand privileges beyond what is needed.

Apply these principles:

1. Only register functions genuinely needed for the problem.
2. Use utility classes with small, easily testable public static methods.
3. Do not register methods capable of executing system commands, reading secrets, or modifying data unless specifically required and controlled.
4. Validate the types, sizes, and contents of arguments.
5. Do not use functions to replace service-layer authorization or validation.
6. Use an appropriate EvaluationContext and do not share mutable contexts across requests if there is risk of data leakage.

If you need to provide functions to untrusted expressions, create a dedicated context containing only allowlisted functions. Avoid placing broad-privilege objects or functions into the context merely for convenience.

## 18. Comprehensive Example: Limit-Checking Function

Suppose the application needs to check whether an order total falls within limits:

~~~java
public final class OrderFunctions {

    private OrderFunctions() {
    }

    public static boolean isWithinLimit(
            BigDecimal amount,
            BigDecimal minimum,
            BigDecimal maximum) {

        if (amount == null || minimum == null || maximum == null) {
            return false;
        }

        return amount.compareTo(minimum) >= 0
            && amount.compareTo(maximum) <= 0;
    }
}
~~~

Registering and calling the function:

~~~java
Method method = OrderFunctions.class.getMethod(
    "isWithinLimit",
    BigDecimal.class,
    BigDecimal.class,
    BigDecimal.class
);

StandardEvaluationContext context =
    new StandardEvaluationContext(order);

context.registerFunction("isWithinLimit", method);

context.setVariable("minimum", new BigDecimal("100.00"));
context.setVariable("maximum", new BigDecimal("500.00"));

ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "#isWithinLimit(total, #minimum, #maximum)"
);

Boolean accepted =
    expression.getValue(context, Boolean.class);
~~~

In the expression:

- total is a property of the root object order.
- #minimum and #maximum are variables in the EvaluationContext.
- #isWithinLimit(...) is the registered function.

The Java method is responsible for null checks and BigDecimal comparisons. The expression only connects the input values to the rule encapsulated in the function.

## 19. Testing Functions and Arguments

When testing a function used in SpEL, verify:

| Case | What to verify |
|---|---|
| Valid literal | Argument is passed properly |
| Variable | Latest value in context is used |
| Root property | Exact property of root object is passed |
| Multiple arguments | Correct count and order |
| Compatible type | Method is invoked with matching types |
| Type requiring conversion | TypeConverter handles according to configuration |
| Null argument | Function honors its contract |
| Unregistered variable | Error or missing value is detected |
| Function returns null | Subsequent expression handles null |
| Function throws exception | Error is reported at the evaluation boundary |
| Overload | The exact registered Method is called |
| Selection/projection | Invocation count matches processed elements |
| Variable/function name collision | Namespace is not unintentionally overwritten |
| Function with side effects | Does not cause unexpected repeated actions |

You can test the Java method directly and perform integration testing through SpEL. Direct testing verifies the function's logic; integration testing verifies Method registration, name resolution, argument evaluation, and type conversion.

## 20. Takeaways

A function in SpEL is a Java Method registered in an EvaluationContext and called using the #functionName(arguments) syntax. Functions normally use static methods; the application obtains the Method object and registers it under a function name. Starting from Spring Framework 6.1, use StandardEvaluationContext.registerFunction; in older versions, a Method can be registered via setVariable.

Arguments can be literals, variables, properties of the root object, or results of other expressions. Argument order and types must match the registered Method. Functions can return values used in conditions or larger expressions; nulls and exceptions need clear contracts.

Functions and variables share a namespace, so avoid giving them the same name. Functions differ from bean references and method invocations on objects. Functions may run multiple times in selection/projection or when an expression is re-evaluated, so prefer pure, fast methods without side effects.

Only register necessary functions, validate arguments, and restrict invocation privileges when expressions come from untrusted sources. For services with dependencies, lifecycles, or side effects, consider using a bean or handling it in Java rather than turning it into a static function.

## References

- [Spring Framework Reference — Functions](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/functions.html)
- [StandardEvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardEvaluationContext.html)
- [EvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/EvaluationContext.html)