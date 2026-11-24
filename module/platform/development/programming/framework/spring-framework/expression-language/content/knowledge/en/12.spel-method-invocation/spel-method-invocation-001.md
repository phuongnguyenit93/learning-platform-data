# Invoking Methods Without Parameters and With Parameters

SpEL allows invoking methods on the root object, nested objects, variables, or beans provided by the EvaluationContext. Method invocation syntax has parentheses after the method name. If the method takes no parameters, use an empty pair of parentheses; if the method has parameters, place the arguments in the correct order inside the parentheses.

The ability to invoke methods helps expressions not only read properties but also use behavior exposed by objects. However, a method call can execute complex logic or mutate state. Therefore, understand how SpEL resolves methods and choose appropriate methods so that expressions remain predictable and easy to control.

## 1. Basic method invocation syntax

General syntax:

~~~text
methodName()
methodName(argument1)
methodName(argument1, argument2)
object.methodName()
object.methodName(argument1, argument2)
~~~

Parentheses are required to represent a method call. Without parameters, you must still write an empty pair of parentheses.

Examples:

~~~text
name.toUpperCase()
name.substring(0, 3)
items.size()
items.get(0)
~~~

The expressions above respectively invoke methods on a string or a collection. The result of the method becomes the value of the expression and can be used further in string concatenation, comparisons, calculations, or other method calls.

Distinguishing property access from method invocation:

~~~text
customer.displayName
customer.getDisplayName()
~~~

The first expression accesses the displayName property through a property accessor. The second expression explicitly invokes the getDisplayName() method. Both may return the same data, but the syntax expresses two different operations.

## 2. Invoking a no-parameter method on the root object

When an EvaluationContext has a root object, you can invoke a method of the root object directly without writing a variable name or special prefix.

Suppose there is a Profile class:

~~~java
public class Profile {

    private final String displayName;

    public Profile(String displayName) {
        this.displayName = displayName;
    }

