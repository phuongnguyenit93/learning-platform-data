# Testing Against Contracts Instead of Implementation Classes

## What Promise Should a Test Protect?

Suppose a function accepts a `List<String>`. Today it is called with an `ArrayList`, and later it switches to a `LinkedList` or a custom list you wrote yourself. If the behavior the function relies on still holds, the test should continue to pass.

A check like "the object must have the exact class `ArrayList`" usually does not protect that need. It locks onto how the object was constructed. By contrast, "an element inserted at index 1 appears at index 1, subsequent elements shift properly, and the size increases by one" describes public behavior.

**Contract testing** verifies what an API promises under its corresponding usage conditions. A contract covers more than just the final data:

- Input conditions and state prior to the call.
- Return values.
- Which data changes and which data is preserved.
- Exceptions thrown in each case.
- Ordering, uniqueness, and equality comparison semantics.
- Mutability through iterators and views.
- `null` policies, optional operations, and domain constraints.
- Concurrency guarantees, if the API actually publishes them.

An **implementation detail** is how a class fulfills that promise: whether it uses an array or linked nodes, internal field names, the number of currently allocated array slots, the capacity growth algorithm, or private helper call paths.

Changing those details can be valid as long as the external contract still holds. A good test suite makes it possible to refactor the implementation while still catching broken behavior that must be preserved.

## Three Sources of Contracts to Distinguish

| Promise Source | Example | Applicable Test Suite |
| --- | --- | --- |
| Interface | `List.set` returns the previous element; a list iterator traverses in order | Shared test suite for implementations meeting the required capabilities |
| Structural family or capability profile | Fixed-size list; list allowing `null`; read-only iterator | Conditional test suite gated by declared capabilities |
| Class-specific public API | Queue with a specific capacity; view with a specific order; snapshot iterator | Extended test suite dedicated to that specific promise |

Not every characteristic of a concrete class is an internal detail. If a class documents its iteration order or snapshot policy, that is a testable contract. The goal is to identify the source of each expectation, not to ban mentioning class names in every test.

For example, testing an algorithm that accepts a `Set` should not arbitrarily demand insertion order. However, testing an API that promises to preserve insertion order must verify that order. Two different goals lead to two different kinds of checks.

For classes extending `AbstractList` or other skeletal implementations, do not test only the newly overridden methods. Iterators, views, and default methods can open up other behavioral paths. `AbstractList` builds much of its functionality on top of primitive methods; see [AbstractList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractList.html).

## Common Expectations That Accidentally Lock Onto Implementation Details

| Fragile Expectation | Why It Is Not a General Contract | Better Expectation |
| --- | --- | --- |
| Result must satisfy `getClass() == ArrayList.class` | Another implementation can provide the exact same behavior | Check the data and capabilities required by the caller |
| Every `Set` iterates in a fixed order | `Set` does not define a general iteration order | Check membership and uniqueness; add order checks only when the API promises order |
| A priority queue's iterator returns a sorted sequence | Head retrieval order differs from iterator traversal order | Check order through repeated head removals according to the chosen comparator |
| Every `List` supports adding, removing, and replacing | Many mutation operations are optional | Define a capability profile and test each operation accordingly |
| If a list is mutable, its iterator is also mutable | A snapshot iterator may be read-only | Test iterator capabilities separately |
| External modification outside an iterator always immediately throws CME | Depends on policy and check points | Test only documented guarantees; never rely on CME for program correctness |
| An exception must have the exact message string of the running JDK | Exception messages are rarely part of the general contract | Check the exception type and relevant state |
| After adding N elements, internal capacity must be M | Capacity growth is an internal allocation policy | Check contents, size, and promised capabilities |
| An operation must finish under a few milliseconds on every CI run | Affected by machine load and environment | Separate behavioral tests from methodical performance benchmarks |

`HashSet` and `HashMap` do not guarantee a fixed iteration order; seeing the same output repeatedly on your current machine does not create a new contract. See [HashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html) and [HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html).

For `PriorityQueue`, the promise about the priority head element does not turn its iterator into a sorting operation. Tests must choose the right operation to observe that property; see [PriorityQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html).

## Writing Expectations from Preconditions and Postconditions

Consider `set(index, value)` on a list that supports element replacement.

A meaningful test case:

~~~text
Before:
    [A, B, A]
    index = 1
    value = X

After:
    return value = B
    contents = [A, X, A]
    size = 3
~~~

If you check only the final contents, a class that mistakenly returns `X` instead of `B` will still pass. If you check only the return value, a class that does not actually replace the element might also pass.

For removing by value on a list:

~~~text
Before:
    [A, B, A]

