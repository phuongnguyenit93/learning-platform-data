# Nested Wildcards and the Limits of Capture in Java Generics

When encountering types such as `List<List<?>>`, `List<? extends List<?>>`, or `List<? extends List<? extends Number>>`, even a single `?` requires attention to read/write direction; **multiple `?` symbols at different levels never mean they share the same type**. Java checks constraints at each generic level and provides *wildcard capture* to temporarily name a single hidden type. Yet capture has limits: it does not turn independent wildcards into one shared type, does not permit arbitrary value writes, and does not alter generic invariance.

This lesson clarifies three questions:

1. **Which level holds the wildcard?** The outer list level and the inner list level determine which assignments and updates are permitted.
2. **What can capture solve?** A generic method can capture one hidden type to read and write back **a value of the same type belonging to that exact collection**.
3. **What can capture not solve?** It does not prove two independent wildcards are the same type, does not coerce a list of a subtype into a list of a supertype, and does not bypass the modification limits of the underlying object.

Runnable examples use Java 17 or newer. Intentionally ill-typed snippets are annotated and explained separately, not as standalone runnable programs.

## 1. From One Wildcard to Multiple Generic Levels

`List<?>` has an unknown element type: it reads safely as `Object`, yet you cannot arbitrarily call `add("text")`. It is **not** equivalent to `List<Object>`. Java can capture `?` into a temporary type internally named `CAP#1`; a generic helper `<E>` preserves the same element type when reading and writing back to **that same list**.

When dealing with a **list of lists**, the issue is no longer a single `?`: a wildcard at the **outer level** differs from a wildcard inside the **inner level's element type**. Two different rows can hold different kinds of data, even though both are viewed as `List<?>`.

Illustrative example (place inside a method importing `java.util.List`):

~~~java
List<List<?>> rows = List.of(List.of("A"), List.of(1));
Object first = rows.get(0).get(0); // "A"
Object next  = rows.get(1).get(0); // 1
~~~

Read-only code needs no capture helper. If you need to modify a specific row, you must determine **which level the capture belongs to and whether the actual list is mutable**. The following sections distinguish `List<List<?>>`, `List<? extends List<?>>`, and how to place a helper at the right level; do not deduce from the shared `?` symbol that two rows share a common element type.

## 2. Distinguishing Type Levels: Three Similar-Looking Declarations That Differ Greatly

Consider three types:

~~~java
List<?> a;
List<List<?>> b;
List<? extends List<?>> c;
~~~

They differ in **wildcard placement**:

| Type | Where is the wildcard? | Reading from the outer list | Adding a new row to the outer list |
| --- | --- | --- | --- |
| `List<?>` | Directly on the outer list's element | `Object` | Cannot add a non-`null` row |
| `List<List<?>>` | Inside the element type; the outer level has exact type argument `List<?>` | `List<?>` | Can add any `List<X>` because it can be used as `List<?>` |
| `List<? extends List<?>>` | Outer level has a wildcard with upper bound `List<?>` | `List<?>` | Cannot add a non-`null` row because the outer level's real element type is unknown |

### 2.1. `List<List<?>>`: The Outer List Knows Its Elements Are `List<?>`

~~~java
List<List<?>> rows = new ArrayList<>();
rows.add(new ArrayList<String>(List.of("A", "B")));
rows.add(new ArrayList<Integer>(List.of(1, 2)));

List<?> firstRow = rows.get(0); // Valid.
// firstRow.add("C");           // ERROR: the type of this row is unknown.
rows.add(List.of(true, false)); // Valid: adds a Boolean row.
~~~

This is an illustrative snippet requiring `import java.util.*` inside a class. `rows.add(...)` compiles because **the outer list's element type is exact `List<?>`**, and `List<String>`, `List<Integer>`, `List<Boolean>` all convert to the `List<?>` view.

However, once you retrieve a row, the `List<?>` variable does not know **the element type inside that row**. Having an outer list capable of holding multiple kinds of rows does not permit mixing element types within one specific row.

### 2.2. `List<? extends List<?>>`: The Outer Level Also Has a Hidden Type

~~~java
List<List<Integer>> integerRows = new ArrayList<>();
integerRows.add(new ArrayList<>(List.of(1, 2)));

