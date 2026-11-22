# Allowed Changes via set and Rejected Operations

## 1. Starting Point: Same List Interface, Different Mutation Rights

In this lesson, the subject under consideration is a list created from `Arrays.asList` in the **arrays and conversion** topic group. An array already has a fixed number of slots. Passing it through `Arrays.asList` lets you use the `List` interface to read, search, or replace the contents of those slots; this conversion does not by itself grant the ability to add or remove slots.

Imagine a registration form with exactly three name boxes. You can edit the name in the second box, swap two names, or capitalize all three names. Those operations still use the same three boxes. If you want to write in a fourth person or remove a box altogether, you need a structure that allows changing the number of boxes.

The `Arrays.asList` documentation specifies that the returned list has a fixed size and is backed by the underlying array; updates made through one side are visible on the other. Operations that change the size are not supported. [Java SE 17 — Arrays.asList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)).

Three questions must be kept separate when reading a piece of code:

1. Can an element at an existing index be replaced?
2. Can the number of elements in the list be changed?
3. Does the operation affect another array or object that is being shared?

For `Arrays.asList(array)`, the usual answers are: replacing at an index is allowed, changing the size is not allowed, and replacing at an index affects the backing array. Being able to call a method through a variable of type `List` only proves that the method signature exists; it does not prove that the actual object supports that operation.

After this lesson, you should be able to predict what a `set` call changes, explain why `sort` can run while `add` is rejected, recognize errors caused by indices or array types, and choose the right way to copy when you need a list that supports adding and removing elements.

## 2. set Replaces an Existing Position

Consider the following illustrative snippet inside a method; `java.util.Arrays` and `java.util.List` must be imported:

~~~java
String[] names = {"Lan", "Mai", "An"};
List<String> view = Arrays.asList(names);

String old = view.set(1, "Vy");
~~~

After the last statement:

| Component | Value |
| --- | --- |
| `old` | `"Mai"` |
| `view` | `[Lan, Vy, An]` |
| `names[1]` | `"Vy"` |
| `view.size()` | `3` |
| `names.length` | `3` |

