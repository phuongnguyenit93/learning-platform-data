# A `final` Field Does Not Guarantee That Component Objects Are Immutable in Java

## 1. The problem: fixing a reference does not mean fixing state

In Java, `final` applies to the **declared variable or field**. For a reference-type field, `final` prevents reassigning that field after valid initialization; it **does not lock the state** of the referenced object.

Consider a short example:

```java
final StringBuilder text = new StringBuilder("Java");
text.append(" 17");          // Valid: modifies StringBuilder state.
// text = new StringBuilder(); // Compile error: cannot reassign final variable.
System.out.println(text);     // Java 17
```

This is an **illustrative snippet** placed inside a method; the comment about a compile error is not an executable statement. After the `append` call, the original `StringBuilder` object itself changed its contents, while the variable `text` still points to the old object.

We should distinguish three questions:
1. Can the variable/field be reassigned? — `final` controls this.
2. Can the state of the referenced object be modified? — depends on the object's API and design.
3. Can the state of **child objects** referenced from that object be modified? — depends on nesting structure, alias retention, and copying strategy.

This issue ties directly to the **Object Contract**: if an object uses data from mutable components to compute `equals()` or `hashCode()`, both operations can change over time. When the object is an element of a `HashSet` or a key of a `HashMap`, the consequence can be failed lookups or unexpected changes in duplicate relationships.

## 2. Levels of immutability to distinguish

| Concept | Meaning | What is not yet guaranteed |
|---|---|---|
| `final` reference variable | Cannot assign another reference to that variable itself | The pointed-to object may still be mutable |
| `private final` field | Cannot reassign the field after the object is validly constructed in normal Java | Properties of the referenced object may still change |
| `final` class | Cannot create subclasses of the class | Fields or child objects may still be mutable |
| Structurally unmodifiable collection | Cannot add/remove/replace elements through that collection | Mutable elements inside may still change |
| Shallow copy | Creates an independent outer structure, usually keeping element references | Shared element objects may change |
| Deep copy or snapshot | Copies mutable parts needing protection across the data graph | Must be designed per model; there is no universal Java command to freeze every object |
| Observable immutability (immutable state) | After creation, the object's meaningful state does not change via its API or external aliases | Must inspect getters, constructors, collections, nested elements, and other mechanisms |

Example:

```java
final List<String> names = new ArrayList<>();
names.add("An");             // Valid: ArrayList is mutable.
names.set(0, "Binh");        // Valid: replaces element.
// names = List.of("Chi");   // Compile error: reassigning a final variable.
```

Here, the `names` variable does not change its reference, yet the list contents can change. Similarly, `private final Date createdAt` can still be modified via `Date.setTime(...)` if code holds a reference to the `Date` or a getter returns that object directly.

Conversely, objects like `String`, `Instant`, and `LocalDate` are immutable types in normal usage: if a `final` field points directly to them and there is no other mutable state affecting semantics, the enclosing class is easier to keep immutable.

## 3. Two ways mutable state leaks out

### 3.1. Alias from constructor: the caller retains the original reference

Suppose a class looks like this:

```java
final class UnsafeTags {
    private final List<String> tags;

    UnsafeTags(List<String> tags) {
        this.tags = tags; // Keeps the same List object passed in by the caller.
    }
}
```

Creating an `ArrayList` outside and passing it into the constructor does not automatically create a copy. The caller retains an **alias**, meaning another reference to the same list. After the `UnsafeTags` object is created, the caller can still call `add`, `remove`, or `set`. Although the `tags` field is `final`, the referenced object's state has changed.

In real applications, this also happens with arrays, `Date`, `Calendar`, `StringBuilder`, `ByteBuffer`, objects containing collections, or a mutable POJO.

### 3.2. Alias from getter: the class itself returns its internal object

Even if the constructor copies the list, a getter like the following still breaks protection:

```java
List<String> tags() {
    return tags; // If tags is an internal ArrayList, the caller can mutate it.
}
```

