# Record Patterns and Component Pattern Lists (Java 21+)

## 1. What Problem Do Record Patterns Solve?

A `record` is a concise data type for representing a group of named components, such as `record Point(int x, int y) {}`. When you need to check whether an object is a `Point` and immediately extract its two coordinates, the traditional approach uses a type pattern and then calls the accessors:

```java
record Point(int x, int y) {}

static void printPoint(Object value) {
    if (value instanceof Point point) {
        System.out.println(point.x() + ", " + point.y());
    }
}
```

Starting in Java 21, a **record pattern** combines two operations into a single construct: checking the record type and deconstructing its components into variables:

```java
static void printPointWithPattern(Object value) {
    if (value instanceof Point(int x, int y)) {
        System.out.println(x + ", " + y);
    }
}
```

With `new Point(3, 5)`, the `if` branch executes and prints `3, 5`. With an object that is not a `Point`, the branch does not execute. The names `x` and `y` in the pattern are **new variables declared upon matching**, not a method call or arguments to construct a record.

**Version requirement:** Record patterns were standardized in **Java 21 (JEP 440)**; using JDK 21 or later does not require `--enable-preview`. Java 17 supports type patterns in `instanceof` but does not yet have stable record patterns.

## 2. Structure of a Record Pattern

General form:

```text
RecordType(componentPattern1, componentPattern2, ..., componentPatternN)
```

- `RecordType` must be a `record` type, for example `Point`.
- The parentheses contain an ordered **component pattern list**, consisting of one pattern for **each component** declared in the record.
- Each sub-pattern can declare a variable with a specific type (`int x`, `String name`), use `var` for type inference, or be another record pattern.
- The number and order of sub-patterns strictly follow the record's component list and **do not depend on the variable names** chosen by the author.

Example:

```java
record Person(String name, int age) {}

// Person(String fullName, int years) corresponds to:
// first component: name -> variable fullName
// second component: age  -> variable years
static void show(Object value) {
    if (value instanceof Person(String fullName, int years)) {
        System.out.println(fullName + " - " + years);
    }
}
```

In `Person(String fullName, int years)`, the two variables `fullName` and `years` receive their values via the `name()` and `age()` accessors after a successful match. Renaming the variables does not change which component is read.

| Element in Pattern | Role | Example |
| --- | --- | --- |
| `int x` | Pattern with primitive type, declares variable `x` | `Point(int x, int y)` |
| `var x` | Infers variable type from the corresponding component | `Point(var x, var y)` |
| `String name` | Type pattern for a reference component | `Person(String name, int age)` |
| `Point(int x, int y)` | Nested record pattern, continues deconstructing | `Segment(Point(int x, int y), var end)` |

**A “component pattern list” is not a `java.util.List`.** It is the list of patterns *in the syntax* of a record pattern, separated by commas.

A record with no components still has an empty record pattern: `record Marker() {}` can be tested with `value instanceof Marker()`.

## 3. Matching Process and Variable Scope

For `value instanceof Point(int px, int py)`, the steps can be understood in order:

1. Check that `value` is not `null` and can match the record type `Point`.
2. Retrieve the corresponding components using the record's accessors (`x()` and `y()`).
3. Match each component against the pattern at the **same position** in the list.
4. Only when **all component patterns** match does the record pattern match, and the variables `px` and `py` become available in the matching branch.

```java
Object value = new Point(4, 9);

if (value instanceof Point(int left, int right)) {
    int sum = left + right;     // left = 4, right = 9
    System.out.println(sum);    // 13
}
// left and right are not in scope here.
```

A record pattern checks **structure and types**; it does not automatically compare contents against a fixed value. `Point(int x, int y)` still matches when `x != y`; if you want to enforce a condition such as `x == y`, check it inside the `if` body or use `when` in a `switch` branch.

Note that accessors can be overridden in a record. The pattern uses the result of the accessor to obtain the component; you should not assume that deconstruction is always a pure field read that cannot throw an exception.

## 4. Nested Record Patterns

Records can contain other records:

```java
record Point(int x, int y) {}
record Segment(Point from, Point to) {}
```

How to extract the coordinates using accessors:

```java
static void printSegmentOld(Object value) {
    if (value instanceof Segment segment) {
        Point from = segment.from();
        Point to = segment.to();
        if (from != null && to != null) {
            System.out.println(from.x() + "," + from.y()
                    + " -> " + to.x() + "," + to.y());
        }
    }
}
```