List<? extends List<?>> rows = integerRows;
List<?> firstRow = rows.get(0); // Valid.

// rows.add(List.of("X")); // ERROR: outer level has a wildcard.
// rows.add(List.of(3));   // ALSO AN ERROR.
~~~

This is an illustrative snippet requiring `import java.util.*` inside a class. `integerRows` has type argument `List<Integer>`; that argument matches upper bound `List<?>`, so it can be assigned to `List<? extends List<?>>`.

However, the compiler **does not know the exact row type accepted by the outer list**, only that it is some subtype of `List<?>`. The real target accepts `List<Integer>` rows; allowing a `List<String>` to be added would be dangerous. Hence even a new `List<Integer>` cannot be added via the `rows` reference, because the static type does not retain the fact that the actual type argument is specifically `List<Integer>`.

### 2.3. The Difference Observed Through a Single Assignment

~~~java
List<List<Integer>> integerRows = new ArrayList<>();

List<? extends List<?>> accepted = integerRows; // Valid.
// List<List<?>> rejected = integerRows;         // COMPILE ERROR.
~~~

**Why is the second line wrong?** Java generics are invariant in the outer level's type argument. If converting `List<List<Integer>>` to `List<List<?>>` were allowed, you could call `rejected.add(List.of("text"))`, causing a list declared to hold `List<Integer>` rows to suddenly contain a `List<String>` row.

**Why is the first line right?** `? extends List<?>` preserves the constraint that the real row type can be any specific subtype of `List<?>`; by disallowing arbitrary row insertions, the assignment remains safe.

This is the most important rule of nested wildcards: **where `?` is placed matters just as much as the upper bound following it**.

## 3. Two Wildcard Levels Can Appear Together

Now consider:

~~~java
List<? extends List<? extends Number>> groups;
~~~

Read it **from the inside out**:

1. `List<? extends Number>` is a list whose retrieved elements can be used as `Number`. It could actually be `List<Integer>`, `List<Double>`, or `List<Number>`.
2. `List<? extends List<? extends Number>>` is an outer list whose real row type is some concrete subtype of `List<? extends Number>`. Reading a row yields something usable as `List<? extends Number>`.
3. Through this reference, you cannot arbitrarily add a new row to the outer list, nor arbitrarily add a new `Number` to a retrieved row. Yet you can **read every numeric element as `Number`**.

Example:

~~~java
List<List<Integer>> integerGroups =
        List.of(List.of(1, 2), List.of(3));

List<? extends List<? extends Number>> groups = integerGroups;

List<? extends Number> firstGroup = groups.get(0);
Number firstNumber = firstGroup.get(0); // Valid.

// groups.add(List.of(4, 5));  // ERROR at outer level.
// firstGroup.add(3.14);       // ERROR at inner level.
~~~

This is an illustrative snippet requiring `import java.util.List` inside a class. Likewise, `List<List<Double>>` can be assigned to `groups`.

Observe carefully that **each wildcard level carries a separate constraint**. The outer level governs the row type; the inner level governs a row's element type. A capture at the inner level **does not automatically unlock** permission to add rows to the outer level.

## 4. Java 17+ Program: Observing Levels and Safe Operations

