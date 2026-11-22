# Difference Between Declaring a Generic Array Variable and an Array Creation Expression in Java

## 1. The Question: Is "Allowed to Declare, Forbidden to `new`" a Contradiction?

One of the surprising situations when combining Java Generics with arrays is:

~~~java
import java.util.List;

class Example {
    List<String>[] values;       // VALID: variable/field declaration.

    void initialize() {
        // values = new List<String>[3]; // ERROR: generic array creation.
    }
}
~~~

Square brackets `[]` appear in both places, yet the two constructs do **two different things**:

- `List<String>[] values;` **declares a variable or field of an array type**, meaning its elements are described at compile time as `List<String>`. The statement only informs the compiler of the type; it **does not create a runtime array object**.
- `new List<String>[3]` asks the JVM to **create an array object**, which has a runtime component type. The type argument `String` in `List<String>` is not preserved in full at runtime due to type erasure, so Java forbids this form of array creation expression.

Therefore, Java can completely allow a **type in declarations** while disallowing **expressions that directly create an array of that type**. There is no contradiction: declaration rules and object creation rules serve different stages.

The main questions answered here are:

1. Why are `List<String>[]` and `T[]` valid in declarations, whereas `new List<String>[n]` and `new T[n]` fail?
2. Why is `new List<?>[n]` valid?
3. Can `new List<?>[n]` be assigned directly to `List<String>[]`?
4. If an unchecked cast is used to create a generic array, what can go wrong at runtime?
5. What safer alternatives exist, and when should you use `List<List<String>>` or accept an array from the caller?

## 2. Separating Three Concepts: Array Type, Variable, and Array Creation Expression

### 2.1. An Array Type Is a Type

`String[]` is an array type whose elements are Strings.

`List<String>[]` is an array type whose elements have the parameterized type `List<String>`.

`T[]` inside a generic class or generic method is an array type whose elements have the **type variable T**.

These types can appear in field, local variable, parameter, or return type signatures:

~~~java
import java.util.List;

class Inventory<T> {
    T[] elements;                // Valid.
    List<String>[] groups;       // Valid.

    void accept(List<T>[] input) {  // Valid at the declaration level.
        // Can process input according to the declared type.
    }

    List<T>[] expose() {         // Valid at the declaration level.
        return null;             // Illustrates the signature only.
    }
}
~~~

The snippet above **does not create** any `List<T>[]`. An unassigned instance array field defaults to `null`. The fact that a generic array signature is valid does not mean the compiler knows how to instantiate it automatically.

### 2.2. An Array Variable Does Not Necessarily Hold an Array Object

~~~java
List<String>[] declared = null; // Valid.
~~~

`declared` has static type `List<String>[]`, yet its current value is `null`. The compiler allows the declaration because it does not have to allocate a runtime array object with component type `List<String>`.

Conversely, the following statement requires creating an object:

~~~java
// List<String>[] created = new List<String>[2];
// Compile-time error: generic array creation.
~~~

### 2.3. An Array Creation Expression Must Have a Runtime Component Type

Every Java array has a **runtime component type** so the JVM can enforce element assignments. With:

~~~java
String[] strings = new String[2];
~~~

the runtime component type is `java.lang.String`. If the array is actually `String[]` and an `Integer` element is assigned through an `Object[]` alias, the JVM rejects it with `ArrayStoreException`.

With:

~~~java
// new List<String>[2]
~~~

the JVM does not possess a dedicated runtime class "List of String" to check whether a newly assigned `List<?>` element contains Strings. Therefore, Java forbids directly creating arrays with non-reifiable component types such as `List<String>`.

## 3. Reifiable Type Rules Explain the Difference

A **reifiable type** is a type that retains enough necessary information at runtime under Java's rules. Useful cases in this lesson:

- Non-generic types: `String`, `Integer`, `Runnable`.
- Raw types of generic classes/interfaces: `List`, `Map`.
- Parameterized types containing only **unbounded wildcard arguments**, such as `List<?>`, `Map<?, ?>`.
- Array types whose component type is reifiable, such as `String[]` or `List<?>[]`.

By contrast:

- `List<String>` is non-reifiable.
- `List<Integer>` is non-reifiable.
- `List<? extends Number>` is non-reifiable because the wildcard has a concrete upper bound rather than an unbounded `?`.
- `Map<String, List<Integer>>` is non-reifiable.
- An ordinary type variable `T` does not have a concrete runtime component class to use with `new T[n]`.

