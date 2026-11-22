# When Arrays of `List<?>` Can Be Validly Created in Java Generics

## 1. The Core Question

In Java, you cannot directly create an array with component type `List<String>`:

```java
// Does not compile:
List<String>[] strings = new List<String>[3];
```

Yet the following snippet **is valid**:

```java
List<?>[] groups = new List<?>[3];
```

Why do both involve Generics, yet only the second expression is allowed? The answer is **reifiable types** (*types that can be represented at runtime*) and the JVM's array component type-checking mechanism.

`List<?>` is a parameterized type in which **all type arguments are unbounded wildcards**. Under Java's rules, this type is **reifiable**, meaning it qualifies as the component type of an array allocation expression `new List<?>[n]`. Conversely, `List<String>` and `List<? extends Number>` are non-reifiable: the JVM cannot verify those specific type arguments in an array component check.

This lesson explains precisely:

- Why `new List<?>[n]` is accepted by Java.
- What the array actually remembers at runtime and what `List<?>[]` allows reading/writing.
- The differences among `List<?>[]`, raw `List[]`, `List<String>[]`, and `List<List<String>>`.
- Risks of covariance, `Object[]` aliases, unchecked casts, and heap pollution.
- How to choose data structures and validate elements when an application requires concrete types.
- How to compile, run, and interpret `generic array creation` errors on Java 17.

The goal is not to find tricks to bypass the compiler, but to understand **why an array of lists with unknown element types is valid**, and the limits of that guarantee.

## 2. Recap: Array Types and Generic Types Are Checked Differently

A Java array has a **runtime component type**. For example:

```java
String[] names = new String[2];
```

The JVM knows the created object is `String[]`, regardless of whether it is referenced through a `String[]`, `Object[]`, or `Object` variable. If code attempts to write an `Integer` via an alias:

```java
Object[] alias = names;
alias[0] = 42; // ArrayStoreException at runtime
```

the runtime blocks the write because `Integer` is incompatible with the true component type `String`.

However, generic collections do not have a separate runtime class per type argument:

```java
List<String> words = new ArrayList<>();
List<Integer> numbers = new ArrayList<>();
```

Both objects created with `new ArrayList<>()` share the same runtime class `ArrayList`; the type arguments `String` and `Integer` are used by the compiler to check source code, not turned into a specialized runtime class per object.

From this arises the question: if the JVM only sees runtime `List`, how could it check every element of an array declared as `List<String>[]`? It cannot verify every `String` in those lists via an array store check. Therefore, Java forbids directly allocating arrays with **non-reifiable** generic component types.

### 2.1. Comparing Arrays and Collections

| Property | `String[]` | `List<String>` |
| --- | --- | --- |
| Component/argument type in source code | `String` | `String` |
| Does the runtime have a dedicated object class representing `String`? | Yes: the array class carries component `String` | No separate `List<String>` specialization |
| Are writes through a wider alias checked at runtime? | Yes, may throw `ArrayStoreException` | No store check by type argument; a raw alias can cause heap pollution |
| Type relationship | Reference arrays are covariant | Java generics are normally invariant |
| Checking an object against the corresponding type | `instanceof String[]` is valid | From `Object`, `instanceof List<String>` cannot be used to check runtime type arguments |
| What error can occur when reading the wrong type? | Array store check usually blocks bad data right at write time | `ClassCastException` can surface when reading polluted data |

This is why you cannot mechanically apply every rule of `List<T>` to `T[]`.

## 3. Reifiable Types Determine the Validity of `new List<?>[n]`

In Java, typical reifiable types include:

1. Primitives such as `int` and `boolean`.
2. Non-generic classes/interfaces such as `String` and `Runnable`.
3. Raw types such as `List` and `Map`.
4. Parameterized types in which **all arguments are unbounded wildcards `?`**, such as `List<?>` and `Map<?, ?>`.
5. Arrays whose component type is reifiable, such as `String[]`, `List<?>[]`, and `List<?>[][]`.

Because `List<?>` belongs to group 4, `List<?>[]` belongs to group 5. Therefore:

```java
List<?>[] groups = new List<?>[3]; // Valid
```

The compiler can emit an array creation operation with runtime component class `java.util.List`. There is no need to verify `String`, `Integer`, or any concrete subtype for the type argument because `?` **does not promise a specific type argument**.

Conversely:

```java
// Invalid:
List<String>[] words = new List<String>[3];

// Invalid:
List<? extends Number>[] numbers = new List<? extends Number>[3];

// Invalid inside a generic method/class:
T[] values = new T[3];
```

The three component types `List<String>`, `List<? extends Number>`, and `T` are non-reifiable. Merely having `?` inside a type **is not enough**: it must be an unbounded wildcard under the conditions of reifiability.

### 3.1. Classification Table

| Array creation expression | Compiles? | Reason |
| --- | --- | --- |
| `new String[3]` | Yes | `String` is reifiable |
| `new Object[3]` | Yes | `Object` is reifiable |
| `new List[3]` | Yes, may warn `rawtypes` | Raw `List` is reifiable |
| `new List<?>[3]` | Yes | `List<?>` is reifiable |
| `new Map<?, ?>[3]` | Yes | All type arguments are wildcard `?` |
| `new List<?>[2][4]` | Yes | Leaf component `List<?>` is reifiable |
| `new List<String>[3]` | No | Argument `String` is not `?` |
| `new List<Object>[3]` | No | `List<Object>` is also non-reifiable |
| `new List<? extends Number>[3]` | No | Wildcard has an upper bound |
| `new List<? super Integer>[3]` | No | Wildcard has a lower bound |
| `new Map<String, ?>[3]` | No | One argument is `String`, not `?` |
| `new T[3]` | No | Type variable `T` is non-reifiable |

**Important:** `List<?>` and `List<Object>` are not synonymous. `List<?>` represents a list with an unknown element type. `List<Object>` represents a list to which you can add objects through a properly typed reference, yet Java Generics are invariant so `List<String>` is not `List<Object>`.

### 3.2. What Runtime Component Does `List<?>[]` Actually Carry?

An experiment:

```java
List<?>[] groups = new List<?>[2];

System.out.println(groups.getClass().getTypeName());
System.out.println(groups.getClass().getComponentType().getTypeName());
```

On Java 17, the output is:

```text
java.util.List[]
java.util.List
```

`List<?>[]` is the source type retaining the wildcard; the runtime array object has component `List`. The JVM enforces on writes **whether an object is a List**, not the type argument of the list's contents.

This result is not an erasure flaw; it matches the exact contract declared by `List<?>[]`: the array slots are lists, while the element type inside each list **is unspecified**.

## 4. Allocating, Assigning, and Reading `List<?>[]` Arrays

Example:

```java
List<?>[] groups = new List<?>[3];

groups[0] = List.of("Java", "Generics");
groups[1] = List.of(10, 20);
groups[2] = List.of(true, false);
```

All three assignments are valid:

- `groups[0]` holds a reference to `List<String>`.
- `groups[1]` holds `List<Integer>`.
- `groups[2]` holds `List<Boolean>`.

Each list can be viewed as `List<?>`. The array does not require all lists to share the same concrete element type.

### 4.1. Reading Elements via Wildcard

```java
Object first = groups[0].get(0);
System.out.println(first); // Java
```

The `get` method of `List<?>` returns a value that the compiler treats as `Object`. You **cannot** automatically obtain a `String`:

```java
// Does not compile because the result has an unknown type:
// String text = groups[0].get(0);
```

Even though in the example you know `groups[0]` was just assigned `List.of("Java", ...)`, the array's contract states that this slot **could hold a List of another element type** at another time. That information is not preserved in the static type `List<?>`.

If you need a `String`, check it:

```java
Object value = groups[0].get(0);

if (value instanceof String text) {
    System.out.println(text.toUpperCase());
}
```

Or use an adapter that validates every element when you want to construct a trustworthy `List<String>`.

### 4.2. Why Can You Not Call `groups[0].add("new")`?

```java
// Invalid:
// groups[0].add("new");
```

Because the type of `groups[0]` is `List<?>`: `?` is treated by the compiler as an unknown element type. The actual list could be `List<Integer>`, so the compiler refuses arbitrarily adding a `String`.

A call `groups[0].add(null)` may be accepted by the type system since `null` is compatible with reference types, yet the runtime list may be immutable or reject `null`. Lists created by `List.of(...)` are unmodifiable.

**The array can replace a slot with a different list**:

```java
groups[0] = List.of(99);
```

That is valid, because `List<Integer>` is still a `List<?>`. However, you cannot arbitrarily add a `String` **into a list whose element type is unknown** through a `List<?>` reference.

### 4.3. Allocating and Initializing Contents

