# Collection.removeIf(), List.replaceAll(), and Collection.forEach() in Java

These three APIs let you pass **behavior** into a collection using a lambda or method reference: filtering out elements by condition, transforming each element, and performing an action on each element. They often make code shorter than manual loops, but differ in **callback type, mutability capability, and return value**.

## 1. Three APIs solving three different needs

| API | Declaration location and callback type | Effect on collection | Result |
| --- | --- | --- | --- |
| `Collection.removeIf(Predicate<? super E> filter)` | `Collection`; tests each element, returns `boolean` | Removes in place every element matching the condition; may reduce size | `boolean`: `true` if any elements were removed |
| `List.replaceAll(UnaryOperator<E> operator)` | `List`; takes `E`, returns a replacement `E` | Reassigns each position in the list; size remains unchanged | `void` |
| `forEach(Consumer<? super T> action)` | Declared on `Iterable`, inherited by `Collection` | Calls the action for each element; the traversal operation itself is not meant to modify the collection | `void` |

All three have been provided since Java 8. `removeIf` applies to collections that support removal, including many `Set` implementations; `replaceAll` is only on `List`. `forEach` can be called on any `Iterable`, including `List`, `Set`, and other collections.

How to read the callback types:
- `Predicate<E>`: `E -> boolean`, used to **select elements to remove**.
- `UnaryOperator<E>`: `E -> E`, used to **compute a replacement value** of the same type.
- `Consumer<E>`: `E -> void`, used to **perform an action**, such as printing or logging.

## 2. `Collection.removeIf()`: removing by condition

For example, to remove all even numbers from a list:

```java
List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3, 4, 5));
boolean changed = numbers.removeIf(n -> n % 2 == 0);
// changed == true; numbers == [1, 3, 5]
```

This is an illustrative snippet that needs to be placed inside a method or class that imports `java.util.ArrayList` and `java.util.List`.

- Java tests elements one by one using the predicate. Elements for which the predicate returns `true` are **the removed elements**, not the retained elements.
- The method mutates the receiving collection itself; it does not return a new collection. When no elements are removed, the result is `false`.
- The default implementation uses `Iterator` and `Iterator.remove()` to remove matching elements; concrete classes can optimize this mechanism, such as `ArrayList`.
- Collections that do not support removal may throw `UnsupportedOperationException`. For instance, `List.of(...)` is an immutable list; `Arrays.asList(...)` has a fixed size and does not support removing elements.
- The predicate should have no side effects, especially not adding/removing elements of the same collection during traversal.

When you want to **preserve the original collection** and create a new result, use `stream().filter(...)` instead of `removeIf`. The two approaches are not equivalent: `removeIf(p)` **removes** elements matching `p`, whereas `filter(p)` **keeps** elements matching `p`.

## 3. `List.replaceAll()`: replacing each element in place

`replaceAll` invokes the operator on each element and writes the result back to the corresponding position:

```java
List<String> words = new ArrayList<>(List.of(" java ", " lambda "));
words.replaceAll(String::trim);
words.replaceAll(String::toUpperCase);
// words == [JAVA, LAMBDA]
```

This is an illustrative snippet using imports `java.util.ArrayList`, `java.util.List`.

- The list still has **the same number of elements and the same positions**; the values at those positions can change.
- The operator needs to return a replacement value. A lambda like `s -> s.trim()` is valid; a lambda that only calls `System.out.println(s)` is unsuitable because it does not return a `String`.
- The default implementation iterates via `ListIterator` and uses `set(...)`. A list that supports `set` but does not allow adding/removing can still use `replaceAll`; for example, `Arrays.asList(...)`.
- An immutable list or one that does not support replacing elements may throw `UnsupportedOperationException`. On a list that allows `null` values, the operator may produce `null`; ensure the result complies with the list's rules.
- When you need to **create a new list** instead of modifying in place, use `stream().map(...).toList()` (Java 16+); the list returned by `Stream.toList()` is unmodifiable.

Do not confuse `List.replaceAll(UnaryOperator)` with `Collections.replaceAll(List, oldValue, newValue)`: the second API replaces elements **with a specific value**, and does not accept a general transformation function.

## 4. `forEach()`: executing an action for each element

```java
List<String> names = List.of("An", "Bình", "Chi");
names.forEach(name -> System.out.println("Xin chào " + name));
// Equivalent to: names.forEach(System.out::println) when you only want to print the names.
```

This is an illustrative snippet using `java.util.List`. With an ordered list as above, the greetings appear in the order `An`, `Bình`, `Chi`.

- The callback is a `Consumer`, with no return value. `forEach` is suitable for printing, sending results, or controlled side effects; use `map` when the goal is to compute new data.
- The default `forEach` method of `Iterable` executes actions in the iteration order of the iterable, **if the iterable defines an order**. With `HashSet`, do not rely on a fixed print order.
- `Collection.forEach` is called via inheritance from `Iterable`; it is **not** `Stream.forEach`. Parallel streams may process elements out of observable order; `forEachOrdered` is only for streams when you need to preserve encounter order.
- Do not remove/add elements to the collection itself from inside the callback. For many collections, doing so can lead to `ConcurrentModificationException` or unreliable behavior. To remove elements, use `removeIf`.

