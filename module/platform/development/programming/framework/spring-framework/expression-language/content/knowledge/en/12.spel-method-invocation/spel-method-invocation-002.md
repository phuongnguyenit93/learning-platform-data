# Method Overloading and Selecting the Right Signature in SpEL

## Objective

Java allows a class to declare multiple methods with the same name but different parameter lists. This is method overloading. When a SpEL expression invokes a method, the parser needs to determine which method on the target object matches the passed arguments.

SpEL supports method invocation using familiar syntax such as `customer.findById('C-17')`. Overload selection depends on the methods available on the object's runtime class, the actual types of the arguments, and the type conversion capability of the evaluation context. If multiple signatures match or the arguments lack sufficient type information, the call may fail or become unpredictable. The best practice is to pass arguments with explicit types and design expression APIs to avoid ambiguous overloads.

## 1. What is overloading?

Overloading is having multiple methods with the same name in the same class or class hierarchy but with different parameter lists. Example:

```java
public class CustomerLookup {
    public Customer find(String customerId) {
        // ...
    }

    public Customer find(Long numericId) {
        // ...
    }

    public Customer find(String region, String customerId) {
        // ...
    }
}
```

All three methods are named `find`, but they have two different parameter types or different parameter counts. In SpEL, the method invocation syntax is still:

```spel
find('C-17')
```

or called on a property/variable:

```spel
customerLookup.find('C-17')
#lookup.find('C-17')
```

Method overriding is a different case: a subclass replaces the implementation of a method with the same signature. Overloading is selected when resolving the call; overriding is dispatched by the JVM according to the runtime object after the method signature has been chosen.

## 2. How does SpEL find a method?

With `StandardEvaluationContext`, SpEL uses reflective method resolution by default. `ReflectiveMethodResolver` searches for a matching method on the target object's runtime class based on the method name, argument count, and argument types. The selected method is then invoked via reflection.

When evaluating a call, the main factors include:

1. **Name and parameter count:** the method must have a matching name and accept the expression's argument count, including varargs handling if present.
2. **Runtime type of arguments:** an argument of `String`, `Integer`, `Long`, or a specific class provides information to distinguish overloads.
3. **Type assignability:** a method accepting the exact type or a compatible parameter type may be preferred.
4. **Type conversion:** the evaluation context's `TypeConverter` can convert an argument to the parameter type required by the method.
5. **Uniqueness of result:** if there is no matching method or multiple candidates cannot be clearly distinguished, SpEL may report a method resolution error.

Conversion rules allow some calls to be valid even when the initial argument type does not match the parameter type. However, do not rely on implicit conversion when a class has multiple overloads that can accept the same value.

## 3. Argument types determine the overload

Suppose a class has the following methods:

```java
public class SearchService {
    public String search(String key) {
        return "string:" + key;
    }

    public String search(Integer key) {
        return "integer:" + key;
    }

    public String search(Number key) {
        return "number:" + key;
    }
}
```

With `SearchService` as the root object, the following expressions provide different argument types:

| Expression | Argument type | Expected matching signature |
| --- | --- | --- |
| `search('A-10')` | `String` | `search(String)` |
| `search(10)` | Numeric literal of type `Integer` in the typical case | `search(Integer)` is the most specific match. |
| `search(T(java.lang.Long).valueOf('10'))` | `Long` | `search(Number)` if no overload accepts `Long`. |

Java example:

```java
ExpressionParser parser = new SpelExpressionParser();
StandardEvaluationContext context = new StandardEvaluationContext(new SearchService());

String byText = parser.parseExpression("search('A-10')")
        .getValue(context, String.class);

String byInteger = parser.parseExpression("search(10)")
        .getValue(context, String.class);

String byLong = parser.parseExpression(
        "search(T(java.lang.Long).valueOf('10'))")
        .getValue(context, String.class);
```

In this example, `T(java.lang.Long)` is a SpEL type reference; `valueOf` creates a `Long` object before invoking the `search` overload. Creating an argument with a specific type makes the call clearer than letting the parser automatically convert a string or number to multiple candidate types.

## 4. Type conversion can affect overload selection

The evaluation context has a `TypeConverter`. With the default context, SpEL can convert several common types when invoking a method. For example, if a class only has `setLimit(Integer)`, a string value `'25'` can be converted to `Integer` at runtime:

```java
public class QueryOptions {
    private Integer limit;

    public void setLimit(Integer limit) {
        this.limit = limit;
    }
}
```

```spel
setLimit('25')
```

However, if the class has both `setLimit(String)` and `setLimit(Integer)`, a string input already matches `String` directly. Do not expect SpEL to infer the intent to convert the string to a number. Convert the type explicitly:

```spel
setLimit(T(java.lang.Integer).valueOf('25'))
```

Type conversion may depend on the `ConversionService` or `TypeConverter` configured in the context. If the application replaces the default converter, the set of valid convertible types and overload resolution behavior may also change.

## 5. Avoiding ambiguous calls with null

`null` carries no specific runtime class. Therefore, if a class has multiple overloads accepting different reference types, a call with a null argument may lack sufficient information to select the right method:

```java
public class NotificationService {
    public String sendTo(String email) {
        return "email";
    }

    public String sendTo(Integer userId) {
        return "user-id";
    }
}
```

```spel
sendTo(null)
```

Do not rely on this call to pick one of the two overloads. Check for null first and invoke a distinctly named method for the missing-data case:

```spel
recipient == null ? sendToDefault() : sendTo(recipient)
```

If you need to keep the same method name, change the API design so there are not multiple competing reference overloads for the null case, or provide a wrapper/helper with an explicit type and meaning.

## 6. Return type does not select the overload

