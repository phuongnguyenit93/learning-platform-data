# Record Contracts: `equals()`, `hashCode()`, and `toString()` Generated from Components

## 1. What Problem Do Records Solve?

A **record** in Java represents data using a list of **record components** declared right in the class header. With Java 17, instead of manually writing a constructor, fields to store values, accessors, and the `Object` methods typically needed for a data object, you can declare:

```java
record Product(String sku, int quantity) {}
```

From this declaration, the compiler provides the necessary members, including:

- Two corresponding instance fields: `private final String sku` and `private final int quantity`.
- A canonical constructor (`canonical constructor`) with parameters in the order of the components: `Product(String sku, int quantity)`.
- Accessors with the same names as the components: `sku()` and `quantity()`, unlike JavaBeans-style getters such as `getSku()`.
- Implementations of `equals(Object)`, `hashCode()`, and `toString()` based on **the record components**.

A record is implicitly `final`, directly extends `java.lang.Record`, and cannot extend another superclass. It can implement interfaces, have its own methods, static members, and additional constructors that forward to the canonical constructor, and it can provide its own implementations of methods permitted to be overridden. It cannot declare regular instance fields beyond the fields derived from the record components.

This lesson focuses on **the contract of the three generated methods**: which components Java uses to determine equality, how the hash is derived, how the object is printed, and the limitations when a component is a mutable reference. Records help eliminate boilerplate code, but **they do not make every component deeply immutable**.

### Learning Objectives

After this lesson, you can:
1. Predict `equals`, `hashCode`, and `toString` of a record simply by reading its component list.
2. Explain why two different record instances can be equal, while two records of different types are not equal even if they contain the same data.
3. Prove the condition `equals ⇒ equal hashCode`, and distinguish it from the false converse.
4. Explain and reproduce the behavior of records with `String`, `List`, array, and floating-point components.
5. Use a compact constructor or canonical constructor to normalize, validate, and copy data when appropriate.
6. Know when to use the compiler-generated implementations, and when to choose another type/value model or override responsibly.

## 2. Basic Mechanism: Components Determine the Value of a Record

Given:

```java
record Coordinate(int x, int y) {}
```

The components are `x` and `y`. Two instances `new Coordinate(3, 5)` and `new Coordinate(3, 5)` differ in reference, yet are equal under the record's `equals` implementation. `new Coordinate(5, 3)` is different because the corresponding values do not match. A record uses the **record type name**, the number/types of components, and the corresponding values; it does not merely "compare every field via reflection" arbitrarily.

Compared with a regular Java class:

```java
final class CoordinateClass {
    private final int x;
    private final int y;

    CoordinateClass(int x, int y) {
        this.x = x;
        this.y = y;
    }

    // Without overriding equals/hashCode/toString:
    // equals inherited from Object: compares reference identity.
}
```

This is a separate illustrative snippet. In a regular class, declaring `final` and two `final` fields does **not** make the compiler automatically write value equality; whereas in a record, the methods matching the component model are generated automatically.

Remember: **component order matters** because a record has a constructor/accessors in the declared order, `toString` presents them in that order, and the corresponding components participate in comparison. Do not rely on an arbitrary permutation of field names to conclude that two records of different kinds are equal.

## 3. The Generated `equals(Object)` Contract

### 3.1. When Are Two Records Equal?

For two instances belonging to the same **record class**:
- Reference-type components are compared with `Objects.equals` semantics (null-safe, and calling `equals` on the component object when non-null).
- Primitive components are compared with the value semantics of their corresponding type; specifically, `float`/`double` have comparison semantics consistent with `Float.compare`/`Double.compare`, requiring attention to `NaN` and signed zero.
- Every corresponding component must be equal; differing in just one component makes the records unequal.
- `record.equals(null)` is `false`; `record.equals(record)` is always `true`.

If two instances belong to different record classes, the generated `equals` implementation will not consider them equal, even when the components have the same names and values.

Example:

```java
record Point(int x, int y) {}
record Location(int x, int y) {}

// Inside a method:
Point p1 = new Point(2, 4);
Point p2 = new Point(2, 4);
Location l = new Location(2, 4);

System.out.println(p1 == p2);  // false
System.out.println(p1.equals(p2)); // true
System.out.println(p1.equals(l));  // false
```

