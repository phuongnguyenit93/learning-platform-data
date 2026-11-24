# Empty Lists and Empty Maps

## 1. Inline collections in SpEL

Spring Expression Language (SpEL) allows declaring Lists and Maps directly inside an expression string. This style is called an inline collection because the data is described right where it is used, without creating a collection beforehand in Java and passing it into the context.

Two basic forms:

    {1, 2, 3}                         // Inline List
    {name: 'Nikola', age: 86}         // Inline Map

SpEL also has dedicated syntax for empty collections:

    {}                                // Empty List
    {:}                               // Empty Map

These two empty expressions have different data types and cannot be used interchangeably. This is the most important point of this lesson.

## 2. Initializing a List with elements

An inline List uses curly braces with elements separated by commas:

    {1, 2, 3, 4}

When evaluated, the expression returns a Java List object containing the elements in the declared order.

Example:

    ExpressionParser parser = new SpelExpressionParser();

    List<?> numbers = (List<?>) parser
        .parseExpression("{1, 2, 3, 4}")
        .getValue();

    // numbers = [1, 2, 3, 4]

Different literals can be used:

    {'Spring', 'Boot', 'Framework'}
    {true, false, true}
    {10, 20.5, 30}

Elements in a List can be SpEL expressions. Therefore, a List can contain literal values, variables, operations, or results of calls permitted in EvaluationContext.

Example:

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("minimum", 18);

    List<?> values = (List<?>) parser
        .parseExpression("{#minimum, #minimum + 1, #minimum + 2}")
        .getValue(context);

    // values = [18, 19, 20]

SpEL evaluates each element and produces the corresponding List result.

## 3. Nested Lists

An inline List can contain other inline Lists. This is a way to represent matrix-like structures or multi-level data groups.

Example:

    {{'a', 'b'}, {'x', 'y'}}

The result is a List containing two elements, where each element is itself a List:

    [
        ['a', 'b'],
        ['x', 'y']
    ]

Elements can be retrieved using an indexer:

    {{'a', 'b'}, {'x', 'y'}}[0][1]

The result is:

    b

Indexing starts at 0. The first indexer selects the sublist at position 0; the next indexer selects the element at position 1 within that sublist.

When nesting deeply, use line breaks and indentation in the expression string for readability:

    {
        {'java', 'spring'},
        {'kotlin', 'coroutines'}
    }

Whitespace between tokens is ignored by the parser, so you can format multi-line expressions without changing the data structure.

## 4. Empty List syntax: {}

In SpEL, simply a pair of curly braces with no elements:

    {}

represents an empty List.

Example:

    Expression emptyListExpression =
        parser.parseExpression("{}");

    List<?> emptyList =
        (List<?>) emptyListExpression.getValue();

    // emptyList = []

The returned object is a List of size 0. You can check:

    emptyList.isEmpty();   // true
    emptyList.size();      // 0

An empty List is useful when an expression needs to return the same collection type across all execution branches, or when optional data has no elements yet.

Do not interpret {} as null. Null is a separate value:

    null

The two results are different:

| Expression | Value |
| --- | --- |
| {} | Empty List |
| null | null |

Therefore, checking for null and checking for an empty List are two different operations.

## 5. Initializing a Map with elements

An inline Map uses curly braces, where each entry has the form key:value. Entries are separated by commas.

Example:

    {name: 'Nikola', dob: '10-July-1856'}

The result is a Java Map with two key-value pairs:

    {
        "name": "Nikola",
        "dob": "10-July-1856"
    }

The expression can be evaluated in Java:

    Map<?, ?> inventorInfo = (Map<?, ?>) parser
        .parseExpression(
            "{name: 'Nikola', dob: '10-July-1856'}"
        )
        .getValue();

    // inventorInfo.get("name") = "Nikola"

Key names do not have to be quoted if they are valid identifiers. However, you can put keys in quotes to explicitly indicate that they are strings:

    {'name': 'Nikola', 'dob': '10-July-1856'}

If a key contains a dot, you must put the key in quotes:

    {'user.name': 'Lan'}

Here the key is a single string user.name, not a property access path user followed by name.

