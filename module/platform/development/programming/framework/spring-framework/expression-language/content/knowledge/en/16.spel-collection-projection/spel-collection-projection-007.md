# Null-safe projection ?.! in SpEL

Spring Expression Language (SpEL) supports projection to transform each element in a collection, array, or map into a result collection. Regular projection uses the syntax `.![expression]`. When the target may be null, **null-safe projection** uses the syntax `?.![expression]` to return null instead of throwing an error when starting projection on a null target.

Null-safe projection is useful when data is optional, such as when a list may not have been loaded yet, a relationship may not exist yet, or a collection property may be null. Distinguish a null target collection from an empty collection and from null elements inside the collection: these three cases behave differently.

## 1. Regular projection

Projection applies an expression to each element of a collection. The result is a new collection containing the values computed from each element.

For example, with a list of customers:

    #customers.![name]

SpEL reads the `name` property of each customer and builds a list of names. If each customer has an `address` property, you can retrieve the cities:

    #customers.![address.city]

In projection, `#this` represents the current element being processed. Therefore, the expression above can also be written as:

    #customers.![#this.address.city]

Use `#this` when the predicate or expression is complex and needs to clarify the current object. For simple properties, the direct property name is usually easier to read.

Projection differs from selection:

- `.![expression]` transforms each element and builds a result collection.
- `.?[condition]` filters the collection, keeping only elements that satisfy the condition.

For example, `#customers.![name]` returns the names of all customers; `#customers.?[active]` returns customers who are active.

## 2. Null-safe projection syntax

Null-safe projection syntax:

    target?.![projectionExpression]

Example:

    #customers?.![name]

If `#customers` is a collection, SpEL performs projection as usual. If `#customers` is null, SpEL returns null for this expression instead of trying to run projection on a null target.

Null-safe projection is supported starting in **Spring Framework 6.2**. If an application runs an older version, the parser will not recognize the `?.!` syntax; you must use an explicit null-check condition or upgrade to an appropriate version.

Example using a null guard compatible with regular projection syntax:

    #customers == null ? null : #customers.![name]

This checks the collection first and then runs projection. If the collection can be null and the expression must run across multiple Spring versions, this is an easy-to-understand alternative.

## 3. Distinguishing a null collection from an empty collection

Null-safe projection only changes behavior when **the target is null**. An empty collection is still a valid collection; projection on an empty collection returns an empty result collection.

| Value of target | Expression | Result |
|---|---|---|
| Collection with elements | `#items?.![name]` | List of name values |
| Empty collection | `#items?.![name]` | Empty list |
| Null collection | `#items?.![name]` | null |

This distinction matters when the result is used further. If the application wants the convention “no data” to always be an empty list, explicitly convert null to an empty collection:

    #items == null ? {} : #items.![name]

In SpEL, `{}` is an empty inline list. The expression above returns an empty list when target is null and the projected list when target has a value. Choose either null or an empty list based on the application's data contract; those two values are not identical in every API.

## 4. Projection on a nullable collection property

A common case is a collection residing on an object property:

    #order?.items?.![productName]

Here there are two points that can be null:

1. `#order` may be null, so use safe navigation before `items`.
2. `items` may be null, so use null-safe projection before `![...]`.

If you only write:

    #order?.items.![productName]

then safe navigation protects accessing `items` on a null order, but the `items` collection can still be null when order exists. In that case, regular projection can still fail. Place the null-safe operator at each target that may be null.

Full example:

    #order?.items?.![productName]

If the projection result is also used to invoke a method or access an element, consider null at the next step:

    #order?.items?.![productName]?.size()

Null-safe projection returns null when items is null. The null-safe method invocation at the end avoids calling `size()` on a null result. If the SpEL version or expression syntax does not support the chaining you need, split it into steps or use the conditional operator.

## 5. Null elements inside a collection

Null-safe projection protects the **target collection**, not automatically every element or nested property. For example, a collection may exist while containing a null element:

    #customers?.![name]

If an element is null, accessing `name` on that element can still cause an error. When the current element may be null, use safe navigation inside the projection expression:

    #customers?.![#this?.name]

If an intermediate property can also be null, continue using safe navigation along that path:

    #customers?.![#this?.address?.city]

This expression returns one result per source element; a null element or a null address produces a corresponding null value in the result list. Projection does not automatically filter out null results.

If you want to exclude null elements or elements missing an address, combine selection and projection:

    #customers?.?[#this != null and address != null]
             .![address.city]

Selection filters first, and then projection extracts city. If the collection can be null at each step, use the appropriate null-safe operator for each nullable target or separate the expression with an explicit null guard.

## 6. Null-safe projection on Map