This is an isolated example snippet to focus on equality; the record declarations are valid at class scope or locally where declarations are permitted, and the statements need to be inside a method.

Do not confuse record-generated equality with:
- `==`: compares **same reference** since a record is a Java object.
- Comparing only `toString`: it is just a display string and must not be used as the basis for defining equality.
- Comparing business keys: by default, a record compares **all components**, including components your domain might want to ignore.
- Comparing through inheritance: a record is `final`, so there is no subclass of that record itself.

### 3.2. How Is `null` Handled?

A reference-type component **can be null** unless the constructor checks and rejects it. Two instances of the same record type having a `null` component at the same position can still be equal:

```java
record Note(String text) {}

// Inside a method:
new Note(null).equals(new Note(null))  // true
new Note(null).equals(new Note("x"))   // false
```

The last two expressions illustrate boolean results, not two standalone Java statements that run on their own without using them in an assignment/call. If business rules disallow null, validate in the constructor, for example `Objects.requireNonNull(text, "text")`.

**Difference from entities with a deferred ID:** a simple record storing `id = null` will by default treat two records of the same type with the same components as equal. If each instance without an ID yet must have its own entity identity, a "compare-all-components" record may not accurately express the domain. Design identity explicitly instead of assuming a record automatically recognizes entity lifecycle.

### 3.3. Reference Types Use Their Own Equality

If a record contains `BigDecimal amount`, the generated `equals` calls `BigDecimal`'s equality. In Java:

```java
record Price(java.math.BigDecimal amount) {}

// Inside a method:
Price a = new Price(new java.math.BigDecimal("1.0"));
Price b = new Price(new java.math.BigDecimal("1.00"));
System.out.println(a.equals(b)); // false
```

`BigDecimal.equals` considers both numeric value and scale; whereas `BigDecimal.compareTo` returns `0` for the two values above. A record does not automatically normalize `BigDecimal` or replace comparison according to business logic. If the domain treats those two numbers as equivalent, you must agree on a normalization policy (e.g., in the constructor) or choose an appropriate model.

For `String`, `String.equals` compares contents, so two `String` instances with the same contents yield equality; `record` does not require the `String`s to be the same object.

### 3.4. The `float` and `double` Cases

Preserve the special semantics of floating-point numbers:
- `NaN` values of the same component are considered equal under record equality logic.
- `+0.0` and `-0.0` are distinguished in equality of `float`/`double` components.
- This comparison ensures the contract with the record's hash code.

You should not manually emulate `double` record equality with the `==` operator and then draw wrong conclusions about `NaN` or signed zero. When the domain needs to define "approximately equal" within a numeric tolerance, that is a different problem from equality used for `HashMap`/`HashSet`, because tolerance comparison may not be transitive.

## 4. The Generated `hashCode()` Contract

The compiler generates the `hashCode` implementation from the same components used by `equals`. The critical rule to verify is:

**If `a.equals(b)` returns `true`, then `a.hashCode() == b.hashCode()` must be `true`.**

The converse does not hold: matching hashes (a collision) do not prove records are equal. There is no rule that "each record has a unique hash", and you should not use a hash as a business ID.

Characteristics to understand:
- Primitive/reference components contribute to the hash value according to their respective semantics; the implementation preserves the equality contract.
- `null` components are handled validly; there is no need to write a null-safe hash manually.
- The combining algorithm and the **specific hash number** of a record are not a storage format or stable protocol that an application should depend on. Avoid hard-coding `hashCode() == 123456` in tests or storing hashes as durable keys.
- If a component is a **mutable** object, the record's hash can change if that component's hash changes. Record fields are `final`, but the referenced object may still be mutable.

### Using Records in `HashSet` and `HashMap`

A record containing immutable components with stable equality is often very convenient as a key:

```java
record CustomerKey(String tenant, long id) {}

// Inside a method:
var map = new java.util.HashMap<CustomerKey, String>();
map.put(new CustomerKey("SHOP", 42), "paid");
System.out.println(map.get(new CustomerKey("SHOP", 42))); // paid
```

