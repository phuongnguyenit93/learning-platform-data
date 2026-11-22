# The `extends` Wildcard Does Not Make the Source Object Immutable

## Goal

`List<? extends Number>` frequently appears in APIs that **read numeric data**, because it can accept lists of element types such as `Integer`, `Double`, or `Number`. Even though an arbitrary `Number` value cannot be added through that reference, the actual list **can still change**.

After this lesson, you should be able to explain four points:

1. How does `? extends Number` constrain the element type at compile time?
2. Why does modifying a list through a source reference still change the contents viewed via `List<? extends Number>`?
3. Why can `remove` and `clear` be called through the wildcard yet sometimes throw `UnsupportedOperationException`?
4. How do you distinguish a wildcard, an unmodifiable view, and an immutable snapshot when designing APIs?

## 1. The Restriction of `extends` Belongs to the Type System

First, consider this snippet inside a Java method that has imported `java.util.List` and `java.util.ArrayList`:

```java
List<Integer> source = new ArrayList<>(List.of(10, 20));
List<? extends Number> view = source;

Number value = view.get(0); // valid

// view.add(42);             // compile error
// view.add(3.14);           // compile error
// view.set(0, 42);          // compile error
```

Because `Integer` extends `Number`, `List<Integer>` can be **referenced through** `List<? extends Number>`. This does not mean `List<Integer>` is a subtype of `List<Number>`: Java generics are *invariant* with respect to concrete type arguments.

`? extends Number` means the element type is an unknown concrete type and **has an upper bound of `Number`**. The compiler allows reading elements as `Number` because every valid element in the list is a `Number`. However, it cannot permit adding `42` or `3.14`: if the actual list is `List<Double>`, then `42` is not a `Double`; if it is `List<Integer>`, then `3.14` is not an `Integer`.

The error lines are commented out, so the snippet above is illustrative rather than a standalone Java program.

Crucial point: **a wildcard only changes which operations are accepted at compile time on the variable `view`.** It does not alter the implementation, create a copy, freeze the object, or impose any synchronization mechanism.

## 2. The Source and the Wildcard View Can Point to the Same Object

With these two statements:

```java
List<Integer> source = new ArrayList<>(List.of(10, 20));
List<? extends Number> view = source;
```

the reference model is:

```text
source: List<Integer> ------------+
                                  |
                                  v
                         ArrayList<Integer>
                              [10, 20]
                                  ^
                                  |
view: List<? extends Number> -----+
```

The assignment `view = source` **does not copy elements**. It creates another variable pointing to the exact same `ArrayList<Integer>` object held by `source`.

If you modify through `source`:

```java
source.add(30);
source.set(0, 99);
System.out.println(view); // [99, 20, 30]
```

then `view` immediately observes the changes when reading. The compiler allows `source.add(30)` and `source.set(0, 99)` because the source variable has type `List<Integer>` and the new values are `Integer`. Blocking `view.add(30)` does not alter `source`'s permission to modify the list.

Therefore: **not being able to add through one reference does not mean no reference can add**.

An object can also be passed through methods, stored in fields, received by constructors, or shared across multiple components. If other references have write access and the implementation supports modification, the data observed through `List<? extends Number>` will still change.

## 3. Standalone Compiling and Runnable Java 17+ Example

Create a file named **`ExtendsNotImmutableDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ExtendsNotImmutableDemo {
    public static void main(String[] args) {
        List<Integer> source = new ArrayList<>(List.of(10, 20));
        List<? extends Number> view = source;

        System.out.println("Initially: " + view);

        source.add(30);
        source.set(0, 99);
        System.out.println("After source changes: " + view);

        Number first = view.get(0);
        System.out.println("First as Number: " + first);

        boolean removed = view.remove(Integer.valueOf(20));
        System.out.println("Removed through wildcard: " + removed);
        System.out.println("Source after removal: " + source);

        view.clear();
        System.out.println("Source after clear: " + source);

        List<Integer> backing = new ArrayList<>(List.of(1, 2));
        List<? extends Number> unmodifiable =
                Collections.unmodifiableList(backing);

        try {
            unmodifiable.clear();
        } catch (UnsupportedOperationException e) {
            System.out.println("Wrapper rejects clear");
        }

        backing.add(3);
        System.out.println("Wrapper reflects source: " + unmodifiable);

        List<? extends Number> snapshot = List.copyOf(backing);
        backing.add(4);
        System.out.println("Snapshot: " + snapshot);
        System.out.println("Backing: " + backing);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac ExtendsNotImmutableDemo.java
java ExtendsNotImmutableDemo
```

