# ArrayList: Initialization, Capacity Growth, and Amortized Append Cost

When reading data rows without knowing the line count in advance, we need a list that can accept additional elements. Java arrays have a fixed length after creation; if we use an array directly, we must track the element count, detect when it is full, allocate another array, and copy the data over. `ArrayList` encapsulates that work so users can operate on an indexed list.

This convenience has a cost worth understanding: most append operations simply write one extra reference, while some must replace the backing array. Therefore, the statement "appending is O(1)" is only accurate when speaking of **amortized constant cost across a sequence of operations**, not the worst-case time of every individual call.

This article moves from the size–capacity model, initialization options, and the array growth mechanism, to the amortization proof and how to choose an allocation strategy. The examples use Java 17-compatible APIs. Implementation details specific to a single OpenJDK build are separated from the guarantees a program can rely on through the API.

## 1. Two Distinct Quantities: Element Count and Reserved Space

**Size** is the number of elements currently belonging to the list. **Capacity** is the number of slots the backing array can currently hold before it needs to grow again.

We can visualize a list as follows:

~~~text
size = 3, capacity = 5

array index:   0      1      2      3      4
             [A]    [B]    [C]  [empty] [empty]
              <--- elements --> <-- reserve -->
~~~

The diagram is an explanatory model. `[empty]` represents an internal reserved slot, not an element that can be read via `get`. In this state:

- `size()` returns 3.
- `get(0)`, `get(1)`, `get(2)` are valid.
- `get(3)` is invalid even though the backing array has room.
- `add("D")` creates the fourth element of the list.
- `set(3, "D")` prior to adding is invalid; `set` only replaces an already existing element.

The invariants that hold are:

~~~text
0 <= size <= capacity

get/set:      0 <= index < size
add(index,x): 0 <= index <= size
~~~

Here, `add(size, x)` inserts at the end; `add(x)` expresses this intent directly.

Capacity is not a lifetime upper bound on the number of elements the list is allowed to accept. When necessary, the list can increase its capacity, provided the environment can still allocate memory. Conversely, a large capacity does not populate the list with elements in advance.

### 1.1. A null Element Still Counts Toward size

`ArrayList` permits `null` elements. Calling `add(null)` adds one element and increments `size`. Do not equate "a slot holding a null reference" with "a slot that does not yet belong to the list."

What determines which portion of the array constitutes the list content is `size`. This is also why the size cannot be inferred by scanning up to the first `null` reference.

### 1.2. The Backing Array Holds References

For an `ArrayList<Person>`, the array slots hold references to `Person` objects. Growing the array copies the references; it does not create a deep copy of each `Person`.

Similarly, `ArrayList<Integer>` is not a self-growing `int[]`. It holds references to `Integer` objects; boxing, object memory overhead, and how values are created are separate costs from replacing the array. When analyzing append operations, be clear about whether you are counting the work inside the list structure or the total work of the application.

## 2. Choosing an Initialization Strategy Based on Available Information

Three common forms of initialization:

| Form | Size immediately after creation | Purpose |
|---|---:|---|
| `new ArrayList<>()` | 0 | No initial data, no useful size estimate yet |
| `new ArrayList<>(expected)` | 0 | Reserve space for the expected number of elements |
| `new ArrayList<>(source)` | `source.size()` if the source is stable | Create a list containing the elements of the source |

The integer parameter specifies the initial capacity, not the initial size. The collection constructor copies elements in the order returned by the source's iterator; it does not sort them automatically. A negative capacity throws `IllegalArgumentException`; a `null` source collection throws `NullPointerException`. See the contract in [ArrayList in Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html).

### 2.1. Default Constructor: A Good Choice When the Count Is Unknown

The following snippet is an illustrative method body fragment:

~~~java
ArrayList<String> names = new ArrayList<>();
names.add("An");
names.add("Binh");
~~~

The user does not need to manage array exhaustion manually. This is usually the cleanest way to write code when the list is small or when there is no reliable expected count.

There is no need to pick an arbitrarily large number "just in case it runs short." Automatic growth is the normal function of this data structure; the decision to pre-size capacity should be justified by data or measurements.

### 2.2. Integer Constructor: Reserving Space Without Populating Data

