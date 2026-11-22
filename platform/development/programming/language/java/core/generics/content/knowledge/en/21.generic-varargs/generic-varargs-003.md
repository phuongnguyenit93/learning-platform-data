# Declaration and Call-Site Warnings for Varargs Methods in Java Generics

## 1. Opening Scenario

Java allows methods to accept a variable number of arguments (*varargs*) using `...`:

```java
static void show(String... values) {
    for (String value : values) {
        System.out.println(value);
    }
}
```

Invocation:

```java
show("Java", "Generics");
```

is convenient because the caller does not have to construct a `String[]` manually. When varargs is combined with **Generics**, the situation becomes more intricate:

```java
static void showFirst(List<String>... lists) {
    System.out.println(lists[0].get(0));
}

// In another method:
showFirst(List.of("Java"), List.of("Generics"));
```

`javac` can emit **two warnings at two different places**:

- **At the declaration** `List<String>... lists`: `Possible heap pollution from parameterized vararg type List<String>`.
- **At the call site** `showFirst(...)`: `unchecked generic array creation for varargs parameter of type List<String>[]`.

Both relate to the **varargs array and type erasure** mechanism, yet neither means the compiler has found an actual bug in your data. They are signals: the array type used to pass arguments has a **non-reifiable** component type, so the compiler and runtime cannot verify every type argument through an array store check.

This lesson explains when the warnings appear, why they point to different sites, when *heap pollution* risk exists, how to read `javac -Xlint`, how to distinguish reifiable varargs from generic varargs, and how to design or annotate APIs safely with `@SafeVarargs` when justified.

## 2. Varargs Is Actually an Array Parameter

In source code:

```java
static void printAll(String... items) {
    for (String item : items) {
        System.out.println(item);
    }
}
```

The `items` parameter **inside the method** has type `String[]`. The call:

```java
printAll("a", "b");
```

is normally compiled as a call passing a `String[]` array holding the arguments.

You can also call it with an existing array:

```java
String[] names = {"a", "b"};
printAll(names);
```

A varargs method essentially has an array parameter in the final position; therefore:

```java
static void take(List<String>... groups) {
    System.out.println(groups.length);
}
```

has a `groups` parameter whose source type is **`List<String>[]`**, even though it is written with `...` syntax.

The catch: Java forbids ordinary array creation expressions like:

```java
// Invalid:
List<String>[] array = new List<String>[2];
```

because `List<String>` is not a **reifiable type**. Yet varargs syntax lets the compiler handle `take(List.of("a"), List.of("b"))` using a runtime array with component type `List`. That is precisely why a warning is needed.

### 2.1. Two Ways to Call Varargs

Suppose:

```java
static void count(String... words) {
    System.out.println(words.length);
}
```

There are two important invocation forms:

```java
count("a", "b");                 // Variable-arity invocation.
count(new String[] {"a", "b"});  // Fixed-arity invocation with a real array.
```

In the first form, the compiler packs the arguments into an array. In the second form, the caller explicitly supplies the array.

With `List<T>...`, the **call-site** warning primarily targets cases where the compiler must **implicitly** create a varargs array with a non-reifiable component type. A call that passes an existing array might not trigger the exact "unchecked generic array creation" warning on that call line, yet where that array came from must still be inspected. Never conclude an API is safe simply because a call line has no warning.

## 3. Why Does the Varargs Component Type Matter?

Java arrays retain their runtime component type:

```java
String[] strings = new String[1];
Object[] alias = strings;
alias[0] = 123; // ArrayStoreException.
```

The JVM knows the real array is `String[]` and rejects an `Integer` value.

However, with:

```java
List<String> words = List.of("Java");
List<Integer> ids = List.of(123);
```

both `List<String>` and `List<Integer>` share the underlying runtime interface `List`; type arguments are not specialized into distinct runtime classes.

Hence, if an array holds `List` instances and code stores a `List<Integer>` into a slot that other code **believes** is `List<String>`, the array store check only verifies that the object is a `List` — it does not inspect every element inside.

In the varargs case:

```java
static void method(List<String>... groups) {
    // Inside the method, groups is List<String>[] in source code.
}
```