The value after the colon is a SpEL expression. Therefore, a Map can contain numbers, strings, booleans, null, variables, or other collections.

## 6. Empty Map syntax: {:}

SpEL uses a dedicated syntax to represent an empty Map:

    {:}

The result is a Java Map with no entries.

Example:

    Expression emptyMapExpression =
        parser.parseExpression("{:}");

    Map<?, ?> emptyMap =
        (Map<?, ?>) emptyMapExpression.getValue();

    // emptyMap = {}

You can check:

    emptyMap.isEmpty();    // true
    emptyMap.size();       // 0

An easy mistake to make is that an empty List and an empty Map both have no elements, yet their syntaxes differ:

| Data type | Inline syntax | Result type |
| --- | --- | --- |
| Empty List | {} | List |
| Empty Map | {:} | Map |
| Null value | null | null |

Do not use {} when an empty Map is needed. The parser treats {} as an empty List. Similarly, do not use {:} to represent a List.

## 7. Nested Maps

A Map can contain another Map as a value. This suits hierarchical data, such as personal information, date of birth, or address.

Example:

    {
        name: {
            first: 'Nikola',
            last: 'Tesla'
        },
        dob: {
            day: 10,
            month: 'July',
            year: 1856
        }
    }

The result is a Map with two top-level keys: name and dob. Each key points to a nested Map.

Nested values can be accessed by key:

    {
        name: {first: 'Nikola', last: 'Tesla'},
        dob: {day: 10, month: 'July', year: 1856}
    }['name']['first']

The result is:

    Nikola

Nested Maps allow representing object-like data without defining a separate Java class for every intermediate structure. However, if the data is a business model with clear rules and types, a Java class or record is usually easier to maintain than a multi-level Map.

## 8. Lists and Maps can be combined

An inline List can contain Maps, and an inline Map can contain Lists. You can combine the two structures to represent JSON-like data.

Example of a List of Maps:

    {
        {id: 1, name: 'Lan'},
        {id: 2, name: 'Minh'}
    }

This is a List with two Map elements.

Example of a Map containing a List:

    {
        team: 'Platform',
        members: {'Lan', 'Minh', 'An'}
    }

Example of a nested Map containing a List:

    {
        department: {
            name: 'Engineering',
            skills: {'Java', 'Spring', 'SQL'}
        }
    }

Data can be accessed across multiple levels:

    {
        department: {
            name: 'Engineering',
            skills: {'Java', 'Spring', 'SQL'}
        }
    }['department']['skills'][1]

The result is:

    Spring

When combining multiple levels, clearly identify whether each level is a List or a Map. Use numeric indices for Lists and keys for Maps.

## 9. Using variables and dynamic expressions in collections

Inline collections do not only hold fixed literals. Elements and values can reference variables from EvaluationContext.

Example:

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("name", "Lan");
    context.setVariable("score", 92);

    List<?> summary = (List<?>) parser
        .parseExpression("{#name, #score, #score >= 80}")
        .getValue(context);

    // summary = ["Lan", 92, true]

Map example:

    Map<?, ?> profile = (Map<?, ?>) parser
        .parseExpression(
            "{name: #name, score: #score, passed: #score >= 80}"
        )
        .getValue(context);

    // profile.get("passed") = true

This allows expressions to construct collections from runtime data. The parser builds the expression structure; when getValue is called, variables and operations are evaluated in the provided context.

If a variable has not been registered, the expression may parse successfully but evaluation will fail when that variable needs to be read.

## 10. Distinguishing inline List/Map from array construction

Curly braces also appear in array initialization syntax, but the two forms produce different result types.

Inline List:

    {1, 2, 3}

Array construction:

    new int[]{1, 2, 3}

Example:

    List<?> numbers = (List<?>) parser
        .parseExpression("{1, 2, 3}")
        .getValue();

    int[] numberArray = (int[]) parser
        .parseExpression("new int[]{1, 2, 3}")
        .getValue();

The first result is a List. The second result is an int array.

Similarly, an inline Map is a Map; it is not an arbitrary Java object or an array. Choose the syntax based on the data type that downstream code needs to receive.

