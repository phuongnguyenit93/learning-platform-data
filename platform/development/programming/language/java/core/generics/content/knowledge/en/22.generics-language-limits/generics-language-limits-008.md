# Overload, `instanceof`, and Array Creation Limits Related to Type Erasure in Java Generics

## Learning objectives

Java Generics provides compile-time type checking, yet most information about *type arguments* (such as `String` in `List<String>`) does not exist as a separate kind of runtime class. This mechanism is called **type erasure**. It delivers compatibility with pre-generics Java libraries while creating important language limits.

The three groups that cause the most confusion are:

1. **Overloading:** you cannot define two overloads differing only in `List<String>` vs `List<Integer>` because their signatures collide after erasure.
2. **`instanceof`:** you cannot inspect an `Object` with `instanceof List<String>` to ask whether it is "truly" a list containing only Strings; runtime can only verify the container type at the appropriate level.
3. **Array creation:** you cannot write `new List<String>[n]` or `new T[n]` in a generic method, because arrays require a real component type that the JVM can check.

This lesson progresses from language rules to **compilable/runnable Java 17+ examples**, verified compiler errors, alternative API designs, and self-check exercises.

## 1. Foundation: what does type erasure remove?

Consider:

```java
List<String> names = new ArrayList<>();
List<Integer> numbers = new ArrayList<>();
```

In source code, the two references have distinct parameterized types:

- `names.add("An")` is valid, whereas `names.add(123)` is rejected by the compiler.
- `numbers.add(123)` is valid, whereas `numbers.add("An")` is rejected by the compiler.
- `names.get(0)` is seen by the compiler as `String`.
- `numbers.get(0)` is seen by the compiler as `Integer`.

At runtime, however, there is no `ArrayList<String>` class distinct from `ArrayList<Integer>`. Regular instances share the `java.util.ArrayList` class and `java.util.List` interface; `getClass()` does not represent each instance's type argument.

Erasure follows basic rules:

| Source type declaration | Erasure | Notes |
| --- | --- | --- |
| `List<String>` | `List` | Drops the `String` argument information. |
| `List<Integer>` | `List` | Same erasure as `List<String>`. |
| `Map<String, Integer>` | `Map` | Neither type argument exists in the runtime class. |
| Unbounded `T` | `Object` | Implicit bound is `Object`. |
| `T extends Number` | `Number` | Type variable erasure comes from the first bound. |
| `T extends Number & Comparable<T>` | `Number` | Uses the erasure of the leftmost bound. |
| `String` | `String` | Contains no type argument to erase. |
| `String[]` | `String[]` | Component type `String` exists at runtime. |

This is a helpful simplification for understanding the mechanism; class files can still store generic metadata in the `Signature` attribute for reflection and analysis tools. That metadata **does not turn** a `List<String>` into a distinct runtime class that `instanceof` or array store checks can fully verify.

An intuitive example:

```java
// Code placed inside a method with List and ArrayList imported:
boolean same = new ArrayList<String>().getClass()
        == new ArrayList<Integer>().getClass();
// same == true
```

Because both objects share the same runtime class, operations relying directly on class descriptors cannot automatically distinguish `String` from `Integer` type arguments.

## 2. First limit: no overloading solely by generic type argument

### 2.1. Situation rejected by the compiler

Suppose you want the same method name to handle two kinds of lists:

```java
import java.util.List;

class OverloadErasureClash {
    static void process(List<String> data) {}
    static void process(List<Integer> data) {}
}
```

**`OverloadErasureClash.java` intentionally does not compile.** Verify with:

```bash
javac --release 17 OverloadErasureClash.java
```

Verified key diagnostic:

```text
name clash: process(List<Integer>) and process(List<String>)
have the same erasure
```

In source code, `List<String>` and `List<Integer>` are different types. Yet the erased parameter signature of both methods is `process(List)`. Java does not allow keeping them as two overloads differing only in generic arguments.

To be precise, distinguish:

- **Java method signature:** name, formal parameter list, and type-parameter elements according to JLS rules.
- **Signature erasure:** replacing generic types in parameters with their erasures.
- **JVM method descriptor:** includes the return type in bytecode, though that does not allow Java overloading solely by return type.

Do not conclude "generics are erased" means everything in a method is erased: method names and parameter types that do not depend on type arguments still distinguish methods.

### 2.2. Rename by intent when contracts genuinely differ

A clear solution:

```java
static void logStrings(List<String> values) {
    System.out.println("strings=" + values);
}

static void logIntegers(List<Integer> values) {
    System.out.println("integers=" + values);
}
```

These are two illustrative methods placed in a class importing `List`, also appearing in the complete program in Section 6.

Advantage: method names tell callers which business operation applies. Merely tweaking a few characters to "work around" erasure is not always good; use meaningful names when two operations differ.

### 2.3. If the algorithm is identical, usually use one generic method

If both list types need the same behavior, such as simply counting elements, do not write two overloads:

```java
static <E> int count(List<E> values) {
    return values.size();
}
```

Both `count(List<String>)` and `count(List<Integer>)` are valid at call sites. Inside the method, the algorithm does not need to know whether `E` is `String` or `Integer`.

If the method only inspects the `List` without using `E` elsewhere, consider a simpler signature:

```java
static int countUnknown(List<?> values) {
    return values.size();
}
```

Use a named type variable only when linking types across parameters, return values, or multiple positions; use a wildcard when the concrete element type does not matter to the contract.

### 2.4. Another parameter can create a genuine overload

The following overloads differ in actual parameters that do not erase identically:

```java
static void process(List<String> data, int mode) {}
static void process(List<Integer> data, String description) {}
```

Their erasures are `process(List, int)` and `process(List, String)`, so they can coexist when placed in a valid class. However, the extra parameter should make design sense. Avoid adding dummy parameters merely to force overload resolution.

You can choose domain-specific method names instead of creating confusing parameter pairs for callers.

### 2.5. Bounded type variables can also clash

Not every erasure of `T` is `Object`. With `T extends Number`, the erasure of `T` is `Number`:

**File `OverloadBoundClash.java` — does not compile:**

```java
class OverloadBoundClash {
    <T extends Number> void take(T n) {}
    void take(Number n) {}
}
```

Check:

```bash
javac --release 17 OverloadBoundClash.java
```

The compiler reports something like:

```text
name clash: take(Number) and <T>take(T) have the same erasure
```

The solution is not casting `T` to `Object` hoping the two methods differ. You need a different method name, distinct runtime parameter types, or unified logic in a single appropriate method.

### 2.6. Do not confuse overloading with overriding

The **override** relationship across an inheritance hierarchy has additional **subsignature** rules to preserve compatibility when a legacy library method is generified. Thus, a subclass method can sometimes use an erased signature and still override a superclass generic method.

This **does not** permit two overloads `process(List<String>)` and `process(List<Integer>)` in the same class. When resolving a `name clash`, identify whether you are looking at **two overloaded methods** or **two methods in an inheritance relationship**.

## 3. Second limit: `instanceof` does not deeply inspect type arguments

### 3.1. Checking whether a container is a `List`

Suppose a value arrives from an API with unknown type:

```java
Object input = List.of("A", 42);
boolean listLike = input instanceof List<?>;
System.out.println(listLike);
```

Output:

```text
true
```

`instanceof List<?>` only asks whether the value is a `List` of unknown element type. The runtime can determine that from the object's class/interface. It does not need and **does not attempt** to prove every element is a `String`.

The result remains `true` even when the `List` contains an `Integer`, because `List<?>` makes no commitment to a concrete element type.

### 3.2. Why is `Object instanceof List<String>` rejected?

**File `InstanceofParameterized.java` — intentionally does not compile:**

```java
import java.util.List;

class InstanceofParameterized {
    static boolean check(Object value) {
        return value instanceof List<String>;
    }
}
```

Try:

```bash
javac --release 17 InstanceofParameterized.java
```

In the verified environment, the compiler reports:

```text
Object cannot be safely cast to List<String>
```

Reason: the operand has static type `Object`, yet `List<String>` is non-reifiable, so the runtime cannot perform a check distinguishing Lists whose type argument is `String`.

**Beware absolute claims:** in Java 17, certain `instanceof` checks using a parameterized type like `List<String>` are permitted by the compiler **if the operand's static type is already specific enough for the corresponding cast to be valid**. The following example compiled with `--release 17`:

```java
static boolean redundantCheck(List<String> value) {
    return value instanceof List<String>;
}
```

This is not a new runtime capability to check every element: the static type is already `List<String>`, and the test does not detect a List suffering from heap pollution. Therefore the practical rule is **never use `instanceof List<String>` to validate untrusted data**; use `List<?>` and validate each element instead. Claiming "`instanceof List<String>` never compiles in any context" is inaccurate for Java 17.

