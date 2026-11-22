# Choose Order-Based or Value-Set Comparison Before Writing Code

## 1. Decide what “equal” means before calling equals

Two structures with the same values can still be **equal or not**, depending on the requirements of the problem. For arrays, lists, and nested structures, the first question must be: **do element positions matter, and does the number of occurrences of each value matter?**

For example, given two sequences of numbers:

~~~text
A = [2, 1, 2]
B = [1, 2, 2]
C = [1, 1, 2]
~~~

- If comparing **by order**, A differs from B because the element at the first position differs.
- If comparing as a **value set**, A, B, and C all represent the set `{1, 2}`: order and occurrence count do not matter.
- If comparing as a **multiset (bag)**, A equals B because both have one `1` and two `2`s; A differs from C because C has two `1`s and one `2`.
- If the structure is a **map**, equality is determined by the set of key–value pairs, not by entry iteration order.

Those are **four different equality policies**. Do not choose `Arrays.equals`, `List.equals`, `Set.equals`, or a data conversion approach before determining the policy. A short piece of code can be syntactically valid yet violate business requirements if it chooses the wrong meaning of “equal”.

In Java's object contract module, this decision also governs implementing **both `equals(Object)` and `hashCode()`**. If two objects are considered equal under the chosen policy, their hash codes must match.

## 2. Three common policies for sequences of values

| Policy | Does order matter? | Does repetition count matter? | A vs. B | A vs. C |
| --- | --- | --- | --- | --- |
| Ordered sequence | Yes | Yes | Different | Different |
| Value set | No | No | Equal | Equal |
| Multiset / bag | No | Yes | Equal | Different |

### 2.1. Order-based comparison

Use when positions have meaning: sequences of processing steps, event histories, coordinates, priority orders, parameter lists, a data row with fixed columns, or paths across nodes.

Two sequences are equal only when:

1. They have the same number of elements.
2. Each pair of elements at the **same index** is equal according to the element type's equality policy.

For `int[]` arrays, `Arrays.equals(left, right)` compares integer values sequentially. For `List<T>`, `List.equals` compares elements at each position using the corresponding `equals`. Merely swapping two distinct elements can make two sequences unequal.

### 2.2. Set-based comparison

Use when you only need to know **which values appear**, such as a set of permissions, deduplicated tags, enabled feature flags, or selected IDs. The sequences `[2, 1, 2]` and `[1, 2]` represent the same set `{1, 2}`, if the contract allows ignoring duplicates.

A `Set<E>` under the Java contract does not treat iteration order as an equality criterion. Two sets are equal when they have the same elements under the `equals` relation and the same size. **Converting a sequence to a `Set` is a decision to discard occurrence count information**: this is the right operation only when duplicate counts carry no meaning.

For example, a registrant list containing two identical rows can sometimes be a bug to detect, or two separate registrations. Converting it straight into a `Set` can silently hide an important difference.

### 2.3. Multiset-based comparison

Use when order does not matter but **occurrence frequency** still matters, such as a shopping cart with quantities, an ingredient list, a label distribution, or checking whether two datasets have the same elements along with repetition counts.

A clear approach is building a frequency table: for each value, count occurrences, then compare the count maps using `Map.equals`. For `int[]`, we can use `Map<Integer, Integer>` and call `merge(value, 1, Integer::sum)`.

Sorting two sequences and then comparing by order can also check multiset equality **when sorting and comparison follow the same equality definition**. However, sorting in place mutates the input sequence; if data must be preserved, a copy must be created first. For custom types, a comparator may treat two elements as equivalent even though `equals` returns `false`; you must define the policy explicitly rather than assuming sorting is a universal answer.

## 3. Arrays in Java: reference, shallow content, and nested content

Different methods answer different questions:

| Comparison approach | Meaning |
| --- | --- |
| `arrayA == arrayB` | Do two variables point to the same array object? |
| `arrayA.equals(arrayB)` | Arrays do not override `Object.equals`: checks for the same array object |
| `Arrays.equals(int[], int[])` | Compares `int` elements sequentially by index |
| `Arrays.equals(Object[], Object[])` | Compares each element with `Objects.equals`; sub-arrays are still treated as reference objects |
| `Arrays.deepEquals(Object[], Object[])` | Recursively compares contents of nested arrays, including primitive array elements |
| `List.equals` | Compares lists by order, invoking equality on each element |
| `Set.equals` | Compares by element set; ignores iteration position |

For example, two different `int[]` variables containing the same `[1, 2]` are not equal under `==`, yet are equal under `Arrays.equals`. With `int[][]`, the rows are separate `int[]` objects, so `Arrays.equals(matrixA, matrixB)` usually returns `false` when rows are created separately; `Arrays.deepEquals(matrixA, matrixB)` compares each row's content.

