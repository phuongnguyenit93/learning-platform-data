# Testing Heap Pollution and When ClassCastException Occurs in Java Generics

## 1. Why Can Generic Code Compile, Write Wrong-Typed Data, and Not Throw Immediately?

Java Generics provide type checking at **compile time**, yet most generic type arguments are removed by **type erasure**. When a program uses raw types, unchecked casts, varargs with non-reifiable components, or unsafe aliasing paths, a collection can hold data that **does not match the type the program trusts it to hold**.

That phenomenon is called **heap pollution**. An important example:

~~~java
List<String> names = new ArrayList<>(List.of("safe"));

List raw = names;
raw.add(42); // Compiles with warnings; usually does not throw an exception yet.

Object value = names.get(1); // Reading as Object: can succeed.
String name = names.get(1);  // ClassCastException when used as String.
~~~

The surprising point: an error does not necessarily occur at `raw.add(42)`. The raw alias allows calling `add` without a `String` constraint at compile time. The actual object added is an `Integer`, and `ArrayList` does not check a `String` generic argument at runtime.

The failure appears when a subsequent usage **requires treating that `Integer` as a `String`**. `javac` typically inserts `checkcast java/lang/String` along the typed-value read path; the JVM executes this cast and throws `ClassCastException`.

Therefore, when testing generic code, separate at least four points in time:

1. **Compilation:** are there `rawtypes`/`unchecked` warnings or compile errors?
2. **Creating an alias/cast:** which runtime class does the cast check, and were generic arguments checked?
3. **Writing data:** does the array/list implementation reject the element type here?
4. **Reading/consuming a typed value:** does the JVM need to perform a cast to a concrete type and throw `ClassCastException`?

**The testing goal is not merely asking "does it throw ClassCastException?" but determining "at which operation, due to which type-checking mechanism, and under what conditions?"**

## 2. Three Concepts Not to Mix Up

| Concept | Meaning | Example |
| --- | --- | --- |
| **Unchecked warning** | The compiler cannot prove the generic safety of an assignment/call/cast. | `raw.add(42)`; `(List<String>) unknown` |
| **Heap pollution** | A parameterized-type reference points to an object/data violating its type commitment. | A `List<String>` receiving an `Integer` via a raw alias. |
| **ClassCastException** | A runtime cast to a target class/interface fails. | Reading an `Integer` as a `String`. |

A **warning** does not prove wrong data actually exists. An **unchecked cast** may succeed on the runtime class while still hiding an invalid generic argument. Even a polluted list can keep working on operations like `size()` or reading directly into `Object`, only failing many steps later when the value must become a `String`.

Therefore:
- **Compilation success** does not prove data matches the type.
- **No exception on write** does not prove the write is safe.
- **Having warnings** does not prove every call will definitely throw an exception.
- **Having `ClassCastException`** does not necessarily prove heap pollution is the cause; an ordinary checked cast to the wrong class also causes `ClassCastException`.

The claims in this lesson are demonstrated and verified through the complete Java 17 program in Section 9.

## 3. What Does Type Erasure Explain?

Given collections:

~~~java
List<String> strings = new ArrayList<>();
List<Integer> numbers = new ArrayList<>();
~~~

both use the same runtime class `java.util.ArrayList`. The JVM does not generate `ArrayList<String>` and `ArrayList<Integer>` as two independent runtime classes corresponding to their type arguments.

`List<E>.get(int)` returns an object of erased type `Object` at the bytecode level. When a caller writes:

~~~java
String s = strings.get(0);
~~~

`javac` knows in source code that `strings` is `List<String>`, so it can emit bytecode corresponding to:

~~~text
invokeinterface java/util/List.get:(I)Ljava/lang/Object;
checkcast java/lang/String
astore ...
~~~

This is a **bytecode-style** illustration, not fixed instruction offsets. The additional cast after `get` checks whether the object can actually be used as a `String`.

Meanwhile:

~~~java
Object o = strings.get(0);
~~~

needs no cast from `Object` to `String` to satisfy the target variable. If the element is an `Integer` due to pollution, reading into `Object` still succeeds.

**Failure timing depends on the context requiring a target type.** A method call, assignment, return, method reference, or lambda can force the compiler/JVM to check types differently. Do not promise that "every `get` throws immediately" or that "every `get` is safe."

### Why Doesn't `ArrayList.add` Automatically Check Generic `E`?

In bytecode, generic `E` has been erased (typically to `Object` in `Collection`). `ArrayList.add(Object)` handles object references; it has no `String` runtime class token attached individually to each `List<String>` to validate inserted elements.

Conversely, a wrapper created with a `String.class` token can actively validate on write; see `Collections.checkedList` in Section 12.

## 4. Scenario 1: Pollution via a Raw `List`

A raw alias drops type arguments:

~~~java
List<String> names = new ArrayList<>(List.of("safe"));

List raw = names;
raw.add(42);
~~~

When `-Xlint:rawtypes,unchecked` is enabled, the compiler may report:
- `[rawtypes] found raw type: List` at the `List raw` declaration.
- `[unchecked] unchecked call to add(E)` at `raw.add(42)`.

Yet Java retains raw types for backward compatibility with older code. Compiler warnings do not turn into automatic runtime guards.

After the write:

~~~java
System.out.println(names.size()); // 2
~~~

still runs normally because computing size does not require reading the `Integer` as a `String`.

A read:

~~~java
Object second = names.get(1); // Integer object viewed as Object.
~~~

also succeeds.

However:

~~~java
String second = names.get(1); // ClassCastException.
~~~

when the JVM must cast the result to `String`, `Integer` is incompatible and the exception is thrown.

