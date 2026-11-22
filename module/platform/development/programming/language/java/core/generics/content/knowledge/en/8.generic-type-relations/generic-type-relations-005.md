# Testing Type Errors Prevented by Java Generics Invariance

One of the major benefits of **invariance** is preventing mis-typed code right at compile time. `List<Integer>` does not automatically become `List<Number>` even though Integer is a subtype of Number, because `List<Number>` is permitted to accept Double. If Java allowed that alias, the data underlying a `List<Integer>` could be corrupted with the wrong element type.

This lesson does not merely repeat the explanation of invariance. The focus is on **designing tests capable of distinguishing**:

1. Which type errors must the compiler **block before execution**?
2. Which wildcard/copy path **preserves the type contract**?
3. If the compiler is deliberately bypassed via a **raw alias**, does the error occur on write or only when **reading as Integer**?
4. Why do arrays throw **ArrayStoreException on the write operation**, unlike many generic collection cases?
5. Can an ambiguous error at the end of a pipeline be turned into a **validation error at the data boundary**?

This is a testing/regression lesson, not a guide to using raw types in production code. All unsafe operations below are used solely in deliberate tests.

## 1. What the Compiler Blocks Immediately

With `Integer <: Number`, assigning an Integer to a Number is valid. Yet two concrete parameterized types of List are **invariant**:

~~~java
List<Integer> ids = new ArrayList<>(List.of(1, 2));

// COMPILE ERROR if uncommented:
List<Number> numbers = ids;
~~~

If the code above were accepted, one could continue:

~~~java
// Hypothetical violation of Java rules, not a runnable program:
// numbers.add(3.5);
// Integer later = ids.get(2);
// Double written through List<Number> yet read back as Integer.
~~~

**The value of the type system** is completely eliminating that dangerous cross-write path. It is not an error "caught later": javac rejects the very first assignment.

Implementing classes **still have a subtype relationship if the exact same type argument is kept**:

~~~java
ArrayList<Integer> backing = new ArrayList<>();
List<Integer> list = backing;
Collection<Integer> collection = list;
~~~

This is inheritance between **generic declarations** (`ArrayList<E> implements List<E>`, `List<E> extends Collection<E>`), not a conversion of Integer into Number in the type argument position. To check that step separately, remember the invariance rule still applies to List<Integer> and Collection<Number>.

## 2. Creating Two Separate Test Groups: Compile-Time and Runtime

A single test that wraps everything in `try/catch(ClassCastException)` is too broad. It neither proves that the compiler prevented the wrong assignment path nor proves **on which operation** the exception occurred.

Split testing into two suites:

| Test suite | Input | Result to prove |
| --- | --- | --- |
| **Negative compilation** | Source attempting to assign List<Integer> to List<Number> | `javac` fails with incompatible types. |
| **Type-safe alternative** | Viewing List<Integer> through a read wildcard, copying into a new List<Number> | Compiles/runs cleanly; original list is unpolluted. |
| **Raw alias misuse** | Raw List receives Double into an underlying list originally typed Integer | Unchecked warning occurs; write may succeed. |
| **Typed read** | Reading the Double written through the raw alias as Integer | ClassCastException at the point the element is used as Integer. |
| **Reified array** | Number[] aliasing an Integer[] and writing Double | ArrayStoreException **right at the write**. |
| **Boundary validation** | List<?> containing both Integer and Double | Validator rejects the invalid element before publishing List<Integer>. |

Separating the build and run phases is crucial: **code blocked by the compiler cannot run**. Code with intentional compile errors must go into a **separate test file**, not mixed into a program expected to run successfully.

## 3. Negative Compilation: Verifying the Exact Blocked Error

The file **CompileShouldFail.java** is designed **not** to compile:

~~~java
import java.util.ArrayList;
import java.util.List;

public class CompileShouldFail {
    public static void main(String[] args) {
        List<Integer> ids = new ArrayList<>(List.of(1, 2));

        // The compiler must reject the line below:
        List<Number> allNumbers = ids;

        allNumbers.add(3.5);
    }
}
~~~

Run:

~~~bash
javac --release 17 CompileShouldFail.java
~~~

Expected result: **non-zero exit code**, with a diagnostic along the lines of `List<Integer> cannot be converted to List<Number>` or `incompatible types`. Exact wording, line location, and message formatting depend on the javac version; **do not hard-code the verbatim entire stderr** as a contract.

Significance of this check: the invalid assignment is rejected before `add(3.5)` ever has a chance to run. This is the goal to preserve when refactoring public APIs: do not replace a method taking `List<Integer>` with raw List or introduce an unchecked cast just to make the source "compile."

