# Risks of Writing Through a Supertype Array Reference in Java Generic Varargs

## 1. The Problem to Identify

A method accepting varargs can be called with multiple arguments such as:

```java
static void print(String... values) {
    for (String value : values) {
        System.out.println(value);
    }
}
```

This is an illustrative method snippet; it needs to be placed inside a class to run. Mechanically, `String...` is a parameter of array type `String[]`, and the call `print("A", "B")` can be compiled by creating an array holding the two strings.

The danger becomes clearer when the varargs element type is a **non-reifiable generic type**, for example:

```java
static void process(java.util.List<String>... lists) {
    // ...
}
```

Inside the method, `lists` is seen as `List<String>[]`, yet at runtime there is **no** separate component class for `List<String>`. The array used to pass the arguments has a runtime component type corresponding to raw `List`.

If code lets a supertype reference, such as `Object[]`, point to that same array and then **writes** into the array:

```java
Object[] alias = lists;
alias[0] = java.util.List.of(123);
```

Java accepts the write because a `List<Integer>` object is still a `List` when checking the runtime component type. However, another place reading `lists[0]` as `List<String>` can throw `ClassCastException` when retrieving an `Integer` as a `String`.

**Core conclusion:**

> With generic varargs, assigning the array to a supertype reference like `Object[]` can open a path to **writing elements with the wrong generic type arguments** directly into the varargs array. The runtime array store check only knows the raw component type, whereas the compiler assumed the elements obey the generic contract. This mismatch between the contract and actual data is *heap pollution*.

Not every assignment to `Object[]` is dangerous. The specific risk arises when there is an unsafe write operation or when the alias is exposed to code that can perform such a write.

## 2. Three Mechanisms That Make Writing Through a Supertype Reference Dangerous

| Mechanism | Key Rule | Consequence in This Lesson |
| --- | --- | --- |
| **Varargs uses an array** | `List<String>...` has source parameter type `List<String>[]`. | The array has slots that can be replaced via indexed assignment. |
| **Array covariance** | A reference array such as `List[]` can be viewed through `Object[]`. | A broader alias allows writing code like `alias[0] = newValue`. |
| **Generic erasure** | The runtime component type is `List`, not a `List<String>` specialization. | The JVM cannot automatically check the `String` type argument when a slot is replaced. |

The combination of all three is the heart of the issue: `Object[]` creates no copy, so writing through the alias modifies **the exact slot of the varargs array**. Writing a `String` into a runtime `List[]` still causes the JVM to throw `ArrayStoreException`; yet a `List<Integer>` is a valid `List` at runtime and slips through. The bug surfaces only when callers use that list under the `List<String>` contract, typically at a read expecting `String`.

Specifically, `new List<String>[2]` is forbidden because its component is non-reifiable, whereas `List<String>...` is permitted in declarations with corresponding unchecked warnings. This lesson focuses on **writes through an alias**; it does not treat every alias or every varargs usage as automatically causing heap pollution.

## 3. A Baseline Example: Array Covariance with `String[]`

Before looking at generic varargs, let's run an ordinary array example to see when the JVM can block an invalid write.

File **`CovariantArrayDemo.java`**:

```java
public class CovariantArrayDemo {
    public static void main(String[] args) {
        String[] strings = {"Java", "Generics"};
        Object[] alias = strings;

        System.out.println(strings.getClass()
                .getComponentType().getName());

        try {
            alias[0] = Integer.valueOf(42);
        } catch (ArrayStoreException ex) {
            System.out.println("ArrayStoreException");
        }

        System.out.println(strings[0]);
        System.out.println(alias == strings);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac CovariantArrayDemo.java
java CovariantArrayDemo
```

Stdout:

```text
java.lang.String
ArrayStoreException
Java
true
```

Reasons:

1. The array object has runtime component type `String`.
2. `Object[] alias = strings` creates **another reference to the same object**, without copying the array.
3. `alias[0] = Integer.valueOf(42)` satisfies the static type of `Object[]`, but violates the runtime component type of `String[]`.
4. The JVM throws `ArrayStoreException` immediately on write; index 0 of the array still holds `"Java"`.
5. `alias == strings` is `true`, underscoring that this is an alias, not a copy.

The `ArrayStoreException` mechanism demonstrates that Java arrays perform a runtime store check. However, this check is only as strong as what the **runtime component type can represent**.

