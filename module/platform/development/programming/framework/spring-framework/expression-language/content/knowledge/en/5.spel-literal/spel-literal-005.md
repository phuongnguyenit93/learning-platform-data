# Array, List, and Map Literals

Spring Expression Language (SpEL) provides syntax for creating data structures directly in an expression. We can create inline lists, inline maps, and allocate Java arrays without writing a separate Java snippet for each value. These structures are useful when passing arguments to methods, building input data, accessing elements, or combining multiple values in one expression.

Three concepts need to be distinguished:

- **Java array:** has a defined element type and fixed size after creation.
- **Inline list:** SpEL syntax using curly braces to create a List object.
- **Inline map:** SpEL syntax using key-value pairs to create a Map object.

Curly braces in SpEL do not automatically mean a Java array initializer. **{1, 2, 3}** creates an inline list; to create a Java array, use allocation syntax such as **new int[3]**.

## 1. Inline Lists

### 1.1. Basic Syntax

An inline list is written with curly braces, with elements separated by commas:

~~~java
{1, 2, 3}
~~~

It can be parsed and evaluated directly:

~~~java
ExpressionParser parser = new SpelExpressionParser();

List<?> numbers = parser
        .parseExpression("{1, 2, 3}")
        .getValue(List.class);
~~~

The result is a List containing three numeric values. The exact type of the elements depends on the literals used in the expression and SpEL's type inference rules.

An inline list can contain different literal types:

~~~java
{'Spring', 'SpEL', 'Expression'}
{10, 20.5, 30}
{true, false, null}
~~~

Avoid mixing multiple types if the purpose of the list requires a uniform element type. If the list is assigned to a property with a specific type, conversion capability also depends on TypeConverter and the target type metadata.

### 1.2. Empty List

SpEL represents an empty list with a pair of curly braces without elements:

~~~java
{}
~~~

Example:

~~~java
List<?> empty = parser
        .parseExpression("{}")
        .getValue(List.class);
~~~

When reading expressions, distinguish **{}** from **{:}**. The first syntax is an empty inline list; the second syntax is an empty inline map.

### 1.3. Nested Lists

An element of a list can be another inline list:

~~~java
{{1, 2}, {3, 4}, {5, 6}}
~~~

This is a list consisting of three sublists. Elements can be accessed by index:

~~~java
parser.parseExpression("{{1, 2}, {3, 4}}[1][0]")
        .getValue(Integer.class);
~~~

The result is **3**: index **1** selects the second sublist, and index **0** selects the first element in that sublist.

List indices start at 0. Accessing a negative or out-of-bounds index can cause an error during expression evaluation.

### 1.4. Combining Literals and Dynamic Expressions

An inline list does not require every element to be a fixed literal. Elements can be properties, variables, arithmetic operations, or other SpEL expressions:

~~~java
List<?> values = parser
        .parseExpression("{1, order.total, order.quantity * 2}")
        .getValue(context, List.class);
~~~

In this example, **order.total** and **order.quantity * 2** are evaluated against the context. The values in the list therefore depend on the root object or variables present at evaluation time.

Lists can be nested with subexpressions:

~~~java
{
    order.id,
    order.customer.name,
    order.items[0].productCode
}
~~~

When an expression is long, break lines and keep a clear structure to easily identify which element causes an error.

### 1.5. Fixed Literal Lists and SpEL Optimization

For performance reasons, SpEL may create a constant list when all elements of an inline list are fixed literals. When the expression is evaluated multiple times, the parser may reuse the constant value instead of recreating the list each time.

This has a practical consequence: do not assume every call to **getValue()** will return a new list for the application to freely modify. Treat inline list results as input data of the expression and avoid modifying them. If business logic needs a mutable collection with its own lifecycle, create the collection in Java or through a controlled factory.

When a list contains properties or dynamic expressions, element values need to be evaluated against the current context; the assumption that the entire list is always a constant does not apply.

## 2. Inline Maps

### 2.1. Key-Value Syntax

An inline map uses curly braces, with each pair consisting of a key, a colon, and a value; pairs are separated by commas:

~~~java
{'name': 'An', 'active': true, 'level': 3}
~~~

The result can be retrieved as a Map:

~~~java
Map<?, ?> user = parser
        .parseExpression("{'name': 'An', 'active': true, 'level': 3}")
        .getValue(Map.class);
~~~