Create **`NestedWildcardViewsDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class NestedWildcardViewsDemo {
    private static void showRows(List<? extends List<?>> rows) {
        for (List<?> row : rows) {
            System.out.println("row = " + row);
            for (Object item : row) {
                System.out.println("  item = " + item);
            }
        }
    }

    public static void main(String[] args) {
        List<List<Integer>> integerRows = new ArrayList<>();
        integerRows.add(new ArrayList<>(List.of(1, 2)));
        integerRows.add(new ArrayList<>(List.of(3)));

        List<List<?>> mixedRows = new ArrayList<>();
        mixedRows.add(new ArrayList<>(List.of("A", "B")));
        mixedRows.add(new ArrayList<>(List.of(true, false)));

        showRows(integerRows);
        showRows(mixedRows);
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac NestedWildcardViewsDemo.java
java NestedWildcardViewsDemo
~~~

Exact stdout:

~~~text
row = [1, 2]
  item = 1
  item = 2
row = [3]
  item = 3
row = [A, B]
  item = A
  item = B
row = [true, false]
  item = true
  item = false
~~~

`showRows` accepts both source types because `List<List<Integer>>` and `List<List<?>>` both match `List<? extends List<?>>`. In each iteration, a row is read as `List<?>` and each element as `Object`. There are no unchecked casts or unsafe assignments.

Do not infer from `mixedRows` holding multiple kinds of rows that **every row accepts every kind of element**. The first row is truly an `ArrayList<String>` and still keeps its own element contract.

## 5. Capturing a Row Inside a Nested List

If you need to rearrange elements *within a single row*, you can use a generic helper to capture that row's type.

Create **`NestedCaptureDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class NestedCaptureDemo {
    public static void swapEndsInEveryRow(List<? extends List<?>> rows) {
        for (List<?> row : rows) {
            swapCaptured(row);
        }
    }

    private static <E> void swapCaptured(List<E> row) {
        int last = row.size() - 1;
        if (last > 0) {
            E first = row.get(0);
            row.set(0, row.get(last));
            row.set(last, first);
        }
    }

    public static void main(String[] args) {
        List<List<?>> mixed = new ArrayList<>();
        mixed.add(new ArrayList<>(List.of("A", "B", "C")));
        mixed.add(new ArrayList<>(List.of(1, 2)));
        mixed.add(new ArrayList<>(List.of(true)));

        swapEndsInEveryRow(mixed);
        System.out.println(mixed);
    }
}
~~~

Compile/run:

~~~bash
javac NestedCaptureDemo.java
java NestedCaptureDemo
~~~

Stdout:

~~~text
[[C, B, A], [2, 1], [true]]
~~~

Exact walkthrough:

1. `swapEndsInEveryRow` receives a list of rows whose actual types are unknown, yet each row can be used as `List<?>`.
2. Each iteration binds a reference `row: List<?>` to **one specific row**.
3. The call `swapCaptured(row)` lets the compiler capture the hidden type argument of **the current row** as `E`.
4. Inside `swapCaptured`, `get` and `set` both use `E`, so swapping elements **of that exact row** is type-safe.
5. When the loop moves to another row, a separate capture can represent a completely different element type. The helper does not force all rows to share the same `E`.

The method needs no `@SuppressWarnings("unchecked")` and uses no raw types. Having `mixed` be an `ArrayList` of `ArrayList` rows enables `set` to work at runtime; if a row were created by `List.of(...)`, `set` would throw `UnsupportedOperationException` even though capture succeeds.

### Why Is This Not a Way to “Put Any Object Into a Row”?

Suppose a helper:

~~~java
private static <E> void addCaptured(List<E> row, E value) {
    row.add(value);
}
~~~

This is an **illustrative method to place inside a class with `import java.util.List;`**. Having a type parameter `E` does not fabricate a new value of `E`. If the caller only has `List<?>` and an arbitrary `Object`, it still cannot prove `Object` matches the hidden `E`:

~~~java
static void addUnknown(List<?> row, Object value) {
    // addCaptured(row, value); // ERROR: cannot guarantee value has the hidden type E.
}
~~~

Thus, **a generic helper only expresses type relationships that are genuinely guaranteed**, such as a value retrieved from `List<E>` itself. It is not a tool to bypass type checking.

## 6. Outer-Level Capture Differs from Inner-Level Capture

There are two completely distinct tasks:

- **Swapping two existing rows inside the same outer list:** requires preserving the outer level's hidden row type.
- **Swapping two existing elements inside the same row:** requires preserving the inner level's hidden element type.

Whichever level is obscured by a wildcard may need its own capture. The following program illustrates **outer-level capture** by swapping two `List<Integer>` rows inside a `List<List<Integer>>` received through a broader view.