~~~java
ArrayList<String> names = new ArrayList<>(100);
~~~

The line above creates an empty list with the specified initial capacity. It does not create 100 empty names, 100 empty strings, or 100 `null` elements. Immediately afterward, `names.size()` is still 0.

If you want the list to actually contain 100 `null` elements, you must add 100 elements; that is a different requirement and changes the observable content. Do not fill a list with dummy elements as a substitute for reserving memory.

A value of 0 is valid: `new ArrayList<>(0)` can still accept elements later. A negative value does not mean "let Java compute it automatically." If an estimate might be negative, handle the invalid input before calling the constructor.

Pre-sizing with a reasonable capacity is useful when you know you will collect roughly 20,000 results. It shifts allocation work to initialization time and reduces array replacements during additions. However, if you ultimately receive only 3 results, most of the reserved region will not have served actual content.

### 2.3. Collection Constructor: Copying Structure, Sharing Elements

~~~java
ArrayList<String> names = new ArrayList<>(List.of("An", "Binh"));
names.add("Chi");
~~~

The new list can be structurally modified even though the `List.of` source does not allow additions or removals. This is convenient when you need to start from a fixed dataset and continue editing.

Two kinds of independence must be distinguished:

- Adding or removing elements in the new list does not directly add or remove elements in the source list.
- If the elements are mutable objects and both lists hold references to them, mutating an object can be observed through both lists.

The complete example in the practice section uses `StringBuilder` to observe this phenomenon. Copying a list does not automatically make the internal objects immutable or independent.

If the source has m elements, setting up the new list's contents requires processing the source elements; do not treat this constructor as an O(1) operation just because it fits on a single line of syntax. For a typical, stable source with linear traversal, the copying cost is O(m). If the source has a specialized implementation or is modified concurrently, you must examine the contract and cost of the source itself.

### 2.4. What Does "Default 10" Mean?

The Java 17 documentation describes the no-arg constructor as constructing an empty list with an initial capacity of 10. That does not mean `size()` is 10 or that the program is allowed to read 10 indices.

