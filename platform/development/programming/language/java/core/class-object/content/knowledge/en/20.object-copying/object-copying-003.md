# Deep Copying and the Scope of Data to Copy in Java

**Deep copying (deep copy)** is the operation of creating a new representation of an object's state so that **mutable components that need to be separated independently** are no longer unintentionally shared between the original and the copy. In Java, the hard question is not just "use `clone()` or a constructor?", but:

> **What scope of data belongs to the snapshot? Which components need independent copies created, and which components should preserve their original identity or be safely shared?**

Consider an `Order` consisting of an `OrderLine` list, customer information, a reference to `ProductCatalog`, and `PaymentGateway`:

- Order lines whose quantities are allowed to be edited: usually **need to be copied** if creating an independent draft order.
- Product codes and immutable product name strings: can be **shared**.
- The reference to `ProductCatalog`, which is a lookup service: usually **does not belong to the snapshot payload**.
- `PaymentGateway` has a connection/resource: **do not deep copy** as data.
- If two lines point to the same mutable `DiscountRule` object, you must decide whether the copy keeps **an internal shared alias** or creates independent rules.
- If two objects reference each other mutually, the copy algorithm must handle **cycles**, without infinite recursion.

This lesson belongs to the **Object Copying** section of Java Core, using **Java 17+**. The content covers the object graph model, determining boundaries/ownership, shallow copy and deep copy, preserving aliases/cycles, how to copy arrays/collections/custom classes/records, copy constructors/factories/`clone`, resources/identity, snapshots under concurrency, testing results, common mistakes, and a compilable/runnable program with deterministic stdout.

## 1. What Does Copying an Object Mean?

Suppose:

```java
class Note {
    String text;
    Note(String text) { this.text = text; }
}

Note original = new Note("Java");
Note alias = original;
```

The statement `Note alias = original;` **does not copy the object**: both variables point to the same instance.

```java
System.out.println(original == alias); // true
```

If we do:

```java
Note copy = new Note(original.text);
```

we create a new instance with an equivalent initial `text` state. Because `String` is immutable, the two Note objects can share the String reference without the text state being directly modified by one side.

However, when fields contain mutable objects, an operation that copies only the field references is not enough to separate state.

### Practical Definitions

- **Reference assignment:** does not create a copied object; same identity.
- **Shallow copy:** creates a new outer object, copying primitive values and references to child objects.
- **Deep copy:** creates a new outer object and copies the mutable descendants **within the scope of data requiring independence**; immutable values or out-of-scope dependencies may be shared.
- **Snapshot:** a representation of state at a logical point in time; can be immutable or mutable, shallow or deep depending on the contract.
- **Immutable:** observable state does not change after construction; **not synonymous** with having been deep copied.

Saying "deep copy everything reachable" is usually both infeasible and incorrect for the business domain. **The scope must be defined first.**

## 2. Object Graphs, Not Just Trees

Java objects connect to each other via references to form an **object graph**:

```text
Order
 ├── lines: ArrayList
 │    ├── Line A ──► Product("P01")
 │    └── Line B ──► Product("P02")
 ├── customer ────► Customer("C07")
 ├── gateway ─────► PaymentGateway service
 └── catalog ─────► Shared Catalog service
```

A shallow traversal only sees direct fields. A deep traversal can find nested collections, arrays, domain values, back-references, caches, services, and resources.

However, **"reachable" is different from "owned state"**:
- `Order.lines` may be a constituent part of the order data.
- `Order.gateway` may just be an injected service.
- `Order.catalog` may be a singleton used by many orders.
- `Product` may be an immutable shared lookup value.
- `Customer` may be an entity looked up by ID, which should not be arbitrarily duplicated and assigned a new identity.

**The copy boundary** is usually a selective set of edges/nodes in the graph, not the entire rest of the JVM.

## 3. Three Rules for Deciding What to Copy

For each field/reference when building a copy, ask:

1. **Does it belong to the value state of the object being snapshotted?** If not, do not copy it by default; you can omit it, reattach it, keep a shared reference, or keep only its ID.
2. **If that element is mutated after copying, does the other side need to remain unaffected?** If yes, you need to copy it or convert to an immutable representation.
3. **Must the identity relationship of references in the original be preserved?** If two edges point to the same child, sometimes the copy must also have two edges pointing to **the same child copy**.

From this, we have the following policies:

| Component Type | Usually Reasonable Policy |
| --- | --- |
| Primitive `int`, `boolean`, `double` | Copy the value |
| `String`, `Instant`, truly immutable records | Share safely |
| `int[]`, `ArrayList<MutableItem>` | Copy the mutable part within the snapshot |
| Mutable value child belonging to the owner | Copy recursively according to the contract |
| Shared immutable lookup/cache | Can be shared |
| Other JPA entity/aggregate, external identity | Usually use an ID or reference; do not duplicate indiscriminately |
| `Socket`, `Connection`, `Thread`, executor | Do not clone as data; design a separate lifecycle |
| `Lock`, monitor object | Do not duplicate arbitrarily; synchronization of the copy must be clearly designed |
| Back-reference to the owner | Point to the **owner copy**, not the original owner |
| Two fields referencing one mutable node | Preserve or intentionally split the alias as required |
| Derived cache, transient field | Can be omitted and recomputed |

The table above is an analytical guide, not a mandatory rule for every domain.

## 4. Shallow Copy Creates a New Outer Object but Still Shares the Child

The program **`ShallowOrderDemo.java`**:

```java
final class MutableLine {
    String sku;
    int quantity;

    MutableLine(String sku, int quantity) {
        this.sku = sku;
        this.quantity = quantity;
    }
}

final class Order {
    final MutableLine line;

    Order(MutableLine line) {
        this.line = line;
    }
}

public class ShallowOrderDemo {
    public static void main(String[] args) {
        MutableLine line = new MutableLine("P01", 2);
        Order original = new Order(line);
        Order shallow = new Order(original.line);

        System.out.println(original == shallow);
        System.out.println(original.line == shallow.line);

        shallow.line.quantity = 9;
        System.out.println(original.line.quantity);
    }
}
```

Run:

```bash
javac -encoding UTF-8 ShallowOrderDemo.java
java ShallowOrderDemo
```

Stdout:

```text
false
true
9
```

There are two `Order` instances, but only **one MutableLine**. Mutating through the copy affects the original's data.

**Why doesn't `final MutableLine line` help?** `final` forbids reassigning the reference field, not `line.quantity = 9`.

## 5. Correct Deep Copy for a Simple Graph

If an `Order` **owns** `MutableLine` and the copy needs to be independent, copy the child:

```java
final class Order {
    final MutableLine line;

    Order(MutableLine line) {
        this.line = line;
    }

    Order deepCopy() {
        MutableLine source = line;
        return new Order(
                new MutableLine(source.sku, source.quantity));
    }
}
```

`MutableLine.sku` is an immutable `String`, so sharing the string reference is allowed. `quantity` is a primitive, copied directly. Creating a new MutableLine separates the mutable state of the two orders.

**The deep copy here has a two-level scope**: Order and MutableLine. Not "all Java objects in memory" are duplicated.

## 6. Runnable: Two Copies with an Independent Mutable Line

Save **`DeepOrderDemo.java`**:

```java
final class MutableLine {
    final String sku;
    int quantity;

    MutableLine(String sku, int quantity) {
        this.sku = sku;
        this.quantity = quantity;
    }

    MutableLine copy() {
        return new MutableLine(sku, quantity);
    }
}

final class Order {
    final MutableLine line;

    Order(MutableLine line) {
        this.line = line;
    }

    Order deepCopy() {
        return new Order(line.copy());
    }
}

public class DeepOrderDemo {
    public static void main(String[] args) {
        Order original = new Order(
                new MutableLine("P01", 2));
        Order copy = original.deepCopy();

        copy.line.quantity = 9;

        System.out.println(original == copy);
        System.out.println(original.line == copy.line);
        System.out.println(original.line.quantity);
        System.out.println(copy.line.quantity);
        System.out.println(
                original.line.sku == copy.line.sku);
    }
}
```

```bash
javac -encoding UTF-8 DeepOrderDemo.java
java DeepOrderDemo
```

Stdout:

```text
false
false
2
9
true
```

The two `sku` values can be the same String reference because the `sku` field value is copied directly; this **does not break mutable state independence** because String cannot be mutated.

## 7. Deep Copy Differs from Deep Immutability

A deep copy can still be **mutable**:

```java
Order copied = original.deepCopy();
copied.line.quantity = 9;
```

What needs to be proven for a deep copy: a mutation in the copied line **does not affect** the original line and vice versa, within the contract.

