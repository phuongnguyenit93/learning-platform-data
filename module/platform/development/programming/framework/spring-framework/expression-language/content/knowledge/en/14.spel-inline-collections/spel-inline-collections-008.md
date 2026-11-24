# Accessing Elements After Creating Collections in SpEL

Spring Expression Language (SpEL) supports creating lists, maps, and arrays directly inside expressions. After creating a collection, you can use the index operator `[]` to retrieve an element by position or by key. You can access elements directly on a collection literal, on a variable/property already in EvaluationContext, or on the result of another expression.

You need to distinguish list/array indices from map keys: lists and arrays use 0-based indices, while maps use keys to look up values. When accessing nested collections, each pair of square brackets selects one level of data.

## 1. Basic index operator

General syntax:

    target[index]

Where `target` is a list, array, map, or data type supported by SpEL for indexed access; `index` is the position or key to retrieve.

Example with a list:

    {'red', 'green', 'blue'}[0]   // 'red'
    {'red', 'green', 'blue'}[1]   // 'green'
    {'red', 'green', 'blue'}[2]   // 'blue'

List indexing starts at 0. Therefore the first element is at position 0 and the second element is at position 1. An index equal to or greater than the list length will exceed the valid range.

You can store a list in a variable and then access it:

    #colors[1]

In this case, `colors` must be registered in EvaluationContext and hold a List or collection that supports indexed access.

## 2. Accessing immediately after creating an inline list

SpEL allows placing the index operator right after an inline list literal:

    {'Spring', 'Framework', 'SpEL'}[2]

The expression above returns the third element, namely `'SpEL'`. There is no need to create an intermediate variable if you only need one value at a specific position.

Example of retrieving an element from a list of status codes:

    {'NEW', 'PROCESSING', 'DONE'}[1]

The result is `'PROCESSING'`. This is a concise way to write small, fixed data used immediately at the expression site.

With an empty list `{}`, there is no valid index. Before accessing an element, ensure the collection has at least one element.

## 3. Accessing array elements

Arrays also use the index operator and 0-based indexing. You can create an array using SpEL's array creation syntax:

    new int[]{10, 20, 30}[0]
    new int[]{10, 20, 30}[2]

The first expression retrieves the value 10, and the second retrieves the value 30.

You can store an array in a Java variable and put it into the context:

    int[] levels = {1, 3, 5, 7};

    StandardEvaluationContext context =
            new StandardEvaluationContext();
    context.setVariable("levels", levels);

    ExpressionParser parser = new SpelExpressionParser();
    Object selected = parser.parseExpression("#levels[2]")
            .getValue(context);

The result is the element at index 2, namely 5. For multidimensional arrays, use multiple pairs of square brackets:

    new int[][]{{1, 2}, {3, 4}}[1][0]

The expression above takes the second row and then takes the first element of that row, resulting in 3.

## 4. Accessing values in an inline map

A Map does not use numeric positions to access elements; it uses keys. An inline map in SpEL is written as key-value pairs inside curly braces:

    {'name': 'An', 'role': 'EDITOR', 'active': true}

Use the index operator with a key to retrieve a value:

    {'name': 'An', 'role': 'EDITOR'}['name']

The result is `'An'`.

Example of retrieving another value:

    {'code': 'EXPRESS', 'fee': 25000}['fee']

The result is 25000. Using the `map['key']` syntax makes it clear that you are accessing by key. This is also convenient when the key contains special characters or is stored in a variable.

An empty map can be represented by `{:}`. A map that does not contain the requested key typically returns null for that lookup; distinguish between the case where the key does not exist and the case where the key exists but its value is null if business logic needs to differentiate those two situations.

## 5. Using variables as indices or keys

An index does not have to be a literal. You can use a variable registered in EvaluationContext:

    context.setVariable("colors", List.of("red", "green", "blue"));
    context.setVariable("position", 2);

    Object color = parser.parseExpression("#colors[#position]")
            .getValue(context);

The expression retrieves the element at the position provided by the `position` variable. This is useful when the position comes from user selection or a calculation in Java.

Similarly, a map key can be a variable:

    context.setVariable("settings",
            Map.of("language", "vi", "theme", "dark"));
    context.setVariable("settingName", "theme");

    Object theme = parser.parseExpression(
            "#settings[#settingName]"
    ).getValue(context);

The result is `'dark'`. When keys are dynamic, verify that the key belongs to an allowed set if the map contains sensitive data or has a large scope.

An index can also be an expression:

    #values[#start + 1]

SpEL evaluates the index expression first and then uses the result to access the element. For lists or arrays, the final index must be a valid integer value.

## 6. Accessing nested collections

A collection can contain other collections. In that case, each use of `[]` descends one level deeper:

    {{'A', 'B'}, {'C', 'D'}}[1][0]

The first step retrieves the sublist at position 1, namely `{'C', 'D'}`; the next step retrieves the element at position 0, resulting in `'C'`.

A map can also contain a list:

    {'scores': {8, 9, 10}}['scores'][1]

