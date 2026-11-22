# From Type Checking to Testing and Extracting Data in Java

## 1. The Problem: Knowing the Type Alone Is Not Enough

When a variable has a broad declared type such as `Object`, a program often needs to determine its actual runtime type before using type-specific behavior. For example, a `String` has a `length()` method, while an `Integer` can be used as an integer value. Type checking helps select the right branch; however, to invoke methods or extract specific data components, you still need to access the object as the appropriate type.

**Pattern matching** brings these two operations closer together: **testing whether a value matches a pattern** and, if it matches, **binding the corresponding data to a variable**. With a *type pattern*, the variable receives the type-checked object itself; with a *record pattern* (Java 21+), the pattern can directly extract the components of a `record`.

After this lesson, you will be able to:
- Explain why traditional `instanceof` checks are usually paired with a cast.
- Write `instanceof Type variable` to both test and use the matched value.
- Understand the scope of a pattern variable based on control flow.
- Distinguish a *type pattern* (binding the entire object) from a *record pattern* (extracting its components).
- Recognize when to use pattern matching in `switch` and common pitfalls to avoid.

## 2. The Traditional Approach: Check First, Cast Later

Before pattern matching for `instanceof`, code typically separated asking "is it this type?" and casting into two separate steps.

~~~java
public class BeforePattern {
    static String describe(Object value) {
        if (value instanceof String) {
            String text = (String) value;
            return "String(length=" + text.length() + ")";
        }
        if (value instanceof Integer) {
            Integer number = (Integer) value;
            return "Integer(value=" + number + ")";
        }
        return "Other";
    }

    public static void main(String[] args) {
        System.out.println(describe("Java"));
        System.out.println(describe(42));
        System.out.println(describe(null));
    }
}
~~~

Save the file as `BeforePattern.java` and run it with JDK 17 or later:

~~~bash
javac --release 17 BeforePattern.java
java BeforePattern
~~~

Output:

~~~text
String(length=4)
Integer(value=42)
Other
~~~

In the first branch, `value instanceof String` returns `true` if the value currently references a `String` object. However, the declared type of `value` is still `Object`; therefore, the code must write `(String) value` before calling `length()`.

This approach is valid, but it repeats the type name, introduces an extra variable, and can cause bugs when a developer updates the condition but forgets to update the corresponding cast. An incorrect cast can throw a `ClassCastException`. The goal of pattern matching is to eliminate that boilerplate while keeping the type information right at the check site.

## 3. Type Patterns: Testing and Binding a Variable in One Expression

Since Java 16, *pattern matching for instanceof* has been a standard feature; Java 17 supports it without enabling preview features.

~~~java
public class PatternBinding {
    static String describe(Object value) {
        if (value instanceof String text) {
            return "String(length=" + text.length() + ")";
        }
        if (value instanceof Integer number) {
            return "Integer(value=" + number + ")";
        }
        return "Other";
    }

    public static void main(String[] args) {
        System.out.println(describe("Java"));
        System.out.println(describe(42));
        System.out.println(describe(null));
    }
}
~~~

~~~bash
javac --release 17 PatternBinding.java
java PatternBinding
~~~

The output remains:

~~~text
String(length=4)
Integer(value=42)
Other
~~~

Read the expression `value instanceof String text` in three parts:

1. **The value to test:** `value`.
2. **The type pattern:** `String` — requires the value to be an object compatible with this type.
3. **The pattern variable:** `text` — bound to the value only when the pattern matches, and typed as `String`.

Because `text` already has type `String`, you can call `text.length()` directly without casting. The variable `text` is not a copy of the object; it references the exact same object that `value` references. The same principle applies to `Integer number`.

Note: **`null instanceof String text` never matches**. Therefore, calling `describe(null)` goes to the `Other` branch without throwing a `NullPointerException` at the `instanceof` check.

You can visualize the flow as follows:

~~~text
Value with declared type Object
               |
               v
   Matches pattern String text?
         /             \
       yes              no
        |                |
 Bind variable text   Try another pattern
        |
   Use String API
~~~

## 4. Variable Scope Depends on the Matched Branch

A pattern variable does not automatically exist throughout the entire method. The compiler tracks control flow to determine where the pattern is **definitely matched** (*flow scoping*).

