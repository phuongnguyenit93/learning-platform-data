# pollFirst, pollLast, descendingSet, and descendingIterator

## 1. Choosing How to Read or Remove Elements in Order

Suppose a set stores the levels `10, 20, 30, 40` in ascending order. You might need to inspect the smallest level while keeping the data, remove the largest level for processing, or read from largest to smallest.

Those three needs differ in two respects: **the direction of traversal** and **whether elements are removed**. If you mix them up, code meant only for display might lose data, while code meant to process each element might loop forever because nothing is removed.

The four methods in this lesson belong to `NavigableSet`:

- `pollFirst()`: retrieves and removes the first element.
- `pollLast()`: retrieves and removes the last element.
- `descendingSet()`: creates a reverse-order view sharing the same elements as the source set.
- `descendingIterator()`: creates an iterator that traverses in reverse order.

"First" and "last" are determined by the ordering of the specific set or view on which you call the method, not by insertion time. If a reversed `Comparator` is used, the largest number can be at the front of the original set and the smallest number at the front of the reversed view.

This lesson uses `TreeSet` to verify these behaviors using APIs available in Java 17. You should already be familiar with variables, loops, and basic set usage; `NavigableSet`, views, and iterators will be explained before diving into the complete code.

## 2. How Does NavigableSet Relate to Sorted Sets?

`Set` models a collection with no duplicates. `SortedSet` adds an ordering along with operations like `first()`, `last()`, and ordered range views. `NavigableSet` extends it further with navigation operations and the ability to work from both ends.

`TreeSet` is a class that implements `NavigableSet`. It can be declared as:

~~~java
NavigableSet<Integer> values =
        new TreeSet<>(List.of(40, 10, 30, 20));
~~~

This is an illustrative declaration; the complete program below includes the necessary import statements.

The object uses the natural ordering of `Integer`, so normal traversal yields `[10, 20, 30, 40]`. The first element is 10 and the last element is 40, even though 40 appeared first in the source list.

The declared type matters when calling the API. If a variable only has type `Set<Integer>` or `SortedSet<Integer>` in Java 17, the compiler does not allow calling `NavigableSet`-specific methods through that variable. Choose a type that reflects the capabilities the code actually needs instead of casting arbitrarily.

`NavigableSet` also provides neighbor-lookup methods and range views with configurable bounds. In this lesson, we only use a small range view to observe the scope of effect of the four main methods. [Java 17: NavigableSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NavigableSet.html).

## 3. Distinguishing Reading, Polling, and Iterating

For a modifiable `TreeSet`, the following table helps you choose the right operation:

| Operation | Return value | Automatically removes element? | When empty |
| --- | --- | --- | --- |
| `first()` | First element | No | `NoSuchElementException` |
| `last()` | Last element | No | `NoSuchElementException` |
| `pollFirst()` | Removed first element | Yes, if an element exists | Returns `null` |
| `pollLast()` | Removed last element | Yes, if an element exists | Returns `null` |
| `descendingSet()` | A `NavigableSet` viewed in reverse order | Not from creating the view itself | Empty view |
| `descendingIterator()` | An `Iterator` traversing in reverse order | Not from creating or reading itself | `hasNext()` is `false` |