remove("A"):
    returns true
    leaves [B, A]
~~~

The contract of removing the first occurrence makes the post-operation order meaningful. Converting the result into the set `{A,B}` loses information about position and multiplicity.

Behaviors regarding index positions, ordering, return values, and list equality are specified in [Java 17 List](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html). A test case should be able to explain which part of that promise it is protecting.

### Exception Tests Also Have Preconditions

To test an out-of-bounds `get`, use a valid list and an invalid index. To test `UnsupportedOperationException` on `set`, use a valid index on a list that does not support replacement.

If you pass an invalid index while simultaneously invoking an unsupported operation, the test may inadvertently demand an exception precedence order that the API does not promise.

Similarly, an iterator that does not support `remove` and an iterator that supports `remove` but has not had `next` called yet are two distinct cases. Do not use a call that violates multiple conditions at once to draw conclusions about an object's capabilities.

## Capability Profiles Must Be Declared Explicitly

A shared test suite does not mean applying the exact same write operations to every object.

A small capability profile can be described as follows:

| Capability | Question to Answer |
| --- | --- |
| Resizable | Does it allow adding/removing through the paths under test? |
| Element replacement | Is `set(index,value)` supported? |
| Iterator removal | Is `Iterator.remove` supported? |
| List iterator replacement | Is `ListIterator.set` supported? |
| `null` policy | What are the rules for initializing, writing, and reading `null`? |
| Views | How do `subList`, `keySet`, `values`, or `entrySet` write through to the backing collection? |
| Concurrency | Does it require external synchronization, use snapshots, or allow concurrent updates? |

Do not use a single "mutable" flag to infer everything. `CopyOnWriteArrayList` allows mutating the list directly, but its iterator does not support `remove/set/add`. That is its published contract, not a bug for a shared test suite to reject. See [CopyOnWriteArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html).

The capability profile must come from the approved API specification, not inferred by trial and error and flipping flags until the tests turn green. If a class is required to support removal and removal is currently broken, flipping the flag to "unsupported" simply erases the original requirement.

Nor is every capability independent along the exact five flags of a single example. A collection that only allows removal through a view, a list that restricts duplicates, or a structure with a restricted element domain may require a different profile. A test suite must establish preconditions suited to its target.

### No-Op Cases Are Insufficient for Probing Capabilities

A collection that does not support addition may accept `addAll` with an empty source without throwing an exception. An operation removing a non-existent value may return `false` even though removing an existing value would be rejected.

Therefore, when testing an unsupported capability, choose inputs that genuinely exercise that write path—such as inserting an element at a valid index or removing an element that is actually present.

When testing a no-op call under a general contract, do not force all implementations to produce the exact same exception outcome. A concrete class may publish a stricter policy and be tested separately. The rules for optional operations and no-op cases are defined in [Collection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html).

## Preparing Test Data and Object Factories

An object creator, commonly called a `factory` in test code, takes input data and constructs the instance under test. A behavioral test suite works through the interface without needing to know whether the internals use an array or linked nodes.

An illustration of the idea:

~~~java
Function<List<String>, List<String>> factory = ArrayList::new;
List<String> actual = factory.apply(List.of("A", "B", "A"));
~~~

This snippet illustrates how to pass a factory; the full `import` statements and complete test suite appear in the program below.

Test data should be chosen with clear purpose:

- An empty collection tests the zero-element boundary.
- A single element tests removing the last element and transitioning to empty.
- `[A,B,A]` tests ordering together with two equal occurrences.
- `null` is included only for profiles that allow it or in explicit rejection test cases.
- Elements with colliding hash codes that are not equal are useful when testing hash-based structures.
- Equal objects with distinct identities help detect removing the wrong occurrence.

Each mutating test case should use a fresh object or restore state via a well-defined protocol. One test case should never depend on another test case having run first.

For mutable objects, factory invocations must not accidentally share backing storage that could mutate across instances. For immutable objects, a factory reusing the same instance is not inherently a bug; do not enforce distinct object identity when the contract only promises value semantics.

## Complete Program: One Test Suite, Multiple Implementations

Save this as `CollectionContractDemo.java`. The program requires no external testing libraries. `Verify` uses explicit checks so it does not depend on enabling `-ea` for Java's `assert` statements.

The scope of this test suite covers selected list capability profiles:

- The factory accepts a source list, preserves order and multiplicity, and can construct an empty list.
- Profiles marked `resizable` support the direct add/remove group and range removal via `subList` exercised here.
- `replaceable` refers specifically to `List.set`; replacement and removal via iterators are declared separately.
- The `allowsNull` policy in this example covers initializing with `null`, reading/searching for it, and replacing with `null` if `set` is supported.
- The test suite runs sequentially and does not verify concurrent update policies.

