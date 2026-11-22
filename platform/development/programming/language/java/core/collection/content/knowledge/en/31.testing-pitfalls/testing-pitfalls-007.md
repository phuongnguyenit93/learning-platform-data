# ClassCastException, NullPointerException, and Invalid Data Types in Java Collections

## 1. Objectives

In Java Collections (`List`, `Set`, `Queue`, `Map`), failures can occur when adding, reading, sorting, converting, or using elements. Distinguish three categories:

- **`ClassCastException`**: an object is cast to a type that the actual runtime object is not an instance of. With generics, this failure can occur at `get()` because the compiler inserts an implicit cast.
- **`NullPointerException` (NPE)**: dereferencing `null`, auto-unboxing a `null` value, or passing `null` to a factory/API that does not allow `null`.
- **Invalid type/value**: external data violates a type contract or business rule (for example, receiving the string `"90"` where an `Integer` is expected, or a score of `120` where only 0–100 is accepted).

The objective is to locate the source of failure, prevent it using generics and validation, and test both happy paths and failure paths on Java 17+.

## 2. Identifying the Right Error Type

| Symptom | Exception | Explanation |
| --- | --- | --- |
| Reading a `String` when the actual element is an `Integer` | `ClassCastException` | Invalid cast; typically caused by raw types or unchecked casts causing heap pollution in the collection. |
| Calling a method on a `null` element | `NullPointerException` | `null` is not an object to dereference. |
| Retrieving a `null` `Integer` and assigning it to an `int` | `NullPointerException` | Unboxing requires a non-null value. |
| Creating `List.of("A", null)`, or `List.copyOf` containing `null` | `NullPointerException` | These factories disallow `null` elements. |
| Data has the right type but falls outside the valid range | `IllegalArgumentException` if explicitly validated | This is a data contract violation, not a type cast error. |
| Parsing `"12x"` into an integer | `NumberFormatException` | The string is not a valid number format, unlike casting from `String` to `Integer`. |
| Copying `Integer` elements into a `String[]` via `toArray(T[])` | `ArrayStoreException` | The destination array has an incompatible component type. |
| Adding to `List.of` or `List.copyOf` | `UnsupportedOperationException` | The resulting collection is unmodifiable; unrelated to element types. |
| Reading an index outside the list size | `IndexOutOfBoundsException` | Index boundary error, not an NPE or ClassCastException. |

The exception name tells you the symptom at a specific operation; the place where bad data entered the system may be on a different line. Do not catch every `RuntimeException` and return a default value: doing so easily hides data errors.

## 3. ClassCastException and Generics

### 3.1. Why Can Generics Still Fail at Runtime?

`List<String>` helps the compiler reject `names.add(42)` when `names` is properly typed. However, Java uses **type erasure**: most generic type arguments are not retained to automatically check every element at runtime. Raw types, unchecked casts, reflection, or legacy libraries can insert the wrong type into a list.

```java
List<String> names = new ArrayList<>();
List raw = names;         // Raw type: loses generic type checking.
raw.add(42);             // Inserts an Integer into List<String>.
String first = names.get(0); // ClassCastException at the read site.
```

The snippet above requires importing `java.util.ArrayList` and `java.util.List`; the compiler warns about raw/unchecked operations. Do not use this in production. The wrong element was inserted before the exception appeared; fixing the `get` line without fixing the `add` site only treats the symptom.

You cannot write `value instanceof List<String>`: the `String` type argument is erased. `value instanceof List<?>` only confirms that the object is a `List`; to trust that every element is a `String`, you must validate the elements or receive the collection from a source with a trustworthy type contract.

### 3.2. Running a Lab to Reproduce the Failures

Save as `CollectionFailureDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class CollectionFailureDemo {
    @SuppressWarnings({"rawtypes", "unchecked"})
    static List<String> pollutedList() {
        List<String> names = new ArrayList<>();
        List raw = names;
        raw.add(42); // Intentionally wrong to simulate a legacy API.
        return names;
    }

    static void show(String label, Runnable operation) {
        try {
            operation.run();
            System.out.println(label + ": OK");
        } catch (RuntimeException ex) {
            System.out.println(label + ": " + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        show("wrong-cast", () -> {
            String name = pollutedList().get(0);
            System.out.println(name);
        });

        show("null-element", () -> {
            List<String> names = new ArrayList<>();
            names.add(null);
            System.out.println(names.get(0).length());
        });

        show("factory-null", () -> {
            List.of("An", null);
        });

        show("null-unboxing", () -> {
            List<Integer> values = new ArrayList<>();
            values.add(null);
            int number = values.get(0);
            System.out.println(number);
        });
    }
}
```

