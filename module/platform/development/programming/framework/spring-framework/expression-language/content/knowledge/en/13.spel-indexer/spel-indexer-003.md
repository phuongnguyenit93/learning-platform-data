# Indexer on Strings and Character Sequences

In Spring Expression Language (SpEL), an **indexer** uses square-bracket syntax **[index]** to retrieve an element at a specific position in a data structure. For a String, the indexer returns the character at the specified position as a **String** of length one UTF-16 code unit, not a Character object.

Indices start at **0**: position 0 is the first character, position 1 is the second character, and the last position is **length - 1**. This access style is useful when an expression needs to extract a character from an identifier, perform a simple prefix or suffix check, or combine characters with other pieces of data.

## String Indexing Syntax

Basic syntax:

~~~text
someString[index]
~~~

Where **someString** is a String value accessible from the root object or a variable in the EvaluationContext; **index** is an expression that produces a valid integer index.

For example, using a variable in the context:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("text", "Spring");

Expression expression =
        parser.parseExpression("#text[0]");

String firstCharacter =
        expression.getValue(context, String.class);
~~~

The result of the expression is **"S"**. The variable **#text** references the string Spring placed into the EvaluationContext. Index **0** retrieves the first character.

You can retrieve subsequent positions:

~~~java
String second =
        parser.parseExpression("#text[1]")
                .getValue(context, String.class);

String fourth =
        parser.parseExpression("#text[3]")
                .getValue(context, String.class);
~~~

For the string Spring, the results are **"p"** and **"i"**, respectively.

## 0-Based Indexing

SpEL's indexer uses zero-based indexing, similar to how Java accesses array and String elements. For the string **"Spring"**, the position table is as follows:

| Index | Character |
|---:|:---|
| 0 | S |
| 1 | p |
| 2 | r |
| 3 | i |
| 4 | n |
| 5 | g |

Therefore:

- **#text[0]** gets the first character.
- **#text[2]** gets the third character.
- **#text[5]** gets the last character of a string with six UTF-16 code units.

There is no position 6 in this string. A valid index must fall within the range from 0 to **text.length() - 1**.

## The Indexer Returns a String, Not a Character

A common point of confusion is that Java has the **String.charAt(int)** method which returns type **char**, whereas SpEL's indexer on a String returns a **String** containing the extracted character.

~~~java
String character =
        parser.parseExpression("#text[0]")
                .getValue(context, String.class);
~~~

In this example, the result has type String and value **"S"**. If the application needs a Character or char value, convert it explicitly in Java where it is used. Do not assume that the indexer result has the same type as the value returned by String.charAt(...).

Returning a String allows the indexer result to be used directly in subsequent expressions that work with strings, such as string concatenation or calling String methods when the context permits.

## Getting a Character from a Root Object Property

The indexer does not only work with variables. It can also access a String retrieved from a root object property.

~~~java
public class Customer {
    private final String code;

    public Customer(String code) {
        this.code = code;
    }

    public String getCode() {
        return code;
    }
}
~~~

~~~java
Customer customer = new Customer("CUS-2048");

ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("code[0]");

String prefix =
        expression.getValue(customer, String.class);
~~~

In the example, **customer** is the root object. SpEL reads the **code** property, and then the indexer gets the character at position 0. The result is **"C"**.

Property access and indexing can be combined in the same expression:

~~~java
"customer.code[4]"
~~~

If customer has a code property of **CUS-2048**, the expression above retrieves the character at position 4 of the code string. This notation allows accessing nested data without creating a separate expression for each step.

## Using Expressions to Calculate the Index

The part inside square brackets is also a SpEL expression. Therefore, the index can be calculated from literals, variables, or properties:

~~~java
String character =
        parser.parseExpression("#text[1 + 2]")
                .getValue(context, String.class);
~~~

With **#text = "Spring"**, the expression gets position 3 and returns **"i"**.

If you need to get the last character, you can calculate the index from the string length:

~~~java
Expression lastCharacterExpression =
        parser.parseExpression("#text[#text.length() - 1]");

