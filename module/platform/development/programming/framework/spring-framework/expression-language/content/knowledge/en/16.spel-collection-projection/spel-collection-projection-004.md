# Projection on nested properties in SpEL

Projection in Spring Expression Language (SpEL) allows applying an expression to each element of a collection and gathering the results into a new collection. When the target property lies deep in an object graph, projection can traverse multiple levels such as customer.address.city or product.category.name.

To use projection on nested properties properly, you need to understand the current object in each iteration, how properties are resolved, how to handle null at each level, and the shape of the result when projections are nested. This lesson focuses on practical cases when turning a collection of objects into a list of values or a simpler data structure.

## 1. Objectives and prerequisites

After this lesson, you can:

- Use the projection operator .![] to retrieve a property from each element.
- Access nested properties inside a projection expression.
- Understand the role of #this and distinguish it from #root.
- Handle intermediate objects or properties that may be null.
- Write nested projections and recognize list-of-lists results.
- Combine selection and projection to filter and then transform data.
- Build a small map per element when multiple output fields are needed.
- Evaluate projections in Java and test edge cases.

You should know collections, JavaBean getters, property paths, SpEL variables, and how to use SpelExpressionParser with EvaluationContext.

## 2. What is projection?

Projection is the operation of transforming each element of a collection with an expression. General syntax:

~~~text
collection.![expression]
~~~

SpEL iterates through the collection, evaluates the expression on each element, and creates the resulting collection. For an input List, a normal projection result is a new List with one corresponding result for each input element.

For example, suppose you have a list of Products and each product has a name property:

~~~text
#products.![name]
~~~

The expression returns a list of product names. Instead of receiving full Product objects, the result contains only the name values.

Projection differs from selection:

| Operation | Syntax | Result |
|---|---|---|
| Selection | .?[condition] | Original elements matching the condition |
| Projection | .![expression] | Result of the expression on each element |

Selection filters elements; projection transforms elements. Both operations can be combined to transform only matching elements.

## 3. Nested properties in projection

Suppose the data model has the following structure:

~~~java
class Order {
    private Customer customer;
    private BigDecimal total;

    public Customer getCustomer() {
        return customer;
    }

    public BigDecimal getTotal() {
        return total;
    }
}

class Customer {
    private Address address;

    public Address getAddress() {
        return address;
    }
}

class Address {
    private String city;

    public String getCity() {
        return city;
    }
}
~~~

Each Order has a customer; each Customer has an address; Address has a city. If you want to get the city of all orders, you can write:

~~~text
#orders.![customer.address.city]
~~~

In each projection iteration, SpEL gets the current Order's customer, then gets address, and then reads city. The result is a list of cities in the order of the elements in the source collection.

Example input:

| Order | Customer | Address city |
|---|---|---|
| O-100 | An | Hanoi |
| O-101 | Binh | Da Nang |
| O-102 | Chi | Can Tho |

Projection returns:

~~~text
{'Hanoi', 'Da Nang', 'Can Tho'}
~~~

The syntax above illustrates the resulting collection; the concrete runtime type depends on the collection and values produced by the projection.

### 3.1. No need to repeat the collection name inside the expression

In the projection:

~~~text
#orders.![customer.address.city]
~~~

SpEL automatically sets the element being processed as the current object. You do not need to write #orders.customer.address.city again, because #orders is a collection rather than an individual Order.

Unprefixed property names are resolved against the current element. If you want to reference it explicitly, you can use #this:

~~~text
#orders.![#this.customer.address.city]
~~~

Both ways have the same meaning in this example. Using the property name directly is usually more concise; #this is helpful when the expression is complex or has multiple nested contexts.

## 4. Understanding #this and #root in projection

SpEL provides two important references:

- #this: the current object at the point currently being evaluated.
- #root: the root object of the EvaluationContext.

When projection runs on a collection, #this is normally the current element. In nested projections, the current object changes with each iteration level.

Example:

~~~text
#orders.![#this.customer.address.city]
~~~

In the outer projection, #this is an Order. When reading customer.address.city, properties are resolved from that Order.

If the root object is a different object and needs to be accessed again inside the expression, #root still represents the initial root object. Do not confuse #root with the current element of the collection.

Use #this to state intent clearly when the expression has multiple collection levels or when a property name might be confused with a property of the root object.

## 5. Null in nested property paths

Nested properties may lack data. For example, an Order exists but customer is null, or customer exists but address is null. Regular access:

~~~text
#orders.![customer.address.city]
~~~

can raise an error when an intermediate link is null.

Use null-safe navigation at each level that may be null:

~~~text
#orders.![customer?.address?.city]
~~~

If the Order element itself can be null, protect the current element as well:

~~~text
#orders.![#this?.customer?.address?.city]
~~~

Each ?. protects the receiver immediately before it. If customer is null, the expression returns null for that branch; if address is null, reading city returns null. The projection result still has a slot corresponding to the source element, and the value at that slot may be null.

### 5.1. Null on the source collection is a separate case

Null-safe navigation inside the expression does not automatically protect the source collection. If orders is null, the expression #orders.![...] still cannot start projection.

You can check the collection beforehand:

~~~text
#orders != null ? #orders.![customer?.address?.city] : null
~~~

This returns null when the source collection is null. If business rules expect an empty collection instead of null, choose an intentional default value and ensure a compatible result type.

Spring Framework 6.2 and later support null-safe projection directly on the collection with the syntax:

~~~text
#orders?.![customer?.address?.city]
~~~

This syntax protects the collection receiver. The ?. operators inside the projection are still necessary to protect customer and address if they can be null. On older Spring versions, use an explicit guard before projection.

### 5.2. Null vs. a non-existent property

Null-safe navigation handles a receiver whose value is null. It does not fix misspelled property names or create properties that do not exist. If the model lacks a getter/accessor for city, the expression can still fail. Distinguish null data from object structure errors or access errors.

## 6. Nested projection

An element can contain a child collection. For example, each Order has a List of LineItem, and each LineItem has a sku.

You can retrieve the list of SKUs for each order using nested projection:

~~~text
#orders.![items.![sku]]
~~~

The outer projection runs on each Order. The inner projection runs on the current Order's items. The result is a nested collection:

~~~text
[
  ['SKU-A', 'SKU-B'],
  ['SKU-C'],
  ['SKU-D', 'SKU-E', 'SKU-F']
]
~~~

This is a list-of-lists: each sublist corresponds to one order. Projection does not automatically flatten child collections into a single list.

If null levels need protection:

~~~text
#orders.![items?.![sku]]
~~~

On Spring Framework 6.2 and later, ?. before the inner projection protects against null items. If a LineItem can be null or sku lies on a deeper property path, continue using #this?.property or safe navigation at the required links.

### 6.1. When results need to be flattened

If the goal is a flat list of SKUs, perform flattening in Java after projection, or use Java Stream to map and then flatMap. Do not assume .![] will merge child collections automatically.

Java example:

~~~java
List<String> allSkus = orders.stream()
    .filter(Objects::nonNull)
    .filter(order -> order.getItems() != null)
    .flatMap(order -> order.getItems().stream())
    .filter(Objects::nonNull)
    .map(LineItem::getSku)
    .toList();
~~~

Java expresses null handling and flattening clearly. If the logic requires multiple transformation, filtering, and error-handling steps, a Stream or Java loop is usually easier to read than a deeply nested SpEL expression.

## 7. Combining selection and projection

A common use case is filtering a collection first and then extracting nested properties.

For example, getting only the city of paid orders:

~~~text
#orders.?[status == 'PAID'].![customer?.address?.city]
~~~

The first operation:

~~~text
#orders.?[status == 'PAID']
~~~

retains Orders whose status is PAID.

The second operation:

~~~text
.![customer?.address?.city]
~~~

retrieves the customer's city for each filtered order.

You can filter by nested properties:

~~~text
#orders.?[customer != null and customer.active].![customer.address.city]
~~~

In the predicate, #this is the current Order. The condition customer != null is placed before customer.active so that AND short-circuiting protects the property access.

If address can also be null, write the projection with safe navigation:

~~~text
#orders.?[customer != null and customer.active].![customer?.address?.city]
~~~

Selection preserves the original objects; projection produces new values from those objects.

## 8. Building output structures with a map inside projection

Projection is not required to return only a single property. The expression inside .![] can be a complex expression, including an inline map.

For example, suppose you want to build a summary for each Order:

~~~text
#orders.![{
    'orderNumber': number,
    'city': customer?.address?.city,
    'total': total
}]
~~~

Each result element is a map with three keys. The output structure looks like:

~~~text
[
  {'orderNumber': 'O-100', 'city': 'Hanoi', 'total': 120},
  {'orderNumber': 'O-101', 'city': null, 'total': 80}
]
~~~

This approach is useful when creating compact presentation data or passing results to a downstream processing step. Keys in the inline map are string literals; values are evaluated on the current Order.

If the result structure is stable and used widely in the application, consider creating a typed DTO in Java instead of passing Map<String, Object>.

## 9. Evaluating projection in Java

