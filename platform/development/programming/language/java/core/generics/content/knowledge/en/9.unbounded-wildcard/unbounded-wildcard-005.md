# Why Can You Still Call `clear()` or `remove()` on Some `List<?>`?

## Objectives

After this lesson, you will be able to explain accurately why a `List<?>` declaration prevents many **add or replace element** operations yet still allows **calling removal methods** such as `clear()`, `remove(Object)`, `remove(int)`, and `removeIf(...)`. You will also distinguish two separate questions:

1. **Does the compiler allow calling the method?** — depends on the static type `List<?>` and the method signature.
2. **Does the actual list object support modification?** — depends on the implementation, state, and runtime contract of the list.

These two questions explain the keyword **“some”** in the title: the same `List<?>` declaration can point to a modifiable list, a fixed-size list, or an unmodifiable list.

## 1. What does `List<?>` mean?

`List<?>` is a `List` with an **unknown concrete element type** (unbounded wildcard). For example, the same method parameter of type `List<?>` can accept `List<String>`, `List<Integer>`, or `List<Customer>`. The compiler cannot assume that element type is `String`, `Integer`, or `Object`.

```java
static void inspect(List<?> values) {
    Object element = values.get(0); // valid if the list has elements
    System.out.println(element);

    // values.add("new");   // compile error
    // values.add(123);     // compile error
    // values.set(0, "new"); // compile error
}
```

This is an **illustrative method snippet**, not a standalone Java file. With `get(0)`, an element of unknown type can still be viewed as `Object` because every Java reference type is a subtype of `Object`. Conversely, to add a `String` into `List<?>`, the compiler needs to prove `String` is compatible with the **unknown actual element type**. It cannot prove that if the actual object might be a `List<Integer>`.

**Do not interpret `List<?>` as synonymous with a read-only list.** The wildcard describes a type-information limitation at compile time; it does not by itself make the object immutable.

## 2. Mechanism: removal operations do not need to know `E` to insert a new value into the list

Look at the main signatures of the `List<E>` and `Collection<E>` APIs. The snippet below depicts **signature shapes for learning**, not a complete copy of the JDK interface declarations:

```java
// Methods involving E:
boolean add(E element);
E set(int index, E element);
E get(int index);

// Removal methods:
void clear();
boolean remove(Object value);
E remove(int index);
boolean removeIf(java.util.function.Predicate<? super E> filter);
```

These methods may be declared directly in `List` or inherited by `List` from `Collection`. When a variable has type `List<?>`, the compiler treats `E` as an **unknown wildcard capture type**. What matters is whether the method **accepts** or **returns** a value of type `E`:

- `add(E)` and `set(int, E)`: insert a new element into a position of type `E`. You cannot arbitrarily pass a known non-null object such as `String` or `Integer` into `List<?>`.
- `clear()`: **accepts no** new elements. Clearing all existing elements creates no risk of putting a wrong type into the list.
- `remove(Object)`: accepts an `Object` argument to search/remove by equality comparison, **without requiring** the parameter to have the exact type `E`.
- `remove(int)`: accepts only an **`int` index**. The removed value has the unknown type `E`, yet that result can be received as type `Object`.
- `removeIf(Predicate<? super E>)`: the predicate only **inspects** each element and decides whether to remove it; no new element of type `E` needs to be inserted.

Therefore, all of the removal calls above **can compile** through a `List<?>` reference. The phrase “can compile” does not mean they will always succeed at runtime.

### Why does `remove(Object)` use `Object`?

A signature taking `Object` allows finding and attempting to remove an object based on `equals`, even when the type of the passed-in object does not match the list's element type. For example, calling `listOfStrings.remove(123)` **is valid at compile time**; on a regular `ArrayList<String>`, the call returns `false` if there is no matching element. A specialized implementation can still apply its own contract constraints; do not infer that every list must respond identically to every argument.

Meanwhile, `add` takes `E` because its purpose is to **store** the object in the list. Allowing arbitrary additions through `List<?>` could break the type promise of a `List<Integer>`.

### Why is `remove(int)` valid even though it returns `E`?

The return type can be an unknown capture type that the compiler still safely assigns to `Object`:

```java
static Object takeFirst(List<?> list) {
    return list.remove(0); // valid, the list must have at least one element
}
```

The method does not need to create or insert an object of type `E`. However, if the list is empty, `remove(0)` throws `IndexOutOfBoundsException`; if the implementation does not support removal, it may throw `UnsupportedOperationException`.

## 3. Standalone runnable Java 17+ example

