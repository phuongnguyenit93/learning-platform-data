# Indexers on Arrays and Lists

## Objectives

After this lesson, you can use the Spring Expression Language (SpEL) indexer to read elements in Java arrays and Lists; understand 0-based indexing; use expressions as indices; access nested structures; and update elements when the object allows writing. You will also know how to handle out-of-bounds indices, null collections, null elements, and mutability differences between arrays and types of Lists.

## 1. What is an Indexer?

An indexer is a syntax for accessing an element by position using square brackets:

~~~text
target[index]
~~~

In SpEL, an indexer can access elements of an array and a List. For example:

~~~text
#scores[0]
~~~

The expression above retrieves the first element in the #scores variable. This syntax is similar to array access in Java and calling List.get(index), but written directly inside an expression string.

Indexers are useful when a configuration rule needs to retrieve an element by position, read a property of an element, or perform calculations with data already in memory. It does not query a database on its own and does not create a new collection.

## 2. 0-Based Indexing

Java arrays and Lists both use 0-based indexing:

| Index | Position | Example with list [10, 20, 30] |
|---:|---|---:|
| 0 | First element | 10 |
| 1 | Second element | 20 |
| 2 | Third element | 30 |

Example with SpEL:

~~~text
#scores[0]
#scores[1]
#scores[2]
~~~

If a list has three elements, valid indices are 0, 1, and 2. Do not use index 1 to refer to the first element as in ordinary counting.

SpEL uses Java's indexing rules. Negative indices do not mean "counting from the end" as in some other languages. For example, #scores[-1] does not retrieve the last element; it is an invalid index.

To get the last element, use the collection size to calculate the index:

~~~text
#scores[#scores.size() - 1]
~~~

This expression is only valid when #scores is not null and has at least one element. If the list is empty, the calculated index is -1 and the access will fail.

## 3. Accessing Arrays with an Indexer

Suppose Java provides an array of scores:

~~~java
int[] scores = {75, 82, 91};

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("scores", scores);

ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("#scores[1]");

Integer secondScore =
    expression.getValue(context, Integer.class);
~~~

The result is 82 because index 1 corresponds to the second element.

Indexers work with both reference-type arrays and primitive-type arrays. For example, elements of String[], Integer[], int[], or double[] can be accessed with the same syntax.

With primitive-type arrays such as int[], Java does not store elements as Integer objects. When SpEL retrieves an element to return to the application, the value may be boxed into the corresponding wrapper type. When requesting a result type via getValue(..., Integer.class), make sure the target type matches the element.

Arrays have a fixed length. You can change the value of an element if the array is writable, but you cannot add or remove elements to change the length of the array itself.

## 4. Accessing Lists with an Indexer

Lists also use square-bracket syntax:

~~~text
#names[0]
#names[1]
~~~

Java example:

~~~java
List<String> names =
    new ArrayList<>(List.of("An", "Binh", "Chi"));

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("names", names);

ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("#names[1]");

String secondName =
    expression.getValue(context, String.class);
~~~

The result is "Binh".

Indexers keep expressions concise when you need to read an element. If you are writing Java directly, List.get(index) remains the standard API. If you are writing SpEL, #names[1] is the corresponding element access syntax.

List is an interface, so actual behavior depends on the implementation:

- ArrayList supports fast index-based access under normal conditions.
- LinkedList can still be accessed by index, but reaching distant positions may take more time.
- Unmodifiable or immutable Lists may allow reading while rejecting write operations.

When an expression is evaluated frequently, consider a collection structure suited to the access pattern. Frequent random-position access generally suits ArrayList or arrays better than LinkedList.

## 5. Using Expressions to Calculate the Index

The index inside square brackets can also be a SpEL expression. It does not have to be a hardcoded number.

For example:

~~~text
#items[#selectedIndex]
~~~

Or:

~~~text
#items[#page * #pageSize + #offset]
~~~

In the second case, SpEL calculates the index from the page number, page size, and offset before accessing the element.

You can pass the index from Java:

~~~java
context.setVariable("items", items);
context.setVariable("selectedIndex", 2);

Expression expression =
    parser.parseExpression("#items[#selectedIndex]");

Object selected = expression.getValue(context);
~~~