### 3.3. `instanceof T` when `T` is a type variable

**File `InstanceofTypeVariable.java` — intentionally does not compile:**

```java
class InstanceofTypeVariable {
    static <T> boolean check(Object value) {
        return value instanceof T;
    }
}
```

With `javac --release 17`, the output looks like:

```text
Object cannot be safely cast to T
```

`T` is a compile-time type variable and does not automatically supply a runtime class token per call. Do not use `T.class` or `instanceof T` to try to access the actual class.

If you need to check a concrete class at runtime, pass a token from the caller:

```java
static <T> boolean isType(Object value, Class<T> token) {
    return token.isInstance(value);
}
```

`isType("A", String.class)` returns `true`; `isType(1, String.class)` returns `false`. However, `List.class` only checks the `List` container type and cannot replace a `List<String>.class` token because no such class literal exists.

### 3.4. How to verify a `List` genuinely contains Strings

One approach:

```java
static boolean allStrings(Object value) {
    if (!(value instanceof List<?> list)) {
        return false;
    }
    for (Object element : list) {
        if (!(element instanceof String)) {
            return false;
        }
    }
    return true;
}
```

Place the method in a class importing `java.util.List`, as in the complete program in Section 6. The method first checks the container and then iterates over every element.

This contract intentionally treats `null` as invalid (since `null instanceof String` is false). For an empty list, it returns `true` meaning "no violating element exists". If domain rules require at least one `String`, add `!list.isEmpty()`.

Note on **time of check**: if another caller can mutate the list after validation, `allStrings` does not guarantee the list stays valid forever. To establish a trust boundary, validate and copy into a new collection, avoiding shared mutable aliases.

### 3.5. Reflection can inspect declarations but cannot prove data integrity

Java reflection provides `Field.getGenericType()`, `Method.getGenericReturnType()`, `ParameterizedType`, and similar APIs to read generic type metadata from class files. Yet `List<String>` metadata on a field only describes **the declared type**; it does not ensure every element placed into the List passes a `String` check at runtime.

If an `Integer` was inserted into a `List` via a raw alias, reading declaration metadata still reports `List<String>`; the actual data remains invalid. When handling untrusted data, validate elements or use a contract-enforcing deserialization/conversion step.

## 4. Third limit: creating generic arrays

### 4.1. Why do arrays need a runtime element type?

Java arrays are *reified*: an array object retains its actual component type at runtime. Given:

```java
String[] strings = new String[2];
Object[] alias = strings;
alias[0] = "OK"; // Valid.
// alias[1] = 42; // ArrayStoreException at runtime.
```

The JVM knows the real array is `String[]`, so it blocks storing an `Integer` even though `alias` has static type `Object[]`. This is a runtime safeguard specific to reference arrays.

However, `List<String>` has no dedicated runtime class distinct from `List<Integer>`, so there is no reified "List of String" component type for an array to deeply enforce.

### 4.2. Two prohibited array creations

**File `GenericArrayCreation.java` — intentionally does not compile:**

```java
import java.util.List;

class GenericArrayCreation {
    List<String>[] items = new List<String>[2];

    static <T> T[] create(int n) {
        return new T[n];
    }
}
```

Compile:

```bash
javac --release 17 GenericArrayCreation.java
```

The compiler was verified to reject both lines with:

```text
error: generic array creation
```

Here:

- `new List<String>[2]` is forbidden because `List<String>` is non-reifiable.
- `new T[n]` is forbidden because `T` is a type variable that provides no runtime class for the element type to allocate.

This cannot be fixed with `@SuppressWarnings("unchecked")`: it is a compile-time error in the array creation expression, not merely a warning.

### 4.3. Arrays that can be created

| Expression | Valid? | Reason |
| --- | --- | --- |
| `new String[3]` | Yes | Component type `String` is reifiable. |
| `new int[3]` | Yes | Primitive array has runtime component type `int`. |
| `new List[3]` | Yes | Raw `List` is reifiable, though it loses generic checking when used. |
| `new List<?>[3]` | Yes | Unbounded wildcard; `List<?>` is reifiable. |
| `new List<String>[3]` | No | Generic argument `String` is not reified in the `List` component. |
| `new List<? extends Number>[3]` | No | This parameterized type is not reifiable without unbounded wildcards everywhere. |
| `new T[3]` in a generic method | No | Type variable lacks a concrete class token. |
| `new String[2][]` | Yes | First-dimension array has two slots, each initially null with type `String[]`. |