**Proper testing:** place the assertion/exception expectation on the typed read, while verifying the earlier steps actually ran without throwing. If a test wraps the entire method from start to finish in `expectClassCast`, you know an error occurred, but not whether it happened immediately on write or later on a read.

### 4.1. Where Is the Root Bug?

The design flaw lies in the **unsafe write path via the raw alias**. The typed read is where the error **surfaces**. The stack trace usually points to the typed read, yet the polluting action may have happened many calls earlier and in another class.

When debugging, find both where the exception occurs and where the data entered the collection. A real fix blocks raw/unchecked writes at the boundary rather than merely catching `ClassCastException` at every read site.

## 5. Scenario 2: Unchecked Cast Checks the Raw Class, Not Type Arguments

Example:

~~~java
Object unknown = List.of(7);

List<String> forged = (List<String>) unknown;
~~~

With `-Xlint:unchecked`, the compiler reports an **unchecked cast**. At runtime, the object is a `List`, so the `List` class/interface check succeeds. The JVM **does not iterate through the list to verify that elements are `String`**.

The following operations still run:

~~~java
int size = forged.size();     // 1.
Object first = forged.get(0); // Integer, yet target is Object.
~~~

Whereas:

~~~java
String first = forged.get(0); // ClassCastException.
~~~

Distinguish two things:
- Casting `Object` to `List<String>` **can still throw `ClassCastException` right at the cast** if the actual object is not a `List` at all, e.g., `"hello"`.
- If the actual object is a `List` containing non-`String` elements, the **raw class check** passes while the generic element type remains unverified. Failure then happens when an element is used as `String`.

Hence saying "an unchecked cast **always** waits until reading an element to fail" is also wrong. Timing depends on **whether the object passes the raw-type check**.

### 5.1. `List<?>` Does Not Assert the `String` Type Argument

When data is unverified, you can hold it in a variable with a more honest contract:

~~~java
if (unknown instanceof List<?> candidates) {
    for (Object candidate : candidates) {
        System.out.println(candidate);
    }
}
~~~

`instanceof List<?>` performs the appropriate runtime `List` check, yet **does not prove `List<String>`**. Iterate and check each element if you intend to expose the result as `List<String>`.

## 6. Scenario 3: Generic Varargs and Backing Arrays

Varargs `T...` are represented by an **array**. Trouble arises with non-reifiable element types such as `List<String>`:

~~~java
static void unsafeVarargs(List<String>... groups) {
    Object[] alias = groups;
    alias[0] = List.of(99);
}
~~~

Java forbids creating a generic array directly with an expression:

~~~java
// List<String>[] array = new List<String>[2];
// Compile error: generic array creation.
~~~

However, declaring `List<String>...` is valid and calling:

~~~java
unsafeVarargs(List.of("before"));
~~~

is allowed with **unchecked varargs warnings**. The compiler prepares an array with runtime component type `List`, unable to create a distinct `List<String>` component class because type arguments are non-reifiable.

Inside the method:
- `groups` has static type `List<String>[]`.
- `groups.getClass().getComponentType()` can be `List.class` when the compiler creates a backing `List[]`.
- `Object[] alias = groups` is valid because Java arrays are covariant.
- `alias[0] = List.of(99)` passes the runtime array-store check because the value is still a `List`.
- `groups[0].get(0)` returns the actual `Integer`, and a later typed read as `String` throws `ClassCastException`.

Operations like `groups[0].size()` or `Object x = groups[0].get(0)` do not require casting to `String`, so they run before the error occurs.

### 6.1. Why Is This Heap Pollution Characteristic of Generic Varargs?

Java arrays are **reifiable** at the runtime component class level: `List[]` knows "each element must be a `List`", yet does not know the first element must be `List<String>` and the second element must also be `List<String>`.

Thus the backing array for `List<String>...` allows a `List<Integer>` object to pass the `List` component check. The bug is not `List.of(99)` itself; that is a completely valid `List<Integer>`. The bug is storing it into a slot that the program treats as `List<String>`.

### 6.2. Which Compiler Warnings Should You Watch?

With:

~~~bash
javac --release 17 -Xlint:rawtypes,unchecked,varargs HeapPollutionTest.java
~~~

For the unannotated unsafe example, `javac` emits messages along the lines of:

~~~text
[unchecked] Possible heap pollution from parameterized vararg type List<String>
[unchecked] unchecked generic array creation for varargs parameter of type List<String>[]
~~~

Both warnings belong to category `unchecked`, even though the message text mentions varargs. `-Xlint:varargs` is also useful when inspecting operations that use the backing array inside a `@SafeVarargs` method yet still expose the array. Do not confuse message wording with category names.

## 7. Scenario 4: Why Does `String[]` Throw `ArrayStoreException` Earlier?

A concrete Java array **knows its runtime component class**:

~~~java
String[] textArray = {"ok"};
Object[] alias = textArray;

alias[0] = 99; // ArrayStoreException right at the write.
~~~

At runtime, the actual array object is `String[]`. The JVM checks whether the element being written is compatible with `String`, rejecting `Integer` immediately at `aastore`.

Comparison:

| Case | Runtime Component | Wrong Write | Where Failure Typically Appears |
| --- | --- | --- | --- |
| `String[]` via `Object[]` alias | `String` | Writing `Integer` | **`ArrayStoreException` at write**. |
| `List<String>[]` backing from varargs | `List` | Writing `List<Integer>` | May **not fail at write**; later typed read may throw CCE. |
| `List<String>` via raw `List` alias | No runtime `String` element type on `ArrayList` | `add(Integer)` | May **not fail at write**; later typed read may throw CCE. |
| `Collections.checkedList(...,String.class)` through the wrapper itself | Wrapper holds `String.class` token | `add(Integer)` | **`ClassCastException` at write through wrapper**. |

