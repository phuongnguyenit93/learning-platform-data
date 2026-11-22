# Swapping Elements of `List<?>` Using a Helper Method

## Objectives

A `List<?>` can be a `List<String>`, `List<Integer>`, or a list of any element type that the calling code does not know exactly. You can still **read** elements as `Object`, yet trying to read an element and put it back via `list.set(...)` directly inside a method accepting `List<?>` can be rejected by the compiler. This is a classic **wildcard capture** scenario.

After this lesson, you will be able to:

1. Explain why `List<?>` is not equivalent to `List<Object>` and why direct swapping fails to compile.
2. Write a generic helper method `<T> void swapCaptured(List<T>, int, int)` so the compiler preserves the link between the retrieved element and the written-back element.
3. Use a public `swap(List<?>, int, int)` method without casts or raw types.
4. Know when to use the standard API `Collections.swap(List<?>, int, int)`.
5. Distinguish **compile-time type correctness** from **runtime element replacement support** and handle index and unmodifiable-list cases.

## 1. The Problem: `get` Can Read, but `set` Is Blocked

Look at the following code. This is an **example intentionally containing compile errors**, not a runnable program:

```java
import java.util.List;

class BrokenSwap {
    static void swap(List<?> list, int i, int j) {
        Object saved = list.get(i);
        list.set(i, list.get(j)); // type error
        list.set(j, saved);       // type error
    }
}
```

`list.get(i)` compiles because an element of any reference type can be observed as `Object`. However, `list.set(i, element)` requires an **argument compatible with the list's exact element type `E`**.

`List<?>` means the element type is **an unknown type**, not “freely holds any `Object`.” Suppose the actual list is `List<Integer>`: if the compiler allowed passing any `Object` to `set`, you could replace an integer with a `String` and break the source's type contract.

You might think `list.get(j)` and `list.set(i, ...)` both refer to the same list, so the retrieved element is naturally of the right type. Algorithmically that reasoning is sound; however, at the direct expression level, the compiler does not prove the required type relationship between those wildcard occurrences. `javac` error messages typically look like “`Object cannot be converted to CAP#1`” or mention `capture of ?` types.

Do not fix this problem by declaring `Object saved` and casting, because `Object` discards the information “this value came from the list's exact element type.”

## 2. Wildcard Capture: Naming the Unknown Type as `T`

The solution is to move the read–write operations into a **generic helper method**:

```java
static void swap(List<?> list, int i, int j) {
    swapCaptured(list, i, j);
}

private static <T> void swapCaptured(List<T> list, int i, int j) {
    T saved = list.get(i);
    list.set(i, list.get(j));
    list.set(j, saved);
}
```

This snippet illustrates the signatures and method bodies; the standalone runnable example below adds index validation and `i == j` handling.

The mechanism happens at **compile time**:

1. When calling `swapCaptured(list, i, j)`, the compiler **captures** the `?` of the `List<?>` argument as an internal unknown type, often described as `CAP#1`.
2. The compiler infers `T` for that helper call as that captured type. Therefore, throughout the body of `swapCaptured`, `list` has a consistent type `List<T>`.
3. `list.get(i)` returns `T`, so `T saved = ...` is valid.
4. `list.set(i, list.get(j))` receives a `T` from the **same list**; `list.set(j, saved)` also receives `T`.
5. The caller only sees `List<?>` and can call `swap` with many kinds of lists without knowing what `T` is.

**Note:** the helper **does not discover or inspect the actual element type at runtime**. It lets the compiler prove type consistency at a specific site. Because of generic type erasure, Java also does not generate a separate machine version of the helper for each `T`.

### Diagram of Relationships in a Single Call

```text
Caller:
    List<?> values        -- unknown wildcard --
             |
             | swapCaptured(values, i, j)
             v
Generic helper:
    List<T> list           -- T = capture of ? --
             |
     T first = get(i)      -- read T --
             |
     set(i, get(j))        -- write T into List<T> --
     set(j, first)         -- write T into List<T> --
```

All operations still execute on **the caller's own list object**. There is no copying of the list and no conversion to `List<Object>`.

## 3. Complete Implementation on Java 17+

A practical version should validate the object and indices before touching data, and treat swapping an index with itself as a no-op that needs no element replacement.

