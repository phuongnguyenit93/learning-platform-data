# Impact of Mutable Elements on Collection equals and hashCode

A list can retain the same list object, the same number of elements, and the exact same element references, while its `equals` or `hashCode` result still changes. The cause lies in the element objects: collections with content-based equality typically rely on the equality and hash codes of the objects they contain.

This matters when using a collection as a map key, an element in a hash set, a snapshot for change comparison, or a component of a value object. Merely wrapping a collection to make it unmodifiable does not necessarily make its value stable.

This article uses Java 17 and focuses on the dependency from mutable elements to the equality value and hash code of the containing structure. Short Java snippets only illustrate the mechanisms. The complete program in the experimental section includes compilation commands and standard output.

## 1. First, Distinguish Three Levels of Change

Suppose `labels` is an `ArrayList<MutableLabel>` with a single element.

Consider three different operations:

```java
labels.add(new MutableLabel("C"));
labels.set(0, new MutableLabel("B"));
labels.get(0).rename("B");
```

- `add` appends an element, changing the list's structure.
- `set` replaces the element associated with an existing position.
- `rename` mutates the internal state of the object already referenced by the list.

This article focuses primarily on the last operation. The list itself might not receive any mutating call, yet the content used during value comparison has changed.

Diagram:

```text
Before:
    list ----> index 0 ----> MutableLabel, text = "A"

After rename:
    same list -> same index 0 -> same MutableLabel, text = "B"
```

If `MutableLabel.equals` and `hashCode` depend on `text`, the data used by the list's operations changes accordingly.

We need to separate two questions:

1. Did the collection change structurally through its API?
2. Are the collection's equality value and hash code still the same as before?

An answer of "no" to the first question does not imply an answer of "yes" to the second.

## 2. What Do equals and hashCode of a Containing Structure Depend On?

Not every `Collection` defines equality in the same way. Before analyzing mutability, you must know the specific contract.

| Common Structure Type | Equality Depends On | Hash Code Depends On |
| --- | --- | --- |
| `List` | Same sequence of elements in order | Hash codes of elements at corresponding positions in the sequence |
| `Set` | Same members according to the set contract | Hash codes of the members |
| `Map` | Same key–value mappings | Hash codes of the entries, including both keys and values |
| Structures using only identity equality | The instance itself | Identity rules or class contract |
| Other specialized structures | Must consult the specific contract | Must consult the specific contract |

Do not apply the behavior of `List.equals` to every queue or deque. For example, a class might continue to use default identity equality instead of comparing content.

Therefore, the accurate statement is: **when a structure's equality or hashing contract depends on element state, mutating the relevant state of an element can propagate to the containing structure**. The [Java 17 Collection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html) documentation also distinguishes the modifiability of a collection from the mutability of its contained objects.

## 3. List: Unchanged Size, Yet the Value Can Change

### 3.1. Order-Based and Element-Wise Equality

Two lists are equal when they have the same size and corresponding pairs of elements are equal according to the list contract.

Suppose:

```text
current   = [MutableLabel("A")]
baseline  = [MutableLabel("A")]
```

The two elements are independent objects, but the class defines equality based on the `text` field. Initially, the two lists are equal.

After mutating only the element in `current` to `"B"`:

```text
current   = [MutableLabel("B")]
baseline  = [MutableLabel("A")]
```

The two lists are no longer equal. No elements were added or removed.

The result reflects the current state, not the historical value at the time the list was created.

### 3.2. Sequence Hash Code Mechanism

The `List.hashCode` contract uses an ordered accumulation, which can be expressed as:

```java
int hash = 1;
for (E element : list) {
    hash = 31 * hash + (element == null ? 0 : element.hashCode());
}
```

This is Java-style pseudocode describing the formula; it requires generic and list context if placed inside a class.

For a single-element list where the element's hash equals the hash code of the string `"A"`:

```text
initial hash = 31 × 1 + 65 = 96
```

If the element switches to using the hash of `"B"`:

```text
hash after modification = 31 × 1 + 66 = 97
```

This specific example changes the hash code. However, do not conclude that every value change alters the hash: hash collisions can still occur.