## 4. Difference When Array Elements Are Generic Lists

Suppose an array has runtime component type `java.util.List`. When assigning to an array element:

- A `String` is **not** a `List`, so the JVM rejects it.
- A `List<String>` is a `List`, so it is accepted.
- A `List<Integer>` is also a `List`, so it **is still accepted**.
- The runtime does not inspect `String` or `Integer` inside each `List`.

Comparison table:

| Actual Array Object | Object Written via `Object[]` | Runtime Array Store Check | Can Generic Contract Be Broken? |
|---|---|---|---|
| `String[]` | `Integer` | Rejected with `ArrayStoreException` | Unrelated to generics |
| `List[]` | `String` | Rejected with `ArrayStoreException` | No write succeeded |
| `List[]` | `List<String>` | Accepted | Consistent if slot expects `List<String>` |
| `List[]` | `List<Integer>` | Accepted | Yes, if slot is treated as `List<String>` |
| `Object[]` | `List<Integer>` | Accepted | Depends on external data contract for the array |

The crucial point is that **a `List[]` array does not know the generic argument of a stored `List` object**. That the runtime array type can reject a non-`List` object does not mean it verifies `List<String>`.

## 5. Main Program: Heap Pollution via an `Object[]` Alias

Create the file **`UnsafeGenericVarargsDemo.java`**:

```java
import java.util.List;

public class UnsafeGenericVarargsDemo {

    static void corrupt(List<String>... groups) {
        System.out.println(groups.length);

        Object[] alias = groups;
        alias[0] = List.of(42);

        System.out.println(groups[0].size());

        String word = groups[0].get(0);
        System.out.println(word);
    }

    public static void main(String[] args) {
        try {
            corrupt(List.of("safe"));
        } catch (ClassCastException ex) {
            System.out.println("ClassCastException");
        }
    }
}
```

Compile and run:

```bash
javac UnsafeGenericVarargsDemo.java
java UnsafeGenericVarargsDemo
```

Program **stdout**:

```text
1
1
ClassCastException
```

`javac` may print a note/warning about unsafe generic varargs operations during compilation. **Compiler diagnostics are not part of program stdout**. To view the warnings clearly, run:

```bash
javac -Xlint:unchecked -Xlint:varargs UnsafeGenericVarargsDemo.java
```

### Line-by-Line Explanation

1. `corrupt(List.of("safe"))` passes a list of strings. The method declares `List<String>... groups`.
2. Varargs is passed using an array. With generic argument `<String>`, the runtime array component is only `List`.
3. `Object[] alias = groups` is valid because arrays are covariant.
4. `alias[0] = List.of(42)` puts a `List<Integer>` into the array; the runtime `List` component accepts it, so **no** `ArrayStoreException` is thrown.
5. `groups[0].size()` works: the element count is 1, and `size()` does not require retrieving `Integer` as `String`.
6. `String word = groups[0].get(0)` is where the compiler expects a `String` result. The actual value is an `Integer`, causing `ClassCastException`.
7. The `catch` block prints the exception name.

This is **heap pollution**: a reference typed with a parameterized type (`List<String>[]`) points to runtime state containing a list that violates that contract.

This example is **intentionally unsafe for learning**. Do not use the `corrupt` method body in production code, and do not put `@SafeVarargs` on it.

## 6. Why Is `alias[0] = List.of(42)` Valid in Source Code?

Distinguish three static types:

```java
List<String>[] groups; // An array viewed with a generic component type.
Object[] alias;         // A supertype array reference.
List<Integer> wrong;    // A list with Integer elements.
```

These are illustrative declarations; `groups` and `alias` must be properly initialized before use in a complete method.

In source code, `groups[0]` has type `List<String>`; the compiler rejects assigning a `List<Integer>` directly:

```java
// Intentionally invalid if placed in a method with initialized variables:
groups[0] = List.of(42);
```

However, if the code creates an alias:

```java
Object[] alias = groups;
alias[0] = List.of(42);
```

then the static type of `alias[0]` is `Object`. `List<Integer>` is an object, so the compiler **has no basis from the type `Object[]` to reject it**. The write delegates verification to the runtime array store check.

The problem is that the runtime only knows the array has raw component class `List`, so it lets `List<Integer>` pass. The `<String>` information is not recovered at write time.

