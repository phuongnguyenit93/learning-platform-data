# Reproducing Raw Types and Heap Pollution and Fixing Them at the Source in Java Generics

## 1. Objectives of This Practice Lab

Java Generics allow the compiler to prevent a `List<String>` from accidentally receiving an `Integer`, yet that guarantee can be broken when a program uses **raw types**, unchecked casts, unsafe generic varargs, or passes data through legacy APIs lacking full generic information.

**Heap pollution** occurs when a variable of a parameterized type points to an object that does not conform to its expected parameterized type. In our core example, a variable is declared as `List<String>`, yet that very list contains an `Integer` after code invokes `add` through a raw `List` reference.

This lab focuses on the workflow **reproduce → read warnings and errors → trace the pollution site → fix at the source → verify no recurrence**, rather than merely placing `@SuppressWarnings` around warnings.

You will learn how to:

- Distinguish raw `List`, `List<Object>`, `List<?>`, and `List<String>`.
- Reproduce writing an Integer into a list with a String contract through a raw alias.
- Explain why the write statement can succeed while `ClassCastException` occurs **on the read side**.
- Enable `-Xlint:rawtypes,unchecked` and understand which warnings require fixes on which lines.
- Rewrite a legacy API into a properly typed generic/specific method right at the insertion point.
- Build a validation boundary for `List<?>` input before converting to `List<String>`.
- Use `Class<T>.cast` and `Collections.checkedList` within their proper scopes, knowing their limitations.
- Reproduce another heap pollution case involving generic varargs.
- Verify valid Java 17 code and distinguish compile errors, compiler warnings, and runtime exceptions.

## 2. From Generic Safety to the Loophole Caused by Raw Types

In normal typed code:

```java
List<String> names = new ArrayList<>();
names.add("An");
names.add("Binh");
// names.add(42); // Does not compile.
```

The compiler knows `List<String>.add` requires String. Attempting to pass 42 fails the build. That is where generic type checking delivers its greatest value: mistakes are caught **right at the write site**.

However, Java also supports **raw types** for compatibility with pre-Java 5 code:

```java
List raw = names;
raw.add(42);
```

Raw `List` omits the type argument, causing the compiler to lose element type information on the `raw` reference. The call `raw.add(42)` is accepted **with an unchecked warning**, while the underlying object remains the exact `ArrayList` referenced by `names`. Afterward, `names` contains an Integer violating `List<String>`.

Java did not create two separate lists here. The variables `names` and `raw` are **two aliases** to the same object. No copy is created automatically when you assign `List raw = names`.

### Easily confused types

| Reference type | Meaning | Read/Write capability |
| --- | --- | --- |
| `List<String>` | Contract requires String elements. | `add(String)` allowed; `get` is typed as String. |
| `List<Object>` | Contract permits Object elements. | Can add String, Integer, and Object per API; cannot be assigned from `List<String>`. |
| `List<?>` | Holds an unknown element type. | Safely readable as Object; cannot add arbitrary non-null values. |
| Raw `List` | Drops the generic interface's type argument. | Allows `add(42)` with an unchecked warning; easily breaks contracts of other typed aliases. |

**`List<Object>` is not the modern spelling of raw `List`.** `List<Object>` is still a parameterized type checked by the compiler. `List<?>` is not raw either: it retains the constraint that an element type exists though unknown, blocking unverified writes.

Example:

```java
List<String> names = new ArrayList<>();
List<?> view = names;
Object item = view.isEmpty() ? null : view.get(0);

// view.add(42); // Does not compile.
```

`List<?>` is a view **to which arbitrary non-null values cannot be added statically**, but that does not make the collection immutable. If another typed alias mutates the list, the view sees the changes; certain operations like `clear()` or inserting `null` also depend on the specific API and collection. So "read-only" here refers to **typed element writes**, not a blanket promise of immutability.

## 3. Reproducing Heap Pollution via a Raw Alias

First, save the `RawHeapPollutionDemo.java` program in section 7 and run the exact compile command. Here is a condensed snippet to grasp the core idea:

```java
static void legacyAppend(List raw) {
    raw.add(42);
}

List<String> names = new ArrayList<>(List.of("An"));
legacyAppend(names);

System.out.println(names); // [An, 42]
String second = names.get(1); // ClassCastException at runtime.
```

This snippet illustrates the method and calls to place inside an appropriate class/`main`; the complete program in section 7 includes imports and exception handling.

Sequence of events:

1. The caller creates an `ArrayList` and holds it under a `List<String>` reference.
2. `legacyAppend(List raw)` receives **the same object** through a raw parameter.
3. `raw.add(42)` inserts an Integer. There is no runtime check inside ArrayList verifying that the original alias's type argument was String.
4. Printing the list outputs `[An, 42]` because `toString()` handles both String and Integer as Objects.
5. `String second = names.get(1)` demands a String. The compiler permitted the read based on `names`'s type argument.
6. When the actual element is an Integer, the compiler-inserted cast to String at the use site fails and throws `ClassCastException`.

