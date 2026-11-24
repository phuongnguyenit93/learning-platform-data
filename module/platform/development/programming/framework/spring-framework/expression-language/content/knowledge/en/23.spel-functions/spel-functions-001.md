# Registering Java Functions in EvaluationContext

Spring Expression Language (SpEL) allows calling Java functions from an expression by registering a **java.lang.reflect.Method** object in an **EvaluationContext**. Once registered, the expression invokes the function using the **#functionName(arguments)** syntax.

This mechanism is useful when multiple expressions need to share a small processing operation, such as normalizing strings, validating codes, performing calculations, or applying a simple rule. Instead of rewriting the logic in every expression, the application puts the Java method into the context once and calls it by function name.

Example:

~~~text
#normalizeCode(#rawCode)
~~~

The expression calls the normalizeCode function registered in the context and passes the value of the rawCode variable as an argument.

## 1. What is a Function in SpEL?

A SpEL function is a Java method registered under a name so that an expression can call it. The function name is chosen by the application and does not necessarily have to match the Java method name.

Java method example:

~~~java
public final class TextFunctions {

    private TextFunctions() {
    }

    public static String normalize(String value) {
        return value == null
                ? null
                : value.trim().toUpperCase(Locale.ROOT);
    }
}
~~~

The Java method is named normalize. When this method is registered under the name normalizeCode, the expression calls:

~~~text
#normalizeCode(' spring ')
~~~

The result is the string SPRING.

Function call syntax:

~~~text
#functionName(argument1, argument2, ...)
~~~

The # sign indicates that the name is being looked up in the variable/function namespace of the EvaluationContext. The parentheses pass the arguments to the method.

A function can return any Java type that SpEL can accept and use: String, boolean, numbers, enums, domain objects, collections, or null. The returned result can continue to be used in operations, conditions, property accesses, or other method calls.

## 2. Registering a Method with StandardEvaluationContext

The common approach is to obtain the Method via reflection and then call **registerFunction()** on StandardEvaluationContext.

Complete example:

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
        return value == null
                ? null
                : value.trim().toUpperCase(Locale.ROOT);
    }
}

class FunctionExample {

    public static void main(String[] args) throws NoSuchMethodException {
        StandardEvaluationContext context =
                new StandardEvaluationContext();

        Method normalizeMethod = TextFunctions.class
                .getMethod("normalize", String.class);

        context.registerFunction("normalizeCode", normalizeMethod);
        context.setVariable("rawCode", " spring ");

        ExpressionParser parser = new SpelExpressionParser();

        Expression expression =
                parser.parseExpression("#normalizeCode(#rawCode)");

        String result = expression.getValue(context, String.class);

        System.out.println(result); // SPRING
    }
}
~~~

Main steps:

1. Create a StandardEvaluationContext.
2. Obtain the Method object representing the Java method to register.
3. Call registerFunction() with the function name and the Method.
4. Register the variables that the expression needs to use.
5. Parse the expression containing the #functionName(...) syntax.
6. Evaluate the expression using the same context where the function was registered.

The function is registered on a specific context. Only expressions evaluated with that context see this function.

## 3. What Signature Should a Method Used as a Function Have?

A function is registered using a Method object, so it is necessary to choose the exact method and desired signature.

### 3.1. Use a static method

You should register a **public static method**. Function invocation does not pass a Java instance as the receiver for the method; the method is invoked as a standalone utility function.

Suitable example:

~~~java
public static boolean isValidCode(String value) {
    return value != null && value.matches("[A-Z]{3}-[0-9]{4}");
}
~~~

Registration:

~~~java
Method method = CodeFunctions.class
        .getMethod("isValidCode", String.class);

context.registerFunction("validCode", method);
~~~

Calling in SpEL:

~~~text
#validCode(#code)
~~~

