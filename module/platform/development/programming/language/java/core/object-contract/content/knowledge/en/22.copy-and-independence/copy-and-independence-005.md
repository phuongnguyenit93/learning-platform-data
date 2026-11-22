# `final` Fields and the Limitation of Adding Copying After `super.clone()`

## 1. The Problem to Solve

When copying a Java object, we usually want to create **a new instance** while ensuring that mutable data inside it is not unintentionally shared with the original object. For arrays, `List`, `Map`, or mutable objects, simply copying the reference is not enough.

One approach mentioned in legacy Java code is:

1. Call `super.clone()` to create an instance whose initial fields are copied from the current object.
2. Then, on the copied object, **reassign the mutable reference fields** to separate copies (for example `result.items = new ArrayList<>(items)`).

This technique **has an important limitation when a field is declared `final`**. With:

```java
private final int[] values;
```

the statement `result.values = values.clone();` inside `clone()` **does not compile**, because Java does not allow reassigning a `final` field in an ordinary method, even though that field belongs to the new instance created by `super.clone()`.

Meanwhile, `super.clone()` still copies the **reference value** of the `final` field. As a result, the original object and the cloned object can hold **the same mutable array**:

```text
Before clone:
original.values ─────> int[] {1, 2}

After super.clone() (shallow copy):
original.values ──┐
                  ├────> same int[] {1, 2}
copy.values ──────┘

Desired if independent:
original.values ─────> int[] {1, 2}
copy.values ─────────> int[] {1, 2} (different array)
```

This is the core of the lesson: **`final` prevents a reference from being reassigned after normal initialization, but does not make the referenced object immutable; `super.clone()` performs a shallow copy, and the fix of reassigning the field after cloning is blocked by `final`.**

## 2. Understanding `final` on Data Fields Precisely

Compare these cases:

| Declaration | What `final` protects | What it does **not** protect |
| --- | --- | --- |
| `private final int count;` | After initialization, `count` cannot be reassigned from an ordinary method | There is no mutable child object in this primitive field |
| `private final String name;` | The `name` reference cannot be reassigned | `String` itself is immutable; that is a property of the `String` class, not magic from `final` |
| `private final int[] scores;` | The `scores` reference cannot be reassigned in a method | You can still call `scores[0] = 99`; array elements are mutable |
| `private final List<Item> items;` | The `items` reference cannot be reassigned | The collection can be modified if the list type allows it; each mutable `Item` can also be modified |

Example:

```java
// Code snippet inside a class; not a standalone program.
private final int[] scores = {5, 10};

void update() {
    scores[0] = 20;            // Valid: modifies array element
    // scores = new int[] {5}; // COMPILE ERROR: reassigning final field
}
```

A `final` field can be initialized in its declaration or in a constructor under Java's definite-assignment rules; it cannot be arbitrarily reassigned in other methods. For a mutable reference, that is **fixing the reference address at the language level**, not *deep immutability*.

Distinguish `final class` from `final field`: a `final` class cannot be subclassed, yet objects stored in its fields can still be mutable. Conversely, a `final` field can appear in a non-`final` class.

## 3. `Cloneable`, `Object.clone()`, and Shallow Copies

### 3.1. `Cloneable` Does Not Automatically Provide a Public `clone()` Method

`java.lang.Cloneable` is a **marker interface**. It does not declare a `clone()` method for callers to invoke freely. `Object.clone()` is a `protected` method, which subclasses can override to expose an appropriate clone API.

When `Object.clone()` is called on an instance that does not support `Cloneable`, it can throw `CloneNotSupportedException`. Java arrays are a special case: arrays support cloning, and `array.clone()` creates a new array with elements shallow-copied at the array level.

A traditional pattern:

```java
@Override
public Example clone() {
    try {
        return (Example) super.clone();
    } catch (CloneNotSupportedException e) {
        throw new AssertionError(e);
    }
}
```