Compile/run on JDK 17+:

```bash
javac CollectionFailureDemo.java
java CollectionFailureDemo
```

Stdout:

```text
wrong-cast: ClassCastException
null-element: NullPointerException
factory-null: NullPointerException
null-unboxing: NullPointerException
```

`@SuppressWarnings` is used only in the example to simulate unsafe code; it does not inspect or fix collection contents. The `show` helper catches exceptions for demonstration; real applications should let unexpected errors surface clearly or translate them into contextual exceptions at an appropriate boundary.

### 3.3. How to Avoid Invalid Casts

For an `Object` value coming from an untrusted source:

```java
Object value = 42;

if (value instanceof String text) {
    System.out.println(text.length());
} else {
    System.out.println("Không phải String");
}
```

Output: `Không phải String`. `instanceof` on `null` evaluates to `false`. However, if the contract requires *every* element to be a `String`, silently skipping invalid elements will cause data loss. It is better to validate the entire input, report the index and the invalid value type, and return a normalized collection.

`Collections.checkedList(new ArrayList<String>(), String.class)` can guard a boundary against raw APIs: the wrapper checks types on insertion and throws `ClassCastException` early. The wrapper **does not scan and fix** invalid elements already present in the backing list. Proper generics and input validation remain the primary defenses.

### 3.4. Sorted Collections Also Have Type Contracts

`TreeSet`/`TreeMap` must compare elements or keys. When using natural ordering, values must be mutually comparable; when using a `Comparator`, the comparator must accept the target type and define a consistent ordering. Mixing incompatible types via raw collections can trigger a `ClassCastException` during insertion, lookup, or sorting, depending on the data and operation.

Use `TreeSet<String>` or an explicitly typed comparator. If you need to compare `null` values, define the rule explicitly using `Comparator.nullsFirst(...)` or `nullsLast(...)` combined with an appropriate comparator. Do not assume natural ordering accepts `null`.

## 4. NullPointerException in Collection Operations

### 4.1. Null Policies Vary by API

- `ArrayList` allows `null` elements; `HashMap` allows one `null` key and `null` values.
- `List.of(...)`, `Set.of(...)`, `Map.of(...)`, `List.copyOf(...)` reject disallowed `null`s; the failure usually happens immediately upon creation.
- `ConcurrentHashMap` does not allow `null` keys or values.
- `TreeMap` with natural key ordering does not allow `null` keys; with a custom comparator, `null` handling depends on the comparator.
- `Collections.unmodifiableList(list)` only creates a view that prevents modification through the wrapper; it does not remove `null`s already present in the source list.

Example:

```java
List<String> names = new ArrayList<>();
names.add(null);                    // Valid.
System.out.println(names.size()); // 1
System.out.println(names.get(0)); // null
names.get(0).length();            // NullPointerException.
```

`null` can be inserted legally yet cause an NPE on subsequent use. Similarly, `Integer boxed = null; int n = boxed;` throws an NPE because Java must perform unboxing.

### 4.2. Map.get Returning Null Is Not Enough to Conclude a Missing Key

With `HashMap`:

```java
import java.util.HashMap;
import java.util.Map;

Map<String, String> labels = new HashMap<>();
labels.put("has-null", null);

System.out.println(labels.containsKey("has-null")); // true
System.out.println(labels.containsKey("missing"));  // false
System.out.println(labels.get("has-null"));         // null
System.out.println(labels.get("missing"));          // null
```

`get(key) == null` cannot distinguish between an absent key and a key mapped to `null`. `getOrDefault(key, fallback)` only returns the fallback when there is no mapping; an existing mapping with a `null` value still produces `null`. Decide clearly whether business logic needs to distinguish these two states, then use `containsKey` or adjust the data model accordingly.

### 4.3. Establish a Null Contract at the Boundary

If the collection parameter itself cannot be `null`, use `Objects.requireNonNull(input, "input")` to fail fast with a clear parameter name. If **elements** can be `null`, define an explicit policy: reject them, filter them intentionally, or replace them with a business-approved default. Do not automatically convert `null` into `0` or an empty string just to avoid exceptions if those values have different meanings.

Once validation confirms there are no `null`s, `List.copyOf` is a good choice for returning an unmodifiable list. `Optional` works well for an API returning *a single optional value*, but wrapping every element of a collection in `Optional` does not solve an unclear data contract.