Conversely, an immutable `record Point(int x, int y)` can be **shared directly** among multiple owners without needing to be duplicated, because there is no mutation within that value state.

| Question | Deep copy | Immutable |
| --- | --- | --- |
| Does it create an independent representation? | Yes, for the mutable parts that need separation | Does not necessarily create a new copy |
| Does the result have setters? | Can have | Must not alter the promised state |
| Can it share an immutable child? | Yes | Yes |
| Can it share a mutable child? | If the child belongs to the snapshot requiring independence: no | If the child affects the observable value: no |
| Purpose | Isolate the impact of mutation | Prevent state mutation |
| Does it need alias checking? | Very necessary | Very necessary |

Do not use the two terms interchangeably.

## 8. One-Dimensional Arrays: `clone`/`Arrays.copyOf`

A one-dimensional primitive array holds **primitive value** elements, so:

```java
int[] original = {1, 2, 3};
int[] copy = original.clone();
```

creates a new array and copies the 3 values.

There is also:

```java
int[] copy = java.util.Arrays.copyOf(
        original, original.length);
```

`Arrays.copyOf` allows choosing a different length, with padding/truncation behavior depending on each overload; if the goal is an "exact copy", keep the exact same length.

`System.arraycopy` also quickly copies a range of elements, but the caller must allocate the destination itself and control bounds/type.

### Runnable

Save **`PrimitiveArrayCopyDemo.java`**:

```java
import java.util.Arrays;

public class PrimitiveArrayCopyDemo {
    public static void main(String[] args) {
        int[] source = {4, 5, 6};
        int[] clone = source.clone();
        int[] copy = Arrays.copyOf(source, source.length);

        source[0] = 99;
        clone[1] = 88;

        System.out.println(Arrays.toString(source));
        System.out.println(Arrays.toString(clone));
        System.out.println(Arrays.toString(copy));
        System.out.println(source == copy);
    }
}
```

```bash
javac -encoding UTF-8 PrimitiveArrayCopyDemo.java
java PrimitiveArrayCopyDemo
```

Stdout:

```text
[99, 5, 6]
[4, 88, 6]
[4, 5, 6]
false
```

This is a deep copy **for the data belonging to this `int[]` array**, because there are no nested mutable references.

## 9. Reference Arrays: Copying the Outer Array Is Not Enough

```java
StringBuilder[] source = {
    new StringBuilder("A")
};
StringBuilder[] copy = source.clone();
```

`source != copy` but `source[0] == copy[0]`.

Similarly, `Employee[]`, `Date[]`, and `List<?>[]` contain **references**, so mutable elements are shared when only cloning the array.

To separate them:
- Allocate a new outer array.
- Copy each mutable element according to the model.
- Preserve `null` according to the contract.
- References to immutable elements can be kept unchanged.
- If an element appears multiple times and the alias structure must be preserved, use an identity map or a dedicated handling approach.

### Runnable

Save **`ReferenceArrayCopyDemo.java`**:

```java
import java.util.Arrays;

public class ReferenceArrayCopyDemo {
    public static void main(String[] args) {
        StringBuilder item = new StringBuilder("A");
        StringBuilder[] original = {item};
        StringBuilder[] shallow = original.clone();
        StringBuilder[] deep = {
                new StringBuilder(original[0].toString())
        };

        item.append("!");

        System.out.println(Arrays.toString(original));
        System.out.println(Arrays.toString(shallow));
        System.out.println(Arrays.toString(deep));
        System.out.println(shallow[0] == original[0]);
        System.out.println(deep[0] == original[0]);
    }
}
```

```bash
javac -encoding UTF-8 ReferenceArrayCopyDemo.java
java ReferenceArrayCopyDemo
```

Stdout:

```text
[A!]
[A!]
[A]
true
false
```

## 10. Two-Dimensional Arrays: Copying Row by Row

`int[][]` is an **array of references to `int[]`**, so `source.clone()` only copies the outer array.

```java
int[][] source = {{1, 2}, {3, 4}};
int[][] shallow = source.clone();
source[0][0] = 9;
```

`shallow[0][0]` also becomes 9.

For a two-dimensional primitive array, a deep copy within this scope is:

```java
static int[][] deepCopy(int[][] source) {
    int[][] result = new int[source.length][];
    for (int i = 0; i < source.length; i++) {
        result[i] = source[i] == null
                ? null
                : source[i].clone();
    }
    return result;
}
```

The method preserves:
- The number of rows.
- The individual length of each row, including a *jagged array*.
- `null` rows if the contract allows.
- Primitive values.

**There is a subtlety regarding identity:** if `source[0] == source[1]` (two positions point to the same row), the code above will create **two different row copies**. For a typical matrix value, that may be appropriate; if alias topology needs to be preserved, memoization must be used even for arrays.

## 11. Runnable: Matrix Copy with Ragged Rows

Save **`MatrixDeepCopyDemo.java`**:

```java
import java.util.Arrays;

public class MatrixDeepCopyDemo {
    static int[][] deepCopy(int[][] source) {
        int[][] result = new int[source.length][];
        for (int i = 0; i < source.length; i++) {
            result[i] = source[i] == null
                    ? null
                    : source[i].clone();
        }
        return result;
    }

    public static void main(String[] args) {
        int[][] original = {
                {1, 2},
                {3},
                null
        };

        int[][] copy = deepCopy(original);
        original[0][0] = 9;
        copy[1][0] = 8;

        System.out.println(Arrays.deepToString(original));
        System.out.println(Arrays.deepToString(copy));
        System.out.println(original[0] == copy[0]);
    }
}
```

```bash
javac -encoding UTF-8 MatrixDeepCopyDemo.java
java MatrixDeepCopyDemo
```

Stdout:

```text
[[9, 2], [3], null]
[[1, 2], [8], null]
false
```

This is an exact example for the scope of primitive arrays; it is not a polymorphic deep-cloning algorithm for all objects.

## 12. `new ArrayList<>(source)` Is a Shallow Copy

A collection constructor:

```java
List<Employee> copy = new ArrayList<>(source);
```

creates a new list but keeps the **same Employee references**.

Consequences:
- `copy.add(newEmployee)` does not increase the size of `source`.
- `copy.get(0).setName(...)` can still modify the Employee that `source.get(0)` references.
- Copying the list structure does not create independence for mutable elements.

If `Employee` is immutable, sharing elements is safe against mutation. If `Employee` is a domain entity with shared identity, **sharing may be intentional**, not necessarily a bug.

### Copying Elements Using a Copy Factory

```java
List<EmployeeSnapshot> result = source.stream()
        .map(EmployeeSnapshot::from)
        .toList();
```

`EmployeeSnapshot.from` must be defined to copy the exact state fields needed for the snapshot. `Stream.toList()` in Java 17 returns an unmodifiable list; it does not automatically determine the deep contents of each snapshot.

## 13. Runnable: Outer-Layer List Copy and Copying Each Value

Save **`ListElementCopyDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class MutableItem {
    final String code;
    int quantity;

    MutableItem(String code, int quantity) {
        this.code = code;
        this.quantity = quantity;
    }

    MutableItem copy() {
        return new MutableItem(code, quantity);
    }

    @Override
    public String toString() {
        return code + ":" + quantity;
    }
}

public class ListElementCopyDemo {
    public static void main(String[] args) {
        MutableItem item = new MutableItem("A", 2);
        List<MutableItem> original = new ArrayList<>();
        original.add(item);

        List<MutableItem> shallow =
                new ArrayList<>(original);

        List<MutableItem> deep = original.stream()
                .map(MutableItem::copy)
                .toList();

        item.quantity = 5;

        System.out.println("original = " + original);
        System.out.println("shallow = " + shallow);
        System.out.println("deep = " + deep);
        System.out.println(original.get(0) == deep.get(0));
    }
}
```

```bash
javac -encoding UTF-8 ListElementCopyDemo.java
java ListElementCopyDemo
```

Stdout:

```text
original = [A:5]
shallow = [A:5]
deep = [A:2]
false
```

`deep` has a list structure that does not allow ordinary mutators through the `Stream.toList` API, but the `MutableItem` inside is still mutable if someone holds another reference to that copied item itself. **Deep copy and immutability are two separate things.**

## 14. `List.copyOf` Only Seals the List Structure

`List.copyOf(source)` creates an **unmodifiable list** containing a snapshot of the elements from a typical mutable source, but **does not deep-copy each element**.

```java
StringBuilder b = new StringBuilder("A");
List<StringBuilder> source = new ArrayList<>();
source.add(b);

List<StringBuilder> snapshot = List.copyOf(source);
b.append("!");
```

