# BitSet and How It Differs from Set<Integer>

## 1. From a Set of Indices to a Sequence of Bits

Suppose a program has positions numbered from 0 upward and needs to record which positions are currently selected. If positions 2 and 5 are selected, you can store those two numbers in a `Set<Integer>`. Another representation is to set the bits at indices 2 and 5 to `true`, while keeping all other bits `false`.

`BitSet` is a sequence of bits that can grow as needed. Each non-negative integer index corresponds to a boolean state. When used as a set, the convention is:

```text
bit i = true  → index i belongs to the represented set
bit i = false → index i does not belong to the represented set

Index: 0 1 2 3 4 5 6 7
Bit:   0 0 1 0 0 1 0 0
Set:   {2, 5}
```

A `0` in the `Bit` row means `false`; it does not mean that the element `0` is selected. To include `0` in the set, the bit at index `0` itself must be set to `true`.

`BitSet` is well suited for bitmasks, index sets, groups of conditions sharing the same numbering domain, and intersection/union operations across many flags. However, it **does not implement `Set` or `Collection`**. Having "Set" in its name does not give it the same API type or contract as `Set<Integer>`.

This lesson walks through marking individual indices, distinguishing three size-related quantities, performing set operations, working with ranges, and converting between representations. All complete programs target Java 17 or later.

## 2. What Do BitSet and Set<Integer> Represent?

| Characteristic | BitSet | Set<Integer> |
|---|---|---|
| Data model | Bit states at indices | Set of `Integer` objects |
| Value domain | Non-negative integer indices | May include negative numbers, depending on implementation and application constraints |
| Null | No null elements; indices are `int` | Whether null is accepted depends on implementation; `HashSet` allows it |
| Mark presence | `set(i)` | `add(i)` |
| Check presence | `get(i)` | `contains(i)` |
| Unmark | `clear(i)` | `remove(i)` |
| Count selected elements | `cardinality()` | `size()` |
| Set operations | Dedicated bit operations: `and`/`or`/`xor`/`andNot` | Collection operations or suitable algorithms |
| Iteration order | Ascending indices via `stream`/`nextSetBit` | Depends on the `Set` implementation |
| Collection/Set type | No | Yes |

`BitSet` does not store a separate `Integer` object for each enabled index. That is one reason it can be compact for dense index domains. However, the packed bit layout still depends on where the indices lie, not just on the number of elements. Two set bits placed very far apart have a different space cost than two set bits near the beginning.

`set`, `clear`, and the state-mutating logical operations do not return a `boolean` indicating "whether the set changed" like some `Set` operations do. Their return type is `void`. You cannot mechanically replace `set.add(i)` with a single call and still use its boolean return value.

Refer to the official contracts at [BitSet — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/BitSet.html) and [Set — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html).

## 3. Initialization and Single-Bit Operations

### 3.1. All Bits Start as false

`new BitSet()` creates a state with no `true` bits. `new BitSet(128)` requests enough initial space to represent indices `0` through `127`, yet still has no bits set.

The number `128` is neither the current element count nor a hard upper bound. You can set bit `130` later; `BitSet` will grow as needed. If an application only allows 128 positions, the application itself must enforce that limit and validate indices.

### 3.2. set, clear, flip, and get

| Call | Effect |
|---|---|
| `set(i)` | Sets bit `i` to `true` |
| `set(i, false)` | Sets bit `i` to `false` |
| `clear(i)` | Sets bit `i` to `false` |
| `flip(i)` | Toggles `false` to `true` or `true` to `false` |
| `get(i)` | Reads the boolean value at bit `i` |
| `clear()` | Sets all bits to `false` |

Setting a bit that is already `true` to `true` again does not create a duplicate element. `BitSet` does not count how many times an index has been added. If you need the frequency of each number, you need a structure that stores counts rather than a single present/absent bit.

Calling `get(i)` on a non-negative index that has not been set returns `false`, even if `i` lies beyond the highest currently `true` bit. That is not an application-domain index error. Negative indices are rejected with `IndexOutOfBoundsException`.

## 4. cardinality, length, and size Are Not Interchangeable

### 4.1. Three Different Questions

| Method | Question Answered | Example with bits 2, 5, 100 set |
|---|---|---|
| `cardinality()` | How many `true` bits are there? | `3` |
| `length()` | What is the logical length up to just after the highest `true` bit? | `101` |
| `size()` | How many bits of space does the structure currently use for representation? | Depends on allocated space and implementation |

`length()` equals the index of the highest `true` bit plus one; if there are no `true` bits, it returns `0`. It is not the number of selected elements. Clearing the highest bit can cause `length()` to drop even though only a single element was removed.

`size()` refers to the current representation space, which is different from `Set.size()`. The documentation notes that this value is implementation-dependent and may vary across implementations. Do not use it to count elements or as the number of domain positions.

