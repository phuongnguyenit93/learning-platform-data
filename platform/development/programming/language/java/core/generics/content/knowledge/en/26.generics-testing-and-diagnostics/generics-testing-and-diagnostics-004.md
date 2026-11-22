# Testing Raw Type, Reflection, and Cast Boundaries in Java Generics

Java Generics primarily protect **type correctness at compile time**. When a program crosses **raw types**, **unchecked casts**, **reflection**, or APIs taking data as `Object`, part of the compiler's guarantees can be bypassed. These are the *type boundaries* that must be tested intentionally: not just testing that valid data works, but proving where invalid data is rejected, or where it will fail later if unchecked.

Objectives of this lesson:

- Distinguish **errors rejected by `javac`**, **unchecked warnings where code still runs**, and **exceptions occurring when runtime consumes wrong-typed data**.
- Build tests containing both *positive cases* and *negative cases*, rather than only running valid data.
- Understand that casting to `List<String>` does not verify each element of the list.
- Demonstrate that `Field.set` and `Method.invoke` can bypass the **type argument constraints** of a generic declaration due to erasure, while still performing the necessary runtime checks on the erased type.
- Test defensive measures such as `Class<T>.cast`, `Collections.checkedList`, typed copies/validators, and write-path controls.
- Distinguish array runtime checks from generic type checks and properly explain `ClassCastException`, `ArrayStoreException`, `IllegalArgumentException`, and `InvocationTargetException`.
- Build a standalone Java 17+ program with result checks **independent of `-ea`**, printing the count of passing tests and failing the program whenever an expected condition does not hold.

**Principle:** "Code running past an unchecked cast" does not mean "safety has been proven." A good test must ask **whether the type invariant still holds after crossing each boundary**, and whether an exception occurs immediately at the boundary or only when a caller reads the result with a concrete type argument.

## 1. Three Layers to Separate in a Test Plan

| Layer | Example | Tested With | Expected Outcome |
| --- | --- | --- | --- |
| **Compile-time type checking** | `List<String>.add(42)` from a typed caller | `javac` | Compilation error |
| **Compile-time warning** | `List raw = typed; raw.add(42)` | `javac -Xlint:rawtypes -Xlint:unchecked` | Compiles with raw/unchecked warnings |
| **Delayed runtime exception** | Reading a polluted `Integer` as `String` | Runnable test | `ClassCastException` when the value is consumed at the concrete type |
| **Active runtime validation** | `String.class.cast(42)` | Runnable test | `ClassCastException` right at the validation boundary |
| **Reflection on generic declarations** | `Field.set` assigning `List<Integer>` to a field declared `List<String>` | Reflection + subsequent read | Assignment can succeed; failure when reading elements as `String` |
| **Array runtime check** | `Object[] a = new String[1]; a[0] = 42` | Runnable test | `ArrayStoreException` immediately on write |
| **Wrong array cast** | `(String[]) new Object[]{"x"}` | Runnable test | `ClassCastException` because the array's runtime class is `Object[]` |

At the compile-time layer, the compiler blocks the operation before any program runs. At the runtime layer, the outcome depends on the **actual runtime class**, **checks applied by the API**, and **when the caller uses the polluted value**.

Do not lump every phenomenon under a single label like "Java generics are unsafe": one code path can be well protected at compile time, another path can have its contract broken by raw types, while reflection still enforces its own **erased parameter type** checks.

## 2. Identifying Boundaries Worth Testing

A generic API typically has these risk points:

1. **Data entry boundary:** `Object`, `List<?>`, JSON-parsed data, database/legacy API input; callers can assert a type argument without validating contents.
2. **Raw-type call boundary:** the compiler sees `List` without preserving the `List<String>` relationship, so an `add(Integer)` call can pass with an unchecked warning.
3. **Reflection boundary:** `Field.set`, `Method.invoke`, and `Constructor.newInstance` use the runtime classes from erased descriptors; they cannot automatically verify all parameterized arguments.
4. **Cast boundary:** `(T)`, `(List<T>)`, `Class<T>.cast`; distinguish casts actually checked by the JVM from casts the compiler only warns about.
5. **Container/array boundary:** `Object[]`, `T[]`, `List<T>`, covariant arrays, and invariant generic collections; the runtime checks each by a different mechanism.
6. **Return boundary:** an API returns `List<T>`, `T`, `T[]`; the cast may not fail at the return statement yet fails at the caller.
7. **Mutation/alias boundary:** a value that was once properly typed can be altered later via a raw alias, backing list, or another thread.

For each boundary, write down three elements clearly: **what untrusted input looks like**, **what the API's obligation is**, and **what the test must observe**. For example, an `Object -> List<String>` adapter might have the contract "immediately reject any non-`String` element"; you cannot merely test that the outer cast succeeds.

