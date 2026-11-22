# Stream.toList, collect, and the Limits of Mutability Guarantees

## 1. Same List Type, Different Mutability Contracts

A stream pipeline can produce a `List` to be read downstream, appended to, sorted, or returned from an API. Choosing a terminal operation is not merely choosing a shorter syntax; it is also choosing the contract of the resulting object.

For example, the following two snippets both have variables of type `List<String>`:

```java
// Illustrative snippet; source is an existing List<String>.
List<String> first = source.stream().toList();
List<String> second = source.stream().collect(Collectors.toList());
```

From the type `List<String>` alone, you cannot conclude that both support calling `add`, `remove`, or `set`. Mutating operations in the `List` interface are optional capabilities that may not be supported by a specific implementation.

We need to separate three questions:

1. **Does the list allow mutation through its API?** Can you add, remove, replace elements, or sort it in place?
2. **Does the list directly share the backing structure of the source?** If the source changes after collection finishes, does the result update along with it?
3. **Are the element objects themselves mutable?** A list that forbids replacing elements does not necessarily prevent modifying a field inside an element.

This lesson focuses on those guarantees when using `Stream.toList()`, `collect`, and list-producing collectors. The programs target Java 17, are saved under the exact `public class` names, and include compile commands and stdout for self-verification.

## 2. Read the Contract Before Choosing a Collection Method

| How the Result Is Created | Mutability Guarantee | Implementation Type | Ordering |
| --- | --- | --- | --- |
| `stream.toList()` | Unmodifiable list; mutating method calls throw `UnsupportedOperationException` | Not guaranteed to be any specific class | Preserves encounter order if the stream is ordered |
| `stream.collect(Collectors.toList())` | No guarantee of mutability | Not guaranteed to be `ArrayList` | Collects in encounter order |
| `stream.collect(Collectors.toCollection(ArrayList::new))` | Mutable according to the `ArrayList` contract | Explicitly requests `ArrayList` | Collects in encounter order |
| `stream.collect(Collectors.toUnmodifiableList())` | Unmodifiable list | Does not commit to a specific class to depend on | Collects in encounter order |
| `collect` combined with `collectingAndThen` | Determined by both the collection step and the finisher step | Determined by how it is created and finished | Depends on the collector used |

### Stream.toList Commits to Unmodifiability

`Stream.toList()` returns an unmodifiable list. This includes replacing elements via `set`, not just size-changing operations like `add` or `remove`. The method has been available since Java 16. [Javadoc Stream.toList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList())

If you need to change the order, you can sort inside the pipeline with `sorted` and then collect. If you need to continue modifying the list after collection, explicitly choose a mutable result.

### Collectors.toList Does Not Commit to Mutability

