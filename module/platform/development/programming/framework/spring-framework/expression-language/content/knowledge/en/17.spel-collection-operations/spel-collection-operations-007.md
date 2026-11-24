# Distinguishing mutable collections from read-only results

When working with collections in Spring Expression Language (SpEL), you need to distinguish **the mutability of the source collection**, **a new collection created by an expression**, and **the read-only policy of EvaluationContext**. These three concepts are related, but not synonymous.

One collection may allow adding, removing, or replacing elements. Another collection may only allow reading. Meanwhile, a SpEL expression may return a reference to the source collection or create a new result collection via selection and projection. Using a read-only context also does not automatically turn every returned object into an immutable one.

## What is a mutable collection?

A mutable collection allows changing its structure or contents through operations such as:

- **add(...)**: add an element.
- **remove(...)**: remove an element.
- **set(...)**: replace an element at a position in a List.
- **put(...)**: add or replace an entry in a Map.
- **clear()**: remove all elements.

Example with ArrayList:

~~~java
List<String> names = new ArrayList<>();
names.add("An");
names.add("Binh");

names.add("Chi");
names.set(0, "Anh");
names.remove("Binh");
~~~

After these operations, the collection contains **Anh** and **Chi**. These changes apply directly to the referenced ArrayList object.

A read-only or unmodifiable collection does not allow callers to perform write operations through that reference. Example:

~~~java
List<String> names = List.of("An", "Binh", "Chi");

// names.add("Dung"); // UnsupportedOperationException
~~~

**List** is an interface describing how to access a list; it does not guarantee a mutable implementation. An ArrayList is usually mutable, whereas List.of(...) returns a list that does not support modification. Therefore, you cannot conclude a collection is mutable solely from the declared type List or Collection.

## Read-only view and immutable snapshot

Java has multiple ways to provide collections that disallow caller modification, but they do not have the same semantics.

### Unmodifiable view

**Collections.unmodifiableList(...)** creates a wrapper that blocks write operations through the wrapper:

~~~java
List<String> source = new ArrayList<>(
        List.of("An", "Binh"));

List<String> view =
        Collections.unmodifiableList(source);
~~~

Callers cannot invoke **view.add(...)** or **view.remove(...)** successfully. However, the view still reads from the source collection. If other code modifies source, the content observed through view changes as well:

~~~java
source.add("Chi");

// view now also sees "Chi"
~~~

This is a **read-only view**, not an independent snapshot. The underlying collection remains mutable and other references can still modify it.

### Unmodifiable snapshot

If you want to create a result that disallows modification and does not reflect subsequent changes to the source collection, copy first and then wrap:

~~~java
List<String> snapshot =
        Collections.unmodifiableList(
                new ArrayList<>(source));
~~~

Or use **List.copyOf(...)** when the data contains no nulls:

~~~java
List<String> snapshot = List.copyOf(source);
~~~

List.copyOf creates a list that does not support modification and does not track structural changes to the source collection. This method does not accept null elements.

For a Map, you can use **Collections.unmodifiableMap(new LinkedHashMap<>(source))** to create a snapshot that disallows caller modification and preserves LinkedHashMap iteration order. **Map.copyOf(...)** also creates an unmodifiable Map, but does not accept null keys or null values.

Both snapshot approaches above are **shallow copies**: the new collection has its own structure, but the objects contained inside may still be the same mutable references.

## Does SpEL return the source collection or a new collection?

Check whether the expression is reading a property directly or performing a collection operation.

### Reading a property directly

Suppose the root object has a products property:

~~~java
public class Catalog {
    private final List<Product> products;

    public Catalog(List<Product> products) {
        this.products = products;
    }

    public List<Product> getProducts() {
        return products;
    }
}
~~~

If evaluating the expression:

~~~java
Expression expression =
        parser.parseExpression("products");

List<Product> result =
        expression.getValue(catalog, List.class);
~~~

SpEL reads the products property and returns the value provided by the getter. If the getter returns the internal mutable collection of Catalog itself, **result and catalog.getProducts() reference the same collection**.

Therefore, if the caller modifies result, the collection inside Catalog is also modified:

~~~java
result.add(new Product("Keyboard"));
~~~

This is a mutation on the source collection because no new collection was created during this property read.

If you do not want to expose the internal collection directly, return an appropriate view or snapshot from the getter, or create a DTO containing only the data needed for reading.

## Selection creates a new result collection

Selection uses the syntax **.?[condition]** to filter elements:

~~~java
List<Product> selected =
        parser.parseExpression("products.?[active]")
                .getValue(catalog, List.class);
~~~

SpEL evaluates the condition on each element and returns a new collection containing the matching elements. With selection on a Map, the result is a new Map containing the selected entries.

Spring documentation describes selection as an operation that creates a new collection containing a subset of the source data. However, the documentation contract does not state that every result collection is unmodifiable. You should not rely on being able to call add, remove, or put on the result unless you control the actual implementation.

Another important point is that **a new collection does not mean the elements inside are copied**. Selection keeps the selected elements from the source. If an element is a mutable Product, result and source still reference the same Product.

Example:

~~~java
Product product = catalog.getProducts().get(0);

List<Product> selected =
        parser.parseExpression("products.?[active]")
                .getValue(catalog, List.class);

selected.get(0).setName("Updated name");
~~~

If selected contains the original product itself, changing name will be visible through the source collection because the Product object is shared. Creating a new collection only separates the **container**; it does not automatically make a deep copy of the elements.

## Projection creates a collection from expression values

Projection uses the syntax **.![expression]** to compute a value for each element and collect the results:

~~~java
List<String> names =
        parser.parseExpression("products.![name]")
                .getValue(catalog, List.class);
