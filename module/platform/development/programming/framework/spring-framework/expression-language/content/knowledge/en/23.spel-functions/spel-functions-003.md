# Function Call Syntax with #functionName

## Objectives

Spring Expression Language (SpEL) allows an application to register a Java method as a function in an EvaluationContext, and then invoke that function from an expression using the **#functionName(arguments)** syntax. This makes it possible to expose a shared calculation or rule to expressions without duplicating logic in multiple places.

Functions in SpEL are typically implemented using a public static method. The application obtains the Method object via reflection, registers the method under a readable name, and the expression invokes that name with the required arguments.

After this lesson, you will be able to:

- Understand the function call syntax using #functionName.
- Register a public static method using StandardEvaluationContext.
- Pass literals, variables, and properties as arguments.
- Use function return values in conditions and collection operations.
- Distinguish functions from variables, properties, and instance methods.
- Check argument types, return types, and execution errors.
- Restrict which functions are permitted to be called from expressions.

## 1. Function Call Syntax

General syntax:

~~~text
#functionName(argument1, argument2, ...)
~~~

The # sign tells SpEL that this is a function name registered in the EvaluationContext. The function name during registration does not include the # sign; this sign only appears when referencing it in an expression.

Examples:

~~~text
#normalizeCode(' ab-123 ')
#isEligible(#customer, 18)
#calculateTax(#amount, #taxRate)
~~~

Arguments can be literals, variables, properties of the root object, results of another expression, or results from another function. If the function takes no arguments, the parentheses must still be written:

~~~text
#currentTimestamp()
~~~

A function returns a value. That value can be used as part of a larger expression, such as a comparison, property access, or argument passed into another function.

## 2. A Function Is a Registered Java Method

A SpEL function usually refers to a public static method. For example, create a utility class:

~~~java
package com.example.spel;

public class TextFunctions {

    public static String normalizeCode(String value) {
        if (value == null) {
            return null;
        }
        return value.trim().toUpperCase();
    }
}
~~~

The normalizeCode method takes a String and returns a String with leading and trailing whitespace removed and converted to uppercase.

The application needs to obtain the java.lang.reflect.Method object representing this method and register it in the EvaluationContext.

~~~java
Method normalizeMethod = TextFunctions.class.getMethod(
    "normalizeCode",
    String.class
);
~~~

getMethod looks up a public method by name and parameter types. If the method does not exist or the signature does not match, Java throws NoSuchMethodException when creating the configuration; it is best to catch this error at application startup rather than waiting until the expression runs.

## 3. Registering a Function in StandardEvaluationContext

Complete example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context = new StandardEvaluationContext();

Method normalizeMethod = TextFunctions.class.getMethod(
    "normalizeCode",
    String.class
);

context.registerFunction("normalizeCode", normalizeMethod);

Expression expression =
    parser.parseExpression("#normalizeCode(' ab-123 ')");

String result = expression.getValue(context, String.class);
~~~

The result is:

~~~text
AB-123
~~~

Main steps:

1. Create or obtain a StandardEvaluationContext.
2. Retrieve the Method of the public static method to expose.
3. Call registerFunction with the function name and the Method.
4. Parse the expression referencing #normalizeCode(...).
5. Evaluate the expression in the same context where the function was registered.

The name passed to registerFunction is normalizeCode, without the # sign. In the expression, you must write #normalizeCode(...). If the function is not registered in the context used for evaluation, SpEL cannot resolve that call.

Multiple functions can be registered on the same context:

~~~java
context.registerFunction("normalizeCode", normalizeMethod);
context.registerFunction("isValidCode", isValidCodeMethod);
context.registerFunction("calculateTax", calculateTaxMethod);
~~~

Only register the functions that expressions actually need.

## 4. Passing Arguments to a Function

A function can accept one or more arguments. The number and types of arguments must match the registered Java method signature.

Example:

~~~java
public class PricingFunctions {