## 3. Compile-Time Tests: Operations Java Must Reject

The snippets in this section **intentionally fail to compile** and must be placed in a separate test file; do not include them in the runnable program later.

```java
import java.util.*;

class CompileTimeFailures {
    static void test() {
        List<String> names = new ArrayList<>();

        // Wrong element type: rejected by javac.
        names.add(42);

        // Generic invariance: List<String> is not List<Object>.
        List<Object> objects = names;

        // Java Generics do not accept primitive type arguments.
        List<int> numbers = new ArrayList<>();

        // There is no generic class literal List<String>.
        Class<?> token = List<String>.class;

        Object input = names;
        // Cannot verify type argument in Object -> List<String>.
        boolean ok = input instanceof List<String>;
    }
}
```

Use `javac CompileTimeFailures.java` to confirm the compiler reports errors. Specific wording may differ across JDK versions, but the **desired outcome is compilation failure**.

A test suite must not try to "run the invalid snippet and expect `ClassCastException`": those lines **do not produce valid bytecode**, so there is no runtime behavior to observe. Separate *negative compilation tests* from *runtime exception tests*.

### Why Have Negative Compilation Tests?

A generic library can accidentally weaken a public API from `void add(T)` to `void add(Object)`, or return `Object` instead of `T`. Tests that only run valid data will still pass, while operations that were previously **blocked by the compiler** are now accepted. Negative compilation tests detect regressions in the **compile-time** type-safety barrier.

When setting up CI, put fixtures that intentionally fail to compile in a dedicated group, verify a **non-zero exit code**, and inspect the required diagnostic pattern. Do not mix them into the main source build command.

## 4. Raw Types: Creating Heap Pollution via a Write Path That Triggers Compiler Warnings

Example:

```java
List<String> names = new ArrayList<>();
names.add("ok");

List raw = names; // Raw type: omits the String type argument.
raw.add(42);      // Unchecked call, usually still compiles.

// String second = names.get(1); // Runtime ClassCastException.
```

At `raw.add(42)`, the `add` method is viewed through raw `List`. Even though the same object is still referenced later through a `List<String>` variable, an `Integer` element has entered the list.

The state where a parameterized variable claims `List<String>` while the underlying data it references contains an element violating `String` is called **heap pollution**.

Tests should verify two distinct points:

- **The raw write path can succeed:** it does not necessarily throw an exception immediately when adding to an `ArrayList`.
- **The typed read path is what fails:** `String value = names.get(1)` expects a `String`; the compiler can insert `checkcast String` at the point the result is consumed.

Do not write a test like `Object o = names.get(1)` and conclude "no error": assigning to `Object` may not require casting to `String` and therefore misses the condition under test.

### Raw Types Should Not Be Part of a Production API

Raw types usually appear in legacy code or illustrative snippets. For new code, keep `List<String>`, `List<?>`, or `List<T>` as appropriate. Raw-alias tests should be **isolated in fixtures dedicated to unsafe behavior** so warnings do not leak into business code.

Run:

```bash
javac -Xlint:rawtypes -Xlint:unchecked GenericBoundaryTests.java
```

The complete example contains raw aliases **intentionally**, so warnings on those lines are expected. Do not apply `@SuppressWarnings("unchecked")` at the class level just to silence the test build; the test's purpose is to show the compiler warns at the right boundary.

## 5. Unchecked Cast of a Whole `List<T>`: Checking the Shell Without Checking Elements

With unknown data:

```java
Object outside = List.of("one", 7);

@SuppressWarnings("unchecked")
List<String> claimed = (List<String>) outside;
```

This cast can pass because the object implements `List`; Java has no dedicated runtime class for `List<String>` to scan and prove the `String` type argument.

Two different tests:

```java
// Succeeds: only checks the size.
boolean hasTwo = claimed.size() == 2;

// Fails: reads the Integer element and requires a String.
// String second = claimed.get(1);
```

Behaviors to remember:

- **`List<String>` in source code** is a generic contract enforced by the compiler on typed calls.
- **`List` at runtime** is the outer interface/container; type arguments such as `String` have been erased.
- An **unchecked cast** does not prove the actual elements, and a runtime exception can appear far away from the cast line.

A test that only checks `claimed != null` or `claimed.size()` is **not enough** to prove the returned value can be used as `List<String>`.

### The `List<?> -> List<String>` Issue

`List<?>` explicitly states "this is a list of an unknown type." It permits reading each element as `Object`, not assuming all are `String`. If you need to upgrade the contract to `List<String>`, **validate every element** or have a trustworthy proof of the data source.

