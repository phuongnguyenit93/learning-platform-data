# Element Types of Inline Collections in Spring Expression Language (SpEL)

SpEL allows declaring collections directly inside an expression using inline syntax. An inline list can contain numbers, strings, Booleans, null, or the results of other expressions. An inline map can combine different value types for keys and values. Therefore, when working with inline collections, you need to understand how each element's type is formed and what form Java receives the result in.

This lesson focuses on element types of inline lists and inline maps, homogeneous and heterogeneous collections, nested collections, dynamic values from EvaluationContext, how results are received in Java, and how to validate or convert types when an application needs a clearly typed data structure.

## 1. What is an inline collection?

An inline collection is a collection written directly inside a SpEL expression, without creating a List or Map variable beforehand in Java.

Two common forms:

~~~text
{1, 2, 3}
{'red', 'green', 'blue'}
{'name': 'An', 'age': 30}
~~~

- An inline list uses comma-separated elements enclosed in curly braces.
- An inline map uses key:value pairs, with each pair separated by commas.
- Elements can be literals or expressions evaluated when getValue() is called.

For example, the following expression creates a list of three numbers:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression("{1, 2, 3}");

List<?> numbers = expression.getValue(List.class);
~~~

Map expression:

~~~java
Expression expression = parser.parseExpression(
        "{'name': 'An', 'age': 30}"
);

Map<?, ?> person = expression.getValue(Map.class);
~~~

An inline list creates a List object; an inline map creates a Map object. They are not Java generic declaration syntax, nor do they automatically become arrays.

## 2. Type of each element in an inline list

Each element in an inline list is evaluated into an individual value. The runtime type of an element depends on the expression that produces that value.

Example:

~~~text
{'Spring', 42, true, null, 3.14}
~~~

This list can contain:

- String from the string literal 'Spring'.
- An integer type from the literal 42.
- Boolean from the literal true.
- A null value.
- A floating-point type from the literal 3.14.

SpEL does not require every element in an inline list to have the same type. A list can contain multiple different runtime types. Therefore, when receiving the result in Java, the appropriate type is usually List<?> or List<Object> rather than assuming every element is a String or Integer.

Example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
        "{'Spring', 42, true, null, 3.14}"
);

List<?> values = expression.getValue(List.class);

Object first = values.get(0);
Object second = values.get(1);
Object third = values.get(2);
Object fourth = values.get(3);
Object fifth = values.get(4);
~~~

Each element can be inspected:

~~~java
for (Object value : values) {
    if (value == null) {
        System.out.println("null");
    } else {
        System.out.println(value.getClass().getName());
    }
}
~~~

This snippet checks the runtime type of each element. A null element has no object on which to call getClass(), so null must be checked first.

## 3. Element types from SpEL literals

Literals in inline collections follow SpEL's own typing rules. A few common groups:

| Literal | Common value or type |
|---|---|
| 'text' | String |
| true, false | Boolean |
| null | null |
| 42 | Integer number, usually Integer for typical values |
| 42L | Long |
| 3.14 | Floating-point number, usually Double |
| 3.14F | Float |
| 3.14M | BigDecimal |

Example combining types:

~~~text
{'name', 25, 9000000000L, 3.14F, 19.99M, false}
~~~

The exact numeric type also depends on the value and literal suffix. When an application requires a specific numeric type, express that type explicitly or perform conversion at the Java boundary.

Do not infer that a list containing only numbers guarantees all elements have the same type. For example, a list can contain Integer, Long, BigDecimal, and Double at the same time. If calculations are needed, define the conversion policy and precision before use.

## 4. Homogeneous and heterogeneous inline lists

### 4.1. Homogeneous lists

A homogeneous list is a list whose elements have the same runtime type or adhere to a single type contract expected by the application.

Example:

~~~text
{'Spring', 'Spring Boot', 'Spring MVC'}
{10, 20, 30}
{true, false, true}
~~~

In Java, you can receive those results as List<?> and then validate or convert them to the desired type:

~~~java
List<?> rawNames = parser.parseExpression(
        "{'Spring', 'Spring Boot', 'Spring MVC'}"
).getValue(List.class);
~~~

Because the elements are all strings, the application can convert to List<String> after confirming the type. Do not simply cast the entire list without checking if the expression can be modified by users or external configuration.

### 4.2. Heterogeneous lists

A heterogeneous list contains elements of different types:

~~~text
{'An', 25, true, null}
~~~

This structure is useful when an expression needs to return a group of values with different meanings. However, it requires the receiving Java code to handle the type of each element.

~~~java
List<?> values = parser.parseExpression(
        "{'An', 25, true, null}"
).getValue(List.class);

String name = (String) values.get(0);
Integer age = (Integer) values.get(1);
Boolean active = (Boolean) values.get(2);
Object optionalValue = values.get(3);
~~~

The casts above are only safe if the expression content maintains the expected order and types. If configuration can change, check with instanceof or use a controlled conversion function.