For nested array structures, use the matching hash function pair: `Arrays.hashCode` for one-dimensional arrays compared by order, `Arrays.deepHashCode` for nested arrays compared with `Arrays.deepEquals`. You must not use the array's default `Object.hashCode()` for a class that defines content-based equality, because two arrays with different references but identical content can receive different hashes.

**Note:** `Arrays.deepEquals` handles **array** structures, but does not automatically turn a `List` into an unordered set, nor does it automatically traverse into arbitrary custom objects. When elements are `List` or `Set`, it uses the equality defined by those element types. Self-referential array structures with cycles also require special design; do not treat `deepEquals` as a general cycle-aware graph comparator.

## 4. Runnable Java 17 example: one dataset, multiple equality results

The program below simultaneously demonstrates order-based comparison, set-based comparison, multiset-based comparison, and nested array structure comparison. It also inserts two objects with identical-content arrays into a `HashSet` to test `equals`/`hashCode` of a class containing arrays.

Save in file **ComparisonPolicyDemo.java**:

~~~java
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class ComparisonPolicyDemo {
    static Set<Integer> valuesAsSet(int[] numbers) {
        Set<Integer> result = new HashSet<>();
        for (int number : numbers) {
            result.add(number);
        }
        return result;
    }

    static Map<Integer, Integer> frequencies(int[] numbers) {
        Map<Integer, Integer> count = new HashMap<>();
        for (int number : numbers) {
            count.merge(number, 1, Integer::sum);
        }
        return count;
    }

    static final class OrderedSequence {
        private final int[] values;

        OrderedSequence(int... values) {
            this.values = values.clone();
        }

        @Override
        public boolean equals(Object other) {
            return this == other
                    || (other instanceof OrderedSequence that
                            && Arrays.equals(values, that.values));
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(values);
        }
    }

    static final class ValueSet {
        private final Set<Integer> values;

        ValueSet(int... numbers) {
            this.values = Set.copyOf(valuesAsSet(numbers));
        }

        @Override
        public boolean equals(Object other) {
            return this == other
                    || (other instanceof ValueSet that
                            && values.equals(that.values));
        }

        @Override
        public int hashCode() {
            return values.hashCode();
        }
    }

    public static void main(String[] args) {
        int[] a = {2, 1, 2};
        int[] b = {1, 2, 2};
        int[] c = {1, 1, 2};
        int[] sameAsA = {2, 1, 2};

        System.out.println("same array reference: " + (a == sameAsA));
        System.out.println("ordered A/B: " + Arrays.equals(a, b));
        System.out.println("ordered A/copy: "
                + Arrays.equals(a, sameAsA));
        System.out.println("set A/B: "
                + valuesAsSet(a).equals(valuesAsSet(b)));
        System.out.println("set A/C: "
                + valuesAsSet(a).equals(valuesAsSet(c)));
        System.out.println("multiset A/B: "
                + frequencies(a).equals(frequencies(b)));
        System.out.println("multiset A/C: "
                + frequencies(a).equals(frequencies(c)));

        Set<OrderedSequence> orderedKeys = new HashSet<>();
        orderedKeys.add(new OrderedSequence(a));
        System.out.println("ordered HashSet contains copy: "
                + orderedKeys.contains(new OrderedSequence(sameAsA)));
        System.out.println("ordered HashSet contains B: "
                + orderedKeys.contains(new OrderedSequence(b)));

        Set<ValueSet> setKeys = new HashSet<>();
        setKeys.add(new ValueSet(a));
        System.out.println("set-key HashSet contains B: "
                + setKeys.contains(new ValueSet(b)));
        System.out.println("set-key HashSet contains C: "
                + setKeys.contains(new ValueSet(c)));

        int[][] matrixA = {{1, 2}, {3, 4}};
        int[][] matrixB = {{1, 2}, {3, 4}};
        System.out.println("matrix shallow equality: "
                + Arrays.equals(matrixA, matrixB));
        System.out.println("matrix deep equality: "
                + Arrays.deepEquals(matrixA, matrixB));
        System.out.println("matrix deep hashes agree: "
                + (Arrays.deepHashCode(matrixA)
                        == Arrays.deepHashCode(matrixB)));

        List<Set<Integer>> nestedA =
                List.of(Set.of(1, 2), Set.of(3));
        List<Set<Integer>> nestedB =
                List.of(Set.of(2, 1), Set.of(3));
        List<Set<Integer>> nestedReordered =
                List.of(Set.of(3), Set.of(1, 2));
        System.out.println("nested same structure: "
                + nestedA.equals(nestedB));
        System.out.println("nested outer order: "
                + nestedA.equals(nestedReordered));
    }
}
~~~

Use JDK 17 or later:

~~~bash
javac ComparisonPolicyDemo.java
java ComparisonPolicyDemo
~~~

Exact expected output:

~~~text
same array reference: false
ordered A/B: false
ordered A/copy: true
set A/B: true
set A/C: true
multiset A/B: true
multiset A/C: false
ordered HashSet contains copy: true
ordered HashSet contains B: false
set-key HashSet contains B: true
set-key HashSet contains C: true
matrix shallow equality: false
matrix deep equality: true
matrix deep hashes agree: true
nested same structure: true
nested outer order: false
~~~

Explanation:

- Arrays `a` and `sameAsA` are two different objects, yet elements at every position are identical, so `==` returns `false` while `Arrays.equals` returns `true`.
- `a` and `b` do not share the same order; however, both contain the same set `{1, 2}` and the same occurrence count for each value. Thus both set and multiset comparisons treat them as equal.
- `c` still has the value set `{1, 2}`, but its frequencies differ from `a`; multiset comparison must return `false`.
- `OrderedSequence` copies the array in the constructor, compares content with `Arrays.equals`, and uses `Arrays.hashCode`. Two keys with the same content are recognized by `HashSet` as the same value; a sequence with a different order is different.
- `ValueSet` converts the input into an immutable set, ignoring order and repetition counts. Both `equals` and `hashCode` rely on the same `Set` object, preserving the equality contract.
- Two matrices have separately created `int[]` rows: shallow comparison does not treat the rows as the same reference; deep comparison sees the same content and produces the same deep hash.
- The `List<Set<Integer>>` structure uses a **combined rule**: the outer list cares about position, while each inner set ignores order. Hence swapping element declaration order inside a set still compares equal, whereas swapping the positions of two sets in the outer list differs.

The `equals`/`hashCode` pair of the two wrapper classes illustrates equality policies encoded at **the data type level**. Two wrappers with the same input set may be equal under `ValueSet` even if unequal under `OrderedSequence`; this is an intentional design choice, not a contradiction.

## 5. Nested structures: applying policies level by level

There is no rule that all levels must care about order alike. Define the meaning of **each node** in the data structure:

| Structure | Outer-level rule | Inner-level rule |
| --- | --- | --- |
| `List<List<String>>` | Outer list is ordered | Each inner list is ordered |
| `List<Set<String>>` | Outer list is ordered | Inner set is unordered, no duplicates |
| `Set<List<String>>` | Outer set is unordered | Each inner list is ordered |
| `Map<String, List<Integer>>` | Key–value pairs do not depend on map iteration order | List for each key is ordered |
| `int[][]` with `Arrays.deepEquals` | Rows by index | Elements within each row by index |

For example, a `List<Set<String>>` can represent “ordered stages, where each stage is an unordered group of permissions”. Swapping two permissions within the same stage does not change meaning; swapping two stages can change meaning. Meanwhile, `Set<List<String>>` can represent a “set of paths”, where step order within a path must be preserved, but the listing order of paths is arbitrary.

If business logic requires a multiset **at an inner level**, `Set` is no longer suitable because it removes duplicates; you can use `Map<Element, Integer>` to represent frequencies for each group. Similarly, if the requirement is “matrices having the same rows in any order while preserving column order within each row”, you must design a policy for a set/multiset of **rows** first. Calling `Arrays.deepEquals` alone is insufficient, because it still compares each row by position.

Be careful when using arrays as `Set` elements or `Map` keys: Java arrays default to reference-based equality. For instance, two independent `int[]` arrays with the same `[1, 2]` are still treated as two **distinct** elements in `HashSet<int[]>`. If you need a set of rows by content, use a wrapper type with `equals`/`hashCode` based on `Arrays.equals`, or convert each row into an appropriate value type.

## 6. Keeping the equals/hashCode contract aligned with the chosen policy

### 6.1. Ordered equality

For a class holding `int[] values` with sequence-based equality, the consistent pairing is:

~~~java
@Override
public boolean equals(Object other) {
    return this == other
            || (other instanceof OrderedSequence that
                    && java.util.Arrays.equals(values, that.values));
}

@Override
public int hashCode() {
    return java.util.Arrays.hashCode(values);
}
~~~

This is an **illustrative method excerpt in the `OrderedSequence` class already declared in the main program**, not a standalone Java file. Changing element order can change both equality and the hash code. Different arrays may still collide in hash code; that is permitted.

### 6.2. Set-based equality

For a class holding `Set<Integer> values`:

~~~java
@Override
public boolean equals(Object other) {
    return this == other
            || (other instanceof ValueSet that
                    && values.equals(that.values));
}

@Override
public int hashCode() {
    return values.hashCode();
}
~~~

This is an **illustrative excerpt in `ValueSet`**, not a standalone program. The `Set.hashCode` contract is based on elements and thus independent of iteration order. Therefore two equal sets must have equal hashes even if iteration order differs.

### 6.3. Multiset-based equality

