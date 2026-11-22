# Choosing `record` for Immutable Data in Domain Model Design (Java 21+)

## 1. The Design Problem: Does an Object Represent a *Value* or an *Entity*?

In Java, a `record` is a way to declare a **data-carrying class whose state is defined by its components**. When designing a domain model, the important question is not “how many fields does it have?”, but rather: **is this object identified by its value, or by its own identity and lifecycle?**

For example: coordinates `Point(2, 3)`, time intervals, customer IDs, order line items, and order state snapshots are typically treated as **value objects**. Two values with the same components and the same business invariants can be considered equivalent. For this kind of concept, a record usually expresses intent very well.

Conversely, `Customer` or `Order` in a transactional system may be an **entity**: it holds a stable identity (ID), has a state transition history, concurrency version, ORM relationships, and a business lifecycle. Two entities with the same current name and address are not necessarily the same entity. Using a record directly as an entity can obscure the meaning of identity and hinder certain persistence mechanisms.

**Lesson objectives:** know when to choose a record, understand the immutability limits of records, design constructors with invariants, guard against mutable components, reason about equality, and choose a model that fits pattern matching.

Version note: `record` has been a standard feature since **Java 16** (JEP 395); for example, Java 17 supports records and compact constructors. The examples of **record patterns in `switch`** in this lesson use standard **Java 21+** syntax (JEP 440 and 441), without requiring `--enable-preview`.

## 2. What Does a Record Actually Provide?

Concise declaration:

```java
record Point(int x, int y) {}
```

The compiler provides a structure semantically equivalent to a class carrying two `int` components, including:

- Two state fields corresponding to the components, of type `private final`.
- A canonical constructor accepting `x` and `y`.
- Accessors `x()` and `y()`, rather than JavaBean getters `getX()`/`getY()`.
- `equals(Object)` and `hashCode()` based on the components, along with `toString()` representing the state.
- The record class is `final`; it cannot extend any application class (a record extends `java.lang.Record`), but **it can implement interfaces**.

Usage:

```java
Point first = new Point(2, 3);
Point second = new Point(2, 3);

System.out.println(first.x());          // 2
System.out.println(first.equals(second)); // true
System.out.println(first == second);      // false (two distinct objects)
```

**Meaning:** records are convenient for **value semantics**: comparing content rather than reference identity. However, Java does not automatically infer domain relationships from every field. The default `equals` only compares components using Java's equality mechanism and does not know business rules such as “two customer IDs differing only in letter case are still the same.”

### A Record Is Not Synonymous with Every Kind of Immutability

`record` is a reference class, not a primitive or a *deep freeze* mechanism. Component references are stored in final fields, but **the objects they point to can still be mutated**. A record's constructor also does not automatically reject `null`, negative numbers, blank strings, or invalid business data. The domain model author must still define the invariants and how to enforce them.

## 3. Decision Table: `record` or `class`?

| Data Kind | Usually Prefer | Reason |
| --- | --- | --- |
| Points, value ranges, dimensions, coordinates | `record` | Value is determined by components; minimal state |
| Identifiers like `CustomerId`, `ProductCode` | `record` | Creates a clear domain type; place validation/normalization in the constructor |
| Input/output DTOs, messages, computation results | `record` if framework supports it | Often a clear snapshot of components; convenient accessors and equality |
| Order line items, immutable configuration parameters | `record` if components are protected | Good for value-carrying data passed across multiple processing layers |
| Entities with identity, lifecycle, history, version | Usually `class` with explicit identity design | State-based equality does not always equal identity-based equality |
| Objects that must mutate state repeatedly via methods | `class` or a state-transition model returning new instances | Records have no additional mutable instance state; use records to describe static state |
| Objects needing to extend another class or proxy subclassing | Not suitable for `record` | Records are `final` and only extend `Record` |
| Objects containing large/cyclic mutable graphs | Consider carefully | Must perform defensive copying and define appropriate equality |

