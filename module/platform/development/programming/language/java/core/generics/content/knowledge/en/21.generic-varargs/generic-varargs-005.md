# Risks of Exposing the Varargs Array Externally in Java Generics

## Learning Objectives

Varargs is a feature that lets you write methods accepting multiple arguments: `log("A", "B", "C")` instead of building an array manually at the call site. However, a parameter declared as `T... values` is actually handled as a **`T[]` array** inside the method body. When `T` is a *non-reifiable* type, such as `List<String>`, the runtime array does not carry enough generic information to enforce the full `List<String>[]` contract.

A prominent risk is **varargs array escape**: the method directly returns the received array, stores it in a field, hands it to an untrusted callback, or returns a view backed by that array. External code can hold an alias to the array and overwrite a slot with an object that matches the runtime component type yet has the wrong generic type argument. This produces *heap pollution* and can lead to a delayed `ClassCastException`.

This lesson helps you:

- Describe accurately how varargs are passed as arrays and why generics trigger warnings.
- Understand the differences among `String...`, `List<?>...`, and `List<String>...`.
- Trace creating an `Object[]` alias, inserting a `List<Integer>` into `List<String>[]`, and the failure thrown on read.
- Evaluate whether a method exposes its varargs array directly or indirectly.
- Understand the effect, eligibility rules, and limitations of `@SafeVarargs`.
- Fix APIs using independent snapshots, preserving data invariants and using collections with clear contracts.
- Run `javac -Xlint` and write tests guarding against aliasing/generic bugs.

## 1. Varargs Is Really an Array

Example:

```java
static void show(String... words) {
    System.out.println(words.length);
}
```

A caller can write:

```java
show("A", "B", "C");
show(new String[] {"A", "B", "C"});
```

Inside `show`, `words` has type `String[]`. It has `length`, supports indexed access, and accepts slot assignments if the code performs them. The first call style has the compiler assemble an array during the varargs call; the second style passes the caller's existing array directly via a fixed-arity call.

The two declarations `String... words` and `String[] words` cannot coexist as overloads differing only in the ellipsis: inside the method and after compilation, a varargs parameter is represented as an array. The `...` syntax changes how callers supply a variable number of arguments; it does not invent a new runtime container.

With generics:

```java
static <T> void consume(T... values) {
    for (T value : values) {
        System.out.println(value);
    }
}
```

Inside the method body, `values` has source type `T[]`. If `T` is an unbounded type variable, the erasure of `T` is `Object`. With a nested generic type like `List<String>`, the runtime array has no dedicated component class carrying the `String` type argument; that is the intersection of varargs and type erasure.

## 2. Why Do Reifiability and Ownership Both Matter?

In the JVM, arrays carry a runtime component class. With `String[]`, writing an `Integer` through an `Object[]` alias fails with `ArrayStoreException`. With generic varargs `List<String>...`, however, the array's runtime component type is `List` and cannot verify the `String` type argument; a `List<Integer>` still passes the array store check.

| Varargs Element Type | Reifiable? | What to Remember |
| --- | --- | --- |
| `String` or `int` | Yes | The array has runtime component `String` or `int`, respectively. |
| `List<?>` | Yes | Only guarantees each slot is a `List`, making no promise about inner element types. |
| `List<String>`, `List<? extends Number>` | No | Concrete type arguments and bounded wildcards are not deeply checked at runtime. |
| `T` in `<T> void f(T... values)` | Not in general | `erasure(T)` and how the caller constructs the array determine the actual runtime component. |

**Even reifiable arrays are mutable**: a method can be passed the exact array constructed by the caller. This lesson analyzes what happens when a method **returns the array, stores it in a field, or publishes an array-backed view**, allowing others to retain an alias and mutate slots after the method returns. This is an **array ownership and lifetime** issue, not just whether the compiler emits an unchecked warning.

## 3. What Does Exposing the Varargs Array Mean?

A method has **exposed** (*escaped*) the varargs array if external code can retain and use that same array reference after the method finishes or in a context the method no longer controls.

