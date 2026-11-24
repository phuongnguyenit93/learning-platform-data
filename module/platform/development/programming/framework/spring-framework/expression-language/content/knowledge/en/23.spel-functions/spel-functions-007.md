# Differences Between Functions and Root Object Methods in Spring Expression Language (SpEL)

SpEL allows calling both **functions registered in EvaluationContext** and **methods of the root object**. The two invocation styles have different syntax and purposes:

~~~text
#normalize('  Spring  ')
greeting('Hello')
~~~

`#normalize(...)` calls a function registered in the context. `greeting(...)` calls a method on the current root object. A function is typically a static Java method registered via a `Method` object; a root object method is behavior belonging to the instance currently used as the root object.

Understanding this difference clearly helps you choose the right place for logic, configure the context properly, and avoid confusing variables, functions, root object methods, and bean methods.

## 1. The Two Invocation Mechanisms Have Different Roles

### Functions in EvaluationContext

A function is a Java method registered by name in EvaluationContext. When called in SpEL, the function name has a `#` prefix:

~~~text
#functionName(argument1, argument2)
~~~

Examples:

~~~text
#normalize('  Spring Expression Language  ')
#isValidCode('SKU-100')
~~~

A function does not require the root object to have a method with the same name. SpEL looks up the function in the variable/function namespace of the EvaluationContext.

### Methods of the root object

A root object method is a method available on the root object currently being used to evaluate the expression. You can call the method directly:

~~~text
methodName(argument1, argument2)
~~~

Or specify the root object explicitly:

~~~text
#root.methodName(argument1, argument2)
~~~

Examples:

~~~text
greeting('Hello')
#root.calculateDiscount('VIP')
~~~

Here, SpEL calls the method on the root object instance. The method can read the state of that object itself through its instance fields or properties.

## 2. Comparison Table Between Functions and Root Object Methods

| Criterion | Function | Root object method |
|---|---|---|
| Invocation syntax | `#functionName(...)` | `methodName(...)` or `#root.methodName(...)` |
| Where declared | Java method registered in EvaluationContext | Method of the root object's class |
| Resolution mechanism | Function name in context | MethodResolver on the target object |
| Target receiving the call | Registered function; typically a static method | Root object instance |
| Root object dependency | Does not require the root object to have the method | Requires the root object to have a matching method |
| Common purpose | Shared utility, normalization, validation, or calculation functions | Behavior tied to the data and state of a business domain object |

A function can receive data retrieved from the root object as arguments. Conversely, a root object method can directly use the instance's state without needing to pass that object itself again.

## 3. Registering Functions in StandardEvaluationContext

`StandardEvaluationContext` provides the `registerFunction(String, Method)` method to register functions.

For example, create a utility class with static methods:

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

    public static boolean isValidCode(String value) {
        return value != null && value.matches("[A-Z]{3}-[0-9]+");
    }
}
~~~

Obtain the Method objects via reflection and register them:

~~~java
import java.lang.reflect.Method;

Method normalizeMethod =
        TextFunctions.class.getDeclaredMethod("normalize", String.class);

Method validCodeMethod =
        TextFunctions.class.getDeclaredMethod("isValidCode", String.class);

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.registerFunction("normalize", normalizeMethod);
context.registerFunction("isValidCode", validCodeMethod);
~~~

In the example, two functions are registered with the names normalize and isValidCode. When writing expressions, add the `#` prefix before the registered name.

~~~java
ExpressionParser parser = new SpelExpressionParser();

String normalized = parser.parseExpression(
        "#normalize('  Spring  ')"
).getValue(context, String.class);

Boolean valid = parser.parseExpression(
        "#isValidCode('SKU-100')"
).getValue(context, Boolean.class);
~~~

The function's result is returned as the result of the expression. The expected Java type can be specified using the `getValue(Class<T>)` overload.

### 3.1. Signature of a method used as a function

A function is registered via a `java.lang.reflect.Method` object. A static method is the usual choice because a function does not have a root object instance as its receiver.

When retrieving the Method, the method name and parameter type list must match the actual signature:

~~~java
Method method =
        TextFunctions.class.getDeclaredMethod(
                "normalize",
                String.class
        );
~~~

If the name or parameter types do not match, `getDeclaredMethod(...)` will not find the method. Handle `NoSuchMethodException` in Java code when configuring the context.

A function should have clear inputs and results. If a function has side effects, depends on global state, or performs unpredictable actions, expressions will become harder to test and understand.

## 4. Calling Methods of the Root Object

To call a method on the root object, create the context with an object that has the needed methods.

~~~java
public class Customer {
    private final String name;
    private final int age;

    public Customer(String name, int age) {
        this.name = name;
        this.age = age;
    }

    public String getName() {
        return name;
    }

    public int getAge() {
        return age;
    }

