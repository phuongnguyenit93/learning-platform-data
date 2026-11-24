# Choosing Indexer or Property Based on Data Model

In Spring Expression Language (SpEL), there are two common ways to navigate into data: **property access** using a dot and **indexer** using square brackets. Both can appear in the same expression, yet they describe two different ways of organizing data.

- Use **property** when reading a named property of an object, such as customer, address, or status.
- Use **indexer** when retrieving an element by position, key, or index, such as the first element of a List, a key in a Map, or a character in a String.

The right decision depends on the data model and the meaning of the operation. A stable property name of a domain object should be expressed as a property; a dataset looked up by key or position should be accessed with an indexer.

## 1. The Two Access Mechanisms and Their Meanings

### 1.1. Property Access — Accessing Named Properties

Property access uses a dot:

~~~text
#order.customer.address.city
~~~

The expression starts from the order variable, then reads the customer, address, and city properties. Each property is a named part of the object model.

JavaBean example:

~~~java
public class Order {
    private Customer customer;

    public Customer getCustomer() {
        return customer;
    }
}

public class Customer {
    private String status;

    public String getStatus() {
        return status;
    }
}
~~~

The following expressions read the corresponding properties:

~~~text
#order.customer
#order.customer.status
~~~

SpEL resolves properties through the PropertyAccessors in the EvaluationContext. For a typical JavaBean, properties are usually read via getters. Properties can also come from a custom accessor if the application registers one.

Property access fits when the field name is meaningful in the domain model and determined by the object type. When a class renames a property or changes its return type, expressions using that property also need to be updated.

### 1.2. Indexer — Accessing Elements by Key or Position

An indexer uses square brackets:

~~~text
#items[0]
#settings['region']
~~~

The meaning of the content inside the brackets depends on the data type:

- For a List or array, the index is the element position, normally starting from 0.
- For a Map, the expression inside the brackets is the key used to look up the value.
- For a String, the index can retrieve the character at the corresponding position.
- For an object with a suitable IndexAccessor, the indexer can access data according to that accessor's convention.

Example:

~~~java
context.setVariable("items", List.of("A", "B", "C"));
context.setVariable("settings", Map.of("region", "ap-southeast-1"));
~~~

The expressions:

~~~text
#items[0]
#settings['region']
~~~

return the first element of the list and the value corresponding to the key region in the map, respectively.

## 2. Choosing by Data Structure

| Data Model | Common Access Style | Example |
| --- | --- | --- |
| JavaBean or domain object | Property | **#order.customer.name** |
| Java record | Property by component | **#customer.address.city** |
| Map | Indexer by key | **#attributes['priority']** |
| List | Indexer by position | **#orders[0]** |
| Array | Indexer by position | **#scores[2]** |
| String | Indexer by character position | **#code[0]** |
| Object with IndexAccessor | Indexer per accessor contract | **#document['title']** |

This table is a guiding rule. If the application registers custom PropertyAccessors or IndexAccessors, access capabilities can be extended. Check the EvaluationContext configuration and accessors in use before assuming a syntax always works for every object type.

## 3. When Should You Use a Property?

Use a property when the data is a named part with a stable meaning in the object.

Example:

~~~java
class Invoice {
    private Customer customer;
    private BigDecimal total;
    private String status;

    public Customer getCustomer() {
        return customer;
    }

    public BigDecimal getTotal() {
        return total;
    }

    public String getStatus() {
        return status;
    }
}
~~~

Expressions:

~~~text
#invoice.customer.name
#invoice.total
#invoice.status
~~~

This notation directly reflects the domain model: an invoice has customer, total, and status. Readers do not need to know the field order or internal storage position inside the object.

Properties are suitable in the following cases:

1. **Well-structured domain objects:** customer, account, shippingAddress, status.
2. **JavaBeans or records:** attributes defined by getters or record components.
3. **Business expressions:** checking status, ownership, or a value belonging to an object.
4. **Named configuration:** reading a property from a bean or configuration object.
5. **Stable nested paths:** for example order.customer.address.city.

Do not use an indexer simply because a property happens to be stored at a fixed position in an internal structure. If the data carries a name and meaning in the domain, property access makes the intent clearer.

## 4. When Should You Use an Indexer?

Use an indexer when data is organized as a collection that can be looked up by key or position.

### 4.1. Map — Key-Based Lookup

A Map fits when entries are identified by keys rather than fixed property names of a class:

~~~java
Map<String, Object> attributes = new HashMap<>();
attributes.put("priority", "HIGH");
attributes.put("source", "WEB");