type erasure means the JVM has no separate runtime component class for `List<String>`. The compiler warns that internal code or aliases could break the element contract of the array/lists.

### 3.1. Reifiable vs. Non-Reifiable

| Varargs Type | Array Component Type | Typical Unchecked Varargs Warning? |
| --- | --- | --- |
| `String... values` | Reifiable `String` | No |
| `int... values` | Primitive `int` | No |
| `List<?>... groups` | Reifiable `List<?>` | No, unless other unchecked operations exist |
| `Map<?, ?>... maps` | Reifiable `Map<?, ?>` | Not from the varargs component itself |
| `List... groups` | Reifiable raw `List` | Not for non-reifiable component; may emit `rawtypes` warning |
| `List<String>... groups` | Non-reifiable `List<String>` | May warn at declaration and call site |
| `List<? extends Number>... groups` | Bounded wildcard, non-reifiable | May warn |
| `<T> void run(T... values)` | Non-reifiable `T` | May warn |
| `<T> void run(List<T>... groups)` | Non-reifiable `List<T>` | May warn |

**`?` only suffices for reifiability when it is a completely unbounded wildcard and every type argument in the parameterized type is unbounded.** `List<? extends Number>` is still non-reifiable; do not treat it as equivalent to `List<?>`.

A warning attached to a varargs component **does not mean** all generic code is unsafe. For example, `<T> T first(List<T> values)` is not varargs, so it has no implicit array mechanism.

## 4. Warnings at the Method Declaration

Look at:

```java
static void printFirst(List<String>... groups) {
    System.out.println(groups[0].get(0));
}
```

When enabling:

```bash
javac --release 17 -Xlint:unchecked VarargsWarningDemo.java
```

`javac` emits a warning at the varargs declaration:

```text
warning: [unchecked] Possible heap pollution from parameterized vararg type List<String>
```

This message means **structurally**, the final parameter is represented as an array with a non-reifiable `List<String>` component, and heap pollution *could* occur through unsafe operations on the array or an alias.

It does not prove that `printFirst`'s body actually wrote any wrong element. If it only reads and never lets the array escape, the method may in fact be safe. The compiler still warns because the declared type opens the door to unchecked operations.

### 4.1. Method Declarations with Their Own Type Parameter

```java
static <T> int countElements(List<T>... groups) {
    int total = 0;
    for (List<T> group : groups) {
        total += group.size();
    }
    return total;
}
```

Here `T` is the **method's** type parameter, while each varargs argument is a `List<T>`. `List<T>` is non-reifiable, so the compiler emits the warning:

```text
warning: [unchecked] Possible heap pollution from parameterized vararg type List<T>
```

Do not confuse a method type variable with an array element. Java has no way to create a runtime array class with a `List<T>` component specialization where `T` varies per call.

### 4.2. Declaration Warnings Can Appear Even When the Method Body Only Reads

```java
static <T> int countElements(List<T>... groups) {
    int result = 0;
    for (List<T> group : groups) {
        result += group.size();
    }
    return result;
}
```

The method only reads `size` and modifies neither `groups` nor any inner list. The risk in this implementation is low if no external alias modifies the array. Still, the compiler is not a general theorem prover for every generic varargs method design.

What you should do is **review invariants and array handling**: are slots written to, is the array exposed to other code, is it aliased as `Object[]`, is it cast or passed to untrusted APIs? Only after that review should you consider `@SafeVarargs` if the method qualifies.

## 5. Warnings at the Method Call Site

Definition:

```java
static void printFirst(List<String>... groups) {
    System.out.println(groups[0].get(0));
}
```

The call:

```java
printFirst(List.of("Java"), List.of("Generics"));
```

can emit the warning:

```text
warning: [unchecked] unchecked generic array creation for varargs parameter of type List<String>[]
```

The exact message text can vary depending on type inference context, but the meaning is: the compiler has to supply an array holding the varargs arguments whose source component type is `List<String>` — a non-reifiable type — so creating or passing that array across the varargs boundary is not fully generically checked.

**Key distinction:** the declaration warning says the API accepts varargs with a non-reifiable component type; the call-site warning says **right here** the compiler is creating/supplying a non-reifiable varargs array.