`Collectors.toList()` provides no guarantees on the type, mutability, serializability, or thread-safety of the returned `List`. Therefore, "calling `add` happens to work on this JDK version" is not a contract for application code. [Javadoc Collectors.toList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#toList())

Do not replace what is unspecified with the opposite claim either. This collector also does not promise that the result is always unmodifiable. The right conclusion is: if your algorithm requires either policy, request that policy explicitly.

### If You Need Mutation, Request a Suitable Container

`Collectors.toCollection(ArrayList::new)` directly states that the result must be an `ArrayList`. This class supports adding, removing, replacing elements, and sorting. You do not have to guess what internal class another collector happens to use.

You can also create a mutable copy from an existing list:

```java
// Illustrative snippet; result is an already-collected List<String>.
List<String> editable = new ArrayList<>(result);
```

This copy is structurally independent of `result`, but it can still share element object references. Section 5 will verify that boundary.

## 3. Experiment: Same Data, Different Mutability

Save as `StreamListGuaranteesDemo.java`.

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Collectors;

public class StreamListGuaranteesDemo {
    private static void expectBlocked(String name, Runnable action) {
        try {
            action.run();
            throw new IllegalStateException("Expected rejection: " + name);
        } catch (UnsupportedOperationException e) {
            System.out.println(name + "=UnsupportedOperationException");
        }
    }

    public static void main(String[] args) {
        List<String> source = List.of("B", "A", "B");
        List<String> direct = source.stream().toList();
        List<String> unspecified = source.stream().collect(Collectors.toList());
        ArrayList<String> mutable = source.stream()
                .collect(Collectors.toCollection(ArrayList::new));
        List<String> unmodifiable = source.stream()
                .collect(Collectors.toUnmodifiableList());

        System.out.println("direct=" + direct);
        System.out.println("collector=" + unspecified);
        System.out.println("explicitArrayList=" + mutable);
        System.out.println("unmodifiableCollector=" + unmodifiable);
        expectBlocked("directAdd", () -> direct.add("C"));
        expectBlocked("directSet", () -> direct.set(0, "X"));
        expectBlocked("directRemove", () -> direct.remove("B"));
        expectBlocked("directSort", () -> direct.sort(Comparator.naturalOrder()));
        expectBlocked("unmodifiableAdd", () -> unmodifiable.add("C"));

        mutable.sort(Comparator.naturalOrder());
        mutable.set(0, "A*");
        mutable.remove("B");
        mutable.add("C");
        System.out.println("mutableAfterEdits=" + mutable);
        System.out.println("source=" + source);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 StreamListGuaranteesDemo.java
java StreamListGuaranteesDemo
```

Stdout:

```text
direct=[B, A, B]
collector=[B, A, B]
explicitArrayList=[B, A, B]
unmodifiableCollector=[B, A, B]
directAdd=UnsupportedOperationException
directSet=UnsupportedOperationException
directRemove=UnsupportedOperationException
directSort=UnsupportedOperationException
unmodifiableAdd=UnsupportedOperationException
mutableAfterEdits=[A*, B, C]
source=[B, A, B]
```

All four initial results contain `[B, A, B]`. Both order and duplicate elements are preserved; collecting into a list does not deduplicate.

The error lines are printed intentionally:

- `directAdd` tests adding an element.
- `directSet` tests replacing an element at an index, even though that operation does not change the size.
- `directRemove` tests removal.
- `directSort` tests in-place sorting.
- `unmodifiableAdd` tests the list from `Collectors.toUnmodifiableList()`.

All corresponding mutating calls are blocked. The program catches `UnsupportedOperationException` and prints a fixed label, so stdout does not depend on the exception message text of a particular JDK version.

The `unspecified` variable created by `Collectors.toList()` is only read and printed. The example does not treat a mutating call succeeding on one implementation as a guarantee of mutability.

In contrast, `mutable` is created with `ArrayList::new`, so the program intentionally relies on the `ArrayList` contract: sorting, replacing the first value, removing one `"B"`, adding `"C"`, and ending up with `[A*, B, C]`. The source remains `[B, A, B]`.

### final and List Do Not Determine Runtime Mutability

The `final` keyword on a reference variable only prevents reassigning the variable to a different object. It does not turn an `ArrayList` into an unmodifiable list.

Conversely, removing `final` from a variable holding the result of `toList()` does not make that result support `add`. Mutability belongs to the contract of the list object, not the reassignability of the variable.

### Sorting Before or After Must Be Chosen Explicitly

If you need a sorted result that is read-only afterward, you can use this illustrative snippet:

```java
// source is a List<String> with no null elements.
List<String> sortedResult = source.stream().sorted().toList();
```

If you want to continue modifying the collected list, use an `ArrayList` result and then call `sort`. Do not collect with `toList()` and assume `sort` will work.

## 4. Mutability and Null Policy Are Two Separate Choices

Two lists both being unmodifiable does not mean they accept the same kind of input data.

`Stream.toList()` can contain `null` elements. Meanwhile, `Collectors.toUnmodifiableList()` rejects `null` and throws `NullPointerException` if it encounters one. Therefore, these two forms cannot be substituted for each other based solely on the word "unmodifiable." [Javadoc Collectors.toUnmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#toUnmodifiableList())

| Requirement | Appropriate Expression |
| --- | --- |
| Unmodifiable list that preserves null elements | `stream.toList()` |
| Unmodifiable list that rejects null | `collect(Collectors.toUnmodifiableList())` |
| Mutable ArrayList that can contain null | `collect(Collectors.toCollection(ArrayList::new))` |
| Wrap a private ArrayList result into an unmodifiable list, preserving null | `collectingAndThen(toCollection(ArrayList::new), Collections::unmodifiableList)` |

The last option is more verbose, but it demonstrates that a collector can accumulate into a mutable container and then return an unmodifiable object in the finisher step.

Save as `StreamListNullPolicyDemo.java`.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.stream.Collectors;

public class StreamListNullPolicyDemo {
    public static void main(String[] args) {
        List<String> source = Arrays.asList("A", null, "B");
        List<String> direct = source.stream().toList();
        ArrayList<String> mutable = source.stream()
                .collect(Collectors.toCollection(ArrayList::new));
        List<String> wrapped = source.stream().collect(Collectors.collectingAndThen(
                Collectors.toCollection(ArrayList::new),
                Collections::unmodifiableList));

        System.out.println("direct=" + direct);
        System.out.println("mutable=" + mutable);
        System.out.println("wrapped=" + wrapped);

        try {
            source.stream().collect(Collectors.toUnmodifiableList());
        } catch (NullPointerException e) {
            System.out.println("unmodifiableCollector=NullPointerException");
        }
        try {
            List.copyOf(direct);
        } catch (NullPointerException e) {
            System.out.println("copyOf=NullPointerException");
        }
        try {
            wrapped.set(0, "X");
        } catch (UnsupportedOperationException e) {
            System.out.println("wrappedSet=UnsupportedOperationException");
        }

        List<String> withoutNull = source.stream()
                .filter(value -> value != null)
                .collect(Collectors.toUnmodifiableList());
        System.out.println("withoutNull=" + withoutNull);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 StreamListNullPolicyDemo.java
java StreamListNullPolicyDemo
```

Stdout:

```text
direct=[A, null, B]
mutable=[A, null, B]
wrapped=[A, null, B]
unmodifiableCollector=NullPointerException
copyOf=NullPointerException
wrappedSet=UnsupportedOperationException
withoutNull=[A, B]
```

The source is created with `Arrays.asList` so that it can hold `null`. If `List.of("A", null, "B")` were used, the error would occur when creating the source, before reaching the collection operation under test.

The output shows:

1. `direct`, `mutable`, and `wrapped` all retain the `null` element.
2. `toUnmodifiableList` rejects that input.
3. `List.copyOf(direct)` also rejects `null`, even though `direct` is already unmodifiable.
4. The `wrapped` wrapper blocks `set`, but forbidding element replacement does not mean existing `null` elements must be removed.
5. The `withoutNull` pipeline explicitly filters out `null` before using the null-rejecting collector.

That final filtering step is a data decision, not a universal trick for avoiding exceptions. If `null` is invalid input that should be reported to the caller, silently removing it can mask a bug. Only filter when the requirements allow dropping those elements.

Also distinguish `null` elements inside the source from the source variable or stream itself being `null`. An element-containment policy never makes a method call on a `null` reference valid.

## 5. An Unmodifiable List Does Not Mean Immutable Elements

When collecting a stream of objects, the resulting list normally holds references to the elements that passed through the pipeline. Without a step that constructs new objects, collection does not automatically deep-copy each element.

Save as `ListResultAndElementsDemo.java`.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ListResultAndElementsDemo {
    static final class Task {
        private String label;

        Task(String label) {
            this.label = label;
        }
    }

    record TaskView(String label) {}

    public static void main(String[] args) {
        Task first = new Task("draft");
        List<Task> source = new ArrayList<>(List.of(first));
        List<Task> liveView = Collections.unmodifiableList(source);
        List<Task> result = source.stream().toList();
        List<TaskView> projected = source.stream()
                .map(task -> new TaskView(task.label))
                .toList();

        source.add(new Task("later"));
        System.out.println("sourceSizeAfterAdd=" + source.size());
        System.out.println("liveViewSizeAfterAdd=" + liveView.size());
        System.out.println("resultSizeAfterAdd=" + result.size());
        System.out.println("sameElementReference=" + (result.get(0) == first));

        first.label = "done";
        System.out.println("resultElementLabel=" + result.get(0).label);
        System.out.println("projectedLabel=" + projected.get(0).label());

        source.clear();
        System.out.println("liveViewSizeAfterClear=" + liveView.size());
        System.out.println("resultSizeAfterClear=" + result.size());
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 ListResultAndElementsDemo.java
java ListResultAndElementsDemo
```

Stdout:

```text
sourceSizeAfterAdd=2
liveViewSizeAfterAdd=2
resultSizeAfterAdd=1
sameElementReference=true
resultElementLabel=done
projectedLabel=draft
liveViewSizeAfterClear=0
resultSizeAfterClear=1
```

The program creates three views over the source data:

| Variable | How It Is Created | Behavior in the Example |
| --- | --- | --- |
| `liveView` | `Collections.unmodifiableList(source)` | Unmodifiable through the wrapper, but reads the source structure directly |
| `result` | `source.stream().toList()` | Collected result list holding `Task` references |
| `projected` | `map` to `TaskView`, then `toList` | Holds data-representation objects created during the transformation step |

After `source.add(...)`, both the source and `liveView` have two elements, while `result` still has one. After `source.clear()`, `liveView` is empty, whereas `result` still holds the collected element.

`Collections.unmodifiableList` is a read-only view of the backing list. It does not copy the source structure; changes to the backing list through another reference are still reflected when reading the view. [Javadoc Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List))

### Independent Structure, Shared Objects

The line `sameElementReference=true` shows that `result.get(0)` is the exact same object as `first`. Changing `first.label` to `"done"` makes the value read through `result` become `"done"` as well.

No `result.set(...)` call occurred during that change. The list did not have an element replaced; the object referenced by that element changed its internal state.

Therefore, "an unmodifiable result" must be understood with the right scope: blocking list-mutating operations does not mean blocking every change visible through its elements.

### To Get a Data Snapshot, Choose the Element Representation

`projected` holds `TaskView` instances created while the label was still `"draft"`. In this example, the field of `TaskView` is an immutable `String`, so mutating `Task.label` afterward does not change `projectedLabel`.

This is one way to decouple the output data model from the source objects. Do not assume every `record` is deeply immutable: if a record contains a field referencing a mutable list or object, you still must design protection for that data.

Similarly, `new ArrayList<>(result)` creates a mutable list without creating new `Task` instances. Copying the container structure and copying element state are two separate tasks.

### Do Not Use "Unmodifiable" to Infer Other Guarantees

An unmodifiable list also does not automatically establish an access-coordination policy for shared element objects. When data is shared across threads of execution, you still need to consider how the data is published and how those objects are read or modified.

`Stream.toList()` itself also makes no commitment to a specific implementation class or serializability. Do not cast the result to an internal class observed in one run to gain extra capabilities.

The result may be a value-based object; compare contents with `equals` when content equality is what you need to check. Do not build protocols around the reference identity of two `toList()` results, and do not use the result itself as a synchronization lock.

## 6. collect Can Accumulate in a Mutable Object Yet Return an Unmodifiable Result

The term "mutable reduction" describes how accumulation works: elements are placed into a container by updating that container. It does not require the final returned object of every collector to support mutation.

There are two common forms:

- `collect(collector)`: the collector encapsulates creating the accumulation container, accepting elements, combining partial results, and finishing the result.
- `collect(supplier, accumulator, combiner)`: directly supplies how to create a container, add one element, and merge two partial results.

With `collectingAndThen`, a finisher function runs after the collection step. That function can return an unmodifiable wrapper. Therefore, seeing the word `collect` in code is not enough to conclude that `add` can be called on the result.

### Parallel Collection Experiment

Save as `ParallelListCollectionDemo.java`.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.stream.Collectors;

public class ParallelListCollectionDemo {
    public static void main(String[] args) {
        List<Integer> source = List.of(1, 2, 3, 4, 5, 6);
        List<Integer> direct = source.parallelStream()
                .map(n -> n * 2)
                .toList();
        ArrayList<Integer> mutable = source.parallelStream()
                .map(n -> n * 2)
                .collect(ArrayList::new, ArrayList::add, ArrayList::addAll);
        List<Integer> wrapped = source.parallelStream()
                .map(n -> n * 2)
                .collect(Collectors.collectingAndThen(
                        Collectors.toCollection(ArrayList::new),
                        Collections::unmodifiableList));

        System.out.println("direct=" + direct);
        System.out.println("mutable=" + mutable);
        System.out.println("wrapped=" + wrapped);
        System.out.println("equalBeforeEdits="
                + (direct.equals(mutable) && direct.equals(wrapped)));

        mutable.add(14);
        System.out.println("mutableAfterAdd=" + mutable);
        System.out.println("directAfterOtherEdit=" + direct);
        try {
            wrapped.add(14);
        } catch (UnsupportedOperationException e) {
            System.out.println("wrappedAdd=UnsupportedOperationException");
        }
        System.out.println("source=" + source);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 ParallelListCollectionDemo.java
java ParallelListCollectionDemo
```

Stdout:

```text
direct=[2, 4, 6, 8, 10, 12]
mutable=[2, 4, 6, 8, 10, 12]
wrapped=[2, 4, 6, 8, 10, 12]
equalBeforeEdits=true
mutableAfterAdd=[2, 4, 6, 8, 10, 12, 14]
directAfterOtherEdit=[2, 4, 6, 8, 10, 12]
wrappedAdd=UnsupportedOperationException
source=[1, 2, 3, 4, 5, 6]
```

All three initial results contain `[2, 4, 6, 8, 10, 12]` in the source's encounter order. Parallel execution does not automatically make the output list lose its order or become mutable.

In the three-argument collection form:

```text
ArrayList::new     creates a new container
ArrayList::add     adds one element to a container
ArrayList::addAll  merges the second partial result into the first
```

The library can create multiple intermediate containers and combine them, rather than having all workers mutate a single external `ArrayList`. The supplier must return a fresh container each time it is called; do not return the same shared list from the supplier. [Javadoc Stream.collect](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#collect(java.util.function.Supplier,java.util.function.BiConsumer,java.util.function.BiConsumer))

In `wrapped`, the collector accumulates into `ArrayList` instances and then the finisher returns a `Collections.unmodifiableList` wrapper. That backing container was created exclusively for the result; the program exposes no other reference to mutate it. Thus, a receiver of `wrapped` cannot add elements through the list API.

`mutable.add(14)` succeeds because the collection explicitly chose `ArrayList`. Modifying `mutable` does not modify `direct` or the source. Calling `wrapped.add(14)` is blocked.

### Do Not Replace collect with External Accumulation

Writing `forEach(output::add)` against an external `ArrayList` `output` does not follow the accumulation and combination protocol of a collector. With a parallel stream, concurrent actions can update an unprotected object at the same time.

If the goal is to produce a list, use a collection operation that expresses the desired output policy. Do not introduce shared mutable state just to end up with a mutable list.

Even when a collector coordinates parallel accumulation safely, the returned `ArrayList` afterward still has the ordinary `ArrayList` contract. It does not become a thread-safe collection for all concurrent access in the rest of the application.

## 7. Changing the Collection Method Can Also Affect Type Inference

When switching from `collect(Collectors.toList())` to `toList()`, in addition to mutability, you must check the data type required by the surrounding code.

`String` is a `CharSequence`, yet Java does not treat `List<String>` as a subtype of `List<CharSequence>`. If the two list types were treated as interchangeable, one side could add another kind of `CharSequence` to a list that another side believes contains only `String`. [Java Language Specification on Subtyping](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.10.2)

The generic `collect` call can infer the collector's type argument from the target type context. In contrast, `toList()` returns `List<T>` based on the current stream's element type.

Save the following valid program as `ListCollectionTypeDemo.java`.

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class ListCollectionTypeDemo {
    public static void main(String[] args) {
        List<CharSequence> collected =
                Stream.of("A", "B").collect(Collectors.toList());
        List<CharSequence> widened =
                Stream.<CharSequence>of("A", "B").toList();
        List<? extends CharSequence> readable =
                Stream.of("A", "B").toList();

        System.out.println("collected=" + collected);
        System.out.println("widened=" + widened);
        System.out.println("readable=" + readable);
        System.out.println("firstLength=" + readable.get(0).length());
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 ListCollectionTypeDemo.java
java ListCollectionTypeDemo
```

Stdout:

```text
collected=[A, B]
widened=[A, B]
readable=[A, B]
firstLength=1
```

There are three different choices in the example:

- `collected` relies on type inference at the `collect` call.
- `widened` specifies at stream creation that the elements have type `CharSequence`.
- `readable` uses a wildcard type to read elements of some subtype of `CharSequence`.

They may print the same contents, but the reason these assignments are valid belongs to the type system, not runtime mutability.

### A Mechanical Replacement May Fail to Compile

Save the following **intentionally ill-typed** example separately as `IncompatibleToListAssignment.java`. This is a compile-error experiment, not a program expected to run:

```java
import java.util.List;
import java.util.stream.Stream;

public class IncompatibleToListAssignment {
    public static void main(String[] args) {
        List<CharSequence> result = Stream.of("A", "B").toList();
    }
}
```

Verify the error with:

```shell
javac --release 17 -encoding UTF-8 IncompatibleToListAssignment.java
```

Compilation fails. The diagnostic message identifies the cause as:

```text
List<String> cannot be converted to List<CharSequence>
```

This is an excerpt of the cause from the compiler diagnostic, not program stdout. There is no `java` execution step for this intentionally invalid file.

The right fix in that situation is to specify the needed stream type, such as `Stream.<CharSequence>of(...)`, or choose a receiving variable type that matches how it is used. Do not fix it with an unchecked cast or by switching to a raw type to hide the error.

### Wildcards Are Not a Mechanism for Making a List Read-Only

`List<? extends CharSequence>` restricts putting values in at the type-checking level; it is not a promise that all list-mutating operations are forbidden. Some operations such as removal are still type-valid to call.

In the program, `readable` is unmodifiable at runtime because the actual object was created by `toList()`, not because `? extends` alone creates that property.

If an API must guarantee an unmodifiable result, it must construct and document the result according to that contract. Do not use a wildcard type as a substitute for that promise.

## 8. Choose How to Create the Result Based on What Comes Next

### Need to Read a Result List

If you only need to iterate over the result or return an unmodifiable list from an API, `toList()` usually expresses that intent directly. It preserves encounter order when present and retains duplicate occurrences.

However, check whether the data contains mutable objects. If you want a stable data result, choose an appropriate output element representation rather than merely blocking list operations.

### Need to Add, Remove, Replace, or Sort Afterward

Explicitly request an `ArrayList` with `toCollection(ArrayList::new)`, or construct `new ArrayList<>(result)` when you already have a result list.

This choice makes the contract clear to both the writer and reader of the code. You do not have to depend on the implicit implementation class of `Collectors.toList()`, and you do not have to attempt a mutation and catch an exception to probe the policy at runtime.

If you create a copy, name it to reflect the copy's role in the subsequent work. Copying should have a purpose; do not add an extra copy merely to obtain an internal class that the program does not actually need.

### Need an Unmodifiable Result That Rejects Null

`Collectors.toUnmodifiableList()` expresses both requirements. If the input can contain `null`, the decision to fail, substitute a valid value, or drop it must come from the business contract.

Do not switch to `toList()` just to make a `NullPointerException` go away if rejecting `null` was actually a valid requirement of the API.

### Need a Custom Finishing Step

`collectingAndThen` lets you collect and then transform the result once at the end, such as wrapping a private backing list in an unmodifiable wrapper. Final mutability depends on both steps, not just the intermediate accumulator. [Javadoc collectingAndThen](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#collectingAndThen(java.util.stream.Collector,java.util.function.Function))

If you use a wrapper, do not expose a mutable reference to the backing list and then call it an immutable snapshot. Moreover, element objects still need their own policy.

### Need an Order Different from Encounter Order

List-creating operations do not automatically sort or deduplicate. If you want sorting, use a sorting step; if you want deduplication, state the deduplication rule explicitly.

If the source has no guaranteed encounter order, creating a `List` does not invent a stable business order for those values. To get a deterministic order, specify the appropriate criterion.

Output ordering and mutability are two independent decisions. A sorted list can be mutable or unmodifiable depending on how it is collected.

### Check the Java Version When Migrating Code

| API | Available Since Java |
| --- | --- |
| `Stream`, `Collectors.toList()`, and `Collectors.toCollection(...)` | 8 |
| `Collectors.toUnmodifiableList()` | 10 |
| `Stream.toList()` | 16 |

The commands in this lesson use `--release 17`, so all of them fall within Java 17's supported scope. If a project must compile on Java 8 or 11, you cannot simply switch to `Stream.toList()` and expect to preserve that compatibility.

A code migration must check every place the result is used: mutating operations, `null` policy, target types, and Java version. Comparing two list-creation lines without reading the operations that follow can miss behavioral changes.

## 9. Conclusions to Avoid

| Misconception | Accurate Understanding |
| --- | --- |
| If a result has type `List`, calling `add` must work | The interface does not guarantee that every implementation supports mutation |
| `collect(Collectors.toList())` always returns a mutable `ArrayList` | The implementation type and mutability are not guaranteed by the API |
| `toList()` only forbids size changes | Mutating operations like `set` and `sort` are also blocked |
| Every collection using `collect` produces a mutable result | The finisher step can return an unmodifiable result |
| Any two unmodifiable results share the same null policy | `toList` and `toUnmodifiableList` differ on this point |
| An unmodifiable list is a deep copy | Element objects can still be shared |
| An `unmodifiable` wrapper never changes when the source changes | The view reads the backing list and can reflect changes made through another path |
| Creating an `ArrayList` from a result copies each object | It copies the structure holding the references, not a deep copy |
| `final List` makes the list immutable | `final` controls reassigning the reference variable |
| A parallel stream returns a mutable or unordered result | Those properties are still determined by the specific operations and collector |
| If a collector uses an intermediate `ArrayList`, the result is always mutable | The finisher function can wrap or transform the result |
| Switching `collect` to `toList` is just a syntax shortcut | It can change mutability, type compatibility, or version requirements |
| `List<? extends T>` itself guarantees unmodifiability | The wildcard governs type relationships, not a protective wrapper |
| You can synchronize on the identity of a `toList` result | The API does not allow relying on the result's identity in that way |

For an API that returns a list, useful documentation states whether the result is mutable, whether it accepts `null`, what ordering is preserved, and how far element data is protected. Writing only the type `List<T>` does not communicate these conditions.

## 10. Contract Verification Exercises

### Exercise 1: Mutating After Collection

A method creates a result with `source.stream().toList()`, then calls `result.add(extra)`. Is switching to `collect(Collectors.toList())` enough to guarantee the algorithm will always be able to mutate the result?

**Check:**

No. `Collectors.toList()` makes no mutability commitment. If the algorithm needs to add elements, explicitly request an `ArrayList` with `toCollection(ArrayList::new)`, or create an `ArrayList` copy before the mutation phase.

### Exercise 2: Replacing an Element Without Changing Size

The result of `toList()` has three elements. Is calling `set(0, value)` valid because the size remains three?

**Check:**

No. Replacing an element is still a list-mutating operation and is blocked with `UnsupportedOperationException`. "Unmodifiable" is stronger than "fixed-size."

### Exercise 3: Input Containing Null

A pipeline currently uses `toList()` and the data contains a `null` element. Does switching to `collect(Collectors.toUnmodifiableList())` preserve the same behavior just because both are unmodifiable?

**Check:**

No. The second collector rejects `null`. You must decide whether to keep `null` elements, throw an error, or transform the data according to the contract.

### Exercise 4: Source and Element Both Change

Collect a `List<Task>` with `toList()`. After collection finishes, add a new `Task` to the source, then change the label of a `Task` that is already in the result. Do the two changes have the same effect?

**Check:**

No. Adding to the source structure does not add an element to the collected result list. However, mutating the state of a shared `Task` object is visible through the element in the result.

To get an independent data snapshot, construct suitable output elements, such as `TaskView` holding a `String` label as shown in the program.

### Exercise 5: Accumulation Container vs. Final Result

A collector accumulates into an `ArrayList`, and then the finisher step calls `Collections.unmodifiableList`. May the caller add to the returned list knowing it is backed by an `ArrayList` internally?

**Check:**

No. The final result's API blocks mutating operations via the wrapper. Knowing the intermediate container is mutable does not change the contract of the returned object.

If another reference to the backing list is exposed, that mutation path must be evaluated separately; the wrapper does not sever the connection to the backing data.

### Exercise 6: Changing Syntax and Type Errors

An assignment to `List<CharSequence>` compiles with `Stream.of("A", "B").collect(Collectors.toList())`. Changing the end to `toList()` fails to compile. Does Java reject the assignment because the result is unmodifiable?

**Check:**

No. This is an issue of type inference and the relationship between `List<String>` and `List<CharSequence>`. You can specify the stream type as `CharSequence` upfront or choose an appropriate receiving variable type. Mutability is a separate contract.

### Exercise 7: Producing Two Result Variants

From the number list `[3, 1, 3, 2]`, produce:

1. A list sorted in ascending order, keeping duplicates, and unmodifiable.
2. An `ArrayList` sorted in ascending order, keeping duplicates, and allowing `4` to be added after collection.

**Approach check:**

The first variant can use `sorted().toList()`, giving `[1, 2, 3, 3]`. The second variant uses `sorted().collect(Collectors.toCollection(ArrayList::new))`, then adds `4` to get `[1, 2, 3, 3, 4]`.

When verifying, read the source again to confirm it was not sorted in place. Also explain why preserving result order and allowing mutation are two separate decisions.
