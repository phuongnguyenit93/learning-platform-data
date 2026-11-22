# `@SafeVarargs` Is a Safety Pledge, Not a Fix for the Method Body

## Lesson Objectives

In Java Generics, a method accepting **generic varargs** such as `List<String>... groups` can trigger warnings from `javac` because the varargs parameter is represented by an **array**, whereas `List<String>` is not a type that can be fully verified at runtime (*non-reifiable type*).

`@SafeVarargs` is an annotation allowing the author of certain constructors or methods to affirm that the implementation **performs no unsafe operations on varargs**. It can reduce warnings related to the declaration and call sites, yet **inserts no new runtime checks, adds no erased generic type information, sanitizes no data, and fixes no statements inside the method body**.

After this lesson, you will be able to:

- Explain accurately what `@SafeVarargs` means and the difference between an author's pledge and a runtime-enforced guarantee.
- Identify the risk sources of `List<T>...`: generic arrays, type erasure, array covariance, and heap pollution.
- Distinguish warnings at the **declaration**, **call site**, and **inside the method body**.
- See a method annotated with `@SafeVarargs` still throw `ClassCastException` due to an unsafe implementation.
- Write generic varargs methods that only read data, produce new typed results, and never let the varargs array escape.
- Know precisely which constructor/method kinds may carry the annotation in Java 17+.
- Decide when to remove `@SafeVarargs`, redesign the API, or replace varargs with a collection.
- Test the safety pledge against mismatched data, aliases, raw types, and consuming code.

All complete examples compile and run on **Java 17**; outputs from `javac`, `java`, and `javap` are distinguished clearly.

## 1. Definition and Proper Mindset for `@SafeVarargs`

Example declaration of a generic varargs method:

```java
@SafeVarargs
static <T> List<T> copyAll(List<? extends T>... groups) {
    List<T> result = new ArrayList<>();
    for (List<? extends T> group : groups) {
        result.addAll(group);
    }
    return List.copyOf(result);
}
```

The snippet above requires importing `java.util.ArrayList` and `java.util.List` inside a class; the complete program is in section 7.

What the annotation means is: the author has audited how the `groups` varargs parameter is used and **vouches that the method performs no unsafe operations on non-reifiable varargs elements**. The compiler cannot necessarily prove that pledge along every path; it trusts the pledge to suppress certain warnings at the declaration and call sites.

The annotation **does not**:

- Create a new runtime type `List<String>`.
- Turn `List<T>[]` into an array with a dedicated `List<T>` runtime component type.
- Automatically fix wrong assignments or casts.
- Validate every element of the `List`s at runtime.
- Automatically turn an implementation causing **heap pollution** into a safe one.
- Prevent `ClassCastException` if code still reads or casts mismatched data.

In other words, `@SafeVarargs` is like a **pledge about the method**, not a data-conversion tool, nor an instruction telling the JVM to "turn on runtime generics."

## 2. Why Can't the Annotation Fix the Method Body?

A `List<String>...` parameter is `List<String>[]` in source code, yet the runtime array only checks the `List` component, not `String`. When a method uses an `Object[]` alias to overwrite a slot with a `List<Integer>`, the JVM accepts the write; a caller reading an element as `String` then throws `ClassCastException`.

```java
// Inside a static varargs method with List imported:
Object[] alias = groups;     // Same array.
alias[0] = List.of(99);      // Runtime component is List.
String text = groups[0].get(0); // Wrong type on read.
```

`@SafeVarargs` **does not change** assignments, casts, body bytecode, or the runtime component type. It only states the author's pledge so the compiler reduces certain varargs warnings at the declaration and callers. The compiler can still emit `[varargs]` inside the body when it spots array aliasing or escape. Thus, in this lesson the decisive question is **does the pledge match the actual implementation?** — even when Java permits the annotation syntactically.

## 3. Heap Pollution Is the Risk to Evaluate

**Heap pollution** occurs when a variable of a parameterized type points to data or an object incompatible with the type argument promised by that variable. For example, `List<String>[]` is used to read `List<String>` values, while one slot of the actual array holds `List<Integer>`.

Do not confuse three things:

1. **An `unchecked` warning**: the compiler cannot fully guarantee the type safety of an operation. It does not prove heap pollution has definitely happened.
2. **Heap pollution**: the source-level type promise has been violated for the actual object/data; a runtime failure might not have occurred yet.
3. **`ClassCastException`**: a concrete runtime cast fails, which may be a consequence of heap pollution or a non-generic invalid cast.

An `Object[]` pointing to a `String[]` that receives an `Integer` throws `ArrayStoreException` immediately on write, because the JVM knows the real component type is `String`. Yet an `Object[]` pointing to a varargs `List<String>[]` array whose runtime component is `List` **does not** know about `String` elements inside the lists, so writing `List<Integer>` slips through.

Never conclude from one safe example that every generic varargs method is always safe, nor conclude from a warning that every call is guaranteed to fail. You must read **the method body and the data flow**.

## 4. Counterexample: Annotated with `@SafeVarargs` Yet Still Broken

Create the file **`FalsePromiseDemo.java`**:

```java
import java.util.List;

public final class FalsePromiseDemo {
    @SafeVarargs
    static List<String>[] corrupt(List<String>... groups) {
        Object[] alias = groups;
        alias[0] = List.of(99);
        return groups;
    }

    public static void main(String[] args) {
        List<String> original = List.of("safe");
        List<String>[] result = corrupt(original);

        System.out.println("original: " + original);
        System.out.println("array component: "
                + result.getClass().getComponentType().getName());

        try {
            String bad = result[0].get(0);
            System.out.println(bad);
        } catch (ClassCastException ex) {
            System.out.println("broken promise: "
                    + ex.getClass().getSimpleName());
        }
    }
}
```

Compile and run:

```bash
javac -Xlint:all FalsePromiseDemo.java
java FalsePromiseDemo
```

**Verified stdout:**

```text
original: [safe]
array component: java.util.List
broken promise: ClassCastException
```

Pay close attention: the file **compiles** even though the annotation makes a false promise. The compiler may warn about certain operations inside the method body, yet Java does not turn dangerous code safe simply because the annotation is present.

### Step-by-Step Path to Failure

1. `main` creates `original`, a `List<String>` containing `"safe"`.
2. Calling `corrupt(original)` uses varargs. Packing the single argument into an array produces a runtime array with component type `java.util.List`.
3. `Object[] alias = groups` creates **a second reference to the same array**. No array copy is made and individual lists are not copied.
4. `alias[0] = List.of(99)` replaces slot 0 of **the array** with a new list holding an `Integer`. The runtime array store check accepts it because the new list is still a `List`.
5. The method returns `groups`, handing the **polluted array** to the caller under source contract `List<String>[]`.
6. `String bad = result[0].get(0)` expects a `String`, but the actual value is an `Integer`; the compiler generated the required cast, resulting in `ClassCastException`.

The line:

```text
original: [safe]
```

also highlights an important debugging detail: the code above **did not** insert `99` into `original` itself. It replaced the reference in a **slot of the varargs array**. `original` still holds the initial string, while `result[0]` now points to a different list.

If you only inspected `original`, you might think everything was safe. Therefore, when evaluating generic varargs, track the **varargs array** and the **collections referenced inside the array** separately.

## 5. The Compiler Can Still Warn About Dangerous Code in the Body

In `FalsePromiseDemo.java`, running `javac -Xlint:all` emitted `[varargs]` warnings on two expressions:

```java
Object[] alias = groups;
return groups;
```

Verified representative warning:

```text
warning: [varargs] Varargs method could cause heap pollution from non-reifiable varargs parameter groups
```

On the JDK 17 build tested, the program emitted **two** `[varargs]` warnings: one on the alias assignment and one on returning the varargs array. File paths and line numbers depend on your compilation environment; the lesson is that **the compiler detects specific potentially unsafe operations**.

This simultaneously proves two points:

- `@SafeVarargs` can suppress certain **unchecked warnings at the declaration or call site**, yet it does not "silence every diagnostic about varargs."
- When the **method body** performs dangerous operations, the compiler can still emit `[varargs]` if appropriate lint flags are enabled; even without a warning, code can still be wrong and must be verified by reasoning.

Never judge a method safe simply because no warning appears in a default build. Warning output depends on `javac` flags and JDK versions; what matters more is **whether the method body exposes, mutates, swaps, or passes the varargs array along an uncontrolled path**.