The expression retrieves the list at key `scores`, then retrieves the second element, resulting in 9.

A list can contain maps:

    {
        {'id': 101, 'name': 'Lan'},
        {'id': 102, 'name': 'Minh'}
    }[1]['name']

The expression retrieves the second map in the list, then reads the value at key `name`, resulting in `'Minh'`.

With nested data, check one level at a time. If a nested list or nested map is null, the index operation at the next level may fail.

## 7. Combining index with properties and methods

After retrieving an element, you can continue reading properties or invoking methods on that element:

    #orders[0].status
    #customers[1].getDisplayName()
    #products[0].price

The expressions above respectively take the first element and then read a property, call a method, or get the price property value of the product.

You can access an element from the result of a method:

    #orderService.findRecentOrders()[0]

The `findRecentOrders()` method is called first; then the index operator retrieves the first element in the result. This requires the method to return a collection or array that has elements.

If the method returns null or an empty collection, the subsequent index cannot retrieve an element. With methods that have side effects, consider repeated expression evaluation; a method call in an index path is still executed every time the Expression is evaluated.

## 8. Checking for null and index bounds

Before accessing an element by position, determine whether the collection is null or empty. You can use a condition:

    #items != null and #items.size() > 0
        ? #items[0]
        : null

The AND operator in SpEL short-circuits. If `#items != null` is false, the size check is not evaluated. If the collection exists but is empty, the expression returns null instead of accessing index 0.

With a dynamic position:

    #items != null and
    #position >= 0 and
    #position < #items.size()
        ? #items[#position]
        : null

This condition checks the collection, a non-negative index, and an index smaller than the size before accessing. If the index comes from external data, validate the type and bounds right at the Java layer before putting it into the context.

For arrays, use the `length` property to check the element count:

    #numbers != null and
    #position >= 0 and
    #position < #numbers.length
        ? #numbers[#position]
        : null

Do not use `size()` for arrays; `size()` is normally used with collections, whereas arrays have a `length` property.

## 9. Distinguishing index from selection and projection

The index operator `[]` retrieves a single element by position or key. It does not filter or transform the entire collection.

SpEL has dedicated collection operators:

- Selection `.?[condition]` filters elements that satisfy a condition.
- Projection `.![expression]` creates a new collection from the result of an expression applied to each element.
- Selection to get the first matching element can use `.^[condition]`; the last matching element uses `.$[condition]`.

For example, retrieving the first element by position:

    #orders[0]

Filtering paid orders:

    #orders.?[status == 'PAID']

Retrieving the list of order IDs:

    #orders.![id]

You can combine selection results with an index when needed, but account for empty collections and null before retrieving an element. Using the right operator helps the expression clearly state its intent: index to pick by position/key, selection to filter, projection to transform each element.

## 10. Complete example in Java

The following example creates a list and a map in Java, puts them into EvaluationContext, and accesses elements using SpEL:

    List<String> names = List.of("Lan", "Minh", "An");

    Map<String, Object> profile = Map.of(
            "name", "Lan",
            "scores", List.of(8, 9, 10)
    );

    StandardEvaluationContext context =
            new StandardEvaluationContext();
    context.setVariable("names", names);
    context.setVariable("profile", profile);

    ExpressionParser parser = new SpelExpressionParser();

    String secondName = parser.parseExpression("#names[1]")
            .getValue(context, String.class);

    Integer middleScore = parser.parseExpression(
            "#profile['scores'][1]"
    ).getValue(context, Integer.class);

The result `secondName` is `"Minh"`, and `middleScore` is 9. This example illustrates accessing a list by index, a map by key, and further indexing a collection retrieved from the map.

You can parse an Expression once and reuse it with different contexts if the expression does not depend on parse-time state. Evaluation still uses the current data in the passed-in context.

## 11. Common errors

- **Using an out-of-bounds index:** a list or array without an element at that position causes an evaluation error. Check the size before accessing.
- **Using a numeric index for a map:** a map requires a key, such as `#map['code']`, not an element position.
- **Confusing a key with a property:** `'name'` is a string literal; `name` is a property looked up on the current target.
- **Forgetting `#` before a variable:** variables in EvaluationContext must be referenced with `#variable`.
- **Accessing a null collection:** check the collection before calling `size()` or indexing.
- **Nested indexing on a null element:** check each collection/map level before continuing.
- **Confusing index with selection:** use `[]` to get an element by position/key; use `.?[...]` to filter.
- **Assuming every Collection has the same ordering:** indexing has positional meaning; with structures that do not guarantee ordering, choose an ordered collection or convert the data beforehand.

## 12. Takeaways

After creating an inline list, map, or array in SpEL, use `[]` to access an element right in the same expression. Lists and arrays use 0-based indices; maps use keys. An index can be a literal, variable, or expression, and can be chained multiple times to access nested collections. You can continue reading properties or invoking methods on the retrieved element. Before indexing dynamic data, check for null and position bounds; use selection or projection when the goal is to filter or transform a collection rather than retrieve a specific element.
