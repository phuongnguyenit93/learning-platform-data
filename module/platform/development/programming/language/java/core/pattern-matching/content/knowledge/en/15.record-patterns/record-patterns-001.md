# What Is a Record Pattern in Java?

## 1. Concept

A **record pattern** is a form of *pattern matching* in Java that allows you to **check whether a value belongs to a target `record` type and, if it matches, deconstruct the record's components into named variables** right at the point of the check. Record patterns can also be nested to extract data located deep within multiple records.

For example, given a record representing a two-dimensional point:

```java
record Point(int x, int y) {}
```

You can write:

```java
Object value = new Point(2, 5);

if (value instanceof Point(int x, int y)) {
    System.out.println(x + y); // 7
}
```

Here, `Point(int x, int y)` is a **record pattern**, not a constructor call. The `Point` part checks the record type; `(int x, int y)` describes how to match and bind the two components corresponding to `x()` and `y()`. When the match succeeds, the variable `x` receives `2` and `y` receives `5`; they can be used inside the `if` branch.

**Version:** `record` became a standard feature in **Java 16**; **record patterns** were previewed in Java 19–20 and became a standard feature in **Java 21** (JEP 440). The examples below use Java 21 or later and do not require `--enable-preview`. Java 17 can declare records, but cannot use record pattern syntax yet.

## 2. How Does a Record Pattern Work?

With the declaration `record Point(int x, int y) {}`, Java provides the component accessor methods `x()` and `y()`. To understand the benefit of a record pattern, compare:

**Checking only the type with a type pattern:**

```java
if (value instanceof Point p) {
    int x = p.x();
    int y = p.y();
    System.out.println(x + y);
}
```

**Checking the type and deconstructing components with a record pattern:**

```java
if (value instanceof Point(int x, int y)) {
    System.out.println(x + y);
}
```

Both examples extract data from a `Point`, but the record pattern directly expresses the structure of the data to be matched. Java performs the type check and uses the record's accessors to retrieve the component values; the developer does not need to manually call each accessor in the branch body.

A record pattern has the general structure:

```text
RecordName(componentPattern1, componentPattern2, ...)
```

- **RecordName** must be a suitable `record` type.
- The number and order of component patterns must correspond to the record declaration; matching is **positional**, not based on variable names. For example, `Point(int y, int x)` is still valid syntax, but naming the variables in that order can easily cause confusion.
- Each sub-pattern can bind a variable such as `int x`, use type inference with `var x`, or be another nested record pattern.
- Pattern variables can only be used within the scope where the compiler determines that the match has succeeded, such as the `if` body when the condition is true or the corresponding `case` branch.

You can replace explicit types with `var`:

```java
if (value instanceof Point(var x, var y)) {
    // For Point(int x, int y), Java infers x and y as int.
    System.out.println(x + ", " + y);
}
```

`var` in this example **does not mean dynamic typing**; the compiler infers the static type of each record component.

## 3. Complete Runnable Example: instanceof, switch, and Nested Record Patterns

Save the following code as **`RecordPatternDemo.java`**:

```java
public class RecordPatternDemo {
    record Point(int x, int y) {}
    record Segment(Point start, Point end) {}

    static String describe(Object value) {
        if (value instanceof Point(int x, int y)) {
            return "Điểm: (" + x + ", " + y + ")";
        }
        return "Không phải Point";
    }

    static String classify(Object value) {
        return switch (value) {
            case Point(int x, int y) when x == 0 && y == 0 ->
                    "Gốc tọa độ";

            case Point(int x, int y) ->
                    "Điểm (" + x + ", " + y + ")";

            case Segment(Point(int x1, int y1), Point(int x2, int y2)) ->
                    "Đoạn (" + x1 + ", " + y1 + ") -> ("
                            + x2 + ", " + y2 + ")";

            case null -> "Giá trị null";
            default -> "Loại khác";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Point(2, 5)));
        System.out.println(describe("text"));
        System.out.println(describe(null));

        System.out.println(classify(new Point(0, 0)));
        System.out.println(classify(
                new Segment(new Point(1, 2), new Point(3, 4))));
        System.out.println(classify(null));
    }
}
```