Now `snapshot.get(0).toString()` is `"A!"`. Calling `snapshot.add(...)` cannot succeed, but it does not prevent mutation on the builder.

Also keep in mind:
- `List.copyOf` does not accept null elements; it can throw `NullPointerException`.
- When the input is already a suitable unmodifiable implementation, it may return that same instance.
- An "outer-layer snapshot" has a different meaning from a snapshot of **the entire object graph**.

**The question to consider is whether the elements are immutable or need to be copied into value snapshots.**

## 15. Collection Wrapper View Differs from a Detached Snapshot

`Collections.unmodifiableList(backing)` creates a **view**: modifying the backing list can cause the view to change.

`List.copyOf(backing)` returns an **unmodifiable snapshot** of the list elements for a typical mutable backing list, not reflecting subsequent structural changes to the backing list.

`new ArrayList<>(backing)` creates a **mutable shallow copy**.

`backing.stream().map(Item::copy).toList()` creates a list of **element copies** according to `Item.copy` semantics; in Java 17, the outer list is unmodifiable.

A decision table:

| Need | Typical Solution | Trade-off |
| --- | --- | --- |
| Caller must not mutate through the view while the owner still manages the live list | `unmodifiableList(backing)` | Not a detached snapshot |
| Capture the structural history of immutable elements | `List.copyOf(backing)` | Shallow elements |
| A list copy where elements can be added/removed independently | `new ArrayList<>(backing)` | Mutable children are still shared |
| A list copy with mutable elements isolated independently | Copy outer and copy each child | Must design the copy scope |
| Immutable value graph | Immutable elements + snapshot | May not need to create child instances |
| Preserve graph aliases/cycles | Memoized object graph copy | More complex, requires identity mapping |

Do not use the method name "copy" as proof that the right scope was copied.

## 16. Map: Distinguishing Keys, Values, and Nested Mutable State

A `Map<String, List<Line>>` has multiple layers:
1. Map structure.
2. String keys.
3. List values.
4. Line elements.
5. Fields inside Line.

If you require a **snapshot of a draft order** that is unaffected by modifications to Lines/Lists from the caller:
- Copy Map entries to a new Map.
- You can **keep String keys** because they are immutable.
- Copy each List structure.
- Copy the mutable Line objects.
- Continue deeper if Line has a mutable child belonging to the snapshot.
- Control iteration order if output depends on ordering.

`new HashMap<>(source)` only copies the Map layer; `Map.copyOf(source)` seals the outer structure but does not copy deep values.

### Be Careful with Mutable Keys

If a key is a mutable object whose `equals/hashCode` depends on a field that can change, a map copy sharing key references is prone to lookup failures when the key is mutated. You should use immutable keys (ID/value objects), or copy keys according to the value contract and define how to handle duplicates/equality properly.

## 17. Runnable: Copying a Map and Nested Lists/Items

Save **`MapDeepCopyDemo.java`**:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

final class Line {
    final String sku;
    int quantity;

    Line(String sku, int quantity) {
        this.sku = sku;
        this.quantity = quantity;
    }

    Line copy() {
        return new Line(sku, quantity);
    }

    @Override
    public String toString() {
        return sku + ":" + quantity;
    }
}

public class MapDeepCopyDemo {
    static Map<String, List<Line>> copyDeep(
            Map<String, List<Line>> source) {

        Map<String, List<Line>> result =
                new LinkedHashMap<>();

        for (var entry : source.entrySet()) {
            List<Line> copiedLines = new ArrayList<>();
            for (Line line : entry.getValue()) {
                copiedLines.add(line.copy());
            }

            result.put(entry.getKey(), copiedLines);
        }

        return result;
    }

    public static void main(String[] args) {
        Line item = new Line("A", 1);

        Map<String, List<Line>> source =
                new LinkedHashMap<>();
        source.put("cart", new ArrayList<>(List.of(item)));

        Map<String, List<Line>> copy =
                copyDeep(source);

        item.quantity = 9;
        source.get("cart").add(new Line("B", 2));

        System.out.println("source = " + source);
        System.out.println("copy = " + copy);
        System.out.println(
                source.get("cart") == copy.get("cart"));
    }
}
```

```bash
javac -encoding UTF-8 MapDeepCopyDemo.java
java MapDeepCopyDemo
```

Stdout:

```text
source = {cart=[A:9, B:2]}
copy = {cart=[A:1]}
false
```

`LinkedHashMap` is used to preserve insertion order in the example. The `String` key is safely shared; `List` and `Line` are the mutable nodes that are copied.

## 18. Copy According to **Ownership Boundary**

A domain object does not necessarily own everything it references.

For example, `OrderService` has:
- `Repository`;
- `Clock`;
- `PaymentClient`;
- `InventoryCatalog`;
- An `OrderDraft` variable being processed.

If the requirement is to "create another order draft for the user to try editing", we usually copy **the OrderDraft data**, and **do not clone** Repository, Clock, PaymentClient, or Catalog.

### Field-by-Field Analysis

| Field | Belongs to Order Snapshot? | Choice |
| --- | --- | --- |
| `orderId` | Depends on semantics | Can assign a new ID if creating a new aggregate, or keep the ID if snapshotting the same aggregate |
| `line.quantity` | Yes | Copy mutable value |
| `line.sku` | Yes | Share immutable String |
| `customerId` | Yes | Share/copy immutable ID |
| `customerEntity` | Depends on boundary | Keep ID/shared reference or create a customer snapshot |
| `inventoryService` | No | Re-inject/share, do not deep-copy |
| `paymentGateway` | No | Do not copy resource/connection |
| `status` | Yes | Copy enum value |
| `auditLog` | Depends on requirements | Can snapshot entries or reference an external log |

**"Deep copy" should not mean "cloning the entire business universe".**

## 19. Entity Identity Differs from Value Copy

For a **value object**, copying data can be the primary intent: `Address(city,street)`, `Money(amount,currency)`, or `Coordinate(x,y)`.

For an **entity**, identity has meaning independent of its fields:
- Two `Customer` entities with the same name/email are not necessarily the same customer.
- Copying an `Order` with the same ID can mean a snapshot of **the same logical entity** at a different point in time.
- Copying an `Order` with a new ID can mean **duplicating as a new order**, with different rules (resetting status, timestamps, totals).
- Copying a JPA-managed entity with `new` does not automatically turn the new object into a managed entity in the persistence context.

Therefore, you need to **name operations semantically**:
- `snapshot()`: captures data for observation/storage.
- `duplicateForEditing()`: creates a working copy.
- `copyWithNewId()`: creates a new aggregate with a new identity.
- `toDto()` or `toValueSnapshot()`: converts an entity into a data representation.

A `deepCopy()` method cannot explain these identity decisions without contract documentation.

## 20. Runnable: Snapshot Preserves the ID, Duplicate Assigns a New ID

Save **`IdentityCopyPolicyDemo.java`**:

```java
record OrderSnapshot(String id, String sku, int quantity) {
}

final class OrderDraft {
    private final String id;
    private final String sku;
    private int quantity;

    OrderDraft(String id, String sku, int quantity) {
        this.id = id;
        this.sku = sku;
        this.quantity = quantity;
    }

    OrderSnapshot snapshot() {
        return new OrderSnapshot(id, sku, quantity);
    }

    OrderDraft duplicateAs(String newId) {
        return new OrderDraft(newId, sku, quantity);
    }

    void changeQuantity(int value) {
        quantity = value;
    }
}

