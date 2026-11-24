# Negative Indices, Out-of-Bounds Indices, and Evaluation Errors

Indexers in Spring Expression Language (SpEL) use square-bracket syntax to access a position or a value by key, such as **items[0]**, **text[2]**, or **settings['theme']**. When the index or accessed data is invalid, the expression may parse successfully but raise an error during the evaluation phase.

Three cases must be distinguished: negative indices on positionally accessed structures, indices exceeding the available bounds, and missing keys in a Map. They do not have the same meaning and do not necessarily produce the same result.

## Negative Indices Do Not Access from the End

For **array**, **List**, and **String**, SpEL uses 0-based indexing following Java rules. Index 0 is the first element or character; the last index is length minus 1.

SpEL does not use negative indices according to Python's convention for counting backward from the end. For example:

~~~java
List<String> names = List.of("An", "Binh", "Chi");

StandardEvaluationContext context =
        new StandardEvaluationContext();
context.setVariable("names", names);

ExpressionParser parser = new SpelExpressionParser();

String first = parser.parseExpression("#names[0]")
        .getValue(context, String.class);

// Negative index does not mean the last element
String last = parser.parseExpression("#names[-1]")
        .getValue(context, String.class);
~~~

The expression **#names[0]** returns An. The expression **#names[-1]** does not return Chi; it causes an error when SpEL attempts to access the List with a negative index.

To get the last element, compute a valid index from the collection size or prepare an index variable in Java:

~~~java
context.setVariable("lastIndex", names.size() - 1);

String last = parser.parseExpression("#names[#lastIndex]")
        .getValue(context, String.class);
~~~

This makes it explicit that the last position depends on the collection size at evaluation time. If the collection can be empty, check before computing or using the last index.

## Negative Indices with String

String also uses 0-based indexing. A negative index does not access characters from the end of the string:

~~~java
context.setVariable("code", "SPRING");

String first = parser.parseExpression("#code[0]")
        .getValue(context, String.class);

// Not the last character of the string
String invalid = parser.parseExpression("#code[-1]")
        .getValue(context, String.class);
~~~

The first expression returns **"S"**. The second expression throws an error because a String has no negative positions.

If you want to get the last character, you can use **length() - 1** when the EvaluationContext permits calling instance methods:

~~~java
String last = parser.parseExpression(
        "#code[#code.length() - 1]")
        .getValue(context, String.class);
~~~

Or compute the index in Java and pass it into the context. The second approach is suitable when using a read-only context that does not enable method invocation.

Note that Java String indices are based on UTF-16 code units. For emojis or characters outside the Basic Multilingual Plane, one user-perceived character can occupy two UTF-16 code units. Therefore, taking the position at **length() - 1** does not necessarily capture a complete Unicode code point in every string.

## Out-of-Bounds Indices on Arrays and Lists

For an array or List, a valid index must be in the range from 0 to size minus 1. An index equal to the size or greater than the size is out of bounds.

~~~java
List<String> names = List.of("An", "Binh", "Chi");

context.setVariable("names", names);

String value = parser.parseExpression("#names[3]")
        .getValue(context, String.class);
~~~

The List has three elements, so valid indices are 0, 1, and 2. Accessing index 3 raises an evaluation error. Similarly, accessing an out-of-bounds element of an array does not return a default value.

With dynamic input data, do not assume the index is always valid. Check the size before evaluation or handle the evaluation error at an appropriate boundary.

~~~java
int index = requestedIndex;

if (index < 0 || index >= names.size()) {
    throw new IllegalArgumentException("Index is outside the list bounds");
}

context.setVariable("index", index);

String value = parser.parseExpression("#names[#index]")
        .getValue(context, String.class);
~~~

Checking in Java allows the application to return an understandable business message instead of letting an internal access error propagate outward.

## Collection Auto-Grow Can Change Behavior

SpEL has an **autoGrowCollections** option in **SpelParserConfiguration**. When enabled, certain collections can be automatically expanded if an expression accesses an index greater than the current last index. This is useful in data binding, but can be surprising if the expression is only meant for reading data.

Example configuring the parser with auto-grow and a size limit:

~~~java
SpelParserConfiguration configuration =
        new SpelParserConfiguration(
                false,  // do not auto-initialize null references
                true,   // allow auto-growing collections
                128);   // auto-grow size limit

ExpressionParser parser =
        new SpelExpressionParser(configuration);
~~~

When the collection is growable and the index is beyond the current size yet within the configured limit, SpEL can add the necessary positions. The new positions may contain null until assigned a value.

Auto-grow does not make a negative index valid. Nor is it a universal mechanism for all structures: String is immutable, arrays have fixed size, and Maps access by key rather than position. Collections that do not support resizing also cannot grow.

If expressions are read-only, consider keeping auto-grow disabled. If it must be enabled for binding, set a reasonable limit and remember that reading a large index can mutate the collection in memory.

## Auto-Grow Size Limits

Automatically growing to a very large index can consume memory and time. The **maximumAutoGrowSize** parameter limits the size to which SpEL is allowed to expand under the auto-grow mechanism.

For example, if the limit is 128, the application should not expect SpEL to expand a collection to millions of elements just because an expression requests a large index. When the limit is exceeded, evaluation can raise an error.

This limit helps control a specific parser behavior. It does not replace validating input indices, bounding overall data sizes, or managing application resources.

