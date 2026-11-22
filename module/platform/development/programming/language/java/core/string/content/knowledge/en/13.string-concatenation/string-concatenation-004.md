# String.concat and Differences When Arguments Are null

In Java, there are multiple ways to concatenate strings, but **String.concat(String str)** and the **+** operator do not handle **null** the same way. This is a common source of bugs when joining names, codes, messages, or API data where one component may not have been provided.

- **"Java".concat(" 17")** returns a String with content **"Java 17"**.
- **"Java".concat(null)** throws **NullPointerException**.
- **"Java" + null** creates a String with content **"Javanull"**: the concatenation operator converts a null reference into the text **"null"**.
- If **the variable receiving the concat() call is null**, e.g., **prefix.concat(" 17")**, it also throws **NullPointerException**.
- **String.concat() does not modify the original String**: String is immutable, so the result must be used or assigned to a variable.

The difference is not merely syntactic; it also determines how an application represents missing data. The word "null" appearing in concatenated output is usually **a sign that missing data was not handled according to business policy**, not content the user naturally expects to see.

## 1. Understanding the signature of String.concat()

The String class method has the signature:

~~~java
public String concat(String str)
~~~

This is an **API signature for explanation**, not a method you need to define yourself. **str** must be a reference to a valid String; the method has no contract to convert null into text.

Basic example:

~~~java
String first = "Java";
String result = first.concat(" 17");

System.out.println(first);  // Java
System.out.println(result); // Java 17
~~~

The variable first still refers to the String with content "Java". concat() creates/returns a result value; to use the concatenated content, you must keep the return value.

If the parameter is an empty String, the content does not change:

~~~java
String value = "Java";
String result = value.concat("");

System.out.println(result);       // Java
System.out.println(value.equals(result)); // true
~~~

According to the String.concat() API, if the argument has length 0, the method returns the receiver String itself. Even so, when comparing **content**, prefer equals() rather than relying on the == operator to decide string equality.

### What happens if the argument is null?

~~~java
String text = "Hello";
String extra = null;

String result = text.concat(extra); // NullPointerException
~~~

This is an **error-demonstration snippet**. The problem is not that text is invalid: the receiver text is a normal String. It is the argument extra that fails to supply a String to concatenate; concat() neither treats null as an empty string nor writes out the word "null".

**Rule:** the argument to concat() must be a non-null String. If the data source is nullable, handle it before calling concat().

## 2. Comparing with the + and += operators

In a context where one operand is a String, the **+** operator uses Java's string concatenation mechanism. Non-String operands are converted to their String representation; for a **null reference**, the representation is **"null"**.

~~~java
String first = "Java";
String missing = null;

System.out.println(first + missing); // Javanull
System.out.println(missing + first); // nullJava
System.out.println("Value: " + missing); // Value: null
~~~

The + operator does not call **missing.concat(...)**. Therefore, having a null variable missing **does not make the string concatenation above throw NullPointerException**.

However, this does not guarantee the application handled the data properly. For instance, **"Hello null"** can be misleading when "null" actually meant there was no customer name.

### += also uses the + concatenation rules

~~~java
String message = "Hello";
String name = null;

message += " " + name;
System.out.println(message); // Hello null
~~~

The compound concatenation assignment **+=** is semantically equivalent to creating the concatenated result and reassigning the variable. It does not make String mutable and does not check for null automatically.

Comparison:

| Expression | When the reference part is null | Result |
|---|---|---|
| **"A".concat((String) null)** | null is the argument to concat | NullPointerException |
| **"A" + (String) null** | null participates in string concatenation | "Anull" |
| **(String) null + "A"** | null participates in string concatenation | "nullA" |
| **"A" + 42** | Number is converted to String | "A42" |
| **"A".concat("42")** | Argument is a valid String | "A42" |
| **"A".concat("")** | Argument is an empty String | "A" |
| **"A" + ""** | Concatenation includes an empty string | "A" |

The + operator accepts many value types when concatenating with String; concat() accepts **String**. Writing **"A".concat(42)** is a compile-time type error, whereas **"A" + 42** is valid.

### Do not confuse string concatenation with numeric addition

~~~java
System.out.println("Total: " + 1 + 2);   // Total: 12
System.out.println("Total: " + (1 + 2)); // Total: 3
~~~

A + expression is evaluated according to operand order and types. Once the process has become string concatenation, subsequent numeric operands are converted to text. Use parentheses to request arithmetic addition before concatenation.

## 3. Distinguishing null as receiver vs. null as argument

Both expressions below throw NullPointerException, though not for the same reason:

~~~java
String first = "Hello";
String missing = null;

first.concat(missing);       // Receiver exists, argument is null
missing.concat(" World");    // Receiver is null, cannot invoke instance method
~~~

On the first line, String.concat() requires a String argument but receives null. On the second line, the instance method call has no receiver object.

This matters when writing input processing:

~~~java
static String unsafeConcat(String left, String right) {
    return left.concat(right);
}
~~~

This is an **illustrative method**, meant to be placed inside a Java class. It requires **both left and right to be non-null**; checking only right is insufficient if left can be null.

Conversely, with the expression:

~~~java
static String stringifyWithPlus(String left, String right) {
    return left + right;
}
~~~

Java can produce a resulting String when one or both references are null—for example, **null + null** with two String variables yields the text **"nullnull"**. But that is merely the reference conversion rule during concatenation, not a data validation policy.

**Caution during debugging:** a concatenated string ending up as "null" does not tell you for sure whether the original element was null or the user actually entered the four letters n-u-l-l. To preserve that distinction, manage null before the text-conversion step.

## 4. Standalone Java 17+ program: observing every case

Save as file **StringConcatNullDemo.java**:

~~~java
import java.util.Objects;

public class StringConcatNullDemo {
    public static void main(String[] args) {
        String left = "Java";
        String right = null;

        System.out.println("concat-ok=" + left.concat(" 17"));
        System.out.println("plus-right-null=" + (left + right));
        System.out.println("plus-left-null=" + (right + left));

        try {
            left.concat(right);
        } catch (NullPointerException ex) {
            System.out.println("concat-null-argument=NPE");
        }

        try {
            right.concat(" 17");
        } catch (NullPointerException ex) {
            System.out.println("concat-null-receiver=NPE");
        }

        StringBuilder builder = new StringBuilder("Java");
        builder.append((String) null);
        System.out.println("builder-append-null=" + builder);

        System.out.println("fallback-empty="
                + left.concat(Objects.toString(right, "")));
        System.out.println("explicit-value-of="
                + String.valueOf((Object) right));

        String original = "J";
        original.concat("ava");
        System.out.println("ignored-result=" + original);
    }
}
~~~

Compile/run on JDK 17+:

~~~bash
javac StringConcatNullDemo.java
java StringConcatNullDemo
~~~

Exact output:

~~~text
concat-ok=Java 17
plus-right-null=Javanull
plus-left-null=nullJava
concat-null-argument=NPE
concat-null-receiver=NPE
builder-append-null=Javanull
fallback-empty=Java
explicit-value-of=null
ignored-result=J
~~~

**Line-by-line explanation:**

1. **concat-ok** is the case where both receiver and String parameter are valid.
2. **plus-right-null** and **plus-left-null** illustrate + converting a null reference to the text "null", regardless of whether it appears before or after the other string.
3. The two **...=NPE** lines appear because both NullPointerException errors are caught separately; the program does not terminate partway through.
4. **StringBuilder.append((String) null)** has its own contract and appends the text "null". That does not make String.concat(null) valid.
5. **Objects.toString(right, "")** turns null into an empty string per the specified policy, making the subsequent concat() call safe.
6. **String.valueOf((Object) right)** illustrates explicitly converting a null Object into the string "null".
7. **ignored-result=J** proves that String.concat() does not mutate an existing String object.

Printing **NPE** is text chosen by the catch block, not the full exception message generated by the JVM. The message text of NullPointerException can vary; do not depend on it when stable output is needed.

## 5. Intentional null handling: four common policies

Before concatenating nullable data, make an explicit choice: **reject**, **treat as empty**, **use a default label**, or **preserve absence**. Each policy suits different requirements.

### 5.1. Reject null if data is required

If both parts must have values:

~~~java
import java.util.Objects;

public class StrictConcatDemo {
    static String joinRequired(String left, String right) {
        Objects.requireNonNull(left, "left is required");
        Objects.requireNonNull(right, "right is required");
        return left.concat(right);
    }

    public static void main(String[] args) {
        System.out.println(joinRequired("Java", " 17"));

        try {
            joinRequired("Java", null);
        } catch (NullPointerException ex) {
            System.out.println("Missing right");
        }
    }
}
~~~

Save **StrictConcatDemo.java**, run:

~~~bash
javac StrictConcatDemo.java
java StrictConcatDemo
~~~

Output:

~~~text
Java 17
Missing right
~~~

**Advantage:** avoids silently producing "Javanull" or masking missing data. For user-supplied input, systems should usually translate the failure into an appropriate validation message rather than letting an unhandled exception propagate to the UI.