The two key instances have different references, yet record equality/hash are both based on `tenant` and `id`, so the map can look up by value.

Conversely, a record containing a mutable `List` can fail: after adding it as a key, the caller mutates the list externally, `hashCode` recalculates from the changed contents, and lookup may fail to find it. The issue lies in **mutable component state**, not in the compiler generating a bad hash.

### A Record's Hash Is Not a Unique Fingerprint

Even with immutable components, the number of `int` hash values has only 2³² possibilities while the number of records can be much larger. Collisions are normal, and `HashMap` still uses equality to resolve them. If you need a checksum/stable identifier across systems, you must use a deterministic algorithm over a normalized data representation, rather than repurposing `hashCode()`.

## 5. The Generated `toString()` Contract

Records provide a useful `toString` for reading logs and debugging. Java 17 displays a format containing the **record name** and **component name = value** pairs in declaration order:

```java
record Product(String sku, int quantity) {}

// Inside a method:
System.out.println(new Product("BOOK", 2));
// Product[sku=BOOK, quantity=2]
```

There is no need to manually concatenate strings when you just want to inspect data in a simple DTO/value object. When a record contains another record or a list, the component's `toString` is invoked via that object's String representation.

Important limitations:
- `toString` is not a standard serializer and does not replace JSON, CSV, database keys, or data transfer formats.
- For arrays, the default display format is typically the array type name and identity hash, not listing elements with `Arrays.toString`.
- With mutable components, `toString` can **change** after the record is created even though the component field is `final`.
- Sensitive components such as tokens, passwords, and personally identifiable data can be accidentally exposed through logs. In such cases, consider a custom `toString` that masks data or avoid logging the record directly.
- Do not use `toString` to determine `equals` or hashing; display is a separate responsibility from identity.

## 6. Standalone Java 17 Program: Three Generated Methods and Edge Cases