If this is a mutable list, the caller can use `tags().clear()` or `tags().add(...)`. Therefore, ensuring immutability requires checking **both the path bringing data in and the path returning data out**.

Another flawed variation is creating a wrapper:

```java
this.tags = Collections.unmodifiableList(input);
```

The wrapper blocks edits **through the wrapper itself**, but if `input` is still an `ArrayList` held by the caller, the caller can modify `input` and the wrapper will reflect the change. This wrapper is a **view**, not an independent snapshot. You must combine copying with wrapping when you want to block both directions:

```java
this.tags = Collections.unmodifiableList(new ArrayList<>(input));
```

This is an illustrative snippet inside a constructor with the corresponding `input` variable and `tags` field. For a list of immutable types, `List.copyOf(input)` is usually more concise.

## 4. Standalone Java 17 example: observing the difference

Create a file **`FinalReferenceDemo.java`** with the following content. The example intentionally retains a mutable reference in `UnsafeTags`; `SafeTags` captures a snapshot with `List.copyOf`; `DeepSnapshot` copies each mutable element into an immutable record.

```java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public class FinalReferenceDemo {
    public static void main(String[] args) {
        List<String> callerTags = new ArrayList<>(List.of("java"));
        UnsafeTags unsafe = new UnsafeTags(callerTags);

        callerTags.add("hash");
        System.out.println("unsafe after caller edit: " + unsafe.tags());

        unsafe.tags().add("api");
        System.out.println("caller sees getter edit: " + callerTags);

        Set<UnsafeTags> unsafeSet = new HashSet<>();
        unsafeSet.add(unsafe);
        int before = unsafe.hashCode();
        callerTags.add("mutable");
        System.out.println("unsafe hash changed: "
                + (before != unsafe.hashCode()));

        List<String> source = new ArrayList<>(List.of("java"));
        SafeTags safe = new SafeTags(source);
        source.add("hash");
        System.out.println("safe after caller edit: " + safe.tags());

        boolean rejected = false;
        try {
            safe.tags().add("api");
        } catch (UnsupportedOperationException expected) {
            rejected = true;
        }
        System.out.println("safe getter rejects edit: " + rejected);

        Set<SafeTags> safeSet = new HashSet<>();
        safeSet.add(safe);
        int stableHash = safe.hashCode();
        source.clear();
        System.out.println("safe hash stable: "
                + (stableHash == safe.hashCode()));
        System.out.println("safe set contains: " + safeSet.contains(safe));
        System.out.println("same value equals: "
                + safe.equals(new SafeTags(List.of("java"))));

        MutablePart mutablePart = new MutablePart("HN");
        List<MutablePart> shallow = List.copyOf(List.of(mutablePart));
        mutablePart.setLabel("HCM");
        System.out.println("shallow element now: "
                + shallow.get(0).label());

        DeepSnapshot snapshot = new DeepSnapshot(List.of(mutablePart));
        mutablePart.setLabel("Da Nang");
        System.out.println("deep snapshot keeps: "
                + snapshot.parts().get(0).label());
    }

    // INTENTIONALLY UNSAFE: final only fixes the list reference.
    static final class UnsafeTags {
        private final List<String> tags;

        UnsafeTags(List<String> tags) {
            this.tags = Objects.requireNonNull(tags, "tags");
        }

        List<String> tags() {
            return tags;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof UnsafeTags that
                    && tags.equals(that.tags);
        }

        @Override
        public int hashCode() {
            return tags.hashCode();
        }
    }

    // Structural snapshot; safe here because String is immutable.
    static final class SafeTags {
        private final List<String> tags;

        SafeTags(List<String> tags) {
            this.tags = List.copyOf(Objects.requireNonNull(tags, "tags"));
        }

        List<String> tags() {
            return tags;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof SafeTags that
                    && tags.equals(that.tags);
        }

        @Override
        public int hashCode() {
            return tags.hashCode();
        }
    }

    // Component object intentionally mutable to illustrate aliasing.
    static final class MutablePart {
        private String label;

        MutablePart(String label) {
            this.label = Objects.requireNonNull(label, "label");
        }

        String label() {
            return label;
        }

        void setLabel(String label) {
            this.label = Objects.requireNonNull(label, "label");
        }
    }

    // Record containing an immutable String: represents snapshot value.
    record PartValue(String label) {
        PartValue {
            Objects.requireNonNull(label, "label");
        }
    }

    static final class DeepSnapshot {
        private final List<PartValue> parts;

        DeepSnapshot(List<MutablePart> source) {
            Objects.requireNonNull(source, "source");
            List<PartValue> copied = new ArrayList<>();
            for (MutablePart part : source) {
                copied.add(new PartValue(
                        Objects.requireNonNull(part, "part").label()));
            }
            this.parts = List.copyOf(copied);
        }

        List<PartValue> parts() {
            return parts;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof DeepSnapshot that
                    && parts.equals(that.parts);
        }

        @Override
        public int hashCode() {
            return parts.hashCode();
        }
    }
}
```

