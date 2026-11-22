# Runtime Array Type, ArrayStoreException, and the Terminating null Element

## 1. Why Does Converting a Collection to an Array Still Require Understanding Data Types?

A list may be built element by element, while another API expects a `String[]`, `Number[]`, or an existing array in which to write the result. `toArray` serves as the bridge between those two representations. However, retrieving all the values is not the whole job: the resulting array must have **an appropriate runtime component type**, enough slots to hold the data, and a clear boundary between the newly copied data and any leftover portion of a reused array.

The three questions of this lesson are:

1. Is the actual array created an `Object[]`, a `String[]`, or another type?
2. What happens if an element cannot be stored in the requested array type?
3. When the destination array is longer than the number of elements, what does the `null` slot placed after the data mean?

Imagine a storage tray labeled "strings only" with five slots. We put two people's names into it. The two names are placed at the front; the third slot is set to `null` to mark the point immediately after the copied data. The tray's "strings only" label still exists, even if the person holding the tray refers to it generically as an "object tray." If you try to put an integer into that tray, the problem lies in the actual type of the tray, not in the name of the variable holding it.

This lesson covers conversions from `Collection` to reference arrays in Java 17. It does not turn a `List<Integer>` into an `int[]`, and it does not treat array conversion as a value transformation—such as automatically converting the number `42` into the string `"42"`.

## 2. Identifying the Three Forms of toArray