public class IdentityCopyPolicyDemo {
    public static void main(String[] args) {
        OrderDraft original =
                new OrderDraft("ORD-1", "SKU-A", 2);

        OrderSnapshot snapshot = original.snapshot();
        OrderDraft duplicate =
                original.duplicateAs("ORD-2");

        original.changeQuantity(9);

        System.out.println(snapshot);
        System.out.println(duplicate.snapshot());
        System.out.println(original.snapshot());
    }
}
```

```bash
javac -encoding UTF-8 IdentityCopyPolicyDemo.java
java IdentityCopyPolicyDemo
```

Stdout:

```text
OrderSnapshot[id=ORD-1, sku=SKU-A, quantity=2]
OrderSnapshot[id=ORD-2, sku=SKU-A, quantity=2]
OrderSnapshot[id=ORD-1, sku=SKU-A, quantity=9]
```

The snapshot record preserves identity **by ID value**, whereas duplication intentionally assigns a different ID. Each operation has a clearer meaning than an ambiguous clone call.

## 21. Preserving Shared Aliases When Copying a Graph

This is the subtlest issue in deep copying.

Suppose in the original graph:

```text
root.left  ──► Child X
root.right ──► Child X
```

Two fields point to **the same child instance**:

```java
root.left == root.right  // true
```

If you copy with simple recursion:

```java
copy.left = root.left.copy();
copy.right = root.right.copy();
```

the copy may become:

```text
copy.left  ──► Child X1
copy.right ──► Child X2
```

and `copy.left == copy.right` is false.

**Is that wrong?** It depends on the contract:
- If the two fields are intentionally required to always be the same logical part (identity-sharing), it is **wrong**.
- If only two independent values are needed and aliasing does not matter, it may be acceptable.
- If the copy aims to create a **graph isomorphic with respect to references**, preserving the alias topology is mandatory.

A typical graph deep-copy algorithm requires a **memo map original object identity → copied object**.

## 22. `IdentityHashMap` and Remembering Already-Copied Nodes

`java.util.IdentityHashMap` compares keys by **reference identity** (`==`), instead of relying solely on custom `equals`.

Why does this matter? Two distinct mutable nodes can be `equals` to each other yet still be two objects that need to be copied separately.

A `HashMap<Node,Node>` for memoization could mistakenly merge them if `Node.equals` defines equality by value. `IdentityHashMap` is appropriate when the task is to preserve **object graph identities**.

Procedure:

1. If the node is null, return null.
2. If the node is already in the memo map, return **the same copied node** that was created.
3. If not present, **allocate the copy node first**.
4. Put the `original → copy` mapping into the memo.
5. Recursively copy children/edges; when encountering a previously seen node, use the memo.
6. Return the copy node.

**The order "put into the memo before recursing deeper" is crucial** for handling cycles.

## 23. Cyclic Graph: Reference Cycle A → B → A

If the graph has:

```text
A.next ──► B
B.next ──► A
```

the naive copy function:

```java
Node deepCopy(Node n) {
    Node result = new Node(n.name);
    result.next = deepCopy(n.next);
    return result;
}
```

has no stopping point for the cycle; it keeps copying A, B, A, B...

You must memoize immediately after allocating the copy of each node. When encountering A again, look up the memo and use `copyA` instead of allocating A2.

### What About Immutable Nodes with final next Fields?

Building a cyclic graph using **only final fields** can be difficult because you need to create objects pointing to each other before both complete construction. You can:
- Use a mutable build phase and then freeze it into another representation/structure;
- Convert the graph to immutable adjacency IDs;
- Use a builder graph separate from the data snapshot;
- Define the snapshot of edges using IDs instead of Java references.

**You should not force a "generic" deep-copy algorithm to bypass a type's initialization/invariants.**

## 24. Java 17 Program: Copying a Graph with a Shared Alias and Cycle

Save **`GraphDeepCopyDemo.java`**:

```java
import java.util.IdentityHashMap;
import java.util.Map;

final class Node {
    final String label;
    Node first;
    Node second;

    Node(String label) {
        this.label = label;
    }

    static Node copyGraph(Node root) {
        return copyGraph(root, new IdentityHashMap<>());
    }

    private static Node copyGraph(
            Node original,
            Map<Node, Node> visited) {

        if (original == null) {
            return null;
        }

        Node known = visited.get(original);
        if (known != null) {
            return known;
        }

        Node copy = new Node(original.label);
        visited.put(original, copy);

        copy.first = copyGraph(original.first, visited);
        copy.second = copyGraph(original.second, visited);

        return copy;
    }
}

public class GraphDeepCopyDemo {
    public static void main(String[] args) {
        Node root = new Node("root");
        Node shared = new Node("shared");

        root.first = shared;
        root.second = shared;
        shared.first = root;

        Node copy = Node.copyGraph(root);

        System.out.println(root == copy);
        System.out.println(root.first == copy.first);
        System.out.println(copy.first == copy.second);
        System.out.println(copy.first.first == copy);
        System.out.println(copy.label);
        System.out.println(copy.first.label);
    }
}
```

```bash
javac -encoding UTF-8 GraphDeepCopyDemo.java
java GraphDeepCopyDemo
```

**Stdout:**

```text
false
false
true
true
root
shared
```

Analysis:
- The outer root has been copied and no longer shares identity with the original.
- The shared child has been copied and is no longer the original shared node.
- **Both edges in the copy point to the same shared-node copy**, so the alias relation is preserved.
- The back-reference from the child copy points to the **root copy**, not the original root.
- The immutable `String label` values can be safely shared.

**Demo scope:** Graph nodes have two references and a String label. It does not copy arbitrary Java fields via reflection; this is an explicit domain-specific algorithm.

## 25. Cases Where Copying Loses an Alias but Is Not Necessarily Wrong

If the original has:

```text
Pair(left = mutable Money M, right = mutable Money M)
```

and the business requirement is "create two independent monetary amounts to edit separately", then copying M into two objects **may actually be what is desired**.

Conversely, if Pair represents "debit/credit referencing the same source value entity", breaking the alias may violate a domain invariant.

Therefore, you must answer one question before writing a memo algorithm:

> **Does the contract require copying the values or copying the topology/identity of the graph?**

- **Value copy**: can flatten and duplicate the values.
- **Graph-preserving copy**: needs to preserve identity relationships.
- **Snapshot DTO**: can convert edges to IDs instead of references.
- **Aggregate duplicate**: can change the root identity and only deep-copy owned children.

The word "deep" does not resolve these business decisions.

## 26. Nulls, Polymorphism, and Field Subclasses

If a field is declared:

```java
Animal pet;
```

but the runtime object is a `Dog`, creating:

```java
new Animal(/* base fields */)
```

when copying `pet` can **lose Dog-specific state** and behavior. Java does not automatically clone the runtime subtype when we use the base constructor.

Examples of requirements:
- Preserve the runtime subtype if the snapshot must remain a `Dog`;
- Or convert into an immutable DTO with a discriminator/type field;
- Or copy only the state belonging to the base contract if the business requirement genuinely only needs the base part.

### Design Options

1. **Polymorphic copy method** in a hierarchy with a clear contract.
2. **Visitor/factory** with sealed types if the set of subclasses is closed.
3. **Snapshot DTO** with the necessary fields from each subtype.
4. **Serialization** if the model genuinely has a serializer with an appropriate schema, though you must know the caveats.

**Do not treat a cast as a copy**:

```java
Animal pet = new Dog();
// Dog dog = (Dog) pet; // Only changes the visible type, does not clone.
```

## 27. Runnable: Copy Intentionally Preserving the Subtype

Save **`PolymorphicCopyDemo.java`**:

```java
sealed interface Pet permits Dog, Cat {
    Pet copy();
    String describe();
}

final class Dog implements Pet {
    private int tricks;

    Dog(int tricks) {
        this.tricks = tricks;
    }

    void learn() {
        tricks++;
    }

    @Override
    public Pet copy() {
        return new Dog(tricks);
    }

    @Override
    public String describe() {
        return "Dog tricks=" + tricks;
    }
}

final class Cat implements Pet {
    private int naps;

    Cat(int naps) {
        this.naps = naps;
    }

    @Override
    public Pet copy() {
        return new Cat(naps);
    }

    @Override
    public String describe() {
        return "Cat naps=" + naps;
    }
}

public class PolymorphicCopyDemo {
    public static void main(String[] args) {
        Pet original = new Dog(2);
        Pet copied = original.copy();

        ((Dog) original).learn();

        System.out.println(original.describe());
        System.out.println(copied.describe());
        System.out.println(original == copied);
        System.out.println(copied instanceof Dog);
    }
}
```

```bash
javac -encoding UTF-8 PolymorphicCopyDemo.java
java PolymorphicCopyDemo
```

Stdout:

```text
Dog tricks=3
Dog tricks=2
false
true
```

Here the copy is a **value copy of a single Pet object**; because the fields are only primitives, there are no nested mutable children. For a complex graph with cycles, each implementation needs the same memo/context mechanism to preserve topology.

## 28. Copy Constructor: Readable, but Must Copy the Mutable Parts Properly

A copy constructor:

```java
final class Profile {
    private final String name;
    private final int[] scores;

