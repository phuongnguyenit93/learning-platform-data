# Distinguishing Language Limits from Limits of a Specific API in Java Generics

When a piece of Java code involving generics fails to compile or reaches a call and throws an exception, the first question should not be "Does Java Generics have this limitation?" but rather: **does the limit come from the Java language itself, from the signature/types chosen by the API author, or from the runtime contract of a specific API/implementation?**

These three layers are related, yet distinct:

1. **Language rules:** the Java Language Specification (JLS) defines which code is valid—such as invariant generics, disallowing primitive type arguments in standard generics, forbidding `new T[]`, and forbidding a class's type parameter in static contexts. Writing invalid code is rejected by the compiler regardless of which library you use.
2. **API signature constraints (API type contract):** library authors choose `List<? extends Number>`, `<T extends Number>`, `Consumer<? super T>`, or specific overloads. The compiler enforces those constraints according to Java's rules, yet **choosing that signature** is an API design decision, not a language rule requiring every generic API to accept only `Number`.
3. **Runtime contract of the API/implementation:** `List.of` forbids `null` elements and does not support modification; `ArrayList` allows adding elements including `null`; `Arrays.asList` allows `set` but not resizing. These differences typically surface only at runtime, even when all variables have type `List<String>`.

Understanding these boundaries leads to the right fix: **do not try to cast around a language rule**, and do not blame generic type erasure for every `UnsupportedOperationException` or `NullPointerException`.

## 1. Classification map: which layer is the error in?

| Situation | Primary layer | Typical symptom | Resolution |
| --- | --- | --- | --- |
| `List<int>` | Language | Compilation error: type argument must be a reference type | Use `List<Integer>`, or `int[]` array if appropriate |
| Assigning `List<String>` to `List<Object>` | Language | Compilation error due to invariance | Choose wildcards or another API matching read-write direction |
| `new T[10]` with generic `T` | Language | `generic array creation` error | Use `List<T>`, a class token, or an array factory |
| `value instanceof List<String>` where `value` is `Object` | Language and erasure | Cannot test type argument as desired | `instanceof List<?>`, then validate elements |
| `static T cache` inside `class Box<T>` | Language | Error because class's `T` cannot be used in static context | Instance field or separate static method type parameter |
| Passing `String` to a method declared `<T extends Number>` | API signature | Compilation error from the bound chosen by the API | Supply a `Number` or use an API with a different contract |
| `new ArrayList<String>().add(null)` | API contract | Allowed for `ArrayList` | Specify your own null policy if needed |
| `List.of("A", (String) null)` | API contract | `NullPointerException` | Do not pass null or choose a suitable API |
| `List.of("A").add("B")` | API contract | `UnsupportedOperationException` | Create a mutable collection if adding is needed |
| `Arrays.asList("A","B").set(0,"X")` | API contract | Succeeds | Overwrites elements but cannot resize |
| `Arrays.asList("A","B").add("C")` | API contract | `UnsupportedOperationException` | Use `new ArrayList<>(...)` |
| Writing wrong type through `Collections.checkedList` via raw alias | API-provided runtime guard | `ClassCastException` at the write site | Avoid raw aliases; preserve proper typing |
| `List<String> names = raw;` | Language/generic conversion | May compile with `unchecked warning` | Validate data and restrict raw types |

**Do not diagnose by exception name alone:** a `NullPointerException` can also come from an ordinary programming bug rather than an API forbidding null; a `ClassCastException` can stem from an ordinary cast, heap pollution, or a type-checking wrapper. Always examine both **contract preconditions** and **the throw site**.

## 2. Language rules apply regardless of external APIs

**Language limits** are constraints of the Java compiler/JLS and do not change when switching from `ArrayList` to `LinkedList` or an internal company library. Use **compile-time symptoms** to identify them:

| Case | Why is it a language rule? | Alternative |
|---|---|---|
| `List<int>` | Standard generic type arguments must be reference types | `List<Integer>`, `int[]`, `IntStream` |
| `List<String>` → `List<Object>` | Generic type arguments are invariant | Use `List<?>` to observe, PECS wildcards for read/write |
| `new T[10]` | Java forbids creating generic arrays with non-reifiable components | `List<T>`, `IntFunction<T[]>`, suitable token/factory |
| `obj instanceof List<String>` with `obj: Object` | Runtime cannot verify erased type arguments | `instanceof List<?>`, inspect elements |
| `static T last;` inside `class Box<T>` | Class type variable cannot be used directly in static context | Instance field or static `<U>` method |