This is a scoped test suite, not a universal certification suite for every possible `List` implementation.

`SlotList` is a custom class holding a fixed number of slots, supporting `get/size/set`, and copying the source into its own array. `WrongReturnList` deliberately returns the new element from `set` to test the quality of the test suite itself. Do not use deliberately broken classes as production implementations.

~~~java
import java.util.AbstractList;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Iterator;
import java.util.LinkedList;
import java.util.List;
import java.util.ListIterator;
import java.util.NoSuchElementException;
import java.util.Objects;
import java.util.Random;
import java.util.function.Function;
import java.util.concurrent.CopyOnWriteArrayList;

public class CollectionContractDemo {
    record Spec(
            String name,
            Function<List<String>, List<String>> factory,
            boolean resizable,
            boolean replaceable,
            boolean iteratorRemovable,
            boolean iteratorReplaceable,
            boolean allowsNull) {
        List<String> fresh(String... values) {
            return factory.apply(Arrays.asList(values));
        }
    }

    static class SlotList extends AbstractList<String> {
        private final String[] data;

        SlotList(List<String> source) {
            data = source.toArray(String[]::new);
        }

        @Override public int size() {
            return data.length;
        }

        @Override public String get(int index) {
            return data[Objects.checkIndex(index, data.length)];
        }

        @Override public String set(int index, String value) {
            Objects.checkIndex(index, data.length);
            String old = data[index];
            data[index] = value;
            return old;
        }
    }

    static final class WrongReturnList extends SlotList {
        WrongReturnList(List<String> source) {
            super(source);
        }

        @Override public String set(int index, String value) {
            super.set(index, value);
            return value;
        }
    }

    static final class ContractFailure extends AssertionError {
        ContractFailure(String message) {
            super(message);
        }
    }

    static final class Verify {
        private int checks;

        void check(boolean condition, String message) {
            checks++;
            if (!condition) {
                throw new ContractFailure(message);
            }
        }

        void equal(Object expected, Object actual, String message) {
            check(Objects.equals(expected, actual), message);
        }

        void throwsType(Class<? extends Throwable> type,
                        Runnable operation, String message) {
            checks++;
            try {
                operation.run();
            } catch (Throwable failure) {
                if (type.isInstance(failure)) {
                    return;
                }
                throw new ContractFailure(message + ": wrong exception "
                        + failure.getClass().getSimpleName());
            }
            throw new ContractFailure(message + ": no exception");
        }
    }