Example creating a parser and passing a collection into the context:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression(
        "#orders.![customer?.address?.city]"
    );

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("orders", orders);

List<?> cities =
    expression.getValue(context, List.class);
~~~

The orders variable can hold Order objects. Projection reads the property on each element and returns a collection of cities.

If you want to retrieve a deeper property, just change the expression:

~~~java
#orders.![customer?.address?.city]
~~~

If you want a summary map:

~~~java
#orders.![{'number': number, 'city': customer?.address?.city}]
~~~

Passing data through variables keeps the expression independent of how the application constructs the collection. There is no need to concatenate objects or runtime values into the expression string.

## 10. Does projection modify the source collection?

Projection builds a result collection from values computed on the source elements. The projection operation itself does not mean updating properties of the source elements.

Example:

~~~text
#products.![price * 1.1]
~~~

The expression computes a new price for each element and returns a list of results. It does not automatically invoke setters to update price on Product.

If the expression inside projection calls a method with side effects or uses an assignment operator, that behavior can mutate objects. Therefore, do not put write operations or side-effecting methods into read-only projections. Keep expressions pure so results remain predictable.

## 11. Data types and projection results

The result of a projection depends on the inner expression:

| Expression | Value of each result element |
|---|---|
| .![name] | Value of name |
| .![total > 100] | Boolean |
| .![price * quantity] | Result of the calculation |
| .![customer?.address?.city] | City or null |
| .![{'id': id, 'name': name}] | Map for each element |
| .![items.![sku]] | Child collection for each element |

When using getValue(context, List.class), elements in the List can still have different types if the expression returns multiple value types. Check types before casting and define the result's data contract.

If the result is a list-of-lists, do not cast it directly to List<String>. If the result is a map, check keys and values before using them.

## 12. Common errors and how to handle them

| Symptom | Common cause | How to handle |
|---|---|---|
| Nested property throws an error | An intermediate object is null | Use ?. at each nullable level |
| Source collection is null | Projection starts on null | Guard the collection or use null-safe projection on Spring 6.2+ |
| Source element is null | Property is accessed on a null element | Use #this?.property in the expression |
| Property not found | Wrong name or unsupported accessor | Check the model and getters/accessors |
| Result has multiple sublists | Nested projection keeps hierarchical structure | Flatten in Java if a flat list is needed |
| Result contains null | A property path evaluates to null | Specify clearly whether to keep null, filter out, or substitute a default |
| Source data is mutated | Expression calls a side-effecting method or assignment | Keep projection read-only and move updates to Java |
| Expression is too hard to read | Too many collection levels and nested properties | Split into Java steps or create a DTO |

When debugging, test projection on a simple property first, then add property levels one by one. Next, test with null elements, null intermediate properties, and null child collections to pinpoint the exact boundary causing failure.

## 13. Practice exercises

1. Create a List of Products with name and category.name. Use projection to get each product's category name.
2. Create a List of Orders with customer.address.city. Retrieve the list of cities using nested property projection.
3. Set customer to null on one Order and test the expression with safe navigation.
4. Set one Order element to null and protect it with #this?.
5. Create Orders with a List of LineItems; use nested projection to retrieve SKUs per order.
6. Combine selection to get only cities of paid orders.
7. Build a summary map for each Order containing orderNumber, city, and total.
8. Compare the list-of-lists from nested projection with the flattened result using Java Stream.
9. Test with a null source collection, an empty collection, and a collection containing null elements.
10. Verify that projection does not update source properties when the expression is read-only.

## 14. Checklist before using projection on nested properties

- [ ] Does the source collection exist?
- [ ] Have you identified the current element inside the projection?
- [ ] Does the property path match the model and accessors?
- [ ] Have you protected every intermediate object that can be null?
- [ ] Can a collection element itself be null?
- [ ] Can a child collection be null or empty?
- [ ] Is the result a list of values, a list of maps, or a list-of-lists?
- [ ] Does the result need to be flattened in Java?
- [ ] Are any values constructed with an inline map?
- [ ] Does the expression call methods with side effects or mutate objects?
- [ ] Have you tested complete data, nulls, and empty collections?
- [ ] If using null-safe projection on a collection, does your Spring version support it?

## 15. Conclusion

Projection .![] lets you transform each collection element with a SpEL expression. When properties sit deep inside an object graph, they can be accessed directly like customer.address.city; #this represents the current element in each iteration. Use null-safe navigation at every level that can be null, distinguish a null collection from an empty collection, and remember that nested projection creates a list-of-lists rather than flattening automatically. For long expressions, complex data, or multi-step transformations, moving the logic to Java makes type safety, null handling, and performance much clearer.