### 5.1. Type Inference Gives Call-Site Messages a Concrete Type

With:

```java
static <T> int countElements(List<T>... groups) {
    int count = 0;
    for (List<T> group : groups) count += group.size();
    return count;
}
```

The call:

```java
countElements(List.of("A", "B"), List.of("C"));
```

when `javac` infers `T = String`, can produce:

```text
warning: [unchecked] unchecked generic array creation for varargs parameter of type List<String>[]
```

At the declaration, the message uses `List<T>`; at the call site, type inference has resolved `String`, so the message can display `List<String>[]`. This is not a contradiction: the same risk is viewed from **two different contexts**.

Do not conclude that because the caller constructed `List.of("A")` with generic type safety, the `List<String>[]` varargs array must be reifiable. Constructing a collection safely and **packing it into a generic array** are two separate concerns.

### 5.2. One Method Can Produce Both Warnings

Enabling lint on the same file can show warnings at both the definition line:

```java
static void printFirst(List<String>... groups) { ... }
```

and the usage line:

```java
printFirst(List.of("Java"));
```

Two warnings do not mean the compiler is double-counting a single mistake. They reflect **two risk surfaces**: API design and array creation at the caller.

You might address one while leaving the other exposed if the method or other call sites continue using an unchecked structure.

## 6. Why Does the Compiler Warn Even When the Body Looks Harmless?

A method that only reads `size()` on `List<String>...` can run cleanly and still carry **declaration/call-site warnings**: the `String` type argument is non-reifiable in the array prepared for the varargs call. Heap pollution only **actually occurs** when a write or cast path causes a generic variable to hold data violating its contract.

Typical failure path:

```java
static void corrupt(List<String>... groups) {
    Object[] alias = groups;       // Same array, no copy.
    alias[0] = List.of(42);       // Runtime component is only List.
    String item = groups[0].get(0); // ClassCastException on read.
}
```

The illustrative method above requires `import java.util.List;`, must live inside a class, and is **not for production**. If you tried writing a `String` directly into a runtime `List[]` array, the JVM could indeed throw `ArrayStoreException`. Thus, the array store check **still exists**, it simply cannot inspect the generic argument inside `List`.

When diagnosing, do not infer from a warning that the code is definitely corrupting data. Locate any concrete write/escape operations first, then decide whether you can commit to `@SafeVarargs` or should change the API. **The core takeaway of this lesson is the two warning sites**: the declaration describes the signature's risk; the call site describes creating a non-reifiable array for that call.

## 7. What Does `@SafeVarargs` Solve?

Java provides the annotation:

```java
@SafeVarargs
```

It is used when the author of a varargs method or constructor **promises** that the implementation performs no unsafe operations on the varargs array with a non-reifiable component.

Safe method example:

```java
@SafeVarargs
static <T> List<T> flatten(List<? extends T>... groups) {
    List<T> result = new ArrayList<>();
    for (List<? extends T> group : groups) {
        result.addAll(group);
    }
    return result;
}
```

This method:

- Only iterates over the source lists.
- Adds elements into a new `ArrayList<T>` via type-checked generic APIs.
- Does not write a mismatched list into the `groups` array.
- Does not expose the `groups` array for external code to mutate.
- Returns a **new list**, not the varargs array or an alias to it.

This is a case where using `@SafeVarargs` can be justified. With a valid annotation, the compiler can suppress *unchecked generic varargs* warnings at the **declaration and call sites** associated with that method.

**Important:** the annotation **does not** make `List<T>` reifiable, does not create a new runtime component type, does not validate individual elements, and does not prove the code safe on its own.

### 7.1. `@SafeVarargs` vs. `@SuppressWarnings("unchecked")`

`@SuppressWarnings("unchecked")` suppresses warnings within a specific scope and can apply to many kinds of unchecked operations.

`@SafeVarargs` is a specialized pledge for a varargs method or constructor about how its non-reifiable varargs parameter is used. It affects related varargs warnings, including at callers, yet it is not a JVM-enforced certificate.

Never slap `@SafeVarargs` onto a method merely to clean up lint output when the body still assigns aliases or stores mismatched lists into the array.