This approach allows reusing the same expression with different positions. The application only needs to update the variable in the context for the corresponding evaluation.

However, dynamic indices must be checked. An index that is syntactically valid can still be negative or greater than the last index of the array/List.

## 6. Accessing Properties of an Element

Indexers can be combined with the property access operator. If an element is a Java object, you can read its property right after the square brackets.

For example:

~~~text
#employees[0].name
~~~

SpEL retrieves the first employee in the list and then reads the name property.

With an order object that has a list of items:

~~~text
#order.items[1].price
~~~

The expression sequentially retrieves order, accesses items, gets the item at index 1, and reads price.

This is useful in configuration when you need to get a field from a specific element. Remember that every intermediate link must exist and have a compatible type. If order, items, or the retrieved element is null, the subsequent property access can cause an error.

## 7. Accessing Nested Structures

An array can contain other arrays, and a List can contain nested Lists. In that case, you can chain multiple indexers consecutively.

Example with a two-dimensional array:

~~~java
int[][] matrix = {
    {1, 2, 3},
    {4, 5, 6}
};

context.setVariable("matrix", matrix);
~~~

The expression:

~~~text
#matrix[1][2]
~~~

retrieves the subarray at index 1 and then gets the element at index 2. The result is 6.

With nested Lists:

~~~java
List<List<String>> groups = List.of(
    List.of("A", "B"),
    List.of("C", "D")
);

context.setVariable("groups", groups);
~~~

The expression:

~~~text
#groups[1][0]
~~~

returns "C".

Each pair of square brackets accesses one level. Each index must be valid for the specific array or List at that level. A valid index in the outer collection does not guarantee that the index in the inner collection is also valid.

## 8. Differences Between Arrays and Lists

SpEL's indexer syntax is similar, but the data structures have different characteristics:

| Characteristic | Java Array | List |
|---|---|---|
| SpEL syntax | #array[index] | #list[index] |
| First index | 0 | 0 |
| Length/size | Fixed after creation | Depends on implementation |
| Replace existing element | Yes, if the array is writable | Yes, if the List supports set |
| Add/remove elements | Cannot change array length | Yes, if the List supports add/remove |
| Element type | Has a specific component type | Can declare generic; actual type still depends on the object stored inside |
| Out-of-bounds index error | Cannot access element | Cannot access element |

Arrays are generally suitable when the number of elements is known and changes rarely. Lists are suitable when the application needs collection operations such as adding, removing, or replacing elements depending on the implementation.

The indexer only handles positional access. It does not make an array resizable, nor does it turn an immutable List into a modifiable List.

## 9. Writing or Replacing Elements

In a writable context and when the target object supports updates, an indexer can be used to set the value of an element.

Example with a modifiable List:

~~~java
List<String> names =
    new ArrayList<>(List.of("An", "Binh", "Chi"));

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("names", names);

ExpressionParser parser = new SpelExpressionParser();
Expression element = parser.parseExpression("#names[1]");

element.setValue(context, "Minh");
~~~

After this operation, the element at index 1 is replaced with "Minh". The list becomes ["An", "Minh", "Chi"].

With an array, you can reset the value of an element if the value type is compatible:

~~~java
int[] scores = {75, 82, 91};

context.setVariable("scores", scores);

Expression element = parser.parseExpression("#scores[1]");
element.setValue(context, 90);
~~~

After the operation, the array has elements 75, 90, and 91; its length remains 3.

This is a write operation to an existing element. Assigning a value at an index does not insert a new element into the middle of a List or automatically increase an array's length. To add or remove elements, use the Java collection API according to your business requirements.

If the List is immutable or does not support set, the write operation can throw an exception. With an array that has a specific component type, an incompatible value can also be rejected or cause a conversion error.

## 10. Out-of-Bounds Indices and Null Collections

An indexer requires an existing array/List and a valid index.

For example, the following accesses are invalid if a list has three elements:

~~~text
#items[3]
#items[-1]
~~~

Valid indices are 0, 1, and 2. Out-of-bounds access usually causes SpEL evaluation to fail with an index evaluation error.

If the collection itself is null, SpEL also cannot access an element:

~~~text
#items[0]
~~~