`toArray()` returns `Object[]`; `toArray(T[] array)` reuses the input array if it has enough space or allocates another array of **the same runtime type**; `toArray(IntFunction<T[]>)` takes a generator function that creates an array of the corresponding type (`Collection`'s default implementation passes `0` as the argument to this function). None of these forms automatically converts individual `Integer` elements into `int`.

The previous lesson compared the syntax and array-allocation branches. Here we examine three deeper consequences: the runtime type of the container, the position of the terminating `null` when reusing a larger buffer, and the effect of an `ArrayStoreException` during copying.

## 3. The Variable Type Does Not Change the Actual Type of the Array

### 3.1. Every array has a runtime component type

In the following snippet:

~~~java
Object[] values = new String[3];
~~~

the declared type of the variable is `Object[]`, but the array object created by `new String[3]` is still a `String[]`. It has three slots, each of which can hold a `String` reference or `null`.

You can read `values[0]` as an `Object`. However, that does not mean you can store any `Object` into the array:

~~~java
values[0] = "A";  // Valid.
values[1] = 42;   // ArrayStoreException at runtime.
~~~

The number `42` is boxed into an `Integer`. It matches the `Object` type of the variable-access expression, but it does not match the `String` component type of the actual array.

Java checks element stores into reference arrays at runtime; an incompatible value throws `ArrayStoreException`. [Java Language Specification 17 — Array Store Exception](https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html#jls-10.5).

You can inspect the type for learning or diagnostics:

~~~java
System.out.println(values.getClass().getTypeName());
System.out.println(values.getClass().getComponentType().getTypeName());
~~~

The two lines print `java.lang.String[]` and `java.lang.String`, respectively. Printing the type names lets you see what object was actually created. In normal application code, creating arrays explicitly and maintaining clear type contracts remains far more important than repeatedly probing types and attempting writes.

### 3.2. Casting is not creating a new array

The following snippet illustrates a failing cast:

~~~java
Object[] plain = names.toArray();
String[] wrong = (String[]) plain;
~~~

`plain` holds an array whose actual runtime type is `Object[]`. The cast asks the JVM to verify whether that exact object is a `String[]`; it does not iterate over each string and build a new `String[]`. Therefore, it throws a `ClassCastException` right at the cast.

Comparing the two exceptions:

| Exception | What is being checked? | Example |
| --- | --- | --- |
| `ClassCastException` | Whether the array object can be viewed as the requested reference type | Casting an actual `Object[]` to `String[]` |
| `ArrayStoreException` | Whether an element value can be stored into the array's actual component type | Copying an `Integer` into a `String[]` |

The fix for the example above is to request an array of the right type directly from `toArray`:

~~~java
String[] correct = names.toArray(String[]::new);
~~~

Do not wrap an invalid cast in a `try/catch` and fall back to an empty array. That discards data without properly handling the conversion requirement.

## 4. How Does toArray(T[]) Choose the Result Array?

Let `n` be the number of elements to copy and `m` be the length of the passed-in array. When the source is stable and all elements are type-compatible, there are three cases.

| Condition | Returned array | Data and termination |
| --- | --- | --- |
| `m < n` | New array with the same runtime type as the input array | Holds all `n` elements |
| `m == n` | The input array itself | Exactly `n` slots, with no extra slot for a terminator |
| `m > n` | The input array itself | Copies into `0..n-1` and sets `null` at index `n` |

For `ArrayList`, the documentation explicitly specifies reusing or creating an array of the same runtime type, and the rule of placing `null` immediately after the end of the data when the array has extra space. [Java SE 17 — ArrayList.toArray](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html#toArray(T[])).

### 4.1. Undersized array: you must use the return value

Snippet:

~~~java
String[] small = {"old"};
String[] result = names.toArray(small);
~~~

The list has two elements, so `small` with length one is not large enough. The `result` array contains `[Lan, An]`, has runtime type `String[]`, and `result == small` is `false`. The `small` array remains a separate object; it does not grow in place.

A common mistake is ignoring the return value:

~~~java
String[] target = new String[0];
names.toArray(target);
// target still references the 0-length array.
~~~

An array cannot change its length in place. If you want `target` to hold the resulting array, you must reassign it:

~~~java
target = names.toArray(target);
~~~

Or use `String[] result = names.toArray(String[]::new)` when there is no need to reuse an existing array.

A zero-length array in `new String[0]` serves to specify the type without pre-allocating space for the names. It does not require the result to also have length `0`.

### 4.2. Exact-sized array: reuses the same array

~~~java
String[] exact = {"old0", "old1"};
String[] result = names.toArray(exact);
~~~

`result == exact` is `true` and the contents become `[Lan, An]`. There is no index `2` in a two-slot array, so no `null` is placed after the two names.

Java arrays already have a `length` property; the terminating `null` in an oversized array is a specific rule of this copy operation. It does not mean every result array must have a trailing `null` slot.

### 4.3. Oversized array: a data boundary within larger storage

~~~java
String[] large = {"old0", "old1", "old2", "old3", "old4"};
String[] result = names.toArray(large);
~~~

In the demonstration program using `ArrayList`, the result is:

~~~text
[Lan, An, null, old3, old4]
~~~

Indices `0` and `1` hold the two names. Index `2` is set to `null` because it is the position immediately following the copied data. The two old values at the end remain untouched in the observed implementation.

What the contract guarantees is the slot immediately after the data, not clearing all remaining slots. You must not interpret the entire `result.length` as the new element count of the list. Nor should you rely on this rule as a mechanism for wiping old data from the entire trailing region.

If a receiver will iterate over every element of the array and expects only the two names, passing an array of length two is clearer than sending a five-slot buffer and implicitly expecting the receiver to ignore the tail.

## 5. Understanding the Terminating null Element

### 5.1. The terminator index equals the number of copied elements

With two names and a five-slot array:

~~~text
index              0      1      2       3       4
after copy         Lan    An     null    old3    old4
role               data          term.   unused tail
~~~

More precisely, slots `0` and `1` are data; slot `2` is the specified terminator position. Subsequent slots belong to the unused tail of the reused array.

The `null` at index `2` is not an element added to `names`. The list still has `size() == 2`. The array still has `length == 5`. The conversion does not grow the list by an extra element just to mark the end.

If the source is empty and the destination array has at least one slot, the position immediately after the data is `0`. Therefore, the first slot is set to `null`. In a test case with a three-slot array, the observed result is `[null, old1, old2]`. If both the source and the destination array have length `0`, there is no slot to write to and no separate marker slot needs to be created.

### 5.2. A null in the data differs from a null used as a boundary

A list can contain `null` if that list implementation permits it. For example:

~~~java
List<String> values = Arrays.asList("A", null, "B");
String[] target = {"old0", "old1", "old2", "old3", "old4"};
values.toArray(target);
~~~

Observed result:

~~~text
[A, null, B, null, old4]
~~~

There are two distinct roles here:

- `target[1]` is an actual `null` element from the list.
- `target[3]` is the slot immediately after the three copied elements, set to `null` because the destination had extra space.

If you scan from the beginning and stop at the first `null`, the algorithm only reads `A` and misses `B`. The resulting count `1` is not the size of the source, which is `3`.

The terminator can only be used to infer length by scanning up to the first `null` when you are certain the data contains no `null` values. In a design with nullable data, track the element count separately or use a result array of the exact required length.

### 5.3. New arrays also contain null, but for a different reason

Java initializes the slots of a newly allocated reference array to `null`. Therefore, seeing multiple `null` values at the end of a new array does not prove that `toArray` actively wrote all of those slots.

To see the rule clearly, this lesson's examples deliberately pre-fill the destination array with old data `old0`, `old1`... before converting. That makes it easy to distinguish which slots were overwritten, which slot received the terminator, and which part does not belong to the new data.

This is a useful testing technique whenever code uses a reusable buffer: start with recognizable old data rather than using an all-`null` buffer and assuming all leftover slots were cleared.

## 6. ArrayStoreException During Conversion

### 6.1. Each element's type must fit the destination array

Snippet:

~~~java
Collection<Number> numbers = Arrays.<Number>asList(4, 2.5);

Number[] accepted = numbers.toArray(new Number[0]);
Integer[] rejected = numbers.toArray(new Integer[0]);
~~~

`Number[]` can hold both `Integer` and `Double`, so the first array contains `[4, 2.5]`. `Integer[]` cannot hold `Double`, so the second call throws `ArrayStoreException`.

`toArray` does not do any of the following to rescue the second call:

- It does not truncate `2.5` to `2`.
- It does not call `intValue()` on each number.
- It does not skip incompatible elements.
- It does not silently change the result from `Integer[]` to `Number[]`.

If an `Integer[]` is needed, the application must define and perform the value conversion beforehand. Rounding, truncating fractional parts, checking for overflow, or rejecting invalid data are all separate business decisions.

### 6.2. Why does the code still compile?

The signature `<T> T[] toArray(T[] a)` declares its own method-level type parameter `T`. It has no type constraint forcing every element of `Collection<E>` to be compatible at compile time. Actual compatibility is checked when storing the concrete values.

Consequently, a broadly typed source can be converted into a narrower array if all actual elements are compatible:

~~~java
List<Object> values = List.of("A", "B");
String[] strings = values.toArray(new String[0]);
~~~

Both elements here are `String`, so the call succeeds. If an `Integer` is later added to the source, the outcome will be different. Succeeding on one dataset does not guarantee type safety for every value permitted in a `List<Object>`.

When an API accepts only strings, keeping the source typed as `Collection<String>` and validating incoming data makes the model clearer. However, even a properly typed generic source does not turn the `Object[]` from the no-argument `toArray()` into a `String[]`.

### 6.3. An Object[] variable can still hold a narrower array

~~~java
Object[] target = new Integer[4];
numbers.toArray(target);
~~~

The `target` variable has a compile-time type of `Object[]`. The actual object is still an `Integer[]`, so it still cannot hold a `Double`. Having length four—plenty of room for two numbers—does not solve the type mismatch.

Two conditions must be separated:

~~~text
enough slots?
    able to copy all elements

right component type?
    able to store each value into those slots
~~~

Both must be satisfied. An array with plenty of slots whose type is too narrow is still unsuitable. An array of the right type with too few slots can be replaced by a new array, because allocating the new array preserves the component type requested by the caller.

### 6.4. Empty sources and null-only sources do not catch all type errors

If the source contains no incompatible elements, a store error will not appear just because the generic type parameters look different. An empty source has no values to store; `null` can be stored in any reference array.

Therefore, testing solely with an empty list can miss errors that real data would trigger. Include at least one value of an incompatible type when testing the `ArrayStoreException` path. Conversely, do not assume `null` in a list that allows `null` is the default cause of an array store error.

## 7. The Array Constructor Form: Type-Clear, Not Check-Free

Writing:

~~~java
String[] result = names.toArray(String[]::new);
~~~

uses an array constructor reference. Given length `n`, `String[]::new` creates a `String[n]`. It expresses the desired component type clearly without needing to cast the result of `toArray()`.

You can choose an interface type if all elements are compatible:

~~~java
CharSequence[] result = names.toArray(CharSequence[]::new);
~~~

`String` instances can be stored in `CharSequence[]`. However, an array constructor is not a per-element converter. Calling `names.toArray(Integer[]::new)` still asks to copy strings into an `Integer[]` and throws `ArrayStoreException`.

The default implementation of `Collection.toArray(IntFunction)` invokes the generator with `0` and passes that array to `toArray(T[])`. That is a detail documented for the default implementation, not a reason to write a generator that ignores the length or has side effects. Use a generator that returns a new array of the exact requested type and length. [Java SE 17 — Collection.toArray(IntFunction)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#toArray(java.util.function.IntFunction)).

Do not write code that depends on the assumption that every implementation will call the generator exactly once with `size()`. Implementations may provide their own overrides; for conversion tasks, a pure constructor reference like `String[]::new` avoids unnecessary coupling.

This lesson does not claim that one form is always faster than another. Type rules, return values, and array-reuse semantics must be understood first; performance comparisons are only meaningful when measured on a specific JDK version and workload.

## 8. Do Not Confuse the Three Meanings of null

| Where `null` appears | Meaning | How to handle |
| --- | --- | --- |
| An element of the source | Nullable data if the structure permits it | Copied as a valid reference value; readers must handle it |
| Slot immediately after data in an oversized destination array | Boundary specified by `toArray(T[])` | Do not count that slot as a new source element |
| The array or generator argument itself is `null` | Missing object to specify/create the destination array | `NullPointerException` |

A source containing a `null` element is completely different from calling:

~~~java
names.toArray((String[]) null);
~~~

This snippet throws `NullPointerException` because the destination array itself is `null`. It does not mean "create a default string array," nor does it produce a list containing a `null`.

Similarly, a `null` generator argument is invalid. In Java 17, which has both single-argument overloads, `names.toArray(null)` can even fail to compile due to overload ambiguity, since `null` matches both the array type and `IntFunction`. In the exception-testing examples, the lesson explicitly casts `null` to test the intended overload.

Avoid using `null` as an implicit signal to select an array type. Pass `new String[0]`, `String[]::new`, or use the no-argument form according to the required output contract.

## 9. Failure While Copying into a Reused Array Can Leave Partial Data

If you supply an array with enough space, the conversion may already be writing elements when it encounters an incompatible value. Do not treat `ArrayStoreException` as a guarantee that the input array was left unmodified.

Demonstration case using `ArrayList`:

~~~java
List<Object> mixed = new ArrayList<>(List.of("ok", 42, "later"));
String[] reused = {"old0", "old1", "old2", "old3", "old4"};

mixed.toArray(reused);
~~~

The `"ok"` element can be copied into the first slot. Upon reaching `42`, an `Integer` cannot be stored into `String[]`. In the executed program, after catching the exception, the array holds:

~~~text
[ok, old1, old2, old3, old4]
~~~

You must not treat `reused[3]` as a valid terminator of a successful conversion: the call failed before completing.

The OpenJDK 17 source code for `ArrayList.toArray(T[])` uses an array copy when reusing the destination buffer. The behavior of `System.arraycopy` with an incompatible reference element can copy the prefix before throwing the exception. [OpenJDK 17 — ArrayList.java](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/ArrayList.java), [Java SE 17 — System.arraycopy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#arraycopy(java.lang.Object,int,java.lang.Object,int,int)).

This explains the specific test case, not a guarantee that every `Collection` implementation leaves the exact same prefix on failure.

If the old array holds published data and must not be partially overwritten, create a new result first:

~~~java
String[] next = source.toArray(String[]::new);
// Only use or publish next after the call succeeds.
~~~

`source` in this snippet is a collection supplied by the application. If the call throws an exception, no new value is assigned to `next` by that call. The design still needs to manage other side effects and concurrency policies if applicable; a single conversion does not provide a transaction for the entire program.

## 10. A Separate Result Array Does Not Mean a Deep Copy

When creating a new result array, replacing a slot in the array does not replace the slot in the list:

~~~java
String[] snapshot = names.toArray(String[]::new);
snapshot[0] = "Other";
~~~

`names` still contains `[Lan, An]`. The `snapshot` array has its own slots and becomes `[Other, An]`.

However, `toArray` copies element references; it does not clone each object. With mutable elements:

~~~java
StringBuilder item = new StringBuilder("seed");
List<StringBuilder> items = List.of(item);
StringBuilder[] result = items.toArray(StringBuilder[]::new);

result[0].append("!");
~~~

`items.get(0)` also reflects `seed!` because the same `StringBuilder` object was mutated. If you replace `result[0]` with another `StringBuilder`, only the result array's slot changes.

This distinction connects directly to understanding "runtime type": the array object has its own component type, and each element in it is a reference to a separate object. Runtime store checks ensure the reference matches the array type; they do not make the element objects immutable.

Also distinguish this from `Arrays.asList(array)`, which creates a list backed by the underlying array's slots. `toArray` goes in the opposite direction to extract elements into an array and should not be assumed to share backing storage in the same way.

## 11. Complete Demonstration Program

Save the following code as **ToArrayRuntimeDemo.java**. The program uses only the standard library and is compatible with Java 17.

`rejects` verifies that a call fails with the expected exception type; it does not merely print a message and ignore errors. If no exception is thrown or a different exception type occurs, the program halts to expose the incorrect result.

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.List;
import java.util.function.IntFunction;

public class ToArrayRuntimeDemo {
    private static void rejects(
            String label,
            Class<? extends RuntimeException> expected,
            Runnable action) {
        try {
            action.run();
            throw new AssertionError(label + " did not fail");
        } catch (RuntimeException ex) {
            if (!expected.isInstance(ex)) {
                throw ex;
            }
            System.out.println(label + " -> " + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        List<String> names = new ArrayList<>(List.of("Lan", "An"));

        Object[] plain = names.toArray();
        System.out.println("plain-type=" + plain.getClass().getTypeName());
        System.out.println("plain-values=" + Arrays.toString(plain));
        rejects("cast-plain", ClassCastException.class, () -> {
            String[] wrong = (String[]) plain;
            System.out.println(wrong.length);
        });

        String[] typed = names.toArray(new String[0]);
        System.out.println("typed-type=" + typed.getClass().getTypeName());
        System.out.println("typed-values=" + Arrays.toString(typed));

        String[] small = {"old"};
        String[] grown = names.toArray(small);
        System.out.println("small-reused=" + (grown == small));
        System.out.println("small-original=" + Arrays.toString(small));
        System.out.println("small-result=" + Arrays.toString(grown));

        String[] exact = {"old0", "old1"};
        String[] exactResult = names.toArray(exact);
        System.out.println("exact-reused=" + (exactResult == exact));
        System.out.println("exact-values=" + Arrays.toString(exactResult));

        String[] large = {"old0", "old1", "old2", "old3", "old4"};
        String[] largeResult = names.toArray(large);
        System.out.println("large-reused=" + (largeResult == large));
        System.out.println("large-values=" + Arrays.toString(largeResult));

        String[] emptyTarget = {"old0", "old1", "old2"};
        List.<String>of().toArray(emptyTarget);
        System.out.println("empty-values=" + Arrays.toString(emptyTarget));

        List<String> nullable = Arrays.asList("A", null, "B");
        String[] nullableTarget = {"old0", "old1", "old2", "old3", "old4"};
        nullable.toArray(nullableTarget);
        int firstNull = 0;
        while (firstNull < nullableTarget.length && nullableTarget[firstNull] != null) {
            firstNull++;
        }
        System.out.println("nullable-values=" + Arrays.toString(nullableTarget));
        System.out.println("nullable-size=" + nullable.size() + " / first-null=" + firstNull);

        Collection<Number> numbers = Arrays.<Number>asList(4, 2.5);
        Number[] numeric = numbers.toArray(new Number[0]);
        System.out.println("number-type=" + numeric.getClass().getTypeName());
        System.out.println("number-values=" + Arrays.toString(numeric));
        rejects("integer-target", ArrayStoreException.class,
                () -> numbers.toArray(new Integer[0]));

        Object[] wideReference = new Integer[4];
        System.out.println("wide-reference-type=" + wideReference.getClass().getTypeName());
        rejects("wide-reference-target", ArrayStoreException.class,
                () -> numbers.toArray(wideReference));

        List<Object> stringObjects = List.of("A", "B");
        String[] narrowed = stringObjects.toArray(new String[0]);
        System.out.println("broad-source-values=" + Arrays.toString(narrowed));

        String[] generated = names.toArray(String[]::new);
        System.out.println("generator-type=" + generated.getClass().getTypeName());
        CharSequence[] sequences = names.toArray(CharSequence[]::new);
        System.out.println("interface-type=" + sequences.getClass().getTypeName());
        rejects("wrong-generator", ArrayStoreException.class,
                () -> names.toArray(Integer[]::new));
        rejects("null-array", NullPointerException.class,
                () -> names.toArray((String[]) null));
        rejects("null-generator", NullPointerException.class,
                () -> names.toArray((IntFunction<String[]>) null));

        List<Object> mixed = new ArrayList<>(List.of("ok", 42, "later"));
        String[] reused = {"old0", "old1", "old2", "old3", "old4"};
        rejects("partial-copy", ArrayStoreException.class, () -> mixed.toArray(reused));
        System.out.println("partial-target=" + Arrays.toString(reused));

        String[] snapshot = names.toArray(String[]::new);
        snapshot[0] = "Other";
        System.out.println("detached-slots=" + names + " / " + Arrays.toString(snapshot));

        StringBuilder item = new StringBuilder("seed");
        List<StringBuilder> items = List.of(item);
        StringBuilder[] itemArray = items.toArray(StringBuilder[]::new);
        itemArray[0].append("!");
        System.out.println("shared-item=" + items.get(0));
        itemArray[0] = new StringBuilder("other");
        System.out.println("replaced-slot=" + items.get(0) + " / " + itemArray[0]);
    }
}
~~~

Compile and run:

~~~shell
javac --release 17 -encoding UTF-8 ToArrayRuntimeDemo.java
java ToArrayRuntimeDemo
~~~

Exact stdout:

~~~text
plain-type=java.lang.Object[]
plain-values=[Lan, An]
cast-plain -> ClassCastException
typed-type=java.lang.String[]
typed-values=[Lan, An]
small-reused=false
small-original=[old]
small-result=[Lan, An]
exact-reused=true
exact-values=[Lan, An]
large-reused=true
large-values=[Lan, An, null, old3, old4]
empty-values=[null, old1, old2]
nullable-values=[A, null, B, null, old4]
nullable-size=3 / first-null=1
number-type=java.lang.Number[]
number-values=[4, 2.5]
integer-target -> ArrayStoreException
wide-reference-type=java.lang.Integer[]
wide-reference-target -> ArrayStoreException
broad-source-values=[A, B]
generator-type=java.lang.String[]
interface-type=java.lang.CharSequence[]
wrong-generator -> ArrayStoreException
null-array -> NullPointerException
null-generator -> NullPointerException
partial-copy -> ArrayStoreException
partial-target=[ok, old1, old2, old3, old4]
detached-slots=[Lan, An] / [Other, An]
shared-item=seed!
replaced-slot=seed! / other
~~~

The code was compiled with `--release 17` and executed on JDK 24.0.2. The compiler flag verifies Java 17 language and API compatibility; it does not mean it was executed on a Java 17 JVM.

Reading the output by group:

- `plain-type` and `cast-plain` confirm the array type created by the no-argument form and the failure when casting to the wrong type.
- `typed-type` confirms the array has a specific component type.
- `small`, `exact`, and `large` distinguish allocating a new array from reusing one; `==` checks for the same array object, not equal contents.
- `empty-values` and `nullable-values` show that the terminating `null` depends on the number of copied elements, whereas a `null` in the data is not a general stopping point.
- `integer-target` and `wide-reference-target` prove that the array's runtime type governs what values can be stored.
- `broad-source-values` illustrates that a broadly typed source can still contain only compatible strings.
- `wrong-generator`, `null-array`, and `null-generator` separate type requirements from argument validity.
- `partial-target` is the outcome of a specific failure case with `ArrayList`; do not generalize it into a guarantee about post-failure state across all structures.
- `detached-slots` and `shared-item` distinguish separate array slots from shared element objects.

These conversions run sequentially against stable sources. Do not use these results to infer a consistent snapshot when another thread is modifying a collection without an appropriate concurrency contract.

## 12. Applying Properly at API Boundaries

When a method accepts `String[]`, the clearest conversion is usually to create that type directly:

~~~java
String[] arguments = names.toArray(String[]::new);
~~~

`arguments.length` reflects the number of names in this conversion with a standard generator and a stable source. The receiver does not have to scan for `null` or know that an oversized buffer still contains old data.

If the application genuinely needs to reuse an array, keep both the returned array and the valid element count. Snippet:

~~~java
// names remains stable throughout this processing block.
int count = names.size();
String[] buffer = obtainBuffer();
buffer = names.toArray(buffer);
consumePrefix(buffer, count);
~~~

`obtainBuffer` and `consumePrefix` are application-defined methods, so this is not a standalone program. The "stable source" condition matters: calling `size` and then `toArray` are two separate operations; if uncoordinated concurrent modifications occur, you cannot assume the old count equals the data length of the new result.

The contract of `consumePrefix` should state that only indices `0` through `count - 1` belong to valid data. Having a `null` slot after the data cannot replace the count information when the source may contain `null`.

Furthermore, if the receiver retains the array for long-term use, reusing that same array for a subsequent conversion will mutate the data the receiver sees. Buffer ownership and lifetime must be managed separately. `toArray` only defines the copy operation; it does not manage other holders of references to the destination array.

When working with numbers, choose an array type that can hold the data or convert the values explicitly. `Number[]` can hold multiple numeric types; `Integer[]` is only suitable for values that can be stored as `Integer`. There is no `Collection.toArray` overload that directly accepts `int[]`, because `T[]` here is an array of a reference type. Converting to a primitive array requires a different conversion step suited to that target, not casting the result array.

## 13. Practice with Answers

### Exercise 1 — If every element is a String, can you cast?

Given `List<String> values = List.of("A", "B")`. Is `String[] result = (String[]) values.toArray()` valid at runtime? How do you fix it?

**Answer:** No, the array returned by `toArray()` has runtime type `Object[]`, so casting it to `String[]` throws `ClassCastException`. Use `values.toArray(String[]::new)` or `values.toArray(new String[0])` to request the right array type.

### Exercise 2 — Ignoring the return value

Given `String[] target = new String[1]` and a list with three strings. After `values.toArray(target)`, can you read all three elements through `target`?

**Answer:** No. The original array has only one slot; `toArray` returns a new array large enough to hold the elements, but `target` has not been reassigned. You must capture the return value, e.g., `target = values.toArray(target)`. An array object cannot grow in place via a method call.

### Exercise 3 — Filling the exact terminator slot

The list `[A, B]` is copied into `String[] target = {"x0", "x1", "x2", "x3"}`. Which slot is guaranteed to be set to `null` after a successful conversion? Is there a guarantee that all remaining slots are cleared?

**Answer:** Slot index `2` is the position immediately after the two elements and is set to `null`. The contract does not require clearing the entire tail. In the `ArrayList` demonstration case, slot `3` retains its old value. You must not treat the entire four-slot array as four new data elements.

### Exercise 4 — Is the first null the length?

The source is `[A, null, B]`, and the oversized result array becomes `[A, null, B, null, old4]`. Scanning up to the first `null` yields `1`. Why is this not the source length?

**Answer:** The `null` at index `1` is an actual element of the source, while the terminator slot is at index `3`. The data has three elements. You can only scan to the first `null` when you have a guarantee that the data contains no `null` values; otherwise, track the count separately or allocate an exact-sized array.

### Exercise 5 — Object[] yet still ArrayStoreException

Given `Collection<Number> numbers = Arrays.<Number>asList(1, 2.5)` and `Object[] target = new Integer[5]`. Why does `numbers.toArray(target)` fail even though the array is long enough?

**Answer:** The actual array object is an `Integer[]`. The `Double` element cannot be stored in it. `Object[]` is only the type of the reference variable; it does not change the actual array's type to `Object[]`. Choose `Number[]` if you need to hold both numeric types.

### Exercise 6 — Does converting with a constructor transform each value?

Given `List<Integer> values = List.of(1, 2)`, does calling `values.toArray(String[]::new)` produce `["1", "2"]`?

**Answer:** No. The constructor only specifies a `String[]` array; it does not call `toString` on each element. Copying `Integer` instances into a string array throws `ArrayStoreException`. If strings are needed, convert each value to a string first before creating the appropriate array.

### Exercise 7 — Does a failed copy leave the reused array untouched?

An `ArrayList<Object>` containing `["ok", 42, "later"]` is copied into a `String[]` with enough space. After `ArrayStoreException`, can you assume the destination array was not modified?

**Answer:** No. The lesson's test case shows that the first element was written before encountering the incompatible number. The contract provides no full rollback mechanism. If partial writes to a published array are unacceptable, allocate a new result and use it only after the conversion succeeds.

### Exercise 8 — Does a separate array protect the inner objects?

A list containing a `StringBuilder` is converted to a new `StringBuilder[]`. Calling `array[0].append("!")` and then `array[0] = new StringBuilder("other")`. How do these two operations affect the original list differently?

**Answer:** `append` mutates the `StringBuilder` object shared by both containers, so reading the element from the list also sees the change. The subsequent assignment only replaces slot `0` of the result array; it does not change the slot in the list. `toArray` does not deep-copy elements.

## 14. Questions to Answer Before Converting

Before calling `toArray`, determine the array type required by the target API, the actual element types that may appear, and whether an existing array needs to be reused. When reusing an array, always capture the return value and distinguish the storage length from the data element count.

After a successful call, a `null` slot immediately following the data appears only under the oversized-array rule; it does not clear all leftover slots, and you cannot determine length by scanning if the data itself can contain `null`. When a call fails, do not assume a reused array rolled back on its own.

The mental model to keep is: **the type of the array object determines which values can be stored; the size determines whether it is reused or newly allocated; the number of copied elements determines the position of the terminating `null`.** Together, these three rules explain conversion behavior—rather than relying on variable types or just looking at printed values.