    static int contract(Spec spec) {
        Verify v = new Verify();
        List<String> list = spec.fresh("A", "B", "A");
        List<String> expected = List.of("A", "B", "A");
        v.equal(3, list.size(), "seed size");
        v.check(!list.isEmpty(), "seed must be nonempty");
        v.equal(expected, list, "list order and multiplicity");
        v.check(list.equals(expected) && expected.equals(list), "symmetric equality");
        v.equal(expected.hashCode(), list.hashCode(), "equal lists need equal hashes");
        v.equal("B", list.get(1), "indexed read");
        v.equal(0, list.indexOf("A"), "first equal occurrence");
        v.equal(2, list.lastIndexOf("A"), "last equal occurrence");
        v.check(list.contains("A") && !list.contains("missing"), "membership");
        v.throwsType(IndexOutOfBoundsException.class,
                () -> list.get(-1), "negative read index");
        v.throwsType(IndexOutOfBoundsException.class,
                () -> list.get(list.size()), "read index at size");

        Object[] array = list.toArray();
        v.equal(3, array.length, "array length");
        array[0] = "outside";
        v.equal("A", list.get(0), "array must not write through");
        String[] typed = list.toArray(String[]::new);
        v.check(Arrays.equals(new String[]{"A", "B", "A"}, typed), "typed array contents");

        Iterator<String> iterator = list.iterator();
        v.check(iterator.hasNext() && iterator.hasNext(), "hasNext must not consume");
        v.equal("A", iterator.next(), "first iterator value");
        v.equal("B", iterator.next(), "next without hasNext");
        v.equal("A", iterator.next(), "last iterator value");
        v.check(!iterator.hasNext(), "iterator exhausted");
        v.throwsType(NoSuchElementException.class, iterator::next, "next past end");

        List<String> empty = spec.fresh();
        v.check(empty.isEmpty() && empty.size() == 0, "empty construction");
        v.check(!empty.iterator().hasNext(), "empty iterator");
        v.throwsType(NoSuchElementException.class,
                empty.iterator()::next, "next on empty");

        List<String> forSet = spec.fresh("A", "B", "A");
        if (spec.replaceable()) {
            v.equal("B", forSet.set(1, "X"), "set must return previous value");
            v.equal(List.of("A", "X", "A"), forSet, "set must replace one position");
        } else {
            v.throwsType(UnsupportedOperationException.class,
                    () -> forSet.set(1, "X"), "replacement unsupported");
            v.equal(expected, forSet, "rejected replacement must not change list");
        }
        ListIterator<String> listIterator = forSet.listIterator();
        listIterator.next();
        if (spec.iteratorReplaceable()) {
            listIterator.set("Z");
            v.equal(List.of("Z", "X", "A"), forSet, "list iterator set");
        } else {
            v.throwsType(UnsupportedOperationException.class,
                    () -> listIterator.set("Z"), "iterator replacement unsupported");
        }

        List<String> forResize = spec.fresh("A", "B", "A");
        if (spec.resizable()) {
            forResize.add(1, "X");
            v.equal(List.of("A", "X", "B", "A"), forResize, "indexed insertion");
            v.check(forResize.add("Y"), "append reports a change");
            v.equal("B", forResize.remove(2), "indexed removal returns removed value");
            v.check(forResize.remove("A"), "remove present value");
            v.equal(List.of("X", "A", "Y"), forResize, "remove first equal occurrence");
            v.check(!forResize.remove("missing"), "missing removal reports false");

            List<String> byView = spec.fresh("A", "B", "A");
            byView.subList(1, 3).clear();
            v.equal(List.of("A"), byView, "subList removal writes through");
            forResize.clear();
            v.check(forResize.isEmpty(), "clear removes all values");
        } else {
            v.throwsType(UnsupportedOperationException.class,
                    () -> forResize.add(0, "X"), "insertion unsupported");
            v.throwsType(UnsupportedOperationException.class,
                    () -> forResize.remove(0), "indexed removal unsupported");
            v.throwsType(UnsupportedOperationException.class,
                    () -> forResize.remove("A"), "value removal unsupported");
            v.equal(expected, forResize, "rejected resize must preserve values");
        }


        List<String> byIterator = spec.fresh("A", "B", "A");
        Iterator<String> removing = byIterator.iterator();
        if (spec.iteratorRemovable()) {
            v.throwsType(IllegalStateException.class,
                    removing::remove, "remove before next");
            removing.next();
            removing.next();
            removing.next();
            removing.remove();
            v.equal(List.of("A", "B"), byIterator, "iterator removes last returned occurrence");
            v.throwsType(IllegalStateException.class,
                    removing::remove, "remove twice");
        } else {
            removing.next();
            v.throwsType(UnsupportedOperationException.class,
                    removing::remove, "iterator removal unsupported");
            v.equal(expected, byIterator, "rejected iterator removal preserves list");
        }

        if (spec.allowsNull()) {
            List<String> nullable = spec.fresh("A", null, "A");
            v.equal(null, nullable.get(1), "null value can be read");
            v.equal(1, nullable.indexOf(null), "null value can be found");
            if (spec.replaceable()) {
                List<String> target = spec.fresh("A");
                v.equal("A", target.set(0, null), "replace with null");
                v.equal(null, target.get(0), "null replacement stored");
            }
        } else {
            v.throwsType(NullPointerException.class,
                    () -> spec.fresh("A", null), "factory rejects null");
        }
        return v.checks;
    }

    static int modelSequence(Spec spec, long seed, int steps) {
        Verify v = new Verify();
        Random random = new Random(seed);
        List<String> actual = spec.fresh();
        List<String> model = new ArrayList<>();
        for (int step = 0; step < steps; step++) {
            int action = random.nextInt(5);
            String value = "v" + random.nextInt(7);
            if (model.isEmpty() || action == 0) {
                int index = random.nextInt(model.size() + 1);
                model.add(index, value);
                actual.add(index, value);
            } else if (action == 1) {
                int index = random.nextInt(model.size());
                v.equal(model.remove(index), actual.remove(index),
                        "model remove result at step " + step);
            } else if (action == 2) {
                int index = random.nextInt(model.size());
                v.equal(model.set(index, value), actual.set(index, value),
                        "model set result at step " + step);
            } else if (action == 3) {
                v.equal(model.remove(value), actual.remove(value),
                        "model value removal at step " + step);
            } else {
                model.clear();
                actual.clear();
            }
            v.equal(model.size(), actual.size(), "model size at step " + step);
            v.equal(model, actual, "model sequence at step " + step);
        }
        return steps;
    }