In the simple case: inside the `if (value instanceof String text)` branch, the variable `text` is in scope. In the corresponding `else` branch, you cannot assume it has been bound.

A useful case is a negated check followed by an early return:

~~~java
public class FlowScopeDemo {
    static String normalized(Object value) {
        if (!(value instanceof String text)) {
            return "Not a String";
        }
        if (text.isBlank()) {
            return "Blank String";
        }
        return text.trim().toUpperCase();
    }

    public static void main(String[] args) {
        System.out.println(normalized("  java  "));
        System.out.println(normalized("   "));
        System.out.println(normalized(3));
    }
}
~~~

~~~bash
javac --release 17 FlowScopeDemo.java
java FlowScopeDemo
~~~

Output:

~~~text
JAVA
Blank String
Not a String
~~~

Because the "not a String" branch returns early, every remaining execution path reaching `text.isBlank()` has matched `String text`. Thus, the variable `text` is valid after the `if` statement.

**Compound conditions also follow control flow:**

- `value instanceof String text && !text.isBlank()` is valid: the right-hand side is evaluated only when the pattern on the left-hand side has matched.
- `value instanceof String text || text.isBlank()` is invalid: the right-hand side can be evaluated when the pattern on the left-hand side **did not** match, so `text` has not been bound.
- If the failing branch does not exit the current flow, do not use the pattern variable in code that the failing branch can also reach.

Rule of thumb: only use a pattern variable in places where Java can prove the corresponding check succeeded.

## 5. From Binding the Whole Object to Extracting Components: Record Patterns

With `String text`, a type pattern only gives you a single variable pointing to the entire `String`. When data is held across multiple components, you might still have to call accessor methods. For example, with `record Point(int x, int y)`, the `Point` type has the accessors `x()` and `y()`.

Since **Java 21**, *record patterns* let you test a record and directly extract its components in the same pattern, including when records are nested:

~~~java
record Point(int x, int y) {}
record Line(Point start, Point end) {}

public class RecordPatternDemo {
    static String describe(Object value) {
        if (value instanceof Point(int x, int y)) {
            return "Point(" + x + "," + y + ")";
        }
        if (value instanceof Line(Point(int x1, int y1), Point(int x2, int y2))) {
            return "Line(" + x1 + "," + y1 + ")->(" + x2 + "," + y2 + ")";
        }
        return "Other";
    }

    public static void main(String[] args) {
        System.out.println(describe(new Point(2, 5)));
        System.out.println(describe(
            new Line(new Point(1, 2), new Point(3, 4))
        ));
        System.out.println(describe("Java"));
    }
}
~~~

~~~bash
javac --release 21 RecordPatternDemo.java
java RecordPatternDemo
~~~

Output:

~~~text
Point(2,5)
Line(1,2)->(3,4)
Other
~~~

In the pattern `Point(int x, int y)`:
- `Point` specifies the record type that must match.
- The two component patterns `int x` and `int y` extract values from the corresponding record components in declaration order.
- Inside the matched branch, `x` and `y` are `int` variables ready to use immediately.

The pattern `Line(Point(int x1, int y1), Point(int x2, int y2))` goes a step further: it checks for a `Line`, then matches the two inner `Point` instances and binds all four coordinates to variables. This is *deconstruction*: describing the data structure you want to extract, instead of casting and calling `start().x()`, `start().y()`, `end().x()`, and `end().y()` one by one.

**Limitations to understand:** record pattern syntax applies to `record` types, not as a general way to automatically "unpack" arbitrary regular Java classes. Component types and order must match the record declaration. If any nested component fails to match its corresponding pattern, the entire pattern fails to match. Record patterns are a standard feature starting in Java 21; this snippet will not compile with `--release 17`.

## 6. Pattern Matching in `switch`: Branching and Extracting Data Together

When there are many input types, an `if/else if` chain can grow long. Since **Java 21**, `switch` officially supports type patterns and additional conditions using `when`.

~~~java
public class SwitchPatternDemo {
    static String classify(Object value) {
        return switch (value) {
            case null -> "Null";
            case String text when text.isBlank() -> "Blank String";
            case String text -> "String(length=" + text.length() + ")";
            case Integer n -> "Integer(value=" + n + ")";
            default -> "Other";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify(null));
        System.out.println(classify("  "));
        System.out.println(classify("Java"));
        System.out.println(classify(7));
    }
}
~~~

