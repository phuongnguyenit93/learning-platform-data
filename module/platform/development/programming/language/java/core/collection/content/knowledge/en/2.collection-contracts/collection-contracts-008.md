# API Contracts vs. Implementation Details That Can Change Across JDKs

When learning collections, we often read both the Javadoc and the JDK source code. These two sources answer two related but distinct questions:

- **API contract:** what is a program allowed to require, and what can it rely on?
- **Implementation details:** how is a specific library version currently fulfilling that requirement?

Distinguishing between these two layers of information helps you write programs that remain correct when changing implementations, upgrading the JDK, or switching distribution vendors. It also lets you read source code deeply without turning a current observation into a permanent rule of Java.

For example, `ArrayList` guarantees indexed access and describes certain performance characteristics. However, the exact array growth factor is not something an application is entitled to hardcode or rely on. `HashMap` stores mappings by key, but does not guarantee the iteration order that you happen to observe when printing it.

This lesson uses Java 17 as the API baseline for examples. When mentioning version differences, you need to distinguish whether something is a documented change or merely a possibility left open by the contract.

## 1. An API Contract Consists of More Than Method Signatures

A signature like `boolean add(E e)` only tells you how to call the method and its return type. To use it correctly, you also need to know:

| Contract Component | Questions to Check |
| --- | --- |
| Operation semantics | Where is it added, by what rules is it searched, does it mutate data or create a new result? |
| Input preconditions | Does it accept `null`, boundary indices, or this element type? |
| Return value | Is it an element, the previous value, a count, or an indicator of whether a change occurred? |
| Exceptions | When is an input rejected or an operation unsupported? |
| Ordering | Does it preserve insertion order, index order, comparator order, or make no guarantee? |
| Mutability | Can elements be added, removed, or replaced? |
| Relationship to other data | Is it a copy or a view backed by the source? |
| Concurrency | Are there safety, atomicity, or visibility guarantees for changes? |
| Documented performance | Are there complexity guarantees and accompanying assumptions? |

Not every API provides the same level of commitment for each item. If the documentation does not promise a property, a program should not elevate an observation into a promise.

For instance, two runs might both produce the same `HashMap` order; that only proves those two runs produced the same order. It does not create a contract that "a map is always sorted by key."

## 2. Reading the Right Layer of the Contract

### 2.1. Interfaces Define the General Model

`List`, `Set`, `Queue`, and `Map` express different models. A method accepting `List<Integer>` can iterate in list order without needing to know whether elements are stored in an array or linked nodes.

However, `List` has optional modification operations. Just because the declared type has an `add` method does not mean every `List` object passed in supports `add`.

```java
List<String> first = new ArrayList<>();
List<String> second = List.of("A");
```

Both variables have type `List<String>`, but they do not have the same mutability permissions. If a method needs to modify the list it receives, that method's own contract must state the requirement clearly or create a modifiable copy itself.

An interface also does not mandate identical access costs across implementations. A loop calling `get(i)` repeatedly can behave very differently in terms of time complexity on `ArrayList` versus `LinkedList`. [Java 17: List](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html)

### 2.2. Concrete Classes Can Provide Stronger Guarantees

When you intentionally choose `ArrayList`, you may rely on the published properties of that class itself, such as support for standard modification operations and certain performance characteristics.

This does not contradict the advice to declare variables by interface type:

```java
List<String> names = new ArrayList<>();
```

The variable still holds an `ArrayList` object; the declaration type does not erase the object's characteristics. However, when passing the variable across an API boundary that only states "accepts `List`," the receiver should not assume every future caller will pass an `ArrayList`.

If you truly need a specific capability like `ensureCapacity`, you can use the concrete type in the code that owns the data. That is an intentional dependency on a public API, which is different from reading private fields via reflection.

### 2.3. Factory and Creation Methods Have Their Own Contracts

A method returning `List<T>` does not automatically promise a specific concrete class or mutability of the result. You must read the contract of the creation method itself:

| Creation Method | What You Can Rely On |
| --- | --- |
| `new ArrayList<>(source)` | Creates an `ArrayList` containing the source elements in the source's iteration order |
| `Arrays.asList(array)` | Fixed-size list backed by the passed-in array |
| `List.of(...)` | Unmodifiable list with documented input restrictions |
| `List.copyOf(source)` | Unmodifiable list that does not reflect subsequent additions or removals in the source |
| `Collections.unmodifiableList(source)` | View that disallows modification through itself, still backed by the source |