Small snippet (placed in a method with suitable imports):

```java
List<String> names = new ArrayList<>();
List<?> view = names;
Object first = view.isEmpty() ? null : view.get(0);
```

`List<?>` is **not** `List<Object>`: it lets you view a list of unknown type argument without allowing arbitrary non-null additions. Likewise, `String.class` is a real class token while `List<String>.class` does not exist; a `List.class` token does not deeply validate element types.

Key triage point: if *no `List` implementation whatsoever* makes `List<int>` compile, you are facing a language rule. Conversely, the same `List<String>` type can succeed on `add`, throw `UnsupportedOperationException`, or reject `null` depending on the API. **Do not confuse type-checker rules with runtime behavior governed by an implementation or factory.**

## 3. API signature constraints: checked by the compiler, chosen by the API author

This category is easily mistaken for "Java generics forbids type X". Consider two methods written by an API author:

```java
// Two independent methods that can coexist in the same class.
static <T> T first(java.util.List<T> items) {
    return items.get(0);
}

static <T extends Number> double twice(T number) {
    return number.doubleValue() * 2;
}
```

`first` accepts `List<T>` for any suitable reference type `T`. `twice` constrains `T extends Number`; the compiler accepts only values whose inferred type satisfies that bound.

```java
record Ticket(int id) {}

Ticket ticket = first(java.util.List.of(new Ticket(7))); // Valid
double value = twice(3); // Valid, 3 is boxed to Integer
// twice("3"); // DOES NOT COMPILE
```

Key points:

- **Language rules** allow defining generic methods with or without upper bounds.
- **The API author** chose the `Number` bound in order to call `doubleValue()`; the compiler then enforces that bound using Java's rules.
- The error on `twice("3")` does **not** mean Java forbids using `String` with all generic methods. `first(List<String>)` remains valid.

In the Java standard library, signatures such as `Collections.max(Collection<? extends T>)`, `Comparator<? super T>`, `Function<? super T, ? extends R>`, or `Stream<T>` reflect **contract choices and type relationships needed by those specific operations**. They obey the JLS, yet do not become a rule that every generic API must carry those exact wildcards or bounds.

### API signatures and runtime behavior are two separate layers

A method taking `List<String>` is not necessarily **allowed to mutate** that list. The signature `List<String>` states **the element type at compile time**; it does not state whether the list is mutable, allows null, or has a capacity limit.

Similarly, `List<? extends Number>` allows reading values as `Number`, yet rejects ordinary `add(Integer)` calls because the captured wildcard type is unknown. That is a compile-time restriction of the parameterized type **chosen by the API**; if the runtime list is also unmodifiable, an independent runtime restriction applies too.

## 4. Same type `List<String>`, three implementations with different behaviors

This is the clearest counterexample to the misconception "one generic type always implies the same mutability":

```java
java.util.List<String> mutable = new java.util.ArrayList<>();
java.util.List<String> fixed = java.util.Arrays.asList("A", "B");
java.util.List<String> immutable = java.util.List.of("A", "B");
```

All three variables have static type `List<String>`, so the compiler knows elements are `String` and exposes `get`, `set`, and `add` from the `List` interface. Yet their implementations and contracts differ:

| Behavior | `ArrayList` | `Arrays.asList` | `List.of` |
| --- | --- | --- | --- |
| `get(index)` | Yes | Yes | Yes |
| `set(index, value)` | Yes | Yes | Unsupported |
| `add(value)` changing size | Yes | Unsupported | Unsupported |
| `remove(...)` changing size | Yes | Unsupported | Unsupported |
| Can contain `null` | Yes | Yes if source array/elements contain null | No |
| Runtime exception on unsupported operations? | Possible for invalid preconditions like index | `UnsupportedOperationException` on add/remove | `UnsupportedOperationException` on modification |
| Separate copy of input array? | Depends on constructor | Fixed-size view backed by the provided array | Factory creating an unmodifiable list by contract |

`Arrays.asList` does not return a standard `java.util.ArrayList`: it returns a fixed-size list backed by an array. Thus `set` is supported, whereas structural add/remove operations are not.

`List.of` is a factory producing an **unmodifiable list** disallowing null. Do not assume "unmodifiable" means every element object is immutable: if an element itself is mutable, its internal state can still be modified from elsewhere.