### How to Turn a Negative Test into a Regression Test

A project with test infrastructure can compile small source snippets using `javax.tools.JavaCompiler` inside the test process and assert that the compile status is failure; or use the build tool's compile-fail test support. What matters is asserting that **compilation fails for the exact case under analysis**, not for an unrelated syntax error.

For pure Java examples in this lesson, running javac in the terminal and observing the exit code is sufficient.

## 4. Positive Test: Passing via Wildcard and Creating a New List

When you need to **only read Number** from a List<Integer>, use a `List<? extends Number>` reference:

~~~java
List<Integer> original = new ArrayList<>(List.of(1, 2));
List<? extends Number> readable = original;

Number first = readable.get(0); // OK.
// readable.add(3.5);           // Compile error.
~~~

When you need **a list that can actually hold Double**, create another `List<Number>`:

~~~java
List<Number> independent = new ArrayList<>(original);
independent.add(3.5); // Modifies only the new list.

System.out.println(original);    // [1, 2]
System.out.println(independent); // [1, 2, 3.5]
~~~

This is proof of safety for an **alternative design**, not "casting to List<Number>." The two collections have separate structures; copying the list does not change the source's type argument.

A `List<? super Integer>` variable can serve as a **write destination for Integer** when values need to be placed into List<Number> or List<Object>. However, when reading through this variable, the guaranteed type is only Object; do not assume every element read back is Integer.

**Runtime note:** a `List.of(...)` still does not support `add` even when the signature allows the operation by type. Therefore, positive tests use `new ArrayList<>(...)` when writes actually occur.

## 5. Raw Alias: Errors Do Not Necessarily Appear at Write Time

In a separate test file:

~~~java
List<Integer> vulnerable = new ArrayList<>(List.of(1));

List raw = vulnerable;
raw.add(3.5); // Unchecked call; may write Double successfully.

Object observed = vulnerable.get(1); // Reading as Object: may succeed.

// Integer bad = vulnerable.get(1);
// If this line executes, ClassCastException occurs when runtime requires Integer.
~~~

`raw` and `vulnerable` are **the same collection object**, not a copy. Raw List drops the E check on `add`, so ArrayList accepts a Double in a slot that typed code views as Integer.

In bytecode, generic `List.get` has erased return type Object; when the caller requires Integer, javac can emit `checkcast java/lang/Integer`. ClassCastException typically occurs at the **typed read / typed usage**, not necessarily at `raw.add`.

When testing this bug, the two assertions must be **separated**:
1. Verify that the raw write actually mutated the data without throwing an exception.
2. Wrap only the typed read in the block expecting ClassCastException.

If you wrap the entire init–write–read sequence in a single catch block, the test could pass due to an exception from an operation other than the intended one.

### javac Warnings

Use:

~~~bash
javac --release 17 -Xlint:rawtypes,unchecked InvarianceRegressionDemo.java
~~~

When the code contains `List raw = vulnerable; raw.add(3.5);`, the compiler can emit:
- `[rawtypes]` due to using raw List.
- `[unchecked]` at the add(E) call through a raw receiver.

Warnings **are not exceptions themselves** and do not mean the compiler rejects the build, unless the project configures a quality gate such as `-Werror`.

Do not use `@SuppressWarnings("unchecked")` as a "fix": suppression only hides the warning without verifying the collection's type arguments.

## 6. Control Comparison: Arrays Catch the Error on Write

Java arrays have a runtime component type (**reified**), so a Number[] alias can point to an actual Integer[] array, and Java checks whether the written element is compatible with Integer:

~~~java
Number[] view = new Integer[1];

try {
    view[0] = 3.5;
} catch (ArrayStoreException ex) {
    System.out.println("arrayWrite=ArrayStoreException");
}
~~~

The statement `view[0] = 3.5` compiles because the static type Number[] accepts Number, yet the actual Integer[] array object does not accept Double. The JVM throws **ArrayStoreException on the write**.

| Case | What is constrained/checked? | Point of error detection |
| --- | --- | --- |
| `List<Integer> → List<Number>` | Generic invariant assignment | Compile time, never runs. |
| Raw `add(Double)` into ArrayList<Integer> | Only erased Object type on add; generic E check lost | May not fail on write; data is polluted. |
| Typed `Integer x = vulnerable.get(1)` | JVM checkcast Integer at typed usage | ClassCastException if the element is Double. |
| `Number[] view = new Integer[1]`, write Double | Runtime array component Integer | ArrayStoreException on write. |