Comparison:

| Expression | Java 17 | Reason |
| --- | --- | --- |
| `new String[3]` | Valid | String is reifiable. |
| `new Integer[3]` | Valid | Integer is reifiable. |
| `new List[3]` | Valid, raw use | Raw List is reifiable, yet loses generic checking wherever raw types are used. |
| `new List<?>[3]` | Valid | List<?> is reifiable. |
| `new Map<?, ?>[3]` | Valid | Every type argument is an unbounded wildcard. |
| `new List<String>[3]` | Invalid | List<String> is non-reifiable. |
| `new List<Integer>[3]` | Invalid | List<Integer> is non-reifiable. |
| `new List<? extends Number>[3]` | Invalid | Type argument is not an unbounded wildcard. |
| `new Map<String, Integer>[3]` | Invalid | Map<String,Integer> is non-reifiable. |
| `new T[3]` in a generic class | Invalid | T has no concrete runtime component type for array creation. |

**Do not confuse `List<?>` with raw `List`.** `List<?>` is a valid parameterized type with a wildcard, whereas raw `List` omits type arguments altogether. Both array creation expressions `new List<?>[3]` and `new List[3]` compile, yet the static types of the results differ, which changes how subsequent code is type-checked.

## 4. Why Do Arrays Check Types at Runtime While Generics Check Primarily at Compile Time?

Java arrays are **covariant**: if `String` is a subtype of `Object`, then `String[]` is also a subtype of `Object[]`.

~~~java
String[] strings = new String[1];
Object[] alias = strings; // Valid due to array covariance.
~~~

Yet the array object still carries `String` as its runtime component type. Therefore:

~~~java
Object[] alias = new String[1];

try {
    alias[0] = Integer.valueOf(7);
} catch (ArrayStoreException error) {
    System.out.println("Rejected non-String element");
}
~~~

The JVM detects that an `Integer` object cannot reside in a `String[]` and throws `ArrayStoreException` **at assignment time**.

Generic parameterized types in Java are generally **invariant**:

~~~java
List<String> strings = new ArrayList<>();

// List<Object> objects = strings; // Does not compile.
List<?> unknown = strings;        // Valid.
~~~

This invariance lets the compiler prevent adding an `Integer` into a `List<String>` through a `List<Object>` alias. However, because of type erasure, the runtime does not generally distinguish `ArrayList<String>` and `ArrayList<Integer>` as two distinct runtime classes.

If `new List<String>[n]` were allowed, array covariance could create a path to insert a `List<Integer>` into an array supposedly holding only `List<String>`. With the runtime component type only able to check `List`, the array store check would miss the difference in type arguments. That is why **generic array creation is forbidden for non-reifiable component types**.

## 5. Thought Experiment: What If `new List<String>[]` Were Allowed?

This is **intentionally invalid code** to explain the language design:

~~~java
// DOES NOT COMPILE:
List<String>[] strings = new List<String>[1];

Object[] alias = strings;
alias[0] = List.of(123);

String value = strings[0].get(0);
~~~

Hypothetical danger points:

1. The `strings` variable promises that every array element is `List<String>`.
2. Due to array covariance, `alias` has type `Object[]` yet points to the same array.
3. If the JVM only sees runtime component type `List`, assigning `List<Integer>` through `alias` would pass the array store check.
4. Later, the compiler assumes `strings[0].get(0)` is `String`.
5. The actual value is `Integer`, resulting in `ClassCastException` at read time.

Java prevents building arrays directly with non-reifiable generic syntax from the start, thereby reducing the chance of arrays carrying false promises about type arguments.

**Note:** a program can still create a similar situation if it actively uses an **unchecked cast**. Prohibiting generic array creation cannot stop all unsafe code, especially raw types and unchecked casts.

## 6. Declaring `List<String>[]` Is Completely Valid

These declarations:

~~~java
List<String>[] a;
List<String>[] b = null;
List<Integer>[][] matrix;
~~~

are all valid when placed in an appropriate Java context with `java.util.List` imported. They only establish static types; they are not array creation.

A method can **accept** or **return** a generic array type:

~~~java
static void inspect(List<String>[] rows) {
    for (List<String> row : rows) {
        System.out.println(row.size());
    }
}

static List<String>[] identity(List<String>[] rows) {
    return rows;
}
~~~