Why is generic array creation like `new List<String>[2]` forbidden directly? If it were allowed as a real array while reifying only raw `List`, generic argument guarantees could be easily broken via array covariance. Prohibiting generic array creation with non-reifiable component types reduces type-unsafe paths, while varargs still need source syntax support with appropriate warnings.

## 8. Test Design: Verify Both **No Early Failure** and **Failure at the Exact Point**

A poor test merely writes:

~~~java
try {
    doEverything();
} catch (ClassCastException e) {
    // considered a pass
}
~~~

This approach cannot tell whether the exception happened at:
- The initial cast;
- A write through a wrapper;
- A typed read;
- A method reference/lambda;
- A bridge method;
- Or an entirely unrelated piece of code.

A good test breaks this down into clear assertions:
1. The write through the raw alias executed.
2. The size/actual data shows a wrong-typed element is present.
3. Reading as `Object` succeeds.
4. Assigning specifically to `String` throws `ClassCastException`.
5. For a `String[]` array, writing through `Object[]` throws `ArrayStoreException` **immediately on write**.
6. For `checkedList`, an invalid write through the wrapper throws `ClassCastException` **immediately on write**.
7. A boundary validator rejects invalid data and only returns a typed copy after checking.

Using a helper such as `expect(Class<? extends Throwable>,Runnable,String)` distinguishes the exact exception type and wrapped operation. Do not merely check "some `Exception` occurred": `ClassCastException`, `ArrayStoreException`, `IllegalArgumentException`, and `AssertionError` carry different meanings.

### 8.1. Tests Must Fail When an Expected Exception Does Not Occur

A reliable helper must:
- Invoke the exact operation under test.
- If the operation **does not throw**, throw `AssertionError` to fail the test.
- If it throws the **expected class**, report the test as passed.
- If it throws a different kind, **never swallow the error**—fail instead.

In the complete example below, the helper checks `expected.isInstance(thrown)` and increments a counter for each passing check. It does not rely on Java `assert` statements, which are disabled by default unless `-ea` is enabled.

## 9. Complete Java 17 Test Program, Zero Dependencies

Save the following program verbatim as **HeapPollutionTest.java**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class HeapPollutionTest {
    private static int checks;

    private static void check(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError(label);
        }
        checks++;
        System.out.println("PASS " + label);
    }

    private static void expect(
            Class<? extends Throwable> expected,
            Runnable action,
            String label) {

        try {
            action.run();
            throw new AssertionError(
                    label + ": expected " + expected.getSimpleName()
            );
        } catch (Throwable thrown) {
            if (!expected.isInstance(thrown)) {
                throw thrown;
            }
            checks++;
            System.out.println(
                    "PASS " + label + " -> "
                            + thrown.getClass().getSimpleName()
            );
        }
    }

    static List<String> validateStrings(List<?> candidates) {
        List<String> clean = new ArrayList<>();

        for (Object value : candidates) {
            if (!(value instanceof String text)) {
                throw new IllegalArgumentException(
                        "Non-string element"
                );
            }
            clean.add(text);
        }

        return List.copyOf(clean);
    }

    // Unsafe: intentionally illustrates pollution via List[] backing.
    static void unsafeVarargs(List<String>... groups) {
        check(
                groups.getClass().getComponentType() == List.class,
                "varargs runtime component is List"
        );

        Object[] alias = groups;
        alias[0] = List.of(99);

        check(
                groups[0].size() == 1,
                "varargs polluted without immediate failure"
        );

        Object rawRead = groups[0].get(0);
        check(
                rawRead.equals(99),
                "varargs reading as Object succeeds"
        );

        expect(ClassCastException.class, () -> {
            String value = groups[0].get(0);
            System.out.println(value);
        }, "varargs typed read");
    }

    public static void main(String[] args) {
        // 1. Raw alias: wrong write without immediate failure; typed read fails.
        List<String> names =
                new ArrayList<>(List.of("safe"));
        List raw = names;
        raw.add(42);

        check(
                names.size() == 2,
                "raw insertion did not throw"
        );

        Object second = names.get(1);
        check(
                second.equals(42),
                "Object read skips String checkcast"
        );

        expect(ClassCastException.class, () -> {
            String text = names.get(1);
            System.out.println(text);
        }, "raw typed read");

        // 2. Unchecked cast from Object only checks raw List.
        Object unknown = List.of(7);
        List<String> forged = (List<String>) unknown;

        check(
                forged.size() == 1,
                "unchecked cast checked only raw List"
        );

        expect(ClassCastException.class, () -> {
            String text = forged.get(0);
            System.out.println(text);
        }, "unchecked cast typed read");

        // 3. List<String>... has backing List[].
        unsafeVarargs(List.of("before"));

        // 4. Array reification: fails immediately when writing into String[].
        String[] textArray = {"ok"};
        Object[] arrayAlias = textArray;

        expect(ArrayStoreException.class, () ->
                        arrayAlias[0] = 99,
                "reified String array write"
        );

        check(
                "ok".equals(textArray[0]),
                "reified array unchanged"
        );

        // 5. Iterate/validate at boundary and create a typed copy.
        expect(IllegalArgumentException.class,
                () -> validateStrings(names),
                "boundary validator rejects corrupted list"
        );

        check(
                validateStrings(List.of("A", "B"))
                        .equals(List.of("A", "B")),
                "validator makes typed copy"
        );

        // 6. Runtime-checked wrapper blocks wrong type at write.
        List<String> guarded = Collections.checkedList(
                new ArrayList<>(), String.class
        );
        List rawGuarded = guarded;

        expect(ClassCastException.class,
                () -> rawGuarded.add(99),
                "checkedList rejects invalid insertion"
        );

        check(
                guarded.isEmpty(),
                "checkedList backing unchanged"
        );

        System.out.println("TOTAL=" + checks);
    }
}
~~~