## 6. Control Case: Without the Annotation, Where Do Warnings Appear?

Create the file **`UnannotatedWarningDemo.java`**:

```java
import java.util.List;

public final class UnannotatedWarningDemo {
    static void print(List<String>... groups) {
        for (List<String> group : groups) {
            System.out.println("group: " + group);
        }
    }

    public static void main(String[] args) {
        print(List.of("ok"));
    }
}
```

Run:

```bash
javac -Xlint:all UnannotatedWarningDemo.java
java UnannotatedWarningDemo
```

Application stdout:

```text
group: [ok]
```

On the tested Java 17 build, `javac -Xlint:all` emitted two `[unchecked]` warnings:

```text
Possible heap pollution from parameterized vararg type List<String>
unchecked generic array creation for varargs parameter of type List<String>[]
```

One warning is at the **method signature**, and one is at the **call site** where the generic varargs array must be created. This `print` method only reads and iterates over `List<String>`; the warnings reflect the limits of proving varargs type safety, not that `print` itself corrupted data.

Once you have verified that an eligible method like `print` truly causes no heap pollution, you may consider `@SafeVarargs` to publish that pledge. Conversely, if you have not proven it safe, keep the warnings, improve the body, or change the API design.

## 7. Proper Program: Using `@SafeVarargs` with a Safe Method Body

Create the file **`SafeVarargsContractDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public final class SafeVarargsContractDemo {
    @SafeVarargs
    static <T> List<T> copyAll(List<? extends T>... groups) {
        List<T> result = new ArrayList<>();
        for (List<? extends T> group : groups) {
            result.addAll(group);
        }
        return List.copyOf(result);
    }

    @SafeVarargs
    static <T> List<T> copyArrayElements(T... elements) {
        List<T> result = new ArrayList<>();
        for (T element : elements) {
            result.add(element);
        }
        return List.copyOf(result);
    }

    public static void main(String[] args) {
        System.out.println("strings: "
                + copyAll(List.of("An"), List.of("Binh")));

        List<Number> numbers = copyAll(
                List.of(1, 2), List.of(3.5));
        System.out.println("numbers: " + numbers);

        System.out.println("elements: "
                + copyArrayElements("A", "B"));
    }
}
```

Compile and run:

```bash
javac -Xlint:all SafeVarargsContractDemo.java
java SafeVarargsContractDemo
```

**Verified stdout:**

```text
strings: [An, Binh]
numbers: [1, 2, 3.5]
elements: [A, B]
```

During the test compile with `-Xlint:all`, this program **emitted zero warnings**. Yet what makes the methods safe is not merely having zero warnings: **the implementation itself** is why the annotation can be applied responsibly.

### Reviewing `copyAll`

- Reads `groups`; never writes into array slots.
- Never casts `groups` to `Object[]` to replace elements.
- Never returns the varargs array itself, never stores it in a field, and never passes it to code that could retain or mutate it.
- For each `List<? extends T>`, only reads elements as `T`; never pushes mismatched elements into the source lists.
- Creates a fresh `ArrayList<T>`, appends compiler-checked elements, and returns a copy via `List.copyOf`.
- `List.copyOf` produces a list that forbids direct mutation through list APIs; if `T` is a mutable object, **elements do not automatically become deeply immutable**.

From an API perspective, the wildcard `? extends T` also expresses the **producer** role of each source list: elements are read from the source and added into the result list.

### Reviewing `copyArrayElements`

The method iterates over each `T` element in the `elements` varargs array, builds a new list, and never pollutes the array. For ordinary typed calls, it neither stores incompatible values into the array nor exposes the array for external mutation.

It does not overwrite or replace `elements` slots, and does not cast or insert objects outside the generic contract. This is a clean example of **copy data out, do not leak the varargs array**.

For both methods, the contract must also state how `null` is handled: `List.copyOf` rejects `null` elements. That is an API policy independent of generic varargs safety; if you wish to support `null`, choose a different return representation and document the contract clearly.

## 8. Which Methods/Constructors Can Carry `@SafeVarargs`?

Java permits `@SafeVarargs` on **constructors** and methods that **cannot be overridden** under language rules. Specifically:

| Target | Eligible? | Why |
| --- | --- | --- |
| `static` varargs method | Yes | No ordinary overriding |
| `final` instance varargs method | Yes | Cannot be overridden |
| `private` instance varargs method (Java 9+) | Yes | Cannot be overridden |
| Varargs constructor | Yes | Constructors are not overridden |
| Overridable public/protected instance varargs method | No | Overrides could break the pledge |
| Non-varargs method | No | Annotation applies only to variable-arity declarations |
| Reifiable `String...` | Eligible syntactically, yet redundant | Compiler may emit `Redundant SafeVarargs annotation` |

The purpose of this restriction is not mere syntax: if a subclass could override a method with a body causing heap pollution, the pledge attached to the superclass method would not hold when dispatching to the override.

### Checking with Java 17

The example below compiles with a **redundant annotation** warning on the `String...` constructor:

```java
public final class AnnotationEligibility {
    @SafeVarargs
    private <T> void privateMethod(T... values) {}

    @SafeVarargs
    public final <T> void finalMethod(T... values) {}

    @SafeVarargs
    public AnnotationEligibility(String... parts) {}

    public static void main(String[] args) {
        new AnnotationEligibility().privateMethod("ok");
    }
}
```

Commands:

```bash
javac -Xlint:all AnnotationEligibility.java
java AnnotationEligibility
```

The program prints no output. The Java 17 compiler verified emitting the corresponding warning:

```text
warning: [varargs] Redundant SafeVarargs annotation. Varargs element type String is reifiable.
```

Thus, `@SafeVarargs` is **unnecessary** when the varargs component is already reifiable like `String`; a runtime `String[]` array already enforces its component type.

### Invalid Declarations — For Analysis Only

Do not copy the snippets below as a runnable program:

```java
class InvalidExamples {
    // ERROR: overridable public instance method.
    // @SafeVarargs
    // public <T> void overridable(T... values) {}

    // ERROR: method does not accept varargs.
    // @SafeVarargs
    // static <T> void ordinary(java.util.List<T> values) {}
}
```

Restricting `@SafeVarargs` to eligible declarations does not prove an eligible method's body is safe. For example, `FalsePromiseDemo.corrupt` is `static`, so placing the annotation is **syntactically valid**, yet its body intentionally breaks the contract.

## 9. What Does `@SafeVarargs` Change at Compile Time?

Distinguish **warning levels** from **program behavior**:

| Aspect | Without Annotation | With Valid `@SafeVarargs` |
| --- | --- | --- |
| Generic varargs declaration | May emit unchecked warning | Compiler may omit declaration warning |
| Invocation creating a generic varargs array | May emit unchecked warning | Compiler may omit call-site warning based on author's pledge |
| Method body with dangerous alias/write/return | Still dangerous | **Still dangerous**; `-Xlint:varargs` may warn |
| Erasure in bytecode | Still erases generic type arguments | Still erases generic type arguments |
| Runtime component type of varargs array | Typically erased `List` component | **Unchanged** |
| An invalid runtime cast | May still throw exception | **Not prevented by annotation** |

In `FalsePromiseDemo`, lacking an unchecked warning at the call site **does not** make `alias[0] = List.of(99)` safe. `[varargs]` warnings inside the body help reveal problems, yet never replace the API designer's responsibility.

Nor should you compare warning counts between two files to decide which is safer when their bodies differ. Inspect the **data flow**, then use warnings as a supporting tool.

## 10. Inspecting Runtime and Bytecode with `javap`

After compiling `FalsePromiseDemo.java`, run:

```bash
javap -s -p FalsePromiseDemo
```

Excerpt from actual verification:

```text
static java.util.List<java.lang.String>[] corrupt(java.util.List<java.lang.String>...);
  descriptor: ([Ljava/util/List;)[Ljava/util/List;
```

Reading the descriptor:

- `[` denotes an array.
- `Ljava/util/List;` denotes a `List` in a JVM descriptor.
- `([Ljava/util/List;)[Ljava/util/List;` means it takes and returns a **`List[]` array** in the erased descriptor.

`javap` can display `List<String>...` from generic `Signature` metadata, yet runtime array element checks only have component type `List`. That is the fundamental reason the annotation cannot make `String` reappear in the runtime descriptor.

To see what the method actually executes:

```bash
javap -c -p FalsePromiseDemo
```

Look for array load instructions, `aastore` performing array stores, and `checkcast java/lang/String` at reads/casts dictated by the source type. Bytecode offsets and constant-pool indices vary across `javac` versions; base your conclusions on **opcodes and descriptors**, not exact line numbers.

`@SafeVarargs` is also an annotation visible in class-file metadata, yet an annotation entry **does not rewrite an instruction sequence** containing corrupting writes.

## 11. Red Flags When Reviewing Generic Varargs Methods

Examine these operations carefully before adding or keeping `@SafeVarargs`:

**Red Flag A — Upcasting the varargs array to `Object[]`.**

```java
Object[] alias = groups;
```

An alias reference by itself does not necessarily corrupt data immediately. However, it opens the door to writing elements incompatible with the erased type arguments, as shown in `FalsePromiseDemo`.

**Red Flag B — Writing into a slot of the varargs array.**

```java
alias[0] = List.of(99);
```

When `groups` is declared `List<String>...`, this swaps a `List<Integer>` into a position callers may assume is `List<String>`.

**Red Flag C — Returning the varargs array itself to the caller.**

```java
return groups;
```

Returning the array can expose it so callers or other code mutate it later. Risk depends on signature, ownership, and caller behavior; this is why APIs retaining or returning uncontrolled varargs arrays should be avoided.

**Red Flag D — Storing the array in a shared field.**

```java
// Illustrating a dangerous design:
Object[] saved = groups;
```

If that state outlives the call or is accessed by other code, the array can be modified unexpectedly. Consider a properly typed snapshot/collection with clear mutation rules.

**Red Flag E — Passing the array to a helper with an unclear contract.**

```java
untrustedHelper(groups);
```

A helper could retain the array, cast to `Object[]`, or replace elements. Having no direct `aastore` in the current method is insufficient grounds to claim safety.

**Red Flag F — Unchecked casts / raw operations.**

```java
// Example requiring array declaration context:
@SuppressWarnings("unchecked")
List<String>[] assumed = (List<String>[]) someArray;
```

Unchecked casts do not validate each `List` element; suppression is not proof of actual types. Verify the data source or change the design.

## 12. When to Use a Collection Instead of Varargs?

Not every API needs `List<T>...`. When callers already hold a dynamic collection, a method accepting a collection is often clearer:

```java
static <T> List<T> flatten(
        List<? extends List<? extends T>> groups) {
    List<T> out = new ArrayList<>();
    for (List<? extends T> group : groups) {
        out.addAll(group);
    }
    return List.copyOf(out);
}
```

This is an illustrative method snippet; import `java.util.List` and `java.util.ArrayList` and place it in a suitable class. A caller holding `List<List<String>>` can pass the list of groups under a compatible contract without creating a generic varargs array at invocation.

Another option is accepting a single source collection:

```java
static <T> List<T> snapshot(
        java.util.Collection<? extends T> source) {
    return List.copyOf(source);
}
```

Benefits of dropping varargs when unnecessary:

- No `@SafeVarargs` pledge is needed.
- Avoids creating a varargs array of a non-reifiable element type at the call site.
- The API clearly communicates a dynamic source collection rather than a list of separate arguments.
- Ownership (snapshot, read-only view, or live collection) and `null` policies are easier to express.

However, switching to a collection **does not** automatically prevent raw types, unchecked casts, or wrong-type data from external sources. Type safety still depends on sound contracts and boundary validation when inputs are untrusted.

## 13. What to Do When Source Data Might Already Have Wrong Types?

Suppose a legacy library returns a raw `List`, or a deserializer supplies an unvalidated list. Putting `@SafeVarargs` on a method receiving that data **does not verify** that the list actually holds `String`s.

A sample adapter:

```java
static List<String> checkedStrings(List<?> input) {
    List<String> result = new ArrayList<>();
    for (int i = 0; i < input.size(); i++) {
        Object item = input.get(i);
        if (!(item instanceof String s)) {
            throw new IllegalArgumentException(
                    "Invalid String element at index " + i);
        }
        result.add(s);
    }
    return List.copyOf(result);
}
```

