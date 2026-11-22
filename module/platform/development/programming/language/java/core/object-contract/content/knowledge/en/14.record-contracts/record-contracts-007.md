# Defensive Copy Immutability via Accessors and Canonical Constructors of `record`

## 1. The Problem: A `record` Has `final` Fields, Yet Components Can Still Mutate

`record` (Java 16+, finalized in Java 17) is a data type designed to describe **a tuple of values defined by its components (record components)**. When declaring:

```java
record Report(int id, int[] scores) {}
```

the compiler provides core members such as `private final` fields for each component, a canonical constructor, `id()`/`scores()` accessors, along with `equals`, `hashCode`, and `toString`. However, `final` **only fixes the reference inside the field**; it does not make the object the field points to immutable.

Therefore:

- An object constructed via `new Report(1, array)` by default **holds the exact input array reference**.
- Calling `report.scores()` by default **returns that internal array reference**.
- External code can modify the array via the input variable or via the accessor, causing the observable state of `report` to change after creation.

This is **shallow immutability**: the component reference is fixed, yet its contents can change. To build a record with **stable values**, both access paths must be protected:

1. **Incoming path**: in the canonical constructor, store a **defensive copy** or an immutable representation instead of the mutable data passed in from outside.
2. **Outgoing path**: the accessor must not directly return a mutable internal object; return an appropriate copy or a safe immutable view.

This lesson focuses on these two points, how to write them properly in a Java record's canonical constructor, and the impact on the `equals`/`hashCode` contract.

## 2. How Do a Record's Canonical Constructor and Accessors Work?

Given:

```java
record OrderLine(String sku, int[] quantities) {}
```

the components are represented by private, `final` fields. The canonical constructor receives parameters matching the exact order and types of the components, and the public `sku()`, `quantities()` accessors have corresponding return types. In the basic declaration, initializing `quantities` is equivalent to storing the passed reference; the accessor returns that reference. There is no built-in mechanism to copy array elements automatically.

**The canonical constructor has two main forms** to distinguish:

### Explicit Canonical Constructor

When full control over every assignment is needed, write the complete parameter list:

```java
import java.util.Arrays;
import java.util.Objects;

record Scores(int[] values) {
    public Scores(int[] values) {
        Objects.requireNonNull(values, "values");
        this.values = Arrays.copyOf(values, values.length);
    }

    public int[] values() {
        return values.clone();
    }
}
```

This snippet is a valid record (placed in `Scores.java` with the imports); it demonstrates two-way copying. In an explicit canonical constructor, all component fields must be initialized according to definite assignment rules, without omitting any component. Here `this.values` receives **a new array**, not the array owned by the caller.

### Compact Canonical Constructor

Java allows omitting the parameter list; component parameters are declared implicitly and **the component fields are automatically assigned from the parameter values when the compact constructor body completes normally**:

```java
import java.util.Objects;

record Scores(int[] values) {
    public Scores {
        Objects.requireNonNull(values, "values");
        values = values.clone(); // Reassign the compact constructor parameter.
    }

    public int[] values() {
        return values.clone();
    }
}
```

Both examples enforce the same protection policy: **copy on input** and **copy on output**. In the compact constructor, `values = values.clone()` updates the **local parameter**; the implicit assignment at the end of the constructor writes the new parameter into the component field. Do not write `this.values = ...` inside the compact constructor body: assigning component fields directly there is invalid; the implicit assignment mechanism handles it.

Note that these are **two alternative implementations of the same `Scores` record**. When trying to compile, choose one snippet as the contents of `Scores.java`; do not place two record definitions with the same name in one file.

## 3. Two Paths Where Mutable Data "Leaks"

Suppose a record has no protective measures yet:

```java
record UnsafeScores(int[] values) {}
```

**Leak from the constructor (incoming path):**

```java
int[] source = {10, 20};
UnsafeScores report = new UnsafeScores(source);
source[0] = 99;

// report.values()[0] is now 99.
```

The caller holds `source` and the record also uses that exact array. Modifying the input after creating the record alters the state represented by the record.