context.setVariable("attributes", attributes);
~~~

Accessing with an indexer:

~~~text
#attributes['priority']
#attributes['source']
~~~

The key can be a dynamic expression:

~~~text
#attributes[#attributeName]
~~~

If attributeName has the value priority, the expression is equivalent to retrieving the key priority.

Use a Map indexer when:

- Keys come from configuration or runtime data.
- The set of keys is not fixed at compile time.
- The data is metadata or extended attributes.
- You need to access a key with special characters or one that is not a standard identifier name.

Do not assume that keys in a Map can always be accessed with dot notation. The clear and standard syntax for a Map is an indexer with the key placed inside square brackets.

### 4.2. List — Positional Access

A List fits when element order is meaningful:

~~~java
context.setVariable("steps", List.of("validate", "approve", "publish"));
~~~

Expressions:

~~~text
#steps[0]
#steps[1]
#steps[2]
~~~

Indices start at 0. The first element is at position 0, the second element is at position 1.

Use a List indexer when you need to retrieve an element by a defined position or by an index computed in the expression:

~~~text
#steps[#currentIndex]
~~~

If you need to find an element by a business attribute instead of position, consider the selection operator or handling it in a Java service. A fixed index easily becomes wrong when data order changes.

### 4.3. Array — Element Access by Index

Arrays also use indexers:

~~~java
int[] scores = {70, 85, 92};
context.setVariable("scores", scores);
~~~

Expressions:

~~~text
#scores[0]
#scores[2]
~~~

Use an array when the data is actually provided as an array or an API requires that type. There is no need to convert an array into an object property just to access an element.

### 4.4. String — Getting a Character by Position

SpEL supports indexers on Strings to access characters:

~~~java
context.setVariable("code", "AB12");
~~~

Expressions:

~~~text
#code[0]
#code[1]
~~~

This indexer suits operations based on character position, such as reading the first character of a code. If you need to handle Unicode supplementary characters or user-perceived character rules, consider the difference between Java char, code point, and grapheme cluster; a character index does not necessarily correspond to a single display character.

## 5. Combining Properties and Indexers in the Same Path

In real-world data, objects often contain collections or Maps. In that case, a property path may alternate between dots and square brackets.

Examples:

~~~text
#order.customer.address.city
#order.lines[0].product.name
#order.attributes['priority']
~~~

How to read them:

- order is a variable.
- customer, address, and city are nested properties.
- lines is a property returning a collection; [0] retrieves the first element.
- product and name continue as properties of the retrieved element.
- attributes is a property returning a Map; ['priority'] retrieves the value by key.

Another data structure:

~~~text
#response.data['orders'][0].customer.address.city
~~~

SpEL sequentially reads the data property, gets the orders key in the Map, gets the first element of the List, and then accesses customer, address, and city.

When reading a long expression, identify the data type after each step. A dot means accessing a property of the current object; square brackets mean accessing an element via an indexer on the current value.

## 6. Cases Where Map Keys and Object Properties Are Easily Confused

Consider two models:

~~~java
class Customer {
    private String name;

    public String getName() {
        return name;
    }
}

Map<String, Object> attributes = new HashMap<>();
attributes.put("name", "Linh");
~~~

With Customer, name is a named property:

~~~text
#customer.name
~~~

With Map, name is a key:

~~~text
#attributes['name']
~~~

Both expressions can return the string Linh, but they rely on two different mechanisms:

- Property access requires an accessor to resolve the property name on the object.
- Map indexer looks up the value corresponding to the key in the Map.

Using an indexer for a Map makes it clear that data is being looked up by key. This is especially important when the key is generated dynamically:

~~~text
#attributes[#requestedField]
~~~

If requestedField changes per request, the expression still accesses the corresponding key without having to define a JavaBean property for every key.

Conversely, if an object has a stable domain attribute, do not turn it into a Map just to access it by a key string. Explicitly typed, named data helps the compiler, IDE, and readers understand the structure.

## 7. Indexers on Custom Objects

By default, indexers are commonly used with structured data types supported by SpEL such as Map, List, array, and String. For custom data types, an application can provide an IndexAccessor to define how to read or write using square-bracket syntax.

Starting from Spring Framework 6.2, SpEL provides the IndexAccessor API for this purpose. For example, an application can define a Document type that supports accessing fields by key:

~~~text
document['title']
document['metadata']
~~~

The specific access behavior depends on the IndexAccessor registered in the EvaluationContext. Do not assume that an arbitrary object can use an indexer just because it has a get(int) or get(String) method. A corresponding accessor is required, or the type must belong to the group directly supported by SpEL.