**It is not that the compiler "forgot to check" `groups[0]`.** We replaced the compiler's view with a supertype reference and routed the write through a path no longer tied to the generic component type.

## 7. An Alias Is Not a Copy: Why Mutations Are Visible Through All References

The statement:

```java
Object[] alias = groups;
```

does not create a new array. Both `alias` and `groups` point to the same array element storage. Therefore:

- `alias[0] = ...` changes the value that `groups[0]` will read.
- `groups[0] = ...` also changes the value that `alias[0]` reads.
- Reassigning `alias = new Object[1]` changes only the `alias` reference, **not** the array that `groups` points to.

This distinction matters for every API that receives or returns an array. A method might not write to the array itself, yet if it **exposes the alias externally** to untrusted code, external code can mutate it and introduce the same risk.

For example, `return groups;`, storing `groups` in a mutable field, or passing `groups` to a callback that retains `Object[]` all require analysis. Not every operation automatically causes heap pollution; the risk factor is the ability to **modify array contents through an alias that does not enforce the generic contract**.

## 8. Distinguishing `ArrayStoreException` from `ClassCastException`

These two exceptions can appear at different times:

**`ArrayStoreException`:**

- Typically occurs when storing an object incompatible with the **array's runtime component type**.
- In the `String[]` example, writing an `Integer` through `Object[]` is blocked immediately by the JVM.
- In a `List`-component array, writing a `String` (which is not a `List`) is also blocked immediately.

**`ClassCastException`:**

- Can occur **later**, when some code consumes data as a narrower type that the runtime object does not satisfy.
- In the generic varargs example, reading `List<String>.get(0)` and receiving an actual `Integer` causes the failure.
- Heap pollution already happened at the write line; the exception is a symptom detected at a later usage line.

Hence, "the write threw no exception" **does not prove** that the write preserved generic type safety.

## 9. Testing a Wildcard Array That Can Be Created Directly

Java forbids `new List<String>[n]`, yet allows creating an array whose component is an unbounded wildcard:

```java
List<?>[] groups = new List<?>[2];
```

`List<?>` is a reifiable type under the unbounded wildcard rule. Any slot can hold any list, whether that list holds strings, numbers, or another type.

File **`WildcardArrayDemo.java`**:

```java
import java.util.List;

public class WildcardArrayDemo {

    public static void main(String[] args) {
        List<?>[] groups = new List<?>[2];

        groups[0] = List.of("A", "B");
        groups[1] = List.of(10, 20);

        System.out.println(groups.getClass()
                .getComponentType().getName());
        System.out.println(groups[0].get(0));
        System.out.println(groups[1].get(1));

        Object[] alias = groups;
        try {
            alias[0] = "not a list";
        } catch (ArrayStoreException ex) {
            System.out.println("ArrayStoreException");
        }
    }
}
```

Compile/run:

```bash
javac WildcardArrayDemo.java
java WildcardArrayDemo
```

Stdout:

```text
java.util.List
A
20
ArrayStoreException
```

This example illustrates a point **distinct from heap pollution**: `List<?>[]` does not promise every slot contains `List<String>`. Placing a `List<Integer>` into a slot is valid under the contract because each list's type argument is unknown. If the application requires all groups to be `List<String>`, `List<?>[]` does not meet that goal.

Never use `List<?>[]` and then perform an unchecked cast to `List<String>[]` just to recreate a dangerous pattern like section 5.

## 10. Not Every Read of Generic Varargs Is Dangerous

A method can simply read elements from generic varargs and place them into a new structure:

```java
static <T> void printCount(java.util.List<T>... groups) {
    for (java.util.List<T> group : groups) {
        System.out.println(group.size());
    }
}
```

This snippet must be placed in a class; it does not include `main`. Iterating and calling `size()` **does not create heap pollution**, because there is no assignment of a wrong-type list into the array and no exposure of the array for external writes.

Nevertheless, declaring generic varargs with a non-reifiable component can still trigger compiler warnings. The warning reminds both author and caller that the method uses an array structure that does not carry full type arguments at runtime.

To deem an implementation safe, you must inspect the entire method body, any objects to which it passes the array, and how it uses the data. "Seeing no direct assignment" is a good sign, yet **insufficient** if the method lets an array alias escape to somewhere mutable.

## 11. Safe Generic Varargs Example: Iterate and Copy Data