Create a file named **`WildcardSwapDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

public class WildcardSwapDemo {
    public static void swap(List<?> values, int i, int j) {
        Objects.requireNonNull(values, "values");
        Objects.checkIndex(i, values.size());
        Objects.checkIndex(j, values.size());
        swapCaptured(values, i, j);
    }

    private static <T> void swapCaptured(List<T> values, int i, int j) {
        if (i == j) {
            return;
        }
        T saved = values.get(i);
        values.set(i, values.get(j));
        values.set(j, saved);
    }

    public static void main(String[] args) {
        List<String> names = new ArrayList<>(List.of("An", "Binh", "Chi"));
        List<?> unknown = names;
        swap(unknown, 0, 2);
        System.out.println("names: " + names);

        List<Integer> numbers = new ArrayList<>(List.of(10, 20, 30));
        swap(numbers, 0, 1);
        System.out.println("numbers: " + numbers);

        Collections.swap(unknown, 0, 1);
        System.out.println("Collections.swap: " + names);

        List<String> fixed = Arrays.asList("red", "blue");
        swap(fixed, 0, 1);
        System.out.println("fixed-size: " + fixed);

        List<String> immutable = List.of("x", "y");
        try {
            swap(immutable, 0, 1);
        } catch (UnsupportedOperationException e) {
            System.out.println("immutable: unsupported");
        }

        List<String> one = new ArrayList<>(List.of("only"));
        swap(one, 0, 0);
        System.out.println("same index: " + one);

        try {
            swap(one, 0, 1);
        } catch (IndexOutOfBoundsException e) {
            System.out.println("invalid index: " + e.getClass().getSimpleName());
        }
    }
}
```

Compile and run in the file's directory with JDK 17 or newer:

```bash
javac WildcardSwapDemo.java
java WildcardSwapDemo
```

**Standard output:**

```text
names: [Chi, Binh, An]
numbers: [20, 10, 30]
Collections.swap: [Binh, Chi, An]
fixed-size: [blue, red]
immutable: unsupported
same index: [only]
invalid index: IndexOutOfBoundsException
```

### Reading the Output Step by Step

- `names` is actually a `List<String>` containing `[An, Binh, Chi]`; the variable `unknown` of type `List<?>` points to the same list. `swap(unknown, 0, 2)` swaps elements at indices `0` and `2`, yielding `[Chi, Binh, An]`.
- `swap(numbers, 0, 1)` applies the exact same method to `List<Integer>` and produces `[20, 10, 30]`; the code does not need to know ahead of time whether `T` is `Integer` or `String`.
- `Collections.swap(unknown, 0, 1)` is the standard JDK API, swapping the first two positions to `[Binh, Chi, An]`.
- `Arrays.asList("red", "blue")` creates a **fixed-size** list that supports `set`, so swapping the two values succeeds.
- `List.of("x", "y")` creates an **unmodifiable** list; calling `set` inside the helper throws `UnsupportedOperationException`, even though the generic signature is completely valid.
- When `i == j`, the helper returns directly after both indices have been verified valid. With `[only]`, the contents remain unchanged.
- `Objects.checkIndex(1, one.size())` throws `IndexOutOfBoundsException` because a single-element list only has valid index `0`.

This complete example uses exact imports from `java.util`. `Objects.checkIndex` was added in Java 9, so it runs on Java 17.

## 4. Why Is a Helper the Type-Safe Solution?

In `swapCaptured`, we declare:

```java
private static <T> void swapCaptured(List<T> values, int i, int j) {
    T saved = values.get(i);
    values.set(i, values.get(j));
    values.set(j, saved);
}
```

Type `T` represents **the same element type for all three operations**. The compiler checks:

| Expression | Type seen by compiler | Meaning |
| --- | --- | --- |
| `values` | `List<T>` | List with element type `T` |
| `values.get(i)` | `T` | Reads the exact list element type |
| `T saved` | `T` | Stores value without losing type info |
| `values.set(i, values.get(j))` | `T` passed to `set(int, T)` | Writes element of the same type |
| `values.set(j, saved)` | `T` passed to `set(int, T)` | Restores old value at the other position |

In contrast to a method accepting only `List<?>`, if you wrote `Object saved = list.get(i)`, the expression `saved` retains only static type `Object`. A `List<Integer>` does not let the compiler treat any `Object` as an `Integer`. Hence **preserving type `T` across the swap** is the key.

No type bound such as `<T extends Number>` is needed because the swap algorithm performs no arithmetic and needs no `Number` properties. It only moves elements between two positions of the same list. This is why an **unbounded** helper works with any concrete data type.

If one day you need type-specific processing, such as calculations on `Number`, add a bound for the **processing requirement**, not because swapping itself requires a bound.

## 5. `Collections.swap`: When Should You Use the Standard API?

The JDK already provides the method:

```java
public static void swap(List<?> list, int i, int j)
```

This is a minimally excerpted **API signature**; the actual method belongs to `java.util.Collections`. You can call it directly:

```java
List<String> words = new ArrayList<>(List.of("left", "right"));
List<?> view = words;
Collections.swap(view, 0, 1);
System.out.println(words); // [right, left]
```

