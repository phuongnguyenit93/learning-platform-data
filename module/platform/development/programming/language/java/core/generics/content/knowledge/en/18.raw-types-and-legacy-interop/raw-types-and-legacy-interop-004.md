# Converting from Raw Types to Parameterized Types and Handling `unchecked` Warnings in Java Generics

## 1. Learning Objectives

A **raw type** is the use of a generic type name while omitting its type arguments. For example, `List` is the raw type of `List<E>`; `Map` is the raw type of `Map<K,V>`. Raw types mainly exist so legacy Java code written before generics can continue interacting with newer APIs.

When maintaining an application, you often encounter:

```java
List names = new ArrayList();
names.add("Lan");

List<String> typed = names; // Unchecked conversion warning
```

The program can compile, yet the compiler cannot prove that every element in `names` is a `String`. The migration task is more than just adding `<String>` to a few declarations: you must determine the **actual data**, **intended type**, **read/write flows**, and **legacy boundaries**.

After this lesson, you can:

- Distinguish raw types, `List<?>`, `List<Object>`, and `List<String>`.
- Read `[rawtypes]` and `[unchecked]` warnings, especially *unchecked conversion*, *unchecked call*, and *unchecked cast*.
- Systematically migrate declarations, parameters, return types, and utility methods to generics.
- Recognize *heap pollution* and why `ClassCastException` can appear later than the warning site.
- Use `Class<T>` and element-by-element validation to move legacy data into structures with guaranteed types.
- Isolate unavoidable uses of `@SuppressWarnings("unchecked")` with proof of invariants instead of hiding warnings in bulk.

The main examples use Java 17+, compiled and run to compare both warnings and outputs.

## 2. What Does a Raw Type Actually Lose?

A parameterized collection:

```java
List<String> names = new ArrayList<>();
names.add("Java");

// names.add(17); // Compile error: int/Integer is not compatible with String.
String first = names.get(0);
```

The `String` type parameter is a **compile-time contract**: callers may only add compatible values, and reads yield `String` without writing manual casts.

The raw form:

```java
List names = new ArrayList();
names.add("Java");
names.add(17); // Compiler may emit an unchecked call warning.
```

allows `add` calls with different types because `List<E>` is used without a concrete `E`. This is **not** a type-safe list for holding arbitrary kinds of objects. It simply drops much of generic checking at the use site.

Assignments between raw and generic types can be permitted by the compiler for backward compatibility, though with warnings:

```java
List raw = new ArrayList();
List<String> strings = raw; // Unchecked conversion.
```

The assignment **does not scan or convert elements**. If `raw` contains an `Integer`, reading a `String` elsewhere can throw `ClassCastException`.

### 2.1. Differences among `List`, `List<?>`, and `List<Object>`

| Type | Type contract | Reading elements | Adding elements |
| --- | --- | --- | --- |
| `List` | Raw; no type argument for full compiler checks | Usually as `Object` | Can call `add` with different objects, producing unchecked warnings |
| `List<?>` | List with an **unknown** element type, still valid generic form | Read as `Object` | Cannot add elements other than `null` through that reference |
| `List<Object>` | List with element type `Object` | Read as `Object` | Can add many kinds of objects |
| `List<String>` | List with `String` elements | Read as `String` | Add `String` or `null`, depending on data policy |

A `List<String>` can be viewed as `List<?>`:

```java
List<String> strings = List.of("a", "b");
List<?> unknown = strings;
Object first = unknown.get(0);
```

However, it **cannot** be arbitrarily assigned to `List<Object>`:

```java
// List<Object> values = strings; // Compile error: generics are invariant.
```

Even though `String extends Object`, `List<String>` is not a subtype of `List<Object>`. Therefore, replacing every raw `List` with `List<Object>` can give APIs the wrong semantics or break compilation for callers. When you only need to observe a list of unknown element type, `List<?>` is usually more suitable.

### 2.2. Raw types differ from wildcards

`List<?>` retains generic type checking. The compiler prevents you from adding a value incompatible with the unknown element type.

```java
static int count(List<?> list) {
    return list.size();
}
```