    public String greeting() {
        return "Hello " + displayName;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

You can parse and evaluate the greeting() call:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Profile profile = new Profile("Lan");

EvaluationContext context =
        new StandardEvaluationContext(profile);

Expression expression = parser.parseExpression("greeting()");

String message = expression.getValue(context, String.class);

System.out.println(message); // Hello Lan
~~~

In this example, profile is the root object. When SpEL encounters greeting(), the method resolver finds the matching method on the root object and invokes it. There is no need to write profile.greeting() because profile itself is already the root object of the context.

If the context is created without a root object, a method call without a target object cannot be resolved in the manner above. In that case, you need to set a root object or invoke the method through a provided variable, property, or bean.

## 3. Invoking a method with one or more parameters

Arguments are written inside parentheses, separated by commas. SpEL supports passing literals, variables, properties, or the result of another expression as arguments.

Suppose Profile has additional methods:

~~~java
public String greet(String name) {
    return "Hello " + name;
}

public String formatName(String prefix, String suffix) {
    return prefix + displayName + suffix;
}
~~~

They can be invoked as follows:

~~~java
Expression greet = parser.parseExpression("greet('Minh')");
String first = greet.getValue(context, String.class);

Expression format = parser.parseExpression(
        "formatName('Mr. ', ' Nguyen')"
);
String second = format.getValue(context, String.class);
~~~

In SpEL, string literals are enclosed in single quotes. Numeric literals can be written directly without quotes; Booleans use true or false; null values use null.

Examples:

~~~text
calculate(10, 20)
setEnabled(true)
findByCode('SP-100')
combine('Spring', 6)
~~~

The number and order of arguments must match the selected method. If the method requires two parameters, the call must provide two arguments, unless the method has a varargs declaration or another matching overload exists.

## 4. Passing variables as arguments

There is no need to embed dynamic data into the expression string. You can place values into the EvaluationContext as variables and reference them with the # prefix.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Profile profile = new Profile("Lan");
StandardEvaluationContext context =
        new StandardEvaluationContext(profile);

context.setVariable("targetName", "Minh");

Expression expression =
        parser.parseExpression("greet(#targetName)");

String message = expression.getValue(context, String.class);
~~~

The variable #targetName is retrieved from the context and passed as an argument to greet(String). This approach is useful when the expression is stored in configuration while the actual value varies by request or business data.

Multiple variables can be passed:

~~~java
context.setVariable("prefix", "Hello ");
context.setVariable("suffix", "!");

Expression expression = parser.parseExpression(
        "formatName(#prefix, #suffix)"
);
~~~

Use meaningful variable names and keep them consistent between where variables are configured and where expressions are written. If a variable is not registered or its name is misspelled, SpEL cannot resolve the corresponding argument.

## 5. Arguments can be other expressions

Each argument is not limited to a simple literal or variable. It can be a calculation expression or property access.

~~~text
calculate(price * quantity)
format(customer.firstName + ' ' + customer.lastName)
substring(0, name.length())
~~~

Example in Java:

~~~java
Expression expression = parser.parseExpression(
        "calculate(#unitPrice * #quantity)"
);

context.setVariable("unitPrice", 19.5);
context.setVariable("quantity", 3);

Object result = expression.getValue(context);
~~~

SpEL evaluates the argument expression to obtain its value, then uses that value when resolving and invoking the method. If an argument contains another method call, the inner call must be evaluated first to produce the argument for the outer call.

For multi-level expressions, use whitespace and line breaks in the Java string so readers can see the boundary of each argument. If argument calculation logic is too long, prepare the value in Java or a context variable before evaluation.

## 6. Invoking a method on a nested object

If the root object contains child objects, you can invoke a method on a child object through a property path:

~~~text
customer.getDisplayName()
customer.address.format()
order.calculateTotal()
order.customer.isActive()
~~~

Example:

~~~java
Expression expression = parser.parseExpression(
        "customer.getDisplayName()"
);

String name = expression.getValue(context, String.class);
~~~

SpEL first accesses the customer property on the root object, then invokes getDisplayName() on the returned object. Every link in the path must exist and be accessible.

If customer is null, continuing to invoke a method on it can raise an error during evaluation. Check the data beforehand, design an object graph with clear state, or use a null-safe mechanism appropriate for the Spring version in use. Do not rely on an object happening to be non-null in sample data.

## 7. Invoking a method on a variable

A variable in EvaluationContext can hold an object, not just a string or number. When a variable is an object, you can invoke a method of that object using the #variable.method(...) syntax.

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("text", "Spring Expression Language");

Expression expression = parser.parseExpression(
        "#text.toUpperCase()"
);

String result = expression.getValue(context, String.class);
~~~

You can invoke methods with parameters on the same variable:

~~~text
#text.substring(0, 6)
#text.replace('Expression', 'EL')
~~~

This approach is useful when the root object should not hold all input data. The application can place each needed object into the context under a specific variable name, making the expression clearly show the data it uses.

## 8. Invoking a static method

SpEL supports invoking static methods through the type reference T(...). After the type name comes a dot and the method name, followed by any arguments.

~~~text
T(java.lang.Math).abs(-10)
T(java.lang.Math).max(12, 30)
T(java.lang.String).valueOf(123)
~~~

Example:

~~~java
Expression expression = parser.parseExpression(
        "T(java.lang.Math).max(12, 30)"
);

Integer result = expression.getValue(Integer.class);
~~~

T(...) requires SpEL to resolve the type through the EvaluationContext's TypeLocator. Static methods are not invoked on the root object because they belong to the class, not an instance.

Only use static methods that are necessary and have easy-to-understand behavior. If expressions are untrusted, the ability to reference types and invoke static methods must be restricted with appropriate context configuration.

## 9. Invoking a Spring bean's method

In a Spring application, an expression can invoke a method on a bean using the @beanName.method(...) syntax, if the EvaluationContext has a corresponding BeanResolver.

Syntax examples:

~~~text
@pricingService.calculateTotal(#order)
@featureFlags.isEnabled('new-checkout')
~~~

With a self-created context, you can connect a BeanFactory using BeanFactoryResolver:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(order);

context.setBeanResolver(
        new BeanFactoryResolver(beanFactory)
);
~~~

After configuration, the expression can resolve beans by name. The fact that a bean already exists in the Spring container does not mean every EvaluationContext can automatically access that bean. This capability depends on the resolver provided to the context.

Calling beans from SpEL can expand an expression's scope of action because beans can access repositories, services, or external systems. Expose only the beans and methods truly needed for the use case; avoid turning expressions into an arbitrary way to call all application services.

## 10. MethodResolver and how the matching method is chosen

When encountering a method call, SpEL needs to determine which method on the target object matches the method name and arguments. This work is performed through the EvaluationContext's MethodResolver.

StandardEvaluationContext by default has a reflection-based method resolution mechanism. Therefore, a matching public method on an object can be invoked if the method resolver and argument types permit.

Example with two overloads:

~~~java
public String describe(String value) {
    return "text: " + value;
}

public String describe(Integer value) {
    return "number: " + value;
}
~~~

Calls with string and numeric arguments can select the corresponding overload:

~~~text
describe('42')
describe(42)
~~~

Overload selection depends on the actual runtime types of the arguments and type conversion capabilities. If an argument is null or multiple overloads are compatible, the resolution result may be ambiguous or may not select the expected method.

When encountering overload errors:

1. Check the runtime type of each argument.
2. Check the number and order of parameters.
3. Check whether the method has overloads with the same name.
4. Check the TypeConverter if type conversion is needed.
5. Use distinct method names or variables with explicit types if overloading causes ambiguity.

Do not rely on a numeric string like '42' always being automatically understood as an Integer. In SpEL, a string literal remains a String until an appropriate conversion mechanism is applied.

## 11. Methods with varargs and null parameters

A Java method can declare varargs, for example:

~~~java
public String join(String separator, String... values) {
    return String.join(separator, values);
}
~~~

When calling from SpEL, you need to provide arguments matching the signature and the method resolution capability of the Spring version in use. With varargs, test the call on the exact application version rather than assuming every way of passing an array or list is converted the same way.

Null parameters also require attention:

~~~text
findByCode(null)
~~~

If there are multiple overloads accepting different reference types, null does not clearly indicate which overload is desired. Use a method with a distinct name, pass a variable with an explicit type, or normalize the data before calling.

## 12. SimpleEvaluationContext and method invocation restrictions

StandardEvaluationContext supports method invocation with a broader default configuration. SimpleEvaluationContext is designed for a restricted subset of SpEL and does not enable instance method invocation by default.

If the use case genuinely requires invoking instance methods in SimpleEvaluationContext, the builder can enable it explicitly with withInstanceMethods():

~~~java
EvaluationContext context =
        SimpleEvaluationContext
                .forReadOnlyDataBinding()
                .withInstanceMethods()
                .build();
~~~

Only enable this capability when method invocation is an explicit requirement. A restricted context does not automatically make every method on an object safe; the root object and accessors still need to be chosen carefully.

If you only need to read properties for filtering or display, keep the context read-only and do not enable method invocation. If calling methods is necessary, provide an object with a small, stable API and no unexpected side effects.

## 13. Method calls can produce side effects

Calling a method does not just return a value. A method can update an object, write logs, query a database, send a request, or change system state.

Examples:

~~~text
account.withdraw(100)
notificationService.send(message)
repository.deleteById(#id)
~~~

These expressions can perform state-changing actions if the context permits invoking the corresponding methods. Therefore, SpEL should not be viewed as a read-only language.

In particular, when an expression is evaluated multiple times, a method with side effects can be called multiple times. An expression used across multiple requests or in a template can cause repeated behavior if lifecycle is not controlled.

Practical principles:

- Prefer pure methods that only compute and return a result.
- Do not put data-writing repositories or services into the context if unnecessary.
- Do not place sending emails, payments, or state updates in configuration expressions that may be evaluated repeatedly.
- Keep method permissions minimal through the chosen root object and resolvers.
- Execute important business actions in the Java/service flow, where transactions, authorization, and error handling can be managed clearly.

## 14. Troubleshooting errors when invoking methods

A method call can fail at several different steps:

| Symptom | Common cause | How to check |
|---|---|---|
| Method not found | Wrong name or method is not accessible | Check name, visibility, and target object |
| Wrong number of arguments | Parameter count does not match signature | Compare the call against the Java method |
| Unable to select overload | Argument type is ambiguous or null | Check runtime types and overloads |
| Unable to convert argument | No matching converter | Check TypeConverter and parameter types |
| Unable to invoke method on child property | Intermediate object is null or property is inaccessible | Check each link in the path |
| Bean reference does not work | Context does not have a BeanResolver | Check BeanFactoryResolver configuration |
| Static method cannot be resolved | TypeLocator cannot find class | Check class name and TypeLocator |
| SimpleEvaluationContext rejects method | Instance method invocation is not enabled | Only enable withInstanceMethods when needed |

When debugging, separate parsing from evaluation. The parser may accept method call syntax, and only at getValue is it discovered that the method cannot be resolved or arguments cannot be converted.

## 15. Summary

A no-parameter method is invoked with the method name and empty parentheses, for example greeting(). A parameterized method receives arguments in order, for example greet('Lan') or calculate(#price, #quantity). Methods can be invoked on the root object, nested objects, variables, or beans provided by the context. Static methods are invoked through the type reference T(...).

MethodResolver decides which method matches; TypeConverter may participate in argument conversion. StandardEvaluationContext supports method invocation more broadly, whereas SimpleEvaluationContext only enables instance methods when explicitly configured. Control the exposed objects and methods, prefer pure methods, and keep important side effects in the Java/service layer.