**Leak from the accessor (outgoing path):**

```java
UnsafeScores report = new UnsafeScores(new int[] {10, 20});
int[] leaked = report.values();
leaked[1] = 88;

// report.values()[1] is now 88.
```

Each snippet above is an **illustrative example**, not a standalone program. Even though the component is `private final`, the data remains mutable through references.

| What the Record Does | Who Can Later Mutate Internal Data? | Result |
| --- | --- | --- |
| No copy in constructor, no accessor protection | Both callers holding input and callers receiving from accessor | Leaks in both directions. |
| Copy in constructor but return directly from accessor | Callers obtaining the array from the accessor | Still not immutable. |
| Keep input reference directly but copy in accessor | Callers still holding the input array | Still not immutable. |
| Copy in constructor and copy in accessor | Callers cannot directly mutate internal array elements via these two paths | Sufficient for **1D arrays containing primitive values**, provided the class does not expose mutable references through any other path. |

**Copying in only one direction is not enough.** Check all points receiving and exposing data, including any additional custom methods written inside the record.

## 4. Choosing a Copy Method by Component Type

There is no single copy function that is right for every kind of data.

| Component | Common Solution | Limitations to Understand |
| --- | --- | --- |
| `int[]`, `byte[]`, `char[]` | `clone()` or `Arrays.copyOf` on input and output | 1D arrays containing primitive values; a single copy suffices to isolate elements. |
| `String[]` | Copy array on input/output; `String` is immutable | New outer array, while strings are safely shared because `String` itself is immutable. |
| `Object[]` containing mutable objects | Copy array **and** copy/freeze elements per policy | `clone()` only copies the outer array; elements still share the same references. |
| `int[][]` or multi-dimensional arrays | Create outer array and copy **each sub-array** | `matrix.clone()` is only shallow; must loop over rows or handle deeper nesting. |
| `List<String>` | `List.copyOf(input)` in constructor; accessor can return this list | Immutable element types (`String`) and structurally unmodifiable list. |
| `List<MutableItem>` | Create an immutable copy **of each item**, then `List.copyOf` | `List.copyOf` does not automatically deep-copy elements. |
| `Map<K, V>`, `Set<E>` | `Map.copyOf`, `Set.copyOf` where appropriate | These are unmodifiable structural copies at the collection level, not guaranteeing keys/values are deeply immutable. |
| `String`, `Integer`, `LocalDate`, or truly immutable value objects | Can be kept directly | No copying needed when the component object is already immutable and satisfies desired semantics. |

When using `List.copyOf`, `Set.copyOf`, `Map.copyOf`, understand the API's preconditions, including rejecting `null` elements (`Map.copyOf` also rejects `null` keys/values). This rule can be an advantage for consistency, yet if the domain allows `null`, you must choose an appropriate representation or validation policy.

`List.copyOf` returns a **list that cannot be structurally modified through the list API**. Do not confuse it with `Collections.unmodifiableList(input)`: an unmodifiable **view** can still reflect modifications made through the original `input` itself. If a snapshot isolated from the source is needed, use an appropriate copy such as `List.copyOf(input)`.

## 5. Runnable Java 17+ Example: Constructor, Accessor, and `equals`

The following program illustrates four scenarios:

1. `UnsafeNumbers` holds and exposes the array directly, so it is mutated via both paths.
2. `ImmutableTags` creates a snapshot via `List.copyOf`. Because elements are immutable `String`s, the default accessor can safely return that list.
3. `NumberSnapshot` copies the array both on input and on output, and also **overrides `equals`/`hashCode` by contents** to match value-object semantics.
4. `ShallowBox` uses `List.copyOf` yet still holds mutable elements: mutating an element changes the observable state.

