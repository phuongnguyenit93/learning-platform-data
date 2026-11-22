# Component pattern containing another record

## 1. When a record contains another record

In real-world data, a record often has a component whose type is another record. For example, a delivery order has a destination, and the destination has coordinates:

```java
record Point(int x, int y) {}
record Place(String name, Point coordinate) {}
record Delivery(String id, Place destination) {}
```

Here, the data structure has three levels:

```text
Delivery
├── id: String
└── destination: Place
    ├── name: String
    └── coordinate: Point
        ├── x: int
        └── y: int
```

If a variable of type `Object` holds a `Delivery`, you may want to both verify that it is the right data type and extract `id`, the destination name, and both coordinates. A **nested record pattern** lets you do that in a single pattern match, instead of multiple type checks and accessor calls.

The key point to understand is that **a component of an outer record can itself be a record**. You place *another record pattern* in that component's position to continue deconstructing at the inner level.

## 2. Writing nested patterns that match the structure

With the three declarations above, the full pattern is:

```java
Delivery(String id, Place(String name, Point(int x, int y)))
```

Reading from left to right:

1. `Delivery(...)` checks whether the value is a matching `Delivery`.
2. The first component of `Delivery` is `id`, which is bound to the variable `String id`.
3. The second component is `destination` of type `Place`. Instead of only binding a `Place` variable, you use `Place(...)` to deconstruct it further.
4. The first component of `Place` is `name`; the second component is a `Point`. The pattern `Point(int x, int y)` extracts the two coordinates as well.

For example:

```java
Object value = new Delivery(
        "D-01",
        new Place("Kho A", new Point(2, 7))
);

if (value instanceof Delivery(
        String id,
        Place(String name, Point(int x, int y)))) {
    System.out.println(id + ": " + name + ", " + (x + y));
}
```

This code prints `D-01: Kho A, 9`. The variables `id`, `name`, `x`, and `y` are only bound after the entire nested pattern matches. This is an illustrative snippet, assuming the three record types are declared in the same scope.

**Component order matters more than variable names.** In `Place(String name, Point coordinate)`, the pattern in the first position corresponds to `name`, and the one in the second position corresponds to `coordinate`. Variable names inside the pattern can differ from the original component names and Java will still compile as long as the types are compatible.

| Actual component | Pattern at corresponding position | Extracted value in example |
| --- | --- | --- |
| `Delivery.id` | `String id` | `"D-01"` |
| `Delivery.destination` | `Place(...)` | Continues deconstructing `Place` |
| `Place.name` | `String name` | `"Kho A"` |
| `Place.coordinate` | `Point(...)` | Continues deconstructing `Point` |
| `Point.x` | `int x` | `2` |
| `Point.y` | `int y` | `7` |

A nested record pattern does not instantiate a new record, does not modify the original record, and does not automatically turn components into global variables. It expresses the type-checking and data-extraction steps in a single pattern matching expression.

## 3. Complete runnable Java 21 example

Save the entire program as **`NestedRecordPatternDemo.java`**:

```java
public class NestedRecordPatternDemo {
    record Point(int x, int y) {}
    record Place(String name, Point coordinate) {}
    record Delivery(String id, Place destination) {}

    static String describe(Object input) {
        return switch (input) {
            case Delivery(String id,
                    Place(String name, Point(int x, int y))) ->
                    id + " đến " + name + " (" + x + ", " + y + ")";

            case Delivery(String id, Place place) ->
                    id + ": có Place nhưng chưa đủ dữ liệu";

            case Delivery delivery ->
                    delivery.id() + ": chưa khớp mẫu lồng";

            case null -> "Không có dữ liệu";
            default -> "Không phải Delivery";
        };
    }

    public static void main(String[] args) {
        Object first = new Delivery(
                "D-01", new Place("Kho A", new Point(2, 7)));

        if (first instanceof Delivery(
                String id, Place(String name, Point(int x, int y)))) {
            System.out.println("Tách được: " + id + ", "
                    + name + ", tổng = " + (x + y));
        }

        System.out.println(describe(first));
        System.out.println(describe(
                new Delivery("D-02", new Place("Kho B", null))));
        System.out.println(describe(new Delivery("D-03", null)));
        System.out.println(describe("khác"));
        System.out.println(describe(null));
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac NestedRecordPatternDemo.java
java NestedRecordPatternDemo
```

