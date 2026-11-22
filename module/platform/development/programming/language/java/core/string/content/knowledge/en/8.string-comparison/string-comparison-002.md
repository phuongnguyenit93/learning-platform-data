# String.equals with null and Non-String Objects

In Java, **String.equals(Object)** checks whether the argument is a **String with the same content** as the calling String. The two most easily confused situations are passing **null** and passing **an object of a type other than String**:

- A non-null String calling **equals(null)** always returns **false**, without throwing an exception.
- A non-null String calling **equals(non-String object)** always returns **false**, even if that object can print the exact same text as the String.
- If the **variable before the dot is null**, calling **variable.equals(...)** throws **NullPointerException** before String.equals() ever gets a chance to run.

Distinguishing a **null argument** from a **null receiving object** is key to reading results accurately and writing safe comparison conditions.

## 1. Signature and Comparison Principles

String provides the method:

~~~java
public boolean equals(Object anObject)
~~~

This is an **illustrative API signature**, not a new method declaration that learners need to add to a class. The method takes an Object parameter, yet **String.equals() only considers content equal when the argument is actually a String object**. It does not automatically convert Integer, StringBuilder, char[], or any other type into a String for comparison.

For the String object invoking the method:

1. If both references point to the same String, the result is true.
2. If the argument is a different String object with the same sequence of UTF-16 code units, the result is still true.
3. If the argument is null, the result is false.
4. If the argument is not a String, the result is false.
5. If both are Strings with different content, the result is false.

**equals() compares content values; the == operator compares reference identity** when both operands are reference types. These are two distinct checks.

~~~java
String first = new String("Java");
String second = new String("Java");

System.out.println(first == second);      // false
System.out.println(first.equals(second)); // true
~~~

The two `new` statements create two distinct String objects, so == is false. The content "Java" matches, so equals() is true.

## 2. Passing null to String.equals(): Returns false

Example:

~~~java
String language = "Java";
String missing = null;

System.out.println(language.equals(null));    // false
System.out.println(language.equals(missing)); // false
System.out.println("Java".equals(null));      // false
~~~

**Why is NullPointerException not thrown?** The object on the calling side (language or the literal "Java") exists. Java executes String.equals(), and the method determines that null is not a String object with equal content.

Compare that with calling it the other way around:

~~~java
String missing = null;
System.out.println(missing.equals("Java")); // Throws NullPointerException
~~~

The snippet above is an **error illustration**, not code to be run alongside the examples printing outputs earlier. Attempting to access a method through missing has no receiving object because missing is null. This is an error on the **receiver** (the object receiving the call), not because equals() "rejects null".

Keep in mind:

| Expression | Result | Reason |
|---|---|---|
| "Java".equals(null) | false | Receiver is a valid String; argument is null |
| "Java".equals("Java") | true | Content is equal |
| "Java".equals("java") | false | Case-sensitive |
| ((String) null).equals("Java") | NullPointerException | Receiver is null |
| null == null | true | == allows comparing two null references |
| "Java" == null | false | Non-null String reference |

**Do not use null.equals(...) directly:** the null keyword is not a valid receiver expression for a method call; the real runtime scenario is a reference variable whose value is null, such as missing.equals(...).

## 3. Passing a Non-String Object: Always false

Because the signature accepts Object, the compiler allows passing many kinds of arguments. However, String.equals() **does not implicitly cast to String**, does not call toString() and then compare, and does not compare "two objects that display identically" if the other object is not a String.

Example:

~~~java
String text = "42";
Integer number = 42;

System.out.println(text.equals(number)); // false
~~~

Even though number.toString() produces "42", number is an Integer, so text.equals(number) is false.

Similarly:

~~~java
String text = "Java";
StringBuilder builder = new StringBuilder("Java");

System.out.println(text.equals(builder));            // false
System.out.println(text.equals(builder.toString())); // true
~~~

StringBuilder displays "Java" as its content, yet it is **not a String**. toString() creates a new String, at which point String.equals() can compare the content.

### Table of Different Argument Types

Assume the receiver is always **"Java"**:

| Argument | Runtime Argument Type | equals() Result |
|---|---|---|
| "Java" | String | true |
| new String("Java") | String | true |
| "java" | String | false |
| null | null | false |
| new StringBuilder("Java") | StringBuilder | false |
| new StringBuffer("Java") | StringBuffer | false |
| new char[] {'J', 'a', 'v', 'a'} | char[] | false |
| Integer.valueOf(123) | Integer | false |
| new Object() | Object | false |

If you **intentionally** need to compare String content with another CharSequence, you can consider **String.contentEquals(CharSequence)**. For example:

~~~java
String text = "Java";
StringBuilder builder = new StringBuilder("Java");

System.out.println(text.equals(builder));        // false
System.out.println(text.contentEquals(builder)); // true
~~~

The two methods return different results because they have **different comparison contracts**: equals() only accepts a String with the same content, whereas contentEquals() is designed to compare content against a CharSequence. You should not blindly replace equals() with contentEquals() everywhere, because data-type comparison requirements may differ.

