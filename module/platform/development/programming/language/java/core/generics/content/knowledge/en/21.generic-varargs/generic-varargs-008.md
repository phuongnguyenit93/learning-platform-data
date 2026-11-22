# Distinguishing `unchecked`, `rawtypes`, and `varargs` Warnings in Java Generics

## 1. Three Warning Categories: Related but Not Synonymous

When compiling Java Generics, three `javac` warning categories frequently appear together:

- **`[rawtypes]`**: a generic class or interface name is used as a **raw type**, such as `List` instead of `List<String>` or `List<?>`.
- **`[unchecked]`**: the compiler cannot fully prove the type safety of a **conversion or invocation**, such as calling `add` on a raw `List`, casting to `List<String>`, or preparing an array for `List<String>...`.
- **`[varargs]`**: warnings concerning **how a non-reifiable varargs parameter is used inside the method body**, especially when a method annotated with `@SafeVarargs` exposes or forwards the varargs array in a way the compiler considers capable of causing heap pollution.

A single piece of code can trigger **all three** categories. However:
- A raw type **does not necessarily** produce an unchecked warning if you only declare a variable without performing an unsafe operation; use `-Xlint:rawtypes` to detect such declarations.
- An unchecked warning **does not require** an explicit raw type: casting `Object` to `List<String>` can also be unchecked.
- Warnings on a generic varargs declaration like `List<String>...` and on caller array creation normally carry the label **`[unchecked]`**, not necessarily `[varargs]`.
- `[varargs]` does not mean "any method with `...`", rather a specific category of varargs operations recognized by `javac`'s analyzer under concrete rules.

The goal is not "making every warning disappear with annotations," but understanding **what evidence the compiler lacks** and fixing it at the right design layer.

## 2. How to Enable Each Warning Category Accurately

On JDK 17 or later, compile a file with:

~~~bash
javac --release 17 -Xlint:rawtypes -Xlint:unchecked -Xlint:varargs LintCategoriesDemo.java
~~~

Or in shorthand:

~~~bash
javac --release 17 -Xlint:rawtypes,unchecked,varargs LintCategoriesDemo.java
~~~

Meaning of the flags:

| `javac` Option | Warnings Observed |
| --- | --- |
| `-Xlint:rawtypes` | Places where a generic type is used without type arguments. |
| `-Xlint:unchecked` | Unchecked method invocations, conversions, casts, generic array creation for varargs, and operations that cannot be fully verified. |
| `-Xlint:varargs` | Uses of a varargs parameter that risk heap pollution, especially inside `@SafeVarargs` methods. |
| `-Xlint:all` | Enables all lint categories supported by `javac`, which may include unrelated categories. |
| `-Werror` | Treats compilation warnings as build errors; **does not** make conversions any safer. |

Exact wording, line numbers, and counts can vary across JDK versions and source contexts. Read the **bracketed category**, the highlighted caret position, and `required/found` lines to identify the root cause.

`javac` sometimes prints only a note:

~~~text
Note: ... uses unchecked or unsafe operations.
Note: Recompile with -Xlint:unchecked for details.
~~~

A note does not mean warnings were resolved. Enable `-Xlint:unchecked` to see the exact operations. If your project uses Gradle or Maven, configure the compiler arguments accordingly or run a `javac` command reproducing the exact classpath and source release.

## 3. `rawtypes` — A Mistake in How the Type Name Is Written

Java defines:

~~~java
interface List<E> { /* generic members */ }
~~~

In the standard library, `java.util.List<E>` is a generic interface. If you write:

~~~java
List raw = new ArrayList();
~~~

two sites stand out:

1. `List` omits type argument `E`.
2. `new ArrayList()` also uses the generic name `ArrayList<E>` in raw form.

With `-Xlint:rawtypes`, `javac` warns:

~~~text
[rawtypes] found raw type: List
[rawtypes] found raw type: ArrayList
~~~

By contrast:

~~~java
List<String> names = new ArrayList<>();
List<?> unknown = names;
List<Object> anyObjects = new ArrayList<>();
~~~