Create the file **`SafeVarargsMergeDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class SafeVarargsMergeDemo {

    @SafeVarargs
    static <T> List<T> merge(List<? extends T>... groups) {
        List<T> output = new ArrayList<>();

        for (List<? extends T> group : groups) {
            output.addAll(group);
        }

        return List.copyOf(output);
    }

    public static void main(String[] args) {
        List<String> words = merge(
                List.of("red"), List.of("blue", "green"));

        List<Number> numbers = merge(
                List.of(1, 2), List.of(3.5));

        System.out.println(words);
        System.out.println(numbers);
    }
}
```

Compile/run with Java 17 or later:

```bash
javac SafeVarargsMergeDemo.java
java SafeVarargsMergeDemo
```

Stdout:

```text
[red, blue, green]
[1, 2, 3.5]
```

### Why Is `@SafeVarargs` Justified for This Method?

- It only **iterates** over the slots of the varargs array.
- It never replaces an array slot with a list having a different generic argument.
- It never returns the array itself or stores it in a field that other code could access and mutate.
- Data is copied into a new `ArrayList<T>` under the generic contract.
- The return type is `List<T>`, not `List<T>[]`, and `List.copyOf` converts it into a list that cannot be mutated through standard APIs.

`@SafeVarargs` is an **author's commitment** about how the implementation uses its varargs parameter; the compiler does not automatically prove every execution path safe solely from the annotation.

`List.copyOf` rejects `null` elements. In the example, the inputs contain no `null`; for data permitting `null`, choose a different policy rather than assuming `copyOf` accepts it.

## 12. What Does `@SafeVarargs` Do, and What Does It Not Do?

`java.lang.SafeVarargs` is an annotation expressing that the author of a method or constructor with a non-reifiable varargs element type **commits to performing no unsafe operations** on that varargs variable.

It can reduce unchecked warnings at the varargs declaration and call sites in permitted cases.

What the annotation **does not** do:

- Does not change the runtime array component type from raw `List` to `List<String>`.
- Does not add generic-argument checks to the JVM.
- Does not stop an `Object[]` alias from writing a `List<Integer>` into the array.
- Does not automatically copy or protect the input array.
- Does not automatically detect every dangerous method body.
- Does not allow writing `new List<String>[n]` directly.

Therefore, the following is **a false promise**:

```java
// INTENTIONALLY DANGEROUS: do not apply this pattern.
@SafeVarargs
static void unsafe(java.util.List<String>... groups) {
    Object[] alias = groups;
    alias[0] = java.util.List.of(99);
}
```

Some compilers may emit additional warnings inside the method body despite the annotation; regardless of warnings, the annotation never legitimizes heap pollution.

### Permitted Targets

In Java 17, `@SafeVarargs` is allowed on constructors, `static` methods, `final` methods, and `private` instance methods according to language rules. It cannot be placed arbitrarily on an overridable `public` instance method.

Syntactic eligibility for the annotation is **different** from actual method safety. A `static` method can carry the annotation and still be dangerous if it writes wrong types or exposes the array.

## 13. A Subtle Bug: Exposing the Array Instead of Writing to It Directly

Heap pollution does not require `alias[0] = ...` inside the varargs method itself. If the method returns the array to the caller or stores it somewhere accessible, the caller can write through a broader reference.

Consider this design **to avoid**:

```java
// This snippet only illustrates the API risk and must be placed inside a class.
static <T> T[] expose(T... values) {
    return values;
}
```

When a caller receives an array whose runtime component type is not sufficiently specific, `expose` can leak the array to other code. Another piece of code with write access can introduce a type mismatch the caller never anticipated.

Distinguish the cases:

- With `String...` and callers passing ordinary strings, the runtime array can be `String[]`, so writing an `Integer` through `Object[]` is blocked.
- With `List<String>...`, the runtime array has raw component `List`, so `List<Integer>` can pass the store check.
- With unbounded `T...`, `T` erases to `Object`; the created runtime array depends on concrete types and call context. You cannot infer that all cases are safe or all cases fail from the characters `T...` alone.

**Safety rule:** Never expose a reference to a generic varargs array to code that could replace elements contrary to the contract. If you need to retain data, copy it into a generic collection with a clear contract or create an appropriate copy for the API.

## 14. Example Returning a New Collection Instead of the Varargs Array