Compile with the compiler warnings you want to observe, then run:

~~~bash
javac --release 17 -Xlint:rawtypes,unchecked,varargs HeapPollutionTest.java
java HeapPollutionTest
~~~

The program **is expected to have `unchecked`/`rawtypes` warnings** because it intentionally constructs unsafe cases for testing. In a production application, these are not warnings to ignore; in this educational test, they are part of the subject under study.

**Exact stdout when running:**

~~~text
PASS raw insertion did not throw
PASS Object read skips String checkcast
PASS raw typed read -> ClassCastException
PASS unchecked cast checked only raw List
PASS unchecked cast typed read -> ClassCastException
PASS varargs runtime component is List
PASS varargs polluted without immediate failure
PASS varargs reading as Object succeeds
PASS varargs typed read -> ClassCastException
PASS reified String array write -> ArrayStoreException
PASS reified array unchanged
PASS boundary validator rejects corrupted list -> IllegalArgumentException
PASS validator makes typed copy
PASS checkedList rejects invalid insertion -> ClassCastException
PASS checkedList backing unchanged
TOTAL=15
~~~

The program uses **explicit `check` and `expect`** instead of `assert`, so `-ea` is not required. If any expectation fails, the program throws `AssertionError` or an unexpected exception and the test fails.

### 9.1. Order of the 15 Checks

**Raw alias group (3 checks):**
1. Raw `add` does not throw.
2. Reading the `Integer` element into an `Object` variable succeeds.
3. Reading that element into `String` throws `ClassCastException`.

**Unchecked cast group (2 checks):**
4. Casting an object with runtime type `List` to `List<String>` does not validate the type argument.
5. Reading the `Integer` in the cast list as `String` throws `ClassCastException`.

**Generic varargs group (4 checks):**
6. Runtime array component is `List`.
7. Placing `List<Integer>` into `List[]` does not throw immediately.
8. Reading the `Integer` from the group as `Object` succeeds.
9. Reading the same element as `String` throws `ClassCastException`.

**Array reification group (2 checks):**
10. Writing an `Integer` into a runtime `String[]` via `Object[]` throws `ArrayStoreException`.
11. The original array still contains `"ok"`.

**Validation group (2 checks):**
12. Validator rejects the corrupted list.
13. Validator accepts and copies a list of all `String`s.

**`checkedList` group (2 checks):**
14. Raw `add` of the wrong type through the checked wrapper throws `ClassCastException` on write.
15. The wrapper contains no elements after the failed write.

This is **one program containing operation-level independent checks**, not 15 separate test files. Grouping tests in one program makes it easy to compare exception timing in the same Java environment.

## 10. Compiler Warnings Are Evidence to Record in Testing

The command:

~~~bash
javac --release 17 -Xlint:rawtypes,unchecked,varargs HeapPollutionTest.java
~~~

can print diagnostics with representative contents:

~~~text
[unchecked] Possible heap pollution from parameterized vararg type List<String>
[rawtypes] found raw type: List
[unchecked] unchecked call to add(E) as a member of the raw type List
[unchecked] unchecked cast
[unchecked] unchecked generic array creation for varargs parameter of type List<String>[]
~~~

In this program, two raw `List` declarations and two `add` calls through raw receivers produce more warnings than the representative lines above. Line numbers, paths, and total warning counts depend on source and compiler version; inspect **category and operation location** rather than hard-coding the entire compiler stderr like stable stdout.

**Distinguish `javac` stderr from `java` stdout:**
- Compiler warnings appear during the **build** phase.
- `PASS` lines are **test execution results**.
- Having warnings does not mean `javac` failed; this test intentionally creates compilable yet unsafe code.
- If a project enables `-Werror`, warnings fail the build under that quality gate policy; separate educational unsafe-code tests from the production build or use an appropriate test strategy.

In environments using multiple compilers/language releases, checking both compile diagnostics and runtime behavior catches changes in warning locations and test logic.

## 11. Using `javap` to Find Inserted `checkcast` Points

Compile:

~~~bash
javac --release 17 -Xlint:unchecked HeapPollutionTest.java
~~~

Inspect bytecode:

~~~bash
javap -c -p HeapPollutionTest
~~~

Sections corresponding to typed reads can contain:

~~~text
invokeinterface java/util/List.get:(I)Ljava/lang/Object;
checkcast     java/lang/String
~~~

This is the **important instruction pattern**, not a full string for matching exact offsets on every `javac`. The program uses lambdas, so some `checkcast` instructions may live inside **synthetic lambda methods** shown in `javap -p -c` output.

### 11.1. Distinguishing Compile-Time Generic Type from Runtime Cast

`List<String>` guarantees the compiler only lets `get` results be used as `String` in normal checked code. Yet the actual element can be wrong if the collection was polluted via raw/unchecked aliases. When a target variable or method demands `String`, bytecode has `checkcast String`, and the JVM checks the actual data.

Thus these lines:

~~~java
Object rawRead = names.get(1);
String typedRead = names.get(1);
~~~

differ in **target type**. Calling the same `get` method does not mean the same `checkcast` is executed.

### 11.2. Stack Traces Usually Show Only Where the Bug Was Detected

If a `List<String>` passes through multiple services before a typed read, the `ClassCastException` stack trace typically points to the read/cast site. It does not answer "who put an `Integer` into `List<String>`?". Tests should model the **polluting write path** and the **detecting read point** as two separate events.