Save to `RecordDefensiveCopyDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.HashSet;

public class RecordDefensiveCopyDemo {
    record UnsafeNumbers(int[] numbers) {}

    record ImmutableTags(List<String> tags) {
        public ImmutableTags {
            Objects.requireNonNull(tags, "tags");
            tags = List.copyOf(tags);
        }
    }

    record NumberSnapshot(int[] numbers) {
        public NumberSnapshot {
            Objects.requireNonNull(numbers, "numbers");
            numbers = numbers.clone();
        }

        // Explicit accessor: returns a new array on each call.
        public int[] numbers() {
            return numbers.clone();
        }

        @Override
        public boolean equals(Object other) {
            return this == other
                    || (other instanceof NumberSnapshot that
                        && Arrays.equals(numbers, that.numbers));
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(numbers);
        }
    }

    static final class MutableCell {
        int value;

        MutableCell(int value) {
            this.value = value;
        }
    }

    record ShallowBox(List<MutableCell> cells) {
        public ShallowBox {
            cells = List.copyOf(cells);
        }
    }

    public static void main(String[] args) {
        int[] unsafeSource = {1, 2};
        UnsafeNumbers unsafe = new UnsafeNumbers(unsafeSource);
        unsafeSource[0] = 99;
        System.out.println("unsafe input leak: "
                + Arrays.toString(unsafe.numbers()));
        unsafe.numbers()[1] = 88;
        System.out.println("unsafe accessor leak: "
                + Arrays.toString(unsafe.numbers()));

        List<String> sourceTags =
                new ArrayList<>(List.of("java"));
        ImmutableTags tags = new ImmutableTags(sourceTags);
        sourceTags.add("spring");
        System.out.println("tags after source edit: " + tags.tags());
        try {
            tags.tags().add("kotlin");
        } catch (UnsupportedOperationException exception) {
            System.out.println("tags accessor: unmodifiable");
        }

        int[] source = {10, 20};
        NumberSnapshot safe = new NumberSnapshot(source);
        source[0] = 999;
        System.out.println("safe after input edit: "
                + Arrays.toString(safe.numbers()));

        int[] returned = safe.numbers();
        returned[1] = 777;
        System.out.println("safe after accessor edit: "
                + Arrays.toString(safe.numbers()));

        NumberSnapshot equivalent =
                new NumberSnapshot(new int[] {10, 20});
        System.out.println("snapshot equals: "
                + safe.equals(equivalent));
        System.out.println("snapshot hash equal: "
                + (safe.hashCode() == equivalent.hashCode()));

        Set<NumberSnapshot> set = new HashSet<>();
        set.add(safe);
        System.out.println("set contains equivalent: "
                + set.contains(equivalent));

        UnsafeNumbers raw1 = new UnsafeNumbers(new int[] {10, 20});
        UnsafeNumbers raw2 = new UnsafeNumbers(new int[] {10, 20});
        System.out.println("default array component equals: "
                + raw1.equals(raw2));

        MutableCell cell = new MutableCell(7);
        ShallowBox box =
                new ShallowBox(new ArrayList<>(List.of(cell)));
        cell.value = 8;
        System.out.println("shallow element edit: "
                + box.cells().get(0).value);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 RecordDefensiveCopyDemo.java
java RecordDefensiveCopyDemo
```

Exact expected output:

```text
unsafe input leak: [99, 2]
unsafe accessor leak: [99, 88]
tags after source edit: [java]
tags accessor: unmodifiable
safe after input edit: [10, 20]
safe after accessor edit: [10, 20]
snapshot equals: true
snapshot hash equal: true
set contains equivalent: true
default array component equals: false
shallow element edit: 8
```

### Reading Output by Class

**`UnsafeNumbers`:** the default constructor stores `unsafeSource`; mutating `unsafeSource[0]` is reflected in the record. The default accessor returns the exact internal array, allowing further mutation of the second element. This is an example with no defensive copying.

**`ImmutableTags`:** the compact canonical constructor converts the list via `List.copyOf(tags)`, then Java assigns the new list (or an equivalent immutable representation) to the component field when the constructor finishes. Modifying `sourceTags` afterward does not affect `tags.tags()`. The default accessor returns a list that disallows adding/removing/replacing elements. Because `String` is immutable, there is no element-mutation loophole here.