Create **`OuterCaptureDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class OuterCaptureDemo {
    static void swapOuterRows(List<? extends List<?>> rows) {
        if (rows.size() >= 2) {
            swapCaptured(rows, 0, 1);
        }
    }

    private static <E> void swapCaptured(List<E> list, int i, int j) {
        E first = list.get(i);
        list.set(i, list.get(j));
        list.set(j, first);
    }

    public static void main(String[] args) {
        List<List<Integer>> rows = new ArrayList<>();
        rows.add(new ArrayList<>(List.of(1, 2)));
        rows.add(new ArrayList<>(List.of(3, 4)));

        swapOuterRows(rows);

        System.out.println(rows);
    }
}
~~~

~~~bash
javac OuterCaptureDemo.java
java OuterCaptureDemo
~~~

Exact stdout:

~~~text
[[3, 4], [1, 2]]
~~~

In the helper, `E` is the actual row type of the **outer list** (in the example, `List<Integer>`), not the `Integer` element type inside each row. Swapping two rows belonging to the same list is safe because both share the outer collection's element type.

Do not read this program as “wildcard capture lets you add a new `List<String>` row.” Capture only preserves the type `E` of **existing** rows; it does not allow fabricating an arbitrary value of a `List<?>` subtype and inserting it.

## 7. Important Limit: Two Independent Wildcards Are Not Equal

A common misconception is that if two parameters both write `List<?>`, they are “the same wildcard.” In reality, each wildcard position only denotes an unknown type; **no condition states that the two hidden types are equal**.

~~~java
List<?> first = new ArrayList<String>(List.of("A"));
List<?> second = new ArrayList<Integer>(List.of(1));

// first.set(0, second.get(0)); // COMPILE ERROR.
~~~

This is an illustrative snippet requiring `import java.util.*` inside a class. If the assignment were accepted, an `Integer` would be written into a list holding `String`s. Both variables writing `List<?>` is nowhere near enough to guarantee safety.

Similarly inside a nested list:

~~~java
List<List<?>> rows = new ArrayList<>();
rows.add(new ArrayList<String>(List.of("A")));
rows.add(new ArrayList<Integer>(List.of(1)));

List<?> row0 = rows.get(0);
List<?> row1 = rows.get(1);

// row0.set(0, row1.get(0)); // COMPILE ERROR.
~~~

Even a generic helper capturing `row0` cannot prove that an element from `row1` has the same type. Two rows belonging to the same `List<List<?>>` only guarantees **each row is a `List<?>`**, not that **the rows have the same type argument**.

### Solution When a Type Link Between Source and Destination Is Truly Needed

If the problem requires transferring an element from a source list to a destination list capable of accepting that type, **express the relationship explicitly using a type parameter and bounds**:

~~~java
static <T> void appendFirst(
        List<? extends T> source,
        List<? super T> destination) {
    if (!source.isEmpty()) {
        destination.add(source.get(0));
    }
}
~~~

This is an **illustrative method requiring `import java.util.List` inside a class**.

With a `List<Integer>` source and a `List<Number>` destination, the compiler verifies the constraint via PECS and the call is valid. With a `List<?>` source and a `List<?>` destination lacking any declared relationship, the compiler must not assume they share the same type. **If type information has been erased from the API at both ends**, you may need to redesign the API or preserve the generic type parameter end-to-end instead of looking for a “stronger capture.”

## 8. Limits of Nested Wildcards When Passing Second-Level Collections

Look at the types:

~~~java
List<List<Integer>> integerGroups = new ArrayList<>();
List<List<? extends Number>> groupSlots = new ArrayList<>();

// groupSlots = integerGroups; // COMPILE ERROR.
groupSlots.add(new ArrayList<Integer>()); // Valid.
~~~

Illustrative snippet requiring `import java.util.*` inside a class. Easy point of confusion: `List<Integer>` is **compatible** with `List<? extends Number>`, yet that does not make `List<List<Integer>>` a subtype of `List<List<? extends Number>>`. The outer level remains **invariant** in its type argument.

If assigning to `groupSlots` were permitted, subsequent code could add a `List<Double>` to a list originally holding only `List<Integer>` instances. The compiler therefore rejects it.

The way to **accept** a list of `Number`-subtype groups is:

~~~java
List<List<Integer>> integerGroups =
        List.of(List.of(1, 2), List.of(3));

List<? extends List<? extends Number>> readOnlyView = integerGroups;
~~~

“readOnlyView” is an illustrative variable name; it does not guarantee the runtime collection is immutable. It is a **view restricted from adding rows/elements**. The two `? extends` wildcards allow reading numbers safely across both levels without opening up ill-typed writes.

### A Comparison Table

| Parameter type | Accepts `List<List<Integer>>`? | Can add a `List<Double>` row through the parameter? | Can read numbers as `Number`? |
| --- | --- | --- | --- |
| `List<List<Number>>` | No | No; can only add a row of type `List<Number>` | Yes |
| `List<List<? extends Number>>` | No | Yes, because `List<Double>` matches `List<? extends Number>` | Yes |
| `List<? extends List<? extends Number>>` | Yes | Cannot add a non-`null` new row | Yes |
| `List<? extends List<?>>` | Yes | Cannot add a non-`null` new row | Only reads elements as `Object` |

In the first row, even though a `List<Number>` can contain `Double` values, `List<Double>` itself is **not** a `List<Number>`. Hence an entire `List<Double>` row cannot be added to `List<List<Number>>`. Keep *a row's type argument* and *element values inside a row* separate.

## 9. Practical Example: Flattening Numeric Groups with a Nested Producer

A method that only **reads** numeric groups should accept the outer list with two producer wildcard levels:

~~~java
static List<Number> flatten(
        List<? extends List<? extends Number>> groups) {
    List<Number> result = new ArrayList<>();
    for (List<? extends Number> group : groups) {
        for (Number number : group) {
            result.add(number);
        }
    }
    return result;
}
~~~

This is an **illustrative method requiring `import java.util.*` inside a class**. It accepts lists composed of `Integer` or `Double` rows; every retrieved element is a `Number`. The result list is **a new `ArrayList<Number>`**, so adding `Number` to the result does not violate any write restriction on the wildcard source.

Create **`NestedFlattenDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class NestedFlattenDemo {
    static List<Number> flatten(
            List<? extends List<? extends Number>> groups) {
        List<Number> result = new ArrayList<>();
        for (List<? extends Number> group : groups) {
            for (Number value : group) {
                result.add(value);
            }
        }
        return result;
    }

    public static void main(String[] args) {
        List<List<Integer>> integerGroups =
                List.of(List.of(1, 2), List.of(3));
        List<List<Double>> doubleGroups =
                List.of(List.of(1.5, 2.5));

        System.out.println("integer groups = " + flatten(integerGroups));
        System.out.println("double groups = " + flatten(doubleGroups));
    }
}
~~~