Expected output:

```text
Tách được: D-01, Kho A, tổng = 9
D-01 đến Kho A (2, 7)
D-02: có Place nhưng chưa đủ dữ liệu
D-03: chưa khớp mẫu lồng
Không phải Delivery
Không có dữ liệu
```

Explanation of each case:

- **`D-01`:** `Delivery`, `Place`, and `Point` are all present, so the three-level pattern matches. `x` is `2` and `y` is `7`; adding them yields `9`.
- **`D-02`:** `destination` is a `Place`, but `coordinate` is `null`. The inner `Point(int x, int y)` pattern does not match, so the first branch is skipped; the `Delivery(String id, Place place)` branch handles the remaining value because `Place` is still present.
- **`D-03`:** `destination` is `null`. Neither the three-level nested pattern nor the pattern requiring a non-null `Place` matches. The `case Delivery delivery` branch catches the remaining `Delivery` record.
- **`"khác"`:** Not a `Delivery`, so it falls into `default`.
- **`null`:** Handled separately by `case null`, and does not enter the record patterns.

Note that the `case Delivery delivery` branch is a **general fallback branch for any `Delivery` that did not match the two branches above**. The string `"chưa khớp mẫu lồng"` ("did not match nested pattern") describes that accurately; you should not infer that every value reaching this branch has `destination == null`.

## 4. How deep should you nest?

You do not have to deconstruct every level. Choose the depth that matches the data you need to process.

**Check only the outer record and keep the inner record intact:**

```java
if (value instanceof Delivery(String id, Place place)) {
    // id is a String; place remains a Place object.
    System.out.println(id + " -> " + place.name());
}
```

**Deconstruct one level deeper while keeping `Point` intact:**

```java
if (value instanceof Delivery(
        String id, Place(String name, Point point))) {
    // point remains a Point; you can call point.x(), point.y().
    System.out.println(id + " -> " + name + ": " + point.x());
}
```

**Deconstruct all three levels:**

```java
if (value instanceof Delivery(
        String id, Place(String name, Point(int x, int y)))) {
    // x and y are now two int variables.
    System.out.println(id + " -> " + name + ": " + x + ", " + y);
}
```

The three snippets above are standalone syntax examples in a context where the records and a `value` variable are already declared. Deeper patterns specify more components that must match. If the code only needs `place` to pass to another method, keeping `Place` intact is often easier to read.

You can use `var` to let Java infer the type at a component position:

```java
if (value instanceof Delivery(
        var id, Place(var name, Point(var x, var y)))) {
    System.out.println(id + " -> " + name + ": " + (x + y));
}
```

With the declarations at the start of the lesson, `id` and `name` are inferred as `String`, while `x` and `y` are `int`. `var` **does not mean skipping a component**: it is still a variable-binding pattern. Every component position inside a record pattern's parentheses must have a corresponding pattern.

## 5. Null and matching of the entire pattern

A multi-level deconstruction pattern succeeds only when **every nested record pattern inside it also matches**. If `destination` is `null`, it cannot match `Place(...)`. If `destination` is present but `coordinate` is `null`, it cannot match `Point(...)`.

This is a useful difference compared to chained accessor calls:

```java
Delivery delivery = new Delivery("D-02", new Place("Kho B", null));

// This approach can throw NullPointerException:
// int x = delivery.destination().coordinate().x();

// This approach checks the structure before using x, y:
if (delivery instanceof Delivery(
        String id, Place(String name, Point(int x, int y)))) {
    System.out.println(x + y);
} else {
    System.out.println("Thiếu thông tin tọa độ");
}
```

For `D-02`, the `if` statement does not enter the true branch and prints `Thiếu thông tin tọa độ`. There is no call to `x()` on a `null` reference inside the pattern.

