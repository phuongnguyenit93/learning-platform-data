# LinkedList: Node Lookup Cost by Index

`LinkedList` implements the `List` interface, so it provides `get(i)`, `set(i, value)`, `add(i, value)`, and `remove(i)`. However, sharing method names with `ArrayList` does not mean sharing the same way of locating a position.

An array can access position `i` directly. A linked list must find the node holding that position by traversing links. Java's `LinkedList` is doubly linked and holds references to both the head and the tail, so it can start from whichever end is closer. This reduces the number of steps, but it does not make accessing the middle of the list O(1).

The key point to understand is: **navigating to the node** and **performing the work at the located node** are two distinct cost components. Confusing these two parts easily leads to O(n²) loops or the mistaken conclusion that index-based insertion and removal always have constant cost.

## 1. The Model: An Index Is a Logical Position, Not a Node Address

A doubly linked list can be visualized as follows:

~~~text
first                                             last
  |                                                 |
  v                                                 v
 [A] <-> [B] <-> [C] <-> [D] <-> [E] <-> [F] <-> [G]
  0       1       2       3       4       5       6
               logical index in the list
~~~

Each node holds an element and links to the previous and next nodes. The numbers 0, 1, 2… in the diagram are positions used to explain the order. There is no public array mapping each of those numbers directly to a node.

Knowing `i = 4` means knowing that we want the fifth element. That does not directly provide a reference to node E.

According to the [Java SE 17 LinkedList documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html), operations that index into the list will traverse the list from the beginning or the end, whichever is closer to the specified index. This is an important characteristic when choosing how to iterate and evaluate costs.

### 1.1. How Does the `prev` Link Help?

If there were only forward links and only a head reference, finding index `i` would require taking `i` steps from the head. With two-way links and a `last` reference as well, searching near the end can traverse backward in far fewer steps.

For example, in a list with 10,000 elements:

- Finding index 2 can start from the head across two links.
- Finding index 9,997 can start from the tail across two links.
- Finding index 5,000 still requires traversing roughly half the list.

Therefore, not every `get(i)` has to start from the head. Nor does being doubly linked mean that every `get(i)` takes only a few steps.

### 1.2. An Element Is Different from the Node Containing It

`get(i)` returns an element of type `E`; it does not return a public node object for the application to link or unlink on its own.

Even when holding a reference to an element, we do not necessarily have a reference to the node containing it. A list may also contain the same element reference at multiple positions.

Therefore, the statement "we already have the object to remove, so removal is O(1)" does not automatically apply to `linkedList.remove(object)`. That method still has to search for the matching occurrence by value.

## 2. Counting Node Lookup Steps for a Valid Index

Let:

- `n` be the current number of elements.
- `i` be the index to access.
- `0 <= i < n`.

The distance from the head is `i`. The distance from the tail, at index `n−1`, is `n−1−i`.

The number of link traversal steps when choosing the closer end is:

~~~text
h(n, i) = min(i, n - 1 - i)
~~~

This is the number of transitions from one node to an adjacent node, not the total number of instructions executed by the JVM. Even when `h = 0`, the method must still bounds-check the index, obtain the head/tail reference, and read the element.

Therefore, the work model for finding the node and accessing the element is:

~~~text
Theta(1 + min(i, n - 1 - i))
~~~

Adding 1 properly represents the constant work at both ends.

### 2.1. Example with n = 8

| i | From head | From tail | Closer end | Steps h(n,i) |
|---:|---:|---:|---|---:|
| 0 | 0 | 7 | Head | 0 |
| 1 | 1 | 6 | Head | 1 |
| 2 | 2 | 5 | Head | 2 |
| 3 | 3 | 4 | Head | 3 |
| 4 | 4 | 3 | Tail | 3 |
| 5 | 5 | 2 | Tail | 2 |
| 6 | 6 | 1 | Tail | 1 |
| 7 | 7 | 0 | Tail | 0 |

Finding index 4 starts at the node at index 7, moves through 6 and 5, and reaches 4. We traverse three links instead of starting from the head across four links.

### 2.2. Specific Branch Selection in OpenJDK 17

