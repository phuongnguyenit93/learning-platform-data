# Enabling `javac -Xlint:unchecked`, `-Xlint:rawtypes`, and `-Xlint:varargs` to Inspect Java Generics

## 1. Learning Objectives

Java Generics help the compiler catch many type mismatches early. However, when code uses **raw types**, performs **unchecked casts/conversions**, or declares **varargs with a non-reifiable element type**, the compiler cannot fully prove the type safety of every operation. Some code snippets still compile, but emit warnings instead of errors.

To see these risks clearly, proactively enable the warning categories when compiling:

```bash
javac -Xlint:unchecked -Xlint:rawtypes -Xlint:varargs Example.java
```

Or write the three keys compactly in one option:

```bash
javac -Xlint:unchecked,rawtypes,varargs Example.java
```

These commands are for the JDK Java compiler `javac`, not the `java` runtime launcher. The three lint categories have distinct meanings:

| Option | Primary Observation Scope | Example Risk |
|---|---|---|
| `-Xlint:rawtypes` | Using a generic type name **without type arguments** | `List raw = new ArrayList();` |
| `-Xlint:unchecked` | Generic-related operations that the compiler **cannot fully verify** | `raw.add(123)`, assigning raw `List` to `List<String>` |
| `-Xlint:varargs` | Potentially unsafe operations on a **varargs parameter** with a non-reifiable element type, especially inside a method annotated with `@SafeVarargs` | Exposing an alias or writing into a generic varargs array |

**Do not think of these three warnings as three completely independent error categories.** One piece of code can emit multiple warnings simultaneously, and generic varargs can also emit warnings belonging to the `unchecked` category. Exact locations and diagnostic phrasing depend on the source code and `javac` version.

This lesson covers command syntax, underlying mechanisms, runnable Java 17 examples with exact stdout, ways to fix code, how to review valid exceptions, and workflows for controlling warnings in builds/CI.

## 2. Starting with `javac` and Distinguishing Compile Time from Run Time

Suppose we have a file `Hello.java`:

```java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello");
    }
}
```

Commands:

```bash
javac Hello.java
java Hello
```

Stdout of the **running program**:

```text
Hello
```

Any **compiler** messages are produced during the `javac` step; they are not lines printed by the program's `System.out.println`.

When adding the lint flags:

```bash
javac -Xlint:unchecked,rawtypes,varargs Hello.java
java Hello
```

`Hello.java` has no raw types, unchecked operations, or generic varargs, so there is no reason for these lint categories to warn about it.

Notes:

- `javac` analyzes and compiles **source code**.
- `java` runs the generated class.
- A warning does not mean the compilation command failed; by default, many warnings still allow `.class` generation.
- A compilation error (*error*) is different from a warning.
- A warning signals a **potentially risky issue**, which does not mean the program will definitely throw an exception immediately at runtime.

## 3. Exact Syntax of the Options

Separate form:

```bash
javac -Xlint:unchecked -Xlint:rawtypes -Xlint:varargs Main.java
```

Combined form:

```bash
javac -Xlint:unchecked,rawtypes,varargs Main.java
```

Form that enables all lint categories supported by the compiler version:

```bash
javac -Xlint:all Main.java
```

Command to view additional available compiler options:

```bash
javac --help-extra
```

The examples use `javac` from JDK 17. The list of lint keys and diagnostic details can change across JDK versions; when setting up CI, pin the JDK or actively verify output on the target JDK.

`-Xlint:all` is broader than the three categories studied here, so it may also warn about deprecation, serial, cast, fallthrough, or other topics. When first auditing a Generics module, enabling just these three categories helps keep focus.

You can add `-Xdiags:verbose` when detailed diagnostics are needed:

```bash
javac -Xdiags:verbose -Xlint:unchecked,rawtypes,varargs Main.java
```

This option does not fix the program by itself; it helps present error/warning details that can be useful during investigation.

## 4. `rawtypes`: What Is a Raw Type?

A raw type is the use of a generic class/interface **without specifying type arguments**.

Example:

```java
List raw = new ArrayList();
```

Assuming `java.util.List` and `java.util.ArrayList` are imported, the line above is normally valid because Java supports raw types for compatibility with pre-Generics code.

Corresponding typed form:

```java
List<String> typed = new ArrayList<>();
```

Differences:

- `List<String>` informs the compiler that elements must be `String`.
- Raw `List` drops element type information in many checks.
- `new ArrayList()` is a raw class instance creation.
- `new ArrayList<>()` uses **diamond inference**, not a raw constructor.
- Raw `List` is not equivalent to `List<Object>` or `List<?>`.

Enable `-Xlint:rawtypes` so the compiler points out places where a generic type name is used in raw form.

**A `rawtypes` warning does not guarantee a runtime exception.** It reminds you that you have stepped outside an explicit generic contract and can easily lose type checking in subsequent operations.

## 5. Java 17 Example: Raw `List` Causing Heap Pollution

Create the file **`RawTypesWarningDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class RawTypesWarningDemo {
    public static void main(String[] args) {
        List<String> words = new ArrayList<>();
        words.add("safe");

        List raw = words;
        raw.add(100);

        System.out.println(words.size());

        try {
            String second = words.get(1);
            System.out.println(second);
        } catch (ClassCastException ex) {
            System.out.println("ClassCastException");
        }
    }
}
```

Compile with lint enabled:

```bash
javac -Xlint:unchecked,rawtypes,varargs RawTypesWarningDemo.java
java RawTypesWarningDemo
```