Create the file **`WildcardRemovalDemo.java`** with the full content:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class WildcardRemovalDemo {

    static void removeAndClear(List<?> elements) {
        Object first = elements.remove(0);
        System.out.println("Removed by index: " + first);

        boolean removedByValue = elements.remove("cam");
        System.out.println("Removed by value: " + removedByValue);

        elements.clear();
        System.out.println("After clear: " + elements);
    }

    public static void main(String[] args) {
        List<String> fruits =
                new ArrayList<>(List.of("tao", "cam", "le"));

        List<?> view = fruits;
        System.out.println("First: " + view.get(0));
        removeAndClear(view);
        System.out.println("Original: " + fruits);

        List<?> numbers = new ArrayList<>(List.of(1, 2, 3, 4));
        boolean changed = numbers.removeIf(
                e -> e instanceof Integer i && i % 2 == 0);
        System.out.println("Remove evens: " + changed + " -> " + numbers);

        List<?> fixedSize = Arrays.asList("a", "b");
        try {
            fixedSize.clear();
        } catch (UnsupportedOperationException e) {
            System.out.println("Arrays.asList: clear unsupported");
        }

        List<?> immutable = List.of("a", "b");
        try {
            immutable.remove(0);
        } catch (UnsupportedOperationException e) {
            System.out.println("List.of: remove unsupported");
        }
    }
}
```

Compile/run with JDK 17 or later from the directory containing the file:

```bash
javac WildcardRemovalDemo.java
java WildcardRemovalDemo
```

Stdout:

```text
First: tao
Removed by index: tao
Removed by value: true
After clear: []
Original: []
Remove evens: true -> [1, 3]
Arrays.asList: clear unsupported
List.of: remove unsupported
```

Sequence explanation:

1. `fruits` has type `List<String>`, while `view` has type `List<?>`; **both point to the same `ArrayList`**. `view.get(0)` reads the first element.
2. `elements.remove(0)` removes `"tao"` and returns the element as type `Object`. `elements.remove("cam")` removes the string `"cam"` because it exists, so it returns `true`.
3. `elements.clear()` removes the remaining `"le"`. Printing `fruits` again shows `[]`, proving the wildcard does not create a copy and does not freeze the object.
4. `removeIf` iterates over the values and removes the two even numbers from the `ArrayList`. Here the predicate checks the type with `instanceof` and then checks the remainder; this pattern matching syntax is valid since Java 16.
5. The last two calls are both **through `List<?>` and valid at compile time**, yet fail at runtime because the underlying lists do not support removal.

The program intentionally uses `new ArrayList<>(List.of(...))` for the part needing removal: `List.of(...)` itself does not support modification operations. The `removeAndClear` function assumes the input list is **non-empty and modifiable**; you should not call it with an arbitrary `List<?>` without knowing the object's contract.

## 4. “Some” lists: differing in mutability, not in the wildcard

| Way of creating the list | Can call `clear/remove` from `List<?>`? | When the list has elements, does it support actual removal? |
| --- | --- | --- |
| `new ArrayList<>(...)` | Yes | Yes; resizable list |
| `new LinkedList<>(...)` | Yes | Yes; resizable list |
| `Arrays.asList("a", "b")` | Yes | No; fixed-size list, usually allows `set` but forbids add/remove |
| `List.of("a", "b")` | Yes | No; unmodifiable list |
| `List.copyOf(source)` | Yes | No; creates an unmodifiable list |
| `Collections.unmodifiableList(source)` | Yes | Not through the wrapper; modification operations are rejected |
| `new CopyOnWriteArrayList<>(...)` | Yes | Direct `remove/clear` methods are supported; `Iterator.remove()` is unsupported |

The table distinguishes **statically type-valid calls** from the **runtime behavior of typical implementations**. In the JDK, many collection modification operations are considered *optional operations*; when unsupported, an implementation can throw `UnsupportedOperationException`. This holds for `List<String>` or `List<Integer>` variables as well, not specifically because of `?`.

In particular, **fixed size** does not mean completely immutable: a list created by `Arrays.asList(...)` allows replacing values at existing indices with `set` when called through a reference with an appropriate element type, yet forbids changing the number of elements. Conversely, `List.of(...)` forbids changing both values and size.

With `Collections.unmodifiableList(source)`, the wrapper forbids modification through itself; if other code still holds `source` and can modify `source`, the contents viewed through the wrapper can change. Therefore, an “unmodifiable view” also differs from an “immutable snapshot”.

## 5. Two `remove` overloads: removing by index and by value

Java has both `remove(int index)` and `remove(Object value)`. Both can be called on `List<?>`, yet they select different targets.

```java
List<?> values = new ArrayList<>(List.of(10, 20, 30));
values.remove(1);                 // removes index 1: removes 20
values.remove(Integer.valueOf(30)); // removes value 30
System.out.println(values);       // [10]
```

This is an **illustrative snippet**, which can be placed inside a method of a Java class that has imported `java.util.ArrayList` and `java.util.List`.

- A primitive `int` argument like `1` selects `remove(int)`.
- An argument `Integer.valueOf(30)` selects `remove(Object)` under overload resolution rules, so it searches for the element by value.
- If you want to remove an integer by value without confusing it with an index, use `Integer.valueOf(value)` or cast the argument to `Object`.
- `remove(int)` returns the removed element, and can throw `IndexOutOfBoundsException` if the index is invalid. `remove(Object)` returns a `boolean` indicating whether removal by value occurred on lists that support removal.

Confusing overloads can lead to removing the wrong element or an index error even when the wildcard and implementation fully permit removal.

## 6. Removing with an iterator and other collection methods

Wildcards do not inherently forbid removal via an iterator either, because `Iterator.remove()` does not require supplying an element of type `E`:

```java
static void removeFirstWithIterator(List<?> values) {
    var iterator = values.iterator();
    if (iterator.hasNext()) {
        iterator.next();
        iterator.remove();
    }
}
```

This is an **illustrative method snippet**. With an `ArrayList` iterator, calling `remove()` after `next()` removes the element just traversed. However, `Iterator.remove()` is also an optional operation: the iterator of `CopyOnWriteArrayList` does not support it, even though calling `CopyOnWriteArrayList.remove(Object)` directly can still work. Calling `remove()` without a proper prior `next()` can also throw `IllegalStateException`.

Methods inherited from `Collection`, such as `removeIf(Predicate<? super E>)`, `removeAll(Collection<?>)`, and `retainAll(Collection<?>)`, can also be called through `List<?>`. They select or retain **existing** elements rather than needing to insert an arbitrary element into the unknown type `E`. They may still be unsupported by an implementation.

During iteration/removal, avoid modifying an `ArrayList` directly with `list.remove(...)` inside a foreach loop that is using its own iterator; doing so can cause `ConcurrentModificationException`. If you need to filter for removal, prefer `removeIf` or `Iterator.remove` according to the implementation's contract.

## 7. Special case of `null`

Although `add("abc")` does not compile when the receiver is `List<?>`, **`list.add(null)` can compile**: `null` is convertible to any reference type, including an unknown capture type. Similarly, `list.set(0, null)` passes static type checking.

That **does not guarantee success at runtime**. For example, `List.of(...)` does not support adding/replacing elements, and some collections do not accept `null`. You should not treat the ability to pass `null` as a workaround for writing arbitrarily typed elements into `List<?>`.

`remove(null)` also compiles because the `remove(Object)` overload accepts a `null` reference. The outcome still depends on the underlying object: whether the list permits null elements, whether it supports removal, and what its argument-validation rules are.

## 8. Safe API design

If a method only needs to remove an element by object or empty the list, declaring `List<?>` accurately expresses that **the logic does not depend on the element type**:

```java
static void reset(List<?> items) {
    items.clear(); // callable if the runtime list supports clear()
}
```

If code needs to **add or replace new `String` elements**, declare the parameter as `List<String>` or an appropriate generic type. If code needs to read and preserve an element's type relationship across multiple operations, a generic method can be used instead of an unsafe cast:

```java
static <T> void replaceFirstWithSameValue(List<T> items) {
    if (!items.isEmpty()) {
        T first = items.get(0);
        items.set(0, first);
    }
}
```

This is an **illustrative method snippet**. The relationship between `T` of the `get` result and the argument of `set` is preserved by the compiler; the method still requires the implementation to support `set`.

Do not convert `List<?>` to a raw `List` or arbitrarily cast it to `List<Object>` just to call `add`. Casting does not change the actual element type and can break type safety, leading to errors at other usage sites. Nor is the name `List<?>` synonymous with `List<Object>`: `List<?>` accepts many kinds of lists, whereas `List<Object>` can accept any `Object` allowed to be added.

## 9. Quick check

**Question 1.** If `List<?> a = new ArrayList<String>();`, will `a.clear()` compile and run?

**Answer:** Yes. `clear` does not need a `String` type argument, and `ArrayList` supports removal operations.

**Question 2.** If `List<?> b = List.of("x");`, does `b.remove(0)` cause a compile error?

**Answer:** No. The call is valid at compile time; at runtime it throws `UnsupportedOperationException` because lists from `List.of` do not allow modification.

**Question 3.** Why is `a.remove("x")` allowed while `a.add("x")` is blocked by the compiler?

**Answer:** `remove` takes `Object` and only searches/removes an existing element; `add` takes `E` and must be sure the new element matches the unknown type represented by the wildcard.

**Question 4.** Does `List<?>` always allow removal using an iterator?

**Answer:** No. Statically, calling `iterator.remove()` is type-valid; at runtime, some iterators reject this operation.

## Conclusion

**`List<?>` restricts inserting an arbitrary non-null value into the list because the element type is unknown; it does not by itself forbid removing existing elements.** The methods `clear()`, `remove(Object)`, and `remove(int)` do not require you to supply a new element of type `E`, so they can pass the compiler's type check. Whether removal **can actually be executed** is the responsibility of the implementation and runtime contract of the list, not the `?` sign.