Both forms are valid:

```java
List<?>[] emptySlots = new List<?>[2];
```

And:

```java
List<?>[] prepared = new List<?>[] {
    List.of("a", "b"),
    List.of(1, 2)
};
```

The first form creates two slots initially holding `null`. The second creates an array containing references to two already-populated lists. When using `List.of`, those lists themselves cannot be modified via mutating methods.

You can create an empty array:

```java
List<?>[] none = new List<?>[0];
```

This is a valid zero-length array, useful when an API must return an array with no results yet.

## 5. `List<?>[]` Differs from Raw `List[]` Despite Having the Same Runtime Class

Java also allows:

```java
List[] rawGroups = new List[2];
```

The reason array creation is valid is similar: **raw `List` is reifiable**. However, raw types drop many generic checks in source code and can emit `rawtypes` or `unchecked` warnings.

Conversely:

```java
List<?>[] safeGroups = new List<?>[2];
```

expresses that each slot contains a `List` with an unknown element type; the compiler still protects element addition when you read a list from an array slot.

If the two arrays are created respectively:

```java
List<?>[] wildcard = new List<?>[2];
List[] raw = new List[2];

boolean sameRuntimeClass = wildcard.getClass() == raw.getClass();
```

`sameRuntimeClass` is `true` in standard Java because the runtime component of both is the raw `List` class/interface.

Yet **having the same runtime class does not mean having the same source contract**. Use `List<?>[]` when you do not need to call generic members via a raw reference; only use `List[]` at legacy boundaries with a clear reason.

### 5.1. `List<?>[]` Does Not Mean an "Untyped" Array

Both the array and the inner lists still follow rules:

- At the array level, elements must be compatible with runtime component `List` (or `null`).
- At the `List<?>` level, you can read elements as `Object`, and cannot arbitrarily write elements through the wildcard reference.
- There is no guarantee of uniform type arguments across lists in different slots.
- There is no guarantee that lists in the array are mutable, immutable, non-null, or equal in length.

Reifiability allows **creating** the array; it does not automatically supply all domain invariants.

## 6. Arrays Are Covariant and Still Enforce Store Checks

Reference arrays in Java are covariant. Therefore:

```java
List<?>[] groups = new List<?>[2];
Object[] alias = groups;
```

Assigning `List<?>[]` to `Object[]` is valid. However, the runtime object of `groups` remains an array with component class `List`.

If you do:

```java
alias[0] = "not a List";
```

the JVM throws `ArrayStoreException`: `String` does not conform to component type `List`.

Conversely:

```java
alias[0] = List.of(42);
```

is permitted at runtime, because the object is a `List`. This remains true even if `groups[0]` previously held `List<String>`. The array cannot check `String` on each list's contents; `List<?>[]` never promised that.

### 6.1. There Are Two Distinct Kinds of Checks

| Scenario | Runtime check | Possible outcome |
| --- | --- | --- |
| Putting a `String` into an object array whose actual component is `List` | JVM checks whether the object is a `List` | `ArrayStoreException` |
| Putting `List<Integer>` into an array whose component is `List` | JVM checks whether the object is a `List` | Write succeeds; `Integer` argument is not checked |
| Reading a list holding `Integer` through an alias falsely declared as `List<String>` | Compiler/JVM may cast the read result to `String` | `ClassCastException` |
| Reading a list through `List<?>` | Does not automatically cast elements to `String` | Receives `Object` |

The two errors `ArrayStoreException` and `ClassCastException` are not the same. The first concerns the element type **of the array**, while the second can involve an invalid generic assumption **inside the list**.

## 7. Casting `List<?>[]` to `List<String>[]` Is Unsafe

Some code attempts to bypass generic array creation limits using a cast:

```java
@SuppressWarnings("unchecked")
static List<String>[] unsafeClaim(List<?>[] input) {
    return (List<String>[]) input;
}
```

The generic cast can generate an unchecked warning (intentionally suppressed by the annotation in the example). The JVM knows `input` is an array of `List`s, yet cannot verify that every list has `String` elements.

Example:

```java
List<?>[] mixed = new List<?>[1];
mixed[0] = List.of(42);

List<String>[] claimed = unsafeClaim(mixed);
String text = claimed[0].get(0); // ClassCastException
```

Casting the array does not iterate over elements of each list. When `get(0)` is used as `String`, the `String` check fails because the actual value is `Integer`.