## 12. `Collections.checkedList`: Blocking Errors at the Write Boundary, with Limits

Java provides a wrapper for runtime type checking:

~~~java
List<String> checked = Collections.checkedList(
        new ArrayList<>(),
        String.class
);
~~~

It retains a `String` runtime class token and checks new elements added through the **checked wrapper**. For example:

~~~java
List raw = checked;
raw.add(99); // ClassCastException immediately on write through wrapper.
~~~

In the complete program, this addition is wrapped with `expect(ClassCastException.class, ...)` and the test then verifies the checked list remains empty.

### 12.1. A Wrapper Cannot Eliminate Every Dangerous Alias

Example:

~~~java
List<String> backing = new ArrayList<>();
List<String> guarded = Collections.checkedList(
        backing, String.class
);

// If someone holds a raw alias to the backing list itself,
// they can bypass the wrapper and insert wrong objects into the backing.
~~~

A checked wrapper only guards mutations going **through the wrapper itself**. It cannot prevent another access path from modifying the backing collection directly. Nor does it fix wrong-typed elements already present before wrapping, and it does not deep-validate nested generic structures.

Therefore, when incoming data is untrusted, it is better to **validate and build a new collection** at the trust boundary while never exposing mutable aliases to the underlying collection.

### 12.2. `CheckedList` Is Runtime Checking, Not a Reified `List<String>`

`Collections.checkedList` uses a `Class<E>` token to check directly inserted objects. It does not make all Java generics reified. For a nested element type like `List<List<String>>`, raw `List.class` alone cannot validate every `String` inside the inner lists.

If nested validation is needed, traverse the levels explicitly or use a validator suited to the business schema.

## 13. Validating Data at the Boundary Is Better Than an Unchecked Cast

A boundary method can accept `List<?>` and build a new `List<String>`:

~~~java
static List<String> validateStrings(List<?> candidates) {
    List<String> clean = new ArrayList<>();

    for (Object value : candidates) {
        if (!(value instanceof String text)) {
            throw new IllegalArgumentException(
                    "Non-string element"
            );
        }
        clean.add(text);
    }

    return List.copyOf(clean);
}
~~~

This is Java 17 code: pattern matching `instanceof String text` checks the runtime class of each element. If an element is not a `String` (including `null`), the method throws `IllegalArgumentException` per the chosen policy.

**Why isn't casting or copying alone enough?**

~~~java
// Does not verify String elements:
List<String> forged = (List<String>) unknown;

// Copying via constructor/copyOf does not automatically verify each E:
// if the source was already polluted, merely copying can keep wrong data.
~~~

A collection constructor only copies elements at the implementation's runtime `Object` level; it has no automatic `String` class token in generics. At an untrusted boundary, **validate every element before building a typed copy**.

### 13.1. Rules of `List.copyOf`

`List.copyOf(clean)` returns a `List` unmodifiable via normal APIs. It is a **shallow copy**: if elements are mutable objects, copying does not make those inner objects immutable. `List.copyOf` also rejects `null` elements by contract. In the example above, `null` is already rejected by the earlier pattern check.

Do not say `List.copyOf` automatically "fixes heap pollution." It is useful for severing shared mutable aliases **after the data has been validated**.

## 14. `@SafeVarargs` Does Not Fix a Genuinely Unsafe Method

Some generic varargs APIs are safe if they only read elements properly and never overwrite or expose the backing array. Java lets authors place `@SafeVarargs` on eligible declarations (constructors, `static`/`final`/`private` varargs methods) to commit that the implementation performs no unsafe varargs operations.

Example of a method provably safe because it only reads and creates a new `List`:

~~~java
@SafeVarargs
static <T> List<T> copyValues(T... values) {
    List<T> result = new ArrayList<>();
    for (T value : values) {
        result.add(value);
    }
    return List.copyOf(result);
}
~~~

This snippet assumes `java.util.List` and `java.util.ArrayList` are imported; the method can be placed inside a class. It neither exposes the backing array nor writes different types into it.

By contrast, `unsafeVarargs` in the test program intentionally performs:

~~~java
Object[] alias = groups;
alias[0] = List.of(99);
~~~

Adding `@SafeVarargs` to that method **does not make it safe**; it only suppresses some warnings at call sites and states a false contract. Heap pollution and `ClassCastException` still occur at runtime.

If you want to test error detection, keep the unsafe version isolated in test code rather than annotating it to make compiler output look clean.

## 15. When Can Exceptions Occur Earlier or Later?

A detection-timing table:

| Operation | Condition | Outcome to Test |
| --- | --- | --- |
| Cast `Object` to `String` | Actual object is `Integer` | `ClassCastException` **right at the cast**. |
| Cast `Object` holding a `List<Integer>` to `List<String>` | Runtime object is `List` | Raw `List` cast can pass; generic elements are unvalidated. |
| Raw `add(Integer)` to `ArrayList` with typed `List<String>` alias | No checked wrapper/token | Can succeed; typed read fails later. |
| `String s = names.get(1)` after pollution | Actual element is `Integer` | `ClassCastException` at typed read/inserted `checkcast`. |
| `Object o = names.get(1)` | Actual element is `Integer` | No cast to `String` needed; can succeed. |
| `alias[0] = 99` with alias pointing to `String[]` | Runtime component `String` | `ArrayStoreException` **right at the write**. |
| `alias[0] = List.of(99)` with alias pointing to `List[]` | Runtime component `List` | Passes array store check; later typed read can fail. |
| Raw add via `Collections.checkedList` with `String` token | Wrapper checks each insertion | `ClassCastException` **right at write through wrapper**. |
| Validating `List<?>` element by element | Encounters `Integer` when `String` expected | Validator throws `IllegalArgumentException` per boundary policy. |

