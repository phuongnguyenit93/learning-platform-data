# Method Does Not Exist or Is Inaccessible in Spring Expression Language

Spring Expression Language (SpEL) allows invoking Java methods directly inside expressions, for example `customer.calculateDiscount(10)` or `name.toUpperCase()`. When evaluating a call, SpEL must find a matching method on the target object, determine how to pass arguments, and execute that method.

If the method does not exist, no overload matches, or the method cannot be accessed in the current environment, evaluation fails. Understanding this processing chain helps distinguish syntax errors from method resolution errors and errors occurring inside the Java method itself.

## 1. Method invocation syntax in SpEL

A method call has the form:

~~~spel
methodName(argument1, argument2, ...)
~~~

If the method belongs to a nested property, the expression uses a dot:

~~~spel
customer.calculateDiscount(10)
product.getName()
name.toUpperCase()
~~~

If there is no object before the dot, the method is searched on the current object, usually the root object of the EvaluationContext.

Java class example:

~~~java
public class Customer {
    public String greeting() {
        return "Hello";
    }

    public String formatName(String name) {
        return name.toUpperCase();
    }
}
~~~

Both methods can be called on the root object:

~~~java
Customer customer = new Customer();

StandardEvaluationContext context =
    new StandardEvaluationContext(customer);

ExpressionParser parser = new SpelExpressionParser();

String greeting = parser.parseExpression("greeting()")
    .getValue(context, String.class);

String formatted = parser.parseExpression("formatName('Linh')")
    .getValue(context, String.class);
~~~

The results are `Hello` and `LINH`, respectively.

## 2. How does SpEL find a method?

When evaluating a method call, SpEL uses the `MethodResolver` instances registered in the EvaluationContext. The resolver is responsible for finding a method matching the method name and the expression's arguments.

In `StandardEvaluationContext`, SpEL provides `ReflectiveMethodResolver` by default. This resolver looks up Java methods via reflection and considers factors such as name, argument types, overloads, and supported type conversions.

The processing flow can be illustrated as:

~~~text
Expression: customer.calculateDiscount(10)
                   |
                   v
Evaluate object customer
                   |
                   v
Evaluate arguments
                   |
                   v
MethodResolver finds matching method
                   |
             +-----+-----+
             |           |
           Found      Not found
             |           |
             v           v
       MethodExecutor   Evaluation error
             |
             v
       Invoke method
             |
        +----+----+
        |         |
      Success  Method throws error
        |         |
        v         v
     Return    Invocation error
     value
~~~

When a method is found, the resolver returns a `MethodExecutor` to perform the call. If no suitable method is found, SpEL cannot continue evaluating that call.

## 3. Common reasons a method is not found

### 3.1. Wrong method name

The method name in SpEL must match the Java method name that the resolver can locate. Java is case-sensitive.

For example, the class has:

~~~java
public String getName() {
    return name;
}
~~~

An expression calling:

~~~spel
getname()
~~~

does not match the name `getName()`. If you want to read a JavaBean property, you should usually use:

~~~spel
name
~~~

If you want to invoke the method directly, you must write the exact name:

~~~spel
getName()
~~~

### 3.2. Method does not exist on the target object

Suppose the root object is Customer, but this class does not have a `calculateTax()` method. The expression:

~~~spel
calculateTax()
~~~

cannot be resolved on Customer unless the context has a custom resolver providing alternative handling.

Verify the exact runtime type of the target object, especially when the root object is passed through an interface, a superclass, or a proxy.

### 3.3. No overload matches the argument count

Suppose the class only defines:

~~~java
public String format(String value) {
    return value.trim();
}
~~~

But the expression calls:

~~~spel
format()
~~~

The call has a different number of arguments from the method signature. The resolver cannot find a matching candidate and evaluation fails.

Similarly, if a method requires two arguments but the expression passes one or three arguments, there is no matching overload and the call cannot proceed.

### 3.4. Incompatible argument types

Example:

~~~java
public String repeat(String value, int count) {
    return value.repeat(count);
}
~~~

Expression:

~~~spel
repeat('A', 'many')
~~~

passes the string `many` for a position expecting an integer. SpEL can use TypeConverter to convert arguments when conversion is supported, but a string that does not represent an integer will not convert successfully.