**Stdout:**

```text
Initially: [10, 20]
After source changes: [99, 20, 30]
First as Number: 99
Removed through wildcard: true
Source after removal: [99, 30]
Source after clear: []
Wrapper rejects clear
Wrapper reflects source: [1, 2, 3]
Snapshot: [1, 2, 3]
Backing: [1, 2, 3, 4]
```

**Why does the program produce the output above?**

- `source` and `view` point to the same `ArrayList<Integer>`; therefore `add(30)` and `set(0, 99)` via `source` change the data observed through `view`.
- `view.get(0)` reads an element of type `Number`, so variable `first` receives the value `99`.
- `view.remove(Integer.valueOf(20))` is valid because the `remove(Object)` overload only needs an object to find/remove. `ArrayList` supports removal, so it returns `true`.
- `view.clear()` takes no new element, so it is type-permitted and works on `ArrayList`. Because it is the same object, `source` becomes `[]`.
- `Collections.unmodifiableList(backing)` creates a wrapper that rejects modifications through the wrapper, yet `backing.add(3)` is still allowed; the result seen through the wrapper becomes `[1, 2, 3]`.
- `List.copyOf(backing)` creates a structurally unmodifiable snapshot from the mutable `backing` list. When `4` is added to `backing`, the snapshot still holds `[1, 2, 3]`.

What `view`, `unmodifiable`, and `snapshot` have in common is that **they all have type `List<? extends Number>`**. Yet their behaviors differ completely depending on the underlying object. This is direct proof that a wildcard is **not a tool for guaranteeing immutability**.

## 4. Why Can `remove` or `clear` Still Be Called Through `? extends`?

To understand, examine the relevant abbreviated signatures of `List<E>` and `Collection<E>`. These are **illustrative API shapes**, not the full JDK source code:

```java
E get(int index);
boolean add(E element);
E set(int index, E element);

boolean remove(Object value);
E remove(int index);
void clear();
```

The wildcard in `List<? extends Number>` prevents the compiler from **knowing the exact `E`**. Methods that introduce a new `E` value into the collection are therefore restricted:

- `add(E)` must know that the value to add has the exact type `E`.
- `set(int, E)` must know that the replacement value has the exact type `E`.

Meanwhile, removal methods do not supply a new element value:

- `clear()` takes no parameter of type `E`.
- `remove(Object)` takes `Object` to match against existing elements.
- `remove(int)` takes an integer index and returns an element of type `E`; the returned element can be used as `Number`.

For example, the two methods below compile when placed inside a class that has imported `java.util.List`:

```java
static Number takeFirst(List<? extends Number> numbers) {
    return numbers.remove(0);
}

static void empty(List<? extends Number> numbers) {
    numbers.clear();
}
```

Neither introduces a new `Integer` or `Double`. `takeFirst` requests the element at index `0`; if the list is empty, `remove(0)` throws `IndexOutOfBoundsException`. With an implementation that does not support removal, the operation may throw `UnsupportedOperationException`.

**Do not confuse the two overloads of `remove`:**

```java
List<Integer> source = new ArrayList<>(List.of(10, 20, 30));
List<? extends Number> view = source;

view.remove(1);                    // removes at index 1 (value 20)
view.remove(Integer.valueOf(30));  // removes value 30
System.out.println(source);       // [10]
```

Calling `remove(1)` selects `remove(int)`; calling `remove(Integer.valueOf(30))` selects `remove(Object)`. This is also an illustrative snippet inside a method and requires importing `java.util.List` and `java.util.ArrayList`.

## 5. Some Lists Allow Modification, Some Reject It: You Must Check the Implementation

