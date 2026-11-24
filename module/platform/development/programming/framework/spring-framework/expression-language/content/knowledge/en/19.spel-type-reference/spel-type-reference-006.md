# The instanceof Operator Combined with Type References

In SpEL, the instanceof operator checks the runtime type of a value. The left-hand side is the object to check; the right-hand side is usually a type reference written using the T(...) syntax. The result is a Boolean: true if the object is compatible with the specified type, false otherwise.

Combining instanceof with type references lets expressions branch by data type without manually calling getClass() or comparing class names. This approach is useful when a variable or property can hold multiple object types, such as an Object field, a value received from configuration, or different implementations of the same interface.

## 1. Syntax of instanceof and T(...)

General syntax:

~~~text
value instanceof T(TypeName)
~~~

Where:

- value is the object to check, usually a root property or context variable.
- instanceof is the type-checking operator.
- T(TypeName) is a type reference, representing a Class object that SpEL resolves.

Example:

~~~text
#value instanceof T(String)
#value instanceof T(java.lang.Number)
#value instanceof T(java.time.LocalDate)
~~~

The first expression checks whether value is a String. The second expression checks whether the object belongs to Number or a subclass of Number. The third expression checks whether the object is a LocalDate.

Java example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("value", "Spring");

Expression expression = parser.parseExpression(
        "#value instanceof T(String)"
);

Boolean result = expression.getValue(context, Boolean.class);

System.out.println(result); // true
~~~

T(...) is not a method name or variable. It is SpEL's special syntax for referencing a Java type. The instanceof operator uses the class resolved from the type reference to check the object on the left-hand side.

## 2. How does a type reference resolve a class name?

A type reference uses the T(...) syntax. The class name can be a simple name if the class belongs to a package already imported in TypeLocator, or a fully qualified name including the package.

StandardEvaluationContext uses StandardTypeLocator by default. The default TypeLocator imports java.lang, so you can write:

~~~text
T(String)
T(Integer)
T(Number)
T(Boolean)
~~~

For classes in other packages, write the fully qualified name:

~~~text
T(java.time.LocalDate)
T(java.math.BigDecimal)
T(java.util.UUID)
~~~

If the application wants to use short names for a specific package, it can register the package import on StandardTypeLocator:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

StandardTypeLocator typeLocator =
        new StandardTypeLocator();

typeLocator.registerImport("com.example.domain");

context.setTypeLocator(typeLocator);
~~~

Once the package is registered, expressions can reference types by simple name provided there is no name collision with another type. In shared expressions or expressions stored in long-lived configurations, fully qualified names are usually easier to identify and reduce reliance on hidden imports.

If SpEL cannot resolve the type in T(...), an error occurs when evaluating the expression. Check the package name, class name, and the TypeLocator used by the context.

## 3. Checking runtime type, not the declared variable type

instanceof checks the actual object referenced at evaluation time. It does not look only at the declared type of the Java variable.

Example:

~~~java
Object value = "Spring Expression Language";

context.setVariable("value", value);

Boolean isString = parser.parseExpression(
        "#value instanceof T(String)"
).getValue(context, Boolean.class);
~~~

Even though the Java variable is declared as Object, the actual object is String, so the result is true.

Similarly, if a variable is declared as Number but currently holds an Integer, checking against Integer can still return true:

~~~java
Number amount = Integer.valueOf(42);
context.setVariable("amount", amount);

Boolean isInteger = parser.parseExpression(
        "#amount instanceof T(Integer)"
).getValue(context, Boolean.class);
~~~

This matters when the root object or variable has a general type such as Object, Number, Serializable, or an interface. Think about the runtime type the data actually carries, not just the declared type in the Java signature.

## 4. Inheritance and interfaces

instanceof follows Java's type compatibility rules. An instance of a subclass is also considered an instance of its superclass and the interfaces it implements.

Example:

~~~java
Integer value = 42;
context.setVariable("value", value);
~~~

The following expressions all return true:

~~~text
#value instanceof T(Integer)
#value instanceof T(Number)
#value instanceof T(Comparable)
~~~

Integer is a subclass of Number and implements Comparable. Therefore, checking against the corresponding parent type or interface still succeeds.

This is useful when an expression only cares about a shared capability rather than a specific implementation. For example, checking Number accepts Integer, Long, Double, or BigDecimal; checking an interface can accept many different implementations.

Prefer checking an interface or superclass when the business logic needs shared behavior. Only check a concrete implementation when the distinction between object types truly matters.

## 5. Distinguishing instanceof from exact class comparison

instanceof checks type compatibility, including subclasses. It differs from comparing the exact runtime class.

Example:

~~~java
Object value = Integer.valueOf(42);
context.setVariable("value", value);
~~~

The expression:

~~~text
#value instanceof T(Number)
~~~

returns true because Integer is a Number.

If you need to check the exact class, you can compare the result of getClass() with a type reference:

~~~text
#value.getClass() == T(Integer)
~~~

This expression is true only when the exact runtime class is Integer. If value is another subclass of Number, the class comparison will be false even though instanceof Number is true.

Choose the check according to business intent:

| Requirement | Syntax |
|---|---|
| Object belongs to type or compatible subclass | value instanceof T(Type) |
| Object has exact runtime class | value.getClass() == T(Type) |
| Object implements an interface | value instanceof T(InterfaceType) |

Do not use string-based class name comparisons if you can use a type reference. Comparing Class directly avoids depending on fully qualified or shortened name formatting.

## 6. Handling null

A null value is not an instance of any reference type, so an instanceof check against null yields false.

Example:

~~~java
context.setVariable("value", null);

Boolean result = parser.parseExpression(
        "#value instanceof T(String)"
).getValue(context, Boolean.class);

System.out.println(result); // false
~~~

If you need to clearly distinguish null from an object of the wrong type, you can write two conditions:

~~~text
#value == null
#value != null and #value instanceof T(String)
~~~

AND short-circuits. If #value is null, the right-hand side does not need to be evaluated.

Normally, instanceof itself already returns false when the value is null. However, an explicit null check remains helpful when the expression continues to call methods or read properties after the type check:

~~~text
#value instanceof T(String) and #value.length() > 0
~~~

If value is null or not a String, the left-hand side is false and the length() call is skipped. This idiom both checks the type and guards operations valid only for String.

## 7. Using instanceof to branch by data type

instanceof can be combined with AND, OR, and other logical expressions to build data classification conditions.

~~~text
#payload instanceof T(String) and #payload.length() > 0
#amount instanceof T(Number) and #amount.doubleValue() > 0
#date instanceof T(java.time.LocalDate)
~~~

For example, a variable can hold multiple data types:

~~~java
context.setVariable("payload", "HELLO");

Expression expression = parser.parseExpression(
        "#payload instanceof T(String) and #payload.length() >= 5"
);

Boolean accepted = expression.getValue(context, Boolean.class);
~~~

Only if payload is a String does the expression check its length. If payload is an Integer or null, the first condition is false and the right-hand side is not executed.

Multiple branches can be combined:

~~~text
#value instanceof T(String) or #value instanceof T(Number)
~~~

The expression returns true if value is a String or a Number. With complex logic, use parentheses to clarify condition grouping and avoid confusion about precedence.

## 8. instanceof with root object properties

There is no need to put an object into a separate variable if it is already present on the root object. You can check the property directly:

~~~text
payload instanceof T(String)
amount instanceof T(java.math.BigDecimal)
metadata instanceof T(java.util.Map)
~~~

Example:

~~~java
public class Message {

    private Object payload;

    public Object getPayload() {
        return payload;
    }

    public void setPayload(Object payload) {
        this.payload = payload;
    }
}
~~~

Evaluation:

~~~java
Message message = new Message();
message.setPayload("Hello");

StandardEvaluationContext context =
        new StandardEvaluationContext(message);

Expression expression = parser.parseExpression(
        "payload instanceof T(String)"
);

Boolean isText = expression.getValue(context, Boolean.class);
~~~

SpEL reads the payload property on the root object, then checks the runtime type of the returned value. If payload is another object or null, the result is false accordingly.

If a property lies deep in the object graph, ensure intermediate links are accessible. When an intermediate object may be null, check for null first or use a data structure with explicit state.

## 9. instanceof with numeric types

Numeric types in Java have different inheritance relationships. Integer, Long, Double, and BigDecimal can all be checked using Number, but they are not the same class.

~~~text
#value instanceof T(Number)
#value instanceof T(Integer)
#value instanceof T(Long)
#value instanceof T(Double)
#value instanceof T(java.math.BigDecimal)
~~~

Example:

~~~java
context.setVariable("value", new BigDecimal("19.90"));

Boolean isNumber = parser.parseExpression(
        "#value instanceof T(Number)"
).getValue(context, Boolean.class);

Boolean isDecimal = parser.parseExpression(
        "#value instanceof T(java.math.BigDecimal)"
).getValue(context, Boolean.class);
~~~

Both results are true because BigDecimal is a subclass of Number.

If an expression only needs to know whether a value is numeric, checking Number is usually more flexible. If specific BigDecimal behavior such as scale or decimal arithmetic is needed, check BigDecimal specifically or design an appropriate method.

