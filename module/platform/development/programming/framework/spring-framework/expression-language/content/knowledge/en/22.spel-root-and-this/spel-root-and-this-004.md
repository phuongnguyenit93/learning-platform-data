# Changing the Active Context Object in SpEL Collection Expressions

In Spring Expression Language (SpEL), the **active context object** is the current object against which a part of an expression is being evaluated. The special variable `#this` references this current object; `#root` always references the initial root object of the evaluation pass.

When an expression enters a collection operation such as selection or projection, SpEL sets each element of the collection in turn as the active context object to evaluate the condition or sub-expression. Therefore, `#this` changes with the element being processed, while `#root` stays the same. Understanding this difference clearly helps access the right properties when an expression has multiple collection levels.

## 1. Distinguishing the root object and the active context object

An EvaluationContext has a root object used as the starting point when evaluating an expression. SpEL provides two special references:

- `#root`: the initial root object of the evaluation pass.
- `#this`: the active context object at the current position during evaluation.

Outside collection operations, `#this` is usually the root object itself. When an expression enters selection or projection, the active context object switches to the current element of the collection. `#root` does not change with that switch.

For example, suppose the root object is a catalog with a `products` property:

    #root.products

At the outer level, you can access the root property directly:

    products

When evaluating the predicate inside selection:

    products.?[price > 100]

SpEL evaluates `price > 100` on each product. Inside the predicate, `#this` is the product being checked, so the expression can be written explicitly:

    products.?[#this.price > 100]

Both forms are equivalent in this context. Using `#this` makes it clear that the `price` property belongs to the current element, especially when the expression has multiple nested levels.

## 2. Active context object in selection

Selection uses operators to filter elements by a predicate:

| Operator | Meaning | Result |
|---|---|---|
| `.?[condition]` | Select all matching elements | Collection of matching elements |
| `.^[condition]` | Select the first matching element | A single element or null |
| `.$[condition]` | Select the last matching element | A single element or null |

In each predicate, the active context object is the element being checked. Therefore, properties can be accessed directly or via `#this`.

Example:

    #root.products.?[price >= #root.minimumPrice]

Suppose the root object has `products` and `minimumPrice` properties. Inside the predicate:

- `price` is read from the current product.
- `#this` is the current product.
- `#root.minimumPrice` is read from the initial catalog.

If you want to make both sides explicit:

    #root.products.?[
        #this.price >= #root.minimumPrice
    ]

This style avoids confusing element properties with root object properties.

## 3. Active context object in projection

Projection applies an expression to each element and creates a new result collection. The projection operator is `.![expression]`.

Example to retrieve the name of every product:

    #root.products.![name]

In the `name` sub-expression, the active context object is each product. You can write it explicitly:

    #root.products.![#this.name]

If you need to combine multiple properties of an element:

    #root.products.![
        #this.name + ' - ' + #this.category
    ]

Each time projection processes a product, `#this` points to that product. When moving to the next product, the active context object is updated accordingly. The root object remains the initial catalog throughout the process.

Selection and projection have different purposes: selection keeps the original elements that satisfy the condition, whereas projection creates new values from the expression applied to each element.

## 4. Accessing root properties inside collection expressions

A common mistake is writing a root property name directly inside a predicate, even though the active context object at that point is already a collection element.

Example:

    #root.products.?[price >= minimumPrice]

Inside the predicate, SpEL looks for `minimumPrice` on the current product. If Product does not have that property, the expression will error. If Product happens to have a property with the same name, the expression may run but compare against the product's value instead of the catalog's.

Reference root explicitly:

    #root.products.?[
        price >= #root.minimumPrice
    ]

Rules to remember:

- An unprefixed property name inside a predicate/projection is usually resolved on the active context object.
- `#this.property` also accesses a property of the active context object.
- `#root.property` always accesses a property of the initial root object.
- `#variable` accesses a variable registered in EvaluationContext; variables do not automatically change when the active context object changes.

When two objects have overlapping property names, use `#this` and `#root` explicitly to indicate the right data source.

## 5. Variables in EvaluationContext do not change with #this

Variables registered with `setVariable` have their own scope in EvaluationContext. A collection operation changing the active context object does not change a variable's value.

Example:

    context.setVariable("minimumPrice", new BigDecimal("100"));

    #root.products.?[
        price >= #minimumPrice
    ]

In the predicate, `#this` is the current product, while `#minimumPrice` remains the variable registered by the application. Variables can be used to pass thresholds, configuration, or input data shared across all elements.

