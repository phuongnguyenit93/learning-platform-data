# Record component pattern variables in Java 21+

## 1. Concept and purpose

A `record` describes a data type using **record components** declared in the record header. For example:

~~~java
record Point(int x, int y) {}
~~~

`x` and `y` are two record components of type `int`. The compiler provides the accessors `x()` and `y()` to read values from a `Point` object.

A **record pattern** lets you check the record type and directly extract its component values. A **record component pattern variable** is a local variable declared by a *component pattern* inside a record pattern; the variable is assigned only when matching succeeds.

~~~java
Object value = new Point(3, 5);

if (value instanceof Point(int first, int second)) {
    System.out.println(first + second); // 8
}
~~~

In `Point(int first, int second)`:

- `Point(...)` is a **record pattern**, which checks whether the object is a `Point` and matches its components in their declaration order.
- `int first` and `int second` are **type patterns** applied to the two components, declaring the pattern variables `first` and `second`, respectively.
- `first` receives `3`, and `second` receives `5`; the variable names are chosen by the author of the pattern and do not have to match `x` or `y` in the record declaration.
- The variables' scope depends on the branch where the compiler knows for certain that the pattern has matched; they do not become new fields or components of `Point`.

Record patterns were standardized in **Java 21 (JEP 440)**, without needing `--enable-preview`. Java 19/20 only had preview versions; Java 17 cannot compile the record pattern syntax in this article.

## 2. How do pattern variables differ from record components and a variable holding the whole record?

| Construct | Example | Meaning |
| --- | --- | --- |
| Record component | `x` in `record Point(int x, int y)` | Data member belonging to the record type definition |
| Accessor | `p.x()` | Method that reads a component of object `p` |
| Type pattern holding the whole object | `value instanceof Point p` | Variable `p` holds a reference to the entire `Point`; accessed via `p.x()` |
| Record pattern extracting components | `value instanceof Point(int a, int b)` | Pattern variables `a` and `b` receive the two component values after matching |

Two equivalent ways of reading the data:

~~~java
if (value instanceof Point p) {
    System.out.println(p.x() + p.y());
}

if (value instanceof Point(int a, int b)) {
    System.out.println(a + b);
}
~~~

A record pattern **does not directly declare a variable representing the entire record**. The bound variables are declared by the nested patterns at each component position. In `Point(int a, int b)`, the names `a` and `b` are independent of the component names `x` and `y`.

## 3. Matching mechanism and variable types

For a value tested with `Point(int a, int b)`, Java semantically performs the following steps:

1. The value must be non-`null` and compatible with the record type `Point`.
2. Java retrieves the value of each record component in declaration order using the corresponding accessor (`x()`, `y()`).
3. Each component must match its corresponding pattern. Only when the **entire** pattern matches are the pattern variables considered initialized and usable.

The number of positions in a record pattern must **equal the exact number of components**. For example, `Point` has two components, so `Point(int a)` is missing a position and will not compile. The pattern type must also be compatible with the component type: `Point(String a, int b)` is invalid because the first component has type `int`.

You can write the type explicitly or use `var` to let the compiler infer it:

~~~java
// Both are valid for record Point(int x, int y).
if (value instanceof Point(int a, int b)) {
    System.out.println(a + b);
}

if (value instanceof Point(var a, var b)) {
    System.out.println(a + b);
}
~~~

Here both `a` and `b` of the `var` patterns are inferred as `int`. `var` appears in the component list of a record pattern and does not mean the variables are dynamically typed; their types are determined at compile time. You cannot use `value instanceof var v` as a top-level type pattern instead of `Point(var a, var b)`.

**Note on accessors:** When destructuring, a record pattern uses the component's accessor. If the record defines a custom accessor with its own logic, matching uses that logic; an exception thrown by an accessor during record pattern matching is wrapped by Java 21 into a `MatchException` with the original exception as its cause. Therefore, avoid putting unpredictable side effects in accessors.

## 4. Scope (flow scoping) and conditions

A pattern variable is not a variable that can be read everywhere after an `if` statement. Java only allows using it where control flow guarantees that the pattern has matched.

~~~java
Object input = new Point(2, 4);

// Valid: when checking x > 0, Point has already matched, so x is already bound.
if (input instanceof Point(var x, var y) && x > 0) {
    System.out.println("y = " + y); // y = 4
}
~~~