Stdout of the **program**:

```text
2
ClassCastException
```

What happens:

1. `words` is declared as `List<String>`.
2. `List raw = words` creates a raw reference to the **same list object**, without creating a copy.
3. `raw.add(100)` calls `add` through a raw type; at runtime the `ArrayList` receives an `Integer`.
4. `words.size()` still returns `2`, because counting elements does not require the second element to be a `String`.
5. `words.get(1)` is used in a `String` position; the actual object is an `Integer`, causing a `ClassCastException`.

Regarding warnings:

- The line `List raw = words` is a raw type usage falling under `rawtypes`.
- The call `raw.add(100)` typically emits an **unchecked call warning** from `unchecked`.
- Both can be observed when those two lint categories are enabled; `varargs` is not involved in this example.

**Heap pollution** is the state where a variable of a parameterized type refers to an object containing data that does not satisfy its generic contract. Raw operations are one of the paths that create this state.

## 6. Fixing a Raw Type According to the API's True Intent

There is no single raw replacement that is right for every program.

If the list is only used to store strings:

```java
List<String> words = new ArrayList<>();
words.add("safe");
// words.add(100); // Intentionally invalid: rejected by the compiler.
```

If you genuinely want to hold multiple object types:

```java
List<Object> mixed = new ArrayList<>();
mixed.add("safe");
mixed.add(100);
```

If the code only needs to **read from a list with an unknown element type**:

```java
static void showAll(List<?> values) {
    for (Object value : values) {
        System.out.println(value);
    }
}
```

The illustrative method needs to be placed inside a class with `List` imported.

Important distinction:

| Intent | Recommended Form | Characteristics |
|---|---|---|
| Store strings only | `List<String>` | Compiler rejects adding numbers |
| Store multiple object types | `List<Object>` | Element type is truly `Object` |
| Accept any list, mainly reading | `List<?>` | Element type unknown; restricts arbitrary writes |
| Interoperate with a raw API that cannot be changed immediately | Isolate the raw/unchecked boundary | Validate data and gradually replace |

Changing raw `List` to `List<Object>` is not always valid: `List<String>` is **not** a subtype of `List<Object>` because Java generics are invariant. `List<?>` is often the better choice when the API only needs to read.

## 7. `unchecked`: The Compiler Cannot Prove Type Safety

Warnings in the `unchecked` category appear when an operation is allowed for backward compatibility, yet **generic safety cannot be fully verified at compile time**.

Common examples:

```java
List raw = new ArrayList();
List<String> typed = raw;
raw.add("A");
```

This is an illustrative snippet; `List` and `ArrayList` must be imported.

Notable cases:

- **Unchecked conversion:** converting from raw `List` to `List<String>`.
- **Unchecked method invocation:** calling a generic method through a raw receiver.
- **Unchecked cast:** casting an object/raw container to a parameterized type where runtime lacks sufficient generic information.
- **Generic varargs:** in certain declarations/calls with a non-reifiable varargs component, the compiler may emit a warning under `unchecked`.

`-Xlint:unchecked` highlights places where type erasure or raw APIs cause type evidence to be lost.

Do not assume every `unchecked` warning is an active bug. Some boundaries interoperating with legacy APIs are necessary; the author's responsibility is to **prove and isolate** them rather than hide them.

## 8. Example: Unchecked Conversion from a Legacy API

Create the file **`UncheckedConversionDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class UncheckedConversionDemo {

    static List legacy() {
        List result = new ArrayList();
        result.add("hello");
        return result;
    }

    public static void main(String[] args) {
        List<String> names = legacy();

        System.out.println(names.size());
        System.out.println(names.get(0).toUpperCase());
    }
}
```

Compile and run:

```bash
javac -Xlint:unchecked,rawtypes,varargs UncheckedConversionDemo.java
java UncheckedConversionDemo
```

Stdout:

```text
1
HELLO
```

The compiler may warn about:

- Raw return type `List` in the `legacy` signature.
- Raw local `List` and raw `new ArrayList()`.
- Unchecked invocation at `result.add("hello")`.
- Unchecked conversion when assigning the result of `legacy()` to `List<String>`.

The demo data happens to contain only strings so the program runs fine, but the signature of `legacy()` **does not guarantee** that future callers will only receive strings. If `legacy()` is modified to add a number, callers could hit a `ClassCastException` later.

Lesson: **running cleanly on the current dataset does not prove an unchecked conversion is safe.**

## 9. Fixing Unchecked Conversion by Changing the API

When you have permission to modify the legacy API, the best solution is usually to type it at the source:

```java
static List<String> names() {
    List<String> result = new ArrayList<>();
    result.add("hello");
    return result;
}
```

This method must be placed inside a class, importing `List` and `ArrayList`.

The caller:

```java
List<String> values = names();
```

needs no unchecked conversion. The compiler can block adding an `Integer` into `result`.

If you cannot modify the API because it belongs to a legacy library, build an **adapter** that accepts `List<?>`, checks each element, and creates a new typed list:

```java
static <T> List<T> checkedCopy(
        List<?> source,
        Class<T> elementType) {

    List<T> copy = new ArrayList<>();

    for (Object element : source) {
        copy.add(elementType.cast(element));
    }

    return copy;
}
```

This adapter verifies the runtime class of each element. When `elementType = String.class`, an `Integer` is rejected immediately during the copy.

`Class<T>` only checks the **element-level class** passed in; if an element is `List<String>` or a deeper parameterized type, a suitably structured validator is required.

