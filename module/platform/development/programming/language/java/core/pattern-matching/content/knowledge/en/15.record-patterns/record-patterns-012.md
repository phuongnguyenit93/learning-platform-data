# When do record patterns make code clearer?

**Applies to:** Java 21 and later. Record patterns were finalized in Java 21 (JEP 440), without needing to enable preview. Java 17 has record types but does not yet support record pattern syntax.

## 1. Goal: state the data to extract right at the type check

A record describes a group of data components. When a variable has a general type (such as Object), we often have to check the type, obtain the cast object, and then call each accessor.

With record patterns, we express both the **record type** and the **components to extract** in the same pattern. For example, given the following two records:

~~~java
record Point(int x, int y) {}
record Segment(Point start, Point end) {}
~~~

- The pattern **Point(int x, int y)** checks whether the value is a Point and, if it matches, binds the two components to the variables x and y.
- The pattern **Segment(Point(int startX, int startY), Point(int endX, int endY))** goes one level deeper: extracting the coordinates of both endpoints of the line segment.
- This is **matching and deconstruction syntax**, not a constructor call; it does not create a new Point or Segment.

**Quick rule of thumb:** a record pattern is worth using when a processing branch needs multiple components of the same record, especially when there are nested records, and the data shape helps the reader understand that branch.

## 2. Before and after: reducing intermediate steps while preserving meaning

Suppose we need to format the coordinates of a Segment. A Segment is only considered complete when both start and end are non-null Points. The two methods below use the two records from section 1 and return equivalent results.

**Before — using a type pattern and then calling accessors:**

~~~java
static String showOld(Object candidate) {
    if (!(candidate instanceof Segment segment)) {
        return "Không có đoạn thẳng đầy đủ";
    }

    Point start = segment.start();
    Point end = segment.end();
    if (start == null || end == null) {
        return "Không có đoạn thẳng đầy đủ";
    }

    return "(%d, %d) -> (%d, %d)".formatted(
            start.x(), start.y(), end.x(), end.y());
}
~~~

**After — using nested record patterns:**

~~~java
static String showNew(Object candidate) {
    if (candidate instanceof Segment(
            Point(int startX, int startY),
            Point(int endX, int endY))) {
        return "(%d, %d) -> (%d, %d)".formatted(
                startX, startY, endX, endY);
    }
    return "Không có đoạn thẳng đầy đủ";
}
~~~

In the later version, the condition directly expresses a requirement: **the input is a Segment and both of its endpoints are Points**. The reader sees the four coordinates being used without having to trace the start and end variables and four accessor calls. This is an improvement in clarity when the focus of the branch is the **data structure**.

Note: if start or end is null, the nested pattern Point(...) **does not match**, so execution falls through to the branch returning the invalid message. If the business logic needs to distinguish between “not a Segment” and “a Segment missing a point”, write separate handling branches; do not merge the two cases just to shorten the code.

## 3. Situations where record patterns make code easier to understand

| Situation | Why it is clearer | Sign to use it |
| --- | --- | --- |
| Checking a type and reading multiple components | The condition both verifies the type and lists the values to use | A branch reads x, y, or multiple components |
| Nested record data | Reveals the shape required by the processing; reduces intermediate variables | Segment containing two Points; Order containing an address record |
| Processing branches that depend on data shape | Each branch of the switch describes the applicable case | Classifying different records from Object or a supertype |
| Simple auxiliary conditions after deconstruction | Variables are clearly named, and the **when** condition expresses a concise rule | Two coordinates are equal, a value exceeds a threshold |

For example: a branch handling a line segment whose two endpoints coincide can be written with the pattern Segment(Point(...), Point(...)) combined with **when startX == endX && startY == endY**. The reader immediately sees the data being compared and the applicable condition, instead of inferring them from chains of accessors.

Clarity depends on **variable names and nesting depth**: startX, startY, endX, endY are more helpful than a, b, c, d. When a pattern is nested too many levels deep, extract it into processing steps or methods whose names express the business logic.

## 4. Complete Java 21 example: using switch to classify

The following example checks nested patterns, a **when** condition, null component values, and a null selector. This is a standalone program that can be compiled and run:

~~~java
public class RecordPatternClarityDemo {
    record Point(int x, int y) {}
    record Segment(Point start, Point end) {}