Use JDK 17 or newer:

```bash
javac --release 17 FinalReferenceDemo.java
java FinalReferenceDemo
```

Expected output:

```text
unsafe after caller edit: [java, hash]
caller sees getter edit: [java, hash, api]
unsafe hash changed: true
safe after caller edit: [java]
safe getter rejects edit: true
safe hash stable: true
safe set contains: true
same value equals: true
shallow element now: HCM
deep snapshot keeps: HCM
```

**Explanation of each group of results:**

- `UnsafeTags` retains `callerTags` itself; when the caller edits the list after the constructor returns, `unsafe.tags()` also changes. The getter returns that same list, so edits through the getter are reflected in `callerTags`.
- `UnsafeTags.hashCode()` relies on `List.hashCode()` and the list contents. After adding `"mutable"`, the hash in the example dataset changes even though the `tags` field is still `final`. This is a hazard if the object has already been placed into a `HashSet` or used as a `HashMap` key.
- `SafeTags` uses `List.copyOf`. Because the elements are immutable `String` values, the caller editing `source` after the constructor does not alter internal state. The resulting list does not support `add`, so it throws `UnsupportedOperationException`. Content-based hashing stays stable and `HashSet.contains(safe)` continues to work.
- Two `SafeTags` created from different lists with the same contents `["java"]` return `equals == true`; their hashes are also equal thanks to the same list algorithm.
- `List.copyOf(List.of(mutablePart))` creates a structurally unmodifiable list that still keeps **the same `MutablePart` reference**. Calling `setLabel("HCM")` also changes the element seen through the shallow list.
- `DeepSnapshot` converts `MutablePart` to `PartValue` (a record holding an immutable `String`) and stores an unmodifiable list. Thus, the subsequent change of `mutablePart` to `"Da Nang"` does not alter the captured data `"HCM"`.

**Regarding verifying hash collections:** the example prints that the hash changed, rather than relying on a specific outcome of `unsafeSet.contains(unsafe)` after mutation. Once a field used in hashing changes, lookup capability is no longer guaranteed; under some bucket configurations, a query might succeed by chance, so a single run cannot be used to prove a design is safe.

## 5. Why does this directly relate to `equals` and `hashCode`?

Suppose `UnsafeTags`'s equality relation is defined as `tags.equals(that.tags)`. When a caller adds or removes elements:
- The value used to compute equality changes.
- `hashCode` also changes because list hashing depends on order and elements.
- Two previously equal objects may no longer be equal; two previously unequal objects may also become equal.

Java does not forbid a mutable object from changing equality when its state changes: `equals`'s consistency requirement is conditioned on the comparison information not changing. However, using that object in a hash structure can break lookup assumptions:

1. `HashSet.add(key)` locates the bucket from the hash at insertion time.
2. The caller alters state that affects the hash.
3. `HashSet.contains(key)` may search a different bucket.
4. The object may still be sitting in the set while search/removal operations fail to reflect expectations.