For example, a `BitSet` created with initial space for 128 positions and no bits set has `cardinality()` `0` and `length()` `0`. Conversely, setting only bit `100` makes `length()` `101` while `cardinality()` remains `1`.

### 4.2. Application Domain Length Must Be Stored Separately

If there are exactly `N` seats, `N` pages, or `N` flags, the value `N` remains meaningful even when every bit is `false`. You cannot recover `N` from `length()` alone because `length()` is `0` in that case.

Nor is the number of valid positions determined by `size()`. The internal representation may allocate space different from `N`, and the constructor does not forbid growth. The slot-allocation example near the end of this lesson keeps a separate `limit` field.

## 5. Program 1: Marking, Reading, Counting, and Growing

Save the complete program to `BitSetBasicsDemo.java`:

```java
import java.util.BitSet;

public class BitSetBasicsDemo {
    public static void main(String[] args) {
        BitSet bits = new BitSet(128);
        System.out.println("initialCardinality=" + bits.cardinality());
        System.out.println("initialLength=" + bits.length());
        System.out.println("capacityAtLeastRequested=" + (bits.size() >= 128));
        bits.set(2);
        bits.set(5);
        bits.set(100);
        bits.set(5);
        System.out.println("selected=" + bits);
        System.out.println("cardinality=" + bits.cardinality());
        System.out.println("length=" + bits.length());
        System.out.println("get3=" + bits.get(3));
        System.out.println("get500=" + bits.get(500));
        bits.clear(100);
        System.out.println("afterClear100=" + bits);
        System.out.println("lengthAfterClear=" + bits.length());
        bits.flip(5);
        bits.flip(7);
        bits.set(130);
        System.out.println("afterFlipAndGrow=" + bits);
        System.out.println("grownLength=" + bits.length());
        bits.clear();
        System.out.println("empty=" + bits.isEmpty());
        System.out.println("emptyLength=" + bits.length());
        System.out.println("emptyCardinality=" + bits.cardinality());
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 BitSetBasicsDemo.java
java BitSetBasicsDemo
```

Stdout:

```text
initialCardinality=0
initialLength=0
capacityAtLeastRequested=true
selected={2, 5, 100}
cardinality=3
length=101
get3=false
get500=false
afterClear100={2, 5}
lengthAfterClear=6
afterFlipAndGrow={2, 7, 130}
grownLength=131
empty=true
emptyLength=0
emptyCardinality=0
```

### 5.1. Initial Space Does Not Increase the Number of true Bits

`initialCardinality=0` and `initialLength=0` confirm that no index is selected yet. The example only checks that the initial space is at least what was requested, without locking in a specific `size()` value as a contract to rely on across all implementations.

Setting `2`, `5`, `100`, and then setting `5` again still yields `{2, 5, 100}`. Cardinality is `3` and length is `101`. `get3=false` and `get500=false` are both valid reads at unset non-negative indices.

### 5.2. Clearing the Highest Bit and Growing Again

Clearing `100` leaves `{2, 5}`, so `length` becomes `6`, not `100` or `2`. Flipping bit `5` turns it off, flipping bit `7` turns it on, and then setting `130` produces `{2, 7, 130}`.

`grownLength=131` shows that index `130` is valid even though the constructor originally received `128`. If `128` is a real requirement limit, you must reject out-of-range indices before calling `set` rather than relying on the constructor.

Finally, `clear()` empties the state: `isEmpty` is `true`, `length` is `0`, and `cardinality` is `0`. Do not infer from this that the JVM has immediately reclaimed all backing space the object previously used.

## 6. Set Operations on BitSet

### 6.1. Each Index Is a Boolean Operation

For two `BitSet` instances `A` and `B` using the same numbering scheme:

| Operation | API on A | When is bit `i` in the result? |
|---|---|---|
| Intersection | `A.and(B)` | Both `A` and `B` have `i` |
| Union | `A.or(B)` | At least one of `A`, `B` has `i` |
| Symmetric difference | `A.xor(B)` | Exactly one of `A`, `B` has `i` |
| Difference `A` minus `B` | `A.andNot(B)` | `A` has `i` and `B` does not have `i` |
| Intersection test only | `A.intersects(B)` | Returns `true` if at least one index is set in both |

XOR is not set difference: elements present only in `B` still appear in XOR, whereas they do not appear in `A` minus `B`. `andNot` is not symmetric; swapping the two operands can produce a different result.

### 6.2. and/or/xor/andNot Mutate the Receiver Object

`A.or(B)` modifies `A`; it does not create and return a new `BitSet`. `B` is not modified simply by being passed as an argument when `A` and `B` are distinct objects.

If you need to preserve both sources, clone `A` first and apply the logical operation to the clone. A reference assignment `result = A` does not create a copy, so operating on `result` would still mutate `A`.

`intersects` is suitable when you only need to know whether there is any common element without storing the intersection itself. It returns a `boolean` and mutates neither set.

## 7. Program 2: Intersection, Union, XOR, and Difference