On the right-hand side of `&&` and inside the `if` body, `x` and `y` exist if the left-hand side is true. Conversely, you cannot use them arbitrarily in the `else` branch, after the `if`, or on the right-hand side of `||` when that branch can execute because the pattern **did not match**.

~~~java
// The following snippets illustrate compile errors and are not part of a runnable program.

// Invalid: x may not be initialized on the right-hand side of ||.
// if (input instanceof Point(var x, var y) || x > 0) { ... }

// Invalid: x is no longer guaranteed to be in scope after the if.
// if (input instanceof Point(var x, var y)) { System.out.println(x); }
// System.out.println(x);
~~~

A `switch` using a record pattern also limits the variables to the `when` guard and the corresponding `case` branch; names in other branches are not automatically shared. Avoid declaring duplicate pattern variable names within the same record pattern (for example, `Point(int x, int x)`).

## 5. Nested patterns: component variables at multiple levels

When a component contains another record, you can destructure multiple levels in a single check:

~~~java
record Point(int x, int y) {}
record LabeledPoint(String label, Point point) {}

Object candidate = new LabeledPoint("A", new Point(4, 7));
if (candidate instanceof LabeledPoint(String name, Point(var px, var py))) {
    System.out.println(name + ": " + px + ", " + py); // A: 4, 7
}
~~~

In the pattern `LabeledPoint(String name, Point(var px, var py))`:

- `name` extracts the `label` component of the outer record.
- `Point(var px, var py)` is a **nested record pattern** applied to the `point` component; `px` and `py` extract `x` and `y` of the inner record.
- If `point` is `null`, the `Point(...)` pattern does not match, so the `if` branch does not execute and none of the variables in this pattern are successfully bound.

This style is suitable when you need multiple components of a nested data structure. If you only need to keep the inner record as a whole, use `LabeledPoint(var name, var point)` to bind the `point` component to a variable of type `Point`.

## 6. `null`: distinguishing the record object from component values

**A `null` value never matches a record pattern itself.** Therefore, `value instanceof Point(var x, var y)` returns `false` if `value == null`; a nested `Point(...)` also fails when the record value at that position is `null`.

However, a component with a reference type **can be `null`**. A component type pattern using `var` (or an unconditionally matching explicit type) can receive `null` at that position:

~~~java
record Note(String text) {}

Object value = new Note(null);
if (value instanceof Note(var message)) {
    System.out.println(message == null); // true
}
~~~

Therefore, distinguish carefully:

- `new Note(null) instanceof Note(var text)`: **matches**, `text` is assigned `null`.
- `new LabeledPoint("B", null) instanceof LabeledPoint(var label, Point(var x, var y))`: **does not match**, because the `Point(...)` record pattern does not accept `null`.
- `new LabeledPoint("B", null) instanceof LabeledPoint(var label, var point)`: **matches**, `point == null`.

Do not rely on "the record matched" to conclude that all reference components are non-`null`. With `switch` on a nullable value, handle it explicitly with `case null` or according to the input contract.

## 7. Using pattern variables in `switch`

Since Java 21, `switch` supports record patterns and `when` guards. Pattern variables can be used directly in the guard and branch of that same pattern:

~~~java
static String classify(Object value) {
    return switch (value) {
        case Point(int x, int y) when x == y -> "Đường chéo: " + x;
        case Point(var x, var y) -> "Điểm: " + x + ", " + y;
        case null -> "null";
        default -> "Kiểu khác";
    };
}
~~~

- The first branch catches a `Point` with `x == y`; the `when` guard can use the matched `x` and `y`.
- The next branch catches the remaining `Point` instances.
- `case null` handles a `null` input value, while `default` handles other types.
- **Branch order matters:** an earlier general pattern can *dominate* a narrower pattern, causing a compile error on the later branch. Place branches with specific guards before the general `Point(var x, var y)` branch.

## 8. Generic records and type inference

With a generic record, the compiler can infer the type argument and component variable types from context:

~~~java
record Box<T>(T value) {}

Box<String> box = new Box<>("Java");
if (box instanceof Box(var text)) {
    System.out.println(text.toUpperCase()); // JAVA
}
~~~

In this example `text` has type `String`, inferred from `Box<String>`. Record patterns do not remove Java's *type erasure* rules: do not treat destructuring as an automatic runtime verification of every object's generic type. Patterns using explicit generic types must still satisfy the compiler's safe cast rules.

## 9. Complete runnable example on Java 21+