## 6. Reflection on Generic Fields: Erased Type vs. Generic Signature

Definition:

```java
static final class Document {
    public List<String> tags = new ArrayList<>(List.of("start"));
}
```

Reading metadata:

```java
Field field = Document.class.getDeclaredField("tags");

Class<?> erased = field.getType();           // List.class
Type declared = field.getGenericType();     // ParameterizedType List<String>
```

`Field.getType()` returns the `Class` corresponding to the field's runtime type: `List`. `Field.getGenericType()` can return a `ParameterizedType` containing `String` from the **declared signature**. Declaration metadata is **not** a runtime validator that scans elements.

Therefore:

```java
Document document = new Document();
field.set(document, List.of(99)); // Object is a List, so it can be assigned.

// String tag = document.tags.get(0); // ClassCastException.
```

Reflection still enforces necessary `Field.set` constraints against the **runtime field type** and accessibility. It **does not automatically verify** `List<String>` by iterating through the list. Assigning a `List<Integer>` to a field declared `List<String>` can succeed if the object is a valid `List` at the erased type level.

A good test should verify:

1. Generic metadata genuinely shows the `List<String>` declaration.
2. The field's runtime type is `List`.
3. A `List<Integer>` value can enter via reflection when access and erased type rules permit.
4. When a caller later reads an element as `String`, the invariant is violated and triggers `ClassCastException`.

If reflection assigns a `String` (not a `List`) to a field of runtime type `List`, `Field.set` rejects it due to **erased field type incompatibility**. Do not conclude reflection "accepts anything."

## 7. Reflection on Generic Methods: Lookup by Erased Parameter Type

A class:

```java
static final class Box<T> {
    private T value;

    Box(T value) {
        this.value = value;
    }

    public void set(T next) {
        this.value = next;
    }

    T get() {
        return value;
    }
}
```

Since `T` has no explicit upper bound, the erasure of `T` is `Object`. The reflective method can be looked up via:

```java
Method setter = Box.class.getDeclaredMethod("set", Object.class);
Box<String> box = new Box<>("first");

setter.invoke(box, 123); // Object argument matches the erased parameter.
```

A `set(T)` method in Java source **does not automatically check `T = String` at runtime** when invoked reflectively using the erased parameter `Object`. Thus, an `Integer` value can be stored, and:

```java
// String value = box.get(); // ClassCastException.
```

exposes heap pollution.

**Distinguish two kinds of reflection exceptions:**

- If a `Method.invoke` call supplies arguments **incompatible with runtime parameter types**, reflection can throw `IllegalArgumentException` at the invoke boundary.
- If **the invoked method body itself throws an exception**, `Method.invoke` typically wraps it in `InvocationTargetException`. Tests verifying an exception from the body should inspect `getCause()`.
- If the invocation succeeds yet the data violates the generic contract, the failure may only surface on a **subsequent typed read**, as in the `Box<String>` example.

Do not write a test that merely checks `setter.invoke` returns `null` for a `void` method and assume the data is valid: a `void` method returns `null` via reflection even after storing a wrong-typed value.

### Bounds Affect the Erased Signature

With `class NumericBox<T extends Number>`, `set(T)` has erased parameter type `Number`, not `Object`. Reflection can reject a `String` (which is not a `Number`) on `invoke`, yet still cannot automatically verify every exact subtype `T` expected by the client, such as `Integer` vs. `Double`.

## 8. `Class<T>.cast`: Provable Runtime Class Checking

An `Object` value can be checked using a concrete class token:

```java
String text = String.class.cast("safe");

// String bad = String.class.cast(7); // ClassCastException.
```

Compared to `(T)` inside a generic method without a runtime token, `Class<T>.cast` knows the required class at runtime. There is also `Class.isInstance`:

```java
boolean yes = String.class.isInstance("Java"); // true
boolean no = String.class.isInstance(7);       // false
```

Edge cases to test:

- `String.class.isInstance(null)` returns `false`.
- `String.class.cast(null)` returns `null`; if the contract forbids null, apply `Objects.requireNonNull` separately.
- `Class<T>.cast` has no `List<String>.class` to verify nested type arguments. `List.class.cast(value)` only checks whether the outer object is a `List`.

An adapter API from `Object` to `List<T>` can **iterate over each element** and call `elementType.cast` before copying into a new list. For nested data, validate each level according to an appropriate schema rather than relying only on an outer cast.

## 9. `Collections.checkedList`: Runtime Guard When Writing Through the Wrapper

`Collections.checkedList(backing, String.class)` creates a wrapper that checks the runtime class of elements on additions/modifications **going through the wrapper**:

```java
List<String> protectedList =
        Collections.checkedList(new ArrayList<>(), String.class);

List rawProtected = protectedList;

// rawProtected.add(4); // ClassCastException at the write operation.
```

