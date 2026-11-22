# Deconstructing Nested Records with Record Patterns in Java 21

## 1. What is nested record deconstruction?

**Deconstruction** is the operation of breaking down a record object into its component values during **pattern matching**. With a **nested record pattern**, we continue deconstructing a component that is itself another record, across multiple levels, without having to manually write chains of accessor calls at each level.

For example, consider structured data:

```text
Order(id, customer)
           |
           +-- Customer(name, address)
                               |
                               +-- Address(city, point)
                                                   |
                                                   +-- Point(x, y)
```

With Java 21, we can check and extract all components in a single expression:

```java
if (value instanceof Order(
        String id,
        Customer(String name,
                Address(String city, Point(int x, int y))))) {
    System.out.println(id + ": " + name + " - " + city
            + " (" + x + ", " + y + ")");
}
```

This is an **illustrative snippet** using the `Order`, `Customer`, `Address`, and `Point` records, which are fully defined in the runnable example section below.

The key point: Java only enters the `if` body when **the entire pattern matches**. The variables `id`, `name`, `city`, `x`, and `y` are bound to their corresponding component values. We do not need to manually cast at each level.

**Version milestone:** Record Patterns belong to **JEP 440**, finalized in **Java 21**. When using record patterns in `switch`, the corresponding feature is Pattern Matching for switch (**JEP 441**), also finalized as of Java 21. `--enable-preview` is not required.

## 2. Record structure and component order

Suppose we declare:

```java
record Point(int x, int y) {}

record Address(String city, Point point) {}

record Customer(String name, Address address) {}

record Order(String id, Customer customer) {}
```

The lines above are **illustrative declarations**, not four standalone Java programs. When a record pattern appears, the **order and count** of sub-patterns must match the record's components.

| Record | Components in order | Corresponding pattern |
|---|---|---|
| `Point` | `int x`, `int y` | `Point(int x, int y)` |
| `Address` | `String city`, `Point point` | `Address(String city, Point(int x, int y))` |
| `Customer` | `String name`, `Address address` | `Customer(String name, Address(String city, Point(int x, int y)))` |
| `Order` | `String id`, `Customer customer` | `Order(String id, Customer(String name, Address(String city, Point(int x, int y))))` |

Inside each pair of parentheses of a record pattern, we write **one pattern per component**, in the exact declaration order. You can use:

- **Type pattern:** `String name`, `int x`.
- **`var` pattern:** `var name`, `var x`, to let the compiler infer the component's type.
- **Nested record pattern:** `Address(String city, Point(int x, int y))`.

For example, `Order(String id, Customer(...))` requires two components because `Order` has two components; you cannot omit `id` by writing `Order(Customer(...))`. If `id` is not used, you can still declare a named variable such as `var ignoredId`. In Java 21, the unnamed pattern syntax `_` is still a preview feature, so this article does not use it.

There is no deconstruction assignment syntax such as `var (id, customer) = order;` in Java 21. We deconstruct through **pattern matching**, primarily with `instanceof` and `switch`.

## 3. How does Java match nested record patterns?

Given:

```java
Order(String id,
      Customer(String name,
               Address(String city, Point(int x, int y))))
```

Conceptually, matching is understood in this order:

1. The input value must be a **non-`null`** `Order` object.
2. The `id` component is matched against `String id`; the `customer` component is matched against `Customer(...)`.
3. `Customer(...)` requires `customer` to be a **non-`null`** `Customer`; it continues deconstructing `name` and `address`.
4. `Address(...)` requires `address` to be non-`null`; it continues deconstructing `city` and `point`.
5. `Point(int x, int y)` requires `point` to be a non-`null` `Point`, then binds the two integer coordinates.
6. If every sub-pattern matches, the entire pattern matches, and the variables can be used where the compiler determines the match succeeded.

Conceptually, record patterns use the **component accessors** provided by the record (for example `customer()`, `address()`, `point()`). They do not mutate the record, do not create automatic copies, and do not require a user-written `deconstruct()` method.

Because matching happens recursively, **a single `null` nested record component is enough for the entire nested pattern to fail to match**. However, that does not mean every leaf component must be non-`null`.

## 4. Distinguishing null nested records from null leaf components

Let's compare four cases:

| Input | Pattern `Order(..., Customer(..., Address(..., Point(...))))` | Reason |
|---|---|---|
| `null` | Does not match | Root record is `null` |
| `new Order("O1", null)` | Does not match | Nested `Customer(...)` encounters `null` |
| `new Order("O2", new Customer("An", new Address("Hue", null)))` | Does not match | Nested `Point(...)` encounters `null` |
| `new Order("O3", new Customer(null, new Address(null, new Point(0, 0))))` | **Matches** | Every record object exists; only the `String` components are `null` |

**Why does the last row still match?** In Java 21 record patterns, a direct type pattern can match `null` when it is **unconditional for the declared type of the component**. `String name` is unconditional for the component declared as `String name`; the same applies to `String city`. Therefore, both variables can be bound to `null`.

Conversely, **the record pattern `Point(int x, int y)` does not match `null`**, even when the `point` component is declared as `Point`.

If we replace `Point(int x, int y)` with `var point` or `Point point` directly in `Address`'s component list, we can bind `point == null` instead of failing at that level:

```java
if (value instanceof Order(
        var id,
        Customer(var name, Address(var city, var point)))) {
    // customer and address are guaranteed to be non-null records;
    // id, name, city, and point can still be null.
    System.out.println(point == null ? "Chưa có point" : point);
}
```

The snippet above uses the records declared in section 2. Note: `instanceof Point p` at the outer level does **not** match `null`; the null-matching rule of a direct type pattern in a **record pattern component** must be distinguished from a regular type pattern on the selector.

## 5. Complete Java 21 example: multi-level deconstruction

Create a file named **`NestedRecordDeconstructionDemo.java`** with the following code. The program demonstrates three ways to use nested deconstruction:

- `inspect`: `instanceof` with a four-level structure, returning details only when the full pattern matches.
- `route`: `switch` using nested patterns and `when` to classify; includes fallback branches for incomplete data.
- `loose`: deconstructs down to `Address` but uses `var point` to **accept a null point**.

```java
public class NestedRecordDeconstructionDemo {
    record Point(int x, int y) {}
    record Address(String city, Point point) {}
    record Customer(String name, Address address) {}
    record Order(String id, Customer customer) {}

    static String inspect(Object value) {
        if (value instanceof Order(
                String id,
                Customer(String name,
                        Address(String city, Point(int x, int y))))) {
            return "DETAIL=" + id + "/" + name + "/" + city + "/" + x + "," + y;
        }
        return "NO_FULL_MATCH";
    }

    static String route(Object value) {
        return switch (value) {
            case null -> "NULL_ROOT";
            case Order(var id,
                       Customer(var name, Address(var city, Point(int x, int y))))
                    when city != null && !city.isBlank() && x >= 0 && y >= 0
                    -> "VALID_POINT";
            case Order(var id,
                       Customer(var name, Address(var city, Point(int x, int y))))
                    -> "HAS_POINT";
            case Order(var id, var customer) -> "INCOMPLETE";
            default -> "OTHER_TYPE";
        };
    }

    static String loose(Object value) {
        if (value instanceof Order(
                var id, Customer(var name, Address(var city, var point)))) {
            return "CITY=" + (city == null ? "<unknown>" : city)
                    + "; POINT_NULL=" + (point == null);
        }
        return "NO_ADDRESS";
    }

    static void show(String label, Object value) {
        System.out.println(label + " | " + inspect(value)
                + " | " + route(value) + " | " + loose(value));
    }

    public static void main(String[] args) {
        show("full", new Order("O1",
                new Customer("Lan", new Address("Hue", new Point(1, 2)))));
        show("leaf-null", new Order("O2",
                new Customer(null, new Address(null, new Point(0, 0)))));
        show("blank-city", new Order("O3",
                new Customer("An", new Address(" ", new Point(3, 4)))));
        show("point-null", new Order("O4",
                new Customer("Chi", new Address("Ha Noi", null))));
        show("address-null", new Order("O5", new Customer("Duc", null)));
        show("customer-null", new Order("O6", null));
        show("root-null", null);
        show("other-type", "text");
    }
}
```

Compile and run on **JDK 21 or later**:

```bash
javac --release 21 NestedRecordDeconstructionDemo.java
java NestedRecordDeconstructionDemo
```

**Exact stdout:**