The target type passed to `getValue`, for example `getValue(context, String.class)`, is used to convert the result of the expression after the expression has been evaluated. It is not a hint to select a method overload.

For example, if `calculate(Integer)` and `calculate(String)` coexist, writing:

```java
String result = parser.parseExpression("calculate(10)")
        .getValue(context, String.class);
```

does not mean instructing SpEL to choose an overload returning `String`. The overload is decided from the `calculate(10)` call and argument type; afterwards the result is converted to the requested type if needed.

Therefore, to control the overload, control the argument types or change the method name. Do not use the desired return type as a way to force signature selection.

## 7. Invoking overloads on objects and static methods

Overloads can appear on regular objects, objects in context variables, or static methods.

```spel
customer.format('Lan')
#formatter.format(100)
T(java.lang.Math).max(10, 20)
```

- `customer.format('Lan')` looks up the method on the runtime class of `customer`.
- `#formatter.format(100)` looks up the method on the object registered in the evaluation context under the variable `formatter`.
- `T(java.lang.Math).max(10, 20)` invokes the static method `max` on the `Math` class; the numeric arguments help the resolver pick the matching numeric overload.

The type reference `T(...)` requires the type locator to permit the corresponding class. In a restricted context or an application with strict security policies, not every class is allowed to be referenced.

## 8. Customizing method resolution and type conversion

`StandardEvaluationContext` allows configuring how SpEL finds methods and converts values:

- **MethodResolver:** determines how methods are found. The default resolver is reflective; the application can add a custom resolver or replace the resolver list to allow only predefined methods.
- **TypeConverter:** converts arguments to parameter types when needed. A custom converter can be configured to match the application's data rules.
- **MethodFilter:** with the reflective resolver, you can restrict the methods allowed on a specific type.

Example of registering a `MethodFilter` to restrict which methods can be invoked on a class:

```java
StandardEvaluationContext context = new StandardEvaluationContext(service);
context.registerMethodFilter(SearchService.class, methods ->
        methods.stream()
                .filter(method -> method.getName().equals("search"))
                .toList());
```

This is an example illustrating the allowlist idea; in a real application you need to check the target class, parameter signatures, and the Java version in use. `registerMethodFilter` works with the reflective method resolver; if replacing the default resolver, ensure the new resolver respects the corresponding filtering policy.

If expressions come from users or untrusted sources, do not provide a `StandardEvaluationContext` with full reflection permissions by default. Use a restricted context, an allowlist resolver, and expose only the necessary objects/methods. Do not treat hiding a few overloads as a complete sandbox measure.

## 9. Designing APIs that are easy to use from SpEL

SpEL is often used in configurations, rules, templates, or application-stored expressions. APIs with too many overloads of the same name make expressions hard to read and hard to control.

Prefer the following practices:

- Use different method names when input semantics differ, for example `findByCode(String)` and `findById(Long)`.
- If overloads must be kept, pass arguments with explicit types rather than relying on implicit conversion.
- Avoid overloads accepting multiple unrelated reference types if the call can receive null.
- Do not rely on the result type of `getValue` to force overload selection.
- Separate null checks from method calls; use a separate method for the missing-value case.
- For important rules, create small helper methods with stable signatures instead of exposing an entire complex API to SpEL.

Example of an API with clearer meaning:

```java
public class CustomerLookup {
    public Customer findByCode(String code) {
        // ...
    }

    public Customer findByNumericId(Long id) {
        // ...
    }

    public Customer findDefault() {
        // ...
    }
}
```

The corresponding expressions are easy to understand and require no overload guessing:

```spel
findByCode('C-17')
findByNumericId(T(java.lang.Long).valueOf('17'))
recipient == null ? findDefault() : findByCode(recipient)
```

## 10. Common errors and how to handle them

| Symptom | Causes to check | How to handle |
| --- | --- | --- |
| Method not found | Wrong name, wrong parameter count, method inaccessible, or no compatible signature. | Check runtime class, method name, argument count, and parameter types. |
| Call with a string does not pick numeric overload | `String` directly matches the overload taking String; converting to a number is not an explicit intent. | Use `T(Integer).valueOf(...)` or pass a pre-typed object from the context. |
| Call `method(null)` fails or is ambiguous | Null has no runtime type to distinguish multiple reference overloads. | Check for null first or call a separate method for the null case. |
| An expression works in one environment but fails in another | Different TypeConverter, MethodResolver, or runtime class. | Check the evaluation context configuration and actual argument types. |
| Result does not have the expected type | `getValue(..., TargetType.class)` only converts the result after evaluation. | Adjust the expression/arguments and check the return type of the selected method. |
| Method is not allowed to be called in a restricted context | Resolver or policy only exposes a specific set of methods. | Add the method to the allowlist in a controlled way or create a suitable helper API. |

## Summary

- Overloads are methods with the same name but different parameter lists; overriding is replacing the implementation of the same signature.
- SpEL selects a method based on the runtime target class, name, argument count and types, and the context's conversion capability.
- Arguments with specific types help the resolver distinguish overloads clearly.
- Type conversion can make a call valid, but multiple overloads can make the intent ambiguous.
- `null` has no runtime class; avoid calling different reference overloads with `method(null)`.
- The target type of `getValue` is used for the result, not to select the overload.
- `MethodResolver`, `MethodFilter`, and `TypeConverter` can be customized to control method invocation capability.
- For important rules or untrusted expressions, expose a small, clear, and restricted helper API.

## References

- [Spring Framework Reference — Methods](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/methods.html)
- [Spring Framework Reference — Type Conversion](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework API — ReflectiveMethodResolver](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/ReflectiveMethodResolver.html)
- [Spring Framework API — StandardEvaluationContext](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardEvaluationContext.html)