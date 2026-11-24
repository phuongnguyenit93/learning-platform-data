# Indexer for Nullable Collections in Spring Expression Language

Spring Expression Language (SpEL) uses the indexer operator [] to read an element from an array, list, or map. For example, items[0] gets the first element of a list, while settings['theme'] gets the value for the key theme in a map.

In real-world applications, a collection or map may be uninitialized and hold a null value. With a standard indexer, SpEL cannot access an element on a null object and evaluation may raise an error. Starting from Spring Framework 6.2, SpEL supports a null-safe indexer with the syntax ?.[]. This syntax allows the expression to return null when the target object being indexed is null.

A null collection must be distinguished from an empty collection: the null-safe indexer handles the case where the target object is null; it does not turn an invalid index into a null result.

## 1. Standard Indexer

An indexer places the index or key expression inside square brackets:

~~~spel
items[0]
settings['theme']
matrix[1][2]
~~~

How access works depends on the target type:

| Object | Syntax | Meaning |
|---|---|---|
| Array | scores[0] | Reads the first element |
| List | items[0] | Reads the element at index 0 |
| Map | settings['theme'] | Reads the value by key |
| Nested structure | matrix[1][2] | Reads an element in a multi-dimensional structure |

Indices for arrays and lists start at 0. For maps, the content inside square brackets is the key used for lookup.

Example:

~~~java
List<String> languages =
    Arrays.asList("Java", "Kotlin", "Scala");

Map<String, String> settings = new HashMap<>();
settings.put("theme", "dark");

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("languages", languages);
context.setVariable("settings", settings);

ExpressionParser parser = new SpelExpressionParser();

String firstLanguage =
    parser.parseExpression("#languages[0]")
          .getValue(context, String.class);

String theme =
    parser.parseExpression("#settings['theme']")
          .getValue(context, String.class);
~~~

The results are Java and dark.

## 2. The Problem When a Collection Can Be Null

In real-world applications, data often comes from APIs, databases, configuration, or conditionally constructed objects. Consequently, a property holding a collection may be uninitialized.

Example:

~~~java
List<String> tags = null;
context.setVariable("tags", tags);
~~~

If evaluating:

~~~spel
#tags[0]
~~~

SpEL has to access the first element on the value of #tags. Because the target object is null, the index operation cannot be performed and evaluation may fail.

The same situation occurs with a map:

~~~spel
#settings['theme']
~~~

If #settings is null, SpEL has no map in which to look up the key theme.

This differs from a map that exists but does not contain the requested key. A map without the key normally returns null according to the behavior of Map.get(...); whereas a null map cannot perform the index operation.

## 3. Null-Safe Indexer with the ?.[ ] Syntax

Starting from Spring Framework 6.2, SpEL supports null-safe indexing. The syntax places a question mark and a dot directly before the square brackets, with no whitespace between the dot and the opening bracket:

~~~spel
#tags?.[0]
#settings?.['theme']
#scores?.[1]
~~~

If the object preceding the indexer operator is null, the expression returns null instead of attempting to access the element.

Example:

~~~java
List<String> tags = null;

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("tags", tags);

ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("#tags?.[0]");

String firstTag =
    expression.getValue(context, String.class);

System.out.println(firstTag);
~~~

Output:

~~~text
null
~~~

In this case:

1. SpEL reads the #tags variable from the EvaluationContext.
2. The value of the variable is null.
3. The null-safe indexer operator recognizes that the target object is null.
4. SpEL returns null without performing the element-retrieval operation.

The null-safe indexer helps expressions handle optional data more cleanly and reduces the need for null checks in external Java code.

## 4. Using the Null-Safe Indexer with Lists

With a list, the expression typically retrieves an element by index:

~~~spel
#items?.[0]
~~~

If the list exists and has an element at index 0, SpEL returns that element. If the list is null, SpEL returns null.

Example:

~~~java
List<String> items =
    Arrays.asList("Spring", "SpEL");

context.setVariable("items", items);

Expression firstExpression =
    parser.parseExpression("#items?.[0]");

String first =
    firstExpression.getValue(context, String.class);
~~~

Output:

~~~text
Spring
~~~

You can use the same Expression with different variable values:

~~~java
context.setVariable("items", null);
String whenNull =
    firstExpression.getValue(context, String.class);

context.setVariable(
    "items",
    Arrays.asList("Spring", "SpEL")
);
String whenPresent =
    firstExpression.getValue(context, String.class);
~~~

The results are null and Spring, respectively.

This shows that the expression stays the same, while the return value changes according to the object provided in the context.

## 5. Using the Null-Safe Indexer with Maps

With a map, the part inside square brackets is the key:

~~~spel
#settings?.['theme']
~~~

If the map is null, the expression returns null. If the map exists, SpEL looks up the value by key.

Example:

~~~java
Map<String, String> settings = new HashMap<>();
settings.put("theme", "dark");

context.setVariable("settings", settings);

Expression themeExpression =
    parser.parseExpression("#settings?.['theme']");

String theme =
    themeExpression.getValue(context, String.class);
~~~

Output:

~~~text
dark
~~~

If the variable is changed to null:

~~~java
context.setVariable("settings", null);
~~~

the same expression returns null.

Two cases must be distinguished:

- Null map: the null-safe indexer skips the access operation and returns null.
- Existing map without the key: the lookup operation is still performed and the result is normally null according to the Map contract.

Both cases can produce null, but for different reasons.

## 6. Using the Null-Safe Indexer with Arrays

An indexer can also be used to read array elements:

~~~spel
#scores?.[0]
~~~

Example:

~~~java
Integer[] scores = null;
context.setVariable("scores", scores);

Expression scoreExpression =
    parser.parseExpression("#scores?.[0]");

Integer firstScore =
    scoreExpression.getValue(context, Integer.class);
~~~

When the array is null, the result is null. When the array has elements, SpEL returns the element at the requested index.

The null-safe indexer protects the array object when it is null. It does not change array indexing rules.

## 7. The Null-Safe Indexer Does Not Handle Empty Collections or Invalid Indices

This is a very common point of confusion.

Suppose a list exists but has no elements:

~~~java
List<String> items = Collections.emptyList();
context.setVariable("items", items);
~~~

The expression:

~~~spel
#items?.[0]
~~~

can still raise an out-of-bounds index error. The reason is that the list is not null, so SpEL proceeds with the indexer; the list simply does not have an element at position 0.

Comparison:

| Object State | Expression | Behavior |
|---|---|---|
| List is null | #items?.[0] | Returns null |
| List has elements | #items?.[0] | Returns the first element |
| Empty list | #items?.[0] | Error due to out-of-bounds index |
| List with one element, reading index 3 | #items?.[3] | Error due to out-of-bounds index |

The null-safe indexer only protects against the case where the target object is null. It does not check collection size on its own and does not turn every index error into null.

### Checking Both Null and Empty

If the application wants to receive null when a list is null or empty, check before reading the element:

~~~spel
#items != null && !#items.isEmpty() ? #items[0] : null
~~~

The logical && operator evaluates with short-circuiting. When #items is null, the right-hand side is not evaluated; when the list exists but is empty, the conditional branch returns null.

You can use a default value:

~~~spel
#items != null && !#items.isEmpty() ? #items[0] : 'N/A'
~~~

This handles both null and empty conditions according to the application's requirements.

## 8. Combining the Null-Safe Indexer with Subsequent Property Access

An element retrieved from a collection may be an object whose properties need to be read next:

~~~spel
#orders?.[0].customer.name
~~~

If #orders is null, the safe index operation returns null. However, the remainder of the expression may still be evaluated; if it continues to access customer.name on null, an error can occur.

Therefore, place the null-safe operator at every point where traversal continues through an object that can be null:

~~~spel
#orders?.[0]?.customer?.name
~~~

In this expression:

1. #orders?.[0] protects against the orders collection being null.
2. ?.customer protects against the first element being null.
3. ?.name protects against customer being null.

When a segment returns null, the next null-safe access segment keeps the result null.

This rule applies more broadly to compound expressions: use the null-safe operator at every path segment that can be null, not just at the first position.