**The true bug site is the line `raw.add(42)`, not a flaw in the String getter.** The exception merely manifests on the read side. That is why the stack trace and the site where data was corrupted can be far apart in a codebase.

### Two typical compiler warnings

When enabling:

```bash
javac --release 17 -Xlint:rawtypes,unchecked RawHeapPollutionDemo.java
```

the compiler was verified to emit two warnings from the example's raw code:

```text
[rawtypes] found raw type: List
[unchecked] unchecked call to add(E) as a member of the raw type List
```

The first warning points out that parameter `List raw` lacks type arguments. The second flags the exact write operation whose safety the compiler cannot verify.

Do not dismiss these as "harmless warnings because the code still runs." The code **genuinely inserted the wrong element type**.

## 4. Why Does the Exception Trigger on Read Instead of Write?

Generic type erasure means `List<String>` and `List<Integer>` do not have separate runtime classes. In bytecode, `List.get(int)` returns `Object` according to its erased signature. The compiler inserts a `checkcast java/lang/String` where the caller consumes the value as a String.

Conceptually:

```java
// Source logic:
String second = names.get(1);

// Conceptual illustration after erasure:
Object element = names.get(1);
String second = (String) element;
```

This is a **conceptual illustration**, not verbatim javac output. The JVM may optimize or generate different bytecode depending on context, yet in principle the result of `get` must be String-compatible at the use site.

Thus:

```java
System.out.println(names);       // May print [An, 42].
Object value = names.get(1);     // Can read Integer as Object.
String text = names.get(1);      // ClassCastException.
```

If debugging focuses solely on `String text = ...`, you might mistakenly patch it by changing the cast or turning `text` into `Object`. Doing so **does not fix the polluted data** and merely shifts the failure elsewhere.

### Why no `ArrayStoreException`?

Java arrays are reified: an actual `String[]` retains component type String at runtime, so the JVM blocks writing an Integer through an `Object[]` alias with `ArrayStoreException`.

A standard `ArrayList<String>` carries no runtime component type "String" the way a `String[]` does; ArrayList itself stores Object references. Consequently, writes via a raw API slip through, and the failure surfaces only when later code requires a String.

**Key difference:** `ArrayStoreException` belongs to runtime array component checks; `ClassCastException` in our example stems from the cast at the read site. Both are runtime type errors, yet their causes and check sites differ.

## 5. Workflow for Tracing Pollution Sources in a Project

When production reports `ClassCastException: Integer cannot be cast to String` at a generic getter:

1. **Identify the polluted collection:** which instance is it, who created it, and which methods share it?
2. **Trace alias paths:** are there `List raw`, `Map raw`, `Collection raw`, or `Object[]` aliases?
3. **Locate `unchecked`/`rawtypes` warnings:** these usually pinpoint where the compiler lost type-checking visibility.
4. **Inspect all write operations:** `add`, `set`, `put`, `addAll`, reflection, or legacy API adapters.
5. **Check unchecked casts:** is there a `(List<String>) unknown` cast without element validation?
6. **Inspect actual runtime elements:** print `getClass().getName()` of the offending element via an Object reference rather than casting to String again.
7. **Fix at the write boundary:** apply typed signatures or input validation rather than catching `ClassCastException` in the getter.
8. **Add regression tests:** prove that writing an Integer is rejected by the compiler or actively rejected at the boundary.
9. **Check whether legacy aliases still hold mutable references:** a new signature patch may be insufficient if old code still shares the collection.
10. **Tighten build checks:** systematically eliminate new `rawtypes` and `unchecked` warnings, then tighten build settings when ready.

If the application stores data from JSON, JDBC, reflection, or legacy libraries, inspect where **Objects are converted into domain types**. A parameterized cast only checks the outer container to the extent checkable at runtime; it never proves every inner element is valid.

## 6. Fixing at the Source: Turning a Raw API into a Typed API

The pollution site in our example:

```java
static void legacyAppend(List raw) {
    raw.add(42);
}
```

If the method's domain responsibility is **adding a name**, rewrite it to:

```java
static void appendName(List<String> target, String name) {
    target.add(name);
}
```

Caller:

```java
List<String> names = new ArrayList<>(List.of("An"));
appendName(names, "Binh");
// appendName(names, 42); // Compile error.
```

Now the compiler has enough information to reject an Integer right at the boundary. No `@SuppressWarnings` is needed, and getters no longer crash unexpectedly.

### A verified compile error

**File `TypedListRejectsWrongValue.java` — intentionally fails to compile:**