| Object referenced through `List<? extends Number>` | Calling `add(Number)` via wildcard | Calling `clear()` via wildcard | Actual state |
| --- | --- | --- | --- |
| `new ArrayList<Integer>()` | Blocked by compiler | Compiles and runs | Mutable list; source alias can add/replace/remove |
| `new LinkedList<Double>()` | Blocked by compiler | Compiles and runs | Mutable list; source alias can add/replace/remove |
| `Arrays.asList(1, 2)` | Blocked by compiler | Compiles, but size-changing removal is unsupported | Fixed-size list; `set` works through an appropriately typed reference |
| `List.of(1, 2)` | Blocked by compiler | Compiles, rejected at runtime | Unmodifiable list |
| `Collections.unmodifiableList(source)` | Blocked by compiler | Compiles, rejected at runtime | Wrapper blocks changes through itself; source may still be mutable |
| `List.copyOf(source)` | Blocked by compiler | Compiles, rejected at runtime | Unmodifiable list, isolated from subsequent structural edits to a mutable source |

In the `add(Number)` column, "Blocked by compiler" refers to adding a **non-null expression of type `Number`** through `List<? extends Number>`. The table also does not imply that every `clear()` call on every implementation succeeds: Java Collections have optional mutating operations (*optional operations*), so runtime may throw `UnsupportedOperationException`.

`Arrays.asList` creates a **fixed-size list**, which is not equivalent to being completely immutable. Replacing a value at an existing index with `set` can succeed through a properly typed reference. `List.of`, by contrast, forbids replacing, adding, or removing elements.

With `Collections.unmodifiableList(source)`, the wrapper disallows modification **through itself**, yet the wrapper's contents can still change if another party still holds `source` and modifies the original list. This is an unmodifiable view, distinct from an independent snapshot.

## 6. `List<?>`, `List<? extends Number>`, and `List<Number>` Differ

These reference types differ in **type-level read/write permissions**, without themselves determining mutability:

- `List<?>`: unknown element type, safely read as `Object`.
- `List<? extends Number>`: elements have upper bound `Number`, read as `Number`.
- `List<Number>`: declared element type is exact `Number`; adding `Integer` or `Double` is type-valid if the list supports modification.

```java
List<Integer> original = new ArrayList<>(List.of(1, 2));
List<?> any = original;
List<? extends Number> numbers = original;
Object a = any.get(0);
Number b = numbers.get(0);
// List<Number> invalid = original; // Invariance.
```

Both `any` and `numbers` point to **the same list**. The original alias can still mutate it; wildcards do not create copies or lock objects. Exceptions related to `add(null)` require separating type checking from runtime null policy, as explained in the dedicated lesson.

## 7. Using `? extends` for Its Proper Purpose in APIs

Suppose a method only needs to compute a sum:

```java
static double sum(List<? extends Number> values) {
    double total = 0;
    for (Number n : values) {
        total += n.doubleValue();
    }
    return total;
}
```

This is an illustrative method snippet. This signature accepts `List<Integer>`, `List<Double>`, and lists carrying other subtypes of `Number` without forcing callers to convert everything into `List<Number>`.

**Producer Extends** in the PECS rule means `? extends T` is convenient when an API needs to **accept and read data of type `T`**. This rule does not declare the API read-only in the sense of immutability; removal operations may still be available.

If a method only needs to iterate, using `Iterable<? extends Number>` expresses an even narrower API surface; it does not directly expose `clear()`. However, limiting the methods visible through a reference still does not lock the underlying object. An iterator might even provide an optional `remove()` operation.

If you genuinely need to **add `Integer`**, the type `List<Integer>` or `List<? super Integer>` is usually more appropriate:

```java
static void appendInteger(List<? super Integer> destination) {
    destination.add(42);
}
```

`? super Integer` accepts lists whose element type is `Integer` or a supertype of `Integer` and allows adding `Integer` safely. It does not mean the actual list is guaranteed to support adding (for instance, an unmodifiable list can still reject it at runtime).

## 8. When You Want to Protect Data, Use Data-Protection Mechanisms

### Blocking modification through a return value

```java
static List<? extends Number> exposeView(List<Integer> source) {
    return java.util.Collections.unmodifiableList(source);
}
```

