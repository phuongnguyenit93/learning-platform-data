# Working with map entries, keys, and values in SpEL

In Spring Expression Language (SpEL), a Map is not only a structure for looking up a value by key. SpEL can also filter entries by key or value, extract separate lists of keys/values, and transform each entry into another data structure using selection and projection.

When selection runs on a Map, the current element is a Map.Entry, so its two properties key and value can be accessed. Selection keeps matching key-value pairs and returns a Map. Projection applies an expression to each entry and returns a List of results. Understanding this difference helps choose the right operation and avoid confusing the output data shape.

## 1. Objectives and prerequisites

After this lesson, you can:

- Access a Map value by key.
- Use selection to filter a Map by key or value.
- Read the key and value of the current entry using key, value, or #this.
- Use projection to create a list of keys, values, or composite data.
- Combine selection and projection in a single expression.
- Handle null keys/values and heterogeneous data types.
- Distinguish operations on a Map from operations on entrySet(), keySet(), and values().
- Understand result element order and limits of inline operations.

You should know inline Map syntax, collection selection .?[...], projection .![...], and how to pass variables into EvaluationContext.

## 2. Map and Map.Entry structure

A Map stores data as key-value pairs. Example:

~~~java
Map<String, Integer> stock = new LinkedHashMap<>();
stock.put("BOOK", 12);
stock.put("PEN", 40);
stock.put("BAG", 5);
~~~

You can visualize the data:

| Key | Value |
|---|---:|
| BOOK | 12 |
| PEN | 40 |
| BAG | 5 |

Each pair in the Map is represented by a Map.Entry. An entry has two components:

- key: the key used to look up the entry.
- value: the data associated with the key.

When SpEL performs selection or projection on a Map, the inner expression is evaluated on the current entry. Therefore, key and value can be used directly:

~~~text
#stock.?[value > 10]
~~~

Or written explicitly:

~~~text
#stock.?[#this.value > 10]
~~~

Inside the predicate, #this represents the current Map.Entry.

## 3. Accessing a value by key

If the key is already known and you only need one value, use index syntax:

~~~text
#stock['BOOK']
~~~

When the key is in a variable:

~~~text
#stock[#requestedCode]
~~~

Java example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("#stock[#code]");

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("stock", stock);
context.setVariable("code", "PEN");

Integer quantity =
    expression.getValue(context, Integer.class);
~~~

The result is 40.

Indexing is appropriate when the lookup key is known. If you need to find multiple entries matching a condition, selection is usually more suitable.

Distinguish two cases:

- The key does not exist in the Map.
- The key exists, but its value is null.

Both can return null when read. If the application needs to distinguish them, check containsKey(key) in Java or perform a separate check before using the value.

## 4. Selection: filtering a Map by value

Selection uses the syntax .?[condition]. On a Map, the condition is evaluated on each Map.Entry.

For example, keep only items with quantity greater than 10:

~~~text
#stock.?[value > 10]
~~~

The result is a new Map containing the matching entries:

~~~text
{
    'BOOK': 12,
    'PEN': 40
}
~~~

Selection on a Map preserves the key and value of selected entries. The result still has a Map structure, not a List.

You can filter by a specific value:

~~~text
#stock.?[value == 5]
~~~

Or combine conditions:

~~~text
#stock.?[value >= 10 and key != 'PEN']
~~~

This expression keeps entries with value at least 10 and key not equal to PEN.

## 5. Selection by key

Because the current entry provides key, you can filter a Map by key content.

For example, keep only keys starting with the letter B:

~~~text
#stock.?[key.startsWith('B')]
~~~

You can use #this to clarify that startsWith is called on the entry's key:

~~~text
#stock.?[#this.key.startsWith('B')]
~~~

If key can be null, put a null check before calling the method:

~~~text
#stock.?[key != null and key.startsWith('B')]
~~~

Short-circuit AND ensures startsWith is only called when key is non-null.

Runtime Map keys do not have to be String. If a Map has numeric, enum, or custom object keys, use comparisons and methods appropriate for the actual type. Do not call startsWith on non-string keys.

## 6. Combining key and value conditions

You can filter by multiple attributes of the same entry:

~~~text
#stock.?[key.startsWith('B') and value >= 10]
~~~

The Map keeps only entries whose key starts with B and quantity is at least 10.

You can use OR:

~~~text
#stock.?[key == 'BOOK' or value == 5]
~~~

And negation:

~~~text
#stock.?[not (key == 'BAG')]
~~~

When a condition has multiple AND/OR operators, use parentheses to show logical grouping:

~~~text
#stock.?[(key == 'BOOK' or key == 'PEN') and value > 10]
~~~

This makes clear that key must be one of the two choices and value must still be greater than 10.

## 7. Projection: extracting a list of keys or values

Projection uses the syntax .![expression]. On a Map, the expression is applied to each Map.Entry and the result is a List.

Extract all keys:

~~~text
#stock.![key]
~~~

Result:

~~~text
{'BOOK', 'PEN', 'BAG'}
~~~

Extract all values:

~~~text
#stock.![value]
~~~

Result:

~~~text
{12, 40, 5}
~~~

In the two examples above, the result is a List in the entry iteration order of the source Map. Projection does not return a Map because each entry has been transformed into a single value.

You can write it explicitly with #this:

~~~text
#stock.![#this.key]
~~~

~~~text
#stock.![#this.value]
~~~

Using key and value directly is usually more concise; #this is useful when expressions have multiple levels or need to avoid ambiguity with other variables/properties.

## 8. Combining selection and projection

A common workflow is filtering entries first, then extracting keys or values of the remaining entries.

For example, retrieve keys of items with quantity greater than 10:

~~~text
#stock.?[value > 10].![key]
~~~

Steps:

1. Selection filters the Map and keeps entries with value > 10.
2. Projection runs on the resulting Map.
3. Each entry is transformed into its key.
4. The final result is a List of keys.

Retrieve values of keys starting with B:

~~~text
#stock.?[key.startsWith('B')].![value]
~~~

If you need to keep both key and value, stop after selection to receive a Map. If you need a list of keys/values for display or further processing, use projection.

## 9. Creating an output structure for each entry

Projection can create an inline Map for each entry. Example:

~~~text
#stock.![{'code': key, 'quantity': value}]
~~~

The result is a List of small Maps:

~~~text
[
    {'code': 'BOOK', 'quantity': 12},
    {'code': 'PEN', 'quantity': 40},
    {'code': 'BAG', 'quantity': 5}
]
~~~

You can compute additional fields in the values:

~~~text
#stock.![{
    'code': key,
    'quantity': value,
    'lowStock': value < 10
}]
~~~

This approach is useful when creating presentation data or a small intermediate structure. If the output has a fixed schema used in many places, consider a typed DTO in Java instead of List<Map<String, Object>>.

## 10. Handling null keys and values

A Map can contain null keys or null values depending on its implementation. Therefore, predicates should clearly reflect data types and null policies.

For example, keep only entries whose value is non-null and greater than 0:

~~~text
#stock.?[value != null and value > 0]
~~~

Due to short-circuit AND, the comparison value > 0 only runs when value is non-null.

Filter non-null keys:

~~~text
#stock.?[key != null]
~~~

If key is a String that may be null:

~~~text
#stock.?[key != null and key.startsWith('A')]
~~~

Not every Map implementation allows null keys or null values. Check the contract of the actual Map. Null-safe navigation on the Map receiver is also a separate concern: if the stock variable itself is null, normal selection cannot begin.

Spring Framework 6.2 and later supports null-safe selection and projection on collections/maps:

~~~text
#stock?.?[value != null and value > 0]
~~~

~~~text
#stock?.![key]
~~~

For versions before 6.2, check that the Map is non-null before performing selection or projection. Null-safe selection protects the Map receiver; it does not automatically fix null keys/values inside entries.

## 11. Comparing selection/projection with keySet, values, and entrySet

The Java Map API provides familiar views:

- keySet(): set of keys.
- values(): collection of values.
- entrySet(): set of Map.Entry.

In SpEL, you can invoke these methods if MethodResolver and EvaluationContext allow it:

~~~text
#stock.keySet()
~~~

~~~text
#stock.values()
~~~

~~~text
#stock.entrySet()
~~~

Usage comparison:

| Need | SpEL expression |
|---|---|
| Get value of a known key | #stock['BOOK'] |
| Filter Map by value | #stock.?[value > 10] |
| Filter Map by key | #stock.?[key.startsWith('B')] |
| Get list of keys | #stock.![key] or #stock.keySet() |
| Get list of values | #stock.![value] or #stock.values() |
| Get entry set | #stock.entrySet() |

Selection and projection are useful when you need to filter or transform via an expression. Java methods fit when code needs general collection operations or when keeping logic in Java. Method invocation also depends on permissions in the context; do not assume every method is allowed.

## 12. Result order and Map implementations

Selection returns a result Map; projection returns a result List. Iteration order depends on the source Map implementation.