Illustrative examples:

```java
// Dangerous if T is non-reifiable and callers receive T[]:
static <T> T[] returnArray(T... items) {
    return items;
}

// Also exposes it if storing the array reference itself in a field:
// this.cachedItems = items;

// Or passing the array itself to a callback that could retain or mutate it:
// callback.accept(items);

// Arrays.asList returns a view backed by the input array:
// return Arrays.asList(items);
```

These declarations and commented snippets are for design analysis, not a standalone Java program.

Escape paths are not limited to `return items`. An **array-backed view** can also create an indirect alias. If you return `Arrays.asList(items)`, the recipient can call `set` to mutate slots of the original array; conversely, mutating the array shows through the list view.

By contrast, a method that merely iterates over the values to compute a sum, check a condition, or copy elements into a new collection normally has no need to expose the array.

Two dimensions must be evaluated separately:

1. **Type safety:** does the runtime array component fully reflect the generic element type?
2. **Ownership/mutability:** do caller and callee share or mutate the same array object?

Even reifiable `String...` carries the risk of sharing and mutating the caller's input array if the callee retains or writes to it. Non-reifiable varargs additionally carries **heap pollution** risk because nested generics are unchecked at runtime.

## 4. How Heap Pollution Occurs When the Array Escapes

Consider the method:

```java
// Requires import java.util.List.
static <E> List<E>[] expose(List<E>... groups) {
    return groups;
}
```

In source code, the signature returns `List<E>[]`. When a caller passes `List<String>` arguments as varargs, the compiler can allocate an array with runtime component type `List` because `List<String>` is non-reifiable.

Then:

```java
List<String>[] escaped = expose(List.of("A"), List.of("B"));
Object[] alias = escaped;
alias[0] = List.of(42);           // Write succeeds into the List[] array.
String first = escaped[0].get(0); // ClassCastException on read.
```

This snippet demonstrates the error scenario; the complete program in section 6 catches the exception to display the result.

Exact trace:

1. `expose` receives a newly synthesized varargs array or a caller-supplied array; in this call the compiler creates an array with runtime component `List`.
2. `return groups` returns that exact array reference without cloning or changing its structure.
3. The variable `escaped` is declared `List<String>[]`; the programmer trusts every slot points to a `List` of `String`.
4. `Object[] alias = escaped` is valid because Java reference arrays are covariant.
5. `alias[0] = List.of(42)` writes a `List<Integer>` into the runtime `List[]` array. The array store check **throws no error** because the inserted object really is a `List`.
6. `escaped[0].get(0)` returns an `Integer`; source code expects `String`. The compiler inserts `checkcast String` where the result is consumed, and the JVM throws `ClassCastException`.

Conclusion: the JVM checking that an array element is a `List` **does not mean** it checks that the `List` contains only `String`. Hence, the failure does not necessarily happen when the alias writes the invalid value.

### Data-Flow Diagram

```text
expose(List<String>, List<String>)
    |
    v
runtime array List[] (varargs)
    |
    | return groups; -- ESCAPE
    v
List<String>[] escaped
    |
    | Object[] alias = escaped;
    | alias[0] = List.of(42);
    v
List[] array still accepts List<Integer>
    |
    | String s = escaped[0].get(0);
    v
List.get() returns Object(Integer)
    |
    | compiler inserts checkcast String
    v
ClassCastException at caller
```

This is a form of *heap pollution*: the actual value in the slot no longer satisfies the `List<String>` contract declared for the variable. The site that corrupts the data and the site that throws the exception may reside in completely different modules.

## 5. What Do Compiler Warnings Mean?

With `expose`, run:

```bash
javac --release 17 -Xlint:all VarargsEscapeDemo.java
```

The compiler can emit warnings at both the **declaration** and the **call site**:

```text
[unchecked] Possible heap pollution from parameterized vararg type List<E>
[unchecked] unchecked generic array creation for varargs parameter of type List<String>[]
```

