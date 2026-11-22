# forEach, Lambdas, and Limits on Modifying the Source During Traversal

`forEach` expresses a simple requirement: **perform an action for each element or each mapping**. A lambda describes that action.

Shorter syntax does not remove the rules of traversal. In particular, a lambda may compile successfully while still modifying the data source in an unguaranteed way.

To use it correctly, distinguish between:

- Traversing the source to produce external side effects.
- Modifying the state of element objects.
- Adding, removing, or modifying the very source being traversed.
- Sequential traversal and processing via parallel streams.

## 1. Which forEach Is Being Called?

These expressions have similar names, but their contracts are not completely identical:

| Expression | Receiver Object | Action Parameter | Scope to Consult |
| --- | --- | --- | --- |
| `list.forEach(action)` | An Iterable, such as a List | `Consumer<E>` | Iterable contract and the collection class |
| `map.forEach(action)` | A Map | `BiConsumer<K, V>` | Map contract and the implementation class |
| `stream.forEach(action)` | A Stream | `Consumer<T>` | Stream contract, especially non-interference with the source |
| `stream.forEachOrdered(action)` | A Stream | `Consumer<T>` | Encounter order and how the stream is processed |
| `iterator.forEachRemaining(action)` | An Iterator that already has a traversal position | `Consumer<E>` | Iterator contract and the remaining elements |

There is also the language loop construct:

```java
for (String name : names) {
    System.out.println(name);
}
```

This is a **for-each** loop, not a `forEach` method call.

A for-each loop allows using `break` or `continue` according to loop rules. A lambda passed to `forEach` is a separate function body, so loop control keywords cannot be applied as if writing directly inside an outer loop.

## 2. What Role Does a Lambda Play in forEach?

### 2.1. Consumer Accepts One Element and Returns No Result

Illustrative example inside a method:

```java
names.forEach(name -> System.out.println(name));
```

The lambda receives one name on each invocation. It does not return a new list.

It can also be written using a method reference:

```java
names.forEach(System.out::println);
```

`Consumer<T>` has the functional method `accept(T)` which returns `void`. It fits actions with observable effects such as printing data, sending information, or writing into a separate result destination. See the [Consumer API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Consumer.html).

A method call expression that returns `boolean`, such as `result.add(value)`, can still be used in a lambda matching `Consumer`; the return value of that call is not used as a result of `forEach`.

### 2.2. Map Passes Both Key and Value

```java
levels.forEach((name, level) ->
        System.out.println(name + "=" + level));
```

This snippet receives two arguments for each mapping, not a `Map.Entry`.

`BiConsumer<K, V>` also returns `void`. If you need to compute and replace the value for each key, `Map.replaceAll` expresses that intent better than assuming the `forEach` lambda returns a new value. See the [BiConsumer API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/BiConsumer.html).

### 2.3. Reassigning a Parameter Does Not Replace the Element in the Source

In:

```java
names.forEach(name -> {
    name = name.toUpperCase(Locale.ROOT);
});
```

the parameter variable `name` receives a new value during that lambda invocation. It is not a "list slot" where assignment automatically writes back into the list.

For strings, `toUpperCase` creates or returns an appropriate string value; it does not mutate the original `String` object itself. To produce an uppercase list, use a separate result or an appropriate transformation operation. To replace each element in place, use `List.replaceAll` on a list that supports replacement.

The short snippets in this section require appropriate imports and variables; a standalone program appears in a later section.

## 3. Variables Used by a Lambda: final Does Not Mean Immutable Data

An outer local variable used by a lambda must be `final` or **effectively final**: not reassigned after initialization according to the language rules.

Syntactically valid pattern:

```java
List<String> result = new ArrayList<>();
names.forEach(name -> result.add(name));
```

`result` is not reassigned to a different list, even though the contents of the object it references change.

Non-compiling pattern:

```java
// Illustrates the local variable capture rule, not a runnable program.
// int count = 0;
// names.forEach(name -> count++);
```

Prohibiting modification of captured local variables does not prohibit all side effects. Conversely, the fact that a call like `source.add(...)` compiles does not prove it is permitted during a traversal of the source.