    public static void main(String[] args) {
        List<Spec> specs = List.of(
                new Spec("ArrayList", ArrayList::new, true, true, true, true, true),
                new Spec("LinkedList", LinkedList::new, true, true, true, true, true),
                new Spec("CopyOnWriteArrayList", CopyOnWriteArrayList::new,
                        true, true, false, false, true),
                new Spec("array-backed fixed list",
                        source -> Arrays.asList(source.toArray(String[]::new)),
                        false, true, false, true, true),
                new Spec("List.copyOf", List::copyOf, false, false, false, false, false),
                new Spec("SlotList", SlotList::new, false, true, false, true, true)
        );

        for (Spec spec : specs) {
            int checks = contract(spec);
            System.out.println(spec.name() + " = PASS (" + checks + " checks)");
        }
        for (Spec spec : specs) {
            if (spec.resizable() && spec.replaceable()) {
                int steps = modelSequence(spec, 2026L, 200);
                System.out.println(spec.name() + " model = PASS (" + steps + " steps)");
            }
        }

        Spec broken = new Spec("WrongReturnList",
                WrongReturnList::new, false, true, false, true, true);
        try {
            contract(broken);
            throw new AssertionError("Broken implementation was not detected");
        } catch (ContractFailure expected) {
            System.out.println("deliberately broken = DETECTED: " + expected.getMessage());
        }
    }
}
~~~

Compile and run:

~~~shell
javac --release 17 -encoding UTF-8 CollectionContractDemo.java
java CollectionContractDemo
~~~

The code was compiled with `--release 17` and executed on OpenJDK Zulu 24.0.2. Exact stdout:

~~~text
ArrayList = PASS (41 checks)
LinkedList = PASS (41 checks)
CopyOnWriteArrayList = PASS (40 checks)
array-backed fixed list = PASS (36 checks)
List.copyOf = PASS (33 checks)
SlotList = PASS (36 checks)
ArrayList model = PASS (200 steps)
LinkedList model = PASS (200 steps)
CopyOnWriteArrayList model = PASS (200 steps)
deliberately broken = DETECTED: set must return previous value
~~~

## What Did the Test Suite Verify?

### Shared Read Behavior Remains Consistent Across Implementations

The initial cases verify:

- Size and empty/non-empty status.
- Ordering and element multiplicity.
- `get`, `indexOf`, `lastIndexOf`, and `contains`.
- Symmetric `equals` against a list with the same data, along with `hashCode` consistency.
- Negative read indices and indices equal to `size`.
- `toArray` preserving contents and preventing the returned array from writing through to the list.
- Iterator not consuming elements when `hasNext` is called multiple times.
- `next` working without a preceding `hasNext` call and throwing the right exception type when exhausted.

There are no checks for class names, internal field names, or internal array capacity.

`toArray` not writing through is a public data contract, even when an implementation uses an array as its backing store. Conversely, demanding that an internal array have a length equal to twice the element count would lock onto a private allocation policy.

### Replacement Tests Both the Return Value and the Side Effect

For profiles allowing `set`, the test suite verifies both the returned previous value and the updated list contents. It then creates a fresh list iterator and checks replacement via the iterator according to its dedicated flag.

Creating the iterator after the direct mutation ensures the test does not rely on a blanket assumption about whether an already-open iterator will observe external replacements. If you want to test snapshot behavior or live change visibility, that should live in a dedicated test group with an explicitly declared policy.

For profiles that disallow replacement, the operation uses a valid index and a real replacement value. After catching the exception, the test suite verifies that the list contents remain unchanged.

### Resizing Tests Multiple Write Paths

For lists that support resizing, the program tests indexed insertion, appending at the end, indexed removal, removing the first equal occurrence by value, removing a non-existent value, range removal through a `subList` view, and `clear`.

Removal through an iterator is tested separately. The two occurrences of `A` in `[A,B,A]` help distinguish removing the last element returned by the iterator from scanning from the front and mistakenly removing the first equal occurrence.

For fixed-size or read-only lists, the test checks that operations with genuine effects throw `UnsupportedOperationException` while leaving the underlying data unmodified.

`Arrays.asList` returns a fixed-size list backed by the provided array. In the example factory, a fresh array is created from the source on each call, so test cases do not inadvertently share a mutable backing array. See [Arrays.asList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)).

### CopyOnWriteArrayList Demonstrates the Value of Granular Profiles

This configuration passes the direct list mutation tests and the model sequence tests, while the iterator tests confirm that mutating through its iterator is unsupported.

If the test suite used a single `resizable` flag and assumed the iterator must also support removal, it would report a failure on a class that is faithfully following its own documented contract.