Do not use this trick to "fix" `generic array creation` errors. It merely defers the error from compile time to runtime and can introduce **heap pollution** — the condition where a variable of a parameterized type no longer refers to data conforming to its type contract.

### 7.1. Why Can the Cast Succeed While the Value Is Still Wrong?

After erasure, the runtime component class of `List<?>[]` is `List`, which is the same runtime representation checked when casting to `List<String>[]`. The `<String>` part has no full element-type check.

In Java code protected by generic checking, if `List<String>[]` enters through a legacy API, it still risks being aliased as `Object[]` or unchecked-cast. Hence, merely having the appearance of `List<String>[]` does not prove that every list inside truly holds `String`s.

### 7.2. What If Legacy Code Forces Returning `List<String>[]`?

If a legacy library has an API requiring this array:

1. Determine why the API cannot migrate to `List<List<String>>` or another type-safe abstraction.
2. Identify who creates, holds, and mutates the array; are there external raw aliases or `Object[]` aliases?
3. Validate every list and every element as `String` before handing the data to the caller.
4. If an unchecked cast is unavoidable, isolate the cast to a tiny scope and document the invariant; never suppress warnings at the class level.
5. Prefer copies and do not hand out aliases with uncontrolled write access.
6. Test invalid elements, null lists, and post-return mutations.

Even if validated at one point in time, if elsewhere someone still holds write access to the same list/array, the invariant can still be broken later. Validation and ownership must be considered together.

## 8. Complete Java 17 Example and Tested Output

Create the file **`WildcardListArrayDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class WildcardListArrayDemo {
    static <T> List<T> checkedCopy(List<?> input, Class<T> elementType) {
        List<T> result = new ArrayList<>();
        for (Object item : input) {
            result.add(elementType.cast(item));
        }
        return List.copyOf(result);
    }

    @SuppressWarnings("unchecked")
    static List<String>[] unsafeClaim(List<?>[] input) {
        return (List<String>[]) input;
    }

    public static void main(String[] args) {
        List<?>[] rows = new List<?>[3];
        rows[0] = List.of("Java", "Generics");
        rows[1] = List.of(10, 20);
        rows[2] = List.of(true, false);

        System.out.println("array-type=" + rows.getClass().getTypeName());
        System.out.println("component="
                + rows.getClass().getComponentType().getTypeName());
        System.out.println("is-list-array=" + (rows instanceof List<?>[]));
        System.out.println("first-values=" + rows[0].get(0) + ","
                + rows[1].get(0) + "," + rows[2].get(0));
        System.out.println("checked=" + checkedCopy(rows[0], String.class));

        Object[] alias = rows;
        try {
            alias[1] = "not a List";
        } catch (ArrayStoreException e) {
            System.out.println("store=" + e.getClass().getSimpleName());
        }
        alias[1] = List.of(99);
        System.out.println("replaced=" + rows[1].get(0));

        List<String>[] claimed = unsafeClaim(rows);
        try {
            String value = claimed[1].get(0);
            System.out.println(value);
        } catch (ClassCastException e) {
            System.out.println("unchecked=" + e.getClass().getSimpleName());
        }

        List<?>[][] matrix = new List<?>[1][2];
        matrix[0][0] = List.of("left");
        matrix[0][1] = List.of(100);
        System.out.println("matrix=" + matrix[0][0].get(0) + ","
                + matrix[0][1].get(0));
    }
}
```

Compile and run with a JDK supporting Java 17:

```bash
javac --release 17 -Xlint:all WildcardListArrayDemo.java
java WildcardListArrayDemo
```

The source compiles cleanly with no warnings under the stated lint flags (the intentionally illustrative unchecked cast is scoped to `unsafeClaim`). Exact stdout:

```text
array-type=java.util.List[]
component=java.util.List
is-list-array=true
first-values=Java,10,true
checked=[Java, Generics]
store=ArrayStoreException
replaced=99
unchecked=ClassCastException
matrix=left,100
```

### 8.1. Reading the Lines Related to Reifiability

`array-type=java.util.List[]` and `component=java.util.List` prove that the created array type has runtime component `List`, not `List<String>` or `List<Integer>`.

`is-list-array=true` proves that type checking the array with the reifiable form `List<?>[]` is valid.

`first-values=Java,10,true` proves that one array can hold lists with different element types; when read via `List<?>`, the results are used as `Object`.

### 8.2. Reading the Safety-Check Lines