Do not assume **every `ClassCastException` arrives late**; casting to an incompatible runtime class fails immediately. What we are studying is **generic type argument checks being deferred or absent at alias creation or write time**, after which a typed usage detects the mismatch.

### 15.1. What If Code Never Reads as `String`?

A polluted `List<String>` can exist for a long time without throwing `ClassCastException` if code only:
- Checks `size()`.
- Passes the reference around.
- Removes elements by index.
- Reads a value into `Object` without casting to `String`.

Yet the data still violates the API contract. **Not seeing an exception does not make that structure safe.** A later code change adding `map(String::length)` or reading into `String` can trigger the latent bug.

### 15.2. Reading via Lambdas, Iterators, or Streams Can Also Be the Detection Point

A `Consumer<String>` lambda has input type `String`. When used with a polluted `List<String>`, the element-processing step can force a cast to `String`. Thus the exception need not appear directly on a source line shaped like `String s = list.get(0)`; it can occur inside a generated lambda adapter or library reading code.

To diagnose effectively, locate where the **target type is demanded** and cross-reference the generic data source. `javap` and stack traces help pinpoint the location, though you still need to trace the write path.

## 16. Distinguishing Heap Pollution from an Ordinary Bad Cast

A pure `ClassCastException`:

~~~java
Object value = Integer.valueOf(10);
String text = (String) value; // Direct ClassCastException.
~~~

There is no generic collection or raw type; this is a normal wrong-type runtime cast. Do not label every `ClassCastException` as heap pollution.

By contrast, **heap pollution** describes the state in which a generic reference/data structure no longer upholds its declared type arguments, which can exist before an error is raised.

Warning example:

~~~java
Object unknown = List.of("A");
List<String> typed = (List<String>) unknown; // Unchecked warning.
String value = typed.get(0);                 // Succeeds with valid data.
~~~

An unchecked cast is a **risky path**, not proof on its own that the list actually holds bad elements in this case. Writing tests for both **valid data** and **invalid data** verifies whether a validation method behaves correctly.

## 17. Testing Multi-Layer Pipelines: Place Checks at Boundaries and Consumers

A real system may pass data across multiple layers:

~~~text
External source / legacy API
       │ returns raw List / Object
       ▼
Repository or adapter
       │ unchecked cast
       ▼
Service holding List<String>
       │ calls size(), passes list through methods
       ▼
Consumer / renderer
       │ String s = list.get(index)
       ▼
ClassCastException
~~~

A good test suite should include:

1. **Boundary test:** a `List<Integer>` input must not silently become `List<String>`.
2. **Contract test:** an adapter returning `List<String>` must contain real `String`s, or fail early with a clear diagnostic.
3. **Mutation test:** raw aliases must not modify data that the API promised holds only `String`.
4. **Consumer test:** logic demanding `String` should not be the only place detecting polluted data.
5. **Regression test:** after fixing the bug, invalid inputs are blocked at the appropriate point while valid inputs still succeed.

In unit tests, creating bad data via raw aliases is reasonable to reproduce the vulnerability. In production code, avoid intentionally keeping raw aliases just because tests simulated that path.

## 18. Testing with JUnit 5 If the Project Uses a Framework

The program in Section 9 needs no external libraries. If a project has **JUnit Jupiter**, a case can be converted to `assertThrows`:

~~~java
@Test
void pollutedListFailsWhenReadAsString() {
    List<String> values = new ArrayList<>(List.of("safe"));
    List raw = values;
    raw.add(42);

    assertEquals(2, values.size());

    Object value = values.get(1);
    assertEquals(42, value);

    assertThrows(ClassCastException.class, () -> {
        String text = values.get(1);
        System.out.println(text);
    });
}
~~~

This is a **snippet for a JUnit 5 test class**, not a standalone runnable Java file. It requires the JUnit Jupiter dependency and necessary imports:

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import java.util.ArrayList;
import java.util.List;
~~~

The important point is not the framework name, but the **scope of `assertThrows`**: wrap only the typed-value read, after the test has verified that the earlier raw mutation succeeded.

An overly broad assertion:

~~~java
// assertThrows(ClassCastException.class, () -> {
//     setup();
//     insertWrongValue();
//     consumeValue();
// });
~~~

can create **false confidence**: any step inside the block throwing that exception type makes the test "pass" even if the timing does not match the bug being reproduced.

### 18.1. Negative Path Testing Must Be Strict About Exception Type

If an API is required to reject schema-invalid data with `IllegalArgumentException` right at the boundary, do not write `assertThrows(Exception.class, ...)`. A late `ClassCastException` is also an `Exception`, so an overly broad expectation can hide the failure mode the test was meant to catch.

Use the specific exception type together with pre/post assertions to verify both timing and postconditions.

## 19. Do Not Depend on Verbatim `ClassCastException` Messages

Messages can vary by JDK, classloaders, module names, proxy classes, and bytecode generation:

~~~text
class java.lang.Integer cannot be cast to class java.lang.String
~~~

This is just one illustrative message format. When testing:
- Prefer asserting the **exception class** and the exact operation.
- If an API requires a stable business message, assert the message created by **the API itself**.
- Avoid strict exact matching of the entire JVM-generated `ClassCastException` message, as it is not a stable cross-environment contract.
- You may log cause/stack trace and context for debugging, yet test logic should not depend on bytecode offsets or source paths.