```java
import java.util.List;

class TypedListRejectsWrongValue {
    static void append(List<String> names) {
        names.add(42);
    }
}
```

Run:

```bash
javac --release 17 -Xdiags:verbose TypedListRejectsWrongValue.java
```

Key compiler output:

```text
no suitable method found for add(int)
method List.add(String) is not applicable
(argument mismatch; int cannot be converted to String)
```

This is the desired behavior: type errors are caught at compile time before invalid data enters the collection.

### What if business logic genuinely accepts multiple types?

Not every raw method should become `List<String>`. If a method's job is adding **a value matching whatever type the caller specifies**, use a generic method:

```java
static <T> void appendTyped(List<T> target, T value) {
    target.add(value);
}
```

However, do not assume `<T> void appendTyped(List<T>,T)` always forces callers to pass two expressions of the exact same runtime class; inference solves all constraints together and may pick a common supertype in suitable contexts. If the contract mandates a list of Strings, the concrete signature `List<String>` is clearest.

If the method **only reads** collections of any type:

```java
static void printElements(List<?> values) {
    for (Object value : values) {
        System.out.println(value);
    }
}
```

`List<?>` is far better than raw `List` because it preserves compile-time bounds. It prevents arbitrarily adding an Object into a list that might actually be `List<String>`.

## 7. Complete Java 17 Program: Reproduce and Fix

**File `RawHeapPollutionDemo.java`:**

```java
import java.util.ArrayList;
import java.util.List;

public class RawHeapPollutionDemo {
    static void legacyAppend(List raw) {
        raw.add(42);
    }

    static void appendName(List<String> target, String name) {
        target.add(name);
    }

    static List<String> checkedStringCopy(List<?> input) {
        List<String> result = new ArrayList<>();
        for (Object item : input) {
            if (!(item instanceof String text)) {
                throw new IllegalArgumentException("not String: " + item);
            }
            result.add(text);
        }
        return List.copyOf(result);
    }

    static <T> List<T> checkedCopy(List<?> input, Class<T> type) {
        List<T> result = new ArrayList<>();
        for (Object item : input) {
            result.add(type.cast(item));
        }
        return List.copyOf(result);
    }

    public static void main(String[] args) {
        List<String> names = new ArrayList<>(List.of("An"));
        legacyAppend(names);
        System.out.println("runtimeContent=" + names);

        try {
            String second = names.get(1);
            System.out.println("read=" + second);
        } catch (ClassCastException error) {
            System.out.println("rawFailure="
                    + error.getClass().getSimpleName());
        }

        List<String> fixed = new ArrayList<>(List.of("An"));
        appendName(fixed, "Binh");
        System.out.println("typed=" + fixed);

        System.out.println("checked="
                + checkedStringCopy(List.of("A", "B")));

        try {
            checkedStringCopy(names);
        } catch (IllegalArgumentException error) {
            System.out.println("rejected=" + error.getMessage());
        }

        System.out.println("tokenCopy="
                + checkedCopy(List.of("C", "D"), String.class));

        try {
            checkedCopy(List.of("A", 42), String.class);
        } catch (ClassCastException error) {
            System.out.println("tokenRejected="
                    + error.getClass().getSimpleName());
        }

        List<?> readOnlyView = names;
        System.out.println("unknownSize=" + readOnlyView.size());
        System.out.println("unknownElement="
                + readOnlyView.get(1).getClass().getSimpleName());
    }
}
```

**Compile with warnings enabled:**

```bash
javac --release 17 -Xlint:rawtypes,unchecked RawHeapPollutionDemo.java
java RawHeapPollutionDemo
```

Note: This program **deliberately uses a flawed raw API**, so the compiler emits two warnings as shown in section 3. Those warnings are part of the lab exercise, not a JDK setup error.

**Verified stdout:**

```text
runtimeContent=[An, 42]
rawFailure=ClassCastException
typed=[An, Binh]
checked=[A, B]
rejected=not String: 42
tokenCopy=[C, D]
tokenRejected=ClassCastException
unknownSize=2
unknownElement=Integer
```

### Reading each output line

- `runtimeContent=[An, 42]`: the raw write modified the same object held by the typed reference.
- `rawFailure=ClassCastException`: the exception occurred when retrieving the second element as String.
- `typed=[An, Binh]`: after fixing the signature to `List<String>`, typed additions are compiler-enforced.
- `checked=[A, B]`: the boundary produced a copy after verifying each element is a String.
- `rejected=not String: 42`: the boundary caught the invalid input and threw a domain-meaningful error instead of letting a delayed CCE occur.
- `tokenCopy=[C, D]`: the `Class<T>` variant produced a typed copy after invoking `type.cast` on each element.
- `tokenRejected=ClassCastException`: the type token blocked Integer when the caller requested String.
- `unknownSize=2` and `unknownElement=Integer`: a `List<?>` can still inspect the wrong object as Object without casting to String.