are all **parameterized types**, not raw. `List<?>` has a wildcard; `List<Object>` has a concrete `Object` type argument. The diamond `<>` in `new ArrayList<>()` requests type-argument inference; it is **not** raw `new ArrayList()`.

### Not Every Type Without `<>` Is Raw

~~~java
String name = "Java";
Integer count = 7;
Object value = name;
Runnable job = () -> System.out.println("run");
~~~

`String`, `Integer`, `Object`, and `Runnable` declare no type parameters; they are **non-generic types**. `-Xlint:rawtypes` does not warn about every class name written without `<...>`, only generic types used raw.

A non-generic class can still contain generic methods:

~~~java
final class Helpers {
    static <T> T same(T value) {
        return value;
    }
}
~~~

`Helpers` is not generic, so writing `Helpers.same("A")` is not raw. Type parameter `T` belongs to the method, not the class.

### Seeing Only `rawtypes` Does Not Prove a `ClassCastException` Exists

~~~java
List legacy;
~~~

This raw declaration can emit `[rawtypes]`, yet no mismatched element addition, cast, or runtime operation has happened yet. The warning points to a **site where type arguments were dropped**, not proof that a runtime failure has already occurred.

When fixing it, choose the right type argument: `List<String>` if element types are known, `List<?>` if reading elements of unknown type, or `List<Object>` if the contract genuinely accepts any `Object`.

## 4. `unchecked` — The Compiler Cannot Fully Prove Type Safety

`[unchecked]` typically accompanies operations that are syntactically valid in Java yet **not comprehensively verified by runtime generic information**.

### 4.1. Unchecked Call via a Raw Collection

~~~java
List raw = new ArrayList();
raw.add("Java");
~~~

Because `raw` carries no type argument `E`, calling `add(E)` is not checked against a concrete `E`. With `-Xlint:unchecked`, `javac` warns:

~~~text
[unchecked] unchecked call to add(E) as a member of the raw type List
~~~

The issue is not that `String` is invalid for all lists; the issue is that **calling through a raw type loses element-type constraints**. That same raw reference could be used to add an `Integer` to a list another alias declares as `List<String>`.

### 4.2. Unchecked Conversion from Raw to Parameterized

~~~java
List raw = new ArrayList();
List<String> strings = raw;
~~~

`javac` allows the assignment for legacy compatibility, along with:

~~~text
[unchecked] unchecked conversion
required: List<String>
found:    List
~~~

The compiler does not inspect every element inside the raw `List`. A bad value might only trigger `ClassCastException` when read later as `String`.

### 4.3. Unchecked Cast Without Explicit Raw Syntax

~~~java
Object unknown = List.of("A");

@SuppressWarnings("unchecked")
List<String> assumed = (List<String>) unknown;
~~~

Even without declaring a raw variable on this line, casting `(List<String>)` still cannot verify that every element is a `String`. Without the annotation, `-Xlint:unchecked` reports:

~~~text
[unchecked] unchecked cast
~~~

At runtime, the cast checks the **`List` class/interface**, yet cannot verify the `String` generic argument. The fact that the example list happens to contain `"A"` does not turn the cast into a checked cast in the compiler's eyes.

### 4.4. A Checked Cast Is a Different Case

~~~java
Object input = "Java";
String string = (String) input;
~~~

This cast targets the reifiable runtime class `String`, so the JVM checks it directly. It can throw `ClassCastException` if the object is the wrong class, yet **that does not make it an unchecked generic cast**.

Distinguish clearly: "a cast can fail at runtime" is not equivalent to "an unchecked warning." Unchecked describes **what the compiler and runtime lack enough generic information to verify completely**.

## 5. Why Do `unchecked` and `rawtypes` Warnings Often Appear Together?

Consider this example:

~~~java
List raw = new ArrayList();
raw.add("Java");
List<String> typed = raw;
~~~

Read in order:

| Location | Warning Category | Issue |
| --- | --- | --- |
| `List raw` | `[rawtypes]` | Uses raw `List`. |
| `new ArrayList()` | `[rawtypes]` | Instantiates raw `ArrayList`. |
| `raw.add("Java")` | `[unchecked]` | Invokes `add` on a raw generic receiver. |
| `List<String> typed = raw` | `[unchecked]` | Assigns a raw collection to a parameterized variable. |

A very short snippet can generate multiple warnings because they refer to **different operations**. Fixing a raw declaration while forgetting an unchecked cast does not remove all risk. Conversely, suppressing only `[unchecked]` **does not fix** the fact that raw types remain in the code.

In legacy code, fix types at the data creation/hand-off boundary and avoid passing raw references through multiple application layers. If `E` is genuinely unknown, choose a wildcard and validate elements before asserting a concrete `E`.

## 6. Why Does a Warning Mentioning Varargs Belong to `unchecked`?

`T...` and `List<String>...` are **array parameters** in source code. When the compiler must create an array for a variable-arity invocation with a non-reifiable component like `List<String>`, the runtime array only checks the `List` component without checking `String`; thus, it emits **`[unchecked]` generic array creation** at the caller, alongside a possible heap pollution warning at the method declaration.

```java
static void groups(List<String>... values) {
    System.out.println(values.length);
}
// groups(List.of("A"), List.of("B"));
// Two [unchecked] warnings may appear at the declaration and call site.
```

The illustrative snippet requires `import java.util.List;` and placing the call inside an appropriate method. Note the distinction: `new List<String>[2]` is a **compile error** due to a non-reifiable component type; calling generic varargs compiles with warnings. Meanwhile, `[varargs]` typically targets **how the array is used, forwarded, or escaped inside a method body marked `@SafeVarargs`**, and does not automatically appear merely because `...` is in the signature.

That is the core difference between **diagnostic classification** and **runtime root cause**. To see all three categories, use `-Xlint:rawtypes,unchecked,varargs` instead of `-Xlint:varargs` alone.

## 7. Varargs Warnings at Declarations and Call Sites Are Usually `[unchecked]`

A program containing:

~~~java
static void groups(List<String>... values) {
    System.out.println(values.length);
}

static void call() {
    groups(List.of("A"), List.of("B"));
}
~~~

when compiled with `-Xlint:unchecked`, typically yields **two warning locations**:

~~~text
[unchecked] Possible heap pollution from parameterized vararg type List<String>
[unchecked] unchecked generic array creation for varargs parameter of type List<String>[]
~~~

The first warning attaches to the **declaration** using `List<String>...`; the second warning attaches to the **call site** that must allocate a backing generic array for the call.

A common point of confusion: even though the message contains the word `vararg`, the actual lint category label is normally **`[unchecked]`**, because the compiler is reporting creation and use of a generic array with a non-reifiable component lacking full type checks.

Enabling only:

~~~bash
javac --release 17 -Xlint:varargs Example.java
~~~

does not necessarily display **those two warnings in detail**. When debugging generic varargs, always include `unchecked` to observe declaration and call-site warnings.

## 8. What Does `[varargs]` Check Inside the Method Body?

Consider an annotated method:

~~~java
@SafeVarargs
static <T> T[] expose(T... values) {
    return values;
}
~~~

`@SafeVarargs` is a pledge that the author **performs no operations that compromise type safety involving the varargs array**. Yet the body above returns the backing array directly to callers, which can expose aliases and lead to heap pollution or runtime failures.

With `-Xlint:varargs`, `javac` 17 emits a warning on `return values`:

~~~text
[varargs] Varargs method could cause heap pollution from non-reifiable varargs parameter values
~~~

`[varargs]` warnings generally target **array usage inside the body**, such as:
- Directly returning the varargs array.
- Passing the array into another API that the compiler cannot prove avoids mutating or leaking aliases.
- Operations that could expose or unsafely manipulate the varargs array.

Reading `values.length`, iterating over elements, or simply using a varargs method does not automatically trigger `[varargs]`.

### Why Doesn't the Compiler Treat `@SafeVarargs` as "Proven Safe"?

The annotation is an **API author's pledge**, not a formal proof that every execution path is safe. The compiler can warn on suspicious patterns yet cannot detect every unsafe behavior across external helper calls.