Save to `BitSetAlgebraDemo.java`. The `of` method in this program is a custom helper for setting indices; it is not a `BitSet.of` static method in the Java 17 API.

```java
import java.util.BitSet;

public class BitSetAlgebraDemo {
    private static BitSet of(int... indices) {
        BitSet result = new BitSet();
        for (int index : indices) {
            result.set(index);
        }
        return result;
    }

    public static void main(String[] args) {
        BitSet a = of(1, 3, 5, 9);
        BitSet b = of(3, 4, 9);
        BitSet intersection = (BitSet) a.clone();
        intersection.and(b);
        BitSet union = (BitSet) a.clone();
        union.or(b);
        BitSet symmetricDifference = (BitSet) a.clone();
        symmetricDifference.xor(b);
        BitSet difference = (BitSet) a.clone();
        difference.andNot(b);

        System.out.println("intersection=" + intersection);
        System.out.println("union=" + union);
        System.out.println("symmetricDifference=" + symmetricDifference);
        System.out.println("difference=" + difference);
        System.out.println("intersects=" + a.intersects(b));
        System.out.println("originalA=" + a);
        System.out.println("originalB=" + b);
        a.or(b);
        System.out.println("aAfterDirectOr=" + a);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 BitSetAlgebraDemo.java
java BitSetAlgebraDemo
```

Stdout:

```text
intersection={3, 9}
union={1, 3, 4, 5, 9}
symmetricDifference={1, 4, 5}
difference={1, 5}
intersects=true
originalA={1, 3, 5, 9}
originalB={3, 4, 9}
aAfterDirectOr={1, 3, 4, 5, 9}
```

### 7.1. Checking Each Result

With `A={1,3,5,9}` and `B={3,4,9}`, the intersection is `{3, 9}`, union is `{1, 3, 4, 5, 9}`, XOR is `{1, 4, 5}`, and `A` minus `B` is `{1, 5}`. Element `4` highlights the difference between XOR and set difference.

Because the earlier operations ran on clones, `originalA` and `originalB` remain unchanged. The final `a.or(b)` operates directly on `a`, turning `a` into the union. This demonstrates why you must track which object receives the call when using `void`-returning methods.

Sets being combined must share the same index meaning: bit `5` must represent the same object or attribute in both sources. If one source uses page numbers and the other uses user IDs, `and` will still execute, but the result has no domain meaning.

## 8. Operating on a Range of Indices

### 8.1. Start Inclusive, End Exclusive

The overloads accepting `fromIndex, toIndex` use the half-open interval `[fromIndex, toIndex)`:

- `set(2, 8)` sets `2, 3, 4, 5, 6, 7`.
- `clear(4, 6)` clears `4` and `5`.
- `flip(6, 9)` flips `6, 7, 8`.

`toIndex` is not included in the range. To operate on positions `0` through `N-1`, use `N` as the end bound. Using a half-open range makes the range length equal to `toIndex - fromIndex`.

A range where both bounds are equal is empty and contains no bits to modify. Negative bounds or `fromIndex > toIndex` are rejected with `IndexOutOfBoundsException`.

The constructor taking a negative initial bit count has its own error contract: `NegativeArraySizeException`. Do not confuse it with negative-index access errors from `get`/`set`.

### 8.2. get(from, to) Returns a New BitSet and Re-zeros Indices

`get(from, to)` is not a live view backed by the source `BitSet`. It returns a new `BitSet` containing the bits in the range, with the source's `from` position mapped to index `0` in the result.

For example, if the source has `2, 3, 8` set and you take the range `[2, 9)`, the result has `0, 1, 6` set. The mapping formula is `newIndex = originalIndex - fromIndex`.

Clearing bit `0` in the result does not clear bit `2` in the source. If you need to preserve the original numbering scheme, do not call `get(range)` and assume the printed numbers are still the original indices.

## 9. Program 3: Ranges, Copies, and Equality

Save the complete program to `BitSetRangeCopyDemo.java`:

```java
import java.util.BitSet;

public class BitSetRangeCopyDemo {
    public static void main(String[] args) {
        BitSet bits = new BitSet();
        bits.set(2, 8);
        System.out.println("setRange=" + bits);
        bits.clear(4, 6);
        System.out.println("clearRange=" + bits);
        bits.flip(6, 9);
        System.out.println("flipRange=" + bits);

        BitSet slice = bits.get(2, 9);
        System.out.println("slice=" + slice);
        slice.clear(0);
        System.out.println("sliceAfterClear=" + slice);
        System.out.println("originalBit2=" + bits.get(2));

        BitSet copy = (BitSet) bits.clone();
        copy.clear(3);
        System.out.println("copyAfterClear=" + copy);
        System.out.println("originalBit3=" + bits.get(3));

        BitSet small = new BitSet(1);
        BitSet large = new BitSet(1024);
        small.set(6);
        large.set(6);
        System.out.println("equalDespiteCapacity=" + small.equals(large));
        System.out.println("equalHashCodes=" + (small.hashCode() == large.hashCode()));
        try {
            bits.get(-1);
            throw new AssertionError("Expected IndexOutOfBoundsException");
        } catch (IndexOutOfBoundsException expected) {
            System.out.println("negativeIndex=IndexOutOfBoundsException");
        }
        try {
            bits.set(9, 3);
            throw new AssertionError("Expected IndexOutOfBoundsException");
        } catch (IndexOutOfBoundsException expected) {
            System.out.println("reversedRange=IndexOutOfBoundsException");
        }
        try {
            new BitSet(-1);
            throw new AssertionError("Expected NegativeArraySizeException");
        } catch (NegativeArraySizeException expected) {
            System.out.println("negativeInitialSize=NegativeArraySizeException");
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 BitSetRangeCopyDemo.java
java BitSetRangeCopyDemo
```

