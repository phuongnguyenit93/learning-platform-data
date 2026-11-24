# Null-Safe Indexer ?.[] and Related Null-Safe Forms

## 1. Why is null-safe indexing needed?

Spring Expression Language (SpEL) allows accessing elements of arrays, collections, Strings, Maps, and object properties using indexer syntax. For example:

    members[0]
    settings['theme']
    customer['name']

These expressions work when the object before the square brackets can be accessed. If that object is null, standard indexing can raise an evaluation error.

Starting in Spring Framework 6.2, SpEL supports the null-safe index operator with the syntax:

    target?.[index]

Example:

    members?.[0]

If members is null, the expression returns null instead of throwing a NullPointerException. If members exists, SpEL performs indexing normally.

The null-safe indexer is especially useful when data has a nested structure, a collection may not be initialized yet, or a key may reference a nonexistent object.

## 2. Syntax and semantics of ?.[]

General syntax:

    expression?.[indexExpression]

Where:

- expression is the object or structure to access.
- ?. is the marker requesting safe indexing when the receiver is null.
- indexExpression is the index or key used to retrieve the element.

Example with List:

    members?.[0]

Example with Map:

    settings?.['theme']

Example with String:

    title?.[0]

Example with an object accessed by property name:

    customer?.['name']

When the receiver is null, the null-safe indexer returns null. When the receiver is non-null, SpEL continues processing the indexer according to the data type and provided index.

Remember that ?. precedes the square brackets. The valid form is:

    members?.[0]

Do not write:

    members?[0]

or:

    members[?.0]

This is a SpEL-specific syntax, not standard Java indexer syntax.

## 3. Supported structures

SpEL supports indexing across many types of structures. The indexer can access elements by position, key, or property name depending on the data type.

| Structure | Example | Meaning |
| --- | --- | --- |
| Array | colors?.[0] | First element |
| List | members?.[0] | First element |
| Ordered collection | items?.[2] | Element at index position |
| String | title?.[0] | Character at index position, returned as String |
| Map | settings?.['theme'] | Value for key theme |
| Object | customer?.['name'] | Property name of the object |
| Custom structure | payload?.['id'] | Element via registered IndexAccessor |

Numeric indexes for arrays, Lists, and Strings start at 0, following common Java indexing conventions.

For a Map, the part inside brackets is the key. The key type must match the actual Map.

For an object, the indexer can take the property name as a string. Whether the property can be read depends on the property accessor provided by the EvaluationContext.

Starting in Spring Framework 6.2, applications can also register an IndexAccessor to support indexing on custom data structures. The null-safe indexer can be used with structures for which the EvaluationContext has a corresponding accessor.

## 4. Example with List and root object

Suppose there is a Society class containing a list of members:

    public class Society {
        private List<Inventor> members;

        public List<Inventor> getMembers() {
            return members;
        }

        public void setMembers(List<Inventor> members) {
            this.members = members;
        }
    }

You can use SpEL to get the first member:

    ExpressionParser parser = new SpelExpressionParser();

    Society society = new Society();
    society.setMembers(
        List.of(new Inventor("Nikola Tesla"))
    );

    StandardEvaluationContext context =
        new StandardEvaluationContext(society);

    Expression expression =
        parser.parseExpression("members?.[0]");

    Inventor first =
        expression.getValue(context, Inventor.class);

When members has data, the result is the element at position 0.

If the list has not been initialized:

    society.setMembers(null);

    Inventor first =
        expression.getValue(context, Inventor.class);

The result is null. The null-safe indexer prevents an error simply because members is null.

This example uses members as a property of the root object society. If the list is placed in a variable, you can write:

    #members?.[0]

and supply members to EvaluationContext via setVariable.

## 5. Example with Map

A Map indexer uses a key to retrieve a value.

    Map<String, Object> settings = new HashMap<>();
    settings.put("theme", "dark");

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("settings", settings);

    Expression expression =
        parser.parseExpression("#settings?.['theme']");

    String theme =
        expression.getValue(context, String.class);

The result is:

    dark

If settings is null:

    context.setVariable("settings", null);

