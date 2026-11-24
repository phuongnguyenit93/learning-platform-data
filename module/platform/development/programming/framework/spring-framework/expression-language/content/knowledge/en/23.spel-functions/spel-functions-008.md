# Function Signatures, Type Conversion, and Evaluation Errors

In SpEL, a function is a Java method registered in an EvaluationContext so that an expression can call it by name. During registration, the application supplies a Method object, so the method's Java signature determines the number, order, and types of parameters that the function accepts. During evaluation, SpEL retrieves arguments from the expression, performs type conversion if supported by TypeConverter, invokes the method, and uses the return value as the expression result.

Three parts need to be understood separately: the function signature, data conversion, and evaluation errors. A function can be registered successfully yet the call still fails because arguments are incompatible, the converter cannot handle the source type, or the method itself throws an exception. Distinguishing these stages helps diagnose the exact cause.

## 1. What is a Function in SpEL?

A function is a Java method placed into EvaluationContext under a name that expressions can reference with the # prefix.

Call syntax:

~~~text
#functionName()
#functionName(argument)
#functionName(argument1, argument2)
~~~

The function name in the context does not include #. The # symbol only appears in the expression when invoking the function.

For example, a function library:

~~~java
public class TextFunctions {

    public static String normalize(String value) {
        return value == null ? "" : value.trim().toLowerCase();
    }
}
~~~

Registering and calling:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext();

Method normalizeMethod =
        TextFunctions.class.getMethod("normalize", String.class);

context.registerFunction("normalize", normalizeMethod);

Expression expression =
        parser.parseExpression("#normalize('  Spring  ')");

String result = expression.getValue(context, String.class);

System.out.println(result); // spring
~~~

SpEL does not automatically discover every static method on the classpath by function name. A function can only be invoked if the application registers it in the active context or provides a corresponding mechanism.

## 2. Method Signature Defines the Function Contract

When registering a function, the application supplies a java.lang.reflect.Method object. That Method defines:

- The method name and declaring class.
- The number of parameters.
- The order of parameters.
- The Java type of each parameter.
- The return type.
- Any exceptions the implementation can throw.

Example:

~~~java
public class PriceFunctions {

    public static BigDecimal calculateTax(
            BigDecimal amount,
            BigDecimal rate) {

        return amount.multiply(rate);
    }
}
~~~

Registering the exact signature:

~~~java
Method taxMethod = PriceFunctions.class.getMethod(
        "calculateTax",
        BigDecimal.class,
        BigDecimal.class
);

context.registerFunction("calculateTax", taxMethod);
~~~

The expression must provide two arguments in the exact order:

~~~text
#calculateTax(#amount, #taxRate)
~~~

The first argument is passed to amount, and the second argument is passed to rate. If the order is swapped or the wrong number of parameters is supplied, calling the function can fail at evaluation time.

Use concrete parameter types that reflect the data contract. Avoid declaring all parameters as Object just to make expressions easier to call, because that shifts many type errors inside the method and makes the contract hard to verify.

## 3. Registering a Method via Reflection

You can obtain a Method using Class.getMethod or Class.getDeclaredMethod. getMethod finds public methods, including inherited methods; getDeclaredMethod finds methods declared directly on the class and can return non-public methods.

Example:

~~~java
Method method = TextFunctions.class.getMethod(
        "normalize",
        String.class
);

context.registerFunction("normalize", method);
~~~

For functions used in applications, prefer public static methods with clear signatures. The function registration API takes a specific Method, so the method is chosen right when configuring the context.

If a class has multiple overloads with the same name, select the exact signature when obtaining the Method. SpEL does not resolve function overloads solely based on the registered name the way regular instance method resolution works; the function name is bound to the registered Method.

If multiple invocation forms are needed, you can register distinct function names or create a wrapper method with a unified signature to dispatch in Java.

## 4. Calling Functions Without and With Arguments

A zero-argument function is called with empty parentheses:

~~~text
#currentTimestamp()
#defaultLocale()
~~~

A function with one or more parameters places arguments inside parentheses:

~~~text
#normalize(#rawName)
#calculateTax(#amount, #rate)
#formatLabel('Order', #orderNumber)
~~~

Arguments can be literals, context variables, properties of the root object, or another expression. SpEL evaluates the arguments to obtain values to pass into the method.