`checked=[Java, Generics]` appears because `checkedCopy` verifies each element is `String` using `Class<String>.cast`. The adapter returns a new list; there is no need to assume every `List<?>` is `List<String>`.

`store=ArrayStoreException` results from putting a `String` into a runtime array with component `List`. This is a direct error on the **array element**.

`replaced=99` proves that putting `List<Integer>` through the same `Object[]` alias is valid, because the new object is still a `List`.

`unchecked=ClassCastException` shows that casting `List<?>[]` to `List<String>[]` did not verify `String` elements at all; the failure blows up when reading `Integer` as `String`.

`matrix=left,100` proves that multidimensional arrays `List<?>[][]` can also be created, because the leaf component `List<?>` is reifiable.

### 8.3. Why Does `checkedCopy` Use `List.copyOf`?

The function:

```java
static <T> List<T> checkedCopy(List<?> input, Class<T> elementType) {
    List<T> result = new ArrayList<>();
    for (Object item : input) {
        result.add(elementType.cast(item));
    }
    return List.copyOf(result);
}
```

ensures every element placed into `result` has been verified by the runtime class token. `List.copyOf` creates an unmodifiable copy and **rejects null**. If the contract permits null or requires a mutable list, choose a different copy structure and explicit validation rules.

`Class<T>` only helps verify concrete runtime types such as `String.class`. It cannot automatically verify a nested generic type `List<String>` inside an element of `List<List<String>>` without traversing nested levels.

## 9. Intentionally Non-Compiling Example: Limits of Array Creation

Create the file **`InvalidWildcardArray.java`**:

```java
import java.util.List;

class InvalidWildcardArray<T> {
    void invalid() {
        List<String>[] strings = new List<String>[2];
        List<? extends Number>[] numbers =
                new List<? extends Number>[2];
        T[] values = new T[2];
    }
}
```

Run:

```bash
javac --release 17 InvalidWildcardArray.java
```

`javac` rejects all three array creation expressions with the core message:

```text
error: generic array creation
error: generic array creation
error: generic array creation
```

Reasons:

1. `List<String>` is non-reifiable because of the concrete type argument `String`.
2. `List<? extends Number>` is non-reifiable because `?` has an upper bound rather than being a completely unbounded wildcard.
3. `T` is non-reifiable even if it has a bound; the erasure of `T` does not identify a component class matching each caller's choice of `T`.

Do not confuse **declaring an array variable** with **allocating an array**. Java lets you declare:

```java
List<String>[] declaredOnly;
```

but does not allow direct creation via `new List<String>[2]`. A generic array type declaration has no object yet and provides no guarantees about internal data.

## 10. Using `List<?>[]` in Methods Accepting and Returning Data

Wildcard arrays are not limited to local variables:

```java
static List<?>[] createGroups() {
    return new List<?>[] {
        List.of("Java"),
        List.of(2026)
    };
}
```

This is an illustrative method placed in a class with `import java.util.List;`. The created array has runtime component `List`, and the caller can inspect elements as `List<?>`.

A method accepting an array:

```java
static int countAll(List<?>[] groups) {
    int count = 0;
    for (List<?> group : groups) {
        count += group.size();
    }
    return count;
}
```

This function does not need `<T>` because it only uses each list's size, does not care about element types, and establishes no relationship among type arguments.

**Watch out for `null`:** `new List<?>[n]` initially creates null slots. Calling `group.size()` on an unassigned slot causes `NullPointerException`. A public API can check for null or adopt a policy treating null slots as empty groups, depending on the contract.

### 10.1. Varargs with `List<?>`

A varargs parameter is backed by an array:

```java
static int total(List<?>... groups) {
    int count = 0;
    for (List<?> group : groups) {
        count += group.size();
    }
    return count;
}
```

Because the component type `List<?>` is reifiable, this varargs form does not trigger the *non-reifiable varargs parameter* warning typically seen with `List<String>...` or `List<T>...`.

Call example:

```java
int total = total(List.of("a", "b"), List.of(1, 2, 3));
// total equals 5
```

This does not mean the varargs array may be mutated arbitrarily. A varargs method can also receive an already-existing array, while the inner lists may be immutable, null, or shared with the caller.

### 10.2. Contrasting with Generic Varargs

```java
static <T> void inspect(List<T>... groups) {
    // ...
}
```