The snippet above illustrates statements inside a method that imports `List`, `ArrayList`, `Collections`.

Notice that the standard API itself publicly accepts `List<?>`. That **does not mean all elements are `Object`**; rather, it expresses that swapping positions **does not depend on the specific element type**. API users benefit from generality without having to write or see the internal wildcard capture mechanism.

**In real applications, if you only need to swap two positions, prefer `Collections.swap`.** Writing your own helper is a way to learn capture and is useful when another custom algorithm needs to link values derived from the same generic type.

`Collections.swap` can throw `IndexOutOfBoundsException` if indices are invalid, and `UnsupportedOperationException` if the list does not support `set`. It does not turn immutable lists into mutable ones.

## 6. Swapping Is Replacing Elements, Not Changing Size

A typical swap keeps the element count constant and only replaces values at two positions. Therefore it requires **`get` and `set`** capabilities rather than `add` or `remove` to change size.

| List kind | Replace via `set` | Swappable with valid indices? | Notes |
| --- | --- | --- | --- |
| `new ArrayList<>(...)` | Yes | Yes | Supports indexed element replacement |
| `new LinkedList<>(...)` | Yes | Yes | Indexed access can be costly |
| `Arrays.asList(...)` | Yes | Yes | Fixed size, yet supports element replacement |
| `List.of(...)` | No | No | Unmodifiable list |
| `List.copyOf(...)` | No | No | Unmodifiable list |
| `Collections.unmodifiableList(...)` | Not via wrapper | Not via wrapper | May reflect source mutations via another alias |

Thus, two concepts must be separated:

- **Type-safety:** the helper guarantees no element of the wrong type is inserted into the list.
- **Mutability:** the implementation decides whether `set` is accepted.

A call like `swap(List.of("a", "b"), 0, 1)` **compiles**; only at runtime does it throw `UnsupportedOperationException`. Meanwhile `swap(Arrays.asList("a", "b"), 0, 1)` succeeds because it does not need to change size.

For `Collections.unmodifiableList(source)`, the `source` alias may still be mutable; the wrapper only blocks mutations through the wrapper itself. Wildcards and unmodifiable wrappers are two separate mechanisms.

## 7. Index Validation and Same-Position Swaps

The sample implementation calls:

```java
Objects.checkIndex(i, values.size());
Objects.checkIndex(j, values.size());
```

These are illustrative statements inside the method. For a list with `size() == n`, valid indices satisfy `0 <= index < n`. Checking both before starting the swap gives a clear error for negative or out-of-bounds indices, and avoids modifying the first position before discovering the second index is invalid.

If `i == j`, both elements are at the same position, so swapping changes nothing. The sample helper **returns early** to avoid unnecessary `get/set` calls, while still validating both indices beforehand. This choice also lets a list that does not support `set` accept the same-index case because no mutation is performed; do not generalize that behavior to every other swap implementation.

If the list is empty, there are no valid indices to swap two elements. Requiring both index parameters to be **non-negative** is also insufficient; they must be less than the current `size()`.

The checks above do not guarantee safety if another thread concurrently modifies the list's structure. Synchronization is required for shared access.

## 8. Do Not Use Raw Types or Casts to Bypass Wildcard Capture

A hasty workaround is casting `List<?>` to `List<Object>`, or using raw `List` to force the `set` call to compile:

```java
// Intentionally UNSAFE example, should not be used:
@SuppressWarnings({"rawtypes", "unchecked"})
static void unsafe(List<?> values, int index) {
    List raw = values;
    raw.set(index, "some text");
}
```

This method illustrates a design flaw. If `values` actually points to a `List<Integer>`, this approach can place a `String` into a list that the rest of the code trusts to hold only `Integer`s. The program can fail with `ClassCastException` when reading later.

The `<T>` helper avoids that problem because:

1. It does not change the list's actual element type.
2. It only writes values read from `List<T>` back into `List<T>`.
3. It requires no `@SuppressWarnings("unchecked")`.
4. The compiler checks every `set` call against a single consistent `T`.

Important point: **not every helper taking `List<T>` is automatically safe**; safety comes from how `T` is used. Passing unrelated values via raw types or unchecked casts can still break type constraints.

## 9. Capture Is for One List; Do Not Merge Two Different Wildcards

Two variables both declared as `List<?>` **do not guarantee they have the same element type**:

```java
List<?> left = List.of("a", "b");
List<?> right = List.of(1, 2);

// Do not assume elements from left can be written to right,
// or vice versa.
```

`left` can hold `String` while `right` holds `Integer`. Therefore, a helper accepting **one** `List<T>` suffices to swap **two positions of that same list**. If you want to exchange elements between two different lists, you must design type constraints for both lists: two independent wildcards do not prove elements of one list are compatible with the other.

