# Basic Record Pattern Syntax in Java

A **record pattern** is a syntax used to test whether a value is an instance of a `record` type and, at the same time, *deconstruct* the record's components into named variables. This feature was finalized in **Java 21 (JEP 440)**; Java 19 and 20 only provided preview versions. The examples below target Java 21+ and do not require `--enable-preview`.

## 1. Quick Look at the Syntax

Suppose we define a record:

```java
record Point(int x, int y) {}
```

The record has two components, in declaration order: `x` (of type `int`) and `y` (of type `int`). The snippet below demonstrates a record pattern on the right-hand side of `instanceof` (placed inside a method):

```java
Object value = new Point(3, 5);

if (value instanceof Point(int x, int y)) {
    System.out.println(x + y); // 8
}
```

In the expression `value instanceof Point(int x, int y)`:

1. `value` is the value to be tested.
2. `Point` is the record type we want to match.
3. `(int x, int y)` is the list of **component patterns**, corresponding to each record component by **position**.
4. When the match succeeds, Java assigns the value of the first component to `x` and the second component to `y`; these variables are only in scope where the compiler knows the match has succeeded.

General form:

```text
RecordType(ComponentPattern1, ComponentPattern2, ...)
```

This is a **pattern**, not a constructor call. `new Point(3, 5)` creates an object; `Point(int x, int y)` describes how to test and deconstruct an existing object. Java uses the record's accessor methods, such as `x()` and `y()`, to retrieve the components; the pattern does not modify the record.

## 2. Explicit Types or Using `var`

The two forms below are equivalent when `Point` declares `int x, int y`:

```java
if (value instanceof Point(int x, int y)) {
    System.out.println(x + y);
}

if (value instanceof Point(var a, var b)) {
    System.out.println(a + b);
}
```

- `int x` is a **type pattern**: it explicitly states the component's type and declares the variable `x`.
- `var a` lets the compiler infer the type from the record declaration; both `a` and `b` have type `int`, not a dynamic type.
- Variable names (`x`, `y`, `a`, `b`) are chosen by the author. **Component order** determines which data is extracted; the names do not need to match the component names in the record.
- The number of component patterns must equal the number of record components. For `Point(int x, int y)`, the pattern `Point(int x)` has the wrong arity and will not compile.
- Each pattern's type must be compatible with its corresponding component type. `Point(String x, int y)` is invalid because the first component has type `int`.

You may also encounter records with no components, such as `record Marker() {}`; the corresponding pattern is `Marker()`.

## 3. Match Conditions and Variable Scope

`instanceof` with a record pattern performs two tasks: confirming the matching record type and testing the component patterns. If the match fails, the `if` branch does not execute; variables declared in the pattern cannot be used arbitrarily outside it.

```java
Object input = new Point(4, 7);

if (input instanceof Point(var x, var y) && x >= 0) {
    System.out.println("x=" + x + ", y=" + y);
}
// Do not use x or y here: outside the guaranteed match scope.
```

With the `&&` operator, the right-hand side is evaluated only when the left-hand side is true, so `x` can appear in `x >= 0`. After the condition, the variables exist only in places where the compiler determines the pattern has definitely matched.

**A `null` value does not match any record pattern.** For example, `null instanceof Point(var x, var y)` evaluates to `false`. If a record contains another record, a nested pattern also requires the corresponding component to have a matching non-null value to continue deconstructing; see the `Segment` example below.

## 4. Nested Record Patterns

A record can contain another record:

```java
record Segment(Point start, Point end) {}
```

You can test and deconstruct multiple levels in a single pattern:

```java
Object shape = new Segment(new Point(1, 2), new Point(4, 6));

if (shape instanceof Segment(Point(var x, var y), var end)) {
    System.out.println("Start: (" + x + ", " + y + ")");
    System.out.println("End: " + end);
}
```

Here, `Segment(...)` matches the outer record; `Point(var x, var y)` deconstructs the `start` record into two coordinates; `var end` keeps the `end` component intact (inferred as type `Point`). If `start` is `null`, the `Point(var x, var y)` pattern does not match, so the entire `Segment(...)` pattern fails. This combines type checking and data structure extraction without manually calling a chain of accessors in the success branch.

## 5. Using in `switch`

Since Java 21, `switch` also officially supports pattern matching (JEP 441). You can place a record pattern directly after `case`:

```java
String kind = switch (value) {
    case Point(var x, var y) -> x == 0 && y == 0 ? "Origin" : "Other point";
    case null -> "null";
    default -> "Other type";
};
```