File **`VarargsSnapshotDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class VarargsSnapshotDemo {

    @SafeVarargs
    static <T> List<T> snapshot(T... values) {
        List<T> result = new ArrayList<>();

        for (T value : values) {
            result.add(value);
        }

        return List.copyOf(result);
    }

    public static void main(String[] args) {
        List<String> words = snapshot("a", "b");
        List<Integer> numbers = snapshot(1, 2, 3);

        System.out.println(words);
        System.out.println(numbers);
    }
}
```

Compile/run:

```bash
javac VarargsSnapshotDemo.java
java VarargsSnapshotDemo
```

Stdout:

```text
[a, b]
[1, 2, 3]
```

In this example, `snapshot` gives callers no direct access to the varargs array. It creates a new `ArrayList<T>` and returns an unmodifiable collection snapshot.

This is a strong pattern when the business logic **needs a collection of values** rather than the original array object. Note the *shallow copy* behavior: if elements are mutable objects, copying the list does not deep-copy each element's internal state.

## 15. Varargs Forwarding: Aliases Can Appear Through Another Method

Suppose a method receives `List<String>...` and passes the whole array to another method under a broader type:

```java
static void acceptsObjects(Object[] values) {
    // Could write into values.
}

static void forward(java.util.List<String>... groups) {
    acceptsObjects(groups);
}
```

This is a structural illustration, not a standalone program. Passing `groups` to `acceptsObjects(Object[])` does not cause heap pollution by itself. Yet if the receiving method later writes `List<Integer>` into a slot, it causes the exact same issue even though the write is not inside `forward`.

Accordingly, when auditing `@SafeVarargs`, do not look solely for direct assignments. Trace everywhere the varargs array:

- is passed to a helper;
- is stored in a field or callback;
- is returned or exposed via a getter;
- is wrapped in a view or array-backed container that outside code can mutate.

The goal is to know whether any external code could use a broader alias to overwrite a slot with an object carrying the wrong generic argument.

## 16. Do Not Confuse Modifying List Contents with Modifying a Varargs Array Slot

Compare two actions:

```java
// Inside a method receiving List<String>... groups:

groups[0] = java.util.List.of("new");  // Replace slot with a List<String>.
groups[0].add("x");                    // Attempt to modify the list's contents.
```

These lines are illustrative; calling `add` can throw `UnsupportedOperationException` if the concrete list is unmodifiable, such as `List.of`.

**Replacing an array slot** and **mutating the list object inside the slot** are two different operations:

- `groups[0] = someList` replaces a reference inside the varargs array.
- `groups[0].add(...)` mutates the list object that the slot points to, without changing the slot's reference.
- If the list is mutable, calling `add("x")` through `List<String>` in typed code is valid; the compiler still checks the `String` argument.
- However, if the list is passed to a raw/unchecked helper, the list's own contents can also suffer heap pollution through a separate mechanism.

Warnings about generic varargs and array aliasing focus on the risk that the runtime array component type does not fully reflect generic arguments. That can combine with other raw-collection hazards, so analyze each access path separately.

## 17. `List<String>[]` Can Be Declared, Not Directly Allocated with `new`

Some developers see a method like:

```java
static void use(java.util.List<String>... groups) { }
```

and assume they can declare and allocate arrays freely:

```java
// INTENTIONALLY INVALID:
java.util.List<String>[] arr = new java.util.List<String>[2];
```

The two cases follow different rules:

- **The declared type** `List<String>[]` can validly appear in parameters or variables.
- **The array creation expression** `new List<String>[2]` is forbidden because component type `List<String>` is non-reifiable.
- Generic varargs has special syntax and rules: the compiler can create an array at the call site according to erasure and emit unchecked warnings.
- A call passing an existing array instead of separate arguments also involves *fixed-arity* vs. *variable-arity invocation* rules; do not equate every varargs call with always allocating a new array.

**The existence of generic varargs is not an exception allowing you to write generic array creation expressions directly.**

## 18. Varargs and Different Ways of Calling

The method:

```java
static void printAll(String... values) {
    System.out.println(values.length);
}
```

can be invoked as:

```java
printAll("A", "B");
printAll(new String[] {"A", "B"});
```

In the first call, the compiler uses the varargs mechanism to pass two elements. In the second call, the caller passes a `String[]` array directly as the single parameter matching the signature.

