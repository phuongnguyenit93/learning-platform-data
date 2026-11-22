# Recognizing Record Patterns to Extract `record` Data — Java 17+/21

A **record pattern** allows checking whether an object has a specific `record` type and **extracting the record's components into variables** right inside the check. This has been a **standard feature since Java 21 (JEP 440)**. In Java 17, `record` is already a standard feature, but **record pattern syntax is not yet standard**.

~~~java
record Point(int x, int y) {}

Object value = new Point(2, 3);
if (value instanceof Point(int x, int y)) { // JDK 21+
    System.out.println(x + y);              // 5
}
~~~

`Point(int x, int y)` is a **record pattern**, distinct from `new Point(2, 3)` which is an **object creation** expression. When the pattern matches, it extracts the record's two components and binds them to variables `x` and `y` without needing to cast and separately call `point.x()` and `point.y()`.

## 1. Distinguishing `record`, Type Patterns, and Record Patterns

| Construct | Meaning | Standard Version |
| --- | --- | --- |
| `record Point(int x, int y) {}` | Declares a record class with two components | Java 16+ |
| `obj instanceof Point p` | Checks type, binds the entire object to `p` | Java 16+ |
| `obj instanceof Point(int x, int y)` | Checks type **and deconstructs two components** | Java 21+ |
| `case Point(int x, int y) -> ...` | Uses a record pattern in switch | Java 21+ |

With a **type pattern**, you get a variable `p` representing the entire record and read components via `p.x()` and `p.y()`. With a **record pattern**, variables `x` and `y` directly represent each component. A record pattern **is not a standalone destructuring assignment**: it must appear in a pattern-supporting context, such as `instanceof` or `switch`.

**Important rule:** the number, order, and types of nested patterns must correspond to the record's component list. `Point(int x, int y)` matches the two components by **declaration order**, not by the variable names you choose.

## 2. Program Running on JDK 21+

Create a UTF-8 file named **`RecordPattern21Demo.java`**:

~~~java
public class RecordPattern21Demo {
    record Point(int x, int y) {}
    record Segment(Point start, Point end) {}
    record Person(String name, int age) {}

    static String describe(Object value) {
        return switch (value) {
            case null -> "null";
            case Point(int x, int y) -> "point=" + x + "," + y;
            case Segment(Point(int sx, int sy), Point(int ex, int ey)) ->
                    "segment=" + sx + "," + sy + "->" + ex + "," + ey;
            case Person(String name, int age) when age >= 18 ->
                    "adult=" + name;
            case Person(String name, int age) ->
                    "minor=" + name;
            default -> "other";
        };
    }

    static int sum(Object value) {
        if (value instanceof Point(int x, int y)) {
            return x + y;
        }
        return -1;
    }

    static int squaredDistance(Object value) {
        if (value instanceof Segment(
                Point(int x1, int y1),
                Point(int x2, int y2))) {
            int dx = x2 - x1;
            int dy = y2 - y1;
            return dx * dx + dy * dy;
        }
        return -1;
    }

    public static void main(String[] args) {
        Object[] values = {
            null,
            new Point(2, 3),
            new Segment(new Point(0, 0), new Point(2, 3)),
            new Person("Mai", 20),
            new Person("Nam", 15),
            new Segment(null, new Point(1, 1)),
            42
        };

        for (Object value : values) {
            System.out.println(describe(value));
        }

        System.out.println("sum=" + sum(new Point(2, 3)));
        System.out.println("notPoint=" + sum("hello"));
        System.out.println("distance="
                + squaredDistance(new Segment(
                        new Point(0, 0), new Point(2, 3))));
        System.out.println("missingStart="
                + squaredDistance(new Segment(null, new Point(1, 1))));
    }
}
~~~

Use **JDK 21 or later** in PowerShell (Windows) or Bash (Linux/macOS):

~~~bash
java -version
javac -version
javac -encoding UTF-8 RecordPattern21Demo.java
java RecordPattern21Demo
~~~

**Exact expected stdout** of the `java RecordPattern21Demo` command alone:

~~~text
null
point=2,3
segment=0,0->2,3
adult=Mai
minor=Nam
other
other
sum=5
notPoint=-1
distance=13
missingStart=-1
~~~

`java -version` and `javac -version` print versions depending on the JDK installed on your machine. With JDK 21, the example above **does not require `--enable-preview`**.

## 3. Nested Record Patterns: Multi-Level Deconstruction

`Segment` contains two components of type `Point`, so you can write a nested pattern:

~~~java
if (value instanceof Segment(
        Point(int x1, int y1),
        Point(int x2, int y2))) {
    System.out.println(x1 + "," + y1);
    System.out.println(x2 + "," + y2);
}
~~~

When it succeeds, `value` must be a `Segment` and both `start` and `end` must match the two `Point(...)` patterns. The components are extracted into **four `int` variables**.

If `Segment` contains `start == null`, the `Point(int x1, int y1)` pattern for that component **does not match**, so the entire nested pattern fails. That is why the demo prints `missingStart=-1` instead of raising an error from calling `start.x()` on null.

The deconstruction outcome can be read via this diagram:

~~~mermaid
flowchart TD
    A["value"] --> B{"Segment?"}
    B -- No --> F["Pattern does not match"]
    B -- Yes --> C{"start matches Point?"}
    C -- No --> F
    C -- Yes --> D{"end matches Point?"}
    D -- No --> F
    D -- Yes --> E["Bind x1, y1, x2, y2"]
~~~

For reference-type components, Java can use appropriate patterns such as `String name` for further checking/binding. Record patterns are composed from multiple subpatterns rather than allowing only primitive `int`.

## 4. `null`, `when`, and Pattern Order in `switch`

The pattern `Point(int x, int y)` does not match a `null` selector. In a **Java 21 switch**, we can handle it explicitly:

~~~java
String label = switch (value) {
    case null -> "missing";
    case Point(int x, int y) when x == 0 && y == 0 -> "origin";
    case Point(int x, int y) -> "point";
    default -> "other";
};
~~~

Here:

- `case null` specifically handles a null selector; **`default` does not automatically replace `case null`**.
- `when` adds a condition **after the pattern matches**.
- The origin branch must be placed **before** the general `Point(...)` branch. Reversing the order can cause the origin branch to be shadowed by a broader pattern (*dominated case*) and fail to compile.
- The `case ... ->` form does not fall through to other labels.

**Record patterns do not solve every `null` case:** a null selector needs `case null` or a prior check; a null component can cause a nested pattern not to match, depending on the inner pattern. Deconstructing components invokes the record's accessors; avoid creating accessors with side effects or exceptions if you want checks to remain predictable.

## 5. JDK 17 Compatible Approach — Using Record Accessors and Type Patterns

To run on **JDK 17** without using record patterns, check the type with `instanceof Point p`, then read components with `p.x()` and `p.y()`.

Create a UTF-8 file **`RecordPattern17Compat.java`**:

~~~java
public class RecordPattern17Compat {
    record Point(int x, int y) {}
    record Segment(Point start, Point end) {}
    record Person(String name, int age) {}

    static String describe(Object value) {
        if (value == null) {
            return "null";
        }
        if (value instanceof Point point) {
            return "point=" + point.x() + "," + point.y();
        }
        if (value instanceof Segment segment
                && segment.start() != null
                && segment.end() != null) {
            Point start = segment.start();
            Point end = segment.end();
            return "segment=" + start.x() + "," + start.y()
                    + "->" + end.x() + "," + end.y();
        }
        if (value instanceof Person person) {
            return (person.age() >= 18 ? "adult=" : "minor=")
                    + person.name();
        }
        return "other";
    }

    static int sum(Object value) {
        if (value instanceof Point point) {
            return point.x() + point.y();
        }
        return -1;
    }

    static int squaredDistance(Object value) {
        if (value instanceof Segment segment
                && segment.start() != null
                && segment.end() != null) {
            int dx = segment.end().x() - segment.start().x();
            int dy = segment.end().y() - segment.start().y();
            return dx * dx + dy * dy;
        }
        return -1;
    }