### Why does code compile despite warnings?

`javac` supports raw types for backward compatibility with older Java code. Even though `raw.add(42)` lacks full generic verification, javac allows compilation when an issue only triggers a warning and breaks no mandatory constraints. It is a **type-safety warning**, and this program proves through runtime failure that a warning can reflect a real bug.

In non-demonstration production code, fix raw methods and adopt a build policy to reduce and eliminate warnings.

## 8. Data Already Arriving as `List<?>`: Validate and Copy Safely

Sometimes external data is known only as a list of unknown element type:

```java
List<?> rawInput = someExternalApi();
```

This is illustrative syntax; `someExternalApi` must be supplied by your application and is not part of the JDK.

You **cannot** safely convert it to a String list simply via:

```java
// UNSAFE:
@SuppressWarnings("unchecked")
List<String> names = (List<String>) rawInput;
```

Casting from `List<?>` to `List<String>` is unchecked because the JVM does not verify every generic element at runtime. A cast that succeeds only confirms the outer container matches what runtime can check; elements inside could still be Integers.

### Fix: iterate as Object and build a new typed collection

```java
static List<String> checkedStringCopy(List<?> input) {
    List<String> result = new ArrayList<>();
    for (Object item : input) {
        if (!(item instanceof String text)) {
            throw new IllegalArgumentException("not String: " + item);
        }
        result.add(text);
    }
    return List.copyOf(result);
}
```

Advantages:

1. Every element is validated before entering the String list.
2. Only genuine String values enter `result`.
3. No unchecked cast is needed.
4. Returns a structurally unmodifiable snapshot, preventing external mutable aliases from modifying the new collection after validation.
5. If a non-String value appears, the exception triggers **right at the data boundary** with an identifiable message.

Example:

```java
List<String> a = checkedStringCopy(List.of("A", "B"));
// checkedStringCopy(List.of("A", 42)); // IllegalArgumentException.
```

Clarify the null policy: `null instanceof String` evaluates to false, so this method actively rejects null. `List.copyOf` also rejects null elements. That is a specific contract choice, not an automatic property of every String list.

### Defensive copy is not deep copy

`List.copyOf(result)` creates a structurally unmodifiable collection; it does not make the contained objects immutable. For String that poses little risk because String is immutable; for `List<MutableEntity>`, each MutableEntity can still mutate its state. If deep immutability is required, clone or convert objects into immutable representations.

## 9. Generic Boundary Using `Class<T>`

When an adapter must support multiple simple runtime types, it can accept a type token:

```java
static <T> List<T> checkedCopy(List<?> input, Class<T> type) {
    List<T> result = new ArrayList<>();
    for (Object item : input) {
        result.add(type.cast(item));
    }
    return List.copyOf(result);
}
```

Caller:

```java
List<String> names = checkedCopy(List.of("A", "B"), String.class);
List<Integer> ids = checkedCopy(List.of(1, 2), Integer.class);
```

`Class<T>.cast` is a runtime check backed by the Class token. If a value is incompatible with String.class, it throws ClassCastException at the boundary.

**Limitations to understand:**

- `String.class` checks String; `Integer.class` checks Integer.
- There is no `List<String>.class` literal for deeply verifying nested type arguments.
- `List.class` checks only the outer List container, not every String inside.
- `Class.cast(null)` accepts null; however, `checkedCopy` uses `List.copyOf`, so null will be rejected at the copy step. If null is valid domain data, a different contract and implementation are required.

A framework receiving `Type`/`ParameterizedType` metadata can know the expected generic element type, yet it still must **perform validation/deserialization itself**. Metadata does not turn the JVM into an automatic deep validator for nested generic types.

## 10. `Collections.checkedList`: Blocking Dynamic Raw Writes at the Boundary

If you must still interoperate with a legacy API holding a raw `List` reference that might call `add`, `Collections.checkedList` provides a **dynamic type-checking view** for writes going through the wrapper.

Example:

```java
List<String> checkedNames =
        Collections.checkedList(new ArrayList<>(), String.class);

checkedNames.add("An");
List raw = checkedNames; // Raw alias at legacy boundary.
raw.add(42);             // ClassCastException right at the write operation.
```

This snippet requires importing `Collections`, `ArrayList`, and `List`, and intentionally triggers warnings for using raw types.

How it helps: the wrapper holds String.class, so it checks elements added through the wrapper at runtime. This provides an additional line of defense when you cannot rewrite all legacy code immediately.

### Program verifying wrapper behavior