## 10. Complete Example: Adapter Validating Data Instead of an Unchecked Cast

File **`CheckedAdapterDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class CheckedAdapterDemo {

    static <T> List<T> checkedCopy(
            List<?> source, Class<T> elementType) {

        List<T> result = new ArrayList<>();
        for (Object value : source) {
            result.add(elementType.cast(value));
        }
        return List.copyOf(result);
    }

    public static void main(String[] args) {
        List<String> accepted =
                checkedCopy(List.of("A", "B"), String.class);

        System.out.println(accepted);

        try {
            checkedCopy(List.of("A", 7), String.class);
        } catch (ClassCastException ex) {
            System.out.println("ClassCastException");
        }
    }
}
```

Compile/run:

```bash
javac -Xlint:unchecked,rawtypes,varargs CheckedAdapterDemo.java
java CheckedAdapterDemo
```

Stdout:

```text
[A, B]
ClassCastException
```

This technique avoids pretending that a raw list is *already guaranteed* to be `List<String>`. It inspects the data and **copies** across the boundary.

Two limitations:

- `List.copyOf` rejects `null` elements; a different policy is needed if the source allows `null`.
- The copied list is a **shallow copy**: mutable element objects can still be modified through other references.

## 11. Unchecked Cast: A Warning That May Signal a Delayed Failure

Place inside a method with `java.util.List` imported:

```java
Object input = List.of("Java", 42);
List<String> words = (List<String>) input; // unchecked cast
System.out.println(words.size());         // 2
// String second = words.get(1);         // Throws ClassCastException at runtime.
```

With `javac -Xlint:unchecked,rawtypes,varargs`, the cast line may emit an **unchecked warning**; if `-Werror` is not enabled, the program is still allowed to compile. The JVM only checks whether `input` is a `List` at the runtime class level, without validating the `String` type argument. Thus `size()` succeeds, and only when the `Integer` value is used as a `String` does a specific cast fail.

Do not treat a program that has not thrown an error yet as proof that the warning is harmless. If the data is untrusted, accept `List<?>`, validate each element, and create a typed copy. The heap pollution testing lesson analyzes in detail the moments of wrong writes, `Object` reads, typed reads, and `checkcast` points with a standalone test suite; here the focus is that **the `unchecked` warning appears at compile time and is not automatically turned into an immediate failure by the JVM**.

## 12. Why Are Generics and Unchecked Casts Linked to Type Erasure?

Java implements standard Generics via **type erasure**. For instance, `List<String>` and `List<Integer>` do not generate two separate runtime classes of `List`.

Consequences:

- The compiler checks `List<String>` at compile time.
- A runtime list object is not automatically tagged with a dedicated class token for `<String>`.
- The JVM can check `object instanceof List<?>` or cast an object to raw `List`, but cannot verify `<String>` from the runtime class alone.
- If unchecked casts or raw operations occur, a state containing data that violates the contract can still arise.

Warnings are not merely a matter of "code style"; they point to **boundaries where compile-time guarantees weaken**.

When an unchecked warning genuinely has a valid justification, state clearly where the invariant is upheld. If you cannot prove the invariant, replace it with a checked adapter or redesign the API.

## 13. `varargs`: Varargs Are Arrays at the Method Level

Given:

```java
static void print(String... values) {
    for (String value : values) {
        System.out.println(value);
    }
}
```

This is an illustrative method that must be placed inside a class.

`String...` is a **variable arity parameter**, yet inside the method body `values` is a `String[]`.

When the varargs element type is a **non-reifiable** generic type, such as:

```java
static void display(List<String>... groups) {
    // ...
}
```

the runtime has no dedicated `List<String>` array component class. For a variable-arity call, the compiler may create an array whose runtime component is raw `List`; from this arises the risk of *heap pollution* if code exposes or writes to the array unsafely.

Distinguish between:

- `-Xlint:unchecked`: can report generic varargs with a non-reifiable parameterized element type at declarations/calls.
- `-Xlint:varargs`: focuses on **potentially unsafe varargs** operations in contexts recognized by the compiler, especially in the body of a `@SafeVarargs` declaration.
- `@SafeVarargs`: a commitment by the author that the implementation uses varargs safely; it does **not** make the JVM check generic arguments.

Some generic varargs warnings relate to both categories; you should not enable only `varargs` while disabling `unchecked`.

## 14. Java 17 Example: Heap Pollution via an `Object[]` Alias

Create the file **`UnsafeVarargsDemo.java`**:

```java
import java.util.List;

public class UnsafeVarargsDemo {

    static void unsafe(List<String>... groups) {
        Object[] alias = groups;

        alias[0] = List.of(99);

        System.out.println(groups[0].size());

        try {
            String text = groups[0].get(0);
            System.out.println(text);
        } catch (ClassCastException ex) {
            System.out.println("ClassCastException");
        }
    }

    public static void main(String[] args) {
        unsafe(List.of("safe"));
    }
}
```

Compile/run:

```bash
javac -Xlint:unchecked,rawtypes,varargs UnsafeVarargsDemo.java
java UnsafeVarargsDemo
```

Program stdout:

```text
1
ClassCastException
```

Analysis:

1. `groups` is viewed as `List<String>[]`.
2. `Object[] alias = groups` creates a supertype reference to the same array object.
3. `alias[0] = List.of(99)` inserts a `List<Integer>`, but the runtime component type only requires an object belonging to raw `List`, so it does **not** block this write.
4. `groups[0].size()` does not retrieve data as a `String`, so it still runs.
5. When reading the element and assigning it to `String`, the runtime cast encounters an `Integer`, causing `ClassCastException`.