**`NumberSnapshot`:** the constructor receives a copy of `int[]`; the accessor creates a new array each time. Modifying either the input array or the array obtained from the accessor does not affect internal state. Both `equals` and `hashCode` rely on element values, so two independent snapshots with identical contents are equal and look up accurately in `HashSet`.

**`UnsafeNumbers` under auto-generated `equals`:** two records with separate child arrays yet identical `{10,20}` are not equal. This is not a record-specific bug; `int[].equals` inherently checks identity. `record` generates `equals` based on components, and for array components, that comparison reflects array identity rather than individual elements.

**`ShallowBox`:** `List.copyOf` freezes **the list structure**, yet each element remains a `MutableCell`. Modifying `cell.value` causes the accessor to observe the value `8`. This demonstrates that **an unmodifiable collection does not imply deep immutability**.

## 6. Critical Trap: Defensive Copying and Auto-Generated `equals`/`hashCode` of Records

Regular records provide `equals` and `hashCode` from their components. For reference components, the equality rule uses the component's appropriate comparison semantics; for arrays, the default array methods are **identity-based**.

Consider the following record:

```java
import java.util.Objects;

record DefensiveButIdentity(int[] values) {
    public DefensiveButIdentity {
        Objects.requireNonNull(values, "values");
        values = values.clone();
    }

    public int[] values() {
        return values.clone();
    }

    // equals() and hashCode() are auto-generated by Java.
}
```

This record protects the internal array in both directions, yet two instances created from arrays with identical contents still **are not equal** under auto-generated `equals` because they hold two different component arrays. More seriously, a key design invariant of records is that a copy constructed by passing back the accessor results of every component should normally be equivalent to the original record under `equals` (copy invariant). In the array case, the accessor creates a new array causing the new record to use a different array reference; auto-generated `equals` does not treat those two records as equal.

Illustrative example:

```java
DefensiveButIdentity a =
        new DefensiveButIdentity(new int[] {1, 2});
DefensiveButIdentity b =
        new DefensiveButIdentity(a.values());

// a.equals(b) returns false under auto-generated equals().
```

**Therefore, if a record has an array component and is intended as a content-immutable value, defensive copying alone is not enough.** You must choose the right semantics:

- **Want equality by contents:** like `NumberSnapshot`, manually write `equals` using `Arrays.equals` and `hashCode` using `Arrays.hashCode`. For regular nested arrays, use the `Arrays.deepEquals`/`Arrays.deepHashCode` pair and protect the immutability of nested arrays.
- **Want to use auto-generated comparison:** choose a component type that itself has value-based equality semantics and can be immutable, such as an immutably copied `List<Integer>` or a suitably designed value object. Then the record can rely on auto-generated `equals`/`hashCode`.
- **Truly want to represent the identity of a specific array:** consider whether copying the array contradicts that identity policy; a value-object record may not be the most appropriate model for this need.

Do not "fix" this by comparing `Arrays.hashCode(values)` to infer that two arrays have identical contents. Hashes can collide. `equals` verifies element-by-element; `hashCode` only assists in directing lookup.

## 7. Using `List.copyOf` and Default Accessors for Collections

When a component is a collection **that is already immutable and whose elements are also immutable**, returning a collection copy on every accessor call is unnecessary. A record like the following is usually sufficient:

```java
import java.util.List;
import java.util.Objects;

record Permissions(List<String> names) {
    public Permissions {
        Objects.requireNonNull(names, "names");
        names = List.copyOf(names);
    }
}
```

After the constructor finishes, the `names` field holds an unmodifiable list unaffected by add/remove operations on the source list. `String` is immutable so contents stay stable too. The auto-generated `names()` accessor can return that exact list without opening a mutation loophole through the list API.

Why the distinction matters:

- `Collections.unmodifiableList(source)` creates a **view disallowing modification through the view**, yet external `source.add(...)` can still cause the contents observed through the view to change.
- `List.copyOf(source)` provides an unmodifiable list containing a snapshot of the elements at the time of copying (or may reuse an already immutable list), unaffected by subsequent add/remove operations on `source`.
- Neither **deep-copies** mutable element objects. For `List<MutableAddress>`, each address must be copied/converted into an immutable value object before using `List.copyOf`.
- `List.copyOf` does not guarantee preserving the **reference identity** of the list object; code should rely on value and the list contract.
- For records with an immutable list, auto-generated `equals`/`hashCode` rely on `List.equals`/`List.hashCode`, which compare element-by-element, provided the element type has valid semantics.

A useful design policy: **copy once in the constructor and return directly via the accessor when the object is genuinely immutable**; if the component is a mutable array, **copy on both input and output**.

## 8. Deep Copying: Multi-Dimensional Arrays and Mutable Elements

### 8.1. Two-Dimensional Arrays

`int[][]` is actually an array holding references to `int[]` arrays. Thus `input.clone()` only copies the outer array. To get an independent snapshot, you must copy **each row**. Example logic for an array with no `null` rows:

```java
private static int[][] copyMatrix(int[][] source) {
    Objects.requireNonNull(source, "source");
    int[][] copy = new int[source.length][];
    for (int row = 0; row < source.length; row++) {
        copy[row] = Objects.requireNonNull(
                source[row], "matrix row"
        ).clone();
    }
    return copy;
}
```

This is an **illustrative snippet to be placed inside a class importing `java.util.Objects`**, not a standalone program. If rules permit `null` rows, you must explicitly define how to handle them differently.

Inside a record receiving a matrix, you can call `matrix = copyMatrix(matrix);` in the compact canonical constructor and `return copyMatrix(matrix);` in the accessor. To also have content-based semantics, implement `equals` with `Arrays.deepEquals(matrix, other.matrix)` and `hashCode` with `Arrays.deepHashCode(matrix)`.

Note that `deepEquals`/`deepHashCode` are suitable for acyclic nested array structures; they are not general algorithms for comparing graphs with cyclic references. Those models require separate rules.

### 8.2. Lists Containing Mutable Elements

`List.copyOf` keeps the same references to each element. If a record contains `List<MutableAddress>` and other code still holds references to the address objects, mutating an address still alters the values observed from the record.

A clear approach is to **convert into immutable value objects** immediately on receipt:

```java
record AddressSnapshot(String city, String street) {}

record ShippingAddresses(List<AddressSnapshot> entries) {
    public ShippingAddresses {
        entries = List.copyOf(entries);
    }
}
```

This example is safe toward immutability if `AddressSnapshot` contains only immutable `String`s like the two components above, with no accessor override returning mutable content. If the initial input data is `MutableAddress`, map each item into `new AddressSnapshot(...)` before creating the record or in an appropriate constructor/factory method. Merely changing the generic declaration from `MutableAddress` to another type without performing conversion does not solve the problem.

### 8.3. Limits of "Deep Immutability"

Immutability must be evaluated across **the entire object graph exposed by the record**:

- If a record contains `List<List<String>>`, ensure each inner list also cannot be modified. `List.copyOf(outer)` only wraps the outside.
- If a record contains `Date`, `Calendar`, `StringBuilder`, `ByteBuffer`, or mutable objects, copy/convert according to their respective APIs and semantics.
- Copying large data on every accessor call incurs CPU/memory cost; sometimes it is more appropriate to store a dedicated immutable structure or provide a read API that does not expose mutable data.
- If a component is an object that cannot be safely copied or represents a resource handle, a record may not be the right representation for an immutable value.

There is no rule that "all records are automatically deep immutable". Records support concise data modeling; true immutability design remains the programmer's responsibility.

## 9. Validation and Normalization in the Compact Canonical Constructor

Besides copying, a compact constructor is ideal for checking invariants and normalizing components. Example:

```java
import java.util.List;
import java.util.Objects;

record Job(String name, List<String> labels) {
    public Job {
        Objects.requireNonNull(name, "name");
        Objects.requireNonNull(labels, "labels");

        name = name.strip();
        if (name.isEmpty()) {
            throw new IllegalArgumentException("Blank job name");
        }
        labels = List.copyOf(labels);
    }
}
```