With `List<T>...`, the component `List<T>` is non-reifiable, so the compiler can warn about potential heap pollution. `@SafeVarargs` may only be used on methods permitted by Java to carry the annotation and when the author can justify that the body performs no unsafe operations on the varargs array. The annotation **does not make** `List<T>` reifiable.

If the method does not need to relate a specific `T` across lists, consider declaring `List<?>...` instead of `List<T>...`. If the same `T` must be preserved, uphold the generic contract and handle varargs deliberately, rather than swapping types indiscriminately just to remove warnings.

## 11. When Should You Use `List<List<String>>` Instead of an Array?

`List<?>[]` is suitable when the requirement is merely a **fixed-length sequence of lists with unknown element types** or when interoperating with an API requiring an array. It is not suitable when you need to guarantee that all sub-lists contain `String`.

Compare:

```java
List<?>[] mixed = new List<?>[2];
mixed[0] = List.of("a");
mixed[1] = List.of(42); // Valid
```

with:

```java
List<List<String>> groups = new ArrayList<>();
groups.add(List.of("a", "b"));
// groups.add(List.of(42)); // Compile-time error
```

The `List<List<String>>` structure preserves the `String` type argument in the source contract across both levels. When code is checked by generics without raw/unchecked aliases breaking the contract, the compiler rejects a list holding `Integer` at the insertion site.

Selection criteria:

| Requirement | Consider | Reason |
| --- | --- | --- |
| Need an exact number of slots, able to replace the entire list at each slot | `List<?>[]` | Fixed-size array; each slot accepts any compatible `List<?>`. |
| Lists may have different element types, read-only | `List<?>[]` or `List<List<?>>` | Does not promise all elements share `T`. |
| Every list must hold String and the number of groups can change | `List<List<String>>` | Preserves generic contract at both levels; easy to add/remove groups. |
| API mandates returning an array yet needs type-safe String groups | Consider another API or an adapter with clear validation and ownership | Cannot directly create `new List<String>[n]` in valid Java syntax. |
| Need a real object array with component `String` | `String[]` | Runtime array enforces component `String`. |

`List<List<String>>` itself is also **non-reifiable**, yet it can be used in declarations and `new ArrayList<>()` creation because it does not require allocating an array with component `List<String>`. Its safety comes from source-level generic checking, not from the JVM creating a distinct class for `List<List<String>>`.

## 12. Common Misconceptions

### 12.1. "`new List<?>[n]` is valid because the wildcard disables type checking"

Incorrect. `List<?>` is still a generic type checked by the compiler. Precisely because it promises no concrete type argument, it qualifies as **reifiable** for array creation; at the same time, the compiler still restricts adding elements to a `List<?>`.

### 12.2. "`List<?>[]` is equivalent to `List<Object>[]`"

No. `List<Object>` is a non-reifiable parameterized type, so `new List<Object>[n]` cannot be allocated. Moreover, `List<String>` is not a subtype of `List<Object>`, whereas it can be viewed as `List<?>`.

### 12.3. "`List<?>[]` can only contain empty lists"

No. It can hold `List<String>`, `List<Integer>`, `List<Boolean>`, or other compatible lists. `?` does not restrict what kind of elements exist inside the list; it restricts what you are allowed to **assume and write** through the wildcard reference.

### 12.4. "`ArrayStoreException` will check `String` inside `List<String>`"

No. The runtime array has component class `List`; the store check verifies that the assigned object conforms to `List`, rather than iterating over list elements to verify `String`. If `String` must be guaranteed, write an element-level validator.

### 12.5. "A cast `(List<String>[]) array` makes the data type-safe"

No. The cast may pass the compiler with an unchecked warning, yet it does not turn type arguments into a runtime component. `ClassCastException` can still appear later when reading data.

### 12.6. "Having a `?` wildcard always makes a type reifiable"

No. `List<? extends Number>` and `List<? super Integer>` have **bounded** wildcards, failing the condition that "all arguments are unbounded wildcards." `new List<? extends Number>[n]` is rejected by the compiler.

### 12.7. "Erasure turns every array into `Object[]`"

No. The runtime component type of `String[]` remains `String`, and that of `List<?>[]` remains `List`. Erasure applies to how generics/type variables are represented; it does not automatically turn every created array object into `Object[]`.

### 12.8. "Because `new List<?>[n]` is valid, it is always the best choice"

No. If an application wants every group to be `List<String>`, a structure with an explicit generic element type like `List<List<String>>` usually helps the compiler catch mistakes earlier. Choose an array when you truly need array semantics or API compatibility.