This is an illustrative code snippet inside a class `Example implements Cloneable`. Catching the exception into `AssertionError` only makes sense if you **know for sure** the class implements `Cloneable` and `super.clone()` works under the contract; do not copy it mechanically across every inheritance hierarchy.

### 3.2. `super.clone()` Does Not Run the Constructor of the Class Being Cloned

`Object.clone()` creates an object whose fields initially receive the same values as the source object via shallow copy. It **does not call the ordinary constructor** of that class to reinitialize fields or recheck all invariants.

Therefore:

- Primitive fields receive the same primitive values.
- `String` or immutable object fields can keep the same reference; usually safe because their contents cannot be modified.
- Fields referencing arrays, collections, or mutable objects are copied as **the same reference**.
- `final` fields also have their initial value copied, but Java code in `clone()` cannot reassign them afterward.

This does not mean Java says “a class with `final` cannot be cloned”: **it can still be cloned**, but if a `final` field points to mutable data requiring independence, the “`super.clone()` then reassign field” technique cannot satisfy it.

## 4. Why the Usual Shallow-Clone Fix Does Not Apply to `final`

With a non-`final` field, legacy classes often wrote:

```java
// Code snippet inside a class that implements Cloneable, with List<String> items.
@Override
public Example clone() {
    try {
        Example result = (Example) super.clone();
        result.items = new ArrayList<>(this.items);
        return result;
    } catch (CloneNotSupportedException e) {
        throw new AssertionError(e);
    }
}
```

This snippet assumes `items` is a **non-final** field and `String` elements are immutable. `new ArrayList<>(items)` creates a new list, but only shallow-copies the elements. If `items` contains `MutableItem`, the two different lists still share the very same mutable elements.

Change the declaration to:

```java
private final List<String> items;
```

and the line:

```java
result.items = new ArrayList<>(this.items);
```

becomes a **compile-time error**: cannot assign a value to a `final` field. You cannot bypass this restriction merely by casting, calling a setter, or removing `private`; a setter still has no right to reassign an already-initialized `final` field.

**Do not fix it by mutating the shared collection directly**:

```java
// WRONG if original.items and result.items point to the same list!
result.items.clear();
result.items.addAll(this.items);
```

Such operations mutate **the very collection owned by the original**. With `this.items` pointing to the same object, `clear()` even wipes out the source data before `addAll` runs. This is not a way to create an independent copy.

Similarly, calling `result.values[0] = ...` on a `final` array after cloning only modifies an element of the same array, rather than separating it into a new array.

## 5. Complete Java 17 Example: Dangerous Sharing and Two Safe Alternatives

The following example tests three designs:

1. `ShallowFinalClone` has `private final int[]` and overrides `clone()` using `super.clone()`. The source array is copied in the constructor, yet the original and the clone **still share the array** after cloning.
2. `SafeCopy` keeps `private final int[]` and has a **copy constructor**, creating a new array when constructing the object. The original and the copy can be mutated independently.
3. `DeepCloneMutableField` intentionally leaves the array field **non-final**, allowing cloning via `super.clone()` followed by reassigning a copy of the array. It illustrates the syntax boundary: this technique works when the field is non-final, at the trade-off of giving up reference immutability at the field level.