~~~

In the example, projection creates a List of product names. The result elements are Strings, so callers cannot use them to modify the name property of the original Product.

If projection returns the current object itself:

~~~java
List<Product> sameProducts =
        parser.parseExpression("products.![#this]")
                .getValue(catalog, List.class);
~~~

The List container is new, but the elements are still references to Products in the source collection. If projection returns a property containing a mutable object, those references can also be shared.

With projection on a Map, SpEL evaluates the expression on each Map.Entry and creates a List of results. This is a new collection; it is not the original Map and does not automatically preserve the original key-value mapping.

## Distinguishing the three cases

| Expression or operation | Result container | Relationship to source |
|---|---|---|
| **products** | Reference to the collection returned by the getter | May be the source collection itself |
| **products.?[active]** | New collection containing selected elements | Separate container; elements may share references |
| **products.![name]** | New collection containing projected values | Separate container; values may be new objects or existing references |
| **Collections.unmodifiableList(source)** | Read-only wrapper | Still sees changes to source |
| **Collections.unmodifiableList(new ArrayList<>(source))** | Read-only snapshot | Independent structure; elements may still be mutable |

Spring Reference describes selection and projection as operations that return a new collection. Selection retains matching elements; projection produces a value for each element. Distinguish that from directly reading a collection property. See also [Collection Selection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-selection.html) and [Collection Projection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-projection.html).

## Read-only SimpleEvaluationContext does not freeze collections

**SimpleEvaluationContext.forReadOnlyDataBinding()** configures property access in a read-only direction. Its purpose is to restrict property assignment through SpEL in that context.

Example:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

Expression expression =
        parser.parseExpression("products");

List<Product> products =
        expression.getValue(context, catalog, List.class);
~~~

Using read-only data binding does not automatically:

- Copy the returned collection.
- Wrap the collection with Collections.unmodifiableList or Collections.unmodifiableMap.
- Convert elements into immutable objects.
- Create a deep copy of the object graph.
- Prevent external Java code from modifying a mutable collection to which it holds a reference.

In other words, **a read-only EvaluationContext is SpEL's access policy**, whereas mutability is a property of the returned Java objects. These two layers of protection must be designed separately.

Spring documentation also notes that read-only data binding controls property assignment, but does not verify that an accessor invoked when reading a property is pure and side-effect-free. Therefore, objects exposed to expressions still need APIs suited to the trust level of the expressions.

## How to create a mutable result intentionally

If you need to modify the set of selected elements, create a mutable copy:

~~~java
List<Product> selected =
        parser.parseExpression("products.?[active]")
                .getValue(catalog, List.class);

List<Product> editable =
        new ArrayList<>(selected);

editable.add(new Product("New product"));
~~~

Here, editable is an ArrayList intentionally created by the application. Adding or removing elements in editable does not alter the structure of the products collection in Catalog.

However, the Products in editable may still be the original objects. If you need to modify properties without affecting the source, copy each Product or convert them into new DTOs/value objects.

## How to create a read-only result intentionally

If you want to provide results to another layer strictly for reading, create a snapshot and then wrap it:

~~~java
List<Product> selected =
        parser.parseExpression("products.?[active]")
                .getValue(catalog, List.class);

List<Product> readOnlySnapshot =
        Collections.unmodifiableList(
                new ArrayList<>(selected));
~~~

Callers cannot add or remove elements through readOnlySnapshot. The snapshot's structure also does not change when elements are later added to or removed from the source collection.

But if Product is still mutable, callers can invoke setters on a Product obtained from the snapshot. If you need to protect element state as well, map to an immutable DTO or deep-copy according to the application's data structure:

~~~java
List<ProductView> views = selected.stream()
        .map(product -> new ProductView(
                product.getId(),
                product.getName()))
        .toList();
~~~

This example creates ProductView instances containing only the data needed for display. To guarantee immutability, ProductView itself and any nested fields inside it must also be designed appropriately.

## Note on Kotlin

In Kotlin, **List<T>** is a read-only interface at the language API level, whereas **MutableList<T>** provides add, remove, and replace operations. However, a List<T> can be backed by a mutable collection to which other code still holds a reference.

Therefore, declaring a variable as List<T> restricts the operations Kotlin code can call directly, but does not necessarily create an immutable snapshot. If an unchanging snapshot is needed, copy to an unmodifiable collection or use an appropriate immutable data type.

## Common design mistakes

- **Assuming List is always mutable:** List is only an interface; implementations can be mutable or unmodifiable.
- **Assuming selection/projection results are read-only:** Spring describes the result as a new collection, but does not guarantee it is immutable.
- **Assuming a new collection means new objects:** selection generally keeps the selected elements; projection may return element references.
- **Confusing a read-only context with immutable data:** SimpleEvaluationContext limits SpEL capabilities, not freezes the object graph.
- **Using an unmodifiable view while still exposing the underlying collection:** other code can modify the source collection and cause the view to change as well.
- **Copying only the container while ignoring mutable elements:** a structural snapshot does not guarantee that nested object state is immutable.

## Conclusion

When using collections in SpEL, clearly determine whether an expression returns a reference to the source collection or creates a new result collection. Reading a property directly may return the object's own mutable collection. Selection and projection create a new collection, but do not automatically deep-copy elements or guarantee the result is unmodifiable.

**SimpleEvaluationContext.forReadOnlyDataBinding()** restricts property assignment via SpEL; it does not make returned collections immutable. If modifications are needed, create an explicit ArrayList or Map copy. If read-only results are needed, create a snapshot and wrap it with an unmodifiable API or use an appropriate immutable collection. When inner elements remain mutable, immutable DTOs or deep copies are needed to protect all data.