**File `CheckedBoundaryDemo.java`:**

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class CheckedBoundaryDemo {
    static List<String> makeCheckedNames() {
        return Collections.checkedList(new ArrayList<>(), String.class);
    }

    static void legacyWrite(List raw, Object value) {
        raw.add(value);
    }

    public static void main(String[] args) {
        List<String> checkedNames = makeCheckedNames();
        checkedNames.add("An");
        try {
            legacyWrite(checkedNames, 42);
        } catch (ClassCastException e) {
            System.out.println("writeRejected="
                    + e.getClass().getSimpleName());
        }
        System.out.println("checkedContents=" + checkedNames);

        List<String> storage = new ArrayList<>(List.of("An"));
        List<String> wrapper =
                Collections.checkedList(storage, String.class);
        legacyWrite(storage, 42);
        System.out.println("wrapperDidNotRetroactivelyValidate="
                + wrapper);
    }
}
```

Compile and run:

```bash
javac --release 17 -Xlint:rawtypes,unchecked CheckedBoundaryDemo.java
java CheckedBoundaryDemo
```

The code intentionally has raw `List` and an unchecked write in `legacyWrite`, so the compiler emits two warnings regarding raw types/unchecked calls during testing.

**Verified stdout:**

```text
writeRejected=ClassCastException
checkedContents=[An]
wrapperDidNotRetroactivelyValidate=[An, 42]
```

### Two important limitations of checked wrappers

**First:** a checked wrapper **does not scan, fix, or reject elements already present** in the collection when created. If the underlying collection was already polluted, wrapping it does not clean the data.

**Second:** if code still holds a direct alias to the underlying collection, writes through that alias **bypass the wrapper**. In the example, `storage` still accesses the original ArrayList, so `legacyWrite(storage, 42)` succeeds and the wrapper later observes `[An, 42]`.

Therefore, a checked view is a helpful safeguard at controlled boundaries, not a replacement for eliminating raw aliases and fixing API signatures. Restrict access to the underlying collection if you want every operation routed through the wrapper.

## 11. Another Heap Pollution Vector: Generic Varargs and Non-Reifiable Arrays

Heap pollution does not come solely from raw `List`. Another source is **generic varargs**, where the compiler bridges parameterized types with arrays at runtime.

Look at this intentionally unsafe example:

**File `UnsafeVarargsPollutionDemo.java`:**

```java
import java.util.List;

public class UnsafeVarargsPollutionDemo {
    static void corrupt(List<String>... groups) {
        Object[] alias = groups;
        alias[0] = List.of(42);
        String item = groups[0].get(0);
        System.out.println(item);
    }