Save as **`RecordComponentPatternsDemo.java`**:

~~~java
public class RecordComponentPatternsDemo {
    record Point(int x, int y) {}
    record LabeledPoint(String label, Point point) {}
    record Box<T>(T value) {}

    static String format(Object value) {
        if (value instanceof LabeledPoint(String label, Point(var x, var y))) {
            return label + ": (" + x + ", " + y + ")";
        }
        return "Không khớp";
    }

    static String classify(Object value) {
        return switch (value) {
            case Point(int x, int y) when x == y -> "Đường chéo: " + x;
            case Point(var x, var y) -> "Điểm: " + x + ", " + y;
            case null -> "null";
            default -> "Kiểu khác";
        };
    }

    public static void main(String[] args) {
        Object candidate = new Point(3, 5);
        if (candidate instanceof Point(int x, int y) && x > 0) {
            System.out.println("Tổng tọa độ: " + (x + y));
        }

        System.out.println(format(new LabeledPoint("A", new Point(4, 7))));
        System.out.println(format(new LabeledPoint("B", null)));
        System.out.println(classify(new Point(6, 6)));
        System.out.println(classify(new Point(3, 5)));
        System.out.println(classify(null));

        Box<String> box = new Box<>("Java");
        if (box instanceof Box(var text)) {
            System.out.println("Nhãn: " + text.toUpperCase());
        }

        record Note(String text) {}
        Object note = new Note(null);
        if (note instanceof Note(var text)) {
            System.out.println("Text null? " + (text == null));
        }
    }
}
~~~

Compile and run with JDK 21 or later:

~~~bash
javac --release 21 RecordComponentPatternsDemo.java
java RecordComponentPatternsDemo
~~~

Output:

~~~text
Tổng tọa độ: 8
A: (4, 7)
Không khớp
Đường chéo: 6
Điểm: 3, 5
null
Nhãn: JAVA
Text null? true
~~~

The program demonstrates: binding two primitive components, a nested record pattern, a mismatch caused by a `null` inner record, a `switch` with a guard, generic type inference, and the case where a `null` reference component still matches `var`.

## 10. Common mistakes and how to avoid them

| Mistake | Cause and fix |
| --- | --- |
| Writing `Point(int x)` when the record has two components | Incorrect arity; provide all patterns in declaration order: `Point(int x, int y)`. |
| Using a `String` pattern for an `int` component | Incompatible type; use `int` or `var`. |
| Using `x` after an `if` without a guaranteed match | Pattern variables have *flow scope*; use them inside the `if` body or a branch proven to have matched the pattern. |
| Using the same name `x` for two components in one pattern | Duplicate variable declaration; give each component a distinct name. |
| Assuming `Point(...)` matches `null` | A record pattern itself does not match `null`; distinguish that from a reference component being `null`. |
| Assuming `var` is a flexible runtime type | `var` has its type statically inferred at compile time. |
| Destructuring a regular class like a record | Record patterns only apply to record class types; for regular classes use type patterns and appropriate getters. |
| Using `_` as an unnamed pattern in Java 21 without preview enabled | Java 21 does not have unnamed patterns in standard mode; use a named variable, e.g., `var unused`. |
| Placing `case Point(var x, var y)` before a narrower `Point` branch | The general branch can dominate later branches; place specific patterns first. |
| Running with JDK 17 or habitually adding `--enable-preview` | Record pattern syntax is standard since JDK 21; use JDK 21+ without preview. |

## 11. Self-check

1. Given `record Range(int start, int end) {}`, write an `instanceof` check to bind both components to `start` and `end`, then compute `end - start`. Can the two pattern variable names **differ** from the component names?
2. Given `record User(String name, Box<String> email) {}`, explain why `User(var name, Box(var email))` does not match if the `email` component contains `null`, whereas `User(var name, var box)` can match with `box == null`.
3. In a `switch` containing `case Point(var x, var y)` and `case Point(int x, int y) when x == y`, which branch must come first, and why?

Suggested answers: (1) `if (obj instanceof Range(int a, int b)) { int length = b - a; }` (and yes, pattern variable names can differ from component names); (2) the nested `Box(...)` record pattern does not match `null`, whereas `var box` in the component position can receive `null`; (3) the branch with the `x == y` guard must come before the general branch to avoid dominance.

## References

- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440).
- [Oracle Java SE 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html).
- [Java Language Specification 21, `14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30).