    public static BigDecimal calculateTax(
            BigDecimal amount,
            BigDecimal taxRate) {
        return amount.multiply(taxRate);
    }
}
~~~

Register the function:

~~~java
Method calculateTaxMethod = PricingFunctions.class.getMethod(
    "calculateTax",
    BigDecimal.class,
    BigDecimal.class
);

context.registerFunction("calculateTax", calculateTaxMethod);
context.setVariable("amount", new BigDecimal("200.00"));
context.setVariable("taxRate", new BigDecimal("0.10"));
~~~

Call the function:

~~~text
#calculateTax(#amount, #taxRate)
~~~

The result is a BigDecimal with value 20.00.

Arguments can also be properties of the root object:

~~~text
#calculateTax(#root.subtotal, #root.taxRate)
~~~

Or combine a literal with a variable:

~~~text
#calculateTax(#root.subtotal, 0.10)
~~~

In financial applications, use BigDecimal consistently for amounts and rates. Avoid passing floating-point numbers and relying on implicit conversion when decimal precision matters.

### Argument types and conversion

SpEL has a type conversion mechanism through the EvaluationContext's TypeConverter in supported situations. Even so, pass arguments whose types are compatible with the registered method. Especially with overloads or numeric types, test real values to avoid selecting the wrong type or encountering runtime conversion errors.

A function is registered with a specific Method. If different behavior is needed for that signature, register another function with a clear name or write an intermediate Java method with a stable signature.

## 5. Using the Return Value of a Function

A function's result is a regular SpEL value. The result can be compared:

~~~text
#isValidCode(#root.code) == true
~~~

Used in a condition:

~~~text
#isEligible(#root.customer, #minimumAge) and #root.account.active
~~~

Or passed as an argument to another function:

~~~text
#formatLabel(#normalizeCode(#root.code))
~~~

If the function returns an object, the expression can continue reading properties or calling context-supported operations on that object:

~~~text
#parseCustomer(#root.rawCustomer).status
~~~

The return type must fit how it is used next. If the method returns null, the subsequent expression must handle null properly. Safe navigation can guard property access on a null result:

~~~text
#parseCustomer(#root.rawCustomer)?.status
~~~

Safe navigation does not handle errors inside the function. If the method throws an exception, evaluation still fails.

## 6. Using Functions in Collection Selection

A function can encapsulate a shared condition and be called for each element in a collection.

Java example:

~~~java
public class CustomerFunctions {

    public static boolean isEligible(Customer customer, int minimumAge) {
        return customer != null
            && customer.getAge() >= minimumAge
            && customer.isActive();
    }
}
~~~

Registration:

~~~java
Method eligibleMethod = CustomerFunctions.class.getMethod(
    "isEligible",
    Customer.class,
    int.class
);

context.registerFunction("isEligible", eligibleMethod);
context.setVariable("minimumAge", 18);
~~~

Selection:

~~~text
#root.customers.?[#isEligible(#this, #minimumAge)]
~~~

In selection, #this is the current Customer. #minimumAge is a variable passed into the context by the application. The function returns a Boolean to decide whether the element is kept.

Functions can be used in projection:

~~~text
#root.customers.![#normalizeCode(#this.code)]
~~~

The result is a list of normalized codes. Avoid functions with side effects in selection or projection because SpEL may call the function multiple times, once for each element.

## 7. Distinguishing Functions from Variables, Properties, and Methods

The following syntaxes have different meanings:

| Syntax | Meaning |
|---|---|
| **#normalizeCode('ab')** | Calls a function registered in EvaluationContext |
| **#minimumAge** | Reads the minimumAge variable in EvaluationContext |
| **#root.name** | Reads the name property of the root object |
| **#this.name** | Reads the name property of the current object |
| **#root.normalizeCode()** | Calls an instance method on the root object, if the context permits |

Functions are registered by name and invoked with #functionName(...). Instance methods are called on a specific object using object.method(...) syntax. These two mechanisms do not replace one another.

A function is also not automatically a Spring bean. Registering a static Method does not make the containing class a bean, and does not enable dependency injection for that method.