With generic varargs, an array created elsewhere can also be passed in, so **the trustworthiness of that array's origin** must still be evaluated. If the array suffered heap pollution before being passed, even a read-only method can receive contract-violating data.

Takeaway for API authors: it is not enough to check whether the method itself "dirties" the array; understand how trustworthy the array parameter is and how it is used across different call paths.

## 19. Ways to Avoid Generic Varargs When Unnecessary

If the problem only requires processing multiple lists, you can switch the API to a nested collection:

```java
static void printCounts(
        java.util.Collection<? extends java.util.List<String>> groups) {
    for (java.util.List<String> group : groups) {
        System.out.println(group.size());
    }
}
```

This snippet must sit inside a class. Callers can invoke:

```java
printCounts(java.util.List.of(
        java.util.List.of("A", "B"),
        java.util.List.of("C")));
```

No varargs array with a non-reifiable `List<String>` component is created for that call. The compiler still verifies that inner lists have type argument `String` when used through the typed API.

### Complete Example: Merging Groups Without Varargs

File **`CollectionAlternativeDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

public class CollectionAlternativeDemo {

    static <T> List<T> merge(
            Collection<? extends List<? extends T>> groups) {
        List<T> output = new ArrayList<>();

        for (List<? extends T> group : groups) {
            output.addAll(group);
        }

        return List.copyOf(output);
    }

    public static void main(String[] args) {
        List<String> words = merge(List.of(
                List.of("A"), List.of("B", "C")));

        System.out.println(words);
    }
}
```

Compile/run:

```bash
javac CollectionAlternativeDemo.java
java CollectionAlternativeDemo
```

Stdout:

```text
[A, B, C]
```

Instead of a varargs array, the API accepts a collection of lists. It can accept various appropriately typed collection sources without exposing a generic array at the parameter boundary.

In exchange, callers must construct the outer collection of groups. If an API needs the convenience of `merge(list1, list2)` and the method has been proven safe, generic varargs combined with `@SafeVarargs` can be completely reasonable.

## 20. PECS and Generic Varargs: Safely Widening Inputs

In the safe example:

```java
@SafeVarargs
static <T> java.util.List<T> merge(
        java.util.List<? extends T>... groups) {
    // ...
}
```

The parameter `List<? extends T>` expresses that each group is a producer supplying elements readable as `T`. This applies **Producer Extends** from PECS.

However, a bounded wildcard **does not make the varargs array reifiable**. It relaxes element type constraints for each list at compile time, while the generic varargs array remains risky if the method uses an alias that can write wrong types into a slot.

Distinguish:

- `? extends T` governs how **each list is used** in source code.
- `Object[] alias` opens a path to **replace an entire list object** in the array if the code performs writes.
- `@SafeVarargs` is only justified when the method design and helpers introduce no unsafe array writes or array exposure.

You cannot replace an aliasing audit merely by adding a wildcard.

## 21. Spotting Bugs in Code Review

Review a generic varargs method in order:

1. **Identify the varargs element type:** `String` is reifiable; `List<String>` is non-reifiable; an unbounded `T` typically erases to `Object`.
2. **Find where the array is viewed as a supertype:** `Object[]`, raw `List[]`, or a helper accepting a compatible array.
3. **Find every write to a slot:** `array[i] = ...`, `System.arraycopy`, `Arrays.fill`, array-mutating helpers, and mutating callbacks.
4. **Find where the reference escapes:** returning the array, storing it in a field, returning an array-backed view, writing to shared state.
5. **Compare the runtime component type with written data:** `List<Integer>` is still a raw `List`.
6. **Evaluate read calls:** casts when reading under `List<String>` can throw late exceptions.
7. **Check annotations:** if `@SafeVarargs` is present, verify it reflects the actual implementation rather than merely hiding warnings.
8. **Choose a fix:** read and copy only; never expose the array; or switch the API to `Collection`/`List`.

### Suspicious Code Pattern

```java
// Analysis snippet, not a safe API.
static void mutate(java.util.List<String>... groups) {
    Object[] values = groups;
    values[0] = java.util.List.of(123);
}
```

This pattern exhibits all three signals: generic varargs with a non-reifiable component, a supertype alias, and writing a list with a different generic argument.

### Lower-Risk Code Pattern