### 7.2. Annotation Placement Rules in Java 17

`@SafeVarargs` is permitted on:

- `static` varargs methods.
- `final` instance varargs methods.
- `private` instance varargs methods (allowed since Java 9).
- Constructors with a varargs parameter.

It is invalid on an **overridable** instance method and invalid on a **non-varargs** method.

Valid examples of **placement**:

```java
@SafeVarargs
static <T> void staticMethod(T... values) {
    // Implementation must guarantee safe handling.
}
```

```java
class Example {
    @SafeVarargs
    private final <T> void privateMethod(T... values) {
        // Must uphold the safety contract.
    }
}
```

The `private final` declaration here only illustrates allowed modifiers; `private` alone already satisfies annotation placement in Java 17. Do not confuse syntactic validity of the annotation with the method actually being safe.

### 7.3. The Compiler May Still Warn Inside the Method Even When Annotated

Consider an **unsafe** method where the annotation is placed in a semantically false way:

```java
@SafeVarargs
static <T> void lie(List<T>... groups) {
    Object[] alias = groups;
    alias[0] = List.of(42);
}
```

With:

```bash
javac --release 17 -Xlint:varargs -Xlint:unchecked UnsafeAnnotationDemo.java
```

`javac` has been verified to emit a warning on the alias line:

```text
warning: [varargs] Varargs method could cause heap pollution from non-reifiable varargs parameter groups
```

This shows that even when the annotation makes certain declaration/caller varargs warnings disappear, operations that look unsafe inside the body can still be flagged by `-Xlint:varargs`.

**Never leave this annotation in real code** when the method can violate type invariants. Fix the body's design, rather than merely silencing warnings.

## 8. Behaviors That Make a Varargs API Unsafe

When reviewing a method with `List<T>...` or `T...`, watch for:

### 8.1. Writing to the Array Through a Broader Alias

```java
Object[] alias = groups;
alias[0] = List.of(42);
```

This is the classic heap-pollution example with `List<T>[]`. Even if `groups` is declared `List<String>[]`, the runtime array only knows component `List`.

### 8.2. Returning the Varargs Array Directly

```java
@SafeVarargs // Not a recommendation to use the annotation here.
static <T> List<T>[] expose(List<T>... groups) {
    return groups;
}
```

If the array escapes to callers or other code that holds and mutates it, invariants can be broken. With `-Xlint:varargs`, the compiler may warn about letting a non-reifiable varargs array escape scope.

If the goal is returning data, consider returning a new `List<List<T>>` or a properly designed immutable/copied structure instead of exposing the varargs array.

### 8.3. Passing the Array to Untrusted Code

```java
static void forward(Object[] values) {
    // This method could replace elements in the array.
}
```

If a generic varargs method calls an API accepting `Object[]` and lets that API modify the array, you cannot claim varargs safety merely because the current code does not directly write `groups[0]`.

A *safe varargs method* must control both aliases and any methods called with the array. **Having no direct write in a few local lines is not enough** if the array can escape elsewhere.

### 8.4. Opening Write Access to Inner Lists

Even when the array itself is not overwritten, code using a raw alias of an individual list to add mismatched elements can still cause heap pollution:

```java
List raw = groups[0];
raw.add(42); // Unchecked call can break List<String>.
```

That is a raw-type issue combined with varargs. Avoid raw aliases, unchecked casts, and mutations when the type-argument contract is not guaranteed.

## 9. Reifiable Varargs: When Is `@SafeVarargs` Unnecessary?

### 9.1. `List<?>...`

```java
static int countUnknown(List<?>... groups) {
    int total = 0;
    for (List<?> group : groups) {
        total += group.size();
    }
    return total;
}
```

`List<?>` is reifiable because its type argument is an unbounded wildcard. Therefore, this varargs parameter does not hit the same warning about a non-reifiable component.

Valid call:

```java
int count = countUnknown(
        List.of("a"),
        List.of(1, 2)
);
// count == 3
```

The `?` prevents reading elements as a concrete type like `String` without checking first. Since this method only sums sizes, it does not need to know the type argument.