Both warnings were verified with `javac --release 17 -Xlint:all` on the program in section 6.

- First warning: the varargs parameter has a non-reifiable type; the method could use the array unsafely.
- Second warning: at the varargs call site, the compiler creates an array of the erased type and therefore cannot fully verify the generic component.

**A warning does not mean a method definitely has a bug**; a method that only iterates over elements and never exposes the array can be designed safely despite a non-reifiable signature. Still, a warning is a signal to audit, not something to suppress reflexively.

`@SuppressWarnings("unchecked")` only hides warnings within its annotated scope; it does not fix the runtime component type, create a copy, or protect aliases. `@SafeVarargs` also affects call-site warnings, so it demands greater responsibility from the library author.

## 6. Complete Runnable Java 17 Example

**File `VarargsEscapeDemo.java`:**

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class VarargsEscapeDemo {
    static <E> List<E>[] expose(List<E>... groups) {
        return groups;
    }

    @SafeVarargs
    static <T> List<T> snapshot(T... values) {
        List<T> copy = new ArrayList<>(values.length);
        for (T value : values) copy.add(value);
        return List.copyOf(copy);
    }

    @SafeVarargs
    static <T> List<List<T>> snapshotGroups(List<? extends T>... groups) {
        List<List<T>> copy = new ArrayList<>();
        for (List<? extends T> group : groups) {
            copy.add(List.copyOf(group));
        }
        return List.copyOf(copy);
    }

    static void observe(List<?>... groups) {
        for (List<?> group : groups) {
            System.out.println("observed-size=" + group.size());
        }
    }

    public static void main(String[] args) {
        List<String>[] escaped = expose(List.of("A"), List.of("B"));
        System.out.println("runtime-component="
                + escaped.getClass().getComponentType().getSimpleName());

        Object[] alias = escaped;
        alias[0] = List.of(42);
        System.out.println("array-store-accepted=" + escaped.length);

        try {
            String result = escaped[0].get(0);
            System.out.println(result);
        } catch (ClassCastException error) {
            System.out.println("late-failure=" + error.getClass().getSimpleName());
        }

        List<String> flat = snapshot("x", "y");
        System.out.println("flat=" + flat);
        try {
            flat.add("z");
        } catch (UnsupportedOperationException error) {
            System.out.println("flat-is-fixed="
                    + error.getClass().getSimpleName());
        }

        List<List<String>> groups = snapshotGroups(
                List.of("one"), List.of("two"));
        System.out.println("groups=" + groups);
        try {
            groups.get(0).set(0, "changed");
        } catch (UnsupportedOperationException error) {
            System.out.println("inner-is-fixed="
                    + error.getClass().getSimpleName());
        }

        observe(List.of("a"), List.of(3));
    }
}
```

Compile and run:

```bash
javac --release 17 -Xlint:all VarargsEscapeDemo.java
java VarargsEscapeDemo
```

**Verified stdout:**

```text
runtime-component=List
array-store-accepted=2
late-failure=ClassCastException
flat=[x, y]
flat-is-fixed=UnsupportedOperationException
groups=[[one], [two]]
inner-is-fixed=UnsupportedOperationException
observed-size=1
observed-size=1
```

The program intentionally produces **two unchecked warnings** on `expose` and its corresponding call site. The warnings appear during `javac`, not in `java` stdout.

### 6.1. The Escaped Array Has Runtime Component List

The line `runtime-component=List` comes from `getClass().getComponentType().getSimpleName()`. Although the static type is `List<String>[]`, the actual array stores `List` objects with no `String` check at the runtime component level.

### 6.2. Mismatched Write Produces No ArrayStoreException

`Object[] alias` and `escaped` are two references to **the same array object**. Writing `List.of(42)` satisfies the runtime component `List`. Thus execution reaches `array-store-accepted=2`; this is not proof that the generic data remains valid.

### 6.3. Failure Surfaces Late on Read

`escaped[0].get(0)` retrieves an `Integer` element, while the caller expects a `String`. When the JVM runs the compiler-inserted cast, `ClassCastException` is caught and printed. By then, the code that caused heap pollution has already finished executing.

### 6.4. Both Snapshots Avoid Returning the Varargs Array

`snapshot` iterates over the elements and copies them into a new `List`. `snapshotGroups` iterates over the array of groups and copies each group into a new `List` before returning a new outer `List`. No varargs array reference is present in the return value, so callers cannot obtain that array through this API.

`List.copyOf` returns an unmodifiable collection; that is why the program catches `UnsupportedOperationException` in two places. This provides **structural unmodifiability**, not an automatic deep copy of `T` element objects.

### 6.5. When You Only Need to Inspect, Do Not Overpromise

`observe(List<?>... groups)` only calls `size()` on each group. It does not require every group to share the same concrete element type; `List<?>` matches that need and is a reifiable type. The method neither returns nor stores the array.

## 7. When Should `@SafeVarargs` Be Used?

`@SafeVarargs` is a **programmer's promise**: the method or constructor body handles varargs of a non-reifiable type without introducing unsafe operations involving that array. The annotation lets the compiler suppress certain unchecked warnings at the varargs declaration and call sites.

It **does not**:

- Turn `List<String>` into a reifiable type.
- Turn runtime `List[]` into an array with component `List<String>`.
- Automatically copy or freeze the varargs parameter.
- Prevent external code from keeping an already-exposed alias.
- Guarantee that the compiler exhaustively proved the method body safe.

Never add the annotation to hide warnings on a pattern like:

```java
// UNSAFE PATTERN - do not add @SafeVarargs:
static <E> List<E>[] expose(List<E>... groups) {
    return groups;
}
```

Here the hazard arises directly from returning the array externally. Adding `@SafeVarargs` may silence caller warnings while data can still be corrupted.

### Annotation Eligibility Rules in Java 17

`@SafeVarargs` is valid on constructors or **`static`, `final`, or `private` varargs methods**. It cannot be placed arbitrarily on an overridable instance method. An example that intentionally fails to compile:

```java
class InvalidSafeVarargs {
    @SafeVarargs
    void instanceMethod(String... values) {}
}
```

When checked with `javac --release 17`, the compiler rejects it because the method is not `static`, `final`, or `private`. Moreover, `@SafeVarargs` is redundant when the varargs element type is already reifiable, such as `String...`, since there is no corresponding warning to suppress.

**The Java specification does not treat the annotation as a formal proof.** The compiler may warn on suspicious bodies, yet does not guarantee catching every aliasing path. Therefore, the author must audit the entire method body before annotating.

### Pattern Eligible for the Annotation

```java
@SafeVarargs
static <T> List<T> snapshot(T... values) {
    List<T> copy = new ArrayList<>(values.length);
    for (T value : values) {
        copy.add(value);
    }
    return List.copyOf(copy);
}
```

This snippet resides in a class importing `List` and `ArrayList`. It only reads the array, copies elements into a `List`, and returns a new structure; it never mutates varargs slots, never returns or stores the array, and never hands the array reference outside.

Do not conclude from `@SafeVarargs` that all downstream data is unconditionally safe: elements may be mutable, `null` will be rejected by `List.copyOf`, and callers could still have misused raw types beforehand. The annotation only speaks to how the method handles its varargs contract.

## 8. Array-Backed Views Can Also Expose Aliases

A common example:

```java
static <T> List<T> backedView(T... values) {
    return java.util.Arrays.asList(values);
}
```

This is an analysis pattern; do not add `@SafeVarargs` without auditing the aliasing path. `Arrays.asList(values)` creates a **fixed-size** `List` backed by the `values` array. It disallows structural resizing like `ArrayList`, yet `set` overwrites slots of the underlying array.

Check on a reifiable array:

```java
String[] original = {"A", "B"};
List<String> view = java.util.Arrays.asList(original);
view.set(0, "C");
System.out.println(original[0]); // C
```

`original` and `view` access the same backing array. This case is not heap pollution because the elements are `String`, yet it demonstrates **alias exposure through a view**. With a varargs array of a non-reifiable type, handing out a view makes mutation paths harder to control.

You can create a structural snapshot by copying:

```java
List<String> copy =
        List.copyOf(java.util.Arrays.asList(original));