String lastCharacter =
        lastCharacterExpression.getValue(context, String.class);
~~~

This example calls the **length()** method on the String and subtracts 1 to get the last index. It requires an EvaluationContext that supports instance method invocation. With a read-only context for data binding, method invocation may not be enabled; in that case, calculate the index in Java and pass it as a variable into the context, or use a context suitable for the application's access policy.

Another approach is to provide an index variable upfront:

~~~java
context.setVariable("lastIndex", 5);

String last =
        parser.parseExpression("#text[#lastIndex]")
                .getValue(context, String.class);
~~~

This keeps the expression short and avoids calling methods on the String.

## Indexers Can Be Combined with Other String Operations

Because the indexing result is a String, you can continue using it in expressions:

~~~java
String upper =
        parser.parseExpression("#text[0].toUpperCase()")
                .getValue(context, String.class);
~~~

In the example, the indexer retrieves the first character, and then the expression calls **toUpperCase()** on the resulting String. Whether instance methods can be called depends on the EvaluationContext. If the context does not allow method invocation, perform the conversion step in Java or choose a context with an appropriate access surface.

You can use an indexer in comparison expressions:

~~~java
Boolean startsWithS =
        parser.parseExpression("#text[0] == 'S'")
                .getValue(context, Boolean.class);
~~~

The expression gets the first character and compares it with the string literal **'S'**. The result is true when the first character of text is equal to S.

If the goal is solely to check a prefix, String's **startsWith(...)** method usually expresses the intent more clearly. The indexer is suitable when you need to extract the exact character or position for further use in an expression.

## Indexing on Empty Strings and Out-of-Bounds Indices

An empty string has no characters, so it has no valid index. Likewise, negative indices or indices greater than or equal to the string length are invalid.

~~~java
context.setVariable("emptyText", "");

Expression expression =
        parser.parseExpression("#emptyText[0]");

String value = expression.getValue(context, String.class);
~~~

When evaluating the expression above, SpEL throws an error because the empty string has no element at index 0. A similar error occurs when accessing **#text[6]** on the string Spring or using a negative index.

The String indexer does not automatically return an empty string or null when the index is invalid. Check the length and index before evaluation, especially if the index comes from external input.

Example check in Java:

~~~java
if (text != null && index >= 0 && index < text.length()) {
    context.setVariable("text", text);
    context.setVariable("index", index);

    String character =
            parser.parseExpression("#text[#index]")
                    .getValue(context, String.class);
}
~~~

Validating in Java helps avoid unnecessary evaluation errors and lets the application decide how to handle an empty string or a non-existent position.

## Handling Null Strings with Null-Safe Indexing

If a String value can be null, standard indexing syntax will cause an error when attempting to access an element of null. Starting from **Spring Framework 6.2**, SpEL supports **null-safe indexing** using the **?.** operator before the square brackets:

~~~java
context.setVariable("text", null);

Expression expression =
        parser.parseExpression("#text?.[0]");

String first =
        expression.getValue(context, String.class);
~~~

When **#text** is null, the expression returns null instead of attempting to access index 0. If text is not null, SpEL performs indexing as usual.

Null-safe indexing only handles the case where the target object is null. It does not make an out-of-bounds index valid. If the string exists but is empty, **#text?.[0]** can still cause an error because index 0 does not exist.

For Spring versions prior to 6.2, this null-safe indexing syntax is not supported. When compatibility across multiple versions is required, check for null in Java or use a conditional expression compatible with the deployed SpEL version.

## Unicode, Emojis, and UTF-16 Units

A Java String is represented as a sequence of UTF-16 code units. SpEL's String indexer uses indices following Java String character access, equivalent to operating on individual UTF-16 code units rather than Unicode code points or user-perceived characters.

For regular Latin letters, each character usually occupies one UTF-16 code unit, so the index appears to match the character count. However, some Unicode characters outside the Basic Multilingual Plane, such as many emojis, are represented by **two UTF-16 code units** (a surrogate pair).