### Why does the compiler accept `add` while runtime rejects it?

Because `List<E>`'s signature declares `boolean add(E e)`; the compiler checks the parameter type `E = String` and call validity at the language level. From the variable type `List<String>` alone, it does not know that **the actual object** at runtime is an unmodifiable implementation.

```java
java.util.List<String> list = java.util.List.of("An");

// Compiler allows writing the call because List<String> has add(String):
// list.add("Binh"); // Runtime: UnsupportedOperationException
```

Commented lines do not belong in a safely runnable snippet; the demo program catches the exception to demonstrate it cleanly.

## 5. Is `null` forbidden by Java Generics?

**No.** `List<String>` does not mean "a list accepting only non-null `String`s". `String` is a reference type; `null` is assignable to reference types under Java's language rules unless an API or external analysis tool enforces a stricter policy.

The following two snippets share the type argument `String`, yet behave differently:

```java
java.util.List<String> a = new java.util.ArrayList<>();
a.add(null); // Valid and supported by ArrayList

// java.util.List<String> b = java.util.List.of((String) null);
// Runtime: NullPointerException
```

`List.of` is designed to reject null elements; `ArrayList` accepts them. The accurate answer is not "generics forbid null", but **the `List.of` API factory enforces a specific null policy**.

Further comparison:

- `List.copyOf(collection)` produces an unmodifiable list by contract and **rejects null elements**.
- `Arrays.asList` allows a null element because its backing list can hold null.
- `Objects.requireNonNull(value)` can be used in any custom API to enforce a non-null policy without changing generic type arguments.

If a codebase uses nullness annotations or static analyzers outside `javac`, they may add project-level static warnings or checks. Those are **supplementary rule sets**, not a property inherent to standard Java's `List<String>`.

## 6. Unmodifiable views vs copies: this limit is also an API contract

Same static type `List<String>`:

```java
java.util.List<String> source =
        new java.util.ArrayList<>(java.util.List.of("one"));

java.util.List<String> view =
        java.util.Collections.unmodifiableList(source);

java.util.List<String> snapshot =
        java.util.List.copyOf(source);

source.add("two");
System.out.println(view);     // [one, two]
System.out.println(snapshot); // [one]
```

**`Collections.unmodifiableList(source)`** creates a *view that forbids modification through the view*. Callers cannot invoke `view.add("x")`, yet because the view still looks at `source`, changes to `source` appear when reading `view`.

**`List.copyOf(source)`** returns an unmodifiable result and, for the mutable `source` here, acts as an independent **structural** snapshot at copy time. After `source.add("two")`, `snapshot` does not show the new element.

Keep two nuances in mind:

1. **`List.copyOf` does not guarantee allocating a new object on every call:** if the source is already a suitable unmodifiable list, the implementation may reuse the object. Do not use `a != b` as the definition of copying.
2. Both views and snapshots are **shallow** in that they do not clone the internal state of mutable element objects. An unmodifiable list does not mean an immutable object graph.

This is a difference in **API contract and data ownership**, not a difference between `List<String>` and some other kind of generics.

## 7. `Collections.checkedList`: an API adding runtime type checks

Java Generics primarily enforces types at compile time. When interacting with raw types or legacy code, `Collections.checkedList` can wrap a list to check each element's class **when elements are added through the wrapper**:

```java
java.util.List<String> checked =
        java.util.Collections.checkedList(
                new java.util.ArrayList<>(), String.class);

checked.add("ok");

java.util.List raw = checked;
// raw.add(42); // Emits unchecked warning; wrapper throws ClassCastException
```

Differences:

- **Language rule:** `List<String>.add(Integer)` is rejected by the compiler in normal typed code; raw aliases can bypass part of checking with a warning.
- **`checkedList` contract:** the wrapper uses `String.class` to validate elements whenever code operates **through that wrapper**, including calls via a raw alias, and rejects `Integer`.
- **API limit:** the wrapper does not automatically scan preexisting elements prior to wrapping, nor can it prevent another retained alias to the underlying list from mutating the backing list directly.

`checkedList` also does not turn `List<String>` into a reified generic type in the JVM. It enforces **a library-implemented runtime guard** at the operations controlled by the wrapper.

If a system receives untrusted `Object` data, validate each value before treating it as `String` — do not simply cast `(List<String>) input` and trust an erased generic argument.

## 8. Runnable Java 17+ example: seeing all three limit layers