In the example, the keys are strings and the values include String, Boolean, and a number. This is a concise way to create a key-value structure to pass to a method or use in a subsequent expression.

### 2.2. Empty Map

An empty inline map uses special syntax:

~~~java
{:}
~~~

Example:

~~~java
Map<?, ?> emptyMap = parser
        .parseExpression("{:}")
        .getValue(Map.class);
~~~

Do not confuse this syntax with **{}**, which represents an empty list.

### 2.3. Accessing Elements by Key

Values can be retrieved from a map using an indexer:

~~~java
parser.parseExpression("{'name': 'An', 'age': 25}['name']")
        .getValue(String.class);
~~~

The result is the string **An**.

If the map is in the root object, access it similarly:

~~~java
settings['timeout']
settings['language']
~~~

For string keys, enclose the key in quotes when writing the expression. This clearly distinguishes the key name from a property or variable that SpEL needs to resolve.

### 2.4. Values Can Be Expressions

A map can combine static data with values retrieved from the context:

~~~java
{
    'customerId': customer.id,
    'customerName': customer.name,
    'total': order.total,
    'eligible': order.total >= 100
}
~~~

Each value is evaluated as a SpEL expression. Therefore, a map can act as an intermediate data object to pass into a method or produce a result for a business rule.

Keys are also part of the expression. In typical cases, use readable literal keys, especially String. Avoid creating complex keys if there is no clear need because it makes the expression harder to read and diagnose.

### 2.5. Nested Maps

Inline maps or inline lists can be placed inside values:

~~~java
{
    'customer': {
        'id': 1001,
        'name': 'An'
    },
    'permissions': {'READ', 'WRITE'},
    'preferences': {
        'language': 'vi',
        'notifications': true
    }
}
~~~

This structure is a map whose values include nested maps and lists. Access nested elements by combining indexers:

~~~java
{
    'customer': {'id': 1001, 'name': 'An'},
    'permissions': {'READ', 'WRITE'}
}['customer']['name']
~~~

The result is **An**.

For multi-level structures, split the expression into multiple parts or prepare the data in Java if access and transformation become complex.

### 2.6. Fixed Literal Maps

Similar to inline lists, SpEL may optimize an inline map where all keys and values are fixed literals by creating a constant map. Do not rely on the assumption that each evaluation will return a new map to mutate.

If a map needs to be modified per request, needs elements added, or holds long-lived state, manage that map in Java and pass it into the evaluation context. Inline maps are better suited for data structures created to serve a single expression evaluation.

## 3. Creating Java Arrays

### 3.1. Array Allocation Syntax

SpEL supports array construction using the **new** keyword, the element type name, and the array size:

~~~java
new int[3]
~~~

This expression creates an **int** array with three elements. Because this is a primitive array, the elements initially have a default value of **0**.

Reference arrays can be created:

~~~java
new java.lang.String[2]
~~~

The String array has two elements and each element is initially **null**.

Example of retrieving the result:

~~~java
int[] numbers = parser
        .parseExpression("new int[3]")
        .getValue(int[].class);
~~~

The result is a real Java array, not a List.

### 3.2. Default Values and Size

The default value depends on the element type:

| Element Type | Default Value |
|---|---|
| **int**, **long**, **short**, **byte** | **0** |
| **float**, **double** | **0.0** |
| **boolean** | **false** |
| **char** | Null character |
| Reference types such as String or domain objects | **null** |

The size is determined at allocation time. Java arrays do not automatically grow or shrink in element count like collections.

Invalid sizes, such as negative numbers, will cause an error during evaluation. Applications should also limit sizes if expressions come from untrusted sources to avoid allocating overly large arrays.

### 3.3. Multidimensional Arrays

SpEL supports allocating multidimensional arrays:

~~~java
new int[2][3]
~~~

The expression creates a two-dimensional array consisting of two rows, each with three elements. After the array is assigned to a property of the root object, an element can be accessed with two indices:

~~~java
matrix[1][2]
~~~

Index **1** selects the second row, and index **2** selects the third element of that row.

A three-dimensional array can be created with three dimensions:

~~~java
new int[2][3][4]
~~~

For readability, assign the array to a property of the root object and then access it by dimension. All array indices start at 0.

### 3.4. Arrays Are Not Like Inline Lists

The following two expressions produce two different result types:

~~~java
{1, 2, 3}
new int[3]
~~~