The fact that these signatures are valid does not prove that the method can instantiate `new List<String>[n]` itself. To obtain a compatible array object, the method must **receive it from the caller**, obtain it from a valid API, or rely on a specialized creation mechanism with clear assumptions and risks.

Example with an unassigned variable:

~~~java
List<String>[] rows;
// System.out.println(rows.length); // Does not compile: local variable may not have been initialized.
~~~

Do not confuse "valid declaration" with "initialized variable ready for use." In Java, local variables must be initialized before being read.

## 7. Why Is `new List<?>[n]` Valid?

`List<?>` is a **parameterized type with an unbounded wildcard**, which Java considers reifiable. Therefore:

~~~java
List<?>[] buckets = new List<?>[3];

buckets[0] = List.of("Java");
buckets[1] = List.of(10, 20);
buckets[2] = List.of(true);
~~~

This snippet is valid: each element of the array is a `List`, yet they can have **different element types**. That matches the exact meaning of the wildcard: we do not declare a single element type.

Reading data:

~~~java
Object value = buckets[0].get(0);
System.out.println(value); // Java.
~~~

Values retrieved from `List<?>` are safe to treat as `Object`. The compiler does not allow concluding immediately that it is `String` without additional checks.

A concise initialization form:

~~~java
List<?>[] buckets = {
    List.of("Java"),
    List.of(123)
};
~~~

An array initializer like the one above can also create an array containing `List<?>` according to the declared context, not `new List<String>[]`.

### A Wildcard Array Does Not Guarantee the Type of Deeply Nested Elements

~~~java
List<?>[] buckets = new List<?>[2];
buckets[0] = List.of("A");
buckets[1] = List.of(42);
~~~

Both are valid because the array's runtime component type is `List`. Each inner `List` can carry a different element type. `List<?>[]` therefore **cannot safely substitute for `List<String>[]` when business rules require every List to contain String**.

## 8. You Cannot Directly Assign `List<?>[]` to `List<String>[]`

This is a common question after learning `new List<?>[n]`:

~~~java
// List<String>[] specific = new List<?>[3]; // Does not compile.
~~~

The compiler forbids the assignment because `List<?>[]` can contain `List<Integer>`, whereas `List<String>[]` promises that the array elements are `List<String>`. There is no safe conversion for this direct assignment.

Trying this on Java 17 produces an error along the lines of:

~~~text
incompatible types: List<?>[] cannot be converted to List<String>[]
```
~~~

Wait—let's check the exact fence in line 285-289 of `generic-arrays-004.md`!
In `generic-arrays-004.md` lines 287-289:
```
~~~text
incompatible types: List<?>[] cannot be converted to List<String>[]
~~~
```
Yes, `~~~text` closed by `~~~`. I must make sure NOT to put ` ``` ` instead of `~~~`! Good catch. Let's continue carefully.

What **can** be done—though it should not be treated as safe by default—is an unchecked cast:

~~~java
@SuppressWarnings("unchecked")
List<String>[] risky = (List<String>[]) new List<?>[3];
~~~

At runtime, the cast can succeed because the underlying array object has a runtime component corresponding to `List`. However, the cast does not check the `String` type argument of each `List`, so `risky` may carry an unproven type promise.

Snippets using such unchecked casts should only exist in a very narrow utility, with invariants clearly documented, and must guarantee there is no write path that puts elements with the wrong type arguments into the array.

## 9. Complete Java 17+ Example: Declaration, Wildcard Array, Unchecked Cast, and Runtime Error

Save the following program into **GenericArrayDemo.java**:

~~~java
import java.lang.reflect.Array;
import java.util.Arrays;
import java.util.List;

public class GenericArrayDemo {
    static <T> T[] makeArray(Class<T> componentType, int length) {
        @SuppressWarnings("unchecked")
        T[] result = (T[]) Array.newInstance(componentType, length);
        return result;
    }

    static <T> T[] copy(T[] input) {
        return Arrays.copyOf(input, input.length);
    }