If the logic requires Spring-managed services, repositories, or clients, do not try to turn a static function into a holder for dependencies. Implement the logic in a Java service or use a properly configured and controlled bean reference mechanism.

## 8. Functions and EvaluationContext Lifecycle

Functions are registered on an EvaluationContext. When the application creates a new context, it must re-register the required functions in that context or use a shared factory to build the context.

Simple factory example:

~~~java
public class SpelContextFactory {

    public StandardEvaluationContext create(Object rootObject)
            throws NoSuchMethodException {

        StandardEvaluationContext context =
            new StandardEvaluationContext(rootObject);

        Method normalizeMethod = TextFunctions.class.getMethod(
            "normalizeCode",
            String.class
        );

        context.registerFunction("normalizeCode", normalizeMethod);

        return context;
    }
}
~~~

Centralized context creation avoids having one evaluation flow with the function registered while another lacks it.

An Expression can be parsed once and reused. However, the context holding the root object, variables, and function registrations needs a lifecycle appropriate for the application's data and concurrency.

Do not share a mutable context across multiple requests if requests can overwrite each other's variables or root objects. Create a separate context per request or use an appropriate immutable configuration.

## 9. Handling Nulls and Exceptions

A function must clearly define how null arguments are handled. There are two common choices:

- Accept null and return a defined value, for example normalizeCode(null) returns null.
- Reject null by throwing an exception with a clear message if the input is required.

Do not let null behavior rely on accidental errors like NullPointerException when the contract can be defined directly inside the method.

If a function throws an exception during evaluation, SpEL reports an evaluation error and the original exception may be in the cause chain. When handling errors:

- Identify which function was called.
- Check the number and types of arguments.
- Check null values and boundary data.
- Inspect the original exception from the Java method.
- Do not turn every error into null if null is not a valid business result.

You can wrap errors at the application boundary to provide a stable business message while preserving the cause for diagnostics.

## 10. Restrictions and Safety When Exposing Functions

A function opens a Java method to expressions. Therefore, registering a function is a decision about the capabilities that expressions are allowed to perform.

Principles:

- Only register methods with a clear purpose that are needed by expressions.
- Prefer pure functions: accept inputs, return a result, and do not mutate external state.
- Avoid exposing methods that write to a database, send emails, open connections, or perform I/O if the expression only needs calculation.
- Do not register methods that can access files, processes, credentials, or resources outside business scope.
- Validate argument types and value ranges inside the Java method.
- Do not include sensitive data in function results or unnecessary logs.
- Control expression sources; users can invoke any exposed functions if they can author expressions.
- Use an EvaluationContext with the minimum necessary scope of privileges.

A function name is not an authorization mechanism. If a user is permitted to call a function, that method must still ensure that the inputs and operation are permitted according to business rules.

## 11. Common Errors and Diagnostics

| Symptom | Possible cause | Resolution |
|---|---|---|
| Cannot resolve function | Function not registered in the active context or wrong name | Check registerFunction and the #functionName name |
| Error retrieving Method | Wrong method name or parameter signature | Check class, method, and parameter types in getMethod |
| Function is not called | Missing #, missing parentheses, or mistakenly using instance method syntax | Check #name(arguments) |
| Wrong argument count | Expression passes a different number of arguments than the Method signature | Compare the call against the Java declaration |
| Argument type error | Actual type is incompatible or conversion is unsuitable | Standardize types before calling and test TypeConverter |
| Function unexpectedly returns null | Null argument or method logic has a branch returning null | Define a null contract and validate inputs |
| Error accessing the result | Function returns null or a different return type than expected | Check return type and use safe navigation where appropriate |
| Works in one context but not another | Second context has not registered the function | Use a shared context factory |
| Unstable results | Function has side effects or depends on mutable state | Make the function pure or manage state outside the expression |

When diagnosing, separate Method configuration errors from expression parse errors and runtime errors inside the function. Retrieving the Method should be verified at application startup; expression evaluation should be tested with representative data.