Indices start at `0`, so `1` is the second position. `set` returns the previous element at that position; it does not return the list, nor does it return a boolean indicating success. The contract of `List.set` describes the replacement operation and the condition `0 <= index < size()`. [Java SE 17 — List.set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#set(int,E)).

The key point is that **the position must already exist before the call**. For a three-element list, the valid indices for `set` are `0`, `1`, and `2`. `set(3, value)` is not a way to append a fourth element. Index `3` is outside the replaceable range, even though `3` happens to equal the current size.

`add(index, value)` is a different request. It inserts a new position and shifts subsequent elements; `size` increases. Therefore, `add(1, "Vy")` cannot be used as a substitute for `set(1, "Vy")` on a fixed-size list. Two statements can look similar in the arguments they take while having different structural meanings.

Nor is there an "unused" region in the following list:

~~~java
String[] slots = new String[3];
List<String> fixed = Arrays.asList(slots);
~~~

`fixed.size()` is already `3` from the start. All three positions hold `null`. To populate the first position, use `fixed.set(0, "Lan")`. Calling `fixed.add("Lan")` is still a request to create a fourth position and is rejected. Having `null` at a position does not mean that position is excluded from the size.

This is also why you should not confuse **current size** with the **initial capacity** of an `ArrayList`. `new ArrayList<String>(3)` creates a list of size `0`; the `3` is only the initial capacity. By contrast, `Arrays.asList(new String[3])` already has three elements. If an algorithm is going to call `set(0, ...)`, these two structures have different starting conditions.

## 3. Scope of set's Effect on the Source Array

`Arrays.asList(array)` shares the positions of the source array. Continuing with `names` and `view` from above:

~~~java
names[0] = "Ha";
view.set(2, null);
~~~

Both the array and the list now read `[Ha, Vy, null]`. A method that accepts a `List` can unintentionally modify the caller's array through `set`; conversely, whoever holds the array can change the data that the method is reading. Therefore, document it clearly when a method mutates its input.

Reassigning the `names` variable to another array does not move the view to the new array: the view continues to reference the old array. The bidirectional reference relationship and how to detach a copy are explained in full in the preceding lesson on `Arrays.asList`; here, the point to keep in mind is that **`set` modifies an existing position, even when the array is not accessed directly**.

## 4. Allowed Mutations When the Number of Positions Stays Constant

`set` is the most direct case. Several algorithms that update multiple positions while keeping the size unchanged can also be applied to a list from `Arrays.asList`.

| Operation | Type of change | What to keep in mind |
| --- | --- | --- |
| `view.set(i, x)` | Replaces one position | The index must exist; the value must match the array type |
| `ListIterator.set(x)` | Replaces the element just traversed | Must satisfy the iterator's state |
| `view.replaceAll(op)` | Recomputes each element | The transformation function may throw an exception |
| `view.sort(comparator)` | Reorders elements | Elements must be comparable according to the chosen rule |
| `Collections.reverse(view)` | Reverses the order | The backing array's order also changes |
| `Collections.swap(view, i, j)` | Swaps two positions | Both indices must be valid |
| `Collections.fill(view, x)` | Writes the same value into all positions | Does not create additional elements |
| `Collections.copy(view, source)` | Overwrites a leading segment | The destination must already have sufficient size before copying |

List-manipulation algorithms in `Collections` document their own requirements regarding element replacement. You cannot assume that every object of type `List` works with them. [Java SE 17 — Collections](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html).

The illustrative example below requires importing `Arrays`, `Collections`, `List`, and `Locale` from `java.util`:

~~~java
String[] words = {"c", "a", "b"};
List<String> view = Arrays.asList(words);

view.sort(null);
Collections.reverse(view);
view.replaceAll(s -> s.toUpperCase(Locale.ROOT));
Collections.copy(view, List.of("X", "Y"));
~~~

Progression of the backing array:

~~~text
initial      [c, a, b]
sort         [a, b, c]
reverse      [c, b, a]
replaceAll   [C, B, A]
copy         [X, Y, A]
~~~

`sort(null)` uses the natural ordering of strings. `reverse` reverses the values in the existing positions. `replaceAll` uppercases each string using `Locale.ROOT` to avoid depending on the default locale setting. Finally, `copy` overwrites the first two elements and leaves the third element untouched.

None of the operations in this chain creates a new position. However, all four mutate the data. When you want to preserve the original array for display or further computation, "just sorting" can still break the caller's assumptions.

`Collections.copy` does not automatically grow the destination either. If the destination has only one element while the source has two, copying does not have enough positions to write into. A list created with a large reserved capacity but `size() == 0` still does not satisfy this requirement.

`sort` can fail because of the data or the comparator, even when the list allows replacing positions. For example, `String`'s natural ordering does not handle `null` as a regular string; if `null` is present and sorting is genuinely needed, choose an explicit rule such as a null-handling comparator. List mutability and data comparability are two separate requirements.

## 5. Size-Changing Operations That Are Rejected

For a non-empty fixed-size list, a request that actually adds or removes an element results in `UnsupportedOperationException`. This exception indicates that the object does not support the requested operation.

| Typical call | Why it cannot be performed |
| --- | --- |
| `view.add(x)` | Needs to append a position at the end |
| `view.add(i, x)` | Needs to insert a position |
| `view.addAll(nonEmptySource)` | Needs to add positions for a non-empty source |
| `view.remove(i)` with a valid index | Needs to remove a position |
| `view.remove(existingValue)` | Needs to remove the position holding the found value |
| `view.clear()` when elements are present | Needs to delete existing positions |
| `view.removeIf(predicate)` when an element matches | Needs to delete positions satisfying the predicate |
| `view.removeAll(values)` when elements are removed | Needs to reduce the number of positions |
| `view.retainAll(values)` when elements are removed | Needs to reduce the number of positions |
| `iterator.remove()` after advancing over an element | Needs to delete the element just traversed |
| `listIterator.add(x)` | Needs to insert a position through the iterator |

The examples in the table assume normal valid arguments and an operation that actually has an add/remove effect. Do not use the table to guess the order of error checks when both an index is invalid and the operation is unsupported.

A common mistake is using `remove` to drop `null` slots:

~~~java
List<String> fixed = Arrays.asList("A", null, "B");
fixed.removeIf(value -> value == null);
~~~

This is an illustrative snippet that causes an error, not a valid way to filter this list. `null` is an element occupying a position; removing it would shrink the list from three elements to two. If the goal is to keep three boxes and mark the second box as empty, `set(1, null)` expresses that. If the goal is to produce a list with only two elements, filter into a different structure that supports resizing.

Similarly, replacing an element with the empty string `""` does not delete the position. `set(i, "")` and `remove(i)` differ in both size and data semantics. Choosing a sentinel value is only appropriate when the domain model defines that value.

Pay special attention to lists of integers:

~~~java
List<Integer> values = Arrays.asList(10, 20, 30);
values.remove(1);
~~~

The argument `1` has type `int`, so it selects removal by index—that is, a request to remove the element `20`. Using `values.remove(Integer.valueOf(20))` selects removal by value. On this fixed-size list, neither can succeed when there is an element to remove. Using the right type selects the intended overload of `remove`; it does not grant removal capability to the object.

## 6. Why a remove or addAll Call Sometimes Does Not Throw

Never use a call that performs no actual change to conclude that a list supports adding or removing elements.

Typical cases are `remove("absent")`, `addAll` with an empty source, `removeIf` when every predicate check returns `false`, or `clear` on an already-empty list. An implementation may return without needing to perform any structural modification step.

The `Collection` contract allows an unsupported optional operation to return normally if the call has no effect; it also allows throwing `UnsupportedOperationException` in that situation. Therefore, you should not write code that relies on "adding zero elements will definitely not throw". [Java SE 17 — Collection, optional operations](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html).

Reasoning example:

~~~text
remove("Z") on [A, B]
    Z is not found
    may finish without requesting removal of a position

remove("A") on [A, B]
    A is found
    completing requires removing a position
    the fixed-size list does not support that step
~~~

The difference lies in the execution path and the data conditions, not in the list suddenly changing its type after the first call.

A filtering method like the following will have an input-dependent bug:

~~~java
// Illustrative snippet inside a method; items is passed in from the caller.
items.removeIf(item -> item == null);
~~~

If `items` is a fixed-size list and today there are no `null` values, the method may not expose the bug yet. Tomorrow, when the data contains a `null`, the very same statement reaches the unsupported removal step. Testing only with data that requires no removals easily misses this design flaw.

`Collection.removeIf` also specifies that the default implementation iterates and uses `Iterator.remove` for elements matching the predicate. This explains why evaluating the filter predicate and performing the removal are two separate phases; you should not let the predicate perform side effects and rely on an exception to "roll them back".

The robust solution is to know the algorithm's requirements and the input's mutation rights up front. Do not probe capability by attempting a no-op operation, and do not catch every `UnsupportedOperationException` and ignore it as if the request succeeded.

## 7. Replacing via ListIterator and via subList

### 7.1. ListIterator.set Does Not Add Elements

A plain `Iterator` does not have a `set` method. A `ListIterator` can replace the element last returned by `next` or `previous` if the list supports replacement. It does not treat the cursor position itself as a selected element.

Illustrative snippet:

~~~java
List<String> fixed = Arrays.asList("A", "B");
ListIterator<String> editing = fixed.listIterator();

editing.next();
editing.set("X");
~~~

The result is `[X, B]`. `next` returned `A`, so `set` replaces `A`'s position. If `set` is called immediately after creating the iterator without calling `next` or `previous`, the state condition is not met. The `ListIterator.set` contract specifies the valid states and `IllegalStateException`. [Java SE 17 — ListIterator.set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ListIterator.html#set(E)).

Two conditions must hold at the same time:

- The iterator currently has a most-recently-returned element to replace.
- The backing list allows replacing that element.

On `Arrays.asList`, satisfying the state condition allows `set` to work. With that same iterator, `add` requires inserting a position and is rejected. `remove` requires removing a position and does not become valid just because `next` was called.

Do not "fix" a removal loop by switching from `list.remove` to `iterator.remove` and assuming the problem is solved. An iterator can address certain traversal-and-mutation constraints, but it does not change the add/remove contract of the underlying structure.

### 7.2. subList Continues to Share Data

With a four-element array:

~~~java
String[] days = {"Mon", "Tue", "Wed", "Thu"};
List<String> week = Arrays.asList(days);
List<String> middle = week.subList(1, 3);
middle.set(0, "TUE");
~~~

`middle` holds the positions corresponding to indices `1` and `2` of `week`. Index `0` in the sublist maps to index `1` in the original list. After the `set` call, the array becomes `[Mon, TUE, Wed, Thu]`.

`subList` is a view backed by the underlying list, not an independent copied list. Its contract describes how non-structural changes are reflected between both sides and how optional operations are inherited from the backing list. [Java SE 17 — List.subList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#subList(int,int)).

Because the backing list has a fixed size, `middle.clear()` when elements are present still cannot delete them. Taking a slice does not turn that slice into a resizable structure. To obtain an independent sublist that supports adding and removing elements, you can create `new ArrayList<>(week.subList(1, 3))`.

## 8. set Is Supported Yet Can Still Fail

`UnsupportedOperationException` is only one category of failure. Do not lump every exception from `set` into the conclusion "the list cannot be modified".

### 8.1. Invalid Index

With three elements, `set(-1, x)` and `set(3, x)` are both out of bounds. Catch or check against `IndexOutOfBoundsException` when you genuinely need to handle index errors; an implementation may throw a subclass such as `ArrayIndexOutOfBoundsException`.

Do not use exceptions to control normal loops. The condition `i < list.size()` expresses the boundary more clearly. If data needs to be appended at position `size()`, choose a structure that supports `add` rather than trying to adjust the index for `set`.

### 8.2. Runtime Array Type Is Narrower Than the Variable's Static Type

The following snippet compiles:

~~~java
Number[] narrow = new Integer[] {1, 2};
List<Number> numbers = Arrays.asList(narrow);
numbers.set(0, 1.5);
~~~

`1.5` is boxed into a `Double`, which is a `Number`. However, the actual array object is an `Integer[]`. Storing a `Double` into it violates the array's component type and throws `ArrayStoreException`.

This is a consequence of runtime array store checks. A wider reference type does not change the actual runtime type of the array object. [Java Language Specification 17 — Array Store Exception](https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html#jls-10.5).

Compare two ways of preparing the data:

~~~java
// The actual array is Number[]: it can hold Integer or Double.
Number[] broad = new Number[] {1, 2};
List<Number> broadView = Arrays.asList(broad);
broadView.set(0, 1.5);

// A copy with its own structure: does not write into the original Integer[].
Number[] narrow = new Integer[] {1, 2};
List<Number> detached = new ArrayList<>(Arrays.asList(narrow));
detached.set(0, 1.5);
~~~

This is an illustrative snippet and requires importing `Arrays`, `ArrayList`, and `List`. The first approach chooses the right array type from the start; the second stops writing replacements back into the original narrower array. Choose based on your data-sharing requirements, not just to make the exception disappear.

### 8.3. null Is Not a Removal

A reference array `String[]` can hold `null`; setting a position to `null` through its view keeps the number of positions unchanged. However, subsequent statements must be able to handle `null`. For instance, `value.toUpperCase(...)` cannot be called on a `null` reference.

Distinguish between a `null` value stored inside an array and passing a `null` array reference itself to `Arrays.asList`. The second case fails to provide a valid backing array and causes a `NullPointerException` when creating the list. Do not test whether `null` elements are accepted by passing a `null` array reference.

## 9. Replacing Multiple Positions Is Not an Atomic Transaction

An operation that is valid with respect to size can still fail partway through execution. `replaceAll` should not be understood as "either replace everything or automatically roll everything back".

Consider this illustrative snippet:

~~~java
Integer[] amounts = {1, 2, 3};
List<Integer> view = Arrays.asList(amounts);

view.replaceAll(n -> {
    if (n == 2) {
        throw new IllegalStateException("stop at 2");
    }
    return n * 10;
});
~~~

In the implementation tested by the demonstration program below, element `1` had already been changed to `10` before the function encountered `2` and threw the exception. At that point, the array was `[10, 2, 3]`. Catching the exception does not restore the value `1`.

The OpenJDK 17 source code for the internal list class in `Arrays` shows `replaceAll` writing results sequentially into the array. This serves as the basis for explaining the partially updated state, not as a promise of atomicity or non-atomicity for every `List` implementation. [OpenJDK 17 — Arrays.java](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/Arrays.java).

If the business requirement is not to touch the original data until the entire computation succeeds, you can compute on a copy first. The illustrative snippet requires standard imports:

~~~java
List<Integer> working = new ArrayList<>(view);
working.replaceAll(n -> transform(n));
~~~

`transform` here is an application-defined method, so this snippet is not a standalone program. During computation, replacing elements in `working` does not replace elements in `view`. Only after validation succeeds does the application decide which results to publish.

If you then copy elements one by one from `working` back into a shared array, that copy phase itself does not automatically become an atomic transaction across multiple threads. Furthermore, copying references into a new list does not prevent a transformation function from directly mutating the state of shared element objects. Stronger consistency requirements must be designed explicitly, rather than inferred from the name `replaceAll` or from the fact that the size does not change.

## 10. Choosing a Structure Based on Required Mutation Rights

Three options are very easy to mix up:

| Creation method | Can replace elements with set? | Can add/remove? | Relationship to source array |
| --- | --- | --- | --- |
| `Arrays.asList(array)` | Yes, within valid index and type | Cannot change size | Shares the positions |
| `new ArrayList<>(Arrays.asList(array))` | Yes | Yes | Has its own structure; initially copies element references |
| `Collections.unmodifiableList(Arrays.asList(array))` | No, through the read-only view | No, through the read-only view | Still sees changes in the source array |
| `List.copyOf(Arrays.asList(array))` | No | No | Does not reflect replacements in the source array; rejects null elements |

For a standard `ArrayList`, having its own structure allows both adding/removing and replacing positions; the constructor taking a `Collection` is the clear choice when a working list is needed. [Java SE 17 — ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html).

For `Collections.unmodifiableList`, the restriction applies to accesses through the view. If the backing array is still held by another party, it can still change. Do not treat this wrapper as an independent snapshot. [Java SE 17 — Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)).

`List.of` and `List.copyOf` create lists that disallow element replacement and reject `null`. This is a different contract from the fixed-size list returned by `Arrays.asList`. [Java SE 17 — Unmodifiable Lists](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#unmodifiable).

A structural copy is not yet a deep copy either. Consider:

~~~java
StringBuilder item = new StringBuilder("seed");
List<StringBuilder> view = Arrays.asList(item);
List<StringBuilder> copy = new ArrayList<>(view);

copy.get(0).append("!");
~~~

The two lists have separate positions, yet position `0` in both still references the same `StringBuilder`. Reading `view.get(0)` will show `seed!`. Conversely, `copy.set(0, new StringBuilder("other"))` only replaces the position in `copy`.

When you need to eliminate all effects from element-object mutations, you must decide how to copy each object or use an appropriate immutable element type. No general array-to-list conversion knows the deep-copy rules for every domain type.

### An Array Obtained from toArray Is a Different Case

`Arrays.asList(array)` uses the passed-in array as its backing store; that does not mean every conversion between arrays and lists shares the same positions.

With `String[] snapshot = view.toArray(String[]::new)`, the resulting new array has its own positions. Changing `snapshot[0]` does not write into `view`. However, if the elements are mutable objects, the references inside can still point to the same objects.

The `Collection.toArray` contract is the basis for choosing the right conversion for the desired target array and component type. [Java SE 17 — Collection.toArray](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#toArray(java.util.function.IntFunction)).

## 11. set with a List Containing a Primitive Array

```java
int[] raw = {1, 2};
List<int[]> groups = Arrays.asList(raw);
groups.set(0, new int[] {8, 9});
```

This is an illustrative snippet inside a method with `Arrays` and `List` imported. `groups` has only **one element of type `int[]`**, so `set(0, ...)` replaces the array reference at that position without modifying or reassigning `raw`. The size of `groups` remains `1`. How to convert each `int` into an `Integer`, including empty and `null` sources, is covered separately in the next lesson.

## 12. Complete Demonstration Program

Save all of the following code as **ArrayListChangesDemo.java**. The program uses Java 17-compatible APIs and requires no external libraries. The class name here is an example name; the fixed-size list from `Arrays.asList` is not a resizable `java.util.ArrayList` object.

The `rejects` method checks whether the thrown exception is an instance of the expected type. It prints the **expected type** name, so the `IndexOutOfBoundsException` line remains accurate even when the concrete exception is a subclass. If the operation does not fail or fails with a different exception type, the program stops with an error rather than silently treating it as a valid result.

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;
import java.util.ListIterator;
import java.util.Locale;

public class ArrayListChangesDemo {
    private static void rejects(
            String label,
            Class<? extends RuntimeException> expected,
            Runnable action) {
        try {
            action.run();
            throw new AssertionError(label + " did not fail");
        } catch (RuntimeException ex) {
            if (!expected.isInstance(ex)) {
                throw ex;
            }
            System.out.println(label + " -> " + expected.getSimpleName());
        }
    }

    public static void main(String[] args) {
        String[] names = {"Lan", "Mai", "An"};
        List<String> view = Arrays.asList(names);
        System.out.println("old=" + view.set(1, "Vy"));
        names[0] = "Ha";
        System.out.println("shared=" + view + " / " + Arrays.toString(names));
        System.out.println("size=" + view.size());
        view.set(2, null);
        System.out.println("null=" + Arrays.toString(names));

        String[] words = {"c", "a", "b"};
        List<String> changes = Arrays.asList(words);
        changes.sort(null);
        System.out.println("sort=" + Arrays.toString(words));
        Collections.reverse(changes);
        System.out.println("reverse=" + Arrays.toString(words));
        changes.replaceAll(s -> s.toUpperCase(Locale.ROOT));
        System.out.println("replaceAll=" + Arrays.toString(words));
        Collections.copy(changes, List.of("X", "Y"));
        System.out.println("copy=" + Arrays.toString(words));

        List<String> blocked = Arrays.asList("A", "B");
        rejects("add", UnsupportedOperationException.class, () -> blocked.add("C"));
        rejects("remove-index", UnsupportedOperationException.class, () -> blocked.remove(0));
        rejects("remove-value", UnsupportedOperationException.class, () -> blocked.remove("A"));
        rejects("clear", UnsupportedOperationException.class, blocked::clear);
        rejects("removeIf", UnsupportedOperationException.class,
                () -> blocked.removeIf(s -> s.equals("A")));
        Iterator<String> iterator = blocked.iterator();
        iterator.next();
        rejects("iterator-remove", UnsupportedOperationException.class, iterator::remove);
        System.out.println("after-rejection=" + blocked);

        ListIterator<String> editing = blocked.listIterator();
        editing.next();
        editing.set("X");
        System.out.println("iterator-set=" + blocked);
        rejects("iterator-add", UnsupportedOperationException.class, () -> editing.add("Y"));

        String[] days = {"Mon", "Tue", "Wed", "Thu"};
        List<String> week = Arrays.asList(days);
        List<String> middle = week.subList(1, 3);
        middle.set(0, "TUE");
        System.out.println("subList=" + Arrays.toString(days));
        rejects("subList-clear", UnsupportedOperationException.class, middle::clear);

        rejects("set-at-size", IndexOutOfBoundsException.class,
                () -> view.set(view.size(), "Out"));
        Number[] narrow = new Integer[] {1, 2};
        List<Number> numbers = Arrays.asList(narrow);
        rejects("runtime-array-type", ArrayStoreException.class, () -> numbers.set(0, 1.5));
        System.out.println("narrow=" + Arrays.toString(narrow));

        Integer[] amounts = {1, 2, 3};
        List<Integer> amountView = Arrays.asList(amounts);
        rejects("operator-failure", IllegalStateException.class,
                () -> amountView.replaceAll(n -> {
                    if (n == 2) {
                        throw new IllegalStateException("stop at 2");
                    }
                    return n * 10;
                }));
        System.out.println("partial=" + Arrays.toString(amounts));

        String[] source = {"A", "B"};
        List<String> fixed = Arrays.asList(source);
        List<String> editable = new ArrayList<>(fixed);
        editable.set(0, "C");
        editable.add("D");
        System.out.println("editable=" + editable + " / source=" + Arrays.toString(source));
        String[] snapshot = fixed.toArray(String[]::new);
        snapshot[0] = "Z";
        System.out.println("snapshot=" + Arrays.toString(snapshot) + " / fixed=" + fixed);
        List<String> readOnly = Collections.unmodifiableList(fixed);
        rejects("readOnly-set", UnsupportedOperationException.class, () -> readOnly.set(0, "X"));
        source[0] = "Q";
        System.out.println("readOnly-shared=" + readOnly);
        rejects("List.of-set", UnsupportedOperationException.class,
                () -> List.of("A", "B").set(0, "X"));

        StringBuilder item = new StringBuilder("seed");
        List<StringBuilder> itemView = Arrays.asList(item);
        List<StringBuilder> itemCopy = new ArrayList<>(itemView);
        itemCopy.get(0).append("!");
        System.out.println("shared-object=" + itemView.get(0));

        int[] raw = {1, 2};
        List<int[]> groups = Arrays.asList(raw);
        groups.get(0)[0] = 7;
        System.out.println("primitive-size=" + groups.size() + " / raw=" + Arrays.toString(raw));
        groups.set(0, new int[] {8, 9});
        System.out.println("primitive-set=" + Arrays.toString(groups.get(0))
                + " / raw=" + Arrays.toString(raw));
    }
}
~~~

Compile and run in the directory containing the file:

~~~shell
javac --release 17 -encoding UTF-8 ArrayListChangesDemo.java
java ArrayListChangesDemo
~~~

Exact stdout:

~~~text
old=Mai
shared=[Ha, Vy, An] / [Ha, Vy, An]
size=3
null=[Ha, Vy, null]
sort=[a, b, c]
reverse=[c, b, a]
replaceAll=[C, B, A]
copy=[X, Y, A]
add -> UnsupportedOperationException
remove-index -> UnsupportedOperationException
remove-value -> UnsupportedOperationException
clear -> UnsupportedOperationException
removeIf -> UnsupportedOperationException
iterator-remove -> UnsupportedOperationException
after-rejection=[A, B]
iterator-set=[X, B]
iterator-add -> UnsupportedOperationException
subList=[Mon, TUE, Wed, Thu]
subList-clear -> UnsupportedOperationException
set-at-size -> IndexOutOfBoundsException
runtime-array-type -> ArrayStoreException
narrow=[1, 2]
operator-failure -> IllegalStateException
partial=[10, 2, 3]
editable=[C, B, D] / source=[A, B]
snapshot=[Z, B] / fixed=[A, B]
readOnly-set -> UnsupportedOperationException
readOnly-shared=[Q, B]
List.of-set -> UnsupportedOperationException
shared-object=seed!
primitive-size=1 / raw=[7, 2]
primitive-set=[8, 9] / raw=[7, 2]
~~~

The code was compiled with `--release 17` and verified on JDK 24.0.2. The compiler flag checks the Java 17 language and API level; it does not mean the program was executed on a Java 17 JVM. The `partial` line is an observation of the implementation that was run, not a guarantee that an algorithm must leave that exact state on every `List` implementation.

Reading the output by group:

- `old`, `shared`, `size`, and `null` demonstrate position replacement, the return value, and array sharing.
- `sort`, `reverse`, `replaceAll`, and `copy` show that replacing multiple positions still does not require changing size.
- The `UnsupportedOperationException` lines prove that add/remove requests were tested with data that genuinely requires structural changes.
- `iterator-set` and `subList` show that other access paths can still modify positions in the same backing data.
- `set-at-size` and `runtime-array-type` separate index errors from array component-type errors.
- `partial` illustrates the limitation when a transformation fails midway.
- `editable`, `snapshot`, and `readOnly-shared` distinguish a structural copy, a separate result array, and a read-only view that still shares data.
- `shared-object` and the two `primitive` lines help identify which level of element object is being modified.

The program runs sequentially. The results above do not demonstrate thread safety when multiple threads concurrently access and modify the data.

## 13. Applying This in Method Design

Suppose a method is responsible for normalizing each name while keeping the number of columns in a record unchanged. Accepting a fixed-size list and using `set` or `replaceAll` can be appropriate if the method's contract clearly states that it mutates the input and allows valid values.

If the method must drop empty names, merge duplicates, or append a summary label, the number of elements changes. Creating an `ArrayList` copy before processing makes structural mutation rights explicit:

~~~java
// Illustrative snippet inside a method.
// incoming is a List<String> provided by the caller.
List<String> result = new ArrayList<>(incoming);
result.removeIf(name -> name == null || name.isBlank());
result.add("TOTAL");
~~~

This snippet does not modify the positions of `incoming`. It builds a separate result for an algorithm that needs to filter and append. Deciding whether the `"TOTAL"` label belongs to the same data model is an application-design question; the example simply illustrates the difference in mutation rights.

When writing a general-purpose method that accepts `List<T>`, establish one of the following contracts:

| Method purpose | How to document/assign responsibility |
| --- | --- |
| Read-only | Do not call mutating operations and do not assume the input is immutable |
| Mutate values in place | Clearly state that the input must support replacement and that shared data may change |
| Add/remove in place | Clearly state that the input must support size changes |
| Return a new result | Create an appropriate result structure; clarify the level of element copying |

There is no need to cast to `ArrayList` to try to gain mutation rights. Another implementation may also support the required operations. Conversely, the object returned by `Arrays.asList` is not a regular `java.util.ArrayList`; such a cast does not convert the structure and can cause a `ClassCastException`.

Nor should you rely on internal class names printed during debugging. Names such as the nested class inside `Arrays` are implementation details. Supported operations should be determined from how the list was created and the API contracts the code uses.

## 14. Practice with Answers

### Exercise 1 — Filling Existing Slots

A method receives `Arrays.asList(new String[2])` and needs to write `"A"` and `"B"` into the two slots. Should it use `add` or `set`? What is the final size?

**Answer:** Use `set(0, "A")` then `set(1, "B")`. The list already has two positions holding `null`, so the size remains `2`. `add` requests creating a new position and does not satisfy this list's contract.

### Exercise 2 — Does Sorting Modify the Array?

Given `String[] data = {"b", "a"}` and `List<String> view = Arrays.asList(data)`. After `view.sort(null)`, what is `data[0]`? If the original array must remain unchanged, how should data preparation be changed?

**Answer:** `data[0]` is `"a"`. To avoid changing the order of positions in the source array, sort on a separate structure, such as `new ArrayList<>(view)`. Switching the algorithm from `sort` to `Collections.sort` does not by itself solve the shared-data issue.

### Exercise 3 — Does No Error Prove Removal Works?

A call `fixed.remove("Z")` returns `false` for the data `[A, B]`. Can you conclude that `fixed.remove("A")` will also work?

**Answer:** No. The first call had no element to remove, so it may not have reached a structural modification step. On a fixed-size list, the second call needs to remove a position and is rejected. The optional-operation contract also does not guarantee that every list returns `false` for that no-op call.

### Exercise 4 — Fixing a set Error at the End

With `List<String> fixed = Arrays.asList("A", "B")`, `fixed.set(fixed.size(), "C")` fails. Is changing the index to `fixed.size() - 1` a way to append `"C"`?

**Answer:** No. The new index turns the call into replacing `"B"` with `"C"`, leaving two elements. If you need to keep both `A` and `B` and append `C`, create a list that supports growing in size and use `add`.

### Exercise 5 — Why Does a Valid Number Still Fail?

`Number[] data = new Integer[] {4, 5}` is wrapped as `List<Number>`. Why is `set(0, 2.5)` invalid at runtime?

**Answer:** `Double` conforms to `Number`, but it cannot be stored in an array object whose actual runtime type is `Integer[]`. The error is `ArrayStoreException`. Create an actual `Number[]` array or a list copy with its own structure depending on your needs; do not explain this error as `set` being universally forbidden.

### Exercise 6 — Has the Copy Isolated All Changes?

`copy = new ArrayList<>(Arrays.asList(builder))` with a `StringBuilder`. After `copy.get(0).append("!")`, does the outer `builder` object change? What if `copy.set(0, new StringBuilder("X"))` is used instead?

**Answer:** `append` mutates the shared object itself, so `builder` changes. `set` replaces the position in `copy` with a different reference without reassigning `builder` or the source list's position. Distinguish between mutating an element object and replacing the reference held at a position.

### Exercise 7 — Is a Read-Only View a Snapshot?

You create `readOnly = Collections.unmodifiableList(Arrays.asList(array))`, and then the array holder executes `array[0] = "Q"`. Does `readOnly.get(0)` see `"Q"`? Is `readOnly.set(0, "X")` valid?

**Answer:** Yes, it sees `"Q"` because the underlying data is still shared. However, modifying through `readOnly.set` is rejected. If you need a snapshot of positions that does not reflect source changes, choose a copying approach; if you also require preventing modifications to the result, apply an appropriate read-only contract on top.

### Exercise 8 — The Element Type Determines What set Means

Given `int[] raw = {1, 2}` and `List<int[]> groups = Arrays.asList(raw)`, what is `groups.size()`? After `groups.set(0, new int[] {3, 4})`, does the variable `raw` point to the new array?

**Answer:** The size is `1` because the single element is a reference to an `int[]`. `set` replaces that reference inside the list; the variable `raw` is not reassigned. To obtain a list of individual integers, you must convert each number to an `Integer` element using an appropriate list-creation approach.

## 15. Key Points to Keep Straight When Using Arrays.asList

Before performing a mutating operation, determine which element is being targeted, whether that position already exists, whether the actual array type can hold the new value, and whether the algorithm needs to increase or decrease the number of positions. Then consider any other places sharing the array or element objects.

The core mental model of this lesson is: **`set` replaces the contents of an existing position; adding/removing changes the number of positions; `Arrays.asList` provides only the first set of permissions over the backing array.** From this model, you can explain the examples involving sorting, iterators, sublists, type errors, and copying strategies without having to memorize each exception in isolation.