The compiler may warn at both the **method declaration** and the **generic varargs call**. Do not copy compiler diagnostics as "fixed stdout": warning counts, column pointers, and phrasing depend on the JDK version.

This example is intentionally unsafe for learning; do not use it as a production implementation.

## 15. `@SafeVarargs`: When Should It Be Used?

If a generic varargs method only iterates over the input and copies data into a new collection, without overwriting array slots and without letting an array alias escape to where it could be modified, `@SafeVarargs` can be considered.

Example:

```java
@SafeVarargs
static <T> List<T> merge(List<? extends T>... groups) {
    List<T> result = new ArrayList<>();
    for (List<? extends T> group : groups) {
        result.addAll(group);
    }
    return List.copyOf(result);
}
```

This is an illustrative method; it must be placed inside a class with `List` and `ArrayList` imported.

In Java 17, the `@SafeVarargs` annotation is allowed on appropriate varargs declarations such as:

- `static` methods;
- `final` instance methods;
- `private` instance methods;
- constructors.

It cannot be placed arbitrarily on an overridable public instance method.

**Important:** The annotation is the author's declaration of implementation safety; the compiler does not prove every data path is safe merely because it sees the annotation.

Do not place `@SafeVarargs` on a method that intentionally uses an `Object[]` alias to write a list with the wrong generic argument, or passes the array to a helper capable of writing the wrong type.

## 16. A Valid and Easily Reviewable `@SafeVarargs` Program

Create the file **`SafeVarargsMergeDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class SafeVarargsMergeDemo {

    @SafeVarargs
    static <T> List<T> merge(List<? extends T>... groups) {
        List<T> result = new ArrayList<>();

        for (List<? extends T> group : groups) {
            result.addAll(group);
        }

        return List.copyOf(result);
    }

    public static void main(String[] args) {
        List<String> names =
                merge(List.of("An"), List.of("Binh", "Chi"));

        List<Number> numbers =
                merge(List.of(1, 2), List.of(3.5));

        System.out.println(names);
        System.out.println(numbers);
    }
}
```

Commands:

```bash
javac -Xlint:unchecked,rawtypes,varargs SafeVarargsMergeDemo.java
java SafeVarargsMergeDemo
```

Stdout:

```text
[An, Binh, Chi]
[1, 2, 3.5]
```

Here:

- `groups` is only read.
- No array slot is replaced with a `List` having a different generic argument.
- `groups` is neither returned nor exposed outside.
- A new `List<T>` is created, and an unmodifiable list is returned.

`List.copyOf` rejects `null` if the data contains null. In this example, the inputs contain no nulls.

If the method passes the array to a helper, you must also audit the helper before asserting safety. Do not rely solely on "not seeing an `=` operator on the array in this method".

## 17. Why Is `-Xlint:varargs` Still Valuable When Using `@SafeVarargs`?

A common misconception is: **putting `@SafeVarargs` makes all warnings disappear, so no further review is needed**.

In reality:

- The annotation can suppress certain unchecked warnings at the declaration and call sites of generic varargs, because the author commits that the implementation is safe.
- The compiler can still emit **warnings inside the method body** about potentially unsafe operations on the non-reifiable varargs array when `-Xlint:varargs` is enabled.
- Even when no warning is emitted in a particular snippet, the annotation does not make a heap-pollution operation valid in terms of data safety.

Intentionally dangerous example:

```java
// Educational snippet: DO NOT apply @SafeVarargs like this example.
@SafeVarargs
static void unsafeAnnotated(List<String>... groups) {
    Object[] alias = groups;
    alias[0] = List.of(123);
}
```

Because the method is `static`, the annotation is permitted by placement rules, yet **the commitment is false**. Compiling with `-Xlint:varargs` helps expose risky operations that the compiler can recognize; it does not mean the compiler detects every alias path and every helper.

The right fix is to **remove the dangerous operation** or redesign the API, not merely switch to `@SuppressWarnings`.

## 18. Choosing `List<T>`/`Collection<T>` Instead of Generic Varargs When Appropriate

If the goal is to process a group of already-existing lists, an API accepting a collection can be simpler:

```java
static <T> List<T> mergeGroups(
        Collection<? extends List<? extends T>> groups) {

    List<T> result = new ArrayList<>();

    for (List<? extends T> group : groups) {
        result.addAll(group);
    }

    return List.copyOf(result);
}
```

This is an illustrative method; `Collection`, `List`, and `ArrayList` must be imported and placed inside a class.

Caller usage:

```java
List<String> merged =
        mergeGroups(List.of(List.of("A"), List.of("B")));
```

Advantages:

- No varargs array with a non-reifiable component at the API boundary.
- Generic type information is tracked by the compiler through `Collection`/`List` in source code.
- The method can read/copy data without holding a varargs array.
- Clear API when the caller already has a collection containing the groups.

In trade-off, the call syntax may be longer than `merge(group1, group2)`. If varargs genuinely make the API easier to use and the implementation has been proven safe, `@SafeVarargs` is a reasonable choice.

## 19. Comparing the Three Lint Categories with a Combined Example