For expressions or inputs from users, restrict the index before putting it into the context. Do not rely solely on maximumAutoGrowSize to handle untrusted input data.

## Missing Keys in a Map Differ from Out-of-Bounds Indices

Maps are accessed by **key**, not by sequential position. Therefore, a negative key can be completely valid if the Map contains that key:

~~~java
Map<Integer, String> labels = new HashMap<>();
labels.put(-1, "Special");

context.setVariable("labels", labels);

String label = parser.parseExpression("#labels[-1]")
        .getValue(context, String.class);
~~~

In this example, **-1** is a key of the Map. It does not mean the last element. If the Map contains key -1, the expression can return the value Special.

If the key does not exist, a regular Map lookup returns null. This differs from a List or String: an out-of-bounds index on a positionally accessed structure normally throws an error, whereas a missing key in a Map can simply mean there is no value.

When a Map allows null values, distinguish a non-existent key from an existing key with a null value if the business logic needs to tell those two cases apart. You can check in Java before passing data into the expression.

## Empty Strings and Empty Collections

An empty String has length 0, an empty List has size 0, and an empty array also has no elements. There is no valid index to read from these structures.

~~~java
context.setVariable("text", "");
context.setVariable("items", Collections.emptyList());

String character =
        parser.parseExpression("#text[0]")
                .getValue(context, String.class);

String item =
        parser.parseExpression("#items[0]")
                .getValue(context, String.class);
~~~

Both expressions have no element at index 0. If a string or collection can be empty, check its length or size before accessing.

You can perform the check in Java, or prepare a Boolean variable such as **#hasItems** in the context and use it in a conditional expression. Which approach fits depends on whether the context permits the needed methods.

## Distinguishing Null from Out-of-Bounds Indices

A null object and an invalid index are two different problems:

- **Null object:** there is no object on which to perform indexing.
- **Out-of-bounds index:** the object exists, but the requested position does not exist.
- **Missing Map key:** the Map exists, but does not contain the requested key.

Starting from **Spring Framework 6.2**, SpEL supports null-safe indexing via the **?.[index]** syntax:

~~~java
context.setVariable("text", null);

String first = parser.parseExpression("#text?.[0]")
        .getValue(context, String.class);
~~~

If text is null, the expression returns null instead of attempting to access the index. However, null-safe indexing does not turn an out-of-bounds index into a valid one. If text is an empty string, **#text?.[0]** can still raise an error because position 0 does not exist.

For Spring versions prior to 6.2, this syntax is not supported. When compatibility with older versions is needed, check for null in Java before evaluation.

## Errors Occurring in the Evaluation Phase

The string **#items[10]** can parse successfully because the indexing syntax is valid. The error only appears when SpEL evaluates the expression against a collection that has no element at index 10.

You should distinguish:

- **ParseException:** the expression string has invalid syntax, such as missing brackets or a misspelled operator.
- **EvaluationException:** the expression parses successfully, but cannot be evaluated against the current root object, context, or data. Index access errors generally belong to this group and may be represented by a specific SpelEvaluationException.

Example separating the two phases:

~~~java
Expression expression;

try {
    expression = parser.parseExpression("#items[#index]");
} catch (ParseException ex) {
    throw new IllegalArgumentException("Invalid SpEL syntax", ex);
}

try {
    String item = expression.getValue(context, String.class);
} catch (EvaluationException ex) {
    throw new IllegalStateException("Cannot access indexed value", ex);
}
~~~

Separating the errors helps determine whether the problem lies in the syntax string or the actual data. When logging, record the expression identifier, the type of structure being accessed, and the validated index according to appropriate policy; avoid logging the entire object if it contains sensitive data.

## Do Not Mask Errors with Arbitrary Default Values

When an index is invalid, it can be tempting to return an empty string or a default element to avoid errors. However, replacing errors with default values can make invalid data harder to detect.

For example, if an order code must have at least six characters and an expression accesses index 5 on a short string, returning an empty string might cause the system to misclassify the code. In that case, validating length and returning a clear input error is more appropriate.

Only use a default value when it is an intentional business rule, such as a missing Map key being allowed to fall back to a default label. Do not turn every IndexOutOfBounds into null or an empty string across the board.

## Best Practices When Using Indexers

- For String, array, and List, use non-negative indices starting at 0.
- Check that the index is less than the length or size before evaluation if the data comes from external sources.
- Do not treat negative indices as a way to access from the end.
- For Maps, treat the value inside brackets as a key; negative keys can be valid.
- Only enable auto-grow when genuinely needed for data binding and set an appropriate maximumAutoGrowSize.
- Distinguish a null object, an out-of-bounds index, and a missing Map key.
- Use null-safe indexing from Spring 6.2 when you need to handle a null target object; still validate the index.
- Catch and classify evaluation errors at an appropriate boundary without masking invalid input data with arbitrary defaults.

## Conclusion

SpEL's indexer does not use negative indices to access from the end for String, array, or List. Negative indices and out-of-bounds indices generally lead to evaluation errors. Maps look up by key instead, so a negative key can be valid and a missing key usually returns null.

Collection auto-grow can expand certain collections when an index exceeds the current size, but it does not make negative indices valid and can mutate object state. Set size limits, validate indices, and clearly distinguish null from a non-existent position. When input data is untrusted, performing checks in Java before SpEL evaluation usually keeps behavior predictable and easy to diagnose.