Even though `List<?>[]` is valid, each slot of the array could hold a `List<String>` or a `List<Integer>`. Runtime checks only verify that stored objects are `List` instances, not each `List`'s element type.

### 4.4. Risks of working around it with unsafe casts

A risky pattern:

```java
// DO NOT USE:
@SuppressWarnings("unchecked")
static <T> T[] fake(int n) {
    return (T[]) new Object[n];
}
```

The real array is `Object[]`. Casting inside the generic method does not turn it into `String[]` when the caller expects `String`. At the assignment site:

```java
// When calling the fake method above:
String[] values = fake(3);
```

the runtime can throw `ClassCastException` because `Object[]` is not `String[]`. Type erasure does not mean arrays lose their runtime component type.

Another workaround creates `new List<?>[n]` and casts it to `List<String>[]`. That cast does not verify `String` inside each `List`, permitting heap pollution if an `Object[]` alias stores a `List<Integer>` into a slot. Never build APIs around such casts.

### 4.5. Creating arrays with a factory or `Class` token

**Using `Class<T>`:**

```java
@SuppressWarnings("unchecked")
static <T> T[] newReferenceArray(Class<T> component, int length) {
    if (component.isPrimitive()) {
        throw new IllegalArgumentException("reference type required");
    }
    return (T[]) java.lang.reflect.Array.newInstance(component, length);
}
```

The caller passes `String.class`, `Integer.class`, etc. `Array.newInstance` actually allocates an array with the matching runtime component type. This helper explicitly rejects primitive tokens because `int[]` is not equivalent to `Integer[]`.

The cast from `Object` to `T[]` is justified in this isolated spot because the input component token is used directly to instantiate the real array. Do not apply this reasoning to casting an arbitrary `Object[]` to `T[]`.

**Using an array factory:**

```java
static <T> T[] copyArray(
        Collection<? extends T> source,
        java.util.function.IntFunction<T[]> arrayFactory) {
    return source.toArray(arrayFactory.apply(0));
}
```

With `String[]::new`, the factory supplies the runtime component type `String`:

```java
String[] words = copyArray(List.of("C", "D"), String[]::new);
```

This helper belongs in a class importing `Collection` and `List`, as in the complete program. For data already in a `Collection`, the shorter form is calling `list.toArray(String[]::new)` directly.

### 4.6. When an array is not needed, use `List`

If the goal is merely storing, adding, removing, or passing elements, `List<T>` is usually preferable to `T[]`. Arrays have fixed length, require runtime component types, and have covariance leading to array store checks; `List` offers a cleaner compile-time generic contract in typical applications.

Do not treat arrays as a "faster List" without concrete API requirements or benchmark evidence.

## 5. Distinguishing `List<?>`, raw `List`, and `List<Object>`

These three types are frequently conflated when fixing erasure errors:

| Type | Meaning | Write safety? |
| --- | --- | --- |
| `List<?>` | A list with an unknown element type. | Cannot add arbitrary non-null elements; reads only as `Object`. |
| `List` | Raw type: omits generic parameters. | Compiler may allow writes with unchecked warnings; easily violates another typed reference's contract. |
| `List<Object>` | List intentionally holding `Object`. | `Object` instances can be added, yet `List<String>` is not a subtype of it. |
| `List<? extends Number>` | Elements are an unknown subtype of `Number`. | Reads as `Number`; cannot arbitrarily add `Number`. |
| `List<? super Integer>` | Container able to accept `Integer`. | `Integer` can be added; reads safely only as `Object`. |

`List<?>` is helpful in `instanceof` when simply asking whether an object is a `List`. It is also considered reifiable in Java's type rules, so `new List<?>[2]` is valid. However, the wildcard syntax **does not create a distinct `List<?>` class** and does not automatically validate elements inside each `List`.

## 6. Complete Java 17 program: the three limits and how to apply them

**File `ErasureLimitsDemo.java`:**

