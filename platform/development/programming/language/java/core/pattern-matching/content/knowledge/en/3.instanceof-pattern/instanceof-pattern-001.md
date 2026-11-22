# `instanceof` Syntax with Type Patterns in Java

## 1. From Type Checking to Type Patterns

When a variable is declared with a general type such as `Object` or an interface, the actual object that the variable references can belong to many concrete types. Java uses the `instanceof` operator to check the type at runtime. A **type pattern** combines that check with declaring a variable of the checked type, eliminating the need for an explicit cast after a successful check.

Compare two ways of handling a value that might be a `String`:

**Traditional approach — check then cast:**

```java
static int lengthOfString(Object input) {
    if (input instanceof String) {
        String text = (String) input;
        return text.length();
    }
    return 0;
}
```

**Using a type pattern:**

```java
static int lengthOfString(Object input) {
    if (input instanceof String text) {
        return text.length();
    }
    return 0;
}
```

Both snippets produce the same result for corresponding inputs. In the new approach, the compiler already knows that `text` is a `String` in the matching branch; the source code is shorter and avoids the mistake of changing the type in the condition while forgetting to update the cast inside the branch body.

Pattern matching for `instanceof` was standardized in **Java 16** (JEP 394); therefore, it can be used in **Java 17** without enabling preview features. This lesson focuses on **`instanceof` type patterns**. Record pattern syntax such as `Point(int x, int y)` is a different feature, standardized in Java 21.

## 2. Syntax Anatomy

Basic structure:

```java
expression instanceof ReferenceType patternVariable
```

Concrete example:

```java
Object value = "Java";
boolean matched = value instanceof String text;
```

Meaning of each component:

| Component | In the example | Meaning |
| --- | --- | --- |
| `expression` | `value` | The expression producing the value to check |
| `instanceof` | `instanceof` | The type-checking operator, producing a `boolean` result |
| `ReferenceType` | `String` | The reference type that the value must be compatible with at runtime |
| `patternVariable` | `text` | The variable initialized with the matched value, having type `String` |

In the `matched` declaration above, if `value` actually references a `String`, then `matched` is `true` and the pattern matches. However, **the expression returning `true` does not mean `text` is automatically in scope for every subsequent statement**. The scope of `text` depends on how the condition is written and the control flow; the next section explains this in detail.

Key points:

- **Successful match:** the expression returns `true`, and the pattern variable receives a reference to the exact object that was checked. No copy of the object is created.
- **No match:** the expression returns `false`, and the pattern variable is not initialized for use in the non-matching branch.
- **Input is `null`:** `null instanceof String text` returns `false`; it does not throw a `NullPointerException` solely because of this check.
- **Variable type is known:** within the valid scope, `text.length()` calls the `String` API directly, without needing `(String) value`.
- **Scope is checked at compile time:** the compiler rejects using `text` anywhere it is not guaranteed that the type pattern has matched.

### How does a type pattern differ from traditional `instanceof`?

```java
if (value instanceof String) {
    // Only knows that the String check is true.
}
```

```java
if (value instanceof String text) {
    // Also provides the variable text of type String, usable here.
}
```

Both check the type. A type pattern adds a **binding variable** bound to the matched result, allowing the value to be used immediately after the check.

### Which types and expressions are allowed?

In Java 17, a type pattern uses a **reference type**, such as `String`, `Integer`, an interface, a user-defined class, or an array type like `int[]`. `int[]` is a reference type (an array), whereas `int` is a primitive type, so the two cases differ:

```java
Object a = new int[] {1, 2, 3};

if (a instanceof int[] numbers) { // Valid in Java 17
    System.out.println(numbers.length); // 3
}
```

```java
// INVALID in Java 17:
// if (a instanceof int number) { ... }
```

The type on the left and the type in the pattern must allow a valid type check according to Java rules. The compiler also rejects a type pattern that is always true for every non-`null` value based on the static type of the expression:

```java
String text = "Java";

// INVALID in Java 17: String is already the static type of text.
// if (text instanceof String anotherText) { ... }
```

In this case, no type check is needed; `text` can be used directly. Conversely, `Object value = "Java"` has the static type `Object`, so `value instanceof String text` is a meaningful test.

## 3. Pattern Variable Scope: Only Where a Match Is Guaranteed

The scope of a pattern variable depends on **flow scoping**, rather than just curly braces. An easy mental model: **you may only use the variable when every path reaching that location has confirmed that the pattern matched successfully**.

### 3.1. `if` and `else`

```java
static String describe(Object input) {
    if (input instanceof String text) {
        return "Length: " + text.length(); // text can be used
    } else {
        return "Not a string";              // text cannot be used
    }
}
```