Compile and run with **JDK 21+**:

```bash
javac --release 21 RecordPatternDemo.java
java RecordPatternDemo
```

Output:

```text
Điểm: (2, 5)
Không phải Point
Không phải Point
Gốc tọa độ
Đoạn (1, 2) -> (3, 4)
Giá trị null
```

Explanation:

1. In `describe`, `Point(int x, int y)` only matches when `value` is a non-null `Point`; therefore, the string `"text"` and `null` go to the remaining branch.
2. In `switch`, the condition `when x == 0 && y == 0` specifically filters the origin point. The guarded branch is placed **before** the general `Point` branch so that it is not dominated by the general branch.
3. `Segment(Point(int x1, int y1), Point(int x2, int y2))` is a **nested record pattern**: Java matches `Segment`, continues matching the two `Point` values at `start` and `end`, and then binds the four coordinates.
4. `case null` handles null explicitly. In a `switch` using pattern matching, having only `default` does not mean null is handled: without a suitable null-handling branch, a null selector value can throw a `NullPointerException`.

## 4. Rules and Common Pitfalls

### A record pattern is not a constructor or a copy operation

`new Point(2, 5)` creates a new object; `Point(int x, int y)` in `instanceof` or `case` is a description of **the input value to be matched**. The pattern only extracts data from an existing object; it does not create a new `Point` and does not modify the record's components.

### Record patterns only deconstruct records

You cannot directly use the `SomeClass(...)` syntax as a record pattern for a regular class not declared with `record`. For regular objects, you can use a type pattern (`instanceof SomeClass s`) and then call the appropriate accessor methods.

### Component position and types must be correct

With `record Point(int x, int y) {}`, the pattern `Point(int x, int y)` matches two `int` components in the exact order. `Point(int x)` is missing a component; `Point(String x, String y)` has incompatible types and will not compile. The names `x` and `y` in the pattern are **new variable names**, not lookup keys for components by name.

### Distinguish between a null record and a null component

A `null` value does not match any record pattern; `null instanceof Point(int x, int y)` evaluates to `false`.

With a nested pattern, such as `Segment(Point(var a, var b), Point(var c, var d))`, if `start` or `end` is `null`, the corresponding `Point(...)` pattern **does not match**. That does not mean every record containing a null component cannot match: the result depends on the sub-pattern used to match that component.

### When an accessor has unusual behavior

A record pattern accesses components through the record's accessors. If an accessor is customized and throws an exception, the match may terminate with an exception instead of simply returning `false`. Therefore, accessors should be designed to reflect the data semantics of the record and avoid unexpected side effects.

### Do not confuse with type patterns and guard conditions

- `value instanceof Point p`: matches the type and binds the **entire object** to `p`.
- `value instanceof Point(int x, int y)`: matches the type and binds the **components** to `x` and `y`.
- `case Point(int x, int y) when x > 0 -> ...`: in addition to matching the record, there is a `when` guard condition on the `switch` branch. `when` is not part of the record pattern syntax itself.

## 5. When Should You Use It?

Record patterns are useful when data is modeled using records and the processing logic primarily focuses on **the structure and components** of the data: classifying values in a `switch`, handling multiple nested record layers, or writing case-by-case logic without repeatedly calling accessors manually.

For overly deep nested structures, a long pattern can become hard to read; consider breaking it into smaller steps or using a type pattern if the code actually needs the whole object. Record patterns support a data-oriented style, but they do not replace business validation, null control, and exception handling.

**Key takeaway:** `record` defines **the shape of data**; `record pattern` describes **the shape to match** and extracts the components in a single check.

### References

- Oracle Java 21 — Record Patterns: https://docs.oracle.com/en/java/javase/21/language/record-patterns.html
- JEP 440 — Record Patterns: https://openjdk.org/jeps/440
