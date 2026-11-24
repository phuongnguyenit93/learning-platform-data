# Filtering and Projecting Object Lists with Selection and Projection in SpEL

## 1. What do selection and projection solve?

Spring Expression Language (SpEL) provides two commonly used collection operations:

- Selection filters elements according to a condition.
- Projection creates a result value for each element in a collection.

Selection uses the syntax `.?[condition]`. Projection uses the syntax `.![expression]`.

For example, from a list of products, get the products in stock and then get their names:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
        "products.?[active and stock > 0].![name]");

List<?> names = expression.getValue(catalog, List.class);
~~~

The selection part keeps products whose active is true and stock is greater than 0. The projection part reads the name of each retained product.

The two operations can be combined in a short expression. When multiple business steps or multiple levels of nested collections are needed, consider splitting them into clearly named Java steps.

## 2. Syntax structure

General syntax:

~~~text
collection.?[selectionExpression]
collection.![projectionExpression]
~~~

Selection evaluates the condition on each element. An element is kept if the condition evaluates to Boolean true.

Projection evaluates the expression on each element and adds the result to the result collection. Projection does not filter elements; each input element produces a corresponding result value.

For example:

~~~text
products.?[active]
products.![name]
products.?[stock > 0].![name]
~~~

- `products.?[active]` selects products that are active.
- `products.![name]` gets the name of all products.
- `products.?[stock > 0].![name]` filters products in stock and then gets their names.

Choose selection when you need to reduce the number of elements and projection when you need to transform an element into another value.

## 3. Preparing an object graph for practice

The example uses Product and Catalog. Getters allow SpEL to read properties by name:

~~~java
public class Product {
    private final String sku;
    private final String name;
    private final String category;
    private final boolean active;
    private final int stock;
    private final BigDecimal price;

    public Product(
            String sku,
            String name,
            String category,
            boolean active,
            int stock,
            BigDecimal price) {
        this.sku = sku;
        this.name = name;
        this.category = category;
        this.active = active;
        this.stock = stock;
        this.price = price;
    }

    public String getSku() {
        return sku;
    }

    public String getName() {
        return name;
    }

    public String getCategory() {
        return category;
    }

    public boolean isActive() {
        return active;
    }

    public int getStock() {
        return stock;
    }

    public BigDecimal getPrice() {
        return price;
    }
}

public class Catalog {
    private final String owner;
    private final List<Product> products;

    public Catalog(String owner, List<Product> products) {
        this.owner = owner;
        this.products = products;
    }

    public String getOwner() {
        return owner;
    }

    public List<Product> getProducts() {
        return products;
    }
}
~~~

Create a small fixture:

~~~java
Catalog catalog = new Catalog(
        "Lan",
        List.of(
                new Product("P-01", "Keyboard", "Computer", true, 12,
                        new BigDecimal("45.00")),
                new Product("P-02", "Mouse", "Computer", true, 0,
                        new BigDecimal("20.00")),
                new Product("P-03", "Notebook", "Stationery", false, 30,
                        new BigDecimal("5.00")),
                new Product("P-04", "Pen", "Stationery", true, 50,
                        new BigDecimal("2.50"))));
~~~

The data includes active and inactive products, in-stock and out-of-stock products, across multiple categories. Thanks to that, selection conditions produce easily observable results.

## 4. Filtering a collection with selection

Selection keeps the elements that satisfy the predicate inside square brackets:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("products.?[active]");

List<?> activeProducts =
        expression.getValue(catalog, List.class);

assertEquals(3, activeProducts.size());
~~~

In the predicate, an unprefixed property is read on the current element. Therefore `active` is equivalent to checking the active property of each Product.

You can write it explicitly using `#this`:

~~~java
Expression expression =
        parser.parseExpression("products.?[#this.active]");
~~~

Writing `#this` is useful when a predicate has multiple references and needs to clarify the current object. For simple conditions, the direct property is usually more concise.

