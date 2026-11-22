# Destructuring Object Graphs by Record Structure (Nested Record Patterns)

## 1. Mental model: going from outer record to inner record

In applications, data is often organized into multiple nested objects. For example, an order contains a customer, and the customer contains an address:

```text
Order(id, customer)
  └── Customer(name, address)
        └── Address(city, country)
```

Suppose all three types above are Java `record`s. To get the customer's city, the traditional way is to get `Order.customer()`, then `Customer.address()`, and then `Address.city()`; each link in the chain may require a `null` check.

**Nested record patterns** allow you to describe the exact shape you want to extract and name the components across multiple levels in **a single match**:

```java
if (value instanceof Order(
        var orderId,
        Customer(var customerName, Address(var city, var country)))) {
    // Here we have orderId, customerName, city, country.
}
```

Reading from the outside in: `value` must be an `Order`; its second component must match the `Customer(...)` pattern; the second component of `Customer` must match the `Address(...)` pattern. When the entire pattern succeeds, the variables at all levels are bound and can be used inside the `if` branch. This is a check of **declared record types and component structure**, not a property-lookup-by-name mechanism like JavaScript destructuring, nor an arbitrary object graph traversal.

**Version:** Record classes were standardized in Java 16; **record patterns, including nested patterns, are a standard feature since Java 21 (JEP 440)**. The examples below use JDK 21 or later, without needing `--enable-preview`.

## 2. Structure and syntax

Suppose we declare:

```java
record Address(String city, String country) {}
record Customer(String name, Address address) {}
record Order(String id, Customer customer) {}
```

A record pattern has the form `RecordName(component_pattern_1, component_pattern_2, ...)`. The number and **order** of component patterns must correspond to the record declaration. For example:

- `Order(var id, var customer)`: single-level destructuring; `id` is inferred as type `String`, `customer` is inferred as type `Customer`.
- `Order(String id, Customer(var name, var address))`: two-level destructuring; the customer component must match a `Customer` record pattern.
- `Order(String id, Customer(String name, Address(String city, String country)))`: three-level destructuring and directly binds four variables `id`, `name`, `city`, `country`.
- `var` in the component list asks the compiler to infer the type from the record declaration, rather than turning the entire structure into dynamic data.

A pattern can combine *record patterns* (`Address(...)`), *type patterns* (`String city`), and *type-inferred patterns* (`var city`). You do not have to destructure every level: you can stop at `var address` when you only want the `Address` object. However, each record pattern must still list all component positions; you cannot write `Address(var city)` if `Address` declares two components.

## 3. Before and after: manual access vs. nested patterns

For data whose initial type is `Object`, manual access typically looks like this (this snippet assumes the three records are already declared above):

```java
Object value = new Order("DH-01",
        new Customer("Lan", new Address("Đà Nẵng", "VN")));

if (value instanceof Order order) {
    Customer customer = order.customer();
    if (customer != null) {
        Address address = customer.address();
        if (address != null) {
            System.out.println(order.id() + " - " + customer.name()
                    + " - " + address.city());
        }
    }
}
```

With nested record patterns, checking the records along the path and extracting their components are expressed in one place:

```java
if (value instanceof Order(
        var id,
        Customer(var name, Address(var city, var country)))) {
    System.out.println(id + " - " + name + " - " + city);
}
```

Both print `DH-01 - Lan - Đà Nẵng` for this data. The pattern-based version is shorter because it avoids creating intermediate variables and calling each accessor in the body. The pattern clearly shows the reader the required data path. It is best suited when you know the nested record types in advance and only need to extract or check a few values from that structure.

## 4. Complete, runnable example on Java 21+

Save the following code to a file named **`NestedGraphDemo.java`**. The `record` declarations inside the class are for demonstration purposes only and can be replaced with standalone records in a real application.

