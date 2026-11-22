# Selecting Components to Extract When Deconstructing Records in Java

## 1. Goal and Scope

When working with a `record`, an object can contain multiple components (data members), yet we often only care about a few of them. For example, `Point(int x, int y)` has two coordinates, but the current operation only needs `x`; `Order(long id, Customer customer, int quantity)` holds multiple pieces of information, but the shipping flow only needs the city name inside `customer.address`.

**Selecting components to extract** means choosing which values to *bind to variables and use* when deconstructing a record. We need to distinguish between two things:

1. **A record pattern must specify all component positions** in the exact declaration order of the record; Java 21 does not allow omitting positions inside the parentheses.
2. **You are not required to use every matched component**. You can name a temporary variable to ignore an unused value (Java 21), or use the **unnamed pattern `_`** (Java 22 and later).

Since **Java 21**, record patterns have been a standard feature (JEP 440). The `_` syntax as an unnamed pattern was standardized in **Java 22** (JEP 456), so the main examples run on **Java 21+** and the `_` section is noted separately for **Java 22+**.

This lesson focuses on selecting components via `instanceof`, multi-level record deconstruction, combining `switch` and `when`, nullable cases, ways to keep code concise, and common mistakes.

## 2. A Record Pattern Always Matches the Exact Record Structure

Given the record:

```java
record Point(int x, int y) {}
```

To extract only `x` from a variable of type `Object`, write in Java 21:

```java
if (value instanceof Point(var x, var ignoredY)) {
    System.out.println("x=" + x);
}
```

- `Point(...)` requires `value` to be a non-`null` `Point`.
- The first position corresponds to component `x`, and the pattern variable `x` is used.
- The second position corresponds to component `y`. `ignoredY` is still a valid variable; we simply do not use it in the `if` body. Java does not automatically skip the second position just because the code does not need `y`.
- `var` lets the compiler infer the types from the record definition: both `x` and `ignoredY` have type `int`.

**Invalid in Java 21:**

```java
// Does not compile: Point declares 2 components, pattern only has 1.
if (value instanceof Point(var x)) {
    System.out.println(x);
}
```

There is also no named-selection syntax such as `Point(x = var x)`, and no deconstruction assignment operator `var (x, y) = point` in Java 21. The **position and order** of components are determined by the `record` declaration.

Names like `ignoredY` are only a convention for readers—not a Java keyword—and do not cause the JVM to automatically skip evaluating the component. Use consistent naming, such as `unusedY` or `ignoredQuantity`, when a project is still running on Java 21.

## 3. Choosing the Deconstruction Depth: Only Unpack the Layers You Actually Need

Consider this structure:

```java
record Address(String city, String street, String postalCode) {}
record Customer(String id, Address address) {}
record Order(long id, Customer customer, int quantity) {}
```

If you only need the **order ID**, there is no need to deconstruct `Customer` or `Address`:

```java
if (obj instanceof Order(var id, var ignoredCustomer, var ignoredQuantity)) {
    System.out.println("Order #" + id);
}
```

We use a record pattern at the `Order` level with all three positions; the `customer` component is kept as a single variable without deconstructing it further. This makes it clear to readers that `id` is the only data the code needs.

If you only need the **shipping city**, unpack down to `Address`:

```java
if (obj instanceof Order(
        var ignoredOrderId,
        Customer(
            var ignoredCustomerId,
            Address(var city, var ignoredStreet, var ignoredZip)),
        var ignoredQuantity)) {
    System.out.println(city);
}
```

Reading from outside in:

1. `Order(...)` matches an order with three components; the ID and quantity are not used.
2. `Customer(...)` matches the customer record in the second component of `Order`; the customer ID is not used.
3. `Address(...)` matches the address record in the second component of `Customer`.
4. Only `city` is used. `street` and `postalCode` still have pattern positions, but their corresponding variables are unused.

This is **component selection along the path `Order → Customer → Address → city`**. There is no need to create a separate variable for the entire `Order`, no repeated casts, and no chained accessor calls after the whole pattern matches.

**Note on `null`:** If `customer == null` or `address == null`, the nested record pattern `Customer(...)` or `Address(...)` does not match; execution takes the `else`/non-matching path. However, if the `Address` record exists and only `city == null`, `var city` can still receive `null`. Selecting a component does not imply checking that every inner value is non-`null`.