```java
@SafeVarargs
static <T> int count(
        java.util.List<? extends T>... groups) {
    int total = 0;
    for (java.util.List<? extends T> group : groups) {
        total += group.size();
    }
    return total;
}
```

This snippet must live inside a class. It only reads `size()` and never exposes the array; this is a much more appropriate case for an author to consider `@SafeVarargs`.

## 22. Common Misconceptions

**Misconception 1 — "Every `Object[]` alias is dangerous."** No. Creating an alias does not corrupt data by itself; risk arises when the alias is used to write or handed to code that can write mismatched types.

**Misconception 2 — "Array store checks will always block `List<Integer>` from entering `List<String>[]`."** No. The runtime component is typically just raw `List`, so both list types pass the check.

**Misconception 3 — "`ClassCastException` happens right at `alias[0] = List.of(42)`."** Not in our main example. The write succeeds; the error occurs later when the `Integer` element is used as `String`.

**Misconception 4 — "Having `@SafeVarargs` means the JVM reified the generic type."** No. The annotation changes neither type erasure nor the runtime component type.

**Misconception 5 — "`List<String>...` cannot be declared."** It can be declared, though the compiler emits warnings and enforces rules to highlight non-reifiable risks.

**Misconception 6 — "`List<?>[]` cannot be created with `new`."** You can create `new List<?>[n]` because unbounded wildcards are reifiable under Java's rules.

**Misconception 7 — "`List<?>[]` is equivalent to `List<String>[]`."** No. The former allows different generic arguments in each list; the latter expects every element to be `List<String>`.

**Misconception 8 — "Using `? extends T` is enough for safety even when writing through `Object[]`."** No. The wildcard governs compile-time operations on `List`; it does not stop an array alias from replacing an entire slot.

**Misconception 9 — "A method that only forwards varargs to a helper is guaranteed safe."** No. If the helper retains or writes into the array, the hazard remains.

**Misconception 10 — "Heap pollution only happens with varargs."** No. Raw types, unchecked casts, and other API paths can also produce data incompatible with a parameterized type.

**Misconception 11 — "Warnings should only be handled with `@SuppressWarnings`."** No. You need to understand the data flow and fix the design; suppression should only cover a proven, tightly scoped boundary.

**Misconception 12 — "Switching `List<String>...` to `Collection<List<String>>` makes generics reified."** No. It removes the specific array-aliasing risk when an array isn't needed, while Generics remain checked primarily at compile time.

## 23. Exercises and Answers

**Exercise 1 — Predict the Exception**

```java
String[] arr = new String[1];
Object[] alias = arr;
alias[0] = 123;
```

When the last line executes, which exception is thrown?

**Answer:** `ArrayStoreException`, because the runtime component type is `String`.

**Exercise 2 — Generic List Array**

```java
List<?>[] arr = new List<?>[1];
Object[] alias = arr;
alias[0] = List.of(123);
```

Does the last line throw `ArrayStoreException`?

**Answer:** No. The runtime component is `List` and `List.of(123)` returns an object implementing `List`. `List<?>[]` does not promise that elements are string lists.

**Exercise 3 — Heap Pollution**

Suppose a `List<String>[]` exists via unchecked conversion or varargs and its runtime component is `List`. Can `Object[] alias = array; alias[0] = List.of(123);` succeed?

**Answer:** Yes; the runtime array only checks raw `List`. If read later as `String`, `ClassCastException` can occur.

**Exercise 4 — Alias or Copy**

```java
Object[] alias = groups;
```

Does this copy the array?

**Answer:** No. It creates another reference pointing to the same array object.

**Exercise 5 — Annotation**

Should `@SafeVarargs` be placed on a method that deliberately writes `List<Integer>` into a `List<String>...` array?

**Answer:** No. The annotation is a safety commitment, not a self-defense mechanism.

**Exercise 6 — Alternative API**

A method only needs to iterate over string groups and print their sizes. What parameter type can avoid generic arrays?

**Answer:** `Collection<? extends List<String>>` fits many cases, or `List<List<String>>` if indexing and ordering are needed.

**Exercise 7 — Safe Usage**

A varargs method only loops over groups to build a new `ArrayList<T>` and returns `List.copyOf`, never writing to or exposing the varargs array. Is it a reasonable candidate for `@SafeVarargs`?

**Answer:** Yes, provided the method satisfies annotation placement constraints and all call paths and helpers are genuinely safe.

