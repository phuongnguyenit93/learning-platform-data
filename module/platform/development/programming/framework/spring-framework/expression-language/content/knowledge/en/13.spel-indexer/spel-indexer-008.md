# Null-Safe Collection Selection and Index Access in SpEL

## 1. Why Is Null-Safe Access Needed?

Spring Expression Language (SpEL) can read elements of a List, array, or Map by index/key; it can also filter and transform elements in a collection using selection and projection. These operations frequently appear in object paths that may be uninitialized, optional data, or query results that can be null.

Starting from Spring Framework 6.2, SpEL supports null-safe operators for index access, collection selection, and projection. These syntaxes allow an expression to return null when the target collection, Map, or array itself is null.

Main forms:

| Operation | Regular Syntax | Null-Safe Syntax |
|---|---|---|
| Index access | `items[0]` | `items?.[0]` |
| Map key access | `settings['theme']` | `settings?.['theme']` |
| Selection: all matching elements | `items.?[condition]` | `items?.?[condition]` |
| Selection: first matching element | `items.^[condition]` | `items?.^[condition]` |
| Selection: last matching element | `items.$[condition]` | `items?.$[condition]` |
| Projection | `items.![expression]` | `items?.![expression]` |

The `?.` token is placed immediately after the target and before the index, selection, or projection operation. The expression inside the square brackets retains standard SpEL syntax.

## 2. Null-Safe Index Access

Index access uses square brackets to retrieve an element by position or by key. For Lists and arrays, the index is normally a 0-based integer; for Maps, the index is a key.

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("scores", Arrays.asList(72, 85, 91));

Expression expression = parser.parseExpression("#scores?.[0]");
Integer firstScore = expression.getValue(context, Integer.class);

System.out.println(firstScore); // 72
~~~

When `scores` has a value, the expression `#scores?.[0]` works like ordinary index access. When `scores` is null, the null-safe operator returns null instead of trying to get the first element from a non-existent target.

~~~java
context.setVariable("scores", null);

Object firstScore = parser.parseExpression("#scores?.[0]")
        .getValue(context);

System.out.println(firstScore); // null
~~~

The same syntax can be used with arrays:

~~~java
context.setVariable("codes", new String[] {"A-01", "B-02"});

String firstCode = parser.parseExpression("#codes?.[0]")
        .getValue(context, String.class);
~~~

And with Maps:

~~~java
Map<String, Object> settings = new HashMap<>();
settings.put("theme", "dark");
context.setVariable("settings", settings);

String theme = parser.parseExpression("#settings?.['theme']")
        .getValue(context, String.class);
~~~

Null-safe index access only handles the case where the target is null. It does not check whether the index is within bounds. If a List is empty and `[0]` is accessed, or the index exceeds the List/array size, evaluation can still fail. With a Map, a missing key usually yields null, but that differs from the target Map itself being null.

## 3. Selection: Filtering Matching Elements

Selection is used to choose elements in a collection based on a condition. The regular syntax is `.?[condition]`; the null-safe syntax is `?.?[condition]`.

Example filtering scores of 80 or higher:

~~~java
List<Integer> scores = Arrays.asList(55, 82, 91, 67);

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("scores", scores);

Expression expression =
        parser.parseExpression("#scores?.?[#this >= 80]");

List<?> passedScores = expression.getValue(context, List.class);
System.out.println(passedScores); // [82, 91]
~~~

Inside the predicate:

- `#this` is the current element being evaluated.
- `#root` still refers to the root object of the evaluation context.
- The expression after `?.?` must produce a Boolean condition to decide whether the element is retained.

If the target collection is null:

~~~java
context.setVariable("scores", null);

Object passedScores = parser.parseExpression(
        "#scores?.?[#this >= 80]").getValue(context);

System.out.println(passedScores); // null
~~~

If the target is an empty collection rather than null, selection returns an empty collection. Therefore, distinguish the two states: a null target yields null; an empty collection is processed as a collection with zero elements and yields an empty selection result.

## 4. Selection of the First Matching Element

When only the first element matching a condition is needed, use the `.^[]` operator. The null-safe form is `?.^[]`.

~~~java
List<Integer> scores = Arrays.asList(55, 82, 91, 67);

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("scores", scores);

Expression expression =
        parser.parseExpression("#scores?.^[#this >= 80]");

Integer firstPassed = expression.getValue(context, Integer.class);
System.out.println(firstPassed); // 82
~~~

SpEL iterates through the collection in its order and returns the first element satisfying the predicate. This is a single result, not a collection containing all matching elements.

If the target `scores` is null, `#scores?.^[...]` returns null. If the target is non-null but no element matches, first-selection also finds no element and returns null. Therefore, if the application needs to distinguish "collection does not exist" from "no matching element", check the target separately in Java or with an appropriate expression.

## 5. Selection of the Last Matching Element

When the last element matching a condition is needed, use the `.$[]` operator. The null-safe form is `?.$[]`.

~~~java
List<Integer> scores = Arrays.asList(55, 82, 91, 67);

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("scores", scores);

Expression expression =
        parser.parseExpression("#scores?.$[#this >= 80]");