### 5.2. Treat null as an empty string

If an absent optional part is equivalent to adding nothing:

~~~java
static String appendOptional(String base, String extra) {
    if (base == null) {
        throw new IllegalArgumentException("base is required");
    }
    return base.concat(extra == null ? "" : extra);
}
~~~

This is an **illustrative method** to place inside a Java class. If base="Java" and extra=null, the result is "Java". If extra=" 17", the result is "Java 17".

Another option is **Objects.toString(extra, "")**, though using the ternary operator makes clear that extra has type String and null is replaced with an empty String.

**Do not equate null with an empty string if the business domain distinguishes those two states**, such as in partial data updates.

### 5.3. Use meaningful default text

If the UI requires a fallback label, for example for an unnamed customer:

~~~java
String customerName = null;
String shownName = customerName == null ? "(unknown)" : customerName;
String greeting = "Hello, ".concat(shownName);

System.out.println(greeting); // Hello, (unknown)
~~~

The text **"(unknown)"** is a design decision, not an automatic rule of concat(). Some applications choose "Guest", "N/A", or omit that piece of information altogether; align with product requirements and UI language.

### 5.4. Keep null as a state without concatenating prematurely

When null means “no data yet”, you can return null or a type representing absence, concatenating only when conditions are met:

~~~java
static String combineIfPresent(String left, String right) {
    if (left == null || right == null) {
        return null;
    }
    return left.concat(right);
}
~~~

This is an **illustrative method**. It differs from the policy of converting null to an empty string: missing either part makes the **entire result absent**, rather than returning the remaining part.

No single null-handling branch fits every application. What matters is having a **transparent and consistent rule**.

## 6. Differences among concat(), +, StringBuilder.append(), and String.join()

These APIs serve similar string-concatenation scenarios but **do not share identical null contracts**:

| Concatenation method | Input | Behavior with null | Use when |
|---|---|---|---|
| **left.concat(right)** | Both must be String | Null receiver or null argument → NullPointerException | Required String parts are already validated |
| **left + right** in String concatenation context | Many value types | Null reference becomes "null" | Joining a few short parts, building messages when null display is controlled |
| **StringBuilder.append((String) value)** | String value | Null String argument appends the text "null" | Building text over multiple steps; handle null beforehand if "null" is unwanted |
| **String.join(", ", elements...)** | Delimiter and String parts | Null element appends the text "null"; null delimiter throws NullPointerException | Joining a list of elements with a separator |
| **String.valueOf((Object) value)** | Object | Null Object → "null" | Converting explicitly to a textual representation |
| **Objects.toString(value, fallback)** | Object and fallback string | Null value → uses fallback | Choosing an application-defined default string |

StringBuilder example:

~~~java
StringBuilder sb = new StringBuilder("Hello");
String name = null;

sb.append(" ");
sb.append(name);
System.out.println(sb); // Hello null
~~~

**StringBuilder is not synonymous with concat()** in null policy, even though both can be used to join text. In addition, StringBuilder is **mutable**: append() alters the buffer's contents, unlike String.concat(), which returns a String without altering the original object.

**Note on overloads:** StringBuilder has multiple append() methods accepting different types. For example, **append((char[]) null)** does not have the same behavior as **append((String) null)** and can throw NullPointerException. When analyzing null behavior precisely, inspect **the parameter type and chosen overload**, not just the method name.

### Avoiding misunderstanding with String.valueOf(null)

String.valueOf() has multiple overloads, including **valueOf(Object)** and **valueOf(char[])**. Writing **String.valueOf(null)** directly can select the **char[]** overload and throw NullPointerException instead of producing the text "null".

Therefore, when you want to clearly demonstrate the rule **null Object → "null"**, use **String.valueOf((Object) null)**. Or if the goal is to replace null with an empty string or another label, use Objects.toString(value, fallback) and choose an explicit fallback.

### String.join() does not skip null elements automatically

~~~java
System.out.println(String.join(", ", "A", null, "B")); // A, null, B
~~~

If business logic requires **skipping** null elements, filter them or define handling rules before calling join(). Never assume an API silently drops null for presentation convenience.

## 7. Comparing null, "null", and empty string: a data issue, not just syntax

The following three values are distinct:

~~~java
String missing = null;
String empty = "";
String literal = "null";
~~~

- **missing**: a reference not pointing to any String.
- **empty**: an existing String of length 0.
- **literal**: a String containing the four characters n, u, l, l.

Therefore:

~~~java
System.out.println(missing == null);         // true
System.out.println("".equals(missing));      // false
System.out.println("null".equals(literal));  // true
System.out.println("null".equals(missing));  // false
~~~

After executing **"prefix" + missing**, the result contains the four letters "null" just as when concatenating **"prefix" + literal**. If only the resulting String is kept, the information of whether the original value was null is lost.

In real applications, this can lead to bugs such as:

- **Display names:** "Hello null" instead of "Hello Guest".
- **Paths:** "/users/null" creates an address that looks valid but is based on missing data.
- **Cache keys or identifiers:** a missing value and the literal text "null" collapse into the same key after conversion to String.
- **Logs and messages:** text containing "null" is insufficient to distinguish a null reference from user-entered input.

If data semantics must be preserved, **check for null before converting to text**, or store a data structure with explicit value and status.

## 8. Should you use concat() instead of + for performance optimization?

`concat()` is not inherently faster than `+`. For a few components, `+` is usually clearer in intent and modern compilers/JVMs can optimize it. For multi-step accumulation, `StringBuilder` builds the result in a mutable buffer. The lesson **Concatenation in a single expression vs. accumulation across loops** explains the trade-offs and benchmarking; here, prioritize the **null contract** when deciding whether to call `concat`.

## 9. Practical scenario analysis: building a greeting from an optional name

Suppose an API returns a customer name that may be null:

~~~java
String nameFromApi = null;
~~~

Three ways of writing it have different meanings:

~~~java
String unsafe = "Hello, " + nameFromApi;
// unsafe: "Hello, null"

String safeDisplay = "Hello, "
        + (nameFromApi == null ? "Guest" : nameFromApi);
// safeDisplay: "Hello, Guest"

// "Hello, ".concat(nameFromApi) will throw NullPointerException.
~~~

This is **illustrative code**, not three business-equivalent alternatives. If the user has an empty name or only whitespace, even checking **nameFromApi == null** is not enough. You might need:

~~~java
static String greeting(String name) {
    String display = name == null || name.isBlank()
            ? "Guest"
            : name.strip();
    return "Hello, ".concat(display);
}
~~~

This function explicitly defines: null, empty, or whitespace-only all become "Guest"; names with content are stripped on both ends via strip(). This is appropriate when **the UI contract permits** such handling. If whitespace is significant information, do not strip automatically.

The **greeting()** method above is illustrative and must be placed inside a Java class to compile.

## 10. Common mistakes to avoid

- `concat(null)` throws `NullPointerException`, whereas `"A" + (String) null` gives `"Anull"`.
- `left.concat(right)` requires **both receiver and argument** to be non-null.
- `concat()` returns a result without modifying the old string; calling it and discarding the return value does not change the variable.
- `concat(String)` does not directly accept `int` or an arbitrary object, unlike `+` in a string concatenation context.
- `String.valueOf(null)` requires considering overloads: cast `(Object) null` when you specifically need the `valueOf(Object)` contract.
- Before constructing UI text, keys, URLs, SQL, or logs, define a missing-data policy; use prepared statements for SQL and proper serializers for structured data.

**Core takeaway:** null and the text `"null"` are two different states; decide how to handle them before generating text.

## 11. Exercises and answers

Consider the following snippet:

~~~java
String a = "A";
String b = null;
String c = "";
~~~

Try answering before checking the solutions:

1. What content does **a.concat(c)** return?
2. Does **a.concat(b)** produce a result or throw an exception?
3. What is the content of **a + b**?
4. What is the content of **b + a**?
5. Does **a + c** differ in content from **a.concat(c)**?
6. If you call **b.concat(a)**, is the error cause different from question 2?
7. When should you use **Objects.toString(b, "")**?
8. If you need to distinguish null from a string containing "null", should you concatenate with + right away?

**Answers:**

1. **"A"**: concatenating an empty String adds no characters.
2. **NullPointerException**: the argument to concat() is null.
3. **"Anull"**: the + operator converts a null reference into the text "null".
4. **"nullA"**: null is also converted to "null" when it appears first.
5. **No difference in content**, both are "A"; do not rely on reference identity to compare content.
6. **Yes**: question 2 fails because of a null argument; b.concat(a) fails because of a null receiver.
7. When you **intentionally** want to treat null as an empty String before concatenating, not when business logic needs to preserve the absent state.
8. **No**, if the result must preserve real null information. Decide on a policy or keep structured data before converting to text.

**Takeaway:** **concat(null) → NullPointerException; String concatenation via + with a null reference → text "null"**. For real data, check receiver, argument, and null-handling policy before concatenating; and always use the return value of concat() because String is immutable.