Stdout:

```text
setRange={2, 3, 4, 5, 6, 7}
clearRange={2, 3, 6, 7}
flipRange={2, 3, 8}
slice={0, 1, 6}
sliceAfterClear={1, 6}
originalBit2=true
copyAfterClear={2, 8}
originalBit3=true
equalDespiteCapacity=true
equalHashCodes=true
negativeIndex=IndexOutOfBoundsException
reversedRange=IndexOutOfBoundsException
negativeInitialSize=NegativeArraySizeException
```

### 9.1. Tracing the Three Range Operations

After `set(2, 8)`, bits `2` through `7` are set. `clear(4, 6)` removes `4` and `5`, leaving `{2, 3, 6, 7}`. `flip(6, 9)` turns off `6` and `7` and turns on `8`, so the source becomes `{2, 3, 8}`.

`slice={0, 1, 6}` shows the index shift when slicing from `2` up to (excluding) `9`. Clearing `0` on `slice` still leaves `originalBit2=true`.

### 9.2. clone Preserves Indices While Detaching Bit State

`clone()` creates a new `BitSet` with the same `true` bits, keeping the original numbering. Clearing `3` on `copy` leaves `{2, 8}` in the copy, while `originalBit3=true` confirms the source is untouched.

This contrasts with assigning a second reference variable to the same `BitSet`. Another reference does not duplicate the bit state.

### 9.3. equals Checks true Bits, Not Reserved Capacity

`small` and `large` are created with different initial sizes, yet both only have bit `6` set. `equalDespiteCapacity=true` and `equalHashCodes=true` confirm that bit content determines equality and hash code.

No trailing `false` bits are recorded as a separate domain length in `equals`. Two application configurations with different `N` but the same `true` bit pattern may need to be distinguished by a wrapper class holding both `N` and the `BitSet`, rather than relying on `BitSet.equals` alone.

`BitSet` is mutable, and `hashCode` depends on its `true` bits. Do not mutate a `BitSet` that is currently used as a key in a hash-based structure or as an element of a `HashSet` if doing so changes the hash code and equality relation that the structure relies on.

### 9.4. Intentional Input Errors

The three caught exceptions test three error conditions: a negative index, a reversed range, and a negative initial size. Each case prints the exact expected exception type.

Returning `false` for an unset index is different from an invalid negative index. That is why `get500` in Program 1 runs normally, whereas `get(-1)` here throws an exception.

## 10. Iterating Over Set Indices

### 10.1. nextSetBit Skips false Bits

`nextSetBit(from)` finds the first `true` bit at or after `from` (inclusive). If no `true` bit remains, it returns `-1`.

To continue iterating after index `i`, the next search starts at `i + 1`. If you kept searching from `i`, you would encounter the same `true` bit again and fail to make progress.

The loop pattern in the next program guards `i` against `Integer.MAX_VALUE` before computing `i + 1`, avoiding integer overflow at the maximum index. This is also noted in the `BitSet` API's iteration example. There is no need to create a huge `BitSet` just to run the small examples in this lesson.

### 10.2. stream Returns int Indices, Not Booleans

`bits.stream()` returns an `IntStream` containing the `true` bit indices in ascending order. For `{1, 7, 11}`, the array from the stream is `[1, 7, 11]`, not an array of `true`/`false` values at every position.

When collected into a `Set<Integer>`, the `int` indices are boxed into `Integer` objects by Java. Having `stream()` does not make `BitSet` a `Collection` that can be passed directly to any API expecting a `Set`.

A `BitSet` stream binds to its source when the terminal operation begins. The documentation specifies that the result is undefined if the `BitSet` is modified during that operation. When a stable source is required, ensure proper access synchronization or take a copy appropriately before iterating.

## 11. Program 4: Converting Between BitSet and Set<Integer>

Save to `BitSetIntegerSetDemo.java`. The program uses `TreeSet` when deterministic ascending print order is needed, rather than relying on the iteration order of an arbitrary `Set`.