## 4. Complete, Runnable Java 21 Example

Create the file **`SelectComponentDemo.java`**:

```java
public class SelectComponentDemo {
    record Point(int x, int y) {}
    record Address(String city, String street, String postalCode) {}
    record Customer(String id, Address address) {}
    record Order(long id, Customer customer, int quantity) {}

    static String cityOf(Object obj) {
        if (obj instanceof Order(var ignoredOrderId,
                Customer(var ignoredCustomerId,
                         Address(var city, var ignoredStreet, var ignoredZip)),
                var ignoredQuantity)) {
            return city == null ? "City missing" : city;
        }
        return "No address";
    }

    static String orderId(Object obj) {
        if (obj instanceof Order(var id, var ignoredCustomer, var ignoredQuantity)) {
            return "Order #" + id;
        }
        return "Not an order";
    }

    static String label(Object obj) {
        return switch (obj) {
            case null -> "No input";
            case Order(var ignoredId,
                    Customer(var ignoredCustomerId,
                            Address(var city, var ignoredStreet, var ignoredZip)),
                    var ignoredQuantity)
                    when city != null && !city.isBlank() -> "Ship to " + city;
            case Order(var ignoredId, var ignoredCustomer, var ignoredQuantity)
                    -> "Order without city";
            default -> "Not an order";
        };
    }

    static String pointX(Object obj) {
        if (obj instanceof Point(var x, var ignoredY)) {
            return "x=" + x;
        }
        return "Not a point";
    }

    public static void main(String[] args) {
        Object full = new Order(42L,
                new Customer("C01", new Address("Da Nang", "Tran Phu", "550000")), 3);
        Object noAddress = new Order(43L, new Customer("C02", null), 2);
        Object nullCity = new Order(44L,
                new Customer("C03", new Address(null, "Ngo Quyen", "100000")), 1);

        System.out.println(cityOf(full));
        System.out.println(cityOf(noAddress));
        System.out.println(cityOf(nullCity));
        System.out.println(orderId(noAddress));
        System.out.println(label(full));
        System.out.println(label(noAddress));
        System.out.println(label(nullCity));
        System.out.println(label(null));
        System.out.println(pointX(new Point(7, 9)));
    }
}
```

Run with JDK 21 or newer:

```bash
javac --release 21 SelectComponentDemo.java
java SelectComponentDemo
```

**Exact output:**

```text
Da Nang
No address
City missing
Order #43
Ship to Da Nang
Order without city
Order without city
No input
x=7
```

Analysis:

- `cityOf(full)` returns only the `city` component of the `Address` record nested inside `Customer` and `Order`; all required nested patterns match.
- `cityOf(noAddress)` returns `No address` because the `Customer.address` component is `null`, so it cannot match `Address(...)`.
- `cityOf(nullCity)` returns `City missing`: `Address` itself exists, so the pattern matches, but the `city` component is `null`.
- `orderId(noAddress)` extracts ID `43` **without requiring** a valid address record, avoiding deconstructing deeper than needed.
- `label(full)` uses `switch`, selects the city, and additionally checks `when city != null && !city.isBlank()`.
- `label(noAddress)` and `label(nullCity)` both return `Order without city`, but for different reasons: the first fails to match the nested `Address(...)`, while the second matches the pattern but fails the `when` guard.
- `label(null)` has a dedicated `case null` branch; this handles a `null` `switch` selector value, which is different from a `null` component inside a record.
- `pointX` uses only `x` and does not need `y`, yet the pattern still declares both positions.

This example intentionally uses `ignored...` names for Java 21 compatibility. In production code, you can use shorter variable names or Java 22's unnamed patterns if the project has already upgraded its JDK.

## 5. Using `switch`/`when` When Conditions Depend on the Selected Component

In a `switch`, you can extract a component and write a `when` guard that uses only that variable:

```java
// Illustrative snippet inside a method taking Object obj;
// assumes the Order/Customer/Address records are already declared.
return switch (obj) {
    case Order(var id, Customer(var customerId,
            Address(var city, var street, var zip)), var quantity)
            when city != null && city.startsWith("Da") -> "Central";
    case Order(var id, var customer, var quantity) -> "Other order";
    default -> "Not an order";
};
```