    public static void main(String[] args) {
        // Valid declaration even without creating an array.
        List<String>[] declared = null;
        System.out.println("declared=" + declared);

        // Reifiable List<?> array can be created.
        List<?>[] wildcard = new List<?>[2];
        wildcard[0] = List.of("Java");
        wildcard[1] = List.of(42);
        System.out.println(
                "wildcard=" + Arrays.toString(wildcard)
        );
        System.out.println(
                "wildcardType=" +
                wildcard.getClass().getComponentType().getName()
        );

        // Create array from a runtime Class token when the component type is reifiable.
        String[] names = makeArray(String.class, 2);
        names[0] = "Java";
        names[1] = "Kotlin";
        String[] duplicate = copy(names);
        System.out.println(
                "copy=" + Arrays.toString(duplicate)
        );

        // Unchecked cast: syntactically valid, yet DOES NOT automatically guarantee
        // that every List in the array contains String.
        @SuppressWarnings("unchecked")
        List<String>[] risky = (List<String>[]) new List<?>[2];

        risky[0] = List.of("safe");
        Object[] alias = risky;

        // The runtime array only knows the component is List.
        alias[1] = List.of(42);

        System.out.println(
                "riskyClass=" +
                risky.getClass().getComponentType().getName()
        );

        try {
            String bad = risky[1].get(0);
            System.out.println(bad);
        } catch (ClassCastException exception) {
            System.out.println("polluted=ClassCastException");
        }

        // Control case: the JVM checks the String component of String[].
        Object[] actualStrings = new String[1];

        try {
            actualStrings[0] = 42;
        } catch (ArrayStoreException exception) {
            System.out.println("arrayStore=ArrayStoreException");
        }
    }
}
~~~

Compile and run with Java 17 or higher:

~~~bash
javac --release 17 -Xlint:unchecked GenericArrayDemo.java
java GenericArrayDemo
~~~

**Exact** stdout:

~~~text
declared=null
wildcard=[[Java], [42]]
wildcardType=java.util.List
copy=[Java, Kotlin]
riskyClass=java.util.List
polluted=ClassCastException
arrayStore=ArrayStoreException
~~~

### Output Explanation in Order

**`declared=null`:** the variable of type `List<String>[]` exists but does not yet reference any array object. This is a valid declaration.

**`wildcard=[[Java], [42]]`:** the array holds two Lists with different elements. The type `List<?>[]` accurately expresses this unknown element type.

**`wildcardType=java.util.List`:** the runtime component type is `List`, not `List<String>` or `List<Integer>`. This clarifies why an array store check does not verify the generic elements inside.

**`copy=[Java, Kotlin]`:** the method `makeArray(String.class,2)` creates a `String[]` via reflection; `Arrays.copyOf` uses the input's runtime array type to produce an appropriate copy.

**`riskyClass=java.util.List`:** after the unchecked cast, the array still has runtime component `List`. The cast does not turn the array into a special runtime kind holding `List<String>`.

**`polluted=ClassCastException`:** the `Object[]` alias assigns a `List<Integer>` into an array slot viewed by `risky` as `List<String>[]`. The JVM accepts it because the assigned object is a `List`. However, when reading the first element with static type `String`, the compiler/JVM check throws `ClassCastException` because the actual value is `Integer`.

**`arrayStore=ArrayStoreException`:** for an array genuinely having component `String`, the JVM immediately rejects assigning an `Integer` through an `Object[]` alias. This is the difference between the runtime array mechanism and type erasure of generic arguments.

**Educational purpose:** the unchecked-cast section is an **intentionally unsafe** example. You should not copy that pattern into production APIs without proving the component invariant, alias limits, and write sites.

## 10. Array Creation Expressions Rejected by Java: Compile-Time Checks

The following snippet **intentionally fails to compile**, kept separate from `GenericArrayDemo.java`:

~~~java
import java.util.List;

class InvalidArrays<T> {
    List<String>[] a = new List<String>[3];
    List<? extends Number>[] b =
            new List<? extends Number>[3];
    T[] c = new T[3];
    List<String>[] d = new List<?>[3];
}
~~~

Compile with Java 17:

~~~bash
javac --release 17 InvalidArrays.java
~~~

Corresponding errors:

| Line | Error category | Why |
| --- | --- | --- |
| `new List<String>[3]` | `generic array creation` | `List<String>` is non-reifiable. |
| `new List<? extends Number>[3]` | `generic array creation` | Bounded wildcard, not a reifiable unbounded wildcard. |
| `new T[3]` | `generic array creation` | `T` is a type variable, with no runtime component type. |
| `List<String>[] d = new List<?>[3]` | `incompatible types` | Cannot safely convert `List<?>[]` directly to `List<String>[]`. |