## 9. Combining with Elvis to Provide a Default Value

If the index result can be null and the application wants to substitute a default value, you can combine the null-safe indexer with Elvis:

~~~spel
#items?.[0] ?: 'N/A'
~~~

If the list is null, the indexer returns null and Elvis chooses the string N/A. If the list has a non-null first element, the result is that element.

However, this expression still does not handle an empty list: when the list exists but has no element 0, the indexer can raise an error before Elvis is applied.

If you need to handle both null and empty, use a size-checking condition as in the previous section.

With a map, Elvis can be suitable when the map exists but the key has no value:

~~~spel
#settings?.['theme'] ?: 'light'
~~~

The expression returns theme if it has a non-null value; if the map is null or the looked-up value is null, it returns light.

## 10. Combining the Null-Safe Indexer with an Index Variable

The indexer can take an expression as the index instead of only a numeric literal:

~~~spel
#items?.[#index]
~~~

Where #index is a variable registered in the EvaluationContext.

Example:

~~~java
context.setVariable(
    "items",
    Arrays.asList("Java", "Kotlin", "Scala")
);
context.setVariable("index", 1);

Expression expression =
    parser.parseExpression("#items?.[#index]");

String language =
    expression.getValue(context, String.class);
~~~

Output:

~~~text
Kotlin
~~~

The null-safe operator protects the collection when the collection is null. The index value must still be valid for the collection at evaluation time. If the index is negative or out of bounds, an index error can still occur.

## 11. Spring Framework Versions and Compatibility

The null-safe indexer ?.[] is supported starting in Spring Framework 6.2. If the application runs an older version, the parser may not understand this syntax.

In versions without support, you can check for null before indexing:

~~~spel
#items != null ? #items[0] : null
~~~

If empty collections also need handling:

~~~spel
#items != null && !#items.isEmpty() ? #items[0] : null
~~~

When upgrading the framework or sharing expressions across multiple applications, verify the actual Spring version to choose compatible syntax.

## 12. Complete Java Example

The following example demonstrates a nullable list, using a safe indexer and providing a default value:

~~~java
List<String> labels = null;

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("labels", labels);

ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "#labels?.[0] ?: 'No label'"
);

String result =
    expression.getValue(context, String.class);

System.out.println(result);
~~~

Output:

~~~text
No label
~~~

If the null list is replaced with a list containing elements:

~~~java
context.setVariable(
    "labels",
    Arrays.asList("Primary", "Secondary")
);
~~~

re-evaluating the same Expression returns:

~~~text
Primary
~~~

The Expression is parsed once and reused; the returned value depends on the data currently present in the context.

## 13. Common Misconceptions

**Misconception 1: The null-safe indexer makes an empty list return null.**  
It only protects when the target object itself is null. An empty list still has no element at index 0.

**Misconception 2: Using ?.[] means index checking is unnecessary.**  
The index must still be valid when the collection exists.

**Misconception 3: One null-safe operator protects the entire expression.**  
In a compound expression, subsequent access segments still need null-safe operators if intermediate objects can be null.

**Misconception 4: Elvis handles all index errors automatically.**  
Elvis handles null values; it does not catch exceptions caused by out-of-bounds indices.

**Misconception 5: The null-safe indexer exists in all SpEL versions.**  
The ?.[] syntax requires Spring Framework 6.2 or later. For older versions, use conditional expressions checking null and size.

## 14. Key Takeaways

- The indexer [] reads an array/list element by index or a map element by key.
- The null-safe indexer ?.[] returns null when the target object is null.
- Null-safe indexing is supported starting from Spring Framework 6.2.
- An existing but empty collection or an out-of-bounds index can still cause an error.
- For maps, a missing key typically returns null according to map lookup behavior.
- You can combine the null-safe indexer with subsequent property access, but you must protect each path segment that can be null.
- Elvis can replace a null result with a default value, but does not catch index errors.
- If both null and empty need handling, check null and isEmpty() before reading an element.

When using indexers with optional data, clarify whether the collection can be null or empty, whether the index is valid, and whether subsequent properties can be null. Choose the appropriate protective syntax for each case so that expressions return predictable results.