Example:

~~~java
context.setVariable("amount", new BigDecimal("250.00"));
context.setVariable("rate", new BigDecimal("0.08"));

Expression expression = parser.parseExpression(
        "#calculateTax(#amount, #rate)"
);

BigDecimal tax = expression.getValue(context, BigDecimal.class);
~~~

Keep argument order consistent with the Java signature. When a function has multiple parameters of the same type, swapping arguments may not cause a runtime error yet still produce the wrong business result. Use meaningful variable names and wrappers with clear parameters to reduce confusion.

## 5. Functions and Instance Methods Are Different Mechanisms

A registered function is called via #functionName(...). An instance method is called on the root object, a variable object, or a property object:

~~~text
#normalize(#rawText)
#customer.getDisplayName()
#order.calculateTotal()
~~~

Both syntaxes may call a Java method, but how they are resolved differs:

| Invocation style | Method source | How it is referenced |
|---|---|---|
| Registered function | Method registered in the context | #functionName(args) |
| Instance method | Current target object or accessed object | object.method(args) |
| Static method via type reference | Class resolved by T(...) | T(com.example.Utility).method(args) |
| Spring bean method | Bean resolved via BeanResolver | @beanName.method(args) |

Registering a function is appropriate when you want to provide a small, stable API to expressions. If a method depends on the state of an instance, pass the object via root/variable or use a bean resolver instead of trying to register an instance method as a static function.

## 6. Function Names and Context Variables

A function is registered by name, for example normalize. In the expression, that name is referenced as #normalize.

Since Spring Framework 6.1, functions and variables share the same namespace in EvaluationContext. Therefore, do not register a function and a context variable with the same name expecting both to coexist independently. A later registration can replace the previous binding.

Example of conflicting names:

~~~java
context.registerFunction("format", formatMethod);
context.setVariable("format", "plain");
~~~

Use a separated naming convention, such as verbs for functions and nouns for variables:

~~~java
context.registerFunction("formatLabel", formatMethod);
context.setVariable("labelFormat", "plain");
~~~

This keeps expressions readable and avoids subtle errors when a context is configured in multiple places.

## 7. Type Conversion for Function Arguments

Arguments in an expression may have a different type from the Java parameter type. SpEL uses the EvaluationContext's TypeConverter to convert when an appropriate converter exists.

For example, a function expects an Integer, while the expression passes a String value:

~~~java
public class NumberFunctions {

    public static String describe(Integer value) {
        return "number=" + value;
    }
}
~~~

When a conversion service capable of converting String to Integer is configured, the call can use a suitable string value:

~~~text
#describeNumber('42')
~~~

Conversion capability depends on the active TypeConverter and registered converters. Do not assume every string can be converted to every type or that malformed data will be fixed automatically.

If conversion cannot be performed, the error surfaces during the function evaluation stage. Check the runtime type of the argument, the parameter type of the Method, and whether the converter supports the source/target type pair.

## 8. Configuring a Custom ConversionService

StandardTypeConverter can use a Spring ConversionService. If the application has custom domain types, register a converter and attach StandardTypeConverter to the EvaluationContext.

Example with a CustomerId type:

~~~java
public record CustomerId(String value) {
}

public class CustomerFunctions {

    public static String label(CustomerId id) {
        return "customer:" + id.value();
    }
}
~~~

Configuring conversion from String to CustomerId:

~~~java
DefaultConversionService conversionService =
        new DefaultConversionService();

conversionService.addConverter(
        String.class,
        CustomerId.class,
        CustomerId::new
);

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setTypeConverter(
        new StandardTypeConverter(conversionService)
);

Method labelMethod = CustomerFunctions.class.getMethod(
        "label",
        CustomerId.class
);

context.registerFunction("customerLabel", labelMethod);
~~~

Expression:

~~~text
#customerLabel('C-100')
~~~

When TypeConverter uses the configured ConversionService, the String argument can be converted into CustomerId before invoking the method.

A converter should have clear rules and validate input data. If an empty or malformed string cannot produce a valid CustomerId, throw a meaningful conversion error for the application to handle.

## 9. Return Type Conversion

A function returns the type declared by the Java method. If the expression is retrieved via a typed getValue overload, SpEL can convert the result to the target type if TypeConverter supports it.

Example:

~~~java
Expression expression = parser.parseExpression(
        "#calculateCount('12')"
);

Integer count = expression.getValue(context, Integer.class);
~~~

There are two conversion points to distinguish:

1. Argument conversion before invoking the function to match parameter types.
2. Return value conversion to the type requested by Java code when calling getValue(context, TargetType.class).

If a function returns BigDecimal while the code requests String, the result depends on whether the converter supports that conversion. Requesting a return type does not alter the function's Java signature and does not cause the method to execute with a different type.

When the return type is part of the business contract, declare the appropriate Java type directly in the function and only use typed getValue to enforce the type at the result-receiving boundary.

## 10. Conversion Is Not Validation

Conversion transforms a value from a source type to a target type. Validation checks whether a value is valid according to business rules.

For example, the string " -5 " can be converted into Integer -5 successfully. Yet if a function requires a positive quantity, that value is still invalid.

~~~java
public static int normalizeQuantity(Integer quantity) {
    if (quantity == null || quantity <= 0) {
        throw new IllegalArgumentException(
                "Quantity must be positive"
        );
    }
    return quantity;
}
~~~

A converter should only be responsible for type conversion. Business rules such as positive quantities, limits, access rights, or valid states should be checked in the appropriate function or service.

Do not treat successful conversion as proof that data is valid. Likewise, a function returning the right type does not mean the result satisfies all domain invariants.

## 11. Overloaded Signatures and Varargs

A registered function name binds to a specific Method. If a class has multiple overloads:

~~~java
public static String describe(String value) {
    return "text";
}

public static String describe(Integer value) {
    return "number";
}
~~~

explicitly select the overload when registering:

~~~java
Method textMethod = Functions.class.getMethod(
        "describe",
        String.class
);

context.registerFunction("describeText", textMethod);
~~~

The other overload can be registered under a different name:

~~~java
Method numberMethod = Functions.class.getMethod(
        "describe",
        Integer.class
);

context.registerFunction("describeNumber", numberMethod);
~~~

For varargs methods, pay attention to how Java reflection represents the last parameter as an array and how SpEL prepares arguments. Test invocations with actual argument counts on the running Spring version. If expressions are configured by multiple teams, a wrapper method with fixed parameters is often easier to understand and more stable.

## 12. Parse Errors and Evaluate Errors Occur in Two Stages

SpEL has two main stages:

- Parse: analyzes the expression string and builds an Expression.
- Evaluate: executes the Expression with an EvaluationContext and specific data.

Syntax errors typically appear in the parse stage as ParseException. Examples include missing parentheses, missing quotes, or malformed function call structure.

Errors in the evaluate stage typically appear as EvaluationException or a subclass such as SpelEvaluationException. Examples include an unregistered function, wrong arguments, failed type conversion, or an exception thrown by the method.

Example handling the two stages separately:

~~~java
Expression expression;

try {
    expression = parser.parseExpression(
            "#calculateTax(#amount, #rate)"
    );
} catch (ParseException ex) {
    // Invalid expression syntax
    throw ex;
}

try {
    BigDecimal result = expression.getValue(
            context,
            BigDecimal.class
    );
} catch (EvaluationException ex) {
    // Error resolving or evaluating the expression
    throw ex;
}
~~~

Separating the two stages identifies whether an error lies in the expression string or in runtime data/context. In real applications, you can parse once and reuse the Expression across many evaluations.

## 13. Common Causes of Evaluation Errors

| Symptom | Possible cause | What to check |
|---|---|---|
| Function not found | Name not registered or active context differs from configured context | Check registered name and context passed to getValue |
| Method not found during initialization | Wrong name or parameter type list when using reflection | Check getMethod/getDeclaredMethod |
| Wrong argument count | Expression does not match the Method signature | Compare parameter count and argument order |
| Incompatible argument | TypeConverter lacks a matching converter | Check runtime types and parameter types |
| Conversion failed | Malformed source value or converter rejected it | Check input data and conversion cause |
| Result has unexpected type | Return type incompatible with type requested by getValue | Check return signature and converter |
| Function throws exception | Error in the method's logic | Inspect the root cause of the evaluation error |
| Function disappears after registration | Name collided with a context variable | Use distinct function and variable names |
| Error only happens on one request | Context or input variables differ between evaluations | Check root object, variables, and TypeConverter |