## 4. Declared Type Object Does Not Decide the Result: Actual Type Matters

A variable declared as **Object** can still point to a String. In that case, when it is passed to String.equals(), the method checks the **actual runtime object**, not merely the declared type.

~~~java
String expected = "Java";

Object stringValue = new String("Java");
Object builderValue = new StringBuilder("Java");
Object nullValue = null;

System.out.println(expected.equals(stringValue));  // true
System.out.println(expected.equals(builderValue)); // false
System.out.println(expected.equals(nullValue));    // false
~~~

On the first line, stringValue has variable type Object, but its actual value is a String containing "Java", so the result is true. The second line references a StringBuilder, so it is false. The last line is null, also false.

**Do not infer that an Object parameter means all types are converted to String.** Object is a broad parameter type; the specific logic inside String.equals() decides what counts as equal.

## 5. When the Receiver Can Be `null`: Choose the Right Call Pattern

If you need to check against a fixed status, call `equals()` on the literal. If you want to call it on a variable, use `&&` to ensure the variable is non-`null` before calling:

~~~java
String status = null;
System.out.println("ACTIVE".equals(status)); // false
System.out.println(status != null && status.equals("ACTIVE")); // false
~~~

For **two** references that can both be `null`, `Objects.equals(left, right)` returns `true` if both are `null`, returns `false` if only one side is `null`, and calls `left.equals(right)` when `left` is non-`null`. If two unprovided values must not be treated as equal in your business logic, check presence separately.

The next article fully explains `Objects.equals` across Strings, arrays, and custom classes. Here, the distinction to remember is a **`null` argument** versus a **`null` receiver** for `String.equals(Object)` itself.

## 6. Standalone Java 17+ Program

The program below brings together null, non-String arguments, Object-typed variables, Objects.equals(), and safe comparison patterns.

Save as **StringEqualsNullAndTypeDemo.java**:

~~~java
import java.util.Objects;