Create the file **`CombinedWarningsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class CombinedWarningsDemo {

    static void acceptLists(List<String>... groups) {
        for (List<String> group : groups) {
            System.out.println(group.size());
        }
    }

    public static void main(String[] args) {
        List raw = new ArrayList();
        raw.add("A");

        List<String> typed = raw;

        acceptLists(typed);
    }
}
```

Compile/run:

```bash
javac -Xlint:unchecked,rawtypes,varargs CombinedWarningsDemo.java
java CombinedWarningsDemo
```

Stdout:

```text
1
```

Which part belongs to which category?

| Line/Operation | Commonly Involved Category | Reason |
|---|---|---|
| `List raw` | `rawtypes` | Generic type name without arguments |
| `new ArrayList()` | `rawtypes` | Using a raw generic class in an instance creation expression |
| `raw.add("A")` | `unchecked` | Invocation through a raw receiver |
| `List<String> typed = raw` | `unchecked` | Unchecked conversion |
| `List<String>... groups` | Usually `unchecked` | Non-reifiable varargs element type |
| `acceptLists(typed)` | Possibly `unchecked` | Variable-arity invocation with a generic array component |
| Read-only body of `acceptLists` | Does not necessarily warn under `varargs` | No unsafe alias/write indicated |

Do not claim `-Xlint:varargs` **must definitely** emit a warning in every method with `...`. It depends on the operations, annotations, type reifiability, and compiler rules.

## 20. Reading and Classifying a Compiler Warning

`javac` diagnostics usually indicate:

- The relevant file and line/column location.
- The key or message describing the warning type.
- The operation considered raw/unchecked/unsafe.
- Sometimes additional **required/found** details or a compiler note.

An example message format might look like:

```text
Example.java:12: warning: [unchecked] unchecked call to ...
```

This is an **illustrative pattern**, not required output from a specific program.

Reading workflow:

1. Look at the **source line** first: is it actually a method call, variable assignment, cast, or varargs declaration?
2. Identify the **source of lost generic information**: raw receiver, raw return type, reflection, or varargs array.
3. Identify the **contract to uphold**: must `List<String>` contain only Strings, or is `List<?>` enough?
4. Inspect **where data enters**: who has permission to add wrong-typed elements?
5. Find a way for the compiler to prove safety: typed signature changes, wildcards, adapters, factories, or redesign.
6. Use suppression only when there is a clear invariant and tests.

A warning at the point where a value is read is not necessarily the root of the problem. The bug may have happened earlier where a raw `add` inserted wrong-typed data.

## 21. `-Werror`: Turning Warnings into Build Errors

For codebases that are already warning-free or managing warnings as technical debt, you can use:

```bash
javac -Xlint:unchecked,rawtypes,varargs -Werror Main.java
```

`-Werror` instructs the compiler to treat the presence of warnings as a failed compilation. It does **not** change the meaning of Generics and does not turn raw/unchecked operations into new runtime checks.

A sensible workflow:

1. Enable lint first to inspect existing warnings.
2. Classify and fix genuinely dangerous cases.
3. Document legacy boundaries that cannot yet be fixed.
4. Isolate suppressions with justification.
5. Once warnings are under control, add `-Werror` to prevent new warnings from slipping in.

If a project currently has too many warnings, enabling `-Werror` abruptly can cause massive CI failures without yet helping improve design. Use a baseline/triage phase or apply it to new modules first before tightening system-wide.

## 22. Example of a Compilation Workflow and Not Confusing Stdout

With `RawTypesWarningDemo.java` created earlier:

```bash
javac -Xlint:rawtypes RawTypesWarningDemo.java
```

The compiler focuses on raw usages. With:

```bash
javac -Xlint:unchecked RawTypesWarningDemo.java
```

The compiler focuses on unchecked operations. With:

```bash
javac -Xlint:varargs RawTypesWarningDemo.java
```

There are no generic varargs in the demo file, so the `varargs` category is not triggered there.

With:

```bash
javac -Xlint:unchecked,rawtypes,varargs RawTypesWarningDemo.java
```

we see the broader set of warnings. Combining the lint categories **does not alter program logic**, so if compilation succeeds, the step:

```bash
java RawTypesWarningDemo
```

still prints:

```text
2
ClassCastException
```

If `-Werror` is added, the `javac` step may fail due to warnings, meaning you must not automatically run a stale `.class` file and mistake it for the result of the latest compilation. Distinguish **compiler build result** from **program run result**.

## 23. `@SuppressWarnings("unchecked")`: Use Only with Proof

There are integration points with legacy APIs or generic array reflection that require an unchecked cast the compiler cannot prove. In such cases, `@SuppressWarnings("unchecked")` may be considered at the **smallest possible scope**.

Example of a class-token-based helper:

```java
@SuppressWarnings("unchecked")
static <T> T[] newArray(Class<T> type, int length) {
    return (T[]) java.lang.reflect.Array.newInstance(type, length);
}
```

This is an illustrative method that must be placed inside a class. When the caller passes a **reference class token** corresponding to `T`, the created array has a runtime component type equal to that token, so the invariant supports the cast.

However, consider cases of primitive tokens, `void.class`, null, or APIs using raw/unchecked code to pass an incorrect token. A production library should specify input preconditions rather than treating the annotation as absolute proof.

Conversely, the following snippet has **no proof of safety**:

```java
@SuppressWarnings("unchecked")
List<String> names = (List<String>) someUnknownObject;
```

If `someUnknownObject` holds a `List<Integer>`, suppression only hides the warning; a runtime error can still occur.

Principle: **fix the root cause if possible; if unavoidable, isolate the scope and write comments stating the invariant along with tests.**