```java
public class NestedGraphDemo {
    record Address(String city, String country) {}
    record Customer(String name, Address address) {}
    record Order(String id, Customer customer) {}

    // Extract data strictly along the Order -> Customer -> Address chain.
    static String describe(Object value) {
        if (value instanceof Order(
                String orderId,
                Customer(String customerName, Address(String city, String country)))) {
            return orderId + " | " + customerName + " | " + city + ", " + country;
        }
        return "Không khớp cấu trúc";
    }

    // Pattern variables can be used on the right-hand side of && when the pattern succeeds.
    static String describeVn(Object value) {
        if (value instanceof Order(
                var id,
                Customer(var name, Address(var city, var country)))
                && "VN".equals(country)) {
            return name + " ở " + city + " (" + id + ")";
        }
        return "Không có địa chỉ VN";
    }

    // Handle full structure, missing address, and missing customer in order.
    static String classify(Object value) {
        return switch (value) {
            case Order(var id, Customer(var name, Address(var city, var country))) ->
                    id + ": " + name + " @ " + city;
            case Order(var id, Customer(var name, var address)) ->
                    id + ": " + name + " chưa có địa chỉ";
            case Order(var id, var customer) ->
                    id + ": chưa có khách hàng";
            case null -> "Giá trị null";
            default -> "Không phải Order";
        };
    }

    public static void main(String[] args) {
        Object complete = new Order("DH-01",
                new Customer("Lan", new Address("Đà Nẵng", "VN")));
        Object missingAddress = new Order("DH-02",
                new Customer("Minh", null));

        System.out.println(describe(complete));
        System.out.println(describe(missingAddress));
        System.out.println(describe(null));
        System.out.println(describeVn(complete));
        System.out.println(classify(missingAddress));
        System.out.println(classify(null));
    }
}
```

Compile and run in the directory containing the file:

```bash
javac -encoding UTF-8 --release 21 NestedGraphDemo.java
java NestedGraphDemo
```

Output (in a terminal supporting UTF-8):

```text
DH-01 | Lan | Đà Nẵng, VN
Không khớp cấu trúc
Không khớp cấu trúc
Lan ở Đà Nẵng (DH-01)
DH-02: Minh chưa có địa chỉ
Giá trị null
```

In `describe`, the nested pattern succeeds only when all three records `Order`, `Customer`, and `Address` are present according to the declared relationship. For `missingAddress`, `Customer` exists, but its `address` component is `null`, so the `Address(...)` record pattern does not match; the method returns the fallback message. For a `null` input, `instanceof` returns `false`.

## 5. Matching rules and null handling

There are two situations to distinguish:

**A. A child record is `null`.** A `null` value does not match a **record pattern**. For example:

```java
Order order = new Order("DH-02", new Customer("Minh", null));

boolean deepMatch = order instanceof Order(
        var id, Customer(var name, Address(var city, var country)));
// deepMatch == false: no Address to destructure.
```

**B. A reference component is `null`, but the pattern for that component is `var` (or a type pattern that matches unconditionally with the exact declared type).** The pattern can still succeed, and the variable can receive `null`:

```java
Order order = new Order("DH-02", new Customer("Minh", null));

if (order instanceof Order(var id, Customer(var name, var address))) {
    // This branch runs; address == null.
    System.out.println(address == null); // true
}
```

Similarly, `Address(String city, String country)` can bind a `city` equal to `null` if the `city` component is declared as `String`. **Do not confuse a successful record match with all fields being non-null, non-empty, or business-valid.** You can add extra conditions, such as `city != null && !city.isBlank()`, after the pattern matches.

Scenario table for the deep pattern `Order(var id, Customer(var name, Address(var city, var country)))`:

| Input value | Matches deep pattern? | Reason |
| --- | --- | --- |
| `Order` with `Customer` and `Address` | Yes | All three nested records are present |
| `Order` with `Customer`, but `address == null` | No | `null` does not match `Address(...)` |
| `Order` with `customer == null` | No | `null` does not match `Customer(...)` |
| `null` | No | `null` does not match the outermost record pattern |
| Object not of type `Order` | No | Wrong outermost record type |

Records help describe data components clearly, but **do not automatically make the entire graph deeply immutable**. If a component is a `List` or a mutable object, the referenced values can still be modified according to the rules of that type.

## 6. Combining conditions and switch

### 6.1. Guards after `instanceof`

The condition after `&&` is evaluated only when the pattern on the left-hand side matches. Therefore, the `country` variable already has a value before the comparison:

```java
if (value instanceof Order(
        var id, Customer(var name, Address(var city, var country)))
        && "VN".equals(country)) {
    System.out.println(name + " - " + city);
}
```