**Only replace `List<T>...` with `List<?>...` when the type relationship `T` is genuinely unnecessary.** If the method must link input types to an output type (`List<T>`), removing `T` can strip the API of meaningful type safety or type inference.

### 9.2. `String...`, `int...`

```java
static int sum(int... values) {
    int result = 0;
    for (int value : values) result += value;
    return result;
}
```

`int` is a reifiable primitive type. `String` is also reifiable. These varargs do not carry the **non-reifiable generic array component** risk of `List<T>...`.

A method could still have logic bugs or unwanted mutation, but not the unchecked generic array creation warning examined here.

### 9.3. `List<?>...` Is Not Equivalent to `List<String>...`

If an API must guarantee that all groups contain `String`, `List<?>...` does not enforce that. `List<?>` can hold `String`, `Integer`, `Boolean`, and other values. Changing the signature just to make warnings vanish can loosen the contract inappropriately.

When the same type `T` is required, use proper generics, or consider passing `List<? extends List<T>>` instead of varargs to avoid implicit arrays.

## 10. Complete Java 17 Example: Both Warning Sites

Create the file **`VarargsWarningDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class VarargsWarningDemo {
    static void printFirst(List<String>... batches) {
        System.out.println("first=" + batches[0].get(0));
    }

    static <T> int countElements(List<T>... batches) {
        int total = 0;
        for (List<T> batch : batches) total += batch.size();
        return total;
    }

    @SafeVarargs
    static <T> List<T> flatten(List<? extends T>... batches) {
        List<T> result = new ArrayList<>();
        for (List<? extends T> batch : batches) result.addAll(batch);
        return result;
    }

    static int countUnknown(List<?>... batches) {
        int total = 0;
        for (List<?> batch : batches) total += batch.size();
        return total;
    }

    static <T> T corruptAndRead(List<T>... batches) {
        Object[] alias = batches;
        alias[0] = List.of(42);
        return batches[0].get(0);
    }

    public static void main(String[] args) {
        printFirst(List.of("Java"), List.of("Generics"));

        System.out.println("count="
                + countElements(List.of("A", "B"), List.of("C")));

        System.out.println("flatten="
                + flatten(List.of(1, 2), List.of(3)));

        System.out.println("unknown="
                + countUnknown(List.of("x"), List.of(1, 2)));

        try {
            String item = corruptAndRead(List.of("safe"));
            System.out.println(item);
        } catch (ClassCastException ex) {
            System.out.println("pollution=" + ex.getClass().getSimpleName());
        }
    }
}
```

Note that `import java.util.Arrays` is unused in the body; it is a harmless extra import that can be removed when adapting code to a project. The three methods `printFirst`, `countElements`, and `corruptAndRead` **intentionally keep non-reifiable varargs signatures without `@SafeVarargs`** so learners can observe the warnings. Among them, `corruptAndRead` is deliberately unsafe; do not put it into production.

Compile:

```bash
javac --release 17 -Xlint:unchecked -Xlint:varargs VarargsWarningDemo.java
```

On the source above, `javac` emitted **6 warnings**:

| Location | Warning Category | Key Message |
| --- | --- | --- |
| Declaration of `printFirst(List<String>...)` | `[unchecked]` | `Possible heap pollution from parameterized vararg type List<String>` |
| Declaration of `countElements(List<T>...)` | `[unchecked]` | `Possible heap pollution from parameterized vararg type List<T>` |
| Declaration of `corruptAndRead(List<T>...)` | `[unchecked]` | `Possible heap pollution from parameterized vararg type List<T>` |
| Call `printFirst(...)` | `[unchecked]` | `unchecked generic array creation ... List<String>[]` |
| Call `countElements(...)` | `[unchecked]` | `unchecked generic array creation ... List<String>[]` |
| Call `corruptAndRead(...)` | `[unchecked]` | `unchecked generic array creation ... List<String>[]` |

There are no varargs warnings from `flatten(...)` because the annotation is used on a static method with a safe body in this example. `countUnknown(...)` needs no annotation because its `List<?>` component is reifiable.