Do not lump all of these together as "an immutable list." A view can change its observable contents if the source is modified; a structurally unmodifiable list also does not automatically freeze the element objects themselves. [Java 17: Arrays.asList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)), [Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List))

## 3. How to Read Javadoc Systematically

When opening the documentation for a class or method, read in this order:

1. Verify the exact Java version.
2. Read the class/interface description first, because general rules may not be repeated on every method.
3. Read the method description, parameters, and return value.
4. Read exceptions, optional conditions, and `null` handling notes.
5. Follow links to inherited methods or related specifications.
6. Distinguish usage explanations from implementation descriptions.
7. Check `Since` if you need to support a minimum Java version.

Javadoc-generated documentation includes parameter, return, exception, and version history sections. Do not just read a method name or an example and skip the applicability conditions. [JDK 17 Javadoc Comment Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/javadoc/doc-comment-spec.html)

### Note Sections Have Different Meanings

In JDK documentation, you may encounter these sections:

- **API Note:** explanation for users, illustrating scenarios or usage guidance.
- **Implementation Requirements:** describes requirements/behavior tied to the documented implementation, such as a default method.
- **Implementation Note:** explains implementation choices or characteristics.

Do not read every paragraph as if it binds every class implementing the interface. For example, `Collection.removeIf` describes a default algorithm based on an iterator. A class overriding `removeIf` does not therefore have to use the exact same loop structure.

Conversely, do not ignore a guarantee just because it discusses performance or structure. If a class's public documentation states a characteristic with a specific scope, that is valid information for choosing the class within that scope. [Java 17: Collection.removeIf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#removeIf(java.util.function.Predicate))

## 4. ArrayList: Public Guarantees vs. What Is Left Open

Java 17 documentation describes `ArrayList` as a resizable-array implementation of the `List` interface. Operations such as `get`, `set`, and `size` run in constant time; adding an element has amortized constant time cost.

At the same time, the documentation states that the details of the growth policy are not specified beyond the fact that adding an element has constant amortized time cost.

| Statement | Assessment |
| --- | --- |
| `get(i)` returns the element at valid index `i` | Can be relied on |
| Appending to the end preserves list order | Can be relied on |
| Capacity is sufficient to hold the current number of elements | Part of the documented model |
| Every time it fills up, the array must grow by an exact fixed ratio | Not an API commitment |
| The backing array is always allocated at the exact observable moment | Should not be inferred from the API without a corresponding guarantee |
| `size()` equals the number of pre-allocated slots | Misunderstands the API meaning |

Example:

```java
ArrayList<String> values = new ArrayList<>(100);
System.out.println(values.size()); // 0
```

The capacity parameter does not create 100 elements. If you need to optimize based on an expected number of elements, use the constructor or `ensureCapacity`; do not extract the array growth formula from source code to infer business data.

You can study the formula currently used by an OpenJDK build to understand copying costs. When taking notes, tie it to the specific source version and keep it in an explanatory role, not as a condition for your program to produce correct results. [Java 17: ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html)

## 5. HashMap: Do Not Turn Observed Order into a Rule

`HashMap` explicitly documents that it makes no guarantees as to the order of the map. An order that happens to look like numerical order, insertion order, or a stable order is still not a requirement for another run.

The following test relies on the wrong assumption:

```java
// Incorrect expectation example, not a guarantee of HashMap.
assert map.keySet().toString().equals("[A, B, C]");
```

If the requirement is only that the mappings are correct, check using map equality or individual entries. If the product needs a report sorted by key, create an explicitly ordered projection:

```java
Map<String, Integer> sorted = new TreeMap<>(map);
System.out.println(sorted);
```

If insertion order must be preserved, consider `LinkedHashMap` according to its contract. Each choice expresses a different requirement; do not use a `HashMap` and hope a specific set of keys will produce the desired order. [Java 17: HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html)

### A Documented Historical Change

The Java SE 8 Collections Enhancements guide describes using balanced trees in hash bins with many colliding keys to improve performance. The documentation also warns that this can change the iteration order of `HashMap`/`HashSet` in certain situations.