## 12. Testing Functions

Tests should verify that the method is registered, the expression invokes the right function, and the result has the expected type.

Example:

~~~java
@Test
void callsRegisteredFunction() throws Exception {
    ExpressionParser parser = new SpelExpressionParser();
    StandardEvaluationContext context = new StandardEvaluationContext();

    Method method = TextFunctions.class.getMethod(
        "normalizeCode",
        String.class
    );

    context.registerFunction("normalizeCode", method);

    Expression expression =
        parser.parseExpression("#normalizeCode(' ab-123 ')");

    assertEquals("AB-123", expression.getValue(context, String.class));
}
~~~

Test cases should include:

- Function registered under the correct name.
- Unregistered function.
- Wrong function name.
- Correct and incorrect argument counts.
- Compatible and incompatible argument types.
- Null arguments.
- Boundary values and invalid data.
- Function returning null.
- Function returning Boolean, number, String, or object.
- Function called inside selection/projection.
- A new context created via the factory still has all functions.
- Function does not produce unexpected side effects.

If a function uses reflection to retrieve a Method, check configuration errors at startup and prevent the application from activating expressions that depend on missing functions.

## 13. Process for Adding a New Function

When you need to provide an operation to SpEL:

1. **Define the purpose.** Choose a small calculation or rule that expressions genuinely need.
2. **Write a public static method.** Declare explicit argument types, return type, and null behavior.
3. **Check for side effects.** Ensure the method does not mutate state or perform unintended actions.
4. **Obtain the Method via reflection.** Use the exact method name and parameter type list.
5. **Register in the context.** Use a short, stable name without the # sign in registerFunction.
6. **Call in the expression.** Use the #functionName(arguments) syntax.
7. **Test.** Cover argument types, null values, results, and runtime errors.
8. **Control permissions.** Only expose the function to expressions and user sources authorized to call it.

If a function starts requiring many dependencies or involves multiple business steps, move the logic into a Spring-managed Java service. SpEL should express conditions or combine results, not become the orchestrator for the entire application.

## 14. Best Practices

- Register public static methods using registerFunction(name, method).
- Use a name without # when registering and #name(...) when calling.
- Keep functions small, with descriptive behavior names and stable signatures.
- Use specific Java types for arguments and return values.
- Check nulls and boundary data directly inside the function.
- Reuse Expression while managing EvaluationContext according to data lifecycle.
- Use a context factory to register functions consistently.
- Use pure functions in selection/projection to avoid side effects when called repeatedly.
- Do not use static functions to replace services with dependency injection.
- Only expose necessary functions and control expression sources.
- Test both reflection configuration and runtime behavior.
- Move multi-step business logic into Java when expressions become hard to read.

## 15. Review Checklist

Before approving an expression that calls a function, check:

- [ ] Does the function have a clear name and purpose?
- [ ] Is the Java method public static with an appropriate signature?
- [ ] Is the Method retrieved via reflection with the exact parameter types?
- [ ] Is the function registered in the right EvaluationContext?
- [ ] Is the registration name free of #; does the expression call #functionName(...)?
- [ ] Are the argument count and types appropriate?
- [ ] Is the return type used properly in the expression?
- [ ] Do nulls and exceptions have a clear contract?
- [ ] Does the function avoid unwanted side effects?
- [ ] Is the function not being used to replace dependency injection?
- [ ] Does the context factory register functions consistently across tests and production?
- [ ] Are expression sources and the exposed function set controlled?

## Conclusion

SpEL invokes functions using the **#functionName(arguments)** syntax after the application registers a Java Method in an EvaluationContext. The common approach is to use a public static method, obtain the Method via reflection, and call registerFunction on StandardEvaluationContext. Functions can accept variables, properties, and literal values; their results can continue to be used in conditions, selection, or projection. Keep functions small, with clear data types and null behavior, avoid side effects, register them consistently in each context, and only expose operations that expressions are permitted to perform.