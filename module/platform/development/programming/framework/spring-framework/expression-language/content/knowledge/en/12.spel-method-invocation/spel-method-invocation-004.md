# Varargs and Argument Conversion

When SpEL invokes a Java method, the expression can pass arguments directly, even when the method declares variable-length arguments (varargs). SpEL can also convert argument values to the types required by the method through the EvaluationContext's TypeConverter.

These two capabilities make expressions more concise, but it is necessary to understand how methods are found, how arguments are grouped into the varargs array, and when type conversion takes place. Otherwise, an expression can invoke the wrong overload, raise an evaluation error, or hide type incompatibilities.

## 1. How SpEL invokes methods

A method call in SpEL has the form:

~~~java
order.calculateTotal()
customer.findAddress('HOME')
#service.findById(42)
~~~

Methods can be invoked on the root object or on a variable placed in the EvaluationContext. For a variable, the syntax begins with the **#** symbol.

Example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext(order);

BigDecimal total = parser
        .parseExpression("calculateTotal()")
        .getValue(context, BigDecimal.class);
~~~

When evaluating a call, SpEL performs the main steps:

1. Identify the target object and method name.
2. Collect the arguments in the expression.
3. Find a matching method through MethodResolver.
4. Determine how to convert arguments if actual types differ from parameter types.
5. Execute the method and return the result.

In a typical configuration, StandardEvaluationContext uses reflection to resolve and invoke methods. Finding the method and converting arguments are two separate responsibilities: MethodResolver finds the matching method, while TypeConverter converts values to parameter types when needed.

Method invocation occurs during the evaluate phase. An expression can parse successfully yet still fail if the method does not exist, no matching overload is found, or the method throws an exception.

## 2. Varargs in Java

### 2.1. Declaring variable-length parameters

In Java, varargs allows a method to accept a variable number of arguments. A varargs parameter is declared with an ellipsis:

~~~java
public String join(String separator, String... values) {
    return String.join(separator, values);
}
~~~

When Java compiles, a varargs parameter is represented as an array. The method signature at the bytecode level has String[] as its final parameter.

The method can be called from Java in several ways:

~~~java
join(", ", "java", "spring", "spel");
join(", ", "java");
join(", ");
~~~

The variable arguments are collected into a String array. When no varargs arguments are passed, the method receives an empty array.

### 2.2. Invoking varargs methods from SpEL

SpEL supports invoking methods with varargs parameters. Extra arguments in the expression are collected into the final array parameter.

For example, create a formatter:

~~~java
public class TagFormatter {

    public String join(String separator, String... tags) {
        return String.join(separator, tags);
    }
}
~~~

Register the object in EvaluationContext:

~~~java
TagFormatter formatter = new TagFormatter();

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("formatter", formatter);
~~~

Invoke the method with multiple arguments:

~~~java
String result = parser
        .parseExpression(
                "#formatter.join(', ', 'java', 'spring', 'spel')"
        )
        .getValue(context, String.class);
~~~

Result:

~~~text
java, spring, spel
~~~

In the example, the first argument is the separator. The remaining arguments are collected into the tags array.

It can be called without varargs elements:

~~~java
#formatter.join(', ')
~~~

Or passing only one element:

~~~java
#formatter.join(', ', 'spring')
~~~

### 2.3. Passing an existing array

If the application already has an array, it can put the array into the context and pass it to the method:

~~~java
String[] tags = {"java", "spring", "spel"};

context.setVariable("tags", tags);

String result = parser
        .parseExpression("#formatter.join(', ', #tags)")
        .getValue(context, String.class);
~~~

The last argument is a String array created in Java. This approach is useful when the argument list is prepared from runtime data rather than written directly in the expression.

Do not confuse an array passed as a single argument with multiple separate arguments. If a method accepts a varargs parameter, both Java and reflection represent the trailing varargs part as an array. When integrating with overloaded methods, check the actual runtime type of the array argument to ensure the right method is chosen.