Do not use a heterogeneous inline list as a complex data contract when the application needs multiple fields with stable names and types. In that case, a Java object or a Map with meaningful keys is usually easier to maintain.

## 5. Element types in inline maps

An inline map represents data as key:value pairs:

~~~text
{'name': 'An', 'age': 25, 'active': true}
~~~

Each key and value is an evaluated expression. Therefore, keys and values can have different types; values can also be heterogeneous.

Example:

~~~java
Expression expression = parser.parseExpression(
        "{'name': 'An', 'age': 25, 'active': true, 'note': null}"
);

Map<?, ?> result = expression.getValue(Map.class);

Object name = result.get("name");
Object age = result.get("age");
Object active = result.get("active");
Object note = result.get("note");
~~~

In this example, the keys are strings, while the values are String, an integer, Boolean, and null, respectively.

Map keys do not necessarily have to be strings if an expression produces another key type. However, for configuration or business data, strings are usually readable and convenient when accessing with get(key).

If two keys have equal values under equals/hashCode rules, the map will contain only one entry for that key after the expression is created. Therefore, do not rely on duplicate keys to store multiple independent values.

## 6. Elements as dynamic expressions

Inline collections do not only hold fixed literals. Elements can reference the root object, variables in EvaluationContext, or properties of an object.

Example using variables:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();

context.setVariable("userName", "An");
context.setVariable("minimumAge", 18);

Expression expression = parser.parseExpression(
        "{#userName, #minimumAge, #minimumAge + 2}"
);

List<?> values = expression.getValue(context, List.class);
~~~

The result contains the values of the variables and the calculation result. The third element is the result of the expression #minimumAge + 2, not the expression string itself.

Example using a root object:

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
}

Customer customer = new Customer("Lan", 25);

Expression expression = parser.parseExpression(
        "{name, age, age >= 18}"
);

List<?> values = expression.getValue(customer, List.class);
~~~

The elements respectively retrieve name, age, and the comparison result age >= 18 from the root object customer. The type of each element is the type of the value returned by its sub-expression.

If variables or properties change between evaluations, the corresponding element values may also change according to the context or root object passed into getValue().

## 7. Nested inline collections

An inline list can contain other lists. This creates a multi-level structure:

~~~text
{{1, 2}, {3, 4}, {5, 6}}
~~~

The result is a List whose elements are also Lists.

~~~java
Expression expression = parser.parseExpression(
        "{{1, 2}, {3, 4}, {5, 6}}"
);

List<?> matrix = expression.getValue(List.class);

List<?> firstRow = (List<?>) matrix.get(0);
Object firstValue = firstRow.get(0);
~~~

You can nest maps inside lists or lists inside maps:

~~~text
{{'id': 1, 'name': 'An'}, {'id': 2, 'name': 'Binh'}}
~~~

~~~text
{'roles': {'reader', 'editor'}, 'enabled': true}
~~~

With nested structures, types must be checked at each level. An outermost List<?> tells nothing about the types of the inner elements. Each element could be a List, a Map, or a single value.

Do not deeply cast the entire structure without a clear contract. Inspect each level or convert to strongly typed domain classes.

## 8. Inline collections and Java generic types

SpEL returns Java collection objects, but Java generic types are not preserved as part of normal runtime types. For example, List<String> and List<Integer> both have the runtime class java.util.List.

When calling:

~~~java
List<?> values = expression.getValue(List.class);
~~~

the List.class argument only requests that the result be a List. It does not require SpEL to guarantee every element is a String.

The following snippet compiles but does not prove that every element is actually a String:

~~~java
@SuppressWarnings("unchecked")
List<String> names = (List<String>) expression.getValue(List.class);
~~~

Generic types are erased at runtime, so the cast above does not check individual elements. An error may appear later when the application retrieves an element and uses it as a String.

A safer approach is to receive List<?> and then validate:

~~~java
List<?> values = expression.getValue(List.class);
List<String> names = new ArrayList<>();

for (Object value : values) {
    if (!(value instanceof String)) {
        throw new IllegalArgumentException(
                "Expected a String element"
        );
    }

    names.add((String) value);
}
~~~

After the loop completes, names contains verified String elements. This is useful when expressions are externally configured and their content may change.

## 9. Element type conversion

SpEL has a TypeConverter mechanism via EvaluationContext. Conversion is used when an expression needs to supply a value to a location with a target type, such as assigning to a property or passing into a call with a specifically typed parameter.

However, retrieving an inline list with getValue(List.class) does not automatically produce a generic contract like List<String>. The List class carries no element type information. If a homogeneous list is needed, the application should validate or convert each element to the target type.

Example of controlled conversion in Java:

~~~java
List<?> rawValues = parser.parseExpression("{'10', '20', '30'}")
        .getValue(List.class);

List<Integer> numbers = new ArrayList<>();