Save the file **`FinalCloneDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

public class FinalCloneDemo {
    static final class ShallowFinalClone implements Cloneable {
        private final int[] values;

        ShallowFinalClone(int[] input) {
            values = Objects.requireNonNull(input, "input").clone();
        }

        void update(int index, int value) {
            values[index] = value;
        }

        int[] snapshot() {
            return values.clone();
        }

        boolean sharesArrayWith(ShallowFinalClone other) {
            return values == other.values;
        }

        @Override
        public ShallowFinalClone clone() {
            try {
                return (ShallowFinalClone) super.clone();
                // Cannot write:
                // result.values = this.values.clone();
                // because values is final.
            } catch (CloneNotSupportedException e) {
                throw new AssertionError(e);
            }
        }
    }

    static final class SafeCopy {
        private final int[] values;

        SafeCopy(int[] input) {
            values = Objects.requireNonNull(input, "input").clone();
        }

        SafeCopy(SafeCopy other) {
            Objects.requireNonNull(other, "other");
            values = other.values.clone();
        }

        void update(int index, int value) {
            values[index] = value;
        }

        int[] snapshot() {
            return values.clone();
        }

        boolean sharesArrayWith(SafeCopy other) {
            return values == other.values;
        }
    }

    static final class DeepCloneMutableField implements Cloneable {
        private int[] values; // Non-final so it can be reassigned in clone()

        DeepCloneMutableField(int[] input) {
            values = Objects.requireNonNull(input, "input").clone();
        }

        void update(int index, int value) {
            values[index] = value;
        }

        int[] snapshot() {
            return values.clone();
        }

        boolean sharesArrayWith(DeepCloneMutableField other) {
            return values == other.values;
        }

        @Override
        public DeepCloneMutableField clone() {
            try {
                DeepCloneMutableField copy =
                    (DeepCloneMutableField) super.clone();
                copy.values = values.clone();
                return copy;
            } catch (CloneNotSupportedException e) {
                throw new AssertionError(e);
            }
        }
    }

    public static void main(String[] args) {
        int[] external = {1, 2};
        ShallowFinalClone original = new ShallowFinalClone(external);
        ShallowFinalClone clone = original.clone();

        external[0] = 99;
        System.out.println("Constructor detached input: "
            + Arrays.toString(original.snapshot()));
        System.out.println("Final clone shares array: "
            + original.sharesArrayWith(clone));

        clone.update(0, 7);
        System.out.println("Original after clone update: "
            + Arrays.toString(original.snapshot()));
        System.out.println("Clone after update: "
            + Arrays.toString(clone.snapshot()));

        SafeCopy safeOriginal = new SafeCopy(new int[] {1, 2});
        SafeCopy safeCopy = new SafeCopy(safeOriginal);
        safeCopy.update(0, 7);
        System.out.println("Copy constructor shares array: "
            + safeOriginal.sharesArrayWith(safeCopy));
        System.out.println("Safe original: "
            + Arrays.toString(safeOriginal.snapshot()));
        System.out.println("Safe copy: "
            + Arrays.toString(safeCopy.snapshot()));

        DeepCloneMutableField deepOriginal =
            new DeepCloneMutableField(new int[] {1, 2});
        DeepCloneMutableField deepCopy = deepOriginal.clone();
        deepCopy.update(0, 7);
        System.out.println("Repaired clone shares array: "
            + deepOriginal.sharesArrayWith(deepCopy));
        System.out.println("Repaired original: "
            + Arrays.toString(deepOriginal.snapshot()));
        System.out.println("Repaired copy: "
            + Arrays.toString(deepCopy.snapshot()));
    }
}
```

Compile and run with **JDK 17 or higher**, in the directory containing the file:

```bash
javac FinalCloneDemo.java
java FinalCloneDemo
```

Deterministic output:

```text
Constructor detached input: [1, 2]
Final clone shares array: true
Original after clone update: [7, 2]
Clone after update: [7, 2]
Copy constructor shares array: false
Safe original: [1, 2]
Safe copy: [7, 2]
Repaired clone shares array: false
Repaired original: [1, 2]
Repaired copy: [7, 2]
```

**Interpretation:**