This is a very valuable test because it demonstrates active checking **right at the write boundary**, unlike delayed failures on a raw-polluted `ArrayList`.

However, a `checkedList` **does not** retroactively clean wrong-typed elements that existed before wrapping. If another alias refers **directly to the backing list** and writes the wrong type there, the wrapper has no way to intercept operations that bypass it.

Tests should cover:

1. Writing a valid-typed value through the wrapper succeeds.
2. Writing an invalid value through a raw alias **of the wrapper** is blocked.
3. The backing list remains unchanged after the blocked write.
4. If the design can expose a backing alias, write a dedicated test for that bypass path — or change the API so the alias is never exposed.

`checkedList` also does not automatically guarantee thread safety, immutability, or deep validation of nested generic elements.

## 10. Array Covariance and Runtime Component Types: Two Distinct Errors

Java checks arrays by their **runtime component type**, unlike the erased generic arguments of `List<String>`.

Wrong write case:

```java
Object[] strings = new String[] { "x" };
strings[0] = 8; // ArrayStoreException.
```

The reference has type `Object[]`, while the actual object is `String[]`. The JVM knows the component type is `String` and blocks storing an `Integer`.

Wrong whole-array cast case:

```java
Object[] data = new Object[] { "x" };
// String[] actual = (String[]) data; // ClassCastException.
```

Even though every current element is a `String`, the array object still has runtime class `Object[]`. Casting the reference to `String[]` does not transform the object into an array with a different component type.

Valid cast case:

```java
Object[] data = new String[] { "x" };
String[] actual = (String[]) data; // Succeeds: runtime class is String[].
```

In tests, always distinguish:

- `ArrayStoreException` is a **failure when writing an element** into an array whose runtime component type is incompatible.
- `ClassCastException` is a **failure when casting a reference** to an incompatible array class.

A generic API backed by `new Object[n]` cannot promise a genuine typed `T[]` via an unchecked cast `(T[]) data`. If a true runtime `String[]` is needed, construct it via `String[]::new` or a token/factory and copy the elements.

## 11. Complete Java 17+ Program: 17 Standalone Tests

Save the following program verbatim to **`GenericBoundaryTests.java`**. It uses only the standard JDK, requiring no JUnit.

```java
import java.lang.reflect.*;
import java.util.*;

public class GenericBoundaryTests {
    private static int passed = 0;

    static final class Box<T> {
        private T value;

        Box(T value) {
            this.value = value;
        }

        public void set(T next) {
            this.value = next;
        }

        T get() {
            return value;
        }
    }

    static final class Document {
        public List<String> tags =
                new ArrayList<>(List.of("start"));
    }

    static void check(String label, boolean condition) {
        if (!condition) {
            throw new AssertionError(label);
        }

        passed++;
        System.out.println("PASS " + label);
    }

    static void fails(
            String label,
            Class<? extends Throwable> expected,
            Runnable action) {
        try {
            action.run();
        } catch (Throwable error) {
            if (!expected.isInstance(error)) {
                throw new AssertionError(
                        label + " had "
                        + error.getClass().getSimpleName(),
                        error);
            }

            passed++;
            System.out.println(
                    "PASS " + label + " -> "
                    + error.getClass().getSimpleName());
            return;
        }

        throw new AssertionError(label + " did not throw");
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        List<String> typed = new ArrayList<>();
        typed.add("ok");

        check("typed write/read",
                typed.get(0).equals("ok"));

        List raw = typed;
        raw.add(42);

        fails("raw alias causes late failure",
                ClassCastException.class, () -> {
                    String value = typed.get(1);
                    System.out.println(value);
                });

        Object outside = List.of("one", 7);

        // Intentionally demonstrates a cast that does not inspect elements.
        @SuppressWarnings("unchecked")
        List<String> claimed = (List<String>) outside;

        check("unchecked outer cast does not inspect elements",
                claimed.size() == 2);

        fails("unchecked element read",
                ClassCastException.class, () -> {
                    String value = claimed.get(1);
                    System.out.println(value);
                });

        check("class token accepts String",
                String.class.isInstance("safe"));

        check("class token rejects Integer",
                !String.class.isInstance(7));

        fails("checked token cast",
                ClassCastException.class,
                () -> String.class.cast(7));

        Document document = new Document();
        Field field = Document.class.getDeclaredField("tags");

        check("field erased type",
                field.getType() == List.class);

        check("field generic signature",
                field.getGenericType()
                        instanceof ParameterizedType);

        field.set(document, List.of(99));

        fails("reflection field pollution",
                ClassCastException.class, () -> {
                    String value = document.tags.get(0);
                    System.out.println(value);
                });

        Box<String> box = new Box<>("first");
        Method setter = Box.class.getDeclaredMethod(
                "set", Object.class);

        check("generic method erased parameter",
                setter.getParameterTypes()[0] == Object.class);

        setter.invoke(box, 123);

        fails("reflection method pollution",
                ClassCastException.class, () -> {
                    String value = box.get();
                    System.out.println(value);
                });

        List<String> protectedList =
                Collections.checkedList(
                        new ArrayList<>(), String.class);

        List rawProtected = protectedList;

        fails("checkedList guards write",
                ClassCastException.class,
                () -> rawProtected.add(4));

        check("checkedList remains empty",
                protectedList.isEmpty());

        Object[] stringArray = new String[] { "x" };

        check("cast actual String[]",
                ((String[]) stringArray)[0].equals("x"));

        fails("array store guard",
                ArrayStoreException.class,
                () -> stringArray[0] = 8);

        Object[] objectArray = new Object[] { "x" };

        fails("Object[] is not String[]",
                ClassCastException.class, () -> {
                    String[] nope = (String[]) objectArray;
                    System.out.println(nope.length);
                });

        System.out.println("TOTAL PASS: " + passed);
    }
}
```

