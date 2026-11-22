# Records Are Only Shallowly Immutable and Can Still Hold Mutable Data

## 1. What Matters Most to Understand

In Java 17+, `record` lets you declare a class dedicated to representing data via a list of **record components**. Given the example:

```java
record Profile(String name, java.util.List<String> roles) {}
```

Java generates `private final` fields corresponding to `name` and `roles`, a constructor, `name()`/`roles()` accessors, and the `equals()`, `hashCode()`, and `toString()` methods. The record class itself is also `final`, meaning it cannot be extended via inheritance.

However, `final` on a **reference field** only prevents reassigning that reference after initialization. It **does not freeze the object the reference points to**. Consequently, a record can hold a `List`, `Map`, array, `Date`, `StringBuilder`, or a custom object you wrote that has mutable state. If a record directly holds a mutable object, the data observed through the record can still change.

**Distinguish three concepts:**

- **Unreassignable field (final reference):** the `roles` field always keeps the same reference it was initialized with; you cannot write `profile.roles = other` from outside.
- **Shallow immutability:** the outer structure does not allow replacing the component reference, yet the data inside the referenced object can change.
- **Deep immutability:** all observable state affecting the value cannot be modified through any available references; this requires nested components to also be immutable or appropriately copied/isolated.

**Records do not automatically guarantee deep immutability.** A record is a data-modeling tool with a contract over its components, not a mechanism that automatically freezes an entire object graph.

## 2. Mechanism: `final` Fixes the Reference, Not the State

Consider this illustrative snippet:

```java
record Team(String name, java.util.List<String> members) {}

java.util.List<String> people =
        new java.util.ArrayList<>(java.util.List.of("An"));
Team team = new Team("Backend", people);

people.add("Binh");

// team.members() now has ["An", "Binh"].
```

`team.members()` returns the list the record holds; because the default constructor does not copy it, the variable `people` and the component `members` point to the same `ArrayList`.

Callers can mutate the list through at least two paths:

1. Keep the input reference `people` and call `people.add(...)`; the record will observe that change.
2. Call `team.members().add(...)`; the default generated accessor returns the exact `List` reference stored internally.

`private final` applies only to **the record's `members` field**. It does not make `add`, `remove`, or `clear` on an `ArrayList` illegal.

If a component is a `String` or an appropriate immutable value, we do not face content mutation through that object itself. Yet having just one mutable component makes it impossible to claim that all state of the record is immutable.

## 3. What Java Guarantees and Does Not Guarantee for Records

| Property | What a Record Guarantees | What a Record Does Not Automatically Guarantee |
| --- | --- | --- |
| Record type | Is a `final` type, no subclasses | All objects pointed to by components are immutable |
| Component fields | Corresponding fields are `private final` | Referenced objects cannot be modified elsewhere |
| Default accessors | Provides `componentName()` | Automatically performs defensive copying when returning components |
| Default constructor | Receives component values and stores them in fields | Automatically copies/validates mutable structures |
| Default `equals()`/`hashCode()` | Based on components per Java rules | Results remain stable if a mutable component is modified |
| Default `toString()` | Represents record name and components | An immutable snapshot or data safe to expose publicly |
| Arrays or collections as components | Can store references to them | Deeply compares all elements or locks internal state |

A record can define methods, constructors to validate/copy inputs, or custom accessors. It still cannot declare extra standalone **instance fields** beyond the component fields permitted by record syntax; `static` fields can still exist under Java rules. This restriction does not mean the objects held inside components are immutable.

## 4. Why Does Mutable Data Also Affect the `equals()` and `hashCode()` Contract?

A crucial aspect of the **record contract** is that the generated `equals()` and `hashCode()` methods are based on the components.

Given the record:

```java
record Task(String title, java.util.List<String> labels) {}
```

the `labels` component is compared using `List` equality. Standard `List`s compare by **sequence of elements** and compute their hash from the sequence's contents. Thus, after adding an element to the stored list, `task.hashCode()` can change. Relative to another record, `task.equals(otherTask)` can also flip from `true` to `false` or vice versa if data participating in comparison is modified.

This does not automatically violate the `equals` contract: the consistency contract only applies when the data used for comparison does not change. However, mutable records pose major risks when used as keys in a `HashMap` or elements in a `HashSet`.