```java
import java.util.Arrays;
import java.util.BitSet;
import java.util.Set;
import java.util.StringJoiner;
import java.util.TreeSet;

public class BitSetIntegerSetDemo {
    public static void main(String[] args) {
        Set<Integer> original = new TreeSet<>(Set.of(1, 7, 11));
        BitSet bits = new BitSet();
        for (int index : original) {
            bits.set(index);
        }
        System.out.println("bits=" + bits);
        System.out.println("streamIndices=" + Arrays.toString(bits.stream().toArray()));
        StringJoiner visited = new StringJoiner(", ");
        for (int index = bits.nextSetBit(0);
                index >= 0;
                index = bits.nextSetBit(index + 1)) {
            visited.add(Integer.toString(index));
            if (index == Integer.MAX_VALUE) {
                break;
            }
        }
        System.out.println("nextSetBitIndices=" + visited);
        Set<Integer> restored = new TreeSet<>();
        bits.stream().forEach(restored::add);
        System.out.println("restored=" + restored);
        System.out.println("sameMembers=" + restored.equals(original));
        System.out.println("bitSetEqualsSet=" + bits.equals(original));
        System.out.println("setEqualsBitSet=" + original.equals(bits));

        Set<Integer> signed = new TreeSet<>(Set.of(-1, 1));
        System.out.println("setHasNegative=" + signed.contains(-1));
        try {
            bits.get(-1);
            throw new AssertionError("Expected IndexOutOfBoundsException");
        } catch (IndexOutOfBoundsException expected) {
            System.out.println("negativeBitLookup=IndexOutOfBoundsException");
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 BitSetIntegerSetDemo.java
java BitSetIntegerSetDemo
```

Stdout:

```text
bits={1, 7, 11}
streamIndices=[1, 7, 11]
nextSetBitIndices=1, 7, 11
restored=[1, 7, 11]
sameMembers=true
bitSetEqualsSet=false
setEqualsBitSet=false
setHasNegative=true
negativeBitLookup=IndexOutOfBoundsException
```

### 11.1. Preserving the Same Elements in the Non-Negative Domain

The loop setting each index builds the `BitSet` `{1, 7, 11}`. Both `stream()` and the `nextSetBit` loop visit `1, 7, 11`. When collected back into a `TreeSet`, `sameMembers=true` confirms that the restored `Integer` set has the same members as the source set.

This conversion assumes the input consists of non-negative integers. For a general `Set`, you must explicitly decide how to handle negative numbers and `null` before converting: reject them, remap them through a separate index table, or choose another data structure. Never silently drop elements that `BitSet` cannot represent directly.

### 11.2. Same Set Semantics Does Not Mean equals Between the Two Types

`bitSetEqualsSet=false` and `setEqualsBitSet=false` follow the contracts. `BitSet.equals` requires the other object to also be a `BitSet` with the same `true` bits; `Set.equals` requires a `Set` with the same elements.

Do not use `equals` directly between the two types to verify a conversion. Compare two `BitSet` instances using the same representation, or convert both to `Set` and compare members as the program does.

### 11.3. Set Can Hold Negative Numbers; BitSet Has No Negative Indices

The `Set` in the final section validly holds `-1` and `1`. `BitSet.get(-1)`, by contrast, throws `IndexOutOfBoundsException`. This reflects a difference in data domains, not an equivalent lookup with a different method name.

`Set` is an interface; individual implementations also have different policies for `null` and ordering. For instance, [HashSet — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html) allows a `null` element, whereas `BitSet` has no special slot to represent a "null element".

## 12. When Is a Bit Representation Advantageous?

### 12.1. Dense Index Domains Sharing a Numbering Scheme

If identifiers already fall within `0` to `U-1` and many positions in that range may be used, one bit per position is a natural representation. Logical operations can process words of bits rather than handling individual `Integer` objects.

In OpenJDK, `BitSet` packs bits into 64-bit `long` words; you can inspect the [OpenJDK 17 BitSet source code](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/BitSet.java). This explains the implementation behind word-level processing, not a guarantee that every method runs in constant time.

Operations such as counting bits, iterating, or combining many bit words still do work proportional to the data examined. Do not use the intuition "it is just one `and` call" to conclude that intersection always has the same cost whether the domain is small or huge.

### 12.2. Sparse Sets with Very High Indices Can Be Disadvantageous

If there are only two elements, `0` and one billion, a linear bit representation must be able to reach that very high position. The raw bits alone take roughly 125 million bytes, not counting structural and allocation details. A `cardinality` of `2` does not reflect this cost.

A `HashSet` holding two numbers does not need to reserve a bit for every position between them. Therefore, do not choose `BitSet` solely from the statement "I only need to store integers." Consider both the highest index and data density.

Do not allocate huge indices in an example just to observe `true`; analyzing the data domain is enough to decide on the representation. If real identifiers are very sparse, you can keep them in a `Set` or design a mapping table to dense indices, provided every `BitSet` being combined uses the same mapping table.