- `ShallowFinalClone`'s constructor already called `clone()` on the input array, so modifying `external[0]` does not affect internal state. However, that is only the **caller → original** boundary. When `original.clone()` is called, `super.clone()` creates **two objects holding the same reference field**, and `final` cannot separate the referenced object.
- `clone.update(0, 7)` modifies the shared array; snapshots of both the original and the clone become `[7, 2]`. This is a copy independence bug, not a getter exposing a reference.
- `SafeCopy(SafeCopy other)` **creates the object via a constructor**, so it is allowed to assign a new value to the `final` field during initialization. The array is cloned separately, and subsequent edits are independent.
- `DeepCloneMutableField.clone()` can use `copy.values = values.clone()` because `values` is not `final`. It must still properly copy all other mutable components of the class if any exist; this is only an example with a single primitive array.
- All copies are distinct instances. The goal of “independence” refers to **not sharing mutable contents requiring separate ownership**, not just checking `clone != original`.

## 6. Preferred Solution: Copy Constructor or Factory Creating a New Object

When a class needs `final` fields and independently copied state, a **copy constructor** is the direct approach:

```java
public final class Snapshot {
    private final int[] values;

    public Snapshot(int[] values) {
        this.values = values.clone();
    }

    public Snapshot(Snapshot source) {
        this.values = source.values.clone();
    }

    public int[] values() {
        return values.clone();
    }
}
```

Note: this snippet is a standalone class without `main`; if compiling separately, save as `Snapshot.java`. `null` checks should be added if invalid inputs are possible and a clear error message is needed.

This approach satisfies three requirements:

1. **Valid `final` field initialization:** the constructor assigns the reference once during instance construction.
2. **Copy-in:** prevents the caller from mutating the input array and altering the snapshot.
3. **Copy-out:** the getter does not return the internal array directly.

You can create a factory whose name states the policy clearly:

```java
public static Snapshot copyOf(Snapshot source) {
    return new Snapshot(source);
}
```

This is an additional code snippet **inside** the `Snapshot` class above, not a standalone method outside the class.

### 6.1. A “Copy Constructor” Is Not Automatically a Deep Copy

If a field is `List<MutableItem>`, writing `new ArrayList<>(other.items)` only copies the **outer collection shell**; the `MutableItem` instances may still be shared. If each element needs separate ownership, the constructor must copy at the right level of mutable data:

```java
// Code snippet: suppose MutableItem has a copy constructor.
List<MutableItem> copiedItems = other.items.stream()
    .map(MutableItem::new)
    .toList();
```

`Stream.toList()` in Java 17 creates a structurally unmodifiable list, though if `MutableItem` remains mutable then the copy allows mutating individual elements; that can be right for a class owning its own elements, provided those references are not leaked improperly. If deeply immutable state is wanted, use an immutable value object or snapshot record for each element.

### 6.2. When Is Copying Each Component Unnecessary?

Not every reference must be cloned:

- `String`, `LocalDate`, `Instant`, `BigInteger`, and properly designed immutable value objects: sharing references is usually safe.
- A `List<String>` created with `List.copyOf`, with immutable `String` elements and no affecting mutable aliases, can be shared as an immutable value.
- An immutable record with **all deeply immutable components** can be reused in the copy without breaking observable independence.

Conversely, merely marking `List<MutableItem>` as `final` or using `List.copyOf` does not make `MutableItem` immutable. A structurally unmodifiable collection containing mutable objects is **not** an immutable graph.

## 7. Can You Keep Public `clone()` Without Using `super.clone()`?

For a self-designed `final` class, if an API already requires the name `clone()`, you can **create a new instance via constructor** inside the override instead of using `super.clone()`:

```java
public final class CloneByConstructor implements Cloneable {
    private final int[] values;

    public CloneByConstructor(int[] input) {
        this.values = input.clone();
    }

    @Override
    public CloneByConstructor clone() {
        return new CloneByConstructor(this.values);
    }
}
```

This is a compilable class if saved as `CloneByConstructor.java`; it does not contain `main`. In this example, the constructor clones the input array again, ensuring the copy has its own array. Implementing `Cloneable` is an option to keep a familiar API, but is **not a necessary condition** for this hand-written method to use `new` to create a new object; it only matters when using the `Object.clone()` mechanism.