A method that only counts does not need its own type parameter. If a method must **preserve a type relationship** between input and output, use a generic method:

```java
static <T> T first(List<T> list) {
    return list.get(0);
}
```

`List<?>` cannot replace every `<T>` method: wildcards express "the element type does not matter / is unknown"; a type variable `T` expresses "these positions must share the same type".

## 3. Three Common Warning Types

Compile with these `javac` options:

```bash
javac --release 17 -Xlint:rawtypes -Xlint:unchecked YourFile.java
```

Replace `YourFile.java` with your source file name. `-Xlint:rawtypes` requests warnings when raw types are used inappropriately; `-Xlint:unchecked` enables warnings for operations that cannot be fully type-checked in the generics system. Exact warning text, line numbers, and formatting may vary by JDK version.

### 3.1. `[rawtypes] found raw type`

Example:

```java
List values = new ArrayList();
```

The compiler sees that both generic types `List<E>` and `ArrayList<E>` are used without type arguments.

If every element is truly a string:

```java
List<String> values = new ArrayList<>();
```

If the element type is currently unknown and only read:

```java
void inspect(List<?> values) {
    for (Object value : values) {
        System.out.println(value);
    }
}
```

Switching to `List<?>` avoids exposing uncontrolled `add(Object)` capability. However, do not force an object that genuinely needs content updates into a read-only API when business logic still requires writes.

### 3.2. `[unchecked] unchecked call to add(E)`

Example:

```java
List raw = new ArrayList();
raw.add(123);
```

With a raw receiver, the compiler has no concrete `E` type to validate the argument to `add`. An `unchecked call` warning indicates **a call to a generic member through a raw type**.

If the list must hold integers:

```java
List<Integer> integers = new ArrayList<>();
integers.add(123);
```

Change a declaration from `List` to `List<Integer>` only when it holds true for **every write path**, including functions receiving aliases of the same list. A list already populated with incompatible types from multiple places must have its data flow fixed, split into domain models, or validated/converted element by element.

### 3.3. `[unchecked] unchecked conversion`

Example:

```java
List raw = new ArrayList();
List<String> strings = raw;
```

The assignment is allowed for backward compatibility, but the compiler cannot prove each element is a `String`. It does not automatically validate elements and does not "sanitize" the collection.

Also watch out for return types or parameters of legacy methods:

```java
static List loadLegacy() {
    return new ArrayList();
}

// ...
List<String> names = loadLegacy(); // Unchecked conversion.
```

Changing only the receiving variable to `List<String>` merely pushes the warning to the usage boundary. If you do not control the implementation of `loadLegacy`, transfer data into a new list by validating each element.

### 3.4. `[unchecked] unchecked cast`

Example:

```java
Object value = new ArrayList<String>();
List<String> names = (List<String>) value;
```

Casting to `List<String>` cannot verify the **type argument** `String` via the object's runtime class. The runtime can check that the object is a `List`, but cannot verify a generic specialization like `List<String>`.

Especially dangerous:

```java
List raw = List.of(123);
List<String> wrong = (List<String>) raw;
String text = wrong.get(0); // May throw ClassCastException.
```

None of the statements above check **each element** before creating `wrong`. Completing the cast without throwing does not prove the list has the right element type.

## 4. Why Must `unchecked` Warnings Be Fixed?

### 4.1. Heap pollution

*Heap pollution* occurs when a variable of a parameterized type holds a reference to an object that does not conform to the declared parameterized type. Raw aliases or unchecked operations can create this situation.

Controlled failure example, file **`RawWarningDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class RawWarningDemo {
    public static void main(String[] args) {
        List<String> typed = new ArrayList<>();
        List raw = typed;
        raw.add(123);

        try {
            String value = typed.get(0);
            System.out.println(value);
        } catch (ClassCastException e) {
            System.out.println("ClassCastException");
        }
    }
}
```

Run:

```bash
javac --release 17 -Xlint:rawtypes -Xlint:unchecked RawWarningDemo.java
java RawWarningDemo
```

`javac` reports main warnings at `List raw = typed` (raw type) and `raw.add(123)` (unchecked call). The program **still compiles**, and stdout is:

```text
ClassCastException
```