### 12.3. Selection Criteria

| Need | What to Consider First |
|---|---|
| Many flags over a moderate index range | `BitSet` with a clearly documented domain `N` |
| Intersection/union of many groups sharing an index scheme | `BitSet` bit operations |
| A few numbers spaced very far apart | Cost scales with highest index; `Set` may fit better |
| Need negative numbers or `null` as elements | `Set` element policies or a custom mapping |
| Need to pass to an API accepting `Collection`/`Set` | `BitSet` cannot directly substitute for that interface |
| Need to count occurrences of each number | A frequency-counting structure, not a single present/absent bit |

There is no single best choice for all data. Any comparison should be based on index domain, element count, primary operations, and state-sharing requirements.

## 13. Finite Domains and Set Complements

### 13.1. You Must Know Which Domain the Complement Is Taken In

For the selected set `{0, 2}`, the question "which positions are unselected?" has no finite answer without knowing the valid domain. In `[0, 3)`, the remaining positions are `{1}`. In `[0, 5)`, the remaining positions are `{1, 3, 4}`.

`flip(0, N)` flips exactly the bits in that half-open range; it does not compute an unbounded complement. Bits outside the range are unaffected by this call. If you clone and then flip to compute the set of free positions, you must ensure the clone contains no `true` bits outside the application domain, or apply a domain mask with an appropriate set difference.

Do not use `length()` in place of `N`: when the last position is free, `length()` can be smaller than `N`. Nor should you use `size()` in place of `N`, because the backing representation may be larger than the business domain.

### 13.2. nextClearBit Does Not Know Resource Limits

`nextClearBit(0)` finds a `false` position starting from `0`. When positions `0, 1, 2` are all busy, it can return `3`; that only says bit `3` is `false`, not that the system has a fourth resource slot.

To allocate within a finite domain, check that the found index is less than the limit before marking it busy. This is a practical difference between an expandable bit state and a fixed-size resource list.

## 14. Program 5: Managing Positions 0 Through limit−1

Save the complete program to `BitSetSlotsDemo.java`. The `Slots` class convention is that a `true` bit means the slot is busy; `allocate` returns `-1` when no valid slot remains. The example is designed for single-threaded use.

```java
import java.util.BitSet;

public class BitSetSlotsDemo {
    static final class Slots {
        private final int limit;
        private final BitSet busy;

        Slots(int limit) {
            if (limit < 0) {
                throw new IllegalArgumentException("negative limit");
            }
            this.limit = limit;
            busy = new BitSet(limit);
        }

        int allocate() {
            int index = busy.nextClearBit(0);
            if (index >= limit) {
                return -1;
            }
            busy.set(index);
            return index;
        }

        void release(int index) {
            if (index < 0 || index >= limit) {
                throw new IndexOutOfBoundsException("slot");
            }
            busy.clear(index);
        }

        BitSet busySnapshot() {
            return (BitSet) busy.clone();
        }

        BitSet freeSnapshot() {
            BitSet free = (BitSet) busy.clone();
            free.flip(0, limit);
            return free;
        }
    }

    public static void main(String[] args) {
        Slots slots = new Slots(3);
        System.out.println("allocate=" + slots.allocate());
        System.out.println("allocate=" + slots.allocate());
        System.out.println("allocate=" + slots.allocate());
        System.out.println("fullAllocate=" + slots.allocate());
        slots.release(1);
        System.out.println("busyAfterRelease=" + slots.busySnapshot());
        System.out.println("freeAfterRelease=" + slots.freeSnapshot());
        System.out.println("allocateAgain=" + slots.allocate());
        BitSet snapshot = slots.busySnapshot();
        snapshot.clear();
        System.out.println("busyAfterSnapshotClear=" + slots.busySnapshot());
        System.out.println("zeroLimitAllocate=" + new Slots(0).allocate());
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 BitSetSlotsDemo.java
java BitSetSlotsDemo
```

Stdout:

```text
allocate=0
allocate=1
allocate=2
fullAllocate=-1
busyAfterRelease={0, 2}
freeAfterRelease={1}
allocateAgain=1
busyAfterSnapshotClear={0, 1, 2}
zeroLimitAllocate=-1
```

### 14.1. The Limit Is Checked Before Setting

The first three allocations return `0, 1, 2`. The fourth does not automatically expand the resource by using bit `3`: the method checks `index >= limit` and returns `-1`.

Releasing `1` leaves `busy` as `{0, 2}`. The free snapshot flips `[0, 3)`, yielding `{1}`. The next allocation reclaims slot `1`, and `busy` returns to `{0, 1, 2}`.

A limit of `0` is defined as having no valid slots, so `allocate` returns `-1` even though `nextClearBit` finds index `0`. A negative limit is rejected by the wrapper constructor with `IllegalArgumentException` before creating the `BitSet`.

### 14.2. Copies Protect Internal State

