# Passing Literals, Properties, and Expressions as Arguments When Invoking Methods in SpEL

When invoking a method with Spring Expression Language (SpEL), each argument inside parentheses can be a literal, a property, or another expression. SpEL evaluates each argument to obtain its runtime value, then uses the method resolution mechanism to find the matching method on the target object. Understanding the argument forms and their data types helps write concise calls, avoid type conversion errors, and keep expressions easy to test.

## 1. Method invocation syntax and argument list

The basic syntax is the method name followed by a comma-separated list of arguments:

    methodName(argument1, argument2, ...)

A method can be invoked on the root object, on a property of the root object, or on a variable in the EvaluationContext.

Example of invoking a method on the root object:

    calculateDiscount('VIP', total, quantity)

If the root object has a `calculateDiscount` method, SpEL will locate and invoke that method. In this example:

- `'VIP'` is a string literal.
- `total` is a property of the root object.
- `quantity` is also a property of the root object.

When invoking a method on a variable, use the `#` symbol to reference the variable:

    #pricingService.quote('EXPRESS', #order.total)

Here `pricingService` and `order` are variables registered in the EvaluationContext. The `#` symbol distinguishes a variable from a property looked up on the root object.

The order of arguments in the expression corresponds to the parameter order of the selected method. The number and types of arguments must match an invocable method on the target.

## 2. Passing literals as arguments

A literal is a value written directly in the expression. Common types include:

| Literal type | Example | Passed value |
|---|---|---|
| String | `'EXPRESS'` | String |
| Integer | `10` | Integer literal |
| Long integer | `10L` | Long |
| Floating-point | `19.95` | Double |
| Boolean | `true`, `false` | Boolean |
| Null | `null` | null |

Example:

    #shippingService.calculate('EXPRESS', 10, true)

This call passes three values directly: the shipping service name, quantity, and priority flag. Literals are suitable when values are fixed, short, and immediately clear at the call site.

String literals containing single quotes can be passed by escaping them according to SpEL's string syntax. When a string is long or requires processing input data, place the value into the context as a variable to avoid making the expression hard to read.

Do not confuse a literal with a property name. `'status'` is a string with content status, whereas `status` accesses the property named status on the current target.

## 3. Passing properties of the root object as arguments

When the EvaluationContext has a root object, you can use property names directly in the expression to read values from the root object:

    applyDiscount('MEMBER', subtotal, customer.level)

Suppose the root object is Order and has properties `subtotal` and `customer`. SpEL reads their values and passes them to the `applyDiscount` method.

If the root object is referenced through a variable, the syntax is:

    #order.applyDiscount('MEMBER', #order.subtotal, #order.customer.level)

Both approaches are valid in their respective contexts. Use a property without `#` when reading from the root object; use `#variable` when the value is registered as a variable.

Nested properties can be passed as arguments:

    #notificationService.send(
        #order.customer.name,
        #order.customer.email
    )

Property paths are evaluated when the expression runs. If an intermediate object is null, reading the next property can cause an evaluation error. Safe navigation can be used when null is an acceptable case:

    #notificationService.send(
        #order.customer?.email
    )

When safe navigation returns null, the method receives a null argument if the parameter type permits it. Primitive parameters such as `int` or `boolean` cannot accept null; missing values must be handled before invoking the method.

## 4. Passing an expression as an argument

An argument is not limited to an already-existing value. You can place a calculation expression inside the argument list. SpEL evaluates the sub-expression and passes the result to the method.

Example using arithmetic operations:

    #pricingService.quote(
        #order.subtotal,
        #order.quantity * #order.unitPrice
    )

The second argument is the result of the multiplication `quantity * unitPrice`, not an expression string passed verbatim to the method.

A conditional expression can be used:

    #shippingService.calculate(
        #order.weight,
        #order.priority ? 'EXPRESS' : 'STANDARD'
    )

The conditional operator selects one of the two strings based on the value of the `priority` property, then passes the selected string into the method.

Another method call can also be an argument:

    #reportService.createSummary(
        #order,
        #order.items.size()
    )

Here `#order.items.size()` is a nested method call. The resulting element count is passed into the `createSummary` method.

When a sub-expression is long, extract it into a variable in Java or format the expression across multiple lines. This makes it easier to inspect each intermediate value and avoids an unreadable method call.

## 5. Combining literals, properties, and expressions in a single call

Multiple kinds of arguments can be combined in the same method call. For example, a quoting service accepts customer tier, order value, item count, and discount amount calculated from data:

    #pricingService.quote(
        'MEMBER',
        #order.subtotal,
        #order.items.size(),
        #order.subtotal * #discountRate
    )

Suppose the variables `pricingService`, `order`, and `discountRate` have been registered in the context. The call consists of:

1. String literal `'MEMBER'`.
2. Property `#order.subtotal`.
3. Expression `#order.items.size()`.
4. Arithmetic expression `#order.subtotal * #discountRate`.

Java example illustrating how to prepare the context:

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setVariable("pricingService", pricingService);
    context.setVariable("order", order);
    context.setVariable("discountRate", new BigDecimal("0.05"));

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression = parser.parseExpression(
            "#pricingService.quote(" +
            "'MEMBER', " +
            "#order.subtotal, " +
            "#order.items.size(), " +
            "#order.subtotal * #discountRate)"
    );

    Object quote = expression.getValue(context);

This approach keeps business data in Java objects and only describes how to combine them in SpEL. If the expression is used repeatedly, you can parse the Expression once and evaluate it with the appropriate context for each call.