The receiver of the result cannot modify it through the wrapper. Yet anyone holding `source` can still modify it; any changes from the source can appear the next time the receiver reads the wrapper. Thus a wrapper fits a **read-only access-path policy** rather than automatically creating a data snapshot.

### Creating a structural list snapshot

```java
static List<? extends Number> exposeSnapshot(List<Integer> source) {
    return List.copyOf(source);
}
```

When `source` is a mutable list, `List.copyOf(source)` creates an unmodifiable list containing the current elements. Later size changes or element replacements in `source` do not affect the snapshot's structure. `List.copyOf` forbids `null` elements; if the input is already an eligible unmodifiable list, the JDK may reuse the instance.

**Note on shallow copying:** `List.copyOf` does not deep-clone each element. If the list contains mutable objects and an external reference mutates an object's state, that property change can still be observed through the snapshot. For a fully immutable snapshot of the entire object graph, immutable element objects or appropriate state copying must be used.

### Designing data ownership

Sometimes you do not need a wrapper if the API only exposes computed results or an already fixed read structure, but that is a design decision based on **ownership and reference boundaries**. Wildcards themselves do not control aliases or lifetimes.

At the same time, `? extends` adds no thread-safety. If one thread mutates an `ArrayList` while another thread is iterating over it, you must design synchronization yourself or choose an appropriate collection; wildcards do not guarantee a consistent snapshot or prevent `ConcurrentModificationException`.

## 9. Common Mistakes

**"A `List<? extends Number>` variable cannot call `add(42)`, so its object is immutable."** False. What is blocked is adding that value **through the wildcard-typed variable**. Another `List<Integer>` reference can modify the same object.

**"`? extends Number` is equivalent to `List<Number>`."** False. A `List<Integer>` can be viewed as `List<? extends Number>`, yet does not turn into `List<Number>`; inserting a `Double` into `List<Integer>` is not type-safe.

**"`? extends` cannot call any mutating methods."** False. `remove(Object)`, `remove(int)`, and `clear()` do not insert an arbitrary element `E`; hence the compiler allows calling them and mutable implementations can execute them successfully.

**"Using `Collections.unmodifiableList` prevents seeing changes to the source."** False. The wrapper tracks the source list. To retain a structural snapshot independent of a mutable source, create an appropriate unmodifiable copy.

**"`List.copyOf` makes every element immutable."** False. The list is structurally copied and holds references to the elements; mutable element objects can still change state from elsewhere.

**"Wildcards make data safe when accessed by multiple threads concurrently."** False. Generics handle types, not synchronization.

## 10. Self-Check

**Question 1.** Given `List<Integer> a = new ArrayList<>(); List<? extends Number> b = a;`, why does `a.add(42)` work while `b.add(42)` does not compile?

Because the compiler knows `a`'s exact element type is `Integer`, whereas `b`'s is an unknown subtype of `Number`. Both still point to the same object.

**Question 2.** After `a.add(42)`, does `b.size()` change?

Yes, because the underlying list is the exact object `a` just modified. The assignment `b = a` does not create a copy.

**Question 3.** Does `b.clear()` compile? Does it always run successfully?

It compiles. It runs successfully if the underlying object supports `clear`; for example `ArrayList` supports it, while `List.of` and unmodifiable wrappers reject it.

**Question 4.** How do `Collections.unmodifiableList(a)` and `List.copyOf(a)` differ?

The wrapper blocks modification through itself yet can observe modifications to `a`; when `a` is mutable, `List.copyOf(a)` creates an unmodifiable list storing the element structure at creation time, without reflecting subsequent additions or removals on `a`.

**Question 5.** Why is `List<? extends Number>` still useful if it does not guarantee immutability?

Because it allows an API to read many kinds of `List` whose elements are subtypes of `Number`, while preventing code using that reference from accidentally adding an incompatible element type. That is **type safety**, a different goal from **data immutability**.

## Conclusion

`? extends Number` expresses "I can read elements belonging to an unknown subtype of `Number`." It **does not create an immutable object**: a concretely typed source reference can still modify it if the implementation permits, and removal operations that do not insert new elements can also be called through the wildcard. To protect state, you must choose appropriate object contracts, wrappers, or snapshots, while managing aliases and mutable element objects.