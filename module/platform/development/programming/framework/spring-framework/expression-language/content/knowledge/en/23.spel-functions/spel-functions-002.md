# Using Static Methods as Functions

SpEL allows registering a Java static method under a function name so that an expression can call it using the #functionName(...) syntax. This approach is useful when a rule needs to reuse Java logic, such as normalizing codes, checking formats, or computing a value from parameters. The Java side holds the algorithm; the SpEL expression only calls the function with the required arguments.

A registered function should be distinguished from a direct static method call via a type reference. Both can call a static method, but their declaration and expression syntax differ: a function uses an alias name in the context, whereas a direct call uses T(Type).method(...).

## 1. What is a Function in SpEL?

A function is a Java method placed into an EvaluationContext under a name so that a SpEL expression can invoke it. The registered method must be static because SpEL calls it without needing an object instance as the receiver.

Function call syntax:

    #functionName(argument1, argument2)

For example, if the context registers a function named normalizeCode, the expression can call:

    #normalizeCode(customer.code)

The # prefix indicates that this is a function name registered in the context. Arguments inside the parentheses are still SpEL expressions, so they can read data from the root object, context variables, or the result of another calculation.

A function returns a value just like a regular method call. The return value can continue to be used in comparisons, string concatenation, conditional operators, selection, or projection.

Example:

    #normalizeCode(customer.code) == 'AB-123'

