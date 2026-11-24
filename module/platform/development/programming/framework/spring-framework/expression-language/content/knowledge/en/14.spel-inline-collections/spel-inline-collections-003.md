# Creating Inline Maps with Keys and Values in SpEL

Spring Expression Language (SpEL) allows declaring a Map directly in an expression using inline map syntax. This is useful when you need to create a small key-value structure to pass to a method, represent metadata, build configuration, or gather values computed from the current object.

An inline map has key and value pairs separated by commas. Keys are string literals placed in single quotes; values can be literals or SpEL expressions. Therefore, a map can both contain fixed values and pull data from variables, properties, or calculations in EvaluationContext.

## 1. Objectives and prerequisites

After this lesson, you can:

- Recognize inline map syntax and distinguish it from inline lists.
- Declare key-value pairs in a SpEL expression.
- Use string literals as keys and expressions as values.
- Pass variables, read properties, and compute values in a map.
- Create nested maps and combine maps with inline lists.
- Read an element by key after receiving the map result.
- Understand how SpEL handles fixed literal maps and maps with dynamic values.
- Know when to create a map in Java instead of writing it inline in SpEL.

You should know how to use SpelExpressionParser, Expression.getValue(), and StandardEvaluationContext to pass variables into expressions.

## 2. What is an inline map?

A Map is a data structure that stores key-value pairs. In SpEL, you can create a map directly inside the expression string instead of creating a Map object beforehand in Java.

Example:

~~~text
{'name': 'Spring', 'version': 6}
~~~

The expression above creates a map with two pairs:

| Key | Value |
|---|---|
| name | Spring |
| version | 6 |

Keys are written as string literals in single quotes. Values can be strings, numbers, booleans, null, or an expression returning an appropriate value.

Another example:

~~~text
{'enabled': true, 'retryCount': 3, 'description': 'default policy'}
~~~

Inline maps are usually suitable for small data with a known structure. For large data, frequent changes, or complex operations, create the Map in Java and pass it into the context.

## 3. Basic syntax

General syntax:

~~~text
{'key1': value1, 'key2': value2, 'key3': value3}
~~~

Components:

- Curly braces surround the map.
- Keys are string literals enclosed in single quotes.
- A colon separates the key and value.
- A comma separates key-value pairs.
- A value is a valid SpEL expression.

Example:

~~~text
{'id': 1001, 'active': true, 'name': 'An'}
~~~

You can write the expression across multiple lines for readability as long as the string passed to the parser preserves the syntax:

~~~text
{
    'id': 1001,
    'active': true,
    'name': 'An'
}
~~~

Avoid duplicate keys because when a key is declared multiple times, the previous value may be overwritten during Map creation. A structure with unique keys is easier to understand and maintain.

## 4. Distinguishing inline maps from inline lists

SpEL uses curly braces for both inline lists and inline maps. The distinguishing mark is the colon between key and value.

| Structure | Example | Meaning |
|---|---|---|
| Inline list | {'red', 'green', 'blue'} | List of elements |
| Inline map | {'color': 'red', 'enabled': true} | Key-value pairs |

A List holds values by position; a Map holds values looked up by key. When describing named properties such as name, status, or configuration, an inline map is usually more suitable.

A map can contain a list as a value:

~~~text
{
    'name': 'Spring',
    'tags': {'java', 'framework', 'expression'}
}
~~~

Conversely, a list can also contain maps:

~~~text
{
    {'id': 1, 'name': 'A'},
    {'id': 2, 'name': 'B'}
}
~~~

The second structure is a list of maps; it is useful when representing a small set of records in an expression.

## 5. Using different value types

Values in an inline map are not limited to strings. You can use numbers, booleans, null, and expressions that return objects.

~~~text
{
    'name': 'Spring',
    'majorVersion': 6,
    'stable': true,
    'deprecated': false,
    'note': null
}
~~~

Some examples:

~~~text
{'count': 10 + 5}
~~~