Compile and run with Java 17+:

```bash
javac -encoding UTF-8 -Xlint:rawtypes -Xlint:unchecked GenericBoundaryTests.java
java GenericBoundaryTests
```

**Standard output** (excluding compiler warnings):

```text
PASS typed write/read
PASS raw alias causes late failure -> ClassCastException
PASS unchecked outer cast does not inspect elements
PASS unchecked element read -> ClassCastException
PASS class token accepts String
PASS class token rejects Integer
PASS checked token cast -> ClassCastException
PASS field erased type
PASS field generic signature
PASS reflection field pollution -> ClassCastException
PASS generic method erased parameter
PASS reflection method pollution -> ClassCastException
PASS checkedList guards write -> ClassCastException
PASS checkedList remains empty
PASS cast actual String[]
PASS array store guard -> ArrayStoreException
PASS Object[] is not String[] -> ClassCastException
TOTAL PASS: 17
```

**Why doesn't this test runner require `-ea`?** `check` and `fails` **explicitly throw `AssertionError`** when a condition fails. Java's `assert` statement can be disabled unless the JVM is launched with `-ea`; this harness always runs.

**How to read the PASS lines:** each line confirms the **expected behavior of one specific scenario**. A line with `-> ClassCastException` is a **passing negative test**, not an unintended program crash.

The code contains two intentional raw aliases and two intentional unchecked calls; `-Xlint` will emit warnings. They belong to a **test fixture**, not code to copy directly into a production application.

## 12. Why Must Exception Assertions Be Precise?

A poor test might be written like this:

```java
try {
    suspiciousOperation();
} catch (Exception ex) {
    System.out.println("pass");
}
```

If `suspiciousOperation` throws a `NullPointerException` due to an unrelated bug instead of the `ClassCastException` under test, the test still reports pass. An even weaker test catches any exception yet **fails to fail when no exception is thrown**.

In the complete program, the `fails(label, expected, action)` helper enforces two conditions:

1. **Exact exception kind**: uses `expected.isInstance(error)`. If the wrong exception type is thrown, it throws `AssertionError`.
2. **An exception is mandatory**: if `action.run()` does not throw, the helper also throws `AssertionError` instead of silently passing.

For strict checks, you can compare `error.getClass() == expected` to require the exact class. `isInstance` allows subtypes of the expected exception, which is suitable when a test only needs to guarantee a general error category.

**Do not assert fixed stack trace/line numbers** if code may change or be compiled on different JDKs. Keep test expectations focused on the exception type and the contracts that truly matter.

### Why Not Check Only `ClassCastException` and Ignore the Data?

A negative test should regularly check the **state after the error**. For instance, when `checkedList` rejects adding an invalid element: in addition to the exception, verify that the list does not contain that element. If an API promises transaction-like behavior, tests must also verify state was not partially mutated; many collection APIs do **not** promise atomicity for bulk operations.

## 13. Negative Compilation Tests and `javac` Warnings: Do Not Depend on Exact Messages

For compile-time failures, create separate fixtures:

```java
// Separate file for compiler testing, not part of the runnable file.
import java.util.*;

class WrongUse {
    void addWrongValue() {
        List<String> names = new ArrayList<>();
        names.add(3); // Wrong type: rejected by the compiler.
    }
}
```

When building automated tests, check that `javac`'s exit code indicates failure. If you need to verify the **diagnostic kind**, you can check relatively stable keywords (such as the actual type and required type), while avoiding matching the entire line, punctuation, file path, or line number if multiple JDKs must be supported.