```

`copy` is a structurally independent unmodifiable `List`. Still, when writing an annotated generic varargs method, passing the varargs array directly to an intermediate API like `Arrays.asList(values)` can cause `javac -Xlint:varargs` to warn about potential reference leakage, even if the final copy step is safe. Using a loop like `snapshot` above keeps the data flow more explicit.

## 9. Does Cloning the Array Completely Solve the Problem?

`values.clone()` returns a different array from the input array, separating **array references** at the boundary. However, that does not mean a `List<String>[]` gains deep runtime `String` checking.

Suppose a helper returns a clone of an array with runtime component `List`; the caller can still write:

```java
List<String>[] result = /* returned array, static type List<String>[] */;
Object[] wider = result;
wider[0] = List.of(99); // Runtime List[] still accepts List<Integer>.
```

The snippet above is a conceptual sketch, not a standalone program (`result` must come from an appropriate source). The independent cloned array is still `List[]` at runtime and has no `List<String>` class token. A new `Object[]` alias to the clone itself can still cause heap pollution.

In addition, cloning an array only copies **the element references**. If elements are mutable objects, both the original and cloned arrays still reference the same objects; mutating one remains visible from both sides.

From this follow three levels of defense:

1. **Do not return the input array:** reduces alias leakage back to the original array.
2. **Do not return a non-reifiable array if unnecessary:** avoids giving callers a `List<String>[]` easily aliased via `Object[]`.
3. **Copy data and define mutability clearly:** for nested lists, copy every level needing protection; if element objects must be immutable, add a domain-appropriate deep-copy strategy.

In many APIs, returning an independent `List<List<T>>` is clearer than returning `List<T>[]`.

## 10. A Caller's Own Array Can Be Passed Directly Through Varargs

Never assume the compiler always allocates a new array. When called with an existing array of the matching type, a varargs method can receive that exact array:

```java
static void edit(String... words) {
    words[0] = "CHANGED";
}