In the [OpenJDK 17 LinkedList source code, build jdk-17+35](https://raw.githubusercontent.com/openjdk/jdk/jdk-17%2B35/src/java.base/share/classes/java/util/LinkedList.java), the internal node lookup function compares the index against half the size. The first half traverses from `first` via `next`; the remaining part traverses from `last` via `prev`.

If `n` is odd, the exact middle node is equidistant from both ends; the branch selection in this version traverses from the tail when landing right on the midpoint. Choosing head or tail in a tie does not change the step count or the asymptotic cost order.

The program in this article models this counting rule. It does not call a private node-inspection API and does not directly measure internal JVM fields.

### 2.3. Why Is Accessing the Head and Tail Still O(1)?

For `i = 0`:

~~~text
min(0, n - 1) = 0
~~~

For `i = n−1`:

~~~text
min(n - 1, 0) = 0
~~~

Because head and tail references are already maintained, there is no need to walk the list to find these two positions. Intent-revealing operations such as `getFirst()`, `getLast()`, `addFirst()`, `addLast()`, `removeFirst()`, and `removeLast()` directly use the endpoints in the implementation under consideration.

O(1) describes the amount of structural management work, not a guarantee that every call has identical absolute latency. Allocating a new node, memory activity, and the runtime environment can still affect wall-clock time.

### 2.4. Why Is the Middle Still O(n)?

If `i` is near `n/2`, both distances are proportional to `n`. Taking `n/2` steps instead of `n` steps is beneficial in raw step count, but:

~~~text
Theta(n/2) = Theta(n)
~~~

Reducing a constant factor does not change the order of growth. For accessing an arbitrary position, the worst case of index-based node lookup remains linear.

The complete phrasing is: **position-dependent, fast at both ends, and linear in the middle region in the worst case**. Simply saying "`LinkedList.get` is O(n)" works as a worst-case bound, but it omits useful information about positions near the head or tail.

## 3. Which Methods Pay the Node Lookup Cost?

### 3.1. get(i): Find Then Read the Element

`get(i)` validates the index, finds the node, and then reads the element inside the node. Reading the element once the node is found takes constant time; traversing the links creates the position-dependent cost.

Two consecutive calls `get(i)` and `get(i+1)` do not automatically share a cursor sitting at `i`. In the referenced OpenJDK implementation, each `get` call restarts the node lookup from the head or tail.

This is a crucial difference between repeated index-based access and traversal with an iterator.

### 3.2. set(i, value): Find Then Replace the Element Reference

`set` does not insert a node and does not change the number of elements. However, it still must find the node at `i` before replacing the value.

Consequently, one cannot deduce from "it only replaces a single reference" that the entire `set(i, value)` call is always O(1). If the index lies in the middle, the lookup step is still linear.

If an algorithm calls both `get(i)` and `set(i, newValue)` for every `i`, it may repeat the lookup traversal twice at each position. Using a `ListIterator` to read and replace at the current traversal position avoids re-locating by index.

### 3.3. remove(i): Find Then Unlink

Once the node is located, removing it from the linked chain requires updating a fixed number of references and the head/tail pointers when necessary. It does not shift all subsequent elements as in an array.

However, `remove(i)` starts with an index, so it must still find the node. The cost of the full operation is:

~~~text
find node at i + unlink at that node
~~~

For a middle node, the first part is linear and the second part is constant; the total remains linear.

There is no pass over all subsequent nodes just to decrement an "index number" stored on them. An index is a logical position derived from order, not a mandatory field updated on every node.

### 3.4. add(i, value): Pay Attention to Insertion at the End

The valid domain for insertion is wider than for reading:

~~~text
get/set/remove:  0 <= i < n
add:             0 <= i <= n
~~~

In the implementation under consideration:

- If `i = n`, it can link directly at the tail.
- If `i < n`, it must find the node currently at `i` and link the new node before it.
- Linking the new node once the position is known takes constant work, aside from allocation.

An empty list has only insertion position 0, but no valid read or removal positions.

Do not apply the formula `min(i, n−1−i)` directly to `i = n`: that formula finds an existing element, whereas `i = n` is an insertion gap after the last element.

### 3.5. Two-Phase Breakdown Table

| Operation on LinkedList | Requires lookup by index? | Work after having the node/position |
|---|---|---|
| `get(i)` | Yes | Read element |
| `set(i, x)` | Yes | Replace element |
| `remove(i)` | Yes | Unlink node and update links |
| `add(i, x)`, i < n | Yes | Link new node before the located node |
| `add(n, x)` | No need to traverse to a middle node | Link at tail |
| `getFirst()`, `getLast()` | No | Read head/tail directly |
| Positioned `ListIterator.next()` | No re-lookup by index | Advance to next node and return element |

The table describes structural management under valid usage conditions. It does not include application work performed on the element and is not a real-time latency guarantee.

## 4. Major Trap: An Index-Based `for` Loop Can Become O(n²)

Consider an illustrative method body snippet:

~~~java
long sum = 0;
for (int index = 0; index < values.size(); index++) {
    sum += values.get(index);
}
~~~

If `values` is a `LinkedList`, each `get(index)` call searches from one of the ends. The loop does not retain the position from the previous iteration.

### 4.1. With n = 8, Summing the Steps of Each `get`

The sequence of lookup steps is:

~~~text
index:       0  1  2  3  4  5  6  7
steps:       0  1  2  3  3  2  1  0

total = 12 link traversal steps
~~~

In addition to these 12 steps, there are 8 element-processing iterations and constant overhead per iteration. Do not confuse the number of lookup steps with the total number of machine instructions.

### 4.2. Proving the Total in Terms of n

If `n = 2m` is even, the distance sequence is:

~~~text
0, 1, ..., m-1, m-1, ..., 1, 0
~~~

Total:

~~~text
2 * (0 + 1 + ... + m-1) = m(m-1)
~~~

If `n = 2m+1` is odd, the sequence is:

~~~text
0, 1, ..., m-1, m, m-1, ..., 1, 0
~~~

Total:

~~~text
2 * (0 + 1 + ... + m-1) + m = m^2
~~~

Both are Θ(n²). Always picking the closer end makes the total smaller than always starting from the head, but it still does not make it linear.

With `n = 1,000`, the total number of lookup steps according to the model is 249,500. A single pass through the list does not need to restart the search 1,000 times.

### 4.3. Caching `size` in a Variable Does Not Fix the Primary Cost

In OpenJDK's `LinkedList`, the size is stored directly. `size()` does not recount the nodes each time.

Changing the condition to `index < cachedSize` changes how the loop is written, but it does not eliminate `get(index)` re-finding the node. If the problem is quadratic behavior caused by indexed access, you must change the traversal method or the data structure.

Similarly, iterating the index downward from `n−1` to `0` merely reverses the order of distances. The total number of lookup steps remains the same if every index is read once that way.

### 4.4. Repeated Access to the Same Middle Position Also Needs Reconsideration

If `get(n/2)` is called `q` independent times on an unchanged list, each call still has to walk to the middle node. The total lookup work can be Θ(qn).

If you truly only need to reuse the same element and the list does not change in a way that affects requirements, you can retrieve the element once and use the variable holding it. If you need to traverse neighboring elements, use a positioned iterator.

Do not assume the library will cache the most recently accessed node between `get` calls.

## 5. Iterators Retain Position: Pay the Lookup Cost Once, Then Advance Step by Step

### 5.1. Sequential Traversal with `for-each`

Illustrative snippet:

~~~java
long sum = 0;
for (int value : values) {
    sum += value;
}
~~~

With `LinkedList`, the iterator walks through the existing node chain. Each advance uses the next link rather than converting an integer into a position by searching again from the head or tail.

A single pass over `n` elements has O(n) structural cost, plus the work to process each element. Shorter code is not what makes it faster; preserving positional state across steps is the reason.

The example using `int` assumes elements are non-`null`, because reading into a primitive variable requires unboxing. If the list allows `null`, the handling must match the data.

### 5.2. `listIterator(i)` Is Not Free in the Middle

A `ListIterator` has a cursor positioned between elements. With `listIterator(i)`, the first call to `next()` returns the element at `i` if elements remain.

To place the cursor in the middle of a `LinkedList`, the implementation must find the corresponding node. Therefore:

~~~text
create iterator at position i:
    pay initial positioning cost

then next/previous:
    follow links, each step O(1)
~~~

If traversing `k` elements after positioning at `i < n`, the cost model is:

~~~text
O(1 + min(i, n - 1 - i) + k)
~~~

Instead of calling `get(i)`, `get(i+1)`… and paying the re-lookup cost for every position, we position once.

### 5.3. Position `size` Is a Valid Cursor at the End

`listIterator(n)` is valid: the cursor sits after the last element, and `hasNext()` is `false`; if the list is non-empty, `previous()` can return the last element.

In the OpenJDK implementation under consideration, creating an iterator at the end does not traverse `n` nodes. It uses the tail state directly.

Conversely, `get(n)` is invalid because there is no element at position `n`. You must distinguish an **element index** from a **cursor position / insertion gap**.

### 5.4. Keeping One Iterator for Multiple Local Edits

Once a `LinkedList`'s `ListIterator` has reached a position, valid calls to `set`, `add`, and `remove` can operate using the node references it currently holds. There is no need to re-locate the node by index for each operation.

For example: position before element 3, read it, replace its value, insert an element next to it, read the next element, and remove the element just read. The positioning cost is paid upfront; subsequent local updates use a fixed number of link operations.

However, these methods have state rules:

- `set` and `remove` require an element to have just been returned by `next` or `previous`.
- After `add`, the "last returned element" state used by `set`/`remove` is reset.
- Do not call `remove` twice for a single read.
- Do not structurally modify the list through another path and continue using the iterator as if its position were still valid.

The program below calls `next` after `add` before calling `remove`, so it removes the element that was just read. Having a favorable cost profile does not allow bypassing the operation contract.

### 5.5. Creating a New Iterator in Every Iteration Can Still Be Slow

If every loop iteration calls `listIterator(i)` and then calls `next()` only once, we are still repeating the positioning work. Having the word "iterator" in the syntax does not guarantee a linear algorithm.

The benefit comes from keeping and advancing that same iterator across the positions to be traversed. Count the number of positioning operations, not just the number of `next` calls.

## 6. Complete Program: Index-Based Access and Sequential Traversal

The program creates a real `LinkedList`, reads positions, and compares traversal results. The `modeledHops` and `initialHops` columns are **computed by formula**, not numbers read from inside the JVM.

The goal is to clarify the mechanism and verify the calculations; do not use this example to conclude a nanosecond speed ratio.

### 6.1. Source Code

Save as `LinkedListIndexCostDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.LinkedList;
import java.util.List;
import java.util.ListIterator;
import java.util.Objects;
import java.util.RandomAccess;

public class LinkedListIndexCostDemo {
    // Number of link traversal hops according to the model, not measuring JVM internals.
    static int modeledHops(int size, int index) {
        Objects.checkIndex(index, size);
        return Math.min(index, size - 1 - index);
    }

    static long allIndexHops(int size) {
        if (size < 0) {
            throw new IllegalArgumentException("negative size");
        }
        long half = size / 2L;
        return size % 2 == 0 ? half * (half - 1) : half * half;
    }

    public static void main(String[] args) {
        LinkedList<Integer> values = new LinkedList<>();
        for (int value = 0; value < 8; value++) {
            values.addLast(value);
        }
        System.out.println("values: " + values);
        System.out.println("index, direction, modeledHops, value");
        for (int index = 0; index < values.size(); index++) {
            String direction = index < values.size() / 2 ? "HEAD" : "TAIL";
            System.out.printf("%d, %s, %d, %d%n", index, direction,
                    modeledHops(values.size(), index), values.get(index));
        }

        long indexedSum = 0;
        long indexedHops = 0;
        for (int index = 0; index < values.size(); index++) {
            indexedSum += values.get(index);
            indexedHops += modeledHops(values.size(), index);
        }
        long sequentialSum = 0;
        int visits = 0;
        for (int value : values) {
            sequentialSum += value;
            visits++;
        }
        System.out.printf("get loop: sum=%d, modeledHops=%d%n",
                indexedSum, indexedHops);
        System.out.printf("for-each: sum=%d, visits=%d%n", sequentialSum, visits);
        System.out.println("same sums: " + (indexedSum == sequentialSum));

        for (int size : new int[] {8, 9, 10, 100, 1000}) {
            System.out.printf("formula only: n=%d, allIndexHops=%d%n",
                    size, allIndexHops(size));
        }

        int start = 3;
        int width = 3;
        ListIterator<Integer> range = values.listIterator(start);
        long rangeSum = 0;
        for (int count = 0; count < width; count++) {
            rangeSum += range.next();
        }
        System.out.printf("range [3,6): initialHops=%d, nextCalls=%d, sum=%d%n",
                modeledHops(values.size(), start), width, rangeSum);

        ListIterator<Integer> editor = values.listIterator(3);
        int first = editor.next();
        editor.set(30);
        editor.add(31);
        int second = editor.next();
        editor.remove();
        System.out.printf("editor read=%d then %d, values=%s%n",
                first, second, values);

        ListIterator<Integer> reverse = values.listIterator(values.size());
        System.out.println("iterator at size, previous: " + reverse.previous());
        try {
            values.get(values.size());
        } catch (IndexOutOfBoundsException exception) {
            System.out.println("get(size): IndexOutOfBoundsException");
        }

        List<Integer> linkedAsList = values;
        List<Integer> arrayAsList = new ArrayList<>(values);
        System.out.println("LinkedList RandomAccess: "
                + (linkedAsList instanceof RandomAccess));
        System.out.println("ArrayList RandomAccess: "
                + (arrayAsList instanceof RandomAccess));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~shell
javac --release 17 -encoding UTF-8 LinkedListIndexCostDemo.java
java LinkedListIndexCostDemo
~~~

### 6.2. Standard Output Result

~~~text
values: [0, 1, 2, 3, 4, 5, 6, 7]
index, direction, modeledHops, value
0, HEAD, 0, 0
1, HEAD, 1, 1
2, HEAD, 2, 2
3, HEAD, 3, 3
4, TAIL, 3, 4
5, TAIL, 2, 5
6, TAIL, 1, 6
7, TAIL, 0, 7
get loop: sum=28, modeledHops=12
for-each: sum=28, visits=8
same sums: true
formula only: n=8, allIndexHops=12
formula only: n=9, allIndexHops=16
formula only: n=10, allIndexHops=20
formula only: n=100, allIndexHops=2450
formula only: n=1000, allIndexHops=249500
range [3,6): initialHops=3, nextCalls=3, sum=12
editor read=3 then 4, values=[0, 1, 2, 30, 31, 5, 6, 7]
iterator at size, previous: 7
get(size): IndexOutOfBoundsException
LinkedList RandomAccess: false
ArrayList RandomAccess: true
~~~

### 6.3. Explanation of Results

The eight index lines show the lookup direction and the modeled distance. Both ends have 0 steps; the middle region requires 3 steps for `n = 8`.

Both summation methods yield 28. This verifies that changing the traversal method does not alter the result on the test data. The algorithmic difference lies in the `get` loop re-finding the position while `for-each` advances continuously.

The `formula only` lines compute totals strictly by formula; they do not allocate lists or benchmark thousands of calls. `long` is used for products and sums to prevent `int` overflow as `n` grows.

For the range `[3,6)`, the iterator is placed at 3 with a single modeled positioning operation, then `next` is called three times to receive 3, 4, 5 and compute the sum 12. `initialHops` and `nextCalls` count two different kinds of work, not two time columns to be added together into nanoseconds.

The `editor` section:

1. Reads 3 and replaces it with 30.
2. Inserts 31 at the cursor position, before 4.
3. Reads 4 and removes it through the iterator itself.
4. Produces `[0, 1, 2, 30, 31, 5, 6, 7]`.

This is an example of local updates after positioning. It does not imply that `values.add(3, ...)` automatically skips the lookup step.

`listIterator(size)` can step backward to 7, whereas `get(size)` throws `IndexOutOfBoundsException`. The program prints the exception class name itself so the output does not depend on the specific message string of a particular JDK build.

The two `RandomAccess` lines illustrate that even when held through variables of type `List`, the underlying objects still have different access characteristics.

## 7. List and RandomAccess: Same Interface Does Not Mean Same Cost

### 7.1. The Variable Type Does Not Change the Underlying Structure

Illustrative snippet:

~~~java
List<String> values = new LinkedList<>();
~~~

The call `values.get(i)` still executes `LinkedList`'s implementation. Declaring against an interface reduces type coupling, but it does not turn a linked list into an array.

When writing a method that accepts `List<T>`, avoid assuming that every `get(i)` is O(1). A `for-each` loop usually expresses intent better when the goal is simply to inspect each element once.

The `List` contract permits indexed access; it does not guarantee that every implementing class has the same cost for that access pattern. See [Java 17 List](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html).

### 7.2. RandomAccess Is a Marker for Algorithms to Choose a Traversal Strategy

`RandomAccess` is a marker interface for `List` implementations that support fast random access. `ArrayList` implements this marker; `LinkedList` does not.

The [Java 17 RandomAccess documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/RandomAccess.html) explains the role of this marker so generic algorithms can avoid choosing an unfavorable access pattern across different list types.

It does not automatically optimize a loop already written by the application. If code still calls `get(i)` for every `i` on a `LinkedList`, there is no automatic mechanism that rewrites that loop into an iterator just because a marker interface exists in the library.

When a specialized dual strategy is unnecessary, iterating via an iterator is a simple way to avoid depending on random-access capability. When choosing between two strategies is genuinely needed, checking the marker should go hand in hand with algorithmic analysis and specific requirements.

### 7.3. Copying to an ArrayList for Heavy Indexed Access

If you already have a stable `LinkedList` but a later phase requires many scattered index accesses, you can consider:

~~~java
List<String> indexed = new ArrayList<>(linkedSource);
~~~

A one-time conversion must read the source and allocate a structure holding the references, which takes linear time and extra memory. After that, index-based `get` access on `ArrayList` runs in constant time, per [Java 17 ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html).

If you only read one element or iterate once, creating a copy may be unnecessary. If the source continues to change, the copy does not automatically reflect new structural changes; timing and ownership must be chosen clearly.

The collection copy constructor does not deep-copy element objects. Both structures may still hold references to the same mutable objects.

## 8. Do Not Confuse Lookup by Index with Lookup by Value

### 8.1. `indexOf` Does Not Know the Target Position in Advance

`get(i)` knows `i` and finds the node there. `indexOf(value)` needs to discover where the first matching element is located.

In the implementation under consideration, `indexOf` walks sequentially from the head, checking the element at each node. It does not try `get(0)`, `get(1)`, `get(2)` in a loop that triggers repeated lookups for each position.

Therefore, searching by value inspects O(n) elements in the worst case, plus comparison cost. Do not look at a contract specification phrased in terms of `get(i)` and conclude that the implementation code must use a quadratic `get` loop.

### 8.2. Calling `indexOf` Followed by `get` May Traverse a Segment Twice

If you only need the object matching a condition, finding its index first and then calling `get` again can cause the program to walk through part of the list a second time.

A single traversal returning the found element directly may suffice. If you need to modify or remove the element being searched for, an iterator used according to its rules can retain the position.

Not every second pass is a bug worth optimizing; this is a way to identify duplicate work so you can evaluate it when data is large or the operation repeats frequently.

### 8.3. `remove(Object)` Is Not `remove(int)`

With a list of integers, `remove(2)` selects the overload that removes at index 2; `remove(Integer.valueOf(2))` searches for and removes an element equal to the value 2.

Removing by value does not obtain the node directly just because the target object is passed in. The lookup cost must still be accounted for before the unlinking step occurs.

## 9. Limitations of the Cost Model

### 9.1. Link Hop Count Is Not Wall-Clock Time

A step from the current node to the next node requires reading a reference. Actual latency can depend on how nodes are laid out in memory, CPU caches, the JVM, and system load.

Hop counts help explain asymptotic growth and repeated work. They do not allow claiming "every hop takes exactly X nanoseconds" or "this list is always exactly Y times slower than that structure."

If a performance decision is needed in a real application, you must measure the specific access pattern, data size, and target environment.

### 9.2. User Work Is Added Separately

Iterating with an iterator is structurally O(n). If each element triggers a network query, a search over another collection, or an O(n) computation, total application cost can exceed O(n).

Similarly, accessing the head of the list being O(1) does not make the expression `getFirst().expensiveOperation()` O(1) with respect to total work.

### 9.3. Formulas Assume a Valid, Stable State During Analysis

`n` and `i` are understood at the moment of the operation. If elements are added or removed, the size and the indices of subsequent elements can change; calculations must be updated accordingly.

If `i` is invalid, the method checks the index and throws an exception rather than applying the node lookup formula as if a node existed outside the list.

`LinkedList` is not inherently thread-safe when multiple threads modify its structure concurrently. Iterator fail-fast behavior is not a synchronization mechanism and is not guaranteed to detect every concurrent access bug. The example in this article uses a single thread.

### 9.4. Holding an Iterator Means Holding Active Usage State

An iterator is useful because it retains position, but that position comes with state and validity tied to the list's structure. Do not treat an iterator as a persistent identifier to store away while mutating the list through multiple independent paths.

If a problem requires stable references to domain objects, design an identifier on the element itself. Do not equate it with an index or a stale iterator.

## 10. Common Reasoning Mistakes

| Claim | Accurate Understanding |
|---|---|
| LinkedList has `get`, so indexed access works like an array | It must locate the node by traversing links |
| Every `get` starts from the head | It starts from whichever of head or tail is closer |
| Being doubly linked makes middle lookup O(1) | The middle is still a number of steps proportional to `n` away from both ends |
| Taking `n/2` steps instead of `n` is no longer linear | A factor of 1/2 does not change the Θ(n) order |
| `get(0)` must also traverse `n` nodes | It holds a head reference and does not need to traverse links |
| `set` only replaces a value, so the whole operation is always O(1) | The index-based node lookup step must be included |
| Removing a node is O(1), so `remove(i)` is always O(1) | `remove(i)` must still locate the position first |
| Knowing the element object means already having its node | The element and the node containing it are two different objects |
| An index-based `get` loop walks the list only once | Each `get` can restart the lookup |
| Iterating indices in reverse avoids quadratic cost | It only reverses the order of the distances |
| Calling `listIterator(i)` always constructs in O(1) | Creating it in the middle still requires finding the position |
| Creating a new iterator each iteration is still a single traversal | The positioning cost can be repeated every time |
| Declaring the variable as `List` makes costs identical | The concrete implementation object determines the mechanism |
| Lacking `RandomAccess` means `get` cannot be used | `get` is available, but algorithms must account for its cost |
| Searching by value necessarily calls `get(i)` repeatedly | The library traverses links directly |

## 11. Self-Check Exercises

### Exercise 1: Distance from Both Ends

A list has `n = 12`. How many modeled steps are needed to find `i = 2` and `i = 9`?

**Explanation:** `i = 2` has distance 2 from the head and 9 from the tail, choosing 2. `i = 9` has distance 9 from the head and 2 from the tail, also choosing 2. Symmetric positions share the same minimum distance.

### Exercise 2: Middle Node of an Odd Element Count

`n = 9`, find `i = 4`. How many steps does it take? Does choosing head or tail change the asymptotic order?

**Explanation:** Both distances equal 4. The referenced OpenJDK build chooses the tail branch on this tie, but the step count and asymptotic cost order do not change.

### Exercise 3: Loop Reading Every Index

With `n = 10`, what is the total number of lookup steps from `get(0)` through `get(9)`?

**Explanation:** `n = 2m` with `m = 5`, so the total is `m(m−1) = 20`. Aside from the 20 traversal steps, there is constant overhead across the 10 accesses. As `n` grows, the total is quadratic.

### Exercise 4: Reading a Contiguous Range

You need to read 100 consecutive elements starting in the middle of a large linked list. Should you create an iterator once or call `get` for each index?

**Explanation:** An iterator positioned once and advanced across 100 elements avoids re-finding the node from the head/tail for each index. You must account for the initial positioning cost and ensure the read range is valid.

### Exercise 5: Modifying at an Already Reached Position

A `ListIterator` has just returned an element. Why can `iterator.set(x)` have constant structural cost while `list.set(i, x)` in the middle can be linear?

**Explanation:** The iterator retains the node just returned; the index-based call must locate the node again. Both replace the element, but they receive positional information differently.

### Exercise 6: Position n

A list has 5 elements. Do `get(5)`, `add(5, x)`, and `listIterator(5)` share the same validity?

**Explanation:** No. `get(5)` has no element to read. The other two operations allow the position after the last element: inserting at the tail or placing the cursor at the end.

When analyzing an operation on a `LinkedList`, ask: **is the position already held as a valid cursor, or do we only have an index number?** The answer determines whether an extra node-lookup cost must be paid, and helps choose between indexed access, holding an iterator, or switching to a more suitable storage structure.