then the same expression returns null.

The null-safe indexer only protects the receiver settings when it is null. It does not automatically replace a nonexistent key with a default value. For a standard Map, a nonexistent key normally returns null; you can combine Elvis if a default is desired:

    #settings?.['theme'] ?: 'light'

If settings is null or the theme value is null or an empty string, the expression above returns light. If theme is a non-empty string, that value is kept.

## 6. Null-safe indexing does not ignore invalid indexes

The null-safe indexer addresses the case where the receiver is null. It does not turn every indexing error into null.

Example:

    members?.[0]

If members is null, the result is null.

If members is an empty List, the receiver is not null, yet there is no element at index 0. Indexing can still raise an out-of-bounds error.

Similarly, for a non-empty array, List, or String when the index is out of bounds, the null-safe operator does not handle that error automatically.

| Situation | Expected result |
| --- | --- |
| Receiver is null | Returns null |
| Receiver has element at index | Returns the element |
| Empty List, accessing index 0 | Can raise an out-of-range index error |
| Negative or out-of-bounds index | Can raise an out-of-range index error |
| Map lacks key | Usually returns null per Map behavior |
| Retrieved element is null | Indexer result is null; subsequent access step must be protected separately |

If you need to check both null and empty collections, use an explicit condition:

    #members != null and !#members.isEmpty()
        ? #members[0]
        : null

The null check comes first. Thanks to short-circuit AND, SpEL does not call isEmpty() when members is null.

For arrays, Strings, Maps, or custom structures, write conditions suited to their respective data types.

## 7. Combining with property navigation

Null-safe indexing is often just one step in an object access path.

Example:

    members?.[0].name

This expression protects the indexing operation when members is null. However, if the first element is null, the subsequent .name access can still fail.

Safer form:

    members?.[0]?.name

In this expression:

1. If members is null, the null-safe indexer returns null.
2. If the first element is null, null-safe property navigation returns null.
3. If both exist, SpEL reads the name property.

Multi-layer example:

    #society?.members?.[0]?.placeOfBirth?.city

Each ?. protects the receiver of the operation immediately following it. This pattern is suitable when any intermediate object can be null.

Do not assume that a single null-safe operator at the start of a chain automatically makes the entire remainder safe.

## 8. Important rule for compound expressions

In SpEL, when a null-safe operation returns null inside a compound expression, the rest of the compound expression continues to be evaluated.

Example:

    #person?.address.city

If person is null, accessing address returns null. SpEL then continues with .city. Because the receiver of .city is null and this step is not null-safe, the expression can throw a NullPointerException.

Safe form:

    #person?.address?.city

The same rule applies to indexers:

    #person?.orders?.[0]?.items?.[0]?.name

Every step that can receive a null receiver must be protected individually if the goal is for the whole expression to return null instead of throwing an error.

This is the most important point when combining the null-safe indexer with property access, method invocation, or other indexers.

## 9. Null-safe selection and projection

In addition to the indexer, SpEL also has null-safe operators for collection selection and projection.

Common forms:

| Operation | Standard syntax | Null-safe syntax |
| --- | --- | --- |
| Select all matching elements | members.?[condition] | members?.?[condition] |
| Select first matching element | members.^[condition] | members?.^[condition] |
| Select last matching element | members.$[condition] | members?.$[condition] |
| Projection | members.![expression] | members?.![expression] |

These null-safe operators allow performing selection or projection when the collection may be null.

### Null-safe selection

Selection filters elements satisfying a condition:

    members?.?[nationality == 'Serbian']

If members is null, the result is null. If members exists, SpEL filters matching elements and returns the resulting collection.

Example with a variable:

    List<Inventor> serbians =
        parser.parseExpression(
            "#members?.?[nationality == 'Serbian']"
        ).getValue(context, List.class);

### Null-safe select first and select last

To get the first element matching a condition:

    members?.^[nationality == 'Serbian']

To get the last element matching a condition:

    members?.$[nationality == 'Serbian']

If the source collection is null, both null-safe expressions return null. If the collection exists but no element matches the condition, the selection result can also be null.