**Important:** not every appearance of a generic array type is forbidden. The **left-hand sides** `List<String>[] a` and `T[] c` are valid type declarations. The error arises in the **creation expression on the right**, or from assigning two incompatible array types.

## 11. Declaring `T[]` Is Valid, Yet `new T[n]` Is Invalid

In a generic class:

~~~java
class Buffer<T> {
    private T[] values; // Valid.

    Buffer(T[] supplied) {
        values = supplied; // Valid: accepts an array supplied by the caller.
    }

    T get(int index) {
        return values[index];
    }
}
~~~

Usage:

~~~java
Buffer<String> buffer =
        new Buffer<>(new String[] {"A", "B"});

String first = buffer.get(0); // "A".
~~~

The caller created **`String[]`** with a reifiable component type and supplied it to `Buffer<T>`. The generic class does not have to deduce `T`'s runtime class from type erasure itself.

Conversely, you cannot write:

~~~java
class BadBuffer<T> {
    // T[] values = new T[3]; // Does not compile.
}
~~~

Reason: Java cannot use a type variable `T` to directly create a runtime array with a concrete component type, even though callers might later instantiate `BadBuffer<String>` or `BadBuffer<Integer>`.

### A Type Bound Does Not Make `new T[n]` Valid Either

~~~java
class BoundedBuffer<T extends Number> {
    // T[] items = new T[3]; // Does not compile.
}
~~~

Even though `T` is erased to `Number` at compile time, `Number[]` is not equivalent to `Integer[]`, `Double[]`, or any specific `T`. If the true goal is merely to store `Number`s, consider creating `new Number[n]` with a `Number`-based design; if the API promises `T[]`, ensure the `T` component type via an appropriate mechanism.

## 12. Solutions Depend on Where Component Type Information Lives

This problem requires first distinguishing **declaring** a generic array from **allocating** it. When a real array object is needed, choose a way that carries the right runtime component type:

1. **Accept an array already created by the caller:** `static <T> T[] copy(T[] source) { return Arrays.copyOf(source, source.length); }` leverages the source's actual component class.
2. **Accept `Class<T>`:** use `Array.newInstance(componentType, length)`, isolating the cast since reflection returns `Object`. For example, `String.class` creates `String[]`, not a disguised `Object[]`.
3. **Accept a factory:** `IntFunction<T[]>` with `String[]::new` lets the caller directly decide the runtime component class.
4. **Do not force arrays:** `List<List<String>>` describes multiple string groups; `List<?>[]` only makes sense when type arguments are genuinely unknown and the API requires an array.

```java
static <T> T[] cloneOf(T[] source) {
    return java.util.Arrays.copyOf(source, source.length);
}

static <T> T[] make(int n, java.util.function.IntFunction<T[]> factory) {
    return factory.apply(n);
}
```

**Do not equate the `List.class` token with a nonexistent `List<String>.class`.** A `Class<T>` or factory can supply the runtime class of `String`, yet cannot make the type arguments of `List<String>` reifiable. The dedicated lesson on array factories covers `null` handling, factories returning the wrong length, primitive arrays, and `Collection.toArray`.

## 13. Why Should You Not Mechanically Use `(T[]) new Object[n]`?

A common trick:

~~~java
class Risky<T> {
    @SuppressWarnings("unchecked")
    T[] create(int n) {
        return (T[]) new Object[n];
    }
}
~~~

The compiler may accept it with the unchecked warning suppressed, yet the actual runtime array is always **`Object[]`**. If the caller needs `String[]`, the JVM's check/cast of the concrete result to `String[]` can fail:

~~~java
Risky<String> factory = new Risky<>();
// String[] names = factory.create(2);
// May throw ClassCastException: Object[] is not String[].
~~~

**The issue is not just element types at read time:** the array object itself carries component type `Object` instead of `String`. Because of runtime array reification, `Object[]` cannot substitute for `String[]` when the caller expects `String[]`.

Sometimes libraries use `Object[]` internally and cast at a specially designed boundary. In such cases, never casually expose an API returning `T[]` if it cannot provide the runtime component type expected by the caller. A more provable direction is storing an actual `Object[]` internally, checking individual values on read, or using a `Class<T>` token to allocate an array with the appropriate component.

## 14. How Do Generic Varargs Relate to This?

A generic varargs declaration:

~~~java
static <T> void printAll(T... values) {
    for (T value : values) {
        System.out.println(value);
    }
}
~~~