In the OpenJDK 17 build referenced in this article, the default constructor uses a shared empty sentinel array and defers regular array allocation until needed. On the first ordinary addition, the default threshold is 10. The constructor passed 0 goes through a different empty state; do not use these two creation paths to assume an identical growth schedule. This is an implementation detail, shown in the [OpenJDK 17 ArrayList source code, build jdk-17+35](https://raw.githubusercontent.com/openjdk/jdk/jdk-17%2B35/src/java.base/share/classes/java/util/ArrayList.java).

The takeaway for writing code is: both approaches create a valid empty list, and applications use `size`, `add`, and `get` according to the contract. Do not write business logic conditions that depend on whether the first array allocation has exactly 10 slots.

## 3. What Happens When Appending to the End?

Consider a list currently holding n elements with capacity c. There are two scenarios.

### 3.1. Space Available: Write to the Next Slot

If `n < c`, the structure can:

1. Write the new element reference into slot n.
2. Increment the size to n + 1.

No preceding elements need to be shifted. Considering only array and index management work, the number of operations does not grow with n: this is the O(1) cost path.

Creating the element itself may take much longer. With `list.add(loadLargeDocument())`, loading the document happens before the `add` call receives its argument; evaluating the speed of the full expression must account for that work separately.

### 3.2. Already Full: Replace the Array Before Writing

If `n == c`, the structure needs a larger backing store. The typical model is:

1. Choose a new capacity large enough to hold at least the element being added.
2. Allocate a new array.
3. Copy data from the old array.
4. Point the internal reference to the new array.
5. Write the new element and update the size.

The illustrative example below intentionally uses a hypothetical growth policy:

~~~text
before add(D):    size=3, capacity=3
old array:        [A] [B] [C]

after growth:     size=3, capacity=6
new array:        [A] [B] [C] [ ] [ ] [ ]

after add(D):     size=4, capacity=6
new array:        [A] [B] [C] [D] [ ] [ ]
~~~

The diagram does not claim that Java's `ArrayList` always grows from 3 to 6. It explains why a single addition can require work proportional to the number of existing elements.

When growing from a full array, copying the n existing references incurs O(n) cost. Allocating and initializing the new array also has a cost; amortized analysis must consider the entire sequence of growth events rather than simply ignoring the expensive steps.

### 3.3. The List Remains the Same Object

When the backing array is replaced, the `ArrayList` instance held by application code is not replaced by a new list object. Variables pointing to that same list still see the added contents.

The elements themselves do not change identity merely because the array holding their references was replaced. There is no requirement to re-invoke each element's constructor, `clone` each element, or recompute business data.

The old array becomes eligible for garbage collection once no active references to it remain. This does not guarantee that memory is reclaimed immediately. During the transition, space is needed for both the old array and the new array; peak memory usage can be higher than the steady-state footprint after growth completes.

## 4. Capacity Growth Policy: Contract vs. Implementation Details

What applications should rely on is the ability to grow automatically and the guarantee that appending has amortized constant cost. The API does not fix a specific growth factor that every Java implementation must use.

In the OpenJDK 17 build cited above, once a regular backing array exists, the preferred increment is roughly half the old capacity. The minimum required growth and integer limit handling can make the result differ from a simple multiplication by 1.5. Length calculation delegates to [ArraysSupport in the same OpenJDK build](https://raw.githubusercontent.com/openjdk/jdk/jdk-17%2B35/src/java.base/share/classes/jdk/internal/util/ArraysSupport.java).

You do not need to memorize a specific sequence of capacities to use `ArrayList` properly. The following claims all lack necessary qualifications:

- "Every growth step doubles the array."
- "Every growth step multiplies by exactly 1.5, including empty arrays and small numbers."
- "After adding n elements, the capacity is guaranteed to equal a fixed formula of n."
- "The constructor or `ensureCapacity` will always allocate the exact number of slots that I can verify via a getter."

`ArrayList` does not provide a public `capacity()` method. `size()` only reports the number of elements. Do not use reflection on private fields to turn an implementation detail into a business condition or an application correctness test.

This article uses a **doubling** policy in the mathematical proof and the work-counting program. This policy makes the geometric series easy to see. It is a standalone educational model, not a replica of the OpenJDK algorithm.

## 5. Why Do Occasional O(n) Steps Still Yield Amortized O(1) Appends?

### 5.1. Consider the Total Cost of a Sequence, Not Just the Slowest Call

Suppose we start empty and only append to the end. In the doubling model, capacity passes through:

~~~text
1, 2, 4, 8, 16, 32, ...
~~~

To move from a full array to the next array, we copy:

~~~text
0, 1, 2, 4, 8, 16, ...
~~~

Most additions fall between two growth thresholds and copy zero existing elements. One expensive growth operation creates multiple free slots that serve many subsequent additions.

Work-counting table for 9 additions:

| Addition # | Capacity after add | Existing elements copied this step | New element writes |
|---:|---:|---:|---:|
| 1 | 1 | 0 | 1 |
| 2 | 2 | 1 | 1 |
| 3 | 4 | 2 | 1 |
| 4 | 4 | 0 | 1 |
| 5 | 8 | 4 | 1 |
| 6 | 8 | 0 | 1 |
| 7 | 8 | 0 | 1 |
| 8 | 8 | 0 | 1 |
| 9 | 16 | 8 | 1 |

After 9 additions, there are a total of 15 element copies and 9 new writes. The 9th addition alone does much more work than the 8th, yet the cumulative work remains proportional to the number of elements added.

### 5.2. Proof via Geometric Series Sum

Let n be the number of added elements, n >= 1; let C be the final capacity in the doubling model. We have:

~~~text
n <= C < 2n

total old references/elements copied
    = 1 + 2 + 4 + ... + C/2
    = C - 1
    < 2n

number of new element writes = n

sum of both types of work < 3n
~~~

For C = 1, the empty copy sum is 0; the formula C - 1 still holds.

Because the total work for n additions is O(n), dividing by n operations gives an amortized O(1) cost per addition. This is an upper bound for the entire sequence under the model, requiring no assumption that the user supplies random data.

Array allocation and initialization costs do not invalidate this asymptotic bound in the standard model: the sum of all allocated array lengths is also a geometric series and is O(n). However, constant factors, JVM allocation mechanics, garbage collection, and the elements created by the application all affect wall-clock time.

### 5.3. Amortized Is Neither Probabilistic Average Nor a Latency Bound

**Amortized analysis** distributes the total work of a sequence of operations. It does not say "the data is usually lucky, so it is fast."

If a program must meet a very strict latency deadline for every single request, a large copy can still make that particular request slow. Amortized O(1) is not a promise that every call takes the same number of nanoseconds, performs no allocation, or experiences no garbage collection pause.

Three questions and their properly scoped conclusions:

| Question | Appropriate conclusion |
|---|---|
| How much list-management work does appending take when spare capacity exists? | O(1) |
| How much work can a single append do when it must grow from a full array? | O(n), where n is the number of existing elements |
| What is the asymptotic total work of a sequence of n appends starting from empty under a standard multiplicative growth policy? | O(n), i.e., amortized O(1) per operation |

If a list initially contains m elements, the very first addition in the observed window may have to move those m elements. You cannot truncate history and claim that a very short sequence always costs only in proportion to the newly added elements. A safe bound for appending n more elements from a state that already has m elements is O(m + n), accounting for the associated growth step.

### 5.4. Why Not Grow by Just One Slot at a Time?

If every full array grew by allocating only a single extra slot, the number of copies when adding n elements from an empty list would be:

~~~text
0 + 1 + 2 + ... + (n - 1) = n(n - 1)/2
~~~

The total becomes O(n²). Allocating a proportional surplus of capacity trades reserved memory for far fewer copy operations.

With any fixed growth factor greater than 1, the sum of array lengths across growth steps remains a geometric series. A larger growth factor typically leaves more unused slack after a resize but reduces resize frequency; a factor closer to 1 typically reduces slack but increases the constant factor on total copies. This is a data structure design trade-off, not a public parameter you can tune on `ArrayList`.

## 6. What Do ensureCapacity and trimToSize Control?

### 6.1. ensureCapacity: Preparing in Advance for a Well-Founded Need

On an existing list, you can call:

~~~java
ArrayList<String> rows = new ArrayList<>();
rows.ensureCapacity(20_000);
~~~

This request does not add elements. Nor does it fill the list with `null`, change element ordering, or make indices 0 through 19,999 valid for reading.

The word "capacity" here should be understood as a minimum threshold to serve a need, not a command to set the capacity to the exact argument value. If enough room already exists, no growth is needed. If growth is needed, the implementation may choose an array larger than the requested minimum. This method is not used for shrinking.

Along the default-constructor path in OpenJDK 17, small requests may even preserve the lazy allocation state mentioned earlier. Therefore, do not assume that every call to `ensureCapacity(k)` performs an immediate allocation.

When about to append a batch of data, the requirement is the **total size needed after the addition**, not just the size of the incoming batch. If the list currently holds 3,000 elements and expects 2,000 more, requesting 2,000 does not express a need for 5,000 elements.

Computing `size + incomingCount` using `int` arithmetic can overflow if the numbers are huge. If an application genuinely accepts external counts that could be large, validate non-negativity and check for overflow—for instance with `Math.addExact`—and apply the application's own memory limits. A sum that fits in an `int` still does not guarantee that allocation will succeed.

There is no need to call `ensureCapacity(size() + 1)` before every `add`: `add` itself already knows how to grow. Conversely, you should not claim that such redundant calls automatically force the array to grow by only one slot each time; `ensureCapacity` specifies a minimum required threshold, not the exact growth increment. Any performance conclusion must analyze actual behavior.

### 6.2. trimToSize: Discarding Unused Reserve Capacity

`trimToSize()` requests shrinking the capacity down to the current size. It preserves the logical content of the list.

If a list once held a large number of elements, now retains only a small fraction, and will be kept around for a long time for read-only access, trimming can release the unused backing array slots. If the list is about to receive many new additions again, trimming may simply force the next addition to reallocate and grow the array.

This is not an unconditionally O(1) operation. In an array-backed implementation, when trimming actually occurs, a new array must be allocated and the remaining data copied over. Both the copying time and the temporary memory required during copying must be accounted for.

### 6.3. clear Releases List Content Without Promising Immediate Memory Return

`clear()` empties the list, resetting `size()` to 0. In OpenJDK 17, the element references are nulled out across the used slots while the backing array itself is retained. Keeping the backing array is beneficial if the same list instance is reused for a subsequent batch.

Do not assume that calling `clear` causes all element objects to vanish from the heap immediately. They might still be referenced elsewhere; even if they are not, the timing of garbage collection is decided by the JVM.

If you have just cleared a very large dataset and are certain you do not need to retain the reserved capacity, you can consider calling `trimToSize` afterward, or changing how you manage the list's lifecycle. That decision should consider who still holds references to the list and whether it will be reused, rather than looking at a single memory snapshot in isolation.

### 6.4. Do Not Trim After Every Addition

Suppose `trimToSize` were called after every `add`. At the end of each loop iteration, capacity would once again equal size, leaving zero spare slots for the next addition.

In an array-backed structure, doing so forces consecutive additions to copy an ever-longer list, and the trim operation itself may perform yet another copy. The total cost can degrade to O(n²). The program itself has destroyed the spare-capacity invariant needed to amortize copying costs.

This anti-pattern is completely different from a deliberate one-time trim after a data-loading phase completes. Do not turn a conditional memory optimization into a mandatory ritual inside a loop.

## 7. Practice: Observing the API and Counting Work in a Custom Model

The following program has two independent parts:

1. Using a real `ArrayList` to verify size, indexing, constructors, `ensureCapacity`, `trimToSize`, and shallow copying.
2. Using a custom `DoublingBuffer` to count doubling growth work, because the `ArrayList` API does not expose a copy counter or a capacity getter.

`DoublingBuffer` is intentionally minimal and uses `int[]`. It does not implement `List`, lacks the full operations and boundary policies of `ArrayList`, and is not meant for production data. Its sole purpose is to verify the arithmetic proven earlier.

### 7.1. Complete Source Code

Save as `ArrayListGrowthDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class ArrayListGrowthDemo {
    // Work-counting model: NOT the ArrayList source code.
    static final class DoublingBuffer {
        private int[] elements = new int[0];
        private int size;
        private long copies;
        private int growths;

        void add(int value) {
            if (size == elements.length) {
                int nextCapacity = elements.length == 0
                        ? 1 : Math.multiplyExact(elements.length, 2);
                copies += size;
                elements = Arrays.copyOf(elements, nextCapacity);
                growths++;
            }
            elements[size++] = value;
        }

        long totalWork() {
            return copies + size;
        }
    }

    public static void main(String[] args) {
        ArrayList<String> defaults = new ArrayList<>();
        ArrayList<String> zero = new ArrayList<>(0);
        ArrayList<String> reserved = new ArrayList<>(4);
        System.out.printf("empty sizes: default=%d, zero=%d, reserved=%d%n",
                defaults.size(), zero.size(), reserved.size());

        try {
            reserved.get(0);
        } catch (IndexOutOfBoundsException exception) {
            System.out.println("get(0) before add: IndexOutOfBoundsException");
        }

        reserved.add("A");
        reserved.add("B");
        System.out.printf("after add: size=%d, values=%s%n",
                reserved.size(), reserved);
        reserved.ensureCapacity(100);
        System.out.printf("after ensureCapacity: size=%d, values=%s%n",
                reserved.size(), reserved);
        reserved.trimToSize();
        System.out.printf("after trimToSize: size=%d, values=%s%n",
                reserved.size(), reserved);
        reserved.clear();
        System.out.printf("after clear: size=%d, values=%s%n",
                reserved.size(), reserved);

        ArrayList<String> mutable = new ArrayList<>(List.of("X", "Y"));
        mutable.add("Z");
        System.out.println("copy from List.of: " + mutable);
        try {
            new ArrayList<String>(-1);
        } catch (IllegalArgumentException exception) {
            System.out.println("negative capacity: IllegalArgumentException");
        }

        ArrayList<StringBuilder> source = new ArrayList<>();
        source.add(new StringBuilder("item"));
        ArrayList<StringBuilder> copied = new ArrayList<>(source);
        source.add(new StringBuilder("other"));
        copied.get(0).append("*");
        System.out.printf("shallow copy: sourceSize=%d, copySize=%d, shared=%s%n",
                source.size(), copied.size(), source.get(0) == copied.get(0));
        System.out.printf("shared content: source=%s, copy=%s%n",
                source.get(0), copied.get(0));

        System.out.println("doubling model: n, capacity, growths, copies, stores, work");
        for (int n : new int[] {1, 2, 3, 4, 5, 8, 9, 16, 17, 1000}) {
            DoublingBuffer buffer = new DoublingBuffer();
            for (int value = 0; value < n; value++) {
                buffer.add(value);
            }
            System.out.printf("%d, %d, %d, %d, %d, %d%n",
                    n, buffer.elements.length, buffer.growths,
                    buffer.copies, buffer.size, buffer.totalWork());
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~shell
javac --release 17 -encoding UTF-8 ArrayListGrowthDemo.java
java ArrayListGrowthDemo
~~~

### 7.2. Standard Output

~~~text
empty sizes: default=0, zero=0, reserved=0
get(0) before add: IndexOutOfBoundsException
after add: size=2, values=[A, B]
after ensureCapacity: size=2, values=[A, B]
after trimToSize: size=2, values=[A, B]
after clear: size=0, values=[]
copy from List.of: [X, Y, Z]
negative capacity: IllegalArgumentException
shallow copy: sourceSize=2, copySize=1, shared=true
shared content: source=item*, copy=item*
doubling model: n, capacity, growths, copies, stores, work
1, 1, 1, 0, 1, 1
2, 2, 2, 1, 2, 3
3, 4, 3, 3, 3, 6
4, 4, 3, 3, 4, 7
5, 8, 4, 7, 5, 12
8, 8, 4, 7, 8, 15
9, 16, 5, 15, 9, 24
16, 16, 5, 15, 16, 31
17, 32, 6, 31, 17, 48
1000, 1024, 11, 1023, 1000, 2023
~~~

### 7.3. Reading the Results

The `empty sizes` line shows that all three ways of creating an empty list result in the same logical size. It does not measure actual capacity and does not claim that the three backing arrays are allocated identically.

The exception on `get(0)` proves that reserved capacity does not expand the range of valid indices. The program prints only the exception type name that it explicitly catches, avoiding dependence on JDK-specific exception message wording.

The lines following `ensureCapacity` and `trimToSize` still report `size=2`, `values=[A, B]`. This is what is observable through the API: the logical content is preserved. The program does not attempt to inspect private state to measure how many slots were allocated.

The copy constructed from `List.of` accepts `Z` successfully. In the `StringBuilder` example, adding another object to the source brings the source size to 2 while the copy still has 1 element; however, because the first element reference is shared, both lists see `item*`.

In the `doubling model` table:

- `n` is the number of additions into a fresh empty buffer.
- `capacity` is the array length of our custom model, not of `ArrayList`.
- `growths` counts the number of array allocations, including the initial step from 0 to 1.
- `copies` counts the cumulative number of existing elements copied between arrays.
- `stores` counts one write per newly added element.
- `work` is `copies + stores`.

At n = 16, the total counted work is 15 + 16 = 31. At n = 17, adding one more element crosses the 16 threshold and bumps cumulative copies to 31, yet the total work of 48 is still less than 3 × 17. At n = 1,000, the 2,023 units of work still scale linearly with n.

This counter does not include zero-initializing new array slots, index arithmetic, branch checks, garbage collection, or element creation time. Therefore, do not read 2,023 as 2,023 nanoseconds, and do not compare that number directly against the wall-clock execution time of Java's `ArrayList`. It demonstrates an explicitly defined cost model.

## 8. Choosing an Allocation Strategy in Applications

### 8.1. When the Output Count Is Known with Reasonable Confidence

If you know the output will have exactly or roughly k elements and k fits comfortably within your memory budget, using `new ArrayList<>(k)` avoids multiple resize cycles during population.

Be sure to include container initialization cost when evaluating list construction. Pre-sizing with a very large k does not make the overall process free; it shifts array allocation cost upfront and holds onto memory earlier.

If list creation is moved outside a timed benchmark section, the measurement reflects only the remaining work. That may align with your measurement goal, but it must be stated explicitly when comparing against a list that grows dynamically.

### 8.2. When Only a Very Loose Upper Bound Is Known

Suppose there are 1,000,000 input records but only a small fraction passes a filter. Using the input count as the output capacity can waste substantial memory.

You can choose the default constructor, a modest estimate based on observed selectivity, or batch processing. There is no rule stating "if an upper bound is known, always allocate the upper bound." A moderate initial estimate still allows the list to grow if actual data exceeds expectations.

Never pre-allocate based on an arbitrarily large count supplied by user input or external data without enforcing application bounds first. Passing a type-valid `int` to the constructor does not prove that the request fits available memory.

### 8.3. Lists That Grow Across Multiple Batches

If each incoming batch has a known count, you can prepare capacity for the cumulative need before the batch arrives. Do not call `trimToSize` between batches only to grow the array again a few seconds later.

If a list is long-lived but experiences peak load only once, holding onto a massive backing array forever may be undesirable. Separating the loading phase, processing phase, and data lifecycle makes it much clearer when to trim or discard the list.

### 8.4. Controlling the Latency of Individual Additions

Pre-sizing capacity can avoid array resizes within an expected range. However, it does not by itself guarantee a maximum execution time for the whole application: element creation, data access, thread scheduling, and garbage collection remain factors.

If tail latency is a critical requirement, measure the latency distribution under realistic load and design your memory lifecycle accordingly. A good average time does not prove the absence of slow additions at capacity boundaries.

### 8.5. When Retaining All Results Is Unnecessary

If you only need to compute an aggregate sum, write out records one by one, or stream data forward, ask whether you truly need to accumulate every element in a list. Avoiding unnecessary retention often has a far greater impact than tuning capacity.

This is a decision about algorithms and output requirements. If you need repeated indexed access to the entire dataset, keeping a list is completely reasonable; do not replace the data structure merely out of fear of an occasional array resize.

## 9. Boundaries of Performance Conclusions

### 9.1. Pre-Sizing Capacity Does Not Make Every Operation O(1)

Having spare capacity avoids array replacement overhead, but inserting at the front still requires shifting all subsequent elements. Similarly, removing from the middle requires closing the gap.

For `ArrayList`, the standard cost model is:

| Operation | Primary work |
|---|---|
| `get(index)`, `set(index, value)` | Access an existing slot, O(1) |
| `add(value)` | Amortized O(1); individual growth steps take O(n) |
| `add(index, value)` | Shift the trailing elements, up to O(n), plus potential array growth |
| Finding an element by scanning | May inspect up to n elements |
| Actual array trimming | Allocate a new array and copy retained data |

Asymptotic complexity describes how operation counts scale with input size. It does not replace profiling an application with large element objects, expensive equality comparisons, or specific heap constraints.

### 9.2. Memory Footprint Is More Than Just n Elements

You must distinguish between the capacity of the reference array, the list object itself, the element objects, and temporary memory during growth. You cannot calculate exact byte usage with a universal fixed formula like "n × 4" across every JVM.

Reference size, object alignment, and object headers depend on JVM configuration. If you need byte counts to make an engineering decision, measure with tools appropriate for your target environment rather than extrapolating from `size()`.

Near system limits, allocation can fail due to heap exhaustion or JVM array size limits. `Integer.MAX_VALUE` is not a promise that you can create an `ArrayList` holding that many elements. There is no need to run experiments that deliberately exhaust memory just to verify everyday usage guidelines.

### 9.3. Pre-Allocating Capacity Does Not Solve Concurrency

`ArrayList` is not thread-safe when multiple threads modify its structure concurrently. Having plenty of spare slots does not turn size updates and element writes into a valid concurrent protocol.

If a list is shared for writes across threads, you must use proper synchronization or a concurrent data structure suited to your access pattern. Capacity is a storage and performance concern; it does not replace thread coordination rules.

### 9.4. Do Not Infer the Growth Factor from a Single Stopwatch Run

A single wall-clock timing run can be skewed by JVM warm-up, JIT compilation, dead-code elimination, memory allocation, garbage collection, and background system load.

To make a meaningful comparison, define a consistent measurement scope: whether constructor execution, element creation, and cleanup are included; whether each iteration uses a fresh list or reuses an existing one; and whether the data represents realistic workloads. In particular, do not compare a pre-allocated list against one that must allocate on the fly and conclude that the first structure is universally faster by that exact ratio.

The mathematical proof explains the asymptotic growth of work. The work-counting demo confirms the arithmetic on the model. Real performance benchmarking answers a different question on a specific JVM under a defined workload.

## 10. Common Misconceptions

| Misconception | Correct understanding |
|---|---|
| `new ArrayList<>(100)` contains 100 elements | The size is still 0; the argument specifies initial capacity |
| Spare capacity lets you `set` any slot within capacity | `set` only works for indices strictly less than `size` |
| A `null` element does not count toward size | Every `add(null)` adds an element and increments `size` |
| Appending always takes constant time on every individual call | It is amortized constant time; a growth step can be linear |
| Amortized means random data is usually fast | It bounds total work over a sequence without assuming random inputs |
| Growing the array deep-copies every element object | Only references are copied; the referenced objects remain shared |
| The collection constructor creates a list completely independent of the source | The list structure is independent, but mutable element objects are shared |
| `ensureCapacity` sets the list size | It adjusts storage capacity without adding elements |
| `ensureCapacity(k)` forces capacity to be exactly k | k expresses a minimum required capacity, not an exact array size setter |
| `clear` guarantees returning all memory to the OS immediately | It clears logical content, while the backing array is retained and GC runs on its own schedule |
| Trimming after every addition always saves memory and runs faster | It destroys spare capacity and can degrade total copying to quadratic time |
| Pre-sizing capacity makes inserting at index 0 an O(1) operation | Trailing elements still have to be shifted |
| Pre-sizing capacity makes concurrent multi-threaded writes safe | It does not change thread synchronization requirements |

## 11. Self-Check Exercises

### Scenario 1: Valid Index Range

After creating `new ArrayList<String>(8)` without adding any elements, is `get(0)` valid? After two `add` calls, is `set(2, "C")` valid?

**Explanation:** Both are invalid. Initially `size=0`; after two additions `size=2`, so the only valid replacement indices for `set` are 0 and 1. To add a third element, use `add("C")` or `add(2, "C")`.

### Scenario 2: Total Work

In the doubling model, after adding 8 elements and then adding the 9th element, how does the cumulative copy count change?

**Explanation:** After 8 elements, 1 + 2 + 4 = 7 copies have occurred. The 9th addition copies 8 existing elements, bringing the total to 15. A sudden jump on a single step does not contradict the linear upper bound across the entire sequence.

### Scenario 3: Reserving Space for the Next Batch

A list currently holds 700 elements and is about to receive 500 more. Does calling `ensureCapacity(500)` accurately express the capacity needed for the batch?

**Explanation:** No. The total capacity needed is 1,200 (assuming no intervening removals and a reliable count). Requesting 500 may do nothing because the current size already exceeds 500. Even without calling `ensureCapacity`, however, `add` will still grow the list automatically as needed.

### Scenario 4: Over-Allocated Capacity

A list once held 100,000 elements, now holds 100, and will be retained long-term for read-only lookups. Should you automatically call `trimToSize` inside every removal step?

**Explanation:** There is no need to tie it to every removal. You can consider trimming once after the reduction phase finishes, based on the list's lifecycle and reuse needs. Remember to account for copying cost and temporary memory; observing `size=100` alone does not tell you how much backing capacity is currently held.

### Scenario 5: Shallow Copy

A source list and a copied list both contain the same `StringBuilder`. Does removing the reference from the source remove the element from the copy? Can mutating the `StringBuilder` content be observed through the copy?

**Explanation:** Removing the element from the source does not remove it from the copied list. Mutating the shared `StringBuilder` object can be seen through the copy. Structural independence of the lists and independence of the element objects are two separate things.

When reading or writing code that uses `ArrayList`, identify clearly whether you are reasoning about **element count**, **reserved capacity**, **single-operation cost**, or **cumulative cost across a sequence**. Those four questions help you pick the right constructor, avoid wasteful allocations, and apply the amortized O(1) conclusion under the right conditions.