The formula and equality relationship are specified in [Java 17 List.equals and List.hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#hashCode()).

### 3.3. Changes Can Also Affect contains and indexOf

If an element's `equals` behavior changes, a query for the old value may no longer find a match, while a query for the new value may succeed.

For a regular list, this can be a valid change to current data. A list does not rely on an element's hash table bucket to locate its position the way a hash set does.

Even so, the application must still determine whether mutating that state is permissible. "The structure still operates according to its contract" does not prove the operation is appropriate for business logic.

## 4. Set: Distinguishing the Set's Hash from Member Validity

### 4.1. Set Hash Code Depends on Member Hash Codes

The `Set.hashCode` contract sums the hash codes of its elements, with a corresponding rule for `null` if permitted.

Because addition is order-independent, two equal sets have the same hash code even if their iteration orders differ. However, if a member's hash code changes, the hash code computed for the entire set can change.

That is a value-level dependency. There is an even more serious issue: the element is still residing inside the very structure that uses those properties to manage membership.

### 4.2. Mutating an Element Inside a HashSet Can Break Lookup Assumptions

A hash set uses equality and hash codes to organize elements. When an element is added, its lookup location is tied to its information at that moment.

If a setter later modifies a field participating in `equals` or `hashCode`, the set does not automatically intercept the setter and relocate the element to match its new state.

The `Set` contract does not specify the behavior when an object currently belonging to a set is modified in a manner that affects equality comparisons. Do not assert a mandatory output such as "`contains` is guaranteed to always return false" for every scenario where this precondition is broken. It may manifest as unexpected lookup, removal, or deduplication behavior.

Key boundaries to remember:

- The element may still appear during iteration.
- That does not prove value-based lookup remains valid.
- Recomputing the set's hash code does not repair the element's internal bucket placement.
- An unchanged hash in a specific case is still insufficient to prove safety if the equality relationship has changed.

See [Java 17 Set: mutable elements and the hashCode contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html).

### 4.3. Modifying Fields Not Used in Equality May Have No Effect

An `Item` with an immutable `id` and a mutable `label`, where `equals` and `hashCode` depend solely on `id`, can change its label without altering its equality relationship or hash code.

Therefore, having a setter on an object does not mean every collection containing it will necessarily change its hash.

You must ask **which field changes and which methods depend on that field**. If a comparator, business logic, or another index uses the label, those must still be evaluated separately.

## 5. Map: Mutable Values Also Affect the Whole Map's Hash

### 5.1. A Map's Hash Does Not Depend Only on Keys

For a standard map, `hashCode` is computed from its entries. Each entry gets a contribution from both its key and its value, commonly expressed by the entry contract as the XOR of the key's hash code and the value's hash code; the whole map's hash is the sum of the entry contributions.

Therefore:

```java
Map<String, MutableLabel> labels = new HashMap<>();
```

can have stable keys while the hash of `labels` itself still changes when a value object changes its hash code.

### 5.2. Two Maps Can Cease to Be Equal Even When Their Key Sets Are Unchanged

Suppose two maps have the same key `"key"`, associated with two independent values that are currently equal.

Mutating the value in one map in a way that alters `equals` can cause the two maps to no longer be equal. Both still contain the exact same key, and `size()` remains unchanged.

Do not use "the key set is unchanged" as proof that the map as a whole has not changed in value.

### 5.3. Distinguishing Value Mutation from Key Mutation

If a value changes, looking up the mapping by a stable string key in a `HashMap` can still work properly. What changes is the value of the mapping, along with the equality and hash code of the entire map.

If a key object is mutated in a part that affects equality or hashing, locating the mapping itself can lose its validity precondition.

The [Java 17 Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html) documentation specifically warns against mutable keys that affect equality. These two cases must be analyzed separately.

## 6. Does a Hash Changing Over Time Violate the Object Contract?

Not necessarily.

The `Object.hashCode` contract requires consistency within a single execution as long as no information used in `equals` comparisons is modified. It does not require every object's hash to be a constant regardless of state.

If an element defines equality based on a `text` field and that field is allowed to change, the element's hash code may change accordingly. A list containing it may also change its hash code when the state used to compare the list changes.

Problems arise when the application simultaneously imposes a stronger requirement: an object currently being used as a key or indexed member must maintain stable lookup criteria.

Distinguish these scenarios:

| Scenario | Implication |
| --- | --- |
| A list holding current data changes equality after an element mutates | Can be valid stateful behavior |
| The list's hash changes alongside equality information | Does not by itself violate the hashCode contract |
| That list is currently used as a key in a HashMap and gets mutated | Can break the outer map's assumptions |
| Two equal objects have different hashes in the same state | Violates the equals–hashCode contract |
| Two different states produce the same hash | May simply be a valid hash collision |

Do not try to fix the issue by forcing `hashCode` to always return a cached number while `equals` continues to use the current state without an appropriate design. The hash code must remain consistent with the chosen equality relationship.

See [Java 17 Object.hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#hashCode()).

## 7. Propagation Effects Across Nested Structures

A dependency can travel through multiple layers:

```text
mutable property of an object
        |
        v
equals/hashCode of the element
        |
        v
equals/hashCode of the inner list
        |
        v
equals/hashCode of the record or object containing the list
        |
        v
equals/hashCode of the outer collection
```

### 7.1. List Inside a List

If an outer list contains an inner list, and the inner list's equality changes after adding an element or mutating relevant state, the outer list can also change its comparison result or hash.

No call to `outer.add`, `outer.set`, or `outer.remove` is required.

### 7.2. Record Containing a List

For example:

```java
record TagGroup(List<String> tags) {
}
```

A record's component reference cannot be reassigned normally after construction. However, the list object that `tags` points to can still mutate.

The generated equality and hash code of a record depend on the current value of its list component. Modifying the list's contents can alter the record's equality and hash; any collection containing the record can in turn be affected.

A `record` does not automatically copy or deeply freeze its component objects. See [Java 17 Record](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html).

### 7.3. Map as a Value or Component of a Key

A key object containing a map field can have a hash that depends even on mutable values deep inside that map.

A top-level variable being `final` or a field lacking a setter is not sufficient to prove that the entire data graph used in equality is stable.

You must trace the exact data branches that `equals` and `hashCode` actually inspect.

### 7.4. Do Not Create Arbitrary Self-Referential Relationships

A collection containing itself, or cyclic references across multiple collections, can cause `equals`, `hashCode`, or recursive traversals to no longer be well-defined by the contract, or fail to terminate as expected.

Do not assume that the ability to store arbitrary references means content-equality algorithms will automatically handle arbitrary cyclic graphs.

## 8. Collections as Keys or Members of an Outer Hash Structure

### 8.1. Indirect Risk

A dangerous illustrative snippet:

```java
List<MutableLabel> key = new ArrayList<>(List.of(label));
Map<List<MutableLabel>, String> index = new HashMap<>();
index.put(key, "saved");

label.rename("changed");
```

The last line calls no method on `key` or `index`. Yet if it alters the equality and hash code of `label`, it can change the hash of the list serving as the key.

The outer map still organizes the mapping according to the state used previously; it does not automatically re-index when an object deep inside a key is mutated.

This is why "do not modify a list used as a key" must also include not modifying internal data that affects that list's equality.

### 8.2. Map as an Element of a HashSet

A similar situation occurs when a map is placed into a `HashSet`, and a value inside the map is subsequently mutated in a way that changes its hash.

The inner map's keys may be completely stable, yet the hash of the inner map itself has changed; the outer set is where the lookup risk arises.

### 8.3. Do Not Assert That Every Call Is Guaranteed to Produce the Same Failure

Once the stability precondition of a key or member is violated, do not build rules around an incidental outcome such as:

- `contains` will definitely return false.
- Re-adding will definitely increase the size.
- A single removal will definitely repair every state.

The actual outcome depends on hash codes, collisions, internal bucket structure, and specific state. What needs to be demonstrated is that the contract precondition was broken, not that a particular output must appear across every JDK.

The program in this article only executes mutations that respect the preconditions of hash structures, and illustrates the workflow of removing before mutating.

## 9. How Far Do Unmodifiable Views, Copies, and final Protect You?

### 9.1. final Only Fixes the Reference

`final List<MutableLabel> labels` prevents reassigning the variable `labels`; it does not lock the list structure or the fields of its elements.

### 9.2. An Unmodifiable View Still Sees the Backing Source

`Collections.unmodifiableList(source)` blocks mutating operations through the wrapper. The backing source can still be modified through another reference, and the elements themselves can still be mutated.

Equality or hash values observed through the view can change along with the underlying data.

### 9.3. A Shallow Copy Separates Structure, Not Elements

With:

```java
List<MutableLabel> copy = new ArrayList<>(source);
```

adding or replacing elements in the source does not modify the structure of `copy`. However, mutating an object referenced by both lists can cause the equality and hash of both to change together.

This creates a trap when detecting changes:

```text
create shallow copy as baseline
mutate shared element
compare source against baseline
result is still equal
```

Not because the data hasn't changed, but because both sides are looking at the new state of the same shared object.

### 9.4. List.copyOf Is Not a Deep Value Snapshot

`List.copyOf(source)` produces an unmodifiable list containing the elements of the source at the time of the call. Structural changes to the source are not reflected as in a live view.

However, the element objects themselves can still be shared references. If an element is mutable and its equality is state-based, the result of `copyOf` can still change its observable value.

Consequently, using `List.copyOf` does not automatically make a collection safe to use as a hash key if elements participating in equality remain mutable.

### 9.5. Deep Immutability Must Be Designed

A snapshot can be constructed from immutable value objects, or by extracting the specific immutable attributes that need to be preserved.

There is no need to mechanically copy every field in the system. You need to copy the exact portion of data that the snapshot must represent, while ensuring that portion cannot be altered later through aliases.

For a label stored as a `String`, capturing the current string value into a new list may suffice for a label snapshot. For more deeply nested structures, each layer must be inspected.

## 10. Mutable Elements Do Not Always Change Equality or Hash

### 10.1. The Modified Field Does Not Participate in Equality

If equality and hash depend solely on a stable `id`, changing `displayName` may not alter the collection's result.

You must evaluate the exact contract. A change in `toString()` or display output does not prove that equality has changed.

### 10.2. Elements Using Identity Equality

A class that does not override state-based equality retains default identity-based `equals` and `hashCode`. Modifying an ordinary field does not turn it into a different object instance.

For example, objects whose contents change but do not define content-based `equals` are not automatically compared by collections using their new contents.

Arrays likewise do not provide content equality through `Object.equals`. Replacing an element inside a referenced array does not act like changing a deep value in a list's equality formula if the list only inspects the array via identity equality.

If an application requires deep content comparison, it must use or design an appropriate comparison mechanism.

### 10.3. Hash Collisions Exist

Even when state-based equality changes, the hash code may collide between two states.

Therefore:

```text
hash before == hash after
```

does not prove that the object or collection did not change.

The converse direction is more useful: if the same contract-compliant hash computation on two states yields different results, they cannot be considered equal under that same contract in those states. Even so, do not use a hash code as a complete historical record.

## 11. Safe Design Strategies

### 11.1. Use Stable Identifiers for Lookup Structures

Instead of using an entire changing collection as a key, you can use an immutable identifier with business meaning.

For example, a map can manage shopping carts by `cartId`, while the list of items is the value. Changes to the cart do not force a change in the key's hash.

Choosing an identifier must match requirements: an identifier does not replace content comparison when the true goal is comparing two value snapshots.

### 11.2. Use Immutable Values for Content-Based Keys

If a key genuinely needs to be content-based, create an immutable representation of the content to be indexed.

For nested data structures, wrapping only the outer layer is not enough. You must ensure that every component participating in equality and hashing remains stable for as long as the key is in use.

### 11.3. Remove from the Index Before Mutating, Then Reinsert

If updating an object used as a member or key is permitted, the workflow should be:

1. Locate and remove the object while it still holds its valid old state.
2. Verify that the removal succeeded.
3. Mutate the state.
4. Reinsert the object into all relevant indexes.
5. Handle cases where the new state collides with an already existing value.

Do not mutate first and then attempt to remove using the new state. Once mutated, the lookup operation required for removal may no longer be reliable under the contract.

If the object resides in multiple indexes or is accessed by multiple threads, the entire sequence must be coordinated consistently. Removing it from one place is insufficient if another structure still uses it as a key.

### 11.4. Create a Meaningful Baseline

To detect changes, a baseline must represent the prior state rather than continuing to point to elements that are being mutated.

You can store:

- A snapshot of the value attributes to be compared.
- Immutable value objects.
- An application-managed version number or dirty flag.
- An element copy tailored to the data model.

Do not rely solely on `hashCode` as a collision-free fingerprint or a substitute for a full snapshot. A collection's hash is an integer serving the hashing contract, not a cryptographic checksum.

### 11.5. Do Not Cache Hash Codes Arbitrarily

Caching a hash computed once can work well for properly designed immutable objects. For data that continues to mutate while equality uses the new state, retaining an old hash can cause equal objects to have different hash codes.

Caching requires either immutability or an invalidation mechanism that guarantees consistency with equality—not merely hiding the symptom of a changing hash.

## 12. Complete Java Program

The program tests valid mutations: a mutable element inside a list, a mutable value inside a map with a stable key, a descriptive field excluded from equality, and an index update sequence that removes before mutating.

Save to `MutableElementEqualityDemo.java`:

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class MutableElementEqualityDemo {
    static final class MutableLabel {
        private String text;

        MutableLabel(String text) {
            this.text = Objects.requireNonNull(text);
        }

        String text() {
            return text;
        }

        void rename(String text) {
            this.text = Objects.requireNonNull(text);
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof MutableLabel that
                    && text.equals(that.text);
        }

        @Override
        public int hashCode() {
            return text.hashCode();
        }

        @Override
        public String toString() {
            return text;
        }
    }

    static final class Item {
        private final String id;
        private String label;

        Item(String id, String label) {
            this.id = Objects.requireNonNull(id);
            this.label = Objects.requireNonNull(label);
        }

        void rename(String label) {
            this.label = Objects.requireNonNull(label);
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof Item that && id.equals(that.id);
        }

        @Override
        public int hashCode() {
            return id.hashCode();
        }
    }

    record TagGroup(List<String> tags) {
    }

    public static void main(String[] args) {
        MutableLabel label = new MutableLabel("A");
        List<MutableLabel> current = new ArrayList<>(List.of(label));
        List<MutableLabel> independent =
                List.of(new MutableLabel("A"));
        List<MutableLabel> shallow = new ArrayList<>(current);
        List<MutableLabel> unmodifiable = List.copyOf(current);
        List<String> frozenValues = List.of(label.text());

        int initialHash = current.hashCode();
        System.out.println("before equals: " + current.equals(independent));
        System.out.println("before list hash: " + initialHash);

        label.rename("B");

        System.out.println("same list size: " + (current.size() == 1));
        System.out.println("after equals: " + current.equals(independent));
        System.out.println("after list hash: " + current.hashCode());
        System.out.println("shallow copy follows: " + shallow);
        System.out.println("unmodifiable copy follows: " + unmodifiable);
        System.out.println("shallow equals current: " + shallow.equals(current));
        System.out.println("frozen values: " + frozenValues);

        MutableLabel value = new MutableLabel("X");
        Map<String, MutableLabel> map = new HashMap<>();
        map.put("key", value);
        Map<String, MutableLabel> expectedMap =
                Map.of("key", new MutableLabel("X"));
        int mapHash = map.hashCode();

        value.rename("Y");
        System.out.println("map key still present: " + map.containsKey("key"));
        System.out.println("map equals baseline: " + map.equals(expectedMap));
        System.out.println("map hash changed: " + (mapHash != map.hashCode()));

        Item item = new Item("P1", "Old label");
        Set<Item> items = new HashSet<>(List.of(item));
        Set<Item> expectedItems = Set.of(new Item("P1", "Other label"));
        int setHash = items.hashCode();
        item.rename("New label");
        System.out.println("ignored field keeps set equals: "
                + items.equals(expectedItems));
        System.out.println("ignored field keeps set hash: "
                + (setHash == items.hashCode()));

        List<String> tags = new ArrayList<>(List.of("A"));
        TagGroup group = new TagGroup(tags);
        TagGroup expectedGroup = new TagGroup(List.of("A"));
        List<TagGroup> outer = List.of(group);
        List<TagGroup> expectedOuter = List.of(expectedGroup);
        int outerHash = outer.hashCode();
        tags.set(0, "B");
        System.out.println("nested record equals baseline: "
                + group.equals(expectedGroup));
        System.out.println("outer list equals baseline: "
                + outer.equals(expectedOuter));
        System.out.println("outer list hash changed: "
                + (outerHash != outer.hashCode()));

        List<String> key = new ArrayList<>(List.of("A"));
        Set<List<String>> index = new HashSet<>();
        index.add(key);
        boolean removed = index.remove(key);
        key.add("B");
        boolean addedAgain = index.add(key);
        System.out.println("remove before mutation: " + removed);
        System.out.println("reinsert after mutation: " + addedAgain);
        System.out.println("index contains new value: "
                + index.contains(List.of("A", "B")));
    }
}
```

Compile and run:

```shell
javac --release 17 MutableElementEqualityDemo.java
java MutableElementEqualityDemo
```

Standard output:

```text
before equals: true
before list hash: 96
same list size: true
after equals: false
after list hash: 97
shallow copy follows: [B]
unmodifiable copy follows: [B]
shallow equals current: true
frozen values: [A]
map key still present: true
map equals baseline: false
map hash changed: true
ignored field keeps set equals: true
ignored field keeps set hash: true
nested record equals baseline: false
outer list equals baseline: false
outer list hash changed: true
remove before mutation: true
reinsert after mutation: true
index contains new value: true
```

### 12.1. List Retains Size While Its Value Changes

`MutableLabel` computes equality and hash from `text`. When changed from `A` to `B`, `current` still has one element but is no longer equal to the independent baseline.

The hash values 96 and 97 come from this specific data combined with the list formula, not as proof that every mutation always alters the hash.

### 12.2. A Shallow Copy Causes the Baseline to Drift with the Source

`shallow` and `unmodifiable` hold the exact same `MutableLabel` object, so they print `[B]`. `shallow.equals(current)` remains `true`.

`frozenValues` holds the label string `"A"` captured before the setter ran. `String` is immutable and the setter assigned a new string reference to the object, so this snapshot remains `[A]`.

### 12.3. Map Has a Stable Key, Yet the Whole Map's Hash Changes

The `MutableLabel` value changes from `X` to `Y`. The map can still find the key `"key"`, but it is no longer equal to the baseline map with an independent value `X`; the hash of the whole map also changes for this data.

This is not a key lookup bug in the inner map. It becomes a different risk if this map itself is being used as a key or member in an outer structure.

### 12.4. Fields Outside the Equality Criteria Do Not Alter the Set

`Item` uses only its immutable `id` in equality and hashing. Changing the label does not affect those two methods.

Consequently, this test does not violate the stability requirement for hash set elements. It illustrates why you must analyze dependency relationships rather than concluding that any setter changes the hash.

### 12.5. A Record Does Not Lock Its Component List

`TagGroup` holds a reference to `tags`. `tags.set(0, "B")` changes the equality of the list, which in turn changes the equality of the record and the outer list containing the record.

In this program, these objects are not residing inside a hash index that requires stable values, so observing state-based equality changes is completely valid.

### 12.6. Removing Before Mutation Keeps the Index Valid

The final section removes `key` from the set before adding `B` to the list. It then reinserts the list and queries using another list with identical content.

This single-threaded example only demonstrates the proper order of operations. It does not address multi-index transactions or concurrent access.

## 13. An Iterator Is Not a Monitor for Every Value Change

An element's setter typically does not update the collection's structural modification counter. There is no reason to expect a `ConcurrentModificationException` to be thrown merely because an element's hash changed.

From this:

- An iterator continuing to run does not prove the collection's value is unchanged.
- `size()` remaining constant does not prove the hash is stable.
- A collection supporting concurrent access does not automatically make its internal elements thread-safe.
- A comparison operation running while relevant data is being mutated requires proper synchronization or a dedicated snapshot.

If one thread computes a hash while another thread mutates fields used for equality, the application may fail to observe a consistent business state. Do not use equality or hash codes as a synchronization mechanism.

## 14. How to Audit a Real-World Data Structure

When a collection contains mutable elements, walk through this sequence of questions:

1. How does the specific collection type define equality and hash code?
2. Which elements, keys, or values have their equality or hash used by its methods?
3. Which properties of those objects can change?
4. Are the modified properties outside the equality criteria?
5. Are there lists, maps, records, or container objects nested across multiple levels?
6. Do aliases allow mutations from another component?
7. Is the collection merely holding current data, or is it serving as a key or member in an index?
8. Is the comparison baseline truly independent with respect to the state that needs to be preserved?
9. Is a read-only wrapper being confused with deep immutability?
10. Are mutations properly re-indexed across every related index?
11. Could multiple threads compromise the consistency of the observation point?
12. Are tests relying on unguaranteed behavior after a contract has already been broken?

The goal is to trace the propagation path of changes, rather than looking only at the declared type or an isolated setter call.

## 15. Self-Verification Exercises

### Exercise 1: List Hash Changes Due to an Element

Create two independent lists, each containing a label `"A"`. The label class uses string content for equality and hashing.

Change the label on one side to `"B"`. Check the size, element reference, equality between the two lists, and the hash before and after.

Explain why the hash change does not require the list to receive an add or remove call.

### Exercise 2: Shared Baseline

Create a baseline using `new ArrayList<>(source)`, then mutate a shared element.

Demonstrate that comparing the two lists can still return `true` even though the data has changed relative to its initial state. Then replace the baseline with a snapshot of the immutable values that need to be preserved.

### Exercise 3: Map Value vs. Map Key

Design two scenarios:

- A value changes while its string key remains stable.
- A mutable object is used as a key and its equality field is modified.

In the first scenario, you can observe the whole map's equality or hash changing while key lookup still works. The second scenario must be identified as a violation of the key stability precondition; do not require a fixed error output across all JDKs.

### Exercise 4: Which Fields Actually Matter?

A class has `id`, `displayName`, and `lastViewedAt`. Choose `id` as the sole criterion for equality and hashing.

Verify whether changing the other two fields affects the equality or hash of a list or set containing it. Then explain why a change in display representation is not proof that equality has changed.

### Exercise 5: Collection Nested Inside a Record

Create a record containing a list of strings, then place the record inside an outer list. Replace a string using `set` on the component list.

Trace each layer of dependency. Redesign the constructor or data model to produce an appropriate immutable snapshot, rather than just a final component reference.

### Exercise 6: Updating an Indexed Member

An object needs to change its value while residing in multiple hash sets or maps. Outline the workflow for removing it from all relevant indexes, mutating it, checking for conflicts, and reinserting it.

Describe how to prevent readers from observing an intermediate state if business requirements demand consistency.

## 16. Conclusions to Avoid

- "If the size doesn't change, equals and hashCode don't change."
- "If the elements keep the same references, the collection's value remains the same."
- "A hash changing with state always violates Object.hashCode."
- "An unchanged hash proves the data hasn't changed."
- "List.copyOf creates a deep copy."
- "A record has final components, so its equality is always immutable."
- "As long as you don't call set or add on a list used as a key, it is completely safe."
- "A map's hash depends only on its keys."
- "Modifying any field of an element always changes the collection's hash."
- "No ConcurrentModificationException means the index is still valid."

The principle to uphold is tracking all data participating in equality and hashing, including objects nested deep inside. Values can change validly over time; when a value is used for lookup in another structure, the application must either guarantee stability or update the index through a sound procedure.