Save the code to **`LanguageVsApiDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public class LanguageVsApiDemo {
    record Ticket(int id) {}

    static <T> T first(List<T> list) {
        return list.get(0);
    }

    // The Number bound is a signature choice of this API.
    static <T extends Number> double twice(T value) {
        return value.doubleValue() * 2;
    }

    public static void main(String[] args) {
        List<String> mutable = new ArrayList<>();
        mutable.add("An");
        mutable.add(null);
        System.out.println("ArrayList allows null: " + mutable);

        List<String> fixed = Arrays.asList("A", "B");
        fixed.set(0, "X");
        System.out.println("Arrays.asList allows set: " + fixed);
        try {
            fixed.add("C");
        } catch (UnsupportedOperationException ex) {
            System.out.println(
                    "Arrays.asList add: UnsupportedOperationException");
        }

        List<String> immutable = List.of("A", "B");
        try {
            immutable.set(0, "X");
        } catch (UnsupportedOperationException ex) {
            System.out.println(
                    "List.of set: UnsupportedOperationException");
        }
        try {
            List.of("A", (String) null);
        } catch (NullPointerException ex) {
            System.out.println("List.of null: NullPointerException");
        }

        List<String> source = new ArrayList<>(List.of("one"));
        List<String> view = Collections.unmodifiableList(source);
        List<String> copy = List.copyOf(source);
        source.add("two");

        System.out.println("Unmodifiable view: " + view);
        System.out.println("List.copyOf snapshot: " + copy);

        List<?> unknown = source;
        System.out.println("Wildcard can read: " + unknown.get(0));

        List<String> checked = Collections.checkedList(
                new ArrayList<>(), String.class);
        checked.add("safe");

        List raw = checked;
        try {
            raw.add(42); // Intentionally illustrates an unchecked call
        } catch (ClassCastException ex) {
            System.out.println(
                    "CheckedList raw add: ClassCastException");
        }

        System.out.println("Generic first accepts Ticket: "
                + first(List.of(new Ticket(7))).id());
        System.out.println("Bounded method accepts Integer: "
                + twice(3));
    }
}
```

Compile and run with JDK 17+:

```bash
javac -encoding UTF-8 -Xlint:rawtypes -Xlint:unchecked LanguageVsApiDemo.java
java LanguageVsApiDemo
```

Standard output (excluding compiler warnings):

```text
ArrayList allows null: [An, null]
Arrays.asList allows set: [X, B]
Arrays.asList add: UnsupportedOperationException
List.of set: UnsupportedOperationException
List.of null: NullPointerException
Unmodifiable view: [one, two]
List.copyOf snapshot: [one]
Wildcard can read: one
CheckedList raw add: ClassCastException
Generic first accepts Ticket: 7
Bounded method accepts Integer: 6.0
```

Layer-by-layer interpretation:

1. `mutable.add(null)` is accepted by **the language** and supported by **the `ArrayList` API**.
2. `fixed.set(0, "X")` succeeds because `Arrays.asList` supports replacing element values; `fixed.add` fails because the list is fixed-size under **its API contract**.
3. `List.of` rejects both `set` and `null` values, yet there is no generic syntax error when writing those calls.
4. `view` reflects changes to `source`, whereas `copy` produces a result isolated from later additions to the mutable source.
5. `List<?> unknown` is accepted by the compiler to read any element as `Object`, illustrating generic wildcard rules **in the language**.
6. Raw alias `List raw` can invoke `add(42)` with an **unchecked warning**; `checkedList` uses the API's runtime guard to throw `ClassCastException`.
7. `first` accepts the `Ticket` record because the method author left `T` unbounded; `twice` requires `Number` because the author chose that bound in its signature.

This standalone program intentionally creates a raw alias to contrast `checkedList`'s runtime mechanism; do not use raw types as an implementation pattern in application code.

## 9. A `List<String>` type does not describe full behavior

We can split the type information and behavior of a `List<String>`:

**What the static type tells you:** elements are treated as `String` in normal typed operations; the compiler rejects `add(Integer)`; `get(i)` has type `String`; methods declared by the `List` interface may be called under language rules.

**What the static type does not tell you automatically:** whether the implementation is mutable; whether `add` is supported; whether `null` is allowed; whether the list is thread-safe; whether capacity is bounded; whether it is a live view reflecting source mutations; whether it is a snapshot; or algorithmic complexity of operations.