This is also why you should not split tests purely by class name and write a completely separate test suite for each class. Shared behavior is reused, while genuine differences are expressed through explicit capability flags.

### A Deliberately Broken Class Tests the Test Suite

`WrongReturnList` updates the data properly but returns the new value instead of the old one. If the test suite observed only list contents, this bug could easily slip through.

The line `deliberately broken = DETECTED: set must return previous value` confirms that the return-value assertion caught the planted defect.

This is a simple mutation-testing experiment: creating a faulty variant to see whether the test suite catches it. It does not prove the test suite catches every possible bug. You can design additional purposeful variants: ignoring tail appends, removing the wrong occurrence, an iterator skipping the last element, or a view mutating a detached copy instead of the backing list.

There is no need to keep deliberately broken classes in production code. The purpose of the experiment is to verify whether every critical promise is guarded by a check that genuinely distinguishes right from wrong.

## Model-Based Testing After Every Step

A structural bug might only surface after a sequence of operations: inserting, replacing, removing, clearing, and inserting again. Short, isolated single-method tests may never produce that sequence.

In `modelSequence`, the program maintains:

- `model`: an `ArrayList` serving as the reference model for ordered data.
- `actual`: the candidate instance under test.
- A pseudo-random number generator initialized with a fixed seed.
- A sequence of indexed insertions, replacements, indexed removals, value removals, and clears.

After every step, the program compares any relevant return value, the size, and the element sequence. It does not wait until the end to compare, because an intermediate bug could be accidentally masked by a later operation.

Indices are generated from the model's current state to produce valid operations. Invalid-index cases belong in their own dedicated test group. Separating the two makes it clear whether a failure stems from state transitions or precondition checks.

### A Fixed Seed Makes Failures Reproducible

The seed `2026L` together with the same sequence of `Random` calls produces the exact same pseudo-random number sequence. This is a documented guarantee of `java.util.Random`; see [Random](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Random.html).

In this program, each eligible profile runs 200 steps with that seed. If you expand the generator, log both the seed and the operation history on failure, because changing how numbers are drawn or adding a single `nextInt` call will shift the entire downstream sequence.

When a failure occurs, shrink the sequence down to a minimal counterexample:

~~~text
Long failing sequence
    -> strip out irrelevant segments
    -> keep a sequence that still reproduces the failure
    -> identify the precondition and the broken promise
    -> add a short, clearly named regression test
~~~

The diagram above illustrates the failure analysis workflow; the full program does not implement automatic sequence shrinking.

### Reference Models Also Have Limits

Using `ArrayList` as a reference model works well for list profiles that share the same ordering semantics, value domain, and direct mutation capabilities under test. It is not suitable for forcing a set to retain duplicates, or forcing a priority queue to behave as FIFO.

Running `ArrayList` as the candidate against an `ArrayList` reference model mainly verifies the generator setup; it does not provide strong independent proof of every behavior of `ArrayList`. That is why the suite also includes explicit deterministic assertions and custom implementations.

The 200 steps or the check counts printed to stdout describe the experiment that ran, not a complete measure of contract coverage. A single targeted check on a return value can be worth more than thousands of random operations that ignore that return value.

## Comparing Properly by Collection Type

### List: Preserve Order and Multiplicity

For a `List`, `[A,B,A]` is different from `[A,A,B]`. Converting both to sets discards information and can cause a test to miss ordering bugs or missing duplicate removals.

If the test data involves mutable element objects, keep your expected baseline stable. If both the expected model and the actual collection hold references to the same mutated element instance, both may change identically and allow a broken test case to pass.

When what needs protection is the exact object identity of a specific occurrence, check reference equality or a distinguishing identifier field as appropriate. Contract testing does not forbid identity comparisons; it simply requires that identity truly be what the test case intends to observe.

### Set: Check Uniqueness Without Inventing Order

For a set following standard equality semantics:

- Adding a new element modifies the set.
- Adding an object equal to an existing element does not create an additional member.
- Equal elements never appear twice during iteration.
- Two sets containing the same elements must be compatible under `equals/hashCode`, regardless of iteration order.

Do not simply normalize the result via `new HashSet<>(actual)` and conclude that the candidate contains no duplicates. That normalization deduplicates on its own and can hide a buggy set implementation. You must also check the number of iterated elements, the reported `size()`, and the candidate's own uniqueness.

For a bag/multiset collection that allows duplicates without ordering, comparing frequency maps is usually more appropriate than comparing sets. For a `Set` with a documented iteration order, add a dedicated ordering test group. The foundational contract for set uniqueness is defined in [Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html).

### Map: Compare Mappings and Views

