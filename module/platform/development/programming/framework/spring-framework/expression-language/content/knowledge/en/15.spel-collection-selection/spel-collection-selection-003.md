# The #this variable in a selection context

In Spring Expression Language (SpEL), **#this** is a special variable that references the object currently being evaluated at the present moment. When using collection selection, SpEL evaluates a condition expression on each element of the collection. On each evaluation of the condition, **#this points to the current element**.

This helps the expression clearly describe which element is being checked, especially when the collection contains objects with multiple properties or when selections are nested. You need to distinguish **#this** from **#root**: #root always references the initial root object of the entire evaluation, while #this changes according to the current evaluation context.

## How does collection selection work?

SpEL supports selection to filter collection elements according to a condition. The basic syntax is:

~~~text
collection.?[selectionExpression]
~~~

SpEL iterates through the elements, evaluates selectionExpression for each element, and keeps the elements whose condition result is true. While evaluating the predicate, the element being examined becomes the current object and can be referenced with **#this**.

For example, filtering numbers greater than 10:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable(
        "numbers",
        List.of(4, 12, 7, 18, 25));

Expression expression =
        parser.parseExpression("#numbers.?[#this > 10]");

List<?> result =
        expression.getValue(context, List.class);
~~~

The result contains the values **12, 18, 25**. Each time the predicate is evaluated, #this is 4, 12, 7, 18, and 25 in turn. Only elements that make the condition return true are retained.

With simple elements like integers, the condition can be written directly without #this. Writing **#this > 10** explicitly helps make it clear that the operator is comparing the current element of the collection.

## #this points to the current element inside the predicate

When the collection contains objects, #this lets you access the properties of the object currently being checked:

~~~java
public class Product {
    private final String name;
    private final BigDecimal price;
    private final boolean active;

    public Product(String name, BigDecimal price, boolean active) {
        this.name = name;
        this.price = price;
        this.active = active;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public boolean isActive() {
        return active;
    }
}
~~~

~~~java
List<Product> products = List.of(
        new Product("Keyboard", new BigDecimal("80.00"), true),
        new Product("Monitor", new BigDecimal("250.00"), true),
        new Product("Mouse", new BigDecimal("25.00"), false));

StandardEvaluationContext context =
        new StandardEvaluationContext();
context.setVariable("products", products);

ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression(
                "#products.?[#this.active and #this.price >= 50]");

List<?> available =
        expression.getValue(context, List.class);
~~~

The predicate checks two conditions on the same current Product:

- **#this.active** requires the product to be active.
- **#this.price >= 50** requires the price to be at least 50.

The result keeps Keyboard and Monitor. For Mouse, the active condition is false so the element is not selected, even though its price does not affect the final result.

Inside a selection predicate, SpEL also allows accessing properties directly without writing #this:

~~~text
#products.?[active and price >= 50]
~~~

Both ways express the same meaning in the predicate context. Using #this explicitly is often helpful when the expression is long, has multiple access levels, or contains nested selection.

## Distinguishing #this and #root

These two special variables have different roles:

| Variable | Meaning | Behavior during selection |
|---|---|---|
| **#root** | Initial root object of the evaluation | Stays unchanged throughout the expression |
| **#this** | Current object at the position being evaluated | Becomes each element as the predicate runs |

Suppose the application has a Catalog containing a list of Products and a minimum price threshold:

~~~java
public class Catalog {
    private final List<Product> products;
    private final BigDecimal minimumPrice;

    public Catalog(
            List<Product> products,
            BigDecimal minimumPrice) {
        this.products = products;
        this.minimumPrice = minimumPrice;
    }

    public List<Product> getProducts() {
        return products;
    }