~~~bash
javac --release 21 SwitchPatternDemo.java
java SwitchPatternDemo
~~~

Output:

~~~text
Null
Blank String
String(length=4)
Integer(value=7)
~~~

`case String text` both recognizes a `String` input and binds the variable `text` for use in that branch. With `case String text when text.isBlank()`, the `when` guard is evaluated only after the type pattern has matched. The branch for an empty or whitespace-only `String` must come **before** the broader `case String text` branch; reversing their order causes the narrower branch to be reported as unreachable (*dominated case*).

With `switch` on objects, `null` needs to be considered explicitly: without `case null`, passing `null` normally causes `switch` to throw a `NullPointerException`. `default` handles the remaining types in the example. Java 17 does not yet support this `switch` syntax as a standard feature; use JDK 21+.

## 7. Choosing the Right Level of Pattern

| Need | Typical syntax | Data obtained | Standard version |
| --- | --- | --- | --- |
| Only check whether it belongs to a type | `obj instanceof String` | A `boolean` value | Available since early Java |
| Check type and use the object | `obj instanceof String s` | Variable `s` of type `String` | Java 16+ |
| Check record and extract components | `obj instanceof Point(int x, int y)` | Variables `x`, `y` | Java 21+ |
| Select one of many patterns | `switch (obj) { case String s -> ...; ... }` | Variable scoped only to the matching branch | Java 21+ |

When you only need to know "is it this type?", traditional `instanceof` is still sufficient. When you need to use the object after the check, a *type pattern* usually makes the code shorter and easier to read. When working with records that have a clear structure, a *record pattern* directly expresses the data you want to extract; when there are many type branches, `switch` centralizes the classification logic.

Pattern matching does not parse a string into a number, automatically decode JSON, or replace business-level data validation. It **matches the existing type/structure** of an object and binds variables only when the pattern succeeds.

## 8. Common Mistakes and How to Avoid Them

1. **Using a pattern variable outside the region guaranteed to match.** For example, do not access `text` on the right-hand side of an `||` expression when `text` is only declared in a type pattern on the left-hand side. Use `&&` when the logic fits, or split into an `if` branch with an explicit exit.
2. **Assuming `null` is an object that matches a type pattern.** `null instanceof String s` evaluates to `false`; with `switch` on reference types, explicitly decide how to handle `null`.
3. **Confusing variable binding with copying or converting data.** `obj instanceof String s` does not create a new `String`. A record pattern extracts components according to the record declaration; it does not create a new object to replace the original value.
4. **Using newer syntax on an older JDK.** `instanceof String s` works in Java 17; the record pattern and `switch` pattern syntax shown above require Java 21+. When sharing code, check both the JDK version and the `--release` setting.
5. **Placing a broad pattern before a specific pattern in `switch`.** An unguarded `case String s` can dominate any `String` branches placed after it. Place cases with `when` guards first.
6. **Assuming record patterns work on every class.** Regular class instances do not automatically expose record component structure; when needed, use accessors or design appropriate data types.

## 9. Self-Check

**Exercise 1.** Given `Object input = "  Java  ";`, write a condition using an `instanceof` pattern so that `trim()` is called only if `input` is a non-blank `String`. Hint: combine `instanceof String s` with `&& !s.isBlank()`. The value after `trim()` is `"Java"`.

**Exercise 2.** Given `record Size(int width, int height) {}`, use a record pattern to extract `Size` from an `Object` variable and compute the area. If the variable holds `new Size(3, 4)`, the result is `12`; if it holds `"3x4"`, the pattern does not match. This exercise requires Java 21+.

**Thought Question.** Why does `if (!(value instanceof String s)) return;` (in a `void` method) allow using `s` on the following line, whereas `if (!(value instanceof String s)) { System.out.println("other"); }` does not? Answer: the first case completely eliminates the non-matching execution path; the second case can still fall through to the next line when the pattern fails.

**Takeaway:** The key progression of pattern matching is moving from **"does this value belong to this type?"** to **"if it matches, what data can we use right away, and where in the program flow is that data guaranteed to be valid?"**.