A nested record pattern expresses the same structure directly at the match site:

```java
static void printSegment(Object value) {
    if (value instanceof Segment(
            Point(int fromX, int fromY),
            Point(int toX, int toY))) {
        System.out.println(fromX + "," + fromY
                + " -> " + toX + "," + toY);
    }
}
```

The outer pattern requires a `Segment`; each component `from` and `to` must in turn match `Point(int, int)`. With `new Segment(new Point(0, 0), new Point(3, 4))`, the output is `0,0 -> 3,4`. If either endpoint is `null`, the **nested record pattern `Point(...)` does not match**, so the `if` branch does not execute.

You can mix different levels of deconstruction. `Segment(Point(int x, int y), var end)` only unpacks `from` into its two coordinates, while `end` receives the entire `to` component. This is one advantage of the component pattern list: each position can hold a pattern suited to your processing needs.

## 5. Complete Example: `instanceof`, `switch`, `when`, and `null`

Save the following file as **RecordPatternDemo.java**. This is a complete program that runs on Java 21+:

```java
public class RecordPatternDemo {
    record Point(int x, int y) {}
    record Segment(Point from, Point to) {}

    static String describe(Object input) {
        return switch (input) {
            case null -> "null";
            case Point(int x, int y) when x == y ->
                    "diagonal:" + x;
            case Point(int x, int y) ->
                    "point:" + x + "," + y;
            case Segment(
                    Point(int x1, int y1),
                    Point(int x2, int y2)) ->
                    "segment:" + x1 + "," + y1
                    + " -> " + x2 + "," + y2;
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Point(2, 2)));
        System.out.println(describe(new Point(2, 5)));
        System.out.println(describe(
                new Segment(new Point(0, 0), new Point(3, 4))));
        System.out.println(describe(null));
        System.out.println(describe(
                new Segment(null, new Point(3, 4))));
    }
}
```

Compile and run:

```bash
javac RecordPatternDemo.java
java RecordPatternDemo
```

Exact output:

```text
diagonal:2
point:2,5
segment:0,0 -> 3,4
null
other
```

Explanation:

- `case Point(int x, int y) when x == y` executes only when it both matches `Point` and satisfies the condition `x == y`. Variables from the component pattern are used directly in `when`.
- `case Point(int x, int y)` handles the remaining `Point` values. Place the guarded branch **before** the general branch so the general branch does not shadow the specialized one.
- `case Segment(Point(...), Point(...))` matches only if both endpoints are `Point` instances that can be deconstructed.
- `case null` explicitly handles `input == null`. In a Java 21 `switch`, do not expect `default` to handle `null` automatically.
- `default` handles all remaining values, including a `Segment` with a `null` component where the nested pattern fails to match.

In a `switch` with patterns, branch ordering is also subject to Java's **dominance** rules: a general branch can make a more specific branch placed after it invalid at compile time.

## 6. `var` and Type Inference in Component Patterns

There is no need to repeat component types when the compiler can infer them:

```java
record Point(int x, int y) {}

static void print(Object input) {
    if (input instanceof Point(var x, var y)) {
        // The compiler infers that both x and y are int.
        System.out.println(x + y);
    }
}
```

With generic records, static type information also aids inference:

```java
record Box<T>(T value) {}

static void showUppercase(Box<String> box) {
    if (box instanceof Box(var text)) {
        // text is inferred as String in the context of Box<String>.
        System.out.println(text.toUpperCase());
    }
}
```

The example above assumes `value` is non-`null` when calling `toUpperCase()`. `var` **does not automatically perform a non-null check** for every component. When you want to ensure a component is a `String` from a record declared with `Object`, you can use an explicit type pattern, such as `Entry(String text)` with `record Entry(Object value) {}`.

For generic records, writing explicit type arguments (for example, `Box<String>(String text)`) is also subject to compile-time safe type-conversion rules. You cannot arbitrarily take a raw `Box` and force the pattern to `Box<String>` if doing so would require an unchecked conversion.

## 7. Be Careful with `null` in Component Pattern Lists

You need to distinguish between **the value matched against the record pattern** and **the value of a component**:

- `null` itself **does not match** `Point(int x, int y)` or any record pattern.
- If a component is `null` and the pattern at that position is also a **nested record pattern** (such as `Point(int x, int y)`), that branch does not match.
- A **type pattern at a component position** can match `null` when it is an unconditional pattern for the component's declared type. Therefore, you cannot conclude that *every null component causes a record pattern to fail*.

Example illustrating the difference:

```java
record Entry(Object value) {}

static void checkNullComponents() {
    Entry item = new Entry(null);
    System.out.println(item instanceof Entry(var anyValue)); // true
    System.out.println(item instanceof Entry(String text));   // false
}
```

`Entry(var anyValue)` extracts a component with static type `Object` and can match a `null` value; `Entry(String text)` requires the component to match type `String`, so it does not match `null` in this case. Both still require the **outer `Entry` object to be non-`null`**.

When handling potentially missing data, express your `null` policy clearly in business logic. With `switch`, add `case null` for the selector whenever it may receive `null`.

## 8. Common Syntax and Conceptual Mistakes

**Wrong number of components:** A record pattern must have a pattern for each component. For `record Point(int x, int y) {}`, writing `Point(int x)` or `Point(int x, int y, int z)` is a compile-time error because `Point` has exactly two components.

**Confusing position and name:** `Point(int y, int x)` still compiles because both components are `int`, but variable `y` receives the first component (`x()`), and variable `x` receives the second component (`y()`). Names do not route values; **order decides**.

**Using a record pattern on a regular class:** The syntax `Customer(String name)` is valid only if `Customer` is a matching record; record patterns do not automatically deconstruct arbitrary classes with getters.

**Confusing a pattern with a constructor:** `Point(int x, int y)` in `instanceof`/`case` does not create a new object. Creating a record requires `new Point(1, 2)`. A pattern only tests for a match and declares variables.

**Duplicate variable names:** `Point(int x, int x)` is invalid because two component patterns both declare a variable named `x`. To check that two coordinates are equal, use two distinct names and compare them.

**Using variables out of scope:** Pattern variables are only available where a match is guaranteed, such as the true branch of an `if` or the body of the corresponding `case`. Do not use those variables in a non-matching branch.

**Wrong `case` order:** A general matching branch can shadow a specific branch; organize `when` clauses and cases intentionally so the program compiles and handles cases in the right order.

**Using `_` in default Java 21:** Unnamed patterns/variables are a preview feature in Java 21; if you need Java 21 exercises without preview enabled, use a regular variable name (which may remain unused).

**Confusing with record patterns in enhanced `for`:** Java 21 does not support placing a record pattern in the header of an enhanced `for` loop. Use `for (var item : items)` and then match `item` inside the loop body.

## 9. Self-Check Exercises

**Exercise 1.** Given `record RGB(int red, int green, int blue) {}`, write a pattern to extract the three components and print their sum. Solution:

```java
static void printBrightness(Object color) {
    if (color instanceof RGB(int r, int g, int b)) {
        System.out.println(r + g + b);
    }
}
```

With `new RGB(10, 20, 30)`, the output is `60`. This is the sum of the three values in the example, not a standard color brightness formula.

**Exercise 2.** Given `record Segment(Point from, Point to) {}`, what information does the pattern `Segment(Point(var x, var y), var end)` extract?

Answer: `x` and `y` are the two coordinates of `from`; `end` is the entire `to` component (of type `Point`). Because `from` is checked with a nested record pattern, the pattern does not match if `from == null`. If you do not need to split `to` into coordinates, this form is simpler than nesting another `Point(...)`.

**Exercise 3.** Why does `Point(int a, int b)` not automatically guarantee `a == b`?

Answer: The component pattern list matches by **type and position**; it declares variables `a` and `b` without imposing a relational condition between the two values. Use `if (a == b)` inside the matched branch or `when a == b` in `case`.

## 10. Key Takeaways

A record pattern has the form **`RecordName(component pattern list)`**. It checks the record type and deconstructs components in their declared order; each position can be a type pattern, `var`, or a nested record pattern. The list must match the exact number of components, variables are only in scope when the pattern matches, and `null` must be considered at each nesting level. Combining record patterns with `instanceof` and `switch` lets you express structured data extraction directly at the decision point.

References:
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [Oracle Java 21 — Java Language Changes](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html)