## 13. Workflow for Fixing `generic array creation` Errors

If you see:

```text
error: generic array creation
```

check whether you are creating one of the forms like:

```java
new List<String>[n]
new List<? extends Number>[n]
new T[n]
```

Then ask yourself:

1. **Is the component type reifiable?** `List<?>` is; `List<String>` or `T` is not.
2. **Is an array truly necessary?** If not, use `List<List<T>>` or a suitable collection.
3. **Do the lists need the same concrete type argument?** If so, `List<?>[]` does not provide that invariant.
4. **Can the API accept a wildcard structure?** If only reading groups of unknown element type, `List<?>[]` can express the contract accurately.
5. **Is there legacy/raw data or an unchecked cast?** If so, validate elements carrying concrete types before publishing a type-safe result.
6. **Who owns the array and inner lists?** If aliases escape outside, callers may swap slots; lists may also be mutable.
7. **Are there enough negative tests?** Test a non-List object via an `Object[]` alias, a list with unexpected elements, null slots, and post-initialization mutation.

Do not fix the error by converting all code to raw types or adding an unchecked cast right at allocation. That only hides the loss of generic type information.

## 14. Practice Exercises

### Exercise 1 — Classifying Allocations

Given the lines:

```java
List<?>[] a = new List<?>[2];
List<String>[] b = new List<String>[2];
List[] c = new List[2];
List<? extends Number>[] d = new List<? extends Number>[2];
```

Which lines can allocate?

<details>
<summary>Answer</summary>

`a` and `c` can allocate: `List<?>` and raw `List` are reifiable. Line `c` may emit a `rawtypes` warning. `b` and `d` are invalid because `List<String>` and `List<? extends Number>` are non-reifiable.

</details>

### Exercise 2 — Reading Elements

```java
List<?>[] rows = new List<?>[1];
rows[0] = List.of("Java");
```

Can you directly assign `String text = rows[0].get(0);`?

<details>
<summary>Answer</summary>

No. The static type of `rows[0]` is `List<?>`; `get(0)` is read as `Object`. If `String` is needed, check the value with `instanceof String` or an element-validating adapter. Just assigning a `List<String>` does not change the declared type of `rows[0]` into `List<String>`.

</details>

### Exercise 3 — Runtime Array Store

```java
List<?>[] rows = new List<?>[1];
Object[] alias = rows;
alias[0] = "x";
```

What happens?

<details>
<summary>Answer</summary>

`ArrayStoreException` at the write statement. The array object has runtime component `List` and rejects `String` as an array element.

</details>

### Exercise 4 — Can a List with `Integer` Enter the Array?

```java
List<?>[] rows = new List<?>[1];
rows[0] = List.of(99);
```

<details>
<summary>Answer</summary>

Yes, because `List<Integer>` is compatible with `List<?>`. The array does not promise that its lists hold Strings. Reading the element via `rows[0].get(0)` yields a value whose static type is `Object`.

</details>

### Exercise 5 — Why Can `new List<?>[3]` Allocate While `new List<? super Integer>[3]` Cannot?

<details>
<summary>Answer</summary>

`List<?>` has an unbounded wildcard, belonging to reifiable parameterized types. `List<? super Integer>` has a wildcard with a lower bound, which is non-reifiable and rejected as an array creation component.

</details>

### Exercise 6 — Data Needing Two Levels of String

An application needs a collection of groups, each containing only strings, where the number of groups can change. Which structure should be preferred?

<details>
<summary>Answer</summary>

Usually choose `List<List<String>>`. It preserves the `String` type contract across both levels and makes adding/removing groups easy. `List<?>[]` does not promise every element of each group is `String`; array types have fixed slots and do not resize automatically.

</details>

## 15. Conclusion

**`new List<?>[n]` is valid because `List<?>` is reifiable.** The created array has runtime component class `List`; the JVM can check whether the object assigned to each slot belongs to `List`. The unbounded `?` promises no specific type argument, so the array can hold `List<String>`, `List<Integer>`, or lists of other element types.

This does **not** make `List<String>[]` directly creatable, does not allow automatically reading `String` from `List<?>`, and does not turn unchecked casts into element checks. When an array of lists of unknown type is needed, `List<?>[]` expresses the right contract. When an invariant requires every list to contain a specific `T`, prefer type-preserving APIs, nested collections, or data-validating adapters.