## 3. Varargs with primitive types and reference types

Varargs can use both primitive types and reference types:

~~~java
public long sum(long... values) {
    long total = 0;
    for (long value : values) {
        total += value;
    }
    return total;
}
~~~

Can be called from SpEL:

~~~java
#calculator.sum(10, 20, 30)
~~~

The result is 60.

With reference types:

~~~java
public String describe(Object... values) {
    return Arrays.toString(values);
}
~~~

SpEL can pass values of different types if the method and conversion permit:

~~~java
#formatter.describe('Spring', 3, true)
~~~

Do not choose Object... just to avoid defining parameter types. A method with a specific varargs type usually helps catch invalid data earlier and clarifies the API contract.

For primitive varargs such as long..., each trailing element must be convertible to the corresponding primitive type. If a null value is passed where a primitive is required, conversion cannot produce a valid primitive value and the call will fail.

## 4. Converting arguments with TypeConverter

### 4.1. Why is conversion needed?

Suppose a Java method requires a Long:

~~~java
public Customer findById(Long id) {
    // Look up customer
}
~~~

In an expression, data might come from a string:

~~~java
#customerService.findById('42')
~~~

The literal value '42' is a String, while the method requires a Long. SpEL can use the EvaluationContext's TypeConverter to convert String to Long if the converter supports it.

This is argument conversion during method invocation. It does not change the type of the original value in the root object or context variable.

### 4.2. StandardTypeConverter

StandardEvaluationContext by default provides a TypeConverter based on Spring's standard conversion mechanism. The default configuration can be used for common conversions:

~~~java
public class CustomerService {

    public String findById(Long id) {
        return "Customer-" + id;
    }
}
~~~

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("customerService", new CustomerService());

String result = parser
        .parseExpression("#customerService.findById('42')")
        .getValue(context, String.class);
~~~

If String-to-Long conversion is supported, the method receives the numeric value 42.

Do not assume every pair of types can be converted. Conversion capability depends on the configured ConversionService and TypeConverter. Empty strings, non-numeric strings, or domain types without a matching converter can cause evaluation errors.

### 4.3. Configuring a custom ConversionService

If the application needs custom conversion rules, register a converter on a ConversionService and supply it to StandardTypeConverter.

For example, a domain identifier type:

~~~java
public record CustomerCode(String value) {
}
~~~

Method requiring CustomerCode:

~~~java
public class CustomerService {

    public String lookup(CustomerCode code) {
        return "Customer code: " + code.value();
    }
}
~~~

Register the converter:

~~~java
DefaultConversionService conversionService =
        new DefaultConversionService();

conversionService.addConverter(
        String.class,
        CustomerCode.class,
        CustomerCode::new
);
~~~

Configure EvaluationContext:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setTypeConverter(
        new StandardTypeConverter(conversionService)
);

context.setVariable("customerService", new CustomerService());
~~~

The expression can pass a String literal:

~~~java
#customerService.lookup('C-1024')
~~~

TypeConverter uses the registered ConversionService to create a CustomerCode before invoking the method.

The converter should validate input data and throw a clear error if the string cannot represent a valid CustomerCode. Do not convert arbitrarily just so the method call technically runs while producing invalid domain data.

## 5. Converting individual varargs elements

Because a varargs parameter is represented as an array, each element needs to be compatible with that array's element type.

Example method:

~~~java
public long sum(long... values) {
    return Arrays.stream(values).sum();
}
~~~

Expression passing numeric literals:

~~~java
#calculator.sum(10, 20, 30)
~~~

If the input data is String and TypeConverter supports conversion to the numeric type, it can be configured so that arguments are converted to the parameter type. Example:

~~~java
#calculator.sum('10', '20', '30')
~~~

This capability depends on the converter and how the method is resolved. For important data, test with the exact Spring version and ConversionService of the application instead of assuming every element always converts automatically.