Class names, line numbers, source paths, and some diagnostic formatting details can depend on the JDK. Focus on the **messages** and declaration/call-site locations rather than asserting that the caret always sits at the exact same column.

Run:

```bash
java VarargsWarningDemo
```

Exact stdout:

```text
first=Java
count=3
flatten=[1, 2, 3]
unknown=3
pollution=ClassCastException
```

### 10.1. Interpreting the Output

`first=Java` and `count=3` show that generic varargs methods can execute properly even when compiler warnings are present. The warnings report **structural risk**, not guaranteed data corruption.

`flatten=[1, 2, 3]` illustrates collecting elements into a new list without letting the varargs array escape or replacing it with a wrong-type list.

`unknown=3` proves an API using `List<?>...` can handle heterogeneous lists without needing a type variable linking them.

`pollution=ClassCastException` is the intentional consequence of the unsafe method: it writes a `List<Integer>` through an `Object[]` alias and the caller then uses the value as a `String`.

## 11. Example Showing `@SafeVarargs` Is Not a Safety Certificate

A separate illustrative file **`UnsafeAnnotationDemo.java`**:

```java
import java.util.List;

class UnsafeAnnotationDemo {
    @SafeVarargs
    static <T> void lie(List<T>... groups) {
        Object[] objects = groups;
        objects[0] = List.of(42);
    }

    static void invoke() {
        lie(List.of("ok"));
    }
}
```

Compile:

```bash
javac --release 17 -Xlint:varargs -Xlint:unchecked UnsafeAnnotationDemo.java
```

`javac` warned:

```text
warning: [varargs] Varargs method could cause heap pollution
from non-reifiable varargs parameter groups
```

The warning points at the operation using the alias of the varargs array. The annotation does not make the body safe and cannot guarantee that every compiler or toolchain will catch every real-world hazard.

**How to fix:** remove writable aliases; never replace lists in the varargs array with data carrying a different type argument; if only output data is needed, build a new collection with an explicit type.

### 11.1. Annotation Rejected on Invalid Methods

Error illustration file **`InvalidAnnotationDemo.java`**:

```java
import java.util.List;

class InvalidAnnotationDemo {
    @SafeVarargs
    void notFinal(List<String>... values) {
    }

    @SafeVarargs
    static void notVarargs(List<String> values) {
    }
}
```

Run:

```bash
javac --release 17 InvalidAnnotationDemo.java
```

The compiler rejects both cases:

```text
Invalid SafeVarargs annotation. Instance method ... is neither final nor private.
Invalid SafeVarargs annotation. Method ... is not a varargs method.
```

These examples demonstrate the syntactic constraints of `@SafeVarargs`; they **intentionally do not compile**.

Do not change `void notFinal` to `final void notFinal` just to get past the compiler if the method still causes heap pollution. The annotation requires both a **valid target** and a **valid safety guarantee**.

## 12. Handling Warnings Properly When Designing APIs

When you see warnings at a declaration or call site, do not immediately add suppressions. Decide according to the actual API requirements.

### Option A — Use `List<?>...` If Only Inspecting Lists

```java
static int totalSize(List<?>... lists) {
    int total = 0;
    for (List<?> list : lists) total += list.size();
    return total;
}
```

Clear contract: accepts multiple lists of any type arguments and only computes total size. No `<T>` is needed because there is no shared `T` relationship to preserve.

### Option B — Use an Outer Collection Instead of a Varargs Array

If callers already hold multiple lists of the same type `T`, you can accept `List<? extends List<? extends T>>` or a signature better suited to the domain:

```java
static <T> List<T> flattenGroups(
        List<? extends List<? extends T>> groups) {
    List<T> result = new ArrayList<>();
    for (List<? extends T> group : groups) {
        result.addAll(group);
    }
    return result;
}
```

This illustrative method requires `import java.util.List;` and `import java.util.ArrayList;`. Invocation:

```java
List<String> result = flattenGroups(
        List.of(List.of("a", "b"), List.of("c")));
```

The compiler does not need to synthesize a `List<T>[]` varargs array. This approach often fits best when the groups are already in a collection or when the structure is shared across multiple APIs.

### Option C — Keep Varargs While Proving the Method Safe