This is concrete evidence that an internal change can remain fully compliant with the API while exposing bugs in programs that depended on an unguaranteed behavior. It does not mean every JDK upgrade changes the order, nor does it mean every hash bin is always a tree. [Oracle: Collections Enhancements in Java SE 8](https://docs.oracle.com/javase/8/docs/technotes/guides/collections/changes8.html)

Treeification thresholds, bit-mixing operations, and internal field layouts are useful when studying a specific source build. Do not use them to identify data types or decide access permissions, business logic, or key uniqueness.

## 6. Do Not Infer a Concrete Class from a Returned List Type

A common mistake is observing the runtime class and casting based on that observation:

```java
List<String> result = Stream.of("A", "B")
        .collect(Collectors.toList());

// Not guaranteed by the Collectors.toList contract:
ArrayList<String> assumed = (ArrayList<String>) result;
```

`Collectors.toList()` makes no guarantees on the type, mutability, serializability, or thread-safety of the `List` returned. The fact that one JDK build happens to return a certain class does not make that class a promised type.

If you need a mutable `ArrayList`, request it directly:

```java
ArrayList<String> editable = Stream.of("A", "B")
        .collect(Collectors.toCollection(ArrayList::new));

editable.add("C");
```

If you already have a `List` and just need a modifiable copy, `new ArrayList<>(result)` also expresses the intent clearly. [Java 17: Collectors.toList and toCollection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#toList())

### Stream.toList Is a Different Contract

`stream.toList()` in Java 17 returns an unmodifiable list. Being shorter to write does not make it synonymous with `collect(Collectors.toList())`.

```java
List<String> fixed = Stream.of("A", "B").toList();
fixed.add("C"); // UnsupportedOperationException
```

Even though both names contain "toList," you must read each method's specification. Also, do not rely on internal class names, serializability, or reference identity of the result if the documentation does not guarantee them. [Java 17: Stream.toList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList())

## 7. Unmodifiable Objects: Content vs. Identity

With factories like `List.of`, what matters is usually the content and the unmodifiable contract. Internal class names, whether two calls reuse the same instance, or how classes are split by element count are not requirements a caller should impose.

For example, check content like this:

```java
List<String> actual = List.of("A", "B");
boolean sameContent = actual.equals(List.of("A", "B"));
```

Do not use `actual == anotherList` to check content. Objects documented as value-based are also unsuitable for identity-based synchronization locks.

`List.copyOf(source)` does not promise to always allocate a new object. If the source already meets the requirements, the implementation may avoid unnecessary copying. What is required is that the result satisfies the contract—including not reflecting subsequent structural changes to the source—not that `result != source` must always be true. [Java 17: List factories and copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html)

Also do not infer from "does not reflect additions/removals in the source" that it is a deep copy. If elements are mutable objects, both lists can still reference the same element instances.

## 8. An Example of an Algorithm That Can Change While the Result Must Be Preserved

The `Arrays` documentation explains that algorithm descriptions in the class are considered implementation notes; the algorithm may be replaced as long as the specification is adhered to. For example, sorting an object array must preserve stability when the API specifies it, without requiring one specific sorting algorithm.

Distinguish between two kinds of requirements:

- "Elements that are equal according to the comparator retain their relative original order" is a result property that can be guaranteed.
- "The method must partition the array into chunks of this exact size" is an algorithmic choice, unless the contract explicitly states it.

For collections, reading contracts the same way helps avoid confusing sorting algorithms, array compaction strategies, or search mechanisms with what the caller is guaranteed. [Java 17: Arrays implementation notes](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html)

"Implementation details may change" does not mean the library is free to drop stability or alter the published meaning of a return value. The contract boundary defines what is permitted to be optimized.

## 9. Exceptions and Concurrency Must Also Be Read Within Their Exact Scope

### 9.1. Fail-Fast Is Not a Synchronization Mechanism

Iterators of many standard collections are described as fail-fast. However, throwing `ConcurrentModificationException` is best-effort detection, not a guarantee to detect every unsynchronized modification.

A program must never rely on this reasoning:

```java
// Flawed reasoning:
// If the iterator does not throw an exception, the data was definitely accessed safely.
```

If a JDK version changes when checks occur or optimizes iteration loops, a program that violated data-sharing rules does not become correct merely because it previously ran without error. Design data ownership, locking, or concurrent structures according to your requirements. [Java 17: ArrayList, fail-fast limitations](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html)

### 9.2. An Exception Does Not Promise Arbitrary Timing or Messages

When an API specifies an exception type, you still need to read the conditions under which it is thrown. Do not further assume that:

- Every invalid object is rejected at the exact same step.
- Exception messages always have the exact same text.
- When an operation fails, all prior changes are guaranteed to be rolled back.
- An unmodifiable collection must always accept no-op operations.

For unsupported inputs, the `Collection` documentation even allows certain queries to either throw an exception or return a result under optional conditions. These cases must be read in the specific API, not guessed from the version currently in use. [Java 17: Collection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html)

When writing tests, only assert on error message strings if your own application or a contract under test explicitly commits to that string. For JDK APIs, you should normally check the exception type and the specified state.

## 10. Read Source Code to Understand, Not to Invent Promises

Reading JDK source code is very valuable when you want to know:

- Why an operation takes significant time or allocates a lot of memory.
- How current loops and data structures work.
- Which version introduced a particular optimization.
- Whether a specific bug is related to an implementation change.

Your workflow should keep two separate notes:

| Note Type | Example Wording |
| --- | --- |
| What the application may rely on | "The report needs key-sorted order; use a structure with key ordering." |
| Implementation observation | "In the source build being analyzed, this operation traverses internal structure nodes as follows..." |

For implementation observations, record the vendor/distribution, full version, source tag or commit, and test conditions. Do not use the current `master` branch to definitively explain a program running on an older JDK without cross-checking.

The fact that a field is `private`, a class name is in an internal package, or a constant appears in the source does not make it a supported API. Accessing it via reflection or module-opening flags also does not create a compatibility commitment for that field.

You do not need to eliminate all implementation knowledge from your learning. Just clarify its role: explanatory mechanism, diagnostic data, or measurement result—never present it as a mandatory rule for all JDKs.

## 11. Test Against the Contract Instead of Coincidence

### What You Should Test

- List contents and order as required by the list contract.
- Key/value sets or correct map entries.
- Mutability when your own application method commits to returning a mutable result.
- View or copy behavior according to the chosen creation mechanism.
- Boundary conditions and specified exception types.
- Business invariants before and after the operation.

### Expectations to Drop Unless Explicitly Guaranteed

- Internal class names of factory results.
- `HashMap` or `HashSet` iteration order.
- Private capacity, array resize counts, or treeification thresholds.
- Helper method call counts if the API does not commit to them.
- Exact execution time in milliseconds across all machines.
- That an unsynchronized operation "will definitely throw an exception."

If a product requirement needs something the current API does not promise, change the design: pick a type with the right contract, make an explicit copy, or introduce an application-owned API layer with implemented and tested guarantees.

Do not fix a failing test by accepting any arbitrary result. Determine what is a real requirement and turn it into an explicit guarantee in the design.

## 12. Upgrading the JDK: Distinguish API Availability from Implementation Behavior

A new API that only exists in a higher version is a different issue from an internal algorithm change in an existing API.

Practical steps:

1. Identify the lowest Java version the application supports.
2. Compile with the matching release configuration.
3. Run tests on all supported runtimes.
4. Compare the API documentation of the source and target versions when differences appear.
5. Re-measure flows sensitive to latency, memory, or high load.
6. When a change is detected, check whether the program depended on something unguaranteed.
7. If there are still signs of a contract violation, create a minimal reproduction and check JDK bug fixes/documentation.

The command `javac --release 17` checks your code against the language level and public API corresponding to Java 17. It does not turn a `java` command pointing to another runtime into Java 17.

You can check the tools in use with:

```shell
javac --version
java --version
```

The version output depends on the environment, so there is no fixed stdout to copy as an expectation across all machines.

A test suite passing on one runtime is evidence for that test run, not proof that every unspecified case has become compatible. Conversely, do not assume every difference is an application bug; verify against the contract and input data.

## 13. Complete Java 17 Program

The following program prints results based strictly on API-guaranteed behavior. Save it to `ApiContractDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.LinkedList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class ApiContractDemo {
    private static int total(List<Integer> values) {
        int result = 0;
        for (int value : values) {
            result += value;
        }
        return result;
    }

    public static void main(String[] args) {
        List<Integer> arrayList = new ArrayList<>(List.of(3, 1, 2));
        List<Integer> linkedList = new LinkedList<>(List.of(3, 1, 2));
        System.out.println("array total = " + total(arrayList));
        System.out.println("linked total = " + total(linkedList));
        System.out.println("same list contents = " + arrayList.equals(linkedList));

        List<String> factory = List.of("A", "B");
        try {
            factory.add("C");
        } catch (UnsupportedOperationException expected) {
            System.out.println("List.of is unmodifiable");
        }

        List<String> collected =
                Stream.of("A", "B").collect(Collectors.toList());
        System.out.println("collected contents = " + collected);

        ArrayList<String> editable =
                Stream.of("A", "B")
                      .collect(Collectors.toCollection(ArrayList::new));
        editable.add("C");
        System.out.println("explicit editable list = " + editable);

        List<String> streamList = Stream.of("A", "B").toList();
        try {
            streamList.add("C");
        } catch (UnsupportedOperationException expected) {
            System.out.println("Stream.toList is unmodifiable");
        }

        Map<String, Integer> counts = new HashMap<>();
        counts.put("B", 2);
        counts.put("A", 1);
        System.out.println("explicit sorted keys = " + new TreeMap<>(counts));

        String[] sourceArray = {"A", "B"};
        List<String> fixed = Arrays.asList(sourceArray);
        fixed.set(0, "Z");
        System.out.println("backing array = " + Arrays.toString(sourceArray));
        try {
            fixed.add("C");
        } catch (UnsupportedOperationException expected) {
            System.out.println("Arrays.asList is fixed-size");
        }

        List<String> original = new ArrayList<>(List.of("A"));
        List<String> snapshot = List.copyOf(original);
        original.add("B");
        System.out.println("original = " + original);
        System.out.println("copy contents = " + snapshot);

        ArrayList<String> reserved = new ArrayList<>(100);
        System.out.println("reserved list size = " + reserved.size());
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 ApiContractDemo.java
java ApiContractDemo
```

Stdout:

```text
array total = 6
linked total = 6
same list contents = true
List.of is unmodifiable
collected contents = [A, B]
explicit editable list = [A, B, C]
Stream.toList is unmodifiable
explicit sorted keys = {A=1, B=2}
backing array = [Z, B]
Arrays.asList is fixed-size
original = [A, B]
copy contents = [A]
reserved list size = 0
```

How to read the demonstration:

1. `total` only needs to iterate over a list of integers containing no `null`; both storage implementations yield a total of 6.
2. `List.equals` compares contents and order without requiring the same implementation class.
3. `List.of` and `Stream.toList` reject additions.
4. The `Collectors.toList` result is only read for its contents; the program does not attempt to infer its class or mutability from observation.
5. When a mutable list is needed, the program explicitly requests `ArrayList` using `toCollection`.
6. The hash map is transferred into a `TreeMap` before printing, so the displayed order is grounded in a contract.
7. `Arrays.asList` reflects value changes back to the source array but does not allow resizing.
8. `List.copyOf` does not reflect subsequent additions to the source.
9. An initial capacity of 100 does not make the list size 100.

The program intentionally avoids printing internal class names, reading capacity via reflection, or asserting directly on `HashMap` order.

## 14. Self-Check: Classifying Statements

| Statement | Evaluation |
| --- | --- |
| "`List` is positionally ordered" | Part of the list model contract |
| "Every `List` supports adding elements" | False; there are optional modification operations and unmodifiable lists |
| "`Collectors.toList` always returns an `ArrayList`" | Not guaranteed by the method |
| "`Stream.toList` in Java 17 returns an unmodifiable list" | Can be relied on |
| "`HashMap` is currently printing in ascending order, so it is an ordered map" | Wrong inference from observation |
| "`ArrayList` can change its growth policy while still meeting its published amortized cost" | Fits the boundary between contract and implementation |
| "Changing the sorting algorithm allows dropping the stability promised by the API" | False; optimizations must preserve the specification |
| "Not throwing `ConcurrentModificationException` proves concurrent access is correct" | False; fail-fast is not synchronization |

## 15. Self-Practice

1. An application method must return a list to which the caller can add elements. Should it just call `Collectors.toList()` and rely on the observed class?  
   **Hint:** explicitly request a mutable structure, such as `toCollection(ArrayList::new)` or an `ArrayList` copy.

2. A test fails after a JDK upgrade because `HashMap` key order differs from before. What should you ask first?  
   **Hint:** does the product actually require an order; if so, did the design choose an API that guarantees that order?

3. `List.copyOf(source) == source` is sometimes true. Is that enough to conclude the method failed to produce a contract-compliant result?  
   **Answer:** no. The contract does not require every call to allocate a different object.

4. Reading source code reveals a specific growth factor. How should you document it?  
   **Hint:** tie it to the specific source version and distinguish it from the public performance guarantees.

5. Why do you need both compiling with `--release` and running tests on the target runtime?  
   **Answer:** they verify different aspects; the API level at compile time does not select the runtime that will execute the code.

When using knowledge about collections to make a design decision, trace back whether it comes from a public contract, an implementation note, or a measurement. This classification tells you what can remain stable in your program and what must be re-verified when the environment changes.