## 11. Constant collections and performance

SpEL optimizes inline collections that contain only fixed values.

- If a List consists solely of fixed literals, SpEL creates a constant List to represent the expression instead of building a new List on every evaluation.
- If a Map consists solely of fixed literals or nested List/Map structures that are also constant, SpEL can create a constant Map similarly.
- If an element or value depends on a variable or runtime expression, the collection must be evaluated using the context data.

Constant examples:

    {1, 2, 3}
    {name: 'Lan', active: true}
    {name: {first: 'Nikola', last: 'Tesla'}}

Examples with runtime data:

    {#minimum, #minimum + 1}
    {name: #customerName}

Constant optimization means SpEL does not have to rebuild literal-only structures on every call. Therefore, do not assume every getValue call returns an independent collection that can be modified without affecting other evaluations.

If business logic needs a separate mutable List or Map per request, create a copy in Java before adding, removing, or modifying entries:

    List<Object> mutableCopy =
        new ArrayList<>(constantList);

    Map<Object, Object> mutableMapCopy =
        new HashMap<>(constantMap);

This ensures the mutable data lifecycle is managed explicitly in Java.

## 12. Using empty collections in application logic

Empty Lists and empty Maps are often used as default values for optional data.

Example choosing an empty List when a variable has no value:

    #members ?: {}

If members is null, Elvis selects the empty List. If members is already a List with data, that value is preserved.

Similarly, an empty Map:

    #settings ?: {:}

If settings is null, the result is an empty Map.

Make sure the type of the default value matches the type expected by downstream logic:

- Collection of elements: use {}
- Key-value map: use {:}

Do not substitute an empty List for an empty Map just because both have no elements. Code accessing Map keys and code accessing List indices behave differently.

If you need to distinguish null from an empty collection, do not use Elvis to replace null. Check directly:

    #members == null
    #members != null and #members.isEmpty()

## 13. Common errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Need a Map but got a List | Used {} instead of {:} | Use the correct empty Map syntax |
| Parse error when creating an empty Map | Missing colon in {:} | Write {:} exactly |
| Cannot access Map key | Incorrect key or wrong type | Check the key and use quotes when needed |
| Mismatched indexer | Using numeric index on a Map or key on a List | Distinguish List indices and Map keys |
| Variable not found | Did not call setVariable or wrong name | Check EvaluationContext |
| Data does not change between evaluations | Inline collection with only literals may be optimized as a constant | Create a mutable copy if updates are needed |
| Confusing empty collection with null | Used {} or {:} syntax while expecting null | Use the null literal when representing null |

When debugging, check which type the expression returns before accessing data:

    Object listValue = parser.parseExpression("{}").getValue();
    Object mapValue = parser.parseExpression("{:}").getValue();

Then check the actual type in Java:

    listValue instanceof List
    mapValue instanceof Map

This helps verify whether the parser is creating the expected collection type.

## 14. Key points to remember

- Inline Lists use {value1, value2, ...}.
- Empty Lists use {}.
- Inline Maps use {key: value, ...}.
- Empty Maps use {:}.
- {} and {:} have different result types.
- Lists and Maps can be nested or contain collections of the other type.
- Values can be literals, variables, or runtime expressions.
- Map keys do not require quotes if they are valid identifiers; keys containing dots must be enclosed in quotes.
- Collections containing only fixed literals may be optimized as constants and reused during evaluation.
- Do not assume a constant collection is a fresh mutable instance on every getValue call.
- Inline Lists/Maps differ from array construction such as new int[]{1, 2, 3}.
- Empty collections differ from null; choose the right data type for downstream logic.

When writing inline collections in SpEL, determine beforehand whether the structure to create is a List or a Map. In particular, remember the two empty syntaxes {} and {:} to avoid data type errors in subsequent processing steps.

## References

- Spring Framework Reference — Inline Lists: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/inline-lists.html
- Spring Framework Reference — Inline Maps: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/inline-maps.html
- Spring Framework Reference — Properties, Arrays, Lists, Maps, and Indexers: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/properties-arrays.html