`text` is in scope in the `if` branch when the condition is true, and not in scope in the `else` branch. After a normal `if/else` statement, if there is still a path where the pattern did not match, you cannot use `text` as a variable with a known value either.

### 3.2. `&&`: the right-hand condition can use the matched variable

The `&&` operator evaluates from left to right and only evaluates the right-hand side when the left-hand side is `true`. Therefore, the following statement is valid:

```java
if (input instanceof String text && !text.isBlank()) {
    System.out.println(text.strip());
}
```

If `input` is not a `String` or is `null`, `text.isBlank()` is not executed. If the right-hand side is evaluated, the compiler already knows `text` is a valid `String`. This is a common way to **check both the type and a property** of the value at the same time.

Multiple short-circuiting conditions can be combined:

```java
if (input instanceof String text
        && text.length() >= 3
        && text.startsWith("J")) {
    System.out.println(text);
}
```

### 3.3. `||`: cannot use the variable on the right-hand side after a positive match

This snippet **does not compile**:

```java
// WRONG: When instanceof is false,
// Java needs to evaluate the right-hand side, but text has not been assigned.
// if (input instanceof String text || text.isEmpty()) {
//     System.out.println("Matched");
// }
```

`||` only evaluates the right-hand side when the left-hand side is `false`; in that exact case, `text` **has not matched**. This is a variable scoping error, not a syntax error specific to the `||` operator.

If you need a condition in the opposite direction, combine negation with `||`:

```java
static String validate(Object input) {
    if (!(input instanceof String text) || text.isBlank()) {
        return "Invalid";
    }
    return text.strip();
}
```

On the right-hand side of `||`, the condition `!(input instanceof String text)` is already `false`, which means the pattern actually **matched**, so `text.isBlank()` is allowed. Also, because the `if` branch returns early when the condition is true, the code after it only runs when `text` has matched and is non-blank.

### 3.4. `!` and early exit

Negation flips the true/false branches without losing the ability to use the variable on paths where the match is confirmed:

```java
static String normalized(Object input) {
    if (!(input instanceof String text)) {
        return "Not a string";
    }

    // If execution reaches here, the negated condition was false:
    // input is a String and text has been initialized.
    return text.strip();
}
```

This technique is often called a *guard clause*: handle invalid inputs first, then write the main flow at a lower indentation level. You can use `throw` instead of `return` depending on the method's contract.

**Note on parentheses:** Write `!(input instanceof String text)` to negate the entire check result. Do not confuse it with `(!input) instanceof String text`: the `!` operator cannot be applied to an arbitrary object.

### 3.5. Conditional expression `?:`

A type pattern can also be used in a ternary expression when the branch using the variable is guaranteed to have matched:

```java
static int textLength(Object input) {
    return input instanceof String text ? text.length() : -1;
}
```

In the branch after `?`, `text` always has type `String`. The branch after `:` cannot rely on the same pattern variable, because that branch represents a failed check.

### 3.6. Reusing variable names in disjoint branches

Pattern variable names follow Java's scoping rules. Two separate branches can reuse a name when their scopes do not overlap:

```java
static String label(Object value) {
    if (value instanceof String item) {
        return "Text: " + item;
    } else if (value instanceof Integer item) {
        return "Number: " + item;
    }
    return "Unknown";
}
```

However, declaring a pattern variable with the same name as a local variable **already in scope** causes a compile error. For maintainable code, prefer meaningful names like `text`, `number`, `order`, rather than trying to reuse the same name across multiple branches.

## 4. Complete Example, Runnable with Java 17+

Create a file named **`TypePatternDemo.java`** with the following content:

```java
import java.util.List;

public class TypePatternDemo {
    static String classify(Object value) {
        if (value instanceof String text && !text.isBlank()) {
            return "String: " + text.strip();
        }

        if (value instanceof Integer number) {
            return "Integer doubled: " + (number * 2);
        }

        if (value instanceof List<?> elements) {
            return "List size: " + elements.size();
        }

        if (value instanceof int[] numbers) {
            return "Array length: " + numbers.length;
        }

        return "Unknown";
    }

    static String requireNonBlankText(Object value) {
        if (!(value instanceof String text) || text.isBlank()) {
            return "Invalid";
        }
        return "Valid: " + text.strip();
    }

    public static void main(String[] args) {
        System.out.println(classify("  Java  "));
        System.out.println(classify(7));
        System.out.println(classify(List.of("a", "b")));
        System.out.println(classify(new int[] {2, 4, 6}));
        System.out.println(classify(""));
        System.out.println(classify(null));
        System.out.println(requireNonBlankText("  hello  "));
        System.out.println(requireNonBlankText("   "));
    }
}
```

Run with JDK 17 or later:

```bash
javac --release 17 TypePatternDemo.java
java TypePatternDemo
```

**Expected output:**

```text
String: Java
Integer doubled: 14
List size: 2
Array length: 3
Unknown
Unknown
Valid: hello
Invalid
```

Explanation:

1. `"  Java  "` matches `String text`; `!text.isBlank()` is true; `strip()` removes leading/trailing whitespace.
2. `7` is autoboxed to `Integer` when passed to the `Object` parameter; the type pattern `Integer number` matches and `number * 2` uses unboxing.
3. `List.of("a", "b")` matches `List<?> elements`; the check only guarantees it is a `List`, not the type of each element.
4. `new int[] {2, 4, 6}` matches `int[] numbers`, because an array is a reference type.
5. The empty string `""` matches by **type** but fails the `!text.isBlank()` condition, so execution continues to `Unknown`.
6. `null` matches no pattern and falls through to the default result; `instanceof` itself does not throw an exception.
7. `requireNonBlankText` rejects wrong-type values or blank strings early, then uses `text` in the branch guaranteed to have matched.

This example compiles on Java 17 without enabling preview features. If using an IDE, select Java language level 17 or higher; for Maven/Gradle, configure the corresponding release version.

## 5. Type Patterns with Inheritance and Interfaces

An instance of a subclass can also match a type pattern for its superclass or an interface it implements. Example:

```java
interface Printable {
    String render();
}

final class Receipt implements Printable {
    @Override
    public String render() {
        return "Receipt #42";
    }
}
```

In a method receiving `Object value`, you can write:

```java
if (value instanceof Printable printable) {
    System.out.println(printable.render());
}
```

If `value` points to `new Receipt()`, the pattern `Printable printable` matches; the static type of `printable` is `Printable`, so the `render()` method declared on the interface can be called. The syntax does not require a concrete class: a type pattern can specify an appropriate abstract type.

### Distinguishing static type from runtime type

```java
Object input = "hello";
if (input instanceof CharSequence chars) {
    System.out.println(chars.length()); // 5
}
```

The variable `input` has static type `Object`, while the runtime object is a `String`. `String` implements `CharSequence`, so the pattern matches. Inside the `if` branch, `chars` has static type `CharSequence`, meaning only members of `CharSequence` are guaranteed to be directly callable. The purpose of a type pattern is to obtain a variable of the checked type, **not to automatically promote the variable to every concrete type the object implements**.

### Not synonymous with checking for an exact single class

`obj instanceof BaseType b` is also true when `obj` is a valid subclass of `BaseType`; it does not require `obj.getClass() == BaseType.class`. If business logic needs to distinguish the exact runtime class, that is a different requirement and requires a separate design choice.

## 6. Type Patterns with Generics and Type Erasure Limits

At runtime, Java does not retain full generic type arguments due to *type erasure*. Therefore, you cannot rely on `instanceof` to verify that a list contains only `String`s using parameterized syntax alone.

**Valid:**

```java
if (value instanceof List<?> items) {
    System.out.println(items.size());
}
```

**Invalid for `Object value` in Java 17:**

```java
// DOES NOT COMPILE:
// if (value instanceof List<String> items) {
//     System.out.println(items.size());
// }
```

`List<?> items` indicates that the value is a `List` with an unknown element type. You can check elements when needed:

```java
if (value instanceof List<?> items) {
    for (Object element : items) {
        if (element instanceof String text) {
            System.out.println(text.toUpperCase());
        }
    }
}
```

Do not infer that every element is a `String` just because a few elements match. If the application requires a homogeneous list, check all elements or enforce a type contract at the data boundary.

## 7. Key Differences to Remember When Reading and Writing Code

| Topic | Correct understanding |
| --- | --- |
| `instanceof String` | Only returns the type-check result |
| `instanceof String text` | Returns the type-check result **and** binds `text` within the valid scope |
| `instanceof` with `null` | Returns `false`, does not throw `NullPointerException` |
| `if (x instanceof String s && s.length() > 3)` | Valid because the right-hand side only runs when `s` has matched |
| `if (x instanceof String s || s.length() > 3)` | Invalid because the right-hand side can run when `s` has not matched |
| `if (!(x instanceof String s)) return; ... s ...` | Can be valid because all subsequent paths have matched |
| `List<?> list` | Can be checked at runtime, but does not guarantee element types |
| `String text = ...; text instanceof String s` | Compiler rejects a match that is always true by static type in Java 17 |
| `instanceof Point point` | Type pattern, binds a name to the `Point` object; does not destructure fields |
| `instanceof Point(int x, int y)` | Record pattern in Java 21+, distinct from basic type pattern syntax |