    public static void main(String[] args) {
        try {
            corrupt(List.of("A"), List.of("B"));
        } catch (ClassCastException error) {
            System.out.println("varargsFailure="
                    + error.getClass().getSimpleName());
        }
    }
}
```

Compile:

```bash
javac --release 17 -Xlint:all UnsafeVarargsPollutionDemo.java
java UnsafeVarargsPollutionDemo
```

**Verified:** `javac` emits two key warnings:

```text
[unchecked] Possible heap pollution from parameterized vararg type List<String>
[unchecked] unchecked generic array creation for varargs parameter of type List<String>[]
```

Stdout:

```text
varargsFailure=ClassCastException
```

### Sequence in the varargs case

1. The parameter `List<String>... groups` is backed by an array whose runtime component type cannot distinguish a List of Strings from a List of Integers.
2. The array of lists is viewed through an `Object[]` alias.
3. `alias[0] = List.of(42)` passes the array store check because the new element is still a List at runtime.
4. `groups[0].get(0)` returns an Integer, while the caller site expects a String.
5. ClassCastException triggers when String is required.

This is a **distinct heap pollution pathway**, separate from the earlier raw List bug. It shows why even a generic-looking signature can be dangerous if code misuses a non-reifiable varargs array.

### Do not mask it mechanically with `@SafeVarargs`

`@SafeVarargs` is an author's assertion that the method body performs no unsafe operations on the varargs array in contexts permitted by the compiler. **The `corrupt` method above is unsafe**, as it deliberately writes a List of Integers into a slot expected to hold a List of Strings. Never attach `@SafeVarargs` solely to silence warnings.

If an API genuinely needs multiple lists, consider a parameter `List<? extends List<String>>` or a typed collection of groups, or write a varargs method that never writes to or exposes the backing array, verifying safety before using the annotation where permitted.

## 12. Why `@SuppressWarnings("unchecked")` Cannot Fix the Bug

The annotation merely tells the compiler not to display a warning category within the annotated scope. It does not:

- Validate elements inside a `List`.
- Convert Integer into String.
- Restore erased generic type arguments.
- Prevent raw aliases from writing bad data.
- Stop `ClassCastException`.
- Fix an unsafe generic varargs implementation.

Example:

```java
@SuppressWarnings("unchecked")
static List<String> unsafeAssumeStrings(Object obj) {
    return (List<String>) obj;
}
```

This method can return a List that actually holds Integers. Callers reading an element as String will crash. Silencing the warning does not make the data valid.

### When can suppression ever be considered?

A legacy adapter may occasionally require a cast the compiler cannot verify, while the developer has guarantees from a protocol, schema, or explicit validation. In that case:

1. Verify the invariant **before casting**; validate the data whenever possible.
2. Narrow suppression scope to **a single variable or small adapter method**, never casually across an entire class or package.
3. Document the exact invariant the adapter relies on.
4. Write tests covering both valid and invalid element types.
5. Prioritize updating upstream APIs so the cast becomes unnecessary.

Never treat suppression as "fixing at the source." Fixing at the source means restoring a typed contract and guarding insertion/ingestion boundaries.

## 13. Distinguishing Heap Pollution and Related Errors

| Phenomenon | Where it appears | Symptom |
| --- | --- | --- |
| Raw type | Java source code | `List raw` instead of `List<String>`/`List<?>`. |
| Unchecked operation | Compilation | `[unchecked] unchecked call`, cast, or generic array creation. |
| Heap pollution | Type state of references/objects in the program | Typed reference sees data violating its type argument. |
| ClassCastException | Runtime | Code expects String but encounters Integer. |
| ArrayStoreException | Runtime | Array with runtime component type rejects writing an incompatible object. |
| Compile-time type error | Compilation | `List<String>.add(42)` rejected immediately. |
| UnsupportedOperationException | Runtime | Collection refuses mutation, even with valid element types. |
| NullPointerException | Runtime | Null data violates an operation's contract, such as `List.copyOf`. |

A collection can **simultaneously be heap-polluted and print normally**. Heap pollution is a violation of the type contract, not guaranteed to crash the program immediately.

A method with a valid generic signature can still be unsafe if it uses unchecked casts or uncontrolled aliases. The compiler protects **paths with sufficient type information**, without proving the runtime logic of every external library.

## 14. Fixing at the Source: Practical Legacy API Migration Plan

In large projects, removing raw types often proceeds incrementally due to legacy APIs and un-migrated consumers.

### Phase A — Isolate and measure warnings

Run:

```bash
javac --release 17 -Xlint:rawtypes,unchecked *.java
```

Wildcard expansion differs across shells, IDEs, and build tools; in Maven/Gradle, configure `JavaCompile`/`javac` options as needed. For this lab's examples, compile each file individually as instructed.

Categorize warnings:

- Raw declarations directly under your control.
- Unchecked calls/assignments from older APIs.
- Intentional casts lacking validation.
- Generic varargs and array alias operations.
- Reflection/deserialization boundaries.

Prioritize fixing **write paths into typed collections**, because they can corrupt data shared across many consumers.

### Phase B — Provide safe new APIs

Example legacy API:

```java
void addRecords(List list, Object item);
```

Typed design per domain:

```java
void addNames(List<String> names, String name);
```

or generic method:

```java
<T> void addRecord(List<T> target, T item);
```

The signatures above illustrate design declarations; place them in classes/interfaces with implementations in a real project.

For external inputs with unknown type arguments, use `List<?>` for reading and validate/copy into a new typed structure.

### Phase C — Controlled backward compatibility

If legacy callers still rely on the raw API, introduce a small **adapter**:

- Stop letting raw lists propagate deeper into core business logic.
- Convert Object to domain types right at the boundary.
- Reject invalid types with clear error messages.
- Return a new typed collection rather than leaking mutable aliases.
- Use dynamic checked views only where callers cannot be updated yet, mindful of aliases and pre-existing data.

Never merely change a local variable `List raw` to `List<String>` via an unchecked cast without checking elements; that is **relabeling the type**, not validating the data.

### Phase D — Tighten the build after fixing

Once active warnings are resolved, configure the compiler to catch new raw/unchecked regressions:

```bash
javac --release 17 -Xlint:rawtypes,unchecked -Werror SafeSource.java
```

`-Werror` turns warnings into build failures, so enable it only after establishing a clean baseline. When temporary migration exceptions are needed, isolate legacy adapters with clear documentation and technical deadlines rather than disabling warnings indefinitely.

### Phase E — Regression tests

Test in both directions:

- **Positive:** typed API accepts String and produces expected output.
- **Negative:** attempting to add Integer to `List<String>` fails to compile or is actively rejected at the runtime boundary.

Keep negative compilation tests in separate files/fixtures so the main build is not intentionally broken.

## 15. Common Pitfalls When Migrating from Raw to Generic

**Pitfall 1 — Replacing raw with `List<Object>` everywhere.** This changes the contract and typically cannot accept `List<String>` due to invariance. If only reading any list, `List<?>` is appropriate.

**Pitfall 2 — Casting `List<?>` to `List<String>` for convenience.** The compiler cannot verify every element is a String; an unchecked cast can mask heap pollution.

**Pitfall 3 — Only catching `ClassCastException` at the read site.** That treats only the symptom; the raw write site still corrupts data other consumers may read.

**Pitfall 4 — Putting `@SuppressWarnings("unchecked")` on an entire class.** Warnings disappear while generic checks remain bypassed in risky places.

**Pitfall 5 — Treating `Collections.checkedList` as a data sanitizer.** Checked views do not validate pre-existing elements and do not block writes via direct aliases to the backing list.

**Pitfall 6 — Believing type erasure means zero runtime type checks.** The JVM still checks casts, ArrayStore, Class tokens, and reifiable object types. Only **non-reified type arguments** lack deep automatic JVM verification.

**Pitfall 7 — Assuming `List<?>` is immutable.** A wildcard view blocks many typed additions at compile time, yet does not render the backing collection immutable.

**Pitfall 8 — Blaming the compiler for raw List warnings.** Raw types remain for historical compatibility; warnings are signals helping you locate and fix lost type information.

**Pitfall 9 — Creating `List<String>[]` arrays and casting unsafely.** Non-reifiable generic arrays easily cause heap pollution, especially via `Object[]` aliases or varargs.

**Pitfall 10 — Thinking a Class-token checked cast validates nested `List<String>`.** `Class<List>` knows only List; String elements inside must be validated separately.

**Pitfall 11 — Ignoring source mutability.** Validating or copying once does not stop external mutable aliases from mutating the source later. Returning a fresh copy without sharing the backing collection enforces the boundary.

**Pitfall 12 — Forgetting null contracts.** `type.cast(null)` does not reject null by itself, whereas `List.copyOf` rejects null; align the adapter's policy explicitly.

## 16. Technique for Inspecting Polluted Data Without Triggering a New CCE

When suspecting a `List<String>` has been polluted with wrong types, **do not immediately iterate it with a String loop variable**:

```java
// May throw ClassCastException when encountering a non-String element:
for (String name : names) {
    System.out.println(name.length());
}
```

Instead, inspect via `List<?>`/Object:

```java
List<?> unknown = names;
for (Object item : unknown) {
    System.out.println(item == null
            ? "null"
            : item.getClass().getName());
}
```

With mixed String and Integer data, you see the real runtime classes without forcing each element to cast to String. This is a **diagnostic** step, not a collection sanitizer.

After finding bad values:

1. Trace the write path that inserted them.
2. Fix that write site and related signatures.
3. Decide whether legacy data should be discarded or converted.
4. Return a newly validated collection if consumers rely on a strict invariant.
5. Add tests protecting both legacy data handling and the fixed flow.

Note when logging personal or sensitive data for debugging: log only classes/types and minimal metadata, avoiding dumping full contents unnecessarily.

## 17. Comparing Boundary Protection Approaches

| Approach | What does it check? | Strengths | Limitations |
| --- | --- | --- | --- |
| `List<String>` in signature | Compiler checks typed calls. | Catches bugs as code is written. | Raw/unchecked legacy code can still bypass it. |
| `checkedStringCopy(List<?>)` | Each element is a String while copying. | Blocks bad data and returns a fresh snapshot. | O(n) traversal; must define null/error policy. |
| `checkedCopy(List<?>,Class<T>)` | `Class.cast` per element. | Reusable across many runtime classes. | Does not verify nested generic arguments. |
| `Collections.checkedList(backing,String.class)` | Insertions routed through wrapper. | Runtime defense at legacy write paths. | Does not validate old data; backing aliases can bypass it. |

You do not need to apply **all** of these everywhere. In cleanly typed codebases, signatures and compiler checks suffice for most core logic. Boundaries ingesting external data need validation/copying. Wrappers serve as extra defense while legacy writers remain active.

## 18. Practice Exercises and Answers

### Exercise 1 — Where does the error appear?

```java
List<String> names = new ArrayList<>();
List raw = names;
raw.add(42);
String s = names.get(0);
```

**Answer:** The raw write is accepted with a warning; when reading as String, `ClassCastException` can occur. The root defect to fix first is `raw.add(42)` or the API signature permitting raw writes.

### Exercise 2 — Can `List<Object>` replace `List<?>` to accept any typed list?

**Answer:** No. `List<String>` is not a subtype of `List<Object>`. `List<?>` is suitable for APIs inspecting any List without allowing arbitrary element additions.

### Exercise 3 — Does `List<?>` remove wrong elements?

**Answer:** No. It only restricts what the compiler permits through that reference; the underlying object and all other aliases keep their existing data.

### Exercise 4 — Why can a generic getter throw ClassCastException after a raw setter finishes?

**Answer:** Type erasure means the runtime List does not deeply enforce String elements on raw writes. When `get`'s result is used as String, the compiler inserts a cast and discovers the Integer.

### Exercise 5 — Which warnings should be taken seriously?

**Answer:** `[rawtypes]` on raw declarations and `[unchecked] unchecked call` on write operations are direct signals of lost type checking. Both can lead to heap pollution.

### Exercise 6 — How do you fix `void addName(List raw,Object value)`?

**Answer:** If the business operation adds Strings, change it to `void addName(List<String> names,String value)`; the compiler will then reject Integers at callers.

### Exercise 7 — What if the input's element type is unknown?

**Answer:** Accept `List<?>`, iterate each Object, check `instanceof String`, and copy into a new `List<String>`. Never cast the entire list without validating elements.

### Exercise 8 — Can a Class token validate `List<String>`?

**Answer:** `String.class` validates each String when you call `cast` on elements. `List.class` checks only the container; there is no `List<String>.class` for the JVM to scan the entire list.

### Exercise 9 — Why is `Collections.checkedList` insufficient if a backing alias still exists?

**Answer:** A checked wrapper intercepts only operations made through the wrapper. A raw writer using an alias to the backing list can bypass it and insert wrong types.

### Exercise 10 — Should `@SafeVarargs` be used to silence warnings on a method that deliberately writes a List of Integers into a List-of-Strings array?

**Answer:** No. The annotation is valid only when the implementation upholds the corresponding safety guarantee; annotating an unsafe method does not fix heap pollution.

### Exercise 11 — Do heap pollution and ClassCastException always occur on the same line?

**Answer:** No. Heap pollution may be introduced at a raw write, whereas CCE occurs later at a consumer reading as String.

### Exercise 12 — How can you check an element's real runtime class without casting to String?

**Answer:** Use `List<?>`, iterate as `Object`, then call `item.getClass()` with a null check. This is a diagnostic step, not a substitute for validation/copying.

### Exercise 13 — Why is `String[]` different from `List<String>`?

**Answer:** A String array retains its runtime component type and performs array store checks; `List<String>` undergoes type erasure at the runtime class level and does not enforce String on raw List writes.

### Exercise 14 — How should already-polluted legacy data be handled after fixing the API?

**Answer:** Do not assume data cleans itself. Inspect or convert each element, reject invalid values per contract, create a fresh collection if needed, and add regression tests.

### Exercise 15 — Does warning-free compilation guarantee 100% of runtime data is valid?

**Answer:** No. External inputs, reflection, native libraries, raw legacy code, and unchecked boundaries can still introduce issues. Eliminating raw/unchecked usage in core logic is still essential so the compiler protects as much as possible.

## 19. Checklist for Fixing Heap Pollution Bugs

1. **Reproduce the exact input** that puts a wrong element into a typed list.
2. **Trace where the object was created** and every alias pointing to it.
3. **Enable compiler warnings** with `-Xlint:rawtypes,unchecked`.
4. **Find the earliest unchecked write:** raw add/set/put, cast, or varargs alias.
5. **Define the expected invariant:** e.g., every element must be a non-null String.
6. **Fix signatures at the source:** `List<String>` or `List<T>` matching real intent.
7. **Use `List<?>` for read-only views**, never raw types.
8. **Validate external input** before adopting a stronger typed view.
9. **Create defensive copies** when needed to stop mutable aliases from corrupting validated data.
10. **Consider checked wrappers** while legacy writers remain, limiting backing aliases.
11. **Avoid unjustified warning suppression**; confine adapters tightly.
12. **Add negative compile tests** ensuring wrong writes are rejected by the compiler.
13. **Add negative runtime tests** for invalid inputs at boundaries.
14. **Verify null handling, mutability, nested generics, and varargs** where relevant.
15. **Re-read stack traces:** after fixing, errors should fail at the source/boundary rather than as a late CCE.
16. **Audit other consumers** that shared the collection for lingering polluted data.

## 20. Summary

Raw types allow legacy Java code to drop type arguments from generic references. If a raw alias writes an incompatible value into a collection, typed variables still point to the same object while holding data that violates their contract — that is **heap pollution**. Java may warn at the write site yet throw `ClassCastException` much later at a read site.

The proper solution is not hiding stack traces, adding casts, or adding `@SuppressWarnings`. **Fix at the source** with typed signatures, eliminate raw aliases, validate unknown inputs at boundaries, and produce fresh snapshots when protecting invariants from external writers. `Collections.checkedList` and `Class<T>` are helpful supporting tools, each with well-defined scope limits.

**Most important rule:** Wherever data enters a typed collection must be where the type contract is enforced. Restoring that boundary lets the compiler catch errors as code is written, instead of letting an unsuspecting consumer fail at runtime.