At the end of the compact constructor body, Java assigns the processed parameters into the `final` fields. Hence `name` is stored in its `strip()`ped form and `labels` is stored as an immutable snapshot. If validation fails, the constructor throws an exception and no invalid record is created.

Some rules:

1. **Do not call `this` accessor methods to read unassigned components** during a compact constructor. While executing its body, component fields have not yet been initialized by the implicit assignment at the end of the constructor. Use **constructor parameters** for validation and normalization.
2. **Do not assign `this.component` directly in a compact constructor.** Use parameter reassignment such as `labels = List.copyOf(labels)`.
3. **Do not let `this` escape the constructor** before the record is fully initialized (e.g., registering a listener or storing it in a shared location).
4. **Do not return a mutable reference from a custom accessor** if the constructor protected the input data; doing so nullifies defensive copying.
5. **Do not artificially alter contents returned by an accessor** in a way that breaks record consistency or violates `equals` semantics.

The sequence matters: with a compact canonical constructor, *validate/normalize/copy on parameters* → *implicit assignment to component fields* → *record formed with normalized values*.

## 10. The Copy Invariant and the Value-Object Contract of Records

A property of records is that components describe **all stored state** relevant to the value. Therefore, "copying via accessors" is expected to preserve equality:

```java
// Illustration with record R having components c1(), c2().
// R copied = new R(original.c1(), original.c2());
// original.equals(copied) should hold by value design.
```

With genuinely immutable components and value-based `equals`, that property is naturally preserved. With mutable components, defensive copying may produce new references; if default `equals` uses element identity (like arrays), the record copy may not equal the original. Thus one of the following must be chosen:

- Design components as **immutable values**, such as an immutable list of immutable value objects, so auto-generated `equals` fits naturally.
- Manually define **content-based `equals` and `hashCode`** for array components protected by defensive copies, so a copy via accessors remains equivalent.
- Do not use a record as a value object if requirements genuinely depend on resource identity, objects with independent lifecycles, or unsuitable mutable structures.

For any content-based `equals` implementation, the hash must be based on **the exact same fields used in `equals`**. `HashSet`/`HashMap` structures require this pair to remain stable when the object serves as a key: if the hash function depends on internal data that still mutates after adding to the collection, lookup operations may fail to find the element again.

## 11. Cost, API Compatibility, and Design Decisions

Defensive copying increases safety, yet is not free. For an array of length `n`, `clone()` typically allocates a new array and copies `n` elements, costing proportional to array size. If every accessor call invokes `clone()`, frequent reads can allocate many arrays. Even so, returning a mutable array directly can open a path to unauthorized state mutation, which is very difficult to debug later.

Practical options:

- **Small and simple:** a record containing a 1D primitive array, cloning on input/output and using `Arrays.equals`/`hashCode` if the value is defined by contents.
- **Collections of immutable elements:** a record using `List.copyOf` once in the constructor; the default accessor returns the immutable list, avoiding allocations on every access.
- **Large data or frequent updates:** consider a class with controlled read/write APIs, persistent collections, versioned immutable snapshots, or separating mutable and snapshot models. A record is not necessarily a good model for objects needing continuous mutation.
- **Serialization or API transport requirements:** do not assume a serialization library constructs/reads records via the same constructor path under all configurations. Test the decoding path of the library in use to ensure validation and defensive copying execute.

In standard Java object serialization for records, the canonical constructor participates in reconstructing the record during deserialization; however, systems may use various frameworks with their own mechanisms. Do not leave validation/copying only inside a factory method that other object-construction paths bypass.

## 12. Common Mistakes and How to Fix Them