These are **design guidelines**, not rigid rules such as “no entity may ever be a record” or “every DTO must be a record.” Representing an entity as a **record snapshot for reading data** is completely reasonable, even if the underlying persistence entity uses a class. The decision depends on access contracts, lifecycle, and the tools in use.

**Key question:** do domain consumers expect `new Value(a, b).equals(new Value(a, b))` to be true? If yes, and the state is defined by its components and does not need to change after creation, a record is a strong candidate.

## 4. Shallow Immutability vs. Deep Immutability

### 4.1. Primitive or Built-in Immutable Components

```java
record Point(int x, int y) {}
record CustomerId(String value) {}
```

`int` is a primitive and `String` is immutable. If the constructor disallows invalid states and the record holds no other mutable references, the internal data can be considered immutable according to normal expectations. You cannot call `point.setX(10)` because a record does not generate setters, and the `x` component of a record cannot be reassigned after construction.

However, a record **does not automatically verify** that `CustomerId.value` is a valid string. To treat it as a trustworthy value object, you must design its invariants.

### 4.2. List Components: `final` Does Not Protect the Target Object

Example **with risk of external mutation**:

```java
record UnsafeOrder(java.util.List<String> lines) {}

// Demonstration inside a method:
var source = new java.util.ArrayList<String>();
source.add("BOOK");
var order = new UnsafeOrder(source);

source.add("PEN");           // Mutates the list inside the record!
order.lines().add("RULER"); // The accessor returns the mutable list itself.
```

Even though the `lines` field is final, the contents of the list can change. The behavior of `equals`/`hashCode` can also change over time due to a mutable component, causing hard-to-find bugs if the record is used as a key in a `HashMap` or an element in a `HashSet`.

**How to protect it:**

```java
record OrderLines(java.util.List<String> lines) {
    OrderLines {
        lines = java.util.List.copyOf(
            java.util.Objects.requireNonNull(lines, "lines"));
    }
}
```

`List.copyOf` creates a list that **cannot be modified through the accessor** and is unaffected by add/remove operations on the source list after the record is created. It also rejects `null` elements. When the component elements are `String` (which are immutable), this is a fairly safe model.

**Important limitation:** `List.copyOf` does not turn a mutable element into an immutable one. If a `List<Customer>` contains `Customer` objects with setters, those elements can still be mutated through references held elsewhere. To achieve deeper immutability, use immutable element types (such as safe component records), or defensively copy each element according to the domain contract.

### 4.3. Array Components: Be Careful with Both Accessors and Equality

```java
record UnsafeBytes(byte[] data) {}
```

Java arrays are mutable. `new UnsafeBytes(source)` retains the same reference; `data()` returns that array. In addition, a record's default equality **does not compare the contents of two arrays**: arrays use reference equality unless custom logic is provided.

If you must use an array as a value object, you can write:

```java
record Bytes(byte[] data) {
    Bytes {
        data = java.util.Objects.requireNonNull(data, "data").clone();
    }

    @Override
    public byte[] data() {
        return data.clone();
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof Bytes b
            && java.util.Arrays.equals(data, b.data);
    }

    @Override
    public int hashCode() {
        return java.util.Arrays.hashCode(data);
    }
}
```

The constructor copies the data on input; the accessor copies it on return; `equals/hashCode` apply array content comparison under the same policy. Consider the copying cost and data size. Whenever possible, using a component type that already has appropriate value semantics and immutability is simpler.

A detail worth remembering: **defensive copying, null validation, and equality are three separate responsibilities**. Simply declaring a `record` does not handle them for you.

## 5. Canonical Constructors and Business Invariants

A value object record is useful when its state is **valid at the moment of creation**. For example, a customer ID must not be blank:

```java
record CustomerId(String value) {
    CustomerId {
        value = java.util.Objects.requireNonNull(value, "value").strip();
        if (value.isEmpty()) {
            throw new IllegalArgumentException("CustomerId is blank");
        }
    }
}
```