Integer lastPassed = expression.getValue(context, Integer.class);
System.out.println(lastPassed); // 91
~~~

Both first and last selection return a single element, or null if no matching element is found. The result depends on the collection's iteration order. For collections without a deterministic order, "first" and "last" should likewise not be treated as a fixed business order.

If you need all elements matching the condition, use `?.?[]`; if you need only a single element by first/last position, use `?.^[]` or `?.$[]`.

## 6. Projection: Transforming Each Element

Projection applies an expression to each element of a collection and produces a result collection. The regular syntax is `.![expression]`; the null-safe form is `?.![expression]`.

Example doubling each score:

~~~java
List<Integer> scores = Arrays.asList(10, 20, 30);

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("scores", scores);

Expression expression =
        parser.parseExpression("#scores?.![#this * 2]");

List<?> doubled = expression.getValue(context, List.class);
System.out.println(doubled); // [20, 40, 60]
~~~

In projection, `#this` is the current element. The expression after `?.!` is evaluated once for each element and the results are placed into a new collection.

You can project properties from objects:

~~~java
public class Person {
    private String name;

    public Person(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }
}

List<Person> people = Arrays.asList(
        new Person("Lan"),
        new Person("Minh"));

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("people", people);

Expression expression =
        parser.parseExpression("#people?.![name]");

List<?> names = expression.getValue(context, List.class);
System.out.println(names); // [Lan, Minh]
~~~

If `people` is null, null-safe projection returns null. If `people` is an empty collection, projection returns an empty collection. The null-safe operator on the target does not automatically protect properties inside each element; if an element can be null or a nested property can be null, use null-safe access on that element path itself.

Example when each Person's `address` property can be null:

~~~text
#people?.![address?.city]
~~~

`?.!` protects the `people` collection; `address?.city` protects each element's `address` property.

## 7. Combining Selection and Projection

You can filter a collection first and then transform the remaining elements. For example, retrieving only the names of active people:

~~~java
Expression expression = parser.parseExpression(
        "#people?.?[active]?.![name]");
~~~

Execution steps:

1. `#people?.?` filters the collection if the target is non-null.
2. The predicate `active` is evaluated on each current element.
3. `?.!` projects the names of the selected elements.

Use a null-safe operator at each step when the previous step's result can be null. A null-safe operator only protects the target immediately preceding its operation; it does not automatically make the rest of the expression null-safe.

You can combine this with index access when you want to take an element from the filtered result:

~~~text
(#people?.?[active])?.[0]
~~~

Parentheses group the selection result before performing index access. If the initial collection is null, selection returns null and the subsequent null-safe index access also returns null. If the collection is non-null but no element matches, the selection result is an empty collection; accessing index 0 can still throw an error because there is no element at that position.

## 8. Applying to Maps, Lists, and Arrays

SpEL supports index access and selection/projection on suitable collection structures:

| Structure | Element Access | Null-Safe Example |
|---|---|---|
| List | 0-based index | `#items?.[0]` |
| Array | 0-based index | `#codes?.[1]` |
| Map | Lookup by key | `#settings?.['theme']` |
| Collection | Selection | `#items?.?[#this.active]` |
| Collection | Projection | `#items?.![#this.name]` |

With a Map, the indexer uses a key rather than a position. Selection on a Map has its own semantics because the iterated elements are entries; when writing a predicate, use the key/value access appropriate to what the expression context provides. For example, in certain cases you can access the entry value via the `value` variable or an expression corresponding to the entry being examined. Avoid mechanically applying a List predicate to a Map.

With Lists and arrays, the index is a position. Out-of-bounds access is still an error even when the target is null-safe protected. With a non-null but empty collection, selection/projection processes an empty collection; index access has no element to return.

## 9. A Null-Safe Operator Does Not Protect the Entire Access Chain

A common misconception is thinking that placing `?.` at the start of a path makes every subsequent operation safe. In reality, each null-safe operator only protects the operation immediately following it.

Example:

~~~text
#people?.[0].name
~~~

If `people` is null, `?.[0]` returns null; the subsequent `.name` part can still attempt to access a property on null and cause an error.

A safer way to write it if the first element can also be null:

~~~text
#people?.[0]?.name
~~~

Similarly, with selection/projection:

~~~text
#people?.?[active]?.![address?.city]
~~~

- `?.?` protects the root collection during selection.
- `?.!` protects the selection result if that result is null.
- `address?.city` protects the address property of each element being projected.

Break the expression down step by step and place null-safe operators at every data boundary that can be null.

## 10. Distinguishing Null, Empty Collection, and Element Not Found

These three cases have different meanings:

| State | Null-Safe Index | Multi-Element Selection | Projection |
|---|---|---|---|
| Target is null | `null` | `null` | `null` |
| Target is empty collection | Index has no element, may error | Empty collection | Empty collection |
| Target has elements but predicate does not match | Depends on requested index | Empty collection | Projection still returns results for elements |
| First/last selection finds nothing | Not applicable | `null` | Not applicable |

In particular, first-selection `?.^[]` and last-selection `?.$[]` return a single element, so when no matching element exists, the result is null. If you need a result collection, use full selection `?.?[]`.

Applications may need to handle null collections and empty collections differently. For example, null can mean "data not yet loaded", whereas an empty collection means "loaded and has no elements". Do not automatically replace null with an empty collection if the two states carry different business meanings.

## 11. Using in @Value and Spring Configuration

SpEL null-safe selection/projection/index access can be used at Spring configuration points that support expressions, such as `@Value`:

~~~java
@Component
public class ScoreSummary {
    @Value("#{scoreProvider.scores?.?[#this >= 80]}")
    private List<Integer> passedScores;
}
~~~

The example above uses a bean named `scoreProvider` and its `scores` property as the target collection. When this property is null, the null-safe selection operator returns null. For complex collection logic, injecting the data into a bean and processing it in Java is usually clearer and easier to test.

Another approach is evaluating the expression directly in Java with an `EvaluationContext`, as in the examples above. This makes the root object, variables, and result type explicit.

## 12. Spring Framework Version

Null-safe index access and null-safe collection selection/projection are capabilities added in Spring Framework 6.2. If the application is running an older version, the parser may not recognize the `?.[]`, `?.?[]`, `?.^[]`, `?.$[]`, or `?.![]` syntax forms.

When an expression reports a syntax error, check the actual Spring Framework version on the classpath, especially if the project uses Spring Boot dependency management. Do not upgrade only the `spring-expression` module to a different version from the remaining Spring modules; let the Spring Boot BOM or Spring Framework BOM manage versions consistently.

For applications that cannot upgrade yet, you can check for null in Java before evaluating the expression, or use a conditional expression compatible with the syntax supported by the running version.

## 13. Common Errors

**Placing the question mark in the wrong position**

Null-safe index is written `target?.[index]`; selection is written `target?.?[predicate]`; projection is written `target?.![expression]`. The `?.` must stand between the target and the corresponding operator.

**Thinking out-of-range indices are skipped**

Null-safe indexing only handles a null target. Indices exceeding List/array bounds can still raise an evaluation error.

**Confusing null with an empty collection**

Null-safe selection on a null target returns null. Selection on an empty collection returns an empty collection. The two results differ and can affect subsequent logic.

**Forgetting to protect subsequent steps**

`?.` does not make the entire trailing access chain automatically safe. Add further null-safe operators when subsequent elements or properties can also be null.

**Using a predicate that does not return Boolean**

Selection requires a Boolean predicate. An unsuitable condition can cause the expression to fail during evaluation.

**Confusing selection and projection**

Selection filters and retains matching elements. Projection transforms each element into a new value. `?.?[]` and `?.![]` serve different purposes.

**Using the new syntax on an older Spring version**

The null-safe forms for index, selection, and projection require Spring Framework 6.2 or later. Verify the runtime version if the parser does not recognize the syntax.

## 14. Combined Example

The following example filters passing scores, retrieves the first passing score, and transforms all scores into labels. The same context can be evaluated with either a normal collection or null:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("scores", Arrays.asList(55, 82, 91, 67));

Expression passedExpression =
        parser.parseExpression("#scores?.?[#this >= 80]");
Expression firstPassedExpression =
        parser.parseExpression("#scores?.^[#this >= 80]");
Expression labelExpression =
        parser.parseExpression("#scores?.!['Score: ' + #this]");
Expression firstExpression =
        parser.parseExpression("#scores?.[0]");

List<?> passed = passedExpression.getValue(context, List.class);
Integer firstPassed = firstPassedExpression.getValue(context, Integer.class);
List<?> labels = labelExpression.getValue(context, List.class);
Integer firstScore = firstExpression.getValue(context, Integer.class);

System.out.println(passed);      // [82, 91]
System.out.println(firstPassed); // 82
System.out.println(labels);      // [Score: 55, Score: 82, Score: 91, Score: 67]
System.out.println(firstScore);  // 55

context.setVariable("scores", null);

Object safeIndex = firstExpression.getValue(context);
Object safeSelection = passedExpression.getValue(context);
Object safeProjection = labelExpression.getValue(context);

System.out.println(safeIndex);      // null
System.out.println(safeSelection);  // null
System.out.println(safeProjection); // null
~~~

The expressions are parsed once and can be re-evaluated after updating the variable. When `scores` is null, each null-safe operation returns null. When the collection exists, index access gets an element by position, selection filters elements, first-selection gets one matching element, and projection creates a new collection.

## 15. Key Takeaways

- Null-safe index access: `target?.[index]`.
- Null-safe selection of all elements: `target?.?[predicate]`.
- Null-safe selection of first element: `target?.^[predicate]`.
- Null-safe selection of last element: `target?.$[predicate]`.
- Null-safe projection: `target?.![expression]`.
- These null-safe collection/index syntaxes require Spring Framework 6.2 or later.
- A null target returns null; an empty collection remains an empty collection; an out-of-bounds index can still error.
- A null-safe operator only protects the target immediately before the operation, so add `?.` at subsequent stages that can be null.
- Selection filters elements; projection transforms elements; first/last selection returns a single element.
- Use `#this` to refer to the current element in a predicate or projection.
