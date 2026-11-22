# removeIf and Removal Predicate Handling

When you need to remove all elements that are no longer valid, you can describe the task with a condition: remove cancelled orders, remove empty strings, remove expired items, or remove even numbers. `removeIf` expresses that operation directly: **test each element with a predicate and remove the elements that satisfy it from the target collection**.

The key point to grasp from the start is the direction of the predicate:

- Predicate returns `true`: the element is marked for removal.
- Predicate returns `false`: the element is kept.

This is an in-place mutation. It differs from creating a new result list by filtering a stream. This article belongs to the general contracts section of the Java Collections Framework; the examples use Java 17 or later.

## 1. The Contract of removeIf

The signature declared in `Collection<E>` is:

```java
default boolean removeIf(Predicate<? super E> filter)
```

This is an API signature, not a standalone program.

`Predicate<T>` represents a test that takes a value of type `T` and returns `boolean`. A lambda such as `n -> n % 2 == 0` is one way to write a predicate for even numbers.

`? super E` allows passing a predicate that handles elements of type `E` or a suitable supertype. For example, a `Predicate<Object>` can be used to test the elements of a `Collection<String>`. You do not need arbitrary casts to write ordinary conditions.

If the method completes normally:

| Situation | Result |
| --- | --- |
| At least one element was removed | Returns `true` |
| No elements were removed | Returns `false` |

The return value is **not the count of removed elements**, nor is it the predicate result for the last element. If the collection is empty or no elements match the predicate, a collection that supports the operation can complete and return `false`.