## 5. Combining multiple selection conditions

A predicate can combine Boolean conditions:

~~~java
Expression expression = parser.parseExpression(
        "products.?[active and stock > 0 and price >= 10]");

List<?> availableProducts =
        expression.getValue(catalog, List.class);
~~~

Here a product is kept only when simultaneously:

- active is true.
- stock is greater than 0.
- price is greater than or equal to 10.

You can use `or` and parentheses to express condition grouping:

~~~text
products.?[active and (category == 'Computer' or stock >= 40)]
~~~

When a predicate has multiple branches, use parentheses so readers clearly see the combination order. If the condition becomes a long business rule, move the predicate to a Java method named something like isEligibleForSale.

## 6. Using variables as filter parameters

You can pass thresholds or filter criteria into the EvaluationContext instead of concatenating values into the expression source:

~~~java
Expression expression =
        parser.parseExpression("products.?[price >= #minimumPrice]");

StandardEvaluationContext context =
        new StandardEvaluationContext(catalog);

context.setVariable("minimumPrice", new BigDecimal("10.00"));

List<?> result = expression.getValue(context, List.class);
~~~

The same expression can be used with a different threshold:

~~~java
context.setVariable("minimumPrice", new BigDecimal("40.00"));

List<?> expensiveProducts =
        expression.getValue(context, List.class);
~~~

Variables are referenced with the `#` prefix. The products property is still read from the root object catalog.

Passing dynamic data via variables keeps the expression source stable, makes it easy to parse once, and avoids turning input data into SpEL syntax.

## 7. Getting the first or last element matching a condition

In addition to regular selection, SpEL supports selection that retrieves the first or last matching result:

~~~text
collection.^[condition]
collection.$[condition]
~~~

For example:

~~~java
Expression firstAvailable = parser.parseExpression(
        "products.^[active and stock > 0]");

Expression lastAvailable = parser.parseExpression(
        "products.$[active and stock > 0]");

Product first = firstAvailable.getValue(catalog, Product.class);
Product last = lastAvailable.getValue(catalog, Product.class);
~~~

- `.^[...]` returns the first element satisfying the condition.
- `.$[...]` returns the last element satisfying the condition.

If no element matches, the result of first/last selection is null. Handle null before accessing properties on the result.

The order of the input collection affects the first and last results. If ordering has business meaning, ensure the collection has a clear ordering contract.

## 8. Projection to extract a property from each object

Projection applies an expression to each element and creates a result collection:

~~~java
Expression expression =
        parser.parseExpression("products.![name]");

List<?> names = expression.getValue(catalog, List.class);

assertEquals(
        List.of("Keyboard", "Mouse", "Notebook", "Pen"),
        names);
~~~

Each Product produces a String corresponding to the name property. The number of elements in the projection result corresponds to the number of input elements processed.

Various types of properties can be projected:

~~~text
products.![sku]
products.![price]
products.![category]
products.![active]
~~~

Projection extracts only the needed value, reducing the dependency of downstream processing on the entire Product object.

If only product names are needed, use `products.![name]` instead of returning the entire object and looping manually in Java.

## 9. Projection to create computed values

Projection is not limited to reading a property. The inner expression can perform calculations on each element:

~~~java
Expression expression =
        parser.parseExpression("products.![price * 1.1]");

List<?> pricesWithTax =
        expression.getValue(catalog, List.class);
~~~

You can create a descriptive string for each product:

~~~text
products.![name + ' (' + category + ')']
~~~

Or produce a Boolean value:

~~~text
products.![active and stock > 0]
~~~

Each input element produces a corresponding result. Keep projection simple and easy to understand; if complex pricing calculations, multi-rule rounding, or multiple service calls are needed, move the computation to Java.

## 10. Combining selection then projection

A common workflow is to filter first and then project values:

~~~java
Expression expression = parser.parseExpression(
        "products.?[active and stock > 0].![name]");

List<?> names = expression.getValue(catalog, List.class);