`HeapPollutionTest` prints only `ClassCastException`, `ArrayStoreException`, or `IllegalArgumentException` from `getClass().getSimpleName()` so stdout remains stable.

## 20. Common Mistakes When Designing Tests

### Mistake A — Test only asserts an exception at the end of the entire workflow

It fails to distinguish exceptions from casts, writes, reads, lambdas, or other steps. Test each operation and confirm preceding steps.

### Mistake B — Thinking a `rawtypes` warning is an exception

Warnings are compiler diagnostics, not automatically converted into runtime errors by the JVM. Tests need both compile diagnostics and runtime assertions when teaching this mechanism.

### Mistake C — Assuming casting to `List<String>` validated elements

`(List<String>) unknown` can only check the raw runtime class `List`, with no automatic check of all `String` elements. Iterate `List<?>` to validate.

### Mistake D — Using `new List<String>[n]` in runnable examples

Java forbids generic array creation with non-reifiable `List<String>`. Use varargs or depict a raw array **only when actively demonstrating the risk**; do not sneak unchecked hacks into production code to bypass it.

### Mistake E — Assuming `ArrayStoreException` and `ClassCastException` occur at the same place

`ArrayStoreException` occurs on a **write into a reified array**. `ClassCastException` occurs on a **cast/typed read**, or on a write through a runtime-checked wrapper. Look at the specific mechanism.

### Mistake F — Assuming `List.copyOf` automatically verifies `String`

`List.copyOf` has no `String` token to inspect generic arguments. A validator must iterate and check every element before exposing the concrete type.

### Mistake G — Putting `@SafeVarargs` on an unsafe method

The annotation is a commitment by the API author, not a compiler proof or runtime guard. If the method stores `List<Integer>` into the `List<String>[]` backing array, that commitment is false.

### Mistake H — Silencing all warnings with `@SuppressWarnings`

Broad suppression can hide new raw aliases/unchecked casts. Prefer eliminating the root cause and isolating legacy-compatible operations alongside a documented invariant.

### Mistake I — Testing only the happy path

A `List<String>` that genuinely contains only `String`s passes casts and reads normally. You must test `List<Integer>`/mixed data to verify the rejection path.

### Mistake J — Looking only at the `List` implementation class name

`names.getClass()` returns `ArrayList` (or another class), which does not prove the `String` type argument. The runtime class can be identical for `List<E>` with different `E`.

### Mistake K — Using Java `assert` and forgetting `-ea`

Java `assert` statements can be disabled by default. If the goal is a simple test harness, use explicit checks throwing `AssertionError` as in Section 9 or intentionally run with `java -ea`.

### Mistake L — Ignoring shared mutable aliases

A checked wrapper or defensive copy only helps if unsafe write paths are actually controlled. If a raw alias to the backing list still exists and allows direct writes, the invariant can be broken from another path.

## 21. Production Remediation Strategy

A workflow from test to fix:

1. **Reproduce accurately** the path creating wrong-typed data in a dedicated test; record compiler warnings.
2. **Locate where pollution occurs**, not just where `ClassCastException` is thrown.
3. **Replace raw types with parameterized types** or `List<?>` if element types are unknown.
4. **Do not use unchecked casts as validation**; validate external data element by element when needed.
5. **Consider defensive copying** to sever mutable aliases between boundaries and core domain logic.
6. **If using generic varargs**, never write via `Object[]` aliases and never return/expose the backing array unless proven safe.
7. **Use `@SafeVarargs` only** once the method's contract has been audited and verified safe.
8. **If runtime insertion checks are required**, use APIs like `Collections.checkedList` with the right token and ensure the backing reference never escapes.
9. **Place negative tests at boundaries** so type mismatches fail early with an appropriate API exception, rather than letting CCE surface randomly in a renderer.
10. **Keep regression tests for typed reads** so old bugs do not reappear when legacy code is edited.
11. **Use `javap` when needed** to locate compiler-inserted `checkcast` instructions and understand why a stack trace points to a line that looks like a simple `get`.
12. **Do not replace a bug with an unchecked suppression**; compiler messages may disappear while data remains wrong.

### 21.1. Should Boundary APIs Accept `List<?>` or `List<String>`?

If callers are fully compiler-checked typed Java code with no untrusted raw/unchecked sources, `List<String>` is a useful contract.

If arguments come from deserialization, reflection, legacy raw APIs, or uncertain objects, `List<?>`/`Object` may be a more honest input type; after validation, return `List<String>`. The decision depends on where the responsibility for proving the invariant resides.

Do not unnecessarily make every method accept `Object` if code already has proper type safety; flexible handling belongs at **risk boundaries**, while core code keeps strict generic types.

## 22. Code and Test Review Checklist

- [ ] Distinguish `rawtypes` warnings, `unchecked` warnings, heap pollution, and `ClassCastException`.
- [ ] Tests verify whether an **invalid write** throws an exception or not.
- [ ] Test reading as `Object` and reading as `String` with **two separate assertions**.
- [ ] Test that casting `Object` to `List<String>` is unchecked and does not validate elements.
- [ ] For generic varargs, verify the `List[]` runtime component and array covariance.
- [ ] For `String[]`, verify `ArrayStoreException` occurs immediately on write.
- [ ] For `Collections.checkedList`, verify invalid insertion through the wrapper fails immediately.
- [ ] Check whether mutable raw aliases to the backing collection still exist.
- [ ] Create validated typed copies where untrusted data enters.
- [ ] Never suppress compiler warnings without a safety proof.
- [ ] Use `javac --release 17 -Xlint:rawtypes,unchecked,varargs` to inspect diagnostics.
- [ ] Use `javap -c -p` when needed to inspect inserted `checkcast` instructions.
- [ ] Wrap `assertThrows`/`expect` as tightly around the **target operation** as possible.
- [ ] Do not hard-code full JVM exception messages unless they are an application contract.
- [ ] Test both valid-typed and wrong-typed data.
- [ ] Ensure tests fail when an **expected exception does not happen**.
- [ ] Also evaluate mutability, nulls, aliasing, and concurrency if data is shared across layers.