## 24. `@SuppressWarnings("rawtypes")` and `@SafeVarargs` Do Not Replace Each Other

The mechanisms have different scopes:

| Tool | Role | What It Cannot Do |
|---|---|---|
| `@SuppressWarnings("rawtypes")` | Suppresses certain warnings from raw type usages | Does not turn raw `List` into `List<String>` |
| `@SuppressWarnings("unchecked")` | Suppresses warnings from unchecked operations | Does not increase runtime type safety |
| `@SafeVarargs` | Commits that a varargs implementation is safe on valid declarations | Does not automatically prove heap pollution is avoided |
| `-Xlint:varargs` | Asks the compiler to report warnings on recognized unsafe varargs operations | Not an omniscient static analyzer |
| `-Werror` | Makes warnings affect the build result | Does not fix underlying code |

A method can both use a raw type and contain an unchecked call. Suppressing `rawtypes` does not necessarily suppress `unchecked`, and vice versa.

**Do not place the annotation on an entire class** just to "keep logs clean", unless there is a very specific rationale. If a new warning arises elsewhere in the class, broad suppression makes it hard to detect.

## 25. Example of Narrow-Scoped Suppression: Legacy Boundary

Suppose a legacy API returns a raw `List` and a contract outside the Java type system guarantees it contains only `String`. If the signature cannot be changed, an adapter should still validate the data:

```java
static List<String> legacyStrings(List<?> input) {
    List<String> copy = new ArrayList<>();
    for (Object item : input) {
        copy.add(String.class.cast(item));
    }
    return List.copyOf(copy);
}
```

No unchecked cast is needed for the design above. The compiler can check the types of objects placed into the copy.

If an API genuinely returns a typed object from an unchecked path where you are forced to cast, place the suppression right on the **single expression requiring the cast**, rather than on the whole file. For example:

```java
@SuppressWarnings("unchecked")
List<String> result = (List<String>) rawValue;
```

However, do not treat this as safe code for unvalidated input; `rawValue` must already have an **independent invariant** ensuring the element type is `String`, and that invariant should be documented in the wrapper's comments/docs.

In all cases, lint warnings are tools to help you decide **how much you can trust the data**, not an exercise in silencing the compiler at any cost.

## 26. Generic Varargs: Reviewing Alias and Escape Paths

A method might not directly write:

```java
values[0] = ...;
```

yet still be dangerous if it passes the varargs array to other code that could write the wrong type or store that reference.

Varargs array review checklist:

- Is there an `Object[] alias = values` assignment?
- Is there `Arrays.fill(values, ...)`, `System.arraycopy`, or a helper that modifies slots?
- Is `values` stored into a field, static state, or callback?
- Is the array itself or a view backed by the array returned?
- Is there a helper taking raw `Object[]`/raw array to modify elements?
- Is the array cast to another array type and then written to?
- Is `@SafeVarargs` present? If so, has the safety contract been proven?

A safe method typically **only reads the varargs parameter** and copies the contents it needs to keep into another structure, without exposing the array alias to uncontrolled places.

Do not equate **modifying an object currently sitting in a slot** with **replacing a slot of the array**. Both may carry risks depending on the object type, but heap pollution via generic array aliasing primarily refers to writing a value with the wrong generic argument into an array slot.

## 27. Runnable Test to Catch the Consequences of an Unchecked Path

Create the file **`LintRegressionDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class LintRegressionDemo {

    static List<String> safeStrings(List<?> source) {
        List<String> copy = new ArrayList<>();

        for (Object value : source) {
            copy.add(String.class.cast(value));
        }

        return List.copyOf(copy);
    }

    public static void main(String[] args) {
        System.out.println(
                safeStrings(List.of("A", "B")));

        try {
            safeStrings(List.of("A", 1));
        } catch (ClassCastException ex) {
            System.out.println("Rejected mixed types");
        }

        System.out.println(
                safeStrings(List.of()).isEmpty());
    }
}
```

Commands:

```bash
javac -Xlint:unchecked,rawtypes,varargs LintRegressionDemo.java
java LintRegressionDemo
```

Stdout:

```text
[A, B]
Rejected mixed types
true
```

Here the adapter checks each element and requires no unchecked cast. The test covers a valid data path, an invalid data path, and an empty list.

Lint helps detect boundaries not proven by the compiler; tests must verify **runtime behavior** with valid data and invariant-breaking data. The two checks complement each other rather than replacing one another.

## 28. Guide to Using Compiler Warnings in Multi-Module Projects

For a large codebase:

1. **Standardize the JDK/compiler version** so diagnostics are consistent between developer machines and CI.
2. **Enable all three categories** when compiling modules that handle Generics.
3. **Record a baseline** of existing warnings if there is substantial technical debt.
4. **Prioritize data bugs**: raw writes causing heap pollution, unchecked conversions from untrusted input, generic varargs exposing the array.
5. **Separate new warnings from old warnings** if a migration roadmap is needed.
6. **Place typed adapters** at legacy boundaries rather than propagating raw types throughout the system.
7. **Allow suppressions only with rationale**; review each suppression as a verified exception.
8. **Consider `-Werror` for clean modules** to prevent regressions.
9. **Keep runtime tests** for mixed data, nulls, boundaries, and exceptions.
10. **Watch dependency changes**: a library updating its signature can change the raw/unchecked warnings in callers.