Therefore, the signature `List<String>` does not guarantee that the following method can always append an element:

```java
static void appendName(List<String> names) {
    names.add("new");
}
```

This method **compiles**, yet if the caller passes `List.of("A")` or `Arrays.asList("A")`, runtime can throw `UnsupportedOperationException`.

The API author must **document the requirement** (e.g., "parameter must be a mutable list supporting structural modification"), or design it without mutating the parameter:

```java
static List<String> appendedCopy(List<String> names, String next) {
    List<String> result = new java.util.ArrayList<>(names);
    result.add(next);
    return result;
}
```

The second version returns a new list and does not require a modifiable input; yet you still must consider null policy, size, concurrent mutations on the source, and domain requirements. It is an **API contract choice**, not an automatic consequence of generics.

## 10. When does an API signature fail at compile time?

Not every compile-time error is purely "an invariant language restriction applying to every API". If a method itself declares a bound:

```java
static <T extends Comparable<? super T>> T greatest(
        java.util.List<T> items) {
    T best = items.get(0);
    for (T next : items) {
        if (next.compareTo(best) > 0) {
            best = next;
        }
    }
    return best;
}
```

Here the API chooses to require `T` to be comparable via `Comparable<? super T>`. Passing a list of a type that does not satisfy the bound produces a compiler error. Yet you can certainly write another method needing no comparison:

```java
static <T> int count(java.util.List<T> items) {
    return items.size();
}
```

`count` accepts a wider range of `T` types because its algorithm needs no ordering relation. **The API author chooses the operational requirements**, and the compiler enforces those requirements using the language's generic type-checking rules.

Similarly, `List.of`, `Arrays.asList`, and `Collections.unmodifiableList` share generic signatures across many element types while having **different mutation contracts**. A general generic signature does not imply every method on the interface is supported at runtime.

## 11. Interface return types and design-by-contract principles

When a method returns `List<T>`, it may return an `ArrayList<T>`, `List.of(...)`, a view, or another implementation, as long as it satisfies the signature constraints and documented API contract.

For example:

```java
static List<String> names() {
    return List.of("An", "Binh");
}
```

Callers can read, iterate, search, and check size; yet they must not assume `names().add("C")` always succeeds.

API author choices:

- **If returning unmodifiable state:** return `List.copyOf(source)` and document null policy, shallow copy semantics, and concurrency handling.
- **If callers should mutate an independent list:** return `new ArrayList<>(source)` and document ownership clearly.
- **If returning a live view:** return `Collections.unmodifiableList(source)`, explicitly stating that changes to `source` remain visible through the view.
- **If the API is read-only:** accept `Collection<? extends T>` or `Iterable<T>` as needed, instead of forcing callers to supply a mutable `List`.

These choices do not alter Java's type erasure or invariance. They define the **semantic contract** that users must read in Javadoc and verify with tests.

## 12. Diagnosing errors accurately

### Case A — `javac` reports missing type or incompatible type argument

Examples:

```java
// List<int> values;              // Invalid type argument
// List<Object> o = List.<String>of("A"); // Generic invariance
```

Here you must consult the JLS, generic rules, wildcards, and static types. No mutable API makes `List<int>` valid syntax.

### Case B — `javac` reports an unsatisfied bound

Example:

```java
static <T extends Number> T same(T value) {
    return value;
}

// same("Java"); // Error: cannot infer T compatible with Number
```

Read **the chosen API's signature** and check whether you are calling the right method. Another generic API without that bound could accept `String`.

### Case C — Compiles cleanly, yet throws `UnsupportedOperationException`

Example:

```java
List<String> names = List.of("A");
// names.add("B"); // Runtime error even though type is valid
```

Inspect the implementation and mutation contract. Convert with `new ArrayList<>(names)` if a mutable list is genuinely needed; do not cast `(ArrayList<String>) names` expecting the object to change type.

### Case D — Compiles cleanly, yet throws `NullPointerException` in a factory

Example:

```java
// List.of("A", (String) null); // Runtime NPE
```

Read the API's null policy; do not blame generics for forbidding null. If null is valid in domain data, pick an appropriate collection/factory or filter data before calling.

### Case E — Unchecked warnings and `ClassCastException`

For example, a raw alias bypassing compile-time generic checking. This can cause heap pollution and runtime errors when reading, or be caught immediately on insertion by `Collections.checkedList`.