- LinkedHashMap maintains insertion order.
- TreeMap maintains order according to the key comparator.
- HashMap does not guarantee a stable iteration order.

Projection preserves the iteration order of the source collection at evaluation time. If order is a business requirement, choose an appropriate Map implementation or sort the result explicitly in Java. Do not rely on the order observed from a HashMap in a single run.

Selection creates a new result Map, but values in the result can still be the same object references as in the source Map. This is not a deep copy. If a value is a mutable object, modifying that object can still affect other places holding the same reference.

## 13. Evaluating with Java and EvaluationContext

Full example:

~~~java
Map<String, Integer> stock = new LinkedHashMap<>();
stock.put("BOOK", 12);
stock.put("PEN", 40);
stock.put("BAG", 5);

ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("stock", stock);

Expression filter =
    parser.parseExpression("#stock.?[value > 10]");

Map<?, ?> filtered =
    filter.getValue(context, Map.class);

Expression keys =
    parser.parseExpression("#stock.?[value > 10].![key]");

List<?> selectedKeys =
    keys.getValue(context, List.class);
~~~

filtered is a Map keeping entries BOOK and PEN. selectedKeys is a List containing BOOK and PEN in the iteration order of LinkedHashMap.

Passing the Map via a variable separates runtime data from the expression string. There is no need to concatenate Map contents into the SpEL string.

## 14. Do selection and projection modify the source Map?

Selection and projection are used to produce a result from the source Map. They do not mean updating the source Map:

~~~text
#stock.?[value > 10]
~~~

filters entries and returns a result Map.

~~~text
#stock.![value * 2]
~~~

creates a List of doubled values; it does not write the new values back into the source Map.

However, if the inner expression calls methods with side effects or performs assignments on mutable objects, those actions can still change state. Keep predicates and projections read-only when the goal is querying data. Perform Map updates in Java with clear control flow.

## 15. Common errors and solutions

| Symptom | Common cause | Solution |
|---|---|---|
| key/value not found in predicate | Expression is not running on a Map or current context is not Map.Entry | Check source type and use #this.key/#this.value |
| Selection returns Map instead of List | Selection preserves matching entries | Use projection if a List is needed |
| Projection returns List instead of Map | Projection turns each entry into one value | Use selection if key-value pairs must be kept |
| Calling startsWith fails | Key is not String or key is null | Check null and key type first |
| Value comparison fails | Value is null or incompatible type | Check null and data type |
| Result has unexpected order | Source Map does not guarantee order | Use LinkedHashMap/TreeMap or sort in Java |
| Source Map is null | Selection/projection cannot start | Guard Map or use null-safe operator on Spring 6.2+ |
| Modifying value affects elsewhere | Value is a shared object reference | Make an appropriate copy or avoid mutation in expressions |

## 16. Practice exercises

1. Create a Map<String, Integer> containing product codes and quantities.
2. Use selection to retrieve entries with value greater than 10.
3. Filter keys starting with the letter B.
4. Retrieve the list of keys using projection.
5. Retrieve the list of values using projection.
6. Combine selection and projection to get keys of entries whose value exceeds a threshold.
7. Create a List<Map<String, Object>> from each entry with code, quantity, and lowStock.
8. Test an entry with a null value and add an appropriate guard.
9. Compare the result of .![key] with keySet().
10. Run the same expression on HashMap, LinkedHashMap, and TreeMap to observe order.
11. Test a null Map and an empty Map separately.
12. Verify that selection/projection does not write values back into the source Map.

## 17. Checklist before using Map operations

- [ ] Is the source actually a Map?
- [ ] Have you distinguished Map.Entry from standalone keys and values?
- [ ] Did you use selection when wanting to keep key-value pairs?
- [ ] Did you use projection when wanting to produce a result List?
- [ ] Does the predicate check key/value for null before calling methods or comparing?
- [ ] Do the key and value types match the operations?
- [ ] Have you determined the iteration order of the Map implementation?
- [ ] Have you distinguished a null Map from an empty Map?
- [ ] Are there any side-effect methods or assignments in predicates/projections?
- [ ] Have you tested both the result and the output data type?

## 18. Conclusion

In SpEL, selection on a Map works on each Map.Entry: key represents the key and value represents the data. Selection .?[...] keeps matching entries and returns a Map; projection .![...] transforms each entry into a result and returns a List. You can filter by key/value, extract keys or values separately, build a summary map for each entry, and combine selection with projection. Control null, data types, and iteration order, while keeping query expressions read-only. When updating a Map or handling complex processing, the Java Map API usually expresses intent more clearly.