    public static void main(String[] args) {
        Object[] values = {
            null,
            new Point(2, 3),
            new Segment(new Point(0, 0), new Point(2, 3)),
            new Person("Mai", 20),
            new Person("Nam", 15),
            new Segment(null, new Point(1, 1)),
            42
        };

        for (Object value : values) {
            System.out.println(describe(value));
        }
        System.out.println("sum=" + sum(new Point(2, 3)));
        System.out.println("notPoint=" + sum("hello"));
        System.out.println("distance="
                + squaredDistance(new Segment(
                        new Point(0, 0), new Point(2, 3))));
        System.out.println("missingStart="
                + squaredDistance(new Segment(null, new Point(1, 1))));
    }
}
~~~

Run with **JDK 17+**:

~~~bash
javac -encoding UTF-8 RecordPattern17Compat.java
java RecordPattern17Compat
~~~

**Exact expected stdout** of `java RecordPattern17Compat` is **identical** to the stdout block in Section 2. The Java 17 version calls accessors explicitly and checks null for nested records, without having Java 21's direct deconstruction syntax.

## 6. Limitations and Common Mistakes

| Misconception | Correct Understanding |
| --- | --- |
| "Since Java 17 has `record`, it already has `record pattern`." | Records are standard since Java 16; record patterns are standard since Java 21 |
| "`new Point(2,3)` is the same as `Point(int x,int y)`." | One constructs a record, the other is a pattern to match and deconstruct |
| "A record pattern modifies or copies the record." | It only checks and binds components, without creating a new record |
| "`Point(int y,int x)` automatically matches component names by variable name." | Patterns map **by position**, not by variable name |
| "Nested patterns automatically skip null components." | Subpatterns must match; null can cause the entire pattern to fail |
| "Placing `case Point(...)` before `case Point(...) when ...`." | The general branch can dominate the specialized branch |
| "`default` always catches a null selector." | Null must be handled separately when business logic requires it |
| "JDK 17 compiles files containing `case Point(int x,int y)`." | Not in standard Java 17 mode |
| "Variables `x` and `y` remain usable after a failed check." | Variables are only valid in the **flow scope** where the pattern is proven to match |

Record components are part of the data model; avoid overusing overly long, deeply nested record patterns if introducing intermediate variables or calling accessors would be easier to read.

## 7. Self-Check Exercises

1. Given `Object p = new Point(4, 5);`, if it matches `Point(int x, int y)`, what is `x + y`?  
   *Answer:* `9`.
2. Does a record pattern check runtime type or only variable names?  
   *Answer:* It checks the type and then deconstructs components in declaration order.
3. For `Segment(null, new Point(1,1))`, does a nested pattern requiring both `Point(...)` match?  
   *Answer:* No.
4. In a Java 21 switch, can `case Point(int x,int y) when x == 0` be used?  
   *Answer:* Yes, placed before the general Point branch.
5. Can `record Point` run on JDK 17? Are record patterns standard in JDK 17?  
   *Answer:* Records work, but record patterns are not yet standard.
6. How do you extract Point components with JDK 17?  
   *Answer:* `if (obj instanceof Point p)` and then `p.x()` and `p.y()`.

## Checklist

- [ ] Distinguish a `record` declaration from `record pattern` syntax.
- [ ] Remember that record patterns are standard since **Java 21**, whereas records and `instanceof` type patterns are already available on Java 17.
- [ ] Read components in the right order and respect variable scope after a pattern match.
- [ ] Understand nested record patterns and the null-component scenario.
- [ ] Use `when` and `case null` intentionally in Java 21 switches.
- [ ] Know how to substitute `instanceof` + accessors if the environment still uses JDK 17.

**Conclusion:** Record patterns let you extract record components **right during the type check**, even for nested records. Use JDK 21+ to run this syntax; for JDK 17 projects, the same task can still be accomplished via `instanceof` type patterns and accessor methods.