for (Object value : rawValues) {
    if (!(value instanceof String)) {
        throw new IllegalArgumentException("Expected numeric text");
    }

    numbers.add(Integer.valueOf((String) value));
}
~~~

After conversion, numbers has element type Integer. If an element is not a valid numeric string, Integer.valueOf throws an error; the application must handle that error according to business requirements.

When converting a collection to a property with a declared generic type, Spring can use TypeDescriptor to obtain additional target type metadata and assist with element conversion. The exact result depends on the converter, source type, and target type supplied to the conversion operation.

## 10. Inline collection literals and reuse

SpEL can optimize inline lists containing only fixed values. For a list where all elements are fixed literals, the parser may create a constant list to avoid rebuilding the list on every evaluation.

This has two design implications:

- Inline collections are suitable for representing fixed input data for an expression.
- Do not treat a collection literal as a mutable state holder across multiple evaluations.

If the application needs to add, remove, or modify elements, create a separate collection in Java or pass a collection through a variable in EvaluationContext. Do not rely on an inline list being mutable or having the same identity across calls.

When elements depend on variables, the root object, or dynamic data, values must be evaluated against the current context. Treat inline collections as expression results, not places to store business state.

## 11. Inline lists, inline maps, and Java arrays

These three structures serve different roles:

| Structure | Result form | Access |
|---|---|---|
| Inline list | List | By index, e.g., get(0) |
| Inline map | Map | By key, e.g., get("name") |
| Java array | Array with a specific component type | By index, e.g., array[0] |

Inline lists and inline maps are convenient when an expression needs to create a collection. If Java code requires an array of type String[] or int[], perform an explicit conversion on the Java side or use SpEL's appropriate array creation mechanism.

Do not assume an inline list can be directly assigned to every array parameter. Lists and arrays are two different structures even though both hold multiple elements.

## 12. Practical example: creating condition lists and configuration

An expression can create a list containing Boolean conditions from the root object:

~~~java
public class Account {
    private final int age;
    private final boolean active;
    private final boolean verified;

    public Account(int age, boolean active, boolean verified) {
        this.age = age;
        this.active = active;
        this.verified = verified;
    }

    public int getAge() {
        return age;
    }

    public boolean isActive() {
        return active;
    }

    public boolean isVerified() {
        return verified;
    }
}

Account account = new Account(25, true, false);

Expression expression = parser.parseExpression(
        "{age >= 18, active, verified}"
);

List<?> checks = expression.getValue(account, List.class);
~~~

The resulting List has three Boolean elements. Each element is the result of a sub-expression. The application can inspect each condition or combine them in a subsequent processing step.

An inline map can create a small configuration:

~~~java
Expression expression = parser.parseExpression(
        "{'minAge': 18, 'roles': {'reader', 'editor'}, 'enabled': true}"
);

Map<?, ?> configuration = expression.getValue(Map.class);

Object minAge = configuration.get("minAge");
Object roles = configuration.get("roles");
Object enabled = configuration.get("enabled");
~~~

This map contains an integer, a nested collection, and a Boolean. Because the value types are heterogeneous, Map<?, ?> is a safe receiving type before checking or converting each value.

## 13. Common mistakes

| Mistake | Cause | Resolution |
|---|---|---|
| Assuming all elements have the same type | Inline lists allow multiple runtime types. | Use List<?> and check each element. |
| Casting List<?> to List<String> without checking | Generic types are not verified at runtime. | Iterate elements and validate or convert. |
| Calling getClass() on a null element | null has no object on which to invoke methods. | Check for null first. |
| Confusing inline lists with arrays | Inline lists create a List, not an array. | Convert explicitly if the target API requires an array. |
| Assuming a Map has all values of the same type | Map values can differ in type. | Use Map<?, ?> and determine types by key. |
| Ignoring the type of nested collections | Outer elements may be a List or Map. | Check each level before casting. |
| Using a fixed inline list to store state | Fixed literal lists may be optimized by SpEL into constant lists. | Create a separate mutable collection in Java when modification is needed. |
| Assuming getValue(List.class) checks generic types | The List class carries no List<String> or List<Integer> metadata. | Validate or convert elements at the Java boundary. |
| Not handling conversion errors | Data may be malformed or incompatible. | Validate data and handle conversion errors. |

## 14. Takeaways

- Inline lists use the syntax {value1, value2}; inline maps use {key: value} pairs.
- Inline lists return a List; inline maps return a Map.
- Each element is evaluated separately and retains the runtime type of the value that produced it.
- An inline list or map can contain multiple different data types.
- Elements can be literals, variables, properties, operations, or nested collections.
- List<?> and Map<?, ?> are safe receiving types before individual element types are confirmed.
- Java generic types are not checked solely by getValue(List.class).
- Use TypeConverter or controlled conversion when the application needs specific element types.
- Inline collections are suitable for representing data in expressions; create separate Java collections when storing state or modifying elements.