`T...` is fundamentally a parameter of array type `T[]`. Java allows that declaration, yet when a call site must construct an array holding a **non-reifiable type**, the compiler may emit an unchecked warning or `possible heap pollution from parameterized vararg type`.

Example:

~~~java
static void showAll(List<String>... groups) {
    for (List<String> group : groups) {
        System.out.println(group);
    }
}
~~~

This is a valid declaration, yet it can become a channel passing non-reifiable values through an array. Do not treat varargs syntax as a safe way to bypass generic array creation rules.

`@SafeVarargs` should only be used when the author **can genuinely prove that the method body performs no unsafe operations on the varargs array**. In Java 17, the annotation can be used on `static`/`final` methods, constructors, and `private` instance methods under the language's conditions. It **does not add runtime checks automatically** and does not legitimize operations causing heap pollution.

When an API only needs a collection of generic elements, a `List<T>` or `Collection<T>` parameter often avoids risky scenarios and warnings related to varargs arrays.

## 15. Distinguishing `ArrayStoreException` and `ClassCastException`

These two exceptions are frequently confused in generic array problems:

| Scenario | Check that fails | Exception |
| --- | --- | --- |
| Assigning `Integer` into `String[]` via `Object[]` | The array's runtime component type `String` | `ArrayStoreException` at assignment time. |
| Assigning `List<Integer>` into an array with runtime component `List` | The `List` component still matches; store is accepted | No error necessarily raised at assignment time. |
| Reading `Integer` from a `List` inside a polluted `List<String>[]` and using it as `String` | Casting the `Object` element to `String` on use | `ClassCastException` at read/use time. |
| Casting an actual `Object[]` array to `String[]` | Incompatible runtime array class | `ClassCastException` immediately at the array cast. |

Example:

~~~java
Object[] a = new String[1];
// a[0] = 5;             // At runtime: ArrayStoreException.

Object[] b = new List<?>[1];
b[0] = List.of(5);       // Valid: the object is a List.
~~~

Conclusion: **arrays check the direct element type of the array at runtime**, while generic arguments inside a collection may not be deeply checked. A cast inserted by the compiler when using a generic value can uncover a mismatch later.

## 16. Common Misconceptions

### "Being able to declare `List<String>[]` means `new List<String>[]` should also work"

False. Declaring an array type does not require creating a runtime array. `new` requires a suitable runtime component type; `List<String>` is non-reifiable.

### "`List<?>[]` can be assigned to `List<String>[]` because `?` covers `String`"

False. `List<?>` represents an unknown element type, not an assertion of `String`. Java does not allow directly assigning `List<?>[]` to `List<String>[]`.

### "An unchecked cast solves the problem for generic arrays"

False. `(List<String>[]) new List<?>[n]` does not change the runtime component into `List<String>`. It merely declares a concrete static type that the JVM cannot fully verify. Code can throw `ClassCastException` when consuming wrongly typed data.

### "If `new T[n]` is rejected, just replace it with `new Object[n]` and cast to `T[]`"

Dangerous. The actual array is `Object[]`, whereas the caller may expect `String[]`; the array cast will fail. Examine the API contract and runtime component type.

### "`new List<?>[n]` allows reading every element as `String`"

False. The wildcard permits reading a `List` with an unknown type argument, yet retrieved elements are only safe as `Object` without further verification.

### "`ArrayStoreException` and `ClassCastException` are the same thing"

False. `ArrayStoreException` checks **writes into an array**. `ClassCastException` checks **incompatible type casts**, including when using generic data expected to be `String` that is actually `Integer`.

### "Seeing a generic array in a method parameter is definitely an error"

False. `void read(List<String>[] input)` and `<T> void read(T[] input)` can be valid signatures; the issue lies in how an array with an appropriate and safe runtime representation is created or obtained.

### "Generics cannot create arrays, so Java cannot work with generic arrays at all"

False. Java can declare array types with generic elements, receive arrays from callers, return arrays under generic signatures, use reifiable wildcard arrays, or create arrays of known runtime classes with a `Class` token. What is forbidden is **certain array creation expressions with non-reifiable component types**, not all array-related operations.

## 17. Workflow for Choosing an Approach

When facing a requirement that "needs an array holding generic values," check in order:

1. **Is an array truly mandatory?** If you only want a list of `List<String>`s, `List<List<String>>` is usually safer and simpler.
2. **Is the component type reifiable?** For `String`, `Integer`, `List<?>`, or `Map<?, ?>`, direct array creation can be used.
3. **Are you only declaring a variable, parameter, or return type?** `List<String>[]` or `T[]` is valid; no array needs to be allocated on that line.
4. **Are you invoking `new ...[n]`?** The component type must obey array creation rules; you cannot use `List<String>`, `List<? extends Number>`, or a type variable `T` arbitrarily.
5. **Can the caller supply a runtime component class?** Consider `Class<T>` with `Array.newInstance`.
6. **Can you accept an array from the caller?** Take a `T[]` input and copy if needed, avoiding inventing an array with an assumed component type.
7. **Is there an unchecked cast?** Clearly identify the actual runtime array class, who can write through aliases, and what happens if data with wrong generic arguments is read.
8. **Are there non-reifiable varargs?** Inspect compiler warnings; only use `@SafeVarargs` if the method is genuinely safe.
9. **Are you relying on `ArrayStoreException` to verify generic arguments?** That is incorrect: runtime array stores only check the visible component class/interface, not elements inside collections.
10. **Test with the target compiler** (for example `javac --release 17`) to avoid confusing compile-time errors with runtime exceptions.

## 18. Self-Check Questions

**Question 1.** Why is `List<String>[] rows;` valid while `new List<String>[2]` is rejected?

**Answer:** The first line only declares the array type at compile time; the second requires creating a runtime array of the non-reifiable component `List<String>`, whose `String` generic argument cannot be checked on array store.

**Question 2.** Is `new List<?>[2]` valid? Does it allow adding `List<Integer>` to the array?

**Answer:** Yes. `List<?>` is reifiable and can hold Lists with different type arguments. Each `List` placed into the array conforms to the runtime component `List`.

**Question 3.** Can you directly assign `List<String>[] a = new List<?>[2];`?

**Answer:** No. `List<?>[]` does not guarantee that every element is `List<String>`; the compiler reports `incompatible types`.

**Question 4.** If you cast `(List<String>[]) new List<?>[2]`, is an error guaranteed to occur immediately?

**Answer:** Not necessarily. The cast may pass at runtime because the underlying array is still `List[]`, yet it requires an unchecked conversion/cast and carries heap pollution risk. An error can occur when reading non-`String` data.

**Question 5.** Is `new T[2]` in `class Buffer<T>` valid if `T extends Number`?

**Answer:** No. The bound does not provide a concrete runtime component type for `T`, such as `Integer[]` or `Double[]`.

**Question 6.** Is the method `<T> T[] copy(T[] source)` necessarily wrong?

**Answer:** No. It can accept a real array already created by the caller with the right component type; for example, `Arrays.copyOf` can create a copy matching the source's runtime array class.

**Question 7.** Why does assigning an `Integer` into `Object[] alias = new String[1]` throw `ArrayStoreException`, whereas assigning `List.of(42)` into an `Object[]` alias of `List<?>[]` can succeed?

**Answer:** Runtime component `String` rejects `Integer`. Runtime component `List` accepts any `List` regardless of its inner type argument; generic `String` is not verified on array store.

**Question 8.** Does `@SafeVarargs` make an array of `List<String>` reifiable?

**Answer:** No. It is an annotation communicating a safety guarantee for an eligible method, adding no runtime metadata to check generic arguments.

**Question 9.** If you want to structure multiple groups of strings, should you prefer `List<String>[]` or `List<List<String>>`?

**Answer:** Unless an API strictly mandates an array, `List<List<String>>` is usually better because it can be instantiated normally and the compiler checks generics at each level; no generic array creation or unchecked cast is needed.

## 19. Takeaways

**Being able to declare a type does not mean you can directly instantiate a runtime object of that type.** Java allows declaring `List<String>[]` and `T[]`, yet forbids `new List<String>[n]` and `new T[n]` because the elements of those array creation expressions lack a suitable reifiable component type.

`new List<?>[n]` is valid because an unbounded wildcard is reifiable; however, `List<?>[]` does not prove that every list contains Strings. Arrays retain their runtime component type to raise `ArrayStoreException` when needed, while generic arguments are typically erased and type mismatches may surface as `ClassCastException` when data is consumed.

In modern Java design, prefer **explicitly typed nested collections**, accept a suitable array from the caller, or use a `Class<T>` token when creating an array of a reifiable component class is mandatory. Use unchecked casts only when you understand all runtime constraints and access boundaries that make them genuinely safe.