If an element cannot be converted, the method call cannot complete normally. Do not silently skip the failing element or substitute 0 unless business rules explicitly define that behavior.

With domain-type varargs, converters can be registered for each element:

~~~java
public Money total(Money... values) {
    // Calculate total according to domain currency rules
}
~~~

In that case, each value needs to be converted to Money according to the registered rules, and business constraints must be checked inside the method.

## 6. Argument conversion and overload resolution

### 6.1. Multiple methods with the same name

A class can declare multiple overloads:

~~~java
public String format(String value) {
    return "text:" + value;
}

public String format(Long value) {
    return "number:" + value;
}
~~~

When SpEL evaluates:

~~~java
#formatter.format('42')
~~~

SpEL must find a method matching the String argument type. If the argument can be converted to the parameter type of another overload, conversion capability also participates in the method resolution process.

Therefore, do not rely on the simple assumption that the method whose parameter type most closely resembles the literal will always be selected in every situation. The outcome also depends on existing overloads, the TypeConverter, and the configured resolver.

### 6.2. Overloading with varargs

Varargs overloads can make resolution more complex:

~~~java
public String render(String label, String... values) {
    return label + Arrays.toString(values);
}

public String render(String label, Object... values) {
    return label + Arrays.toString(values);
}
~~~

When multiple methods can accept the arguments, the resolver must choose the best matching method. If candidates cannot be clearly distinguished, SpEL may report a method mismatch or ambiguous match error.

To avoid ambiguity:

- Do not declare multiple varargs overloads differing only in a generic/super type unless truly necessary.
- Use distinct method names for different behaviors.
- Pass explicitly typed arguments from Java when disambiguating overloads.
- Register a custom MethodResolver only when the application truly needs a special resolution policy.
- Test cases with 0, 1, and multiple varargs elements.

An API with clear method names and parameter types generally makes expressions easier to read and more stable.

## 7. Difference between argument conversion and result conversion

TypeConverter can be used at multiple points during evaluation. Distinguish between:

1. **Argument conversion:** converting arguments to the method's parameter types before execution.
2. **Result conversion:** converting the Expression's return value to the type requested by the caller.

Example:

~~~java
String result = parser
        .parseExpression("#service.findById('42')")
        .getValue(context, String.class);
~~~

Here there can be two independent conversions:

- String '42' to Long to invoke findById(Long).
- The return value to String if the actual return type is not String and TypeConverter supports it.

If the method already returns String, no result conversion is needed.

You can retrieve the result as Object to inspect its runtime type:

~~~java
Object result = parser
        .parseExpression("#service.findById('42')")
        .getValue(context);
~~~

This is useful when debugging because it separates argument conversion errors from result conversion errors.

## 8. Cases where conversion fails

| Symptom | Possible cause | How to handle |
|---|---|---|
| Method not found | No method matches the name and argument count | Check method name, arity, and signature |
| String cannot be converted to number | Malformed string or unsupported converter | Check data and ConversionService |
| Cannot convert domain type | Converter not registered | Add appropriate Converter/GenericConverter |
| Null passed to primitive | Primitives cannot accept null | Use a wrapper or check for null beforehand |
| Multiple overloads match | Resolver cannot distinguish candidates | Clarify argument types or rename methods |
| Varargs element has wrong type | One or more elements cannot be converted | Check each value and element type |
| Method throws exception | Logic inside method failed | Handle the root cause in the method or Java layer |
| Result cannot be converted to target type | getValue(context, Target.class) has no matching converter | Retrieve as Object first or add a converter |

Errors in these cases occur when evaluating the expression. Successful parsing does not guarantee that the method will be found or that arguments will convert.

## 9. Designing methods to be called from SpEL

Methods exposed to expressions should have clear contracts:

- Prefer public methods with names that accurately reflect their behavior.
- Keep the number of overloads moderate to avoid ambiguity.
- Use varargs when the number of arguments is genuinely variable.
- Clearly define the varargs element type and how an empty list is handled.
- Validate null and invalid data inside the method or before calling.
- Keep methods pure when possible so expressions are predictable.
- Do not use methods called from SpEL to perform I/O or unnecessary state changes.