## 5. Invalid Data Types: Validate Instead of Casting

### 5.1. Distinguishing Wrong Type from Out-of-Range Values

An API accepting `Integer` scores in the range 0–100 may encounter:

- `"90"`: its Java type is `String`, which cannot be cast directly to `Integer`. If string input is permitted, parse it with `Integer.parseInt` and handle `NumberFormatException` on invalid formats.
- `null`: no value present; requires a `null` policy.
- `120`: valid `Integer` type, but out of range; throw `IllegalArgumentException` with the index and valid range.

Do not mix validation with unchecked casts. When data arrives from CSV/JSON/legacy APIs, accept `Collection<?>` at the outer boundary, validate each element, and then pass only the validated collection to the domain layer.

### 5.2. Complete Validation Example with Tests

Save as `CollectionValidationLab.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.List;
import java.util.Objects;

public class CollectionValidationLab {
    static List<Integer> validatedScores(Collection<?> input) {
        Objects.requireNonNull(input, "input");
        List<Integer> result = new ArrayList<>();

        int index = 0;
        for (Object item : input) {
            if (!(item instanceof Integer score)) {
                String actual = item == null
                        ? "null"
                        : item.getClass().getSimpleName();
                throw new IllegalArgumentException(
                        "index " + index + ": expected Integer, got " + actual);
            }
            if (score < 0 || score > 100) {
                throw new IllegalArgumentException(
                        "index " + index + ": outside 0..100");
            }
            result.add(score);
            index++;
        }
        return List.copyOf(result);
    }

    static void expect(Class<? extends RuntimeException> expected,
                       Runnable action) {
        try {
            action.run();
        } catch (RuntimeException ex) {
            if (expected.isInstance(ex)) {
                return;
            }
            throw new AssertionError(
                    "Expected " + expected.getSimpleName()
                            + " but got " + ex, ex);
        }
        throw new AssertionError(
                "Expected " + expected.getSimpleName() + " but no exception");
    }

    public static void main(String[] args) {
        List<Integer> good = validatedScores(Arrays.asList(80, 90));
        if (!good.equals(List.of(80, 90))) {
            throw new AssertionError("Wrong values");
        }

        expect(NullPointerException.class,
                () -> validatedScores(null));
        expect(IllegalArgumentException.class,
                () -> validatedScores(Arrays.asList(80, null)));
        expect(IllegalArgumentException.class,
                () -> validatedScores(Arrays.asList(80, "90")));
        expect(IllegalArgumentException.class,
                () -> validatedScores(Arrays.asList(80, 101)));
        expect(UnsupportedOperationException.class,
                () -> good.add(95));

        System.out.println("6 checks passed");
    }
}
```

Run with JDK 17+:

```bash
javac CollectionValidationLab.java
java CollectionValidationLab
```

Exact stdout if all checks pass:

```text
6 checks passed
```

One valid-list check and five `expect` calls make up the six checks. The method does not trust element types from the `Collection<?>` input; it verifies that each element is an `Integer`, rejects `null` and numbers outside 0–100 with a clear error message, and returns an unmodifiable `List<Integer>`. A `null` **entire collection** is treated as a required-parameter violation (NPE); a `null` **element** is treated as a data violation (`IllegalArgumentException`). That is a consistently chosen contract, which can be replaced by a domain-specific exception type if project conventions require it.

`expect` does not accept just any exception: the wrong exception type or no exception at all results in an `AssertionError`. Merely calling a function inside `try/catch` without asserting anything easily produces false-positive tests. Never catch a generic `RuntimeException` in business logic and silently continue.

**Important extension:** the example rejects the string `"90"` instead of arbitrarily parsing it. If the system needs to support strings, add that requirement to the contract and test `"90"`, `""`, `"90x"`, strings with whitespace, negative numbers, out-of-range numbers, and formatting issues. Never coerce invalid data into valid data by guessing.

## 6. Related Type Errors That Are Easily Confused

**ArrayStoreException with `toArray`:** calling `List.of(1, 2).toArray(new String[0])` compiles due to the generic signature of `toArray(T[])`, but fails at runtime when copying an `Integer` into a `String[]`. Use `toArray(new Integer[0])` or `toArray(Integer[]::new)`.

**ClassCastException inside a comparator:** a sorted collection whose types were mixed through a raw reference may throw at the comparison site rather than where the element was originally added. Use a comparator typed to match the element/key, and verify `null` handling and ordering rules.

