# Order-Dependent equals and hashCode of List

A `List` represents **a sequence**. Therefore, when asking whether two lists are equal, Java considers both the elements and their positions, rather than just asking "what values do they contain?".

For example:

~~~text
[A, B] and [A, B] -> can be equal, even if they are two different List objects
[A, B] and [B, A] -> not equal
[A, A, B] and [A, B] -> not equal
~~~

The `hashCode` of a List also combines the hashes of its elements in order. However, "order-dependent" does not mean that every distinct sequence always has a different hash. A hash is an `int` value that can collide; it does not replace `equals`.

Understanding these two contracts is especially essential when testing, deduplicating sequences, using a List in a HashSet, or using a List as a HashMap key.

## 1. Three Different Levels of Comparison

| Comparison Method | Question Answered |
| --- | --- |
| `left == right` | Do both variables point to the exact same object? |
| `left.equals(right)` | Do both lists contain the same sequence of elements according to the List contract? |
| `left.hashCode() == right.hashCode()` | Are the two hash values equal? Not sufficient to conclude that the two Lists are equal. |

For example:

~~~java
// Code snippet inside a method; requires corresponding java.util imports.
List<String> first = new ArrayList<>(List.of("A", "B"));
List<String> second = new LinkedList<>(List.of("A", "B"));

System.out.println(first == second);      // false
System.out.println(first.equals(second)); // true
~~~

The two objects use different internal storage, yet both are Lists, have the same size, and hold equal values at every position.

There is no need to convert a LinkedList into an ArrayList to compare sequence content. The List contract is designed so that compliant implementations can be compared with the same semantics.

Conversely, simply seeing that two variables share the declared type `List<String>` does not prove they are equal. Their data must be checked.

## 2. The equals Contract: Same Sequence Collection Type, Same Size, Same at Every Position

In terms of content, two Lists are equal when:

1. The object being compared is also a List.
2. Both Lists have the same number of elements.
3. Corresponding pairs of elements, from start to end, are equal according to `equals`, with `null` handling.

This can be visualized as:

~~~text
left[0]   corresponds to right[0]
left[1]   corresponds to right[1]
...
left[n-1] corresponds to right[n-1]
~~~

Element comparison behaves identically to `Objects.equals(leftElement, rightElement)`.