If you remove the annotation and see `[unchecked]`, then add `@SafeVarargs` just to silence warnings while the method still returns the array, you are **hiding risk signals rather than preserving invariants**.

In Java 17, `@SafeVarargs` can only be placed on constructors or eligible varargs methods such as `static`, `final`, or `private` (not an arbitrary overridable instance method). It does not make type arguments reifiable.

## 9. Complete Java 17+ Program Demonstrating All Three Categories

Save all of the following as **LintCategoriesDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class LintCategoriesDemo {
    static void rawExample() {
        // [rawtypes] at two places using a raw generic class.
        List raw = new ArrayList();

        // [unchecked] because add is called on a raw List.
        raw.add("Java");

        // [unchecked] because raw List is converted to List<String>.
        List<String> strings = raw;

        System.out.println("raw=" + strings.get(0));
    }

    static void uncheckedCast() {
        Object unknown = List.of("A");

        // [unchecked] even though no raw variable is used here.
        List<String> assumed = (List<String>) unknown;

        System.out.println("cast=" + assumed.get(0));
    }

    // [unchecked] declaration/call-site with non-reifiable List<String>.
    static void groups(List<String>... values) {
        System.out.println("groups=" + values.length);
    }

    // Read and copy into a new collection; do not return or expose the array.
    @SafeVarargs
    static <T> List<T> safeCopy(T... values) {
        List<T> result = new ArrayList<>();

        for (T value : values) {
            result.add(value);
        }

        return List.copyOf(result);
    }

    // Intentionally violates safety intent: exposes the backing array to callers.
    // When -Xlint:varargs is enabled, javac warns right at the return.
    @SafeVarargs
    static <T> T[] unsafeExpose(T... values) {
        return values;
    }

    public static void main(String[] args) {
        rawExample();
        uncheckedCast();

        groups(List.of("x"), List.of("y"));

        System.out.println(
                "copy=" + safeCopy("A", "B")
        );

        System.out.println(
                "exposed=" + unsafeExpose("a", "b").length
        );
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 -Xlint:rawtypes,unchecked,varargs LintCategoriesDemo.java
java LintCategoriesDemo
~~~

When compiled with a Java 17-compatible `javac`, the demo emits the corresponding warning categories:

~~~text
[rawtypes] found raw type: List
[rawtypes] found raw type: ArrayList
[unchecked] unchecked call to add(E) as a member of the raw type List
[unchecked] unchecked conversion
[unchecked] unchecked cast
[unchecked] Possible heap pollution from parameterized vararg type List<String>
[varargs] Varargs method could cause heap pollution from non-reifiable varargs parameter values
[unchecked] unchecked generic array creation for varargs parameter of type List<String>[]
~~~

The list above **summarizes only the core warning messages**, rather than reproducing verbatim full `javac` output (which includes file paths, line numbers, `required/found` details, and total warning counts). What matters is which lines carry which labels.

**Exact program stdout:**

~~~text
raw=Java
cast=A
groups=2
copy=[A, B]
exposed=2
~~~

This lesson uses `unsafeExpose` as a **flawed-design** example, not a pattern to deploy in production. Because the caller here passes two genuine `String` values, the program still runs and prints `exposed=2`. Running successfully **does not prove** that the method body satisfies `@SafeVarargs` for all calls and aliasing interactions.

### Why Did the Program Have Warnings Yet Throw No Exception?

The compiler points out **potential** unsafety from raw/unchecked/varargs paths; it does not claim every piece of data in this example is already corrupted. A list holding only `String`s and read as `String`s runs fine despite an unchecked conversion. Yet that same kind of warning can mask a path putting an `Integer` into the list and triggering `ClassCastException`.

What needs fixing is the architecture or unchecked conversion path, not merely checking whether this single test throws an exception.

## 10. Enabling Each Category Individually to Isolate Root Causes

Using the same `LintCategoriesDemo.java` above:

~~~bash
javac --release 17 -Xlint:rawtypes LintCategoriesDemo.java
javac --release 17 -Xlint:unchecked LintCategoriesDemo.java
javac --release 17 -Xlint:varargs LintCategoriesDemo.java
javac --release 17 -Xlint:rawtypes,unchecked,varargs LintCategoriesDemo.java
~~~

The first command highlights **where raw types are used**; detailed unchecked warnings that are not enabled may be summarized by a Note.

The second command reveals:
- Calling `raw.add` and converting raw to `List<String>`.
- Casting `(List<String>) unknown`.
- The `List<String>...` declaration and call-site generic array creation.

The third command flags how `unsafeExpose`'s body returns the varargs parameter externally. Other unchecked warnings may not print in detail when only `varargs` is enabled.

The final command places **all locations side by side** to distinguish them: two warnings may share the broad root cause "loss of type checking" while belonging to two different kinds of operations.

Use the same `--release 17` and same source when comparing, avoiding confusion from compiler or source-level differences.

## 11. Distinguishing Unchecked Conversion, Unchecked Cast, and Checked Cast

Three operations look similar yet differ fundamentally.

### Unchecked Conversion

~~~java
List raw = List.of("Java");
List<String> words = raw;
~~~

Assigning raw `List` to `List<String>` is allowed for legacy compatibility, yet the compiler does not validate every element. `[unchecked] unchecked conversion` describes this accurately.

### Unchecked Cast

~~~java
Object input = List.of(10);
List<String> assumed = (List<String>) input;
~~~

Casting to `List<String>` does not check the `Integer` element. Calling `assumed.get(0)` as `String` can throw `ClassCastException`. `[unchecked] unchecked cast` appears because the runtime lacks sufficient generic argument information.

### Checked Cast

~~~java
Object input = "Java";
String text = (String) input;
~~~

The target `String` is a runtime-verifiable class. This is a checked reference cast; if `input` actually holds an `Integer`, it throws `ClassCastException` immediately, yet **is not an unchecked generic warning**.

Never suppress warnings merely because "Java casts at runtime anyway": a runtime cast checks the outer class, not that nested elements match generic type arguments.

## 12. Heap Pollution: When Does a Concern Become a Real Failure?

Consider a flawed varargs method:

~~~java
static void pollute(List<String>... lists) {
    Object[] alias = lists;
    alias[0] = List.of(42);

    String text = lists[0].get(0);
    System.out.println(text);
}
~~~

This is an **illustrative code snippet**, not integrated into a complete program. Calling `pollute(List.of("safe"))` leads to:

1. The compiler allocates an array with runtime component `List` because `List<String>` is non-reifiable.
2. The method receives an array whose static type is `List<String>[]`.
3. An `Object[]` alias points to the same array.
4. Assigning `List<Integer>` into an array slot is accepted by the JVM because the runtime only checks that it is a `List`.
5. Calling `get(0)` and using it as `String` causes the JVM to throw `ClassCastException`.

Step 4 explains why the failure is not `ArrayStoreException` at the assignment: the runtime component is `List`, and the assigned object is indeed a `List`.

The **root cause** is the unsafe operation via an alias/raw reference or exposing the array. The two declaration/call-site warnings flag general risk, though a warning alone does not prove heap pollution has definitely occurred.

### Unsafe Varargs Does Not Mean Every Call Fails

A method that only reads `List<String>` values and never exposes the array can operate safely despite a non-reifiable component type. If the author is eligible and proves safety, `@SafeVarargs` avoids unnecessary warnings.

Conversely, even a method annotated with `@SafeVarargs` can fail if it exposes or mutates the array. The annotation does not change JVM behavior.

## 13. How to Fix `rawtypes`?

Given:

~~~java
List raw = new ArrayList();
~~~

pick a replacement matching the contract:

~~~java
List<String> strings = new ArrayList<>(); // Known that every element is String.
List<?> unknown = strings;                // Unknown element type for reading only.
List<Object> mixed = new ArrayList<>();   // Intentionally allows any Object.
~~~

Do not treat those three types as interchangeable:
- `List<String>` locks element types to `String` across generic API calls.
- `List<?>` acknowledges an unknown element type; the compiler prevents arbitrary additions.
- `List<Object>` accepts any `Object` yet **is not a supertype of `List<String>`** due to generic invariance.

If data genuinely arrives from a legacy raw API, you can temporarily accept it as `List<?>` and validate elements:

~~~java
static List<String> validatedStrings(List<?> input) {
    List<String> result = new ArrayList<>();

    for (Object value : input) {
        if (!(value instanceof String text)) {
            throw new IllegalArgumentException("String required");
        }
        result.add(text);
    }

    return List.copyOf(result);
}
~~~

This snippet requires `import java.util.List;` and `import java.util.ArrayList;`, and uses Java 17 pattern matching. It rejects `null` and produces a list that cannot be modified via standard APIs. The goal is **re-establishing a data-verified invariant**, rather than attaching `<String>` via an unchecked cast.

## 14. Fixing `unchecked` Without Hiding Warnings

When you see:

~~~java
@SuppressWarnings("unchecked")
List<String> strings = (List<String>) unknown;
~~~

ask:
1. Who created `unknown` and what contract do they guarantee?
2. Can the runtime verify that the top-level object is a `List`?
3. Can we iterate over elements as `Object` and confirm each is a `String`?
4. Can the source API be updated to return `List<String>` directly?
5. Is a defensive copy needed to prevent a raw alias from mutating data later?

A safe approach at any `Object` boundary:

~~~java
static List<String> checkedCopy(Object source) {
    if (!(source instanceof List<?> unknown)) {
        throw new IllegalArgumentException("List required");
    }

    List<String> result = new ArrayList<>();
    for (Object value : unknown) {
        if (!(value instanceof String s)) {
            throw new IllegalArgumentException("String required");
        }
        result.add(s);
    }

    return List.copyOf(result);
}
~~~

No warning suppression is needed. `instanceof List<?>` only confirms the object is a `List`; the `instanceof String` loop validates the elements.

For unchecked casts that **cannot be eliminated** inside a low-level generic library, keep the annotation narrowly scoped, document the **invariant justifying the cast**, restrict write paths, and test wrong-type scenarios. Never silence warnings project-wide just to get a clean compile output.

## 15. How to Fix `varargs` Warnings?

### 15.1. If the API Does Not Need Variable Arity, Drop Varargs

Replace:

~~~java
static void process(List<String>... groups) {
    // ...
}
~~~

with:

~~~java
static void process(List<List<String>> groups) {
    // ...
}
~~~

This is sensible whenever callers already hold a collection. It removes the need to synthesize a `List<String>[]` backing array at the call site.

### 15.2. If Varargs Is Needed, Neither Mutate Nor Expose the Array

Potentially safe pattern:

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

The body only reads elements, never returns `values`, never writes mismatched types into the array, and never passes the array to APIs that might retain an alias. `List.copyOf` rejects `null` and performs a shallow copy; those are specific constraints of this example.

### 15.3. If the Compiler Emits `[varargs]` on `return` or Forwarding, Revisit Ownership

~~~java
@SafeVarargs
static <T> T[] returnBackingArray(T... values) {
    return values; // [varargs] may warn.
}
~~~

Do not simply add `@SuppressWarnings("varargs")` and treat it as fixed. Redesign the API to avoid exposing the array, or prove the special conditions preventing alias misuse. If a library truly must return an array, handle the runtime component type and caller contract properly.

### 15.4. Never Copy Annotations Mechanically

`@SafeVarargs` cannot be placed arbitrarily on an overridable instance method, and should not be used on non-varargs methods. It is an author's contract, not a "trick" to silence lint.

Even suppressed warnings can reflect a real runtime bug. Safety tests must cover mismatched data, not just happy paths.

## 16. Why Does `Arrays.asList(values)` Require Extra Care?

`Arrays.asList(values)` produces a **fixed-size `List` backed by the array**. It does not copy the backing array:

~~~java
String[] source = {"A", "B"};
List<String> view = java.util.Arrays.asList(source);

view.set(0, "changed");
System.out.println(source[0]); // changed
~~~

If an `@SafeVarargs` method passes its varargs array directly to `Arrays.asList` or another method, `javac -Xlint:varargs` **may warn** at that forwarding site. An external call could retain or create a view over the array itself, so forwarding must be proven safe end-to-end.

A clearer pattern for avoiding array exposure inside `@SafeVarargs` is **looping over `T` into a new collection**, then calling `List.copyOf` if an unmodifiable result is desired. That way the compiler does not have to guess whether an external call retains or mutates an alias to `values`.

**Important:** copying the collection is only a **shallow copy**; if element `T` itself is mutable or is a raw/unchecked `List` with wrong generic types, copying only the outer list does not validate nested elements.

## 17. When Should `@SuppressWarnings` Be Used?

`@SuppressWarnings` specifies a category for a targeted code region, for example:

~~~java
@SuppressWarnings("unchecked")
static <T> T controlledCast(Object value) {
    return (T) value;
}
~~~

The snippet above only illustrates syntax and is **not automatically safe**: a caller can request an incompatible `T` and hit `ClassCastException` when consuming the result. Never use it as-is in an application without runtime type evidence.

Categories are usually passed as strings:
- `"rawtypes"` for raw-type diagnostics.
- `"unchecked"` for unchecked operations.
- `"varargs"` for corresponding varargs warnings when supported by the compiler.

Suppression should be a **last resort on a small piece of code proven safe**. Always add a comment explaining the invariant:
- Where is type information validated?
- Who has write access to the data?
- Why can this cast never receive a wrong-type object?
- Why is the varargs array never mutated or exposed?
- Does the invariant still hold if the API is subclassed or called through a raw type?

Suppressing across an entire class or build hides new warnings added later; good practice narrows the scope to the single method, line, or variable needed.

## 18. Quick Decision Table by Warning

| Common Message | Category | Immediate Cause | Preferred Resolution |
| --- | --- | --- | --- |
| `found raw type: List` | `rawtypes` | Using a generic name without type arguments. | Choose the right `List<T>` or `List<?>`. |
| `unchecked call to add(E)` | `unchecked` | Calling an `E`-dependent method on a raw receiver. | Remove the raw alias and use a typed generic reference. |
| `unchecked conversion` | `unchecked` | Raw `List` → `List<String>` without checking elements. | Fix the source API or validate/copy the data. |
| `unchecked cast` | `unchecked` | Casting to a non-reifiable generic type. | Use a validator or an explicit invariant. |
| `Possible heap pollution from parameterized vararg type` | `unchecked` | Varargs declared with a non-reifiable component. | Audit the API; use `@SafeVarargs` when genuinely safe. |
| `unchecked generic array creation for varargs parameter` | `unchecked` | Caller packs arguments into a non-reifiable generic array. | Use a safe `@SafeVarargs` API or a collection alternative. |
| `Varargs method could cause heap pollution ...` | `varargs` | Inside the body, the varargs array may be exposed/forwarded unsafely. | Fix the body to avoid unsafe exposure or verify the contract. |

Exact messages can differ across `javac` builds. Do not merely search for the word "varargs" in the text and assume the category is `[varargs]`; read the bracketed label and the marker location.

## 19. Generic Code Review Checklist

1. **Enable all relevant lint categories:** `-Xlint:rawtypes,unchecked,varargs` at your project's source release level.
2. **Read the warning label**, not just the prose text.
3. **Locate the generic root type:** `List<E>`, `Map<K,V>`, `Optional<T>`, or a project-defined generic class.
4. **Check whether raw types are intentional:** prefer wildcards when the type argument is unknown.
5. **Check where unchecked operations occur:** declaration, method call, cast, or varargs call site.
6. **Verify runtime invariants:** where data originates, whether raw aliases exist, and whether elements are validated.
7. **For varargs:** trace the caller's backing array, fixed vs. variable arity, and the erased runtime component.
8. **Inspect bodies of `@SafeVarargs` methods:** check for returned arrays, field storage, forwarding to other APIs, `Object[]` aliases, or array writes.
9. **Prefer fixing the API:** parameterized collections, validators, defensive copies; suppress annotations only with concrete proof.
10. **Test negative cases:** `Integer` inside `List<String>` via raw alias, exposed generic varargs, mismatched types on read.
11. **Separate compiler diagnostics from stdout:** warnings belong to build output, not program output.
12. **Do not treat `-Werror` as a substitute for fixing bugs:** it fails the build on warnings to enforce hygiene, yet does not make code safe by itself.

These steps apply when migrating legacy Java code to generics, designing public library APIs, or auditing `@SafeVarargs` usage across a codebase.

## 20. Self-Check Questions

**Question 1.** What warning does `List raw;` produce with `-Xlint:rawtypes` when no elements are added?

**Answer:** `[rawtypes]` because `List<E>` is used raw. `[unchecked]` is not required until an operation needing generic type checking occurs.

**Question 2.** What does `List<String> values = raw;` warn about?

**Answer:** `[unchecked] unchecked conversion` because the compiler cannot prove the raw collection actually contains only `String`s.

**Question 3.** Does casting `(List<String>) unknown` from `Object` require a raw `List` variable to trigger a warning?

**Answer:** No. `[unchecked] unchecked cast` appears because the cast targets a non-reifiable parameterized type, even when the source is `Object`.

**Question 4.** Which category do `static void f(List<String>... xs)` and `f(List.of("A"))` usually emit?

**Answer:** With `-Xlint:unchecked`, `javac` reports `[unchecked]` at both the declaration ("Possible heap pollution...") and the call site ("unchecked generic array creation..."); the word `vararg` in the message does not change the category to `[varargs]`.

**Question 5.** Is `@SafeVarargs static <T> T[] f(T... xs) { return xs; }` guaranteed to be warning-free?

**Answer:** No. `-Xlint:varargs` can warn at `return xs` because the method exposes the varargs array despite the annotation. The annotation does not prove code safe.

**Question 6.** If code has both `rawtypes` and `unchecked` warnings, does suppressing `"rawtypes"` make it safe?

**Answer:** No. Raw declarations and unchecked operations represent distinct issues. Suppression only hides diagnostics without fixing data or invariants.

**Question 7.** Why does `List<String>...` carry heap pollution risk?

**Answer:** The parameter is a `List<String>[]` array in source code, yet its erased runtime component is typically `List`. Through an `Object[]` alias, a `List<Integer>` can be stored in the array; reading that element as `String` can throw `ClassCastException`.

**Question 8.** Does `@SafeVarargs` automatically check every element of `List<String>`?

**Answer:** No. It creates no runtime validation and does not change type erasure. The designer must still ensure the body performs no unsafe array operations.

**Question 9.** Why can `List.copyOf(Arrays.asList(values))` inside an `@SafeVarargs` method still trigger `-Xlint:varargs`?

**Answer:** Because the method passes the backing array `values` directly to another API. Even if the final result is a copy, the compiler warns at forwarding paths that could expose or use the array. Iterating over elements directly into a new collection makes it clearer that the array reference never escapes.

**Question 10.** If warnings appear yet the program still prints the expected output, are the warnings wrong?

**Answer:** No. Warnings indicate the compiler cannot prove safety in all cases. Current well-typed inputs may run cleanly, while other code using raw aliases or unchecked casts can break the invariant.

## 21. Conclusion

**`rawtypes` is about using a generic type name without type arguments. `unchecked` is about operations whose generic safety cannot be fully proven. `varargs` is about potentially unsafe uses of a varargs array, particularly when a method advertised with `@SafeVarargs` exposes or forwards the array.**

The most important practical distinction: **warnings for `List<String>...` at declarations and varargs call sites are usually labeled `[unchecked]`, whereas `[varargs]` attaches to unsafe array usage inside the body**. A single method can trigger both categories.

Use compiler warnings as **leads for auditing type contracts**, fix root causes where data or APIs originate, keep `@SafeVarargs` and `@SuppressWarnings` strictly scoped to proven-safe code, and remember that running cleanly on current data does not make unchecked operations safe for all inputs.