// Inside main:
String[] input = {"A", "B"};
edit(input);
System.out.println(input[0]); // CHANGED
```

This example is independent of non-reifiable generics, yet demonstrates an **ownership risk**: the callee mutates the caller's input array.

Conversely, `edit("A", "B")` causes the compiler to construct an array at the call site; the caller does not directly hold a reference to that temporary array unless the method exposes it.

If your contract promises **not to mutate caller data**, never write to varargs slots. If you must retain the elements asynchronously or after the method returns, copy them with an explicit null/mutability policy instead of keeping `values`.

## 11. What to Do When Multiple `List` Groups Are Needed?

If the logic only counts total elements:

```java
static int count(List<?>... groups) {
    int result = 0;
    for (List<?> group : groups) {
        result += group.size();
    }
    return result;
}
```

`List<?>` lets the method accept both `List<String>` and `List<Integer>` without promising that all groups share a single type `T`. The method only reads and returns an `int`, with no reason to return an array.

If the logic must retain data longer:

```java
@SafeVarargs
static <T> List<List<T>> snapshotGroups(List<? extends T>... groups) {
    List<List<T>> copy = new ArrayList<>();
    for (List<? extends T> group : groups) {
        copy.add(List.copyOf(group));
    }
    return List.copyOf(copy);
}
```

Here the method creates new inner groups via `List.copyOf(group)` as well as a new outer `List`. No varargs array is exposed. In return, the API must document that `null` is rejected by `List.copyOf`, and mutable `T` objects are not deep-copied.

### When to Choose `Collection` Over Varargs?

If callers already have a collection, a signature taking `Collection<? extends T>` or `List<? extends T>` is often sufficient and avoids allocating an extra varargs array. Varargs fits best when the primary goal is concise call syntax for a few arguments; it is not mandatory for every multi-element API.

Need an actual array with a concrete runtime component such as `String[]`? Consider accepting an `IntFunction<T[]>` (e.g., `String[]::new`) or `Class<T>`. Never cast `Object[]` to `T[]` without the corresponding runtime guarantee.

## 12. Common Mistakes in Code Review

| Claim or Practice | Issue | How to Handle |
| --- | --- | --- |
| "A `T...` parameter is not an array." | Inside the method body, it is `T[]`. | Trace every alias, assignment, and array pass-through. |
| "A `List<String>[]` array blocks any `Integer` list." | The runtime component is `List`; `String` is not reified. | Do not expose the array; copy into a properly typed structure. |
| "No `ArrayStoreException` means nothing is wrong." | Writing `List<Integer>` into `List[]` is accepted. | Check the generic contract and delayed cast sites. |
| "Adding `@SafeVarargs` makes the method safe." | The annotation neither inspects the body nor copies data. | Apply only after proving array handling is safe. |
| "`return items.clone()` always eliminates all risks." | Clones still have a non-reifiable array type and share element objects. | Evaluate the return API type and copy required levels. |
| "`Arrays.asList(items)` creates an isolated `List`." | It is a list view backed by the array. | Copy if the goal is an independent snapshot. |
| "Suppressing all unchecked warnings at callers is enough." | Hides risk signals without fixing heap pollution. | Review declaration, call sites, and alias paths. |
| "`List<?>...` promises all groups have the same type." | Unbounded wildcards make no concrete element-type promise. | Pick a signature matching read-only intent. |
| "Returning a snapshot performs a deep copy." | `List.copyOf` only copies structure, keeping `T` references. | If deep copying is needed, design it specifically for the domain. |
| "Varargs always allocates a fresh array." | Callers can pass an existing array directly. | Never write into the array unless the contract allows it. |

## 13. Workflow for Investigating and Reproducing the Bug

When a `ClassCastException` occurs in code reading a `List<String>` from an array or collection produced by a varargs API, follow these steps:

1. **Preserve the full stack trace** to identify the failing `checkcast` site and the actual runtime type.
2. **Trace the data origin**: which method receiving `T...` or `List<T>...` created, returned, or stored the array?
3. **Inspect the source signature**: is the element type non-reifiable, or are there raw/unchecked casts?
4. **Search for escape paths**: `return varargs`, field storage, caches, callbacks, or `Arrays.asList` views.
5. **Search for broader aliases**: `Object[]`, raw `List[]`, `Collection[]`, or a supertype array.
6. **Find slot-overwriting statements**: `alias[index] = ...` may have inserted a container with the right runtime class but wrong generic argument.
7. **Enable lint**: `javac --release 17 -Xlint:unchecked,varargs ...`. Never suppress warnings before understanding them.
8. **Reproduce in a controlled test**: build a test with `List<String>` inputs, insert a `List<Integer>` via an alias, and read; confirm the old code fails and the fix avoids exposing the array.
9. **Refactor data ownership**: process locally in the callee or return a snapshot, avoiding returning non-reifiable arrays unless there is a strong design reason.
10. **Review the post-fix contract**: nulls, mutable elements, copy cost, thread safety, and legacy callers.

Regardless of whether the compiler emits warnings in a given build, a public API handing out a mutable array reference always deserves an ownership audit.

### Why Can the Error Be Delayed?

After a slot of a `List<String>[]` array is replaced with `List<Integer>`, code calling `array.length`, `array[0].size()`, or passing the array through multiple layers can run normally. The failure surfaces only when the program demands a `String` element from the `List` actually holding an `Integer`. Therefore, changing the `get(0)` line with another cast usually only masks the symptom without fixing the source of heap pollution.

## 14. Practice Exercises

**Exercise 1.** Is the code below safe?

```java
static <T> T[] save(T... values) {
    return values;
}
```

**Answer:** It cannot be considered a generally safe design. It exposes the array itself. If `T` is non-reifiable (especially a parameterized generic type), callers can face heap pollution and aliasing. Even when `T` is reifiable, it carries mutable-array sharing risk. Never add `@SafeVarargs` just to hide warnings.

**Exercise 2.** For a `List<String>[]` whose runtime component is `List`, why can an `Object[]` alias write a `List<Integer>`?

**Answer:** Array covariance permits the alias. The array store check only knows the component is `List`; `List<Integer>` is a `List` at runtime. The JVM does not check the `String` type argument inside the slot.

**Exercise 3.** Why can the failure occur at `String value = escaped[0].get(0)`?

**Answer:** After erasure, `List.get` returns `Object`. The caller expects `String`, so the compiler inserts `checkcast String`; if the actual element is an `Integer`, the JVM throws `ClassCastException`.

**Exercise 4.** Should `@SafeVarargs` be applied to a method that directly returns `List<E>[]` from `List<E>...`?

**Answer:** No, because it exposes the array so callers can hold aliases and replace slots. The annotation does not change runtime behavior.

**Exercise 5.** Can a `String[]` passed into `void update(String... values)` be modified if the callee writes to `values[0]`?

**Answer:** Yes. The caller passed an existing array, so both variables point to the same array. The contract must specify mutation rights.

**Exercise 6.** Does `Arrays.asList(varargs)` detach from the backing array?

**Answer:** No. It is a fixed-size view where `set` modifies the array. If you need an independent snapshot, you must copy.

**Exercise 7.** Does `List.copyOf` make a mutable `T` object inside the list immutable?

**Answer:** No. It protects the `List` structure from modification and copies the collection; the element objects themselves can still be mutable.

**Exercise 8.** If you only count elements across `List<String>` and `List<Integer>` groups, should you accept `List<String>...` or `List<?>...`?

**Answer:** `List<?>...` accurately expresses independence from element types; only read `size` and do not return the array.

**Exercise 9.** Why does a method using `List<E>...` emit warnings even when its body only reads?

**Answer:** The varargs element type is non-reifiable; the compiler warns about potential heap pollution at the array boundary. If the method truly only reads, never mutates slots, never passes the array where an alias could be retained, and never exposes the array, the author may consider `@SafeVarargs` when eligible.

**Exercise 10.** Should you return a cloned `List<T>[]` from varargs to avoid all risk?

**Answer:** Cloning separates from the original array, yet callers still hold a non-reifiable array with a broad runtime component that can be re-aliased and have slots overwritten. If returning multiple groups is needed, `List<List<T>>` is usually better.

## 15. Summary and References

The crux is the combination of three mechanisms: **varargs is implemented via an array**, **arrays are covariant and mutable**, and **non-reifiable generic type arguments are not deeply verified by the JVM**. When a `List<String>[]` array is returned or exposed externally, other code can replace a slot with a `List<Integer>` through `Object[]` without being stopped by the array store check. The violation may only surface at a `String` read site as a `ClassCastException`.

A more reliable design keeps the varargs array strictly local, reads or copies elements into a new structure, and returns a result with a clear contract. `@SafeVarargs` is an author's pledge made after auditing the method body, not an automatic transformation that makes broken code safe.

Further reading in official Java documentation:

- [JLS Java SE 17: SafeVarargs and heap pollution sections](https://docs.oracle.com/javase/specs/jls/se17/jls17.pdf)
- [Oracle Java Tutorials: Non-Reifiable Types and generic varargs](https://docs.oracle.com/javase/tutorial/java/generics/nonReifiableVarargsType.html)
- [Java API: SafeVarargs annotation](https://docs.oracle.com/en/java/javase/18/docs/api/java.base/java/lang/SafeVarargs.html)

**Practical rule:** Never treat a varargs array reference as a harmless value to return or store. Identify who is allowed to mutate the array, whether the element type is reifiable, and how the data will be used after the method returns.