Create the file **`RecordContractDemo.java`** below. The example includes: a record with two immutable components, a record containing a snapshotted list, a record holding a mutable list without defense, a record containing an array, and a record containing a floating-point number. The records are declared nested inside the main class to compile as **a single file**.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class RecordContractDemo {
    record Product(String sku, int quantity) {
        Product {
            sku = Objects.requireNonNull(sku, "sku").strip();
            if (sku.isEmpty()) {
                throw new IllegalArgumentException("blank sku");
            }
            if (quantity <= 0) {
                throw new IllegalArgumentException("invalid quantity");
            }
        }
    }

    record Cart(String owner, List<Product> items) {
        Cart {
            Objects.requireNonNull(owner, "owner");
            items = List.copyOf(Objects.requireNonNull(items, "items"));
        }
    }

    // No snapshot: component references a mutable list.
    record OpenBox(List<String> tags) {}

    // Two arrays with different references are not equal under record equality.
    record Bytes(byte[] data) {}

    record Reading(double value) {}

    public static void main(String[] args) {
        Product p1 = new Product(" BOOK ", 2);
        Product p2 = new Product("BOOK", 2);
        Product p3 = new Product("PEN", 1);

        System.out.println("same instance: " + (p1 == p2));
        System.out.println("products equal: " + p1.equals(p2));
        System.out.println("hash equal: "
                + (p1.hashCode() == p2.hashCode()));
        System.out.println("product print: " + p1);

        Set<Product> products = new HashSet<>(List.of(p1, p2, p3));
        System.out.println("set size: " + products.size());

        Map<Product, String> stock = new HashMap<>();
        stock.put(p1, "available");
        System.out.println("map lookup: " + stock.get(p2));

        List<Product> source = new ArrayList<>(List.of(p1));
        Cart cart = new Cart("SHOP", source);
        source.add(p3);
        System.out.println("cart items: " + cart.items());
        System.out.println("cart print: " + cart);
        System.out.println("same cart value: "
                + cart.equals(new Cart("SHOP", List.of(p2))));

        boolean editRejected = false;
        try {
            cart.items().add(p3);
        } catch (UnsupportedOperationException expected) {
            editRejected = true;
        }
        System.out.println("cart edit rejected: " + editRejected);

        List<String> mutableTags = new ArrayList<>(List.of("a"));
        OpenBox box = new OpenBox(mutableTags);
        int hashBefore = box.hashCode();
        mutableTags.add("b");
        System.out.println("box tags after edit: " + box.tags());
        System.out.println("box hash changed: "
                + (hashBefore != box.hashCode()));
        System.out.println("box print after edit: " + box);

        Bytes b1 = new Bytes(new byte[] {1, 2});
        Bytes b2 = new Bytes(new byte[] {1, 2});
        System.out.println("arrays as components equal: " + b1.equals(b2));
        System.out.println("array contents equal: "
                + Arrays.equals(b1.data(), b2.data()));

        System.out.println("NaN records equal: "
                + new Reading(Double.NaN).equals(
                        new Reading(Double.NaN)));
        System.out.println("signed zero records equal: "
                + new Reading(+0.0).equals(new Reading(-0.0)));
    }
}
```

Run with JDK 17 or later:

```bash
javac --release 17 RecordContractDemo.java
java RecordContractDemo
```

Output:

```text
same instance: false
products equal: true
hash equal: true
product print: Product[sku=BOOK, quantity=2]
set size: 2
map lookup: available
cart items: [Product[sku=BOOK, quantity=2]]
cart print: Cart[owner=SHOP, items=[Product[sku=BOOK, quantity=2]]]
same cart value: true
cart edit rejected: true
box tags after edit: [a, b]
box hash changed: true
box print after edit: OpenBox[tags=[a, b]]
arrays as components equal: false
array contents equal: true
NaN records equal: true
signed zero records equal: false
```

### Explaining Why Those Lines Are Correct

1. `p1` and `p2` are created by two `new` statements so `==` returns `false`. The `Product` compact constructor uses `strip()` to normalize the SKU to `"BOOK"`; with the same `quantity`, the compiler-generated `equals` returns `true`, and the hashes must also be equal.
2. `HashSet` keeps two distinct values: `Product("BOOK", 2)` and `Product("PEN", 1)`. `HashMap` finds the string `"available"` using `p2` even though the key was stored using `p1`, illustrating a record as a value key.
3. `Cart` uses `List.copyOf` in the compact constructor, so the caller adding `p3` to `source` after construction does not change the list inside `cart`. The list returned from the accessor does not allow `add`, so the catch block records `UnsupportedOperationException`.
4. `Cart` compares both components `owner` and `items`. List equality compares sequential contents, and the `Product` elements are compared by record equality. Therefore, the cart created from `p1` equals the cart created from `p2`.
5. `OpenBox` retains the original list without snapshotting. After the caller adds `"b"`, the accessor, hash, and `toString` all reflect the new contents. The changing hash can cause bugs if `box` is currently inside a hash collection.
6. The two `Bytes` instances hold two `byte[]` arrays with different references. Arrays do not override `Object.equals` by contents so record equality returns `false`, whereas explicitly calling `Arrays.equals` returns `true`.
7. `Reading` uses the equality rule for `double`: two `NaN`s are equivalent under the record, while `+0.0` and `-0.0` differ. This is the semantics of the record contract, not directly applying the `==` operator on the doubles.

**Output reliability:** The program does not print hashes as numbers because you should not rely on the specific value of `hashCode`. It only prints boolean comparisons guaranteed by the contract. The text/list values are fixed so the output does not depend on `HashSet` iteration order; the program only prints `size()`.

## 7. What Records Generate and What They Do Not Do Automatically

| Feature | Compiler Support | Notes |
|---|---|---|
| Accessor for each component | `sku()`, `quantity()` | Does not automatically generate JavaBeans getters `getSku()` |
| Canonical constructor | Matching component order and types | A compact constructor can be written to validate/normalize |
| `equals` | Based on all components | Uses reference type's equality; does not automatically pick business keys |
| `hashCode` | Consistent with `equals` | Does not replace a stable ID or cryptographic hash |
| `toString` | Record name and component names/values | Can expose sensitive data; not a serializer |
| Fields corresponding to components | `private final` | **Reference** immutability, not necessarily deep immutability |
| Copying collections or arrays | **No** | Defensive copying is needed if the domain requires immutable state |
| Checking `null`/business rules | **No** | The constructor must validate explicitly if rejection is desired |
| Ordering `Comparable` | **No** | Implement `Comparable<T>` or provide a separate `Comparator<T>` |
| Equality on a subset of components | **Not by default** | Design the model or override properly if truly needed |

A record like `record User(String email, String displayName) {}` **compares both components**, not just email by default. If the application only wants identity by an immutable code, a clearer approach is usually to create a separate `UserId`/`UserKey` or rethink the entity model; overriding equality arbitrarily easily breaks the expectation that a record carries value semantics across all components.

## 8. Boundaries of the Overview Example

`List.copyOf` can snapshot the list structure but does not deep-copy mutable elements; arrays as components still compare by identity even if bytes match. A record with `final` fields can still hold mutable state, and that data can affect `equals`, `hashCode`, `toString`, or hash keys. The overview example above helps identify risks; the following lessons explain each case in detail with dedicated code.

When a non-default policy is needed, prefer choosing the right components and canonical constructor: normalize data before storing; defensively copy at the right level; only override `equals` together with `hashCode` if you want to change value equality, such as comparing arrays by contents. You can override `toString` alone to avoid logging secrets, but do not use the printed output as a protocol. If only an ID defines identity, a separate `ProductId` key record is usually clearer than silently omitting components in `equals`.

## 9. Self-Check Exercises

### Exercise A — Predict the Output

Given:

```java
record UserName(String first, String last) {}