    public String greeting(String prefix) {
        return prefix + ", " + name;
    }

    public boolean isAdult() {
        return age >= 18;
    }
}
~~~

Set Customer as the root object and call its methods:

~~~java
Customer customer = new Customer("Lan", 25);

StandardEvaluationContext context =
        new StandardEvaluationContext(customer);

ExpressionParser parser = new SpelExpressionParser();

String greeting = parser.parseExpression(
        "greeting('Hello')"
).getValue(context, String.class);

Boolean adult = parser.parseExpression(
        "isAdult()"
).getValue(context, Boolean.class);
~~~

`greeting('Hello')` is called on the customer instance. The method uses that instance's own name to produce the greeting. `isAdult()` likewise reads age from that instance.

It can be written explicitly via `#root`:

~~~text
#root.greeting('Hello')
#root.isAdult()
~~~

This syntax is useful when the expression has multiple current objects or is nested inside selection/projection.

## 5. How Root Object Methods Are Resolved

When SpEL encounters a method call on the root object, it uses the MethodResolver in EvaluationContext to find a method matching the name and arguments.

With `StandardEvaluationContext`, the default reflective mechanism can resolve matching methods on Java objects.

Example:

~~~text
calculateTotal(3, 4)
#root.calculateTotal(3, 4)
~~~

If the root object's class has multiple overloads with the same name, SpEL must select the matching method based on argument count and types, along with conversion rules supported by the context.

When a method cannot be found or arguments are incompatible, evaluation can raise an error. Check:

- Method name and parameter signature.
- Runtime types of the arguments.
- Return type expected by Java code.
- Whether the method is accessible in the current environment.
- The MethodResolver configured in EvaluationContext.

A root object method should generally express reasonable behavior belonging to that object. Do not put entire application logic or system operations into methods just to call them from SpEL.

## 6. Functions and Methods Can Receive the Same Data with Different Receivers

A function and a method can perform a similar calculation, yet they are invoked through two different mechanisms.

For example, a function calculating a discounted price:

~~~java
public final class PricingFunctions {

    private PricingFunctions() {
    }

    public static BigDecimal discountedPrice(
            BigDecimal price,
            BigDecimal rate) {
        return price.multiply(BigDecimal.ONE.subtract(rate));
    }
}
~~~

Registering and calling:

~~~java
Method method = PricingFunctions.class.getDeclaredMethod(
        "discountedPrice",
        BigDecimal.class,
        BigDecimal.class
);

context.registerFunction("discountedPrice", method);

BigDecimal result = parser.parseExpression(
        "#discountedPrice(100M, 0.1M)"
).getValue(context, BigDecimal.class);
~~~

In this case, the function takes both price and rate as arguments. It does not need a PricingPolicy as the root object.

Conversely, a method on PricingPolicy can use the rate stored in the instance:

~~~java
public class PricingPolicy {
    private final BigDecimal discountRate;

    public PricingPolicy(BigDecimal discountRate) {
        this.discountRate = discountRate;
    }

    public BigDecimal discountedPrice(BigDecimal price) {
        return price.multiply(BigDecimal.ONE.subtract(discountRate));
    }
}
~~~

Calling the root object method:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(new PricingPolicy(new BigDecimal("0.10")));

BigDecimal result = parser.parseExpression(
        "discountedPrice(100M)"
).getValue(context, BigDecimal.class);
~~~

The method only takes price because discountRate is already in the state of the root object.

Choose a function when the operation is a shared utility and inputs should be passed explicitly. Choose a method when the behavior is tied to the data or state of the object itself.

## 7. Function and Variable Namespace

Functions are registered in EvaluationContext by name and invoked with the `#` prefix. Variables also use that prefix:

~~~text
#minimumAge
#normalize('Spring')
~~~

Because functions and variables share the `#`-prefixed reference namespace, avoid registering a variable and a function with the same name in the same context. Duplicate names can make expressions confusing or cause resolution conflicts.

Example:

~~~java
context.setVariable("minimumAge", 18);
context.registerFunction("normalize", normalizeMethod);
~~~

After registration:

~~~text
age >= #minimumAge
#normalize(name)
~~~

`#minimumAge` retrieves the variable value; `#normalize(name)` calls the normalize function with an argument read from the root object.

Do not add `#` before a root object method name when calling the method directly:

~~~text
isAdult()
#root.isAdult()
~~~

This is an important syntactic difference when reading expressions.

## 8. Calling Functions and Methods Inside Collection Expressions

Registered functions can be used in selection or projection expressions. Methods on the current element can also be called inside those expressions.

For example, the root object is CustomerReport with a customers collection:

~~~text
customers.?[#this.isAdult()].![#normalize(#this.name)]
~~~

In the expression:

- `#this.isAdult()` calls a method on the current Customer.
- `#normalize(...)` calls a function registered in the EvaluationContext.
- `#this.name` reads the name property from the current Customer.

If you need to call a method on the outer root object inside the collection expression, use `#root`:

~~~text
customers.?[#root.isAllowed(#this)].![#this.name]
~~~

This clearly distinguishes a method on the root object from a method on the current element. Do not rely on unprefixed names in nested expressions unless you know what the current object is at that position.

## 9. Comparison with Methods on Referenced Beans

Root object methods and referenced bean methods are also two different invocation forms.

Bean reference example:

~~~text
@pricingService.discountedPrice(100M)
~~~

`@pricingService` asks BeanResolver to find the bean by name and then invoke the method on that bean.

Comparison:

| Invocation style | Target receiving the call |
|---|---|
| `discountedPrice(100M)` | Current root object |
| `#root.discountedPrice(100M)` | Explicitly specified root object |
| `#discountedPrice(100M)` | Function registered in EvaluationContext |
| `@pricingService.discountedPrice(100M)` | pricingService bean resolved by BeanResolver |

The last three cases can look similar, but their resolution mechanisms differ. Identify the receiver before reading or writing an expression.

## 10. Return Values, Type Conversion, and Errors

Both functions and methods return values that SpEL continues using in the expression. The return type can be String, Boolean, numbers, business domain objects, or null.

Example:

~~~java
String label = parser.parseExpression(
        "#normalize(name)"
).getValue(context, String.class);
~~~

SpEL uses the result type together with the context's TypeConverter when it needs to supply a value of the requested type. If conversion is not possible, evaluation can raise an EvaluationException.

Common errors:

- Function not registered in the context.
- Function name in the expression differs from the name used in registerFunction.
- The Java method used as a function does not have the required signature.
- The root object does not have a matching method.
- Arguments are incompatible with method parameters.
- The method or function throws an exception during execution.
- The result is null, yet the expression continues accessing properties or calling methods on that result.

When diagnosing, distinguish syntax parse errors from evaluation errors. Check where the function is registered, the current root object, the method signature, and actual argument types.

## 11. Design and Security Notes

Both functions and methods can execute Java code when an expression is evaluated. If expressions come from users or untrusted sources, you must control registered functions and the methods that the root object permits access to.

Some principles:

1. Only register genuinely necessary functions.
2. Use functions with clear inputs and avoid side effects.
3. Keep root object methods focused on behavior belonging to the object's responsibility.
4. Only provide a root object containing the data and behavior necessary for the expression.
5. Do not evaluate untrusted expressions using a StandardEvaluationContext with broad access permissions.
6. If you need to restrict features, consider SimpleEvaluationContext and specifically configure allowed capabilities; do not assume all functions or methods are enabled in a restricted context.

Do not use functions as a way to bypass object design, and do not turn the root object into an arbitrary gateway to the entire application.

## 12. Common Mistakes

| Mistake | Cause | Resolution |
|---|---|---|
| Calling a function while forgetting `#` | Functions are referenced via the variable namespace with a # prefix. | Use `#functionName(...)`. |
| Calling a root method like a function | Root object methods do not need to be registered with registerFunction. | Call `methodName(...)` or `#root.methodName(...)`. |
| Function does not exist | registerFunction was not called or the registered name does not match. | Register the Method under the exact name in the evaluating context. |
| Using an instance method as a function without a suitable receiver | Functions registered via Method are normally designed as static methods. | Use a static utility method or move the behavior to a root object method. |
| Confusing functions with variables | Both use the # prefix. | Avoid duplicate names and document the purpose of each name. |
| Calling a root object method with the wrong signature | Method does not exist or arguments are incompatible. | Check the method signature and argument types. |
| Calling the wrong root method inside selection/projection | The current object has switched to the collection element. | Use `#root.methodName(...)` to specify the root object explicitly. |
| Assuming a function automatically accesses the root object | A function is called according to its registered Method and passed arguments. | Pass the needed data as arguments or use a root object method. |
| Expressions causing unpredictable side effects | A function or method mutates state when invoked. | Prefer pure logic with deterministic results that is easy to test. |

## 13. Takeaways

- Functions are registered in EvaluationContext and called using the `#functionName(...)` syntax.
- `StandardEvaluationContext.registerFunction(...)` takes a name and a Java Method object.
- Functions are typically static methods, independent of the root object instance.
- Root object methods are called using `methodName(...)` or `#root.methodName(...)`.
- A root object method is behavior of the current instance and can use the instance's state.
- Functions and variables share the `#` reference namespace; avoid duplicate names.
- In selection/projection, `#this` is the current element, while `#root` remains the original root object.
- `@beanName.method(...)` is a method call on a bean resolved by BeanResolver, not a function or direct root object method.
- Choose functions for shared utilities; choose root methods for behavior tied to the object.
- Restrict functions, root objects, and access permissions when evaluating untrusted expressions.