`busySnapshot()` returns a clone, not `busy` itself. Thus, clearing all bits on `snapshot` does not cause `Slots` to lose track of busy positions; `busyAfterSnapshotClear` remains `{0, 1, 2}`.

`freeSnapshot()` is valid because the class only sets bits within `[0, limit)`, so no out-of-domain `true` bits can remain after `flip`. That invariant is maintained by keeping the field `private` and checking bounds in the class methods.

The `release` method checks that the index is in range and clears the bit. As written, releasing a valid slot that is already free leaves it free; the example does not add an error policy for duplicate releases. In a real application, that contract should be chosen explicitly.

### 14.3. This Is a Multi-Step Workflow

`allocate` consists of finding a free bit and then marking it busy. `BitSet` does not make those two steps an atomic allocation across multiple threads. Two threads using it without coordination could find the same free index.

If concurrent use is required, you must design coordination for the entire state and workflow. The program output only verifies the single-threaded behavior described; it provides no concurrency guarantees on its own.

## 15. Converting to Arrays: Index Lists Differ from Packed Bit Data

Three similarly named APIs return different data:

| Extraction Method | Result Contents |
|---|---|
| `bits.stream().toArray()` | `int[]` containing the indices that are `true` |
| `bits.toByteArray()` | `byte[]` with packed bits |
| `bits.toLongArray()` | `long[]` with bits packed into words |

`BitSet.valueOf(byte[])` or `valueOf(long[])` reads a packed bit representation, not a list of selected integers. If you want to represent members `1, 7, 11`, set each index or convert as in Program 4; do not pass an array of members to `valueOf` and treat it as a `Set` conversion.

The `BitSet` documentation specifies the bit-numbering rules and little-endian representation of packed arrays. When defining a storage or wire format, follow that exact contract and do not equate this binary data with a binary character string or text encoding.

The bit pattern also does not preserve trailing `false` bits as a separate domain length. If a format needs to remember `N` valid positions, store `N` alongside the data as part of the format design. Restoring the same `true` bits does not by itself prove that all application-level information has been restored.

## 16. Mutability, Sharing, and Verification

### 16.1. Clearly Decide Which Object May Mutate

`BitSet` is mutable. Methods such as `set`/`clear`/`flip` and the logical operations can change data seen through other reference variables.

When a function is meant to compute a result while keeping the source intact, clone intentionally as in the algebra demo. When returning data to callers while protecting internal state, return an appropriate copy as in `Slots`. Naming a new variable does not create a data boundary.

There is no thread-safety guarantee without external synchronization. A word-level logical operation or a `set` call must not be interpreted as a complete transaction for multiple application steps.

### 16.2. Valuable Checks

- For `{2, 5, 100}`, verify `cardinality` `3` and `length` `101`; do not substitute `size` for either.
- Setting the same bit again must keep the member count unchanged, and flipping the same bit twice must restore the previous state.
- Ranges are start-inclusive and end-exclusive; also test empty ranges and reversed bounds.
- `get(range)` must shift indices to zero and return a separate copy; `clone` returns a separate copy while keeping indices.
- Intersection, union, XOR, and difference must yield the right results and mutate only the intended target object.
- Converting to a `Set` and back to a `BitSet` must preserve members within the supported domain.
- For finite domains, every set bit must be less than `N`, and `nextClearBit` results at or beyond `N` must be handled.

You can use a non-negative `Set<Integer>` as a reference oracle for operations: intersection corresponds to `retainAll` on a copy; union corresponds to `addAll`; difference corresponds to `removeAll`. Copy the `Set` if you want to keep the source intact, just like cloning a `BitSet`.

Verify both the result and that the sources remain untouched when that is part of the contract. An intersection that returns the right bits but accidentally mutates a source used in a later step is still a usage bug.

### 16.3. Do Not Infer Speed from the Structure's Name

Compact representation and word-level operations can offer major benefits when the index domain fits. Still, growing, copying, iterating, and counting bits all have costs; the element count `n` and the index domain `U` are not the same quantity.

When evaluating performance, use data representative of real-world density and maximum indices. A benchmark on numbers `0` to `100` does not tell you the cost of a few numbers near one billion.

## 17. Common Pitfalls