- **{1, 2, 3}** is an inline list, with a collection type.
- **new int[3]** is a Java array of type **int[]**, containing three initial **0** values.

Do not use the curly braces of an inline list as if they were a Java array initializer. If an array already populated with specific data is needed, prepare the array in Java and place it into the root object or a context variable. Then SpEL accesses the elements like an ordinary array.

## 4. Accessing and Updating Elements

### 4.1. Accessing by Index

SpEL uses an indexer to access elements of an array or list:

~~~java
numbers[0]
items[1]
matrix[0][2]
~~~

Indices start at 0. When an index is out of range, evaluation may fail. If the index is computed from a property or variable, check input data to avoid runtime errors.

Example with a root object:

~~~java
Expression expression =
        parser.parseExpression("quantities[1]");

Integer secondQuantity =
        expression.getValue(context, Integer.class);
~~~

The result depends on whether the **quantities** property is an array or a list and the value at the second position.

### 4.2. Accessing a Map by Key

For a map, the indexer takes a key:

~~~java
settings['timeout']
settings['language']
~~~

If the key does not exist, the result may be **null** depending on the map type and accessor. If the expression continues accessing properties of a null value, an evaluation error may occur. Check the key or use an appropriate conditional expression before deep access.

### 4.3. Updating Elements with setValue

When an expression points to a writable location in the root object, **setValue** can be used to update the element:

~~~java
Expression expression =
        parser.parseExpression("quantities[1]");

expression.setValue(context, 25);
~~~

Similarly, a list element or a value in a map can be updated:

~~~java
parser.parseExpression("items[0]").setValue(context, newItem);

parser.parseExpression("settings['timeout']")
        .setValue(context, 30);
~~~

These examples assume the root object provides the corresponding properties and the collection/array is mutable. Writing still depends on the accessibility of the property accessor, element type, and configured TypeConverter.

Not all inline results are suitable for updating. If an inline list or map is optimized into a constant, do not rely on it being mutable. For data that needs to be updated, use a collection or array managed by the application and placed in the context.

## 5. Combining Lists, Maps, and Arrays in One Expression

An expression can nest multiple structures to describe complex data:

~~~java
{
    'code': order.id,
    'lines': {
        {
            'product': order.items[0].productCode,
            'quantity': order.items[0].quantity
        },
        {
            'product': order.items[1].productCode,
            'quantity': order.items[1].quantity
        }
    },
    'tags': {'priority', 'online'},
    'valid': order.total > 0
}
~~~

This is an outer map in which **lines** is a list of submaps, **tags** is a list, and **valid** is a Boolean expression. Such a structure can be useful when creating an argument for a method that accepts Map data.

However, do not turn SpEL into an overly large object-building language. If an expression contains many levels of nesting, many conditions, or repeats the same access, consider moving the data creation part to Java. SpEL is suitable for short, clear expressions with a controlled scope of permissions.

## 6. Type Conversion Between Lists, Maps, and Arrays

Inline lists and inline maps are collections; arrays are a separate Java data type. Converting from one type to another depends on the context's TypeConverter and ConversionService or how the application retrieves the result.

For example, if an int array is needed from list data, do not assume every SpEL configuration will automatically convert it:

~~~java
Object value = parser
        .parseExpression("{1, 2, 3}")
        .getValue(context);
~~~

The desired result type can be requested:

~~~java
int[] values = parser
        .parseExpression("{1, 2, 3}")
        .getValue(context, int[].class);
~~~

Conversion only succeeds when TypeConverter supports the corresponding source and target types. If special conversion rules are needed, register an appropriate converter on ConversionService and configure StandardTypeConverter for the context.

For generic collections, element type metadata also matters. For example, **List<String>** and **List<Integer>** share the same raw type List but require different element conversions. If converting data for a generic property, ensure TypeDescriptor and the converter have sufficient information about the target type.

For maps, both key type and value type need to be controlled. A map with String keys cannot automatically be used as a map with CustomerId keys without a corresponding conversion rule.

## 7. Complete Example with a Root Object

The following example uses a bean containing an array, a list, and a map to illustrate how SpEL reads data structures:

~~~java
import java.util.List;
import java.util.Map;

public class ReportData {

    private final int[] scores = {80, 90, 95};
    private final List<String> names =
            List.of("An", "Binh", "Chi");
    private final Map<String, Object> settings =
            Map.of("language", "vi", "enabled", true);