Do not say "generic type safety is entirely runtime" or "arrays are unsafe." Both mechanisms provide protection, but **at different times and with different type evidence**.

## 7. Validator at the Data Boundary: Fail Early with Clear Semantics

In an API receiving untrusted data, you should not return `List<Integer>` merely via an unchecked cast from Object or raw List.

Instead, accept `List<?>` and check **every element**:

~~~java
static List<Integer> requireIntegers(List<?> source) {
    List<Integer> checked = new ArrayList<>();

    for (Object item : source) {
        if (!(item instanceof Integer value)) {
            throw new IllegalArgumentException("expected Integer");
        }
        checked.add(value);
    }

    return checked;
}
~~~

Java 17 supports pattern matching `instanceof Integer value`. If a Double, String, or null is encountered, the method throws IllegalArgumentException under the example's policy; invalid data is rejected **right at the boundary** rather than propagating deep to where code reads Integer.

The method returns a **copy** of the collection structure, so a raw alias to source cannot directly insert elements into the resulting list. However, if elements are mutable objects, this is still a shallow copy; the current example uses immutable Integer.

You can choose a different exception type or domain validation result depending on the real contract. What matters is that validation actually inspects the elements, rather than pretending a cast `(List<Integer>) someList` checked all generic arguments.

## 8. Complete Java 17 Program, Testing at the Exact Phases

Save as **InvarianceRegressionDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class InvarianceRegressionDemo {
    static List<Integer> requireIntegers(List<?> source) {
        List<Integer> checked = new ArrayList<>();
        for (Object item : source) {
            if (!(item instanceof Integer value)) {
                throw new IllegalArgumentException("expected Integer");
            }
            checked.add(value);
        }
        return checked;
    }

    public static void main(String[] args) {
        // Positive path: create a separate List<Number> instead of aliasing.
        List<Integer> original =
                new ArrayList<>(List.of(1, 2));
        List<Number> independent = new ArrayList<>(original);
        independent.add(3.5);

        System.out.println(
                "safe=" + original + " / " + independent
        );

        // Test-only misuse: raw alias bypasses generic type checking.
        List<Integer> vulnerable =
                new ArrayList<>(List.of(1));
        List raw = vulnerable;
        raw.add(3.5);

        System.out.println("rawWrite=" + vulnerable.size());

        Object observed = vulnerable.get(1);
        System.out.println("rawAsObject=" + observed);

        try {
            Integer bad = vulnerable.get(1);
            System.out.println(bad);
        } catch (ClassCastException ex) {
            System.out.println("typedRead=ClassCastException");
        }

        // Array covariance: fails immediately at the write operation.
        Number[] array = new Integer[1];
        try {
            array[0] = 3.5;
        } catch (ArrayStoreException ex) {
            System.out.println("arrayWrite=ArrayStoreException");
        }

        // Validate input before publishing List<Integer>.
        try {
            requireIntegers(vulnerable);
        } catch (IllegalArgumentException ex) {
            System.out.println("boundary=IllegalArgumentException");
        }

        System.out.println(
                "validated=" + requireIntegers(List.of(3, 4))
        );
    }
}
~~~

Compile, observe warnings, and run:

~~~bash
javac --release 17 -Xlint:rawtypes,unchecked InvarianceRegressionDemo.java
java InvarianceRegressionDemo
~~~

**Verified stdout:**

~~~text
safe=[1, 2] / [1, 2, 3.5]
rawWrite=2
rawAsObject=3.5
typedRead=ClassCastException
arrayWrite=ArrayStoreException
boundary=IllegalArgumentException
validated=[3, 4]
~~~

Step-by-step explanation:
1. **safe:** the Number copy contains the added Double, while the Integer source remains intact.
2. **rawWrite=2:** adding Double through the raw alias succeeds and increases size; no CCE yet.
3. **rawAsObject=3.5:** the same element is read as Object so no Integer cast is needed.
4. **typedRead=ClassCastException:** runtime finally has to treat Double as Integer.
5. **arrayWrite=ArrayStoreException:** the JVM blocks writing Double into an actual Integer[].
6. **boundary=IllegalArgumentException:** the validator detects Double against the Integer schema and rejects it.
7. **validated=[3, 4]:** valid data is inspected and produces a safe typed copy.

Do not merge the negative compilation file `CompileShouldFail.java` into this program. It serves a separate purpose: **compilation must fail**, whereas this file **must compile successfully with intentional warnings** and produce deterministic output.

## 9. Test Cases That Easily Lead to Wrong Conclusions

### "There was no ClassCastException on raw add, so the data is safe"