This is a **compact canonical constructor**. Inside the constructor body, the variable `value` is the parameter corresponding to the component. You can validate and normalize the parameter; the compiler assigns the processed parameter to the record's final field when the constructor completes normally.

Principles:

1. **Validate structure:** non-null, non-empty, allowed types and value domains.
2. **Normalize intentionally:** `strip()`, case normalization, or rounding only when the domain requires it and has clear rules.
3. **Protect mutable inputs:** `List.copyOf`, copy maps/sets, or apply an appropriate defensive copy strategy.
4. **Never let an object exist in a half-valid state:** throw an exception immediately when an invariant fails.
5. **Stay consistent with `equals`:** after normalization, two inputs with the same meaning can produce two equal records.

Example with monetary amounts in the smallest currency unit:

```java
record Money(long minorUnits, String currency) {
    Money {
        if (minorUnits < 0) {
            throw new IllegalArgumentException("Negative amount");
        }
        currency = java.util.Objects.requireNonNull(currency, "currency")
            .strip()
            .toUpperCase(java.util.Locale.ROOT);
        if (!currency.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException("Invalid currency code");
        }
    }
}
```

Here `minorUnits` is defined as a non-negative integer, and the currency code must be three A–Z letters. **Checking a three-letter format does not guarantee it is a valid ISO 4217 code**; if the system requires true validity, a dedicated catalog/check must be added. Disallowing negative amounts is also **this application's policy**, not a mandatory restriction for every `Money` type.

Using `long` minor units avoids binary floating-point rounding errors from `double` in simple monetary problems. For currencies with different minor units, complex rounding/decimal rules, or multi-currency business logic, use an appropriate domain type and consider `BigDecimal` with an explicit scale policy.

## 6. Complete Java 21 Program: Value Objects, Snapshots, and Record Patterns