In case #items is null, it must be handled before evaluating the indexer.

If the collection can be null or empty, you can use a guard condition:

~~~text
#items != null and
#items.size() > 0 and
#items[0] != null
~~~

SpEL uses short-circuit evaluation for the and operator, so the right-hand side is only evaluated when the preceding condition is true. When you need to read the first element, check both that the collection is non-null and that it has at least one element.

If the element is at a valid index but the element itself is null, the indexer can still return null. An error only appears when the expression continues to call a method or read a property on the null element without proper handling.

## 11. Auto-Grow and Size Limits

SpEL has a configuration option for auto-growing collections via SpelParserConfiguration. When the appropriate feature is enabled, SpEL can grow a collection when an expression accesses a position beyond the current size, within the configured limit.

Configuration example:

~~~java
SpelParserConfiguration configuration =
    new SpelParserConfiguration(
        false,
        true,
        64
    );

ExpressionParser parser =
    new SpelExpressionParser(configuration);
~~~

In this form of constructor, the parameters control auto-growing null references, auto-growing collections, and the maximum auto-grow size limit, respectively.

Auto-grow is a behavior that should be enabled intentionally. It can mutate in-memory data when evaluating expressions. You should not rely on it as a substitute for index checking or input validation.

In particular, distinguish growing a collection from the fixed-length characteristic of Java arrays. If an application needs to change the size or structure of data, choose an appropriate collection model and Java API. Check the Javadoc of the Spring version in use to determine the exact auto-grow behavior supported for a given data type.

## 12. Complete Example with Both Array and List

The example below creates a context containing an array of scores and a list of names, then accesses elements using indexers:

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

public class IndexerExample {

    public static void main(String[] args) {
        int[] scores = {75, 82, 91};

        List<String> names =
            new ArrayList<>(List.of("An", "Binh", "Chi"));

        StandardEvaluationContext context =
            new StandardEvaluationContext();

        context.setVariable("scores", scores);
        context.setVariable("names", names);

        ExpressionParser parser = new SpelExpressionParser();

        Integer secondScore = parser
            .parseExpression("#scores[1]")
            .getValue(context, Integer.class);

        String firstName = parser
            .parseExpression("#names[0]")
            .getValue(context, String.class);

        System.out.println(secondScore); // 82
        System.out.println(firstName);   // An
    }
}
~~~

This example shows that the same indexer syntax can be used for arrays and Lists. The return type requested via getValue helps Java receive the result in the desired type when an appropriate conversion is possible.

In a real application, if an expression is fixed and used multiple times, you can parse the expression once and reuse the Expression object. For each evaluation, provide a context and data suitable for the application's lifecycle.

## 13. Testing Edge Cases

When testing indexers, include the following cases:

| Case | What to verify |
|---|---|
| Index 0 | Retrieves the first element correctly |
| Last valid index | Retrieves the last element correctly |
| Index equal to size | Handles out-of-bounds error |
| Negative index | Must not be interpreted as counting from the end |
| Null array or List | Cannot access element |
| Empty collection | No valid index |
| Null element | Reading the index can return null; subsequent property access needs handling |
| Immutable List | Readable, but writing can fail |
| Writing wrong type to array | Check conversion and component type |
| Nested structures | Check indices at each level |

For expressions using dynamic indices, test the minimum value, maximum value, and out-of-bounds values. If the index comes from a request or external configuration, validate it in Java before passing it into the EvaluationContext.

## 14. Key Takeaways

SpEL's indexer uses the syntax target[index] to access an array or List element. Indices start at 0; negative indices do not mean counting from the end; and every index must be valid for the structure being accessed.

You can use variables or expressions to calculate indices, combine indexers with property access, and nest multiple indexers for two-dimensional arrays or nested Lists. In writable contexts and objects, an indexer can also replace an existing element.

Arrays have a fixed length, though elements can be updated. List mutability depends on the implementation; an immutable List can reject writes. Handle null collections, empty collections, null elements, and out-of-bounds indices; only enable auto-grow when you fully understand the configuration's impact.

Use indexers for accessing elements by position in existing data. If you need to add/remove elements, query data, or orchestrate complex logic, perform that in the Java layer with the appropriate API.