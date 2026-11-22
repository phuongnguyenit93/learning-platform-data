# Distinguishing String Content from a String Reference Variable

In Java, when writing `String name = "Java";`, you need to distinguish the **string content** (`"Java"`), the **`String` object** representing that content, and the **reference variable** (`name`) used to access the object. These three concepts are related but not identical. Understanding this distinction helps explain assignment, `String` immutability, comparisons with `==` and `equals()`, as well as common pitfalls when working with strings.

## 1. Content, object, and reference variable

Consider:

```java
String text = "Java";
```

- `String` is a reference type, not a primitive type like `int` or `boolean`.
- `"Java"` is a *string literal*: an expression providing a reference to a `String` object whose content is the four characters `J`, `a`, `v`, `a`. Java manages literals and `intern()`ed strings in a shared region called the *string pool*.
- `text` is a variable of type `String`. The value of this variable is **a reference to an object** (or `null`); do not think of the variable as directly holding an independent copy of the entire `"Java"` content.
- String content is the sequence of characters that the `String` object represents. That content can be queried using methods such as `length()`, `charAt()`, or `equals()`.

You can visualize the relationship conceptually:

```text
Variable text --reference--> String object
                             Content: "Java"
```

The diagram is meant to illustrate the reference relationship, **not** specific memory addresses, memory region layouts, or how the JVM must implement it internally. Java does not expose object memory addresses through a `String` variable.

| Aspect | String content | `String` reference variable |
|---|---|---|
| Question to answer | Which characters does the string represent? | Which object (or `null`) is the variable pointing to? |
| Example | `"Java"` | `text` in `String text = "Java";` |
| Typical comparison | `equals()` | `==` checks whether two references point to the same object |
| Modifiable via assignment? | Cannot modify the content of an existing `String` | Yes, the variable can be assigned a different reference |
| Can be `null`? | No: `null` is not a string with content | Yes: a reference variable can hold `null` |

## 2. Assigning a reference does not copy the string

```java
String first = "Java";
String alias = first;
```

After the assignment `alias = first`, both variables **refer to the same `String` object**. Assigning between two reference variables does not create a new object and does not copy the characters into another object.

```text
first -----+
           +----> String with content "Java"
alias -----+
```

If you execute `first = "Kotlin";`, Java only replaces the reference value stored in `first`. The `alias` variable still refers to the `"Java"` string:

```text
first ----------> String with content "Kotlin"
alias ----------> String with content "Java"
```

This differs from the idea of “changing the content inside the original object.” Reassigning one variable does not automatically change the references held by other variables.

## 3. Immutable `String`: changing a variable's value vs. modifying an object's content

A `String` object is **immutable**: once created, the content of that object itself cannot be changed through the `String` API. Operations like `concat()`, `replace()`, `substring()`, or string concatenation may return a reference to a string with the desired content; they do not modify the characters inside the original object. An operation may return the existing object itself when appropriate (such as concatenating an empty string), so you should not claim that every call creates a new object.

```java
String a = "Java";
String b = a;

a = a.concat(" Core");

System.out.println(a); // Java Core
System.out.println(b); // Java
```

Initially, `a` and `b` both point to `"Java"`. `concat(" Core")` produces the string `"Java Core"`; the assignment places the resulting reference into `a`. `b` still points to the original `"Java"` object. Similarly, `a += " Core"` does not “modify in place” the original `String` object.

Practical tip: when you want to keep the result of string-returning operations, use the returned value, e.g., `text = text.trim();`. Calling `text.trim();` alone and discarding the return value will not update the `text` variable.

## 4. Comparison: `==` asks “same object?”, `equals()` asks “same content?”

Given two `String` variables:

- `a == b` is **reference comparison**: `true` if both currently point to the same object, or both are `null`.
- `a.equals(b)` is **content comparison** as defined by `String.equals`: `true` when `b` is a string with the exact same character sequence; the comparison is case-sensitive. If `a` is `null`, calling `a.equals(b)` throws `NullPointerException`.
- You can have **the same content across different objects**. Conversely, if two references point to the same `String` object, their content is obviously identical.

Complete runnable example on Java 17+:

**File `StringReferenceDemo.java`**

```java
public class StringReferenceDemo {
    public static void main(String[] args) {
        String first = "Java";
        String alias = first;
        String separate = new String("Java");
        String sameLiteral = "Java";

        System.out.println("first == alias: " + (first == alias));
        System.out.println("first == separate: " + (first == separate));
        System.out.println("first.equals(separate): " + first.equals(separate));
        System.out.println("first == sameLiteral: " + (first == sameLiteral));

        first = first.concat(" Core");
        System.out.println("first: " + first);
        System.out.println("alias: " + alias);
        System.out.println("separate: " + separate);
        System.out.println("first == alias after reassignment: " + (first == alias));
    }
}
```

Compile and run in the directory containing the file:

```bash
javac StringReferenceDemo.java
java StringReferenceDemo
```

**Output:**

```text
first == alias: true
first == separate: false
first.equals(separate): true
first == sameLiteral: true
first: Java Core
alias: Java
separate: Java
first == alias after reassignment: false
```

Breakdown of key points:

1. `alias = first` copies the reference, so `first == alias` is `true`.
2. `new String("Java")` explicitly creates a new `String` object, distinct from the `"Java"` literal object. Both objects still have the same content, so `==` is `false` and `equals()` is `true`.
3. Both uses of the `"Java"` literal share the interned object, so `first == sameLiteral` is `true` at the time of comparison.
4. After `first = first.concat(" Core")`, `first` holds a reference to the result with content `"Java Core"`; `alias` and `separate` still have content `"Java"`. Since `first` was reassigned, `first == alias` is `false`.

