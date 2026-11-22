# Match a record and extract its components at the same time

## 1. The problem to solve

A `record` groups related data into a clear data type. For example, `record Point(int x, int y)` represents a point with two coordinates. When receiving a value of a general type such as `Object`, a program often has to do two things: check whether it is a `Point`, and then extract the `x` and `y` components to process them.

Before record patterns, you could use a *type pattern* with `instanceof` and then call the accessor methods:

```java
record Point(int x, int y) {}

static void printSum(Object candidate) {
    if (candidate instanceof Point p) {
        int x = p.x();
        int y = p.y();
        System.out.println(x + y);
    }
}
```

A **record pattern** combines the type check and component extraction right at the pattern matching site:

```java
static void printSum(Object candidate) {
    if (candidate instanceof Point(int x, int y)) {
        System.out.println(x + y);
    }
}
```

The two snippets above assume `Point` is declared in the same scope. In the second example, `x` and `y` are **new local variables bound when the pattern matches**, not newly declared fields in `Point`.

## 2. How does a record pattern work?

Given the declaration:

```java
record Point(int x, int y) {}
```

The pattern `Point(int a, int b)` expresses three requirements:

1. The value under test must be compatible with the record type `Point`.
2. The first component, of type `int`, is extracted and bound to variable `a`; the second component is bound to `b`.
3. The component patterns must also match. With `int a` and `int b`, the corresponding integer values are bound directly.

The names `a` and `b` are chosen by the pattern author; they **do not have to** match the component names `x` and `y`. Order is what determines the mapping: `Point(int first, int second)` extracts the first component and then the second, in the record's declaration order. A pattern can use `var` so Java infers the component types, for example `Point(var x, var y)`.

The pattern syntax is `Point(int x, int y)`, **not** `new Point(...)` or `record Point(...)`. A record pattern does not create a new `Point`, does not mutate the original value, and is not a standalone destructuring assignment syntax. It checks and deconstructs a record in a context that supports pattern matching, such as `instanceof` or a `switch` `case` branch.

**Distinguishing two easily confused patterns:**

| Pattern | When matched, what do we have? |
| --- | --- |
| `candidate instanceof Point p` | A variable `p` referencing the whole record; you must call `p.x()` and `p.y()` to get the components. |
| `candidate instanceof Point(int x, int y)` | Two variables `x` and `y` already holding the corresponding components; no need to call accessors inside the `if` body. |

## 3. Complete runnable Java 21 example

Create a file named `RecordPatternDemo.java` with the following content:

```java
public class RecordPatternDemo {
    record Point(int x, int y) {}
    record Segment(Point start, Point end) {}

    static String describe(Object value) {
        return switch (value) {
            case Point(int x, int y) ->
                    "Point(" + x + ", " + y + ")";
            case Segment(Point(int x1, int y1), Point(int x2, int y2)) ->
                    "Segment[(" + x1 + ", " + y1 + ") -> ("
                            + x2 + ", " + y2 + ")]";
            case null -> "null";
            default -> "Không phải Point hoặc Segment";
        };
    }

    public static void main(String[] args) {
        Object candidate = new Point(3, 5);

        if (candidate instanceof Point(int x, int y)) {
            System.out.println("Tổng tọa độ: " + (x + y));
        }

        System.out.println(describe(candidate));
        System.out.println(describe(
                new Segment(new Point(1, 2), new Point(4, 6))));
        System.out.println(describe("khác"));
        System.out.println(describe(null));
    }
}
```

Use **JDK 21 or later** and run:

```bash
javac RecordPatternDemo.java
java RecordPatternDemo
```

Output:

```text
Tổng tọa độ: 8
Point(3, 5)
Segment[(1, 2) -> (4, 6)]
Không phải Point hoặc Segment
null
```

Step-by-step explanation:

- `candidate` holds a `Point(3, 5)`, so `instanceof Point(int x, int y)` matches and binds `x = 3`, `y = 5`. The expression `x + y` produces `8`.
- In `switch`, the branch `case Point(int x, int y)` both selects the right record type and extracts the two coordinates to build the string.
- `Segment` has two components of type `Point`. The pattern `Segment(Point(int x1, int y1), Point(int x2, int y2))` matches from the outside in: it recognizes `Segment`, deconstructs `start` and `end`, and then deconstructs both `Point` values. As a result, we access all four coordinates directly.
- The string `"khác"` does not match the record patterns, so it falls into `default`.
- `case null` specifically handles a `null` value for the `switch` expression.

## 4. Variable scope and matching conditions

Variables declared in a pattern can only be used where the compiler knows the pattern has matched:

```java
Object candidate = new Point(2, 7);
if (candidate instanceof Point(int x, int y)) {
    System.out.println(x * y); // 14
}
// System.out.println(x); // Compile error: x is not in scope here.
```

Similarly, `x` and `y` in a `case` branch belong to that branch's scope. You cannot use variables from the `Point` branch in the `Segment` branch or outside the `switch`. When the pattern does not match, Java does not bind those variables.

With `instanceof`, a `null` value makes the check evaluate to `false`; the `if` body does not run. With `switch` on a reference type, if the input may be `null`, handle it explicitly with `case null` as in the example; if there is no matching branch to handle `null`, `switch` can throw a `NullPointerException`.

Nested patterns must also match **at every level**. For instance, the pattern `Segment(Point(int x1, int y1), Point(int x2, int y2))` requires both `start` and `end` to hold non-null `Point` values. If a component holds `null`, the corresponding nested pattern does not match; prepare another branch when your data allows that case.

## 5. When to use them and common pitfalls

Record patterns are especially useful when handling structured data in `if` or `switch`: coordinates, value ranges, events with explicit fields, or records containing records. They eliminate repetitive accessor calls and make the data structure being used clear right at the condition or handling branch. If you only need a single component or need to keep the whole record to pass it along, a type pattern like `Point p` is sometimes easier to read.

Pitfalls to avoid:

- **Using the wrong Java version.** `record` has been a standard feature since Java 16, but **record patterns were finalized in Java 21**. This lesson uses Java 21 syntax and runs without `--enable-preview` on JDK 21. You cannot compile the `Point(int x, int y)` pattern with standard Java 17.
- **Mixing up component order.** Variable names are arbitrary, but values always follow the record's component order. Given `record Range(int min, int max)`, the pattern `Range(int max, int min)` still binds the variable `max` to the **first** component, causing a subtle semantic bug that is easy to miss.
- **Using them with regular classes.** Only records support this record deconstruction pattern form; a class with getters `getX()`, `getY()` does not automatically work as a record pattern.
- **Using variables out of scope.** `x` and `y` only exist when the relevant pattern has matched and within the scope Java allows.
- **Forgetting to handle other types or null.** With a `switch` whose selector has type `Object`, make sure to cover other types (such as `default`) and account for `null` if the input value can be null.

## 6. Self-check

Suppose we have `record Size(int width, int height) {}` and the value `Object value = new Size(4, 6);`:

```java
if (value instanceof Size(int width, int height)) {
    System.out.println(width * height);
}
```

The result is `24`. The pattern both confirms that `value` is a `Size` and binds `width` and `height` in the exact component order. If you swap the two variable names to `height`, `width` in the pattern, the program still compiles because both have type `int`, but the meaning of each value is reversed. This is why you must check the **record declaration order**, rather than relying on variable names in the pattern.

**Remember:** `Point(int x, int y)` is a record pattern: it performs a type check and extracts the components in the same pattern-matching expression. When records have nested structures, you can nest record patterns to extract data at multiple levels, while still paying attention to the Java version, variable scope, component order, and `null` values.
