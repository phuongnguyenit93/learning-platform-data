# Property and Method Access Operators

## Objectives

In Spring Expression Language (SpEL), the dot lets you navigate from the current object to its property or method. This syntax allows expressions to read nested data, invoke object behavior, and combine multiple steps into one result. To use it safely, you need to distinguish property access from method invocation, understand which object is currently being accessed, and know what operations EvaluationContext permits.

After this lesson, you will be able to:

- Read properties of the root object and nested objects using dot syntax.
- Call instance methods with or without parameters.
- Access elements in a List, array, and Map using the index operator.
- Handle potentially null objects with safe navigation.
- Read or write properties according to the permissions allowed by EvaluationContext.
- Identify and handle common property/method errors.

## 1. The Dot and the Object Currently Being Accessed

The dot (.) is the navigation syntax in SpEL. The left side identifies the current object; the right side specifies the property to read or method to call on that object.

Suppose the application has the following model:

~~~java
public class Person {
    private String name;
    private Address address;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public Address getAddress() {
        return address;
    }

    public void setAddress(Address address) {
        this.address = address;
    }
}

public class Address {
    private String city;

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }
}
~~~

If the root object is a Person, the following expressions have these meanings:

| Expression | Meaning |
|---|---|
| **name** | Read the name property of the root object |
| **address** | Read the address property of the root object |
| **address.city** | Read address, then read city on Address |
| **#root.name** | Read name by explicitly specifying the root object |
| **#root.address.city** | Same nested path, but explicitly specifying root |

When the root object has already been passed in at evaluation time, you can reference properties of root directly without writing #root. Use #root when you want to clarify the starting point or when the expression has multiple navigation steps.

## 2. Property Access: Reading an Object's Properties

Property access uses the property name, without needing to write the getter name:

~~~text
name
address.city
~~~

For JavaBeans, the property name is usually mapped to the getter getName(), while a Boolean property active is usually mapped to isActive() or the appropriate getter. Therefore, name is property access syntax; it is not an arbitrary shorthand for a method call.

SpEL performs access through PropertyAccessor in EvaluationContext. Under the common default configuration, reflective accessors can use the JavaBean properties and public fields they support. Applications can also register a custom accessor to map properties according to another rule.

Example of reading a property in Java:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("address.city");

SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();

String city = expression.getValue(context, person, String.class);
~~~

Here, person is the root object. SpEL reads the address property, then reads city from the returned Address object. The String.class result type clearly states the type the application expects.

The property name must match the name supported by the accessor. If the model renames the getter, changes the object structure, or the accessor no longer provides that property, the expression may fail at runtime even though the Java code still compiles.

### Nested Properties

Multiple properties can be chained with dots:

~~~text
order.customer.address.city
~~~

Each step uses the result of the previous step. The expression can only evaluate if every intermediate object exists and the corresponding property is accessible. If customer or address can be null, handle it explicitly rather than assuming the path is always complete.

### Properties of Map, List, and Array

When data resides in a collection structure, SpEL supports the index operator:

~~~text
settings['theme']
items[0]
orders[0].total
matrix[0][1]
~~~

- For a Map, use the key inside square brackets, for example settings['theme'].
- For a List or array, use a zero-based index, for example items[0].
- You can continue navigating after retrieving an element, for example orders[0].total.

Check whether the Map contains the requested key, whether the List/array has an element at that position, and whether the retrieved element has the expected type. Out-of-bounds index access or using a nonexistent key can lead to errors or unexpected missing values depending on the data type and accessor.

## 3. Method Invocation: Calling an Object's Methods

To call a method, write the method name followed by parentheses. Parameters are placed inside the parentheses and separated by commas:

~~~text
getName()
formatName('Nguyen')
calculateTotal(10, 2)
~~~

If the root object is Person, the expression getName() calls the method on root. You can write #root.getName() to explicitly indicate the object receiving the call.

Differences to remember:

| Syntax | Operation Type |
|---|---|
| **name** | Read the name property |
| **getName()** | Call the method named getName |
| **address.city** | Read the city property on the address object |
| **address.getCity()** | Call the getCity method on the address object |
| **address.city.toUpperCase()** | Read city, then call a method on the return value |