```java
import java.lang.reflect.Array;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.List;
import java.util.function.IntFunction;

public class ErasureLimitsDemo {
    static void logStrings(List<String> values) {
        System.out.println("strings=" + values);
    }

    static void logIntegers(List<Integer> values) {
        System.out.println("integers=" + values);
    }

    static <E> int count(List<E> values) {
        return values.size();
    }

    static boolean allStrings(Object value) {
        if (!(value instanceof List<?> list)) {
            return false;
        }
        for (Object element : list) {
            if (!(element instanceof String)) {
                return false;
            }
        }
        return true;
    }

    @SuppressWarnings("unchecked")
    static <T> T[] newReferenceArray(Class<T> component, int length) {
        if (component.isPrimitive()) {
            throw new IllegalArgumentException("reference type required");
        }
        return (T[]) Array.newInstance(component, length);
    }

    static <T> T[] copyArray(
            Collection<? extends T> source,
            IntFunction<T[]> arrayFactory) {
        return source.toArray(arrayFactory.apply(0));
    }

    static <T> T checkedCast(Class<T> type, Object value) {
        return type.cast(value);
    }

    public static void main(String[] args) {
        List<String> words = List.of("A", "B");
        List<Integer> numbers = List.of(10, 20);
        logStrings(words);
        logIntegers(numbers);
        System.out.println("count=" + count(words));
        System.out.println("sameRuntimeClass="
                + (new ArrayList<String>().getClass()
                == new ArrayList<Integer>().getClass()));

        Object mixed = List.of("A", 42);
        System.out.println("instanceofWildcard=" + (mixed instanceof List<?>));
        System.out.println("mixedAllStrings=" + allStrings(mixed));
        System.out.println("wordsAllStrings=" + allStrings(words));

        List<?>[] groups = new List<?>[2];
        groups[0] = words;
        groups[1] = numbers;
        System.out.println("groupSizes=" + groups[0].size()
                + "," + groups[1].size());

        String[] allocated = newReferenceArray(String.class, 2);
        allocated[0] = "X";
        System.out.println("allocated=" + Arrays.toString(allocated));
        try {
            Object[] alias = allocated;
            alias[1] = 42;
        } catch (ArrayStoreException error) {
            System.out.println("arrayStore=" + error.getClass().getSimpleName());
        }

        String[] copied = copyArray(List.of("C", "D"), String[]::new);
        System.out.println("copied=" + Arrays.toString(copied));
        System.out.println("cast=" + checkedCast(String.class, "OK"));
    }
}
```

**Compile and run:**

```bash
javac --release 17 -Xlint:all ErasureLimitsDemo.java
java ErasureLimitsDemo
```

**Verified stdout from this program:**

```text
strings=[A, B]
integers=[10, 20]
count=2
sameRuntimeClass=true
instanceofWildcard=true
mixedAllStrings=false
wordsAllStrings=true
groupSizes=2,2
allocated=[X, null]
arrayStore=ArrayStoreException
copied=[C, D]
cast=OK
```

In our test run, `javac --release 17 -Xlint:all` emitted zero warnings for the program above.

### 6.1. Two differently named methods instead of clashing overloads

`logStrings` and `logIntegers` can coexist because **their names differ**. `count(List<E>)` illustrates a shared algorithm when distinguishing element types is unnecessary.

### 6.2. Two `ArrayList`s share the same runtime class

The `getClass()` comparison prints `true`; generic arguments `String`/`Integer` do not create two distinct `ArrayList` classes at runtime. This explains the common root cause behind the limits in this lesson.

### 6.3. Checking the `List` container and each element are two steps

`mixed instanceof List<?>` returns `true` because `mixed` is a `List`. Yet `allStrings(mixed)` returns `false` upon encountering an `Integer`, while `allStrings(words)` returns `true`.

Do not use `instanceof List<String>` in place of actual element iteration when receiving an `Object` from outside.

### 6.4. Wildcard arrays are valid, yet do not enforce uniform element types across groups

`new List<?>[2]` allows placing a `List<String>` in the first slot and a `List<Integer>` in the second. Both satisfy the `List<?>` contract. `groupSizes=2,2` only inspects sizes and never reads `String` or `Integer` elements.

### 6.5. A real `String` array still enforces array store checks

`Array.newInstance(String.class, 2)` creates a `String[]`. When an `Object[]` alias attempts to store an `Integer`, the JVM throws `ArrayStoreException`. That is the runtime mechanism of arrays, with no contradiction to generic `List` type arguments being erased.

### 6.6. An array factory preserves the exact component type

`String[]::new` tells `copyArray` that a real `String[]` is required. After copying, the program prints `copied=[C, D]`. There is no fundamentally flawed `(String[]) new Object[n]` cast.

## 7. Summary of intentionally non-compiling examples