Sequence of events:

1. An `ArrayList<String>` is created through a typed reference.
2. The raw alias `raw` points to **the same object**, without creating a copy.
3. `raw.add(123)` inserts an `Integer` into a list that other code trusts contains only `String`.
4. `typed.get(0)` is seen by the compiler as a `String` expression; checking/casting to `String` happens on the read result and fails.

An unchecked warning at the write site is an early warning for a later runtime failure. Ignoring the warning does not mean wrong elements were automatically removed.

### 4.2. Type erasure does not remove compile-time checks

In the JVM, `List<String>` and `List<Integer>` usually share the same runtime class such as `ArrayList`. Yet before execution, `javac` still analyzes type arguments to prevent inserting an `Integer` via a `List<String>` variable.

Raw types create an "unprotected zone" at compile time; casts generated by the compiler on read can expose failures later. Do not infer that erasure makes Generics useless: the compile-time checks bypassed by raw/unchecked operations are precisely what you want to restore during migration.

## 5. Handling Warnings by Source of Lost Type Guarantees

When gradually upgrading a method from raw to generic, **distinguish the specific warning before deciding how to fix the code**:

| Symptom | Source of risk | Preferred fix step |
| --- | --- | --- |
| `List raw`, `new ArrayList()` | Omitted type arguments | Use `List<T>`, `List<?>`, or a concrete type matching the data |
| `raw.add(value)` | Invocation through a raw receiver | Move write paths to a typed API where data is owned |
| `List<String> x = raw` | Unchecked conversion | Verify incoming data or prove the invariant from creation site |
| `(List<String>) object` | Unchecked cast | Check each element; do not assume casts check type arguments |
| `@SuppressWarnings("unchecked")` | Only hides the warning | Keep solely on a small helper with rationale and tests |

For example, fixing `List<String> names = legacy.load()` with a suppressed cast does not ensure the new list holds only strings. An adapter `checkedCopy(List<?>, Class<T>)` can verify the element class and create a typed snapshot; consider `null` handling and source mutation.

After isolating warnings, run `javac -Xlint:rawtypes,unchecked`, test behavior with mixed data, and observe **where failures are detected**. This section focuses on **proving unchecked conversions safe**; multi-module migration, changing public contracts, and preserving binary compatibility require separate planning, not annotations.

## 6. Converting Raw Collections via a Data-Validating Adapter

If the source is a raw `List`, instead of an unchecked cast, you can check **each element** to build a new collection. Use `Class<T>` as a runtime type token for the concrete element type, such as `String.class` or `Order.class`.

Method:

```java
static <T> List<T> validatedCopy(List<?> input, Class<T> elementType) {
    List<T> result = new ArrayList<>();
    for (Object item : input) {
        result.add(elementType.cast(item));
    }
    return List.copyOf(result);
}
```

This approach has several properties:

- `List<?>` can accept references to many different `List` instances without requiring callers to assume all elements already share a concrete type.
- `Class<T>.cast(item)` checks **each element** against the runtime class; any mismatch throws `ClassCastException`.
- If iteration succeeds, `result` is newly created with type `List<T>` built from verified values.
- `List.copyOf(result)` returns a list unmodifiable via normal update methods and **rejects `null` elements**; if the source contains `null`, creating this copy throws `NullPointerException`.
- This is a **shallow copy**: if elements are mutable objects, those elements themselves are not deep-copied.

For nested generic types like `List<List<String>>`, `Class<List<String>>` is not normally represented by a single runtime `Class` capable of checking the entire type argument. Using `Class<List>` checks only that outer elements are `List`, **without checking the strings inside the nested lists**. To guarantee nested structures, validate recursively or use a dedicated parser/schema representing the full structure.

### 6.1. Why cannot `instanceof List<String>` be used?

You cannot write:

```java
// Does not compile:
if (value instanceof List<String>) {
}
```

Because the type argument `String` is not reifiable. You can check:

```java
if (value instanceof List<?> list) {
    System.out.println(list.size());
}
```

However, that check **only** proves `value` is a `List`, not that its elements are `String`. To promote it to `List<String>`, you still must check every value.