Using a single-element array or an `AtomicInteger` merely to work around variable capture restrictions can hide confusing design. If the goal is counting or summing, consider `count`, `sum`, or an appropriate reduction operation rather than introducing unnecessary shared state.

The rules for local variables used by a lambda are specified in [JLS 17, Lambda Body section](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27.2).

## 4. return, break, and Exceptions Do Not Have the Same Effect

### 4.1. return Only Ends the Current Lambda Invocation

```java
names.forEach(name -> {
    if (name.length() == 2) {
        return;
    }
    System.out.println(name);
});
```

A name of length 2 is skipped for that action. `forEach` still continues with the subsequent elements.

`return` does not:

- Exit the enclosing method calling `forEach`.
- Stop the traversal of `forEach`.
- Return an aggregated result to the caller.

### 4.2. Choose an Appropriate Construct When Early Termination Is Needed

If control flow requires `break` or returning from the enclosing method, a standard loop is usually clearer.

If the goal is testing a condition, you can use a short-circuiting stream operation:

```java
boolean hasLongName =
        names.stream().anyMatch(name -> name.length() > 3);
```

There is no need to traverse everything with `forEach` and use an external flag variable to simulate searching.

Do not deliberately throw ordinary exceptions just to act as `break` when clearer control flow constructs exist.

### 4.3. Exceptions Interrupt Traversal Without Rolling Back

With `Iterable.forEach`, if the action throws an exception, the exception is relayed to the caller and the traversal does not continue as a normal completion.

Actions already performed before the failure are not automatically undone. If the lambda has already written to a result list or sent an external request, `forEach` provides no transactional mechanism to roll back to the initial state.

`Consumer` and `BiConsumer` do not declare arbitrary checked exceptions in their functional method signatures. If an action requires I/O that throws checked exceptions, you must decide how to handle them, wrap them into an appropriate type, or use a loop or method with a clear error contract. Switching to a lambda does not eliminate the responsibility of error handling.

## 5. Complete Program on Lambdas and Execution Flow

Save as **ForEachLambdaDemo.java**. The APIs used are compatible with Java 17 and later:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

public class ForEachLambdaDemo {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>(List.of("An", "Binh", "Chi"));

        List<String> uppercase = new ArrayList<>();
        names.forEach(name -> uppercase.add(name.toUpperCase(Locale.ROOT)));
        System.out.println("Source: " + names);
        System.out.println("Separate result: " + uppercase);

        names.forEach(name -> {
            name = name.toUpperCase(Locale.ROOT);
        });
        System.out.println("After parameter assignment: " + names);

        List<String> accepted = new ArrayList<>();
        names.forEach(name -> {
            if (name.length() == 2) {
                return;
            }
            accepted.add(name);
        });
        System.out.println("After lambda return: " + accepted);

        Map<String, Integer> levels = new LinkedHashMap<>();
        levels.put("An", 1);
        levels.put("Binh", 2);
        List<String> rows = new ArrayList<>();
        levels.forEach((name, level) -> rows.add(name + "=" + level));
        System.out.println("Map rows: " + rows);