### Null-safe projection

Projection transforms each element into a value or property:

    members?.![placeOfBirth.city]

If members is null, the result is null. If the collection exists, SpEL applies the projection expression to each element and returns the resulting collection.

Null-safe projection only protects the source collection. If an element's placeOfBirth can be null, continue using null-safe navigation inside the projection:

    members?.![placeOfBirth?.city]

This avoids confusing a null source collection with a null property inside an individual element.

## 10. Null source differs from an empty collection

A null-safe operator does not convert a null collection into an empty collection.

Example:

    #members?.?[active == true]

If members is null, the result is null.

If members is an empty collection, selection runs on the empty collection and returns an empty collection.

Similarly, projection on an empty collection returns an empty result collection. Select first or select last on a collection with no matching elements returns null.

This distinction is important when downstream code checks collection size:

- null indicates there is no source collection.
- an empty collection indicates the source exists but contains no elements.
- null-safe selection/projection preserves that distinction.

If business logic wants to turn null into an empty collection, use Elvis with an appropriately constructed empty collection or normalize the data before evaluation.

## 11. Spring Framework version

Null-safe indexing is supported starting in Spring Framework 6.2.

Syntax:

    members?.[0]

Do not assume this expression runs on older Spring Framework versions. If the application uses a version prior to 6.2, verify the actual version before using it.

For versions that do not yet support the null-safe indexer, you can use a ternary condition to check the receiver first:

    #members != null and !#members.isEmpty()
        ? #members[0]
        : null

The fallback must match the structure type and index-check requirements. Checking only for null is insufficient if the collection can be empty.

Null-safe selection and projection forms are also described in current SpEL documentation. Cross-check the documentation for the exact Spring Framework version your application runs.

## 12. Common errors and debugging

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Parse error at ?.[] | Spring Framework does not yet support the syntax or expression is malformed | Check version and target?.[index] syntax |
| NullPointerException after indexer | Subsequent property/method step is not null-safe | Use ?. at every receiver that may be null |
| Index out of bounds | Receiver exists but index is invalid | Check size or index bounds |
| Unexpected null result | Receiver is null, key does not exist, or retrieved element is null | Inspect each step along the path |
| Selection returns null instead of empty collection | Source collection is null | Normalize null to empty collection if business rules require |
| Projection fails | Property inside an element is null | Use null-safe navigation inside the projection expression |
| Custom structure cannot be indexed | Missing suitable IndexAccessor | Register accessor in EvaluationContext |

When debugging, split the expression step by step:

    #members
    #members?.[0]
    #members?.[0]?.name

Evaluating step by step helps identify which receiver is null, whether the index is valid, and which property causes the failure.

Do not look only at the final result. An expression can return null because the receiver is null, a key does not exist, or an element is null; those cases carry different business meanings.

## 13. Key points to remember

- The null-safe indexer has the syntax target?.[index].
- Null-safe indexing is supported starting in Spring Framework 6.2.
- The indexer can access arrays, collections, Strings, Maps, objects, and custom structures with an appropriate IndexAccessor.
- Numeric indexes start at 0.
- A null receiver returns null; an existing receiver with an invalid index can still raise an error.
- The null-safe indexer does not automatically protect properties or methods accessed afterward.
- Use ?. at every step that can receive a null receiver in compound expressions.
- Null-safe selection, select first, select last, and projection use ?.?, ?.^, ?.$, and ?.! respectively.
- A null collection differs from an empty collection; null-safe operators do not automatically convert null into an empty collection.
- When debugging, check the version, receiver, index, retrieved element, and each subsequent access step.

Use the null-safe indexer to handle cases where the source structure may be null, while still checking indexes and inner data according to business rules. Null-safe navigation prevents null access errors at the marked operation; it does not replace validation for the entire object graph.

## References

- Spring Framework Reference — Safe Navigation Operator: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-safe-navigation.html
- Spring Framework Reference — Properties, Arrays, Lists, Maps, and Indexers: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/properties-arrays.html
- Spring Framework Javadoc — Indexer: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/ast/Indexer.html