The files below must be saved and compiled **separately**, not merged with the valid program in Section 6.

| File | Invalid operation | Core `javac` diagnostic |
| --- | --- | --- |
| `OverloadErasureClash.java` | `process(List<String>)` with `process(List<Integer>)` | `name clash ... same erasure`. |
| `OverloadBoundClash.java` | `take(Number)` with `<T extends Number> take(T)` | `same erasure`. |
| `InstanceofParameterized.java` | `Object value instanceof List<String>` | `Object cannot be safely cast to List<String>`. |
| `InstanceofTypeVariable.java` | `Object value instanceof T` | `Object cannot be safely cast to T`. |
| `GenericArrayCreation.java` | `new List<String>[2]`, `new T[n]` | `generic array creation`. |

These compiler error cases were reproduced with `javac --release 17`. Exact wording and caret positions may vary by compiler version, but the violation categories in the table are what matter.

## 8. Common bad fixes

### Mistake 1: turning all `List` parameters into raw types to overload

You cannot create two same-named overloads taking raw `List` and still distinguish `String`/`Integer` by content; after erasure they still share the same signature. Dropping generics only loses element checking without fixing the API design.

### Mistake 2: using a cast `(List<String>) value` as validation

A generic cast cannot fully verify `List` elements at runtime. Usually the JVM only checks that the container is a `List`, while elements may still have wrong types. For untrusted data, iterate using `List<?>` and check each element; consider copying after validation to guard against future mutation via aliases.

### Mistake 3: treating `instanceof List<?>` as meaning "contains Strings"

It only confirms the object is a `List`. It returns `true` for lists of `Integer` or mixed lists as well.

### Mistake 4: assuming `T.class` or `new T[n]` can be used freely

A type variable does not provide a runtime class token on its own. Accept `Class<T>` or a factory from the caller if checking or allocating elements of a specific type is truly needed.

### Mistake 5: using `(T[]) new Object[n]`

Casting does not alter the array's runtime component type of `Object`. Callers expecting `String[]` can hit `ClassCastException` upon receiving the result.

### Mistake 6: creating `List<?>[]` and casting it to `List<String>[]`

The array only checks the `List` component; a non-reifiable cast adds no `String` enforcement on inner elements. If a `List<Integer>` is written through an `Object[]` alias, heap pollution and a delayed `ClassCastException` can follow.

### Mistake 7: adding `@SuppressWarnings("unchecked")` to "fix errors"

Annotations only silence warnings; they create no runtime proof nor alter data. Nor can they turn compiler errors like `generic array creation` into valid code.

### Mistake 8: claiming Java 17 forbids every `instanceof List<String>` expression

You must consider the operand's static type and casting conversion rules: certain cases like `List<String> x; x instanceof List<String>` can compile. Still, it is not a deep element check; avoid using it to validate `Object` values of unknown origin.

## 9. Choosing a solution by requirement

| Real requirement | Approach |
| --- | --- |
| Two distinct behaviors for `List<String>` vs `List<Integer>` | Use different method names or design parameters that genuinely differ after erasure. |
| Same algorithm for any `List` | `<E> method(List<E>)` or `method(List<?>)` when `E` does not need linking. |
| Check whether an `Object` is a `List` | `value instanceof List<?>` or `List.class.isInstance(value)`. |
| Check whether a `List` contains only `String`s | Iterate `List<?>` and check `instanceof String` on each element; control aliases if needed. |
| Check whether an `Object` is a `String` | `value instanceof String`, or `String.class.isInstance(value)`. |
| Generic method needing runtime `Class<T>` | Caller passes `Class<T>`; use `type.cast(value)` where appropriate. |
| Need `T[]` with a real runtime component type | Caller passes `Class<T>` and uses `Array.newInstance`, or passes `IntFunction<T[]>`. |
| Convert a `Collection` to a typed array | `collection.toArray(String[]::new)` or an equivalent overload. |
| Need multiple nested generic lists | Consider `List<List<T>>` instead of non-reifiable arrays. |
| Only observing multiple lists of varying types | `List<?>[]` or `List<List<?>>` depending on ownership and mutability. |

Do not pick a cast hack just to make the compiler stop complaining. Clarify whether **the limit lies in overload resolution, runtime type testing, or array component-type requirements**, and adjust the contract at the right spot.

## 10. Quick diagnostic workflow

When hitting an erasure-related error:

1. **Read the exact message:** `same erasure`, `cannot be safely cast`, or `generic array creation`?
2. **Identify compile-time vs runtime:** is this a `javac` error or a JVM runtime exception?
3. **Write out parameter erasures:** e.g., `List<String> → List`, `T extends Number → Number`.
4. **For overloading:** check whether the two parameter lists still differ after erasure; if not, redesign.
5. **For `instanceof`:** ask whether the JVM has enough info about the tested type. For `List<String>` from `Object`, test `List<?>` and iterate elements.
6. **For arrays:** ask which reifiable component type the array needs at runtime. Use a factory/token or a `List`.
7. **Evaluate untrusted data:** raw types, unchecked casts, reflection, and legacy data can bypass compile-time checks.
8. **Write boundary tests:** compile forbidden examples to observe errors; run valid cases to inspect outputs and array store checks.
9. **Never suppress warnings blindly:** warnings often pinpoint where heap pollution and delayed `ClassCastException`s originate.
10. **Keep APIs simple:** callers should see clear contracts rather than unverifiable casts.

## 11. Self-check exercises

### Question 1

Can you write both `void save(List<String> x)` and `void save(List<Integer> x)` in the same class?

**Answer:** No. Both become `save(List)` after erasure, and the compiler reports a name clash.

### Question 2

Why can `void save(List<String> x, int kind)` and `void save(List<Integer> x, String category)` coexist?

**Answer:** Erasure produces parameter lists `(List, int)` and `(List, String)`, which differ in the second parameter. Still, consider API clarity when designing.

### Question 3

Can `<T extends Number> void read(T x)` overload `void read(Number x)`?

**Answer:** Not in the same overload context; `T` erases to `Number`, resulting in the same erasure.

### Question 4

What does `Object obj = List.of(1, 2); obj instanceof List<?>` evaluate to?

**Answer:** `true`, because `obj` is a `List`; the wildcard does not require every element to be `String` or any specific type.

### Question 5

Can you use `obj instanceof List<String>` to guarantee every element is a `String` when `obj` has static type `Object`?

**Answer:** No. That test is rejected by the compiler in the `Object` case, and runtime does not reify the `String` type argument. Check `List<?>` and iterate elements.

### Question 6

Why can `List<String> list; list instanceof List<String>` compile on Java 17?

**Answer:** Because the static type is already specific enough to evaluate the check, not because the JVM can deeply inspect each element. It is unsuitable for validating untrusted data.

### Question 7

Why is `new List<String>[5]` forbidden while `new List<?>[5]` is valid?

**Answer:** `List<String>` is non-reifiable whereas `List<?>` is reifiable since all arguments are unbounded wildcards. The runtime component type of `List<?>[]` is still just `List`.

### Question 8

How do you write a generic method that allocates a real `String[]` array?

**Answer:** Pass `String.class` to a helper using `Array.newInstance`, or pass `String[]::new` to a helper accepting `IntFunction<T[]>`; do not use `new T[n]`.

### Question 9

If an `Integer` was inserted into a `List` via a raw alias, what can `String s = list.get(0)` throw?

**Answer:** It can throw `ClassCastException` at the compiler-inserted cast when the caller expects `String`. That is a runtime failure, unlike compile-time `generic array creation` errors.

### Question 10

How should you handle two overloads differing only in generic types when the algorithm is identical?

**Answer:** Merge them into one generic method like `<E> int count(List<E>)`, or accept `List<?>` if only observing. If the two behaviors genuinely differ, use method names reflecting each operation.

## 12. Takeaways

- **Erasure** strips most generic type arguments from runtime types; `List<String>` and `List<Integer>` share the same erasure `List`.
- **Overloads** must not differ solely in erased type arguments, as that causes a `name clash`.
- **`instanceof`** is not a tool to prove every element of a `List<String>` from an `Object` is a `String`; `List<?>` tests the container, while verifying contents takes an explicit step.
- **Arrays** require a reifiable component type for runtime JVM checks; `new T[n]` and `new List<String>[n]` are forbidden.
- **Class tokens/factories** supply the needed runtime component type when you truly must allocate `T[]`.
- **Raw types/unchecked casts** can bypass generic safety and cause delayed failures, not solve these limits.

To design safe and clear Java APIs, identify which parts of a type exist at compile time, which parts can be checked at runtime, and **place contracts at the right boundary** instead of trying to force the JVM to recognize type arguments that erasure does not preserve.