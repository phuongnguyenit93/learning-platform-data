# Risk of Mixing Wrong-Typed Data and Late-Surfacing Errors When Using Raw Types in Java Generics

## Learning Objectives

A *raw type* is the name of a generic type used **without providing type arguments**: writing `List` instead of `List<String>`, or `Map` instead of `Map<String, Integer>`. Java still supports this syntax mainly for compatibility with legacy libraries and source code predating generics. However, when using raw types to write data, element-type guarantees can be broken while the program still compiles and keeps running.

After this lesson, you can:

- Distinguish `List<String>`, raw `List`, `List<?>`, and `List<Object>`.
- Explain **heap pollution**: an actual object containing elements that do not match the generic type trusted by another reference.
- Describe why an `add` call can succeed while `ClassCastException` only erupts at a `get` operation, a loop, or a downstream business layer running later.
- Correctly read `rawtypes` and `unchecked` warnings and `checkcast` bytecode.
- Fix API boundaries using parameterized types, purposeful wildcards, element validation, and runtime type-checked collections when truly needed.

## 1. Why Can a Raw Alias Cause Errors to Surface Very Late?

A `List<String>` has a compile-time `String` element contract. If another reference views **the exact same object** as a raw `List`, Java allows calling `add` under the erasure of `List.add(E)`, usually emitting only an unchecked warning:

```java
List<String> cities = new ArrayList<>();
cities.add("Ha Noi");
List rawAlias = cities; // Does not create a copy
rawAlias.add(42);       // Unchecked call
```

This is a snippet inside a method with `java.util.List` and `java.util.ArrayList` imported. Even though `cities` is declared as typed, `rawAlias` inserted an `Integer` element into the shared object. **There is no automatic `String.class` check on raw `ArrayList.add`**. The erroneous behavior is exposed only when a downstream operation specifically demands a `String`.

Quick comparison: `List<?>` preserves reading as `Object` while forbidding arbitrary non-null additions; `List<Object>` is genuinely parameterized with `Object` and does not directly accept `List<String>` due to invariance. The central focus of this lesson is **tracing from the wrong-typed write point to the failing cast site**, rather than merely memorizing the definition of a raw type.

## 2. Core Scenario: Insert the Wrong Type Now, Fail Later

Illustrative example **inside a method**, with appropriate imports:

```java
List<String> cities = new ArrayList<>();
cities.add("Ha Noi");

List raw = cities;
raw.add(42);             // Unchecked call; may succeed at runtime.

String first = cities.get(0);  // "Ha Noi", still valid.
String second = cities.get(1); // ClassCastException when reading Integer as String.
```

The surprising part: at `raw.add(42)`, Java does not automatically throw `ClassCastException` simply because a `List<String>` reference also points to the same object. Raw `List` has method `add(Object)` after erasure; `Integer.valueOf(42)` is also an `Object`, so it can be stored in an ordinary `ArrayList`.

When execution reaches `String second = cities.get(1)`, the program relies on the element being a `String`. The compiler inserts a cast from the `Object` return value of `List.get(int)` to `String`. Because the actual element is an `Integer`, the cast fails **at the read site**, which may be far away from where the wrong-typed data was written.

That is the origin of **delayed failure**: the operation that breaks the invariant occurs at one point in time, while the exception is triggered at a subsequent use requiring a concrete type.

The unsafe call is warned about during compilation, yet **a warning is not a runtime exception**. The compiler still produces class files and the JVM continues running unless you configure your build pipeline to reject warnings.

## 3. Heap Pollution: Why Can Data and Reference Types Contradict Each Other?

*Heap pollution* in Java generics is the situation where a variable of a parameterized type refers to an object that does not match that parameterized type. In the example above:

```text
Actual ArrayList:
index 0 -> String("Ha Noi")
index 1 -> Integer(42)

A trusting reference:
List<String> cities
  └── every element is retrieved to be used as String

A raw reference pointing to the same object:
List raw
  └── add(Object) inserted an Integer

Reading from cities:
get(1) returns Object(Integer)
    ↓
compiler inserts checkcast String
    ↓
ClassCastException
```

Because both references hold **the same object**, you cannot fix the bug merely by renaming the variable or casting the reference:

```java
// Not a fix:
List<String> anotherView = cities;
```

`anotherView` is just another alias seeing the same polluted list. Casting a collection to `List<String>` via an unchecked cast also **does not** scan and verify every element inside.