A `null` predicate is invalid. Exceptions thrown during testing or removal are propagated to the caller; the general contract does not promise to roll back any changes that have already occurred. [Java 17: Collection.removeIf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#removeIf(java.util.function.Predicate))

## 2. Removing Every Matching Element, Not Just the First

Example inside a method:

```java
List<Integer> numbers =
        new ArrayList<>(List.of(1, 2, 2, 3, 4));

boolean changed = numbers.removeIf(n -> n % 2 == 0);

System.out.println(changed); // true
System.out.println(numbers); // [1, 3]
```

You need to import `List` and `ArrayList` from `java.util`.

Both occurrences of `2` and the element `4` are removed. For this list, the remaining elements preserve their original relative order.

If called again:

```java
boolean changedAgain = numbers.removeIf(n -> n > 10);
System.out.println(changedAgain); // false
System.out.println(numbers);      // [1, 3]
```

No number is greater than 10, so nothing changes.

`removeIf` does not add, replace, or transform element values. If you need to convert each value into a new one, you must choose another operation such as `List.replaceAll` or stream mapping.

### Distinguishing from Other Removal Operations

| Need | How to Express It |
| --- | --- |
| Remove a single occurrence of a value | `remove(value)` |
| Remove elements belonging to a set of values | `removeAll(values)` |
| Keep only elements belonging to a set of values | `retainAll(values)` |
| Remove by property or computed condition | `removeIf(predicate)` |
| Remove everything | `clear()` |

For example, `removeIf(n -> n == 2)` on a list of integers without `null` removes every `2`. It avoids the ambiguity between `List<Integer>.remove(int index)` and `remove(Object value)`, because the removal condition is stated explicitly. However, `n == 2` involves unboxing and will throw an error if it encounters `null`; the `null` policy must be designed separately.

## 3. Default Mechanism and Collection Mutability

### 3.1. Default Implementation Using an Iterator

You can picture the default implementation of `Collection.removeIf` through this illustrative code:

```java
boolean changed = false;
Iterator<E> iterator = collection.iterator();

while (iterator.hasNext()) {
    E element = iterator.next();
    if (filter.test(element)) {
        iterator.remove();
        changed = true;
    }
}
return changed;
```

This code illustrates the algorithm, omitting the non-`null` check on the predicate; it is not a complete program to copy directly.

Note the word **default**: a class may override the method with handling tailored to its own structure. Do not assume every collection removes elements one by one using an iterator, or that all collections have the same cost and behavior when the predicate fails.

`Iterator.remove()` is an optional operation. With the default implementation, if the iterator does not support removal, `UnsupportedOperationException` may be thrown when a matching element needs to be removed. [Java 17: Iterator.remove](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html#remove())

### 3.2. Do Not Remove via the Collection Inside a for-each Loop

The following snippet is an error-prone pattern:

```java
// Do not use this approach to remove elements while iterating over an ArrayList.
for (Integer number : numbers) {
    if (number % 2 == 0) {
        numbers.remove(number);
    }
}
```

A `for-each` loop uses an iterator under the hood. Modifying the structure through another call path while iterating can invalidate the iterator and cause `ConcurrentModificationException` or lead to unexpected behavior. Do not treat "it didn't throw on one run" as proof that it is correct.

For a condition that depends only on the element and stable reference state, use:

```java
numbers.removeIf(number -> number % 2 == 0);
```

If you need step-by-step control over iteration and the iterator supports removal, you can use `iterator.remove()` after `next()`. That is a different case from calling `numbers.remove` from outside the iterator.

### 3.3. Having a List Does Not Mean Having Permission to Remove

Lists can differ in mutability:

| Creation Source | Removal Capability |
| --- | --- |
| `new ArrayList<>(...)` | Supports removing elements |
| `Arrays.asList(...)` | Fixed-size list; does not support removals that change size |
| `List.of(...)` | Does not allow modifying contents through the list API |
| `Collections.unmodifiableList(source)` | Unmodifiable view; the underlying source can still change via another reference |
| `CopyOnWriteArrayList` | Supports `removeIf`, even though its iterator does not support `remove` |

`Arrays.asList` is not a regular `java.util.ArrayList`. It allows replacing elements with `set` but does not allow reducing the number of elements. When removal is needed, you can explicitly create a mutable copy:

```java
List<String> editable =
        new ArrayList<>(Arrays.asList("old", "keep", "old"));

editable.removeIf("old"::equals);
System.out.println(editable); // [keep]
```

This is an illustrative snippet inside a method; the corresponding classes must be imported. [Java 17: Arrays.asList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...))

Do not use a predicate that always returns `false` to probe whether a collection is mutable. For an unsupported operation, a case that makes no changes may still be rejected depending on the contract. Know the creation source and your mutation rights.

## 4. Designing Removal Predicates with the Right Meaning

### 4.1. Name Predicates After the Removal Condition

Compare these two naming approaches:

```java
Predicate<Order> shouldDelete =
        order -> order.status() == Status.CANCELLED;

orders.removeIf(shouldDelete);
```

and:

```java
Predicate<Order> shouldKeep =
        order -> order.status() != Status.CANCELLED;

orders.removeIf(shouldKeep); // Wrong intent: this removes the orders that should be kept.
```

These are illustrative snippets; `Order`, `Status`, and `orders` are defined by the application.

Names like `expired`, `cancelled`, or `shouldDelete` help verify the direction of the condition. If you already have a predicate describing what to "keep", you must invert it with `negate()` when using it as a removal condition.

### 4.2. Handle null Before Calling Methods on Elements

If the list may contain `null`, the following predicate is unsafe:

```java
names.removeIf(name -> name.isBlank());
```

It throws `NullPointerException` when it encounters `null`. First, decide whether `null` should be removed or kept.

Remove both `null` and blank strings:

```java
names.removeIf(name -> name == null || name.isBlank());
```

Keep `null`, remove only non-null blank strings:

```java
names.removeIf(name -> name != null && name.isBlank());
```

Remove only `null`:

```java
names.removeIf(Objects::isNull);
```

These snippets assume `names` has already been created and `java.util.Objects` is imported for the last example.

The `||` and `&&` operators use short-circuit evaluation. In the first case, if `name == null` is true, `isBlank` is not called. Reversing the order to `name.isBlank() || name == null` no longer protects against `null`.

A field inside an object can also be `null`. Guarding with `item != null` is not enough if you then call `item.owner().isBlank()` and `owner()` can still return `null`.

### 4.3. Compose Multiple Conditions Deliberately

`Predicate` provides composition methods:

- `a.and(b)`: both conditions are true.
- `a.or(b)`: at least one condition is true.
- `a.negate()`: inverts the result.

Example with `null`-sanitized data:

```java
Predicate<String> longName = name -> name.length() > 3;
Predicate<String> startsWithM = name -> name.startsWith("M");

names.removeIf(longName.and(startsWithM));
```

This predicate removes names longer than 3 characters **and** starting with `M`. It does not remove every name starting with `M`, nor does it remove every long name.

`and` and `or` short-circuit in order. If the first condition already determines the result, the second condition is not invoked. If a predicate throws an exception, the exception is propagated rather than automatically converted to `false`. [Java 17: Predicate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Predicate.html)

### 4.4. Fix the Reference Point for a Processing Batch

Suppose you want to remove tasks that are archived or expired before a cutoff date:

```java
record Task(String id, LocalDate expiresOn, boolean archived) {}

LocalDate cutoff = LocalDate.of(2025, 1, 1);

Predicate<Task> shouldDelete = task ->
        task.archived()
        || (task.expiresOn() != null
            && task.expiresOn().isBefore(cutoff));

tasks.removeIf(shouldDelete);
```

This illustration requires importing `LocalDate`, `Predicate`, and having a `tasks` list with no `null` elements. Here, `expiresOn == null` represents having no expiration date.

The condition uses "before the cutoff date", so a task whose expiration date equals `cutoff` is not removed for expiration. If you want "up to and including the cutoff date", you must express the condition to include equality.

Do not query the clock or load continuously changing state per element if the business rule is to evaluate everything against the same reference point. Computing the reference point once makes the result easier to test and reason about. For exact instants or time zones, choose the appropriate time types and rules; do not arbitrarily convert every problem to local dates.

## 5. Keep Predicates Focused on Testing

A manageable predicate typically:

- Reads only the element and precomputed reference values.
- Returns `true` or `false` according to a clear rule.
- Does not add or remove elements in the collection currently being processed.
- Does not mutate properties used to decide outcomes for other elements.
- Does not perform external side effects such as sending messages, charging money, or deleting remote records.

Example to avoid:

```java
// Illustrates an incorrect pattern: the predicate mutates the very list being filtered.
items.removeIf(item -> {
    items.add(replacement);
    return item.isExpired();
});
```

`items`, `replacement`, and the element type above only illustrate the scenario. Modifying the structure inside the predicate can cause traversal to fail or violate the implementation's requirements. Do not rely on a specific exception type as a valid control-flow mechanism.

A predicate that has to call a network service to decide whether to remove an element also makes execution time and failures hard to predict. When appropriate, prepare reference data upfront, validate it, and then evaluate the predicate in memory.

If you need to record which items were removed, design a separate classification step or build a separate result. Do not rely on the number of times or the order in which the predicate is called as a general auditing mechanism across all collections.

## 6. Exceptions and Partial Removal State

### 6.1. No Transactional Guarantee in the General Contract

Suppose a predicate removes even numbers but throws an exception when it encounters `3`. A default implementation may have already removed `2` before reaching `3`. The exception terminates the method, but it does not put `2` back.

Therefore:

- When the method throws an exception, no `boolean` value is returned for that call.
- Do not conclude the collection is unchanged just because you did not receive `true`.
- Do not blindly retry if the predicate had external side effects or requires exactly-once processing.

A specific class may handle this differently, such as marking elements first and mutating data afterward. That does not establish a rollback guarantee that applies to all `Collection` implementations.

The program at the end of this article creates a small collection using the default implementation to observe partial removal. It does not extrapolate `ArrayList`'s specific failure behavior into the general contract.

### 6.2. When You Need "All or Nothing"

If the requirement is to publish the result only when every condition evaluates successfully, you can:

1. Create a separate result collection.
2. Evaluate the condition and place the elements to keep into the result.
3. If everything succeeds, swap the reference managed by the owning component.

This still requires a design that accounts for other holders of the reference and concurrent access. Making a copy does not automatically create a transaction with a database or external service; the copy usually still holds references to the same element objects.

Do not treat `clear()` followed by `addAll(result)` on a shared collection as an atomic operation. If multiple parties must observe a consistent state together, you need a dedicated publication or synchronization mechanism.

## 7. In-Place Removal or Creating a New Result?

These two snippets have opposite predicate directions:

```java
numbers.removeIf(isEven); // Removes elements where isEven == true.
```

```java
List<Integer> kept = numbers.stream()
        .filter(isEven.negate()) // Keeps elements where isEven == false.
        .toList();
```

This assumes `Predicate<Integer> isEven` is already defined.

| Aspect | `removeIf` | `stream().filter(...).toList()` |
| --- | --- | --- |
| What gets modified | Target collection | Does not structurally modify the source via filtering |
| `true` from predicate | Remove | Keep |
| Return value | `boolean` indicating whether anything was removed | A result list |
| Requires source removal support | Yes | No |
| Element references | Kept elements remain the same objects | Result still references the source objects |

In Java 17, the list returned by `Stream.toList()` does not support modification. If you need a mutable result list, create an `ArrayList` explicitly or use an appropriate collector. Do not mistake `toList()` for a promise to return an `ArrayList`. [Java 17: Stream.toList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList())

Choose based on ownership: if the method is responsible for cleaning up a mutable collection, `removeIf` is usually direct. If the caller needs to preserve the original data or multiple places are using it, a new result may be more appropriate.

## 8. Removing on Views and on Map

`Map` does not have `removeIf` directly like `Collection`, but its views are collections.

Example removing out-of-stock items:

```java
Map<String, Integer> stock = new LinkedHashMap<>();
stock.put("book", 0);
stock.put("pen", 2);
stock.put("case", 0);

stock.entrySet().removeIf(entry -> entry.getValue() == 0);

System.out.println(stock); // {pen=2}
```

You need to import `Map` and `LinkedHashMap`. The sample data guarantees stock values are not `null`.

`entrySet()` is a view backed by the map; removing an entry through the view removes the corresponding mapping from the map. It is not an independent copy.

Common patterns:

```java
map.keySet().removeIf(keyRule);
map.values().removeIf(valueRule);
map.entrySet().removeIf(entryRule);
```

These are usage patterns, not standalone programs. If the condition needs both the key and the value, using `entrySet` expresses it more directly.

A single value may appear under multiple keys. `map.values().removeIf(v -> condition)` can remove multiple mappings if several entries have values matching the condition.

Similarly, a `subList` of a list is a view. Removing from `subList` can remove elements from the backing list as well. Always check whether the object you hold is independent data or a view into other data. [Java 17: Map views](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#entrySet()), [List.subList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#subList(int,int))

## 9. Concurrency and Execution Cost

### 9.1. removeIf Does Not Turn an Ordinary Collection into a Concurrent Structure

Do not call `removeIf` on an `ArrayList` that is being modified by another thread without coordination.

Even for structures that support concurrent access, read the specific contract. Do not assume the entire `removeIf` call is a transaction over all elements, or that all predicate invocations see the same immutable snapshot.

`CopyOnWriteArrayList` is an important example of a class overriding behavior: its iterator does not allow removal, yet the list itself supports `removeIf`. Therefore, do not infer `removeIf` support solely from iterator capabilities. The cost of copying on modification also makes this choice better suited to read-heavy, write-rarely workloads. [Java 17: CopyOnWriteArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html)

### 9.2. Account for Both Predicate Cost and Removal Cost

If `n` elements must be examined, the predicate is evaluated while processing those elements. A simple check is very different from a predicate that makes a network call or searches a large list each time.

Example:

```java
items.removeIf(item -> blockedIds.contains(item.id()));
```

If `blockedIds` is a list of `m` elements and frequently requires a long scan, the check alone can approach `n × m` cost. A prebuilt lookup set can reduce average cost if it matches the equality rules and the data does not change during the batch.

On the other hand, removal itself depends on the data structure: node unlinking, shifting elements, compacting, or copying all have different costs. A class may optimize bulk removal. Do not claim every `removeIf` is O(n), and do not assume it is always faster than every manual loop.

When data is large, measure with the actual collection type, match ratio, and representative predicate. Clarity of the rule remains more important than shortening a lambda at all costs.

## 10. Complete Java 17 Program

Save the following code to `RemoveIfDemo.java`:

```java
import java.util.AbstractCollection;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.function.Predicate;

public class RemoveIfDemo {
    static final class IterableBag<E> extends AbstractCollection<E> {
        private final List<E> data;

        IterableBag(List<E> source) {
            data = new ArrayList<>(source);
        }

        @Override
        public Iterator<E> iterator() {
            return data.iterator();
        }

        @Override
        public int size() {
            return data.size();
        }
    }

    public static void main(String[] args) {
        List<Integer> numbers = new ArrayList<>(List.of(1, 2, 2, 3, 4));
        boolean changed = numbers.removeIf(n -> n % 2 == 0);
        System.out.println("removed even = " + changed);
        System.out.println("numbers = " + numbers);
        System.out.println("removed above 10 = " + numbers.removeIf(n -> n > 10));

        List<String> names = new ArrayList<>(
                Arrays.asList(null, "", "  ", "Lan", "Minh"));
        names.removeIf(name -> name == null || name.isBlank());
        System.out.println("names = " + names);

        Predicate<String> longName = name -> name.length() > 3;
        Predicate<String> startsWithM = name -> name.startsWith("M");
        names.removeIf(longName.and(startsWithM));
        System.out.println("after composed rule = " + names);

        List<Integer> original = new ArrayList<>(List.of(1, 2, 3, 4));
        List<Integer> kept = original.stream().filter(n -> n % 2 != 0).toList();
        System.out.println("original = " + original);
        System.out.println("filtered copy = " + kept);

        Map<String, Integer> stock = new LinkedHashMap<>();
        stock.put("book", 0);
        stock.put("pen", 2);
        stock.put("case", 0);
        stock.entrySet().removeIf(entry -> entry.getValue() == 0);
        System.out.println("stock = " + stock);

        try {
            Arrays.asList(1, 2, 3).removeIf(n -> n % 2 == 0);
        } catch (UnsupportedOperationException expected) {
            System.out.println("fixed-size removal is unsupported");
        }

        try {
            numbers.removeIf(null);
        } catch (NullPointerException expected) {
            System.out.println("null predicate is invalid");
        }

        CopyOnWriteArrayList<String> listeners =
                new CopyOnWriteArrayList<>(List.of("active", "stale"));
        listeners.removeIf("stale"::equals);
        System.out.println("listeners = " + listeners);

        IterableBag<Integer> bag = new IterableBag<>(List.of(1, 2, 3, 4));
        try {
            bag.removeIf(n -> {
                if (n == 3) {
                    throw new IllegalStateException("stop at 3");
                }
                return n % 2 == 0;
            });
        } catch (IllegalStateException expected) {
            System.out.println("predicate failure = " + expected.getMessage());
        }
        System.out.println("bag after failure = " + bag);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 RemoveIfDemo.java
java RemoveIfDemo
```

Stdout:

```text
removed even = true
numbers = [1, 3]
removed above 10 = false
names = [Lan, Minh]
after composed rule = [Lan]
original = [1, 2, 3, 4]
filtered copy = [1, 3]
stock = {pen=2}
fixed-size removal is unsupported
null predicate is invalid
listeners = [active]
predicate failure = stop at 3
bag after failure = [1, 3, 4]
```

How to verify each part:

1. The number list removes all even numbers, including duplicates. The return value is `true`; the second call looking for numbers greater than 10 removes nothing, so it returns `false`.
2. The predicate with a leading `null` check cleans up both `null` elements and blank strings.
3. `and` removes `"Minh"` because it is both longer than 3 characters and starts with `M`.
4. The stream produces a list keeping odd numbers; the `original` list still has all 4 elements.
5. Removing through `entrySet` mutates the stock map itself.
6. The fixed-size list does not support removing the element `2`.
7. A `null` predicate is rejected.
8. `CopyOnWriteArrayList.removeIf` still works even though the class's iterator does not support removal.
9. `IterableBag` extends `AbstractCollection` and provides only an iterator and size. It uses the default `removeIf` algorithm. Element `2` was already removed before the predicate threw at `3`, so `[1, 3, 4]` remains after the failure.

The small `IterableBag` class here is only to clarify the contract and state on failure; it is not a recommendation to write a custom collection instead of using JDK classes in ordinary applications.

## 11. Common Mistakes

| Mistake | Correct Understanding |
| --- | --- |
| Passing a "keep" condition to `removeIf` | `true` means remove; invert the condition when needed |
| Assuming returning `true` means exactly one element was removed | It only indicates a change occurred; multiple elements may have been removed |
| Using a predicate that calls methods on elements that can be `null` | Define the rule and check for `null` first |
| Treating `Arrays.asList` as an add/remove-capable list | It has a fixed size |
| Treating a view as a copy | Removals can propagate to the underlying data |
| Removing from or adding to the collection from inside the predicate | Can break the iteration contract and cause errors |
| Having a predicate both test and send notifications/transactions | Failures or retries can leave irreversible side effects |
| Assuming an exception means nothing was removed | The general contract may leave partial changes |
| Treating a method on a concurrent collection as a full transaction | Must check specific guarantees and invariants to preserve |
| Assuming `removeIf` cannot work if the iterator cannot remove | A class can override the method to support it |

## 12. Self-Check

1. A list `[1, 2, 2, 3]` calls `removeIf(n -> n == 2)`. What remains and what is returned?  
   **Answer:** `[1, 3]` remains, and `true` is returned.

2. A list contains `null`, `""`, and `"A"`. Write a predicate that removes the first two elements without throwing an error.  
   **Answer:** `value -> value == null || value.isBlank()`.

3. You already have a predicate `shouldKeep`. What should you pass to remove the elements that should not be kept?  
   **Answer:** `shouldKeep.negate()`, assuming the predicate is valid for all elements.

4. Why can `removeIf` on `Arrays.asList(1, 2, 3)` not remove `2`?  
   **Answer:** that list does not support resizing.

5. A predicate removed one element and then threw an exception on the next element. Can you rely on the general contract to guarantee the data was rolled back?  
   **Answer:** no. You must check the implementation's guarantees and design a separate workflow if atomicity is required.

A good removal predicate clearly expresses which items must be excluded, handles edge-case data properly, and avoids hard-to-control side effects. Before calling `removeIf`, verify both the predicate rule and the mutability of the collection you hold.