**UnsupportedOperationException with immutable factories:** `List.of("A").add("B")` throws because modification is disallowed. Do not misinterpret this as an invalid element type. `List.copyOf` rejects `null` and disallows modification; those are two distinct contracts.

**ClassCastException is not NumberFormatException:** `(Integer) (Object) "123"` is an invalid cast; `Integer.parseInt("123x")` is a parsing failure. Their fixes are completely different.

## 7. Recommended Testing Matrix

| Scenario | Expectation |
| --- | --- |
| `[80, 90]` | Returns the exact elements, type, and order. |
| `[]` | According to contract: for example, `validatedScores` allows it and returns an empty list. |
| `null` as the input collection | Clear parameter error; the example uses NPE. |
| `[80, null]` | Rejects `null` at index 1. |
| `[80, "90"]` | Rejects `String` type even though the content looks numeric. |
| `[80, 101]` | Rejects out-of-range number. |
| `good.add(95)` | `UnsupportedOperationException` if the result is unmodifiable. |
| Raw `List<String>` containing `Integer` | Reproduces CCE at the read site and identifies the invalid insertion point. |
| `Map` with key mapped to `null` vs. non-existent key | Uses `containsKey` when differentiation is needed. |
| `toArray(new String[0])` from an `Integer` list | `ArrayStoreException` due to incompatible array type. |

In a project configured with JUnit 5/JUnit Jupiter, exception and error-message tests can be written as follows (this is a separate test file and will not compile with plain `javac` unless JUnit is on the classpath):

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.Arrays;
import org.junit.jupiter.api.Test;

class CollectionValidationLabTest {
    @Test
    void rejectsNullElementAtCorrectIndex() {
        IllegalArgumentException ex = assertThrows(
                IllegalArgumentException.class,
                () -> CollectionValidationLab.validatedScores(
                        Arrays.asList(80, null)));
        assertEquals("index 1: expected Integer, got null", ex.getMessage());
    }
}
```

Place the test in the same package as `CollectionValidationLab`, or adjust visibility according to your project structure. For JVM-generated NPE messages, do not depend verbatim on message wording that may vary across versions or runtimes; assert the exception type and the contract defined by your own API.

## 8. Debugging and Prevention Workflow

1. **Read the first exception and stack trace.** Note the operation: `get`, cast, sort, lookup, dereference, unboxing, factory, or `toArray`.
2. **Inspect the data at the failure point.** For non-null values, `value.getClass().getName()` reveals the runtime type; always check for `null` before calling `getClass()`. Log only permitted metadata and avoid exposing sensitive data.
3. **Trace back to where the data entered.** A CCE at `get` typically originates from a raw `add`, an adapter, or an unchecked cast. An NPE on a method call usually comes from a `null` returned by an earlier operation.
4. **Verify the contract.** Is `null` allowed? Which collection allows `null`? What types and value ranges are valid? Is a missing key in `Map.get` normal? Should the returned collection be modifiable?
5. **Fix at an early boundary.** Declare proper generics; perform explicit validation/parsing; report errors with position and cause; produce a validated collection so downstream layers never need to cast again.
6. **Add regression tests.** Test valid inputs, `null`, wrong types, out-of-range values, empty collections, incompatible target arrays, and unmodifiable result behavior.

Do not treat ignoring invalid elements, replacing `null` with `0`, or catching all exceptions and returning an empty list as default solutions. They can hide data loss. If you translate an exception into a higher-level error, preserve the cause (for example, `new IllegalArgumentException("Invalid scores", ex)`).

## 9. Pre-Delivery Checklist

- Collections use explicit generic types, avoiding uncontrolled raw types and unchecked casts.
- Contracts specify `null` rules for the collection itself, individual elements, and map keys/values.
- External data is validated for both type **and** value range before use.
- Casts are not used to parse strings, and CCE is not confused with `NumberFormatException` or `IllegalArgumentException`.
- Sorted collections have properly typed comparators, explicit `null` policies, and consistent ordering.
- Tests assert the exact exception, data, error position, and mutability state; regression tests cover previously encountered bugs.
- When an exception appears at a **read site**, the root cause is still traced back to the **write site**.

**Conclusion:** Generics eliminate many errors at compile time, but collections receiving untrusted data still require runtime validation. Clear null/type contracts, early boundary checks, and targeted tests prevent `ClassCastException` and `NullPointerException` from recurring in complex business workflows.