- The `case Point(var x, var y)` branch both identifies `Point` and provides `x` and `y` to the expression on the right-hand side of `->`.
- `case null` explicitly handles `null`; without a matching branch for `null`, this `switch` would throw a `NullPointerException` when given `null`.
- `default` handles values other than `Point`. When multiple cases can match, pay attention to ordering and `switch` dominance rules; this basic example uses only a single record pattern.

## 6. Complete, Runnable Program

Save the following code to a file named **`RecordPatternBasics.java`**:

```java
public class RecordPatternBasics {
    record Point(int x, int y) {}
    record Segment(Point start, Point end) {}

    static String describe(Object value) {
        if (value instanceof Point(int x, int y)) {
            return "Point: x=" + x + ", y=" + y;
        }
        return "Not a Point";
    }

    static String startInfo(Object value) {
        if (value instanceof Segment(Point(var x, var y), var end)) {
            return "Start: (" + x + ", " + y + "), end=" + end;
        }
        return "No valid start point";
    }

    static String classify(Object value) {
        return switch (value) {
            case Point(var x, var y) -> x == 0 && y == 0 ? "Origin" : "Other point";
            case null -> "null";
            default -> "Other type";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Point(3, 5)));
        System.out.println(describe("hello"));
        System.out.println(startInfo(new Segment(new Point(1, 2), new Point(4, 6))));
        System.out.println(startInfo(new Segment(null, new Point(4, 6))));
        System.out.println(classify(new Point(0, 0)));
        System.out.println(classify(new Point(3, 5)));
        System.out.println(classify(null));
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac -encoding UTF-8 --release 21 RecordPatternBasics.java
java RecordPatternBasics
```

**Expected output:**

```text
Point: x=3, y=5
Not a Point
Start: (1, 2), end=Point[x=4, y=6]
No valid start point
Origin
Other point
null
```

Explanation: the first call deconstructs `Point(3, 5)` into `x=3` and `y=5`. The string `"hello"` is not a `Point`, so it takes the fallback branch. The first `Segment` has a valid `start`; the `end` value is printed via the record's `toString()` method, producing `Point[x=4, y=6]`. The second `Segment` has `start=null`, so it does not match the nested pattern. The three calls to `classify` distinguish the origin, another point, and `null`, respectively.

## 7. Comparison with Type Patterns and Common Mistakes

| Syntax | Meaning |
| --- | --- |
| `value instanceof Point p` | Type pattern: checks the type and binds the entire record to `p`; components are read via `p.x()`, `p.y()`. |
| `value instanceof Point(int x, int y)` | Record pattern: checks the type and immediately deconstructs the two components into `x`, `y`. |
| `value instanceof Point(var x, var y)` | Record pattern with component type inference. |
| `value instanceof Segment(Point(var x, var y), var end)` | Nested record pattern: deconstructs `Segment` and then deconstructs `Point`. |

Mistakes to avoid:

1. **Writing `Point(x, y)` without declaring a type or `var`.** Here `x` and `y` are not expressions for comparing values; you must write `Point(var x, var y)` or `Point(int x, int y)`.
2. **Wrong number or order of components.** Patterns deconstruct according to the record's structure and declaration order, not by matching variable names. Check the `record` definition before writing a pattern.
3. **Using pattern variables outside the matched scope.** Only use them in the success branch or in conditions where the compiler proves the pattern has matched.
4. **Assuming `null` objects will be deconstructed.** Record patterns do not match `null`; handle this case explicitly when needed, especially with `switch`.
5. **Using deconstruction syntax on regular classes.** Record patterns require a `record` type. For regular classes, use a type pattern such as `obj instanceof SomeClass c` and then call the appropriate accessor methods.
6. **Confusing preview syntax with standard Java 21 syntax.** Record patterns are stable in Java 21, but some other pattern syntax, such as using `_` for unnamed patterns, is not a finalized feature in Java 21; do not include them in code that must run with `--release 21`.

## 8. Self-Check

Given `record Point(int x, int y) {}`:

- If `Object v = new Point(8, 9);` and `v instanceof Point(var a, var b)` succeeds, `a + b` equals **17**.
- Given `Segment(null, new Point(4, 6))`, the pattern `Segment(Point(var x, var y), var end)` **does not match** because `start=null` cannot be deconstructed by `Point(...)`.
- If you only need the whole `Point` object to call multiple methods, the type pattern `Point p` may be easier to read; if you need the components right away, choose a record pattern.

**Official references:** [Oracle Java 21 – Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html), [JEP 440 – Record Patterns](https://openjdk.org/jeps/440), [JEP 441 – Pattern Matching for switch](https://openjdk.org/jeps/441).