assertEquals(List.of("Keyboard", "Pen"), names);
~~~

The order of operations is very important:

1. Selection keeps only active and in-stock products.
2. Projection gets name from the remaining products.
3. The result is a list of names, not a list of Product.

If the order is reversed, the meaning changes. Projecting first creates a collection of name values; the subsequent predicate must be written for the new data type and can no longer access properties of Product.

Read the expression from left to right to determine the data type each step receives and returns.

## 11. Using #this and #root in predicates

In selection and projection, `#this` represents the current element. `#root` holds a reference to the original root object of the evaluation.

For example, a predicate checking both the Catalog's owner and the product's price:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(catalog);

context.setVariable("expectedOwner", "Lan");
context.setVariable("minimumPrice", new BigDecimal("10.00"));

Expression expression = parser.parseExpression(
        "products.?[#root.owner == #expectedOwner "
        + "and #this.price >= #minimumPrice].![name]");

List<?> names = expression.getValue(context, List.class);
~~~

In the predicate:

- `#root.owner` reads owner from Catalog.
- `#this.price` reads price of the current Product.
- `#expectedOwner` and `#minimumPrice` are variables in the context.

When collection operations are nested, #this changes according to the current collection level. If you have to track multiple levels of #this to understand an expression, extract the intermediate collection into a Java variable or a named method.

## 12. Selection on Map

SpEL also supports selection on Map. With a Map, selection keeps entries that satisfy the condition and the result is a Map containing the selected entries.

In the predicate, the current element is an entry; key and value can be accessed:

~~~java
Map<String, Product> productsBySku = Map.of(
        "P-01", new Product("P-01", "Keyboard", "Computer",
                true, 12, new BigDecimal("45.00")),
        "P-02", new Product("P-02", "Mouse", "Computer",
                true, 0, new BigDecimal("20.00")));

StandardEvaluationContext context =
        new StandardEvaluationContext();
context.setVariable("productsBySku", productsBySku);

Expression expression = parser.parseExpression(
        "#productsBySku.?[value.active and value.stock > 0]");

Map<?, ?> available =
        expression.getValue(context, Map.class);
~~~

Here `value` is the value of the current Map.Entry. You can check key when the condition depends on the entry key:

~~~text
#productsBySku.?[key.startsWith('P-') and value.active]
~~~

Projection on a Map creates a list of values computed from each entry. For example, you can extract names from value:

~~~text
#productsBySku.![value.name]
~~~

Distinguish Map from List: a Map predicate operates on entries having key and value, whereas a List predicate operates directly on element objects.

## 13. Selection on arrays and collections

Selection can be used on collection types supported by SpEL, including Collection and array. The result of selection on a collection/array is a list of matching elements; with a Map, the result is a Map holding matching entries.

Example with an array:

~~~java
Product[] products = {
        new Product("P-01", "Keyboard", "Computer",
                true, 12, new BigDecimal("45.00")),
        new Product("P-02", "Mouse", "Computer",
                true, 0, new BigDecimal("20.00"))
};

Expression expression =
        parser.parseExpression("[?]"); // Only illustrates an array passed as root.
~~~

When an array is the root object, selection can be used directly on the root collection using syntax appropriate for the expression. In applications, it is usually more readable if the array is exposed through a named property, such as `products.?[active]`.

With an empty collection, regular selection returns an empty result collection. Projection on an empty collection also returns an empty collection. This differs from a null target collection.

## 14. Handling null elements inside a collection

A collection can contain null elements. A null-safe operator on the root collection does not automatically remove null elements inside it.

The predicate should check the element before reading properties:

~~~java
List<Product> products = Arrays.asList(
        new Product("P-01", "Keyboard", "Computer",
                true, 12, new BigDecimal("45.00")),
        null,
        new Product("P-02", "Mouse", "Computer",
                true, 0, new BigDecimal("20.00")));

StandardEvaluationContext context =
        new StandardEvaluationContext();