Compile and run:

~~~bash
javac NestedFlattenDemo.java
java NestedFlattenDemo
~~~

Exact stdout:

~~~text
integer groups = [1, 2, 3]
double groups = [1.5, 2.5]
~~~

In this example we **do not need a wildcard capture helper** because we only read from the source and append to a `result` list with concrete element type `Number`. Do not reach for capture merely because you see multiple `?` symbols; use it when you genuinely need to link read and written values of the same hidden type.

If the input must contain **multiple kinds of rows within one outer list**, you can create `List<List<? extends Number>>`, add `List<Integer>` and `List<Double>` rows, and then call `flatten`. This is allowed because each row matches `List<? extends Number>`; the outer list then declares the exact element type `List<? extends Number>`.

## 10. When Both a Nested Source and an Element-Accepting Destination Are Needed

Combine PECS with nested wildcards:

~~~java
static <T> void appendFlattened(
        List<? extends List<? extends T>> groups,
        List<? super T> destination) {
    for (List<? extends T> group : groups) {
        for (T value : group) {
            destination.add(value);
        }
    }
}
~~~

This is an **illustrative method**, requiring `import java.util.List` inside a class.

- `groups`: outer level reads out groups; inner level reads out `T` or subtypes of `T`.
- `destination`: accepts values of `T` or subtypes of `T`.
- `T` connects **the read direction from the groups** with **the write direction into the destination**, without requiring every group to hold the exact same subtype.
- The method does not insert new elements into the source groups, so it needs no separate capture of each group's type.

Example:

~~~java
List<List<Integer>> groups = List.of(List.of(1, 2), List.of(3));
List<Number> destination = new ArrayList<>();

appendFlattened(groups, destination);
System.out.println(destination); // [1, 2, 3]
~~~

This is an illustrative call snippet requiring `import java.util.*` inside a class alongside `appendFlattened`. The compiler can infer a suitable `T` from both source and destination, or you can call `ClassName.<Number>appendFlattened(groups, destination)` to specify `T = Number` explicitly.