When troubleshooting, compare the runtime type of each argument against the Java parameter types and check whether the context has a matching converter.

### 3.5. Method resides on another object

Expression:

~~~spel
calculateDiscount(10)
~~~

calls the method on the current object. If the method actually belongs to another property, specify the path explicitly:

~~~spel
customer.calculateDiscount(10)
~~~

If the root object is not Customer and has no corresponding method, the call cannot be resolved as expected.

## 4. Method exists but is inaccessible

Finding the method name and signature is not enough. SpEL must also be able to access that method in the running Java environment.

### 4.1. Non-public method

Example:

~~~java
class Customer {
    private String internalCode() {
        return "C-100";
    }
}
~~~

An expression calling:

~~~spel
internalCode()
~~~

should not be expected to work with the default reflection access configuration. Non-public methods may not be permitted by the resolver or may not be callable from the execution site.

For calls from SpEL, provide public methods on an accessible type:

~~~java
public class Customer {
    public String getCode() {
        return "C-100";
    }
}
~~~

### 4.2. Declaring class is inaccessible

A method may be declared public, yet its containing class is inaccessible from the SpEL execution code, such as a package-private class in another package or a type restricted by the Java module structure.

In this case, reflection may fail to invoke the method even though the method name and modifier appear appropriate.

Check the accessibility of the declaring class as well, not just the method's modifier.

### 4.3. Reflection and Java module restrictions

Access restrictions of the JVM, module system, or deployment environment can prevent reflection from accessing members. A call that works in a development environment may encounter issues when running in a modular environment or a runtime with stricter access configuration.

When encountering an access error, inspect the underlying exception to determine whether it is a method resolution issue, a reflection access permission issue, or an error thrown by the executed method.

## 5. Overloading and method selection

Java allows multiple methods with the same name but different parameter lists:

~~~java
public class Formatter {
    public String format(String value) {
        return value.trim();
    }

    public String format(Integer value) {
        return String.valueOf(value);
    }
}
~~~

The following expressions can select the corresponding overload:

~~~spel
format('  Spring  ')
format(42)
~~~

The resolver must select a method compatible with the arguments SpEL evaluates. Argument types, conversion capabilities, and overload selection rules can all affect the outcome.

If there are multiple closely matched overloads or type conversion causes ambiguity, clarify the input types, adjust the method signatures, or pass explicitly typed values from the context.

For example, you can set a properly typed Java variable before evaluation:

~~~java
context.setVariable("count", Integer.valueOf(3));

Expression expression =
    parser.parseExpression("formatter.format(#count)");
~~~

This helps make the argument type more explicit.

## 6. EvaluationContext can restrict method invocation

MethodResolver is a component of EvaluationContext. Therefore, the context type and registered resolvers determine which methods can be invoked.

### StandardEvaluationContext

`StandardEvaluationContext` supports default reflective method resolution and can be further configured. It is a flexible choice when expressions need to invoke Java methods suited to the application.

### SimpleEvaluationContext

`SimpleEvaluationContext` is designed for cases requiring restricted features, commonly seen in data binding. The builder lets you choose supported capabilities and register appropriate resolvers.

If a restricted context is used without registering the necessary MethodResolver, a method call may fail to resolve even though the method exists on the Java class.

Therefore, when a method is not found, check the context's resolver list rather than only checking the object's source code.

## 7. Methods on nested properties

A call can traverse multiple properties before invoking a method:

~~~spel
order.customer.getName()
~~~

SpEL needs to perform sequentially:

1. Read the `customer` property on the root object order.
2. Obtain the Customer object from the corresponding getter.
3. Find the `getName()` method on the Customer object.
4. Invoke the method and receive the return value.

If customer is null, the step of finding and invoking the method cannot proceed on a valid object. If the customer property does not exist, the error occurs right at the property access step.

Null-safe navigation can be used to guard segments of the path that might be null:

~~~spel
order.customer?.getName()
~~~

When the object to the left of the null-safe operator is null, the corresponding call evaluates to null. Null-safe navigation does not fabricate a missing method and does not solve signature or access permission issues.

## 8. Invoking static methods and methods on beans

### Static method

You can reference a Java type with `T(...)` and then call a static method:

~~~spel
T(java.lang.Math).abs(-10)
~~~

If the type or matching static method cannot be found, evaluation may fail. Check the fully qualified type name, method name, and argument types.

### Bean method

In a context with an appropriate BeanResolver, an expression can invoke a method on a bean:

~~~spel
@environment.getProperty('app.name')
~~~

If the bean is not resolved, the bean lacks the corresponding method, or the context does not support bean references, the call cannot complete.

Bean reference syntax does not work automatically in every EvaluationContext. The resolver must be configured and the bean must be accessible in the application environment.

## 9. Distinguishing method resolution errors from errors inside the method

There are two important error groups:

**Method resolution/access error:**

- No method with the requested name.
- No overload matching the argument count or types.
- Method is inaccessible.
- Context does not provide a resolver for that kind of call.

In this group, SpEL has not yet successfully executed the method call.

**Method invocation error:**

- SpEL found the method and invoked it.
- However, the method body itself throws an exception at runtime.

Example:

~~~java
public BigDecimal calculateDiscount(BigDecimal amount) {
    if (amount.signum() < 0) {
        throw new IllegalArgumentException("Amount must be non-negative");
    }
    return amount.multiply(new BigDecimal("0.10"));
}
~~~

With a negative input, the method was found and invoked; the error originates from the logic inside the method.

The two error groups require different handling. For resolution errors, check name, signature, argument types, accessibility, and resolvers. For invocation errors, inspect the underlying exception and the method's input data.

## 10. How to investigate when SpEL reports a method does not exist or is inaccessible

You can trace through the following steps:

1. **Identify the target object:** does the root object or the property before the dot have the right runtime type?
2. **Check the method name:** are the capitalization and method name exact?
3. **Check the argument count:** does the number of arguments in the expression match an overload?
4. **Check argument types:** are the actual values compatible with parameter types? Is a TypeConverter needed?
5. **Check accessibility:** can the method and declaring class be accessed by reflection?
6. **Check the context:** which MethodResolver is registered? Does the context intentionally restrict method invocation?
7. **Inspect the underlying exception:** did the error occur while finding the method or while executing the method?

Do not rename methods or add overloads by guesswork. Use runtime types, signatures, and exceptions to pinpoint the exact cause.

## 11. Complete example: method exists and is invoked successfully

~~~java
public class Customer {
    private final String name;

    public Customer(String name) {
        this.name = name;
    }

    public String formatGreeting(String prefix) {
        return prefix + name.toUpperCase();
    }
}
~~~

Evaluating with SpEL:

~~~java
Customer customer = new Customer("Linh");

StandardEvaluationContext context =
    new StandardEvaluationContext(customer);

context.setVariable("prefix", "Hello, ");

ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("formatGreeting(#prefix)");

String result =
    expression.getValue(context, String.class);

System.out.println(result);
~~~

Result:

~~~text
Hello, LINH
~~~

In this example:

- The root object is Customer.
- The prefix variable is retrieved from EvaluationContext.
- SpEL finds the public method `formatGreeting(String)`.
- MethodResolver identifies the matching method.
- The method is invoked and returns a String.
- getValue returns the result as the requested String type.

If you change the expression to `formatGreeting()`, there is no matching overload for the argument count and evaluation fails. If you modify the method body to throw an exception, the error belongs to the invocation phase rather than the resolution phase.

## 12. Summary

- A method call in SpEL has the form `methodName(arguments)` or `object.methodName(arguments)`.
- SpEL uses MethodResolver to locate a matching method on the target object.
- StandardEvaluationContext provides ReflectiveMethodResolver by default; restricted contexts may require explicitly registered resolvers.
- Wrong name, wrong argument count, incompatible argument types, and ambiguous overloads can all cause method resolution to fail.
- An inaccessible method or declaring class can also cause the call to fail.
- Resolution errors differ from exceptions thrown from inside an invoked method.
- Nested properties, root objects, bean references, and static methods can all participate in a call if the context supports them.
- When debugging, check the target object, method name, signature, argument types, resolvers, and underlying exception.

When a method call in SpEL fails, trace the path from the target object to the resolver, verify the signature required by the expression, and check access permissions before concluding that the method truly does not exist.