The `when` guard runs only after **the entire nested pattern matches**. The `city` variable is declared by the pattern and is in scope in both the guard and that branch's body. If a nested record fails to match, execution moves to the next branch; there is no automatic insertion of `null` checks for statements inside a matched branch.

Place the specific branch with `when` **before** the broader `Order(...)` branch. If the broader branch comes first, the subsequent branch may be shadowed and the compiler will report a dominated case label error.

For a `switch` expression over a value of type `Object`, an exhaustive branch such as `default` is needed for non-`Order` values. If the selector can be `null`, handle it explicitly with `case null` or per the input contract, because `default` does not match `null`.

## 6. Java 22+: The Unnamed Pattern `_` to Truly Ignore Components

Starting in **Java 22**, JEP 456 allows using the **unnamed pattern `_`** when a component's position still needs to be matched in the structure, but its value does not need to be bound to a variable.

Example extracting only `x`:

```java
// Java 22 or later
if (obj instanceof Point(var x, _)) {
    System.out.println(x);
}
```

This has the same data-selection goal as the Java 21 `Point(var x, var ignoredY)` approach, except `_` **does not declare a named variable**, so it cannot be referenced later.

With nested records, the `_` symbol makes the path to the selected component much clearer:

```java
// Java 22 or later; Order, Customer, and Address as defined above.
if (obj instanceof Order(_, Customer(_, Address(var city, _, _)), _)) {
    System.out.println(city);
}
```

The pattern still has **all three components of `Order`**, **two components of `Customer`**, and **three components of `Address`**. `_` only stands in for a single component pattern at that position; it **does not remove positions** and does not make the specified nested records optional.

This is a very important version distinction:

| Requirement | Java 21 | Java 22 and later |
| --- | --- | --- |
| Extract one component, keep all positions | `Point(var x, var ignoredY)` | `Point(var x, _)` |
| Select a component across multiple levels | `Order(var skipId, Customer(var skipId2, Address(var city, var skipStreet, var skipZip)), var skipQuantity)` | `Order(_, Customer(_, Address(var city, _, _)), _)` |
| Ignore a position without creating a variable name | No standard `_` yet | Use unnamed pattern `_` |
| Use `_` as a variable to print the value | Invalid | Invalid; `_` has no accessible name |

**Do not paste Java 22 snippets using `_` into a file compiled with `javac --release 21`.** If you have not upgraded Java yet, use `var ignored...`.

Even when using an unnamed pattern, do not treat it as an optimization directive guaranteeing that the JVM will not read or invoke the corresponding accessor. The primary purpose of `_` is to express **no interest in the value** and avoid declaring unused variables.

## 7. When Should You Choose Accessors Instead of a Record Pattern?

If an object already has a known record type and you only need one component at the same level, a direct accessor is usually simplest:

```java
Point point = new Point(7, 9);
int x = point.x();
```

There is no need to write `if (point instanceof Point(var x, var y))` just to read `x` when `point` is already a `Point`. Deconstruction is more useful when you need to **both check structure/type and extract values**, or choose among different branches in a `switch`.

With multiple levels and potentially `null` values, you can write explicit accessor conditions (snippet inside a method taking `Order order`):

```java
if (order != null && order.customer() != null
        && order.customer().address() != null) {
    String city = order.customer().address().city();
    System.out.println(city == null ? "City missing" : city);
}
```

This approach is useful when you need to handle `null` errors level by level, need more detail about the data state, or when the rest of the code already works with `Order`. Nested record patterns are a better fit when you only care whether the full structure matches and want to reduce repetitive accessor chains.

Rule of thumb: **deconstruct only down to the component you actually need; do not unpack deeper if an intermediate record value is sufficient for the next step**. If a pattern spans many lines and contains too many `ignored...` variables, consider a helper method, direct accessors, or `_` on Java 22+.