Example:

```java
java.util.List<String> labels =
        new java.util.ArrayList<>(java.util.List.of("java"));
Task key = new Task("study", labels);

java.util.Set<Task> items = new java.util.HashSet<>();
items.add(key);
labels.add("spring"); // Mutates the data used to compute the hash.
```

After the final `add`, `key`'s hash value may differ from the hash at the time of `items.add(key)`. `HashSet` places the element in a slot computed from the old hash, so looking up `items.contains(key)` can fail even when **holding the exact same `key` reference**. You should not write tests assuming every hash configuration is guaranteed to fail because hash/bucket collisions and table sizes can affect outcomes; what to avoid is **mutating a key after inserting it into a collection**.

### Difference Between `List` and Arrays as Components

For `List`, standard `equals` inspects elements. However, Java arrays **do not override `Object.equals()` by contents**. Therefore:

```java
record Bytes(byte[] content) {}

Bytes a = new Bytes(new byte[] {1, 2});
Bytes b = new Bytes(new byte[] {1, 2});

// java.util.Arrays.equals(a.content(), b.content()) is true.
// a.equals(b) is false: two arrays with different references.
```

The comments above describe the outcome of the illustrative snippet; there is no need to change the record's `equals` code to observe them. Records generate `equals` for array components using array reference equality, **without automatically calling `Arrays.equals`**. If you want arrays compared by contents, you must manually design an appropriate `equals`/`hashCode` (and defensive copies), or change the model to an immutable value type with the desired equality relation.

**Remember:** Immutability and equality are two related yet **distinct** concerns. Blocking array mutation with cloning still does not make a default record compare bytes by contents.

## 5. Two Boundaries to Protect When Deep Immutability Is Needed

For mutable data, you must examine **both constructor inputs and accessor outputs**. For instance, a record containing `byte[]` must clone on input so the caller cannot mutate the original array, and also clone on return so the accessor does not expose the internal array. For `List<String>`, `List.copyOf` in a compact constructor is usually enough because the list is unmodifiable and `String` is immutable; `Collections.unmodifiableList(source)` is only a view and does not take a snapshot.

These measures depend on element types and ownership contracts. `List.copyOf(List<MutableItem>)` still allows mutating each item via an alias; multi-dimensional arrays require examining every level. If array content comparison is required, `equals` and `hashCode` must be synchronized, because generated equality only compares array identity. The following lesson on canonical constructors and accessors walks through step-by-step implementation.

## 6. Complete Java 17+ Example

The following example illustrates three scenarios: a record keeping the original `List`; a record taking a `List<String>` snapshot; a record taking a `List` snapshot yet holding mutable elements; and a cloned array where default `equals` still compares array references.

Create the file **`RecordShallowDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public class RecordShallowDemo {

    record LooseProfile(String user, List<String> roles) {}

    record SafeProfile(String user, List<String> roles) {
        public SafeProfile {
            Objects.requireNonNull(user, "user");
            roles = List.copyOf(roles);
        }
    }

    static final class Tag {
        private String label;

        Tag(String label) {
            this.label = label;
        }

        void rename(String newLabel) {
            label = newLabel;
        }

        String label() {
            return label;
        }
    }

    record Holder(List<Tag> tags) {
        public Holder {
            tags = List.copyOf(tags);
        }
    }

    record ByteData(byte[] bytes) {
        public ByteData {
            bytes = bytes.clone();
        }

        @Override
        public byte[] bytes() {
            return bytes.clone();
        }
    }

    public static void main(String[] args) {
        List<String> source =
                new ArrayList<>(List.of("reader"));

        LooseProfile loose = new LooseProfile("An", source);
        SafeProfile safe = new SafeProfile("An", source);

        System.out.println("loose aliases source: "
                + (loose.roles() == source));
        System.out.println("safe aliases source: "
                + (safe.roles() == source));

        Set<LooseProfile> indexed = new HashSet<>();
        indexed.add(loose);
        int before = loose.hashCode();
        int safeBefore = safe.hashCode();

        source.add("admin");

        System.out.println("loose roles: " + loose.roles());
        System.out.println("safe roles: " + safe.roles());
        System.out.println("loose hash changed: "
                + (before != loose.hashCode()));
        System.out.println("safe hash unchanged: "
                + (safeBefore == safe.hashCode()));

        try {
            safe.roles().add("editor");
        } catch (UnsupportedOperationException ex) {
            System.out.println("safe roles are unmodifiable");
        }

        Tag tag = new Tag("draft");
        List<Tag> originals = new ArrayList<>(List.of(tag));
        Holder holder = new Holder(originals);

        originals.clear();
        System.out.println("holder count: "
                + holder.tags().size());

        tag.rename("published");
        System.out.println("tag inside holder: "
                + holder.tags().get(0).label());

        byte[] input = {1, 2};
        ByteData left = new ByteData(input);
        ByteData right = new ByteData(new byte[] {1, 2});

        input[0] = 9;
        System.out.println("array copy protected: "
                + (left.bytes()[0] == 1));
        System.out.println("same byte contents: "
                + Arrays.equals(left.bytes(), right.bytes()));
        System.out.println("record equality for arrays: "
                + left.equals(right));
    }
}
```