However, **do not apply this naively to an open inheritance hierarchy**: superclass/subclass constructors may enforce invariants, the runtime type of the object may be a subclass, and a copy created via the superclass constructor can lose subclass state/type. Usually it is better to design a clear copy constructor or factory per type, or prefer immutable value objects.

If the class is `final` like `CloneByConstructor`, there are no subclasses, so creating the right copy type is easier to control.

## 8. Why Removing `final` Just for `super.clone()` May Not Be Good

One syntactic option is to remove `final`:

```java
private int[] values; // Can be reassigned in clone(), but no longer final.
```

That allows:

```java
Example copy = (Example) super.clone();
copy.values = values.clone();
```

This is a snippet assuming a class `Example implements Cloneable`, with a non-final `values` field, inside a `clone()` method with appropriate checked-exception handling.

However, removing `final` trades off:

- **Reference invariant:** other methods in the class can reassign the field, increasing the state space to reason about.
- **Design signal:** readers no longer have a guarantee that the reference field does not change after the object is initialized.
- **Publication safety and concurrency:** `final` carries specific memory semantics under the Java Memory Model when the object is properly constructed without leaking `this` in the constructor. Removing `final` can make reasoning about initialization/publication harder; it does not automatically make code wrong, but this benefit should not be discarded merely for `clone()`.
- **Maintenance:** you must always remember to update `clone()` when adding a new mutable field; forgetting to copy a field introduces an unwanted sharing path.

There is no need to claim every class should be immutable. If requirements genuinely demand a mutable class cloned under its own protocol, non-final fields and controlled deep copying are an acceptable design. But if the core requirement is an unchanging snapshot or a value object, constructors/factories and `final` fields are usually easier to prove correct.

## 9. Impact on `equals()`, `hashCode()`, and Hash Collections

When copying an object, separate **state independence** from **value equality**:

- `original == copy` must be `false` if a genuinely new instance was created.
- `original.equals(copy)` can be `true` or `false` depending on the class's equality semantics. For value objects with identical components, it is usually `true`; for entities compared by distinct identity, it depends on the ID strategy.
- `original.hashCode() == copy.hashCode()` is **required** when `equals` reports equality; two distinct objects may still legitimately have the same hash.
- `toString()` may display the same content even when a clone shares a mutable object; identical readable strings **do not prove** independence.

If `equals/hashCode` is based on a mutable array shared by a clone, mutating through the clone can **silently change** the original object's hash. If the original is currently a `HashMap` key or `HashSet` element, lookups can fail.

Example:

```java
// Code snippet: suppose key.hashCode() is based on the contents of a mutable array.
set.add(original);
CloneType copy = original.clone(); // super.clone() shares the final array
copy.updateValue(0, 99);          // may cause original.hashCode() to change
boolean found = set.contains(original); // not guaranteed as expected
```

The code above illustrates a design consequence; it is not a standalone Java program. If an object is used as a hash key, fields participating in `equals/hashCode` need to remain stable while it resides in a hash structure, or an appropriate identity representation must be chosen. Defensive copying only solves external aliasing; if the class itself has mutating methods, the object remains mutable.

## 10. Handling Collections or Nested Objects

### 10.1. `final List<String>`

If a class receives a list containing `String`s and wants to take a structural snapshot:

```java
// Code snippet inside constructor; input: List<String>.
this.tags = List.copyOf(input);
```

With field `private final List<String> tags;`, calling `List.copyOf` creates/assigns an unmodifiable list with immutable `String` elements. When creating a business copy later, `tags` can be reused if immutability of contents is guaranteed. There is **no need** to call `super.clone()` and reassign `tags` to achieve value independence.

### 10.2. `final List<MutableItem>`

If `MutableItem` is mutable, `List.copyOf(items)` only creates/keeps a **structurally** unmodifiable list; mutable elements are still shared. Each item must be copied or converted to an immutable item in the constructor:

```java
// Code snippet: ItemSnapshot is a record containing only immutable fields.
this.items = input.stream()
    .map(x -> new ItemSnapshot(x.id(), x.name()))
    .toList();
```

This snippet assumes the field has type `List<ItemSnapshot>`, `input` has `id()` and `name()`, and `ItemSnapshot`'s components are immutable. `Stream.toList()` returns a structurally unmodifiable list in Java 17. This is a snapshot of selected fields, not an automatic “clone everything”.

### 10.3. `final int[][]`

`matrix.clone()` only copies the outer array; the `int[]` rows are still shared. If full matrix independence is needed:

```java
static int[][] copyMatrix(int[][] source) {
    int[][] result = new int[source.length][];
    for (int i = 0; i < source.length; i++) {
        result[i] = source[i].clone();
    }
    return result;
}
```

This illustrative method assumes `source` and every row are non-`null`; a `null` policy must be designed additionally if data allows nulls. Call `copyMatrix` in the constructor to assign the final field, and when returning the matrix externally so aliases are not exposed.

### 10.4. Object Graphs with Circular References

With multiple nodes referencing one another, “deep copy” may need a mapping table from old nodes to new nodes to preserve structure and handle cycles; a simple copy constructor per node can loop infinitely or accidentally create multiple copies of the same node. If business requirements only need a few values, designing an immutable DTO/snapshot is usually less error-prone than cloning the entire graph.

## 11. Asking the Right Questions Before Choosing a Solution

A practical decision table:

| Need | Suitable solution | Notes |
| --- | --- | --- |
| Snapshot/value object with `final` and data needing independence | Copy constructor or factory + defensive copy | Easy to preserve `final` fields and invariants |
| Only primitive fields and immutable references | Sharing immutable values is acceptable | Avoids pointless deep copies |
| Must stay compatible with legacy `clone`, non-final mutable fields | `super.clone()` then replace each mutable reference with a copy | Update whenever a new field needing copy is added |
| API requires method named `clone()`, `final` class with mutable final field | Override `clone()` to call a new constructor/factory | Using `super.clone()` is not mandatory |
| Have `final List<MutableItem>` needing deep immutability | Convert each item to an immutable value snapshot | `List.copyOf` alone is not enough |
| Class/graph with inheritance or complex relationships | Design a dedicated copy protocol or domain-specific snapshot | Watch out for losing subtypes and circular references |

**There is no single automatic “deep clone” right for every Java object**: file/socket resources, locks, entity IDs, database connections, and object graphs may each have their own ownership rules. Cloning a connection or copying the same business ID may make no valid sense. You must clearly decide what the new object is allowed to share and what it must be independent from.

## 12. Common Mistakes

| Mistake | Why is it wrong? | How to fix |
| --- | --- | --- |
| Thinking `final int[]` makes the array immutable | Only fixes the reference; elements can still be mutated | Defensive copy and APIs that do not leak aliases |
| Thinking `super.clone()` automatically deep-copies | Only shallow-copies fields | Design copying for each mutable component |
| Writing `copy.finalField = ...` after `super.clone()` | Does not compile: cannot reassign a `final` field | Copy constructor/factory creating a new instance |
| Calling `copy.items.clear()/addAll` to “fix” aliasing | Both objects may share the list; editing the clone edits the original | Create a new collection in constructor or make field non-final if design warrants |
| Using `new ArrayList<>(source)` and assuming mutable elements are independent | Only copies the collection shell | Copy mutable elements or take an immutable snapshot |
| Copying input only in constructor then calling `super.clone()` | Caller is detached, yet the new clone still shares internals with original | Apply a separate copy strategy when creating clones |
| Removing `final` without considering design | Loses reference-fixity guarantee and changes concurrency reasoning | Prefer constructor when `final` fields are wanted |
| Letting an inherited clone miss new fields of a subclass | Copy may share mutable state or violate invariants | Design copying for both parent/child classes and test |
| Using `clone()` without error-handling/`Cloneable` strategy | `Object.clone()` can throw `CloneNotSupportedException` | Use an explicit copy API or implement `Cloneable` properly |
| Calling clone and only checking `original != copy` | Two objects with different references can still share arrays | Try mutating the copy and confirm the original is unchanged |