    Profile(Profile other) {
        name = other.name;
        scores = other.scores.clone();
    }
}
```

clearly:
- Shares `String name` safely.
- Copies the primitive array independently.

**There is no special `copy constructor` syntax in Java** as a built-in clone operator. It is a programmer-written constructor that takes an object of the same type as input.

### Limitations to Consider

- If the class is not `final` and has subclasses, calling the base copy constructor may not copy state in the subtype.
- If nested fields are mutable, you must copy deeper.
- If the object has an ID/resource, you need to define how to handle it.
- If fields have invariants, the constructor needs to validate or use a helper that preserves the invariant.
- If the source is being mutated by another thread, an unsynchronized copy constructor does not guarantee a consistent snapshot.

## 29. Static Factory `copyOf` and API Names That Communicate Intent

A pattern:

```java
final class Profile {
    static Profile copyOf(Profile source) {
        return new Profile(source);
    }
}
```

A factory allows you to:
- Validate source/null;
- Choose to return an existing immutable object if sharing is safe and fits the contract;
- Choose a different representation;
- Have clear names: `deepCopyOf`, `snapshotOf`, `duplicateAs`;
- Hide constructors if needed.

**However,** the name `copyOf` **does not guarantee allocation**: some APIs such as `List.copyOf` may return the input if it is already an appropriate unmodifiable implementation. When designing your own API, you must document whether it guarantees a **new identity** or only guarantees **value/immutability**.

If the caller requires `copy != source`, state that explicitly in the contract.

## 30. `Object.clone()`: The Underlying Mechanism, Shallow by Default

`Object` has the method `protected Object clone() throws CloneNotSupportedException`. It is not public in Object. Validly calling clone depends on the class, access, and the `Cloneable` marker interface along with the applicable rules.

`Object.clone()` performs **field-wise** copying of fields, so reference fields point to **the same child objects** by default (shallow copy), unless custom logic fixes it.

### Marker Interface `Cloneable`

`Cloneable` does not declare a public `clone` method itself; it marks the capability so that `Object.clone` does not reject it under the API's normal conditions.

If you want to expose clone:
- The class can override `clone` as public;
- It can call `super.clone()`;
- It must re-copy mutable components;
- It must handle the exception/return type;
- It must consider subclassing.

### Why Are Copy Constructors/Factories Often Easier to Use?

`clone` has many corner cases with inheritance, protected access, invariants, final fields, and shallow nested references. For an object graph with identity/cycles, custom logic must be designed whether using clone or not.

**Simply having `implements Cloneable` does not mean "deep copy".**

## 31. Runnable: Shallow `clone()` and Manual Deep Copy

Save **`CloneDepthDemo.java`**:

```java
import java.util.Arrays;

final class Scores implements Cloneable {
    private int[] values;

    Scores(int[] values) {
        this.values = values;
    }

    @Override
    public Scores clone() {
        try {
            return (Scores) super.clone();
        } catch (CloneNotSupportedException error) {
            throw new AssertionError(error);
        }
    }

    Scores deepCopy() {
        return new Scores(values.clone());
    }

    void set(int index, int value) {
        values[index] = value;
    }

    @Override
    public String toString() {
        return Arrays.toString(values);
    }
}

public class CloneDepthDemo {
    public static void main(String[] args) {
        Scores original = new Scores(new int[] {1, 2});
        Scores shallow = original.clone();
        Scores deep = original.deepCopy();

        shallow.set(0, 99);
        deep.set(1, 88);

        System.out.println("original = " + original);
        System.out.println("shallow = " + shallow);
        System.out.println("deep = " + deep);
    }
}
```

```bash
javac -encoding UTF-8 CloneDepthDemo.java
java CloneDepthDemo
```

Stdout:

```text
original = [99, 2]
shallow = [99, 2]
deep = [1, 88]
```

**Intentional warning:** the `Scores(int[])` constructor keeps a direct input alias, so Scores itself **is not immutable** and does not protect data from external sources. The goal of the example is to clarify that `super.clone()` is shallow; a production API needs to define ownership.

## 32. Record: Copies Data, but Nested References Still Need a Policy

A record:

```java
record Report(String title, List<StringBuilder> lines) {
}
```

newly created via:

```java
Report copy = new Report(
        original.title(), original.lines());
```

holds **the exact same list**. Copying the record container does not deep-copy.

If you want a text snapshot:
- Convert each `StringBuilder` into a `String`;
- Store them as a `List<String>`;
- The copy record does not necessarily have the same type as the source if the snapshot's meaning differs.

Example:

```java
record ReportSnapshot(
        String title, List<String> lines) {

    ReportSnapshot {
        lines = List.copyOf(lines);
    }
}
```

Do not confuse an implicitly final record with deep immutability: components can contain mutable referents. Copying a record solely via its canonical constructor is shallow with respect to those references.

## 33. Runnable: Mutable Source → Immutable Snapshot Record

Save **`RecordSnapshotDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class MutableReport {
    String title;
    List<StringBuilder> lines = new ArrayList<>();

    MutableReport(String title) {
        this.title = title;
    }
}

record ReportSnapshot(
        String title, List<String> lines) {

    ReportSnapshot {
        lines = List.copyOf(lines);
    }

    static ReportSnapshot from(MutableReport source) {
        List<String> copiedText = source.lines.stream()
                .map(StringBuilder::toString)
                .toList();

        return new ReportSnapshot(source.title, copiedText);
    }
}

public class RecordSnapshotDemo {
    public static void main(String[] args) {
        MutableReport report = new MutableReport("Q1");
        StringBuilder line = new StringBuilder("Revenue");

        report.lines.add(line);
        ReportSnapshot snapshot =
                ReportSnapshot.from(report);

        line.append(" updated");
        report.lines.add(new StringBuilder("Profit"));

        System.out.println(report.lines);
        System.out.println(snapshot);
    }
}
```

```bash
javac -encoding UTF-8 RecordSnapshotDemo.java
java RecordSnapshotDemo
```

Stdout:

```text
[Revenue updated, Profit]
ReportSnapshot[title=Q1, lines=[Revenue]]
```

Immutable `String` elements and an unmodifiable list create a representation that is not mutated by subsequent changes to the source, within the model's scope. If `source` is modified from another thread **during the copy**, snapshot synchronization is still required.

## 34. Defensive Copying: Protecting the Owner Boundary

A class that advertises "holding a data snapshot" usually needs to:
- **Copy upon receiving input** so the caller no longer holds an alias to internal state.
- **Copy when returning output** if the internal representation is still mutable.
- **Not let other mutators expose internal references**.
- **Not retain exposed mutable children** in a field that the caller knows about and can modify.

Example with `int[]`:

```java
final class IntSnapshot {
    private final int[] values;

    IntSnapshot(int[] input) {
        values = input.clone();
    }

    int[] values() {
        return values.clone();
    }
}
```

However, if the getter only needs `size()`/`get(i)`, you may not return an array at all.

### Deep Copy in Constructor vs. Snapshot Method

If the source is a large mutable aggregate, copying in the constructor of a snapshot value object creates a clear boundary:
- The aggregate executes business logic;
- The snapshot holds observed fields;
- Does not create a duplicate aggregate with two IDs of the same meaning;
- Can serialize the snapshot without touching the live aggregate.

**Not every getter has to deep-copy the entire graph**. Designing an immutable read model is usually better than returning a pile of mutable internals and copying them every time.

## 35. Runnable: Protecting Both Input and Output Arrays

Save **`DefensiveCopyDemo.java`**:

```java
import java.util.Arrays;

final class IntSnapshot {
    private final int[] values;

    IntSnapshot(int[] input) {
        values = input.clone();
    }

    int[] values() {
        return values.clone();
    }

    int at(int index) {
        return values[index];
    }
}

public class DefensiveCopyDemo {
    public static void main(String[] args) {
        int[] input = {10, 20};
        IntSnapshot snapshot = new IntSnapshot(input);

        input[0] = 99;
        int[] fromGetter = snapshot.values();
        fromGetter[1] = 88;

        System.out.println(snapshot.at(0));
        System.out.println(snapshot.at(1));
        System.out.println(Arrays.toString(fromGetter));
        System.out.println(Arrays.toString(input));
    }
}
```

```bash
javac -encoding UTF-8 DefensiveCopyDemo.java
java DefensiveCopyDemo
```

Stdout:

```text
10
20
[10, 88]
[99, 20]
```

The two copy operations serve **two different directions of aliasing**; omitting either direction leaves an avenue to mutate internal state.

## 36. Deep Copying Under Concurrency: The Snapshot Must Be Consistent

A method:

```java
List<Item> snapshot = source.stream()
        .map(Item::copy)
        .toList();