Which `.java` files `javac` compiles depends on how you invoke the build and the classpath/modulepath. Compiling just one demo file does not automatically scan the entire repository; in a real project, configure the lint flags in the build tool being used.

## 29. Conceptual Maven/Gradle Configuration

In Maven, the plugin responsible for compiling Java is the **Maven Compiler Plugin**. The flags can be passed as compiler arguments or through the lint configuration corresponding to the plugin version in use.

In Gradle, tasks of type `JavaCompile` can accept compiler arguments:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.addAll([
        '-Xlint:unchecked',
        '-Xlint:rawtypes',
        '-Xlint:varargs'
    ])
}
```

This is an **illustrative Gradle Groovy DSL snippet** that must be placed in a build script and applied in a project using the appropriate Java plugin. It is not a standalone Java program.

For Kotlin DSL build scripts, the configuration syntax differs; do not copy the Groovy DSL verbatim and expect it to run in `.gradle.kts`.

If Maven/Gradle already manages a JDK toolchain, align the toolchain with the JDK running lint locally. Before rolling out `-Werror`, ensure warnings are understood and addressed; do not suppress them en masse just to make the build green.

There is no need to guess a specific Maven or Gradle plugin version if the project already has build conventions. The key requirement is simply that the flags actually reach **`javac`** during compilation.

## 30. When Can Warnings Be Missed Even with Flags Enabled?

Enabling `-Xlint` does not guarantee finding every Generic bug.

Examples:

- Bad data can arrive from runtime reflection or deserialization before hitting a cast.
- A call through a typed API whose internal implementation has a bug might not trigger a warning at the caller.
- `@SafeVarargs` wrongly declares safety while the compiler misses an alias path through a helper.
- Generic element types are erased; the JVM does not automatically validate the contents of every `List<String>`.
- `@SuppressWarnings` may hide diagnostics on risky code.
- If a file/module is not compiled in that build command, the compiler cannot report errors from it.
- Warnings from a precompiled library are not reproduced by compiling only the caller without the library's source.

Therefore, a quality process requires:

**Static type checking + lint warnings + code review + runtime tests + clear API contracts.**

Additional analysis tools can find other classes of bugs, but a list of flags should never be treated as a proof of formal correctness.

## 31. Common Misconceptions

**Misconception 1 — `-Xlint:rawtypes` stops raw types from compiling.** No. It emits warnings; to make warnings fail the build, add `-Werror` or an appropriate build policy.

**Misconception 2 — `-Xlint:unchecked` and `-Xlint:rawtypes` are the same.** No. One focuses on raw usages, while the other focuses on operations that cannot be fully type-checked. One piece of code can trigger both.

**Misconception 3 — `-Xlint:varargs` warns on every method with `...`.** No. Varargs with a reifiable element type like `String...` generally do not carry the generic heap pollution risk in question.

**Misconception 4 — Compiler warnings are program stdout.** No. Diagnostics appear at compile time; illustrative stdout comes from `java ClassName`.

**Misconception 5 — Using `@SuppressWarnings("unchecked")` fixes the bug.** No. It only silences the warning and adds no runtime generic validation.

**Misconception 6 — `@SafeVarargs` makes the JVM know `List<String>`.** No. Erasure still applies and the array has a raw `List` runtime component.

**Misconception 7 — `@SafeVarargs` can be placed on any method.** No. Java restricts valid placement sites for the annotation.

**Misconception 8 — `List<Object>` can replace every raw List in every API.** No. Java Generics are invariant; `List<String>` is not `List<Object>`.

**Misconception 9 — `List<?>` is the same as `List<Object>`.** No. The unknown wildcard restricts write operations.

**Misconception 10 — You can get a `Class<List<String>>` token from `List<String>.class`.** No. That parameterized type has no class literal.

**Misconception 11 — An unchecked cast to `List<String>` checks every String.** No. It can only check the raw runtime class `List`.

**Misconception 12 — `javac -Xlint:all` enables only the three Generics categories.** No. It enables many more lint categories.

**Misconception 13 — Having warnings while tests pass means the warnings are harmless.** No. Tests only run on selected datasets; type pollution may lie on an untested path.

**Misconception 14 — Zero warnings means `ClassCastException` is impossible.** No. Warnings do not guarantee detecting every source of bad data.

**Misconception 15 — `-Werror` generates new runtime checks.** No. It only affects the build outcome when compiler warnings are present.

**Misconception 16 — `javac -Xlint` scans the entire project even if only one file is passed.** No. Only sources processed by the compiler produce diagnostics in that compilation.

**Misconception 17 — Any `varargs` warning can be safely cleared by adding `@SafeVarargs`.** No. You must prove the body and helpers do not cause heap pollution.

**Misconception 18 — Use raw types to save keystrokes.** Using diamond or wildcards usually keeps code concise while providing much better type checks.

## 32. Exercises with Answers

### Question 1 — Identifying a Raw Type

```java
List list = new ArrayList();
```

Which lint key should be enabled to detect the raw usage?

**Answer:** `-Xlint:rawtypes`.

### Question 2 — Identifying an Unchecked Call

```java
List raw = new ArrayList();
raw.add(123);
```

Which warning category does the `add` call typically belong to?

**Answer:** `-Xlint:unchecked`, because a method invocation through a raw receiver cannot be fully checked.

### Question 3 — Unchecked Conversion

```java
List<String> strings = raw;
```

If `raw` has raw type `List`, what warning may the compiler emit?

**Answer:** An unchecked conversion warning.

### Question 4 — Heap Pollution

If a `List<String>` receives an `Integer` via a raw alias and is then read as `String`, what error can occur?

**Answer:** `ClassCastException` at the point where the `Integer` element is retrieved and used as a `String`.

### Question 5 — `@SafeVarargs`

Does this annotation automatically make a varargs method safe?

**Answer:** No. It is an author's commitment and does not change the runtime component type or erasure.

### Question 6 — `-Xlint:varargs`

Will every `String... values` method emit a warning?

**Answer:** No. `String` is a reifiable component type; the generic varargs risk in question does not arise.

### Question 7 — Fixing a Raw Receiver

If an API wants to accept any list solely for reading, what type should replace raw `List`?

**Answer:** `List<?>` is usually appropriate.

### Question 8 — `List<Object>` and `List<String>`

Can `List<String>` be assigned to `List<Object>`?

**Answer:** No, due to the invariance of Java generics.

### Question 9 — `Class.cast`

How can `String.class.cast(123)` help in an adapter?

**Answer:** It catches the wrong class at runtime via `ClassCastException`, instead of trusting an unchecked cast.

### Question 10 — Warnings and Builds

Which command enables all three lint categories and requires the compiler to fail when warnings occur?

**Answer:**

```bash
javac -Xlint:unchecked,rawtypes,varargs -Werror Main.java
```

### Question 11 — Warnings vs. Errors

Does a warning always block `.class` generation?

**Answer:** Not by default. `-Werror` can turn the presence of warnings into a build failure.

### Question 12 — stdout

If the compiler warns while running `javac`, is that warning part of the stdout produced by the program's `System.out.println`?

**Answer:** No. Distinguish the compile and run steps.

### Question 13 — Varargs Alias

Why can `Object[] alias = groups` be dangerous with `List<String>... groups`?

**Answer:** The alias can be used to write a `List<Integer>` into the array whose runtime component is raw `List`, violating the generic contract.

### Question 14 — Testing

After eliminating warnings, should you remove tests that check for wrong-typed data?

**Answer:** No. Lint does not prove every runtime path and does not replace testing.

### Question 15 — Suppression

What does an unchecked cast claimed to be safe require?

**Answer:** An explainable and verifiable invariant, narrow-scoped suppression, and tests at the data boundary.

## 33. Pre-Merge Practical Checklist

1. Build with the exact **target JDK**.
2. Enable `-Xlint:unchecked,rawtypes,varargs`.
3. Record all emitted warnings and classify them by location.
4. Convert raw types to parameterized types, wildcards, or typed adapters where appropriate.
5. Locate unchecked casts/conversions from legacy input, reflection, or untrusted collections.
6. Check whether data with the wrong generic argument can slip through casts or raw aliases.
7. For generic varargs, inspect writes, helper calls, aliasing, and escape paths.
8. Use `@SafeVarargs` only when the implementation is truly safe and the placement is valid.
9. Do not use broad suppressions to hide unanalyzed issues.
10. For unavoidable suppressions, document the reason and write tests.
11. Ensure compilation results and runtime results are verified separately.
12. Test with valid data, wrong-typed elements, `null`, and boundary cases.
13. Consider enabling `-Werror` once baseline warnings are under control.
14. Keep compiler flag configurations consistent between developer machines and CI.
15. In multi-module builds, confirm every relevant Java module is actually compiled with the flags.
16. Treat new warnings when upgrading dependencies or the JDK as a signal to investigate.
17. Do not assume "compiles cleanly" means "generic API is type-safe".
18. Prioritize eliminating the root cause over reducing warning line counts.

## 34. Summary and Official References

Enabling the following lint categories is an essential step when learning and auditing Java Generics:

```bash
javac -Xlint:unchecked,rawtypes,varargs Main.java
```

- **`rawtypes`** detects places where generic types are used without type arguments.
- **`unchecked`** detects operations whose type safety the compiler cannot fully prove, such as raw calls/conversions or casts with parameterized types.
- **`varargs`** helps detect potentially unsafe operations on varargs arrays with non-reifiable generic components, especially when code uses `@SafeVarargs`.

These are **compile-time warning mechanisms**, not runtime type-checking suites. Issues involving erasure, heap pollution, delayed casts, nulls, aliasing, or legacy APIs still need to be addressed through clear type design and testing.

The right workflow is: **enable warnings → read the cause → fix the generic signature or adapter → audit varargs → test at runtime → guard against new warnings in build/CI**. `@SuppressWarnings`, `@SafeVarargs`, and `-Werror` each have specific roles, but none can substitute for proving type safety.

Official reference sources:

- [JDK 17 `javac` tool documentation](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): `-Xlint`, `-Werror`, compiler options.
- [JLS §4.8 — Raw Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.8): raw types and unchecked behavior.
- [JLS §4.5 — Parameterized Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5): type arguments and generics.
- [JLS §4.12.2 — Variables of Reference Type](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.2): heap pollution.
- [JLS §4.7 — Reifiable Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.7): runtime type limitations.
- [JLS §8.4.1 — Formal Parameters](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.1): variable arity parameters.
- [JLS §9.6.4.7 — `@SafeVarargs`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.7): annotation placement and safety commitment.
- [Java SE 17 `java.lang.SafeVarargs`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/SafeVarargs.html): annotation API.
- [Java SE 17 `java.lang.SuppressWarnings`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/SuppressWarnings.html): suppression scope.
- [Java SE 17 `java.util.Collections`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html): checked collections wrappers and legacy boundaries.