Several points worth remembering:

1. The bug can stay hidden for a long time if the application reads valid elements first.
2. If code only prints `list.size()` or passes the list through layers without demanding `String`, no exception may occur yet.
3. The error may erupt inside a different service, formatter, mapper, consumer, or loop, leading debuggers to suspect the wrong layer.
4. The site where the type mismatch is detected is usually the compiler-inserted cast at the **read site**, not the raw `add` statement that corrupted the data.
5. Heap pollution does not come only from raw collections: unchecked casts, unsafe generic varargs, and reflection/legacy API boundaries can create similar conditions.

## 4. Complete Java 17 Example: Late Detection and Early Defense

The following program intentionally inserts wrong-typed data through raw `List` to demonstrate delayed failure, then illustrates two safeguards: **validating data when receiving from an untyped source** and **a runtime-checked collection**.

**File `RawTypeRiskDemo.java`:**

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;

public class RawTypeRiskDemo {
    static List<String> validatedCopy(List<?> input) {
        List<String> result = new ArrayList<>();
        for (Object element : input) {
            if (!(element instanceof String text)) {
                String found = element == null
                        ? "null" : element.getClass().getSimpleName();
                throw new IllegalArgumentException(
                        "Expected String, found " + found);
            }
            result.add(text);
        }
        return List.copyOf(result);
    }