Run with JDK 17 or later:

```bash
javac RecordShallowDemo.java
java RecordShallowDemo
```

**Output:**

```text
loose aliases source: true
safe aliases source: false
loose roles: [reader, admin]
safe roles: [reader]
loose hash changed: true
safe hash unchanged: true
safe roles are unmodifiable
holder count: 1
tag inside holder: published
array copy protected: true
same byte contents: true
record equality for arrays: false
```

### Step-by-Step Explanation

1. `loose.roles() == source` is `true` because the record keeps the exact list reference. `safe.roles() == source` is `false` because `List.copyOf` creates a snapshot from the original `ArrayList`.
2. After `source.add("admin")`, `loose`'s list gains `"admin"`. `safe` still has only `"reader"`.
3. `loose.hashCode()` changes because `List.hashCode()` depends on contents. With `safe`, the `List<String>` snapshot does not change so its hash stays stable.
4. `safe.roles().add("editor")` throws `UnsupportedOperationException`; the program catches the exception and prints the message.
5. `Holder` copied the `Tag` list so `originals.clear()` does not remove the element inside `holder`. However, both still hold **the exact same `Tag` object**; hence `tag.rename("published")` changes the tag name inside `holder`.
6. `ByteData` clones the array in both the constructor and accessor, so editing `input[0]` externally does not alter internal data.
7. `Arrays.equals(left.bytes(), right.bytes())` is `true` because the bytes match. However, `left.equals(right)` is `false` because by default the record compares the two `byte[]` components by the identity of two distinct arrays.

The example uses `HashSet` to illustrate a key with a mutating hash; it **does not depend** on `contains` always returning `false` across every JVM or hash table configuration. The risk is that a changing hash can break accurate lookup once the object is already inside a hash collection.

## 7. If a Truly Deeply Immutable Record Is Needed

One strategy you can apply:

1. **Choose immutable components from the start:** prefer `String`, primitives, enums, `BigInteger`, `BigDecimal`, and verified immutable value objects.
2. **Use snapshots for collections:** `List.copyOf`, `Set.copyOf`, `Map.copyOf` if those choices match your null policy, ordering, and data semantics.
3. **Check nested elements as well:** if elements are mutable, transform them into immutable records/value objects before putting them into the collection, or perform type-appropriate defensive copying.
4. **Close leak paths through accessors:** do not directly return internal arrays or mutable objects if callers are not allowed to mutate them.
5. **Keep the equality contract stable:** components used in `equals`/`hashCode` should not change when the record serves as a key or set element.
6. **Be explicit about null policies and validation:** `List.copyOf` rejects nulls; specify clearly whether missing data is allowed.
7. **Write tests for input and output aliases:** mutate original data after creation, attempt to mutate accessor return values, and mutate nested elements to verify the actual scope of immutability.

Example with mutable elements:

```java
record MutableAddress(StringBuilder street) {}

record AddressValue(String street) {}

record Person(String name, List<AddressValue> addresses) {
    public Person {
        addresses = List.copyOf(addresses);
    }
}
```

This is an illustrative declaration snippet requiring `import java.util.List;`. `MutableAddress` is not deeply immutable because `StringBuilder` can be modified. Conversely, `AddressValue` holds only a `String`, and `Person` snapshots a list of `AddressValue`s, so **within the scope of the defined components and with no other mutable state**, they form an immutable value graph.