Do not confuse type conversion with instanceof. A string "42" can be converted to a number in an assignment or method call if a converter supports it, yet the string itself is not an instance of Number.

## 10. Limitations with generic types

instanceof checks the runtime class, not full Java generic type parameters. Due to type erasure, types like List<String> and List<Integer> share the same runtime class List.

Example:

~~~java
List<String> names = List.of("Lan", "Minh");
context.setVariable("value", names);
~~~

The expression:

~~~text
#value instanceof T(java.util.List)
~~~

returns true. However, SpEL cannot use a standard type reference to directly distinguish List<String> from List<Integer> with an instanceof check.

If element types need to be checked, inspect each element or normalize the data in Java:

~~~text
#value instanceof T(java.util.List)
~~~

Then, the application can iterate over the List and check each element's type in Java, or provide a clearly named pure method to validate the data contract.

Do not assume that because a List passes instanceof List, every element inside has the type the business logic expects. Collection type and element type are two separate things to verify.

## 11. TypeLocator and scope of referencable types

A type reference needs TypeLocator to resolve class names. StandardEvaluationContext typically uses StandardTypeLocator, which allows resolving many types by fully qualified name and package imports.

If an application evaluates user-supplied expressions, the ability to reference types must be considered an access privilege. Do not allow expressions to freely reference every class on the classpath if the use case only needs to check a few known domain types.

You can create a custom TypeLocator to restrict the set of resolvable types, or place only the necessary objects and capabilities into the context. Also control MethodResolver, PropertyAccessor, BeanResolver, and other capabilities if expressions are untrusted.

SimpleEvaluationContext is designed for a restricted SpEL feature set and does not provide type references like StandardEvaluationContext. If an expression needs T(...), confirm that the implementation/context used supports that capability; do not switch to a broadly permissive full context just to handle a simple type check.

## 12. Primitive and wrapper types

instanceof is a runtime object check. In Java, primitives such as int, long, or boolean are not objects and cannot appear directly on the left-hand side of instanceof.

When working with values in SpEL, remember that data is evaluated as objects and Java primitives are typically boxed into their corresponding wrappers, such as int into Integer when passed through generic APIs or the context.

Therefore, type references commonly used in instanceof checks are reference types:

~~~text
#value instanceof T(Integer)
#value instanceof T(Boolean)
#value instanceof T(Double)
~~~

Do not use T(int) as a substitute for T(Integer) in object checks. If you need to check the type of data the context holds, check the actual wrapper class.

## 13. Checking arrays and container types

Arrays in Java are objects, so an array value can be checked against superclasses or interfaces that arrays implement, such as Object or Cloneable. However, checking an array with a specific component type requires attention to how type references and actual runtime types are represented.

If an expression needs to distinguish a specific array, consider providing a strongly typed check method in Java instead of making type reference syntax hard to read. Similarly, instanceof List only confirms the object is a List; it does not prove the collection has the desired business ordering, is free of nulls, or has no mistyped elements.

For Map, Set, and other collections, check the interface matching the requirement. For example, instanceof Map confirms the container type; rules about keys/values still need separate validation.

## 14. Common errors

| Symptom | Common cause | Resolution |
|---|---|---|
| Cannot resolve T(...) | Wrong class name or TypeLocator cannot find the type | Use the fully qualified name or configure appropriate imports |
| instanceof returns false unexpectedly | Runtime object differs from the checked type | Check the actual class of the value |
| Subclass is not recognized | Performing exact class comparison instead of instanceof | Use instanceof when subtypes are accepted |
| Null makes condition false | null is not an instance of any reference type | Handle null according to business semantics |
| Wanting to check List<String> but only List is confirmed | Generic types undergo type erasure | Check each element or validate data in Java |
| Short name works in one environment but fails in another | TypeLocator imports differ | Use fully qualified package names or configure imports explicitly |
| SimpleEvaluationContext does not support type references | Context restricts features | Use an appropriate context or move type checking to Java |
| Numeric string treated as Number | Confusing conversion with runtime type relationship | Convert data first before checking instanceof |

## 15. Key takeaways

Use the syntax value instanceof T(Type) to check an object's runtime type. T(...) is a type reference resolved by TypeLocator; StandardTypeLocator imports java.lang by default so names like String, Integer, or Number can be used, while types in other packages should be written fully qualified.

instanceof accepts subclasses and interfaces implemented by the object, whereas comparing getClass() only checks the exact class. null always evaluates to false. Generic types are not fully checked due to type erasure, and primitives should be checked via their corresponding wrapper objects.

Use instanceof when expressions need to branch by actual type, combine short-circuiting to guard type-dependent operations, and restrict TypeLocator/context when expressions come from untrusted sources.