| Misconception | Consequence | How to Handle |
|---|---|---|
| `BitSet` is a `Set<Integer>` implementation | Wrong type passed to Collection APIs or misunderstood `equals` | Convert explicitly when a `Set` is needed |
| `new BitSet(N)` already has `N` elements | Wrong count right after construction | All bits start `false`; check `cardinality()` |
| `N` in constructor is a hard limit | Bits set beyond application domain without error | Store and check the limit separately |
| `size()` is the number of selected elements | Confuses backing space with membership | Use `cardinality()` |
| `length()` is the number of selected elements | Wrong whenever there are gaps between bits | Remember it is highest `true` bit plus one |
| Clearing the highest bit reduces `cardinality` by the whole gap | Confuses slot count with `true` bit count | `cardinality` decreases only by the cleared `true` bit |
| `or`/`and` return a new set | Unintentionally mutates the receiver | Clone first if a separate result is needed |
| XOR is `A` minus `B` | Retains elements present only in `B` | Distinguish `xor` from `andNot` |
| Ranges include both endpoints | Sets or clears one extra bit | Use half-open `[from, to)` |
| `get(from, to)` keeps original indices or returns a view | Misreads positions or expects source mutations | Understand it returns a new, zero-shifted copy |
| `nextClearBit` always returns a valid resource | Allocates beyond limit `N` | Check the result against `N` |
| Two elements means `BitSet` is definitely tiny | Ignores the highest index | Consider both domain `U` and density |
| `valueOf(long[])` takes a list of members | Builds the wrong bit pattern | It expects packed bit words |

## 18. Self-Check

### Questions

1. If `0` and `100` are set, what are `cardinality` and `length`?
2. Does `new BitSet(64)` forbid `set(100)`?
3. Does `get` at an unset non-negative index return `false` or `null`?
4. Why is `bits.equals(aSet)` not the right way to check whether two sets have equivalent members?
5. Does `a.and(b)` mutate `a` or return a new `BitSet`?
6. For `A={1, 3}` and `B={3, 4}`, how do XOR and `A` minus `B` differ?
7. If the source has `5, 7` set, which bits are set in `get(5, 8)`?
8. Why shouldn't `length` be used as the total number of seats in a system with `N` seats?
9. Positions `0, 1, 2` are busy; does `nextClearBit(0)` returning `3` mean there is another valid slot?
10. Why can a `BitSet` with a small `cardinality` still consume a lot of space?

### Answers

1. `cardinality` is `2`, `length` is `101`.
2. No; the initial size is not a fixed upper limit.
3. `false`; boolean values have no `null` state.
4. The two types have different `equals` contracts; `BitSet` is not a `Set`.
5. It mutates `a` and returns `void`. Clone `a` first if you need to keep the source.
6. XOR is `{1, 4}`, whereas `A` minus `B` is `{1}`.
7. Bits `0` and `2`, because `5` is subtracted from the original indices.
8. The last bit might be `false`, or all bits might be `false`; `length` describes the highest set bit, not `N`.
9. No; the application must check whether `3` is less than the limit.
10. A linear bit representation must reach up to the highest index; `cardinality` does not measure that span.

## 19. Practice with Expected Results

### Exercise 1: Three Size Quantities

Create a `BitSet` with initial space for 256 positions, setting only `4` and `200`. Before running, predict `cardinality` and `length`, then clear `200` and predict again.

Expected result: initially `cardinality` `2`, `length` `201`; after `clear(200)`, `cardinality` `1`, `length` `5`. Do not assume `size` equals `cardinality` or `length`.

### Exercise 2: Logical Operations Preserving Sources

Create `A={0, 2, 4}` and `B={2, 3}`. Use `clone` to compute intersection, union, XOR, and `A` minus `B`. After each operation, verify that `A` and `B` still match the original sets.

Expected result: intersection `{2}`, union `{0, 2, 3, 4}`, XOR `{0, 3, 4}`, difference `{0, 4}`. If `A` changed along the way, check whether the same reference was accidentally used as the target.

### Exercise 3: Slicing vs. Filtering While Keeping Indices

The source has `5` and `7` set. Call `get(5, 8)`, clear bit `0` on the result, and print both the source and the slice. Next, clone the source, clear bit `5` on the clone, and compare again.

Expected result: the initial slice is `{0, 2}`, and after clearing `0` it is `{2}`; the source remains `{5, 7}`. The clone preserves the original index system, so after `clear(5)` it becomes `{7}`. Both copy methods isolate state, but they differ in index semantics.

### Exercise 4: Complement in a Chosen Domain

In the domain `[0, 5)`, the busy set is `{0, 2}`. Create a copy with only those bits and call `flip(0, 5)`. Check the free set and the sum of cardinalities of busy and free.

Expected result: free is `{1, 3, 4}`, the total number of `true` bits is `5`, and the intersection of the two sets is empty. If you change the domain to `[0, 3)`, the free result becomes `{1}`; the domain is part of the problem definition, not inherent in the bit pattern.

## 20. Runtime Environment and References

The five programs in this lesson are self-contained and use Java 17–compatible syntax and APIs. They were compiled with `javac --release 17 -encoding UTF-8` and run on JDK 24.0.2; the stdout shown was captured from those runs. Each `public` class is saved in a file matching its name, with no external library dependencies.

- [BitSet — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/BitSet.html): indices, sizing, ranges, logical operations, streams, and packed arrays.
- [Set — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html): object set contract and `equals`.
- [HashSet — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html): a general `Set` implementation and its `null` element policy.
- [BitSet — OpenJDK 17 Source](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/BitSet.java): reference for `long`-word packed representation.