If a method requires too many arguments, that may be a sign to create a command object or request object in Java instead of passing a long varargs list.

For example, instead of:

~~~java
#reportService.create('Q4', 'VI', true, 100, 'FINANCE')
~~~

you can create a ReportRequest object in Java and place that object into the context:

~~~java
#reportService.create(#request)
~~~

This makes the method contract clearer as the number of parameters and business rules grows.

## 10. Security when invoking methods from expressions

StandardEvaluationContext supports method access through resolvers and reflection. Therefore, do not evaluate expressions submitted by untrusted users in a context that can invoke arbitrary methods on sensitive objects.

Some principles:

- Put only necessary objects into the EvaluationContext.
- Restrict methods with side effects or access to sensitive data.
- Control MethodResolver and MethodExecutor if a custom method invocation policy is required.
- Do not treat TypeConverter as an authorization mechanism.
- Do not allow converters to perform system access or external operations just to convert types.
- Limit the number of arguments and varargs data size if inputs are user-controlled.

Successful type conversion only indicates that data can be represented as the target type. It does not prove that the caller is authorized to execute that method or that the data is business-valid.

## 11. Testing varargs and conversion

Test argument counts, data types, and converters separately.

Example of testing varargs:

~~~java
TagFormatter formatter = new TagFormatter();

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("formatter", formatter);

assertEquals(
        "java, spring",
        parser.parseExpression(
                "#formatter.join(', ', 'java', 'spring')"
        ).getValue(context, String.class)
);

assertEquals(
        "",
        parser.parseExpression(
                "#formatter.join(', ')"
        ).getValue(context, String.class)
);
~~~

Testing String-to-Long conversion:

~~~java
CustomerService service = new CustomerService();

context.setVariable("customerService", service);

assertEquals(
        "Customer-42",
        parser.parseExpression(
                "#customerService.findById('42')"
        ).getValue(context, String.class)
);
~~~

With custom converters, test:

- Valid convertible values.
- Empty strings or null.
- Malformed values.
- Values outside the valid domain.
- Method receiving one argument and method receiving multiple varargs arguments.
- Overloads with the same name.
- Calls with a pre-created array.

These tests verify both conversion rules and method resolution behavior in the real configuration.

## 12. Summary

SpEL supports invoking Java methods with varargs parameters and uses TypeConverter to convert arguments to parameter types when needed.

- Varargs allows passing a variable number of arguments; trailing arguments are collected into an array per the method signature.
- TypeConverter and ConversionService determine which type conversions are supported.
- MethodResolver selects a matching method based on name, argument count and types, and conversion capability.
- Varargs overloads can cause ambiguity; design clear APIs and test edge cases.
- Argument conversion is distinct from getValue result conversion.
- Conversion errors and method invocation errors occur at evaluation time, not parse time.

Keep methods invoked from SpEL compact, with clear parameter types and minimal side effects. When method invocation rules become complex, prepare data or execute logic in Java and pass the result into EvaluationContext.## 13. Implementation checklist

Before introducing a method-calling expression into an application, verify:

- The method has a clear name and signature matching the argument count.
- Varargs parameters have a concrete element type and rules for handling zero elements.
- Runtime arguments can be converted to parameter types by the configured TypeConverter.
- Custom converters are registered on the exact ConversionService used by the context.
- Overloads do not create ambiguous cases when arguments have different types.
- Null and malformed data are handled according to business rules.
- The method does not perform unexpected side effects when the expression is evaluated.
- EvaluationContext provides only the objects and methods the expression needs to access.

If an expression requires too many preparation steps, move that processing into Java. SpEL is well suited for invoking an API with a stable contract, while data validation, authorization, and business orchestration should be kept where they can be clearly tested and controlled.