`first` and `last` are read operations. `pollFirst` and `pollLast` are mutating operations. Their behavior when empty is also part of the contract, not just a naming difference. [Java 17: SortedSet.first and last](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SortedSet.html#first()).

An exhausted iterator does not return `null` when `next()` is called. It throws `NoSuchElementException`. Use `hasNext()` to check whether elements remain before calling `next()` again.

Do not lump all of these operations together as "getting first/last." When reviewing a piece of code, clearly identify whether the returned value is an element, a view, or an iterator, and only then reason about its effect on the data.

## 4. pollFirst and pollLast Both Return and Remove an Element

Starting from the initial state:

~~~text
[10, 20, 30, 40]
~~~

calling them in sequence gives:

~~~text
pollFirst() → returns 10; set becomes [20, 30, 40]
pollLast()  → returns 40; set becomes [20, 30]
~~~

Each successful call removes one member from the set. You do not need to call `remove` afterward for the element that was just returned.

When the set is empty, both return `null`. They do not wait for new data to arrive, nor do they automatically load more data from elsewhere. If a program needs to wait for incoming work, that is a different requirement from the `TreeSet` operations covered here.

Do not use `first()` in a loop expecting each read to discard the previous element. If the set does not change, `first()` will keep returning the same first element.

Nor should you assume `pollFirst` returns the earliest-inserted element. `TreeSet` organizes elements by comparison order, so processing via `pollFirst` follows that ordering. If you need first-in, first-out order, you must choose a model suited to event arrival order.

An important consequence when processing work: once `pollFirst` returns, the element has already left the set. If subsequent processing fails, the set does not restore it automatically. Whether to re-insert it or record its processing state is an application-level decision, not a built-in effect of `poll`.

## 5. descendingSet Is a View, Not a Copy

From the set `base = [10, 20, 30]` in natural order:

~~~java
NavigableSet<Integer> descending = base.descendingSet();
~~~

gives a view with traversal order `[30, 20, 10]`.

You can visualize it as:

~~~text
shared members: 10, 20, 30

base:        10 → 20 → 30
descending:  30 → 20 → 10
~~~

The two lines represent two viewing directions over shared data. There is no step that permanently reverses `base`'s ordering rule. After creating the view, iterating over `base` still yields `10, 20, 30`.

Adding or removing through one side is visible from the other:

~~~text
descending.add(25)
base        → [10, 20, 25, 30]
descending  → [30, 25, 20, 10]
~~~

If you then add `40` through `base`, the reversed view will show `[40, 30, 25, 20, 10]` when traversed again.

Creating a view does not clone every element and does not make the data independent. If you pass `descending` to a method that may remove members, that method can also mutate the original set. This is an important part of a method's contract, even if a variable name only suggests "data for display."

According to the API, the view's ordering is equivalent to reversing the source's comparison rule. Creating a reversed view of a reversed view is essentially equivalent to the original set; there is no need to assume the two variables hold the same object reference. [Java 17: TreeSet.descendingSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html#descendingSet()).

## 6. Both Ends Swap Roles in a Reversed View

Suppose `base` uses natural order and currently contains:

~~~text
base        = [10, 20, 25, 30, 40]
descending  = [40, 30, 25, 20, 10]
~~~

Then:

| Call | Removed member | Equivalent on the original set |
| --- | --- | --- |
| `descending.pollFirst()` | `40` | Polls the last element of `base` |
| `descending.pollLast()` | `10` | Polls the first element of `base` |

Each row describes the relationship between the two ends; if run consecutively, each call sees the state left by the previous one.

It is not just the printed sequence that is reversed. Directional operations on the view are also interpreted in reverse order. Therefore, `descending.first()` is `base.last()` when the set is non-empty, and `descending.last()` is `base.first()`.

For the same state and the same member range, you can use this rule of thumb:

~~~text
first of reversed view ↔ last of source
last of reversed view  ↔ first of source
~~~

If the source is a bounded range view of a larger set, "source" here refers to that range view itself. The last element of the range is not necessarily the last element of the entire larger set.

Creating `descending` does not change the meaning of `base.pollFirst()`. Calls on `base` still use `base`'s direction; calls on `descending` use the view's direction.

## 7. descendingIterator Only Creates a Single Reverse Pass

If you only need to traverse elements in reverse order, you can use:

~~~java
Iterator<Integer> iterator = values.descendingIterator();
while (iterator.hasNext()) {
    Integer value = iterator.next();
    System.out.println(value);
}
~~~

This snippet assumes `values` is a `NavigableSet<Integer>`. `hasNext` checks whether an element remains; `next` retrieves the next element in the traversal. There is no removal in this snippet.

With natural-order `values = [1, 2, 3, 4]`, the traversal produces `4, 3, 2, 1`, while the set still retains all four elements.

`descendingIterator()` has the same traversal effect as `descendingSet().iterator()`. Choose the first when you only need an iterator; choose the view when you need to continue using set operations in reverse order.

The name "descending iterator" does not turn the return type into `ListIterator`. You still call `next()` to advance through the chosen reverse traversal—you do not call `previous()`, do not insert elements at a list position, and do not use indices.

An iterator holds the state of **a single traversal pass**. Once exhausted, you must create a new iterator to read again. Calling `hasNext` does not rewind to the start, and calling `next` past the end throws an exception.

## 8. Removing During Iteration Using the Iterator Itself

`TreeSet`'s iterator supports `remove()`. This method does not take a value to search for; it removes the last element returned by `next()` on that same iterator.

Example filtering out even numbers during a reverse traversal:

~~~java
Iterator<Integer> iterator = values.descendingIterator();
while (iterator.hasNext()) {
    int value = iterator.next();
    if (value % 2 == 0) {
        iterator.remove();
    }
}
~~~

This snippet is verified in the full program with the set `[1, 2, 3, 4]`. It visits `4, 3, 2, 1` and leaves `[1, 3]`.

Reverse traversal order does not invert the even-number condition. It only changes the order in which elements are tested against that condition.

State rules for `Iterator.remove`:

- A call to `next` must have returned an element beforehand.
- After each call to `next`, `remove` may be called at most once.
- Calling it before `next` or calling it a second time for the same element results in `IllegalStateException` in this example's iterator.
- `remove` is an optional operation on the `Iterator` interface; do not assume every iterator of every data structure supports it.

Do not replace `iterator.remove()` with `values.remove(value)` or `values.pollLast()` inside the same loop and then continue using the old iterator. Doing so modifies the data outside the update path the iterator is tracking. [Java 17: Iterator.remove](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html#remove()).

## 9. Complete Program Using Java 17

Save this as `NavigableSetEndsDemo.java`. The program separates the data for each example group so that removals in one group do not distort results in another.

`readAll` only consumes an iterator and records the results into a list. `drainFirst` removes all members using `pollFirst` and empties the passed-in set. The two methods serve different purposes.

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.Iterator;
import java.util.List;
import java.util.NavigableSet;
import java.util.TreeSet;

public class NavigableSetEndsDemo {
    static <E> List<E> readAll(Iterator<E> iterator) {
        List<E> values = new ArrayList<>();
        while (iterator.hasNext()) {
            values.add(iterator.next());
        }
        return values;
    }

    static <E> List<E> drainFirst(NavigableSet<E> set) {
        List<E> removed = new ArrayList<>();
        while (!set.isEmpty()) {
            removed.add(set.pollFirst());
        }
        return removed;
    }

    public static void main(String[] args) {
        NavigableSet<Integer> ends = new TreeSet<>(List.of(40, 10, 30, 20));
        System.out.println("ends initial=" + ends);
        System.out.println("read first/last=" + ends.first() + "/" + ends.last());
        System.out.println("after read=" + ends);
        System.out.println("pollFirst=" + ends.pollFirst());
        System.out.println("pollLast=" + ends.pollLast());
        System.out.println("ends remaining=" + ends);
        System.out.println("drained=" + drainFirst(ends));
        System.out.println("ends empty=" + ends.isEmpty());
        System.out.println("empty pollFirst=" + ends.pollFirst());
        System.out.println("empty pollLast=" + ends.pollLast());

        NavigableSet<Integer> base = new TreeSet<>(List.of(10, 20, 30));
        NavigableSet<Integer> descending = base.descendingSet();
        System.out.println("base=" + base);
        System.out.println("descending=" + descending);
        System.out.println("descending first/last="
                + descending.first() + "/" + descending.last());
        descending.add(25);
        System.out.println("base after view add=" + base);
        base.add(40);
        System.out.println("view after base add=" + descending);
        System.out.println("view pollFirst=" + descending.pollFirst());
        System.out.println("base after view pollFirst=" + base);
        System.out.println("view pollLast=" + descending.pollLast());
        System.out.println("base after view pollLast=" + base);
        System.out.println("double reverse order="
                + new ArrayList<>(base).equals(
                        new ArrayList<>(descending.descendingSet())));

        NavigableSet<Integer> copy = new TreeSet<>(descending);
        base.add(35);
        System.out.println("base after later add=" + base);
        System.out.println("view after later add=" + descending);
        System.out.println("independent copy=" + copy);
        System.out.println("copy pollFirst=" + copy.pollFirst());
        System.out.println("base after copy poll=" + base);

        NavigableSet<Integer> iteration = new TreeSet<>(List.of(1, 2, 3, 4));
        System.out.println("descending traversal=" + readAll(iteration.descendingIterator()));
        System.out.println("after traversal=" + iteration);
        Iterator<Integer> iterator = iteration.descendingIterator();
        try {
            iterator.remove();
        } catch (IllegalStateException exception) {
            System.out.println("remove before next=" + exception.getClass().getSimpleName());
        }
        List<Integer> visited = new ArrayList<>();
        while (iterator.hasNext()) {
            int value = iterator.next();
            visited.add(value);
            if (value % 2 == 0) {
                iterator.remove();
            }
        }
        System.out.println("visited while filtering=" + visited);
        System.out.println("after iterator remove=" + iteration);
        try {
            iterator.next();
        } catch (java.util.NoSuchElementException exception) {
            System.out.println("next after end=" + exception.getClass().getSimpleName());
        }

        NavigableSet<Integer> custom = new TreeSet<>(Comparator.reverseOrder());
        custom.addAll(List.of(8, 2, 5));
        System.out.println("custom order=" + custom);
        System.out.println("custom descending=" + custom.descendingSet());
        System.out.println("custom descending iterator="
                + readAll(custom.descendingIterator()));
        System.out.println("custom view pollFirst=" + custom.descendingSet().pollFirst());
        System.out.println("custom after view poll=" + custom);
        System.out.println("custom pollFirst=" + custom.pollFirst());
        System.out.println("custom remaining=" + custom);

        NavigableSet<Integer> all = new TreeSet<>(List.of(1, 2, 3, 4, 5));
        NavigableSet<Integer> range = all.subSet(2, true, 5, false);
        NavigableSet<Integer> reverseRange = range.descendingSet();
        System.out.println("reverse range=" + reverseRange);
        System.out.println("range pollFirst=" + reverseRange.pollFirst());
        System.out.println("all after range poll=" + all);
        try {
            reverseRange.add(5);
        } catch (IllegalArgumentException exception) {
            System.out.println("outside range=" + exception.getClass().getSimpleName());
        }

        NavigableSet<String> nullable =
                new TreeSet<>(Comparator.nullsFirst(Comparator.naturalOrder()));
        nullable.addAll(Arrays.asList(null, "b", "a"));
        System.out.println("nullable initial=" + nullable);
        System.out.println("nullable first poll=" + nullable.pollFirst());
        System.out.println("empty after null poll=" + nullable.isEmpty());
        System.out.println("nullable remaining=" + nullable);
        System.out.println("nullable drained=" + drainFirst(nullable));
        System.out.println("nullable empty poll=" + nullable.pollFirst());
        nullable.addAll(Arrays.asList(null, "b", "a"));
        System.out.println("nullable full drain=" + drainFirst(nullable));
        System.out.println("nullable finally empty=" + nullable.isEmpty());
    }
}
~~~

Compile and run in the directory containing the file:

~~~shell
javac --release 17 -encoding UTF-8 NavigableSetEndsDemo.java
java NavigableSetEndsDemo
~~~

Use JDK 17 or later. `--release 17` enforces checking code and APIs against Java 17. The filename must match the `public` class name.

Expected output:

~~~text
ends initial=[10, 20, 30, 40]
read first/last=10/40
after read=[10, 20, 30, 40]
pollFirst=10
pollLast=40
ends remaining=[20, 30]
drained=[20, 30]
ends empty=true
empty pollFirst=null
empty pollLast=null
base=[10, 20, 30]
descending=[30, 20, 10]
descending first/last=30/10
base after view add=[10, 20, 25, 30]
view after base add=[40, 30, 25, 20, 10]
view pollFirst=40
base after view pollFirst=[10, 20, 25, 30]
view pollLast=10
base after view pollLast=[20, 25, 30]
double reverse order=true
base after later add=[20, 25, 30, 35]
view after later add=[35, 30, 25, 20]
independent copy=[30, 25, 20]
copy pollFirst=30
base after copy poll=[20, 25, 30, 35]
descending traversal=[4, 3, 2, 1]
after traversal=[1, 2, 3, 4]
remove before next=IllegalStateException
visited while filtering=[4, 3, 2, 1]
after iterator remove=[1, 3]
next after end=NoSuchElementException
custom order=[8, 5, 2]
custom descending=[2, 5, 8]
custom descending iterator=[2, 5, 8]
custom view pollFirst=2
custom after view poll=[8, 5]
custom pollFirst=8
custom remaining=[5]
reverse range=[4, 3, 2]
range pollFirst=4
all after range poll=[1, 2, 3, 5]
outside range=IllegalArgumentException
nullable initial=[null, a, b]
nullable first poll=null
empty after null poll=false
nullable remaining=[a, b]
nullable drained=[a, b]
nullable empty poll=null
nullable full drain=[null, a, b]
nullable finally empty=true
~~~

## 10. Reading the Output by Its Effect on the Data

### 10.1. Reading First/Last Differs From Polling

`read first/last=10/40` paired with `after read=[10, 20, 30, 40]`: the two read operations do not remove anything.

After `pollFirst=10` and `pollLast=40`, the set only has `[20, 30]` left. `drainFirst` returns the list `[20, 30]` and the set becomes empty. The last two `poll` calls return `null` because no members remain.

The list returned by `drainFirst` holds the removed data, not a view that continues to change with the now-emptied set.

### 10.2. Views Share Members

`base after view add=[10, 20, 25, 30]` shows that adding through `descending` affects `base`.

`view after base add=[40, 30, 25, 20, 10]` shows the reverse direction: adding 40 through `base` appears when reading the reversed view. This is a fresh read after mutation, not continuing an existing active iterator.

The two `poll` calls through the view remove 40 and 10 from the original set, respectively. Having different variable names does not create two independent stores of members.

### 10.3. Double Reversal Is Checked by Sequence Order

`double reverse order=true` is computed by converting both sides into `ArrayList` instances and comparing them. This checks traversal order, not just membership.

If you only used `base.equals(descending)`, it would also return `true` because `Set.equals` ignores iteration order. Set equality is not proof that both sides traverse data in the same direction.

### 10.4. Iterators Read Without Losing Elements

`descending traversal=[4, 3, 2, 1]` paired with `after traversal=[1, 2, 3, 4]` confirms that read-only iteration does not shrink the set.

In the subsequent filtering pass, `visited while filtering` still contains all four numbers in reverse order. Only 4 and 2 are removed via `iterator.remove`, leaving `[1, 3]`.

The `remove before next` and `next after end` errors represent two different state errors: there is not yet a valid element to remove, and there are no more elements to read.

## 11. A Reversed Comparator Can Make descending Numerically Ascending

The program creates:

~~~java
NavigableSet<Integer> custom =
        new TreeSet<>(Comparator.reverseOrder());
~~~

With the data `8, 2, 5`, the ordering of the original set is:

~~~text
custom                 = [8, 5, 2]
custom.descendingSet() = [2, 5, 8]
~~~

"Descending" means reversing **the source's current order**, not a mandate to print larger numbers before smaller ones.

Therefore:

~~~text
custom.descendingSet().pollFirst() → returns 2
custom afterwards                  → [8, 5]

custom.pollFirst()                → returns 8
custom afterwards                  → [5]
~~~

Both calls share the name `pollFirst`, yet the two target objects have opposite directions. Memorizing "pollFirst gets the smallest number" would predict both calls above incorrectly.

When a set holds domain objects, replace "large/small number" with the comparator's rule: descending score, ascending timestamp, or a chain of criteria. Read the source's rule accurately and reverse its direction to understand the view.

Reversing the order does not change which pairs of elements the comparator treats as equivalent. `descendingSet` is still a set over the same members; it does not restore entries that were treated as duplicates when added.

## 12. An Independent Copy Differs From a Reversed View

If you need to modify data in reverse order without mutating the source's members, create a true copy with the desired ordering rule.

The program uses:

~~~java
NavigableSet<Integer> copy = new TreeSet<>(descending);
~~~

Here `descending` has type `NavigableSet`, which is also a `SortedSet`. The constructor accepting a `SortedSet` preserves the source's ordering. Thus, the copy has sequence `[30, 25, 20]` at the moment of copying.

Afterward, `base.add(35)`:

~~~text
base        = [20, 25, 30, 35]
descending  = [35, 30, 25, 20]
copy        = [30, 25, 20]
~~~

The view sees the new member; the copy does not receive it. Calling `copy.pollFirst()` returns 30 and does not remove 30 from `base`.

However, this is structural independence of the set's membership, not a deep copy of the element objects. If elements are mutable objects, both sets can still hold references to the same objects. In this program, `Integer` is immutable, so there is no element-mutation side effect to confuse things.

You also need to pay attention to which constructor overload is chosen. A source declared only as `Collection` may select the natural-order constructor instead of preserving the reversed rule. When the copy's ordering matters, pass the comparator explicitly or use the right source type for the `SortedSet` constructor. [Java 17: TreeSet constructors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html).

## 13. A Reversed View of a Range Only Acts Within the Range

In the program:

~~~java
NavigableSet<Integer> all = new TreeSet<>(List.of(1, 2, 3, 4, 5));
NavigableSet<Integer> range = all.subSet(2, true, 5, false);
NavigableSet<Integer> reverseRange = range.descendingSet();
~~~

The `range` view contains `2, 3, 4`: inclusive of 2, exclusive of 5. The reversed view is `[4, 3, 2]`.

`reverseRange.pollFirst()` removes 4, not 5, because 5 is outside the range's membership bounds. The larger set becomes `[1, 2, 3, 5]`; members outside the range remain untouched.

Reversing direction does not remove bounds. `reverseRange.add(5)` is still invalid and throws `IllegalArgumentException`. The fact that 5 is currently in the larger set does not put it within the passed-in range.

This matters when writing a method that takes a `NavigableSet` parameter. The method might receive the entire set or only a bounded view. "Draining the passed-in set" via repeated `pollFirst` calls will remove everything visible in that view, not necessarily every member of the original larger set.

Conversely, if what was passed in is indeed a shared view, the polled elements still disappear from the backing structure. A narrower range does not mean data independence.

## 14. null Has Two Meanings When poll Returns

Sets using natural ordering in most examples do not allow `null` elements. Under that model, receiving `null` from `pollFirst` or `pollLast` can serve as a signal that no elements remain.

However, `TreeSet` can accept `null` if given an appropriate comparator. The end of the program uses `Comparator.nullsFirst(Comparator.naturalOrder())`, producing the order `[null, a, b]`.

The first call:

~~~text
nullable.pollFirst() → null
nullable.isEmpty()   → false
nullable             → [a, b]
~~~

removed **an actual member whose value is null**. It does not mean the set was initially empty. After removing `a` and `b`, the next `pollFirst` call also returns `null`, but this time the set truly has nothing left.

The `nullsFirst` wrapper defines how `null` compares against other elements; it does not change the return-value contract of `poll`. [Java 17: Comparator.nullsFirst](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html#nullsFirst(java.util.Comparator)).

Therefore, the following pattern is only appropriate when the data contract excludes `null`:

~~~java
// Illustration: only use when null cannot be a member.
Integer value;
while ((value = values.pollFirst()) != null) {
    System.out.println(value);
}
~~~

If the set has `null` at the front, the loop stops right after removing it and leaves the remaining members unprocessed.

Do not assign a potentially `null` result directly to an `int`. Auto-unboxing a `null` `Integer` throws `NullPointerException` before you can handle the empty signal.

## 15. Draining All Data Requires the Right Stopping Condition

The program's helper method:

~~~java
static <E> List<E> drainFirst(NavigableSet<E> set) {
    List<E> removed = new ArrayList<>();
    while (!set.isEmpty()) {
        removed.add(set.pollFirst());
    }
    return removed;
}
~~~

is taken from the complete code. In a single-threaded context with no intervening mutations, it handles `null` members too because the stopping condition checks emptiness rather than the value of the polled element.

If you pass the original natural-order set, the returned list follows natural order. If you pass a reversed view, the returned list follows reversed order and the corresponding members are removed from the source.

The line `nullable full drain=[null, a, b]` specifically verifies passing a set still containing `null` to the method: both `null` and the two strings are removed, and the set is empty afterward.

The method builds a list of all results to make verification easy. If the goal is to process and discard each element, an application can process them directly instead of accumulating a list; you still need a clear error-handling policy after an element has been removed.

The `isEmpty` followed by `pollFirst` loop is not an atomic pair of operations. With data shared across multiple threads, another actor could change the state between the two calls. Do not carry single-threaded reasoning about this method directly over as a concurrency guarantee for `TreeSet`.

`TreeSet` is not synchronized. If you need to share and mutate across threads, you must design proper coordination or choose an implementation that satisfies the desired concurrency contract, while also checking that implementation's `null` and iterator semantics.

## 16. Views Seeing Updates Does Not Mean an Old Iterator Can Continue

These two points are different:

- A view shares data, so a new read sees valid changes made to the source.
- An already-created iterator has its own traversal state and rules regarding mutations during traversal.

If you are using an iterator on `base` and call `descending.pollFirst()`, you are still removing from the same backing data outside that iterator. Switching direction or variable name does not create an exception to the rule against mutating during iteration.

`TreeSet`'s iterator uses a fail-fast mechanism when it detects structural modifications outside its own `remove` operation. `ConcurrentModificationException` is a best-effort bug-detection aid, not a synchronization mechanism or a correctness condition for your program. Not seeing an exception in a single test run does not prove the mutation pattern is valid. [Java 17: TreeSet iterator policy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html).

Choose a single update path for each pass:

- If only reading, use an iterator and do not mutate the backing data during that pass.
- If filtering while iterating over a `TreeSet`, use the iterator's own `remove` according to its state rules.
- If polling all elements to process them, loop with `pollFirst` or `pollLast` without keeping an active old iterator.
- If you need to plan changes and then apply them, finish the traversal before mutating, or use an independent copy as needed.

These choices clarify the relationship between traversal and member mutation, rather than relying on whether code happens to run to completion by chance.

## 17. Choosing the Right API for the Job

| Task | Suitable approach within this lesson |
| --- | --- |
| Inspect first/last element while keeping it | `first` / `last`, with empty-set handling |
| Retrieve and remove first/last element | `pollFirst` / `pollLast` |
| Read-only traversal in reverse order | `descendingIterator` or a loop over `descendingSet` |
| Need multiple set operations in reverse order | Keep a view variable from `descendingSet` |
| Conditional filtering during a reverse pass | `descendingIterator` and `iterator.remove` |
| Drain from the back end of the source | Use `pollLast` on the source or `pollFirst` on the reversed view |
| Mutate independently of the source's members | Create a true copy, specifying the ordering rule clearly |
| Process only a subrange | Create a range view, then choose direction; mutations still propagate to the source |

Do not choose `poll` just because its name looks more convenient than `first` if the requirement is only to read. Likewise, do not create a copy just to reverse order if a view or iterator already satisfies the data-sharing contract you need.

In terms of cost, `descendingSet` does not allocate an independent store of all members. A true copy must maintain its own member structure. Iterating over all elements or building a list of all results must visit the corresponding elements.

`TreeSet` documents `O(log n)` cost for the basic operations `add`, `remove`, and `contains`. Do not infer from polling either end or having a view that every `NavigableSet` implementation has the same cost, iterator policy, or thread-sharing capabilities.

Remember this is still a set: additions considered equal by the comparator do not create multiple members to be polled individually later. If you need to store every task sharing the same priority level, your uniqueness key or storage structure must reflect that requirement.

## 18. Practice Exercises with Solutions

### Exercise 1: Reading and Polling

An initial natural-order set is `[3, 6, 9]`. Call `first()` then `pollLast()`. What are the two returned values and the final set?

**Solution:** `first` returns 3 without removing it. `pollLast` returns 9 and removes it. The final set is `[3, 6]`.

### Exercise 2: Both Ends of a Reversed View

The original natural-order set is `[2, 4, 8]`. Create `reverse = base.descendingSet()`, then call `reverse.pollFirst()` and `reverse.pollLast()`.

**Solution:** The initial view is `[8, 4, 2]`. The first call returns 8 and removes the last element of the source. The second call returns 2 and removes the first element of the source. Both the original set and the view are left with the single member 4.

### Exercise 3: Does an Iterator Auto-Remove?

You traverse the entire `descendingIterator` of `[1, 2, 3]` using `next` without calling `remove`. What remains in the set?

**Solution:** `[1, 2, 3]` remains. The read pass visits `3, 2, 1` without removing anything. An exhausted iterator must be recreated if you want to read again.

### Exercise 4: Wrong Update Path During Iteration

Inside a loop using an iterator, you call `base.pollFirst()` and then continue using the old iterator. Can this be considered safe because `poll` does not take an element as an argument?

**Solution:** No. `poll` still mutates the membership of the same backing data outside the iterator. Use the appropriate update path: `iterator.remove` for filtering during traversal, or a separate polling loop without keeping an old iterator.

### Exercise 5: Source Set Already Has a Reversed Comparator

A source set uses `Comparator.reverseOrder()` and contains 1, 5, 9. Which number does `source.pollFirst()` remove? Which number does `source.descendingSet().pollFirst()` remove from the initial state?

**Solution:** The source traverses `[9, 5, 1]`, so `source.pollFirst` removes 9. The reversed view traverses `[1, 5, 9]`, so calling `pollFirst` on the view removes 1. Both answers are evaluated independently from the same initial state.

### Exercise 6: null Does Not Mean Empty

A set allowing `null` has order `[null, a, b]`. Will a loop that stops when `pollFirst() == null` process everything?

**Solution:** No. The first call removes the `null` member and the condition stops the loop, leaving `a` and `b` behind. In a single-threaded example, you can check `isEmpty` as the stopping condition like `drainFirst`.

### Exercise 7: Range Scope

The larger set is `[1, 2, 3, 4, 5]`. A range includes from 2 inclusive to 5 exclusive. If you reverse the range and call `pollFirst`, does it remove 5?

**Solution:** No. The range only contains `[2, 3, 4]`, so the reversed view removes 4. The number 5 is outside the range and remains in the larger set.

### Exercise 8: Copy or View?

You need to receive data in reverse order and remove elements freely without removing members from the source. Is calling `descendingSet` alone enough?

**Solution:** No. That is a view sharing the underlying data. You need a true copy with the appropriate ordering; also keep in mind the distinction between set-structure independence and deep copying of element objects.

### Exercise 9: remove State

After creating `descendingIterator`, you call `remove` immediately before calling `next`. Or you call `next` once and then call `remove` twice in a row. What is wrong?

**Solution:** In the first case, no element has been returned by the iterator to remove yet. In the second case, you are removing twice for a single `next` call. The `TreeSet` iterator in this lesson throws `IllegalStateException` for these state errors.

### Exercise 10: Verifying Double Reversal

You want to confirm that `s.descendingSet().descendingSet()` has the same traversal order as `s`. Is comparing with `Set.equals` enough?

**Solution:** Not for proving traversal order, because set equality ignores order. The program converts both sides to lists and compares their sequences. Nor do you need to require both variables to point to the same object with `==`.

## 19. Self-Check Before Applying

Before each piece of code, identify three things: which members the target object sees, which direction it uses, and whether the operation removes members.

Next, check the empty case and the `null` policy. If an iterator is active, identify the allowed update path instead of mutating through another reference and continuing to use it.

For the same store of members, `descendingSet` only changes the viewing angle; `descendingIterator` only chooses the direction of a single pass. Only mutating operations like `poll` or `iterator.remove` actually remove members in these examples.