## 8. Common Mistakes and How to Fix Them

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| `Point(var x)` | Wrong number of components: `Point` has two components `x, y`. | Use `Point(var x, var ignoredY)` (Java 21) or `Point(var x, _)` (Java 22+). |
| `Order(Customer(Address(var city)))` | Omits `id` and `quantity` positions, as well as other components of `Customer` and `Address`. | Provide a pattern for **every position**, using `var ignored...` or `_` according to your Java version. |
| Placing `Address(...)` in the ID position of `Customer` | Record patterns rely on **declaration order**, not component name matching. | Check the record definition and place `Address(...)` in the second position. |
| Using `_` when the project is still on Java 21 | Unnamed patterns were standardized in Java 22. | Use `ignored...` variables or upgrade the JDK/source level to 22+. |
| Using `ignoredY` in code while expecting it to be ignored | In Java 21, that name is still a valid variable; "unused" is only a convention. | Name variables to clearly reflect intent. On Java 22+, use `_` when no reference is needed. |
| Assuming `_` lets you skip an entire nested record | `_` skips a **component position**, whereas `Address(...)` requires the nested record to match. | Use `var address` or `_` at the nested record's position if you **do not need** to check or deconstruct it. |
| Assuming `city` is always non-`null` because `Address(...)` matched | A non-`null` `Address` record does not guarantee its `city` component is non-`null`. | Check `city != null` or apply the appropriate business condition. |
| Referencing a pattern variable outside its scope | The variable is only in scope where the compiler knows the pattern matched. | Use the variable inside the `if` branch, `when` guard, or matching `case` branch. |
| Using a record pattern on a regular class | Record deconstruction works with `record` types, not arbitrary classes. | Use accessors/type patterns or design an appropriate `record`. |

A note on performance: writing shorter nested patterns does not necessarily mean fewer runtime operations than every accessor-based alternative. Prioritize **correctness, clear matching conditions, and readability**; optimize only after measuring if actually needed.

## 9. Practice Exercise: Select the Right Component Without Over-Extracting

Given:

```java
record Dimensions(int width, int height) {}
record Product(String sku, String name, Dimensions dimensions, double price) {}
record CartItem(Product product, int quantity) {}
```

**Requirement A:** From `Object input`, extract only `sku` if `input` is a `CartItem` with a `Product`; do not require `dimensions` to be non-`null`.

Java 21 solution (inside a method with `input`):

```java
if (input instanceof CartItem(
        Product(var sku, var ignoredName, var ignoredDimensions, var ignoredPrice),
        var ignoredQuantity)) {
    System.out.println(sku);
}
```

Here `dimensions` is bound to a variable but **is not deconstructed into `Dimensions(...)`**. Therefore, if `Product.dimensions == null`, the `Product(...)` pattern can still match; only `CartItem.product` must be a non-`null` `Product` record.

**Requirement B:** Extract `width` only when the full `CartItem → Product → Dimensions` structure is valid.

Java 21 solution:

```java
if (input instanceof CartItem(
        Product(var ignoredSku, var ignoredName,
                Dimensions(var width, var ignoredHeight),
                var ignoredPrice),
        var ignoredQuantity)) {
    System.out.println(width);
}
```

When `Dimensions == null`, the pattern in Requirement B **does not match**, unlike Requirement A. The difference is not whether a variable is used, but the decision of **whether to apply a record pattern down to the `Dimensions` level**.

A more concise solution for Requirement B on Java 22+:

```java
if (input instanceof CartItem(
        Product(_, _, Dimensions(var width, _), _), _)) {
    System.out.println(width);
}
```

These solution snippets are illustrative fragments using the three `record` types declared above; the complete standalone runnable program is in Section 4.

## 10. Takeaways

- **Selecting components to extract** means choosing which variables are bound and how deep deconstruction goes; the record pattern must still list **all components in order**.
- **Java 21:** use `var wanted` for needed data and `var ignored...` for unused components. You can stop at a nested record with `var child` instead of unpacking further.
- **Java 22+:** use the **unnamed pattern `_`** to express "I do not care about this component" without naming a variable. The `_` pattern still occupies one exact position.
- **Null:** a nested record that needs to be deconstructed being `null` causes the nested record pattern not to match; a component bound with `var` can still be `null`. Do not skip necessary checks.
- **Code design:** when you already have a typed record and only need one value, an accessor can be clearer; when you need to check structure and extract data at the same time, a record pattern expresses the intent directly.

**References:** [JEP 440 — Record Patterns (Java 21)](https://openjdk.org/jeps/440), [JEP 456 — Unnamed Variables & Patterns (Java 22)](https://openjdk.org/jeps/456), [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html).