    public BigDecimal getMinimumPrice() {
        return minimumPrice;
    }
}
~~~

Products can be filtered with the expression:

~~~java
Catalog catalog =
        new Catalog(products, new BigDecimal("50.00"));

Expression expression = parser.parseExpression(
        "products.?[#this.price >= #root.minimumPrice]");

List<?> selected =
        expression.getValue(catalog, List.class);
~~~

In the predicate:

- **#this.price** reads the price of the Product being checked.
- **#root.minimumPrice** reads the threshold from the original Catalog.

When selection moves to the next Product, #this changes to that element. #root remains Catalog and does not turn into Product. As a result, the expression can combine data from the current element with configuration or properties of the root object.

If **#this.minimumPrice** were written by mistake in this example, SpEL would look for a minimumPrice property on the current Product. That is not the data the expression needs to access.

## #this changes for each element

You can think of selection as performing a separate evaluation pass for each element:

~~~text
Collection: [P1, P2, P3]
Predicate: #this.active

Evaluation 1: #this = P1 -> true
Evaluation 2: #this = P2 -> false
Evaluation 3: #this = P3 -> true

Selection result: [P1, P3]
~~~

The value of #this is not a Java variable that the application manually declares with setVariable. It is a special variable managed by SpEL in the evaluation context and updated according to the object currently being evaluated.

Therefore, there is no need to create a variable named this yourself for each element. Simply use **#this** inside the selection expression to reference the current element.

## Using #this with selection on Map

Selection also supports Map. With a Map, SpEL evaluates the condition on each entry and returns a new Map containing the entries that satisfy the predicate.

An entry has a key and a value. In a Map selection context, these two parts can be accessed via **#this.key** and **#this.value** when the corresponding accessor supports them:

~~~java
Map<String, Integer> inventory = Map.of(
        "keyboard", 12,
        "monitor", 3,
        "mouse", 25);

context.setVariable("inventory", inventory);

Expression expression = parser.parseExpression(
        "#inventory.?[#this.value >= 10]");

Map<?, ?> available =
        expression.getValue(context, Map.class);
~~~

The result retains entries whose value is at least 10, consisting of keyboard and mouse. Here, #this is the entry being checked, not the entire Map.

You can filter based on the key:

~~~text
#inventory.?[#this.key.startsWith('m')]
~~~

The expression keeps entries whose key starts with the letter m, provided the evaluation context allows calling the instance method startsWith on String. If a read-only context does not have method invocation enabled, use an appropriate context or prepare the required data in Java.

With Maps, remember that selection filters by entry. It does not turn the Map into a List of values. If you only need the list of values after filtering or want to transform the data, consider projection or processing in Java.

## #this in nested selection

A collection can contain objects where each object in turn contains another collection. When selections are nested, **#this** is updated according to the current selection context.

For example, a Department has multiple Employees. Suppose we want to select departments that have at least one active employee:

~~~java
Expression expression = parser.parseExpression(
        "departments.?["
        + "#this.employees.?[#this.active].size() > 0"
        + "]");
~~~

In the outer predicate, #this is the current Department. When SpEL enters the inner selection **employees.?[...]**, #this in the inner predicate is the current Employee. After the inner selection expression completes, the context of the outer predicate continues to be the Department under examination.

In this example, **#root** is still the initial root object. If you need to access configuration data or properties of the root object from both levels, #root is the more stable reference.

The **size()** call in the example requires an EvaluationContext that supports instance method invocation. With a default SimpleEvaluationContext configured for read-only data binding, method invocation is not enabled by default. If you do not want to enable method invocation, you can precompute the needed information in Java or use a context configured appropriately for the use case.

Nested selection easily becomes hard to read if there are many levels. When an expression has to rely on multiple #this variables at different levels, consider extracting the logic into clearly named Java methods.

## #this and selection operators

SpEL has three commonly used forms of selection:

| Syntax | Meaning | Result |
|---|---|---|
| **.?[condition]** | Select all matching elements | Collection or Map containing matching elements |
| **.^[condition]** | Select the first matching element | A single element |
| **.$[condition]** | Select the last matching element | A single element |

The #this variable has the same role as the current element inside the predicates of all these selection forms.

For example, selecting the first matching product:

~~~java
Expression firstMatch = parser.parseExpression(
        "#products.^[#this.active and #this.price >= 50]");

Product first =
        firstMatch.getValue(context, Product.class);
~~~

Selecting the last matching product:

~~~java
Expression lastMatch = parser.parseExpression(
        "#products.$[#this.active and #this.price >= 50]");

Product last =
        lastMatch.getValue(context, Product.class);
~~~

Use **.?[...]** when all results are needed; use **.^[...]** or **.$[...]** when only one element is needed according to its first or last occurrence in iteration order. If no element matches, the result of first/last selection may be null; the application needs to handle this case.

## Distinguishing selection from projection

Selection and projection both iterate over collections, but they have different purposes:

- **Selection .?[...]** filters and keeps the elements that satisfy the condition intact.
- **Projection .![...]** creates a result collection from expression values computed for each element.

For example, filtering products priced at 50 or more:

~~~text
#products.?[#this.price >= 50]
~~~

For example, getting the names of all products:

~~~text
#products.![#this.name]
~~~

Example combining the two operations:

~~~text
#products.?[#this.active].![#this.name]
~~~

The final expression selects active products and then creates a collection of names from the selected products. In the first selection, #this is the Product being examined; in the subsequent projection, #this is again the Product being transformed. The current element is always bound to the active evaluation context.

## EvaluationContext and the #this variable

**#this** is a special SpEL variable, different from application-defined variables such as **#minimumPrice**. An application can use **setVariable(...)** to put business variables into the context:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(catalog);

context.setVariable(
        "minimumPrice",
        new BigDecimal("50.00"));

Expression expression = parser.parseExpression(
        "products.?[#this.price >= #minimumPrice]");
~~~

In this expression, #this is updated by SpEL for each Product. #minimumPrice is supplied by the application and keeps the value assigned in the context.

You should not try to overwrite #this with setVariable to control the current element. The lifecycle of #this belongs to expression evaluation. If you want to pass a threshold, state, or business parameter, use a separate variable name.

## Common mistakes when using #this

- **Confusing #this with #root:** in selection, #this is the current element; #root remains the root object.
- **Using #this outside a predicate as if it were always a collection element:** outside a selection or projection context, #this reflects the current object of evaluation at that position.
- **Confusing Map with List:** when selecting on a Map, #this represents the entry being examined; you may need to access key and value.
- **Forgetting that nested selection changes #this:** inside nested selection, #this points to an element of the inner collection.
- **Using a method not permitted by the context:** calling size(), startsWith(), or other methods requires an EvaluationContext that supports instance method invocation.
- **Confusing selection with projection:** selection keeps elements that satisfy the condition; projection creates new values from each element.
- **Not handling null or empty collections:** you need to define the null policy and the case where no element matches.

When an expression parses successfully but cannot access a property or method on the current element, the error occurs during the evaluation phase. Check the actual element type, property accessors, and EvaluationContext configuration.

## When should #this be used?

#this is useful when:

- A selection predicate needs to access multiple properties of the current element.
- You want to combine element data with configuration on #root.
- Selections are nested and elements at each level need to be distinguished.
- You want the expression to explicitly show the object being checked.
- Filtering a Map by key or value through the current entry.

For simple conditions, property names can be used directly inside the predicate. When an expression has multiple levels or it is easy to confuse the root object with an element, writing #this and #root explicitly will help readers understand the data scope.

If a predicate involves many business steps, calls services, or requires complex error handling, move the filtering to a Java Stream or a dedicated method. SpEL is well suited for short declarative expressions where the current context can be clearly understood.

## Conclusion

In collection selection, **#this represents the current element being checked**. Each time the predicate is evaluated, SpEL updates #this to the corresponding element. Conversely, **#root always keeps a reference to the initial root object** throughout the entire evaluation.

Understanding these two variables properly helps write selections on Lists, arrays, and Maps, while avoiding confusion in nested selections. Use #this to access element properties, #root to fetch data from the root object, and separately named variables to pass business parameters. When expressions become deeply nested or hard to read, moving the logic to Java will make it easier to control and test.