The rules for `equals` and the ordered hash formula are specified in the [Java SE 17 List API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#equals(java.lang.Object)).

### Order Matters

~~~java
List<String> first = List.of("A", "B");
List<String> reversed = List.of("B", "A");

System.out.println(first.equals(reversed)); // false
~~~

At index `0`, A does not equal B. Having the same size and the same distinct values does not make two sequences equal.

If two occurrences with equal values are swapped, the observable sequence may still be equal. "Considering order" does not mean every internal swap operation produces a different sequence according to `equals`.

### Occurrence Count Also Matters

~~~java
List<String> first = List.of("A", "A", "B");
List<String> second = List.of("A", "B", "B");

System.out.println(first.equals(second)); // false
~~~

Both sequences contain A and B and both have size `3`, but they differ at position `1`.

Duplicate elements are not ignored when evaluating List equality. This is an important difference compared to converting the data into a Set.

## 3. Equality Across Implementations and Modifiability

The same sequence content can be equal across:

- ArrayList.
- LinkedList.
- A list from Arrays.asList.
- An unmodifiable list from List.of or List.copyOf.
- A List view with the same current content.

For example:

~~~java
List<String> mutable = new ArrayList<>(List.of("A", "B"));
List<String> unmodifiable = List.of("A", "B");

System.out.println(mutable.equals(unmodifiable)); // true
~~~

The ability to add, remove, or replace elements is not part of the List `equals` contract. The capacity of an ArrayList is also not part of the sequence value.

Do not equate "equal" with:

- Same runtime class.
- Same capacity.
- Same modifiability.
- Same memory layout.
- Same object identity.

Those characteristics may matter for another requirement, but they must not be read into a `List.equals` conclusion if that is not the chosen contract.

### A List Does Not Equal a Set Just Because They Share Elements

~~~java
List<String> sequence = List.of("A", "B");
Set<String> members = Set.of("A", "B");

System.out.println(sequence.equals(members)); // false
~~~

A List compares a sequence against another List. A Set has a different value contract. Do not use an arbitrary Collection as a substitute for a List in sequence comparisons.

## 4. Null and Element Types

### Null Is Compared by Position

If the source permits null:

~~~java
List<String> first = Arrays.asList("A", null, "B");
List<String> second = new ArrayList<>(first);
List<String> moved = Arrays.asList(null, "A", "B");

System.out.println(first.equals(second)); // true
System.out.println(first.equals(moved));  // false
~~~

Two null elements at the same position are considered equal. A null at a different position can make the sequence different.

Do not use `List.of` to create a list containing null, because that factory itself rejects null before comparison is even reached.

### Identical Display Output Is Not Enough

~~~java
List<Integer> integers = List.of(1);
List<Long> longs = List.of(1L);

System.out.println(integers);               // [1]
System.out.println(longs);                  // [1]
System.out.println(integers.equals(longs)); // false
~~~

An Integer `1` and a Long `1L` are not equal according to the `equals` methods of those wrapper types.

On the other hand, different declared generic types do not automatically make two lists unequal. For example, a `List<Object>` and a `List<String>` that actually contain equal Strings at every position can be equal. `equals` accepts an `Object` and evaluates runtime contents according to the contract; it is not decided by the generic type parameter written in source code.

### Same Content, Different Element References

Two String objects with different references but identical content can be equal. Because List uses the element's `equals`, it does not require every corresponding pair of elements to be the exact same object.

If an element class does not provide value-based `equals` semantics and instead keeps the default behavior from `Object`, two distinct instances will not be equal even if their fields look identical. A List does not introspect every field on its own to invent a new `equals` definition for its elements.

## 5. The List hashCode Formula

List combines element hashes in order using an accumulation formula:

~~~java
// Illustrative helper method inside a class; requires java.util.List and java.util.Objects imports.
static int listHash(List<?> values) {
    int hash = 1;
    for (Object value : values) {
        hash = 31 * hash + Objects.hashCode(value);
    }
    return hash;
}
~~~

`Objects.hashCode(value)` returns `0` if `value` is null; if non-null, it calls the element's `hashCode`.

Key points to remember:

- The initial value is `1`.
- Each step multiplies the previous result by `31`.
- It then adds the hash of the current element.
- Elements are traversed in the exact order of the List.

This is a contract formula, not a cryptographic hash algorithm. See [List.hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#hashCode()).

For an empty List, the loop does not run, so the hash is `1`.

### Step-by-Step Calculation with A, B

The hash of String `"A"` is `65`, and `"B"` is `66`.

~~~text
[A, B]:

h0 = 1
h1 = 31 * 1  + 65 = 96
h2 = 31 * 96 + 66 = 3042
~~~

Reversing the order:

~~~text
[B, A]:

h0 = 1
h1 = 31 * 1  + 66 = 97
h2 = 31 * 97 + 65 = 3072
~~~

Earlier elements affect subsequent multiplications, so the accumulation is not simply an order-insensitive sum of all element hashes.

### int Overflow Is Part of the Java Computation

The hash uses a 32-bit `int`. For long lists or large element hashes, multiplication and addition can wrap around the signed integer range according to standard Java integer arithmetic rules.

Do not rewrite the function using overflow-checking addition that throws an exception, or change the result to another type while still calling it the `List.hashCode` formula.

A hash value can be negative. A negative number does not mean the List or the hash function is broken.

## 6. The Mandatory Rule and What Cannot Be Inferred in Reverse

For objects that obey the `equals`/`hashCode` contract:

~~~text
left.equals(right) == true
    -> left.hashCode() == right.hashCode()
~~~

The converse does not hold:

~~~text
left.hashCode() == right.hashCode()
    -> cannot yet conclude left.equals(right)
~~~

Different hashes are enough to know two objects are not equal in their current state, assuming contracts are respected. Equal hashes only mean that `equals` must still be used to distinguish them.

Do not write:

~~~java
// Wrong if the goal is to decide whether two Lists are equal.
boolean same = left.hashCode() == right.hashCode();
~~~

Use:

~~~java
boolean same = left.equals(right);
~~~

If `left` may be null, `Objects.equals(left, right)` can be used when appropriate.

### Simple Numeric Collision

~~~text
[1, 0]:
h1 = 31 + 1 = 32
h2 = 31 * 32 + 0 = 992

[0, 31]:
h1 = 31 + 0 = 31
h2 = 31 * 31 + 31 = 992
~~~

The two Lists are not equal, yet both have the hash `992`.

### Different Orders Can Still Produce the Same Hash

The two Strings `"Aa"` and `"BB"` have the same `hashCode` under String's hash formula.

Therefore:

~~~text
["Aa", "BB"] and ["BB", "Aa"]
~~~

are not equal according to `List.equals`, yet both produce the hash `68545`.

This is not because List ignores order. The formula still accounts for position; because the input element hashes already collide, the accumulated result can also collide.

Saying "the hash depends on order" must always be paired with the qualification "it does not guarantee a unique mapping for every sequence".

## 7. List as a HashSet Element or HashMap Key

Two sequences equal by value can act as the same key:

~~~java
Map<List<String>, String> cache = new HashMap<>();
cache.put(List.of("A", "B"), "cached");

System.out.println(
        cache.get(new LinkedList<>(List.of("A", "B")))
); // cached

System.out.println(cache.get(List.of("B", "A"))); // null
~~~

Lookup does not require the same List implementation class or the same object reference as the original key.

In this example the map does not store null values, so `null` from the second lookup means no such mapping exists. In a general Map that permits null values, distinguish "key absent" from "key mapped to null" using the appropriate API when needed.

Similarly:

~~~java
Set<List<String>> sequences = new HashSet<>();

sequences.add(new ArrayList<>(List.of("A", "B")));
sequences.add(new LinkedList<>(List.of("A", "B")));
sequences.add(List.of("B", "A"));

System.out.println(sequences.size()); // 2
~~~

`HashSet` deduplicates the two equal `[A, B]` sequences into a single set member, while `[B, A]` remains a distinct member.

Do not infer from this example that `HashSet` iteration order is fixed. The code checks only the element count; it does not print or rely on the iteration order of sequences inside the set.

## 8. The Risk of Mutable List Keys

If a mutable List is used as a key and then modified, its `equals` or `hashCode` can change while the hash structure still holds bucket placement from insertion time.

~~~java
// Risky design example; do not use as a template for stable keys.
List<String> key = new ArrayList<>(List.of("A", "B"));
Map<List<String>, String> cache = new HashMap<>();

cache.put(key, "cached");
key.add("C");

// Do not rely on any specific lookup result after mutating a key like this.
~~~

There is no general guarantee for an application to rely on map behavior after a key is mutated in a way that affects `equals`. See the note on mutable keys in the [Map API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html).

Do not try to work around this by calling `get` repeatedly, or by assuming the map will automatically relocate the key to the right bucket once it notices the hash changed. Design key data to remain stable for the entire time it resides in a map or set.

### Structural Snapshot with Immutable Elements

With non-null Strings:

~~~java
List<String> input = new ArrayList<>(List.of("A", "B"));
List<String> key = List.copyOf(input);

Map<List<String>, String> cache = new HashMap<>();
cache.put(key, "cached");

input.add("C");

System.out.println(input); // [A, B, C]
System.out.println(key);   // [A, B]
System.out.println(cache.get(List.of("A", "B"))); // cached
~~~

`List.copyOf` produces an unmodifiable result that does not reflect subsequent structural changes made to `input`, unlike a view backed by a shared source. It may reuse a suitable input object; do not rely on the object identity of the returned list to verify correctness.

In this example, `String` is immutable, so both the key's structure and the element data participating in `equals`/hash are stable. `List.copyOf` rejects null elements; if the data domain allows null, choose an appropriate snapshot policy instead of passing it directly and assuming all inputs are accepted.

## 9. An Unmodifiable List Is Not Enough If Its Elements Still Mutate

Consider an element whose `equals`/`hashCode` depends on a mutable field:

~~~text
Structurally fixed List: [label]
Initial label.value: "A"
Later label.value:   "B"
~~~

Even without adding, removing, or replacing elements in the List, the element's hash has changed. By the List formula, the hash of the entire List can also change.

The complete program below illustrates this:

~~~text
List hash before: 96
List hash after:  97
~~~

That List was created with `List.of(label)`, so its structure cannot be modified. However, the `label` object inside it can still change its `value`.

Distinguish three levels:

| Level | What Is Kept Stable |
| --- | --- |
| Blocking add/remove/set through a List reference | Only restricts mutation operations through that specific object or view. |
| Structural List snapshot independent of a mutable source | The sequence of references does not track subsequent structural mutations of the source. |
| Truly stable value key | All data participating in `equals`/`hashCode` of both the List and its elements remain stable while used as a key. |

A `Collections.unmodifiableList(backing)` can still reflect changes made to `backing` if code elsewhere mutates the underlying list. It is not equivalent to a snapshot.

Even a shallow snapshot via `List.copyOf` does not deep-copy a mutable element. For domain keys, it is usually better to store explicitly chosen immutable values or identifiers rather than entire stateful objects.

## 10. Element equals/hashCode Is the Foundation

If an element class defines value-based `equals`, it must also provide a compatible `hashCode`:

~~~text
two elements are equal according to equals
    -> the hashes of the two elements must be equal
~~~

If an element violates that rule, two Lists can end up being equal while producing different hashes. A List cannot repair a broken element contract by inspecting fields on its own or inventing a new hash function.

Required properties of `equals`, such as symmetry and transitivity, must also be preserved by the elements. For instance, a class whose `equals` compares against another class in only one direction can make container comparisons confusing and contract-violating.

Not every element class needs a hand-written `equals`. Built-in value types or `record` types work well when they match the data definition. What matters is choosing clear element equality semantics and keeping `hashCode` consistent with them.

### Do Not Confuse with a Comparator Returning 0

A comparator that sorts people by age may return `0` for two people of the same age, even though `equals` on the person class checks their ID and considers them different.

`List.equals` does not take a comparator and does not automatically adopt whatever sorting rule was most recently used. Two sorted sequences with tied sort keys are still compared element by element using `equals`.

Therefore, sorting two lists and calling `equals` solves an order-insensitive comparison requirement only when the chosen canonical ordering truly matches the value equality definition being tested. Never assume that a comparator returning `0` is equivalent to `equals`.

## 11. Nested Lists and Arrays Inside a List

### Nested Lists Respect Order at Every Level

~~~java
List<List<Integer>> first =
        List.of(List.of(1, 2), List.of(3));

List<List<Integer>> second =
        List.of(List.of(2, 1), List.of(3));

System.out.println(first.equals(second)); // false
~~~

The first element of the outer List is an inner List. The inner List's `equals` continues by comparing the ordered sequence `1, 2` against `2, 1`.

If the two inner Lists are swapped in the outer List, the outer level's order matters as well.

This is a natural consequence of List elements themselves implementing sequence-based `equals`, rather than `List.equals` performing any special deep traversal for arbitrary objects.

### Arrays Use a Different equals Than List

~~~java
int[] first = {1, 2};
int[] second = {1, 2};

System.out.println(
        List.of(first).equals(List.of(second))
); // false

System.out.println(Arrays.equals(first, second)); // true
~~~

Each List here contains a single element of type `int[]`. Two distinct arrays are not equal by content under the `Object.equals` method inherited by arrays.

If business logic requires array elements to have value semantics, choose a representation or wrapper with appropriate content-based `equals`/`hashCode`, or use a different value-sequence type instead. Do not override `equals` on a wrapper while neglecting `hashCode`. Array comparison utilities are documented in the [Arrays API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#equals(int%5B%5D,int%5B%5D)).

Avoid creating self-referential structures or reference cycles and expecting recursive content-based `equals`/`hashCode` to terminate cleanly. That is not a normal List value-key model and runs into contract limitations.

## 12. When Business Logic Wants to Ignore Order

Choose the right comparison model instead of trying to reinterpret `List.equals`:

| Requirement | Comparison Model |
| --- | --- |
| Same sequence and same element occurrences at the exact positions | `List.equals` |
| Same set of distinct values, ignoring duplicate counts | `Set.equals` with contract-compliant elements |
| Same occurrence count for each value, ignoring order | Compare frequency maps or a suitable multiset representation |

A common flawed check:

~~~java
boolean same = left.size() == right.size()
        && left.containsAll(right)
        && right.containsAll(left);
~~~

With:

~~~text
left  = [A, A, B]
right = [A, B, B]
~~~

the sizes are equal and both sides contain A and B, yet the occurrence counts differ. This expression neither proves sequence equality nor multiset equality.

Converting both lists into `HashSet` instances and comparing them discards duplicate counts. That may be what the domain requires, but it must be a deliberate choice rather than treated as an optimization that preserves `List.equals` semantics.

When testing an API that returns a list, determine whether its contract guarantees order. If it does, comparing as a List is appropriate. If it does not, the test should explicitly express the intended set or multiset semantics rather than arbitrarily sorting the data and masking a real ordering bug where order was actually promised.

## 13. Complete Program

Save as **ListEqualityHashDemo.java**. The `MutableLabel` class is used intentionally to demonstrate how a list's hash changes when an element's state mutates; the program does not insert the list containing `MutableLabel` into a Map and then mutate the key.

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedList;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class ListEqualityHashDemo {
    public static void main(String[] args) {
        List<String> arrayList = new ArrayList<>(List.of("A", "B"));
        List<String> linkedList = new LinkedList<>(List.of("A", "B"));
        List<String> reversed = List.of("B", "A");

        System.out.println("Same reference = " + (arrayList == linkedList));
        System.out.println("Cross-implementation equals = "
                + arrayList.equals(linkedList));
        System.out.println("Reverse direction equals = "
                + linkedList.equals(arrayList));
        System.out.println("Reordered equals = " + arrayList.equals(reversed));
        System.out.println("AB hash = " + arrayList.hashCode());
        System.out.println("BA hash = " + reversed.hashCode());
        System.out.println("Manual AB hash = " + listHash(arrayList));
        System.out.println("Empty list hash = " + List.of().hashCode());

        List<Integer> collisionLeft = List.of(1, 0);
        List<Integer> collisionRight = List.of(0, 31);
        System.out.println("Collision equals = "
                + collisionLeft.equals(collisionRight));
        System.out.println("Collision hashes = "
                + collisionLeft.hashCode() + ", " + collisionRight.hashCode());

        List<String> swappedCollisionLeft = List.of("Aa", "BB");
        List<String> swappedCollisionRight = List.of("BB", "Aa");
        System.out.println("Reordered collision equals = "
                + swappedCollisionLeft.equals(swappedCollisionRight));
        System.out.println("Reordered collision hashes = "
                + swappedCollisionLeft.hashCode()
                + ", " + swappedCollisionRight.hashCode());

        List<String> withNull = Arrays.asList("A", null, "B");
        List<String> withNullCopy = new ArrayList<>(withNull);
        List<String> nullMoved = Arrays.asList(null, "A", "B");
        System.out.println("Null-aware equals = "
                + withNull.equals(withNullCopy));
        System.out.println("Null moved equals = " + withNull.equals(nullMoved));

        System.out.println("Duplicate count equals = "
                + List.of("A", "A", "B").equals(List.of("A", "B")));
        System.out.println("List versus set equals = "
                + arrayList.equals(Set.of("A", "B")));

        Set<List<String>> sequences = new HashSet<>();
        sequences.add(arrayList);
        sequences.add(linkedList);
        sequences.add(reversed);
        System.out.println("Distinct sequences in HashSet = "
                + sequences.size());

        List<String> mutableInput = new ArrayList<>(List.of("A", "B"));
        List<String> stableKey = List.copyOf(mutableInput);
        Map<List<String>, String> cache = new HashMap<>();
        cache.put(stableKey, "cached");
        mutableInput.add("C");
        System.out.println("Changed input = " + mutableInput);
        System.out.println("Stable key = " + stableKey);
        System.out.println("Equal sequence lookup = "
                + cache.get(new LinkedList<>(List.of("A", "B"))));
        System.out.println("Reordered lookup = "
                + cache.get(List.of("B", "A")));

        MutableLabel label = new MutableLabel("A");
        List<MutableLabel> fixedStructure = List.of(label);
        int before = fixedStructure.hashCode();
        label.rename("B");
        int after = fixedStructure.hashCode();
        System.out.println("Unmodifiable list hash before/after = "
                + before + ", " + after);

        int[] firstArray = {1, 2};
        int[] secondArray = {1, 2};
        System.out.println("Lists of separate arrays equal = "
                + List.of(firstArray).equals(List.of(secondArray)));
        System.out.println("Array contents equal = "
                + Arrays.equals(firstArray, secondArray));

        List<List<Integer>> nested = List.of(List.of(1, 2), List.of(3));
        List<List<Integer>> nestedReordered =
                List.of(List.of(2, 1), List.of(3));
        System.out.println("Nested inner order equals = "
                + nested.equals(nestedReordered));
    }

    private static int listHash(List<?> values) {
        int hash = 1;
        for (Object value : values) {
            hash = 31 * hash + Objects.hashCode(value);
        }
        return hash;
    }

    private static final class MutableLabel {
        private String value;

        private MutableLabel(String value) {
            this.value = Objects.requireNonNull(value);
        }

        private void rename(String newValue) {
            value = Objects.requireNonNull(newValue);
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof MutableLabel label
                    && value.equals(label.value);
        }

        @Override
        public int hashCode() {
            return value.hashCode();
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~shell
javac --release 17 -encoding UTF-8 ListEqualityHashDemo.java
java ListEqualityHashDemo
~~~

Stdout:

~~~text
Same reference = false
Cross-implementation equals = true
Reverse direction equals = true
Reordered equals = false
AB hash = 3042
BA hash = 3072
Manual AB hash = 3042
Empty list hash = 1
Collision equals = false
Collision hashes = 992, 992
Reordered collision equals = false
Reordered collision hashes = 68545, 68545
Null-aware equals = true
Null moved equals = false
Duplicate count equals = false
List versus set equals = false
Distinct sequences in HashSet = 2
Changed input = [A, B, C]
Stable key = [A, B]
Equal sequence lookup = cached
Reordered lookup = null
Unmodifiable list hash before/after = 96, 97
Lists of separate arrays equal = false
Array contents equal = true
Nested inner order equals = false
~~~

## 14. Evidence Explanation

**Same sequence, different implementations**

The two Lists do not share the same reference, yet they are equal in both directions. Whether stored in an ArrayList or a LinkedList, the meaning of the sequence A, B does not change.

**Reversed order**

A, B does not equal B, A. Their hashes are `3042` and `3072` respectively in the example, matching the accumulation calculation.

**Manual hash and empty List**

The `listHash` method computing element by element produces the exact same hash as the List. An empty List runs zero accumulation steps, so its hash is `1`.

**Two types of collisions**

Different numeric sequences produce the same hash `992`. Two differently ordered String sequences also produce the same hash `68545` because the Strings `"Aa"` and `"BB"` share identical hashes. In both cases, `equals` still returns `false`.

**Null and occurrence counts**

Null at the same position is compared consistently; moving null to another position makes the sequence unequal. A sequence with an extra A does not equal a sequence missing that occurrence.

**HashSet containing sequences**

A, B from two implementations represent the same List value, whereas B, A is a distinct value. Consequently, there are two List elements in the HashSet.

**String snapshot key**

C is added to `mutableInput`, yet `stableKey` remains A, B. A different LinkedList with the same sequence successfully retrieves the stored value. The reversed sequence does not match the key in the program's map.

**Unmodifiable structure but changing hash**

`MutableLabel` changes A to B, shifting the element hash from String A's hash to String B's hash. The single-element List changes its hash from `96` to `97`, even though no `add`/`remove`/`set` was called on the List.

**Arrays and nested Lists**

Two arrays with different references are not compared by content by a List. Two inner Lists, however, are compared using their own List contract, so the inner order still matters.

## 15. Testing and Cost

Recommended test cases:

1. Two Lists with the same content but different object instances and different implementations.
2. Two Lists with different element orders.
3. Duplicate elements and differing duplicate counts.
4. Null at the same position and null at different positions when the source permits null.
5. An empty List.
6. Two equal Lists must produce the same hash.
7. Two unequal Lists may share the same hash; do not write assertions requiring all unequal lists to have distinct hashes.
8. Elements with value-based `equals`/`hashCode`.
9. Array elements or mutable element objects.
10. A snapshot key protected against structural mutations of the original input source.

Do not test hashing with a rule like "changing order must change the hash in every case". Instead, verify the formula itself and the mandatory implication from `equals` to `hashCode`.

Regarding performance cost, sequence comparison can short-circuit early when sizes differ or when the first mismatched element pair is encountered; when lists are equal, all corresponding elements must be checked. Actual cost also depends on element `equals` implementations and the List implementation.

Computing the hash according to the contract formula generally requires accumulating across all elements, including the cost of hashing each element. Do not assume `hashCode` is a precomputed constant-time identifier on every List, or cache the hash of a mutable structure without a sound invalidation mechanism.

Calling `equals` or `hashCode` on a source being modified concurrently does not automatically create a snapshot or provide a consistent guarantee across the whole sequence. Choose stable data or an appropriate synchronization protocol for your requirements.

## 16. Common Pitfalls

| Misconception | Correct Understanding |
| --- | --- |
| Having the same distinct elements means `List.equals` is true | List also checks order and occurrence count. |
| Both lists must be `ArrayList` instances to be equal | Compliant List implementations compare using the same sequence contract. |
| Same `toString` output means equal | Elements of different types or unequal values can still render identically as strings. |
| `List.equals` compares elements using `==` | It compares element by element using `equals`, with null handling. |
| Equal hashes mean two Lists are equal | Collisions can occur; `equals` is required. |
| Because hash depends on order, every permutation has a different hash | Element collisions or arithmetic collisions can produce the same hash. |
| If a List is unmodifiable, its hash is guaranteed to be immutable | Mutable elements or a mutable backing list behind a view can still change. |
| `List.copyOf` always deep-copies all data | It does not deep-copy element objects. |
| Mutating a key inside a map causes the map to update its hash bucket automatically | All data participating in `equals`/hash must remain stable while used as a key. |
| A List containing arrays automatically compares array contents deeply | List delegates to element `equals`/hash; arrays use reference identity by default. |
| Two-way `containsAll` plus `size` check replaces `List.equals` | That ignores order and can even fail on duplicate counts. |

## 17. Practice

1. Calculate the hashes of `List.of(1, 2)` and `List.of(2, 1)` by hand, then verify with a program.
2. Create an ArrayList and a LinkedList containing null at the same position; check two-way `equals` and their hashes.
3. Use the Strings `"Aa"` and `"BB"` to construct two reversed sequences that share the same hash but are not equal.
4. Create two lists with the same size and mutual `containsAll` results, but different occurrence counts. Explain why that check fails even for multiset equality.
5. Design a composite key as a List of immutable values. Test lookup using a different List implementation holding the same sequence.
6. Mutate a stateful element inside an unmodifiable List. Observe the before-and-after hashes without inserting the unstable key into a real map.
7. Choose the appropriate comparison model for three requirements: a route with an ordered sequence of waypoints, a set of non-duplicate permissions, and a shopping cart that counts occurrences of each item code.

Before comparing lists or using a List as a key, determine whether the value being modeled is a sequence, a set, or a multiset. For a sequence, `equals` checks every position; `hashCode` accumulates in the same order and only assists hash-based lookup—it never replaces the definition of equality.
