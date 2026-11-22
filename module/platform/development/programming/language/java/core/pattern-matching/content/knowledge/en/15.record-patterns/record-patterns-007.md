# Record Patterns in `instanceof` (Java 21+)

## 1. What problem do record patterns solve?

A `record` describes data through its components (record components). When receiving a value of a broad type such as `Object`, we often want to both check whether it is the expected record and immediately extract its inner components for processing. A **record pattern** allows doing both directly in the `instanceof` operator, even when the components themselves are nested records.

Record patterns were finalized in **Java 21** (JEP 440). On Java 21 and later, the examples below use standard language features without needing `--enable-preview`. Java 17 supports `record` but **does not yet support record pattern syntax**; Java 19–20 provided the feature in preview.

## 2. Syntax and matching behavior

Suppose we declare:

```java
record Point(int x, int y) {}
```

We can check and deconstruct the data as follows:

```java
Object value = new Point(2, 5);
if (value instanceof Point(int x, int y)) {
    System.out.println(x + y); // 7
}
```

In `value instanceof Point(int x, int y)`:

- `Point` is the **record type to match**, and `(int x, int y)` is the **list of component patterns** in the exact declaration order; this is not a constructor call.
- Java first checks whether the value can be treated as a `Point`. If so, it retrieves the values from the `x()` and `y()` accessors and matches them sequentially against the two component patterns.
- When the entire pattern matches, the expression evaluates to `true` and the variables `x` and `y` are assigned values for use in the matching branch; if it does not match, the result is `false`.
- The pattern list must match the **exact number and types of the record's components**; you cannot write `Point(var x)` to omit the `y` component.

There are three related but distinct approaches:

| Syntax | Meaning |
| --- | --- |
| `value instanceof Point` | Only checks the type, without declaring variables to extract components. |
| `value instanceof Point p` | Type pattern: checks and assigns the whole record to `p`; requires calling `p.x()`, `p.y()` to retrieve data. |
| `value instanceof Point(int x, int y)` | Record pattern: checks the type and simultaneously deconstructs the components directly into `x` and `y`. |

You can use `var` so the compiler infers the static component types of the record:

```java
if (value instanceof Point(var x, var y)) {
    System.out.println(x * x + y * y);
}
```

Here `x` and `y` still have type `int`, because the two components of `Point` are of type `int`. `var` does not mean dynamic typing or `Object`.

## 3. Complete runnable example

Create the file **`RecordPatternInstanceofDemo.java`**:

```java
public class RecordPatternInstanceofDemo {
    record Point(int x, int y) {}
    record Marker(String label, Point point) {}

    public static void main(String[] args) {
        Object candidate = new Point(3, 4);

        if (candidate instanceof Point(int x, int y)) {
            System.out.println("Point: (" + x + ", " + y + ")");
            System.out.println("Distance squared: " + (x * x + y * y));
        }

        Object other = new Marker("A", new Point(7, 9));

        if (other instanceof Marker(var label, Point(var x, var y))) {
            System.out.println(label + " at (" + x + ", " + y + ")");
        }

        Object withNullNested = new Marker("B", null);
        System.out.println(
            withNullNested instanceof Marker(var label, Point(var x, var y))
        );

        Object absent = null;
        System.out.println(absent instanceof Point(var x, var y));
    }
}
```

Compile and run with **JDK 21 or later**:

```bash
javac --release 21 RecordPatternInstanceofDemo.java
java RecordPatternInstanceofDemo
```

Expected output:

```text
Point: (3, 4)
Distance squared: 25
A at (7, 9)
false
false
```

The last two lines return `false` because the nested `Point` record is `null` in the first case, and the entire value being tested is `null` in the second. The program does not throw a `NullPointerException` merely from performing `instanceof` on a `null` variable.

## 4. Nested record patterns

With a record containing another record:

```java
record Address(String city, String street) {}
record Customer(String name, Address address) {}
```

We can extract the city directly when checking the object:

```java
Object input = new Customer(
    "Lan",
    new Address("Da Nang", "Bach Dang")
);

if (input instanceof Customer(var name, Address(var city, var street))) {
    System.out.println(name + " - " + city + " - " + street);
    // Lan - Da Nang - Bach Dang
}
```

The outer pattern `Customer(...)` and the inner pattern `Address(...)` must **both match simultaneously**. Nesting depth can follow the record structure, but keep the code readable; if the condition becomes too long, you can use a type pattern and access the records step by step.

Notes on `null`:

- If the **target on the left-hand side of `instanceof`** is `null`, the record pattern does not match.
- If the `address` component is `null`, the nested `Address(...)` pattern does not match.
- A component pattern using `var`, such as `Customer(var name, var address)`, **can bind `null` to `address`**. Do not assume that every `null` reference component causes the record pattern to fail; the outcome depends on the sub-pattern. Check for `null` when you intend to use that component.

## 5. Combining conditions and variable scope

Pattern variables follow **flow scoping**: they can only be used in locations where the compiler knows the pattern has matched.

```java
record Point(int x, int y) {}

static boolean isInFirstQuadrant(Object value) {
    return value instanceof Point(var x, var y)
            && x >= 0
            && y >= 0;
}
```

The right-hand side of `&&` is evaluated only if the left-hand side matches, so `x` and `y` are valid to use. With `if`, the variables can be used inside the true branch:

```java
if (value instanceof Point(var x, var y) && x == y) {
    System.out.println("Trên đường chéo: " + x);
}
```

You can also use a **guard clause** style so that the variables remain in scope after an early-returning `if` statement:

```java
static int sumCoordinates(Object value) {
    if (!(value instanceof Point(int x, int y))) {
        return 0;
    }
    return x + y;
}
```

Conversely, the following snippet **does not compile** because the right-hand side of `||` can execute when the record pattern has not matched, leaving `x` unassigned:

```java
// Invalid: x is not available after || in this way.
if (value instanceof Point(var x, var y) || x > 0) {
    // ...
}
```

Avoid using `x` or `y` on execution paths where the pattern is not guaranteed to have matched.

## 6. Generic records and `instanceof` limitations

Records can be generic:

```java
record Box<T>(T value) {}
```

Due to **type erasure**, an expression with static type `Object` cannot be safely checked directly with `Box<String>(var item)` in `instanceof`: such a check would require an unchecked generic conversion. You can match the record with a wildcard and then check the component's type:

```java
Object obj = new Box<>("hello");

if (obj instanceof Box<?>(var item) && item instanceof String text) {
    System.out.println(text.toUpperCase()); // HELLO
}
```

When a variable already has the type `Box<String>`, the compiler can also infer the type argument for `Box(var item)`. Be sure to distinguish between the **static type of the expression** and the runtime type of the element when choosing a generic pattern.

## 7. When should you use it?

Record patterns in `instanceof` are especially suitable when:

- The input data has a general type (`Object`, an interface, or a supertype), and you need to handle a specific record shape.
- Your logic needs the **component fields** immediately, especially for nested structures.
- You want to combine type matching with business constraints using `&&`, such as `Point(var x, var y) && x >= 0`.

If you only need to know "is this a `Point`?", a plain `instanceof Point` is enough. If you need to access the record multiple times, keeping the object intact with `instanceof Point p` is sometimes clearer.

## 8. Common pitfalls and how to avoid them

1. **Running on an older JDK:** Java 17 does not recognize `Point(var x, var y)`; use JDK 21+ for the finalized syntax.
2. **Using record patterns with regular classes:** `Point(...)` requires `Point` to be a `record`; regular Java classes do not automatically support this deconstruction syntax.
3. **Missing or misordered components:** A record pattern matches against the record's component list, not by arbitrary variable names. The component count must match, and the pattern types must be compatible.
4. **Confusing `var` with dynamic casting:** `var` infers the declared type of the component; to narrow the runtime type inside a component, add an appropriate type pattern.
5. **Using variables on paths where matching is not guaranteed:** Pattern variables are not automatically method-scoped; pay attention to `&&`, `||`, negation, and `if` branches.
6. **Treating all `null` cases identically:** An outer record pattern does not match `null`; a nested record pattern does not match a `null` child record either; however, a component pattern like `var` can receive a `null` value.
7. **Assuming a record pattern is just direct field access:** At runtime, Java retrieves components through the record's accessor methods. If a custom accessor has unusual behavior, matching can be affected.

## 9. Self-check

Given `record Result(int code, String message) {}` and `Object response = new Result(200, "OK");`:

- Write an `instanceof` check that extracts `code` and `message` in a single expression.
- Print `message` only if `code == 200`, using `&&`.
- Try `response = null` and explain why the processing branch does not execute.

Sample solution:

```java
if (response instanceof Result(var code, var message) && code == 200) {
    System.out.println(message); // OK
}
```

**References:** [JEP 440 — Record Patterns](https://openjdk.org/jeps/440) and [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html).