If a class stores `Map<T, Integer>` to count how many times each element appears, then `equals` can compare the two count maps and `hashCode` can use `Map.hashCode` on that same count map. You must ensure counts accurately reflect permitted data, are updated consistently, and are large enough for actual occurrence counts.

Do not use order-sensitive `Arrays.hashCode` if the class's `equals` treats `[2,1,2]` and `[1,2,2]` as equal as a multiset: two business-equal sequences could very likely have different hashes, **violating the contract**. Conversely, hashing by value set while `equals` is order-based can produce many collisions without necessarily breaking the contract; it is a poor distribution choice and fails to express design intent.

## 7. Protecting data against state mutation

If a class defines equality by array content, keeping the reference directly from the constructor allows external code to mutate the array and change `equals`/`hashCode` results after the object has been placed into a `HashMap` or `HashSet`. Consequently, lookups can fail even though the element is still in the collection.

In the example, `OrderedSequence` calls `values.clone()` to obtain a copy of `int[]`. Because the field is `private final` and does not expose the internal array, the array content used as a key cannot be altered by modifying the input after creating the wrapper.

For two-dimensional arrays, **`matrix.clone()` only copies the outer array; it does not automatically copy the rows**. If each `int[]` row can be mutated, each row must be copied individually or another immutable type must be used. `List.copyOf` or `Set.copyOf` likewise only freezes the outer collection structure; inner elements can continue to mutate if they themselves are mutable.

For a `List` used as a key, consider an immutable copy and ensure all elements participating in equality have stable state. For a `Set`, ensure none of the element properties affecting `equals`/`hashCode` are mutated, because the hash collection itself depends on them as well.

## 8. Typical mistakes

### Mistake 1: switching to Set just to avoid caring about order

If two orders have duplicate product lines, converting the line list to a `Set` can strip away the meaning of **occurrence count**. When order does not matter but quantity matters, compare as a multiset or aggregate by key with total quantity.

### Mistake 2: using Arrays.equals on multidimensional arrays and thinking it compares deeply

`Arrays.equals(int[][], int[][])` compares rows as `int[]` objects, often leading to `false` when rows are separately allocated. If the goal is each numeric element at the exact coordinate, use `Arrays.deepEquals` and `Arrays.deepHashCode` under the same policy.

### Mistake 3: comparing two Lists by sorting them directly

In-place sorting mutates the input lists and can destroy business order. For lists that do not support modification, the operation can throw `UnsupportedOperationException`. Choose the right data type from the start, or sort **copies** by appropriate criteria if the policy truly requires multiset comparison.

### Mistake 4: using a Set of arrays to represent a set of rows by content

`HashSet<int[]>` uses the array's default `equals` and `hashCode`, which are based on object identity. It does not make two arrays with the same content equal elements. You need a wrapper, structural conversion, or value keys with an appropriate contract.

### Mistake 5: implementing equals and hashCode under two different policies

If `equals` is order-insensitive while `hashCode` uses an order-sensitive hash, two equal objects can receive different hash codes. This breaks the assumptions of `HashMap`/`HashSet` and violates the contract.

### Mistake 6: assuming every Collection compares content by the same rules

`List` and `Set` have different equality contracts. Two collections displaying similar values are not enough to declare them equal. For nested structures, you must read the **data type and contract at each level** accurately.

## 9. Process for choosing a policy before writing code

When encountering a requirement to “compare two arrays, two lists, or two nested structures”, determine:

1. **Comparison unit:** primitive element, custom object, matrix row, or nested group?
2. **Order:** does swapping the positions of two elements change the meaning? If yes, choose sequence-based comparison.
3. **Duplicates:** is `[A,A,B]` equal to `[A,B]`? If yes, you can choose a set; if not, and order still does not matter, choose a multiset.
4. **Each nesting level:** a list of groups may need an ordered outer list but unordered sets inside. Write down the policy for each level first.
5. **`null` inputs and `null` elements:** specify where `null` is allowed, how two missing values are interpreted, and pick an API that satisfies the contract. For example, `Set.copyOf` does not accept `null` elements.
6. **Mutability:** can the fields determining equality change while the object is a key in a hash collection? If so, design defensive copies/immutability or an appropriate update workflow.
7. **`hashCode` contract:** if objects are equal under the chosen policy, does the hash method always produce the same result?
8. **Counterexamples:** test a pair differing only in order and a pair differing only in repetition count. These two small examples usually expose a wrong equality rule immediately.

**Key takeaway:** “Same elements” is not a sufficient specification for implementing `equals`. Decide explicitly **whether order matters**, **whether occurrence count matters**, and **what each nesting level means**. Only then choose `Arrays.equals`, `Arrays.deepEquals`, `List.equals`, `Set.equals`, or a frequency table, while designing `hashCode` consistently with the chosen policy.