For a raw-alias fixture that is **allowed to compile with warnings**, you can test that `javac -Xlint:unchecked -Xlint:rawtypes` still emits notices. Do not confuse **errors** with **warnings**: `-Werror` can turn warnings into build errors, yet that is an added CI policy, not proof that raw calls are inherently forbidden by the JLS in every configuration.

A sensible CI strategy has three groups:

- **Compile-positive:** valid generic calls must compile.
- **Compile-negative:** calls violating the type contract must be rejected.
- **Runtime-boundary:** fixtures intentionally using raw/reflection/unchecked constructs, verifying expected exceptions and invariants.

The third group can permit intentional warnings without letting those warnings leak into the main source code.

## 14. Choosing Test Inputs to Hit the Boundaries Instead of Only the "Happy Path"

For a generic API, include test cases like the following:

| Boundary | Positive Case | Negative/Edge Case |
| --- | --- | --- |
| Typed `List<String>` | `add("A")`, `get(0)` | `add(42)` must fail compilation |
| Raw alias | No raw usage in normal code | Raw `add(42)` fails on typed read |
| `Object -> List<String>` unchecked | Actual list containing only Strings | Mixed String/Integer list still passes outer cast, fails on read |
| `Class<String>` | `cast("A")` | `cast(42)`; also evaluate null policy |
| `Field.set` | Assigning a properly typed list | Assigning `List<Integer>` to a `List<String>` field via reflection |
| `Method.invoke` | Invoking with matching erased parameter and contract-compliant data | Erased parameter lets data violating the type argument enter |
| `checkedList` | `add("A")` through wrapper | Raw alias of wrapper `add(42)` is rejected |
| Arrays | `String[]` through `Object[]` reference | Writing an `Integer` triggers `ArrayStoreException` |
| Array cast | Actual runtime object `String[]` | Runtime object `Object[]` even full of Strings triggers `ClassCastException` |
| Mutable generic container | Using typed API without exposing backing | Raw alias or mutation via backing alias breaks invariant |
| Null | Contract explicitly allows or forbids | `Class.cast(null)` and `isInstance(null)` behave differently |
| Empty container | No spurious errors from zero elements | Test empty/vacuous truth rules; do not mistake for proof that every element has a specific `T` |

**Note:** an empty list satisfies `stream().allMatch(String.class::isInstance)` due to *vacuous truth*. That does not restore the `String` type argument on the list's runtime class; if a non-empty list is required, add `!list.isEmpty()`.

## 15. Reflection Exceptions: Testing at the Right Layer

Beyond generic field/method pollution, reflection has its own failure modes.

### 15.1. `Field.set` with an Incompatible Erased Type

A field of type `List<String>` has erased type `List`. Calling:

```java
Field field = Document.class.getDeclaredField("tags");
// field.set(document, "not a list"); // IllegalArgumentException.
```

Reflection rejects an object that is **not a `List`**. It does not scan list contents when assigning a valid `List` object.

### 15.2. `Method.invoke` and `InvocationTargetException`

If the reflected method itself throws `IllegalStateException` from its body, an `invoke` call can throw **`InvocationTargetException`**. When testing, check:

```java
try {
    method.invoke(target, arguments);
    throw new AssertionError("Expected target failure");
} catch (InvocationTargetException ex) {
    Throwable cause = ex.getCause();
    if (!(cause instanceof IllegalStateException)) {
        throw new AssertionError("Wrong target cause", cause);
    }
}
```

This is an **in-context snippet** assuming `method`, `target`, and `arguments` exist, not a standalone program. `InvocationTargetException` is how reflection **wraps an exception thrown by the invoked code**, whereas `ClassCastException` when a caller later reads contract-violating data is a different scenario.

If the invocation arguments are incompatible with the **erased descriptor**, an exception can be thrown directly from `invoke` without entering the method body.

### 15.3. Access Permissions and the Module System

`Field.getDeclaredField` does not automatically grant access to every private field. `IllegalAccessException`, `InaccessibleObjectException`, or module encapsulation policies can block reflection depending on target and environment.

To test **generic boundaries** rather than access control, fixtures should use legitimately accessible declarations, as in the program above. To test module security/access control, create a separate test group; do not interpret an `IllegalAccessException` as evidence that the compiler/JVM protected `List<String>` at the element level.

## 16. Stating Type-Safety Invariants Explicitly for Testing

Suppose a library implements `Store<T>` using `private Object[] slots`:

```java
class Store<T> {
    private Object[] slots = new Object[8];
    private int size;

    void add(T value) {
        slots[size++] = value;
    }

    T get(int index) {
        @SuppressWarnings("unchecked")
        T value = (T) slots[index];
        return value;
    }
}
```