## 23. Self-Check Questions

**1.** Why can `List raw = names; raw.add(42);` run without throwing `ClassCastException` right away?

**Answer:** Raw `List` does not enforce the `String` type argument on `add`, and `ArrayList` performs no runtime `String` check for the element type of a normal `List<String>`. The compiler emits an unchecked warning, yet the write succeeds.

**2.** If `Object value = names.get(1)` then runs cleanly, is the list safe?

**Answer:** Not yet. Reading as `Object` does not prove the element is a `String`. A typed read `String value = ...` can still fail.

**3.** Where does the JVM typically detect that an `Integer` is not a `String` during a typed read?

**Answer:** A `checkcast java/lang/String` inserted by the compiler when the generic `get` result must be used as `String`.

**4.** Does an unchecked cast `(List<String>) unknown` always throw immediately?

**Answer:** No. If `unknown` is a `List<Integer>`, the raw `List` check passes; however, if `unknown` is a non-`List` object, the cast throws immediately there.

**5.** Why does a varargs backing `List<String>[]` have runtime component `List`?

**Answer:** The generic argument `String` is non-reifiable in the component type `List<String>`; the compiler creates a `List[]` when preparing a generic varargs call.

**6.** Does writing `List.of(99)` into a backing `List[]` via `Object[]` throw `ArrayStoreException`?

**Answer:** Not necessarily; `List<Integer>` is still a `List` as far as the runtime component check is concerned. The error appears later when reading the `Integer` as a `String`.

**7.** Why does `String[]` via an `Object[]` alias reject `Integer` immediately on write?

**Answer:** `String[]` is a reifiable array with runtime component `String`; the JVM performs an array-store check and throws `ArrayStoreException`.

**8.** What does `Collections.checkedList(new ArrayList<>(),String.class)` block?

**Answer:** It uses `String.class` to check the runtime type of elements inserted through the wrapper; a raw `add(Integer)` through the wrapper throws `ClassCastException` immediately on write.

**9.** Does a checked wrapper protect against someone who still holds a raw alias to the backing list?

**Answer:** No. A path bypassing the wrapper can still modify the backing list directly and corrupt the data.

**10.** Why isn't `List.copyOf` sufficient as a validator for an untrusted `List<?>`?

**Answer:** It copies elements without checking whether each `Object` is a `String` according to a generic type argument lacking a class token. You must validate each element before returning `List<String>`.

**11.** What is missing from a test that only writes `assertThrows(ClassCastException.class, () -> doEverything())`?

**Answer:** It does not verify which specific operation threw the exception; errors from another step can make the test pass mistakenly.

**12.** Will a `List<String>` containing an `Integer` necessarily throw CCE if only `size()` is called?

**Answer:** No. `size` requires no typed element cast. Pollution can persist long before being discovered.

**13.** Is `ClassCastException` always caused by heap pollution?

**Answer:** No. An ordinary bad checked cast like `(String) Integer.valueOf(1)` also throws `ClassCastException` without any generic data structure.

**14.** Why are compiler warnings considered part of testing even when the program still runs?

**Answer:** They point to paths that are not fully verified; running only the happy path can overlook latent risks. Testing covers both diagnostics and runtime behavior.

**15.** Given an external `Object` source, what is a trustworthy way to return `List<String>`?

**Answer:** First confirm the object is a `List<?>`; iterate over each element and check `instanceof String`; build a new collection with type argument `String` and avoid sharing raw mutable aliases.

**16.** Why doesn't adding `@SafeVarargs` to a method that intentionally overwrites `groups[0]` with `List.of(99)` fix the bug?

**Answer:** The annotation adds no runtime validation and does not prove the implementation safe; the backing `List[]` can still suffer heap pollution.

**17.** What does `TOTAL=15` in the test program prove?

**Answer:** All 15 assertions passed and the specific exceptions occurred at the exact wrapped operations. It does not prove that every other potential heap-pollution case has been eliminated from an application.

## 24. Summary

In Java Generics, **heap pollution is a state where data/type invariants are broken**, whereas **`ClassCastException` is one way the failure is detected at runtime when casting to a concrete class**. These two events can happen at **very distant points in time**.

~~~text
Raw alias / unchecked generic conversion / generic varargs
                       │
                       ▼
             Wrong generic-typed data
                       │
                  Not necessarily an error yet
                       │
          ┌────────────┴────────────┐
          ▼                         ▼
     size(), Object read       Typed read / cast
         may run               requires String
                                    │
                                    ▼
                             ClassCastException

Exceptions to distinguish:
String[] + Object[] alias + write Integer → ArrayStoreException at write
CheckedList<String> + write Integer via wrapper → ClassCastException at write
~~~

To test properly, confirm the **sequence of events**: compiler warnings, cast/alias, mutation, safe read, typed read, and the expected exception at the exact point. Use a self-contained test program or tight `assertThrows` around the operation, inspect `checkcast` with `javap` when needed, and fix the root cause at the raw/unchecked alias path or boundary validation instead of only catching `ClassCastException` where the failure surfaces.

**Remember:** Java Generics protect very effectively when the entire data flow obeys type checking. Once you leave the safe zone via raw types, unchecked casts, or non-reifiable varargs, the program must manage invariants itself — otherwise, failures can arrive late and far from their source.