Create the file **`ImmutableRecordDomainDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public class ImmutableRecordDomainDemo {

    // Value object carrying a normalized identifier.
    record CustomerId(String value) {
        CustomerId {
            value = Objects.requireNonNull(value, "value").strip();
            if (value.isEmpty()) {
                throw new IllegalArgumentException("CustomerId is blank");
            }
        }
    }

    // Immutable component of an order snapshot.
    record LineItem(String sku, int quantity) {
        LineItem {
            sku = Objects.requireNonNull(sku, "sku").strip();
            if (sku.isEmpty()) {
                throw new IllegalArgumentException("SKU is blank");
            }
            if (quantity <= 0) {
                throw new IllegalArgumentException("Quantity must be positive");
            }
        }
    }

    // Snapshot: does not retain the caller's mutable list.
    record OrderSnapshot(CustomerId customer, List<LineItem> lines) {
        OrderSnapshot {
            customer = Objects.requireNonNull(customer, "customer");
            lines = List.copyOf(Objects.requireNonNull(lines, "lines"));
            if (lines.isEmpty()) {
                throw new IllegalArgumentException("Order must have lines");
            }
        }

        int totalUnits() {
            int total = 0;
            for (LineItem item : lines) {
                total = Math.addExact(total, item.quantity());
            }
            return total;
        }
    }

    // A non-negative monetary value per demo policy.
    record Money(long minorUnits, String currency) {
        Money {
            if (minorUnits < 0) {
                throw new IllegalArgumentException("Negative amount");
            }
            currency = Objects.requireNonNull(currency, "currency")
                .strip()
                .toUpperCase(Locale.ROOT);
            if (!currency.matches("[A-Z]{3}")) {
                throw new IllegalArgumentException("Invalid currency code");
            }
        }

        Money plus(Money other) {
            Objects.requireNonNull(other, "other");
            if (!currency.equals(other.currency())) {
                throw new IllegalArgumentException("Different currencies");
            }
            return new Money(
                Math.addExact(minorUnits, other.minorUnits()),
                currency);
        }
    }

    // Record patterns used to branch on domain shape.
    static String describe(Object value) {
        return switch (value) {
            case null -> "Không có dữ liệu";

            case OrderSnapshot(CustomerId(var id), var lines)
                    when lines.size() >= 2 ->
                "Đơn nhiều dòng: " + id;

            case OrderSnapshot(CustomerId(var id), var lines) ->
                "Đơn một dòng: " + id;

            case Money(var amount, var currency) ->
                "Tiền: " + amount + " " + currency;

            default -> "Loại khác";
        };
    }

    public static void main(String[] args) {
        List<LineItem> source = new ArrayList<>();
        source.add(new LineItem(" BOOK ", 2));

        CustomerId customer = new CustomerId("  C-01  ");
        OrderSnapshot snapshot = new OrderSnapshot(customer, source);

        // Mutate the input collection after creating the snapshot.
        source.add(new LineItem("PEN", 3));

        System.out.println("Khách: " + snapshot.customer().value());
        System.out.println("Số dòng snapshot: " + snapshot.lines().size());
        System.out.println("Tổng số món: " + snapshot.totalUnits());

        OrderSnapshot sameValue = new OrderSnapshot(
            new CustomerId("C-01"),
            List.of(new LineItem("BOOK", 2)));
        System.out.println("Equals theo giá trị: "
            + snapshot.equals(sameValue));

        Money total = new Money(1000, " usd ")
            .plus(new Money(250, "USD"));
        System.out.println("Cộng tiền: "
            + total.minorUnits() + " " + total.currency());

        System.out.println(describe(snapshot));
        System.out.println(describe(new OrderSnapshot(
            customer,
            List.of(new LineItem("BOOK", 2),
                    new LineItem("PEN", 3)))));
        System.out.println(describe(total));
        System.out.println(describe(null));

        try {
            snapshot.lines().add(new LineItem("PAD", 1));
        } catch (UnsupportedOperationException ex) {
            System.out.println("Không thể sửa danh sách snapshot");
        }

        try {
            new LineItem(" ", 0);
        } catch (IllegalArgumentException ex) {
            System.out.println("Từ chối dòng không hợp lệ");
        }
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac --release 21 -encoding UTF-8 ImmutableRecordDomainDemo.java
java ImmutableRecordDomainDemo
```

Expected output:

```text
Khách: C-01
Số dòng snapshot: 1
Tổng số món: 2
Equals theo giá trị: true
Cộng tiền: 1250 USD
Đơn một dòng: C-01
Đơn nhiều dòng: C-01
Tiền: 1250 USD
Không có dữ liệu
Không thể sửa danh sách snapshot
Từ chối dòng không hợp lệ
```

### Analysis of Design Decisions

- `CustomerId("  C-01  ")` normalizes to `"C-01"` in the compact constructor; two `CustomerId` instances with the same normalized value have component-based equality.
- `LineItem(" BOOK ", 2)` becomes SKU `"BOOK"`, and quantity must be positive. Each `LineItem` has only `String` and `int`, making it suitable for an immutable list.
- `OrderSnapshot` uses `List.copyOf`. Adding `"PEN"` to `source` afterward **does not** modify `snapshot.lines()`, so the line count remains `1` and total units remain `2`.
- `snapshot.equals(sameValue)` is `true` because `customer` and `lines` have matching component equality, lists compare by order and elements, and `LineItem` also compares by components.
- `Money.plus` checks for the same currency and uses `Math.addExact` to throw on integer overflow instead of silently producing a wrong result. The method returns a new record without mutating the old one.
- `describe` uses the nested record pattern `OrderSnapshot(CustomerId(var id), var lines)`. The variable `id` already has type `String`, and `lines` has type `List<LineItem>`, usable in both the `when` guard and the branch body. The two `OrderSnapshot` branches must be ordered from the more specific guarded branch to the general branch.
- `case null` handles a null selector; `default` handles other types. A record pattern only matches when the target object and the required nested records are non-null.
- `snapshot.lines().add(...)` throws `UnsupportedOperationException` because the accessor returns an unmodifiable list. The constructor also rejects invalid `LineItem` invariants.