Conversely, if you wanted to write arbitrary `Number` elements into `List<Integer>` rows, that write would be unsafe: a `Double` could end up in an `Integer` row. No placement of a capture helper can make that broken contract valid.

## 11. Capture Is Neither a Runtime Transformation Nor a Technique to “Erase” Bounds

### 11.1. Capture Creates No New Object and Checks No Actual Subtype

When calling `helper(List<E>)` with a `List<?>` argument, the compiler introduces a temporary `E` to type-check the expression. This is a **compile-time mechanism**, not a call creating a special class at runtime. Java generics use **type erasure**, so the program lacks full information about the generic type arguments of each `List` at runtime.

You cannot perform this check:

~~~java
Object value = List.of(1, 2);

// if (value instanceof List<String>) { ... } // COMPILE ERROR.
if (value instanceof List<?> list) {
    System.out.println(list.size());
}
~~~

This is an illustrative snippet requiring `import java.util.List` inside a class. `instanceof List<?>` works because it only checks that the object is a `List`, without verifying its element subtype.

### 11.2. Capture Does Not Prove Two Hidden Types Are Equal

Two `List<?>` variables holding two lists that both happen to contain `String`s still **do not form a shared generic contract** merely because their current data looks the same. The compiler checks **signatures and type constraints**, not by inferring a new generic equality from inspecting runtime contents.

If you need an API using two lists sharing type `E`, preserve the signature `<E> ... (List<E> a, List<E> b)` while the data is still typed, or provide safe value-transfer constraints such as `List<? extends E>` and `List<? super E>`.

### 11.3. Capture Does Not Guarantee Collection Mutability

~~~java
List<?> immutable = List.of("A", "B");
swapCaptured(immutable); // Compiles, yet set throws UnsupportedOperationException.
~~~

This snippet is an illustration inside a class defining `swapCaptured(List<E>)` as above. When the helper calls `set`, the underlying list still retains the right to reject modifications. The same applies to both outer and inner levels of a nested list: each level may be backed by a collection that permits or forbids modification.

### 11.4. Capture Does Not Legalize Unchecked Casts

~~~java
List<Integer> integers = new ArrayList<>();
@SuppressWarnings("unchecked")
List<String> forged = (List<String>) (List<?>) integers;
forged.add("wrong"); // Risk of heap pollution.
~~~

This is **code illustrating a hazard**, not a solution. An unchecked cast can trick the static type system and corrupt the `List<Integer>` contract. A proper capture helper **requires no unchecked cast**.

## 12. Common Mistakes When Reading Nested Wildcards

**Mistake 1 — Ignoring which level has the wildcard.** `List<List<?>>` and `List<? extends List<?>>` do not have the same write permission on the outer list. One permits adding a matching `List<X>`; the other does not.

**Mistake 2 — Deducing a subtype relationship across two invariant generic levels.** From `List<Integer> <: List<? extends Number>` you cannot deduce `List<List<Integer>> <: List<List<? extends Number>>`. To widen input at the outer level, you need a wildcard at that exact level.

**Mistake 3 — Seeing two `?` symbols and assuming they share the same type.** `List<List<?>>` can contain one `List<String>` row and one `List<Integer>` row. The type arguments of two rows can be completely different.

**Mistake 4 — Thinking a capture helper can accept any arbitrary `Object` for addition.** A `<E>` helper can only operate on values already proven to be `E`; it cannot turn a random `Object` into `E` through inference.

**Mistake 5 — Thinking capturing the first row automatically unlocks writing to the outer list.** The outer level and inner level can have different hidden types; capture must attach to the exact collection where the read/write happens.

**Mistake 6 — Confusing wildcards with runtime immutability.** `List<?>` or `List<? extends Number>` does not mean immutable. `remove` or `clear` can be type-valid; `set` through a helper can be type-valid; runtime behavior still depends on whether the collection allows modification.

**Mistake 7 — Using `List<Object>` instead of `List<?>`.** `List<Object>` only accepts the exact type argument `Object`. It is not a “writable version of every list”; trying to coerce `List<String>` into `List<Object>` is usually a sign of flawed design.