Even if the hash is intentionally fixed, if the equality of **two objects already inside a Set** flips from `false` to `true`, the set will not reorganize and merge them on its own. Therefore, the right solution is to **stabilize the data used to identify the value/key throughout storage time**, or not use that mutable object directly as a key.

Additional pitfalls:
- For arrays, `array.equals(otherArray)` compares **references** by default, not contents; you need `Arrays.equals` and `Arrays.hashCode` (or the appropriate `deepEquals`/`deepHashCode` variants for nested arrays).
- If using a `record` with an array component, the auto-generated `equals`/`hashCode` for that component also rely on array-reference equality/hashing, not automatic deep content comparison. A record does not make an array immutable.
- Using a collection holding mutable objects as an equality component remains dangerous even if the list forbids structural changes: the list may have the same elements before and after, yet an **element's** hash changes if the element implements hashing via mutable fields.

### Relationship with `toString()`

If `toString()` includes the contents of a mutable list in its display string, two calls may yield different results even though the field reference is `final`. This is not necessarily a `toString` contract bug because the object is genuinely mutable. However, when designing a value object expected to be immutable, unexpectedly changing logs is a sign to inspect for state leaks.

You should not use `toString` to define `equals`, `hashCode`, or persistent identifiers.

## 6. Blocking aliases so `final` fields genuinely preserve meaningful state

After distinguishing a `final` reference from a mutable object, inspect both **constructor inputs** and **getter outputs**. If you keep the caller's `int[]` directly, the caller mutating the array mutates internal state; if you copy-in but the getter returns the internal array directly, the caller can still mutate state. For a one-dimensional primitive array, calling `clone()` on both receipt and return is a direct defense.

```java
// Illustrative lines inside a class with a byte[] bytes field:
this.bytes = input.clone();  // constructor: copy-in
return bytes.clone();        // getter: copy-out
```

For `List<String>` with immutable elements, `List.copyOf(input)` creates an unmodifiable and structurally stable list (while also rejecting null). `Collections.unmodifiableList(input)` by itself is a **view**: mutating `input` through another alias still shows up in the view. If elements are mutable objects, both `List.copyOf` and an ArrayList copy are only shallow copies; you must convert each element to a stable value type if element state participates in `equals/hashCode`.

For multidimensional arrays, cloning the outer array does not copy the rows; for `Date` or other mutable objects, copy-in/copy-out must match the data type. For records, components are `final`, yet auto-generated getters can return mutable references, and array components compare by reference by default rather than by contents. The lesson *Defensive Copying to Protect Array or Collection Fields* provides full runnable examples for `int[]`, `int[][]`, collections, records, `Arrays.equals/hashCode`, and the difference between snapshots and views.

Copies only guard controlled alias paths; if the class itself has a setter modifying data used in equality/hash, the object remains mutable. `final` and defensive copying also do not substitute for a synchronization policy when another party can write while taking a snapshot.

## 7. `final`, `record`, and immutability: common misunderstandings

### `final` on a class

`final class Profile` only blocks inheritance. It can still have a `private String name` with a setter or a `private final List<String> tags` pointing to an `ArrayList` modified externally. A `final` class is a tool that aids immutable design because it prevents subclasses from adding mutable state or changing behavior, yet it does not complete the design on its own.

### `private final` fields

Keeping fields `private final` limits reference-modification paths and makes designs easier to reason about; however, it must be combined with immutable component objects, defensive copying, and getters that do not leak mutable references. If you store a `List<MutablePart>` using `List.copyOf`, the field and list are structurally unmodifiable while each `MutablePart` can still change.

### Records in Java 17+

A record automatically generates `private final` component fields, a constructor, accessors, `equals`, `hashCode`, and `toString`. Yet it is only **shallow** in preserving immutability:

```java
record Bag(List<String> tags) { }

List<String> original = new ArrayList<>(List.of("x"));
Bag bag = new Bag(original);
original.add("y");
System.out.println(bag.tags()); // [x, y]
```