For a map without a documented iteration order, its contents are defined by key–value mappings, not by its `toString` formatting.

Useful test cases when mutation is supported:

1. Insert a new key; verify size and associated value.
2. Call `put` on an existing key; verify the returned previous value and confirm the size does not increase.
3. Remove both an existing key and a non-existent key.
4. For maps that permit `null` values, distinguish an absent key from a present key mapped to `null` using `containsKey`.
5. Obtain the map views (`keySet`, `values`, `entrySet`) and verify documented write-through behavior.
6. Test `Entry.setValue` according to supported capabilities, not just `map.put`.

Checking `get(key) == null` is not enough to prove a key is absent in a map that permits `null` values. Similarly, blocking `put` does not automatically prove that all entries and views are read-only.

A reference model map must use the same key-comparison semantics as the map under test. Do not use an `equals`-based reference model to test a structure that explicitly publishes different key equivalence semantics (such as `IdentityHashMap` or a comparator-based `TreeMap`) and treat every difference as a bug. See the mapping and view rules in [Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html).

### Queue: Distinguish Retrieval Order from Iteration Order

`Queue` does not impose a universal FIFO rule across all implementations. Priority queues and other orderings exist; each implementation specifies its own ordering policy.

For a documented FIFO queue, verify that successive removals return elements in insertion order. For a priority queue, verify that the removed head element conforms to the comparator; if the comparator considers two elements equal and the API does not promise tie-breaking stability, do not enforce insertion order between them.

You should also test the paired operation behaviors:

| Scenario | Value-Returning Method | Exception-Throwing Method |
| --- | --- | --- |
| Empty queue, remove head | `poll()` returns `null` | `remove()` throws `NoSuchElementException` |
| Empty queue, inspect head | `peek()` returns `null` | `element()` throws `NoSuchElementException` |
| Bounded queue is full | `offer(e)` returns `false` | `add(e)` throws `IllegalStateException` |

The `null` element policy must be checked per queue specification rather than assuming all queues share the exact same restriction. These distinctions are detailed in [Queue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Queue.html).

## What Not to Put into a Shared Contract Test Suite

### Do Not Assert Specific Outcomes in Undefined Behavior Regions

For example, structurally modifying a list directly while traversing a `subList` view or an active iterator often enters territory where the general contract does not define a single universal outcome. A test should not violate usage preconditions and simultaneously demand a specific final state across every list implementation.

For iterators with a fail-fast policy, you can test single-threaded sequential cases according to the implementation's documentation. However, never treat the absence of a `ConcurrentModificationException` as proof of thread safety, and never rely on CME being thrown as a correctness mechanism in concurrent algorithms. See [ConcurrentModificationException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ConcurrentModificationException.html).

Similarly, do not write a shared contract test demanding that `Iterator.remove` always succeed after `forEachRemaining`. The general contract does not guarantee that behavior. See [Iterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html).

### Do Not Assume Bulk Operations Are Transactional

If `addAll` processes elements one by one and encounters an invalid element midway through, earlier elements may already have been added. If an update callback throws an exception mid-operation, there is no automatic rollback unless specified.

A test suite should demand all-or-nothing atomicity ("either everything succeeds or the collection remains unchanged") only when the API explicitly promises that guarantee. Otherwise, test the documented postconditions and keep strong transactional checks in a class-specific suite.

When deliberately throwing an exception inside a callback, respect only guaranteed traversal orders. Do not assume that a callback over an unordered structure will visit the exact same key first on every run.

### Do Not Assert Internal Call Counts Unless the API Promises Them

A hash-based structure can use hash codes to filter out non-equal candidates without calling `equals` on every element. An algorithm might traverse via an iterator or via indexed lookups. Asserting exact `equals`, `get`, or `iterator` call counts makes tests brittle against valid optimizations.

If call counts carry contractual meaning—for instance, an API promising that a mapping function is invoked at most once when a key is absent—test that specific public guarantee. Do not turn an invocation pattern observed in one JDK version into an interface-wide contract.

## Separating Three Kinds of Evidence

### Behavioral Evidence

Observed exclusively through the public API: return values, stored data, exceptions, views, ordering, and relationships between operations. This is the layer that can be shared most broadly.

### Internal Invariant Evidence

When developing your own data structure, you may want to verify that doubly linked node pointers match in both directions, that array slots beyond `size` are nulled out to avoid memory leaks, or that entry counts across buckets sum to the total size.

These are valuable checks for that specific implementation. Name them accurately and scope them to that implementation; do not force a class backed by a different storage mechanism to expose the same fields or satisfy the same physical invariants.