A pattern variable is **not implicitly `final`** in Java 16+, but in practice you should avoid reassigning it unless necessary: using a new name for a transformed value helps avoid confusing the original object with normalized data.

## 8. Common Mistakes and How to Fix Them

### Mistake 1: trying to use the variable in the non-matching branch

```java
// INVALID:
// if (value instanceof String text) {
//     System.out.println(text);
// } else {
//     System.out.println(text.length());
// }
```

**Fix:** use `text` in the matching branch; in the `else` branch, handle `value` using its original type or choose a default value.

### Mistake 2: assuming `instanceof` changed the source variable's type

```java
Object value = "hello";
if (value instanceof String text) {
    System.out.println(text.length()); // Correct
    // System.out.println(value.length()); // WRONG: value still has static type Object
}
```

**Fix:** call type-specific methods through `text`, since only that variable is declared with type `String`.

### Mistake 3: confusing `&&` with `||`

```java
// WRONG:
// if (value instanceof String text || text.startsWith("A")) { ... }

// RIGHT:
if (value instanceof String text && text.startsWith("A")) {
    System.out.println(text);
}
```

**Fix:** choose the operator according to the intended semantics, and verify which branch guarantees the variable is initialized.

### Mistake 4: using a primitive type in a pattern position

```java
// WRONG in Java 17:
// if (value instanceof int n) { ... }

// RIGHT when value is an Object that may hold an Integer:
if (value instanceof Integer n) {
    System.out.println(n.intValue());
}
```

**Fix:** in Java 17, use a reference type such as `Integer` when checking boxed objects.

### Mistake 5: confusing a type pattern with a record pattern

If you have:

```java
record Point(int x, int y) {}
```

then in Java 17 you can still write:

```java
if (value instanceof Point point) {
    System.out.println(point.x() + point.y());
}
```

This snippet uses the **type pattern** `Point point`. It does not create variables `x` and `y`; you must call the record accessors. The `Point(int x, int y)` syntax for destructuring components was only finalized in Java 21.

### Mistake 6: checking a type when the static type is already specific enough

```java
String name = "Java";
System.out.println(name.length());
```

Here there is no need for `name instanceof String otherName`. When the compiler already knows the concrete type, a type pattern only makes the code longer and may be rejected as an unconditionally true test for non-`null` values.

## 9. Practice Exercises to Check Understanding

**Exercise 1 — predict the output.**

```java
static String result(Object value) {
    if (value instanceof String s && s.length() >= 4) {
        return s.substring(0, 2);
    }
    return "NO";
}
```

What do `result("Java")`, `result("Go")`, and `result(null)` return?

The answers are **`"Ja"`**, **`"NO"`**, and **`"NO"`**, respectively. `"Go"` is still a `String` but fails the length condition; `null` does not match the type pattern.

**Exercise 2 — fix the compile error.**

```java
// WRONG:
// if (value instanceof String s || s.isBlank()) {
//     System.out.println("Invalid");
// }
```

If the intent is to detect an input that is not a string **or** is a blank string, you can write:

```java
if (!(value instanceof String s) || s.isBlank()) {
    System.out.println("Invalid");
}
```

When `value` is not a `String`, the left-hand side is `true`, so `s.isBlank()` does not need to be evaluated. If the right-hand side is evaluated, the pattern has already matched.

**Exercise 3 — write your own method.** Write `String summary(Object value)` with these rules: if it is a `String`, return the string after calling `strip()`; if it is an `Integer`, return `"number:"` concatenated with the value; otherwise return `"unknown"`. Use two type patterns and test with `"  hi "`, `5`, and `null`. Expected outputs respectively: `"hi"`, `"number:5"`, `"unknown"`.

## 10. When Should You Use It?

Type patterns are a great fit when code receives a value of a general type, needs to classify a few possibilities, or needs additional conditions based on methods of the matched type. For a single simple branch, `if (value instanceof T t)` is usually easier to read than separate check and cast statements.

If there are many classification branches, revisit the data type design before extending a long `if/else` chain. In closed type hierarchies, pattern `switch` (finalized in Java 21) can express branches more clearly; for objects with polymorphic behavior, calling methods through an interface is sometimes a better fit. That is a design choice, not a mandatory requirement when using `instanceof`.

**Key takeaway:** The syntax `value instanceof String text` does two things — it checks the runtime type of `value` and binds the matched value to `text`. The next essential skill is understanding **flow-dependent scope**: only use `text` where the compiler proves the pattern has definitely succeeded.

## References

- [Oracle Java 17 — Pattern Matching for instanceof](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html)
- [OpenJDK JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [Java SE 17 Language Specification — Scope of Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3)
- [Java SE 17 Language Specification — The instanceof Operator](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2)