```text
full | DETAIL=O1/Lan/Hue/1,2 | VALID_POINT | CITY=Hue; POINT_NULL=false
leaf-null | DETAIL=O2/null/null/0,0 | HAS_POINT | CITY=<unknown>; POINT_NULL=false
blank-city | DETAIL=O3/An/ /3,4 | HAS_POINT | CITY= ; POINT_NULL=false
point-null | NO_FULL_MATCH | INCOMPLETE | CITY=Ha Noi; POINT_NULL=true
address-null | NO_FULL_MATCH | INCOMPLETE | NO_ADDRESS
customer-null | NO_FULL_MATCH | INCOMPLETE | NO_ADDRESS
root-null | NO_FULL_MATCH | NULL_ROOT | NO_ADDRESS
other-type | NO_FULL_MATCH | OTHER_TYPE | NO_ADDRESS
```

How to read the output:

- **`full`:** the entire nested pattern matches. The `when` condition is true, so `route` returns `VALID_POINT`.
- **`leaf-null`:** both `name` and `city` are `null`, but the `Order`, `Customer`, `Address`, and `Point` records all exist. `inspect` still deconstructs successfully; `route` returns `HAS_POINT` because `city != null` is false.
- **`blank-city`:** deconstruction succeeds because a single-space string is still a `String` value. The `!city.isBlank()` guard is false, so it is classified as `HAS_POINT`.
- **`point-null`:** the pattern requiring `Point(...)` fails; the pattern using `var point` in `loose` still matches and receives `point == null`.
- **`address-null` and `customer-null`:** the nested record pattern fails at the missing level, but `Order` still exists, so `route` selects `INCOMPLETE`.
- **`root-null`:** `instanceof` evaluates to `false`; `switch` selects `case null`.
- **`other-type`:** `String` is not an `Order`; `default` handles it.

This is demo data meant to clarify the pattern matching mechanism, not real-world address or coordinate validation logic.

## 6. Nested deconstruction in switch and guards

`switch` helps handle multiple levels of matching using ordered branches. From the program:

```java
return switch (value) {
    case null -> "NULL_ROOT";

    // Matches all nested records and satisfies the additional condition.
    case Order(var id,
               Customer(var name, Address(var city, Point(int x, int y))))
            when city != null && !city.isBlank() && x >= 0 && y >= 0
            -> "VALID_POINT";

    // Still has a Point, but does not satisfy the guard.
    case Order(var id,
               Customer(var name, Address(var city, Point(int x, int y))))
            -> "HAS_POINT";

    // Order exists, but any nested record may be missing.
    case Order(var id, var customer) -> "INCOMPLETE";

    default -> "OTHER_TYPE";
};
```

**The snippet above is only an illustrative `switch` expression body.** The complete, compilable version is inside the class in section 5.

Keep in mind:

1. **The `when` guard is evaluated after the pattern matches.** Therefore, we only check `city.isBlank()` once the `city` variable is bound, while using `city != null` and `&&` to avoid an error when `city` is null.
2. **The guarded branch comes before the unguarded branch with the same pattern.** If the order is reversed, the more specific branch is dominated (*dominance*) by the broader branch, causing a compile error.
3. **Specific nested branches come before `Order(var id, var customer)`.** The broad `Order(...)` branch matches even when `customer` or deeper components are null; placing it first can shadow the specific branches.
4. **`case null` only catches a null selector**, not automatically every null nested component. `default` in this kind of `switch` also does not replace explicit handling of a null selector.

If you only need to know whether the data has all four levels, a single `instanceof` branch is usually easier to read. If you need to make decisions across multiple levels of completeness, `switch` can provide a clearer flow.

## 7. When to choose var vs. a nested record pattern?

The following two statements behave differently when `Address.point() == null`:

```java
value instanceof Order(
    var id, Customer(var name, Address(var city, Point(int x, int y))))

value instanceof Order(
    var id, Customer(var name, Address(var city, var point)))
```

- In the first statement, `Point(int x, int y)` requires `point` to be a non-null record object; when it matches, you immediately get `x` and `y` as `int`.
- In the second statement, `var point` binds `null` directly as well; the code author must check it manually before calling `point.x()` or `point.y()`.

Choose a **nested pattern** when the logic needs the data inside the record and requires it to exist. Choose a **direct type/`var` pattern** when you want to keep a potentially null reference, or when you do not need to unpack the structure any deeper.

You can also stop at the `Customer` level:

```java
if (value instanceof Order(var id, Customer(var name, var address))) {
    // customer is non-null; address may be null.
    if (address != null) {
        System.out.println(address.city());
    }
}
```