~~~text
{'isAdult': #age >= 18}
~~~

~~~text
{'displayName': #firstName + ' ' + #lastName}
~~~

~~~text
{'upperName': #person.name.toUpperCase()}
~~~

Values are evaluated according to the SpEL context. If a value references an unregistered variable, a nonexistent property, or an uncallable method, evaluation may fail.

Keys and values have different rules: the key of an inline map is a string literal enclosed in single quotes; the value is where dynamic expressions are normally placed. If you need dynamic keys, build the Map in Java and pass that map into SpEL.

## 6. Using variables in values

SpEL variables have the # prefix. The application registers variables in EvaluationContext before evaluating the map:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "{'name': #name, 'age': #age, 'active': #active}"
);

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("name", "An");
context.setVariable("age", 25);
context.setVariable("active", true);

Map<?, ?> result =
    expression.getValue(context, Map.class);
~~~

The result is a map equivalent to:

~~~text
{
    'name': 'An',
    'age': 25,
    'active': true
}
~~~

You can change variable values and re-evaluate the same expression:

~~~java
context.setVariable("name", "Binh");
context.setVariable("age", 30);

Map<?, ?> anotherResult =
    expression.getValue(context, Map.class);
~~~

The resulting map on the next evaluation pulls the new values from the context. This approach keeps the map structure stable while data changes across evaluations.

There is no need to concatenate values into the expression string. Passing data via variables keeps a boundary between syntax and data, while avoiding escaping errors when values contain quotes or special characters.

## 7. Getting values from object properties

An inline map can use properties of the root object or an object passed via a variable:

~~~java
public class Customer {
    private Long id;
    private String name;
    private boolean active;

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public boolean isActive() {
        return active;
    }
}
~~~

Expression:

~~~text
{'customerId': #customer.id, 'customerName': #customer.name, 'active': #customer.active}
~~~

Register customer:

~~~java
context.setVariable("customer", customer);

Map<?, ?> summary =
    parser.parseExpression(
        "{'customerId': #customer.id, 'customerName': #customer.name, 'active': #customer.active}"
    ).getValue(context, Map.class);
~~~

SpEL reads properties according to the PropertyAccessors in the context. If customer is null, or a property path is invalid, evaluating the corresponding value may fail. Use null-safe navigation on the value if the data can be null:

~~~text
{'customerName': #customer?.name ?: 'Guest'}
~~~

Null-safe navigation and Elvis are evaluated inside the value; the key remains a string literal.

## 8. Combining calculations in values

One advantage of inline maps is grouping computed values into a single structure:

~~~text
{
    'subtotal': #price * #quantity,
    'discount': #price * #quantity * #discountRate,
    'total': (#price * #quantity) * (1 - #discountRate)
}
~~~

The resulting map can be used as a summary or input for a subsequent step.

Use parentheses when a formula has multiple operators to express calculation order. For long business formulas or monetary rounding, consider computing in Java to manage BigDecimal, scale, and rounding explicitly.

A conditional example:

~~~text
{
    'eligible': #customer.active and #order.total >= #minimum,
    'label': #order.total >= #minimum ? 'QUALIFIED' : 'PENDING'
}
~~~

Each value is evaluated as a separate expression. If any value errors, the entire map creation may not complete.

## 9. Nested maps

The value of a key can be another inline map. This fits data with a hierarchical structure:

~~~text
{
    'customer': {
        'id': #customerId,
        'name': #customerName
    },
    'order': {
        'number': #orderNumber,
        'total': #orderTotal
    }
}
~~~

Nested data can be read using index syntax:

~~~text
#result['customer']['name']
~~~

If the map is returned directly from the expression, Java can read it via the Map API:

~~~java
Map<?, ?> result = expression.getValue(context, Map.class);

Object customerValue = result.get("customer");

if (customerValue instanceof Map<?, ?> customerMap) {
    Object customerName = customerMap.get("name");
}
~~~

When maps are nested across multiple levels, keep key names clear and avoid overly deep structures. If the data is a stable API contract, a typed DTO is usually safer and easier to maintain than nested Maps.

## 10. Combining maps with inline lists

A map can contain lists as values, such as a list of roles or tags:

~~~text
{
    'username': #username,
    'roles': {'ADMIN', 'EDITOR'},
    'permissions': {'read', 'write'}
}
~~~

A list can also contain maps:

~~~text
{
    {'code': 'VN', 'name': 'Vietnam'},
    {'code': 'SG', 'name': 'Singapore'}
}
~~~

This is a way to represent a small dataset directly inside an expression. If the list is long, updated frequently, or needs validation, initialize it in Java and pass it into the context instead of embedding all the data in the SpEL string.

## 11. Accessing a map after creation

After receiving the map result, you can retrieve a value by key using index syntax:

~~~text
#settings['theme']
~~~

If the map is a variable registered in the context:

~~~java
Map<String, Object> settings = new HashMap<>();
settings.put("theme", "dark");
settings.put("maxItems", 20);

context.setVariable("settings", settings);

Expression expression =
    parser.parseExpression("#settings['theme']");

String theme =
    expression.getValue(context, String.class);
~~~

The result is dark.

For an inline map created in an expression, you can retrieve the map into Java and read it with get(key). Distinguish between a missing key and a key whose value is null. Both cases can cause a read to return null; if you need to distinguish them, use Map.containsKey(...) in Java or provide a separate check rule.

## 12. Fixed literal maps and dynamic values

SpEL can optimize an inline map containing only fixed literals or nested constant structures by creating a constant map to reuse for the expression. If one or more values depend on runtime data, such as variables or properties, the map is created when the expression is evaluated to capture the current values.

Fixed map example:

~~~text
{'mode': 'SAFE', 'maxRetries': 3}
~~~

Dynamic map example:

~~~text
{'user': #username, 'createdAt': #timestamp}
~~~

This distinction matters when designing an application. Do not rely on a fixed inline map creating a new object on every evaluation. If you need a mutable map to modify, create a copy in Java:

~~~java
Map<?, ?> literal =
    parser.parseExpression("{'mode': 'SAFE', 'maxRetries': 3}")
        .getValue(Map.class);

Map<Object, Object> mutableCopy =
    new LinkedHashMap<>(literal);
~~~

Treat fixed literal maps as read-only data. This avoids depending on internal parser optimization details and prevents unintended modifications from affecting subsequent uses.

## 13. Using inline maps in Spring

Inline maps can appear in Spring integration points that accept SpEL, such as @Value:

~~~java
@Value("#{ {'mode': 'SAFE', 'maxRetries': 3} }")
private Map<String, Object> defaults;
~~~

The expression creates a map with two key-value pairs. Spring evaluates the expression in the container's context and assigns the result to the property if the result type is compatible.

You can create a map whose values come from other beans or properties, depending on the resolver and context Spring provides:

~~~java
@Value("#{ {'serviceName': @serviceInfo.name, 'enabled': @featureFlags.enabled} }")
private Map<String, Object> serviceSettings;
~~~

Only use bean references when a bean resolver is available in the context and the bean is managed by the container. If the map is just static configuration, consider using configuration properties or typed Java configuration instead of complex expressions.

An inline map does not automatically convert into an arbitrary DTO just because keys match field names. If you need a typed object, use a constructor, factory, or binder appropriate for your application model.

## 14. Controlling types and values

An inline map can contain values of many different types. When retrieved with Map.class, values are typically handled as Object. Therefore, code consuming the map must check types before casting.

~~~java
Map<?, ?> result = expression.getValue(context, Map.class);

Object ageValue = result.get("age");

if (ageValue instanceof Number age) {
    int years = age.intValue();
}
~~~

Do not assume all values are Strings. A map can contain Booleans, Numbers, collections, nested maps, objects from the context, or null.

If the data contract requires fixed types, validate each key and value or convert to a DTO in Java. For input maps from external sources, check required keys, value types, size limits, and valid values.

## 15. Common errors and how to handle them

| Symptom | Common cause | Resolution |
|---|---|---|
| Parser reports syntax error | Missing colon, comma, or quotes | Check each key-value pair |
| Used a list when wanting a map | No key:value pairs | Add literal keys and colons |
| Dynamic key does not work | Inline keys require string literals | Create the map in Java if keys change |
| Variable not found | Variable not registered in context | Call setVariable with the exact name |
| Value property errors | Null root object or wrong property path | Check the object and use null-safe navigation when appropriate |
| Value has unexpected type | Map contains multiple Object types | Check the type before casting |
| Nested map hard to read | Structure too deep or unclear keys | Use meaningful key names or switch to a DTO |
| Modifying map affects later uses | Fixed literal map may be reused | Create a mutable copy in Java before modifying |
| Annotation fails to resolve bean | Context lacks bean resolver or wrong bean name | Check the integration point and ApplicationContext |

## 16. Practice exercises

1. Create an inline map containing name, age, and active.
2. Create a map whose values come from variables in StandardEvaluationContext.
3. Create a map whose values are arithmetic expressions and Boolean conditions.
4. Create a nested map containing customer and order, then read customer.name.
5. Create a map containing lists of roles and permissions.
6. Use a fixed inline map, then create a mutable copy in Java and modify a key.
7. Try passing a dynamic key and observe why the map should be built in Java.
8. Write tests for unregistered variables, null properties, null values, missing keys, and wrong value types.

## 17. Checklist before using inline maps

- [ ] Are curly braces and key:value pairs syntactically valid?
- [ ] Are keys string literals enclosed in single quotes?
- [ ] Are keys unique and easy to understand?
- [ ] Do values reference variables or properties that already exist in the context?
- [ ] Is null handled in values if data may be missing?
- [ ] Have you distinguished inline maps from inline lists?
- [ ] Is the nested structure shallow and clear enough?
- [ ] Are value types verified when Java consumes the map?
- [ ] Is a mutable copy needed before modifying the map?
- [ ] Is the data small enough to put inline, or should a Map be created in Java?
- [ ] Does EvaluationContext grant only the permissions needed for dynamic values?

## 18. Conclusion

Inline maps allow quickly creating key-value structures directly in SpEL. Keys are string literals, while values can be literals, variables, properties, calculations, conditions, or nested map/list structures. Use this syntax for small, stable data; pass dynamic data through EvaluationContext instead of string concatenation. Check value types, distinguish missing keys from null values, and create a copy in Java if a mutable map is needed. When structures become large or serve as critical data contracts, DTOs and Maps built in Java are usually easier to control.