Projection also supports Map. When projecting on a Map, the expression is evaluated on each entry; you can access the key and value of the current entry using the names `key` and `value`.

Example:

    #scores?.![value]

The expression retrieves the Map's values and builds a result List. If you want to get a name or property from an object stored as the value:

    #profiles?.![value?.displayName]

If the Map is null, null-safe projection returns null. If the Map is empty, the result is an empty List. If an entry's value is null, safe navigation `value?.displayName` makes that entry's result null instead of failing when reading the property.

To produce results tied to keys, you can project into an object or structure defined by the application, or process the Map in Java if exact key-value relationships must be preserved. Projection on a Map builds a result list in the Map's iteration order; use a Map with a deterministic order if result order matters.

## 7. Null-safe projection on arrays

Projection can be applied to arrays. For an array that may be null:

    #names?.![#this?.toUpperCase()]

If the array is not null, SpEL applies the expression to each element and builds a result collection. If the array is null, the expression returns null.

For example, with an array of names:

    String[] names = {"Lan", null, "Minh"};

    StandardEvaluationContext context =
            new StandardEvaluationContext();
    context.setVariable("names", names);

    ExpressionParser parser = new SpelExpressionParser();

    List<?> upperNames = parser.parseExpression(
            "#names?.![#this?.toUpperCase()]"
    ).getValue(context, List.class);

The result contains `"LAN"`, null, and `"MINH"`. Safe navigation on `#this` handles the null element; `?.!` handles the case where the entire array is null.

## 8. Support by Spring version

Null-safe navigation for properties and methods has existed in earlier Spring versions using the `?.` syntax. Null-safe operators for indexing, selection, and projection were added in Spring Framework 6.2.

Some related syntaxes:

| Operation | Null-safe syntax |
|---|---|
| Property or method | `target?.property`, `target?.method()` |
| Index | `target?.[index]` |
| Selection all | `target?.?[condition]` |
| First selection | `target?.^[condition]` |
| Last selection | `target?.$[condition]` |
| Projection | `target?.![expression]` |

If an expression uses the new syntax while the application runs an older Spring version, an error can occur immediately during parsing rather than during evaluation. Confirm the actual Spring Framework version of your application before using these operators.

## 9. Complete example with EvaluationContext

The following example illustrates a null collection, null elements, and nested properties:

    public class Customer {
        private Address address;

        public Address getAddress() {
            return address;
        }
    }

    public class Address {
        private String city;

        public String getCity() {
            return city;
        }
    }

    List<Customer> customers = loadCustomersOrNull();

    StandardEvaluationContext context =
            new StandardEvaluationContext();
    context.setVariable("customers", customers);

    ExpressionParser parser = new SpelExpressionParser();

    Expression citiesExpression = parser.parseExpression(
            "#customers?.![#this?.address?.city]"
    );

    List<?> cities = citiesExpression.getValue(context, List.class);

If `customers` is null, the result is null. If the list is empty, the result is an empty list. If a customer is null or address is null, the corresponding position in the result is null. This handling preserves the number of input elements in the projection result.

If the application needs to exclude customers who do not have an address yet, filter first:

    #customers?.?[
        #this != null and address != null
    ]?.![address.city]

This example uses null-safe selection to handle a null collection, filters elements that have both customer and address, and then projects city. Null-safe selection and projection syntax require Spring Framework 6.2 or later.

## 10. Common errors

- **Using `?.!` on older Spring versions:** null-safe projection syntax requires Spring Framework 6.2+; check the version if the parser reports an error.
- **Protecting only the collection:** `#items?.![address.city]` does not automatically protect null elements or null addresses; use `#this?.address?.city` if those values can be missing.
- **Confusing null with an empty collection:** a null target returns null, while an empty collection produces an empty result.
- **Assuming projection automatically filters nulls:** projection keeps a null result if an element's expression returns null; use selection if you want to drop elements.
- **Chaining non-null-safe operations afterward:** if projection returns null, calling a regular method or index on the result can cause an error; keep checking or use safe navigation.
- **Forgetting collection order:** projection results preserve the source's iteration order; if a Map has no stable order, the result should not be assumed stable either.
- **Using projection instead of filtering:** use `.![...]` to transform elements and `.?[...]` to select elements matching a condition.

## 11. Key takeaways

Null-safe projection uses the syntax `target?.![expression]` and is supported starting in Spring Framework 6.2. If the target collection or array is null, the expression returns null; if the target is empty, projection returns an empty collection. This operator does not automatically handle null elements or nested properties that may be null, so use safe navigation inside the projection expression when needed. Projection produces a result for each element; selection is the tool for filtering. When chaining additional methods, indexing, or other projections, check for null at each step so the expression behaves predictably.