Distinguishing the three data sources makes expressions easier to read:

| Syntax | Source |
|---|---|
| `#this` | Current active context object |
| `#root` | Initial root object |
| `#threshold` | Variable named threshold in EvaluationContext |

## 6. Active context object in nested collections

When collection operations are nested, each operation has its own active context object corresponding to the element being processed at that level. When an inner selection or projection runs, `#this` switches to the element of the inner collection. Once the inner operation finishes, the outer expression continues in the context of the outer element currently being processed.

For example, a catalog contains departments, and each department has employees:

    #root.departments.![
        employees.?[active].![name]
    ]

You can read it layer by layer:

1. The outer projection iterates through each department; the active context object of the outer expression is department.
2. The inner selection on `employees` iterates through each employee; inside the `active` predicate, `#this` is the current employee.
3. The innermost projection takes `name` of each matching employee; `#this` continues to be the employee being processed by the projection.
4. The result is a nested collection, with each department corresponding to a list of active employee names.

If you need to reference the root object from any layer, still use `#root`. Do not use `#this` assuming it always represents the element of the outermost collection.

For deeply nested expressions, format each collection operation as a separate block and use `#this` explicitly in important predicates. If logic needs to retain multiple parent/child objects simultaneously for comparison, consider computing part of the data in Java and passing the result via a variable instead of creating an expression that is too hard to follow.

## 7. Collection expressions on Map

When selection or projection runs on a Map, the active context object is the entry currently being processed. Inside the predicate, key and value can be accessed using the names `key` and `value`.

Example selecting entries with value greater than or equal to 80:

    #root.scores.?[value >= 80]

In this predicate, `#this` represents the current Map.Entry; `key` is the entry's key and `value` is its value.

You can write explicitly:

    #root.scores.?[
        #this.value >= #root.minimumScore
    ]

Projection on a Map also evaluates the expression on each entry:

    #root.scores.![value]

The projection result is a collection of values. If you need both key and value, reference `#this.key` and `#this.value` or construct an appropriate result object.

Note that iteration order depends on the Map implementation. If the result needs deterministic ordering by insertion or by key, use a Map with a defined order.

## 8. Complete example in Java

The following example uses a catalog as the root object. The expression filters products whose price meets the catalog's threshold, then projects their names:

    public class Catalog {
        private BigDecimal minimumPrice;
        private List<Product> products;

        public BigDecimal getMinimumPrice() {
            return minimumPrice;
        }

        public List<Product> getProducts() {
            return products;
        }
    }

    public class Product {
        private String name;
        private BigDecimal price;

        public String getName() {
            return name;
        }

        public BigDecimal getPrice() {
            return price;
        }
    }

    Catalog catalog = loadCatalog();

    StandardEvaluationContext context =
            new StandardEvaluationContext(catalog);

    ExpressionParser parser = new SpelExpressionParser();

    List<?> names = parser.parseExpression(
            "products.?[price >= #root.minimumPrice].![#this.name]"
    ).getValue(context, List.class);

In selection, `#this` is each Product in turn and `#root` remains Catalog. Projection after selection continues using each retained Product as the active context object to retrieve `name`.

You can also use `#this` explicitly inside selection:

    #root.products.?[
        #this.price >= #root.minimumPrice
    ].![#this.name]

This form is slightly longer but very helpful when the expression has multiple overlapping property names or is read by someone unfamiliar with active context rules.

## 9. Common mistakes

- **Assuming #this is always root:** inside selection/projection, `#this` switches to the current element.
- **Using a root property without #root:** inside a predicate, property names are looked up on the current element; use `#root.property` for root.
- **Confusing variables with properties:** variables must have the `#` prefix; variable values do not change when the active context changes.
- **Forgetting nested context:** inside an inner collection operation, `#this` represents the element of the inner collection.
- **Assuming #root changes per element:** root is always the initial object of the evaluation pass.
- **Confusing Map with List:** selection on a Map processes Map.Entry; use `key` and `value` to access entry fields.
- **Using overly deep nested expressions:** extract logic into variables or process part of it in Java when multiple object levels must be referenced.

## 10. Takeaways

In SpEL, `#this` is the active context object and can change when an expression enters collection selection or projection. Each element being processed becomes the context object for the corresponding predicate or projection expression. `#root` always preserves the initial root object; `#variable` variables also keep the values registered in EvaluationContext. Use the property name directly or `#this.property` for the current element, and use `#root.property` when reading data from root. With nested collections or Maps, identify the active context clearly at each layer to avoid accessing the wrong object.