Specific error messages and error codes may vary by Spring version and execution path. Rely on the exception type, cause, and actual input data rather than depending on the entire message string.

## 14. Diagnosing Function Errors Systematically

When a function does not behave as expected, check in this order:

1. Confirm that the expression string parses successfully.
2. Confirm that the right EvaluationContext is passed to getValue.
3. Confirm that the function is registered under the exact name, with no # in the registration name.
4. Confirm that the Method was retrieved from the exact class, name, and parameter types.
5. Check the count, order, and runtime types of arguments.
6. Check TypeConverter and ConversionService if type conversion is needed.
7. If the method executed and failed, inspect the root cause to locate the error inside the function.
8. Check the return type and target type of getValue.

You can log the expression name or rule ID, exception type, and root cause. Avoid logging all sensitive data in the context or argument values.

Do not catch every Throwable and return null, because that hides programming bugs, conversion errors, and business errors. Catch appropriate exceptions at the processing boundary and translate them into meaningful messages for the caller.

## 15. Safety When Providing Functions to Expressions

Registering functions increases what an expression can perform. If a function can write to a database, send email, make payments, or call APIs, an expression can trigger those actions when evaluated.

Some principles:

- Only register functions genuinely required for the use case.
- Prefer pure functions that do not mutate state and do not perform I/O.
- Use names that describe behavior and explicit parameter signatures.
- Validate data inside the function; do not rely on conversion to replace validation.
- Do not register broad-privilege repositories or services as convenient functions.
- Keep a separate EvaluationContext per evaluation when variables or the root object change.
- Do not treat hiding function names as an authorization mechanism.

If expressions are supplied by users or untrusted sources, you must control functions, MethodResolver, PropertyAccessor, TypeLocator, and BeanResolver. Registering only a few safe functions is part of restricting privileges, yet other access paths in the context still need restriction.

## 16. Complete Example: Function, Conversion, and Error Handling

The following example registers a fee calculation function taking two BigDecimal parameters, uses context variables, and retrieves a specifically typed result:

~~~java
public class BillingFunctions {

    public static BigDecimal calculateFee(
            BigDecimal amount,
            BigDecimal rate) {

        if (amount == null || rate == null) {
            throw new IllegalArgumentException(
                    "Amount and rate are required"
            );
        }

        if (amount.signum() < 0 || rate.signum() < 0) {
            throw new IllegalArgumentException(
                    "Amount and rate must be non-negative"
            );
        }

        return amount.multiply(rate);
    }
}
~~~

Configuration and evaluation:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext();

Method feeMethod = BillingFunctions.class.getMethod(
        "calculateFee",
        BigDecimal.class,
        BigDecimal.class
);

context.registerFunction("calculateFee", feeMethod);

context.setVariable("amount", new BigDecimal("250.00"));
context.setVariable("rate", new BigDecimal("0.08"));

Expression expression = parser.parseExpression(
        "#calculateFee(#amount, #rate)"
);

try {
    BigDecimal fee = expression.getValue(
            context,
            BigDecimal.class
    );

    System.out.println(fee); // 20.0000
} catch (EvaluationException ex) {
    // Log the evaluation error and handle it according to application policy
}
~~~

The Method signature defines two BigDecimal parameters. Context variables supply values for the call. The function enforces business invariants and returns BigDecimal. Typed getValue requests a BigDecimal result; since the function already returns the exact type, no result conversion is needed.

In real applications, decide scale and RoundingMode for monetary calculations at the business layer. The example above illustrates the signature and evaluation flow, without defining a rounding policy for every kind of fee.

## 17. Takeaways

A SpEL function is a Java Method registered in an EvaluationContext and called using the #functionName(args) syntax. The chosen Method determines the count, order, parameter types, and return type. With overloads, explicitly select the Method at registration or provide separate function names.

TypeConverter can convert arguments to match the signature and convert results to the type requested by getValue, if converters support it. StandardTypeConverter can use a custom ConversionService. Conversion only changes types; business validation must still be performed separately.

ParseException indicates an expression parsing error; EvaluationException and SpelEvaluationException typically indicate errors during evaluation, function resolution, conversion, or method execution. Separate parse from evaluate, verify the context and Method signature, inspect the root cause when a function fails, and only expose functions with an appropriate permission scope.