An example signature requiring a shared relationship, for illustration only:

```java
static <T> void exchange(List<T> a, int i, List<T> b, int j) {
    T saved = a.get(i);
    a.set(i, b.get(j));
    b.set(j, saved);
}
```

The method above requires **both lists to be accepted under the same `T`** and both to support `set`. It is not a general solution for two independent `List<?>` values; you should not force them into a shared type just to silence compiler errors. When the task is simply swapping within one list, `swap(List<?>)` is simpler and more accurate.

## 10. Complexity and Algorithm Limitations

The helper performs at most two `get` calls and two `set` calls, plus a constant number of checks:

- With `ArrayList`, indexed access is typically O(1), so swapping two indices takes O(1) time.
- With `LinkedList`, indexed access generally traverses nodes, costing up to O(n) for long lists.
- The helper stores only one reference `T saved`, so it uses O(1) auxiliary space.
- Swapping **does not deep-copy** elements; it only swaps the references located at the two positions.

If an implementation allows `set` at the first index but rejects or fails on the subsequent `set`, the method does not promise atomicity or rollback. With normal mutable lists, both `set` calls succeed; however, the helper should not be advertised as an atomic transaction.

When elements themselves are mutable objects, swapping only changes the order of references to those objects; the objects' internal state does not change. If both positions refer to the same object, swapping produces no observable difference.

No generic wildcard automatically provides thread safety. If a list is shared across threads, you must follow the synchronization contract of the collection used.

## 11. Common Misconceptions

**“`List<?>` is always unmodifiable.”** False. Wildcards restrict passing a value of an unknown type into the list via the variable, yet a generic helper can still perform `set` with an element retrieved from the same list, if the implementation supports it.

**“You can change `List<?>` to `List<Object>` for simplicity.”** False. `List<String>` is not a subtype of `List<Object>`. Raw types or unchecked casts can break type safety.

**“`List<?>.get(...)` returns `Object`, so writing that `Object` back must be valid.”** Logically, a value from the same list has the right type; however, an `Object` expression loses that type relationship so the compiler cannot prove it. A generic helper creates a consistent `T` for both the read and the write.

**“A `<T>` helper turns the list into a new `List<T>`.”** False. It creates no list, copies nothing, and changes no runtime type; `T` is a type variable for compile-time checking.

**“`Collections.swap` accepts `List<?>`, so it can swap even `List.of`.”** False. The signature accepts many generic kinds, yet an immutable object still rejects `set`.

**“Fixed-size lists cannot be swapped.”** Not true in all cases. `Arrays.asList` forbids additions/removals that change size, yet still supports replacement via `set`.

**“Swapping two positions across two `List<?>` variables uses the same helper.”** You cannot assume that, because two wildcards can capture two completely different element types.

## 12. Self-Check

**Question 1.** Why can `swap(List<?> list, ...)` be called with both `List<Integer>` and `List<String>`?

Because any `List<T>` can be referenced through `List<?>`. During the helper call, the compiler captures one consistent element type specifically for that list.

**Question 2.** Inside the helper, why is `T saved` better than `Object saved`?

Because `T saved` preserves the exact element type of `List<T>` so it can be passed back to `set(int, T)`. With `Object`, the compiler cannot treat it as `T` in general.

**Question 3.** Given `List<?> view = Arrays.asList("x", "y")`, does `swap(view, 0, 1)` run successfully?

Yes. `Arrays.asList` supports `set` and swapping does not change size, so the result is `[y, x]`.

**Question 4.** What about `List<?> view = List.of("x", "y")`?

It compiles, but at runtime the method attempts `set` and throws `UnsupportedOperationException`.

**Question 5.** Does `Collections.swap` require `List<Object>`?

No. The public signature is `swap(List<?>, int, int)`; it accepts lists of any element type.

**Question 6.** If a list has 3 elements, what does `swap(list, 0, 3)` produce?

`Objects.checkIndex(3, 3)` throws `IndexOutOfBoundsException` before any data is modified, since valid indices are only `0`, `1`, `2`.

**Question 7.** With `swap(list, 1, 1)` where index `1` is valid, does the helper in the main example modify elements?

No. After validating both indices, the helper sees `i == j` and returns without performing `get/set`.

## Takeaways

A `List<?>` holds an **unknown element type**, so you cannot arbitrarily pass an `Object` value through `set`. **Wildcard capture** enables a generic helper `<T>` to keep the same `T` between `get` and `set`, thereby swapping elements of the list itself without raw types or casts. When you only need this functionality in a program, you can use `Collections.swap(List<?>, int, int)` directly. Either way, the actual list must still support element replacement, indices must be valid, and generics do not automatically guarantee atomicity or synchronization.