**This is a domain snapshot demonstration program**, not a complete order system. It does not include persistence, transactions, concurrency synchronization, discounts, taxes, regional rules, or refund policies.

## 7. Value Semantics, Equality, and Pitfalls

A typical record has `equals`/`hashCode` generated from its components, which is very useful when:

- Using `CustomerId` as a map key or in a set of values.
- Comparing two `Point` instances or two independent computation results.
- Detecting unchanged snapshot contents.

However, **a record's value semantics are component-based** and do not automatically understand business identity:

```java
record CustomerView(String id, String name) {}

CustomerView a = new CustomerView("C-01", "An");
CustomerView b = new CustomerView("C-01", "Anh");

// Not equal because name differs,
// even though they may refer to the same customer entity id in the system.
System.out.println(a.equals(b)); // false
```

If only the ID determines identity, you should not default to using all component state for entity equality. You can keep the domain entity as a class or write a dedicated value object such as `CustomerId`.

### Cases Requiring More Careful Equality Decisions

1. **Arrays:** default array equality is by reference; consider a wrapper, copying, or deep comparison.
2. **Collections:** `List.equals` compares by element and order; lists with different ordering may not be equal. If the business treats items as unordered, choose an appropriate model.
3. **`BigDecimal`:** `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` is `false` because the scales differ, even though `compareTo` considers them equal. If using `BigDecimal` in a `Money` record, design normalization/scale according to the currency policy.
4. **Mutable components:** mutating state changes the record's hash/equality over time; dangerous when used as a `HashMap` key.
5. **Normalization:** two differently formatted strings can be treated as the same value if normalized consistently in the constructor. Do not normalize arbitrarily when the business needs to preserve the distinction.

Do not override `equals`/`hashCode` to arbitrarily “hide” a field while forgetting to preserve the `equals`/`hashCode` contract and the meaning of the record. If component-based equality does not accurately reflect the value of the type, re-evaluate its components or choose a `class`.

## 8. Records, Entities, and Snapshots: Separation of Responsibilities

In a domain model, you can have all of the following at the same time:

- **Entity:** `Order` carrying an ID, version, processing state, state-transition behavior, and transactional invariants.
- **Value objects:** `Money`, `CustomerId`, `LineItem`, `Address`, immutable by contract.
- **Snapshot or DTO:** `OrderSnapshot` capturing an entity's state at a point in time to return from an API, render UI, cache, or transfer across layers.

Conceptual architecture example:

```text
Order (entity / class)
    ├── id: OrderId                 (value object / record)
    ├── total: Money                (value object / record)
    ├── lines: List<LineItem>       (immutable elements)
    └── state transitions: place(), cancel(), fulfill()
                  |
                  | create snapshot on read
                  v
OrderSnapshot (record)
    ├── id
    ├── items (unmodifiable snapshot list)
    └── status (value or enum)
```

If an ORM framework requires a no-arg constructor, proxy subclassing, setters, or field mutation, a `record` is usually not suitable as a direct entity. However, many systems still use records for **projections/read models**, DTOs, or query results. Check the official support of the framework and version you are using rather than assuming all tools behave the same way.

**Records do not forbid behavioral methods.** A record can contain computation methods and methods that return a new copy, as long as the design preserves value-object semantics. For example, `Money.plus` in the main program is domain behavior, not just an “inert” data structure.

## 9. Using Record Patterns Without Compromising Immutability

Java 21 allows testing and **deconstructing** a record:

```java
if (value instanceof Money(var amount, var currency)) {
    System.out.println(amount + " " + currency);
}
```

This pattern extracts components into variables. It does not mutate the record. With a nested record pattern:

```java
case OrderSnapshot(CustomerId(var id), var lines)
        when lines.size() >= 2 ->
    "Đơn nhiều dòng: " + id;
```

Reading order:

1. The selector must be a non-null `OrderSnapshot`.
2. The `customer` component must be a non-null `CustomerId` because of `CustomerId(...)`.
3. `var id` receives the `String value` inside `CustomerId`.
4. `var lines` receives `List<LineItem>`; the `when` guard uses that list to check the line count.
5. When all patterns match and the guard is true, the branch is selected.

**Subtle point:** record patterns do not make data “safer” on their own. If a record has a mutable component and its accessor returns the reference directly, `var list` in the pattern will also receive that same mutable reference. For a trustworthy value model, immutability must be protected in **type and constructor design**, not by relying on deconstruction.

With safely immutable records, pattern matching is a natural way to access data without casting or chaining nested accessor calls.

## 10. When Does Using a Record Cause Friction?

### 10.1. Domains Requiring In-Place State Mutation

```java
// A record has no setters to mutate final components.
record Counter(int count) {
    Counter next() {
        return new Counter(Math.addExact(count, 1));
    }
}
```

This approach is **valid** if the problem domain needs new counter snapshots. But if the counter must change continuously, synchronize across threads, or preserve the identity of a long-lived object, a stateful class may be more appropriate.

### 10.2. Many Components Changing Structure Over Time

A record carries an explicit data contract. Adding, removing, changing types, or reordering components changes the API/constructor, pattern deconstruction, and potentially `equals`/`toString`. For public APIs, backward compatibility and serialization must be managed deliberately.

Just because a record is concise does not mean components can be added casually. A new component can change the meaning of `equals` and break existing `new Record(...)` calls; `Record(...)` patterns must also be updated for the new component count.

### 10.3. Very Large Data or Nested Mutable Graphs

Defensively copying everything on every record creation can incur significant cost. If the graph has cycles, holds open resources (sockets, streams), or needs a complex lifecycle, a record does not solve resource management on its own. Evaluate the data model, ownership, and copying cost before choosing.

### 10.4. Modeling Around Framework Getters/Setters

Some frameworks by default recognize JavaBeans via `getName()`/`setName()` or require a no-arg constructor. Records use accessors named `name()` and final components. If a library does not yet support records well, use a DTO adapter/class or configure a compatible adapter rather than bending a value object to satisfy an ill-fitting API.

## 11. Common Mistakes

| Mistake or Misconception | Why It Is Wrong | How to Handle It |
| --- | --- | --- |
| “Records are always deeply immutable” | Final references do not freeze Lists, arrays, or referenced objects | Use immutable components, defensive copies, and do not expose mutable state |
| “Records never need a constructor” | There is no default validation for null, negative numbers, or blank strings | Use a compact canonical constructor to enforce invariants |
| “`List.copyOf` makes every element immutable” | It only creates an unmodifiable/snapshot list, not a deep copy of mutable elements | Use value-object elements or copy elements individually |
| “With an array component, two records with the same bytes are `equals`” | Default array equality is reference-based | Implement content equality and defensive copying, or change the component type |
| Using `record Customer(id, name)` and comparing entities by all fields | Entity identity often differs from snapshot/value equality | Separate entities from value objects/read models |
| Using `record` for continuous mutable state changes via setters | Components are final; no setters are generated | Use a class/state machine or intentionally return a new record |
| Using `double` for money without a precision policy | Floating-point has binary rounding errors | Choose minor units or `BigDecimal` with domain rules |
| Adding two `Money` values with different currencies | Quantities in different units cannot be added arbitrarily | Check currency and convert using an explicit exchange rate/source when needed |
| Assuming record patterns validate business rules automatically | Patterns mainly check structure/type and extract data | Constructors enforce invariants; guards check contextual rules |
| Placing a general `case` before a guarded `case` | The specific branch can be dominated | Place specific branches before broader catch-all branches |
| Not checking nullable components | Shallow immutability does not forbid null | Use `Objects.requireNonNull` and null checks where needed |
| Arbitrarily changing components in a public API record | Affects constructors, accessors, patterns, and equality | Manage compatibility and migration with tests |