If you need to call an instance method that has injected dependencies, state, or configuration, consider calling the method on a Spring bean using a bean reference, for example @codePolicy.isValid(#code). A bean method is more appropriate when the logic requires Spring-managed dependencies.

### 3.2. Choose the right overload

Java allows method overloading, but registerFunction() takes a specific Method object. Therefore, explicitly select the overload by method name and parameter type list:

~~~java
Method method = NumberFunctions.class
        .getMethod("round", BigDecimal.class, int.class);

context.registerFunction("roundAmount", method);
~~~

Expression:

~~~text
#roundAmount(#amount, 2)
~~~

The registered method is the overload taking BigDecimal and int. Do not expect SpEL to automatically discover all Java overloads simply because they share the same name.

If multiple invocation forms are needed, you can register separate function names for each signature or write a facade method that accepts a unified input type and handles it in Java.

### 3.3. Arguments and return value

The number and types of arguments in the expression must be compatible with the registered method signature.

Example method:

~~~java
public static BigDecimal addTax(
        BigDecimal amount,
        BigDecimal taxRate) {
    return amount.multiply(BigDecimal.ONE.add(taxRate));
}
~~~

Expression:

~~~text
#addTax(#subtotal, #taxRate)
~~~

The result is a BigDecimal and can continue to be used:

~~~text
#addTax(#subtotal, #taxRate).setScale(2)
~~~

If the number of arguments is incorrect, the types are incompatible, or conversion fails, the expression may throw an error during evaluation. Keep the data types of variables and method parameters clear to avoid relying on unnecessary conversions.

## 4. Using Functions in Multiple Parts of an Expression

Once registered, a function can be called in any part of an expression where that position accepts a value or a condition.

Example:

~~~text
#isValidCode(#code)
    and #normalizeCode(#code) == #expectedCode
~~~

Both functions use the same code variable. One function checks validity; the other normalizes the value for comparison.

A function can also appear in a ternary branch:

~~~text
#isPremium(#customer)
    ? #calculateDiscount(#order, #customer)
    : 0
~~~

Or be passed as an argument to a bean method:

~~~text
@auditService.record(#formatAuditMessage(#event))
~~~

In this case, SpEL calls the formatAuditMessage function first, then passes the result to the record method of the auditService bean. Bean references still require a BeanResolver in the EvaluationContext.

### 4.1. Using a function in selection

Suppose the isEligible function has been registered taking an Order and returning a boolean:

~~~java
public static boolean isEligible(Order order) {
    return order != null
            && order.getTotal().compareTo(new BigDecimal("100.00")) >= 0;
}
~~~

Expression:

~~~text
#orders.?[#isEligible(#this)]
~~~

Selection calls the function for each element and keeps only the Order instances for which the function returns true.

### 4.2. Using a function in projection

If there is a formatOrder function that takes an Order and returns a String:

~~~text
#orders.![#formatOrder(#this)]
~~~

Projection creates a list of strings from the Order collection. #this is the current element of the collection; the function receives that element as an argument.

Selection and projection can be combined:

~~~text
#orders.?[#isEligible(#this)].![#formatOrder(#this)]
~~~

First filter the collection using isEligible, then transform each remaining Order into a string using formatOrder.

## 5. Functions and Variables Share a Namespace

Functions are called using the # symbol just like variables, but their usage differs:

- **#minimumTotal** reads a variable value.
- **#normalizeCode(#rawCode)** calls a function and passes arguments.
- **#currentUser.name** reads a property of the object stored in the currentUser variable.

In StandardEvaluationContext, function names and variable names share the same namespace. Therefore, avoid registering a function and a variable with the same name. A call to setVariable() can change the value looked up under that name, and registering a function can also overwrite an entry with the same name.

Example to avoid:

~~~java
context.registerFunction("normalize", normalizeMethod);
context.setVariable("normalize", "UPPER");
~~~

After using the same name for the variable, the expression #normalize(...) is no longer resolved as the registered function.

Use a clear naming convention, for example:

- Functions: normalizeCode, isEligible, calculateTax.
- Variables: rawCode, currentUser, taxRate, orders.

### 5.1. Registering a Method using setVariable()

Besides registerFunction(), StandardEvaluationContext also allows registering a Method using setVariable():

~~~java
context.setVariable("normalizeCode", normalizeMethod);
~~~

When the registered value is a Method, SpEL can invoke it like a function:

~~~text
#normalizeCode(#rawCode)
~~~

However, registerFunction() expresses the intent to register a function more clearly and should be preferred when the Spring API version in use supports this method. Regardless of which approach is used, the name still resides in the shared namespace with variables.

## 6. How Does a Function Differ from Bean Methods and Static Method Calls?

There are three common ways to call Java logic from SpEL:

| Invocation style | Example | Mechanism |
| --- | --- | --- |
| Registered function | **#normalizeCode(#value)** | Method registered in EvaluationContext |
| Spring bean method | **@textPolicy.normalize(#value)** | BeanResolver finds the bean and calls the instance method |
| Static method via type reference | **T(com.example.TextFunctions).normalize(#value)** | TypeLocator finds the class and calls the static method |

### 6.1. When to use a registered function?

Use a function when you need a small, static utility method that does not depend on an instance or dependency injection. The function name can be concise and clearly scoped within the EvaluationContext.

Examples: string normalization, format validation, pure calculations, or converting a value.

### 6.2. When to use a bean method?

Use a bean method when the logic needs Spring-managed dependencies, configuration, state, or coordination with other repositories/services:

~~~text
@permissionService.canRead(#document, #currentUser)
~~~

A bean reference requires a BeanResolver. In return, the method can be an instance method and use injected dependencies.

### 6.3. When to use T()?

SpEL supports type references using the T() operator:

~~~text
T(java.lang.Math).max(#left, #right)
~~~

This approach is suitable when you want to directly call a public static method of a class. There is no need to register the Method as a function, but the expression must reference the type via TypeLocator and the EvaluationContext must allow type references.

A registered function creates an explicit alias in the context; T() directly exposes the class and method being called. Choose the approach that fits the desired clarity and access scope.

## 7. What Argument Types Can a Function Accept?

A function accepts arguments according to the signature of the registered Java Method. Arguments in the expression can be literals, variables, properties, results of other functions, or results of an operation.

Example method:

~~~java
public static BigDecimal calculateFee(
        BigDecimal amount,
        BigDecimal rate,
        boolean priority) {

    BigDecimal fee = amount.multiply(rate);

    return priority
            ? fee.add(new BigDecimal("10.00"))
            : fee;
}
~~~

Expression:

~~~text
#calculateFee(#amount, #feeRate, #priority)
~~~

Literals can be passed:

~~~text
#calculateFee(#amount, 0.02, true)
~~~

Or use the result of another function as an argument:

~~~text
#calculateFee(#normalizeAmount(#rawAmount), #feeRate, #priority)
~~~

### 7.1. Argument type conversion

SpEL can use the EvaluationContext's TypeConverter during method invocation. Conversion capability depends on the configured ConversionService and converters. Do not assume that every string can automatically convert to every domain type.

If a function takes a BigDecimal, the clear approach is to supply a BigDecimal from a variable or construct it explicitly:

~~~text
#calculateFee(new java.math.BigDecimal('100.00'), #feeRate, false)
~~~

If conversion is an application-specific rule, register an appropriate converter or perform the conversion in Java before placing the data into the context.

### 7.2. Varargs

A Java method can use varargs if the registered signature supports it:

~~~java
public static String joinCodes(String separator, String... codes) {
    return String.join(separator, codes);
}
~~~

The expression can pass the corresponding arguments:

~~~text
#joinCodes('-', 'A1', 'B2', 'C3')
~~~

When using varargs, ensure that the number and types of arguments match the fixed parameters along with the element type of the varargs array.

## 8. Functions Returning null or Throwing Exceptions

If the method returns null, the function result in SpEL is also null. That result can be handled with the Elvis operator:

~~~text
#displayName(#user) ?: 'Anonymous'
~~~

If the method throws an exception, expression evaluation fails and Spring Expression typically wraps the original error in a SpEL exception. Handle business errors in the Java method if they can be meaningfully recovered from; do not use a function to hide all errors with a generic default value.

A function should clearly define its contract for null inputs:

~~~java
public static String safeUpper(String value) {
    return value == null ? null : value.toUpperCase(Locale.ROOT);
}
~~~

For another method, null may be invalid data and should throw IllegalArgumentException or a specific domain exception. What matters is that the behavior is clear and consistent with where the expression is used.

## 9. Scope and Lifecycle of a Function

A function is registered on an EvaluationContext, not registered globally for every SpEL parser in the JVM.

Example:

~~~java
StandardEvaluationContext firstContext =
        new StandardEvaluationContext();

firstContext.registerFunction("normalizeCode", normalizeMethod);

StandardEvaluationContext secondContext =
        new StandardEvaluationContext();
~~~

An expression evaluated with firstContext can call #normalizeCode(...). If the same expression is evaluated with secondContext, the function does not appear there automatically; it must be registered again.

A parsed Expression can be reused across many different contexts. The Expression holds the parsed structure, while functions and variables are resolved from the EvaluationContext passed into each getValue() call.

A useful pattern is to create a context per processing unit:

~~~java
StandardEvaluationContext createContext(String rawCode)
        throws NoSuchMethodException {

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    Method normalizeMethod = TextFunctions.class
            .getMethod("normalize", String.class);

    context.registerFunction("normalizeCode", normalizeMethod);
    context.setVariable("rawCode", rawCode);

    return context;
}
~~~

If function registration is identical across multiple contexts, you can place Method lookup and registration into a factory/helper to avoid code duplication. Do not share a mutable context across concurrent requests if those requests require different variables.

## 10. Testing Registered Functions

JUnit can be used to verify that a function is registered and invoked properly:

~~~java
class SpelFunctionTest {

    private final ExpressionParser parser =
            new SpelExpressionParser();

    @Test
    void invokesRegisteredStaticMethod() throws Exception {
        StandardEvaluationContext context =
                new StandardEvaluationContext();

        Method normalizeMethod = TextFunctions.class
                .getMethod("normalize", String.class);

        context.registerFunction("normalizeCode", normalizeMethod);
        context.setVariable("rawCode", " spring ");

        String result = parser
                .parseExpression("#normalizeCode(#rawCode)")
                .getValue(context, String.class);

        assertEquals("SPRING", result);
    }

    @Test
    void usesFunctionResultInAnotherExpression() throws Exception {
        StandardEvaluationContext context =
                new StandardEvaluationContext();

        Method normalizeMethod = TextFunctions.class
                .getMethod("normalize", String.class);

        context.registerFunction("normalizeCode", normalizeMethod);
        context.setVariable("rawCode", " spring ");

        Boolean result = parser
                .parseExpression(
                    "#normalizeCode(#rawCode) == 'SPRING'"
                )
                .getValue(context, Boolean.class);

        assertEquals(Boolean.TRUE, result);
    }
}
~~~

Tests should cover:

- The function is registered under the expected name.
- Arguments have the right types and count.
- The result has the expected type and value.
- Null inputs or boundary data according to the method contract.
- The function called within selection, projection, or logical expressions if the application uses those cases.
- A fresh context where the function is not registered and the behavior when the function name does not exist.

If the function is used in @Value, @Cacheable, or Method Security, test the actual integration point as well to confirm that the context Spring creates has the required functions/variables. Do not assume annotations automatically inherit functions registered in a completely separate StandardEvaluationContext.

## 11. Security When Registering Functions

Functions allow expressions to invoke Java code. Therefore, registered methods are part of the access surface that expressions can use.

Some practical principles:

1. Only register functions that the expressions actually need.
2. Prefer pure methods with deterministic results and no side effects.
3. Do not register methods that can delete data, execute payments, modify permissions, access secrets, or call external systems if expressions are not completely trusted.
4. Do not evaluate arbitrary user-submitted SpEL with a StandardEvaluationContext containing broad-privilege functions.
5. Validate input types and values inside the Java method; do not rely solely on the expression for validation.
6. Isolate contexts by processing scope to avoid leaking variables or state between requests.
7. If logic requires services or complex access permissions, consider a facade bean with a restricted API instead of registering many static utility methods.

StandardEvaluationContext provides many SpEL capabilities. Simply registering a single function does not automatically turn the entire expression into a sandbox. Restrict expression sources and the features allowed by the context.

## 12. Common Mistakes

1. **Forgetting to register the function:** the expression calls #normalizeCode(...) but the context has not registered that name.
2. **Using the wrong syntax:** functions are called with #name(args), not @name(args).
3. **Registering the wrong Method overload:** getMethod() must receive the exact list of parameter types.
4. **Using an instance method as a function:** function registration does not provide a receiver object; use a static method or call a bean instance method via @beanName.
5. **Wrong argument count or types:** the expression must be compatible with the registered Method signature.
6. **Variable and function name collision:** they share the same namespace in StandardEvaluationContext.
7. **Registering in a different context:** a function exists only in the context where it was registered.
8. **Assuming a function is a bean:** functions are not managed by the Spring container and do not receive automatic dependency injection.
9. **Not handling null or exceptions:** errors from the method can cause the entire expression to fail.
10. **Registering overly privileged functions:** untrusted expressions can invoke methods that were exposed to them.

## 13. Quick Takeaways

- Register a function using **StandardEvaluationContext.registerFunction(name, method)**.
- The registered method is a **java.lang.reflect.Method** object.
- Prefer a **public static method**, because function invocation does not pass an instance receiver.
- Call a function in SpEL using **#functionName(arguments)**.
- The function name can differ from the Java method name.
- Select the exact overload when obtaining the Method via reflection.
- Functions can accept literals, variables, properties, or results of other expressions.
- Return values can continue to be used in conditions, operations, selection, and projection.
- Functions and variables share a namespace; avoid giving them the same name.
- A function belongs to the EvaluationContext in which it was registered; a new context needs to register it again.
- Use a bean reference for instance methods needing dependency injection; use T() when calling a static method directly via type reference.
- Only register necessary methods and do not evaluate untrusted expressions with an overly permissive context.

## 14. Official References

- [Spring Framework — Functions in SpEL](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/functions.html)
- [Spring Framework — EvaluationContext](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [StandardEvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardEvaluationContext.html)
- [EvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/EvaluationContext.html)
- [Spring Framework — Bean References](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/bean-references.html)