This snippet illustrates an addition to the `NestedRecordDeconstructionDemo` class in section 5. The pattern only deconstructs to the depth the logic actually needs. Deconstructing as deeply as possible is not always the best choice for readability.

## 8. Scope, data types, and common compile errors

**Scope of pattern variables.** Variables such as `x` and `y` can only be used where the compiler determines the pattern has matched, such as the `if` body, the `when` guard expression, and the corresponding `switch` branch. They cannot be used arbitrarily after an `if` if the condition could be false.

**Types are checked at compile time.** If you change the component order or use a pattern incompatible with the component type, the compiler reports an error. Java relies on the order and types of record components, not on the variable names you choose in the pattern.

**No literal patterns for components in Java 21.** Do not write:

```java
// Not valid record component pattern syntax in Java 21:
Order("O1", Customer("Lan", Address("Hue", Point(1, 2))))
```

The strings and numbers above are *literals*, not component patterns. If you want to check specific values, bind the variables first and then use a guard:

```java
case Order(var id, Customer(var name,
        Address(var city, Point(int x, int y))))
        when "O1".equals(id) && "Hue".equals(city) && x == 1 && y == 2
        -> "EXACT_MATCH";
```

These two snippets are for syntax illustration only; to run `case`, it must be placed inside a `switch` with appropriate remaining branches.

**Do not confuse with accessor chaining.** The expression:

```java
order.customer().address().point().x()
```

can throw a `NullPointerException` if an intermediate reference is null. A nested record pattern is equivalent in intent for **reading the structure when sufficient data is present**, except that a non-matching branch due to a null nested record simply causes the pattern to fail. If the domain needs to return a specific error when a level is missing, handle the missing branch separately; do not treat patterns as a mechanism for validating every record invariant.

**Another pitfall is dereferencing a null leaf.** `String city` in a record pattern can still bind `null` when the component is declared as `String`. Always check before calling `city.length()`, `city.isBlank()`, or similar methods.

## 9. Applying in real-world code

Nested deconstruction is useful when:

- You need to select a processing branch based on a nested data structure, for example event -> payload record -> metadata record.
- You want to read part of the information from immutable records without writing repetitive cast and accessor chains.
- You need to distinguish an object with a complete structure from an object missing some inner records.

However, when a nested pattern becomes too long or is repeated in many places, consider a **domain method** to encapsulate the business question. For example, instead of having many callers understand `Order -> Customer -> Address -> Point` to compute "eligibility", move that rule to the object or policy that owns it. Nested patterns remain well suited at **data-classification boundaries**, while business decisions can live in a clearly named domain method.

You do not need to force every record into a multi-level pattern: if you only need `id`, `case Order(var id, var customer)` is usually clearer.

## 10. Self-check exercises

Suppose we use the records from section 5:

```java
Object input = new Order("T1", new Customer(null,
        new Address("Da Nang", null)));
```

1. What does `input instanceof Order(var id, Customer(var name, Address(var city, Point(int x, int y))))` return? **`false`**, because `point` is `null` and `Point(...)` does not match.
2. What if we replace `Point(int x, int y)` with `var point`? **`true`**, with `name == null` and `point == null`. The `Order`, `Customer`, and `Address` records all exist.
3. Does `String name` require `name` to be non-null? **No.** This direct type pattern is unconditional for a component of type `String`.
4. How do you accept only a non-blank `city` and an existing `point`? **Use a nested `Point(...)`** and add `when city != null && !city.isBlank()` or an `&&` condition after `instanceof`.
5. If `Order.customer() == null`, can you extract `name` with the pattern `Customer(var name, ...)`? **No**, because the nested record pattern `Customer(...)` does not match null. You need a fallback branch or to bind `var customer` and handle null manually.

## Summary

**Deconstructing nested records** lets Java 21 check and break down multiple levels of records in a single pattern: the outer record must match, each nested record must also match, and only then are deeper components bound. A record pattern does not accept null at the position it is deconstructing, whereas a direct type/`var` pattern for a component can still bind null depending on the declared type.

Use `instanceof` for a single structural check, `switch` for multiple ordered branches, and `when` to add conditions on bound values. Only deconstruct to the depth you actually need, handle null explicitly, and keep syntax within stable Java 21 features.

## References

- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Java Language Specification, Java SE 21 — §14.30 Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