## 12. Checklist When Choosing a Record for a Domain Type

Before creating a new type, answer:

1. **Identity:** should two instances with the same components be equal? If not, are you modeling an entity rather than a value object?
2. **State:** does it need in-place mutation, or should each change produce a new value?
3. **Invariants:** can the type reject null, blank strings, negative numbers, invalid currencies, or empty lists in its constructor?
4. **Component types:** are the components truly immutable? Are there Lists, Maps, Sets, arrays, legacy `Date`s, or objects with setters?
5. **Ownership:** if accepting a collection from the caller, do you create a snapshot copy and avoid exposing mutable references through the accessor?
6. **Equality/hash:** does each component's equality match domain semantics? Are there arrays or `BigDecimal` scale differences?
7. **API constraints:** what do your framework, persistence layer, serialization, and public constructors require?
8. **Readability:** does a record make the state clearer to readers, or are there too many components and overly deep nested patterns?
9. **Behavior:** can pure methods and methods returning new values be placed on the record?
10. **Testing:** have you tested equality, `hashCode`, normalization, defensive copying, null handling, boundaries, and exceptions?

If the answers for identity/value semantics, immutability, and ownership are clear, a record is a strong choice. If you need a series of workarounds to maintain a mutable lifecycle or complex identity, reconsider the design.

## 13. Practice Exercises

**Exercise 1 — Entity vs. value object classification.** Choose `record` or `class` for: `GeoPoint`, `Money`, `OrderId`, `OrderSnapshot`, `OrderEntity` with an updatable payment status, and `ConnectionPool`. Explain in terms of equality, identity, state, and resources.

**Exercise 2 — Fix an immutability bug.** Given `record Tags(List<String> values) {}`, write a compact constructor so that mutating the caller's original `List` does not change `Tags`, and the accessor does not allow adding elements. Hint: use `Objects.requireNonNull` and `List.copyOf`.

**Exercise 3 — Mutable elements.** Change the component to `List<MutableAddress>`, where `MutableAddress` has setters. Why is `List.copyOf` not enough? Propose an immutable `Address` record or per-element copying.

**Exercise 4 — Equality with arrays.** Consider two instances `new UnsafeBytes(new byte[]{1,2})`. Are they equal by default? Answer: normally **no**, because the two arrays are distinct objects. Apply the `Bytes` design from Section 4 and test `equals`/`hashCode`.

**Exercise 5 — Domain invariants.** Extend `Money` to reject blank currency codes; test passing `"usd"`, `" USD "`, `"ZZ"`, and `null`. Explain the difference between checking the `[A-Z]{3}` format and validating a real currency.

**Exercise 6 — Pattern matching.** Add a branch `case Money(var amount, var currency) when amount == 0 -> "Miễn phí"` before the general `Money` case. Explain why branch order matters and why a record pattern does not make `Money` mutable.

**Exercise 7 — Testing snapshots.** In the main program, try adding a `LineItem` to the `source` list after creating `OrderSnapshot`, then read `snapshot.totalUnits()` and `source.size()`. Predict the difference. If `LineItem` were replaced with a mutable class, what additional tests would be needed to protect immutability?

## 14. Summary

**Choose `record` when a domain type represents a value defined by its components, with clearly designed invariants and immutability.** Records reduce boilerplate, provide component-based value equality, and integrate naturally with Java 21 record patterns; however, they **do not** automatically provide deep immutability, validate data, or replace every entity or stateful service.

Good record design usually rests on three pillars: **appropriate components**, **a canonical constructor that enforces invariants**, and **no leaking of mutable state**. From there, you can leverage equality and deconstruction to write code that is easier to read, easier to test, and safer.

### References

- [Oracle Java 21 — Record Classes](https://docs.oracle.com/en/java/javase/21/language/records.html)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [JEP 395 — Records](https://openjdk.org/jeps/395)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Java SE 21 API — List.copyOf](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection))