## 6. Argument types and conversion when invoking methods

Methods are declared with specific parameter types. SpEL must find a method matching the number and types of the evaluated arguments.

For example, the method:

    BigDecimal quote(String tier, BigDecimal amount)

requires a String and a BigDecimal. If the second argument is a value of a compatible type, SpEL can select that method. When needed, the EvaluationContext's type conversion mechanism can convert an argument to the parameter type required by the method.

StandardEvaluationContext uses ReflectiveMethodResolver by default to resolve methods via reflection. Method selection and argument conversion depend on the resolver and TypeConverter configured in the context.

For example, if a method accepts Long, pass an explicit Long value when possible:

    #counterService.setLimit(100L)

If the source value is a String, do not rely on the assumption that every string automatically converts to a numeric type in every context. Parse and validate the data beforehand, or configure an appropriate converter and check for conversion errors.

Type conversion is not synonymous with business validation. A string may convert to an Integer successfully yet still fall outside the bounds accepted by the method. The method or application layer still needs to check the relevant rules.

## 7. Method overloading and arguments with ambiguous types

A class can declare multiple methods with the same name but different parameter types:

    String format(Integer value)
    String format(Long value)
    String format(String value)

When SpEL calls an overloaded method, ReflectiveMethodResolver needs to select the method matching the actual argument types. If multiple overloads can accept the argument after conversion, the selection may not match the business intent or may fail to resolve.

To avoid ambiguity:

- Prepare variables with explicit types in Java before evaluation.
- Use literal suffixes such as `L`, `F`, or `D` when you want to indicate the numeric type explicitly.
- Convert Strings to the target type explicitly before the call.
- Avoid overloading too many methods with the same name if they are frequently called from dynamic expressions.
- Check the runtime types of arguments and the actual method invoked in tests.

For example, instead of passing an integer literal when a method expects Long, you can use:

    #counterService.setLimit(100L)

Or prepare a variable:

    context.setVariable("limit", Long.valueOf(100));
    #counterService.setLimit(#limit)

The second approach is useful when the value comes from an external data source or needs validation before calling.

## 8. Null arguments and missing data

The `null` literal or a property returning null can both be used as arguments if the method accepts null values:

    #profileService.updateNickname(#user.nickname)

If `nickname` is null and the method accepts String, the call can proceed with a null argument. However, if the method accepts a primitive type, such as `int`, null cannot be converted into a valid value.

When there are multiple overloads accepting different reference types, null can make method selection ambiguous. Normalize the value or call a method with a clear signature instead of relying on overload selection in the null case.

Safe navigation can be used to avoid errors when an intermediate property does not exist:

    #profileService.updateEmail(#user.contact?.email)

Safe navigation only handles null access paths according to supported syntax. It does not generate a fallback value and does not guarantee that the target method accepts null. If a default value is needed, use the conditional operator or prepare a variable in Java.

## 9. Varargs arguments and parameter lists

Java methods can declare varargs parameters, for example:

    void notifyUsers(String subject, String... recipients)

SpEL can invoke varargs methods when the resolver finds a matching signature. When an expression has multiple trailing arguments, verify how they match the varargs array and element type. For complex calls, passing a pre-typed array or collection from Java may be clearer.

Do not confuse a collection passed as a single argument with multiple separate arguments. For example:

    #reportService.export(#order.items)

passes one collection as a single argument; whereas:

    #reportService.notify('Ready', 'a@example.com', 'b@example.com')

is a call with multiple trailing arguments, which can match the corresponding varargs method.

If a method accepts an array, verify the array type and element type. If a method accepts List, pass an appropriate collection rather than assuming SpEL automatically converts every collection to an array or vice versa.

## 10. Debugging and testing method calls

When a call does not work, check in order:

1. Is the target object null?
2. Is the method name correct and is the method accessible in the context?
3. Does the argument count match the method signature?
4. What is the runtime type of each argument?
5. Are there competing or ambiguous overloads?
6. Does TypeConverter support the required conversion?
7. Does a property or sub-expression return null or throw an exception?

You can inspect the type of an argument before evaluating the expression:

    Object amount = context.lookupVariable("amount");

    System.out.println(amount);
    System.out.println(amount == null
            ? "null"
            : amount.getClass().getName());

Write separate tests for literals, properties, nested expressions, null, different numeric types, and overloads. For methods with side effects, tests should verify both the return value and the changes on objects or mock services.

## 11. Restricting permissions when invoking methods via SpEL

Method invocation can execute business logic, access data, or mutate state. If expressions come from users or configurations that are not fully trusted, restrict which objects and methods can be accessed.

SimpleEvaluationContext does not enable instance method invocation by default; the application must explicitly configure it if this capability is needed. StandardEvaluationContext provides broader reflection capabilities, so do not put a sensitive service into the context and allow expressions to arbitrarily call all public methods.

Put only the services needed for the use case into the context. Prefer methods with narrow purposes, clear parameters, and minimal side effects. Validate input data in Java or in the business layer before performing important operations.

## 12. Summary

Method arguments in SpEL can be literals, properties, or expressions evaluated at call time. Use properties directly when reading data from the root object, and use `#variable` when reading data from the EvaluationContext. The method resolver selects a method matching the number and types of arguments; TypeConverter can assist with conversion when needed. For overloads, null, varargs, or dynamic input data, clarify argument types and test the actual method signatures. When expressions can invoke services or mutate state, restrict the context and allow only the methods that the use case requires.