UserName u1 = new UserName("An", "Le");
UserName u2 = new UserName("An", "Le");
UserName u3 = new UserName("Le", "An");
```

Determine `u1 == u2`, `u1.equals(u2)`, `u1.equals(u3)`, and `u1.hashCode() == u2.hashCode()`. The answers are `false`, `true`, `false`, `true` respectively.

### Exercise B — Error When Ignoring a Component

Create `record Entry(long id, String status) {}`. Are two records with ID `10` but different statuses equal? No: both `id` and `status` participate in equality. If the business logic wants identity by ID only, design a separate `EntryId` or clarify why an entity is needed instead of a value snapshot.

### Exercise C — Arrays

Create two `record Data(byte[] bytes) {}` with two distinct `{1, 2}` arrays. Predict `equals` and try `Arrays.equals`. Explain the risk when the default getter returns a mutable array, even if the record's `hashCode` does not change with array elements.

### Exercise D — Mutable List in `HashSet`

Create `record Tags(List<String> tags) {}`. Add the object to a `HashSet`, then modify the source list; print the hash before/after and test `contains`. If lookup happens to succeed on one run, explain why mutating state makes using the key unreliable. Fix the record using `List.copyOf` and try again.

### Exercise E — Special Numeric Tests

Create `record F(double value) {}` and test `Double.NaN`, `+0.0`, and `-0.0`. Compare the `==` operator on doubles with the record's generated `equals` and explain why the results differ.

### Exercise F — Customizing `toString`

Write `record ApiToken(String owner, String secret)`. Override only `toString` so `secret` is not shown, while keeping the generated equality/hash considering both components. Discuss when **the entire record should not be logged** even if partially masked.

## 10. Application Checklist

- Identified all record components and the meaning of each component in value equality.
- Validated null and normalized inputs when required by the domain.
- Checked primitives, references, `BigDecimal`, and floating-point numbers according to each component type's equality.
- Understood that generated `hashCode` preserves the contract with generated `equals`; do not confuse collisions with equality.
- Understood that `toString` is only a representation for reading/debugging and may expose sensitive data.
- Checked components that are arrays, lists, or mutable objects; applied appropriate defensive copies/snapshots if needed.
- Known how to use records as `HashMap`/`HashSet` keys when data participating in equality/hash is stable.
- If overriding `equals`, reviewed and retested `hashCode` and semantics.
- Ran `RecordContractDemo.java` and can explain every line of output.

**Remember:** Java records generate `equals()`, `hashCode()`, and `toString()` from their components, helping represent data with concise value semantics. The quality of the contract still depends on **the type and semantics of each component**, normalization policies, the degree of immutability, and how the object is used in collections.