If a fluent API needs convenient multi-argument call syntax, keep `List<? extends T>...` while ensuring:

- No mismatched elements are written into the array.
- The array is never returned, stored, or handed to code that could mutate it.
- No raw or unchecked aliases break the contract.
- Read values are used only through compiler-checked generic APIs.
- A new collection or immutable result is returned when the contract permits.
- `@SafeVarargs` is added **only when** the method/constructor is an eligible target and all safety conditions have been proven.

### Option D — Fix Data Sources or Ownership

Even a seemingly read-only method receiving an external array or mutable lists still needs clear ownership. If other code holds an alias and mutates concurrently, the issue extends beyond generic varargs warnings (synchronization, snapshotting, validation). Never assume `@SafeVarargs` makes inputs immutable or thread-safe.

## 13. Reading Warnings by Location and Category

A step-by-step diagnostic workflow:

1. **Enable explicit lint flags**: `javac -Xlint:unchecked -Xlint:varargs`.
2. **Check whether the caret is at the declaration or call site**; do not just count warnings.
3. At the declaration, note the varargs component type: `T`, `List<T>`, `List<String>`, `List<?>`, `String`.
4. At the call site, check whether the compiler must implicitly create a varargs array or the caller is passing an existing array; see what `T` is inferred to be.
5. Inspect the body: is there an `Object[]` alias, array slot assignment, returned varargs array, or pass-through to mutating code?
6. Check for raw types, unchecked casts, inner-list mutations, and external data flows.
7. Choose whether to redesign the API (`List<?>...`, outer collection) or keep generic varargs with `@SafeVarargs` when justified.
8. Recompile with lint enabled and run both valid and failure paths to confirm you fixed the **root cause**, not just the message.

### 13.1. Quick Diagnostic Table

| Message / Symptom | Typical Location | Proper Interpretation |
| --- | --- | --- |
| `Possible heap pollution from parameterized vararg type List<T>` | Method declaration | Varargs parameter has a non-reifiable component. |
| `unchecked generic array creation for varargs parameter ...` | Varargs call site | Compiler creates an implicit array whose type argument is unchecked at runtime. |
| `[varargs] Varargs method could cause heap pollution ...` | Inside an `@SafeVarargs` method with appropriate lint | An operation on the varargs array could compromise type safety. |
| `[rawtypes] found raw type: List` | Declaration using raw `List` | Raw-type issue; distinct from `List<T>` being non-reifiable. |
| `ClassCastException` when receiving a generic result | Runtime, usually at a read/assignment site | Data may have suffered prior heap pollution via alias or cast. |
| `ArrayStoreException` when writing into an array | Runtime at assignment | Object is incompatible with the array's **runtime component class**. |
| Warnings gone after adding `@SafeVarargs` | Declaration/caller | Does not prove the method is safe; still review the body. |

### 13.2. When the Build Only Reports "uses unchecked or unsafe operations"

If `javac` runs without detailed lint flags, it may only emit a note advising recompilation with `-Xlint:unchecked`. Run:

```bash
javac --release 17 -Xlint:unchecked -Xlint:varargs VarargsWarningDemo.java
```

to pinpoint exact locations. Do not try to fix it via `-nowarn`, disabling all compiler warnings, or package-wide suppressions.

## 14. Common Thinking Errors

**Mistake 1 — Declaration warnings prove the method has already written bad data.** Incorrect. The compiler warns about the potential for heap pollution from a non-reifiable component, even when the body only reads.

**Mistake 2 — Call-site warnings are unrelated new bugs separate from the method signature.** Incorrect. They reflect creating an implicit varargs array for a method with a non-reifiable component, directly tied to the signature and type inference.

**Mistake 3 — Generic type arguments are guaranteed to be checked inside a `List<String>[]`.** Incorrect. The runtime array usually checks only the `List` component class, not elements inside each list.

**Mistake 4 — `@SafeVarargs` makes every call safe.** Incorrect. It is the author's promise. A flawed method can still cause heap pollution and `ClassCastException`.

**Mistake 5 — Adding `@SuppressWarnings("unchecked")` solves the problem.** Incorrect. It only hides warnings; it gives the runtime no extra type information or data validation.