**Exercise 8 — Runtime Component**

When `void f(List<String>... lists)` is invoked as varargs, what component class does the runtime array have?

**Answer:** Corresponding to raw `java.util.List`, not a specialized `List<String>` class.

**Exercise 9 — Writing a List vs. Modifying List Elements**

Do `groups[0] = List.of("A")` and `groups[0].add("A")` mean the same thing?

**Answer:** No. The first replaces the reference in slot 0; the second modifies the contents of the list object currently in that slot (and may be disallowed if the list is unmodifiable).

**Exercise 10 — Late Detection**

Why can `groups[0].size()` still run after a slot is replaced with `List<Integer>`, whereas `String s = groups[0].get(0)` fails?

**Answer:** `size()` does not require elements to be `String`, whereas `get(0)` is used in a context requiring `String`, forcing a runtime cast that checks the actual value.

## 24. Fix Workflow and Tool-Based Verification

When receiving a generic varargs warning:

1. Compile with `javac -Xlint:unchecked -Xlint:varargs` to pinpoint warning locations and call paths.
2. Check whether the varargs element type is non-reifiable.
3. Search for aliases to `Object[]` or broader array types.
4. Verify there are no mismatched writes into array slots, including via helpers.
5. Verify the array does not escape to places that could write wrong types.
6. If you simply need to process a set of groups, consider `Collection<? extends List<T>>`.
7. If varargs is genuinely the best API, keep the method body read/copy-only and consider `@SafeVarargs` on an eligible target.
8. Write tests covering both valid inputs and controlled heap-pollution scenarios.
9. Avoid asserting that "the compiler didn't warn" means contents are actually safe.
10. Distinguish `ArrayStoreException` at assignment from `ClassCastException` at data consumption.

### Inspecting Descriptors with `javap`

On the compiled `UnsafeGenericVarargsDemo` class:

```bash
javap -p -s UnsafeGenericVarargsDemo
```

At the JVM type-descriptor level, `corrupt(List<String>...)` has one parameter, an array of raw `List`, with the typical descriptor:

```text
([Ljava/util/List;)V
```

`[` denotes an array, `L...;` is a reference type, and `V` is `void`. The descriptor carries no `<String>`.

To look more closely at element assignments and casts:

```bash
javap -p -c UnsafeGenericVarargsDemo
```

Look for `aastore` for array element stores, `invokeinterface`/`invokevirtual` for method calls, and `checkcast` to `String` when the result of `get()` is received as `String`.

For a classfile produced by `javac`, `javap -v` can also display a `Signature` attribute preserving the generic declaration. That serves metadata purposes and **does not make the array store check verify `<String>` at runtime**.

## 25. Summary

The risk of **writing through a supertype array reference** stems from the combination of:

1. **Generic varargs** with a non-reifiable element type like `List<String>`.
2. **Array covariance** allowing an `Object[]` reference to point to the varargs array.
3. **Type erasure** leaving the runtime array component as raw `List`.
4. **An unsafe write** replacing a slot with `List<Integer>`, which the JVM cannot distinguish by generic argument.
5. **A subsequent read/cast** still trusting the `List<String>` contract, potentially throwing `ClassCastException`.

A `String[]` normally catches an invalid object write at store time with `ArrayStoreException`, whereas a `List<String>` varargs array may not catch a generic-argument mismatch until read time.

To avoid the issue, **do not write through broader aliases, do not expose the varargs array to code that might write mismatched types, and prefer read/copy-only designs**. Use `@SafeVarargs` when the method body truly satisfies the safety commitment; if an array is unnecessary, consider shifting the API to an appropriate generic `Collection`/`List`.

### Authoritative References

- [Java Language Specification §8.4.1 — Formal Parameters](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.1): declaring variable-arity parameters.
- [Java Language Specification §15.12.4.2 — Evaluate Arguments](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.4.2): argument evaluation and creating varargs arrays when needed.
- [Java Language Specification §4.7 — Reifiable Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.7): types with full runtime representation.
- [Java Language Specification §4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6): erasure of generic types.
- [Java Language Specification §10.5 — Array Store Exception](https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html#jls-10.5): checks when writing into arrays.
- [Java Language Specification §9.6.4.7 — `@SafeVarargs`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.7): the annotation and its usage rules.
- [Java SE 17 `java.util.List`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html): generic list methods used in the examples.