Resolution: restrict raw types, fix callers to use generic APIs, validate data from untrusted sources, and never apply `@SuppressWarnings` to claim safety without proof.

## 13. Self-check exercises

**Question 1.** Why does `List<int>` fail to compile while `List<Integer>` succeeds?

Because standard Java generic type arguments require reference types; `int` is a primitive, whereas `Integer` is a wrapper reference type. This is a language rule.

**Question 2.** Where does `List<String> x = List.of("A"); x.add("B");` fail?

The call is type-valid at compile time; at runtime, the implementation returned by `List.of` rejects structural modification, typically throwing `UnsupportedOperationException`. This is an API contract.

**Question 3.** Why does the generics system not forbid `new ArrayList<String>().add(null)`?

Because type argument `String` does not mean "non-null"; `ArrayList` permits null elements. Another API such as `List.of` can impose a stricter policy.

**Question 4.** `static <T extends Number> void f(T x)` rejects `f("abc")`. Does that mean Java forbids `String` in all generic methods?

No. The `Number` bound is a signature choice made by `f` itself. Java simply enforces that bound when type-checking the call.

**Question 5.** Two variables both have type `List<String>`; one comes from `Arrays.asList` and the other from `new ArrayList<>()`. Why does `add` behave differently?

Because resizability is part of the implementation's contract, not guaranteed by the `String` type argument or the `List` interface type alone.

**Question 6.** Does `Collections.unmodifiableList(source)` create a completely independent snapshot?

No. It creates an unmodifiable view, so mutations through the backing `source` can show up in the view. For a mutable source, `List.copyOf(source)` is better when a structural snapshot is desired.

**Question 7.** How does `Collections.checkedList` help with raw aliases?

It checks the runtime class of elements added through the wrapper and can throw `ClassCastException` at the write site. It does not replace all compile-time generic rules or validate elements already present beforehand.

**Question 8.** If an API only accepts `List<? extends Number>`, what should you do when you have a `List<String>`?

Check the goal and API signature: if the operation requires `Number`, passing `List<String>` violates the contract. Do not use an unchecked cast to bypass it; provide appropriate data or find an API suited to your feature.

**Question 9.** If the compiler allows `list.add("x")` on a `List<String>` variable, can you conclude no runtime exception will occur?

No. The API may reject modification, reject null (when the argument is null), reject based on state, or enforce other documented preconditions.

## 14. Checklist when designing and using generic APIs

Before editing code, answer each question:

1. **Does `javac` reject the code?** If so, check JLS type-checking rules and the exact method signature; a compiler error may come from an API-chosen bound.
2. **Is there a runtime exception?** Identify which method throws it, which concrete implementation is used, and which precondition was violated.
3. **What does the static type tell you?** `List<String>` describes elements at compile time; it does not automatically tell you mutability, nullability, or thread safety.
4. **What non-type constraints does the API impose?** Fixed-size, unmodifiable, view, snapshot, null policy, ordering, comparator, capacity, ownership?
5. **Are there unchecked or raw types?** If so, check for heap pollution and paths carrying mismatched element types.
6. **Where does the right fix belong?** Change generic types/design when language rules require it; switch methods/APIs when bounds mismatch; change collections or initialization when runtime contracts mismatch.
7. **Can the API stay more general?** If only reading data, consider `List<?>`, `Collection<? extends T>`, or `Iterable<?>` instead of forcing callers to pass a mutable `List`.
8. **Is a defensive copy needed?** Distinguish unmodifiable views from snapshots and alias ownership.
9. **Have empty, null, and mutation cases been tested?** Those cases often expose API differences far more clearly than the choice of `T`.
10. **Are you relying on documentation or only type names?** Read Javadoc and method contracts: the compiler cannot prove every runtime rule of an implementation.

## 15. Conclusion

**Java language limits** dictate which generic code can be written and how types are checked — such as invariance, type erasure, disallowing `List<int>`, `new T[]`, or class `T` in static contexts. **API signature limits** determine which type arguments, bounds, and wildcards a specific operation accepts. **Runtime API/implementation behavior** determines whether a collection supports adding/removing, allows null, acts as a live view or snapshot, or checks element types on writes.

Consequently, two values sharing the type `List<String>` **do not necessarily share the same mutability or null policy**. When encountering errors, classify the layer first: **language → API signature → runtime contract**. Classifying accurately addresses the real cause, preserves type safety, and avoids casts or raw-type workarounds that fail later.