    public static void main(String[] args) {
        List<String> cities = new ArrayList<>(List.of("Ha Noi", "Hue"));
        List raw = cities;
        raw.add(42);
        System.out.println("size=" + cities.size());
        System.out.println("first=" + cities.get(0));

        try {
            for (String city : cities) {
                System.out.println("upper=" + city.toUpperCase(Locale.ROOT));
            }
        } catch (ClassCastException exception) {
            System.out.println("late error="
                    + exception.getClass().getSimpleName());
            System.out.println("late frame="
                    + exception.getStackTrace()[0].getMethodName());
        }

        List<?> observed = cities;
        System.out.println("third type="
                + observed.get(2).getClass().getSimpleName());

        try {
            validatedCopy(observed);
        } catch (IllegalArgumentException exception) {
            System.out.println("validation=" + exception.getMessage());
        }
        System.out.println("clean=" + validatedCopy(List.of("Da Nang", "Hue")));

        List<String> guarded = Collections.checkedList(
                new ArrayList<>(), String.class);
        List rawGuarded = guarded;
        rawGuarded.add("Safe");
        try {
            rawGuarded.add(42);
        } catch (ClassCastException exception) {
            System.out.println("guarded error="
                    + exception.getClass().getSimpleName());
        }
        System.out.println("guarded=" + guarded);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac --release 17 RawTypeRiskDemo.java
java RawTypeRiskDemo
```

`javac` may print a note about unchecked/unsafe operations during compilation; this is an intentional consequence of the raw type. Verified **stdout of the `java` command**:

```text
size=3
first=Ha Noi
upper=HA NOI
upper=HUE
late error=ClassCastException
late frame=main
third type=Integer
validation=Expected String, found Integer
clean=[Da Nang, Hue]
guarded error=ClassCastException
guarded=[Safe]
```

Why does the output look exactly like this?

- `raw.add(42)` increases the list size to three elements without throwing an exception yet.
- `cities.get(0)` returns the leading string element, so it still prints `Ha Noi`.
- The loop `for (String city : cities)` processes the first two strings. On the third `Integer` element, the cast to `String` fails. The exception is caught and prints `late error=ClassCastException`; the method containing the cast instruction is `main`.
- `List<?> observed` only reads elements as `Object`, so `observed.get(2).getClass()` sees the runtime class `Integer` without requiring a cast to `String`.
- `validatedCopy` iterates through all elements, checks each one with `instanceof String`, and stops with a meaningful message right at the validation boundary.
- `Collections.checkedList(..., String.class)` creates a **wrapper that checks types on updates through the wrapper**. `rawGuarded.add(42)` throws CCE immediately at the write site, leaving only the valid element `Safe` in `guarded`.

The `validatedCopy` example uses *pattern matching for instanceof*, an official feature in Java 17. `List.copyOf` returns an unmodifiable list and rejects `null`; in this function, `null` is already blocked at the `instanceof` step, so the output contract is a list of non-null Strings only.

**Do not remove the raw statements from the program if you want to reproduce the failure**: the purpose of the example is to demonstrate the risk. When applying this in real applications, replace them with properly generic APIs.

## 5. Why Doesn't the Error Explode Immediately at `add`?

There are three distinct levels:

### 5.1. Contract in source code

With:

```java
List<String> names = new ArrayList<>();
// names.add(42); // Compile error.
```

the compiler understands `names.add(...)` expects a `String` argument. An integer literal 42 is boxed into an `Integer`, which is incompatible with `String`, so the program is rejected at compile time.

### 5.2. Call on a raw type

With:

```java
List raw = names;
raw.add(42); // Unchecked warning.
```

the operation on raw `List` no longer restricts the input to `String`. A standard `ArrayList` stores object references and does not carry a `String.class` check on each insertion. Therefore adding an `Integer` can succeed and pollute the list.

### 5.3. Compiler-inserted cast on read

When reading:

```java
String result = names.get(0);
```

at the bytecode level, `List.get(int)` has a descriptor returning `Object`. The compiler inserts `checkcast String` before assigning to `result`. If the actual element is not a `String`, the JVM throws `ClassCastException` here.

**Core distinction:** erasure does not mean the JVM skips type checks entirely. The JVM still checks **concrete** reference casts; what is lost is the automatic guarantee that a generic collection accessed via a raw type still respects the type arguments of other references.

## 6. Observing Through Compiler Warnings and Bytecode

### 6.1. Enabling relevant warnings

Run:

```bash
javac --release 17 -Xlint:rawtypes,unchecked RawTypeRiskDemo.java
```

Key warnings in the program:

| Site | Warning type | Meaning |
| --- | --- | --- |
| `List raw = cities;` | `[rawtypes]` | A generic type name is used without writing type arguments. |
| `raw.add(42);` | `[unchecked]` | Call to `add(E)` on raw `List`; the compiler cannot prove the data conforms. |
| `List rawGuarded = guarded;` | `[rawtypes]` | Still a raw declaration, even though the actual object is a checked wrapper. |
| `rawGuarded.add(...)` | `[unchecked]` | The compiler cannot verify the raw call is safe; the checked wrapper checks at runtime. |

In the verified run, the lint command above reported five warnings: two rawtypes warnings and three unchecked warnings for `add` calls through raw variables. Warning counts or wording may vary if you edit the program or use a different compiler version.

Difference between the two flags:

- `rawtypes` helps locate places where **generic parameters are omitted**.
- `unchecked` helps locate operations that the compiler **cannot fully verify**, especially calls through raw types and unsafe generic conversions.

An unchecked warning **does not claim the statement will always throw an exception**. It merely says the compiler cannot guarantee safety. `rawGuarded.add("Safe")` still succeeds; `rawGuarded.add(42)` throws CCE due to the checked wrapper.

### 6.2. Inspecting the actual cast site

Compile the program from section 4 and run:

```bash
javap -c -p RawTypeRiskDemo
```

In the bytecode of `main`, look for `invokeinterface java/util/List.get` or `java/util/Iterator.next` and `checkcast java/lang/String` right after retrieving the result from the list.

An equivalent logical sequence:

```text
invokeinterface java/util/Iterator.next:()Ljava/lang/Object;
checkcast java/lang/String
astore ...
```

This is an **illustrative excerpt**; local variable and constant pool indices depend on the compilation. For the verified program, `javap` indeed shows `checkcast java/lang/String` at the read site of `List.get` and inside the loop after `Iterator.next`.

Thanks to this, you can separate:

- **Where was the bug caused?** Raw `add` put an `Integer` into a structure with a `List<String>` contract.
- **Where was the bug detected?** The `checkcast` instruction after reading through the `List<String>` reference.
- **Where does the error appear in the stack trace?** Usually in the method containing the read/cast operation, such as `RawTypeRiskDemo.main` in this program.

When a stack trace reports an error in a data-reading service, do not rush to patch the `get` line with another cast. Trace backward to where elements were added or unvalidated data was accepted.

## 7. Late-Surfacing Errors Across Multiple Application Layers

In real projects, the operation causing heap pollution and the operation detecting it can belong to different layers.

Diagram:

```text
Legacy adapter / unparameterized API
  |
  | writes Integer into a collection assumed to be List<String>
  v
Cache / state / internal DTO
  |
  | passed across multiple methods without reading elements
  v
Business service
  |
  | reads String, applies String::trim / toUpperCase
  v
checkcast String fails
  |
  v
ClassCastException in Service
```

Example with a `Map`:

```java
// Illustrative snippet inside a method:
Map<String, Integer> ages = new HashMap<>();
Map rawAges = ages;
rawAges.put("Mai", "unknown"); // unchecked: String value instead of Integer

Integer age = ages.get("Mai"); // CCE when Object result is cast to Integer
```

Import `java.util.Map` and `java.util.HashMap` if extracting into a standalone program. An ordinary `HashMap` does not validate generic `String, Integer` pairs at runtime. The wrong value is written, and when the caller expects an `Integer`, the cast fails.

If another component only calls `ages.containsKey("Mai")`, it may not encounter any problem yet even though the data is already corrupted. This explains why the stack trace in a reading component does not necessarily point to the source of the bug.

Another case is a legacy API boundary:

```java
// Legacy API, illustrative:
static List fetchLegacyRows() {
    return new ArrayList();
}

// Caller:
// List<String> rows = fetchLegacyRows(); // unchecked conversion
```

At the assignment statement itself, Java does not iterate over each element to verify they are all `String`. If the list contains an element of another type, the failure will occur when the program uses that element as a `String`.

In systems using caches, queues, callbacks, or concurrent execution, the time gap can be even wider. Raw types **are not synonymous with concurrency bugs**; the core issue here remains lost type constraints, regardless of whether multiple threads are involved.

## 8. Wildcards Block New Wrong Writes, Without Cleaning Up Old Heap Pollution

If a component only observes a list of unknown element type, accept `List<?>` instead of raw `List`:

```java
static void reportValues(List<?> source) {
    for (Object value : source) {
        System.out.println(value);
    }
}
```

The method requires importing `java.util.List` and placing it in a class. The wildcard prevents callers of this method from adding an arbitrary `String` or `Integer` **through the `List<?>` reference**. It does not mean `source` is immutable: `clear()` or `remove(index)` is still permitted by the compiler per `List`'s contract, subject to runtime mutability.

In particular, if a raw alias **already** polluted a `List<String>`, switching the view to `List<?>` will not remove the existing `Integer` element. To expose a `List<String>` result, an adapter must validate each element and usually create a copy to isolate aliases.

An API that **actively writes `String`** into a target can accept `List<? super String>`; whereas an API that merely inspects data flow should choose a type that prevents writes outside its responsibility. When reading/writing a concrete list that already has a clear type argument, keep `List<String>` instead of raw so the compiler protects the invariant.

## 9. Validating Data at the Boundary: Fail Fast

Suppose a legacy API returns a `List`, an endpoint returns `Object` data, or a library does not yet provide a suitable generic type. If you cannot immediately fix the source, validate the data **before** exposing it as `List<String>`.

Do not do this:

```java
// Illustrates a dangerous approach; do not use:
@SuppressWarnings("unchecked")
static List<String> trustRaw(List raw) {
    return (List<String>) raw;
}
```

Casting `(List<String>) raw` cannot fully check generic contents at runtime. It can succeed on a list containing `Integer` because erasure only lets the JVM check that the object is a `List`. `@SuppressWarnings("unchecked")` neither fixes the data nor turns that cast into a real check.

Instead, consider the validation pattern from section 4:

```java
static List<String> validatedCopy(List<?> input) {
    List<String> result = new ArrayList<>();
    for (Object element : input) {
        if (!(element instanceof String text)) {
            String found = element == null
                    ? "null" : element.getClass().getSimpleName();
            throw new IllegalArgumentException(
                    "Expected String, found " + found);
        }
        result.add(text);
    }
    return List.copyOf(result);
}
```

This pattern is a method extracted from the complete program and requires importing `List` and `ArrayList`.

It has three useful properties:

1. **Verifies each actual element** instead of merely casting the collection.
2. **Fails at the data-receiving boundary**, with a message naming both expected and actual types.
3. **Creates a new result list**, sharing no alias with the input list; a raw variable holding the input object cannot insert elements into the copy after validation.

This pattern intentionally rejects `null`. If the contract allows `null`, define clear rules, check accordingly, and choose a result collection type that supports `null` (since `List.copyOf` rejects `null`).

If external data must be returned as a multi-level generic structure, checking `instanceof List` only proves the outer structure is a `List`; it does not prove nested elements or key/value pairs have the right types. Validate **to the depth required by the contract**.

## 10. Using `Collections.checkedList` to Catch Bad Data Right at Write Time

The Java Collections Framework provides runtime type-checking wrappers, for example:

```java
List<String> checked = Collections.checkedList(
        new ArrayList<>(), String.class);
```

When a call passes **through the `checked` wrapper**, the wrapper checks the added object against `Class<String>`. In the program:

```java
List rawGuarded = checked;
rawGuarded.add("Safe"); // Succeeds.
rawGuarded.add(42);     // ClassCastException at add through wrapper.
```

This is an illustrative snippet requiring imports for `List`, `ArrayList`, and `Collections`. Calling through a raw type still emits warnings; however, the checked wrapper adds a runtime defense layer so errors are detected **close to where invalid data enters**, rather than lingering until read time.

Important limitations:

- The wrapper only checks operations **going through the wrapper**. If other code still holds a direct reference to the backing list and writes to it, the wrapper cannot block that write.
- Wrapping a list already polluted with wrong elements **does not validate or sanitize existing elements**.
- Checking based on `Class<E>` verifies runtime types representable by a class token, such as `String.class`; it cannot deeply verify types like `List<String>` with just `List.class`.
- Checked wrappers do not replace proper generic design and do not automatically make a collection thread-safe.
- Some collections allow `null`; `null` acceptance and other data constraints must be controlled separately.

When you control the source and all callers, **prefer fixing signatures** to `List<String>` or an appropriate API. Checked wrappers are useful as an extra safeguard at boundaries with legacy/untrusted code.

## 11. Why `List.of` or `List.copyOf` Can Help, and Their Limits

An unmodifiable collection can reduce the risk of wrong data being inserted **after** creation:

```java
List<String> cities = List.of("Ha Noi", "Hue");
```

A raw alias calling `add(42)` on this list cannot add an element either: `List.of`'s implementation is unmodifiable, so mutation throws `UnsupportedOperationException`. However, this is an **immutability** mechanism, not generic validation of an arbitrary list.

In `validatedCopy`, after checking each element, `List.copyOf(result)` produces an unmodifiable result list, preventing other callers from adding elements to that copy. With arbitrary input, merely calling `List.copyOf(someRawList)` and casting the result to `List<String>` **does not prove the elements are String**. If the source collection already holds wrong-typed data, you still need element-by-element validation.

If business logic needs to update the list, a properly typed `List<String>` with controlled sharing/aliasing is usually more practical than imposing inappropriate immutability.

## 12. Guide to Investigating a Late `ClassCastException`

Suppose a stack trace reports an error at:

```java
String label = results.get(index);
```

while most of the code trusts `results` is `List<String>`. Investigate along the causal chain:

1. **Identify the actual type and detection site.** Which type could not be cast to which? If you have `javap`, look for `checkcast String` after `get` or `Iterator.next`.
2. **Inspect actual data at boundaries.** Observe runtime types of elements via `List<?>` and `Object` references, avoiding casting back to `String` during diagnosis.
3. **Find where the collection is created and passed.** List all aliases, mappers, repositories, caches, and legacy APIs that can write into the same object.
4. **Look for raw or unchecked operations near write sites.** Enable `-Xlint:rawtypes,unchecked`. Watch for `List raw = typed`, `Map raw = typed`, unchecked generic casts, and methods returning raw types.
5. **Measure the time gap.** The error may surface only after many processing steps; do not conclude the read line is where data was corrupted.
6. **Fix the offending source.** Prefer eliminating raw types, enforcing consistent generic bounds, and fixing method contracts. If data comes from outside, validate/copy before passing into typed logic.
7. **Add meaningful behavior tests.** Test boundaries with valid values, wrong-typed values, and `null` per contract; ensure detection occurs before data flows deep into the system.

For example, a test should not check only `list.size()` after calling legacy code: a list with three elements can still hold the wrong type. Tests must actually read elements at the expected type or validate data right at the boundary.

### Quick symptom recognition

| Symptom | Likely cause | What to check |
| --- | --- | --- |
| `ClassCastException` at `get`/for-each | Compiler-inserted cast when reading an element | Runtime element at that index and all aliases with write access. |
| `ClassCastException` right at `add` on a checked collection | Wrapper checks elements before writing | Whether input data matches the wrapper's `Class<E>`. |
| `Unchecked call to add(E)` on raw `List` | Compiler cannot verify element type | Replace raw type, or isolate and validate the legacy boundary. |
| `Unchecked conversion` when receiving `List` as `List<String>` | No deep element check | Iterate, validate, and copy before exposing the new type. |
| `ClassCastException` in a service far from list creation | Delayed detection | Trace write/read flows, shared state, and intermediate APIs. |

## 13. Common Wrong Fixes

### Mistake A — Hiding warnings with class-wide `@SuppressWarnings`

`@SuppressWarnings({"rawtypes", "unchecked"})` silences the compiler, yet has no effect on data, casts, or runtime behavior. Applying this annotation to an entire class can mask new bugs introduced later.

If interfacing with legacy APIs is unavoidable, isolate the conversion point, verify everything that can be verified, and limit the annotation to the smallest scope with an accurate explanation.

### Mistake B — Casting the list and believing contents were checked

`(List<String>) raw` can compile with a warning while leaving wrong data inside. Never use that cast in place of a loop validating each element.

### Mistake C — Replacing raw types with `List<Object>` without changing business requirements

`List<Object>` means the list is allowed to hold heterogeneous `Object` values. If business rules require all `String`, that is the wrong contract. It also cannot directly receive every `List<String>` because generics are invariant.

### Mistake D — Assuming no exception on `add` means the data is safe

An ordinary `ArrayList` carries no `String` constraint at runtime. An unchecked warning at `add` is a signal to address even if no exception has happened yet.

### Mistake E — Always applying `String.valueOf` on read

`String.valueOf(42)` can turn a number into `"42"`, but that is a **data conversion rule**, not a type fix preserving the original contract. If business logic genuinely accepts numbers and strings and wants text conversion, model that explicitly. If only genuine Strings are allowed, silent conversion can mask bugs.

### Mistake F — Assuming a checked wrapper guarantees existing inner data is clean

The wrapper only guards operations performed through it, not prior state or direct aliases to the backing collection. Validating pre-existing data remains a separate step.

## 14. Self-Check Exercises

**Exercise 1.** Why does the snippet below compile with a warning, yet fail only on the fourth statement?

```java
List<String> items = new ArrayList<>();
List raw = items;
raw.add(100);
String item = items.get(0);
```

**Answer:** Raw `List` allows calling add with an `Integer` alongside an unchecked warning. `items.get(0)` returns the actual object which is an Integer; where a String is required, the compiler inserted a cast to String and the JVM throws `ClassCastException`.

**Exercise 2.** Does `List<?> view = items` remove an Integer already inserted into `items`?

**Answer:** No. The wildcard only changes operations allowed by the compiler through `view`; it creates no copy and does not validate existing contents.

**Exercise 3.** Given a polluted `List<String>`, does calling `size()` successfully prove the elements have the right type?

**Answer:** No. `size()` does not cast elements to String. Failure can appear later on a concrete read.

**Exercise 4.** When does `Collections.checkedList` help fail fast?

**Answer:** When element additions pass through the wrapper. With a wrapper expecting String, adding an Integer is rejected at the write call instead of waiting for a read through a typed reference.

**Exercise 5.** Should you fix it with `@SuppressWarnings("unchecked")` or `(List<String>) raw`?

**Answer:** No. They do not validate elements. You need proper generic APIs or element-by-element validation at boundaries.

**Exercise 6.** A `Map<String, Integer>` has a String value inserted via raw `Map`. Why might `containsKey` work fine while `Integer n = map.get(key)` throws?

**Answer:** `containsKey` only checks keys and does not force values to be Integer. When `get` returns the Object value to a caller expecting Integer, the compiler inserts a cast and an exception can occur.

## 15. Key Takeaways

**The biggest risk of raw types is not merely losing signature clarity, but breaking the generic contract of a shared object so that errors surface late elsewhere.** A raw `add` call may only emit a warning and write wrong data; `ClassCastException` appears when typed code must use the value as its expected type.

Prefer proper generics across all APIs, use wildcards when only observing an unknown type, deeply validate legacy data before granting a stronger contract, and consider checked collections at boundaries needing runtime defense. When debugging, trace **warning/unchecked write → heap pollution → read requiring cast → ClassCastException** to locate the true offending source.