Or using a function in projection:

    lines.![#normalizeCode(product.sku)]

In the second expression, the function is called once for each element of the collection.

## 2. Preparing a Static Method in Java

Functions used for expressions should be placed in a utility class with public static methods. Example:

    public final class SpelFunctions {

        private SpelFunctions() {
        }

        public static String normalizeCode(String value) {
            if (value == null) {
                return null;
            }
            return value.trim().toUpperCase(Locale.ROOT);
        }

        public static boolean hasPrefix(
                String value, String prefix) {
            return value != null
                    && prefix != null
                    && value.startsWith(prefix);
        }
    }

This class provides two functions:

- normalizeCode trims leading and trailing whitespace and converts the code to uppercase consistently using Locale.ROOT.
- hasPrefix checks whether the string starts with the given prefix.

The constructor is made private to prevent unnecessary instantiation. The methods are declared static so they can be called directly without creating a SpelFunctions object.

A good function typically has clear inputs and outputs, minimal dependence on external state, and easily testable behavior. If you need to access a database, send notifications, or mutate system state, consider placing that action in a Java service instead of registering it as a function used in expressions.

## 3. Registering a Method with StandardEvaluationContext

SpEL uses a java.lang.reflect.Method object to represent the method to be registered. You can obtain the Method via reflection, then call registerFunction():

    Method normalizeMethod =
            SpelFunctions.class.getMethod(
                    "normalizeCode", String.class);

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    context.registerFunction(
            "normalizeCode", normalizeMethod);

getMethod finds a public method by name and exact parameter type list. In the example, the method is named normalizeCode and takes one String parameter.

registerFunction binds that Method to the alias normalizeCode in the EvaluationContext. After registration, the expression invokes it with the # prefix:

    #normalizeCode(customer.code)

Additional functions can be registered:

    Method prefixMethod =
            SpelFunctions.class.getMethod(
                    "hasPrefix", String.class, String.class);

    context.registerFunction("hasPrefix", prefixMethod);

Expression calling the two-argument function:

    #hasPrefix(customer.code, 'AB-')

The function name in the expression must match the registered name. Renaming the alias in the context without updating the expression, or vice versa, will prevent SpEL from finding the function.

## 4. Evaluating Functions with ExpressionParser

Complete example:

    ExpressionParser parser = new SpelExpressionParser();

    Method normalizeMethod =
            SpelFunctions.class.getMethod(
                    "normalizeCode", String.class);

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    context.registerFunction(
            "normalizeCode", normalizeMethod);

    Expression expression =
            parser.parseExpression(
                    "#normalizeCode(customer.code)");

    String normalizedCode =
            expression.getValue(context, String.class);

The workflow consists of these steps:

1. Java obtains the Method representing the static method.
2. EvaluationContext registers the Method under the name normalizeCode.
3. ExpressionParser parses the SpEL string.
4. getValue evaluates the expression against the root object order.
5. SpEL calls the function with the value of customer.code and returns the result to Java.

The expression does not need to know which package the SpelFunctions class is in. It only needs to know the function name provided by the context. This is an advantage when you want to use a stable alias across many rules.

If the method can throw a checked exception, handle the exception inside the method or design an appropriate wrapper. When a function raises an error during evaluation, SpEL typically wraps the error in an expression evaluation exception; the application should log the root cause and handle it according to its policy.

## 5. Using setVariable with Method

Besides registerFunction(), StandardEvaluationContext also allows registering a Method as a variable:

    Method normalizeMethod =
            SpelFunctions.class.getMethod(
                    "normalizeCode", String.class);

    context.setVariable("normalizeCode", normalizeMethod);

When a variable holds a Method object, SpEL can invoke it using function syntax:

    #normalizeCode(customer.code)

This approach is useful when the application wants to manage functions using the same setVariable() mechanism as other data. registerFunction() expresses the intent of registering a function more clearly; setVariable() provides a more general registration mechanism.

Do not register the same name for different purposes. Functions and variables reside in the same context variable namespace; overwriting a name can cause an expression to reference the wrong object or fail to invoke the intended function.

When reading legacy code, you may encounter both registration methods. Check the value being placed in the context and the application's Spring version before changing the API.

## 6. How Functions Differ from Static Method Calls via T(...)

SpEL can call a static method directly without registering a function. The syntax uses a type reference T(...) and then invokes the method:

    T(java.lang.Math).max(10, 20)

For an application utility class:

    T(com.example.rules.SpelFunctions)
        .normalizeCode(customer.code)

This is a method invocation on a type resolved by TypeLocator. The expression must know the class name; for classes outside java.lang, the fully qualified name or an appropriate package prefix configuration is usually required.

Meanwhile, a registered function is called by alias:

    #normalizeCode(customer.code)

Comparison:

| Invocation style | Example | Requires Method registration in context? |
|---|---|---|
| Registered function | #normalizeCode(customer.code) | Yes |
| Static method via type reference | T(com.example.rules.SpelFunctions).normalizeCode(customer.code) | No, but TypeLocator must be able to resolve the class |

Use a function when you want expressions to depend on a short, stable function name explicitly permitted by the application. Use T(Type).method(...) when you want to call a static method directly and accept having the class name appear in the expression.

Both approaches require access restrictions when expressions may come from external sources.

## 7. Function Arguments and Data Types

Function arguments are SpEL expressions. They can be properties of the root object, context variables, literals, or results of other functions.

Example:

    #hasPrefix(customer.code, #requiredPrefix)

Where customer.code is a property of the root object, and requiredPrefix is a registered variable:

    context.setVariable("requiredPrefix", "AB-");

Literals can be passed directly:

    #hasPrefix(customer.code, 'AB-')

Or use the result of a calculation:

    #calculateDiscount(order.total, #discountRate)

SpEL must find a Method matching the argument count and types. A method registered via a Method object is bound to a specific signature. If a class has multiple overloads with the same name, retrieve the exact Method with the desired parameter type list.

Example retrieving the overload taking two Strings:

    Method method = SpelFunctions.class.getMethod(
            "hasPrefix", String.class, String.class);

Do not rely on the method name alone to describe an overload. If there are multiple ways to handle inputs, you can register separate function aliases or create a static wrapper method with an explicit signature.

SpEL has a type conversion mechanism in applicable method invocation contexts, but you should not rely on implicit conversion to mask malformed input data. Pass explicit types and validate values at application boundaries.

## 8. Using Functions in Selection and Projection

A function registered in the context can be called inside selection and projection. For example, filtering line items whose product code starts with a configured prefix:

    lines.?[#hasPrefix(product.sku, #requiredPrefix)]

Then retrieving the names of the matching products:

    lines.?[#hasPrefix(product.sku, #requiredPrefix)]
         .![product.name]

You can normalize the code for each line item:

    lines.![#normalizeCode(product.sku)]

On each call, an unprefixed property such as product.sku is read from the current element of the collection; the function is resolved by the name registered in the context.

If the function needs data from the root object, pass that data as an argument:

    lines.![#formatLine(product.name, #root.currency)]

Functions do not automatically receive the root object or #this as an implicit parameter. Required values must be included explicitly in the argument list.

## 9. Handling Nulls and Return Values

A function should clearly define how it handles null inputs. For example, normalizeCode above returns null when value is null. If business rules require a default value, you can combine the function with Elvis:

    #normalizeCode(customer?.code) ?: 'UNKNOWN'

Null-safe navigation protects reading code if customer might be null. The function receives the result of that expression; if it receives null, it returns null. Elvis then supplies UNKNOWN.

Distinguish between these cases:

- If customer is null and the expression uses customer.code directly, an error can occur before the function is called.
- If customer?.code is used, the argument may be null.
- If the function does not accept null, validate the input or guard the condition before calling it.
- If the function returns null, the outer expression can use Elvis or a condition to handle it.

For primitive parameters like int or boolean, null cannot be passed directly as a primitive value. If data may be missing, consider using wrapper types such as Integer or Boolean and define clear null rules.

## 10. Functions Should Be Pure and Narrowly Scoped

Functions are invoked while SpEL evaluates an expression. If a function performs side effects, the same expression may mutate state every time it is re-evaluated.

For example, a string normalization or scoring function is generally predictable:

    #normalizeCode(customer.code)
    #calculateRiskScore(order.total, #customerTier)

A function that sends emails, writes to a database, or deducts money can cause hard-to-control actions if the expression is evaluated multiple times, invoked in a loop, or rechecked in a processing flow.

Prefer functions that:

- Have clear inputs and outputs.
- Do not depend on external mutable state.
- Do not perform I/O or mutate business data.
- Can be tested independently with Java unit tests.
- Have reasonable computational cost bounds.

If a business action needs to be performed, let a Java service handle transactions, authorization, retries, and logging. SpEL should evaluate or compute small conditions, not become the orchestrator for actions with side effects.

## 11. Lifecycle of Expression and EvaluationContext

If the expression string does not change, you can parse it once and reuse the Expression:

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression =
            parser.parseExpression(
                    "#normalizeCode(customer.code)");

For each evaluation, supply a context with the registered functions and appropriate root object:

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    context.registerFunction("normalizeCode", normalizeMethod);

    String code =
            expression.getValue(context, String.class);

Expression retains the parsed expression structure. EvaluationContext provides functions, variables, and the root object for the current evaluation.

StandardEvaluationContext is a mutable object. Do not share a context that is being updated across multiple concurrent requests if those requests have different functions, variables, or root objects. Create a context per evaluation or manage sharing and synchronization intentionally.

There is also no need to re-parse the expression just because the root object changes. The same Expression can be used with a new context, as long as the function names and expression semantics remain compatible.

## 12. Common Mistakes When Registering Static Functions

| Situation | Cause | Resolution |
|---|---|---|
| #normalizeCode(...) not found | Not registered or wrong function name | Check registerFunction/setVariable and the alias name |
| Reflection throws NoSuchMethodException | Wrong method name or parameter types when retrieving Method | Use the exact signature in getMethod |
| Method cannot be invoked | Method is not public or not static | Register a suitable public static method |
| Function called with wrong argument count | Expression does not match the Method signature | Check parameter count and types |
| Function unexpectedly receives null | Input property may be null | Use null-safe navigation and define a null policy |
| Registered function gets overwritten | Name collision in variable namespace | Use unique names and centralize registration |
| Expression fails when calling function | Error inside the static method itself or argument conversion | Check the root cause and test the method independently |

When debugging, split the process into two steps: first verify that Java retrieves the right Method and registers it successfully; then verify that the SpEL expression calls the right alias with the right arguments. This helps separate reflection/configuration errors from expression evaluation errors.

## 13. Security Boundaries When Registering Functions

Registering a function allows expressions to invoke a chosen Java method. Therefore, the set of registered functions is part of the permission surface that expressions can use.

Some principles:

- Only register methods that rules actually need.
- Prefer small, pure public static methods without side effects.
- Do not register methods capable of executing system commands, accessing arbitrary files, making network calls, or manipulating sensitive data without dedicated controls.
- Do not evaluate arbitrary SpEL strings from external users inside a broadly privileged StandardEvaluationContext.
- Validate arguments inside the method and enforce authorization in services before sensitive actions.
- Log rule identifiers and necessary errors, avoiding logging sensitive data or full payloads.

A function alias does not automatically create a sandbox for the Java method. A registered static method still runs with the application's privileges. Therefore, only register permitted functions and control the source of expressions.

## 14. Testing Functions and Expressions Calling Functions

You should test the static method independently first, then test integration with SpEL.

For normalizeCode, test cases to verify include:

- Normal string: verify the result is normalized.
- String with leading/trailing whitespace: verify trimming.
- Lowercase string: verify conversion to uppercase.
- null: verify the policy returns null or the specified value.
- Empty string: verify the result matches business rules.

At the SpEL level, additionally check:

- Whether the method is registered under the correct alias.
- Whether the expression parses successfully.
- Whether arguments from the root object and context variables are passed correctly.
- Whether the return type from getValue is appropriate.
- Whether errors in the method are propagated and handled properly.
- Whether the function works properly when invoked inside selection/projection.

If expressions are externally configured, validate and store the parse result before putting the rule into a processing flow. An expression that parses successfully can still fail at runtime if a function is unregistered or runtime data is invalid.

## Conclusion

A static method can be registered in StandardEvaluationContext as a function using registerFunction(name, method), or placed into the context using setVariable(name, method). In an expression, call the function using the #functionName(arguments) syntax. The method must be static because SpEL invokes it without an instance receiver.

Distinguish registered functions from direct static method calls via T(Type).method(...). Functions are suitable when you want to provide a clear alias and restrict the set of functions rules can use; calls via T(...) are suitable when expressions need to reference a class directly. Keep functions small and easy to test, define argument types and null behavior clearly, manage the EvaluationContext lifecycle, and register only trusted methods.