```

may be correct in a single-threaded state, but is not automatically an **atomic snapshot** when other threads are mutating `source` or the Items inside.

If the source is modified concurrently without synchronization, you may:
- Encounter `ConcurrentModificationException` with some iterators (not a guarantee to detect every race);
- Copy a "half-before/half-after" dataset;
- Read inconsistent fields;
- Produce a snapshot that violates business invariants.

### Consistent Design

1. All writers and copiers use **the same monitor/lock**, copying inside a short and reasonable critical section.
2. Convert the entire state into an **immutable aggregate snapshot** and publish a reference atomically.
3. Use transaction/versioning/snapshot isolation at the data layer if the source is a database.
4. If using a concurrent collection, read its iteration/snapshot contract carefully (some iterators are weakly consistent, not atomic snapshots).

**Deep copy and concurrency snapshot are two separate requirements.** Properly copying mutable nodes while reading inconsistently can still yield incorrect data.

## 37. Runnable: Capturing Two Fields Under the Same Monitor

Save **`ConsistentSnapshotDemo.java`**:

```java
record BalanceSnapshot(int debit, int credit) {
}

final class AccountPair {
    private final Object lock = new Object();
    private int debit;
    private int credit;

    void setBoth(int debit, int credit) {
        synchronized (lock) {
            this.debit = debit;
            this.credit = credit;
        }
    }

    BalanceSnapshot snapshot() {
        synchronized (lock) {
            return new BalanceSnapshot(debit, credit);
        }
    }
}

public class ConsistentSnapshotDemo {
    public static void main(String[] args)
            throws InterruptedException {

        AccountPair pair = new AccountPair();
        pair.setBoth(10, 10);

        Thread writer = new Thread(
                () -> pair.setBoth(20, 20));
        writer.start();
        writer.join();

        BalanceSnapshot snapshot = pair.snapshot();
        System.out.println(snapshot);
    }
}
```

```bash
javac -encoding UTF-8 ConsistentSnapshotDemo.java
java ConsistentSnapshotDemo
```

Stdout:

```text
BalanceSnapshot[debit=20, credit=20]
```

The example intentionally calls `join` so that stdout is deterministic; in a real concurrent application, `snapshot()` holding the monitor ensures reading **a consistent pair of fields**, rather than reading one field before an update and the other field after the update.

## 38. Do Not Copy System Resources Like Ordinary Values

The following types have their own identity/lifecycle:

- `java.net.Socket`;
- `java.io.InputStream` / `OutputStream`;
- `java.sql.Connection`;
- `Thread`, executor;
- File descriptor/OS handle;
- Monitor lock/`ReentrantLock`;
- Transaction context and managed persistence sessions.

Attempting to deep-copy them can:
- Lack a clone API;
- Create a new resource without the same semantics;
- Violate ownership and lifecycle;
- Cause multiple copies to think they own the same handle;
- Lose synchronization correctness.

When an object needs to clone **data** and also holds a resource:
- **Copy data fields** according to scope.
- **Omit or re-provide the dependency** at the composition root.
- **Do not copy the resource directly** unless the resource API provides an operation with a clear contract (for example, creating a new stream to the same file) and the requirement genuinely intends that.
- Document who is responsible for `close()` on the original/copy.

**Do not use reflection to copy every field blindly**, especially for JDK/resource internals.

## 39. Shared Services Are Not Child State of the Snapshot

`ReportGenerator` has fields:

```java
private final Formatter formatter;
private final Repository repository;
private final List<Section> sections;
```

A requirement to "copy a report draft to edit sections" usually only needs to:
- Copy `sections` along with the mutable elements belonging to the draft;
- Potentially keep the `formatter` and `repository` references for both generators if these are shared dependencies with a shared-use contract;
- Or exclude services from the snapshot DTO.

**A good API expression:**

```java
ReportSnapshot snapshot = generator.snapshot();
ReportGenerator copy = new ReportGenerator(
        formatter, repository, snapshot.copySections());
```

The snippet above **illustrates the idea**; it is not a standalone runnable because `ReportSnapshot`/`copySections` must be defined according to the domain.

What matters is dependency injection and a clear copy policy, not drawing an object graph and copying every edge.

## 40. Do Not Arbitrarily Deep-Copy JPA Entities Outside a Transaction

With ORM/JPA entities:
- Proxies and lazy associations may trigger queries when traversing the graph.
- Bidirectional associations easily create cycles.
- Entity identity and the persistence context have their own meaning.
- ORM collection wrappers have specific semantics.
- Copying IDs verbatim can confuse an "entity snapshot" with a "new entity to persist".

A generally safe approach:
- Identify the aggregate boundary.
- Create a DTO/value snapshot from the required data under an appropriate transaction.
- Do not use reflection to clone every field.
- For duplication, create a new entity following business rules, assigning appropriate new IDs/state.
- If an owned child collection must be cloned, clearly distinguish owned vs. shared relationships.

**Deep copying for a domain does not equate to deep-cloning the entire database.**

## 41. Is a Serialization Round-Trip a Deep Copy?

You may have heard the trick:

```text
object -> JSON -> new object
```

or Java serialization/another binary codec to "deep clone". However, a round-trip **is not a general solution you can use without thinking**.

Risks:
- Only serialized fields appear in the copy;
- Object graph cycles/shared identity may not be preserved if the format/config does not support them;
- Polymorphic subtype info may be lost if the schema does not represent it;
- Transient fields, derived caches, and resource references are handled differently;
- Constructors/validation and default values may produce different semantics;
- Serializing/deserializing untrusted data carries security risks;
- CPU/allocations and compatibility/schema versioning can be costly.

**Use serialization when the snapshot format/DTO is already a genuine contract**, rather than treating it by default as a general `Object.deepCopy`.

### If Graph-Preserving Serialization Is Needed

You must explicitly verify whether the codec supports:
- Object identity/reference tracking;
- Cycle handling;
- Immutable/record value construction;
- Subclass type discriminators;
- Nulls, generics, maps, and collections;
- Security/allowlists;
- Version migration.

Do not infer from "the output JSON looks the same" that "the copy preserved graph identity".

## 42. HashMap Keys and Copy Policy

A `Map<Key,Value>` can use mutable or immutable keys.

If copying a map while sharing mutable keys, a thread/caller modifying fields participating in `equals/hashCode` can cause map lookup to behave unexpectedly.

If you **deep-copy keys**, other issues arise:
- Will the copy preserve equality semantics?
- Will there be key collisions after normalization/copying?
- Are there two original keys with different identities that are equal by value, meaning the new map cannot contain both under the same equality contract?
- If a key is an entity identity, does copying it break links with other objects?

Therefore:
- Use immutable key types whenever possible (String, immutable IDs/records).
- Copy values/nested state as needed.
- Do not copy keys blindly.
- When keys have custom equality, explicitly test the mapping after copying.

**The correctness of a copied map is not just "having the same size".**

## 43. Choosing Copy Depth via the API Contract

A `copy()` method lacking a description can create misunderstandings:
- The caller thinks it is deep; the implementation does shallow.
- The caller thinks it is a snapshot; the implementation keeps a live view.
- The caller thinks it is a new identity; the implementation shares an immutable instance.
- The caller thinks it includes the resource; the implementation omits the resource.
- The caller thinks it copies the subtype as well; the implementation only copies base fields.

You should state clearly:
- Which fields belong to the snapshot;
- Which nested types are copied or shared;
- Whether alias/cycle topology is preserved;
- Whether a new object is guaranteed for the root;
- Whether dependencies/resources are shared;
- Whether the copy is mutable or immutable;
- Whether it is a thread-safe snapshot;
- Whether it gets a new ID or keeps the ID.

JavaDoc example:

```java
/**
 * Creates an independent working copy of the order lines.
 * String SKU and ProductId are shared because they are immutable.
 * InventoryService does not belong to the snapshot.
 * The root receives a new identity according to the business rule.
 * The new line objects can be modified without affecting the original.
 */
OrderDraft duplicateForEditing(String newOrderId) {
    // implementation...
    return null;
}
```

This snippet **illustrates a contract**, not an implementation to use. Returning null only indicates that the body has not been shown; in production source code, you must write the real implementation and not keep this placeholder.

## 44. Correctness: Equality, Independence, and Alias Preservation

A deep copy test should not only have:

```java
assertNotSame(original, copy);
```

That only confirms a new root; it says nothing about the children.

Tests must answer multiple dimensions:
1. **Initial value equivalence:** values within the copy scope are equal when the copy is created.
2. **Mutable independence:** modifying the original does not change the copy; modifying the copy does not change the original.
3. **Root identity:** a new root if the contract requires it.
4. **Nested identity:** a mutable child copy is distinct from its corresponding original child.
5. **Shared alias topology:** if the original has aliases to a child, does the copy preserve the relation as intended?
6. **Cycles:** a back-reference points to the copy root, not the original root.
7. **Null/empty input:** copies missing/empty branches properly as well.
8. **Runtime subtype:** are implementation types preserved if the contract requires it?
9. **External references:** are services/resources handled according to policy?
10. **Concurrency:** is the snapshot state consistent if the source is modified concurrently?

### Not Every Field Is Required to Have a Different Identity

For an immutable `String` or `Instant`, `original.name == copy.name` can be true while the deep copy is completely valid under the mutation-independence contract.

## 45. Runnable: Testing Deep Copy with Stable Output

Save **`DeepCopyContractDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class EditableLine {
    final String code;
    int count;

    EditableLine(String code, int count) {
        this.code = code;
        this.count = count;
    }

    EditableLine copy() {
        return new EditableLine(code, count);
    }
}