## 5. Complete runnable Java 17+ example: combining all three APIs

Save as `CollectionBehaviorDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class CollectionBehaviorDemo {
    public static void main(String[] args) {
        List<String> labels = new ArrayList<>(
                List.of(" an ", "  ", "Bình", "Chi", "An")
        );

        // Remove elements containing only whitespace.
        boolean removed = labels.removeIf(String::isBlank);

        // Normalize each value in place.
        labels.replaceAll(String::trim);
        labels.replaceAll(s -> s.toUpperCase(Locale.ROOT));

        System.out.println("removed = " + removed);
        labels.forEach(s -> System.out.println("item = " + s));
        System.out.println("result = " + labels);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 CollectionBehaviorDemo.java
java CollectionBehaviorDemo
```

Expected output:

```text
removed = true
item = AN
item = BÌNH
item = CHI
item = AN
result = [AN, BÌNH, CHI, AN]
```

Step-by-step explanation:

1. Initially there are five elements, including the string `"  "` containing only spaces. `String::isBlank` returns `true` for this string so `removeIf` removes it; `removed` is `true`.
2. `replaceAll(String::trim)` removes leading/trailing whitespace from each remaining string.
3. `replaceAll(s -> s.toUpperCase(Locale.ROOT))` converts the strings to uppercase with a neutral locale. Both `replaceAll` calls preserve the four existing positions.
4. `forEach` prints the four normalized strings in the order of the `ArrayList`. The last line confirms the original list was modified in place.

`new ArrayList<>(List.of(...))` is used intentionally: `List.of` provides convenient input data but is an immutable list; `ArrayList` can remove and reassign elements.

## 6. Choosing the right API for the situation

| Requirement | Should use | Reason |
| --- | --- | --- |
| Remove invalid records from a mutable collection | `removeIf(x -> invalid(x))` | Updates the original collection; returns whether anything was removed |
| Normalize all strings in a mutable list | `replaceAll(String::trim)` | Replaces values at the same positions, preserving size |
| Print, log, or trigger an action per element | `forEach(System.out::println)` | `Consumer`-style callback |
| Create a separate result collection, keeping original data | `stream().filter(...).toList()` or `stream().map(...).toList()` | Pipeline creates a new result without mutating input data through filtering/mapping |

Example with a fixed-size list:

```java
List<String> fixed = java.util.Arrays.asList(" a ", " b ");
fixed.replaceAll(String::trim);             // Valid: replaces the elements.
fixed.removeIf(s -> s.equals("a"));          // Throws UnsupportedOperationException.
```

This is a standalone snippet demonstrating operation support, not part of the main program. `Arrays.asList` allows `set` but does not allow removing elements that change the size. `List.of("a", "b")` is unsuitable for `replaceAll` or `removeIf` because it is immutable.

## 7. Common pitfalls and important notes

1. **Confusing the filter logic:** `removeIf(x -> x.isEmpty())` removes empty strings. If you want to *keep* empty strings, you must invert the condition.
2. **Confusing in-place mutation with returning a result:** `removeIf` returns `boolean`, while `replaceAll` and `forEach` return `void`. You cannot assign the result of `replaceAll` to a `List`.
3. **Using immutable collections:** `List.of`, `List.copyOf`, and lists returned by `Stream.toList()` do not support the structural/value updates above. Copy into an `ArrayList` when modification is needed.
4. **Mutating the collection inside `forEach`/predicate:** avoid calling `list.remove(...)` or `list.add(...)` in a callback iterating over that same list; use `removeIf` or design a separate processing pass.
5. **Assuming ordering on all collection types:** `ArrayList` iterates in index order, but `HashSet` does not guarantee a specific order.
6. **Assuming callbacks always complete for all elements:** if a predicate/operator/action throws an exception, the call may stop partway through; earlier updates may already have occurred. These three methods do not guarantee atomicity or automatic rollback.
7. **Sharing a collection across multiple threads without coordination:** these APIs do not synchronize automatically; you must follow the implementation's thread-safety contract, or choose an appropriate structure/synchronization mechanism.
8. **Unintended side effects:** keep predicates and unary operators predictable, not depending on mutable external state. With `forEach`, clearly control side effects and handle exceptions if needed.

Regarding cost, each API typically needs to traverse the elements, but actual complexity depends on the implementation and the work inside the callback; do not assume every `Collection` has the same performance characteristics.

## Key takeaways

- **`removeIf` = remove elements matching `Predicate`**, can change size and returns `boolean`.
- **`replaceAll` = transform each value with `UnaryOperator`**, preserves list size.
- **`forEach` = execute `Consumer` on each element**, does not create a result list.

Before using data-mutating APIs, always check whether the collection supports **remove** or **set**; this is the crucial boundary between `ArrayList`, fixed-size lists, and immutable lists.