This is an illustrative snippet placed inside a method; the record should be declared in an allowed scope. If you want a safe snapshot for a list of `String`s, use a compact constructor:

```java
record SafeBag(List<String> tags) {
    SafeBag {
        tags = List.copyOf(tags);
    }
}
```

When only immutable components reside inside the list, the record's auto-generated accessor returns an unmodifiable list, keeping state stable. However, if a record holds an array, the record getter returns the same array reference; you must handle defensive copying yourself and pay attention to the array component's equality/hashing. For a record whose component holds mutable objects, `List.copyOf` alone does not freeze child objects either.

### `Collections.unmodifiableList` vs `List.copyOf`

| Expression | Does caller editing the original list affect the view/result? | Can mutable elements be modified? |
|---|---|---|
| `Collections.unmodifiableList(original)` | **Yes**: the wrapper sees changes from original | Yes |
| `Collections.unmodifiableList(new ArrayList<>(original))` | No, for structural changes on original | Yes |
| `List.copyOf(original)` | No, for structural changes on original | Yes |
| `List.of(element)` | Cannot modify list structure | Yes, if element is a mutable object |
| `List.copyOf(original.stream().map(copyToImmutable).toList())` | No, when snapshot elements are truly immutable | Not through the snapshotted state |

Collection immutability and **individual element** immutability are two separate issues.

## 8. Immutability, thread safety, and the Java Memory Model

`final` also has significance for **initialization safety** in the Java Memory Model: if an object is properly constructed (specifically, without letting `this` escape the constructor), `final` field mechanics ensure other threads see properly initialized field values when accessing the constructed object. However:

- `final` does not automatically guarantee that subsequent state edits on the referenced object after construction are visibly synchronized across threads.
- A `final List` containing an `ArrayList` can be mutated concurrently, still requiring synchronization design or avoiding shared mutable state.
- A getter that creates a copy on demand does not automatically resolve races if the source is being modified simultaneously by another thread.
- Mechanisms such as `synchronized`, locks, concurrent collections, or immutable snapshots address different problems and should not be substituted for one another.

A value object whose entire meaningful state is immutable after initialization is usually easier to share across threads because no synchronization is needed for **reading unchanging state**. Yet if the object has a mutable lazy cache or depends on external state, those interaction paths still need inspection.

## 9. Design strategies tied to the Object Contract

When you want an object to serve as a **value** or a **map/set key**:
1. Choose the fields determining equality according to domain semantics.
2. Identify whether those fields or child objects can change.
3. If stable state is needed, use immutable values; when receiving arrays/collections/mutable objects, create appropriate protective snapshots.
4. Never return internal mutable references directly via getters, callbacks, or other APIs.
5. Implement `equals` and `hashCode` based on the same information and verify hash stability for as long as the object is used as a key.
6. For an **intentionally mutable** entity, avoid using editable attributes as long-term identity; consider an immutable ID or separate immutable key. Distinguish entity identity from value equality.

**When immutability is not needed:** an object modeling a shopping cart currently being edited can be intentionally mutable. In that case, not every field needs to be immutable; what matters is understanding the contract, naming update APIs clearly, and avoiding using the entire changing state as a hash key.

### Deep aliasing traps

A type like `final Map<String, List<Item>>` has at least three layers:
- The map can be mutable.
- The lists serving as map values can be mutable.
- Each `Item` can be mutable.

`Map.copyOf` alone blocks modifying the map structure, without automatically copying inner lists or items. `List.copyOf` on each list still leaves the `Item` risk. To achieve a genuinely stable snapshot, you must identify and freeze or copy **every mutable component that affects equality or public behavior**.

## 10. Common mistakes and how to recognize them