**Usage rule:** if the business requirement is to check whether two strings have the same text (names, codes, user input, string-represented statuses), generally use `equals()`; never rely on `==` as the criterion for comparing content.

## 5. String pool: why does `==` sometimes return `true`?

Java stores string literals and interned strings so the same object can be reused. This mechanism explains why two literals with the same content often share the same reference. Meanwhile, `new String("Java")` creates a new object for the `new` expression.

The compiler can also precompute **constant expressions** formed by concatenating literals. In contrast, concatenating strings from runtime-determined data creates results along the execution flow; do not rely on matching references to conclude two contents are equal.

**File `StringPoolDemo.java`**

```java
public class StringPoolDemo {
    public static void main(String[] args) {
        String literal = "Java";
        String folded = "Ja" + "va";
        String prefix = new String("Ja");
        String computed = prefix + "va";

        System.out.println(literal == folded);
        System.out.println(literal.equals(computed));
        System.out.println(literal == computed);
        System.out.println(literal == computed.intern());
    }
}
```

```bash
javac StringPoolDemo.java
java StringPoolDemo
```

**Output on Java 17+:**

```text
true
true
false
true
```

- `"Ja" + "va"` is a constant expression and is folded into the `"Java"` literal at compile time: `literal == folded` is `true`.
- `prefix` holds an object created at runtime using `new`. `computed` has the same characters as `literal`, so `equals()` is `true`, but the result of a runtime concatenation does not automatically become the same interned object as the literal.
- `computed.intern()` returns the corresponding canonical reference in the pool; because the `"Java"` literal already exists, the reference comparison with `literal` is `true`.

The pool mechanism explains the difference between expressions, **not** a reason to use `==` for content comparison. In application code, creating `new String(...)` merely to test reference differences is usually unnecessary; there is no need to force strings into the pool just to compare them properly.

## 6. `null`, empty strings, and safe comparison

`null` means the variable **does not refer to any object**. It is different from the empty string `""`: an empty string is a valid `String` object with length `0`.

```java
String missing = null;
String empty = "";

System.out.println(missing == null); // true
System.out.println(empty == null);   // false
System.out.println(empty.length());  // 0
```

Calling `missing.length()` or `missing.equals("Java")` throws `NullPointerException` because there is no object on which to invoke the method.

Two safe ways to compare content when `null` is possible:

- With a literal guaranteed to be non-null, reverse the caller side: `"Java".equals(candidate)`; if `candidate` is `null`, the result is `false`.
- With two variables that may both be null, use `Objects.equals(left, right)`. This method returns `true` when both are `null` or when two non-null values are equal according to `equals()`.

**File `SafeStringCompareDemo.java`**

```java
import java.util.Objects;

public class SafeStringCompareDemo {
    public static void main(String[] args) {
        String candidate = null;

        System.out.println(candidate == null);
        System.out.println("Java".equals(candidate));
        System.out.println(Objects.equals(candidate, null));
        System.out.println("".equals(candidate));
    }
}
```

```bash
javac SafeStringCompareDemo.java
java SafeStringCompareDemo
```

**Output:**

```text
true
false
true
false
```

Note: `Objects.equals(null, null)` is `true` because both values lack a reference; that **does not** mean `null` is a string containing text.

## 7. Common mistakes and how to avoid them

| Mistake or misconception | Why is it wrong? | Correct practice |
|---|---|---|
| `if (input == "yes")` to check user-entered text | `input` may point to a different object from the literal even if content is `"yes"` | `"yes".equals(input)` |
| Thinking `String copy = original;` creates a content copy | Assignment copies the reference value | Understand both point to the same object; `String` is immutable so defensive copying against content mutation is unnecessary |
| Thinking `text = text + "!"` mutates the old object | `text` is assigned a reference to the concatenation result | Distinguish reassigning a variable from modifying an object |
| Calling `text.trim();` and expecting `text` to change | `trim()` returns a result without modifying the original `String` | `text = text.trim();` |
| Seeing `"a" == "a"` as `true` and inferring `==` always compares characters | Two literals can be shared via the string pool | Use `equals()` or `Objects.equals()` for content |
| Calling `text.equals(other)` when `text` can be null | Accessing a method through a `null` reference causes `NullPointerException` | Check for null, put the literal first, or use `Objects.equals()` |
| Treating `null` and `""` as the same | `null` points to no object; `""` is a valid string with 0 characters | Handle them separately based on business requirements |

## 8. Self-check

Predict the output before running the following snippet:

```java
String x = "cat";
String y = x;
String z = new String("cat");

x = "dog";

System.out.println(y);
System.out.println(x == y);
System.out.println(y.equals(z));
System.out.println(y == z);
```

**Answers in order:** `cat`, `false`, `true`, `false`.

Explanation: `y` keeps the initial reference to `"cat"`; assigning `"dog"` to `x` does not affect `y`. `z` is a different object but has the same content as `y`.

When reading any code involving `String`, ask yourself in this exact order: **(1) Which object is the variable currently pointing to? (2) What is that object's content? (3) Is the operation checking references, checking content, or reassigning a reference?** These three questions clearly separate “what the string holds” from “where the variable points,” even when the string pool or concatenation appears.