Do not call something deeply immutable merely because a class has the `record` keyword or because an accessor returns an "unmodifiable" collection; examine **the contained objects**.

## 8. Practical Guidelines and Common Mistakes

| Wrong or Incomplete Practice | Problem | How to Fix |
| --- | --- | --- |
| Using `record User(List<String> roles) {}` and assuming it is immutable | Exposes the `ArrayList` reference via constructor and accessor | Use a snapshot in the canonical constructor if immutable values are needed. |
| Relying solely on `private final` for reference variables | Does not lock contents of `List`, `Map`, arrays, or mutable objects | Defensively copy and check immutability of each component. |
| Using `Collections.unmodifiableList(source)` directly | Only blocks mutation through the view; editing `source` still affects it | Use `List.copyOf` when a structural snapshot is desired. |
| Using `new ArrayList<>(source)` and returning it via accessor | The copy can still be mutated via the accessor | Return an unmodifiable collection or a defensive copy. |
| Using `List.copyOf(List<MutableItem>)` and calling it deeply immutable | Elements still hold mutable references | Convert each element to an immutable value or deep-copy as required. |
| Cloning an array on input but returning the array directly | External callers can mutate the internal array via the accessor | Clone both on input and on output. |
| Cloning an array and expecting `record.equals` to compare contents | Arrays do not override `equals` by contents | Manually define array-based equality/hash or use an appropriate value-type component. |
| Putting a record holding a mutable `ArrayList` as a `HashMap` key | Hash changes after insertion can break lookup | Design an immutable snapshot before using as a key. |
| Assuming a record's `final` prevents all side effects | Methods can still call mutators on referenced objects, write logs, or affect other systems | Distinguish internal record state, references, and external side effects. |

### When Is a Record Allowed to Have a Mutable Component?

Not every record is required to be deeply immutable. Some APIs intentionally wrap a resource or a state object to pass multiple values concisely. This can be valid if ownership conventions and data lifecycles are clearly defined.

Nevertheless, default records are designed around **component values**. If components change over time, seriously evaluate the consequences for `equals()`, `hashCode()`, `toString()`, thread safety, data serialization, and using the object as a cache key.

**Specifically:** `final` does not create thread-safety on its own. A mutable `List` component may be read/written concurrently by multiple threads; records do not replace synchronization rules, ownership, or deep immutability.

## 9. Self-Check

**Question 1.** A record has a component field `private final List<String> roles`. What is guaranteed?

**Answer:** The field reference is initialized and cannot be reassigned afterward. The list contents can still change if the list object is mutable and a reference to mutate it remains accessible.

**Question 2.** Why is `List.copyOf(source)` different from `Collections.unmodifiableList(source)`?

**Answer:** `List.copyOf` provides an unmodifiable snapshot of the list structure from a mutable input; `Collections.unmodifiableList` is an unmodifiable view that can still reflect modifications made to the underlying list.

**Question 3.** Does `List.copyOf` make a record containing `List<StringBuilder>` deeply immutable?

**Answer:** No. The list does not allow adding/removing elements via its API, yet the `StringBuilder`s inside can still be appended to or otherwise mutated.

**Question 4.** Why can a record containing a mutable `List` cause trouble when used as a `HashMap` key?

**Answer:** Records generate `hashCode()` from their components. For `List`, the hash changes with contents; mutating the list after inserting the key into the map can cause lookups in the old bucket to fail.

**Question 5.** Will two records holding two distinct `byte[]` arrays with identical bytes be equal by default via `equals()`?

**Answer:** No. Arrays default to comparing references, not all elements. If content comparison is required, a different equality/hash rule is needed.

**Question 6.** To make a record store an array such that external code cannot mutate internal data, what must be done?

**Answer:** Clone the array in the constructor to isolate input and clone again in the accessor so the internal array is not exposed. If content equality is needed, design appropriate `equals`/`hashCode` manually.

**Key Takeaway:** Java records fix **component references** and provide a convenient value contract, yet **they do not automatically make referenced objects deeply immutable**. When true immutability is needed, control inputs, nested objects, accessors, and the `equals()`/`hashCode()` relation.