This is an illustrative snippet **without capacity/index checks**. When reviewing a complete version, the invariant should include:

1. `0 <= size <= slots.length`.
2. Every `slots[i]` in `0 <= i < size` was written through paths controlled by `T`.
3. Internal storage never escapes as a directly modifiable alias.
4. Resizing and bulk-update methods do not bypass type checks or corrupt the `size` boundary.
5. If nulls are allowed, the null policy is enforced consistently; if not, block nulls before writing.
6. All callers must honor the typed contract, or the class must keep a runtime token/validator when guarding against raw callers.
7. If used across multiple threads, proper synchronization is needed; an invariant valid in single-threaded code does not automatically prove thread safety.

For the cast `(T) slots[index]`, a test that only reads valid elements is not enough. You must test **every write path that could break the invariant**: raw aliases, reflection, backing aliases, `set`, `addAll`, deserialization, and concurrent mutation if the API claims to support it.

To protect even against raw callers, an instance can retain a `Class<T>` token and check `elementType.cast(value)` at the write boundary. This guards against objects of the wrong runtime class, though it does not automatically validate nested generic type arguments like `List<String>`.

### Why Do Failures Usually Surface at the Caller?

With an unbounded `T`, the erasure of `T` is `Object`. A `get()` returning `T` can compile to a bytecode descriptor returning `Object`; a caller needing `String` must convert from `Object` to `String` statically. Hence `ClassCastException` typically happens **when the caller uses the value**, not necessarily inside `get` or during the raw-type write.

When testing, force the result into a variable/operation that actually demands the expected type:

```java
String name = polluted.get(0); // Hits the String type check.
```

If you merely call `polluted.get(0)` and discard the result, you may miss observing the failure the test aims to prove.

## 17. The Fix: Moving from "Cast First, Fail Later" to "Validate at the Boundary"

A safer adapter for `Object` input:

```java
static <T> List<T> validatedCopy(
        Object candidate, Class<T> elementType) {
    Objects.requireNonNull(elementType, "elementType");

    if (!(candidate instanceof List<?> source)) {
        throw new IllegalArgumentException("not a List");
    }

    List<T> result = new ArrayList<>(source.size());
    for (Object value : source) {
        result.add(elementType.cast(
                Objects.requireNonNull(value, "element")));
    }

    return List.copyOf(result);
}
```

Advantages:

- `instanceof List<?>` checks the outer structure.
- `Class<T>.cast` checks each element against the runtime class supplied by the caller.
- `requireNonNull` enforces the null policy proactively.
- Copying each element into a new `List<T>` avoids structural aliasing with the source after validation.
- Eliminates any unchecked cast of the entire `List<T>`.

However, **note the limitations**: `List.copyOf` produces a structurally unmodifiable result, not a deep copy of element objects. If a mutable source is modified **during iteration**, the code does not automatically provide an atomic snapshot; synchronization or a concurrency contract is required. `Class<T>` also checks only one concrete class rather than verifying nested `List<Map<String,Integer>>`.

The test suite for the adapter should cover: non-list input, missing token, valid list, wrong-element list, list containing null, empty list, source mutated after copy, and concurrent mutation cases if the API claims support.

## 18. Using a Dedicated Test Framework Without Losing the Meaning of Tests

The pure-JDK program above helps clarify the mechanisms with zero dependencies. In a codebase using **JUnit 5**, a helper can be translated into:

```java
// JUnit 5 snippet, requires dependency org.junit.jupiter:junit-jupiter:
import static org.junit.jupiter.api.Assertions.*;

@Test
void rawAliasPollutionIsDetectedAtRead() {
    List<String> typed = new ArrayList<>();
    List raw = typed;
    raw.add(42);

    assertThrows(ClassCastException.class, () -> {
        String value = typed.get(0);
        System.out.println(value);
    });
}
```

You need to import `org.junit.jupiter.api.Test` and configure JUnit Jupiter in the project. This snippet is a **template for a test class with the appropriate dependency**, not part of the pure-JDK program in Section 11.

Framework benefits: independent test cases, clear names, easy parallel/selective execution, and per-method reporting. Yet an `assertThrows` call alone does not guarantee proof: the **specific action** must still hit the cast or type boundary, and post-exception state must be checked when relevant.

In projects tracking code coverage, use boundary tests to cover precisely those paths where generic type checks are bypassed; do not treat high coverage numbers by themselves as proof that an API is type-safe.

## 19. Common Test Design Mistakes

**Mistake 1 — "Casting to `List<String>` succeeded, so element types were checked."** No. An unchecked cast may only validate the outer structure; typed reads expose bad elements.