False. Raw add can pass through the erased Object parameter. The error only surfaces when an operation requires a typed result and the runtime cast fails.

### "`List<?>` is an immutable list"

False. `List<?>` is a type with an unknown type argument. It prevents adding arbitrary non-null elements via the generic API, yet it does not prevent `clear` or `remove`, and the underlying object can still be mutable.

### "A test with only ClassCastException proves invariance worked"

Insufficient. Invariance protects at compile time, so you must test that **the compiler rejects** the invalid assignment. ClassCastException appears after code has already bypassed generic checks or performed an invalid runtime cast.

### "Every exception should be handled with catch"

No. For a new generic API, prioritize not creating raw alias paths that cause pollution. Only catch exceptions at appropriate business boundaries while keeping compiler contracts accurate.

### "Java generics prevent all runtime type errors"

False. Generics detect many static mistakes, yet reflection, raw types, unchecked casts/conversions, and external data still require responsible handling. Compiler-inserted casts and runtime checks do not turn invalid data into valid data.

### "Using checkedCast or a wrapper eliminates the need for validation"

`Class<Integer>` only checks whether an individual object is an Integer; it does not verify an entire `List<Integer>` via a single cast on List. `Collections.checkedList` can check insertions made through the wrapper when given an appropriate class token, yet it does not stop mutations bypassing the wrapper through an alias to the backing collection.

## 10. Regression Test Checklist Before Accepting a Refactor

1. **Negative compilation:** confirm `List<Number> = List<Integer>` is still rejected by the compiler.
2. **Positive wildcard:** accept List<Integer> via `? extends Number` and read only.
3. **Positive copy:** build a new `List<Number>`, adding Double without mutating source.
4. **Raw warnings:** the intentionally raw test path produces `rawtypes/unchecked` diagnostics.
5. **Write vs read:** raw insertion succeeded before the typed read failure.
6. **Object read:** reading as Object does not itself prove the element type.
7. **Correct exception:** typed read throws ClassCastException at the right point.
8. **Array contrast:** array-store check throws ArrayStoreException on write.
9. **Boundary validation:** reject invalid data from List<?> and accept valid data.
10. **No unchecked workaround:** production APIs do not use raw casts to bypass invariant type arguments.
11. **Mutability:** positive writes use a genuinely modifiable collection.
12. **Type vs policy:** a properly typed List<Integer> can still violate business rules such as negative values, null policy, or size limits.

## 11. Self-Check Questions

**1.** Does invariance of List<T> block errors at compile time or runtime?

**Answer:** Primarily at compile time across assignments/calls with incompatible type arguments.

**2.** Can an Integer be assigned to Number? Does that imply List<Integer> can be assigned to List<Number>?

**Answer:** Yes for an individual Integer object; no for the two concrete parameterized List types.

**3.** If raw add(Double) into a List<Integer> succeeds, when can CCE appear?

**Answer:** When typed code needs to use the Double as an Integer, such as `Integer i = list.get(index)`, not necessarily at raw add.

**4.** If you must accept List<Integer> only to read Number, should you create a List<Number> copy?

**Answer:** Usually not needed; choose `List<? extends Number>` for the receiving parameter when the API can be modified.

**5.** If you must add both Integer and Double into an independent collection, what should you use?

**Answer:** An actual `List<Number>`, which can be created with `new ArrayList<>(sourceIntegers)`.

**6.** Why does a Number[] view of Integer[] throw ArrayStoreException on a Double write?

**Answer:** The JVM knows the array's runtime component type is Integer, so it blocks the Double value at write time.

**7.** Why is casting List<?> to List<Integer> insufficient to validate data?

**Answer:** Erasure does not check the generic arguments of all elements; you must validate each element or rely on a trustworthy invariant source.

**8.** What does a test that asserts only a generic exception at the end of a workflow miss?

**Answer:** It fails to pinpoint where and at which phase the error actually occurred; it may pass due to an exception from an unrelated operation.

**9.** When test output prints `rawAsObject=3.5`, what does that prove?

**Answer:** The actual value is a Double, and reading it as Object does not require casting to Integer. It does not confirm that the collection is safe under the Integer contract.

**10.** Does a List<Integer> guarantee no nulls or only positive values?

**Answer:** No. Generic type relationships are distinct from null/business value constraints; separate validation and data contracts are required.

**Takeaway:** **the compiler blocks invalid aliases before execution**; if generic checks are deliberately bypassed, errors may surface late on typed reads. Good design combines negative compilation tests, positive wildcard/copy tests, diagnostics for raw paths, and boundary validation to prevent invalid data from entering the core application.