**Mistake 8 — Forgetting size and mutability conditions.** An element-swapping helper should check for at least two elements before reading/writing; `List.of(...)` still throws an exception if `set` is attempted. The compiler only checks types, not runtime logic.

## 13. Knowledge-Check Exercises

Suppose you have these variables inside a Java method with `import java.util.*;`:

~~~java
List<List<Integer>> integers = new ArrayList<>();
integers.add(new ArrayList<>(List.of(1, 2)));

List<List<?>> mixed = new ArrayList<>();
List<? extends List<?>> upperOuter = integers;
List<? extends List<? extends Number>> upperBoth = integers;
~~~

Determine whether each of the following expressions **compiles or not**, evaluated independently per line:

| Expression | Compiles? | Explanation |
| --- | --- | --- |
| `mixed.add(List.of("A"));` | Yes | Outer-level element has type `List<?>` |
| `mixed.add(List.of(1, 2));` | Yes | `List<Integer>` matches `List<?>` |
| `mixed = integers;` | No | Outer level is invariant; `List<List<Integer>>` is not `List<List<?>>` |
| `upperOuter = integers;` | Yes | Row type `List<Integer>` matches upper bound `List<?>` |
| `upperOuter.add(List.of(3));` | No | Outer level has a hidden element type |
| `List<?> row = upperOuter.get(0);` | Yes | Retrieved row can be used as `List<?>` |
| `Object x = upperOuter.get(0).get(0);` | Yes | Inner-level element can be used as `Object` |
| `upperBoth = integers;` | Yes | Both upper-bound levels match |
| `Number n = upperBoth.get(0).get(0);` | Yes | Guaranteed readable as `Number` |
| `upperBoth.get(0).add(10);` | No | Row's element type is unknown |
| `upperBoth.add(List.of(10));` | No | Outer level's actual row type is unknown |
| `mixed.get(0).add("X");` | No | Inner level is `List<?>` |
| `mixed.get(0).clear();` | Yes | Clearing requires supplying no value of the hidden type; runtime depends on collection |

In the exercise, `mixed.get(0)` would throw `IndexOutOfBoundsException` at runtime because `mixed` starts empty; the table only asks about **compilability**. In the assignment `mixed = integers`, the compiler blocks it even if the current rows happen to be empty or share a type.

### Applied Questions

1. Why is using `List<? extends List<?>>` safe for reading multiple kinds of rows, while adding a `List<String>` to it is blocked?
2. Can a `<E> void swap(List<E> row)` helper swap elements inside a `List<?>` row? **Yes**, because reading and writing use the same captured `E`.
3. Can you take elements from two different `List<?>` rows and cross-swap them without a shared constraint? **Not guaranteed**, because the two hidden types may differ.
4. If you only want to sum `Number` values from `List<List<Integer>>`, should you use a capture helper or nested `extends`? **Nested `extends` suffices**, because only reading values is needed.
5. Why does `List<List<? extends Number>>` not directly accept `List<List<Integer>>`? **Because generics at the outer level are invariant**, even though the row type matches the wildcard.

## 14. Conclusion and Design Rules

To use nested wildcards safely, **read the type from the outer level to the inner level**, then identify which level the operation targets:

- `List<List<?>>`: outer list has exact element type `List<?>`; matching `List<X>` rows can be added to the outside, yet each retrieved row still has a hidden type argument.
- `List<? extends List<?>>`: accepts outer lists whose row type is a subtype of `List<?>` (such as `List<List<Integer>>`), yet no non-`null` row can be added through the wildcard view.
- `List<? extends List<? extends Number>>`: accepts lists of numeric subtype groups at both levels and reads elements as `Number`; you cannot arbitrarily write new elements or rows through that view.
- **A `<E>` capture helper** is useful when operating on values **of the same hidden type from a single collection**. If multiple independent collections are involved, an explicit declared type relationship is required; capture does not invent that relationship.

Core limit: **one wildcard is one specific but unknown type; two wildcards are two unknowns that can differ; each wildcard level enforces its own constraint**. Capture helps the compiler track a consistent hidden type within a small scope; it does not eliminate generic invariance, does not permit writing the wrong subtype, and does not change the mutability of a runtime collection.