### 6.2. When normalization is needed instead of mere validation

If `legacy()` has inconsistent data, you may want to **convert** according to business rules rather than throwing. For example, an ID field might arrive as either an integer or a string, and converting everything to `String` requires clear rules:

- Which numbers are allowed to convert into text IDs?
- Does `null` mean missing data or a valid value?
- If an unexpected object appears, should it be skipped, logged as an error, or abort the whole operation?
- Must ordering and duplicates be preserved?

Do not blindly call `.toString()` on every element: the result may be a meaningless string that hides input data errors.

## 7. Complete Java 17 Program to Practice Migration

Create file **`MigrationDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class MigrationDemo {
    static List legacyNames() {
        List values = new ArrayList();
        values.add("Lan");
        values.add("Minh");
        return values;
    }

    static <T> List<T> validatedCopy(List<?> input, Class<T> elementType) {
        List<T> result = new ArrayList<>();
        for (Object item : input) {
            result.add(elementType.cast(item));
        }
        return List.copyOf(result);
    }

    static <T> void copy(List<? extends T> source, List<? super T> target) {
        for (T item : source) {
            target.add(item);
        }
    }

    public static void main(String[] args) {
        List<String> names = validatedCopy(legacyNames(), String.class);
        System.out.println("names=" + names);

        List<Number> numbers = new ArrayList<>();
        copy(List.of(3, 5), numbers);
        System.out.println("numbers=" + numbers);

        List<?> unknown = List.of("A", 10);
        System.out.println("unknown-size=" + unknown.size());

        try {
            validatedCopy(List.of("OK", 99), String.class);
        } catch (ClassCastException e) {
            System.out.println("invalid=" + e.getClass().getSimpleName());
        }
    }
}
```

Compile:

```bash
javac --release 17 -Xlint:rawtypes -Xlint:unchecked MigrationDemo.java
```

`javac` emits warnings from **only the legacy method** `legacyNames()`:

```text
[rawtypes] found raw type: List
[rawtypes] found raw type: List
[rawtypes] found raw type: ArrayList
[unchecked] unchecked call to add(E) as a member of the raw type List
[unchecked] unchecked call to add(E) as a member of the raw type List
```

These are **warning identification lines**, extracted from compiler output; file locations, caret lines, and bound descriptions are omitted from the excerpt because they depend on file positions. With the source above and `javac --release 17`, the compiler reported **5 warnings**. There are no unchecked warnings from `validatedCopy` or `copy`: both use generics properly according to their contracts.

Run:

```bash
java MigrationDemo
```

Exact stdout:

```text
names=[Lan, Minh]
numbers=[3, 5]
unknown-size=2
invalid=ClassCastException
```

Explanation:

- `legacyNames()` simulates old code that still uses raw types; new logic does not immediately trust that returned data has the right type.
- `validatedCopy(..., String.class)` iterates over the source, casts each element, and returns a new list with declared type `List<String>`.
- `copy` uses data-flow direction: source `List<? extends T>` for **reading**, target `List<? super T>` for **writing**. With a `List<Integer>` source and `List<Number>` target, copying is valid.
- `List<?> unknown` can hold values inferred with an unknown element type; here only `size()` is read, so no raw type is needed.
- The attempt with `"OK", 99` is rejected by the adapter at the `Integer` element, **before** a corrupted list is handed to the caller as a `List<String>`.

### 7.1. Next migration step when you own the legacy API

Once you know and verify that `legacyNames()` returns only strings, if you **own** its source, you can replace the raw part with:

```java
static List<String> names() {
    List<String> values = new ArrayList<>();
    values.add("Lan");
    values.add("Minh");
    return List.copyOf(values);
}
```

If all writers already preserve the right type, caller code becomes cleaner:

```java
List<String> names = names();
```

When the data source boundary truly has no raw types and no wrong-typed write paths, the element-checking adapter may no longer be needed. Do not hastily delete the adapter if data still comes from third parties, reflection, file imports, serialization, or APIs returning unverified `Object`.

### 7.2. Verifying both compile time and runtime

A **warning-free** program can still contain business logic bugs; conversely, an old project with warnings does not mean every call is failing. For solid migration evidence, you need both:

- Compilation with `-Xlint:rawtypes -Xlint:unchecked`.
- Tests for valid inputs, wrong-typed inputs, empty data, and `null` if the API allows it.
- Checking callers of any method whose signature changed.
- Verifying that type invariants still hold when aliases or external code mutate data.
- Comparing return behavior: mutable vs. immutable list, element ordering, duplicate handling, and `null` acceptance.

`List.copyOf` in the program produces an unmodifiable result and rejects `null`. If the legacy contract requires mutability or allows `null`, choose a suitable copy rather than treating this as a drop-in equivalent.

## 8. Migrating Legacy Method Signatures and Classes

### 8.1. Changing a read-only method

Before:

```java
static void logAll(List values) {
    for (Object value : values) {
        System.out.println(value);
    }
}
```

After:

```java
static void logAll(List<?> values) {
    for (Object value : values) {
        System.out.println(value);
    }
}
```

The method does not modify the list and does not require knowing the element type. Using `List<?>` forms a clearer input contract than `List<Object>`, because both `List<String>` and `List<Integer>` can be passed in.

### 8.2. Changing a method that must preserve type

Before:

```java
static Object first(List values) {
    return values.get(0);
}
```

After:

```java
static <T> T first(List<T> values) {
    return values.get(0);
}
```

Callers benefit from type inference:

```java
String name = first(List.of("Java"));
Integer number = first(List.of(7));
```

Now the `T` relationship between parameter and result is preserved right in the signature. If the input is still a raw `List`, the caller can still trigger warnings; fixing only the helper is not enough to prove every source value.

### 8.3. Changing a stateful class

Before:

```java
class OldHolder {
    private Object value;

    Object get() {
        return value;
    }

    void set(Object value) {
        this.value = value;
    }
}
```

If the class needs to support many value types while each instance holds one specific type:

```java
class Holder<T> {
    private T value;

    T get() {
        return value;
    }

    void set(T value) {
        this.value = value;
    }
}
```

Usage:

```java
Holder<String> holder = new Holder<>();
holder.set("hello");
String result = holder.get();
```

This pattern eliminates manual casts on read. However, do not generify a class when the real domain model needs a heterogeneous aggregate of different value types with distinct processing rules. In that case, use a domain interface, a sealed hierarchy, or explicit records.

### 8.4. Generic API at a library boundary

Suppose code consumes a legacy library:

```java
List loadFromLibrary(); // Legacy signature; cannot be modified directly.
```

If the external API does not check type arguments, add an adapter in code you control:

```java
static List<String> readNamesSafely(List<?> incoming) {
    List<String> names = new ArrayList<>();
    for (Object item : incoming) {
        if (!(item instanceof String name)) {
            throw new IllegalArgumentException(
                    "Expected a String name, got: " + item);
        }
        names.add(name);
    }
    return names;
}
```

When writing this method as standalone source, import `java.util.List` and `java.util.ArrayList`. `instanceof String name` is pattern matching syntax available in Java 17. In this example `null` also fails `instanceof String`; throwing on it is intentional.

The adapter ensures other parts of the codebase see only `List<String>`, yet **does not force the legacy library to become type-safe**. If the library continues mutating the same list, returning a copy after validation isolates the new object from the source alias.

## 9. Using Wildcards for Producers and Consumers

When migrating raw APIs, many cases require type variables and wildcards rather than turning every parameter into the same `List<T>`.

A method that only reads elements from a source:

```java
static double total(List<? extends Number> numbers) {
    double sum = 0;
    for (Number number : numbers) {
        sum += number.doubleValue();
    }
    return sum;
}
```

Accepts `List<Integer>`, `List<Double>`, and compatible subtypes of `Number`. The source is a **producer**, so `? extends Number` makes sense.

A method that only adds integers to a target:

```java
static void seed(List<? super Integer> target) {
    target.add(1);
    target.add(2);
}
```

Can be called with `List<Integer>`, `List<Number>`, `List<Object>`; the target is a **consumer**, so `? super Integer` fits.

With the `copy` method from the runnable program:

```java
static <T> void copy(
        List<? extends T> source,
        List<? super T> target) {
    for (T item : source) {
        target.add(item);
    }
}
```

The `T` relationship between source and target cannot be fully expressed with two independent `List<?>` parameters if elements must be transferred without casts. The **PECS** (*Producer Extends, Consumer Super*) rule is a great post-migration design tool, but apply it based on actual read/write needs rather than reflexively replacing every raw `List` with wildcards.

## 10. When Can `@SuppressWarnings("unchecked")` Be Used?

Some legacy APIs, reflection, or serialization force casts where the compiler cannot fully verify type arguments. When no viable alternative exists, you can narrowly scope suppression:

```java
@SuppressWarnings("unchecked")
static <T> List<T> uncheckedBoundary(Object input) {
    return (List<T>) input;
}
```

**This is only a syntax illustration**, not a safe adapter. The method itself does not verify that `input` is genuinely a `List<T>`; it can even fail if input is not a `List`. Do not copy this method into production and assume the warning is solved.

Conditions for considering responsible suppression:

1. Prove the invariant that the compiler cannot prove (for example, the object is created locally and **every write path** through aliases is controlled).
2. Place suppression at the **smallest possible scope**: a local variable or a small dedicated method, avoiding suppression across an entire class or package.
3. Document the source guaranteeing the type, what data was checked, and what could break the invariant.
4. Write tests with both valid and invalid-typed inputs, especially when untrusted data or external aliases exist.
5. Prefer copy-building adapters with element checks whenever possible, as they provide clear runtime proof.

`@SuppressWarnings("rawtypes")` likewise only hides raw-type warnings. Suppressing `rawtypes` or `unchecked` **adds no type checks** and fixes no invalid data.

### 10.1. What does `Collections.checkedList` help with?

Java provides a wrapper that checks elements on write:

```java
List<String> checked =
        java.util.Collections.checkedList(new ArrayList<>(), String.class);
```

The wrapper checks element-adding operations **that go through the wrapper itself**. If raw code tries to add an invalid value through the wrapper, the runtime can throw `ClassCastException` at the write site.

Important limitations:

- The wrapper does not automatically scan or fix existing elements when created.
- If a direct alias to the backing list exists, writes through that alias bypass the wrapper's checks.
- It does not replace designing proper public generic signatures and eliminating raw aliases.
- With nested type arguments, `Class<T>` still does not verify the full nested generic element structure.

Use the wrapper when you need a runtime safeguard on legacy write paths; when you need **clean data at output**, an element-validating copy adapter is usually clearer.

## 11. Common Migration Mistakes

### Mistake 1 — Replacing raw with `List<Object>` everywhere

`List<Object>` cannot accept `List<String>` via ordinary assignment. If a method only observes arbitrary data, use `List<?>`. If a type relationship between input and output is needed, use `<T>`.

### Mistake 2 — Adding `@SuppressWarnings` before understanding the warning

Suppression quiets build output without changing data or write permissions. An unchecked warning usually signals a **boundary where type checking was lost**; address that boundary with parameterized types or validation.

### Mistake 3 — Casting `List<?>` to `List<String>` and treating it as validated

Casting does not check each element. Checking `value instanceof List<?>` also verifies only the collection type. To get a truly clean `List<String>` from untrusted data, iterate and validate elements.

### Mistake 4 — Assuming a raw alias creates a copy

```java
List<String> strings = new ArrayList<>();
List raw = strings;
```

Both variables point to one list. Writes through the raw alias can break the contract of `strings`. If you need isolation from legacy data, create a copy **after** validating values.

### Mistake 5 — Fixing only the receiving variable while ignoring the producer

Changing `List names = legacy()` to `List<String> names = legacy()` may merely convert the issue into an unchecked conversion. Update the producer signature if you own the code, or use an adapter at the boundary if you do not.

### Mistake 6 — Forgetting null, mutability, and ordering

A copy created with `List.copyOf` is unmodifiable and rejects `null`. If legacy data contains `null` or callers expect a mutable list, migration can change runtime behavior even though type safety improved. Document the output contract before migrating.

### Mistake 7 — Confusing `unchecked` with hard generic compile errors