    static String describe(Object value) {
        return switch (value) {
            case Segment(Point(int x1, int y1), Point(int x2, int y2))
                    when x1 == x2 && y1 == y2 ->
                    "Point: (%d, %d)".formatted(x1, y1);

            case Segment(Point(int x1, int y1), Point(int x2, int y2)) ->
                    "Segment: (%d, %d) -> (%d, %d)"
                            .formatted(x1, y1, x2, y2);

            case null -> "Null";
            default -> "Not a complete Segment";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(
                new Segment(new Point(1, 2), new Point(4, 6))));
        System.out.println(describe(
                new Segment(new Point(3, 3), new Point(3, 3))));
        System.out.println(describe(
                new Segment(new Point(1, 2), null)));
        System.out.println(describe(null));
    }
}
~~~

Save the file as **RecordPatternClarityDemo.java** and run it with JDK 21+:

~~~bash
javac RecordPatternClarityDemo.java
java RecordPatternClarityDemo
~~~

Output:

~~~text
Segment: (1, 2) -> (4, 6)
Point: (3, 3)
Not a complete Segment
Null
~~~

Explanation of branch order:

1. The branch with **when** comes first because it is more specific: it only matches when both Points exist and have the same coordinates.
2. The Segment branch without an auxiliary condition handles the remaining line segments that have two valid Points. If this general branch were placed first, the branch with the same pattern and **when** below it would be dominated and fail to compile.
3. A Segment with end = null does not match the nested Point(...) pattern, so it falls into default.
4. A null selector value is handled by **case null**. With switch pattern matching, you should not rely on **default** to handle a null selector; lacking an appropriate null branch can cause a NullPointerException.

In **instanceof**, if the pattern does not match, the condition is false. Variables introduced by the pattern can only be used in regions where the compiler determines the pattern has matched. In **switch**, pattern variables are scoped to their corresponding branch.

## 5. When is keeping accessors or a type pattern clearer?

**Only one component is needed.** If the processing is simply checking a Point and using only x, the following expression is already direct without needing to deconstruct y as well:

~~~java
if (candidate instanceof Point point && point.x() > 0) {
    System.out.println(point.x());
}
~~~

**The record object itself is needed.** If you repeatedly pass the Point into other methods or invoke behavior on the object, keeping the point variable can be more convenient than only extracting its components.

**Complex business conditions.** When multiple rules, validity checks, or decisions do not depend directly on the shape of the record, a method such as isEligible(order) expresses intent more clearly than a long nested pattern with contrived conditions. A record pattern only extracts data; by itself, it does not replace business validation.

**Deeply nested structures.** When a single line has multiple nested records and a long list of variable names, the detailed structure can obscure the processing goal. Splitting into named steps makes maintenance easier.

**Non-record data types.** Record patterns apply to record types. For regular Java classes, use a type pattern (for example, instanceof Customer customer) and the appropriate methods; you cannot arbitrarily use Customer(...) syntax to deconstruct a regular class.

## 6. Notes to avoid trading correctness for brevity

- **Version:** use JDK 21+ to compile standard record patterns. JDK 19 and 20 previously offered the feature in preview; JDK 17 does not support record patterns.
- **Null:** a null selector in instanceof does not match; a null component can cause a specific nested record pattern not to match. Design explicit null and missing-data branches if the business logic needs to distinguish them.
- **Switch order:** place specific cases with **when** conditions before general cases of the same type to avoid dominance errors.
- **Variable scope:** extracted variables are only in scope where the pattern is guaranteed to have matched; do not use them in non-matching branches.
- **Meaningful names:** prefer names that express roles (startX, endY, city) and break lines at the boundaries of nested records.
- **Preserve semantics:** when switching from accessors to record patterns, re-verify behavior with wrong-type inputs, records containing null, a null selector, and every path of the switch.

## 7. Deciding for yourself whether to use it

Ask yourself: (1) is the input data a record; (2) does this branch need multiple components, or need to show the nested structure immediately; (3) is the pattern with named variables shorter and easier to read than the accessor steps; (4) are null cases and business conditions still handled properly?

If those answers favor record patterns, use them to bring the **data shape** right to where the processing decision is made. If only one accessor is needed or the pattern becomes cluttered, a type pattern and a clearly named method will be easier to understand.