    public int[] getScores() {
        return scores;
    }

    public List<String> getNames() {
        return names;
    }

    public Map<String, Object> getSettings() {
        return settings;
    }
}
~~~

Create a context and evaluate the expressions:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext(new ReportData());

Integer firstScore = parser
        .parseExpression("scores[0]")
        .getValue(context, Integer.class);

String secondName = parser
        .parseExpression("names[1]")
        .getValue(context, String.class);

String language = parser
        .parseExpression("settings['language']")
        .getValue(context, String.class);

Boolean enabled = parser
        .parseExpression("settings['enabled']")
        .getValue(context, Boolean.class);
~~~

The results are **80**, **Binh**, **vi**, and **true**, respectively.

A new data structure can be created based on the root object:

~~~java
Map<?, ?> summary = parser
        .parseExpression(
                "{'firstScore': scores[0], " +
                "'secondName': names[1], " +
                "'language': settings['language']}"
        )
        .getValue(context, Map.class);
~~~

Here the map is created from runtime values of the root object. If evaluated with a different root object, the values may change according to the corresponding data.

## 8. Common Mistakes

| Symptom | Possible Cause | How to Handle |
|---|---|---|
| Using **{}** while expecting a Map | **{}** is an empty inline list | Use **{:}** to create an empty map |
| Using **{1,2,3}** when an array is needed | This syntax creates a List | Use array construction or pass an array from Java |
| Accessing an element out of bounds | Negative index or greater than limit | Check size before evaluation |
| Cannot retrieve map value | Wrong or non-existent key | Check exact key and key type |
| Converting list to array fails | TypeConverter does not support conversion | Configure ConversionService or convert in Java |
| Updating element fails | Collection is not mutable or property is not writable | Check write permissions and collection lifecycle |
| Nested expression is hard to parse | Missing braces, commas, or colons | Check each structure pair and split the expression to test |

When debugging, parse each small structure first. For example, test the inline list separately, then test the map, and only then nest them together. This helps determine whether the error is in syntax, result type, or runtime data.

## 9. Performance and Safety

### 9.1. Do Not Create Overly Large Structures in Expressions

Inline lists/maps can keep expressions concise, but creating large collections directly in an expression makes the string hard to read and resource usage hard to control. For large data, prepare it in Java and pass it into the context.

Array size should also be limited. An expression may be syntactically valid yet request allocating an overly large array during evaluation.

### 9.2. Do Not Mutate Constant Collections

For inline lists/maps consisting of fixed literals, SpEL may create a constant collection for optimization. Do not modify these collections or rely on the assumption that each evaluation yields a new instance.

If elements need to be added/removed, use a mutable collection owned by the application. Do not use expressions as a place to store state between evaluations.

### 9.3. Controlling User-Provided Expressions

If users can enter SpEL, limit expression size and complexity, allowed referenced types, and operations provided by EvaluationContext. Do not allow expressions to arbitrarily allocate large arrays or access sensitive objects simply because the syntax parses validly.

Remember that inline lists/maps are expression data structures, not a security boundary. Actual access permissions still depend on the root object, property accessor, method resolver, type locator, and other services in the context.

## 10. Choosing the Right Data Structure

| Need | Structure to Use | SpEL Syntax |
|---|---|---|
| List of elements accessible by index | List | **{1, 2, 3}** |
| Nested lists | List of lists | **{{1, 2}, {3, 4}}** |
| Key-value data | Map | **{'name': 'An', 'active': true}** |
| Empty map | Map | **{:}** |
| Empty list | List | **{}** |
| Memory region with fixed element type and size | Java array | **new int[3]** |
| Multidimensional array | Java multidimensional array | **new int[2][3]** |
| Collection needing long-term modification | Collection managed by Java | Pass via root object/context |

## 11. Summary

SpEL supports three data structures for different purposes:

- **Inline list** uses **{...}** to create a List; **{}** is an empty list.
- **Inline map** uses **key: value** pairs; **{:}** is an empty map.
- **Array construction** uses **new Type[size]** to create a Java array with a defined element type and size.

Use lists and maps to represent concise data directly in expressions; use arrays when a Java array type is needed; and use application-managed collections when updating or retaining state is required. When converting types between structures, check TypeConverter and ConversionService instead of assuming SpEL converts every case automatically.