Some type mismatches are not merely warnings:

```java
List<String> texts = new ArrayList<>();
// texts.add(10); // Compilation error.
```

The compiler rejects this because it knows the concrete type argument. By contrast, a raw call can proceed after a warning. Distinguishing errors from warnings helps prioritize fixes and avoid "patching" with unnecessary casts.

### Mistake 8 — Forgetting APIs receiving/passing data via generic methods

When changing signatures, inspect related method references, lambdas, overloaded methods, overrides, and serialization boundaries. A raw signature may have accidentally allowed heterogeneous values; after migration, code will expose violations of an under-specified legacy contract.

## 12. Final Verification Checklist When Completing Migration

| Question | Expected evidence |
| --- | --- |
| Which exact element type does the collection hold? | API contracts, producer, and all writers reviewed. |
| Are any raw types still necessary? | Remaining only at identified and documented legacy boundaries. |
| Are any unchecked conversions/casts/calls left? | `javac -Xlint:rawtypes -Xlint:unchecked` output is clear; remaining warnings are isolated. |
| If data enters from outside, who checks elements? | Runtime validating adapter or dedicated parser/schema. |
| Can an alias write wrong types into the collection? | Ownership/copy flow or wrapper verified. |
| Do null, mutability, and ordering still match the contract? | Unit/integration tests on migrated APIs. |
| Do callers receive the right return type? | All affected modules and consumers compile cleanly. |
| Does every suppression have a provable invariant? | Comment near cast, minimal scope, tests with wrong-typed data. |

A practical workflow is fixing **from producer to consumer**, ensuring every data entry point has a verified contract before removing manual casts from business logic. When an API must remain compatible with legacy callers, organizing migration boundary by boundary keeps changes safe and easy to review.

## 13. Self-Check Exercises

**Exercise 1.** Does the snippet below actually validate every element of `strings`?

```java
List raw = List.of(1, 2);
List<String> strings = raw;
```

<details>
<summary>Answer</summary>

No. There is an unchecked conversion; no element was converted to `String`. When reading an element as `String`, `ClassCastException` can occur. If the source is untrusted, validate/copy each element or fix the producer.

</details>

**Exercise 2.** A method only accepts a list to print its size; should it use `List`, `List<Object>`, or `List<?>`?

<details>
<summary>Answer</summary>

Use `List<?>`: it accepts a list of any element type, keeps generic type checking, and forbids inserting arbitrary values through this reference. `List<Object>` restricts `List<String>` callers; raw `List` drops type checking.

</details>

**Exercise 3.** Why can a warning at `raw.add(123)` cause a failure when another method reads `typed.get(0)`?

<details>
<summary>Answer</summary>

`raw` and `typed` can be two aliases of the same collection. The raw add bypasses generic checks, creating data that violates the `List<String>` assumption. When reading the element and casting to `String`, the runtime discovers the actual type is `Integer`.

</details>

**Exercise 4.** Given a `List<?>` from an external API, can `instanceof List<String>` be used to check it?

<details>
<summary>Answer</summary>

No. `List<String>` is not a reifiable type. You can verify the object is a `List<?>`, then use `Class<String>` or `instanceof String` to validate each element when building a new `List<String>`.

</details>

**Exercise 5.** Does `@SuppressWarnings("unchecked")` make a cast safe?

<details>
<summary>Answer</summary>

No. The annotation only hides the compiler warning. Safety must rely on a proven invariant or an actual runtime check. Prefer a validating adapter when data might have the wrong type.

</details>

## 14. Key Takeaways

Converting raw types to parameterized types means **restoring the type contract from where data is created to where it is used**. `rawtypes` tells you a type argument is missing; `unchecked` tells you the compiler cannot prove a call, assignment, or cast is type-safe. Zero warnings do not replace testing, and merely hiding warnings does not fix the data contract.

For source you control, explicitly declare `List<T>`, `Map<K,V>`, and appropriate `<T>` methods. For legacy sources without data guarantees, use `List<?>`, validate **each element**, and create a new collection with a concrete type. Isolate unchecked casts only when invariants are proven and truly cannot be eliminated.