final class Draft {
    private final List<EditableLine> lines;

    Draft(List<EditableLine> lines) {
        this.lines = lines;
    }

    Draft deepCopy() {
        List<EditableLine> result = new ArrayList<>();
        for (EditableLine line : lines) {
            result.add(line.copy());
        }
        return new Draft(result);
    }

    EditableLine line(int index) {
        return lines.get(index);
    }

    int size() {
        return lines.size();
    }
}

public class DeepCopyContractDemo {
    public static void main(String[] args) {
        EditableLine line = new EditableLine("P", 2);
        Draft original = new Draft(
                new ArrayList<>(List.of(line)));
        Draft copy = original.deepCopy();

        boolean rootDistinct = original != copy;
        boolean childDistinct =
                original.line(0) != copy.line(0);

        original.line(0).count = 9;
        copy.line(0).count = 5;

        System.out.println("root distinct = " + rootDistinct);
        System.out.println("child distinct = " + childDistinct);
        System.out.println("original count = "
                + original.line(0).count);
        System.out.println("copy count = "
                + copy.line(0).count);
        System.out.println("same size = "
                + (original.size() == copy.size()));
    }
}
```

```bash
javac -encoding UTF-8 DeepCopyContractDemo.java
java DeepCopyContractDemo
```

Stdout:

```text
root distinct = true
child distinct = true
original count = 9
copy count = 5
same size = true
```

The example shows that both the root and the mutable element are separated. It does not yet test cycles or shared-alias preservation; those cases belong to a separate graph contract.

## 46. Cost: Complexity and Memory

Suppose we copy an acyclic tree of `n` mutable nodes:
- Time is typically **O(n)** if each node is visited/copied once and field-copy operations have constant cost.
- New memory for nodes is typically **O(n)**, plus the recursion stack proportional to depth.
- If each node contains a large array/string that must be copied, total time/memory depends on **the total amount of data actually copied**.

For a graph with cycles/shared aliases using a memo:
- If each node/edge is traversed once, the baseline complexity is **O(V + E)** for the graph structure, plus the cost of copying the payload.
- The memo map requires memory proportional to the number of original nodes copied.
- Recursion depth can cause `StackOverflowError` on very deep graphs; iterative traversal/a work queue is an option for large data or uncontrolled depth.

### Do Not Deep-Copy Every Time a Getter Is Called

If an object has 100,000 elements, deep-copying on every `getLines()` call can create many allocations and be slow. Instead:
- Publish an immutable snapshot once at the boundary;
- Provide narrow `getCount()`/`getAt(i)` queries;
- Use persistent data structures when versions are needed frequently;
- Define an explicit `snapshot()` so the caller knows the cost.

**Performance is an API design issue**, not just loop optimization.

## 47. Structural Sharing: Independence Does Not Always Require Cloning Every Node

Immutable persistent structures can create a new version and **share immutable branches** with the old version:

```text
Version A ──► Branch1 ──► SharedImmutableTail
Version B ──► Branch2 ──► SharedImmutableTail
```

Because SharedImmutableTail cannot be mutated, sharing does not affect the observational independence of the two versions.

Conversely, **sharing a mutable tail** allows version A to change when B mutates, breaking the snapshot contract.

Good mindset:
- **Copy** the mutable values that need independence.
- **Share** the safe immutable nodes.
- **Preserve identity** for meaningful shared references.
- **Exclude/reinject** non-data services/resources.
- **Change representation** if the original graph is too complex or unsuitable for a snapshot.

This is why "deep copy" must be defined by **scope and contract**, not by a fixed number of levels.

## 48. Technical Limitations: Reflection Does Not Solve Everything

A helper attempting to automatically iterate fields and recursively copy via reflection can run into:

- Private fields/strong encapsulation and JPMS module accessibility;
- Constructors and invariants not being established properly;
- Final fields that cannot be handled arbitrarily like mutable references;
- Not knowing which fields are owned, shared, derived, or resources;
- Cycles, aliases, and class loaders;
- Collections with special internal representations;
- Security risks when touching secrets;
- Types that are not cloneable or require a lifecycle;
- Dynamic proxies and bytecode-enhanced ORM entities.

Therefore, **"generic recursive deepCopy(Object)" is not a safe default solution for Java**.

Using an explicit copy policy/factory or an intentional serialization schema makes reviewing correctness easier.

## 49. Design Questions Before Choosing a Technique

Answer specifically:

1. **What is the purpose of the copy?** Undo, snapshot, prototype, concurrent read model, duplicate entity, message payload, or test fixture?
2. **Does the root need a new identity?**
3. **Which state is owned data?**
4. **Which components are merely external dependencies/references?**
5. **Which values are immutable and shareable?**
6. **Which mutable children must be independent?**
7. **Are there shared alias relationships?**
8. **Are there cycles/back-references?**
9. **Are there polymorphic subclasses?**
10. **Are there nulls, jagged arrays, or sparse collections?**
11. **Are there unmanaged resources?**
12. **Can the source be modified concurrently?**
13. **Is it necessary to preserve object graph topology or only content values?**
14. **Will the copy remain mutable, or must the snapshot be immutable?**
15. **What are the data size and copy frequency?**

If you do not have the answers yet, immediately choosing `clone()` or serialize-copy usually only hides important decisions.

## 50. Decision Matrix for Some Practical Requirements

| Requirement | What Must Be Copied | What Can Be Shared / Not Copied | Technical Approach |
| --- | --- | --- | --- |
| Copy `int[]` before saving | Array values | No nested mutable refs | `clone`/`Arrays.copyOf` |
| Copy `int[][]` | Outer + inner arrays | Primitive values | Copy row by row |
| Snapshot a list of names | Outer list snapshot | `String` elements | `List.copyOf` |
| Copy a list of `MutableLine` | Outer + each mutable Line | Immutable SKU | Copy constructor/factory per Line |
| Snapshot a report from builders | Text content | Do not keep StringBuilder aliases | Convert `StringBuilder→String` |
| Duplicate an Order with a new ID | Owned lines + domain values; ID per rule | Product catalog, services | Explicit domain factory |
| Clone a cyclic graph preserving aliases | Nodes/edges belonging to the graph | Immutable payload | `IdentityHashMap` memo |
| Copy an API DTO | DTO fields per schema | Services/resources omitted | Explicit mapping |
| Copy an ORM entity | Only owned aggregate per business logic | Shared entities by ID | DTO/new aggregate factory |
| Copy `Socket/Connection` | Do not copy as value | Reinject/construct according to contract | Lifecycle design |
| Snapshot mutable concurrent state | Consistent state under lock/transaction | Immutable subgraphs | Lock/snapshot isolation |
| Versioned immutable tree | Changed branches | Immutable unchanged nodes | Structural sharing |

## 51. Exercise 1 — Does Reference Assignment Copy?

```java
List<String> a = new ArrayList<>();
List<String> b = a;
```

**Answer:** No. `a == b` is true. Mutating the List through one reference affects both because it is the same object.

## 52. Exercise 2 — Does Copying `List<String>` Require Deep Copying Strings?

**Answer:** No, `String` is immutable. If you want an unmodifiable detached list snapshot, `List.copyOf(source)` is usually sufficient for a mutable `List<String>` source (with an appropriate null policy). There is no need to duplicate each String.

## 53. Exercise 3 — Is Copying `List<StringBuilder>` with `new ArrayList<>(source)` Deep?

**Answer:** No. The outer list is new, but the StringBuilder references are shared. To be independent regarding the builders' contents, copy each builder or convert to String snapshots.

## 54. Exercise 4 — Is Copying a Matrix with `matrix.clone()` Deep?

**Answer:** Not for `int[][]`. It only copies the outer references; the rows are still shared. You need to clone each row, or design a graph-aware copy if shared-row alias topology matters.

## 55. Exercise 5 — Two Fields Pointing to the Same Node

```java
root.left == root.right // true
```

After a deep copy, must this always stay true?

**Answer:** **Depends on the contract.** If the copy must preserve graph identity/alias topology, then yes, a memo map is needed; if copying values into two independent children as required, then not necessarily.

## 56. Exercise 6 — Cyclic Graph

A.next = B and B.next = A. What is the problem with naive recursive deep copy?

**Answer:** It does not terminate due to the cycle, typically causing `StackOverflowError`. You need to memoize original→copy **as soon as the copy node is created** before recursing on children.

## 57. Exercise 7 — `HashMap` or `IdentityHashMap` for the Visited Map?

Nodes override `equals` so that two nodes with different identities but the same label are considered equal.

**Answer:** If the goal is to preserve the **reference identity** of the graph, use `IdentityHashMap` or an identity-aware strategy. `HashMap` may mistakenly merge nodes that are equal yet have different identities.

## 58. Exercise 8 — Clone a Shared `Connection`?

An OrderService holds a `Connection` managed by a DI container. When copying an Order draft, do you need to deep-copy the Connection?

**Answer:** No. Connection is a resource/dependency outside the scope of the order data snapshot. Ownership/lifecycle of the connection must be managed separately.

## 59. Exercise 9 — Copying an Entity ID

Create a new order from an old order, but it must have a different ID.

**Answer:** You should use a factory `duplicateAs(newId)` or equivalent workflow, rather than copying the exact ID and pretending the two entities are different. Owned lines are copied according to business rules; shared catalog/products are handled according to identity semantics.

## 60. Exercise 10 — Is Clone Deep?

A class `implements Cloneable` and its public `clone()` only does `return (X)super.clone();`, and the class has an `ArrayList` field.

**Answer:** It is shallow by default for the ArrayList reference field. Custom copying is needed for mutable state within scope; simply implementing the marker interface is not enough.

## 61. Exercise 11 — `List.copyOf` with MutableItem

```java
List<MutableItem> x = List.copyOf(source);
```

**Answer:** The List structure is unmodifiable; MutableItem elements still hold the same references. This is not yet a deep copy of mutable values.

## 62. Exercise 12 — Record Containing an Array

```java
record Packet(byte[] payload) {}
```

**Answer:** The default canonical constructor/accessor can retain/expose the same mutable array reference. If a payload snapshot is needed, clone upon receiving and clone upon returning; if byte-based value equality is needed, handle `equals/hashCode` appropriately or switch to another immutable representation.

## 63. Exercise 13 — Does Deep Copy Mean Immutable?

**Answer:** No. The copy can still modify its own fields/collections. Deep copy guarantees independence within scope; immutability guarantees state does not change through the corresponding API/aliases.

## 64. Exercise 14 — Must a Shared Immutable Child Be Newly Copied?

Two objects both point to `String "Java"` or an immutable Address record.

**Answer:** Creating a new child is not mandatory. Because the child is immutable, sharing does not propagate mutations from one instance to the other.

## 65. Exercise 15 — Source Modified During Copy

One thread mutates an `ArrayList<Line>`, while another thread calls stream to deep-copy Line without synchronization.

**Answer:** There is no guarantee of a consistent snapshot and there may be a race. You need to use a lock/transaction/immutable publication or a collection with an appropriate snapshot contract.

## 66. Exercise 16 — Does JSON Serialization Preserve Object Aliases?

A graph has root.left and root.right pointing to the same child. After serializing to JSON and parsing back, is it guaranteed that both fields point to the same child instance?

**Answer:** No. Most value-based representations do not automatically represent Java object identity. Only when a special schema/codec supports reference tracking and is configured appropriately can alias topology be preserved.

## 67. Exercise 17 — A Mutable Cache Inside a Snapshot

The snapshot has a derived cache, initially null and recomputable.

**Answer:** You can **omit the cache when copying** if the cache is not business state, and let the copy recompute it when needed. If the cache is shared and mutable, thread-safety and observable semantics must be considered. Do not mechanically copy every field.

## 68. Exercise 18 — Deep Copying a Graph with final References and a Cycle

You want to clone a cyclic graph, but `next` fields are final and constructors do not allow creating a node without next.

**Answer:** You cannot directly apply the "allocate an empty node then attach edges" algorithm if the API does not permit it. You need to change the representation to immutable IDs, a builder/freeze phase, or a factory supporting cycles; do not use reflection to break invariants.

## 69. Exercise 19 — Copying a Map with Mutable Keys

Map keys have `equals/hashCode` based on a mutable field. The copy shares keys.

**Answer:** Keys can change and cause abnormal lookups. It is best to use immutable key types or an explicit copy policy with proper value semantics.

## 70. Exercise 20 — Reducing Deep Copy Cost

A getter calls `deepCopy()` on a list of 100,000 nodes every time to display the count.

**Answer:** Design a safe read API like `size()`/`count()`, or an explicit immutable snapshot when genuinely needed. Deep-copying the entire graph for a count is an unnecessary cost.

## 71. Exercise 21 — Does "Deep Copy the Entire Object Graph" Make Sense?

A DTO references `CustomerEntity`, `DataSource`, `Logger`, `Cache`, and `List<Line>`.

**Answer:** It cannot be decided solely from the depth of the graph. You must set the scope: Lines belong to the snapshot; Customer can keep an ID; DataSource/Logger/Cache are dependencies and should not be deep-copied automatically. The result depends on ownership and use case.

## 72. Deep Copy Review Checklist

1. Have you explicitly stated **the purpose of the copy**: snapshot, working copy, or duplicate entity?
2. Have you determined whether **the root identity** changes?
3. Which fields belong to the **data payload**, and which fields are dependencies?
4. Are there any mutable descendants to which the caller still retains an alias?
5. Is every mutable part within scope copied independently?
6. Can immutable values such as `String`/`Instant`/immutable records be shared?
7. Are external resources/locks/connections mistakenly being copied?
8. If it is a List/Map, have both **the outer structure** and the mutable elements/values needing copying been copied?
9. If `int[][]`, have inner arrays and possible null rows been handled?
10. Are there shared aliases across multiple edges?
11. Does the contract need to preserve **alias topology**?
12. Are there cycles requiring an original→copy memo map?
13. Does the memo map use **reference identity** when appropriate?
14. Is the copy node allocated before recursing to avoid cycles?
15. Could the copy encounter subclasses whose fields are not covered by the base constructor?
16. Is `clone()` only shallow-copying references?
17. Is there a record with arrays/collections that are not sufficiently copied?
18. Are entity IDs and JPA lifecycle handled according to business rules?
19. Can the data be mutated **during the copy**?
20. At which monitor/transaction boundary is a consistent snapshot needed?
21. Is the copy immutable by API or still mutable?
22. Do the snapshot's getters expose mutable internals if immutability is required?
23. Has a null/empty policy been defined?
24. Have you tested modifying the original after copying and modifying the copy afterward?
25. Have you tested aliases/cycles/subtype-specific fields?
26. Have you tested value equality/hashCode if the copy will be used as a map key?
27. Is there a depth/size limit or recursion stack protection for large graphs?
28. Is the copy cost appropriate for the frequency/size of the data?
29. Would an immutable DTO/structural sharing simplify things?
30. Do the API name and documentation clearly state *what is actually copied*?

## Key Takeaways

**Deep copy in Java does not mean "copy everything the object can point to".** It means creating an independent representation for **the mutable data defined within the copy scope**.

- Reference assignment does not copy an object; creating an outer object with `new` may still be only a **shallow copy**.
- One-dimensional primitive arrays are usually copied sufficiently with `clone`; reference arrays, multi-dimensional arrays, collections, and nested classes require inspecting mutable parts at deeper levels.
- `List.copyOf`/`Map.copyOf` create unmodifiable outer structures; they **do not automatically deep-copy elements**.
- Sharing immutable leaves is safe; blindly copying resources/shared dependencies is usually wrong.
- Shared aliases and cycles need a clear policy. If graph topology must be preserved, use **identity memoization** such as `IdentityHashMap` and memoize the node before copying edges.
- Copy constructors, `clone`, `copyOf` factories, DTO mapping, and serialization **do not define copy depth on their own**. It must be designed per domain.
- Distinguish **a snapshot with the same identity** from **a duplicate entity with a new identity**, and **deep copy** from **deep immutability**.
- Under concurrency, a snapshot must be read from a consistent state; properly copying a graph does not automatically make concurrent reads atomic.
- Verify with **value equivalence, mutation independence, alias/cycle preservation, resource policy, and performance**.

A correct copy is not necessarily the one with the most new objects, but rather **the copy that preserves the exact values and relationships that need to be kept, while properly isolating the changes that need to be independent**.