Using `"VN".equals(country)` also avoids throwing a `NullPointerException` when `country` is `null`. Pattern variables are only in scope where the compiler guarantees the pattern has matched; you cannot use `city` arbitrarily outside the `if` branch.

### 6.2. Multiple structural shapes in `switch`

`switch` pattern matching is a standard feature in Java 21. When handling multiple possibilities of a data graph, order branches **specific first, general last**:

```java
return switch (value) {
    case Order(var id, Customer(var name, Address(var city, var country))) ->
            "Đủ địa chỉ: " + city;
    case Order(var id, Customer(var name, var address)) ->
            "Có khách hàng, chưa có địa chỉ";
    case Order(var id, var customer) ->
            "Không có khách hàng";
    case null -> "Không có đầu vào";
    default -> "Không phải đơn hàng";
};
```

Here, branch 1 handles orders with an `Address`; branch 2 handles `Customer` cases where `address == null`; branch 3 handles orders where `customer == null`. The `case null` branch handles `null` input explicitly. Placing the broad pattern `Order(var id, var customer)` before the more specific patterns will shadow the later branches and can cause a compile-time *dominance* error (an earlier pattern already covers a later pattern). This `switch` snippet is part of a method body, assuming the records and `value` variable are declared as in the complete example in section 4.

## 7. When to use and when not to use

**Use** when the data structure consists of records with a fixed number of levels; when you only need to read a few deeply nested fields; or when multiple business branches correspond to different record shapes. Nested patterns are especially clear in `instanceof`, `switch`, event handling, data models, and hierarchical record types.

**Do not force it** when:
- The graph contains `List`, `Map`, or nodes with a variable count: record patterns do not automatically iterate over collection elements; you need loops, Streams, or a dedicated traversal algorithm.
- Relationships have cycles or an unknown depth: a record pattern only describes a finite nesting chain at compile time, not a dynamic path search in a graph.
- The data is a regular POJO/class rather than a record: you can use a type pattern such as `obj instanceof Customer customer` and call accessors/getters; you cannot write a record pattern `Customer(...)` for a non-record class.
- A single expression nests too many levels, making the structure hard to read: splitting steps across business layers or using intermediate variables will be easier to maintain.

## 8. Common mistakes and self-checks

1. **Confusing field names with component order.** `Address(var city, var country)` corresponds strictly to `record Address(String city, String country)`. If you swap the variable order, the code may still compile (because both have type `String`), but the meaning of the data is swapped.
2. **Missing components in a pattern.** Since `Address` has two components, `Address(var city)` is invalid. Declare all positions; for unused positions, standard Java 21 allows naming them `var ignoredCountry`. Unnamed pattern syntax `_` is still a preview feature in Java 21, so do not treat it as stable Java 21 syntax.
3. **Assuming deep patterns automatically skip null.** `Address(...)` will not match when `address` is `null`. If you want to distinguish missing data, add a broader pattern in `switch` or bind `var address` and check it yourself.
4. **Assuming the data itself is validated.** A pattern matches types and component positions; it does not prove that `country` is a valid country code or that `city` has content.
5. **Placing a broad pattern before a narrow pattern in switch.** The broad pattern can capture all cases that the narrow pattern is meant to handle, leading to a dominance error; prioritize checking specific shapes first.
6. **Using the wrong JDK version.** On `javac` older than 21, record patterns may not be officially supported. Use `java -version` and `javac -version` to confirm the environment.

**Short exercises:**

- Create `new Order("DH-03", null)`. Predict `describe` and `classify` from the full example. The results are `Không khớp cấu trúc` and `DH-03: chưa có khách hàng`, respectively.
- Create an order with address `new Address(null, "VN")`. Does the deep pattern match? **Yes**: the `city` component can be bound to `null`. To reject this address, add the condition `city != null && !city.isBlank()` after the pattern.
- Change `Address` from two components to `record Address(String street, String city, String country)`. Update all `Address(...)` patterns to three positions in the right order and update the constructor calls accordingly.

**Remember:** Nested record patterns help **check record shapes and destructure data levels in a single expression**. Code readability comes from matching the right structure, controlling `null` at each record node, keeping branches ordered from specific to general, and using deep patterns only as far as truly needed.

**References:** [Oracle — Record Patterns (Java 21)](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html), [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