        List<String> processed = new ArrayList<>();
        try {
            names.forEach(name -> {
                if (name.equals("Binh")) {
                    throw new IllegalArgumentException("stop");
                }
                processed.add(name);
            });
        } catch (IllegalArgumentException ex) {
            System.out.println("Failure: " + ex.getMessage());
        }
        System.out.println("Processed before failure: " + processed);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 ForEachLambdaDemo.java
java ForEachLambdaDemo
```

Stdout:

```text
Source: [An, Binh, Chi]
Separate result: [AN, BINH, CHI]
After parameter assignment: [An, Binh, Chi]
After lambda return: [Binh, Chi]
Map rows: [An=1, Binh=2]
Failure: stop
Processed before failure: [An]
```

### 5.1. Producing a Separate Result Does Not Modify the Source

The `uppercase` list is independent of `names`. The lambda only adds to another destination, so the source remains `[An, Binh, Chi]`.

This is a sequential case where the lists are not accessed by other threads in the program. Do not infer that this same result-writing style remains safe when switched directly to `parallelStream`.

### 5.2. Parameter Assignment and return

The assignment `name = ...` does not change the list contents, as shown by the `After parameter assignment` output line.

`return` skips `An`, while `Binh` and `Chi` are still added to `accepted`. It ends the processing of the current name, not the entire `forEach`.

### 5.3. Map and Mid-Traversal Failure

The `LinkedHashMap` in the example traverses in insertion order, so `rows` contains the two strings in that exact printed order.

In the final pass, `An` is added to `processed`; when reaching `Binh`, an exception is thrown before adding. `Chi` is not processed further. After catching the exception, `processed` still contains `An`: the side effects prior to the failure are not rolled back.

## 6. Modifying the Source Inside the Action: Critical Limits

The `Iterable.forEach` contract makes no general guarantee if the action performs side effects that modify the underlying source of elements, unless an overriding class specifies its own concurrent modification policy. See the [Iterable.forEach API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Iterable.html#forEach(java.util.function.Consumer)).

Pattern to avoid with an ordinary `ArrayList`:

```java
// Illustrates modifying the very source currently being traversed.
numbers.forEach(number -> {
    if (number % 2 == 0) {
        numbers.remove(number);
    }
});
```

The source is `numbers`, and the action removes from `numbers`. This is not `Iterator.remove` on an explicitly controlled iterator.

Adding elements to the source itself has similar problems:

```java
// Do not use expecting newly added elements to be reliably traversed in the same pass.
numbers.forEach(number -> numbers.add(number * 10));
```

Do not assume that:

- Every newly added element is guaranteed to be processed.
- The traversal will only see the data present at the start.
- An exception will always be thrown immediately at the modifying call.
- Completing a run without throwing an exception proves the usage is valid.

For standard collections, choose a source modification strategy explicitly supported by the contract rather than relying on the accidental outcome of a single run.

### 6.1. ConcurrentModificationException Is Not Only About Multiple Threads

A single thread modifying a source while traversing it can trigger this exception. The word "Concurrent" here does not prove that two threads are necessarily running.

In `ArrayList`, the mechanism for detecting modifications outside the active iterator helps catch bugs, but it is not guaranteed to detect every invalid behavior. Do not catch this exception as a way to synchronize or control removal. See the [ArrayList API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html).

### 6.2. Not Changing the Size Is Not Necessarily Enough

Replacing a slot with `set`, sorting the source, or altering element order also affects what the traversal reads. Do not infer from "no `add`/`remove`" that "anything is allowed inside `forEach`".

If the goal is replacing each element, use `replaceAll` or an update mechanism with a suitable contract. If sorting is needed, perform it in a separate step under clear usage conditions.

### 6.3. The Source Can Be Modified Indirectly

An action does not have to reference the exact variable name of the source to cause modifications.

Cases to recognize:

- Two variables referencing the same list.
- Modifying a `subList` that shares backing storage with the list being traversed.
- Traversing a map while modifying it through `keySet` or `values`.
- Calling a helper method or callback that modifies the source internally.
- Another thread modifying the source while the action is executing.

Renaming a variable does not create an independent collection.

## 7. Mutating Elements Is Different from Modifying the Container Structure

You may need to mark an object as processed, increment an internal counter on an object, or update its business state.

Those operations do not by themselves add or remove a slot in a list. However, you must still consider the impact of the mutation:

- If the element is also an element of a `HashSet` or a key in a `HashMap`, mutating fields that participate in `equals`/`hashCode` can break lookup semantics.
- If the element or key resides in a sorted tree, mutating fields that determine ordering does not automatically reorganize the tree.
- If multiple elements reference the same object, a single mutation may be visible in multiple places.
- In parallel processing, element objects may become shared mutable state requiring coordination.

Therefore, do not lump all changes into a single category, nor assume by default that every object mutation inside a lambda is safe.

A list that disallows adding or removing elements does not necessarily contain immutable objects. "Unmodifiable collection" and "deeply immutable data inside" are two different guarantees.

## 8. Choosing Operations by Modification Intent

| Intent | Generally Clearer Approach |
| --- | --- |
| Only perform an action on each element | `forEach` or a loop |
| Remove elements matching a condition | `removeIf` on a supporting source |
| Traverse and remove the element just retrieved | Explicit `Iterator` and `Iterator.remove` if supported |
| Replace each element of a list | `List.replaceAll` |
| Replace the value for each key in a map | `Map.replaceAll` |
| Transform/filter to produce new data | `map`, `filter`, `collect`/`toList`, or a separate sequential result destination |
| Add to the source based on existing data | Accumulate separately, then add after the traversal finishes |
| Traverse a point-in-time snapshot of data | Create a structural copy under appropriate concurrency conditions |

### 8.1. removeIf and replaceAll

`removeIf` explicitly states the condition for removing elements. The predicate returns a `boolean`, and should not itself make further structural modifications to the source being processed. See the [Collection.removeIf API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#removeIf(java.util.function.Predicate)).

`List.replaceAll` uses the value returned by the function to replace each element; this achieves what parameter reassignment inside a `Consumer` does not. The source must support replacement. See the [List.replaceAll API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#replaceAll(java.util.function.UnaryOperator)).

Dedicated operations still have their own preconditions and limits. They are not permission for a lambda to perform arbitrary additional modifications outside the task controlled by the API.

### 8.2. Accumulate Changes and Apply Afterwards

If new elements need to be created based on existing data, add them to a separate `additions` list. Only after the source traversal finishes, call `source.addAll(additions)`.

Newly added elements are not automatically re-processed in the finished pass. If business logic requires processing a queue that continuously generates tasks, design it with a proper queue and termination condition.

### 8.3. Traversing a Structural Copy

In a sequential program, you can create `new ArrayList<>(source)`, traverse that copy, and modify the original source. The traversal then does not walk over the same structure being modified.

Limitations to keep in mind:

- Creating a copy incurs memory and time overhead.
- A copy typically copies references only; it does not deep-clone element objects.
- If the source is being modified concurrently while copying, creating the copy does not automatically become an atomic snapshot operation.
- Removing by value from a source containing equal elements requires clear intent regarding which occurrence is removed.

Do not use a view or an alias variable in place of a copy and expect isolation.

## 9. Complete Program on Intentional Modification Strategies

Save as **SafeTraversalChangesDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class SafeTraversalChangesDemo {
    public static void main(String[] args) {
        List<Integer> numbers =
                new ArrayList<>(List.of(1, 2, 3, 4, 5, 6));
        numbers.removeIf(number -> number % 2 == 0);
        System.out.println("After removeIf: " + numbers);

        List<String> labels = new ArrayList<>(List.of("a", "b", "c"));
        labels.replaceAll(label -> "[" + label + "]");
        System.out.println("After replaceAll: " + labels);

        List<Integer> source = new ArrayList<>(List.of(1, 2, 3));
        List<Integer> additions = new ArrayList<>();
        source.forEach(number -> {
            if (number % 2 != 0) {
                additions.add(number * 10);
            }
        });
        source.addAll(additions);
        System.out.println("After staged additions: " + source);

        List<String> tasks =
                new ArrayList<>(List.of("keep", "done", "later"));
        new ArrayList<>(tasks).forEach(task -> {
            if (task.equals("done")) {
                tasks.remove(task);
            }
        });
        System.out.println("After snapshot traversal: " + tasks);

        List<String> tokens =
                new ArrayList<>(Arrays.asList("A", null, "B", null));
        Iterator<String> iterator = tokens.iterator();
        while (iterator.hasNext()) {
            if (iterator.next() == null) {
                iterator.remove();
            }
        }
        System.out.println("After iterator removal: " + tokens);

        Map<String, Integer> stock = new LinkedHashMap<>();
        stock.put("pen", 0);
        stock.put("book", 3);
        stock.put("bag", 0);
        stock.entrySet().removeIf(entry -> entry.getValue() == 0);
        stock.replaceAll((code, quantity) -> quantity + 1);
        System.out.println("Map after explicit changes: " + stock);

        List<Integer> squares = List.of(1, 2, 3, 4)
                .parallelStream()
                .map(number -> number * number)
                .toList();
        System.out.println("Parallel collected result: " + squares);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 SafeTraversalChangesDemo.java
java SafeTraversalChangesDemo
```

Stdout:

```text
After removeIf: [1, 3, 5]
After replaceAll: [[a], [b], [c]]
After staged additions: [1, 2, 3, 10, 30]
After snapshot traversal: [keep, later]
After iterator removal: [A, B]
Map after explicit changes: {book=4}
Parallel collected result: [1, 4, 9, 16]
```

### Reading the Steps

- `removeIf` controls the removal of even numbers, leaving 1, 3, and 5 in the list.
- `replaceAll` replaces each string with a new bracketed value.
- The action adds to `additions` rather than to the source being traversed, applying the additions once afterwards.
- The `tasks` traversal runs over a separate `ArrayList` copy. Since the string values in this example are unique, removing `"done"` by value has clear semantics.
- An explicit iterator removes `null` elements via `iterator.remove()` itself, not via `forEach`.
- The map removes out-of-stock entries and then increments the remaining values using operations dedicated to each respective goal.
- The parallel stream produces its result via `map(...).toList()`, rather than having multiple threads call `add` concurrently on an external `ArrayList`.

The program uses collections and data that are not concurrently modified by other threads. These examples illustrate distinct strategies, not advice to combine all of them into every processing task.

## 10. Map.forEach Also Requires Limits on Modifying the Source

Removing keys from the map itself inside `map.forEach` is not a portable pattern for a general-purpose map.

If you need to remove mappings based on their value, you can use:

```java
stock.entrySet().removeIf(entry -> entry.getValue() == 0);
```

This snippet assumes the map is modifiable, the `Integer` values are non-null, and the entry view supports removal.

If you need to replace the value for every key:

```java
stock.replaceAll((code, quantity) -> quantity + 1);
```

Assigning `quantity = quantity + 1` inside a `BiConsumer` only changes the local parameter. The lambda passed to `replaceAll` returns the new value so the API can perform the update.

The default methods on `Map` do not automatically provide synchronization or transactional guarantees across the entire pass. Concrete map implementations may have different policies, so consult the specific class documentation when using them concurrently. See the [Map.forEach API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#forEach(java.util.function.BiConsumer)) and [Map.replaceAll](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#replaceAll(java.util.function.BiFunction)).

## 11. Stream.forEach: The Additional Non-Interference Rule

A stream processes a source through a pipeline. Behavioral parameters passed into a pipeline generally must be **non-interfering** with the source and must not depend on state that may change during execution of the stream pipeline.

Pattern to avoid:

```java
// Do not use to remove from the stream's own underlying source.
numbers.stream().forEach(number -> {
    if (number < 0) {
        numbers.remove(number);
    }
});
```

A sequential stream does not make modifying the underlying source valid. Non-interference is part of the stream source processing contract, not merely a matter of avoiding multi-threaded race conditions.

If you want to create a list without negative numbers:

```java
List<Integer> nonNegative = numbers.stream()
        .filter(number -> number >= 0)
        .toList();
```

If you want to remove elements directly from a supporting source, `removeIf` usually describes that intent better.

`Stream.toList()` returns an unmodifiable list; when a modifiable `ArrayList` is needed, choose an appropriate collector such as `Collectors.toCollection(ArrayList::new)`. Choosing the result destination is a separate decision from keeping the source free of interference.

Rules on stream sources, statefulness, and side effects are explained in the [java.util.stream package documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html).

## 12. Parallel forEach and Shared State

Unsafe pattern when using a regular `ArrayList` as a shared destination:

```java
// Do not use as a way to collect parallel results.
List<Integer> result = new ArrayList<>();
numbers.parallelStream().forEach(number ->
        result.add(number * number));
```

Actions may run across multiple threads. The lambda does not automatically synchronize access to `result`. Data loss, race conditions, or exceptions may occur; no fixed stdout should be assumed for this incorrect usage.

Producing new data via reduction/collection is usually much clearer:

```java
List<Integer> result = numbers.parallelStream()
        .map(number -> number * number)
        .toList();
```

The collection API coordinates the combining process, rather than letting parallel actions arbitrarily mutate a shared `ArrayList`.

### Execution Order Differs from Source Order

`Stream.forEach` does not guarantee encounter order when processing in parallel. Having an ordered `List` does not cause parallel actions to automatically complete in that order.

If actions must be performed in the stream's encounter order, consider `forEachOrdered`. However, it does not lift the restrictions on modifying the source, does not automatically make external shared data safe against other concurrent operations, and can reduce parallel performance.

Do not guess ordering guarantees from observing output once. See [Stream.forEach](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#forEach(java.util.function.Consumer)) and [Stream.forEachOrdered](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#forEachOrdered(java.util.function.Consumer)).

## 13. Concurrent Classes Have Specific Policies, Not Arbitrary Exemptions

Some data structures are designed to support modification during traversal. They may use snapshots or weakly consistent traversal mechanisms that reflect changes according to their own specific guarantees.

For example:

- An iterator of `CopyOnWriteArrayList` operates on a snapshot and does not reflect modifications made after the iterator was created.
- `ConcurrentHashMap` provides traversal operations suited for concurrent environments, but a traversal pass is not by default an atomic snapshot of the entire map.

These characteristics must be verified against the contract of the actual class and method. Do not infer from "thread-safe" that "any data-modifying action is automatically correct for business logic", or generalize from a snapshot iterator to every similar API.

Even when a collection permits concurrent modification, the action itself must still be safe with respect to any external state it mutates. Valid concurrent modifications may or may not be fully visible during an ongoing pass, depending on the collection's policy.

See [CopyOnWriteArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html) and [ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html).

### Iterator.forEachRemaining Does Not Authorize Calling remove Inside the Action

Do not use the presence of an `iterator` variable to conclude that `remove` can be called arbitrarily inside a `forEachRemaining` lambda.

The general contract does not guarantee behavior if the action modifies the underlying source, including calling `remove`, unless a specific overriding policy is documented. Nor is there a general guarantee for calling `remove` after `forEachRemaining` completes.

When you need to remove the element just read by an iterator, an explicit `while` loop with `next` and `remove` expresses the proper mechanism. See the [Iterator.forEachRemaining API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html#forEachRemaining(java.util.function.Consumer)).

## 14. Diagnosis and Self-Review

Before writing a `forEach` call, ask:

1. Is this `Iterable.forEach`, `Map.forEach`, `Stream.forEach`, or `Iterator.forEachRemaining`?
2. Does the action only observe, mutate element state, modify the source structure, or write to another structure?
3. Is that "other" structure truly independent, or is it an alias or view of the source?
4. Is early termination or returning an external result needed?
5. Is parameter reassignment being confused with updating an element or mapping?
6. If an action fails mid-way, are the side effects already performed acceptable?
7. If switched to parallel execution, what external state becomes shared?
8. Is the required order the data order or the action completion order?
9. What concurrent modification policy does the concrete collection class document?
10. Would a dedicated operation such as `removeIf`, `replaceAll`, `map`/`filter`, or an explicit loop make the intent clearer?

## 15. Self-Check Exercises

1. In the first program, why does `name = ...` not change the source while `uppercase.add(...)` changes the result list?
2. If `return` is executed on the first element, are subsequent elements still processed?
3. Why can a `ConcurrentModificationException` occur even when a program runs on a single thread?
4. Rewrite the snippet that removes negative numbers inside `forEach` using `removeIf`, and then using an approach that creates a new result; compare their effects on the source.
5. For a list containing the exact same object reference at two positions, does a shallow `ArrayList` copy isolate the object's internal data?
6. Explain why changing `stream()` to `parallelStream()` can make a previously working `ArrayList` result destination unsafe.
7. Describe how to preserve the intent of "processing in priority order" without relying on accidental output order.

`forEach` is useful when the action to perform on each element is straightforward. When the action starts dictating source structure, controlling early termination, or coordinating state across invocations, choose the appropriate API and coordination mechanism for that requirement.