public class StringEqualsNullAndTypeDemo {
    public static void main(String[] args) {
        String value = "Java";
        String missing = null;

        Object stringAsObject = new String("Java");
        Object builder = new StringBuilder("Java");
        Object number = Integer.valueOf(42);

        System.out.println("literal-null=" + "Java".equals(null));
        System.out.println("value-null=" + value.equals(missing));
        System.out.println("safe-constant=" + "Java".equals(missing));

        System.out.println("object-string=" + value.equals(stringAsObject));
        System.out.println("object-builder=" + value.equals(builder));
        System.out.println("object-number=" + "42".equals(number));

        System.out.println("builder-content="
                + value.contentEquals((StringBuilder) builder));
        System.out.println("builder-string="
                + value.equals(builder.toString()));

        System.out.println("objects-null-null="
                + Objects.equals(missing, null));
        System.out.println("objects-null-value="
                + Objects.equals(missing, value));
        System.out.println("objects-value-value="
                + Objects.equals(value, stringAsObject));

        System.out.println("different-case=" + value.equals("java"));
        System.out.println("equal-new-instance="
                + value.equals(new String("Java")));

        try {
            System.out.println(missing.equals(value));
        } catch (NullPointerException exception) {
            System.out.println("null-receiver=NullPointerException");
        }
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac StringEqualsNullAndTypeDemo.java
java StringEqualsNullAndTypeDemo
~~~

Output:

~~~text
literal-null=false
value-null=false
safe-constant=false
object-string=true
object-builder=false
object-number=false
builder-content=true
builder-string=true
objects-null-null=true
objects-null-value=false
objects-value-value=true
different-case=false
equal-new-instance=true
null-receiver=NullPointerException
~~~

Details to observe:

1. **The first three lines** are all false because the receiver is a real String while the argument is null.
2. **object-string=true** proves that an Object variable can actually be referencing a real String.
3. **object-builder=false** and **object-number=false** prove that String.equals() does not convert the argument's type.
4. **builder-content=true** and **builder-string=true** use methods with different comparison semantics, allowing content matching when intended.
5. **objects-null-null=true** shows the difference between Objects.equals() and String.equals(null).
6. **different-case=false** shows that equals() is case-sensitive.
7. **null-receiver=NullPointerException** comes from the catch block: calling the method on missing genuinely throws the exception and is caught so the program can continue.

## 7. Practical Applications: Validating Input, Status, and Nullable Values

### Checking a Status That May Be Missing

Example of a method receiving a status from an API:

~~~java
static boolean isReady(String status) {
    return "READY".equals(status);
}
~~~

This is an **illustrative method** that must be placed inside a Java class when used. It returns true only when status is a String equal to exact "READY"; for null, "ready", or "", it returns false.

This style is natural when an application wants to check **a single constant value** and missing data counts as a mismatch.

### When Two Absent Values Are Also Considered Equal

Suppose both the old and new values of a nullable field have no data. To detect changes between two nullable Strings:

~~~java
static boolean hasChanged(String oldValue, String newValue) {
    return !java.util.Objects.equals(oldValue, newValue);
}
~~~

When both oldValue and newValue are null, the result is false (no change). When one side is null and the other has a value, the result is true. When both Strings have the same content, the result is false.

**Choose deliberately:** in some business domains, "no data" does not mean "equal"; in those cases, do not mechanically use Objects.equals() without clarifying the comparison rules.

### When Values Arrive as Object

When processing Objects or multi-type data, do not confuse toString() with type checking:

~~~java
static boolean isJavaString(Object candidate) {
    return "Java".equals(candidate);
}
~~~

The function returns true if candidate is actually a String with content "Java", rejecting a StringBuilder displaying "Java" or other objects just because toString() produces the same text.

If the business logic **genuinely permits multiple types** and wants to normalize them into a String, you must design explicit conversion rules and account for null, number formatting, locale, and invalid cases. String.equals(Object) itself is not responsible for performing that normalization.

## 8. Common Misconceptions and Pitfalls

### Mistake 1: equals(null) definitely throws NullPointerException

False. **"Java".equals(null)** returns false. **nullable.equals("Java")** only throws NullPointerException when nullable is actually null. The position of null in the call matters greatly.

### Mistake 2: Because the parameter is declared as Object, equals() compares against any type

False. The **Object** signature allows passing an argument into the method; it does not mean the method converts the argument into a String. "42".equals(42) returns false (the int argument is boxed into Integer); "42".equals(Integer.valueOf(42)) is also false.

### Mistake 3: Two objects with identical toString() must have equals() return true

False. toString() primarily provides a textual representation; each class's equals() contract decides equality. String.equals() does not call the argument's toString() to compare.

### Mistake 4: Using == instead of equals() for String

Wrong if the goal is comparing **content**. == only compares references. String literals can be interned so == may occasionally appear to work, but you cannot use that coincidental outcome as a business rule.

### Mistake 5: Objects.equals(null, null) must be false because String.equals(null) is false

False. The two APIs have different contracts. Objects.equals(null, null) is true; in that case **no String object receives an equals() call**.

### Mistake 6: null, empty string, and whitespace-only string are all the same

False. null means no reference; "" is a valid String of length 0; " " is a String containing one space. For instance, "".equals(null) is false, "".equals("") is true, and "".equals(" ") is false. If the business logic wants to treat those values as equivalent, separate data-handling rules are needed before comparing.

### Mistake 7: equals() automatically ignores case or normalizes Unicode

False. String.equals() compares the exact sequence of UTF-16 code units, distinguishing "Java" from "java". If you need to ignore certain case differences, there is String.equalsIgnoreCase(String), though that method is **not** a full locale-aware string collation or Unicode normalization. Business-driven normalization must be decided explicitly.

### Mistake 8: Casting any object to String will solve the problem

False. If candidate points to a StringBuilder, `(String) candidate` causes ClassCastException. Check the type with instanceof before casting, or convert only when the application genuinely intends to accept that data type.

~~~java
Object candidate = new StringBuilder("Java");

if (candidate instanceof String text) {
    System.out.println("Java".equals(text));
} else {
    System.out.println("Not a String");
}
~~~

This is an **illustrative snippet** using pattern matching for instanceof supported in Java 17. The output is **Not a String**; there is no invalid cast.

## 9. Summary by Case and Self-Check

| Need to determine | Answer |
|---|---|
| Non-null String calling equals(null)? | false |
| Non-null String calling equals(StringBuilder with same content)? | false |
| Non-null String calling equals(Object pointing to String with same content)? | true |
| Null String variable calling equals("abc")? | NullPointerException |
| Both nullable Strings are null, using Objects.equals()? | true |
| StringBuilder needing content comparison with String? | Explicitly convert with toString() or use contentEquals() as required |
| Checking against constant "OK" and a nullable variable? | "OK".equals(value) |
| Comparing two nullable Strings where null/null counts as equal? | Objects.equals(a, b) |

**Answer for yourself:**

1. Why is "123".equals(123) false even though both sides have the same text representation?
2. Why does Object x = "Java"; make "Java".equals(x) true, while Object y = new StringBuilder("Java"); returns false?
3. What is the difference between "Java".equals(nullable) and nullable.equals("Java") when nullable is null?
4. Why does Objects.equals(null, null) return true while "Java".equals(null) returns false?
5. If a status field can be null, would you choose "READY".equals(status) or status.equals("READY"), and why?

**Core answers:** (1) String.equals() requires the actual argument to be a String; an integer is not a String. (2) The runtime object type decides, not the Object variable type or displayed text. (3) A non-null receiver returns false, whereas a null receiver throws an exception. (4) Objects.equals() handles two null references under its own contract. (5) Put the literal on the left for a safe check.

**Remember:** **null argument → false; non-String argument → false; null receiver → NullPointerException.** Put the String literal on the left when comparing against a constant, or use Objects.equals() for two nullable Strings when the **null equals null** rule is appropriate.