Property access and method invocation can yield the same value in a JavaBean, but they are two different resolution mechanisms. Property access depends on PropertyAccessor; method invocation depends on MethodResolver.

### Passing Arguments

Arguments can be literals, variables, or the result of another expression:

~~~text
greet('Lan')
calculatePrice(#quantity, #unitPrice)
isAllowed(order.customer)
~~~

Strings are enclosed in single quotes. Variables in EvaluationContext are referenced with #, for example #quantity. If a method accepts multiple parameters, the order and types of arguments must match the method signature.

SpEL can resolve methods based on name and argument types; type conversion may be performed through the context's TypeConverter. With overloaded methods, test the actual input types to ensure SpEL selects the intended method. Do not rely on an implicit conversion that the application does not explicitly specify.

### Calling Methods Without Parameters

Parentheses still must be written even when the method takes no parameters:

~~~text
customer.getName()
customer.isActive()
~~~

Write customer.name if the goal is to read a JavaBean property. Write customer.getName() if the goal is to call the method of that exact name. This style makes intent clear and helps avoid confusion when a class has a custom accessor.

### Calling Methods in a Path

An expression can read a property, call a method, and continue navigating:

~~~text
order.customer.getName().toUpperCase()
~~~

Read from left to right: get customer from order, call getName, then call toUpperCase on the returned String. Each step depends on the previous step's result. If one step returns null, the next step may fail unless handled with safe navigation.

## 4. Safe Navigation When an Object May Be Null

The safe navigation operator is **?.**. It allows accessing a property or calling a method without throwing an error solely because the object immediately to the left of the operator is null. When that object is null, the result of the access step is null.

Example:

~~~text
customer?.name
customer?.getName()
~~~

If customer is null, the expression returns null for the corresponding access step. If customer has a value, SpEL proceeds to read the property or call the method as usual.

For multi-level paths, place safe navigation at each point that may be null:

~~~text
order?.customer?.address?.city
~~~

If order can be null while customer or address can also be null, writing only order?.customer.address.city does not fully express the points that need protection. Assess the nullability of each intermediate object and use ?. at the right positions.

Safe navigation also applies to method invocations:

~~~text
customer?.getName()?.toUpperCase()
~~~

Here, the first ?. guards the getName call when customer is null; the second ?. guards the toUpperCase call when the result of getName is null.

Do not use safe navigation to mask required data. If business logic requires customer to exist, returning null may cause subsequent conditions to silently fail to match. In that case, validating input and reporting an explicit error may be more appropriate.

## 5. Reading and Writing Properties

Reading properties usually uses getValue. When an expression points to a writable property, SpEL also supports setValue, provided PropertyAccessor and EvaluationContext allow writing.

Example:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression nameExpression = parser.parseExpression("name");

SimpleEvaluationContext readContext =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();

String currentName =
    nameExpression.getValue(readContext, person, String.class);

SimpleEvaluationContext writeContext =
    SimpleEvaluationContext.forReadWriteDataBinding().build();

nameExpression.setValue(writeContext, person, "Lan");
~~~

A read-only context is appropriate when the expression only needs to read data. A read-write context allows writing according to the supported data binding mechanism. If a property has no setter or the accessor does not support writing, setValue will fail.

Only allow writing when it is an explicit application requirement. For expressions coming from configuration or users, property write permission can mutate object state and create hard-to-control side effects.

## 6. EvaluationContext Determines Access Capabilities

EvaluationContext provides the components used to resolve properties and methods. Context configuration determines which properties an expression can read, which methods it can call, and whether it is allowed to modify objects.

**StandardEvaluationContext** typically uses reflection-based mechanisms to access properties and resolve methods. It is flexible and can be extended with PropertyAccessor, MethodResolver, and other components. Configure only the necessary capabilities and control the expression source.

**SimpleEvaluationContext** is suitable for data binding with a narrower scope. Example of reading properties:

~~~java
SimpleEvaluationContext readOnly =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();
~~~

If an expression needs to call instance methods in SimpleEvaluationContext, you can enable that capability explicitly:

~~~java
SimpleEvaluationContext methodContext =
    SimpleEvaluationContext.forReadOnlyDataBinding()
        .withInstanceMethods()
        .build();
~~~

Do not assume that a method can be called in every context. An expression may work with StandardEvaluationContext yet fail in SimpleEvaluationContext if instance methods have not been enabled or MethodResolver does not provide the corresponding capability.

When the application uses a custom PropertyAccessor or MethodResolver, use the same configuration in tests and in the actual evaluation flow. This avoids the situation where an expression works in tests but fails in deployment.

## 7. A Complete Example

Suppose Person has property name and method greet(String suffix):

~~~java
public class Person {
    private String name;

    public Person(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String greet(String suffix) {
        return "Hello " + name + suffix;
    }
}
~~~

You can read the property and call the method with SpEL:

~~~java
ExpressionParser parser = new SpelExpressionParser();

SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding()
        .withInstanceMethods()
        .build();

Person person = new Person("Lan");

Expression propertyExpression = parser.parseExpression("name");
String name =
    propertyExpression.getValue(context, person, String.class);

Expression methodExpression = parser.parseExpression("greet('!')");
String greeting =
    methodExpression.getValue(context, person, String.class);
~~~

Expected results:

- name returns Lan.
- greet('!') returns Hello Lan!.

This example shows that property access and method invocation can share one root object and one parser. Method calling capability is explicitly enabled in SimpleEvaluationContext.

## 8. Common Errors and How to Diagnose Them

| Symptom | Possible Cause | What to Check |
|---|---|---|
| Property not found | Wrong name, unsuitable getter, or unsupported accessor | Check the model, JavaBean properties, and PropertyAccessor |
| Intermediate property is null | Nested path assumes the object always exists | Check nullability and add safe navigation at the right step |
| Method not found | Wrong name, wrong parameter count, or method not supported by resolver | Check method signature and MethodResolver |
| Overloaded method not resolved as intended | Ambiguous argument types or conversion | Test actual argument types and TypeConverter configuration |
| Method call fails in SimpleEvaluationContext | Instance methods not yet enabled | Check builder and method resolver configuration |
| Cannot write property | Read-only property or accessor does not support writing | Check setter, accessor, and context type |
| Error when using [0] | Empty collection or index out of bounds | Check size and data rules before accessing |

When troubleshooting errors, identify the full expression, root object, context type, and data type at the failing step. Do not look only at the expression string: the same expression may work with one context but not with another.

## 9. Best Practices

- Use property syntax for reading data and method syntax when you genuinely need to invoke object behavior.
- Keep property paths short and easy to understand; if many levels must be chained, consider creating a derived property or a clearly named method in the model/service.
- Use ?. for points that may be null, but do not replace required data validation with silent null values.
- Check collections and indices before accessing elements.
- Test overloaded methods and type conversions with actual argument types.
- Only enable instance methods or property write permissions when the expression needs them and the expression source is controlled.
- Avoid calling methods with side effects such as writing to a database, sending notifications, or mutating state in an expression evaluated multiple times.
- Do not evaluate expressions supplied by untrusted sources using a context with broad access permissions.
- Parse an expression once when loading or updating configuration and reuse the Expression when appropriate.
- When refactoring the model, search for SpEL strings referencing properties and methods because the Java compiler cannot guarantee detecting every string-based reference.

## 10. Checklist

Before using an expression with property or method access, check:

- [ ] The root object and property path are clearly identified.
- [ ] Property names match the actual accessor and model.
- [ ] Intermediate objects that may be null are handled.
- [ ] Map keys and collection indices have clear existence rules.
- [ ] Method name, parameter count, and argument types match.
- [ ] EvaluationContext supports the required properties/methods.
- [ ] Property write permissions are only enabled when truly needed.
- [ ] Invoked methods do not produce unintended side effects.
- [ ] Normal cases, null, empty collections, and resolution errors have been tested.

## Conclusion

The dot in SpEL allows navigating from the root object to properties or methods of nested objects. Property access reads data via PropertyAccessor; method invocation calls behavior via MethodResolver. Combined with the index operator and safe navigation, expressions can describe quite flexible data paths. To keep expressions maintainable, clarify the root object, control EvaluationContext, handle null intentionally, and test both property names and method signatures.