With `instanceof`, a `null` expression on the left-hand side always causes a record pattern not to match. With `switch`, you should include `case null` if the input data can be `null`; omitting appropriate handling can lead to a `NullPointerException`. When a nested pattern fails, subsequent `case` branches can continue to be evaluated in order.

A record **can contain `null` reference components**, unless the developer explicitly adds validation rules in the constructor. Simply declaring `record Place(String name, Point coordinate)` does not forbid `coordinate == null`.

## 6. Comparison with manual accessor code

Before using nested record patterns, one way to write this using type patterns and accessors was:

```java
if (value instanceof Delivery delivery) {
    Place place = delivery.destination();
    if (place != null && place.coordinate() != null) {
        Point point = place.coordinate();
        System.out.println(delivery.id() + " -> " + place.name()
                + " (" + point.x() + ", " + point.y() + ")");
    }
}
```

This approach is valid when `value` is a declared variable and the records from the beginning of the lesson exist. The reader has to track intermediate variables `delivery`, `place`, `point`, and the null checks. A nested record pattern places the exact structure to check directly in the condition:

```java
if (value instanceof Delivery(
        String id, Place(String name, Point(int x, int y)))) {
    System.out.println(id + " -> " + name + " (" + x + ", " + y + ")");
}
```

The advantage is fewer accessor calls and a clear expression of the required data structure. However, overly deeply nested patterns can be hard to read; when a structure is complex, it is better to deconstruct step by step or extract a helper method rather than cramming all the logic onto a single line.

## 7. Common mistakes and limitations

1. **Using an older JDK.** Record patterns, including nested record patterns, are a standard feature starting in **Java 21**. Regular records became standard earlier, but syntax like `Delivery(String id, Place(...))` does not work on Java 17 under normal compilation. The example runs on JDK 21 without `--enable-preview`.
2. **Omitting a pattern for a component.** `record Delivery(String id, Place destination)` has two components, so `Delivery(Place(...))` is invalid: you cannot skip the position of `id`. You can write `Delivery(var id, Place(...))` when you do not care about the value of `id`.
3. **Swapping positions.** `Place(Point point, String name)` does not match the declaration `Place(String name, Point coordinate)`. Patterns always rely on component order and types, not on whether two variable names look semantically similar.
4. **Assuming every nested component is always non-null.** Records do not automatically guarantee that reference values are non-`null`. The nested pattern `Point(...)` does not match if the component holding `Point` is `null`; you need a fallback branch when data may be missing.
5. **Trying to use deconstruction syntax with a regular class.** `Place(...)` is only a record pattern if `Place` is a matching record type. A regular class with getters identical to record components does not automatically support this syntax.
6. **Using variables out of scope.** Variables such as `id`, `name`, `x`, and `y` in `instanceof` are only in scope in the branch where Java knows the pattern matched. Variables in one `case` branch do not become shared variables across all `switch` branches.
7. **Placing a general branch before a specific branch.** In a `switch`, a `case Delivery delivery` placed before `case Delivery(String id, Place(...))` covers all `Delivery` values and causes the specific branch after it to be *dominated*, resulting in a compile-time error. Order specific patterns before general ones.

## 8. Self-check

Given the declarations:

```java
record Engine(String model, int power) {}
record Car(String brand, Engine engine) {}
```

And:

```java
Object vehicle = new Car("A", new Engine("E-1", 120));

if (vehicle instanceof Car(
        String brand, Engine(String model, int power))) {
    System.out.println(brand + "/" + model + "/" + power);
}
```

The program prints `A/E-1/120` because `vehicle` is a `Car`, the `engine` component is an `Engine`, and both `model` and `power` components are successfully bound. If changed to `new Car("A", null)`, the entire nested pattern fails to match and the `if` body does not execute.

**Remember:** When a component contains another record, you can place a record pattern in that component's position and deconstruct recursively across multiple levels. Whether a match succeeds depends on matching types, matching component order, and whether the records being deconstructed are non-null; bound variables can only be used within the scope where the pattern matched.