**Mistake 6 — `List<?>...` emits the same warnings as `List<T>...`.** With a reifiable `List<?>` component, the non-reifiable varargs component warning does not occur. Other warnings can still appear if code uses unsafe raw types or casts.

**Mistake 7 — Every `List<T>...` should immediately be changed to `List<?>...`.** If the method must link a `T` between input and output, switching to a wildcard can destroy API accuracy. Evaluate the purpose before changing.

**Mistake 8 — Reviewing the body in isolation while forgetting array aliases can escape.** An array passed to another method, returned, or stored for later mutation can still break invariants. Audit the entire data flow.

**Mistake 9 — Disappearing compiler warnings mean data has been validated.** No. An API can compile with zero lint warnings while data from raw/legacy or external sources is still wrong. Generic type checking, runtime validation, and ownership are separate responsibilities.

## 15. Practice Exercises

### Exercise 1 — Identifying Both Warning Sites

Given the method:

```java
static void visit(List<String>... lists) {
    System.out.println(lists.length);
}
```

and the call:

```java
visit(List.of("A"), List.of("B"));
```

If `-Xlint:unchecked` is enabled, which locations can receive warnings?

<details>
<summary>Answer</summary>

At the declaration: `Possible heap pollution from parameterized vararg type List<String>`. At the call site: `unchecked generic array creation for varargs parameter of type List<String>[]`. They describe two sides of the same non-reifiable array mechanism.

</details>

### Exercise 2 — Why Does `List<?>...` Differ from `List<String>...`?

<details>
<summary>Answer</summary>

`List<?>` is reifiable because its argument is an unbounded wildcard; `List<String>` is non-reifiable. The JVM can allocate a `List` component array in certain structures, yet using a generic component `List<String>` in varargs carries unchecked type-argument risk, prompting compiler warnings.

</details>

### Exercise 3 — Should `@SafeVarargs` Be Added?

```java
static <T> T wrong(List<T>... groups) {
    Object[] alias = groups;
    alias[0] = List.of(42);
    return groups[0].get(0);
}
```

<details>
<summary>Answer</summary>

No. The body writes a `List<Integer>` into an array with source component `List<T>`, which can cause heap pollution. Fix the body and design first rather than adding the annotation merely to silence caller warnings.

</details>

### Exercise 4 — When Should an Outer Collection Be Chosen Over Varargs?

<details>
<summary>Answer</summary>

When callers already hold a list of groups, need to pass it across multiple layers, or do not need `...` convenience syntax, accepting `List<? extends List<? extends T>>` or an appropriate domain structure avoids implicit varargs arrays and keeps the generic contract clear.

</details>

### Exercise 5 — A `static` Method with `@SafeVarargs` Compiles Cleanly. Is Its Body Always Safe?

<details>
<summary>Answer</summary>

No. `static` only satisfies annotation placement rules; the author must still ensure no heap pollution occurs. `-Xlint:varargs` can warn about aliasing or exposing a non-reifiable varargs array.

</details>

### Exercise 6 — Can `@SafeVarargs` Be Applied to a Non-`final`, Non-`private` Instance Method on Java 17?

<details>
<summary>Answer</summary>

No. Overridable instance methods are ineligible for `@SafeVarargs`; on Java 17 only `final` or `private` instance varargs methods are valid, alongside `static` methods and varargs constructors.

</details>

## 16. Conclusion

A **declaration warning** on generic varargs indicates that the signature accepts an array with a non-reifiable component, creating heap-pollution potential. A **call-site warning** indicates that the compiler is creating or supplying a generic varargs array whose type arguments cannot be fully verified at runtime. The two messages are related yet live at two different places in a program.

`@SafeVarargs` should only be used when a method is an eligible target **and** you can ensure the varargs array is never written with wrong types, never escapes to untrusted code, and never suffers corruption via raw aliases. If linking type `T` is unnecessary, `List<?>...` can be a clean reifiable API. If keeping generic relationships without varargs arrays matters, consider passing an outer collection.

With Java Generics, resolving warnings properly means **preserving type contracts and controlling data flow**, not merely quieting the compiler.