This illustrative method uses `List` and `ArrayList` from `java.util` and can be placed inside a class to run. It performs **element-by-element validation**, rejects mismatched values and `null`, and returns a new typed collection without any unchecked cast.

Additional notes:

- A `List<?>` lets you iterate over elements as `Object` while preventing arbitrary writes through that reference.
- `List<String>` in the return signature is a **post-validation guarantee**, not the result of a blind cast.
- If the input collection can be mutated concurrently, use appropriate synchronization or snapshotting; a plain validation loop is not an atomic snapshot.
- If elements inside are mutable objects, copying the list does not automatically provide deep immutability.

Placing an adapter at the boundary ensures type errors are caught immediately upon ingest rather than surfacing downstream when generic code relies on a broken promise.

## 14. Important Misconceptions

### "Any method with `@SafeVarargs` has been proven safe by the compiler"

False. It is an **author's pledge**, and the compiler cannot verify every state or data path. `FalsePromiseDemo` carries a syntactically valid annotation on a `static` method while actively causing heap pollution.

### "`@SafeVarargs` eliminates all warnings"

False. `javac -Xlint:all` can still emit `[varargs]` warnings for dangerous array aliasing or returns inside an annotated method. Raw types and unchecked casts elsewhere can also continue producing warnings.

### "With no warnings, runtime cannot throw `ClassCastException`"

False. No warnings does not mean the JVM checks all generic type arguments. `ClassCastException` can still come from bad casts or data corrupted along a path the compiler could not inspect.

### "The annotation turns `List<String>...` into an array checking `String` at runtime"

False. The runtime component type is erased to `List`; a `List<Integer>` is still a `List` at the runtime array-store level.

### "Only mutating an individual `List` is dangerous; mutating the array is harmless"

False. You can break a generic reference by **replacing a varargs array slot**, even when the `original` list itself is untouched.

### "Seeing `ClassCastException` means the method body definitely caused heap pollution"

Not necessarily. Bad casts unrelated to generics can also throw it. To find the root cause, trace where invalid data entered and where the type contract broke.

### "`@SafeVarargs` works on any instance method"

False. The annotation is only allowed on declarations meeting non-overridable rules such as `final`, `private` (Java 9+), or `static`, plus constructors. Overridable instance methods are ineligible.

### "With a reifiable varargs type like `String...`, the annotation makes it even safer"

Usually **unnecessary**. A runtime `String[]` already preserves its component type, and `javac` may report a redundant annotation.

### "One passing test proves `@SafeVarargs` is justified"

Insufficient. Tests often exercise only a few happy paths. Audit aliasing, writes, array escape, helper calls, and wrong-type inputs; a passing build does not replace reasoning about the method body.

## 15. Review Workflow for an `@SafeVarargs` Method

When encountering an annotated method in a codebase:

1. **Read the signature:** is the varargs component non-reifiable? For example `List<T>`, `List<String>`, or just `String`?
2. **Check annotation eligibility:** is it a constructor, `static`, `final`, or `private` method valid under your target Java version?
3. **Find every alias assignment:** `Object[] a = args`, array casts, storing the reference in a field, returning the array.
4. **Find every write to an array slot:** `args[i] = ...`, `a[i] = ...`; evaluate the chance of writing a value with the wrong generic argument.
5. **Find helpers receiving the array:** could any helper retain/mutate the array, return it, or pass it to untrusted code?
6. **Inspect generic casts/raw conversions:** is there valid proof that data has the expected type?
7. **Enable compiler lint:** `-Xlint:rawtypes`, `-Xlint:unchecked`, `-Xlint:varargs`; inspect warnings in the method body.
8. **Test with bad data and typed reads:** verify no heap pollution occurs with mixed element types.
9. **Evaluate alternative APIs:** snapshots, `Collection<? extends T>`, suitable overloads, or type tokens when truly needed.
10. **Keep the annotation only with a safety argument:** document the method's invariants so future maintainers understand why it is valid.

Note: a currently safe method can change later. Whenever refactoring the body of an `@SafeVarargs` method, **re-verify the pledge** rather than treating the annotation as permanent decoration.

## 16. Practice Questions and Answers

**Exercise 1 — Direct Effect of the Annotation**

```java
@SafeVarargs
static void f(List<String>... values) { /* ... */ }
```