## 13. Testing Checklist

For a class with mutable `final` fields requiring independent copies:

1. **Check distinct instance creation:** `original != copy`.
2. **Check initial contents:** values must be equivalent after copying.
3. **Check aliasing:** mutate through the copy's methods, observe whether the original changes.
4. **Check input aliasing:** mutate input arrays/lists after the constructor; does the created object change?
5. **Check output aliasing:** if getters return arrays/lists, does mutating the returned values affect internal state?
6. **Check nested mutables:** are multidimensional arrays or mutable elements copied to the right depth?
7. **Check `equals`/`hashCode`:** independent copies must not unexpectedly alter the original object's hash; equality relationship fits the domain.
8. **Check nulls, collection order, and invariants:** the copy strategy must not accidentally alter validity conditions, ordering, or uniqueness.
9. **Check `final` declarations and compilation:** constructor-based solutions assign fields at a valid point; solutions reassigning inside `clone()` will be rejected by Java.
10. **Check subtypes:** if inheritance is present, does cloning preserve the runtime type and each class's invariants?

A test that only checks whether initial arrays are equal is not enough to prove independence. You must actively **mutate the copy after creation** and compare against the original; this is the fastest way to detect shared mutable state.

## 14. Self-Check

**Question 1.** A class has `private final int[] numbers`. Does `super.clone()` copy the elements into a new array?

**Answer:** No. The shallow copy keeps the same array reference. The `final` field still has its initial reference value copied, rather than automatically creating a new array.

**Question 2.** Why does `copy.numbers = numbers.clone()` after `super.clone()` not compile if `numbers` is `final`?

**Answer:** Because that is reassigning a `final` field inside the `clone()` method, not a valid field initialization in a constructor or initializer. An object produced by `super.clone()` does not waive the language's `final` rules.

**Question 3.** Can you write `numbers[0] = 3` even if `numbers` is `final`? Does that solve deep copying?

**Answer:** You can modify elements if the array is mutable; however, it does not create a new array, so it does not solve alias sharing. If the clone shares the array with the original, both observe the change.

**Question 4.** How can you keep `private final int[] numbers` yet create two instances owning separate arrays?

**Answer:** A copy constructor or a factory calling a constructor, cloning the array when assigning the field at instance creation time. If a `clone()` API is needed, you can construct a new instance using the constructor inside that method for an appropriately designed class.

**Question 5.** Does `List.copyOf(List<MutableItem>)` create an immutable graph?

**Answer:** No. It prevents modifying the list structure, yet still references the `MutableItem` instances; to get deep immutability, immutable items or proper per-item copying is needed.

**Question 6.** After `super.clone()`, two objects have `original != copy` and `original.toString().equals(copy.toString())`. Is independence proven?

**Answer:** Not yet. Both only confirm distinct instances and similar string representations. You must try mutating mutable data through one side and observe the other.

**Question 7.** Is it necessary to remove `final` to get an independent copy?

**Answer:** No. Only **reassigning after `super.clone()`** is blocked. Creating a new object via a constructor/factory allows initializing the `final` field with an already-copied reference, while keeping the reference-fixing design.

---

**Takeaway:** `final` fixes the **field's reference**, without making the referenced data immutable. `super.clone()` creates a **shallow copy**, without automatically copying arrays/collections; the “`super.clone()` then reassign field” pattern does not apply to `final` fields. When genuine independence is needed while keeping `final` fields, prefer a **copy constructor/factory with defensive copying**, and test by mutating the copy and confirming the original does not change.