| Mistake | Why It Is Wrong | How to Fix |
| --- | --- | --- |
| Thinking `record` or `final` makes arrays automatically immutable | `final` fixes the reference, while elements remain mutable. | Copy mutable components on both incoming and outgoing paths. |
| Cloning only in the constructor | The default accessor still exposes the internal array. | Declare an accessor returning `clone()` or an appropriate copy. |
| Cloning only in the accessor | The caller still holds the input reference and can mutate the record from outside. | Copy in the canonical constructor before storing. |
| Writing `this.values = values.clone()` inside a compact constructor | Does not conform to component-field assignment rules of compact constructors. | Write `values = values.clone()`; Java assigns implicitly after the body. |
| Using `List.copyOf` for `List<MutableItem>` and calling it deeply immutable | The list prevents structural edits, yet items can still be mutated. | Copy/convert items into immutable value objects first. |
| Using `Collections.unmodifiableList(source)` as a snapshot | The view can reflect modifications through the `source` reference. | Use `List.copyOf` or create your own copy per policy. |
| Using `array.clone()` on nested arrays and thinking it deep-copied | Sub-arrays remain shared. | Copy each sub-array or recurse through the structure. |
| Cloning the array in constructor and accessor while keeping auto-generated `equals` | Two records with identical array contents may still be unequal due to array identity. | Use immutable values with content-based `equals` or override the `equals`/`hashCode` pair. |
| Overriding only `equals` with `Arrays.equals` | Auto-generated `hashCode` may compute differently, breaking the hash contract. | Always override matching `hashCode` with `Arrays.hashCode` (or the deep pair). |
| Returning a mutable copy while assuming client classes will mutate the record | Operations on the copy do not alter the record. | Provide a method returning a new snapshot, e.g., `withValues` returning a new record, if value updates are needed. |
| Forgetting to define a `null` policy | `clone()` on `null` throws NPE; `List.copyOf` rejects `null` elements. | Check `Objects.requireNonNull` or design clear default/optional values. |

## 13. Checklist for Testing Record Immutability

Create a record containing mutable components and test both directions:

1. **Input aliasing:** pass an array/list into the record, mutate the source data after creation, and confirm the accessor still yields the original snapshot.
2. **Output aliasing:** obtain the array from the accessor, mutate the copy, call the accessor again, and confirm the record did not change.
3. **Collection snapshot:** add/remove in the source list after creation and verify the record is unchanged; attempting to mutate the returned list must be blocked when policy requires unmodifiable.
4. **Mutable elements:** if the list contains mutable objects, try mutating the object itself; if the record's value is supposed to be immutable yet the result changes, the copy policy is incomplete.
5. **Nested arrays:** mutate an `int[]` row of the source matrix and of the accessor result; it must not affect the matrix inside the record snapshot.
6. **Value equality:** create two independent records with equivalent data; check `equals` returns the right result according to content policy.
7. **Hash agreement:** any pair of equal records must have equal `hashCode`; after all attempts to mutate source/output, the immutable record's hash remains unchanged.
8. **Copy invariant:** construct a new record from the accessors of the original record itself; the result must be equivalent under `equals` if the record is designed as a value object.
9. **Validation:** supply `null`, missing, or malformed data; verify the constructor rejects or normalizes per policy without creating invalid state.
10. **Collection behavior:** use the record as a `HashSet` element or `HashMap` key, then attempt to mutate any source data or returned copies. Lookup using an equivalent record must still succeed.

These are tests of the object's external behavior. They uncover two major classes of bugs: records that are not truly immutable, and immutable records whose `equals`/`hashCode` do not reflect the contents to be compared.

## 14. Key Takeaways

**Records do not automatically guarantee deep immutability.** With mutable components, block aliasing from **the canonical constructor** (copying on input) and from **the accessor** (copying on output or returning a safe immutable representation). Compact canonical constructors allow reassigning parameters, which Java then automatically assigns to component fields when the constructor completes. `List.copyOf` is useful for collections of immutable elements, whereas arrays and nested objects require examining inner components as well. With array components, defensive copying must also accompany appropriate `equals`/`hashCode` semantics; if content comparison is desired, do not rely on the array's default identity-based mechanism. Choosing copying and equality rules together helps records preserve stable values, remain safe across APIs, and stay reliable as hash keys.