| Mistake | Consequence | How to fix |
|---|---|---|
| Assuming `private final List` is immutable | Caller can modify list via alias | Defensive copy in constructor and safe accessor |
| Using `Collections.unmodifiableList(input)` while keeping external `input` | View still reflects changes to input | Copy before wrapping, or use `List.copyOf` |
| Using `List.copyOf` for a list of mutable elements and assuming deep immutability | Element state still changes | Snapshot each element or use immutable element types |
| Getter returns raw `byte[]` array | Caller mutates internal array | `clone()` in both constructor and getter |
| Overriding `equals` by array contents but hashing by array address | Violates hash contract | Use `Arrays.equals` + `Arrays.hashCode` |
| Using a mutable collection in `hashCode` for a key object | Hash changes and lookups can fail | Stabilize key contents or use a separate immutable key |
| Using a record with mutable components and assuming deep immutability | Accessor exposes mutable element/array | Compact constructor and structural defensive copy |
| Using `final` as a substitute for thread synchronization | Race and visibility bugs when child state changes | Design immutable snapshots or explicit synchronization |
| Calling `clone` without understanding shallow vs deep clone | Aliases remain in child objects | Copy constructor/factory with explicit semantics |

## 11. Self-check exercises

### Exercise 1 — Predicting `final` behavior

```java
final List<String> data = new ArrayList<>(List.of("a"));
data.add("b");
// data = new ArrayList<>(); // Does not compile if uncommented.
System.out.println(data);
```

Prediction: `[a, b]`. The reassignment line is only a comment pointing out the limit of `final`.

### Exercise 2 — Shallow snapshot and mutable elements

Create a `List<MutablePart>`; capture `List.copyOf(list)`; modify `list.get(0).setLabel(...)`. Explain why the new list cannot `add`, yet the `label` value viewed through the list still changes. Then replace the element with a `record PartValue(String label)` and check the difference.

### Exercise 3 — Arrays and the object contract

Create two arrays `byte[] a = {1, 2}`, `byte[] b = {1, 2}`. Compare `a == b`, `a.equals(b)`, and `Arrays.equals(a, b)`; predict `false`, `false`, `true` respectively. Design a `ByteKey` that does not expose its internal array.

### Exercise 4 — State leak through a getter

Change `UnsafeTags`'s constructor to `new ArrayList<>(tags)` while keeping the getter returning the list directly. Can the object still be mutated from outside? Yes: the getter still returns an alias to the internal mutable list. Next, change the getter to return `List.copyOf(tags)` or use a field storing the snapshot list right from the constructor and test again.

### Exercise 5 — Hash collections

Insert an `UnsafeTags` into a `HashSet`, then modify the list participating in `hashCode`. Read the hash before and after, and try finding the object again. If `contains` still returns `true` in one run, explain why that **does not prove the design is correct**. Try adding many elements, without writing tests dependent on the JDK's internal buckets.

### Exercise 6 — Business domain policy

An order has an immutable ID and a mutable list of products. Will you define `equals`/`hashCode` by ID or by the list? If it is an **entity**, it is normally identified by persistent identity, not by line items currently being edited. If it is a **value snapshot**, you need to snapshot the line items and ensure they have stable value semantics. You must make the decision based on domain meaning rather than merely because `final` is present.

## 12. Completion checklist

- Distinguish "cannot reassign a reference" from "cannot mutate the referenced object."
- Spot at least two alias paths: constructor input and getter output.
- Know that `List.copyOf` protects list structure, while mutable elements still need snapshots.
- Know that arrays must be defensively copied on both input and output if immutability is needed.
- Do not mistakenly assume a `final` class or Java record guarantees deep immutability.
- Explain why mutating component fields changes `equals`/`hashCode` and creates risks with `HashSet`/`HashMap`.
- Distinguish immutable from thread-safe; `final` does not replace synchronization of mutable state.
- Compile and run `FinalReferenceDemo.java`, accurately predict stdout, and explain the results.

**Key point:** `final` only fixes variable/field assignment. To make an object state-immutable and stable under the Object Contract, you must design the entire meaningful reference graph: control aliases, copy necessary mutable components, and prevent data participating in equality/hashing from changing unexpectedly.