Does `@SafeVarargs` automatically add runtime checks for every `String` element?

**Answer:** no. It is the author's guarantee regarding safe varargs usage; the array's runtime component type remains erased to `List`.

**Exercise 2 — Spotting a Broken Path**

An annotated method writes `Object[] x = groups; x[0] = List.of(7);` when `groups` has type `List<String>...`. Can this method be considered safe?

**Answer:** no. That array slot holds a list whose actual type argument is incompatible with `List<String>`; if callers read as `String`, `ClassCastException` can result.

**Exercise 3 — Meaning of Body Warnings**

Why can `javac -Xlint:all` still emit `[varargs]` warnings when a method already has `@SafeVarargs`?

**Answer:** the annotation suppresses certain declaration/call-site warnings based on the pledge, yet the compiler can still flag risky array aliasing or return operations in the body. It is not a mechanism that disables all warnings.

**Exercise 4 — Where the Annotation Can Be Placed**

In Java 17, given constructors, `private` varargs, `static` varargs, `final` instance varargs, and overridable `public` instance varargs — which are eligible?

**Answer:** the first four are eligible; an overridable `public` instance method is ineligible. Syntactic eligibility does not substitute for proof of body safety.

**Exercise 5 — Comparing Two Array Types**

Why can `Object[] x = groups; x[0] = List.of(7)` succeed with `List<String>...`, while `Object[] a = new String[1]; a[0] = 7` throws `ArrayStoreException`?

**Answer:** the varargs array's runtime component type is `List`, so `List.of(7)` is still a `List`; by contrast, a `String[]` array has component type `String` and rejects `Integer`.

**Exercise 6 — Which Implementation Pattern Fits?**

A static varargs method only iterates over `List<? extends T>... groups`, builds a new `ArrayList<T>`, and returns `List.copyOf` without retaining or mutating the array. Can `@SafeVarargs` be applied?

**Answer:** yes, after verifying all paths in the body. That is the safe pattern in `SafeVarargsContractDemo`; there are no slot-swapping operations or array escapes.

**Exercise 7 — Fixing a Broken Method**

What is the minimal way to fix `FalsePromiseDemo.corrupt` to avoid heap pollution?

**Answer guide:** do not cast the varargs array to `Object[]` to swap elements, do not write `List<Integer>` into an array callers trust as `List<String>[]`, and do not return an uncontrolled array. If collecting results is needed, iterate over the inputs and return a new `List<String>` or `List<List<String>>` per contract; then re-evaluate whether varargs or the annotation is even needed.

**Exercise 8 — Re-Checking After Refactoring**

An `@SafeVarargs` method previously only read varargs; after an optimization, the author passes the array to a new helper for caching. Can the annotation be kept without re-reviewing?

**Answer:** no. The helper may retain or mutate the array, invalidating the old pledge. You must analyze array ownership, aliases, and all read/write paths before keeping the annotation.

## End-of-Lesson Checklist

Before adding `@SafeVarargs`, confirm to yourself:

- [ ] The varargs declaration is valid and the method/constructor is eligible for the annotation.
- [ ] You know which type arguments are non-reifiable and what the actual runtime array component type is.
- [ ] The body never writes incompatible elements into the varargs array.
- [ ] The body never passes the varargs array down a path where it could be mutated or retained outside your control.
- [ ] Casts or unchecked conversions inside the body are soundly justified or replaced with safe typed alternatives.
- [ ] Any helpers called by the method do not violate the pledge.
- [ ] You compiled with appropriate lint flags and investigated every meaningful warning.
- [ ] You tested incompatible data and typed read paths that could throw `ClassCastException`.
- [ ] If varargs is unnecessary, you considered using a collection or wildcard alternative instead.
- [ ] Whenever the implementation changes, you will re-audit the entire safety pledge.

## Conclusion

**`@SafeVarargs` is a responsible pledge by the API author that generic varargs handling does not compromise type safety; it is not an automatic code-fixing tool.** Because varargs is implemented as an array with an erased generic component type, a method writing bad data through `Object[]` still causes heap pollution and `ClassCastException` even when annotated. Choose an implementation that neither mutates nor exposes the varargs array, build new typed results where appropriate, enable lint, and verify the data flow — only then apply `@SafeVarargs` to express a truthful pledge.