Similarly, PropertyAccessor allows extending how SpEL resolves named properties. These two SPIs address two different access models:

| SPI | Expression Syntax | Purpose |
| --- | --- | --- |
| PropertyAccessor | **object.property** | Reads/writes a named property |
| IndexAccessor | **object[index]** | Reads/writes an element by key or index |

When building a custom accessor, clearly specify supported target types, valid index types, behavior when a key does not exist, read/write permissions, and null handling. An accessor must reflect the application's data contract and should not create ambiguous syntax between properties and keys.

## 8. Nulls, Missing Keys, and Out-of-Bounds Indices

### 8.1. Intermediate Objects Can Be Null

A property path or indexer can fail if the receiving object is null:

~~~text
#order.customer.address.city
#order.lines[0]
#settings['region']
~~~

If order is null, customer cannot be read. If lines is null, the first element cannot be retrieved. If settings is null, the region key cannot be looked up.

With property access, use the safe-navigation operator at points that can be null:

~~~text
#order?.customer?.address?.city
~~~

With indexers, Spring Framework 6.2 adds safe-navigation for indexing using the **?.[]** syntax:

~~~text
#order?.lines?.[0]
#settings?.['region']
~~~

Null-safe indexing syntax depends on the framework version. If a project uses an older version, check actual support and handle nulls with conditions or Java helpers before indexing.

### 8.2. Missing Key in a Map

When a key is not present in a Map, the lookup result is normally null:

~~~text
#settings['missingKey']
~~~

You can combine with Elvis to provide a default value:

~~~text
#settings['region'] ?: 'ap-southeast-1'
~~~

This is appropriate when the key is optional. If the key is required, validate the data and report a clear error rather than silently substituting a default value.

### 8.3. Out-of-Bounds Index

For a List or array, the index must be within valid bounds:

~~~text
#items[0]
#items[10]
~~~

If the collection has no element at the requested position, evaluation can throw an exception. An indexer does not automatically convert an invalid index into null.

Before using a dynamic index, ensure the index is valid or check the size using Java logic. For example, if you need the first element when a list is non-empty, you can create a helper that returns null when the list is empty and combine it with Elvis.

### 8.4. Distinguishing Null-Safe and Bounds-Safe

Safe navigation protects the case where the receiving object is null. It does not mean the index is always valid.

Example:

~~~text
#items?.[0]
~~~

This expression handles a null items according to the null-safe indexing mechanism of supported versions. However, if items is an empty List, index 0 is still out of bounds and can cause an error.

Null safety and bounds checking are two separate conditions.

## 9. Using Property or Indexer at Spring Integration Points?

SpEL appears in many annotations and modules. The EvaluationContext provided by each integration point determines the available root object, variables, and bean references. How you choose property or indexer still depends on the type of data being accessed.

### 9.1. Cache Key

If the parameter is a domain object with an ID property:

~~~java
@Cacheable(cacheNames = "orders", key = "#order.customer.id")
public OrderSummary summarize(Order order) {
    // ...
}
~~~

If the parameter contains a metadata Map:

~~~java
@Cacheable(cacheNames = "reports", key = "#request.attributes['reportType']")
public Report generate(ReportRequest request) {
    // ...
}
~~~

The first example accesses nested properties. The second example reads a dynamic key in the attributes Map. Do not choose an indexer just to avoid defining a property on a domain object.

### 9.2. Method Security

You can check an object property:

~~~java
@PreAuthorize("#document.owner.id == authentication.principal.id")
public Document read(Document document) {
    // ...
}
~~~

If authorization is determined by metadata in a Map:

~~~java
@PreAuthorize("#document.attributes['visibility'] == 'PUBLIC'")
public Document read(Document document) {
    // ...
}
~~~

The expression must match the actual structure of Document. If owner is an object with an explicit type, use property access. If visibility is a key in a metadata Map, use an indexer.

With untrusted data, do not allow users to freely submit expressions that can read every property or call every method. Restrict the EvaluationContext and accessors to the exact scope required by the feature.

## 10. Selection and Projection When Filtering Collections

An indexer retrieves an element by a specific position. If the goal is to filter or transform an entire collection based on properties of each element, SpEL has selection and projection operators.

Example retrieving all orders with a total of 1000 or more:

~~~text
#orders.?[total >= 1000]
~~~

Retrieving a list of customer names from a collection of orders:

~~~text
#orders.![customer.name]
~~~

These two operations differ from an indexer:

- **#orders[0]** retrieves one element by position.
- **#orders.?[condition]** filters elements matching a condition.
- **#orders.![expression]** creates a result collection from an expression evaluated on each element.

If you need the first element matching a condition, use first-selection:

~~~text
#orders.^[total >= 1000]
~~~

If you need the last element matching a condition:

~~~text
#orders.$[total >= 1000]
~~~

Choose the syntax according to intent: retrieving by position uses an indexer; finding by condition uses selection; transforming each element uses projection.

## 11. Quick Decision Criteria

When writing a new expression, ask yourself:

1. **Is the data an object with named properties?** Use property access, e.g. customer.address.city.
2. **Is the data a Map looked up by key?** Use an indexer, e.g. attributes['priority'].
3. **Is the data a List or array where position is meaningful?** Use an indexer, e.g. items[0].
4. **Is the key or index determined at runtime?** Use an indexer with an expression as the key/index, e.g. attributes[#fieldName].
5. **Do you need to find an element by condition rather than position?** Use the selection operator or a Java service.
6. **Can the object be null?** Use safe navigation at each step that can be null; check out-of-bounds indices separately.
7. **Is the object a custom type?** Check whether a PropertyAccessor or IndexAccessor has been registered.

A practical principle: use properties to describe named structure on an object; use indexers to describe lookup operations in keyed or positional structures. Do not pick a syntax solely because it is shorter if the data semantics do not match.

## 12. Testing Expressions with Different Structures

You can use a parser and EvaluationContext to test both access styles:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("customer", customer);
context.setVariable("attributes", Map.of("priority", "HIGH"));
context.setVariable("items", List.of("A", "B"));

String customerName = parser
        .parseExpression("#customer.name")
        .getValue(context, String.class);

String priority = parser
        .parseExpression("#attributes['priority']")
        .getValue(context, String.class);

String firstItem = parser
        .parseExpression("#items[0]")
        .getValue(context, String.class);
~~~

The expressions above verify:

- the name property is resolved on the customer object;
- the Map indexer retrieves the value by the priority key;
- the List indexer retrieves the element at position 0.

In real tests, also include missing keys, out-of-bounds indices, null intermediate objects, and the behavior of custom accessors if the application uses them. With annotations like @Cacheable or @PreAuthorize, test at the actual integration point to verify that the context supplies data as expected.

## 13. Common Errors

1. **Using dot notation for a Map key without a supporting accessor:** use indexer syntax with the key in square brackets.
2. **Using a fixed index for data whose order can change:** if you need to look up by ID or condition, look up by key or use selection.
3. **Confusing an indexer with a property:** items[0] is element access; items.size() is a method call on the object.
4. **Forgetting 0-based indexing:** the first element of a List/array is at index 0.
5. **Not checking out-of-bounds indices:** safe navigation does not guarantee a valid index.
6. **Assuming custom objects always support indexers:** an IndexAccessor or built-in support is required.
7. **Not handling nulls at intermediate steps:** place safe navigation at the right spots and define fallbacks clearly.
8. **Using dynamic data structures for fixed domain fields:** clearly named properties are usually easier to maintain than Map keys.
9. **Allowing overly broad expression access:** restrict accessors and the EvaluationContext if expressions come from untrusted sources.

## 14. Quick Reference

- Dot **.** accesses a named property on an object.
- Square brackets **[]** access a Map key, List/array index, String index, or data provided by an IndexAccessor.
- JavaBeans and records generally suit property access.
- Maps suit indexers because data is looked up by key, including dynamic keys.
- Lists and arrays use positional indexers, starting from 0.
- An expression can alternate between properties and indexers, such as order.lines[0].product.name.
- Use **?.** for null-safe property access; Spring Framework 6.2 supports null-safe indexing with **?.[]**.
- Null-safe does not mean bounds-safe; out-of-bounds indices can still error.
- Use selection to find elements by condition and projection to transform collections.
- PropertyAccessor and IndexAccessor allow extending access behavior, but must be configured in the EvaluationContext.
- Choose syntax according to the data model and business semantics, not merely expression brevity.

## 15. Official References

- [Spring Expression Language Reference](https://docs.spring.io/spring-framework/reference/core/expressions.html)
- [Spring Framework — Properties, Arrays, Lists, Maps and Indexers](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/properties-arrays.html)
- [Spring Framework — Safe Navigation Operator](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-safe-navigation.html)
- [Spring Framework — EvaluationContext and Property Accessors](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework — IndexAccessor API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/IndexAccessor.html)