context.setVariable("products", products);

Expression expression = parser.parseExpression(
        "#products.?[#this != null and #this.active].![name]");

List<?> names = expression.getValue(context, List.class);
~~~

The `#this != null` check precedes accessing `#this.active`. As a result, null elements do not have their properties accessed.

If projection needs to preserve the position of a null element while producing a corresponding null value, null-safe property access can be used:

~~~text
#products.![#this?.name]
~~~

If the business logic wants to drop null elements, filter first and then project. Decide clearly whether to remove elements or keep a null result.

## 15. Handling a null root collection

A null target collection differs from an empty collection. Null-safe selection and projection are supported starting from Spring Framework 6.2:

~~~text
products?.?[active]
products?.![name]
~~~

If products is null, the null-safe collection operation returns null. If products is an empty collection, the result is an empty collection.

With Spring Framework versions older than 6.2, check for null in Java before evaluating or supply an empty collection if the two states have the same business meaning.

Do not automatically turn null into an empty collection if null means "data not loaded yet" while empty means "loaded but no elements".

## 16. Result collections and data types

Selection and projection have different result types depending on the input collection and the operation:

| Input | Operation | Result |
|---|---|---|
| Collection or array | Selection | List of matching elements |
| Map | Selection | Map containing matching entries |
| Collection, array, or Map | Projection | List of projected values |
| Empty collection | Selection | Empty result collection |
| Empty collection | Projection | Empty result collection |
| Null collection with null-safe operator | Selection/projection | null |

When calling getValue, you can request the appropriate List or Map type:

~~~java
List<?> names = expression.getValue(context, List.class);
Map<?, ?> selectedEntries = mapExpression.getValue(context, Map.class);
~~~

Class<List> does not represent the generic type of elements. If the application needs a concrete List<String>, verify the contents and type of each element in tests.

## 17. Testing selection with JUnit 5

Tests should include both matching and non-matching elements to prove the predicate works properly:

~~~java
@Test
void selectsOnlyActiveProducts() {
    Catalog catalog = TestData.catalog();

    Expression expression = new SpelExpressionParser()
            .parseExpression("products.?[active]");

    List<?> result = expression.getValue(catalog, List.class);

    assertEquals(3, result.size());
    assertEquals("Keyboard", ((Product) result.get(0)).getName());
    assertEquals("Mouse", ((Product) result.get(1)).getName());
}
~~~

In addition to count, check the contents and order if ordering is part of the collection contract. A selection might return the right number of elements while still selecting the wrong elements.

Cases to include:

- All elements match.
- No elements match.
- Only one element matches.
- Empty collection.
- Null elements if the collection allows them.
- Property used in the predicate has a null value.
- Variable value changes between evaluations.

## 18. Testing projection with JUnit 5

Projection needs to confirm each input element produces the right value:

~~~java
@Test
void projectsProductNames() {
    Catalog catalog = TestData.catalog();

    Expression expression = new SpelExpressionParser()
            .parseExpression("products.![name]");

    List<?> names = expression.getValue(catalog, List.class);

    assertEquals(
            List.of("Keyboard", "Mouse", "Notebook", "Pen"),
            names);
}
~~~

You can test projection after selection:

~~~java
@Test
void filtersBeforeProjectingNames() {
    Catalog catalog = TestData.catalog();

    Expression expression = new SpelExpressionParser()
            .parseExpression(
                    "products.?[active and stock > 0].![name]");

    List<?> names = expression.getValue(catalog, List.class);

    assertEquals(List.of("Keyboard", "Pen"), names);
}
~~~

Tests should verify result ordering if the collection is ordered. For projections with calculations, check both the type and value of results to detect unexpected conversions.

## 19. Testing first and last selection

First/last selection needs tests for both matching and non-matching cases:

~~~java
@Test
void selectsFirstAndLastAvailableProduct() {
    Catalog catalog = TestData.catalog();

    Expression firstExpression =
            parser.parseExpression("products.^[active and stock > 0]");
    Expression lastExpression =
            parser.parseExpression("products.$[active and stock > 0]");

    Product first = firstExpression.getValue(catalog, Product.class);
    Product last = lastExpression.getValue(catalog, Product.class);

    assertEquals("P-01", first.getSku());
    assertEquals("P-04", last.getSku());
}
~~~

Case with no matching element:

~~~java
Expression expression =
        parser.parseExpression("products.^[stock < 0]");

Product result = expression.getValue(catalog, Product.class);

assertNull(result);
~~~

Do not access properties on the result before checking for null. If the input order is unstable, first/last also have no stable meaning; sort the data in Java before evaluating.

## 20. Splitting selection and projection when debugging

An expression combining two operations can be split into two expressions to inspect intermediate results:

~~~java
Expression selection =
        parser.parseExpression("products.?[active and stock > 0]");

Expression projection =
        parser.parseExpression("#selected.![name]");

StandardEvaluationContext context =
        new StandardEvaluationContext(catalog);

List<?> selected = selection.getValue(context, List.class);
context.setVariable("selected", selected);

List<?> names = projection.getValue(context, List.class);
~~~

The selection step allows checking which Products are kept. The projection step allows checking how name is extracted from that list.

There is no need to split every short expression into multiple steps. Split when intermediate results help find bugs or when each step has a distinct business meaning.

## 21. Common errors

**Confusing selection with projection**

Selection filters elements; projection creates a new value for each element. Projection does not automatically remove non-matching elements.

**Forgetting the dot before the operator**

Collection operation syntax uses the forms `.?[...]` and `.![...]`. Check the dot, symbol, and square brackets.

**Using a root property instead of an element property**

In a predicate, a direct property is normally read on the current element. Use `#root` when you need to access the root object.

**Confusing #this and #root**

#this changes according to the current element inside selection/projection; #root keeps the original root object.

**Assuming Map behaves like List**

Selection on a Map returns the selected Map entries. In the predicate, access key and value of the entry.

**Not checking for null elements**

A collection may be non-null yet contain null elements. Check #this before reading properties.

**Confusing a null collection with an empty collection**

A null-safe operation on a null target returns null; an operation on an empty collection returns an empty collection.

**Checking only size**

Tests that only check count may miss selecting the wrong elements or projecting in the wrong order. Check actual values.

**Nesting too many collection operations**

Multi-level selection/projection makes it hard to track #this scope. Split into named Java steps when the expression becomes hard to read.

## 22. Workflow for choosing and verifying an expression

When filtering and transforming a list of objects:

1. Identify whether the collection is in a root property or a variable.
2. Identify which elements the predicate needs to keep.
3. Use selection `.?[...]` to filter.
4. Identify the value to extract from each element.
5. Use projection `.![...]` to produce the result.
6. Verify that #this is the current element and #root is the original root object.
7. Determine whether the collection can be null or contain null elements.
8. Test empty collections, no matching elements, and multiple matching elements.
9. Verify the type, contents, and order of the result.
10. If multiple levels or long rules are needed, move the logic to Java.

This workflow helps the expression clearly express two tasks: filtering elements and extracting the required data from the retained elements.

## 23. Key takeaways

- Selection uses `.?[condition]` to keep elements satisfying a condition.
- Projection uses `.![expression]` to create one value for each element.
- Selection followed by projection can be chained, for example `products.?[active].![name]`.
- `#this` is the current element; `#root` is the original root object.
- Use `.^[condition]` to get the first matching element and `.$[condition]` to get the last matching element.
- Selection on a Map returns selected Map entries; the predicate can read key and value.
- Projection creates a list of values from the input elements.
- An empty collection differs from a null collection; null-safe collection operators are available starting from Spring Framework 6.2.
- Check for null elements before reading properties.
- Test both contents and order, not just count.
- Keep expressions short; move deeply nested collection operations to Java when needed.