Migrating an implementation from an array to linked nodes may require rewriting the internal invariant tests while keeping the behavioral contract suite untouched. That is a sign that your testing boundaries are well organized.

### Performance and Concurrency Evidence

If there are performance requirements, use proper benchmarking methodology that accounts for dataset distribution, JVM warm-up, and environmental noise. A tight millisecond assertion inside a functional unit test rarely proves asymptotic complexity or load capacity.

If there are concurrency requirements, test the actual concurrency guarantees. A passing sequential test suite proves nothing about thread safety or atomicity. Use explicit coordination primitives (such as `CountDownLatch` or `CyclicBarrier`) rather than `Thread.sleep` to orchestrate thread interleavings, and verify invariants after worker threads complete.

For example, with `ConcurrentHashMap`, do not demand that aggregate read operations during concurrent writes act as an atomic full-map snapshot. Its weakly consistent visibility policy is documented specifically in [ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html). A sequential reference model can be compared once the map reaches a quiescent state, whereas checks performed during concurrent updates must follow the applicable concurrent contract.

## Workflow for Building a Custom Collection Test Suite

1. Write down the public promises in behavioral terms: structure type, mutability capabilities, `null` handling, ordering, views, and concurrency.
2. Choose the target interface and capability profile; document preconditions for generated test data.
3. Create a factory that produces independent instances tailored to the test requirements.
4. Write explicit test cases covering return values, state mutations, and boundary exceptions.
5. Run multiple valid implementations through the same suite to flush out accidental class-specific assumptions.
6. Add multi-step operation sequences and compare against a reference model after every step when an appropriate model exists.
7. Create a few deliberately broken variants to verify that critical assertions actually catch defects.
8. Separate internal invariant tests, performance benchmarks, and concurrency stress tests from the shared behavioral contract suite.
9. When a new bug is discovered, shrink the failing sequence into a short, clearly named regression test.

If swapping in another valid implementation causes a test to fail, do not rush to patch the new class or delete the assertion. Trace the source of the expectation first: is it a genuine contract requirement, a misconfigured capability flag, or an implementation detail that leaked into the shared test suite?

## Self-Check Exercises

### 1. Function returns List, but the test asserts ArrayList

A function's specification only states that it returns a list preserving result order and supporting indexed reads. The test asserts that the exact runtime class is `ArrayList`.

**Answer:** The runtime-class assertion is overly strict relative to the stated requirement. Test the element sequence and indexed read behavior instead; only assert the concrete class if the API intentionally promises that specific class.

### 2. Why can converting a list to a set before comparing hide bugs?

The expected result is `[A,B,A]`, but the actual result is `[B,A]`.

**Answer:** Both convert into the exact same set `{A,B}`. The conversion discards element multiplicity and ordering, both of which are core parts of the `List` contract.

### 3. If a list supports adding elements, is it always a bug when iterator.remove throws UOE?

The object is a list whose documentation explicitly states that its iterator is a read-only snapshot iterator.

**Answer:** No. Mutating the list directly and mutating through its iterator are two distinct capabilities. The test suite should declare them separately and apply the appropriate expectations to each path.

### 4. Does an empty addAll succeeding without error prove that addition is supported?

The collection remains unchanged after `addAll(List.of())` and the method returns normally.

**Answer:** No. No elements needed to be added. Rely on the documented contract, and test with an operation that genuinely adds elements if you want to verify addition support.

### 5. A custom Set iterator yields duplicates, yet new HashSet(actual) matches the expected set

After normalizing the candidate result into a `HashSet`, the set of elements matches expectations.

**Answer:** The normalization step itself deduplicated the elements and masked the bug. You must verify the iteration element count, the candidate's `size()`, and uniqueness on the candidate directly before performing any lossy conversion.

### 6. List.set updates the element properly but returns the new value

All content assertions pass.

**Answer:** It still violates the `List.set` contract, which requires returning the previous value at that index. You need a dedicated assertion on the return value; `WrongReturnList` in the sample program demonstrates this exact defect.

### 7. Does passing a 200-step random sequence with one fixed seed prove complete correctness?

Three implementations pass the exact same 200-step operation sequence using a fixed seed.

**Answer:** No. It provides evidence only for the sequence that was executed. You still need boundary cases, tests for capabilities not exercised by the generator, a semantically accurate reference model, and independent assertions guarding critical promises.

### 8. Is testing internal state always bad practice?

A custom doubly linked structure could have a corrupted backward pointer that simple forward-traversal test cases miss.

**Answer:** Testing internal invariants is valuable for that specific implementation. Just keep those checks separate from the shared public contract test suite so you can change the internal backing store without conflating external promises with internal organization.