**Mistake 2 — "Raw types can be written, so Java has no type safety."** No. Java still has a strong type system in typed code; raw types are a legacy compatibility zone that must be controlled.

**Mistake 3 — "Reflection ignores all types."** No. Reflection still checks erased field/parameter types, accessibility, and other runtime conditions; it just does not automatically verify all generic type arguments.

**Mistake 4 — "`Field.getGenericType()` returns `List<String>`, so `Field.set` checks each element."** No. Declaration metadata and runtime data validation are two different things.

**Mistake 5 — "Any failure on `Method.invoke` becomes `ClassCastException`."** No. It can be `IllegalArgumentException` at the invoke boundary, `InvocationTargetException` when the target method throws, or `ClassCastException` when the caller later reads polluted data.

**Mistake 6 — "`Class.cast(null)` always throws."** No. It returns `null`; null policy must be tested separately.

**Mistake 7 — "`CheckedList` also protects backing aliases."** No. It protects operations through the wrapper, without stopping other code from mutating the backing list directly.

**Mistake 8 — "An `Object[]` full of Strings can be cast to `String[]`."** No. The array's runtime class determines whether the cast succeeds.

**Mistake 9 — "`ArrayStoreException` and `ClassCastException` are the same."** No. One occurs when storing an element into an array with an incompatible component type; the other occurs when casting a reference to an incompatible type.

**Mistake 10 — "A test passes if it catches any `Exception`."** Wrong. Require the right exception type and fail if nothing is thrown.

**Mistake 11 — "Only valid inputs need to be tested."** No. Raw/reflection/cast boundaries matter precisely for behavior on invalid inputs or untrusted aliases.

**Mistake 12 — "A suppressed warning means the code is safe."** No. `@SuppressWarnings` only alters compiler diagnostics; it generates no runtime checks.

**Mistake 13 — "An empty list passing `allMatch` proves a concrete class `T`."** No. Vacuous truth does not create a runtime type token.

**Mistake 14 — "A test not throwing when discarding `get()` proves safety."** No. A cast to the concrete type argument at the caller may simply not have occurred.

## 20. Checklist for Code Review and CI

A generic boundary testing suite can use this checklist:

1. **List every trust boundary:** raw types, reflection, unchecked casts, `Object` inputs, native/deserialization, arrays/varargs.
2. **For each boundary, are there positive + negative cases?** Valid writes succeed and invalid data is handled according to the contract.
3. **Are there negative compilation tests?** Calls with invalid generic types must be rejected by the compiler.
4. **Are `-Xlint:unchecked -Xlint:rawtypes` enabled?** Unexpected warnings in main source code must be investigated.
5. **Are erased descriptors checked?** With reflection, distinguish `getType/getGenericType` and `getParameterTypes/getGenericParameterTypes`.
6. **Is the expected exception class precise?** Do not catch broadly and pass; for `InvocationTargetException`, inspect `getCause()`.
7. **Is a real typed read triggered?** A heap-pollution test must force the compiler/runtime to check the expected type at the consumption point.
8. **Are runtime tokens/validators tested?** `Class.cast`, null handling, wrong classes, and nested data.
9. **Is post-failure state checked?** Did a wrapper or adapter mutate the container before rejecting the operation?
10. **Are aliases/mutations tested?** Is the private backing list kept unexposed, can raw callers break the invariant, and can the source be mutated after validation?
11. **Are arrays tested for both cast and store?** Distinguish `ClassCastException` from `ArrayStoreException`.
12. **Are unnecessary unchecked casts avoided?** Prefer `List<?>`, typed copies, tokens, or standard generic APIs.
13. **Are raw fixtures separated from production code?** Do not place overly broad `@SuppressWarnings` that hide new warnings.
14. **Are tests run on the target Java version?** For instance, use `javac --release 17` when Java 17 compatibility is required.
15. **Are both behavior and documentation verified?** Javadoc should state null policy, exception types, ownership, mutability, and when validation happens.

## 21. Conclusion

Testing raw types, reflection, and cast boundaries reveals the **exact limits of compile-time guarantees in Java Generics**. Normal typed code is protected by the compiler; raw aliases and unchecked casts can break the contract; reflection generally checks **erased types** rather than individual generic type arguments; containers and arrays have distinct runtime guards.

A solid test suite must prove three things: **the compiler blocks invalid calls where sufficient type information exists**, **the runtime detects or misses type mismatches at the exact boundaries dictated by the design**, and **the API has a way to stop untrusted data from leaking into typed code**, such as `Class<T>.cast`, validated copies, or wrappers with runtime checks. Above all, every unchecked operation must be paired with a stateable, testable safety invariant rather than merely having its warning suppressed.