For example, the string **"A😀B"** has three Unicode code points but four UTF-16 code units:

| UTF-16 Index | Unit Content |
|---:|---|
| 0 | A |
| 1 | High surrogate of the emoji |
| 2 | Low surrogate of the emoji |
| 3 | B |

Therefore, indexing at position 1 or 2 does not return the entire emoji as a user-perceived character. It retrieves each individual UTF-16 code unit. A character cluster with combining marks can also consist of multiple code points even though the user perceives it as a single character.

If the application needs to process Unicode by code point or grapheme cluster, do not use the SpEL String indexer directly to count display characters. Process it in Java using **String.codePoints()**, **Character**, or an appropriate grapheme-handling library, and then pass the normalized result into the expression if needed.

## String Indexer Is a Read Operation

Strings in Java are immutable, so SpEL's indexer on a String only supports reading. It cannot modify characters inside the string by assigning to an index position.

~~~java
Expression expression =
        parser.parseExpression("#text[0] = 's'");
~~~

The expression above is not a valid way to replace the first character of a String. If you need to create a new string, use Java, such as constructing a new String from substrings or using StringBuilder. Changing string content should be expressed as creating a new value, not updating in place.

This differs from indexing on a List, where an element can be replaced if the collection and EvaluationContext allow writing.

## Distinguishing String Indexing from Other Structures

The same square-bracket syntax is used by SpEL for many structures, but the meaning and result type differ:

| Structure | Example | Meaning |
|---|---|---|
| String | **#text[0]** | Gets the character at the position; result is a String |
| Array | **numbers[0]** | Gets the first element of the array |
| List | **items[0]** | Gets the first element of the List |
| Map | **settings['theme']** | Gets the value by key |
| Object | **#root['name']** | Accesses a property by name if an accessor supports it |

For a String, the index must be an integer and specifies a position. For a Map, the content inside square brackets is a key; for an object, a property-name index can be handled through a property accessor. Do not confuse these rules just because they share square brackets.

## Common Errors and How to Handle Them

When using a String indexer, common errors include:

- **1-based indexing:** Java and SpEL use 0-based indexing, so the first position is 0.
- **Index exceeding length:** verify that the index is less than the length of the string.
- **Null string:** use null-safe indexing from Spring 6.2 or check for null before accessing.
- **Confusing return type:** the indexer returns a String, not a Character.
- **Confusing Unicode characters:** indices operate on UTF-16 code units, not display characters or code points.
- **Attempting to assign to a String:** Strings are immutable and the String indexer does not support writing.

If an expression parses successfully but fails when calling getValue, it is usually an evaluation error caused by invalid input data or an invalid index. You can catch **EvaluationException** in the Java layer to translate it into an appropriate business message. Avoid masking all errors by returning a default character if doing so hides information about invalid data.

## When Should You Use the String Indexer?

The String indexer is suitable when you need to retrieve a specific position from a string with a simple, validated format, for example:

- Getting the first character of a code for quick classification.
- Getting a character at a fixed position in an identifier.
- Extracting a character from a simply structured string.
- Combining a character with another condition or expression at a SpEL integration point.

If you need complex string processing, advanced Unicode handling, full-string format validation, or multi-step manipulation, write the logic in Java. Methods such as **startsWith**, **substring**, **charAt**, **codePoints**, and dedicated string-processing libraries usually express intent much more clearly than a long SpEL expression.

## Conclusion

SpEL's indexer on a String uses the syntax **string[index]**, with 0-based indexing. The result is a String containing the character at that position. The indexer can access strings from variables, the root object, or nested properties; it is read-only and will raise an error if the index is out of bounds.

When a string can be null, Spring Framework 6.2 and later support the null-safe syntax **?.[index]**. When handling emojis or complex Unicode characters, remember that String indices are based on Java's UTF-16 code units, which do not correspond one-to-one with user-perceived characters. Validate length and index before evaluating, and move complex string processing logic to Java.
